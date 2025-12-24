"""
Storage Base - القاعدة الأساسية للتخزين
======================================

Base Checkpoint Storage Interface
---------------------------------

This module defines the abstract interface for checkpoint storage backends.

يحدد هذا الملف الواجهة الأساسية لخلفيات تخزين نقاط الحفظ.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from distributed_cluster.checkpointing.checkpoint import CheckpointMetadata

logger = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """
    إعدادات التخزين
    Storage configuration
    """
    # Connection
    connection_timeout_seconds: int = 30
    read_timeout_seconds: int = 60
    write_timeout_seconds: int = 120

    # Retry
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    retry_backoff: float = 2.0

    # Batching
    batch_size: int = 100

    # Custom settings
    extra: dict[str, Any] = field(default_factory=dict)


class StorageError(Exception):
    """خطأ في التخزين / Storage error"""
    pass


class ConnectionError(StorageError):
    """خطأ في الاتصال / Connection error"""
    pass


class WriteError(StorageError):
    """خطأ في الكتابة / Write error"""
    pass


class ReadError(StorageError):
    """خطأ في القراءة / Read error"""
    pass


class CheckpointStorage(ABC):
    """
    واجهة تخزين نقاط الحفظ الأساسية
    Base Checkpoint Storage Interface

    جميع خلفيات التخزين يجب أن ترث من هذه الفئة.
    All storage backends must inherit from this class.
    """

    def __init__(self, config: Optional[StorageConfig] = None):
        """
        تهيئة التخزين

        Args:
            config: إعدادات التخزين
        """
        self.config = config or StorageConfig()
        self._connected = False

    # =========================================================================
    # Connection / الاتصال
    # =========================================================================

    @abstractmethod
    async def connect(self) -> None:
        """
        الاتصال بالتخزين
        Connect to storage

        Raises:
            ConnectionError: إذا فشل الاتصال
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        قطع الاتصال بالتخزين
        Disconnect from storage
        """
        pass

    @property
    def is_connected(self) -> bool:
        """هل التخزين متصل؟"""
        return self._connected

    # =========================================================================
    # Checkpoint Operations / عمليات نقاط الحفظ
    # =========================================================================

    @abstractmethod
    async def save_checkpoint(
        self,
        checkpoint_id: str,
        data: bytes,
        metadata: CheckpointMetadata,
    ) -> bool:
        """
        حفظ نقطة حفظ
        Save checkpoint

        Args:
            checkpoint_id: معرف نقطة الحفظ
            data: البيانات المتسلسلة
            metadata: البيانات الوصفية

        Returns:
            True إذا تم الحفظ بنجاح

        Raises:
            WriteError: إذا فشلت الكتابة
        """
        pass

    @abstractmethod
    async def load_checkpoint(self, checkpoint_id: str) -> Optional[bytes]:
        """
        تحميل نقطة حفظ
        Load checkpoint

        Args:
            checkpoint_id: معرف نقطة الحفظ

        Returns:
            البيانات المتسلسلة أو None

        Raises:
            ReadError: إذا فشلت القراءة
        """
        pass

    @abstractmethod
    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        حذف نقطة حفظ
        Delete checkpoint

        Args:
            checkpoint_id: معرف نقطة الحفظ

        Returns:
            True إذا تم الحذف بنجاح
        """
        pass

    @abstractmethod
    async def get_metadata(
        self,
        checkpoint_id: str,
    ) -> Optional[CheckpointMetadata]:
        """
        الحصول على البيانات الوصفية
        Get checkpoint metadata

        Args:
            checkpoint_id: معرف نقطة الحفظ

        Returns:
            البيانات الوصفية أو None
        """
        pass

    @abstractmethod
    async def list_checkpoints(
        self,
        job_id: str,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[CheckpointMetadata]:
        """
        قائمة نقاط الحفظ
        List checkpoints

        Args:
            job_id: معرف المهمة
            task_id: معرف المهمة الفرعية (اختياري)
            limit: الحد الأقصى للنتائج

        Returns:
            قائمة البيانات الوصفية
        """
        pass

    @abstractmethod
    async def checkpoint_exists(self, checkpoint_id: str) -> bool:
        """
        التحقق من وجود نقطة حفظ
        Check if checkpoint exists

        Args:
            checkpoint_id: معرف نقطة الحفظ

        Returns:
            True إذا كانت موجودة
        """
        pass

    # =========================================================================
    # Health & Status / الصحة والحالة
    # =========================================================================

    async def health_check(self) -> bool:
        """
        فحص صحة التخزين
        Check storage health

        Returns:
            True إذا كان التخزين سليماً
        """
        return self._connected

    def get_status(self) -> dict[str, Any]:
        """
        الحصول على حالة التخزين
        Get storage status
        """
        return {
            "backend": self.__class__.__name__,
            "connected": self._connected,
        }

    # =========================================================================
    # Helper Methods / طرق مساعدة
    # =========================================================================

    def _get_checkpoint_path(self, checkpoint_id: str) -> str:
        """الحصول على مسار نقطة الحفظ"""
        return f"checkpoints/{checkpoint_id}"

    def _get_metadata_path(self, checkpoint_id: str) -> str:
        """الحصول على مسار البيانات الوصفية"""
        return f"checkpoints/{checkpoint_id}.meta"

    def _get_job_prefix(self, job_id: str) -> str:
        """الحصول على بادئة المهمة"""
        return f"jobs/{job_id}/"
