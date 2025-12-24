"""
Cache Backends for NebulaCompute.

Provides multiple storage backends for the cache system:
- MemoryBackend: In-process memory storage
- RedisBackend: Redis-based storage
- TieredBackend: Multi-tier caching
"""

import asyncio
import pickle
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in the cache."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a key from the cache."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all entries."""
        pass

    async def mget(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple keys."""
        result = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value
        return result

    async def mset(self, items: List[Tuple[str, Any, Optional[int]]]) -> bool:
        """Set multiple keys."""
        for key, value, ttl in items:
            await self.set(key, value, ttl)
        return True

    async def connect(self) -> None:
        """Connect to the backend."""
        pass

    async def close(self) -> None:
        """Close the backend connection."""
        pass


@dataclass
class MemoryEntry:
    """Entry in memory cache."""
    value: Any
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    size_bytes: int = 0


class MemoryBackend(CacheBackend):
    """
    In-process memory cache backend.

    Features:
    - LRU eviction
    - TTL support
    - Size limits
    - Thread-safe with asyncio
    """

    def __init__(
        self,
        max_size: int = 10000,
        max_memory_bytes: int = 100 * 1024 * 1024,  # 100MB
        default_ttl: int = 300,
    ):
        self.max_size = max_size
        self.max_memory_bytes = max_memory_bytes
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, MemoryEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._current_memory = 0

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from memory cache."""
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            # Check expiration
            if entry.expires_at and datetime.now() > entry.expires_at:
                self._remove_entry(key)
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            entry.access_count += 1

            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a value in memory cache."""
        async with self._lock:
            # Calculate size
            try:
                size_bytes = len(pickle.dumps(value))
            except Exception:
                size_bytes = 1024  # Estimate

            # Evict if necessary
            while (
                len(self._cache) >= self.max_size
                or self._current_memory + size_bytes > self.max_memory_bytes
            ):
                if not self._cache:
                    break
                self._evict_oldest()

            # Calculate expiration
            ttl = ttl or self.default_ttl
            expires_at = datetime.now() + timedelta(seconds=ttl) if ttl else None

            # Remove old entry if exists
            if key in self._cache:
                self._remove_entry(key)

            # Add new entry
            entry = MemoryEntry(
                value=value,
                expires_at=expires_at,
                size_bytes=size_bytes,
            )

            self._cache[key] = entry
            self._current_memory += size_bytes

            return True

    async def delete(self, key: str) -> bool:
        """Delete a key from memory cache."""
        async with self._lock:
            if key in self._cache:
                self._remove_entry(key)
                return True
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.expires_at and datetime.now() > entry.expires_at:
                self._remove_entry(key)
                return False
            return True

    async def clear(self) -> None:
        """Clear all entries."""
        async with self._lock:
            self._cache.clear()
            self._current_memory = 0

    def _remove_entry(self, key: str) -> None:
        """Remove an entry (must hold lock)."""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._current_memory -= entry.size_bytes

    def _evict_oldest(self) -> None:
        """Evict oldest entry (must hold lock)."""
        if self._cache:
            oldest_key = next(iter(self._cache))
            self._remove_entry(oldest_key)

    async def cleanup_expired(self) -> int:
        """Remove expired entries."""
        async with self._lock:
            now = datetime.now()
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.expires_at and now > entry.expires_at
            ]

            for key in expired_keys:
                self._remove_entry(key)

            return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """Get memory cache statistics."""
        return {
            "entries": len(self._cache),
            "memory_bytes": self._current_memory,
            "memory_mb": self._current_memory / (1024 * 1024),
            "max_size": self.max_size,
            "max_memory_mb": self.max_memory_bytes / (1024 * 1024),
        }


class RedisBackend(CacheBackend):
    """
    Redis cache backend.

    Features:
    - Persistent storage
    - Cluster support
    - Pipeline operations
    - Pub/sub for invalidation
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        prefix: str = "nebula:",
        default_ttl: int = 3600,
        pool_size: int = 10,
    ):
        self.url = url
        self.prefix = prefix
        self.default_ttl = default_ttl
        self.pool_size = pool_size
        self._redis = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(
                self.url,
                max_connections=self.pool_size,
                decode_responses=False,
            )

            # Test connection
            await self._redis.ping()
            self._connected = True
            logger.info("Connected to Redis at %s", self.url)

        except ImportError:
            logger.warning("redis package not installed, Redis backend unavailable")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            raise

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._connected = False

    def _make_key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from Redis."""
        if not self._connected:
            return None

        try:
            data = await self._redis.get(self._make_key(key))
            if data is None:
                return None
            return pickle.loads(data)
        except Exception as e:
            logger.error("Redis get error: %s", e)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a value in Redis."""
        if not self._connected:
            return False

        try:
            ttl = ttl or self.default_ttl
            data = pickle.dumps(value)
            await self._redis.setex(self._make_key(key), ttl, data)
            return True
        except Exception as e:
            logger.error("Redis set error: %s", e)
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        if not self._connected:
            return False

        try:
            result = await self._redis.delete(self._make_key(key))
            return result > 0
        except Exception as e:
            logger.error("Redis delete error: %s", e)
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        if not self._connected:
            return False

        try:
            return await self._redis.exists(self._make_key(key)) > 0
        except Exception as e:
            logger.error("Redis exists error: %s", e)
            return False

    async def clear(self) -> None:
        """Clear all keys with our prefix."""
        if not self._connected:
            return

        try:
            pattern = f"{self.prefix}*"
            cursor = 0

            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break

        except Exception as e:
            logger.error("Redis clear error: %s", e)

    async def mget(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple keys from Redis."""
        if not self._connected or not keys:
            return {}

        try:
            prefixed_keys = [self._make_key(k) for k in keys]
            values = await self._redis.mget(prefixed_keys)

            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = pickle.loads(value)

            return result
        except Exception as e:
            logger.error("Redis mget error: %s", e)
            return {}

    async def mset(self, items: List[Tuple[str, Any, Optional[int]]]) -> bool:
        """Set multiple keys in Redis using pipeline."""
        if not self._connected or not items:
            return True

        try:
            async with self._redis.pipeline() as pipe:
                for key, value, ttl in items:
                    ttl = ttl or self.default_ttl
                    data = pickle.dumps(value)
                    pipe.setex(self._make_key(key), ttl, data)

                await pipe.execute()

            return True
        except Exception as e:
            logger.error("Redis mset error: %s", e)
            return False

    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment a counter."""
        if not self._connected:
            return 0

        try:
            return await self._redis.incrby(self._make_key(key), amount)
        except Exception as e:
            logger.error("Redis incr error: %s", e)
            return 0

    async def get_info(self) -> Dict[str, Any]:
        """Get Redis server info."""
        if not self._connected:
            return {}

        try:
            info = await self._redis.info()
            return {
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "total_connections_received": info.get("total_connections_received"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
            }
        except Exception as e:
            logger.error("Redis info error: %s", e)
            return {}


class TieredBackend(CacheBackend):
    """
    Multi-tier cache backend.

    Combines multiple backends in a hierarchy:
    L1 (Memory) -> L2 (Redis) -> L3 (Distributed)

    Features:
    - Automatic promotion on reads
    - Write-through or write-back
    - Configurable tiers
    """

    def __init__(
        self,
        tiers: List[CacheBackend],
        write_through: bool = True,
    ):
        self.tiers = tiers
        self.write_through = write_through

    async def connect(self) -> None:
        """Connect all tiers."""
        for tier in self.tiers:
            await tier.connect()

    async def close(self) -> None:
        """Close all tiers."""
        for tier in self.tiers:
            await tier.close()

    async def get(self, key: str) -> Optional[Any]:
        """Get from tiers with promotion."""
        for i, tier in enumerate(self.tiers):
            value = await tier.get(key)
            if value is not None:
                # Promote to higher tiers
                for higher_tier in self.tiers[:i]:
                    await higher_tier.set(key, value)
                return value
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set in all tiers (write-through) or top tier only."""
        if self.write_through:
            # Write to all tiers
            results = await asyncio.gather(*[
                tier.set(key, value, ttl) for tier in self.tiers
            ])
            return all(results)
        else:
            # Write to top tier only
            return await self.tiers[0].set(key, value, ttl)

    async def delete(self, key: str) -> bool:
        """Delete from all tiers."""
        results = await asyncio.gather(*[
            tier.delete(key) for tier in self.tiers
        ])
        return any(results)

    async def exists(self, key: str) -> bool:
        """Check if exists in any tier."""
        for tier in self.tiers:
            if await tier.exists(key):
                return True
        return False

    async def clear(self) -> None:
        """Clear all tiers."""
        await asyncio.gather(*[tier.clear() for tier in self.tiers])
