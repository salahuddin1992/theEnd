"""
Database Persistence - تخزين قاعدة البيانات
============================================

تخزين حالة الكلاستر في قاعدة بيانات:
- Workers
- Jobs
- Leases
- Events

يدعم:
- SQLite (للتطوير والاستخدام الخفيف)
- PostgreSQL (للإنتاج) - مستقبلاً
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiosqlite

from distributed_cluster.models.events import Event, EventType
from distributed_cluster.models.job import Job, JobResult, JobStatus, JobSubmission
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerInfo, WorkerStatus


@dataclass
class DatabaseConfig:
    """إعدادات قاعدة البيانات."""

    type: str = "sqlite"  # sqlite, postgresql
    path: str = "./cluster.db"  # for SQLite
    host: str = "localhost"  # for PostgreSQL
    port: int = 5432
    database: str = "nebula"
    user: str = ""
    password: str = ""


class Database(ABC):
    """واجهة قاعدة البيانات."""

    @abstractmethod
    async def initialize(self) -> None:
        """تهيئة قاعدة البيانات وإنشاء الجداول."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """إغلاق الاتصال."""
        pass

    # Workers
    @abstractmethod
    async def save_worker(self, worker: WorkerInfo) -> None:
        pass

    @abstractmethod
    async def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        pass

    @abstractmethod
    async def get_all_workers(self) -> List[WorkerInfo]:
        pass

    @abstractmethod
    async def delete_worker(self, worker_id: str) -> bool:
        pass

    @abstractmethod
    async def update_worker_heartbeat(self, worker_id: str, last_heartbeat: datetime, status: WorkerStatus) -> bool:
        pass

    # Jobs
    @abstractmethod
    async def save_job(self, job: Job) -> None:
        pass

    @abstractmethod
    async def get_job(self, job_id: str) -> Optional[Job]:
        pass

    @abstractmethod
    async def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        pass

    @abstractmethod
    async def get_jobs_by_worker(self, worker_id: str) -> List[Job]:
        pass

    @abstractmethod
    async def update_job_status(self, job_id: str, status: JobStatus, **kwargs) -> bool:
        pass

    # Events
    @abstractmethod
    async def save_event(self, event: Event) -> None:
        pass

    @abstractmethod
    async def get_recent_events(self, limit: int = 100) -> List[Event]:
        pass


class SQLiteDatabase(Database):
    """
    تخزين SQLite.

    مناسب للتطوير والاستخدام الخفيف (< 1000 workers/jobs).
    """

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.db_path = Path(config.path)
        self._connection: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """تهيئة قاعدة البيانات."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row

        await self._create_tables()

    async def _create_tables(self) -> None:
        """إنشاء الجداول."""
        await self._connection.executescript(
            """
            -- Workers table
            CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready',
                total_resources TEXT NOT NULL,  -- JSON
                available_resources TEXT NOT NULL,  -- JSON
                tags TEXT NOT NULL DEFAULT '[]',  -- JSON array
                labels TEXT NOT NULL DEFAULT '{}',  -- JSON object
                platform TEXT DEFAULT 'linux',
                docker_available INTEGER DEFAULT 0,
                gpu_driver_version TEXT,
                registered_at TEXT NOT NULL,
                last_heartbeat TEXT,
                active_jobs TEXT NOT NULL DEFAULT '[]',  -- JSON array
                completed_jobs_count INTEGER DEFAULT 0,
                failed_jobs_count INTEGER DEFAULT 0
            );

            -- Jobs table
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                submission TEXT NOT NULL,  -- JSON
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,  -- JSON, nullable
                assigned_worker TEXT,
                lease_id TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                scheduled_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                execution_history TEXT NOT NULL DEFAULT '[]'  -- JSON array
            );

            -- Events table
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT,
                data TEXT NOT NULL DEFAULT '{}',  -- JSON
                message TEXT,
                job_id TEXT,
                worker_id TEXT
            );

            -- Leases table
            CREATE TABLE IF NOT EXISTS leases (
                lease_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                expires_at TEXT,
                last_renewed_at TEXT,
                released_at TEXT,
                renewal_count INTEGER DEFAULT 0
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_worker ON jobs(assigned_worker);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_leases_job ON leases(job_id);
            CREATE INDEX IF NOT EXISTS idx_leases_worker ON leases(worker_id);
        """
        )
        await self._connection.commit()

    async def close(self) -> None:
        """إغلاق الاتصال."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    # ==================== Workers ====================

    async def save_worker(self, worker: WorkerInfo) -> None:
        """حفظ worker."""
        await self._connection.execute(
            """
            INSERT OR REPLACE INTO workers (
                worker_id, hostname, ip_address, port, status,
                total_resources, available_resources, tags, labels,
                platform, docker_available, gpu_driver_version,
                registered_at, last_heartbeat, active_jobs,
                completed_jobs_count, failed_jobs_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                worker.worker_id,
                worker.hostname,
                worker.ip_address,
                worker.port,
                worker.status.value,
                json.dumps(worker.total_resources.to_dict()),
                json.dumps(worker.available_resources.to_dict()),
                json.dumps(worker.tags),
                json.dumps(worker.labels),
                worker.platform,
                1 if worker.docker_available else 0,
                worker.gpu_driver_version,
                worker.registered_at.isoformat(),
                worker.last_heartbeat.isoformat() if worker.last_heartbeat else None,
                json.dumps(worker.active_jobs),
                worker.completed_jobs_count,
                worker.failed_jobs_count,
            ),
        )
        await self._connection.commit()

    async def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """الحصول على worker."""
        cursor = await self._connection.execute("SELECT * FROM workers WHERE worker_id = ?", (worker_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_worker(row)

    async def get_all_workers(self) -> List[WorkerInfo]:
        """الحصول على كل workers."""
        cursor = await self._connection.execute("SELECT * FROM workers")
        rows = await cursor.fetchall()
        return [self._row_to_worker(row) for row in rows]

    async def delete_worker(self, worker_id: str) -> bool:
        """حذف worker."""
        cursor = await self._connection.execute("DELETE FROM workers WHERE worker_id = ?", (worker_id,))
        await self._connection.commit()
        return cursor.rowcount > 0

    async def update_worker_heartbeat(self, worker_id: str, last_heartbeat: datetime, status: WorkerStatus) -> bool:
        """تحديث heartbeat."""
        cursor = await self._connection.execute(
            """
            UPDATE workers
            SET last_heartbeat = ?, status = ?
            WHERE worker_id = ?
        """,
            (last_heartbeat.isoformat(), status.value, worker_id),
        )
        await self._connection.commit()
        return cursor.rowcount > 0

    def _row_to_worker(self, row) -> WorkerInfo:
        """تحويل row إلى WorkerInfo."""
        return WorkerInfo(
            worker_id=row["worker_id"],
            hostname=row["hostname"],
            ip_address=row["ip_address"],
            port=row["port"],
            status=WorkerStatus(row["status"]),
            total_resources=ResourceSpec.from_dict(json.loads(row["total_resources"])),
            available_resources=ResourceSpec.from_dict(json.loads(row["available_resources"])),
            tags=json.loads(row["tags"]),
            labels=json.loads(row["labels"]),
            platform=row["platform"],
            docker_available=bool(row["docker_available"]),
            gpu_driver_version=row["gpu_driver_version"],
            registered_at=datetime.fromisoformat(row["registered_at"]),
            last_heartbeat=datetime.fromisoformat(row["last_heartbeat"]) if row["last_heartbeat"] else None,
            active_jobs=json.loads(row["active_jobs"]),
            completed_jobs_count=row["completed_jobs_count"],
            failed_jobs_count=row["failed_jobs_count"],
        )

    # ==================== Jobs ====================

    async def save_job(self, job: Job) -> None:
        """حفظ job."""
        await self._connection.execute(
            """
            INSERT OR REPLACE INTO jobs (
                job_id, submission, status, result, assigned_worker,
                lease_id, retry_count, created_at, scheduled_at,
                started_at, completed_at, execution_history
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                job.job_id,
                json.dumps(job.submission.to_dict()),
                job.status.value,
                json.dumps(job.result.to_dict()) if job.result else None,
                job.assigned_worker,
                job.lease_id,
                job.retry_count,
                job.created_at.isoformat(),
                job.scheduled_at.isoformat() if job.scheduled_at else None,
                job.started_at.isoformat() if job.started_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
                json.dumps(job.execution_history),
            ),
        )
        await self._connection.commit()

    async def get_job(self, job_id: str) -> Optional[Job]:
        """الحصول على job."""
        cursor = await self._connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_job(row)

    async def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        """الحصول على jobs بحالة معينة."""
        cursor = await self._connection.execute("SELECT * FROM jobs WHERE status = ?", (status.value,))
        rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows]

    async def get_jobs_by_worker(self, worker_id: str) -> List[Job]:
        """الحصول على jobs معينة لـ worker."""
        cursor = await self._connection.execute("SELECT * FROM jobs WHERE assigned_worker = ?", (worker_id,))
        rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows]

    async def update_job_status(self, job_id: str, status: JobStatus, **kwargs) -> bool:
        """تحديث حالة job."""
        updates = ["status = ?"]
        params = [status.value]

        for key, value in kwargs.items():
            if value is not None:
                if key in ("scheduled_at", "started_at", "completed_at"):
                    value = value.isoformat() if isinstance(value, datetime) else value
                elif key == "result":
                    value = json.dumps(value.to_dict()) if hasattr(value, "to_dict") else json.dumps(value)
                updates.append(f"{key} = ?")
                params.append(value)

        params.append(job_id)

        cursor = await self._connection.execute(
            f"""
            UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?
        """,
            params,
        )
        await self._connection.commit()
        return cursor.rowcount > 0

    def _row_to_job(self, row) -> Job:
        """تحويل row إلى Job."""
        submission_dict = json.loads(row["submission"])
        submission = JobSubmission.from_dict(submission_dict)

        result = None
        if row["result"]:
            result_dict = json.loads(row["result"])
            result = JobResult(
                exit_code=result_dict["exit_code"],
                stdout=result_dict.get("stdout", ""),
                stderr=result_dict.get("stderr", ""),
                execution_time_seconds=result_dict.get("execution_time_seconds", 0),
                peak_memory_mb=result_dict.get("peak_memory_mb", 0),
                error_message=result_dict.get("error_message"),
            )

        return Job(
            job_id=row["job_id"],
            submission=submission,
            status=JobStatus(row["status"]),
            result=result,
            assigned_worker=row["assigned_worker"],
            lease_id=row["lease_id"],
            retry_count=row["retry_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            scheduled_at=datetime.fromisoformat(row["scheduled_at"]) if row["scheduled_at"] else None,
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            execution_history=json.loads(row["execution_history"]),
        )

    # ==================== Events ====================

    async def save_event(self, event: Event) -> None:
        """حفظ event."""
        await self._connection.execute(
            """
            INSERT INTO events (
                event_type, timestamp, source, data, message, job_id, worker_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                event.event_type.value,
                event.timestamp.isoformat(),
                event.source,
                json.dumps(event.data),
                event.message,
                event.job_id,
                event.worker_id,
            ),
        )
        await self._connection.commit()

    async def get_recent_events(self, limit: int = 100) -> List[Event]:
        """الحصول على آخر الأحداث."""
        cursor = await self._connection.execute(
            """
            SELECT * FROM events ORDER BY timestamp DESC LIMIT ?
        """,
            (limit,),
        )
        rows = await cursor.fetchall()

        events = []
        for row in rows:
            events.append(
                Event(
                    event_type=EventType(row["event_type"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    source=row["source"],
                    data=json.loads(row["data"]),
                    message=row["message"],
                    job_id=row["job_id"],
                    worker_id=row["worker_id"],
                )
            )
        return events


async def create_database(config: DatabaseConfig) -> Database:
    """إنشاء قاعدة بيانات حسب النوع."""
    if config.type == "sqlite":
        db = SQLiteDatabase(config)
    else:
        raise ValueError(f"Unsupported database type: {config.type}")

    await db.initialize()
    return db
