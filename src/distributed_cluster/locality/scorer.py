"""
Locality Scorer - مسجّل المحلية
=================================

Advanced scoring algorithms for data locality in scheduling.
خوارزميات متقدمة لتسجيل محلية البيانات في الجدولة.

Scoring Factors:
- Data presence (local vs remote)
- Data size (larger = more important)
- Access patterns (frequently accessed = higher priority)
- Network topology (rack-aware, zone-aware)
- Transfer cost estimation
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from distributed_cluster.models.job import Job
from distributed_cluster.models.worker import WorkerInfo

from .tracker import DataBlock, DataLocation, DataLocationTracker

logger = logging.getLogger(__name__)


class LocalityLevel(str, Enum):
    """Levels of data locality."""

    NODE_LOCAL = "node_local"  # Data on the same node
    RACK_LOCAL = "rack_local"  # Data on the same rack
    ZONE_LOCAL = "zone_local"  # Data on the same zone/DC
    REMOTE = "remote"  # Data needs to be transferred


@dataclass
class LocalityPreference:
    """
    Locality preference for scheduling.
    تفضيل المحلية للجدولة.
    """

    level: LocalityLevel = LocalityLevel.NODE_LOCAL
    weight: float = 1.0  # Importance of this level
    acceptable_levels: List[LocalityLevel] = field(
        default_factory=lambda: [
            LocalityLevel.NODE_LOCAL,
            LocalityLevel.RACK_LOCAL,
            LocalityLevel.ZONE_LOCAL,
            LocalityLevel.REMOTE,
        ]
    )
    max_transfer_size_mb: Optional[float] = None  # Max data to transfer


@dataclass
class NetworkTopology:
    """
    Network topology information for locality scoring.
    معلومات طوبولوجيا الشبكة لتسجيل المحلية.
    """

    # Worker -> Rack mapping
    worker_rack: Dict[str, str] = field(default_factory=dict)

    # Worker -> Zone/DC mapping
    worker_zone: Dict[str, str] = field(default_factory=dict)

    # Rack -> Zone mapping
    rack_zone: Dict[str, str] = field(default_factory=dict)

    # Bandwidth estimates (in Mbps)
    intra_node_bandwidth: float = 10000.0  # 10 Gbps local
    intra_rack_bandwidth: float = 1000.0  # 1 Gbps within rack
    intra_zone_bandwidth: float = 500.0  # 500 Mbps within zone
    inter_zone_bandwidth: float = 100.0  # 100 Mbps between zones

    # Latency estimates (in ms)
    intra_node_latency: float = 0.1
    intra_rack_latency: float = 1.0
    intra_zone_latency: float = 5.0
    inter_zone_latency: float = 50.0

    def get_worker_rack(self, worker_id: str) -> str:
        """Get rack for a worker."""
        return self.worker_rack.get(worker_id, "default-rack")

    def get_worker_zone(self, worker_id: str) -> str:
        """Get zone for a worker."""
        return self.worker_zone.get(worker_id, "default-zone")

    def get_locality_level(
        self,
        source_worker: str,
        target_worker: str,
    ) -> LocalityLevel:
        """Determine locality level between two workers."""
        if source_worker == target_worker:
            return LocalityLevel.NODE_LOCAL

        source_rack = self.get_worker_rack(source_worker)
        target_rack = self.get_worker_rack(target_worker)

        if source_rack == target_rack:
            return LocalityLevel.RACK_LOCAL

        source_zone = self.get_worker_zone(source_worker)
        target_zone = self.get_worker_zone(target_worker)

        if source_zone == target_zone:
            return LocalityLevel.ZONE_LOCAL

        return LocalityLevel.REMOTE

    def get_bandwidth(self, level: LocalityLevel) -> float:
        """Get estimated bandwidth for a locality level."""
        return {
            LocalityLevel.NODE_LOCAL: self.intra_node_bandwidth,
            LocalityLevel.RACK_LOCAL: self.intra_rack_bandwidth,
            LocalityLevel.ZONE_LOCAL: self.intra_zone_bandwidth,
            LocalityLevel.REMOTE: self.inter_zone_bandwidth,
        }.get(level, self.inter_zone_bandwidth)

    def get_latency(self, level: LocalityLevel) -> float:
        """Get estimated latency for a locality level."""
        return {
            LocalityLevel.NODE_LOCAL: self.intra_node_latency,
            LocalityLevel.RACK_LOCAL: self.intra_rack_latency,
            LocalityLevel.ZONE_LOCAL: self.intra_zone_latency,
            LocalityLevel.REMOTE: self.inter_zone_latency,
        }.get(level, self.inter_zone_latency)


@dataclass
class LocalityScoreResult:
    """
    Result of locality scoring.
    نتيجة تسجيل المحلية.
    """

    worker_id: str
    total_score: float  # 0.0 to 1.0
    locality_level: LocalityLevel  # Best locality level achieved

    # Score breakdown
    local_data_score: float = 0.0  # Score for locally available data
    transfer_cost_score: float = 0.0  # Score for transfer cost (lower = better)
    access_pattern_score: float = 0.0  # Score based on access patterns

    # Data statistics
    total_blocks_required: int = 0
    local_blocks: int = 0
    rack_local_blocks: int = 0
    zone_local_blocks: int = 0
    remote_blocks: int = 0

    # Size statistics
    total_size_bytes: int = 0
    local_size_bytes: int = 0
    transfer_size_bytes: int = 0

    # Transfer estimates
    estimated_transfer_time_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "worker_id": self.worker_id,
            "total_score": self.total_score,
            "locality_level": self.locality_level.value,
            "local_data_score": self.local_data_score,
            "transfer_cost_score": self.transfer_cost_score,
            "access_pattern_score": self.access_pattern_score,
            "total_blocks_required": self.total_blocks_required,
            "local_blocks": self.local_blocks,
            "rack_local_blocks": self.rack_local_blocks,
            "zone_local_blocks": self.zone_local_blocks,
            "remote_blocks": self.remote_blocks,
            "total_size_bytes": self.total_size_bytes,
            "local_size_bytes": self.local_size_bytes,
            "transfer_size_bytes": self.transfer_size_bytes,
            "estimated_transfer_time_seconds": self.estimated_transfer_time_seconds,
        }


@dataclass
class LocalityScoringConfig:
    """
    Configuration for locality scoring.
    إعدادات تسجيل المحلية.
    """

    # Score weights
    local_data_weight: float = 0.5  # Weight for local data presence
    transfer_cost_weight: float = 0.3  # Weight for transfer cost
    access_pattern_weight: float = 0.2  # Weight for access patterns

    # Locality level scores (0.0 to 1.0)
    node_local_score: float = 1.0
    rack_local_score: float = 0.7
    zone_local_score: float = 0.4
    remote_score: float = 0.1

    # Transfer cost thresholds
    low_transfer_threshold_mb: float = 100.0  # Below this = low cost
    high_transfer_threshold_mb: float = 1000.0  # Above this = high cost

    # Access pattern scoring
    min_access_for_bonus: int = 5  # Minimum accesses for bonus
    access_bonus_weight: float = 0.2  # Bonus for frequently accessed data

    # Enable topology-aware scoring
    topology_aware: bool = True


class LocalityScorerBase(ABC):
    """Base class for locality scorers."""

    @abstractmethod
    async def score(
        self,
        job: Job,
        worker: WorkerInfo,
        tracker: DataLocationTracker,
    ) -> LocalityScoreResult:
        """Calculate locality score for a worker given a job."""
        pass


class LocalityScorer(LocalityScorerBase):
    """
    Advanced locality scorer.
    مسجّل المحلية المتقدم.

    Calculates a comprehensive locality score considering:
    - Data presence on the worker
    - Network topology (rack/zone awareness)
    - Transfer cost estimation
    - Access patterns
    """

    def __init__(
        self,
        config: Optional[LocalityScoringConfig] = None,
        topology: Optional[NetworkTopology] = None,
    ):
        self.config = config or LocalityScoringConfig()
        self.topology = topology or NetworkTopology()

    async def score(
        self,
        job: Job,
        worker: WorkerInfo,
        tracker: DataLocationTracker,
    ) -> LocalityScoreResult:
        """
        Calculate locality score for a worker.
        حساب درجة المحلية لـ worker.
        """
        # Get required data blocks for the job
        required_blocks = await self._get_required_blocks(job, tracker)

        if not required_blocks:
            # No data requirements
            return LocalityScoreResult(
                worker_id=worker.worker_id,
                total_score=1.0,
                locality_level=LocalityLevel.NODE_LOCAL,
            )

        # Analyze block locations
        analysis = await self._analyze_block_locations(
            worker.worker_id,
            required_blocks,
            tracker,
        )

        # Calculate component scores
        local_data_score = self._calculate_local_data_score(analysis)
        transfer_cost_score = self._calculate_transfer_cost_score(analysis)
        access_pattern_score = self._calculate_access_pattern_score(
            required_blocks,
            analysis,
        )

        # Calculate total score
        total_score = (
            local_data_score * self.config.local_data_weight
            + transfer_cost_score * self.config.transfer_cost_weight
            + access_pattern_score * self.config.access_pattern_weight
        )

        # Normalize
        weight_sum = (
            self.config.local_data_weight
            + self.config.transfer_cost_weight
            + self.config.access_pattern_weight
        )
        if weight_sum > 0:
            total_score /= weight_sum

        # Determine best locality level
        best_level = self._determine_best_locality_level(analysis)

        # Estimate transfer time
        transfer_time = self._estimate_transfer_time(analysis)

        return LocalityScoreResult(
            worker_id=worker.worker_id,
            total_score=total_score,
            locality_level=best_level,
            local_data_score=local_data_score,
            transfer_cost_score=transfer_cost_score,
            access_pattern_score=access_pattern_score,
            total_blocks_required=len(required_blocks),
            local_blocks=analysis["local_blocks"],
            rack_local_blocks=analysis["rack_local_blocks"],
            zone_local_blocks=analysis["zone_local_blocks"],
            remote_blocks=analysis["remote_blocks"],
            total_size_bytes=analysis["total_size"],
            local_size_bytes=analysis["local_size"],
            transfer_size_bytes=analysis["transfer_size"],
            estimated_transfer_time_seconds=transfer_time,
        )

    async def score_workers(
        self,
        job: Job,
        workers: List[WorkerInfo],
        tracker: DataLocationTracker,
    ) -> List[LocalityScoreResult]:
        """
        Score multiple workers for locality.
        تسجيل عدة workers للمحلية.
        """
        results = []
        for worker in workers:
            result = await self.score(job, worker, tracker)
            results.append(result)

        # Sort by score (highest first)
        results.sort(key=lambda r: r.total_score, reverse=True)
        return results

    async def find_best_worker(
        self,
        job: Job,
        workers: List[WorkerInfo],
        tracker: DataLocationTracker,
        min_score: float = 0.0,
    ) -> Optional[Tuple[WorkerInfo, LocalityScoreResult]]:
        """
        Find the best worker for a job based on locality.
        إيجاد أفضل worker لـ job بناءً على المحلية.
        """
        best_worker = None
        best_result = None

        for worker in workers:
            result = await self.score(job, worker, tracker)

            if result.total_score >= min_score:
                if best_result is None or result.total_score > best_result.total_score:
                    best_worker = worker
                    best_result = result

        if best_worker and best_result:
            return (best_worker, best_result)
        return None

    # ==================== Helper Methods ====================

    async def _get_required_blocks(
        self,
        job: Job,
        tracker: DataLocationTracker,
    ) -> List[DataBlock]:
        """Get data blocks required by a job."""
        blocks = []

        # Get blocks from job's input files
        if job.submission.input_files:
            for local_path in job.submission.input_files.keys():
                # Try to find block by path or create block ID
                from .tracker import create_block_id

                block_id = create_block_id(local_path, job_id=job.job_id)
                block = await tracker.get_block(block_id)
                if block:
                    blocks.append(block)

        # Get blocks from job metadata
        if "required_blocks" in job.submission.labels:
            block_ids = job.submission.labels["required_blocks"].split(",")
            for block_id in block_ids:
                block_id = block_id.strip()
                if block_id:
                    block = await tracker.get_block(block_id)
                    if block:
                        blocks.append(block)

        # Get job-specific blocks
        job_blocks = await tracker.get_job_input_blocks(job.job_id)
        for block in job_blocks:
            if block not in blocks:
                blocks.append(block)

        return blocks

    async def _analyze_block_locations(
        self,
        target_worker_id: str,
        blocks: List[DataBlock],
        tracker: DataLocationTracker,
    ) -> Dict:
        """Analyze block locations relative to target worker."""
        analysis = {
            "local_blocks": 0,
            "rack_local_blocks": 0,
            "zone_local_blocks": 0,
            "remote_blocks": 0,
            "total_size": 0,
            "local_size": 0,
            "transfer_size": 0,
            "block_levels": {},  # block_id -> LocalityLevel
            "best_locations": {},  # block_id -> (worker_id, level)
        }

        for block in blocks:
            analysis["total_size"] += block.size_bytes

            locations = await tracker.get_locations(block.block_id)

            if not locations:
                analysis["remote_blocks"] += 1
                analysis["transfer_size"] += block.size_bytes
                analysis["block_levels"][block.block_id] = LocalityLevel.REMOTE
                continue

            # Find best location for this block
            best_level = LocalityLevel.REMOTE
            best_worker = None

            for loc in locations:
                if loc.worker_id == target_worker_id:
                    best_level = LocalityLevel.NODE_LOCAL
                    best_worker = loc.worker_id
                    break

                if self.config.topology_aware:
                    level = self.topology.get_locality_level(
                        loc.worker_id,
                        target_worker_id,
                    )
                    if self._level_priority(level) > self._level_priority(best_level):
                        best_level = level
                        best_worker = loc.worker_id

            analysis["block_levels"][block.block_id] = best_level
            analysis["best_locations"][block.block_id] = (best_worker, best_level)

            if best_level == LocalityLevel.NODE_LOCAL:
                analysis["local_blocks"] += 1
                analysis["local_size"] += block.size_bytes
            elif best_level == LocalityLevel.RACK_LOCAL:
                analysis["rack_local_blocks"] += 1
                analysis["transfer_size"] += block.size_bytes
            elif best_level == LocalityLevel.ZONE_LOCAL:
                analysis["zone_local_blocks"] += 1
                analysis["transfer_size"] += block.size_bytes
            else:
                analysis["remote_blocks"] += 1
                analysis["transfer_size"] += block.size_bytes

        return analysis

    def _calculate_local_data_score(self, analysis: Dict) -> float:
        """Calculate score based on local data presence."""
        total = (
            analysis["local_blocks"]
            + analysis["rack_local_blocks"]
            + analysis["zone_local_blocks"]
            + analysis["remote_blocks"]
        )

        if total == 0:
            return 1.0

        weighted_score = (
            analysis["local_blocks"] * self.config.node_local_score
            + analysis["rack_local_blocks"] * self.config.rack_local_score
            + analysis["zone_local_blocks"] * self.config.zone_local_score
            + analysis["remote_blocks"] * self.config.remote_score
        )

        return weighted_score / total

    def _calculate_transfer_cost_score(self, analysis: Dict) -> float:
        """Calculate score based on transfer cost."""
        transfer_mb = analysis["transfer_size"] / (1024 * 1024)

        if transfer_mb <= 0:
            return 1.0

        if transfer_mb <= self.config.low_transfer_threshold_mb:
            # Linear decrease from 1.0 to 0.7
            ratio = transfer_mb / self.config.low_transfer_threshold_mb
            return 1.0 - (0.3 * ratio)
        elif transfer_mb <= self.config.high_transfer_threshold_mb:
            # Linear decrease from 0.7 to 0.2
            range_size = (
                self.config.high_transfer_threshold_mb
                - self.config.low_transfer_threshold_mb
            )
            ratio = (transfer_mb - self.config.low_transfer_threshold_mb) / range_size
            return 0.7 - (0.5 * ratio)
        else:
            # Exponential decrease below 0.2
            excess = transfer_mb / self.config.high_transfer_threshold_mb
            return max(0.01, 0.2 / excess)

    def _calculate_access_pattern_score(
        self,
        blocks: List[DataBlock],
        analysis: Dict,
    ) -> float:
        """Calculate score based on access patterns."""
        if not blocks:
            return 0.5

        total_access = 0
        weighted_local_access = 0

        for block in blocks:
            access_count = block.access_count
            total_access += access_count

            level = analysis["block_levels"].get(block.block_id, LocalityLevel.REMOTE)

            if level == LocalityLevel.NODE_LOCAL:
                weighted_local_access += access_count

        if total_access < self.config.min_access_for_bonus:
            return 0.5  # Neutral - not enough data

        access_ratio = weighted_local_access / total_access
        bonus = access_ratio * self.config.access_bonus_weight

        return min(1.0, 0.5 + bonus)

    def _determine_best_locality_level(self, analysis: Dict) -> LocalityLevel:
        """Determine the best locality level achieved."""
        if analysis["local_blocks"] > 0:
            if (
                analysis["rack_local_blocks"] == 0
                and analysis["zone_local_blocks"] == 0
                and analysis["remote_blocks"] == 0
            ):
                return LocalityLevel.NODE_LOCAL
            return LocalityLevel.RACK_LOCAL

        if analysis["rack_local_blocks"] > 0:
            return LocalityLevel.RACK_LOCAL

        if analysis["zone_local_blocks"] > 0:
            return LocalityLevel.ZONE_LOCAL

        return LocalityLevel.REMOTE

    def _estimate_transfer_time(self, analysis: Dict) -> float:
        """Estimate total transfer time in seconds."""
        transfer_time = 0.0

        for block_id, (worker_id, level) in analysis.get("best_locations", {}).items():
            if level == LocalityLevel.NODE_LOCAL:
                continue

            # Get block size (simplified - would need actual block)
            block_size_mb = analysis["transfer_size"] / (1024 * 1024)
            bandwidth = self.topology.get_bandwidth(level)
            latency = self.topology.get_latency(level) / 1000  # Convert to seconds

            transfer_time += latency + (block_size_mb / (bandwidth / 8))

        return transfer_time

    def _level_priority(self, level: LocalityLevel) -> int:
        """Get priority for locality level (higher = better)."""
        return {
            LocalityLevel.NODE_LOCAL: 4,
            LocalityLevel.RACK_LOCAL: 3,
            LocalityLevel.ZONE_LOCAL: 2,
            LocalityLevel.REMOTE: 1,
        }.get(level, 0)


class SimpleLocalityScorer(LocalityScorerBase):
    """
    Simple locality scorer for basic use cases.
    مسجّل محلية بسيط للحالات الأساسية.
    """

    def __init__(self, local_bonus: float = 0.5):
        self.local_bonus = local_bonus

    async def score(
        self,
        job: Job,
        worker: WorkerInfo,
        tracker: DataLocationTracker,
    ) -> LocalityScoreResult:
        """Simple scoring based on local data presence."""
        # Get required block IDs from job labels
        required_blocks = []
        if "required_blocks" in job.submission.labels:
            required_blocks = [
                b.strip()
                for b in job.submission.labels["required_blocks"].split(",")
                if b.strip()
            ]

        if not required_blocks:
            return LocalityScoreResult(
                worker_id=worker.worker_id,
                total_score=0.5,
                locality_level=LocalityLevel.NODE_LOCAL,
            )

        # Calculate simple locality score
        score = await tracker.calculate_locality_score(
            worker.worker_id,
            required_blocks,
        )

        # Apply bonus
        score = score * (1 + self.local_bonus)
        score = min(1.0, score)

        return LocalityScoreResult(
            worker_id=worker.worker_id,
            total_score=score,
            locality_level=(
                LocalityLevel.NODE_LOCAL if score > 0.7 else LocalityLevel.REMOTE
            ),
            local_data_score=score,
            total_blocks_required=len(required_blocks),
        )


class CompositeLocalityScorer(LocalityScorerBase):
    """
    Composite scorer combining multiple scoring strategies.
    مسجّل مركب يجمع عدة استراتيجيات تسجيل.
    """

    def __init__(self):
        self.scorers: List[Tuple[LocalityScorerBase, float]] = []

    def add_scorer(self, scorer: LocalityScorerBase, weight: float = 1.0) -> None:
        """Add a scorer with a weight."""
        self.scorers.append((scorer, weight))

    async def score(
        self,
        job: Job,
        worker: WorkerInfo,
        tracker: DataLocationTracker,
    ) -> LocalityScoreResult:
        """Calculate combined score from all scorers."""
        if not self.scorers:
            return LocalityScoreResult(
                worker_id=worker.worker_id,
                total_score=0.5,
                locality_level=LocalityLevel.NODE_LOCAL,
            )

        total_weight = sum(w for _, w in self.scorers)
        weighted_score = 0.0
        best_level = LocalityLevel.REMOTE

        for scorer, weight in self.scorers:
            result = await scorer.score(job, worker, tracker)
            weighted_score += result.total_score * weight

            if self._level_priority(result.locality_level) > self._level_priority(
                best_level
            ):
                best_level = result.locality_level

        final_score = weighted_score / total_weight if total_weight > 0 else 0.5

        return LocalityScoreResult(
            worker_id=worker.worker_id,
            total_score=final_score,
            locality_level=best_level,
        )

    def _level_priority(self, level: LocalityLevel) -> int:
        """Get priority for locality level."""
        return {
            LocalityLevel.NODE_LOCAL: 4,
            LocalityLevel.RACK_LOCAL: 3,
            LocalityLevel.ZONE_LOCAL: 2,
            LocalityLevel.REMOTE: 1,
        }.get(level, 0)
