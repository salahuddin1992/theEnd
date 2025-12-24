"""
Database Connection Pool for NebulaCompute.

Provides efficient database connection pooling for:
- PostgreSQL
- SQLite
- Generic async databases
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Configuration for database connection pool."""
    # Connection settings
    dsn: str = ""
    host: str = "localhost"
    port: int = 5432
    database: str = ""
    user: str = ""
    password: str = ""

    # Pool settings
    min_size: int = 2
    max_size: int = 10
    max_idle_time: float = 300.0
    max_lifetime: float = 3600.0
    acquire_timeout: float = 30.0

    # Query settings
    statement_timeout: float = 30.0
    command_timeout: float = 60.0

    # SSL settings
    ssl: bool = False
    ssl_ca_file: Optional[str] = None

    @property
    def connection_string(self) -> str:
        """Build connection string."""
        if self.dsn:
            return self.dsn

        ssl_param = "?sslmode=require" if self.ssl else ""

        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}{ssl_param}"
        )


class DatabasePool:
    """
    Database connection pool.

    Supports:
    - PostgreSQL via asyncpg
    - SQLite via aiosqlite
    - Generic databases via databases library
    """

    def __init__(self, config: DatabaseConfig):
        """
        Initialize database pool.

        Args:
            config: Database configuration
        """
        self.config = config
        self._pool = None
        self._db_type = self._detect_db_type()
        self._query_count = 0
        self._error_count = 0
        self._total_time = 0.0

    def _detect_db_type(self) -> str:
        """Detect database type from connection string."""
        dsn = self.config.connection_string.lower()

        if "postgresql" in dsn or "postgres" in dsn:
            return "postgresql"
        elif "sqlite" in dsn:
            return "sqlite"
        elif "mysql" in dsn:
            return "mysql"
        else:
            return "generic"

    async def start(self) -> None:
        """Start the connection pool."""
        if self._db_type == "postgresql":
            await self._start_postgresql()
        elif self._db_type == "sqlite":
            await self._start_sqlite()
        else:
            await self._start_generic()

        logger.info(
            "DatabasePool started for %s with %d-%d connections",
            self._db_type,
            self.config.min_size,
            self.config.max_size,
        )

    async def _start_postgresql(self) -> None:
        """Start PostgreSQL pool."""
        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self.config.connection_string,
                min_size=self.config.min_size,
                max_size=self.config.max_size,
                max_inactive_connection_lifetime=self.config.max_idle_time,
                command_timeout=self.config.command_timeout,
            )

        except ImportError:
            raise RuntimeError("asyncpg not installed for PostgreSQL support")

    async def _start_sqlite(self) -> None:
        """Start SQLite pool (single connection with queue)."""
        try:
            import aiosqlite

            # SQLite doesn't support true pooling
            # Use a single connection with async access
            self._pool = await aiosqlite.connect(
                self.config.database or ":memory:"
            )

        except ImportError:
            raise RuntimeError("aiosqlite not installed for SQLite support")

    async def _start_generic(self) -> None:
        """Start generic database pool."""
        try:
            from databases import Database

            self._pool = Database(
                self.config.connection_string,
                min_size=self.config.min_size,
                max_size=self.config.max_size,
            )
            await self._pool.connect()

        except ImportError:
            raise RuntimeError("databases library not installed")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            if self._db_type == "postgresql":
                await self._pool.close()
            elif self._db_type == "sqlite":
                await self._pool.close()
            else:
                await self._pool.disconnect()

            self._pool = None

        logger.info("DatabasePool closed")

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a database connection.

        Usage:
            async with pool.acquire() as conn:
                result = await conn.fetch("SELECT * FROM users")
        """
        if self._db_type == "postgresql":
            async with self._pool.acquire() as conn:
                yield DatabaseConnection(conn, "postgresql")
        elif self._db_type == "sqlite":
            yield DatabaseConnection(self._pool, "sqlite")
        else:
            yield DatabaseConnection(self._pool, "generic")

    async def execute(
        self,
        query: str,
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute a query.

        Args:
            query: SQL query
            *args: Query parameters
            **kwargs: Additional options

        Returns:
            Query result
        """
        import time
        start = time.perf_counter()

        try:
            self._query_count += 1

            async with self.acquire() as conn:
                return await conn.execute(query, *args, **kwargs)

        except Exception:
            self._error_count += 1
            raise

        finally:
            self._total_time += time.perf_counter() - start

    async def fetch(
        self,
        query: str,
        *args,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Fetch rows from database.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            List of rows as dictionaries
        """
        async with self.acquire() as conn:
            return await conn.fetch(query, *args, **kwargs)

    async def fetchone(
        self,
        query: str,
        *args,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single row.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Row as dictionary or None
        """
        async with self.acquire() as conn:
            return await conn.fetchone(query, *args, **kwargs)

    async def fetchval(
        self,
        query: str,
        *args,
        column: int = 0,
        **kwargs,
    ) -> Any:
        """
        Fetch a single value.

        Args:
            query: SQL query
            *args: Query parameters
            column: Column index to fetch

        Returns:
            Single value
        """
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args, column=column, **kwargs)

    @asynccontextmanager
    async def transaction(self):
        """
        Start a transaction.

        Usage:
            async with pool.transaction() as conn:
                await conn.execute("INSERT INTO ...")
                await conn.execute("UPDATE ...")
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                yield conn

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        stats = {
            "db_type": self._db_type,
            "query_count": self._query_count,
            "error_count": self._error_count,
            "error_rate": (
                self._error_count / self._query_count
                if self._query_count else 0
            ),
            "avg_query_time_ms": (
                (self._total_time / self._query_count * 1000)
                if self._query_count else 0
            ),
        }

        # Add pool-specific stats
        if self._db_type == "postgresql" and self._pool:
            stats.update({
                "pool_size": self._pool.get_size(),
                "pool_free": self._pool.get_idle_size(),
                "pool_min": self._pool.get_min_size(),
                "pool_max": self._pool.get_max_size(),
            })

        return stats


class DatabaseConnection:
    """Wrapper for database connection with unified interface."""

    def __init__(self, conn: Any, db_type: str):
        """
        Initialize connection wrapper.

        Args:
            conn: Underlying connection
            db_type: Database type
        """
        self._conn = conn
        self._db_type = db_type

    async def execute(self, query: str, *args, **kwargs) -> Any:
        """Execute a query."""
        if self._db_type == "postgresql":
            return await self._conn.execute(query, *args)
        elif self._db_type == "sqlite":
            cursor = await self._conn.execute(query, args)
            await self._conn.commit()
            return cursor
        else:
            return await self._conn.execute(query, kwargs or args)

    async def fetch(self, query: str, *args, **kwargs) -> List[Dict[str, Any]]:
        """Fetch all rows."""
        if self._db_type == "postgresql":
            rows = await self._conn.fetch(query, *args)
            return [dict(row) for row in rows]
        elif self._db_type == "sqlite":
            cursor = await self._conn.execute(query, args)
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        else:
            return await self._conn.fetch_all(query, kwargs or args)

    async def fetchone(self, query: str, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Fetch single row."""
        if self._db_type == "postgresql":
            row = await self._conn.fetchrow(query, *args)
            return dict(row) if row else None
        elif self._db_type == "sqlite":
            cursor = await self._conn.execute(query, args)
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        else:
            return await self._conn.fetch_one(query, kwargs or args)

    async def fetchval(
        self,
        query: str,
        *args,
        column: int = 0,
        **kwargs,
    ) -> Any:
        """Fetch single value."""
        if self._db_type == "postgresql":
            return await self._conn.fetchval(query, *args, column=column)
        else:
            row = await self.fetchone(query, *args, **kwargs)
            if row:
                values = list(row.values())
                return values[column] if column < len(values) else None
            return None

    @asynccontextmanager
    async def transaction(self):
        """Start a transaction."""
        if self._db_type == "postgresql":
            async with self._conn.transaction():
                yield self
        elif self._db_type == "sqlite":
            # SQLite uses implicit transactions
            yield self
            await self._conn.commit()
        else:
            async with self._conn.transaction():
                yield self

    async def executemany(
        self,
        query: str,
        args_list: List[tuple],
    ) -> None:
        """Execute query with multiple parameter sets."""
        if self._db_type == "postgresql":
            await self._conn.executemany(query, args_list)
        elif self._db_type == "sqlite":
            await self._conn.executemany(query, args_list)
            await self._conn.commit()
        else:
            for args in args_list:
                await self._conn.execute(query, args)
