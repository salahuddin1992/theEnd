"""
Scheduler - المجدول
=======================

"الدماغ" - يقرر أي job يروح لأي worker.

سياسات الجدولة:
- First-Fit: أول worker مناسب
- Best-Fit: أفضل worker (أقل موارد فائضة)
- Worst-Fit: أكثر worker عنده موارد فائضة
- Priority: الأولوية أولاً
- Fair-Share: توزيع عادل بين المستخدمين
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from distributed_cluster.models.job import Job
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerInfo

logger = logging.getLogger(__name__)


class SchedulingPolicy(str, Enum):
    """سياسات الجدولة المتاحة."""
    FIRST_FIT = "first_fit"  # أول worker مناسب
    BEST_FIT = "best_fit"  # أقل موارد فائضة (bin packing)
    WORST_FIT = "worst_fit"  # أكثر موارد فائضة (spread)
    ROUND_ROBIN = "round_robin"  # بالتناوب
    LEAST_LOADED = "least_loaded"  # أقل حمل


@dataclass
class SchedulingDecision:
    """قرار الجدولة."""
    job: Job
    worker: WorkerInfo
    lease_id: str
    decision_time: datetime
    policy_used: SchedulingPolicy


class Scheduler:
    """
    مجدول الـ Jobs.

    يأخذ قائمة jobs في الانتظار وقائمة workers المتاحين،
    ويقرر أي job يروح لأي worker.
    """

    def __init__(
        self,
        policy: SchedulingPolicy = SchedulingPolicy.BEST_FIT,
        max_jobs_per_worker: int = 10,
    ):
        self.policy = policy
        self.max_jobs_per_worker = max_jobs_per_worker
        self._round_robin_index = 0

        # Internal storage for stateful scheduling
        self._workers: dict[str, WorkerInfo] = {}
        self._pending_jobs: dict[str, Job] = {}

    @property
    def workers(self) -> dict[str, WorkerInfo]:
        """الـ workers المسجلين."""
        return self._workers

    @property
    def pending_jobs(self) -> dict[str, Job]:
        """الـ jobs في الانتظار."""
        return self._pending_jobs

    def add_worker(self, worker: WorkerInfo) -> None:
        """إضافة worker للمجدول."""
        self._workers[worker.worker_id] = worker

    def remove_worker(self, worker_id: str) -> bool:
        """إزالة worker من المجدول."""
        if worker_id in self._workers:
            del self._workers[worker_id]
            return True
        return False

    def submit_job(self, job: Job) -> None:
        """إضافة job للانتظار."""
        self._pending_jobs[job.job_id] = job

    def schedule_next(self) -> Optional[tuple[str, str, str]]:
        """
        جدولة الـ job التالي.

        Returns:
            (job_id, worker_id, lease_id) أو None إذا لا يوجد job أو worker
        """
        if not self._pending_jobs or not self._workers:
            return None

        pending = list(self._pending_jobs.values())
        workers = list(self._workers.values())

        decisions = self.schedule(pending, workers)
        if not decisions:
            return None

        decision = decisions[0]
        # Remove from pending
        if decision.job.job_id in self._pending_jobs:
            del self._pending_jobs[decision.job.job_id]

        return (decision.job.job_id, decision.worker.worker_id, decision.lease_id)

    def schedule(
        self,
        pending_jobs: list[Job],
        workers: list[WorkerInfo],
    ) -> list[SchedulingDecision]:
        """
        جدولة مجموعة jobs على workers.

        Args:
            pending_jobs: Jobs في حالة PENDING
            workers: Workers المتاحين

        Returns:
            قائمة قرارات الجدولة
        """
        if not pending_jobs or not workers:
            return []

        # فلترة workers المتاحين فعلياً
        available_workers = [w for w in workers if w.can_accept_jobs]
        if not available_workers:
            logger.debug("No available workers for scheduling")
            return []

        # ترتيب jobs حسب الأولوية
        sorted_jobs = sorted(
            pending_jobs,
            key=lambda j: (
                -j.submission.priority.value,  # الأولوية الأعلى أولاً
                j.created_at,  # الأقدم أولاً (FIFO ضمن نفس الأولوية)
            ),
        )

        decisions = []

        # محاولة جدولة كل job
        for job in sorted_jobs:
            decision = self._schedule_single_job(job, available_workers)
            if decision:
                decisions.append(decision)

                # تحديث الموارد المتاحة للـ worker
                decision.worker.allocate_resources(job.submission.resources)
                decision.worker.active_jobs.append(job.job_id)

        return decisions

    def _schedule_single_job(
        self,
        job: Job,
        workers: list[WorkerInfo],
    ) -> Optional[SchedulingDecision]:
        """جدولة job واحد."""

        # فلترة workers حسب المتطلبات
        candidates = self._filter_candidates(job, workers)
        if not candidates:
            logger.debug(f"No candidates for job {job.job_id}")
            return None

        # اختيار worker حسب السياسة
        selected = self._select_worker(job, candidates)
        if not selected:
            return None

        # إنشاء قرار
        lease_id = f"lease-{uuid.uuid4().hex[:12]}"
        return SchedulingDecision(
            job=job,
            worker=selected,
            lease_id=lease_id,
            decision_time=datetime.utcnow(),
            policy_used=self.policy,
        )

    def _filter_candidates(
        self,
        job: Job,
        workers: list[WorkerInfo],
    ) -> list[WorkerInfo]:
        """فلترة workers حسب متطلبات الـ job."""
        candidates = []

        for worker in workers:
            # التحقق من عدد jobs الحالية
            if len(worker.active_jobs) >= self.max_jobs_per_worker:
                continue

            # التحقق من الموارد
            if not job.submission.resources.fits_in(worker.available_resources):
                continue

            # التحقق من tags المطلوبة
            if job.submission.required_tags:
                if not all(tag in worker.tags for tag in job.submission.required_tags):
                    continue

            # التحقق من worker مفضل
            if job.submission.preferred_worker:
                if job.submission.preferred_worker == worker.worker_id:
                    # إذا موجود ومتاح، أعطيه الأولوية
                    return [worker]
                # إذا مو المفضل، نستمر بالبحث

            # التحقق من Docker إذا مطلوب
            if job.submission.docker_image and not worker.docker_available:
                continue

            candidates.append(worker)

        return candidates

    def _select_worker(
        self,
        job: Job,
        candidates: list[WorkerInfo],
    ) -> Optional[WorkerInfo]:
        """اختيار worker من المرشحين حسب السياسة."""
        if not candidates:
            return None

        if self.policy == SchedulingPolicy.FIRST_FIT:
            return candidates[0]

        elif self.policy == SchedulingPolicy.BEST_FIT:
            # أقل موارد فائضة (bin packing)
            return min(
                candidates,
                key=lambda w: self._calculate_slack(
                    w.available_resources, job.submission.resources
                ),
            )

        elif self.policy == SchedulingPolicy.WORST_FIT:
            # أكثر موارد فائضة (spread)
            return max(
                candidates,
                key=lambda w: self._calculate_slack(
                    w.available_resources, job.submission.resources
                ),
            )

        elif self.policy == SchedulingPolicy.ROUND_ROBIN:
            # بالتناوب
            selected = candidates[self._round_robin_index % len(candidates)]
            self._round_robin_index += 1
            return selected

        elif self.policy == SchedulingPolicy.LEAST_LOADED:
            # أقل حمل (أقل jobs نشطة)
            return min(candidates, key=lambda w: len(w.active_jobs))

        return candidates[0]

    def _calculate_slack(
        self,
        available: ResourceSpec,
        required: ResourceSpec,
    ) -> float:
        """
        حساب "الفائض" بعد تخصيص الموارد.

        قيمة أقل = مناسبة أفضل (best fit)
        """
        remaining = available.subtract(required)

        # نحسب نسبة الفائض الإجمالية
        cpu_slack = remaining.cpu_cores / max(available.cpu_cores, 1)
        memory_slack = remaining.memory_mb / max(available.memory_mb, 1)
        gpu_slack = remaining.gpu_count / max(available.gpu_count, 1) if available.gpu_count > 0 else 0

        # المتوسط المرجح
        return (cpu_slack + memory_slack + gpu_slack) / 3

    def estimate_wait_time(
        self,
        job: Job,
        pending_ahead: int,
        avg_job_duration: float = 60.0,
    ) -> float:
        """تقدير وقت الانتظار لـ job."""
        # تقدير بسيط: عدد jobs قبله * متوسط الوقت
        return pending_ahead * avg_job_duration


class SchedulerLoop:
    """
    حلقة الجدولة المستمرة.

    تشتغل كـ background task وتحاول جدولة jobs باستمرار.
    """

    def __init__(
        self,
        scheduler: Scheduler,
        get_pending_jobs: Callable[[], list[Job]],
        get_workers: Callable[[], list[WorkerInfo]],
        on_decision: Callable[[SchedulingDecision], None],
        on_no_resources: Callable[[Job], None],
        interval_seconds: float = 1.0,
    ):
        self.scheduler = scheduler
        self.get_pending_jobs = get_pending_jobs
        self.get_workers = get_workers
        self.on_decision = on_decision
        self.on_no_resources = on_no_resources
        self.interval_seconds = interval_seconds

        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """بدء حلقة الجدولة."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler loop started")

    async def stop(self) -> None:
        """إيقاف حلقة الجدولة."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler loop stopped")

    async def _loop(self) -> None:
        """الحلقة الرئيسية."""
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")

            await asyncio.sleep(self.interval_seconds)

    async def _tick(self) -> None:
        """دورة جدولة واحدة."""
        pending_jobs = self.get_pending_jobs()
        if not pending_jobs:
            return

        workers = self.get_workers()
        if not workers:
            # لا workers متاحين
            for job in pending_jobs[:5]:  # نبلّغ عن أول 5 فقط
                self.on_no_resources(job)
            return

        # جدولة
        decisions = self.scheduler.schedule(pending_jobs, workers)

        # تنفيذ القرارات
        for decision in decisions:
            try:
                self.on_decision(decision)
            except Exception as e:
                logger.error(f"Failed to apply scheduling decision: {e}")

        # تحقق من jobs اللي ما تمت جدولتها
        scheduled_ids = {d.job.job_id for d in decisions}
        unscheduled = [j for j in pending_jobs if j.job_id not in scheduled_ids]

        for job in unscheduled[:3]:  # نبلّغ عن أول 3 فقط
            self.on_no_resources(job)
