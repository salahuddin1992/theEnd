"""
Distributed Cache System for NebulaCompute.

Provides high-performance distributed caching with multiple backends
to reduce latency and improve throughput.
"""

from .cache_manager import CacheManager, CacheConfig
from .backends import (
    CacheBackend,
    MemoryBackend,
    RedisBackend,
    TieredBackend,
)
from .strategies import (
    CacheStrategy,
    LRUStrategy,
    LFUStrategy,
    TTLStrategy,
    AdaptiveStrategy,
)
from .distributed import (
    DistributedCache,
    CacheNode,
    ConsistentHashing,
    CacheReplication,
)

__all__ = [
    # Core
    "CacheManager",
    "CacheConfig",
    # Backends
    "CacheBackend",
    "MemoryBackend",
    "RedisBackend",
    "TieredBackend",
    # Strategies
    "CacheStrategy",
    "LRUStrategy",
    "LFUStrategy",
    "TTLStrategy",
    "AdaptiveStrategy",
    # Distributed
    "DistributedCache",
    "CacheNode",
    "ConsistentHashing",
    "CacheReplication",
]
