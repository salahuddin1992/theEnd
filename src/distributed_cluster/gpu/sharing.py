# -*- coding: utf-8 -*-
"""
GPU Sharing Manager for NebulaCompute.

Provides intelligent GPU sharing capabilities including:
- Time-slicing: Multiple jobs share GPU time
- Space-sharing: GPU memory partitioning
- MPS mode: NVIDIA Multi-Process Service
- MIG mode: Multi-Instance GPU (A100/H100)

نظام مشاركة GPU الذكي لـ NebulaCompute.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    import pynvml

    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

logger = logging.getLogger(__name__)


class SharingMode(str, Enum):
    """GPU sharing mode."""

    EXCLUSIVE = "exclusive"  # One job per GPU
    TIME_SLICING = "time_slicing"  # Time-based sharing
    SPACE_SHARING = "space_sharing"  # Memory partitioning
    MPS = "mps"  # NVIDIA Multi-Process Service
    MIG = "mig"  # Multi-Instance GPU


class GPUType(str, Enum):
    """GPU type classification."""

    CONSUMER = "consumer"  # GeForce series
    PROFESSIONAL = "professional"  # Quadro/RTX series
    DATACENTER = "datacenter"  # Tesla/A100/H100
    UNKNOWN = "unknown"


@dataclass
class GPUSlice:
    """
    Represents a slice/partition of a GPU.

    شريحة من GPU يمكن تخصيصها لمهمة.
    """

    slice_id: str
    gpu_index: int
    memory_mb: int
    compute_percentage: float  # 0.0 to 1.0
    mode: SharingMode
    job_id: Optional[str] = None
    allocated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_allocated(self) -> bool:
        """Check if slice is currently allocated."""
        return self.job_id is not None

    @property
    def is_expired(self) -> bool:
        """Check if allocation has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "slice_id": self.slice_id,
            "gpu_index": self.gpu_index,
            "memory_mb": self.memory_mb,
            "compute_percentage": self.compute_percentage,
            "mode": self.mode.value,
            "job_id": self.job_id,
            "allocated_at": self.allocated_at.isoformat() if self.allocated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
        }


@dataclass
class GPUPartition:
    """
    Represents a GPU partition configuration.

    تكوين تقسيم GPU.
    """

    partition_id: str
    gpu_index: int
    total_memory_mb: int
    available_memory_mb: int
    slices: List[GPUSlice] = field(default_factory=list)
    mode: SharingMode = SharingMode.EXCLUSIVE
    max_slices: int = 8
    min_slice_memory_mb: int = 512
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def utilization(self) -> float:
        """Calculate partition utilization."""
        if self.total_memory_mb == 0:
            return 0.0
        used = self.total_memory_mb - self.available_memory_mb
        return used / self.total_memory_mb

    @property
    def allocated_slices(self) -> List[GPUSlice]:
        """Get allocated slices."""
        return [s for s in self.slices if s.is_allocated]

    @property
    def free_slices(self) -> List[GPUSlice]:
        """Get free slices."""
        return [s for s in self.slices if not s.is_allocated]

    def can_allocate(self, memory_mb: int) -> bool:
        """Check if can allocate memory."""
        return (
            self.available_memory_mb >= memory_mb
            and memory_mb >= self.min_slice_memory_mb
            and len(self.allocated_slices) < self.max_slices
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "partition_id": self.partition_id,
            "gpu_index": self.gpu_index,
            "total_memory_mb": self.total_memory_mb,
            "available_memory_mb": self.available_memory_mb,
            "slices": [s.to_dict() for s in self.slices],
            "mode": self.mode.value,
            "max_slices": self.max_slices,
            "utilization": self.utilization,
            "created_at": self.created_at.isoformat(),
        }


class GPUSharingManager:
    """
    Manages GPU sharing across the cluster.

    مدير مشاركة GPU للكلستر.

    Features:
    - Intelligent GPU partitioning
    - Dynamic slice allocation
    - Oversubscription support
    - Fairness policies
    - Memory pressure handling
    """

    def __init__(
        self,
        default_mode: SharingMode = SharingMode.TIME_SLICING,
        max_oversubscription: float = 1.5,
        slice_timeout_seconds: int = 3600,
        enable_mps: bool = True,
        enable_mig: bool = False,
    ):
        """
        Initialize GPU Sharing Manager.

        Args:
            default_mode: Default sharing mode
            max_oversubscription: Maximum memory oversubscription ratio
            slice_timeout_seconds: Default slice allocation timeout
            enable_mps: Enable NVIDIA MPS support
            enable_mig: Enable Multi-Instance GPU support
        """
        self.default_mode = default_mode
        self.max_oversubscription = max_oversubscription
        self.slice_timeout_seconds = slice_timeout_seconds
        self.enable_mps = enable_mps
        self.enable_mig = enable_mig

        # GPU tracking
        self._gpus: Dict[int, Dict[str, Any]] = {}
        self._partitions: Dict[str, GPUPartition] = {}
        self._allocations: Dict[str, GPUSlice] = {}  # job_id -> slice
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "total_allocations": 0,
            "successful_allocations": 0,
            "failed_allocations": 0,
            "evictions": 0,
            "oversubscription_events": 0,
        }

        # Initialize NVML if available
        self._nvml_initialized = False
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self._nvml_initialized = True
                logger.info("NVML initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize NVML: {e}")

    async def initialize(self) -> None:
        """Initialize GPU sharing manager and discover GPUs."""
        async with self._lock:
            await self._discover_gpus()
            await self._create_default_partitions()
            logger.info(
                f"GPU Sharing Manager initialized with {len(self._gpus)} GPUs"
            )

    async def _discover_gpus(self) -> None:
        """Discover available GPUs."""
        self._gpus.clear()

        if not self._nvml_initialized:
            logger.warning("NVML not available, using mock GPU discovery")
            return

        try:
            device_count = pynvml.nvmlDeviceGetCount()

            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8")

                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                uuid_str = pynvml.nvmlDeviceGetUUID(handle)
                if isinstance(uuid_str, bytes):
                    uuid_str = uuid_str.decode("utf-8")

                # Determine GPU type
                gpu_type = self._classify_gpu(name)

                # Check MIG capability
                mig_capable = False
                if self.enable_mig:
                    try:
                        mig_mode = pynvml.nvmlDeviceGetMigMode(handle)
                        mig_capable = mig_mode[0] == pynvml.NVML_DEVICE_MIG_ENABLE
                    except Exception:
                        pass

                # Check MPS compatibility
                mps_compatible = gpu_type in [
                    GPUType.DATACENTER,
                    GPUType.PROFESSIONAL,
                ]

                self._gpus[i] = {
                    "index": i,
                    "name": name,
                    "uuid": uuid_str,
                    "memory_total_mb": memory_info.total // (1024 * 1024),
                    "memory_free_mb": memory_info.free // (1024 * 1024),
                    "gpu_type": gpu_type,
                    "mig_capable": mig_capable,
                    "mps_compatible": mps_compatible,
                    "compute_capability": self._get_compute_capability(handle),
                }

                logger.info(
                    f"Discovered GPU {i}: {name} "
                    f"({self._gpus[i]['memory_total_mb']}MB)"
                )

        except Exception as e:
            logger.error(f"Error discovering GPUs: {e}")
            raise

    def _classify_gpu(self, name: str) -> GPUType:
        """Classify GPU type based on name."""
        name_lower = name.lower()

        if any(x in name_lower for x in ["a100", "h100", "v100", "tesla"]):
            return GPUType.DATACENTER
        elif any(x in name_lower for x in ["quadro", "rtx a", "rtx 4000", "rtx 5000"]):
            return GPUType.PROFESSIONAL
        elif any(x in name_lower for x in ["geforce", "gtx", "rtx 20", "rtx 30", "rtx 40"]):
            return GPUType.CONSUMER
        else:
            return GPUType.UNKNOWN

    def _get_compute_capability(self, handle) -> Tuple[int, int]:
        """Get GPU compute capability."""
        try:
            major = pynvml.nvmlDeviceGetCudaComputeCapability(handle)[0]
            minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)[1]
            return (major, minor)
        except Exception:
            return (0, 0)

    async def _create_default_partitions(self) -> None:
        """Create default partitions for discovered GPUs."""
        for gpu_index, gpu_info in self._gpus.items():
            partition_id = f"partition-gpu{gpu_index}-default"

            partition = GPUPartition(
                partition_id=partition_id,
                gpu_index=gpu_index,
                total_memory_mb=gpu_info["memory_total_mb"],
                available_memory_mb=gpu_info["memory_free_mb"],
                mode=self._select_best_mode(gpu_info),
                max_slices=self._calculate_max_slices(gpu_info),
            )

            self._partitions[partition_id] = partition
            logger.debug(f"Created partition {partition_id} for GPU {gpu_index}")

    def _select_best_mode(self, gpu_info: Dict[str, Any]) -> SharingMode:
        """Select best sharing mode for GPU."""
        if gpu_info.get("mig_capable") and self.enable_mig:
            return SharingMode.MIG
        elif gpu_info.get("mps_compatible") and self.enable_mps:
            return SharingMode.MPS
        elif gpu_info.get("gpu_type") == GPUType.DATACENTER:
            return SharingMode.TIME_SLICING
        else:
            return self.default_mode

    def _calculate_max_slices(self, gpu_info: Dict[str, Any]) -> int:
        """Calculate maximum slices for GPU."""
        memory_mb = gpu_info["memory_total_mb"]
        min_slice = 512  # Minimum 512MB per slice

        if gpu_info.get("gpu_type") == GPUType.DATACENTER:
            # Datacenter GPUs can handle more slices
            return min(16, memory_mb // min_slice)
        elif gpu_info.get("gpu_type") == GPUType.PROFESSIONAL:
            return min(8, memory_mb // min_slice)
        else:
            # Consumer GPUs - fewer slices
            return min(4, memory_mb // min_slice)

    async def allocate_slice(
        self,
        job_id: str,
        memory_mb: int,
        compute_percentage: float = 0.25,
        gpu_index: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[GPUSlice]:
        """
        Allocate a GPU slice for a job.

        تخصيص شريحة GPU لمهمة.

        Args:
            job_id: Job identifier
            memory_mb: Required memory in MB
            compute_percentage: Required compute (0.0-1.0)
            gpu_index: Preferred GPU index (optional)
            timeout_seconds: Allocation timeout
            priority: Job priority for scheduling
            metadata: Additional metadata

        Returns:
            Allocated GPUSlice or None if allocation failed
        """
        async with self._lock:
            self._stats["total_allocations"] += 1

            # Check if job already has allocation
            if job_id in self._allocations:
                logger.warning(f"Job {job_id} already has GPU allocation")
                return self._allocations[job_id]

            # Find suitable partition
            partition = await self._find_best_partition(
                memory_mb, compute_percentage, gpu_index
            )

            if partition is None:
                # Try with oversubscription
                partition = await self._find_partition_with_oversubscription(
                    memory_mb, compute_percentage, gpu_index
                )

            if partition is None:
                self._stats["failed_allocations"] += 1
                logger.warning(
                    f"No GPU partition available for job {job_id} "
                    f"(requested {memory_mb}MB)"
                )
                return None

            # Create slice
            timeout = timeout_seconds or self.slice_timeout_seconds
            now = datetime.utcnow()

            gpu_slice = GPUSlice(
                slice_id=str(uuid.uuid4()),
                gpu_index=partition.gpu_index,
                memory_mb=memory_mb,
                compute_percentage=compute_percentage,
                mode=partition.mode,
                job_id=job_id,
                allocated_at=now,
                expires_at=now + timedelta(seconds=timeout),
                metadata=metadata or {},
            )

            # Update partition
            partition.slices.append(gpu_slice)
            partition.available_memory_mb -= memory_mb

            # Track allocation
            self._allocations[job_id] = gpu_slice
            self._stats["successful_allocations"] += 1

            logger.info(
                f"Allocated GPU slice {gpu_slice.slice_id} for job {job_id} "
                f"on GPU {partition.gpu_index} ({memory_mb}MB)"
            )

            return gpu_slice

    async def _find_best_partition(
        self,
        memory_mb: int,
        compute_percentage: float,
        preferred_gpu: Optional[int] = None,
    ) -> Optional[GPUPartition]:
        """Find best partition for allocation."""
        candidates: List[Tuple[float, GPUPartition]] = []

        for partition in self._partitions.values():
            if not partition.can_allocate(memory_mb):
                continue

            if preferred_gpu is not None and partition.gpu_index != preferred_gpu:
                continue

            # Score based on available resources and fragmentation
            score = self._score_partition(partition, memory_mb, compute_percentage)
            candidates.append((score, partition))

        if not candidates:
            return None

        # Sort by score (higher is better)
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _score_partition(
        self,
        partition: GPUPartition,
        memory_mb: int,
        compute_percentage: float,
    ) -> float:
        """Score partition for allocation suitability."""
        score = 0.0

        # Prefer partitions with more available memory
        memory_score = partition.available_memory_mb / partition.total_memory_mb
        score += memory_score * 0.4

        # Prefer partitions with fewer active slices (less contention)
        slice_score = 1.0 - (len(partition.allocated_slices) / partition.max_slices)
        score += slice_score * 0.3

        # Prefer best-fit allocation (minimize fragmentation)
        fit_score = 1.0 - abs(
            partition.available_memory_mb - memory_mb
        ) / partition.total_memory_mb
        score += fit_score * 0.3

        return score

    async def _find_partition_with_oversubscription(
        self,
        memory_mb: int,
        compute_percentage: float,
        preferred_gpu: Optional[int] = None,
    ) -> Optional[GPUPartition]:
        """Find partition allowing oversubscription."""
        for partition in self._partitions.values():
            if preferred_gpu is not None and partition.gpu_index != preferred_gpu:
                continue

            # Calculate current usage including oversubscription
            total_allocated = sum(s.memory_mb for s in partition.allocated_slices)
            max_allowed = partition.total_memory_mb * self.max_oversubscription

            if total_allocated + memory_mb <= max_allowed:
                self._stats["oversubscription_events"] += 1
                logger.info(
                    f"Using oversubscription on partition {partition.partition_id}"
                )
                return partition

        return None

    async def release_slice(self, job_id: str) -> bool:
        """
        Release a GPU slice.

        تحرير شريحة GPU.

        Args:
            job_id: Job identifier

        Returns:
            True if released successfully
        """
        async with self._lock:
            if job_id not in self._allocations:
                logger.warning(f"No GPU allocation found for job {job_id}")
                return False

            gpu_slice = self._allocations.pop(job_id)

            # Find and update partition
            for partition in self._partitions.values():
                if gpu_slice in partition.slices:
                    partition.slices.remove(gpu_slice)
                    partition.available_memory_mb += gpu_slice.memory_mb
                    break

            logger.info(f"Released GPU slice {gpu_slice.slice_id} for job {job_id}")
            return True

    async def extend_allocation(
        self,
        job_id: str,
        additional_seconds: int,
    ) -> bool:
        """Extend GPU allocation timeout."""
        async with self._lock:
            if job_id not in self._allocations:
                return False

            gpu_slice = self._allocations[job_id]
            if gpu_slice.expires_at:
                gpu_slice.expires_at += timedelta(seconds=additional_seconds)
                logger.debug(
                    f"Extended allocation for job {job_id} by {additional_seconds}s"
                )
            return True

    async def cleanup_expired(self) -> List[str]:
        """
        Clean up expired allocations.

        تنظيف التخصيصات المنتهية.

        Returns:
            List of released job IDs
        """
        released = []
        async with self._lock:
            expired_jobs = [
                job_id
                for job_id, allocation in self._allocations.items()
                if allocation.is_expired
            ]

            for job_id in expired_jobs:
                await self.release_slice(job_id)
                released.append(job_id)
                self._stats["evictions"] += 1

        if released:
            logger.info(f"Cleaned up {len(released)} expired GPU allocations")

        return released

    async def get_allocation(self, job_id: str) -> Optional[GPUSlice]:
        """Get allocation for a job."""
        return self._allocations.get(job_id)

    async def get_gpu_status(self, gpu_index: int) -> Optional[Dict[str, Any]]:
        """Get GPU status and allocations."""
        if gpu_index not in self._gpus:
            return None

        gpu_info = self._gpus[gpu_index].copy()

        # Find partitions for this GPU
        gpu_partitions = [
            p for p in self._partitions.values() if p.gpu_index == gpu_index
        ]

        gpu_info["partitions"] = [p.to_dict() for p in gpu_partitions]
        gpu_info["total_slices"] = sum(len(p.slices) for p in gpu_partitions)
        gpu_info["allocated_slices"] = sum(
            len(p.allocated_slices) for p in gpu_partitions
        )

        # Get current memory usage from NVML
        if self._nvml_initialized:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpu_info["memory_used_mb"] = memory_info.used // (1024 * 1024)
                gpu_info["memory_free_mb"] = memory_info.free // (1024 * 1024)
                gpu_info["utilization"] = pynvml.nvmlDeviceGetUtilizationRates(
                    handle
                ).gpu
            except Exception as e:
                logger.warning(f"Failed to get GPU {gpu_index} status: {e}")

        return gpu_info

    async def get_all_gpus_status(self) -> List[Dict[str, Any]]:
        """Get status of all GPUs."""
        statuses = []
        for gpu_index in self._gpus:
            status = await self.get_gpu_status(gpu_index)
            if status:
                statuses.append(status)
        return statuses

    async def get_statistics(self) -> Dict[str, Any]:
        """Get GPU sharing statistics."""
        return {
            **self._stats,
            "gpu_count": len(self._gpus),
            "partition_count": len(self._partitions),
            "active_allocations": len(self._allocations),
            "mode": self.default_mode.value,
            "max_oversubscription": self.max_oversubscription,
        }

    async def rebalance(self) -> int:
        """
        Rebalance GPU allocations across partitions.

        إعادة توازن تخصيصات GPU.

        Returns:
            Number of reallocated slices
        """
        # TODO: Implement intelligent rebalancing
        # This would move allocations to reduce fragmentation
        logger.info("GPU rebalancing triggered")
        return 0

    async def shutdown(self) -> None:
        """Shutdown GPU sharing manager."""
        async with self._lock:
            # Release all allocations
            for job_id in list(self._allocations.keys()):
                await self.release_slice(job_id)

            self._partitions.clear()
            self._gpus.clear()

            if self._nvml_initialized:
                try:
                    pynvml.nvmlShutdown()
                except Exception:
                    pass

            logger.info("GPU Sharing Manager shutdown complete")
