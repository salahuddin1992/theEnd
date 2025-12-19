"""
Audit Logging - سجل التدقيق
============================

Comprehensive audit logging for security and compliance.
تسجيل تدقيق شامل للأمان والامتثال.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    """أنواع الإجراءات المسجلة."""
    # Authentication
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_TOKEN_CREATED = "auth.token_created"
    AUTH_TOKEN_REVOKED = "auth.token_revoked"
    AUTH_TOKEN_EXPIRED = "auth.token_expired"
    AUTH_PERMISSION_DENIED = "auth.permission_denied"

    # Worker management
    WORKER_REGISTERED = "worker.registered"
    WORKER_UNREGISTERED = "worker.unregistered"
    WORKER_ENROLLMENT_APPROVED = "worker.enrollment_approved"
    WORKER_ENROLLMENT_REJECTED = "worker.enrollment_rejected"
    WORKER_DRAINED = "worker.drained"
    WORKER_UNDRAINED = "worker.undrained"

    # Job operations
    JOB_SUBMITTED = "job.submitted"
    JOB_CANCELLED = "job.cancelled"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_RETRIED = "job.retried"

    # Configuration changes
    CONFIG_CHANGED = "config.changed"
    CONFIG_POLICY_CHANGED = "config.policy_changed"
    CONFIG_SECRET_ACCESSED = "config.secret_accessed"

    # Admin actions
    ADMIN_USER_CREATED = "admin.user_created"
    ADMIN_USER_DELETED = "admin.user_deleted"
    ADMIN_ROLE_CHANGED = "admin.role_changed"
    ADMIN_PERMISSION_GRANTED = "admin.permission_granted"
    ADMIN_PERMISSION_REVOKED = "admin.permission_revoked"

    # System events
    SYSTEM_STARTED = "system.started"
    SYSTEM_STOPPED = "system.stopped"
    SYSTEM_ERROR = "system.error"
    SYSTEM_BACKUP = "system.backup"


class AuditResult(str, Enum):
    """نتيجة الإجراء."""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


@dataclass
class AuditEvent:
    """حدث تدقيق واحد."""
    event_id: str
    timestamp: datetime
    action: AuditAction
    result: AuditResult

    # Who performed the action
    actor_id: Optional[str] = None
    actor_type: Optional[str] = None  # user, worker, system, api_key
    actor_role: Optional[str] = None
    actor_ip: Optional[str] = None

    # What was affected
    resource_type: Optional[str] = None  # job, worker, user, config
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None

    # Additional context
    details: Dict[str, Any] = field(default_factory=dict)
    changes: Dict[str, Any] = field(default_factory=dict)  # before/after for changes
    error_message: Optional[str] = None

    # Metadata
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    source: str = "api"  # api, cli, internal, hook

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        result["action"] = self.action.value
        result["result"] = self.result.value
        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AuditEvent:
        """Create from dictionary."""
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        data["action"] = AuditAction(data["action"])
        data["result"] = AuditResult(data["result"])
        return cls(**data)


class AuditBackend:
    """Base class for audit storage backends."""

    async def write(self, event: AuditEvent) -> None:
        """Write an audit event."""
        raise NotImplementedError

    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        result: Optional[AuditResult] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query audit events."""
        raise NotImplementedError

    async def count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        result: Optional[AuditResult] = None,
    ) -> int:
        """Count matching events."""
        raise NotImplementedError


class MemoryAuditBackend(AuditBackend):
    """In-memory audit backend for development/testing."""

    def __init__(self, max_events: int = 10000):
        self._events: List[AuditEvent] = []
        self._max_events = max_events
        self._lock = asyncio.Lock()

    async def write(self, event: AuditEvent) -> None:
        """Write an audit event."""
        async with self._lock:
            self._events.append(event)
            # Trim old events if exceeded
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]

    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        result: Optional[AuditResult] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query audit events."""
        async with self._lock:
            filtered = self._events.copy()

        # Apply filters
        if start_time:
            filtered = [e for e in filtered if e.timestamp >= start_time]
        if end_time:
            filtered = [e for e in filtered if e.timestamp <= end_time]
        if action:
            filtered = [e for e in filtered if e.action == action]
        if actor_id:
            filtered = [e for e in filtered if e.actor_id == actor_id]
        if resource_type:
            filtered = [e for e in filtered if e.resource_type == resource_type]
        if resource_id:
            filtered = [e for e in filtered if e.resource_id == resource_id]
        if result:
            filtered = [e for e in filtered if e.result == result]

        # Sort by timestamp descending
        filtered.sort(key=lambda e: e.timestamp, reverse=True)

        # Paginate
        return filtered[offset:offset + limit]

    async def count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        result: Optional[AuditResult] = None,
    ) -> int:
        """Count matching events."""
        events = await self.query(
            start_time=start_time,
            end_time=end_time,
            action=action,
            result=result,
            limit=999999,
        )
        return len(events)


class FileAuditBackend(AuditBackend):
    """File-based audit backend with JSON lines format."""

    def __init__(self, log_dir: str | Path, rotate_size_mb: int = 100):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._rotate_size_mb = rotate_size_mb
        self._current_file: Optional[Path] = None
        self._lock = asyncio.Lock()

    def _get_current_file(self) -> Path:
        """Get current log file path."""
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        return self._log_dir / f"audit-{date_str}.jsonl"

    async def write(self, event: AuditEvent) -> None:
        """Write an audit event."""
        async with self._lock:
            log_file = self._get_current_file()

            # Check rotation
            if log_file.exists():
                size_mb = log_file.stat().st_size / (1024 * 1024)
                if size_mb >= self._rotate_size_mb:
                    # Rotate by adding timestamp
                    ts = datetime.utcnow().strftime("%H%M%S")
                    rotated = log_file.with_suffix(f".{ts}.jsonl")
                    log_file.rename(rotated)

            # Write event
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")

    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        result: Optional[AuditResult] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query audit events from files."""
        events = []

        # Get relevant log files
        log_files = sorted(self._log_dir.glob("audit-*.jsonl"), reverse=True)

        for log_file in log_files:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        event = AuditEvent.from_dict(data)

                        # Apply filters
                        if start_time and event.timestamp < start_time:
                            continue
                        if end_time and event.timestamp > end_time:
                            continue
                        if action and event.action != action:
                            continue
                        if actor_id and event.actor_id != actor_id:
                            continue
                        if resource_type and event.resource_type != resource_type:
                            continue
                        if resource_id and event.resource_id != resource_id:
                            continue
                        if result and event.result != result:
                            continue

                        events.append(event)

                    except (json.JSONDecodeError, KeyError):
                        continue

            # Early exit if we have enough
            if len(events) >= offset + limit:
                break

        # Sort and paginate
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[offset:offset + limit]

    async def count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        result: Optional[AuditResult] = None,
    ) -> int:
        """Count matching events."""
        events = await self.query(
            start_time=start_time,
            end_time=end_time,
            action=action,
            result=result,
            limit=999999,
        )
        return len(events)


class AuditLogger:
    """
    Audit Logger - مسجل التدقيق.

    Central audit logging for the distributed cluster.

    Example:
        audit = AuditLogger()

        # Log a job submission
        await audit.log(
            action=AuditAction.JOB_SUBMITTED,
            result=AuditResult.SUCCESS,
            actor_id="user-123",
            actor_type="user",
            resource_type="job",
            resource_id="job-456",
            details={"command": "python train.py"}
        )

        # Query audit logs
        events = await audit.query(
            action=AuditAction.AUTH_LOGIN_FAILED,
            start_time=datetime.utcnow() - timedelta(hours=24),
            limit=100,
        )
    """

    def __init__(
        self,
        backend: Optional[AuditBackend] = None,
        enabled: bool = True,
    ):
        self._backend = backend or MemoryAuditBackend()
        self._enabled = enabled
        self._handlers: List[Callable[[AuditEvent], None]] = []

    def add_handler(self, handler: Callable[[AuditEvent], None]) -> None:
        """Add a handler to be called for each event."""
        self._handlers.append(handler)

    async def log(
        self,
        action: AuditAction,
        result: AuditResult,
        actor_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        actor_role: Optional[str] = None,
        actor_ip: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        changes: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        source: str = "api",
    ) -> AuditEvent:
        """
        Log an audit event.

        Args:
            action: The action being performed
            result: The result of the action
            actor_id: ID of who performed the action
            actor_type: Type of actor (user, worker, system)
            resource_type: Type of resource affected
            resource_id: ID of resource affected
            details: Additional details
            changes: Before/after for configuration changes

        Returns:
            The created AuditEvent
        """
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            action=action,
            result=result,
            actor_id=actor_id,
            actor_type=actor_type,
            actor_role=actor_role,
            actor_ip=actor_ip,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            details=details or {},
            changes=changes or {},
            error_message=error_message,
            session_id=session_id,
            request_id=request_id,
            source=source,
        )

        if self._enabled:
            await self._backend.write(event)

            # Call handlers
            for handler in self._handlers:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Audit handler error: {e}")

        # Also log to standard logger
        log_level = logging.INFO if result == AuditResult.SUCCESS else logging.WARNING
        logger.log(
            log_level,
            f"AUDIT: {action.value} {result.value} "
            f"actor={actor_id} resource={resource_type}:{resource_id}"
        )

        return event

    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        result: Optional[AuditResult] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query audit events."""
        return await self._backend.query(
            start_time=start_time,
            end_time=end_time,
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            limit=limit,
            offset=offset,
        )

    async def count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        result: Optional[AuditResult] = None,
    ) -> int:
        """Count matching events."""
        return await self._backend.count(
            start_time=start_time,
            end_time=end_time,
            action=action,
            result=result,
        )

    # Convenience methods for common actions

    async def log_login(
        self,
        user_id: str,
        success: bool,
        ip_address: Optional[str] = None,
        error: Optional[str] = None,
    ) -> AuditEvent:
        """Log a login attempt."""
        return await self.log(
            action=AuditAction.AUTH_LOGIN if success else AuditAction.AUTH_LOGIN_FAILED,
            result=AuditResult.SUCCESS if success else AuditResult.FAILURE,
            actor_id=user_id,
            actor_type="user",
            actor_ip=ip_address,
            error_message=error,
        )

    async def log_permission_denied(
        self,
        actor_id: str,
        actor_type: str,
        permission: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> AuditEvent:
        """Log a permission denied event."""
        return await self.log(
            action=AuditAction.AUTH_PERMISSION_DENIED,
            result=AuditResult.DENIED,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            details={"permission": permission},
        )

    async def log_job_submitted(
        self,
        job_id: str,
        user_id: str,
        job_name: Optional[str] = None,
        command: Optional[str] = None,
    ) -> AuditEvent:
        """Log a job submission."""
        return await self.log(
            action=AuditAction.JOB_SUBMITTED,
            result=AuditResult.SUCCESS,
            actor_id=user_id,
            actor_type="user",
            resource_type="job",
            resource_id=job_id,
            resource_name=job_name,
            details={"command": command} if command else {},
        )

    async def log_config_change(
        self,
        actor_id: str,
        config_key: str,
        old_value: Any,
        new_value: Any,
    ) -> AuditEvent:
        """Log a configuration change."""
        return await self.log(
            action=AuditAction.CONFIG_CHANGED,
            result=AuditResult.SUCCESS,
            actor_id=actor_id,
            actor_type="user",
            resource_type="config",
            resource_id=config_key,
            changes={
                "before": old_value,
                "after": new_value,
            },
        )


# Global audit logger instance
_default_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the default audit logger instance."""
    global _default_audit_logger
    if _default_audit_logger is None:
        _default_audit_logger = AuditLogger()
    return _default_audit_logger


def set_audit_logger(logger: AuditLogger) -> None:
    """Set the default audit logger instance."""
    global _default_audit_logger
    _default_audit_logger = logger
