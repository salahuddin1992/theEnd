"""
Notification Scheduler - مجدول الإشعارات
=========================================

Schedule notifications for delayed or recurring delivery.
جدولة الإشعارات للتسليم المؤجل أو المتكرر.

Features:
- One-time delayed notifications
- Recurring notifications (cron-like)
- Priority-based scheduling
- Persistence support
- Timezone awareness
- Job management (pause, resume, cancel)
"""

from __future__ import annotations

import asyncio
import heapq
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from distributed_cluster.notifications.channels import (
    Notification,
)

logger = logging.getLogger(__name__)


class ScheduleType(str, Enum):
    """نوع الجدولة."""

    ONCE = "once"                    # مرة واحدة
    INTERVAL = "interval"            # كل فترة
    DAILY = "daily"                  # يومياً
    WEEKLY = "weekly"                # أسبوعياً
    MONTHLY = "monthly"              # شهرياً
    CRON = "cron"                    # تعبير cron


class JobStatus(str, Enum):
    """حالة المهمة."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Schedule:
    """
    إعدادات الجدولة.

    Schedule Configuration.
    """

    schedule_type: ScheduleType
    run_at: Optional[datetime] = None           # For ONCE
    interval_seconds: Optional[int] = None       # For INTERVAL
    time_of_day: Optional[str] = None           # HH:MM for DAILY/WEEKLY/MONTHLY
    day_of_week: Optional[int] = None           # 0=Mon, 6=Sun for WEEKLY
    day_of_month: Optional[int] = None          # 1-31 for MONTHLY
    cron_expression: Optional[str] = None       # For CRON
    timezone: str = "UTC"
    max_runs: Optional[int] = None              # Max number of executions
    end_time: Optional[datetime] = None         # Stop scheduling after this

    def next_run_time(self, after: Optional[datetime] = None) -> Optional[datetime]:
        """حساب وقت التشغيل التالي."""
        now = after or datetime.now(timezone.utc)

        if self.schedule_type == ScheduleType.ONCE:
            if self.run_at and self.run_at > now:
                return self.run_at
            return None

        elif self.schedule_type == ScheduleType.INTERVAL:
            if self.interval_seconds:
                return now + timedelta(seconds=self.interval_seconds)
            return None

        elif self.schedule_type == ScheduleType.DAILY:
            if self.time_of_day:
                hour, minute = map(int, self.time_of_day.split(":"))
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
                return next_run
            return None

        elif self.schedule_type == ScheduleType.WEEKLY:
            if self.time_of_day and self.day_of_week is not None:
                hour, minute = map(int, self.time_of_day.split(":"))
                days_ahead = self.day_of_week - now.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                next_run = now + timedelta(days=days_ahead)
                next_run = next_run.replace(hour=hour, minute=minute, second=0, microsecond=0)
                return next_run
            return None

        elif self.schedule_type == ScheduleType.MONTHLY:
            if self.time_of_day and self.day_of_month:
                hour, minute = map(int, self.time_of_day.split(":"))
                next_run = now.replace(
                    day=min(self.day_of_month, 28),  # Simplified
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0,
                )
                if next_run <= now:
                    # Move to next month
                    if next_run.month == 12:
                        next_run = next_run.replace(year=next_run.year + 1, month=1)
                    else:
                        next_run = next_run.replace(month=next_run.month + 1)
                return next_run
            return None

        elif self.schedule_type == ScheduleType.CRON:
            # Simplified cron parsing (minute hour day month weekday)
            if self.cron_expression:
                return self._parse_cron_next(now)
            return None

        return None

    def _parse_cron_next(self, after: datetime) -> Optional[datetime]:
        """Parse simplified cron expression."""
        # Very simplified cron: "minute hour day month weekday"
        # Supports: *, specific numbers
        parts = self.cron_expression.split()
        if len(parts) != 5:
            return None

        minute, hour, day, month, weekday = parts

        # Start from next minute
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # Search for next valid time (max 1 year ahead)
        for _ in range(525600):  # Minutes in a year
            if self._cron_match(candidate, minute, hour, day, month, weekday):
                return candidate
            candidate += timedelta(minutes=1)

        return None

    def _cron_match(
        self,
        dt: datetime,
        minute: str,
        hour: str,
        day: str,
        month: str,
        weekday: str,
    ) -> bool:
        """Check if datetime matches cron pattern."""
        def match_field(value: int, pattern: str) -> bool:
            if pattern == "*":
                return True
            if pattern.isdigit():
                return value == int(pattern)
            if "/" in pattern:
                _, step = pattern.split("/")
                return value % int(step) == 0
            if "-" in pattern:
                start, end = map(int, pattern.split("-"))
                return start <= value <= end
            if "," in pattern:
                return value in map(int, pattern.split(","))
            return False

        return (
            match_field(dt.minute, minute) and
            match_field(dt.hour, hour) and
            match_field(dt.day, day) and
            match_field(dt.month, month) and
            match_field(dt.weekday(), weekday)
        )


@dataclass
class ScheduledJob:
    """
    مهمة مجدولة.

    Scheduled Notification Job.
    """

    job_id: str
    notification: Notification
    schedule: Schedule
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    run_count: int = 0
    error: Optional[str] = None

    # Callback for when notification is sent
    callback: Optional[Callable[[Notification, bool], Any]] = field(
        default=None, compare=False, repr=False
    )

    def __post_init__(self):
        if not self.next_run:
            self.next_run = self.schedule.next_run_time()
            if self.next_run:
                self.status = JobStatus.SCHEDULED

    def __lt__(self, other: "ScheduledJob") -> bool:
        """For heap ordering by next_run time."""
        if self.next_run is None:
            return False
        if other.next_run is None:
            return True
        return self.next_run < other.next_run


class NotificationScheduler:
    """
    مجدول الإشعارات.

    Notification Scheduler with Persistence.

    Usage:
        scheduler = NotificationScheduler()
        await scheduler.start()

        # Schedule one-time notification
        job = await scheduler.schedule_once(
            notification,
            run_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        # Schedule recurring notification
        job = await scheduler.schedule_interval(
            notification,
            interval_seconds=3600,  # Every hour
        )

        # Schedule daily notification
        job = await scheduler.schedule_daily(
            notification,
            time_of_day="09:00",
        )

        # Cancel job
        await scheduler.cancel(job.job_id)

        await scheduler.stop()
    """

    def __init__(
        self,
        send_callback: Optional[Callable[[Notification], Any]] = None,
        persistence_path: Optional[Path] = None,
        max_concurrent: int = 10,
    ):
        self.send_callback = send_callback
        self.persistence_path = persistence_path
        self.max_concurrent = max_concurrent

        self._jobs: Dict[str, ScheduledJob] = {}
        self._heap: List[ScheduledJob] = []
        self._lock = asyncio.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._db: Optional[sqlite3.Connection] = None

        if persistence_path:
            self._init_persistence()

    def _init_persistence(self) -> None:
        """Initialize persistence database."""
        if not self.persistence_path:
            return

        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.persistence_path))

        self._db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id TEXT PRIMARY KEY,
                notification_data TEXT,
                schedule_data TEXT,
                status TEXT,
                next_run TEXT,
                last_run TEXT,
                run_count INTEGER,
                created_at TEXT,
                error TEXT
            )
        """)
        self._db.commit()

        # Load existing jobs
        self._load_jobs()

    def _load_jobs(self) -> None:
        """Load jobs from database."""
        if not self._db:
            return

        cursor = self._db.execute(
            "SELECT * FROM scheduled_jobs WHERE status NOT IN ('completed', 'cancelled')"
        )

        for row in cursor.fetchall():
            try:
                notification_data = json.loads(row[1])
                schedule_data = json.loads(row[2])

                notification = Notification.from_dict(notification_data)
                schedule = Schedule(
                    schedule_type=ScheduleType(schedule_data["schedule_type"]),
                    run_at=datetime.fromisoformat(schedule_data["run_at"]) if schedule_data.get("run_at") else None,
                    interval_seconds=schedule_data.get("interval_seconds"),
                    time_of_day=schedule_data.get("time_of_day"),
                    day_of_week=schedule_data.get("day_of_week"),
                    day_of_month=schedule_data.get("day_of_month"),
                    cron_expression=schedule_data.get("cron_expression"),
                    max_runs=schedule_data.get("max_runs"),
                )

                job = ScheduledJob(
                    job_id=row[0],
                    notification=notification,
                    schedule=schedule,
                    status=JobStatus(row[3]),
                    next_run=datetime.fromisoformat(row[4]) if row[4] else None,
                    last_run=datetime.fromisoformat(row[5]) if row[5] else None,
                    run_count=row[6] or 0,
                    created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(timezone.utc),
                    error=row[8],
                )

                self._jobs[job.job_id] = job
                if job.next_run:
                    heapq.heappush(self._heap, job)

            except Exception as e:
                logger.error(f"Failed to load job {row[0]}: {e}")

        logger.info(f"Loaded {len(self._jobs)} scheduled jobs")

    def _save_job(self, job: ScheduledJob) -> None:
        """Save job to database."""
        if not self._db:
            return

        schedule_data = {
            "schedule_type": job.schedule.schedule_type.value,
            "run_at": job.schedule.run_at.isoformat() if job.schedule.run_at else None,
            "interval_seconds": job.schedule.interval_seconds,
            "time_of_day": job.schedule.time_of_day,
            "day_of_week": job.schedule.day_of_week,
            "day_of_month": job.schedule.day_of_month,
            "cron_expression": job.schedule.cron_expression,
            "max_runs": job.schedule.max_runs,
        }

        self._db.execute(
            """
            INSERT OR REPLACE INTO scheduled_jobs
            (id, notification_data, schedule_data, status, next_run, last_run, run_count, created_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id,
                json.dumps(job.notification.to_dict()),
                json.dumps(schedule_data),
                job.status.value,
                job.next_run.isoformat() if job.next_run else None,
                job.last_run.isoformat() if job.last_run else None,
                job.run_count,
                job.created_at.isoformat(),
                job.error,
            ),
        )
        self._db.commit()

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Notification scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Notification scheduler stopped")

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._process_due_jobs()
                await asyncio.sleep(1)  # Check every second
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(5)

    async def _process_due_jobs(self) -> None:
        """Process jobs that are due."""
        now = datetime.now(timezone.utc)

        async with self._lock:
            while self._heap and self._heap[0].next_run and self._heap[0].next_run <= now:
                job = heapq.heappop(self._heap)

                if job.status == JobStatus.PAUSED:
                    continue

                if job.status == JobStatus.CANCELLED:
                    continue

                # Execute job
                asyncio.create_task(self._execute_job(job))

    async def _execute_job(self, job: ScheduledJob) -> None:
        """Execute a scheduled job."""
        async with self._semaphore:
            job.status = JobStatus.RUNNING

            try:
                # Send notification
                if self.send_callback:
                    result = self.send_callback(job.notification)
                    if asyncio.iscoroutine(result):
                        await result
                    success = True
                else:
                    # Log if no callback
                    logger.info(f"Scheduled notification: {job.notification.title}")
                    success = True

                job.last_run = datetime.now(timezone.utc)
                job.run_count += 1
                job.error = None

                # Call job callback if present
                if job.callback:
                    cb_result = job.callback(job.notification, success)
                    if asyncio.iscoroutine(cb_result):
                        await cb_result

            except Exception as e:
                logger.error(f"Job execution failed: {e}")
                job.error = str(e)
                success = False

            # Schedule next run
            if job.schedule.schedule_type != ScheduleType.ONCE:
                # Check max runs
                if job.schedule.max_runs and job.run_count >= job.schedule.max_runs:
                    job.status = JobStatus.COMPLETED
                # Check end time
                elif job.schedule.end_time and datetime.now(timezone.utc) >= job.schedule.end_time:
                    job.status = JobStatus.COMPLETED
                else:
                    job.next_run = job.schedule.next_run_time(after=job.last_run)
                    if job.next_run:
                        job.status = JobStatus.SCHEDULED
                        async with self._lock:
                            heapq.heappush(self._heap, job)
                    else:
                        job.status = JobStatus.COMPLETED
            else:
                job.status = JobStatus.COMPLETED

            # Persist
            self._save_job(job)

    async def schedule(
        self,
        notification: Notification,
        schedule: Schedule,
        callback: Optional[Callable[[Notification, bool], Any]] = None,
    ) -> ScheduledJob:
        """
        Schedule a notification.

        Args:
            notification: The notification to send
            schedule: Schedule configuration
            callback: Optional callback when notification is sent

        Returns:
            The scheduled job
        """
        job = ScheduledJob(
            job_id=str(uuid.uuid4()),
            notification=notification,
            schedule=schedule,
            callback=callback,
        )

        async with self._lock:
            self._jobs[job.job_id] = job
            if job.next_run:
                heapq.heappush(self._heap, job)

        self._save_job(job)
        logger.info(f"Scheduled job {job.job_id} for {job.next_run}")

        return job

    async def schedule_once(
        self,
        notification: Notification,
        run_at: datetime,
        callback: Optional[Callable[[Notification, bool], Any]] = None,
    ) -> ScheduledJob:
        """Schedule a one-time notification."""
        schedule = Schedule(
            schedule_type=ScheduleType.ONCE,
            run_at=run_at,
        )
        return await self.schedule(notification, schedule, callback)

    async def schedule_interval(
        self,
        notification: Notification,
        interval_seconds: int,
        max_runs: Optional[int] = None,
        end_time: Optional[datetime] = None,
        callback: Optional[Callable[[Notification, bool], Any]] = None,
    ) -> ScheduledJob:
        """Schedule a recurring notification at fixed intervals."""
        schedule = Schedule(
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=interval_seconds,
            max_runs=max_runs,
            end_time=end_time,
        )
        return await self.schedule(notification, schedule, callback)

    async def schedule_daily(
        self,
        notification: Notification,
        time_of_day: str,
        max_runs: Optional[int] = None,
        callback: Optional[Callable[[Notification, bool], Any]] = None,
    ) -> ScheduledJob:
        """Schedule a daily notification."""
        schedule = Schedule(
            schedule_type=ScheduleType.DAILY,
            time_of_day=time_of_day,
            max_runs=max_runs,
        )
        return await self.schedule(notification, schedule, callback)

    async def schedule_weekly(
        self,
        notification: Notification,
        day_of_week: int,
        time_of_day: str,
        callback: Optional[Callable[[Notification, bool], Any]] = None,
    ) -> ScheduledJob:
        """Schedule a weekly notification."""
        schedule = Schedule(
            schedule_type=ScheduleType.WEEKLY,
            day_of_week=day_of_week,
            time_of_day=time_of_day,
        )
        return await self.schedule(notification, schedule, callback)

    async def schedule_cron(
        self,
        notification: Notification,
        cron_expression: str,
        callback: Optional[Callable[[Notification, bool], Any]] = None,
    ) -> ScheduledJob:
        """Schedule a notification using cron expression."""
        schedule = Schedule(
            schedule_type=ScheduleType.CRON,
            cron_expression=cron_expression,
        )
        return await self.schedule(notification, schedule, callback)

    async def cancel(self, job_id: str) -> bool:
        """Cancel a scheduled job."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False

            job.status = JobStatus.CANCELLED
            self._save_job(job)
            return True

    async def pause(self, job_id: str) -> bool:
        """Pause a scheduled job."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False

            job.status = JobStatus.PAUSED
            self._save_job(job)
            return True

    async def resume(self, job_id: str) -> bool:
        """Resume a paused job."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != JobStatus.PAUSED:
                return False

            job.status = JobStatus.SCHEDULED
            job.next_run = job.schedule.next_run_time()
            if job.next_run:
                heapq.heappush(self._heap, job)
            self._save_job(job)
            return True

    async def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """Get a scheduled job."""
        return self._jobs.get(job_id)

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
    ) -> List[ScheduledJob]:
        """List all scheduled jobs."""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: j.next_run or datetime.max)

    async def get_pending_count(self) -> int:
        """Get count of pending jobs."""
        return sum(
            1 for j in self._jobs.values()
            if j.status in (JobStatus.PENDING, JobStatus.SCHEDULED)
        )

    @property
    def stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        by_status = {}
        for job in self._jobs.values():
            by_status[job.status.value] = by_status.get(job.status.value, 0) + 1

        return {
            "total_jobs": len(self._jobs),
            "pending_jobs": len(self._heap),
            "by_status": by_status,
            "running": self._running,
        }

    def close(self) -> None:
        """Close resources."""
        if self._db:
            self._db.close()
            self._db = None
