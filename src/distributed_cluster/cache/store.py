"""
Cache Store - مخزن التخزين المؤقت
=================================

Local Cache Store
-----------------

This module provides the local cache store implementation.

يوفر هذا الملف تطبيق مخزن التخزين المؤقت المحلي.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import pickle
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Callable, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """
    مدخلة التخزين المؤقت
    Cache entry
    """
    key: str
    value: T
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    access_count: int = 0
    size_bytes: int = 0
    tags: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """هل انتهت الصلاحية؟"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        """تحديث وقت الوصول"""
        self.accessed_at = time.time()
        self.access_count += 1

    @property
    def ttl_seconds(self) -> Optional[float]:
        """الوقت المتبقي للانتهاء"""
        if self.expires_at is None:
            return None
        remaining = self.expires_at - time.time()
        return max(0, remaining)


@dataclass
class CacheConfig:
    """
    إعدادات التخزين المؤقت
    Cache configuration
    """
    # Capacity
    max_size: int = 10000
    max_memory_bytes: int = 1024 * 1024 * 1024  # 1 GB

    # TTL
    default_ttl_seconds: Optional[float] = 3600  # 1 hour
    max_ttl_seconds: float = 86400 * 7  # 7 days

    # Eviction
    eviction_policy: str = "lru"  # lru, lfu, fifo, random
    eviction_batch_size: int = 100

    # Persistence
    persistence_enabled: bool = False
    persistence_path: str = ".cache_store"
    persistence_interval_seconds: int = 300

    # Compression
    compression_enabled: bool = False
    compression_threshold_bytes: int = 1024

    # Statistics
    stats_enabled: bool = True


class CacheStore:
    """
    مخزن التخزين المؤقت المحلي
    Local Cache Store

    يوفر تخزين مؤقت محلي مع سياسات إخلاء متعددة.
    Provides local caching with multiple eviction policies.
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        """
        تهيئة المخزن

        Args:
            config: إعدادات التخزين المؤقت
        """
        self.config = config or CacheConfig()

        # Storage
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = Lock()

        # Memory tracking
        self._current_memory_bytes = 0

        # Statistics
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0,
            "expirations": 0,
        }

        # Background tasks
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء المخزن"""
        self._running = True

        # Load from persistence
        if self.config.persistence_enabled:
            await self._load_from_disk()

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("CacheStore started")

    async def stop(self) -> None:
        """إيقاف المخزن"""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Save to persistence
        if self.config.persistence_enabled:
            await self._save_to_disk()

        logger.info("CacheStore stopped")

    # =========================================================================
    # Basic Operations
    # =========================================================================

    async def get(self, key: str) -> Optional[Any]:
        """
        الحصول على قيمة
        Get value by key
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats["misses"] += 1
                return None

            if entry.is_expired():
                self._delete_entry(key)
                self._stats["misses"] += 1
                self._stats["expirations"] += 1
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            entry.touch()
            self._stats["hits"] += 1

            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
        tags: Optional[set[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        تعيين قيمة
        Set value with optional TTL
        """
        # Calculate expiration
        ttl = ttl_seconds or self.config.default_ttl_seconds
        if ttl is not None:
            ttl = min(ttl, self.config.max_ttl_seconds)
            expires_at = time.time() + ttl
        else:
            expires_at = None

        # Calculate size
        try:
            size_bytes = len(pickle.dumps(value))
        except Exception:
            size_bytes = 0

        # Create entry
        entry = CacheEntry(
            key=key,
            value=value,
            expires_at=expires_at,
            size_bytes=size_bytes,
            tags=tags or set(),
            metadata=metadata or {},
        )

        with self._lock:
            # Check if updating existing
            if key in self._cache:
                old_entry = self._cache[key]
                self._current_memory_bytes -= old_entry.size_bytes

            # Ensure capacity
            await self._ensure_capacity(size_bytes)

            # Store entry
            self._cache[key] = entry
            self._cache.move_to_end(key)
            self._current_memory_bytes += size_bytes
            self._stats["sets"] += 1

        return True

    async def delete(self, key: str) -> bool:
        """
        حذف قيمة
        Delete value by key
        """
        with self._lock:
            if key in self._cache:
                self._delete_entry(key)
                self._stats["deletes"] += 1
                return True
            return False

    async def exists(self, key: str) -> bool:
        """
        التحقق من وجود مفتاح
        Check if key exists
        """
        with self._lock:
            if key not in self._cache:
                return False

            entry = self._cache[key]
            if entry.is_expired():
                self._delete_entry(key)
                return False

            return True

    async def clear(self) -> int:
        """
        مسح جميع المدخلات
        Clear all entries
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._current_memory_bytes = 0
            return count

    # =========================================================================
    # Extended Operations
    # =========================================================================

    async def mget(self, keys: list[str]) -> dict[str, Any]:
        """الحصول على قيم متعددة"""
        results = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                results[key] = value
        return results

    async def mset(
        self,
        items: dict[str, Any],
        ttl_seconds: Optional[float] = None,
    ) -> bool:
        """تعيين قيم متعددة"""
        for key, value in items.items():
            await self.set(key, value, ttl_seconds=ttl_seconds)
        return True

    async def incr(self, key: str, amount: int = 1) -> int:
        """زيادة قيمة رقمية"""
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                value = amount
            else:
                if entry.is_expired():
                    value = amount
                else:
                    value = int(entry.value) + amount

            await self.set(key, value)
            return value

    async def decr(self, key: str, amount: int = 1) -> int:
        """تقليل قيمة رقمية"""
        return await self.incr(key, -amount)

    async def expire(self, key: str, ttl_seconds: float) -> bool:
        """تعيين وقت انتهاء"""
        with self._lock:
            if key not in self._cache:
                return False

            entry = self._cache[key]
            entry.expires_at = time.time() + ttl_seconds
            entry.updated_at = time.time()
            return True

    async def ttl(self, key: str) -> Optional[float]:
        """الحصول على الوقت المتبقي"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            return entry.ttl_seconds

    async def keys(self, pattern: str = "*") -> list[str]:
        """قائمة المفاتيح"""
        import fnmatch

        with self._lock:
            if pattern == "*":
                return list(self._cache.keys())

            return [
                key for key in self._cache.keys()
                if fnmatch.fnmatch(key, pattern)
            ]

    async def get_by_tag(self, tag: str) -> dict[str, Any]:
        """الحصول على قيم بالوسم"""
        results = {}
        with self._lock:
            for key, entry in self._cache.items():
                if tag in entry.tags and not entry.is_expired():
                    results[key] = entry.value
        return results

    async def delete_by_tag(self, tag: str) -> int:
        """حذف قيم بالوسم"""
        deleted = 0
        with self._lock:
            keys_to_delete = [
                key for key, entry in self._cache.items()
                if tag in entry.tags
            ]
            for key in keys_to_delete:
                self._delete_entry(key)
                deleted += 1
        return deleted

    # =========================================================================
    # Eviction
    # =========================================================================

    async def _ensure_capacity(self, needed_bytes: int) -> None:
        """ضمان وجود سعة كافية"""
        # Check size limit
        while len(self._cache) >= self.config.max_size:
            await self._evict_one()

        # Check memory limit
        while self._current_memory_bytes + needed_bytes > self.config.max_memory_bytes:
            if not await self._evict_one():
                break

    async def _evict_one(self) -> bool:
        """إخلاء مدخلة واحدة"""
        if not self._cache:
            return False

        policy = self.config.eviction_policy

        if policy == "lru":
            # Least Recently Used - first item
            key = next(iter(self._cache))
        elif policy == "lfu":
            # Least Frequently Used
            key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].access_count,
            )
        elif policy == "fifo":
            # First In First Out
            key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].created_at,
            )
        elif policy == "random":
            import random
            key = random.choice(list(self._cache.keys()))
        else:
            key = next(iter(self._cache))

        self._delete_entry(key)
        self._stats["evictions"] += 1
        return True

    def _delete_entry(self, key: str) -> None:
        """حذف مدخلة"""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._current_memory_bytes -= entry.size_bytes

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def _cleanup_loop(self) -> None:
        """حلقة التنظيف"""
        while self._running:
            try:
                await asyncio.sleep(60)  # Every minute
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    async def _cleanup_expired(self) -> int:
        """تنظيف المدخلات المنتهية"""
        cleaned = 0
        now = time.time()

        with self._lock:
            keys_to_delete = [
                key for key, entry in self._cache.items()
                if entry.expires_at and now > entry.expires_at
            ]

            for key in keys_to_delete:
                self._delete_entry(key)
                cleaned += 1

        if cleaned > 0:
            self._stats["expirations"] += cleaned
            logger.debug(f"Cleaned up {cleaned} expired entries")

        return cleaned

    # =========================================================================
    # Persistence
    # =========================================================================

    async def _save_to_disk(self) -> None:
        """حفظ إلى القرص"""
        import os

        path = self.config.persistence_path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        with self._lock:
            data = {
                key: {
                    "value": entry.value,
                    "created_at": entry.created_at,
                    "expires_at": entry.expires_at,
                    "tags": list(entry.tags),
                }
                for key, entry in self._cache.items()
                if not entry.is_expired()
            }

        with open(path, "wb") as f:
            pickle.dump(data, f)

        logger.info(f"Saved {len(data)} cache entries to disk")

    async def _load_from_disk(self) -> None:
        """تحميل من القرص"""
        import os

        path = self.config.persistence_path

        if not os.path.exists(path):
            return

        try:
            with open(path, "rb") as f:
                # nosec B301 - Loading from local file created by this system
                data = pickle.load(f)

            count = 0
            for key, entry_data in data.items():
                # Skip expired entries
                expires_at = entry_data.get("expires_at")
                if expires_at and time.time() > expires_at:
                    continue

                await self.set(
                    key=key,
                    value=entry_data["value"],
                    ttl_seconds=expires_at - time.time() if expires_at else None,
                    tags=set(entry_data.get("tags", [])),
                )
                count += 1

            logger.info(f"Loaded {count} cache entries from disk")

        except Exception as e:
            logger.error(f"Failed to load cache from disk: {e}")

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """الحصول على الإحصائيات"""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0

        return {
            **self._stats,
            "hit_rate": hit_rate,
            "size": len(self._cache),
            "memory_bytes": self._current_memory_bytes,
            "max_size": self.config.max_size,
            "max_memory_bytes": self.config.max_memory_bytes,
        }

    @property
    def size(self) -> int:
        """حجم التخزين المؤقت"""
        return len(self._cache)

    @property
    def memory_bytes(self) -> int:
        """الذاكرة المستخدمة"""
        return self._current_memory_bytes
