"""
Cache Invalidation - استراتيجيات إبطال التخزين المؤقت
=====================================================

Cache Invalidation Strategies
-----------------------------

This module provides various cache invalidation strategies.

يوفر هذا الملف استراتيجيات إبطال التخزين المؤقت المختلفة.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class InvalidationStrategy(ABC):
    """
    استراتيجية إبطال التخزين المؤقت الأساسية
    Base cache invalidation strategy
    """

    @abstractmethod
    async def should_invalidate(self, key: str, entry: Any) -> bool:
        """هل يجب إبطال المدخلة؟"""
        pass

    @abstractmethod
    async def on_access(self, key: str, entry: Any) -> None:
        """عند الوصول لمدخلة"""
        pass

    @abstractmethod
    async def on_write(self, key: str, entry: Any) -> None:
        """عند الكتابة"""
        pass


class TTLInvalidation(InvalidationStrategy):
    """
    إبطال بناءً على الوقت (TTL)
    Time-To-Live based invalidation
    """

    def __init__(self, default_ttl_seconds: float = 3600):
        self.default_ttl_seconds = default_ttl_seconds
        self._expirations: dict[str, float] = {}

    async def should_invalidate(self, key: str, entry: Any) -> bool:
        """التحقق من انتهاء الصلاحية"""
        expiration = self._expirations.get(key)
        if expiration is None:
            return False
        return time.time() > expiration

    async def on_access(self, key: str, entry: Any) -> None:
        """لا شيء عند الوصول"""
        pass

    async def on_write(self, key: str, entry: Any) -> None:
        """تعيين وقت الانتهاء عند الكتابة"""
        ttl = getattr(entry, "ttl_seconds", None) or self.default_ttl_seconds
        self._expirations[key] = time.time() + ttl

    def set_ttl(self, key: str, ttl_seconds: float) -> None:
        """تعيين TTL لمفتاح"""
        self._expirations[key] = time.time() + ttl_seconds

    def remove(self, key: str) -> None:
        """إزالة من التتبع"""
        self._expirations.pop(key, None)

    async def cleanup_expired(self) -> list[str]:
        """تنظيف المنتهية الصلاحية"""
        now = time.time()
        expired = [
            key for key, exp in self._expirations.items()
            if now > exp
        ]
        for key in expired:
            del self._expirations[key]
        return expired


class LRUInvalidation(InvalidationStrategy):
    """
    إبطال بناءً على الأقل استخداماً مؤخراً (LRU)
    Least Recently Used invalidation
    """

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._access_order: OrderedDict[str, float] = OrderedDict()

    async def should_invalidate(self, key: str, entry: Any) -> bool:
        """التحقق مما إذا كان يجب الإخلاء"""
        if len(self._access_order) <= self.max_size:
            return False

        # Least recently used key
        lru_key = next(iter(self._access_order))
        return key == lru_key

    async def on_access(self, key: str, entry: Any) -> None:
        """تحديث ترتيب الوصول"""
        if key in self._access_order:
            self._access_order.move_to_end(key)
        else:
            self._access_order[key] = time.time()

    async def on_write(self, key: str, entry: Any) -> None:
        """إضافة/تحديث عند الكتابة"""
        self._access_order[key] = time.time()
        self._access_order.move_to_end(key)

    def get_lru_keys(self, count: int = 1) -> list[str]:
        """الحصول على المفاتيح الأقل استخداماً"""
        return list(self._access_order.keys())[:count]

    def remove(self, key: str) -> None:
        """إزالة من التتبع"""
        self._access_order.pop(key, None)


class LFUInvalidation(InvalidationStrategy):
    """
    إبطال بناءً على الأقل تكراراً (LFU)
    Least Frequently Used invalidation
    """

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._frequencies: dict[str, int] = {}
        self._min_freq = 0

    async def should_invalidate(self, key: str, entry: Any) -> bool:
        """التحقق مما إذا كان يجب الإخلاء"""
        if len(self._frequencies) <= self.max_size:
            return False

        # Find minimum frequency key
        min_key = min(self._frequencies.keys(), key=lambda k: self._frequencies[k])
        return key == min_key

    async def on_access(self, key: str, entry: Any) -> None:
        """زيادة التردد"""
        self._frequencies[key] = self._frequencies.get(key, 0) + 1

    async def on_write(self, key: str, entry: Any) -> None:
        """تهيئة التردد"""
        self._frequencies[key] = 1

    def get_lfu_keys(self, count: int = 1) -> list[str]:
        """الحصول على المفاتيح الأقل تكراراً"""
        sorted_keys = sorted(
            self._frequencies.keys(),
            key=lambda k: self._frequencies[k],
        )
        return sorted_keys[:count]

    def remove(self, key: str) -> None:
        """إزالة من التتبع"""
        self._frequencies.pop(key, None)


# =============================================================================
# Write Strategies
# =============================================================================

@dataclass
class WriteOperation:
    """عملية كتابة"""
    key: str
    value: Any
    ttl_seconds: Optional[float] = None
    timestamp: float = field(default_factory=time.time)


class WriteThrough:
    """
    استراتيجية الكتابة المباشرة
    Write-Through Strategy

    تكتب إلى التخزين المؤقت والمخزن الدائم في نفس الوقت.
    Writes to cache and persistent store simultaneously.
    """

    def __init__(
        self,
        cache_write: Callable[[str, Any, Optional[float]], Any],
        store_write: Callable[[str, Any], Any],
    ):
        """
        تهيئة الاستراتيجية

        Args:
            cache_write: دالة الكتابة للتخزين المؤقت
            store_write: دالة الكتابة للمخزن الدائم
        """
        self.cache_write = cache_write
        self.store_write = store_write

    async def write(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
    ) -> bool:
        """
        كتابة متزامنة
        Synchronous write to both cache and store
        """
        try:
            # Write to store first
            if asyncio.iscoroutinefunction(self.store_write):
                await self.store_write(key, value)
            else:
                self.store_write(key, value)

            # Then write to cache
            if asyncio.iscoroutinefunction(self.cache_write):
                await self.cache_write(key, value, ttl_seconds)
            else:
                self.cache_write(key, value, ttl_seconds)

            return True

        except Exception as e:
            logger.error(f"Write-through failed for key {key}: {e}")
            return False


class WriteBehind:
    """
    استراتيجية الكتابة المتأخرة
    Write-Behind Strategy

    تكتب إلى التخزين المؤقت فوراً وتؤجل الكتابة للمخزن الدائم.
    Writes to cache immediately and defers persistent store write.
    """

    def __init__(
        self,
        cache_write: Callable[[str, Any, Optional[float]], Any],
        store_write: Callable[[str, Any], Any],
        batch_size: int = 100,
        flush_interval_seconds: float = 5.0,
    ):
        """
        تهيئة الاستراتيجية

        Args:
            cache_write: دالة الكتابة للتخزين المؤقت
            store_write: دالة الكتابة للمخزن الدائم
            batch_size: حجم الدفعة
            flush_interval_seconds: فترة التنظيف
        """
        self.cache_write = cache_write
        self.store_write = store_write
        self.batch_size = batch_size
        self.flush_interval_seconds = flush_interval_seconds

        # Write queue
        self._queue: list[WriteOperation] = []
        self._lock = asyncio.Lock()

        # Background task
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """بدء الاستراتيجية"""
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("WriteBehind started")

    async def stop(self) -> None:
        """إيقاف الاستراتيجية"""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush remaining
        await self._flush()

        logger.info("WriteBehind stopped")

    async def write(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
    ) -> bool:
        """
        كتابة مؤجلة
        Deferred write
        """
        try:
            # Write to cache immediately
            if asyncio.iscoroutinefunction(self.cache_write):
                await self.cache_write(key, value, ttl_seconds)
            else:
                self.cache_write(key, value, ttl_seconds)

            # Queue for store write
            async with self._lock:
                self._queue.append(WriteOperation(
                    key=key,
                    value=value,
                    ttl_seconds=ttl_seconds,
                ))

                # Flush if batch size reached
                if len(self._queue) >= self.batch_size:
                    await self._flush()

            return True

        except Exception as e:
            logger.error(f"Write-behind failed for key {key}: {e}")
            return False

    async def _flush_loop(self) -> None:
        """حلقة التنظيف"""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval_seconds)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Flush loop error: {e}")

    async def _flush(self) -> None:
        """تنظيف قائمة الانتظار"""
        async with self._lock:
            if not self._queue:
                return

            operations = self._queue.copy()
            self._queue.clear()

        # Write all to store
        for op in operations:
            try:
                if asyncio.iscoroutinefunction(self.store_write):
                    await self.store_write(op.key, op.value)
                else:
                    self.store_write(op.key, op.value)
            except Exception as e:
                logger.error(f"Store write failed for {op.key}: {e}")
                # Re-queue on failure
                async with self._lock:
                    self._queue.append(op)

        if operations:
            logger.debug(f"Flushed {len(operations)} write operations")

    @property
    def pending_writes(self) -> int:
        """عدد العمليات المعلقة"""
        return len(self._queue)


class WriteAround:
    """
    استراتيجية الكتابة حول التخزين المؤقت
    Write-Around Strategy

    تكتب مباشرة إلى المخزن الدائم وتحدث التخزين المؤقت عند القراءة.
    Writes directly to store and updates cache on read.
    """

    def __init__(
        self,
        store_write: Callable[[str, Any], Any],
        cache_invalidate: Callable[[str], Any],
    ):
        """
        تهيئة الاستراتيجية

        Args:
            store_write: دالة الكتابة للمخزن الدائم
            cache_invalidate: دالة إبطال التخزين المؤقت
        """
        self.store_write = store_write
        self.cache_invalidate = cache_invalidate

    async def write(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
    ) -> bool:
        """
        كتابة حول التخزين المؤقت
        Write around cache
        """
        try:
            # Write to store only
            if asyncio.iscoroutinefunction(self.store_write):
                await self.store_write(key, value)
            else:
                self.store_write(key, value)

            # Invalidate cache
            if asyncio.iscoroutinefunction(self.cache_invalidate):
                await self.cache_invalidate(key)
            else:
                self.cache_invalidate(key)

            return True

        except Exception as e:
            logger.error(f"Write-around failed for key {key}: {e}")
            return False
