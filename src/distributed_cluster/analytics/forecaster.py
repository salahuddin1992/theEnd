# -*- coding: utf-8 -*-
"""
Resource Forecaster for NebulaCompute.

Forecasts resource usage for capacity planning.

نظام التنبؤ بالموارد للتخطيط.
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


class ForecastHorizon(str, Enum):
    """Forecast time horizon."""

    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass
class ResourceMetric:
    """Resource usage metric data point."""

    timestamp: datetime
    cpu_usage: float  # Percentage
    memory_usage: float  # Percentage
    gpu_usage: float  # Percentage
    network_in_mbps: float
    network_out_mbps: float
    disk_usage: float  # Percentage
    active_jobs: int
    queue_depth: int


@dataclass
class Forecast:
    """
    Resource usage forecast.

    توقعات استخدام الموارد.
    """

    forecast_id: str
    resource_type: str
    horizon: ForecastHorizon
    start_time: datetime
    end_time: datetime
    predictions: List[Tuple[datetime, float]]  # (timestamp, value)
    confidence_intervals: List[Tuple[float, float]]  # (lower, upper)
    confidence_level: float
    seasonality_detected: bool
    trend: str  # "increasing", "decreasing", "stable"
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "forecast_id": self.forecast_id,
            "resource_type": self.resource_type,
            "horizon": self.horizon.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "predictions": [
                {"timestamp": ts.isoformat(), "value": val}
                for ts, val in self.predictions
            ],
            "confidence_intervals": [
                {"lower": lower, "upper": upper}
                for lower, upper in self.confidence_intervals
            ],
            "confidence_level": self.confidence_level,
            "seasonality_detected": self.seasonality_detected,
            "trend": self.trend,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class CapacityRecommendation:
    """Capacity planning recommendation."""

    recommendation_id: str
    resource_type: str
    current_capacity: float
    predicted_peak: float
    recommended_capacity: float
    scale_by: float  # Percentage increase/decrease
    urgency: str  # "low", "medium", "high"
    reason: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "recommendation_id": self.recommendation_id,
            "resource_type": self.resource_type,
            "current_capacity": self.current_capacity,
            "predicted_peak": self.predicted_peak,
            "recommended_capacity": self.recommended_capacity,
            "scale_by": self.scale_by,
            "urgency": self.urgency,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }


class ResourceForecaster:
    """
    Resource usage forecaster for capacity planning.

    نظام التنبؤ بالموارد للتخطيط.

    Features:
    - Time series forecasting
    - Seasonality detection
    - Trend analysis
    - Capacity recommendations
    - Multi-horizon predictions
    """

    def __init__(
        self,
        history_days: int = 30,
        confidence_level: float = 0.95,
        seasonality_periods: Optional[List[int]] = None,
    ):
        """
        Initialize Resource Forecaster.

        Args:
            history_days: Days of history to keep
            confidence_level: Confidence level for intervals
            seasonality_periods: Seasonality periods to check (hours)
        """
        self.history_days = history_days
        self.confidence_level = confidence_level
        self.seasonality_periods = seasonality_periods or [24, 168]  # Daily, weekly

        # Storage
        self._metrics: List[ResourceMetric] = []
        self._forecasts: Dict[str, Forecast] = {}
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "forecasts_generated": 0,
            "recommendations_made": 0,
            "metrics_stored": 0,
        }

    async def add_metric(self, metric: ResourceMetric) -> None:
        """
        Add resource metric data point.

        إضافة نقطة بيانات للموارد.
        """
        async with self._lock:
            self._metrics.append(metric)
            self._stats["metrics_stored"] += 1

            # Cleanup old data
            cutoff = datetime.utcnow() - timedelta(days=self.history_days)
            self._metrics = [m for m in self._metrics if m.timestamp > cutoff]

    async def forecast(
        self,
        resource_type: str,
        horizon: ForecastHorizon,
        steps: Optional[int] = None,
    ) -> Forecast:
        """
        Generate resource usage forecast.

        توليد توقعات استخدام الموارد.
        """
        import uuid

        # Determine number of steps
        if steps is None:
            steps = self._get_default_steps(horizon)

        # Get historical data for resource
        history = await self._get_resource_history(resource_type)

        if len(history) < 24:  # Need at least 24 hours of data
            return await self._generate_naive_forecast(
                resource_type, horizon, steps
            )

        # Detect seasonality
        seasonality = await self._detect_seasonality(history)

        # Detect trend
        trend = await self._detect_trend(history)

        # Generate forecast using Holt-Winters or similar
        predictions, intervals = await self._generate_forecast(
            history, steps, seasonality, trend
        )

        # Create forecast object
        start_time = datetime.utcnow()
        step_duration = self._get_step_duration(horizon)
        end_time = start_time + step_duration * steps

        forecast = Forecast(
            forecast_id=str(uuid.uuid4()),
            resource_type=resource_type,
            horizon=horizon,
            start_time=start_time,
            end_time=end_time,
            predictions=[
                (start_time + step_duration * i, pred)
                for i, pred in enumerate(predictions)
            ],
            confidence_intervals=intervals,
            confidence_level=self.confidence_level,
            seasonality_detected=seasonality is not None,
            trend=trend,
        )

        async with self._lock:
            self._forecasts[forecast.forecast_id] = forecast
            self._stats["forecasts_generated"] += 1

        logger.info(
            f"Generated {horizon.value} forecast for {resource_type}: "
            f"trend={trend}, seasonality={seasonality is not None}"
        )

        return forecast

    async def get_capacity_recommendations(
        self,
        current_capacities: Dict[str, float],
        safety_margin: float = 0.2,
    ) -> List[CapacityRecommendation]:
        """
        Get capacity planning recommendations.

        الحصول على توصيات تخطيط السعة.
        """
        import uuid

        recommendations = []

        for resource_type, current_capacity in current_capacities.items():
            # Get weekly forecast
            forecast = await self.forecast(
                resource_type, ForecastHorizon.WEEK
            )

            if not forecast.predictions:
                continue

            # Find predicted peak
            values = [v for _, v in forecast.predictions]
            predicted_peak = max(values)
            sum(values) / len(values)

            # Calculate recommended capacity with safety margin
            recommended = predicted_peak * (1 + safety_margin)

            # Determine scale factor
            scale_by = ((recommended - current_capacity) / current_capacity * 100
                        if current_capacity > 0 else 100)

            # Determine urgency
            if predicted_peak > current_capacity:
                urgency = "high"
                reason = f"Predicted peak ({predicted_peak:.1f}%) exceeds current capacity"
            elif predicted_peak > current_capacity * 0.8:
                urgency = "medium"
                reason = f"Predicted to reach {predicted_peak/current_capacity*100:.0f}% of capacity"
            else:
                urgency = "low"
                reason = "Capacity is sufficient for predicted usage"

            recommendation = CapacityRecommendation(
                recommendation_id=str(uuid.uuid4()),
                resource_type=resource_type,
                current_capacity=current_capacity,
                predicted_peak=predicted_peak,
                recommended_capacity=recommended,
                scale_by=scale_by,
                urgency=urgency,
                reason=reason,
            )

            recommendations.append(recommendation)
            self._stats["recommendations_made"] += 1

        return recommendations

    async def _get_resource_history(
        self,
        resource_type: str,
    ) -> List[Tuple[datetime, float]]:
        """Get historical values for a resource type."""
        history = []

        for metric in self._metrics:
            value = getattr(metric, f"{resource_type}_usage", None)
            if value is None and resource_type == "cpu":
                value = metric.cpu_usage
            elif value is None and resource_type == "memory":
                value = metric.memory_usage
            elif value is None and resource_type == "gpu":
                value = metric.gpu_usage
            elif value is None and resource_type == "disk":
                value = metric.disk_usage

            if value is not None:
                history.append((metric.timestamp, value))

        return sorted(history, key=lambda x: x[0])

    async def _detect_seasonality(
        self,
        history: List[Tuple[datetime, float]],
    ) -> Optional[int]:
        """Detect seasonality in the data."""
        if len(history) < 48:  # Need at least 2 days
            return None

        values = np.array([v for _, v in history])

        # Check for daily and weekly seasonality
        for period in self.seasonality_periods:
            if len(values) >= period * 2:
                # Calculate autocorrelation at this lag
                autocorr = self._autocorrelation(values, period)
                if autocorr > 0.5:  # Strong correlation
                    return period

        return None

    async def _detect_trend(
        self,
        history: List[Tuple[datetime, float]],
    ) -> str:
        """Detect trend in the data."""
        if len(history) < 2:
            return "stable"

        values = [v for _, v in history]

        # Simple linear regression
        n = len(values)
        x = np.arange(n)
        y = np.array(values)

        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (
            n * np.sum(x ** 2) - np.sum(x) ** 2
        )

        # Determine trend based on slope relative to mean
        mean = np.mean(y)
        relative_slope = slope * n / mean if mean > 0 else 0

        if relative_slope > 0.1:
            return "increasing"
        elif relative_slope < -0.1:
            return "decreasing"
        else:
            return "stable"

    async def _generate_forecast(
        self,
        history: List[Tuple[datetime, float]],
        steps: int,
        seasonality: Optional[int],
        trend: str,
    ) -> Tuple[List[float], List[Tuple[float, float]]]:
        """Generate forecast using exponential smoothing."""
        values = np.array([v for _, v in history])

        # Simple exponential smoothing with trend

        n = len(values)
        level = values[0]
        trend_value = 0 if trend == "stable" else (values[-1] - values[0]) / n

        predictions = []
        for i in range(steps):
            # Forecast
            forecast = level + (i + 1) * trend_value

            # Add seasonality if detected
            if seasonality and n >= seasonality:
                seasonal_idx = (n + i) % seasonality
                if seasonal_idx < n:
                    seasonal_factor = values[seasonal_idx] / np.mean(values[:seasonality])
                    forecast *= seasonal_factor

            predictions.append(max(0, min(100, forecast)))

        # Calculate confidence intervals
        std = np.std(values)
        z = 1.96  # 95% confidence

        intervals = []
        for i, pred in enumerate(predictions):
            # Wider intervals for further predictions
            margin = std * z * math.sqrt(1 + 0.1 * i)
            lower = max(0, pred - margin)
            upper = min(100, pred + margin)
            intervals.append((lower, upper))

        return predictions, intervals

    async def _generate_naive_forecast(
        self,
        resource_type: str,
        horizon: ForecastHorizon,
        steps: int,
    ) -> Forecast:
        """Generate naive forecast when insufficient data."""
        import uuid

        start_time = datetime.utcnow()
        step_duration = self._get_step_duration(horizon)

        # Use simple moving average or default
        history = await self._get_resource_history(resource_type)
        if history:
            avg_value = sum(v for _, v in history) / len(history)
        else:
            avg_value = 50.0  # Default

        predictions = [(start_time + step_duration * i, avg_value) for i in range(steps)]
        intervals = [(avg_value * 0.5, min(100, avg_value * 1.5)) for _ in range(steps)]

        return Forecast(
            forecast_id=str(uuid.uuid4()),
            resource_type=resource_type,
            horizon=horizon,
            start_time=start_time,
            end_time=start_time + step_duration * steps,
            predictions=predictions,
            confidence_intervals=intervals,
            confidence_level=0.5,  # Low confidence
            seasonality_detected=False,
            trend="stable",
            metadata={"method": "naive"},
        )

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

    def _get_default_steps(self, horizon: ForecastHorizon) -> int:
        """Get default number of forecast steps."""
        return {
            ForecastHorizon.HOUR: 12,   # 12 x 5-min intervals
            ForecastHorizon.DAY: 24,    # 24 hours
            ForecastHorizon.WEEK: 7,    # 7 days
            ForecastHorizon.MONTH: 30,  # 30 days
        }.get(horizon, 24)

    def _get_step_duration(self, horizon: ForecastHorizon) -> timedelta:
        """Get step duration for horizon."""
        return {
            ForecastHorizon.HOUR: timedelta(minutes=5),
            ForecastHorizon.DAY: timedelta(hours=1),
            ForecastHorizon.WEEK: timedelta(days=1),
            ForecastHorizon.MONTH: timedelta(days=1),
        }.get(horizon, timedelta(hours=1))

    async def get_forecast(self, forecast_id: str) -> Optional[Forecast]:
        """Get forecast by ID."""
        return self._forecasts.get(forecast_id)

    async def get_statistics(self) -> Dict[str, Any]:
        """Get forecaster statistics."""
        return {
            **self._stats,
            "history_days": self.history_days,
            "confidence_level": self.confidence_level,
        }

    async def shutdown(self) -> None:
        """Shutdown forecaster."""
        logger.info("Resource Forecaster shutdown complete")
