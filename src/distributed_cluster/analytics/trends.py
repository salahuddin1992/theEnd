# -*- coding: utf-8 -*-
"""
Trend Analyzer for NebulaCompute.

Analyzes trends and patterns in cluster metrics.

تحليل الاتجاهات والأنماط في مقاييس المجموعة.
"""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class TrendDirection(str, Enum):
    """Trend direction."""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


class TrendStrength(str, Enum):
    """Trend strength."""

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


@dataclass
class TrendReport:
    """
    Trend analysis report.

    تقرير تحليل الاتجاه.
    """

    report_id: str
    metric_name: str
    period_start: datetime
    period_end: datetime

    # Trend characteristics
    direction: TrendDirection
    strength: TrendStrength
    slope: float  # Rate of change
    r_squared: float  # Fit quality

    # Statistical summary
    mean: float
    median: float
    std_dev: float
    min_value: float
    max_value: float
    percentile_95: float

    # Pattern detection
    patterns_detected: List[str]
    anomalies_count: int
    seasonality: Optional[str]

    # Insights
    insights: List[str]
    recommendations: List[str]

    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "report_id": self.report_id,
            "metric_name": self.metric_name,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "direction": self.direction.value,
            "strength": self.strength.value,
            "slope": self.slope,
            "r_squared": self.r_squared,
            "mean": self.mean,
            "median": self.median,
            "std_dev": self.std_dev,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "percentile_95": self.percentile_95,
            "patterns_detected": self.patterns_detected,
            "anomalies_count": self.anomalies_count,
            "seasonality": self.seasonality,
            "insights": self.insights,
            "recommendations": self.recommendations,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class MetricDataPoint:
    """Metric data point for trend analysis."""

    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class CorrelationResult:
    """Correlation analysis result."""

    metric_a: str
    metric_b: str
    correlation: float  # -1 to 1
    p_value: float
    significance: str  # "significant", "not_significant"
    lag: int  # Time lag for max correlation

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric_a": self.metric_a,
            "metric_b": self.metric_b,
            "correlation": self.correlation,
            "p_value": self.p_value,
            "significance": self.significance,
            "lag": self.lag,
        }


class TrendAnalyzer:
    """
    Analyzes trends and patterns in metrics.

    محلل الاتجاهات والأنماط.

    Features:
    - Trend detection and quantification
    - Pattern recognition
    - Anomaly detection
    - Correlation analysis
    - Insight generation
    """

    def __init__(
        self,
        anomaly_threshold: float = 3.0,  # Standard deviations
        min_data_points: int = 10,
    ):
        """
        Initialize Trend Analyzer.

        Args:
            anomaly_threshold: Z-score threshold for anomalies
            min_data_points: Minimum data points for analysis
        """
        self.anomaly_threshold = anomaly_threshold
        self.min_data_points = min_data_points

        # Storage
        self._metrics: Dict[str, List[MetricDataPoint]] = {}
        self._reports: Dict[str, TrendReport] = {}
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "reports_generated": 0,
            "anomalies_detected": 0,
            "correlations_analyzed": 0,
        }

    async def add_data_point(
        self,
        metric_name: str,
        value: float,
        timestamp: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Add metric data point.

        إضافة نقطة بيانات للمقياس.
        """
        point = MetricDataPoint(
            timestamp=timestamp or datetime.utcnow(),
            value=value,
            labels=labels or {},
        )

        async with self._lock:
            if metric_name not in self._metrics:
                self._metrics[metric_name] = []
            self._metrics[metric_name].append(point)

    async def analyze_trend(
        self,
        metric_name: str,
        period_hours: int = 24,
    ) -> Optional[TrendReport]:
        """
        Analyze trend for a metric.

        تحليل اتجاه المقياس.
        """
        import uuid

        data = self._metrics.get(metric_name, [])
        if len(data) < self.min_data_points:
            logger.warning(
                f"Insufficient data for {metric_name}: "
                f"{len(data)} < {self.min_data_points}"
            )
            return None

        # Filter by period
        cutoff = datetime.utcnow() - timedelta(hours=period_hours)
        filtered = [d for d in data if d.timestamp > cutoff]

        if len(filtered) < self.min_data_points:
            filtered = data[-self.min_data_points:]

        values = np.array([d.value for d in filtered])
        timestamps = [d.timestamp for d in filtered]

        # Calculate trend
        direction, strength, slope, r_squared = self._calculate_trend(values)

        # Calculate statistics
        mean = float(np.mean(values))
        median = float(np.median(values))
        std_dev = float(np.std(values))
        min_val = float(np.min(values))
        max_val = float(np.max(values))
        p95 = float(np.percentile(values, 95))

        # Detect patterns
        patterns = self._detect_patterns(values)

        # Detect anomalies
        anomalies = self._detect_anomalies(values)

        # Detect seasonality
        seasonality = self._detect_seasonality(values)

        # Generate insights
        insights = self._generate_insights(
            metric_name, direction, strength, mean, std_dev, patterns, anomalies
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            metric_name, direction, strength, mean, p95
        )

        report = TrendReport(
            report_id=str(uuid.uuid4()),
            metric_name=metric_name,
            period_start=timestamps[0],
            period_end=timestamps[-1],
            direction=direction,
            strength=strength,
            slope=slope,
            r_squared=r_squared,
            mean=mean,
            median=median,
            std_dev=std_dev,
            min_value=min_val,
            max_value=max_val,
            percentile_95=p95,
            patterns_detected=patterns,
            anomalies_count=len(anomalies),
            seasonality=seasonality,
            insights=insights,
            recommendations=recommendations,
        )

        async with self._lock:
            self._reports[report.report_id] = report
            self._stats["reports_generated"] += 1
            self._stats["anomalies_detected"] += len(anomalies)

        logger.info(
            f"Trend analysis for {metric_name}: "
            f"{direction.value} ({strength.value}), "
            f"anomalies={len(anomalies)}"
        )

        return report

    async def analyze_correlation(
        self,
        metric_a: str,
        metric_b: str,
        max_lag: int = 12,
    ) -> Optional[CorrelationResult]:
        """
        Analyze correlation between two metrics.

        تحليل الارتباط بين مقياسين.
        """
        data_a = self._metrics.get(metric_a, [])
        data_b = self._metrics.get(metric_b, [])

        if len(data_a) < self.min_data_points or len(data_b) < self.min_data_points:
            return None

        # Align data by timestamp
        values_a, values_b = self._align_time_series(data_a, data_b)

        if len(values_a) < self.min_data_points:
            return None

        # Find correlation with lag
        best_correlation = 0.0
        best_lag = 0

        for lag in range(-max_lag, max_lag + 1):
            if lag < 0:
                corr = self._pearson_correlation(
                    values_a[-lag:], values_b[:len(values_a) + lag]
                )
            elif lag > 0:
                corr = self._pearson_correlation(
                    values_a[:-lag] if lag else values_a,
                    values_b[lag:]
                )
            else:
                corr = self._pearson_correlation(values_a, values_b)

            if abs(corr) > abs(best_correlation):
                best_correlation = corr
                best_lag = lag

        # Calculate p-value approximation
        n = len(values_a)
        t_stat = best_correlation * math.sqrt((n - 2) / (1 - best_correlation ** 2 + 1e-10))
        p_value = 2 * (1 - self._t_distribution_cdf(abs(t_stat), n - 2))

        significance = "significant" if p_value < 0.05 else "not_significant"

        result = CorrelationResult(
            metric_a=metric_a,
            metric_b=metric_b,
            correlation=best_correlation,
            p_value=p_value,
            significance=significance,
            lag=best_lag,
        )

        self._stats["correlations_analyzed"] += 1

        return result

    async def compare_periods(
        self,
        metric_name: str,
        period1_start: datetime,
        period1_end: datetime,
        period2_start: datetime,
        period2_end: datetime,
    ) -> Dict[str, Any]:
        """
        Compare metric between two periods.

        مقارنة المقياس بين فترتين.
        """
        data = self._metrics.get(metric_name, [])

        # Filter by periods
        period1 = [d.value for d in data if period1_start <= d.timestamp <= period1_end]
        period2 = [d.value for d in data if period2_start <= d.timestamp <= period2_end]

        if not period1 or not period2:
            return {"error": "Insufficient data for comparison"}

        p1_mean = np.mean(period1)
        p2_mean = np.mean(period2)
        p1_std = np.std(period1)
        p2_std = np.std(period2)

        change = ((p2_mean - p1_mean) / p1_mean * 100) if p1_mean != 0 else 0
        volatility_change = ((p2_std - p1_std) / p1_std * 100) if p1_std != 0 else 0

        return {
            "metric_name": metric_name,
            "period1": {
                "start": period1_start.isoformat(),
                "end": period1_end.isoformat(),
                "mean": p1_mean,
                "std": p1_std,
                "min": min(period1),
                "max": max(period1),
                "count": len(period1),
            },
            "period2": {
                "start": period2_start.isoformat(),
                "end": period2_end.isoformat(),
                "mean": p2_mean,
                "std": p2_std,
                "min": min(period2),
                "max": max(period2),
                "count": len(period2),
            },
            "comparison": {
                "mean_change_percent": change,
                "volatility_change_percent": volatility_change,
                "direction": "improved" if change < 0 else "degraded" if change > 0 else "unchanged",
            },
        }

    def _calculate_trend(
        self,
        values: np.ndarray,
    ) -> Tuple[TrendDirection, TrendStrength, float, float]:
        """Calculate trend direction and strength."""
        n = len(values)
        x = np.arange(n)

        # Linear regression
        x_mean = np.mean(x)
        y_mean = np.mean(values)

        numerator = np.sum((x - x_mean) * (values - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        slope = numerator / denominator if denominator != 0 else 0

        # Calculate R-squared
        y_pred = slope * x + (y_mean - slope * x_mean)
        ss_res = np.sum((values - y_pred) ** 2)
        ss_tot = np.sum((values - y_mean) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        # Determine direction
        relative_slope = slope * n / y_mean if y_mean != 0 else 0

        if abs(relative_slope) < 0.05:
            direction = TrendDirection.STABLE
        elif relative_slope > 0:
            direction = TrendDirection.INCREASING
        else:
            direction = TrendDirection.DECREASING

        # Check for volatility
        cv = np.std(values) / np.mean(values) if np.mean(values) != 0 else 0
        if cv > 0.5 and r_squared < 0.3:
            direction = TrendDirection.VOLATILE

        # Determine strength
        if r_squared > 0.7:
            strength = TrendStrength.STRONG
        elif r_squared > 0.4:
            strength = TrendStrength.MODERATE
        else:
            strength = TrendStrength.WEAK

        return direction, strength, float(slope), float(r_squared)

    def _detect_patterns(self, values: np.ndarray) -> List[str]:
        """Detect patterns in the data."""
        patterns = []

        # Check for spikes
        mean = np.mean(values)
        std = np.std(values)
        spikes = np.sum(np.abs(values - mean) > 2 * std)
        if spikes > len(values) * 0.1:
            patterns.append("frequent_spikes")

        # Check for cyclical pattern
        if len(values) >= 24:
            # Simple autocorrelation check
            autocorr_12 = self._autocorrelation(values, 12)
            autocorr_24 = self._autocorrelation(values, 24)
            if autocorr_12 > 0.5:
                patterns.append("12_hour_cycle")
            if autocorr_24 > 0.5:
                patterns.append("24_hour_cycle")

        # Check for plateau
        recent = values[-len(values) // 4:]
        if np.std(recent) < std * 0.5:
            patterns.append("plateau")

        # Check for rapid change
        diffs = np.diff(values)
        if np.max(np.abs(diffs)) > mean * 0.5:
            patterns.append("rapid_changes")

        return patterns

    def _detect_anomalies(self, values: np.ndarray) -> List[int]:
        """Detect anomalies using Z-score."""
        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return []

        z_scores = np.abs((values - mean) / std)
        anomaly_indices = np.where(z_scores > self.anomaly_threshold)[0]

        return anomaly_indices.tolist()

    def _detect_seasonality(self, values: np.ndarray) -> Optional[str]:
        """Detect seasonality period."""
        if len(values) < 48:
            return None

        # Check common periods
        for period, name in [(24, "daily"), (168, "weekly"), (12, "12_hour")]:
            if len(values) >= period * 2:
                autocorr = self._autocorrelation(values, period)
                if autocorr > 0.5:
                    return name

        return None

    def _generate_insights(
        self,
        metric_name: str,
        direction: TrendDirection,
        strength: TrendStrength,
        mean: float,
        std_dev: float,
        patterns: List[str],
        anomalies: List[int],
    ) -> List[str]:
        """Generate insights from analysis."""
        insights = []

        # Trend insight
        if direction == TrendDirection.INCREASING:
            insights.append(
                f"{metric_name} shows a {strength.value} increasing trend"
            )
        elif direction == TrendDirection.DECREASING:
            insights.append(
                f"{metric_name} shows a {strength.value} decreasing trend"
            )
        elif direction == TrendDirection.VOLATILE:
            insights.append(
                f"{metric_name} shows high volatility"
            )

        # Variability insight
        cv = std_dev / mean if mean != 0 else 0
        if cv > 0.3:
            insights.append(
                f"High variability detected (CV: {cv:.2f})"
            )

        # Pattern insights
        if "frequent_spikes" in patterns:
            insights.append("Frequent spikes detected - investigate causes")
        if "rapid_changes" in patterns:
            insights.append("Rapid changes observed - may indicate instability")
        if "plateau" in patterns:
            insights.append("Recent values show a plateau pattern")

        # Anomaly insight
        if len(anomalies) > 0:
            insights.append(
                f"{len(anomalies)} anomalies detected in the period"
            )

        return insights

    def _generate_recommendations(
        self,
        metric_name: str,
        direction: TrendDirection,
        strength: TrendStrength,
        mean: float,
        p95: float,
    ) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []

        if direction == TrendDirection.INCREASING and strength != TrendStrength.WEAK:
            recommendations.append(
                f"Consider scaling resources as {metric_name} is increasing"
            )
            if p95 > 80:
                recommendations.append(
                    "95th percentile exceeds 80% - immediate attention recommended"
                )

        if direction == TrendDirection.VOLATILE:
            recommendations.append(
                "Investigate sources of volatility and stabilize workload"
            )

        if mean > 70:
            recommendations.append(
                f"Average {metric_name} is high ({mean:.1f}%) - consider optimization"
            )

        if p95 > 90:
            recommendations.append(
                "Peak usage exceeds 90% - consider adding capacity"
            )

        return recommendations

    def _autocorrelation(self, x: np.ndarray, lag: int) -> float:
        """Calculate autocorrelation at given lag."""
        n = len(x)
        if lag >= n:
            return 0.0

        mean = np.mean(x)
        var = np.var(x)
        if var == 0:
            return 0.0

        cov = np.sum((x[:n - lag] - mean) * (x[lag:] - mean)) / n
        return cov / var

    def _align_time_series(
        self,
        data_a: List[MetricDataPoint],
        data_b: List[MetricDataPoint],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Align two time series by timestamp."""
        # Create dictionaries keyed by rounded timestamp
        def round_time(dt: datetime) -> datetime:
            return dt.replace(second=0, microsecond=0)

        dict_a = {round_time(d.timestamp): d.value for d in data_a}
        dict_b = {round_time(d.timestamp): d.value for d in data_b}

        # Find common timestamps
        common = sorted(set(dict_a.keys()) & set(dict_b.keys()))

        values_a = np.array([dict_a[t] for t in common])
        values_b = np.array([dict_b[t] for t in common])

        return values_a, values_b

    def _pearson_correlation(
        self,
        x: np.ndarray,
        y: np.ndarray,
    ) -> float:
        """Calculate Pearson correlation coefficient."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        x_mean = np.mean(x)
        y_mean = np.mean(y)

        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = math.sqrt(
            np.sum((x - x_mean) ** 2) * np.sum((y - y_mean) ** 2)
        )

        return numerator / denominator if denominator != 0 else 0.0

    def _t_distribution_cdf(self, t: float, df: int) -> float:
        """Approximate t-distribution CDF."""
        # Using normal approximation for large df
        if df > 30:
            return 0.5 * (1 + math.erf(t / math.sqrt(2)))

        # Simple approximation
        x = df / (df + t * t)
        return 1 - 0.5 * (x ** (df / 2))

    async def get_report(self, report_id: str) -> Optional[TrendReport]:
        """Get trend report by ID."""
        return self._reports.get(report_id)

    async def list_metrics(self) -> List[str]:
        """List all tracked metrics."""
        return list(self._metrics.keys())

    async def get_statistics(self) -> Dict[str, Any]:
        """Get analyzer statistics."""
        return {
            **self._stats,
            "metrics_tracked": len(self._metrics),
            "total_data_points": sum(
                len(data) for data in self._metrics.values()
            ),
        }

    async def shutdown(self) -> None:
        """Shutdown analyzer."""
        logger.info("Trend Analyzer shutdown complete")
