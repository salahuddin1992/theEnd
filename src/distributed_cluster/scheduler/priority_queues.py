"""
Priority Queue System
=====================

نظام قوائم الانتظار بأولويات مختلفة.

يدعم:
- قوائم انتظار متعددة بأولويات مختلفة
- جدولة عادلة مع أوزان
- حدود معدل التنفيذ
- إيقاف واستئناف القوائم
"""

import heapq
import json
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional


class QueueState(Enum):
    """Queue state."""

    ACTIVE = "active"
    PAUSED = "paused"
    DRAINING = "draining"
    DISABLED = "disabled"


class FairnessPolicy(Enum):
    """Fairness policy for scheduling."""

    STRICT_PRIORITY = "strict_priority"  # Higher priority always first
    WEIGHTED_FAIR = "weighted_fair"  # Weighted fair queuing
    ROUND_ROBIN = "round_robin"  # Round-robin across queues
    DEFICIT_ROUND_ROBIN = "deficit_round_robin"  # DRR with credits


@dataclass
class QueueLimits:
    """Rate and resource limits for a queue."""

    max_pending_jobs: int = 0  # 0 = unlimited
    max_concurrent_jobs: int = 0
    max_jobs_per_minute: int = 0
    max_jobs_per_hour: int = 0
    max_cpu_usage: float = 0
    max_memory_mb: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_pending_jobs": self.max_pending_jobs,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "max_jobs_per_minute": self.max_jobs_per_minute,
            "max_jobs_per_hour": self.max_jobs_per_hour,
            "max_cpu_usage": self.max_cpu_usage,
            "max_memory_mb": self.max_memory_mb,
        }


@dataclass
class QueueStats:
    """Queue statistics."""

    total_submitted: int = 0
    total_completed: int = 0
    total_failed: int = 0
    jobs_last_minute: int = 0
    jobs_last_hour: int = 0
    avg_wait_time_seconds: float = 0
    avg_execution_time_seconds: float = 0
    wait_times: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    execution_times: Deque[float] = field(default_factory=lambda: deque(maxlen=100))

    def record_wait_time(self, seconds: float):
        self.wait_times.append(seconds)
        if self.wait_times:
            self.avg_wait_time_seconds = sum(self.wait_times) / len(self.wait_times)

    def record_execution_time(self, seconds: float):
        self.execution_times.append(seconds)
        if self.execution_times:
            self.avg_execution_time_seconds = sum(self.execution_times) / len(self.execution_times)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_submitted": self.total_submitted,
            "total_completed": self.total_completed,
            "total_failed": self.total_failed,
            "jobs_last_minute": self.jobs_last_minute,
            "jobs_last_hour": self.jobs_last_hour,
            "avg_wait_time_seconds": self.avg_wait_time_seconds,
            "avg_execution_time_seconds": self.avg_execution_time_seconds,
        }


@dataclass
class PriorityQueue:
    """Priority queue definition."""

    name: str
    queue_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    state: QueueState = QueueState.ACTIVE

    # Priority and scheduling
    priority: int = 50  # Base priority (0-200)
    weight: int = 1  # Scheduling weight for fair queuing

    # Limits
    limits: QueueLimits = field(default_factory=QueueLimits)

    # Pool binding
    target_pool: Optional[str] = None  # Send jobs to specific pool

    # Preemption
    preemption_enabled: bool = False
    can_preempt_queues: List[str] = field(default_factory=list)

    # Current state
    pending_jobs: List[str] = field(default_factory=list)  # job_ids
    running_jobs: List[str] = field(default_factory=list)

    # Deficit counter for DRR
    deficit: int = 0

    # Rate limiting state
    _job_timestamps: Deque[datetime] = field(default_factory=lambda: deque(maxlen=1000))

    # Statistics
    stats: QueueStats = field(default_factory=QueueStats)

    # Metadata
    labels: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def pending_count(self) -> int:
        return len(self.pending_jobs)

    @property
    def running_count(self) -> int:
        return len(self.running_jobs)

    def can_accept_job(self) -> tuple[bool, str]:
        """Check if queue can accept a new job."""
        if self.state != QueueState.ACTIVE:
            return False, f"Queue is {self.state.value}"

        # Check pending limit
        if self.limits.max_pending_jobs > 0:
            if self.pending_count >= self.limits.max_pending_jobs:
                return False, "Queue pending limit reached"

        # Check rate limits
        now = datetime.now(timezone.utc)

        # Jobs per minute
        if self.limits.max_jobs_per_minute > 0:
            minute_ago = now - timedelta(minutes=1)
            jobs_last_minute = sum(1 for t in self._job_timestamps if t > minute_ago)
            if jobs_last_minute >= self.limits.max_jobs_per_minute:
                return False, "Queue rate limit (per minute) reached"

        # Jobs per hour
        if self.limits.max_jobs_per_hour > 0:
            hour_ago = now - timedelta(hours=1)
            jobs_last_hour = sum(1 for t in self._job_timestamps if t > hour_ago)
            if jobs_last_hour >= self.limits.max_jobs_per_hour:
                return False, "Queue rate limit (per hour) reached"

        return True, ""

    def can_run_job(self) -> tuple[bool, str]:
        """Check if queue can start running a job."""
        if self.state not in (QueueState.ACTIVE, QueueState.DRAINING):
            return False, f"Queue is {self.state.value}"

        if self.limits.max_concurrent_jobs > 0:
            if self.running_count >= self.limits.max_concurrent_jobs:
                return False, "Queue concurrent job limit reached"

        return True, ""

    def enqueue_job(self, job_id: str, job_priority: int = 50) -> bool:
        """Add a job to the queue."""
        can_accept, reason = self.can_accept_job()
        if not can_accept:
            return False

        # Add to pending list (will be sorted by scheduler)
        self.pending_jobs.append(job_id)
        self._job_timestamps.append(datetime.now(timezone.utc))
        self.stats.total_submitted += 1

        return True

    def dequeue_job(self) -> Optional[str]:
        """Get the next job from the queue."""
        can_run, _ = self.can_run_job()
        if not can_run:
            return None

        if not self.pending_jobs:
            return None

        job_id = self.pending_jobs.pop(0)
        self.running_jobs.append(job_id)

        return job_id

    def complete_job(self, job_id: str, success: bool = True):
        """Mark a job as completed."""
        if job_id in self.running_jobs:
            self.running_jobs.remove(job_id)

            if success:
                self.stats.total_completed += 1
            else:
                self.stats.total_failed += 1

    def cancel_job(self, job_id: str):
        """Cancel a job in this queue."""
        if job_id in self.pending_jobs:
            self.pending_jobs.remove(job_id)
        if job_id in self.running_jobs:
            self.running_jobs.remove(job_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "priority": self.priority,
            "weight": self.weight,
            "limits": self.limits.to_dict(),
            "target_pool": self.target_pool,
            "preemption_enabled": self.preemption_enabled,
            "can_preempt_queues": self.can_preempt_queues,
            "pending_jobs": len(self.pending_jobs),
            "running_jobs": len(self.running_jobs),
            "stats": self.stats.to_dict(),
            "labels": self.labels,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PriorityQueue":
        limits = QueueLimits(
            max_pending_jobs=data.get("limits", {}).get("max_pending_jobs", 0),
            max_concurrent_jobs=data.get("limits", {}).get("max_concurrent_jobs", 0),
            max_jobs_per_minute=data.get("limits", {}).get("max_jobs_per_minute", 0),
            max_jobs_per_hour=data.get("limits", {}).get("max_jobs_per_hour", 0),
            max_cpu_usage=data.get("limits", {}).get("max_cpu_usage", 0),
            max_memory_mb=data.get("limits", {}).get("max_memory_mb", 0),
        )

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            name=data["name"],
            queue_id=data.get("queue_id", str(uuid.uuid4())),
            description=data.get("description", ""),
            state=QueueState(data.get("state", "active")),
            priority=data.get("priority", 50),
            weight=data.get("weight", 1),
            limits=limits,
            target_pool=data.get("target_pool"),
            preemption_enabled=data.get("preemption_enabled", False),
            can_preempt_queues=data.get("can_preempt_queues", []),
            labels=data.get("labels", {}),
            created_at=created_at or datetime.now(timezone.utc),
        )


@dataclass
class QueuedJob:
    """Job entry in queue system."""

    job_id: str
    queue: str
    priority: int
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    resources: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other):
        # Higher priority first, then earlier submission
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.submitted_at < other.submitted_at


class QueueManager:
    """
    Manager for priority queues.
    Handles multi-queue scheduling with various fairness policies.
    """

    def __init__(self, database=None, fairness_policy: FairnessPolicy = FairnessPolicy.WEIGHTED_FAIR):
        self.database = database
        self.fairness_policy = fairness_policy
        self._queues: Dict[str, PriorityQueue] = {}
        self._job_queue_map: Dict[str, str] = {}  # job_id -> queue_name

        # For weighted fair scheduling
        self._last_served_queue: Optional[str] = None
        self._round_robin_index: int = 0

        # Priority heap for strict priority
        self._priority_heap: List[QueuedJob] = []

        # Create default queue
        self._create_default_queue()

    def _create_default_queue(self):
        """Create the default queue."""
        default_queue = PriorityQueue(
            name="default",
            description="Default job queue",
            priority=50,
            weight=1,
        )
        self._queues["default"] = default_queue

    async def create_queue(self, queue: PriorityQueue) -> PriorityQueue:
        """Create a new queue."""
        if queue.name in self._queues:
            raise ValueError(f"Queue '{queue.name}' already exists")

        self._queues[queue.name] = queue

        if self.database:
            await self._persist_queue(queue)

        return queue

    async def get_queue(self, name: str) -> Optional[PriorityQueue]:
        """Get a queue by name."""
        return self._queues.get(name)

    async def list_queues(self) -> List[PriorityQueue]:
        """List all queues."""
        return list(self._queues.values())

    async def update_queue(self, name: str, updates: Dict[str, Any]) -> PriorityQueue:
        """Update a queue."""
        queue = self._queues.get(name)
        if not queue:
            raise ValueError(f"Queue '{name}' not found")

        if "description" in updates:
            queue.description = updates["description"]
        if "state" in updates:
            queue.state = QueueState(updates["state"])
        if "priority" in updates:
            queue.priority = updates["priority"]
        if "weight" in updates:
            queue.weight = updates["weight"]
        if "target_pool" in updates:
            queue.target_pool = updates["target_pool"]
        if "preemption_enabled" in updates:
            queue.preemption_enabled = updates["preemption_enabled"]

        if "limits" in updates:
            limits = updates["limits"]
            if "max_pending_jobs" in limits:
                queue.limits.max_pending_jobs = limits["max_pending_jobs"]
            if "max_concurrent_jobs" in limits:
                queue.limits.max_concurrent_jobs = limits["max_concurrent_jobs"]
            if "max_jobs_per_minute" in limits:
                queue.limits.max_jobs_per_minute = limits["max_jobs_per_minute"]
            if "max_jobs_per_hour" in limits:
                queue.limits.max_jobs_per_hour = limits["max_jobs_per_hour"]

        queue.updated_at = datetime.now(timezone.utc)

        if self.database:
            await self._persist_queue(queue)

        return queue

    async def delete_queue(self, name: str) -> bool:
        """Delete a queue."""
        if name == "default":
            raise ValueError("Cannot delete the default queue")

        queue = self._queues.get(name)
        if not queue:
            return False

        # Move pending jobs to default queue
        for job_id in list(queue.pending_jobs):
            self._job_queue_map[job_id] = "default"
            self._queues["default"].pending_jobs.append(job_id)

        del self._queues[name]

        if self.database:
            await self.database.execute("DELETE FROM queues WHERE name = ?", (name,))

        return True

    async def submit_job(
        self, job_id: str, queue_name: str = "default", priority: int = 50, resources: Dict[str, Any] = None
    ) -> tuple[bool, str]:
        """
        Submit a job to a queue.

        Returns (success, message).
        """
        queue = self._queues.get(queue_name)
        if not queue:
            # Fall back to default queue
            queue = self._queues["default"]
            queue_name = "default"

        can_accept, reason = queue.can_accept_job()
        if not can_accept:
            return False, reason

        # Add to queue
        queue.enqueue_job(job_id, priority)
        self._job_queue_map[job_id] = queue_name

        # Add to priority heap for strict priority scheduling
        queued_job = QueuedJob(
            job_id=job_id,
            queue=queue_name,
            priority=priority + queue.priority,  # Combined priority
            resources=resources or {},
        )
        heapq.heappush(self._priority_heap, queued_job)

        return True, f"Job submitted to queue '{queue_name}'"

    async def get_next_job(self) -> Optional[str]:
        """
        Get the next job to run based on fairness policy.

        Returns job_id or None if no jobs available.
        """
        if self.fairness_policy == FairnessPolicy.STRICT_PRIORITY:
            return await self._get_next_strict_priority()
        elif self.fairness_policy == FairnessPolicy.WEIGHTED_FAIR:
            return await self._get_next_weighted_fair()
        elif self.fairness_policy == FairnessPolicy.ROUND_ROBIN:
            return await self._get_next_round_robin()
        elif self.fairness_policy == FairnessPolicy.DEFICIT_ROUND_ROBIN:
            return await self._get_next_drr()

        return None

    async def _get_next_strict_priority(self) -> Optional[str]:
        """Get next job using strict priority ordering."""
        while self._priority_heap:
            queued_job = heapq.heappop(self._priority_heap)
            job_id = queued_job.job_id
            queue_name = queued_job.queue

            queue = self._queues.get(queue_name)
            if not queue:
                continue

            # Check if job is still pending
            if job_id not in queue.pending_jobs:
                continue

            # Check if queue can run job
            can_run, _ = queue.can_run_job()
            if not can_run:
                # Put back in heap
                heapq.heappush(self._priority_heap, queued_job)
                continue

            # Dequeue the job
            queue.pending_jobs.remove(job_id)
            queue.running_jobs.append(job_id)

            return job_id

        return None

    async def _get_next_weighted_fair(self) -> Optional[str]:
        """Get next job using weighted fair queuing."""
        # Sort queues by (pending_jobs / weight), descending
        active_queues = [q for q in self._queues.values() if q.pending_count > 0 and q.state == QueueState.ACTIVE]

        if not active_queues:
            return None

        # Calculate fair share scores
        total_weight = sum(q.weight for q in active_queues)

        def fair_score(q: PriorityQueue) -> float:
            target_share = q.weight / total_weight
            actual_share = q.running_count / max(1, sum(x.running_count for x in active_queues))
            # Prioritize queues below their fair share
            return target_share - actual_share

        # Sort by fair score (higher = more deserving)
        active_queues.sort(key=fair_score, reverse=True)

        for queue in active_queues:
            can_run, _ = queue.can_run_job()
            if not can_run:
                continue

            job_id = queue.dequeue_job()
            if job_id:
                return job_id

        return None

    async def _get_next_round_robin(self) -> Optional[str]:
        """Get next job using round-robin across queues."""
        queue_names = list(self._queues.keys())
        if not queue_names:
            return None

        # Start from last served position
        start_idx = self._round_robin_index

        for i in range(len(queue_names)):
            idx = (start_idx + i) % len(queue_names)
            queue_name = queue_names[idx]
            queue = self._queues[queue_name]

            if queue.state != QueueState.ACTIVE:
                continue

            can_run, _ = queue.can_run_job()
            if not can_run:
                continue

            job_id = queue.dequeue_job()
            if job_id:
                self._round_robin_index = (idx + 1) % len(queue_names)
                return job_id

        return None

    async def _get_next_drr(self) -> Optional[str]:
        """Get next job using Deficit Round Robin."""
        queue_names = list(self._queues.keys())
        if not queue_names:
            return None

        # Process each queue
        for queue_name in queue_names:
            queue = self._queues[queue_name]

            if queue.state != QueueState.ACTIVE or queue.pending_count == 0:
                continue

            # Add quantum (weight) to deficit
            queue.deficit += queue.weight

            # Try to dequeue as many jobs as deficit allows
            while queue.deficit > 0 and queue.pending_count > 0:
                can_run, _ = queue.can_run_job()
                if not can_run:
                    break

                job_id = queue.dequeue_job()
                if job_id:
                    queue.deficit -= 1  # Cost per job
                    return job_id
                else:
                    break

            # Reset deficit if queue is empty
            if queue.pending_count == 0:
                queue.deficit = 0

        return None

    async def complete_job(self, job_id: str, success: bool = True, wait_time: float = 0, execution_time: float = 0):
        """Mark a job as completed."""
        queue_name = self._job_queue_map.get(job_id)
        if queue_name:
            queue = self._queues.get(queue_name)
            if queue:
                queue.complete_job(job_id, success)
                queue.stats.record_wait_time(wait_time)
                queue.stats.record_execution_time(execution_time)

            del self._job_queue_map[job_id]

    async def cancel_job(self, job_id: str):
        """Cancel a job."""
        queue_name = self._job_queue_map.get(job_id)
        if queue_name:
            queue = self._queues.get(queue_name)
            if queue:
                queue.cancel_job(job_id)
            del self._job_queue_map[job_id]

    async def pause_queue(self, name: str):
        """Pause a queue."""
        queue = self._queues.get(name)
        if queue:
            queue.state = QueueState.PAUSED
            queue.updated_at = datetime.now(timezone.utc)

            if self.database:
                await self._persist_queue(queue)

    async def resume_queue(self, name: str):
        """Resume a paused queue."""
        queue = self._queues.get(name)
        if queue:
            queue.state = QueueState.ACTIVE
            queue.updated_at = datetime.now(timezone.utc)

            if self.database:
                await self._persist_queue(queue)

    async def drain_queue(self, name: str):
        """Drain a queue (finish running jobs, don't accept new ones)."""
        queue = self._queues.get(name)
        if queue:
            queue.state = QueueState.DRAINING
            queue.updated_at = datetime.now(timezone.utc)

            if self.database:
                await self._persist_queue(queue)

    async def get_queue_stats(self, name: str) -> Dict[str, Any]:
        """Get statistics for a queue."""
        queue = self._queues.get(name)
        if not queue:
            return {}

        return {
            "name": queue.name,
            "state": queue.state.value,
            "priority": queue.priority,
            "weight": queue.weight,
            "pending_jobs": queue.pending_count,
            "running_jobs": queue.running_count,
            "stats": queue.stats.to_dict(),
        }

    async def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all queues."""
        stats = {}
        for name in self._queues:
            stats[name] = await self.get_queue_stats(name)
        return stats

    def get_job_position(self, job_id: str) -> Optional[int]:
        """Get a job's position in its queue."""
        queue_name = self._job_queue_map.get(job_id)
        if not queue_name:
            return None

        queue = self._queues.get(queue_name)
        if not queue:
            return None

        try:
            return queue.pending_jobs.index(job_id) + 1
        except ValueError:
            return None

    async def _persist_queue(self, queue: PriorityQueue):
        """Persist queue to database."""
        if not self.database:
            return

        await self.database.execute(
            """
            INSERT OR REPLACE INTO queues
            (queue_id, name, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                queue.queue_id,
                queue.name,
                json.dumps(queue.to_dict()),
                queue.created_at.isoformat(),
                queue.updated_at.isoformat(),
            ),
        )

    async def load_from_database(self):
        """Load queues from database."""
        if not self.database:
            return

        rows = await self.database.fetch_all("SELECT data FROM queues")

        for row in rows:
            data = json.loads(row["data"])
            queue = PriorityQueue.from_dict(data)
            self._queues[queue.name] = queue


# Pre-defined queue configurations
PREDEFINED_QUEUES = {
    "urgent": PriorityQueue(
        name="urgent",
        description="High-priority urgent jobs",
        priority=150,
        weight=5,
        limits=QueueLimits(
            max_concurrent_jobs=10,
        ),
        preemption_enabled=True,
        can_preempt_queues=["batch", "low"],
    ),
    "interactive": PriorityQueue(
        name="interactive",
        description="Interactive user-facing jobs",
        priority=100,
        weight=3,
        limits=QueueLimits(
            max_pending_jobs=100,
            max_concurrent_jobs=20,
        ),
    ),
    "batch": PriorityQueue(
        name="batch",
        description="Batch processing jobs",
        priority=30,
        weight=2,
        limits=QueueLimits(
            max_concurrent_jobs=50,
        ),
    ),
    "low": PriorityQueue(
        name="low",
        description="Low-priority background jobs",
        priority=10,
        weight=1,
        limits=QueueLimits(
            max_jobs_per_hour=100,
        ),
    ),
    "gpu": PriorityQueue(
        name="gpu",
        description="GPU compute jobs",
        priority=80,
        weight=2,
        target_pool="gpu",
        limits=QueueLimits(
            max_concurrent_jobs=8,
        ),
    ),
}


async def create_predefined_queues(manager: QueueManager):
    """Create predefined queues."""
    for name, queue in PREDEFINED_QUEUES.items():
        try:
            await manager.create_queue(queue)
        except ValueError:
            pass  # Already exists
