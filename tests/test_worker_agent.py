"""
Tests for Worker Agent
اختبارات وكيل العامل
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distributed_cluster.core.config import WorkerConfig
from distributed_cluster.models.job import Job, JobResult, JobStatus, JobSubmission
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.worker.agent import WorkerAgent


class TestWorkerAgentInit:
    """Tests for WorkerAgent initialization."""

    def test_default_config(self):
        """Test agent with default configuration."""
        agent = WorkerAgent()
        assert agent.config is not None
        assert agent.worker_id is None
        assert agent._running is False

    def test_custom_config(self):
        """Test agent with custom configuration."""
        config = WorkerConfig(
            master_url="http://custom-master:8080",
            port=9000,
            docker_enabled=False,
        )
        agent = WorkerAgent(config=config)
        assert agent.config.master_url == "http://custom-master:8080"
        assert agent.config.port == 9000
        assert agent.config.docker_enabled is False

    def test_master_url_property(self):
        """Test master URL property strips trailing slash."""
        config = WorkerConfig(master_url="http://master:8080/")
        agent = WorkerAgent(config=config)
        assert agent.master_url == "http://master:8080"


class TestWorkerAgentLifecycle:
    """Tests for WorkerAgent lifecycle."""

    @pytest.mark.asyncio
    async def test_stop_cancels_heartbeat(self):
        """Test that stop cancels heartbeat task."""
        agent = WorkerAgent()
        agent._running = True
        agent._heartbeat_task = asyncio.create_task(asyncio.sleep(100))

        await agent.stop()

        assert agent._running is False
        assert agent._heartbeat_task.cancelled() or agent._heartbeat_task.done()

    @pytest.mark.asyncio
    async def test_stop_cancels_job_tasks(self):
        """Test that stop cancels running job tasks."""
        agent = WorkerAgent()
        agent._running = True

        # Mock a running job task
        job_task = asyncio.create_task(asyncio.sleep(100))
        agent._job_tasks["job-1"] = job_task

        # Mock executor
        agent.executor = MagicMock()
        agent.executor.cancel = AsyncMock()

        await agent.stop()

        assert agent._running is False
        agent.executor.cancel.assert_called_with("job-1")

    @pytest.mark.asyncio
    async def test_stop_closes_http_client(self):
        """Test that stop closes HTTP client."""
        agent = WorkerAgent()
        agent._running = True

        # Mock HTTP client
        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()
        agent._client = mock_client

        await agent.stop()

        mock_client.aclose.assert_called_once()


class TestWorkerAgentRegistration:
    """Tests for WorkerAgent registration."""

    @pytest.mark.asyncio
    async def test_registration_builds_correct_payload(self):
        """Test that registration sends correct data."""
        agent = WorkerAgent()

        # Mock detector
        agent.detector = MagicMock()
        agent.detector.get_hostname.return_value = "test-host"
        agent.detector.get_ip_address.return_value = "192.168.1.100"
        agent.detector.get_total_resources.return_value = ResourceSpec(
            cpu_cores=4, memory_mb=8192
        )
        agent.detector.get_capabilities.return_value = ["docker", "gpu"]

        # Mock HTTP client with successful response
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"worker_id": "worker-123"}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        agent._client = mock_client

        result = await agent._register()

        assert result is True
        assert agent.worker_id == "worker-123"

        # Verify the call was made
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/api/workers/register" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_registration_handles_failure(self):
        """Test registration handles HTTP failure."""
        agent = WorkerAgent()

        # Mock detector
        agent.detector = MagicMock()
        agent.detector.get_hostname.return_value = "test-host"
        agent.detector.get_ip_address.return_value = "192.168.1.100"
        agent.detector.get_total_resources.return_value = ResourceSpec(
            cpu_cores=4, memory_mb=8192
        )
        agent.detector.get_capabilities.return_value = []

        # Mock HTTP client with failure response
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        agent._client = mock_client

        result = await agent._register()

        assert result is False
        assert agent.worker_id is None

    @pytest.mark.asyncio
    async def test_registration_handles_exception(self):
        """Test registration handles exceptions."""
        agent = WorkerAgent()

        # Mock detector
        agent.detector = MagicMock()
        agent.detector.get_hostname.return_value = "test-host"
        agent.detector.get_ip_address.return_value = "192.168.1.100"
        agent.detector.get_total_resources.return_value = ResourceSpec(
            cpu_cores=4, memory_mb=8192
        )
        agent.detector.get_capabilities.return_value = []

        # Mock HTTP client that raises exception
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        agent._client = mock_client

        result = await agent._register()

        assert result is False


class TestWorkerAgentHeartbeat:
    """Tests for WorkerAgent heartbeat."""

    @pytest.mark.asyncio
    async def test_heartbeat_sends_status(self):
        """Test heartbeat sends worker status."""
        agent = WorkerAgent()
        agent.worker_id = "worker-123"
        agent._running = True

        # Mock detector
        agent.detector = MagicMock()
        agent.detector.get_available_resources.return_value = ResourceSpec(
            cpu_cores=2, memory_mb=4096
        )

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"jobs": []}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        agent._client = mock_client

        # Run one heartbeat
        agent._running = False  # Stop after one iteration
        await agent._send_heartbeat()

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/api/workers/worker-123/heartbeat" in call_args[0][0]


class TestWorkerAgentJobExecution:
    """Tests for WorkerAgent job execution."""

    @pytest.mark.asyncio
    async def test_execute_job_success(self):
        """Test successful job execution."""
        agent = WorkerAgent()
        agent.worker_id = "worker-123"

        # Create test job
        submission = JobSubmission(
            name="test-job",
            command="echo hello",
            resources=ResourceSpec(cpu_cores=1, memory_mb=512),
        )
        job = Job(
            job_id="job-123",
            submission=submission,
            status=JobStatus.ASSIGNED,
            assigned_worker="worker-123",
            created_at=datetime.utcnow(),
        )

        # Mock executor
        mock_result = JobResult(
            exit_code=0,
            stdout="hello\n",
            stderr="",
            execution_time_seconds=0.5,
        )
        agent.executor = MagicMock()
        agent.executor.execute = AsyncMock(return_value=mock_result)

        # Mock HTTP client for result upload
        mock_response = MagicMock()
        mock_response.is_success = True

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        agent._client = mock_client

        await agent._execute_job(job)

        agent.executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_job_failure(self):
        """Test job execution with failure."""
        agent = WorkerAgent()
        agent.worker_id = "worker-123"

        # Create test job
        submission = JobSubmission(
            name="failing-job",
            command="exit 1",
            resources=ResourceSpec(cpu_cores=1, memory_mb=512),
        )
        job = Job(
            job_id="job-456",
            submission=submission,
            status=JobStatus.ASSIGNED,
            assigned_worker="worker-123",
            created_at=datetime.utcnow(),
        )

        # Mock executor with failure
        mock_result = JobResult(
            exit_code=1,
            stdout="",
            stderr="Command failed",
            execution_time_seconds=0.1,
        )
        agent.executor = MagicMock()
        agent.executor.execute = AsyncMock(return_value=mock_result)

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.is_success = True

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        agent._client = mock_client

        await agent._execute_job(job)

        agent.executor.execute.assert_called_once()


class TestResourceSpec:
    """Tests for ResourceSpec model."""

    def test_resource_spec_creation(self):
        """Test ResourceSpec creation."""
        spec = ResourceSpec(cpu_cores=4, memory_mb=8192)
        assert spec.cpu_cores == 4
        assert spec.memory_mb == 8192

    def test_resource_spec_with_gpu(self):
        """Test ResourceSpec with GPU."""
        spec = ResourceSpec(cpu_cores=4, memory_mb=8192, gpu_count=2)
        assert spec.gpu_count == 2

    def test_resource_spec_comparison(self):
        """Test ResourceSpec fits comparison."""
        available = ResourceSpec(cpu_cores=8, memory_mb=16384)
        required = ResourceSpec(cpu_cores=4, memory_mb=8192)

        # Check if required fits in available
        assert required.cpu_cores <= available.cpu_cores
        assert required.memory_mb <= available.memory_mb


class TestJobSubmission:
    """Tests for JobSubmission model."""

    def test_job_submission_minimal(self):
        """Test minimal job submission."""
        submission = JobSubmission(
            name="test-job",
            command="echo test",
            resources=ResourceSpec(cpu_cores=1, memory_mb=256),
        )
        assert submission.name == "test-job"
        assert submission.command == "echo test"

    def test_job_submission_with_docker(self):
        """Test job submission with Docker image."""
        submission = JobSubmission(
            name="docker-job",
            command="python script.py",
            resources=ResourceSpec(cpu_cores=2, memory_mb=1024),
            docker_image="python:3.11",
        )
        assert submission.docker_image == "python:3.11"

    def test_job_submission_with_env(self):
        """Test job submission with environment variables."""
        submission = JobSubmission(
            name="env-job",
            command="echo $MY_VAR",
            resources=ResourceSpec(cpu_cores=1, memory_mb=256),
            environment={"MY_VAR": "hello"},
        )
        assert submission.environment["MY_VAR"] == "hello"
