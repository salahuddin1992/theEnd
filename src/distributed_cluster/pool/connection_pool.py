"""
Generic Connection Pool for NebulaCompute.

Provides a flexible connection pool that can be used
with any connection type.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Connection(ABC, Generic[T]):
    """Abstract base class for poolable connections."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish the connection."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if connection is healthy."""
        pass

    @abstractmethod
    def get_underlying(self) -> T:
        """Get the underlying connection object."""
        pass


class ConnectionFactory(ABC, Generic[T]):
    """Factory for creating connections."""

    @abstractmethod
    async def create(self) -> Connection[T]:
        """Create a new connection."""
        pass


@dataclass
class ConnectionWrapper(Generic[T]):
    """Wrapper for connection with metadata."""

    connection: Connection[T]
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    use_count: int = 0
    errors: int = 0

    @property
    def age_seconds(self) -> float:
        """Get connection age."""
        return (datetime.now() - self.created_at).total_seconds()

    @property
    def idle_seconds(self) -> float:
        """Get idle time."""
        return (datetime.now() - self.last_used).total_seconds()


class ConnectionPool(Generic[T]):
    """
    Connection pool for managing reusable connections.

    Features:
    - Async connection acquisition
    - Connection health checking
    - Automatic connection recycling
    - Connection lifetime management
    """

    def __init__(
        self,
        factory: ConnectionFactory[T],
        min_size: int = 2,
        max_size: int = 10,
        max_idle_time: float = 300.0,
        max_lifetime: float = 3600.0,
        acquire_timeout: float = 30.0,
        health_check_interval: float = 30.0,
    ):
        """
        Initialize connection pool.

        Args:
            factory: Factory for creating connections
            min_size: Minimum pool size
            max_size: Maximum pool size
            max_idle_time: Max idle time before connection is closed
            max_lifetime: Max lifetime for a connection
            acquire_timeout: Timeout for acquiring connection
            health_check_interval: Interval for health checks
        """
        self.factory = factory
        self.min_size = min_size
        self.max_size = max_size
        self.max_idle_time = max_idle_time
        self.max_lifetime = max_lifetime
        self.acquire_timeout = acquire_timeout
        self.health_check_interval = health_check_interval

        self._pool: asyncio.Queue[ConnectionWrapper[T]] = asyncio.Queue()
        self._in_use: Dict[int, ConnectionWrapper[T]] = {}
        self._size = 0
        self._lock = asyncio.Lock()
        self._closed = False
        self._health_check_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the pool and create initial connections."""
        self._closed = False

        # Create minimum connections
        for _ in range(self.min_size):
            await self._create_connection()

        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        logger.info(
            "ConnectionPool started with %d connections",
            self._size,
        )

    async def close(self) -> None:
        """Close the pool and all connections."""
        self._closed = True

        # Stop health check
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        while not self._pool.empty():
            try:
                wrapper = self._pool.get_nowait()
                await wrapper.connection.close()
            except (asyncio.QueueEmpty, Exception) as e:
                logger.error("Error closing connection: %s", e)

        for wrapper in self._in_use.values():
            try:
                await wrapper.connection.close()
            except Exception as e:
                logger.error("Error closing in-use connection: %s", e)

        self._in_use.clear()
        self._size = 0

        logger.info("ConnectionPool closed")

    async def _create_connection(self) -> ConnectionWrapper[T]:
        """Create a new connection."""
        async with self._lock:
            if self._size >= self.max_size:
                raise RuntimeError("Pool at maximum size")

            connection = await self.factory.create()
            await connection.connect()

            wrapper = ConnectionWrapper(connection=connection)
            await self._pool.put(wrapper)
            self._size += 1

            return wrapper

    async def _destroy_connection(self, wrapper: ConnectionWrapper[T]) -> None:
        """Destroy a connection."""
        try:
            await wrapper.connection.close()
        except Exception as e:
            logger.error("Error closing connection: %s", e)
        finally:
            async with self._lock:
                self._size -= 1

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the pool.

        Usage:
            async with pool.acquire() as conn:
                result = await conn.execute(query)
        """
        if self._closed:
            raise RuntimeError("Pool is closed")

        wrapper = await self._acquire()

        try:
            yield wrapper.connection.get_underlying()
        except Exception:
            wrapper.errors += 1
            raise
        finally:
            await self._release(wrapper)

    async def _acquire(self) -> ConnectionWrapper[T]:
        """Internal acquire logic."""
        deadline = time.time() + self.acquire_timeout

        while True:
            # Try to get from pool
            try:
                wrapper = self._pool.get_nowait()

                # Check if connection is still valid
                if await self._validate(wrapper):
                    wrapper.last_used = datetime.now()
                    wrapper.use_count += 1
                    self._in_use[id(wrapper)] = wrapper
                    return wrapper
                else:
                    await self._destroy_connection(wrapper)
                    continue

            except asyncio.QueueEmpty:
                pass

            # Try to create new connection
            if self._size < self.max_size:
                try:
                    wrapper = await self._create_connection()
                    wrapper = await self._pool.get()
                    wrapper.last_used = datetime.now()
                    wrapper.use_count += 1
                    self._in_use[id(wrapper)] = wrapper
                    return wrapper
                except Exception as e:
                    logger.error("Failed to create connection: %s", e)

            # Wait for connection
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError("Connection acquire timeout")

            try:
                wrapper = await asyncio.wait_for(
                    self._pool.get(),
                    timeout=min(remaining, 1.0),
                )

                if await self._validate(wrapper):
                    wrapper.last_used = datetime.now()
                    wrapper.use_count += 1
                    self._in_use[id(wrapper)] = wrapper
                    return wrapper
                else:
                    await self._destroy_connection(wrapper)

            except asyncio.TimeoutError:
                continue

    async def _release(self, wrapper: ConnectionWrapper[T]) -> None:
        """Release connection back to pool."""
        wrapper_id = id(wrapper)

        if wrapper_id in self._in_use:
            del self._in_use[wrapper_id]

        wrapper.last_used = datetime.now()

        # Check if connection should be recycled
        if wrapper.errors > 3 or not await self._validate(wrapper):
            await self._destroy_connection(wrapper)
            return

        # Return to pool
        try:
            self._pool.put_nowait(wrapper)
        except asyncio.QueueFull:
            await self._destroy_connection(wrapper)

    async def _validate(self, wrapper: ConnectionWrapper[T]) -> bool:
        """Validate a connection."""
        # Check lifetime
        if wrapper.age_seconds > self.max_lifetime:
            return False

        # Check idle time
        if wrapper.idle_seconds > self.max_idle_time:
            return False

        # Check health
        try:
            return await wrapper.connection.is_healthy()
        except Exception:
            return False

    async def _health_check_loop(self) -> None:
        """Periodically check connection health."""
        while not self._closed:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health check error: %s", e)

    async def _health_check(self) -> None:
        """Check health of pooled connections."""
        # Get all pooled connections
        connections: List[ConnectionWrapper[T]] = []
        while not self._pool.empty():
            try:
                connections.append(self._pool.get_nowait())
            except asyncio.QueueEmpty:
                break

        # Check each connection
        valid_count = 0
        for wrapper in connections:
            if await self._validate(wrapper):
                await self._pool.put(wrapper)
                valid_count += 1
            else:
                await self._destroy_connection(wrapper)

        # Ensure minimum connections
        while self._size < self.min_size:
            try:
                await self._create_connection()
            except Exception as e:
                logger.error("Failed to create connection: %s", e)
                break

        logger.debug(
            "Health check: %d valid, %d total",
            valid_count,
            self._size,
        )

    @property
    def size(self) -> int:
        """Get current pool size."""
        return self._size

    @property
    def available(self) -> int:
        """Get available connections."""
        return self._pool.qsize()

    @property
    def in_use(self) -> int:
        """Get connections in use."""
        return len(self._in_use)

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return {
            "size": self._size,
            "available": self.available,
            "in_use": self.in_use,
            "min_size": self.min_size,
            "max_size": self.max_size,
            "closed": self._closed,
        }
