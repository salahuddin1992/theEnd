"""
Sync Module - نظام المزامنة المستمرة بين الحواسيب
=================================================

Continuous synchronization system for distributed computing:
- State synchronization across all nodes
- Data replication and consistency
- Real-time updates via WebSocket
- Conflict resolution with CRDT
- Model and configuration sync
- Automatic failover and recovery
"""

from distributed_cluster.sync.manager import (
    SyncManager,
    SyncConfig,
    SyncMode,
    SyncStatus,
)
from distributed_cluster.sync.state import (
    StateSync,
    StateDelta,
    StateSnapshot,
)
from distributed_cluster.sync.data import (
    DataSync,
    DataChunk,
    DataTransfer,
)
from distributed_cluster.sync.realtime import (
    RealtimeSync,
    SyncChannel,
    SyncMessage,
)
from distributed_cluster.sync.conflict import (
    ConflictResolver,
    ConflictStrategy,
    VectorClock,
)

__all__ = [
    # Manager
    "SyncManager",
    "SyncConfig",
    "SyncMode",
    "SyncStatus",

    # State
    "StateSync",
    "StateDelta",
    "StateSnapshot",

    # Data
    "DataSync",
    "DataChunk",
    "DataTransfer",

    # Realtime
    "RealtimeSync",
    "SyncChannel",
    "SyncMessage",

    # Conflict
    "ConflictResolver",
    "ConflictStrategy",
    "VectorClock",
]
