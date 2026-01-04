"""
Advanced Health Dashboard - لوحة المراقبة المتقدمة
=================================================

Health Dashboard Module
-----------------------

This module provides an advanced health monitoring dashboard:
- Real-time metrics visualization
- Worker health monitoring
- Job queue analytics
- Resource utilization graphs
- Alert configuration

يوفر هذا النظام لوحة مراقبة صحية متقدمة:
- تصور المقاييس في الوقت الفعلي
- مراقبة صحة العمال
- تحليلات قائمة المهام
- رسومات استخدام الموارد
- إعدادات التنبيهات

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.dashboard.alerts import (
    Alert,
    AlertManager,
    AlertRule,
    AlertSeverity,
)
from distributed_cluster.dashboard.health import (
    ComponentHealth,
    HealthChecker,
    HealthStatus,
)
from distributed_cluster.dashboard.metrics import (
    MetricPoint,
    MetricsCollector,
    MetricSeries,
    MetricType,
)
from distributed_cluster.dashboard.server import (
    DashboardConfig,
    DashboardServer,
)

__all__ = [
    # Metrics
    "MetricsCollector",
    "MetricPoint",
    "MetricSeries",
    "MetricType",
    # Health
    "HealthChecker",
    "ComponentHealth",
    "HealthStatus",
    # Alerts
    "AlertManager",
    "Alert",
    "AlertRule",
    "AlertSeverity",
    # Server
    "DashboardServer",
    "DashboardConfig",
]
