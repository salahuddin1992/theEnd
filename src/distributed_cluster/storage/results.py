"""
Result Storage - تخزين النتائج
================================

Persistent storage for job results.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StorageBackend(str, Enum):
    """Backend storage types."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    FILE = "file"


@dataclass
class JobResult:
    """نتيجة مهمة."""

    job_id: str
    status: str
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    output_data: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time_seconds: float = 0.0
    worker_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "output_data": self.output_data,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "execution_time_seconds": self.execution_time_seconds,
            "worker_id": self.worker_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobResult":
        return cls(
            job_id=data["job_id"],
            status=data["status"],
            exit_code=data.get("exit_code", 0),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            output_data=data.get("output_data", {}),
            artifacts=data.get("artifacts", []),
            metrics=data.get("metrics", {}),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            execution_time_seconds=data.get("execution_time_seconds", 0.0),
            worker_id=data.get("worker_id"),
            created_at=(
                datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc)
            ),
        )


class ResultStorage:
    """
    تخزين نتائج المهام.

    Features:
    - Persistent storage for job results
    - Multiple backend support (SQLite, PostgreSQL, file)
    - Result querying and filtering
    - Automatic cleanup of old results
    - Export capabilities
    """

    def __init__(
        self,
        backend: StorageBackend = StorageBackend.SQLITE,
        connection_string: Optional[str] = None,
        storage_path: Optional[Path] = None,
        retention_days: int = 30,
    ):
        self.backend = backend
        self.connection_string = connection_string
        self.storage_path = storage_path or Path.home() / ".nebula" / "results"
        self.retention_days = retention_days

        self._db = None
        self._lock = asyncio.Lock()

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """تهيئة التخزين."""
        if self.backend == StorageBackend.SQLITE:
            await self._init_sqlite()
        elif self.backend == StorageBackend.POSTGRESQL:
            await self._init_postgresql()
        # FILE backend doesn't need initialization

        logger.info(f"Result storage initialized ({self.backend.value})")

    async def _init_sqlite(self) -> None:
        """تهيئة SQLite."""
        import aiosqlite

        db_path = self.storage_path / "results.db"
        self._db = await aiosqlite.connect(str(db_path))

        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS job_results (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                exit_code INTEGER DEFAULT 0,
                stdout TEXT,
                stderr TEXT,
                output_data TEXT,
                artifacts TEXT,
                metrics TEXT,
                started_at TEXT,
                completed_at TEXT,
                execution_time_seconds REAL,
                worker_id TEXT,
                created_at TEXT NOT NULL
            )
        """
        )

        await self._db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_status ON job_results(status)
        """
        )

        await self._db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_created ON job_results(created_at)
        """
        )

        await self._db.commit()

    async def _init_postgresql(self) -> None:
        """تهيئة PostgreSQL."""
        try:
            import asyncpg

            self._db = await asyncpg.connect(self.connection_string)

            await self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS job_results (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    exit_code INTEGER DEFAULT 0,
                    stdout TEXT,
                    stderr TEXT,
                    output_data JSONB,
                    artifacts JSONB,
                    metrics JSONB,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    execution_time_seconds REAL,
                    worker_id TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """
            )
        except ImportError:
            logger.warning("asyncpg not installed, falling back to file storage")
            self.backend = StorageBackend.FILE

    async def store_result(self, result: JobResult) -> None:
        """
        تخزين نتيجة.

        Args:
            result: نتيجة المهمة
        """
        async with self._lock:
            if self.backend == StorageBackend.SQLITE:
                await self._store_sqlite(result)
            elif self.backend == StorageBackend.POSTGRESQL:
                await self._store_postgresql(result)
            else:
                await self._store_file(result)

        logger.debug(f"Stored result for job {result.job_id}")

    async def _store_sqlite(self, result: JobResult) -> None:
        """تخزين في SQLite."""
        await self._db.execute(
            """
            INSERT OR REPLACE INTO job_results
            (job_id, status, exit_code, stdout, stderr, output_data, artifacts,
             metrics, started_at, completed_at, execution_time_seconds, worker_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.job_id,
                result.status,
                result.exit_code,
                result.stdout,
                result.stderr,
                json.dumps(result.output_data),
                json.dumps(result.artifacts),
                json.dumps(result.metrics),
                result.started_at.isoformat() if result.started_at else None,
                result.completed_at.isoformat() if result.completed_at else None,
                result.execution_time_seconds,
                result.worker_id,
                result.created_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def _store_postgresql(self, result: JobResult) -> None:
        """تخزين في PostgreSQL."""
        await self._db.execute(
            """
            INSERT INTO job_results
            (job_id, status, exit_code, stdout, stderr, output_data, artifacts,
             metrics, started_at, completed_at, execution_time_seconds, worker_id, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (job_id) DO UPDATE SET
                status = EXCLUDED.status,
                exit_code = EXCLUDED.exit_code,
                stdout = EXCLUDED.stdout,
                stderr = EXCLUDED.stderr,
                output_data = EXCLUDED.output_data,
                artifacts = EXCLUDED.artifacts,
                metrics = EXCLUDED.metrics,
                completed_at = EXCLUDED.completed_at,
                execution_time_seconds = EXCLUDED.execution_time_seconds
            """,
            result.job_id,
            result.status,
            result.exit_code,
            result.stdout,
            result.stderr,
            json.dumps(result.output_data),
            json.dumps(result.artifacts),
            json.dumps(result.metrics),
            result.started_at,
            result.completed_at,
            result.execution_time_seconds,
            result.worker_id,
            result.created_at,
        )

    async def _store_file(self, result: JobResult) -> None:
        """تخزين في ملف."""
        result_path = self.storage_path / f"{result.job_id}.json"
        with open(result_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

    async def get_result(self, job_id: str) -> Optional[JobResult]:
        """
        الحصول على نتيجة.

        Args:
            job_id: معرف المهمة

        Returns:
            JobResult: النتيجة أو None
        """
        if self.backend == StorageBackend.SQLITE:
            return await self._get_sqlite(job_id)
        elif self.backend == StorageBackend.POSTGRESQL:
            return await self._get_postgresql(job_id)
        else:
            return await self._get_file(job_id)

    async def _get_sqlite(self, job_id: str) -> Optional[JobResult]:
        """الحصول من SQLite."""
        cursor = await self._db.execute(
            "SELECT * FROM job_results WHERE job_id = ?",
            (job_id,),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return JobResult(
            job_id=row[0],
            status=row[1],
            exit_code=row[2],
            stdout=row[3] or "",
            stderr=row[4] or "",
            output_data=json.loads(row[5] or "{}"),
            artifacts=json.loads(row[6] or "[]"),
            metrics=json.loads(row[7] or "{}"),
            started_at=datetime.fromisoformat(row[8]) if row[8] else None,
            completed_at=datetime.fromisoformat(row[9]) if row[9] else None,
            execution_time_seconds=row[10] or 0.0,
            worker_id=row[11],
            created_at=datetime.fromisoformat(row[12]) if row[12] else datetime.now(timezone.utc),
        )

    async def _get_postgresql(self, job_id: str) -> Optional[JobResult]:
        """الحصول من PostgreSQL."""
        row = await self._db.fetchrow(
            "SELECT * FROM job_results WHERE job_id = $1",
            job_id,
        )
        if not row:
            return None

        return JobResult.from_dict(dict(row))

    async def _get_file(self, job_id: str) -> Optional[JobResult]:
        """الحصول من ملف."""
        result_path = self.storage_path / f"{job_id}.json"
        if not result_path.exists():
            return None

        with open(result_path, "r") as f:
            return JobResult.from_dict(json.load(f))

    async def query_results(
        self,
        status: Optional[str] = None,
        worker_id: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[JobResult]:
        """
        استعلام النتائج.

        Args:
            status: تصفية حسب الحالة
            worker_id: تصفية حسب العامل
            since: من تاريخ
            until: إلى تاريخ
            limit: الحد الأقصى
            offset: الإزاحة

        Returns:
            List[JobResult]: قائمة النتائج
        """
        if self.backend == StorageBackend.SQLITE:
            return await self._query_sqlite(status, worker_id, since, until, limit, offset)
        elif self.backend == StorageBackend.POSTGRESQL:
            return await self._query_postgresql(status, worker_id, since, until, limit, offset)
        else:
            return await self._query_file(status, worker_id, since, until, limit, offset)

    async def _query_sqlite(
        self,
        status: Optional[str],
        worker_id: Optional[str],
        since: Optional[datetime],
        until: Optional[datetime],
        limit: int,
        offset: int,
    ) -> List[JobResult]:
        """استعلام SQLite."""
        query = "SELECT * FROM job_results WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)

        if worker_id:
            query += " AND worker_id = ?"
            params.append(worker_id)

        if since:
            query += " AND created_at >= ?"
            params.append(since.isoformat())

        if until:
            query += " AND created_at <= ?"
            params.append(until.isoformat())

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                JobResult(
                    job_id=row[0],
                    status=row[1],
                    exit_code=row[2],
                    stdout=row[3] or "",
                    stderr=row[4] or "",
                    output_data=json.loads(row[5] or "{}"),
                    artifacts=json.loads(row[6] or "[]"),
                    metrics=json.loads(row[7] or "{}"),
                    started_at=datetime.fromisoformat(row[8]) if row[8] else None,
                    completed_at=datetime.fromisoformat(row[9]) if row[9] else None,
                    execution_time_seconds=row[10] or 0.0,
                    worker_id=row[11],
                    created_at=datetime.fromisoformat(row[12]) if row[12] else datetime.now(timezone.utc),
                )
            )

        return results

    async def _query_postgresql(self, *args) -> List[JobResult]:
        """استعلام PostgreSQL."""
        # Similar to SQLite
        return []

    async def _query_file(
        self,
        status: Optional[str],
        worker_id: Optional[str],
        since: Optional[datetime],
        until: Optional[datetime],
        limit: int,
        offset: int,
    ) -> List[JobResult]:
        """استعلام الملفات."""
        results = []

        for path in self.storage_path.glob("*.json"):
            with open(path, "r") as f:
                result = JobResult.from_dict(json.load(f))

                if status and result.status != status:
                    continue
                if worker_id and result.worker_id != worker_id:
                    continue
                if since and result.created_at < since:
                    continue
                if until and result.created_at > until:
                    continue

                results.append(result)

        # Sort and paginate
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[offset : offset + limit]

    async def cleanup_old_results(self) -> int:
        """
        تنظيف النتائج القديمة.

        Returns:
            int: عدد النتائج المحذوفة
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        deleted = 0

        if self.backend == StorageBackend.SQLITE:
            cursor = await self._db.execute(
                "DELETE FROM job_results WHERE created_at < ?",
                (cutoff.isoformat(),),
            )
            deleted = cursor.rowcount
            await self._db.commit()

        elif self.backend == StorageBackend.FILE:
            for path in self.storage_path.glob("*.json"):
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                        created = datetime.fromisoformat(data["created_at"])
                        if created < cutoff:
                            path.unlink()
                            deleted += 1
                except Exception:
                    pass

        logger.info(f"Cleaned up {deleted} old results")
        return deleted

    async def get_stats(self) -> Dict[str, Any]:
        """إحصائيات التخزين."""
        if self.backend == StorageBackend.SQLITE:
            cursor = await self._db.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    AVG(execution_time_seconds) as avg_time
                FROM job_results
            """
            )
            row = await cursor.fetchone()

            return {
                "total_results": row[0] or 0,
                "completed": row[1] or 0,
                "failed": row[2] or 0,
                "average_execution_time": row[3] or 0.0,
            }

        return {"total_results": len(list(self.storage_path.glob("*.json")))}

    async def close(self) -> None:
        """إغلاق الاتصال."""
        if self._db:
            await self._db.close()
