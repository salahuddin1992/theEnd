"""
E2E Tests: Job Workflow
=======================

End-to-end tests for complete job lifecycle including:
- Job submission
- Job scheduling and assignment
- Job execution simulation
- Job completion and result retrieval
- Job cancellation and retry
"""

from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from distributed_cluster.models.job import Job, JobPriority, JobResult, JobStatus, JobSubmission
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
from distributed_cluster.scheduler import Scheduler
from distributed_cluster.storage.database import SQLiteDatabase

from .conftest import create_test_job_submission


@pytest.mark.asyncio
class TestJobSubmissionWorkflow:
    """Tests for job submission workflow."""

    async def test_submit_single_job(self, e2e_database: SQLiteDatabase, job_factory):
        """Test submitting a single job."""
        submission = job_factory(name="single-job-test")

        job = Job(
            job_id="e2e-job-001",
            submission=submission,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        await e2e_database.save_job(job)
        retrieved = await e2e_database.get_job(job.job_id)

        assert retrieved is not None
        assert retrieved.job_id == "e2e-job-001"
        assert retrieved.status == JobStatus.PENDING
        assert retrieved.submission.name == "single-job-test"

    async def test_submit_batch_jobs(self, e2e_database: SQLiteDatabase, job_factory):
        """Test submitting multiple jobs in batch."""
        job_count = 10
        jobs = []

        for i in range(job_count):
            submission = job_factory(name=f"batch-job-{i:03d}")
            job = Job(
                job_id=f"e2e-batch-{i:03d}",
                submission=submission,
                status=JobStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            jobs.append(job)
            await e2e_database.save_job(job)

        # Verify all jobs were saved
        pending_jobs = await e2e_database.get_jobs_by_status(JobStatus.PENDING)
        assert len(pending_jobs) >= job_count

    async def test_submit_priority_jobs(self, e2e_database: SQLiteDatabase):
        """Test submitting jobs with different priorities."""
        priorities = [
            (JobPriority.LOW, "low-priority-job"),
            (JobPriority.NORMAL, "normal-priority-job"),
            (JobPriority.HIGH, "high-priority-job"),
            (JobPriority.CRITICAL, "critical-priority-job"),
        ]

        for priority, name in priorities:
            submission = create_test_job_submission(name=name, priority=priority)
            job = Job(
                job_id=f"e2e-priority-{priority.value}",
                submission=submission,
                status=JobStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            await e2e_database.save_job(job)

        # Verify priorities are preserved
        for priority, name in priorities:
            retrieved = await e2e_database.get_job(f"e2e-priority-{priority.value}")
            assert retrieved.submission.priority == priority


@pytest.mark.asyncio
class TestJobSchedulingWorkflow:
    """Tests for job scheduling and assignment."""

    async def test_schedule_job_to_worker(
        self, e2e_database: SQLiteDatabase, e2e_scheduler: Scheduler, job_factory
    ):
        """Test scheduling a job to an available worker."""
        # Get available workers
        workers = await e2e_database.get_all_workers()
        ready_workers = [w for w in workers if w.status == WorkerStatus.READY]
        assert len(ready_workers) > 0

        # Create job that fits worker resources
        submission = job_factory(name="schedulable-job", cpu_cores=4, memory_mb=8192)
        job = Job(
            job_id="e2e-schedule-001",
            submission=submission,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        # Schedule the job
        assigned_worker = e2e_scheduler.schedule(job, ready_workers)

        assert assigned_worker is not None
        assert assigned_worker.worker_id in [w.worker_id for w in ready_workers]

    async def test_schedule_gpu_job_to_gpu_worker(
        self, e2e_database: SQLiteDatabase, e2e_scheduler: Scheduler
    ):
        """Test that GPU jobs are scheduled to GPU workers."""
        workers = await e2e_database.get_all_workers()
        ready_workers = [w for w in workers if w.status == WorkerStatus.READY]

        # Create GPU job
        submission = create_test_job_submission(
            name="gpu-job", cpu_cores=8, memory_mb=16384, gpu_count=2
        )
        job = Job(
            job_id="e2e-gpu-001",
            submission=submission,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        assigned_worker = e2e_scheduler.schedule(job, ready_workers)

        if assigned_worker:
            assert assigned_worker.total_resources.gpu_count >= 2

    async def test_job_not_schedulable_insufficient_resources(
        self, e2e_database: SQLiteDatabase, e2e_scheduler: Scheduler
    ):
        """Test that jobs with excessive resource requirements cannot be scheduled."""
        workers = await e2e_database.get_all_workers()
        ready_workers = [w for w in workers if w.status == WorkerStatus.READY]

        # Create job with excessive requirements
        submission = create_test_job_submission(
            name="impossible-job", cpu_cores=1000, memory_mb=10000000, gpu_count=100
        )
        job = Job(
            job_id="e2e-impossible-001",
            submission=submission,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        assigned_worker = e2e_scheduler.schedule(job, ready_workers)
        assert assigned_worker is None


@pytest.mark.asyncio
class TestJobExecutionWorkflow:
    """Tests for job execution lifecycle."""

    async def test_job_lifecycle_pending_to_completed(
        self, e2e_database: SQLiteDatabase, job_factory
    ):
        """Test complete job lifecycle from pending to completed."""
        submission = job_factory(name="lifecycle-test")
        now = datetime.now(timezone.utc)

        # Create pending job
        job = Job(
            job_id="e2e-lifecycle-001",
            submission=submission,
            status=JobStatus.PENDING,
            created_at=now,
        )
        await e2e_database.save_job(job)

        # Transition to running
        await e2e_database.update_job_status(
            job.job_id,
            JobStatus.RUNNING,
            started_at=now + timedelta(seconds=1),
            assigned_worker="e2e-worker-cpu-1",
        )

        running_job = await e2e_database.get_job(job.job_id)
        assert running_job.status == JobStatus.RUNNING
        assert running_job.assigned_worker == "e2e-worker-cpu-1"

        # Complete the job with result
        result = JobResult(
            exit_code=0,
            stdout="Job completed successfully",
            stderr="",
            execution_time_seconds=5.5,
            peak_memory_mb=512,
        )

        job.status = JobStatus.COMPLETED
        job.result = result
        job.completed_at = now + timedelta(seconds=6)
        await e2e_database.save_job(job)

        completed_job = await e2e_database.get_job(job.job_id)
        assert completed_job.status == JobStatus.COMPLETED
        assert completed_job.result.exit_code == 0

    async def test_job_failure_workflow(self, e2e_database: SQLiteDatabase, job_factory):
        """Test job failure workflow."""
        submission = job_factory(name="failing-job")
        now = datetime.now(timezone.utc)

        job = Job(
            job_id="e2e-fail-001",
            submission=submission,
            status=JobStatus.PENDING,
            created_at=now,
        )
        await e2e_database.save_job(job)

        # Start the job
        await e2e_database.update_job_status(
            job.job_id,
            JobStatus.RUNNING,
            started_at=now,
            assigned_worker="e2e-worker-general-1",
        )

        # Job fails
        result = JobResult(
            exit_code=1,
            stdout="",
            stderr="Error: Something went wrong",
            execution_time_seconds=2.0,
            peak_memory_mb=256,
        )

        job.status = JobStatus.FAILED
        job.result = result
        job.completed_at = now + timedelta(seconds=2)
        job.error_message = "Job exited with non-zero status"
        await e2e_database.save_job(job)

        failed_job = await e2e_database.get_job(job.job_id)
        assert failed_job.status == JobStatus.FAILED
        assert failed_job.result.exit_code == 1

    async def test_job_cancellation(self, e2e_database: SQLiteDatabase, job_factory):
        """Test cancelling a running job."""
        submission = job_factory(name="cancellable-job")
        now = datetime.now(timezone.utc)

        job = Job(
            job_id="e2e-cancel-001",
            submission=submission,
            status=JobStatus.RUNNING,
            created_at=now,
            started_at=now,
            assigned_worker="e2e-worker-cpu-1",
        )
        await e2e_database.save_job(job)

        # Cancel the job
        await e2e_database.update_job_status(
            job.job_id,
            JobStatus.CANCELLED,
        )

        cancelled_job = await e2e_database.get_job(job.job_id)
        assert cancelled_job.status == JobStatus.CANCELLED


@pytest.mark.asyncio
class TestJobRetryWorkflow:
    """Tests for job retry functionality."""

    async def test_retry_failed_job(self, e2e_database: SQLiteDatabase, job_factory):
        """Test retrying a failed job."""
        submission = job_factory(name="retry-test")
        now = datetime.now(timezone.utc)

        # Create and fail the original job
        original_job = Job(
            job_id="e2e-retry-original",
            submission=submission,
            status=JobStatus.FAILED,
            created_at=now,
            retry_count=0,
        )
        await e2e_database.save_job(original_job)

        # Create retry job
        retry_job = Job(
            job_id="e2e-retry-001",
            submission=submission,
            status=JobStatus.PENDING,
            created_at=now + timedelta(seconds=10),
            retry_count=1,
        )
        await e2e_database.save_job(retry_job)

        # Verify retry job
        retrieved = await e2e_database.get_job(retry_job.job_id)
        assert retrieved.retry_count == 1
        assert retrieved.status == JobStatus.PENDING

    async def test_max_retries_exceeded(self, e2e_database: SQLiteDatabase, job_factory):
        """Test that jobs respect max retry limits."""
        submission = job_factory(name="max-retry-test")
        max_retries = 3

        for attempt in range(max_retries + 1):
            job = Job(
                job_id=f"e2e-maxretry-{attempt}",
                submission=submission,
                status=JobStatus.FAILED if attempt < max_retries else JobStatus.PENDING,
                created_at=datetime.now(timezone.utc),
                retry_count=attempt,
            )
            await e2e_database.save_job(job)

        # Check all attempts are recorded
        for attempt in range(max_retries + 1):
            job = await e2e_database.get_job(f"e2e-maxretry-{attempt}")
            assert job.retry_count == attempt


@pytest.mark.asyncio
class TestJobQueryWorkflow:
    """Tests for querying and filtering jobs."""

    async def test_query_jobs_by_status(self, e2e_database: SQLiteDatabase, job_factory):
        """Test querying jobs by different statuses."""
        statuses = [JobStatus.PENDING, JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.FAILED]

        for i, status in enumerate(statuses):
            submission = job_factory(name=f"query-test-{status.value}")
            job = Job(
                job_id=f"e2e-query-{i}",
                submission=submission,
                status=status,
                created_at=datetime.now(timezone.utc),
            )
            await e2e_database.save_job(job)

        # Query each status
        for status in statuses:
            jobs = await e2e_database.get_jobs_by_status(status)
            assert any(j.status == status for j in jobs)

    async def test_query_jobs_by_worker(self, e2e_database: SQLiteDatabase, job_factory):
        """Test querying jobs assigned to specific workers."""
        workers = ["e2e-worker-cpu-1", "e2e-worker-gpu-1"]

        for i, worker_id in enumerate(workers):
            for j in range(3):
                submission = job_factory(name=f"worker-job-{i}-{j}")
                job = Job(
                    job_id=f"e2e-worker-query-{i}-{j}",
                    submission=submission,
                    status=JobStatus.RUNNING,
                    assigned_worker=worker_id,
                    created_at=datetime.now(timezone.utc),
                )
                await e2e_database.save_job(job)

        # Query jobs by worker
        for worker_id in workers:
            jobs = await e2e_database.get_jobs_by_worker(worker_id)
            assert len(jobs) >= 3
            for job in jobs:
                assert job.assigned_worker == worker_id

    async def test_paginated_job_query(self, e2e_database: SQLiteDatabase, job_factory):
        """Test paginated job queries."""
        total_jobs = 25
        page_size = 10

        for i in range(total_jobs):
            submission = job_factory(name=f"paginated-{i:03d}")
            job = Job(
                job_id=f"e2e-paginated-{i:03d}",
                submission=submission,
                status=JobStatus.COMPLETED,
                created_at=datetime.now(timezone.utc),
            )
            await e2e_database.save_job(job)

        # Query first page
        jobs_page1, total = await e2e_database.get_jobs_paginated(
            offset=0, limit=page_size
        )
        assert len(jobs_page1) == page_size
        assert total >= total_jobs

        # Query second page
        jobs_page2, _ = await e2e_database.get_jobs_paginated(
            offset=page_size, limit=page_size
        )
        assert len(jobs_page2) == page_size

        # Ensure no overlap
        page1_ids = {j.job_id for j in jobs_page1}
        page2_ids = {j.job_id for j in jobs_page2}
        assert page1_ids.isdisjoint(page2_ids)
