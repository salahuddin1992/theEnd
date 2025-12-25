"""
State Sync - مزامنة الحالة
===========================

Cross-Cluster State Synchronization
-----------------------------------

This module provides state synchronization between federated clusters.

يوفر هذا الملف مزامنة الحالة بين الكتل المتحدة.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

from distributed_cluster.federation.cluster import FederatedCluster

logger = logging.getLogger(__name__)


class SyncMode(str, Enum):
    """وضع المزامنة / Sync mode"""
    PUSH = "push"           # دفع الحالة للكتل الأخرى
    PULL = "pull"           # سحب الحالة من الكتل الأخرى
    BIDIRECTIONAL = "bidirectional"  # في كلا الاتجاهين
    EVENTUAL = "eventual"   # اتساق نهائي


class ConflictResolution(str, Enum):
    """حل التعارضات / Conflict resolution"""
    LATEST_WINS = "latest_wins"       # الأحدث يفوز
    PRIMARY_WINS = "primary_wins"     # الكتلة الأساسية تفوز
    MERGE = "merge"                   # دمج التغييرات
    MANUAL = "manual"                 # حل يدوي


class SyncStatus(str, Enum):
    """حالة المزامنة / Sync status"""
    IDLE = "idle"
    SYNCING = "syncing"
    SUCCESS = "success"
    FAILED = "failed"
    CONFLICT = "conflict"


@dataclass
class SyncConfig:
    """
    إعدادات المزامنة
    Sync Configuration
    """
    mode: SyncMode = SyncMode.BIDIRECTIONAL
    conflict_resolution: ConflictResolution = ConflictResolution.LATEST_WINS

    # Timing
    sync_interval_seconds: float = 30.0
    timeout_seconds: float = 60.0

    # Content
    sync_config: bool = True
    sync_state: bool = True
    sync_jobs: bool = False
    sync_metrics: bool = True

    # Filtering
    include_keys: Optional[list[str]] = None
    exclude_keys: Optional[list[str]] = None

    # Compression
    compress: bool = True
    compression_threshold_bytes: int = 1024

    # Versioning
    enable_versioning: bool = True
    max_versions: int = 10


@dataclass
class SyncResult:
    """
    نتيجة المزامنة
    Sync Result
    """
    success: bool
    sync_id: str
    source_cluster: str
    target_cluster: str
    items_synced: int = 0
    conflicts: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "sync_id": self.sync_id,
            "source_cluster": self.source_cluster,
            "target_cluster": self.target_cluster,
            "items_synced": self.items_synced,
            "conflicts": self.conflicts,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SyncState:
    """
    حالة المزامنة
    Sync State Entry
    """
    key: str
    value: Any
    version: int
    timestamp: datetime
    checksum: str
    source_cluster: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "version": self.version,
            "timestamp": self.timestamp.isoformat(),
            "checksum": self.checksum,
            "source_cluster": self.source_cluster,
        }

    @classmethod
    def create(
        cls,
        key: str,
        value: Any,
        source_cluster: str,
        version: int = 1,
    ) -> SyncState:
        value_str = json.dumps(value, sort_keys=True, default=str)
        checksum = hashlib.sha256(value_str.encode()).hexdigest()[:16]

        return cls(
            key=key,
            value=value,
            version=version,
            timestamp=datetime.utcnow(),
            checksum=checksum,
            source_cluster=source_cluster,
        )


class StateSync:
    """
    مزامنة الحالة
    State Sync

    يدير مزامنة الحالة بين الكتل المتحدة.
    Manages state synchronization between federated clusters.
    """

    def __init__(
        self,
        cluster_id: str,
        config: Optional[SyncConfig] = None,
    ):
        """
        تهيئة المزامنة

        Args:
            cluster_id: معرف الكتلة المحلية
            config: إعدادات المزامنة
        """
        self.cluster_id = cluster_id
        self.config = config or SyncConfig()

        # Clusters
        self._clusters: dict[str, FederatedCluster] = {}

        # Local state
        self._local_state: dict[str, SyncState] = {}
        self._state_versions: dict[str, list[SyncState]] = {}

        # Sync status
        self._status = SyncStatus.IDLE
        self._last_sync: Optional[datetime] = None
        self._last_result: Optional[SyncResult] = None

        # Background sync
        self._running = False
        self._sync_task: Optional[asyncio.Task] = None

        # Conflict handlers
        self._conflict_handlers: list[Callable] = []

        # Stats
        self._stats = {
            "total_syncs": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
            "conflicts_resolved": 0,
            "items_synced": 0,
        }

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء المزامنة"""
        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info(f"StateSync started for cluster {self.cluster_id}")

    async def stop(self) -> None:
        """إيقاف المزامنة"""
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        logger.info("StateSync stopped")

    # =========================================================================
    # Cluster Management
    # =========================================================================

    def add_cluster(self, cluster: FederatedCluster) -> None:
        """إضافة كتلة للمزامنة"""
        self._clusters[cluster.info.cluster_id] = cluster

    def remove_cluster(self, cluster_id: str) -> None:
        """إزالة كتلة"""
        self._clusters.pop(cluster_id, None)

    # =========================================================================
    # Local State
    # =========================================================================

    def set_local(
        self,
        key: str,
        value: Any,
    ) -> None:
        """تعيين قيمة محلية"""
        existing = self._local_state.get(key)
        version = existing.version + 1 if existing else 1

        state = SyncState.create(
            key=key,
            value=value,
            source_cluster=self.cluster_id,
            version=version,
        )

        self._local_state[key] = state

        # Store version history
        if self.config.enable_versioning:
            if key not in self._state_versions:
                self._state_versions[key] = []
            self._state_versions[key].append(state)

            # Trim old versions
            if len(self._state_versions[key]) > self.config.max_versions:
                self._state_versions[key] = self._state_versions[key][
                    -self.config.max_versions:
                ]

    def get_local(self, key: str) -> Optional[Any]:
        """الحصول على قيمة محلية"""
        state = self._local_state.get(key)
        return state.value if state else None

    def get_all_local(self) -> dict[str, Any]:
        """الحصول على كل القيم المحلية"""
        return {key: state.value for key, state in self._local_state.items()}

    def delete_local(self, key: str) -> bool:
        """حذف قيمة محلية"""
        if key in self._local_state:
            del self._local_state[key]
            return True
        return False

    # =========================================================================
    # Synchronization
    # =========================================================================

    async def sync(self) -> list[SyncResult]:
        """مزامنة مع كل الكتل"""
        results = []
        self._status = SyncStatus.SYNCING

        for cluster in self._clusters.values():
            if not cluster.info.is_healthy():
                continue

            try:
                result = await self._sync_with_cluster(cluster)
                results.append(result)

            except Exception as e:
                logger.error(f"Sync with {cluster.info.cluster_id} failed: {e}")
                results.append(SyncResult(
                    success=False,
                    sync_id=str(uuid4()),
                    source_cluster=self.cluster_id,
                    target_cluster=cluster.info.cluster_id,
                    error=str(e),
                ))

        # Update status
        if all(r.success for r in results):
            self._status = SyncStatus.SUCCESS
        elif any(r.conflicts > 0 for r in results):
            self._status = SyncStatus.CONFLICT
        else:
            self._status = SyncStatus.FAILED

        self._last_sync = datetime.utcnow()
        self._stats["total_syncs"] += len(results)
        self._stats["successful_syncs"] += sum(1 for r in results if r.success)
        self._stats["failed_syncs"] += sum(1 for r in results if not r.success)

        return results

    async def sync_with(self, cluster_id: str) -> Optional[SyncResult]:
        """مزامنة مع كتلة محددة"""
        cluster = self._clusters.get(cluster_id)
        if not cluster:
            return None

        return await self._sync_with_cluster(cluster)

    async def _sync_with_cluster(
        self,
        cluster: FederatedCluster,
    ) -> SyncResult:
        """مزامنة مع كتلة واحدة"""
        import time
        start = time.time()
        sync_id = str(uuid4())

        items_synced = 0
        conflicts = 0

        try:
            if self.config.mode in (SyncMode.PUSH, SyncMode.BIDIRECTIONAL):
                # Push local state
                pushed = await self._push_state(cluster)
                items_synced += pushed

            if self.config.mode in (SyncMode.PULL, SyncMode.BIDIRECTIONAL):
                # Pull remote state
                pulled, conf = await self._pull_state(cluster)
                items_synced += pulled
                conflicts += conf

            duration = time.time() - start

            self._stats["items_synced"] += items_synced
            self._stats["conflicts_resolved"] += conflicts

            return SyncResult(
                success=True,
                sync_id=sync_id,
                source_cluster=self.cluster_id,
                target_cluster=cluster.info.cluster_id,
                items_synced=items_synced,
                conflicts=conflicts,
                duration_seconds=duration,
            )

        except Exception as e:
            return SyncResult(
                success=False,
                sync_id=sync_id,
                source_cluster=self.cluster_id,
                target_cluster=cluster.info.cluster_id,
                error=str(e),
                duration_seconds=time.time() - start,
            )

    async def _push_state(
        self,
        cluster: FederatedCluster,
    ) -> int:
        """دفع الحالة للكتلة"""
        # Prepare state payload
        state_data = {}

        for key, state in self._local_state.items():
            # Apply filters
            if self._should_sync_key(key):
                state_data[key] = state.to_dict()

        if not state_data:
            return 0

        # Push to cluster
        success = await cluster.push_state({
            "source_cluster": self.cluster_id,
            "timestamp": datetime.utcnow().isoformat(),
            "state": state_data,
        })

        return len(state_data) if success else 0

    async def _pull_state(
        self,
        cluster: FederatedCluster,
    ) -> tuple[int, int]:
        """سحب الحالة من الكتلة"""
        # Get remote state
        remote_data = await cluster.get_state()
        remote_state = remote_data.get("state", {})

        pulled = 0
        conflicts = 0

        for key, remote_entry in remote_state.items():
            if not self._should_sync_key(key):
                continue

            # Create SyncState from remote
            remote = SyncState(
                key=key,
                value=remote_entry.get("value"),
                version=remote_entry.get("version", 1),
                timestamp=datetime.fromisoformat(remote_entry.get("timestamp")),
                checksum=remote_entry.get("checksum", ""),
                source_cluster=remote_entry.get("source_cluster", cluster.info.cluster_id),
            )

            # Check for conflicts
            local = self._local_state.get(key)

            if local:
                if local.checksum != remote.checksum:
                    # Conflict detected
                    resolved = self._resolve_conflict(local, remote)
                    if resolved != local:
                        self._local_state[key] = resolved
                        pulled += 1
                    conflicts += 1
            else:
                # No local version, accept remote
                self._local_state[key] = remote
                pulled += 1

        return pulled, conflicts

    def _should_sync_key(self, key: str) -> bool:
        """هل يجب مزامنة هذا المفتاح؟"""
        if self.config.include_keys:
            if key not in self.config.include_keys:
                return False

        if self.config.exclude_keys:
            if key in self.config.exclude_keys:
                return False

        return True

    def _resolve_conflict(
        self,
        local: SyncState,
        remote: SyncState,
    ) -> SyncState:
        """حل تعارض"""
        resolution = self.config.conflict_resolution

        if resolution == ConflictResolution.LATEST_WINS:
            return remote if remote.timestamp > local.timestamp else local

        elif resolution == ConflictResolution.PRIMARY_WINS:
            # Prefer local (assuming this is primary)
            return local

        elif resolution == ConflictResolution.MERGE:
            # Simple merge: prefer remote for non-dict values
            if isinstance(local.value, dict) and isinstance(remote.value, dict):
                merged = {**local.value, **remote.value}
                return SyncState.create(
                    key=local.key,
                    value=merged,
                    source_cluster=self.cluster_id,
                    version=max(local.version, remote.version) + 1,
                )
            return remote if remote.timestamp > local.timestamp else local

        else:
            # Manual or unknown - prefer local
            for handler in self._conflict_handlers:
                try:
                    result = handler(local, remote)
                    if result:
                        return result
                except Exception:
                    pass
            return local

    # =========================================================================
    # Background Sync
    # =========================================================================

    async def _sync_loop(self) -> None:
        """حلقة المزامنة الخلفية"""
        while self._running:
            try:
                await self.sync()
                await asyncio.sleep(self.config.sync_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
                await asyncio.sleep(self.config.sync_interval_seconds)

    # =========================================================================
    # Conflict Handlers
    # =========================================================================

    def register_conflict_handler(
        self,
        handler: Callable[[SyncState, SyncState], Optional[SyncState]],
    ) -> None:
        """تسجيل معالج تعارضات"""
        self._conflict_handlers.append(handler)

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """الحصول على الحالة"""
        return {
            "cluster_id": self.cluster_id,
            "status": self._status.value,
            "running": self._running,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "clusters_count": len(self._clusters),
            "local_keys": len(self._local_state),
            "stats": self._stats,
        }

    def get_sync_diff(
        self,
        cluster_id: str,
    ) -> dict[str, Any]:
        """الحصول على الفروقات مع كتلة"""
        # This would compare local state with remote
        return {
            "local_only": [],
            "remote_only": [],
            "different": [],
            "same": [],
        }
