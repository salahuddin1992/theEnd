"""
Backup & Restore System - نظام النسخ الاحتياطي والاستعادة
=========================================================

Comprehensive Backup System
---------------------------

This module provides backup and restore functionality:
- Automatic state backups
- Manual backup creation
- Point-in-time restore
- Configuration export/import
- Incremental backups
- Multiple storage backends

يوفر هذا النظام وظائف النسخ الاحتياطي والاستعادة:
- نسخ احتياطي تلقائي للحالة
- إنشاء نسخ يدوية
- استعادة من نقطة زمنية
- تصدير/استيراد الإعدادات
- نسخ تزايدي
- دعم عدة وسائط تخزين

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.backup.manager import (
    BackupConfig,
    BackupManager,
    BackupResult,
    RestoreResult,
)
from distributed_cluster.backup.scheduler import (
    BackupScheduler,
    RetentionPolicy,
    ScheduleConfig,
)
from distributed_cluster.backup.snapshot import (
    Snapshot,
    SnapshotMetadata,
    SnapshotType,
)
from distributed_cluster.backup.storage import (
    AzureStorage,
    BackupStorage,
    LocalStorage,
    S3Storage,
)

__all__ = [
    # Manager
    "BackupManager",
    "BackupConfig",
    "BackupResult",
    "RestoreResult",
    # Snapshot
    "Snapshot",
    "SnapshotMetadata",
    "SnapshotType",
    # Storage
    "BackupStorage",
    "LocalStorage",
    "S3Storage",
    "AzureStorage",
    # Scheduler
    "BackupScheduler",
    "ScheduleConfig",
    "RetentionPolicy",
]
