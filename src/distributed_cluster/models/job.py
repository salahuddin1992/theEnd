"""
Job Models - نماذج الـ Jobs
==============================

تعريفات الـ Job (المهمة) والحالات والنتائج.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from distributed_cluster.models.resources import ResourceSpec


class JobStatus(str, Enum):
    """حالات الـ Job."""

    PENDING = "pending"  # في الطابور، ينتظر worker
    SCHEDULED = "scheduled"  # تم تعيينه لـ worker
    RUNNING = "running"  # يشتغل حالياً
    COMPLETED = "completed"  # انتهى بنجاح
    FAILED = "failed"  # فشل
    CANCELLED = "cancelled"  # ألغي
    TIMEOUT = "timeout"  # تجاوز الوقت المحدد


class JobPriority(int, Enum):
    """أولويات الـ Jobs."""

    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class JobSubmission:
    """
    طلب إرسال Job جديد.

    هذا ما يرسله الـ Client للـ Master.
    """

    # ما يُنفَّذ
    command: str  # الأمر المباشر (مثل "python script.py")
    args: list[str] = field(default_factory=list)  # arguments إضافية

    # أو container
    docker_image: Optional[str] = None  # مثل "python:3.11"
    docker_command: Optional[str] = None  # override الأمر داخل الـ container

    # الموارد المطلوبة
    resources: ResourceSpec = field(default_factory=ResourceSpec)

    # إعدادات التنفيذ
    name: Optional[str] = None  # اسم وصفي
    timeout_seconds: int = 3600  # ساعة افتراضياً
    max_retries: int = 3
    priority: JobPriority = JobPriority.NORMAL

    # تقييدات التوزيع
    required_tags: list[str] = field(default_factory=list)  # لازم الـ worker يكون عنده هاي tags
    preferred_worker: Optional[str] = None  # worker محدد (اختياري)

    # Environment
    environment: dict[str, str] = field(default_factory=dict)
    working_dir: Optional[str] = None

    # Input/Output
    input_files: dict[str, str] = field(default_factory=dict)  # {local_path: remote_path}
    output_patterns: list[str] = field(default_factory=list)  # glob patterns للنتائج

    # Metadata
    labels: dict[str, str] = field(default_factory=dict)
    user_id: Optional[str] = None

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "command": self.command,
            "args": self.args,
            "docker_image": self.docker_image,
            "docker_command": self.docker_command,
            "resources": self.resources.to_dict(),
            "name": self.name,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "priority": self.priority.value,
            "required_tags": self.required_tags,
            "preferred_worker": self.preferred_worker,
            "environment": self.environment,
            "working_dir": self.working_dir,
            "input_files": self.input_files,
            "output_patterns": self.output_patterns,
            "labels": self.labels,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> JobSubmission:
        """إنشاء من dictionary."""
        return cls(
            command=data["command"],
            args=data.get("args", []),
            docker_image=data.get("docker_image"),
            docker_command=data.get("docker_command"),
            resources=ResourceSpec.from_dict(data.get("resources", {})),
            name=data.get("name"),
            timeout_seconds=data.get("timeout_seconds", 3600),
            max_retries=data.get("max_retries", 3),
            priority=JobPriority(data.get("priority", 50)),
            required_tags=data.get("required_tags", []),
            preferred_worker=data.get("preferred_worker"),
            environment=data.get("environment", {}),
            working_dir=data.get("working_dir"),
            input_files=data.get("input_files", {}),
            output_patterns=data.get("output_patterns", []),
            labels=data.get("labels", {}),
            user_id=data.get("user_id"),
        )


@dataclass
class JobResult:
    """
    نتيجة تنفيذ Job.

    يُرسلها Worker للـ Master عند انتهاء الـ Job.
    """

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    output_files: dict[str, str] = field(default_factory=dict)  # {pattern: storage_path}
    execution_time_seconds: float = 0.0
    peak_memory_mb: int = 0
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        """هل نجح التنفيذ؟"""
        return self.exit_code == 0

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "output_files": self.output_files,
            "execution_time_seconds": self.execution_time_seconds,
            "peak_memory_mb": self.peak_memory_mb,
            "error_message": self.error_message,
            "success": self.success,
        }


@dataclass
class Job:
    """
    Job كامل مع كل المعلومات (يحفظه Master).

    هذا هو الـ state الكامل للـ job في النظام.
    """

    job_id: str
    submission: JobSubmission
    status: JobStatus = JobStatus.PENDING
    result: Optional[JobResult] = None

    # تتبع التنفيذ
    assigned_worker: Optional[str] = None  # worker_id
    retry_count: int = 0
    lease_id: Optional[str] = None  # لمنع race conditions

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # History
    execution_history: list[dict] = field(default_factory=list)

    @classmethod
    def from_submission(cls, submission: JobSubmission) -> Job:
        """إنشاء Job من طلب submission."""
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        name = submission.name or job_id

        return cls(
            job_id=job_id,
            submission=JobSubmission(
                command=submission.command,
                args=submission.args,
                docker_image=submission.docker_image,
                docker_command=submission.docker_command,
                resources=submission.resources,
                name=name,
                timeout_seconds=submission.timeout_seconds,
                max_retries=submission.max_retries,
                priority=submission.priority,
                required_tags=submission.required_tags,
                preferred_worker=submission.preferred_worker,
                environment=submission.environment,
                working_dir=submission.working_dir,
                input_files=submission.input_files,
                output_patterns=submission.output_patterns,
                labels=submission.labels,
                user_id=submission.user_id,
            ),
        )

    @property
    def name(self) -> str:
        """اسم الـ Job."""
        return self.submission.name or self.job_id

    @property
    def is_terminal(self) -> bool:
        """هل الـ Job في حالة نهائية؟"""
        return self.status in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMEOUT,
        )

    @property
    def can_retry(self) -> bool:
        """هل ممكن إعادة المحاولة؟"""
        return self.status == JobStatus.FAILED and self.retry_count < self.submission.max_retries

    @property
    def wait_time_seconds(self) -> float:
        """كم انتظر في الطابور؟"""
        if self.started_at:
            return (self.started_at - self.created_at).total_seconds()
        return (datetime.utcnow() - self.created_at).total_seconds()

    @property
    def execution_time_seconds(self) -> Optional[float]:
        """وقت التنفيذ الفعلي."""
        if self.result:
            return self.result.execution_time_seconds
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def schedule(self, worker_id: str, lease_id: str) -> None:
        """تعيين Job لـ Worker."""
        self.status = JobStatus.SCHEDULED
        self.assigned_worker = worker_id
        self.lease_id = lease_id
        self.scheduled_at = datetime.utcnow()

    def start(self) -> None:
        """بدء التنفيذ."""
        self.status = JobStatus.RUNNING
        self.started_at = datetime.utcnow()

    def complete(self, result: JobResult) -> None:
        """إنهاء بنجاح أو فشل."""
        self.completed_at = datetime.utcnow()
        self.result = result

        if result.success:
            self.status = JobStatus.COMPLETED
        else:
            self.status = JobStatus.FAILED

        # تسجيل في التاريخ
        self.execution_history.append(
            {
                "worker_id": self.assigned_worker,
                "attempt": self.retry_count + 1,
                "status": self.status.value,
                "exit_code": result.exit_code,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "completed_at": self.completed_at.isoformat(),
                "execution_time": result.execution_time_seconds,
            }
        )

    def timeout(self) -> None:
        """تجاوز الوقت المحدد."""
        self.status = JobStatus.TIMEOUT
        self.completed_at = datetime.utcnow()

    def cancel(self) -> None:
        """إلغاء الـ Job."""
        self.status = JobStatus.CANCELLED
        self.completed_at = datetime.utcnow()

    def prepare_retry(self) -> None:
        """تجهيز لإعادة المحاولة."""
        self.retry_count += 1
        self.status = JobStatus.PENDING
        self.assigned_worker = None
        self.lease_id = None
        self.scheduled_at = None
        self.started_at = None
        self.completed_at = None
        self.result = None

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status.value,
            "submission": self.submission.to_dict(),
            "result": self.result.to_dict() if self.result else None,
            "assigned_worker": self.assigned_worker,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "wait_time_seconds": self.wait_time_seconds,
            "execution_time_seconds": self.execution_time_seconds,
            "is_terminal": self.is_terminal,
            "can_retry": self.can_retry,
            "execution_history": self.execution_history,
        }
