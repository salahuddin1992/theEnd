"""
Advanced Caching Layer for NebulaCompute.

This module provides comprehensive caching capabilities including:
- Redis integration for distributed caching
- Multi-level cache (L1 memory, L2 Redis)
- Cache invalidation strategies
- TTL management and eviction policies
"""

from .cache import (
    Cache,
    CacheConfig,
    CacheEntry,
    CacheStats,
    CacheError,
)
from .backends import (
    CacheBackend,
    MemoryBackend,
    RedisBackend,
    MemcachedBackend,
)
from .multilevel import (
    MultiLevelCache,
    L1Cache,
    L2Cache,
    CacheLevel,
)
from .invalidation import (
    InvalidationStrategy,
    TTLInvalidation,
    WriteThrough,
    WriteBehind,
    CacheAside,
    RefreshAhead,
    InvalidationEvent,
)
from .policies import (
    EvictionPolicy,
    LRUPolicy,
    LFUPolicy,
    FIFOPolicy,
    TTLPolicy,
    SizeBasedPolicy,
    AdaptivePolicy,
)
from .distributed import (
    DistributedCache,
    CacheCluster,
    ConsistentHashing,
    CacheNode,
)
from .decorators import (
    cached,
    cache_aside,
    cache_invalidate,
    memoize,
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
