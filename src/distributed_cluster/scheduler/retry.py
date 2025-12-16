"""
Job Retry Manager - مدير إعادة المحاولة
========================================

إدارة إعادة محاولة المهام الفاشلة:
- Exponential backoff
- Jitter لتجنب thundering herd
- Circuit breaker للعمال المتكررين الفشل
- Dead letter queue للمهام المستنفدة
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List, Set, Callable, Awaitable, Any
import logging
import heapq

from distributed_cluster.models.job import Job, JobStatus
from distributed_cluster.models.events import Event, EventType

logger = logging.getLogger(__name__)


class RetryStrategy(str, Enum):
    """استراتيجية إعادة المحاولة."""
    IMMEDIATE = "immediate"  # فوري
    LINEAR = "linear"  # تأخير ثابت
    EXPONENTIAL = "exponential"  # تصاعدي أسي
    FIBONACCI = "fibonacci"  # تتابع فيبوناتشي


class FailureReason(str, Enum):
    """سبب الفشل."""
    WORKER_FAILURE = "worker_failure"  # فشل العامل
    TIMEOUT = "timeout"  # انتهى الوقت
    OUT_OF_MEMORY = "out_of_memory"  # نفذت الذاكرة
    EXIT_CODE = "exit_code"  # كود خروج غير صفري
    CANCELLED = "cancelled"  # ألغيت
    LEASE_EXPIRED = "lease_expired"  # انتهى الـ lease
    UNKNOWN = "unknown"


@dataclass
class RetryPolicy:
    """سياسة إعادة المحاولة."""
    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL

    # Delays
    initial_delay_seconds: float = 5.0
    max_delay_seconds: float = 300.0  # 5 minutes
    multiplier: float = 2.0

    # Jitter to prevent thundering herd
    jitter: bool = True
    jitter_factor: float = 0.1  # ±10%

    # Failure-specific handling
    non_retryable_exit_codes: Set[int] = field(default_factory=lambda: {1, 2, 126, 127})
    retry_on_timeout: bool = True
    retry_on_oom: bool = False  # Often not worth retrying
    retry_on_worker_failure: bool = True

    def should_retry(self, failure_reason: FailureReason, exit_code: Optional[int]) -> bool:
        """هل يجب إعادة المحاولة؟"""
        if failure_reason == FailureReason.CANCELLED:
            return False

        if failure_reason == FailureReason.TIMEOUT:
            return self.retry_on_timeout

        if failure_reason == FailureReason.OUT_OF_MEMORY:
            return self.retry_on_oom

        if failure_reason == FailureReason.WORKER_FAILURE:
            return self.retry_on_worker_failure

        if exit_code is not None and exit_code in self.non_retryable_exit_codes:
            return False

        return True

    def calculate_delay(self, attempt: int) -> float:
        """حساب التأخير للمحاولة."""
        if self.strategy == RetryStrategy.IMMEDIATE:
            delay = 0.0
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.initial_delay_seconds
        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.initial_delay_seconds * (self.multiplier ** attempt)
        elif self.strategy == RetryStrategy.FIBONACCI:
            delay = self.initial_delay_seconds * self._fibonacci(attempt + 1)
        else:
            delay = self.initial_delay_seconds

        # Cap at max delay
        delay = min(delay, self.max_delay_seconds)

        # Add jitter
        if self.jitter and delay > 0:
            jitter_range = delay * self.jitter_factor
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

    def _fibonacci(self, n: int) -> int:
        """حساب عدد فيبوناتشي."""
        if n <= 1:
            return n
        a, b = 0, 1
        for _ in range(n - 1):
            a, b = b, a + b
        return b


@dataclass
class RetryAttempt:
    """معلومات محاولة إعادة."""
    job_id: str
    attempt_number: int
    scheduled_at: datetime
    failure_reason: FailureReason
    exit_code: Optional[int] = None
    worker_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class PendingRetry:
    """إعادة محاولة معلقة."""
    job_id: str
    retry_at: datetime
    attempt_number: int

    def __lt__(self, other: PendingRetry) -> bool:
        return self.retry_at < other.retry_at


class RetryManager:
    """
    مدير إعادة المحاولة.

    يدير:
    - جدولة إعادة المحاولات
    - Exponential backoff
    - Circuit breaker للعمال
    - Dead letter queue
    """

    def __init__(
        self,
        default_policy: Optional[RetryPolicy] = None,
        on_retry_scheduled: Optional[Callable[[str, datetime], Awaitable[None]]] = None,
        on_retry_exhausted: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        self.default_policy = default_policy or RetryPolicy()
        self.on_retry_scheduled = on_retry_scheduled
        self.on_retry_exhausted = on_retry_exhausted

        # Retry history per job
        self._retry_history: Dict[str, List[RetryAttempt]] = {}

        # Pending retries (priority queue)
        self._pending_retries: List[PendingRetry] = []

        # Per-job policies
        self._job_policies: Dict[str, RetryPolicy] = {}

        # Circuit breaker state for workers
        self._worker_failures: Dict[str, List[datetime]] = {}
        self._circuit_open: Set[str] = set()

        # Dead letter queue
        self._dead_letter_queue: List[str] = []

        # Background processor
        self._processor_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """بدء المدير."""
        self._running = True
        self._processor_task = asyncio.create_task(self._process_retries())
        logger.info("Retry manager started")

    async def stop(self) -> None:
        """إيقاف المدير."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("Retry manager stopped")

    def set_policy(self, job_id: str, policy: RetryPolicy) -> None:
        """تعيين سياسة لمهمة محددة."""
        self._job_policies[job_id] = policy

    def get_policy(self, job_id: str) -> RetryPolicy:
        """الحصول على سياسة المهمة."""
        return self._job_policies.get(job_id, self.default_policy)

    async def handle_failure(
        self,
        job: Job,
        failure_reason: FailureReason,
        exit_code: Optional[int] = None,
        worker_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        معالجة فشل مهمة.

        Args:
            job: المهمة الفاشلة
            failure_reason: سبب الفشل
            exit_code: كود الخروج
            worker_id: معرف العامل
            error_message: رسالة الخطأ

        Returns:
            True إذا تم جدولة إعادة المحاولة، False إذا استنفدت المحاولات
        """
        job_id = job.job_id
        policy = self.get_policy(job_id)

        # Record attempt
        attempt_number = len(self._retry_history.get(job_id, []))
        attempt = RetryAttempt(
            job_id=job_id,
            attempt_number=attempt_number,
            scheduled_at=datetime.utcnow(),
            failure_reason=failure_reason,
            exit_code=exit_code,
            worker_id=worker_id,
            error_message=error_message,
        )

        if job_id not in self._retry_history:
            self._retry_history[job_id] = []
        self._retry_history[job_id].append(attempt)

        # Update worker circuit breaker
        if worker_id:
            await self._record_worker_failure(worker_id)

        # Check if should retry
        if not policy.should_retry(failure_reason, exit_code):
            logger.info(f"Job {job_id} failure not retryable: {failure_reason}")
            await self._move_to_dlq(job_id)
            return False

        # Check retry limit
        if attempt_number >= policy.max_retries:
            logger.info(f"Job {job_id} exhausted retries ({policy.max_retries})")
            await self._move_to_dlq(job_id)
            return False

        # Schedule retry
        delay = policy.calculate_delay(attempt_number)
        retry_at = datetime.utcnow() + timedelta(seconds=delay)

        pending = PendingRetry(
            job_id=job_id,
            retry_at=retry_at,
            attempt_number=attempt_number + 1,
        )
        heapq.heappush(self._pending_retries, pending)

        logger.info(
            f"Job {job_id} scheduled for retry #{attempt_number + 1} "
            f"at {retry_at.isoformat()} (delay={delay:.1f}s)"
        )

        if self.on_retry_scheduled:
            await self.on_retry_scheduled(job_id, retry_at)

        return True

    async def _process_retries(self) -> None:
        """معالجة إعادة المحاولات المعلقة."""
        while self._running:
            try:
                now = datetime.utcnow()

                # Process due retries
                while self._pending_retries and self._pending_retries[0].retry_at <= now:
                    pending = heapq.heappop(self._pending_retries)

                    logger.info(
                        f"Processing retry for job {pending.job_id} "
                        f"(attempt #{pending.attempt_number})"
                    )

                    # Notify (the scheduler will pick up and reschedule)
                    if self.on_retry_scheduled:
                        await self.on_retry_scheduled(pending.job_id, now)

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Retry processing error: {e}")
                await asyncio.sleep(1)

    async def _move_to_dlq(self, job_id: str) -> None:
        """نقل مهمة إلى Dead Letter Queue."""
        self._dead_letter_queue.append(job_id)
        logger.warning(f"Job {job_id} moved to dead letter queue")

        if self.on_retry_exhausted:
            await self.on_retry_exhausted(job_id)

    async def _record_worker_failure(self, worker_id: str) -> None:
        """تسجيل فشل عامل (للـ circuit breaker)."""
        now = datetime.utcnow()

        if worker_id not in self._worker_failures:
            self._worker_failures[worker_id] = []

        # Add failure
        self._worker_failures[worker_id].append(now)

        # Keep only recent failures (last 5 minutes)
        cutoff = now - timedelta(minutes=5)
        self._worker_failures[worker_id] = [
            t for t in self._worker_failures[worker_id] if t > cutoff
        ]

        # Check circuit breaker (5 failures in 5 minutes)
        if len(self._worker_failures[worker_id]) >= 5:
            if worker_id not in self._circuit_open:
                self._circuit_open.add(worker_id)
                logger.warning(f"Circuit breaker OPEN for worker {worker_id}")

    def is_worker_healthy(self, worker_id: str) -> bool:
        """هل العامل سليم (circuit breaker مغلق)؟"""
        if worker_id not in self._circuit_open:
            return True

        # Check if circuit should close (after 30 seconds)
        failures = self._worker_failures.get(worker_id, [])
        if failures:
            last_failure = max(failures)
            if datetime.utcnow() - last_failure > timedelta(seconds=30):
                self._circuit_open.discard(worker_id)
                logger.info(f"Circuit breaker CLOSED for worker {worker_id}")
                return True

        return False

    def get_retry_count(self, job_id: str) -> int:
        """عدد إعادة المحاولات لمهمة."""
        return len(self._retry_history.get(job_id, []))

    def get_retry_history(self, job_id: str) -> List[RetryAttempt]:
        """تاريخ إعادة المحاولات."""
        return self._retry_history.get(job_id, []).copy()

    def get_pending_retries(self) -> List[PendingRetry]:
        """إعادة المحاولات المعلقة."""
        return sorted(self._pending_retries)

    def get_dead_letter_queue(self) -> List[str]:
        """Dead Letter Queue."""
        return self._dead_letter_queue.copy()

    def remove_from_dlq(self, job_id: str) -> bool:
        """إزالة من DLQ (للإعادة اليدوية)."""
        if job_id in self._dead_letter_queue:
            self._dead_letter_queue.remove(job_id)
            return True
        return False

    def clear_job_history(self, job_id: str) -> None:
        """مسح تاريخ مهمة (عند النجاح)."""
        self._retry_history.pop(job_id, None)
        self._job_policies.pop(job_id, None)

    @property
    def stats(self) -> Dict[str, Any]:
        """إحصائيات."""
        return {
            "pending_retries": len(self._pending_retries),
            "dlq_size": len(self._dead_letter_queue),
            "tracked_jobs": len(self._retry_history),
            "unhealthy_workers": len(self._circuit_open),
        }


def classify_failure(
    exit_code: Optional[int],
    error_message: Optional[str],
    timed_out: bool,
    worker_lost: bool,
) -> FailureReason:
    """
    تصنيف سبب الفشل.

    Args:
        exit_code: كود الخروج
        error_message: رسالة الخطأ
        timed_out: هل انتهى الوقت؟
        worker_lost: هل فُقد الاتصال بالعامل؟

    Returns:
        سبب الفشل
    """
    if worker_lost:
        return FailureReason.WORKER_FAILURE

    if timed_out:
        return FailureReason.TIMEOUT

    if error_message:
        error_lower = error_message.lower()
        if "out of memory" in error_lower or "oom" in error_lower:
            return FailureReason.OUT_OF_MEMORY
        if "cancelled" in error_lower or "canceled" in error_lower:
            return FailureReason.CANCELLED

    if exit_code is not None and exit_code != 0:
        return FailureReason.EXIT_CODE

    return FailureReason.UNKNOWN
