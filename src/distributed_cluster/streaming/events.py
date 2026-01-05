"""
Event types and base classes for the streaming system.
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, Optional


class EventType(Enum):
    """Types of events in the system."""
    # System events
    SYSTEM_STARTUP = auto()
    SYSTEM_SHUTDOWN = auto()
    SYSTEM_ERROR = auto()
    SYSTEM_WARNING = auto()
    SYSTEM_INFO = auto()

    # Job events
    JOB_SUBMITTED = auto()
    JOB_STARTED = auto()
    JOB_PROGRESS = auto()
    JOB_COMPLETED = auto()
    JOB_FAILED = auto()
    JOB_CANCELLED = auto()
    JOB_RETRYING = auto()

    # Cluster events
    CLUSTER_NODE_ADDED = auto()
    CLUSTER_NODE_REMOVED = auto()
    CLUSTER_NODE_FAILED = auto()
    CLUSTER_SCALED_UP = auto()
    CLUSTER_SCALED_DOWN = auto()
    CLUSTER_REBALANCING = auto()

    # Worker events
    WORKER_STARTED = auto()
    WORKER_STOPPED = auto()
    WORKER_BUSY = auto()
    WORKER_IDLE = auto()
    WORKER_HEARTBEAT = auto()

    # Resource events
    RESOURCE_ALLOCATED = auto()
    RESOURCE_RELEASED = auto()
    RESOURCE_EXHAUSTED = auto()

    # Metric events
    METRIC_CPU = auto()
    METRIC_MEMORY = auto()
    METRIC_GPU = auto()
    METRIC_NETWORK = auto()
    METRIC_DISK = auto()
    METRIC_CUSTOM = auto()

    # Security events
    AUTH_LOGIN = auto()
    AUTH_LOGOUT = auto()
    AUTH_FAILED = auto()
    ACCESS_DENIED = auto()

    # Custom events
    CUSTOM = auto()


class EventPriority(Enum):
    """Priority levels for events."""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    DEBUG = 5


@dataclass
class EventMetadata:
    """Metadata associated with an event."""
    source: str
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventMetadata":
        return cls(**data)


@dataclass
class Event:
    """Base event class for all events in the system."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.CUSTOM
    priority: EventPriority = EventPriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.utcnow)
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: EventMetadata = field(default_factory=lambda: EventMetadata(source="unknown"))
    version: str = "1.0"

    def __post_init__(self):
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)
        if isinstance(self.event_type, str):
            self.event_type = EventType[self.event_type]
        if isinstance(self.priority, str):
            self.priority = EventPriority[self.priority]
        if isinstance(self.metadata, dict):
            self.metadata = EventMetadata.from_dict(self.metadata)

    @property
    def age_seconds(self) -> float:
        """Get the age of the event in seconds."""
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds()

    @property
    def checksum(self) -> str:
        """Calculate a checksum for the event."""
        content = (
            f"{self.event_id}:{self.event_type.name}:{self.timestamp.isoformat()}:"
            f"{json.dumps(self.payload, sort_keys=True)}"
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.name,
            "priority": self.priority.name,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "metadata": self.metadata.to_dict(),
            "version": self.version,
        }

    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=(
                EventType[data["event_type"]]
                if isinstance(data.get("event_type"), str)
                else data.get("event_type", EventType.CUSTOM)
            ),
            priority=(
                EventPriority[data["priority"]]
                if isinstance(data.get("priority"), str)
                else data.get("priority", EventPriority.NORMAL)
            ),
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if isinstance(data.get("timestamp"), str)
                else data.get("timestamp", datetime.now(timezone.utc))
            ),
            payload=data.get("payload", {}),
            metadata=(
                EventMetadata.from_dict(data["metadata"])
                if isinstance(data.get("metadata"), dict)
                else data.get("metadata", EventMetadata(source="unknown"))
            ),
            version=data.get("version", "1.0"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Event":
        """Create event from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def with_correlation(self, correlation_id: str) -> "Event":
        """Create a new event with correlation ID."""
        self.metadata.correlation_id = correlation_id
        return self

    def caused_by(self, event: "Event") -> "Event":
        """Mark this event as caused by another event."""
        self.metadata.causation_id = event.event_id
        self.metadata.correlation_id = event.metadata.correlation_id or event.event_id
        return self


@dataclass
class SystemEvent(Event):
    """System-level events."""
    component: str = "system"
    severity: str = "info"

    def __post_init__(self):
        super().__post_init__()
        self.payload["component"] = self.component
        self.payload["severity"] = self.severity


@dataclass
class JobEvent(Event):
    """Job-related events."""
    job_id: str = ""
    job_name: str = ""
    worker_id: Optional[str] = None
    progress: float = 0.0

    def __post_init__(self):
        super().__post_init__()
        self.payload["job_id"] = self.job_id
        self.payload["job_name"] = self.job_name
        if self.worker_id:
            self.payload["worker_id"] = self.worker_id
        self.payload["progress"] = self.progress


@dataclass
class ClusterEvent(Event):
    """Cluster-related events."""
    cluster_id: str = ""
    node_id: Optional[str] = None
    node_count: int = 0

    def __post_init__(self):
        super().__post_init__()
        self.payload["cluster_id"] = self.cluster_id
        if self.node_id:
            self.payload["node_id"] = self.node_id
        self.payload["node_count"] = self.node_count


@dataclass
class MetricEvent(Event):
    """Metric events for monitoring."""
    metric_name: str = ""
    metric_value: float = 0.0
    metric_unit: str = ""
    dimensions: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        super().__post_init__()
        self.event_type = EventType.METRIC_CUSTOM
        self.payload["metric_name"] = self.metric_name
        self.payload["metric_value"] = self.metric_value
        self.payload["metric_unit"] = self.metric_unit
        self.payload["dimensions"] = self.dimensions


class EventBuilder:
    """Builder pattern for creating events."""

    def __init__(self):
        self._event_type: EventType = EventType.CUSTOM
        self._priority: EventPriority = EventPriority.NORMAL
        self._payload: Dict[str, Any] = {}
        self._metadata: EventMetadata = EventMetadata(source="unknown")

    def type(self, event_type: EventType) -> "EventBuilder":
        self._event_type = event_type
        return self

    def priority(self, priority: EventPriority) -> "EventBuilder":
        self._priority = priority
        return self

    def payload(self, **kwargs) -> "EventBuilder":
        self._payload.update(kwargs)
        return self

    def source(self, source: str) -> "EventBuilder":
        self._metadata.source = source
        return self

    def correlation(self, correlation_id: str) -> "EventBuilder":
        self._metadata.correlation_id = correlation_id
        return self

    def tenant(self, tenant_id: str) -> "EventBuilder":
        self._metadata.tenant_id = tenant_id
        return self

    def user(self, user_id: str) -> "EventBuilder":
        self._metadata.user_id = user_id
        return self

    def tag(self, key: str, value: str) -> "EventBuilder":
        self._metadata.tags[key] = value
        return self

    def header(self, key: str, value: str) -> "EventBuilder":
        self._metadata.headers[key] = value
        return self

    def trace(self, trace_id: str, span_id: Optional[str] = None) -> "EventBuilder":
        self._metadata.trace_id = trace_id
        self._metadata.span_id = span_id
        return self

    def build(self) -> Event:
        return Event(
            event_type=self._event_type,
            priority=self._priority,
            payload=self._payload,
            metadata=self._metadata,
        )


def create_event(
    event_type: EventType,
    source: str,
    payload: Optional[Dict[str, Any]] = None,
    priority: EventPriority = EventPriority.NORMAL,
    **kwargs
) -> Event:
    """Factory function for creating events."""
    metadata = EventMetadata(source=source, **kwargs)
    return Event(
        event_type=event_type,
        priority=priority,
        payload=payload or {},
        metadata=metadata,
    )
