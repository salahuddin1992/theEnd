"""
Scheduler Performance Tests
===========================

Benchmark tests for the scheduler component.
"""

import time
from datetime import datetime, timezone

import pytest

from distributed_cluster.models.job import Job, JobPriority, JobSubmission
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
from distributed_cluster.scheduler import Scheduler, SchedulingPolicy


class TestSchedulerPerformance:
    """Performance benchmarks for scheduler operations."""

    @pytest.fixture
    def large_worker_pool(self) -> list[WorkerInfo]:
        """Create a large pool of workers for stress testing."""
        workers = []
        now = datetime.now(timezone.utc)

        for i in range(100):
            workers.append(
                WorkerInfo(
                    worker_id=f"worker-{i}",
                    hostname=f"host-{i}",
                    ip_address=f"192.168.{i // 256}.{i % 256}",
                    port=8081,
                    status=WorkerStatus.READY,
                    total_resources=ResourceSpec(
                        cpu_cores=16 + (i % 32),
                        memory_mb=32768 + (i % 8) * 8192,
                        gpu_count=i % 4,
                        gpu_memory_mb=(i % 4) * 8192 if i % 4 > 0 else 0,
                    ),
                    available_resources=ResourceSpec(
                        cpu_cores=8 + (i % 16),
                        memory_mb=16384 + (i % 4) * 4096,
                        gpu_count=i % 2,
                        gpu_memory_mb=(i % 2) * 4096 if i % 2 > 0 else 0,
                    ),
                    tags=["cpu"] + (["gpu", "nvidia"] if i % 4 > 0 else []),
                    labels={"zone": f"zone-{i % 5}", "tier": f"tier-{i % 3}"},
                    platform="linux",
                    docker_available=True,
                    registered_at=now,
                    last_heartbeat=now,
                )
            )
        return workers

    @pytest.fixture
    def many_jobs(self) -> list[JobSubmission]:
        """Create many job submissions for stress testing."""
        jobs = []
        for i in range(500):
            jobs.append(
                JobSubmission(
                    command=f"python task_{i}.py",
                    resources=ResourceSpec(
                        cpu_cores=1 + (i % 4),
                        memory_mb=512 + (i % 8) * 256,
                        gpu_count=1 if i % 10 == 0 else 0,
                    ),
                    priority=[JobPriority.LOW, JobPriority.NORMAL, JobPriority.HIGH][i % 3],
                    timeout_seconds=60 + (i % 60) * 10,
                    environment={"TASK_ID": str(i)},
                )
            )
        return jobs

    def test_scheduler_creation_time(self, benchmark):
        """Benchmark scheduler creation."""

        def create_scheduler():
            return Scheduler(policy=SchedulingPolicy.BEST_FIT)

        result = benchmark(create_scheduler)
        assert result is not None

    def test_worker_registration_throughput(self, large_worker_pool: list[WorkerInfo], benchmark):
        """Benchmark worker registration throughput."""
        scheduler = Scheduler(policy=SchedulingPolicy.BEST_FIT)

        def register_all_workers():
            for worker in large_worker_pool:
                scheduler.add_worker(worker)
            return len(scheduler.workers)

        count = benchmark(register_all_workers)
        assert count == len(large_worker_pool)

    def test_job_scheduling_latency(
        self,
        large_worker_pool: list[WorkerInfo],
        many_jobs: list[JobSubmission],
        benchmark,
    ):
        """Benchmark job scheduling latency."""
        scheduler = Scheduler(policy=SchedulingPolicy.BEST_FIT)
        for worker in large_worker_pool:
            scheduler.add_worker(worker)

        def schedule_jobs():
            scheduled = 0
            for i, submission in enumerate(many_jobs[:50]):  # Schedule subset
                job = Job(job_id=f"latency-test-{i}", submission=submission)
                scheduler.submit_job(job)
                scheduled += 1
            return scheduled

        result = benchmark(schedule_jobs)
        assert result >= 0

    def test_policy_comparison(self, large_worker_pool: list[WorkerInfo]):
        """Compare scheduling policy performance."""
        policies = [
            SchedulingPolicy.FIRST_FIT,
            SchedulingPolicy.BEST_FIT,
            SchedulingPolicy.ROUND_ROBIN,
        ]

        results = {}
        submission = JobSubmission(
            command="python test.py",
            resources=ResourceSpec(cpu_cores=2, memory_mb=2048),
            priority=JobPriority.NORMAL,
        )

        for policy in policies:
            scheduler = Scheduler(policy=policy)
            for worker in large_worker_pool:
                scheduler.add_worker(worker)

            start = time.perf_counter()
            for i in range(100):
                job = Job(job_id=f"test-job-{policy.value}-{i}", submission=submission)
                scheduler.submit_job(job)
            elapsed = time.perf_counter() - start
            results[policy.value] = elapsed

        # Log results
        for policy, elapsed in results.items():
            print(f"{policy}: {elapsed:.4f}s for 100 schedules")

        # All policies should complete reasonably fast
        for elapsed in results.values():
            assert elapsed < 5.0  # 100 schedules should take < 5s


class TestDatabasePerformance:
    """Performance benchmarks for database operations."""

    @pytest.mark.asyncio
    async def test_job_insert_throughput(self, database, benchmark):
        """Benchmark job insertion throughput."""
        from distributed_cluster.models.job import Job, JobStatus, JobSubmission

        async def insert_jobs():
            jobs_created = 0
            for i in range(100):
                job = Job(
                    job_id=f"perf-job-{i}",
                    submission=JobSubmission(
                        command=f"echo test_{i}",
                        resources=ResourceSpec(cpu_cores=1, memory_mb=512),
                        priority=JobPriority.NORMAL,
                    ),
                    status=JobStatus.PENDING,
                )
                await database.save_job(job)
                jobs_created += 1
            return jobs_created

        # Can't use benchmark directly with async, measure manually
        start = time.perf_counter()
        count = await insert_jobs()
        elapsed = time.perf_counter() - start

        assert count == 100
        assert elapsed < 10.0  # Should complete in < 10s
        print(f"Inserted {count} jobs in {elapsed:.3f}s ({count/elapsed:.1f} jobs/s)")

    @pytest.mark.asyncio
    async def test_job_query_performance(self, database):
        """Benchmark job query performance."""
        from distributed_cluster.models.job import Job, JobStatus, JobSubmission

        # Insert test data
        for i in range(50):
            job = Job(
                job_id=f"query-job-{i}",
                submission=JobSubmission(
                    command=f"echo test_{i}",
                    resources=ResourceSpec(cpu_cores=1, memory_mb=512),
                    priority=JobPriority.NORMAL,
                ),
                status=JobStatus.PENDING if i % 2 == 0 else JobStatus.COMPLETED,
            )
            await database.save_job(job)

        # Benchmark queries
        start = time.perf_counter()
        for _ in range(100):
            jobs = await database.get_jobs_by_status(JobStatus.PENDING)
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0  # 100 queries should take < 5s
        print(f"100 status queries in {elapsed:.3f}s ({100/elapsed:.1f} queries/s)")


class TestAPIPerformance:
    """Performance benchmarks for API endpoints."""

    @pytest.mark.asyncio
    async def test_health_check_latency(self):
        """Benchmark health check endpoint latency."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Warmup
            await client.get("/health")

            # Benchmark
            latencies = []
            for _ in range(100):
                start = time.perf_counter()
                response = await client.get("/health")
                elapsed = (time.perf_counter() - start) * 1000  # ms
                latencies.append(elapsed)
                assert response.status_code == 200

            avg_latency = sum(latencies) / len(latencies)
            p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]

            print(f"Health check: avg={avg_latency:.2f}ms, p99={p99_latency:.2f}ms")
            assert avg_latency < 50  # Average < 50ms
            assert p99_latency < 100  # P99 < 100ms


# pytest-benchmark configuration
def pytest_benchmark_scale_unit(config, unit, benchmarks, best, worst, sort):
    """Configure benchmark units."""
    if unit == "seconds":
        return "ms", 1000
    return unit, 1
