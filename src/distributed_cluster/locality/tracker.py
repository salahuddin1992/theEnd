"""
Data Location Tracker - متتبع مواقع البيانات
=============================================

Tracks the location of data blocks across the cluster.
يتتبع مواقع البيانات عبر الكلاستر.

Key Concepts:
- DataBlock: A unit of data (file, chunk, partition)
- DataLocation: Where a DataBlock is stored
- Replica: A copy of a DataBlock on a different node

Features:
- Track data locations across workers
- Support for data replication
- Locality hints for scheduling
- Data freshness tracking
- Automatic stale data cleanup
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class DataType(str, Enum):
    """Types of data that can be tracked."""

    FILE = "file"  # Regular file
    CHUNK = "chunk"  # File chunk/partition
    MODEL = "model"  # ML model
    DATASET = "dataset"  # Training/inference dataset
    CACHE = "cache"  # Cached computation result
    CHECKPOINT = "checkpoint"  # Job checkpoint
    ARTIFACT = "artifact"  # Build/job artifact
    INTERMEDIATE = "intermediate"  # Intermediate computation result


class ReplicaState(str, Enum):
    """State of a data replica."""

    AVAILABLE = "available"  # Ready for use
    SYNCING = "syncing"  # Being synchronized
    STALE = "stale"  # Outdated, needs refresh
    PENDING = "pending"  # Not yet transferred
    FAILED = "failed"  # Transfer/sync failed


@dataclass
class DataBlock:
    """
    A unit of data in the cluster.
    وحدة بيانات في الكلاستر.
    """

    block_id: str  # Unique identifier
    data_type: DataType = DataType.FILE
    size_bytes: int = 0
    checksum: Optional[str] = None  # For integrity verification

    # Source information
    source_path: Optional[str] = None
    source_worker: Optional[str] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    modified_at: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    last_accessed: Optional[datetime] = None

    # Job associations
    job_id: Optional[str] = None
    is_input: bool = False
    is_output: bool = False

    # TTL for automatic cleanup
    ttl_seconds: Optional[int] = None

    # Custom metadata
    metadata: Dict[str, str] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if the data block has expired."""
        if self.ttl_seconds is None:
            return False
        age = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return age > self.ttl_seconds

    def touch(self) -> None:
        """Update access time."""
        self.last_accessed = datetime.now(timezone.utc)
        self.access_count += 1

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "block_id": self.block_id,
            "data_type": self.data_type.value,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "source_path": self.source_path,
            "source_worker": self.source_worker,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "job_id": self.job_id,
            "is_input": self.is_input,
            "is_output": self.is_output,
            "ttl_seconds": self.ttl_seconds,
            "metadata": self.metadata,
        }


@dataclass
class DataLocation:
    """
    Location of a data block replica.
    موقع نسخة من البيانات.
    """

    block_id: str
    worker_id: str
    local_path: str
    state: ReplicaState = ReplicaState.AVAILABLE

    # Replication info
    is_primary: bool = False  # Is this the primary replica?
    replica_index: int = 0  # 0 = primary, 1+ = replicas

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_verified: Optional[datetime] = None
    last_accessed: Optional[datetime] = None

    # Transfer info
    transfer_start: Optional[datetime] = None
    transfer_end: Optional[datetime] = None
    transfer_speed_mbps: Optional[float] = None

    # Health
    verification_failures: int = 0

    def is_healthy(self) -> bool:
        """Check if the replica is healthy and usable."""
        return self.state == ReplicaState.AVAILABLE and self.verification_failures < 3

    def mark_accessed(self) -> None:
        """Mark as recently accessed."""
        self.last_accessed = datetime.now(timezone.utc)

    def mark_verified(self) -> None:
        """Mark as verified."""
        self.last_verified = datetime.now(timezone.utc)
        self.verification_failures = 0

    def mark_failed(self) -> None:
        """Mark a verification failure."""
        self.verification_failures += 1
        if self.verification_failures >= 3:
            self.state = ReplicaState.STALE

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "block_id": self.block_id,
            "worker_id": self.worker_id,
            "local_path": self.local_path,
            "state": self.state.value,
            "is_primary": self.is_primary,
            "replica_index": self.replica_index,
            "created_at": self.created_at.isoformat(),
            "last_verified": self.last_verified.isoformat() if self.last_verified else None,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "is_healthy": self.is_healthy(),
        }


@dataclass
class LocalityInfo:
    """
    Locality information for scheduling decisions.
    معلومات المحلية لقرارات الجدولة.
    """

    worker_id: str
    total_blocks: int = 0
    total_size_bytes: int = 0
    primary_replicas: int = 0

    # Block IDs present on this worker
    block_ids: Set[str] = field(default_factory=set)

    # Scoring
    locality_score: float = 0.0

    def add_block(self, block_id: str, size_bytes: int, is_primary: bool) -> None:
        """Add a block to this worker's locality info."""
        self.block_ids.add(block_id)
        self.total_blocks += 1
        self.total_size_bytes += size_bytes
        if is_primary:
            self.primary_replicas += 1


class DataLocationTracker:
    """
    Tracks data locations across the cluster.
    يتتبع مواقع البيانات عبر الكلاستر.

    Thread-safe and supports async operations.
    """

    def __init__(
        self,
        stale_threshold_seconds: float = 300.0,  # 5 minutes
        cleanup_interval_seconds: float = 60.0,
        enable_background_cleanup: bool = True,
    ):
        self.stale_threshold_seconds = stale_threshold_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds

        # Data storage
        self._blocks: Dict[str, DataBlock] = {}
        self._locations: Dict[str, List[DataLocation]] = {}  # block_id -> locations
        self._worker_blocks: Dict[str, Set[str]] = {}  # worker_id -> block_ids

        # Indexes for fast lookup
        self._job_blocks: Dict[str, Set[str]] = {}  # job_id -> block_ids
        self._type_blocks: Dict[DataType, Set[str]] = {}  # data_type -> block_ids

        # Locking for thread safety
        self._lock = asyncio.Lock()

        # Background cleanup
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        self._enable_background_cleanup = enable_background_cleanup

        # Event callbacks
        self._on_block_registered: List[Callable] = []
        self._on_block_removed: List[Callable] = []
        self._on_location_added: List[Callable] = []
        self._on_location_removed: List[Callable] = []

        # Statistics
        self._stats = {
            "blocks_registered": 0,
            "blocks_removed": 0,
            "locations_added": 0,
            "locations_removed": 0,
            "lookups": 0,
            "hits": 0,
            "misses": 0,
        }

    async def start(self) -> None:
        """Start background tasks."""
        if self._running:
            return

        self._running = True

        if self._enable_background_cleanup:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("DataLocationTracker started")

    async def stop(self) -> None:
        """Stop background tasks."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("DataLocationTracker stopped")

    # ==================== Block Management ====================

    async def register_block(self, block: DataBlock) -> None:
        """
        Register a new data block.
        تسجيل كتلة بيانات جديدة.
        """
        async with self._lock:
            self._blocks[block.block_id] = block
            self._locations[block.block_id] = []

            # Update indexes
            if block.job_id:
                if block.job_id not in self._job_blocks:
                    self._job_blocks[block.job_id] = set()
                self._job_blocks[block.job_id].add(block.block_id)

            if block.data_type not in self._type_blocks:
                self._type_blocks[block.data_type] = set()
            self._type_blocks[block.data_type].add(block.block_id)

            self._stats["blocks_registered"] += 1

        # Fire callbacks
        for callback in self._on_block_registered:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(block)
                else:
                    callback(block)
            except Exception as e:
                logger.error(f"Error in block registered callback: {e}")

        logger.debug(f"Registered block: {block.block_id}")

    async def get_block(self, block_id: str) -> Optional[DataBlock]:
        """Get a data block by ID."""
        async with self._lock:
            self._stats["lookups"] += 1
            block = self._blocks.get(block_id)
            if block:
                self._stats["hits"] += 1
                block.touch()
            else:
                self._stats["misses"] += 1
            return block

    async def remove_block(self, block_id: str) -> bool:
        """
        Remove a data block and all its locations.
        إزالة كتلة بيانات وكل مواقعها.
        """
        async with self._lock:
            if block_id not in self._blocks:
                return False

            block = self._blocks[block_id]

            # Remove from worker mappings
            for location in self._locations.get(block_id, []):
                if location.worker_id in self._worker_blocks:
                    self._worker_blocks[location.worker_id].discard(block_id)

            # Remove from indexes
            if block.job_id and block.job_id in self._job_blocks:
                self._job_blocks[block.job_id].discard(block_id)

            if block.data_type in self._type_blocks:
                self._type_blocks[block.data_type].discard(block_id)

            # Remove block and locations
            del self._blocks[block_id]
            del self._locations[block_id]

            self._stats["blocks_removed"] += 1

        # Fire callbacks
        for callback in self._on_block_removed:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(block)
                else:
                    callback(block)
            except Exception as e:
                logger.error(f"Error in block removed callback: {e}")

        logger.debug(f"Removed block: {block_id}")
        return True

    # ==================== Location Management ====================

    async def add_location(
        self,
        block_id: str,
        worker_id: str,
        local_path: str,
        is_primary: bool = False,
        state: ReplicaState = ReplicaState.AVAILABLE,
    ) -> Optional[DataLocation]:
        """
        Add a location for a data block.
        إضافة موقع لكتلة بيانات.
        """
        async with self._lock:
            if block_id not in self._blocks:
                logger.warning(f"Block {block_id} not found")
                return None

            # Check if location already exists
            existing = self._find_location(block_id, worker_id)
            if existing:
                existing.state = state
                existing.local_path = local_path
                return existing

            # Determine replica index
            replica_index = len(self._locations[block_id])
            if is_primary:
                replica_index = 0

            location = DataLocation(
                block_id=block_id,
                worker_id=worker_id,
                local_path=local_path,
                state=state,
                is_primary=is_primary,
                replica_index=replica_index,
            )

            self._locations[block_id].append(location)

            # Update worker index
            if worker_id not in self._worker_blocks:
                self._worker_blocks[worker_id] = set()
            self._worker_blocks[worker_id].add(block_id)

            self._stats["locations_added"] += 1

        # Fire callbacks
        for callback in self._on_location_added:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(location)
                else:
                    callback(location)
            except Exception as e:
                logger.error(f"Error in location added callback: {e}")

        logger.debug(f"Added location: {block_id} on {worker_id}")
        return location

    async def remove_location(self, block_id: str, worker_id: str) -> bool:
        """
        Remove a specific location for a data block.
        إزالة موقع معين لكتلة بيانات.
        """
        async with self._lock:
            if block_id not in self._locations:
                return False

            location = self._find_location(block_id, worker_id)
            if not location:
                return False

            self._locations[block_id].remove(location)

            if worker_id in self._worker_blocks:
                self._worker_blocks[worker_id].discard(block_id)

            self._stats["locations_removed"] += 1

        # Fire callbacks
        for callback in self._on_location_removed:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(location)
                else:
                    callback(location)
            except Exception as e:
                logger.error(f"Error in location removed callback: {e}")

        logger.debug(f"Removed location: {block_id} from {worker_id}")
        return True

    async def get_locations(
        self,
        block_id: str,
        healthy_only: bool = True,
    ) -> List[DataLocation]:
        """
        Get all locations for a data block.
        الحصول على كل مواقع كتلة بيانات.
        """
        async with self._lock:
            locations = self._locations.get(block_id, [])
            if healthy_only:
                locations = [loc for loc in locations if loc.is_healthy()]
            return locations.copy()

    async def get_primary_location(self, block_id: str) -> Optional[DataLocation]:
        """Get the primary location for a data block."""
        async with self._lock:
            locations = self._locations.get(block_id, [])
            for loc in locations:
                if loc.is_primary and loc.is_healthy():
                    return loc
            # Fall back to first healthy location
            for loc in locations:
                if loc.is_healthy():
                    return loc
            return None

    async def update_location_state(
        self,
        block_id: str,
        worker_id: str,
        state: ReplicaState,
    ) -> bool:
        """Update the state of a location."""
        async with self._lock:
            location = self._find_location(block_id, worker_id)
            if location:
                location.state = state
                return True
            return False

    # ==================== Worker Queries ====================

    async def get_worker_blocks(self, worker_id: str) -> List[DataBlock]:
        """
        Get all data blocks on a worker.
        الحصول على كل كتل البيانات على worker معين.
        """
        async with self._lock:
            block_ids = self._worker_blocks.get(worker_id, set())
            return [self._blocks[bid] for bid in block_ids if bid in self._blocks]

    async def get_worker_locality_info(self, worker_id: str) -> LocalityInfo:
        """
        Get locality information for a worker.
        الحصول على معلومات المحلية لـ worker.
        """
        async with self._lock:
            info = LocalityInfo(worker_id=worker_id)
            block_ids = self._worker_blocks.get(worker_id, set())

            for block_id in block_ids:
                block = self._blocks.get(block_id)
                if not block:
                    continue

                location = self._find_location(block_id, worker_id)
                if location and location.is_healthy():
                    info.add_block(
                        block_id=block_id,
                        size_bytes=block.size_bytes,
                        is_primary=location.is_primary,
                    )

            return info

    async def remove_worker(self, worker_id: str) -> int:
        """
        Remove all data locations for a worker.
        إزالة كل مواقع البيانات لـ worker.

        Returns the number of locations removed.
        """
        removed_count = 0

        async with self._lock:
            block_ids = list(self._worker_blocks.get(worker_id, set()))

            for block_id in block_ids:
                if block_id in self._locations:
                    location = self._find_location(block_id, worker_id)
                    if location:
                        self._locations[block_id].remove(location)
                        removed_count += 1

            if worker_id in self._worker_blocks:
                del self._worker_blocks[worker_id]

        logger.info(f"Removed {removed_count} locations for worker {worker_id}")
        return removed_count

    # ==================== Job Queries ====================

    async def get_job_blocks(self, job_id: str) -> List[DataBlock]:
        """Get all data blocks associated with a job."""
        async with self._lock:
            block_ids = self._job_blocks.get(job_id, set())
            return [self._blocks[bid] for bid in block_ids if bid in self._blocks]

    async def get_job_input_blocks(self, job_id: str) -> List[DataBlock]:
        """Get input data blocks for a job."""
        blocks = await self.get_job_blocks(job_id)
        return [b for b in blocks if b.is_input]

    async def get_job_output_blocks(self, job_id: str) -> List[DataBlock]:
        """Get output data blocks for a job."""
        blocks = await self.get_job_blocks(job_id)
        return [b for b in blocks if b.is_output]

    async def remove_job_blocks(
        self,
        job_id: str,
        outputs_only: bool = False,
    ) -> int:
        """
        Remove all data blocks for a job.
        إزالة كل كتل البيانات لـ job.
        """
        async with self._lock:
            block_ids = list(self._job_blocks.get(job_id, set()))

        removed = 0
        for block_id in block_ids:
            block = await self.get_block(block_id)
            if block and (not outputs_only or block.is_output):
                await self.remove_block(block_id)
                removed += 1

        return removed

    # ==================== Locality Scoring ====================

    async def calculate_locality_score(
        self,
        worker_id: str,
        required_blocks: List[str],
        weights: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Calculate locality score for a worker given required data blocks.
        حساب درجة المحلية لـ worker بناءً على البيانات المطلوبة.

        Higher score = more data locally available.
        """
        if not required_blocks:
            return 1.0  # No data requirements, perfect locality

        weights = weights or {}

        async with self._lock:
            worker_block_ids = self._worker_blocks.get(worker_id, set())

            total_weight = 0.0
            local_weight = 0.0

            for block_id in required_blocks:
                block = self._blocks.get(block_id)
                if not block:
                    continue

                # Weight by size or custom weight
                weight = weights.get(block_id, block.size_bytes / (1024 * 1024))  # MB
                weight = max(weight, 1.0)  # Minimum weight of 1

                total_weight += weight

                if block_id in worker_block_ids:
                    location = self._find_location(block_id, worker_id)
                    if location and location.is_healthy():
                        # Primary replicas get full weight
                        if location.is_primary:
                            local_weight += weight
                        else:
                            local_weight += weight * 0.9  # Replicas slightly lower

        if total_weight == 0:
            return 0.5  # Neutral score if no blocks found

        return local_weight / total_weight

    async def find_best_workers(
        self,
        required_blocks: List[str],
        top_n: int = 5,
    ) -> List[Tuple[str, float]]:
        """
        Find the best workers for given data blocks.
        إيجاد أفضل workers للبيانات المطلوبة.

        Returns list of (worker_id, locality_score) tuples.
        """
        async with self._lock:
            worker_scores: Dict[str, float] = {}

            for block_id in required_blocks:
                block = self._blocks.get(block_id)
                if not block:
                    continue

                weight = block.size_bytes / (1024 * 1024)  # MB
                weight = max(weight, 1.0)

                for location in self._locations.get(block_id, []):
                    if location.is_healthy():
                        if location.worker_id not in worker_scores:
                            worker_scores[location.worker_id] = 0.0

                        score_add = weight
                        if location.is_primary:
                            score_add *= 1.1  # Bonus for primary

                        worker_scores[location.worker_id] += score_add

            # Normalize scores
            if worker_scores:
                max_score = max(worker_scores.values())
                if max_score > 0:
                    worker_scores = {
                        w: s / max_score for w, s in worker_scores.items()
                    }

            # Sort and return top N
            sorted_workers = sorted(
                worker_scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )

            return sorted_workers[:top_n]

    # ==================== Cleanup ====================

    async def cleanup_stale_locations(self) -> int:
        """
        Clean up stale data locations.
        تنظيف مواقع البيانات القديمة.
        """
        now = datetime.now(timezone.utc)
        stale_threshold = timedelta(seconds=self.stale_threshold_seconds)
        removed = 0

        async with self._lock:
            for block_id in list(self._locations.keys()):
                locations = self._locations[block_id]
                stale_locations = []

                for location in locations:
                    if location.state == ReplicaState.STALE:
                        stale_locations.append(location)
                    elif location.last_verified:
                        if now - location.last_verified > stale_threshold:
                            location.state = ReplicaState.STALE
                            stale_locations.append(location)

                # Remove stale locations (keep at least one)
                if len(locations) > 1:
                    for stale in stale_locations[:-1]:
                        self._locations[block_id].remove(stale)
                        if stale.worker_id in self._worker_blocks:
                            self._worker_blocks[stale.worker_id].discard(block_id)
                        removed += 1

        if removed > 0:
            logger.info(f"Cleaned up {removed} stale locations")

        return removed

    async def cleanup_expired_blocks(self) -> int:
        """Clean up expired data blocks."""
        expired = []

        async with self._lock:
            for block_id, block in self._blocks.items():
                if block.is_expired():
                    expired.append(block_id)

        for block_id in expired:
            await self.remove_block(block_id)

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired blocks")

        return len(expired)

    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self.cleanup_stale_locations()
                await self.cleanup_expired_blocks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    # ==================== Statistics ====================

    async def get_stats(self) -> Dict:
        """Get tracker statistics."""
        async with self._lock:
            total_blocks = len(self._blocks)
            total_locations = sum(len(locs) for locs in self._locations.values())
            total_workers = len(self._worker_blocks)

            total_size = sum(b.size_bytes for b in self._blocks.values())

            type_counts = {
                dtype.value: len(bids)
                for dtype, bids in self._type_blocks.items()
            }

            return {
                **self._stats,
                "total_blocks": total_blocks,
                "total_locations": total_locations,
                "total_workers": total_workers,
                "total_size_bytes": total_size,
                "type_counts": type_counts,
                "hit_rate": (
                    self._stats["hits"] / max(self._stats["lookups"], 1)
                ),
            }

    # ==================== Event Callbacks ====================

    def on_block_registered(self, callback: Callable) -> None:
        """Register callback for block registration."""
        self._on_block_registered.append(callback)

    def on_block_removed(self, callback: Callable) -> None:
        """Register callback for block removal."""
        self._on_block_removed.append(callback)

    def on_location_added(self, callback: Callable) -> None:
        """Register callback for location addition."""
        self._on_location_added.append(callback)

    def on_location_removed(self, callback: Callable) -> None:
        """Register callback for location removal."""
        self._on_location_removed.append(callback)

    # ==================== Internal Helpers ====================

    def _find_location(
        self,
        block_id: str,
        worker_id: str,
    ) -> Optional[DataLocation]:
        """Find a specific location (not thread-safe, call within lock)."""
        locations = self._locations.get(block_id, [])
        for loc in locations:
            if loc.worker_id == worker_id:
                return loc
        return None


# ==================== Helper Functions ====================


def create_block_id(
    source_path: str,
    worker_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> str:
    """Create a consistent block ID from source information."""
    import hashlib

    parts = [source_path]
    if job_id:
        parts.append(job_id)

    hash_input = ":".join(parts)
    hash_value = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    return f"block-{hash_value}"


def estimate_transfer_time(
    size_bytes: int,
    bandwidth_mbps: float = 100.0,
    overhead_seconds: float = 0.5,
) -> float:
    """Estimate data transfer time in seconds."""
    size_mb = size_bytes / (1024 * 1024)
    transfer_time = size_mb / (bandwidth_mbps / 8)  # Convert to MB/s
    return transfer_time + overhead_seconds
