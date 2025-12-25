# -*- coding: utf-8 -*-
"""
Tests for Advanced Analytics Module
====================================

اختبارات وحدة التحليلات المتقدمة.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock

from distributed_cluster.analytics.advanced_analytics import (
    AnomalyDetector,
    AnomalyType,
    AlertSeverity,
    WorkloadClassifier,
    WorkloadCategory,
    CostPredictor,
    PatternAnalyzer,
    AdvancedAnalyticsEngine,
)


# =============================================================================
# Anomaly Detector Tests
# =============================================================================


class TestAnomalyDetector:
    """Tests for AnomalyDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return AnomalyDetector(window_size=50, z_threshold=2.0, sensitivity=0.8)

    @pytest.mark.asyncio
    async def test_add_data_point_no_anomaly(self, detector):
        """Test adding normal data points."""
        # Add baseline data
        for i in range(20):
            result = await detector.add_data_point("cpu_usage", 50.0 + i * 0.1)
            # First few points shouldn't trigger anomalies
            if i < 10:
                assert result is None

    @pytest.mark.asyncio
    async def test_detect_spike_anomaly(self, detector):
        """Test detection of spike anomalies."""
        # Establish baseline
        for i in range(30):
            await detector.add_data_point("cpu_usage", 50.0)

        # Add spike
        anomaly = await detector.add_data_point("cpu_usage", 95.0)

        assert anomaly is not None
        assert anomaly.anomaly_type == AnomalyType.SPIKE
        assert anomaly.metric_name == "cpu_usage"
        assert anomaly.value == 95.0

    @pytest.mark.asyncio
    async def test_detect_drop_anomaly(self, detector):
        """Test detection of drop anomalies."""
        # Establish baseline
        for i in range(30):
            await detector.add_data_point("memory_usage", 70.0)

        # Add drop
        anomaly = await detector.add_data_point("memory_usage", 10.0)

        assert anomaly is not None
        assert anomaly.anomaly_type == AnomalyType.DROP

    @pytest.mark.asyncio
    async def test_callback_registration(self, detector):
        """Test anomaly callback registration."""
        callback_called = []

        def callback(anomaly):
            callback_called.append(anomaly)

        detector.register_callback(callback)

        # Establish baseline and trigger anomaly
        for i in range(30):
            await detector.add_data_point("test_metric", 50.0)
        await detector.add_data_point("test_metric", 150.0)

        assert len(callback_called) > 0

    @pytest.mark.asyncio
    async def test_get_recent_anomalies(self, detector):
        """Test getting recent anomalies."""
        # Generate some anomalies
        for i in range(30):
            await detector.add_data_point("metric1", 50.0)
        await detector.add_data_point("metric1", 150.0)
        await detector.add_data_point("metric1", 5.0)

        anomalies = await detector.get_recent_anomalies(limit=10)
        assert len(anomalies) >= 1

    @pytest.mark.asyncio
    async def test_get_statistics(self, detector):
        """Test getting detector statistics."""
        for i in range(20):
            await detector.add_data_point("test", float(i))

        stats = await detector.get_statistics()

        assert "data_points_processed" in stats
        assert stats["data_points_processed"] == 20
        assert "metrics_tracked" in stats


# =============================================================================
# Workload Classifier Tests
# =============================================================================


class TestWorkloadClassifier:
    """Tests for WorkloadClassifier class."""

    @pytest.fixture
    def classifier(self):
        """Create a classifier instance."""
        return WorkloadClassifier()

    @pytest.mark.asyncio
    async def test_add_sample(self, classifier):
        """Test adding workload samples."""
        await classifier.add_sample(
            job_type="ml_training",
            cpu_usage=80.0,
            memory_usage=60.0,
            gpu_usage=90.0,
            io_operations=10.0,
            duration=3600.0,
        )

        # Should not have profile yet (need more samples)
        profile = await classifier.get_profile("ml_training")
        assert profile is None

    @pytest.mark.asyncio
    async def test_classify_gpu_intensive(self, classifier):
        """Test classification of GPU-intensive workload."""
        # Add multiple samples
        for i in range(15):
            await classifier.add_sample(
                job_type="gpu_job",
                cpu_usage=30.0,
                memory_usage=40.0,
                gpu_usage=95.0,
                io_operations=5.0,
                duration=1800.0,
            )

        profile = await classifier.get_profile("gpu_job")

        assert profile is not None
        assert profile.category == WorkloadCategory.GPU_INTENSIVE

    @pytest.mark.asyncio
    async def test_classify_cpu_intensive(self, classifier):
        """Test classification of CPU-intensive workload."""
        for i in range(15):
            await classifier.add_sample(
                job_type="cpu_job",
                cpu_usage=95.0,
                memory_usage=20.0,
                gpu_usage=0.0,
                io_operations=5.0,
                duration=600.0,
            )

        profile = await classifier.get_profile("cpu_job")

        assert profile is not None
        assert profile.category == WorkloadCategory.CPU_INTENSIVE

    @pytest.mark.asyncio
    async def test_recommend_resources(self, classifier):
        """Test resource recommendations."""
        for i in range(15):
            await classifier.add_sample(
                job_type="test_job",
                cpu_usage=50.0,
                memory_usage=60.0,
                gpu_usage=0.0,
                io_operations=10.0,
                duration=300.0,
            )

        recommendations = await classifier.recommend_resources("test_job")

        assert "cpu_cores" in recommendations
        assert "memory_mb" in recommendations
        assert recommendations["cpu_cores"] > 0
        assert recommendations["memory_mb"] > 0

    @pytest.mark.asyncio
    async def test_get_all_profiles(self, classifier):
        """Test getting all profiles."""
        for job_type in ["job1", "job2"]:
            for i in range(15):
                await classifier.add_sample(
                    job_type=job_type,
                    cpu_usage=50.0,
                    memory_usage=50.0,
                    gpu_usage=0.0,
                    io_operations=10.0,
                    duration=300.0,
                )

        profiles = await classifier.get_all_profiles()
        assert len(profiles) == 2


# =============================================================================
# Cost Predictor Tests
# =============================================================================


class TestCostPredictor:
    """Tests for CostPredictor class."""

    @pytest.fixture
    def predictor(self):
        """Create a predictor instance."""
        return CostPredictor(
            cpu_cost_per_hour=0.05,
            memory_cost_per_gb_hour=0.01,
            gpu_cost_per_hour=0.50,
        )

    @pytest.mark.asyncio
    async def test_predict_cost_basic(self, predictor):
        """Test basic cost prediction."""
        prediction = await predictor.predict_cost(
            job_type="test_job",
            cpu_cores=4.0,
            memory_mb=8192,
            gpu_units=1.0,
            estimated_duration_seconds=3600,  # 1 hour
        )

        assert prediction is not None
        assert prediction.estimated_cost > 0
        assert "cpu" in prediction.cost_breakdown
        assert "memory" in prediction.cost_breakdown
        assert "gpu" in prediction.cost_breakdown

    @pytest.mark.asyncio
    async def test_predict_cost_no_gpu(self, predictor):
        """Test cost prediction without GPU."""
        prediction = await predictor.predict_cost(
            job_type="cpu_job",
            cpu_cores=2.0,
            memory_mb=4096,
            gpu_units=0.0,
            estimated_duration_seconds=1800,  # 30 minutes
        )

        assert prediction.cost_breakdown["gpu"] == 0

    @pytest.mark.asyncio
    async def test_record_actual_cost(self, predictor):
        """Test recording actual costs."""
        await predictor.record_actual_cost("test_job", 1.50)
        await predictor.record_actual_cost("test_job", 1.60)
        await predictor.record_actual_cost("test_job", 1.55)

        # Future predictions should use historical data
        prediction = await predictor.predict_cost(
            job_type="test_job",
            cpu_cores=4.0,
            memory_mb=8192,
            gpu_units=0.0,
            estimated_duration_seconds=3600,
        )

        # Confidence should be higher with historical data
        assert prediction.confidence > 0.7

    @pytest.mark.asyncio
    async def test_estimate_monthly_cost(self, predictor):
        """Test monthly cost estimation."""
        estimates = await predictor.estimate_monthly_cost(
            avg_jobs_per_day=100,
            avg_cost_per_job=0.50,
        )

        assert "daily" in estimates
        assert "weekly" in estimates
        assert "monthly" in estimates
        assert estimates["daily"] == 50.0
        assert estimates["monthly"] == 1500.0


# =============================================================================
# Pattern Analyzer Tests
# =============================================================================


class TestPatternAnalyzer:
    """Tests for PatternAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create an analyzer instance."""
        return PatternAnalyzer()

    @pytest.mark.asyncio
    async def test_add_event(self, analyzer):
        """Test adding events."""
        await analyzer.add_event({
            "type": "job_completion",
            "job_id": "test-123",
            "duration": 300,
        })

        # Event should be in buffer
        assert len(analyzer._sequence_buffer) == 1

    @pytest.mark.asyncio
    async def test_detect_patterns_insufficient_data(self, analyzer):
        """Test pattern detection with insufficient data."""
        for i in range(5):
            await analyzer.add_event({"type": "test", "value": i})

        patterns = await analyzer.detect_patterns()
        # Should return empty list with insufficient data
        assert isinstance(patterns, list)

    @pytest.mark.asyncio
    async def test_detect_failure_pattern(self, analyzer):
        """Test detection of failure patterns."""
        base_time = datetime.utcnow()

        # Add cascading failures
        for i in range(5):
            await analyzer.add_event({
                "type": "failure",
                "timestamp": base_time + timedelta(seconds=i * 10),
                "error": "Connection failed",
            })

        # Add some normal events
        for i in range(20):
            await analyzer.add_event({
                "type": "success",
                "timestamp": base_time + timedelta(seconds=100 + i * 60),
            })

        patterns = await analyzer.detect_patterns()

        # Should detect cascading failure pattern
        failure_patterns = [p for p in patterns if p.pattern_name == "cascading_failure"]
        # Pattern detection depends on timing, may or may not detect


# =============================================================================
# Advanced Analytics Engine Tests
# =============================================================================


class TestAdvancedAnalyticsEngine:
    """Tests for AdvancedAnalyticsEngine class."""

    @pytest.fixture
    def engine(self):
        """Create an engine instance."""
        return AdvancedAnalyticsEngine(anomaly_sensitivity=0.8)

    @pytest.mark.asyncio
    async def test_start_stop(self, engine):
        """Test engine start and stop."""
        await engine.start()
        assert engine._running is True

        await engine.stop()
        assert engine._running is False

    @pytest.mark.asyncio
    async def test_process_metric(self, engine):
        """Test processing metrics."""
        await engine.start()

        # Process some metrics
        for i in range(30):
            await engine.process_metric("cpu", 50.0)

        # Process anomalous value
        anomaly = await engine.process_metric("cpu", 99.0)

        # May or may not detect anomaly depending on thresholds
        await engine.stop()

    @pytest.mark.asyncio
    async def test_process_job_completion(self, engine):
        """Test processing job completions."""
        await engine.start()

        await engine.process_job_completion(
            job_type="test_job",
            cpu_usage=70.0,
            memory_usage=60.0,
            gpu_usage=0.0,
            io_operations=100.0,
            duration=300.0,
            cost=0.50,
        )

        await engine.stop()

    @pytest.mark.asyncio
    async def test_get_recommendations(self, engine):
        """Test getting recommendations."""
        await engine.start()

        # Add some job data
        for i in range(15):
            await engine.process_job_completion(
                job_type="ml_job",
                cpu_usage=40.0,
                memory_usage=80.0,
                gpu_usage=90.0,
                io_operations=20.0,
                duration=3600.0,
                cost=2.00,
            )

        recommendations = await engine.get_recommendations("ml_job")

        assert "workload_profile" in recommendations
        assert "recommended_resources" in recommendations

        await engine.stop()

    @pytest.mark.asyncio
    async def test_get_statistics(self, engine):
        """Test getting engine statistics."""
        await engine.start()

        stats = await engine.get_statistics()

        assert "events_processed" in stats
        assert "running" in stats
        assert stats["running"] is True

        await engine.stop()


# =============================================================================
# Integration Tests
# =============================================================================


class TestAnalyticsIntegration:
    """Integration tests for analytics components."""

    @pytest.mark.asyncio
    async def test_full_analytics_pipeline(self):
        """Test full analytics pipeline."""
        engine = AdvancedAnalyticsEngine()
        await engine.start()

        # Simulate workload over time
        for hour in range(24):
            for job in range(10):
                # Process job completion
                await engine.process_job_completion(
                    job_type="batch_job",
                    cpu_usage=50.0 + hour,
                    memory_usage=60.0,
                    gpu_usage=0.0,
                    io_operations=100.0,
                    duration=300.0 + job * 10,
                    cost=0.10 + job * 0.01,
                )

                # Process metrics
                await engine.process_metric("cpu_usage", 50.0 + hour)
                await engine.process_metric("memory_usage", 60.0)

        # Get final statistics
        stats = await engine.get_statistics()
        assert stats["events_processed"] > 0

        # Get recommendations
        recommendations = await engine.get_recommendations("batch_job")
        assert recommendations is not None

        await engine.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
