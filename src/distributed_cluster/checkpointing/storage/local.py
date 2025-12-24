"""
Local Storage - التخزين المحلي
==============================

Local Filesystem Checkpoint Storage
-----------------------------------

This module provides local filesystem storage for checkpoints.

يوفر هذا الملف تخزين نقاط الحفظ على نظام الملفات المحلي.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from distributed_cluster.checkpointing.checkpoint import CheckpointMetadata
from distributed_cluster.checkpointing.storage.base import (
    CheckpointStorage,
    ReadError,
    StorageConfig,
    WriteError,
)

logger = logging.getLogger(__name__)


class LocalStorage(CheckpointStorage):
    """
    تخزين نقاط الحفظ على نظام الملفات المحلي
    Local filesystem checkpoint storage

    يخزن نقاط الحفظ في مجلد محلي مع
    فهرسة بسيطة للبحث السريع.

    Stores checkpoints in a local directory with
    simple indexing for fast lookups.
    """

    def __init__(
        self,
        base_path: str | Path,
        config: Optional[StorageConfig] = None,
    ):
        """
        تهيئة التخزين المحلي

        Args:
            base_path: المسار الأساسي للتخزين
            config: إعدادات التخزين
        """
        super().__init__(config)

        self.base_path = Path(base_path)
        self._checkpoints_dir = self.base_path / "checkpoints"
        self._metadata_dir = self.base_path / "metadata"
        self._index_dir = self.base_path / "index"

        # Metadata cache
        self._metadata_cache: dict[str, CheckpointMetadata] = {}

    # =========================================================================
    # Connection / الاتصال
    # =========================================================================

    async def connect(self) -> None:
        """الاتصال (إنشاء المجلدات)"""
        try:
            # Create directories
            self._checkpoints_dir.mkdir(parents=True, exist_ok=True)
            self._metadata_dir.mkdir(parents=True, exist_ok=True)
            self._index_dir.mkdir(parents=True, exist_ok=True)

            self._connected = True
            logger.info(f"LocalStorage connected at {self.base_path}")

        except Exception as e:
            logger.error(f"Failed to connect LocalStorage: {e}")
            raise

    async def disconnect(self) -> None:
        """قطع الاتصال"""
        self._metadata_cache.clear()
        self._connected = False
        logger.info("LocalStorage disconnected")

    # =========================================================================
    # Checkpoint Operations / عمليات نقاط الحفظ
    # =========================================================================

    async def save_checkpoint(
        self,
        checkpoint_id: str,
        data: bytes,
        metadata: CheckpointMetadata,
    ) -> bool:
        """حفظ نقطة حفظ"""
        try:
            # Save data
            data_path = self._get_data_path(checkpoint_id)
            await self._write_file(data_path, data)

            # Save metadata
            metadata_path = self._get_meta_path(checkpoint_id)
            metadata_json = json.dumps(metadata.to_dict(), indent=2)
            await self._write_file(metadata_path, metadata_json.encode())

            # Update index
            await self._update_index(metadata)

            # Cache metadata
            self._metadata_cache[checkpoint_id] = metadata

            logger.debug(f"Saved checkpoint {checkpoint_id} to {data_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save checkpoint {checkpoint_id}: {e}")
            raise WriteError(f"Failed to save checkpoint: {e}")

    async def load_checkpoint(self, checkpoint_id: str) -> Optional[bytes]:
        """تحميل نقطة حفظ"""
        try:
            data_path = self._get_data_path(checkpoint_id)

            if not data_path.exists():
                return None

            return await self._read_file(data_path)

        except Exception as e:
            logger.error(f"Failed to load checkpoint {checkpoint_id}: {e}")
            raise ReadError(f"Failed to load checkpoint: {e}")

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """حذف نقطة حفظ"""
        try:
            # Get metadata for index cleanup
            metadata = await self.get_metadata(checkpoint_id)

            # Delete data file
            data_path = self._get_data_path(checkpoint_id)
            if data_path.exists():
                data_path.unlink()

            # Delete metadata file
            metadata_path = self._get_meta_path(checkpoint_id)
            if metadata_path.exists():
                metadata_path.unlink()

            # Update index
            if metadata:
                await self._remove_from_index(metadata)

            # Remove from cache
            self._metadata_cache.pop(checkpoint_id, None)

            logger.debug(f"Deleted checkpoint {checkpoint_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete checkpoint {checkpoint_id}: {e}")
            return False

    async def get_metadata(
        self,
        checkpoint_id: str,
    ) -> Optional[CheckpointMetadata]:
        """الحصول على البيانات الوصفية"""
        # Check cache
        if checkpoint_id in self._metadata_cache:
            return self._metadata_cache[checkpoint_id]

        try:
            metadata_path = self._get_meta_path(checkpoint_id)

            if not metadata_path.exists():
                return None

            data = await self._read_file(metadata_path)
            metadata_dict = json.loads(data.decode())
            metadata = CheckpointMetadata.from_dict(metadata_dict)

            # Cache it
            self._metadata_cache[checkpoint_id] = metadata

            return metadata

        except Exception as e:
            logger.error(f"Failed to get metadata for {checkpoint_id}: {e}")
            return None

    async def list_checkpoints(
        self,
        job_id: str,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[CheckpointMetadata]:
        """قائمة نقاط الحفظ"""
        try:
            index_path = self._get_job_index_path(job_id)

            if not index_path.exists():
                return []

            data = await self._read_file(index_path)
            index = json.loads(data.decode())

            checkpoints: list[CheckpointMetadata] = []

            for checkpoint_id in index.get("checkpoints", []):
                metadata = await self.get_metadata(checkpoint_id)
                if metadata:
                    # Filter by task_id if specified
                    if task_id and metadata.task_id != task_id:
                        continue

                    checkpoints.append(metadata)

                    if len(checkpoints) >= limit:
                        break

            return checkpoints

        except Exception as e:
            logger.error(f"Failed to list checkpoints for job {job_id}: {e}")
            return []

    async def checkpoint_exists(self, checkpoint_id: str) -> bool:
        """التحقق من وجود نقطة حفظ"""
        data_path = self._get_data_path(checkpoint_id)
        return data_path.exists()

    # =========================================================================
    # Index Management / إدارة الفهرس
    # =========================================================================

    async def _update_index(self, metadata: CheckpointMetadata) -> None:
        """تحديث فهرس المهمة"""
        index_path = self._get_job_index_path(metadata.job_id)

        if index_path.exists():
            data = await self._read_file(index_path)
            index = json.loads(data.decode())
        else:
            index = {"job_id": metadata.job_id, "checkpoints": []}

        if metadata.checkpoint_id not in index["checkpoints"]:
            index["checkpoints"].append(metadata.checkpoint_id)

        await self._write_file(index_path, json.dumps(index, indent=2).encode())

    async def _remove_from_index(self, metadata: CheckpointMetadata) -> None:
        """إزالة من فهرس المهمة"""
        index_path = self._get_job_index_path(metadata.job_id)

        if not index_path.exists():
            return

        data = await self._read_file(index_path)
        index = json.loads(data.decode())

        if metadata.checkpoint_id in index.get("checkpoints", []):
            index["checkpoints"].remove(metadata.checkpoint_id)

        await self._write_file(index_path, json.dumps(index, indent=2).encode())

    # =========================================================================
    # Path Helpers / مساعدات المسار
    # =========================================================================

    def _get_data_path(self, checkpoint_id: str) -> Path:
        """الحصول على مسار البيانات"""
        return self._checkpoints_dir / f"{checkpoint_id}.ckpt"

    def _get_meta_path(self, checkpoint_id: str) -> Path:
        """الحصول على مسار البيانات الوصفية"""
        return self._metadata_dir / f"{checkpoint_id}.json"

    def _get_job_index_path(self, job_id: str) -> Path:
        """الحصول على مسار فهرس المهمة"""
        return self._index_dir / f"{job_id}.json"

    # =========================================================================
    # File I/O / عمليات الملفات
    # =========================================================================

    async def _write_file(self, path: Path, data: bytes) -> None:
        """كتابة ملف بشكل غير متزامن"""
        loop = asyncio.get_event_loop()

        def _write():
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)

        await loop.run_in_executor(None, _write)

    async def _read_file(self, path: Path) -> bytes:
        """قراءة ملف بشكل غير متزامن"""
        loop = asyncio.get_event_loop()

        def _read():
            with open(path, "rb") as f:
                return f.read()

        return await loop.run_in_executor(None, _read)

    # =========================================================================
    # Status / الحالة
    # =========================================================================

    def get_status(self) -> dict:
        """الحصول على حالة التخزين"""
        status = super().get_status()

        # Count files
        checkpoint_count = len(list(self._checkpoints_dir.glob("*.ckpt")))

        # Calculate total size
        total_size = sum(
            f.stat().st_size
            for f in self._checkpoints_dir.glob("*.ckpt")
            if f.exists()
        )

        status.update({
            "base_path": str(self.base_path),
            "checkpoint_count": checkpoint_count,
            "total_size_bytes": total_size,
            "cache_size": len(self._metadata_cache),
        })

        return status

    async def cleanup(self, before_days: int = 7) -> int:
        """
        تنظيف نقاط الحفظ القديمة
        Cleanup old checkpoints
        """
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(days=before_days)
        cleaned = 0

        for meta_file in self._metadata_dir.glob("*.json"):
            try:
                data = await self._read_file(meta_file)
                metadata = CheckpointMetadata.from_dict(json.loads(data.decode()))

                if metadata.created_at < cutoff:
                    if await self.delete_checkpoint(metadata.checkpoint_id):
                        cleaned += 1

            except Exception as e:
                logger.error(f"Error cleaning up {meta_file}: {e}")

        logger.info(f"Cleaned up {cleaned} old checkpoints")
        return cleaned
