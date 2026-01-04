"""
Advanced Caching Layer for NebulaCompute.

This module provides comprehensive caching capabilities including:
- Redis integration for distributed caching
- Multi-level cache (L1 memory, L2 Redis)
- Cache invalidation strategies
- TTL management and eviction policies
"""

from .backends import (
    CacheBackend,
    MemcachedBackend,
    MemoryBackend,
    RedisBackend,
)
from .cache import (
    Cache,
    CacheConfig,
    CacheEntry,
    CacheError,
    CacheStats,
)
from .decorators import (
    cache_aside,
    cache_invalidate,
    cached,
    memoize,
)
from .distributed import (
    CacheCluster,
    CacheNode,
    ConsistentHashing,
    DistributedCache,
)
from .invalidation import (
    CacheAside,
    InvalidationEvent,
    InvalidationStrategy,
    RefreshAhead,
    TTLInvalidation,
    WriteBehind,
    WriteThrough,
)
from .multilevel import (
    CacheLevel,
    L1Cache,
    L2Cache,
    MultiLevelCache,
)
from .policies import (
    AdaptivePolicy,
    EvictionPolicy,
    FIFOPolicy,
    LFUPolicy,
    LRUPolicy,
    SizeBasedPolicy,
    TTLPolicy,
)

__all__ = [
    # Core
    "Cache",
    "CacheConfig",
    "CacheEntry",
    "CacheStats",
    "CacheError",
    # Backends
    "CacheBackend",
    "MemoryBackend",
    "RedisBackend",
    "MemcachedBackend",
    # Multi-level
    "MultiLevelCache",
    "L1Cache",
    "L2Cache",
    "CacheLevel",
    # Invalidation
    "InvalidationStrategy",
    "TTLInvalidation",
    "WriteThrough",
    "WriteBehind",
    "CacheAside",
    "RefreshAhead",
    "InvalidationEvent",
    # Policies
    "EvictionPolicy",
    "LRUPolicy",
    "LFUPolicy",
    "FIFOPolicy",
    "TTLPolicy",
    "SizeBasedPolicy",
    "AdaptivePolicy",
    # Distributed
    "DistributedCache",
    "CacheCluster",
    "ConsistentHashing",
    "CacheNode",
    # Decorators
    "cached",
    "cache_aside",
    "cache_invalidate",
    "memoize",
]
