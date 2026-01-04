"""
Federated Cluster - الكتلة المتحدة
===================================

Cluster Representation
----------------------

This module provides federated cluster data structures.

يوفر هذا الملف هياكل بيانات الكتلة المتحدة.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ClusterStatus(str, Enum):
    """حالة الكتلة / Cluster status"""
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNREACHABLE = "unreachable"
    DRAINING = "draining"
    OFFLINE = "offline"


class ClusterRole(str, Enum):
    """دور الكتلة / Cluster role"""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    OBSERVER = "observer"
    STANDBY = "standby"


@dataclass
class ClusterCapacity:
    """
    سعة الكتلة
    Cluster Capacity
    """
    # Workers
    total_workers: int = 0
    available_workers: int = 0
    busy_workers: int = 0

    # CPU
    total_cpu_cores: int = 0
    available_cpu_cores: float = 0.0
    cpu_utilization: float = 0.0

    # Memory
    total_memory_gb: float = 0.0
    available_memory_gb: float = 0.0
    memory_utilization: float = 0.0

    # GPU
    total_gpus: int = 0
    available_gpus: int = 0

    # Jobs
    pending_jobs: int = 0
    running_jobs: int = 0
    max_concurrent_jobs: int = 100

    # Queue
    queue_depth: int = 0
    estimated_wait_seconds: float = 0.0

    def get_load_score(self) -> float:
        """حساب درجة الحمل (0-1)"""
        scores = []

        if self.total_workers > 0:
            worker_load = self.busy_workers / self.total_workers
            scores.append(worker_load)

        if self.total_cpu_cores > 0:
            scores.append(self.cpu_utilization / 100)

        if self.total_memory_gb > 0:
            scores.append(self.memory_utilization / 100)

        if self.max_concurrent_jobs > 0:
            job_load = self.running_jobs / self.max_concurrent_jobs
            scores.append(job_load)

        return sum(scores) / len(scores) if scores else 0.0

    def can_accept_job(
        self,
        required_cpu: float = 1.0,
        required_memory_gb: float = 1.0,
        required_gpu: int = 0,
    ) -> bool:
        """هل يمكن قبول مهمة؟"""
        if self.available_workers <= 0:
            return False

        if self.available_cpu_cores < required_cpu:
            return False

        if self.available_memory_gb < required_memory_gb:
            return False

        if required_gpu > 0 and self.available_gpus < required_gpu:
            return False

        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "workers": {
                "total": self.total_workers,
                "available": self.available_workers,
                "busy": self.busy_workers,
            },
            "cpu": {
                "total_cores": self.total_cpu_cores,
                "available_cores": self.available_cpu_cores,
                "utilization": self.cpu_utilization,
            },
            "memory": {
                "total_gb": self.total_memory_gb,
                "available_gb": self.available_memory_gb,
                "utilization": self.memory_utilization,
            },
            "gpu": {
                "total": self.total_gpus,
                "available": self.available_gpus,
            },
            "jobs": {
                "pending": self.pending_jobs,
                "running": self.running_jobs,
                "max_concurrent": self.max_concurrent_jobs,
            },
            "queue": {
                "depth": self.queue_depth,
                "estimated_wait_seconds": self.estimated_wait_seconds,
            },
            "load_score": self.get_load_score(),
        }


@dataclass
class ClusterInfo:
    """
    معلومات الكتلة
    Cluster Information
    """
    cluster_id: str
    cluster_name: str
    endpoint: str  # API endpoint
    region: str = "default"
    zone: str = ""

    # Role and status
    role: ClusterRole = ClusterRole.SECONDARY
    status: ClusterStatus = ClusterStatus.UNKNOWN

    # Version
    version: str = "1.0.0"

    # Capacity
    capacity: ClusterCapacity = field(default_factory=ClusterCapacity)

    # Network
    latency_ms: float = 0.0
    bandwidth_mbps: float = 0.0

    # Timestamps
    joined_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None

    # Features
    supported_features: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_healthy(self) -> bool:
        """هل الكتلة صحية؟"""
        return self.status in (ClusterStatus.HEALTHY, ClusterStatus.DEGRADED)

    def is_available(self) -> bool:
        """هل الكتلة متاحة؟"""
        if not self.is_healthy():
            return False

        if self.status == ClusterStatus.DRAINING:
            return False

        return self.capacity.available_workers > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "cluster_name": self.cluster_name,
            "endpoint": self.endpoint,
            "region": self.region,
            "zone": self.zone,
            "role": self.role.value,
            "status": self.status.value,
            "version": self.version,
            "capacity": self.capacity.to_dict(),
            "latency_ms": self.latency_ms,
            "bandwidth_mbps": self.bandwidth_mbps,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "supported_features": self.supported_features,
            "tags": self.tags,
        }


class FederatedCluster:
    """
    كتلة متحدة
    Federated Cluster

    تمثل كتلة بعيدة في الاتحاد.
    Represents a remote cluster in the federation.
    """

    def __init__(
        self,
        info: ClusterInfo,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        تهيئة الكتلة المتحدة

        Args:
            info: معلومات الكتلة
            api_key: مفتاح API
            timeout: مهلة الاتصال
        """
        self.info = info
        self.api_key = api_key
        self.timeout = timeout

        self._client = None
        self._connected = False
        self._last_error: Optional[str] = None

        # Stats
        self._request_count = 0
        self._error_count = 0
        self._total_latency_ms = 0.0

    # =========================================================================
    # Connection
    # =========================================================================

    async def connect(self) -> bool:
        """الاتصال بالكتلة"""
        try:
            import httpx

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.info.endpoint,
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
            )

            # Test connection
            await self._ping()
            self._connected = True
            self.info.status = ClusterStatus.HEALTHY
            self.info.last_seen = datetime.utcnow()

            logger.info(f"Connected to cluster {self.info.cluster_id}")
            return True

        except Exception as e:
            self._last_error = str(e)
            self.info.status = ClusterStatus.UNREACHABLE
            logger.error(f"Failed to connect to cluster {self.info.cluster_id}: {e}")
            return False

    async def disconnect(self) -> None:
        """قطع الاتصال"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def _ping(self) -> float:
        """فحص الاتصال وقياس التأخير"""
        start = time.time()
        response = await self._client.get("/health")
        response.raise_for_status()
        latency = (time.time() - start) * 1000
        self.info.latency_ms = latency
        return latency

    # =========================================================================
    # Health
    # =========================================================================

    async def check_health(self) -> ClusterStatus:
        """فحص صحة الكتلة"""
        try:
            latency = await self._ping()

            if latency < 100:
                self.info.status = ClusterStatus.HEALTHY
            elif latency < 500:
                self.info.status = ClusterStatus.DEGRADED
            else:
                self.info.status = ClusterStatus.UNHEALTHY

            self.info.last_heartbeat = datetime.utcnow()
            return self.info.status

        except Exception as e:
            self._last_error = str(e)
            self.info.status = ClusterStatus.UNREACHABLE
            return self.info.status

    async def update_capacity(self) -> ClusterCapacity:
        """تحديث سعة الكتلة"""
        try:
            response = await self._client.get("/api/v1/capacity")
            response.raise_for_status()
            data = response.json()

            self.info.capacity = ClusterCapacity(
                total_workers=data.get("total_workers", 0),
                available_workers=data.get("available_workers", 0),
                busy_workers=data.get("busy_workers", 0),
                total_cpu_cores=data.get("total_cpu_cores", 0),
                available_cpu_cores=data.get("available_cpu_cores", 0),
                cpu_utilization=data.get("cpu_utilization", 0),
                total_memory_gb=data.get("total_memory_gb", 0),
                available_memory_gb=data.get("available_memory_gb", 0),
                memory_utilization=data.get("memory_utilization", 0),
                total_gpus=data.get("total_gpus", 0),
                available_gpus=data.get("available_gpus", 0),
                pending_jobs=data.get("pending_jobs", 0),
                running_jobs=data.get("running_jobs", 0),
                queue_depth=data.get("queue_depth", 0),
            )

            return self.info.capacity

        except Exception as e:
            logger.warning(f"Failed to update capacity for {self.info.cluster_id}: {e}")
            return self.info.capacity

    # =========================================================================
    # Job Operations
    # =========================================================================

    async def submit_job(
        self,
        job_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        إرسال مهمة للكتلة

        Args:
            job_data: بيانات المهمة

        Returns:
            نتيجة الإرسال
        """
        start = time.time()
        self._request_count += 1

        try:
            response = await self._client.post(
                "/api/v1/jobs",
                json=job_data,
            )
            response.raise_for_status()

            latency = (time.time() - start) * 1000
            self._total_latency_ms += latency

            return response.json()

        except Exception:
            self._error_count += 1
            raise

    async def get_job_status(
        self,
        job_id: str,
    ) -> dict[str, Any]:
        """الحصول على حالة مهمة"""
        response = await self._client.get(f"/api/v1/jobs/{job_id}")
        response.raise_for_status()
        return response.json()

    async def cancel_job(
        self,
        job_id: str,
    ) -> bool:
        """إلغاء مهمة"""
        try:
            response = await self._client.delete(f"/api/v1/jobs/{job_id}")
            response.raise_for_status()
            return True
        except Exception:
            return False

    async def get_job_result(
        self,
        job_id: str,
    ) -> dict[str, Any]:
        """الحصول على نتيجة مهمة"""
        response = await self._client.get(f"/api/v1/jobs/{job_id}/result")
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # State Sync
    # =========================================================================

    async def get_state(self) -> dict[str, Any]:
        """الحصول على حالة الكتلة"""
        response = await self._client.get("/api/v1/state")
        response.raise_for_status()
        return response.json()

    async def push_state(
        self,
        state: dict[str, Any],
    ) -> bool:
        """دفع الحالة للكتلة"""
        try:
            response = await self._client.post(
                "/api/v1/state/sync",
                json=state,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to push state to {self.info.cluster_id}: {e}")
            return False

    # =========================================================================
    # Stats
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """الحصول على الإحصائيات"""
        avg_latency = (
            self._total_latency_ms / self._request_count
            if self._request_count > 0
            else 0
        )

        return {
            "cluster_id": self.info.cluster_id,
            "connected": self._connected,
            "status": self.info.status.value,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": (
                self._error_count / self._request_count
                if self._request_count > 0
                else 0
            ),
            "avg_latency_ms": avg_latency,
            "last_error": self._last_error,
        }
