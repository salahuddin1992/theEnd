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
- PostgreSQL (للإنتاج مع connection pooling)
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Tuple

import aiosqlite

from distributed_cluster.models.events import Event, EventType
from distributed_cluster.models.job import Job, JobResult, JobStatus, JobSubmission
from distributed_cluster.models.lease import Lease, LeaseState
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerInfo, WorkerStatus

logger = logging.getLogger(__name__)


# ==================== Configuration ====================


@dataclass
class DatabaseConfig:
    """إعدادات قاعدة البيانات."""

    type: str = "sqlite"  # sqlite, postgresql
    path: str = "./cluster.db"  # for SQLite

    # PostgreSQL settings
    host: str = "localhost"
    port: int = 5432
    database: str = "nebula"
    user: str = ""
    password: str = ""

    # Connection pool settings
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    pool_recycle: int = 3600  # Recycle connections after 1 hour

    # SSL/TLS settings
    ssl_mode: str = "prefer"  # disable, allow, prefer, require, verify-ca, verify-full
    ssl_ca_file: Optional[str] = None
    ssl_cert_file: Optional[str] = None
    ssl_key_file: Optional[str] = None

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """تحميل الإعدادات من متغيرات البيئة."""
        import os

        return cls(
            type=os.getenv("DB_TYPE", "sqlite"),
            path=os.getenv("DB_PATH", "./cluster.db"),
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_DATABASE", "nebula"),
            user=os.getenv("DB_USER", ""),
            password=os.getenv("DB_PASSWORD", ""),
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            ssl_mode=os.getenv("DB_SSL_MODE", "prefer"),
        )

    def get_connection_string(self) -> str:
        """إنشاء connection string للـ PostgreSQL."""
        if self.type == "sqlite":
            return f"sqlite:///{self.path}"

        auth = f"{self.user}:{self.password}@" if self.user else ""
        return f"postgresql://{auth}{self.host}:{self.port}/{self.database}"


# ==================== Exceptions ====================


class DatabaseError(Exception):
    """خطأ عام في قاعدة البيانات."""

    pass


class ConnectionError(DatabaseError):
    """خطأ في الاتصال."""

    pass


class TransactionError(DatabaseError):
    """خطأ في الـ transaction."""

    pass


class NotFoundError(DatabaseError):
    """السجل غير موجود."""

    pass


# ==================== Abstract Database Interface ====================


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

    @abstractmethod
    async def health_check(self) -> bool:
        """فحص صحة الاتصال."""
        pass

    # ==================== Transaction Support ====================

    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """بدء transaction."""
        yield

    # ==================== Workers ====================

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
    async def update_worker_heartbeat(
        self, worker_id: str, last_heartbeat: datetime, status: WorkerStatus
    ) -> bool:
        pass

    # ==================== Jobs ====================

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

    @abstractmethod
    async def get_jobs_count_by_status(self) -> Dict[str, int]:
        """إحصائيات المهام حسب الحالة."""
        pass

    @abstractmethod
    async def get_jobs_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
        status: Optional[JobStatus] = None,
        worker_id: Optional[str] = None,
    ) -> Tuple[List[Job], int]:
        """الحصول على jobs مع pagination."""
        pass

    # ==================== Leases ====================

    @abstractmethod
    async def save_lease(self, lease: Lease) -> None:
        """حفظ lease."""
        pass

    @abstractmethod
    async def get_lease(self, lease_id: str) -> Optional[Lease]:
        """الحصول على lease."""
        pass

    @abstractmethod
    async def get_lease_by_job(self, job_id: str) -> Optional[Lease]:
        """الحصول على lease لـ job معين."""
        pass

    @abstractmethod
    async def get_leases_by_worker(self, worker_id: str) -> List[Lease]:
        """الحصول على جميع leases لـ worker."""
        pass

    @abstractmethod
    async def get_active_leases(self) -> List[Lease]:
        """الحصول على جميع الـ leases الفعّالة."""
        pass

    @abstractmethod
    async def update_lease_state(self, lease_id: str, state: LeaseState) -> bool:
        """تحديث حالة lease."""
        pass

    @abstractmethod
    async def update_lease_expiry(self, lease_id: str, expires_at: datetime, renewal_count: int) -> bool:
        """تجديد lease."""
        pass

    @abstractmethod
    async def delete_old_leases(self, before: datetime) -> int:
        """حذف leases قديمة."""
        pass

    # ==================== Events ====================

    @abstractmethod
    async def save_event(self, event: Event) -> None:
        pass

    @abstractmethod
    async def get_recent_events(self, limit: int = 100) -> List[Event]:
        pass

    @abstractmethod
    async def get_events_by_type(self, event_type: EventType, limit: int = 100) -> List[Event]:
        """الحصول على events بنوع معين."""
        pass

    @abstractmethod
    async def get_events_by_job(self, job_id: str) -> List[Event]:
        """الحصول على events لـ job معين."""
        pass

    @abstractmethod
    async def delete_old_events(self, before: datetime) -> int:
        """حذف events قديمة."""
        pass

    # ==================== Cleanup ====================

    @abstractmethod
    async def cleanup_old_data(self, retention_days: int = 30) -> Dict[str, int]:
        """تنظيف البيانات القديمة."""
        pass


# ==================== SQLite Implementation ====================


class SQLiteDatabase(Database):
    """
    تخزين SQLite.

    مناسب للتطوير والاستخدام الخفيف (< 1000 workers/jobs).
    """

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.db_path = Path(config.path)
        self._connection: Optional[aiosqlite.Connection] = None
        self._in_transaction = False

    async def initialize(self) -> None:
        """تهيئة قاعدة البيانات."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row

        # Enable foreign keys
        await self._connection.execute("PRAGMA foreign_keys = ON")

        await self._create_tables()
        logger.info(f"SQLite database initialized at {self.db_path}")

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
                renewal_count INTEGER DEFAULT 0,
                idempotency_key TEXT
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

            -- Schema version table for migrations
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                description TEXT
            );

            -- Indexes for workers
            CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
            CREATE INDEX IF NOT EXISTS idx_workers_last_heartbeat ON workers(last_heartbeat);

            -- Indexes for jobs
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_worker ON jobs(assigned_worker);
            CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
            CREATE INDEX IF NOT EXISTS idx_jobs_lease ON jobs(lease_id);

            -- Indexes for leases
            CREATE INDEX IF NOT EXISTS idx_leases_job ON leases(job_id);
            CREATE INDEX IF NOT EXISTS idx_leases_worker ON leases(worker_id);
            CREATE INDEX IF NOT EXISTS idx_leases_state ON leases(state);
            CREATE INDEX IF NOT EXISTS idx_leases_expires_at ON leases(expires_at);

            -- Indexes for events
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
            CREATE INDEX IF NOT EXISTS idx_events_worker ON events(worker_id);
        """
        )
        await self._connection.commit()

        # Initialize schema version if empty
        cursor = await self._connection.execute("SELECT COUNT(*) FROM schema_version")
        count = (await cursor.fetchone())[0]
        if count == 0:
            await self._connection.execute(
                "INSERT INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
                (1, datetime.utcnow().isoformat(), "Initial schema"),
            )
            await self._connection.commit()

    async def close(self) -> None:
        """إغلاق الاتصال."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("SQLite database connection closed")

    async def health_check(self) -> bool:
        """فحص صحة الاتصال."""
        try:
            cursor = await self._connection.execute("SELECT 1")
            await cursor.fetchone()
            return True
        except Exception:
            return False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """بدء transaction."""
        if self._in_transaction:
            # Nested transaction - just yield
            yield
            return

        self._in_transaction = True
        try:
            await self._connection.execute("BEGIN TRANSACTION")
            yield
            await self._connection.commit()
        except Exception as e:
            await self._connection.rollback()
            raise TransactionError(f"Transaction failed: {e}") from e
        finally:
            self._in_transaction = False

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
        if not self._in_transaction:
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
        cursor = await self._connection.execute("SELECT * FROM workers ORDER BY registered_at DESC")
        rows = await cursor.fetchall()
        return [self._row_to_worker(row) for row in rows]

    async def delete_worker(self, worker_id: str) -> bool:
        """حذف worker."""
        cursor = await self._connection.execute("DELETE FROM workers WHERE worker_id = ?", (worker_id,))
        if not self._in_transaction:
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
        if not self._in_transaction:
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
        if not self._in_transaction:
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
        cursor = await self._connection.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC", (status.value,)
        )
        rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows]

    async def get_jobs_by_worker(self, worker_id: str) -> List[Job]:
        """الحصول على jobs معينة لـ worker."""
        cursor = await self._connection.execute(
            "SELECT * FROM jobs WHERE assigned_worker = ? ORDER BY created_at DESC", (worker_id,)
        )
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
        if not self._in_transaction:
            await self._connection.commit()
        return cursor.rowcount > 0

    async def get_jobs_count_by_status(self) -> Dict[str, int]:
        """إحصائيات المهام حسب الحالة."""
        cursor = await self._connection.execute(
            "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
        )
        rows = await cursor.fetchall()
        return {row["status"]: row["count"] for row in rows}

    async def get_jobs_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
        status: Optional[JobStatus] = None,
        worker_id: Optional[str] = None,
    ) -> Tuple[List[Job], int]:
        """الحصول على jobs مع pagination."""
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if worker_id:
            conditions.append("assigned_worker = ?")
            params.append(worker_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Get total count
        count_cursor = await self._connection.execute(
            f"SELECT COUNT(*) FROM jobs {where_clause}", params
        )
        total = (await count_cursor.fetchone())[0]

        # Get paginated results
        params.extend([limit, offset])
        cursor = await self._connection.execute(
            f"SELECT * FROM jobs {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        )
        rows = await cursor.fetchall()

        return [self._row_to_job(row) for row in rows], total

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

    # ==================== Leases ====================

    async def save_lease(self, lease: Lease) -> None:
        """حفظ lease."""
        await self._connection.execute(
            """
            INSERT OR REPLACE INTO leases (
                lease_id, job_id, worker_id, state, created_at,
                expires_at, last_renewed_at, released_at,
                renewal_count, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                lease.lease_id,
                lease.job_id,
                lease.worker_id,
                lease.state.value,
                lease.created_at.isoformat(),
                lease.expires_at.isoformat() if lease.expires_at else None,
                lease.last_renewed_at.isoformat() if lease.last_renewed_at else None,
                lease.released_at.isoformat() if lease.released_at else None,
                lease.renewal_count,
                lease.idempotency_key,
            ),
        )
        if not self._in_transaction:
            await self._connection.commit()

    async def get_lease(self, lease_id: str) -> Optional[Lease]:
        """الحصول على lease."""
        cursor = await self._connection.execute(
            "SELECT * FROM leases WHERE lease_id = ?", (lease_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_lease(row)

    async def get_lease_by_job(self, job_id: str) -> Optional[Lease]:
        """الحصول على lease لـ job معين."""
        cursor = await self._connection.execute(
            "SELECT * FROM leases WHERE job_id = ? AND state = 'active' ORDER BY created_at DESC LIMIT 1",
            (job_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_lease(row)

    async def get_leases_by_worker(self, worker_id: str) -> List[Lease]:
        """الحصول على جميع leases لـ worker."""
        cursor = await self._connection.execute(
            "SELECT * FROM leases WHERE worker_id = ? ORDER BY created_at DESC",
            (worker_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_lease(row) for row in rows]

    async def get_active_leases(self) -> List[Lease]:
        """الحصول على جميع الـ leases الفعّالة."""
        cursor = await self._connection.execute(
            "SELECT * FROM leases WHERE state = 'active' ORDER BY expires_at ASC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_lease(row) for row in rows]

    async def update_lease_state(self, lease_id: str, state: LeaseState) -> bool:
        """تحديث حالة lease."""
        released_at = datetime.utcnow().isoformat() if state in (LeaseState.RELEASED, LeaseState.REVOKED) else None

        cursor = await self._connection.execute(
            """
            UPDATE leases SET state = ?, released_at = COALESCE(?, released_at)
            WHERE lease_id = ?
        """,
            (state.value, released_at, lease_id),
        )
        if not self._in_transaction:
            await self._connection.commit()
        return cursor.rowcount > 0

    async def update_lease_expiry(self, lease_id: str, expires_at: datetime, renewal_count: int) -> bool:
        """تجديد lease."""
        cursor = await self._connection.execute(
            """
            UPDATE leases
            SET expires_at = ?, last_renewed_at = ?, renewal_count = ?
            WHERE lease_id = ? AND state = 'active'
        """,
            (expires_at.isoformat(), datetime.utcnow().isoformat(), renewal_count, lease_id),
        )
        if not self._in_transaction:
            await self._connection.commit()
        return cursor.rowcount > 0

    async def delete_old_leases(self, before: datetime) -> int:
        """حذف leases قديمة."""
        cursor = await self._connection.execute(
            """
            DELETE FROM leases
            WHERE state != 'active' AND created_at < ?
        """,
            (before.isoformat(),),
        )
        if not self._in_transaction:
            await self._connection.commit()
        return cursor.rowcount

    def _row_to_lease(self, row) -> Lease:
        """تحويل row إلى Lease."""
        return Lease(
            lease_id=row["lease_id"],
            job_id=row["job_id"],
            worker_id=row["worker_id"],
            state=LeaseState(row["state"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            last_renewed_at=datetime.fromisoformat(row["last_renewed_at"]) if row["last_renewed_at"] else None,
            released_at=datetime.fromisoformat(row["released_at"]) if row["released_at"] else None,
            renewal_count=row["renewal_count"],
            idempotency_key=row["idempotency_key"],
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
        if not self._in_transaction:
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
        return [self._row_to_event(row) for row in rows]

    async def get_events_by_type(self, event_type: EventType, limit: int = 100) -> List[Event]:
        """الحصول على events بنوع معين."""
        cursor = await self._connection.execute(
            """
            SELECT * FROM events WHERE event_type = ?
            ORDER BY timestamp DESC LIMIT ?
        """,
            (event_type.value, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    async def get_events_by_job(self, job_id: str) -> List[Event]:
        """الحصول على events لـ job معين."""
        cursor = await self._connection.execute(
            """
            SELECT * FROM events WHERE job_id = ?
            ORDER BY timestamp ASC
        """,
            (job_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    async def delete_old_events(self, before: datetime) -> int:
        """حذف events قديمة."""
        cursor = await self._connection.execute(
            "DELETE FROM events WHERE timestamp < ?",
            (before.isoformat(),),
        )
        if not self._in_transaction:
            await self._connection.commit()
        return cursor.rowcount

    def _row_to_event(self, row) -> Event:
        """تحويل row إلى Event."""
        return Event(
            event_type=EventType(row["event_type"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            source=row["source"],
            data=json.loads(row["data"]),
            message=row["message"],
            job_id=row["job_id"],
            worker_id=row["worker_id"],
        )

    # ==================== Cleanup ====================

    async def cleanup_old_data(self, retention_days: int = 30) -> Dict[str, int]:
        """تنظيف البيانات القديمة."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        cutoff_str = cutoff.isoformat()

        results = {}

        async with self.transaction():
            # Delete old completed/failed jobs
            cursor = await self._connection.execute(
                """
                DELETE FROM jobs
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < ?
            """,
                (cutoff_str,),
            )
            results["jobs"] = cursor.rowcount

            # Delete old leases
            results["leases"] = await self.delete_old_leases(cutoff)

            # Delete old events
            results["events"] = await self.delete_old_events(cutoff)

        logger.info(f"Cleanup completed: {results}")
        return results


# ==================== PostgreSQL Implementation ====================


class PostgreSQLDatabase(Database):
    """
    تخزين PostgreSQL مع connection pooling.

    مناسب للإنتاج والاستخدام الكثيف.
    """

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool = None
        self._in_transaction = False

    async def initialize(self) -> None:
        """تهيئة قاعدة البيانات."""
        try:
            import asyncpg
        except ImportError:
            raise ImportError("asyncpg is required for PostgreSQL support. Install with: pip install asyncpg")

        # Create connection pool
        self._pool = await asyncpg.create_pool(
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            user=self.config.user,
            password=self.config.password,
            min_size=2,
            max_size=self.config.pool_size + self.config.max_overflow,
            command_timeout=self.config.pool_timeout,
        )

        await self._create_tables()
        logger.info(f"PostgreSQL database initialized at {self.config.host}:{self.config.port}")

    async def _create_tables(self) -> None:
        """إنشاء الجداول."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                -- Workers table
                CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY,
                    hostname TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready',
                    total_resources JSONB NOT NULL,
                    available_resources JSONB NOT NULL,
                    tags JSONB NOT NULL DEFAULT '[]',
                    labels JSONB NOT NULL DEFAULT '{}',
                    platform TEXT DEFAULT 'linux',
                    docker_available BOOLEAN DEFAULT FALSE,
                    gpu_driver_version TEXT,
                    registered_at TIMESTAMPTZ NOT NULL,
                    last_heartbeat TIMESTAMPTZ,
                    active_jobs JSONB NOT NULL DEFAULT '[]',
                    completed_jobs_count INTEGER DEFAULT 0,
                    failed_jobs_count INTEGER DEFAULT 0
                );

                -- Jobs table
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    submission JSONB NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result JSONB,
                    assigned_worker TEXT,
                    lease_id TEXT,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL,
                    scheduled_at TIMESTAMPTZ,
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    execution_history JSONB NOT NULL DEFAULT '[]'
                );

                -- Leases table
                CREATE TABLE IF NOT EXISTS leases (
                    lease_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'active',
                    created_at TIMESTAMPTZ NOT NULL,
                    expires_at TIMESTAMPTZ,
                    last_renewed_at TIMESTAMPTZ,
                    released_at TIMESTAMPTZ,
                    renewal_count INTEGER DEFAULT 0,
                    idempotency_key TEXT
                );

                -- Events table
                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    source TEXT,
                    data JSONB NOT NULL DEFAULT '{}',
                    message TEXT,
                    job_id TEXT,
                    worker_id TEXT
                );

                -- Schema version table
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL,
                    description TEXT
                );

                -- Indexes
                CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
                CREATE INDEX IF NOT EXISTS idx_workers_last_heartbeat ON workers(last_heartbeat);
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_worker ON jobs(assigned_worker);
                CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
                CREATE INDEX IF NOT EXISTS idx_leases_job ON leases(job_id);
                CREATE INDEX IF NOT EXISTS idx_leases_worker ON leases(worker_id);
                CREATE INDEX IF NOT EXISTS idx_leases_state ON leases(state);
                CREATE INDEX IF NOT EXISTS idx_leases_expires_at ON leases(expires_at);
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
                CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
            """
            )

    async def close(self) -> None:
        """إغلاق connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL connection pool closed")

    async def health_check(self) -> bool:
        """فحص صحة الاتصال."""
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """بدء transaction."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield

    # ==================== Workers ====================

    async def save_worker(self, worker: WorkerInfo) -> None:
        """حفظ worker."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO workers (
                    worker_id, hostname, ip_address, port, status,
                    total_resources, available_resources, tags, labels,
                    platform, docker_available, gpu_driver_version,
                    registered_at, last_heartbeat, active_jobs,
                    completed_jobs_count, failed_jobs_count
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                ON CONFLICT (worker_id) DO UPDATE SET
                    hostname = EXCLUDED.hostname,
                    ip_address = EXCLUDED.ip_address,
                    port = EXCLUDED.port,
                    status = EXCLUDED.status,
                    total_resources = EXCLUDED.total_resources,
                    available_resources = EXCLUDED.available_resources,
                    tags = EXCLUDED.tags,
                    labels = EXCLUDED.labels,
                    platform = EXCLUDED.platform,
                    docker_available = EXCLUDED.docker_available,
                    gpu_driver_version = EXCLUDED.gpu_driver_version,
                    last_heartbeat = EXCLUDED.last_heartbeat,
                    active_jobs = EXCLUDED.active_jobs,
                    completed_jobs_count = EXCLUDED.completed_jobs_count,
                    failed_jobs_count = EXCLUDED.failed_jobs_count
            """,
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
                worker.docker_available,
                worker.gpu_driver_version,
                worker.registered_at,
                worker.last_heartbeat,
                json.dumps(worker.active_jobs),
                worker.completed_jobs_count,
                worker.failed_jobs_count,
            )

    async def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """الحصول على worker."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM workers WHERE worker_id = $1", worker_id)
            if not row:
                return None
            return self._row_to_worker(row)

    async def get_all_workers(self) -> List[WorkerInfo]:
        """الحصول على كل workers."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM workers ORDER BY registered_at DESC")
            return [self._row_to_worker(row) for row in rows]

    async def delete_worker(self, worker_id: str) -> bool:
        """حذف worker."""
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM workers WHERE worker_id = $1", worker_id)
            return result == "DELETE 1"

    async def update_worker_heartbeat(self, worker_id: str, last_heartbeat: datetime, status: WorkerStatus) -> bool:
        """تحديث heartbeat."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE workers SET last_heartbeat = $1, status = $2 WHERE worker_id = $3",
                last_heartbeat,
                status.value,
                worker_id,
            )
            return result == "UPDATE 1"

    def _row_to_worker(self, row) -> WorkerInfo:
        """تحويل row إلى WorkerInfo."""
        total_res = row["total_resources"]
        avail_res = row["available_resources"]
        if isinstance(total_res, str):
            total_res = json.loads(total_res)
        if isinstance(avail_res, str):
            avail_res = json.loads(avail_res)

        tags = row["tags"]
        labels = row["labels"]
        active_jobs = row["active_jobs"]
        if isinstance(tags, str):
            tags = json.loads(tags)
        if isinstance(labels, str):
            labels = json.loads(labels)
        if isinstance(active_jobs, str):
            active_jobs = json.loads(active_jobs)

        return WorkerInfo(
            worker_id=row["worker_id"],
            hostname=row["hostname"],
            ip_address=row["ip_address"],
            port=row["port"],
            status=WorkerStatus(row["status"]),
            total_resources=ResourceSpec.from_dict(total_res),
            available_resources=ResourceSpec.from_dict(avail_res),
            tags=tags,
            labels=labels,
            platform=row["platform"],
            docker_available=row["docker_available"],
            gpu_driver_version=row["gpu_driver_version"],
            registered_at=row["registered_at"],
            last_heartbeat=row["last_heartbeat"],
            active_jobs=active_jobs,
            completed_jobs_count=row["completed_jobs_count"],
            failed_jobs_count=row["failed_jobs_count"],
        )

    # ==================== Jobs ====================

    async def save_job(self, job: Job) -> None:
        """حفظ job."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO jobs (
                    job_id, submission, status, result, assigned_worker,
                    lease_id, retry_count, created_at, scheduled_at,
                    started_at, completed_at, execution_history
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (job_id) DO UPDATE SET
                    submission = EXCLUDED.submission,
                    status = EXCLUDED.status,
                    result = EXCLUDED.result,
                    assigned_worker = EXCLUDED.assigned_worker,
                    lease_id = EXCLUDED.lease_id,
                    retry_count = EXCLUDED.retry_count,
                    scheduled_at = EXCLUDED.scheduled_at,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at,
                    execution_history = EXCLUDED.execution_history
            """,
                job.job_id,
                json.dumps(job.submission.to_dict()),
                job.status.value,
                json.dumps(job.result.to_dict()) if job.result else None,
                job.assigned_worker,
                job.lease_id,
                job.retry_count,
                job.created_at,
                job.scheduled_at,
                job.started_at,
                job.completed_at,
                json.dumps(job.execution_history),
            )

    async def get_job(self, job_id: str) -> Optional[Job]:
        """الحصول على job."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM jobs WHERE job_id = $1", job_id)
            if not row:
                return None
            return self._row_to_job(row)

    async def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        """الحصول على jobs بحالة معينة."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM jobs WHERE status = $1 ORDER BY created_at DESC",
                status.value,
            )
            return [self._row_to_job(row) for row in rows]

    async def get_jobs_by_worker(self, worker_id: str) -> List[Job]:
        """الحصول على jobs لـ worker."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM jobs WHERE assigned_worker = $1 ORDER BY created_at DESC",
                worker_id,
            )
            return [self._row_to_job(row) for row in rows]

    async def update_job_status(self, job_id: str, status: JobStatus, **kwargs) -> bool:
        """تحديث حالة job."""
        updates = ["status = $1"]
        params = [status.value]
        param_idx = 2

        for key, value in kwargs.items():
            if value is not None:
                if key == "result" and hasattr(value, "to_dict"):
                    value = json.dumps(value.to_dict())
                updates.append(f"{key} = ${param_idx}")
                params.append(value)
                param_idx += 1

        params.append(job_id)

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ${param_idx}",
                *params,
            )
            return result == "UPDATE 1"

    async def get_jobs_count_by_status(self) -> Dict[str, int]:
        """إحصائيات المهام."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT status, COUNT(*) as count FROM jobs GROUP BY status")
            return {row["status"]: row["count"] for row in rows}

    async def get_jobs_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
        status: Optional[JobStatus] = None,
        worker_id: Optional[str] = None,
    ) -> Tuple[List[Job], int]:
        """الحصول على jobs مع pagination."""
        conditions = []
        params = []
        param_idx = 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1
        if worker_id:
            conditions.append(f"assigned_worker = ${param_idx}")
            params.append(worker_id)
            param_idx += 1

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        async with self._pool.acquire() as conn:
            # Get total count
            total = await conn.fetchval(f"SELECT COUNT(*) FROM jobs {where_clause}", *params)

            # Get paginated results
            params.extend([limit, offset])
            rows = await conn.fetch(
                f"SELECT * FROM jobs {where_clause} ORDER BY created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}",
                *params,
            )

        return [self._row_to_job(row) for row in rows], total

    def _row_to_job(self, row) -> Job:
        """تحويل row إلى Job."""
        submission = row["submission"]
        if isinstance(submission, str):
            submission = json.loads(submission)
        submission = JobSubmission.from_dict(submission)

        result = None
        if row["result"]:
            result_dict = row["result"]
            if isinstance(result_dict, str):
                result_dict = json.loads(result_dict)
            result = JobResult(
                exit_code=result_dict["exit_code"],
                stdout=result_dict.get("stdout", ""),
                stderr=result_dict.get("stderr", ""),
                execution_time_seconds=result_dict.get("execution_time_seconds", 0),
                peak_memory_mb=result_dict.get("peak_memory_mb", 0),
                error_message=result_dict.get("error_message"),
            )

        execution_history = row["execution_history"]
        if isinstance(execution_history, str):
            execution_history = json.loads(execution_history)

        return Job(
            job_id=row["job_id"],
            submission=submission,
            status=JobStatus(row["status"]),
            result=result,
            assigned_worker=row["assigned_worker"],
            lease_id=row["lease_id"],
            retry_count=row["retry_count"],
            created_at=row["created_at"],
            scheduled_at=row["scheduled_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            execution_history=execution_history,
        )

    # ==================== Leases ====================

    async def save_lease(self, lease: Lease) -> None:
        """حفظ lease."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO leases (
                    lease_id, job_id, worker_id, state, created_at,
                    expires_at, last_renewed_at, released_at,
                    renewal_count, idempotency_key
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (lease_id) DO UPDATE SET
                    state = EXCLUDED.state,
                    expires_at = EXCLUDED.expires_at,
                    last_renewed_at = EXCLUDED.last_renewed_at,
                    released_at = EXCLUDED.released_at,
                    renewal_count = EXCLUDED.renewal_count
            """,
                lease.lease_id,
                lease.job_id,
                lease.worker_id,
                lease.state.value,
                lease.created_at,
                lease.expires_at,
                lease.last_renewed_at,
                lease.released_at,
                lease.renewal_count,
                lease.idempotency_key,
            )

    async def get_lease(self, lease_id: str) -> Optional[Lease]:
        """الحصول على lease."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM leases WHERE lease_id = $1", lease_id)
            if not row:
                return None
            return self._row_to_lease(row)

    async def get_lease_by_job(self, job_id: str) -> Optional[Lease]:
        """الحصول على lease لـ job."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM leases WHERE job_id = $1 AND state = 'active' ORDER BY created_at DESC LIMIT 1",
                job_id,
            )
            if not row:
                return None
            return self._row_to_lease(row)

    async def get_leases_by_worker(self, worker_id: str) -> List[Lease]:
        """الحصول على leases لـ worker."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM leases WHERE worker_id = $1 ORDER BY created_at DESC",
                worker_id,
            )
            return [self._row_to_lease(row) for row in rows]

    async def get_active_leases(self) -> List[Lease]:
        """الحصول على active leases."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM leases WHERE state = 'active' ORDER BY expires_at ASC"
            )
            return [self._row_to_lease(row) for row in rows]

    async def update_lease_state(self, lease_id: str, state: LeaseState) -> bool:
        """تحديث حالة lease."""
        released_at = datetime.utcnow() if state in (LeaseState.RELEASED, LeaseState.REVOKED) else None

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE leases SET state = $1, released_at = COALESCE($2, released_at) WHERE lease_id = $3",
                state.value,
                released_at,
                lease_id,
            )
            return result == "UPDATE 1"

    async def update_lease_expiry(self, lease_id: str, expires_at: datetime, renewal_count: int) -> bool:
        """تجديد lease."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE leases
                SET expires_at = $1, last_renewed_at = $2, renewal_count = $3
                WHERE lease_id = $4 AND state = 'active'
            """,
                expires_at,
                datetime.utcnow(),
                renewal_count,
                lease_id,
            )
            return result == "UPDATE 1"

    async def delete_old_leases(self, before: datetime) -> int:
        """حذف leases قديمة."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM leases WHERE state != 'active' AND created_at < $1",
                before,
            )
            # Parse "DELETE X" to get count
            return int(result.split()[1]) if result.startswith("DELETE") else 0

    def _row_to_lease(self, row) -> Lease:
        """تحويل row إلى Lease."""
        return Lease(
            lease_id=row["lease_id"],
            job_id=row["job_id"],
            worker_id=row["worker_id"],
            state=LeaseState(row["state"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            last_renewed_at=row["last_renewed_at"],
            released_at=row["released_at"],
            renewal_count=row["renewal_count"],
            idempotency_key=row["idempotency_key"],
        )

    # ==================== Events ====================

    async def save_event(self, event: Event) -> None:
        """حفظ event."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO events (event_type, timestamp, source, data, message, job_id, worker_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
                event.event_type.value,
                event.timestamp,
                event.source,
                json.dumps(event.data),
                event.message,
                event.job_id,
                event.worker_id,
            )

    async def get_recent_events(self, limit: int = 100) -> List[Event]:
        """الحصول على آخر الأحداث."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM events ORDER BY timestamp DESC LIMIT $1", limit
            )
            return [self._row_to_event(row) for row in rows]

    async def get_events_by_type(self, event_type: EventType, limit: int = 100) -> List[Event]:
        """الحصول على events بنوع معين."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM events WHERE event_type = $1 ORDER BY timestamp DESC LIMIT $2",
                event_type.value,
                limit,
            )
            return [self._row_to_event(row) for row in rows]

    async def get_events_by_job(self, job_id: str) -> List[Event]:
        """الحصول على events لـ job."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM events WHERE job_id = $1 ORDER BY timestamp ASC",
                job_id,
            )
            return [self._row_to_event(row) for row in rows]

    async def delete_old_events(self, before: datetime) -> int:
        """حذف events قديمة."""
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM events WHERE timestamp < $1", before)
            return int(result.split()[1]) if result.startswith("DELETE") else 0

    def _row_to_event(self, row) -> Event:
        """تحويل row إلى Event."""
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)

        return Event(
            event_type=EventType(row["event_type"]),
            timestamp=row["timestamp"],
            source=row["source"],
            data=data,
            message=row["message"],
            job_id=row["job_id"],
            worker_id=row["worker_id"],
        )

    # ==================== Cleanup ====================

    async def cleanup_old_data(self, retention_days: int = 30) -> Dict[str, int]:
        """تنظيف البيانات القديمة."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        results = {}

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Delete old completed/failed jobs
                result = await conn.execute(
                    """
                    DELETE FROM jobs
                    WHERE status IN ('completed', 'failed', 'cancelled')
                    AND completed_at < $1
                """,
                    cutoff,
                )
                results["jobs"] = int(result.split()[1]) if result.startswith("DELETE") else 0

                # Delete old leases
                result = await conn.execute(
                    "DELETE FROM leases WHERE state != 'active' AND created_at < $1",
                    cutoff,
                )
                results["leases"] = int(result.split()[1]) if result.startswith("DELETE") else 0

                # Delete old events
                result = await conn.execute(
                    "DELETE FROM events WHERE timestamp < $1", cutoff
                )
                results["events"] = int(result.split()[1]) if result.startswith("DELETE") else 0

        logger.info(f"Cleanup completed: {results}")
        return results


# ==================== Factory ====================


async def create_database(config: DatabaseConfig) -> Database:
    """إنشاء قاعدة بيانات حسب النوع."""
    if config.type == "sqlite":
        db = SQLiteDatabase(config)
    elif config.type == "postgresql":
        db = PostgreSQLDatabase(config)
    else:
        raise ValueError(f"Unsupported database type: {config.type}")

    await db.initialize()
    return db
