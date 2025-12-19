"""
Notification System
نظام الإشعارات
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..resources.styles import COLORS


class NotificationType(Enum):
    """Notification types"""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class NotificationConfig:
    """Notification configuration"""

    title: str
    message: str
    type: NotificationType = NotificationType.INFO
    duration: int = 5000  # ms, 0 for persistent
    action_text: Optional[str] = None
    action_callback: Optional[Callable] = None


class NotificationWidget(QFrame):
    """Individual notification widget"""

    def __init__(self, config: NotificationConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._setup_ui()
        self._setup_animation()

        if config.duration > 0:
            QTimer.singleShot(config.duration, self.dismiss)

    def _setup_ui(self):
        """Setup notification UI"""
        # Get colors based on type
        type_colors = {
            NotificationType.INFO: COLORS["info"],
            NotificationType.SUCCESS: COLORS["success"],
            NotificationType.WARNING: COLORS["warning"],
            NotificationType.ERROR: COLORS["danger"],
        }
        accent_color = type_colors.get(self._config.type, COLORS["info"])

        type_icons = {
            NotificationType.INFO: "ℹ",
            NotificationType.SUCCESS: "✓",
            NotificationType.WARNING: "⚠",
            NotificationType.ERROR: "✕",
        }
        icon = type_icons.get(self._config.type, "ℹ")

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {COLORS['bg_medium']};
                border: 1px solid {COLORS['border']};
                border-left: 4px solid {accent_color};
                border-radius: 8px;
            }}
        """
        )
        self.setFixedWidth(350)
        self.setMinimumHeight(70)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(12)

        # Icon
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(
            f"""
            font-size: 20px;
            color: {accent_color};
        """
        )
        icon_label.setFixedWidth(24)
        layout.addWidget(icon_label)

        # Content
        content_layout = QVBoxLayout()
        content_layout.setSpacing(4)

        title_label = QLabel(self._config.title)
        title_label.setStyleSheet(
            f"""
            font-weight: 600;
            font-size: 13px;
            color: {COLORS['text_primary']};
        """
        )
        content_layout.addWidget(title_label)

        message_label = QLabel(self._config.message)
        message_label.setStyleSheet(
            f"""
            font-size: 12px;
            color: {COLORS['text_secondary']};
        """
        )
        message_label.setWordWrap(True)
        content_layout.addWidget(message_label)

        # Action button if provided
        if self._config.action_text:
            action_btn = QPushButton(self._config.action_text)
            action_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: transparent;
                    color: {accent_color};
                    border: none;
                    font-size: 12px;
                    font-weight: 600;
                    text-align: left;
                    padding: 4px 0;
                }}
                QPushButton:hover {{
                    text-decoration: underline;
                }}
            """
            )
            action_btn.setCursor(Qt.PointingHandCursor)
            if self._config.action_callback:
                action_btn.clicked.connect(self._config.action_callback)
            action_btn.clicked.connect(self.dismiss)
            content_layout.addWidget(action_btn)

        layout.addLayout(content_layout)
        layout.addStretch()

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_muted']};
                border: none;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {COLORS['text_primary']};
            }}
        """
        )
        close_btn.clicked.connect(self.dismiss)
        layout.addWidget(close_btn, alignment=Qt.AlignTop)

    def _setup_animation(self):
        """Setup fade animation"""
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(200)
        self._fade_in.setStartValue(0)
        self._fade_in.setEndValue(1)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_in.start()

    def dismiss(self):
        """Dismiss notification with animation"""
        self._fade_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_out.setDuration(200)
        self._fade_out.setStartValue(1)
        self._fade_out.setEndValue(0)
        self._fade_out.setEasingCurve(QEasingCurve.InCubic)
        self._fade_out.finished.connect(self._on_dismissed)
        self._fade_out.start()

    def _on_dismissed(self):
        """Handle dismiss complete"""
        self.setParent(None)
        self.deleteLater()


class NotificationManager(QFrame):
    """Manager for displaying notifications"""

    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._notifications = []
        self._setup_ui()

    def _setup_ui(self):
        """Setup manager UI"""
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignTop | Qt.AlignRight)

    def show_notification(
        self,
        title: str,
        message: str,
        type: NotificationType = NotificationType.INFO,
        duration: int = 5000,
        action_text: Optional[str] = None,
        action_callback: Optional[Callable] = None,
    ):
        """Show a new notification"""
        config = NotificationConfig(
            title=title,
            message=message,
            type=type,
            duration=duration,
            action_text=action_text,
            action_callback=action_callback,
        )

        notification = NotificationWidget(config, self)
        self._layout.insertWidget(0, notification)
        self._notifications.append(notification)

        # Limit number of visible notifications
        while len(self._notifications) > 5:
            oldest = self._notifications.pop(0)
            oldest.dismiss()

        self.adjustSize()
        self.raise_()

    def info(self, title: str, message: str, **kwargs):
        """Show info notification"""
        self.show_notification(title, message, NotificationType.INFO, **kwargs)

    def success(self, title: str, message: str, **kwargs):
        """Show success notification"""
        self.show_notification(title, message, NotificationType.SUCCESS, **kwargs)

    def warning(self, title: str, message: str, **kwargs):
        """Show warning notification"""
        self.show_notification(title, message, NotificationType.WARNING, **kwargs)

    def error(self, title: str, message: str, **kwargs):
        """Show error notification"""
        self.show_notification(title, message, NotificationType.ERROR, **kwargs)

    def clear_all(self):
        """Clear all notifications"""
        for notification in self._notifications:
            notification.dismiss()
        self._notifications.clear()

    @classmethod
    def instance(cls, parent=None) -> "NotificationManager":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls(parent)
        return cls._instance


class ToastNotification(QLabel):
    """Simple toast notification that appears at the bottom"""

    def __init__(self, message: str, parent=None):
        super().__init__(message, parent)
        self._setup_ui()
        self._setup_animation()

        QTimer.singleShot(3000, self.dismiss)

    def _setup_ui(self):
        """Setup toast UI"""
        self.setStyleSheet(
            f"""
            background-color: {COLORS['bg_medium']};
            color: {COLORS['text_primary']};
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 13px;
        """
        )
        self.setAlignment(Qt.AlignCenter)
        self.adjustSize()

    def _setup_animation(self):
        """Setup animations"""
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(150)
        self._fade_in.setStartValue(0)
        self._fade_in.setEndValue(1)
        self._fade_in.start()

    def dismiss(self):
        """Dismiss with animation"""
        self._fade_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_out.setDuration(150)
        self._fade_out.setStartValue(1)
        self._fade_out.setEndValue(0)
        self._fade_out.finished.connect(self.deleteLater)
        self._fade_out.start()
