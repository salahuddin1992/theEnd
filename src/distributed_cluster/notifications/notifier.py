"""
Notifier - نظام الإشعارات الرئيسي
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field


class NotificationPriority(str, Enum):
    """أولوية الإشعار"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationCategory(str, Enum):
    """تصنيف الإشعار"""
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    JOB_TIMEOUT = "job_timeout"
    WORKER_ONLINE = "worker_online"
    WORKER_OFFLINE = "worker_offline"
    WORKER_ERROR = "worker_error"
    CLUSTER_ALERT = "cluster_alert"
    SYSTEM = "system"


@dataclass
class Notification:
    """إشعار"""
    title: str
    message: str
    category: NotificationCategory
    priority: NotificationPriority = NotificationPriority.NORMAL
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    notification_id: str = ""

    def __post_init__(self):
        if not self.notification_id:
            import uuid
            self.notification_id = str(uuid.uuid4())[:12]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "title": self.title,
            "message": self.message,
            "category": self.category.value,
            "priority": self.priority.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }

    @property
    def emoji(self) -> str:
        """إيموجي حسب التصنيف"""
        emojis = {
            NotificationCategory.JOB_COMPLETED: "✅",
            NotificationCategory.JOB_FAILED: "❌",
            NotificationCategory.JOB_TIMEOUT: "⏰",
            NotificationCategory.WORKER_ONLINE: "🟢",
            NotificationCategory.WORKER_OFFLINE: "🔴",
            NotificationCategory.WORKER_ERROR: "⚠️",
            NotificationCategory.CLUSTER_ALERT: "🚨",
            NotificationCategory.SYSTEM: "ℹ️",
        }
        return emojis.get(self.category, "📢")

    @property
    def color(self) -> str:
        """لون حسب الأولوية (للـ Discord/Slack)"""
        colors = {
            NotificationPriority.LOW: "#808080",
            NotificationPriority.NORMAL: "#0099ff",
            NotificationPriority.HIGH: "#ff9900",
            NotificationPriority.CRITICAL: "#ff0000",
        }
        return colors.get(self.priority, "#0099ff")


class NotificationChannel(ABC):
    """قناة إشعارات (Abstract Base)"""

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.sent_count = 0
        self.error_count = 0

    @abstractmethod
    async def send(self, notification: Notification) -> bool:
        """إرسال إشعار"""
        pass

    async def safe_send(self, notification: Notification) -> bool:
        """إرسال مع معالجة الأخطاء"""
        if not self.enabled:
            return False

        try:
            result = await self.send(notification)
            if result:
                self.sent_count += 1
            return result
        except Exception as e:
            self.error_count += 1
            return False

    def stats(self) -> Dict[str, Any]:
        """إحصائيات القناة"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "sent_count": self.sent_count,
            "error_count": self.error_count,
        }


class Notifier:
    """
    مدير الإشعارات الرئيسي

    يدير قنوات متعددة ويوزع الإشعارات عليها
    """

    def __init__(self):
        self.channels: Dict[str, NotificationChannel] = {}
        self.history: List[Notification] = []
        self.max_history = 1000
        self._filters: List[Callable[[Notification], bool]] = []
        self._running = False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    def add_channel(self, channel: NotificationChannel) -> None:
        """إضافة قناة إشعارات"""
        self.channels[channel.name] = channel

    def remove_channel(self, name: str) -> None:
        """إزالة قناة"""
        if name in self.channels:
            del self.channels[name]

    def add_filter(self, filter_func: Callable[[Notification], bool]) -> None:
        """
        إضافة فلتر للإشعارات

        الفلتر يعيد True للسماح بالإشعار، False لمنعه
        """
        self._filters.append(filter_func)

    async def start(self) -> None:
        """بدء معالج الإشعارات"""
        self._running = True
        self._task = asyncio.create_task(self._process_queue())

    async def stop(self) -> None:
        """إيقاف المعالج"""
        self._running = False
        if self._task:
            self._task.cancel()

    async def notify(self, notification: Notification) -> None:
        """إرسال إشعار (يضاف للطابور)"""
        await self._queue.put(notification)

    async def notify_immediate(self, notification: Notification) -> Dict[str, bool]:
        """إرسال إشعار فوري (بدون طابور)"""
        return await self._send_to_channels(notification)

    async def _process_queue(self) -> None:
        """معالجة طابور الإشعارات"""
        while self._running:
            try:
                notification = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0,
                )
                await self._send_to_channels(notification)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _send_to_channels(self, notification: Notification) -> Dict[str, bool]:
        """إرسال إشعار لجميع القنوات"""
        # تطبيق الفلاتر
        for filter_func in self._filters:
            if not filter_func(notification):
                return {}

        # حفظ في السجل
        self.history.append(notification)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        # إرسال للقنوات
        results = {}
        tasks = []

        for name, channel in self.channels.items():
            tasks.append((name, channel.safe_send(notification)))

        for name, task in tasks:
            results[name] = await task

        return results

    # Factory methods للإشعارات الشائعة
    async def job_completed(
        self,
        job_id: str,
        job_name: str,
        duration: float,
        **extra_data,
    ) -> None:
        """إشعار إكمال مهمة"""
        notification = Notification(
            title=f"✅ اكتملت المهمة: {job_name}",
            message=f"المهمة {job_id} اكتملت بنجاح في {duration:.1f} ثانية",
            category=NotificationCategory.JOB_COMPLETED,
            priority=NotificationPriority.NORMAL,
            data={"job_id": job_id, "job_name": job_name, "duration": duration, **extra_data},
        )
        await self.notify(notification)

    async def job_failed(
        self,
        job_id: str,
        job_name: str,
        error: str,
        **extra_data,
    ) -> None:
        """إشعار فشل مهمة"""
        notification = Notification(
            title=f"❌ فشلت المهمة: {job_name}",
            message=f"المهمة {job_id} فشلت: {error}",
            category=NotificationCategory.JOB_FAILED,
            priority=NotificationPriority.HIGH,
            data={"job_id": job_id, "job_name": job_name, "error": error, **extra_data},
        )
        await self.notify(notification)

    async def job_timeout(
        self,
        job_id: str,
        job_name: str,
        timeout_seconds: int,
        **extra_data,
    ) -> None:
        """إشعار انتهاء وقت مهمة"""
        notification = Notification(
            title=f"⏰ انتهى وقت المهمة: {job_name}",
            message=f"المهمة {job_id} تجاوزت الحد الأقصى ({timeout_seconds} ثانية)",
            category=NotificationCategory.JOB_TIMEOUT,
            priority=NotificationPriority.HIGH,
            data={"job_id": job_id, "job_name": job_name, "timeout": timeout_seconds, **extra_data},
        )
        await self.notify(notification)

    async def worker_online(self, worker_id: str, hostname: str, **extra_data) -> None:
        """إشعار اتصال عامل"""
        notification = Notification(
            title=f"🟢 عامل جديد: {hostname}",
            message=f"العامل {worker_id} اتصل بالكلاستر",
            category=NotificationCategory.WORKER_ONLINE,
            priority=NotificationPriority.LOW,
            data={"worker_id": worker_id, "hostname": hostname, **extra_data},
        )
        await self.notify(notification)

    async def worker_offline(self, worker_id: str, hostname: str, **extra_data) -> None:
        """إشعار انقطاع عامل"""
        notification = Notification(
            title=f"🔴 انقطع العامل: {hostname}",
            message=f"العامل {worker_id} انقطع عن الكلاستر",
            category=NotificationCategory.WORKER_OFFLINE,
            priority=NotificationPriority.HIGH,
            data={"worker_id": worker_id, "hostname": hostname, **extra_data},
        )
        await self.notify(notification)

    async def cluster_alert(
        self,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.HIGH,
        **extra_data,
    ) -> None:
        """تنبيه عام للكلاستر"""
        notification = Notification(
            title=f"🚨 {title}",
            message=message,
            category=NotificationCategory.CLUSTER_ALERT,
            priority=priority,
            data=extra_data,
        )
        await self.notify(notification)

    def get_history(
        self,
        category: Optional[NotificationCategory] = None,
        limit: int = 50,
    ) -> List[Notification]:
        """الحصول على سجل الإشعارات"""
        history = self.history
        if category:
            history = [n for n in history if n.category == category]
        return history[-limit:]

    def stats(self) -> Dict[str, Any]:
        """إحصائيات النظام"""
        return {
            "channels": {name: ch.stats() for name, ch in self.channels.items()},
            "history_size": len(self.history),
            "queue_size": self._queue.qsize(),
            "running": self._running,
        }
