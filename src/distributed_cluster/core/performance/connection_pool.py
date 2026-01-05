"""
Connection Pool - تجميع الاتصالات
=================================

Connection Pooling
------------------

This module provides connection pooling for various protocols.

يوفر هذا الملف تجميع الاتصالات لبروتوكولات مختلفة.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Connection type


@dataclass
class ConnectionPoolConfig:
    """
    إعدادات تجميع الاتصالات
    Connection pool configuration
    """

    # Pool size
    min_size: int = 1
    max_size: int = 10

    # Timeouts
    acquire_timeout_seconds: float = 30.0
    connection_timeout_seconds: float = 10.0
    idle_timeout_seconds: float = 300.0  # 5 minutes

    # Health check
    health_check_interval_seconds: float = 30.0
    validate_on_acquire: bool = True

    # Retry
    max_retries: int = 3
    retry_delay_seconds: float = 1.0

    # Options
    recycle_connections: bool = True
    max_connection_age_seconds: float = 3600.0  # 1 hour


@dataclass
class PooledConnection(Generic[T]):
    """
    اتصال مُجمّع
    Pooled connection wrapper
    """

    connection: T
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    use_count: int = 0
    is_healthy: bool = True

    def mark_used(self) -> None:
        """تحديث وقت الاستخدام"""
        self.last_used_at = time.time()
        self.use_count += 1

    @property
    def age_seconds(self) -> float:
        """عمر الاتصال بالثواني"""
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        """وقت الخمول بالثواني"""
        return time.time() - self.last_used_at


class ConnectionPool(Generic[T]):
    """
    تجميع اتصالات عام
    Generic Connection Pool

    يدير مجموعة من الاتصالات القابلة لإعادة الاستخدام.
    Manages a pool of reusable connections.
    """

    def __init__(
        self,
        factory: Callable[[], T],
        config: Optional[ConnectionPoolConfig] = None,
        validator: Optional[Callable[[T], bool]] = None,
        cleanup: Optional[Callable[[T], None]] = None,
    ):
        """
        تهيئة تجميع الاتصالات

        Args:
            factory: دالة إنشاء اتصال جديد
            config: إعدادات التجميع
            validator: دالة التحقق من صحة الاتصال
            cleanup: دالة تنظيف الاتصال
        """
        self.factory = factory
        self.config = config or ConnectionPoolConfig()
        self.validator = validator
        self.cleanup = cleanup

        # Pool state
        self._pool: asyncio.Queue[PooledConnection[T]] = asyncio.Queue(maxsize=self.config.max_size)
        self._all_connections: set[PooledConnection[T]] = set()
        self._lock = asyncio.Lock()
        self._closed = False

        # Statistics
        self._stats = {
            "connections_created": 0,
            "connections_recycled": 0,
            "connections_closed": 0,
            "acquire_count": 0,
            "acquire_timeouts": 0,
            "validation_failures": 0,
        }

        # Background tasks
        self._health_check_task: Optional[asyncio.Task] = None

    # =========================================================================
    # Lifecycle / دورة الحياة
    # =========================================================================

    async def start(self) -> None:
        """بدء التجميع"""
        # Create minimum connections
        for _ in range(self.config.min_size):
            await self._create_connection()

        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        logger.info(f"ConnectionPool started with {self._pool.qsize()} connections")

    async def close(self) -> None:
        """إغلاق التجميع"""
        self._closed = True

        # Stop health check
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        async with self._lock:
            while not self._pool.empty():
                try:
                    pooled = self._pool.get_nowait()
                    await self._close_connection(pooled)
                except asyncio.QueueEmpty:
                    break

        logger.info("ConnectionPool closed")

    # =========================================================================
    # Acquire/Release / الحصول/الإطلاق
    # =========================================================================

    async def acquire(self) -> T:
        """
        الحصول على اتصال من التجميع
        Acquire connection from pool
        """
        if self._closed:
            raise RuntimeError("Pool is closed")

        self._stats["acquire_count"] += 1

        try:
            pooled = await asyncio.wait_for(
                self._get_or_create_connection(),
                timeout=self.config.acquire_timeout_seconds,
            )

            pooled.mark_used()
            return pooled.connection

        except asyncio.TimeoutError:
            self._stats["acquire_timeouts"] += 1
            raise TimeoutError("Failed to acquire connection from pool")

    async def release(self, connection: T) -> None:
        """
        إعادة اتصال إلى التجميع
        Release connection back to pool
        """
        if self._closed:
            return

        # Find the pooled connection
        pooled = None
        for p in self._all_connections:
            if p.connection is connection:
                pooled = p
                break

        if not pooled:
            return

        # Check if connection should be recycled
        if self._should_recycle(pooled):
            await self._close_connection(pooled)
            self._stats["connections_recycled"] += 1
            return

        # Return to pool
        try:
            self._pool.put_nowait(pooled)
        except asyncio.QueueFull:
            await self._close_connection(pooled)

    @asynccontextmanager
    async def connection(self):
        """
        مدير سياق للاتصال
        Context manager for connection
        """
        conn = await self.acquire()
        try:
            yield conn
        finally:
            await self.release(conn)

    # =========================================================================
    # Connection Management / إدارة الاتصالات
    # =========================================================================

    async def _get_or_create_connection(self) -> PooledConnection[T]:
        """الحصول على اتصال موجود أو إنشاء جديد"""
        # Try to get from pool
        try:
            pooled = self._pool.get_nowait()

            # Validate if configured
            if self.config.validate_on_acquire:
                if not await self._validate_connection(pooled):
                    await self._close_connection(pooled)
                    return await self._get_or_create_connection()

            return pooled

        except asyncio.QueueEmpty:
            pass

        # Create new connection if under limit
        async with self._lock:
            if len(self._all_connections) < self.config.max_size:
                return await self._create_connection()

        # Wait for a connection to be released
        return await self._pool.get()

    async def _create_connection(self) -> PooledConnection[T]:
        """إنشاء اتصال جديد"""
        try:
            # Create connection with timeout
            if asyncio.iscoroutinefunction(self.factory):
                connection = await asyncio.wait_for(
                    self.factory(),
                    timeout=self.config.connection_timeout_seconds,
                )
            else:
                loop = asyncio.get_event_loop()
                connection = await asyncio.wait_for(
                    loop.run_in_executor(None, self.factory),
                    timeout=self.config.connection_timeout_seconds,
                )

            pooled = PooledConnection(connection=connection)
            self._all_connections.add(pooled)
            self._stats["connections_created"] += 1

            logger.debug(f"Created new connection, total: {len(self._all_connections)}")

            return pooled

        except Exception as e:
            logger.error(f"Failed to create connection: {e}")
            raise

    async def _close_connection(self, pooled: PooledConnection[T]) -> None:
        """إغلاق اتصال"""
        try:
            if self.cleanup:
                if asyncio.iscoroutinefunction(self.cleanup):
                    await self.cleanup(pooled.connection)
                else:
                    self.cleanup(pooled.connection)

            self._all_connections.discard(pooled)
            self._stats["connections_closed"] += 1

        except Exception as e:
            logger.error(f"Error closing connection: {e}")

    async def _validate_connection(self, pooled: PooledConnection[T]) -> bool:
        """التحقق من صحة الاتصال"""
        if not self.validator:
            return True

        try:
            if asyncio.iscoroutinefunction(self.validator):
                return await self.validator(pooled.connection)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self.validator, pooled.connection)
        except Exception:
            self._stats["validation_failures"] += 1
            return False

    def _should_recycle(self, pooled: PooledConnection[T]) -> bool:
        """التحقق من الحاجة لإعادة التدوير"""
        if not self.config.recycle_connections:
            return False

        # Check age
        if pooled.age_seconds > self.config.max_connection_age_seconds:
            return True

        # Check health
        if not pooled.is_healthy:
            return True

        return False

    # =========================================================================
    # Health Check / فحص الصحة
    # =========================================================================

    async def _health_check_loop(self) -> None:
        """حلقة فحص الصحة"""
        while not self._closed:
            try:
                await asyncio.sleep(self.config.health_check_interval_seconds)
                await self._check_pool_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def _check_pool_health(self) -> None:
        """فحص صحة التجميع"""
        # Check idle connections
        idle_connections: list[PooledConnection[T]] = []

        while not self._pool.empty():
            try:
                pooled = self._pool.get_nowait()

                if pooled.idle_seconds > self.config.idle_timeout_seconds:
                    await self._close_connection(pooled)
                elif not await self._validate_connection(pooled):
                    await self._close_connection(pooled)
                else:
                    idle_connections.append(pooled)

            except asyncio.QueueEmpty:
                break

        # Return healthy connections
        for pooled in idle_connections:
            try:
                self._pool.put_nowait(pooled)
            except asyncio.QueueFull:
                await self._close_connection(pooled)

        # Ensure minimum connections
        current_count = len(self._all_connections)
        if current_count < self.config.min_size:
            for _ in range(self.config.min_size - current_count):
                try:
                    pooled = await self._create_connection()
                    self._pool.put_nowait(pooled)
                except Exception:
                    pass

    # =========================================================================
    # Status / الحالة
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """الحصول على إحصائيات التجميع"""
        return {
            **self._stats,
            "pool_size": self._pool.qsize(),
            "total_connections": len(self._all_connections),
            "max_size": self.config.max_size,
            "min_size": self.config.min_size,
        }

    @property
    def size(self) -> int:
        """حجم التجميع الحالي"""
        return len(self._all_connections)

    @property
    def available(self) -> int:
        """عدد الاتصالات المتاحة"""
        return self._pool.qsize()


# =============================================================================
# HTTP Connection Pool / تجميع اتصالات HTTP
# =============================================================================


class HTTPConnectionPool:
    """
    تجميع اتصالات HTTP
    HTTP Connection Pool

    يوفر تجميع اتصالات httpx.
    Provides httpx connection pooling.
    """

    def __init__(
        self,
        base_url: str = "",
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
        keepalive_expiry: float = 5.0,
        timeout: float = 30.0,
    ):
        """
        تهيئة تجميع HTTP

        Args:
            base_url: URL الأساسي
            max_connections: أقصى عدد اتصالات
            max_keepalive_connections: أقصى اتصالات keepalive
            keepalive_expiry: مدة انتهاء keepalive
            timeout: مهلة الطلب
        """
        self.base_url = base_url
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self.keepalive_expiry = keepalive_expiry
        self.timeout = timeout

        self._client: Optional[Any] = None

    async def start(self) -> None:
        """بدء التجميع"""
        try:
            import httpx

            limits = httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_keepalive_connections,
                keepalive_expiry=self.keepalive_expiry,
            )

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                limits=limits,
                timeout=httpx.Timeout(self.timeout),
            )

            logger.info("HTTPConnectionPool started")

        except ImportError:
            logger.error("httpx not installed")
            raise

    async def close(self) -> None:
        """إغلاق التجميع"""
        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("HTTPConnectionPool closed")

    @property
    def client(self) -> Any:
        """الحصول على العميل"""
        if not self._client:
            raise RuntimeError("Pool not started")
        return self._client

    async def get(self, url: str, **kwargs) -> Any:
        """طلب GET"""
        return await self.client.get(url, **kwargs)

    async def post(self, url: str, **kwargs) -> Any:
        """طلب POST"""
        return await self.client.post(url, **kwargs)

    async def put(self, url: str, **kwargs) -> Any:
        """طلب PUT"""
        return await self.client.put(url, **kwargs)

    async def delete(self, url: str, **kwargs) -> Any:
        """طلب DELETE"""
        return await self.client.delete(url, **kwargs)
