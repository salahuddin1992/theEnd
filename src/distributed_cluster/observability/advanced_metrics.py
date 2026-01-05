"""
Advanced Metrics System - نظام المقاييس المتقدم
================================================

نظام مقاييس متقدم يشمل:
- Request/Response Metrics مع Middleware
- Business Metrics (SLA/SLO)
- API Performance Metrics
- Custom Metric Aggregation
- Real-time Analytics
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import wraps
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    List,
    Optional,
    Tuple,
    TypeVar,
)


class MetricAggregationType(str, Enum):
    """أنواع التجميع."""

    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    RATE = "rate"  # per second
    PERCENTILE = "percentile"


@dataclass
class SlidingWindowConfig:
    """إعدادات النافذة المنزلقة."""

    window_size: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    bucket_size: timedelta = field(default_factory=lambda: timedelta(seconds=10))
    max_buckets: int = 30


@dataclass
class MetricDataPoint:
    """نقطة بيانات مقياس."""

    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


class SlidingWindowCounter:
    """
    عداد بنافذة منزلقة.

    يحتفظ بالبيانات ضمن نافذة زمنية محددة.
    """

    def __init__(self, config: Optional[SlidingWindowConfig] = None):
        self.config = config or SlidingWindowConfig()
        self._buckets: Deque[Tuple[float, float]] = deque()
        self._lock = threading.Lock()
        self._bucket_size_seconds = self.config.bucket_size.total_seconds()
        self._window_size_seconds = self.config.window_size.total_seconds()

    def add(self, value: float = 1.0) -> None:
        """إضافة قيمة."""
        now = time.time()
        bucket_key = now // self._bucket_size_seconds

        with self._lock:
            # إزالة البيانات القديمة
            cutoff = now - self._window_size_seconds
            while self._buckets and self._buckets[0][0] < cutoff:
                self._buckets.popleft()

            # إضافة أو تحديث bucket الحالي
            if self._buckets and self._buckets[-1][0] // self._bucket_size_seconds == bucket_key:
                old_time, old_val = self._buckets.pop()
                self._buckets.append((old_time, old_val + value))
            else:
                self._buckets.append((now, value))

    def get_sum(self) -> float:
        """مجموع القيم في النافذة."""
        now = time.time()
        cutoff = now - self._window_size_seconds

        with self._lock:
            return sum(v for t, v in self._buckets if t >= cutoff)

    def get_rate(self) -> float:
        """معدل القيم في الثانية."""
        total = self.get_sum()
        return total / self._window_size_seconds

    def get_count(self) -> int:
        """عدد العناصر في النافذة."""
        now = time.time()
        cutoff = now - self._window_size_seconds

        with self._lock:
            return sum(1 for t, _ in self._buckets if t >= cutoff)


# =============================================================================
# Request Metrics
# =============================================================================


@dataclass
class RequestMetrics:
    """مقاييس طلب واحد."""

    method: str
    path: str
    status_code: int
    duration_seconds: float
    request_size_bytes: int = 0
    response_size_bytes: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = field(default_factory=dict)


class RequestMetricsCollector:
    """
    جامع مقاييس الطلبات.

    يجمع ويحلل مقاييس HTTP requests.
    """

    def __init__(self, max_history: int = 10000):
        self._history: Deque[RequestMetrics] = deque(maxlen=max_history)
        self._lock = threading.Lock()

        # Sliding window counters للحساب السريع
        self._request_counter = SlidingWindowCounter()
        self._error_counter = SlidingWindowCounter()
        self._latency_sum = SlidingWindowCounter()

        # Per-endpoint metrics
        self._endpoint_metrics: Dict[str, Dict[str, SlidingWindowCounter]] = defaultdict(
            lambda: {
                "requests": SlidingWindowCounter(),
                "errors": SlidingWindowCounter(),
                "latency_sum": SlidingWindowCounter(),
            }
        )

    def record(self, metrics: RequestMetrics) -> None:
        """تسجيل مقاييس طلب."""
        with self._lock:
            self._history.append(metrics)

        # تحديث العدادات
        self._request_counter.add(1)
        self._latency_sum.add(metrics.duration_seconds)

        if metrics.status_code >= 400:
            self._error_counter.add(1)

        # تحديث مقاييس الـ endpoint
        endpoint_key = f"{metrics.method}:{metrics.path}"
        self._endpoint_metrics[endpoint_key]["requests"].add(1)
        self._endpoint_metrics[endpoint_key]["latency_sum"].add(metrics.duration_seconds)

        if metrics.status_code >= 400:
            self._endpoint_metrics[endpoint_key]["errors"].add(1)

    def get_request_rate(self) -> float:
        """معدل الطلبات في الثانية."""
        return self._request_counter.get_rate()

    def get_error_rate(self) -> float:
        """معدل الأخطاء."""
        total = self._request_counter.get_sum()
        if total == 0:
            return 0.0
        return self._error_counter.get_sum() / total

    def get_avg_latency(self) -> float:
        """متوسط زمن الاستجابة."""
        count = self._request_counter.get_sum()
        if count == 0:
            return 0.0
        return self._latency_sum.get_sum() / count

    def get_percentile_latency(self, percentile: float) -> float:
        """حساب percentile لزمن الاستجابة."""
        with self._lock:
            if not self._history:
                return 0.0

            # الحصول على آخر 5 دقائق
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
            latencies = sorted(
                m.duration_seconds for m in self._history if m.timestamp >= cutoff
            )

            if not latencies:
                return 0.0

            index = int(len(latencies) * percentile)
            return latencies[min(index, len(latencies) - 1)]

    def get_endpoint_stats(self) -> Dict[str, Dict[str, float]]:
        """إحصائيات لكل endpoint."""
        stats = {}

        for endpoint, counters in self._endpoint_metrics.items():
            request_count = counters["requests"].get_sum()
            error_count = counters["errors"].get_sum()
            latency_sum = counters["latency_sum"].get_sum()

            stats[endpoint] = {
                "requests_per_second": counters["requests"].get_rate(),
                "total_requests": request_count,
                "error_rate": error_count / request_count if request_count > 0 else 0,
                "avg_latency_ms": (latency_sum / request_count * 1000) if request_count > 0 else 0,
            }

        return stats

    def get_summary(self) -> Dict[str, Any]:
        """ملخص شامل."""
        return {
            "request_rate": self.get_request_rate(),
            "error_rate": self.get_error_rate(),
            "avg_latency_ms": self.get_avg_latency() * 1000,
            "p50_latency_ms": self.get_percentile_latency(0.5) * 1000,
            "p90_latency_ms": self.get_percentile_latency(0.9) * 1000,
            "p99_latency_ms": self.get_percentile_latency(0.99) * 1000,
            "endpoints": self.get_endpoint_stats(),
        }


# =============================================================================
# SLA/SLO Metrics
# =============================================================================


class SLOType(str, Enum):
    """أنواع SLO."""

    AVAILABILITY = "availability"  # نسبة التوفر
    LATENCY = "latency"  # زمن الاستجابة
    ERROR_RATE = "error_rate"  # معدل الأخطاء
    THROUGHPUT = "throughput"  # معدل النقل


@dataclass
class SLODefinition:
    """تعريف SLO."""

    name: str
    slo_type: SLOType
    target: float  # القيمة المستهدفة
    window: timedelta = field(default_factory=lambda: timedelta(days=30))
    description: str = ""

    # للـ latency
    percentile: float = 0.99  # p99 by default

    # للتنبيهات
    alert_threshold: float = 0.95  # تنبيه عند 95% من الهدف


@dataclass
class SLOStatus:
    """حالة SLO."""

    definition: SLODefinition
    current_value: float
    target: float
    compliance: float  # 0.0 - 1.0
    budget_remaining: float  # Error budget remaining
    is_meeting_target: bool
    trend: str  # "improving", "stable", "degrading"
    last_updated: datetime = field(default_factory=datetime.utcnow)


class SLOMonitor:
    """
    مراقب SLO/SLA.

    يتتبع ويحلل الالتزام بـ SLOs.
    """

    def __init__(self, request_metrics: RequestMetricsCollector):
        self._slos: Dict[str, SLODefinition] = {}
        self._request_metrics = request_metrics
        self._history: Dict[str, Deque[Tuple[datetime, float]]] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        self._lock = threading.Lock()

    def register_slo(self, slo: SLODefinition) -> None:
        """تسجيل SLO."""
        self._slos[slo.name] = slo

    def unregister_slo(self, name: str) -> None:
        """إلغاء تسجيل SLO."""
        self._slos.pop(name, None)

    def _calculate_availability(self) -> float:
        """حساب التوفر."""
        error_rate = self._request_metrics.get_error_rate()
        return 1.0 - error_rate

    def _calculate_latency_compliance(self, target: float, percentile: float) -> float:
        """حساب الالتزام بزمن الاستجابة."""
        actual = self._request_metrics.get_percentile_latency(percentile)
        if actual <= target:
            return 1.0
        return target / actual

    def _calculate_error_rate_compliance(self, target: float) -> float:
        """حساب الالتزام بمعدل الأخطاء."""
        actual = self._request_metrics.get_error_rate()
        if actual <= target:
            return 1.0
        return target / actual if actual > 0 else 1.0

    def _calculate_throughput_compliance(self, target: float) -> float:
        """حساب الالتزام بمعدل النقل."""
        actual = self._request_metrics.get_request_rate()
        if actual >= target:
            return 1.0
        return actual / target if target > 0 else 1.0

    def get_slo_status(self, name: str) -> Optional[SLOStatus]:
        """الحصول على حالة SLO."""
        if name not in self._slos:
            return None

        slo = self._slos[name]
        now = datetime.now(timezone.utc)

        # حساب القيمة الحالية
        if slo.slo_type == SLOType.AVAILABILITY:
            current_value = self._calculate_availability()
            compliance = current_value / slo.target if slo.target > 0 else 1.0

        elif slo.slo_type == SLOType.LATENCY:
            current_value = self._request_metrics.get_percentile_latency(slo.percentile)
            compliance = self._calculate_latency_compliance(slo.target, slo.percentile)

        elif slo.slo_type == SLOType.ERROR_RATE:
            current_value = self._request_metrics.get_error_rate()
            compliance = self._calculate_error_rate_compliance(slo.target)

        elif slo.slo_type == SLOType.THROUGHPUT:
            current_value = self._request_metrics.get_request_rate()
            compliance = self._calculate_throughput_compliance(slo.target)

        else:
            current_value = 0.0
            compliance = 0.0

        # حساب الـ budget المتبقي
        budget_remaining = max(0, 1.0 - (1.0 - compliance))

        # تحديد الاتجاه
        with self._lock:
            history = self._history[name]
            history.append((now, compliance))

            if len(history) >= 2:
                recent = [c for _, c in list(history)[-10:]]
                old = [c for _, c in list(history)[-20:-10]]

                if old:
                    recent_avg = sum(recent) / len(recent)
                    old_avg = sum(old) / len(old)

                    if recent_avg > old_avg * 1.02:
                        trend = "improving"
                    elif recent_avg < old_avg * 0.98:
                        trend = "degrading"
                    else:
                        trend = "stable"
                else:
                    trend = "stable"
            else:
                trend = "stable"

        is_meeting = current_value >= slo.target if slo.slo_type in [
            SLOType.AVAILABILITY, SLOType.THROUGHPUT
        ] else current_value <= slo.target

        return SLOStatus(
            definition=slo,
            current_value=current_value,
            target=slo.target,
            compliance=min(1.0, compliance),
            budget_remaining=budget_remaining,
            is_meeting_target=is_meeting,
            trend=trend,
        )

    def get_all_slo_statuses(self) -> Dict[str, SLOStatus]:
        """الحصول على كل حالات SLOs."""
        return {name: self.get_slo_status(name) for name in self._slos if self.get_slo_status(name)}

    def get_summary(self) -> Dict[str, Any]:
        """ملخص SLOs."""
        statuses = self.get_all_slo_statuses()

        return {
            "total_slos": len(statuses),
            "meeting_target": sum(1 for s in statuses.values() if s.is_meeting_target),
            "at_risk": sum(1 for s in statuses.values() if s.budget_remaining < 0.2),
            "slos": {
                name: {
                    "type": status.definition.slo_type.value,
                    "current": status.current_value,
                    "target": status.target,
                    "compliance": status.compliance,
                    "meeting_target": status.is_meeting_target,
                    "trend": status.trend,
                }
                for name, status in statuses.items()
            },
        }


# =============================================================================
# Business Metrics
# =============================================================================


@dataclass
class BusinessMetric:
    """مقياس عمل."""

    name: str
    value: float
    unit: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class BusinessMetricsCollector:
    """
    جامع مقاييس العمل.

    يجمع المقاييس المتعلقة بالعمل مثل:
    - عدد المهام المنجزة
    - وقت الانتظار
    - تكلفة الموارد
    """

    def __init__(self):
        self._metrics: Dict[str, Deque[BusinessMetric]] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        self._counters: Dict[str, SlidingWindowCounter] = defaultdict(SlidingWindowCounter)
        self._lock = threading.Lock()

    def record(self, name: str, value: float, unit: str = "", **labels) -> None:
        """تسجيل مقياس."""
        metric = BusinessMetric(
            name=name,
            value=value,
            unit=unit,
            labels=labels,
        )

        with self._lock:
            self._metrics[name].append(metric)
            self._counters[name].add(value)

    def increment(self, name: str, value: float = 1.0) -> None:
        """زيادة عداد."""
        self._counters[name].add(value)

    def get_rate(self, name: str) -> float:
        """معدل المقياس في الثانية."""
        return self._counters[name].get_rate()

    def get_sum(self, name: str) -> float:
        """مجموع المقياس."""
        return self._counters[name].get_sum()

    def get_recent(self, name: str, minutes: int = 5) -> List[BusinessMetric]:
        """الحصول على المقاييس الأخيرة."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        with self._lock:
            return [m for m in self._metrics[name] if m.timestamp >= cutoff]

    def get_summary(self) -> Dict[str, Any]:
        """ملخص المقاييس."""
        summary = {}

        for name, counter in self._counters.items():
            summary[name] = {
                "sum": counter.get_sum(),
                "rate": counter.get_rate(),
            }

        return summary


# =============================================================================
# Metrics Aggregator
# =============================================================================


class MetricsAggregator:
    """
    مجمع المقاييس الرئيسي.

    يجمع كل المقاييس من مصادر مختلفة.
    """

    def __init__(self):
        self.request_metrics = RequestMetricsCollector()
        self.business_metrics = BusinessMetricsCollector()
        self.slo_monitor = SLOMonitor(self.request_metrics)

        self._custom_metrics: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def register_custom_metric(self, name: str, collector: Any) -> None:
        """تسجيل مقياس مخصص."""
        with self._lock:
            self._custom_metrics[name] = collector

    def get_all_metrics(self) -> Dict[str, Any]:
        """الحصول على كل المقاييس."""
        return {
            "request_metrics": self.request_metrics.get_summary(),
            "business_metrics": self.business_metrics.get_summary(),
            "slo_status": self.slo_monitor.get_summary(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def export_prometheus(self) -> str:
        """تصدير بصيغة Prometheus."""
        lines = []
        now_ms = int(time.time() * 1000)

        # Request metrics
        req = self.request_metrics.get_summary()
        lines.append("# HELP http_request_rate_per_second HTTP request rate")
        lines.append("# TYPE http_request_rate_per_second gauge")
        lines.append(f'http_request_rate_per_second {req["request_rate"]:.6f} {now_ms}')

        lines.append("# HELP http_error_rate HTTP error rate")
        lines.append("# TYPE http_error_rate gauge")
        lines.append(f'http_error_rate {req["error_rate"]:.6f} {now_ms}')

        lines.append("# HELP http_request_latency_ms HTTP request latency")
        lines.append("# TYPE http_request_latency_ms gauge")
        lines.append(f'http_request_latency_ms{{quantile="0.5"}} {req["p50_latency_ms"]:.6f} {now_ms}')
        lines.append(f'http_request_latency_ms{{quantile="0.9"}} {req["p90_latency_ms"]:.6f} {now_ms}')
        lines.append(f'http_request_latency_ms{{quantile="0.99"}} {req["p99_latency_ms"]:.6f} {now_ms}')

        # Endpoint metrics
        for endpoint, stats in req.get("endpoints", {}).items():
            method, path = endpoint.split(":", 1) if ":" in endpoint else ("GET", endpoint)
            path.replace("/", "_").replace("{", "").replace("}", "")

            lines.append(
                f'http_endpoint_requests_total{{method="{method}",path="{path}"}} '
                f'{stats["total_requests"]:.0f} {now_ms}'
            )

        # SLO metrics
        slo_summary = self.slo_monitor.get_summary()
        for name, slo in slo_summary.get("slos", {}).items():
            lines.append(
                f'slo_compliance{{name="{name}",type="{slo["type"]}"}} '
                f'{slo["compliance"]:.6f} {now_ms}'
            )

        # Business metrics
        for name, stats in self.business_metrics.get_summary().items():
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f'business_{safe_name}_sum {stats["sum"]:.6f} {now_ms}')
            lines.append(f'business_{safe_name}_rate {stats["rate"]:.6f} {now_ms}')

        return "\n".join(lines)


# =============================================================================
# FastAPI Middleware
# =============================================================================


def create_metrics_middleware(aggregator: MetricsAggregator):
    """
    إنشاء middleware لـ FastAPI.

    الاستخدام:
        from fastapi import FastAPI
        app = FastAPI()

        aggregator = MetricsAggregator()
        app.middleware("http")(create_metrics_middleware(aggregator))
    """

    async def metrics_middleware(request, call_next):
        start_time = time.time()

        # الحصول على حجم الطلب
        request_size = 0
        if hasattr(request, "headers"):
            content_length = request.headers.get("content-length")
            if content_length:
                request_size = int(content_length)

        # تنفيذ الطلب
        response = await call_next(request)

        # حساب المدة
        duration = time.time() - start_time

        # الحصول على حجم الاستجابة
        response_size = 0
        if hasattr(response, "headers"):
            content_length = response.headers.get("content-length")
            if content_length:
                response_size = int(content_length)

        # تسجيل المقاييس
        metrics = RequestMetrics(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_seconds=duration,
            request_size_bytes=request_size,
            response_size_bytes=response_size,
        )

        aggregator.request_metrics.record(metrics)

        return response

    return metrics_middleware


# =============================================================================
# Decorators
# =============================================================================


T = TypeVar("T")


def track_latency(name: str, aggregator: Optional[MetricsAggregator] = None):
    """
    Decorator لتتبع زمن التنفيذ.

    الاستخدام:
        @track_latency("my_function")
        def my_function():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start
                if aggregator:
                    aggregator.business_metrics.record(
                        f"{name}_duration_seconds", duration, "seconds"
                    )

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.time() - start
                if aggregator:
                    aggregator.business_metrics.record(
                        f"{name}_duration_seconds", duration, "seconds"
                    )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def track_calls(name: str, aggregator: Optional[MetricsAggregator] = None):
    """
    Decorator لتتبع عدد الاستدعاءات.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if aggregator:
                aggregator.business_metrics.increment(f"{name}_calls_total")
            return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if aggregator:
                aggregator.business_metrics.increment(f"{name}_calls_total")
            return await func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# =============================================================================
# Default SLOs
# =============================================================================


def create_default_slos() -> List[SLODefinition]:
    """إنشاء SLOs افتراضية."""
    return [
        SLODefinition(
            name="api_availability",
            slo_type=SLOType.AVAILABILITY,
            target=0.999,  # 99.9% availability
            description="API يجب أن يكون متاحاً 99.9% من الوقت",
        ),
        SLODefinition(
            name="api_latency_p99",
            slo_type=SLOType.LATENCY,
            target=1.0,  # 1 second
            percentile=0.99,
            description="99% من الطلبات يجب أن تُنجز في أقل من ثانية",
        ),
        SLODefinition(
            name="api_error_rate",
            slo_type=SLOType.ERROR_RATE,
            target=0.01,  # 1% max errors
            description="معدل الأخطاء يجب أن يكون أقل من 1%",
        ),
        SLODefinition(
            name="job_throughput",
            slo_type=SLOType.THROUGHPUT,
            target=100.0,  # 100 jobs/second minimum
            description="النظام يجب أن يعالج 100 مهمة في الثانية على الأقل",
        ),
    ]


# =============================================================================
# Global Instance
# =============================================================================


_aggregator: Optional[MetricsAggregator] = None


def get_metrics_aggregator() -> MetricsAggregator:
    """الحصول على مجمع المقاييس العام."""
    global _aggregator
    if _aggregator is None:
        _aggregator = MetricsAggregator()
        # تسجيل SLOs الافتراضية
        for slo in create_default_slos():
            _aggregator.slo_monitor.register_slo(slo)
    return _aggregator


def reset_metrics_aggregator() -> None:
    """إعادة تعيين مجمع المقاييس."""
    global _aggregator
    _aggregator = None
