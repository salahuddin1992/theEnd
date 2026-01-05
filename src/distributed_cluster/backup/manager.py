"""
Backup Manager - مدير النسخ الاحتياطي
======================================

Backup Management
-----------------

This module provides the main backup manager.

يوفر هذا الملف مدير النسخ الاحتياطي الرئيسي.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from distributed_cluster.backup.scheduler import (
    BackupScheduler,
    RetentionPolicy,
)
from distributed_cluster.backup.snapshot import (
    Snapshot,
    SnapshotBuilder,
    SnapshotMetadata,
    SnapshotType,
)
from distributed_cluster.backup.storage import BackupStorage, LocalStorage

logger = logging.getLogger(__name__)


@dataclass
class BackupConfig:
    """
    إعدادات النسخ الاحتياطي
    Backup Configuration
    """

    # Cluster info
    cluster_id: str
    cluster_name: str

    # Storage
    storage_type: str = "local"
    storage_path: str = "./backups"
    s3_bucket: Optional[str] = None
    azure_container: Optional[str] = None

    # Compression
    compress: bool = True
    compression_level: int = 6

    # Content options
    include_cache: bool = False
    include_metrics: bool = True

    # Scheduling
    enable_scheduling: bool = True
    default_schedule: str = "daily"

    # Retention
    retention_days: int = 30
    max_backups: int = 100


@dataclass
class BackupResult:
    """
    نتيجة النسخ الاحتياطي
    Backup Result
    """

    success: bool
    snapshot_id: Optional[str] = None
    snapshot_type: SnapshotType = SnapshotType.FULL
    size_bytes: int = 0
    compressed_size_bytes: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "snapshot_id": self.snapshot_id,
            "snapshot_type": self.snapshot_type.value,
            "size_bytes": self.size_bytes,
            "compressed_size_bytes": self.compressed_size_bytes,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RestoreResult:
    """
    نتيجة الاستعادة
    Restore Result
    """

    success: bool
    snapshot_id: str
    restored_items: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "snapshot_id": self.snapshot_id,
            "restored_items": self.restored_items,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class BackupManager:
    """
    مدير النسخ الاحتياطي
    Backup Manager

    يدير إنشاء واستعادة النسخ الاحتياطية.
    Manages backup creation and restoration.
    """

    def __init__(
        self,
        config: BackupConfig,
        storage: Optional[BackupStorage] = None,
    ):
        """
        تهيئة المدير

        Args:
            config: إعدادات النسخ الاحتياطي
            storage: وسيط التخزين
        """
        self.config = config

        # Initialize storage
        if storage:
            self._storage = storage
        else:
            self._storage = self._create_storage()

        # Initialize scheduler
        self._scheduler = BackupScheduler(
            backup_callback=self._scheduled_backup,
            cleanup_callback=self._cleanup_old_backups,
        )

        # State providers
        self._state_providers: dict[str, Any] = {}

        # Stats
        self._stats = {
            "total_backups": 0,
            "successful_backups": 0,
            "failed_backups": 0,
            "total_restores": 0,
            "successful_restores": 0,
        }

    def _create_storage(self) -> BackupStorage:
        """إنشاء وسيط التخزين"""
        if self.config.storage_type == "local":
            return LocalStorage(self.config.storage_path)

        elif self.config.storage_type == "s3":
            from distributed_cluster.backup.storage import S3Storage

            return S3Storage(bucket=self.config.s3_bucket)

        elif self.config.storage_type == "azure":
            from distributed_cluster.backup.storage import AzureStorage

            return AzureStorage(container_name=self.config.azure_container)

        else:
            return LocalStorage(self.config.storage_path)

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء المدير"""
        if self.config.enable_scheduling:
            await self._scheduler.start()

            # Add default schedules
            self._add_default_schedules()

        logger.info(f"BackupManager started for cluster {self.config.cluster_id}")

    async def stop(self) -> None:
        """إيقاف المدير"""
        await self._scheduler.stop()
        logger.info("BackupManager stopped")

    def _add_default_schedules(self) -> None:
        """إضافة الجدولة الافتراضية"""
        from distributed_cluster.backup.scheduler import (
            create_daily_schedule,
            create_hourly_schedule,
            create_standard_retention,
        )

        # Daily full backup
        self._scheduler.add_job(
            job_id="daily-full",
            config=create_daily_schedule(hour=2),
            retention_policy=create_standard_retention(),
        )

        # Hourly incremental
        self._scheduler.add_job(
            job_id="hourly-incremental",
            config=create_hourly_schedule(),
            retention_policy=RetentionPolicy(
                keep_incremental_count=24,
                max_age_days=2,
            ),
        )

    # =========================================================================
    # State Providers
    # =========================================================================

    def register_state_provider(
        self,
        name: str,
        provider: Any,
    ) -> None:
        """
        تسجيل مزود حالة

        Args:
            name: اسم المزود
            provider: كائن يوفر get_state() و set_state()
        """
        self._state_providers[name] = provider
        logger.debug(f"Registered state provider: {name}")

    # =========================================================================
    # Backup Operations
    # =========================================================================

    async def create_backup(
        self,
        snapshot_type: SnapshotType = SnapshotType.FULL,
        description: str = "",
        tags: Optional[list[str]] = None,
        include_cache: bool = False,
    ) -> BackupResult:
        """
        إنشاء نسخة احتياطية

        Args:
            snapshot_type: نوع اللقطة
            description: وصف
            tags: علامات
            include_cache: تضمين الكاش

        Returns:
            نتيجة النسخ الاحتياطي
        """
        start_time = datetime.now(timezone.utc)
        self._stats["total_backups"] += 1

        try:
            # Build snapshot
            builder = SnapshotBuilder(
                cluster_id=self.config.cluster_id,
                cluster_name=self.config.cluster_name,
            )

            builder.set_type(snapshot_type)
            builder.with_description(description)
            builder.with_tags(tags or [])

            # Collect state from providers
            await self._collect_state(builder, include_cache)

            # Build and serialize
            snapshot = builder.build()
            data = snapshot.serialize(compress=self.config.compress)

            # Save to storage
            await self._storage.save(snapshot, data)

            # Calculate duration
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            self._stats["successful_backups"] += 1

            logger.info(
                f"Backup created: {snapshot.metadata.snapshot_id} "
                f"({snapshot.metadata.compressed_size_bytes} bytes, {duration:.2f}s)"
            )

            return BackupResult(
                success=True,
                snapshot_id=snapshot.metadata.snapshot_id,
                snapshot_type=snapshot_type,
                size_bytes=snapshot.metadata.size_bytes,
                compressed_size_bytes=snapshot.metadata.compressed_size_bytes,
                duration_seconds=duration,
            )

        except Exception as e:
            self._stats["failed_backups"] += 1
            logger.error(f"Backup failed: {e}")

            return BackupResult(
                success=False,
                error=str(e),
                duration_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
            )

    async def _collect_state(
        self,
        builder: SnapshotBuilder,
        include_cache: bool,
    ) -> None:
        """جمع الحالة من المزودين"""
        collected_state = {}
        workers = []
        jobs = []

        for name, provider in self._state_providers.items():
            try:
                if hasattr(provider, "get_state"):
                    state = await self._call_async_or_sync(provider.get_state)
                    collected_state[name] = state

                if hasattr(provider, "get_workers"):
                    ws = await self._call_async_or_sync(provider.get_workers)
                    workers.extend(ws)

                if hasattr(provider, "get_jobs"):
                    js = await self._call_async_or_sync(provider.get_jobs)
                    jobs.extend(js)

            except Exception as e:
                logger.warning(f"Failed to collect state from {name}: {e}")

        builder.with_state(collected_state)
        builder.with_workers(workers)
        builder.with_jobs(jobs)

        # Collect cache if requested
        if include_cache:
            await self._collect_cache(builder)

    async def _collect_cache(self, builder: SnapshotBuilder) -> None:
        """جمع بيانات الكاش"""
        cache_keys = []
        cache_data = {}

        for name, provider in self._state_providers.items():
            if hasattr(provider, "get_cache_data"):
                try:
                    keys, data = await self._call_async_or_sync(provider.get_cache_data)
                    cache_keys.extend(keys)
                    cache_data.update(data)
                except Exception as e:
                    logger.warning(f"Failed to collect cache from {name}: {e}")

        if cache_keys:
            builder.with_cache(cache_keys, cache_data)

    async def _call_async_or_sync(self, func):
        """استدعاء دالة متزامنة أو غير متزامنة"""
        if asyncio.iscoroutinefunction(func):
            return await func()
        return func()

    # =========================================================================
    # Restore Operations
    # =========================================================================

    async def restore(
        self,
        snapshot_id: str,
        restore_config: bool = True,
        restore_state: bool = True,
        restore_jobs: bool = False,
        dry_run: bool = False,
    ) -> RestoreResult:
        """
        استعادة من نسخة احتياطية

        Args:
            snapshot_id: معرف اللقطة
            restore_config: استعادة الإعدادات
            restore_state: استعادة الحالة
            restore_jobs: استعادة المهام
            dry_run: تشغيل تجريبي

        Returns:
            نتيجة الاستعادة
        """
        start_time = datetime.now(timezone.utc)
        self._stats["total_restores"] += 1

        try:
            # Load snapshot
            metadata, data = await self._storage.load(snapshot_id)
            snapshot = Snapshot.deserialize(
                data,
                compressed=metadata.compression.value != "none",
            )

            # Verify checksum
            if not snapshot.verify_checksum(data):
                raise ValueError("Checksum verification failed")

            restored_items = {}

            if dry_run:
                logger.info(f"Dry run restore of {snapshot_id}")
                restored_items = self._get_restore_preview(snapshot)
            else:
                # Restore to providers
                restored_items = await self._apply_restore(
                    snapshot,
                    restore_config,
                    restore_state,
                    restore_jobs,
                )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self._stats["successful_restores"] += 1

            logger.info(f"Restore completed: {snapshot_id} ({duration:.2f}s)")

            return RestoreResult(
                success=True,
                snapshot_id=snapshot_id,
                restored_items=restored_items,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"Restore failed: {e}")

            return RestoreResult(
                success=False,
                snapshot_id=snapshot_id,
                error=str(e),
                duration_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
            )

    def _get_restore_preview(self, snapshot: Snapshot) -> dict[str, int]:
        """الحصول على معاينة الاستعادة"""
        return {
            "config_keys": len(snapshot.data.config),
            "state_keys": len(snapshot.data.cluster_state),
            "workers": len(snapshot.data.workers),
            "jobs": len(snapshot.data.jobs),
            "cache_keys": len(snapshot.data.cache_keys),
        }

    async def _apply_restore(
        self,
        snapshot: Snapshot,
        restore_config: bool,
        restore_state: bool,
        restore_jobs: bool,
    ) -> dict[str, int]:
        """تطبيق الاستعادة"""
        restored = {}

        for name, provider in self._state_providers.items():
            try:
                if restore_config and hasattr(provider, "set_config"):
                    config = snapshot.data.config.get(name, {})
                    await self._call_async_or_sync(lambda: provider.set_config(config))
                    restored[f"{name}_config"] = len(config)

                if restore_state and hasattr(provider, "set_state"):
                    state = snapshot.data.cluster_state.get(name, {})
                    await self._call_async_or_sync(lambda: provider.set_state(state))
                    restored[f"{name}_state"] = len(state)

                if restore_jobs and hasattr(provider, "restore_jobs"):
                    await self._call_async_or_sync(lambda: provider.restore_jobs(snapshot.data.jobs))
                    restored["jobs"] = len(snapshot.data.jobs)

            except Exception as e:
                logger.warning(f"Failed to restore to {name}: {e}")

        return restored

    # =========================================================================
    # List & Query
    # =========================================================================

    async def list_backups(
        self,
        limit: int = 100,
        offset: int = 0,
        snapshot_type: Optional[SnapshotType] = None,
    ) -> list[SnapshotMetadata]:
        """قائمة النسخ الاحتياطية"""
        snapshots = await self._storage.list_snapshots(
            cluster_id=self.config.cluster_id,
            limit=limit,
            offset=offset,
        )

        if snapshot_type:
            snapshots = [s for s in snapshots if s.snapshot_type == snapshot_type]

        return snapshots

    async def get_backup(self, snapshot_id: str) -> Optional[SnapshotMetadata]:
        """الحصول على معلومات نسخة احتياطية"""
        try:
            metadata, _ = await self._storage.load(snapshot_id)
            return metadata
        except FileNotFoundError:
            return None

    async def delete_backup(self, snapshot_id: str) -> bool:
        """حذف نسخة احتياطية"""
        return await self._storage.delete(snapshot_id)

    # =========================================================================
    # Export/Import
    # =========================================================================

    async def export_config(
        self,
        output_path: str | Path,
        format: str = "json",
    ) -> bool:
        """
        تصدير الإعدادات

        Args:
            output_path: مسار الملف
            format: صيغة التصدير (json, yaml)

        Returns:
            نجاح العملية
        """
        try:
            config_data = {}

            for name, provider in self._state_providers.items():
                if hasattr(provider, "get_config"):
                    config = await self._call_async_or_sync(provider.get_config)
                    config_data[name] = config

            output_path = Path(output_path)

            if format == "json":
                output_path.write_text(json.dumps(config_data, indent=2))
            elif format == "yaml":
                import yaml

                output_path.write_text(yaml.dump(config_data))

            logger.info(f"Config exported to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Config export failed: {e}")
            return False

    async def import_config(
        self,
        input_path: str | Path,
        format: str = "json",
        merge: bool = False,
    ) -> bool:
        """
        استيراد الإعدادات

        Args:
            input_path: مسار الملف
            format: صيغة الملف
            merge: دمج مع الإعدادات الحالية

        Returns:
            نجاح العملية
        """
        try:
            input_path = Path(input_path)

            if format == "json":
                config_data = json.loads(input_path.read_text())
            elif format == "yaml":
                import yaml

                config_data = yaml.safe_load(input_path.read_text())
            else:
                raise ValueError(f"Unsupported format: {format}")

            for name, provider in self._state_providers.items():
                if name in config_data and hasattr(provider, "set_config"):
                    if merge and hasattr(provider, "get_config"):
                        current = await self._call_async_or_sync(provider.get_config)
                        current.update(config_data[name])
                        config_data[name] = current

                    await self._call_async_or_sync(lambda: provider.set_config(config_data[name]))

            logger.info(f"Config imported from {input_path}")
            return True

        except Exception as e:
            logger.error(f"Config import failed: {e}")
            return False

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def _cleanup_old_backups(
        self,
        policy: RetentionPolicy,
    ) -> int:
        """تنظيف النسخ القديمة"""
        deleted = 0
        now = datetime.now(timezone.utc)

        snapshots = await self._storage.list_snapshots(
            cluster_id=self.config.cluster_id,
            limit=10000,
        )

        # Group by type
        by_type: dict[SnapshotType, list[SnapshotMetadata]] = {}
        for s in snapshots:
            if s.snapshot_type not in by_type:
                by_type[s.snapshot_type] = []
            by_type[s.snapshot_type].append(s)

        # Calculate total size
        total_size_gb = sum(s.compressed_size_bytes for s in snapshots) / (1024**3)

        for snapshot_type, type_snapshots in by_type.items():
            # Sort oldest first
            type_snapshots.sort(key=lambda s: s.created_at)

            for snapshot in type_snapshots:
                age_days = (now - snapshot.created_at).days

                if policy.should_delete(
                    snapshot_age_days=age_days,
                    snapshot_type=snapshot_type,
                    current_count=len(type_snapshots) - deleted,
                    current_size_gb=total_size_gb,
                ):
                    if await self._storage.delete(snapshot.snapshot_id):
                        deleted += 1
                        total_size_gb -= snapshot.compressed_size_bytes / (1024**3)
                        logger.info(f"Deleted old backup: {snapshot.snapshot_id}")

        return deleted

    async def _scheduled_backup(self, **kwargs) -> None:
        """نسخ احتياطي مجدول"""
        await self.create_backup(**kwargs)

    # =========================================================================
    # Status
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """الحصول على الإحصائيات"""
        return {
            **self._stats,
            "scheduler": self._scheduler.get_status(),
        }

    async def get_storage_stats(self):
        """الحصول على إحصائيات التخزين"""
        return await self._storage.get_stats()
