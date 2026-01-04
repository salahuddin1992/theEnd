"""
Job Checkpointing - نظام نقاط الحفظ للمهام
==========================================

Job Checkpointing System
------------------------

This module provides checkpoint functionality for long-running jobs,
enabling resume from failure with minimal work loss.

يوفر هذا النظام نقاط حفظ للمهام طويلة التشغيل:
- حفظ الحالة على القرص المحلي
- حفظ الحالة على S3
- حفظ الحالة على Azure Blob Storage
- استئناف المهام من نقطة الفشل
- إدارة دورة حياة نقاط الحفظ

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.checkpointing.checkpoint import (
    Checkpoint,
    CheckpointData,
    CheckpointManager,
    CheckpointMetadata,
    CheckpointState,
)
from distributed_cluster.checkpointing.storage.azure import AzureBlobStorage
from distributed_cluster.checkpointing.storage.base import (
    CheckpointStorage,
    StorageConfig,
)
from distributed_cluster.checkpointing.storage.local import LocalStorage
from distributed_cluster.checkpointing.storage.s3 import S3Storage

__all__ = [
    # Core
    "Checkpoint",
    "CheckpointData",
    "CheckpointManager",
    "CheckpointMetadata",
    "CheckpointState",
    # Storage Base
    "CheckpointStorage",
    "StorageConfig",
    # Storage Implementations
    "LocalStorage",
    "S3Storage",
    "AzureBlobStorage",
]
