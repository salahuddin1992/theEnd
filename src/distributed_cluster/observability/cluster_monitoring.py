# -*- coding: utf-8 -*-
"""
Comprehensive Cluster Monitoring System
========================================

Unified monitoring for distributed cluster with:
- Prometheus-compatible metrics for all cluster operations
- Task execution time tracking
- Node health monitoring
- Queue depth metrics
- Error rate tracking
- Centralized logging with multiple log levels

Usage:
    from distributed_cluster.observability.cluster_monitoring import (
        ClusterMonitor,
        get_cluster_monitor,
        setup_cluster_monitoring,
    )

    # Initialize
    monitor = setup_cluster_monitoring(
        service_name="nebula-cluster",
        log_level=LogLevel.INFO,
        enable_prometheus=True,
    )

    # Record metrics
    monitor.record_task_started("task-123", "worker-1")
    monitor.record_task_completed("task-123", "worker-1", duration=5.2, success=True)
    monitor.record_node_health("worker-1", healthy=True, cpu=45.2, memory=60.1)

    # Get Prometheus metrics
    metrics_output = monitor.get_prometheus_metrics()
"""

from __future__ import annotations

import asyncio
import functools
import json
import sys
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# =============================================================================
# Log Levels
# =============================================================================


class LogLevel(IntEnum):
    """Log levels for the centralized logging system."""

    TRACE = 5
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    FATAL = 60

    @classmethod
    def from_string(cls, level: str) -> "LogLevel":
        """Convert string to LogLevel."""
        mapping = {
            "trace": cls.TRACE,
            "debug": cls.DEBUG,
            "info": cls.INFO,
            "warning": cls.WARNING,
            "warn": cls.WARNING,
            "error": cls.ERROR,
            "critical": cls.CRITICAL,
            "fatal": cls.FATAL,
        }
        return mapping.get(level.lower(), cls.INFO)


# =============================================================================
# Prometheus Metric Types
# =============================================================================


class MetricType(str, Enum):
    """Prometheus metric types."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricLabel:
    """Label for a metric."""

    name: str
    value: str


class PrometheusCounter:
    """Thread-safe Prometheus counter metric."""

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
        namespace: str = "cluster",
    ):
        self.name = f"{namespace}_{name}" if namespace else name
        self.help_text = help_text
        self.labels = labels or []
        self._values: Dict[Tuple[str, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment the counter."""
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] += value

    def _labels_to_key(self, labels: Optional[Dict[str, str]] = None) -> Tuple[str, ...]:
        """Convert labels dict to hashable key."""
        if not labels:
            return ()
        return tuple(labels.get(lbl, "") for lbl in self.labels)

    def collect(self) -> str:
        """Collect metrics in Prometheus format."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} counter",
        ]

        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0")
            else:
                for label_values, value in self._values.items():
                    if label_values:
                        label_str = ",".join(
                            f'{self.labels[i]}="{v}"'
                            for i, v in enumerate(label_values)
                            if v
                        )
                        lines.append(f"{self.name}{{{label_str}}} {value}")
                    else:
                        lines.append(f"{self.name} {value}")

        return "\n".join(lines)


class PrometheusGauge:
    """Thread-safe Prometheus gauge metric."""

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
        namespace: str = "cluster",
    ):
        self.name = f"{namespace}_{name}" if namespace else name
        self.help_text = help_text
        self.labels = labels or []
        self._values: Dict[Tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set the gauge value."""
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] = value

    def inc(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment the gauge."""
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0) + value

    def dec(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Decrement the gauge."""
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0) - value

    def _labels_to_key(self, labels: Optional[Dict[str, str]] = None) -> Tuple[str, ...]:
        """Convert labels dict to hashable key."""
        if not labels:
            return ()
        return tuple(labels.get(lbl, "") for lbl in self.labels)

    def collect(self) -> str:
        """Collect metrics in Prometheus format."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} gauge",
        ]

        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0")
            else:
                for label_values, value in self._values.items():
                    if label_values:
                        label_str = ",".join(
                            f'{self.labels[i]}="{v}"'
                            for i, v in enumerate(label_values)
                            if v
                        )
                        lines.append(f"{self.name}{{{label_str}}} {value}")
                    else:
                        lines.append(f"{self.name} {value}")

        return "\n".join(lines)


class PrometheusHistogram:
    """Thread-safe Prometheus histogram metric."""

    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float("inf")]

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None,
        namespace: str = "cluster",
    ):
        self.name = f"{namespace}_{name}" if namespace else name
        self.help_text = help_text
        self.labels = labels or []
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        if self.buckets[-1] != float("inf"):
            self.buckets.append(float("inf"))

        self._data: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Observe a value."""
        key = self._labels_to_key(labels)

        with self._lock:
            if key not in self._data:
                self._data[key] = {
                    "sum": 0.0,
                    "count": 0,
                    "buckets": {b: 0 for b in self.buckets},
                }

            data = self._data[key]
            data["sum"] += value
            data["count"] += 1

            for bucket in self.buckets:
                if value <= bucket:
                    data["buckets"][bucket] += 1

    def _labels_to_key(self, labels: Optional[Dict[str, str]] = None) -> Tuple[str, ...]:
        """Convert labels dict to hashable key."""
        if not labels:
            return ()
        return tuple(labels.get(lbl, "") for lbl in self.labels)

    def collect(self) -> str:
        """Collect metrics in Prometheus format."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} histogram",
        ]

        with self._lock:
            if not self._data:
                for bucket in self.buckets:
                    le = "+Inf" if bucket == float("inf") else str(bucket)
                    lines.append(f'{self.name}_bucket{{le="{le}"}} 0')
                lines.append(f"{self.name}_sum 0")
                lines.append(f"{self.name}_count 0")
            else:
                for label_values, data in self._data.items():
                    base_labels = ""
                    if label_values:
                        base_labels = ",".join(
                            f'{self.labels[i]}="{v}"'
                            for i, v in enumerate(label_values)
                            if v
                        ) + ","

                    cumulative = 0
                    for bucket in self.buckets:
                        cumulative += data["buckets"][bucket]
                        le = "+Inf" if bucket == float("inf") else str(bucket)
                        lines.append(f'{self.name}_bucket{{{base_labels}le="{le}"}} {cumulative}')

                    label_suffix = ""
                    if base_labels:
                        label_suffix = "{" + base_labels.rstrip(",") + "}"
                    lines.append(f"{self.name}_sum{label_suffix} {data['sum']}")
                    lines.append(f"{self.name}_count{label_suffix} {data['count']}")

        return "\n".join(lines)


class PrometheusSummary:
    """Thread-safe Prometheus summary metric."""

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
        quantiles: Optional[List[float]] = None,
        max_age_seconds: int = 600,
        namespace: str = "cluster",
    ):
        self.name = f"{namespace}_{name}" if namespace else name
        self.help_text = help_text
        self.labels = labels or []
        self.quantiles = quantiles or [0.5, 0.9, 0.95, 0.99]
        self.max_age_seconds = max_age_seconds

        self._data: Dict[Tuple[str, ...], List[Tuple[float, float]]] = defaultdict(list)
        self._lock = threading.Lock()

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Observe a value."""
        key = self._labels_to_key(labels)
        now = time.time()

        with self._lock:
            self._data[key].append((now, value))
            # Clean old values
            cutoff = now - self.max_age_seconds
            self._data[key] = [(t, v) for t, v in self._data[key] if t > cutoff]

    def _labels_to_key(self, labels: Optional[Dict[str, str]] = None) -> Tuple[str, ...]:
        """Convert labels dict to hashable key."""
        if not labels:
            return ()
        return tuple(labels.get(lbl, "") for lbl in self.labels)

    def _calculate_quantile(self, values: List[float], q: float) -> float:
        """Calculate quantile value."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        idx = int(len(sorted_values) * q)
        return sorted_values[min(idx, len(sorted_values) - 1)]

    def collect(self) -> str:
        """Collect metrics in Prometheus format."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} summary",
        ]

        with self._lock:
            for label_values, data in self._data.items():
                values = [v for _, v in data]
                if not values:
                    continue

                base_labels = ""
                if label_values:
                    base_labels = ",".join(
                        f'{self.labels[i]}="{v}"'
                        for i, v in enumerate(label_values)
                        if v
                    ) + ","

                for q in self.quantiles:
                    qv = self._calculate_quantile(values, q)
                    lines.append(f'{self.name}{{{base_labels}quantile="{q}"}} {qv}')

                label_suffix = ""
                if base_labels:
                    label_suffix = "{" + base_labels.rstrip(",") + "}"
                lines.append(f"{self.name}_sum{label_suffix} {sum(values)}")
                lines.append(f"{self.name}_count{label_suffix} {len(values)}")

        return "\n".join(lines)


# =============================================================================
# Centralized Logging System
# =============================================================================


@dataclass
class LogRecord:
    """Structured log record."""

    timestamp: datetime
    level: LogLevel
    logger_name: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)
    exception: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    node_id: Optional[str] = None
    task_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "timestamp": self.timestamp.isoformat() + "Z",
            "level": self.level.name,
            "logger": self.logger_name,
            "message": self.message,
        }

        if self.context:
            result["context"] = self.context
        if self.extra:
            result["extra"] = self.extra
        if self.exception:
            result["exception"] = self.exception
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.span_id:
            result["span_id"] = self.span_id
        if self.node_id:
            result["node_id"] = self.node_id
        if self.task_id:
            result["task_id"] = self.task_id

        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class LogHandler:
    """Base class for log handlers."""

    def __init__(self, level: LogLevel = LogLevel.DEBUG):
        self.level = level

    def emit(self, record: LogRecord) -> None:
        """Emit a log record."""
        raise NotImplementedError

    def flush(self) -> None:
        """Flush any buffered output."""
        pass

    def close(self) -> None:
        """Close the handler."""
        pass


class ConsoleLogHandler(LogHandler):
    """Console log handler with optional color support."""

    COLORS = {
        LogLevel.TRACE: "\033[37m",      # White
        LogLevel.DEBUG: "\033[36m",      # Cyan
        LogLevel.INFO: "\033[32m",       # Green
        LogLevel.WARNING: "\033[33m",    # Yellow
        LogLevel.ERROR: "\033[31m",      # Red
        LogLevel.CRITICAL: "\033[35m",   # Magenta
        LogLevel.FATAL: "\033[41m",      # Red background
    }
    RESET = "\033[0m"

    def __init__(
        self,
        level: LogLevel = LogLevel.DEBUG,
        use_colors: bool = True,
        json_output: bool = False,
        stream: Any = None,
    ):
        super().__init__(level)
        self.use_colors = use_colors and sys.stdout.isatty()
        self.json_output = json_output
        self.stream = stream or sys.stderr
        self._lock = threading.Lock()

    def emit(self, record: LogRecord) -> None:
        """Emit a log record to console."""
        if record.level < self.level:
            return

        if self.json_output:
            output = record.to_json()
        else:
            output = self._format_human_readable(record)

        with self._lock:
            self.stream.write(output + "\n")
            self.stream.flush()

    def _format_human_readable(self, record: LogRecord) -> str:
        """Format record for human reading."""
        timestamp = record.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level_name = record.level.name.ljust(8)

        if self.use_colors:
            color = self.COLORS.get(record.level, "")
            level_name = f"{color}{level_name}{self.RESET}"

        parts = [f"{timestamp} [{level_name}] {record.logger_name}: {record.message}"]

        if record.node_id:
            parts.append(f"node={record.node_id}")
        if record.task_id:
            parts.append(f"task={record.task_id}")
        if record.trace_id:
            parts.append(f"trace={record.trace_id}")
        if record.context:
            parts.append(f"ctx={record.context}")
        if record.extra:
            parts.append(f"extra={record.extra}")
        if record.exception:
            parts.append(f"\n{record.exception}")

        return " ".join(parts)


class FileLogHandler(LogHandler):
    """File log handler with rotation support."""

    def __init__(
        self,
        filepath: Union[str, Path],
        level: LogLevel = LogLevel.DEBUG,
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB
        backup_count: int = 5,
        json_output: bool = True,
    ):
        super().__init__(level)
        self.filepath = Path(filepath)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.json_output = json_output
        self._lock = threading.Lock()
        self._file: Optional[Any] = None

        # Ensure directory exists
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._open()

    def _open(self) -> None:
        """Open the log file."""
        self._file = open(self.filepath, "a", encoding="utf-8")

    def _close(self) -> None:
        """Close the log file."""
        if self._file:
            self._file.close()
            self._file = None

    def emit(self, record: LogRecord) -> None:
        """Emit a log record to file."""
        if record.level < self.level:
            return

        if self.json_output:
            output = record.to_json()
        else:
            output = f"{record.timestamp.isoformat()} [{record.level.name}] {record.logger_name}: {record.message}"

        with self._lock:
            if self._should_rotate():
                self._rotate()

            if self._file:
                self._file.write(output + "\n")
                self._file.flush()

    def _should_rotate(self) -> bool:
        """Check if rotation is needed."""
        if not self.filepath.exists():
            return False
        return self.filepath.stat().st_size >= self.max_bytes

    def _rotate(self) -> None:
        """Rotate log files."""
        self._close()

        # Rotate existing files
        for i in range(self.backup_count - 1, 0, -1):
            src = self.filepath.with_suffix(f".{i}.log")
            dst = self.filepath.with_suffix(f".{i + 1}.log")
            if src.exists():
                if i + 1 > self.backup_count:
                    src.unlink()
                else:
                    src.rename(dst)

        # Move current to .1
        if self.filepath.exists():
            self.filepath.rename(self.filepath.with_suffix(".1.log"))

        self._open()

    def flush(self) -> None:
        """Flush the file."""
        with self._lock:
            if self._file:
                self._file.flush()

    def close(self) -> None:
        """Close the handler."""
        with self._lock:
            self._close()


class CentralizedLogger:
    """
    Centralized logging system for distributed cluster.

    Supports multiple handlers, structured logging, and context propagation.
    """

    # Thread-local storage for context
    _context = threading.local()

    def __init__(
        self,
        name: str,
        level: LogLevel = LogLevel.INFO,
        handlers: Optional[List[LogHandler]] = None,
    ):
        self.name = name
        self.level = level
        self.handlers = handlers or []
        self._lock = threading.Lock()

    def add_handler(self, handler: LogHandler) -> None:
        """Add a log handler."""
        with self._lock:
            self.handlers.append(handler)

    def remove_handler(self, handler: LogHandler) -> None:
        """Remove a log handler."""
        with self._lock:
            if handler in self.handlers:
                self.handlers.remove(handler)

    @classmethod
    def set_context(
        cls,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        node_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """Set thread-local context."""
        if not hasattr(cls._context, "data"):
            cls._context.data = {}

        if trace_id:
            cls._context.data["trace_id"] = trace_id
        if span_id:
            cls._context.data["span_id"] = span_id
        if node_id:
            cls._context.data["node_id"] = node_id
        if task_id:
            cls._context.data["task_id"] = task_id
        if extra:
            cls._context.data.update(extra)

    @classmethod
    def clear_context(cls) -> None:
        """Clear thread-local context."""
        cls._context.data = {}

    @classmethod
    def get_context(cls) -> Dict[str, Any]:
        """Get current context."""
        return getattr(cls._context, "data", {})

    @contextmanager
    def context(
        self,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        node_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **extra: Any,
    ):
        """Context manager for setting logging context."""
        old_context = self.get_context().copy()
        self.set_context(trace_id=trace_id, span_id=span_id, node_id=node_id, task_id=task_id, **extra)
        try:
            yield
        finally:
            self._context.data = old_context

    def _log(
        self,
        level: LogLevel,
        message: str,
        exc_info: bool = False,
        **extra: Any,
    ) -> None:
        """Internal logging method."""
        if level < self.level:
            return

        ctx = self.get_context()

        record = LogRecord(
            timestamp=datetime.now(timezone.utc),
            level=level,
            logger_name=self.name,
            message=message,
            context=ctx.get("extra", {}),
            extra=extra,
            trace_id=ctx.get("trace_id"),
            span_id=ctx.get("span_id"),
            node_id=ctx.get("node_id"),
            task_id=ctx.get("task_id"),
        )

        if exc_info:
            import traceback
            record.exception = traceback.format_exc()

        for handler in self.handlers:
            try:
                handler.emit(record)
            except Exception:
                pass  # Don't let handler errors break logging

    def trace(self, message: str, **extra: Any) -> None:
        """Log at TRACE level."""
        self._log(LogLevel.TRACE, message, **extra)

    def debug(self, message: str, **extra: Any) -> None:
        """Log at DEBUG level."""
        self._log(LogLevel.DEBUG, message, **extra)

    def info(self, message: str, **extra: Any) -> None:
        """Log at INFO level."""
        self._log(LogLevel.INFO, message, **extra)

    def warning(self, message: str, **extra: Any) -> None:
        """Log at WARNING level."""
        self._log(LogLevel.WARNING, message, **extra)

    def error(self, message: str, exc_info: bool = False, **extra: Any) -> None:
        """Log at ERROR level."""
        self._log(LogLevel.ERROR, message, exc_info=exc_info, **extra)

    def critical(self, message: str, exc_info: bool = False, **extra: Any) -> None:
        """Log at CRITICAL level."""
        self._log(LogLevel.CRITICAL, message, exc_info=exc_info, **extra)

    def fatal(self, message: str, exc_info: bool = False, **extra: Any) -> None:
        """Log at FATAL level."""
        self._log(LogLevel.FATAL, message, exc_info=exc_info, **extra)

    def exception(self, message: str, **extra: Any) -> None:
        """Log exception with traceback."""
        self._log(LogLevel.ERROR, message, exc_info=True, **extra)


# =============================================================================
# Cluster Metrics Registry
# =============================================================================


class ClusterMetricsRegistry:
    """
    Registry for all cluster Prometheus metrics.

    Provides pre-defined metrics for:
    - Task execution
    - Node health
    - Queue depth
    - Error rates
    """

    def __init__(self, namespace: str = "cluster"):
        self.namespace = namespace
        self._metrics: Dict[str, Any] = {}
        self._lock = threading.Lock()

        # Initialize all metrics
        self._init_task_metrics()
        self._init_node_metrics()
        self._init_queue_metrics()
        self._init_error_metrics()
        self._init_system_metrics()

    def _init_task_metrics(self) -> None:
        """Initialize task-related metrics."""
        # Task execution time histogram
        self._metrics["task_execution_duration_seconds"] = PrometheusHistogram(
            name="task_execution_duration_seconds",
            help_text="Task execution duration in seconds",
            labels=["task_type", "worker_id", "status"],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
            namespace=self.namespace,
        )

        # Task queue time (time waiting before execution)
        self._metrics["task_queue_duration_seconds"] = PrometheusHistogram(
            name="task_queue_duration_seconds",
            help_text="Time tasks spend waiting in queue before execution",
            labels=["task_type", "priority"],
            buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
            namespace=self.namespace,
        )

        # Task counts
        self._metrics["tasks_submitted_total"] = PrometheusCounter(
            name="tasks_submitted_total",
            help_text="Total number of tasks submitted",
            labels=["task_type", "user_id"],
            namespace=self.namespace,
        )

        self._metrics["tasks_completed_total"] = PrometheusCounter(
            name="tasks_completed_total",
            help_text="Total number of tasks completed",
            labels=["task_type", "status", "worker_id"],
            namespace=self.namespace,
        )

        self._metrics["tasks_running"] = PrometheusGauge(
            name="tasks_running",
            help_text="Number of currently running tasks",
            labels=["task_type", "worker_id"],
            namespace=self.namespace,
        )

        self._metrics["tasks_retried_total"] = PrometheusCounter(
            name="tasks_retried_total",
            help_text="Total number of task retries",
            labels=["task_type", "reason"],
            namespace=self.namespace,
        )

    def _init_node_metrics(self) -> None:
        """Initialize node health metrics."""
        # Node status
        self._metrics["node_health_status"] = PrometheusGauge(
            name="node_health_status",
            help_text="Node health status (1=healthy, 0=unhealthy)",
            labels=["node_id", "node_type"],
            namespace=self.namespace,
        )

        # Node resource usage
        self._metrics["node_cpu_usage_percent"] = PrometheusGauge(
            name="node_cpu_usage_percent",
            help_text="Node CPU usage percentage",
            labels=["node_id"],
            namespace=self.namespace,
        )

        self._metrics["node_memory_usage_percent"] = PrometheusGauge(
            name="node_memory_usage_percent",
            help_text="Node memory usage percentage",
            labels=["node_id"],
            namespace=self.namespace,
        )

        self._metrics["node_memory_usage_bytes"] = PrometheusGauge(
            name="node_memory_usage_bytes",
            help_text="Node memory usage in bytes",
            labels=["node_id"],
            namespace=self.namespace,
        )

        self._metrics["node_disk_usage_percent"] = PrometheusGauge(
            name="node_disk_usage_percent",
            help_text="Node disk usage percentage",
            labels=["node_id", "mount_point"],
            namespace=self.namespace,
        )

        self._metrics["node_gpu_usage_percent"] = PrometheusGauge(
            name="node_gpu_usage_percent",
            help_text="Node GPU usage percentage",
            labels=["node_id", "gpu_id"],
            namespace=self.namespace,
        )

        # Node availability
        self._metrics["nodes_total"] = PrometheusGauge(
            name="nodes_total",
            help_text="Total number of nodes in the cluster",
            labels=["node_type", "status"],
            namespace=self.namespace,
        )

        # Heartbeat metrics
        self._metrics["node_heartbeat_latency_seconds"] = PrometheusHistogram(
            name="node_heartbeat_latency_seconds",
            help_text="Latency of node heartbeats",
            labels=["node_id"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
            namespace=self.namespace,
        )

        self._metrics["node_last_heartbeat_timestamp"] = PrometheusGauge(
            name="node_last_heartbeat_timestamp",
            help_text="Timestamp of last node heartbeat",
            labels=["node_id"],
            namespace=self.namespace,
        )

        # Node uptime
        self._metrics["node_uptime_seconds"] = PrometheusGauge(
            name="node_uptime_seconds",
            help_text="Node uptime in seconds",
            labels=["node_id"],
            namespace=self.namespace,
        )

    def _init_queue_metrics(self) -> None:
        """Initialize queue depth metrics."""
        # Queue depth
        self._metrics["queue_depth"] = PrometheusGauge(
            name="queue_depth",
            help_text="Current depth of the task queue",
            labels=["queue_name", "priority"],
            namespace=self.namespace,
        )

        # Queue capacity
        self._metrics["queue_capacity"] = PrometheusGauge(
            name="queue_capacity",
            help_text="Maximum capacity of the task queue",
            labels=["queue_name"],
            namespace=self.namespace,
        )

        # Queue saturation
        self._metrics["queue_saturation_ratio"] = PrometheusGauge(
            name="queue_saturation_ratio",
            help_text="Queue saturation (depth/capacity)",
            labels=["queue_name"],
            namespace=self.namespace,
        )

        # Queue wait time
        self._metrics["queue_wait_time_seconds"] = PrometheusSummary(
            name="queue_wait_time_seconds",
            help_text="Time items spend waiting in queue",
            labels=["queue_name"],
            quantiles=[0.5, 0.9, 0.95, 0.99],
            namespace=self.namespace,
        )

        # Queue throughput
        self._metrics["queue_items_processed_total"] = PrometheusCounter(
            name="queue_items_processed_total",
            help_text="Total items processed from queue",
            labels=["queue_name"],
            namespace=self.namespace,
        )

        self._metrics["queue_items_added_total"] = PrometheusCounter(
            name="queue_items_added_total",
            help_text="Total items added to queue",
            labels=["queue_name"],
            namespace=self.namespace,
        )

    def _init_error_metrics(self) -> None:
        """Initialize error rate metrics."""
        # Error counts
        self._metrics["errors_total"] = PrometheusCounter(
            name="errors_total",
            help_text="Total number of errors",
            labels=["error_type", "component", "severity"],
            namespace=self.namespace,
        )

        # Error rate
        self._metrics["error_rate"] = PrometheusGauge(
            name="error_rate",
            help_text="Current error rate (errors per second)",
            labels=["component"],
            namespace=self.namespace,
        )

        # Task failure rate
        self._metrics["task_failure_rate"] = PrometheusGauge(
            name="task_failure_rate",
            help_text="Task failure rate (failures per total)",
            labels=["task_type"],
            namespace=self.namespace,
        )

        # Timeout errors
        self._metrics["timeouts_total"] = PrometheusCounter(
            name="timeouts_total",
            help_text="Total number of timeout errors",
            labels=["operation", "component"],
            namespace=self.namespace,
        )

        # Connection errors
        self._metrics["connection_errors_total"] = PrometheusCounter(
            name="connection_errors_total",
            help_text="Total number of connection errors",
            labels=["target", "error_type"],
            namespace=self.namespace,
        )

        # Retry exhausted errors
        self._metrics["retry_exhausted_total"] = PrometheusCounter(
            name="retry_exhausted_total",
            help_text="Total number of operations that exhausted retries",
            labels=["operation"],
            namespace=self.namespace,
        )

    def _init_system_metrics(self) -> None:
        """Initialize system-wide metrics."""
        # Cluster info
        self._metrics["cluster_info"] = PrometheusGauge(
            name="cluster_info",
            help_text="Cluster information",
            labels=["version", "cluster_id"],
            namespace=self.namespace,
        )

        # Scheduler metrics
        self._metrics["scheduler_cycle_duration_seconds"] = PrometheusHistogram(
            name="scheduler_cycle_duration_seconds",
            help_text="Duration of scheduler cycles",
            labels=["scheduler_id"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
            namespace=self.namespace,
        )

        self._metrics["scheduler_decisions_total"] = PrometheusCounter(
            name="scheduler_decisions_total",
            help_text="Total number of scheduler decisions",
            labels=["scheduler_id", "decision_type"],
            namespace=self.namespace,
        )

        # API metrics
        self._metrics["api_requests_total"] = PrometheusCounter(
            name="api_requests_total",
            help_text="Total API requests",
            labels=["method", "endpoint", "status_code"],
            namespace=self.namespace,
        )

        self._metrics["api_request_duration_seconds"] = PrometheusHistogram(
            name="api_request_duration_seconds",
            help_text="API request duration",
            labels=["method", "endpoint"],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
            namespace=self.namespace,
        )

        # Lease metrics
        self._metrics["leases_active"] = PrometheusGauge(
            name="leases_active",
            help_text="Number of active leases",
            labels=[],
            namespace=self.namespace,
        )

        self._metrics["leases_expired_total"] = PrometheusCounter(
            name="leases_expired_total",
            help_text="Total number of expired leases",
            labels=[],
            namespace=self.namespace,
        )

    def get_metric(self, name: str) -> Any:
        """Get a metric by name."""
        return self._metrics.get(name)

    def collect_all(self) -> str:
        """Collect all metrics in Prometheus format."""
        lines = []
        for metric in self._metrics.values():
            lines.append(metric.collect())
            lines.append("")
        return "\n".join(lines)


# =============================================================================
# Cluster Monitor
# =============================================================================


class ClusterMonitor:
    """
    Comprehensive cluster monitoring system.

    Provides:
    - Prometheus-compatible metrics
    - Centralized logging
    - Task execution tracking
    - Node health monitoring
    - Queue depth metrics
    - Error rate tracking
    """

    def __init__(
        self,
        service_name: str = "distributed-cluster",
        namespace: str = "cluster",
        log_level: LogLevel = LogLevel.INFO,
        log_dir: Optional[str] = None,
        enable_console_logging: bool = True,
        enable_file_logging: bool = True,
        enable_json_logging: bool = True,
    ):
        self.service_name = service_name
        self.namespace = namespace
        self.log_level = log_level

        # Initialize metrics registry
        self.metrics = ClusterMetricsRegistry(namespace=namespace)

        # Initialize logging
        self.logger = CentralizedLogger(name=service_name, level=log_level)

        if enable_console_logging:
            self.logger.add_handler(
                ConsoleLogHandler(
                    level=log_level,
                    use_colors=True,
                    json_output=False,
                )
            )

        if enable_file_logging and log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)

            # Main application log
            self.logger.add_handler(
                FileLogHandler(
                    filepath=log_path / "cluster.log",
                    level=log_level,
                    json_output=enable_json_logging,
                )
            )

            # Error log
            self.logger.add_handler(
                FileLogHandler(
                    filepath=log_path / "cluster-error.log",
                    level=LogLevel.ERROR,
                    json_output=enable_json_logging,
                )
            )

        # Internal state
        self._task_start_times: Dict[str, float] = {}
        self._task_queue_times: Dict[str, float] = {}
        self._node_start_times: Dict[str, float] = {}
        self._error_window: List[Tuple[float, str]] = []
        self._error_window_size = 60  # 1 minute window
        self._lock = threading.Lock()

        self.logger.info(
            "Cluster monitor initialized",
            service=service_name,
            namespace=namespace,
        )

    # =========================================================================
    # Task Metrics
    # =========================================================================

    def record_task_submitted(
        self,
        task_id: str,
        task_type: str = "default",
        user_id: str = "unknown",
        priority: int = 0,
    ) -> None:
        """Record a task submission."""
        with self._lock:
            self._task_queue_times[task_id] = time.time()

        self.metrics.get_metric("tasks_submitted_total").inc(
            labels={"task_type": task_type, "user_id": user_id}
        )

        self.logger.debug(
            f"Task submitted: {task_id}",
            task_id=task_id,
            task_type=task_type,
            user_id=user_id,
            priority=priority,
        )

    def record_task_started(
        self,
        task_id: str,
        worker_id: str,
        task_type: str = "default",
    ) -> None:
        """Record a task starting execution."""
        now = time.time()

        with self._lock:
            self._task_start_times[task_id] = now

            # Calculate queue time
            if task_id in self._task_queue_times:
                queue_time = now - self._task_queue_times[task_id]
                self.metrics.get_metric("task_queue_duration_seconds").observe(
                    queue_time,
                    labels={"task_type": task_type, "priority": "normal"},
                )

        # Update running tasks gauge
        self.metrics.get_metric("tasks_running").inc(
            labels={"task_type": task_type, "worker_id": worker_id}
        )

        self.logger.info(
            f"Task started: {task_id} on worker {worker_id}",
            task_id=task_id,
            worker_id=worker_id,
            task_type=task_type,
        )

    def record_task_completed(
        self,
        task_id: str,
        worker_id: str,
        duration: Optional[float] = None,
        success: bool = True,
        task_type: str = "default",
        error_message: Optional[str] = None,
    ) -> None:
        """Record a task completion."""
        now = time.time()
        status = "success" if success else "failed"

        # Calculate duration if not provided
        if duration is None:
            with self._lock:
                if task_id in self._task_start_times:
                    duration = now - self._task_start_times[task_id]
                    del self._task_start_times[task_id]
                else:
                    duration = 0.0

        # Clean up queue time tracking
        with self._lock:
            self._task_queue_times.pop(task_id, None)

        # Record metrics
        self.metrics.get_metric("task_execution_duration_seconds").observe(
            duration,
            labels={"task_type": task_type, "worker_id": worker_id, "status": status},
        )

        self.metrics.get_metric("tasks_completed_total").inc(
            labels={"task_type": task_type, "status": status, "worker_id": worker_id}
        )

        self.metrics.get_metric("tasks_running").dec(
            labels={"task_type": task_type, "worker_id": worker_id}
        )

        # Record error if failed
        if not success:
            self.record_error(
                error_type="task_failure",
                component="worker",
                severity="error",
                message=error_message or f"Task {task_id} failed",
            )

        log_func = self.logger.info if success else self.logger.warning
        log_func(
            f"Task completed: {task_id} ({status})",
            task_id=task_id,
            worker_id=worker_id,
            duration=duration,
            success=success,
            task_type=task_type,
        )

    def record_task_retry(
        self,
        task_id: str,
        task_type: str = "default",
        reason: str = "unknown",
        retry_count: int = 1,
    ) -> None:
        """Record a task retry."""
        self.metrics.get_metric("tasks_retried_total").inc(
            labels={"task_type": task_type, "reason": reason}
        )

        self.logger.warning(
            f"Task retry: {task_id} (attempt {retry_count})",
            task_id=task_id,
            task_type=task_type,
            reason=reason,
            retry_count=retry_count,
        )

    # =========================================================================
    # Node Health Metrics
    # =========================================================================

    def record_node_registered(
        self,
        node_id: str,
        node_type: str = "worker",
        hostname: Optional[str] = None,
    ) -> None:
        """Record a node registration."""
        with self._lock:
            self._node_start_times[node_id] = time.time()

        self.metrics.get_metric("node_health_status").set(
            1.0,
            labels={"node_id": node_id, "node_type": node_type},
        )

        self.logger.info(
            f"Node registered: {node_id}",
            node_id=node_id,
            node_type=node_type,
            hostname=hostname,
        )

    def record_node_health(
        self,
        node_id: str,
        healthy: bool = True,
        cpu_percent: Optional[float] = None,
        memory_percent: Optional[float] = None,
        memory_bytes: Optional[int] = None,
        disk_percent: Optional[float] = None,
        gpu_percent: Optional[float] = None,
        node_type: str = "worker",
    ) -> None:
        """Record node health metrics."""
        # Health status
        self.metrics.get_metric("node_health_status").set(
            1.0 if healthy else 0.0,
            labels={"node_id": node_id, "node_type": node_type},
        )

        # Resource usage
        if cpu_percent is not None:
            self.metrics.get_metric("node_cpu_usage_percent").set(
                cpu_percent,
                labels={"node_id": node_id},
            )

        if memory_percent is not None:
            self.metrics.get_metric("node_memory_usage_percent").set(
                memory_percent,
                labels={"node_id": node_id},
            )

        if memory_bytes is not None:
            self.metrics.get_metric("node_memory_usage_bytes").set(
                memory_bytes,
                labels={"node_id": node_id},
            )

        if disk_percent is not None:
            self.metrics.get_metric("node_disk_usage_percent").set(
                disk_percent,
                labels={"node_id": node_id, "mount_point": "/"},
            )

        if gpu_percent is not None:
            self.metrics.get_metric("node_gpu_usage_percent").set(
                gpu_percent,
                labels={"node_id": node_id, "gpu_id": "0"},
            )

        # Update uptime
        with self._lock:
            if node_id in self._node_start_times:
                uptime = time.time() - self._node_start_times[node_id]
                self.metrics.get_metric("node_uptime_seconds").set(
                    uptime,
                    labels={"node_id": node_id},
                )

        if not healthy:
            self.logger.warning(
                f"Node unhealthy: {node_id}",
                node_id=node_id,
                cpu=cpu_percent,
                memory=memory_percent,
            )

    def record_node_heartbeat(
        self,
        node_id: str,
        latency_seconds: float,
    ) -> None:
        """Record a node heartbeat."""
        self.metrics.get_metric("node_heartbeat_latency_seconds").observe(
            latency_seconds,
            labels={"node_id": node_id},
        )

        self.metrics.get_metric("node_last_heartbeat_timestamp").set(
            time.time(),
            labels={"node_id": node_id},
        )

        self.logger.trace(
            f"Node heartbeat: {node_id}",
            node_id=node_id,
            latency=latency_seconds,
        )

    def record_node_offline(
        self,
        node_id: str,
        reason: str = "unknown",
        node_type: str = "worker",
    ) -> None:
        """Record a node going offline."""
        self.metrics.get_metric("node_health_status").set(
            0.0,
            labels={"node_id": node_id, "node_type": node_type},
        )

        self.record_error(
            error_type="node_offline",
            component="cluster",
            severity="warning",
            message=f"Node {node_id} went offline: {reason}",
        )

        self.logger.warning(
            f"Node offline: {node_id}",
            node_id=node_id,
            reason=reason,
        )

    def update_node_counts(
        self,
        total_workers: int,
        healthy_workers: int,
        busy_workers: int,
        offline_workers: int,
    ) -> None:
        """Update aggregate node counts."""
        self.metrics.get_metric("nodes_total").set(
            healthy_workers,
            labels={"node_type": "worker", "status": "healthy"},
        )
        self.metrics.get_metric("nodes_total").set(
            busy_workers,
            labels={"node_type": "worker", "status": "busy"},
        )
        self.metrics.get_metric("nodes_total").set(
            offline_workers,
            labels={"node_type": "worker", "status": "offline"},
        )

    # =========================================================================
    # Queue Metrics
    # =========================================================================

    def record_queue_depth(
        self,
        queue_name: str,
        depth: int,
        priority: str = "normal",
        capacity: Optional[int] = None,
    ) -> None:
        """Record queue depth."""
        self.metrics.get_metric("queue_depth").set(
            depth,
            labels={"queue_name": queue_name, "priority": priority},
        )

        if capacity is not None:
            self.metrics.get_metric("queue_capacity").set(
                capacity,
                labels={"queue_name": queue_name},
            )

            saturation = depth / capacity if capacity > 0 else 0.0
            self.metrics.get_metric("queue_saturation_ratio").set(
                saturation,
                labels={"queue_name": queue_name},
            )

            if saturation > 0.8:
                self.logger.warning(
                    f"Queue {queue_name} nearing capacity",
                    queue=queue_name,
                    depth=depth,
                    capacity=capacity,
                    saturation=saturation,
                )

    def record_queue_item_added(self, queue_name: str) -> None:
        """Record an item added to queue."""
        self.metrics.get_metric("queue_items_added_total").inc(
            labels={"queue_name": queue_name}
        )

    def record_queue_item_processed(
        self,
        queue_name: str,
        wait_time_seconds: float,
    ) -> None:
        """Record an item processed from queue."""
        self.metrics.get_metric("queue_items_processed_total").inc(
            labels={"queue_name": queue_name}
        )

        self.metrics.get_metric("queue_wait_time_seconds").observe(
            wait_time_seconds,
            labels={"queue_name": queue_name},
        )

    # =========================================================================
    # Error Metrics
    # =========================================================================

    def record_error(
        self,
        error_type: str,
        component: str,
        severity: str = "error",
        message: Optional[str] = None,
    ) -> None:
        """Record an error occurrence."""
        self.metrics.get_metric("errors_total").inc(
            labels={
                "error_type": error_type,
                "component": component,
                "severity": severity,
            }
        )

        # Track in error window for rate calculation
        now = time.time()
        with self._lock:
            self._error_window.append((now, component))
            # Clean old errors
            cutoff = now - self._error_window_size
            self._error_window = [(t, c) for t, c in self._error_window if t > cutoff]

            # Update error rate
            component_errors = sum(1 for _, c in self._error_window if c == component)
            rate = component_errors / self._error_window_size
            self.metrics.get_metric("error_rate").set(
                rate,
                labels={"component": component},
            )

        if message:
            log_func = self.logger.error if severity == "error" else self.logger.warning
            log_func(
                message,
                error_type=error_type,
                component=component,
            )

    def record_timeout(
        self,
        operation: str,
        component: str,
        timeout_seconds: float,
    ) -> None:
        """Record a timeout error."""
        self.metrics.get_metric("timeouts_total").inc(
            labels={"operation": operation, "component": component}
        )

        self.record_error(
            error_type="timeout",
            component=component,
            severity="warning",
            message=f"Timeout in {operation} after {timeout_seconds}s",
        )

    def record_connection_error(
        self,
        target: str,
        error_type: str,
        message: Optional[str] = None,
    ) -> None:
        """Record a connection error."""
        self.metrics.get_metric("connection_errors_total").inc(
            labels={"target": target, "error_type": error_type}
        )

        self.record_error(
            error_type="connection_error",
            component="network",
            severity="error",
            message=message or f"Connection error to {target}: {error_type}",
        )

    def record_retry_exhausted(
        self,
        operation: str,
        max_retries: int,
    ) -> None:
        """Record when an operation exhausts all retries."""
        self.metrics.get_metric("retry_exhausted_total").inc(
            labels={"operation": operation}
        )

        self.record_error(
            error_type="retry_exhausted",
            component="retry",
            severity="error",
            message=f"Operation {operation} exhausted {max_retries} retries",
        )

    def update_task_failure_rate(
        self,
        task_type: str,
        success_count: int,
        failure_count: int,
    ) -> None:
        """Update task failure rate gauge."""
        total = success_count + failure_count
        if total > 0:
            rate = failure_count / total
            self.metrics.get_metric("task_failure_rate").set(
                rate,
                labels={"task_type": task_type},
            )

    # =========================================================================
    # Scheduler Metrics
    # =========================================================================

    def record_scheduler_cycle(
        self,
        scheduler_id: str,
        duration_seconds: float,
        tasks_scheduled: int,
    ) -> None:
        """Record a scheduler cycle."""
        self.metrics.get_metric("scheduler_cycle_duration_seconds").observe(
            duration_seconds,
            labels={"scheduler_id": scheduler_id},
        )

        self.metrics.get_metric("scheduler_decisions_total").inc(
            value=tasks_scheduled,
            labels={"scheduler_id": scheduler_id, "decision_type": "schedule"},
        )

        self.logger.debug(
            "Scheduler cycle completed",
            scheduler_id=scheduler_id,
            duration=duration_seconds,
            tasks_scheduled=tasks_scheduled,
        )

    def record_lease_metrics(
        self,
        active_leases: int,
        expired_count: int = 0,
    ) -> None:
        """Record lease metrics."""
        self.metrics.get_metric("leases_active").set(active_leases)

        if expired_count > 0:
            self.metrics.get_metric("leases_expired_total").inc(value=expired_count)

    # =========================================================================
    # API Metrics
    # =========================================================================

    def record_api_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record an API request."""
        self.metrics.get_metric("api_requests_total").inc(
            labels={
                "method": method,
                "endpoint": endpoint,
                "status_code": str(status_code),
            }
        )

        self.metrics.get_metric("api_request_duration_seconds").observe(
            duration_seconds,
            labels={"method": method, "endpoint": endpoint},
        )

        if status_code >= 500:
            self.record_error(
                error_type="api_error",
                component="api",
                severity="error",
                message=f"API error: {method} {endpoint} returned {status_code}",
            )

    # =========================================================================
    # Prometheus Export
    # =========================================================================

    def get_prometheus_metrics(self) -> str:
        """Get all metrics in Prometheus format."""
        return self.metrics.collect_all()

    # =========================================================================
    # Decorators
    # =========================================================================

    def track_task(
        self,
        task_type: str = "default",
        worker_id: Optional[str] = None,
    ):
        """Decorator to track task execution."""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                task_id = str(uuid.uuid4())[:8]
                wid = worker_id or "local"

                self.record_task_started(task_id, wid, task_type)
                start_time = time.time()

                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    self.record_task_completed(
                        task_id, wid, duration=duration, success=True, task_type=task_type
                    )
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    self.record_task_completed(
                        task_id, wid,
                        duration=duration,
                        success=False,
                        task_type=task_type,
                        error_message=str(e),
                    )
                    raise

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                task_id = str(uuid.uuid4())[:8]
                wid = worker_id or "local"

                self.record_task_started(task_id, wid, task_type)
                start_time = time.time()

                try:
                    result = await func(*args, **kwargs)
                    duration = time.time() - start_time
                    self.record_task_completed(
                        task_id, wid, duration=duration, success=True, task_type=task_type
                    )
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    self.record_task_completed(
                        task_id, wid,
                        duration=duration,
                        success=False,
                        task_type=task_type,
                        error_message=str(e),
                    )
                    raise

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return wrapper

        return decorator

    def track_api(self, endpoint: Optional[str] = None):
        """Decorator to track API request metrics."""
        def decorator(func: Callable) -> Callable:
            ep = endpoint or func.__name__

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                status_code = 200

                try:
                    result = func(*args, **kwargs)
                    if hasattr(result, "status_code"):
                        status_code = result.status_code
                    return result
                except Exception:
                    status_code = 500
                    raise
                finally:
                    duration = time.time() - start_time
                    self.record_api_request("POST", ep, status_code, duration)

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                status_code = 200

                try:
                    result = await func(*args, **kwargs)
                    if hasattr(result, "status_code"):
                        status_code = result.status_code
                    return result
                except Exception:
                    status_code = 500
                    raise
                finally:
                    duration = time.time() - start_time
                    self.record_api_request("POST", ep, status_code, duration)

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return wrapper

        return decorator


# =============================================================================
# Global Instance and Factory Functions
# =============================================================================

_cluster_monitor: Optional[ClusterMonitor] = None
_monitor_lock = threading.Lock()


def get_cluster_monitor() -> Optional[ClusterMonitor]:
    """Get the global cluster monitor instance."""
    return _cluster_monitor


def setup_cluster_monitoring(
    service_name: str = "distributed-cluster",
    namespace: str = "cluster",
    log_level: Union[LogLevel, str] = LogLevel.INFO,
    log_dir: Optional[str] = None,
    enable_console_logging: bool = True,
    enable_file_logging: bool = True,
    enable_json_logging: bool = True,
) -> ClusterMonitor:
    """
    Setup cluster monitoring.

    Args:
        service_name: Name of the service
        namespace: Prometheus metrics namespace
        log_level: Logging level (LogLevel enum or string)
        log_dir: Directory for log files
        enable_console_logging: Enable console logging
        enable_file_logging: Enable file logging
        enable_json_logging: Use JSON format for file logs

    Returns:
        Configured ClusterMonitor instance
    """
    global _cluster_monitor

    if isinstance(log_level, str):
        log_level = LogLevel.from_string(log_level)

    with _monitor_lock:
        _cluster_monitor = ClusterMonitor(
            service_name=service_name,
            namespace=namespace,
            log_level=log_level,
            log_dir=log_dir,
            enable_console_logging=enable_console_logging,
            enable_file_logging=enable_file_logging,
            enable_json_logging=enable_json_logging,
        )

    return _cluster_monitor


def shutdown_cluster_monitoring() -> None:
    """Shutdown cluster monitoring and cleanup resources."""
    global _cluster_monitor

    with _monitor_lock:
        if _cluster_monitor:
            for handler in _cluster_monitor.logger.handlers:
                handler.close()
            _cluster_monitor = None


# =============================================================================
# FastAPI Integration
# =============================================================================


def create_monitoring_routes(monitor: ClusterMonitor):
    """
    Create FastAPI routes for monitoring endpoints.

    Usage:
        from fastapi import FastAPI
        from distributed_cluster.observability.cluster_monitoring import (
            setup_cluster_monitoring,
            create_monitoring_routes,
        )

        app = FastAPI()
        monitor = setup_cluster_monitoring()
        monitoring_router = create_monitoring_routes(monitor)
        app.include_router(monitoring_router, prefix="/monitoring")
    """
    from fastapi import APIRouter, Response

    router = APIRouter(tags=["monitoring"])

    @router.get("/metrics")
    async def get_metrics():
        """Get Prometheus metrics."""
        content = monitor.get_prometheus_metrics()
        return Response(
            content=content,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @router.get("/health")
    async def get_health():
        """Get cluster health status."""
        return {"status": "healthy", "service": monitor.service_name}

    @router.get("/ready")
    async def get_ready():
        """Readiness probe."""
        return {"ready": True}

    @router.get("/live")
    async def get_live():
        """Liveness probe."""
        return {"live": True}

    return router


def create_monitoring_middleware(monitor: ClusterMonitor):
    """
    Create ASGI middleware for automatic request monitoring.

    Usage:
        from fastapi import FastAPI
        from distributed_cluster.observability.cluster_monitoring import (
            setup_cluster_monitoring,
            create_monitoring_middleware,
        )

        app = FastAPI()
        monitor = setup_cluster_monitoring()
        app.add_middleware(create_monitoring_middleware(monitor))
    """

    class MonitoringMiddleware:
        def __init__(self, app):
            self.app = app
            self.monitor = monitor

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            start_time = time.time()
            status_code = 500
            method = scope.get("method", "UNKNOWN")
            path = scope.get("path", "/")

            async def send_wrapper(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                duration = time.time() - start_time
                self.monitor.record_api_request(method, path, status_code, duration)

    return MonitoringMiddleware
