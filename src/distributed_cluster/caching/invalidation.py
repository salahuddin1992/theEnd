"""
Cache invalidation strategies and patterns.
"""

import logging
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Empty, Queue
from typing import Any, Callable, Dict, List, Optional, Set

from .cache import Cache

logger = logging.getLogger(__name__)


class InvalidationType(Enum):
    """Types of cache invalidation."""
    KEY = "key"  # Single key invalidation
    PATTERN = "pattern"  # Pattern-based invalidation
    TAG = "tag"  # Tag-based invalidation
    ALL = "all"  # Full cache clear
    TTL = "ttl"  # Time-based expiration


@dataclass
class InvalidationEvent:
    """Represents a cache invalidation event."""
    event_id: str
    invalidation_type: InvalidationType
    key: Optional[str] = None
    pattern: Optional[str] = None
    tags: Optional[List[str]] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "invalidation_type": self.invalidation_type.value,
            "key": self.key,
            "pattern": self.pattern,
            "tags": self.tags,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "metadata": self.metadata,
        }


class InvalidationStrategy(ABC):
    """Abstract base class for cache invalidation strategies."""

    def __init__(self, cache: Cache):
        self.cache = cache
        self._listeners: List[Callable[[InvalidationEvent], None]] = []

    @abstractmethod
    def on_read(self, key: str, value: Any) -> Any:
        """Called when a value is read from cache."""
        pass

    @abstractmethod
    def on_write(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Called when a value is written to cache."""
        pass

    @abstractmethod
    def on_delete(self, key: str) -> bool:
        """Called when a value is deleted from cache."""
        pass

    def add_listener(self, listener: Callable[[InvalidationEvent], None]):
        """Add an invalidation event listener."""
        self._listeners.append(listener)

    def _notify_listeners(self, event: InvalidationEvent):
        """Notify all listeners of an invalidation event."""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error in invalidation listener: {e}")


class TTLInvalidation(InvalidationStrategy):
    """Time-to-live based cache invalidation."""

    def __init__(
        self,
        cache: Cache,
        default_ttl: int = 3600,
        jitter_percent: float = 0.1
    ):
        super().__init__(cache)
        self.default_ttl = default_ttl
        self.jitter_percent = jitter_percent

    def _get_ttl_with_jitter(self, ttl: int) -> int:
        """Add jitter to TTL to prevent thundering herd."""
        import random
        jitter = int(ttl * self.jitter_percent)
        return ttl + random.randint(-jitter, jitter)

    def on_read(self, key: str, value: Any) -> Any:
        return value

    def on_write(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        actual_ttl = self._get_ttl_with_jitter(ttl or self.default_ttl)
        return self.cache.set(key, value, actual_ttl)

    def on_delete(self, key: str) -> bool:
        return self.cache.delete(key)


class WriteThrough(InvalidationStrategy):
    """
    Write-through cache invalidation.

    Writes go to both cache and backing store synchronously.
    """

    def __init__(
        self,
        cache: Cache,
        write_fn: Callable[[str, Any], bool],
        read_fn: Callable[[str], Any],
        delete_fn: Optional[Callable[[str], bool]] = None
    ):
        super().__init__(cache)
        self.write_fn = write_fn
        self.read_fn = read_fn
        self.delete_fn = delete_fn

    def on_read(self, key: str, value: Any) -> Any:
        if value is not None:
            return value

        # Cache miss - read from backing store
        backing_value = self.read_fn(key)
        if backing_value is not None:
            self.cache.set(key, backing_value)
        return backing_value

    def on_write(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        # Write to backing store first
        if not self.write_fn(key, value):
            return False

        # Then update cache
        return self.cache.set(key, value, ttl)

    def on_delete(self, key: str) -> bool:
        # Delete from backing store first
        if self.delete_fn:
            if not self.delete_fn(key):
                return False

        # Then delete from cache
        return self.cache.delete(key)


class WriteBehind(InvalidationStrategy):
    """
    Write-behind (write-back) cache invalidation.

    Writes go to cache immediately and are asynchronously written to backing store.
    """

    def __init__(
        self,
        cache: Cache,
        write_fn: Callable[[str, Any], bool],
        read_fn: Callable[[str], Any],
        delete_fn: Optional[Callable[[str], bool]] = None,
        batch_size: int = 100,
        flush_interval_ms: int = 1000,
        max_retries: int = 3
    ):
        super().__init__(cache)
        self.write_fn = write_fn
        self.read_fn = read_fn
        self.delete_fn = delete_fn
        self.batch_size = batch_size
        self.flush_interval_ms = flush_interval_ms
        self.max_retries = max_retries

        self._write_queue: Queue = Queue()
        self._delete_queue: Queue = Queue()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._running = True
        self._start_flush_threads()

    def _start_flush_threads(self):
        """Start background threads for flushing writes."""
        def flush_writes():
            while self._running:
                batch = []
                try:
                    # Collect batch
                    while len(batch) < self.batch_size:
                        try:
                            item = self._write_queue.get(timeout=self.flush_interval_ms / 1000)
                            batch.append(item)
                        except Empty:
                            break

                    # Flush batch
                    for key, value, retries in batch:
                        try:
                            if not self.write_fn(key, value):
                                if retries < self.max_retries:
                                    self._write_queue.put((key, value, retries + 1))
                        except Exception as e:
                            logger.error(f"Write-behind error for {key}: {e}")
                            if retries < self.max_retries:
                                self._write_queue.put((key, value, retries + 1))
                except Exception as e:
                    logger.error(f"Write flush error: {e}")

        def flush_deletes():
            while self._running:
                batch = []
                try:
                    while len(batch) < self.batch_size:
                        try:
                            item = self._delete_queue.get(timeout=self.flush_interval_ms / 1000)
                            batch.append(item)
                        except Empty:
                            break

                    for key, retries in batch:
                        try:
                            if self.delete_fn and not self.delete_fn(key):
                                if retries < self.max_retries:
                                    self._delete_queue.put((key, retries + 1))
                        except Exception as e:
                            logger.error(f"Delete-behind error for {key}: {e}")
                except Exception as e:
                    logger.error(f"Delete flush error: {e}")

        self._executor.submit(flush_writes)
        self._executor.submit(flush_deletes)

    def on_read(self, key: str, value: Any) -> Any:
        if value is not None:
            return value

        # Cache miss - read from backing store
        backing_value = self.read_fn(key)
        if backing_value is not None:
            self.cache.set(key, backing_value)
        return backing_value

    def on_write(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        # Write to cache immediately
        if not self.cache.set(key, value, ttl):
            return False

        # Queue for async write to backing store
        self._write_queue.put((key, value, 0))
        return True

    def on_delete(self, key: str) -> bool:
        # Delete from cache immediately
        if not self.cache.delete(key):
            return False

        # Queue for async delete from backing store
        if self.delete_fn:
            self._delete_queue.put((key, 0))

        return True

    def flush(self, timeout: float = 10.0):
        """Flush all pending writes."""
        start = time.time()
        while time.time() - start < timeout:
            if self._write_queue.empty() and self._delete_queue.empty():
                return
            time.sleep(0.1)

    def shutdown(self):
        """Shutdown the write-behind threads."""
        self._running = False
        self.flush()
        self._executor.shutdown(wait=True)


class CacheAside(InvalidationStrategy):
    """
    Cache-aside (lazy-loading) pattern.

    Application is responsible for cache population.
    """

    def __init__(
        self,
        cache: Cache,
        load_fn: Callable[[str], Any],
        save_fn: Optional[Callable[[str, Any], bool]] = None,
        delete_fn: Optional[Callable[[str], bool]] = None,
        default_ttl: int = 3600
    ):
        super().__init__(cache)
        self.load_fn = load_fn
        self.save_fn = save_fn
        self.delete_fn = delete_fn
        self.default_ttl = default_ttl

    def on_read(self, key: str, value: Any) -> Any:
        if value is not None:
            return value

        # Cache miss - load from source
        loaded_value = self.load_fn(key)
        if loaded_value is not None:
            self.cache.set(key, loaded_value, self.default_ttl)
        return loaded_value

    def on_write(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        # Invalidate cache first
        self.cache.delete(key)

        # Save to backing store
        if self.save_fn:
            return self.save_fn(key, value)
        return True

    def on_delete(self, key: str) -> bool:
        # Invalidate cache
        self.cache.delete(key)

        # Delete from backing store
        if self.delete_fn:
            return self.delete_fn(key)
        return True


class RefreshAhead(InvalidationStrategy):
    """
    Refresh-ahead cache invalidation.

    Proactively refreshes cache entries before they expire.
    """

    def __init__(
        self,
        cache: Cache,
        load_fn: Callable[[str], Any],
        default_ttl: int = 3600,
        refresh_threshold: float = 0.75  # Refresh at 75% of TTL
    ):
        super().__init__(cache)
        self.load_fn = load_fn
        self.default_ttl = default_ttl
        self.refresh_threshold = refresh_threshold

        self._refresh_times: Dict[str, float] = {}
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._lock = threading.Lock()

    def _should_refresh(self, key: str) -> bool:
        """Check if a key should be refreshed."""
        with self._lock:
            set_time = self._refresh_times.get(key)
            if set_time is None:
                return False

            elapsed = time.time() - set_time
            threshold = self.default_ttl * self.refresh_threshold
            return elapsed >= threshold

    def _async_refresh(self, key: str):
        """Asynchronously refresh a cache entry."""
        try:
            value = self.load_fn(key)
            if value is not None:
                self.cache.set(key, value, self.default_ttl)
                with self._lock:
                    self._refresh_times[key] = time.time()
        except Exception as e:
            logger.error(f"Refresh-ahead error for {key}: {e}")

    def on_read(self, key: str, value: Any) -> Any:
        if value is not None:
            # Check if we should refresh
            if self._should_refresh(key):
                self._executor.submit(self._async_refresh, key)
            return value

        # Cache miss - load from source
        loaded_value = self.load_fn(key)
        if loaded_value is not None:
            self.cache.set(key, loaded_value, self.default_ttl)
            with self._lock:
                self._refresh_times[key] = time.time()

        return loaded_value

    def on_write(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        result = self.cache.set(key, value, ttl or self.default_ttl)
        if result:
            with self._lock:
                self._refresh_times[key] = time.time()
        return result

    def on_delete(self, key: str) -> bool:
        with self._lock:
            self._refresh_times.pop(key, None)
        return self.cache.delete(key)


class TagBasedInvalidation:
    """
    Tag-based cache invalidation.

    Associates cache entries with tags and invalidates all entries with a tag.
    """

    def __init__(self, cache: Cache):
        self.cache = cache
        self._key_tags: Dict[str, Set[str]] = {}
        self._tag_keys: Dict[str, Set[str]] = {}
        self._lock = threading.RLock()

    def set(
        self,
        key: str,
        value: Any,
        tags: List[str],
        ttl: Optional[int] = None
    ) -> bool:
        """Set a value with associated tags."""
        result = self.cache.set(key, value, ttl)

        if result:
            with self._lock:
                # Store key -> tags mapping
                self._key_tags[key] = set(tags)

                # Store tag -> keys mapping
                for tag in tags:
                    if tag not in self._tag_keys:
                        self._tag_keys[tag] = set()
                    self._tag_keys[tag].add(key)

        return result

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value."""
        return self.cache.get(key, default)

    def invalidate_by_tag(self, tag: str) -> int:
        """Invalidate all entries with a tag."""
        with self._lock:
            keys = self._tag_keys.pop(tag, set())
            count = 0

            for key in keys:
                if self.cache.delete(key):
                    count += 1

                # Clean up key -> tags mapping
                if key in self._key_tags:
                    self._key_tags[key].discard(tag)
                    if not self._key_tags[key]:
                        del self._key_tags[key]

            return count

    def invalidate_by_tags(self, tags: List[str]) -> int:
        """Invalidate all entries with any of the given tags."""
        count = 0
        for tag in tags:
            count += self.invalidate_by_tag(tag)
        return count

    def get_tags(self, key: str) -> Set[str]:
        """Get tags for a key."""
        with self._lock:
            return self._key_tags.get(key, set()).copy()

    def get_keys_by_tag(self, tag: str) -> Set[str]:
        """Get all keys with a tag."""
        with self._lock:
            return self._tag_keys.get(tag, set()).copy()


class InvalidationBus:
    """
    Distributed invalidation bus for multi-instance cache coordination.
    """

    def __init__(self, cache: Cache, publish_fn: Callable[[Dict], None]):
        self.cache = cache
        self.publish_fn = publish_fn
        self._handlers: Dict[InvalidationType, List[Callable]] = {}

    def publish(self, event: InvalidationEvent):
        """Publish an invalidation event."""
        self.publish_fn(event.to_dict())

    def handle(self, event_data: Dict):
        """Handle an incoming invalidation event."""
        try:
            event = InvalidationEvent(
                event_id=event_data["event_id"],
                invalidation_type=InvalidationType(event_data["invalidation_type"]),
                key=event_data.get("key"),
                pattern=event_data.get("pattern"),
                tags=event_data.get("tags"),
                timestamp=datetime.fromisoformat(event_data["timestamp"]),
                source=event_data.get("source", "unknown"),
                metadata=event_data.get("metadata", {}),
            )

            if event.invalidation_type == InvalidationType.KEY:
                self.cache.delete(event.key)
            elif event.invalidation_type == InvalidationType.PATTERN:
                keys = self.cache.keys(event.pattern)
                self.cache.delete_many(keys)
            elif event.invalidation_type == InvalidationType.ALL:
                self.cache.clear()

            # Notify handlers
            handlers = self._handlers.get(event.invalidation_type, [])
            for handler in handlers:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Handler error: {e}")

        except Exception as e:
            logger.error(f"Error handling invalidation event: {e}")

    def on(self, event_type: InvalidationType, handler: Callable):
        """Register a handler for an invalidation type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
