"""
Windows 11 Notification Center
مركز الإشعارات بنمط Windows 11

Features:
- Toast notifications with animations
- Notification center panel
- Action buttons
- Auto-dismiss
- Stacked notifications
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List

from PySide6.QtCore import QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .animations import FluentEasing
from .fluent_design import FluentDesignSystem
from .titlebar import FluentIcons

# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION TYPES
# أنواع الإشعارات
# ═══════════════════════════════════════════════════════════════════════════════

class NotificationType(Enum):
    """Notification severity types"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class NotificationAction:
    """Action button for notification"""
    label: str
    callback: Callable[[], None]
    primary: bool = False


@dataclass
class Notification:
    """Notification data"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    message: str = ""
    type: NotificationType = NotificationType.INFO
    icon: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    duration: int = 5000  # Auto-dismiss in ms (0 = no auto-dismiss)
    actions: List[NotificationAction] = field(default_factory=list)
    dismissible: bool = True
    read: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# TOAST NOTIFICATION
# إشعار Toast
# ═══════════════════════════════════════════════════════════════════════════════

class Toast(QFrame):
    """
    Single toast notification widget.
    عنصر إشعار Toast واحد
    """

    dismissed = Signal(str)  # Emits notification ID
    action_clicked = Signal(str, int)  # Emits notification ID and action index

    def __init__(self, notification: Notification, parent=None):
        super().__init__(parent)

        self._notification = notification
        self._opacity = 0.0
        self._slide_offset = 0

        self._setup_ui()
        self._setup_animation()

    def _setup_ui(self):
        """Setup toast UI"""
        colors = FluentDesignSystem().colors

        self.setObjectName("toast")
        self.setFixedWidth(360)
        self.setMinimumHeight(80)

        # Type-specific styles
        type_styles = {
            NotificationType.INFO: (colors.info, FluentIcons.INFO),
            NotificationType.SUCCESS: (colors.success, FluentIcons.CHECKMARK),
            NotificationType.WARNING: (colors.warning, FluentIcons.WARNING),
            NotificationType.ERROR: (colors.error, FluentIcons.ERROR),
        }

        accent_color, default_icon = type_styles[self._notification.type]
        icon = self._notification.icon or default_icon

        self.setStyleSheet(f"""
            #toast {{
                background-color: {colors.bg_solid_secondary};
                border: 1px solid {colors.stroke_surface};
                border-left: 3px solid {accent_color};
                border-radius: 8px;
            }}
        """)

        # Shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        # Layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 12, 12)
        main_layout.setSpacing(12)

        # Icon
        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(f"""
            QLabel {{
                font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets';
                font-size: 16px;
                color: {accent_color};
            }}
        """)
        icon_label.setText(icon)
        main_layout.addWidget(icon_label, 0, Qt.AlignTop)

        # Content
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)

        # Title
        if self._notification.title:
            title_label = QLabel(self._notification.title)
            title_label.setStyleSheet(f"""
                QLabel {{
                    color: {colors.text_primary};
                    font-size: 14px;
                    font-weight: 600;
                }}
            """)
            title_label.setWordWrap(True)
            content_layout.addWidget(title_label)

        # Message
        if self._notification.message:
            message_label = QLabel(self._notification.message)
            message_label.setStyleSheet(f"""
                QLabel {{
                    color: {colors.text_secondary};
                    font-size: 13px;
                }}
            """)
            message_label.setWordWrap(True)
            content_layout.addWidget(message_label)

        # Actions
        if self._notification.actions:
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(0, 8, 0, 0)
            actions_layout.setSpacing(8)

            for i, action in enumerate(self._notification.actions):
                btn = QPushButton(action.label)
                btn.setCursor(Qt.PointingHandCursor)

                if action.primary:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {colors.accent};
                            color: #FFFFFF;
                            border: none;
                            border-radius: 4px;
                            padding: 6px 12px;
                            font-size: 12px;
                            font-weight: 500;
                        }}
                        QPushButton:hover {{
                            background-color: {colors.accent_light_1};
                        }}
                    """)
                else:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {colors.fill_control};
                            color: {colors.text_primary};
                            border: 1px solid {colors.stroke_control};
                            border-radius: 4px;
                            padding: 6px 12px;
                            font-size: 12px;
                        }}
                        QPushButton:hover {{
                            background-color: {colors.fill_control_secondary};
                        }}
                    """)

                btn.clicked.connect(lambda checked, idx=i: self._on_action_clicked(idx))
                actions_layout.addWidget(btn)

            actions_layout.addStretch()
            content_layout.addLayout(actions_layout)

        main_layout.addLayout(content_layout, 1)

        # Close button
        if self._notification.dismissible:
            close_btn = QPushButton()
            close_btn.setFixedSize(24, 24)
            close_btn.setCursor(Qt.PointingHandCursor)
            close_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    border-radius: 4px;
                    font-family: 'Segoe Fluent Icons';
                    font-size: 10px;
                    color: {colors.text_secondary};
                }}
                QPushButton:hover {{
                    background-color: {colors.fill_subtle};
                    color: {colors.text_primary};
                }}
            """)
            close_btn.setText(FluentIcons.CANCEL)
            close_btn.clicked.connect(self.dismiss)
            main_layout.addWidget(close_btn, 0, Qt.AlignTop)

    def _setup_animation(self):
        """Setup enter/exit animations"""
        # Opacity effect
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0)
        # Don't apply to self to avoid conflict with shadow

        # Enter animation
        self._enter_anim = QPropertyAnimation(self, b"pos")
        self._enter_anim.setDuration(FluentEasing.DURATION_NORMAL)
        self._enter_anim.setEasingCurve(FluentEasing.ease_out_cubic())

    def show_animated(self, start_pos: QPoint, end_pos: QPoint):
        """Show with slide-in animation"""
        self.move(start_pos)
        self.show()

        self._enter_anim.setStartValue(start_pos)
        self._enter_anim.setEndValue(end_pos)
        self._enter_anim.start()

        # Auto-dismiss timer
        if self._notification.duration > 0:
            QTimer.singleShot(self._notification.duration, self.dismiss)

    def dismiss(self):
        """Dismiss with animation"""
        # Exit animation
        exit_anim = QPropertyAnimation(self, b"pos")
        exit_anim.setDuration(FluentEasing.DURATION_FAST)
        exit_anim.setEasingCurve(FluentEasing.ease_in_expo())
        exit_anim.setStartValue(self.pos())
        exit_anim.setEndValue(QPoint(self.pos().x() + 400, self.pos().y()))
        exit_anim.finished.connect(lambda: self.dismissed.emit(self._notification.id))
        exit_anim.start()

    def _on_action_clicked(self, index: int):
        """Handle action button click"""
        if index < len(self._notification.actions):
            action = self._notification.actions[index]
            action.callback()
        self.action_clicked.emit(self._notification.id, index)
        self.dismiss()

    @property
    def notification_id(self) -> str:
        return self._notification.id


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION CENTER
# مركز الإشعارات
# ═══════════════════════════════════════════════════════════════════════════════

class NotificationCenter(QWidget):
    """
    Manages toast notifications display.
    يدير عرض إشعارات Toast
    """

    notification_clicked = Signal(str)

    MAX_VISIBLE_TOASTS = 5
    TOAST_SPACING = 12
    TOAST_MARGIN = 16

    def __init__(self, parent=None):
        super().__init__(parent)

        self._notifications: Dict[str, Notification] = {}
        self._toasts: Dict[str, Toast] = {}
        self._toast_queue: List[Notification] = []

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._setup_ui()

    def _setup_ui(self):
        """Setup notification center UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.TOAST_SPACING)
        layout.addStretch()

    def _get_screen_position(self) -> QPoint:
        """Get position for notifications (bottom-right of screen)"""
        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            return QPoint(
                geometry.right() - 360 - self.TOAST_MARGIN,
                geometry.bottom() - self.TOAST_MARGIN
            )
        return QPoint(0, 0)

    def _calculate_toast_position(self, index: int) -> QPoint:
        """Calculate position for toast at given index"""
        base = self._get_screen_position()

        # Calculate offset based on existing toasts
        offset_y = 0
        for i, toast in enumerate(list(self._toasts.values())[:index]):
            offset_y += toast.height() + self.TOAST_SPACING

        return QPoint(base.x(), base.y() - 80 - offset_y)

    def show_notification(self, notification: Notification):
        """Show a notification"""
        self._notifications[notification.id] = notification

        if len(self._toasts) >= self.MAX_VISIBLE_TOASTS:
            self._toast_queue.append(notification)
            return

        self._show_toast(notification)

    def _show_toast(self, notification: Notification):
        """Display a toast notification"""
        toast = Toast(notification)
        toast.dismissed.connect(self._on_toast_dismissed)

        self._toasts[notification.id] = toast

        # Calculate position
        index = len(self._toasts) - 1
        end_pos = self._calculate_toast_position(index)
        start_pos = QPoint(end_pos.x() + 400, end_pos.y())

        toast.show_animated(start_pos, end_pos)

    def _on_toast_dismissed(self, notification_id: str):
        """Handle toast dismissal"""
        if notification_id in self._toasts:
            toast = self._toasts.pop(notification_id)
            toast.deleteLater()

        # Reposition remaining toasts
        self._reposition_toasts()

        # Show queued notification if any
        if self._toast_queue:
            next_notification = self._toast_queue.pop(0)
            QTimer.singleShot(100, lambda: self._show_toast(next_notification))

    def _reposition_toasts(self):
        """Reposition all visible toasts"""
        for i, toast in enumerate(self._toasts.values()):
            target_pos = self._calculate_toast_position(i)

            anim = QPropertyAnimation(toast, b"pos")
            anim.setDuration(FluentEasing.DURATION_FAST)
            anim.setEasingCurve(FluentEasing.ease_out_cubic())
            anim.setEndValue(target_pos)
            anim.start()

    # Convenience methods
    def info(self, title: str, message: str = "", duration: int = 5000,
             actions: List[NotificationAction] = None):
        """Show info notification"""
        notification = Notification(
            title=title,
            message=message,
            type=NotificationType.INFO,
            duration=duration,
            actions=actions or []
        )
        self.show_notification(notification)

    def success(self, title: str, message: str = "", duration: int = 5000,
                actions: List[NotificationAction] = None):
        """Show success notification"""
        notification = Notification(
            title=title,
            message=message,
            type=NotificationType.SUCCESS,
            duration=duration,
            actions=actions or []
        )
        self.show_notification(notification)

    def warning(self, title: str, message: str = "", duration: int = 7000,
                actions: List[NotificationAction] = None):
        """Show warning notification"""
        notification = Notification(
            title=title,
            message=message,
            type=NotificationType.WARNING,
            duration=duration,
            actions=actions or []
        )
        self.show_notification(notification)

    def error(self, title: str, message: str = "", duration: int = 0,
              actions: List[NotificationAction] = None):
        """Show error notification (no auto-dismiss by default)"""
        notification = Notification(
            title=title,
            message=message,
            type=NotificationType.ERROR,
            duration=duration,
            actions=actions or []
        )
        self.show_notification(notification)

    def dismiss_all(self):
        """Dismiss all notifications"""
        for toast in list(self._toasts.values()):
            toast.dismiss()

    def clear_queue(self):
        """Clear notification queue"""
        self._toast_queue.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# IN-APP NOTIFICATION MANAGER
# مدير الإشعارات داخل التطبيق
# ═══════════════════════════════════════════════════════════════════════════════

class InAppNotificationManager(QWidget):
    """
    In-app notification manager that positions notifications within a parent widget.
    مدير الإشعارات داخل التطبيق
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)

        self._notifications: Dict[str, Notification] = {}
        self._toasts: Dict[str, Toast] = {}

        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        # Position in top-right of parent
        self._margin = 16
        self._spacing = 12

        # Don't intercept parent events
        self.lower()

    def resizeEvent(self, event):
        """Handle parent resize"""
        self._reposition_toasts()
        super().resizeEvent(event)

    def _calculate_toast_position(self, index: int) -> QPoint:
        """Calculate position for toast"""
        parent_rect = self.parent().rect()

        offset_y = self._margin
        for i, toast in enumerate(list(self._toasts.values())[:index]):
            offset_y += toast.height() + self._spacing

        return QPoint(
            parent_rect.width() - 360 - self._margin,
            offset_y
        )

    def show_notification(self, notification: Notification):
        """Show notification"""
        self._notifications[notification.id] = notification

        toast = Toast(notification, self.parent())
        toast.dismissed.connect(self._on_dismissed)
        self._toasts[notification.id] = toast

        index = len(self._toasts) - 1
        end_pos = self._calculate_toast_position(index)
        start_pos = QPoint(end_pos.x() + 400, end_pos.y())

        toast.show_animated(start_pos, end_pos)

    def _on_dismissed(self, notification_id: str):
        """Handle dismissal"""
        if notification_id in self._toasts:
            toast = self._toasts.pop(notification_id)
            toast.deleteLater()

        self._reposition_toasts()

    def _reposition_toasts(self):
        """Reposition toasts"""
        for i, toast in enumerate(self._toasts.values()):
            target = self._calculate_toast_position(i)

            anim = QPropertyAnimation(toast, b"pos")
            anim.setDuration(FluentEasing.DURATION_FAST)
            anim.setEasingCurve(FluentEasing.ease_out_cubic())
            anim.setEndValue(target)
            anim.start()

    # Convenience methods
    def info(self, title: str, message: str = ""):
        self.show_notification(Notification(
            title=title, message=message, type=NotificationType.INFO
        ))

    def success(self, title: str, message: str = ""):
        self.show_notification(Notification(
            title=title, message=message, type=NotificationType.SUCCESS
        ))

    def warning(self, title: str, message: str = ""):
        self.show_notification(Notification(
            title=title, message=message, type=NotificationType.WARNING, duration=7000
        ))

    def error(self, title: str, message: str = ""):
        self.show_notification(Notification(
            title=title, message=message, type=NotificationType.ERROR, duration=0
        ))
