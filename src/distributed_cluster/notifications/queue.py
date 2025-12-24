"""
Notification Queue - طابور الإشعارات
=====================================

Priority-based async notification queue with persistence support.
طابور إشعارات غير متزامن مع دعم الأولويات والحفظ.

Features:
- Priority-based ordering (higher priority first)
- Async put/get operations
- Optional SQLite persistence
- Batch operations
- Queue size limits with overflow handling
- Dead letter queue for failed notifications
"""

from __future__ import annotations

import asyncio
import heapq
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from distributed_cluster.notifications.channels import (
    DeliveryStatus,
    Notification,
    NotificationPriority,
)

logger = logging.getLogger(__name__)


class QueueOverflowPolicy(str, Enum):
    """سياسة تجاوز سعة الطابور."""

    DROP_OLDEST = "drop_oldest"      # إسقاط الأقدم
    DROP_NEWEST = "drop_newest"      # إسقاط الأحدث
    DROP_LOWEST = "drop_lowest"      # إسقاط الأقل أولوية
    BLOCK = "block"                  # انتظار حتى توفر مساحة
    RAISE = "raise"                  # رفع استثناء


class QueueFullError(Exception):
    """خطأ امتلاء الطابور."""
    pass


@dataclass(order=True)
class PrioritizedNotification:
    """
    إشعار مع أولوية للترتيب في الطابور.
    Uses negative priority for max-heap behavior with heapq.
    """

    priority_value: int = field(compare=True)
    timestamp: float = field(compare=True)
    notification: Notification = field(compare=False)

    @classmethod
    def from_notification(cls, notification: Notification) -> "PrioritizedNotification":
        """إنشاء من إشعار."""
        # Negative for max-heap (higher priority = lower number = first out)
        return cls(
            priority_value=-notification.priority.numeric_value,
            timestamp=notification.timestamp.timestamp(),
            notification=notification,
        )


class NotificationQueue:
    """
    طابور إشعارات غير متزامن مع أولويات.

    Async Priority Queue for Notifications.

    Usage:
        queue = NotificationQueue(max_size=1000)

        # Add notification
        await queue.put(notification)

        # Get next notification (blocks if empty)
        notification = await queue.get()

        # Non-blocking get
        notification = queue.get_nowait()

        # Batch operations
        notifications = await queue.get_batch(10)
    """

    def __init__(
        self,
        max_size: int = 10000,
        overflow_policy: QueueOverflowPolicy = QueueOverflowPolicy.DROP_OLDEST,
        persistence_path: Optional[Path] = None,
        auto_persist: bool = True,
    ):
        self.max_size = max_size
        self.overflow_policy = overflow_policy
        self.persistence_path = persistence_path
        self.auto_persist = auto_persist

        # Internal heap
        self._heap: List[PrioritizedNotification] = []
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition()
        self._not_full = asyncio.Condition()

        # Dead letter queue
        self._dlq: List[Notification] = []
        self._max_dlq_size = 100

        # Statistics
        self._total_enqueued = 0
        self._total_dequeued = 0
        self._total_dropped = 0

        # Persistence
        self._db: Optional[sqlite3.Connection] = None
        if persistence_path:
            self._init_persistence()

    def _init_persistence(self) -> None:
        """تهيئة قاعدة البيانات للحفظ."""
        if not self.persistence_path:
            return

        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.persistence_path))
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS notification_queue (
                id TEXT PRIMARY KEY,
                priority INTEGER,
                timestamp REAL,
                data TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_queue_priority
            ON notification_queue(priority DESC, timestamp ASC)
        """)
        self._db.commit()

        # Load persisted notifications
        self._load_from_db()

    def _load_from_db(self) -> None:
        """تحميل الإشعارات المحفوظة."""
        if not self._db:
            return

        cursor = self._db.execute(
            "SELECT data FROM notification_queue ORDER BY priority DESC, timestamp ASC"
        )
        for (data,) in cursor.fetchall():
            try:
                notif_dict = json.loads(data)
                notification = Notification.from_dict(notif_dict)
                item = PrioritizedNotification.from_notification(notification)
                heapq.heappush(self._heap, item)
            except Exception as e:
                logger.error(f"Failed to load notification from DB: {e}")

        logger.info(f"Loaded {len(self._heap)} notifications from persistence")

    async def put(
        self,
        notification: Notification,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        إضافة إشعار للطابور.

        Args:
            notification: الإشعار
            timeout: مهلة الانتظار (ثواني)

        Returns:
            True إذا تمت الإضافة بنجاح
        """
        async with self._lock:
            # Handle overflow
            if len(self._heap) >= self.max_size:
                if not await self._handle_overflow(notification, timeout):
                    return False

            # Add to heap
            item = PrioritizedNotification.from_notification(notification)
            heapq.heappush(self._heap, item)
            self._total_enqueued += 1

            # Persist
            if self.auto_persist and self._db:
                self._persist_notification(notification)

        # Signal not empty
        async with self._not_empty:
            self._not_empty.notify()

        return True

    async def _handle_overflow(
        self,
        notification: Notification,
        timeout: Optional[float],
    ) -> bool:
        """معالجة تجاوز السعة."""
        if self.overflow_policy == QueueOverflowPolicy.RAISE:
            raise QueueFullError(f"Queue full (size={self.max_size})")

        elif self.overflow_policy == QueueOverflowPolicy.DROP_NEWEST:
            # Don't add the new notification
            self._total_dropped += 1
            logger.warning(f"Dropped notification (DROP_NEWEST): {notification.notification_id}")
            return False

        elif self.overflow_policy == QueueOverflowPolicy.DROP_OLDEST:
            # Remove oldest (first in heap is highest priority, so we need to find oldest)
            if self._heap:
                oldest_idx = max(range(len(self._heap)), key=lambda i: self._heap[i].timestamp)
                dropped = self._heap.pop(oldest_idx)
                heapq.heapify(self._heap)
                self._add_to_dlq(dropped.notification)
                self._total_dropped += 1
                if self._db:
                    self._remove_from_db(dropped.notification.notification_id)
            return True

        elif self.overflow_policy == QueueOverflowPolicy.DROP_LOWEST:
            # Find and remove lowest priority
            if self._heap:
                lowest_idx = max(range(len(self._heap)), key=lambda i: -self._heap[i].priority_value)
                dropped = self._heap.pop(lowest_idx)
                heapq.heapify(self._heap)
                self._add_to_dlq(dropped.notification)
                self._total_dropped += 1
                if self._db:
                    self._remove_from_db(dropped.notification.notification_id)
            return True

        elif self.overflow_policy == QueueOverflowPolicy.BLOCK:
            # Wait for space
            async with self._not_full:
                try:
                    await asyncio.wait_for(
                        self._not_full.wait(),
                        timeout=timeout,
                    )
                    return True
                except asyncio.TimeoutError:
                    return False

        return True

    def _add_to_dlq(self, notification: Notification) -> None:
        """إضافة للـ Dead Letter Queue."""
        notification.delivery_status = DeliveryStatus.EXPIRED
        self._dlq.append(notification)
        if len(self._dlq) > self._max_dlq_size:
            self._dlq.pop(0)

    def _persist_notification(self, notification: Notification) -> None:
        """حفظ إشعار في قاعدة البيانات."""
        if not self._db:
            return

        try:
            self._db.execute(
                "INSERT OR REPLACE INTO notification_queue (id, priority, timestamp, data) VALUES (?, ?, ?, ?)",
                (
                    notification.notification_id,
                    notification.priority.numeric_value,
                    notification.timestamp.timestamp(),
                    json.dumps(notification.to_dict()),
                ),
            )
            self._db.commit()
        except Exception as e:
            logger.error(f"Failed to persist notification: {e}")

    def _remove_from_db(self, notification_id: str) -> None:
        """حذف إشعار من قاعدة البيانات."""
        if not self._db:
            return

        try:
            self._db.execute(
                "DELETE FROM notification_queue WHERE id = ?",
                (notification_id,),
            )
            self._db.commit()
        except Exception as e:
            logger.error(f"Failed to remove notification from DB: {e}")

    async def get(self, timeout: Optional[float] = None) -> Optional[Notification]:
        """
        الحصول على الإشعار التالي (ينتظر إذا كان فارغاً).

        Args:
            timeout: مهلة الانتظار

        Returns:
            الإشعار أو None إذا انتهت المهلة
        """
        async with self._not_empty:
            while not self._heap:
                try:
                    await asyncio.wait_for(
                        self._not_empty.wait(),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    return None

        async with self._lock:
            if not self._heap:
                return None

            item = heapq.heappop(self._heap)
            self._total_dequeued += 1

            # Remove from persistence
            if self._db:
                self._remove_from_db(item.notification.notification_id)

        # Signal not full
        async with self._not_full:
            self._not_full.notify()

        return item.notification

    def get_nowait(self) -> Optional[Notification]:
        """الحصول على إشعار بدون انتظار."""
        if not self._heap:
            return None

        item = heapq.heappop(self._heap)
        self._total_dequeued += 1

        if self._db:
            self._remove_from_db(item.notification.notification_id)

        return item.notification

    async def get_batch(
        self,
        max_count: int,
        timeout: Optional[float] = None,
    ) -> List[Notification]:
        """
        الحصول على دفعة من الإشعارات.

        Args:
            max_count: الحد الأقصى للعدد
            timeout: مهلة الانتظار للإشعار الأول

        Returns:
            قائمة الإشعارات
        """
        notifications = []

        # Wait for first notification
        first = await self.get(timeout=timeout)
        if first:
            notifications.append(first)

        # Get remaining without waiting
        async with self._lock:
            while len(notifications) < max_count and self._heap:
                item = heapq.heappop(self._heap)
                notifications.append(item.notification)
                self._total_dequeued += 1
                if self._db:
                    self._remove_from_db(item.notification.notification_id)

        return notifications

    async def peek(self) -> Optional[Notification]:
        """إلقاء نظرة على الإشعار التالي بدون إزالته."""
        async with self._lock:
            if self._heap:
                return self._heap[0].notification
            return None

    def clear(self) -> int:
        """مسح الطابور."""
        count = len(self._heap)
        self._heap.clear()

        if self._db:
            self._db.execute("DELETE FROM notification_queue")
            self._db.commit()

        return count

    def get_dead_letters(self) -> List[Notification]:
        """الحصول على الإشعارات الفاشلة."""
        return self._dlq.copy()

    def clear_dead_letters(self) -> int:
        """مسح الإشعارات الفاشلة."""
        count = len(self._dlq)
        self._dlq.clear()
        return count

    @property
    def size(self) -> int:
        """حجم الطابور الحالي."""
        return len(self._heap)

    @property
    def is_empty(self) -> bool:
        """هل الطابور فارغ؟"""
        return len(self._heap) == 0

    @property
    def is_full(self) -> bool:
        """هل الطابور ممتلئ؟"""
        return len(self._heap) >= self.max_size

    @property
    def stats(self) -> Dict[str, Any]:
        """إحصائيات الطابور."""
        return {
            "size": self.size,
            "max_size": self.max_size,
            "total_enqueued": self._total_enqueued,
            "total_dequeued": self._total_dequeued,
            "total_dropped": self._total_dropped,
            "dead_letters": len(self._dlq),
            "is_persistent": self._db is not None,
        }

    def close(self) -> None:
        """إغلاق الموارد."""
        if self._db:
            self._db.close()
            self._db = None


class MultiPriorityQueue:
    """
    طابور متعدد الأولويات.

    Separate queues for each priority level with weighted fair scheduling.
    """

    def __init__(
        self,
        max_size_per_priority: int = 1000,
        weights: Optional[Dict[NotificationPriority, int]] = None,
    ):
        self.max_size_per_priority = max_size_per_priority
        self.weights = weights or {
            NotificationPriority.EMERGENCY: 10,
            NotificationPriority.CRITICAL: 8,
            NotificationPriority.HIGH: 4,
            NotificationPriority.NORMAL: 2,
            NotificationPriority.LOW: 1,
        }

        self._queues: Dict[NotificationPriority, asyncio.Queue] = {
            priority: asyncio.Queue(maxsize=max_size_per_priority)
            for priority in NotificationPriority
        }

        self._counters: Dict[NotificationPriority, int] = {
            priority: 0 for priority in NotificationPriority
        }

    async def put(self, notification: Notification) -> bool:
        """إضافة إشعار."""
        queue = self._queues[notification.priority]
        try:
            queue.put_nowait(notification)
            return True
        except asyncio.QueueFull:
            return False

    async def get(self) -> Notification:
        """الحصول على إشعار مع جدولة عادلة موزونة."""
        while True:
            # Try each priority level based on weights
            for priority in sorted(
                NotificationPriority,
                key=lambda p: -self.weights.get(p, 1),
            ):
                queue = self._queues[priority]
                weight = self.weights.get(priority, 1)

                # Check if this priority should be served
                if not queue.empty():
                    self._counters[priority] += 1
                    if self._counters[priority] >= weight:
                        self._counters[priority] = 0
                    return queue.get_nowait()

            # All queues empty, wait for any
            await asyncio.sleep(0.01)

    @property
    def total_size(self) -> int:
        """الحجم الإجمالي."""
        return sum(q.qsize() for q in self._queues.values())

    def size_by_priority(self) -> Dict[str, int]:
        """الحجم لكل أولوية."""
        return {p.value: q.qsize() for p, q in self._queues.items()}
