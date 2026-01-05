"""
Cluster State - حالة الكلاستر
================================

يحفظ ويدير حالة:
- Workers المسجلين
- Jobs (queue + running + completed)
- Leases
- Events
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from distributed_cluster.models.events import Event, EventType
from distributed_cluster.models.job import Job, JobResult, JobStatus, JobSubmission
from distributed_cluster.models.resources import ResourceUsage
from distributed_cluster.models.worker import WorkerInfo, WorkerRegistration, WorkerStatus

logger = logging.getLogger(__name__)


@dataclass
class Lease:
    """
    Lease - حجز مؤقت لـ job على worker.

    يمنع race conditions عند التوزيع.
    """

    lease_id: str
    job_id: str
    worker_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    renewed_count: int = 0

    def is_expired(self) -> bool:
        """هل انتهت صلاحية الـ lease؟"""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


class ClusterState:
    """
    حالة الكلاستر المركزية.

    هذا هو "state store" اللي يشترك فيه كل أجزاء Master.
    """

    def __init__(
        self,
        heartbeat_timeout_seconds: int = 30,
        max_events: int = 10000,
    ):
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.max_events = max_events

        # Storage
        self._workers: dict[str, WorkerInfo] = {}
        self._jobs: dict[str, Job] = {}
        self._leases: dict[str, Lease] = {}
        self._events: deque[Event] = deque(maxlen=max_events)

        # Locks for thread safety
        self._lock = threading.RLock()

        # Event callbacks
        self._event_handlers: list[Callable[[Event], None]] = []

        # Stats
        self._stats = {
            "total_jobs_submitted": 0,
            "total_jobs_completed": 0,
            "total_jobs_failed": 0,
            "total_workers_registered": 0,
        }

    # ==================== Workers ====================

    def register_worker(self, registration: WorkerRegistration) -> WorkerInfo:
        """تسجيل worker جديد."""
        with self._lock:
            worker = WorkerInfo.from_registration(registration)
            self._workers[worker.worker_id] = worker
            self._stats["total_workers_registered"] += 1

            # Emit event
            event = Event.worker_registered(worker.worker_id, worker.hostname)
            self._emit_event(event)

            logger.info(f"Worker registered: {worker.worker_id} ({worker.hostname})")
            return worker

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """الحصول على worker بالـ ID."""
        with self._lock:
            return self._workers.get(worker_id)

    def get_all_workers(self) -> list[WorkerInfo]:
        """الحصول على كل workers."""
        with self._lock:
            return list(self._workers.values())

    def get_healthy_workers(self) -> list[WorkerInfo]:
        """الحصول على workers الصحيين فقط."""
        with self._lock:
            return [w for w in self._workers.values() if w.can_accept_jobs]

    def update_worker_heartbeat(
        self,
        worker_id: str,
        usage: ResourceUsage,
    ) -> bool:
        """تحديث heartbeat من worker."""
        with self._lock:
            worker = self._workers.get(worker_id)
            if not worker:
                logger.warning(f"Heartbeat from unknown worker: {worker_id}")
                return False

            worker.update_heartbeat(usage)
            return True

    def remove_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """إزالة worker."""
        with self._lock:
            worker = self._workers.pop(worker_id, None)
            if worker:
                # إعادة jobs اللي كانت عليه للطابور
                for job_id in worker.active_jobs:
                    job = self._jobs.get(job_id)
                    if job and not job.is_terminal:
                        job.prepare_retry()
                        logger.info(f"Job {job_id} returned to queue (worker removed)")

                event = Event.worker_offline(worker_id, "removed")
                self._emit_event(event)

            return worker

    def check_worker_health(self) -> list[str]:
        """
        فحص صحة workers وإرجاع قائمة الـ offline.

        يُستدعى دورياً.
        """
        now = datetime.now(timezone.utc)
        timeout = timedelta(seconds=self.heartbeat_timeout_seconds)
        offline_workers = []

        with self._lock:
            for worker in self._workers.values():
                if worker.status == WorkerStatus.OFFLINE:
                    continue

                if worker.last_heartbeat is None:
                    # جديد، ننتظر أول heartbeat
                    continue

                if now - worker.last_heartbeat > timeout:
                    worker.status = WorkerStatus.OFFLINE
                    offline_workers.append(worker.worker_id)

                    event = Event.worker_offline(worker.worker_id, "heartbeat timeout")
                    self._emit_event(event)

                    logger.warning(f"Worker {worker.worker_id} marked offline (timeout)")

        return offline_workers

    # ==================== Jobs ====================

    def submit_job(self, submission: JobSubmission) -> Job:
        """إرسال job جديد."""
        with self._lock:
            job = Job.from_submission(submission)
            self._jobs[job.job_id] = job
            self._stats["total_jobs_submitted"] += 1

            event = Event.job_submitted(job.job_id, job.name, submission.user_id)
            self._emit_event(event)

            logger.info(f"Job submitted: {job.job_id} ({job.name})")
            return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """الحصول على job بالـ ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def get_all_jobs(self) -> list[Job]:
        """الحصول على كل jobs."""
        with self._lock:
            return list(self._jobs.values())

    def get_pending_jobs(self) -> list[Job]:
        """الحصول على jobs في الانتظار."""
        with self._lock:
            return [j for j in self._jobs.values() if j.status == JobStatus.PENDING]

    def get_running_jobs(self) -> list[Job]:
        """الحصول على jobs قيد التنفيذ."""
        with self._lock:
            return [j for j in self._jobs.values() if j.status == JobStatus.RUNNING]

    def get_jobs_by_worker(self, worker_id: str) -> list[Job]:
        """الحصول على jobs معينة لـ worker."""
        with self._lock:
            return [j for j in self._jobs.values() if j.assigned_worker == worker_id]

    def schedule_job(self, job_id: str, worker_id: str, lease_id: str) -> bool:
        """تعيين job لـ worker (من Scheduler)."""
        with self._lock:
            job = self._jobs.get(job_id)
            worker = self._workers.get(worker_id)

            if not job or not worker:
                return False

            if job.status != JobStatus.PENDING:
                return False

            # إنشاء lease
            lease = Lease(
                lease_id=lease_id,
                job_id=job_id,
                worker_id=worker_id,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
            self._leases[lease_id] = lease

            # تحديث job
            job.schedule(worker_id, lease_id)

            # تحديث worker
            worker.active_jobs.append(job_id)

            event = Event.job_scheduled(job_id, worker_id)
            self._emit_event(event)

            logger.info(f"Job {job_id} scheduled to worker {worker_id}")
            return True

    def start_job(self, job_id: str, worker_id: str) -> bool:
        """تأكيد بدء تنفيذ job (من Worker)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False

            if job.assigned_worker != worker_id:
                logger.warning(f"Job {job_id} start from wrong worker")
                return False

            job.start()

            event = Event.job_started(job_id, worker_id)
            self._emit_event(event)

            return True

    def complete_job(
        self,
        job_id: str,
        worker_id: str,
        result: JobResult,
    ) -> bool:
        """إكمال job (من Worker)."""
        with self._lock:
            job = self._jobs.get(job_id)
            worker = self._workers.get(worker_id)

            if not job:
                return False

            if job.assigned_worker != worker_id:
                logger.warning(f"Job {job_id} completion from wrong worker")
                return False

            # تحديث job
            job.complete(result)

            # تحرير موارد worker
            if worker:
                worker.release_resources(job.submission.resources)
                if job_id in worker.active_jobs:
                    worker.active_jobs.remove(job_id)
                if result.success:
                    worker.completed_jobs_count += 1
                else:
                    worker.failed_jobs_count += 1

            # تنظيف lease
            if job.lease_id and job.lease_id in self._leases:
                del self._leases[job.lease_id]

            # Stats
            if result.success:
                self._stats["total_jobs_completed"] += 1
                event = Event.job_completed(job_id, worker_id, result.exit_code, result.execution_time_seconds)
            else:
                self._stats["total_jobs_failed"] += 1
                event = Event.job_failed(job_id, worker_id, result.error_message or "Unknown error", result.exit_code)

            self._emit_event(event)

            # Retry إذا فشل وممكن
            if not result.success and job.can_retry:
                job.prepare_retry()
                event = Event(
                    event_type=EventType.JOB_RETRYING,
                    job_id=job_id,
                    message=f"Job {job_id} will retry (attempt {job.retry_count + 1})",
                )
                self._emit_event(event)

            logger.info(
                f"Job {job_id} completed: exit_code={result.exit_code}, " f"time={result.execution_time_seconds:.2f}s"
            )
            return True

    def cancel_job(self, job_id: str) -> bool:
        """إلغاء job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False

            if job.is_terminal:
                return False

            worker = None
            if job.assigned_worker:
                worker = self._workers.get(job.assigned_worker)

            job.cancel()

            # تحرير موارد
            if worker:
                worker.release_resources(job.submission.resources)
                if job_id in worker.active_jobs:
                    worker.active_jobs.remove(job_id)

            # تنظيف lease
            if job.lease_id and job.lease_id in self._leases:
                del self._leases[job.lease_id]

            event = Event(
                event_type=EventType.JOB_CANCELLED,
                job_id=job_id,
                message=f"Job {job_id} cancelled",
            )
            self._emit_event(event)

            return True

    # ==================== Events ====================

    def add_event_handler(self, handler: Callable[[Event], None]) -> None:
        """إضافة معالج للأحداث."""
        self._event_handlers.append(handler)

    def _emit_event(self, event: Event) -> None:
        """إرسال حدث."""
        self._events.append(event)
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    def get_recent_events(self, limit: int = 100) -> list[Event]:
        """الحصول على آخر الأحداث."""
        with self._lock:
            events = list(self._events)
            return events[-limit:]

    # ==================== Stats ====================

    def get_stats(self) -> dict:
        """الحصول على إحصائيات الكلاستر."""
        with self._lock:
            workers = list(self._workers.values())
            jobs = list(self._jobs.values())

            return {
                **self._stats,
                "active_workers": len([w for w in workers if w.can_accept_jobs]),
                "total_workers": len(workers),
                "pending_jobs": len([j for j in jobs if j.status == JobStatus.PENDING]),
                "running_jobs": len([j for j in jobs if j.status == JobStatus.RUNNING]),
                "completed_jobs": len([j for j in jobs if j.status == JobStatus.COMPLETED]),
                "failed_jobs": len([j for j in jobs if j.status == JobStatus.FAILED]),
                "total_cpu_cores": sum(w.total_resources.cpu_cores for w in workers),
                "available_cpu_cores": sum(w.available_resources.cpu_cores for w in workers),
                "total_memory_gb": sum(w.total_resources.memory_mb for w in workers) / 1024,
                "available_memory_gb": sum(w.available_resources.memory_mb for w in workers) / 1024,
                "total_gpus": sum(w.total_resources.gpu_count for w in workers),
                "available_gpus": sum(w.available_resources.gpu_count for w in workers),
            }
