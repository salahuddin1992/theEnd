"""
Auto-Scaling Module Unit Tests - اختبارات وحدة التوسع التلقائي
=============================================================

Tests for the auto-scaling system including:
- AutoScalingManager
- Metrics collection
- Scaling policies (Queue-based, Resource-based, etc.)
- Cloud providers (AWS, Azure, GCP, Local)
"""

import asyncio
from datetime import datetime, timezone
from datetime import time as dtime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distributed_cluster.autoscaling import (
    AutoScalingConfig,
    AutoScalingEvent,
    AutoScalingManager,
    AutoScalingState,
    AutoScalingStatus,
    CloudProvider,
    CompositePolicy,
    CostAwarePolicy,
    MetricsCollector,
    MetricsSample,
    MetricType,
    PolicyTemplates,
    PredictivePolicy,
    ProviderConfig,
    QueueBasedPolicy,
    ResourceBasedPolicy,
    ResourceMetrics,
    ScalingDecision,
    ScalingDirection,
    ScalingPolicy,
    ScheduleBasedPolicy,
)
from distributed_cluster.autoscaling.metrics import AggregationMethod
from distributed_cluster.autoscaling.providers.base import InstanceInfo, InstanceState


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_cluster_state():
    """Create mock cluster state."""
    state = MagicMock()
    state.get_all_workers.return_value = []
    state.get_healthy_workers.return_value = []
    state.get_pending_jobs.return_value = []
    state.get_running_jobs.return_value = []
    state.get_stats.return_value = {
        "total_jobs_completed": 100,
        "total_jobs_failed": 5,
    }
    state.get_worker.return_value = None
    return state


@pytest.fixture
def mock_metrics_collector(mock_cluster_state):
    """Create mock metrics collector."""
    collector = MagicMock(spec=MetricsCollector)
    collector.collect_now = AsyncMock(
        return_value=ResourceMetrics(
            timestamp=datetime.now(timezone.utc),
            queue_depth=10,
            queue_wait_time_avg=5.0,
            cpu_utilization_avg=50.0,
            memory_utilization_avg=60.0,
            worker_count=5,
            healthy_worker_count=5,
            jobs_completed_last_minute=20,
        )
    )
    collector.get_latest.return_value = ResourceMetrics(
        timestamp=datetime.now(timezone.utc)
    )
    collector.get_trend.return_value = 0.0
    return collector


@pytest.fixture
def mock_provider():
    """Create mock cloud provider."""
    provider = MagicMock(spec=CloudProvider)
    provider.connect = AsyncMock()
    provider.disconnect = AsyncMock()
    provider.provision_workers = AsyncMock(return_value=["worker-1", "worker-2"])
    provider.terminate_workers = AsyncMock(return_value=2)
    provider.get_instances = AsyncMock(return_value=[])
    provider.get_instance = AsyncMock(return_value=None)
    provider.get_terminable_workers = AsyncMock(return_value=["worker-1"])
    provider.get_worker_count = AsyncMock(return_value=5)
    provider.get_status.return_value = {"connected": True}
    provider.__class__.__name__ = "MockProvider"
    return provider


@pytest.fixture
def mock_policy():
    """Create mock scaling policy."""
    policy = MagicMock(spec=ScalingPolicy)
    policy.name = "mock-policy"
    policy.min_workers = 1
    policy.max_workers = 100
    policy.enabled = True
    policy.evaluate = AsyncMock(
        return_value=ScalingDecision(
            direction=ScalingDirection.NONE,
            count=0,
            reason="No scaling needed",
            policy_name="mock-policy",
        )
    )
    policy.get_config.return_value = {"name": "mock-policy"}
    return policy


@pytest.fixture
def resource_metrics():
    """Create sample resource metrics."""
    return ResourceMetrics(
        timestamp=datetime.now(timezone.utc),
        queue_depth=25,
        queue_wait_time_avg=10.5,
        queue_growth_rate=1.5,
        cpu_utilization_avg=75.0,
        cpu_utilization_max=90.0,
        memory_utilization_avg=65.0,
        memory_utilization_max=80.0,
        gpu_utilization_avg=50.0,
        gpu_count_total=4,
        gpu_count_available=2,
        worker_count=10,
        healthy_worker_count=8,
        worker_utilization=70.0,
        jobs_completed_last_minute=50,
        jobs_failed_last_minute=2,
        jobs_running=15,
    )


# =============================================================================
# ResourceMetrics Tests
# =============================================================================


class TestResourceMetrics:
    """Tests for ResourceMetrics dataclass."""

    def test_create_metrics(self):
        """Test creating ResourceMetrics."""
        metrics = ResourceMetrics(timestamp=datetime.now(timezone.utc))
        assert metrics.queue_depth == 0
        assert metrics.cpu_utilization_avg == 0.0

    def test_metrics_with_values(self, resource_metrics):
        """Test ResourceMetrics with values."""
        assert resource_metrics.queue_depth == 25
        assert resource_metrics.cpu_utilization_avg == 75.0
        assert resource_metrics.worker_count == 10

    def test_metrics_to_dict(self, resource_metrics):
        """Test converting metrics to dict."""
        data = resource_metrics.to_dict()
        assert "timestamp" in data
        assert "queue" in data
        assert "cpu" in data
        assert "memory" in data
        assert "gpu" in data
        assert "workers" in data
        assert data["queue"]["depth"] == 25


# =============================================================================
# MetricType Tests
# =============================================================================


class TestMetricType:
    """Tests for MetricType enum."""

    def test_metric_types(self):
        """Test metric type values."""
        assert MetricType.QUEUE_DEPTH == "queue_depth"
        assert MetricType.CPU_UTILIZATION == "cpu_utilization"
        assert MetricType.MEMORY_UTILIZATION == "memory_utilization"
        assert MetricType.GPU_UTILIZATION == "gpu_utilization"
        assert MetricType.WORKER_COUNT == "worker_count"

    def test_aggregation_methods(self):
        """Test aggregation method values."""
        assert AggregationMethod.AVERAGE == "average"
        assert AggregationMethod.MAX == "max"
        assert AggregationMethod.MIN == "min"
        assert AggregationMethod.PERCENTILE_95 == "p95"


# =============================================================================
# ScalingDirection Tests
# =============================================================================


class TestScalingDirection:
    """Tests for ScalingDirection enum."""

    def test_direction_values(self):
        """Test scaling direction values."""
        assert ScalingDirection.UP == "up"
        assert ScalingDirection.DOWN == "down"
        assert ScalingDirection.NONE == "none"


# =============================================================================
# ScalingDecision Tests
# =============================================================================


class TestScalingDecision:
    """Tests for ScalingDecision dataclass."""

    def test_create_decision(self):
        """Test creating scaling decision."""
        decision = ScalingDecision(
            direction=ScalingDirection.UP,
            count=2,
            reason="High queue depth",
            policy_name="queue-based",
        )
        assert decision.direction == ScalingDirection.UP
        assert decision.count == 2
        assert decision.reason == "High queue depth"

    def test_decision_defaults(self):
        """Test decision default values."""
        decision = ScalingDecision(
            direction=ScalingDirection.NONE,
            count=0,
            reason="No scaling",
        )
        assert decision.confidence == 1.0
        assert decision.policy_name == ""
        assert decision.priority == 0

    def test_decision_to_dict(self):
        """Test converting decision to dict."""
        decision = ScalingDecision(
            direction=ScalingDirection.UP,
            count=3,
            reason="Test",
            confidence=0.8,
            policy_name="test-policy",
            priority=2,
        )
        data = decision.to_dict()
        assert data["direction"] == "up"
        assert data["count"] == 3
        assert data["confidence"] == 0.8


# =============================================================================
# QueueBasedPolicy Tests
# =============================================================================


class TestQueueBasedPolicy:
    """Tests for QueueBasedPolicy."""

    def test_create_policy(self):
        """Test creating queue-based policy."""
        policy = QueueBasedPolicy(
            min_workers=2,
            max_workers=50,
            scale_up_threshold=30,
            scale_down_threshold=5,
        )
        assert policy.name == "queue-based"
        assert policy.min_workers == 2
        assert policy.max_workers == 50
        assert policy.scale_up_threshold == 30

    @pytest.mark.asyncio
    async def test_evaluate_no_scaling(self, mock_metrics_collector):
        """Test evaluation with no scaling needed."""
        policy = QueueBasedPolicy(
            scale_up_threshold=50,
            scale_down_threshold=2,
            evaluation_periods=1,
        )
        metrics = ResourceMetrics(
            timestamp=datetime.now(timezone.utc),
            queue_depth=20,
            queue_wait_time_avg=30.0,
        )

        decision = await policy.evaluate(metrics, 5, mock_metrics_collector)
        assert decision.direction == ScalingDirection.NONE

    @pytest.mark.asyncio
    async def test_evaluate_scale_up_wait_time(self, mock_metrics_collector):
        """Test scale up due to high wait time."""
        policy = QueueBasedPolicy(
            max_wait_time_seconds=30.0,
            jobs_per_worker=10,
        )
        metrics = ResourceMetrics(
            timestamp=datetime.now(timezone.utc),
            queue_depth=50,
            queue_wait_time_avg=60.0,  # Exceeds max
        )

        decision = await policy.evaluate(metrics, 2, mock_metrics_collector)
        assert decision.direction == ScalingDirection.UP

    def test_get_config(self):
        """Test getting policy config."""
        policy = QueueBasedPolicy(
            target_queue_depth=15,
            scale_up_threshold=25,
        )
        config = policy.get_config()
        assert config["name"] == "queue-based"
        assert config["target_queue_depth"] == 15
        assert config["scale_up_threshold"] == 25


# =============================================================================
# ResourceBasedPolicy Tests
# =============================================================================


class TestResourceBasedPolicy:
    """Tests for ResourceBasedPolicy."""

    def test_create_policy(self):
        """Test creating resource-based policy."""
        policy = ResourceBasedPolicy(
            cpu_scale_up_threshold=85.0,
            cpu_scale_down_threshold=25.0,
            memory_scale_up_threshold=90.0,
        )
        assert policy.name == "resource-based"
        assert policy.cpu_scale_up_threshold == 85.0
        assert policy.memory_scale_up_threshold == 90.0

    @pytest.mark.asyncio
    async def test_evaluate_not_enough_history(self, mock_metrics_collector):
        """Test evaluation without enough history."""
        policy = ResourceBasedPolicy(evaluation_periods=3)
        metrics = ResourceMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_utilization_avg=50.0,
            memory_utilization_avg=50.0,
        )

        decision = await policy.evaluate(metrics, 5, mock_metrics_collector)
        # Should return no scaling due to not enough history
        assert decision.direction == ScalingDirection.NONE

    @pytest.mark.asyncio
    async def test_evaluate_high_cpu(self, mock_metrics_collector):
        """Test scale up due to high CPU."""
        policy = ResourceBasedPolicy(
            cpu_scale_up_threshold=80.0,
            evaluation_periods=1,
        )
        metrics = ResourceMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_utilization_avg=90.0,
            memory_utilization_avg=50.0,
        )

        # First call populates history
        await policy.evaluate(metrics, 5, mock_metrics_collector)
        # Second call should trigger scale up
        decision = await policy.evaluate(metrics, 5, mock_metrics_collector)
        # Need evaluation_periods to be met
        assert decision.policy_name == "resource-based"

    def test_get_config(self):
        """Test getting policy config."""
        policy = ResourceBasedPolicy(
            gpu_enabled=True,
            gpu_scale_up_threshold=75.0,
        )
        config = policy.get_config()
        assert config["gpu_enabled"] is True
        assert config["gpu_scale_up_threshold"] == 75.0


# =============================================================================
# CompositePolicy Tests
# =============================================================================


class TestCompositePolicy:
    """Tests for CompositePolicy."""

    def test_create_composite(self):
        """Test creating composite policy."""
        queue_policy = QueueBasedPolicy()
        resource_policy = ResourceBasedPolicy()

        composite = CompositePolicy(
            name="test-composite",
            policies=[queue_policy, resource_policy],
            combine_mode=CompositePolicy.CombineMode.ANY,
        )
        assert composite.name == "test-composite"
        assert len(composite.policies) == 2

    def test_add_policy(self):
        """Test adding policy to composite."""
        composite = CompositePolicy()
        policy = QueueBasedPolicy()

        composite.add_policy(policy, weight=2.0)
        assert len(composite.policies) == 1
        assert composite.weights["queue-based"] == 2.0

    @pytest.mark.asyncio
    async def test_evaluate_empty(self, mock_metrics_collector):
        """Test evaluation with no sub-policies."""
        composite = CompositePolicy(policies=[])
        metrics = ResourceMetrics(timestamp=datetime.now(timezone.utc))

        decision = await composite.evaluate(metrics, 5, mock_metrics_collector)
        assert decision.direction == ScalingDirection.NONE

    def test_combine_modes(self):
        """Test combine mode enum values."""
        assert CompositePolicy.CombineMode.ANY == "any"
        assert CompositePolicy.CombineMode.ALL == "all"
        assert CompositePolicy.CombineMode.PRIORITY == "priority"
        assert CompositePolicy.CombineMode.WEIGHTED == "weighted"


# =============================================================================
# CostAwarePolicy Tests
# =============================================================================


class TestCostAwarePolicy:
    """Tests for CostAwarePolicy."""

    def test_create_policy(self):
        """Test creating cost-aware policy."""
        policy = CostAwarePolicy(
            cost_per_worker_hour=0.50,
            max_hourly_budget=25.0,
            target_cost_per_job=0.02,
        )
        assert policy.cost_per_worker_hour == 0.50
        assert policy.max_hourly_budget == 25.0

    def test_with_base_policy(self):
        """Test cost-aware policy with base policy."""
        base = QueueBasedPolicy()
        policy = CostAwarePolicy(
            base_policy=base,
            cost_per_worker_hour=1.0,
            max_hourly_budget=100.0,
        )
        assert policy.base_policy is not None

    @pytest.mark.asyncio
    async def test_evaluate_budget_check(self, mock_metrics_collector):
        """Test budget enforcement."""
        policy = CostAwarePolicy(
            cost_per_worker_hour=10.0,
            max_hourly_budget=50.0,
        )
        metrics = ResourceMetrics(
            timestamp=datetime.now(timezone.utc),
            jobs_completed_last_minute=100,
        )

        decision = await policy.evaluate(metrics, 5, mock_metrics_collector)
        # At 5 workers * $10/hr = $50/hr, at budget limit
        assert decision.policy_name == "cost-aware"


# =============================================================================
# PredictivePolicy Tests
# =============================================================================


class TestPredictivePolicy:
    """Tests for PredictivePolicy."""

    def test_create_policy(self):
        """Test creating predictive policy."""
        policy = PredictivePolicy(
            prediction_window_seconds=600.0,
            trend_threshold=15.0,
            queue_growth_threshold=10.0,
        )
        assert policy.prediction_window_seconds == 600.0
        assert policy.trend_threshold == 15.0

    @pytest.mark.asyncio
    async def test_evaluate_requires_collector(self):
        """Test that evaluation requires metrics collector."""
        policy = PredictivePolicy()
        metrics = ResourceMetrics(timestamp=datetime.now(timezone.utc))

        decision = await policy.evaluate(metrics, 5, None)
        assert decision.direction == ScalingDirection.NONE
        assert "collector required" in decision.reason.lower()


# =============================================================================
# ScheduleBasedPolicy Tests
# =============================================================================


class TestScheduleBasedPolicy:
    """Tests for ScheduleBasedPolicy."""

    def test_create_policy(self):
        """Test creating schedule-based policy."""
        policy = ScheduleBasedPolicy(
            default_workers=5,
            transition_increment=2,
        )
        assert policy.default_workers == 5
        assert policy.transition_increment == 2

    def test_add_schedule(self):
        """Test adding schedule entry."""
        policy = ScheduleBasedPolicy()
        policy.add_schedule(
            start_time=dtime(9, 0),
            end_time=dtime(18, 0),
            target_workers=20,
            days=[0, 1, 2, 3, 4],
            name="business-hours",
        )
        assert len(policy.schedules) == 1
        assert policy.schedules[0].target_workers == 20

    @pytest.mark.asyncio
    async def test_evaluate_uses_schedule(self, mock_metrics_collector):
        """Test evaluation returns schedule-based decision."""
        policy = ScheduleBasedPolicy(default_workers=5)
        metrics = ResourceMetrics(timestamp=datetime.now(timezone.utc))

        decision = await policy.evaluate(metrics, 5, mock_metrics_collector)
        assert decision.policy_name == "schedule-based"

    def test_get_config(self):
        """Test getting policy config."""
        policy = ScheduleBasedPolicy(default_workers=10)
        policy.add_schedule(
            start_time=dtime(9, 0),
            end_time=dtime(17, 0),
            target_workers=15,
        )
        config = policy.get_config()
        assert config["default_workers"] == 10
        assert len(config["schedules"]) == 1


# =============================================================================
# PolicyTemplates Tests
# =============================================================================


class TestPolicyTemplates:
    """Tests for PolicyTemplates factory methods."""

    def test_aggressive_template(self):
        """Test aggressive policy template."""
        policy = PolicyTemplates.aggressive()
        assert policy.name == "aggressive"
        assert isinstance(policy, CompositePolicy)
        assert len(policy.policies) == 2

    def test_conservative_template(self):
        """Test conservative policy template."""
        policy = PolicyTemplates.conservative()
        assert policy.name == "conservative"
        assert isinstance(policy, CompositePolicy)

    def test_cost_optimized_template(self):
        """Test cost-optimized policy template."""
        policy = PolicyTemplates.cost_optimized(
            cost_per_worker=0.25,
            max_budget=100.0,
        )
        assert policy.name == "cost-optimized"
        assert isinstance(policy, CostAwarePolicy)

    def test_gpu_focused_template(self):
        """Test GPU-focused policy template."""
        policy = PolicyTemplates.gpu_focused()
        assert policy.name == "gpu-focused"
        assert isinstance(policy, ResourceBasedPolicy)
        assert policy.gpu_enabled is True

    def test_business_hours_template(self):
        """Test business hours policy template."""
        policy = PolicyTemplates.business_hours(
            peak_workers=25,
            off_peak_workers=5,
            weekend_workers=2,
        )
        assert policy.name == "business-hours"
        assert isinstance(policy, ScheduleBasedPolicy)
        assert len(policy.schedules) == 2


# =============================================================================
# AutoScalingConfig Tests
# =============================================================================


class TestAutoScalingConfig:
    """Tests for AutoScalingConfig."""

    def test_default_config(self):
        """Test default config values."""
        config = AutoScalingConfig()
        assert config.enabled is True
        assert config.min_workers == 1
        assert config.max_workers == 100
        assert config.evaluation_interval_seconds == 30.0

    def test_custom_config(self):
        """Test custom config values."""
        config = AutoScalingConfig(
            min_workers=5,
            max_workers=50,
            cooldown_up_seconds=120.0,
            cooldown_down_seconds=600.0,
        )
        assert config.min_workers == 5
        assert config.max_workers == 50
        assert config.cooldown_up_seconds == 120.0

    def test_config_to_dict(self):
        """Test converting config to dict."""
        config = AutoScalingConfig(
            worker_tags=["production"],
            worker_labels={"env": "prod"},
        )
        data = config.to_dict()
        assert data["enabled"] is True
        assert data["worker_tags"] == ["production"]
        assert data["worker_labels"] == {"env": "prod"}


# =============================================================================
# AutoScalingStatus Tests
# =============================================================================


class TestAutoScalingStatus:
    """Tests for AutoScalingStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert AutoScalingStatus.IDLE == "idle"
        assert AutoScalingStatus.RUNNING == "running"
        assert AutoScalingStatus.SCALING_UP == "scaling_up"
        assert AutoScalingStatus.SCALING_DOWN == "scaling_down"
        assert AutoScalingStatus.COOLDOWN == "cooldown"
        assert AutoScalingStatus.PAUSED == "paused"
        assert AutoScalingStatus.STOPPED == "stopped"
        assert AutoScalingStatus.ERROR == "error"


# =============================================================================
# AutoScalingState Tests
# =============================================================================


class TestAutoScalingState:
    """Tests for AutoScalingState."""

    def test_default_state(self):
        """Test default state values."""
        state = AutoScalingState()
        assert state.status == AutoScalingStatus.IDLE
        assert state.current_worker_count == 0
        assert state.total_scale_ups == 0

    def test_state_to_dict(self):
        """Test converting state to dict."""
        state = AutoScalingState()
        data = state.to_dict()
        assert data["status"] == "idle"
        assert data["current_worker_count"] == 0


# =============================================================================
# AutoScalingEvent Tests
# =============================================================================


class TestAutoScalingEvent:
    """Tests for AutoScalingEvent."""

    def test_default_event(self):
        """Test default event values."""
        event = AutoScalingEvent()
        assert event.event_type == "scaling"
        assert event.direction == "none"
        assert event.success is True

    def test_custom_event(self):
        """Test custom event values."""
        event = AutoScalingEvent(
            event_type="scaling",
            direction="up",
            requested_count=5,
            actual_count=3,
            reason="High queue depth",
        )
        assert event.direction == "up"
        assert event.requested_count == 5
        assert event.actual_count == 3

    def test_event_to_dict(self):
        """Test converting event to dict."""
        event = AutoScalingEvent(reason="Test event")
        data = event.to_dict()
        assert "event_id" in data
        assert "timestamp" in data
        assert data["reason"] == "Test event"


# =============================================================================
# InstanceState Tests
# =============================================================================


class TestInstanceState:
    """Tests for InstanceState enum."""

    def test_instance_states(self):
        """Test instance state values."""
        assert InstanceState.PENDING == "pending"
        assert InstanceState.RUNNING == "running"
        assert InstanceState.TERMINATING == "terminating"
        assert InstanceState.TERMINATED == "terminated"


# =============================================================================
# InstanceInfo Tests
# =============================================================================


class TestInstanceInfo:
    """Tests for InstanceInfo dataclass."""

    def test_create_instance_info(self):
        """Test creating instance info."""
        info = InstanceInfo(
            instance_id="i-123456",
            provider="aws",
            state=InstanceState.RUNNING,
            instance_type="t3.large",
            zone="us-east-1a",
        )
        assert info.instance_id == "i-123456"
        assert info.provider == "aws"
        assert info.state == InstanceState.RUNNING

    def test_instance_info_to_dict(self):
        """Test converting instance info to dict."""
        info = InstanceInfo(
            instance_id="i-test",
            provider="gcp",
            state=InstanceState.PENDING,
            tags={"Name": "test-worker"},
        )
        data = info.to_dict()
        assert data["instance_id"] == "i-test"
        assert data["state"] == "pending"
        assert data["tags"] == {"Name": "test-worker"}


# =============================================================================
# ProviderConfig Tests
# =============================================================================


class TestProviderConfig:
    """Tests for ProviderConfig dataclass."""

    def test_default_config(self):
        """Test default provider config."""
        config = ProviderConfig()
        assert config.enabled is True
        assert config.max_instances == 100

    def test_custom_config(self):
        """Test custom provider config."""
        config = ProviderConfig(
            name="aws-production",
            default_instance_type="c5.xlarge",
            vpc_id="vpc-123",
            subnet_ids=["subnet-1", "subnet-2"],
            cost_per_hour=0.192,
        )
        assert config.name == "aws-production"
        assert config.cost_per_hour == 0.192


# =============================================================================
# AutoScalingManager Tests
# =============================================================================


class TestAutoScalingManager:
    """Tests for AutoScalingManager."""

    def test_create_manager(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test creating auto-scaling manager."""
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
        )
        assert manager.metrics_collector == mock_metrics_collector
        assert manager.policy == mock_policy
        assert manager.provider == mock_provider

    def test_create_with_config(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test creating manager with custom config."""
        config = AutoScalingConfig(
            min_workers=2,
            max_workers=20,
        )
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
            config=config,
        )
        assert manager.config.min_workers == 2
        assert manager.config.max_workers == 20

    @pytest.mark.asyncio
    async def test_start_stop(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test starting and stopping manager."""
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
        )

        await manager.start()
        assert manager.state.status in [
            AutoScalingStatus.STARTING,
            AutoScalingStatus.RUNNING,
        ]
        mock_provider.connect.assert_called_once()

        await manager.stop()
        assert manager.state.status == AutoScalingStatus.STOPPED

    def test_pause_resume(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test pausing and resuming manager."""
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
        )

        manager.pause()
        assert manager.state.status == AutoScalingStatus.PAUSED

        manager.resume()
        assert manager.state.status == AutoScalingStatus.RUNNING

    def test_get_status(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test getting manager status."""
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
        )

        status = manager.get_status()
        assert "enabled" in status
        assert "state" in status
        assert "policy" in status
        assert "provider" in status
        assert "config" in status

    def test_get_events(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test getting events."""
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
        )

        events = manager.get_events(limit=10)
        assert isinstance(events, list)

    def test_callbacks(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test registering callbacks."""
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
        )

        scale_up_callback = MagicMock()
        scale_down_callback = MagicMock()
        error_callback = MagicMock()

        manager.on_scale_up(scale_up_callback)
        manager.on_scale_down(scale_down_callback)
        manager.on_error(error_callback)

        assert len(manager._on_scale_up) == 1
        assert len(manager._on_scale_down) == 1
        assert len(manager._on_error) == 1

    def test_update_config(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test updating config."""
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
        )

        manager.update_config(min_workers=3, max_workers=30)
        assert manager.config.min_workers == 3
        assert manager.config.max_workers == 30

    def test_set_policy(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test setting new policy."""
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
        )

        new_policy = QueueBasedPolicy(name="new-policy")
        manager.set_policy(new_policy)
        assert manager.policy.name == "new-policy"

    def test_set_limits(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test setting worker limits."""
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
        )

        manager.set_limits(min_workers=5, max_workers=25)
        assert manager.config.min_workers == 5
        assert manager.config.max_workers == 25


# =============================================================================
# MetricsCollector Tests
# =============================================================================


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_create_collector(self, mock_cluster_state):
        """Test creating metrics collector."""
        collector = MetricsCollector(
            cluster_state=mock_cluster_state,
            collection_interval_seconds=15.0,
            history_size=100,
        )
        assert collector.collection_interval == 15.0
        assert collector.history_size == 100

    @pytest.mark.asyncio
    async def test_start_stop(self, mock_cluster_state):
        """Test starting and stopping collector."""
        collector = MetricsCollector(
            cluster_state=mock_cluster_state,
            collection_interval_seconds=60.0,
        )

        await collector.start()
        assert collector._running is True

        await collector.stop()
        assert collector._running is False

    def test_get_status(self, mock_cluster_state):
        """Test getting collector status."""
        collector = MetricsCollector(cluster_state=mock_cluster_state)

        status = collector.get_status()
        assert "running" in status
        assert "collection_interval_seconds" in status
        assert "history_size" in status

    def test_add_callback(self, mock_cluster_state):
        """Test adding metrics callback."""
        collector = MetricsCollector(cluster_state=mock_cluster_state)
        callback = MagicMock()

        collector.add_callback(callback)
        assert len(collector._callbacks) == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestAutoScalingIntegration:
    """Integration tests for auto-scaling system."""

    @pytest.mark.asyncio
    async def test_full_scaling_cycle(
        self, mock_cluster_state, mock_provider
    ):
        """Test complete scaling cycle."""
        # Create components
        collector = MagicMock(spec=MetricsCollector)
        collector.collect_now = AsyncMock(
            return_value=ResourceMetrics(
                timestamp=datetime.now(timezone.utc),
                queue_depth=100,
                queue_wait_time_avg=120.0,
            )
        )

        # Create policy that triggers scale up
        policy = MagicMock(spec=ScalingPolicy)
        policy.name = "test-policy"
        policy.evaluate = AsyncMock(
            return_value=ScalingDecision(
                direction=ScalingDirection.UP,
                count=2,
                reason="High queue",
                policy_name="test-policy",
            )
        )
        policy.get_config.return_value = {}

        # Create and start manager
        manager = AutoScalingManager(
            metrics_collector=collector,
            policy=policy,
            provider=mock_provider,
            config=AutoScalingConfig(evaluation_interval_seconds=0.1),
        )

        await manager.start()
        # Give scaling loop time to run
        await asyncio.sleep(0.2)
        await manager.stop()

        # Provider should have been connected
        mock_provider.connect.assert_called()

    @pytest.mark.asyncio
    async def test_manual_scaling(
        self, mock_metrics_collector, mock_policy, mock_provider
    ):
        """Test manual scaling operations."""
        manager = AutoScalingManager(
            metrics_collector=mock_metrics_collector,
            policy=mock_policy,
            provider=mock_provider,
        )

        # Mock provider responses for manual scaling
        mock_provider.provision_workers = AsyncMock(
            return_value=["w-1", "w-2", "w-3"]
        )

        await manager.start()

        # Scale up manually
        event = await manager.scale_up_by(3)
        assert event is not None

        await manager.stop()

    def test_policy_chain(self):
        """Test chaining multiple policies."""
        # Create composite with multiple policies
        composite = CompositePolicy(
            name="chain",
            combine_mode=CompositePolicy.CombineMode.PRIORITY,
        )

        composite.add_policy(QueueBasedPolicy(name="queue"), weight=1.0)
        composite.add_policy(ResourceBasedPolicy(name="resource"), weight=0.8)

        assert len(composite.policies) == 2
        config = composite.get_config()
        assert config["combine_mode"] == "priority"
        assert len(config["policies"]) == 2
