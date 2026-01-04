"""
Chat Bot - بوت المحادثة التفاعلي
================================

بوت تفاعلي لـ Slack و Discord للتحكم بالكلاستر:
- استقبال الأوامر والرد عليها
- عرض حالة الكلاستر
- تنفيذ العمليات (إلغاء مهمة، عرض Workers، إلخ)
- تنبيهات تفاعلية مع أزرار
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


class CommandType(str, Enum):
    """أنواع الأوامر."""
    STATUS = "status"
    JOBS = "jobs"
    WORKERS = "workers"
    CANCEL = "cancel"
    SUBMIT = "submit"
    LOGS = "logs"
    HELP = "help"
    STATS = "stats"
    ALERTS = "alerts"
    CONFIG = "config"


@dataclass
class BotCommand:
    """أمر بوت."""
    command_type: CommandType
    args: List[str] = field(default_factory=list)
    kwargs: Dict[str, str] = field(default_factory=dict)
    raw_text: str = ""
    user_id: Optional[str] = None
    channel_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BotResponse:
    """رد البوت."""
    text: str
    blocks: Optional[List[Dict[str, Any]]] = None  # Slack blocks / Discord embeds
    attachments: Optional[List[Dict[str, Any]]] = None
    ephemeral: bool = False  # Visible only to user
    thread_ts: Optional[str] = None  # Reply in thread


@dataclass
class InteractiveAction:
    """إجراء تفاعلي (زر، قائمة، إلخ)."""
    action_id: str
    action_type: str  # button, select, etc.
    value: str
    user_id: str
    channel_id: str
    message_ts: Optional[str] = None


# =============================================================================
# Command Parser
# =============================================================================


class CommandParser:
    """محلل الأوامر."""

    # Command patterns
    PATTERNS = {
        CommandType.STATUS: [r"^status$", r"^حالة$", r"^cluster status$"],
        CommandType.JOBS: [r"^jobs?(?:\s+(.*))?$", r"^مهام?(?:\s+(.*))?$", r"^list jobs?$"],
        CommandType.WORKERS: [r"^workers?$", r"^عمال$", r"^nodes?$"],
        CommandType.CANCEL: [r"^cancel\s+(\S+)$", r"^إلغاء\s+(\S+)$", r"^stop\s+(\S+)$"],
        CommandType.SUBMIT: [r"^submit\s+(.+)$", r"^run\s+(.+)$", r"^تنفيذ\s+(.+)$"],
        CommandType.LOGS: [r"^logs?\s+(\S+)$", r"^سجلات?\s+(\S+)$"],
        CommandType.HELP: [r"^help$", r"^مساعدة$", r"^\?$"],
        CommandType.STATS: [r"^stats?$", r"^إحصائيات$", r"^metrics?$"],
        CommandType.ALERTS: [r"^alerts?$", r"^تنبيهات$"],
        CommandType.CONFIG: [r"^config(?:\s+(.*))?$", r"^إعدادات(?:\s+(.*))?$"],
    }

    def parse(self, text: str) -> Optional[BotCommand]:
        """تحليل نص الأمر."""
        text = text.strip().lower()

        # Remove bot mention if present
        text = re.sub(r"^<@\w+>\s*", "", text)

        for cmd_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                match = re.match(pattern, text, re.IGNORECASE)
                if match:
                    args = [g for g in match.groups() if g] if match.groups() else []
                    return BotCommand(
                        command_type=cmd_type,
                        args=args,
                        raw_text=text,
                    )

        return None


# =============================================================================
# Bot Handler Base
# =============================================================================


class BotHandler(ABC):
    """معالج أوامر البوت الأساسي."""

    def __init__(self, master_url: str = "http://localhost:8765"):
        self.master_url = master_url
        self.parser = CommandParser()
        self._command_handlers: Dict[CommandType, Callable] = {
            CommandType.STATUS: self._handle_status,
            CommandType.JOBS: self._handle_jobs,
            CommandType.WORKERS: self._handle_workers,
            CommandType.CANCEL: self._handle_cancel,
            CommandType.SUBMIT: self._handle_submit,
            CommandType.LOGS: self._handle_logs,
            CommandType.HELP: self._handle_help,
            CommandType.STATS: self._handle_stats,
            CommandType.ALERTS: self._handle_alerts,
            CommandType.CONFIG: self._handle_config,
        }

    async def _api_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """طلب API للـ master."""
        if not HTTPX_AVAILABLE:
            return None

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                url = f"{self.master_url}{endpoint}"
                resp = await client.request(method, url, **kwargs)
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None

    async def handle_message(self, text: str, user_id: str, channel_id: str) -> Optional[BotResponse]:
        """معالجة رسالة واردة."""
        command = self.parser.parse(text)
        if not command:
            return None

        command.user_id = user_id
        command.channel_id = channel_id

        handler = self._command_handlers.get(command.command_type)
        if handler:
            return await handler(command)

        return BotResponse(text="Unknown command. Type `help` for available commands.")

    @abstractmethod
    async def handle_interaction(self, action: InteractiveAction) -> Optional[BotResponse]:
        """معالجة إجراء تفاعلي."""
        pass

    # Command handlers
    async def _handle_status(self, cmd: BotCommand) -> BotResponse:
        """عرض حالة الكلاستر."""
        data = await self._api_request("GET", "/stats")

        if not data:
            return BotResponse(text="⚠️ Could not fetch cluster status")

        text = f"""
🖥️ *Cluster Status*

*Workers:* {data.get('active_workers', 0)} / {data.get('total_workers', 0)}
*CPU:* {data.get('available_cpu_cores', 0):.1f} / {data.get('total_cpu_cores', 0):.1f} cores
*Memory:* {data.get('available_memory_gb', 0):.1f} / {data.get('total_memory_gb', 0):.1f} GB
*GPUs:* {data.get('available_gpus', 0)} / {data.get('total_gpus', 0)}

*Jobs:*
  ⏳ Pending: {data.get('pending_jobs', 0)}
  🔄 Running: {data.get('running_jobs', 0)}
  ✅ Completed: {data.get('completed_jobs', 0)}
  ❌ Failed: {data.get('failed_jobs', 0)}
        """.strip()

        return BotResponse(text=text)

    async def _handle_jobs(self, cmd: BotCommand) -> BotResponse:
        """عرض قائمة المهام."""
        params = {"limit": 10}
        if cmd.args:
            params["status"] = cmd.args[0]

        data = await self._api_request("GET", "/jobs", params=params)

        if not data:
            return BotResponse(text="⚠️ Could not fetch jobs")

        jobs = data.get("jobs", [])
        if not jobs:
            return BotResponse(text="📭 No jobs found")

        lines = ["📋 *Recent Jobs*\n"]
        status_emoji = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫",
        }

        for job in jobs[:10]:
            emoji = status_emoji.get(job.get("status", ""), "❓")
            name = job.get("name", job.get("job_id", "?"))[:30]
            lines.append(f"{emoji} `{job.get('job_id', '?')[:12]}` - {name}")

        return BotResponse(text="\n".join(lines))

    async def _handle_workers(self, cmd: BotCommand) -> BotResponse:
        """عرض قائمة Workers."""
        data = await self._api_request("GET", "/workers")

        if not data:
            return BotResponse(text="⚠️ Could not fetch workers")

        workers = data.get("workers", [])
        if not workers:
            return BotResponse(text="📭 No workers registered")

        lines = ["👷 *Workers*\n"]
        status_emoji = {
            "ready": "🟢",
            "busy": "🟡",
            "offline": "🔴",
            "draining": "🟠",
        }

        for w in workers:
            emoji = status_emoji.get(w.get("status", ""), "⚪")
            hostname = w.get("hostname", "unknown")[:20]
            total = w.get("total_resources", {})
            lines.append(
                f"{emoji} `{w.get('worker_id', '?')[:12]}` - {hostname} "
                f"({total.get('cpu_cores', 0)} CPU, {total.get('memory_mb', 0)//1024}GB)"
            )

        return BotResponse(text="\n".join(lines))

    async def _handle_cancel(self, cmd: BotCommand) -> BotResponse:
        """إلغاء مهمة."""
        if not cmd.args:
            return BotResponse(text="❌ Usage: `cancel <job_id>`")

        job_id = cmd.args[0]
        result = await self._api_request("DELETE", f"/jobs/{job_id}")

        if result is not None:
            return BotResponse(text=f"✅ Job `{job_id}` cancelled successfully")
        else:
            return BotResponse(text=f"❌ Failed to cancel job `{job_id}`")

    async def _handle_submit(self, cmd: BotCommand) -> BotResponse:
        """تقديم مهمة جديدة."""
        if not cmd.args:
            return BotResponse(text="❌ Usage: `submit <command>`")

        command = " ".join(cmd.args)
        job_data = {
            "command": command,
            "name": f"bot-{datetime.utcnow().strftime('%H%M%S')}",
        }

        result = await self._api_request("POST", "/jobs", json=job_data)

        if result:
            job_id = result.get("job_id", "unknown")
            return BotResponse(text=f"✅ Job submitted: `{job_id}`")
        else:
            return BotResponse(text="❌ Failed to submit job")

    async def _handle_logs(self, cmd: BotCommand) -> BotResponse:
        """عرض سجلات مهمة."""
        if not cmd.args:
            return BotResponse(text="❌ Usage: `logs <job_id>`")

        job_id = cmd.args[0]
        data = await self._api_request("GET", f"/jobs/{job_id}")

        if not data:
            return BotResponse(text=f"❌ Job `{job_id}` not found")

        result = data.get("result", {})
        stdout = result.get("stdout", "")[:1000]
        stderr = result.get("stderr", "")[:500]

        text = f"📜 *Logs for* `{job_id}`\n\n"
        if stdout:
            text += f"*stdout:*\n```{stdout}```\n"
        if stderr:
            text += f"*stderr:*\n```{stderr}```\n"
        if not stdout and not stderr:
            text += "_No logs available yet_"

        return BotResponse(text=text)

    async def _handle_help(self, cmd: BotCommand) -> BotResponse:
        """عرض المساعدة."""
        text = """
🤖 *NebulaCompute Bot Commands*

*Cluster:*
  `status` - Show cluster status
  `workers` - List all workers
  `stats` - Show statistics

*Jobs:*
  `jobs` - List recent jobs
  `jobs <status>` - Filter by status
  `submit <command>` - Submit new job
  `cancel <job_id>` - Cancel a job
  `logs <job_id>` - View job logs

*Other:*
  `alerts` - Show active alerts
  `config` - Show configuration
  `help` - Show this help

*Arabic commands also supported:*
  `حالة` `مهام` `عمال` `إلغاء` `مساعدة`
        """.strip()

        return BotResponse(text=text)

    async def _handle_stats(self, cmd: BotCommand) -> BotResponse:
        """عرض إحصائيات."""
        data = await self._api_request("GET", "/stats")

        if not data:
            return BotResponse(text="⚠️ Could not fetch stats")

        text = f"""
📊 *Cluster Statistics*

*Resource Utilization:*
  CPU: {100 - (data.get('available_cpu_cores', 0) / max(data.get('total_cpu_cores', 1), 1) * 100):.1f}%
  Memory: {100 - (data.get('available_memory_gb', 0) / max(data.get('total_memory_gb', 1), 1) * 100):.1f}%
  GPU: {100 - (data.get('available_gpus', 0) / max(data.get('total_gpus', 1), 1) * 100):.1f}%

*Job Statistics:*
  Total Jobs: {
    data.get('completed_jobs', 0) + data.get('failed_jobs', 0) +
    data.get('running_jobs', 0) + data.get('pending_jobs', 0)
}
  Success Rate: {
    data.get('completed_jobs', 0) /
    max(data.get('completed_jobs', 0) + data.get('failed_jobs', 0), 1) * 100:.1f
}%
        """.strip()

        return BotResponse(text=text)

    async def _handle_alerts(self, cmd: BotCommand) -> BotResponse:
        """عرض التنبيهات النشطة."""
        # This would connect to an alerts system
        return BotResponse(text="🔔 *Active Alerts*\n\n_No active alerts_")

    async def _handle_config(self, cmd: BotCommand) -> BotResponse:
        """عرض الإعدادات."""
        data = await self._api_request("GET", "/config")

        if not data:
            return BotResponse(text="⚠️ Could not fetch config")

        text = f"⚙️ *Configuration*\n\n```{json.dumps(data, indent=2)[:500]}```"
        return BotResponse(text=text)


# =============================================================================
# Slack Bot
# =============================================================================


class SlackBot(BotHandler):
    """
    بوت Slack.

    الاستخدام:
        bot = SlackBot(
            bot_token="xoxb-...",
            signing_secret="...",
            master_url="http://localhost:8765",
        )

        # معالجة حدث
        response = await bot.handle_event(event_data)
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        signing_secret: Optional[str] = None,
        master_url: str = "http://localhost:8765",
    ):
        super().__init__(master_url)
        self.bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
        self.signing_secret = signing_secret or os.environ.get("SLACK_SIGNING_SECRET")

    def verify_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
        """التحقق من توقيع Slack."""
        if not self.signing_secret:
            return True  # Skip if no secret configured

        if abs(time.time() - float(timestamp)) > 60 * 5:
            return False  # Request too old

        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        my_signature = "v0=" + hmac.new(
            self.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(my_signature, signature)

    async def handle_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """معالجة حدث Slack."""
        event_type = event_data.get("type")

        # URL verification challenge
        if event_type == "url_verification":
            return {"challenge": event_data.get("challenge")}

        # Event callback
        if event_type == "event_callback":
            event = event_data.get("event", {})
            return await self._process_event(event)

        return None

    async def _process_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """معالجة حدث داخلي."""
        event_type = event.get("type")

        if event_type == "app_mention" or event_type == "message":
            # Ignore bot's own messages
            if event.get("bot_id"):
                return None

            text = event.get("text", "")
            user_id = event.get("user")
            channel_id = event.get("channel")

            response = await self.handle_message(text, user_id, channel_id)

            if response:
                await self._send_message(channel_id, response, thread_ts=event.get("thread_ts"))

        return None

    async def _send_message(
        self,
        channel: str,
        response: BotResponse,
        thread_ts: Optional[str] = None,
    ) -> bool:
        """إرسال رسالة إلى Slack."""
        if not HTTPX_AVAILABLE or not self.bot_token:
            logger.warning("Cannot send Slack message: missing httpx or token")
            return False

        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "channel": channel,
                    "text": response.text,
                }

                if response.blocks:
                    payload["blocks"] = response.blocks
                if thread_ts or response.thread_ts:
                    payload["thread_ts"] = thread_ts or response.thread_ts

                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    json=payload,
                )

                result = resp.json()
                return result.get("ok", False)

        except Exception as e:
            logger.error(f"Failed to send Slack message: {e}")
            return False

    async def handle_interaction(self, action: InteractiveAction) -> Optional[BotResponse]:
        """معالجة إجراء تفاعلي من Slack."""
        action_id = action.action_id

        if action_id.startswith("cancel_job_"):
            job_id = action_id.replace("cancel_job_", "")
            result = await self._api_request("DELETE", f"/jobs/{job_id}")
            if result is not None:
                return BotResponse(text=f"✅ Job `{job_id}` cancelled")
            return BotResponse(text=f"❌ Failed to cancel job `{job_id}`")

        return None

    def create_job_message(self, job: Dict[str, Any], include_actions: bool = True) -> Dict[str, Any]:
        """إنشاء رسالة مهمة مع أزرار."""
        job_id = job.get("job_id", "unknown")
        status = job.get("status", "unknown")
        name = job.get("name", job_id)

        status_emoji = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
        }

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{status_emoji.get(status, '❓')} *Job:* `{job_id}`\n*Name:* {name}\n*Status:* {status}",
                },
            },
        ]

        if include_actions and status in ("pending", "running"):
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Cancel"},
                        "style": "danger",
                        "action_id": f"cancel_job_{job_id}",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Logs"},
                        "action_id": f"view_logs_{job_id}",
                    },
                ],
            })

        return {"blocks": blocks}


# =============================================================================
# Discord Bot
# =============================================================================


class DiscordBot(BotHandler):
    """
    بوت Discord.

    الاستخدام:
        bot = DiscordBot(
            bot_token="...",
            application_id="...",
            master_url="http://localhost:8765",
        )

        # معالجة تفاعل
        response = await bot.handle_interaction_webhook(interaction_data)
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        application_id: Optional[str] = None,
        public_key: Optional[str] = None,
        master_url: str = "http://localhost:8765",
    ):
        super().__init__(master_url)
        self.bot_token = bot_token or os.environ.get("DISCORD_BOT_TOKEN")
        self.application_id = application_id or os.environ.get("DISCORD_APPLICATION_ID")
        self.public_key = public_key or os.environ.get("DISCORD_PUBLIC_KEY")

    def verify_signature(self, body: bytes, signature: str, timestamp: str) -> bool:
        """التحقق من توقيع Discord."""
        if not self.public_key:
            return True

        try:
            from nacl.signing import VerifyKey

            verify_key = VerifyKey(bytes.fromhex(self.public_key))
            message = timestamp.encode() + body
            verify_key.verify(message, bytes.fromhex(signature))
            return True
        except Exception:
            return False

    async def handle_interaction_webhook(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        """معالجة تفاعل Discord webhook."""
        interaction_type = interaction.get("type")

        # Ping
        if interaction_type == 1:
            return {"type": 1}  # PONG

        # Application command
        if interaction_type == 2:
            return await self._handle_command(interaction)

        # Message component
        if interaction_type == 3:
            return await self._handle_component(interaction)

        return {"type": 4, "data": {"content": "Unknown interaction"}}

    async def _handle_command(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        """معالجة أمر slash."""
        data = interaction.get("data", {})
        command_name = data.get("name", "")
        options = {opt["name"]: opt.get("value") for opt in data.get("options", [])}

        user_id = interaction.get("member", {}).get("user", {}).get("id")
        channel_id = interaction.get("channel_id")

        # Map slash commands to our commands
        command_map = {
            "status": "status",
            "jobs": f"jobs {options.get('status', '')}".strip(),
            "workers": "workers",
            "cancel": f"cancel {options.get('job_id', '')}",
            "submit": f"submit {options.get('command', '')}",
            "logs": f"logs {options.get('job_id', '')}",
            "stats": "stats",
            "help": "help",
        }

        text = command_map.get(command_name, "help")
        response = await self.handle_message(text, user_id, channel_id)

        if response:
            return {
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": {
                    "content": response.text,
                    "embeds": response.blocks or [],
                },
            }

        return {"type": 4, "data": {"content": "Command executed"}}

    async def _handle_component(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        """معالجة تفاعل component."""
        data = interaction.get("data", {})
        custom_id = data.get("custom_id", "")
        user_id = interaction.get("member", {}).get("user", {}).get("id")
        channel_id = interaction.get("channel_id")

        action = InteractiveAction(
            action_id=custom_id,
            action_type="button",
            value=data.get("values", [""])[0] if data.get("values") else "",
            user_id=user_id,
            channel_id=channel_id,
        )

        response = await self.handle_interaction(action)

        if response:
            return {
                "type": 4,
                "data": {"content": response.text},
            }

        return {"type": 6}  # DEFERRED_UPDATE_MESSAGE

    async def handle_interaction(self, action: InteractiveAction) -> Optional[BotResponse]:
        """معالجة إجراء تفاعلي."""
        action_id = action.action_id

        if action_id.startswith("cancel_"):
            job_id = action_id.replace("cancel_", "")
            result = await self._api_request("DELETE", f"/jobs/{job_id}")
            if result is not None:
                return BotResponse(text=f"✅ Job `{job_id}` cancelled")
            return BotResponse(text=f"❌ Failed to cancel job `{job_id}`")

        return None

    async def send_message(self, channel_id: str, response: BotResponse) -> bool:
        """إرسال رسالة إلى Discord."""
        if not HTTPX_AVAILABLE or not self.bot_token:
            return False

        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "content": response.text,
                }

                if response.blocks:
                    payload["embeds"] = response.blocks

                resp = await client.post(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    headers={"Authorization": f"Bot {self.bot_token}"},
                    json=payload,
                )

                return resp.status_code == 200

        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False

    def create_job_embed(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """إنشاء embed لمهمة."""
        job_id = job.get("job_id", "unknown")
        status = job.get("status", "unknown")
        name = job.get("name", job_id)

        color_map = {
            "pending": 0x3498DB,  # Blue
            "running": 0xF1C40F,  # Yellow
            "completed": 0x2ECC71,  # Green
            "failed": 0xE74C3C,  # Red
        }

        return {
            "title": f"Job: {name}",
            "description": f"ID: `{job_id}`",
            "color": color_map.get(status, 0x95A5A6),
            "fields": [
                {"name": "Status", "value": status.upper(), "inline": True},
                {"name": "Worker", "value": job.get("assigned_worker", "N/A"), "inline": True},
            ],
            "footer": {"text": "NebulaCompute"},
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_slash_commands(self) -> List[Dict[str, Any]]:
        """الحصول على قائمة أوامر slash للتسجيل."""
        return [
            {
                "name": "status",
                "description": "Show cluster status",
            },
            {
                "name": "jobs",
                "description": "List jobs",
                "options": [
                    {
                        "name": "status",
                        "description": "Filter by status",
                        "type": 3,  # STRING
                        "required": False,
                        "choices": [
                            {"name": "Pending", "value": "pending"},
                            {"name": "Running", "value": "running"},
                            {"name": "Completed", "value": "completed"},
                            {"name": "Failed", "value": "failed"},
                        ],
                    },
                ],
            },
            {
                "name": "workers",
                "description": "List workers",
            },
            {
                "name": "cancel",
                "description": "Cancel a job",
                "options": [
                    {
                        "name": "job_id",
                        "description": "Job ID to cancel",
                        "type": 3,
                        "required": True,
                    },
                ],
            },
            {
                "name": "submit",
                "description": "Submit a new job",
                "options": [
                    {
                        "name": "command",
                        "description": "Command to execute",
                        "type": 3,
                        "required": True,
                    },
                ],
            },
            {
                "name": "logs",
                "description": "View job logs",
                "options": [
                    {
                        "name": "job_id",
                        "description": "Job ID",
                        "type": 3,
                        "required": True,
                    },
                ],
            },
            {
                "name": "stats",
                "description": "Show statistics",
            },
            {
                "name": "help",
                "description": "Show help",
            },
        ]

    async def register_commands(self) -> bool:
        """تسجيل أوامر slash في Discord."""
        if not HTTPX_AVAILABLE or not self.bot_token or not self.application_id:
            return False

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.put(
                    f"https://discord.com/api/v10/applications/{self.application_id}/commands",
                    headers={"Authorization": f"Bot {self.bot_token}"},
                    json=self.get_slash_commands(),
                )

                if resp.status_code == 200:
                    logger.info("Discord slash commands registered successfully")
                    return True
                else:
                    logger.error(f"Failed to register commands: {resp.text}")
                    return False

        except Exception as e:
            logger.error(f"Failed to register Discord commands: {e}")
            return False


# =============================================================================
# Factory
# =============================================================================


def create_slack_bot(
    bot_token: Optional[str] = None,
    signing_secret: Optional[str] = None,
    master_url: str = "http://localhost:8765",
) -> SlackBot:
    """إنشاء بوت Slack."""
    return SlackBot(
        bot_token=bot_token,
        signing_secret=signing_secret,
        master_url=master_url,
    )


def create_discord_bot(
    bot_token: Optional[str] = None,
    application_id: Optional[str] = None,
    public_key: Optional[str] = None,
    master_url: str = "http://localhost:8765",
) -> DiscordBot:
    """إنشاء بوت Discord."""
    return DiscordBot(
        bot_token=bot_token,
        application_id=application_id,
        public_key=public_key,
        master_url=master_url,
    )
