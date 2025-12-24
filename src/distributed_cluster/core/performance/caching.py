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
    return hashlib.md5(key_data.encode()).hexdigest()


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
