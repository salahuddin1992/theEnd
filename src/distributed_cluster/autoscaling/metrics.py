"""
Metrics Collector - جامع المقاييس للتوسع التلقائي
================================================

Metrics Collection System for Auto-Scaling
------------------------------------------

This module collects and aggregates metrics from the cluster to inform
scaling decisions. Supports various metric types and aggregation methods.

يجمع هذا النظام المقاييس من الكلاستر لدعم قرارات التوسع:
- عمق الطابور / Queue depth
- وقت الانتظار / Wait time
- استخدام CPU/GPU/RAM
- معدل الإنتاجية / Throughput rate
- معدل الفشل / Failure rate

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from distributed_cluster.master.state import ClusterState

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """
    أنواع المقاييس المتاحة للتوسع
    Available metric types for scaling decisions
    """

    # Queue Metrics - مقاييس الطابور
    QUEUE_DEPTH = "queue_depth"  # عدد المهام في الانتظار
    QUEUE_WAIT_TIME = "queue_wait_time"  # متوسط وقت الانتظار بالثواني
    QUEUE_GROWTH_RATE = "queue_growth_rate"  # معدل نمو الطابور

    # Resource Metrics - مقاييس الموارد
    CPU_UTILIZATION = "cpu_utilization"  # نسبة استخدام CPU
    MEMORY_UTILIZATION = "memory_utilization"  # نسبة استخدام RAM
    GPU_UTILIZATION = "gpu_utilization"  # نسبة استخدام GPU
    GPU_MEMORY_UTILIZATION = "gpu_memory_utilization"  # نسبة استخدام ذاكرة GPU

    # Worker Metrics - مقاييس العمال
    WORKER_COUNT = "worker_count"  # عدد العمال الحاليين
    HEALTHY_WORKER_COUNT = "healthy_worker_count"  # عدد العمال السليمين
    WORKER_UTILIZATION = "worker_utilization"  # نسبة استخدام العمال

    # Throughput Metrics - مقاييس الإنتاجية
    JOBS_PER_MINUTE = "jobs_per_minute"  # المهام المكتملة في الدقيقة
    JOBS_PER_WORKER = "jobs_per_worker"  # المهام لكل عامل
    COMPLETION_RATE = "completion_rate"  # معدل الإكمال

    # Failure Metrics - مقاييس الفشل
    FAILURE_RATE = "failure_rate"  # نسبة الفشل
    RETRY_RATE = "retry_rate"  # نسبة إعادة المحاولة

    # Cost Metrics - مقاييس التكلفة
    COST_PER_JOB = "cost_per_job"  # التكلفة لكل مهمة
    HOURLY_COST = "hourly_cost"  # التكلفة بالساعة


class AggregationMethod(str, Enum):
    """
    طرق تجميع المقاييس
    Metrics aggregation methods
    """

    AVERAGE = "average"  # المتوسط
    MEDIAN = "median"  # الوسيط
    MIN = "min"  # الأدنى
    MAX = "max"  # الأقصى
    SUM = "sum"  # المجموع
    PERCENTILE_90 = "p90"  # المئين 90
    PERCENTILE_95 = "p95"  # المئين 95
    PERCENTILE_99 = "p99"  # المئين 99
    LATEST = "latest"  # آخر قيمة


@dataclass
class MetricsSample:
    """
    عينة مقياس واحدة
    Single metrics sample
    """

    timestamp: datetime
    metric_type: MetricType
    value: float
    tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس / Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "metric_type": self.metric_type.value,
            "value": self.value,
            "tags": self.tags,
        }


@dataclass
class ResourceMetrics:
    """
    مقاييس الموارد المجمعة
    Aggregated resource metrics
    """

    timestamp: datetime

    # Queue metrics - مقاييس الطابور
    queue_depth: int = 0
    queue_wait_time_avg: float = 0.0
    queue_wait_time_max: float = 0.0
    queue_growth_rate: float = 0.0

    # CPU metrics - مقاييس المعالج
    cpu_utilization_avg: float = 0.0
    cpu_utilization_max: float = 0.0

    # Memory metrics - مقاييس الذاكرة
    memory_utilization_avg: float = 0.0
    memory_utilization_max: float = 0.0
    memory_used_mb: int = 0
    memory_total_mb: int = 0

    # GPU metrics - مقاييس كرت الشاشة
    gpu_utilization_avg: float = 0.0
    gpu_utilization_max: float = 0.0
    gpu_memory_utilization_avg: float = 0.0
    gpu_count_total: int = 0
    gpu_count_available: int = 0

    # Worker metrics - مقاييس العمال
    worker_count: int = 0
    healthy_worker_count: int = 0
    worker_utilization: float = 0.0

    # Throughput metrics - مقاييس الإنتاجية
    jobs_completed_last_minute: int = 0
    jobs_failed_last_minute: int = 0
    jobs_running: int = 0

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس / Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "queue": {
                "depth": self.queue_depth,
                "wait_time_avg": self.queue_wait_time_avg,
                "wait_time_max": self.queue_wait_time_max,
                "growth_rate": self.queue_growth_rate,
            },
            "cpu": {
                "utilization_avg": self.cpu_utilization_avg,
                "utilization_max": self.cpu_utilization_max,
            },
            "memory": {
                "utilization_avg": self.memory_utilization_avg,
                "utilization_max": self.memory_utilization_max,
                "used_mb": self.memory_used_mb,
                "total_mb": self.memory_total_mb,
            },
            "gpu": {
                "utilization_avg": self.gpu_utilization_avg,
                "utilization_max": self.gpu_utilization_max,
                "memory_utilization_avg": self.gpu_memory_utilization_avg,
                "count_total": self.gpu_count_total,
                "count_available": self.gpu_count_available,
            },
            "workers": {
                "count": self.worker_count,
                "healthy_count": self.healthy_worker_count,
                "utilization": self.worker_utilization,
            },
            "throughput": {
                "completed_last_minute": self.jobs_completed_last_minute,
                "failed_last_minute": self.jobs_failed_last_minute,
                "running": self.jobs_running,
            },
        }


class MetricsSource(ABC):
    """
    مصدر المقاييس الأساسي
    Base metrics source interface
    """

    @abstractmethod
    async def collect(self) -> ResourceMetrics:
        """
        جمع المقاييس من المصدر
        Collect metrics from the source
        """
        pass


class ClusterMetricsSource(MetricsSource):
    """
    مصدر المقاييس من حالة الكلاستر
    Metrics source from cluster state
    """

    def __init__(self, cluster_state: ClusterState):
        self.cluster_state = cluster_state
        self._last_queue_depth: int = 0
        self._last_check_time: datetime = datetime.utcnow()
        self._completed_jobs_history: deque[tuple[datetime, int]] = deque(maxlen=60)
        self._failed_jobs_history: deque[tuple[datetime, int]] = deque(maxlen=60)

    async def collect(self) -> ResourceMetrics:
        """
        جمع المقاييس من الكلاستر
        Collect metrics from cluster state
        """
        now = datetime.utcnow()

        # الحصول على البيانات الأساسية
        workers = self.cluster_state.get_all_workers()
        healthy_workers = self.cluster_state.get_healthy_workers()
        pending_jobs = self.cluster_state.get_pending_jobs()
        running_jobs = self.cluster_state.get_running_jobs()

        # حساب مقاييس الطابور
        queue_depth = len(pending_jobs)
        queue_wait_times = []
        for job in pending_jobs:
            wait_time = (now - job.created_at).total_seconds()
            queue_wait_times.append(wait_time)

        # حساب معدل نمو الطابور
        time_diff = (now - self._last_check_time).total_seconds()
        if time_diff > 0:
            queue_growth_rate = (queue_depth - self._last_queue_depth) / time_diff
        else:
            queue_growth_rate = 0.0

        self._last_queue_depth = queue_depth
        self._last_check_time = now

        # حساب مقاييس الموارد
        cpu_utilizations = []
        memory_utilizations = []
        gpu_utilizations = []
        gpu_memory_utilizations = []
        memory_used = 0
        memory_total = 0
        gpu_total = 0
        gpu_available = 0

        for worker in workers:
            if worker.current_usage:
                cpu_utilizations.append(worker.current_usage.cpu_percent)
                memory_utilizations.append(worker.current_usage.memory_percent)
                memory_used += worker.current_usage.memory_used_mb
                memory_total += worker.current_usage.memory_total_mb

                for gpu in worker.current_usage.gpus:
                    gpu_utilizations.append(gpu.utilization_percent)
                    if gpu.memory_total_mb > 0:
                        gpu_mem_util = (gpu.memory_used_mb / gpu.memory_total_mb) * 100
                        gpu_memory_utilizations.append(gpu_mem_util)
                    gpu_total += 1
                    if gpu.is_available:
                        gpu_available += 1

        # حساب استخدام العمال
        if healthy_workers:
            total_capacity = sum(len(w.active_jobs) for w in healthy_workers)
            max_capacity = len(healthy_workers) * 10  # افتراضي 10 مهام لكل عامل
            worker_utilization = (total_capacity / max_capacity) * 100 if max_capacity > 0 else 0
        else:
            worker_utilization = 0.0

        # تحديث تاريخ الإنجاز
        stats = self.cluster_state.get_stats()
        self._completed_jobs_history.append((now, stats.get("total_jobs_completed", 0)))
        self._failed_jobs_history.append((now, stats.get("total_jobs_failed", 0)))

        # حساب المهام المكتملة في آخر دقيقة
        jobs_completed_last_min = 0
        jobs_failed_last_min = 0
        one_minute_ago = now - timedelta(minutes=1)

        if len(self._completed_jobs_history) >= 2:
            old_completed = None
            for ts, count in self._completed_jobs_history:
                if ts <= one_minute_ago:
                    old_completed = count
                else:
                    break
            if old_completed is not None:
                jobs_completed_last_min = stats.get("total_jobs_completed", 0) - old_completed

        if len(self._failed_jobs_history) >= 2:
            old_failed = None
            for ts, count in self._failed_jobs_history:
                if ts <= one_minute_ago:
                    old_failed = count
                else:
                    break
            if old_failed is not None:
                jobs_failed_last_min = stats.get("total_jobs_failed", 0) - old_failed

        return ResourceMetrics(
            timestamp=now,
            # Queue
            queue_depth=queue_depth,
            queue_wait_time_avg=statistics.mean(queue_wait_times) if queue_wait_times else 0.0,
            queue_wait_time_max=max(queue_wait_times) if queue_wait_times else 0.0,
            queue_growth_rate=queue_growth_rate,
            # CPU
            cpu_utilization_avg=statistics.mean(cpu_utilizations) if cpu_utilizations else 0.0,
            cpu_utilization_max=max(cpu_utilizations) if cpu_utilizations else 0.0,
            # Memory
            memory_utilization_avg=statistics.mean(memory_utilizations) if memory_utilizations else 0.0,
            memory_utilization_max=max(memory_utilizations) if memory_utilizations else 0.0,
            memory_used_mb=memory_used,
            memory_total_mb=memory_total,
            # GPU
            gpu_utilization_avg=statistics.mean(gpu_utilizations) if gpu_utilizations else 0.0,
            gpu_utilization_max=max(gpu_utilizations) if gpu_utilizations else 0.0,
            gpu_memory_utilization_avg=statistics.mean(gpu_memory_utilizations) if gpu_memory_utilizations else 0.0,
            gpu_count_total=gpu_total,
            gpu_count_available=gpu_available,
            # Workers
            worker_count=len(workers),
            healthy_worker_count=len(healthy_workers),
            worker_utilization=worker_utilization,
            # Throughput
            jobs_completed_last_minute=jobs_completed_last_min,
            jobs_failed_last_minute=jobs_failed_last_min,
            jobs_running=len(running_jobs),
        )


class MetricsCollector:
    """
    جامع ومدير المقاييس
    Metrics collector and manager

    يجمع المقاييس من مصادر متعددة ويحتفظ بتاريخها
    للاستخدام في قرارات التوسع التلقائي.

    Collects metrics from multiple sources and maintains
    history for use in auto-scaling decisions.
    """

    def __init__(
        self,
        cluster_state: ClusterState,
        collection_interval_seconds: float = 10.0,
        history_size: int = 360,  # ساعة واحدة بفاصل 10 ثواني
        custom_sources: Optional[list[MetricsSource]] = None,
    ):
        """
        تهيئة جامع المقاييس

        Args:
            cluster_state: حالة الكلاستر
            collection_interval_seconds: فترة جمع المقاييس بالثواني
            history_size: حجم تاريخ المقاييس
            custom_sources: مصادر مقاييس إضافية
        """
        self.cluster_state = cluster_state
        self.collection_interval = collection_interval_seconds
        self.history_size = history_size

        # المصادر
        self._sources: list[MetricsSource] = [ClusterMetricsSource(cluster_state)]
        if custom_sources:
            self._sources.extend(custom_sources)

        # التاريخ
        self._history: deque[ResourceMetrics] = deque(maxlen=history_size)
        self._samples: dict[MetricType, deque[MetricsSample]] = {
            metric_type: deque(maxlen=history_size)
            for metric_type in MetricType
        }

        # التحكم
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: list[Callable[[ResourceMetrics], None]] = []

        # آخر عينة
        self._latest_metrics: Optional[ResourceMetrics] = None

        logger.info(
            f"MetricsCollector initialized: interval={collection_interval_seconds}s, "
            f"history={history_size} samples"
        )

    def add_callback(self, callback: Callable[[ResourceMetrics], None]) -> None:
        """
        إضافة callback عند جمع مقاييس جديدة
        Add callback for new metrics collection
        """
        self._callbacks.append(callback)

    def add_source(self, source: MetricsSource) -> None:
        """
        إضافة مصدر مقاييس جديد
        Add new metrics source
        """
        self._sources.append(source)

    async def start(self) -> None:
        """
        بدء جمع المقاييس
        Start metrics collection
        """
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._collection_loop())
        logger.info("MetricsCollector started")

    async def stop(self) -> None:
        """
        إيقاف جمع المقاييس
        Stop metrics collection
        """
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MetricsCollector stopped")

    async def _collection_loop(self) -> None:
        """حلقة جمع المقاييس / Metrics collection loop"""
        while self._running:
            try:
                await self._collect_once()
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")

            await asyncio.sleep(self.collection_interval)

    async def _collect_once(self) -> None:
        """جمع مقاييس مرة واحدة / Collect metrics once"""
        start_time = time.perf_counter()

        # جمع من جميع المصادر
        for source in self._sources:
            try:
                metrics = await source.collect()
                self._history.append(metrics)
                self._latest_metrics = metrics

                # تحديث العينات الفردية
                self._update_samples(metrics)

                # استدعاء callbacks
                for callback in self._callbacks:
                    try:
                        callback(metrics)
                    except Exception as e:
                        logger.error(f"Metrics callback error: {e}")

            except Exception as e:
                logger.error(f"Error collecting from source {source}: {e}")

        collection_time = time.perf_counter() - start_time
        logger.debug(f"Metrics collected in {collection_time:.3f}s")

    def _update_samples(self, metrics: ResourceMetrics) -> None:
        """تحديث العينات الفردية / Update individual samples"""
        now = metrics.timestamp

        # Queue samples
        self._samples[MetricType.QUEUE_DEPTH].append(
            MetricsSample(now, MetricType.QUEUE_DEPTH, float(metrics.queue_depth))
        )
        self._samples[MetricType.QUEUE_WAIT_TIME].append(
            MetricsSample(now, MetricType.QUEUE_WAIT_TIME, metrics.queue_wait_time_avg)
        )
        self._samples[MetricType.QUEUE_GROWTH_RATE].append(
            MetricsSample(now, MetricType.QUEUE_GROWTH_RATE, metrics.queue_growth_rate)
        )

        # Resource samples
        self._samples[MetricType.CPU_UTILIZATION].append(
            MetricsSample(now, MetricType.CPU_UTILIZATION, metrics.cpu_utilization_avg)
        )
        self._samples[MetricType.MEMORY_UTILIZATION].append(
            MetricsSample(now, MetricType.MEMORY_UTILIZATION, metrics.memory_utilization_avg)
        )
        self._samples[MetricType.GPU_UTILIZATION].append(
            MetricsSample(now, MetricType.GPU_UTILIZATION, metrics.gpu_utilization_avg)
        )
        self._samples[MetricType.GPU_MEMORY_UTILIZATION].append(
            MetricsSample(now, MetricType.GPU_MEMORY_UTILIZATION, metrics.gpu_memory_utilization_avg)
        )

        # Worker samples
        self._samples[MetricType.WORKER_COUNT].append(
            MetricsSample(now, MetricType.WORKER_COUNT, float(metrics.worker_count))
        )
        self._samples[MetricType.HEALTHY_WORKER_COUNT].append(
            MetricsSample(now, MetricType.HEALTHY_WORKER_COUNT, float(metrics.healthy_worker_count))
        )
        self._samples[MetricType.WORKER_UTILIZATION].append(
            MetricsSample(now, MetricType.WORKER_UTILIZATION, metrics.worker_utilization)
        )

        # Throughput samples
        self._samples[MetricType.JOBS_PER_MINUTE].append(
            MetricsSample(now, MetricType.JOBS_PER_MINUTE, float(metrics.jobs_completed_last_minute))
        )
        if metrics.healthy_worker_count > 0:
            jobs_per_worker = metrics.jobs_completed_last_minute / metrics.healthy_worker_count
        else:
            jobs_per_worker = 0.0
        self._samples[MetricType.JOBS_PER_WORKER].append(
            MetricsSample(now, MetricType.JOBS_PER_WORKER, jobs_per_worker)
        )

        # Failure samples
        total_jobs = metrics.jobs_completed_last_minute + metrics.jobs_failed_last_minute
        if total_jobs > 0:
            failure_rate = (metrics.jobs_failed_last_minute / total_jobs) * 100
        else:
            failure_rate = 0.0
        self._samples[MetricType.FAILURE_RATE].append(
            MetricsSample(now, MetricType.FAILURE_RATE, failure_rate)
        )

    async def collect_now(self) -> ResourceMetrics:
        """
        جمع المقاييس الآن (بدون انتظار الحلقة)
        Collect metrics now (without waiting for loop)
        """
        await self._collect_once()
        if self._latest_metrics is None:
            raise RuntimeError("No metrics collected")
        return self._latest_metrics

    def get_latest(self) -> Optional[ResourceMetrics]:
        """
        الحصول على آخر مقاييس
        Get latest metrics
        """
        return self._latest_metrics

    def get_history(
        self,
        duration_seconds: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[ResourceMetrics]:
        """
        الحصول على تاريخ المقاييس
        Get metrics history

        Args:
            duration_seconds: المدة بالثواني (اختياري)
            limit: الحد الأقصى للنتائج (اختياري)
        """
        history = list(self._history)

        if duration_seconds is not None:
            cutoff = datetime.utcnow() - timedelta(seconds=duration_seconds)
            history = [m for m in history if m.timestamp >= cutoff]

        if limit is not None:
            history = history[-limit:]

        return history

    def get_metric_samples(
        self,
        metric_type: MetricType,
        duration_seconds: Optional[float] = None,
    ) -> list[MetricsSample]:
        """
        الحصول على عينات مقياس معين
        Get samples for a specific metric

        Args:
            metric_type: نوع المقياس
            duration_seconds: المدة بالثواني (اختياري)
        """
        samples = list(self._samples.get(metric_type, []))

        if duration_seconds is not None:
            cutoff = datetime.utcnow() - timedelta(seconds=duration_seconds)
            samples = [s for s in samples if s.timestamp >= cutoff]

        return samples

    def get_aggregated_metric(
        self,
        metric_type: MetricType,
        method: AggregationMethod = AggregationMethod.AVERAGE,
        duration_seconds: float = 60.0,
    ) -> float:
        """
        الحصول على قيمة مقياس مجمعة
        Get aggregated metric value

        Args:
            metric_type: نوع المقياس
            method: طريقة التجميع
            duration_seconds: المدة بالثواني
        """
        samples = self.get_metric_samples(metric_type, duration_seconds)
        if not samples:
            return 0.0

        values = [s.value for s in samples]

        if method == AggregationMethod.AVERAGE:
            return statistics.mean(values)
        elif method == AggregationMethod.MEDIAN:
            return statistics.median(values)
        elif method == AggregationMethod.MIN:
            return min(values)
        elif method == AggregationMethod.MAX:
            return max(values)
        elif method == AggregationMethod.SUM:
            return sum(values)
        elif method == AggregationMethod.PERCENTILE_90:
            return self._percentile(values, 90)
        elif method == AggregationMethod.PERCENTILE_95:
            return self._percentile(values, 95)
        elif method == AggregationMethod.PERCENTILE_99:
            return self._percentile(values, 99)
        elif method == AggregationMethod.LATEST:
            return values[-1] if values else 0.0

        return 0.0

    @staticmethod
    def _percentile(data: list[float], percentile: int) -> float:
        """حساب المئين / Calculate percentile"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = (len(sorted_data) - 1) * percentile / 100
        lower = int(index)
        upper = lower + 1
        if upper >= len(sorted_data):
            return sorted_data[-1]
        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight

    def get_trend(
        self,
        metric_type: MetricType,
        duration_seconds: float = 300.0,
    ) -> float:
        """
        حساب اتجاه المقياس (موجب = صاعد، سالب = هابط)
        Calculate metric trend (positive = rising, negative = falling)

        Args:
            metric_type: نوع المقياس
            duration_seconds: المدة بالثواني
        """
        samples = self.get_metric_samples(metric_type, duration_seconds)
        if len(samples) < 2:
            return 0.0

        # حساب الميل باستخدام الانحدار الخطي البسيط
        n = len(samples)
        x_values = list(range(n))
        y_values = [s.value for s in samples]

        x_mean = sum(x_values) / n
        y_mean = sum(y_values) / n

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
        denominator = sum((x - x_mean) ** 2 for x in x_values)

        if denominator == 0:
            return 0.0

        slope = numerator / denominator

        # تطبيع الميل
        if y_mean != 0:
            normalized_slope = slope / abs(y_mean) * 100  # نسبة التغير
        else:
            normalized_slope = slope

        return normalized_slope

    def get_status(self) -> dict[str, Any]:
        """
        الحصول على حالة جامع المقاييس
        Get metrics collector status
        """
        return {
            "running": self._running,
            "collection_interval_seconds": self.collection_interval,
            "history_size": len(self._history),
            "max_history_size": self.history_size,
            "sources_count": len(self._sources),
            "latest_collection": (
                self._latest_metrics.timestamp.isoformat()
                if self._latest_metrics
                else None
            ),
            "callbacks_count": len(self._callbacks),
        }
