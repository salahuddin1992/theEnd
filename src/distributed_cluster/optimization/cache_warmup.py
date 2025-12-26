"""
Cache Warmup - Proactive cache population strategies.

This module provides intelligent cache warming strategies that pre-populate
the cache with frequently accessed data based on historical patterns,
predictive models, and scheduled refresh policies.
"""

import asyncio
import time
import threading
import logging
import hashlib
import heapq
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set, Tuple, Awaitable
from enum import Enum
from collections import deque, defaultdict
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class WarmupStrategy(Enum):
    """Cache warmup strategies."""
    EAGER = "eager"               # Load all data at startup
    LAZY = "lazy"                 # Load on first access
    PREDICTIVE = "predictive"     # Load based on access patterns
    SCHEDULED = "scheduled"       # Load at scheduled times
    TIERED = "tiered"             # Priority-based loading
    ADAPTIVE = "adaptive"         # Dynamically adjust strategy


class WarmupPriority(Enum):
    """Priority levels for cache warmup."""
    CRITICAL = 4    # Must be in cache before service starts
    HIGH = 3        # Should be warmed first
    MEDIUM = 2      # Standard priority
    LOW = 1         # Warm when resources available
    BACKGROUND = 0  # Warm in background only


@dataclass
class WarmupItem:
    """Represents an item to be warmed in the cache."""
    key: str
    loader: Callable[[], Awaitable[Any]]
    priority: WarmupPriority = WarmupPriority.MEDIUM
    ttl_seconds: Optional[int] = None
    dependencies: List[str] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    estimated_load_time_ms: float = 100.0
    estimated_size_bytes: int = 1024

    def __lt__(self, other):
        """Compare by priority for heap operations."""
        return self.priority.value > other.priority.value


@dataclass
class WarmupResult:
    """Result of a warmup operation."""
    key: str
    success: bool
    load_time_ms: float
    size_bytes: int
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WarmupStats:
    """Statistics for warmup operations."""
    total_items: int = 0
    warmed_items: int = 0
    failed_items: int = 0
    total_load_time_ms: float = 0.0
    total_size_bytes: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.warmed_items + self.failed_items
        return self.warmed_items / total if total > 0 else 0.0

    @property
    def duration_seconds(self) -> float:
        """Calculate total duration."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class WarmupDataSource(ABC):
    """Abstract base class for warmup data sources."""

    @abstractmethod
    async def get_keys_to_warm(self) -> List[WarmupItem]:
        """Get list of keys that should be warmed."""
        pass

    @abstractmethod
    async def load_value(self, key: str) -> Any:
        """Load the value for a key."""
        pass


class StaticWarmupSource(WarmupDataSource):
    """Static warmup source with predefined keys."""

    def __init__(self, items: List[WarmupItem]):
        self.items = items

    async def get_keys_to_warm(self) -> List[WarmupItem]:
        return self.items

    async def load_value(self, key: str) -> Any:
        for item in self.items:
            if item.key == key:
                return await item.loader()
        raise KeyError(f"Key not found: {key}")


class HistoricalWarmupSource(WarmupDataSource):
    """Warmup source based on historical access patterns."""

    def __init__(
        self,
        access_history: Dict[str, List[datetime]],
        loader: Callable[[str], Awaitable[Any]],
        min_access_count: int = 5,
        lookback_hours: int = 24
    ):
        self.access_history = access_history
        self.loader = loader
        self.min_access_count = min_access_count
        self.lookback_hours = lookback_hours

    async def get_keys_to_warm(self) -> List[WarmupItem]:
        items = []
        cutoff = datetime.now() - timedelta(hours=self.lookback_hours)

        for key, accesses in self.access_history.items():
            recent_accesses = [a for a in accesses if a > cutoff]
            if len(recent_accesses) >= self.min_access_count:
                priority = self._calculate_priority(len(recent_accesses))
                items.append(WarmupItem(
                    key=key,
                    loader=lambda k=key: self.loader(k),
                    priority=priority,
                    access_count=len(recent_accesses),
                    last_accessed=max(recent_accesses) if recent_accesses else None,
                ))

        return items

    def _calculate_priority(self, access_count: int) -> WarmupPriority:
        """Calculate priority based on access count."""
        if access_count >= 100:
            return WarmupPriority.CRITICAL
        elif access_count >= 50:
            return WarmupPriority.HIGH
        elif access_count >= 20:
            return WarmupPriority.MEDIUM
        else:
            return WarmupPriority.LOW

    async def load_value(self, key: str) -> Any:
        return await self.loader(key)


class AccessPatternPredictor:
    """Predicts which keys will be accessed based on patterns."""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.access_sequences: deque = deque(maxlen=window_size)
        self.co_access_counts: Dict[Tuple[str, str], int] = defaultdict(int)
        self.temporal_patterns: Dict[str, List[int]] = defaultdict(list)
        self._lock = threading.Lock()

    def record_access(self, key: str):
        """Record a key access for pattern learning."""
        current_time = time.time()
        hour = datetime.fromtimestamp(current_time).hour

        with self._lock:
            # Record temporal pattern
            self.temporal_patterns[key].append(hour)
            if len(self.temporal_patterns[key]) > 100:
                self.temporal_patterns[key] = self.temporal_patterns[key][-100:]

            # Record co-access patterns
            if self.access_sequences:
                last_keys = list(self.access_sequences)[-5:]
                for prev_key in last_keys:
                    if prev_key != key:
                        self.co_access_counts[(prev_key, key)] += 1

            self.access_sequences.append(key)

    def predict_next_accesses(self, current_key: str, count: int = 10) -> List[str]:
        """Predict which keys are likely to be accessed next."""
        predictions = []

        with self._lock:
            # Find keys commonly accessed after current_key
            candidates = []
            for (prev, next_key), co_count in self.co_access_counts.items():
                if prev == current_key:
                    candidates.append((next_key, co_count))

            # Sort by co-access count
            candidates.sort(key=lambda x: x[1], reverse=True)
            predictions = [k for k, _ in candidates[:count]]

        return predictions

    def predict_by_time(self, hour: Optional[int] = None, count: int = 10) -> List[str]:
        """Predict which keys are likely to be accessed at a given hour."""
        if hour is None:
            hour = datetime.now().hour

        with self._lock:
            # Count accesses per key at this hour
            hour_counts: Dict[str, int] = defaultdict(int)
            for key, hours in self.temporal_patterns.items():
                for h in hours:
                    if h == hour:
                        hour_counts[key] += 1

            # Sort by count
            sorted_keys = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
            return [k for k, _ in sorted_keys[:count]]


class CacheWarmer:
    """
    Coordinates cache warming operations with support for multiple
    strategies and data sources.
    """

    def __init__(
        self,
        cache_set: Callable[[str, Any, Optional[int]], Awaitable[bool]],
        strategy: WarmupStrategy = WarmupStrategy.ADAPTIVE,
        max_concurrent: int = 10,
        batch_size: int = 100,
        timeout_seconds: float = 60.0
    ):
        self.cache_set = cache_set
        self.strategy = strategy
        self.max_concurrent = max_concurrent
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds

        # Data sources
        self.sources: List[WarmupDataSource] = []
        self.predictor = AccessPatternPredictor()

        # State tracking
        self.pending_items: List[WarmupItem] = []
        self.warmed_keys: Set[str] = set()
        self.failed_keys: Dict[str, str] = {}
        self.warmup_results: deque = deque(maxlen=1000)
        self.current_stats = WarmupStats()

        # Scheduling
        self.scheduled_warmups: List[Tuple[datetime, List[WarmupItem]]] = []

        # Control
        self._running = False
        self._warmup_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        self._semaphore: Optional[asyncio.Semaphore] = None

    def add_source(self, source: WarmupDataSource):
        """Add a warmup data source."""
        self.sources.append(source)

    def add_static_items(self, items: List[WarmupItem]):
        """Add static items to warm."""
        self.sources.append(StaticWarmupSource(items))

    def schedule_warmup(self, when: datetime, items: List[WarmupItem]):
        """Schedule a warmup for a specific time."""
        self.scheduled_warmups.append((when, items))
        self.scheduled_warmups.sort(key=lambda x: x[0])

    async def warm_all(self) -> WarmupStats:
        """Warm all items from all sources."""
        self.current_stats = WarmupStats()
        self.current_stats.start_time = datetime.now()

        # Collect all items from sources
        all_items = []
        for source in self.sources:
            try:
                items = await source.get_keys_to_warm()
                all_items.extend(items)
            except Exception as e:
                logger.error(f"Error getting warmup items from source: {e}")

        self.current_stats.total_items = len(all_items)

        if not all_items:
            self.current_stats.end_time = datetime.now()
            return self.current_stats

        # Execute warmup based on strategy
        if self.strategy == WarmupStrategy.EAGER:
            await self._eager_warmup(all_items)
        elif self.strategy == WarmupStrategy.TIERED:
            await self._tiered_warmup(all_items)
        elif self.strategy == WarmupStrategy.PREDICTIVE:
            await self._predictive_warmup(all_items)
        else:  # ADAPTIVE or others
            await self._adaptive_warmup(all_items)

        self.current_stats.end_time = datetime.now()
        return self.current_stats

    async def _eager_warmup(self, items: List[WarmupItem]):
        """Warm all items as fast as possible."""
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [self._warm_item(item) for item in items]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _tiered_warmup(self, items: List[WarmupItem]):
        """Warm items by priority tier."""
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

        # Group by priority
        priority_groups: Dict[WarmupPriority, List[WarmupItem]] = defaultdict(list)
        for item in items:
            priority_groups[item.priority].append(item)

        # Warm in priority order
        for priority in sorted(WarmupPriority, key=lambda p: p.value, reverse=True):
            group = priority_groups.get(priority, [])
            if group:
                logger.info(f"Warming {len(group)} items with priority {priority.name}")
                tasks = [self._warm_item(item) for item in group]
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _predictive_warmup(self, items: List[WarmupItem]):
        """Warm items based on predicted access patterns."""
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

        # Get predicted keys for current hour
        predicted_keys = set(self.predictor.predict_by_time(count=100))

        # Prioritize predicted keys
        predicted_items = []
        other_items = []

        for item in items:
            if item.key in predicted_keys:
                predicted_items.append(item)
            else:
                other_items.append(item)

        # Warm predicted items first
        if predicted_items:
            logger.info(f"Warming {len(predicted_items)} predicted items first")
            tasks = [self._warm_item(item) for item in predicted_items]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Then warm others
        if other_items:
            tasks = [self._warm_item(item) for item in other_items]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _adaptive_warmup(self, items: List[WarmupItem]):
        """Adaptively warm items based on available resources."""
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

        # Sort by priority and access count
        sorted_items = sorted(
            items,
            key=lambda x: (x.priority.value, x.access_count),
            reverse=True
        )

        # Warm in batches with adaptive concurrency
        for i in range(0, len(sorted_items), self.batch_size):
            batch = sorted_items[i:i + self.batch_size]
            tasks = [self._warm_item(item) for item in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Brief pause between batches to avoid overwhelming the system
            await asyncio.sleep(0.1)

    async def _warm_item(self, item: WarmupItem) -> WarmupResult:
        """Warm a single cache item."""
        async with self._semaphore:
            start_time = time.time()
            result = WarmupResult(
                key=item.key,
                success=False,
                load_time_ms=0.0,
                size_bytes=0,
            )

            try:
                # Check dependencies
                for dep_key in item.dependencies:
                    if dep_key not in self.warmed_keys:
                        result.error = f"Dependency not warmed: {dep_key}"
                        self.failed_keys[item.key] = result.error
                        self.current_stats.failed_items += 1
                        return result

                # Load the value with timeout
                try:
                    value = await asyncio.wait_for(
                        item.loader(),
                        timeout=self.timeout_seconds
                    )
                except asyncio.TimeoutError:
                    result.error = "Load timeout"
                    self.failed_keys[item.key] = result.error
                    self.current_stats.failed_items += 1
                    return result

                # Set in cache
                await self.cache_set(item.key, value, item.ttl_seconds)

                # Calculate metrics
                load_time_ms = (time.time() - start_time) * 1000
                size_bytes = len(str(value)) if value else 0

                result.success = True
                result.load_time_ms = load_time_ms
                result.size_bytes = size_bytes

                with self._lock:
                    self.warmed_keys.add(item.key)
                    self.current_stats.warmed_items += 1
                    self.current_stats.total_load_time_ms += load_time_ms
                    self.current_stats.total_size_bytes += size_bytes

                self.warmup_results.append(result)
                return result

            except Exception as e:
                result.error = str(e)
                result.load_time_ms = (time.time() - start_time) * 1000
                self.failed_keys[item.key] = result.error
                self.current_stats.failed_items += 1
                logger.error(f"Failed to warm key {item.key}: {e}")
                return result

    async def warm_key(self, key: str, loader: Callable[[], Awaitable[Any]], ttl: Optional[int] = None) -> bool:
        """Warm a single key on demand."""
        item = WarmupItem(key=key, loader=loader, ttl_seconds=ttl)
        result = await self._warm_item(item)
        return result.success

    async def warm_predictive(self, current_key: str, count: int = 5):
        """Warm keys predicted to be accessed after current_key."""
        predicted = self.predictor.predict_next_accesses(current_key, count)

        for key in predicted:
            if key not in self.warmed_keys:
                # Find matching source and loader
                for source in self.sources:
                    try:
                        items = await source.get_keys_to_warm()
                        for item in items:
                            if item.key == key:
                                asyncio.create_task(self._warm_item(item))
                                break
                    except Exception:
                        pass

    def record_access(self, key: str):
        """Record a key access for prediction learning."""
        self.predictor.record_access(key)

    async def start_background_warming(self, interval_seconds: float = 300.0):
        """Start background warming loop."""
        if self._running:
            return

        self._running = True
        self._warmup_task = asyncio.create_task(
            self._background_loop(interval_seconds)
        )
        logger.info("Started background cache warming")

    async def stop_background_warming(self):
        """Stop background warming."""
        self._running = False
        if self._warmup_task:
            self._warmup_task.cancel()
            try:
                await self._warmup_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped background cache warming")

    async def _background_loop(self, interval_seconds: float):
        """Background warming loop."""
        while self._running:
            try:
                # Check scheduled warmups
                now = datetime.now()
                due_warmups = [
                    (when, items) for when, items in self.scheduled_warmups
                    if when <= now
                ]

                for when, items in due_warmups:
                    logger.info(f"Executing scheduled warmup with {len(items)} items")
                    self._semaphore = asyncio.Semaphore(self.max_concurrent)
                    tasks = [self._warm_item(item) for item in items]
                    await asyncio.gather(*tasks, return_exceptions=True)
                    self.scheduled_warmups.remove((when, items))

                # Periodic refresh of frequently accessed items
                await self._refresh_hot_items()

                await asyncio.sleep(interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Background warming error: {e}")

    async def _refresh_hot_items(self):
        """Refresh frequently accessed items."""
        predicted = self.predictor.predict_by_time(count=20)

        for key in predicted:
            # Find and refresh
            for source in self.sources:
                try:
                    items = await source.get_keys_to_warm()
                    for item in items:
                        if item.key == key:
                            asyncio.create_task(self._warm_item(item))
                            break
                except Exception:
                    pass

    def get_stats(self) -> Dict[str, Any]:
        """Get warmup statistics."""
        return {
            'strategy': self.strategy.value,
            'total_items': self.current_stats.total_items,
            'warmed_items': self.current_stats.warmed_items,
            'failed_items': self.current_stats.failed_items,
            'success_rate': self.current_stats.success_rate,
            'total_load_time_ms': self.current_stats.total_load_time_ms,
            'total_size_bytes': self.current_stats.total_size_bytes,
            'duration_seconds': self.current_stats.duration_seconds,
            'warmed_keys_count': len(self.warmed_keys),
            'pending_scheduled': len(self.scheduled_warmups),
            'recent_results': [
                {
                    'key': r.key,
                    'success': r.success,
                    'load_time_ms': r.load_time_ms,
                    'error': r.error,
                }
                for r in list(self.warmup_results)[-20:]
            ],
        }


class IncrementalWarmer:
    """
    Incremental cache warmer that gradually warms the cache
    to avoid overwhelming the system.
    """

    def __init__(
        self,
        cache_set: Callable[[str, Any, Optional[int]], Awaitable[bool]],
        items_per_second: float = 10.0,
        max_memory_mb: int = 1024
    ):
        self.cache_set = cache_set
        self.items_per_second = items_per_second
        self.max_memory_mb = max_memory_mb

        self.pending_items: deque = deque()
        self.current_memory_bytes = 0
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def add_items(self, items: List[WarmupItem]):
        """Add items to the warming queue."""
        for item in items:
            self.pending_items.append(item)

    async def start(self):
        """Start incremental warming."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._warming_loop())

    async def stop(self):
        """Stop incremental warming."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _warming_loop(self):
        """Incremental warming loop."""
        interval = 1.0 / self.items_per_second

        while self._running:
            try:
                if not self.pending_items:
                    await asyncio.sleep(1.0)
                    continue

                # Check memory limit
                if self.current_memory_bytes >= self.max_memory_mb * 1024 * 1024:
                    logger.warning("Memory limit reached, pausing warmup")
                    await asyncio.sleep(10.0)
                    continue

                # Warm next item
                item = self.pending_items.popleft()
                try:
                    value = await item.loader()
                    await self.cache_set(item.key, value, item.ttl_seconds)
                    self.current_memory_bytes += item.estimated_size_bytes
                except Exception as e:
                    logger.error(f"Failed to warm {item.key}: {e}")

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Incremental warming error: {e}")


class CacheRefresher:
    """
    Manages cache refresh to keep data fresh without full invalidation.
    """

    def __init__(
        self,
        cache_get: Callable[[str], Awaitable[Any]],
        cache_set: Callable[[str, Any, Optional[int]], Awaitable[bool]],
        refresh_threshold: float = 0.8  # Refresh when 80% of TTL elapsed
    ):
        self.cache_get = cache_get
        self.cache_set = cache_set
        self.refresh_threshold = refresh_threshold

        # Track items for refresh
        self.tracked_items: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def track(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl_seconds: int
    ):
        """Track a key for automatic refresh."""
        with self._lock:
            self.tracked_items[key] = {
                'loader': loader,
                'ttl_seconds': ttl_seconds,
                'last_refresh': time.time(),
            }

    def untrack(self, key: str):
        """Stop tracking a key."""
        with self._lock:
            self.tracked_items.pop(key, None)

    async def start(self, check_interval: float = 10.0):
        """Start refresh monitoring."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._refresh_loop(check_interval))

    async def stop(self):
        """Stop refresh monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _refresh_loop(self, check_interval: float):
        """Check and refresh items as needed."""
        while self._running:
            try:
                await asyncio.sleep(check_interval)

                current_time = time.time()
                items_to_refresh = []

                with self._lock:
                    for key, info in self.tracked_items.items():
                        elapsed = current_time - info['last_refresh']
                        threshold = info['ttl_seconds'] * self.refresh_threshold

                        if elapsed >= threshold:
                            items_to_refresh.append((key, info))

                # Refresh items
                for key, info in items_to_refresh:
                    try:
                        value = await info['loader']()
                        await self.cache_set(key, value, info['ttl_seconds'])

                        with self._lock:
                            if key in self.tracked_items:
                                self.tracked_items[key]['last_refresh'] = current_time

                        logger.debug(f"Refreshed cache key: {key}")

                    except Exception as e:
                        logger.error(f"Failed to refresh {key}: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Refresh loop error: {e}")
