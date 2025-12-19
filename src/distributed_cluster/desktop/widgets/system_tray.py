"""
System Tray Icon
أيقونة شريط النظام
"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..resources.styles import COLORS


class SystemTrayIcon(QSystemTrayIcon):
    """System tray icon with context menu"""

    show_window_requested = Signal()
    hide_window_requested = Signal()
    quit_requested = Signal()
    connect_requested = Signal()
    disconnect_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._running_jobs = 0
        self._pending_jobs = 0

        self._setup_icon()
        self._setup_menu()
        self._connect_signals()

    def _setup_icon(self):
        """Setup tray icon"""
        self.setIcon(self._create_icon())
        self.setToolTip("NebulaCompute Desktop\nDisconnected")

    def _create_icon(self, connected: bool = False, has_activity: bool = False) -> QIcon:
        """Create tray icon with status indicator"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background circle
        bg_color = QColor(COLORS["primary"]) if connected else QColor(COLORS["secondary"])
        painter.setBrush(bg_color)
        painter.setPen(QColor(0, 0, 0, 0))
        painter.drawEllipse(4, 4, 56, 56)

        # Cloud icon (simplified)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(12, 24, 20, 20)  # Left cloud part
        painter.drawEllipse(24, 18, 24, 26)  # Center
        painter.drawEllipse(36, 26, 16, 16)  # Right

        # Status indicator
        if has_activity:
            painter.setBrush(QColor(COLORS["warning"]))
            painter.drawEllipse(44, 4, 16, 16)

        painter.end()

        return QIcon(pixmap)

    def _setup_menu(self):
        """Setup context menu"""
        menu = QMenu()
        menu.setStyleSheet(
            f"""
            QMenu {{
                background-color: {COLORS['bg_medium']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
                color: {COLORS['text_primary']};
            }}
            QMenu::item:selected {{
                background-color: {COLORS['primary']};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {COLORS['border']};
                margin: 4px 8px;
            }}
        """
        )

        # Status header (non-clickable)
        self.status_action = QAction("● Disconnected", self)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)

        menu.addSeparator()

        # Show/Hide window
        self.show_action = QAction("Show Window", self)
        self.show_action.triggered.connect(self.show_window_requested.emit)
        menu.addAction(self.show_action)

        menu.addSeparator()

        # Connection actions
        self.connect_action = QAction("Connect...", self)
        self.connect_action.triggered.connect(self.connect_requested.emit)
        menu.addAction(self.connect_action)

        self.disconnect_action = QAction("Disconnect", self)
        self.disconnect_action.triggered.connect(self.disconnect_requested.emit)
        self.disconnect_action.setEnabled(False)
        menu.addAction(self.disconnect_action)

        menu.addSeparator()

        # Stats section
        self.jobs_action = QAction("Jobs: 0 running, 0 pending", self)
        self.jobs_action.setEnabled(False)
        menu.addAction(self.jobs_action)

        self.workers_action = QAction("Workers: 0 active", self)
        self.workers_action.setEnabled(False)
        menu.addAction(self.workers_action)

        menu.addSeparator()

        # Quick actions
        submit_action = QAction("Submit Job...", self)
        submit_action.triggered.connect(lambda: self._quick_action("submit_job"))
        menu.addAction(submit_action)

        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(lambda: self._quick_action("refresh"))
        menu.addAction(refresh_action)

        menu.addSeparator()

        # Quit
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def _connect_signals(self):
        """Connect signals"""
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window_requested.emit()
        elif reason == QSystemTrayIcon.Trigger:
            # Single click - show menu on some platforms
            pass

    def _quick_action(self, action: str):
        """Handle quick actions"""
        self.show_window_requested.emit()
        # The main window will handle the actual action

    def set_connected(self, connected: bool, server_name: str = ""):
        """Update connection status"""
        self._connected = connected

        if connected:
            self.status_action.setText(f"● Connected to {server_name}")
            self.setToolTip(f"NebulaCompute Desktop\nConnected to {server_name}")
            self.disconnect_action.setEnabled(True)
            self.connect_action.setEnabled(False)
        else:
            self.status_action.setText("● Disconnected")
            self.setToolTip("NebulaCompute Desktop\nDisconnected")
            self.disconnect_action.setEnabled(False)
            self.connect_action.setEnabled(True)

        self.setIcon(self._create_icon(connected, self._running_jobs > 0))

    def update_stats(self, running_jobs: int, pending_jobs: int, active_workers: int):
        """Update statistics display"""
        self._running_jobs = running_jobs
        self._pending_jobs = pending_jobs

        self.jobs_action.setText(f"Jobs: {running_jobs} running, {pending_jobs} pending")
        self.workers_action.setText(f"Workers: {active_workers} active")

        # Update icon if there's activity
        self.setIcon(self._create_icon(self._connected, running_jobs > 0))

        # Update tooltip
        if self._connected:
            self.setToolTip(
                f"NebulaCompute Desktop\n" f"Jobs: {running_jobs} running\n" f"Workers: {active_workers} active"
            )

    def show_message(
        self, title: str, message: str, icon_type: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.Information
    ):
        """Show a balloon notification"""
        self.showMessage(title, message, icon_type, 5000)

    def notify_job_completed(self, job_id: str, job_name: str = ""):
        """Show notification for completed job"""
        name = job_name or job_id
        self.show_message("Job Completed", f"Job '{name}' has finished successfully", QSystemTrayIcon.Information)

    def notify_job_failed(self, job_id: str, job_name: str = "", error: str = ""):
        """Show notification for failed job"""
        name = job_name or job_id
        message = f"Job '{name}' has failed"
        if error:
            message += f"\n{error}"
        self.show_message("Job Failed", message, QSystemTrayIcon.Warning)

    def notify_disconnected(self):
        """Show notification for disconnection"""
        self.show_message("Disconnected", "Connection to server lost", QSystemTrayIcon.Warning)
