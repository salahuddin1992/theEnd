# -*- coding: utf-8 -*-
"""
Real-Time Metrics Streaming - بث المقاييس في الوقت الفعلي
=========================================================

WebSocket-based real-time metrics streaming:
- Live cluster metrics broadcasting
- Subscription-based metric filtering
- Efficient delta encoding
- Automatic reconnection support
- Metric aggregation and downsampling

بث مقاييس WebSocket في الوقت الفعلي:
- بث مقاييس العنقود الحية
- تصفية المقاييس القائمة على الاشتراك
- ترميز دلتا فعال
- دعم إعادة الاتصال التلقائي
- تجميع المقاييس وتقليل العينات
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Types of metrics."""

    GAUGE = "gauge"
    COUNTER = "counter"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class StreamFormat(str, Enum):
    """Stream data formats."""

    FULL = "full"  # Full metric data
    DELTA = "delta"  # Only changed values
    COMPACT = "compact"  # Minimal format


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metric_type: MetricType = MetricType.GAUGE
    labels: Dict[str, str] = field(default_factory=dict)
    unit: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "type": self.metric_type.value,
            "labels": self.labels,
            "unit": self.unit,
        }

    def to_compact(self) -> List[Any]:
        """Compact format: [name, value, timestamp_ms, labels_hash]"""
        ts_ms = int(self.timestamp.timestamp() * 1000)
        labels_hash = (
            hashlib.md5(json.dumps(self.labels, sort_keys=True).encode()).hexdigest()[:8] if self.labels else ""
        )
        return [self.name, self.value, ts_ms, labels_hash]


@dataclass
class MetricSubscription:
    """Subscription to specific metrics."""

    subscription_id: str
    client_id: str
    patterns: List[str]  # Metric name patterns (supports wildcards)
    labels_filter: Dict[str, str] = field(default_factory=dict)
    format: StreamFormat = StreamFormat.FULL
    interval_ms: int = 1000  # Minimum interval between updates
    created_at: datetime = field(default_factory=datetime.utcnow)

    def matches(self, metric: MetricPoint) -> bool:
        """Check if metric matches subscription criteria."""
        # Check name pattern
        name_match = False
        for pattern in self.patterns:
            if pattern == "*":
                name_match = True
                break
            elif pattern.endswith("*"):
                if metric.name.startswith(pattern[:-1]):
                    name_match = True
                    break
            elif metric.name == pattern:
                name_match = True
                break

        if not name_match:
            return False

        # Check labels filter
        for key, value in self.labels_filter.items():
            if metric.labels.get(key) != value:
                return False

        return True


@dataclass
class StreamClient:
    """Connected streaming client."""

    client_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    subscriptions: Dict[str, MetricSubscription] = field(default_factory=dict)
    message_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    last_sent: Dict[str, float] = field(default_factory=dict)  # metric_name -> last value
    messages_sent: int = 0
    messages_dropped: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "connected_at": self.connected_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "subscription_count": len(self.subscriptions),
            "messages_sent": self.messages_sent,
            "messages_dropped": self.messages_dropped,
            "queue_size": self.message_queue.qsize(),
        }


@dataclass
class StreamStats:
    """Statistics for the metrics stream."""

    total_clients: int = 0
    active_subscriptions: int = 0
    metrics_published: int = 0
    messages_sent: int = 0
    messages_dropped: int = 0
    bytes_sent: int = 0
    uptime_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_clients": self.total_clients,
            "active_subscriptions": self.active_subscriptions,
            "metrics_published": self.metrics_published,
            "messages_sent": self.messages_sent,
            "messages_dropped": self.messages_dropped,
            "bytes_sent": self.bytes_sent,
            "uptime_seconds": round(self.uptime_seconds, 2),
        }


class MetricsStreamManager:
    """
    Real-time metrics streaming manager.

    Manages WebSocket connections and streams metrics to subscribed clients.

    Features:
    - Subscription-based filtering
    - Delta encoding for efficient updates
    - Rate limiting per client
    - Automatic aggregation for high-frequency metrics

    Usage:
        stream_manager = MetricsStreamManager()

        # Client connects and subscribes
        client_id = await stream_manager.connect_client()
        await stream_manager.subscribe(client_id, ["cpu.*", "memory.*"])

        # Publish metrics
        await stream_manager.publish(MetricPoint(
            name="cpu.usage",
            value=45.2,
            labels={"worker_id": "worker-1"},
        ))

        # Client receives metrics via message queue
        message = await stream_manager.get_next_message(client_id)
    """

    def __init__(
        self,
        max_clients: int = 1000,
        default_interval_ms: int = 1000,
        buffer_size: int = 100,
        enable_aggregation: bool = True,
        aggregation_window_ms: int = 1000,
    ):
        """
        Initialize the metrics stream manager.

        Args:
            max_clients: Maximum concurrent clients
            default_interval_ms: Default update interval per client
            buffer_size: Size of metric buffer for aggregation
            enable_aggregation: Whether to aggregate high-frequency metrics
            aggregation_window_ms: Window for metric aggregation
        """
        self.max_clients = max_clients
        self.default_interval_ms = default_interval_ms
        self.buffer_size = buffer_size
        self.enable_aggregation = enable_aggregation
        self.aggregation_window_ms = aggregation_window_ms

        # Clients and subscriptions
        self._clients: Dict[str, StreamClient] = {}
        self._client_counter = 0
        self._subscription_counter = 0

        # Metrics buffer for aggregation
        self._metric_buffer: Dict[str, List[MetricPoint]] = defaultdict(list)
        self._last_flush = time.monotonic()

        # Stats
        self._stats = StreamStats()
        self._start_time = time.monotonic()

        # Locks
        self._lock = asyncio.Lock()

        # Background task for aggregation
        self._aggregation_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the stream manager."""
        if self.enable_aggregation:
            self._aggregation_task = asyncio.create_task(self._aggregation_loop())
        logger.info("Metrics stream manager started")

    async def stop(self) -> None:
        """Stop the stream manager."""
        if self._aggregation_task:
            self._aggregation_task.cancel()
            try:
                await self._aggregation_task
            except asyncio.CancelledError:
                pass

        # Disconnect all clients
        for client_id in list(self._clients.keys()):
            await self.disconnect_client(client_id)

        logger.info("Metrics stream manager stopped")

    async def connect_client(self, client_id: Optional[str] = None) -> str:
        """
        Register a new streaming client.

        Args:
            client_id: Optional client ID (auto-generated if not provided)

        Returns:
            Client ID
        """
        async with self._lock:
            if len(self._clients) >= self.max_clients:
                raise ConnectionError("Maximum clients reached")

            if client_id is None:
                self._client_counter += 1
                client_id = f"client-{self._client_counter:06d}"

            self._clients[client_id] = StreamClient(client_id=client_id)
            self._stats.total_clients = len(self._clients)

            logger.debug(f"Client connected: {client_id}")
            return client_id

    async def disconnect_client(self, client_id: str) -> None:
        """Disconnect a client."""
        async with self._lock:
            if client_id in self._clients:
                client = self._clients.pop(client_id)
                self._stats.active_subscriptions -= len(client.subscriptions)
                self._stats.total_clients = len(self._clients)
                logger.debug(f"Client disconnected: {client_id}")

    async def subscribe(
        self,
        client_id: str,
        patterns: List[str],
        labels_filter: Optional[Dict[str, str]] = None,
        format: StreamFormat = StreamFormat.FULL,
        interval_ms: Optional[int] = None,
    ) -> str:
        """
        Subscribe a client to metrics.

        Args:
            client_id: Client ID
            patterns: List of metric name patterns (e.g., ["cpu.*", "memory.usage"])
            labels_filter: Filter by labels
            format: Output format
            interval_ms: Minimum update interval

        Returns:
            Subscription ID
        """
        async with self._lock:
            if client_id not in self._clients:
                raise ValueError(f"Unknown client: {client_id}")

            client = self._clients[client_id]

            self._subscription_counter += 1
            subscription_id = f"sub-{self._subscription_counter:06d}"

            subscription = MetricSubscription(
                subscription_id=subscription_id,
                client_id=client_id,
                patterns=patterns,
                labels_filter=labels_filter or {},
                format=format,
                interval_ms=interval_ms or self.default_interval_ms,
            )

            client.subscriptions[subscription_id] = subscription
            self._stats.active_subscriptions += 1

            logger.debug(f"Subscription created: {subscription_id} for {client_id}")
            return subscription_id

    async def unsubscribe(self, client_id: str, subscription_id: str) -> bool:
        """Unsubscribe from metrics."""
        async with self._lock:
            if client_id not in self._clients:
                return False

            client = self._clients[client_id]
            if subscription_id in client.subscriptions:
                del client.subscriptions[subscription_id]
                self._stats.active_subscriptions -= 1
                return True

            return False

    async def publish(self, metric: MetricPoint) -> None:
        """
        Publish a metric to all subscribed clients.

        Args:
            metric: Metric data point
        """
        self._stats.metrics_published += 1

        if self.enable_aggregation:
            # Buffer for aggregation
            key = f"{metric.name}:{json.dumps(metric.labels, sort_keys=True)}"
            self._metric_buffer[key].append(metric)

            # Trim buffer
            if len(self._metric_buffer[key]) > self.buffer_size:
                self._metric_buffer[key] = self._metric_buffer[key][-self.buffer_size :]
        else:
            # Direct publish
            await self._distribute_metric(metric)

    async def publish_batch(self, metrics: List[MetricPoint]) -> None:
        """Publish multiple metrics at once."""
        for metric in metrics:
            await self.publish(metric)

    async def _distribute_metric(self, metric: MetricPoint) -> None:
        """Distribute a metric to subscribed clients."""
        for client in self._clients.values():
            for subscription in client.subscriptions.values():
                if not subscription.matches(metric):
                    continue

                # Check rate limiting
                rate_limit_key = f"{subscription.subscription_id}:{metric.name}"
                now_ms = int(time.time() * 1000)
                last_sent_ms = client.last_sent.get(rate_limit_key, 0)

                if now_ms - last_sent_ms < subscription.interval_ms:
                    continue

                # Format message
                message = self._format_message(metric, subscription.format, client)

                # Queue message
                try:
                    client.message_queue.put_nowait(message)
                    client.last_sent[rate_limit_key] = now_ms
                    client.messages_sent += 1
                    self._stats.messages_sent += 1
                except asyncio.QueueFull:
                    client.messages_dropped += 1
                    self._stats.messages_dropped += 1

    def _format_message(
        self,
        metric: MetricPoint,
        format: StreamFormat,
        client: StreamClient,
    ) -> Dict[str, Any]:
        """Format metric message based on subscription format."""
        if format == StreamFormat.COMPACT:
            return {
                "type": "metric",
                "data": metric.to_compact(),
            }
        elif format == StreamFormat.DELTA:
            # Include only changed values
            last_value = client.last_sent.get(metric.name)
            if last_value is not None and last_value == metric.value:
                return None  # No change

            return {
                "type": "metric",
                "name": metric.name,
                "value": metric.value,
                "delta": metric.value - last_value if last_value else None,
                "timestamp": metric.timestamp.isoformat(),
            }
        else:  # FULL
            return {
                "type": "metric",
                "data": metric.to_dict(),
            }

    async def _aggregation_loop(self) -> None:
        """Background task for metric aggregation."""
        while True:
            try:
                await asyncio.sleep(self.aggregation_window_ms / 1000)
                await self._flush_aggregated_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Aggregation error: {e}")

    async def _flush_aggregated_metrics(self) -> None:
        """Flush aggregated metrics to clients."""
        now = time.monotonic()
        elapsed_ms = (now - self._last_flush) * 1000

        if elapsed_ms < self.aggregation_window_ms:
            return

        self._last_flush = now

        for key, points in list(self._metric_buffer.items()):
            if not points:
                continue

            # Aggregate: use last value for gauges, sum for counters
            last_point = points[-1]

            if last_point.metric_type == MetricType.COUNTER:
                # Sum all values in the window
                aggregated_value = sum(p.value for p in points)
            else:
                # Use last value for gauges
                aggregated_value = last_point.value

            aggregated = MetricPoint(
                name=last_point.name,
                value=aggregated_value,
                timestamp=datetime.now(timezone.utc),
                metric_type=last_point.metric_type,
                labels=last_point.labels,
                unit=last_point.unit,
            )

            await self._distribute_metric(aggregated)

            # Clear buffer
            self._metric_buffer[key] = []

    async def get_next_message(
        self,
        client_id: str,
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the next message for a client.

        Args:
            client_id: Client ID
            timeout: Timeout in seconds

        Returns:
            Message dict or None on timeout
        """
        if client_id not in self._clients:
            raise ValueError(f"Unknown client: {client_id}")

        client = self._clients[client_id]
        client.last_activity = datetime.now(timezone.utc)

        try:
            if timeout:
                message = await asyncio.wait_for(
                    client.message_queue.get(),
                    timeout=timeout,
                )
            else:
                message = await client.message_queue.get()

            if message:
                self._stats.bytes_sent += len(json.dumps(message))

            return message
        except asyncio.TimeoutError:
            return None

    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a client."""
        if client_id not in self._clients:
            return None
        return self._clients[client_id].to_dict()

    def get_all_clients(self) -> List[Dict[str, Any]]:
        """Get information about all clients."""
        return [client.to_dict() for client in self._clients.values()]

    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics."""
        self._stats.uptime_seconds = time.monotonic() - self._start_time
        return self._stats.to_dict()


# =============================================================================
# Metric Collectors
# =============================================================================


class SystemMetricsCollector:
    """
    Collects system metrics and publishes to stream.

    Usage:
        collector = SystemMetricsCollector(stream_manager)
        await collector.start()
    """

    def __init__(
        self,
        stream_manager: MetricsStreamManager,
        interval_seconds: float = 1.0,
        collect_cpu: bool = True,
        collect_memory: bool = True,
        collect_disk: bool = True,
        collect_network: bool = True,
    ):
        self.stream_manager = stream_manager
        self.interval_seconds = interval_seconds
        self.collect_cpu = collect_cpu
        self.collect_memory = collect_memory
        self.collect_disk = collect_disk
        self.collect_network = collect_network

        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start collecting metrics."""
        self._running = True
        self._task = asyncio.create_task(self._collection_loop())
        logger.info("System metrics collector started")

    async def stop(self) -> None:
        """Stop collecting metrics."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _collection_loop(self) -> None:
        """Background metric collection loop."""
        try:
            import psutil
        except ImportError:
            logger.warning("psutil not installed, using mock metrics")
            psutil = None

        while self._running:
            try:
                metrics = []

                if psutil:
                    if self.collect_cpu:
                        cpu_percent = psutil.cpu_percent(interval=0.1)
                        metrics.append(
                            MetricPoint(
                                name="system.cpu.usage_percent",
                                value=cpu_percent,
                                unit="percent",
                            )
                        )

                        # Per-CPU
                        cpu_per = psutil.cpu_percent(interval=0.1, percpu=True)
                        for i, percent in enumerate(cpu_per):
                            metrics.append(
                                MetricPoint(
                                    name="system.cpu.core_usage_percent",
                                    value=percent,
                                    labels={"core": str(i)},
                                    unit="percent",
                                )
                            )

                    if self.collect_memory:
                        mem = psutil.virtual_memory()
                        metrics.extend(
                            [
                                MetricPoint(
                                    name="system.memory.used_bytes",
                                    value=mem.used,
                                    unit="bytes",
                                ),
                                MetricPoint(
                                    name="system.memory.available_bytes",
                                    value=mem.available,
                                    unit="bytes",
                                ),
                                MetricPoint(
                                    name="system.memory.usage_percent",
                                    value=mem.percent,
                                    unit="percent",
                                ),
                            ]
                        )

                    if self.collect_disk:
                        disk = psutil.disk_usage("/")
                        metrics.extend(
                            [
                                MetricPoint(
                                    name="system.disk.used_bytes",
                                    value=disk.used,
                                    unit="bytes",
                                ),
                                MetricPoint(
                                    name="system.disk.free_bytes",
                                    value=disk.free,
                                    unit="bytes",
                                ),
                                MetricPoint(
                                    name="system.disk.usage_percent",
                                    value=disk.percent,
                                    unit="percent",
                                ),
                            ]
                        )

                    if self.collect_network:
                        net = psutil.net_io_counters()
                        metrics.extend(
                            [
                                MetricPoint(
                                    name="system.network.bytes_sent",
                                    value=net.bytes_sent,
                                    metric_type=MetricType.COUNTER,
                                    unit="bytes",
                                ),
                                MetricPoint(
                                    name="system.network.bytes_recv",
                                    value=net.bytes_recv,
                                    metric_type=MetricType.COUNTER,
                                    unit="bytes",
                                ),
                            ]
                        )
                else:
                    # Mock metrics for testing
                    import random

                    metrics.append(
                        MetricPoint(
                            name="system.cpu.usage_percent",
                            value=random.uniform(10, 90),
                            unit="percent",
                        )
                    )
                    metrics.append(
                        MetricPoint(
                            name="system.memory.usage_percent",
                            value=random.uniform(30, 80),
                            unit="percent",
                        )
                    )

                # Publish all metrics
                await self.stream_manager.publish_batch(metrics)

            except Exception as e:
                logger.error(f"Metric collection error: {e}")

            await asyncio.sleep(self.interval_seconds)


# =============================================================================
# Factory Functions
# =============================================================================


def create_metrics_stream(
    max_clients: int = 1000,
    default_interval_ms: int = 1000,
) -> MetricsStreamManager:
    """
    Create a metrics stream manager.

    Args:
        max_clients: Maximum concurrent clients
        default_interval_ms: Default update interval

    Returns:
        Configured MetricsStreamManager instance
    """
    return MetricsStreamManager(
        max_clients=max_clients,
        default_interval_ms=default_interval_ms,
    )
