# -*- coding: utf-8 -*-
"""
Capacity Planning and Forecasting for NebulaCompute.

Provides intelligent capacity planning, resource forecasting,
and scaling recommendations for distributed systems.

تخطيط السعة والتنبؤ.

Features:
- Resource usage trend analysis
- Capacity forecasting with multiple models
- Scaling recommendations
- Peak demand prediction
- Cost-aware capacity planning
- Growth rate analysis
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class GrowthModel(str, Enum):
    """Growth projection model."""

    LINEAR = "linear"  # y = mx + b
    EXPONENTIAL = "exponential"  # y = a * e^(bx)
    LOGARITHMIC = "logarithmic"  # y = a * ln(x) + b
    POLYNOMIAL = "polynomial"  # y = ax^2 + bx + c
    SEASONAL = "seasonal"  # Seasonal decomposition


class ScalingAction(str, Enum):
    """Recommended scaling action."""

    SCALE_UP = "scale_up"  # Add more resources
    SCALE_DOWN = "scale_down"  # Remove resources
    SCALE_OUT = "scale_out"  # Add more instances
    SCALE_IN = "scale_in"  # Remove instances
    NO_ACTION = "no_action"  # Current capacity is adequate
    REBALANCE = "rebalance"  # Redistribute workload


class ResourceType(str, Enum):
    """Resource type for capacity planning."""

    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    STORAGE = "storage"
    NETWORK = "network"
    WORKERS = "workers"


@dataclass
class ResourceTrend:
    """
    Resource usage trend analysis.

    تحليل اتجاه استخدام الموارد.
    """

    resource_type: ResourceType
    current_usage: float
    average_usage: float
    peak_usage: float
    min_usage: float
    growth_rate: float  # Per day
    volatility: float  # Standard deviation
    trend_direction: str  # "increasing", "decreasing", "stable"
    confidence: float  # 0.0 - 1.0
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_type": self.resource_type.value,
            "current_usage": self.current_usage,
            "average_usage": self.average_usage,
            "peak_usage": self.peak_usage,
            "min_usage": self.min_usage,
            "growth_rate": self.growth_rate,
            "volatility": self.volatility,
            "trend_direction": self.trend_direction,
            "confidence": self.confidence,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class CapacityForecast:
    """
    Capacity forecast result.

    نتيجة التنبؤ بالسعة.
    """

    forecast_id: str
    resource_type: ResourceType
    current_capacity: float
    forecasted_demand: float
    forecast_date: datetime
    confidence_interval: Tuple[float, float]
    confidence: float
    model_used: GrowthModel
    time_to_exhaustion: Optional[timedelta] = None
    recommended_capacity: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def capacity_gap(self) -> float:
        """Calculate gap between forecasted demand and current capacity."""
        return self.forecasted_demand - self.current_capacity

    @property
    def utilization_forecast(self) -> float:
        """Calculate forecasted utilization."""
        if self.current_capacity > 0:
            return min(1.0, self.forecasted_demand / self.current_capacity)
        return 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "forecast_id": self.forecast_id,
            "resource_type": self.resource_type.value,
            "current_capacity": self.current_capacity,
            "forecasted_demand": self.forecasted_demand,
            "forecast_date": self.forecast_date.isoformat(),
            "confidence_interval": list(self.confidence_interval),
            "confidence": self.confidence,
            "model_used": self.model_used.value,
            "time_to_exhaustion": str(self.time_to_exhaustion) if self.time_to_exhaustion else None,
            "recommended_capacity": self.recommended_capacity,
            "capacity_gap": self.capacity_gap,
            "utilization_forecast": self.utilization_forecast,
            "metadata": self.metadata,
        }


@dataclass
class CapacityRecommendation:
    """
    Capacity scaling recommendation.

    توصية بتوسيع السعة.
    """

    recommendation_id: str
    action: ScalingAction
    resource_type: ResourceType
    current_value: float
    recommended_value: float
    urgency: str  # "immediate", "soon", "planned"
    reason: str
    estimated_cost_change: float  # Percentage change
    confidence: float
    valid_until: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def change_percentage(self) -> float:
        """Calculate percentage change."""
        if self.current_value > 0:
            return ((self.recommended_value - self.current_value) /
                    self.current_value * 100)
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "recommendation_id": self.recommendation_id,
            "action": self.action.value,
            "resource_type": self.resource_type.value,
            "current_value": self.current_value,
            "recommended_value": self.recommended_value,
            "change_percentage": self.change_percentage,
            "urgency": self.urgency,
            "reason": self.reason,
            "estimated_cost_change": self.estimated_cost_change,
            "confidence": self.confidence,
            "valid_until": self.valid_until.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class CapacityConfig:
    """Capacity planning configuration."""

    # Data collection
    history_days: int = 30
    sample_interval_minutes: int = 5
    min_samples_for_forecast: int = 100

    # Thresholds
    target_utilization: float = 0.7  # 70% target
    critical_utilization: float = 0.9  # 90% critical
    low_utilization: float = 0.3  # 30% underutilized

    # Forecast settings
    forecast_horizon_days: int = 7
    confidence_level: float = 0.95
    safety_margin: float = 1.2  # 20% safety margin

    # Cost optimization
    enable_cost_optimization: bool = True
    cost_weight: float = 0.3  # Balance between cost and performance

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "history_days": self.history_days,
            "sample_interval_minutes": self.sample_interval_minutes,
            "min_samples_for_forecast": self.min_samples_for_forecast,
            "target_utilization": self.target_utilization,
            "critical_utilization": self.critical_utilization,
            "low_utilization": self.low_utilization,
            "forecast_horizon_days": self.forecast_horizon_days,
            "confidence_level": self.confidence_level,
            "safety_margin": self.safety_margin,
            "enable_cost_optimization": self.enable_cost_optimization,
            "cost_weight": self.cost_weight,
        }


class CapacityPlanner:
    """
    Intelligent capacity planning engine.

    محرك تخطيط السعة الذكي.

    Features:
    - Multi-resource capacity tracking
    - Multiple forecasting models
    - Automatic model selection
    - Scaling recommendations
    - Peak demand prediction
    - Cost-aware planning
    """

    def __init__(
        self,
        config: Optional[CapacityConfig] = None,
        metrics_provider: Optional[Callable] = None,
        cost_provider: Optional[Callable[[ResourceType, float], float]] = None,
    ):
        """
        Initialize CapacityPlanner.

        Args:
            config: Capacity planning configuration
            metrics_provider: Function to get current resource metrics
            cost_provider: Function to get cost for resource changes
        """
        self.config = config or CapacityConfig()
        self.metrics_provider = metrics_provider
        self.cost_provider = cost_provider

        # Historical data per resource type
        max_samples = (
            self.config.history_days * 24 * 60 //
            self.config.sample_interval_minutes
        )
        self._history: Dict[ResourceType, Deque[Tuple[datetime, float]]] = {
            rt: deque(maxlen=max_samples) for rt in ResourceType
        }

        # Current capacity per resource
        self._capacity: Dict[ResourceType, float] = {
            rt: 0.0 for rt in ResourceType
        }

        # Trends
        self._trends: Dict[ResourceType, ResourceTrend] = {}

        # Forecasts
        self._forecasts: Dict[ResourceType, List[CapacityForecast]] = {
            rt: [] for rt in ResourceType
        }

        # State
        self._running = False
        self._collection_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "samples_collected": 0,
            "forecasts_generated": 0,
            "recommendations_made": 0,
        }

    async def start(self) -> None:
        """Start capacity planning."""
        if self._running:
            return

        self._running = True
        self._collection_task = asyncio.create_task(self._collection_loop())
        logger.info("CapacityPlanner started")

    async def stop(self) -> None:
        """Stop capacity planning."""
        self._running = False
        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
        logger.info("CapacityPlanner stopped")

    async def _collection_loop(self) -> None:
        """Main data collection loop."""
        interval = self.config.sample_interval_minutes * 60

        while self._running:
            try:
                await self._collect_metrics()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metric collection error: {e}")
                await asyncio.sleep(interval)

    async def _collect_metrics(self) -> None:
        """Collect current resource metrics."""
        if not self.metrics_provider:
            return

        try:
            metrics = self.metrics_provider()
            if asyncio.iscoroutine(metrics):
                metrics = await metrics

            now = datetime.now(timezone.utc)

            async with self._lock:
                for resource_type, value in metrics.items():
                    if isinstance(resource_type, str):
                        try:
                            resource_type = ResourceType(resource_type)
                        except ValueError:
                            continue

                    if resource_type in self._history:
                        self._history[resource_type].append((now, value))
                        self._stats["samples_collected"] += 1

        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")

    async def record_usage(
        self,
        resource_type: ResourceType,
        value: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Record a resource usage data point.

        تسجيل نقطة بيانات استخدام الموارد.
        """
        timestamp = timestamp or datetime.now(timezone.utc)

        async with self._lock:
            self._history[resource_type].append((timestamp, value))
            self._stats["samples_collected"] += 1

    async def set_capacity(
        self,
        resource_type: ResourceType,
        capacity: float,
    ) -> None:
        """Set current capacity for a resource type."""
        async with self._lock:
            self._capacity[resource_type] = capacity

    async def analyze_trend(
        self,
        resource_type: ResourceType,
    ) -> Optional[ResourceTrend]:
        """
        Analyze usage trend for a resource.

        تحليل اتجاه الاستخدام لمورد.
        """
        history = list(self._history[resource_type])

        if len(history) < 10:
            return None

        values = [v for _, v in history]
        [t.timestamp() for t, _ in history]

        # Calculate basic statistics
        current = values[-1]
        average = statistics.mean(values)
        peak = max(values)
        minimum = min(values)
        volatility = statistics.stdev(values) if len(values) > 1 else 0.0

        # Calculate growth rate using linear regression
        growth_rate = 0.0
        trend_direction = "stable"
        confidence = 0.5

        if len(values) >= 10:
            # Simple linear regression
            x = np.array(range(len(values)))
            y = np.array(values)
            slope, intercept = np.polyfit(x, y, 1)

            # Convert to daily growth rate
            samples_per_day = 24 * 60 / self.config.sample_interval_minutes
            growth_rate = slope * samples_per_day

            # Determine direction
            if growth_rate > 0.01 * average:
                trend_direction = "increasing"
            elif growth_rate < -0.01 * average:
                trend_direction = "decreasing"
            else:
                trend_direction = "stable"

            # Calculate R-squared for confidence
            y_pred = slope * x + intercept
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            confidence = max(0.0, min(1.0, r_squared))

        trend = ResourceTrend(
            resource_type=resource_type,
            current_usage=current,
            average_usage=average,
            peak_usage=peak,
            min_usage=minimum,
            growth_rate=growth_rate,
            volatility=volatility,
            trend_direction=trend_direction,
            confidence=confidence,
        )

        self._trends[resource_type] = trend
        return trend

    async def forecast(
        self,
        resource_type: ResourceType,
        horizon_days: Optional[int] = None,
        model: Optional[GrowthModel] = None,
    ) -> Optional[CapacityForecast]:
        """
        Forecast future resource demand.

        التنبؤ بالطلب المستقبلي على الموارد.
        """
        import uuid

        horizon_days = horizon_days or self.config.forecast_horizon_days
        history = list(self._history[resource_type])

        if len(history) < self.config.min_samples_for_forecast:
            return None

        values = np.array([v for _, v in history])
        capacity = self._capacity.get(resource_type, 0.0)

        # Auto-select model if not specified
        if model is None:
            model = await self._select_best_model(values)

        # Generate forecast
        forecast_value = 0.0
        confidence_interval = (0.0, 0.0)

        if model == GrowthModel.LINEAR:
            forecast_value, confidence_interval = self._forecast_linear(
                values, horizon_days
            )
        elif model == GrowthModel.EXPONENTIAL:
            forecast_value, confidence_interval = self._forecast_exponential(
                values, horizon_days
            )
        elif model == GrowthModel.POLYNOMIAL:
            forecast_value, confidence_interval = self._forecast_polynomial(
                values, horizon_days
            )
        else:
            # Default to linear
            forecast_value, confidence_interval = self._forecast_linear(
                values, horizon_days
            )

        # Calculate time to exhaustion
        time_to_exhaustion = None
        if capacity > 0 and forecast_value > capacity:
            # Estimate when we'll hit capacity
            current = values[-1]
            if current < capacity:
                trend = await self.analyze_trend(resource_type)
                if trend and trend.growth_rate > 0:
                    days_to_exhaust = (capacity - current) / trend.growth_rate
                    time_to_exhaustion = timedelta(days=days_to_exhaust)

        # Recommended capacity with safety margin
        recommended_capacity = forecast_value * self.config.safety_margin

        forecast = CapacityForecast(
            forecast_id=str(uuid.uuid4()),
            resource_type=resource_type,
            current_capacity=capacity,
            forecasted_demand=forecast_value,
            forecast_date=datetime.now(timezone.utc) + timedelta(days=horizon_days),
            confidence_interval=confidence_interval,
            confidence=0.7,  # Base confidence
            model_used=model,
            time_to_exhaustion=time_to_exhaustion,
            recommended_capacity=recommended_capacity,
        )

        # Store forecast
        async with self._lock:
            self._forecasts[resource_type].append(forecast)
            # Keep only last 100 forecasts
            if len(self._forecasts[resource_type]) > 100:
                self._forecasts[resource_type] = self._forecasts[resource_type][-100:]
            self._stats["forecasts_generated"] += 1

        return forecast

    def _forecast_linear(
        self,
        values: np.ndarray,
        horizon_days: int,
    ) -> Tuple[float, Tuple[float, float]]:
        """Linear forecast."""
        x = np.array(range(len(values)))
        slope, intercept = np.polyfit(x, values, 1)

        # Forecast point
        samples_per_day = 24 * 60 / self.config.sample_interval_minutes
        future_x = len(values) + horizon_days * samples_per_day
        forecast = slope * future_x + intercept

        # Confidence interval (simplified)
        std = np.std(values)
        margin = std * 2
        return forecast, (forecast - margin, forecast + margin)

    def _forecast_exponential(
        self,
        values: np.ndarray,
        horizon_days: int,
    ) -> Tuple[float, Tuple[float, float]]:
        """Exponential forecast."""
        # Use log transformation for exponential fit
        positive_values = np.maximum(values, 1e-10)
        log_values = np.log(positive_values)

        x = np.array(range(len(values)))
        slope, intercept = np.polyfit(x, log_values, 1)

        # Forecast point
        samples_per_day = 24 * 60 / self.config.sample_interval_minutes
        future_x = len(values) + horizon_days * samples_per_day
        log_forecast = slope * future_x + intercept
        forecast = np.exp(log_forecast)

        # Confidence interval
        std = np.std(values)
        margin = std * 2.5  # Wider for exponential
        return forecast, (max(0, forecast - margin), forecast + margin)

    def _forecast_polynomial(
        self,
        values: np.ndarray,
        horizon_days: int,
    ) -> Tuple[float, Tuple[float, float]]:
        """Polynomial (quadratic) forecast."""
        x = np.array(range(len(values)))
        coeffs = np.polyfit(x, values, 2)

        # Forecast point
        samples_per_day = 24 * 60 / self.config.sample_interval_minutes
        future_x = len(values) + horizon_days * samples_per_day
        forecast = np.polyval(coeffs, future_x)

        # Confidence interval
        std = np.std(values)
        margin = std * 2
        return max(0, forecast), (max(0, forecast - margin), forecast + margin)

    async def _select_best_model(self, values: np.ndarray) -> GrowthModel:
        """Select best forecasting model based on data characteristics."""
        if len(values) < 20:
            return GrowthModel.LINEAR

        # Calculate R-squared for different models
        x = np.array(range(len(values)))

        # Linear fit
        linear_coef = np.polyfit(x, values, 1)
        linear_pred = np.polyval(linear_coef, x)
        linear_r2 = self._calculate_r_squared(values, linear_pred)

        # Polynomial fit
        poly_coef = np.polyfit(x, values, 2)
        poly_pred = np.polyval(poly_coef, x)
        poly_r2 = self._calculate_r_squared(values, poly_pred)

        # Choose best
        if poly_r2 > linear_r2 + 0.1:  # Significant improvement
            return GrowthModel.POLYNOMIAL
        return GrowthModel.LINEAR

    def _calculate_r_squared(
        self,
        actual: np.ndarray,
        predicted: np.ndarray,
    ) -> float:
        """Calculate R-squared value."""
        ss_res = np.sum((actual - predicted) ** 2)
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)
        return 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    async def get_recommendations(
        self,
        resource_types: Optional[List[ResourceType]] = None,
    ) -> List[CapacityRecommendation]:
        """
        Get scaling recommendations for resources.

        الحصول على توصيات التوسع للموارد.
        """
        import uuid

        resource_types = resource_types or list(ResourceType)
        recommendations = []

        for resource_type in resource_types:
            # Analyze trend
            trend = await self.analyze_trend(resource_type)
            if not trend:
                continue

            # Get forecast
            forecast = await self.forecast(resource_type)
            if not forecast:
                continue

            capacity = self._capacity.get(resource_type, 0.0)
            if capacity <= 0:
                continue

            utilization = trend.current_usage / capacity

            # Determine action
            action = ScalingAction.NO_ACTION
            urgency = "planned"
            reason = ""
            recommended_value = capacity

            if utilization >= self.config.critical_utilization:
                action = ScalingAction.SCALE_UP
                urgency = "immediate"
                reason = f"Critical utilization ({utilization:.1%})"
                recommended_value = capacity * 1.5

            elif utilization >= self.config.target_utilization:
                if trend.trend_direction == "increasing":
                    action = ScalingAction.SCALE_UP
                    urgency = "soon"
                    reason = f"High utilization ({utilization:.1%}) with increasing trend"
                    recommended_value = capacity * 1.3

            elif utilization < self.config.low_utilization:
                if trend.trend_direction != "increasing":
                    action = ScalingAction.SCALE_DOWN
                    urgency = "planned"
                    reason = f"Low utilization ({utilization:.1%})"
                    recommended_value = capacity * 0.7

            # Check time to exhaustion
            if (forecast.time_to_exhaustion and
                    forecast.time_to_exhaustion < timedelta(days=7)):
                action = ScalingAction.SCALE_UP
                urgency = "soon"
                reason = f"Capacity exhaustion in {forecast.time_to_exhaustion}"
                recommended_value = forecast.recommended_capacity

            if action == ScalingAction.NO_ACTION:
                continue

            # Calculate cost impact
            cost_change = 0.0
            if self.cost_provider:
                try:
                    current_cost = self.cost_provider(resource_type, capacity)
                    new_cost = self.cost_provider(resource_type, recommended_value)
                    cost_change = ((new_cost - current_cost) / current_cost * 100
                                   if current_cost > 0 else 0.0)
                except Exception:
                    pass

            recommendation = CapacityRecommendation(
                recommendation_id=str(uuid.uuid4()),
                action=action,
                resource_type=resource_type,
                current_value=capacity,
                recommended_value=recommended_value,
                urgency=urgency,
                reason=reason,
                estimated_cost_change=cost_change,
                confidence=trend.confidence,
                valid_until=datetime.now(timezone.utc) + timedelta(hours=24),
            )

            recommendations.append(recommendation)
            self._stats["recommendations_made"] += 1

        return recommendations

    async def get_peak_prediction(
        self,
        resource_type: ResourceType,
        hours_ahead: int = 24,
    ) -> Dict[str, Any]:
        """
        Predict peak demand for the next N hours.

        توقع ذروة الطلب للساعات القادمة.
        """
        history = list(self._history[resource_type])

        if len(history) < 24:
            return {
                "resource_type": resource_type.value,
                "insufficient_data": True,
            }

        # Group by hour of day
        hourly_peaks: Dict[int, List[float]] = {h: [] for h in range(24)}
        for timestamp, value in history:
            hour = timestamp.hour
            hourly_peaks[hour].append(value)

        # Find peak hours
        peak_by_hour = {
            h: max(values) if values else 0.0
            for h, values in hourly_peaks.items()
        }

        # Predict peak for next N hours
        now = datetime.now(timezone.utc)
        future_hours = [(now + timedelta(hours=i)).hour for i in range(hours_ahead)]
        predicted_peaks = [peak_by_hour.get(h, 0.0) for h in future_hours]

        return {
            "resource_type": resource_type.value,
            "current_hour": now.hour,
            "hours_ahead": hours_ahead,
            "predicted_max": max(predicted_peaks) if predicted_peaks else 0.0,
            "peak_hour": future_hours[predicted_peaks.index(max(predicted_peaks))]
            if predicted_peaks else None,
            "hourly_predictions": list(zip(future_hours, predicted_peaks)),
        }

    async def get_statistics(self) -> Dict[str, Any]:
        """Get planner statistics."""
        return {
            **self._stats,
            "resources_tracked": len([h for h in self._history.values() if h]),
            "total_samples": sum(len(h) for h in self._history.values()),
            "config": self.config.to_dict(),
            "running": self._running,
        }

    async def get_trend_summary(self) -> Dict[str, Any]:
        """Get summary of all resource trends."""
        trends = {}
        for resource_type in ResourceType:
            trend = await self.analyze_trend(resource_type)
            if trend:
                trends[resource_type.value] = trend.to_dict()
        return trends

    async def shutdown(self) -> None:
        """Shutdown capacity planner."""
        await self.stop()
        logger.info("CapacityPlanner shutdown complete")


# Convenience function to create a pre-configured capacity planner
def create_capacity_planner(
    target_utilization: float = 0.7,
    history_days: int = 30,
    forecast_days: int = 7,
) -> CapacityPlanner:
    """
    Create a pre-configured capacity planner.

    إنشاء مخطط سعة مُعد مسبقًا.
    """
    config = CapacityConfig(
        target_utilization=target_utilization,
        history_days=history_days,
        forecast_horizon_days=forecast_days,
    )
    return CapacityPlanner(config=config)
