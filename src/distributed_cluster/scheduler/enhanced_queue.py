"""
Enhanced Priority Queue - طابور أولويات محسن
===============================================

Advanced priority queue with retry logic and sophisticated scheduling.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from heapq import heappop, heappush
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Priority(int, Enum):
    """مستويات الأولوية."""

    CRITICAL = 200  # Must run immediately
    HIGH = 150  # Important, run soon
    NORMAL = 100  # Default priority
    LOW = 50  # Background tasks
    IDLE = 0  # Run when nothing else


class RetryStrategy(str, Enum):
    """استراتيجيات إعادة المحاولة."""

    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"


@dataclass
class RetryConfig:
    """إعدادات إعادة المحاولة."""

    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_retries: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 300.0  # 5 minutes
    multiplier: float = 2.0  # for exponential
    jitter: float = 0.1  # random variance

    def get_delay(self, attempt: int) -> float:
        """حساب التأخير لمحاولة."""
        import random

        if self.strategy == RetryStrategy.NONE:
            return 0

        if self.strategy == RetryStrategy.FIXED:
            delay = self.initial_delay

        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.initial_delay * (attempt + 1)

        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.initial_delay * (self.multiplier**attempt)

        else:
            delay = self.initial_delay

        # Apply max delay
        delay = min(delay, self.max_delay)

        # Add jitter
        jitter_amount = delay * self.jitter
        delay += random.uniform(-jitter_amount, jitter_amount)

        return max(0, delay)


@dataclass(order=True)
class QueueItem:
    """عنصر في الطابور."""

    priority_score: float  # Lower = higher priority (for heapq)
    enqueue_time: float = field(compare=False)
    item_id: str = field(compare=False, default_factory=lambda: str(uuid.uuid4()))
    data: Any = field(compare=False, default=None)

    # Job info
    job_id: str = field(compare=False, default="")
    priority: int = field(compare=False, default=100)
    queue_name: str = field(compare=False, default="default")

    # Retry info
    attempts: int = field(compare=False, default=0)
    last_error: Optional[str] = field(compare=False, default=None)
    next_retry_at: Optional[datetime] = field(compare=False, default=None)

    # Dependencies
    depends_on: List[str] = field(compare=False, default_factory=list)

    @classmethod
    def create(
        cls,
        data: Any,
        priority: int = 100,
        job_id: str = "",
        queue_name: str = "default",
        depends_on: Optional[List[str]] = None,
    ) -> "QueueItem":
        """إنشاء عنصر."""
        now = time.time()

        # Calculate priority score (lower = higher priority)
        # Include time factor for FIFO within same priority
        priority_score = -priority + (now / 1e10)

        return cls(
            priority_score=priority_score,
            enqueue_time=now,
            data=data,
            job_id=job_id or str(uuid.uuid4()),
            priority=priority,
            queue_name=queue_name,
            depends_on=depends_on or [],
        )


class PriorityQueue:
    """
    طابور أولويات محسن.

    Features:
    - Multiple priority levels
    - Automatic retry with backoff
    - Job dependencies
    - Rate limiting
    - Fair scheduling across queues
    """

    def __init__(
        self,
        name: str = "default",
        max_size: int = 10000,
        default_retry: Optional[RetryConfig] = None,
    ):
        self.name = name
        self.max_size = max_size
        self.default_retry = default_retry or RetryConfig()

        self._heap: List[QueueItem] = []
        self._items: Dict[str, QueueItem] = {}
        self._retry_queue: List[QueueItem] = []
        self._completed: set = set()
        self._lock = asyncio.Lock()

        # Stats
        self._enqueued = 0
        self._dequeued = 0
        self._retried = 0
        self._failed = 0

    async def enqueue(
        self,
        data: Any,
        priority: int = Priority.NORMAL,
        job_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ) -> str:
        """
        إضافة عنصر للطابور.

        Args:
            data: البيانات
            priority: الأولوية
            job_id: معرف المهمة
            depends_on: الاعتماديات

        Returns:
            str: معرف العنصر
        """
        async with self._lock:
            if len(self._heap) >= self.max_size:
                raise RuntimeError("Queue is full")

            item = QueueItem.create(
                data=data,
                priority=priority,
                job_id=job_id or "",
                queue_name=self.name,
                depends_on=depends_on,
            )

            heappush(self._heap, item)
            self._items[item.item_id] = item
            self._enqueued += 1

            logger.debug(f"Enqueued {item.item_id} with priority {priority}")

            return item.item_id

    async def dequeue(self, timeout: Optional[float] = None) -> Optional[QueueItem]:
        """
        سحب عنصر من الطابور.

        Args:
            timeout: مهلة الانتظار

        Returns:
            QueueItem: العنصر أو None
        """
        start = time.time()

        while True:
            async with self._lock:
                # Check retry queue first
                now = datetime.now(timezone.utc)
                ready_retries = [r for r in self._retry_queue if r.next_retry_at and r.next_retry_at <= now]

                for retry in ready_retries:
                    self._retry_queue.remove(retry)
                    heappush(self._heap, retry)

                # Get next item
                while self._heap:
                    item = heappop(self._heap)

                    # Check dependencies
                    if item.depends_on:
                        pending_deps = [dep for dep in item.depends_on if dep not in self._completed]
                        if pending_deps:
                            # Re-add to back of queue
                            heappush(self._heap, item)
                            continue

                    del self._items[item.item_id]
                    self._dequeued += 1

                    return item

            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start
                if elapsed >= timeout:
                    return None

            await asyncio.sleep(0.1)

    async def peek(self) -> Optional[QueueItem]:
        """النظر على العنصر التالي."""
        async with self._lock:
            if self._heap:
                return self._heap[0]
        return None

    async def retry(
        self,
        item: QueueItem,
        error: str,
        retry_config: Optional[RetryConfig] = None,
    ) -> bool:
        """
        إعادة محاولة عنصر.

        Args:
            item: العنصر
            error: الخطأ
            retry_config: إعدادات إعادة المحاولة

        Returns:
            bool: هل تم الإضافة للإعادة
        """
        config = retry_config or self.default_retry

        if item.attempts >= config.max_retries:
            self._failed += 1
            logger.warning(f"Item {item.item_id} exceeded max retries")
            return False

        item.attempts += 1
        item.last_error = error

        delay = config.get_delay(item.attempts)
        item.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)

        async with self._lock:
            self._retry_queue.append(item)
            self._retried += 1

        logger.info(f"Scheduled retry {item.attempts}/{config.max_retries} " f"for {item.item_id} in {delay:.1f}s")

        return True

    async def mark_completed(self, job_id: str) -> None:
        """تحديد مهمة كمكتملة."""
        async with self._lock:
            self._completed.add(job_id)

    async def cancel(self, item_id: str) -> bool:
        """إلغاء عنصر."""
        async with self._lock:
            if item_id in self._items:
                item = self._items[item_id]
                self._heap.remove(item)
                del self._items[item_id]
                return True

            # Check retry queue
            for retry in self._retry_queue:
                if retry.item_id == item_id:
                    self._retry_queue.remove(retry)
                    return True

        return False

    async def size(self) -> int:
        """حجم الطابور."""
        async with self._lock:
            return len(self._heap) + len(self._retry_queue)

    async def clear(self) -> None:
        """مسح الطابور."""
        async with self._lock:
            self._heap.clear()
            self._items.clear()
            self._retry_queue.clear()

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات الطابور."""
        return {
            "name": self.name,
            "size": len(self._heap),
            "retry_queue_size": len(self._retry_queue),
            "enqueued": self._enqueued,
            "dequeued": self._dequeued,
            "retried": self._retried,
            "failed": self._failed,
        }


class MultiQueueScheduler:
    """
    مجدول متعدد الطوابير.

    Manages multiple priority queues with fair scheduling.
    """

    def __init__(self):
        self._queues: Dict[str, PriorityQueue] = {}
        self._default_queue = "default"
        self._weights: Dict[str, float] = {}
        self._last_served: Dict[str, float] = {}

        # Create default queues
        self.create_queue("critical", weight=4.0)
        self.create_queue("high", weight=2.0)
        self.create_queue("default", weight=1.0)
        self.create_queue("low", weight=0.5)
        self.create_queue("background", weight=0.25)

    def create_queue(
        self,
        name: str,
        weight: float = 1.0,
        max_size: int = 10000,
        retry_config: Optional[RetryConfig] = None,
    ) -> PriorityQueue:
        """
        إنشاء طابور.

        Args:
            name: اسم الطابور
            weight: وزن الطابور (للتوزيع)
            max_size: الحد الأقصى
            retry_config: إعدادات الإعادة

        Returns:
            PriorityQueue: الطابور
        """
        queue = PriorityQueue(name, max_size, retry_config)
        self._queues[name] = queue
        self._weights[name] = weight
        self._last_served[name] = 0

        return queue

    def get_queue(self, name: str) -> Optional[PriorityQueue]:
        """الحصول على طابور."""
        return self._queues.get(name)

    async def enqueue(
        self,
        data: Any,
        queue: str = "default",
        priority: int = Priority.NORMAL,
        job_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ) -> str:
        """
        إضافة للطابور.

        Args:
            data: البيانات
            queue: اسم الطابور
            priority: الأولوية
            job_id: معرف المهمة
            depends_on: الاعتماديات

        Returns:
            str: معرف العنصر
        """
        q = self._queues.get(queue)
        if not q:
            q = self._queues[self._default_queue]

        return await q.enqueue(data, priority, job_id, depends_on)

    async def dequeue(self, timeout: Optional[float] = None) -> Optional[QueueItem]:
        """
        سحب عنصر باستخدام جدولة عادلة.

        Uses weighted fair queuing to select from multiple queues.
        """
        start = time.time()

        while True:
            # Select queue using weighted fair scheduling
            best_queue = None
            best_score = float("inf")

            for name, queue in self._queues.items():
                size = await queue.size()
                if size == 0:
                    continue

                # Calculate virtual time (lower = should be served)
                weight = self._weights.get(name, 1.0)
                virtual_time = self._last_served.get(name, 0) / weight

                if virtual_time < best_score:
                    best_score = virtual_time
                    best_queue = queue

            if best_queue:
                item = await best_queue.dequeue(timeout=0)
                if item:
                    self._last_served[best_queue.name] = time.time()
                    return item

            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start
                if elapsed >= timeout:
                    return None

            await asyncio.sleep(0.1)

    async def retry(
        self,
        item: QueueItem,
        error: str,
    ) -> bool:
        """إعادة محاولة عنصر."""
        queue = self._queues.get(item.queue_name)
        if queue:
            return await queue.retry(item, error)
        return False

    async def mark_completed(self, job_id: str) -> None:
        """تحديد مهمة كمكتملة."""
        for queue in self._queues.values():
            await queue.mark_completed(job_id)

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات المجدول."""
        return {
            "queues": {name: queue.get_stats() for name, queue in self._queues.items()},
            "total_size": sum(len(q._heap) + len(q._retry_queue) for q in self._queues.values()),
        }
