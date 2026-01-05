"""
Hot Data Tracker - Track and prioritize frequently accessed data.

This module provides sophisticated hot data detection and tracking
with support for dynamic threshold adjustment, time-based decay,
and predictive access modeling.
"""

import asyncio
import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class HotLevel(Enum):
    """Classification levels for data hotness."""

    COLD = 0
    COOL = 1
    WARM = 2
    HOT = 3
    CRITICAL = 4


class AccessEventType(Enum):
    """Types of access events."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SCAN = "scan"


@dataclass
class AccessEvent:
    """Represents a single access event."""

    key: str
    event_type: AccessEventType
    timestamp: float
    latency_ms: float = 0.0
    value_size: int = 0


@dataclass
class KeyMetrics:
    """Metrics for a single key."""

    key: str
    access_count: int = 0
    read_count: int = 0
    write_count: int = 0
    total_latency_ms: float = 0.0
    total_size_bytes: int = 0
    first_access: Optional[float] = None
    last_access: Optional[float] = None
    frequency_score: float = 0.0
    recency_score: float = 0.0
    combined_score: float = 0.0
    hot_level: HotLevel = HotLevel.COLD

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        return self.total_latency_ms / self.access_count if self.access_count > 0 else 0.0

    @property
    def age_seconds(self) -> float:
        """Get age since first access."""
        if self.first_access is None:
            return 0.0
        return time.time() - self.first_access

    @property
    def idle_seconds(self) -> float:
        """Get time since last access."""
        if self.last_access is None:
            return float("inf")
        return time.time() - self.last_access


@dataclass
class HotDataConfig:
    """Configuration for hot data tracking."""

    window_seconds: float = 3600.0  # Time window for analysis
    decay_factor: float = 0.9  # Decay factor per interval
    decay_interval_seconds: float = 60.0  # Decay interval
    hot_threshold: float = 0.7  # Score threshold for HOT
    critical_threshold: float = 0.9  # Score threshold for CRITICAL
    min_accesses: int = 5  # Minimum accesses to consider
    frequency_weight: float = 0.6  # Weight for frequency in score
    recency_weight: float = 0.4  # Weight for recency in score
    max_tracked_keys: int = 100000  # Maximum keys to track


class FrequencyCounter:
    """
    Count-Min Sketch based frequency counter for efficient
    approximate frequency counting.
    """

    def __init__(self, width: int = 10000, depth: int = 5):
        self.width = width
        self.depth = depth
        self.counters = [[0] * width for _ in range(depth)]
        self._lock = threading.Lock()

    def _hash(self, key: str, seed: int) -> int:
        """Hash a key with a seed."""
        h = hash(key + str(seed))
        return abs(h) % self.width

    def increment(self, key: str, amount: int = 1):
        """Increment the count for a key."""
        with self._lock:
            for i in range(self.depth):
                idx = self._hash(key, i)
                self.counters[i][idx] += amount

    def estimate(self, key: str) -> int:
        """Estimate the count for a key."""
        with self._lock:
            return min(self.counters[i][self._hash(key, i)] for i in range(self.depth))

    def decay(self, factor: float):
        """Apply decay to all counters."""
        with self._lock:
            for i in range(self.depth):
                for j in range(self.width):
                    self.counters[i][j] = int(self.counters[i][j] * factor)


class RecencyTracker:
    """Tracks recency of key accesses using time-based buckets."""

    def __init__(self, num_buckets: int = 60, bucket_seconds: float = 60.0):
        self.num_buckets = num_buckets
        self.bucket_seconds = bucket_seconds
        self.buckets: List[Set[str]] = [set() for _ in range(num_buckets)]
        self.key_bucket: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._last_bucket_time = time.time()

    def touch(self, key: str):
        """Record an access to a key."""
        with self._lock:
            current_bucket = int(time.time() / self.bucket_seconds) % self.num_buckets

            # Remove from old bucket
            if key in self.key_bucket:
                old_bucket = self.key_bucket[key]
                self.buckets[old_bucket].discard(key)

            # Add to current bucket
            self.buckets[current_bucket].add(key)
            self.key_bucket[key] = current_bucket

    def get_recency_score(self, key: str) -> float:
        """Get recency score (0-1) for a key."""
        with self._lock:
            if key not in self.key_bucket:
                return 0.0

            key_bucket = self.key_bucket[key]
            current_bucket = int(time.time() / self.bucket_seconds) % self.num_buckets

            # Calculate bucket distance
            distance = (current_bucket - key_bucket) % self.num_buckets
            return max(0.0, 1.0 - (distance / self.num_buckets))

    def cleanup(self, max_age_buckets: int = 30):
        """Remove old entries."""
        with self._lock:
            current_bucket = int(time.time() / self.bucket_seconds) % self.num_buckets

            for i in range(max_age_buckets, self.num_buckets):
                old_bucket = (current_bucket - i) % self.num_buckets
                for key in list(self.buckets[old_bucket]):
                    if self.key_bucket.get(key) == old_bucket:
                        del self.key_bucket[key]
                self.buckets[old_bucket].clear()


class HotDataTracker:
    """
    Comprehensive hot data tracking with dynamic threshold adjustment
    and predictive modeling.
    """

    def __init__(self, config: Optional[HotDataConfig] = None):
        self.config = config or HotDataConfig()

        # Frequency tracking
        self.frequency_counter = FrequencyCounter()

        # Recency tracking
        self.recency_tracker = RecencyTracker()

        # Detailed key metrics
        self.key_metrics: Dict[str, KeyMetrics] = {}

        # Hot keys by level
        self.hot_keys: Dict[HotLevel, Set[str]] = {level: set() for level in HotLevel}

        # Access history for pattern analysis
        self.recent_accesses: deque = deque(maxlen=10000)

        # Callbacks
        self.hot_key_callbacks: List[Callable[[str, HotLevel], None]] = []
        self.threshold_callbacks: List[Callable[[float, float], None]] = []

        # Dynamic thresholds
        self.current_hot_threshold = self.config.hot_threshold
        self.current_critical_threshold = self.config.critical_threshold

        # Statistics
        self.total_accesses = 0
        self.keys_promoted = 0
        self.keys_demoted = 0

        # Control
        self._lock = threading.RLock()
        self._running = False
        self._decay_task: Optional[asyncio.Task] = None
        self._last_decay_time = time.time()

    def record_access(
        self, key: str, event_type: AccessEventType = AccessEventType.READ, latency_ms: float = 0.0, value_size: int = 0
    ):
        """Record an access event."""
        current_time = time.time()

        with self._lock:
            self.total_accesses += 1

            # Update frequency counter
            self.frequency_counter.increment(key)

            # Update recency tracker
            self.recency_tracker.touch(key)

            # Update detailed metrics
            if key not in self.key_metrics:
                if len(self.key_metrics) >= self.config.max_tracked_keys:
                    self._evict_cold_keys()

                self.key_metrics[key] = KeyMetrics(
                    key=key,
                    first_access=current_time,
                )

            metrics = self.key_metrics[key]
            metrics.access_count += 1
            metrics.last_access = current_time
            metrics.total_latency_ms += latency_ms
            metrics.total_size_bytes += value_size

            if event_type == AccessEventType.READ:
                metrics.read_count += 1
            elif event_type == AccessEventType.WRITE:
                metrics.write_count += 1

            # Record for pattern analysis
            self.recent_accesses.append(
                AccessEvent(
                    key=key,
                    event_type=event_type,
                    timestamp=current_time,
                    latency_ms=latency_ms,
                    value_size=value_size,
                )
            )

            # Update scores and classification
            self._update_key_score(key, metrics)

    def _update_key_score(self, key: str, metrics: KeyMetrics):
        """Update score and classification for a key."""
        # Calculate frequency score
        freq = self.frequency_counter.estimate(key)
        max_freq = (
            max(self.frequency_counter.estimate(k) for k in list(self.key_metrics.keys())[:100])
            if self.key_metrics
            else 1
        )
        metrics.frequency_score = freq / max_freq if max_freq > 0 else 0

        # Calculate recency score
        metrics.recency_score = self.recency_tracker.get_recency_score(key)

        # Calculate combined score
        metrics.combined_score = (
            self.config.frequency_weight * metrics.frequency_score + self.config.recency_weight * metrics.recency_score
        )

        # Determine hot level
        old_level = metrics.hot_level
        new_level = self._classify_hot_level(metrics)

        if new_level != old_level:
            self._update_hot_level(key, old_level, new_level)

    def _classify_hot_level(self, metrics: KeyMetrics) -> HotLevel:
        """Classify the hot level based on score."""
        if metrics.access_count < self.config.min_accesses:
            return HotLevel.COLD

        score = metrics.combined_score

        if score >= self.current_critical_threshold:
            return HotLevel.CRITICAL
        elif score >= self.current_hot_threshold:
            return HotLevel.HOT
        elif score >= self.current_hot_threshold * 0.6:
            return HotLevel.WARM
        elif score >= self.current_hot_threshold * 0.3:
            return HotLevel.COOL
        else:
            return HotLevel.COLD

    def _update_hot_level(self, key: str, old_level: HotLevel, new_level: HotLevel):
        """Update the hot level classification for a key."""
        # Remove from old level set
        self.hot_keys[old_level].discard(key)

        # Add to new level set
        self.hot_keys[new_level].add(key)

        # Update metrics
        if key in self.key_metrics:
            self.key_metrics[key].hot_level = new_level

        # Track promotions/demotions
        if new_level.value > old_level.value:
            self.keys_promoted += 1
        else:
            self.keys_demoted += 1

        # Notify callbacks
        for callback in self.hot_key_callbacks:
            try:
                callback(key, new_level)
            except Exception as e:
                logger.error(f"Hot key callback error: {e}")

    def _evict_cold_keys(self):
        """Evict cold keys to make room for new ones."""
        cold_keys = list(self.hot_keys[HotLevel.COLD])

        # Sort by score and remove lowest
        cold_keys_with_scores = [(k, self.key_metrics[k].combined_score) for k in cold_keys if k in self.key_metrics]
        cold_keys_with_scores.sort(key=lambda x: x[1])

        # Remove bottom 20%
        remove_count = max(1, len(cold_keys_with_scores) // 5)
        for key, _ in cold_keys_with_scores[:remove_count]:
            del self.key_metrics[key]
            self.hot_keys[HotLevel.COLD].discard(key)

    async def start_decay_loop(self):
        """Start the decay loop for aging out old access data."""
        if self._running:
            return

        self._running = True
        self._decay_task = asyncio.create_task(self._decay_loop())
        logger.info("Hot data tracker decay loop started")

    async def stop_decay_loop(self):
        """Stop the decay loop."""
        self._running = False
        if self._decay_task:
            self._decay_task.cancel()
            try:
                await self._decay_task
            except asyncio.CancelledError:
                pass
        logger.info("Hot data tracker decay loop stopped")

    async def _decay_loop(self):
        """Background loop for applying decay."""
        while self._running:
            try:
                await asyncio.sleep(self.config.decay_interval_seconds)
                self._apply_decay()
                self._adjust_thresholds()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Decay loop error: {e}")

    def _apply_decay(self):
        """Apply decay to frequency counts."""
        with self._lock:
            self.frequency_counter.decay(self.config.decay_factor)

            # Cleanup recency tracker
            self.recency_tracker.cleanup()

            # Re-evaluate all key scores
            for key, metrics in list(self.key_metrics.items()):
                self._update_key_score(key, metrics)

    def _adjust_thresholds(self):
        """Dynamically adjust hot thresholds based on distribution."""
        with self._lock:
            if len(self.key_metrics) < 100:
                return

            # Get score distribution
            scores = [m.combined_score for m in self.key_metrics.values()]
            scores.sort()

            # Set thresholds at percentiles
            p90 = scores[int(len(scores) * 0.9)]
            p99 = scores[int(len(scores) * 0.99)]

            old_hot = self.current_hot_threshold

            # Smooth threshold adjustment
            self.current_hot_threshold = 0.7 * self.current_hot_threshold + 0.3 * p90
            self.current_critical_threshold = 0.7 * self.current_critical_threshold + 0.3 * p99

            # Notify if changed significantly
            if abs(old_hot - self.current_hot_threshold) > 0.05:
                for callback in self.threshold_callbacks:
                    try:
                        callback(self.current_hot_threshold, self.current_critical_threshold)
                    except Exception as e:
                        logger.error(f"Threshold callback error: {e}")

    def get_hot_keys(self, level: HotLevel = HotLevel.HOT) -> List[str]:
        """Get all keys at or above the specified hot level."""
        with self._lock:
            result = []
            for lvl in HotLevel:
                if lvl.value >= level.value:
                    result.extend(self.hot_keys[lvl])
            return result

    def get_hot_keys_with_scores(
        self, min_level: HotLevel = HotLevel.WARM, limit: int = 100
    ) -> List[Tuple[str, float, HotLevel]]:
        """Get hot keys with their scores, sorted by score."""
        with self._lock:
            result = []
            for lvl in HotLevel:
                if lvl.value >= min_level.value:
                    for key in self.hot_keys[lvl]:
                        if key in self.key_metrics:
                            metrics = self.key_metrics[key]
                            result.append((key, metrics.combined_score, lvl))

            result.sort(key=lambda x: x[1], reverse=True)
            return result[:limit]

    def get_key_metrics(self, key: str) -> Optional[KeyMetrics]:
        """Get metrics for a specific key."""
        with self._lock:
            return self.key_metrics.get(key)

    def get_hot_level(self, key: str) -> HotLevel:
        """Get the hot level for a key."""
        with self._lock:
            metrics = self.key_metrics.get(key)
            return metrics.hot_level if metrics else HotLevel.COLD

    def is_hot(self, key: str) -> bool:
        """Check if a key is hot."""
        return self.get_hot_level(key).value >= HotLevel.HOT.value

    def register_hot_key_callback(self, callback: Callable[[str, HotLevel], None]):
        """Register a callback for hot key changes."""
        self.hot_key_callbacks.append(callback)

    def register_threshold_callback(self, callback: Callable[[float, float], None]):
        """Register a callback for threshold changes."""
        self.threshold_callbacks.append(callback)

    def get_stats(self) -> Dict[str, Any]:
        """Get tracking statistics."""
        with self._lock:
            level_counts = {level.name: len(keys) for level, keys in self.hot_keys.items()}

            return {
                "total_accesses": self.total_accesses,
                "tracked_keys": len(self.key_metrics),
                "max_tracked_keys": self.config.max_tracked_keys,
                "hot_threshold": self.current_hot_threshold,
                "critical_threshold": self.current_critical_threshold,
                "keys_by_level": level_counts,
                "keys_promoted": self.keys_promoted,
                "keys_demoted": self.keys_demoted,
            }

    def get_access_pattern_insights(self) -> Dict[str, Any]:
        """Get insights about access patterns."""
        with self._lock:
            if not self.recent_accesses:
                return {}

            # Analyze recent accesses
            accesses = list(self.recent_accesses)
            read_count = sum(1 for a in accesses if a.event_type == AccessEventType.READ)
            write_count = sum(1 for a in accesses if a.event_type == AccessEventType.WRITE)

            # Calculate inter-arrival times
            if len(accesses) >= 2:
                iats = [accesses[i].timestamp - accesses[i - 1].timestamp for i in range(1, len(accesses))]
                avg_iat = statistics.mean(iats)
                iat_std = statistics.stdev(iats) if len(iats) > 1 else 0
            else:
                avg_iat = iat_std = 0

            # Top accessed keys
            key_counts = defaultdict(int)
            for a in accesses:
                key_counts[a.key] += 1
            top_keys = sorted(key_counts.items(), key=lambda x: x[1], reverse=True)[:10]

            return {
                "read_write_ratio": read_count / (write_count + 1),
                "avg_inter_arrival_ms": avg_iat * 1000,
                "iat_coefficient_of_variation": iat_std / (avg_iat + 0.001),
                "unique_keys_accessed": len(key_counts),
                "top_accessed_keys": top_keys,
                "access_burstiness": "high" if iat_std / (avg_iat + 0.001) > 1.5 else "normal",
            }


class HotDataReplicator:
    """
    Manages replication of hot data to additional nodes
    for improved access performance.
    """

    def __init__(self, tracker: HotDataTracker, min_level: HotLevel = HotLevel.HOT):
        self.tracker = tracker
        self.min_level = min_level
        self.replicated_keys: Set[str] = set()
        self.replica_nodes: List[str] = []
        self.replication_callbacks: List[Callable[[str, List[str]], Any]] = []
        self._lock = threading.Lock()

        # Register for hot key changes
        self.tracker.register_hot_key_callback(self._on_hot_level_change)

    def add_replica_node(self, node_id: str):
        """Add a node for hot data replication."""
        with self._lock:
            if node_id not in self.replica_nodes:
                self.replica_nodes.append(node_id)

    def remove_replica_node(self, node_id: str):
        """Remove a replica node."""
        with self._lock:
            if node_id in self.replica_nodes:
                self.replica_nodes.remove(node_id)

    def _on_hot_level_change(self, key: str, new_level: HotLevel):
        """Handle hot level changes."""
        with self._lock:
            if new_level.value >= self.min_level.value:
                # Key became hot, replicate
                if key not in self.replicated_keys:
                    self._replicate_key(key)
            else:
                # Key became cold, remove replicas
                if key in self.replicated_keys:
                    self._remove_replicas(key)

    def _replicate_key(self, key: str):
        """Replicate a key to replica nodes."""
        self.replicated_keys.add(key)

        for callback in self.replication_callbacks:
            try:
                callback(key, self.replica_nodes)
            except Exception as e:
                logger.error(f"Replication callback error: {e}")

    def _remove_replicas(self, key: str):
        """Remove replicas of a key."""
        self.replicated_keys.discard(key)

    def register_replication_callback(self, callback: Callable[[str, List[str]], Any]):
        """Register a callback for replication events."""
        self.replication_callbacks.append(callback)

    def get_replicated_keys(self) -> Set[str]:
        """Get all currently replicated keys."""
        with self._lock:
            return self.replicated_keys.copy()
