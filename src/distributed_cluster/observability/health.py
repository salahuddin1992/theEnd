"""
Health Monitoring & Alerts
==========================

نظام مراقبة صحة الكلاستر والتنبيهات:
- Health checks
- Alert rules
- Notification channels
- Auto-recovery
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Health Status
# =============================================================================

class HealthStatus(str, Enum):
    """حالة الصحة."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    """شدة التنبيه."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertState(str, Enum):
    """حالة التنبيه."""
    PENDING = "pending"  # في انتظار تأكيد
    FIRING = "firing"  # نشط
    RESOLVED = "resolved"  # تم حله


@dataclass
class HealthCheck:
    """فحص صحة واحد."""
    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    last_check: Optional[datetime] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthReport:
    """تقرير الصحة الكامل."""
    overall_status: HealthStatus
    checks: Dict[str, HealthCheck]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    uptime_seconds: float = 0.0
    version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dict."""
        return {
            "status": self.overall_status.value,
            "timestamp": self.timestamp.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "version": self.version,
            "checks": {
                name: {
                    "status": check.status.value,
                    "message": check.message,
                    "last_check": check.last_check.isoformat() if check.last_check else None,
                    "duration_ms": check.duration_ms,
                    "metadata": check.metadata,
                }
                for name, check in self.checks.items()
            },
        }


@dataclass
class Alert:
    """تنبيه."""
    alert_id: str
    name: str
    severity: AlertSeverity
    state: AlertState
    message: str
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    last_sent_at: Optional[datetime] = None
    send_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dict."""
        return {
            "alert_id": self.alert_id,
            "name": self.name,
            "severity": self.severity.value,
            "state": self.state.value,
            "message": self.message,
            "labels": self.labels,
            "annotations": self.annotations,
            "started_at": self.started_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "duration_seconds": (
                (self.resolved_at or datetime.utcnow()) - self.started_at
            ).total_seconds(),
        }


# =============================================================================
# Health Check Functions
# =============================================================================

class HealthChecker:
    """
    مدير فحوصات الصحة.

    يدير:
    - تسجيل الفحوصات
    - تنفيذ الفحوصات
    - تجميع النتائج
    """

    def __init__(self):
        self._checks: Dict[str, Callable[[], Awaitable[HealthCheck]]] = {}
        self._results: Dict[str, HealthCheck] = {}
        self._start_time = datetime.utcnow()
        self._version = "0.1.0"

    def register(
        self,
        name: str,
        check_func: Callable[[], Awaitable[HealthCheck]],
    ) -> None:
        """تسجيل فحص صحة."""
        self._checks[name] = check_func
        logger.info(f"Registered health check: {name}")

    def unregister(self, name: str) -> None:
        """إلغاء تسجيل فحص."""
        self._checks.pop(name, None)
        self._results.pop(name, None)

    async def check(self, name: str) -> HealthCheck:
        """تنفيذ فحص واحد."""
        if name not in self._checks:
            return HealthCheck(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=f"Check '{name}' not found",
            )

        check_func = self._checks[name]
        start_time = datetime.utcnow()

        try:
            result = await asyncio.wait_for(check_func(), timeout=10.0)
            result.last_check = datetime.utcnow()
            result.duration_ms = (result.last_check - start_time).total_seconds() * 1000
            self._results[name] = result
            return result

        except asyncio.TimeoutError:
            result = HealthCheck(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Check timed out",
                last_check=datetime.utcnow(),
                duration_ms=10000,
            )
            self._results[name] = result
            return result

        except Exception as e:
            result = HealthCheck(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check error: {str(e)}",
                last_check=datetime.utcnow(),
                duration_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            )
            self._results[name] = result
            return result

    async def check_all(self) -> HealthReport:
        """تنفيذ كل الفحوصات."""
        tasks = [self.check(name) for name in self._checks.keys()]
        await asyncio.gather(*tasks)

        # Determine overall status
        overall_status = HealthStatus.HEALTHY
        for check in self._results.values():
            if check.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break
            elif check.status == HealthStatus.DEGRADED:
                overall_status = HealthStatus.DEGRADED

        uptime = (datetime.utcnow() - self._start_time).total_seconds()

        return HealthReport(
            overall_status=overall_status,
            checks=self._results.copy(),
            uptime_seconds=uptime,
            version=self._version,
        )

    def get_last_results(self) -> Dict[str, HealthCheck]:
        """الحصول على آخر نتائج."""
        return self._results.copy()


# =============================================================================
# Standard Health Checks
# =============================================================================

async def database_health_check(db) -> HealthCheck:
    """فحص صحة قاعدة البيانات."""
    try:
        # Try a simple query
        await db.execute("SELECT 1")
        return HealthCheck(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database connection OK",
        )
    except Exception as e:
        return HealthCheck(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database error: {str(e)}",
        )


async def scheduler_health_check(scheduler) -> HealthCheck:
    """فحص صحة المجدول."""
    pending_jobs = scheduler.pending_jobs_count
    workers = len(scheduler.workers)

    if workers == 0:
        return HealthCheck(
            name="scheduler",
            status=HealthStatus.DEGRADED,
            message="No workers available",
            metadata={"pending_jobs": pending_jobs, "workers": workers},
        )

    if pending_jobs > 1000:
        return HealthCheck(
            name="scheduler",
            status=HealthStatus.DEGRADED,
            message=f"High job queue: {pending_jobs} pending",
            metadata={"pending_jobs": pending_jobs, "workers": workers},
        )

    return HealthCheck(
        name="scheduler",
        status=HealthStatus.HEALTHY,
        message=f"{workers} workers, {pending_jobs} pending jobs",
        metadata={"pending_jobs": pending_jobs, "workers": workers},
    )


async def memory_health_check(threshold_percent: float = 90.0) -> HealthCheck:
    """فحص صحة الذاكرة."""
    try:
        import psutil
        memory = psutil.virtual_memory()

        if memory.percent > threshold_percent:
            return HealthCheck(
                name="memory",
                status=HealthStatus.UNHEALTHY,
                message=f"High memory usage: {memory.percent:.1f}%",
                metadata={
                    "used_percent": memory.percent,
                    "used_mb": memory.used // (1024 * 1024),
                    "total_mb": memory.total // (1024 * 1024),
                },
            )

        if memory.percent > threshold_percent * 0.8:
            return HealthCheck(
                name="memory",
                status=HealthStatus.DEGRADED,
                message=f"Memory usage elevated: {memory.percent:.1f}%",
                metadata={
                    "used_percent": memory.percent,
                    "used_mb": memory.used // (1024 * 1024),
                    "total_mb": memory.total // (1024 * 1024),
                },
            )

        return HealthCheck(
            name="memory",
            status=HealthStatus.HEALTHY,
            message=f"Memory usage: {memory.percent:.1f}%",
            metadata={
                "used_percent": memory.percent,
                "used_mb": memory.used // (1024 * 1024),
                "total_mb": memory.total // (1024 * 1024),
            },
        )
    except ImportError:
        return HealthCheck(
            name="memory",
            status=HealthStatus.UNKNOWN,
            message="psutil not available",
        )


async def disk_health_check(path: str = "/", threshold_percent: float = 90.0) -> HealthCheck:
    """فحص صحة القرص."""
    try:
        import psutil
        disk = psutil.disk_usage(path)
        used_percent = disk.percent

        if used_percent > threshold_percent:
            return HealthCheck(
                name="disk",
                status=HealthStatus.UNHEALTHY,
                message=f"High disk usage: {used_percent:.1f}%",
                metadata={
                    "path": path,
                    "used_percent": used_percent,
                    "free_gb": disk.free // (1024 * 1024 * 1024),
                },
            )

        if used_percent > threshold_percent * 0.8:
            return HealthCheck(
                name="disk",
                status=HealthStatus.DEGRADED,
                message=f"Disk usage elevated: {used_percent:.1f}%",
                metadata={
                    "path": path,
                    "used_percent": used_percent,
                    "free_gb": disk.free // (1024 * 1024 * 1024),
                },
            )

        return HealthCheck(
            name="disk",
            status=HealthStatus.HEALTHY,
            message=f"Disk usage: {used_percent:.1f}%",
            metadata={
                "path": path,
                "used_percent": used_percent,
                "free_gb": disk.free // (1024 * 1024 * 1024),
            },
        )
    except ImportError:
        return HealthCheck(
            name="disk",
            status=HealthStatus.UNKNOWN,
            message="psutil not available",
        )


# =============================================================================
# Alert Rules
# =============================================================================

@dataclass
class AlertRule:
    """قاعدة تنبيه."""
    name: str
    condition: Callable[[], Awaitable[bool]]
    severity: AlertSeverity
    message_template: str
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)

    # Timing
    for_duration: timedelta = field(default_factory=lambda: timedelta(minutes=1))
    repeat_interval: timedelta = field(default_factory=lambda: timedelta(hours=4))

    # State
    pending_since: Optional[datetime] = None
    enabled: bool = True


class AlertManager:
    """
    مدير التنبيهات.

    يدير:
    - قواعد التنبيهات
    - تقييم القواعد
    - إرسال التنبيهات
    """

    def __init__(self):
        self._rules: Dict[str, AlertRule] = {}
        self._alerts: Dict[str, Alert] = {}
        self._channels: List[NotificationChannel] = []
        self._processor_task: Optional[asyncio.Task] = None
        self._running = False

    def add_rule(self, rule: AlertRule) -> None:
        """إضافة قاعدة تنبيه."""
        self._rules[rule.name] = rule
        logger.info(f"Added alert rule: {rule.name}")

    def remove_rule(self, name: str) -> None:
        """إزالة قاعدة تنبيه."""
        self._rules.pop(name, None)

    def add_channel(self, channel: NotificationChannel) -> None:
        """إضافة قناة إشعارات."""
        self._channels.append(channel)

    async def start(self, check_interval: float = 30.0) -> None:
        """بدء المدير."""
        self._running = True
        self._processor_task = asyncio.create_task(
            self._evaluate_loop(check_interval)
        )
        logger.info("Alert manager started")

    async def stop(self) -> None:
        """إيقاف المدير."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("Alert manager stopped")

    async def _evaluate_loop(self, interval: float) -> None:
        """حلقة تقييم القواعد."""
        while self._running:
            try:
                await self._evaluate_all_rules()
            except Exception as e:
                logger.error(f"Alert evaluation error: {e}")

            await asyncio.sleep(interval)

    async def _evaluate_all_rules(self) -> None:
        """تقييم كل القواعد."""
        now = datetime.utcnow()

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            try:
                condition_met = await rule.condition()
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.name}: {e}")
                continue

            alert_id = f"alert-{rule.name}"
            existing_alert = self._alerts.get(alert_id)

            if condition_met:
                if not rule.pending_since:
                    rule.pending_since = now

                # Check if for_duration has passed
                pending_duration = now - rule.pending_since
                if pending_duration >= rule.for_duration:
                    # Fire alert
                    if not existing_alert or existing_alert.state == AlertState.RESOLVED:
                        alert = Alert(
                            alert_id=alert_id,
                            name=rule.name,
                            severity=rule.severity,
                            state=AlertState.FIRING,
                            message=rule.message_template,
                            labels=rule.labels,
                            annotations=rule.annotations,
                        )
                        self._alerts[alert_id] = alert
                        await self._send_alert(alert)

                    elif existing_alert.state == AlertState.FIRING:
                        # Check if should repeat
                        if existing_alert.last_sent_at:
                            since_last = now - existing_alert.last_sent_at
                            if since_last >= rule.repeat_interval:
                                await self._send_alert(existing_alert)
            else:
                # Condition not met
                rule.pending_since = None

                if existing_alert and existing_alert.state == AlertState.FIRING:
                    # Resolve alert
                    existing_alert.state = AlertState.RESOLVED
                    existing_alert.resolved_at = now
                    await self._send_resolved(existing_alert)

    async def _send_alert(self, alert: Alert) -> None:
        """إرسال تنبيه."""
        alert.last_sent_at = datetime.utcnow()
        alert.send_count += 1

        logger.warning(f"Alert firing: {alert.name} - {alert.message}")

        for channel in self._channels:
            try:
                await channel.send_alert(alert)
            except Exception as e:
                logger.error(f"Error sending alert to {channel.name}: {e}")

    async def _send_resolved(self, alert: Alert) -> None:
        """إرسال إشعار حل."""
        logger.info(f"Alert resolved: {alert.name}")

        for channel in self._channels:
            try:
                await channel.send_resolved(alert)
            except Exception as e:
                logger.error(f"Error sending resolved to {channel.name}: {e}")

    def get_active_alerts(self) -> List[Alert]:
        """الحصول على التنبيهات النشطة."""
        return [
            alert for alert in self._alerts.values()
            if alert.state == AlertState.FIRING
        ]

    def get_all_alerts(self) -> List[Alert]:
        """الحصول على كل التنبيهات."""
        return list(self._alerts.values())


# =============================================================================
# Notification Channels
# =============================================================================

class NotificationChannel(ABC):
    """قناة إشعارات مجردة."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def send_alert(self, alert: Alert) -> None:
        """إرسال تنبيه."""
        pass

    @abstractmethod
    async def send_resolved(self, alert: Alert) -> None:
        """إرسال إشعار حل."""
        pass


class LogChannel(NotificationChannel):
    """قناة تسجيل (للتطوير)."""

    def __init__(self):
        super().__init__("log")

    async def send_alert(self, alert: Alert) -> None:
        """تسجيل التنبيه."""
        logger.warning(
            f"[ALERT] {alert.severity.value.upper()}: {alert.name} - {alert.message}"
        )

    async def send_resolved(self, alert: Alert) -> None:
        """تسجيل الحل."""
        logger.info(f"[RESOLVED] {alert.name}")


class WebhookChannel(NotificationChannel):
    """قناة Webhook."""

    def __init__(self, name: str, url: str, headers: Optional[Dict[str, str]] = None):
        super().__init__(name)
        self.url = url
        self.headers = headers or {}

    async def send_alert(self, alert: Alert) -> None:
        """إرسال عبر webhook."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                payload = {
                    "status": "firing",
                    "alert": alert.to_dict(),
                }
                await client.post(
                    self.url,
                    json=payload,
                    headers=self.headers,
                    timeout=10.0,
                )
        except Exception as e:
            logger.error(f"Webhook error: {e}")

    async def send_resolved(self, alert: Alert) -> None:
        """إرسال حل عبر webhook."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                payload = {
                    "status": "resolved",
                    "alert": alert.to_dict(),
                }
                await client.post(
                    self.url,
                    json=payload,
                    headers=self.headers,
                    timeout=10.0,
                )
        except Exception as e:
            logger.error(f"Webhook error: {e}")


class SlackChannel(NotificationChannel):
    """قناة Slack."""

    def __init__(self, webhook_url: str, channel: Optional[str] = None):
        super().__init__("slack")
        self.webhook_url = webhook_url
        self.channel = channel

    async def send_alert(self, alert: Alert) -> None:
        """إرسال إلى Slack."""
        color = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#daa038",
            AlertSeverity.ERROR: "#d00000",
            AlertSeverity.CRITICAL: "#8b0000",
        }.get(alert.severity, "#808080")

        payload = {
            "attachments": [{
                "color": color,
                "title": f"🚨 Alert: {alert.name}",
                "text": alert.message,
                "fields": [
                    {"title": "Severity", "value": alert.severity.value, "short": True},
                    {"title": "Started", "value": alert.started_at.isoformat(), "short": True},
                ],
                "footer": "NebulaCompute Alert Manager",
            }]
        }

        if self.channel:
            payload["channel"] = self.channel

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(self.webhook_url, json=payload, timeout=10.0)
        except Exception as e:
            logger.error(f"Slack error: {e}")

    async def send_resolved(self, alert: Alert) -> None:
        """إرسال حل إلى Slack."""
        payload = {
            "attachments": [{
                "color": "#36a64f",
                "title": f"✅ Resolved: {alert.name}",
                "text": f"Alert resolved after {(alert.resolved_at - alert.started_at).total_seconds():.0f} seconds",
                "footer": "NebulaCompute Alert Manager",
            }]
        }

        if self.channel:
            payload["channel"] = self.channel

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(self.webhook_url, json=payload, timeout=10.0)
        except Exception as e:
            logger.error(f"Slack error: {e}")


# =============================================================================
# Standard Alert Rules
# =============================================================================

def create_standard_alert_rules(
    scheduler,
    db,
    worker_offline_threshold: int = 1,
    pending_jobs_threshold: int = 500,
) -> List[AlertRule]:
    """إنشاء قواعد التنبيه القياسية."""
    rules = []

    # No workers available
    async def no_workers_condition():
        return len(scheduler.workers) == 0

    rules.append(AlertRule(
        name="no_workers",
        condition=no_workers_condition,
        severity=AlertSeverity.CRITICAL,
        message_template="No workers available in the cluster",
        for_duration=timedelta(minutes=2),
    ))

    # High pending jobs
    async def high_pending_jobs_condition():
        return scheduler.pending_jobs_count > pending_jobs_threshold

    rules.append(AlertRule(
        name="high_pending_jobs",
        condition=high_pending_jobs_condition,
        severity=AlertSeverity.WARNING,
        message_template=f"More than {pending_jobs_threshold} jobs pending",
        for_duration=timedelta(minutes=5),
    ))

    # High memory usage
    async def high_memory_condition():
        try:
            import psutil
            return psutil.virtual_memory().percent > 90
        except ImportError:
            return False

    rules.append(AlertRule(
        name="high_memory_usage",
        condition=high_memory_condition,
        severity=AlertSeverity.WARNING,
        message_template="Memory usage above 90%",
        for_duration=timedelta(minutes=5),
    ))

    # High disk usage
    async def high_disk_condition():
        try:
            import os
            import sys

            import psutil
            # Use platform-appropriate disk path
            if sys.platform == "win32":
                disk_path = os.environ.get("SystemDrive", "C:") + "\\"
            else:
                disk_path = "/"
            return psutil.disk_usage(disk_path).percent > 90
        except (ImportError, Exception):
            return False

    rules.append(AlertRule(
        name="high_disk_usage",
        condition=high_disk_condition,
        severity=AlertSeverity.WARNING,
        message_template="Disk usage above 90%",
        for_duration=timedelta(minutes=5),
    ))

    return rules
