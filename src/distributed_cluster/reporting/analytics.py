"""
Analytics Engine - محرك التحليلات
====================================

Advanced analytics and metrics processing.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AggregationType(str, Enum):
    """نوع التجميع"""
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    P50 = "p50"
    P95 = "p95"
    P99 = "p99"
    RATE = "rate"


class TimeGranularity(str, Enum):
    """دقة الوقت"""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass
class MetricPoint:
    """نقطة قياس"""
    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSeries:
    """سلسلة قياسات"""
    name: str
    points: List[MetricPoint] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)

    def add_point(self, value: float, timestamp: Optional[datetime] = None) -> None:
        """إضافة نقطة"""
        self.points.append(MetricPoint(
            timestamp=timestamp or datetime.utcnow(),
            value=value,
        ))

    def get_values(self) -> List[float]:
        """الحصول على القيم"""
        return [p.value for p in self.points]

    def get_latest(self) -> Optional[float]:
        """الحصول على آخر قيمة"""
        if self.points:
            return self.points[-1].value
        return None


@dataclass
class AnalyticsResult:
    """نتيجة التحليل"""
    metric_name: str
    aggregation: AggregationType
    value: float
    time_range: Tuple[datetime, datetime]
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metricName": self.metric_name,
            "aggregation": self.aggregation.value,
            "value": self.value,
            "timeRange": {
                "start": self.time_range[0].isoformat(),
                "end": self.time_range[1].isoformat(),
            },
            "labels": self.labels,
            "metadata": self.metadata,
        }


class MetricAggregator:
    """
    مجمّع القياسات
    Metric Aggregator

    يجمّع القياسات حسب الوقت والتسميات.
    Aggregates metrics by time and labels.
    """

    def __init__(self):
        self._series: Dict[str, MetricSeries] = {}

    def record(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """تسجيل قياس"""
        key = self._make_key(name, labels)
        if key not in self._series:
            self._series[key] = MetricSeries(name=name, labels=labels or {})
        self._series[key].add_point(value, timestamp)

    def aggregate(
        self,
        name: str,
        aggregation: AggregationType,
        labels: Optional[Dict[str, str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Optional[AnalyticsResult]:
        """تجميع القياسات"""
        key = self._make_key(name, labels)
        series = self._series.get(key)
        if not series:
            return None

        # Filter by time
        points = series.points
        if start_time:
            points = [p for p in points if p.timestamp >= start_time]
        if end_time:
            points = [p for p in points if p.timestamp <= end_time]

        if not points:
            return None

        values = [p.value for p in points]
        time_range = (points[0].timestamp, points[-1].timestamp)

        # Calculate aggregation
        result_value = self._calculate_aggregation(values, aggregation, time_range)

        return AnalyticsResult(
            metric_name=name,
            aggregation=aggregation,
            value=result_value,
            time_range=time_range,
            labels=labels or {},
        )

    def _calculate_aggregation(
        self,
        values: List[float],
        aggregation: AggregationType,
        time_range: Tuple[datetime, datetime],
    ) -> float:
        """حساب التجميع"""
        if not values:
            return 0.0

        if aggregation == AggregationType.SUM:
            return sum(values)
        elif aggregation == AggregationType.AVG:
            return statistics.mean(values)
        elif aggregation == AggregationType.MIN:
            return min(values)
        elif aggregation == AggregationType.MAX:
            return max(values)
        elif aggregation == AggregationType.COUNT:
            return float(len(values))
        elif aggregation == AggregationType.P50:
            return statistics.median(values)
        elif aggregation == AggregationType.P95:
            return self._percentile(values, 95)
        elif aggregation == AggregationType.P99:
            return self._percentile(values, 99)
        elif aggregation == AggregationType.RATE:
            duration = (time_range[1] - time_range[0]).total_seconds()
            return sum(values) / duration if duration > 0 else 0.0
        else:
            return 0.0

    def _percentile(self, values: List[float], percentile: int) -> float:
        """حساب النسبة المئوية"""
        sorted_values = sorted(values)
        index = (len(sorted_values) - 1) * percentile / 100
        lower = int(index)
        upper = lower + 1
        if upper >= len(sorted_values):
            return sorted_values[-1]
        weight = index - lower
        return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """إنشاء مفتاح فريد"""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_series(self, name: str) -> List[MetricSeries]:
        """الحصول على السلاسل"""
        return [s for s in self._series.values() if s.name == name]

    def clear(self, before: Optional[datetime] = None) -> int:
        """مسح القياسات القديمة"""
        if not before:
            count = len(self._series)
            self._series.clear()
            return count

        count = 0
        for series in self._series.values():
            original_len = len(series.points)
            series.points = [p for p in series.points if p.timestamp >= before]
            count += original_len - len(series.points)
        return count


class TrendAnalyzer:
    """
    محلل الاتجاهات
    Trend Analyzer

    يحلل اتجاهات القياسات ويتنبأ بها.
    Analyzes and predicts metric trends.
    """

    def __init__(self, aggregator: MetricAggregator):
        self.aggregator = aggregator

    def analyze_trend(
        self,
        metric_name: str,
        granularity: TimeGranularity = TimeGranularity.HOUR,
        periods: int = 24,
    ) -> Dict[str, Any]:
        """
        تحليل الاتجاه
        Analyze trend
        """
        series_list = self.aggregator.get_series(metric_name)
        if not series_list:
            return {"error": "No data found"}

        # Combine all series
        all_points: List[MetricPoint] = []
        for series in series_list:
            all_points.extend(series.points)

        if not all_points:
            return {"error": "No data points"}

        all_points.sort(key=lambda p: p.timestamp)

        # Group by granularity
        grouped = self._group_by_granularity(all_points, granularity)

        # Calculate statistics
        values = [g["avg"] for g in grouped]

        trend_direction = self._calculate_trend_direction(values)
        change_percent = self._calculate_change_percent(values)

        return {
            "metricName": metric_name,
            "granularity": granularity.value,
            "periods": len(grouped),
            "data": grouped,
            "summary": {
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
                "avg": statistics.mean(values) if values else 0,
                "stddev": statistics.stdev(values) if len(values) > 1 else 0,
                "trend": trend_direction,
                "changePercent": change_percent,
            },
        }

    def predict(
        self,
        metric_name: str,
        periods_ahead: int = 24,
        method: str = "linear",
    ) -> Dict[str, Any]:
        """
        التنبؤ
        Predict future values
        """
        series_list = self.aggregator.get_series(metric_name)
        if not series_list:
            return {"error": "No data found"}

        all_points: List[MetricPoint] = []
        for series in series_list:
            all_points.extend(series.points)

        if len(all_points) < 2:
            return {"error": "Insufficient data for prediction"}

        all_points.sort(key=lambda p: p.timestamp)
        values = [p.value for p in all_points]

        # Simple linear regression
        n = len(values)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator

        intercept = y_mean - slope * x_mean

        # Generate predictions
        predictions = []
        all_points[-1].timestamp
        for i in range(1, periods_ahead + 1):
            predicted_value = slope * (n + i) + intercept
            predictions.append({
                "period": i,
                "value": max(0, predicted_value),  # Ensure non-negative
            })

        return {
            "metricName": metric_name,
            "method": method,
            "predictions": predictions,
            "model": {
                "slope": slope,
                "intercept": intercept,
                "confidence": self._calculate_r_squared(values, slope, intercept),
            },
        }

    def detect_anomalies(
        self,
        metric_name: str,
        threshold_stddev: float = 2.0,
    ) -> Dict[str, Any]:
        """
        اكتشاف الشذوذ
        Detect anomalies
        """
        series_list = self.aggregator.get_series(metric_name)
        if not series_list:
            return {"error": "No data found"}

        all_points: List[MetricPoint] = []
        for series in series_list:
            all_points.extend(series.points)

        if len(all_points) < 3:
            return {"anomalies": [], "message": "Insufficient data"}

        values = [p.value for p in all_points]
        mean = statistics.mean(values)
        stddev = statistics.stdev(values)

        anomalies = []
        for point in all_points:
            z_score = (point.value - mean) / stddev if stddev > 0 else 0
            if abs(z_score) > threshold_stddev:
                anomalies.append({
                    "timestamp": point.timestamp.isoformat(),
                    "value": point.value,
                    "zScore": z_score,
                    "severity": "high" if abs(z_score) > 3 else "medium",
                })

        return {
            "metricName": metric_name,
            "anomalies": anomalies,
            "statistics": {
                "mean": mean,
                "stddev": stddev,
                "threshold": threshold_stddev,
            },
        }

    def _group_by_granularity(
        self,
        points: List[MetricPoint],
        granularity: TimeGranularity,
    ) -> List[Dict[str, Any]]:
        """تجميع حسب الدقة الزمنية"""
        grouped: Dict[str, List[float]] = defaultdict(list)

        for point in points:
            key = self._get_time_bucket(point.timestamp, granularity)
            grouped[key].append(point.value)

        result = []
        for time_key in sorted(grouped.keys()):
            values = grouped[time_key]
            result.append({
                "time": time_key,
                "count": len(values),
                "sum": sum(values),
                "avg": statistics.mean(values),
                "min": min(values),
                "max": max(values),
            })

        return result

    def _get_time_bucket(self, dt: datetime, granularity: TimeGranularity) -> str:
        """الحصول على دلو الوقت"""
        if granularity == TimeGranularity.MINUTE:
            return dt.strftime("%Y-%m-%d %H:%M")
        elif granularity == TimeGranularity.HOUR:
            return dt.strftime("%Y-%m-%d %H:00")
        elif granularity == TimeGranularity.DAY:
            return dt.strftime("%Y-%m-%d")
        elif granularity == TimeGranularity.WEEK:
            return dt.strftime("%Y-W%W")
        elif granularity == TimeGranularity.MONTH:
            return dt.strftime("%Y-%m")
        else:
            return dt.isoformat()

    def _calculate_trend_direction(self, values: List[float]) -> str:
        """حساب اتجاه الاتجاه"""
        if len(values) < 2:
            return "stable"

        first_half = statistics.mean(values[: len(values) // 2])
        second_half = statistics.mean(values[len(values) // 2 :])

        diff_percent = ((second_half - first_half) / first_half * 100) if first_half != 0 else 0

        if diff_percent > 5:
            return "increasing"
        elif diff_percent < -5:
            return "decreasing"
        else:
            return "stable"

    def _calculate_change_percent(self, values: List[float]) -> float:
        """حساب نسبة التغير"""
        if len(values) < 2 or values[0] == 0:
            return 0.0
        return ((values[-1] - values[0]) / values[0]) * 100

    def _calculate_r_squared(self, values: List[float], slope: float, intercept: float) -> float:
        """حساب R-squared"""
        if len(values) < 2:
            return 0.0

        y_mean = statistics.mean(values)
        ss_tot = sum((v - y_mean) ** 2 for v in values)
        ss_res = sum((values[i] - (slope * i + intercept)) ** 2 for i in range(len(values)))

        if ss_tot == 0:
            return 1.0
        return 1 - (ss_res / ss_tot)


class AnalyticsEngine:
    """
    محرك التحليلات
    Analytics Engine

    المحرك الرئيسي للتحليلات.
    Main analytics engine.
    """

    def __init__(self):
        self.aggregator = MetricAggregator()
        self.trend_analyzer = TrendAnalyzer(self.aggregator)
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """بدء المحرك"""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Analytics Engine started")

    async def stop(self) -> None:
        """إيقاف المحرك"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()

    def record_metric(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """تسجيل قياس"""
        self.aggregator.record(name, value, labels)

    async def query(
        self,
        metric_name: str,
        aggregation: AggregationType = AggregationType.AVG,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> Optional[AnalyticsResult]:
        """استعلام"""
        return self.aggregator.aggregate(
            metric_name, aggregation, labels, start_time, end_time
        )

    async def get_trend(
        self,
        metric_name: str,
        granularity: TimeGranularity = TimeGranularity.HOUR,
        periods: int = 24,
    ) -> Dict[str, Any]:
        """الحصول على الاتجاه"""
        return self.trend_analyzer.analyze_trend(metric_name, granularity, periods)

    async def predict(
        self,
        metric_name: str,
        periods_ahead: int = 24,
    ) -> Dict[str, Any]:
        """التنبؤ"""
        return self.trend_analyzer.predict(metric_name, periods_ahead)

    async def detect_anomalies(
        self,
        metric_name: str,
        threshold: float = 2.0,
    ) -> Dict[str, Any]:
        """اكتشاف الشذوذ"""
        return self.trend_analyzer.detect_anomalies(metric_name, threshold)

    async def get_summary(self) -> Dict[str, Any]:
        """الحصول على ملخص"""
        series_count = len(self.aggregator._series)
        total_points = sum(len(s.points) for s in self.aggregator._series.values())

        return {
            "seriesCount": series_count,
            "totalPoints": total_points,
            "running": self._running,
        }

    async def _cleanup_loop(self) -> None:
        """حلقة التنظيف"""
        while self._running:
            try:
                await asyncio.sleep(3600)  # Every hour
                # Clean up data older than 7 days
                cutoff = datetime.utcnow() - timedelta(days=7)
                count = self.aggregator.clear(before=cutoff)
                if count > 0:
                    logger.info(f"Cleaned up {count} old metric points")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
