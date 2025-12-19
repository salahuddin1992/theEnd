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

Usage:
    from distributed_cluster.sync import SyncManager, SyncMode

    # Create sync manager
    sync = SyncManager(node_id="node-1")

    # Add peers
    await sync.add_peer("http://node-2:8765")

    # Start real-time sync
    await sync.start()

    # Set state (auto-synced)
    await sync.set_state("key", "value")
"""

from distributed_cluster.sync.conflict import (
    Conflict,
    ConflictResolver,
    ConflictStrategy,
    GCounter,
    GSet,
    LWWRegister,
    PNCounter,
    VectorClock,
)
from distributed_cluster.sync.data import (
    DataChunk,
    DataSync,
    DataTransfer,
    TransferStatus,
    collect_stream,
    stream_data,
)
from distributed_cluster.sync.manager import (
    SyncConfig,
    SyncEvent,
    SyncManager,
    SyncMode,
    SyncOperation,
    SyncPeer,
    SyncStatus,
    create_sync_manager,
)
from distributed_cluster.sync.realtime import (
    MessageType,
    Participant,
    RealtimeSync,
    SyncChannel,
    SyncMessage,
    WebSocketSyncAdapter,
)
from distributed_cluster.sync.state import (
    DeltaType,
    StateDelta,
    StateSnapshot,
    StateSync,
)

__all__ = [
    # Manager
    "SyncManager",
    "SyncConfig",
    "SyncMode",
    "SyncStatus",
    "SyncPeer",
    "SyncOperation",
    "SyncEvent",
    "create_sync_manager",
    # State
    "StateSync",
    "StateDelta",
    "StateSnapshot",
    "DeltaType",
    # Data
    "DataSync",
    "DataChunk",
    "DataTransfer",
    "TransferStatus",
    "stream_data",
    "collect_stream",
    # Realtime
    "RealtimeSync",
    "SyncChannel",
    "SyncMessage",
    "MessageType",
    "Participant",
    "WebSocketSyncAdapter",
    # Conflict Resolution
    "ConflictResolver",
    "ConflictStrategy",
    "VectorClock",
    "Conflict",
    # CRDT Types
    "GCounter",
    "PNCounter",
    "LWWRegister",
    "GSet",
]
