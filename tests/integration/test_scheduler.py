"""
Scheduler Integration Tests
===========================

Tests for job scheduling and worker selection.
"""

from datetime import datetime

from distributed_cluster.models.job import Job, JobPriority, JobStatus, JobSubmission
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
from distributed_cluster.scheduler import Scheduler, SchedulingPolicy
from distributed_cluster.scheduler.scoring import SCORING_PROFILES, CompositeScorer, ScoringWeights


class TestSchedulerBasic:
    """Basic scheduler tests."""

    def test_scheduler_creation(self, scheduler: Scheduler):
        """Test scheduler can be created."""
        assert scheduler is not None
        assert scheduler.policy == SchedulingPolicy.BEST_FIT

    def test_add_remove_worker(self, scheduler: Scheduler, sample_worker: WorkerInfo):
        """Test adding and removing workers."""
        # Add worker
        scheduler.add_worker(sample_worker)
        assert sample_worker.worker_id in scheduler.workers

        # Remove worker
        removed = scheduler.remove_worker(sample_worker.worker_id)
        assert removed is True
        assert sample_worker.worker_id not in scheduler.workers

    def test_remove_nonexistent_worker(self, scheduler: Scheduler):
        """Test removing non-existent worker."""
        removed = scheduler.remove_worker("nonexistent-worker")
        assert removed is False

    def test_schedule_job_no_workers(self, scheduler: Scheduler, sample_job_submission: JobSubmission):
        """Test scheduling with no workers available."""
        job = Job(
            job_id="test-job-1",
            submission=sample_job_submission,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        scheduler.submit_job(job)

        # Try to schedule - should return None (no workers)
        assignment = scheduler.schedule_next()
        assert assignment is None


class TestSchedulerWithWorkers:
    """Scheduler tests with workers."""

    def test_schedule_simple_job(
        self, scheduler: Scheduler, sample_worker: WorkerInfo, sample_job_submission: JobSubmission
    ):
        """Test scheduling a simple job to a worker."""
        scheduler.add_worker(sample_worker)

        job = Job(
            job_id="test-job-1",
            submission=sample_job_submission,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        scheduler.submit_job(job)

        assignment = scheduler.schedule_next()
        assert assignment is not None
        assert assignment[0] == job.job_id
        assert assignment[1] == sample_worker.worker_id

    def test_schedule_respects_resources(self, scheduler: Scheduler, multiple_workers: list[WorkerInfo]):
        """Test that scheduler respects resource requirements."""
        for worker in multiple_workers:
            scheduler.add_worker(worker)

        # Create a GPU-requiring job
        gpu_job = Job(
            job_id="gpu-job-1",
            submission=JobSubmission(
                command="python train.py",
                resources=ResourceSpec(
                    cpu_cores=4,
                    memory_mb=16384,
                    gpu_count=2,
                    gpu_memory_mb=16384,
                ),
                priority=JobPriority.HIGH,
            ),
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        scheduler.submit_job(gpu_job)

        assignment = scheduler.schedule_next()
        assert assignment is not None

        # Should be assigned to GPU worker (returns tuple of 3)
        job_id, worker_id, _ = assignment
        assert job_id == "gpu-job-1"
        assert worker_id == "worker-gpu-1"

    def test_schedule_avoids_offline_workers(
        self, scheduler: Scheduler, multiple_workers: list[WorkerInfo], sample_job_submission: JobSubmission
    ):
        """Test that offline workers are not selected."""
        for worker in multiple_workers:
            scheduler.add_worker(worker)

        job = Job(
            job_id="test-job-1",
            submission=sample_job_submission,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        scheduler.submit_job(job)

        assignment = scheduler.schedule_next()
        assert assignment is not None

        _, worker_id, _ = assignment
        assert worker_id != "worker-offline-1"

    def test_priority_ordering(self, scheduler: Scheduler, sample_worker: WorkerInfo):
        """Test that higher priority jobs are scheduled first."""
        scheduler.add_worker(sample_worker)

        # Submit low priority job first
        low_job = Job(
            job_id="low-priority-job",
            submission=JobSubmission(
                command="echo low",
                resources=ResourceSpec(cpu_cores=1, memory_mb=512),
                priority=JobPriority.LOW,
            ),
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        scheduler.submit_job(low_job)

        # Submit high priority job second
        high_job = Job(
            job_id="high-priority-job",
            submission=JobSubmission(
                command="echo high",
                resources=ResourceSpec(cpu_cores=1, memory_mb=512),
                priority=JobPriority.HIGH,
            ),
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        scheduler.submit_job(high_job)

        # High priority should be scheduled first
        assignment = scheduler.schedule_next()
        assert assignment is not None
        assert assignment[0] == "high-priority-job"


class TestCompositeScorer:
    """Tests for the composite scoring system."""

    def test_scorer_creation(self):
        """Test scorer can be created with default weights."""
        scorer = CompositeScorer()
        assert scorer is not None

    def test_scorer_with_custom_weights(self):
        """Test scorer with custom weights."""
        weights = ScoringWeights(
            resource_fit=0.5,
            load_balance=0.3,
            locality=0.1,
            affinity=0.05,
            freshness=0.03,
            reliability=0.02,
        )
        scorer = CompositeScorer(weights=weights)
        assert scorer.weights == weights

    def test_scoring_profiles(self):
        """Test predefined scoring profiles."""
        for profile_name in ["best_fit", "spread", "locality_first", "reliable"]:
            assert profile_name in SCORING_PROFILES

    def test_score_worker(self, sample_worker: WorkerInfo, sample_job_submission: JobSubmission):
        """Test scoring a single worker."""
        scorer = CompositeScorer()
        job = Job(
            job_id="test-job",
            submission=sample_job_submission,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )

        breakdown = scorer.score(job, sample_worker, context={})

        assert breakdown is not None
        assert breakdown.total_score >= 0
        assert breakdown.total_score <= 1
        assert breakdown.worker_id == sample_worker.worker_id

    def test_rank_workers(self, multiple_workers: list[WorkerInfo], sample_job_submission: JobSubmission):
        """Test ranking multiple workers."""
        scorer = CompositeScorer()
        job = Job(
            job_id="test-job",
            submission=sample_job_submission,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )

        # Filter out offline workers
        available_workers = [w for w in multiple_workers if w.status != WorkerStatus.OFFLINE]

        rankings = scorer.rank_workers(job, available_workers, top_n=3)

        assert len(rankings) <= 3
        # Scores should be in descending order
        scores = [r.total_score for r in rankings]
        assert scores == sorted(scores, reverse=True)
