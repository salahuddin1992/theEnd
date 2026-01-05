"""
Notification History - سجل الإشعارات
=====================================

Persistent notification history with search, filtering, and analytics.
سجل إشعارات دائم مع بحث وفلترة وتحليلات.

Features:
- SQLite persistence
- Full-text search
- Time-based filtering
- Priority/category filtering
- Retention policies
- Analytics and statistics
- Export capabilities
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from distributed_cluster.notifications.channels import (
    DeliveryStatus,
    Notification,
    NotificationCategory,
    NotificationPriority,
)

logger = logging.getLogger(__name__)


class RetentionPolicy(str, Enum):
    """سياسة الاحتفاظ."""

    KEEP_ALL = "keep_all"
    DAYS_7 = "days_7"
    DAYS_30 = "days_30"
    DAYS_90 = "days_90"
    DAYS_365 = "days_365"
    MAX_COUNT = "max_count"


@dataclass
class HistoryQuery:
    """
    استعلام البحث في السجل.

    Query for searching notification history.
    """

    # Text search
    search_text: Optional[str] = None
    search_fields: List[str] = field(default_factory=lambda: ["title", "message"])

    # Filters
    priority: Optional[NotificationPriority] = None
    min_priority: Optional[NotificationPriority] = None
    category: Optional[NotificationCategory] = None
    categories: Optional[List[NotificationCategory]] = None
    status: Optional[DeliveryStatus] = None
    source: Optional[str] = None
    tags: Optional[List[str]] = None

    # Time range
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Pagination
    offset: int = 0
    limit: int = 100

    # Sorting
    order_by: str = "timestamp"
    descending: bool = True


@dataclass
class HistoryStats:
    """إحصائيات السجل."""

    total_count: int = 0
    delivered_count: int = 0
    failed_count: int = 0
    pending_count: int = 0

    by_priority: Dict[str, int] = field(default_factory=dict)
    by_category: Dict[str, int] = field(default_factory=dict)
    by_source: Dict[str, int] = field(default_factory=dict)
    by_status: Dict[str, int] = field(default_factory=dict)

    oldest_timestamp: Optional[datetime] = None
    newest_timestamp: Optional[datetime] = None

    avg_delivery_time_ms: float = 0.0
    delivery_rate: float = 0.0


class NotificationHistory:
    """
    سجل الإشعارات الدائم.

    Persistent Notification History with Full-Text Search.

    Usage:
        history = NotificationHistory(db_path=Path("notifications.db"))

        # Add notification
        await history.add(notification)

        # Search
        results = await history.search(HistoryQuery(
            search_text="error",
            priority=NotificationPriority.HIGH,
            start_time=datetime.now(timezone.utc) - timedelta(hours=24),
        ))

        # Get statistics
        stats = await history.get_stats()
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        retention_policy: RetentionPolicy = RetentionPolicy.DAYS_30,
        max_records: int = 100000,
        enable_fts: bool = True,
    ):
        self.db_path = db_path or Path("notification_history.db")
        self.retention_policy = retention_policy
        self.max_records = max_records
        self.enable_fts = enable_fts

        self._db: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """تهيئة قاعدة البيانات."""
        if self._initialized:
            return

        async with self._lock:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(self.db_path))
            self._db.row_factory = sqlite3.Row

            # Main table
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS notification_history (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT,
                    timestamp TEXT NOT NULL,
                    sent_at TEXT,
                    delivered_at TEXT,
                    delivery_status TEXT,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    tags TEXT,
                    metadata TEXT,
                    data TEXT,
                    correlation_id TEXT,
                    parent_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_timestamp
                ON notification_history(timestamp DESC)
            """)
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_priority
                ON notification_history(priority)
            """)
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_category
                ON notification_history(category)
            """)
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_status
                ON notification_history(delivery_status)
            """)
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_source
                ON notification_history(source)
            """)
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_correlation
                ON notification_history(correlation_id)
            """)

            # Full-text search
            if self.enable_fts:
                self._db.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS notification_fts USING fts5(
                        id,
                        title,
                        message,
                        tags,
                        content=notification_history,
                        content_rowid=rowid
                    )
                """)

                # Triggers for FTS sync
                self._db.execute("""
                    CREATE TRIGGER IF NOT EXISTS notification_ai AFTER INSERT ON notification_history BEGIN
                        INSERT INTO notification_fts(rowid, id, title, message, tags)
                        VALUES (NEW.rowid, NEW.id, NEW.title, NEW.message, NEW.tags);
                    END
                """)
                self._db.execute("""
                    CREATE TRIGGER IF NOT EXISTS notification_ad AFTER DELETE ON notification_history BEGIN
                        INSERT INTO notification_fts(notification_fts, rowid, id, title, message, tags)
                        VALUES('delete', OLD.rowid, OLD.id, OLD.title, OLD.message, OLD.tags);
                    END
                """)
                self._db.execute("""
                    CREATE TRIGGER IF NOT EXISTS notification_au AFTER UPDATE ON notification_history BEGIN
                        INSERT INTO notification_fts(notification_fts, rowid, id, title, message, tags)
                        VALUES('delete', OLD.rowid, OLD.id, OLD.title, OLD.message, OLD.tags);
                        INSERT INTO notification_fts(rowid, id, title, message, tags)
                        VALUES (NEW.rowid, NEW.id, NEW.title, NEW.message, NEW.tags);
                    END
                """)

            self._db.commit()
            self._initialized = True
            logger.info(f"Notification history initialized at {self.db_path}")

    async def add(self, notification: Notification) -> bool:
        """
        إضافة إشعار للسجل.

        Args:
            notification: الإشعار

        Returns:
            True إذا تمت الإضافة بنجاح
        """
        await self.initialize()

        async with self._lock:
            try:
                self._db.execute(
                    """
                    INSERT OR REPLACE INTO notification_history (
                        id, title, message, priority, category, source,
                        timestamp, sent_at, delivered_at, delivery_status,
                        error, retry_count, tags, metadata, data,
                        correlation_id, parent_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        notification.notification_id,
                        notification.title,
                        notification.message,
                        notification.priority.value,
                        notification.category.value,
                        notification.source,
                        notification.timestamp.isoformat(),
                        notification.sent_at.isoformat() if notification.sent_at else None,
                        notification.delivered_at.isoformat() if notification.delivered_at else None,
                        notification.delivery_status.value,
                        notification.error,
                        notification.retry_count,
                        json.dumps(notification.tags),
                        json.dumps(notification.metadata),
                        json.dumps(notification.data),
                        notification.correlation_id,
                        notification.parent_id,
                    ),
                )
                self._db.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to add notification to history: {e}")
                return False

    async def add_batch(self, notifications: List[Notification]) -> int:
        """إضافة دفعة من الإشعارات."""
        await self.initialize()

        added = 0
        async with self._lock:
            for notification in notifications:
                try:
                    self._db.execute(
                        """
                        INSERT OR REPLACE INTO notification_history (
                            id, title, message, priority, category, source,
                            timestamp, sent_at, delivered_at, delivery_status,
                            error, retry_count, tags, metadata, data,
                            correlation_id, parent_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            notification.notification_id,
                            notification.title,
                            notification.message,
                            notification.priority.value,
                            notification.category.value,
                            notification.source,
                            notification.timestamp.isoformat(),
                            notification.sent_at.isoformat() if notification.sent_at else None,
                            notification.delivered_at.isoformat() if notification.delivered_at else None,
                            notification.delivery_status.value,
                            notification.error,
                            notification.retry_count,
                            json.dumps(notification.tags),
                            json.dumps(notification.metadata),
                            json.dumps(notification.data),
                            notification.correlation_id,
                            notification.parent_id,
                        ),
                    )
                    added += 1
                except Exception as e:
                    logger.error(f"Failed to add notification: {e}")

            self._db.commit()

        return added

    async def get(self, notification_id: str) -> Optional[Notification]:
        """الحصول على إشعار بالمعرف."""
        await self.initialize()

        async with self._lock:
            cursor = self._db.execute(
                "SELECT * FROM notification_history WHERE id = ?",
                (notification_id,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_notification(row)
            return None

    async def search(self, query: HistoryQuery) -> List[Notification]:
        """
        البحث في السجل.

        Args:
            query: استعلام البحث

        Returns:
            قائمة الإشعارات المطابقة
        """
        await self.initialize()

        conditions = []
        params = []

        # Full-text search
        if query.search_text and self.enable_fts:
            # Use FTS table
            conditions.append("""
                id IN (
                    SELECT id FROM notification_fts
                    WHERE notification_fts MATCH ?
                )
            """)
            params.append(query.search_text)

        # Priority filter
        if query.priority:
            conditions.append("priority = ?")
            params.append(query.priority.value)
        elif query.min_priority:
            # Map priority to numeric for comparison
            priority_order = {
                "low": 1, "normal": 2, "high": 3, "critical": 4, "emergency": 5
            }
            min_val = priority_order.get(query.min_priority.value, 1)
            valid_priorities = [
                p for p, v in priority_order.items() if v >= min_val
            ]
            placeholders = ",".join("?" * len(valid_priorities))
            conditions.append(f"priority IN ({placeholders})")
            params.extend(valid_priorities)

        # Category filter
        if query.category:
            conditions.append("category = ?")
            params.append(query.category.value)
        elif query.categories:
            placeholders = ",".join("?" * len(query.categories))
            conditions.append(f"category IN ({placeholders})")
            params.extend([c.value for c in query.categories])

        # Status filter
        if query.status:
            conditions.append("delivery_status = ?")
            params.append(query.status.value)

        # Source filter
        if query.source:
            conditions.append("source = ?")
            params.append(query.source)

        # Tags filter
        if query.tags:
            tag_conditions = []
            for tag in query.tags:
                tag_conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')
            conditions.append(f"({' OR '.join(tag_conditions)})")

        # Time range
        if query.start_time:
            conditions.append("timestamp >= ?")
            params.append(query.start_time.isoformat())
        if query.end_time:
            conditions.append("timestamp <= ?")
            params.append(query.end_time.isoformat())

        # Build query
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        order_dir = "DESC" if query.descending else "ASC"

        sql = f"""
            SELECT * FROM notification_history
            WHERE {where_clause}
            ORDER BY {query.order_by} {order_dir}
            LIMIT ? OFFSET ?
        """
        params.extend([query.limit, query.offset])

        async with self._lock:
            cursor = self._db.execute(sql, params)
            rows = cursor.fetchall()
            return [self._row_to_notification(row) for row in rows]

    async def count(self, query: Optional[HistoryQuery] = None) -> int:
        """عدد الإشعارات المطابقة."""
        await self.initialize()

        if not query:
            async with self._lock:
                cursor = self._db.execute("SELECT COUNT(*) FROM notification_history")
                return cursor.fetchone()[0]

        # Build conditions from query (simplified)
        conditions = []
        params = []

        if query.priority:
            conditions.append("priority = ?")
            params.append(query.priority.value)
        if query.category:
            conditions.append("category = ?")
            params.append(query.category.value)
        if query.status:
            conditions.append("delivery_status = ?")
            params.append(query.status.value)
        if query.start_time:
            conditions.append("timestamp >= ?")
            params.append(query.start_time.isoformat())
        if query.end_time:
            conditions.append("timestamp <= ?")
            params.append(query.end_time.isoformat())

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        async with self._lock:
            cursor = self._db.execute(
                f"SELECT COUNT(*) FROM notification_history WHERE {where_clause}",
                params,
            )
            return cursor.fetchone()[0]

    async def get_recent(
        self,
        limit: int = 50,
        priority: Optional[NotificationPriority] = None,
    ) -> List[Notification]:
        """الحصول على أحدث الإشعارات."""
        query = HistoryQuery(
            limit=limit,
            priority=priority,
            order_by="timestamp",
            descending=True,
        )
        return await self.search(query)

    async def get_by_correlation(
        self,
        correlation_id: str,
    ) -> List[Notification]:
        """الحصول على الإشعارات المرتبطة."""
        await self.initialize()

        async with self._lock:
            cursor = self._db.execute(
                """
                SELECT * FROM notification_history
                WHERE correlation_id = ?
                ORDER BY timestamp ASC
                """,
                (correlation_id,),
            )
            return [self._row_to_notification(row) for row in cursor.fetchall()]

    async def get_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> HistoryStats:
        """الحصول على إحصائيات السجل."""
        await self.initialize()

        stats = HistoryStats()

        time_condition = "1=1"
        params = []
        if start_time:
            time_condition += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        if end_time:
            time_condition += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        async with self._lock:
            # Total count
            cursor = self._db.execute(
                f"SELECT COUNT(*) FROM notification_history WHERE {time_condition}",
                params,
            )
            stats.total_count = cursor.fetchone()[0]

            # By status
            cursor = self._db.execute(
                f"""
                SELECT delivery_status, COUNT(*) as cnt
                FROM notification_history
                WHERE {time_condition}
                GROUP BY delivery_status
                """,
                params,
            )
            for row in cursor.fetchall():
                status = row["delivery_status"] or "unknown"
                stats.by_status[status] = row["cnt"]
                if status == "delivered":
                    stats.delivered_count = row["cnt"]
                elif status == "failed":
                    stats.failed_count = row["cnt"]
                elif status == "pending":
                    stats.pending_count = row["cnt"]

            # By priority
            cursor = self._db.execute(
                f"""
                SELECT priority, COUNT(*) as cnt
                FROM notification_history
                WHERE {time_condition}
                GROUP BY priority
                """,
                params,
            )
            stats.by_priority = {row["priority"]: row["cnt"] for row in cursor.fetchall()}

            # By category
            cursor = self._db.execute(
                f"""
                SELECT category, COUNT(*) as cnt
                FROM notification_history
                WHERE {time_condition}
                GROUP BY category
                """,
                params,
            )
            stats.by_category = {row["category"]: row["cnt"] for row in cursor.fetchall()}

            # By source
            cursor = self._db.execute(
                f"""
                SELECT source, COUNT(*) as cnt
                FROM notification_history
                WHERE {time_condition}
                GROUP BY source
                ORDER BY cnt DESC
                LIMIT 20
                """,
                params,
            )
            stats.by_source = {row["source"] or "unknown": row["cnt"] for row in cursor.fetchall()}

            # Time range
            cursor = self._db.execute(
                f"SELECT MIN(timestamp), MAX(timestamp) FROM notification_history WHERE {time_condition}",
                params,
            )
            row = cursor.fetchone()
            if row[0]:
                stats.oldest_timestamp = datetime.fromisoformat(row[0])
            if row[1]:
                stats.newest_timestamp = datetime.fromisoformat(row[1])

            # Delivery rate
            if stats.total_count > 0:
                stats.delivery_rate = stats.delivered_count / stats.total_count * 100

        return stats

    async def delete(self, notification_id: str) -> bool:
        """حذف إشعار."""
        await self.initialize()

        async with self._lock:
            cursor = self._db.execute(
                "DELETE FROM notification_history WHERE id = ?",
                (notification_id,),
            )
            self._db.commit()
            return cursor.rowcount > 0

    async def delete_before(self, timestamp: datetime) -> int:
        """حذف الإشعارات قبل تاريخ معين."""
        await self.initialize()

        async with self._lock:
            cursor = self._db.execute(
                "DELETE FROM notification_history WHERE timestamp < ?",
                (timestamp.isoformat(),),
            )
            self._db.commit()
            return cursor.rowcount

    async def apply_retention(self) -> int:
        """تطبيق سياسة الاحتفاظ."""
        await self.initialize()

        deleted = 0

        # Time-based retention
        retention_days = {
            RetentionPolicy.DAYS_7: 7,
            RetentionPolicy.DAYS_30: 30,
            RetentionPolicy.DAYS_90: 90,
            RetentionPolicy.DAYS_365: 365,
        }

        if self.retention_policy in retention_days:
            days = retention_days[self.retention_policy]
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            deleted += await self.delete_before(cutoff)

        # Count-based retention
        if self.retention_policy == RetentionPolicy.MAX_COUNT or self.max_records:
            async with self._lock:
                count = await self.count()
                if count > self.max_records:
                    excess = count - self.max_records
                    cursor = self._db.execute(
                        """
                        DELETE FROM notification_history
                        WHERE id IN (
                            SELECT id FROM notification_history
                            ORDER BY timestamp ASC
                            LIMIT ?
                        )
                        """,
                        (excess,),
                    )
                    self._db.commit()
                    deleted += cursor.rowcount

        return deleted

    async def export_json(
        self,
        output_path: Path,
        query: Optional[HistoryQuery] = None,
    ) -> int:
        """تصدير الإشعارات لملف JSON."""
        notifications = await self.search(query or HistoryQuery(limit=100000))

        data = [n.to_dict() for n in notifications]

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return len(data)

    async def export_csv(
        self,
        output_path: Path,
        query: Optional[HistoryQuery] = None,
    ) -> int:
        """تصدير الإشعارات لملف CSV."""
        import csv

        notifications = await self.search(query or HistoryQuery(limit=100000))

        headers = [
            "id", "title", "message", "priority", "category",
            "source", "timestamp", "delivery_status", "error",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            for n in notifications:
                writer.writerow([
                    n.notification_id,
                    n.title,
                    n.message,
                    n.priority.value,
                    n.category.value,
                    n.source,
                    n.timestamp.isoformat(),
                    n.delivery_status.value,
                    n.error or "",
                ])

        return len(notifications)

    def _row_to_notification(self, row: sqlite3.Row) -> Notification:
        """تحويل صف قاعدة البيانات لإشعار."""
        return Notification(
            notification_id=row["id"],
            title=row["title"],
            message=row["message"],
            priority=NotificationPriority(row["priority"]),
            category=NotificationCategory(row["category"]),
            source=row["source"] or "unknown",
            timestamp=datetime.fromisoformat(row["timestamp"]),
            sent_at=datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None,
            delivered_at=datetime.fromisoformat(row["delivered_at"]) if row["delivered_at"] else None,
            delivery_status=(
                DeliveryStatus(row["delivery_status"])
                if row["delivery_status"]
                else DeliveryStatus.PENDING
            ),
            error=row["error"],
            retry_count=row["retry_count"] or 0,
            tags=json.loads(row["tags"]) if row["tags"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            data=json.loads(row["data"]) if row["data"] else {},
            correlation_id=row["correlation_id"],
            parent_id=row["parent_id"],
        )

    async def close(self) -> None:
        """إغلاق قاعدة البيانات."""
        if self._db:
            self._db.close()
            self._db = None
            self._initialized = False

    async def __aenter__(self) -> "NotificationHistory":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
