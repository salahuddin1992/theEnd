"""
Worker Models - نماذج الـ Worker
==================================

تعريفات Worker Agent والحالات المختلفة.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from distributed_cluster.models.resources import ResourceSpec, ResourceUsage


class WorkerStatus(str, Enum):
    """حالات الـ Worker."""

    INITIALIZING = "initializing"  # يبدأ ويسجل نفسه
    READY = "ready"  # جاهز لاستلام jobs
    BUSY = "busy"  # يشتغل على jobs
    DRAINING = "draining"  # لا يستلم jobs جديدة، ينتظر انتهاء الحالية
    OFFLINE = "offline"  # غير متصل
    ERROR = "error"  # في مشكلة


@dataclass
class WorkerRegistration:
    """
    بيانات تسجيل Worker جديد مع Master.

    يُرسل مرة واحدة عند بدء الـ Worker.
    """

    hostname: str
    ip_address: str
    port: int
    total_resources: ResourceSpec
    tags: list[str] = field(default_factory=list)  # مثل ["gpu", "high-memory"]
    labels: dict[str, str] = field(default_factory=dict)  # metadata إضافية
    platform: str = "linux"  # linux, windows, darwin
    python_version: str = ""
    docker_available: bool = False
    gpu_driver_version: Optional[str] = None

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "port": self.port,
            "total_resources": self.total_resources.to_dict(),
            "tags": self.tags,
            "labels": self.labels,
            "platform": self.platform,
            "python_version": self.python_version,
            "docker_available": self.docker_available,
            "gpu_driver_version": self.gpu_driver_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkerRegistration:
        """إنشاء من dictionary."""
        return cls(
            hostname=data["hostname"],
            ip_address=data["ip_address"],
            port=data["port"],
            total_resources=ResourceSpec.from_dict(data["total_resources"]),
            tags=data.get("tags", []),
            labels=data.get("labels", {}),
            platform=data.get("platform", "linux"),
            python_version=data.get("python_version", ""),
            docker_available=data.get("docker_available", False),
            gpu_driver_version=data.get("gpu_driver_version"),
        )


@dataclass
class WorkerInfo:
    """
    معلومات كاملة عن Worker (يحفظها Master).

    هذا هو الـ "state" الكامل للـ Worker في الـ cluster.
    """

    worker_id: str
    hostname: str
    ip_address: str
    port: int
    status: WorkerStatus
    total_resources: ResourceSpec
    available_resources: ResourceSpec  # ما تبقى بعد تخصيص jobs
    current_usage: Optional[ResourceUsage] = None
    tags: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    platform: str = "linux"
    docker_available: bool = False
    gpu_driver_version: Optional[str] = None

    # Timestamps
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: Optional[datetime] = None

    # Job tracking
    active_jobs: list[str] = field(default_factory=list)  # job IDs
    completed_jobs_count: int = 0
    failed_jobs_count: int = 0

    @classmethod
    def from_registration(cls, registration: WorkerRegistration) -> WorkerInfo:
        """إنشاء WorkerInfo من بيانات التسجيل."""
        return cls(
            worker_id=f"worker-{uuid.uuid4().hex[:12]}",
            hostname=registration.hostname,
            ip_address=registration.ip_address,
            port=registration.port,
            status=WorkerStatus.READY,
            total_resources=registration.total_resources,
            available_resources=registration.total_resources,  # كلها متاحة في البداية
            tags=registration.tags,
            labels=registration.labels,
            platform=registration.platform,
            docker_available=registration.docker_available,
            gpu_driver_version=registration.gpu_driver_version,
        )

    @property
    def address(self) -> str:
        """عنوان الـ Worker الكامل."""
        return f"{self.ip_address}:{self.port}"

    @property
    def is_healthy(self) -> bool:
        """هل الـ Worker في حالة صحية؟"""
        if self.status in (WorkerStatus.OFFLINE, WorkerStatus.ERROR):
            return False
        if self.last_heartbeat is None:
            return False
        # تعتبر غير صحي إذا مر أكثر من 30 ثانية بدون heartbeat
        delta = datetime.now(timezone.utc) - self.last_heartbeat
        return delta.total_seconds() < 30

    @property
    def can_accept_jobs(self) -> bool:
        """هل يقدر يستلم jobs جديدة؟"""
        return self.status in (WorkerStatus.READY, WorkerStatus.BUSY) and self.is_healthy

    def allocate_resources(self, required: ResourceSpec) -> bool:
        """
        تخصيص موارد لـ job.

        Returns:
            True إذا نجح التخصيص، False إذا الموارد غير كافية.
        """
        if not required.fits_in(self.available_resources):
            return False

        self.available_resources = self.available_resources.subtract(required)
        return True

    def release_resources(self, released: ResourceSpec) -> None:
        """تحرير موارد بعد انتهاء job."""
        self.available_resources = self.available_resources.add(released)

        # لا نتجاوز الموارد الإجمالية
        self.available_resources.cpu_cores = min(self.available_resources.cpu_cores, self.total_resources.cpu_cores)
        self.available_resources.memory_mb = min(self.available_resources.memory_mb, self.total_resources.memory_mb)
        self.available_resources.gpu_count = min(self.available_resources.gpu_count, self.total_resources.gpu_count)

    def update_heartbeat(self, usage: ResourceUsage) -> None:
        """تحديث معلومات من heartbeat."""
        self.last_heartbeat = datetime.now(timezone.utc)
        self.current_usage = usage

        # تحديث الحالة بناءً على الاستخدام
        if usage.is_overloaded:
            self.status = WorkerStatus.BUSY
        elif self.active_jobs:
            self.status = WorkerStatus.BUSY
        else:
            self.status = WorkerStatus.READY

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "worker_id": self.worker_id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "port": self.port,
            "address": self.address,
            "status": self.status.value,
            "total_resources": self.total_resources.to_dict(),
            "available_resources": self.available_resources.to_dict(),
            "current_usage": self.current_usage.to_dict() if self.current_usage else None,
            "tags": self.tags,
            "labels": self.labels,
            "platform": self.platform,
            "docker_available": self.docker_available,
            "gpu_driver_version": self.gpu_driver_version,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "active_jobs": self.active_jobs,
            "completed_jobs_count": self.completed_jobs_count,
            "failed_jobs_count": self.failed_jobs_count,
            "is_healthy": self.is_healthy,
            "can_accept_jobs": self.can_accept_jobs,
        }
