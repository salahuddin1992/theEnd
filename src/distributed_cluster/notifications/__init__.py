"""
Notification System - نظام الإشعارات

يوفر إشعارات متعددة القنوات:
- Webhook (Slack, Discord, Custom)
- Email (SMTP)
- Desktop notifications
- Custom handlers
"""

from .notifier import (
    Notifier,
    NotificationChannel,
    NotificationPriority,
    Notification,
)
from .channels import (
    WebhookChannel,
    SlackChannel,
    DiscordChannel,
    EmailChannel,
    ConsoleChannel,
)
from .rules import NotificationRule, RuleCondition

__all__ = [
    "Notifier",
    "NotificationChannel",
    "NotificationPriority",
    "Notification",
    "WebhookChannel",
    "SlackChannel",
    "DiscordChannel",
    "EmailChannel",
    "ConsoleChannel",
    "NotificationRule",
    "RuleCondition",
]
