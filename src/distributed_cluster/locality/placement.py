"""
Data Placement Strategies - استراتيجيات وضع البيانات
=====================================================

Strategies for placing data blocks across the cluster.
استراتيجيات لوضع كتل البيانات عبر الكلاستر.

Strategies:
- Random: Place randomly across workers
- RoundRobin: Distribute evenly across workers
- AffinityBased: Place near related data
- LoadBalanced: Consider worker load
- RackAware: Spread across racks for reliability
- MinimizeTransfer: Minimize network transfer
"""

from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set

from distributed_cluster.models.worker import WorkerInfo

from .scorer import NetworkTopology
from .tracker import DataBlock, DataLocation, DataLocationTracker, ReplicaState

logger = logging.getLogger(__name__)


class PlacementStrategy(str, Enum):
    """Available placement strategies."""

    RANDOM = "random"
    ROUND_ROBIN = "round_robin"
    AFFINITY_BASED = "affinity_based"
    LOAD_BALANCED = "load_balanced"
    RACK_AWARE = "rack_aware"
    MINIMIZE_TRANSFER = "minimize_transfer"
    COLOCATE = "colocate"  # Place with related data


@dataclass
class PlacementConfig:
    """
    Configuration for data placement.
    إعدادات وضع البيانات.
    """

    # Replication settings
    replication_factor: int = 2  # Number of replicas (including primary)
    min_replicas: int = 1  # Minimum healthy replicas
    max_replicas_per_rack: int = 2  # Spread across racks

    # Load balancing
    max_blocks_per_worker: Optional[int] = None
    max_size_per_worker_gb: Optional[float] = None

    # Affinity settings
    prefer_same_rack: bool = True
    prefer_same_zone: bool = True
    avoid_primary_node: bool = True  # For replicas

    # Transfer optimization
    prefer_fast_network: bool = True
    max_concurrent_transfers: int = 5

    # Failure handling
    exclude_failed_workers: bool = True
    min_worker_health_score: float = 0.5


@dataclass
class PlacementDecision:
    """
    A placement decision for a data block.
    قرار وضع لكتلة بيانات.
    """

    block_id: str
    primary_worker: str
    replica_workers: List[str] = field(default_factory=list)

    # Placement info
    strategy_used: PlacementStrategy = PlacementStrategy.RANDOM
    placement_score: float = 0.0

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Estimated transfer
    total_transfer_bytes: int = 0
    estimated_transfer_time_seconds: float = 0.0

    @property
    def all_workers(self) -> List[str]:
        """Get all workers (primary + replicas)."""
        return [self.primary_worker] + self.replica_workers

    @property
    def replica_count(self) -> int:
        """Total number of copies (including primary)."""
        return 1 + len(self.replica_workers)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "block_id": self.block_id,
            "primary_worker": self.primary_worker,
            "replica_workers": self.replica_workers,
            "strategy_used": self.strategy_used.value,
            "placement_score": self.placement_score,
            "created_at": self.created_at.isoformat(),
            "total_transfer_bytes": self.total_transfer_bytes,
            "estimated_transfer_time_seconds": self.estimated_transfer_time_seconds,
        }


@dataclass
class WorkerCapacity:
    """Worker capacity information for placement decisions."""

    worker_id: str
    total_blocks: int = 0
    total_size_bytes: int = 0
    available_space_bytes: int = 0
    health_score: float = 1.0

    # Network info
    rack_id: str = "default-rack"
    zone_id: str = "default-zone"

    # Current load
    active_transfers: int = 0
    network_utilization: float = 0.0


class PlacementStrategyBase(ABC):
    """Base class for placement strategies."""

    @abstractmethod
    async def select_workers(
        self,
        block: DataBlock,
        available_workers: List[WorkerCapacity],
        count: int,
        exclude_workers: Optional[Set[str]] = None,
    ) -> List[str]:
        """
        Select workers for placing a data block.
        اختيار workers لوضع كتلة بيانات.

        Args:
            block: The data block to place
            available_workers: List of available workers with capacity info
            count: Number of workers to select
            exclude_workers: Workers to exclude from selection

        Returns:
            List of selected worker IDs
        """
        pass


class RandomPlacementStrategy(PlacementStrategyBase):
    """
    Random placement strategy.
    استراتيجية وضع عشوائية.
    """

    async def select_workers(
        self,
        block: DataBlock,
        available_workers: List[WorkerCapacity],
        count: int,
        exclude_workers: Optional[Set[str]] = None,
    ) -> List[str]:
        exclude = exclude_workers or set()
        candidates = [w for w in available_workers if w.worker_id not in exclude]

        if len(candidates) < count:
            return [w.worker_id for w in candidates]

        selected = random.sample(candidates, count)
        return [w.worker_id for w in selected]


class RoundRobinPlacementStrategy(PlacementStrategyBase):
    """
    Round-robin placement strategy.
    استراتيجية وضع بالتناوب.
    """

    def __init__(self):
        self._current_index = 0

    async def select_workers(
        self,
        block: DataBlock,
        available_workers: List[WorkerCapacity],
        count: int,
        exclude_workers: Optional[Set[str]] = None,
    ) -> List[str]:
        exclude = exclude_workers or set()
        candidates = [w for w in available_workers if w.worker_id not in exclude]

        if not candidates:
            return []

        selected = []
        for _ in range(min(count, len(candidates))):
            idx = self._current_index % len(candidates)
            selected.append(candidates[idx].worker_id)
            self._current_index += 1

        return selected


class LoadBalancedPlacementStrategy(PlacementStrategyBase):
    """
    Load-balanced placement strategy.
    استراتيجية وضع متوازنة الحمل.

    Prefers workers with:
    - Less existing data
    - More available space
    - Lower network utilization
    """

    def __init__(self, config: Optional[PlacementConfig] = None):
        self.config = config or PlacementConfig()

    async def select_workers(
        self,
        block: DataBlock,
        available_workers: List[WorkerCapacity],
        count: int,
        exclude_workers: Optional[Set[str]] = None,
    ) -> List[str]:
        exclude = exclude_workers or set()
        candidates = [w for w in available_workers if w.worker_id not in exclude]

        if not candidates:
            return []

        # Filter by constraints
        if self.config.max_blocks_per_worker:
            candidates = [
                w
                for w in candidates
                if w.total_blocks < self.config.max_blocks_per_worker
            ]

        if self.config.max_size_per_worker_gb:
            max_bytes = self.config.max_size_per_worker_gb * 1024 * 1024 * 1024
            candidates = [
                w
                for w in candidates
                if w.total_size_bytes + block.size_bytes <= max_bytes
            ]

        if not candidates:
            return []

        # Score workers
        scored = []
        for worker in candidates:
            score = self._calculate_score(worker, block)
            scored.append((worker, score))

        # Sort by score (higher = better)
        scored.sort(key=lambda x: x[1], reverse=True)

        return [w.worker_id for w, _ in scored[:count]]

    def _calculate_score(self, worker: WorkerCapacity, block: DataBlock) -> float:
        """Calculate placement score for a worker."""
        score = 0.0

        # Available space score (0-0.4)
        if worker.available_space_bytes > 0:
            space_ratio = (
                worker.available_space_bytes - block.size_bytes
            ) / worker.available_space_bytes
            score += 0.4 * max(0, min(1, space_ratio))

        # Block count score (0-0.3) - fewer blocks = higher score
        if worker.total_blocks < 100:
            score += 0.3 * (1 - worker.total_blocks / 100)

        # Network utilization score (0-0.2)
        score += 0.2 * (1 - worker.network_utilization)

        # Health score (0-0.1)
        score += 0.1 * worker.health_score

        return score


class RackAwarePlacementStrategy(PlacementStrategyBase):
    """
    Rack-aware placement strategy.
    استراتيجية وضع واعية بالرفوف.

    Spreads replicas across different racks for fault tolerance.
    """

    def __init__(
        self,
        config: Optional[PlacementConfig] = None,
        topology: Optional[NetworkTopology] = None,
    ):
        self.config = config or PlacementConfig()
        self.topology = topology or NetworkTopology()

    async def select_workers(
        self,
        block: DataBlock,
        available_workers: List[WorkerCapacity],
        count: int,
        exclude_workers: Optional[Set[str]] = None,
    ) -> List[str]:
        exclude = exclude_workers or set()
        candidates = [w for w in available_workers if w.worker_id not in exclude]

        if not candidates:
            return []

        # Group by rack
        racks: Dict[str, List[WorkerCapacity]] = {}
        for worker in candidates:
            rack_id = worker.rack_id
            if rack_id not in racks:
                racks[rack_id] = []
            racks[rack_id].append(worker)

        selected = []
        rack_order = list(racks.keys())
        random.shuffle(rack_order)

        # Select one from each rack first
        for rack_id in rack_order:
            if len(selected) >= count:
                break

            rack_workers = racks[rack_id]
            # Sort by health score
            rack_workers.sort(key=lambda w: w.health_score, reverse=True)
            selected.append(rack_workers[0].worker_id)

        # If we need more, add from racks with multiple workers
        if len(selected) < count:
            for rack_id in rack_order:
                if len(selected) >= count:
                    break

                rack_workers = racks[rack_id]
                for worker in rack_workers[1:]:  # Skip first (already selected)
                    if len(selected) >= count:
                        break
                    if worker.worker_id not in selected:
                        selected.append(worker.worker_id)

        return selected[:count]


class AffinityBasedPlacementStrategy(PlacementStrategyBase):
    """
    Affinity-based placement strategy.
    استراتيجية وضع قائمة على التقارب.

    Places data near related data for locality.
    """

    def __init__(
        self,
        tracker: DataLocationTracker,
        config: Optional[PlacementConfig] = None,
    ):
        self.tracker = tracker
        self.config = config or PlacementConfig()

    async def select_workers(
        self,
        block: DataBlock,
        available_workers: List[WorkerCapacity],
        count: int,
        exclude_workers: Optional[Set[str]] = None,
    ) -> List[str]:
        exclude = exclude_workers or set()
        candidates = [w for w in available_workers if w.worker_id not in exclude]

        if not candidates:
            return []

        # Get related blocks (from same job or with affinity)
        related_blocks = await self._get_related_blocks(block)

        if not related_blocks:
            # Fall back to random
            return [
                w.worker_id
                for w in random.sample(candidates, min(count, len(candidates)))
            ]

        # Find workers with related data
        worker_scores: Dict[str, float] = {}

        for related_id in related_blocks:
            locations = await self.tracker.get_locations(related_id)
            for loc in locations:
                if loc.worker_id not in worker_scores:
                    worker_scores[loc.worker_id] = 0.0
                # Primary locations get higher weight
                worker_scores[loc.worker_id] += 2.0 if loc.is_primary else 1.0

        # Sort candidates by affinity score
        scored = []
        for worker in candidates:
            score = worker_scores.get(worker.worker_id, 0.0)
            scored.append((worker, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        return [w.worker_id for w, _ in scored[:count]]

    async def _get_related_blocks(self, block: DataBlock) -> List[str]:
        """Get IDs of related data blocks."""
        related = []

        # Blocks from same job
        if block.job_id:
            job_blocks = await self.tracker.get_job_blocks(block.job_id)
            for b in job_blocks:
                if b.block_id != block.block_id:
                    related.append(b.block_id)

        # Blocks with explicit affinity
        if "affinity_blocks" in block.metadata:
            affinity = block.metadata["affinity_blocks"].split(",")
            related.extend([b.strip() for b in affinity if b.strip()])

        return related


class ColocatePlacementStrategy(PlacementStrategyBase):
    """
    Colocation placement strategy.
    استراتيجية وضع التوزع المشترك.

    Places data on the same workers as specified target blocks.
    """

    def __init__(
        self,
        tracker: DataLocationTracker,
        target_block_ids: List[str],
    ):
        self.tracker = tracker
        self.target_block_ids = target_block_ids

    async def select_workers(
        self,
        block: DataBlock,
        available_workers: List[WorkerCapacity],
        count: int,
        exclude_workers: Optional[Set[str]] = None,
    ) -> List[str]:
        exclude = exclude_workers or set()

        # Find workers that have the target blocks
        target_workers: Set[str] = set()

        for target_id in self.target_block_ids:
            locations = await self.tracker.get_locations(target_id)
            for loc in locations:
                if loc.is_healthy():
                    target_workers.add(loc.worker_id)

        # Filter to available workers
        available_ids = {w.worker_id for w in available_workers}
        valid_workers = target_workers & available_ids - exclude

        if not valid_workers:
            # Fall back to random from available
            candidates = [w for w in available_workers if w.worker_id not in exclude]
            if not candidates:
                return []
            return [
                w.worker_id
                for w in random.sample(candidates, min(count, len(candidates)))
            ]

        return list(valid_workers)[:count]


class MinimizeTransferPlacementStrategy(PlacementStrategyBase):
    """
    Minimize transfer placement strategy.
    استراتيجية تقليل النقل.

    Selects workers that minimize data transfer time.
    """

    def __init__(
        self,
        tracker: DataLocationTracker,
        topology: Optional[NetworkTopology] = None,
        source_worker: Optional[str] = None,
    ):
        self.tracker = tracker
        self.topology = topology or NetworkTopology()
        self.source_worker = source_worker

    async def select_workers(
        self,
        block: DataBlock,
        available_workers: List[WorkerCapacity],
        count: int,
        exclude_workers: Optional[Set[str]] = None,
    ) -> List[str]:
        exclude = exclude_workers or set()
        candidates = [w for w in available_workers if w.worker_id not in exclude]

        if not candidates:
            return []

        source = self.source_worker or block.source_worker

        if not source:
            # No source, use random
            return [
                w.worker_id
                for w in random.sample(candidates, min(count, len(candidates)))
            ]

        # Score workers by network proximity to source
        scored = []
        for worker in candidates:
            level = self.topology.get_locality_level(source, worker.worker_id)
            bandwidth = self.topology.get_bandwidth(level)
            latency = self.topology.get_latency(level)

            # Calculate transfer time
            size_mb = block.size_bytes / (1024 * 1024)
            transfer_time = latency / 1000 + size_mb / (bandwidth / 8)

            # Lower transfer time = higher score
            score = 1.0 / (1.0 + transfer_time)
            scored.append((worker, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        return [w.worker_id for w, _ in scored[:count]]


class DataPlacementManager:
    """
    Manages data placement across the cluster.
    يدير وضع البيانات عبر الكلاستر.
    """

    def __init__(
        self,
        tracker: DataLocationTracker,
        config: Optional[PlacementConfig] = None,
        topology: Optional[NetworkTopology] = None,
    ):
        self.tracker = tracker
        self.config = config or PlacementConfig()
        self.topology = topology or NetworkTopology()

        # Strategies
        self._strategies: Dict[PlacementStrategy, PlacementStrategyBase] = {
            PlacementStrategy.RANDOM: RandomPlacementStrategy(),
            PlacementStrategy.ROUND_ROBIN: RoundRobinPlacementStrategy(),
            PlacementStrategy.LOAD_BALANCED: LoadBalancedPlacementStrategy(self.config),
            PlacementStrategy.RACK_AWARE: RackAwarePlacementStrategy(
                self.config, self.topology
            ),
            PlacementStrategy.AFFINITY_BASED: AffinityBasedPlacementStrategy(
                self.tracker, self.config
            ),
        }

        # Worker capacity cache
        self._worker_capacities: Dict[str, WorkerCapacity] = {}

    def register_strategy(
        self,
        name: PlacementStrategy,
        strategy: PlacementStrategyBase,
    ) -> None:
        """Register a custom placement strategy."""
        self._strategies[name] = strategy

    async def decide_placement(
        self,
        block: DataBlock,
        workers: List[WorkerInfo],
        strategy: PlacementStrategy = PlacementStrategy.LOAD_BALANCED,
        source_worker: Optional[str] = None,
    ) -> PlacementDecision:
        """
        Decide where to place a data block.
        تقرير أين يتم وضع كتلة بيانات.
        """
        # Build capacity info for workers
        capacities = []
        for worker in workers:
            capacity = await self._get_worker_capacity(worker)
            if capacity.health_score >= self.config.min_worker_health_score:
                capacities.append(capacity)

        if not capacities:
            raise ValueError("No healthy workers available for placement")

        # Get strategy
        placement_strategy = self._strategies.get(strategy)
        if not placement_strategy:
            placement_strategy = self._strategies[PlacementStrategy.RANDOM]

        # Select primary worker
        primary_workers = await placement_strategy.select_workers(
            block,
            capacities,
            count=1,
        )

        if not primary_workers:
            raise ValueError("Could not select primary worker")

        primary_worker = primary_workers[0]

        # Select replica workers
        replica_count = self.config.replication_factor - 1
        replica_workers = []

        if replica_count > 0:
            exclude = {primary_worker}

            # Use rack-aware for replicas if configured
            if self.config.prefer_same_rack:
                replica_strategy = self._strategies[PlacementStrategy.RACK_AWARE]
            else:
                replica_strategy = placement_strategy

            replica_workers = await replica_strategy.select_workers(
                block,
                capacities,
                count=replica_count,
                exclude_workers=exclude,
            )

        # Calculate transfer estimates
        total_transfer = 0
        transfer_time = 0.0

        if source_worker and source_worker != primary_worker:
            total_transfer += block.size_bytes
            level = self.topology.get_locality_level(source_worker, primary_worker)
            bandwidth = self.topology.get_bandwidth(level)
            latency = self.topology.get_latency(level) / 1000
            transfer_time += latency + block.size_bytes / (bandwidth / 8 * 1024 * 1024)

        for replica in replica_workers:
            total_transfer += block.size_bytes
            level = self.topology.get_locality_level(primary_worker, replica)
            bandwidth = self.topology.get_bandwidth(level)
            latency = self.topology.get_latency(level) / 1000
            transfer_time += latency + block.size_bytes / (bandwidth / 8 * 1024 * 1024)

        return PlacementDecision(
            block_id=block.block_id,
            primary_worker=primary_worker,
            replica_workers=replica_workers,
            strategy_used=strategy,
            placement_score=1.0,  # Would need more context for actual scoring
            total_transfer_bytes=total_transfer,
            estimated_transfer_time_seconds=transfer_time,
        )

    async def apply_placement(
        self,
        decision: PlacementDecision,
        block: DataBlock,
        local_paths: Optional[Dict[str, str]] = None,
    ) -> List[DataLocation]:
        """
        Apply a placement decision by registering locations.
        تطبيق قرار وضع عن طريق تسجيل المواقع.
        """
        locations = []
        local_paths = local_paths or {}

        # Register primary
        primary_path = local_paths.get(
            decision.primary_worker,
            f"/data/{block.block_id}",
        )
        primary_loc = await self.tracker.add_location(
            block_id=block.block_id,
            worker_id=decision.primary_worker,
            local_path=primary_path,
            is_primary=True,
            state=ReplicaState.AVAILABLE,
        )
        if primary_loc:
            locations.append(primary_loc)

        # Register replicas
        for i, replica_worker in enumerate(decision.replica_workers):
            replica_path = local_paths.get(
                replica_worker,
                f"/data/{block.block_id}",
            )
            replica_loc = await self.tracker.add_location(
                block_id=block.block_id,
                worker_id=replica_worker,
                local_path=replica_path,
                is_primary=False,
                state=ReplicaState.PENDING,  # Needs to be transferred
            )
            if replica_loc:
                locations.append(replica_loc)

        return locations

    async def rebalance_data(
        self,
        workers: List[WorkerInfo],
        dry_run: bool = False,
    ) -> List[PlacementDecision]:
        """
        Rebalance data across workers.
        إعادة توازن البيانات عبر workers.
        """
        decisions = []

        # Get current distribution
        distribution: Dict[str, int] = {}
        for worker in workers:
            blocks = await self.tracker.get_worker_blocks(worker.worker_id)
            distribution[worker.worker_id] = len(blocks)

        if not distribution:
            return decisions

        # Calculate target distribution
        total_blocks = sum(distribution.values())
        avg_blocks = total_blocks / len(workers)

        # Find overloaded and underloaded workers
        overloaded = [
            (w, count)
            for w, count in distribution.items()
            if count > avg_blocks * 1.2
        ]
        underloaded = [
            (w, count)
            for w, count in distribution.items()
            if count < avg_blocks * 0.8
        ]

        # Plan moves
        for over_worker, over_count in overloaded:
            excess = int(over_count - avg_blocks)
            blocks = await self.tracker.get_worker_blocks(over_worker)

            for block in blocks[:excess]:
                if not underloaded:
                    break

                under_worker, under_count = underloaded[0]

                decision = PlacementDecision(
                    block_id=block.block_id,
                    primary_worker=under_worker,
                    replica_workers=[],
                    strategy_used=PlacementStrategy.LOAD_BALANCED,
                )
                decisions.append(decision)

                # Update counts
                underloaded[0] = (under_worker, under_count + 1)
                if under_count + 1 >= avg_blocks * 0.8:
                    underloaded.pop(0)

        if not dry_run:
            # Apply moves (would need actual transfer implementation)
            for decision in decisions:
                logger.info(
                    f"Moving block {decision.block_id} to {decision.primary_worker}"
                )

        return decisions

    async def _get_worker_capacity(self, worker: WorkerInfo) -> WorkerCapacity:
        """Get or build capacity info for a worker."""
        if worker.worker_id in self._worker_capacities:
            return self._worker_capacities[worker.worker_id]

        blocks = await self.tracker.get_worker_blocks(worker.worker_id)

        capacity = WorkerCapacity(
            worker_id=worker.worker_id,
            total_blocks=len(blocks),
            total_size_bytes=sum(b.size_bytes for b in blocks),
            available_space_bytes=worker.available_resources.disk_gb * 1024 * 1024 * 1024
            if hasattr(worker.available_resources, "disk_gb")
            else 1024 * 1024 * 1024 * 100,  # Default 100GB
            health_score=1.0 if worker.is_healthy else 0.0,
            rack_id=self.topology.get_worker_rack(worker.worker_id),
            zone_id=self.topology.get_worker_zone(worker.worker_id),
        )

        self._worker_capacities[worker.worker_id] = capacity
        return capacity

    def invalidate_capacity_cache(self, worker_id: Optional[str] = None) -> None:
        """Invalidate cached capacity information."""
        if worker_id:
            self._worker_capacities.pop(worker_id, None)
        else:
            self._worker_capacities.clear()
