# -*- coding: utf-8 -*-
"""
GPU Management Module for NebulaCompute.

This module provides intelligent GPU sharing, partitioning,
and resource management capabilities.

Features:
- MPS (Multi-Process Service) for NVIDIA GPUs
- GPU memory partitioning
- Time-slicing for GPU sharing
- GPU health monitoring
- Fractional GPU allocation
"""

from .sharing import (
    GPUSharingManager,
    GPUPartition,
    GPUSlice,
    SharingMode,
)
from .mps import (
    MPSManager,
    MPSConfig,
    MPSSession,
)
from .monitor import (
    GPUMonitor,
    GPUHealthStatus,
    GPUMetrics,
)
from .allocator import (
    GPUAllocator,
    AllocationStrategy,
    GPUAllocation,
)

__all__ = [
    # Sharing
    "GPUSharingManager",
    "GPUPartition",
    "GPUSlice",
    "SharingMode",
    # MPS
    "MPSManager",
    "MPSConfig",
    "MPSSession",
    # Monitor
    "GPUMonitor",
    "GPUHealthStatus",
    "GPUMetrics",
    # Allocator
    "GPUAllocator",
    "AllocationStrategy",
    "GPUAllocation",
]
