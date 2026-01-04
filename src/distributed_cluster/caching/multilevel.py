"""
Multi-level caching with L1 (memory) and L2 (distributed) caches.
"""

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .backends import CacheBackend, MemoryBackend
from .cache import Cache, CacheConfig, CacheStats

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """Cache hierarchy levels."""
    L1 = 1  # Fastest, smallest (in-process memory)
    L2 = 2  # Fast, larger (local Redis/Memcached)
    L3 = 3  # Slower, largest (distributed cache)


class CacheTier(ABC):
    """Abstract base class for cache tiers."""

    def __init__(self, level: CacheLevel, backend: CacheBackend):
        self.level = level
        self.backend = backend
        self.stats = CacheStats()
        self._enabled = True

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    @abstractmethod
    def get(self, key: str) -> Optional[bytes]:
        pass

    @abstractmethod
    def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    def invalidate(self, key: str) -> None:
        pass


class L1Cache(CacheTier):
    """L1 in-memory cache tier."""

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,  # 5 minutes for L1
        backend: Optional[MemoryBackend] = None
    ):
        self._backend = backend or MemoryBackend(max_size=max_size, default_ttl=default_ttl)
        super().__init__(CacheLevel.L1, self._backend)
        self.max_size = max_size
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[bytes]:
        if not self._enabled:
            return None

        start = time.time()
        value = self.backend.get(key)
        elapsed = (time.time() - start) * 1000

        if value is not None:
            self.stats.record_hit(elapsed, len(value))
        else:
            self.stats.record_miss(elapsed)

        return value

    def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        if not self._enabled:
            return False

        start = time.time()
        result = self.backend.set(key, value, ttl or self.default_ttl)
        elapsed = (time.time() - start) * 1000

        if result:
            self.stats.record_set(elapsed, len(value))

        return result

    def delete(self, key: str) -> bool:
        if not self._enabled:
            return False
        result = self.backend.delete(key)
        if result:
            self.stats.record_delete()
        return result

    def invalidate(self, key: str) -> None:
        self.delete(key)

    def clear(self) -> int:
        return self.backend.clear()


class L2Cache(CacheTier):
    """L2 distributed cache tier (Redis/Memcached)."""

    def __init__(
        self,
        backend: CacheBackend,
        default_ttl: int = 3600,  # 1 hour for L2
        write_through: bool = True
    ):
        super().__init__(CacheLevel.L2, backend)
        self.default_ttl = default_ttl
        self.write_through = write_through

    def get(self, key: str) -> Optional[bytes]:
        if not self._enabled:
            return None

        start = time.time()
        value = self.backend.get(key)
        elapsed = (time.time() - start) * 1000

        if value is not None:
            self.stats.record_hit(elapsed, len(value))
        else:
            self.stats.record_miss(elapsed)

        return value

    def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        if not self._enabled:
            return False

        start = time.time()
        result = self.backend.set(key, value, ttl or self.default_ttl)
        elapsed = (time.time() - start) * 1000

        if result:
            self.stats.record_set(elapsed, len(value))

        return result

    def delete(self, key: str) -> bool:
        if not self._enabled:
            return False
        result = self.backend.delete(key)
        if result:
            self.stats.record_delete()
        return result

    def invalidate(self, key: str) -> None:
        self.delete(key)

    def get_many(self, keys: List[str]) -> Dict[str, Optional[bytes]]:
        if not self._enabled:
            return {key: None for key in keys}
        return self.backend.get_many(keys)

    def set_many(
        self,
        mapping: Dict[str, bytes],
        ttl: Optional[int] = None
    ) -> Dict[str, bool]:
        if not self._enabled:
            return {key: False for key in mapping}
        return self.backend.set_many(mapping, ttl or self.default_ttl)


@dataclass
class MultiLevelConfig:
    """Configuration for multi-level cache."""
    l1_enabled: bool = True
    l1_max_size: int = 1000
    l1_ttl: int = 300  # 5 minutes
    l2_enabled: bool = True
    l2_ttl: int = 3600  # 1 hour
    write_through: bool = True  # Write to all levels on set
    read_through: bool = True  # Populate lower levels on read
    async_populate: bool = False  # Populate L1 from L2 asynchronously
    invalidation_mode: str = "all"  # all, cascade, l1_only


class MultiLevelCache(Cache):
    """
    Multi-level cache implementation.

    L1: Fast in-process memory cache
    L2: Distributed cache (Redis, Memcached, etc.)
    """

    def __init__(
        self,
        l2_backend: CacheBackend,
        config: Optional[MultiLevelConfig] = None,
        cache_config: Optional[CacheConfig] = None
    ):
        super().__init__(cache_config)
        self.ml_config = config or MultiLevelConfig()

        # Initialize L1 cache
        self.l1: Optional[L1Cache] = None
        if self.ml_config.l1_enabled:
            self.l1 = L1Cache(
                max_size=self.ml_config.l1_max_size,
                default_ttl=self.ml_config.l1_ttl
            )

        # Initialize L2 cache
        self.l2: Optional[L2Cache] = None
        if self.ml_config.l2_enabled:
            self.l2 = L2Cache(
                backend=l2_backend,
                default_ttl=self.ml_config.l2_ttl,
                write_through=self.ml_config.write_through
            )

        self._lock = threading.RLock()
        self._async_executor = None

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache, checking L1 first, then L2."""
        full_key = self._make_key(key)
        start = time.time()

        # Try L1 first
        if self.l1 and self.l1.is_enabled:
            value = self.l1.get(full_key)
            if value is not None:
                elapsed = (time.time() - start) * 1000
                self.stats.record_hit(elapsed, len(value))
                try:
                    return self.serializer.deserialize(value)
                except Exception:
                    return default

        # Try L2
        if self.l2 and self.l2.is_enabled:
            value = self.l2.get(full_key)
            if value is not None:
                elapsed = (time.time() - start) * 1000
                self.stats.record_hit(elapsed, len(value))

                # Populate L1 if read-through enabled
                if self.ml_config.read_through and self.l1:
                    if self.ml_config.async_populate:
                        threading.Thread(
                            target=self.l1.set,
                            args=(full_key, value),
                            daemon=True
                        ).start()
                    else:
                        self.l1.set(full_key, value)

                try:
                    return self.serializer.deserialize(value)
                except Exception:
                    return default

        elapsed = (time.time() - start) * 1000
        self.stats.record_miss(elapsed)
        return default

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        l1_only: bool = False,
        l2_only: bool = False,
        **kwargs
    ) -> bool:
        """Set value in cache."""
        full_key = self._make_key(key)
        start = time.time()

        try:
            serialized = self.serializer.serialize(value)
        except Exception as e:
            logger.error(f"Serialization error: {e}")
            return False

        success = True

        # Write to L1
        if self.l1 and self.l1.is_enabled and not l2_only:
            l1_ttl = min(ttl or self.ml_config.l1_ttl, self.ml_config.l1_ttl)
            if not self.l1.set(full_key, serialized, l1_ttl):
                success = False

        # Write to L2
        if self.l2 and self.l2.is_enabled and not l1_only:
            if self.ml_config.write_through:
                l2_ttl = ttl or self.ml_config.l2_ttl
                if not self.l2.set(full_key, serialized, l2_ttl):
                    success = False

        elapsed = (time.time() - start) * 1000
        if success:
            self.stats.record_set(elapsed, len(serialized))

        return success

    def delete(self, key: str) -> bool:
        """Delete from all cache levels."""
        full_key = self._make_key(key)
        success = False

        if self.ml_config.invalidation_mode == "l1_only":
            if self.l1:
                success = self.l1.delete(full_key)
        elif self.ml_config.invalidation_mode == "cascade":
            # Delete L2 first, then L1
            if self.l2:
                success = self.l2.delete(full_key)
            if self.l1:
                self.l1.delete(full_key)
        else:  # all
            if self.l1:
                success = self.l1.delete(full_key) or success
            if self.l2:
                success = self.l2.delete(full_key) or success

        if success:
            self.stats.record_delete()

        return success

    def exists(self, key: str) -> bool:
        """Check if key exists in any cache level."""
        full_key = self._make_key(key)

        if self.l1 and self.l1.is_enabled:
            if self.l1.backend.exists(full_key):
                return True

        if self.l2 and self.l2.is_enabled:
            if self.l2.backend.exists(full_key):
                return True

        return False

    def clear(self) -> int:
        """Clear all cache levels."""
        count = 0

        if self.l1:
            count += self.l1.clear()

        if self.l2:
            count += self.l2.backend.clear()

        return count

    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern from L2 (L1 doesn't track all keys)."""
        full_pattern = self._make_key(pattern)

        if self.l2 and self.l2.is_enabled:
            return self.l2.backend.keys(full_pattern)

        if self.l1:
            return self.l1.backend.keys(full_pattern)

        return []

    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values, optimizing L2 batch fetch."""
        full_keys = {self._make_key(key): key for key in keys}
        results = {key: None for key in keys}
        missing_l1 = []

        # Check L1 first
        if self.l1 and self.l1.is_enabled:
            for full_key, original_key in full_keys.items():
                value = self.l1.get(full_key)
                if value is not None:
                    try:
                        results[original_key] = self.serializer.deserialize(value)
                    except Exception:
                        pass
                else:
                    missing_l1.append((full_key, original_key))
        else:
            missing_l1 = list(full_keys.items())

        # Batch fetch from L2
        if missing_l1 and self.l2 and self.l2.is_enabled:
            l2_keys = [fk for fk, _ in missing_l1]
            l2_values = self.l2.get_many(l2_keys)

            for full_key, original_key in missing_l1:
                value = l2_values.get(full_key)
                if value is not None:
                    try:
                        results[original_key] = self.serializer.deserialize(value)

                        # Populate L1
                        if self.ml_config.read_through and self.l1:
                            self.l1.set(full_key, value)
                    except Exception:
                        pass

        return results

    def set_many(
        self,
        mapping: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> Dict[str, bool]:
        """Set multiple values."""
        results = {}
        serialized = {}

        for key, value in mapping.items():
            try:
                full_key = self._make_key(key)
                serialized[full_key] = self.serializer.serialize(value)
                results[key] = True
            except Exception:
                results[key] = False

        # Write to L1
        if self.l1 and self.l1.is_enabled:
            l1_ttl = min(ttl or self.ml_config.l1_ttl, self.ml_config.l1_ttl)
            for full_key, data in serialized.items():
                self.l1.set(full_key, data, l1_ttl)

        # Write to L2
        if self.l2 and self.l2.is_enabled and self.ml_config.write_through:
            l2_ttl = ttl or self.ml_config.l2_ttl
            self.l2.set_many(serialized, l2_ttl)

        return results

    def invalidate_all(self, pattern: str = "*") -> int:
        """Invalidate all keys matching pattern."""
        keys = self.keys(pattern)
        count = 0

        for key in keys:
            if self.delete(key):
                count += 1

        return count

    def get_level_stats(self) -> Dict[str, Any]:
        """Get statistics for each cache level."""
        stats = {}

        if self.l1:
            stats["l1"] = {
                **self.l1.stats.to_dict(),
                "size": self.l1.backend.size if hasattr(self.l1.backend, 'size') else 0,
                "max_size": self.ml_config.l1_max_size,
            }

        if self.l2:
            stats["l2"] = self.l2.stats.to_dict()

        stats["combined"] = self.stats.to_dict()

        return stats

    def warm_up(self, keys: List[str], source_fn: Callable[[str], Any]) -> int:
        """Warm up the cache with data from a source function."""
        count = 0

        for key in keys:
            try:
                value = source_fn(key)
                if value is not None and self.set(key, value):
                    count += 1
            except Exception as e:
                logger.error(f"Error warming up key {key}: {e}")

        return count

    def promote_to_l1(self, key: str) -> bool:
        """Promote a key from L2 to L1."""
        if not self.l1 or not self.l2:
            return False

        full_key = self._make_key(key)
        value = self.l2.get(full_key)

        if value is not None:
            return self.l1.set(full_key, value)

        return False

    def demote_from_l1(self, key: str) -> bool:
        """Remove a key from L1 (it stays in L2)."""
        if not self.l1:
            return False

        full_key = self._make_key(key)
        return self.l1.delete(full_key)


class AdaptiveMultiLevelCache(MultiLevelCache):
    """
    Multi-level cache with adaptive behavior based on access patterns.

    Automatically adjusts L1 promotion/demotion based on access frequency.
    """

    def __init__(
        self,
        l2_backend: CacheBackend,
        config: Optional[MultiLevelConfig] = None,
        cache_config: Optional[CacheConfig] = None,
        promotion_threshold: int = 3,  # Accesses before promoting to L1
        demotion_interval: int = 300,  # Seconds between demotion checks
    ):
        super().__init__(l2_backend, config, cache_config)
        self.promotion_threshold = promotion_threshold
        self.demotion_interval = demotion_interval
        self._access_counts: Dict[str, int] = {}
        self._last_access: Dict[str, float] = {}
        self._access_lock = threading.Lock()
        self._demotion_thread: Optional[threading.Thread] = None
        self._running = True

        self._start_demotion_thread()

    def _start_demotion_thread(self):
        """Start background thread for demoting cold entries."""
        def demotion_loop():
            while self._running:
                time.sleep(self.demotion_interval)
                self._demote_cold_entries()

        self._demotion_thread = threading.Thread(target=demotion_loop, daemon=True)
        self._demotion_thread.start()

    def _demote_cold_entries(self):
        """Demote entries that haven't been accessed recently."""
        cutoff = time.time() - self.demotion_interval
        keys_to_demote = []

        with self._access_lock:
            for key, last_access in list(self._last_access.items()):
                if last_access < cutoff:
                    keys_to_demote.append(key)
                    del self._access_counts[key]
                    del self._last_access[key]

        for key in keys_to_demote:
            self.demote_from_l1(key)

    def _record_access(self, key: str):
        """Record access for adaptive behavior."""
        with self._access_lock:
            self._access_counts[key] = self._access_counts.get(key, 0) + 1
            self._last_access[key] = time.time()

    def get(self, key: str, default: Any = None) -> Any:
        """Get with adaptive promotion."""
        self._record_access(key)

        # Check if we should promote from L2 to L1
        with self._access_lock:
            access_count = self._access_counts.get(key, 0)

        # If frequently accessed and not in L1, promote
        if access_count >= self.promotion_threshold:
            full_key = self._make_key(key)
            if self.l1 and not self.l1.backend.exists(full_key):
                self.promote_to_l1(key)

        return super().get(key, default)

    def close(self):
        """Close the cache and stop background threads."""
        self._running = False
        if self._demotion_thread:
            self._demotion_thread.join(timeout=1)
