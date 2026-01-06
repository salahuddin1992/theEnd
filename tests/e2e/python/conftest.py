"""
E2E Test Configuration and Fixtures
====================================

Fixtures for end-to-end testing including mock server setup,
API client initialization, and test data generators.
"""

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from distributed_cluster.models.job import Job, JobPriority, JobStatus, JobSubmission
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
def e2e_temp_dir() -> Generator[Path, None, None]:
    """Create temporary directory for E2E tests."""
    with tempfile.TemporaryDirectory(prefix="nebula_e2e_") as tmpdir:
        yield Path(tmpdir)


@pytest_asyncio.fixture
async def e2e_database(e2e_temp_dir: Path) -> AsyncGenerator[SQLiteDatabase, None]:
    """Create E2E test database with initial data."""
    config = DatabaseConfig(type="sqlite", path=str(e2e_temp_dir / "e2e_cluster.db"))
    db = SQLiteDatabase(config)
    await db.initialize()

    # Seed with initial workers
    workers = create_test_workers()
    for worker in workers:
        await db.save_worker(worker)

    yield db
    await db.close()


@pytest.fixture
def e2e_auth_manager(e2e_temp_dir: Path) -> AuthManager:
    """Create E2E auth manager with test configuration."""
    config = AuthConfig(
        secret_key="e2e-test-secret-key-for-testing",
        token_expiry_hours=24,
        enrollment_mode=EnrollmentMode.AUTO_APPROVE,
    )
    return AuthManager(config)


@pytest.fixture
def e2e_scheduler() -> Scheduler:
    """Create E2E scheduler."""
    return Scheduler(policy=SchedulingPolicy.BEST_FIT)


def create_test_workers() -> list[WorkerInfo]:
    """Create a set of test workers with various configurations."""
    now = datetime.now(timezone.utc)

    return [
        # High-performance CPU worker
        WorkerInfo(
            worker_id="e2e-worker-cpu-1",
            hostname="cpu-node-1.nebula.local",
            ip_address="10.0.1.101",
            port=8081,
            status=WorkerStatus.READY,
            total_resources=ResourceSpec(cpu_cores=64, memory_mb=131072, gpu_count=0),
            available_resources=ResourceSpec(cpu_cores=64, memory_mb=131072, gpu_count=0),
            tags=["cpu", "high-memory", "production"],
            labels={"zone": "us-east-1a", "tier": "compute"},
            platform="linux",
            docker_available=True,
            registered_at=now,
            last_heartbeat=now,
        ),
        # GPU worker for ML workloads
        WorkerInfo(
            worker_id="e2e-worker-gpu-1",
            hostname="gpu-node-1.nebula.local",
            ip_address="10.0.1.102",
            port=8081,
            status=WorkerStatus.READY,
            total_resources=ResourceSpec(cpu_cores=32, memory_mb=65536, gpu_count=8, gpu_memory_mb=81920),
            available_resources=ResourceSpec(cpu_cores=32, memory_mb=65536, gpu_count=8, gpu_memory_mb=81920),
            tags=["gpu", "nvidia", "cuda", "ml", "production"],
            labels={"zone": "us-east-1b", "tier": "gpu"},
            platform="linux",
            docker_available=True,
            gpu_driver_version="535.154.05",
            registered_at=now,
            last_heartbeat=now,
        ),
        # General purpose worker
        WorkerInfo(
            worker_id="e2e-worker-general-1",
            hostname="general-node-1.nebula.local",
            ip_address="10.0.1.103",
            port=8081,
            status=WorkerStatus.READY,
            total_resources=ResourceSpec(cpu_cores=16, memory_mb=32768, gpu_count=0),
            available_resources=ResourceSpec(cpu_cores=16, memory_mb=32768, gpu_count=0),
            tags=["cpu", "general", "production"],
            labels={"zone": "us-east-1c", "tier": "general"},
            platform="linux",
            docker_available=True,
            registered_at=now,
            last_heartbeat=now,
        ),
        # Development/staging worker
        WorkerInfo(
            worker_id="e2e-worker-dev-1",
            hostname="dev-node-1.nebula.local",
            ip_address="10.0.2.101",
            port=8081,
            status=WorkerStatus.READY,
            total_resources=ResourceSpec(cpu_cores=8, memory_mb=16384, gpu_count=1, gpu_memory_mb=8192),
            available_resources=ResourceSpec(cpu_cores=8, memory_mb=16384, gpu_count=1, gpu_memory_mb=8192),
            tags=["dev", "staging", "gpu"],
            labels={"zone": "us-west-2a", "tier": "dev"},
            platform="linux",
            docker_available=True,
            registered_at=now,
            last_heartbeat=now,
        ),
    ]


def create_test_job_submission(
    name: str = "e2e-test-job",
    cpu_cores: int = 4,
    memory_mb: int = 8192,
    gpu_count: int = 0,
    priority: JobPriority = JobPriority.NORMAL,
    timeout: int = 300,
) -> JobSubmission:
    """Create a test job submission with specified resources."""
    return JobSubmission(
        name=name,
        command=f"python -c 'print(\"Running {name}\")'",
        resources=ResourceSpec(
            cpu_cores=cpu_cores,
            memory_mb=memory_mb,
            gpu_count=gpu_count,
        ),
        priority=priority,
        timeout_seconds=timeout,
        environment={"E2E_TEST": "true", "JOB_NAME": name},
        tags=["e2e-test"],
    )


@pytest.fixture
def job_factory():
    """Factory fixture for creating test jobs."""
    return create_test_job_submission


@pytest.fixture
def worker_factory():
    """Factory fixture for creating test workers."""
    return create_test_workers
