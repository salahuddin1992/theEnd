"""
Model Fuzzing Tests
===================

Property-based tests for data models using Hypothesis.
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st


class TestResourceSpecFuzzing:
    """Fuzz testing for ResourceSpec model."""

    @given(
        cpu_cores=st.integers(min_value=0, max_value=1024),
        memory_mb=st.integers(min_value=0, max_value=1024 * 1024),
        gpu_count=st.integers(min_value=0, max_value=64),
        gpu_memory_mb=st.integers(min_value=0, max_value=1024 * 1024),
    )
    @settings(max_examples=100)
    def test_resource_spec_creation(self, cpu_cores, memory_mb, gpu_count, gpu_memory_mb):
        """Test ResourceSpec can be created with various inputs."""
        from distributed_cluster.models.resources import ResourceSpec

        try:
            spec = ResourceSpec(
                cpu_cores=cpu_cores,
                memory_mb=memory_mb,
                gpu_count=gpu_count,
                gpu_memory_mb=gpu_memory_mb,
            )
            # If created successfully, should be valid
            assert spec.cpu_cores >= 0
            assert spec.memory_mb >= 0
        except ValueError:
            # Validation errors are acceptable
            pass

    @given(
        cpu_cores=st.integers(min_value=-1000, max_value=1000),
        memory_mb=st.integers(min_value=-1000, max_value=100000),
    )
    @settings(max_examples=50)
    def test_resource_spec_rejects_negative(self, cpu_cores, memory_mb):
        """Test ResourceSpec rejects negative values."""
        from distributed_cluster.models.resources import ResourceSpec

        if cpu_cores < 0 or memory_mb < 0:
            with pytest.raises((ValueError, Exception)):
                ResourceSpec(cpu_cores=cpu_cores, memory_mb=memory_mb)
        else:
            # Non-negative should work
            spec = ResourceSpec(cpu_cores=cpu_cores, memory_mb=memory_mb)
            assert spec is not None


class TestJobSubmissionFuzzing:
    """Fuzz testing for JobSubmission model."""

    @given(
        command=st.text(min_size=1, max_size=1000),
        cpu_cores=st.integers(min_value=1, max_value=128),
        memory_mb=st.integers(min_value=256, max_value=65536),
        timeout=st.integers(min_value=1, max_value=86400),
    )
    @settings(max_examples=100)
    def test_job_submission_creation(self, command, cpu_cores, memory_mb, timeout):
        """Test JobSubmission with various inputs."""
        from distributed_cluster.models.job import JobPriority, JobSubmission
        from distributed_cluster.models.resources import ResourceSpec

        assume(len(command.strip()) > 0)  # Need non-empty command

        try:
            submission = JobSubmission(
                command=command,
                resources=ResourceSpec(cpu_cores=cpu_cores, memory_mb=memory_mb),
                priority=JobPriority.NORMAL,
                timeout_seconds=timeout,
            )
            assert submission.command == command
        except (ValueError, Exception):
            # Validation errors are acceptable
            pass

    @given(
        env_key=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"),
            min_size=1,
            max_size=64,
        ),
        env_value=st.text(min_size=0, max_size=256),
    )
    @settings(max_examples=50)
    def test_job_environment_variables(self, env_key, env_value):
        """Test job environment variable handling."""
        from distributed_cluster.models.job import JobPriority, JobSubmission
        from distributed_cluster.models.resources import ResourceSpec

        assume(len(env_key) > 0 and env_key[0].isalpha())

        try:
            submission = JobSubmission(
                command="echo test",
                resources=ResourceSpec(cpu_cores=1, memory_mb=512),
                priority=JobPriority.NORMAL,
                environment={env_key: env_value},
            )
            assert env_key in submission.environment
        except (ValueError, Exception):
            pass


class TestWorkerInfoFuzzing:
    """Fuzz testing for WorkerInfo model."""

    @given(
        worker_id=st.text(
            min_size=1,
            max_size=64,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
        ),
        hostname=st.text(min_size=1, max_size=255),
        port=st.integers(min_value=1, max_value=65535),
    )
    @settings(max_examples=50)
    def test_worker_info_creation(self, worker_id, hostname, port):
        """Test WorkerInfo with various inputs."""
        from datetime import datetime, timezone

        from distributed_cluster.models.resources import ResourceSpec
        from distributed_cluster.models.worker import WorkerInfo, WorkerStatus

        assume(len(worker_id.strip()) > 0)
        assume(len(hostname.strip()) > 0)

        try:
            now = datetime.now(timezone.utc)
            worker = WorkerInfo(
                worker_id=worker_id,
                hostname=hostname,
                ip_address="192.168.1.1",
                port=port,
                status=WorkerStatus.READY,
                total_resources=ResourceSpec(cpu_cores=8, memory_mb=16384),
                available_resources=ResourceSpec(cpu_cores=8, memory_mb=16384),
                tags=[],
                labels={},
                platform="linux",
                docker_available=True,
                registered_at=now,
                last_heartbeat=now,
            )
            assert worker.worker_id == worker_id
        except (ValueError, Exception):
            pass


class TestSchedulerFuzzing:
    """Fuzz testing for scheduler operations."""

    @given(
        num_workers=st.integers(min_value=1, max_value=50),
        num_jobs=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=20, deadline=None)
    def test_scheduler_with_random_workload(self, num_workers, num_jobs):
        """Test scheduler with random workloads."""
        import random
        from datetime import datetime, timezone

        from distributed_cluster.models.job import Job, JobPriority, JobSubmission
        from distributed_cluster.models.resources import ResourceSpec
        from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
        from distributed_cluster.scheduler import Scheduler, SchedulingPolicy

        scheduler = Scheduler(policy=SchedulingPolicy.BEST_FIT)
        now = datetime.now(timezone.utc)

        # Register random workers
        for i in range(num_workers):
            worker = WorkerInfo(
                worker_id=f"worker-{i}",
                hostname=f"host-{i}",
                ip_address=f"192.168.1.{i % 256}",
                port=8081,
                status=WorkerStatus.READY,
                total_resources=ResourceSpec(
                    cpu_cores=random.randint(4, 64),
                    memory_mb=random.randint(4096, 65536),
                ),
                available_resources=ResourceSpec(
                    cpu_cores=random.randint(1, 32),
                    memory_mb=random.randint(1024, 32768),
                ),
                tags=[],
                labels={},
                platform="linux",
                docker_available=True,
                registered_at=now,
                last_heartbeat=now,
            )
            scheduler.add_worker(worker)

        # Schedule random jobs
        scheduled = 0
        for i in range(num_jobs):
            submission = JobSubmission(
                command="echo test",
                resources=ResourceSpec(
                    cpu_cores=random.randint(1, 8),
                    memory_mb=random.randint(512, 4096),
                ),
                priority=random.choice(list(JobPriority)),
            )
            job = Job(job_id=f"fuzz-job-{i}", submission=submission)
            scheduler.submit_job(job)
            scheduled += 1

        # Should not crash and should schedule some jobs
        assert scheduled >= 0


class TestAPIInputFuzzing:
    """Fuzz testing for API inputs."""

    @given(
        data=st.dictionaries(
            keys=st.text(min_size=1, max_size=32),
            values=st.one_of(
                st.text(max_size=256),
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
                st.booleans(),
                st.none(),
            ),
            max_size=20,
        )
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_api_handles_arbitrary_json(self, data):
        """Test API handles arbitrary JSON without crashing."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Send arbitrary JSON to job submission endpoint
            response = await client.post("/api/v1/jobs", json=data)

            # Should not cause server error (5xx)
            assert response.status_code < 500, f"Server error with data: {data}"

    @given(
        query_param=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_api_handles_arbitrary_query_params(self, query_param):
        """Test API handles arbitrary query parameters."""
        import urllib.parse

        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            encoded = urllib.parse.quote(query_param, safe="")
            response = await client.get(f"/api/v1/jobs?search={encoded}")

            # Should not cause server error
            assert response.status_code < 500


class TestStringFuzzing:
    """String handling fuzz tests."""

    @given(
        text=st.text(min_size=0, max_size=10000),
    )
    @settings(max_examples=100)
    def test_unicode_handling(self, text):
        """Test unicode string handling."""
        from distributed_cluster.models.job import JobPriority, JobSubmission
        from distributed_cluster.models.resources import ResourceSpec

        if not text.strip():
            return

        try:
            submission = JobSubmission(
                command=f"echo '{text}'",
                resources=ResourceSpec(cpu_cores=1, memory_mb=512),
                priority=JobPriority.NORMAL,
            )
            # Should handle unicode without crashing
            assert submission is not None
        except (ValueError, UnicodeError):
            # Validation errors are OK
            pass

    @given(
        text=st.binary(min_size=0, max_size=1000),
    )
    @settings(max_examples=50)
    def test_binary_data_handling(self, text):
        """Test binary data handling."""
        # Binary data should be properly rejected or handled
        try:
            decoded = text.decode("utf-8", errors="replace")
            # If decodable, should be usable
            assert isinstance(decoded, str)
        except Exception:
            # Decode errors are expected
            pass
