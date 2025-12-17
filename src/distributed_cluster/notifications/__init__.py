"""
Notification System - نظام الإشعارات المتقدم
============================================

Enterprise-Grade Multi-Channel Notification System
نظام إشعارات متعدد القنوات على مستوى المؤسسات

Supported Channels - القنوات المدعومة:
- Webhook (Slack, Discord, Custom, MS Teams)
- Email (SMTP with templates)
- Desktop notifications (cross-platform)
- PagerDuty alerts (incident management)
- SMS notifications (Twilio integration)
- Push notifications (Firebase/APNs)
- Custom handlers (extensible architecture)

Features - الميزات:
- Priority-based routing
- Rate limiting & throttling
- Retry mechanisms with exponential backoff
- Template engine support
- Async/await support
- Batch notifications
- Notification history & audit trail
- Arabic/English RTL support

Author: Dawood AI Assistant Project
License: MIT
"""

from typing import TYPE_CHECKING

# Version info
__version__ = "2.0.0"
__author__ = "Dawood AI Assistant"

# Core notification components
from .notifier import (
    Notifier,
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    Notification,
    NotificationResult,
    NotificationBatch,
)

# Channel implementations
from .channels import (
    BaseChannel,
    WebhookChannel,
    SlackChannel,
    DiscordChannel,
    TeamsChannel,
    EmailChannel,
    SMTPChannel,
    DesktopChannel,
    ConsoleChannel,
    PagerDutyChannel,
    TwilioSMSChannel,
    FirebasePushChannel,
    CustomChannel,
)

# Rules and conditions engine
from .rules import (
    NotificationRule,
    RuleCondition,
    RuleAction,
    RuleEngine,
    ConditionalRouter,
)

# Manager and orchestration
from .manager import (
    NotificationManager,
    NotificationQueue,
    NotificationScheduler,
    NotificationHistory,
    RateLimiter,
)

# Templates
from .templates import (
    NotificationTemplate,
    TemplateEngine,
    HTMLTemplate,
    MarkdownTemplate,
    RTLTemplate,
)

# Exceptions
from .exceptions import (
    NotificationError,
    ChannelError,
    DeliveryError,
    RateLimitError,
    TemplateError,
    ConfigurationError,
)

# Type definitions for static analysis
if TYPE_CHECKING:
    from .types import (
        NotificationPayload,
        ChannelConfig,
        RuleConfig,
        TemplateContext,
    )

__all__ = [
    # Version
    "__version__",
    "__author__",
    # Core
    "Notifier",
    "NotificationChannel",
    "NotificationPriority",
    "NotificationStatus",
    "Notification",
    "NotificationResult",
    "NotificationBatch",
    # Channels
    "BaseChannel",
    "WebhookChannel",
    "SlackChannel",
    "DiscordChannel",
    "TeamsChannel",
    "EmailChannel",
    "SMTPChannel",
    "DesktopChannel",
    "ConsoleChannel",
    "PagerDutyChannel",
    "TwilioSMSChannel",
    "FirebasePushChannel",
    "CustomChannel",
    # Rules
    "NotificationRule",
    "RuleCondition",
    "RuleAction",
    "RuleEngine",
    "ConditionalRouter",
    # Manager
    "NotificationManager",
    "NotificationQueue",
    "NotificationScheduler",
    "NotificationHistory",
    "RateLimiter",
    # Templates
    "NotificationTemplate",
    "TemplateEngine",
    "HTMLTemplate",
    "MarkdownTemplate",
    "RTLTemplate",
    # Exceptions
    "NotificationError",
    "ChannelError",
    "DeliveryError",
    "RateLimitError",
    "TemplateError",
    "ConfigurationError",
]


def get_version() -> str:
    """Return the current version of the notification system."""
    return __version__


def create_notifier(
    channels: list[str] | None = None,
    config: dict | None = None,
) -> "Notifier":
    """
    Factory function to create a configured Notifier instance.
    
    Args:
        channels: List of channel names to enable
        config: Configuration dictionary
        
    Returns:
        Configured Notifier instance
        
    Example:
        >>> notifier = create_notifier(
        ...     channels=["slack", "email"],
        ...     config={"slack_webhook": "https://..."}
        ... )
    """
    notifier = Notifier(config=config)
    
    if channels:
        channel_map = {
            "webhook": WebhookChannel,
            "slack": SlackChannel,
            "discord": DiscordChannel,
            "teams": TeamsChannel,
            "email": EmailChannel,
            "smtp": SMTPChannel,
            "desktop": DesktopChannel,
            "console": ConsoleChannel,
            "pagerduty": PagerDutyChannel,
            "sms": TwilioSMSChannel,
            "push": FirebasePushChannel,
        }
        
        for channel_name in channels:
            if channel_name.lower() in channel_map:
                channel_class = channel_map[channel_name.lower()]
                channel_config = config.get(f"{channel_name}_config", {}) if config else {}
                notifier.add_channel(channel_class(**channel_config))
    
    return notifier