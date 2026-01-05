"""
Audit Backends - خلفيات سجل التدقيق
====================================

خلفيات إضافية لتخزين سجلات التدقيق:
- PostgreSQL
- SQLite
- Elasticsearch
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from distributed_cluster.security.audit import (
    AuditAction,
    AuditBackend,
    AuditEvent,
    AuditResult,
)

logger = logging.getLogger(__name__)


# ==================== SQLite Backend ====================


class SQLiteAuditBackend(AuditBackend):
    """
    خلفية SQLite لسجلات التدقيق.

    مناسبة للتطوير والاستخدام الخفيف.
    """

    def __init__(
        self,
        db_path: str = "./audit.db",
        retention_days: int = 90,
    ):
        self.db_path = db_path
        self.retention_days = retention_days
        self._conn = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """تهيئة قاعدة البيانات."""
        import aiosqlite

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    result TEXT NOT NULL,
                    actor_id TEXT,
                    actor_type TEXT,
                    actor_role TEXT,
                    actor_ip TEXT,
                    resource_type TEXT,
                    resource_id TEXT,
                    resource_name TEXT,
                    details TEXT,
                    error_message TEXT,
                    correlation_id TEXT
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_events(timestamp)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_action
                ON audit_events(action)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_actor
                ON audit_events(actor_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_resource
                ON audit_events(resource_type, resource_id)
            """)

            await conn.commit()

        logger.info(f"SQLite audit backend initialized at {self.db_path}")

    async def _get_conn(self):
        """الحصول على اتصال."""
        import aiosqlite

        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def log(self, event: AuditEvent) -> None:
        """تسجيل حدث."""
        async with self._lock:
            conn = await self._get_conn()

            await conn.execute("""
                INSERT INTO audit_events
                (event_id, timestamp, action, result, actor_id, actor_type,
                 actor_role, actor_ip, resource_type, resource_id, resource_name,
                 details, error_message, correlation_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id,
                event.timestamp.isoformat(),
                event.action.value if isinstance(event.action, AuditAction) else event.action,
                event.result.value if isinstance(event.result, AuditResult) else event.result,
                event.actor_id,
                event.actor_type,
                event.actor_role,
                event.actor_ip,
                event.resource_type,
                event.resource_id,
                event.resource_name,
                json.dumps(event.details),
                event.error_message,
                event.correlation_id,
            ))

            await conn.commit()

    async def query(
        self,
        action: Optional[AuditAction] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        result: Optional[AuditResult] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """استعلام الأحداث."""
        conditions = []
        params = []

        if action:
            conditions.append("action = ?")
            params.append(action.value if isinstance(action, AuditAction) else action)

        if actor_id:
            conditions.append("actor_id = ?")
            params.append(actor_id)

        if resource_type:
            conditions.append("resource_type = ?")
            params.append(resource_type)

        if resource_id:
            conditions.append("resource_id = ?")
            params.append(resource_id)

        if result:
            conditions.append("result = ?")
            params.append(result.value if isinstance(result, AuditResult) else result)

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())

        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT * FROM audit_events
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        async with self._lock:
            conn = await self._get_conn()
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        events = []
        for row in rows:
            events.append(self._row_to_event(row))

        return events

    def _row_to_event(self, row) -> AuditEvent:
        """تحويل row إلى AuditEvent."""
        details = row["details"]
        if isinstance(details, str):
            details = json.loads(details)

        return AuditEvent(
            event_id=row["event_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            action=AuditAction(row["action"]) if row["action"] in [a.value for a in AuditAction] else row["action"],
            result=AuditResult(row["result"]) if row["result"] in [r.value for r in AuditResult] else row["result"],
            actor_id=row["actor_id"],
            actor_type=row["actor_type"],
            actor_role=row["actor_role"],
            actor_ip=row["actor_ip"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            resource_name=row["resource_name"],
            details=details,
            error_message=row["error_message"],
            correlation_id=row["correlation_id"],
        )

    async def count(
        self,
        action: Optional[AuditAction] = None,
        result: Optional[AuditResult] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """عدد الأحداث."""
        conditions = []
        params = []

        if action:
            conditions.append("action = ?")
            params.append(action.value if isinstance(action, AuditAction) else action)

        if result:
            conditions.append("result = ?")
            params.append(result.value if isinstance(result, AuditResult) else result)

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())

        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"SELECT COUNT(*) FROM audit_events WHERE {where_clause}"

        async with self._lock:
            conn = await self._get_conn()
            async with conn.execute(query, params) as cursor:
                row = await cursor.fetchone()

        return row[0] if row else 0

    async def cleanup(self) -> int:
        """تنظيف الأحداث القديمة."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)

        async with self._lock:
            conn = await self._get_conn()
            cursor = await conn.execute(
                "DELETE FROM audit_events WHERE timestamp < ?",
                (cutoff.isoformat(),)
            )
            deleted = cursor.rowcount
            await conn.commit()

        logger.info(f"Cleaned up {deleted} old audit events")
        return deleted

    async def close(self) -> None:
        """إغلاق الاتصال."""
        if self._conn:
            await self._conn.close()
            self._conn = None


# ==================== PostgreSQL Backend ====================


class PostgreSQLAuditBackend(AuditBackend):
    """
    خلفية PostgreSQL لسجلات التدقيق.

    مناسبة للإنتاج والحجم الكبير.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "nebula_audit",
        user: str = "",
        password: str = "",
        pool_size: int = 5,
        retention_days: int = 90,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.pool_size = pool_size
        self.retention_days = retention_days
        self._pool = None

    async def initialize(self) -> None:
        """تهيئة قاعدة البيانات."""
        try:
            import asyncpg
        except ImportError:
            raise ImportError("asyncpg is required for PostgreSQL audit backend")

        self._pool = await asyncpg.create_pool(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            min_size=2,
            max_size=self.pool_size,
        )

        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                    action TEXT NOT NULL,
                    result TEXT NOT NULL,
                    actor_id TEXT,
                    actor_type TEXT,
                    actor_role TEXT,
                    actor_ip INET,
                    resource_type TEXT,
                    resource_id TEXT,
                    resource_name TEXT,
                    details JSONB DEFAULT '{}'::jsonb,
                    error_message TEXT,
                    correlation_id TEXT
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_events(timestamp)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_action
                ON audit_events(action)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_actor
                ON audit_events(actor_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_resource
                ON audit_events(resource_type, resource_id)
            """)

            # Partitioning hint
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp_action
                ON audit_events(timestamp, action)
            """)

        logger.info(f"PostgreSQL audit backend initialized at {self.host}:{self.port}/{self.database}")

    async def log(self, event: AuditEvent) -> None:
        """تسجيل حدث."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO audit_events
                (event_id, timestamp, action, result, actor_id, actor_type,
                 actor_role, actor_ip, resource_type, resource_id, resource_name,
                 details, error_message, correlation_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
                event.event_id,
                event.timestamp,
                event.action.value if isinstance(event.action, AuditAction) else event.action,
                event.result.value if isinstance(event.result, AuditResult) else event.result,
                event.actor_id,
                event.actor_type,
                event.actor_role,
                event.actor_ip,
                event.resource_type,
                event.resource_id,
                event.resource_name,
                json.dumps(event.details),
                event.error_message,
                event.correlation_id,
            )

    async def query(
        self,
        action: Optional[AuditAction] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        result: Optional[AuditResult] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """استعلام الأحداث."""
        conditions = []
        params = []
        param_idx = 1

        if action:
            conditions.append(f"action = ${param_idx}")
            params.append(action.value if isinstance(action, AuditAction) else action)
            param_idx += 1

        if actor_id:
            conditions.append(f"actor_id = ${param_idx}")
            params.append(actor_id)
            param_idx += 1

        if resource_type:
            conditions.append(f"resource_type = ${param_idx}")
            params.append(resource_type)
            param_idx += 1

        if resource_id:
            conditions.append(f"resource_id = ${param_idx}")
            params.append(resource_id)
            param_idx += 1

        if result:
            conditions.append(f"result = ${param_idx}")
            params.append(result.value if isinstance(result, AuditResult) else result)
            param_idx += 1

        if start_time:
            conditions.append(f"timestamp >= ${param_idx}")
            params.append(start_time)
            param_idx += 1

        if end_time:
            conditions.append(f"timestamp <= ${param_idx}")
            params.append(end_time)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        query = f"""
            SELECT * FROM audit_events
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        events = []
        for row in rows:
            events.append(self._row_to_event(row))

        return events

    def _row_to_event(self, row) -> AuditEvent:
        """تحويل row إلى AuditEvent."""
        details = row["details"]
        if isinstance(details, str):
            details = json.loads(details)

        return AuditEvent(
            event_id=row["event_id"],
            timestamp=row["timestamp"],
            action=AuditAction(row["action"]) if row["action"] in [a.value for a in AuditAction] else row["action"],
            result=AuditResult(row["result"]) if row["result"] in [r.value for r in AuditResult] else row["result"],
            actor_id=row["actor_id"],
            actor_type=row["actor_type"],
            actor_role=row["actor_role"],
            actor_ip=str(row["actor_ip"]) if row["actor_ip"] else None,
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            resource_name=row["resource_name"],
            details=details,
            error_message=row["error_message"],
            correlation_id=row["correlation_id"],
        )

    async def count(
        self,
        action: Optional[AuditAction] = None,
        result: Optional[AuditResult] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """عدد الأحداث."""
        conditions = []
        params = []
        param_idx = 1

        if action:
            conditions.append(f"action = ${param_idx}")
            params.append(action.value if isinstance(action, AuditAction) else action)
            param_idx += 1

        if result:
            conditions.append(f"result = ${param_idx}")
            params.append(result.value if isinstance(result, AuditResult) else result)
            param_idx += 1

        if start_time:
            conditions.append(f"timestamp >= ${param_idx}")
            params.append(start_time)
            param_idx += 1

        if end_time:
            conditions.append(f"timestamp <= ${param_idx}")
            params.append(end_time)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        query = f"SELECT COUNT(*) FROM audit_events WHERE {where_clause}"

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

        return row[0] if row else 0

    async def cleanup(self) -> int:
        """تنظيف الأحداث القديمة."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM audit_events WHERE timestamp < $1",
                cutoff,
            )
            deleted = int(result.split()[1]) if result.startswith("DELETE") else 0

        logger.info(f"Cleaned up {deleted} old audit events")
        return deleted

    async def close(self) -> None:
        """إغلاق الاتصال."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def get_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """إحصائيات سجل التدقيق."""
        start_time = start_time or datetime.now(timezone.utc) - timedelta(days=7)
        end_time = end_time or datetime.now(timezone.utc)

        async with self._pool.acquire() as conn:
            # Total events
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM audit_events WHERE timestamp BETWEEN $1 AND $2",
                start_time, end_time,
            )

            # Events by action
            by_action = await conn.fetch("""
                SELECT action, COUNT(*) as count
                FROM audit_events
                WHERE timestamp BETWEEN $1 AND $2
                GROUP BY action
                ORDER BY count DESC
            """, start_time, end_time)

            # Events by result
            by_result = await conn.fetch("""
                SELECT result, COUNT(*) as count
                FROM audit_events
                WHERE timestamp BETWEEN $1 AND $2
                GROUP BY result
            """, start_time, end_time)

            # Top actors
            top_actors = await conn.fetch("""
                SELECT actor_id, actor_type, COUNT(*) as count
                FROM audit_events
                WHERE timestamp BETWEEN $1 AND $2 AND actor_id IS NOT NULL
                GROUP BY actor_id, actor_type
                ORDER BY count DESC
                LIMIT 10
            """, start_time, end_time)

            # Failed actions
            failures = await conn.fetch("""
                SELECT action, COUNT(*) as count
                FROM audit_events
                WHERE timestamp BETWEEN $1 AND $2 AND result IN ('failure', 'denied', 'error')
                GROUP BY action
                ORDER BY count DESC
                LIMIT 10
            """, start_time, end_time)

        return {
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            "total_events": total,
            "by_action": {row["action"]: row["count"] for row in by_action},
            "by_result": {row["result"]: row["count"] for row in by_result},
            "top_actors": [
                {"id": row["actor_id"], "type": row["actor_type"], "count": row["count"]}
                for row in top_actors
            ],
            "top_failures": [
                {"action": row["action"], "count": row["count"]}
                for row in failures
            ],
        }


# ==================== Composite Backend ====================


class CompositeAuditBackend(AuditBackend):
    """
    خلفية مركبة تكتب لعدة backends.

    مفيدة لـ:
    - كتابة محلية + remote
    - كتابة لقاعدة بيانات + ملف للنسخ الاحتياطي
    """

    def __init__(self, backends: List[AuditBackend]):
        self.backends = backends

    async def initialize(self) -> None:
        """تهيئة جميع الخلفيات."""
        for backend in self.backends:
            if hasattr(backend, "initialize"):
                await backend.initialize()

    async def log(self, event: AuditEvent) -> None:
        """تسجيل حدث في جميع الخلفيات."""
        tasks = [backend.log(event) for backend in self.backends]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def query(self, **kwargs) -> List[AuditEvent]:
        """استعلام من أول خلفية."""
        if self.backends:
            return await self.backends[0].query(**kwargs)
        return []

    async def count(self, **kwargs) -> int:
        """عدد من أول خلفية."""
        if self.backends:
            return await self.backends[0].count(**kwargs)
        return 0

    async def cleanup(self) -> int:
        """تنظيف جميع الخلفيات."""
        total = 0
        for backend in self.backends:
            if hasattr(backend, "cleanup"):
                total += await backend.cleanup()
        return total

    async def close(self) -> None:
        """إغلاق جميع الخلفيات."""
        for backend in self.backends:
            if hasattr(backend, "close"):
                await backend.close()


# ==================== Factory ====================


async def create_audit_backend(
    backend_type: str = "memory",
    **kwargs,
) -> AuditBackend:
    """إنشاء خلفية تدقيق."""
    from distributed_cluster.security.audit import FileAuditBackend, MemoryAuditBackend

    if backend_type == "memory":
        return MemoryAuditBackend(**kwargs)
    elif backend_type == "file":
        backend = FileAuditBackend(**kwargs)
        return backend
    elif backend_type == "sqlite":
        backend = SQLiteAuditBackend(**kwargs)
        await backend.initialize()
        return backend
    elif backend_type == "postgresql":
        backend = PostgreSQLAuditBackend(**kwargs)
        await backend.initialize()
        return backend
    else:
        raise ValueError(f"Unknown audit backend type: {backend_type}")
