"""
Enhanced System Tray - شريط النظام المحسّن
==========================================

Windows 11 Enhanced System Tray with:
- Quick Actions menu
- Live status updates
- Job progress indicators
- Rich tooltip information
- Notification badges

شريط النظام المحسّن لويندوز 11 مع:
- قائمة إجراءات سريعة
- تحديثات حية للحالة
- مؤشرات تقدم المهام
- معلومات تلميحات غنية
- شارات الإشعارات

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)


class TrayStatus(str, Enum):
    """Tray status states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    BUSY = "busy"


@dataclass
class QuickAction:
    """Quick action definition"""
    id: str
    name: str
    icon: str = ""
    description: str = ""
    callback: Optional[Callable] = None
    enabled: bool = True
    visible: bool = True
    shortcut: str = ""


@dataclass
class ClusterStatus:
    """Cluster status information"""
    connected: bool = False
    server_name: str = ""
    running_jobs: int = 0
    pending_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    active_workers: int = 0
    total_workers: int = 0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    gpu_usage: float = 0.0
    uptime_seconds: int = 0
    last_update: datetime = field(default_factory=datetime.now)


# Fluent Design Colors
FLUENT_COLORS = {
    "bg_dark": "#1f1f1f",
    "bg_medium": "#2d2d2d",
    "bg_light": "#3d3d3d",
    "accent": "#0078d4",
    "accent_light": "#60cdff",
    "text_primary": "#ffffff",
    "text_secondary": "#b3b3b3",
    "success": "#6ccb5f",
    "warning": "#f7c948",
    "error": "#ff453a",
    "border": "#404040",
}


class StatusWidget(QFrame):
    """
    Rich status widget for tray menu
    ويدجت الحالة الغنية لقائمة شريط النظام
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self._setup_ui()
        self._status = ClusterStatus()

    def _setup_ui(self):
        """Setup the status widget UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header with status indicator
        header = QHBoxLayout()

        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet(f"color: {FLUENT_COLORS['error']}; font-size: 14px;")
        header.addWidget(self.status_indicator)

        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet(f"color: {FLUENT_COLORS['text_primary']}; font-weight: bold; font-size: 14px;")
        header.addWidget(self.status_label)

        header.addStretch()

        self.server_label = QLabel("")
        self.server_label.setStyleSheet(f"color: {FLUENT_COLORS['text_secondary']}; font-size: 12px;")
        header.addWidget(self.server_label)

        layout.addLayout(header)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"background-color: {FLUENT_COLORS['border']};")
        layout.addWidget(separator)

        # Stats grid
        stats_layout = QHBoxLayout()

        # Jobs column
        jobs_layout = QVBoxLayout()
        jobs_layout.setSpacing(4)

        self.running_label = self._create_stat_label("Running", "0")
        self.pending_label = self._create_stat_label("Pending", "0")
        self.completed_label = self._create_stat_label("Completed", "0")

        jobs_layout.addWidget(self.running_label)
        jobs_layout.addWidget(self.pending_label)
        jobs_layout.addWidget(self.completed_label)

        stats_layout.addLayout(jobs_layout)

        # Separator
        v_sep = QFrame()
        v_sep.setFrameShape(QFrame.VLine)
        v_sep.setStyleSheet(f"background-color: {FLUENT_COLORS['border']};")
        stats_layout.addWidget(v_sep)

        # Resources column
        resources_layout = QVBoxLayout()
        resources_layout.setSpacing(4)

        self.workers_label = self._create_stat_label("Workers", "0/0")
        self.cpu_label = self._create_stat_label("CPU", "0%")
        self.memory_label = self._create_stat_label("Memory", "0%")

        resources_layout.addWidget(self.workers_label)
        resources_layout.addWidget(self.cpu_label)
        resources_layout.addWidget(self.memory_label)

        stats_layout.addLayout(resources_layout)

        layout.addLayout(stats_layout)

        # Progress bar for active jobs
        self.job_progress = QProgressBar()
        self.job_progress.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 4px;
                background-color: {FLUENT_COLORS['bg_light']};
                height: 8px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {FLUENT_COLORS['accent']};
                border-radius: 4px;
            }}
        """)
        self.job_progress.setTextVisible(False)
        self.job_progress.setMaximum(100)
        self.job_progress.setValue(0)
        self.job_progress.setVisible(False)
        layout.addWidget(self.job_progress)

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {FLUENT_COLORS['bg_medium']};
                border-radius: 8px;
            }}
        """)

    def _create_stat_label(self, title: str, value: str) -> QWidget:
        """Create a stat label widget"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {FLUENT_COLORS['text_secondary']}; font-size: 11px;")
        layout.addWidget(title_lbl)

        layout.addStretch()

        value_lbl = QLabel(value)
        value_lbl.setObjectName("value")
        value_lbl.setStyleSheet(f"color: {FLUENT_COLORS['text_primary']}; font-size: 11px; font-weight: bold;")
        layout.addWidget(value_lbl)

        return widget

    def update_status(self, status: ClusterStatus):
        """Update the status display"""
        self._status = status

        # Update connection status
        if status.connected:
            self.status_indicator.setStyleSheet(f"color: {FLUENT_COLORS['success']}; font-size: 14px;")
            self.status_label.setText("Connected")
            self.server_label.setText(status.server_name)
        else:
            self.status_indicator.setStyleSheet(f"color: {FLUENT_COLORS['error']}; font-size: 14px;")
            self.status_label.setText("Disconnected")
            self.server_label.setText("")

        # Update stats
        self.running_label.findChild(QLabel, "value").setText(str(status.running_jobs))
        self.pending_label.findChild(QLabel, "value").setText(str(status.pending_jobs))
        self.completed_label.findChild(QLabel, "value").setText(str(status.completed_jobs))

        self.workers_label.findChild(QLabel, "value").setText(
            f"{status.active_workers}/{status.total_workers}"
        )
        self.cpu_label.findChild(QLabel, "value").setText(f"{status.cpu_usage:.0f}%")
        self.memory_label.findChild(QLabel, "value").setText(f"{status.memory_usage:.0f}%")

        # Update progress
        if status.running_jobs > 0:
            self.job_progress.setVisible(True)
            # Calculate approximate progress
            total = status.running_jobs + status.pending_jobs + status.completed_jobs
            if total > 0:
                progress = int((status.completed_jobs / total) * 100)
                self.job_progress.setValue(progress)
        else:
            self.job_progress.setVisible(False)


class QuickActionsWidget(QFrame):
    """
    Quick actions panel
    لوحة الإجراءات السريعة
    """

    action_triggered = Signal(str)

    def __init__(self, actions: List[QuickAction], parent=None):
        super().__init__(parent)
        self._actions = actions
        self._buttons: Dict[str, QPushButton] = {}
        self._setup_ui()

    def _setup_ui(self):
        """Setup the quick actions UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        for action in self._actions:
            if not action.visible:
                continue

            btn = QPushButton(action.name)
            btn.setEnabled(action.enabled)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {FLUENT_COLORS['text_primary']};
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    text-align: left;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {FLUENT_COLORS['bg_light']};
                }}
                QPushButton:pressed {{
                    background-color: {FLUENT_COLORS['accent']};
                }}
                QPushButton:disabled {{
                    color: {FLUENT_COLORS['text_secondary']};
                }}
            """)

            if action.callback:
                btn.clicked.connect(action.callback)
            else:
                btn.clicked.connect(lambda checked, a=action: self.action_triggered.emit(a.id))

            layout.addWidget(btn)
            self._buttons[action.id] = btn

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {FLUENT_COLORS['bg_medium']};
                border-radius: 8px;
            }}
        """)

    def update_action(self, action_id: str, enabled: bool = None, visible: bool = None):
        """Update action state"""
        if action_id in self._buttons:
            btn = self._buttons[action_id]
            if enabled is not None:
                btn.setEnabled(enabled)
            if visible is not None:
                btn.setVisible(visible)


class EnhancedSystemTray(QObject):
    """
    Enhanced Windows 11 System Tray
    شريط النظام المحسّن لويندوز 11
    """

    # Signals
    show_window = Signal()
    hide_window = Signal()
    quit_requested = Signal()
    action_triggered = Signal(str)
    connect_requested = Signal()
    disconnect_requested = Signal()

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        self._status = TrayStatus.DISCONNECTED
        self._cluster_status = ClusterStatus()

        # Create tray icon
        self._tray = QSystemTrayIcon(parent)
        self._menu = QMenu()

        # Quick actions
        self._quick_actions: List[QuickAction] = [
            QuickAction("submit_job", "Submit New Job", description="Submit a new job to the cluster"),
            QuickAction("refresh", "Refresh Status", description="Refresh cluster status"),
            QuickAction("view_logs", "View Logs", description="Open log viewer"),
            QuickAction("settings", "Settings", description="Open settings"),
        ]

        self._setup_menu()
        self._setup_icon()
        self._setup_signals()

        # Auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh_timer)
        self._refresh_timer.start(5000)  # 5 seconds

    def _setup_icon(self):
        """Setup tray icon"""
        self._tray.setIcon(self._create_icon())
        self._update_tooltip()

    def _create_icon(self) -> QIcon:
        """Create tray icon with status indicator"""
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        status_colors = {
            TrayStatus.DISCONNECTED: FLUENT_COLORS["text_secondary"],
            TrayStatus.CONNECTING: FLUENT_COLORS["warning"],
            TrayStatus.CONNECTED: FLUENT_COLORS["accent"],
            TrayStatus.ERROR: FLUENT_COLORS["error"],
            TrayStatus.BUSY: FLUENT_COLORS["accent_light"],
        }

        bg_color = QColor(status_colors.get(self._status, FLUENT_COLORS["text_secondary"]))
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, size - 8, size - 8, 12, 12)

        # Icon symbol (simplified cluster icon)
        painter.setBrush(QColor(255, 255, 255))

        # Center node
        center = size // 2
        node_size = 10
        painter.drawEllipse(center - node_size // 2, center - node_size // 2, node_size, node_size)

        # Surrounding nodes
        offset = 14
        small_size = 6
        positions = [
            (center - offset, center - offset),
            (center + offset, center - offset),
            (center - offset, center + offset),
            (center + offset, center + offset),
        ]

        for x, y in positions:
            painter.drawEllipse(x - small_size // 2, y - small_size // 2, small_size, small_size)

        # Notification badge
        if self._cluster_status.running_jobs > 0:
            badge_color = FLUENT_COLORS["warning"]
            painter.setBrush(QColor(badge_color))
            painter.drawEllipse(size - 20, 4, 16, 16)

            # Badge text
            painter.setPen(QColor(FLUENT_COLORS["bg_dark"]))
            font = QFont("Segoe UI", 8, QFont.Bold)
            painter.setFont(font)
            count = str(min(self._cluster_status.running_jobs, 99))
            painter.drawText(size - 20, 4, 16, 16, Qt.AlignCenter, count)

        painter.end()
        return QIcon(pixmap)

    def _setup_menu(self):
        """Setup context menu"""
        self._menu.setStyleSheet(f"""
            QMenu {{
                background-color: {FLUENT_COLORS['bg_medium']};
                border: 1px solid {FLUENT_COLORS['border']};
                border-radius: 8px;
                padding: 8px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
                color: {FLUENT_COLORS['text_primary']};
            }}
            QMenu::item:selected {{
                background-color: {FLUENT_COLORS['accent']};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {FLUENT_COLORS['border']};
                margin: 4px 8px;
            }}
        """)

        # Status widget
        self._status_widget = StatusWidget()
        status_action = QWidgetAction(self._menu)
        status_action.setDefaultWidget(self._status_widget)
        self._menu.addAction(status_action)

        self._menu.addSeparator()

        # Quick actions widget
        self._quick_widget = QuickActionsWidget(self._quick_actions)
        self._quick_widget.action_triggered.connect(self.action_triggered.emit)
        quick_action = QWidgetAction(self._menu)
        quick_action.setDefaultWidget(self._quick_widget)
        self._menu.addAction(quick_action)

        self._menu.addSeparator()

        # Connection actions
        self._connect_action = QAction("Connect...", self._menu)
        self._connect_action.triggered.connect(self.connect_requested.emit)
        self._menu.addAction(self._connect_action)

        self._disconnect_action = QAction("Disconnect", self._menu)
        self._disconnect_action.triggered.connect(self.disconnect_requested.emit)
        self._disconnect_action.setEnabled(False)
        self._menu.addAction(self._disconnect_action)

        self._menu.addSeparator()

        # Show/Hide window
        show_action = QAction("Show Window", self._menu)
        show_action.triggered.connect(self.show_window.emit)
        self._menu.addAction(show_action)

        self._menu.addSeparator()

        # Quit
        quit_action = QAction("Quit", self._menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(quit_action)

        self._tray.setContextMenu(self._menu)

    def _setup_signals(self):
        """Setup signal connections"""
        self._tray.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """Handle tray activation"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window.emit()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.action_triggered.emit("refresh")

    def _on_refresh_timer(self):
        """Handle refresh timer"""
        self._update_tooltip()

    def _update_tooltip(self):
        """Update tray tooltip"""
        status = self._cluster_status

        if status.connected:
            tooltip = f"NebulaCompute - Connected to {status.server_name}\n"
            tooltip += f"Jobs: {status.running_jobs} running, {status.pending_jobs} pending\n"
            tooltip += f"Workers: {status.active_workers}/{status.total_workers}"
        else:
            tooltip = "NebulaCompute - Disconnected"

        self._tray.setToolTip(tooltip)

    def show(self):
        """Show tray icon"""
        self._tray.show()

    def hide(self):
        """Hide tray icon"""
        self._tray.hide()

    def set_status(self, status: TrayStatus):
        """Set tray status"""
        self._status = status
        self._tray.setIcon(self._create_icon())

        self._connect_action.setEnabled(status == TrayStatus.DISCONNECTED)
        self._disconnect_action.setEnabled(status == TrayStatus.CONNECTED)

    def update_cluster_status(self, status: ClusterStatus):
        """Update cluster status"""
        self._cluster_status = status
        self._status_widget.update_status(status)
        self._tray.setIcon(self._create_icon())
        self._update_tooltip()

        if status.connected:
            self.set_status(TrayStatus.CONNECTED)
        else:
            self.set_status(TrayStatus.DISCONNECTED)

    def show_notification(
        self,
        title: str,
        message: str,
        icon_type: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
        timeout: int = 5000,
    ):
        """Show balloon notification"""
        self._tray.showMessage(title, message, icon_type, timeout)

    def notify_job_completed(self, job_id: str, job_name: str = ""):
        """Notify job completion"""
        name = job_name or job_id
        self.show_notification(
            "Job Completed",
            f"Job '{name}' has finished successfully",
            QSystemTrayIcon.MessageIcon.Information,
        )

    def notify_job_failed(self, job_id: str, job_name: str = "", error: str = ""):
        """Notify job failure"""
        name = job_name or job_id
        message = f"Job '{name}' has failed"
        if error:
            message += f"\n{error}"
        self.show_notification(
            "Job Failed",
            message,
            QSystemTrayIcon.MessageIcon.Warning,
        )

    def add_quick_action(self, action: QuickAction):
        """Add a quick action"""
        self._quick_actions.append(action)
        # Recreate quick actions widget
        self._setup_menu()

    def get_status(self) -> Dict[str, Any]:
        """Get tray status"""
        return {
            "status": self._status.value,
            "visible": self._tray.isVisible(),
            "cluster_connected": self._cluster_status.connected,
        }
