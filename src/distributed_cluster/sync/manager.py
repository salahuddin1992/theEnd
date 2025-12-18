"""
Sync Manager - مدير المزامنة الرئيسي
====================================

Central coordination for all synchronization operations:
- Manages sync state across nodes
- Coordinates data transfer
- Handles failover and recovery
- Monitors sync health
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import httpx

logger = logging.getLogger(__name__)


class SyncMode(str, Enum):
    """أوضاع المزامنة."""
    FULL = "full"  # مزامنة كاملة
    INCREMENTAL = "incremental"  # مزامنة تزايدية
    REALTIME = "realtime"  # مزامنة فورية
    SCHEDULED = "scheduled"  # مزامنة مجدولة
    ON_DEMAND = "on_demand"  # عند الطلب


class SyncStatus(str, Enum):
    """حالة المزامنة."""
    IDLE = "idle"
    SYNCING = "syncing"
    SYNCED = "synced"
    FAILED = "failed"
    PARTIAL = "partial"
    CONFLICT = "conflict"


class SyncDirection(str, Enum):
    """اتجاه المزامنة."""
    PUSH = "push"  # إرسال للآخرين
    PULL = "pull"  # استقبال من الآخرين
    BIDIRECTIONAL = "bidirectional"  # ثنائي الاتجاه


@dataclass
class SyncConfig:
    """إعدادات المزامنة."""
    # Basic settings
    mode: SyncMode = SyncMode.REALTIME
    direction: SyncDirection = SyncDirection.BIDIRECTIONAL
    interval_seconds: float = 5.0  # فترة المزامنة
    timeout_seconds: float = 30.0

    # Data settings
    batch_size: int = 100  # حجم الدفعة
    max_retries: int = 3
    compression: bool = True
    encryption: bool = False

    # Conflict resolution
    auto_resolve_conflicts: bool = True
    conflict_strategy: str = "last_write_wins"

    # Performance
    parallel_transfers: int = 4
    chunk_size_kb: int = 1024  # 1MB chunks

    # Reliability
    enable_checksum: bool = True
    enable_journaling: bool = True
    enable_snapshots: bool = True
    snapshot_interval_minutes: int = 60


@dataclass
class SyncPeer:
    """عقدة مزامنة."""
    peer_id: str
    name: str
    url: str
    status: SyncStatus = SyncStatus.IDLE
    last_sync: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    version: int = 0
    latency_ms: float = 0
    healthy: bool = True

    # Stats
    bytes_sent: int = 0
    bytes_received: int = 0
    sync_count: int = 0
    error_count: int = 0


@dataclass
class SyncOperation:
    """عملية مزامنة."""
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    operation_type: str = "sync"  # sync, push, pull, merge
    source_peer: str = ""
    target_peer: str = ""
    status: SyncStatus = SyncStatus.IDLE
    progress: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    items_total: int = 0
    items_synced: int = 0
    bytes_transferred: int = 0


@dataclass
class SyncEvent:
    """حدث مزامنة."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""  # sync_started, sync_completed, conflict, error
    peer_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = field(default_factory=dict)


class SyncManager:
    """
    مدير المزامنة المركزي.

    Central manager for all synchronization operations across the cluster.

    Features:
    - Multi-node synchronization
    - Real-time data replication
    - Automatic conflict resolution
    - Health monitoring
    - Automatic failover
    """

    def __init__(
        self,
        node_id: Optional[str] = None,
        config: Optional[SyncConfig] = None,
    ):
        self.node_id = node_id or str(uuid.uuid4())
        self.config = config or SyncConfig()

        # Peers
        self._peers: Dict[str, SyncPeer] = {}

        # State
        self._local_state: Dict[str, Any] = {}
        self._state_version: int = 0
        self._state_hash: str = ""

        # Operations
        self._operations: Dict[str, SyncOperation] = {}
        self._pending_changes: List[Dict[str, Any]] = []

        # Event handlers
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._events: List[SyncEvent] = []

        # Control
        self._running = False
        self._sync_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Journal
        self._journal: List[Dict[str, Any]] = []

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء المزامنة."""
        if self._running:
            return

        self._running = True

        # Start background tasks
        if self.config.mode == SyncMode.REALTIME:
            self._sync_task = asyncio.create_task(self._sync_loop())

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(f"SyncManager started (node: {self.node_id})")
        await self._emit_event("sync_manager_started", {})

    async def stop(self) -> None:
        """إيقاف المزامنة."""
        self._running = False

        # Cancel tasks
        for task in [self._sync_task, self._heartbeat_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info("SyncManager stopped")
        await self._emit_event("sync_manager_stopped", {})

    # =========================================================================
    # Peer Management
    # =========================================================================

    async def add_peer(
        self,
        url: str,
        name: Optional[str] = None,
        peer_id: Optional[str] = None,
    ) -> SyncPeer:
        """إضافة عقدة مزامنة."""
        peer_id = peer_id or str(uuid.uuid4())

        peer = SyncPeer(
            peer_id=peer_id,
            name=name or f"peer-{peer_id[:8]}",
            url=url.rstrip("/"),
        )

        # Test connection
        connected = await self._test_peer_connection(peer)
        peer.healthy = connected
        peer.last_heartbeat = datetime.utcnow() if connected else None

        self._peers[peer_id] = peer

        logger.info(f"Added peer: {peer.name} ({peer.url})")
        await self._emit_event("peer_added", {"peer_id": peer_id, "url": url})

        return peer

    async def remove_peer(self, peer_id: str) -> None:
        """إزالة عقدة مزامنة."""
        if peer_id in self._peers:
            peer = self._peers.pop(peer_id)
            logger.info(f"Removed peer: {peer.name}")
            await self._emit_event("peer_removed", {"peer_id": peer_id})

    def get_peers(self) -> List[SyncPeer]:
        """الحصول على قائمة العقد."""
        return list(self._peers.values())

    def get_healthy_peers(self) -> List[SyncPeer]:
        """الحصول على العقد السليمة."""
        return [p for p in self._peers.values() if p.healthy]

    async def _test_peer_connection(self, peer: SyncPeer) -> bool:
        """اختبار الاتصال بعقدة."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                start = time.time()
                response = await client.get(f"{peer.url}/sync/health")
                peer.latency_ms = (time.time() - start) * 1000
                return response.status_code == 200
        except Exception as e:
            logger.debug(f"Peer connection test failed: {peer.url} - {e}")
            return False

    # =========================================================================
    # State Synchronization
    # =========================================================================

    async def set_state(self, key: str, value: Any) -> None:
        """تعيين قيمة في الحالة."""
        async with self._lock:
            old_value = self._local_state.get(key)
            self._local_state[key] = value
            self._state_version += 1
            self._update_state_hash()

            # Record change
            change = {
                "operation": "set",
                "key": key,
                "value": value,
                "old_value": old_value,
                "version": self._state_version,
                "timestamp": datetime.utcnow().isoformat(),
                "node_id": self.node_id,
            }
            self._pending_changes.append(change)

            if self.config.enable_journaling:
                self._journal.append(change)

        # Sync immediately in realtime mode
        if self.config.mode == SyncMode.REALTIME:
            await self._broadcast_change(change)

    async def get_state(self, key: str, default: Any = None) -> Any:
        """الحصول على قيمة من الحالة."""
        return self._local_state.get(key, default)

    async def delete_state(self, key: str) -> None:
        """حذف قيمة من الحالة."""
        async with self._lock:
            if key in self._local_state:
                old_value = self._local_state.pop(key)
                self._state_version += 1
                self._update_state_hash()

                change = {
                    "operation": "delete",
                    "key": key,
                    "old_value": old_value,
                    "version": self._state_version,
                    "timestamp": datetime.utcnow().isoformat(),
                    "node_id": self.node_id,
                }
                self._pending_changes.append(change)

                if self.config.enable_journaling:
                    self._journal.append(change)

                if self.config.mode == SyncMode.REALTIME:
                    await self._broadcast_change(change)

    def get_full_state(self) -> Dict[str, Any]:
        """الحصول على الحالة الكاملة."""
        return {
            "state": self._local_state.copy(),
            "version": self._state_version,
            "hash": self._state_hash,
            "node_id": self.node_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _update_state_hash(self) -> None:
        """تحديث hash الحالة."""
        state_str = json.dumps(self._local_state, sort_keys=True)
        self._state_hash = hashlib.sha256(state_str.encode()).hexdigest()[:16]

    # =========================================================================
    # Synchronization Operations
    # =========================================================================

    async def sync_all(self) -> SyncOperation:
        """مزامنة مع جميع العقد."""
        operation = SyncOperation(
            operation_type="sync_all",
            source_peer=self.node_id,
            started_at=datetime.utcnow(),
        )
        self._operations[operation.operation_id] = operation

        await self._emit_event("sync_started", {"operation_id": operation.operation_id})

        healthy_peers = self.get_healthy_peers()
        operation.items_total = len(healthy_peers)

        errors = []
        for peer in healthy_peers:
            try:
                await self._sync_with_peer(peer)
                operation.items_synced += 1
                peer.sync_count += 1
                peer.last_sync = datetime.utcnow()
            except Exception as e:
                errors.append(f"{peer.name}: {e}")
                peer.error_count += 1

            operation.progress = operation.items_synced / max(1, operation.items_total)

        operation.completed_at = datetime.utcnow()

        if not errors:
            operation.status = SyncStatus.SYNCED
        elif operation.items_synced > 0:
            operation.status = SyncStatus.PARTIAL
            operation.error = "; ".join(errors)
        else:
            operation.status = SyncStatus.FAILED
            operation.error = "; ".join(errors)

        await self._emit_event("sync_completed", {
            "operation_id": operation.operation_id,
            "status": operation.status.value,
        })

        return operation

    async def sync_with_peer(self, peer_id: str) -> SyncOperation:
        """مزامنة مع عقدة محددة."""
        peer = self._peers.get(peer_id)
        if not peer:
            raise ValueError(f"Peer not found: {peer_id}")

        operation = SyncOperation(
            operation_type="sync",
            source_peer=self.node_id,
            target_peer=peer_id,
            started_at=datetime.utcnow(),
        )
        self._operations[operation.operation_id] = operation

        try:
            await self._sync_with_peer(peer)
            operation.status = SyncStatus.SYNCED
            peer.last_sync = datetime.utcnow()
        except Exception as e:
            operation.status = SyncStatus.FAILED
            operation.error = str(e)

        operation.completed_at = datetime.utcnow()
        return operation

    async def _sync_with_peer(self, peer: SyncPeer) -> None:
        """تنفيذ المزامنة مع عقدة."""
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            # Get peer state
            response = await client.get(f"{peer.url}/sync/state")
            response.raise_for_status()
            peer_state = response.json()

            peer.version = peer_state.get("version", 0)

            # Compare and merge
            if self.config.direction in [SyncDirection.PULL, SyncDirection.BIDIRECTIONAL]:
                await self._merge_remote_state(peer_state, peer)

            if self.config.direction in [SyncDirection.PUSH, SyncDirection.BIDIRECTIONAL]:
                await self._push_state_to_peer(peer)

    async def _merge_remote_state(
        self,
        remote_state: Dict[str, Any],
        peer: SyncPeer,
    ) -> None:
        """دمج الحالة البعيدة."""
        remote_data = remote_state.get("state", {})
        remote_version = remote_state.get("version", 0)

        async with self._lock:
            for key, value in remote_data.items():
                if key not in self._local_state:
                    # New key from remote
                    self._local_state[key] = value
                elif self._local_state[key] != value:
                    # Conflict - resolve based on strategy
                    if self.config.auto_resolve_conflicts:
                        resolved = await self._resolve_conflict(
                            key,
                            self._local_state[key],
                            value,
                            remote_version,
                        )
                        self._local_state[key] = resolved
                    else:
                        await self._emit_event("conflict", {
                            "key": key,
                            "local_value": self._local_state[key],
                            "remote_value": value,
                            "peer_id": peer.peer_id,
                        })

            self._state_version = max(self._state_version, remote_version) + 1
            self._update_state_hash()

            peer.bytes_received += len(json.dumps(remote_data))

    async def _push_state_to_peer(self, peer: SyncPeer) -> None:
        """إرسال الحالة لعقدة."""
        state_data = self.get_full_state()

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{peer.url}/sync/state",
                json=state_data,
            )
            response.raise_for_status()

        peer.bytes_sent += len(json.dumps(state_data))

    async def _broadcast_change(self, change: Dict[str, Any]) -> None:
        """بث تغيير لجميع العقد."""
        tasks = []
        for peer in self.get_healthy_peers():
            tasks.append(self._send_change_to_peer(peer, change))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_change_to_peer(
        self,
        peer: SyncPeer,
        change: Dict[str, Any],
    ) -> None:
        """إرسال تغيير لعقدة."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{peer.url}/sync/change",
                    json=change,
                )
                response.raise_for_status()
                peer.bytes_sent += len(json.dumps(change))
        except Exception as e:
            logger.warning(f"Failed to send change to {peer.name}: {e}")

    # =========================================================================
    # Conflict Resolution
    # =========================================================================

    async def _resolve_conflict(
        self,
        key: str,
        local_value: Any,
        remote_value: Any,
        remote_version: int,
    ) -> Any:
        """حل تعارض."""
        strategy = self.config.conflict_strategy

        if strategy == "last_write_wins":
            # الكتابة الأخيرة تفوز
            if remote_version > self._state_version:
                return remote_value
            return local_value

        elif strategy == "first_write_wins":
            # الكتابة الأولى تفوز
            return local_value

        elif strategy == "merge":
            # دمج القيم
            if isinstance(local_value, dict) and isinstance(remote_value, dict):
                merged = {**local_value, **remote_value}
                return merged
            elif isinstance(local_value, list) and isinstance(remote_value, list):
                # Merge lists (unique values)
                return list(set(local_value + remote_value))
            else:
                return remote_value

        elif strategy == "local_priority":
            return local_value

        elif strategy == "remote_priority":
            return remote_value

        else:
            # Default: last write wins
            return remote_value if remote_version > self._state_version else local_value

    # =========================================================================
    # Background Tasks
    # =========================================================================

    async def _sync_loop(self) -> None:
        """حلقة المزامنة المستمرة."""
        while self._running:
            try:
                await asyncio.sleep(self.config.interval_seconds)

                if self._pending_changes:
                    # Flush pending changes
                    async with self._lock:
                        changes = self._pending_changes.copy()
                        self._pending_changes.clear()

                    for change in changes:
                        await self._broadcast_change(change)

                # Periodic full sync
                if len(self._peers) > 0:
                    await self.sync_all()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync loop error: {e}")

    async def _heartbeat_loop(self) -> None:
        """حلقة نبض القلب."""
        while self._running:
            try:
                await asyncio.sleep(10.0)  # Every 10 seconds

                for peer in list(self._peers.values()):
                    healthy = await self._test_peer_connection(peer)

                    if healthy != peer.healthy:
                        peer.healthy = healthy
                        await self._emit_event(
                            "peer_health_changed",
                            {"peer_id": peer.peer_id, "healthy": healthy}
                        )

                    if healthy:
                        peer.last_heartbeat = datetime.utcnow()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")

    # =========================================================================
    # Event System
    # =========================================================================

    def on(self, event_type: str, handler: Callable) -> None:
        """تسجيل معالج حدث."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    async def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """إطلاق حدث."""
        event = SyncEvent(
            event_type=event_type,
            peer_id=self.node_id,
            data=data,
        )
        self._events.append(event)

        # Call handlers
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    def get_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[SyncEvent]:
        """الحصول على الأحداث."""
        events = self._events
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    # =========================================================================
    # Snapshots
    # =========================================================================

    async def create_snapshot(self) -> Dict[str, Any]:
        """إنشاء لقطة من الحالة."""
        snapshot = {
            "snapshot_id": str(uuid.uuid4()),
            "node_id": self.node_id,
            "timestamp": datetime.utcnow().isoformat(),
            "version": self._state_version,
            "hash": self._state_hash,
            "state": self._local_state.copy(),
            "peers": [
                {
                    "peer_id": p.peer_id,
                    "name": p.name,
                    "url": p.url,
                    "healthy": p.healthy,
                }
                for p in self._peers.values()
            ],
        }

        await self._emit_event("snapshot_created", {"snapshot_id": snapshot["snapshot_id"]})

        return snapshot

    async def restore_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """استعادة من لقطة."""
        async with self._lock:
            self._local_state = snapshot.get("state", {}).copy()
            self._state_version = snapshot.get("version", 0)
            self._update_state_hash()

        await self._emit_event("snapshot_restored", {"snapshot_id": snapshot.get("snapshot_id")})

    # =========================================================================
    # Status & Info
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """الحصول على حالة المزامنة."""
        return {
            "node_id": self.node_id,
            "running": self._running,
            "mode": self.config.mode.value,
            "direction": self.config.direction.value,
            "state_version": self._state_version,
            "state_hash": self._state_hash,
            "state_keys": len(self._local_state),
            "peers": {
                "total": len(self._peers),
                "healthy": len(self.get_healthy_peers()),
            },
            "pending_changes": len(self._pending_changes),
            "operations": len(self._operations),
            "events": len(self._events),
        }

    def get_sync_stats(self) -> Dict[str, Any]:
        """إحصائيات المزامنة."""
        total_sent = sum(p.bytes_sent for p in self._peers.values())
        total_received = sum(p.bytes_received for p in self._peers.values())
        total_syncs = sum(p.sync_count for p in self._peers.values())
        total_errors = sum(p.error_count for p in self._peers.values())

        return {
            "total_bytes_sent": total_sent,
            "total_bytes_received": total_received,
            "total_sync_operations": total_syncs,
            "total_errors": total_errors,
            "journal_entries": len(self._journal),
        }


# ============================================================================
# Factory Functions
# ============================================================================

def create_sync_manager(
    node_id: Optional[str] = None,
    mode: SyncMode = SyncMode.REALTIME,
    interval: float = 5.0,
) -> SyncManager:
    """إنشاء مدير مزامنة."""
    config = SyncConfig(
        mode=mode,
        interval_seconds=interval,
    )
    return SyncManager(node_id=node_id, config=config)
