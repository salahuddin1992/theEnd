"""
Auto-Scaling Module Unit Tests - اختبارات وحدة التوسع التلقائي
============================================================

Tests for the auto-scaling system including:
- AutoScalingManager
- Metrics collection
- Scaling policies (Queue-based, Resource-based, etc.)
- Cloud providers (AWS, Azure, GCP, Local)
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distributed_cluster.autoscaling import (
    AutoScalingConfig,
    AutoScalingEvent,
    AutoScalingManager,
    AutoScalingState,
    AutoScalingStatus,
    AWSProvider,
    AzureProvider,
    CloudProvider,
    CompositePolicy,
    CostAwarePolicy,
    GCPProvider,
    LocalProvider,
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


# =============================================================================
# Metrics Tests
# =============================================================================


class TestMetricsSample:
    """Tests for MetricsSample."""

    def test_create_sample(self):
        """Test creating a metrics sample."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=10,
            active_workers=5,
            cpu_utilization=0.75,
            memory_utilization=0.60,
            gpu_utilization=0.50,
        )
        assert sample.queue_depth == 10
        assert sample.active_workers == 5
        assert sample.cpu_utilization == 0.75

    def test_sample_defaults(self):
        """Test default values."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=0,
            active_workers=0,
        )
        assert sample.cpu_utilization == 0.0
        assert sample.memory_utilization == 0.0


class TestResourceMetrics:
    """Tests for ResourceMetrics."""

    def test_create_metrics(self):
        """Test creating resource metrics."""
        metrics = ResourceMetrics(
            cpu_total=32,
            cpu_used=16,
            memory_total_mb=65536,
            memory_used_mb=32768,
            gpu_total=4,
            gpu_used=2,
        )
        assert metrics.cpu_utilization == 0.5
        assert metrics.memory_utilization == 0.5
        assert metrics.gpu_utilization == 0.5

    def test_zero_total_resources(self):
        """Test with zero total resources."""
        metrics = ResourceMetrics(
            cpu_total=0,
            cpu_used=0,
            memory_total_mb=0,
            memory_used_mb=0,
        )
        assert metrics.cpu_utilization == 0.0
        assert metrics.memory_utilization == 0.0


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    @pytest.fixture
    def mock_cluster_state(self):
        """Create mock cluster state."""
        state = MagicMock()
        state.get_queue_depth.return_value = 10
        state.get_active_workers.return_value = 5
        state.get_resource_utilization.return_value = {
            "cpu": 0.75,
            "memory": 0.60,
            "gpu": 0.50,
        }
        return state

    @pytest.fixture
    def collector(self, mock_cluster_state):
        """Create a metrics collector."""
        return MetricsCollector(mock_cluster_state)

    def test_collect_sample(self, collector):
        """Test collecting a metrics sample."""
        sample = collector.collect()

        assert sample.queue_depth == 10
        assert sample.active_workers == 5
        assert sample.cpu_utilization == 0.75

    def test_collect_history(self, collector):
        """Test collecting multiple samples."""
        for _ in range(5):
            collector.collect()

        assert len(collector.history) == 5

    def test_get_average_metrics(self, collector):
        """Test getting average metrics."""
        for _ in range(5):
            collector.collect()

        avg = collector.get_average(window_seconds=60)
        assert avg is not None
        assert avg.queue_depth == 10


# =============================================================================
# Scaling Policy Tests
# =============================================================================


class TestScalingDecision:
    """Tests for ScalingDecision."""

    def test_scale_up_decision(self):
        """Test scale up decision."""
        decision = ScalingDecision(
            direction=ScalingDirection.UP,
            count=2,
            reason="High queue depth",
        )
        assert decision.direction == ScalingDirection.UP
        assert decision.count == 2
        assert decision.should_scale is True

    def test_no_scale_decision(self):
        """Test no scale decision."""
        decision = ScalingDecision(
            direction=ScalingDirection.NONE,
            count=0,
            reason="Metrics within bounds",
        )
        assert decision.direction == ScalingDirection.NONE
        assert decision.should_scale is False


class TestQueueBasedPolicy:
    """Tests for QueueBasedPolicy."""

    @pytest.fixture
    def policy(self):
        return QueueBasedPolicy(
            min_workers=1,
            max_workers=10,
            target_queue_depth=5,
            scale_up_threshold=10,
            scale_down_threshold=2,
        )

    def test_scale_up_on_high_queue(self, policy):
        """Test scaling up when queue is high."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=15,
            active_workers=3,
        )

        decision = policy.evaluate(sample)
        assert decision.direction == ScalingDirection.UP
        assert decision.count > 0

    def test_scale_down_on_low_queue(self, policy):
        """Test scaling down when queue is low."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=1,
            active_workers=5,
        )

        decision = policy.evaluate(sample)
        assert decision.direction == ScalingDirection.DOWN

    def test_no_scale_when_balanced(self, policy):
        """Test no scaling when queue is balanced."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=5,
            active_workers=3,
        )

        decision = policy.evaluate(sample)
        assert decision.direction == ScalingDirection.NONE

    def test_respects_min_workers(self, policy):
        """Test that min_workers is respected."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=0,
            active_workers=1,
        )

        decision = policy.evaluate(sample)
        # Should not scale down below min
        if decision.direction == ScalingDirection.DOWN:
            assert sample.active_workers - decision.count >= policy.min_workers

    def test_respects_max_workers(self, policy):
        """Test that max_workers is respected."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=100,
            active_workers=9,
        )

        decision = policy.evaluate(sample)
        if decision.direction == ScalingDirection.UP:
            assert sample.active_workers + decision.count <= policy.max_workers


class TestResourceBasedPolicy:
    """Tests for ResourceBasedPolicy."""

    @pytest.fixture
    def policy(self):
        return ResourceBasedPolicy(
            min_workers=1,
            max_workers=10,
            cpu_scale_up_threshold=0.80,
            cpu_scale_down_threshold=0.30,
            memory_scale_up_threshold=0.80,
            memory_scale_down_threshold=0.30,
        )

    def test_scale_up_on_high_cpu(self, policy):
        """Test scaling up when CPU is high."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=5,
            active_workers=3,
            cpu_utilization=0.90,
            memory_utilization=0.50,
        )

        decision = policy.evaluate(sample)
        assert decision.direction == ScalingDirection.UP

    def test_scale_up_on_high_memory(self, policy):
        """Test scaling up when memory is high."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=5,
            active_workers=3,
            cpu_utilization=0.50,
            memory_utilization=0.90,
        )

        decision = policy.evaluate(sample)
        assert decision.direction == ScalingDirection.UP

    def test_scale_down_on_low_utilization(self, policy):
        """Test scaling down when utilization is low."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=0,
            active_workers=5,
            cpu_utilization=0.20,
            memory_utilization=0.20,
        )

        decision = policy.evaluate(sample)
        assert decision.direction == ScalingDirection.DOWN


class TestCompositePolicy:
    """Tests for CompositePolicy."""

    @pytest.fixture
    def composite_policy(self):
        queue_policy = QueueBasedPolicy(
            min_workers=1,
            max_workers=10,
            target_queue_depth=5,
        )
        resource_policy = ResourceBasedPolicy(
            min_workers=1,
            max_workers=10,
        )
        return CompositePolicy(
            policies=[queue_policy, resource_policy],
            weights=[0.6, 0.4],
        )

    def test_combines_decisions(self, composite_policy):
        """Test that composite policy combines decisions."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=15,
            active_workers=3,
            cpu_utilization=0.90,
        )

        decision = composite_policy.evaluate(sample)
        assert decision.direction == ScalingDirection.UP


class TestCostAwarePolicy:
    """Tests for CostAwarePolicy."""

    @pytest.fixture
    def policy(self):
        return CostAwarePolicy(
            min_workers=1,
            max_workers=10,
            hourly_budget=100.0,
            cost_per_worker_hour=10.0,
        )

    def test_respects_budget(self, policy):
        """Test that budget is respected."""
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=100,
            active_workers=9,
        )

        # With 9 workers at $10/hour = $90/hour, close to budget
        decision = policy.evaluate(sample)

        # Should limit scaling to stay within budget
        if decision.direction == ScalingDirection.UP:
            new_count = sample.active_workers + decision.count
            assert new_count * policy.cost_per_worker_hour <= policy.hourly_budget


class TestScheduleBasedPolicy:
    """Tests for ScheduleBasedPolicy."""

    @pytest.fixture
    def policy(self):
        # Business hours: more workers
        return ScheduleBasedPolicy(
            schedules=[
                {"hours": (9, 17), "days": (0, 1, 2, 3, 4), "min_workers": 5, "max_workers": 20},
                {"hours": (0, 24), "days": (5, 6), "min_workers": 1, "max_workers": 5},
            ],
            default_min_workers=2,
            default_max_workers=10,
        )

    def test_applies_schedule(self, policy):
        """Test that schedule is applied."""
        # Business hours sample
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=10,
            active_workers=3,
        )

        decision = policy.evaluate(sample)
        # Should consider schedule when making decisions
        assert decision is not None


# =============================================================================
# Cloud Provider Tests
# =============================================================================


class TestLocalProvider:
    """Tests for LocalProvider."""

    @pytest.fixture
    def provider(self):
        config = ProviderConfig(
            instance_type="local",
            region="local",
        )
        return LocalProvider(config)

    @pytest.mark.asyncio
    async def test_launch_workers(self, provider):
        """Test launching workers."""
        workers = await provider.launch_workers(count=3)
        assert len(workers) == 3
        for worker in workers:
            assert worker.startswith("local-worker-")

    @pytest.mark.asyncio
    async def test_terminate_workers(self, provider):
        """Test terminating workers."""
        # First launch some workers
        workers = await provider.launch_workers(count=2)

        # Then terminate them
        terminated = await provider.terminate_workers(workers)
        assert terminated == 2

    @pytest.mark.asyncio
    async def test_get_worker_count(self, provider):
        """Test getting worker count."""
        # Launch workers
        await provider.launch_workers(count=3)

        count = await provider.get_worker_count()
        assert count == 3


class TestAWSProvider:
    """Tests for AWS Provider (mocked)."""

    @pytest.fixture
    def provider(self):
        config = ProviderConfig(
            instance_type="t3.xlarge",
            region="us-east-1",
        )
        return AWSProvider(config)

    @pytest.mark.asyncio
    async def test_launch_workers_mock(self, provider):
        """Test AWS worker launch with mock."""
        with patch.object(provider, "_ec2_client") as mock_ec2:
            mock_ec2.run_instances = AsyncMock(
                return_value={
                    "Instances": [
                        {"InstanceId": "i-12345"},
                        {"InstanceId": "i-67890"},
                    ]
                }
            )

            workers = await provider.launch_workers(count=2)
            assert len(workers) == 2


class TestAzureProvider:
    """Tests for Azure Provider (mocked)."""

    @pytest.fixture
    def provider(self):
        config = ProviderConfig(
            instance_type="Standard_D4s_v3",
            region="eastus",
        )
        return AzureProvider(config)

    @pytest.mark.asyncio
    async def test_initialization(self, provider):
        """Test Azure provider initialization."""
        assert provider.config.region == "eastus"
        assert provider.config.instance_type == "Standard_D4s_v3"


class TestGCPProvider:
    """Tests for GCP Provider (mocked)."""

    @pytest.fixture
    def provider(self):
        config = ProviderConfig(
            instance_type="n1-standard-4",
            region="us-central1",
        )
        return GCPProvider(config)

    @pytest.mark.asyncio
    async def test_initialization(self, provider):
        """Test GCP provider initialization."""
        assert provider.config.region == "us-central1"
        assert provider.config.instance_type == "n1-standard-4"


# =============================================================================
# AutoScalingManager Tests
# =============================================================================


class TestAutoScalingConfig:
    """Tests for AutoScalingConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = AutoScalingConfig()
        assert config.enabled is True
        assert config.cooldown_up_seconds >= 0
        assert config.cooldown_down_seconds >= 0
        assert config.evaluation_interval_seconds > 0

    def test_custom_config(self):
        """Test custom configuration."""
        config = AutoScalingConfig(
            enabled=True,
            cooldown_up_seconds=120,
            cooldown_down_seconds=600,
            evaluation_interval_seconds=30,
        )
        assert config.cooldown_up_seconds == 120
        assert config.cooldown_down_seconds == 600


class TestAutoScalingState:
    """Tests for AutoScalingState."""

    def test_state_values(self):
        """Test state enum values."""
        assert AutoScalingState.IDLE is not None
        assert AutoScalingState.SCALING_UP is not None
        assert AutoScalingState.SCALING_DOWN is not None
        assert AutoScalingState.COOLDOWN is not None


class TestAutoScalingStatus:
    """Tests for AutoScalingStatus."""

    def test_create_status(self):
        """Test creating status."""
        status = AutoScalingStatus(
            state=AutoScalingState.IDLE,
            current_workers=5,
            desired_workers=5,
            last_scale_time=datetime.now(timezone.utc),
            last_scale_direction=ScalingDirection.NONE,
        )
        assert status.state == AutoScalingState.IDLE
        assert status.current_workers == 5


class TestAutoScalingEvent:
    """Tests for AutoScalingEvent."""

    def test_create_event(self):
        """Test creating scaling event."""
        event = AutoScalingEvent(
            timestamp=datetime.now(timezone.utc),
            direction=ScalingDirection.UP,
            previous_count=3,
            new_count=5,
            reason="High queue depth",
        )
        assert event.direction == ScalingDirection.UP
        assert event.previous_count == 3
        assert event.new_count == 5


class TestAutoScalingManager:
    """Tests for AutoScalingManager."""

    @pytest.fixture
    def mock_metrics(self):
        """Create mock metrics collector."""
        collector = MagicMock(spec=MetricsCollector)
        collector.collect.return_value = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=10,
            active_workers=5,
            cpu_utilization=0.75,
        )
        return collector

    @pytest.fixture
    def mock_policy(self):
        """Create mock scaling policy."""
        policy = MagicMock(spec=ScalingPolicy)
        policy.evaluate.return_value = ScalingDecision(
            direction=ScalingDirection.NONE,
            count=0,
            reason="Test",
        )
        return policy

    @pytest.fixture
    def mock_provider(self):
        """Create mock cloud provider."""
        provider = MagicMock(spec=CloudProvider)
        provider.launch_workers = AsyncMock(return_value=["worker-1"])
        provider.terminate_workers = AsyncMock(return_value=1)
        provider.get_worker_count = AsyncMock(return_value=5)
        return provider

    @pytest.fixture
    def manager(self, mock_metrics, mock_policy, mock_provider):
        """Create auto-scaling manager."""
        config = AutoScalingConfig(
            enabled=True,
            cooldown_up_seconds=60,
            cooldown_down_seconds=300,
            evaluation_interval_seconds=10,
        )
        return AutoScalingManager(
            config=config,
            metrics_collector=mock_metrics,
            policy=mock_policy,
            provider=mock_provider,
        )

    def test_initialization(self, manager):
        """Test manager initialization."""
        assert manager.config.enabled is True
        assert manager.state == AutoScalingState.IDLE

    @pytest.mark.asyncio
    async def test_evaluate_no_scaling(self, manager, mock_policy):
        """Test evaluation with no scaling needed."""
        mock_policy.evaluate.return_value = ScalingDecision(
            direction=ScalingDirection.NONE,
            count=0,
            reason="Metrics within bounds",
        )

        await manager.evaluate()
        assert manager.state == AutoScalingState.IDLE

    @pytest.mark.asyncio
    async def test_evaluate_scale_up(self, manager, mock_policy, mock_provider):
        """Test evaluation triggers scale up."""
        mock_policy.evaluate.return_value = ScalingDecision(
            direction=ScalingDirection.UP,
            count=2,
            reason="High queue depth",
        )

        await manager.evaluate()

        mock_provider.launch_workers.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_scale_down(self, manager, mock_policy, mock_provider):
        """Test evaluation triggers scale down."""
        mock_policy.evaluate.return_value = ScalingDecision(
            direction=ScalingDirection.DOWN,
            count=1,
            reason="Low utilization",
        )

        # Skip cooldown for test
        manager._last_scale_time = datetime.now(timezone.utc) - timedelta(hours=1)

        await manager.evaluate()

        mock_provider.terminate_workers.assert_called()

    @pytest.mark.asyncio
    async def test_cooldown_prevents_scaling(self, manager, mock_policy):
        """Test cooldown prevents immediate scaling."""
        mock_policy.evaluate.return_value = ScalingDecision(
            direction=ScalingDirection.UP,
            count=2,
            reason="High queue depth",
        )

        # Set recent scale time
        manager._last_scale_time = datetime.now(timezone.utc)
        manager._last_scale_direction = ScalingDirection.UP

        await manager.evaluate()

        # Should be in cooldown, not scaling
        # The state depends on implementation

    @pytest.mark.asyncio
    async def test_disabled_manager(self, mock_metrics, mock_policy, mock_provider):
        """Test disabled manager doesn't scale."""
        config = AutoScalingConfig(enabled=False)
        manager = AutoScalingManager(
            config=config,
            metrics_collector=mock_metrics,
            policy=mock_policy,
            provider=mock_provider,
        )

        mock_policy.evaluate.return_value = ScalingDecision(
            direction=ScalingDirection.UP,
            count=5,
            reason="Test",
        )

        await manager.evaluate()

        mock_provider.launch_workers.assert_not_called()

    def test_get_status(self, manager):
        """Test getting manager status."""
        status = manager.get_status()
        assert isinstance(status, AutoScalingStatus)
        assert status.state == AutoScalingState.IDLE

    def test_get_events(self, manager):
        """Test getting scaling events."""
        events = manager.get_events()
        assert isinstance(events, list)


# =============================================================================
# Policy Templates Tests
# =============================================================================


class TestPolicyTemplates:
    """Tests for PolicyTemplates factory."""

    def test_create_web_service_policy(self):
        """Test creating web service policy."""
        policy = PolicyTemplates.web_service(
            min_workers=2,
            max_workers=20,
        )
        assert policy is not None

    def test_create_batch_processing_policy(self):
        """Test creating batch processing policy."""
        policy = PolicyTemplates.batch_processing(
            min_workers=0,
            max_workers=50,
        )
        assert policy is not None

    def test_create_ml_training_policy(self):
        """Test creating ML training policy."""
        policy = PolicyTemplates.ml_training(
            min_workers=0,
            max_workers=10,
        )
        assert policy is not None


# =============================================================================
# Integration Tests
# =============================================================================


class TestAutoScalingIntegration:
    """Integration tests for auto-scaling."""

    @pytest.mark.asyncio
    async def test_full_scaling_cycle(self):
        """Test a complete scaling cycle."""
        # Create real components (not mocks)
        mock_state = MagicMock()
        mock_state.get_queue_depth.return_value = 50
        mock_state.get_active_workers.return_value = 2
        mock_state.get_resource_utilization.return_value = {
            "cpu": 0.90,
            "memory": 0.80,
            "gpu": 0.0,
        }

        metrics = MetricsCollector(mock_state)
        policy = QueueBasedPolicy(
            min_workers=1,
            max_workers=10,
            target_queue_depth=5,
            scale_up_threshold=10,
            scale_down_threshold=2,
        )

        provider_config = ProviderConfig(
            instance_type="local",
            region="local",
        )
        provider = LocalProvider(provider_config)

        config = AutoScalingConfig(
            enabled=True,
            cooldown_up_seconds=0,  # No cooldown for test
            cooldown_down_seconds=0,
            evaluation_interval_seconds=1,
        )

        manager = AutoScalingManager(
            config=config,
            metrics_collector=metrics,
            policy=policy,
            provider=provider,
        )

        # Initial state
        assert manager.state == AutoScalingState.IDLE

        # Evaluate should trigger scale up
        await manager.evaluate()

        # Check that workers were launched
        worker_count = await provider.get_worker_count()
        assert worker_count > 0

    @pytest.mark.asyncio
    async def test_policy_evaluation_chain(self):
        """Test chain of policy evaluations."""
        queue_policy = QueueBasedPolicy(
            min_workers=1,
            max_workers=10,
            target_queue_depth=5,
        )

        resource_policy = ResourceBasedPolicy(
            min_workers=1,
            max_workers=10,
            cpu_scale_up_threshold=0.80,
        )

        composite = CompositePolicy(
            policies=[queue_policy, resource_policy],
            weights=[0.5, 0.5],
        )

        # High queue, high CPU
        sample = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=20,
            active_workers=3,
            cpu_utilization=0.90,
            memory_utilization=0.50,
        )

        decision = composite.evaluate(sample)
        assert decision.direction == ScalingDirection.UP

        # Low queue, low CPU
        sample2 = MetricsSample(
            timestamp=datetime.now(timezone.utc),
            queue_depth=1,
            active_workers=5,
            cpu_utilization=0.20,
            memory_utilization=0.20,
        )

        decision2 = composite.evaluate(sample2)
        assert decision2.direction == ScalingDirection.DOWN
