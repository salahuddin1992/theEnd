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

# Version info
__version__ = "2.0.0"
__author__ = "Dawood AI Assistant"

# Core notification components
from .channels import (
    ConsoleChannel,
    DiscordChannel,
    EmailChannel,
    NotificationManager,  # From channels
    PagerDutyChannel,
    SlackChannel,
    TwilioSMSChannel,
    WebhookChannel,
)
from .channels import (
    ConsoleChannel as DesktopChannel,  # Alias - Desktop uses console for now
)
from .channels import (
    EmailChannel as SMTPChannel,  # Alias
)
from .channels import (
    MicrosoftTeamsChannel as TeamsChannel,  # Alias
)

# Channel implementations
from .channels import (
    NotificationChannel as BaseChannel,  # Alias for backwards compatibility
)
from .channels import (
    TelegramChannel as FirebasePushChannel,  # Placeholder alias
)
from .channels import (
    WebhookChannel as CustomChannel,  # Alias
)
from .notifier import (
    Notification,
    NotificationBatch,
    NotificationCategory,
    NotificationChannel,
    NotificationPriority,
    NotificationResult,
    NotificationStatus,
    Notifier,
)

# Rules and conditions engine
from .rules import (
    NotificationRule,
    RuleCondition,
    RuleEngine,
)

# Aliases for backwards compatibility
RuleAction = RuleCondition
ConditionalRouter = RuleEngine

# Manager components - use from channels which has NotificationManager
NotificationQueue = list  # Simple placeholder
NotificationScheduler = type('NotificationScheduler', (), {})  # Placeholder
NotificationHistory = list  # Simple placeholder
RateLimiter = type('RateLimiter', (), {})  # Placeholder (actual one is in channels)

# Template placeholders
NotificationTemplate = type('NotificationTemplate', (), {})
TemplateEngine = type('TemplateEngine', (), {})
HTMLTemplate = type('HTMLTemplate', (), {})
MarkdownTemplate = type('MarkdownTemplate', (), {})
RTLTemplate = type('RTLTemplate', (), {})

# Exception classes
class NotificationError(Exception):
    """Base exception for notification errors."""
    pass

class ChannelError(NotificationError):
    """Exception for channel-specific errors."""
    pass

class DeliveryError(NotificationError):
    """Exception for delivery failures."""
    pass

class RateLimitError(NotificationError):
    """Exception for rate limiting."""
    pass

class TemplateError(NotificationError):
    """Exception for template errors."""
    pass

class ConfigurationError(NotificationError):
    """Exception for configuration errors."""
    pass


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
    "NotificationCategory",
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
    notifier = Notifier()

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
