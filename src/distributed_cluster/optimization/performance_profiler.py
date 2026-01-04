"""
Performance Profiler - Comprehensive performance profiling.

This module provides detailed performance profiling for cache operations
including latency analysis, throughput measurement, resource correlation,
and bottleneck identification.
"""

import asyncio
import functools
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProfileLevel(Enum):
    """Levels of profiling detail."""
    OFF = 0
    BASIC = 1
    DETAILED = 2
    FULL = 3


class OperationType(Enum):
    """Types of operations to profile."""
    CACHE_GET = "cache_get"
    CACHE_SET = "cache_set"
    CACHE_DELETE = "cache_delete"
    CACHE_INVALIDATE = "cache_invalidate"
    SERIALIZATION = "serialization"
    DESERIALIZATION = "deserialization"
    COMPRESSION = "compression"
    DECOMPRESSION = "decompression"
    NETWORK_SEND = "network_send"
    NETWORK_RECV = "network_recv"
    DISK_READ = "disk_read"
    DISK_WRITE = "disk_write"
    MEMORY_ALLOC = "memory_alloc"
    QUERY = "query"
    BATCH = "batch"
    CUSTOM = "custom"


@dataclass
class OperationProfile:
    """Profile data for a single operation."""
    operation_id: str
    operation_type: OperationType
    start_time: float
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    child_operations: List['OperationProfile'] = field(default_factory=list)
    parent_id: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        """Check if operation is complete."""
        return self.end_time is not None


@dataclass
class LatencyHistogram:
    """Histogram for latency distribution."""
    buckets: Dict[float, int] = field(default_factory=dict)
    total_count: int = 0
    total_sum: float = 0.0
    min_value: float = float('inf')
    max_value: float = 0.0

    def record(self, value: float):
        """Record a value in the histogram."""
        # Find bucket (powers of 2)
        if value <= 0:
            bucket = 0.0
        else:
            import math
            bucket = 2 ** math.floor(math.log2(value))

        self.buckets[bucket] = self.buckets.get(bucket, 0) + 1
        self.total_count += 1
        self.total_sum += value
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)

    @property
    def mean(self) -> float:
        """Calculate mean value."""
        return self.total_sum / self.total_count if self.total_count > 0 else 0.0

    def percentile(self, p: float) -> float:
        """Calculate approximate percentile."""
        if self.total_count == 0:
            return 0.0

        target_count = int(self.total_count * p)
        cumulative = 0

        for bucket in sorted(self.buckets.keys()):
            cumulative += self.buckets[bucket]
            if cumulative >= target_count:
                return bucket

        return self.max_value


@dataclass
class OperationStats:
    """Aggregated statistics for an operation type."""
    operation_type: OperationType
    count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0
    latency_histogram: LatencyHistogram = field(default_factory=LatencyHistogram)

    @property
    def avg_duration_ms(self) -> float:
        """Calculate average duration."""
        return self.total_duration_ms / self.count if self.count > 0 else 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        return self.success_count / self.count if self.count > 0 else 0.0

    def record(self, profile: OperationProfile):
        """Record an operation profile."""
        self.count += 1
        if profile.success:
            self.success_count += 1
        else:
            self.error_count += 1

        self.total_duration_ms += profile.duration_ms
        self.min_duration_ms = min(self.min_duration_ms, profile.duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, profile.duration_ms)
        self.latency_histogram.record(profile.duration_ms)


@dataclass
class ProfileSnapshot:
    """Snapshot of profiling data at a point in time."""
    timestamp: datetime
    operation_stats: Dict[OperationType, OperationStats]
    throughput_ops: float
    avg_latency_ms: float
    p99_latency_ms: float
    error_rate: float
    active_operations: int


class OperationContext:
    """Context manager for profiling operations."""

    def __init__(
        self,
        profiler: 'PerformanceProfiler',
        operation_type: OperationType,
        operation_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.profiler = profiler
        self.operation_type = operation_type
        self.operation_id = operation_id or f"{operation_type.value}:{time.time()}"
        self.parent_id = parent_id
        self.metadata = metadata or {}
        self.profile: Optional[OperationProfile] = None

    def __enter__(self):
        self.profile = OperationProfile(
            operation_id=self.operation_id,
            operation_type=self.operation_type,
            start_time=time.time(),
            metadata=self.metadata,
            parent_id=self.parent_id,
        )
        self.profiler._start_operation(self.profile)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.profile:
            self.profile.end_time = time.time()
            self.profile.duration_ms = (self.profile.end_time - self.profile.start_time) * 1000
            self.profile.success = exc_type is None

            if exc_type is not None:
                self.profile.error = str(exc_val)

            self.profiler._complete_operation(self.profile)

        return False  # Don't suppress exceptions

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)

    def add_metadata(self, key: str, value: Any):
        """Add metadata to the profile."""
        if self.profile:
            self.profile.metadata[key] = value


class PerformanceProfiler:
    """
    Comprehensive performance profiler for cache operations.
    """

    def __init__(
        self,
        level: ProfileLevel = ProfileLevel.BASIC,
        history_size: int = 10000,
        snapshot_interval_seconds: float = 60.0
    ):
        self.level = level
        self.history_size = history_size
        self.snapshot_interval_seconds = snapshot_interval_seconds

        # Operation tracking
        self.active_operations: Dict[str, OperationProfile] = {}
        self.completed_operations: deque = deque(maxlen=history_size)

        # Statistics by operation type
        self.operation_stats: Dict[OperationType, OperationStats] = {
            op: OperationStats(operation_type=op)
            for op in OperationType
        }

        # Time-series snapshots
        self.snapshots: deque = deque(maxlen=1000)

        # Slow operation tracking
        self.slow_operations: deque = deque(maxlen=100)
        self.slow_threshold_ms = 100.0

        # Error tracking
        self.error_traces: deque = deque(maxlen=100)

        # Throughput tracking
        self.operation_times: deque = deque(maxlen=10000)

        # Control
        self._lock = threading.RLock()
        self._running = False
        self._snapshot_task: Optional[asyncio.Task] = None
        self._operation_counter = 0

    def profile(
        self,
        operation_type: OperationType,
        operation_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        **metadata
    ) -> OperationContext:
        """Create a profiling context for an operation."""
        if self.level == ProfileLevel.OFF:
            return _NoOpContext()

        return OperationContext(
            profiler=self,
            operation_type=operation_type,
            operation_id=operation_id,
            parent_id=parent_id,
            metadata=metadata,
        )

    def _start_operation(self, profile: OperationProfile):
        """Record the start of an operation."""
        with self._lock:
            self._operation_counter += 1
            self.active_operations[profile.operation_id] = profile

    def _complete_operation(self, profile: OperationProfile):
        """Record the completion of an operation."""
        with self._lock:
            self.active_operations.pop(profile.operation_id, None)
            self.completed_operations.append(profile)
            self.operation_times.append(profile.start_time)

            # Update statistics
            stats = self.operation_stats[profile.operation_type]
            stats.record(profile)

            # Track slow operations
            if profile.duration_ms > self.slow_threshold_ms:
                self.slow_operations.append(profile)

            # Track errors
            if not profile.success and self.level >= ProfileLevel.DETAILED:
                self.error_traces.append({
                    'operation_id': profile.operation_id,
                    'operation_type': profile.operation_type.value,
                    'error': profile.error,
                    'timestamp': profile.end_time,
                    'metadata': profile.metadata,
                })

    def record_operation(
        self,
        operation_type: OperationType,
        duration_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        **metadata
    ):
        """Directly record an operation without context manager."""
        if self.level == ProfileLevel.OFF:
            return

        current_time = time.time()

        profile = OperationProfile(
            operation_id=f"{operation_type.value}:{current_time}",
            operation_type=operation_type,
            start_time=current_time - (duration_ms / 1000),
            end_time=current_time,
            duration_ms=duration_ms,
            success=success,
            error=error,
            metadata=metadata,
        )

        self._complete_operation(profile)

    def get_stats(self, operation_type: Optional[OperationType] = None) -> Dict[str, Any]:
        """Get statistics for operations."""
        with self._lock:
            if operation_type:
                stats = self.operation_stats[operation_type]
                return {
                    'operation_type': operation_type.value,
                    'count': stats.count,
                    'success_count': stats.success_count,
                    'error_count': stats.error_count,
                    'success_rate': stats.success_rate,
                    'avg_duration_ms': stats.avg_duration_ms,
                    'min_duration_ms': stats.min_duration_ms if stats.min_duration_ms != float('inf') else 0,
                    'max_duration_ms': stats.max_duration_ms,
                    'p50_duration_ms': stats.latency_histogram.percentile(0.5),
                    'p95_duration_ms': stats.latency_histogram.percentile(0.95),
                    'p99_duration_ms': stats.latency_histogram.percentile(0.99),
                }
            else:
                return {
                    op.value: self.get_stats(op)
                    for op in OperationType
                    if self.operation_stats[op].count > 0
                }

    def get_throughput(self, window_seconds: float = 60.0) -> float:
        """Calculate operations per second over a time window."""
        with self._lock:
            current_time = time.time()
            cutoff = current_time - window_seconds

            count = sum(1 for t in self.operation_times if t >= cutoff)
            return count / window_seconds if window_seconds > 0 else 0

    def get_latency_percentiles(
        self,
        operation_type: Optional[OperationType] = None,
        percentiles: Optional[List[float]] = None
    ) -> Dict[str, float]:
        """Get latency percentiles."""
        if percentiles is None:
            percentiles = [0.5, 0.9, 0.95, 0.99]
        with self._lock:
            if operation_type:
                histogram = self.operation_stats[operation_type].latency_histogram
            else:
                # Aggregate all operations
                histogram = LatencyHistogram()
                for profile in self.completed_operations:
                    histogram.record(profile.duration_ms)

            return {
                f"p{int(p*100)}": histogram.percentile(p)
                for p in percentiles
            }

    def get_slow_operations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent slow operations."""
        with self._lock:
            return [
                {
                    'operation_id': op.operation_id,
                    'operation_type': op.operation_type.value,
                    'duration_ms': op.duration_ms,
                    'timestamp': op.end_time,
                    'metadata': op.metadata,
                }
                for op in list(self.slow_operations)[-limit:]
            ]

    def get_error_traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent error traces."""
        with self._lock:
            return list(self.error_traces)[-limit:]

    def get_active_operations(self) -> List[Dict[str, Any]]:
        """Get currently active operations."""
        with self._lock:
            current_time = time.time()
            return [
                {
                    'operation_id': op.operation_id,
                    'operation_type': op.operation_type.value,
                    'running_time_ms': (current_time - op.start_time) * 1000,
                    'metadata': op.metadata,
                }
                for op in self.active_operations.values()
            ]

    def take_snapshot(self) -> ProfileSnapshot:
        """Take a snapshot of current profiling state."""
        with self._lock:
            # Calculate aggregate metrics
            total_ops = sum(s.count for s in self.operation_stats.values())
            total_duration = sum(s.total_duration_ms for s in self.operation_stats.values())
            total_errors = sum(s.error_count for s in self.operation_stats.values())

            snapshot = ProfileSnapshot(
                timestamp=datetime.now(),
                operation_stats={
                    op: OperationStats(
                        operation_type=op,
                        count=stats.count,
                        success_count=stats.success_count,
                        error_count=stats.error_count,
                        total_duration_ms=stats.total_duration_ms,
                        min_duration_ms=stats.min_duration_ms,
                        max_duration_ms=stats.max_duration_ms,
                    )
                    for op, stats in self.operation_stats.items()
                },
                throughput_ops=self.get_throughput(),
                avg_latency_ms=total_duration / total_ops if total_ops > 0 else 0,
                p99_latency_ms=self.get_latency_percentiles().get('p99', 0),
                error_rate=total_errors / total_ops if total_ops > 0 else 0,
                active_operations=len(self.active_operations),
            )

            self.snapshots.append(snapshot)
            return snapshot

    async def start_snapshot_loop(self):
        """Start periodic snapshot collection."""
        if self._running:
            return

        self._running = True
        self._snapshot_task = asyncio.create_task(self._snapshot_loop())
        logger.info("Profiler snapshot loop started")

    async def stop_snapshot_loop(self):
        """Stop snapshot collection."""
        self._running = False
        if self._snapshot_task:
            self._snapshot_task.cancel()
            try:
                await self._snapshot_task
            except asyncio.CancelledError:
                pass
        logger.info("Profiler snapshot loop stopped")

    async def _snapshot_loop(self):
        """Background loop for taking snapshots."""
        while self._running:
            try:
                await asyncio.sleep(self.snapshot_interval_seconds)
                self.take_snapshot()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Snapshot loop error: {e}")

    def reset_stats(self):
        """Reset all statistics."""
        with self._lock:
            for op in OperationType:
                self.operation_stats[op] = OperationStats(operation_type=op)
            self.completed_operations.clear()
            self.slow_operations.clear()
            self.error_traces.clear()
            self.operation_times.clear()
            self.snapshots.clear()

    def get_profiling_report(self) -> Dict[str, Any]:
        """Generate a comprehensive profiling report."""
        with self._lock:
            return {
                'level': self.level.value,
                'total_operations': sum(s.count for s in self.operation_stats.values()),
                'active_operations': len(self.active_operations),
                'throughput_ops': self.get_throughput(),
                'latency_percentiles': self.get_latency_percentiles(),
                'operation_stats': self.get_stats(),
                'slow_operations_count': len(self.slow_operations),
                'slow_threshold_ms': self.slow_threshold_ms,
                'recent_slow_operations': self.get_slow_operations(5),
                'error_count': sum(s.error_count for s in self.operation_stats.values()),
                'recent_errors': self.get_error_traces(5),
                'snapshot_count': len(self.snapshots),
            }


class _NoOpContext:
    """No-op context for when profiling is disabled."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def add_metadata(self, key: str, value: Any):
        pass


def profile_function(
    profiler: PerformanceProfiler,
    operation_type: OperationType = OperationType.CUSTOM
):
    """Decorator to profile a function."""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with profiler.profile(
                operation_type,
                operation_id=f"{func.__name__}:{time.time()}",
                function=func.__name__,
            ):
                return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with profiler.profile(
                operation_type,
                operation_id=f"{func.__name__}:{time.time()}",
                function=func.__name__,
            ):
                return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class FlameGraphProfiler:
    """
    Collects data for flame graph visualization.
    """

    def __init__(self, profiler: PerformanceProfiler):
        self.profiler = profiler
        self.stacks: Dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def record_stack(self, stack: List[str], duration_ms: float):
        """Record a call stack."""
        stack_key = ";".join(stack)
        with self._lock:
            self.stacks[stack_key] += int(duration_ms)

    def export_folded(self) -> str:
        """Export stacks in folded format for flamegraph tools."""
        with self._lock:
            lines = []
            for stack, count in sorted(self.stacks.items()):
                lines.append(f"{stack} {count}")
            return "\n".join(lines)

    def clear(self):
        """Clear collected stacks."""
        with self._lock:
            self.stacks.clear()
