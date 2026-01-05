"""
Microsoft Teams Webhook Provider - مزود Teams
==============================================

Teams Webhook Integration
-------------------------

This module provides Microsoft Teams webhook integration.

يوفر هذا الملف تكامل Microsoft Teams webhook.

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


class TeamsWebhook(WebhookProvider):
    """
    مزود Microsoft Teams Webhook
    Microsoft Teams Webhook Provider

    يوفر تنسيق البيانات المتوافق مع Teams Adaptive Cards.
    Provides Teams Adaptive Cards compatible payload formatting.
    """

    # Theme colors
    COLORS = {
        "info": "0078D4",  # Microsoft Blue
        "success": "107C10",  # Microsoft Green
        "warning": "FFA500",  # Orange
        "error": "D13438",  # Microsoft Red
        "critical": "881798",  # Purple
    }

    def __init__(
        self,
        include_actions: bool = True,
        dashboard_url: Optional[str] = None,
    ):
        """
        تهيئة المزود

        Args:
            include_actions: تضمين أزرار الإجراءات
            dashboard_url: رابط لوحة المراقبة
        """
        self.include_actions = include_actions
        self.dashboard_url = dashboard_url

    def format_payload(self, event: WebhookEvent) -> dict[str, Any]:
        """تنسيق البيانات لـ Teams"""
        color = self._get_color(event)
        title = self._get_title(event)
        summary = self._get_summary(event)

        # Build Adaptive Card
        card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": self._build_body(event, title),
        }

        # Add actions
        if self.include_actions:
            actions = self._build_actions(event)
            if actions:
                card["actions"] = actions

        # Build message
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": card,
                }
            ],
            "summary": summary,
            "themeColor": color,
        }

        return payload

    def get_headers(self, config: WebhookConfig) -> dict[str, str]:
        """الحصول على headers"""
        return {
            "Content-Type": "application/json",
        }

    def _get_color(self, event: WebhookEvent) -> str:
        """الحصول على اللون"""
        if event.event_type in (
            EventType.WORKER_FAILED,
            EventType.JOB_FAILED,
            EventType.SYSTEM_ERROR,
        ):
            return self.COLORS["error"]
        elif event.event_type in (EventType.ALERT_FIRED,):
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
            EventType.CLUSTER_CREATED: "🆕 Cluster Created",
            EventType.CLUSTER_UPDATED: "🔄 Cluster Updated",
            EventType.CLUSTER_DELETED: "🗑️ Cluster Deleted",
            EventType.CLUSTER_SCALED: "📊 Cluster Scaled",
            EventType.WORKER_JOINED: "✅ Worker Joined",
            EventType.WORKER_LEFT: "👋 Worker Left",
            EventType.WORKER_FAILED: "❌ Worker Failed",
            EventType.WORKER_RECOVERED: "💚 Worker Recovered",
            EventType.JOB_SUBMITTED: "📤 Job Submitted",
            EventType.JOB_STARTED: "▶️ Job Started",
            EventType.JOB_COMPLETED: "✔️ Job Completed",
            EventType.JOB_FAILED: "💥 Job Failed",
            EventType.JOB_CANCELLED: "🚫 Job Cancelled",
            EventType.ALERT_FIRED: "🚨 Alert Fired",
            EventType.ALERT_RESOLVED: "✅ Alert Resolved",
            EventType.SYSTEM_ERROR: "⚠️ System Error",
            EventType.SYSTEM_WARNING: "⚡ System Warning",
        }
        return titles.get(event.event_type, f"📢 {event.event_type.value}")

    def _get_summary(self, event: WebhookEvent) -> str:
        """الحصول على الملخص"""
        data = event.data
        if "message" in data:
            return data["message"][:200]
        return f"Distributed Cluster: {event.event_type.value}"

    def _build_body(
        self,
        event: WebhookEvent,
        title: str,
    ) -> list[dict[str, Any]]:
        """بناء الجسم"""
        body = []

        # Header
        body.append(
            {
                "type": "TextBlock",
                "size": "Large",
                "weight": "Bolder",
                "text": title,
                "wrap": True,
            }
        )

        # Description
        description = self._get_description(event)
        if description:
            body.append(
                {
                    "type": "TextBlock",
                    "text": description,
                    "wrap": True,
                }
            )

        # Separator
        body.append(
            {
                "type": "TextBlock",
                "text": " ",
                "separator": True,
            }
        )

        # Facts
        facts = self._build_facts(event)
        if facts:
            body.append(
                {
                    "type": "FactSet",
                    "facts": facts,
                }
            )

        # Timestamp
        body.append(
            {
                "type": "TextBlock",
                "size": "Small",
                "isSubtle": True,
                "text": (
                    f"Source: {event.source} | Event ID: {event.event_id[:8]} | "
                    f"{event.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                ),
                "wrap": True,
            }
        )

        return body

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

        return ""

    def _build_facts(self, event: WebhookEvent) -> list[dict[str, str]]:
        """بناء الحقائق"""
        facts = []
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
                facts.append(
                    {
                        "title": label,
                        "value": str(value),
                    }
                )

        return facts

    def _build_actions(self, event: WebhookEvent) -> list[dict[str, Any]]:
        """بناء الإجراءات"""
        actions = []

        # Dashboard link
        if self.dashboard_url:
            actions.append(
                {
                    "type": "Action.OpenUrl",
                    "title": "Open Dashboard",
                    "url": self.dashboard_url,
                }
            )

        # Event-specific actions
        data = event.data

        if event.event_type in (EventType.JOB_FAILED, EventType.JOB_COMPLETED):
            job_id = data.get("job_id")
            if job_id and self.dashboard_url:
                actions.append(
                    {
                        "type": "Action.OpenUrl",
                        "title": "View Job",
                        "url": f"{self.dashboard_url}/jobs/{job_id}",
                    }
                )

        if event.event_type in (EventType.WORKER_FAILED, EventType.WORKER_LEFT):
            worker_id = data.get("worker_id")
            if worker_id and self.dashboard_url:
                actions.append(
                    {
                        "type": "Action.OpenUrl",
                        "title": "View Worker",
                        "url": f"{self.dashboard_url}/workers/{worker_id}",
                    }
                )

        if event.event_type == EventType.ALERT_FIRED:
            alert_name = data.get("name")
            if alert_name and self.dashboard_url:
                actions.append(
                    {
                        "type": "Action.OpenUrl",
                        "title": "View Alert",
                        "url": f"{self.dashboard_url}/alerts/{alert_name}",
                    }
                )

        return actions


# =============================================================================
# Helper Functions
# =============================================================================


def create_teams_provider(
    dashboard_url: Optional[str] = None,
    include_actions: bool = True,
) -> TeamsWebhook:
    """إنشاء مزود Teams"""
    return TeamsWebhook(
        dashboard_url=dashboard_url,
        include_actions=include_actions,
    )
