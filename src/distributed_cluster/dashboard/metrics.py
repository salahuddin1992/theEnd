"""
Metrics Collection - جمع المقاييس
=================================

Metrics Collection System
-------------------------

This module provides metrics collection and aggregation.

يوفر هذا الملف جمع وتجميع المقاييس.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """نوع المقياس / Metric type"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricPoint:
    """
    نقطة بيانات المقياس
    Metric data point
    """
    timestamp: datetime
    value: float
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "labels": self.labels,
        }


@dataclass
class MetricSeries:
    """
    سلسلة بيانات المقياس
    Metric data series
    """
    name: str
    metric_type: MetricType
    description: str = ""
    unit: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    points: deque[MetricPoint] = field(default_factory=lambda: deque(maxlen=1000))

    # Aggregation
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    sum_value: float = 0.0
    count: int = 0

    def add_point(self, value: float, labels: Optional[dict[str, str]] = None) -> None:
        """إضافة نقطة بيانات"""
        point = MetricPoint(
            timestamp=datetime.utcnow(),
            value=value,
            labels=labels or {},
        )
        self.points.append(point)

        # Update aggregations
        if self.min_value is None or value < self.min_value:
            self.min_value = value
        if self.max_value is None or value > self.max_value:
            self.max_value = value
        self.sum_value += value
        self.count += 1

    @property
    def average(self) -> float:
        """القيمة المتوسطة"""
        return self.sum_value / self.count if self.count > 0 else 0.0

    @property
    def latest_value(self) -> Optional[float]:
        """أحدث قيمة"""
        return self.points[-1].value if self.points else None

    def get_points_since(self, since: datetime) -> list[MetricPoint]:
        """الحصول على النقاط منذ وقت معين"""
        return [p for p in self.points if p.timestamp >= since]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.metric_type.value,
            "description": self.description,
            "unit": self.unit,
            "labels": self.labels,
            "min": self.min_value,
            "max": self.max_value,
            "avg": self.average,
            "count": self.count,
            "latest": self.latest_value,
            "points": [p.to_dict() for p in list(self.points)[-100:]],
        }


class MetricsCollector:
    """
    جامع المقاييس
    Metrics Collector

    يجمع ويخزن ويصدر المقاييس.
    Collects, stores, and exports metrics.
    """

    def __init__(
        self,
        collection_interval_seconds: float = 10.0,
        retention_hours: int = 24,
    ):
        """
        تهيئة جامع المقاييس

        Args:
            collection_interval_seconds: فترة الجمع
            retention_hours: ساعات الاحتفاظ
        """
        self.collection_interval = collection_interval_seconds
        self.retention_hours = retention_hours

        # Metric series
        self._metrics: dict[str, MetricSeries] = {}

        # Collectors
        self._collectors: list[Callable[[], dict[str, float]]] = []

        # State
        self._running = False
        self._collection_task: Optional[asyncio.Task] = None

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء الجامع"""
        self._running = True
        self._collection_task = asyncio.create_task(self._collection_loop())
        logger.info("MetricsCollector started")

    async def stop(self) -> None:
        """إيقاف الجامع"""
        self._running = False

        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass

        logger.info("MetricsCollector stopped")

    # =========================================================================
    # Metric Registration
    # =========================================================================

    def register_metric(
        self,
        name: str,
        metric_type: MetricType,
        description: str = "",
        unit: str = "",
        labels: Optional[dict[str, str]] = None,
    ) -> MetricSeries:
        """تسجيل مقياس جديد"""
        if name in self._metrics:
            return self._metrics[name]

        series = MetricSeries(
            name=name,
            metric_type=metric_type,
            description=description,
            unit=unit,
            labels=labels or {},
        )

        self._metrics[name] = series
        logger.debug(f"Registered metric: {name}")

        return series

    def register_collector(
        self,
        collector: Callable[[], dict[str, float]],
    ) -> None:
        """تسجيل جامع مخصص"""
        self._collectors.append(collector)

    # =========================================================================
    # Metric Recording
    # =========================================================================

    def record(
        self,
        name: str,
        value: float,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """تسجيل قيمة مقياس"""
        if name not in self._metrics:
            self.register_metric(name, MetricType.GAUGE)

        self._metrics[name].add_point(value, labels)

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """زيادة عداد"""
        if name not in self._metrics:
            self.register_metric(name, MetricType.COUNTER)

        series = self._metrics[name]
        current = series.latest_value or 0.0
        series.add_point(current + value, labels)

    def gauge(
        self,
        name: str,
        value: float,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """تسجيل gauge"""
        self.record(name, value, labels)

    def histogram(
        self,
        name: str,
        value: float,
        buckets: Optional[list[float]] = None,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """تسجيل histogram"""
        if name not in self._metrics:
            self.register_metric(name, MetricType.HISTOGRAM)

        self._metrics[name].add_point(value, labels)

    # =========================================================================
    # Collection
    # =========================================================================

    async def _collection_loop(self) -> None:
        """حلقة الجمع"""
        while self._running:
            try:
                await self._collect()
                await asyncio.sleep(self.collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Collection error: {e}")
                await asyncio.sleep(5)

    async def _collect(self) -> None:
        """جمع المقاييس"""
        # System metrics
        await self._collect_system_metrics()

        # Custom collectors
        for collector in self._collectors:
            try:
                if asyncio.iscoroutinefunction(collector):
                    metrics = await collector()
                else:
                    metrics = collector()

                for name, value in metrics.items():
                    self.record(name, value)

            except Exception as e:
                logger.error(f"Collector error: {e}")

        # Cleanup old data
        await self._cleanup_old_data()

    async def _collect_system_metrics(self) -> None:
        """جمع مقاييس النظام"""
        try:
            import psutil

            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.gauge("system_cpu_percent", cpu_percent)

            # Memory
            memory = psutil.virtual_memory()
            self.gauge("system_memory_percent", memory.percent)
            self.gauge("system_memory_used_bytes", memory.used)
            self.gauge("system_memory_available_bytes", memory.available)

            # Disk
            disk = psutil.disk_usage("/")
            self.gauge("system_disk_percent", disk.percent)
            self.gauge("system_disk_used_bytes", disk.used)

            # Network
            net = psutil.net_io_counters()
            self.gauge("system_network_bytes_sent", net.bytes_sent)
            self.gauge("system_network_bytes_recv", net.bytes_recv)

        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"System metrics collection failed: {e}")

    async def _cleanup_old_data(self) -> None:
        """تنظيف البيانات القديمة"""
        cutoff = datetime.utcnow() - timedelta(hours=self.retention_hours)

        for series in self._metrics.values():
            while series.points and series.points[0].timestamp < cutoff:
                series.points.popleft()

    # =========================================================================
    # Query
    # =========================================================================

    def get_metric(self, name: str) -> Optional[MetricSeries]:
        """الحصول على مقياس"""
        return self._metrics.get(name)

    def get_all_metrics(self) -> dict[str, MetricSeries]:
        """الحصول على جميع المقاييس"""
        return self._metrics.copy()

    def get_metric_names(self) -> list[str]:
        """قائمة أسماء المقاييس"""
        return list(self._metrics.keys())

    def query(
        self,
        name: str,
        since: Optional[datetime] = None,
        labels: Optional[dict[str, str]] = None,
    ) -> list[MetricPoint]:
        """استعلام عن مقياس"""
        series = self._metrics.get(name)
        if not series:
            return []

        points = list(series.points)

        if since:
            points = [p for p in points if p.timestamp >= since]

        if labels:
            points = [
                p for p in points
                if all(p.labels.get(k) == v for k, v in labels.items())
            ]

        return points

    # =========================================================================
    # Export
    # =========================================================================

    def export_prometheus(self) -> str:
        """تصدير بتنسيق Prometheus"""
        lines = []

        for name, series in self._metrics.items():
            # Help
            if series.description:
                lines.append(f"# HELP {name} {series.description}")

            # Type
            lines.append(f"# TYPE {name} {series.metric_type.value}")

            # Value
            if series.latest_value is not None:
                label_str = ""
                if series.labels:
                    labels = ",".join(
                        f'{k}="{v}"' for k, v in series.labels.items()
                    )
                    label_str = f"{{{labels}}}"

                lines.append(f"{name}{label_str} {series.latest_value}")

        return "\n".join(lines)

    def export_json(self) -> dict[str, Any]:
        """تصدير بتنسيق JSON"""
        return {
            name: series.to_dict()
            for name, series in self._metrics.items()
        }

    def get_summary(self) -> dict[str, Any]:
        """ملخص المقاييس"""
        return {
            "total_metrics": len(self._metrics),
            "total_points": sum(len(s.points) for s in self._metrics.values()),
            "metrics": {
                name: {
                    "type": series.metric_type.value,
                    "latest": series.latest_value,
                    "min": series.min_value,
                    "max": series.max_value,
                    "avg": series.average,
                }
                for name, series in self._metrics.items()
            },
        }
