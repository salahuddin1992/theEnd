"""
Notification Channels - قنوات الإشعارات

- WebhookChannel: إرسال لأي webhook
- SlackChannel: إرسال لـ Slack
- DiscordChannel: إرسال لـ Discord
- EmailChannel: إرسال بريد إلكتروني
- ConsoleChannel: طباعة في الـ console
"""

import asyncio
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import httpx

from .notifier import NotificationChannel, Notification, NotificationPriority


class ConsoleChannel(NotificationChannel):
    """
    قناة الـ Console

    تطبع الإشعارات في الـ terminal
    """

    def __init__(self, name: str = "console", colored: bool = True):
        super().__init__(name)
        self.colored = colored

    async def send(self, notification: Notification) -> bool:
        """طباعة الإشعار"""
        if self.colored:
            color = self._get_color(notification.priority)
            print(f"{color}[{notification.category.value}] {notification.title}\033[0m")
            print(f"  {notification.message}")
        else:
            print(f"[{notification.category.value}] {notification.title}")
            print(f"  {notification.message}")
        return True

    def _get_color(self, priority: NotificationPriority) -> str:
        colors = {
            NotificationPriority.LOW: "\033[90m",      # رمادي
            NotificationPriority.NORMAL: "\033[94m",   # أزرق
            NotificationPriority.HIGH: "\033[93m",     # أصفر
            NotificationPriority.CRITICAL: "\033[91m", # أحمر
        }
        return colors.get(priority, "\033[0m")


class WebhookChannel(NotificationChannel):
    """
    قناة Webhook عامة

    ترسل HTTP POST لأي URL
    """

    def __init__(
        self,
        name: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 10.0,
    ):
        super().__init__(name)
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}
        self.timeout = timeout

    async def send(self, notification: Notification) -> bool:
        """إرسال الإشعار"""
        payload = self._build_payload(notification)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.url,
                json=payload,
                headers=self.headers,
                timeout=self.timeout,
            )
            return response.status_code in (200, 201, 204)

    def _build_payload(self, notification: Notification) -> Dict[str, Any]:
        """بناء الـ payload"""
        return notification.to_dict()


class SlackChannel(NotificationChannel):
    """
    قناة Slack

    ترسل إشعارات لـ Slack عبر Webhook
    """

    def __init__(
        self,
        name: str = "slack",
        webhook_url: str = "",
        channel: Optional[str] = None,
        username: str = "DC Cluster",
        icon_emoji: str = ":robot_face:",
    ):
        super().__init__(name)
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username
        self.icon_emoji = icon_emoji

    async def send(self, notification: Notification) -> bool:
        """إرسال لـ Slack"""
        payload = self._build_slack_message(notification)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                json=payload,
                timeout=10.0,
            )
            return response.status_code == 200

    def _build_slack_message(self, notification: Notification) -> Dict[str, Any]:
        """بناء رسالة Slack"""
        # تحديد اللون
        color_map = {
            NotificationPriority.LOW: "#808080",
            NotificationPriority.NORMAL: "#2196F3",
            NotificationPriority.HIGH: "#FF9800",
            NotificationPriority.CRITICAL: "#F44336",
        }
        color = color_map.get(notification.priority, "#2196F3")

        message = {
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "attachments": [
                {
                    "color": color,
                    "title": notification.title,
                    "text": notification.message,
                    "footer": f"Distributed Cluster | {notification.category.value}",
                    "ts": int(notification.timestamp.timestamp()),
                    "fields": [
                        {"title": k, "value": str(v), "short": True}
                        for k, v in list(notification.data.items())[:4]
                    ],
                }
            ],
        }

        if self.channel:
            message["channel"] = self.channel

        return message


class DiscordChannel(NotificationChannel):
    """
    قناة Discord

    ترسل إشعارات لـ Discord عبر Webhook
    """

    def __init__(
        self,
        name: str = "discord",
        webhook_url: str = "",
        username: str = "DC Cluster",
        avatar_url: Optional[str] = None,
    ):
        super().__init__(name)
        self.webhook_url = webhook_url
        self.username = username
        self.avatar_url = avatar_url

    async def send(self, notification: Notification) -> bool:
        """إرسال لـ Discord"""
        payload = self._build_discord_message(notification)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                json=payload,
                timeout=10.0,
            )
            return response.status_code in (200, 204)

    def _build_discord_message(self, notification: Notification) -> Dict[str, Any]:
        """بناء رسالة Discord"""
        # تحويل اللون لـ integer
        color_map = {
            NotificationPriority.LOW: 0x808080,
            NotificationPriority.NORMAL: 0x2196F3,
            NotificationPriority.HIGH: 0xFF9800,
            NotificationPriority.CRITICAL: 0xF44336,
        }
        color = color_map.get(notification.priority, 0x2196F3)

        embed = {
            "title": notification.title,
            "description": notification.message,
            "color": color,
            "timestamp": notification.timestamp.isoformat(),
            "footer": {
                "text": f"Distributed Cluster | {notification.category.value}",
            },
            "fields": [
                {"name": k, "value": str(v), "inline": True}
                for k, v in list(notification.data.items())[:6]
            ],
        }

        message = {
            "username": self.username,
            "embeds": [embed],
        }

        if self.avatar_url:
            message["avatar_url"] = self.avatar_url

        return message


@dataclass
class EmailConfig:
    """إعدادات البريد الإلكتروني"""
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_email: str
    use_tls: bool = True


class EmailChannel(NotificationChannel):
    """
    قناة البريد الإلكتروني

    ترسل إشعارات عبر SMTP
    """

    def __init__(
        self,
        name: str = "email",
        config: Optional[EmailConfig] = None,
        recipients: Optional[List[str]] = None,
    ):
        super().__init__(name)
        self.config = config
        self.recipients = recipients or []

    async def send(self, notification: Notification) -> bool:
        """إرسال بريد إلكتروني"""
        if not self.config or not self.recipients:
            return False

        # تشغيل في thread pool لأن smtplib ليس async
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._send_email_sync,
            notification,
        )

    def _send_email_sync(self, notification: Notification) -> bool:
        """إرسال البريد (synchronous)"""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = notification.title
            msg["From"] = self.config.from_email
            msg["To"] = ", ".join(self.recipients)

            # نص عادي
            text_content = f"""
{notification.title}

{notification.message}

التصنيف: {notification.category.value}
الأولوية: {notification.priority.value}
الوقت: {notification.timestamp.isoformat()}

البيانات الإضافية:
{json.dumps(notification.data, indent=2, ensure_ascii=False)}
"""

            # HTML
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; }}
        .header {{ background: {notification.color}; color: white; padding: 20px; }}
        .content {{ padding: 20px; }}
        .data {{ background: #f5f5f5; padding: 10px; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>{notification.emoji} {notification.title}</h2>
    </div>
    <div class="content">
        <p>{notification.message}</p>
        <p><strong>التصنيف:</strong> {notification.category.value}</p>
        <p><strong>الأولوية:</strong> {notification.priority.value}</p>
        <div class="data">
            <pre>{json.dumps(notification.data, indent=2, ensure_ascii=False)}</pre>
        </div>
    </div>
</body>
</html>
"""

            msg.attach(MIMEText(text_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            # إرسال
            if self.config.use_tls:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)

            server.login(self.config.username, self.config.password)
            server.sendmail(
                self.config.from_email,
                self.recipients,
                msg.as_string(),
            )
            server.quit()

            return True

        except Exception as e:
            return False


class TelegramChannel(NotificationChannel):
    """
    قناة Telegram

    ترسل إشعارات لـ Telegram Bot
    """

    def __init__(
        self,
        name: str = "telegram",
        bot_token: str = "",
        chat_id: str = "",
    ):
        super().__init__(name)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async def send(self, notification: Notification) -> bool:
        """إرسال لـ Telegram"""
        text = f"""
{notification.emoji} *{notification.title}*

{notification.message}

📂 التصنيف: `{notification.category.value}`
⚡ الأولوية: `{notification.priority.value}`
"""

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                json=payload,
                timeout=10.0,
            )
            return response.status_code == 200
