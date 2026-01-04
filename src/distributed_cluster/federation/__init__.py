"""
Multi-Cluster Federation - اتحاد الكتل المتعددة
=================================================

Federation System
-----------------

This module provides multi-cluster federation capabilities:
- Link multiple clusters together
- Distribute tasks across clusters
- Synchronize state between clusters
- Cross-cluster job routing
- Global resource management

يوفر هذا النظام إمكانيات اتحاد الكتل المتعددة:
- ربط عدة كتل معاً
- توزيع المهام بين الكتل
- مزامنة الحالة بين الكتل
- توجيه المهام عبر الكتل
- إدارة الموارد العالمية

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.federation.cluster import (
    ClusterCapacity,
    ClusterInfo,
    ClusterStatus,
    FederatedCluster,
)
from distributed_cluster.federation.discovery import (
    ClusterDiscovery,
    DiscoveryConfig,
)
from distributed_cluster.federation.manager import (
    FederationConfig,
    FederationManager,
)
from distributed_cluster.federation.router import (
    JobRouter,
    RoutingPolicy,
    RoutingResult,
)
from distributed_cluster.federation.sync import (
    StateSync,
    SyncConfig,
    SyncResult,
)

__all__ = [
    # Cluster
    "FederatedCluster",
    "ClusterInfo",
    "ClusterStatus",
    "ClusterCapacity",
    # Manager
    "FederationManager",
    "FederationConfig",
    # Router
    "JobRouter",
    "RoutingPolicy",
    "RoutingResult",
    # Sync
    "StateSync",
    "SyncConfig",
    "SyncResult",
    # Discovery
    "ClusterDiscovery",
    "DiscoveryConfig",
]
