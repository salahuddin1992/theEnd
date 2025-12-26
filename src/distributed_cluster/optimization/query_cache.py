"""
Query Cache - Specialized caching for scheduler and query operations.

This module provides optimized caching specifically designed for
scheduler queries, job lookups, worker status, and other frequent
distributed cluster operations.
"""

import asyncio
import time
import threading
import hashlib
import logging
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set, Tuple, TypeVar, Generic
from enum import Enum
from collections import deque, defaultdict
from functools import wraps
import json

logger = logging.getLogger(__name__)

T = TypeVar('T')


class QueryType(Enum):
    """Types of queries that can be cached."""
    WORKER_STATUS = "worker_status"
    JOB_STATUS = "job_status"
    JOB_LIST = "job_list"
    WORKER_LIST = "worker_list"
    RESOURCE_AVAILABILITY = "resource_availability"
    SCHEDULER_STATE = "scheduler_state"
    CLUSTER_METRICS = "cluster_metrics"
    LEASE_INFO = "lease_info"
    QUEUE_STATUS = "queue_status"


class InvalidationTrigger(Enum):
    """Triggers for cache invalidation."""
    TIME_BASED = "time_based"
    EVENT_BASED = "event_based"
    MANUAL = "manual"
    VERSION_BASED = "version_based"


@dataclass
class CachedQuery:
    """Represents a cached query result."""
    key: str
    query_type: QueryType
    result: Any
    created_at: float
    expires_at: float
    version: int
    hit_count: int = 0
    last_hit: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if the cached result is expired."""
        return time.time() > self.expires_at

    @property
    def age_seconds(self) -> float:
        """Get the age of the cached result in seconds."""
        return time.time() - self.created_at


@dataclass
class QueryCacheConfig:
    """Configuration for query cache."""
    max_entries: int = 10000
    default_ttl_seconds: int = 60
    worker_status_ttl: int = 5
    job_status_ttl: int = 10
    job_list_ttl: int = 30
    worker_list_ttl: int = 15
    resource_ttl: int = 5
    scheduler_state_ttl: int = 3
    metrics_ttl: int = 10
    enable_negative_caching: bool = True
    negative_cache_ttl: int = 5
    enable_versioning: bool = True


class QueryKeyBuilder:
    """Builds cache keys for different query types."""

    @staticmethod
    def worker_status(worker_id: str) -> str:
        """Build key for worker status query."""
        return f"worker:status:{worker_id}"

    @staticmethod
    def job_status(job_id: str) -> str:
        """Build key for job status query."""
        return f"job:status:{job_id}"

    @staticmethod
    def job_list(
        status: Optional[str] = None,
        priority: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> str:
        """Build key for job list query."""
        params = f"s={status or 'all'},p={priority or 'all'},l={limit},o={offset}"
        return f"job:list:{hashlib.md5(params.encode()).hexdigest()[:16]}"

    @staticmethod
    def worker_list(
        status: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """Build key for worker list query."""
        tag_str = ','.join(sorted(tags)) if tags else 'none'
        params = f"s={status or 'all'},t={tag_str}"
        return f"worker:list:{hashlib.md5(params.encode()).hexdigest()[:16]}"

    @staticmethod
    def resource_availability(resource_type: str = 'all') -> str:
        """Build key for resource availability query."""
        return f"resource:avail:{resource_type}"

    @staticmethod
    def scheduler_state() -> str:
        """Build key for scheduler state."""
        return "scheduler:state"

    @staticmethod
    def cluster_metrics(metric_type: str = 'all') -> str:
        """Build key for cluster metrics."""
        return f"cluster:metrics:{metric_type}"

    @staticmethod
    def lease_info(lease_id: str) -> str:
        """Build key for lease info."""
        return f"lease:info:{lease_id}"

    @staticmethod
    def queue_status(queue_name: str = 'default') -> str:
        """Build key for queue status."""
        return f"queue:status:{queue_name}"


class VersionTracker:
    """Tracks versions for cache invalidation."""

    def __init__(self):
        self.versions: Dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def get_version(self, key: str) -> int:
        """Get current version for a key."""
        with self._lock:
            return self.versions[key]

    def increment_version(self, key: str) -> int:
        """Increment and return new version."""
        with self._lock:
            self.versions[key] += 1
            return self.versions[key]

    def increment_pattern(self, pattern: str) -> int:
        """Increment version for all keys matching pattern."""
        with self._lock:
            count = 0
            for key in list(self.versions.keys()):
                if pattern in key:
                    self.versions[key] += 1
                    count += 1
            return count


class QueryCache:
    """
    Specialized cache for scheduler and cluster queries with
    intelligent invalidation and query-specific optimizations.
    """

    def __init__(self, config: Optional[QueryCacheConfig] = None):
        self.config = config or QueryCacheConfig()
        self.cache: Dict[str, CachedQuery] = {}
        self.version_tracker = VersionTracker()

        # Statistics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.invalidations = 0

        # LRU tracking
        self.access_order: deque = deque(maxlen=self.config.max_entries)

        # Query-specific TTLs
        self.ttl_map = {
            QueryType.WORKER_STATUS: self.config.worker_status_ttl,
            QueryType.JOB_STATUS: self.config.job_status_ttl,
            QueryType.JOB_LIST: self.config.job_list_ttl,
            QueryType.WORKER_LIST: self.config.worker_list_ttl,
            QueryType.RESOURCE_AVAILABILITY: self.config.resource_ttl,
            QueryType.SCHEDULER_STATE: self.config.scheduler_state_ttl,
            QueryType.CLUSTER_METRICS: self.config.metrics_ttl,
            QueryType.LEASE_INFO: self.config.job_status_ttl,
            QueryType.QUEUE_STATUS: self.config.resource_ttl,
        }

        # Event subscriptions for invalidation
        self.invalidation_handlers: Dict[str, List[Callable]] = defaultdict(list)

        self._lock = threading.RLock()
        self._cleanup_task: Optional[asyncio.Task] = None

    def get(
        self,
        key: str,
        query_type: Optional[QueryType] = None
    ) -> Optional[Any]:
        """Get a cached query result."""
        with self._lock:
            if key not in self.cache:
                self.misses += 1
                return None

            cached = self.cache[key]

            # Check expiration
            if cached.is_expired:
                del self.cache[key]
                self.misses += 1
                return None

            # Check version if enabled
            if self.config.enable_versioning:
                current_version = self.version_tracker.get_version(key)
                if cached.version < current_version:
                    del self.cache[key]
                    self.misses += 1
                    return None

            # Update hit statistics
            self.hits += 1
            cached.hit_count += 1
            cached.last_hit = time.time()

            # Update LRU order
            self._update_access_order(key)

            return cached.result

    def set(
        self,
        key: str,
        result: Any,
        query_type: QueryType,
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Set a query result in cache."""
        with self._lock:
            # Determine TTL
            if ttl is None:
                ttl = self.ttl_map.get(query_type, self.config.default_ttl_seconds)

            # Handle negative caching
            if result is None and not self.config.enable_negative_caching:
                return

            if result is None:
                ttl = self.config.negative_cache_ttl

            # Evict if necessary
            while len(self.cache) >= self.config.max_entries:
                self._evict_lru()

            current_time = time.time()
            version = self.version_tracker.get_version(key)

            self.cache[key] = CachedQuery(
                key=key,
                query_type=query_type,
                result=result,
                created_at=current_time,
                expires_at=current_time + ttl,
                version=version,
                metadata=metadata or {},
            )

            self._update_access_order(key)

    def invalidate(self, key: str):
        """Invalidate a specific cache entry."""
        with self._lock:
            if key in self.cache:
                del self.cache[key]
                self.invalidations += 1

            if self.config.enable_versioning:
                self.version_tracker.increment_version(key)

    def invalidate_pattern(self, pattern: str):
        """Invalidate all entries matching a pattern."""
        with self._lock:
            keys_to_remove = [k for k in self.cache if pattern in k]
            for key in keys_to_remove:
                del self.cache[key]
                self.invalidations += 1

            if self.config.enable_versioning:
                self.version_tracker.increment_pattern(pattern)

    def invalidate_query_type(self, query_type: QueryType):
        """Invalidate all entries of a specific query type."""
        with self._lock:
            keys_to_remove = [
                k for k, v in self.cache.items()
                if v.query_type == query_type
            ]
            for key in keys_to_remove:
                del self.cache[key]
                self.invalidations += 1

    def invalidate_worker(self, worker_id: str):
        """Invalidate all cache entries related to a worker."""
        patterns = [
            f"worker:status:{worker_id}",
            "worker:list:",
            "resource:avail:",
            "scheduler:state",
        ]
        for pattern in patterns:
            self.invalidate_pattern(pattern)

    def invalidate_job(self, job_id: str):
        """Invalidate all cache entries related to a job."""
        patterns = [
            f"job:status:{job_id}",
            "job:list:",
            "queue:status:",
            "scheduler:state",
        ]
        for pattern in patterns:
            self.invalidate_pattern(pattern)

    def _update_access_order(self, key: str):
        """Update LRU access order."""
        # Remove if exists
        try:
            self.access_order.remove(key)
        except ValueError:
            pass
        # Add to end (most recently used)
        self.access_order.append(key)

    def _evict_lru(self):
        """Evict the least recently used entry."""
        if self.access_order:
            lru_key = self.access_order.popleft()
            if lru_key in self.cache:
                del self.cache[lru_key]
                self.evictions += 1

    async def cleanup_expired(self):
        """Remove expired entries."""
        current_time = time.time()
        with self._lock:
            expired_keys = [
                k for k, v in self.cache.items()
                if v.expires_at < current_time
            ]
            for key in expired_keys:
                del self.cache[key]

    async def start_cleanup_loop(self, interval_seconds: float = 60.0):
        """Start background cleanup loop."""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(interval_seconds)
                await self.cleanup_expired()

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    async def stop_cleanup_loop(self):
        """Stop background cleanup loop."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self.hits + self.misses
            hit_rate = self.hits / total if total > 0 else 0

            return {
                'entries': len(self.cache),
                'max_entries': self.config.max_entries,
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': hit_rate,
                'evictions': self.evictions,
                'invalidations': self.invalidations,
                'by_type': self._get_stats_by_type(),
            }

    def _get_stats_by_type(self) -> Dict[str, int]:
        """Get entry count by query type."""
        counts: Dict[str, int] = defaultdict(int)
        for cached in self.cache.values():
            counts[cached.query_type.value] += 1
        return dict(counts)


class CachedQueryExecutor:
    """
    Executes queries with caching, providing a convenient interface
    for cached query execution.
    """

    def __init__(self, cache: QueryCache):
        self.cache = cache

    async def execute(
        self,
        key: str,
        query_type: QueryType,
        loader: Callable[[], Any],
        ttl: Optional[int] = None,
        force_refresh: bool = False
    ) -> Any:
        """Execute a query with caching."""
        # Check cache first
        if not force_refresh:
            cached = self.cache.get(key, query_type)
            if cached is not None:
                return cached

        # Execute query
        if asyncio.iscoroutinefunction(loader):
            result = await loader()
        else:
            result = loader()

        # Cache result
        self.cache.set(key, result, query_type, ttl)

        return result


def cached_query(
    cache: QueryCache,
    query_type: QueryType,
    key_builder: Callable[..., str],
    ttl: Optional[int] = None
):
    """Decorator for caching query results."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            key = key_builder(*args, **kwargs)

            # Check cache
            cached = cache.get(key, query_type)
            if cached is not None:
                return cached

            # Execute and cache
            result = await func(*args, **kwargs)
            cache.set(key, result, query_type, ttl)
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            key = key_builder(*args, **kwargs)

            # Check cache
            cached = cache.get(key, query_type)
            if cached is not None:
                return cached

            # Execute and cache
            result = func(*args, **kwargs)
            cache.set(key, result, query_type, ttl)
            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class BatchQueryCache:
    """
    Optimized cache for batch query operations with
    support for partial cache hits.
    """

    def __init__(self, cache: QueryCache, max_batch_size: int = 100):
        self.cache = cache
        self.max_batch_size = max_batch_size

    async def get_many(
        self,
        keys: List[str],
        query_type: QueryType,
        loader: Callable[[List[str]], Dict[str, Any]],
        ttl: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get multiple items, loading missing ones in batch."""
        results = {}
        missing_keys = []

        # Check cache for each key
        for key in keys[:self.max_batch_size]:
            cached = self.cache.get(key, query_type)
            if cached is not None:
                results[key] = cached
            else:
                missing_keys.append(key)

        # Load missing in batch
        if missing_keys:
            if asyncio.iscoroutinefunction(loader):
                loaded = await loader(missing_keys)
            else:
                loaded = loader(missing_keys)

            # Cache and add to results
            for key, value in loaded.items():
                self.cache.set(key, value, query_type, ttl)
                results[key] = value

        return results


class WorkerStatusCache:
    """Specialized cache for worker status with aggregation."""

    def __init__(self, cache: QueryCache):
        self.cache = cache
        self.key_builder = QueryKeyBuilder()

    def get_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get cached worker status."""
        key = self.key_builder.worker_status(worker_id)
        return self.cache.get(key, QueryType.WORKER_STATUS)

    def set_worker_status(self, worker_id: str, status: Dict[str, Any]):
        """Set worker status in cache."""
        key = self.key_builder.worker_status(worker_id)
        self.cache.set(key, status, QueryType.WORKER_STATUS)

    def get_all_workers_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all cached workers."""
        results = {}
        with self.cache._lock:
            for key, cached in self.cache.cache.items():
                if (cached.query_type == QueryType.WORKER_STATUS and
                    not cached.is_expired):
                    worker_id = key.split(':')[-1]
                    results[worker_id] = cached.result
        return results

    def invalidate_worker(self, worker_id: str):
        """Invalidate worker status cache."""
        self.cache.invalidate_worker(worker_id)


class JobStatusCache:
    """Specialized cache for job status with state transitions."""

    def __init__(self, cache: QueryCache):
        self.cache = cache
        self.key_builder = QueryKeyBuilder()
        self.state_transitions: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get cached job status."""
        key = self.key_builder.job_status(job_id)
        return self.cache.get(key, QueryType.JOB_STATUS)

    def set_job_status(self, job_id: str, status: Dict[str, Any]):
        """Set job status in cache."""
        key = self.key_builder.job_status(job_id)

        # Track state transition
        state = status.get('state', 'unknown')
        self.state_transitions[job_id].append((state, time.time()))

        self.cache.set(key, status, QueryType.JOB_STATUS)

    def get_state_history(self, job_id: str) -> List[Tuple[str, float]]:
        """Get state transition history for a job."""
        return self.state_transitions.get(job_id, [])

    def invalidate_job(self, job_id: str):
        """Invalidate job status cache."""
        self.cache.invalidate_job(job_id)


class SchedulerStateCache:
    """
    Cache for scheduler state with consistent snapshot support.
    """

    def __init__(self, cache: QueryCache):
        self.cache = cache
        self.key_builder = QueryKeyBuilder()
        self.snapshot_version = 0
        self._lock = threading.Lock()

    def get_state(self) -> Optional[Dict[str, Any]]:
        """Get cached scheduler state."""
        key = self.key_builder.scheduler_state()
        return self.cache.get(key, QueryType.SCHEDULER_STATE)

    def set_state(self, state: Dict[str, Any]):
        """Set scheduler state in cache."""
        with self._lock:
            self.snapshot_version += 1
            state['_version'] = self.snapshot_version

        key = self.key_builder.scheduler_state()
        self.cache.set(key, state, QueryType.SCHEDULER_STATE)

    def invalidate(self):
        """Invalidate scheduler state cache."""
        key = self.key_builder.scheduler_state()
        self.cache.invalidate(key)

    def get_snapshot_version(self) -> int:
        """Get current snapshot version."""
        with self._lock:
            return self.snapshot_version
