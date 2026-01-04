"""
Auto-Scaling Module - نظام التوسع التلقائي للعمال
=================================================

Intelligent Auto-Scaling System for Workers
-------------------------------------------

This module provides an intelligent auto-scaling system that automatically
scales the number of workers based on workload metrics. It supports:

يوفر هذا النظام توسع تلقائي ذكي للعمال بناءً على:
- مراقبة عمق طابور المهام / Queue depth monitoring
- استخدام الموارد (CPU/GPU/RAM) / Resource utilization
- سياسات قابلة للتكوين / Configurable policies
- تكامل مع مزودي السحابة / Cloud provider integration
- فترات التهدئة / Cooldown periods

Components:
-----------
- AutoScalingManager: المدير الرئيسي للتوسع التلقائي
- MetricsCollector: جامع المقاييس من الكلاستر
- ScalingPolicy: سياسات التوسع المتنوعة
- CloudProvider: واجهة مزودي السحابة

Usage Example / مثال الاستخدام:
-------------------------------
```python
from distributed_cluster.autoscaling import (
    AutoScalingManager,
    MetricsCollector,
    QueueBasedPolicy,
    ResourceBasedPolicy,
    AWSProvider,
)

# إعداد جامع المقاييس
metrics = MetricsCollector(cluster_state)

# إعداد السياسة
policy = QueueBasedPolicy(
    min_workers=1,
    max_workers=100,
    target_queue_depth=10,
    scale_up_threshold=20,
    scale_down_threshold=5,
)

# إعداد مزود السحابة
provider = AWSProvider(
    region="us-east-1",
    instance_type="t3.xlarge",
)

# إنشاء مدير التوسع
manager = AutoScalingManager(
    metrics_collector=metrics,
    policy=policy,
    provider=provider,
    cooldown_up_seconds=60,
    cooldown_down_seconds=300,
)

# بدء التوسع التلقائي
await manager.start()
```

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.autoscaling.metrics import (
    MetricType,
    MetricsCollector,
    MetricsSample,
    ResourceMetrics,
)
from distributed_cluster.autoscaling.policies import (
    CompositePolicy,
    CostAwarePolicy,
    PolicyTemplates,
    PredictivePolicy,
    QueueBasedPolicy,
    ResourceBasedPolicy,
    ScalingDecision,
    ScalingDirection,
    ScalingPolicy,
    ScheduleBasedPolicy,
)
from distributed_cluster.autoscaling.providers import (
    AWSProvider,
    AzureProvider,
    CloudProvider,
    GCPProvider,
    LocalProvider,
    ProviderConfig,
)
from distributed_cluster.autoscaling.scaler import (
    AutoScalingConfig,
    AutoScalingEvent,
    AutoScalingManager,
    AutoScalingState,
    AutoScalingStatus,
)

__all__ = [
    # Core Manager
    "AutoScalingManager",
    "AutoScalingConfig",
    "AutoScalingState",
    "AutoScalingStatus",
    "AutoScalingEvent",
    # Metrics
    "MetricsCollector",
    "MetricsSample",
    "ResourceMetrics",
    "MetricType",
    # Policies
    "ScalingPolicy",
    "ScalingDecision",
    "ScalingDirection",
    "QueueBasedPolicy",
    "ResourceBasedPolicy",
    "CompositePolicy",
    "CostAwarePolicy",
    "PredictivePolicy",
    "ScheduleBasedPolicy",
    "PolicyTemplates",
    # Providers
    "CloudProvider",
    "ProviderConfig",
    "AWSProvider",
    "GCPProvider",
    "AzureProvider",
    "LocalProvider",
]

__version__ = "1.0.0"
