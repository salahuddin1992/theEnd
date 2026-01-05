# -*- coding: utf-8 -*-
"""
GPU Allocator for NebulaCompute.

Provides intelligent GPU allocation strategies for optimal
resource utilization across the cluster.

نظام تخصيص GPU الذكي لـ NebulaCompute.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .monitor import GPUHealthStatus, GPUMetrics, GPUMonitor
from .sharing import GPUSharingManager, GPUSlice, SharingMode

logger = logging.getLogger(__name__)


class AllocationStrategy(str, Enum):
    """GPU allocation strategy."""

    BEST_FIT = "best_fit"  # Minimize fragmentation
    WORST_FIT = "worst_fit"  # Maximize remaining space
    FIRST_FIT = "first_fit"  # First available GPU
    ROUND_ROBIN = "round_robin"  # Distribute evenly
    LEAST_LOADED = "least_loaded"  # GPU with lowest utilization
    POWER_AWARE = "power_aware"  # Minimize power consumption
    TEMPERATURE_AWARE = "temperature_aware"  # Prefer cooler GPUs
    LOCALITY_AWARE = "locality_aware"  # Consider data locality
    AFFINITY_BASED = "affinity_based"  # Respect affinity rules


@dataclass
class GPURequirement:
    """
    GPU resource requirements for a job.

    متطلبات موارد GPU لمهمة.
    """

    memory_mb: int
    compute_percentage: float = 1.0  # 0.0 to 1.0
    gpu_count: int = 1
    min_compute_capability: Tuple[int, int] = (0, 0)
    preferred_gpu_types: List[str] = field(default_factory=list)
    excluded_gpus: Set[int] = field(default_factory=set)
    preferred_gpus: Set[int] = field(default_factory=set)
    require_ecc: bool = False
    require_mig: bool = False
    max_temperature: int = 85
    sharing_mode: Optional[SharingMode] = None
    timeout_seconds: int = 3600

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "memory_mb": self.memory_mb,
            "compute_percentage": self.compute_percentage,
            "gpu_count": self.gpu_count,
            "min_compute_capability": self.min_compute_capability,
            "preferred_gpu_types": self.preferred_gpu_types,
            "excluded_gpus": list(self.excluded_gpus),
            "preferred_gpus": list(self.preferred_gpus),
            "require_ecc": self.require_ecc,
            "require_mig": self.require_mig,
            "max_temperature": self.max_temperature,
            "sharing_mode": self.sharing_mode.value if self.sharing_mode else None,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class GPUAllocation:
    """
    Represents a GPU allocation.

    تمثيل تخصيص GPU.
    """

    allocation_id: str
    job_id: str
    slices: List[GPUSlice]
    strategy_used: AllocationStrategy
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def gpu_indices(self) -> List[int]:
        """Get allocated GPU indices."""
        return list(set(s.gpu_index for s in self.slices))

    @property
    def total_memory_mb(self) -> int:
        """Get total allocated memory."""
        return sum(s.memory_mb for s in self.slices)

    @property
    def total_compute(self) -> float:
        """Get total compute percentage."""
        return sum(s.compute_percentage for s in self.slices)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "allocation_id": self.allocation_id,
            "job_id": self.job_id,
            "slices": [s.to_dict() for s in self.slices],
            "gpu_indices": self.gpu_indices,
            "total_memory_mb": self.total_memory_mb,
            "total_compute": self.total_compute,
            "strategy_used": self.strategy_used.value,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


class GPUAllocator:
    """
    Intelligent GPU allocator for the cluster.

    مخصص GPU الذكي للكلستر.

    Features:
    - Multiple allocation strategies
    - Multi-GPU allocation support
    - Constraint-based allocation
    - Preemption support
    - Fairness policies
    - Reservation system
    """

    def __init__(
        self,
        sharing_manager: GPUSharingManager,
        monitor: GPUMonitor,
        default_strategy: AllocationStrategy = AllocationStrategy.BEST_FIT,
        enable_preemption: bool = False,
        max_pending_requests: int = 1000,
    ):
        """
        Initialize GPU Allocator.

        Args:
            sharing_manager: GPU sharing manager instance
            monitor: GPU monitor instance
            default_strategy: Default allocation strategy
            enable_preemption: Enable job preemption
            max_pending_requests: Maximum pending allocation requests
        """
        self.sharing_manager = sharing_manager
        self.monitor = monitor
        self.default_strategy = default_strategy
        self.enable_preemption = enable_preemption
        self.max_pending_requests = max_pending_requests

        # State
        self._allocations: Dict[str, GPUAllocation] = {}
        self._pending_requests: List[Dict[str, Any]] = []
        self._reservations: Dict[str, Dict[str, Any]] = {}
        self._round_robin_index = 0
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "total_requests": 0,
            "successful_allocations": 0,
            "failed_allocations": 0,
            "preemptions": 0,
            "strategy_usage": {s.value: 0 for s in AllocationStrategy},
        }

    async def allocate(
        self,
        job_id: str,
        requirements: GPURequirement,
        strategy: Optional[AllocationStrategy] = None,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[GPUAllocation]:
        """
        Allocate GPUs for a job.

        تخصيص GPUs لمهمة.

        Args:
            job_id: Unique job identifier
            requirements: GPU requirements
            strategy: Allocation strategy (uses default if None)
            priority: Job priority (higher = more important)
            metadata: Additional metadata

        Returns:
            GPUAllocation if successful, None otherwise
        """
        async with self._lock:
            self._stats["total_requests"] += 1
            strategy = strategy or self.default_strategy

            logger.info(
                f"Allocating GPU for job {job_id}: "
                f"{requirements.gpu_count} GPU(s), "
                f"{requirements.memory_mb}MB, "
                f"strategy={strategy.value}"
            )

            # Check if job already has allocation
            if job_id in self._allocations:
                logger.warning(f"Job {job_id} already has GPU allocation")
                return self._allocations[job_id]

            # Find suitable GPUs based on strategy
            selected_gpus = await self._select_gpus(requirements, strategy)

            if not selected_gpus:
                logger.warning(f"No suitable GPUs found for job {job_id}")

                if self.enable_preemption:
                    # Try preemption
                    selected_gpus = await self._try_preemption(requirements, priority)

                if not selected_gpus:
                    self._stats["failed_allocations"] += 1
                    # Add to pending queue
                    if len(self._pending_requests) < self.max_pending_requests:
                        self._pending_requests.append(
                            {
                                "job_id": job_id,
                                "requirements": requirements,
                                "strategy": strategy,
                                "priority": priority,
                                "metadata": metadata,
                                "timestamp": datetime.now(timezone.utc),
                            }
                        )
                    return None

            # Allocate slices on selected GPUs
            slices = []
            for gpu_index in selected_gpus:
                slice_result = await self.sharing_manager.allocate_slice(
                    job_id=f"{job_id}-gpu{gpu_index}",
                    memory_mb=requirements.memory_mb // len(selected_gpus),
                    compute_percentage=requirements.compute_percentage,
                    gpu_index=gpu_index,
                    timeout_seconds=requirements.timeout_seconds,
                    metadata={"parent_job_id": job_id},
                )
                if slice_result:
                    slices.append(slice_result)

            if len(slices) < requirements.gpu_count:
                # Rollback partial allocation
                for s in slices:
                    await self.sharing_manager.release_slice(s.job_id)
                self._stats["failed_allocations"] += 1
                logger.error(f"Failed to allocate all GPUs for job {job_id}")
                return None

            # Create allocation record
            import uuid

            allocation = GPUAllocation(
                allocation_id=str(uuid.uuid4()),
                job_id=job_id,
                slices=slices,
                strategy_used=strategy,
                metadata=metadata or {},
            )

            self._allocations[job_id] = allocation
            self._stats["successful_allocations"] += 1
            self._stats["strategy_usage"][strategy.value] += 1

            logger.info(f"Allocated {len(slices)} GPU slice(s) for job {job_id} " f"on GPUs {allocation.gpu_indices}")

            return allocation

    async def _select_gpus(
        self,
        requirements: GPURequirement,
        strategy: AllocationStrategy,
    ) -> List[int]:
        """Select GPUs based on strategy and requirements."""
        # Get all available GPUs
        all_gpus = await self.sharing_manager.get_all_gpus_status()

        if not all_gpus:
            return []

        # Filter based on requirements
        candidates = []
        for gpu in all_gpus:
            gpu_index = gpu["index"]

            # Check exclusions
            if gpu_index in requirements.excluded_gpus:
                continue

            # Check temperature
            metrics = await self.monitor.get_metrics(gpu_index)
            if metrics and metrics.temperature_gpu > requirements.max_temperature:
                continue

            # Check health
            health = await self.monitor.get_health_status(gpu_index)
            if health == GPUHealthStatus.CRITICAL:
                continue

            # Check memory availability
            available_memory = gpu.get("memory_free_mb", 0)
            if available_memory < requirements.memory_mb:
                continue

            # Check compute capability
            compute_cap = gpu.get("compute_capability", (0, 0))
            if compute_cap < requirements.min_compute_capability:
                continue

            candidates.append((gpu_index, gpu, metrics))

        if not candidates:
            return []

        # Apply strategy
        if strategy == AllocationStrategy.BEST_FIT:
            selected = self._best_fit(candidates, requirements)
        elif strategy == AllocationStrategy.WORST_FIT:
            selected = self._worst_fit(candidates, requirements)
        elif strategy == AllocationStrategy.FIRST_FIT:
            selected = self._first_fit(candidates, requirements)
        elif strategy == AllocationStrategy.ROUND_ROBIN:
            selected = self._round_robin(candidates, requirements)
        elif strategy == AllocationStrategy.LEAST_LOADED:
            selected = self._least_loaded(candidates, requirements)
        elif strategy == AllocationStrategy.POWER_AWARE:
            selected = self._power_aware(candidates, requirements)
        elif strategy == AllocationStrategy.TEMPERATURE_AWARE:
            selected = self._temperature_aware(candidates, requirements)
        elif strategy == AllocationStrategy.AFFINITY_BASED:
            selected = self._affinity_based(candidates, requirements)
        else:
            selected = self._first_fit(candidates, requirements)

        return selected

    def _best_fit(
        self,
        candidates: List[Tuple[int, Dict, Optional[GPUMetrics]]],
        requirements: GPURequirement,
    ) -> List[int]:
        """Best-fit: Minimize remaining space after allocation."""
        # Sort by remaining memory after allocation (ascending)
        sorted_candidates = sorted(
            candidates,
            key=lambda x: x[1].get("memory_free_mb", 0) - requirements.memory_mb,
        )

        # Prefer preferred GPUs
        if requirements.preferred_gpus:
            preferred = [c for c in sorted_candidates if c[0] in requirements.preferred_gpus]
            if len(preferred) >= requirements.gpu_count:
                sorted_candidates = preferred

        return [c[0] for c in sorted_candidates[: requirements.gpu_count]]

    def _worst_fit(
        self,
        candidates: List[Tuple[int, Dict, Optional[GPUMetrics]]],
        requirements: GPURequirement,
    ) -> List[int]:
        """Worst-fit: Maximize remaining space after allocation."""
        sorted_candidates = sorted(
            candidates,
            key=lambda x: x[1].get("memory_free_mb", 0),
            reverse=True,
        )
        return [c[0] for c in sorted_candidates[: requirements.gpu_count]]

    def _first_fit(
        self,
        candidates: List[Tuple[int, Dict, Optional[GPUMetrics]]],
        requirements: GPURequirement,
    ) -> List[int]:
        """First-fit: First available GPU."""
        return [c[0] for c in candidates[: requirements.gpu_count]]

    def _round_robin(
        self,
        candidates: List[Tuple[int, Dict, Optional[GPUMetrics]]],
        requirements: GPURequirement,
    ) -> List[int]:
        """Round-robin: Distribute evenly across GPUs."""
        result = []
        n = len(candidates)

        for _ in range(requirements.gpu_count):
            idx = self._round_robin_index % n
            result.append(candidates[idx][0])
            self._round_robin_index += 1

        return result

    def _least_loaded(
        self,
        candidates: List[Tuple[int, Dict, Optional[GPUMetrics]]],
        requirements: GPURequirement,
    ) -> List[int]:
        """Least-loaded: GPU with lowest utilization."""

        def get_load(c):
            _, gpu, metrics = c
            if metrics:
                return metrics.gpu_utilization
            return gpu.get("utilization", 0)

        sorted_candidates = sorted(candidates, key=get_load)
        return [c[0] for c in sorted_candidates[: requirements.gpu_count]]

    def _power_aware(
        self,
        candidates: List[Tuple[int, Dict, Optional[GPUMetrics]]],
        requirements: GPURequirement,
    ) -> List[int]:
        """Power-aware: Minimize power consumption."""

        def get_power(c):
            _, gpu, metrics = c
            if metrics:
                return metrics.power_draw_watts
            return float("inf")

        sorted_candidates = sorted(candidates, key=get_power)
        return [c[0] for c in sorted_candidates[: requirements.gpu_count]]

    def _temperature_aware(
        self,
        candidates: List[Tuple[int, Dict, Optional[GPUMetrics]]],
        requirements: GPURequirement,
    ) -> List[int]:
        """Temperature-aware: Prefer cooler GPUs."""

        def get_temp(c):
            _, gpu, metrics = c
            if metrics:
                return metrics.temperature_gpu
            return 50  # Default temp

        sorted_candidates = sorted(candidates, key=get_temp)
        return [c[0] for c in sorted_candidates[: requirements.gpu_count]]

    def _affinity_based(
        self,
        candidates: List[Tuple[int, Dict, Optional[GPUMetrics]]],
        requirements: GPURequirement,
    ) -> List[int]:
        """Affinity-based: Respect GPU affinity rules."""
        # Prefer preferred GPUs first
        preferred = [c for c in candidates if c[0] in requirements.preferred_gpus]

        if len(preferred) >= requirements.gpu_count:
            return [c[0] for c in preferred[: requirements.gpu_count]]

        # Fill remaining with other candidates
        remaining = [c for c in candidates if c[0] not in requirements.preferred_gpus]
        result = [c[0] for c in preferred]
        result.extend([c[0] for c in remaining[: requirements.gpu_count - len(result)]])

        return result

    async def _try_preemption(
        self,
        requirements: GPURequirement,
        priority: int,
    ) -> List[int]:
        """Try to preempt lower priority jobs."""
        # Find allocations with lower priority
        preemption_candidates = []

        for job_id, allocation in self._allocations.items():
            job_priority = allocation.metadata.get("priority", 0)
            if job_priority < priority:
                preemption_candidates.append((job_id, allocation))

        # Sort by priority (lowest first)
        preemption_candidates.sort(key=lambda x: x[1].metadata.get("priority", 0))

        freed_gpus = []
        for job_id, allocation in preemption_candidates:
            if len(freed_gpus) >= requirements.gpu_count:
                break

            # Preempt this job
            await self.release(job_id)
            freed_gpus.extend(allocation.gpu_indices)
            self._stats["preemptions"] += 1
            logger.info(f"Preempted job {job_id} to free GPU resources")

        return freed_gpus[: requirements.gpu_count]

    async def release(self, job_id: str) -> bool:
        """
        Release GPU allocation for a job.

        تحرير تخصيص GPU لمهمة.

        Args:
            job_id: Job identifier

        Returns:
            True if released successfully
        """
        async with self._lock:
            if job_id not in self._allocations:
                logger.warning(f"No allocation found for job {job_id}")
                return False

            allocation = self._allocations.pop(job_id)

            # Release all slices
            for gpu_slice in allocation.slices:
                await self.sharing_manager.release_slice(gpu_slice.job_id)

            logger.info(f"Released GPU allocation for job {job_id} " f"(GPUs: {allocation.gpu_indices})")

            # Process pending requests
            await self._process_pending()

            return True

    async def _process_pending(self) -> None:
        """Process pending allocation requests."""
        if not self._pending_requests:
            return

        # Sort by priority and timestamp
        self._pending_requests.sort(key=lambda x: (-x["priority"], x["timestamp"]))

        # Try to allocate pending requests
        still_pending = []
        for request in self._pending_requests:
            allocation = await self.allocate(
                job_id=request["job_id"],
                requirements=request["requirements"],
                strategy=request["strategy"],
                priority=request["priority"],
                metadata=request["metadata"],
            )

            if allocation is None:
                still_pending.append(request)

        self._pending_requests = still_pending

    async def get_allocation(self, job_id: str) -> Optional[GPUAllocation]:
        """Get allocation for a job."""
        return self._allocations.get(job_id)

    async def list_allocations(self) -> List[GPUAllocation]:
        """List all allocations."""
        return list(self._allocations.values())

    async def create_reservation(
        self,
        reservation_id: str,
        gpu_indices: List[int],
        duration_seconds: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Create a GPU reservation.

        إنشاء حجز GPU.
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            self._reservations[reservation_id] = {
                "gpu_indices": gpu_indices,
                "created_at": now,
                "expires_at": now + timedelta(seconds=duration_seconds),
                "metadata": metadata or {},
            }
            logger.info(f"Created reservation {reservation_id} for GPUs {gpu_indices}")
            return True

    async def cancel_reservation(self, reservation_id: str) -> bool:
        """Cancel a GPU reservation."""
        async with self._lock:
            if reservation_id in self._reservations:
                del self._reservations[reservation_id]
                logger.info(f"Cancelled reservation {reservation_id}")
                return True
            return False

    async def get_statistics(self) -> Dict[str, Any]:
        """Get allocator statistics."""
        return {
            **self._stats,
            "active_allocations": len(self._allocations),
            "pending_requests": len(self._pending_requests),
            "active_reservations": len(self._reservations),
            "default_strategy": self.default_strategy.value,
            "preemption_enabled": self.enable_preemption,
        }

    async def get_gpu_utilization_summary(self) -> Dict[str, Any]:
        """Get GPU utilization summary."""
        all_metrics = await self.monitor.get_all_metrics()

        if not all_metrics:
            return {}

        total_memory = 0
        used_memory = 0
        avg_utilization = 0.0
        avg_temperature = 0.0

        for metrics in all_metrics.values():
            total_memory += metrics.memory_total_mb
            used_memory += metrics.memory_used_mb
            avg_utilization += metrics.gpu_utilization
            avg_temperature += metrics.temperature_gpu

        n = len(all_metrics)
        return {
            "gpu_count": n,
            "total_memory_mb": total_memory,
            "used_memory_mb": used_memory,
            "memory_utilization": (used_memory / total_memory * 100) if total_memory > 0 else 0,
            "average_gpu_utilization": avg_utilization / n if n > 0 else 0,
            "average_temperature": avg_temperature / n if n > 0 else 0,
            "active_allocations": len(self._allocations),
        }

    async def shutdown(self) -> None:
        """Shutdown allocator."""
        async with self._lock:
            # Release all allocations
            for job_id in list(self._allocations.keys()):
                await self.release(job_id)

            self._pending_requests.clear()
            self._reservations.clear()

        logger.info("GPU Allocator shutdown complete")
