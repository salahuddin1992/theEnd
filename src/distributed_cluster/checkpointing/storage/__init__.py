"""
Checkpoint Storage Backends
===========================

Storage backends for checkpoint persistence.
"""

from distributed_cluster.checkpointing.storage.base import (
    CheckpointStorage,
    StorageConfig,
)
from distributed_cluster.checkpointing.storage.local import LocalStorage
from distributed_cluster.checkpointing.storage.s3 import S3Storage
from distributed_cluster.checkpointing.storage.azure import AzureBlobStorage

__all__ = [
    "CheckpointStorage",
    "StorageConfig",
    "LocalStorage",
    "S3Storage",
    "AzureBlobStorage",
]
