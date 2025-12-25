"""
Backup Scheduler - جدولة النسخ الاحتياطي
=========================================

Backup Scheduling
-----------------

This module provides backup scheduling and retention policies.

يوفر هذا الملف جدولة النسخ الاحتياطي وسياسات الاحتفاظ.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

from distributed_cluster.backup.snapshot import SnapshotType

logger = logging.getLogger(__name__)


class ScheduleType(str, Enum):
    """نوع الجدولة / Schedule type"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CRON = "cron"
    INTERVAL = "interval"


class RetentionUnit(str, Enum):
    """وحدة الاحتفاظ / Retention unit"""
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    COUNT = "count"


@dataclass
class RetentionPolicy:
    """
    سياسة الاحتفاظ
    Retention Policy

    تحدد مدة الاحتفاظ بالنسخ الاحتياطية.
    Defines how long to keep backups.
    """
    # Keep last N full backups
    keep_full_count: int = 7

    # Keep last N incremental backups
    keep_incremental_count: int = 24

    # Maximum age for any backup
    max_age_days: int = 30

    # Minimum backups to keep regardless of age
    min_backups: int = 3

    # Size-based retention
    max_total_size_gb: Optional[float] = None

    # Per-type retention
    retention_by_type: dict[SnapshotType, int] = field(default_factory=dict)

    def should_delete(
        self,
        snapshot_age_days: float,
        snapshot_type: SnapshotType,
        current_count: int,
        current_size_gb: float,
    ) -> bool:
        """
        هل يجب حذف هذه اللقطة؟

        Args:
            snapshot_age_days: عمر اللقطة بالأيام
            snapshot_type: نوع اللقطة
            current_count: العدد الحالي
            current_size_gb: الحجم الحالي بـ GB

        Returns:
            True إذا يجب الحذف
        """
        # Don't delete if below minimum
        if current_count <= self.min_backups:
            return False

        # Delete if too old
        if snapshot_age_days > self.max_age_days:
            return True

        # Delete if exceeding size limit
        if self.max_total_size_gb and current_size_gb > self.max_total_size_gb:
            return True

        # Check type-specific retention
        if snapshot_type in self.retention_by_type:
            type_limit = self.retention_by_type[snapshot_type]
            if current_count > type_limit:
                return True

        # Check count limits
        if snapshot_type == SnapshotType.FULL:
            return current_count > self.keep_full_count
        elif snapshot_type == SnapshotType.INCREMENTAL:
            return current_count > self.keep_incremental_count

        return False


@dataclass
class ScheduleConfig:
    """
    إعدادات الجدولة
    Schedule Configuration
    """
    schedule_type: ScheduleType = ScheduleType.DAILY
    snapshot_type: SnapshotType = SnapshotType.FULL

    # For INTERVAL type
    interval_hours: float = 24.0

    # For DAILY type
    daily_hour: int = 2  # 2 AM
    daily_minute: int = 0

    # For WEEKLY type
    weekly_day: int = 0  # Monday = 0
    weekly_hour: int = 2

    # For MONTHLY type
    monthly_day: int = 1  # 1st of month
    monthly_hour: int = 2

    # For CRON type
    cron_expression: str = "0 2 * * *"

    # General settings
    enabled: bool = True
    description: str = ""
    tags: list[str] = field(default_factory=list)

    # Retry settings
    retry_on_failure: bool = True
    max_retries: int = 3
    retry_delay_minutes: int = 5

    def get_next_run(self, from_time: Optional[datetime] = None) -> datetime:
        """حساب موعد التشغيل التالي"""
        now = from_time or datetime.utcnow()

        if self.schedule_type == ScheduleType.INTERVAL:
            return now + timedelta(hours=self.interval_hours)

        elif self.schedule_type == ScheduleType.HOURLY:
            next_hour = now.replace(minute=0, second=0, microsecond=0)
            next_hour += timedelta(hours=1)
            return next_hour

        elif self.schedule_type == ScheduleType.DAILY:
            next_run = now.replace(
                hour=self.daily_hour,
                minute=self.daily_minute,
                second=0,
                microsecond=0,
            )
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        elif self.schedule_type == ScheduleType.WEEKLY:
            days_ahead = self.weekly_day - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7

            next_run = now + timedelta(days=days_ahead)
            next_run = next_run.replace(
                hour=self.weekly_hour,
                minute=0,
                second=0,
                microsecond=0,
            )
            return next_run

        elif self.schedule_type == ScheduleType.MONTHLY:
            next_run = now.replace(
                day=self.monthly_day,
                hour=self.monthly_hour,
                minute=0,
                second=0,
                microsecond=0,
            )
            if next_run <= now:
                # Move to next month
                if now.month == 12:
                    next_run = next_run.replace(year=now.year + 1, month=1)
                else:
                    next_run = next_run.replace(month=now.month + 1)
            return next_run

        elif self.schedule_type == ScheduleType.CRON:
            # Simple cron parsing (would need croniter for full support)
            return now + timedelta(hours=24)

        return now + timedelta(hours=24)


@dataclass
class ScheduledBackup:
    """
    نسخة احتياطية مجدولة
    Scheduled Backup Job
    """
    job_id: str
    config: ScheduleConfig
    retention_policy: RetentionPolicy
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    last_status: str = "pending"
    run_count: int = 0
    failure_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "schedule_type": self.config.schedule_type.value,
            "snapshot_type": self.config.snapshot_type.value,
            "enabled": self.config.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "last_status": self.last_status,
            "run_count": self.run_count,
            "failure_count": self.failure_count,
        }


class BackupScheduler:
    """
    جدولة النسخ الاحتياطي
    Backup Scheduler

    يدير جدولة النسخ الاحتياطية التلقائية.
    Manages automatic backup scheduling.
    """

    def __init__(
        self,
        backup_callback: Callable[..., Any],
        cleanup_callback: Optional[Callable[..., Any]] = None,
    ):
        """
        تهيئة المجدول

        Args:
            backup_callback: دالة إنشاء النسخة الاحتياطية
            cleanup_callback: دالة تنظيف النسخ القديمة
        """
        self.backup_callback = backup_callback
        self.cleanup_callback = cleanup_callback

        self._jobs: dict[str, ScheduledBackup] = {}
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء المجدول"""
        self._running = True
        self._scheduler_task = asyncio.create_task(self._run_scheduler())
        logger.info("Backup scheduler started")

    async def stop(self) -> None:
        """إيقاف المجدول"""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Backup scheduler stopped")

    # =========================================================================
    # Job Management
    # =========================================================================

    def add_job(
        self,
        job_id: str,
        config: ScheduleConfig,
        retention_policy: Optional[RetentionPolicy] = None,
    ) -> ScheduledBackup:
        """إضافة مهمة مجدولة"""
        job = ScheduledBackup(
            job_id=job_id,
            config=config,
            retention_policy=retention_policy or RetentionPolicy(),
            next_run=config.get_next_run(),
        )
        self._jobs[job_id] = job
        logger.info(f"Added backup job {job_id}, next run: {job.next_run}")
        return job

    def remove_job(self, job_id: str) -> bool:
        """إزالة مهمة"""
        if job_id in self._jobs:
            del self._jobs[job_id]
            logger.info(f"Removed backup job {job_id}")
            return True
        return False

    def get_job(self, job_id: str) -> Optional[ScheduledBackup]:
        """الحصول على مهمة"""
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[ScheduledBackup]:
        """قائمة المهام"""
        return list(self._jobs.values())

    def enable_job(self, job_id: str) -> bool:
        """تفعيل مهمة"""
        job = self._jobs.get(job_id)
        if job:
            job.config.enabled = True
            job.next_run = job.config.get_next_run()
            return True
        return False

    def disable_job(self, job_id: str) -> bool:
        """تعطيل مهمة"""
        job = self._jobs.get(job_id)
        if job:
            job.config.enabled = False
            job.next_run = None
            return True
        return False

    # =========================================================================
    # Scheduler Loop
    # =========================================================================

    async def _run_scheduler(self) -> None:
        """حلقة المجدول"""
        while self._running:
            try:
                now = datetime.utcnow()

                for job in self._jobs.values():
                    if not job.config.enabled:
                        continue

                    if job.next_run and now >= job.next_run:
                        await self._execute_job(job)

                # Sleep for 1 minute between checks
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)

    async def _execute_job(self, job: ScheduledBackup) -> None:
        """تنفيذ مهمة"""
        job_id = job.job_id
        logger.info(f"Executing backup job {job_id}")

        retries = 0
        success = False

        while retries <= job.config.max_retries:
            try:
                # Execute backup
                await self.backup_callback(
                    snapshot_type=job.config.snapshot_type,
                    tags=job.config.tags + [f"scheduled:{job_id}"],
                    description=f"Scheduled backup: {job.config.description}",
                )

                success = True
                job.last_status = "success"
                job.run_count += 1
                logger.info(f"Backup job {job_id} completed successfully")
                break

            except Exception as e:
                retries += 1
                job.failure_count += 1
                logger.error(f"Backup job {job_id} failed (attempt {retries}): {e}")

                if retries <= job.config.max_retries and job.config.retry_on_failure:
                    await asyncio.sleep(job.config.retry_delay_minutes * 60)
                else:
                    job.last_status = f"failed: {str(e)}"

        # Update timing
        job.last_run = datetime.utcnow()
        job.next_run = job.config.get_next_run()

        # Run cleanup if configured
        if success and self.cleanup_callback:
            try:
                await self.cleanup_callback(job.retention_policy)
            except Exception as e:
                logger.error(f"Cleanup failed for job {job_id}: {e}")

    # =========================================================================
    # Manual Operations
    # =========================================================================

    async def run_now(self, job_id: str) -> bool:
        """تشغيل مهمة الآن"""
        job = self._jobs.get(job_id)
        if not job:
            return False

        await self._execute_job(job)
        return True

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """الحصول على الحالة"""
        return {
            "running": self._running,
            "jobs_count": len(self._jobs),
            "enabled_jobs": sum(1 for j in self._jobs.values() if j.config.enabled),
            "jobs": [j.to_dict() for j in self._jobs.values()],
        }

    def get_next_scheduled(self) -> Optional[ScheduledBackup]:
        """الحصول على المهمة التالية المجدولة"""
        enabled_jobs = [
            j for j in self._jobs.values()
            if j.config.enabled and j.next_run
        ]

        if not enabled_jobs:
            return None

        return min(enabled_jobs, key=lambda j: j.next_run)


# =============================================================================
# Preset Schedules
# =============================================================================

def create_hourly_schedule(
    snapshot_type: SnapshotType = SnapshotType.INCREMENTAL,
) -> ScheduleConfig:
    """إنشاء جدولة كل ساعة"""
    return ScheduleConfig(
        schedule_type=ScheduleType.HOURLY,
        snapshot_type=snapshot_type,
        description="Hourly backup",
    )


def create_daily_schedule(
    hour: int = 2,
    snapshot_type: SnapshotType = SnapshotType.FULL,
) -> ScheduleConfig:
    """إنشاء جدولة يومية"""
    return ScheduleConfig(
        schedule_type=ScheduleType.DAILY,
        snapshot_type=snapshot_type,
        daily_hour=hour,
        description="Daily backup",
    )


def create_weekly_schedule(
    day: int = 0,
    hour: int = 2,
    snapshot_type: SnapshotType = SnapshotType.FULL,
) -> ScheduleConfig:
    """إنشاء جدولة أسبوعية"""
    return ScheduleConfig(
        schedule_type=ScheduleType.WEEKLY,
        snapshot_type=snapshot_type,
        weekly_day=day,
        weekly_hour=hour,
        description="Weekly backup",
    )


def create_standard_retention() -> RetentionPolicy:
    """إنشاء سياسة احتفاظ قياسية"""
    return RetentionPolicy(
        keep_full_count=7,
        keep_incremental_count=24,
        max_age_days=30,
        min_backups=3,
    )


def create_extended_retention() -> RetentionPolicy:
    """إنشاء سياسة احتفاظ ممتدة"""
    return RetentionPolicy(
        keep_full_count=30,
        keep_incremental_count=168,  # 7 days hourly
        max_age_days=90,
        min_backups=7,
    )
