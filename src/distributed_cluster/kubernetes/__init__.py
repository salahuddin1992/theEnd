"""
Kubernetes Operator - مشغّل Kubernetes
======================================

Kubernetes Operator Module
--------------------------

This module provides Kubernetes integration for the distributed cluster:
- Custom Resource Definitions (CRDs)
- Kubernetes Controller for automatic management
- Helm Charts for deployment
- Health monitoring and auto-recovery

يوفر هذا النظام تكامل Kubernetes للكلاستر الموزع:
- تعريفات الموارد المخصصة
- متحكم للإدارة التلقائية
- رسوم Helm للنشر
- مراقبة الصحة والتعافي التلقائي

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.kubernetes.crds import (
    ClusterCRD,
    WorkerCRD,
    JobCRD,
    CRDManager,
)
from distributed_cluster.kubernetes.controller import (
    ClusterController,
    ControllerConfig,
    ReconcileResult,
)
from distributed_cluster.kubernetes.operator import (
    ClusterOperator,
    OperatorConfig,
)
from distributed_cluster.kubernetes.health import (
    HealthMonitor,
    HealthStatus,
    RecoveryAction,
)

__all__ = [
    # CRDs
    "ClusterCRD",
    "WorkerCRD",
    "JobCRD",
    "CRDManager",
    # Controller
    "ClusterController",
    "ControllerConfig",
    "ReconcileResult",
    # Operator
    "ClusterOperator",
    "OperatorConfig",
    # Health
    "HealthMonitor",
    "HealthStatus",
    "RecoveryAction",
]
