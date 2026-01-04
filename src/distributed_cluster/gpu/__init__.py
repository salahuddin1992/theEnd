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

from .allocator import (
    AllocationStrategy,
    GPUAllocation,
    GPUAllocator,
)
from .monitor import (
    GPUHealthStatus,
    GPUMetrics,
    GPUMonitor,
)
from .mps import (
    MPSConfig,
    MPSManager,
    MPSSession,
)
from .sharing import (
    GPUPartition,
    GPUSharingManager,
    GPUSlice,
    SharingMode,
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
