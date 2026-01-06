"""
E2E Tests: Worker Management
============================

End-to-end tests for worker lifecycle including:
- Worker registration and discovery
- Worker health monitoring
- Worker draining and maintenance
- Resource allocation and tracking
"""

from datetime import datetime, timedelta, timezone

import pytest

from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
from distributed_cluster.storage.database import SQLiteDatabase


@pytest.mark.asyncio
class TestWorkerRegistration:
    """Tests for worker registration workflow."""

    async def test_register_new_worker(self, e2e_database: SQLiteDatabase):
        """Test registering a new worker."""
        now = datetime.now(timezone.utc)

        worker = WorkerInfo(
            worker_id="e2e-new-worker-001",
            hostname="new-node.nebula.local",
            ip_address="10.0.3.101",
            port=8081,
            status=WorkerStatus.READY,
            total_resources=ResourceSpec(cpu_cores=16, memory_mb=32768, gpu_count=0),
            available_resources=ResourceSpec(cpu_cores=16, memory_mb=32768, gpu_count=0),
            tags=["new", "test"],
            labels={"zone": "us-west-1a"},
            platform="linux",
            docker_available=True,
            registered_at=now,
            last_heartbeat=now,
        )

        await e2e_database.save_worker(worker)
        retrieved = await e2e_database.get_worker(worker.worker_id)

        assert retrieved is not None
        assert retrieved.worker_id == "e2e-new-worker-001"
        assert retrieved.status == WorkerStatus.READY
        assert retrieved.total_resources.cpu_cores == 16

    async def test_register_worker_with_gpu(self, e2e_database: SQLiteDatabase):
        """Test registering a GPU-enabled worker."""
        now = datetime.now(timezone.utc)

        worker = WorkerInfo(
            worker_id="e2e-gpu-worker-001",
            hostname="gpu-node.nebula.local",
            ip_address="10.0.3.102",
            port=8081,
            status=WorkerStatus.READY,
            total_resources=ResourceSpec(
                cpu_cores=32,
                memory_mb=131072,
                gpu_count=4,
                gpu_memory_mb=40960,
            ),
            available_resources=ResourceSpec(
                cpu_cores=32,
                memory_mb=131072,
                gpu_count=4,
                gpu_memory_mb=40960,
            ),
            tags=["gpu", "nvidia", "a100", "ml"],
            labels={"gpu_type": "A100", "zone": "us-east-1a"},
            platform="linux",
            docker_available=True,
            gpu_driver_version="535.154.05",
            registered_at=now,
            last_heartbeat=now,
        )

        await e2e_database.save_worker(worker)
        retrieved = await e2e_database.get_worker(worker.worker_id)

        assert retrieved.total_resources.gpu_count == 4
        assert retrieved.total_resources.gpu_memory_mb == 40960
        assert "nvidia" in retrieved.tags

    async def test_worker_reregistration(self, e2e_database: SQLiteDatabase):
        """Test that a worker can re-register with updated info."""
        now = datetime.now(timezone.utc)

        # Initial registration
        worker = WorkerInfo(
            worker_id="e2e-rereg-worker",
            hostname="rereg-node.nebula.local",
            ip_address="10.0.3.103",
            port=8081,
            status=WorkerStatus.READY,
            total_resources=ResourceSpec(cpu_cores=8, memory_mb=16384),
            available_resources=ResourceSpec(cpu_cores=8, memory_mb=16384),
            tags=["initial"],
            labels={},
            platform="linux",
            docker_available=False,
            registered_at=now,
            last_heartbeat=now,
        )
        await e2e_database.save_worker(worker)

        # Re-registration with updated info
        worker.docker_available = True
        worker.tags = ["updated", "docker"]
        worker.total_resources = ResourceSpec(cpu_cores=16, memory_mb=32768)
        worker.available_resources = ResourceSpec(cpu_cores=16, memory_mb=32768)
        await e2e_database.save_worker(worker)

        retrieved = await e2e_database.get_worker(worker.worker_id)
        assert retrieved.docker_available is True
        assert "docker" in retrieved.tags
        assert retrieved.total_resources.cpu_cores == 16


@pytest.mark.asyncio
class TestWorkerHealthMonitoring:
    """Tests for worker health and heartbeat monitoring."""

    async def test_worker_heartbeat_update(self, e2e_database: SQLiteDatabase):
        """Test updating worker heartbeat."""
        workers = await e2e_database.get_all_workers()
        worker = workers[0]

        new_heartbeat = datetime.now(timezone.utc)
        updated = await e2e_database.update_worker_heartbeat(
            worker.worker_id, new_heartbeat, WorkerStatus.READY
        )

        assert updated is True

        retrieved = await e2e_database.get_worker(worker.worker_id)
        assert retrieved.status == WorkerStatus.READY

    async def test_worker_status_transitions(self, e2e_database: SQLiteDatabase):
        """Test various worker status transitions."""
        workers = await e2e_database.get_all_workers()
        worker = workers[0]
        now = datetime.now(timezone.utc)

        # READY -> BUSY
        await e2e_database.update_worker_heartbeat(
            worker.worker_id, now, WorkerStatus.BUSY
        )
        retrieved = await e2e_database.get_worker(worker.worker_id)
        assert retrieved.status == WorkerStatus.BUSY

        # BUSY -> DRAINING
        await e2e_database.update_worker_heartbeat(
            worker.worker_id, now, WorkerStatus.DRAINING
        )
        retrieved = await e2e_database.get_worker(worker.worker_id)
        assert retrieved.status == WorkerStatus.DRAINING

        # DRAINING -> READY
        await e2e_database.update_worker_heartbeat(
            worker.worker_id, now, WorkerStatus.READY
        )
        retrieved = await e2e_database.get_worker(worker.worker_id)
        assert retrieved.status == WorkerStatus.READY

    async def test_detect_offline_workers(self, e2e_database: SQLiteDatabase):
        """Test detecting workers that have gone offline."""
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=5)

        # Create a worker with old heartbeat
        offline_worker = WorkerInfo(
            worker_id="e2e-offline-test",
            hostname="offline.nebula.local",
            ip_address="10.0.4.1",
            port=8081,
            status=WorkerStatus.READY,
            total_resources=ResourceSpec(cpu_cores=8, memory_mb=16384),
            available_resources=ResourceSpec(cpu_cores=8, memory_mb=16384),
            tags=[],
            labels={},
            platform="linux",
            docker_available=True,
            registered_at=threshold - timedelta(hours=1),
            last_heartbeat=threshold - timedelta(minutes=10),
        )
        await e2e_database.save_worker(offline_worker)

        # Mark as offline
        await e2e_database.update_worker_heartbeat(
            offline_worker.worker_id,
            offline_worker.last_heartbeat,
            WorkerStatus.OFFLINE,
        )

        retrieved = await e2e_database.get_worker(offline_worker.worker_id)
        assert retrieved.status == WorkerStatus.OFFLINE


@pytest.mark.asyncio
class TestWorkerDraining:
    """Tests for worker draining and maintenance workflows."""

    async def test_drain_worker(self, e2e_database: SQLiteDatabase):
        """Test draining a worker for maintenance."""
        workers = await e2e_database.get_all_workers()
        worker = workers[0]
        now = datetime.now(timezone.utc)

        # Drain the worker
        await e2e_database.update_worker_heartbeat(
            worker.worker_id, now, WorkerStatus.DRAINING
        )

        retrieved = await e2e_database.get_worker(worker.worker_id)
        assert retrieved.status == WorkerStatus.DRAINING

    async def test_undrain_worker(self, e2e_database: SQLiteDatabase):
        """Test returning a drained worker to service."""
        workers = await e2e_database.get_all_workers()
        worker = workers[0]
        now = datetime.now(timezone.utc)

        # First drain
        await e2e_database.update_worker_heartbeat(
            worker.worker_id, now, WorkerStatus.DRAINING
        )

        # Then undrain
        await e2e_database.update_worker_heartbeat(
            worker.worker_id, now, WorkerStatus.READY
        )

        retrieved = await e2e_database.get_worker(worker.worker_id)
        assert retrieved.status == WorkerStatus.READY

    async def test_remove_worker(self, e2e_database: SQLiteDatabase):
        """Test removing a worker from the cluster."""
        now = datetime.now(timezone.utc)

        # Create a temporary worker
        temp_worker = WorkerInfo(
            worker_id="e2e-temp-worker",
            hostname="temp.nebula.local",
            ip_address="10.0.5.1",
            port=8081,
            status=WorkerStatus.READY,
            total_resources=ResourceSpec(cpu_cores=4, memory_mb=8192),
            available_resources=ResourceSpec(cpu_cores=4, memory_mb=8192),
            tags=["temporary"],
            labels={},
            platform="linux",
            docker_available=True,
            registered_at=now,
            last_heartbeat=now,
        )
        await e2e_database.save_worker(temp_worker)

        # Verify it exists
        exists = await e2e_database.get_worker(temp_worker.worker_id)
        assert exists is not None

        # Remove the worker
        deleted = await e2e_database.delete_worker(temp_worker.worker_id)
        assert deleted is True

        # Verify it's gone
        gone = await e2e_database.get_worker(temp_worker.worker_id)
        assert gone is None


@pytest.mark.asyncio
class TestWorkerResourceTracking:
    """Tests for tracking worker resource allocation."""

    async def test_resource_allocation_tracking(self, e2e_database: SQLiteDatabase):
        """Test tracking resource allocation on workers."""
        workers = await e2e_database.get_all_workers()
        worker = workers[0]

        # Simulate resource allocation (reduce available resources)
        worker.available_resources = ResourceSpec(
            cpu_cores=worker.total_resources.cpu_cores - 8,
            memory_mb=worker.total_resources.memory_mb - 16384,
            gpu_count=max(0, worker.total_resources.gpu_count - 1),
        )
        worker.active_jobs = ["job-1", "job-2"]
        await e2e_database.save_worker(worker)

        retrieved = await e2e_database.get_worker(worker.worker_id)
        assert retrieved.available_resources.cpu_cores < retrieved.total_resources.cpu_cores
        assert len(retrieved.active_jobs) == 2

    async def test_resource_release_on_job_completion(self, e2e_database: SQLiteDatabase):
        """Test that resources are released when jobs complete."""
        workers = await e2e_database.get_all_workers()
        worker = workers[0]

        # First allocate resources
        original_available = worker.available_resources.cpu_cores
        worker.available_resources = ResourceSpec(
            cpu_cores=original_available - 4,
            memory_mb=worker.available_resources.memory_mb - 8192,
        )
        worker.active_jobs = ["job-to-complete"]
        await e2e_database.save_worker(worker)

        # Simulate job completion - release resources
        worker.available_resources = ResourceSpec(
            cpu_cores=original_available,
            memory_mb=worker.total_resources.memory_mb,
        )
        worker.active_jobs = []
        worker.completed_jobs_count = (worker.completed_jobs_count or 0) + 1
        await e2e_database.save_worker(worker)

        retrieved = await e2e_database.get_worker(worker.worker_id)
        assert len(retrieved.active_jobs) == 0
        assert retrieved.completed_jobs_count >= 1


@pytest.mark.asyncio
class TestWorkerDiscovery:
    """Tests for worker discovery and filtering."""

    async def test_get_all_workers(self, e2e_database: SQLiteDatabase):
        """Test getting all registered workers."""
        workers = await e2e_database.get_all_workers()
        assert len(workers) >= 4  # We seed with 4 workers

    async def test_filter_workers_by_status(self, e2e_database: SQLiteDatabase):
        """Test filtering workers by status."""
        workers = await e2e_database.get_all_workers()

        ready_workers = [w for w in workers if w.status == WorkerStatus.READY]
        assert len(ready_workers) > 0

        offline_workers = [w for w in workers if w.status == WorkerStatus.OFFLINE]
        # May or may not have offline workers depending on test state

    async def test_filter_workers_by_resources(self, e2e_database: SQLiteDatabase):
        """Test filtering workers by available resources."""
        workers = await e2e_database.get_all_workers()

        # Find workers with GPU
        gpu_workers = [w for w in workers if w.total_resources.gpu_count > 0]
        assert len(gpu_workers) >= 1  # We seed at least one GPU worker

        # Find high-memory workers
        high_mem_workers = [w for w in workers if w.total_resources.memory_mb >= 65536]
        assert len(high_mem_workers) >= 1

    async def test_filter_workers_by_tags(self, e2e_database: SQLiteDatabase):
        """Test filtering workers by tags."""
        workers = await e2e_database.get_all_workers()

        production_workers = [w for w in workers if "production" in w.tags]
        dev_workers = [w for w in workers if "dev" in w.tags]

        # We have both production and dev workers in seed data
        assert len(production_workers) >= 1 or len(dev_workers) >= 1

    async def test_filter_workers_by_labels(self, e2e_database: SQLiteDatabase):
        """Test filtering workers by labels."""
        workers = await e2e_database.get_all_workers()

        # Filter by zone
        us_east_workers = [
            w for w in workers
            if w.labels.get("zone", "").startswith("us-east")
        ]

        assert len(us_east_workers) >= 1
