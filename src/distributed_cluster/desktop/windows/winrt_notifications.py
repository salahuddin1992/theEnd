"""
WinRT Notifications - إشعارات Windows الأصلية
==============================================

Windows Runtime Notifications Manager
-------------------------------------

This module provides native Windows 10/11 toast notifications
using the Windows Runtime (WinRT) APIs.

يوفر هذا الملف إشعارات Windows الأصلية باستخدام WinRT:
- Toast Notifications مع أزرار
- Progress Notifications
- Notification History
- Action Center integration

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Check for Windows
import platform

IS_WINDOWS = platform.system() == "Windows"


class NotificationType(str, Enum):
    """نوع الإشعار / Notification type"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    PROGRESS = "progress"


class NotificationPriority(str, Enum):
    """أولوية الإشعار / Notification priority"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class NotificationAction:
    """
    إجراء الإشعار
    Notification action button
    """
    action_id: str
    label: str
    icon: Optional[str] = None
    arguments: dict[str, str] = field(default_factory=dict)


@dataclass
class NotificationProgress:
    """
    بيانات تقدم الإشعار
    Notification progress data
    """
    title: str = ""
    status: str = ""
    value: float = 0.0  # 0.0 to 1.0
    value_string: str = ""


@dataclass
class Notification:
    """
    إشعار كامل
    Complete notification
    """
    notification_id: str
    title: str
    message: str
    notification_type: NotificationType = NotificationType.INFO
    priority: NotificationPriority = NotificationPriority.NORMAL

    # Content
    app_logo: Optional[str] = None
    hero_image: Optional[str] = None
    inline_image: Optional[str] = None

    # Actions
    actions: list[NotificationAction] = field(default_factory=list)

    # Progress (for progress notifications)
    progress: Optional[NotificationProgress] = None

    # Timing
    expiration_time: Optional[datetime] = None
    suppress_popup: bool = False

    # Metadata
    group: str = "distributed-cluster"
    tag: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Callbacks
    on_activated: Optional[Callable[[str], None]] = None
    on_dismissed: Optional[Callable[[], None]] = None


class WinRTNotificationManager:
    """
    مدير إشعارات WinRT
    WinRT Notification Manager

    يوفر واجهة لإرسال إشعارات Windows الأصلية
    باستخدام WinRT APIs.

    Provides interface for sending native Windows
    notifications using WinRT APIs.
    """

    # Application ID for notifications
    APP_ID = "DistributedCluster.Desktop"

    def __init__(
        self,
        app_id: Optional[str] = None,
        icon_path: Optional[str] = None,
    ):
        """
        تهيئة مدير الإشعارات

        Args:
            app_id: معرف التطبيق
            icon_path: مسار أيقونة التطبيق
        """
        self.app_id = app_id or self.APP_ID
        self.icon_path = icon_path

        # Notification tracking
        self._notifications: dict[str, Notification] = {}
        self._action_callbacks: dict[str, Callable] = {}

        # WinRT components
        self._notifier = None
        self._initialized = False

        # Event handlers
        self._on_notification_activated: Optional[Callable] = None
        self._on_notification_dismissed: Optional[Callable] = None

    async def initialize(self) -> bool:
        """
        تهيئة نظام الإشعارات
        Initialize notification system
        """
        if not IS_WINDOWS:
            logger.warning("WinRT notifications are only available on Windows")
            return False

        try:
            # Try to import WinRT
            from winsdk.windows.ui.notifications import (
                ToastNotification,  # noqa: F401
                ToastNotificationManager,
            )

            # Create notifier
            self._notifier = ToastNotificationManager.create_toast_notifier(
                self.app_id
            )

            self._initialized = True
            logger.info("WinRT notification manager initialized")
            return True

        except ImportError:
            logger.warning(
                "winsdk not installed. Install with: pip install winsdk"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to initialize WinRT notifications: {e}")
            return False

    async def show_notification(
        self,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        actions: Optional[list[NotificationAction]] = None,
        progress: Optional[NotificationProgress] = None,
        icon: Optional[str] = None,
        tag: Optional[str] = None,
        on_activated: Optional[Callable[[str], None]] = None,
    ) -> Optional[str]:
        """
        عرض إشعار
        Show notification

        Args:
            title: عنوان الإشعار
            message: نص الإشعار
            notification_type: نوع الإشعار
            actions: أزرار الإجراءات
            progress: بيانات التقدم
            icon: أيقونة مخصصة
            tag: وسم للتحديث لاحقاً
            on_activated: callback عند التفعيل

        Returns:
            معرف الإشعار أو None
        """
        notification_id = str(uuid4())

        notification = Notification(
            notification_id=notification_id,
            title=title,
            message=message,
            notification_type=notification_type,
            actions=actions or [],
            progress=progress,
            app_logo=icon or self.icon_path,
            tag=tag or notification_id,
            on_activated=on_activated,
        )

        return await self._send_notification(notification)

    async def _send_notification(
        self,
        notification: Notification,
    ) -> Optional[str]:
        """
        إرسال إشعار
        Send notification
        """
        if not IS_WINDOWS:
            # Fallback for non-Windows
            logger.info(f"[Notification] {notification.title}: {notification.message}")
            return notification.notification_id

        if not self._initialized:
            await self.initialize()

        if not self._notifier:
            return self._send_fallback_notification(notification)

        try:
            from winsdk.windows.data.xml.dom import XmlDocument
            from winsdk.windows.ui.notifications import ToastNotification

            # Build XML
            xml_content = self._build_notification_xml(notification)

            # Create notification
            doc = XmlDocument()
            doc.load_xml(xml_content)

            toast = ToastNotification(doc)
            toast.tag = notification.tag
            toast.group = notification.group

            # Set event handlers
            if notification.on_activated:
                self._action_callbacks[notification.notification_id] = (
                    notification.on_activated
                )

            # Show notification
            self._notifier.show(toast)

            # Track notification
            self._notifications[notification.notification_id] = notification

            logger.debug(f"Sent notification: {notification.notification_id}")
            return notification.notification_id

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return self._send_fallback_notification(notification)

    def _build_notification_xml(self, notification: Notification) -> str:
        """
        بناء XML الإشعار
        Build notification XML
        """
        # Determine template based on content
        if notification.progress:
            return self._build_progress_xml(notification)
        elif notification.actions:
            return self._build_action_xml(notification)
        else:
            return self._build_simple_xml(notification)

    def _build_simple_xml(self, notification: Notification) -> str:
        """بناء XML إشعار بسيط"""
        icon_xml = ""
        if notification.app_logo:
            icon_xml = f'<image placement="appLogoOverride" src="{notification.app_logo}" hint-crop="circle"/>'

        hero_xml = ""
        if notification.hero_image:
            hero_xml = f'<image placement="hero" src="{notification.hero_image}"/>'

        return f"""
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>{self._escape_xml(notification.title)}</text>
            <text>{self._escape_xml(notification.message)}</text>
            {icon_xml}
            {hero_xml}
        </binding>
    </visual>
    <audio src="ms-winsoundevent:Notification.Default"/>
</toast>
"""

    def _build_action_xml(self, notification: Notification) -> str:
        """بناء XML إشعار مع أزرار"""
        actions_xml = ""
        for action in notification.actions:
            args = "&".join(
                f"{k}={v}" for k, v in action.arguments.items()
            )
            actions_xml += f"""
            <action
                content="{self._escape_xml(action.label)}"
                arguments="{action.action_id}?{args}"
                activationType="foreground"/>
"""

        icon_xml = ""
        if notification.app_logo:
            icon_xml = f'<image placement="appLogoOverride" src="{notification.app_logo}" hint-crop="circle"/>'

        return f"""
<toast launch="notification_id={notification.notification_id}">
    <visual>
        <binding template="ToastGeneric">
            <text>{self._escape_xml(notification.title)}</text>
            <text>{self._escape_xml(notification.message)}</text>
            {icon_xml}
        </binding>
    </visual>
    <actions>
        {actions_xml}
    </actions>
    <audio src="ms-winsoundevent:Notification.Default"/>
</toast>
"""

    def _build_progress_xml(self, notification: Notification) -> str:
        """بناء XML إشعار مع شريط تقدم"""
        progress = notification.progress
        if not progress:
            return self._build_simple_xml(notification)

        return f"""
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>{self._escape_xml(notification.title)}</text>
            <progress
                title="{self._escape_xml(progress.title)}"
                value="{progress.value}"
                valueStringOverride="{self._escape_xml(progress.value_string)}"
                status="{self._escape_xml(progress.status)}"/>
        </binding>
    </visual>
</toast>
"""

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape XML special characters"""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;")
        )

    def _send_fallback_notification(
        self,
        notification: Notification,
    ) -> Optional[str]:
        """
        إرسال إشعار بديل (عبر win10toast أو plyer)
        Send fallback notification
        """
        try:
            # Try win10toast
            from win10toast import ToastNotifier

            toaster = ToastNotifier()
            toaster.show_toast(
                notification.title,
                notification.message,
                icon_path=notification.app_logo,
                duration=5,
                threaded=True,
            )

            self._notifications[notification.notification_id] = notification
            return notification.notification_id

        except ImportError:
            pass

        try:
            # Try plyer
            from plyer import notification as plyer_notify

            plyer_notify.notify(
                title=notification.title,
                message=notification.message,
                app_icon=notification.app_logo,
                timeout=5,
            )

            self._notifications[notification.notification_id] = notification
            return notification.notification_id

        except ImportError:
            pass

        # Console fallback
        logger.info(f"[NOTIFICATION] {notification.title}: {notification.message}")
        return notification.notification_id

    async def update_progress(
        self,
        notification_id: str,
        progress: NotificationProgress,
    ) -> bool:
        """
        تحديث شريط التقدم
        Update progress bar

        Args:
            notification_id: معرف الإشعار
            progress: بيانات التقدم الجديدة

        Returns:
            True إذا تم التحديث بنجاح
        """
        if notification_id not in self._notifications:
            return False

        notification = self._notifications[notification_id]
        notification.progress = progress

        # Re-send notification with updated progress
        if self._notifier and IS_WINDOWS:
            try:
                await self._send_notification(notification)
                return True
            except Exception as e:
                logger.error(f"Failed to update progress: {e}")
                return False

        return True

    async def hide_notification(self, notification_id: str) -> bool:
        """
        إخفاء إشعار
        Hide notification
        """
        if notification_id not in self._notifications:
            return False

        notification = self._notifications.pop(notification_id)

        if self._notifier and IS_WINDOWS:
            try:
                from winsdk.windows.ui.notifications import ToastNotificationManager

                history = ToastNotificationManager.history
                history.remove(notification.tag, notification.group, self.app_id)
                return True

            except Exception as e:
                logger.error(f"Failed to hide notification: {e}")
                return False

        return True

    async def clear_all(self) -> bool:
        """
        مسح جميع الإشعارات
        Clear all notifications
        """
        self._notifications.clear()

        if self._notifier and IS_WINDOWS:
            try:
                from winsdk.windows.ui.notifications import ToastNotificationManager

                history = ToastNotificationManager.history
                history.clear(self.app_id)
                return True

            except Exception as e:
                logger.error(f"Failed to clear notifications: {e}")
                return False

        return True

    # =========================================================================
    # Convenience Methods / طرق مساعدة
    # =========================================================================

    async def show_info(
        self,
        title: str,
        message: str,
        **kwargs: Any,
    ) -> Optional[str]:
        """عرض إشعار معلومات"""
        return await self.show_notification(
            title=title,
            message=message,
            notification_type=NotificationType.INFO,
            **kwargs,
        )

    async def show_success(
        self,
        title: str,
        message: str,
        **kwargs: Any,
    ) -> Optional[str]:
        """عرض إشعار نجاح"""
        return await self.show_notification(
            title=title,
            message=message,
            notification_type=NotificationType.SUCCESS,
            **kwargs,
        )

    async def show_warning(
        self,
        title: str,
        message: str,
        **kwargs: Any,
    ) -> Optional[str]:
        """عرض إشعار تحذير"""
        return await self.show_notification(
            title=title,
            message=message,
            notification_type=NotificationType.WARNING,
            **kwargs,
        )

    async def show_error(
        self,
        title: str,
        message: str,
        **kwargs: Any,
    ) -> Optional[str]:
        """عرض إشعار خطأ"""
        return await self.show_notification(
            title=title,
            message=message,
            notification_type=NotificationType.ERROR,
            **kwargs,
        )

    async def show_job_progress(
        self,
        job_id: str,
        job_name: str,
        progress: float,
        status: str = "Processing...",
    ) -> Optional[str]:
        """
        عرض إشعار تقدم المهمة
        Show job progress notification
        """
        return await self.show_notification(
            title=f"Job: {job_name}",
            message=f"Progress: {int(progress * 100)}%",
            notification_type=NotificationType.PROGRESS,
            progress=NotificationProgress(
                title=job_name,
                status=status,
                value=progress,
                value_string=f"{int(progress * 100)}%",
            ),
            tag=f"job-{job_id}",
        )

    async def show_worker_alert(
        self,
        worker_id: str,
        alert_type: str,
        message: str,
    ) -> Optional[str]:
        """
        عرض تنبيه العامل
        Show worker alert notification
        """
        notification_type = NotificationType.WARNING
        if alert_type in ("error", "failure", "disconnected"):
            notification_type = NotificationType.ERROR
        elif alert_type in ("connected", "ready"):
            notification_type = NotificationType.SUCCESS

        return await self.show_notification(
            title=f"Worker Alert: {worker_id}",
            message=message,
            notification_type=notification_type,
            actions=[
                NotificationAction(
                    action_id="view_worker",
                    label="View Details",
                    arguments={"worker_id": worker_id},
                ),
            ],
        )

    async def show_cluster_status(
        self,
        total_workers: int,
        active_jobs: int,
        status: str,
    ) -> Optional[str]:
        """
        عرض حالة الكلاستر
        Show cluster status notification
        """
        notification_type = NotificationType.INFO
        if status == "degraded":
            notification_type = NotificationType.WARNING
        elif status == "offline":
            notification_type = NotificationType.ERROR
        elif status == "healthy":
            notification_type = NotificationType.SUCCESS

        return await self.show_notification(
            title="Cluster Status",
            message=f"Workers: {total_workers} | Jobs: {active_jobs} | Status: {status}",
            notification_type=notification_type,
            tag="cluster-status",
        )


# Factory function
def create_notification_manager(
    app_id: Optional[str] = None,
    icon_path: Optional[str] = None,
) -> WinRTNotificationManager:
    """
    إنشاء مدير إشعارات
    Create notification manager
    """
    return WinRTNotificationManager(
        app_id=app_id,
        icon_path=icon_path,
    )
