"""
Metrics Collection - جمع المقاييس
====================================

مقاييس النظام للمراقبة:

**Jobs:**
- queue_time: وقت الانتظار في الطابور
- execution_time: وقت التنفيذ
- success_rate: نسبة النجاح
- retry_count: عدد المحاولات

**Workers:**
- cpu_utilization: استخدام CPU
- memory_utilization: استخدام الذاكرة
- gpu_utilization: استخدام GPU
- heartbeat_latency: تأخر الـ heartbeat

**Scheduler:**
- scheduling_time: وقت اتخاذ قرار الجدولة
- queue_depth: عمق الطابور
- lease_expirations: انتهاءات الـ leases

يدعم:
- In-memory metrics (للـ dashboard)
- Prometheus export (مستقبلاً)
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class MetricType(str, Enum):
    """أنواع المقاييس."""
    COUNTER = "counter"      # عداد تراكمي (مثل عدد requests)
    GAUGE = "gauge"          # قيمة حالية (مثل CPU %)
    HISTOGRAM = "histogram"  # توزيع (مثل response time)
    SUMMARY = "summary"      # ملخص مع percentiles


@dataclass
class MetricValue:
    """قيمة مقياس."""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class HistogramBucket:
    """Bucket للـ histogram."""
    le: float  # less than or equal
    count: int = 0


class Histogram:
    """
    Histogram لتتبع توزيع القيم.

    مفيد لـ:
    - Response times
    - Queue wait times
    - Execution durations
    """

    DEFAULT_BUCKETS = [
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0,
        2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, float('inf')
    ]

    def __init__(self, name: str, buckets: Optional[List[float]] = None):
        self.name = name
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        self._counts = [0] * len(self.buckets)
        self._sum = 0.0
        self._count = 0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        """تسجيل قيمة."""
        with self._lock:
            self._sum += value
            self._count += 1

            for i, bucket in enumerate(self.buckets):
                if value <= bucket:
                    self._counts[i] += 1

    def get_buckets(self) -> List[tuple[float, int]]:
        """الحصول على الـ buckets."""
        with self._lock:
            return list(zip(self.buckets, self._counts))

    def get_percentile(self, p: float) -> float:
        """
        حساب percentile تقريبي.

        Args:
            p: Percentile (0.0 - 1.0)
        """
        with self._lock:
            if self._count == 0:
                return 0.0

            target = self._count * p
            cumulative = 0

            for i, count in enumerate(self._counts):
                cumulative += count
                if cumulative >= target:
                    # Linear interpolation
                    lower = self.buckets[i - 1] if i > 0 else 0
                    upper = self.buckets[i]
                    return (lower + upper) / 2

            return self.buckets[-2] if len(self.buckets) > 1 else 0.0

    @property
    def sum(self) -> float:
        """مجموع القيم."""
        return self._sum

    @property
    def count(self) -> int:
        """عدد القيم."""
        return self._count

    @property
    def mean(self) -> float:
        """المتوسط."""
        if self._count == 0:
            return 0.0
        return self._sum / self._count


class MetricsCollector:
    """
    جامع المقاييس الرئيسي.

    يجمع ويخزن المقاييس للمراقبة.
    """

    def __init__(self):
        self._counters: Dict[str, Dict[tuple, int]] = defaultdict(lambda: defaultdict(int))
        self._gauges: Dict[str, Dict[tuple, float]] = defaultdict(dict)
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()

        # Pre-defined histograms
        self._init_default_histograms()

    def _init_default_histograms(self) -> None:
        """تهيئة histograms افتراضية."""
        # Job timing histograms
        self._histograms["job_queue_time_seconds"] = Histogram(
            "job_queue_time_seconds",
            [0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600]
        )
        self._histograms["job_execution_time_seconds"] = Histogram(
            "job_execution_time_seconds",
            [1, 5, 10, 30, 60, 300, 600, 1800, 3600, 7200]
        )

        # Scheduler timing
        self._histograms["scheduler_decision_time_seconds"] = Histogram(
            "scheduler_decision_time_seconds",
            [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1]
        )

        # Worker heartbeat latency
        self._histograms["worker_heartbeat_latency_seconds"] = Histogram(
            "worker_heartbeat_latency_seconds",
            [0.01, 0.05, 0.1, 0.5, 1, 5, 10]
        )

    def _labels_to_tuple(self, labels: Optional[Dict[str, str]] = None) -> tuple:
        """تحويل labels إلى tuple للـ hashing."""
        if not labels:
            return ()
        return tuple(sorted(labels.items()))

    # ==================== Counter ====================

    def inc(
        self,
        name: str,
        value: int = 1,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """زيادة counter."""
        key = self._labels_to_tuple(labels)
        with self._lock:
            self._counters[name][key] += value

    def get_counter(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> int:
        """الحصول على قيمة counter."""
        key = self._labels_to_tuple(labels)
        return self._counters.get(name, {}).get(key, 0)

    # ==================== Gauge ====================

    def set(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """تعيين قيمة gauge."""
        key = self._labels_to_tuple(labels)
        with self._lock:
            self._gauges[name][key] = value

    def get_gauge(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> float:
        """الحصول على قيمة gauge."""
        key = self._labels_to_tuple(labels)
        return self._gauges.get(name, {}).get(key, 0.0)

    # ==================== Histogram ====================

    def observe(
        self,
        name: str,
        value: float,
    ) -> None:
        """تسجيل قيمة في histogram."""
        if name not in self._histograms:
            self._histograms[name] = Histogram(name)
        self._histograms[name].observe(value)

    def get_histogram(self, name: str) -> Optional[Histogram]:
        """الحصول على histogram."""
        return self._histograms.get(name)

    # ==================== Convenience Methods ====================

    def job_submitted(self) -> None:
        """تسجيل job submitted."""
        self.inc("jobs_submitted_total")

    def job_completed(self, success: bool, execution_time: float, queue_time: float) -> None:
        """تسجيل job completed."""
        status = "success" if success else "failed"
        self.inc("jobs_completed_total", labels={"status": status})

        self.observe("job_execution_time_seconds", execution_time)
        self.observe("job_queue_time_seconds", queue_time)

    def job_retried(self) -> None:
        """تسجيل job retry."""
        self.inc("jobs_retried_total")

    def worker_registered(self) -> None:
        """تسجيل worker registration."""
        self.inc("workers_registered_total")

    def worker_heartbeat(self, worker_id: str, latency: float) -> None:
        """تسجيل worker heartbeat."""
        self.inc("worker_heartbeats_total", labels={"worker_id": worker_id})
        self.observe("worker_heartbeat_latency_seconds", latency)

    def worker_offline(self, worker_id: str) -> None:
        """تسجيل worker went offline."""
        self.inc("workers_offline_total", labels={"worker_id": worker_id})

    def scheduler_decision(self, decision_time: float, jobs_scheduled: int) -> None:
        """تسجيل scheduler decision."""
        self.observe("scheduler_decision_time_seconds", decision_time)
        self.inc("scheduler_decisions_total")
        self.inc("jobs_scheduled_total", value=jobs_scheduled)

    def lease_expired(self) -> None:
        """تسجيل lease expiration."""
        self.inc("leases_expired_total")

    def update_cluster_gauges(
        self,
        total_workers: int,
        online_workers: int,
        pending_jobs: int,
        running_jobs: int,
        total_cpu: float,
        available_cpu: float,
        total_memory_gb: float,
        available_memory_gb: float,
        total_gpus: int,
        available_gpus: int,
    ) -> None:
        """تحديث مقاييس الكلاستر."""
        self.set("cluster_workers_total", total_workers)
        self.set("cluster_workers_online", online_workers)
        self.set("cluster_jobs_pending", pending_jobs)
        self.set("cluster_jobs_running", running_jobs)
        self.set("cluster_cpu_total", total_cpu)
        self.set("cluster_cpu_available", available_cpu)
        self.set("cluster_memory_total_gb", total_memory_gb)
        self.set("cluster_memory_available_gb", available_memory_gb)
        self.set("cluster_gpus_total", total_gpus)
        self.set("cluster_gpus_available", available_gpus)

    # ==================== Export ====================

    def get_all_metrics(self) -> Dict:
        """الحصول على كل المقاييس."""
        metrics = {
            "counters": {},
            "gauges": {},
            "histograms": {},
        }

        with self._lock:
            # Counters
            for name, values in self._counters.items():
                metrics["counters"][name] = {
                    str(labels): value for labels, value in values.items()
                }

            # Gauges
            for name, values in self._gauges.items():
                metrics["gauges"][name] = {
                    str(labels): value for labels, value in values.items()
                }

            # Histograms
            for name, hist in self._histograms.items():
                metrics["histograms"][name] = {
                    "buckets": hist.get_buckets(),
                    "sum": hist.sum,
                    "count": hist.count,
                    "mean": hist.mean,
                    "p50": hist.get_percentile(0.5),
                    "p90": hist.get_percentile(0.9),
                    "p99": hist.get_percentile(0.99),
                }

        return metrics

    def reset(self) -> None:
        """إعادة تعيين كل المقاييس."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._init_default_histograms()


# Global metrics collector instance
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """الحصول على مجمّع المقاييس العام."""
    return _metrics
