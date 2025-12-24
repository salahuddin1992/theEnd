"""
Discord Webhook Provider - مزود Discord
========================================

Discord Webhook Integration
---------------------------

This module provides Discord webhook integration.

يوفر هذا الملف تكامل Discord webhook.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from distributed_cluster.webhooks.webhook import (
    WebhookProvider,
    WebhookConfig,
    WebhookEvent,
    EventType,
)


class DiscordWebhook(WebhookProvider):
    """
    مزود Discord Webhook
    Discord Webhook Provider

    يوفر تنسيق البيانات المتوافق مع Discord.
    Provides Discord-compatible payload formatting.
    """

    # Severity colors
    COLORS = {
        "info": 0x3498DB,      # Blue
        "success": 0x2ECC71,   # Green
        "warning": 0xF39C12,   # Orange
        "error": 0xE74C3C,     # Red
        "critical": 0x9B59B6,  # Purple
    }

    # Event emojis
    EMOJIS = {
        EventType.CLUSTER_CREATED: "🆕",
        EventType.CLUSTER_UPDATED: "🔄",
        EventType.CLUSTER_DELETED: "🗑️",
        EventType.CLUSTER_SCALED: "📊",
        EventType.WORKER_JOINED: "✅",
        EventType.WORKER_LEFT: "👋",
        EventType.WORKER_FAILED: "❌",
        EventType.WORKER_RECOVERED: "💚",
        EventType.JOB_SUBMITTED: "📤",
        EventType.JOB_STARTED: "▶️",
        EventType.JOB_COMPLETED: "✔️",
        EventType.JOB_FAILED: "💥",
        EventType.JOB_CANCELLED: "🚫",
        EventType.ALERT_FIRED: "🚨",
        EventType.ALERT_RESOLVED: "✅",
        EventType.SYSTEM_ERROR: "⚠️",
        EventType.SYSTEM_WARNING: "⚡",
    }

    def __init__(
        self,
        username: str = "Distributed Cluster",
        avatar_url: Optional[str] = None,
        include_timestamp: bool = True,
    ):
        """
        تهيئة المزود

        Args:
            username: اسم المستخدم للظهور
            avatar_url: رابط صورة الملف الشخصي
            include_timestamp: تضمين الوقت
        """
        self.username = username
        self.avatar_url = avatar_url
        self.include_timestamp = include_timestamp

    def format_payload(self, event: WebhookEvent) -> dict[str, Any]:
        """تنسيق البيانات لـ Discord"""
        # Get event info
        emoji = self.EMOJIS.get(event.event_type, "📢")
        color = self._get_color(event)
        title = self._get_title(event)
        description = self._get_description(event)

        # Build embed
        embed: dict[str, Any] = {
            "title": f"{emoji} {title}",
            "description": description,
            "color": color,
            "fields": self._build_fields(event),
        }

        if self.include_timestamp:
            embed["timestamp"] = event.timestamp.isoformat()

        # Footer
        embed["footer"] = {
            "text": f"Source: {event.source} | Event ID: {event.event_id[:8]}",
        }

        # Build payload
        payload: dict[str, Any] = {
            "username": self.username,
            "embeds": [embed],
        }

        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url

        return payload

    def get_headers(self, config: WebhookConfig) -> dict[str, str]:
        """الحصول على headers"""
        return {
            "Content-Type": "application/json",
        }

    def _get_color(self, event: WebhookEvent) -> int:
        """الحصول على اللون"""
        # Determine severity from event type
        if event.event_type in (
            EventType.WORKER_FAILED,
            EventType.JOB_FAILED,
            EventType.SYSTEM_ERROR,
        ):
            return self.COLORS["error"]
        elif event.event_type in (
            EventType.ALERT_FIRED,
        ):
            return self.COLORS["critical"]
        elif event.event_type in (
            EventType.SYSTEM_WARNING,
            EventType.WORKER_LEFT,
            EventType.JOB_CANCELLED,
        ):
            return self.COLORS["warning"]
        elif event.event_type in (
            EventType.WORKER_JOINED,
            EventType.JOB_COMPLETED,
            EventType.ALERT_RESOLVED,
            EventType.WORKER_RECOVERED,
        ):
            return self.COLORS["success"]
        else:
            return self.COLORS["info"]

    def _get_title(self, event: WebhookEvent) -> str:
        """الحصول على العنوان"""
        titles = {
            EventType.CLUSTER_CREATED: "Cluster Created",
            EventType.CLUSTER_UPDATED: "Cluster Updated",
            EventType.CLUSTER_DELETED: "Cluster Deleted",
            EventType.CLUSTER_SCALED: "Cluster Scaled",
            EventType.WORKER_JOINED: "Worker Joined",
            EventType.WORKER_LEFT: "Worker Left",
            EventType.WORKER_FAILED: "Worker Failed",
            EventType.WORKER_RECOVERED: "Worker Recovered",
            EventType.JOB_SUBMITTED: "Job Submitted",
            EventType.JOB_STARTED: "Job Started",
            EventType.JOB_COMPLETED: "Job Completed",
            EventType.JOB_FAILED: "Job Failed",
            EventType.JOB_CANCELLED: "Job Cancelled",
            EventType.ALERT_FIRED: "Alert Fired",
            EventType.ALERT_RESOLVED: "Alert Resolved",
            EventType.SYSTEM_ERROR: "System Error",
            EventType.SYSTEM_WARNING: "System Warning",
        }
        return titles.get(event.event_type, event.event_type.value)

    def _get_description(self, event: WebhookEvent) -> str:
        """الحصول على الوصف"""
        data = event.data

        if "message" in data:
            return data["message"]

        if event.event_type == EventType.JOB_FAILED:
            return f"Job `{data.get('job_id', 'unknown')}` failed: {data.get('error', 'Unknown error')}"

        if event.event_type == EventType.WORKER_FAILED:
            return f"Worker `{data.get('worker_id', 'unknown')}` is not responding"

        if event.event_type == EventType.ALERT_FIRED:
            return f"**{data.get('name', 'Alert')}**: {data.get('message', 'No details')}"

        return f"Event: {event.event_type.value}"

    def _build_fields(self, event: WebhookEvent) -> list[dict[str, Any]]:
        """بناء الحقول"""
        fields = []
        data = event.data

        # Common fields
        field_mappings = [
            ("cluster_id", "Cluster"),
            ("worker_id", "Worker"),
            ("job_id", "Job"),
            ("name", "Name"),
            ("status", "Status"),
            ("severity", "Severity"),
            ("count", "Count"),
            ("duration", "Duration"),
        ]

        for key, label in field_mappings:
            if key in data:
                value = data[key]
                if isinstance(value, float):
                    value = f"{value:.2f}"
                fields.append({
                    "name": label,
                    "value": str(value),
                    "inline": True,
                })

        return fields[:25]  # Discord limit


# =============================================================================
# Helper Functions
# =============================================================================

def create_discord_provider(
    username: str = "Distributed Cluster Bot",
    avatar_url: Optional[str] = None,
) -> DiscordWebhook:
    """إنشاء مزود Discord"""
    return DiscordWebhook(
        username=username,
        avatar_url=avatar_url,
    )
