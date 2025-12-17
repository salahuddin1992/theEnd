"""
Worker Pools System
===================

نظام تجميع العمال حسب القدرات والتخصصات.

يدعم:
- إنشاء مجموعات عمال مختلفة
- تخصيص الموارد لكل مجموعة
- التوجيه الذكي للوظائف
- Auto-scaling لكل مجموعة
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from enum import Enum
import uuid
import json


class PoolStatus(Enum):
    """Worker pool status."""
    ACTIVE = "active"
    DRAINING = "draining"
    DISABLED = "disabled"
    SCALING = "scaling"


class PoolType(Enum):
    """Worker pool type."""
    GENERAL = "general"
    GPU = "gpu"
    HIGH_MEMORY = "high_memory"
    HIGH_CPU = "high_cpu"
    SPOT = "spot"
    DEDICATED = "dedicated"


@dataclass
class PoolResourceLimits:
    """Resource limits for a pool."""
    max_cpu_cores: float = 0  # 0 = unlimited
    max_memory_mb: int = 0
    max_gpu_count: int = 0
    max_concurrent_jobs: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_cpu_cores": self.max_cpu_cores,
            "max_memory_mb": self.max_memory_mb,
            "max_gpu_count": self.max_gpu_count,
            "max_concurrent_jobs": self.max_concurrent_jobs,
        }


@dataclass
class PoolScalingConfig:
    """Auto-scaling configuration for a pool."""
    enabled: bool = True
    min_workers: int = 0
    max_workers: int = 10
    target_utilization: float = 0.7  # 70%
    scale_up_threshold: float = 0.8
    scale_down_threshold: float = 0.3
    scale_up_cooldown_seconds: int = 60
    scale_down_cooldown_seconds: int = 300
    scale_up_step: int = 1
    scale_down_step: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "min_workers": self.min_workers,
            "max_workers": self.max_workers,
            "target_utilization": self.target_utilization,
            "scale_up_threshold": self.scale_up_threshold,
            "scale_down_threshold": self.scale_down_threshold,
            "scale_up_cooldown_seconds": self.scale_up_cooldown_seconds,
            "scale_down_cooldown_seconds": self.scale_down_cooldown_seconds,
            "scale_up_step": self.scale_up_step,
            "scale_down_step": self.scale_down_step,
        }


@dataclass
class WorkerPool:
    """Worker pool definition."""
    name: str
    pool_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    pool_type: PoolType = PoolType.GENERAL
    status: PoolStatus = PoolStatus.ACTIVE

    # Worker selection criteria
    labels: List[str] = field(default_factory=list)
    required_tags: List[str] = field(default_factory=list)
    node_selector: Dict[str, str] = field(default_factory=dict)

    # Resource limits
    resource_limits: PoolResourceLimits = field(default_factory=PoolResourceLimits)

    # Scaling
    scaling: PoolScalingConfig = field(default_factory=PoolScalingConfig)

    # Scheduling
    priority_offset: int = 0  # Offset to apply to job priorities
    preemption_enabled: bool = False
    queue_binding: Optional[str] = None  # Bind to specific queue

    # Current state
    worker_ids: Set[str] = field(default_factory=set)
    active_jobs: int = 0
    pending_jobs: int = 0

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def worker_count(self) -> int:
        return len(self.worker_ids)

    def can_accept_worker(self, worker_tags: List[str]) -> bool:
        """Check if a worker can join this pool."""
        if self.status not in (PoolStatus.ACTIVE, PoolStatus.SCALING):
            return False

        # Check required tags
        if self.required_tags:
            if not all(tag in worker_tags for tag in self.required_tags):
                return False

        return True

    def can_run_job(self, job_resources: Dict[str, Any]) -> bool:
        """Check if pool can run a job based on resource limits."""
        if self.status != PoolStatus.ACTIVE:
            return False

        limits = self.resource_limits

        # Check resource limits
        if limits.max_cpu_cores > 0:
            if job_resources.get("cpu_cores", 0) > limits.max_cpu_cores:
                return False

        if limits.max_memory_mb > 0:
            if job_resources.get("memory_mb", 0) > limits.max_memory_mb:
                return False

        if limits.max_gpu_count > 0:
            if job_resources.get("gpu_count", 0) > limits.max_gpu_count:
                return False

        if limits.max_concurrent_jobs > 0:
            if self.active_jobs >= limits.max_concurrent_jobs:
                return False

        return True

    def get_utilization(self, total_resources: Dict[str, float]) -> float:
        """Calculate pool utilization."""
        # This is a simplified utilization calculation
        # In practice, would track actual resource usage
        if not total_resources:
            return 0.0

        total_cpu = total_resources.get("cpu_cores", 0)
        if total_cpu <= 0:
            return 0.0

        # Estimate based on active jobs
        # Each job takes some resources
        estimated_used = self.active_jobs * 2.0  # Assume 2 CPU per job average
        return min(1.0, estimated_used / total_cpu)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pool_id": self.pool_id,
            "name": self.name,
            "description": self.description,
            "pool_type": self.pool_type.value,
            "status": self.status.value,
            "labels": self.labels,
            "required_tags": self.required_tags,
            "node_selector": self.node_selector,
            "resource_limits": self.resource_limits.to_dict(),
            "scaling": self.scaling.to_dict(),
            "priority_offset": self.priority_offset,
            "preemption_enabled": self.preemption_enabled,
            "queue_binding": self.queue_binding,
            "worker_count": self.worker_count,
            "worker_ids": list(self.worker_ids),
            "active_jobs": self.active_jobs,
            "pending_jobs": self.pending_jobs,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerPool":
        resource_limits = PoolResourceLimits(
            max_cpu_cores=data.get("resource_limits", {}).get("max_cpu_cores", 0),
            max_memory_mb=data.get("resource_limits", {}).get("max_memory_mb", 0),
            max_gpu_count=data.get("resource_limits", {}).get("max_gpu_count", 0),
            max_concurrent_jobs=data.get("resource_limits", {}).get("max_concurrent_jobs", 0),
        )

        scaling_data = data.get("scaling", {})
        scaling = PoolScalingConfig(
            enabled=scaling_data.get("enabled", True),
            min_workers=scaling_data.get("min_workers", 0),
            max_workers=scaling_data.get("max_workers", 10),
            target_utilization=scaling_data.get("target_utilization", 0.7),
            scale_up_threshold=scaling_data.get("scale_up_threshold", 0.8),
            scale_down_threshold=scaling_data.get("scale_down_threshold", 0.3),
        )

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            name=data["name"],
            pool_id=data.get("pool_id", str(uuid.uuid4())),
            description=data.get("description", ""),
            pool_type=PoolType(data.get("pool_type", "general")),
            status=PoolStatus(data.get("status", "active")),
            labels=data.get("labels", []),
            required_tags=data.get("required_tags", []),
            node_selector=data.get("node_selector", {}),
            resource_limits=resource_limits,
            scaling=scaling,
            priority_offset=data.get("priority_offset", 0),
            preemption_enabled=data.get("preemption_enabled", False),
            queue_binding=data.get("queue_binding"),
            worker_ids=set(data.get("worker_ids", [])),
            active_jobs=data.get("active_jobs", 0),
            pending_jobs=data.get("pending_jobs", 0),
            created_at=created_at or datetime.utcnow(),
        )


class PoolManager:
    """
    Manager for worker pools.
    Handles pool lifecycle, worker assignment, and load balancing.
    """

    def __init__(self, database=None):
        self.database = database
        self._pools: Dict[str, WorkerPool] = {}
        self._worker_pool_map: Dict[str, str] = {}  # worker_id -> pool_name

        # Create default pool
        self._create_default_pool()

    def _create_default_pool(self):
        """Create the default worker pool."""
        default_pool = WorkerPool(
            name="default",
            description="Default worker pool for all workers",
            pool_type=PoolType.GENERAL,
            scaling=PoolScalingConfig(
                enabled=True,
                min_workers=1,
                max_workers=100,
            ),
        )
        self._pools["default"] = default_pool

    async def create_pool(self, pool: WorkerPool) -> WorkerPool:
        """Create a new worker pool."""
        if pool.name in self._pools:
            raise ValueError(f"Pool '{pool.name}' already exists")

        self._pools[pool.name] = pool

        if self.database:
            await self._persist_pool(pool)

        return pool

    async def get_pool(self, name: str) -> Optional[WorkerPool]:
        """Get a pool by name."""
        return self._pools.get(name)

    async def list_pools(self) -> List[WorkerPool]:
        """List all pools."""
        return list(self._pools.values())

    async def update_pool(self, name: str, updates: Dict[str, Any]) -> WorkerPool:
        """Update a pool."""
        pool = self._pools.get(name)
        if not pool:
            raise ValueError(f"Pool '{name}' not found")

        # Apply updates
        if "description" in updates:
            pool.description = updates["description"]
        if "status" in updates:
            pool.status = PoolStatus(updates["status"])
        if "labels" in updates:
            pool.labels = updates["labels"]
        if "required_tags" in updates:
            pool.required_tags = updates["required_tags"]
        if "priority_offset" in updates:
            pool.priority_offset = updates["priority_offset"]
        if "preemption_enabled" in updates:
            pool.preemption_enabled = updates["preemption_enabled"]
        if "queue_binding" in updates:
            pool.queue_binding = updates["queue_binding"]

        if "scaling" in updates:
            scaling_updates = updates["scaling"]
            if "enabled" in scaling_updates:
                pool.scaling.enabled = scaling_updates["enabled"]
            if "min_workers" in scaling_updates:
                pool.scaling.min_workers = scaling_updates["min_workers"]
            if "max_workers" in scaling_updates:
                pool.scaling.max_workers = scaling_updates["max_workers"]
            if "target_utilization" in scaling_updates:
                pool.scaling.target_utilization = scaling_updates["target_utilization"]

        if "resource_limits" in updates:
            limits = updates["resource_limits"]
            if "max_cpu_cores" in limits:
                pool.resource_limits.max_cpu_cores = limits["max_cpu_cores"]
            if "max_memory_mb" in limits:
                pool.resource_limits.max_memory_mb = limits["max_memory_mb"]
            if "max_gpu_count" in limits:
                pool.resource_limits.max_gpu_count = limits["max_gpu_count"]
            if "max_concurrent_jobs" in limits:
                pool.resource_limits.max_concurrent_jobs = limits["max_concurrent_jobs"]

        pool.updated_at = datetime.utcnow()

        if self.database:
            await self._persist_pool(pool)

        return pool

    async def delete_pool(self, name: str, force: bool = False) -> bool:
        """Delete a pool."""
        if name == "default":
            raise ValueError("Cannot delete the default pool")

        pool = self._pools.get(name)
        if not pool:
            return False

        if pool.worker_count > 0 and not force:
            raise ValueError(
                f"Pool '{name}' has {pool.worker_count} workers. "
                "Use force=True to delete anyway."
            )

        # Move workers to default pool
        for worker_id in list(pool.worker_ids):
            await self.reassign_worker(worker_id, "default")

        del self._pools[name]

        if self.database:
            await self.database.execute(
                "DELETE FROM pools WHERE name = ?", (name,)
            )

        return True

    async def assign_worker(
        self,
        worker_id: str,
        worker_tags: List[str],
        preferred_pool: Optional[str] = None
    ) -> str:
        """
        Assign a worker to a pool.
        Returns the assigned pool name.
        """
        # Try preferred pool first
        if preferred_pool:
            pool = self._pools.get(preferred_pool)
            if pool and pool.can_accept_worker(worker_tags):
                pool.worker_ids.add(worker_id)
                self._worker_pool_map[worker_id] = preferred_pool
                return preferred_pool

        # Find best matching pool based on tags
        best_pool = None
        best_match_score = -1

        for pool in self._pools.values():
            if not pool.can_accept_worker(worker_tags):
                continue

            # Calculate match score based on matching labels
            match_score = 0
            for label in pool.labels:
                if label in worker_tags:
                    match_score += 1

            # Prefer more specific pools
            if pool.required_tags:
                match_score += len(pool.required_tags)

            if match_score > best_match_score:
                best_match_score = match_score
                best_pool = pool

        # Fall back to default pool
        if not best_pool:
            best_pool = self._pools["default"]

        best_pool.worker_ids.add(worker_id)
        self._worker_pool_map[worker_id] = best_pool.name

        return best_pool.name

    async def remove_worker(self, worker_id: str):
        """Remove a worker from its pool."""
        pool_name = self._worker_pool_map.get(worker_id)
        if pool_name:
            pool = self._pools.get(pool_name)
            if pool:
                pool.worker_ids.discard(worker_id)
            del self._worker_pool_map[worker_id]

    async def reassign_worker(self, worker_id: str, new_pool: str) -> bool:
        """Reassign a worker to a different pool."""
        if new_pool not in self._pools:
            return False

        # Remove from current pool
        await self.remove_worker(worker_id)

        # Add to new pool
        self._pools[new_pool].worker_ids.add(worker_id)
        self._worker_pool_map[worker_id] = new_pool

        return True

    async def get_worker_pool(self, worker_id: str) -> Optional[str]:
        """Get the pool name for a worker."""
        return self._worker_pool_map.get(worker_id)

    async def select_pool_for_job(
        self,
        job_resources: Dict[str, Any],
        job_pool: Optional[str] = None,
        job_queue: Optional[str] = None
    ) -> Optional[WorkerPool]:
        """
        Select the best pool for a job.

        Selection criteria:
        1. Explicit pool request
        2. Queue binding
        3. Resource requirements
        4. Pool utilization
        """
        # If job specifies a pool, use it if available
        if job_pool:
            pool = self._pools.get(job_pool)
            if pool and pool.can_run_job(job_resources):
                return pool
            return None

        # Check queue bindings
        if job_queue:
            for pool in self._pools.values():
                if pool.queue_binding == job_queue:
                    if pool.can_run_job(job_resources):
                        return pool

        # Find pools that can run this job
        candidates = []
        for pool in self._pools.values():
            if pool.can_run_job(job_resources):
                candidates.append(pool)

        if not candidates:
            return None

        # Sort by utilization (prefer less utilized pools)
        # and number of pending jobs
        def pool_score(p: WorkerPool) -> tuple:
            return (
                p.pending_jobs,  # Fewer pending jobs first
                p.active_jobs / max(1, p.worker_count),  # Lower utilization
            )

        candidates.sort(key=pool_score)

        return candidates[0]

    async def get_pool_workers(self, pool_name: str) -> List[str]:
        """Get worker IDs in a pool."""
        pool = self._pools.get(pool_name)
        if pool:
            return list(pool.worker_ids)
        return []

    def update_pool_job_count(
        self,
        pool_name: str,
        active_delta: int = 0,
        pending_delta: int = 0
    ):
        """Update job counts for a pool."""
        pool = self._pools.get(pool_name)
        if pool:
            pool.active_jobs = max(0, pool.active_jobs + active_delta)
            pool.pending_jobs = max(0, pool.pending_jobs + pending_delta)

    async def drain_pool(self, name: str):
        """Drain a pool (stop accepting new jobs)."""
        pool = self._pools.get(name)
        if pool:
            pool.status = PoolStatus.DRAINING
            pool.updated_at = datetime.utcnow()

            if self.database:
                await self._persist_pool(pool)

    async def activate_pool(self, name: str):
        """Activate a pool."""
        pool = self._pools.get(name)
        if pool:
            pool.status = PoolStatus.ACTIVE
            pool.updated_at = datetime.utcnow()

            if self.database:
                await self._persist_pool(pool)

    async def get_pool_stats(self, name: str) -> Dict[str, Any]:
        """Get statistics for a pool."""
        pool = self._pools.get(name)
        if not pool:
            return {}

        return {
            "name": pool.name,
            "status": pool.status.value,
            "worker_count": pool.worker_count,
            "active_jobs": pool.active_jobs,
            "pending_jobs": pool.pending_jobs,
            "scaling_enabled": pool.scaling.enabled,
            "min_workers": pool.scaling.min_workers,
            "max_workers": pool.scaling.max_workers,
        }

    async def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all pools."""
        stats = {}
        for name in self._pools:
            stats[name] = await self.get_pool_stats(name)
        return stats

    async def _persist_pool(self, pool: WorkerPool):
        """Persist pool to database."""
        if not self.database:
            return

        await self.database.execute(
            """
            INSERT OR REPLACE INTO pools
            (pool_id, name, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                pool.pool_id,
                pool.name,
                json.dumps(pool.to_dict()),
                pool.created_at.isoformat(),
                pool.updated_at.isoformat(),
            )
        )

    async def load_from_database(self):
        """Load pools from database."""
        if not self.database:
            return

        rows = await self.database.fetch_all("SELECT data FROM pools")

        for row in rows:
            data = json.loads(row["data"])
            pool = WorkerPool.from_dict(data)
            self._pools[pool.name] = pool


# Pre-defined pool configurations
PREDEFINED_POOLS = {
    "gpu": WorkerPool(
        name="gpu",
        description="GPU compute pool for ML/AI workloads",
        pool_type=PoolType.GPU,
        required_tags=["gpu"],
        labels=["gpu", "cuda", "ml"],
        resource_limits=PoolResourceLimits(
            max_concurrent_jobs=4,  # Limit concurrent GPU jobs
        ),
        scaling=PoolScalingConfig(
            enabled=True,
            min_workers=0,
            max_workers=8,
            target_utilization=0.8,
            scale_up_cooldown_seconds=120,
            scale_down_cooldown_seconds=600,
        ),
        priority_offset=10,  # Slightly higher priority for GPU jobs
    ),
    "high-memory": WorkerPool(
        name="high-memory",
        description="High memory pool for data processing",
        pool_type=PoolType.HIGH_MEMORY,
        labels=["high-memory", "data-processing"],
        resource_limits=PoolResourceLimits(
            max_memory_mb=65536,  # Allow up to 64GB per job
        ),
        scaling=PoolScalingConfig(
            min_workers=1,
            max_workers=4,
        ),
    ),
    "spot": WorkerPool(
        name="spot",
        description="Spot/preemptible instance pool for cost-effective batch jobs",
        pool_type=PoolType.SPOT,
        labels=["spot", "preemptible", "batch"],
        priority_offset=-20,  # Lower priority
        preemption_enabled=True,
        scaling=PoolScalingConfig(
            min_workers=0,
            max_workers=50,
            target_utilization=0.9,  # Run at higher utilization
            scale_down_cooldown_seconds=120,  # Scale down quickly
        ),
    ),
    "dedicated": WorkerPool(
        name="dedicated",
        description="Dedicated pool for high-priority production jobs",
        pool_type=PoolType.DEDICATED,
        labels=["dedicated", "production"],
        priority_offset=50,  # High priority
        scaling=PoolScalingConfig(
            enabled=False,  # No auto-scaling
            min_workers=2,
            max_workers=2,
        ),
        resource_limits=PoolResourceLimits(
            max_concurrent_jobs=10,
        ),
    ),
}


async def create_predefined_pools(manager: PoolManager):
    """Create predefined pools."""
    for name, pool in PREDEFINED_POOLS.items():
        try:
            await manager.create_pool(pool)
        except ValueError:
            pass  # Already exists
