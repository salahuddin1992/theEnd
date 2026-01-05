"""
Event producers for publishing events to the streaming system.
"""

import asyncio
import logging
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Queue
from typing import Any, Callable, Dict, List, Optional

from .events import Event, EventMetadata, EventPriority, EventType

logger = logging.getLogger(__name__)


@dataclass
class ProducerConfig:
    """Configuration for event producers."""

    batch_size: int = 100
    batch_timeout_ms: int = 1000
    max_retries: int = 3
    retry_backoff_ms: int = 100
    buffer_size: int = 10000
    compression: str = "none"  # none, gzip, snappy, lz4
    acks: str = "all"  # none, leader, all
    idempotent: bool = True
    max_in_flight: int = 5
    linger_ms: int = 5
    enable_metrics: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_size": self.batch_size,
            "batch_timeout_ms": self.batch_timeout_ms,
            "max_retries": self.max_retries,
            "retry_backoff_ms": self.retry_backoff_ms,
            "buffer_size": self.buffer_size,
            "compression": self.compression,
            "acks": self.acks,
            "idempotent": self.idempotent,
            "max_in_flight": self.max_in_flight,
            "linger_ms": self.linger_ms,
            "enable_metrics": self.enable_metrics,
        }


class ProducerMetrics:
    """Metrics tracking for producers."""

    def __init__(self):
        self.events_sent: int = 0
        self.events_failed: int = 0
        self.bytes_sent: int = 0
        self.batches_sent: int = 0
        self.retries: int = 0
        self.avg_latency_ms: float = 0.0
        self._latencies: List[float] = []
        self._lock = threading.Lock()

    def record_send(self, event: Event, latency_ms: float, bytes_count: int):
        with self._lock:
            self.events_sent += 1
            self.bytes_sent += bytes_count
            self._latencies.append(latency_ms)
            if len(self._latencies) > 1000:
                self._latencies = self._latencies[-1000:]
            self.avg_latency_ms = sum(self._latencies) / len(self._latencies)

    def record_failure(self):
        with self._lock:
            self.events_failed += 1

    def record_retry(self):
        with self._lock:
            self.retries += 1

    def record_batch(self, size: int):
        with self._lock:
            self.batches_sent += 1

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "events_sent": self.events_sent,
                "events_failed": self.events_failed,
                "bytes_sent": self.bytes_sent,
                "batches_sent": self.batches_sent,
                "retries": self.retries,
                "avg_latency_ms": self.avg_latency_ms,
            }


class EventProducer(ABC):
    """Abstract base class for event producers."""

    def __init__(self, config: Optional[ProducerConfig] = None):
        self.config = config or ProducerConfig()
        self.metrics = ProducerMetrics()
        self._callbacks: List[Callable[[Event, Optional[Exception]], None]] = []
        self._started = False

    @abstractmethod
    def send(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        """Send an event to a topic."""
        pass

    @abstractmethod
    def flush(self, timeout_ms: Optional[int] = None) -> None:
        """Flush pending events."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the producer."""
        pass

    def on_delivery(self, callback: Callable[[Event, Optional[Exception]], None]) -> None:
        """Register a delivery callback."""
        self._callbacks.append(callback)

    def _notify_callbacks(self, event: Event, error: Optional[Exception] = None):
        for callback in self._callbacks:
            try:
                callback(event, error)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def send_event(
        self,
        topic: str,
        event_type: EventType,
        payload: Dict[str, Any],
        source: str,
        priority: EventPriority = EventPriority.NORMAL,
        key: Optional[str] = None,
        **metadata_kwargs,
    ) -> bool:
        """Convenience method to create and send an event."""
        metadata = EventMetadata(source=source, **metadata_kwargs)
        event = Event(
            event_type=event_type,
            priority=priority,
            payload=payload,
            metadata=metadata,
        )
        return self.send(topic, event, key)


class SyncEventProducer(EventProducer):
    """Synchronous event producer implementation."""

    def __init__(
        self, broker_send_fn: Callable[[str, Event, Optional[str]], bool], config: Optional[ProducerConfig] = None
    ):
        super().__init__(config)
        self._broker_send = broker_send_fn
        self._buffer: Queue = Queue(maxsize=self.config.buffer_size)
        self._started = True

    def send(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        if not self._started:
            raise RuntimeError("Producer not started")

        start_time = time.time()
        retries = 0
        last_error = None

        while retries <= self.config.max_retries:
            try:
                success = self._broker_send(topic, event, key)
                if success:
                    latency_ms = (time.time() - start_time) * 1000
                    self.metrics.record_send(event, latency_ms, len(event.to_json()))
                    self._notify_callbacks(event, None)
                    return True
            except Exception as e:
                last_error = e
                retries += 1
                self.metrics.record_retry()
                if retries <= self.config.max_retries:
                    time.sleep(self.config.retry_backoff_ms * retries / 1000)

        self.metrics.record_failure()
        self._notify_callbacks(event, last_error)
        logger.error(f"Failed to send event after {retries} retries: {last_error}")
        return False

    def flush(self, timeout_ms: Optional[int] = None) -> None:
        # Synchronous producer sends immediately, nothing to flush
        pass

    def close(self) -> None:
        self._started = False


class AsyncEventProducer(EventProducer):
    """Asynchronous event producer using asyncio."""

    def __init__(
        self, broker_send_fn: Callable[[str, Event, Optional[str]], bool], config: Optional[ProducerConfig] = None
    ):
        super().__init__(config)
        self._broker_send = broker_send_fn
        self._buffer: asyncio.Queue = None
        self._send_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self):
        """Start the async producer."""
        self._loop = asyncio.get_event_loop()
        self._buffer = asyncio.Queue(maxsize=self.config.buffer_size)
        self._started = True
        self._send_task = asyncio.create_task(self._send_loop())

    async def _send_loop(self):
        """Background task to send events."""
        while self._started:
            try:
                topic, event, key = await asyncio.wait_for(self._buffer.get(), timeout=0.1)
                await self._send_with_retry(topic, event, key)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in send loop: {e}")

    async def _send_with_retry(self, topic: str, event: Event, key: Optional[str]) -> bool:
        start_time = time.time()
        retries = 0
        last_error = None

        while retries <= self.config.max_retries:
            try:
                # Run in executor to avoid blocking
                success = await self._loop.run_in_executor(None, self._broker_send, topic, event, key)
                if success:
                    latency_ms = (time.time() - start_time) * 1000
                    self.metrics.record_send(event, latency_ms, len(event.to_json()))
                    self._notify_callbacks(event, None)
                    return True
            except Exception as e:
                last_error = e
                retries += 1
                self.metrics.record_retry()
                if retries <= self.config.max_retries:
                    await asyncio.sleep(self.config.retry_backoff_ms * retries / 1000)

        self.metrics.record_failure()
        self._notify_callbacks(event, last_error)
        return False

    def send(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        """Queue event for async sending."""
        if not self._started:
            raise RuntimeError("Producer not started")

        try:
            self._buffer.put_nowait((topic, event, key))
            return True
        except asyncio.QueueFull:
            logger.warning("Producer buffer full, dropping event")
            self.metrics.record_failure()
            return False

    async def send_async(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        """Async send with await."""
        if not self._started:
            raise RuntimeError("Producer not started")

        await self._buffer.put((topic, event, key))
        return True

    async def flush(self, timeout_ms: Optional[int] = None) -> None:
        """Wait for all pending events to be sent."""
        timeout = timeout_ms / 1000 if timeout_ms else None
        try:
            await asyncio.wait_for(self._wait_empty(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Flush timeout reached")

    async def _wait_empty(self):
        while not self._buffer.empty():
            await asyncio.sleep(0.01)

    async def close(self) -> None:
        """Close the async producer."""
        self._started = False
        if self._send_task:
            self._send_task.cancel()
            try:
                await self._send_task
            except asyncio.CancelledError:
                pass

    def close_sync(self) -> None:
        """Synchronous close."""
        self._started = False


class BatchEventProducer(EventProducer):
    """Batch event producer for high-throughput scenarios."""

    def __init__(
        self, broker_send_batch_fn: Callable[[str, List[Event]], bool], config: Optional[ProducerConfig] = None
    ):
        super().__init__(config)
        self._broker_send_batch = broker_send_batch_fn
        self._buffers: Dict[str, List[tuple]] = {}  # topic -> [(event, key), ...]
        self._buffer_lock = threading.Lock()
        self._flush_thread: Optional[threading.Thread] = None
        self._started = False
        self._executor = ThreadPoolExecutor(max_workers=4)

    def start(self):
        """Start the batch producer."""
        self._started = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def _flush_loop(self):
        """Background thread to flush batches."""
        while self._started:
            time.sleep(self.config.batch_timeout_ms / 1000)
            self._flush_all()

    def _flush_all(self):
        """Flush all topic buffers."""
        with self._buffer_lock:
            topics = list(self._buffers.keys())

        for topic in topics:
            self._flush_topic(topic)

    def _flush_topic(self, topic: str):
        """Flush a specific topic buffer."""
        with self._buffer_lock:
            if topic not in self._buffers or not self._buffers[topic]:
                return

            batch = self._buffers[topic][: self.config.batch_size]
            self._buffers[topic] = self._buffers[topic][self.config.batch_size :]

        if batch:
            events = [e for e, _ in batch]
            try:
                success = self._broker_send_batch(topic, events)
                if success:
                    self.metrics.record_batch(len(events))
                    for event in events:
                        self.metrics.record_send(event, 0, len(event.to_json()))
                        self._notify_callbacks(event, None)
                else:
                    for event in events:
                        self.metrics.record_failure()
            except Exception as e:
                logger.error(f"Batch send error: {e}")
                for event in events:
                    self.metrics.record_failure()
                    self._notify_callbacks(event, e)

    def send(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        if not self._started:
            raise RuntimeError("Producer not started")

        with self._buffer_lock:
            if topic not in self._buffers:
                self._buffers[topic] = []

            if len(self._buffers[topic]) >= self.config.buffer_size:
                logger.warning(f"Buffer full for topic {topic}")
                self.metrics.record_failure()
                return False

            self._buffers[topic].append((event, key))

            # Flush if batch size reached
            if len(self._buffers[topic]) >= self.config.batch_size:
                self._executor.submit(self._flush_topic, topic)

        return True

    def flush(self, timeout_ms: Optional[int] = None) -> None:
        """Flush all pending batches."""
        self._flush_all()

    def close(self) -> None:
        """Close the batch producer."""
        self._started = False
        self.flush()
        if self._flush_thread:
            self._flush_thread.join(timeout=5)
        self._executor.shutdown(wait=True)


class PartitionedProducer(EventProducer):
    """Producer that partitions events across multiple topics/partitions."""

    def __init__(
        self,
        base_producer: EventProducer,
        partition_fn: Optional[Callable[[Event], int]] = None,
        num_partitions: int = 8,
    ):
        super().__init__(base_producer.config)
        self._base_producer = base_producer
        self._partition_fn = partition_fn or self._default_partition
        self._num_partitions = num_partitions

    def _default_partition(self, event: Event) -> int:
        """Default partitioning based on event ID."""
        return hash(event.event_id) % self._num_partitions

    def send(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        partition = self._partition_fn(event)
        partitioned_topic = f"{topic}-{partition}"
        return self._base_producer.send(partitioned_topic, event, key)

    def flush(self, timeout_ms: Optional[int] = None) -> None:
        self._base_producer.flush(timeout_ms)

    def close(self) -> None:
        self._base_producer.close()


class TransactionalProducer(EventProducer):
    """Producer with transaction support."""

    def __init__(self, base_producer: EventProducer, transaction_id: str):
        super().__init__(base_producer.config)
        self._base_producer = base_producer
        self._transaction_id = transaction_id
        self._in_transaction = False
        self._pending_events: List[tuple] = []

    def begin_transaction(self):
        """Begin a new transaction."""
        if self._in_transaction:
            raise RuntimeError("Transaction already in progress")
        self._in_transaction = True
        self._pending_events = []

    def send(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        if not self._in_transaction:
            return self._base_producer.send(topic, event, key)

        self._pending_events.append((topic, event, key))
        return True

    def commit_transaction(self) -> bool:
        """Commit the current transaction."""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")

        try:
            for topic, event, key in self._pending_events:
                if not self._base_producer.send(topic, event, key):
                    self.abort_transaction()
                    return False

            self._base_producer.flush()
            self._in_transaction = False
            self._pending_events = []
            return True
        except Exception as e:
            logger.error(f"Transaction commit failed: {e}")
            self.abort_transaction()
            return False

    def abort_transaction(self):
        """Abort the current transaction."""
        self._in_transaction = False
        self._pending_events = []

    def flush(self, timeout_ms: Optional[int] = None) -> None:
        self._base_producer.flush(timeout_ms)

    def close(self) -> None:
        if self._in_transaction:
            self.abort_transaction()
        self._base_producer.close()
