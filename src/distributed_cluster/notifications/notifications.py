"""
Notification Models - نماذج الإشعارات
=====================================

Core notification types and data models.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class NotificationType(str, Enum):
    """Types of notifications."""

    # System notifications
    SYSTEM_ALERT = "system.alert"
    SYSTEM_UPDATE = "system.update"
    SYSTEM_MAINTENANCE = "system.maintenance"

    # Job notifications
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"
    JOB_PROGRESS = "job.progress"

    # Worker notifications
    WORKER_JOINED = "worker.joined"
    WORKER_LEFT = "worker.left"
    WORKER_UNHEALTHY = "worker.unhealthy"
    WORKER_RECOVERED = "worker.recovered"

    # User notifications
    USER_MENTION = "user.mention"
    USER_ASSIGNMENT = "user.assignment"
    USER_INVITATION = "user.invitation"

    # Security notifications
    SECURITY_ALERT = "security.alert"
    SECURITY_LOGIN = "security.login"
    SECURITY_PASSWORD_CHANGE = "security.password_change"

    # Resource notifications
    RESOURCE_LIMIT = "resource.limit"
    RESOURCE_QUOTA = "resource.quota"
    RESOURCE_USAGE = "resource.usage"

    # Custom
    CUSTOM = "custom"


class NotificationPriority(str, Enum):
    """Notification priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class NotificationStatus(str, Enum):
    """Notification delivery status."""

    PENDING = "pending"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class NotificationMetadata:
    """Additional notification metadata."""

    source: str = ""
    source_id: str = ""
    category: str = ""
    tags: List[str] = field(default_factory=list)

    # Tracking
    correlation_id: Optional[str] = None
    parent_id: Optional[str] = None

    # Display
    icon: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = None

    # Actions
    action_url: Optional[str] = None
    actions: List[Dict[str, Any]] = field(default_factory=list)

    # Expiration
    expires_at: Optional[datetime] = None

    # Custom data
    custom: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "source_id": self.source_id,
            "category": self.category,
            "tags": self.tags,
            "correlation_id": self.correlation_id,
            "parent_id": self.parent_id,
            "icon": self.icon,
            "color": self.color,
            "image_url": self.image_url,
            "action_url": self.action_url,
            "actions": self.actions,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "custom": self.custom,
        }


@dataclass
class Notification:
    """
    Represents a single notification.

    Example:
        notification = Notification(
            notification_id=str(uuid.uuid4()),
            notification_type=NotificationType.JOB_COMPLETED,
            recipient_id="user-123",
            title="Job Completed",
            body="Your job 'train-model' has finished successfully.",
            priority=NotificationPriority.NORMAL,
            data={"job_id": "job-456", "duration": 3600}
        )
    """

    notification_id: str
    notification_type: NotificationType
    recipient_id: str
    title: str
    body: str

    # Priority and status
    priority: NotificationPriority = NotificationPriority.NORMAL
    status: NotificationStatus = NotificationStatus.PENDING

    # Channels
    channels: List[str] = field(default_factory=lambda: ["in_app"])

    # Content
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: NotificationMetadata = field(default_factory=NotificationMetadata)

    # Sender
    sender_id: Optional[str] = None
    sender_type: str = "system"  # system, user, service

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None

    # Delivery tracking
    delivery_attempts: int = 0
    last_error: Optional[str] = None
    channel_status: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls, notification_type: NotificationType, recipient_id: str, title: str, body: str, **kwargs
    ) -> Notification:
        """Factory method to create a notification."""
        return cls(
            notification_id=str(uuid.uuid4()),
            notification_type=notification_type,
            recipient_id=recipient_id,
            title=title,
            body=body,
            **kwargs,
        )

    def mark_sent(self, channel: Optional[str] = None) -> None:
        """Mark notification as sent."""
        self.status = NotificationStatus.SENT
        self.sent_at = datetime.now(timezone.utc)
        if channel:
            self.channel_status[channel] = "sent"

    def mark_delivered(self, channel: Optional[str] = None) -> None:
        """Mark notification as delivered."""
        self.status = NotificationStatus.DELIVERED
        self.delivered_at = datetime.now(timezone.utc)
        if channel:
            self.channel_status[channel] = "delivered"

    def mark_read(self) -> None:
        """Mark notification as read."""
        self.status = NotificationStatus.READ
        self.read_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str, channel: Optional[str] = None) -> None:
        """Mark notification as failed."""
        self.status = NotificationStatus.FAILED
        self.last_error = error
        if channel:
            self.channel_status[channel] = f"failed: {error}"

    def is_expired(self) -> bool:
        """Check if notification has expired."""
        if self.metadata.expires_at:
            return datetime.now(timezone.utc) > self.metadata.expires_at
        return False

    def should_send(self) -> bool:
        """Check if notification should be sent."""
        if self.is_expired():
            return False
        if self.status in (
            NotificationStatus.SENT,
            NotificationStatus.DELIVERED,
            NotificationStatus.READ,
            NotificationStatus.CANCELLED,
        ):
            return False
        if self.scheduled_at and datetime.now(timezone.utc) < self.scheduled_at:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "notification_id": self.notification_id,
            "notification_type": self.notification_type.value,
            "recipient_id": self.recipient_id,
            "title": self.title,
            "body": self.body,
            "priority": self.priority.value,
            "status": self.status.value,
            "channels": self.channels,
            "data": self.data,
            "metadata": self.metadata.to_dict(),
            "sender_id": self.sender_id,
            "sender_type": self.sender_type,
            "created_at": self.created_at.isoformat(),
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "delivery_attempts": self.delivery_attempts,
            "channel_status": self.channel_status,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Notification:
        """Create from dictionary."""
        data = data.copy()
        data["notification_type"] = NotificationType(data["notification_type"])
        data["priority"] = NotificationPriority(data["priority"])
        data["status"] = NotificationStatus(data["status"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])

        if data.get("scheduled_at"):
            data["scheduled_at"] = datetime.fromisoformat(data["scheduled_at"])
        if data.get("sent_at"):
            data["sent_at"] = datetime.fromisoformat(data["sent_at"])
        if data.get("delivered_at"):
            data["delivered_at"] = datetime.fromisoformat(data["delivered_at"])
        if data.get("read_at"):
            data["read_at"] = datetime.fromisoformat(data["read_at"])

        metadata_dict = data.pop("metadata", {})
        if metadata_dict.get("expires_at"):
            metadata_dict["expires_at"] = datetime.fromisoformat(metadata_dict["expires_at"])
        data["metadata"] = NotificationMetadata(**metadata_dict)

        return cls(**data)


@dataclass
class NotificationBatch:
    """A batch of notifications for bulk operations."""

    batch_id: str
    notifications: List[Notification]
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Status tracking
    total: int = 0
    sent: int = 0
    failed: int = 0

    def __post_init__(self):
        self.total = len(self.notifications)

    @classmethod
    def create(cls, notifications: List[Notification]) -> NotificationBatch:
        return cls(
            batch_id=str(uuid.uuid4()),
            notifications=notifications,
        )

    def update_stats(self) -> None:
        """Update batch statistics."""
        self.sent = sum(
            1 for n in self.notifications if n.status in (NotificationStatus.SENT, NotificationStatus.DELIVERED)
        )
        self.failed = sum(1 for n in self.notifications if n.status == NotificationStatus.FAILED)

    @property
    def progress(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.sent + self.failed) / self.total

    @property
    def is_complete(self) -> bool:
        return (self.sent + self.failed) >= self.total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "total": self.total,
            "sent": self.sent,
            "failed": self.failed,
            "progress": self.progress,
            "is_complete": self.is_complete,
            "created_at": self.created_at.isoformat(),
        }
