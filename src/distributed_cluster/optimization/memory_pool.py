"""
Memory Pool Manager - Efficient memory management for caching.

This module provides sophisticated memory pool management for cache
operations including slab allocation, memory pressure handling,
and efficient memory reuse.
"""

import asyncio
import time
import threading
import logging
import gc
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from enum import Enum
from collections import deque, defaultdict
import psutil

logger = logging.getLogger(__name__)


class MemoryPressureLevel(Enum):
    """Levels of memory pressure."""
    LOW = "low"           # < 50% usage
    MODERATE = "moderate" # 50-70% usage
    HIGH = "high"         # 70-85% usage
    CRITICAL = "critical" # > 85% usage


class AllocationStrategy(Enum):
    """Memory allocation strategies."""
    BEST_FIT = "best_fit"     # Find smallest fitting block
    FIRST_FIT = "first_fit"   # Use first available block
    SLAB = "slab"             # Slab allocation
    POOL = "pool"             # Pool allocation


@dataclass
class MemoryBlock:
    """Represents a memory block in the pool."""
    block_id: int
    size: int
    data: Optional[bytes] = None
    allocated: bool = False
    allocated_at: Optional[float] = None
    last_used: Optional[float] = None
    key: Optional[str] = None


@dataclass
class SlabClass:
    """Represents a slab class for fixed-size allocations."""
    size: int
    blocks: List[MemoryBlock] = field(default_factory=list)
    free_blocks: List[int] = field(default_factory=list)  # Block IDs
    allocated_count: int = 0
    total_count: int = 0


@dataclass
class MemoryStats:
    """Memory usage statistics."""
    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    allocated_blocks: int = 0
    free_blocks: int = 0
    fragmentation_ratio: float = 0.0
    pressure_level: MemoryPressureLevel = MemoryPressureLevel.LOW
    gc_collections: Dict[int, int] = field(default_factory=dict)


@dataclass
class PoolConfig:
    """Memory pool configuration."""
    max_memory_mb: int = 1024
    slab_sizes: List[int] = field(default_factory=lambda: [64, 256, 1024, 4096, 16384, 65536, 262144])
    initial_slabs_per_class: int = 10
    growth_factor: float = 1.5
    shrink_threshold: float = 0.3
    high_pressure_threshold: float = 0.85
    critical_pressure_threshold: float = 0.95
    enable_gc_on_pressure: bool = True
    defrag_threshold: float = 0.3


class SlabAllocator:
    """
    Slab allocator for efficient fixed-size memory allocation.
    Inspired by the Linux kernel slab allocator.
    """

    def __init__(self, slab_sizes: List[int], initial_slabs: int = 10):
        self.slab_sizes = sorted(slab_sizes)
        self.slabs: Dict[int, SlabClass] = {}
        self._block_counter = 0
        self._lock = threading.Lock()

        # Initialize slab classes
        for size in self.slab_sizes:
            self.slabs[size] = SlabClass(size=size)
            self._grow_slab(size, initial_slabs)

    def _find_slab_class(self, size: int) -> Optional[int]:
        """Find the smallest slab class that can fit the size."""
        for slab_size in self.slab_sizes:
            if slab_size >= size:
                return slab_size
        return None

    def _grow_slab(self, slab_size: int, count: int):
        """Add more blocks to a slab class."""
        slab = self.slabs[slab_size]
        for _ in range(count):
            block_id = self._block_counter
            self._block_counter += 1
            block = MemoryBlock(
                block_id=block_id,
                size=slab_size,
                allocated=False,
            )
            slab.blocks.append(block)
            slab.free_blocks.append(block_id)
            slab.total_count += 1

    def allocate(self, size: int) -> Optional[MemoryBlock]:
        """Allocate a block of at least the specified size."""
        with self._lock:
            slab_size = self._find_slab_class(size)
            if slab_size is None:
                logger.warning(f"No slab class for size {size}")
                return None

            slab = self.slabs[slab_size]

            # Grow slab if needed
            if not slab.free_blocks:
                grow_count = max(1, int(slab.total_count * 0.5))
                self._grow_slab(slab_size, grow_count)

            if not slab.free_blocks:
                return None

            # Get a free block
            block_id = slab.free_blocks.pop()
            block = next(b for b in slab.blocks if b.block_id == block_id)
            block.allocated = True
            block.allocated_at = time.time()
            block.last_used = time.time()
            slab.allocated_count += 1

            return block

    def free(self, block: MemoryBlock):
        """Free an allocated block."""
        with self._lock:
            slab = self.slabs.get(block.size)
            if slab is None:
                return

            block.allocated = False
            block.data = None
            block.key = None
            block.allocated_at = None
            slab.free_blocks.append(block.block_id)
            slab.allocated_count -= 1

    def shrink_slabs(self, target_ratio: float = 0.5):
        """Shrink slab classes that have many free blocks."""
        with self._lock:
            for slab_size, slab in self.slabs.items():
                if slab.total_count == 0:
                    continue

                free_ratio = len(slab.free_blocks) / slab.total_count
                if free_ratio > target_ratio:
                    # Remove some free blocks
                    remove_count = int(len(slab.free_blocks) * 0.3)
                    for _ in range(remove_count):
                        if slab.free_blocks:
                            block_id = slab.free_blocks.pop()
                            slab.blocks = [b for b in slab.blocks if b.block_id != block_id]
                            slab.total_count -= 1

    def get_stats(self) -> Dict[str, Any]:
        """Get slab allocator statistics."""
        with self._lock:
            stats = {}
            for slab_size, slab in self.slabs.items():
                stats[slab_size] = {
                    'total_blocks': slab.total_count,
                    'allocated_blocks': slab.allocated_count,
                    'free_blocks': len(slab.free_blocks),
                    'utilization': slab.allocated_count / slab.total_count if slab.total_count > 0 else 0,
                    'memory_bytes': slab.total_count * slab_size,
                }
            return stats


class MemoryPressureHandler:
    """Handles memory pressure events and triggers appropriate responses."""

    def __init__(
        self,
        high_threshold: float = 0.85,
        critical_threshold: float = 0.95
    ):
        self.high_threshold = high_threshold
        self.critical_threshold = critical_threshold
        self.callbacks: List[Callable[[MemoryPressureLevel], None]] = []
        self.current_level = MemoryPressureLevel.LOW
        self._lock = threading.Lock()

    def register_callback(self, callback: Callable[[MemoryPressureLevel], None]):
        """Register a callback for pressure events."""
        self.callbacks.append(callback)

    def check_pressure(self) -> MemoryPressureLevel:
        """Check current memory pressure level."""
        try:
            memory = psutil.virtual_memory()
            usage_ratio = memory.percent / 100.0
        except Exception:
            usage_ratio = 0.5

        if usage_ratio >= self.critical_threshold:
            level = MemoryPressureLevel.CRITICAL
        elif usage_ratio >= self.high_threshold:
            level = MemoryPressureLevel.HIGH
        elif usage_ratio >= 0.7:
            level = MemoryPressureLevel.MODERATE
        else:
            level = MemoryPressureLevel.LOW

        # Notify if level changed
        with self._lock:
            if level != self.current_level:
                old_level = self.current_level
                self.current_level = level
                self._notify_level_change(old_level, level)

        return level

    def _notify_level_change(self, old_level: MemoryPressureLevel, new_level: MemoryPressureLevel):
        """Notify callbacks of pressure level change."""
        for callback in self.callbacks:
            try:
                callback(new_level)
            except Exception as e:
                logger.error(f"Pressure callback error: {e}")

    def force_gc(self):
        """Force garbage collection."""
        gc.collect()


class MemoryPoolManager:
    """
    Comprehensive memory pool manager for efficient cache memory
    management with pressure handling and automatic optimization.
    """

    def __init__(self, config: Optional[PoolConfig] = None):
        self.config = config or PoolConfig()

        # Slab allocator for efficient allocation
        self.slab_allocator = SlabAllocator(
            slab_sizes=self.config.slab_sizes,
            initial_slabs=self.config.initial_slabs_per_class
        )

        # Memory pressure handling
        self.pressure_handler = MemoryPressureHandler(
            high_threshold=self.config.high_pressure_threshold,
            critical_threshold=self.config.critical_pressure_threshold
        )
        self.pressure_handler.register_callback(self._on_pressure_change)

        # Key to block mapping
        self.key_blocks: Dict[str, MemoryBlock] = {}

        # Statistics
        self.total_allocations = 0
        self.total_frees = 0
        self.allocation_failures = 0

        # Memory limits
        self.max_memory_bytes = self.config.max_memory_mb * 1024 * 1024
        self.current_usage_bytes = 0

        # Eviction callbacks
        self.eviction_callbacks: List[Callable[[str], None]] = []

        # Control
        self._lock = threading.RLock()
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    def allocate(self, key: str, size: int) -> Optional[MemoryBlock]:
        """Allocate memory for a cache entry."""
        with self._lock:
            # Check if we need to evict first
            while self.current_usage_bytes + size > self.max_memory_bytes:
                if not self._evict_one():
                    self.allocation_failures += 1
                    return None

            # Allocate from slab
            block = self.slab_allocator.allocate(size)
            if block is None:
                self.allocation_failures += 1
                return None

            # Track allocation
            block.key = key
            self.key_blocks[key] = block
            self.current_usage_bytes += block.size
            self.total_allocations += 1

            return block

    def free(self, key: str) -> bool:
        """Free memory for a cache entry."""
        with self._lock:
            block = self.key_blocks.pop(key, None)
            if block is None:
                return False

            self.current_usage_bytes -= block.size
            self.slab_allocator.free(block)
            self.total_frees += 1
            return True

    def get(self, key: str) -> Optional[MemoryBlock]:
        """Get the memory block for a key."""
        with self._lock:
            block = self.key_blocks.get(key)
            if block:
                block.last_used = time.time()
            return block

    def update(self, key: str, data: bytes) -> bool:
        """Update the data in a memory block."""
        with self._lock:
            block = self.key_blocks.get(key)
            if block is None:
                return False

            if len(data) > block.size:
                # Need to reallocate
                self.free(key)
                new_block = self.allocate(key, len(data))
                if new_block is None:
                    return False
                new_block.data = data
            else:
                block.data = data
                block.last_used = time.time()

            return True

    def contains(self, key: str) -> bool:
        """Check if a key is in the memory pool."""
        return key in self.key_blocks

    def _evict_one(self) -> bool:
        """Evict one entry (LRU)."""
        if not self.key_blocks:
            return False

        # Find LRU entry
        lru_key = None
        lru_time = float('inf')

        for key, block in self.key_blocks.items():
            if block.last_used and block.last_used < lru_time:
                lru_time = block.last_used
                lru_key = key

        if lru_key is None:
            # Pick any key
            lru_key = next(iter(self.key_blocks))

        # Notify callbacks
        for callback in self.eviction_callbacks:
            try:
                callback(lru_key)
            except Exception as e:
                logger.error(f"Eviction callback error: {e}")

        return self.free(lru_key)

    def evict_until(self, target_usage_bytes: int) -> int:
        """Evict entries until usage is below target."""
        evicted = 0
        with self._lock:
            while self.current_usage_bytes > target_usage_bytes:
                if self._evict_one():
                    evicted += 1
                else:
                    break
        return evicted

    def _on_pressure_change(self, level: MemoryPressureLevel):
        """Handle memory pressure level changes."""
        if level == MemoryPressureLevel.CRITICAL:
            # Aggressive eviction
            target = int(self.max_memory_bytes * 0.5)
            evicted = self.evict_until(target)
            logger.warning(f"Critical memory pressure: evicted {evicted} entries")

            if self.config.enable_gc_on_pressure:
                self.pressure_handler.force_gc()

        elif level == MemoryPressureLevel.HIGH:
            # Moderate eviction
            target = int(self.max_memory_bytes * 0.7)
            evicted = self.evict_until(target)
            logger.info(f"High memory pressure: evicted {evicted} entries")

            # Shrink slabs
            self.slab_allocator.shrink_slabs()

    def register_eviction_callback(self, callback: Callable[[str], None]):
        """Register a callback for eviction notifications."""
        self.eviction_callbacks.append(callback)

    async def start_monitoring(self, interval_seconds: float = 5.0):
        """Start background monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(interval_seconds)
        )
        logger.info("Memory pool monitoring started")

    async def stop_monitoring(self):
        """Stop background monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Memory pool monitoring stopped")

    async def _monitor_loop(self, interval_seconds: float):
        """Background monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(interval_seconds)

                # Check memory pressure
                self.pressure_handler.check_pressure()

                # Check fragmentation
                if self._check_fragmentation() > self.config.defrag_threshold:
                    self._defragment()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

    def _check_fragmentation(self) -> float:
        """Calculate fragmentation ratio."""
        stats = self.slab_allocator.get_stats()
        total_memory = 0
        used_memory = 0

        for size, slab_stats in stats.items():
            total_memory += slab_stats['memory_bytes']
            used_memory += slab_stats['allocated_blocks'] * size

        if total_memory == 0:
            return 0.0

        return 1.0 - (used_memory / total_memory)

    def _defragment(self):
        """Attempt to defragment memory pools."""
        logger.info("Running defragmentation")
        self.slab_allocator.shrink_slabs(target_ratio=0.4)

    def get_stats(self) -> MemoryStats:
        """Get memory pool statistics."""
        with self._lock:
            fragmentation = self._check_fragmentation()
            pressure = self.pressure_handler.check_pressure()

            # Get GC stats
            gc_stats = {i: gc.get_count()[i] for i in range(3)}

            return MemoryStats(
                total_bytes=self.max_memory_bytes,
                used_bytes=self.current_usage_bytes,
                free_bytes=self.max_memory_bytes - self.current_usage_bytes,
                allocated_blocks=len(self.key_blocks),
                free_blocks=sum(
                    len(s.free_blocks)
                    for s in self.slab_allocator.slabs.values()
                ),
                fragmentation_ratio=fragmentation,
                pressure_level=pressure,
                gc_collections=gc_stats,
            )

    def get_detailed_stats(self) -> Dict[str, Any]:
        """Get detailed memory pool statistics."""
        stats = self.get_stats()
        slab_stats = self.slab_allocator.get_stats()

        return {
            'summary': {
                'total_mb': stats.total_bytes / (1024 * 1024),
                'used_mb': stats.used_bytes / (1024 * 1024),
                'free_mb': stats.free_bytes / (1024 * 1024),
                'utilization': stats.used_bytes / stats.total_bytes if stats.total_bytes > 0 else 0,
                'fragmentation': stats.fragmentation_ratio,
                'pressure_level': stats.pressure_level.value,
            },
            'allocations': {
                'total_allocations': self.total_allocations,
                'total_frees': self.total_frees,
                'allocation_failures': self.allocation_failures,
                'current_entries': len(self.key_blocks),
            },
            'slab_classes': slab_stats,
            'gc_stats': stats.gc_collections,
        }


class ObjectPool(dict):
    """
    Generic object pool for reusing expensive-to-create objects.
    """

    def __init__(
        self,
        factory: Callable[[], Any],
        max_size: int = 100,
        cleanup: Optional[Callable[[Any], None]] = None
    ):
        super().__init__()
        self.factory = factory
        self.max_size = max_size
        self.cleanup = cleanup
        self.pool: deque = deque(maxlen=max_size)
        self._lock = threading.Lock()

        # Stats
        self.gets = 0
        self.creates = 0
        self.returns = 0

    def get(self) -> Any:
        """Get an object from the pool or create a new one."""
        with self._lock:
            self.gets += 1
            if self.pool:
                return self.pool.popleft()
            else:
                self.creates += 1
                return self.factory()

    def put(self, obj: Any):
        """Return an object to the pool."""
        with self._lock:
            self.returns += 1
            if self.cleanup:
                try:
                    self.cleanup(obj)
                except Exception:
                    return  # Don't pool if cleanup fails

            if len(self.pool) < self.max_size:
                self.pool.append(obj)

    def clear(self):
        """Clear all pooled objects."""
        with self._lock:
            self.pool.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        with self._lock:
            return {
                'pool_size': len(self.pool),
                'max_size': self.max_size,
                'gets': self.gets,
                'creates': self.creates,
                'returns': self.returns,
                'reuse_rate': (self.gets - self.creates) / self.gets if self.gets > 0 else 0,
            }
