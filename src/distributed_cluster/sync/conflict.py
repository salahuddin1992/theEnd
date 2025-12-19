"""
Conflict Resolution - حل التعارضات
===================================

Advanced conflict resolution for distributed systems:
- Vector clocks for causality tracking
- Multiple resolution strategies
- CRDT support (Conflict-free Replicated Data Types)
- Merge algorithms
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ConflictStrategy(str, Enum):
    """استراتيجيات حل التعارض."""

    LAST_WRITE_WINS = "last_write_wins"  # الكتابة الأخيرة تفوز
    FIRST_WRITE_WINS = "first_write_wins"  # الكتابة الأولى تفوز
    LOCAL_PRIORITY = "local_priority"  # أولوية للمحلي
    REMOTE_PRIORITY = "remote_priority"  # أولوية للبعيد
    MERGE = "merge"  # دمج القيم
    CUSTOM = "custom"  # معالج مخصص
    MANUAL = "manual"  # تدخل يدوي


@dataclass
class VectorClock:
    """
    ساعة متجهة لتتبع السببية.

    Vector clock for tracking causality in distributed systems.
    Each node maintains its own counter, incremented on each update.
    """

    clocks: Dict[str, int] = field(default_factory=dict)

    def increment(self, node_id: str) -> None:
        """زيادة ساعة عقدة."""
        self.clocks[node_id] = self.clocks.get(node_id, 0) + 1

    def update(self, other: VectorClock) -> None:
        """تحديث من ساعة أخرى."""
        for node_id, value in other.clocks.items():
            self.clocks[node_id] = max(self.clocks.get(node_id, 0), value)

    def compare(self, other: VectorClock) -> str:
        """
        مقارنة مع ساعة أخرى.

        Returns:
            "before": self happened before other
            "after": self happened after other
            "concurrent": concurrent (conflict possible)
            "equal": identical
        """
        self_greater = False
        other_greater = False

        all_nodes = set(self.clocks.keys()) | set(other.clocks.keys())

        for node_id in all_nodes:
            self_val = self.clocks.get(node_id, 0)
            other_val = other.clocks.get(node_id, 0)

            if self_val > other_val:
                self_greater = True
            elif self_val < other_val:
                other_greater = True

        if self_greater and not other_greater:
            return "after"
        elif other_greater and not self_greater:
            return "before"
        elif not self_greater and not other_greater:
            return "equal"
        else:
            return "concurrent"

    def copy(self) -> VectorClock:
        """نسخ الساعة."""
        return VectorClock(clocks=self.clocks.copy())

    def to_dict(self) -> Dict[str, int]:
        """تحويل إلى dictionary."""
        return self.clocks.copy()

    @classmethod
    def from_dict(cls, d: Dict[str, int]) -> VectorClock:
        """إنشاء من dictionary."""
        return cls(clocks=d.copy())

    def __str__(self) -> str:
        return str(self.clocks)


@dataclass
class Conflict:
    """تعارض في البيانات."""

    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    key: str = ""
    local_value: Any = None
    remote_value: Any = None
    local_clock: Optional[VectorClock] = None
    remote_clock: Optional[VectorClock] = None
    local_node: str = ""
    remote_node: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolution: Optional[Any] = None
    resolution_strategy: Optional[ConflictStrategy] = None

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        return {
            "conflict_id": self.conflict_id,
            "key": self.key,
            "local_value": self.local_value,
            "remote_value": self.remote_value,
            "local_clock": self.local_clock.to_dict() if self.local_clock else None,
            "remote_clock": self.remote_clock.to_dict() if self.remote_clock else None,
            "local_node": self.local_node,
            "remote_node": self.remote_node,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolution": self.resolution,
            "resolution_strategy": self.resolution_strategy.value if self.resolution_strategy else None,
        }


class ConflictResolver:
    """
    محلل التعارضات.

    Handles conflict detection and resolution in distributed systems.

    Supports:
    - Multiple resolution strategies
    - Custom resolvers
    - CRDT-like merge operations
    - Conflict logging and auditing
    """

    def __init__(
        self,
        node_id: str,
        default_strategy: ConflictStrategy = ConflictStrategy.LAST_WRITE_WINS,
    ):
        self.node_id = node_id
        self.default_strategy = default_strategy

        # Vector clock for this node
        self._clock = VectorClock()
        self._clock.increment(node_id)

        # Custom resolvers per key pattern
        self._custom_resolvers: Dict[str, Callable] = {}

        # Conflict history
        self._conflicts: List[Conflict] = []
        self._unresolved: Dict[str, Conflict] = {}

    @property
    def clock(self) -> VectorClock:
        """الساعة المتجهة الحالية."""
        return self._clock

    # =========================================================================
    # Clock Management
    # =========================================================================

    def tick(self) -> VectorClock:
        """زيادة الساعة وإرجاع نسخة."""
        self._clock.increment(self.node_id)
        return self._clock.copy()

    def merge_clock(self, other: VectorClock) -> None:
        """دمج ساعة أخرى."""
        self._clock.update(other)
        self._clock.increment(self.node_id)

    # =========================================================================
    # Conflict Detection
    # =========================================================================

    def detect_conflict(
        self,
        key: str,
        local_value: Any,
        remote_value: Any,
        local_clock: Optional[VectorClock] = None,
        remote_clock: Optional[VectorClock] = None,
        remote_node: str = "",
    ) -> Optional[Conflict]:
        """
        اكتشاف تعارض.

        Returns Conflict if conflict detected, None otherwise.
        """
        # Same value = no conflict
        if self._values_equal(local_value, remote_value):
            return None

        # Check causality with vector clocks
        if local_clock and remote_clock:
            relation = local_clock.compare(remote_clock)

            if relation == "before":
                # Remote is newer - no conflict, just update
                return None
            elif relation == "after":
                # Local is newer - no conflict
                return None
            elif relation == "equal":
                # Same version but different values - rare but possible
                pass
            # "concurrent" = potential conflict

        # Conflict detected
        conflict = Conflict(
            key=key,
            local_value=local_value,
            remote_value=remote_value,
            local_clock=local_clock.copy() if local_clock else None,
            remote_clock=remote_clock.copy() if remote_clock else None,
            local_node=self.node_id,
            remote_node=remote_node,
        )

        self._conflicts.append(conflict)
        self._unresolved[conflict.conflict_id] = conflict

        logger.warning(f"Conflict detected for key '{key}' with node {remote_node}")

        return conflict

    def _values_equal(self, a: Any, b: Any) -> bool:
        """مقارنة قيمتين."""
        try:
            return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        except (TypeError, ValueError):
            return a == b

    # =========================================================================
    # Conflict Resolution
    # =========================================================================

    def resolve(
        self,
        conflict: Conflict,
        strategy: Optional[ConflictStrategy] = None,
    ) -> Any:
        """
        حل تعارض.

        Returns the resolved value.
        """
        strategy = strategy or self.default_strategy

        # Check for custom resolver
        for pattern, resolver in self._custom_resolvers.items():
            if conflict.key.startswith(pattern) or pattern == "*":
                resolved = resolver(conflict)
                conflict.resolved = True
                conflict.resolution = resolved
                conflict.resolution_strategy = ConflictStrategy.CUSTOM
                self._unresolved.pop(conflict.conflict_id, None)
                return resolved

        # Apply strategy
        if strategy == ConflictStrategy.LAST_WRITE_WINS:
            resolved = self._resolve_last_write_wins(conflict)

        elif strategy == ConflictStrategy.FIRST_WRITE_WINS:
            resolved = self._resolve_first_write_wins(conflict)

        elif strategy == ConflictStrategy.LOCAL_PRIORITY:
            resolved = conflict.local_value

        elif strategy == ConflictStrategy.REMOTE_PRIORITY:
            resolved = conflict.remote_value

        elif strategy == ConflictStrategy.MERGE:
            resolved = self._resolve_merge(conflict)

        elif strategy == ConflictStrategy.MANUAL:
            # Don't resolve automatically
            return None

        else:
            resolved = conflict.remote_value  # Default

        conflict.resolved = True
        conflict.resolution = resolved
        conflict.resolution_strategy = strategy
        self._unresolved.pop(conflict.conflict_id, None)

        logger.info(f"Resolved conflict {conflict.conflict_id} using {strategy.value}")

        return resolved

    def _resolve_last_write_wins(self, conflict: Conflict) -> Any:
        """حل بالكتابة الأخيرة."""
        if conflict.local_clock and conflict.remote_clock:
            # Compare timestamps in clocks
            local_sum = sum(conflict.local_clock.clocks.values())
            remote_sum = sum(conflict.remote_clock.clocks.values())

            if remote_sum > local_sum:
                return conflict.remote_value
            elif local_sum > remote_sum:
                return conflict.local_value

        # Default to remote (assume network delay means remote is newer)
        return conflict.remote_value

    def _resolve_first_write_wins(self, conflict: Conflict) -> Any:
        """حل بالكتابة الأولى."""
        if conflict.local_clock and conflict.remote_clock:
            local_sum = sum(conflict.local_clock.clocks.values())
            remote_sum = sum(conflict.remote_clock.clocks.values())

            if local_sum < remote_sum:
                return conflict.local_value
            elif remote_sum < local_sum:
                return conflict.remote_value

        return conflict.local_value

    def _resolve_merge(self, conflict: Conflict) -> Any:
        """حل بالدمج."""
        local = conflict.local_value
        remote = conflict.remote_value

        # Dict merge
        if isinstance(local, dict) and isinstance(remote, dict):
            return self._merge_dicts(local, remote)

        # List merge (union)
        if isinstance(local, list) and isinstance(remote, list):
            return self._merge_lists(local, remote)

        # Set merge
        if isinstance(local, set) and isinstance(remote, set):
            return local | remote

        # Numeric - take max
        if isinstance(local, (int, float)) and isinstance(remote, (int, float)):
            return max(local, remote)

        # String - concatenate with separator
        if isinstance(local, str) and isinstance(remote, str):
            if local == remote:
                return local
            return f"{local} | {remote}"

        # Default to remote
        return remote

    def _merge_dicts(self, local: Dict, remote: Dict) -> Dict:
        """دمج قاموسين."""
        result = copy.deepcopy(local)

        for key, remote_value in remote.items():
            if key not in result:
                result[key] = remote_value
            else:
                local_value = result[key]

                # Recursive merge for nested dicts
                if isinstance(local_value, dict) and isinstance(remote_value, dict):
                    result[key] = self._merge_dicts(local_value, remote_value)
                elif isinstance(local_value, list) and isinstance(remote_value, list):
                    result[key] = self._merge_lists(local_value, remote_value)
                else:
                    # Take remote for non-collection types
                    result[key] = remote_value

        return result

    def _merge_lists(self, local: List, remote: List) -> List:
        """دمج قائمتين (إزالة التكرار)."""
        try:
            # Try set union for hashable items
            return list(set(local) | set(remote))
        except TypeError:
            # For non-hashable items, use JSON for dedup
            seen = set()
            result = []
            for item in local + remote:
                item_key = json.dumps(item, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
                if item_key not in seen:
                    seen.add(item_key)
                    result.append(item)
            return result

    # =========================================================================
    # Custom Resolvers
    # =========================================================================

    def register_resolver(
        self,
        key_pattern: str,
        resolver: Callable[[Conflict], Any],
    ) -> None:
        """
        تسجيل محلل مخصص.

        Args:
            key_pattern: Pattern to match keys (prefix or "*" for all)
            resolver: Function that takes Conflict and returns resolved value
        """
        self._custom_resolvers[key_pattern] = resolver
        logger.info(f"Registered custom resolver for pattern: {key_pattern}")

    def unregister_resolver(self, key_pattern: str) -> None:
        """إلغاء تسجيل محلل مخصص."""
        self._custom_resolvers.pop(key_pattern, None)

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    def resolve_all_pending(
        self,
        strategy: Optional[ConflictStrategy] = None,
    ) -> Dict[str, Any]:
        """
        حل جميع التعارضات المعلقة.

        Returns dict of {key: resolved_value}
        """
        results = {}

        for conflict_id, conflict in list(self._unresolved.items()):
            resolved = self.resolve(conflict, strategy)
            if resolved is not None:
                results[conflict.key] = resolved

        return results

    def get_pending_conflicts(self) -> List[Conflict]:
        """الحصول على التعارضات المعلقة."""
        return list(self._unresolved.values())

    def get_conflict_history(
        self,
        limit: int = 100,
        resolved_only: bool = False,
    ) -> List[Conflict]:
        """الحصول على سجل التعارضات."""
        conflicts = self._conflicts

        if resolved_only:
            conflicts = [c for c in conflicts if c.resolved]

        return conflicts[-limit:]

    # =========================================================================
    # Manual Resolution
    # =========================================================================

    def manually_resolve(
        self,
        conflict_id: str,
        value: Any,
    ) -> bool:
        """حل تعارض يدوياً."""
        conflict = self._unresolved.get(conflict_id)
        if not conflict:
            return False

        conflict.resolved = True
        conflict.resolution = value
        conflict.resolution_strategy = ConflictStrategy.MANUAL
        self._unresolved.pop(conflict_id, None)

        logger.info(f"Manually resolved conflict: {conflict_id}")
        return True

    def discard_conflict(self, conflict_id: str) -> bool:
        """تجاهل تعارض (استخدام القيمة المحلية)."""
        conflict = self._unresolved.get(conflict_id)
        if not conflict:
            return False

        conflict.resolved = True
        conflict.resolution = conflict.local_value
        conflict.resolution_strategy = ConflictStrategy.LOCAL_PRIORITY
        self._unresolved.pop(conflict_id, None)

        return True

    # =========================================================================
    # Stats & Info
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات."""
        return {
            "node_id": self.node_id,
            "default_strategy": self.default_strategy.value,
            "clock": self._clock.to_dict(),
            "total_conflicts": len(self._conflicts),
            "pending_conflicts": len(self._unresolved),
            "resolved_conflicts": sum(1 for c in self._conflicts if c.resolved),
            "custom_resolvers": len(self._custom_resolvers),
        }


# ============================================================================
# CRDT Types (Conflict-free Replicated Data Types)
# ============================================================================


class GCounter:
    """
    عداد متنامي (Grow-only Counter).

    CRDT that only supports increment operations.
    Always converges to the same value across nodes.
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        self._counts: Dict[str, int] = {}

    def increment(self, amount: int = 1) -> None:
        """زيادة العداد."""
        self._counts[self.node_id] = self._counts.get(self.node_id, 0) + amount

    @property
    def value(self) -> int:
        """القيمة الحالية."""
        return sum(self._counts.values())

    def merge(self, other: GCounter) -> None:
        """دمج مع عداد آخر."""
        for node_id, count in other._counts.items():
            self._counts[node_id] = max(self._counts.get(node_id, 0), count)

    def to_dict(self) -> Dict[str, int]:
        return self._counts.copy()

    @classmethod
    def from_dict(cls, node_id: str, d: Dict[str, int]) -> GCounter:
        counter = cls(node_id)
        counter._counts = d.copy()
        return counter


class PNCounter:
    """
    عداد زيادة/نقصان (Positive-Negative Counter).

    CRDT that supports both increment and decrement.
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        self._positive = GCounter(node_id)
        self._negative = GCounter(node_id)

    def increment(self, amount: int = 1) -> None:
        """زيادة."""
        self._positive.increment(amount)

    def decrement(self, amount: int = 1) -> None:
        """نقصان."""
        self._negative.increment(amount)

    @property
    def value(self) -> int:
        """القيمة الحالية."""
        return self._positive.value - self._negative.value

    def merge(self, other: PNCounter) -> None:
        """دمج."""
        self._positive.merge(other._positive)
        self._negative.merge(other._negative)


class LWWRegister:
    """
    سجل الكتابة الأخيرة (Last-Write-Wins Register).

    CRDT register where the last write wins based on timestamp.
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        self._value: Any = None
        self._timestamp: float = 0

    def set(self, value: Any, timestamp: Optional[float] = None) -> None:
        """تعيين قيمة."""
        import time

        ts = timestamp or time.time()

        if ts >= self._timestamp:
            self._value = value
            self._timestamp = ts

    @property
    def value(self) -> Any:
        """القيمة الحالية."""
        return self._value

    def merge(self, other: LWWRegister) -> None:
        """دمج."""
        if other._timestamp > self._timestamp:
            self._value = other._value
            self._timestamp = other._timestamp


class GSet:
    """
    مجموعة متنامية (Grow-only Set).

    CRDT set that only supports add operations.
    """

    def __init__(self):
        self._items: Set[Any] = set()

    def add(self, item: Any) -> None:
        """إضافة عنصر."""
        self._items.add(item)

    def contains(self, item: Any) -> bool:
        """هل يحتوي على عنصر؟"""
        return item in self._items

    @property
    def items(self) -> Set[Any]:
        """العناصر."""
        return self._items.copy()

    def merge(self, other: GSet) -> None:
        """دمج."""
        self._items |= other._items
