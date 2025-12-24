"""
Connection Pooling System for NebulaCompute.

Provides efficient connection management for:
- Database connections
- HTTP clients
- WebSocket connections
- Generic resource pooling
"""

from .pool_manager import (
    PoolManager,
    PoolConfig,
    PoolStats,
    PoolExhausted,
)
from .connection_pool import (
    ConnectionPool,
    Connection,
    ConnectionFactory,
)
from .http_pool import (
    HTTPConnectionPool,
    HTTPClientConfig,
)
from .database_pool import (
    DatabasePool,
    DatabaseConfig,
)
from .websocket_pool import (
    WebSocketPool,
    WebSocketConfig,
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
