"""
Performance Optimizer - System-wide performance optimization engine.

This module provides comprehensive performance optimization for the distributed
cluster, including resource allocation, query optimization, connection pooling,
and automatic performance tuning.
"""

import asyncio
import functools
import hashlib
import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """Types of system resources."""

    CPU = "cpu"
    MEMORY = "memory"
    DISK_IO = "disk_io"
    NETWORK_IO = "network_io"
    GPU = "gpu"
    CONNECTIONS = "connections"
    THREADS = "threads"


class BottleneckType(Enum):
    """Types of performance bottlenecks."""

    CPU_BOUND = "cpu_bound"
    MEMORY_BOUND = "memory_bound"
    IO_BOUND = "io_bound"
    NETWORK_BOUND = "network_bound"
    LOCK_CONTENTION = "lock_contention"
    CONNECTION_EXHAUSTION = "connection_exhaustion"
    CACHE_MISS = "cache_miss"
    GC_PRESSURE = "gc_pressure"


class OptimizationLevel(Enum):
    """Levels of optimization aggressiveness."""

    MINIMAL = "minimal"  # Only critical optimizations
    MODERATE = "moderate"  # Balanced approach
    AGGRESSIVE = "aggressive"  # Maximum optimization
    ADAPTIVE = "adaptive"  # Dynamically adjust based on conditions


@dataclass
class ResourceMetrics:
    """Snapshot of resource utilization metrics."""

    timestamp: datetime = field(default_factory=datetime.now)
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_available_mb: int = 0
    disk_read_bytes: int = 0
    disk_write_bytes: int = 0
    network_recv_bytes: int = 0
    network_sent_bytes: int = 0
    open_connections: int = 0
    active_threads: int = 0
    gc_collections: Dict[int, int] = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """Application-level performance metrics."""

    timestamp: datetime = field(default_factory=datetime.now)
    request_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    throughput_rps: float = 0.0
    active_requests: int = 0
    queued_requests: int = 0


@dataclass
class OptimizationAction:
    """Represents a performance optimization action."""

    action_type: str
    target: str
    parameters: Dict[str, Any]
    priority: int
    estimated_impact: float
    risk_level: str  # low, medium, high
    reversible: bool
    description: str


@dataclass
class PerformanceProfile:
    """Performance profile for different workload types."""

    name: str
    cpu_target: float = 70.0
    memory_target: float = 80.0
    latency_target_ms: float = 100.0
    throughput_target_rps: float = 1000.0
    connection_pool_size: int = 100
    thread_pool_size: int = 50
    batch_size: int = 100
    prefetch_enabled: bool = True
    compression_enabled: bool = True


class ResourceMonitor:
    """Monitors system resource utilization."""

    def __init__(self, sample_interval: float = 1.0):
        self.sample_interval = sample_interval
        self.metrics_history: deque = deque(maxlen=1000)
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._last_disk_io = None
        self._last_net_io = None

    def start(self):
        """Start resource monitoring."""
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Resource monitor started")

    def stop(self):
        """Stop resource monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        logger.info("Resource monitor stopped")

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            try:
                metrics = self._collect_metrics()
                self.metrics_history.append(metrics)
                time.sleep(self.sample_interval)
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")

    def _collect_metrics(self) -> ResourceMetrics:
        """Collect current resource metrics."""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # Memory
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_mb = memory.available // (1024 * 1024)

            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if disk_io and self._last_disk_io:
                disk_read_bytes = disk_io.read_bytes - self._last_disk_io.read_bytes
                disk_write_bytes = disk_io.write_bytes - self._last_disk_io.write_bytes
            else:
                disk_read_bytes = 0
                disk_write_bytes = 0
            self._last_disk_io = disk_io

            # Network I/O
            net_io = psutil.net_io_counters()
            if net_io and self._last_net_io:
                network_recv_bytes = net_io.bytes_recv - self._last_net_io.bytes_recv
                network_sent_bytes = net_io.bytes_sent - self._last_net_io.bytes_sent
            else:
                network_recv_bytes = 0
                network_sent_bytes = 0
            self._last_net_io = net_io

            # Connections and threads
            try:
                current_process = psutil.Process()
                open_connections = len(current_process.connections())
                active_threads = current_process.num_threads()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                open_connections = 0
                active_threads = 0

            return ResourceMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_available_mb=memory_available_mb,
                disk_read_bytes=disk_read_bytes,
                disk_write_bytes=disk_write_bytes,
                network_recv_bytes=network_recv_bytes,
                network_sent_bytes=network_sent_bytes,
                open_connections=open_connections,
                active_threads=active_threads,
            )

        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            return ResourceMetrics()

    def get_current_metrics(self) -> Optional[ResourceMetrics]:
        """Get the most recent metrics."""
        return self.metrics_history[-1] if self.metrics_history else None

    def get_average_metrics(self, window_seconds: float = 60.0) -> Optional[ResourceMetrics]:
        """Get averaged metrics over a time window."""
        if not self.metrics_history:
            return None

        cutoff = datetime.now() - timedelta(seconds=window_seconds)
        recent = [m for m in self.metrics_history if m.timestamp >= cutoff]

        if not recent:
            return None

        return ResourceMetrics(
            cpu_percent=statistics.mean([m.cpu_percent for m in recent]),
            memory_percent=statistics.mean([m.memory_percent for m in recent]),
            memory_available_mb=int(statistics.mean([m.memory_available_mb for m in recent])),
            disk_read_bytes=int(statistics.mean([m.disk_read_bytes for m in recent])),
            disk_write_bytes=int(statistics.mean([m.disk_write_bytes for m in recent])),
            network_recv_bytes=int(statistics.mean([m.network_recv_bytes for m in recent])),
            network_sent_bytes=int(statistics.mean([m.network_sent_bytes for m in recent])),
            open_connections=int(statistics.mean([m.open_connections for m in recent])),
            active_threads=int(statistics.mean([m.active_threads for m in recent])),
        )


class BottleneckDetector:
    """Detects performance bottlenecks based on metrics."""

    def __init__(self, resource_monitor: ResourceMonitor):
        self.resource_monitor = resource_monitor
        self.bottleneck_history: deque = deque(maxlen=100)

        # Thresholds
        self.cpu_threshold = 85.0
        self.memory_threshold = 90.0
        self.disk_io_threshold = 100 * 1024 * 1024  # 100 MB/s
        self.network_io_threshold = 100 * 1024 * 1024  # 100 MB/s
        self.connection_threshold = 1000
        self.thread_threshold = 500

    def detect_bottlenecks(self) -> List[Tuple[BottleneckType, float]]:
        """Detect current bottlenecks and their severity (0-1)."""
        bottlenecks = []

        metrics = self.resource_monitor.get_average_metrics(window_seconds=30.0)
        if not metrics:
            return bottlenecks

        # CPU bottleneck
        if metrics.cpu_percent > self.cpu_threshold:
            severity = min(1.0, (metrics.cpu_percent - self.cpu_threshold) / (100 - self.cpu_threshold))
            bottlenecks.append((BottleneckType.CPU_BOUND, severity))

        # Memory bottleneck
        if metrics.memory_percent > self.memory_threshold:
            severity = min(1.0, (metrics.memory_percent - self.memory_threshold) / (100 - self.memory_threshold))
            bottlenecks.append((BottleneckType.MEMORY_BOUND, severity))

        # Disk I/O bottleneck
        disk_io_rate = metrics.disk_read_bytes + metrics.disk_write_bytes
        if disk_io_rate > self.disk_io_threshold:
            severity = min(1.0, (disk_io_rate - self.disk_io_threshold) / self.disk_io_threshold)
            bottlenecks.append((BottleneckType.IO_BOUND, severity))

        # Network I/O bottleneck
        network_io_rate = metrics.network_recv_bytes + metrics.network_sent_bytes
        if network_io_rate > self.network_io_threshold:
            severity = min(1.0, (network_io_rate - self.network_io_threshold) / self.network_io_threshold)
            bottlenecks.append((BottleneckType.NETWORK_BOUND, severity))

        # Connection exhaustion
        if metrics.open_connections > self.connection_threshold:
            severity = min(1.0, (metrics.open_connections - self.connection_threshold) / self.connection_threshold)
            bottlenecks.append((BottleneckType.CONNECTION_EXHAUSTION, severity))

        if bottlenecks:
            self.bottleneck_history.append(
                {"timestamp": datetime.now().isoformat(), "bottlenecks": [(b.value, s) for b, s in bottlenecks]}
            )

        return bottlenecks


class AdaptiveConnectionPool:
    """Adaptive connection pool that adjusts size based on demand."""

    def __init__(
        self,
        min_size: int = 10,
        max_size: int = 1000,
        initial_size: int = 50,
        scale_up_threshold: float = 0.8,
        scale_down_threshold: float = 0.3,
    ):
        self.min_size = min_size
        self.max_size = max_size
        self.current_size = initial_size
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold

        self.active_connections = 0
        self.peak_connections = 0
        self.connection_requests: deque = deque(maxlen=1000)
        self.wait_times: deque = deque(maxlen=1000)

        self._lock = threading.Lock()

    def record_connection_usage(self, active: int, wait_time_ms: float = 0.0):
        """Record connection pool usage."""
        with self._lock:
            self.active_connections = active
            self.peak_connections = max(self.peak_connections, active)
            self.connection_requests.append(
                {
                    "timestamp": time.time(),
                    "active": active,
                }
            )
            self.wait_times.append(wait_time_ms)

    def get_recommended_size(self) -> int:
        """Get recommended pool size based on usage patterns."""
        with self._lock:
            if not self.connection_requests:
                return self.current_size

            # Calculate utilization
            utilization = self.active_connections / self.current_size if self.current_size > 0 else 1.0

            # Scale up if high utilization
            if utilization > self.scale_up_threshold:
                new_size = min(int(self.current_size * 1.5), self.max_size)
            # Scale down if low utilization
            elif utilization < self.scale_down_threshold and self.current_size > self.min_size:
                new_size = max(
                    int(self.current_size * 0.8), self.min_size, self.peak_connections + 10  # Keep some headroom
                )
            else:
                new_size = self.current_size

            return new_size

    def apply_recommended_size(self) -> int:
        """Apply the recommended pool size and return new size."""
        new_size = self.get_recommended_size()
        with self._lock:
            self.current_size = new_size
            # Reset peak periodically
            self.peak_connections = int(self.peak_connections * 0.9)
        return new_size


class AdaptiveThreadPool:
    """Adaptive thread pool that adjusts size based on workload."""

    def __init__(
        self, min_workers: int = 4, max_workers: int = 200, initial_workers: int = 20, queue_threshold: int = 50
    ):
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.current_workers = initial_workers
        self.queue_threshold = queue_threshold

        self.executor: Optional[ThreadPoolExecutor] = None
        self.queue_size = 0
        self.active_tasks = 0
        self.completed_tasks = 0
        self.task_times: deque = deque(maxlen=1000)

        self._lock = threading.Lock()

    def initialize(self):
        """Initialize the thread pool."""
        self.executor = ThreadPoolExecutor(max_workers=self.current_workers)

    def shutdown(self, wait: bool = True):
        """Shutdown the thread pool."""
        if self.executor:
            self.executor.shutdown(wait=wait)

    def record_task(self, execution_time_ms: float):
        """Record a completed task."""
        with self._lock:
            self.completed_tasks += 1
            self.task_times.append(execution_time_ms)

    def update_queue_stats(self, queue_size: int, active_tasks: int):
        """Update queue statistics."""
        with self._lock:
            self.queue_size = queue_size
            self.active_tasks = active_tasks

    def get_recommended_workers(self) -> int:
        """Get recommended number of workers."""
        with self._lock:
            # High queue pressure - scale up
            if self.queue_size > self.queue_threshold:
                scale_factor = min(2.0, 1.0 + (self.queue_size - self.queue_threshold) / self.queue_threshold)
                new_workers = min(int(self.current_workers * scale_factor), self.max_workers)
            # Low utilization - scale down
            elif self.queue_size == 0 and self.active_tasks < self.current_workers * 0.3:
                new_workers = max(int(self.current_workers * 0.8), self.min_workers)
            else:
                new_workers = self.current_workers

            return new_workers

    def resize(self, new_size: int):
        """Resize the thread pool."""
        with self._lock:
            if new_size != self.current_workers:
                # ThreadPoolExecutor doesn't support dynamic resizing,
                # so we track the desired size for recreation
                self.current_workers = new_size
                logger.info(f"Thread pool size adjusted to {new_size}")


class QueryOptimizer:
    """Optimizes query patterns for better performance."""

    def __init__(self):
        self.query_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "total_time_ms": 0.0,
                "avg_time_ms": 0.0,
                "result_sizes": [],
            }
        )
        self.slow_query_threshold_ms = 100.0
        self.slow_queries: deque = deque(maxlen=100)
        self._lock = threading.Lock()

    def record_query(self, query_hash: str, execution_time_ms: float, result_size: int):
        """Record query execution statistics."""
        with self._lock:
            stats = self.query_stats[query_hash]
            stats["count"] += 1
            stats["total_time_ms"] += execution_time_ms
            stats["avg_time_ms"] = stats["total_time_ms"] / stats["count"]
            stats["result_sizes"].append(result_size)
            if len(stats["result_sizes"]) > 100:
                stats["result_sizes"] = stats["result_sizes"][-100:]

            if execution_time_ms > self.slow_query_threshold_ms:
                self.slow_queries.append(
                    {
                        "query_hash": query_hash,
                        "execution_time_ms": execution_time_ms,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

    def get_optimization_suggestions(self) -> List[Dict[str, Any]]:
        """Get query optimization suggestions."""
        suggestions = []

        with self._lock:
            for query_hash, stats in self.query_stats.items():
                if stats["count"] < 10:
                    continue

                # Frequent slow queries
                if stats["avg_time_ms"] > self.slow_query_threshold_ms:
                    suggestions.append(
                        {
                            "type": "slow_query",
                            "query_hash": query_hash,
                            "avg_time_ms": stats["avg_time_ms"],
                            "count": stats["count"],
                            "suggestion": "Consider caching results or optimizing query",
                        }
                    )

                # Large result sets
                avg_result_size = statistics.mean(stats["result_sizes"]) if stats["result_sizes"] else 0
                if avg_result_size > 10000:
                    suggestions.append(
                        {
                            "type": "large_result",
                            "query_hash": query_hash,
                            "avg_result_size": avg_result_size,
                            "suggestion": "Consider pagination or result limiting",
                        }
                    )

                # High frequency queries
                if stats["count"] > 1000:
                    suggestions.append(
                        {
                            "type": "high_frequency",
                            "query_hash": query_hash,
                            "count": stats["count"],
                            "suggestion": "Consider caching or batching",
                        }
                    )

        return suggestions


class PerformanceOptimizer:
    """
    System-wide performance optimization engine that coordinates
    all optimization components and provides unified optimization.
    """

    def __init__(
        self, level: OptimizationLevel = OptimizationLevel.ADAPTIVE, profile: Optional[PerformanceProfile] = None
    ):
        self.level = level
        self.profile = profile or PerformanceProfile(name="default")

        # Components
        self.resource_monitor = ResourceMonitor()
        self.bottleneck_detector = BottleneckDetector(self.resource_monitor)
        self.connection_pool = AdaptiveConnectionPool()
        self.thread_pool = AdaptiveThreadPool()
        self.query_optimizer = QueryOptimizer()

        # Metrics tracking
        self.performance_history: deque = deque(maxlen=1000)
        self.latencies: deque = deque(maxlen=10000)
        self.request_times: deque = deque(maxlen=10000)

        # Optimization state
        self.pending_actions: List[OptimizationAction] = []
        self.applied_actions: List[Dict[str, Any]] = []
        self.optimization_callbacks: List[Callable[[OptimizationAction], None]] = []

        # Background optimization
        self._running = False
        self._optimization_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()

    def start(self):
        """Start the performance optimizer."""
        self.resource_monitor.start()
        self.thread_pool.initialize()
        self._running = True
        logger.info("Performance optimizer started")

    def stop(self):
        """Stop the performance optimizer."""
        self._running = False
        self.resource_monitor.stop()
        self.thread_pool.shutdown()
        logger.info("Performance optimizer stopped")

    async def start_async(self):
        """Start async optimization loop."""
        if not self._running:
            self.start()
        self._optimization_task = asyncio.create_task(self._optimization_loop())

    async def stop_async(self):
        """Stop async optimization loop."""
        self._running = False
        if self._optimization_task:
            self._optimization_task.cancel()
            try:
                await self._optimization_task
            except asyncio.CancelledError:
                pass
        self.stop()

    async def _optimization_loop(self):
        """Background optimization loop."""
        while self._running:
            try:
                await asyncio.sleep(10.0)  # Check every 10 seconds

                # Detect bottlenecks
                bottlenecks = self.bottleneck_detector.detect_bottlenecks()

                # Generate optimization actions
                actions = self._generate_actions(bottlenecks)

                # Apply actions based on level
                for action in actions:
                    if self._should_apply_action(action):
                        await self._apply_action(action)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Optimization loop error: {e}")

    def record_request(self, latency_ms: float, success: bool = True):
        """Record a request for performance tracking."""
        current_time = time.time()

        with self._lock:
            self.latencies.append(latency_ms)
            self.request_times.append(current_time)

    def record_query(self, query: str, execution_time_ms: float, result_size: int):
        """Record a query execution."""
        query_hash = hashlib.md5(query.encode()).hexdigest()[:16]
        self.query_optimizer.record_query(query_hash, execution_time_ms, result_size)

    def get_current_performance(self) -> PerformanceMetrics:
        """Get current performance metrics."""
        with self._lock:
            now = time.time()
            window = 60.0  # Last minute

            # Count requests in window
            recent_times = [t for t in self.request_times if now - t <= window]
            request_count = len(recent_times)
            throughput_rps = request_count / window if window > 0 else 0

            # Calculate latency percentiles
            recent_latencies = list(self.latencies)[-1000:]
            if recent_latencies:
                sorted_latencies = sorted(recent_latencies)
                avg_latency = statistics.mean(recent_latencies)
                p50_latency = sorted_latencies[len(sorted_latencies) // 2]
                p95_idx = int(len(sorted_latencies) * 0.95)
                p99_idx = int(len(sorted_latencies) * 0.99)
                p95_latency = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
                p99_latency = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]
            else:
                avg_latency = p50_latency = p95_latency = p99_latency = 0.0

            return PerformanceMetrics(
                request_count=request_count,
                avg_latency_ms=avg_latency,
                p50_latency_ms=p50_latency,
                p95_latency_ms=p95_latency,
                p99_latency_ms=p99_latency,
                throughput_rps=throughput_rps,
            )

    def _generate_actions(self, bottlenecks: List[Tuple[BottleneckType, float]]) -> List[OptimizationAction]:
        """Generate optimization actions based on detected bottlenecks."""
        actions = []

        for bottleneck, severity in bottlenecks:
            if bottleneck == BottleneckType.CPU_BOUND:
                if severity > 0.5:
                    actions.append(
                        OptimizationAction(
                            action_type="reduce_cpu_load",
                            target="thread_pool",
                            parameters={"action": "reduce_workers", "factor": 0.8},
                            priority=int(severity * 10),
                            estimated_impact=severity * 20,
                            risk_level="low",
                            reversible=True,
                            description="Reduce thread pool size to lower CPU usage",
                        )
                    )

            elif bottleneck == BottleneckType.MEMORY_BOUND:
                if severity > 0.3:
                    actions.append(
                        OptimizationAction(
                            action_type="reduce_memory",
                            target="cache",
                            parameters={"action": "evict", "percentage": severity * 30},
                            priority=int(severity * 10),
                            estimated_impact=severity * 25,
                            risk_level="medium",
                            reversible=False,
                            description="Evict cache entries to free memory",
                        )
                    )

            elif bottleneck == BottleneckType.CONNECTION_EXHAUSTION:
                actions.append(
                    OptimizationAction(
                        action_type="optimize_connections",
                        target="connection_pool",
                        parameters={"action": "expand", "factor": 1.5},
                        priority=int(severity * 10),
                        estimated_impact=severity * 30,
                        risk_level="low",
                        reversible=True,
                        description="Expand connection pool to handle more connections",
                    )
                )

            elif bottleneck == BottleneckType.IO_BOUND:
                actions.append(
                    OptimizationAction(
                        action_type="optimize_io",
                        target="batching",
                        parameters={"enable": True, "batch_size": 100},
                        priority=int(severity * 10),
                        estimated_impact=severity * 20,
                        risk_level="low",
                        reversible=True,
                        description="Enable I/O batching to reduce overhead",
                    )
                )

        return sorted(actions, key=lambda a: a.priority, reverse=True)

    def _should_apply_action(self, action: OptimizationAction) -> bool:
        """Determine if an action should be applied based on optimization level."""
        if self.level == OptimizationLevel.MINIMAL:
            return action.priority >= 8 and action.risk_level == "low"
        elif self.level == OptimizationLevel.MODERATE:
            return action.priority >= 5 and action.risk_level in ["low", "medium"]
        elif self.level == OptimizationLevel.AGGRESSIVE:
            return action.priority >= 3
        else:  # ADAPTIVE
            # Consider current system state
            resource_metrics = self.resource_monitor.get_current_metrics()
            if resource_metrics:
                # Be more aggressive when resources are strained
                if resource_metrics.cpu_percent > 90 or resource_metrics.memory_percent > 90:
                    return action.priority >= 3
                elif resource_metrics.cpu_percent > 70 or resource_metrics.memory_percent > 80:
                    return action.priority >= 5 and action.risk_level in ["low", "medium"]
            return action.priority >= 7 and action.risk_level == "low"

    async def _apply_action(self, action: OptimizationAction):
        """Apply an optimization action."""
        try:
            logger.info(f"Applying optimization: {action.description}")

            # Record the action
            self.applied_actions.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "action": action.action_type,
                    "target": action.target,
                    "parameters": action.parameters,
                }
            )

            # Notify callbacks
            for callback in self.optimization_callbacks:
                try:
                    callback(action)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

            self.pending_actions = [a for a in self.pending_actions if a != action]

        except Exception as e:
            logger.error(f"Failed to apply action: {e}")

    def register_callback(self, callback: Callable[[OptimizationAction], None]):
        """Register a callback for optimization actions."""
        self.optimization_callbacks.append(callback)

    def get_optimization_report(self) -> Dict[str, Any]:
        """Get a comprehensive optimization report."""
        resource_metrics = self.resource_monitor.get_average_metrics()
        performance_metrics = self.get_current_performance()
        bottlenecks = self.bottleneck_detector.detect_bottlenecks()
        query_suggestions = self.query_optimizer.get_optimization_suggestions()

        return {
            "resource_metrics": (
                {
                    "cpu_percent": resource_metrics.cpu_percent if resource_metrics else 0,
                    "memory_percent": resource_metrics.memory_percent if resource_metrics else 0,
                    "memory_available_mb": resource_metrics.memory_available_mb if resource_metrics else 0,
                    "open_connections": resource_metrics.open_connections if resource_metrics else 0,
                    "active_threads": resource_metrics.active_threads if resource_metrics else 0,
                }
                if resource_metrics
                else {}
            ),
            "performance_metrics": {
                "request_count": performance_metrics.request_count,
                "avg_latency_ms": performance_metrics.avg_latency_ms,
                "p95_latency_ms": performance_metrics.p95_latency_ms,
                "p99_latency_ms": performance_metrics.p99_latency_ms,
                "throughput_rps": performance_metrics.throughput_rps,
            },
            "bottlenecks": [{"type": b.value, "severity": s} for b, s in bottlenecks],
            "connection_pool": {
                "current_size": self.connection_pool.current_size,
                "active_connections": self.connection_pool.active_connections,
                "recommended_size": self.connection_pool.get_recommended_size(),
            },
            "thread_pool": {
                "current_workers": self.thread_pool.current_workers,
                "queue_size": self.thread_pool.queue_size,
                "recommended_workers": self.thread_pool.get_recommended_workers(),
            },
            "query_suggestions": query_suggestions[:10],
            "applied_actions": self.applied_actions[-20:],
            "optimization_level": self.level.value,
            "profile": self.profile.name,
        }


# Performance decorator for automatic optimization tracking
def track_performance(optimizer: PerformanceOptimizer):
    """Decorator to track performance of functions."""

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception:
                success = False
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000
                optimizer.record_request(latency_ms, success)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception:
                success = False
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000
                optimizer.record_request(latency_ms, success)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
