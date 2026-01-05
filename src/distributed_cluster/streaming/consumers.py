"""
Event consumers for receiving events from the streaming system.
"""

import asyncio
import logging
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Union

from .events import Event

logger = logging.getLogger(__name__)


@dataclass
class ConsumerConfig:
    """Configuration for event consumers."""

    group_id: str = "default-group"
    auto_commit: bool = True
    auto_commit_interval_ms: int = 5000
    max_poll_records: int = 500
    poll_timeout_ms: int = 1000
    session_timeout_ms: int = 30000
    heartbeat_interval_ms: int = 3000
    max_poll_interval_ms: int = 300000
    enable_auto_offset_reset: str = "latest"  # earliest, latest, none
    isolation_level: str = "read_committed"
    fetch_min_bytes: int = 1
    fetch_max_bytes: int = 52428800  # 50MB
    max_partition_fetch_bytes: int = 1048576  # 1MB

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "auto_commit": self.auto_commit,
            "auto_commit_interval_ms": self.auto_commit_interval_ms,
            "max_poll_records": self.max_poll_records,
            "poll_timeout_ms": self.poll_timeout_ms,
            "session_timeout_ms": self.session_timeout_ms,
            "heartbeat_interval_ms": self.heartbeat_interval_ms,
            "max_poll_interval_ms": self.max_poll_interval_ms,
            "enable_auto_offset_reset": self.enable_auto_offset_reset,
            "isolation_level": self.isolation_level,
        }


class ConsumerMetrics:
    """Metrics tracking for consumers."""

    def __init__(self):
        self.events_received: int = 0
        self.events_processed: int = 0
        self.events_failed: int = 0
        self.bytes_received: int = 0
        self.commits: int = 0
        self.rebalances: int = 0
        self.avg_processing_time_ms: float = 0.0
        self._processing_times: List[float] = []
        self._lock = threading.Lock()

    def record_receive(self, event: Event, bytes_count: int):
        with self._lock:
            self.events_received += 1
            self.bytes_received += bytes_count

    def record_processed(self, processing_time_ms: float):
        with self._lock:
            self.events_processed += 1
            self._processing_times.append(processing_time_ms)
            if len(self._processing_times) > 1000:
                self._processing_times = self._processing_times[-1000:]
            self.avg_processing_time_ms = sum(self._processing_times) / len(self._processing_times)

    def record_failure(self):
        with self._lock:
            self.events_failed += 1

    def record_commit(self):
        with self._lock:
            self.commits += 1

    def record_rebalance(self):
        with self._lock:
            self.rebalances += 1

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "events_received": self.events_received,
                "events_processed": self.events_processed,
                "events_failed": self.events_failed,
                "bytes_received": self.bytes_received,
                "commits": self.commits,
                "rebalances": self.rebalances,
                "avg_processing_time_ms": self.avg_processing_time_ms,
            }


@dataclass
class Offset:
    """Represents a consumer offset."""

    topic: str
    partition: int
    offset: int
    timestamp: Optional[datetime] = None
    metadata: str = ""


class EventHandler(ABC):
    """Abstract base class for event handlers."""

    @abstractmethod
    def handle(self, event: Event) -> bool:
        """Handle an event. Returns True if successful."""
        pass

    def on_error(self, event: Event, error: Exception):
        """Called when event processing fails."""
        logger.error(f"Error processing event {event.event_id}: {error}")


class FunctionHandler(EventHandler):
    """Event handler that wraps a function."""

    def __init__(
        self, handler_fn: Callable[[Event], bool], error_fn: Optional[Callable[[Event, Exception], None]] = None
    ):
        self._handler_fn = handler_fn
        self._error_fn = error_fn

    def handle(self, event: Event) -> bool:
        return self._handler_fn(event)

    def on_error(self, event: Event, error: Exception):
        if self._error_fn:
            self._error_fn(event, error)
        else:
            super().on_error(event, error)


class EventConsumer(ABC):
    """Abstract base class for event consumers."""

    def __init__(self, config: Optional[ConsumerConfig] = None):
        self.config = config or ConsumerConfig()
        self.metrics = ConsumerMetrics()
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._subscriptions: Set[str] = set()
        self._started = False
        self._paused = False

    def subscribe(self, topics: Union[str, List[str]], handler: EventHandler) -> None:
        """Subscribe to one or more topics with a handler."""
        if isinstance(topics, str):
            topics = [topics]

        for topic in topics:
            if topic not in self._handlers:
                self._handlers[topic] = []
            self._handlers[topic].append(handler)
            self._subscriptions.add(topic)

    def unsubscribe(self, topics: Optional[Union[str, List[str]]] = None) -> None:
        """Unsubscribe from topics."""
        if topics is None:
            self._handlers.clear()
            self._subscriptions.clear()
        else:
            if isinstance(topics, str):
                topics = [topics]
            for topic in topics:
                self._handlers.pop(topic, None)
                self._subscriptions.discard(topic)

    @abstractmethod
    def poll(self, timeout_ms: Optional[int] = None) -> List[Event]:
        """Poll for new events."""
        pass

    @abstractmethod
    def commit(self, offsets: Optional[List[Offset]] = None) -> None:
        """Commit offsets."""
        pass

    @abstractmethod
    def seek(self, offset: Offset) -> None:
        """Seek to a specific offset."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the consumer."""
        pass

    def pause(self) -> None:
        """Pause consumption."""
        self._paused = True

    def resume(self) -> None:
        """Resume consumption."""
        self._paused = False

    def _dispatch_event(self, topic: str, event: Event) -> bool:
        """Dispatch event to registered handlers."""
        handlers = self._handlers.get(topic, [])
        all_success = True

        for handler in handlers:
            start_time = time.time()
            try:
                success = handler.handle(event)
                processing_time = (time.time() - start_time) * 1000
                if success:
                    self.metrics.record_processed(processing_time)
                else:
                    self.metrics.record_failure()
                    all_success = False
            except Exception as e:
                self.metrics.record_failure()
                handler.on_error(event, e)
                all_success = False

        return all_success


class SyncEventConsumer(EventConsumer):
    """Synchronous event consumer implementation."""

    def __init__(
        self,
        broker_poll_fn: Callable[[List[str], int], List[tuple]],
        broker_commit_fn: Callable[[List[Offset]], None],
        config: Optional[ConsumerConfig] = None,
    ):
        super().__init__(config)
        self._broker_poll = broker_poll_fn
        self._broker_commit = broker_commit_fn
        self._current_offsets: Dict[str, Dict[int, int]] = {}
        self._started = True

    def poll(self, timeout_ms: Optional[int] = None) -> List[Event]:
        if not self._started or self._paused:
            return []

        timeout = timeout_ms or self.config.poll_timeout_ms
        topics = list(self._subscriptions)

        if not topics:
            return []

        try:
            raw_events = self._broker_poll(topics, timeout)
            events = []

            for topic, partition, offset, event_data in raw_events:
                event = Event.from_dict(event_data) if isinstance(event_data, dict) else event_data
                self.metrics.record_receive(event, len(str(event_data)))

                # Track offset
                if topic not in self._current_offsets:
                    self._current_offsets[topic] = {}
                self._current_offsets[topic][partition] = offset

                # Dispatch to handlers
                self._dispatch_event(topic, event)
                events.append(event)

            return events
        except Exception as e:
            logger.error(f"Poll error: {e}")
            return []

    def commit(self, offsets: Optional[List[Offset]] = None) -> None:
        if offsets is None:
            # Commit all current offsets
            offsets = []
            for topic, partitions in self._current_offsets.items():
                for partition, offset in partitions.items():
                    offsets.append(Offset(topic, partition, offset))

        if offsets:
            self._broker_commit(offsets)
            self.metrics.record_commit()

    def seek(self, offset: Offset) -> None:
        if offset.topic not in self._current_offsets:
            self._current_offsets[offset.topic] = {}
        self._current_offsets[offset.topic][offset.partition] = offset.offset

    def close(self) -> None:
        if self.config.auto_commit:
            self.commit()
        self._started = False


class AsyncEventConsumer(EventConsumer):
    """Asynchronous event consumer using asyncio."""

    def __init__(
        self,
        broker_poll_fn: Callable[[List[str], int], List[tuple]],
        broker_commit_fn: Callable[[List[Offset]], None],
        config: Optional[ConsumerConfig] = None,
    ):
        super().__init__(config)
        self._broker_poll = broker_poll_fn
        self._broker_commit = broker_commit_fn
        self._current_offsets: Dict[str, Dict[int, int]] = {}
        self._consume_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self):
        """Start the async consumer."""
        self._loop = asyncio.get_event_loop()
        self._started = True
        self._consume_task = asyncio.create_task(self._consume_loop())

    async def _consume_loop(self):
        """Background task to consume events."""
        while self._started:
            if self._paused:
                await asyncio.sleep(0.1)
                continue

            try:
                events = await self.poll_async(self.config.poll_timeout_ms)
                if not events:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consume loop error: {e}")
                await asyncio.sleep(1)

    async def poll_async(self, timeout_ms: Optional[int] = None) -> List[Event]:
        """Async poll for events."""
        if not self._started or self._paused:
            return []

        timeout = timeout_ms or self.config.poll_timeout_ms
        topics = list(self._subscriptions)

        if not topics:
            return []

        try:
            # Run in executor to avoid blocking
            raw_events = await self._loop.run_in_executor(None, self._broker_poll, topics, timeout)
            events = []

            for topic, partition, offset, event_data in raw_events:
                event = Event.from_dict(event_data) if isinstance(event_data, dict) else event_data
                self.metrics.record_receive(event, len(str(event_data)))

                if topic not in self._current_offsets:
                    self._current_offsets[topic] = {}
                self._current_offsets[topic][partition] = offset

                self._dispatch_event(topic, event)
                events.append(event)

            # Auto commit if enabled
            if self.config.auto_commit and events:
                await self.commit_async()

            return events
        except Exception as e:
            logger.error(f"Async poll error: {e}")
            return []

    def poll(self, timeout_ms: Optional[int] = None) -> List[Event]:
        """Synchronous poll wrapper."""
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.poll_async(timeout_ms), self._loop)
            return future.result()
        return []

    async def commit_async(self, offsets: Optional[List[Offset]] = None) -> None:
        """Async commit offsets."""
        if offsets is None:
            offsets = []
            for topic, partitions in self._current_offsets.items():
                for partition, offset in partitions.items():
                    offsets.append(Offset(topic, partition, offset))

        if offsets:
            await self._loop.run_in_executor(None, self._broker_commit, offsets)
            self.metrics.record_commit()

    def commit(self, offsets: Optional[List[Offset]] = None) -> None:
        """Synchronous commit wrapper."""
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.commit_async(offsets), self._loop)
            future.result()

    def seek(self, offset: Offset) -> None:
        if offset.topic not in self._current_offsets:
            self._current_offsets[offset.topic] = {}
        self._current_offsets[offset.topic][offset.partition] = offset.offset

    async def close_async(self) -> None:
        """Async close."""
        self._started = False
        if self._consume_task:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass

        if self.config.auto_commit:
            await self.commit_async()

    def close(self) -> None:
        """Synchronous close."""
        self._started = False


class ConsumerGroup:
    """Manages a group of consumers for parallel processing."""

    def __init__(self, group_id: str, consumer_factory: Callable[[], EventConsumer], num_consumers: int = 4):
        self.group_id = group_id
        self._consumer_factory = consumer_factory
        self._num_consumers = num_consumers
        self._consumers: List[EventConsumer] = []
        self._executor = ThreadPoolExecutor(max_workers=num_consumers)
        self._started = False
        self._stop_event = threading.Event()

    def start(self):
        """Start all consumers in the group."""
        self._started = True
        self._stop_event.clear()

        for i in range(self._num_consumers):
            consumer = self._consumer_factory()
            self._consumers.append(consumer)
            self._executor.submit(self._consumer_loop, consumer, i)

    def _consumer_loop(self, consumer: EventConsumer, consumer_id: int):
        """Consumer thread loop."""
        logger.info(f"Consumer {consumer_id} started in group {self.group_id}")

        while not self._stop_event.is_set():
            try:
                events = consumer.poll()
                if not events:
                    time.sleep(0.01)
            except Exception as e:
                logger.error(f"Consumer {consumer_id} error: {e}")
                time.sleep(1)

        consumer.close()
        logger.info(f"Consumer {consumer_id} stopped in group {self.group_id}")

    def subscribe(self, topics: Union[str, List[str]], handler: EventHandler):
        """Subscribe all consumers to topics."""
        for consumer in self._consumers:
            consumer.subscribe(topics, handler)

    def stop(self):
        """Stop all consumers in the group."""
        self._stop_event.set()
        self._started = False

        for consumer in self._consumers:
            consumer.close()

        self._executor.shutdown(wait=True)
        self._consumers.clear()

    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics from all consumers."""
        aggregated = {
            "events_received": 0,
            "events_processed": 0,
            "events_failed": 0,
            "bytes_received": 0,
        }

        for consumer in self._consumers:
            metrics = consumer.metrics.to_dict()
            for key in aggregated:
                aggregated[key] += metrics.get(key, 0)

        aggregated["num_consumers"] = len(self._consumers)
        aggregated["group_id"] = self.group_id

        return aggregated


class FilteringConsumer(EventConsumer):
    """Consumer that filters events before processing."""

    def __init__(self, base_consumer: EventConsumer, filter_fn: Callable[[Event], bool]):
        super().__init__(base_consumer.config)
        self._base_consumer = base_consumer
        self._filter_fn = filter_fn

    def subscribe(self, topics: Union[str, List[str]], handler: EventHandler) -> None:
        self._base_consumer.subscribe(topics, handler)

    def unsubscribe(self, topics: Optional[Union[str, List[str]]] = None) -> None:
        self._base_consumer.unsubscribe(topics)

    def poll(self, timeout_ms: Optional[int] = None) -> List[Event]:
        events = self._base_consumer.poll(timeout_ms)
        return [e for e in events if self._filter_fn(e)]

    def commit(self, offsets: Optional[List[Offset]] = None) -> None:
        self._base_consumer.commit(offsets)

    def seek(self, offset: Offset) -> None:
        self._base_consumer.seek(offset)

    def close(self) -> None:
        self._base_consumer.close()


class RetryingConsumer(EventConsumer):
    """Consumer with automatic retry for failed events."""

    def __init__(
        self,
        base_consumer: EventConsumer,
        max_retries: int = 3,
        retry_delay_ms: int = 1000,
        dead_letter_handler: Optional[Callable[[Event, Exception], None]] = None,
    ):
        super().__init__(base_consumer.config)
        self._base_consumer = base_consumer
        self._max_retries = max_retries
        self._retry_delay_ms = retry_delay_ms
        self._dead_letter_handler = dead_letter_handler
        self._retry_counts: Dict[str, int] = {}

    def subscribe(self, topics: Union[str, List[str]], handler: EventHandler) -> None:
        # Wrap handler with retry logic
        retry_handler = RetryHandler(handler, self._max_retries, self._retry_delay_ms, self._dead_letter_handler)
        self._base_consumer.subscribe(topics, retry_handler)

    def unsubscribe(self, topics: Optional[Union[str, List[str]]] = None) -> None:
        self._base_consumer.unsubscribe(topics)

    def poll(self, timeout_ms: Optional[int] = None) -> List[Event]:
        return self._base_consumer.poll(timeout_ms)

    def commit(self, offsets: Optional[List[Offset]] = None) -> None:
        self._base_consumer.commit(offsets)

    def seek(self, offset: Offset) -> None:
        self._base_consumer.seek(offset)

    def close(self) -> None:
        self._base_consumer.close()


class RetryHandler(EventHandler):
    """Handler that retries on failure."""

    def __init__(
        self,
        base_handler: EventHandler,
        max_retries: int,
        retry_delay_ms: int,
        dead_letter_handler: Optional[Callable[[Event, Exception], None]],
    ):
        self._base_handler = base_handler
        self._max_retries = max_retries
        self._retry_delay_ms = retry_delay_ms
        self._dead_letter_handler = dead_letter_handler

    def handle(self, event: Event) -> bool:
        retries = 0
        last_error = None

        while retries <= self._max_retries:
            try:
                return self._base_handler.handle(event)
            except Exception as e:
                last_error = e
                retries += 1
                if retries <= self._max_retries:
                    time.sleep(self._retry_delay_ms * retries / 1000)

        # Send to dead letter queue
        if self._dead_letter_handler and last_error:
            self._dead_letter_handler(event, last_error)

        return False

    def on_error(self, event: Event, error: Exception):
        self._base_handler.on_error(event, error)
