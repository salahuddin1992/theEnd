"""
Cache Manager - Central cache orchestration for NebulaCompute.

Provides unified interface for caching with automatic backend selection,
statistics tracking, and cache warming capabilities.
"""

import asyncio
import hashlib
import pickle
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheLevel(Enum):
    """Cache hierarchy levels."""
    L1_MEMORY = "l1_memory"      # In-process memory (fastest)
    L2_LOCAL = "l2_local"        # Local disk/Redis
    L3_DISTRIBUTED = "l3_distributed"  # Distributed cache cluster


class SerializationFormat(Enum):
    """Serialization formats for cache values."""
    PICKLE = "pickle"
    JSON = "json"
    MSGPACK = "msgpack"


@dataclass
class CacheConfig:
    """Configuration for the cache system."""
    # Memory cache settings
    memory_max_size: int = 10000
    memory_ttl_seconds: int = 300

    # Redis settings
    redis_url: Optional[str] = None
    redis_prefix: str = "nebula:"
    redis_ttl_seconds: int = 3600

    # Distributed settings
    distributed_nodes: List[str] = field(default_factory=list)
    replication_factor: int = 2

    # General settings
    serialization: SerializationFormat = SerializationFormat.PICKLE
    compression_enabled: bool = True
    compression_threshold: int = 1024  # Compress if > 1KB

    # Performance settings
    async_writes: bool = True
    write_behind_delay: float = 0.1
    batch_size: int = 100

    # Monitoring
    stats_enabled: bool = True
    stats_interval: int = 60


@dataclass
class CacheStats:
    """Cache performance statistics."""
    hits: int = 0
    misses: int = 0
    writes: int = 0
    deletes: int = 0
    evictions: int = 0
    errors: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    avg_read_latency_ms: float = 0.0
    avg_write_latency_ms: float = 0.0
    start_time: datetime = field(default_factory=datetime.now)

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def uptime_seconds(self) -> float:
        """Get cache uptime in seconds."""
        return (datetime.now() - self.start_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "deletes": self.deletes,
            "evictions": self.evictions,
            "errors": self.errors,
            "hit_rate": f"{self.hit_rate:.2%}",
            "bytes_read": self.bytes_read,
            "bytes_written": self.bytes_written,
            "avg_read_latency_ms": f"{self.avg_read_latency_ms:.2f}",
            "avg_write_latency_ms": f"{self.avg_write_latency_ms:.2f}",
            "uptime_seconds": self.uptime_seconds,
        }


@dataclass
class CacheEntry(Generic[T]):
    """A cached entry with metadata."""
    key: str
    value: T
    created_at: datetime
    expires_at: Optional[datetime]
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    size_bytes: int = 0
    tags: List[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    @property
    def ttl_remaining(self) -> Optional[float]:
        """Get remaining TTL in seconds."""
        if self.expires_at is None:
            return None
        remaining = (self.expires_at - datetime.now()).total_seconds()
        return max(0, remaining)


class CacheManager:
    """
    Central cache manager for NebulaCompute.

    Features:
    - Multi-level caching (L1 memory, L2 local, L3 distributed)
    - Multiple eviction strategies (LRU, LFU, TTL, Adaptive)
    - Automatic cache warming
    - Statistics and monitoring
    - Compression for large values
    - Async write-behind for performance
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self._cache: Dict[str, CacheEntry] = {}
        self._stats = CacheStats()
        self._locks: Dict[str, asyncio.Lock] = {}
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._read_latencies: List[float] = []
        self._write_latencies: List[float] = []

        # Backend references (lazy initialized)
        self._redis_backend = None
        self._distributed_backend = None

        logger.info("CacheManager initialized with config: %s", self.config)

    async def start(self) -> None:
        """Start the cache manager background tasks."""
        if self._running:
            return

        self._running = True

        # Start background tasks
        if self.config.async_writes:
            asyncio.create_task(self._write_behind_worker())

        if self.config.stats_enabled:
            asyncio.create_task(self._stats_reporter())

        # Initialize backends
        await self._init_backends()

        logger.info("CacheManager started")

    async def stop(self) -> None:
        """Stop the cache manager."""
        self._running = False

        # Flush pending writes
        await self._flush_write_queue()

        # Close backends
        if self._redis_backend:
            await self._redis_backend.close()

        logger.info("CacheManager stopped")

    async def _init_backends(self) -> None:
        """Initialize cache backends."""
        if self.config.redis_url:
            from .backends import RedisBackend
            self._redis_backend = RedisBackend(
                url=self.config.redis_url,
                prefix=self.config.redis_prefix,
            )
            await self._redis_backend.connect()

        if self.config.distributed_nodes:
            from .distributed import DistributedCache
            self._distributed_backend = DistributedCache(
                nodes=self.config.distributed_nodes,
                replication_factor=self.config.replication_factor,
            )
            await self._distributed_backend.connect()

    def _get_lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for a key."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _generate_key(self, *args, **kwargs) -> str:
        """Generate a cache key from arguments."""
        key_data = pickle.dumps((args, sorted(kwargs.items())))
        return hashlib.sha256(key_data).hexdigest()[:32]

    def _serialize(self, value: Any) -> bytes:
        """Serialize a value for storage."""
        data = pickle.dumps(value)

        if self.config.compression_enabled and len(data) > self.config.compression_threshold:
            import zlib
            data = zlib.compress(data)

        return data

    def _deserialize(self, data: bytes) -> Any:
        """Deserialize a value from storage."""
        try:
            # Try decompression first
            import zlib
            data = zlib.decompress(data)
        except zlib.error:
            pass  # Not compressed

        # nosec B301 - Data comes from internal cache storage, trusted source
        return pickle.loads(data)

    async def get(
        self,
        key: str,
        default: Optional[T] = None,
        level: Optional[CacheLevel] = None,
    ) -> Optional[T]:
        """
        Get a value from the cache.

        Args:
            key: Cache key
            default: Default value if not found
            level: Specific cache level to query

        Returns:
            Cached value or default
        """
        start_time = time.perf_counter()

        try:
            # Check L1 memory cache first
            if level is None or level == CacheLevel.L1_MEMORY:
                entry = self._cache.get(key)
                if entry and not entry.is_expired:
                    entry.access_count += 1
                    entry.last_accessed = datetime.now()
                    self._stats.hits += 1
                    self._stats.bytes_read += entry.size_bytes
                    self._record_read_latency(start_time)
                    return entry.value

            # Check L2 Redis cache
            if self._redis_backend and (level is None or level == CacheLevel.L2_LOCAL):
                value = await self._redis_backend.get(key)
                if value is not None:
                    # Promote to L1
                    await self._set_l1(key, value)
                    self._stats.hits += 1
                    self._record_read_latency(start_time)
                    return value

            # Check L3 distributed cache
            if self._distributed_backend and (level is None or level == CacheLevel.L3_DISTRIBUTED):
                value = await self._distributed_backend.get(key)
                if value is not None:
                    # Promote to L1 and L2
                    await self._set_l1(key, value)
                    if self._redis_backend:
                        await self._redis_backend.set(key, value)
                    self._stats.hits += 1
                    self._record_read_latency(start_time)
                    return value

            self._stats.misses += 1
            self._record_read_latency(start_time)
            return default

        except Exception as e:
            self._stats.errors += 1
            logger.error("Cache get error for key %s: %s", key, e)
            return default

    async def set(
        self,
        key: str,
        value: T,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
        level: Optional[CacheLevel] = None,
    ) -> bool:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds
            tags: Optional tags for bulk invalidation
            level: Specific cache level(s) to set

        Returns:
            True if successful
        """
        start_time = time.perf_counter()

        try:
            ttl = ttl or self.config.memory_ttl_seconds
            expires_at = datetime.now() + timedelta(seconds=ttl) if ttl else None

            # Set in L1 memory
            if level is None or level == CacheLevel.L1_MEMORY:
                await self._set_l1(key, value, expires_at, tags)

            # Set in L2 Redis (async if enabled)
            if self._redis_backend and (level is None or level == CacheLevel.L2_LOCAL):
                if self.config.async_writes:
                    await self._write_queue.put(("redis", key, value, ttl))
                else:
                    await self._redis_backend.set(key, value, ttl)

            # Set in L3 distributed
            if self._distributed_backend and (level is None or level == CacheLevel.L3_DISTRIBUTED):
                if self.config.async_writes:
                    await self._write_queue.put(("distributed", key, value, ttl))
                else:
                    await self._distributed_backend.set(key, value, ttl)

            self._stats.writes += 1
            self._record_write_latency(start_time)
            return True

        except Exception as e:
            self._stats.errors += 1
            logger.error("Cache set error for key %s: %s", key, e)
            return False

    async def _set_l1(
        self,
        key: str,
        value: T,
        expires_at: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Set value in L1 memory cache."""
        # Evict if at capacity
        if len(self._cache) >= self.config.memory_max_size:
            await self._evict_lru()

        serialized = self._serialize(value)

        entry = CacheEntry(
            key=key,
            value=value,
            created_at=datetime.now(),
            expires_at=expires_at,
            size_bytes=len(serialized),
            tags=tags or [],
        )

        self._cache[key] = entry
        self._stats.bytes_written += entry.size_bytes

    async def delete(self, key: str) -> bool:
        """Delete a key from all cache levels."""
        try:
            # Delete from L1
            if key in self._cache:
                del self._cache[key]

            # Delete from L2
            if self._redis_backend:
                await self._redis_backend.delete(key)

            # Delete from L3
            if self._distributed_backend:
                await self._distributed_backend.delete(key)

            self._stats.deletes += 1
            return True

        except Exception as e:
            self._stats.errors += 1
            logger.error("Cache delete error for key %s: %s", key, e)
            return False

    async def delete_by_tag(self, tag: str) -> int:
        """Delete all entries with a specific tag."""
        deleted = 0
        keys_to_delete = [
            key for key, entry in self._cache.items()
            if tag in entry.tags
        ]

        for key in keys_to_delete:
            if await self.delete(key):
                deleted += 1

        return deleted

    async def clear(self) -> None:
        """Clear all cache levels."""
        self._cache.clear()

        if self._redis_backend:
            await self._redis_backend.clear()

        if self._distributed_backend:
            await self._distributed_backend.clear()

        logger.info("Cache cleared")

    async def _evict_lru(self) -> None:
        """Evict least recently used entries."""
        if not self._cache:
            return

        # Sort by last accessed time
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1].last_accessed or x[1].created_at,
        )

        # Evict 10% of entries
        evict_count = max(1, len(self._cache) // 10)

        for key, _ in sorted_entries[:evict_count]:
            del self._cache[key]
            self._stats.evictions += 1

    async def _write_behind_worker(self) -> None:
        """Background worker for async writes."""
        batch: List[tuple] = []

        while self._running:
            try:
                # Collect batch
                try:
                    item = await asyncio.wait_for(
                        self._write_queue.get(),
                        timeout=self.config.write_behind_delay,
                    )
                    batch.append(item)
                except asyncio.TimeoutError:
                    pass

                # Process batch if ready
                if len(batch) >= self.config.batch_size or (batch and self._write_queue.empty()):
                    await self._process_write_batch(batch)
                    batch.clear()

            except Exception as e:
                logger.error("Write-behind worker error: %s", e)
                await asyncio.sleep(1)

    async def _process_write_batch(self, batch: List[tuple]) -> None:
        """Process a batch of writes."""
        redis_writes = [(k, v, t) for b, k, v, t in batch if b == "redis"]
        distributed_writes = [(k, v, t) for b, k, v, t in batch if b == "distributed"]

        if redis_writes and self._redis_backend:
            await self._redis_backend.mset(redis_writes)

        if distributed_writes and self._distributed_backend:
            await self._distributed_backend.mset(distributed_writes)

    async def _flush_write_queue(self) -> None:
        """Flush all pending writes."""
        batch = []
        while not self._write_queue.empty():
            batch.append(await self._write_queue.get())

        if batch:
            await self._process_write_batch(batch)

    async def _stats_reporter(self) -> None:
        """Periodically report cache statistics."""
        while self._running:
            await asyncio.sleep(self.config.stats_interval)
            logger.info("Cache stats: %s", self._stats.to_dict())

    def _record_read_latency(self, start_time: float) -> None:
        """Record read latency."""
        latency_ms = (time.perf_counter() - start_time) * 1000
        self._read_latencies.append(latency_ms)

        # Keep last 1000 samples
        if len(self._read_latencies) > 1000:
            self._read_latencies = self._read_latencies[-1000:]

        self._stats.avg_read_latency_ms = sum(self._read_latencies) / len(self._read_latencies)

    def _record_write_latency(self, start_time: float) -> None:
        """Record write latency."""
        latency_ms = (time.perf_counter() - start_time) * 1000
        self._write_latencies.append(latency_ms)

        # Keep last 1000 samples
        if len(self._write_latencies) > 1000:
            self._write_latencies = self._write_latencies[-1000:]

        self._stats.avg_write_latency_ms = sum(self._write_latencies) / len(self._write_latencies)

    def get_stats(self) -> Dict[str, Any]:
        """Get current cache statistics."""
        return self._stats.to_dict()

    def cached(
        self,
        ttl: Optional[int] = None,
        key_prefix: str = "",
        tags: Optional[List[str]] = None,
    ) -> Callable:
        """
        Decorator for caching function results.

        Usage:
            @cache_manager.cached(ttl=300, key_prefix="user")
            async def get_user(user_id: int):
                return await db.fetch_user(user_id)
        """
        def decorator(func: Callable) -> Callable:
            async def wrapper(*args, **kwargs):
                # Generate cache key
                key = f"{key_prefix}:{func.__name__}:{self._generate_key(*args, **kwargs)}"

                # Try cache first
                result = await self.get(key)
                if result is not None:
                    return result

                # Call function and cache result
                result = await func(*args, **kwargs)
                await self.set(key, result, ttl=ttl, tags=tags)

                return result

            return wrapper
        return decorator

    async def warm(
        self,
        keys: List[str],
        loader: Callable[[str], Any],
        ttl: Optional[int] = None,
    ) -> int:
        """
        Warm the cache with data.

        Args:
            keys: Keys to warm
            loader: Function to load data for each key
            ttl: TTL for warmed entries

        Returns:
            Number of entries warmed
        """
        warmed = 0

        for key in keys:
            try:
                value = await loader(key)
                if value is not None:
                    await self.set(key, value, ttl=ttl)
                    warmed += 1
            except Exception as e:
                logger.warning("Failed to warm key %s: %s", key, e)

        logger.info("Cache warmed with %d entries", warmed)
        return warmed
