"""
Locality-Aware Scheduler - المجدول الواعي بالمحلية
===================================================

Scheduler that considers data locality when making scheduling decisions.
مجدول يأخذ محلية البيانات بعين الاعتبار عند اتخاذ قرارات الجدولة.

Features:
- Data-aware worker selection
- Transfer cost estimation
- Locality-first scheduling
- Delay scheduling for better locality
- Co-location of related jobs
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional

from distributed_cluster.models.job import Job
from distributed_cluster.models.worker import WorkerInfo
from distributed_cluster.scheduler.scheduler import (
    Scheduler,
    SchedulingDecision,
    SchedulingPolicy,
)
from distributed_cluster.scheduler.scoring import (
    CompositeScorer,
    ScoreBreakdown,
    ScoringWeights,
)

from .scorer import (
    LocalityLevel,
    LocalityScorer,
    LocalityScoreResult,
    LocalityScoringConfig,
    NetworkTopology,
)
from .tracker import DataLocationTracker

logger = logging.getLogger(__name__)


class LocalitySchedulingPolicy(str, Enum):
    """Locality-aware scheduling policies."""

    LOCALITY_FIRST = "locality_first"  # Prioritize locality over speed
    BALANCED = "balanced"  # Balance locality with other factors
    SPEED_FIRST = "speed_first"  # Prioritize speed, locality as tiebreaker
    DELAY_SCHEDULING = "delay_scheduling"  # Wait for local worker


@dataclass
class LocalitySchedulingConfig:
    """
    Configuration for locality-aware scheduling.
    إعدادات الجدولة الواعية بالمحلية.
    """

    # Scheduling policy
    policy: LocalitySchedulingPolicy = LocalitySchedulingPolicy.BALANCED

    # Locality weights
    locality_weight: float = 0.4  # Weight of locality in scoring
    resource_weight: float = 0.3  # Weight of resource fit
    load_weight: float = 0.2  # Weight of load balancing
    freshness_weight: float = 0.1  # Weight of worker freshness

    # Delay scheduling settings
    enable_delay_scheduling: bool = True
    max_delay_seconds: float = 30.0  # Maximum time to wait for locality
    delay_check_interval: float = 1.0  # How often to check

    # Locality thresholds
    min_locality_score: float = 0.3  # Minimum acceptable locality score
    preferred_locality_score: float = 0.7  # Score to prefer a worker

    # Transfer limits
    max_transfer_mb: float = 1000.0  # Maximum data to transfer
    max_transfer_time_seconds: float = 60.0  # Maximum transfer time

    # Co-location settings
    enable_colocation: bool = True
    colocation_bonus: float = 0.2  # Bonus for co-locating related jobs


@dataclass
class LocalitySchedulingDecision(SchedulingDecision):
    """
    Scheduling decision with locality information.
    قرار جدولة مع معلومات المحلية.
    """

    # Locality info
    locality_score: float = 0.0
    locality_level: LocalityLevel = LocalityLevel.REMOTE

    # Data transfer info
    required_blocks: List[str] = field(default_factory=list)
    local_blocks: int = 0
    transfer_blocks: int = 0
    transfer_size_bytes: int = 0
    estimated_transfer_time: float = 0.0

    # Delay scheduling info
    delay_applied: bool = False
    delay_duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        base_dict = {
            "job_id": self.job.job_id,
            "worker_id": self.worker.worker_id,
            "lease_id": self.lease_id,
            "decision_time": self.decision_time.isoformat(),
            "policy_used": self.policy_used.value,
        }
        return {
            **base_dict,
            "locality_score": self.locality_score,
            "locality_level": self.locality_level.value,
            "required_blocks": self.required_blocks,
            "local_blocks": self.local_blocks,
            "transfer_blocks": self.transfer_blocks,
            "transfer_size_bytes": self.transfer_size_bytes,
            "estimated_transfer_time": self.estimated_transfer_time,
            "delay_applied": self.delay_applied,
            "delay_duration_seconds": self.delay_duration_seconds,
        }


@dataclass
class WorkerLocalityScore:
    """Combined score for a worker including locality."""

    worker: WorkerInfo
    total_score: float
    locality_result: LocalityScoreResult
    resource_score: float = 0.0
    load_score: float = 0.0
    freshness_score: float = 0.0

    # Transfer info
    needs_transfer: bool = False
    transfer_size_bytes: int = 0
    estimated_transfer_time: float = 0.0


class LocalityAwareScheduler:
    """
    Locality-aware job scheduler.
    مجدول المهام الواعي بالمحلية.

    Extends the base scheduler with data locality awareness.
    """

    def __init__(
        self,
        tracker: DataLocationTracker,
        config: Optional[LocalitySchedulingConfig] = None,
        scoring_config: Optional[LocalityScoringConfig] = None,
        topology: Optional[NetworkTopology] = None,
    ):
        self.tracker = tracker
        self.config = config or LocalitySchedulingConfig()
        self.topology = topology or NetworkTopology()

        # Locality scorer
        self.locality_scorer = LocalityScorer(
            config=scoring_config,
            topology=topology,
        )

        # Base scheduler components
        self._scoring_weights = ScoringWeights(
            resource_fit=self.config.resource_weight,
            load_balance=self.config.load_weight,
            locality=self.config.locality_weight,
            freshness=self.config.freshness_weight,
        )
        self._composite_scorer = CompositeScorer(
            weights=self._scoring_weights,
            minimize_slack=True,
        )

        # Internal state
        self._pending_jobs: Dict[str, Job] = {}
        self._delayed_jobs: Dict[str, datetime] = {}  # job_id -> delay_until
        self._job_attempts: Dict[str, int] = {}  # job_id -> scheduling attempts

        # Statistics
        self._stats = {
            "total_decisions": 0,
            "locality_first_decisions": 0,
            "delayed_decisions": 0,
            "transfer_required": 0,
            "perfect_locality": 0,
            "total_transfer_bytes": 0,
        }

    async def schedule(
        self,
        pending_jobs: List[Job],
        workers: List[WorkerInfo],
    ) -> List[LocalitySchedulingDecision]:
        """
        Schedule jobs with locality awareness.
        جدولة المهام مع مراعاة المحلية.
        """
        if not pending_jobs or not workers:
            return []

        # Filter available workers
        available_workers = [w for w in workers if w.can_accept_jobs]
        if not available_workers:
            return []

        # Sort jobs by priority
        sorted_jobs = sorted(
            pending_jobs,
            key=lambda j: (
                -j.submission.priority.value,
                j.created_at,
            ),
        )

        decisions = []

        for job in sorted_jobs:
            decision = await self._schedule_single_job(job, available_workers)
            if decision:
                decisions.append(decision)

                # Update worker resources (simulated allocation)
                decision.worker.allocate_resources(job.submission.resources)
                decision.worker.active_jobs.append(job.job_id)

        return decisions

    async def _schedule_single_job(
        self,
        job: Job,
        workers: List[WorkerInfo],
    ) -> Optional[LocalitySchedulingDecision]:
        """Schedule a single job with locality awareness."""
        # Check for delay scheduling
        if self.config.enable_delay_scheduling:
            if await self._should_delay(job, workers):
                return None

        # Filter candidates
        candidates = self._filter_candidates(job, workers)
        if not candidates:
            return None

        # Score all candidates with locality
        scored = await self._score_workers(job, candidates)
        if not scored:
            return None

        # Select best worker based on policy
        selected = await self._select_worker(job, scored)
        if not selected:
            return None

        # Create decision
        decision = await self._create_decision(job, selected)

        # Update statistics
        self._update_stats(decision)

        return decision

    async def _score_workers(
        self,
        job: Job,
        workers: List[WorkerInfo],
    ) -> List[WorkerLocalityScore]:
        """Score all candidate workers."""
        scored = []

        for worker in workers:
            # Get locality score
            locality_result = await self.locality_scorer.score(
                job,
                worker,
                self.tracker,
            )

            # Get resource/load scores from composite scorer
            base_score = self._composite_scorer.score(job, worker)

            # Combine scores based on policy
            total_score = self._calculate_combined_score(
                locality_result,
                base_score,
            )

            # Check transfer requirements
            needs_transfer = locality_result.transfer_size_bytes > 0
            transfer_ok = True

            if needs_transfer:
                transfer_mb = locality_result.transfer_size_bytes / (1024 * 1024)
                if transfer_mb > self.config.max_transfer_mb:
                    transfer_ok = False
                if locality_result.estimated_transfer_time_seconds > self.config.max_transfer_time_seconds:
                    transfer_ok = False

            if not transfer_ok:
                continue

            scored.append(
                WorkerLocalityScore(
                    worker=worker,
                    total_score=total_score,
                    locality_result=locality_result,
                    resource_score=base_score.resource_fit_score,
                    load_score=base_score.load_balance_score,
                    freshness_score=base_score.freshness_score,
                    needs_transfer=needs_transfer,
                    transfer_size_bytes=locality_result.transfer_size_bytes,
                    estimated_transfer_time=locality_result.estimated_transfer_time_seconds,
                )
            )

        # Sort by score
        scored.sort(key=lambda s: s.total_score, reverse=True)
        return scored

    def _calculate_combined_score(
        self,
        locality_result: LocalityScoreResult,
        base_score: ScoreBreakdown,
    ) -> float:
        """Calculate combined score based on policy."""
        if self.config.policy == LocalitySchedulingPolicy.LOCALITY_FIRST:
            # Locality dominates
            return (
                locality_result.total_score * 0.7
                + base_score.resource_fit_score * 0.15
                + base_score.load_balance_score * 0.15
            )

        elif self.config.policy == LocalitySchedulingPolicy.SPEED_FIRST:
            # Resources and load dominate
            return (
                base_score.resource_fit_score * 0.4
                + base_score.load_balance_score * 0.4
                + locality_result.total_score * 0.2
            )

        else:  # BALANCED
            return (
                locality_result.total_score * self.config.locality_weight
                + base_score.resource_fit_score * self.config.resource_weight
                + base_score.load_balance_score * self.config.load_weight
                + base_score.freshness_score * self.config.freshness_weight
            )

    async def _select_worker(
        self,
        job: Job,
        scored: List[WorkerLocalityScore],
    ) -> Optional[WorkerLocalityScore]:
        """Select the best worker from scored candidates."""
        if not scored:
            return None

        best = scored[0]

        # Check minimum locality score
        if best.locality_result.total_score < self.config.min_locality_score:
            # Check if we should wait for better locality
            if self.config.enable_delay_scheduling:
                attempts = self._job_attempts.get(job.job_id, 0)
                if attempts < 3:  # Max 3 attempts before forcing
                    self._job_attempts[job.job_id] = attempts + 1
                    return None

        return best

    async def _should_delay(
        self,
        job: Job,
        workers: List[WorkerInfo],
    ) -> bool:
        """Check if job should be delayed for better locality."""
        if not self.config.enable_delay_scheduling:
            return False

        # Check if already delayed too long
        if job.job_id in self._delayed_jobs:
            delay_until = self._delayed_jobs[job.job_id]
            if datetime.now(timezone.utc) >= delay_until:
                del self._delayed_jobs[job.job_id]
                return False

            return True

        # Score workers
        candidates = self._filter_candidates(job, workers)
        if not candidates:
            return False

        scored = await self._score_workers(job, candidates)
        if not scored:
            return False

        best = scored[0]

        # Delay if best locality is below threshold
        if best.locality_result.total_score < self.config.preferred_locality_score:
            # Check if a better worker might become available
            potential_workers = await self._find_potential_workers(job)

            if potential_workers:
                # Set delay
                delay_until = datetime.now(timezone.utc) + timedelta(seconds=self.config.max_delay_seconds)
                self._delayed_jobs[job.job_id] = delay_until
                logger.info(
                    f"Delaying job {job.job_id} for better locality "
                    f"(current best: {best.locality_result.total_score:.2f})"
                )
                return True

        return False

    async def _find_potential_workers(self, job: Job) -> List[str]:
        """Find workers that might provide better locality."""
        # Get required blocks
        required_blocks = []
        if "required_blocks" in job.submission.labels:
            required_blocks = [b.strip() for b in job.submission.labels["required_blocks"].split(",") if b.strip()]

        if not required_blocks:
            return []

        # Find workers with this data
        best_workers = await self.tracker.find_best_workers(
            required_blocks,
            top_n=3,
        )

        return [w for w, _ in best_workers]

    def _filter_candidates(
        self,
        job: Job,
        workers: List[WorkerInfo],
    ) -> List[WorkerInfo]:
        """Filter workers based on job requirements."""
        candidates = []

        for worker in workers:
            # Check resources
            if not job.submission.resources.fits_in(worker.available_resources):
                continue

            # Check required tags
            if job.submission.required_tags:
                if not all(tag in worker.tags for tag in job.submission.required_tags):
                    continue

            # Check preferred worker
            if job.submission.preferred_worker:
                if job.submission.preferred_worker == worker.worker_id:
                    return [worker]  # Preferred worker takes precedence

            # Check Docker requirement
            if job.submission.docker_image and not worker.docker_available:
                continue

            candidates.append(worker)

        return candidates

    async def _create_decision(
        self,
        job: Job,
        selected: WorkerLocalityScore,
    ) -> LocalitySchedulingDecision:
        """Create a scheduling decision."""
        lease_id = f"lease-{uuid.uuid4().hex[:12]}"

        # Check if delay was applied
        delay_applied = job.job_id in self._delayed_jobs
        delay_duration = 0.0

        if delay_applied:
            del self._delayed_jobs[job.job_id]

        # Get required blocks
        required_blocks = []
        if "required_blocks" in job.submission.labels:
            required_blocks = [b.strip() for b in job.submission.labels["required_blocks"].split(",") if b.strip()]

        return LocalitySchedulingDecision(
            job=job,
            worker=selected.worker,
            lease_id=lease_id,
            decision_time=datetime.now(timezone.utc),
            policy_used=SchedulingPolicy.BEST_FIT,
            locality_score=selected.locality_result.total_score,
            locality_level=selected.locality_result.locality_level,
            required_blocks=required_blocks,
            local_blocks=selected.locality_result.local_blocks,
            transfer_blocks=selected.locality_result.total_blocks_required - selected.locality_result.local_blocks,
            transfer_size_bytes=selected.transfer_size_bytes,
            estimated_transfer_time=selected.estimated_transfer_time,
            delay_applied=delay_applied,
            delay_duration_seconds=delay_duration,
        )

    def _update_stats(self, decision: LocalitySchedulingDecision) -> None:
        """Update scheduling statistics."""
        self._stats["total_decisions"] += 1

        if decision.locality_level == LocalityLevel.NODE_LOCAL:
            self._stats["perfect_locality"] += 1

        if decision.transfer_size_bytes > 0:
            self._stats["transfer_required"] += 1
            self._stats["total_transfer_bytes"] += decision.transfer_size_bytes

        if decision.delay_applied:
            self._stats["delayed_decisions"] += 1

        # Clear attempt counter
        if decision.job.job_id in self._job_attempts:
            del self._job_attempts[decision.job.job_id]

    async def get_stats(self) -> Dict:
        """Get scheduling statistics."""
        total = max(self._stats["total_decisions"], 1)

        return {
            **self._stats,
            "locality_rate": self._stats["perfect_locality"] / total,
            "transfer_rate": self._stats["transfer_required"] / total,
            "delay_rate": self._stats["delayed_decisions"] / total,
            "avg_transfer_bytes": (self._stats["total_transfer_bytes"] / max(self._stats["transfer_required"], 1)),
        }


class LocalitySchedulerLoop:
    """
    Continuous scheduling loop with locality awareness.
    حلقة جدولة مستمرة مع مراعاة المحلية.
    """

    def __init__(
        self,
        scheduler: LocalityAwareScheduler,
        get_pending_jobs: Callable[[], List[Job]],
        get_workers: Callable[[], List[WorkerInfo]],
        on_decision: Callable[[LocalitySchedulingDecision], None],
        on_no_resources: Optional[Callable[[Job], None]] = None,
        interval_seconds: float = 1.0,
    ):
        self.scheduler = scheduler
        self.get_pending_jobs = get_pending_jobs
        self.get_workers = get_workers
        self.on_decision = on_decision
        self.on_no_resources = on_no_resources or (lambda j: None)
        self.interval_seconds = interval_seconds

        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the scheduling loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("LocalitySchedulerLoop started")

    async def stop(self) -> None:
        """Stop the scheduling loop."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("LocalitySchedulerLoop stopped")

    async def _loop(self) -> None:
        """Main scheduling loop."""
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Scheduling loop error: {e}")

            await asyncio.sleep(self.interval_seconds)

    async def _tick(self) -> None:
        """Single scheduling tick."""
        pending_jobs = self.get_pending_jobs()
        if not pending_jobs:
            return

        workers = self.get_workers()
        if not workers:
            for job in pending_jobs[:5]:
                self.on_no_resources(job)
            return

        # Schedule
        decisions = await self.scheduler.schedule(pending_jobs, workers)

        # Apply decisions
        for decision in decisions:
            try:
                self.on_decision(decision)
            except Exception as e:
                logger.error(f"Failed to apply decision: {e}")

        # Report unscheduled jobs
        scheduled_ids = {d.job.job_id for d in decisions}
        unscheduled = [j for j in pending_jobs if j.job_id not in scheduled_ids]

        for job in unscheduled[:3]:
            self.on_no_resources(job)


# ==================== Integration Helpers ====================


def create_locality_scheduler(
    tracker: DataLocationTracker,
    policy: LocalitySchedulingPolicy = LocalitySchedulingPolicy.BALANCED,
    topology: Optional[NetworkTopology] = None,
) -> LocalityAwareScheduler:
    """
    Create a locality-aware scheduler with sensible defaults.
    إنشاء مجدول واعي بالمحلية بإعدادات افتراضية معقولة.
    """
    config = LocalitySchedulingConfig(policy=policy)

    return LocalityAwareScheduler(
        tracker=tracker,
        config=config,
        topology=topology,
    )


def locality_scheduling_plugin(
    tracker: DataLocationTracker,
    base_scheduler: Scheduler,
) -> Callable:
    """
    Create a plugin to enhance existing scheduler with locality.
    إنشاء إضافة لتعزيز المجدول الحالي بالمحلية.

    Returns a decorator that adds locality scoring to scheduling decisions.
    """
    locality_scheduler = create_locality_scheduler(tracker)

    async def enhanced_schedule(
        pending_jobs: List[Job],
        workers: List[WorkerInfo],
    ) -> List[SchedulingDecision]:
        # Use locality-aware scheduler
        decisions = await locality_scheduler.schedule(pending_jobs, workers)
        return decisions

    return enhanced_schedule
