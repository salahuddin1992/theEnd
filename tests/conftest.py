"""
Pytest Configuration and Fixtures
=================================

Shared fixtures for all tests.
"""

import asyncio
import tempfile
import warnings
from pathlib import Path
from typing import AsyncGenerator, Generator

# Suppress pynvml deprecation warning before any imports that might use it
warnings.filterwarnings("ignore", category=FutureWarning, module="pynvml")

import pytest
import pytest_asyncio

from distributed_cluster.models.job import JobPriority, JobSubmission
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
from distributed_cluster.scheduler import Scheduler, SchedulingPolicy
from distributed_cluster.security.auth import AuthConfig, AuthManager, EnrollmentMode
from distributed_cluster.storage.database import DatabaseConfig, SQLiteDatabase


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest_asyncio.fixture
async def database(temp_dir: Path) -> AsyncGenerator[SQLiteDatabase, None]:
    """Create test database."""
    config = DatabaseConfig(
        type="sqlite",
        path=str(temp_dir / "test_cluster.db")
    )
    db = SQLiteDatabase(config)
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
def auth_manager(temp_dir: Path) -> AuthManager:
    """Create test auth manager."""
    config = AuthConfig(
        secret_key="test-secret-key-for-testing-only",
        token_expiry_hours=1,
        enrollment_mode=EnrollmentMode.AUTO_APPROVE,
    )
    return AuthManager(config)


@pytest.fixture
def scheduler() -> Scheduler:
    """Create test scheduler."""
    return Scheduler(policy=SchedulingPolicy.BEST_FIT)


@pytest.fixture
def sample_resources() -> ResourceSpec:
    """Sample resource specification."""
    return ResourceSpec(
        cpu_cores=8,
        memory_mb=16384,
        gpu_count=1,
        gpu_memory_mb=8192,
    )


@pytest.fixture
def sample_worker(sample_resources: ResourceSpec) -> WorkerInfo:
    """Sample worker info."""
    from datetime import datetime
    return WorkerInfo(
        worker_id="test-worker-1",
        hostname="test-host",
        ip_address="192.168.1.100",
        port=8081,
        status=WorkerStatus.READY,
        total_resources=sample_resources,
        available_resources=sample_resources,
        tags=["cpu", "gpu", "docker"],
        labels={"zone": "us-east-1a", "env": "test"},
        platform="linux",
        docker_available=True,
        registered_at=datetime.utcnow(),
        last_heartbeat=datetime.utcnow(),  # Required for can_accept_jobs
    )


@pytest.fixture
def sample_job_submission() -> JobSubmission:
    """Sample job submission."""
    return JobSubmission(
        command="python -c 'print(hello)'",
        resources=ResourceSpec(
            cpu_cores=2,
            memory_mb=1024,
        ),
        priority=JobPriority.NORMAL,
        timeout_seconds=60,
        environment={"TEST_VAR": "test_value"},
    )


@pytest.fixture
def multiple_workers(sample_resources: ResourceSpec) -> list[WorkerInfo]:
    """Create multiple workers with varying resources."""
    from datetime import datetime

    workers = []
    now = datetime.utcnow()

    # Worker 1: High CPU, low GPU
    workers.append(WorkerInfo(
        worker_id="worker-cpu-1",
        hostname="cpu-host-1",
        ip_address="192.168.1.101",
        port=8081,
        status=WorkerStatus.READY,
        total_resources=ResourceSpec(cpu_cores=32, memory_mb=65536, gpu_count=0),
        available_resources=ResourceSpec(cpu_cores=32, memory_mb=65536, gpu_count=0),
        tags=["cpu", "high-memory"],
        labels={"type": "cpu-optimized"},
        platform="linux",
        docker_available=True,
        registered_at=now,
        last_heartbeat=now,
    ))

    # Worker 2: GPU worker
    workers.append(WorkerInfo(
        worker_id="worker-gpu-1",
        hostname="gpu-host-1",
        ip_address="192.168.1.102",
        port=8081,
        status=WorkerStatus.READY,
        total_resources=ResourceSpec(cpu_cores=8, memory_mb=32768, gpu_count=4, gpu_memory_mb=32768),
        available_resources=ResourceSpec(cpu_cores=8, memory_mb=32768, gpu_count=4, gpu_memory_mb=32768),
        tags=["gpu", "nvidia", "cuda"],
        labels={"type": "gpu-optimized"},
        platform="linux",
        docker_available=True,
        gpu_driver_version="535.104.05",
        registered_at=now,
        last_heartbeat=now,
    ))

    # Worker 3: Busy worker (limited available resources)
    workers.append(WorkerInfo(
        worker_id="worker-busy-1",
        hostname="busy-host-1",
        ip_address="192.168.1.103",
        port=8081,
        status=WorkerStatus.BUSY,
        total_resources=ResourceSpec(cpu_cores=16, memory_mb=32768, gpu_count=2),
        available_resources=ResourceSpec(cpu_cores=2, memory_mb=4096, gpu_count=0),
        tags=["cpu", "gpu"],
        labels={"type": "mixed"},
        platform="linux",
        docker_available=True,
        active_jobs=["job-1", "job-2", "job-3"],
        registered_at=now,
        last_heartbeat=now,
    ))

    # Worker 4: Offline worker
    workers.append(WorkerInfo(
        worker_id="worker-offline-1",
        hostname="offline-host-1",
        ip_address="192.168.1.104",
        port=8081,
        status=WorkerStatus.OFFLINE,
        total_resources=ResourceSpec(cpu_cores=8, memory_mb=16384),
        available_resources=ResourceSpec(cpu_cores=8, memory_mb=16384),
        tags=["cpu"],
        labels={},
        platform="linux",
        docker_available=False,
        registered_at=now,
        last_heartbeat=None,  # Offline, no heartbeat
    ))

    return workers
