"""
High Availability (HA) Module - وحدة التوفر العالي
====================================================

تدعم تشغيل أكثر من Master server مع:
- Leader Election (انتخاب القائد)
- State Synchronization (مزامنة الحالة)
- Automatic Failover (التبديل التلقائي)

الأنماط المدعومة:
- Active-Standby: Master واحد نشط، والباقي احتياط
- Active-Active: كل Masters نشطة (يحتاج قاعدة بيانات مشتركة)
"""

from .leader_election import (
    LeaderElection,
    HARole,
    LeaderInfo,
    ElectionConfig,
)
from .state_sync import (
    StateSync,
    SyncConfig,
    SyncMessage,
    SyncMessageType,
)
from .health_monitor import (
    HAHealthMonitor,
    MasterHealth,
    HealthConfig,
)
from .ha_master import (
    HAMasterServer,
    HAConfig,
    HAMode,
)

__all__ = [
    # Leader Election
    "LeaderElection",
    "HARole",
    "LeaderInfo",
    "ElectionConfig",
    # State Sync
    "StateSync",
    "SyncConfig",
    "SyncMessage",
    "SyncMessageType",
    # Health Monitor
    "HAHealthMonitor",
    "MasterHealth",
    "HealthConfig",
    # HA Master
    "HAMasterServer",
    "HAConfig",
    "HAMode",
]
