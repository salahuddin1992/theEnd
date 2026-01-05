"""
Cache Eviction Strategies for NebulaCompute.

Provides multiple eviction strategies:
- LRU (Least Recently Used)
- LFU (Least Frequently Used)
- TTL (Time-To-Live based)
- Adaptive (ML-based dynamic strategy)
"""

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheItem:
    """Represents a cached item with metadata."""

    key: str
    value: Any
    size_bytes: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    ttl: Optional[float] = None  # Expiration timestamp

    @property
    def is_expired(self) -> bool:
        """Check if item has expired."""
        if self.ttl is None:
            return False
        return time.time() > self.ttl

    @property
    def age(self) -> float:
        """Get item age in seconds."""
        return time.time() - self.created_at

    @property
    def idle_time(self) -> float:
        """Get time since last access in seconds."""
        return time.time() - self.last_accessed


class CacheStrategy(ABC):
    """Abstract base class for eviction strategies."""

    @abstractmethod
    def on_access(self, item: CacheItem) -> None:
        """Called when an item is accessed."""
        pass

    @abstractmethod
    def on_insert(self, item: CacheItem) -> None:
        """Called when an item is inserted."""
        pass

    @abstractmethod
    def on_delete(self, key: str) -> None:
        """Called when an item is deleted."""
        pass

    @abstractmethod
    def select_victim(self, items: Dict[str, CacheItem]) -> Optional[str]:
        """Select an item to evict."""
        pass

    @abstractmethod
    def select_victims(
        self,
        items: Dict[str, CacheItem],
        count: int,
    ) -> List[str]:
        """Select multiple items to evict."""
        pass


class LRUStrategy(CacheStrategy):
    """
    Least Recently Used eviction strategy.

    Evicts items that haven't been accessed for the longest time.
    Good for temporal locality workloads.
    """

    def __init__(self):
        self._access_order: Dict[str, float] = {}

    def on_access(self, item: CacheItem) -> None:
        """Update access time."""
        item.last_accessed = time.time()
        item.access_count += 1
        self._access_order[item.key] = item.last_accessed

    def on_insert(self, item: CacheItem) -> None:
        """Track new item."""
        self._access_order[item.key] = item.last_accessed

    def on_delete(self, key: str) -> None:
        """Remove tracking."""
        self._access_order.pop(key, None)

    def select_victim(self, items: Dict[str, CacheItem]) -> Optional[str]:
        """Select least recently used item."""
        if not self._access_order:
            return None

        return min(self._access_order, key=self._access_order.get)

    def select_victims(
        self,
        items: Dict[str, CacheItem],
        count: int,
    ) -> List[str]:
        """Select multiple LRU items."""
        sorted_keys = sorted(
            self._access_order,
            key=self._access_order.get,
        )
        return sorted_keys[:count]


class LFUStrategy(CacheStrategy):
    """
    Least Frequently Used eviction strategy.

    Evicts items that have been accessed the fewest times.
    Good for popularity-based workloads.
    """

    def __init__(self, decay_factor: float = 0.99):
        self._frequencies: Dict[str, float] = {}
        self._decay_factor = decay_factor
        self._last_decay = time.time()
        self._decay_interval = 60  # Decay every minute

    def on_access(self, item: CacheItem) -> None:
        """Increment frequency."""
        self._maybe_decay()
        item.access_count += 1
        self._frequencies[item.key] = self._frequencies.get(item.key, 0) + 1

    def on_insert(self, item: CacheItem) -> None:
        """Initialize frequency."""
        self._frequencies[item.key] = 1

    def on_delete(self, key: str) -> None:
        """Remove tracking."""
        self._frequencies.pop(key, None)

    def _maybe_decay(self) -> None:
        """Apply time decay to frequencies."""
        now = time.time()
        if now - self._last_decay > self._decay_interval:
            for key in self._frequencies:
                self._frequencies[key] *= self._decay_factor
            self._last_decay = now

    def select_victim(self, items: Dict[str, CacheItem]) -> Optional[str]:
        """Select least frequently used item."""
        if not self._frequencies:
            return None

        return min(self._frequencies, key=self._frequencies.get)

    def select_victims(
        self,
        items: Dict[str, CacheItem],
        count: int,
    ) -> List[str]:
        """Select multiple LFU items."""
        sorted_keys = sorted(
            self._frequencies,
            key=self._frequencies.get,
        )
        return sorted_keys[:count]


class TTLStrategy(CacheStrategy):
    """
    Time-To-Live based eviction strategy.

    Evicts items closest to expiration first.
    Good for time-sensitive data.
    """

    def __init__(self, default_ttl: int = 300):
        self._expirations: Dict[str, float] = {}
        self.default_ttl = default_ttl

    def on_access(self, item: CacheItem) -> None:
        """Update access (no change to TTL)."""
        item.access_count += 1

    def on_insert(self, item: CacheItem) -> None:
        """Track expiration."""
        if item.ttl:
            self._expirations[item.key] = item.ttl
        else:
            self._expirations[item.key] = time.time() + self.default_ttl

    def on_delete(self, key: str) -> None:
        """Remove tracking."""
        self._expirations.pop(key, None)

    def select_victim(self, items: Dict[str, CacheItem]) -> Optional[str]:
        """Select item closest to expiration."""
        if not self._expirations:
            return None

        # First, check for expired items
        now = time.time()
        for key, expiration in self._expirations.items():
            if now > expiration:
                return key

        # Otherwise, return closest to expiration
        return min(self._expirations, key=self._expirations.get)

    def select_victims(
        self,
        items: Dict[str, CacheItem],
        count: int,
    ) -> List[str]:
        """Select items by expiration."""
        sorted_keys = sorted(
            self._expirations,
            key=self._expirations.get,
        )
        return sorted_keys[:count]

    def get_expired(self) -> List[str]:
        """Get all expired keys."""
        now = time.time()
        return [key for key, exp in self._expirations.items() if now > exp]


class AdaptiveStrategy(CacheStrategy):
    """
    Adaptive eviction strategy using multiple signals.

    Combines LRU, LFU, and TTL with dynamic weighting
    based on observed workload patterns.

    Features:
    - Automatic weight adjustment
    - Workload pattern detection
    - Cost-aware eviction
    """

    def __init__(
        self,
        lru_weight: float = 0.4,
        lfu_weight: float = 0.4,
        size_weight: float = 0.2,
        adaptation_rate: float = 0.1,
    ):
        self.lru_weight = lru_weight
        self.lfu_weight = lfu_weight
        self.size_weight = size_weight
        self.adaptation_rate = adaptation_rate

        # Sub-strategies
        self._lru = LRUStrategy()
        self._lfu = LFUStrategy()

        # Metrics for adaptation
        self._hits_after_eviction: Dict[str, int] = defaultdict(int)
        self._eviction_count = 0
        self._regret_count = 0  # Evicted items that were accessed again

    def on_access(self, item: CacheItem) -> None:
        """Update all sub-strategies."""
        self._lru.on_access(item)
        self._lfu.on_access(item)
        item.access_count += 1

        # Track regret for evicted items
        if item.key in self._hits_after_eviction:
            self._regret_count += 1
            del self._hits_after_eviction[item.key]

    def on_insert(self, item: CacheItem) -> None:
        """Track in all sub-strategies."""
        self._lru.on_insert(item)
        self._lfu.on_insert(item)

    def on_delete(self, key: str) -> None:
        """Remove from all sub-strategies."""
        self._lru.on_delete(key)
        self._lfu.on_delete(key)

    def _calculate_score(self, item: CacheItem) -> float:
        """
        Calculate eviction score for an item.
        Higher score = more likely to be evicted.
        """
        # Normalize metrics
        idle_score = min(item.idle_time / 3600, 1.0)  # Cap at 1 hour
        freq_score = 1.0 / (1 + item.access_count)  # Lower freq = higher score
        size_score = min(item.size_bytes / (1024 * 1024), 1.0)  # Cap at 1MB

        # Weighted combination
        score = self.lru_weight * idle_score + self.lfu_weight * freq_score + self.size_weight * size_score

        return score

    def select_victim(self, items: Dict[str, CacheItem]) -> Optional[str]:
        """Select item with highest eviction score."""
        if not items:
            return None

        # First, evict expired items
        for key, item in items.items():
            if item.is_expired:
                return key

        # Calculate scores and select highest
        scores = {key: self._calculate_score(item) for key, item in items.items()}
        victim = max(scores, key=scores.get)

        # Track for regret analysis
        self._eviction_count += 1
        self._hits_after_eviction[victim] = 0

        return victim

    def select_victims(
        self,
        items: Dict[str, CacheItem],
        count: int,
    ) -> List[str]:
        """Select multiple victims by score."""
        if not items:
            return []

        # Calculate all scores
        scores = [(key, self._calculate_score(item)) for key, item in items.items()]

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        victims = [key for key, _ in scores[:count]]

        # Track for regret
        for victim in victims:
            self._eviction_count += 1
            self._hits_after_eviction[victim] = 0

        return victims

    def adapt_weights(self) -> None:
        """
        Adjust weights based on observed performance.

        If we're seeing high regret (evicting items that get
        accessed again), we should increase LFU weight.
        """
        if self._eviction_count < 100:
            return  # Not enough data

        regret_rate = self._regret_count / self._eviction_count

        if regret_rate > 0.1:
            # High regret - increase LFU weight
            adjustment = self.adaptation_rate
            self.lfu_weight = min(0.6, self.lfu_weight + adjustment)
            self.lru_weight = max(0.2, self.lru_weight - adjustment / 2)
            self.size_weight = max(0.1, self.size_weight - adjustment / 2)

        elif regret_rate < 0.05:
            # Low regret - current weights are good, maybe increase LRU
            adjustment = self.adaptation_rate / 2
            self.lru_weight = min(0.5, self.lru_weight + adjustment)
            self.lfu_weight = max(0.3, self.lfu_weight - adjustment)

        # Normalize weights
        total = self.lru_weight + self.lfu_weight + self.size_weight
        self.lru_weight /= total
        self.lfu_weight /= total
        self.size_weight /= total

        # Reset counters
        self._eviction_count = 0
        self._regret_count = 0

        logger.debug(
            "Adapted weights: LRU=%.2f, LFU=%.2f, Size=%.2f",
            self.lru_weight,
            self.lfu_weight,
            self.size_weight,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get strategy statistics."""
        regret_rate = self._regret_count / self._eviction_count if self._eviction_count > 0 else 0

        return {
            "lru_weight": self.lru_weight,
            "lfu_weight": self.lfu_weight,
            "size_weight": self.size_weight,
            "eviction_count": self._eviction_count,
            "regret_count": self._regret_count,
            "regret_rate": f"{regret_rate:.2%}",
        }


class SLRUStrategy(CacheStrategy):
    """
    Segmented LRU eviction strategy.

    Divides cache into protected and probationary segments.
    Items promoted to protected on second access.
    Good for scan-resistant caching.
    """

    def __init__(self, protected_ratio: float = 0.8):
        self.protected_ratio = protected_ratio
        self._probationary: Dict[str, float] = {}  # key -> last_accessed
        self._protected: Dict[str, float] = {}  # key -> last_accessed

    def on_access(self, item: CacheItem) -> None:
        """Promote to protected on access."""
        item.last_accessed = time.time()
        item.access_count += 1

        if item.key in self._probationary:
            # Promote to protected
            del self._probationary[item.key]
            self._protected[item.key] = item.last_accessed
        elif item.key in self._protected:
            # Update protected
            self._protected[item.key] = item.last_accessed

    def on_insert(self, item: CacheItem) -> None:
        """Insert to probationary."""
        self._probationary[item.key] = item.last_accessed

    def on_delete(self, key: str) -> None:
        """Remove from both segments."""
        self._probationary.pop(key, None)
        self._protected.pop(key, None)

    def select_victim(self, items: Dict[str, CacheItem]) -> Optional[str]:
        """Select from probationary first, then protected."""
        # Evict from probationary first
        if self._probationary:
            return min(self._probationary, key=self._probationary.get)

        # Then from protected
        if self._protected:
            return min(self._protected, key=self._protected.get)

        return None

    def select_victims(
        self,
        items: Dict[str, CacheItem],
        count: int,
    ) -> List[str]:
        """Select victims from both segments."""
        victims = []

        # From probationary
        prob_sorted = sorted(self._probationary, key=self._probationary.get)
        victims.extend(prob_sorted[:count])

        # From protected if needed
        if len(victims) < count:
            remaining = count - len(victims)
            prot_sorted = sorted(self._protected, key=self._protected.get)
            victims.extend(prot_sorted[:remaining])

        return victims[:count]
