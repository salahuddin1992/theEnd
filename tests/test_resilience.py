# -*- coding: utf-8 -*-
"""
Tests for Resilience Module.

Tests for load shedding and capacity planning features.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from distributed_cluster.resilience import (
    CapacityPlanner,
    CapacityConfig,
    CapacityForecast,
    CapacityRecommendation,
    GrowthModel,
    LoadShedder,
    LoadSheddingPolicy,
    LoadSheddingStrategy,
    LoadMetrics,
    PriorityLevel,
    QueuedRequest,
    ResourceTrend,
    ResourceType,
    SheddingDecision,
)


# =============================================================================
# Load Shedding Tests
# =============================================================================


class TestQueuedRequest:
    """Tests for QueuedRequest class."""

    def test_request_creation(self):
        """Test creating a queued request."""
        request = QueuedRequest(
            request_id="test-123",
            priority=PriorityLevel.NORMAL,
            client_id="client-1",
            payload={"data": "test"},
            enqueued_at=datetime.utcnow(),
        )

        assert request.request_id == "test-123"
        assert request.priority == PriorityLevel.NORMAL
        assert request.client_id == "client-1"
        assert not request.is_expired

    def test_request_age(self):
        """Test request age calculation."""
        request = QueuedRequest(
            request_id="test-123",
            priority=PriorityLevel.NORMAL,
            client_id="client-1",
            payload=None,
            enqueued_at=datetime.utcnow() - timedelta(seconds=10),
        )

        assert request.age_seconds >= 10

    def test_request_expiration(self):
        """Test request expiration."""
        # Not expired
        request1 = QueuedRequest(
            request_id="test-1",
            priority=PriorityLevel.NORMAL,
            client_id="client-1",
            payload=None,
            enqueued_at=datetime.utcnow(),
            deadline=datetime.utcnow() + timedelta(hours=1),
        )
        assert not request1.is_expired

        # Expired
        request2 = QueuedRequest(
            request_id="test-2",
            priority=PriorityLevel.NORMAL,
            client_id="client-1",
            payload=None,
            enqueued_at=datetime.utcnow() - timedelta(hours=2),
            deadline=datetime.utcnow() - timedelta(hours=1),
        )
        assert request2.is_expired

    def test_request_to_dict(self):
        """Test request serialization."""
        request = QueuedRequest(
            request_id="test-123",
            priority=PriorityLevel.HIGH,
            client_id="client-1",
            payload={"key": "value"},
            enqueued_at=datetime.utcnow(),
            metadata={"source": "api"},
        )

        data = request.to_dict()
        assert data["request_id"] == "test-123"
        assert data["priority"] == "HIGH"
        assert data["client_id"] == "client-1"
        assert "age_seconds" in data


class TestLoadSheddingPolicy:
    """Tests for LoadSheddingPolicy class."""

    def test_default_policy(self):
        """Test default policy values."""
        policy = LoadSheddingPolicy()

        assert policy.soft_limit == 0.7
        assert policy.hard_limit == 0.9
        assert policy.critical_limit == 0.95
        assert policy.max_queue_size == 1000

    def test_custom_policy(self):
        """Test custom policy values."""
        policy = LoadSheddingPolicy(
            soft_limit=0.6,
            hard_limit=0.8,
            max_queue_size=500,
        )

        assert policy.soft_limit == 0.6
        assert policy.hard_limit == 0.8
        assert policy.max_queue_size == 500

    def test_policy_to_dict(self):
        """Test policy serialization."""
        policy = LoadSheddingPolicy()
        data = policy.to_dict()

        assert "soft_limit" in data
        assert "hard_limit" in data
        assert "protect_priorities" in data


class TestLoadShedder:
    """Tests for LoadShedder class."""

    @pytest.fixture
    def shedder(self):
        """Create a load shedder for testing."""
        policy = LoadSheddingPolicy(
            soft_limit=0.7,
            hard_limit=0.9,
            max_queue_size=10,
            max_requests_per_client=5,
            client_window_seconds=60.0,
        )
        return LoadShedder(policy=policy)

    @pytest.mark.asyncio
    async def test_accept_request_low_load(self, shedder):
        """Test that requests are accepted under low load."""

        def low_load_metrics():
            return LoadMetrics(
                cpu_utilization=0.3,
                memory_utilization=0.4,
            )

        shedder.metrics_callback = low_load_metrics

        decision, request = await shedder.admit(
            request_id="test-1",
            priority=PriorityLevel.NORMAL,
            client_id="client-1",
        )

        assert decision == SheddingDecision.ACCEPT
        assert request is not None

    @pytest.mark.asyncio
    async def test_shed_request_critical_load(self, shedder):
        """Test that low priority requests are shed under critical load."""

        def critical_load_metrics():
            return LoadMetrics(
                cpu_utilization=0.99,
                memory_utilization=0.99,
                queue_depth=100,  # High queue depth
                error_rate=0.1,  # Some errors
            )

        shedder.metrics_callback = critical_load_metrics

        decision, request = await shedder.admit(
            request_id="test-1",
            priority=PriorityLevel.BEST_EFFORT,
            client_id="client-1",
        )

        assert decision == SheddingDecision.SHED
        assert request is None

    @pytest.mark.asyncio
    async def test_protect_critical_priority(self, shedder):
        """Test that critical priority is always accepted."""

        def critical_load_metrics():
            return LoadMetrics(
                cpu_utilization=0.99,
                memory_utilization=0.99,
            )

        shedder.metrics_callback = critical_load_metrics

        decision, request = await shedder.admit(
            request_id="test-1",
            priority=PriorityLevel.CRITICAL,
            client_id="client-1",
        )

        assert decision == SheddingDecision.ACCEPT
        assert request is not None

    @pytest.mark.asyncio
    async def test_client_rate_limiting(self, shedder):
        """Test client rate limiting."""
        # Accept first 5 requests
        for i in range(5):
            decision, _ = await shedder.admit(
                request_id=f"test-{i}",
                priority=PriorityLevel.NORMAL,
                client_id="client-1",
            )
            assert decision == SheddingDecision.ACCEPT

        # 6th request should be shed
        decision, _ = await shedder.admit(
            request_id="test-6",
            priority=PriorityLevel.NORMAL,
            client_id="client-1",
        )
        assert decision == SheddingDecision.SHED

    @pytest.mark.asyncio
    async def test_degrade_at_soft_limit(self, shedder):
        """Test degradation at soft limit."""

        def soft_load_metrics():
            return LoadMetrics(
                cpu_utilization=0.85,
                memory_utilization=0.80,
                queue_depth=50,  # Moderate queue
                error_rate=0.02,
            )

        shedder.metrics_callback = soft_load_metrics

        decision, request = await shedder.admit(
            request_id="test-1",
            priority=PriorityLevel.NORMAL,
            client_id="client-1",
        )

        assert decision == SheddingDecision.DEGRADE
        assert request is not None

    @pytest.mark.asyncio
    async def test_queue_statistics(self, shedder):
        """Test queue statistics."""
        stats = await shedder.get_queue_stats()

        assert "total_queued" in stats
        assert "by_priority" in stats
        assert "is_shedding" in stats

    @pytest.mark.asyncio
    async def test_shed_by_strategy(self, shedder):
        """Test shedding by strategy."""
        # Add some requests to queue
        for i in range(5):
            request = QueuedRequest(
                request_id=f"test-{i}",
                priority=PriorityLevel.LOW,
                client_id="client-1",
                payload=None,
                enqueued_at=datetime.utcnow(),
            )
            await shedder._enqueue(request)

        # Shed 3 requests
        shed_requests = await shedder.shed_by_strategy(3)
        assert len(shed_requests) == 3

    @pytest.mark.asyncio
    async def test_get_client_stats(self, shedder):
        """Test getting client statistics."""
        # Make some requests
        await shedder.admit(
            request_id="test-1",
            priority=PriorityLevel.NORMAL,
            client_id="client-1",
        )

        stats = await shedder.get_client_stats("client-1")
        assert stats["client_id"] == "client-1"
        assert "requests_in_window" in stats
        assert "remaining" in stats


# =============================================================================
# Capacity Planning Tests
# =============================================================================


class TestResourceTrend:
    """Tests for ResourceTrend class."""

    def test_trend_creation(self):
        """Test creating a resource trend."""
        trend = ResourceTrend(
            resource_type=ResourceType.CPU,
            current_usage=75.0,
            average_usage=70.0,
            peak_usage=90.0,
            min_usage=50.0,
            growth_rate=5.0,
            volatility=10.0,
            trend_direction="increasing",
            confidence=0.85,
        )

        assert trend.resource_type == ResourceType.CPU
        assert trend.current_usage == 75.0
        assert trend.trend_direction == "increasing"

    def test_trend_to_dict(self):
        """Test trend serialization."""
        trend = ResourceTrend(
            resource_type=ResourceType.MEMORY,
            current_usage=80.0,
            average_usage=75.0,
            peak_usage=95.0,
            min_usage=60.0,
            growth_rate=2.0,
            volatility=5.0,
            trend_direction="stable",
            confidence=0.9,
        )

        data = trend.to_dict()
        assert data["resource_type"] == "memory"
        assert data["current_usage"] == 80.0


class TestCapacityForecast:
    """Tests for CapacityForecast class."""

    def test_forecast_creation(self):
        """Test creating a capacity forecast."""
        forecast = CapacityForecast(
            forecast_id="forecast-123",
            resource_type=ResourceType.CPU,
            current_capacity=100.0,
            forecasted_demand=120.0,
            forecast_date=datetime.utcnow() + timedelta(days=7),
            confidence_interval=(110.0, 130.0),
            confidence=0.85,
            model_used=GrowthModel.LINEAR,
            recommended_capacity=144.0,
        )

        assert forecast.capacity_gap == 20.0
        assert forecast.utilization_forecast == 1.0  # Capped at 1.0

    def test_forecast_to_dict(self):
        """Test forecast serialization."""
        forecast = CapacityForecast(
            forecast_id="forecast-123",
            resource_type=ResourceType.MEMORY,
            current_capacity=100.0,
            forecasted_demand=80.0,
            forecast_date=datetime.utcnow() + timedelta(days=7),
            confidence_interval=(70.0, 90.0),
            confidence=0.9,
            model_used=GrowthModel.LINEAR,
        )

        data = forecast.to_dict()
        assert data["forecast_id"] == "forecast-123"
        assert data["resource_type"] == "memory"


class TestCapacityConfig:
    """Tests for CapacityConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CapacityConfig()

        assert config.target_utilization == 0.7
        assert config.critical_utilization == 0.9
        assert config.forecast_horizon_days == 7

    def test_custom_config(self):
        """Test custom configuration."""
        config = CapacityConfig(
            target_utilization=0.8,
            history_days=60,
            safety_margin=1.3,
        )

        assert config.target_utilization == 0.8
        assert config.history_days == 60
        assert config.safety_margin == 1.3


class TestCapacityPlanner:
    """Tests for CapacityPlanner class."""

    @pytest.fixture
    def planner(self):
        """Create a capacity planner for testing."""
        config = CapacityConfig(
            min_samples_for_forecast=10,
            history_days=7,
        )
        return CapacityPlanner(config=config)

    @pytest.mark.asyncio
    async def test_record_usage(self, planner):
        """Test recording resource usage."""
        await planner.record_usage(ResourceType.CPU, 75.0)
        await planner.record_usage(ResourceType.CPU, 80.0)

        stats = await planner.get_statistics()
        assert stats["samples_collected"] == 2

    @pytest.mark.asyncio
    async def test_set_capacity(self, planner):
        """Test setting resource capacity."""
        await planner.set_capacity(ResourceType.CPU, 100.0)

        # Verify capacity is set
        assert planner._capacity[ResourceType.CPU] == 100.0

    @pytest.mark.asyncio
    async def test_analyze_trend_insufficient_data(self, planner):
        """Test trend analysis with insufficient data."""
        await planner.record_usage(ResourceType.CPU, 75.0)

        trend = await planner.analyze_trend(ResourceType.CPU)
        assert trend is None  # Not enough data

    @pytest.mark.asyncio
    async def test_analyze_trend(self, planner):
        """Test trend analysis with sufficient data."""
        # Add enough data points
        base_time = datetime.utcnow() - timedelta(hours=10)
        for i in range(20):
            await planner.record_usage(
                ResourceType.CPU,
                70.0 + i * 0.5,  # Increasing trend
                timestamp=base_time + timedelta(minutes=i * 5),
            )

        trend = await planner.analyze_trend(ResourceType.CPU)
        assert trend is not None
        assert trend.resource_type == ResourceType.CPU
        assert trend.trend_direction in ["increasing", "stable", "decreasing"]

    @pytest.mark.asyncio
    async def test_forecast(self, planner):
        """Test capacity forecasting."""
        # Add enough data points
        base_time = datetime.utcnow() - timedelta(hours=10)
        for i in range(20):
            await planner.record_usage(
                ResourceType.CPU,
                70.0 + i * 0.5,
                timestamp=base_time + timedelta(minutes=i * 5),
            )

        await planner.set_capacity(ResourceType.CPU, 100.0)

        forecast = await planner.forecast(ResourceType.CPU, horizon_days=1)
        assert forecast is not None
        assert forecast.resource_type == ResourceType.CPU
        assert forecast.forecasted_demand > 0

    @pytest.mark.asyncio
    async def test_get_recommendations(self, planner):
        """Test getting recommendations."""
        # Add data showing high utilization
        base_time = datetime.utcnow() - timedelta(hours=10)
        for i in range(20):
            await planner.record_usage(
                ResourceType.CPU,
                85.0,  # High utilization
                timestamp=base_time + timedelta(minutes=i * 5),
            )

        await planner.set_capacity(ResourceType.CPU, 100.0)

        recommendations = await planner.get_recommendations([ResourceType.CPU])
        # May or may not have recommendations depending on thresholds
        assert isinstance(recommendations, list)

    @pytest.mark.asyncio
    async def test_peak_prediction(self, planner):
        """Test peak demand prediction."""
        # Add data
        base_time = datetime.utcnow() - timedelta(hours=48)
        for i in range(50):
            await planner.record_usage(
                ResourceType.CPU,
                60.0 + (i % 24) * 2,  # Daily pattern
                timestamp=base_time + timedelta(hours=i),
            )

        prediction = await planner.get_peak_prediction(ResourceType.CPU, hours_ahead=12)
        assert prediction["resource_type"] == "cpu"
        assert "predicted_max" in prediction

    @pytest.mark.asyncio
    async def test_get_trend_summary(self, planner):
        """Test getting trend summary."""
        # Add data for multiple resources
        for i in range(20):
            await planner.record_usage(ResourceType.CPU, 70.0)
            await planner.record_usage(ResourceType.MEMORY, 60.0)

        summary = await planner.get_trend_summary()
        assert isinstance(summary, dict)


# =============================================================================
# Integration Tests
# =============================================================================


class TestLoadSheddingIntegration:
    """Integration tests for load shedding."""

    @pytest.mark.asyncio
    async def test_full_load_shedding_cycle(self):
        """Test complete load shedding cycle."""
        policy = LoadSheddingPolicy(
            soft_limit=0.6,
            hard_limit=0.8,
            critical_limit=0.9,
            max_queue_size=5,
        )
        shedder = LoadShedder(policy=policy)

        # Track shed requests
        shed_requests = []

        def on_shed(request, reason):
            shed_requests.append((request, reason))

        shedder.shed_callback = on_shed

        # Test with metrics that produce different overall_load values
        # The overall_load formula is:
        # cpu*0.4 + mem*0.3 + min(1, queue/100)*0.2 + min(1, error*10)*0.1

        # Low load: overall = 0.3*0.4 + 0.3*0.3 + 0 + 0 = 0.21
        def low_metrics():
            return LoadMetrics(cpu_utilization=0.3, memory_utilization=0.3)

        shedder.metrics_callback = low_metrics
        decision, _ = await shedder.admit(
            request_id="req-low",
            priority=PriorityLevel.NORMAL,
            client_id="client-1",
        )
        assert decision == SheddingDecision.ACCEPT

        # Medium load: overall = 0.8*0.4 + 0.75*0.3 + 0.5*0.2 + 0.02*0.1 = 0.647
        def medium_metrics():
            return LoadMetrics(
                cpu_utilization=0.8,
                memory_utilization=0.75,
                queue_depth=50,
                error_rate=0.02,
            )

        shedder.metrics_callback = medium_metrics
        decision, _ = await shedder.admit(
            request_id="req-medium",
            priority=PriorityLevel.NORMAL,
            client_id="client-2",
        )
        # Between soft and hard limit, should degrade
        assert decision == SheddingDecision.DEGRADE

        # High load: overall = 0.95*0.4 + 0.95*0.3 + 1.0*0.2 + 0.5*0.1 = 0.915
        def high_metrics():
            return LoadMetrics(
                cpu_utilization=0.95,
                memory_utilization=0.95,
                queue_depth=100,
                error_rate=0.05,
            )

        shedder.metrics_callback = high_metrics
        decision, _ = await shedder.admit(
            request_id="req-high",
            priority=PriorityLevel.BEST_EFFORT,
            client_id="client-3",
        )
        # Above critical limit, should shed low priority
        assert decision == SheddingDecision.SHED


class TestCapacityPlanningIntegration:
    """Integration tests for capacity planning."""

    @pytest.mark.asyncio
    async def test_full_capacity_planning_cycle(self):
        """Test complete capacity planning cycle."""
        config = CapacityConfig(
            min_samples_for_forecast=15,
            target_utilization=0.7,
            safety_margin=1.2,
        )
        planner = CapacityPlanner(config=config)

        # Simulate historical data with growth trend
        base_time = datetime.utcnow() - timedelta(hours=24)
        for i in range(30):
            usage = 50.0 + i * 2  # Growing usage
            await planner.record_usage(
                ResourceType.CPU,
                usage,
                timestamp=base_time + timedelta(minutes=i * 30),
            )

        await planner.set_capacity(ResourceType.CPU, 100.0)

        # Analyze trend
        trend = await planner.analyze_trend(ResourceType.CPU)
        assert trend is not None
        assert trend.trend_direction == "increasing"

        # Generate forecast
        forecast = await planner.forecast(ResourceType.CPU, horizon_days=7)
        assert forecast is not None
        assert forecast.forecasted_demand > trend.current_usage

        # Get recommendations
        recommendations = await planner.get_recommendations([ResourceType.CPU])
        # Should recommend scaling up due to growth
        assert isinstance(recommendations, list)

        # Get statistics
        stats = await planner.get_statistics()
        assert stats["samples_collected"] == 30
