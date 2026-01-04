"""
Unified Cache System for NebulaCompute - نظام الكاش الموحد
============================================================

This module provides a unified interface for all caching capabilities,
combining the distributed cache system with advanced caching features.

يوفر هذا الملف واجهة موحدة لجميع إمكانيات التخزين المؤقت.

Usage:
    from distributed_cluster.cache import (
        # Simple caching
        Cache,
        cached,
        memoize,

        # Advanced backends
        MemoryBackend,
        RedisBackend,
        TieredBackend,

        # Multi-level caching
        MultiLevelCache,

        # Distributed caching
        DistributedCache,
        CacheCluster,

        # Invalidation strategies
        WriteThrough,
        WriteBehind,
        CacheAside,
    )

Author: NebulaCompute Team
License: MIT
"""

# Core cache components
# Backends
from .backends import (
    CacheBackend,
    MemoryBackend,
    RedisBackend,
    TieredBackend,
)
from .cache_manager import CacheConfig, CacheManager

# Distributed caching
from .distributed import (
    CacheNode,
    CacheReplication,
    ConsistentHashing,
    DistributedCache,
)

# Strategies
from .strategies import (
    AdaptiveStrategy,
    CacheStrategy,
    LFUStrategy,
    LRUStrategy,
    TTLStrategy,
)

# Re-export from caching module for advanced features
try:
    from distributed_cluster.caching import (
        AdaptivePolicy,
        # Core
        Cache,
        CacheAside,
        # Distributed
        CacheCluster,
        CacheEntry,
        CacheError,
        CacheLevel,
        CacheStats,
        # Policies
        EvictionPolicy,
        FIFOPolicy,
        InvalidationEvent,
        # Invalidation
        InvalidationStrategy,
        L1Cache,
        L2Cache,
        LFUPolicy,
        LRUPolicy,
        # Additional backends
        MemcachedBackend,
        # Multi-level
        MultiLevelCache,
        RefreshAhead,
        SizeBasedPolicy,
        TTLInvalidation,
        TTLPolicy,
        WriteBehind,
        WriteThrough,
        cache_aside,
        cache_invalidate,
        # Decorators
        cached,
        memoize,
    )
    _CACHING_AVAILABLE = True
except ImportError:
    _CACHING_AVAILABLE = False
    # Provide stubs if caching module not available
    Cache = None
    CacheEntry = None
    CacheStats = None
    CacheError = None
    MultiLevelCache = None
    L1Cache = None
    L2Cache = None
    CacheLevel = None
    InvalidationStrategy = None
    TTLInvalidation = None
    WriteThrough = None
    WriteBehind = None
    CacheAside = None
    RefreshAhead = None
    InvalidationEvent = None
    EvictionPolicy = None
    LRUPolicy = None
    LFUPolicy = None
    FIFOPolicy = None
    TTLPolicy = None
    SizeBasedPolicy = None
    AdaptivePolicy = None
    MemcachedBackend = None
    CacheCluster = None
    cached = None
    cache_aside = None
    cache_invalidate = None
    memoize = None


def get_cache(
    backend: str = "memory",
    **kwargs,
) -> CacheManager:
    """
    إنشاء مدير كاش بسهولة
    Create a cache manager with sensible defaults

    Args:
        backend: Backend type ("memory", "redis", "tiered")
        **kwargs: Additional configuration

    Returns:
        Configured CacheManager instance

    Example:
        cache = get_cache("redis", url="redis://localhost:6379")
        await cache.set("key", "value", ttl=3600)
        value = await cache.get("key")
    """
    config = CacheConfig(**kwargs)

    if backend == "memory":
        cache_backend = MemoryBackend(
            max_size=kwargs.get("max_size", 10000),
        )
    elif backend == "redis":
        cache_backend = RedisBackend(
            url=kwargs.get("url", "redis://localhost:6379"),
            prefix=kwargs.get("prefix", "cache:"),
        )
    elif backend == "tiered":
        cache_backend = TieredBackend(
            l1_size=kwargs.get("l1_size", 1000),
            redis_url=kwargs.get("url", "redis://localhost:6379"),
        )
    else:
        raise ValueError(f"Unknown backend: {backend}")

    return CacheManager(backend=cache_backend, config=config)


__all__ = [
    # Factory
    "get_cache",
    # Core
    "CacheManager",
    "CacheConfig",
    "Cache",
    "CacheEntry",
    "CacheStats",
    "CacheError",
    # Backends
    "CacheBackend",
    "MemoryBackend",
    "RedisBackend",
    "TieredBackend",
    "MemcachedBackend",
    # Strategies
    "CacheStrategy",
    "LRUStrategy",
    "LFUStrategy",
    "TTLStrategy",
    "AdaptiveStrategy",
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
    "CacheNode",
    "ConsistentHashing",
    "CacheReplication",
    "CacheCluster",
    # Decorators
    "cached",
    "cache_aside",
    "cache_invalidate",
    "memoize",
]
