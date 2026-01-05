"""
State Synchronization - مزامنة الحالة
=====================================

State synchronization across distributed nodes:
- State snapshots
- Delta synchronization
- Version vectors
- Merkle tree verification
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class DeltaType(str, Enum):
    """نوع التغيير."""

    SET = "set"
    DELETE = "delete"
    UPDATE = "update"
    MERGE = "merge"


@dataclass
class StateDelta:
    """تغيير في الحالة."""

    delta_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    delta_type: DeltaType = DeltaType.SET
    key: str = ""
    value: Any = None
    old_value: Any = None
    version: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    node_id: str = ""
    checksum: str = ""

    def __post_init__(self):
        if not self.checksum:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """حساب checksum."""
        data = f"{self.key}:{json.dumps(self.value, sort_keys=True)}:{self.version}"
        # nosec B324 - MD5 used for checksum, not security
        return hashlib.md5(data.encode(), usedforsecurity=False).hexdigest()[:8]

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        return {
            "delta_id": self.delta_id,
            "delta_type": self.delta_type.value,
            "key": self.key,
            "value": self.value,
            "old_value": self.old_value,
            "version": self.version,
            "timestamp": self.timestamp.isoformat(),
            "node_id": self.node_id,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StateDelta:
        """إنشاء من dictionary."""
        return cls(
            delta_id=data.get("delta_id", str(uuid.uuid4())),
            delta_type=DeltaType(data.get("delta_type", "set")),
            key=data.get("key", ""),
            value=data.get("value"),
            old_value=data.get("old_value"),
            version=data.get("version", 0),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
            node_id=data.get("node_id", ""),
            checksum=data.get("checksum", ""),
        )


@dataclass
class StateSnapshot:
    """لقطة كاملة للحالة."""

    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    node_id: str = ""
    version: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    size_bytes: int = 0

    def __post_init__(self):
        if not self.checksum:
            self.checksum = self._compute_checksum()
        if not self.size_bytes:
            self.size_bytes = len(json.dumps(self.data))

    def _compute_checksum(self) -> str:
        """حساب checksum للحالة الكاملة."""
        data_str = json.dumps(self.data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "node_id": self.node_id,
            "version": self.version,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> StateSnapshot:
        """إنشاء من dictionary."""
        return cls(
            snapshot_id=d.get("snapshot_id", str(uuid.uuid4())),
            node_id=d.get("node_id", ""),
            version=d.get("version", 0),
            timestamp=datetime.fromisoformat(d["timestamp"]) if "timestamp" in d else datetime.now(timezone.utc),
            data=d.get("data", {}),
            checksum=d.get("checksum", ""),
            size_bytes=d.get("size_bytes", 0),
        )


class StateSync:
    """
    مزامنة الحالة بين العقد.

    Handles state synchronization with:
    - Delta-based updates (efficient)
    - Full snapshot sync (reliable)
    - Version tracking
    - Consistency verification
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        self._state: Dict[str, Any] = {}
        self._version: int = 0
        self._deltas: List[StateDelta] = []
        self._snapshots: List[StateSnapshot] = []
        self._max_deltas = 1000
        self._max_snapshots = 10

    @property
    def version(self) -> int:
        """الإصدار الحالي."""
        return self._version

    @property
    def checksum(self) -> str:
        """checksum الحالة الحالية."""
        return hashlib.sha256(json.dumps(self._state, sort_keys=True).encode()).hexdigest()[:16]

    # =========================================================================
    # State Operations
    # =========================================================================

    def set(self, key: str, value: Any) -> StateDelta:
        """تعيين قيمة."""
        old_value = self._state.get(key)
        self._state[key] = value
        self._version += 1

        delta = StateDelta(
            delta_type=DeltaType.SET,
            key=key,
            value=value,
            old_value=old_value,
            version=self._version,
            node_id=self.node_id,
        )
        self._add_delta(delta)

        return delta

    def get(self, key: str, default: Any = None) -> Any:
        """الحصول على قيمة."""
        return self._state.get(key, default)

    def delete(self, key: str) -> Optional[StateDelta]:
        """حذف قيمة."""
        if key not in self._state:
            return None

        old_value = self._state.pop(key)
        self._version += 1

        delta = StateDelta(
            delta_type=DeltaType.DELETE,
            key=key,
            old_value=old_value,
            version=self._version,
            node_id=self.node_id,
        )
        self._add_delta(delta)

        return delta

    def update(self, key: str, updates: Dict[str, Any]) -> Optional[StateDelta]:
        """تحديث قيمة (للـ dict فقط)."""
        if key not in self._state or not isinstance(self._state[key], dict):
            return None

        old_value = self._state[key].copy()
        self._state[key].update(updates)
        self._version += 1

        delta = StateDelta(
            delta_type=DeltaType.UPDATE,
            key=key,
            value=updates,
            old_value=old_value,
            version=self._version,
            node_id=self.node_id,
        )
        self._add_delta(delta)

        return delta

    def keys(self) -> Set[str]:
        """مفاتيح الحالة."""
        return set(self._state.keys())

    def items(self) -> List[tuple]:
        """عناصر الحالة."""
        return list(self._state.items())

    def clear(self) -> None:
        """مسح الحالة."""
        self._state.clear()
        self._version += 1

    # =========================================================================
    # Delta Management
    # =========================================================================

    def _add_delta(self, delta: StateDelta) -> None:
        """إضافة delta."""
        self._deltas.append(delta)

        # Trim old deltas
        if len(self._deltas) > self._max_deltas:
            self._deltas = self._deltas[-self._max_deltas :]

    def get_deltas_since(self, version: int) -> List[StateDelta]:
        """الحصول على التغييرات منذ إصدار معين."""
        return [d for d in self._deltas if d.version > version]

    def apply_delta(self, delta: StateDelta) -> bool:
        """تطبيق تغيير."""
        try:
            if delta.delta_type == DeltaType.SET:
                self._state[delta.key] = delta.value

            elif delta.delta_type == DeltaType.DELETE:
                if delta.key in self._state:
                    del self._state[delta.key]

            elif delta.delta_type == DeltaType.UPDATE:
                if delta.key in self._state and isinstance(self._state[delta.key], dict):
                    self._state[delta.key].update(delta.value)

            elif delta.delta_type == DeltaType.MERGE:
                if delta.key in self._state:
                    if isinstance(self._state[delta.key], dict):
                        self._state[delta.key].update(delta.value)
                    elif isinstance(self._state[delta.key], list):
                        self._state[delta.key].extend(delta.value)
                else:
                    self._state[delta.key] = delta.value

            self._version = max(self._version, delta.version)
            return True

        except Exception as e:
            logger.error(f"Failed to apply delta: {e}")
            return False

    def apply_deltas(self, deltas: List[StateDelta]) -> int:
        """تطبيق مجموعة تغييرات."""
        # Sort by version
        sorted_deltas = sorted(deltas, key=lambda d: d.version)
        applied = 0

        for delta in sorted_deltas:
            if self.apply_delta(delta):
                applied += 1

        return applied

    # =========================================================================
    # Snapshot Management
    # =========================================================================

    def create_snapshot(self) -> StateSnapshot:
        """إنشاء لقطة."""
        snapshot = StateSnapshot(
            node_id=self.node_id,
            version=self._version,
            data=self._state.copy(),
        )
        self._snapshots.append(snapshot)

        # Trim old snapshots
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots :]

        return snapshot

    def restore_snapshot(self, snapshot: StateSnapshot) -> None:
        """استعادة من لقطة."""
        self._state = snapshot.data.copy()
        self._version = snapshot.version
        logger.info(f"Restored snapshot {snapshot.snapshot_id} (version {snapshot.version})")

    def get_latest_snapshot(self) -> Optional[StateSnapshot]:
        """الحصول على آخر لقطة."""
        return self._snapshots[-1] if self._snapshots else None

    # =========================================================================
    # Synchronization
    # =========================================================================

    def get_sync_data(self, since_version: int = 0) -> Dict[str, Any]:
        """الحصول على بيانات المزامنة."""
        if since_version > 0 and since_version < self._version:
            # Delta sync
            deltas = self.get_deltas_since(since_version)
            if deltas:
                return {
                    "type": "delta",
                    "version": self._version,
                    "checksum": self.checksum,
                    "deltas": [d.to_dict() for d in deltas],
                }

        # Full sync
        return {
            "type": "full",
            "version": self._version,
            "checksum": self.checksum,
            "state": self._state.copy(),
        }

    def apply_sync_data(self, sync_data: Dict[str, Any]) -> bool:
        """تطبيق بيانات المزامنة."""
        sync_type = sync_data.get("type", "full")
        remote_version = sync_data.get("version", 0)

        try:
            if sync_type == "delta":
                deltas = [StateDelta.from_dict(d) for d in sync_data.get("deltas", [])]
                self.apply_deltas(deltas)

            elif sync_type == "full":
                self._state = sync_data.get("state", {}).copy()
                self._version = remote_version

            # Verify checksum
            expected_checksum = sync_data.get("checksum", "")
            if expected_checksum and self.checksum != expected_checksum:
                logger.warning("Checksum mismatch after sync")
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to apply sync data: {e}")
            return False

    def diff(self, other_state: Dict[str, Any]) -> Dict[str, Any]:
        """حساب الفرق بين حالتين."""
        diff = {
            "added": {},
            "removed": [],
            "modified": {},
        }

        other_keys = set(other_state.keys())
        local_keys = set(self._state.keys())

        # Added keys
        for key in other_keys - local_keys:
            diff["added"][key] = other_state[key]

        # Removed keys
        diff["removed"] = list(local_keys - other_keys)

        # Modified keys
        for key in local_keys & other_keys:
            if self._state[key] != other_state[key]:
                diff["modified"][key] = {
                    "local": self._state[key],
                    "remote": other_state[key],
                }

        return diff

    def merge(
        self,
        other_state: Dict[str, Any],
        strategy: str = "remote_priority",
    ) -> int:
        """دمج حالة أخرى."""
        changes = 0
        diff = self.diff(other_state)

        # Apply additions
        for key, value in diff["added"].items():
            self._state[key] = value
            changes += 1

        # Handle modifications
        for key, values in diff["modified"].items():
            if strategy == "remote_priority":
                self._state[key] = values["remote"]
            elif strategy == "local_priority":
                pass  # Keep local
            elif strategy == "merge":
                local = values["local"]
                remote = values["remote"]
                if isinstance(local, dict) and isinstance(remote, dict):
                    self._state[key] = {**local, **remote}
                elif isinstance(local, list) and isinstance(remote, list):
                    self._state[key] = list(set(local + remote))
                else:
                    self._state[key] = remote
            changes += 1

        if changes > 0:
            self._version += 1

        return changes

    # =========================================================================
    # Utilities
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات الحالة."""
        return {
            "keys_count": len(self._state),
            "version": self._version,
            "checksum": self.checksum,
            "deltas_count": len(self._deltas),
            "snapshots_count": len(self._snapshots),
            "size_bytes": len(json.dumps(self._state)),
        }

    def export_state(self) -> Dict[str, Any]:
        """تصدير الحالة الكاملة."""
        return {
            "node_id": self.node_id,
            "version": self._version,
            "checksum": self.checksum,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": self._state.copy(),
        }

    def import_state(self, data: Dict[str, Any]) -> None:
        """استيراد حالة."""
        self._state = data.get("state", {}).copy()
        self._version = data.get("version", 0)
