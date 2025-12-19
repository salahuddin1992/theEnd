"""
Notification Manager - مدير الإشعارات
======================================

Manages notification routing, rules, and delivery.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from distributed_cluster.notifications.channels import (
    ConsoleChannel,
    EmailChannel,
    Notification,
    NotificationChannel,
    NotificationPriority,
    PagerDutyChannel,
    SlackChannel,
    WebhookChannel,
)

logger = logging.getLogger(__name__)


class RuleTrigger(str, Enum):
    """مشغل القاعدة."""
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_TIMEOUT = "job.timeout"
    WORKER_OFFLINE = "worker.offline"
    WORKER_UNHEALTHY = "worker.unhealthy"
    CLUSTER_DEGRADED = "cluster.degraded"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    RESOURCE_EXHAUSTED = "resource.exhausted"
    SECURITY_ALERT = "security.alert"
    CUSTOM = "custom"


@dataclass
class NotificationRule:
    """قاعدة إشعار."""
    rule_id: str
    name: str
    trigger: RuleTrigger
    channels: List[str]  # Channel names
    enabled: bool = True
    priority: NotificationPriority = NotificationPriority.NORMAL
    filters: Dict[str, Any] = field(default_factory=dict)
    cooldown_minutes: int = 5  # Minimum time between notifications
    message_template: Optional[str] = None
    title_template: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Rate limiting
    last_triggered: Optional[datetime] = None
    trigger_count: int = 0


class NotificationManager:
    """
    مدير الإشعارات.

    يدير قنوات الإشعارات والقواعد والتوجيه.
    """

    def __init__(self):
        self._channels: Dict[str, NotificationChannel] = {}
        self._rules: Dict[str, NotificationRule] = {}
        self._history: List[Notification] = []
        self._max_history = 1000

        # Rate limiting
        self._cooldowns: Dict[str, datetime] = {}

        # Callbacks for custom handling
        self._hooks: List[Callable[[Notification], Any]] = []

    def register_channel(self, channel: NotificationChannel) -> None:
        """تسجيل قناة إشعارات."""
        self._channels[channel.name] = channel
        logger.info(f"Registered notification channel: {channel.name}")

    def unregister_channel(self, name: str) -> None:
        """إلغاء تسجيل قناة."""
        if name in self._channels:
            del self._channels[name]
            logger.info(f"Unregistered notification channel: {name}")

    def get_channel(self, name: str) -> Optional[NotificationChannel]:
        """الحصول على قناة."""
        return self._channels.get(name)

    def list_channels(self) -> List[str]:
        """قائمة القنوات."""
        return list(self._channels.keys())

    def add_rule(self, rule: NotificationRule) -> None:
        """إضافة قاعدة إشعار."""
        self._rules[rule.rule_id] = rule
        logger.info(f"Added notification rule: {rule.name}")

    def remove_rule(self, rule_id: str) -> None:
        """إزالة قاعدة."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            logger.info(f"Removed notification rule: {rule_id}")

    def get_rule(self, rule_id: str) -> Optional[NotificationRule]:
        """الحصول على قاعدة."""
        return self._rules.get(rule_id)

    def list_rules(self) -> List[NotificationRule]:
        """قائمة القواعد."""
        return list(self._rules.values())

    def add_hook(self, hook: Callable[[Notification], Any]) -> None:
        """إضافة hook للإشعارات."""
        self._hooks.append(hook)

    async def send(
        self,
        notification: Notification,
        channels: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """
        إرسال إشعار مباشر.

        Args:
            notification: الإشعار
            channels: قنوات محددة (اختياري)

        Returns:
            نتائج الإرسال لكل قناة
        """
        notification.notification_id = notification.notification_id or f"notif-{uuid.uuid4().hex[:12]}"
        notification.sent_at = datetime.utcnow()

        results = {}
        target_channels = channels or list(self._channels.keys())

        for channel_name in target_channels:
            channel = self._channels.get(channel_name)
            if not channel or not channel.enabled:
                continue

            try:
                success = await channel.send(notification)
                results[channel_name] = success

                if success:
                    notification.delivered = True
                    logger.debug(f"Notification sent via {channel_name}")

            except Exception as e:
                logger.error(f"Failed to send notification via {channel_name}: {e}")
                results[channel_name] = False

        # Store in history
        self._history.append(notification)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Call hooks
        for hook in self._hooks:
            try:
                result = hook(notification)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Notification hook error: {e}")

        return results

    async def trigger(
        self,
        trigger: RuleTrigger,
        data: Dict[str, Any],
        force: bool = False,
    ) -> Dict[str, Dict[str, bool]]:
        """
        تشغيل إشعار بناءً على حدث.

        Args:
            trigger: نوع المشغل
            data: بيانات الحدث
            force: تجاهل cooldown

        Returns:
            نتائج الإرسال لكل قاعدة
        """
        results = {}

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            if rule.trigger != trigger:
                continue

            # Check filters
            if not self._match_filters(rule.filters, data):
                continue

            # Check cooldown
            cooldown_key = f"{rule.rule_id}:{trigger.value}"
            if not force and cooldown_key in self._cooldowns:
                last_time = self._cooldowns[cooldown_key]
                if datetime.utcnow() - last_time < timedelta(minutes=rule.cooldown_minutes):
                    logger.debug(f"Rule {rule.name} is in cooldown")
                    continue

            # Build notification
            title = self._render_template(
                rule.title_template or self._default_title(trigger),
                data,
            )
            message = self._render_template(
                rule.message_template or self._default_message(trigger, data),
                data,
            )

            notification = Notification(
                title=title,
                message=message,
                priority=rule.priority,
                metadata=data,
            )

            # Send to rule's channels
            rule_results = await self.send(notification, rule.channels)
            results[rule.rule_id] = rule_results

            # Update rate limiting
            rule.last_triggered = datetime.utcnow()
            rule.trigger_count += 1
            self._cooldowns[cooldown_key] = datetime.utcnow()

        return results

    def _match_filters(self, filters: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """التحقق من مطابقة الفلاتر."""
        for key, expected in filters.items():
            actual = data.get(key)

            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif callable(expected):
                if not expected(actual):
                    return False
            elif actual != expected:
                return False

        return True

    def _render_template(self, template: str, data: Dict[str, Any]) -> str:
        """تطبيق template."""
        result = template
        for key, value in data.items():
            result = result.replace(f"{{{key}}}", str(value))
            result = result.replace(f"${{{key}}}", str(value))
        return result

    def _default_title(self, trigger: RuleTrigger) -> str:
        """عنوان افتراضي."""
        titles = {
            RuleTrigger.JOB_COMPLETED: "Job Completed",
            RuleTrigger.JOB_FAILED: "Job Failed",
            RuleTrigger.JOB_TIMEOUT: "Job Timeout",
            RuleTrigger.WORKER_OFFLINE: "Worker Offline",
            RuleTrigger.WORKER_UNHEALTHY: "Worker Unhealthy",
            RuleTrigger.CLUSTER_DEGRADED: "Cluster Degraded",
            RuleTrigger.WORKFLOW_COMPLETED: "Workflow Completed",
            RuleTrigger.WORKFLOW_FAILED: "Workflow Failed",
            RuleTrigger.RESOURCE_EXHAUSTED: "Resource Exhausted",
            RuleTrigger.SECURITY_ALERT: "Security Alert",
            RuleTrigger.CUSTOM: "Notification",
        }
        return titles.get(trigger, "Notification")

    def _default_message(self, trigger: RuleTrigger, data: Dict[str, Any]) -> str:
        """رسالة افتراضية."""
        messages = {
            RuleTrigger.JOB_COMPLETED: "Job {job_id} completed successfully.",
            RuleTrigger.JOB_FAILED: "Job {job_id} failed: {error}",
            RuleTrigger.JOB_TIMEOUT: "Job {job_id} timed out after {timeout} seconds.",
            RuleTrigger.WORKER_OFFLINE: "Worker {worker_id} went offline.",
            RuleTrigger.WORKER_UNHEALTHY: "Worker {worker_id} is unhealthy: {reason}",
            RuleTrigger.CLUSTER_DEGRADED: "Cluster performance degraded: {reason}",
            RuleTrigger.WORKFLOW_COMPLETED: "Workflow {workflow_id} completed.",
            RuleTrigger.WORKFLOW_FAILED: "Workflow {workflow_id} failed: {error}",
            RuleTrigger.RESOURCE_EXHAUSTED: "Resource {resource} exhausted on {worker_id}.",
            RuleTrigger.SECURITY_ALERT: "Security alert: {message}",
            RuleTrigger.CUSTOM: "{message}",
        }
        template = messages.get(trigger, "{message}")
        return self._render_template(template, data)

    async def test_channel(self, channel_name: str) -> bool:
        """اختبار قناة."""
        channel = self._channels.get(channel_name)
        if not channel:
            return False

        return await channel.test_connection()

    async def test_all_channels(self) -> Dict[str, bool]:
        """اختبار جميع القنوات."""
        results = {}
        for name, channel in self._channels.items():
            results[name] = await channel.test_connection()
        return results

    def get_history(
        self,
        limit: int = 100,
        priority: Optional[NotificationPriority] = None,
        delivered: Optional[bool] = None,
    ) -> List[Notification]:
        """الحصول على تاريخ الإشعارات."""
        history = self._history

        if priority:
            history = [n for n in history if n.priority == priority]

        if delivered is not None:
            history = [n for n in history if n.delivered == delivered]

        return history[-limit:]

    @property
    def stats(self) -> Dict[str, Any]:
        """إحصائيات."""
        total = len(self._history)
        delivered = sum(1 for n in self._history if n.delivered)

        return {
            "total_channels": len(self._channels),
            "active_channels": sum(1 for c in self._channels.values() if c.enabled),
            "total_rules": len(self._rules),
            "active_rules": sum(1 for r in self._rules.values() if r.enabled),
            "notifications_sent": total,
            "notifications_delivered": delivered,
            "delivery_rate": delivered / total if total > 0 else 0,
        }


# =============================================================================
# Factory Functions
# =============================================================================

def create_notification_manager(config: Dict[str, Any]) -> NotificationManager:
    """
    إنشاء مدير إشعارات من التكوين.

    Config example:
        channels:
          email:
            type: email
            smtp_host: smtp.example.com
            smtp_port: 587
            username: user
            password: pass
            from_email: noreply@example.com
            to_emails:
              - admin@example.com
          slack:
            type: slack
            webhook_url: https://hooks.slack.com/...
            channel: "#alerts"
          webhook:
            type: webhook
            url: https://api.example.com/webhook
            secret: mysecret
          pagerduty:
            type: pagerduty
            routing_key: xxx
        rules:
          - name: Job Failures
            trigger: job.failed
            channels: [slack, email]
            priority: high
            cooldown_minutes: 10
    """
    manager = NotificationManager()

    # Register channels
    channel_factories = {
        "email": EmailChannel,
        "slack": SlackChannel,
        "webhook": WebhookChannel,
        "pagerduty": PagerDutyChannel,
        "console": ConsoleChannel,
    }

    for name, channel_config in config.get("channels", {}).items():
        channel_type = channel_config.get("type", name)
        factory = channel_factories.get(channel_type)

        if factory:
            channel = factory(name, channel_config)
            manager.register_channel(channel)
        else:
            logger.warning(f"Unknown channel type: {channel_type}")

    # Add rules
    for i, rule_config in enumerate(config.get("rules", [])):
        rule = NotificationRule(
            rule_id=rule_config.get("id", f"rule-{i}"),
            name=rule_config.get("name", f"Rule {i}"),
            trigger=RuleTrigger(rule_config.get("trigger", "custom")),
            channels=rule_config.get("channels", []),
            enabled=rule_config.get("enabled", True),
            priority=NotificationPriority(rule_config.get("priority", "normal")),
            filters=rule_config.get("filters", {}),
            cooldown_minutes=rule_config.get("cooldown_minutes", 5),
            message_template=rule_config.get("message_template"),
            title_template=rule_config.get("title_template"),
        )
        manager.add_rule(rule)

    return manager


# =============================================================================
# Default Rules
# =============================================================================

DEFAULT_RULES = [
    NotificationRule(
        rule_id="default-job-failed",
        name="Job Failure Alert",
        trigger=RuleTrigger.JOB_FAILED,
        channels=["slack", "email"],
        priority=NotificationPriority.HIGH,
        cooldown_minutes=5,
    ),
    NotificationRule(
        rule_id="default-worker-offline",
        name="Worker Offline Alert",
        trigger=RuleTrigger.WORKER_OFFLINE,
        channels=["slack"],
        priority=NotificationPriority.HIGH,
        cooldown_minutes=15,
    ),
    NotificationRule(
        rule_id="default-cluster-degraded",
        name="Cluster Degraded Alert",
        trigger=RuleTrigger.CLUSTER_DEGRADED,
        channels=["slack", "pagerduty"],
        priority=NotificationPriority.CRITICAL,
        cooldown_minutes=30,
    ),
    NotificationRule(
        rule_id="default-security-alert",
        name="Security Alert",
        trigger=RuleTrigger.SECURITY_ALERT,
        channels=["slack", "email", "pagerduty"],
        priority=NotificationPriority.CRITICAL,
        cooldown_minutes=1,
    ),
]


def create_default_manager() -> NotificationManager:
    """إنشاء مدير بالقواعد الافتراضية."""
    manager = NotificationManager()

    # Add console channel for development
    manager.register_channel(ConsoleChannel())

    # Add default rules
    for rule in DEFAULT_RULES:
        manager.add_rule(rule)

    return manager
