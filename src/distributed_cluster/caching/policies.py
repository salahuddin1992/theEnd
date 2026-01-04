"""
Cache eviction policies.
"""

import heapq
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheItem:
    """Represents an item in the cache for eviction tracking."""
    key: str
    size: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    expires_at: Optional[float] = None
    priority: int = 0

    def touch(self):
        """Update access time and count."""
        self.last_accessed = time.time()
        self.access_count += 1


class EvictionPolicy(ABC):
    """Abstract base class for cache eviction policies."""

    def __init__(self, max_size: int = 10000, max_memory_bytes: int = 0):
        self.max_size = max_size
        self.max_memory_bytes = max_memory_bytes
        self._items: Dict[str, CacheItem] = {}
        self._current_size = 0
        self._current_memory = 0
        self._lock = threading.RLock()

    @abstractmethod
    def on_access(self, key: str) -> None:
        """Called when an item is accessed."""
        pass

    @abstractmethod
    def on_insert(self, key: str, size: int = 0, ttl: Optional[int] = None, priority: int = 0) -> None:
        """Called when an item is inserted."""
        pass

    @abstractmethod
    def on_delete(self, key: str) -> None:
        """Called when an item is deleted."""
        pass

    @abstractmethod
    def evict(self) -> Optional[str]:
        """Evict an item and return its key."""
        pass

    def should_evict(self) -> bool:
        """Check if eviction is needed."""
        if self.max_size > 0 and self._current_size >= self.max_size:
            return True
        if self.max_memory_bytes > 0 and self._current_memory >= self.max_memory_bytes:
            return True
        return False

    def evict_many(self, count: int = 1) -> List[str]:
        """Evict multiple items."""
        evicted = []
        for _ in range(count):
            key = self.evict()
            if key:
                evicted.append(key)
            else:
                break
        return evicted

    @property
    def size(self) -> int:
        return self._current_size

    @property
    def memory_usage(self) -> int:
        return self._current_memory


class LRUPolicy(EvictionPolicy):
    """Least Recently Used eviction policy."""

    def __init__(self, max_size: int = 10000, max_memory_bytes: int = 0):
        super().__init__(max_size, max_memory_bytes)
        self._order: OrderedDict = OrderedDict()

    def on_access(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                self._items[key].touch()
                self._order.move_to_end(key)

    def on_insert(self, key: str, size: int = 0, ttl: Optional[int] = None, priority: int = 0) -> None:
        with self._lock:
            if key in self._items:
                # Update existing
                old_size = self._items[key].size
                self._current_memory -= old_size
            else:
                self._current_size += 1

            expires_at = time.time() + ttl if ttl else None
            item = CacheItem(key=key, size=size, expires_at=expires_at, priority=priority)

            self._items[key] = item
            self._order[key] = True
            self._order.move_to_end(key)
            self._current_memory += size

    def on_delete(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                self._current_memory -= self._items[key].size
                del self._items[key]
                del self._order[key]
                self._current_size -= 1

    def evict(self) -> Optional[str]:
        with self._lock:
            if not self._order:
                return None

            key, _ = self._order.popitem(last=False)
            if key in self._items:
                self._current_memory -= self._items[key].size
                del self._items[key]
                self._current_size -= 1

            return key


class LFUPolicy(EvictionPolicy):
    """Least Frequently Used eviction policy."""

    def __init__(self, max_size: int = 10000, max_memory_bytes: int = 0):
        super().__init__(max_size, max_memory_bytes)
        self._freq_map: Dict[str, int] = {}
        self._min_freq = 0
        self._freq_to_keys: Dict[int, OrderedDict] = defaultdict(OrderedDict)

    def on_access(self, key: str) -> None:
        with self._lock:
            if key not in self._items:
                return

            self._items[key].touch()

            # Update frequency
            old_freq = self._freq_map[key]
            new_freq = old_freq + 1

            self._freq_map[key] = new_freq
            del self._freq_to_keys[old_freq][key]

            if not self._freq_to_keys[old_freq]:
                del self._freq_to_keys[old_freq]
                if self._min_freq == old_freq:
                    self._min_freq = new_freq

            self._freq_to_keys[new_freq][key] = True

    def on_insert(self, key: str, size: int = 0, ttl: Optional[int] = None, priority: int = 0) -> None:
        with self._lock:
            if key in self._items:
                # Update existing
                self.on_access(key)
                old_size = self._items[key].size
                self._items[key].size = size
                self._current_memory = self._current_memory - old_size + size
                return

            expires_at = time.time() + ttl if ttl else None
            item = CacheItem(key=key, size=size, expires_at=expires_at, priority=priority)

            self._items[key] = item
            self._freq_map[key] = 1
            self._freq_to_keys[1][key] = True
            self._min_freq = 1
            self._current_size += 1
            self._current_memory += size

    def on_delete(self, key: str) -> None:
        with self._lock:
            if key not in self._items:
                return

            freq = self._freq_map[key]
            del self._freq_to_keys[freq][key]

            if not self._freq_to_keys[freq]:
                del self._freq_to_keys[freq]

            del self._freq_map[key]
            self._current_memory -= self._items[key].size
            del self._items[key]
            self._current_size -= 1

    def evict(self) -> Optional[str]:
        with self._lock:
            if not self._freq_to_keys:
                return None

            # Find minimum frequency
            min_freq = min(self._freq_to_keys.keys())
            key, _ = self._freq_to_keys[min_freq].popitem(last=False)

            if not self._freq_to_keys[min_freq]:
                del self._freq_to_keys[min_freq]

            del self._freq_map[key]
            self._current_memory -= self._items[key].size
            del self._items[key]
            self._current_size -= 1

            return key


class FIFOPolicy(EvictionPolicy):
    """First In First Out eviction policy."""

    def __init__(self, max_size: int = 10000, max_memory_bytes: int = 0):
        super().__init__(max_size, max_memory_bytes)
        self._order: OrderedDict = OrderedDict()

    def on_access(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                self._items[key].touch()

    def on_insert(self, key: str, size: int = 0, ttl: Optional[int] = None, priority: int = 0) -> None:
        with self._lock:
            if key in self._items:
                old_size = self._items[key].size
                self._current_memory -= old_size
            else:
                self._current_size += 1

            expires_at = time.time() + ttl if ttl else None
            item = CacheItem(key=key, size=size, expires_at=expires_at, priority=priority)

            self._items[key] = item
            if key not in self._order:
                self._order[key] = True
            self._current_memory += size

    def on_delete(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                self._current_memory -= self._items[key].size
                del self._items[key]
                self._order.pop(key, None)
                self._current_size -= 1

    def evict(self) -> Optional[str]:
        with self._lock:
            if not self._order:
                return None

            key, _ = self._order.popitem(last=False)
            if key in self._items:
                self._current_memory -= self._items[key].size
                del self._items[key]
                self._current_size -= 1

            return key


class TTLPolicy(EvictionPolicy):
    """TTL-based eviction policy - evicts expired items first."""

    def __init__(self, max_size: int = 10000, max_memory_bytes: int = 0):
        super().__init__(max_size, max_memory_bytes)
        self._expiry_heap: List[Tuple[float, str]] = []  # (expires_at, key)
        self._key_expiry: Dict[str, float] = {}

    def on_access(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                self._items[key].touch()

    def on_insert(self, key: str, size: int = 0, ttl: Optional[int] = None, priority: int = 0) -> None:
        with self._lock:
            if key in self._items:
                old_size = self._items[key].size
                self._current_memory -= old_size
            else:
                self._current_size += 1

            expires_at = time.time() + ttl if ttl else float('inf')
            item = CacheItem(key=key, size=size, expires_at=expires_at, priority=priority)

            self._items[key] = item
            self._key_expiry[key] = expires_at
            heapq.heappush(self._expiry_heap, (expires_at, key))
            self._current_memory += size

    def on_delete(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                self._current_memory -= self._items[key].size
                del self._items[key]
                self._key_expiry.pop(key, None)
                self._current_size -= 1

    def evict(self) -> Optional[str]:
        with self._lock:
            now = time.time()

            # First try to evict expired items
            while self._expiry_heap:
                expires_at, key = self._expiry_heap[0]

                # Skip if key was deleted or TTL was updated
                if key not in self._key_expiry or self._key_expiry[key] != expires_at:
                    heapq.heappop(self._expiry_heap)
                    continue

                if expires_at <= now:
                    heapq.heappop(self._expiry_heap)
                    if key in self._items:
                        self._current_memory -= self._items[key].size
                        del self._items[key]
                        del self._key_expiry[key]
                        self._current_size -= 1
                        return key
                else:
                    break

            # No expired items, evict the one with earliest expiry
            while self._expiry_heap:
                expires_at, key = heapq.heappop(self._expiry_heap)

                if key not in self._key_expiry or self._key_expiry[key] != expires_at:
                    continue

                if key in self._items:
                    self._current_memory -= self._items[key].size
                    del self._items[key]
                    del self._key_expiry[key]
                    self._current_size -= 1
                    return key

            return None

    def cleanup_expired(self) -> int:
        """Remove all expired items."""
        count = 0
        now = time.time()

        with self._lock:
            for key, expires_at in list(self._key_expiry.items()):
                if expires_at <= now:
                    self.on_delete(key)
                    count += 1

        return count


class SizeBasedPolicy(EvictionPolicy):
    """Size-based eviction policy - evicts largest items first."""

    def __init__(self, max_size: int = 10000, max_memory_bytes: int = 0):
        super().__init__(max_size, max_memory_bytes)
        self._size_heap: List[Tuple[int, str]] = []  # (-size, key) for max heap
        self._key_size: Dict[str, int] = {}

    def on_access(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                self._items[key].touch()

    def on_insert(self, key: str, size: int = 0, ttl: Optional[int] = None, priority: int = 0) -> None:
        with self._lock:
            if key in self._items:
                old_size = self._items[key].size
                self._current_memory -= old_size
            else:
                self._current_size += 1

            expires_at = time.time() + ttl if ttl else None
            item = CacheItem(key=key, size=size, expires_at=expires_at, priority=priority)

            self._items[key] = item
            self._key_size[key] = size
            heapq.heappush(self._size_heap, (-size, key))
            self._current_memory += size

    def on_delete(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                self._current_memory -= self._items[key].size
                del self._items[key]
                self._key_size.pop(key, None)
                self._current_size -= 1

    def evict(self) -> Optional[str]:
        with self._lock:
            while self._size_heap:
                neg_size, key = heapq.heappop(self._size_heap)

                if key not in self._key_size or self._key_size[key] != -neg_size:
                    continue

                if key in self._items:
                    self._current_memory -= self._items[key].size
                    del self._items[key]
                    del self._key_size[key]
                    self._current_size -= 1
                    return key

            return None


class AdaptivePolicy(EvictionPolicy):
    """
    Adaptive eviction policy that combines LRU and LFU.

    Uses a learning rate to balance between recency and frequency.
    """

    def __init__(
        self,
        max_size: int = 10000,
        max_memory_bytes: int = 0,
        learning_rate: float = 0.5,
        window_size: int = 1000
    ):
        super().__init__(max_size, max_memory_bytes)
        self.learning_rate = learning_rate
        self.window_size = window_size

        self._lru = LRUPolicy(max_size, max_memory_bytes)
        self._lfu = LFUPolicy(max_size, max_memory_bytes)

        self._hit_window: List[bool] = []  # True for LRU hit, False for LFU hit
        self._lru_weight = 0.5

    def _update_weights(self, lru_hit: bool):
        """Update weights based on recent hits."""
        self._hit_window.append(lru_hit)

        if len(self._hit_window) > self.window_size:
            self._hit_window.pop(0)

        if len(self._hit_window) >= 100:
            lru_hits = sum(self._hit_window)
            lfu_hits = len(self._hit_window) - lru_hits

            if lru_hits + lfu_hits > 0:
                lru_ratio = lru_hits / (lru_hits + lfu_hits)
                self._lru_weight = (
                    self._lru_weight * (1 - self.learning_rate) +
                    lru_ratio * self.learning_rate
                )

    def on_access(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                self._items[key].touch()
                self._lru.on_access(key)
                self._lfu.on_access(key)

    def on_insert(self, key: str, size: int = 0, ttl: Optional[int] = None, priority: int = 0) -> None:
        with self._lock:
            if key in self._items:
                old_size = self._items[key].size
                self._current_memory -= old_size
            else:
                self._current_size += 1

            expires_at = time.time() + ttl if ttl else None
            item = CacheItem(key=key, size=size, expires_at=expires_at, priority=priority)

            self._items[key] = item
            self._current_memory += size

            self._lru.on_insert(key, size, ttl, priority)
            self._lfu.on_insert(key, size, ttl, priority)

    def on_delete(self, key: str) -> None:
        with self._lock:
            if key in self._items:
                self._current_memory -= self._items[key].size
                del self._items[key]
                self._current_size -= 1

                self._lru.on_delete(key)
                self._lfu.on_delete(key)

    def evict(self) -> Optional[str]:
        with self._lock:
            import random

            # Choose eviction strategy based on weights
            if random.random() < self._lru_weight:
                key = self._lru.evict()
                if key:
                    self._lfu.on_delete(key)
                    if key in self._items:
                        self._current_memory -= self._items[key].size
                        del self._items[key]
                        self._current_size -= 1
                    return key
            else:
                key = self._lfu.evict()
                if key:
                    self._lru.on_delete(key)
                    if key in self._items:
                        self._current_memory -= self._items[key].size
                        del self._items[key]
                        self._current_size -= 1
                    return key

            return None


class PolicyFactory:
    """Factory for creating eviction policies."""

    _policies: Dict[str, type] = {
        "lru": LRUPolicy,
        "lfu": LFUPolicy,
        "fifo": FIFOPolicy,
        "ttl": TTLPolicy,
        "size": SizeBasedPolicy,
        "adaptive": AdaptivePolicy,
    }

    @classmethod
    def create(cls, policy_name: str, **kwargs) -> EvictionPolicy:
        """Create a policy instance."""
        policy_class = cls._policies.get(policy_name.lower())
        if not policy_class:
            raise ValueError(f"Unknown policy: {policy_name}")
        return policy_class(**kwargs)

    @classmethod
    def register(cls, name: str, policy_class: type):
        """Register a new policy type."""
        cls._policies[name.lower()] = policy_class
