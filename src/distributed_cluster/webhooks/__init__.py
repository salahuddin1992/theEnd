"""
Webhook Integration - تكامل الـ Webhooks
=========================================

Webhook Notification System
---------------------------

This module provides webhook integration for event notifications:
- Discord, Slack, Teams support
- Custom URL webhooks
- Payload templates
- Retry logic with exponential backoff

يوفر هذا النظام تكامل webhooks للإشعارات:
- دعم Discord, Slack, Teams
- webhooks مخصصة
- قوالب البيانات
- إعادة المحاولة مع تأخير أسي

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.webhooks.providers import (
    CustomWebhook,
    DiscordWebhook,
    SlackWebhook,
    TeamsWebhook,
)
from distributed_cluster.webhooks.templates import (
    PayloadTemplate,
    TemplateEngine,
)
from distributed_cluster.webhooks.webhook import (
    WebhookConfig,
    WebhookEvent,
    WebhookManager,
    WebhookProvider,
    WebhookResult,
)

__all__ = [
    # Core
    "WebhookManager",
    "WebhookConfig",
    "WebhookEvent",
    "WebhookResult",
    "WebhookProvider",
    # Templates
    "PayloadTemplate",
    "TemplateEngine",
    # Providers
    "DiscordWebhook",
    "SlackWebhook",
    "TeamsWebhook",
    "CustomWebhook",
]
