"""
Custom Webhook Provider - مزود مخصص
====================================

Custom Webhook Integration
--------------------------

This module provides a custom/generic webhook provider.

يوفر هذا الملف مزود webhook مخصص/عام.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Any, Callable, Optional

from distributed_cluster.webhooks.templates import TemplateEngine
from distributed_cluster.webhooks.webhook import (
    WebhookConfig,
    WebhookEvent,
    WebhookProvider,
)


class CustomWebhook(WebhookProvider):
    """
    مزود Webhook مخصص
    Custom Webhook Provider

    يوفر مرونة كاملة في تنسيق البيانات والـ headers.
    Provides full flexibility in payload formatting and headers.
    """

    def __init__(
        self,
        payload_template: Optional[dict[str, Any]] = None,
        headers_template: Optional[dict[str, str]] = None,
        signature_header: str = "X-Webhook-Signature",
        signature_algorithm: str = "sha256",
        include_metadata: bool = True,
        transform_fn: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    ):
        """
        تهيئة المزود

        Args:
            payload_template: قالب البيانات
            headers_template: قالب الـ headers
            signature_header: اسم header التوقيع
            signature_algorithm: خوارزمية التوقيع
            include_metadata: تضمين البيانات الوصفية
            transform_fn: دالة تحويل مخصصة
        """
        self.payload_template = payload_template
        self.headers_template = headers_template or {}
        self.signature_header = signature_header
        self.signature_algorithm = signature_algorithm
        self.include_metadata = include_metadata
        self.transform_fn = transform_fn

        # Template engine for variable substitution
        self._template_engine = TemplateEngine()

    def format_payload(self, event: WebhookEvent) -> dict[str, Any]:
        """تنسيق البيانات"""
        # Build context for template rendering
        context = self._build_context(event)

        # Use template if provided
        if self.payload_template:
            payload = self._template_engine.render(self.payload_template, context)
        else:
            payload = self._build_default_payload(event)

        # Apply custom transform
        if self.transform_fn:
            payload = self.transform_fn(payload)

        return payload

    def get_headers(self, config: WebhookConfig) -> dict[str, str]:
        """الحصول على headers"""
        headers = {
            "Content-Type": "application/json",
        }

        # Add template headers
        if self.headers_template:
            context = {
                "webhook_id": config.webhook_id,
                "provider": config.provider,
                "timestamp": datetime.utcnow().isoformat(),
            }
            for key, value in self.headers_template.items():
                if isinstance(value, str) and "{{" in value:
                    headers[key] = self._template_engine.render(value, context)
                else:
                    headers[key] = value

        # Add config headers
        headers.update(config.headers)

        return headers

    def sign_payload(
        self,
        payload: bytes,
        secret: str,
    ) -> str:
        """توقيع البيانات"""
        if self.signature_algorithm == "sha256":
            signature = hmac.new(
                secret.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()
        elif self.signature_algorithm == "sha512":
            signature = hmac.new(
                secret.encode(),
                payload,
                hashlib.sha512,
            ).hexdigest()
        elif self.signature_algorithm == "sha1":
            signature = hmac.new(
                secret.encode(),
                payload,
                hashlib.sha1,
            ).hexdigest()
        else:
            signature = hmac.new(
                secret.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()

        return f"{self.signature_algorithm}={signature}"

    def _build_context(self, event: WebhookEvent) -> dict[str, Any]:
        """بناء السياق للقالب"""
        context = {
            # Event info
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "timestamp": event.timestamp,
            "source": event.source,
            "version": event.version,
            # Flattened data
            **event.data,
            # Nested data
            "data": event.data,
        }

        return context

    def _build_default_payload(self, event: WebhookEvent) -> dict[str, Any]:
        """بناء البيانات الافتراضية"""
        payload = {
            "event": {
                "id": event.event_id,
                "type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                "source": event.source,
                "version": event.version,
            },
            "data": event.data,
        }

        if self.include_metadata:
            payload["metadata"] = {
                "sent_at": datetime.utcnow().isoformat(),
                "provider": "custom",
            }

        return payload


# =============================================================================
# Specialized Custom Providers
# =============================================================================

class GitHubWebhook(CustomWebhook):
    """
    مزود GitHub Webhook
    GitHub-style Webhook Provider
    """

    def __init__(self):
        super().__init__(
            signature_header="X-Hub-Signature-256",
            signature_algorithm="sha256",
        )

    def format_payload(self, event: WebhookEvent) -> dict[str, Any]:
        """تنسيق بيانات GitHub-style"""
        return {
            "action": event.event_type.value.split(".")[-1],
            "sender": {
                "login": event.source,
            },
            "repository": event.data.get("repository", {}),
            event.event_type.value.split(".")[0]: event.data,
        }


class PagerDutyWebhook(CustomWebhook):
    """
    مزود PagerDuty Webhook
    PagerDuty Events API v2 Provider
    """

    def __init__(
        self,
        routing_key: str,
        service_name: str = "Distributed Cluster",
    ):
        super().__init__()
        self.routing_key = routing_key
        self.service_name = service_name

    def format_payload(self, event: WebhookEvent) -> dict[str, Any]:
        """تنسيق بيانات PagerDuty"""
        from distributed_cluster.webhooks.webhook import EventType

        # Determine event action
        if event.event_type in (
            EventType.WORKER_FAILED,
            EventType.JOB_FAILED,
            EventType.ALERT_FIRED,
            EventType.SYSTEM_ERROR,
        ):
            event_action = "trigger"
        elif event.event_type in (
            EventType.ALERT_RESOLVED,
            EventType.WORKER_RECOVERED,
        ):
            event_action = "resolve"
        else:
            event_action = "trigger"

        # Determine severity
        if event.event_type in (EventType.SYSTEM_ERROR, EventType.ALERT_FIRED):
            severity = "critical"
        elif event.event_type in (EventType.WORKER_FAILED, EventType.JOB_FAILED):
            severity = "error"
        elif event.event_type in (EventType.SYSTEM_WARNING,):
            severity = "warning"
        else:
            severity = "info"

        return {
            "routing_key": self.routing_key,
            "event_action": event_action,
            "dedup_key": f"{event.source}-{event.event_type.value}",
            "payload": {
                "summary": event.data.get("message", f"{event.event_type.value}"),
                "source": event.source,
                "severity": severity,
                "timestamp": event.timestamp.isoformat(),
                "component": event.data.get("component", "cluster"),
                "group": event.data.get("group", "default"),
                "class": event.event_type.value,
                "custom_details": event.data,
            },
            "client": self.service_name,
        }


class OpsGenieWebhook(CustomWebhook):
    """
    مزود OpsGenie Webhook
    OpsGenie Alert API Provider
    """

    def __init__(
        self,
        api_key: str,
        priority: str = "P3",
    ):
        super().__init__()
        self.api_key = api_key
        self.priority = priority

    def format_payload(self, event: WebhookEvent) -> dict[str, Any]:
        """تنسيق بيانات OpsGenie"""
        from distributed_cluster.webhooks.webhook import EventType

        # Determine priority
        if event.event_type in (EventType.SYSTEM_ERROR, EventType.ALERT_FIRED):
            priority = "P1"
        elif event.event_type in (EventType.WORKER_FAILED, EventType.JOB_FAILED):
            priority = "P2"
        elif event.event_type in (EventType.SYSTEM_WARNING,):
            priority = "P3"
        else:
            priority = self.priority

        return {
            "message": event.data.get("message", f"{event.event_type.value}"),
            "alias": event.event_id,
            "description": str(event.data),
            "entity": event.source,
            "source": event.source,
            "priority": priority,
            "tags": [
                event.event_type.value,
                event.source,
            ],
            "details": event.data,
        }

    def get_headers(self, config: WebhookConfig) -> dict[str, str]:
        """الحصول على headers"""
        headers = super().get_headers(config)
        headers["Authorization"] = f"GenieKey {self.api_key}"
        return headers


# =============================================================================
# Helper Functions
# =============================================================================

def create_custom_provider(
    payload_template: Optional[dict[str, Any]] = None,
    headers_template: Optional[dict[str, str]] = None,
) -> CustomWebhook:
    """إنشاء مزود مخصص"""
    return CustomWebhook(
        payload_template=payload_template,
        headers_template=headers_template,
    )


def create_pagerduty_provider(
    routing_key: str,
    service_name: str = "Distributed Cluster",
) -> PagerDutyWebhook:
    """إنشاء مزود PagerDuty"""
    return PagerDutyWebhook(
        routing_key=routing_key,
        service_name=service_name,
    )


def create_opsgenie_provider(
    api_key: str,
    priority: str = "P3",
) -> OpsGenieWebhook:
    """إنشاء مزود OpsGenie"""
    return OpsGenieWebhook(
        api_key=api_key,
        priority=priority,
    )
