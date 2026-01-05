"""
Secure Session Management - إدارة الجلسات الآمنة
==================================================

Comprehensive session management with device tracking and anomaly detection.
إدارة جلسات شاملة مع تتبع الأجهزة واكتشاف الشذوذ.

Features:
- Session creation and validation
- Device fingerprinting
- Concurrent session limits
- Session hijacking detection
- Geographic anomaly detection
- Activity tracking
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    """Session status."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    LOCKED = "locked"


class SessionEvent(str, Enum):
    """Session events for audit."""

    CREATED = "session.created"
    RENEWED = "session.renewed"
    EXPIRED = "session.expired"
    REVOKED = "session.revoked"
    MFA_VERIFIED = "session.mfa_verified"
    SUSPICIOUS_ACTIVITY = "session.suspicious_activity"
    DEVICE_CHANGED = "session.device_changed"
    IP_CHANGED = "session.ip_changed"


@dataclass
class DeviceFingerprint:
    """Device fingerprint for session binding."""

    fingerprint_id: str
    user_agent: str
    accept_language: Optional[str] = None
    screen_resolution: Optional[str] = None
    timezone: Optional[str] = None
    platform: Optional[str] = None
    plugins_hash: Optional[str] = None
    canvas_hash: Optional[str] = None
    webgl_hash: Optional[str] = None

    # Computed fields
    fingerprint_hash: str = ""

    def __post_init__(self):
        if not self.fingerprint_hash:
            self.fingerprint_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute a stable fingerprint hash."""
        data = {
            "user_agent": self.user_agent,
            "accept_language": self.accept_language,
            "platform": self.platform,
            "timezone": self.timezone,
        }
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:32]

    def similarity(self, other: DeviceFingerprint) -> float:
        """Calculate similarity score (0.0 to 1.0)."""
        score = 0.0
        fields = [
            ("user_agent", 0.4),
            ("accept_language", 0.1),
            ("timezone", 0.2),
            ("platform", 0.2),
            ("screen_resolution", 0.1),
        ]

        for field_name, weight in fields:
            if getattr(self, field_name) == getattr(other, field_name):
                score += weight

        return score

    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> DeviceFingerprint:
        """Create fingerprint from HTTP headers."""
        return cls(
            fingerprint_id=secrets.token_hex(8),
            user_agent=headers.get("user-agent", ""),
            accept_language=headers.get("accept-language"),
            platform=cls._extract_platform(headers.get("user-agent", "")),
        )

    @staticmethod
    def _extract_platform(user_agent: str) -> Optional[str]:
        """Extract platform from user agent."""
        ua_lower = user_agent.lower()
        if "windows" in ua_lower:
            return "windows"
        elif "mac" in ua_lower:
            return "macos"
        elif "linux" in ua_lower:
            return "linux"
        elif "android" in ua_lower:
            return "android"
        elif "iphone" in ua_lower or "ipad" in ua_lower:
            return "ios"
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint_id": self.fingerprint_id,
            "fingerprint_hash": self.fingerprint_hash,
            "user_agent": self.user_agent,
            "platform": self.platform,
            "timezone": self.timezone,
        }


@dataclass
class GeoLocation:
    """Geographic location data."""

    country_code: Optional[str] = None
    country_name: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def distance_km(self, other: GeoLocation) -> Optional[float]:
        """Calculate distance in kilometers."""
        if not all([self.latitude, self.longitude, other.latitude, other.longitude]):
            return None

        import math

        lat1 = math.radians(self.latitude)
        lat2 = math.radians(other.latitude)
        dlat = math.radians(other.latitude - self.latitude)
        dlon = math.radians(other.longitude - self.longitude)

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return 6371 * c  # Earth's radius in km


@dataclass
class SessionActivity:
    """Session activity record."""

    timestamp: datetime
    action: str
    resource: Optional[str] = None
    ip_address: Optional[str] = None
    success: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """User session."""

    session_id: str
    user_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24))
    last_activity: datetime = field(default_factory=datetime.utcnow)
    status: SessionStatus = SessionStatus.ACTIVE

    # Authentication state
    authenticated_at: datetime = field(default_factory=datetime.utcnow)
    mfa_verified: bool = False
    mfa_verified_at: Optional[datetime] = None

    # Device and location binding
    ip_address: Optional[str] = None
    device_fingerprint: Optional[DeviceFingerprint] = None
    geo_location: Optional[GeoLocation] = None

    # Security tracking
    ip_history: List[str] = field(default_factory=list)
    suspicious_flags: List[str] = field(default_factory=list)
    activity_log: List[SessionActivity] = field(default_factory=list)

    # Metadata
    user_agent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE and not self.is_expired

    @property
    def age_seconds(self) -> int:
        return int((datetime.now(timezone.utc) - self.created_at).total_seconds())

    @property
    def idle_seconds(self) -> int:
        return int((datetime.now(timezone.utc) - self.last_activity).total_seconds())

    def update_activity(self, action: str, ip_address: Optional[str] = None) -> None:
        """Update session activity."""
        self.last_activity = datetime.now(timezone.utc)

        if ip_address and ip_address != self.ip_address:
            if self.ip_address:
                self.ip_history.append(self.ip_address)
            self.ip_address = ip_address

        self.activity_log.append(
            SessionActivity(
                timestamp=datetime.now(timezone.utc),
                action=action,
                ip_address=ip_address,
            )
        )

        # Limit activity log size
        if len(self.activity_log) > 1000:
            self.activity_log = self.activity_log[-500:]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "status": self.status.value,
            "mfa_verified": self.mfa_verified,
            "ip_address": self.ip_address,
            "device": self.device_fingerprint.to_dict() if self.device_fingerprint else None,
            "is_active": self.is_active,
            "age_seconds": self.age_seconds,
            "idle_seconds": self.idle_seconds,
        }


@dataclass
class SessionConfig:
    """Session configuration."""

    # Timeouts
    session_lifetime_hours: int = 24
    idle_timeout_minutes: int = 30
    mfa_session_lifetime_hours: int = 12
    absolute_timeout_hours: int = 72  # Max session age

    # Security
    bind_to_ip: bool = False  # Strict IP binding
    bind_to_device: bool = True  # Device fingerprint binding
    detect_anomalies: bool = True

    # Limits
    max_concurrent_sessions: int = 5
    max_sessions_per_device: int = 3

    # Anomaly detection thresholds
    max_ip_changes_per_hour: int = 3
    suspicious_geo_distance_km: float = 500.0
    min_time_between_locations_hours: float = 0.5

    # Token settings
    session_id_length: int = 32


class SessionStore(ABC):
    """Abstract session store."""

    @abstractmethod
    def create(self, session: Session) -> bool:
        pass

    @abstractmethod
    def get(self, session_id: str) -> Optional[Session]:
        pass

    @abstractmethod
    def update(self, session: Session) -> bool:
        pass

    @abstractmethod
    def delete(self, session_id: str) -> bool:
        pass

    @abstractmethod
    def get_user_sessions(self, user_id: str) -> List[Session]:
        pass

    @abstractmethod
    def delete_user_sessions(self, user_id: str) -> int:
        pass

    @abstractmethod
    def cleanup_expired(self) -> int:
        pass


class MemorySessionStore(SessionStore):
    """In-memory session store."""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()

    def create(self, session: Session) -> bool:
        with self._lock:
            if session.session_id in self._sessions:
                return False
            self._sessions[session.session_id] = session
            self._user_sessions[session.user_id].add(session.session_id)
            return True

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def update(self, session: Session) -> bool:
        with self._lock:
            if session.session_id not in self._sessions:
                return False
            self._sessions[session.session_id] = session
            return True

    def delete(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                self._user_sessions[session.user_id].discard(session_id)
                return True
            return False

    def get_user_sessions(self, user_id: str) -> List[Session]:
        with self._lock:
            session_ids = self._user_sessions.get(user_id, set())
            return [self._sessions[sid] for sid in session_ids if sid in self._sessions]

    def delete_user_sessions(self, user_id: str) -> int:
        with self._lock:
            session_ids = self._user_sessions.get(user_id, set()).copy()
            count = 0
            for sid in session_ids:
                if self.delete(sid):
                    count += 1
            return count

    def cleanup_expired(self) -> int:
        with self._lock:
            expired = [sid for sid, session in self._sessions.items() if session.is_expired]
            for sid in expired:
                self.delete(sid)
            return len(expired)


class SessionManager:
    """
    Secure Session Manager.

    Handles session lifecycle, validation, and security.
    """

    def __init__(
        self,
        store: Optional[SessionStore] = None,
        config: Optional[SessionConfig] = None,
        event_handler: Optional[Callable[[SessionEvent, Session, Dict], None]] = None,
    ):
        self.store = store or MemorySessionStore()
        self.config = config or SessionConfig()
        self.event_handler = event_handler
        self._lock = threading.RLock()

    def _generate_session_id(self) -> str:
        """Generate a secure session ID."""
        return secrets.token_urlsafe(self.config.session_id_length)

    def _emit_event(self, event: SessionEvent, session: Session, data: Dict = None) -> None:
        """Emit a session event."""
        if self.event_handler:
            try:
                self.event_handler(event, session, data or {})
            except Exception as e:
                logger.error(f"Session event handler error: {e}")

    def create_session(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        device_fingerprint: Optional[DeviceFingerprint] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Session, Optional[str]]:
        """
        Create a new session.

        Returns:
            (session, error_message)
        """
        # Check concurrent session limit
        existing_sessions = self.store.get_user_sessions(user_id)
        active_sessions = [s for s in existing_sessions if s.is_active]

        if len(active_sessions) >= self.config.max_concurrent_sessions:
            # Revoke oldest session
            oldest = min(active_sessions, key=lambda s: s.created_at)
            self.revoke_session(oldest.session_id, reason="max_sessions_exceeded")

        # Create device fingerprint from user agent if not provided
        if not device_fingerprint and user_agent:
            device_fingerprint = DeviceFingerprint.from_headers({"user-agent": user_agent})

        session = Session(
            session_id=self._generate_session_id(),
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=self.config.session_lifetime_hours),
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint,
            metadata=metadata or {},
        )

        if ip_address:
            session.ip_history.append(ip_address)

        self.store.create(session)
        self._emit_event(SessionEvent.CREATED, session)

        logger.info(f"Created session {session.session_id[:8]}... for user {user_id}")
        return session, None

    def validate_session(
        self,
        session_id: str,
        ip_address: Optional[str] = None,
        device_fingerprint: Optional[DeviceFingerprint] = None,
        update_activity: bool = True,
    ) -> Tuple[Optional[Session], Optional[str]]:
        """
        Validate a session.

        Returns:
            (session, error_message)
        """
        session = self.store.get(session_id)

        if not session:
            return None, "Session not found"

        # Check status
        if session.status == SessionStatus.REVOKED:
            return None, "Session revoked"

        if session.status == SessionStatus.LOCKED:
            return None, "Session locked due to suspicious activity"

        # Check expiration
        if session.is_expired:
            session.status = SessionStatus.EXPIRED
            self.store.update(session)
            self._emit_event(SessionEvent.EXPIRED, session)
            return None, "Session expired"

        # Check idle timeout
        if session.idle_seconds > self.config.idle_timeout_minutes * 60:
            session.status = SessionStatus.EXPIRED
            self.store.update(session)
            return None, "Session timed out due to inactivity"

        # Check absolute timeout
        if session.age_seconds > self.config.absolute_timeout_hours * 3600:
            session.status = SessionStatus.EXPIRED
            self.store.update(session)
            return None, "Session exceeded maximum lifetime"

        # Security checks
        if self.config.detect_anomalies:
            anomaly = self._detect_anomalies(session, ip_address, device_fingerprint)
            if anomaly:
                session.suspicious_flags.append(f"{datetime.now(timezone.utc).isoformat()}: {anomaly}")
                self._emit_event(SessionEvent.SUSPICIOUS_ACTIVITY, session, {"anomaly": anomaly})

                # Lock session on critical anomalies
                if "critical" in anomaly.lower():
                    session.status = SessionStatus.LOCKED
                    self.store.update(session)
                    return None, f"Session locked: {anomaly}"

        # IP binding check
        if self.config.bind_to_ip and ip_address:
            if session.ip_address and session.ip_address != ip_address:
                return None, "IP address mismatch"

        # Device binding check
        if self.config.bind_to_device and device_fingerprint:
            if session.device_fingerprint:
                similarity = session.device_fingerprint.similarity(device_fingerprint)
                if similarity < 0.5:
                    session.suspicious_flags.append(f"{datetime.now(timezone.utc).isoformat()}: Device change detected")
                    self._emit_event(SessionEvent.DEVICE_CHANGED, session)

        # Update activity
        if update_activity:
            session.update_activity("validate", ip_address)
            self.store.update(session)

        return session, None

    def _detect_anomalies(
        self,
        session: Session,
        ip_address: Optional[str],
        device_fingerprint: Optional[DeviceFingerprint],
    ) -> Optional[str]:
        """Detect security anomalies."""
        anomalies = []

        # Check IP changes frequency
        if ip_address and session.ip_address and ip_address != session.ip_address:
            recent_ips = session.ip_history[-10:]  # Last 10 IPs
            if len(set(recent_ips)) >= self.config.max_ip_changes_per_hour:
                anomalies.append("Frequent IP address changes")

        # Check device fingerprint changes
        if device_fingerprint and session.device_fingerprint:
            similarity = session.device_fingerprint.similarity(device_fingerprint)
            if similarity < 0.3:
                anomalies.append("Critical: Significant device change detected")

        # Check for impossible travel (if geo available)
        if session.geo_location and session.geo_location.latitude:
            # This would require IP-to-geo lookup
            pass

        return "; ".join(anomalies) if anomalies else None

    def refresh_session(
        self,
        session_id: str,
        extend_hours: Optional[int] = None,
    ) -> Tuple[Optional[Session], Optional[str]]:
        """
        Refresh/extend a session.

        Returns:
            (session, error_message)
        """
        session, error = self.validate_session(session_id, update_activity=False)
        if error:
            return None, error

        extension = extend_hours or self.config.session_lifetime_hours
        new_expiry = datetime.now(timezone.utc) + timedelta(hours=extension)

        # Don't extend beyond absolute timeout
        max_expiry = session.created_at + timedelta(hours=self.config.absolute_timeout_hours)
        session.expires_at = min(new_expiry, max_expiry)

        session.update_activity("refresh")
        self.store.update(session)
        self._emit_event(SessionEvent.RENEWED, session)

        return session, None

    def set_mfa_verified(
        self,
        session_id: str,
    ) -> Tuple[Optional[Session], Optional[str]]:
        """
        Mark session as MFA verified.

        Returns:
            (session, error_message)
        """
        session, error = self.validate_session(session_id, update_activity=False)
        if error:
            return None, error

        session.mfa_verified = True
        session.mfa_verified_at = datetime.now(timezone.utc)

        # Optionally extend session for MFA-verified users
        session.expires_at = datetime.now(timezone.utc) + timedelta(hours=self.config.mfa_session_lifetime_hours)

        session.update_activity("mfa_verify")
        self.store.update(session)
        self._emit_event(SessionEvent.MFA_VERIFIED, session)

        return session, None

    def revoke_session(
        self,
        session_id: str,
        reason: str = "user_logout",
    ) -> bool:
        """Revoke a session."""
        session = self.store.get(session_id)
        if not session:
            return False

        session.status = SessionStatus.REVOKED
        session.metadata["revocation_reason"] = reason
        session.metadata["revoked_at"] = datetime.now(timezone.utc).isoformat()

        self.store.update(session)
        self._emit_event(SessionEvent.REVOKED, session, {"reason": reason})

        logger.info(f"Revoked session {session_id[:8]}... : {reason}")
        return True

    def revoke_all_user_sessions(
        self,
        user_id: str,
        except_session_id: Optional[str] = None,
        reason: str = "user_logout_all",
    ) -> int:
        """Revoke all sessions for a user."""
        sessions = self.store.get_user_sessions(user_id)
        count = 0

        for session in sessions:
            if session.session_id == except_session_id:
                continue
            if self.revoke_session(session.session_id, reason):
                count += 1

        return count

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self.store.get(session_id)

    def get_user_sessions(self, user_id: str) -> List[Session]:
        """Get all sessions for a user."""
        return self.store.get_user_sessions(user_id)

    def get_active_user_sessions(self, user_id: str) -> List[Session]:
        """Get active sessions for a user."""
        sessions = self.store.get_user_sessions(user_id)
        return [s for s in sessions if s.is_active]

    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        return self.store.cleanup_expired()


class SessionTokenManager:
    """
    Manages session tokens (cookies, JWT).

    Provides secure token generation and validation.
    """

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        token_lifetime_hours: int = 24,
    ):
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key
        self.algorithm = algorithm
        self.token_lifetime_hours = token_lifetime_hours

    def create_token(
        self,
        session_id: str,
        user_id: str,
        extra_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a signed session token."""
        import hashlib
        import hmac

        now = int(time.time())
        payload = {
            "sid": session_id,
            "uid": user_id,
            "iat": now,
            "exp": now + (self.token_lifetime_hours * 3600),
            **(extra_claims or {}),
        }

        # Encode payload
        payload_json = json.dumps(payload, sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")

        # Sign
        signature = hmac.new(self.secret_key, payload_b64.encode(), hashlib.sha256).hexdigest()

        return f"{payload_b64}.{signature}"

    def verify_token(self, token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Verify a session token.

        Returns:
            (payload, error_message)
        """
        import hashlib
        import hmac

        try:
            parts = token.split(".")
            if len(parts) != 2:
                return None, "Invalid token format"

            payload_b64, signature = parts

            # Verify signature
            expected_sig = hmac.new(self.secret_key, payload_b64.encode(), hashlib.sha256).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return None, "Invalid signature"

            # Decode payload
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            payload_json = base64.urlsafe_b64decode(payload_b64).decode()
            payload = json.loads(payload_json)

            # Check expiration
            if time.time() > payload.get("exp", 0):
                return None, "Token expired"

            return payload, None

        except Exception as e:
            return None, f"Token verification failed: {e}"

    def refresh_token(self, token: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Refresh a session token.

        Returns:
            (new_token, error_message)
        """
        payload, error = self.verify_token(token)
        if error:
            return None, error

        return (
            self.create_token(
                session_id=payload["sid"],
                user_id=payload["uid"],
                extra_claims={k: v for k, v in payload.items() if k not in ["sid", "uid", "iat", "exp"]},
            ),
            None,
        )


def create_session_manager(
    config: Optional[SessionConfig] = None,
    store: Optional[SessionStore] = None,
) -> SessionManager:
    """Create a session manager instance."""
    return SessionManager(store=store, config=config)
