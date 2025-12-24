"""
Pool Manager for NebulaCompute.

Central manager for all connection pools with monitoring,
health checks, and automatic scaling.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PoolState(Enum):
    """Pool state."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    DRAINING = "draining"
    CLOSED = "closed"


class PoolExhausted(Exception):
    """Raised when pool is exhausted and no connections available."""

    def __init__(self, pool_name: str, wait_time: float):
        super().__init__(f"Pool '{pool_name}' exhausted after {wait_time}s wait")
        self.pool_name = pool_name
        self.wait_time = wait_time


@dataclass
class PoolConfig:
    """Configuration for connection pool."""
    # Size settings
    min_size: int = 5
    max_size: int = 20
    initial_size: int = 5

    # Timeout settings
    acquire_timeout: float = 30.0
    connection_timeout: float = 10.0
    idle_timeout: float = 300.0
    max_lifetime: float = 3600.0

    # Health check settings
    health_check_interval: float = 30.0
    health_check_timeout: float = 5.0

    # Behavior settings
    validate_on_acquire: bool = True
    validate_on_return: bool = False
    auto_scale: bool = True
    scale_up_threshold: float = 0.8
    scale_down_threshold: float = 0.2

    # Retry settings
    retry_attempts: int = 3
    retry_delay: float = 1.0


@dataclass
class PoolStats:
    """Statistics for connection pool."""
    pool_name: str = ""
    state: PoolState = PoolState.INITIALIZING

    # Size metrics
    total_connections: int = 0
    available_connections: int = 0
    in_use_connections: int = 0

    # Operation metrics
    total_acquires: int = 0
    total_releases: int = 0
    total_creates: int = 0
    total_destroys: int = 0

    # Error metrics
    failed_acquires: int = 0
    failed_creates: int = 0
    timeouts: int = 0
    health_check_failures: int = 0

    # Timing metrics
    avg_acquire_time_ms: float = 0.0
    avg_wait_time_ms: float = 0.0
    max_wait_time_ms: float = 0.0

    # Utilization
    peak_usage: int = 0
    current_utilization: float = 0.0

    start_time: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pool_name": self.pool_name,
            "state": self.state.value,
            "total_connections": self.total_connections,
            "available_connections": self.available_connections,
            "in_use_connections": self.in_use_connections,
            "utilization": f"{self.current_utilization:.1%}",
            "total_acquires": self.total_acquires,
            "total_releases": self.total_releases,
            "failed_acquires": self.failed_acquires,
            "avg_acquire_time_ms": f"{self.avg_acquire_time_ms:.2f}",
            "avg_wait_time_ms": f"{self.avg_wait_time_ms:.2f}",
            "max_wait_time_ms": f"{self.max_wait_time_ms:.2f}",
            "peak_usage": self.peak_usage,
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
        }


@dataclass
class PooledConnection(Generic[T]):
    """Wrapper for pooled connection with metadata."""
    connection: T
    pool_name: str
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    use_count: int = 0
    is_valid: bool = True

    @property
    def age_seconds(self) -> float:
        """Get connection age in seconds."""
        return (datetime.now() - self.created_at).total_seconds()

    @property
    def idle_seconds(self) -> float:
        """Get idle time in seconds."""
        return (datetime.now() - self.last_used).total_seconds()


class PoolManager:
    """
    Central manager for all connection pools.

    Features:
    - Multiple named pools
    - Automatic health checking
    - Connection lifecycle management
    - Statistics and monitoring
    - Auto-scaling
    """

    _instance: Optional["PoolManager"] = None

    def __init__(self):
        self._pools: Dict[str, "GenericPool"] = {}
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "PoolManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(self) -> None:
        """Start the pool manager."""
        if self._running:
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("PoolManager started")

    async def stop(self) -> None:
        """Stop the pool manager and close all pools."""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close all pools
        for pool in self._pools.values():
            await pool.close()

        self._pools.clear()
        logger.info("PoolManager stopped")

    def register_pool(self, name: str, pool: "GenericPool") -> None:
        """Register a pool with the manager."""
        self._pools[name] = pool
        pool.stats.pool_name = name
        logger.info("Registered pool: %s", name)

    def get_pool(self, name: str) -> Optional["GenericPool"]:
        """Get a pool by name."""
        return self._pools.get(name)

    async def _health_check_loop(self) -> None:
        """Periodically check pool health."""
        while self._running:
            try:
                for name, pool in self._pools.items():
                    if pool.state == PoolState.RUNNING:
                        await pool.health_check()

                await asyncio.sleep(30)  # Check every 30 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health check error: %s", e)
                await asyncio.sleep(5)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all pools."""
        return {
            name: pool.stats.to_dict()
            for name, pool in self._pools.items()
        }


class GenericPool(Generic[T]):
    """
    Generic connection pool implementation.

    Features:
    - Configurable size limits
    - Connection validation
    - Automatic cleanup
    - Wait queue for exhausted pool
    """

    def __init__(
        self,
        factory: Callable[[], T],
        config: Optional[PoolConfig] = None,
        validator: Optional[Callable[[T], bool]] = None,
        destroyer: Optional[Callable[[T], None]] = None,
    ):
        """
        Initialize the pool.

        Args:
            factory: Function to create new connections
            config: Pool configuration
            validator: Function to validate connections
            destroyer: Function to destroy connections
        """
        self.factory = factory
        self.config = config or PoolConfig()
        self.validator = validator
        self.destroyer = destroyer

        self._available: asyncio.Queue[PooledConnection[T]] = asyncio.Queue()
        self._in_use: Dict[int, PooledConnection[T]] = {}
        self._waiters: int = 0
        self._lock = asyncio.Lock()
        self._state = PoolState.INITIALIZING
        self._stats = PoolStats()

        # Timing tracking
        self._acquire_times: List[float] = []
        self._wait_times: List[float] = []

    @property
    def state(self) -> PoolState:
        """Get pool state."""
        return self._state

    @property
    def stats(self) -> PoolStats:
        """Get pool statistics."""
        return self._stats

    async def initialize(self) -> None:
        """Initialize the pool with initial connections."""
        self._state = PoolState.INITIALIZING

        # Create initial connections
        for _ in range(self.config.initial_size):
            try:
                await self._create_connection()
            except Exception as e:
                logger.error("Failed to create initial connection: %s", e)

        self._state = PoolState.RUNNING
        self._update_stats()
        logger.info("Pool initialized with %d connections", self._available.qsize())

    async def close(self) -> None:
        """Close the pool and all connections."""
        self._state = PoolState.DRAINING

        # Close in-use connections
        for conn_wrapper in list(self._in_use.values()):
            await self._destroy_connection(conn_wrapper)

        self._in_use.clear()

        # Close available connections
        while not self._available.empty():
            try:
                conn_wrapper = self._available.get_nowait()
                await self._destroy_connection(conn_wrapper)
            except asyncio.QueueEmpty:
                break

        self._state = PoolState.CLOSED
        logger.info("Pool closed")

    async def _create_connection(self) -> PooledConnection[T]:
        """Create a new connection."""
        try:
            if asyncio.iscoroutinefunction(self.factory):
                connection = await asyncio.wait_for(
                    self.factory(),
                    timeout=self.config.connection_timeout,
                )
            else:
                connection = self.factory()

            wrapper = PooledConnection(
                connection=connection,
                pool_name=self._stats.pool_name,
            )

            await self._available.put(wrapper)
            self._stats.total_creates += 1

            return wrapper

        except Exception as e:
            self._stats.failed_creates += 1
            logger.error("Failed to create connection: %s", e)
            raise

    async def _destroy_connection(self, wrapper: PooledConnection[T]) -> None:
        """Destroy a connection."""
        try:
            if self.destroyer:
                if asyncio.iscoroutinefunction(self.destroyer):
                    await self.destroyer(wrapper.connection)
                else:
                    self.destroyer(wrapper.connection)
            elif hasattr(wrapper.connection, "close"):
                if asyncio.iscoroutinefunction(wrapper.connection.close):
                    await wrapper.connection.close()
                else:
                    wrapper.connection.close()

            self._stats.total_destroys += 1

        except Exception as e:
            logger.error("Failed to destroy connection: %s", e)

    async def _validate_connection(self, wrapper: PooledConnection[T]) -> bool:
        """Validate a connection."""
        # Check age
        if wrapper.age_seconds > self.config.max_lifetime:
            return False

        # Check idle time
        if wrapper.idle_seconds > self.config.idle_timeout:
            return False

        # Custom validation
        if self.validator:
            try:
                if asyncio.iscoroutinefunction(self.validator):
                    return await asyncio.wait_for(
                        self.validator(wrapper.connection),
                        timeout=self.config.health_check_timeout,
                    )
                else:
                    return self.validator(wrapper.connection)
            except Exception:
                return False

        return wrapper.is_valid

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the pool.

        Usage:
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
        """
        connection = await self._acquire()
        try:
            yield connection
        finally:
            await self._release(connection)

    async def _acquire(self) -> T:
        """Acquire a connection."""
        start_time = time.perf_counter()
        wait_start = start_time

        self._stats.total_acquires += 1
        self._waiters += 1

        try:
            deadline = time.time() + self.config.acquire_timeout

            while True:
                # Try to get an available connection
                try:
                    wrapper = self._available.get_nowait()

                    # Validate if configured
                    if self.config.validate_on_acquire:
                        if not await self._validate_connection(wrapper):
                            await self._destroy_connection(wrapper)
                            continue

                    # Mark as in use
                    wrapper.last_used = datetime.now()
                    wrapper.use_count += 1
                    self._in_use[id(wrapper.connection)] = wrapper

                    self._record_acquire_time(start_time)
                    self._record_wait_time(wait_start)
                    self._update_stats()

                    return wrapper.connection

                except asyncio.QueueEmpty:
                    pass

                # Check if we can create new connection
                total = self._available.qsize() + len(self._in_use)
                if total < self.config.max_size:
                    try:
                        wrapper = await self._create_connection()
                        wrapper = await self._available.get()
                        wrapper.last_used = datetime.now()
                        wrapper.use_count += 1
                        self._in_use[id(wrapper.connection)] = wrapper

                        self._record_acquire_time(start_time)
                        self._record_wait_time(wait_start)
                        self._update_stats()

                        return wrapper.connection

                    except Exception as e:
                        logger.error("Failed to create connection: %s", e)

                # Check timeout
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._stats.timeouts += 1
                    self._stats.failed_acquires += 1
                    raise PoolExhausted(
                        self._stats.pool_name,
                        self.config.acquire_timeout,
                    )

                # Wait for connection to become available
                try:
                    wrapper = await asyncio.wait_for(
                        self._available.get(),
                        timeout=min(remaining, 1.0),
                    )

                    if self.config.validate_on_acquire:
                        if not await self._validate_connection(wrapper):
                            await self._destroy_connection(wrapper)
                            continue

                    wrapper.last_used = datetime.now()
                    wrapper.use_count += 1
                    self._in_use[id(wrapper.connection)] = wrapper

                    self._record_acquire_time(start_time)
                    self._record_wait_time(wait_start)
                    self._update_stats()

                    return wrapper.connection

                except asyncio.TimeoutError:
                    continue

        finally:
            self._waiters -= 1

    async def _release(self, connection: T) -> None:
        """Release a connection back to the pool."""
        conn_id = id(connection)

        if conn_id not in self._in_use:
            logger.warning("Releasing unknown connection")
            return

        wrapper = self._in_use.pop(conn_id)
        wrapper.last_used = datetime.now()

        self._stats.total_releases += 1

        # Validate if configured
        if self.config.validate_on_return:
            if not await self._validate_connection(wrapper):
                await self._destroy_connection(wrapper)
                self._update_stats()
                return

        # Return to pool
        try:
            self._available.put_nowait(wrapper)
        except asyncio.QueueFull:
            await self._destroy_connection(wrapper)

        self._update_stats()

    async def health_check(self) -> int:
        """
        Check health of all available connections.

        Returns number of connections removed.
        """
        removed = 0
        checked = 0

        # Get all available connections
        connections: List[PooledConnection[T]] = []
        while not self._available.empty():
            try:
                connections.append(self._available.get_nowait())
            except asyncio.QueueEmpty:
                break

        # Check each connection
        for wrapper in connections:
            checked += 1
            if await self._validate_connection(wrapper):
                await self._available.put(wrapper)
            else:
                await self._destroy_connection(wrapper)
                removed += 1
                self._stats.health_check_failures += 1

        # Ensure minimum connections
        current = self._available.qsize() + len(self._in_use)
        while current < self.config.min_size:
            try:
                await self._create_connection()
                current += 1
            except Exception as e:
                logger.error("Failed to create connection: %s", e)
                break

        if removed > 0:
            logger.info(
                "Health check removed %d/%d connections",
                removed,
                checked,
            )

        self._update_stats()
        return removed

    def _update_stats(self) -> None:
        """Update pool statistics."""
        available = self._available.qsize()
        in_use = len(self._in_use)
        total = available + in_use

        self._stats.state = self._state
        self._stats.total_connections = total
        self._stats.available_connections = available
        self._stats.in_use_connections = in_use

        if total > 0:
            self._stats.current_utilization = in_use / total
        else:
            self._stats.current_utilization = 0.0

        if in_use > self._stats.peak_usage:
            self._stats.peak_usage = in_use

    def _record_acquire_time(self, start_time: float) -> None:
        """Record acquire time."""
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._acquire_times.append(elapsed_ms)

        # Keep last 1000
        if len(self._acquire_times) > 1000:
            self._acquire_times = self._acquire_times[-1000:]

        self._stats.avg_acquire_time_ms = (
            sum(self._acquire_times) / len(self._acquire_times)
        )

    def _record_wait_time(self, start_time: float) -> None:
        """Record wait time."""
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._wait_times.append(elapsed_ms)

        # Keep last 1000
        if len(self._wait_times) > 1000:
            self._wait_times = self._wait_times[-1000:]

        self._stats.avg_wait_time_ms = (
            sum(self._wait_times) / len(self._wait_times)
        )

        if elapsed_ms > self._stats.max_wait_time_ms:
            self._stats.max_wait_time_ms = elapsed_ms
