"""
Checkpoint Core - جوهر نظام نقاط الحفظ
======================================

Core Checkpoint Classes
-----------------------

This module defines the core checkpoint data structures
and the main checkpoint manager.

يحدد هذا الملف هياكل بيانات نقاط الحفظ الأساسية
ومدير نقاط الحفظ الرئيسي.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import pickle
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar
from uuid import uuid4

if TYPE_CHECKING:
    from distributed_cluster.checkpointing.storage.base import CheckpointStorage

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CheckpointState(str, Enum):
    """حالة نقطة الحفظ / Checkpoint state"""
    PENDING = "pending"  # قيد الإنشاء
    SAVING = "saving"  # يتم الحفظ
    SAVED = "saved"  # تم الحفظ
    CORRUPTED = "corrupted"  # تالفة
    EXPIRED = "expired"  # منتهية الصلاحية
    DELETED = "deleted"  # محذوفة


@dataclass
class CheckpointMetadata:
    """
    بيانات وصفية لنقطة الحفظ
    Checkpoint metadata
    """
    checkpoint_id: str
    job_id: str
    task_id: Optional[str] = None
    worker_id: Optional[str] = None

    # Versioning
    version: int = 1
    sequence_number: int = 0

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    # Size & Integrity
    size_bytes: int = 0
    checksum: str = ""
    compressed: bool = False

    # Custom metadata
    tags: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس"""
        return {
            "checkpoint_id": self.checkpoint_id,
            "job_id": self.job_id,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "version": self.version,
            "sequence_number": self.sequence_number,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "compressed": self.compressed,
            "tags": self.tags,
            "labels": self.labels,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointMetadata:
        """إنشاء من قاموس"""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            job_id=data["job_id"],
            task_id=data.get("task_id"),
            worker_id=data.get("worker_id"),
            version=data.get("version", 1),
            sequence_number=data.get("sequence_number", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            size_bytes=data.get("size_bytes", 0),
            checksum=data.get("checksum", ""),
            compressed=data.get("compressed", False),
            tags=data.get("tags", {}),
            labels=data.get("labels", {}),
        )


@dataclass
class CheckpointData(Generic[T]):
    """
    بيانات نقطة الحفظ
    Checkpoint data container
    """
    # Core state
    state: T

    # Progress tracking
    progress: float = 0.0  # 0.0 to 1.0
    completed_items: int = 0
    total_items: int = 0

    # Execution context
    iteration: int = 0
    step: str = ""
    substep: str = ""

    # Custom data
    extra: dict[str, Any] = field(default_factory=dict)

    def to_bytes(self, compress: bool = True) -> bytes:
        """تحويل إلى bytes"""
        data = pickle.dumps(self)
        if compress:
            data = zlib.compress(data, level=6)
        return data

    @classmethod
    def from_bytes(cls, data: bytes, compressed: bool = True) -> CheckpointData:
        """إنشاء من bytes"""
        if compressed:
            data = zlib.decompress(data)
        # nosec B301 - Loading checkpoint data from internal system
        return pickle.loads(data)


@dataclass
class Checkpoint(Generic[T]):
    """
    نقطة حفظ كاملة
    Complete checkpoint
    """
    metadata: CheckpointMetadata
    data: CheckpointData[T]
    state: CheckpointState = CheckpointState.PENDING

    def is_valid(self) -> bool:
        """التحقق من صلاحية نقطة الحفظ"""
        if self.state in (CheckpointState.CORRUPTED, CheckpointState.DELETED):
            return False

        if self.metadata.expires_at and datetime.now(timezone.utc) > self.metadata.expires_at:
            self.state = CheckpointState.EXPIRED
            return False

        return True


class CheckpointManager:
    """
    مدير نقاط الحفظ
    Checkpoint Manager

    يدير إنشاء وتخزين واسترداد نقاط الحفظ.
    Manages checkpoint creation, storage, and retrieval.
    """

    def __init__(
        self,
        storage: CheckpointStorage,
        auto_cleanup: bool = True,
        cleanup_interval_seconds: int = 3600,
        max_checkpoints_per_job: int = 10,
        default_ttl_hours: int = 24,
        compress: bool = True,
    ):
        """
        تهيئة مدير نقاط الحفظ

        Args:
            storage: مخزن نقاط الحفظ
            auto_cleanup: تنظيف تلقائي
            cleanup_interval_seconds: فترة التنظيف
            max_checkpoints_per_job: أقصى عدد لكل مهمة
            default_ttl_hours: مدة الصلاحية بالساعات
            compress: ضغط البيانات
        """
        self.storage = storage
        self.auto_cleanup = auto_cleanup
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.max_checkpoints_per_job = max_checkpoints_per_job
        self.default_ttl_hours = default_ttl_hours
        self.compress = compress

        # Internal state
        self._checkpoints: dict[str, CheckpointMetadata] = {}
        self._job_checkpoints: dict[str, list[str]] = {}
        self._sequence_counters: dict[str, int] = {}

        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    # =========================================================================
    # Lifecycle / دورة الحياة
    # =========================================================================

    async def start(self) -> None:
        """بدء المدير"""
        await self.storage.connect()
        self._running = True

        if self.auto_cleanup:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("CheckpointManager started")

    async def stop(self) -> None:
        """إيقاف المدير"""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        await self.storage.disconnect()
        logger.info("CheckpointManager stopped")

    # =========================================================================
    # Checkpoint Operations / عمليات نقاط الحفظ
    # =========================================================================

    async def create_checkpoint(
        self,
        job_id: str,
        data: CheckpointData,
        task_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        ttl_hours: Optional[int] = None,
        tags: Optional[dict[str, str]] = None,
    ) -> str:
        """
        إنشاء نقطة حفظ جديدة
        Create new checkpoint

        Args:
            job_id: معرف المهمة
            data: بيانات نقطة الحفظ
            task_id: معرف المهمة الفرعية
            worker_id: معرف العامل
            ttl_hours: مدة الصلاحية
            tags: وسوم إضافية

        Returns:
            معرف نقطة الحفظ
        """
        checkpoint_id = str(uuid4())

        # Get next sequence number
        self._sequence_counters.setdefault(job_id, 0)
        self._sequence_counters[job_id] += 1
        sequence_number = self._sequence_counters[job_id]

        # Calculate expiration
        ttl = ttl_hours or self.default_ttl_hours
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)

        # Serialize data
        serialized = data.to_bytes(compress=self.compress)
        checksum = hashlib.sha256(serialized).hexdigest()

        # Create metadata
        metadata = CheckpointMetadata(
            checkpoint_id=checkpoint_id,
            job_id=job_id,
            task_id=task_id,
            worker_id=worker_id,
            sequence_number=sequence_number,
            expires_at=expires_at,
            size_bytes=len(serialized),
            checksum=checksum,
            compressed=self.compress,
            tags=tags or {},
        )

        # Save to storage
        await self.storage.save_checkpoint(checkpoint_id, serialized, metadata)

        # Update internal tracking
        self._checkpoints[checkpoint_id] = metadata
        self._job_checkpoints.setdefault(job_id, []).append(checkpoint_id)

        # Enforce max checkpoints per job
        await self._enforce_checkpoint_limit(job_id)

        logger.info(f"Created checkpoint {checkpoint_id} for job {job_id}")
        return checkpoint_id

    async def get_checkpoint(
        self,
        checkpoint_id: str,
        verify_checksum: bool = True,
    ) -> Optional[Checkpoint]:
        """
        استرداد نقطة حفظ
        Retrieve checkpoint

        Args:
            checkpoint_id: معرف نقطة الحفظ
            verify_checksum: التحقق من السلامة

        Returns:
            نقطة الحفظ أو None
        """
        # Get metadata
        metadata = await self.storage.get_metadata(checkpoint_id)
        if not metadata:
            return None

        # Check expiration
        if metadata.expires_at and datetime.now(timezone.utc) > metadata.expires_at:
            return Checkpoint(
                metadata=metadata,
                data=CheckpointData(state=None),
                state=CheckpointState.EXPIRED,
            )

        # Load data
        serialized = await self.storage.load_checkpoint(checkpoint_id)
        if not serialized:
            return None

        # Verify checksum
        if verify_checksum:
            actual_checksum = hashlib.sha256(serialized).hexdigest()
            if actual_checksum != metadata.checksum:
                logger.error(f"Checkpoint {checkpoint_id} checksum mismatch")
                return Checkpoint(
                    metadata=metadata,
                    data=CheckpointData(state=None),
                    state=CheckpointState.CORRUPTED,
                )

        # Deserialize
        try:
            data = CheckpointData.from_bytes(serialized, compressed=metadata.compressed)
        except Exception as e:
            logger.error(f"Failed to deserialize checkpoint {checkpoint_id}: {e}")
            return Checkpoint(
                metadata=metadata,
                data=CheckpointData(state=None),
                state=CheckpointState.CORRUPTED,
            )

        return Checkpoint(
            metadata=metadata,
            data=data,
            state=CheckpointState.SAVED,
        )

    async def get_latest_checkpoint(
        self,
        job_id: str,
        task_id: Optional[str] = None,
    ) -> Optional[Checkpoint]:
        """
        استرداد آخر نقطة حفظ لمهمة
        Get latest checkpoint for job

        Args:
            job_id: معرف المهمة
            task_id: معرف المهمة الفرعية (اختياري)

        Returns:
            آخر نقطة حفظ صالحة أو None
        """
        checkpoints = await self.list_checkpoints(job_id, task_id=task_id)

        if not checkpoints:
            return None

        # Sort by sequence number (descending)
        checkpoints.sort(key=lambda m: m.sequence_number, reverse=True)

        # Find first valid checkpoint
        for metadata in checkpoints:
            checkpoint = await self.get_checkpoint(metadata.checkpoint_id)
            if checkpoint and checkpoint.is_valid():
                return checkpoint

        return None

    async def list_checkpoints(
        self,
        job_id: str,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[CheckpointMetadata]:
        """
        قائمة نقاط الحفظ لمهمة
        List checkpoints for job
        """
        return await self.storage.list_checkpoints(
            job_id=job_id,
            task_id=task_id,
            limit=limit,
        )

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        حذف نقطة حفظ
        Delete checkpoint
        """
        metadata = self._checkpoints.pop(checkpoint_id, None)

        if metadata and metadata.job_id in self._job_checkpoints:
            if checkpoint_id in self._job_checkpoints[metadata.job_id]:
                self._job_checkpoints[metadata.job_id].remove(checkpoint_id)

        success = await self.storage.delete_checkpoint(checkpoint_id)

        if success:
            logger.info(f"Deleted checkpoint {checkpoint_id}")

        return success

    async def delete_job_checkpoints(self, job_id: str) -> int:
        """
        حذف جميع نقاط الحفظ لمهمة
        Delete all checkpoints for job
        """
        checkpoints = await self.list_checkpoints(job_id)
        deleted = 0

        for metadata in checkpoints:
            if await self.delete_checkpoint(metadata.checkpoint_id):
                deleted += 1

        # Clean up tracking
        self._job_checkpoints.pop(job_id, None)
        self._sequence_counters.pop(job_id, None)

        logger.info(f"Deleted {deleted} checkpoints for job {job_id}")
        return deleted

    # =========================================================================
    # Helper Methods / طرق مساعدة
    # =========================================================================

    async def _enforce_checkpoint_limit(self, job_id: str) -> None:
        """فرض حد نقاط الحفظ لكل مهمة"""
        checkpoint_ids = self._job_checkpoints.get(job_id, [])

        if len(checkpoint_ids) <= self.max_checkpoints_per_job:
            return

        # Get all checkpoints with metadata
        checkpoints = []
        for cid in checkpoint_ids:
            metadata = await self.storage.get_metadata(cid)
            if metadata:
                checkpoints.append(metadata)

        # Sort by sequence number (oldest first)
        checkpoints.sort(key=lambda m: m.sequence_number)

        # Delete oldest checkpoints
        to_delete = len(checkpoints) - self.max_checkpoints_per_job
        for i in range(to_delete):
            await self.delete_checkpoint(checkpoints[i].checkpoint_id)

    async def _cleanup_loop(self) -> None:
        """حلقة التنظيف التلقائي"""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    async def _cleanup_expired(self) -> int:
        """تنظيف نقاط الحفظ المنتهية"""
        expired_count = 0

        for checkpoint_id in list(self._checkpoints.keys()):
            metadata = self._checkpoints.get(checkpoint_id)
            if not metadata:
                continue

            if metadata.expires_at and datetime.now(timezone.utc) > metadata.expires_at:
                if await self.delete_checkpoint(checkpoint_id):
                    expired_count += 1

        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired checkpoints")

        return expired_count

    # =========================================================================
    # Status / الحالة
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """الحصول على حالة المدير"""
        return {
            "running": self._running,
            "total_checkpoints": len(self._checkpoints),
            "jobs_tracked": len(self._job_checkpoints),
            "storage": self.storage.get_status(),
            "config": {
                "auto_cleanup": self.auto_cleanup,
                "cleanup_interval_seconds": self.cleanup_interval_seconds,
                "max_checkpoints_per_job": self.max_checkpoints_per_job,
                "default_ttl_hours": self.default_ttl_hours,
                "compress": self.compress,
            },
        }
