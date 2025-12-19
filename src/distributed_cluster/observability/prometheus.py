"""
Prometheus Metrics Exporter
===========================

تصدير المقاييس بصيغة Prometheus:
- مقاييس الكلاستر
- مقاييس المهام
- مقاييس العمال
- مقاييس الأداء
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Prometheus Metric Types
# =============================================================================

class PrometheusMetric:
    """Base class for Prometheus metrics."""

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
    ):
        self.name = name
        self.help_text = help_text
        self.labels = labels or []

    def format_labels(self, label_values: Dict[str, str]) -> str:
        """تنسيق التسميات."""
        if not label_values:
            return ""
        pairs = [f'{k}="{v}"' for k, v in sorted(label_values.items())]
        return "{" + ",".join(pairs) + "}"

    def format(self) -> str:
        """تنسيق الـ metric."""
        raise NotImplementedError


class Counter(PrometheusMetric):
    """Prometheus Counter."""

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
    ):
        super().__init__(name, help_text, labels)
        self._values: Dict[str, float] = {}  # label_key -> value

    def inc(self, labels: Optional[Dict[str, str]] = None, value: float = 1.0) -> None:
        """زيادة العداد."""
        key = self._labels_key(labels)
        self._values[key] = self._values.get(key, 0) + value

    def _labels_key(self, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return ""
        return "|".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def format(self) -> str:
        """تنسيق للتصدير."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} counter",
        ]

        if not self._values:
            lines.append(f"{self.name} 0")
        else:
            for label_key, value in self._values.items():
                labels_str = ""
                if label_key:
                    pairs = label_key.split("|")
                    labels_str = "{" + ",".join(f'{p.split("=")[0]}="{p.split("=")[1]}"' for p in pairs) + "}"
                lines.append(f"{self.name}{labels_str} {value}")

        return "\n".join(lines)


class Gauge(PrometheusMetric):
    """Prometheus Gauge."""

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
    ):
        super().__init__(name, help_text, labels)
        self._values: Dict[str, float] = {}

    def set(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """تعيين القيمة."""
        key = self._labels_key(labels)
        self._values[key] = value

    def inc(self, labels: Optional[Dict[str, str]] = None, value: float = 1.0) -> None:
        """زيادة."""
        key = self._labels_key(labels)
        self._values[key] = self._values.get(key, 0) + value

    def dec(self, labels: Optional[Dict[str, str]] = None, value: float = 1.0) -> None:
        """نقصان."""
        key = self._labels_key(labels)
        self._values[key] = self._values.get(key, 0) - value

    def _labels_key(self, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return ""
        return "|".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def format(self) -> str:
        """تنسيق للتصدير."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} gauge",
        ]

        if not self._values:
            lines.append(f"{self.name} 0")
        else:
            for label_key, value in self._values.items():
                labels_str = ""
                if label_key:
                    pairs = label_key.split("|")
                    labels_str = "{" + ",".join(f'{p.split("=")[0]}="{p.split("=")[1]}"' for p in pairs) + "}"
                lines.append(f"{self.name}{labels_str} {value}")

        return "\n".join(lines)


class Histogram(PrometheusMetric):
    """Prometheus Histogram."""

    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')]

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None,
    ):
        super().__init__(name, help_text, labels)
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        if self.buckets[-1] != float('inf'):
            self.buckets.append(float('inf'))

        # Per-label data
        self._data: Dict[str, Dict[str, Any]] = {}

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """تسجيل قيمة."""
        key = self._labels_key(labels)

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

    def _labels_key(self, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return ""
        return "|".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def format(self) -> str:
        """تنسيق للتصدير."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} histogram",
        ]

        for label_key, data in self._data.items():
            base_labels = ""
            if label_key:
                pairs = label_key.split("|")
                base_labels = ",".join(f'{p.split("=")[0]}="{p.split("=")[1]}"' for p in pairs) + ","

            # Buckets
            cumulative = 0
            for bucket in self.buckets:
                cumulative += data["buckets"][bucket]
                le = "+Inf" if bucket == float('inf') else str(bucket)
                lines.append(f'{self.name}_bucket{{{base_labels}le="{le}"}} {cumulative}')

            # Sum and count
            if base_labels:
                base_labels = "{" + base_labels.rstrip(",") + "}"
            lines.append(f"{self.name}_sum{base_labels} {data['sum']}")
            lines.append(f"{self.name}_count{base_labels} {data['count']}")

        if not self._data:
            # Empty histogram
            for bucket in self.buckets:
                le = "+Inf" if bucket == float('inf') else str(bucket)
                lines.append(f'{self.name}_bucket{{le="{le}"}} 0')
            lines.append(f"{self.name}_sum 0")
            lines.append(f"{self.name}_count 0")

        return "\n".join(lines)


class Summary(PrometheusMetric):
    """Prometheus Summary."""

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
        quantiles: Optional[List[float]] = None,
    ):
        super().__init__(name, help_text, labels)
        self.quantiles = quantiles or [0.5, 0.9, 0.99]
        self._data: Dict[str, List[float]] = {}

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """تسجيل قيمة."""
        key = self._labels_key(labels)
        if key not in self._data:
            self._data[key] = []
        self._data[key].append(value)

    def _labels_key(self, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return ""
        return "|".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def _calculate_quantile(self, values: List[float], q: float) -> float:
        """حساب الـ quantile."""
        if not values:
            return 0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * q)
        return sorted_values[min(index, len(sorted_values) - 1)]

    def format(self) -> str:
        """تنسيق للتصدير."""
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} summary",
        ]

        for label_key, values in self._data.items():
            base_labels = ""
            if label_key:
                pairs = label_key.split("|")
                base_labels = ",".join(f'{p.split("=")[0]}="{p.split("=")[1]}"' for p in pairs) + ","

            # Quantiles
            for q in self.quantiles:
                qv = self._calculate_quantile(values, q)
                lines.append(f'{self.name}{{{base_labels}quantile="{q}"}} {qv}')

            # Sum and count
            if base_labels:
                base_labels = "{" + base_labels.rstrip(",") + "}"
            lines.append(f"{self.name}_sum{base_labels} {sum(values)}")
            lines.append(f"{self.name}_count{base_labels} {len(values)}")

        return "\n".join(lines)


# =============================================================================
# Prometheus Registry
# =============================================================================

class PrometheusRegistry:
    """
    سجل المقاييس.

    يجمع كل المقاييس ويصدرها.
    """

    def __init__(self, namespace: str = "nebula"):
        self.namespace = namespace
        self._metrics: Dict[str, PrometheusMetric] = {}
        self._collectors: List[Callable[[], None]] = []

    def register(self, metric: PrometheusMetric) -> PrometheusMetric:
        """تسجيل metric."""
        full_name = f"{self.namespace}_{metric.name}"
        metric.name = full_name
        self._metrics[full_name] = metric
        return metric

    def counter(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
    ) -> Counter:
        """إنشاء counter."""
        counter = Counter(name, help_text, labels)
        self.register(counter)
        return counter

    def gauge(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
    ) -> Gauge:
        """إنشاء gauge."""
        gauge = Gauge(name, help_text, labels)
        self.register(gauge)
        return gauge

    def histogram(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None,
    ) -> Histogram:
        """إنشاء histogram."""
        histogram = Histogram(name, help_text, labels, buckets)
        self.register(histogram)
        return histogram

    def summary(
        self,
        name: str,
        help_text: str,
        labels: Optional[List[str]] = None,
        quantiles: Optional[List[float]] = None,
    ) -> Summary:
        """إنشاء summary."""
        summary = Summary(name, help_text, labels, quantiles)
        self.register(summary)
        return summary

    def add_collector(self, collector: Callable[[], None]) -> None:
        """إضافة collector."""
        self._collectors.append(collector)

    def collect(self) -> str:
        """جمع كل المقاييس."""
        # Run collectors
        for collector in self._collectors:
            try:
                collector()
            except Exception as e:
                logger.error(f"Collector error: {e}")

        # Format all metrics
        lines = []
        for metric in self._metrics.values():
            lines.append(metric.format())
            lines.append("")

        return "\n".join(lines)


# =============================================================================
# Nebula Metrics
# =============================================================================

class NebulaMetrics:
    """
    مقاييس NebulaCompute.

    مجموعة المقاييس الخاصة بالنظام.
    """

    def __init__(self, registry: Optional[PrometheusRegistry] = None):
        self.registry = registry or PrometheusRegistry()

        # Cluster metrics
        self.workers_total = self.registry.gauge(
            "workers_total",
            "Total number of workers",
            ["status"]
        )

        self.workers_resources = self.registry.gauge(
            "workers_resources",
            "Worker resources",
            ["worker_id", "resource"]
        )

        # Job metrics
        self.jobs_total = self.registry.counter(
            "jobs_total",
            "Total number of jobs",
            ["status"]
        )

        self.jobs_active = self.registry.gauge(
            "jobs_active",
            "Number of active jobs",
            ["status"]
        )

        self.job_duration_seconds = self.registry.histogram(
            "job_duration_seconds",
            "Job execution duration in seconds",
            ["status"],
            buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600]
        )

        self.job_queue_time_seconds = self.registry.histogram(
            "job_queue_time_seconds",
            "Time spent in queue before execution",
            buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300]
        )

        # Scheduler metrics
        self.scheduler_cycles_total = self.registry.counter(
            "scheduler_cycles_total",
            "Total scheduler cycles"
        )

        self.scheduler_cycle_duration_seconds = self.registry.histogram(
            "scheduler_cycle_duration_seconds",
            "Scheduler cycle duration",
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
        )

        self.scheduler_pending_jobs = self.registry.gauge(
            "scheduler_pending_jobs",
            "Number of pending jobs"
        )

        # API metrics
        self.api_requests_total = self.registry.counter(
            "api_requests_total",
            "Total API requests",
            ["method", "endpoint", "status"]
        )

        self.api_request_duration_seconds = self.registry.histogram(
            "api_request_duration_seconds",
            "API request duration",
            ["method", "endpoint"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )

        # gRPC metrics
        self.grpc_requests_total = self.registry.counter(
            "grpc_requests_total",
            "Total gRPC requests",
            ["method", "status"]
        )

        self.grpc_request_duration_seconds = self.registry.histogram(
            "grpc_request_duration_seconds",
            "gRPC request duration",
            ["method"]
        )

        # WebSocket metrics
        self.websocket_connections = self.registry.gauge(
            "websocket_connections",
            "Active WebSocket connections"
        )

        self.websocket_messages_total = self.registry.counter(
            "websocket_messages_total",
            "Total WebSocket messages",
            ["direction"]  # sent, received
        )

        # Resource usage
        self.cluster_cpu_usage = self.registry.gauge(
            "cluster_cpu_usage",
            "Cluster CPU usage (cores)"
        )

        self.cluster_memory_usage_bytes = self.registry.gauge(
            "cluster_memory_usage_bytes",
            "Cluster memory usage (bytes)"
        )

        self.cluster_gpu_usage = self.registry.gauge(
            "cluster_gpu_usage",
            "Cluster GPU usage (count)"
        )

        # Retry metrics
        self.job_retries_total = self.registry.counter(
            "job_retries_total",
            "Total job retries",
            ["reason"]
        )

        self.dead_letter_queue_size = self.registry.gauge(
            "dead_letter_queue_size",
            "Number of jobs in dead letter queue"
        )

        # Lease metrics
        self.leases_active = self.registry.gauge(
            "leases_active",
            "Active leases"
        )

        self.leases_expired_total = self.registry.counter(
            "leases_expired_total",
            "Total expired leases"
        )

        # Quota metrics
        self.quota_usage_percent = self.registry.gauge(
            "quota_usage_percent",
            "Quota usage percentage",
            ["scope", "scope_id", "metric"]
        )

    def collect(self) -> str:
        """جمع المقاييس."""
        return self.registry.collect()

    # Helper methods
    def record_job_completed(
        self,
        status: str,
        duration: float,
        queue_time: float,
    ) -> None:
        """تسجيل اكتمال مهمة."""
        self.jobs_total.inc({"status": status})
        self.job_duration_seconds.observe(duration, {"status": status})
        self.job_queue_time_seconds.observe(queue_time)

    def record_api_request(
        self,
        method: str,
        endpoint: str,
        status: int,
        duration: float,
    ) -> None:
        """تسجيل طلب API."""
        self.api_requests_total.inc({
            "method": method,
            "endpoint": endpoint,
            "status": str(status)
        })
        self.api_request_duration_seconds.observe(duration, {
            "method": method,
            "endpoint": endpoint
        })

    def update_cluster_status(
        self,
        workers_online: int,
        workers_busy: int,
        workers_offline: int,
        pending_jobs: int,
        running_jobs: int,
        cpu_used: float,
        memory_used_bytes: int,
        gpu_used: int,
    ) -> None:
        """تحديث حالة الكلاستر."""
        self.workers_total.set(workers_online, {"status": "online"})
        self.workers_total.set(workers_busy, {"status": "busy"})
        self.workers_total.set(workers_offline, {"status": "offline"})
        self.scheduler_pending_jobs.set(pending_jobs)
        self.jobs_active.set(pending_jobs, {"status": "pending"})
        self.jobs_active.set(running_jobs, {"status": "running"})
        self.cluster_cpu_usage.set(cpu_used)
        self.cluster_memory_usage_bytes.set(memory_used_bytes)
        self.cluster_gpu_usage.set(gpu_used)


# =============================================================================
# FastAPI Integration
# =============================================================================

def create_metrics_endpoint(metrics: NebulaMetrics):
    """
    إنشاء endpoint لـ Prometheus.

    Usage:
        from fastapi import FastAPI, Response
        from distributed_cluster.observability.prometheus import NebulaMetrics, create_metrics_endpoint

        app = FastAPI()
        metrics = NebulaMetrics()

        @app.get("/metrics")
        async def get_metrics():
            return create_metrics_endpoint(metrics)
    """
    from fastapi.responses import PlainTextResponse

    content = metrics.collect()
    return PlainTextResponse(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


# =============================================================================
# Middleware
# =============================================================================

class PrometheusMiddleware:
    """
    Middleware لتسجيل مقاييس HTTP.

    Usage:
        from fastapi import FastAPI
        from distributed_cluster.observability.prometheus import NebulaMetrics, PrometheusMiddleware

        app = FastAPI()
        metrics = NebulaMetrics()
        app.add_middleware(PrometheusMiddleware, metrics=metrics)
    """

    def __init__(self, app, metrics: NebulaMetrics):
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.time() - start_time
            method = scope.get("method", "UNKNOWN")
            path = scope.get("path", "/")

            self.metrics.record_api_request(
                method=method,
                endpoint=path,
                status=status_code,
                duration=duration,
            )
