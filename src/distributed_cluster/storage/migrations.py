"""
Database Migrations - ترحيل قاعدة البيانات
==========================================

إدارة ترحيل مخطط قاعدة البيانات:
- تتبع إصدار المخطط
- تطبيق الترحيلات بالترتيب
- دعم SQLite و PostgreSQL
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    """تعريف ترحيل واحد."""

    version: int
    name: str
    description: str
    up_sqlite: str  # SQL للتطبيق على SQLite
    up_postgresql: str  # SQL للتطبيق على PostgreSQL
    down_sqlite: str = ""  # SQL للتراجع على SQLite
    down_postgresql: str = ""  # SQL للتراجع على PostgreSQL


# ==================== Migration Registry ====================

MIGRATIONS: List[Migration] = [
    Migration(
        version=1,
        name="initial_schema",
        description="المخطط الأولي للجداول الأساسية",
        up_sqlite="""
            -- Workers table
            CREATE TABLE IF NOT EXISTS workers (
                id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'offline',
                cpu_cores INTEGER DEFAULT 0,
                memory_mb INTEGER DEFAULT 0,
                gpu_count INTEGER DEFAULT 0,
                gpu_memory_mb INTEGER DEFAULT 0,
                disk_gb INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                capabilities TEXT DEFAULT '[]',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_heartbeat TIMESTAMP,
                current_load REAL DEFAULT 0.0
            );

            -- Jobs table
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                function_name TEXT NOT NULL,
                args TEXT DEFAULT '[]',
                kwargs TEXT DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER DEFAULT 5,
                worker_id TEXT,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                result TEXT,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                timeout INTEGER DEFAULT 3600,
                required_cpu INTEGER DEFAULT 1,
                required_memory INTEGER DEFAULT 512,
                required_gpu INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}'
            );

            -- Leases table
            CREATE TABLE IF NOT EXISTS leases (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'active',
                duration_seconds INTEGER DEFAULT 300,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                renewed_at TIMESTAMP,
                renewal_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            );

            -- Events table
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL,
                data TEXT DEFAULT '{}',
                message TEXT,
                job_id TEXT,
                worker_id TEXT
            );

            -- Schema version table
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_worker ON jobs(worker_id);
            CREATE INDEX IF NOT EXISTS idx_leases_job ON leases(job_id);
            CREATE INDEX IF NOT EXISTS idx_leases_worker ON leases(worker_id);
            CREATE INDEX IF NOT EXISTS idx_leases_state ON leases(state);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
        """,
        up_postgresql="""
            -- Workers table
            CREATE TABLE IF NOT EXISTS workers (
                id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                port INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'offline',
                cpu_cores INTEGER DEFAULT 0,
                memory_mb INTEGER DEFAULT 0,
                gpu_count INTEGER DEFAULT 0,
                gpu_memory_mb INTEGER DEFAULT 0,
                disk_gb INTEGER DEFAULT 0,
                tags JSONB DEFAULT '[]'::jsonb,
                capabilities JSONB DEFAULT '[]'::jsonb,
                registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_heartbeat TIMESTAMP WITH TIME ZONE,
                current_load REAL DEFAULT 0.0
            );

            -- Jobs table
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                function_name TEXT NOT NULL,
                args JSONB DEFAULT '[]'::jsonb,
                kwargs JSONB DEFAULT '{}'::jsonb,
                status TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER DEFAULT 5,
                worker_id TEXT,
                submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                started_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE,
                result JSONB,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                timeout INTEGER DEFAULT 3600,
                required_cpu INTEGER DEFAULT 1,
                required_memory INTEGER DEFAULT 512,
                required_gpu INTEGER DEFAULT 0,
                tags JSONB DEFAULT '[]'::jsonb,
                metadata JSONB DEFAULT '{}'::jsonb
            );

            -- Leases table
            CREATE TABLE IF NOT EXISTS leases (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'active',
                duration_seconds INTEGER DEFAULT 300,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                renewed_at TIMESTAMP WITH TIME ZONE,
                renewal_count INTEGER DEFAULT 0,
                metadata JSONB DEFAULT '{}'::jsonb
            );

            -- Events table
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                source TEXT NOT NULL,
                data JSONB DEFAULT '{}'::jsonb,
                message TEXT,
                job_id TEXT,
                worker_id TEXT
            );

            -- Schema version table
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_worker ON jobs(worker_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC);
            CREATE INDEX IF NOT EXISTS idx_leases_job ON leases(job_id);
            CREATE INDEX IF NOT EXISTS idx_leases_worker ON leases(worker_id);
            CREATE INDEX IF NOT EXISTS idx_leases_state ON leases(state);
            CREATE INDEX IF NOT EXISTS idx_leases_expires ON leases(expires_at);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
        """,
        down_sqlite="""
            DROP TABLE IF EXISTS events;
            DROP TABLE IF EXISTS leases;
            DROP TABLE IF EXISTS jobs;
            DROP TABLE IF EXISTS workers;
            DROP TABLE IF EXISTS schema_version;
        """,
        down_postgresql="""
            DROP TABLE IF EXISTS events;
            DROP TABLE IF EXISTS leases;
            DROP TABLE IF EXISTS jobs;
            DROP TABLE IF EXISTS workers;
            DROP TABLE IF EXISTS schema_version;
        """,
    ),
    Migration(
        version=2,
        name="add_job_queue",
        description="إضافة جدول قوائم انتظار الوظائف",
        up_sqlite="""
            CREATE TABLE IF NOT EXISTS job_queues (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                priority INTEGER DEFAULT 5,
                max_concurrent INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paused INTEGER DEFAULT 0
            );

            ALTER TABLE jobs ADD COLUMN queue_id TEXT REFERENCES job_queues(id);
            CREATE INDEX IF NOT EXISTS idx_jobs_queue ON jobs(queue_id);
        """,
        up_postgresql="""
            CREATE TABLE IF NOT EXISTS job_queues (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                priority INTEGER DEFAULT 5,
                max_concurrent INTEGER DEFAULT 10,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                paused BOOLEAN DEFAULT FALSE
            );

            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS queue_id TEXT REFERENCES job_queues(id);
            CREATE INDEX IF NOT EXISTS idx_jobs_queue ON jobs(queue_id);
        """,
        down_sqlite="""
            DROP INDEX IF EXISTS idx_jobs_queue;
            ALTER TABLE jobs DROP COLUMN queue_id;
            DROP TABLE IF EXISTS job_queues;
        """,
        down_postgresql="""
            DROP INDEX IF EXISTS idx_jobs_queue;
            ALTER TABLE jobs DROP COLUMN IF EXISTS queue_id;
            DROP TABLE IF EXISTS job_queues;
        """,
    ),
    Migration(
        version=3,
        name="add_worker_pools",
        description="إضافة تجمعات العمال",
        up_sqlite="""
            CREATE TABLE IF NOT EXISTS worker_pools (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                min_workers INTEGER DEFAULT 0,
                max_workers INTEGER DEFAULT 100,
                auto_scale INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            ALTER TABLE workers ADD COLUMN pool_id TEXT REFERENCES worker_pools(id);
            CREATE INDEX IF NOT EXISTS idx_workers_pool ON workers(pool_id);
        """,
        up_postgresql="""
            CREATE TABLE IF NOT EXISTS worker_pools (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                min_workers INTEGER DEFAULT 0,
                max_workers INTEGER DEFAULT 100,
                auto_scale BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            ALTER TABLE workers ADD COLUMN IF NOT EXISTS pool_id TEXT REFERENCES worker_pools(id);
            CREATE INDEX IF NOT EXISTS idx_workers_pool ON workers(pool_id);
        """,
        down_sqlite="""
            DROP INDEX IF EXISTS idx_workers_pool;
            ALTER TABLE workers DROP COLUMN pool_id;
            DROP TABLE IF EXISTS worker_pools;
        """,
        down_postgresql="""
            DROP INDEX IF EXISTS idx_workers_pool;
            ALTER TABLE workers DROP COLUMN IF EXISTS pool_id;
            DROP TABLE IF EXISTS worker_pools;
        """,
    ),
    Migration(
        version=4,
        name="add_job_templates",
        description="إضافة قوالب الوظائف المحفوظة",
        up_sqlite="""
            CREATE TABLE IF NOT EXISTS job_templates (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                function_name TEXT NOT NULL,
                default_args TEXT DEFAULT '[]',
                default_kwargs TEXT DEFAULT '{}',
                default_priority INTEGER DEFAULT 5,
                default_timeout INTEGER DEFAULT 3600,
                required_cpu INTEGER DEFAULT 1,
                required_memory INTEGER DEFAULT 512,
                required_gpu INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """,
        up_postgresql="""
            CREATE TABLE IF NOT EXISTS job_templates (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                function_name TEXT NOT NULL,
                default_args JSONB DEFAULT '[]'::jsonb,
                default_kwargs JSONB DEFAULT '{}'::jsonb,
                default_priority INTEGER DEFAULT 5,
                default_timeout INTEGER DEFAULT 3600,
                required_cpu INTEGER DEFAULT 1,
                required_memory INTEGER DEFAULT 512,
                required_gpu INTEGER DEFAULT 0,
                tags JSONB DEFAULT '[]'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            -- Add trigger for updated_at
            CREATE OR REPLACE FUNCTION update_job_template_timestamp()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS trigger_job_template_updated ON job_templates;
            CREATE TRIGGER trigger_job_template_updated
                BEFORE UPDATE ON job_templates
                FOR EACH ROW
                EXECUTE FUNCTION update_job_template_timestamp();
        """,
        down_sqlite="DROP TABLE IF EXISTS job_templates;",
        down_postgresql="""
            DROP TRIGGER IF EXISTS trigger_job_template_updated ON job_templates;
            DROP FUNCTION IF EXISTS update_job_template_timestamp;
            DROP TABLE IF EXISTS job_templates;
        """,
    ),
    Migration(
        version=5,
        name="add_metrics_tables",
        description="إضافة جداول المقاييس والإحصائيات",
        up_sqlite="""
            CREATE TABLE IF NOT EXISTS worker_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cpu_usage REAL DEFAULT 0.0,
                memory_usage REAL DEFAULT 0.0,
                disk_usage REAL DEFAULT 0.0,
                gpu_usage REAL DEFAULT 0.0,
                network_rx_bytes INTEGER DEFAULT 0,
                network_tx_bytes INTEGER DEFAULT 0,
                active_jobs INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS job_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                phase TEXT NOT NULL,
                duration_ms INTEGER DEFAULT 0,
                cpu_time_ms INTEGER DEFAULT 0,
                memory_peak_mb INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_worker_metrics_worker ON worker_metrics(worker_id);
            CREATE INDEX IF NOT EXISTS idx_worker_metrics_time ON worker_metrics(timestamp);
            CREATE INDEX IF NOT EXISTS idx_job_metrics_job ON job_metrics(job_id);
        """,
        up_postgresql="""
            CREATE TABLE IF NOT EXISTS worker_metrics (
                id SERIAL PRIMARY KEY,
                worker_id TEXT NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                cpu_usage REAL DEFAULT 0.0,
                memory_usage REAL DEFAULT 0.0,
                disk_usage REAL DEFAULT 0.0,
                gpu_usage REAL DEFAULT 0.0,
                network_rx_bytes BIGINT DEFAULT 0,
                network_tx_bytes BIGINT DEFAULT 0,
                active_jobs INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS job_metrics (
                id SERIAL PRIMARY KEY,
                job_id TEXT NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                phase TEXT NOT NULL,
                duration_ms INTEGER DEFAULT 0,
                cpu_time_ms INTEGER DEFAULT 0,
                memory_peak_mb INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_worker_metrics_worker ON worker_metrics(worker_id);
            CREATE INDEX IF NOT EXISTS idx_worker_metrics_time ON worker_metrics(timestamp);
            CREATE INDEX IF NOT EXISTS idx_job_metrics_job ON job_metrics(job_id);

            -- Partitioning hint for large deployments
            -- In production, consider partitioning worker_metrics by time
        """,
        down_sqlite="""
            DROP TABLE IF EXISTS job_metrics;
            DROP TABLE IF EXISTS worker_metrics;
        """,
        down_postgresql="""
            DROP TABLE IF EXISTS job_metrics;
            DROP TABLE IF EXISTS worker_metrics;
        """,
    ),
]


# ==================== Migration Runner ====================


class MigrationRunner:
    """تشغيل الترحيلات على قاعدة البيانات."""

    def __init__(self, db_type: str = "sqlite"):
        """
        تهيئة المشغل.

        Args:
            db_type: نوع قاعدة البيانات (sqlite أو postgresql)
        """
        self.db_type = db_type
        self.migrations = sorted(MIGRATIONS, key=lambda m: m.version)

    async def get_current_version(self, conn) -> int:
        """الحصول على الإصدار الحالي."""
        try:
            if self.db_type == "sqlite":
                async with conn.execute(
                    "SELECT MAX(version) FROM schema_version"
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row and row[0] else 0
            else:
                row = await conn.fetchrow("SELECT MAX(version) FROM schema_version")
                return row[0] if row and row[0] else 0
        except Exception:
            return 0

    async def apply_migration(self, conn, migration: Migration) -> None:
        """تطبيق ترحيل واحد."""
        sql = migration.up_sqlite if self.db_type == "sqlite" else migration.up_postgresql

        logger.info(f"Applying migration {migration.version}: {migration.name}")

        if self.db_type == "sqlite":
            # SQLite: Execute each statement separately
            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    await conn.execute(statement)

            # Record migration
            await conn.execute(
                "INSERT INTO schema_version (version, name) VALUES (?, ?)",
                (migration.version, migration.name),
            )
            await conn.commit()
        else:
            # PostgreSQL: Execute in transaction
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_version (version, name) VALUES ($1, $2)",
                    migration.version,
                    migration.name,
                )

        logger.info(f"Migration {migration.version} applied successfully")

    async def rollback_migration(self, conn, migration: Migration) -> None:
        """التراجع عن ترحيل واحد."""
        sql = (
            migration.down_sqlite if self.db_type == "sqlite" else migration.down_postgresql
        )

        if not sql:
            raise ValueError(f"No rollback defined for migration {migration.version}")

        logger.info(f"Rolling back migration {migration.version}: {migration.name}")

        if self.db_type == "sqlite":
            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    await conn.execute(statement)

            await conn.execute(
                "DELETE FROM schema_version WHERE version = ?", (migration.version,)
            )
            await conn.commit()
        else:
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "DELETE FROM schema_version WHERE version = $1", migration.version
                )

        logger.info(f"Migration {migration.version} rolled back successfully")

    async def migrate(self, conn, target_version: Optional[int] = None) -> List[int]:
        """
        تشغيل جميع الترحيلات المعلقة.

        Args:
            conn: اتصال قاعدة البيانات
            target_version: الإصدار المستهدف (اختياري)

        Returns:
            قائمة بأرقام الإصدارات المطبقة
        """
        current = await self.get_current_version(conn)
        target = target_version or self.migrations[-1].version if self.migrations else 0

        applied = []

        if target > current:
            # Apply migrations forward
            for migration in self.migrations:
                if current < migration.version <= target:
                    await self.apply_migration(conn, migration)
                    applied.append(migration.version)
        elif target < current:
            # Rollback migrations
            for migration in reversed(self.migrations):
                if target < migration.version <= current:
                    await self.rollback_migration(conn, migration)
                    applied.append(-migration.version)  # Negative indicates rollback

        return applied

    def get_pending_migrations(self, current_version: int) -> List[Migration]:
        """الحصول على الترحيلات المعلقة."""
        return [m for m in self.migrations if m.version > current_version]

    def get_migration_history(self) -> List[Dict]:
        """الحصول على سجل الترحيلات."""
        return [
            {
                "version": m.version,
                "name": m.name,
                "description": m.description,
            }
            for m in self.migrations
        ]


# ==================== CLI Helper ====================


async def run_migrations_sqlite(db_path: str, target_version: Optional[int] = None) -> List[int]:
    """تشغيل الترحيلات على SQLite."""
    import aiosqlite

    runner = MigrationRunner("sqlite")

    async with aiosqlite.connect(db_path) as conn:
        return await runner.migrate(conn, target_version)


async def run_migrations_postgresql(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    target_version: Optional[int] = None,
) -> List[int]:
    """تشغيل الترحيلات على PostgreSQL."""
    try:
        import asyncpg
    except ImportError:
        raise ImportError("asyncpg is required for PostgreSQL migrations")

    runner = MigrationRunner("postgresql")

    conn = await asyncpg.connect(
        host=host, port=port, database=database, user=user, password=password
    )

    try:
        return await runner.migrate(conn, target_version)
    finally:
        await conn.close()


def get_latest_version() -> int:
    """الحصول على أحدث إصدار متاح."""
    return MIGRATIONS[-1].version if MIGRATIONS else 0
