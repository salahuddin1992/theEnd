"""
Data Locality Scheduling System - نظام جدولة محلية البيانات
==========================================================

A comprehensive data locality scheduling system for distributed clusters.
نظام شامل لجدولة محلية البيانات للكلاسترات الموزعة.

This module provides:
- **Data Location Tracking**: Track where data blocks are stored across workers
- **Locality Scoring**: Score workers based on data locality for scheduling
- **Placement Strategies**: Intelligent data placement across the cluster
- **Locality-Aware Scheduling**: Schedule jobs near their data
- **Data Transfer Management**: Efficient data movement between workers
- **Metrics & Monitoring**: Track locality effectiveness

Key Concepts:
- **Data Block**: A unit of data (file, chunk, model, dataset)
- **Data Location**: Where a block replica is stored
- **Locality Level**: How close data is (node-local, rack-local, zone-local, remote)
- **Placement Strategy**: How to decide where to place data
- **Delay Scheduling**: Wait for better locality before scheduling

Example Usage:
    ```python
    from distributed_cluster.locality import (
        DataLocationTracker,
        LocalityAwareScheduler,
        DataPlacementManager,
        DataTransferManager,
        LocalityMetricsCollector,
    )

    # Initialize components
    tracker = DataLocationTracker()
    await tracker.start()

    # Register data blocks
    block = DataBlock(
        block_id="block-001",
        data_type=DataType.DATASET,
        size_bytes=1024 * 1024 * 100,  # 100MB
    )
    await tracker.register_block(block)

    # Add location
    await tracker.add_location(
        block_id="block-001",
        worker_id="worker-1",
        local_path="/data/block-001",
        is_primary=True,
    )

    # Create locality-aware scheduler
    scheduler = LocalityAwareScheduler(tracker)

    # Schedule jobs with locality awareness
    decisions = await scheduler.schedule(pending_jobs, workers)
    ```

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                    Locality System                       │
    ├─────────────────────────────────────────────────────────┤
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
    │  │   Tracker   │  │   Scorer    │  │    Placement    │  │
    │  │  (tracker)  │◄─┤  (scorer)   │  │   (placement)   │  │
    │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │
    │         │                │                   │          │
    │         ▼                ▼                   ▼          │
    │  ┌─────────────────────────────────────────────────────┐│
    │  │           Locality-Aware Scheduler                  ││
    │  │                (scheduler)                           ││
    │  └────────────────────┬────────────────────────────────┘│
    │                       │                                  │
    │         ┌─────────────┴─────────────┐                   │
    │         ▼                           ▼                   │
    │  ┌─────────────┐             ┌─────────────┐            │
    │  │  Transfer   │             │   Metrics   │            │
    │  │ (transfer)  │             │  (metrics)  │            │
    │  └─────────────┘             └─────────────┘            │
    └─────────────────────────────────────────────────────────┘

Author: NebulaCompute Team
License: MIT
Version: 1.0.0
"""

from __future__ import annotations

# ==================== Metrics Module ====================
from .metrics import (
    # Dashboard
    LocalityDashboard,
    # Metrics classes
    LocalityMetrics,
    # Collector
    LocalityMetricsCollector,
    SchedulingMetrics,
    WorkerDataMetrics,
)

# ==================== Placement Module ====================
from .placement import (
    AffinityBasedPlacementStrategy,
    ColocatePlacementStrategy,
    # Manager
    DataPlacementManager,
    LoadBalancedPlacementStrategy,
    MinimizeTransferPlacementStrategy,
    # Config classes
    PlacementConfig,
    # Data classes
    PlacementDecision,
    # Enums
    PlacementStrategy,
    # Strategy classes
    PlacementStrategyBase,
    RackAwarePlacementStrategy,
    RandomPlacementStrategy,
    RoundRobinPlacementStrategy,
    WorkerCapacity,
)

# ==================== Scheduler Module ====================
from .scheduler import (
    # Scheduler
    LocalityAwareScheduler,
    LocalitySchedulerLoop,
    # Config classes
    LocalitySchedulingConfig,
    # Decision classes
    LocalitySchedulingDecision,
    # Enums
    LocalitySchedulingPolicy,
    WorkerLocalityScore,
    # Helper functions
    create_locality_scheduler,
    locality_scheduling_plugin,
)

# ==================== Scorer Module ====================
from .scorer import (
    CompositeLocalityScorer,
    # Enums
    LocalityLevel,
    # Config classes
    LocalityPreference,
    LocalityScorer,
    # Scorers
    LocalityScorerBase,
    # Result classes
    LocalityScoreResult,
    LocalityScoringConfig,
    NetworkTopology,
    SimpleLocalityScorer,
)

# ==================== Tracker Module ====================
from .tracker import (
    # Data classes
    DataBlock,
    DataLocation,
    # Main tracker
    DataLocationTracker,
    # Enums
    DataType,
    LocalityInfo,
    ReplicaState,
    # Helper functions
    create_block_id,
    estimate_transfer_time,
)

# ==================== Transfer Module ====================
from .transfer import (
    # Manager
    DataTransferManager,
    SimulatedTransferHandler,
    # Config
    TransferConfig,
    # Handlers
    TransferHandler,
    TransferPriority,
    TransferProgress,
    # Data classes
    TransferRequest,
    TransferResult,
    # Enums
    TransferState,
)

# ==================== Factory Functions ====================


async def create_locality_system(
    enable_transfers: bool = True,
    enable_metrics: bool = True,
    topology: NetworkTopology | None = None,
) -> dict:
    """
    Create a complete locality system with all components.
    إنشاء نظام محلية كامل مع جميع المكونات.

    Args:
        enable_transfers: Whether to enable transfer manager
        enable_metrics: Whether to enable metrics collection
        topology: Optional network topology configuration

    Returns:
        Dictionary with all initialized components

    Example:
        ```python
        system = await create_locality_system()

        tracker = system["tracker"]
        scheduler = system["scheduler"]
        placement = system["placement"]
        transfer = system["transfer"]
        metrics = system["metrics"]

        # Start all components
        await system["start"]()

        # Stop all components
        await system["stop"]()
        ```
    """
    topology = topology or NetworkTopology()

    # Create tracker
    tracker = DataLocationTracker()
    await tracker.start()

    # Create placement manager
    placement = DataPlacementManager(
        tracker=tracker,
        topology=topology,
    )

    # Create scheduler
    scheduler = LocalityAwareScheduler(
        tracker=tracker,
        topology=topology,
    )

    # Create transfer manager
    transfer = None
    if enable_transfers:
        transfer = DataTransferManager(
            tracker=tracker,
            topology=topology,
        )
        await transfer.start()

    # Create metrics collector
    metrics = None
    if enable_metrics:
        metrics = LocalityMetricsCollector(tracker=tracker)
        await metrics.start()

    async def start_all():
        """Start all components."""
        if not tracker._running:
            await tracker.start()
        if transfer and not transfer._running:
            await transfer.start()
        if metrics and not metrics._running:
            await metrics.start()

    async def stop_all():
        """Stop all components."""
        if metrics and metrics._running:
            await metrics.stop()
        if transfer and transfer._running:
            await transfer.stop()
        if tracker._running:
            await tracker.stop()

    return {
        "tracker": tracker,
        "placement": placement,
        "scheduler": scheduler,
        "transfer": transfer,
        "metrics": metrics,
        "topology": topology,
        "start": start_all,
        "stop": stop_all,
    }


def get_locality_config_template() -> dict:
    """
    Get a configuration template for the locality system.
    الحصول على قالب إعدادات لنظام المحلية.

    Returns a dictionary with all configurable options and their defaults.
    """
    return {
        "tracker": {
            "stale_threshold_seconds": 300.0,
            "cleanup_interval_seconds": 60.0,
            "enable_background_cleanup": True,
        },
        "scoring": {
            "local_data_weight": 0.5,
            "transfer_cost_weight": 0.3,
            "access_pattern_weight": 0.2,
            "node_local_score": 1.0,
            "rack_local_score": 0.7,
            "zone_local_score": 0.4,
            "remote_score": 0.1,
        },
        "placement": {
            "replication_factor": 2,
            "min_replicas": 1,
            "max_replicas_per_rack": 2,
            "prefer_same_rack": True,
            "prefer_same_zone": True,
        },
        "scheduling": {
            "policy": "balanced",
            "locality_weight": 0.4,
            "resource_weight": 0.3,
            "load_weight": 0.2,
            "enable_delay_scheduling": True,
            "max_delay_seconds": 30.0,
            "min_locality_score": 0.3,
        },
        "transfer": {
            "max_concurrent_transfers": 5,
            "max_transfers_per_worker": 2,
            "max_retries": 3,
            "verify_checksums": True,
            "enable_compression": False,
        },
        "metrics": {
            "collection_interval_seconds": 60.0,
            "history_size": 60,
        },
        "topology": {
            "intra_node_bandwidth_mbps": 10000.0,
            "intra_rack_bandwidth_mbps": 1000.0,
            "intra_zone_bandwidth_mbps": 500.0,
            "inter_zone_bandwidth_mbps": 100.0,
        },
    }


# ==================== Module Exports ====================

__all__ = [
    # Tracker
    "DataType",
    "ReplicaState",
    "DataBlock",
    "DataLocation",
    "LocalityInfo",
    "DataLocationTracker",
    "create_block_id",
    "estimate_transfer_time",
    # Scorer
    "LocalityLevel",
    "LocalityPreference",
    "NetworkTopology",
    "LocalityScoringConfig",
    "LocalityScoreResult",
    "LocalityScorerBase",
    "LocalityScorer",
    "SimpleLocalityScorer",
    "CompositeLocalityScorer",
    # Placement
    "PlacementStrategy",
    "PlacementConfig",
    "PlacementDecision",
    "WorkerCapacity",
    "PlacementStrategyBase",
    "RandomPlacementStrategy",
    "RoundRobinPlacementStrategy",
    "LoadBalancedPlacementStrategy",
    "RackAwarePlacementStrategy",
    "AffinityBasedPlacementStrategy",
    "ColocatePlacementStrategy",
    "MinimizeTransferPlacementStrategy",
    "DataPlacementManager",
    # Scheduler
    "LocalitySchedulingPolicy",
    "LocalitySchedulingConfig",
    "LocalitySchedulingDecision",
    "WorkerLocalityScore",
    "LocalityAwareScheduler",
    "LocalitySchedulerLoop",
    "create_locality_scheduler",
    "locality_scheduling_plugin",
    # Transfer
    "TransferState",
    "TransferPriority",
    "TransferRequest",
    "TransferProgress",
    "TransferResult",
    "TransferConfig",
    "TransferHandler",
    "SimulatedTransferHandler",
    "DataTransferManager",
    # Metrics
    "LocalityMetrics",
    "WorkerDataMetrics",
    "SchedulingMetrics",
    "LocalityMetricsCollector",
    "LocalityDashboard",
    # Factory functions
    "create_locality_system",
    "get_locality_config_template",
]

__version__ = "1.0.0"
__author__ = "NebulaCompute Team"
