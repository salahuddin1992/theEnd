"""
Storage Module - وحدة التخزين
==============================

تخزين حالة الكلاستر مع دعم:
- SQLite للتطوير والاستخدام الخفيف
- PostgreSQL للإنتاج مع connection pooling

الاستخدام:
    from distributed_cluster.storage import create_database, DatabaseConfig

    # SQLite
    config = DatabaseConfig(type="sqlite", path="./data/cluster.db")
    db = await create_database(config)

    # PostgreSQL
    config = DatabaseConfig(
        type="postgresql",
        host="localhost",
        port=5432,
        database="nebula",
        user="admin",
        password="secret",
        pool_size=10,
    )
    db = await create_database(config)
"""

from distributed_cluster.storage.database import (
    # Configuration
    DatabaseConfig,
    # Base class
    Database,
    # Implementations
    SQLiteDatabase,
    PostgreSQLDatabase,
    # Factory
    create_database,
    # Exceptions
    DatabaseError,
    ConnectionError,
    TransactionError,
    NotFoundError,
)

from distributed_cluster.storage.migrations import (
    Migration,
    MigrationRunner,
    run_migrations_sqlite,
    run_migrations_postgresql,
    get_latest_version,
    MIGRATIONS,
)

__all__ = [
    # Configuration
    "DatabaseConfig",
    # Base class
    "Database",
    # Implementations
    "SQLiteDatabase",
    "PostgreSQLDatabase",
    # Factory
    "create_database",
    # Exceptions
    "DatabaseError",
    "ConnectionError",
    "TransactionError",
    "NotFoundError",
    # Migrations
    "Migration",
    "MigrationRunner",
    "run_migrations_sqlite",
    "run_migrations_postgresql",
    "get_latest_version",
    "MIGRATIONS",
]
