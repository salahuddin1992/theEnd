"""Tests for the scheduler."""

from datetime import datetime

from distributed_cluster.models.job import Job, JobPriority, JobSubmission
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
from distributed_cluster.scheduler.scheduler import Scheduler, SchedulingPolicy


def create_worker(
    worker_id: str,
    cpu: float = 8.0,
    memory: int = 16384,
    gpu: int = 0,
    tags: list = None,
) -> WorkerInfo:
    """Helper to create a test worker."""
    return WorkerInfo(
        worker_id=worker_id,
        hostname=f"host-{worker_id}",
        ip_address="127.0.0.1",
        port=8766,
        status=WorkerStatus.READY,
        total_resources=ResourceSpec(
            cpu_cores=cpu,
            memory_mb=memory,
            gpu_count=gpu,
        ),
        available_resources=ResourceSpec(
            cpu_cores=cpu,
            memory_mb=memory,
            gpu_count=gpu,
        ),
        tags=tags or [],
        last_heartbeat=datetime.utcnow(),
    )


def create_job(
    job_id: str,
    cpu: float = 1.0,
    memory: int = 512,
    gpu: int = 0,
    priority: JobPriority = JobPriority.NORMAL,
    tags: list = None,
) -> Job:
    """Helper to create a test job."""
    submission = JobSubmission(
        command="echo",
        args=["hello"],
        resources=ResourceSpec(
            cpu_cores=cpu,
            memory_mb=memory,
            gpu_count=gpu,
        ),
        priority=priority,
        required_tags=tags or [],
    )
    job = Job(job_id=job_id, submission=submission)
    return job


class TestScheduler:
    """Tests for Scheduler."""

    def test_schedule_single_job(self):
        """Test scheduling a single job."""
        scheduler = Scheduler()
        jobs = [create_job("job-1")]
        workers = [create_worker("worker-1")]

        decisions = scheduler.schedule(jobs, workers)

        assert len(decisions) == 1
        assert decisions[0].job.job_id == "job-1"
        assert decisions[0].worker.worker_id == "worker-1"

    def test_schedule_no_workers(self):
        """Test scheduling with no workers."""
        scheduler = Scheduler()
        jobs = [create_job("job-1")]

        decisions = scheduler.schedule(jobs, [])

        assert len(decisions) == 0

    def test_schedule_no_jobs(self):
        """Test scheduling with no jobs."""
        scheduler = Scheduler()
        workers = [create_worker("worker-1")]

        decisions = scheduler.schedule([], workers)

        assert len(decisions) == 0

    def test_schedule_insufficient_resources(self):
        """Test job not scheduled when resources insufficient."""
        scheduler = Scheduler()
        jobs = [create_job("job-1", cpu=16.0)]  # Needs 16 cores
        workers = [create_worker("worker-1", cpu=8.0)]  # Only has 8

        decisions = scheduler.schedule(jobs, workers)

        assert len(decisions) == 0

    def test_schedule_multiple_jobs(self):
        """Test scheduling multiple jobs."""
        scheduler = Scheduler()
        jobs = [
            create_job("job-1", cpu=2.0),
            create_job("job-2", cpu=2.0),
        ]
        workers = [create_worker("worker-1", cpu=8.0)]

        decisions = scheduler.schedule(jobs, workers)

        assert len(decisions) == 2

    def test_schedule_respects_priority(self):
        """Test high priority jobs scheduled first."""
        scheduler = Scheduler()
        jobs = [
            create_job("job-low", priority=JobPriority.LOW),
            create_job("job-high", priority=JobPriority.HIGH),
        ]
        workers = [create_worker("worker-1")]

        decisions = scheduler.schedule(jobs, workers)

        assert len(decisions) == 2
        # High priority should be first
        assert decisions[0].job.job_id == "job-high"
        assert decisions[1].job.job_id == "job-low"

    def test_schedule_respects_tags(self):
        """Test jobs only go to workers with required tags."""
        scheduler = Scheduler()
        jobs = [create_job("job-gpu", gpu=1, tags=["gpu"])]
        workers = [
            create_worker("worker-no-gpu", gpu=0, tags=[]),
            create_worker("worker-gpu", gpu=2, tags=["gpu"]),
        ]

        decisions = scheduler.schedule(jobs, workers)

        assert len(decisions) == 1
        assert decisions[0].worker.worker_id == "worker-gpu"

    def test_best_fit_policy(self):
        """Test best-fit scheduling selects worker with least slack."""
        scheduler = Scheduler(policy=SchedulingPolicy.BEST_FIT)
        jobs = [create_job("job-1", cpu=2.0, memory=1024)]
        workers = [
            create_worker("worker-big", cpu=16.0, memory=32768),
            create_worker("worker-small", cpu=4.0, memory=2048),  # Better fit
        ]

        decisions = scheduler.schedule(jobs, workers)

        assert len(decisions) == 1
        assert decisions[0].worker.worker_id == "worker-small"

    def test_worst_fit_policy(self):
        """Test worst-fit scheduling selects worker with most slack."""
        scheduler = Scheduler(policy=SchedulingPolicy.WORST_FIT)
        jobs = [create_job("job-1", cpu=2.0, memory=1024)]
        workers = [
            create_worker("worker-big", cpu=16.0, memory=32768),  # Most slack
            create_worker("worker-small", cpu=4.0, memory=2048),
        ]

        decisions = scheduler.schedule(jobs, workers)

        assert len(decisions) == 1
        assert decisions[0].worker.worker_id == "worker-big"

    def test_least_loaded_policy(self):
        """Test least-loaded scheduling."""
        scheduler = Scheduler(policy=SchedulingPolicy.LEAST_LOADED)
        jobs = [create_job("job-1")]

        worker1 = create_worker("worker-1")
        worker1.active_jobs = ["existing-1", "existing-2"]

        worker2 = create_worker("worker-2")
        worker2.active_jobs = []  # No active jobs

        decisions = scheduler.schedule(jobs, [worker1, worker2])

        assert len(decisions) == 1
        assert decisions[0].worker.worker_id == "worker-2"

    def test_offline_worker_skipped(self):
        """Test offline workers are not scheduled to."""
        scheduler = Scheduler()
        jobs = [create_job("job-1")]

        worker = create_worker("worker-1")
        worker.status = WorkerStatus.OFFLINE

        decisions = scheduler.schedule(jobs, [worker])

        assert len(decisions) == 0

    def test_resources_allocated_on_schedule(self):
        """Test worker resources are updated after scheduling."""
        scheduler = Scheduler()
        jobs = [
            create_job("job-1", cpu=2.0, memory=2048),
            create_job("job-2", cpu=2.0, memory=2048),
        ]
        workers = [create_worker("worker-1", cpu=8.0, memory=8192)]

        decisions = scheduler.schedule(jobs, workers)

        assert len(decisions) == 2
        # Worker should have resources deducted
        worker = decisions[0].worker
        assert worker.available_resources.cpu_cores == 4.0
        assert worker.available_resources.memory_mb == 4096
