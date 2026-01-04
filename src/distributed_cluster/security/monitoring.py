"""
Security Monitoring & Threat Detection - مراقبة الأمان واكتشاف التهديدات
=========================================================================

Real-time security monitoring and threat detection for the cluster.
مراقبة الأمان في الوقت الفعلي واكتشاف التهديدات للمجموعة.

Features:
- Failed authentication tracking
- Brute force detection
- Anomaly detection
- Security event correlation
- Real-time alerting
- Threat intelligence integration
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ThreatLevel(str, Enum):
    """Threat severity levels."""
    CRITICAL = "critical"  # Immediate action required
    HIGH = "high"  # Urgent attention needed
    MEDIUM = "medium"  # Should be investigated
    LOW = "low"  # Informational
    INFO = "info"  # Normal activity logging


class ThreatType(str, Enum):
    """Types of security threats."""
    BRUTE_FORCE = "brute_force"
    CREDENTIAL_STUFFING = "credential_stuffing"
    SESSION_HIJACK = "session_hijack"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    DATA_EXFILTRATION = "data_exfiltration"
    DENIAL_OF_SERVICE = "denial_of_service"
    MALICIOUS_PAYLOAD = "malicious_payload"
    INSIDER_THREAT = "insider_threat"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    CERTIFICATE_VIOLATION = "certificate_violation"
    POLICY_VIOLATION = "policy_violation"


class SecurityEventType(str, Enum):
    """Security event types."""
    AUTH_SUCCESS = "auth.success"
    AUTH_FAILURE = "auth.failure"
    AUTH_LOCKOUT = "auth.lockout"
    MFA_SUCCESS = "mfa.success"
    MFA_FAILURE = "mfa.failure"
    SESSION_CREATE = "session.create"
    SESSION_DESTROY = "session.destroy"
    SESSION_ANOMALY = "session.anomaly"
    ACCESS_GRANTED = "access.granted"
    ACCESS_DENIED = "access.denied"
    PRIVILEGE_CHANGE = "privilege.change"
    CONFIG_CHANGE = "config.change"
    CERT_ISSUED = "cert.issued"
    CERT_REVOKED = "cert.revoked"
    POLICY_MATCH = "policy.match"
    RATE_LIMIT_HIT = "rate_limit.hit"
    ANOMALY_DETECTED = "anomaly.detected"


@dataclass
class SecurityEvent:
    """Security event record."""
    event_id: str
    event_type: SecurityEventType
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Actor information
    actor_id: Optional[str] = None
    actor_type: Optional[str] = None  # user, worker, api_key, system
    actor_ip: Optional[str] = None

    # Target information
    target_type: Optional[str] = None
    target_id: Optional[str] = None

    # Event details
    success: bool = True
    details: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "actor_ip": self.actor_ip,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "success": self.success,
            "details": self.details,
        }


@dataclass
class SecurityAlert:
    """Security alert."""
    alert_id: str
    threat_type: ThreatType
    threat_level: ThreatLevel
    title: str
    description: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Context
    source_events: List[str] = field(default_factory=list)
    affected_actors: List[str] = field(default_factory=list)
    affected_resources: List[str] = field(default_factory=list)

    # Status
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    false_positive: bool = False

    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    auto_actions_taken: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "threat_type": self.threat_type.value,
            "threat_level": self.threat_level.value,
            "title": self.title,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "source_events": self.source_events,
            "affected_actors": self.affected_actors,
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
            "recommendations": self.recommendations,
        }


@dataclass
class MonitoringConfig:
    """Security monitoring configuration."""
    # Brute force detection
    auth_failure_threshold: int = 5  # Failures before alert
    auth_failure_window_seconds: int = 300  # 5 minutes
    lockout_duration_seconds: int = 900  # 15 minutes

    # Rate limiting
    request_rate_threshold: int = 100  # Requests per window
    request_rate_window_seconds: int = 60

    # Anomaly detection
    baseline_period_hours: int = 24
    anomaly_std_threshold: float = 3.0

    # Alert settings
    alert_cooldown_seconds: int = 300  # Min time between similar alerts
    critical_alert_actions: List[str] = field(default_factory=lambda: ["lockout", "notify"])

    # Retention
    event_retention_hours: int = 168  # 7 days
    alert_retention_days: int = 90


class ThreatDetector(ABC):
    """Abstract threat detector."""

    @abstractmethod
    def analyze(self, event: SecurityEvent) -> Optional[SecurityAlert]:
        """Analyze event and return alert if threat detected."""
        pass

    @abstractmethod
    def reset(self, actor_id: str) -> None:
        """Reset tracking for an actor."""
        pass


class BruteForceDetector(ThreatDetector):
    """Detects brute force authentication attacks."""

    def __init__(self, config: MonitoringConfig):
        self.config = config
        self._failures: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._lockouts: Dict[str, float] = {}
        self._lock = threading.RLock()

    def analyze(self, event: SecurityEvent) -> Optional[SecurityAlert]:
        if event.event_type != SecurityEventType.AUTH_FAILURE:
            return None

        actor_key = event.actor_ip or event.actor_id or "unknown"

        with self._lock:
            now = time.time()

            # Check if already locked out
            if actor_key in self._lockouts:
                if now < self._lockouts[actor_key]:
                    return None  # Already alerted
                else:
                    del self._lockouts[actor_key]

            # Record failure
            self._failures[actor_key].append(now)

            # Count recent failures
            window_start = now - self.config.auth_failure_window_seconds
            recent_failures = sum(1 for t in self._failures[actor_key] if t >= window_start)

            if recent_failures >= self.config.auth_failure_threshold:
                # Trigger lockout
                self._lockouts[actor_key] = now + self.config.lockout_duration_seconds

                return SecurityAlert(
                    alert_id=f"bf_{actor_key}_{int(now)}",
                    threat_type=ThreatType.BRUTE_FORCE,
                    threat_level=ThreatLevel.HIGH,
                    title="Brute Force Attack Detected",
                    description=f"{recent_failures} failed login attempts from {actor_key} "
                               f"in {self.config.auth_failure_window_seconds} seconds",
                    source_events=[event.event_id],
                    affected_actors=[actor_key],
                    recommendations=[
                        f"Actor locked out for {self.config.lockout_duration_seconds} seconds",
                        "Investigate source IP",
                        "Consider adding to blocklist if attack continues",
                    ],
                    auto_actions_taken=["lockout"],
                )

        return None

    def is_locked_out(self, actor_key: str) -> Tuple[bool, Optional[int]]:
        """Check if actor is locked out."""
        with self._lock:
            if actor_key in self._lockouts:
                remaining = int(self._lockouts[actor_key] - time.time())
                if remaining > 0:
                    return True, remaining
                else:
                    del self._lockouts[actor_key]
            return False, None

    def reset(self, actor_id: str) -> None:
        with self._lock:
            self._failures.pop(actor_id, None)
            self._lockouts.pop(actor_id, None)


class AnomalyDetector(ThreatDetector):
    """Detects anomalous behavior patterns."""

    def __init__(self, config: MonitoringConfig):
        self.config = config
        self._baselines: Dict[str, Dict[str, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=1000))
        )
        self._lock = threading.RLock()

    def _get_hour_key(self) -> str:
        """Get current hour key for baseline grouping."""
        return datetime.utcnow().strftime("%H")

    def record_metric(self, actor_id: str, metric_name: str, value: float) -> None:
        """Record a metric value for baseline calculation."""
        with self._lock:
            self._baselines[actor_id][metric_name].append(value)

    def analyze(self, event: SecurityEvent) -> Optional[SecurityAlert]:
        # Look for specific patterns
        if event.event_type == SecurityEventType.SESSION_ANOMALY:
            return SecurityAlert(
                alert_id=f"anomaly_{event.event_id}",
                threat_type=ThreatType.ANOMALOUS_BEHAVIOR,
                threat_level=ThreatLevel.MEDIUM,
                title="Anomalous Session Activity",
                description=event.details.get("reason", "Unusual session behavior detected"),
                source_events=[event.event_id],
                affected_actors=[event.actor_id] if event.actor_id else [],
                recommendations=[
                    "Review session activity",
                    "Verify user identity",
                    "Check for compromised credentials",
                ],
            )

        return None

    def check_anomaly(
        self,
        actor_id: str,
        metric_name: str,
        current_value: float,
    ) -> Optional[str]:
        """Check if value is anomalous compared to baseline."""
        with self._lock:
            values = list(self._baselines[actor_id][metric_name])

        if len(values) < 10:
            return None  # Not enough data

        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0

        if stdev == 0:
            return None

        z_score = abs(current_value - mean) / stdev

        if z_score > self.config.anomaly_std_threshold:
            return f"{metric_name} value {current_value} is {z_score:.1f} std devs from mean {mean:.1f}"

        return None

    def reset(self, actor_id: str) -> None:
        with self._lock:
            self._baselines.pop(actor_id, None)


class SessionHijackDetector(ThreatDetector):
    """Detects potential session hijacking."""

    def __init__(self):
        self._session_profiles: Dict[str, Dict] = {}
        self._lock = threading.RLock()

    def update_profile(
        self,
        session_id: str,
        ip_address: str,
        user_agent: str,
        fingerprint: Optional[str] = None,
    ) -> None:
        """Update session profile."""
        with self._lock:
            if session_id not in self._session_profiles:
                self._session_profiles[session_id] = {
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "fingerprint": fingerprint,
                    "ip_history": [ip_address],
                }
            else:
                profile = self._session_profiles[session_id]
                if ip_address not in profile["ip_history"]:
                    profile["ip_history"].append(ip_address)

    def analyze(self, event: SecurityEvent) -> Optional[SecurityAlert]:
        if event.event_type != SecurityEventType.SESSION_ANOMALY:
            return None

        session_id = event.target_id

        with self._lock:
            profile = self._session_profiles.get(session_id)

        if not profile:
            return None

        # Check for suspicious patterns
        if len(profile.get("ip_history", [])) > 3:
            return SecurityAlert(
                alert_id=f"hijack_{session_id[:8]}_{int(time.time())}",
                threat_type=ThreatType.SESSION_HIJACK,
                threat_level=ThreatLevel.CRITICAL,
                title="Potential Session Hijacking",
                description=f"Session {session_id[:8]} accessed from multiple IPs: "
                           f"{profile['ip_history']}",
                source_events=[event.event_id],
                affected_actors=[event.actor_id] if event.actor_id else [],
                recommendations=[
                    "Invalidate session immediately",
                    "Force re-authentication",
                    "Review all session activity",
                    "Check for credential compromise",
                ],
            )

        return None

    def reset(self, actor_id: str) -> None:
        with self._lock:
            # Remove sessions belonging to actor
            to_remove = [
                sid for sid, profile in self._session_profiles.items()
                if profile.get("actor_id") == actor_id
            ]
            for sid in to_remove:
                del self._session_profiles[sid]


class SecurityMonitor:
    """
    Security Monitoring System.

    Aggregates events, detects threats, and generates alerts.
    """

    def __init__(
        self,
        config: Optional[MonitoringConfig] = None,
        alert_handler: Optional[Callable[[SecurityAlert], None]] = None,
    ):
        self.config = config or MonitoringConfig()
        self.alert_handler = alert_handler

        # Event storage
        self._events: deque = deque(maxlen=100000)
        self._alerts: Dict[str, SecurityAlert] = {}
        self._alert_cooldowns: Dict[str, float] = {}

        # Threat detectors
        self._detectors: List[ThreatDetector] = [
            BruteForceDetector(self.config),
            AnomalyDetector(self.config),
            SessionHijackDetector(),
        ]

        # Statistics
        self._stats = defaultdict(int)
        self._lock = threading.RLock()

        # Background cleanup
        self._cleanup_interval = 3600  # 1 hour
        self._last_cleanup = time.time()

    def add_detector(self, detector: ThreatDetector) -> None:
        """Add a custom threat detector."""
        self._detectors.append(detector)

    def record_event(self, event: SecurityEvent) -> List[SecurityAlert]:
        """
        Record a security event and check for threats.

        Returns list of generated alerts.
        """
        alerts = []

        with self._lock:
            self._events.append(event)
            self._stats[event.event_type.value] += 1

            # Run through detectors
            for detector in self._detectors:
                try:
                    alert = detector.analyze(event)
                    if alert:
                        if self._should_alert(alert):
                            self._alerts[alert.alert_id] = alert
                            alerts.append(alert)
                            self._alert_cooldowns[alert.threat_type.value] = time.time()
                except Exception as e:
                    logger.error(f"Detector error: {e}")

            # Periodic cleanup
            if time.time() - self._last_cleanup > self._cleanup_interval:
                self._cleanup_old_data()
                self._last_cleanup = time.time()

        # Notify alert handler
        for alert in alerts:
            self._handle_alert(alert)

        return alerts

    def _should_alert(self, alert: SecurityAlert) -> bool:
        """Check if we should generate this alert (respecting cooldown)."""
        cooldown_key = alert.threat_type.value
        last_alert_time = self._alert_cooldowns.get(cooldown_key, 0)

        if time.time() - last_alert_time < self.config.alert_cooldown_seconds:
            return False

        return True

    def _handle_alert(self, alert: SecurityAlert) -> None:
        """Handle a new alert."""
        # Log the alert
        level = {
            ThreatLevel.CRITICAL: logging.CRITICAL,
            ThreatLevel.HIGH: logging.ERROR,
            ThreatLevel.MEDIUM: logging.WARNING,
            ThreatLevel.LOW: logging.INFO,
            ThreatLevel.INFO: logging.DEBUG,
        }.get(alert.threat_level, logging.WARNING)

        logger.log(level, f"SECURITY ALERT [{alert.threat_level.value}]: {alert.title}")

        # Call external handler
        if self.alert_handler:
            try:
                self.alert_handler(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

    def _cleanup_old_data(self) -> None:
        """Clean up old events and resolved alerts."""
        now = datetime.utcnow()
        retention_cutoff = now - timedelta(hours=self.config.event_retention_hours)

        # Remove old events
        while self._events and self._events[0].timestamp < retention_cutoff:
            self._events.popleft()

        # Remove old resolved alerts
        alert_cutoff = now - timedelta(days=self.config.alert_retention_days)
        to_remove = [
            aid for aid, alert in self._alerts.items()
            if alert.resolved and alert.timestamp < alert_cutoff
        ]
        for aid in to_remove:
            del self._alerts[aid]

    # ====================== Event Recording Helpers ======================

    def record_auth_success(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        method: str = "password",
    ) -> None:
        """Record successful authentication."""
        import secrets
        event = SecurityEvent(
            event_id=f"auth_{secrets.token_hex(8)}",
            event_type=SecurityEventType.AUTH_SUCCESS,
            actor_id=user_id,
            actor_ip=ip_address,
            details={"method": method},
        )
        self.record_event(event)

    def record_auth_failure(
        self,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        reason: str = "invalid_credentials",
    ) -> List[SecurityAlert]:
        """Record failed authentication."""
        import secrets
        event = SecurityEvent(
            event_id=f"auth_{secrets.token_hex(8)}",
            event_type=SecurityEventType.AUTH_FAILURE,
            actor_id=user_id,
            actor_ip=ip_address,
            success=False,
            details={"reason": reason},
        )
        return self.record_event(event)

    def record_access_denied(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        reason: str,
        ip_address: Optional[str] = None,
    ) -> None:
        """Record access denial."""
        import secrets
        event = SecurityEvent(
            event_id=f"access_{secrets.token_hex(8)}",
            event_type=SecurityEventType.ACCESS_DENIED,
            actor_id=user_id,
            actor_ip=ip_address,
            target_type=resource_type,
            target_id=resource_id,
            success=False,
            details={"reason": reason},
        )
        self.record_event(event)

    def record_session_anomaly(
        self,
        session_id: str,
        user_id: str,
        anomaly_type: str,
        details: Optional[Dict] = None,
    ) -> List[SecurityAlert]:
        """Record session anomaly."""
        import secrets
        event = SecurityEvent(
            event_id=f"session_{secrets.token_hex(8)}",
            event_type=SecurityEventType.SESSION_ANOMALY,
            actor_id=user_id,
            target_type="session",
            target_id=session_id,
            success=False,
            details={"anomaly_type": anomaly_type, **(details or {})},
        )
        return self.record_event(event)

    # ====================== Alert Management ======================

    def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str,
    ) -> bool:
        """Acknowledge an alert."""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if not alert:
                return False

            alert.acknowledged = True
            alert.acknowledged_by = acknowledged_by
            alert.acknowledged_at = datetime.utcnow()
            return True

    def resolve_alert(
        self,
        alert_id: str,
        false_positive: bool = False,
    ) -> bool:
        """Resolve an alert."""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if not alert:
                return False

            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
            alert.false_positive = false_positive
            return True

    def get_active_alerts(
        self,
        threat_level: Optional[ThreatLevel] = None,
    ) -> List[SecurityAlert]:
        """Get active (unresolved) alerts."""
        with self._lock:
            alerts = [a for a in self._alerts.values() if not a.resolved]

            if threat_level:
                alerts = [a for a in alerts if a.threat_level == threat_level]

            return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def get_alert(self, alert_id: str) -> Optional[SecurityAlert]:
        """Get an alert by ID."""
        with self._lock:
            return self._alerts.get(alert_id)

    # ====================== Statistics ======================

    def get_statistics(
        self,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get security statistics."""
        with self._lock:
            if since:
                events = [e for e in self._events if e.timestamp >= since]
            else:
                events = list(self._events)

            stats = defaultdict(int)
            for event in events:
                stats[event.event_type.value] += 1

            active_alerts = len([a for a in self._alerts.values() if not a.resolved])
            critical_alerts = len([
                a for a in self._alerts.values()
                if not a.resolved and a.threat_level == ThreatLevel.CRITICAL
            ])

            return {
                "total_events": len(events),
                "events_by_type": dict(stats),
                "total_alerts": len(self._alerts),
                "active_alerts": active_alerts,
                "critical_alerts": critical_alerts,
                "auth_failures": stats.get(SecurityEventType.AUTH_FAILURE.value, 0),
                "access_denials": stats.get(SecurityEventType.ACCESS_DENIED.value, 0),
            }

    def is_actor_locked_out(self, actor_key: str) -> Tuple[bool, Optional[int]]:
        """Check if an actor is locked out due to brute force detection."""
        for detector in self._detectors:
            if isinstance(detector, BruteForceDetector):
                return detector.is_locked_out(actor_key)
        return False, None

    def reset_actor(self, actor_id: str) -> None:
        """Reset all tracking for an actor (e.g., after password reset)."""
        for detector in self._detectors:
            detector.reset(actor_id)


class AlertNotifier:
    """
    Alert notification handler.

    Sends alerts to various channels.
    """

    def __init__(self):
        self._handlers: Dict[ThreatLevel, List[Callable[[SecurityAlert], None]]] = {
            level: [] for level in ThreatLevel
        }

    def register_handler(
        self,
        handler: Callable[[SecurityAlert], None],
        min_level: ThreatLevel = ThreatLevel.MEDIUM,
    ) -> None:
        """Register a notification handler."""
        for level in ThreatLevel:
            if level.value <= min_level.value:
                self._handlers[level].append(handler)

    def notify(self, alert: SecurityAlert) -> None:
        """Send notifications for an alert."""
        handlers = self._handlers.get(alert.threat_level, [])
        for handler in handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Notification handler error: {e}")


def create_security_monitor(
    config: Optional[MonitoringConfig] = None,
    alert_handler: Optional[Callable[[SecurityAlert], None]] = None,
) -> SecurityMonitor:
    """Create a security monitor instance."""
    return SecurityMonitor(config=config, alert_handler=alert_handler)
