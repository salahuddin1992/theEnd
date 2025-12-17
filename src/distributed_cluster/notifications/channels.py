"""
Notification Channels - قنوات الإشعارات
========================================

Different notification channels for alerting users.
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class NotificationPriority(str, Enum):
    """أولوية الإشعار."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Notification:
    """إشعار."""
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    source: str = "distributed-cluster"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    # For tracking
    notification_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "tags": self.tags,
        }


class NotificationChannel(abc.ABC):
    """قناة إشعارات أساسية."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.enabled = config.get("enabled", True)

    @abc.abstractmethod
    async def send(self, notification: Notification) -> bool:
        """إرسال إشعار."""
        pass

    @abc.abstractmethod
    async def test_connection(self) -> bool:
        """اختبار الاتصال."""
        pass


class EmailChannel(NotificationChannel):
    """
    قناة البريد الإلكتروني.

    Config:
        smtp_host: SMTP server hostname
        smtp_port: SMTP port (default 587)
        username: SMTP username
        password: SMTP password
        from_email: Sender email address
        to_emails: List of recipient emails
        use_tls: Use TLS (default True)
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.smtp_host = config.get("smtp_host", "localhost")
        self.smtp_port = config.get("smtp_port", 587)
        self.username = config.get("username")
        self.password = config.get("password")
        self.from_email = config.get("from_email", "noreply@distributed-cluster.local")
        self.to_emails = config.get("to_emails", [])
        self.use_tls = config.get("use_tls", True)

    async def send(self, notification: Notification) -> bool:
        """إرسال بريد إلكتروني."""
        if not self.enabled:
            return False

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{notification.priority.value.upper()}] {notification.title}"
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)

            # Plain text version
            text_content = f"""
{notification.title}
{'=' * len(notification.title)}

{notification.message}

Priority: {notification.priority.value}
Time: {notification.timestamp.isoformat()}
Source: {notification.source}

---
Distributed Computing System
            """.strip()

            # HTML version
            priority_color = {
                NotificationPriority.LOW: "#6c757d",
                NotificationPriority.NORMAL: "#17a2b8",
                NotificationPriority.HIGH: "#ffc107",
                NotificationPriority.CRITICAL: "#dc3545",
            }.get(notification.priority, "#17a2b8")

            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background: {priority_color}; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ padding: 20px; }}
        .footer {{ background: #f8f9fa; padding: 15px 20px; border-radius: 0 0 8px 8px; font-size: 12px; color: #6c757d; }}
        .meta {{ color: #6c757d; font-size: 14px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin: 0;">{notification.title}</h2>
        </div>
        <div class="content">
            <p>{notification.message}</p>
            <div class="meta">
                <p><strong>Priority:</strong> {notification.priority.value}</p>
                <p><strong>Time:</strong> {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                <p><strong>Source:</strong> {notification.source}</p>
            </div>
        </div>
        <div class="footer">
            Distributed Computing System Notification
        </div>
    </div>
</body>
</html>
            """

            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            # Send email (in thread pool to avoid blocking)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_email_sync, msg)

            logger.info(f"Email sent to {len(self.to_emails)} recipients")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            notification.error = str(e)
            return False

    def _send_email_sync(self, msg) -> None:
        """إرسال البريد بشكل متزامن."""
        import smtplib

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.send_message(msg)

    async def test_connection(self) -> bool:
        """اختبار اتصال SMTP."""
        try:
            import smtplib

            loop = asyncio.get_event_loop()

            def test_sync():
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                    if self.use_tls:
                        server.starttls()
                    if self.username and self.password:
                        server.login(self.username, self.password)
                    return True

            return await loop.run_in_executor(None, test_sync)
        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False


class SlackChannel(NotificationChannel):
    """
    قناة Slack.

    Config:
        webhook_url: Slack incoming webhook URL
        channel: Optional channel override
        username: Bot username
        icon_emoji: Bot icon emoji
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.webhook_url = config.get("webhook_url", "")
        self.channel = config.get("channel")
        self.username = config.get("username", "DC Bot")
        self.icon_emoji = config.get("icon_emoji", ":robot_face:")

    async def send(self, notification: Notification) -> bool:
        """إرسال إشعار Slack."""
        if not self.enabled or not self.webhook_url:
            return False

        try:
            # Color based on priority
            color = {
                NotificationPriority.LOW: "#6c757d",
                NotificationPriority.NORMAL: "#17a2b8",
                NotificationPriority.HIGH: "#ffc107",
                NotificationPriority.CRITICAL: "#dc3545",
            }.get(notification.priority, "#17a2b8")

            # Build payload
            payload = {
                "username": self.username,
                "icon_emoji": self.icon_emoji,
                "attachments": [
                    {
                        "color": color,
                        "title": notification.title,
                        "text": notification.message,
                        "fields": [
                            {
                                "title": "Priority",
                                "value": notification.priority.value.upper(),
                                "short": True,
                            },
                            {
                                "title": "Source",
                                "value": notification.source,
                                "short": True,
                            },
                        ],
                        "footer": "Distributed Computing System",
                        "ts": int(notification.timestamp.timestamp()),
                    }
                ],
            }

            if self.channel:
                payload["channel"] = self.channel

            # Add metadata fields if present
            if notification.metadata:
                for key, value in list(notification.metadata.items())[:5]:
                    payload["attachments"][0]["fields"].append({
                        "title": key,
                        "value": str(value),
                        "short": True,
                    })

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10,
                )
                response.raise_for_status()

            logger.info(f"Slack notification sent: {notification.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            notification.error = str(e)
            return False

    async def test_connection(self) -> bool:
        """اختبار webhook."""
        if not self.webhook_url:
            return False

        try:
            async with httpx.AsyncClient() as client:
                # Slack webhooks accept POST but may fail with empty payload
                response = await client.post(
                    self.webhook_url,
                    json={"text": "Test notification from Distributed Computing System"},
                    timeout=10,
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Slack test failed: {e}")
            return False


class WebhookChannel(NotificationChannel):
    """
    قناة Webhook عامة.

    Config:
        url: Webhook endpoint URL
        method: HTTP method (POST, PUT)
        headers: Additional headers
        secret: HMAC secret for signature
        retry_count: Number of retries
        timeout: Request timeout
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.url = config.get("url", "")
        self.method = config.get("method", "POST").upper()
        self.headers = config.get("headers", {})
        self.secret = config.get("secret")
        self.retry_count = config.get("retry_count", 3)
        self.timeout = config.get("timeout", 30)

    async def send(self, notification: Notification) -> bool:
        """إرسال webhook."""
        if not self.enabled or not self.url:
            return False

        payload = notification.to_dict()
        payload_bytes = json.dumps(payload).encode()

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DistributedCluster/1.0",
            **self.headers,
        }

        # Add signature if secret is configured
        if self.secret:
            signature = hmac.new(
                self.secret.encode(),
                payload_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Signature-256"] = f"sha256={signature}"

        async with httpx.AsyncClient() as client:
            for attempt in range(self.retry_count):
                try:
                    if self.method == "POST":
                        response = await client.post(
                            self.url,
                            content=payload_bytes,
                            headers=headers,
                            timeout=self.timeout,
                        )
                    elif self.method == "PUT":
                        response = await client.put(
                            self.url,
                            content=payload_bytes,
                            headers=headers,
                            timeout=self.timeout,
                        )
                    else:
                        raise ValueError(f"Unsupported method: {self.method}")

                    if response.status_code < 400:
                        logger.info(f"Webhook sent to {self.url}")
                        return True

                    logger.warning(
                        f"Webhook returned {response.status_code}, attempt {attempt + 1}/{self.retry_count}"
                    )

                except Exception as e:
                    logger.error(f"Webhook attempt {attempt + 1} failed: {e}")

                if attempt < self.retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        notification.error = f"Failed after {self.retry_count} attempts"
        return False

    async def test_connection(self) -> bool:
        """اختبار الـ endpoint."""
        if not self.url:
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.head(self.url, timeout=10)
                return response.status_code < 500
        except Exception:
            return False


class PagerDutyChannel(NotificationChannel):
    """
    قناة PagerDuty.

    Config:
        routing_key: PagerDuty Events API v2 routing key
        service_name: Service name for events
    """

    EVENTS_API = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.routing_key = config.get("routing_key", "")
        self.service_name = config.get("service_name", "Distributed Cluster")

    async def send(self, notification: Notification) -> bool:
        """إرسال حدث PagerDuty."""
        if not self.enabled or not self.routing_key:
            return False

        try:
            # Map priority to severity
            severity = {
                NotificationPriority.LOW: "info",
                NotificationPriority.NORMAL: "warning",
                NotificationPriority.HIGH: "error",
                NotificationPriority.CRITICAL: "critical",
            }.get(notification.priority, "warning")

            payload = {
                "routing_key": self.routing_key,
                "event_action": "trigger",
                "dedup_key": notification.notification_id,
                "payload": {
                    "summary": notification.title,
                    "source": notification.source,
                    "severity": severity,
                    "timestamp": notification.timestamp.isoformat(),
                    "custom_details": {
                        "message": notification.message,
                        **notification.metadata,
                    },
                },
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.EVENTS_API,
                    json=payload,
                    timeout=30,
                )
                response.raise_for_status()

            logger.info(f"PagerDuty event created: {notification.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to send PagerDuty event: {e}")
            notification.error = str(e)
            return False

    async def test_connection(self) -> bool:
        """اختبار API."""
        if not self.routing_key:
            return False

        # PagerDuty doesn't have a test endpoint, so we just validate the key format
        return len(self.routing_key) > 20


class ConsoleChannel(NotificationChannel):
    """
    قناة للطباعة في Console (للتطوير).
    """

    def __init__(self, name: str = "console", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config or {})

    async def send(self, notification: Notification) -> bool:
        """طباعة الإشعار."""
        priority_symbol = {
            NotificationPriority.LOW: "ℹ️ ",
            NotificationPriority.NORMAL: "📢",
            NotificationPriority.HIGH: "⚠️ ",
            NotificationPriority.CRITICAL: "🚨",
        }.get(notification.priority, "📢")

        print(f"""
{priority_symbol} [{notification.priority.value.upper()}] {notification.title}
{'─' * 50}
{notification.message}

Time: {notification.timestamp.isoformat()}
Source: {notification.source}
{'─' * 50}
""")
        return True

    async def test_connection(self) -> bool:
        return True
