"""
API Benchmark Tests
===================

Comprehensive API performance benchmarks.
"""

import asyncio
import statistics
import time

import pytest

from distributed_cluster.models.job import Job, JobPriority, JobSubmission
from distributed_cluster.models.resources import ResourceSpec


class TestAPIBenchmarks:
    """API endpoint performance benchmarks."""

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test API under concurrent load."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()
        concurrent_requests = 50

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

            async def make_request():
                start = time.perf_counter()
                response = await client.get("/health")
                elapsed = time.perf_counter() - start
                return response.status_code, elapsed

            # Execute concurrent requests
            tasks = [make_request() for _ in range(concurrent_requests)]
            results = await asyncio.gather(*tasks)

            statuses = [r[0] for r in results]
            latencies = [r[1] * 1000 for r in results]  # Convert to ms

            success_rate = sum(1 for s in statuses if s == 200) / len(statuses)
            avg_latency = statistics.mean(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

            print(f"\nConcurrent requests: {concurrent_requests}")
            print(f"Success rate: {success_rate * 100:.1f}%")
            print(f"Average latency: {avg_latency:.2f}ms")
            print(f"P95 latency: {p95_latency:.2f}ms")

            assert success_rate >= 0.99  # 99% success rate
            assert avg_latency < 100  # Average < 100ms

    @pytest.mark.asyncio
    async def test_sustained_load(self):
        """Test API under sustained load for 5 seconds."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()
        duration_seconds = 2  # Run for 2 seconds

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            latencies = []
            errors = 0
            start_time = time.perf_counter()

            while time.perf_counter() - start_time < duration_seconds:
                req_start = time.perf_counter()
                try:
                    response = await client.get("/health")
                    if response.status_code == 200:
                        latencies.append((time.perf_counter() - req_start) * 1000)
                    else:
                        errors += 1
                except Exception:
                    errors += 1

            total_requests = len(latencies) + errors
            throughput = total_requests / duration_seconds

            print(f"\nSustained load test ({duration_seconds}s)")
            print(f"Total requests: {total_requests}")
            print(f"Throughput: {throughput:.1f} req/s")
            print(f"Errors: {errors}")
            if latencies:
                print(f"Avg latency: {statistics.mean(latencies):.2f}ms")

            assert errors / total_requests < 0.01 if total_requests > 0 else True

    @pytest.mark.asyncio
    async def test_job_submission_performance(self):
        """Benchmark job submission endpoint."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            job_data = {
                "command": "python -c 'print(1)'",
                "resources": {"cpu_cores": 1, "memory_mb": 512},
                "priority": "normal",
            }

            latencies = []
            for i in range(20):
                start = time.perf_counter()
                response = await client.post("/api/v1/jobs", json=job_data)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            avg_latency = statistics.mean(latencies)
            max_latency = max(latencies)

            print(f"\nJob submission: avg={avg_latency:.2f}ms, max={max_latency:.2f}ms")
            assert avg_latency < 200  # Job submission < 200ms avg

    @pytest.mark.asyncio
    async def test_metrics_endpoint_performance(self):
        """Benchmark metrics collection endpoint."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            latencies = []

            for _ in range(50):
                start = time.perf_counter()
                response = await client.get("/metrics")
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            avg_latency = statistics.mean(latencies)
            p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]

            print(f"\nMetrics endpoint: avg={avg_latency:.2f}ms, p99={p99_latency:.2f}ms")
            assert avg_latency < 100  # Metrics should be fast


class TestMemoryPerformance:
    """Memory usage and efficiency tests."""

    def test_scheduler_memory_with_many_workers(self):
        """Test scheduler memory usage with many workers."""
        import sys
        from datetime import datetime, timezone

        from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
        from distributed_cluster.scheduler import Scheduler, SchedulingPolicy

        scheduler = Scheduler(policy=SchedulingPolicy.BEST_FIT)
        initial_size = sys.getsizeof(scheduler)

        now = datetime.now(timezone.utc)
        for i in range(1000):
            worker = WorkerInfo(
                worker_id=f"worker-{i}",
                hostname=f"host-{i}",
                ip_address=f"10.0.{i // 256}.{i % 256}",
                port=8081,
                status=WorkerStatus.READY,
                total_resources=ResourceSpec(cpu_cores=8, memory_mb=16384),
                available_resources=ResourceSpec(cpu_cores=8, memory_mb=16384),
                tags=["cpu"],
                labels={},
                platform="linux",
                docker_available=True,
                registered_at=now,
                last_heartbeat=now,
            )
            scheduler.add_worker(worker)

        # Memory should grow proportionally
        assert len(scheduler.workers) == 1000
        print("\nScheduler with 1000 workers registered")

    def test_job_queue_memory(self):
        """Test job queue memory efficiency."""
        from distributed_cluster.models.job import Job, JobStatus, JobSubmission

        jobs = []
        for i in range(10000):
            job = Job(
                job_id=f"job-{i}",
                submission=JobSubmission(
                    command="echo test",
                    resources=ResourceSpec(cpu_cores=1, memory_mb=512),
                    priority=JobPriority.NORMAL,
                ),
                status=JobStatus.PENDING,
            )
            jobs.append(job)

        assert len(jobs) == 10000
        print("\nCreated 10000 Job objects successfully")


class TestCPUPerformance:
    """CPU-bound operation benchmarks."""

    def test_resource_matching_cpu(self):
        """Benchmark CPU usage for resource matching."""
        from datetime import datetime, timezone

        from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
        from distributed_cluster.scheduler import Scheduler, SchedulingPolicy

        scheduler = Scheduler(policy=SchedulingPolicy.BEST_FIT)
        now = datetime.now(timezone.utc)

        # Add workers with varied resources
        for i in range(50):
            worker = WorkerInfo(
                worker_id=f"worker-{i}",
                hostname=f"host-{i}",
                ip_address=f"192.168.1.{i}",
                port=8081,
                status=WorkerStatus.READY,
                total_resources=ResourceSpec(
                    cpu_cores=4 * (i + 1),
                    memory_mb=8192 * (i + 1),
                    gpu_count=i % 4,
                ),
                available_resources=ResourceSpec(
                    cpu_cores=2 * (i + 1),
                    memory_mb=4096 * (i + 1),
                    gpu_count=i % 2,
                ),
                tags=["cpu"] + (["gpu"] if i % 4 > 0 else []),
                labels={},
                platform="linux",
                docker_available=True,
                registered_at=now,
                last_heartbeat=now,
            )
            scheduler.add_worker(worker)

        # Benchmark many scheduling decisions
        submission = JobSubmission(
            command="python test.py",
            resources=ResourceSpec(cpu_cores=4, memory_mb=4096),
            priority=JobPriority.NORMAL,
        )

        start = time.perf_counter()
        for i in range(1000):
            job = Job(job_id=f"bench-job-{i}", submission=submission)
            scheduler.submit_job(job)
        elapsed = time.perf_counter() - start

        print(f"\n1000 scheduling decisions in {elapsed:.3f}s")
        print(f"Rate: {1000/elapsed:.1f} decisions/s")
        assert elapsed < 10.0  # Should complete in < 10s
