"""
Core cache implementation and configuration.
"""

import hashlib
import json
import logging
import pickle
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheError(Exception):
    """Base exception for cache errors."""
    pass


class CacheKeyError(CacheError):
    """Error for invalid cache keys."""
    pass


class CacheSerializationError(CacheError):
    """Error during serialization/deserialization."""
    pass


class CacheConnectionError(CacheError):
    """Error connecting to cache backend."""
    pass


class SerializationType(Enum):
    """Serialization formats."""
    JSON = "json"
    PICKLE = "pickle"
    MSGPACK = "msgpack"


@dataclass
class CacheConfig:
    """Configuration for the cache."""
    max_size: int = 10000
    default_ttl_seconds: int = 3600
    serialization: SerializationType = SerializationType.JSON
    compression: bool = False
    compression_threshold: int = 1024  # Compress values larger than this
    namespace: str = "default"
    key_prefix: str = ""
    enable_stats: bool = True
    enable_logging: bool = True
    async_writes: bool = False
    retry_attempts: int = 3
    retry_delay_ms: int = 100
    connection_timeout_ms: int = 5000
    socket_timeout_ms: int = 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_size": self.max_size,
            "default_ttl_seconds": self.default_ttl_seconds,
            "serialization": self.serialization.value,
            "compression": self.compression,
            "namespace": self.namespace,
            "key_prefix": self.key_prefix,
        }


@dataclass
class CacheEntry(Generic[T]):
    """Represents a cache entry."""
    key: str
    value: T
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def ttl_remaining(self) -> Optional[float]:
        if self.expires_at is None:
            return None
        remaining = (self.expires_at - datetime.utcnow()).total_seconds()
        return max(0, remaining)

    @property
    def age_seconds(self) -> float:
        return (datetime.utcnow() - self.created_at).total_seconds()

    def touch(self):
        """Update last accessed time and increment access count."""
        self.last_accessed = datetime.utcnow()
        self.access_count += 1


@dataclass
class CacheStats:
    """Cache statistics."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    expirations: int = 0
    errors: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    total_entries: int = 0
    total_size_bytes: int = 0
    avg_get_time_ms: float = 0.0
    avg_set_time_ms: float = 0.0
    _get_times: List[float] = field(default_factory=list)
    _set_times: List[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def record_hit(self, time_ms: float = 0, bytes_count: int = 0):
        with self._lock:
            self.hits += 1
            self.bytes_read += bytes_count
            if time_ms:
                self._get_times.append(time_ms)
                if len(self._get_times) > 1000:
                    self._get_times = self._get_times[-1000:]
                self.avg_get_time_ms = sum(self._get_times) / len(self._get_times)

    def record_miss(self, time_ms: float = 0):
        with self._lock:
            self.misses += 1
            if time_ms:
                self._get_times.append(time_ms)
                if len(self._get_times) > 1000:
                    self._get_times = self._get_times[-1000:]
                self.avg_get_time_ms = sum(self._get_times) / len(self._get_times)

    def record_set(self, time_ms: float = 0, bytes_count: int = 0):
        with self._lock:
            self.sets += 1
            self.bytes_written += bytes_count
            if time_ms:
                self._set_times.append(time_ms)
                if len(self._set_times) > 1000:
                    self._set_times = self._set_times[-1000:]
                self.avg_set_time_ms = sum(self._set_times) / len(self._set_times)

    def record_delete(self):
        with self._lock:
            self.deletes += 1

    def record_eviction(self):
        with self._lock:
            self.evictions += 1

    def record_expiration(self):
        with self._lock:
            self.expirations += 1

    def record_error(self):
        with self._lock:
            self.errors += 1

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": self.hit_rate,
                "sets": self.sets,
                "deletes": self.deletes,
                "evictions": self.evictions,
                "expirations": self.expirations,
                "errors": self.errors,
                "bytes_read": self.bytes_read,
                "bytes_written": self.bytes_written,
                "total_entries": self.total_entries,
                "total_size_bytes": self.total_size_bytes,
                "avg_get_time_ms": self.avg_get_time_ms,
                "avg_set_time_ms": self.avg_set_time_ms,
            }


class Serializer:
    """Handles serialization and deserialization of cache values."""

    def __init__(
        self,
        serialization_type: SerializationType = SerializationType.JSON,
        compression: bool = False,
        compression_threshold: int = 1024
    ):
        self.serialization_type = serialization_type
        self.compression = compression
        self.compression_threshold = compression_threshold

    def serialize(self, value: Any) -> bytes:
        """Serialize a value to bytes."""
        try:
            if self.serialization_type == SerializationType.JSON:
                data = json.dumps(value, default=str).encode("utf-8")
            elif self.serialization_type == SerializationType.PICKLE:
                data = pickle.dumps(value)
            elif self.serialization_type == SerializationType.MSGPACK:
                try:
                    import msgpack
                    data = msgpack.packb(value, use_bin_type=True)
                except ImportError:
                    raise CacheSerializationError("msgpack not installed")
            else:
                raise CacheSerializationError(f"Unknown serialization type: {self.serialization_type}")

            if self.compression and len(data) >= self.compression_threshold:
                import zlib
                compressed = zlib.compress(data)
                # Prefix with marker
                return b"\x00\x01" + compressed

            return b"\x00\x00" + data

        except Exception as e:
            raise CacheSerializationError(f"Serialization error: {e}")

    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to a value."""
        try:
            if len(data) < 2:
                raise CacheSerializationError("Invalid data format")

            # Check compression marker
            marker = data[:2]
            payload = data[2:]

            if marker == b"\x00\x01":
                # Compressed
                import zlib
                payload = zlib.decompress(payload)
            elif marker != b"\x00\x00":
                # Legacy format without marker
                payload = data

            if self.serialization_type == SerializationType.JSON:
                return json.loads(payload.decode("utf-8"))
            elif self.serialization_type == SerializationType.PICKLE:
                return pickle.loads(payload)
            elif self.serialization_type == SerializationType.MSGPACK:
                try:
                    import msgpack
                    return msgpack.unpackb(payload, raw=False)
                except ImportError:
                    raise CacheSerializationError("msgpack not installed")
            else:
                raise CacheSerializationError(f"Unknown serialization type: {self.serialization_type}")

        except Exception as e:
            raise CacheSerializationError(f"Deserialization error: {e}")


class Cache(ABC):
    """Abstract base class for cache implementations."""

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.stats = CacheStats()
        self.serializer = Serializer(
            self.config.serialization,
            self.config.compression,
            self.config.compression_threshold
        )

    def _make_key(self, key: str) -> str:
        """Create the full cache key with namespace and prefix."""
        if not key:
            raise CacheKeyError("Cache key cannot be empty")

        parts = []
        if self.config.namespace:
            parts.append(self.config.namespace)
        if self.config.key_prefix:
            parts.append(self.config.key_prefix)
        parts.append(key)

        return ":".join(parts)

    def _hash_key(self, key: str) -> str:
        """Hash a key for consistent length."""
        return hashlib.sha256(key.encode()).hexdigest()

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from cache."""
        pass

    @abstractmethod
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        **kwargs
    ) -> bool:
        """Set a value in cache."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a value from cache."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        pass

    @abstractmethod
    def clear(self) -> int:
        """Clear all entries. Returns count of cleared entries."""
        pass

    @abstractmethod
    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern."""
        pass

    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values at once."""
        return {key: self.get(key) for key in keys}

    def set_many(
        self,
        mapping: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> Dict[str, bool]:
        """Set multiple values at once."""
        return {key: self.set(key, value, ttl) for key, value in mapping.items()}

    def delete_many(self, keys: List[str]) -> int:
        """Delete multiple keys. Returns count of deleted keys."""
        return sum(1 for key in keys if self.delete(key))

    def get_or_set(
        self,
        key: str,
        default_fn: Callable[[], Any],
        ttl: Optional[int] = None
    ) -> Any:
        """Get a value or set it using the default function if not found."""
        value = self.get(key)
        if value is None:
            value = default_fn()
            self.set(key, value, ttl)
        return value

    def increment(self, key: str, delta: int = 1) -> int:
        """Increment a numeric value. Returns new value."""
        value = self.get(key, 0)
        if not isinstance(value, (int, float)):
            raise CacheError(f"Cannot increment non-numeric value: {type(value)}")
        new_value = value + delta
        self.set(key, new_value)
        return new_value

    def decrement(self, key: str, delta: int = 1) -> int:
        """Decrement a numeric value. Returns new value."""
        return self.increment(key, -delta)

    def touch(self, key: str, ttl: Optional[int] = None) -> bool:
        """Update the TTL of a key."""
        value = self.get(key)
        if value is not None:
            return self.set(key, value, ttl)
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.stats.to_dict()

    def reset_stats(self):
        """Reset cache statistics."""
        self.stats = CacheStats()


class CacheRegion:
    """A named region within a cache with its own configuration."""

    def __init__(
        self,
        name: str,
        cache: Cache,
        ttl: Optional[int] = None,
        key_prefix: Optional[str] = None
    ):
        self.name = name
        self.cache = cache
        self.ttl = ttl
        self.key_prefix = key_prefix or name

    def _make_key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def get(self, key: str, default: Any = None) -> Any:
        return self.cache.get(self._make_key(key), default)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        return self.cache.set(self._make_key(key), value, ttl or self.ttl)

    def delete(self, key: str) -> bool:
        return self.cache.delete(self._make_key(key))

    def clear(self) -> int:
        """Clear all entries in this region."""
        keys = self.cache.keys(f"{self.key_prefix}:*")
        return self.cache.delete_many(keys)


class CacheManager:
    """Manages multiple cache instances and regions."""

    def __init__(self):
        self._caches: Dict[str, Cache] = {}
        self._regions: Dict[str, CacheRegion] = {}
        self._default_cache: Optional[str] = None

    def register(self, name: str, cache: Cache, default: bool = False):
        """Register a cache instance."""
        self._caches[name] = cache
        if default or self._default_cache is None:
            self._default_cache = name

    def unregister(self, name: str):
        """Unregister a cache instance."""
        self._caches.pop(name, None)
        if self._default_cache == name:
            self._default_cache = next(iter(self._caches.keys()), None)

    def get_cache(self, name: Optional[str] = None) -> Cache:
        """Get a cache instance by name."""
        name = name or self._default_cache
        if name not in self._caches:
            raise CacheError(f"Cache '{name}' not found")
        return self._caches[name]

    def create_region(
        self,
        name: str,
        cache_name: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> CacheRegion:
        """Create a cache region."""
        cache = self.get_cache(cache_name)
        region = CacheRegion(name, cache, ttl)
        self._regions[name] = region
        return region

    def get_region(self, name: str) -> CacheRegion:
        """Get a cache region by name."""
        if name not in self._regions:
            raise CacheError(f"Region '{name}' not found")
        return self._regions[name]

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics from all caches."""
        return {name: cache.get_stats() for name, cache in self._caches.items()}


# Global cache manager instance
cache_manager = CacheManager()
