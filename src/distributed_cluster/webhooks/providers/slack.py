"""
Slack Webhook Provider - مزود Slack
====================================

Slack Webhook Integration
-------------------------

This module provides Slack webhook integration.

يوفر هذا الملف تكامل Slack webhook.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

from typing import Any, Optional

from distributed_cluster.webhooks.webhook import (
    EventType,
    WebhookConfig,
    WebhookEvent,
    WebhookProvider,
)


class SlackWebhook(WebhookProvider):
    """
    مزود Slack Webhook
    Slack Webhook Provider

    يوفر تنسيق البيانات المتوافق مع Slack Block Kit.
    Provides Slack Block Kit compatible payload formatting.
    """

    # Severity colors
    COLORS = {
        "info": "#3498DB",
        "success": "#2ECC71",
        "warning": "#F39C12",
        "error": "#E74C3C",
        "critical": "#9B59B6",
    }

    # Event emojis
    EMOJIS = {
        EventType.CLUSTER_CREATED: ":new:",
        EventType.CLUSTER_UPDATED: ":arrows_counterclockwise:",
        EventType.CLUSTER_DELETED: ":wastebasket:",
        EventType.CLUSTER_SCALED: ":bar_chart:",
        EventType.WORKER_JOINED: ":white_check_mark:",
        EventType.WORKER_LEFT: ":wave:",
        EventType.WORKER_FAILED: ":x:",
        EventType.WORKER_RECOVERED: ":green_heart:",
        EventType.JOB_SUBMITTED: ":outbox_tray:",
        EventType.JOB_STARTED: ":arrow_forward:",
        EventType.JOB_COMPLETED: ":heavy_check_mark:",
        EventType.JOB_FAILED: ":boom:",
        EventType.JOB_CANCELLED: ":no_entry_sign:",
        EventType.ALERT_FIRED: ":rotating_light:",
        EventType.ALERT_RESOLVED: ":white_check_mark:",
        EventType.SYSTEM_ERROR: ":warning:",
        EventType.SYSTEM_WARNING: ":zap:",
    }

    def __init__(
        self,
        channel: Optional[str] = None,
        username: str = "Distributed Cluster",
        icon_emoji: str = ":robot_face:",
        include_footer: bool = True,
    ):
        """
        تهيئة المزود

        Args:
            channel: القناة المستهدفة
            username: اسم المستخدم
            icon_emoji: إيموجي الأيقونة
            include_footer: تضمين تذييل
        """
        self.channel = channel
        self.username = username
        self.icon_emoji = icon_emoji
        self.include_footer = include_footer

    def format_payload(self, event: WebhookEvent) -> dict[str, Any]:
        """تنسيق البيانات لـ Slack"""
        emoji = self.EMOJIS.get(event.event_type, ":bell:")
        color = self._get_color(event)
        title = self._get_title(event)

        # Build blocks
        blocks = self._build_blocks(event, emoji, title)

        # Build attachment for color
        attachment = {
            "color": color,
            "blocks": blocks,
        }

        # Build payload
        payload: dict[str, Any] = {
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "attachments": [attachment],
        }

        if self.channel:
            payload["channel"] = self.channel

        return payload

    def get_headers(self, config: WebhookConfig) -> dict[str, str]:
        """الحصول على headers"""
        headers = {
            "Content-Type": "application/json",
        }

        # Add auth token if provided
        if config.secret:
            headers["Authorization"] = f"Bearer {config.secret}"

        return headers

    def _get_color(self, event: WebhookEvent) -> str:
        """الحصول على اللون"""
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

    def _build_blocks(
        self,
        event: WebhookEvent,
        emoji: str,
        title: str,
    ) -> list[dict[str, Any]]:
        """بناء البلوكات"""
        blocks = []

        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {title}",
                "emoji": True,
            },
        })

        # Description
        description = self._get_description(event)
        if description:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": description,
                },
            })

        # Fields
        fields = self._build_fields(event)
        if fields:
            blocks.append({
                "type": "section",
                "fields": fields,
            })

        # Divider
        blocks.append({"type": "divider"})

        # Footer
        if self.include_footer:
            timestamp = int(event.timestamp.timestamp())
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Source: *{event.source}* | Event ID: `{event.event_id[:8]}` | "
                            f"<!date^{timestamp}^{{date_short_pretty}} at {{time}}|{event.timestamp.isoformat()}>"
                        ),
                    },
                ],
            })

        return blocks

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
            return f"*{data.get('name', 'Alert')}*: {data.get('message', 'No details')}"

        return ""

    def _build_fields(self, event: WebhookEvent) -> list[dict[str, Any]]:
        """بناء الحقول"""
        fields = []
        data = event.data

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
                    "type": "mrkdwn",
                    "text": f"*{label}:*\n{value}",
                })

        return fields[:10]  # Slack limit


# =============================================================================
# Helper Functions
# =============================================================================

def create_slack_provider(
    channel: Optional[str] = None,
    username: str = "Distributed Cluster Bot",
) -> SlackWebhook:
    """إنشاء مزود Slack"""
    return SlackWebhook(
        channel=channel,
        username=username,
    )
