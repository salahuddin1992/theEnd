"""
Connection Pooling System for NebulaCompute.

Provides efficient connection management for:
- Database connections
- HTTP clients
- WebSocket connections
- Generic resource pooling
"""

from .connection_pool import (
    Connection,
    ConnectionFactory,
    ConnectionPool,
)
from .database_pool import (
    DatabaseConfig,
    DatabasePool,
)
from .http_pool import (
    HTTPClientConfig,
    HTTPConnectionPool,
)
from .pool_manager import (
    PoolConfig,
    PoolExhausted,
    PoolManager,
    PoolStats,
)
from .websocket_pool import (
    WebSocketConfig,
    WebSocketPool,
)

__all__ = [
    # Core
    "PoolManager",
    "PoolConfig",
    "PoolStats",
    "PoolExhausted",
    # Connection Pool
    "ConnectionPool",
    "Connection",
    "ConnectionFactory",
    # HTTP
    "HTTPConnectionPool",
    "HTTPClientConfig",
    # Database
    "DatabasePool",
    "DatabaseConfig",
    # WebSocket
    "WebSocketPool",
    "WebSocketConfig",
]
