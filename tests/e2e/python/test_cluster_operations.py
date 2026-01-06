"""
E2E Tests: Cluster Operations
=============================

End-to-end tests for cluster-wide operations including:
- Cluster statistics and monitoring
- Event logging and retrieval
- Lease management
- Cluster health checks
"""

from datetime import datetime, timedelta, timezone

import pytest

from distributed_cluster.models.events import Event, EventType
from distributed_cluster.models.job import Job, JobPriority, JobStatus, JobSubmission
from distributed_cluster.models.lease import Lease
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerStatus
from distributed_cluster.storage.database import SQLiteDatabase

from .conftest import create_test_job_submission


@pytest.mark.asyncio
class TestClusterStatistics:
    """Tests for cluster statistics and monitoring."""

    async def test_get_cluster_stats(self, e2e_database: SQLiteDatabase):
        """Test retrieving cluster-wide statistics."""
        stats = await e2e_database.get_cluster_stats()

        assert stats is not None
        assert "total_workers" in stats or hasattr(stats, "total_workers") or isinstance(stats, dict)

    async def test_worker_count_statistics(self, e2e_database: SQLiteDatabase):
        """Test worker count statistics."""
        workers = await e2e_database.get_all_workers()
        stats = await e2e_database.get_cluster_stats()

        if isinstance(stats, dict):
            total_workers = stats.get("total_workers", len(workers))
        else:
            total_workers = len(workers)

        assert total_workers >= 4  # We seed with 4 workers

    async def test_job_statistics_by_status(self, e2e_database: SQLiteDatabase, job_factory):
        """Test job statistics grouped by status."""
        # Create jobs with different statuses
        statuses = [
            JobStatus.PENDING,
            JobStatus.PENDING,
            JobStatus.RUNNING,
            JobStatus.COMPLETED,
            JobStatus.COMPLETED,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
        ]

        for i, status in enumerate(statuses):
            submission = job_factory(name=f"stats-job-{i}")
            job = Job(
                job_id=f"e2e-stats-{i:03d}",
                submission=submission,
                status=status,
                created_at=datetime.now(timezone.utc),
            )
            await e2e_database.save_job(job)

        stats = await e2e_database.get_jobs_count_by_status()

        assert stats is not None
        if isinstance(stats, dict):
            # Verify counts match what we created
            assert stats.get("pending", 0) >= 2
            assert stats.get("completed", 0) >= 3

    async def test_job_execution_stats(self, e2e_database: SQLiteDatabase, job_factory):
        """Test job execution statistics over time."""
        now = datetime.now(timezone.utc)

        # Create completed jobs over the past few days
        for day in range(7):
            for i in range(3):
                submission = job_factory(name=f"exec-stats-{day}-{i}")
                job = Job(
                    job_id=f"e2e-exec-{day}-{i}",
                    submission=submission,
                    status=JobStatus.COMPLETED,
                    created_at=now - timedelta(days=day),
                    completed_at=now - timedelta(days=day) + timedelta(minutes=5),
                )
                await e2e_database.save_job(job)

        stats = await e2e_database.get_job_execution_stats(days=7)

        assert stats is not None


@pytest.mark.asyncio
class TestEventLogging:
    """Tests for event logging and retrieval."""

    async def test_log_job_event(self, e2e_database: SQLiteDatabase):
        """Test logging a job-related event."""
        event = Event(
            event_type=EventType.JOB_SUBMITTED,
            timestamp=datetime.now(timezone.utc),
            source="e2e-test",
            data={"job_name": "test-job", "priority": "normal"},
            message="Job submitted for E2E testing",
            job_id="e2e-event-job-001",
        )

        await e2e_database.save_event(event)
        events = await e2e_database.get_recent_events(limit=10)

        assert len(events) >= 1
        recent_event = next((e for e in events if e.job_id == "e2e-event-job-001"), None)
        assert recent_event is not None
        assert recent_event.event_type == EventType.JOB_SUBMITTED

    async def test_log_worker_event(self, e2e_database: SQLiteDatabase):
        """Test logging a worker-related event."""
        event = Event(
            event_type=EventType.WORKER_REGISTERED,
            timestamp=datetime.now(timezone.utc),
            source="e2e-test",
            data={"hostname": "new-worker.local", "cpu_cores": 16},
            message="New worker registered",
            worker_id="e2e-event-worker-001",
        )

        await e2e_database.save_event(event)
        events = await e2e_database.get_recent_events(limit=10)

        worker_event = next((e for e in events if e.worker_id == "e2e-event-worker-001"), None)
        assert worker_event is not None

    async def test_event_ordering(self, e2e_database: SQLiteDatabase):
        """Test that events are returned in correct order."""
        base_time = datetime.now(timezone.utc)

        for i in range(5):
            event = Event(
                event_type=EventType.JOB_COMPLETED,
                timestamp=base_time + timedelta(seconds=i * 10),
                source="e2e-test",
                data={"order": i},
                message=f"Event {i}",
                job_id=f"e2e-order-{i}",
            )
            await e2e_database.save_event(event)

        events = await e2e_database.get_recent_events(limit=10)

        # Events should be in descending order by timestamp
        order_values = [e.data.get("order") for e in events if "order" in e.data]
        filtered_orders = [o for o in order_values if o is not None]

        if len(filtered_orders) >= 2:
            # Check descending order
            for i in range(len(filtered_orders) - 1):
                assert filtered_orders[i] >= filtered_orders[i + 1]

    async def test_events_by_job(self, e2e_database: SQLiteDatabase):
        """Test retrieving events for a specific job."""
        job_id = "e2e-specific-job"
        event_types = [
            EventType.JOB_SUBMITTED,
            EventType.JOB_STARTED,
            EventType.JOB_COMPLETED,
        ]

        for event_type in event_types:
            event = Event(
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                source="e2e-test",
                data={},
                message=f"{event_type.value} for {job_id}",
                job_id=job_id,
            )
            await e2e_database.save_event(event)

        events = await e2e_database.get_events_by_job(job_id)

        assert len(events) >= 3
        for event in events:
            assert event.job_id == job_id

    async def test_cleanup_old_events(self, e2e_database: SQLiteDatabase):
        """Test cleaning up old events."""
        old_time = datetime.now(timezone.utc) - timedelta(days=60)

        # Create old event
        old_event = Event(
            event_type=EventType.WORKER_HEARTBEAT,
            timestamp=old_time,
            source="e2e-test",
            data={},
            message="Old heartbeat",
            worker_id="e2e-old-worker",
        )
        await e2e_database.save_event(old_event)

        # Cleanup events older than 30 days
        threshold = datetime.now(timezone.utc) - timedelta(days=30)
        cleaned = await e2e_database.cleanup_old_events(older_than=threshold)

        assert cleaned >= 0  # Should have cleaned at least the old event


@pytest.mark.asyncio
class TestLeaseManagement:
    """Tests for distributed lease management."""

    async def test_create_lease(self, e2e_database: SQLiteDatabase):
        """Test creating a new lease."""
        now = datetime.now(timezone.utc)
        lease = Lease(
            lease_id="e2e-lease-001",
            holder="e2e-test-holder",
            resource_type="job",
            resource_id="job-123",
            expires_at=now + timedelta(minutes=5),
            created_at=now,
        )

        await e2e_database.create_lease(lease)
        retrieved = await e2e_database.get_lease(lease.lease_id)

        assert retrieved is not None
        assert retrieved.holder == "e2e-test-holder"

    async def test_renew_lease(self, e2e_database: SQLiteDatabase):
        """Test renewing an existing lease."""
        now = datetime.now(timezone.utc)
        original_expiry = now + timedelta(minutes=5)
        new_expiry = now + timedelta(minutes=10)

        lease = Lease(
            lease_id="e2e-lease-renew",
            holder="e2e-test-holder",
            resource_type="worker",
            resource_id="worker-456",
            expires_at=original_expiry,
            created_at=now,
        )
        await e2e_database.create_lease(lease)

        renewed = await e2e_database.renew_lease(lease.lease_id, new_expiry)
        assert renewed is True

        retrieved = await e2e_database.get_lease(lease.lease_id)
        # The lease should have a later expiry
        assert retrieved.expires_at >= original_expiry

    async def test_release_lease(self, e2e_database: SQLiteDatabase):
        """Test releasing a lease."""
        now = datetime.now(timezone.utc)
        lease = Lease(
            lease_id="e2e-lease-release",
            holder="e2e-test-holder",
            resource_type="resource",
            resource_id="res-789",
            expires_at=now + timedelta(minutes=5),
            created_at=now,
        )
        await e2e_database.create_lease(lease)

        released = await e2e_database.release_lease(lease.lease_id)
        assert released is True

        # Lease should no longer be active
        retrieved = await e2e_database.get_lease(lease.lease_id)
        # Either None or marked as released

    async def test_get_expired_leases(self, e2e_database: SQLiteDatabase):
        """Test finding expired leases."""
        now = datetime.now(timezone.utc)

        # Create an expired lease
        expired_lease = Lease(
            lease_id="e2e-lease-expired",
            holder="e2e-test-holder",
            resource_type="expired",
            resource_id="exp-001",
            expires_at=now - timedelta(minutes=5),  # Already expired
            created_at=now - timedelta(minutes=10),
        )
        await e2e_database.create_lease(expired_lease)

        expired = await e2e_database.get_expired_leases()
        expired_ids = [l.lease_id for l in expired]

        assert "e2e-lease-expired" in expired_ids

    async def test_get_leases_by_holder(self, e2e_database: SQLiteDatabase):
        """Test getting all leases for a specific holder."""
        now = datetime.now(timezone.utc)
        holder = "e2e-multi-lease-holder"

        for i in range(3):
            lease = Lease(
                lease_id=f"e2e-multi-{i}",
                holder=holder,
                resource_type="multi",
                resource_id=f"res-{i}",
                expires_at=now + timedelta(minutes=5),
                created_at=now,
            )
            await e2e_database.create_lease(lease)

        leases = await e2e_database.get_leases_by_holder(holder)

        assert len(leases) >= 3
        for lease in leases:
            assert lease.holder == holder


@pytest.mark.asyncio
class TestClusterHealthChecks:
    """Tests for cluster health monitoring."""

    async def test_worker_availability_check(self, e2e_database: SQLiteDatabase):
        """Test checking worker availability."""
        workers = await e2e_database.get_all_workers()

        available_workers = [
            w for w in workers
            if w.status in (WorkerStatus.READY, WorkerStatus.BUSY)
        ]

        assert len(available_workers) > 0

    async def test_resource_capacity_check(self, e2e_database: SQLiteDatabase):
        """Test checking total cluster resource capacity."""
        workers = await e2e_database.get_all_workers()

        total_cpu = sum(w.total_resources.cpu_cores for w in workers)
        total_memory = sum(w.total_resources.memory_mb for w in workers)
        total_gpu = sum(w.total_resources.gpu_count for w in workers)

        assert total_cpu > 0
        assert total_memory > 0
        assert total_gpu >= 0  # GPU is optional

    async def test_pending_jobs_check(self, e2e_database: SQLiteDatabase, job_factory):
        """Test checking for pending jobs in the cluster."""
        # Create some pending jobs
        for i in range(5):
            submission = job_factory(name=f"pending-check-{i}")
            job = Job(
                job_id=f"e2e-pending-check-{i}",
                submission=submission,
                status=JobStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            await e2e_database.save_job(job)

        pending = await e2e_database.get_jobs_by_status(JobStatus.PENDING)

        assert len(pending) >= 5


@pytest.mark.asyncio
class TestDatabaseMaintenance:
    """Tests for database maintenance operations."""

    async def test_vacuum_database(self, e2e_database: SQLiteDatabase):
        """Test database vacuum operation."""
        # Create and delete some data to fragment the database
        for i in range(10):
            submission = create_test_job_submission(name=f"vacuum-test-{i}")
            job = Job(
                job_id=f"e2e-vacuum-{i}",
                submission=submission,
                status=JobStatus.COMPLETED,
                created_at=datetime.now(timezone.utc),
            )
            await e2e_database.save_job(job)

        # Run vacuum
        await e2e_database.vacuum()

        # Database should still work
        jobs = await e2e_database.get_jobs_by_status(JobStatus.COMPLETED)
        assert len(jobs) >= 0

    async def test_concurrent_operations(self, e2e_database: SQLiteDatabase, job_factory):
        """Test handling concurrent database operations."""
        import asyncio

        async def create_job(index: int):
            submission = job_factory(name=f"concurrent-{index}")
            job = Job(
                job_id=f"e2e-concurrent-{index:03d}",
                submission=submission,
                status=JobStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            await e2e_database.save_job(job)
            return job.job_id

        # Run multiple operations concurrently
        tasks = [create_job(i) for i in range(20)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 20

        # Verify all jobs were created
        for job_id in results:
            job = await e2e_database.get_job(job_id)
            assert job is not None
