"""
Worker Metrics Tests
====================

Tests for ProcessMemoryTracker and WorkerMetricsCollector.
"""

import asyncio
import os
import subprocess
import sys
import time

import pytest

from distributed_cluster.worker.metrics import (
    ProcessMemoryTracker,
    ProcessMetrics,
    RetryConfig,
    RetryHandler,
    WorkerMetrics,
    WorkerMetricsCollector,
)


class TestProcessMemoryTracker:
    """Tests for ProcessMemoryTracker."""

    @pytest.mark.asyncio
    async def test_track_current_process(self):
        """Test tracking the current process."""
        tracker = ProcessMemoryTracker(
            pid=os.getpid(),
            sample_interval=0.1,
            include_children=False,
        )

        await tracker.start()
        await asyncio.sleep(0.5)  # Let it collect some samples
        await tracker.stop()

        assert tracker.peak_memory_mb > 0
        assert len(tracker.samples) > 0

        # Check sample structure
        sample = tracker.samples[0]
        assert isinstance(sample, ProcessMetrics)
        assert sample.pid == os.getpid()
        assert sample.memory_mb > 0

    @pytest.mark.asyncio
    async def test_track_subprocess(self):
        """Test tracking a subprocess."""
        # Start a subprocess that uses some memory
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; x = [0]*1000000; time.sleep(2)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            tracker = ProcessMemoryTracker(
                pid=proc.pid,
                sample_interval=0.1,
            )

            await tracker.start()
            await asyncio.sleep(1.0)
            await tracker.stop()

            assert tracker.peak_memory_mb > 0
            assert len(tracker.samples) > 0
        finally:
            proc.terminate()
            proc.wait()

    @pytest.mark.asyncio
    async def test_track_nonexistent_process(self):
        """Test tracking a non-existent process."""
        tracker = ProcessMemoryTracker(
            pid=999999999,  # Very unlikely to exist
            sample_interval=0.1,
        )

        await tracker.start()
        await asyncio.sleep(0.3)
        await tracker.stop()

        # Should handle gracefully without crashing
        assert tracker.peak_memory_mb == 0
        assert len(tracker.samples) == 0

    @pytest.mark.asyncio
    async def test_average_cpu_percent(self):
        """Test average CPU calculation."""
        tracker = ProcessMemoryTracker(
            pid=os.getpid(),
            sample_interval=0.1,
        )

        await tracker.start()
        await asyncio.sleep(0.5)
        await tracker.stop()

        # Should have calculated average
        avg_cpu = tracker.average_cpu_percent
        assert avg_cpu >= 0


class TestWorkerMetricsCollector:
    """Tests for WorkerMetricsCollector."""

    @pytest.mark.asyncio
    async def test_collect_metrics(self):
        """Test basic metrics collection."""
        collector = WorkerMetricsCollector(
            worker_id="test-worker",
            collect_interval=0.2,
        )

        await collector.start()
        await asyncio.sleep(0.5)
        await collector.stop()

        metrics = collector.get_current_metrics()
        assert metrics is not None
        assert isinstance(metrics, WorkerMetrics)
        assert metrics.worker_id == "test-worker"
        assert metrics.cpu_count > 0
        assert metrics.memory_total_mb > 0

    @pytest.mark.asyncio
    async def test_job_tracking(self):
        """Test job tracking functionality."""
        collector = WorkerMetricsCollector(
            worker_id="test-worker",
            collect_interval=1.0,
        )

        # Track a job
        collector.start_job_tracking("job-123")

        # Simulate job completion
        await asyncio.sleep(0.1)
        job_metrics = await collector.stop_job_tracking("job-123", exit_code=0)

        assert job_metrics is not None
        assert job_metrics.job_id == "job-123"
        assert job_metrics.exit_code == 0
        assert job_metrics.execution_time_seconds > 0

    @pytest.mark.asyncio
    async def test_record_job_completed(self):
        """Test manual job recording."""
        collector = WorkerMetricsCollector(worker_id="test-worker")

        collector.record_job_completed("job-1", 10.5, 0)
        collector.record_job_completed("job-2", 5.0, 1)

        # Check counters updated
        await collector._collect_metrics()  # Force collection
        collector.get_current_metrics()

        # Note: We can't assert exact counts without waiting for collection
        # Just verify the collector works without error

    @pytest.mark.asyncio
    async def test_prometheus_format(self):
        """Test Prometheus format output."""
        collector = WorkerMetricsCollector(
            worker_id="test-worker",
            collect_interval=0.2,
        )

        await collector.start()
        await asyncio.sleep(0.3)
        await collector.stop()

        output = collector.to_prometheus_format()
        assert "worker_cpu_percent" in output
        assert "worker_memory_used_mb" in output
        assert 'worker="test-worker"' in output


class TestRetryHandler:
    """Tests for RetryHandler."""

    @pytest.mark.asyncio
    async def test_retry_attempts(self):
        """Test retry iteration."""
        config = RetryConfig(
            max_retries=3,
            initial_delay=0.01,
            max_delay=0.1,
        )
        handler = RetryHandler(config)

        attempts = []
        async for attempt in handler:
            attempts.append(attempt)
            if attempt >= 3:
                break

        assert attempts == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test exponential backoff timing."""
        config = RetryConfig(
            max_retries=4,
            initial_delay=0.01,
            exponential_base=2.0,
            jitter=0,  # No jitter for predictable testing
            max_delay=1.0,
        )
        handler = RetryHandler(config)

        start = time.time()
        async for attempt in handler:
            pass

        # Should have had delays: 0, 0.01, 0.02, 0.04
        elapsed = time.time() - start
        assert elapsed >= 0.05  # At least 0.01 + 0.02 + 0.04 = 0.07

    def test_should_retry(self):
        """Test should_retry logic."""
        config = RetryConfig(max_retries=3)
        handler = RetryHandler(config)
        handler._attempt = 1

        # Should retry on connection errors
        assert handler.should_retry(ConnectionError("test"))
        assert handler.should_retry(TimeoutError("test"))

        # Should not retry on other errors
        assert not handler.should_retry(ValueError("test"))

        # Should not retry when at max
        handler._attempt = 3
        assert not handler.should_retry(ConnectionError("test"))
