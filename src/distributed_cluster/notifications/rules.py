"""
Notification Rules - قواعد الإشعارات

تحديد متى وأين يتم إرسال الإشعارات
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field

from .notifier import Notification, NotificationCategory, NotificationPriority


class RuleCondition(str, Enum):
    """شروط القاعدة"""
    ALWAYS = "always"           # دائماً
    CATEGORY_IS = "category_is"  # التصنيف يساوي
    PRIORITY_GTE = "priority_gte"  # الأولوية أكبر أو تساوي
    DATA_CONTAINS = "data_contains"  # البيانات تحتوي
    CUSTOM = "custom"           # دالة مخصصة


@dataclass
class NotificationRule:
    """
    قاعدة إشعار

    تحدد متى يتم إرسال الإشعار وإلى أي قنوات
    """
    name: str
    condition: RuleCondition
    channels: List[str]  # أسماء القنوات
    condition_value: Any = None
    custom_check: Optional[Callable[[Notification], bool]] = None
    enabled: bool = True
    description: str = ""

    def matches(self, notification: Notification) -> bool:
        """هل الإشعار يطابق القاعدة"""
        if not self.enabled:
            return False

        if self.condition == RuleCondition.ALWAYS:
            return True

        elif self.condition == RuleCondition.CATEGORY_IS:
            if isinstance(self.condition_value, list):
                return notification.category in self.condition_value
            return notification.category == self.condition_value

        elif self.condition == RuleCondition.PRIORITY_GTE:
            priority_order = [
                NotificationPriority.LOW,
                NotificationPriority.NORMAL,
                NotificationPriority.HIGH,
                NotificationPriority.CRITICAL,
            ]
            target_idx = priority_order.index(self.condition_value)
            current_idx = priority_order.index(notification.priority)
            return current_idx >= target_idx

        elif self.condition == RuleCondition.DATA_CONTAINS:
            if isinstance(self.condition_value, dict):
                for key, value in self.condition_value.items():
                    if key not in notification.data:
                        return False
                    if notification.data[key] != value:
                        return False
                return True
            return False

        elif self.condition == RuleCondition.CUSTOM:
            if self.custom_check:
                return self.custom_check(notification)
            return False

        return False


class RuleEngine:
    """
    محرك القواعد

    يدير ويطبق قواعد الإشعارات
    """

    def __init__(self):
        self.rules: List[NotificationRule] = []

    def add_rule(self, rule: NotificationRule) -> None:
        """إضافة قاعدة"""
        self.rules.append(rule)

    def remove_rule(self, name: str) -> None:
        """إزالة قاعدة"""
        self.rules = [r for r in self.rules if r.name != name]

    def get_matching_channels(self, notification: Notification) -> List[str]:
        """الحصول على القنوات المطابقة"""
        channels = set()
        for rule in self.rules:
            if rule.matches(notification):
                channels.update(rule.channels)
        return list(channels)

    def create_default_rules(self) -> None:
        """إنشاء قواعد افتراضية"""
        # قاعدة: الأحداث الحرجة تذهب لكل القنوات
        self.add_rule(NotificationRule(
            name="critical_all",
            condition=RuleCondition.PRIORITY_GTE,
            condition_value=NotificationPriority.CRITICAL,
            channels=["slack", "discord", "email", "console"],
            description="الأحداث الحرجة تُرسل لجميع القنوات",
        ))

        # قاعدة: فشل المهام يذهب لـ Slack و Email
        self.add_rule(NotificationRule(
            name="job_failed_alert",
            condition=RuleCondition.CATEGORY_IS,
            condition_value=NotificationCategory.JOB_FAILED,
            channels=["slack", "email"],
            description="فشل المهام يُرسل لـ Slack والبريد",
        ))

        # قاعدة: انقطاع العمال يذهب لـ Slack
        self.add_rule(NotificationRule(
            name="worker_offline_alert",
            condition=RuleCondition.CATEGORY_IS,
            condition_value=NotificationCategory.WORKER_OFFLINE,
            channels=["slack", "discord"],
            description="انقطاع العمال يُرسل لـ Slack و Discord",
        ))

        # قاعدة: كل شيء يذهب للـ console
        self.add_rule(NotificationRule(
            name="console_all",
            condition=RuleCondition.ALWAYS,
            channels=["console"],
            description="جميع الإشعارات تُطبع في الـ console",
        ))

    def to_dict(self) -> List[Dict[str, Any]]:
        """تحويل القواعد لـ dict"""
        return [
            {
                "name": r.name,
                "condition": r.condition.value,
                "condition_value": str(r.condition_value) if r.condition_value else None,
                "channels": r.channels,
                "enabled": r.enabled,
                "description": r.description,
            }
            for r in self.rules
        ]
