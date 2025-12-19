"""
Event Models - نماذج الأحداث
================================

أنواع الأحداث التي تُبث للمراقبة والتتبع.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """أنواع الأحداث في النظام."""

    # Worker events
    WORKER_REGISTERED = "worker.registered"
    WORKER_HEARTBEAT = "worker.heartbeat"
    WORKER_OFFLINE = "worker.offline"
    WORKER_ERROR = "worker.error"
    WORKER_DRAINING = "worker.draining"

    # Job events
    JOB_SUBMITTED = "job.submitted"
    JOB_SCHEDULED = "job.scheduled"
    JOB_STARTED = "job.started"
    JOB_PROGRESS = "job.progress"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_TIMEOUT = "job.timeout"
    JOB_CANCELLED = "job.cancelled"
    JOB_RETRYING = "job.retrying"

    # Scheduler events
    SCHEDULER_NO_RESOURCES = "scheduler.no_resources"
    SCHEDULER_ASSIGNED = "scheduler.assigned"

    # System events
    MASTER_LEADER_ELECTED = "master.leader_elected"
    MASTER_LEADER_LOST = "master.leader_lost"
    SYSTEM_ALERT = "system.alert"


@dataclass
class Event:
    """
    حدث في النظام.

    يُستخدم للمراقبة والإشعارات.
    """

    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = ""  # من أين جاء الحدث (worker_id, master_id, etc.)
    data: dict[str, Any] = field(default_factory=dict)
    message: Optional[str] = None

    # للربط بـ entities
    job_id: Optional[str] = None
    worker_id: Optional[str] = None

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "data": self.data,
            "message": self.message,
            "job_id": self.job_id,
            "worker_id": self.worker_id,
        }

    @classmethod
    def worker_registered(cls, worker_id: str, hostname: str) -> Event:
        """حدث تسجيل worker جديد."""
        return cls(
            event_type=EventType.WORKER_REGISTERED,
            source="master",
            worker_id=worker_id,
            message=f"Worker {hostname} registered with ID {worker_id}",
            data={"hostname": hostname},
        )

    @classmethod
    def worker_offline(cls, worker_id: str, reason: str = "heartbeat timeout") -> Event:
        """حدث worker أصبح offline."""
        return cls(
            event_type=EventType.WORKER_OFFLINE,
            source="master",
            worker_id=worker_id,
            message=f"Worker {worker_id} went offline: {reason}",
            data={"reason": reason},
        )

    @classmethod
    def job_submitted(cls, job_id: str, name: str, user_id: Optional[str] = None) -> Event:
        """حدث إرسال job جديد."""
        return cls(
            event_type=EventType.JOB_SUBMITTED,
            source="api",
            job_id=job_id,
            message=f"Job '{name}' submitted",
            data={"name": name, "user_id": user_id},
        )

    @classmethod
    def job_scheduled(cls, job_id: str, worker_id: str) -> Event:
        """حدث تعيين job لـ worker."""
        return cls(
            event_type=EventType.JOB_SCHEDULED,
            source="scheduler",
            job_id=job_id,
            worker_id=worker_id,
            message=f"Job {job_id} scheduled to worker {worker_id}",
        )

    @classmethod
    def job_started(cls, job_id: str, worker_id: str) -> Event:
        """حدث بدء تنفيذ job."""
        return cls(
            event_type=EventType.JOB_STARTED,
            source=worker_id,
            job_id=job_id,
            worker_id=worker_id,
            message=f"Job {job_id} started on worker {worker_id}",
        )

    @classmethod
    def job_completed(
        cls,
        job_id: str,
        worker_id: str,
        exit_code: int,
        execution_time: float,
    ) -> Event:
        """حدث انتهاء job بنجاح."""
        return cls(
            event_type=EventType.JOB_COMPLETED,
            source=worker_id,
            job_id=job_id,
            worker_id=worker_id,
            message=f"Job {job_id} completed with exit code {exit_code}",
            data={
                "exit_code": exit_code,
                "execution_time_seconds": execution_time,
            },
        )

    @classmethod
    def job_failed(
        cls,
        job_id: str,
        worker_id: str,
        error: str,
        exit_code: int = -1,
    ) -> Event:
        """حدث فشل job."""
        return cls(
            event_type=EventType.JOB_FAILED,
            source=worker_id,
            job_id=job_id,
            worker_id=worker_id,
            message=f"Job {job_id} failed: {error}",
            data={"error": error, "exit_code": exit_code},
        )

    @classmethod
    def scheduler_no_resources(cls, job_id: str, required: dict) -> Event:
        """حدث عدم توفر موارد كافية."""
        return cls(
            event_type=EventType.SCHEDULER_NO_RESOURCES,
            source="scheduler",
            job_id=job_id,
            message=f"No resources available for job {job_id}",
            data={"required_resources": required},
        )
