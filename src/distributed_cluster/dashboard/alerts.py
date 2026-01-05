"""
Alert Manager - مدير التنبيهات
==============================

Alert Management System
-----------------------

This module provides alert management and notification.

يوفر هذا الملف إدارة التنبيهات والإشعارات.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """شدة التنبيه / Alert severity"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertState(str, Enum):
    """حالة التنبيه / Alert state"""
    PENDING = "pending"
    FIRING = "firing"
    RESOLVED = "resolved"
    SILENCED = "silenced"


@dataclass
class Alert:
    """
    تنبيه
    Alert
    """
    alert_id: str
    name: str
    severity: AlertSeverity
    message: str
    state: AlertState = AlertState.PENDING

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    last_notification: Optional[datetime] = None

    # Context
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    value: Optional[float] = None

    # Notifications
    notification_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "alertId": self.alert_id,
            "name": self.name,
            "severity": self.severity.value,
            "message": self.message,
            "state": self.state.value,
            "startedAt": self.started_at.isoformat(),
            "resolvedAt": self.resolved_at.isoformat() if self.resolved_at else None,
            "labels": self.labels,
            "annotations": self.annotations,
            "value": self.value,
            "notificationCount": self.notification_count,
        }

    @property
    def duration_seconds(self) -> float:
        """مدة التنبيه بالثواني"""
        end = self.resolved_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()


@dataclass
class AlertRule:
    """
    قاعدة التنبيه
    Alert rule
    """
    name: str
    condition: Callable[[], bool]
    severity: AlertSeverity = AlertSeverity.WARNING
    message_template: str = ""

    # Thresholds
    for_duration_seconds: float = 0  # How long condition must be true
    repeat_interval_seconds: float = 300  # Notification repeat interval

    # Labels
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)

    # State
    enabled: bool = True
    last_check: Optional[datetime] = None
    pending_since: Optional[datetime] = None


class AlertManager:
    """
    مدير التنبيهات
    Alert Manager

    يدير قواعد التنبيهات ويرسل الإشعارات.
    Manages alert rules and sends notifications.
    """

    def __init__(
        self,
        check_interval_seconds: float = 30.0,
    ):
        """
        تهيئة المدير

        Args:
            check_interval_seconds: فترة الفحص
        """
        self.check_interval = check_interval_seconds

        # Rules and alerts
        self._rules: dict[str, AlertRule] = {}
        self._alerts: dict[str, Alert] = {}
        self._alert_history: list[Alert] = []

        # Notification handlers
        self._handlers: list[Callable[[Alert], None]] = []

        # Silences
        self._silences: dict[str, datetime] = {}  # name -> until

        # State
        self._running = False
        self._check_task: Optional[asyncio.Task] = None

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء المدير"""
        self._running = True
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("AlertManager started")

    async def stop(self) -> None:
        """إيقاف المدير"""
        self._running = False

        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

        logger.info("AlertManager stopped")

    # =========================================================================
    # Rules
    # =========================================================================

    def add_rule(self, rule: AlertRule) -> None:
        """إضافة قاعدة تنبيه"""
        self._rules[rule.name] = rule
        logger.debug(f"Added alert rule: {rule.name}")

    def remove_rule(self, name: str) -> None:
        """إزالة قاعدة تنبيه"""
        self._rules.pop(name, None)

        # Resolve any active alerts for this rule
        if name in self._alerts:
            self._resolve_alert(name)

    def enable_rule(self, name: str) -> None:
        """تفعيل قاعدة"""
        if name in self._rules:
            self._rules[name].enabled = True

    def disable_rule(self, name: str) -> None:
        """تعطيل قاعدة"""
        if name in self._rules:
            self._rules[name].enabled = False

    # =========================================================================
    # Checking
    # =========================================================================

    async def _check_loop(self) -> None:
        """حلقة الفحص"""
        while self._running:
            try:
                await self._check_all_rules()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert check error: {e}")
                await asyncio.sleep(5)

    async def _check_all_rules(self) -> None:
        """فحص جميع القواعد"""
        for name, rule in self._rules.items():
            if not rule.enabled:
                continue

            await self._check_rule(rule)

    async def _check_rule(self, rule: AlertRule) -> None:
        """فحص قاعدة واحدة"""
        rule.last_check = datetime.now(timezone.utc)

        try:
            # Evaluate condition
            if asyncio.iscoroutinefunction(rule.condition):
                condition_met = await rule.condition()
            else:
                condition_met = rule.condition()

            if condition_met:
                await self._handle_condition_met(rule)
            else:
                await self._handle_condition_not_met(rule)

        except Exception as e:
            logger.error(f"Error checking rule {rule.name}: {e}")

    async def _handle_condition_met(self, rule: AlertRule) -> None:
        """معالجة تحقق الشرط"""
        now = datetime.now(timezone.utc)

        # Check if pending
        if rule.pending_since is None:
            rule.pending_since = now

        # Check if for_duration has passed
        pending_duration = (now - rule.pending_since).total_seconds()
        if pending_duration < rule.for_duration_seconds:
            return  # Still pending

        # Check if already firing
        if rule.name in self._alerts:
            alert = self._alerts[rule.name]

            # Check if should repeat notification
            if alert.last_notification:
                since_last = (now - alert.last_notification).total_seconds()
                if since_last >= rule.repeat_interval_seconds:
                    await self._send_notification(alert)
        else:
            # Create new alert
            await self._fire_alert(rule)

    async def _handle_condition_not_met(self, rule: AlertRule) -> None:
        """معالجة عدم تحقق الشرط"""
        rule.pending_since = None

        if rule.name in self._alerts:
            self._resolve_alert(rule.name)

    # =========================================================================
    # Alert Management
    # =========================================================================

    async def _fire_alert(self, rule: AlertRule) -> None:
        """إطلاق تنبيه"""
        alert = Alert(
            alert_id=str(uuid4()),
            name=rule.name,
            severity=rule.severity,
            message=rule.message_template or f"Alert: {rule.name}",
            state=AlertState.FIRING,
            labels=rule.labels.copy(),
            annotations=rule.annotations.copy(),
        )

        self._alerts[rule.name] = alert

        logger.warning(f"Alert fired: {rule.name} ({rule.severity.value})")

        await self._send_notification(alert)

    def _resolve_alert(self, name: str) -> None:
        """حل تنبيه"""
        if name not in self._alerts:
            return

        alert = self._alerts.pop(name)
        alert.state = AlertState.RESOLVED
        alert.resolved_at = datetime.now(timezone.utc)

        # Add to history
        self._alert_history.append(alert)

        # Keep history size manageable
        if len(self._alert_history) > 1000:
            self._alert_history = self._alert_history[-1000:]

        logger.info(f"Alert resolved: {name}")

    # =========================================================================
    # Notifications
    # =========================================================================

    def register_handler(
        self,
        handler: Callable[[Alert], None],
    ) -> None:
        """تسجيل معالج إشعارات"""
        self._handlers.append(handler)

    async def _send_notification(self, alert: Alert) -> None:
        """إرسال إشعار"""
        # Check if silenced
        if alert.name in self._silences:
            if datetime.now(timezone.utc) < self._silences[alert.name]:
                return

        alert.last_notification = datetime.now(timezone.utc)
        alert.notification_count += 1

        for handler in self._handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert)
                else:
                    handler(alert)
            except Exception as e:
                logger.error(f"Notification handler error: {e}")

    # =========================================================================
    # Silencing
    # =========================================================================

    def silence(
        self,
        name: str,
        duration_seconds: float = 3600,
    ) -> None:
        """كتم تنبيه"""
        until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        self._silences[name] = until

        if name in self._alerts:
            self._alerts[name].state = AlertState.SILENCED

        logger.info(f"Silenced alert {name} until {until}")

    def unsilence(self, name: str) -> None:
        """إلغاء كتم تنبيه"""
        self._silences.pop(name, None)

        if name in self._alerts:
            self._alerts[name].state = AlertState.FIRING

    # =========================================================================
    # Query
    # =========================================================================

    def get_active_alerts(self) -> list[Alert]:
        """الحصول على التنبيهات النشطة"""
        return list(self._alerts.values())

    def get_alert(self, name: str) -> Optional[Alert]:
        """الحصول على تنبيه"""
        return self._alerts.get(name)

    def get_alert_history(
        self,
        limit: int = 100,
        severity: Optional[AlertSeverity] = None,
    ) -> list[Alert]:
        """الحصول على سجل التنبيهات"""
        history = self._alert_history[-limit:]

        if severity:
            history = [a for a in history if a.severity == severity]

        return history

    def get_status(self) -> dict[str, Any]:
        """الحصول على الحالة"""
        return {
            "active_alerts": len(self._alerts),
            "total_rules": len(self._rules),
            "enabled_rules": sum(1 for r in self._rules.values() if r.enabled),
            "silenced": len(self._silences),
            "alerts": [a.to_dict() for a in self._alerts.values()],
        }


# =============================================================================
# Predefined Rules
# =============================================================================

def create_threshold_rule(
    name: str,
    metric_fn: Callable[[], float],
    threshold: float,
    comparison: str = ">",
    severity: AlertSeverity = AlertSeverity.WARNING,
    for_duration: float = 60,
) -> AlertRule:
    """إنشاء قاعدة عتبة"""
    def condition():
        value = metric_fn()
        if comparison == ">":
            return value > threshold
        elif comparison == ">=":
            return value >= threshold
        elif comparison == "<":
            return value < threshold
        elif comparison == "<=":
            return value <= threshold
        elif comparison == "==":
            return value == threshold
        return False

    return AlertRule(
        name=name,
        condition=condition,
        severity=severity,
        message_template=f"{name} {comparison} {threshold}",
        for_duration_seconds=for_duration,
    )
