"""
Database Integration Tests
==========================

Tests for SQLite database persistence.
"""

from datetime import datetime, timedelta

import pytest

from distributed_cluster.models.events import Event, EventType
from distributed_cluster.models.job import Job, JobResult, JobStatus, JobSubmission
from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
from distributed_cluster.storage.database import SQLiteDatabase


@pytest.mark.asyncio
class TestWorkerPersistence:
    """Tests for worker persistence."""

    async def test_save_and_get_worker(self, database: SQLiteDatabase, sample_worker: WorkerInfo):
        """Test saving and retrieving a worker."""
        await database.save_worker(sample_worker)

        retrieved = await database.get_worker(sample_worker.worker_id)

        assert retrieved is not None
        assert retrieved.worker_id == sample_worker.worker_id
        assert retrieved.hostname == sample_worker.hostname
        assert retrieved.status == sample_worker.status
        assert retrieved.total_resources.cpu_cores == sample_worker.total_resources.cpu_cores

    async def test_get_nonexistent_worker(self, database: SQLiteDatabase):
        """Test getting a non-existent worker."""
        retrieved = await database.get_worker("nonexistent-worker-id")
        assert retrieved is None

    async def test_get_all_workers(self, database: SQLiteDatabase, multiple_workers: list[WorkerInfo]):
        """Test getting all workers."""
        for worker in multiple_workers:
            await database.save_worker(worker)

        all_workers = await database.get_all_workers()

        assert len(all_workers) == len(multiple_workers)
        worker_ids = {w.worker_id for w in all_workers}
        for worker in multiple_workers:
            assert worker.worker_id in worker_ids

    async def test_delete_worker(self, database: SQLiteDatabase, sample_worker: WorkerInfo):
        """Test deleting a worker."""
        await database.save_worker(sample_worker)

        deleted = await database.delete_worker(sample_worker.worker_id)
        assert deleted is True

        retrieved = await database.get_worker(sample_worker.worker_id)
        assert retrieved is None

    async def test_delete_nonexistent_worker(self, database: SQLiteDatabase):
        """Test deleting non-existent worker."""
        deleted = await database.delete_worker("nonexistent-worker-id")
        assert deleted is False

    async def test_update_worker_heartbeat(self, database: SQLiteDatabase, sample_worker: WorkerInfo):
        """Test updating worker heartbeat."""
        await database.save_worker(sample_worker)

        new_time = datetime.utcnow() + timedelta(minutes=5)
        new_status = WorkerStatus.BUSY

        updated = await database.update_worker_heartbeat(
            sample_worker.worker_id,
            new_time,
            new_status
        )
        assert updated is True

        retrieved = await database.get_worker(sample_worker.worker_id)
        assert retrieved.status == WorkerStatus.BUSY

    async def test_worker_update_replaces(self, database: SQLiteDatabase, sample_worker: WorkerInfo):
        """Test that saving worker with same ID replaces."""
        await database.save_worker(sample_worker)

        # Modify and save again
        sample_worker.status = WorkerStatus.BUSY
        sample_worker.completed_jobs_count = 10
        await database.save_worker(sample_worker)

        retrieved = await database.get_worker(sample_worker.worker_id)
        assert retrieved.status == WorkerStatus.BUSY
        assert retrieved.completed_jobs_count == 10


@pytest.mark.asyncio
class TestJobPersistence:
    """Tests for job persistence."""

    async def test_save_and_get_job(self, database: SQLiteDatabase, sample_job_submission: JobSubmission):
        """Test saving and retrieving a job."""
        job = Job(
            job_id="test-job-1",
            submission=sample_job_submission,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )

        await database.save_job(job)

        retrieved = await database.get_job(job.job_id)

        assert retrieved is not None
        assert retrieved.job_id == job.job_id
        assert retrieved.status == JobStatus.PENDING
        assert retrieved.submission.name == sample_job_submission.name

    async def test_get_jobs_by_status(self, database: SQLiteDatabase, sample_job_submission: JobSubmission):
        """Test getting jobs by status."""
        # Create jobs with different statuses
        statuses = [JobStatus.PENDING, JobStatus.PENDING, JobStatus.RUNNING, JobStatus.COMPLETED]

        for i, status in enumerate(statuses):
            job = Job(
                job_id=f"test-job-{i}",
                submission=sample_job_submission,
                status=status,
                created_at=datetime.utcnow(),
            )
            await database.save_job(job)

        pending_jobs = await database.get_jobs_by_status(JobStatus.PENDING)
        assert len(pending_jobs) == 2

        running_jobs = await database.get_jobs_by_status(JobStatus.RUNNING)
        assert len(running_jobs) == 1

    async def test_get_jobs_by_worker(self, database: SQLiteDatabase, sample_job_submission: JobSubmission):
        """Test getting jobs by assigned worker."""
        worker_id = "worker-1"

        for i in range(3):
            job = Job(
                job_id=f"worker-job-{i}",
                submission=sample_job_submission,
                status=JobStatus.RUNNING,
                assigned_worker=worker_id if i < 2 else "worker-2",
                created_at=datetime.utcnow(),
            )
            await database.save_job(job)

        worker_jobs = await database.get_jobs_by_worker(worker_id)
        assert len(worker_jobs) == 2
        for job in worker_jobs:
            assert job.assigned_worker == worker_id

    async def test_update_job_status(self, database: SQLiteDatabase, sample_job_submission: JobSubmission):
        """Test updating job status."""
        job = Job(
            job_id="test-job-1",
            submission=sample_job_submission,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        await database.save_job(job)

        # Update to running
        now = datetime.utcnow()
        updated = await database.update_job_status(
            job.job_id,
            JobStatus.RUNNING,
            started_at=now,
            assigned_worker="worker-1"
        )
        assert updated is True

        retrieved = await database.get_job(job.job_id)
        assert retrieved.status == JobStatus.RUNNING
        assert retrieved.assigned_worker == "worker-1"

    async def test_job_with_result(self, database: SQLiteDatabase, sample_job_submission: JobSubmission):
        """Test saving job with result."""
        result = JobResult(
            exit_code=0,
            stdout="Hello, World!",
            stderr="",
            execution_time_seconds=1.5,
            peak_memory_mb=128,
        )

        job = Job(
            job_id="completed-job-1",
            submission=sample_job_submission,
            status=JobStatus.COMPLETED,
            result=result,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        await database.save_job(job)

        retrieved = await database.get_job(job.job_id)
        assert retrieved.result is not None
        assert retrieved.result.exit_code == 0
        assert retrieved.result.stdout == "Hello, World!"


@pytest.mark.asyncio
class TestEventPersistence:
    """Tests for event persistence."""

    async def test_save_and_get_events(self, database: SQLiteDatabase):
        """Test saving and retrieving events."""
        event = Event(
            event_type=EventType.JOB_SUBMITTED,
            timestamp=datetime.utcnow(),
            source="test",
            data={"job_name": "test-job"},
            message="Job submitted for testing",
            job_id="test-job-1",
        )

        await database.save_event(event)

        events = await database.get_recent_events(limit=10)

        assert len(events) == 1
        assert events[0].event_type == EventType.JOB_SUBMITTED
        assert events[0].job_id == "test-job-1"

    async def test_events_ordered_by_timestamp(self, database: SQLiteDatabase):
        """Test that events are ordered by timestamp descending."""
        base_time = datetime.utcnow()

        for i in range(5):
            event = Event(
                event_type=EventType.WORKER_HEARTBEAT,
                timestamp=base_time + timedelta(seconds=i),
                source="test",
                data={"index": i},
                worker_id=f"worker-{i}",
            )
            await database.save_event(event)

        events = await database.get_recent_events(limit=10)

        assert len(events) == 5
        # Should be in descending order (newest first)
        for i, event in enumerate(events):
            assert event.data["index"] == 4 - i

    async def test_events_limit(self, database: SQLiteDatabase):
        """Test that event limit is respected."""
        for i in range(20):
            event = Event(
                event_type=EventType.JOB_COMPLETED,
                timestamp=datetime.utcnow(),
                source="test",
                data={},
                job_id=f"job-{i}",
            )
            await database.save_event(event)

        events = await database.get_recent_events(limit=5)
        assert len(events) == 5
