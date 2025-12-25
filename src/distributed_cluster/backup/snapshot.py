"""
Snapshot - لقطة النسخ الاحتياطي
================================

Snapshot Management
-------------------

This module provides snapshot data structures and management.

يوفر هذا الملف هياكل بيانات وإدارة اللقطات.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class SnapshotType(str, Enum):
    """نوع اللقطة / Snapshot type"""
    FULL = "full"                    # نسخة كاملة
    INCREMENTAL = "incremental"      # نسخة تزايدية
    DIFFERENTIAL = "differential"    # نسخة تفاضلية
    CONFIG_ONLY = "config_only"      # الإعدادات فقط
    STATE_ONLY = "state_only"        # الحالة فقط


class CompressionType(str, Enum):
    """نوع الضغط / Compression type"""
    NONE = "none"
    GZIP = "gzip"
    LZ4 = "lz4"
    ZSTD = "zstd"


class EncryptionType(str, Enum):
    """نوع التشفير / Encryption type"""
    NONE = "none"
    AES_256_GCM = "aes-256-gcm"
    CHACHA20_POLY1305 = "chacha20-poly1305"


@dataclass
class SnapshotMetadata:
    """
    بيانات وصفية للقطة
    Snapshot metadata
    """
    snapshot_id: str
    snapshot_type: SnapshotType
    created_at: datetime
    cluster_id: str
    cluster_name: str
    version: str = "1.0"

    # Size info
    size_bytes: int = 0
    compressed_size_bytes: int = 0

    # Checksums
    checksum_sha256: str = ""
    checksum_md5: str = ""

    # Compression/Encryption
    compression: CompressionType = CompressionType.GZIP
    encryption: EncryptionType = EncryptionType.NONE

    # Parent for incremental
    parent_snapshot_id: Optional[str] = None

    # Contents
    includes_config: bool = True
    includes_state: bool = True
    includes_jobs: bool = True
    includes_workers: bool = True
    includes_cache: bool = False

    # Extra metadata
    description: str = ""
    tags: list[str] = field(default_factory=list)
    custom_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_type": self.snapshot_type.value,
            "created_at": self.created_at.isoformat(),
            "cluster_id": self.cluster_id,
            "cluster_name": self.cluster_name,
            "version": self.version,
            "size_bytes": self.size_bytes,
            "compressed_size_bytes": self.compressed_size_bytes,
            "checksum_sha256": self.checksum_sha256,
            "checksum_md5": self.checksum_md5,
            "compression": self.compression.value,
            "encryption": self.encryption.value,
            "parent_snapshot_id": self.parent_snapshot_id,
            "includes_config": self.includes_config,
            "includes_state": self.includes_state,
            "includes_jobs": self.includes_jobs,
            "includes_workers": self.includes_workers,
            "includes_cache": self.includes_cache,
            "description": self.description,
            "tags": self.tags,
            "custom_metadata": self.custom_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SnapshotMetadata:
        return cls(
            snapshot_id=data["snapshot_id"],
            snapshot_type=SnapshotType(data["snapshot_type"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            cluster_id=data["cluster_id"],
            cluster_name=data["cluster_name"],
            version=data.get("version", "1.0"),
            size_bytes=data.get("size_bytes", 0),
            compressed_size_bytes=data.get("compressed_size_bytes", 0),
            checksum_sha256=data.get("checksum_sha256", ""),
            checksum_md5=data.get("checksum_md5", ""),
            compression=CompressionType(data.get("compression", "gzip")),
            encryption=EncryptionType(data.get("encryption", "none")),
            parent_snapshot_id=data.get("parent_snapshot_id"),
            includes_config=data.get("includes_config", True),
            includes_state=data.get("includes_state", True),
            includes_jobs=data.get("includes_jobs", True),
            includes_workers=data.get("includes_workers", True),
            includes_cache=data.get("includes_cache", False),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            custom_metadata=data.get("custom_metadata", {}),
        )


@dataclass
class SnapshotData:
    """
    بيانات اللقطة
    Snapshot data contents
    """
    # Configuration
    config: dict[str, Any] = field(default_factory=dict)

    # Cluster state
    cluster_state: dict[str, Any] = field(default_factory=dict)

    # Workers
    workers: list[dict[str, Any]] = field(default_factory=list)

    # Jobs
    jobs: list[dict[str, Any]] = field(default_factory=list)
    job_queue: list[dict[str, Any]] = field(default_factory=list)

    # Cache state (optional)
    cache_keys: list[str] = field(default_factory=list)
    cache_data: dict[str, Any] = field(default_factory=dict)

    # Metrics
    metrics: dict[str, Any] = field(default_factory=dict)

    # Incremental changes (for incremental backups)
    changes: list[dict[str, Any]] = field(default_factory=list)


class Snapshot:
    """
    لقطة النسخ الاحتياطي
    Backup Snapshot

    تمثل نسخة احتياطية كاملة أو جزئية من حالة الكتلة.
    Represents a full or partial backup of cluster state.
    """

    def __init__(
        self,
        metadata: SnapshotMetadata,
        data: Optional[SnapshotData] = None,
    ):
        """
        تهيئة اللقطة

        Args:
            metadata: البيانات الوصفية
            data: بيانات اللقطة
        """
        self.metadata = metadata
        self.data = data or SnapshotData()
        self._raw_bytes: Optional[bytes] = None

    @classmethod
    def create(
        cls,
        cluster_id: str,
        cluster_name: str,
        snapshot_type: SnapshotType = SnapshotType.FULL,
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> Snapshot:
        """إنشاء لقطة جديدة"""
        metadata = SnapshotMetadata(
            snapshot_id=str(uuid4()),
            snapshot_type=snapshot_type,
            created_at=datetime.utcnow(),
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            description=description,
            tags=tags or [],
        )
        return cls(metadata=metadata)

    def set_config(self, config: dict[str, Any]) -> None:
        """تعيين الإعدادات"""
        self.data.config = config

    def set_cluster_state(self, state: dict[str, Any]) -> None:
        """تعيين حالة الكتلة"""
        self.data.cluster_state = state

    def add_worker(self, worker: dict[str, Any]) -> None:
        """إضافة عامل"""
        self.data.workers.append(worker)

    def add_job(self, job: dict[str, Any]) -> None:
        """إضافة مهمة"""
        self.data.jobs.append(job)

    def set_cache_data(
        self,
        keys: list[str],
        data: dict[str, Any],
    ) -> None:
        """تعيين بيانات الكاش"""
        self.data.cache_keys = keys
        self.data.cache_data = data
        self.metadata.includes_cache = True

    def serialize(
        self,
        compress: bool = True,
        format: str = "pickle",
    ) -> bytes:
        """
        تسلسل اللقطة إلى بايتات

        Args:
            compress: ضغط البيانات
            format: صيغة التسلسل (pickle أو json)

        Returns:
            البيانات كبايتات
        """
        # Serialize data
        if format == "json":
            payload = {
                "metadata": self.metadata.to_dict(),
                "data": {
                    "config": self.data.config,
                    "cluster_state": self.data.cluster_state,
                    "workers": self.data.workers,
                    "jobs": self.data.jobs,
                    "job_queue": self.data.job_queue,
                    "cache_keys": self.data.cache_keys,
                    "cache_data": self.data.cache_data,
                    "metrics": self.data.metrics,
                    "changes": self.data.changes,
                },
            }
            raw_bytes = json.dumps(payload, default=str).encode()
        else:
            payload = {
                "metadata": self.metadata,
                "data": self.data,
            }
            raw_bytes = pickle.dumps(payload)

        # Calculate checksums before compression
        self.metadata.size_bytes = len(raw_bytes)
        self.metadata.checksum_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        # nosec B324 - MD5 used for checksum verification alongside SHA256, not security
        self.metadata.checksum_md5 = hashlib.md5(raw_bytes, usedforsecurity=False).hexdigest()

        # Compress if requested
        if compress:
            compressed = gzip.compress(raw_bytes)
            self.metadata.compression = CompressionType.GZIP
            self.metadata.compressed_size_bytes = len(compressed)
            self._raw_bytes = compressed
            return compressed

        self.metadata.compression = CompressionType.NONE
        self.metadata.compressed_size_bytes = len(raw_bytes)
        self._raw_bytes = raw_bytes
        return raw_bytes

    @classmethod
    def deserialize(
        cls,
        data: bytes,
        compressed: bool = True,
        format: str = "pickle",
    ) -> Snapshot:
        """
        استعادة اللقطة من البايتات

        Args:
            data: البيانات كبايتات
            compressed: هل البيانات مضغوطة
            format: صيغة التسلسل

        Returns:
            اللقطة
        """
        # Decompress if needed
        if compressed:
            raw_bytes = gzip.decompress(data)
        else:
            raw_bytes = data

        # Deserialize
        if format == "json":
            payload = json.loads(raw_bytes.decode())
            metadata = SnapshotMetadata.from_dict(payload["metadata"])
            data_dict = payload["data"]
            snapshot_data = SnapshotData(
                config=data_dict.get("config", {}),
                cluster_state=data_dict.get("cluster_state", {}),
                workers=data_dict.get("workers", []),
                jobs=data_dict.get("jobs", []),
                job_queue=data_dict.get("job_queue", []),
                cache_keys=data_dict.get("cache_keys", []),
                cache_data=data_dict.get("cache_data", {}),
                metrics=data_dict.get("metrics", {}),
                changes=data_dict.get("changes", []),
            )
        else:
            # nosec B301 - Loading snapshot data from internal backup system
            payload = pickle.loads(raw_bytes)
            metadata = payload["metadata"]
            snapshot_data = payload["data"]

        snapshot = cls(metadata=metadata, data=snapshot_data)
        snapshot._raw_bytes = data
        return snapshot

    def verify_checksum(self, data: bytes) -> bool:
        """التحقق من سلامة البيانات"""
        if self.metadata.compression == CompressionType.GZIP:
            raw_bytes = gzip.decompress(data)
        else:
            raw_bytes = data

        calculated_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        return calculated_sha256 == self.metadata.checksum_sha256

    def get_size_info(self) -> dict[str, Any]:
        """الحصول على معلومات الحجم"""
        compression_ratio = (
            1 - (self.metadata.compressed_size_bytes / self.metadata.size_bytes)
            if self.metadata.size_bytes > 0
            else 0
        )

        return {
            "size_bytes": self.metadata.size_bytes,
            "compressed_size_bytes": self.metadata.compressed_size_bytes,
            "compression_ratio": f"{compression_ratio:.1%}",
            "compression": self.metadata.compression.value,
        }

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس"""
        return {
            "metadata": self.metadata.to_dict(),
            "size_info": self.get_size_info(),
            "includes": {
                "config": self.metadata.includes_config,
                "state": self.metadata.includes_state,
                "jobs": self.metadata.includes_jobs,
                "workers": self.metadata.includes_workers,
                "cache": self.metadata.includes_cache,
            },
        }


class SnapshotBuilder:
    """
    بناء اللقطات
    Snapshot Builder

    يساعد في بناء لقطات معقدة خطوة بخطوة.
    Helps build complex snapshots step by step.
    """

    def __init__(
        self,
        cluster_id: str,
        cluster_name: str,
    ):
        """تهيئة البناء"""
        self.cluster_id = cluster_id
        self.cluster_name = cluster_name
        self._snapshot: Optional[Snapshot] = None
        self._snapshot_type = SnapshotType.FULL

    def set_type(self, snapshot_type: SnapshotType) -> SnapshotBuilder:
        """تعيين نوع اللقطة"""
        self._snapshot_type = snapshot_type
        return self

    def with_description(self, description: str) -> SnapshotBuilder:
        """إضافة وصف"""
        self._ensure_snapshot()
        self._snapshot.metadata.description = description
        return self

    def with_tags(self, tags: list[str]) -> SnapshotBuilder:
        """إضافة علامات"""
        self._ensure_snapshot()
        self._snapshot.metadata.tags = tags
        return self

    def with_config(self, config: dict[str, Any]) -> SnapshotBuilder:
        """إضافة الإعدادات"""
        self._ensure_snapshot()
        self._snapshot.set_config(config)
        return self

    def with_state(self, state: dict[str, Any]) -> SnapshotBuilder:
        """إضافة الحالة"""
        self._ensure_snapshot()
        self._snapshot.set_cluster_state(state)
        return self

    def with_workers(self, workers: list[dict[str, Any]]) -> SnapshotBuilder:
        """إضافة العمال"""
        self._ensure_snapshot()
        for worker in workers:
            self._snapshot.add_worker(worker)
        return self

    def with_jobs(self, jobs: list[dict[str, Any]]) -> SnapshotBuilder:
        """إضافة المهام"""
        self._ensure_snapshot()
        for job in jobs:
            self._snapshot.add_job(job)
        return self

    def with_cache(
        self,
        keys: list[str],
        data: dict[str, Any],
    ) -> SnapshotBuilder:
        """إضافة الكاش"""
        self._ensure_snapshot()
        self._snapshot.set_cache_data(keys, data)
        return self

    def with_parent(self, parent_snapshot_id: str) -> SnapshotBuilder:
        """تعيين اللقطة الأب (للنسخ التزايدي)"""
        self._ensure_snapshot()
        self._snapshot.metadata.parent_snapshot_id = parent_snapshot_id
        return self

    def build(self) -> Snapshot:
        """بناء اللقطة النهائية"""
        self._ensure_snapshot()
        return self._snapshot

    def _ensure_snapshot(self) -> None:
        """التأكد من وجود لقطة"""
        if self._snapshot is None:
            self._snapshot = Snapshot.create(
                cluster_id=self.cluster_id,
                cluster_name=self.cluster_name,
                snapshot_type=self._snapshot_type,
            )
