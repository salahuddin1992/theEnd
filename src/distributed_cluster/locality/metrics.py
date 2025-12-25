"""
Locality Metrics - مقاييس المحلية
===================================

Metrics and monitoring for data locality system.
مقاييس ومراقبة لنظام محلية البيانات.

Features:
- Locality efficiency tracking
- Transfer statistics
- Worker data distribution
- Scheduling effectiveness
- Real-time dashboards
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from .tracker import DataBlock, DataLocation, DataLocationTracker, DataType
from .scorer import LocalityLevel, LocalityScoreResult
from .transfer import TransferProgress, TransferResult, TransferState

logger = logging.getLogger(__name__)


@dataclass
class LocalityMetrics:
    """
    Aggregated locality metrics.
    مقاييس المحلية المجمعة.
    """

    # Time window
    window_start: datetime = field(default_factory=datetime.utcnow)
    window_end: Optional[datetime] = None

    # Block metrics
    total_blocks: int = 0
    total_size_bytes: int = 0
    blocks_by_type: Dict[str, int] = field(default_factory=dict)

    # Location metrics
    total_replicas: int = 0
    primary_replicas: int = 0
    healthy_replicas: int = 0
    stale_replicas: int = 0

    # Distribution metrics
    workers_with_data: int = 0
    avg_blocks_per_worker: float = 0.0
    max_blocks_on_worker: int = 0
    min_blocks_on_worker: int = 0
    distribution_variance: float = 0.0

    # Locality metrics
    scheduling_decisions: int = 0
    perfect_locality_decisions: int = 0
    rack_local_decisions: int = 0
    remote_decisions: int = 0

    # Transfer metrics
    total_transfers: int = 0
    successful_transfers: int = 0
    failed_transfers: int = 0
    total_bytes_transferred: int = 0
    avg_transfer_time_seconds: float = 0.0

    @property
    def locality_rate(self) -> float:
        """Percentage of scheduling decisions with perfect locality."""
        if self.scheduling_decisions == 0:
            return 0.0
        return self.perfect_locality_decisions / self.scheduling_decisions

    @property
    def transfer_success_rate(self) -> float:
        """Percentage of successful transfers."""
        if self.total_transfers == 0:
            return 0.0
        return self.successful_transfers / self.total_transfers

    @property
    def replica_health_rate(self) -> float:
        """Percentage of healthy replicas."""
        if self.total_replicas == 0:
            return 0.0
        return self.healthy_replicas / self.total_replicas

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "total_blocks": self.total_blocks,
            "total_size_bytes": self.total_size_bytes,
            "total_size_gb": self.total_size_bytes / (1024 ** 3),
            "blocks_by_type": self.blocks_by_type,
            "total_replicas": self.total_replicas,
            "primary_replicas": self.primary_replicas,
            "healthy_replicas": self.healthy_replicas,
            "stale_replicas": self.stale_replicas,
            "replica_health_rate": self.replica_health_rate,
            "workers_with_data": self.workers_with_data,
            "avg_blocks_per_worker": self.avg_blocks_per_worker,
            "max_blocks_on_worker": self.max_blocks_on_worker,
            "min_blocks_on_worker": self.min_blocks_on_worker,
            "distribution_variance": self.distribution_variance,
            "scheduling_decisions": self.scheduling_decisions,
            "perfect_locality_decisions": self.perfect_locality_decisions,
            "locality_rate": self.locality_rate,
            "rack_local_decisions": self.rack_local_decisions,
            "remote_decisions": self.remote_decisions,
            "total_transfers": self.total_transfers,
            "successful_transfers": self.successful_transfers,
            "failed_transfers": self.failed_transfers,
            "transfer_success_rate": self.transfer_success_rate,
            "total_bytes_transferred": self.total_bytes_transferred,
            "avg_transfer_time_seconds": self.avg_transfer_time_seconds,
        }


@dataclass
class WorkerDataMetrics:
    """
    Per-worker data metrics.
    مقاييس البيانات لكل worker.
    """

    worker_id: str
    total_blocks: int = 0
    total_size_bytes: int = 0
    primary_blocks: int = 0
    replica_blocks: int = 0

    # By type
    blocks_by_type: Dict[str, int] = field(default_factory=dict)

    # Health
    healthy_blocks: int = 0
    stale_blocks: int = 0

    # Access patterns
    total_accesses: int = 0
    avg_access_rate: float = 0.0  # Accesses per minute

    # Transfers
    incoming_transfers: int = 0
    outgoing_transfers: int = 0
    transfer_bytes_in: int = 0
    transfer_bytes_out: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "worker_id": self.worker_id,
            "total_blocks": self.total_blocks,
            "total_size_bytes": self.total_size_bytes,
            "total_size_gb": self.total_size_bytes / (1024 ** 3),
            "primary_blocks": self.primary_blocks,
            "replica_blocks": self.replica_blocks,
            "blocks_by_type": self.blocks_by_type,
            "healthy_blocks": self.healthy_blocks,
            "stale_blocks": self.stale_blocks,
            "total_accesses": self.total_accesses,
            "avg_access_rate": self.avg_access_rate,
            "incoming_transfers": self.incoming_transfers,
            "outgoing_transfers": self.outgoing_transfers,
            "transfer_bytes_in": self.transfer_bytes_in,
            "transfer_bytes_out": self.transfer_bytes_out,
        }


@dataclass
class SchedulingMetrics:
    """
    Scheduling-specific metrics.
    مقاييس الجدولة.
    """

    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Decision counts
    total_decisions: int = 0
    decisions_by_locality: Dict[str, int] = field(default_factory=dict)

    # Delay scheduling
    delayed_jobs: int = 0
    total_delay_seconds: float = 0.0
    avg_delay_seconds: float = 0.0

    # Transfer requirements
    decisions_requiring_transfer: int = 0
    total_transfer_for_scheduling_bytes: int = 0

    # Scores
    avg_locality_score: float = 0.0
    min_locality_score: float = 0.0
    max_locality_score: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_decisions": self.total_decisions,
            "decisions_by_locality": self.decisions_by_locality,
            "delayed_jobs": self.delayed_jobs,
            "total_delay_seconds": self.total_delay_seconds,
            "avg_delay_seconds": self.avg_delay_seconds,
            "decisions_requiring_transfer": self.decisions_requiring_transfer,
            "total_transfer_for_scheduling_bytes": self.total_transfer_for_scheduling_bytes,
            "avg_locality_score": self.avg_locality_score,
            "min_locality_score": self.min_locality_score,
            "max_locality_score": self.max_locality_score,
        }


class LocalityMetricsCollector:
    """
    Collects and aggregates locality metrics.
    يجمع ويُجمّع مقاييس المحلية.
    """

    def __init__(
        self,
        tracker: DataLocationTracker,
        collection_interval_seconds: float = 60.0,
        history_size: int = 60,  # Keep 1 hour of metrics
    ):
        self.tracker = tracker
        self.collection_interval_seconds = collection_interval_seconds
        self.history_size = history_size

        # Metrics storage
        self._metrics_history: List[LocalityMetrics] = []
        self._scheduling_history: List[SchedulingMetrics] = []
        self._worker_metrics: Dict[str, WorkerDataMetrics] = {}

        # Real-time counters
        self._scheduling_decisions = 0
        self._locality_decisions: Dict[str, int] = defaultdict(int)
        self._transfer_count = 0
        self._transfer_bytes = 0
        self._transfer_time_total = 0.0
        self._locality_scores: List[float] = []

        # Background task
        self._running = False
        self._collection_task: Optional[asyncio.Task] = None

        # Callbacks for real-time updates
        self._on_metrics_collected: List[Callable] = []

    async def start(self) -> None:
        """Start the metrics collector."""
        if self._running:
            return

        self._running = True
        self._collection_task = asyncio.create_task(self._collection_loop())

        logger.info("LocalityMetricsCollector started")

    async def stop(self) -> None:
        """Stop the metrics collector."""
        self._running = False

        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass

        logger.info("LocalityMetricsCollector stopped")

    # ==================== Event Recording ====================

    def record_scheduling_decision(
        self,
        locality_level: LocalityLevel,
        locality_score: float,
        required_transfer: bool = False,
        transfer_bytes: int = 0,
        delay_seconds: float = 0.0,
    ) -> None:
        """Record a scheduling decision."""
        self._scheduling_decisions += 1
        self._locality_decisions[locality_level.value] += 1
        self._locality_scores.append(locality_score)

        if required_transfer:
            self._transfer_count += 1
            self._transfer_bytes += transfer_bytes

    def record_transfer_complete(
        self,
        result: TransferResult,
    ) -> None:
        """Record a completed transfer."""
        if result.success:
            self._transfer_time_total += result.transfer_time_seconds

    # ==================== Metrics Collection ====================

    async def collect_metrics(self) -> LocalityMetrics:
        """Collect current locality metrics."""
        metrics = LocalityMetrics(window_start=datetime.utcnow())

        # Get tracker stats
        tracker_stats = await self.tracker.get_stats()

        metrics.total_blocks = tracker_stats["total_blocks"]
        metrics.total_size_bytes = tracker_stats["total_size_bytes"]
        metrics.total_replicas = tracker_stats["total_locations"]
        metrics.workers_with_data = tracker_stats["total_workers"]

        # Block type distribution
        metrics.blocks_by_type = tracker_stats.get("type_counts", {})

        # Calculate distribution metrics
        await self._calculate_distribution_metrics(metrics)

        # Scheduling metrics
        metrics.scheduling_decisions = self._scheduling_decisions
        metrics.perfect_locality_decisions = self._locality_decisions.get(
            LocalityLevel.NODE_LOCAL.value, 0
        )
        metrics.rack_local_decisions = self._locality_decisions.get(
            LocalityLevel.RACK_LOCAL.value, 0
        )
        metrics.remote_decisions = self._locality_decisions.get(
            LocalityLevel.REMOTE.value, 0
        )

        # Transfer metrics
        metrics.total_transfers = self._transfer_count
        if self._transfer_count > 0:
            metrics.avg_transfer_time_seconds = (
                self._transfer_time_total / self._transfer_count
            )
        metrics.total_bytes_transferred = self._transfer_bytes

        metrics.window_end = datetime.utcnow()

        # Store in history
        self._metrics_history.append(metrics)
        if len(self._metrics_history) > self.history_size:
            self._metrics_history.pop(0)

        # Fire callbacks
        for callback in self._on_metrics_collected:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(metrics)
                else:
                    callback(metrics)
            except Exception as e:
                logger.error(f"Metrics callback error: {e}")

        return metrics

    async def collect_worker_metrics(
        self,
        worker_id: str,
    ) -> WorkerDataMetrics:
        """Collect metrics for a specific worker."""
        metrics = WorkerDataMetrics(worker_id=worker_id)

        # Get blocks on worker
        blocks = await self.tracker.get_worker_blocks(worker_id)

        for block in blocks:
            metrics.total_blocks += 1
            metrics.total_size_bytes += block.size_bytes
            metrics.total_accesses += block.access_count

            # By type
            type_name = block.data_type.value
            if type_name not in metrics.blocks_by_type:
                metrics.blocks_by_type[type_name] = 0
            metrics.blocks_by_type[type_name] += 1

        # Get location info
        locality_info = await self.tracker.get_worker_locality_info(worker_id)
        metrics.primary_blocks = locality_info.primary_replicas
        metrics.replica_blocks = metrics.total_blocks - metrics.primary_blocks

        self._worker_metrics[worker_id] = metrics
        return metrics

    async def _calculate_distribution_metrics(
        self,
        metrics: LocalityMetrics,
    ) -> None:
        """Calculate data distribution metrics."""
        # This would need access to worker block counts
        # For now, we'll use estimates based on total counts

        if metrics.workers_with_data > 0:
            metrics.avg_blocks_per_worker = (
                metrics.total_blocks / metrics.workers_with_data
            )

        # Would need actual per-worker counts for variance
        # This is a placeholder
        metrics.distribution_variance = 0.0

    async def _collection_loop(self) -> None:
        """Background collection loop."""
        while self._running:
            try:
                await asyncio.sleep(self.collection_interval_seconds)
                await self.collect_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics collection error: {e}")

    # ==================== Metric Retrieval ====================

    def get_current_metrics(self) -> Optional[LocalityMetrics]:
        """Get the most recent metrics."""
        if self._metrics_history:
            return self._metrics_history[-1]
        return None

    def get_metrics_history(
        self,
        count: Optional[int] = None,
    ) -> List[LocalityMetrics]:
        """Get metrics history."""
        if count:
            return self._metrics_history[-count:]
        return self._metrics_history.copy()

    def get_worker_metrics(
        self,
        worker_id: str,
    ) -> Optional[WorkerDataMetrics]:
        """Get cached metrics for a worker."""
        return self._worker_metrics.get(worker_id)

    def get_all_worker_metrics(self) -> Dict[str, WorkerDataMetrics]:
        """Get metrics for all workers."""
        return self._worker_metrics.copy()

    def get_scheduling_metrics(self) -> SchedulingMetrics:
        """Get current scheduling metrics."""
        metrics = SchedulingMetrics()
        metrics.total_decisions = self._scheduling_decisions
        metrics.decisions_by_locality = dict(self._locality_decisions)

        if self._locality_scores:
            metrics.avg_locality_score = sum(self._locality_scores) / len(
                self._locality_scores
            )
            metrics.min_locality_score = min(self._locality_scores)
            metrics.max_locality_score = max(self._locality_scores)

        return metrics

    # ==================== Aggregations ====================

    async def get_locality_summary(self) -> Dict:
        """Get a summary of locality effectiveness."""
        current = self.get_current_metrics()
        scheduling = self.get_scheduling_metrics()

        return {
            "overall_locality_rate": current.locality_rate if current else 0.0,
            "avg_locality_score": scheduling.avg_locality_score,
            "data_distribution": {
                "total_blocks": current.total_blocks if current else 0,
                "total_size_gb": (
                    current.total_size_bytes / (1024 ** 3) if current else 0
                ),
                "workers": current.workers_with_data if current else 0,
                "replica_health": current.replica_health_rate if current else 0.0,
            },
            "scheduling": {
                "decisions": scheduling.total_decisions,
                "perfect_locality": self._locality_decisions.get(
                    LocalityLevel.NODE_LOCAL.value, 0
                ),
                "rack_local": self._locality_decisions.get(
                    LocalityLevel.RACK_LOCAL.value, 0
                ),
                "remote": self._locality_decisions.get(LocalityLevel.REMOTE.value, 0),
            },
            "transfers": {
                "total": current.total_transfers if current else 0,
                "success_rate": current.transfer_success_rate if current else 0.0,
                "total_bytes": current.total_bytes_transferred if current else 0,
            },
        }

    async def get_trend_analysis(
        self,
        metric_name: str,
        window_size: int = 10,
    ) -> Dict:
        """Analyze trend for a specific metric."""
        if len(self._metrics_history) < 2:
            return {"trend": "unknown", "change": 0.0}

        recent = self._metrics_history[-window_size:]
        values = []

        for m in recent:
            value = getattr(m, metric_name, None)
            if value is not None:
                values.append(value)

        if len(values) < 2:
            return {"trend": "unknown", "change": 0.0}

        # Simple trend analysis
        first_half = sum(values[: len(values) // 2]) / (len(values) // 2)
        second_half = sum(values[len(values) // 2 :]) / (
            len(values) - len(values) // 2
        )

        change = (second_half - first_half) / max(first_half, 0.001)

        if change > 0.1:
            trend = "improving"
        elif change < -0.1:
            trend = "degrading"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "change": change,
            "current_value": values[-1],
            "avg_value": sum(values) / len(values),
        }

    # ==================== Callbacks ====================

    def on_metrics_collected(self, callback: Callable) -> None:
        """Register callback for metrics collection."""
        self._on_metrics_collected.append(callback)

    # ==================== Reset ====================

    def reset_counters(self) -> None:
        """Reset real-time counters."""
        self._scheduling_decisions = 0
        self._locality_decisions.clear()
        self._transfer_count = 0
        self._transfer_bytes = 0
        self._transfer_time_total = 0.0
        self._locality_scores.clear()


class LocalityDashboard:
    """
    Dashboard for locality metrics visualization.
    لوحة تحكم لعرض مقاييس المحلية.
    """

    def __init__(self, collector: LocalityMetricsCollector):
        self.collector = collector

    async def get_dashboard_data(self) -> Dict:
        """Get data for dashboard display."""
        summary = await self.collector.get_locality_summary()
        current = self.collector.get_current_metrics()
        scheduling = self.collector.get_scheduling_metrics()

        # Locality trend
        locality_trend = await self.collector.get_trend_analysis("locality_rate")

        # Build dashboard data
        return {
            "summary": summary,
            "current_metrics": current.to_dict() if current else None,
            "scheduling_metrics": scheduling.to_dict(),
            "trends": {
                "locality": locality_trend,
            },
            "charts": {
                "locality_distribution": self._build_locality_chart(),
                "block_types": current.blocks_by_type if current else {},
            },
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _build_locality_chart(self) -> List[Dict]:
        """Build data for locality distribution chart."""
        history = self.collector.get_metrics_history(10)

        chart_data = []
        for m in history:
            chart_data.append(
                {
                    "timestamp": m.window_start.isoformat(),
                    "locality_rate": m.locality_rate,
                    "transfer_rate": (
                        m.total_transfers / max(m.scheduling_decisions, 1)
                    ),
                }
            )

        return chart_data

    async def get_worker_ranking(self) -> List[Dict]:
        """Get workers ranked by data metrics."""
        all_metrics = self.collector.get_all_worker_metrics()

        ranked = sorted(
            all_metrics.values(),
            key=lambda m: m.total_size_bytes,
            reverse=True,
        )

        return [m.to_dict() for m in ranked[:10]]

    async def get_alerts(self) -> List[Dict]:
        """Get current alerts based on metrics."""
        alerts = []
        current = self.collector.get_current_metrics()

        if not current:
            return alerts

        # Low locality rate alert
        if current.locality_rate < 0.5:
            alerts.append(
                {
                    "level": "warning",
                    "message": f"Low locality rate: {current.locality_rate:.1%}",
                    "metric": "locality_rate",
                    "value": current.locality_rate,
                }
            )

        # High transfer rate
        if current.scheduling_decisions > 0:
            transfer_rate = current.total_transfers / current.scheduling_decisions
            if transfer_rate > 0.5:
                alerts.append(
                    {
                        "level": "warning",
                        "message": f"High transfer rate: {transfer_rate:.1%} of jobs require transfers",
                        "metric": "transfer_rate",
                        "value": transfer_rate,
                    }
                )

        # Poor replica health
        if current.replica_health_rate < 0.9:
            alerts.append(
                {
                    "level": "critical" if current.replica_health_rate < 0.7 else "warning",
                    "message": f"Replica health below target: {current.replica_health_rate:.1%}",
                    "metric": "replica_health_rate",
                    "value": current.replica_health_rate,
                }
            )

        return alerts
