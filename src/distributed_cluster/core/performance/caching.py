"""
Caching Decorators - مزخرفات التخزين المؤقت
==========================================

Caching Decorators
------------------

This module provides caching decorators for functions.

يوفر هذا الملف مزخرفات التخزين المؤقت للدوال.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class CacheEntry:
    """
    مدخلة ذاكرة مؤقتة
    Cache entry
    """
    value: Any
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    ttl_seconds: Optional[float] = None

    def is_expired(self) -> bool:
        """هل انتهت الصلاحية؟"""
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    def touch(self) -> None:
        """تحديث وقت الوصول"""
        self.accessed_at = time.time()
        self.access_count += 1


class LRUCache:
    """
    ذاكرة مؤقتة LRU
    LRU Cache

    تخزين مؤقت بسياسة الأقل استخداماً مؤخراً.
    Cache with Least Recently Used eviction policy.
    """

    def __init__(
        self,
        max_size: int = 128,
        ttl_seconds: Optional[float] = None,
    ):
        """
        تهيئة الذاكرة المؤقتة

        Args:
            max_size: الحد الأقصى للعناصر
            ttl_seconds: مدة الصلاحية
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """الحصول على قيمة"""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.touch()
            self._hits += 1

            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """تعيين قيمة"""
        with self._lock:
            # Remove oldest if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)

            self._cache[key] = CacheEntry(
                value=value,
                ttl_seconds=ttl_seconds or self.ttl_seconds,
            )

    def delete(self, key: str) -> bool:
        """حذف قيمة"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """مسح الذاكرة المؤقتة"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def cleanup_expired(self) -> int:
        """تنظيف العناصر المنتهية"""
        removed = 0
        with self._lock:
            keys_to_remove = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in keys_to_remove:
                del self._cache[key]
                removed += 1
        return removed

    @property
    def hit_rate(self) -> float:
        """نسبة الإصابة"""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def stats(self) -> dict[str, Any]:
        """الإحصائيات"""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }


class AsyncLRUCache:
    """
    ذاكرة مؤقتة LRU غير متزامنة
    Async LRU Cache
    """

    def __init__(
        self,
        max_size: int = 128,
        ttl_seconds: Optional[float] = None,
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Optional[Any]:
        """الحصول على قيمة"""
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return None

            self._cache.move_to_end(key)
            entry.touch()
            self._hits += 1

            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """تعيين قيمة"""
        async with self._lock:
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)

            self._cache[key] = CacheEntry(
                value=value,
                ttl_seconds=ttl_seconds or self.ttl_seconds,
            )

    async def delete(self, key: str) -> bool:
        """حذف قيمة"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """مسح الذاكرة المؤقتة"""
        async with self._lock:
            self._cache.clear()


# =============================================================================
# Decorators / المزخرفات
# =============================================================================

def _make_key(*args: Any, **kwargs: Any) -> str:
    """إنشاء مفتاح من المعاملات"""
    key_data = json.dumps(
        {"args": args, "kwargs": kwargs},
        sort_keys=True,
        default=str,
    )
    # nosec B324 - MD5 used for cache key generation, not security
    return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()


def memoize(
    max_size: int = 128,
    ttl_seconds: Optional[float] = None,
) -> Callable[[F], F]:
    """
    مزخرف للتخزين المؤقت (دوال متزامنة)
    Memoization decorator (sync functions)

    Args:
        max_size: الحد الأقصى للعناصر
        ttl_seconds: مدة الصلاحية

    Returns:
        المزخرف
    """
    cache = LRUCache(max_size=max_size, ttl_seconds=ttl_seconds)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _make_key(*args, **kwargs)

            result = cache.get(key)
            if result is not None:
                return result

            result = func(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper.cache = cache  # type: ignore
        wrapper.cache_clear = cache.clear  # type: ignore

        return wrapper  # type: ignore

    return decorator


def async_lru_cache(
    max_size: int = 128,
    ttl_seconds: Optional[float] = None,
) -> Callable[[F], F]:
    """
    مزخرف للتخزين المؤقت (دوال غير متزامنة)
    Async LRU cache decorator

    Args:
        max_size: الحد الأقصى للعناصر
        ttl_seconds: مدة الصلاحية

    Returns:
        المزخرف
    """
    cache = AsyncLRUCache(max_size=max_size, ttl_seconds=ttl_seconds)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _make_key(*args, **kwargs)

            result = await cache.get(key)
            if result is not None:
                return result

            result = await func(*args, **kwargs)
            await cache.set(key, result)
            return result

        wrapper.cache = cache  # type: ignore
        wrapper.cache_clear = cache.clear  # type: ignore

        return wrapper  # type: ignore

    return decorator


def timed_cache(
    ttl_seconds: float,
    max_size: int = 128,
) -> Callable[[F], F]:
    """
    مزخرف للتخزين المؤقت مع مهلة زمنية
    Timed cache decorator

    Args:
        ttl_seconds: مدة الصلاحية
        max_size: الحد الأقصى للعناصر

    Returns:
        المزخرف
    """
    return memoize(max_size=max_size, ttl_seconds=ttl_seconds)


def cached_property(ttl_seconds: Optional[float] = None):
    """
    مزخرف للخاصية المخزنة مؤقتاً
    Cached property decorator
    """
    def decorator(func: Callable) -> property:
        attr_name = f"_cached_{func.__name__}"
        time_attr = f"_cached_{func.__name__}_time"

        @property
        @functools.wraps(func)
        def wrapper(self) -> Any:
            # Check if cached and not expired
            if hasattr(self, attr_name):
                if ttl_seconds is None:
                    return getattr(self, attr_name)

                cached_time = getattr(self, time_attr, 0)
                if time.time() - cached_time < ttl_seconds:
                    return getattr(self, attr_name)

            # Compute and cache
            value = func(self)
            setattr(self, attr_name, value)
            setattr(self, time_attr, time.time())

            return value

        return wrapper  # type: ignore

    return decorator


# =============================================================================
# Utility Classes / فئات مساعدة
# =============================================================================

class CacheManager:
    """
    مدير الذاكرة المؤقتة
    Cache Manager

    يدير مجموعة من الذاكرات المؤقتة المسماة.
    Manages a collection of named caches.
    """

    def __init__(self):
        self._caches: dict[str, LRUCache] = {}
        self._async_caches: dict[str, AsyncLRUCache] = {}

    def get_cache(
        self,
        name: str,
        max_size: int = 128,
        ttl_seconds: Optional[float] = None,
    ) -> LRUCache:
        """الحصول على أو إنشاء ذاكرة مؤقتة"""
        if name not in self._caches:
            self._caches[name] = LRUCache(
                max_size=max_size,
                ttl_seconds=ttl_seconds,
            )
        return self._caches[name]

    def get_async_cache(
        self,
        name: str,
        max_size: int = 128,
        ttl_seconds: Optional[float] = None,
    ) -> AsyncLRUCache:
        """الحصول على أو إنشاء ذاكرة مؤقتة غير متزامنة"""
        if name not in self._async_caches:
            self._async_caches[name] = AsyncLRUCache(
                max_size=max_size,
                ttl_seconds=ttl_seconds,
            )
        return self._async_caches[name]

    def clear_all(self) -> None:
        """مسح جميع الذاكرات المؤقتة"""
        for cache in self._caches.values():
            cache.clear()

    def stats(self) -> dict[str, Any]:
        """إحصائيات جميع الذاكرات"""
        return {
            name: cache.stats()
            for name, cache in self._caches.items()
        }


# Global cache manager
cache_manager = CacheManager()


# =============================================================================
# Advanced Caching Strategies / استراتيجيات التخزين المؤقت المتقدمة
# =============================================================================


class CacheStrategy(str):
    """Cache strategy types."""

    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    FIFO = "fifo"  # First In First Out
    TTL = "ttl"  # Time To Live based
    ARC = "arc"  # Adaptive Replacement Cache


@dataclass
class CacheConfig:
    """
    تكوين الذاكرة المؤقتة المتقدم.
    Advanced cache configuration.
    """

    max_size: int = 1000
    ttl_seconds: Optional[float] = None
    strategy: str = CacheStrategy.LRU
    write_through: bool = False
    write_behind: bool = False
    write_behind_delay: float = 1.0
    namespace: str = "default"
    serializer: Optional[Callable[[Any], bytes]] = None
    deserializer: Optional[Callable[[bytes], Any]] = None


class LFUCache:
    """
    ذاكرة مؤقتة LFU - الأقل استخداماً
    Least Frequently Used Cache

    تحذف العناصر الأقل استخداماً عند امتلاء الذاكرة.
    Evicts least frequently used items when cache is full.
    """

    def __init__(
        self,
        max_size: int = 128,
        ttl_seconds: Optional[float] = None,
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, CacheEntry] = {}
        self._freq: dict[str, int] = {}  # frequency counter
        self._min_freq: int = 0
        self._freq_to_keys: dict[int, OrderedDict] = {}
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """الحصول على قيمة"""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            if entry.is_expired():
                self._remove(key)
                self._misses += 1
                return None

            # Update frequency
            self._update_freq(key)
            entry.touch()
            self._hits += 1

            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """تعيين قيمة"""
        with self._lock:
            if key in self._cache:
                # Update existing
                self._cache[key] = CacheEntry(
                    value=value,
                    ttl_seconds=ttl_seconds or self.ttl_seconds,
                )
                self._update_freq(key)
                return

            # Evict if necessary
            if len(self._cache) >= self.max_size:
                self._evict()

            # Add new entry
            self._cache[key] = CacheEntry(
                value=value,
                ttl_seconds=ttl_seconds or self.ttl_seconds,
            )
            self._freq[key] = 1
            self._min_freq = 1

            if 1 not in self._freq_to_keys:
                self._freq_to_keys[1] = OrderedDict()
            self._freq_to_keys[1][key] = None

    def _update_freq(self, key: str) -> None:
        """تحديث تردد الوصول"""
        freq = self._freq[key]
        self._freq[key] = freq + 1

        # Remove from old frequency list
        del self._freq_to_keys[freq][key]
        if not self._freq_to_keys[freq]:
            del self._freq_to_keys[freq]
            if self._min_freq == freq:
                self._min_freq = freq + 1

        # Add to new frequency list
        new_freq = freq + 1
        if new_freq not in self._freq_to_keys:
            self._freq_to_keys[new_freq] = OrderedDict()
        self._freq_to_keys[new_freq][key] = None

    def _evict(self) -> None:
        """حذف أقل العناصر استخداماً"""
        if self._min_freq in self._freq_to_keys:
            keys = self._freq_to_keys[self._min_freq]
            if keys:
                key, _ = keys.popitem(last=False)
                self._remove(key)

    def _remove(self, key: str) -> None:
        """حذف عنصر"""
        if key in self._cache:
            del self._cache[key]
        if key in self._freq:
            freq = self._freq[key]
            del self._freq[key]
            if freq in self._freq_to_keys and key in self._freq_to_keys[freq]:
                del self._freq_to_keys[freq][key]

    def clear(self) -> None:
        """مسح الذاكرة المؤقتة"""
        with self._lock:
            self._cache.clear()
            self._freq.clear()
            self._freq_to_keys.clear()
            self._min_freq = 0
            self._hits = 0
            self._misses = 0

    @property
    def hit_rate(self) -> float:
        """نسبة الإصابة"""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def stats(self) -> dict[str, Any]:
        """الإحصائيات"""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
            "strategy": "LFU",
        }


class MultiLevelCache:
    """
    ذاكرة مؤقتة متعددة المستويات
    Multi-Level Cache (L1/L2/L3)

    Usage:
        cache = MultiLevelCache([
            LRUCache(max_size=100, ttl_seconds=60),    # L1: Fast, small
            LRUCache(max_size=1000, ttl_seconds=300),  # L2: Medium
            LRUCache(max_size=10000, ttl_seconds=3600), # L3: Large, slow
        ])
    """

    def __init__(
        self,
        levels: list[LRUCache],
        propagate_on_hit: bool = True,
    ):
        """
        تهيئة الذاكرة المؤقتة متعددة المستويات.

        Args:
            levels: قائمة مستويات الذاكرة المؤقتة (من الأسرع للأبطأ)
            propagate_on_hit: نسخ للمستويات الأعلى عند الإصابة
        """
        self.levels = levels
        self.propagate_on_hit = propagate_on_hit
        self._lock = Lock()

    def get(self, key: str) -> Optional[Any]:
        """الحصول على قيمة من أي مستوى"""
        with self._lock:
            for i, level in enumerate(self.levels):
                value = level.get(key)
                if value is not None:
                    # Propagate to higher levels
                    if self.propagate_on_hit and i > 0:
                        for j in range(i):
                            self.levels[j].set(key, value)
                    return value
            return None

    def set(
        self,
        key: str,
        value: Any,
        levels: Optional[list[int]] = None,
    ) -> None:
        """
        تعيين قيمة في مستويات محددة.

        Args:
            key: المفتاح
            value: القيمة
            levels: قائمة فهارس المستويات (None = كل المستويات)
        """
        with self._lock:
            target_levels = levels if levels is not None else range(len(self.levels))
            for i in target_levels:
                if i < len(self.levels):
                    self.levels[i].set(key, value)

    def delete(self, key: str) -> bool:
        """حذف من جميع المستويات"""
        with self._lock:
            deleted = False
            for level in self.levels:
                if level.delete(key):
                    deleted = True
            return deleted

    def clear(self) -> None:
        """مسح جميع المستويات"""
        with self._lock:
            for level in self.levels:
                level.clear()

    def stats(self) -> dict[str, Any]:
        """إحصائيات جميع المستويات"""
        return {
            f"L{i + 1}": level.stats()
            for i, level in enumerate(self.levels)
        }


class WriteThroughCache:
    """
    ذاكرة مؤقتة Write-Through
    Write-Through Cache

    تكتب للذاكرة المؤقتة والمخزن الخلفي بشكل متزامن.
    Writes to cache and backing store synchronously.
    """

    def __init__(
        self,
        cache: LRUCache,
        write_func: Callable[[str, Any], None],
        read_func: Callable[[str], Optional[Any]],
        delete_func: Optional[Callable[[str], None]] = None,
    ):
        """
        تهيئة Write-Through Cache.

        Args:
            cache: الذاكرة المؤقتة الأساسية
            write_func: دالة الكتابة للمخزن الخلفي
            read_func: دالة القراءة من المخزن الخلفي
            delete_func: دالة الحذف من المخزن الخلفي
        """
        self.cache = cache
        self.write_func = write_func
        self.read_func = read_func
        self.delete_func = delete_func

    def get(self, key: str) -> Optional[Any]:
        """قراءة من الذاكرة المؤقتة أو المخزن الخلفي"""
        # Try cache first
        value = self.cache.get(key)
        if value is not None:
            return value

        # Read from backing store
        value = self.read_func(key)
        if value is not None:
            self.cache.set(key, value)
        return value

    def set(self, key: str, value: Any) -> None:
        """كتابة للذاكرة المؤقتة والمخزن الخلفي معاً"""
        # Write to backing store first
        self.write_func(key, value)
        # Then update cache
        self.cache.set(key, value)

    def delete(self, key: str) -> bool:
        """حذف من الذاكرة المؤقتة والمخزن الخلفي"""
        self.cache.delete(key)
        if self.delete_func:
            self.delete_func(key)
            return True
        return False


class WriteBehindCache:
    """
    ذاكرة مؤقتة Write-Behind (Write-Back)
    Write-Behind Cache

    تكتب للذاكرة المؤقتة فوراً وللمخزن الخلفي بشكل غير متزامن.
    Writes to cache immediately, backing store asynchronously.
    """

    def __init__(
        self,
        cache: LRUCache,
        write_func: Callable[[str, Any], None],
        read_func: Callable[[str], Optional[Any]],
        flush_interval: float = 5.0,
        batch_size: int = 100,
    ):
        """
        تهيئة Write-Behind Cache.

        Args:
            cache: الذاكرة المؤقتة الأساسية
            write_func: دالة الكتابة للمخزن الخلفي
            read_func: دالة القراءة من المخزن الخلفي
            flush_interval: فترة التفريغ بالثواني
            batch_size: حجم الدفعة للتفريغ
        """
        self.cache = cache
        self.write_func = write_func
        self.read_func = read_func
        self.flush_interval = flush_interval
        self.batch_size = batch_size

        self._dirty: OrderedDict[str, Any] = OrderedDict()
        self._lock = Lock()
        self._running = False
        self._flush_thread: Optional[Any] = None

    def get(self, key: str) -> Optional[Any]:
        """قراءة من الذاكرة المؤقتة"""
        # Check dirty buffer first
        with self._lock:
            if key in self._dirty:
                return self._dirty[key]

        # Then cache
        value = self.cache.get(key)
        if value is not None:
            return value

        # Finally backing store
        value = self.read_func(key)
        if value is not None:
            self.cache.set(key, value)
        return value

    def set(self, key: str, value: Any) -> None:
        """كتابة للذاكرة المؤقتة (التفريغ لاحقاً)"""
        self.cache.set(key, value)

        with self._lock:
            self._dirty[key] = value

            # Auto-flush if batch size reached
            if len(self._dirty) >= self.batch_size:
                self._flush_batch()

    def start(self) -> None:
        """بدء خيط التفريغ"""
        import threading

        if self._running:
            return

        self._running = True

        def flush_loop():
            while self._running:
                time.sleep(self.flush_interval)
                self.flush()

        self._flush_thread = threading.Thread(target=flush_loop, daemon=True)
        self._flush_thread.start()

    def stop(self) -> None:
        """إيقاف خيط التفريغ"""
        self._running = False
        if self._flush_thread:
            self._flush_thread.join(timeout=5.0)
        # Final flush
        self.flush()

    def flush(self) -> int:
        """تفريغ جميع التغييرات المعلقة"""
        flushed = 0
        with self._lock:
            while self._dirty:
                flushed += self._flush_batch()
        return flushed

    def _flush_batch(self) -> int:
        """تفريغ دفعة من التغييرات"""
        count = 0
        batch = []

        # Get batch from dirty buffer
        while self._dirty and count < self.batch_size:
            key, value = self._dirty.popitem(last=False)
            batch.append((key, value))
            count += 1

        # Write to backing store
        for key, value in batch:
            try:
                self.write_func(key, value)
            except Exception as e:
                logger.error(f"Write-behind failed for {key}: {e}")
                # Re-add to dirty buffer
                self._dirty[key] = value

        return count


class CacheInvalidator:
    """
    مُبطل الذاكرة المؤقتة
    Cache Invalidator

    يدير إبطال الذاكرة المؤقتة بناءً على الأنماط والتبعيات.
    Manages cache invalidation based on patterns and dependencies.
    """

    def __init__(self, cache: LRUCache):
        self.cache = cache
        self._dependencies: dict[str, set[str]] = {}  # key -> dependent keys
        self._patterns: list[tuple[str, set[str]]] = []  # (pattern, keys)
        self._lock = Lock()

    def register_dependency(self, key: str, depends_on: str) -> None:
        """تسجيل تبعية بين المفاتيح"""
        with self._lock:
            if depends_on not in self._dependencies:
                self._dependencies[depends_on] = set()
            self._dependencies[depends_on].add(key)

    def register_pattern(self, pattern: str, key: str) -> None:
        """تسجيل مفتاح مع نمط للإبطال"""
        import re

        with self._lock:
            for p, keys in self._patterns:
                if p == pattern:
                    keys.add(key)
                    return

            self._patterns.append((pattern, {key}))

    def invalidate(self, key: str) -> int:
        """إبطال مفتاح وجميع المفاتيح التابعة له"""
        invalidated = 0

        with self._lock:
            # Delete the key itself
            if self.cache.delete(key):
                invalidated += 1

            # Invalidate dependencies
            if key in self._dependencies:
                for dep_key in self._dependencies[key]:
                    if self.cache.delete(dep_key):
                        invalidated += 1
                del self._dependencies[key]

        return invalidated

    def invalidate_pattern(self, pattern: str) -> int:
        """إبطال جميع المفاتيح المطابقة للنمط"""
        import re

        invalidated = 0

        with self._lock:
            regex = re.compile(pattern)

            for p, keys in self._patterns:
                if regex.match(p):
                    for key in keys:
                        if self.cache.delete(key):
                            invalidated += 1
                    keys.clear()

        return invalidated

    def invalidate_all(self) -> None:
        """إبطال كل الذاكرة المؤقتة"""
        with self._lock:
            self.cache.clear()
            self._dependencies.clear()
            for _, keys in self._patterns:
                keys.clear()


class AsyncMultiLevelCache:
    """
    ذاكرة مؤقتة متعددة المستويات غير متزامنة
    Async Multi-Level Cache
    """

    def __init__(
        self,
        levels: list[AsyncLRUCache],
        propagate_on_hit: bool = True,
    ):
        self.levels = levels
        self.propagate_on_hit = propagate_on_hit
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """الحصول على قيمة من أي مستوى"""
        async with self._lock:
            for i, level in enumerate(self.levels):
                value = await level.get(key)
                if value is not None:
                    if self.propagate_on_hit and i > 0:
                        for j in range(i):
                            await self.levels[j].set(key, value)
                    return value
            return None

    async def set(
        self,
        key: str,
        value: Any,
        levels: Optional[list[int]] = None,
    ) -> None:
        """تعيين قيمة في مستويات محددة"""
        async with self._lock:
            target_levels = levels if levels is not None else range(len(self.levels))
            for i in target_levels:
                if i < len(self.levels):
                    await self.levels[i].set(key, value)

    async def delete(self, key: str) -> bool:
        """حذف من جميع المستويات"""
        async with self._lock:
            deleted = False
            for level in self.levels:
                if await level.delete(key):
                    deleted = True
            return deleted

    async def clear(self) -> None:
        """مسح جميع المستويات"""
        async with self._lock:
            for level in self.levels:
                await level.clear()


def create_cache(
    config: CacheConfig,
    write_func: Optional[Callable[[str, Any], None]] = None,
    read_func: Optional[Callable[[str], Optional[Any]]] = None,
) -> LRUCache | LFUCache | WriteThroughCache | WriteBehindCache:
    """
    إنشاء ذاكرة مؤقتة بناءً على التكوين.
    Create cache based on configuration.

    Args:
        config: تكوين الذاكرة المؤقتة
        write_func: دالة الكتابة للمخزن الخلفي
        read_func: دالة القراءة من المخزن الخلفي

    Returns:
        الذاكرة المؤقتة المناسبة
    """
    # Create base cache based on strategy
    if config.strategy == CacheStrategy.LFU:
        base_cache = LFUCache(
            max_size=config.max_size,
            ttl_seconds=config.ttl_seconds,
        )
    else:
        base_cache = LRUCache(
            max_size=config.max_size,
            ttl_seconds=config.ttl_seconds,
        )

    # Wrap with write strategy if needed
    if config.write_through and write_func and read_func:
        return WriteThroughCache(
            cache=base_cache,
            write_func=write_func,
            read_func=read_func,
        )
    elif config.write_behind and write_func and read_func:
        return WriteBehindCache(
            cache=base_cache,
            write_func=write_func,
            read_func=read_func,
            flush_interval=config.write_behind_delay,
        )

    return base_cache
