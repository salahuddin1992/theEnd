"""
Advanced Fluent Main Window
النافذة الرئيسية المتقدمة بتصميم Fluent

The main application window that combines all Fluent UI components
into a cohesive Windows 11 style experience.

Features:
- Windows 11 Fluent Design
- All view pages integrated
- Windows integration (tray, notifications)
- Splash screen on startup
"""

from __future__ import annotations

import sys
from typing import Dict

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QSplitter, QStackedWidget, QVBoxLayout, QWidget

from .components import SkeletonLoader
from .dashboard import FluentDashboard
from .dialogs import ConfirmationDialog, ConfirmationType, ConnectionDialog
from .fluent_design import FluentDesignSystem
from .notifications import InAppNotificationManager
from .sidebar import FluentSidebar
from .titlebar import FluentIcons, FramelessWindow
from .views import (
    FluentJobsView,
    FluentLogsView,
    FluentMetricsView,
    FluentPoolsView,
    FluentQueuesView,
    FluentSettingsView,
    FluentTemplatesView,
    FluentWorkersView,
)
from .windows_integration import IS_WINDOWS, WindowsIntegrationManager

# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT MAIN WINDOW
# النافذة الرئيسية بتصميم Fluent
# ═══════════════════════════════════════════════════════════════════════════════


class FluentMainWindow(FramelessWindow):
    """
    Advanced Fluent Design main window.
    النافذة الرئيسية المتقدمة بتصميم Fluent

    Features:
    - Frameless window with custom title bar
    - Mica/Acrylic background effect
    - Animated sidebar navigation
    - Modern notification system
    - Fluent Design components throughout
    """

    # Signals
    connected = Signal()
    disconnected = Signal()
    page_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, title="NebulaCompute Desktop")

        self._connected = False
        self._server_name = ""
        self._current_page = "dashboard"
        self._views: Dict[str, QWidget] = {}

        # Windows integration
        self._windows = WindowsIntegrationManager(self) if IS_WINDOWS else None

        self._setup_main_ui()
        self._setup_shortcuts()
        self._setup_notifications()
        self._setup_refresh_timer()
        self._setup_windows_integration()

        # Initial state
        self._show_loading_state()

    def _setup_main_ui(self):
        """Setup the main UI structure"""
        colors = FluentDesignSystem().colors

        # Main container
        main_container = QWidget()
        main_layout = QHBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self._sidebar = FluentSidebar()
        self._sidebar.page_changed.connect(self._on_page_changed)
        self._sidebar.expanded_changed.connect(self._on_sidebar_expanded)
        main_layout.addWidget(self._sidebar)

        # Content area
        content_container = QWidget()
        content_container.setStyleSheet(f"background-color: {colors.bg_mica_base};")
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Splitter for content and terminal
        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet(
            f"""
            QSplitter::handle {{
                background-color: {colors.stroke_divider};
            }}
            QSplitter::handle:hover {{
                background-color: {colors.accent};
            }}
        """
        )

        # Content stack
        self._content_stack = QStackedWidget()
        self._splitter.addWidget(self._content_stack)

        # Create views
        self._create_views()

        # Terminal (placeholder - hidden by default)
        self._terminal = QFrame()
        self._terminal.setStyleSheet(
            f"""
            QFrame {{
                background-color: {colors.bg_solid_base};
                border-top: 1px solid {colors.stroke_divider};
            }}
        """
        )
        self._terminal.setMinimumHeight(150)
        self._terminal.setVisible(False)
        self._splitter.addWidget(self._terminal)

        self._splitter.setSizes([800, 0])
        content_layout.addWidget(self._splitter)

        # Status bar
        self._status_bar = self._create_status_bar()
        content_layout.addWidget(self._status_bar)

        main_layout.addWidget(content_container, 1)

        # Set content
        self.set_content(main_container)

    def _create_views(self):
        """Create all view pages"""
        FluentDesignSystem().colors

        # Dashboard
        self._dashboard = FluentDashboard()
        self._views["dashboard"] = self._dashboard
        self._content_stack.addWidget(self._dashboard)

        # Jobs View
        self._jobs_view = FluentJobsView()
        self._views["jobs"] = self._jobs_view
        self._content_stack.addWidget(self._jobs_view)

        # Workers View
        self._workers_view = FluentWorkersView()
        self._views["workers"] = self._workers_view
        self._content_stack.addWidget(self._workers_view)

        # Logs View
        self._logs_view = FluentLogsView()
        self._views["logs"] = self._logs_view
        self._content_stack.addWidget(self._logs_view)

        # Metrics View
        self._metrics_view = FluentMetricsView()
        self._views["metrics"] = self._metrics_view
        self._content_stack.addWidget(self._metrics_view)

        # Settings View
        self._settings_view = FluentSettingsView()
        self._views["settings"] = self._settings_view
        self._content_stack.addWidget(self._settings_view)

        # Templates View
        self._templates_view = FluentTemplatesView()
        self._views["templates"] = self._templates_view
        self._content_stack.addWidget(self._templates_view)

        # Pools View
        self._pools_view = FluentPoolsView()
        self._views["pools"] = self._pools_view
        self._content_stack.addWidget(self._pools_view)

        # Queues View
        self._queues_view = FluentQueuesView()
        self._views["queues"] = self._queues_view
        self._content_stack.addWidget(self._queues_view)

    def _create_placeholder_view(self, title: str) -> QWidget:
        """Create a placeholder view"""
        colors = FluentDesignSystem().colors

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel(title)
        header.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 28px;
            font-weight: 600;
        """
        )
        layout.addWidget(header)

        # Loading skeleton
        skeleton_container = QWidget()
        skeleton_layout = QVBoxLayout(skeleton_container)
        skeleton_layout.setSpacing(16)

        for _ in range(3):
            row = QHBoxLayout()
            row.addWidget(SkeletonLoader(200, 120))
            row.addWidget(SkeletonLoader(200, 120))
            row.addWidget(SkeletonLoader(200, 120))
            row.addStretch()
            skeleton_layout.addLayout(row)

        skeleton_layout.addStretch()
        layout.addWidget(skeleton_container)

        return widget

    def _create_status_bar(self) -> QWidget:
        """Create custom status bar"""
        colors = FluentDesignSystem().colors

        status_bar = QWidget()
        status_bar.setFixedHeight(24)
        status_bar.setStyleSheet(
            f"""
            QWidget {{
                background-color: {colors.bg_solid_secondary};
                border-top: 1px solid {colors.stroke_divider};
            }}
        """
        )

        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(16)

        # Connection status
        self._connection_indicator = QLabel()
        self._connection_indicator.setFixedSize(8, 8)
        self._update_connection_indicator()
        layout.addWidget(self._connection_indicator)

        self._status_label = QLabel("Disconnected")
        self._status_label.setStyleSheet(
            f"""
            color: {colors.text_secondary};
            font-size: 12px;
        """
        )
        layout.addWidget(self._status_label)

        layout.addStretch()

        # Version
        version_label = QLabel("v0.1.0")
        version_label.setStyleSheet(
            f"""
            color: {colors.text_tertiary};
            font-size: 11px;
        """
        )
        layout.addWidget(version_label)

        return status_bar

    def _update_connection_indicator(self):
        """Update connection status indicator"""
        colors = FluentDesignSystem().colors
        color = colors.success if self._connected else colors.text_disabled

        self._connection_indicator.setStyleSheet(
            f"""
            background-color: {color};
            border-radius: 4px;
        """
        )

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Navigation
        for i, page_id in enumerate(
            ["dashboard", "jobs", "workers", "templates", "pools", "queues", "logs", "metrics"], 1
        ):
            if i <= 9:
                QShortcut(QKeySequence(f"Ctrl+{i}"), self, lambda p=page_id: self._navigate_to(p))

        # Actions
        QShortcut(QKeySequence("F5"), self, self._refresh)
        QShortcut(QKeySequence("Ctrl+R"), self, self._refresh)
        QShortcut(QKeySequence("Ctrl+K"), self, self._show_connect_dialog)
        QShortcut(QKeySequence("Ctrl+`"), self, self._toggle_terminal)
        QShortcut(QKeySequence("Ctrl+,"), self, lambda: self._navigate_to("settings"))

    def _setup_notifications(self):
        """Setup notification system"""
        self._notifications = InAppNotificationManager(self)

    def _setup_refresh_timer(self):
        """Setup auto-refresh timer"""
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(5000)  # 5 seconds

    def _setup_windows_integration(self):
        """Setup Windows 11 integration"""
        if not self._windows:
            return

        # Setup for this window
        self._windows.setup_for_window(self)

        # Connect tray signals
        self._windows.tray.show_window.connect(self.show)
        self._windows.tray.show_window.connect(self.raise_)
        self._windows.tray.hide_window.connect(self.hide)
        self._windows.tray.quit_requested.connect(self._on_quit_requested)
        self._windows.tray.action_triggered.connect(self._on_tray_action)

        # Theme change detection
        self._windows.theme_changed.connect(self._on_theme_changed)

    def _on_quit_requested(self):
        """Handle quit from tray"""
        dialog = ConfirmationDialog(
            "Quit NebulaCompute",
            "Are you sure you want to quit? Any running jobs will continue on the cluster.",
            "Quit",
            "Cancel",
            ConfirmationType.QUESTION,
            self,
        )
        if dialog.exec():
            QApplication.quit()

    def _on_tray_action(self, action: str):
        """Handle tray menu actions"""
        if action == "submit_job":
            self._navigate_to("jobs")
        elif action == "refresh":
            self._refresh()
        elif action == "settings":
            self._navigate_to("settings")

    def _on_theme_changed(self, is_dark: bool):
        """Handle Windows theme change"""
        # Would switch app theme
        pass

    def _show_loading_state(self):
        """Show initial loading state"""
        # Simulate loading data
        QTimer.singleShot(500, self._load_demo_data)

    def _load_demo_data(self):
        """Load demo data for preview"""
        # Update dashboard with demo data
        self._dashboard.update_stats(jobs=42, workers=8, pending=12, failed=3)

        self._dashboard.update_chart([15, 22, 18, 25, 32, 28, 35, 42, 38, 45, 52, 48])

        self._dashboard.update_health(cpu=45.5, memory=62.3, disk=38.7)

        # Add some activities
        self._dashboard.add_activity(
            FluentIcons.CHECKMARK, "Job Completed", "Training job #1234 finished successfully", "2m ago", "success"
        )

        self._dashboard.add_activity(
            FluentIcons.PLAY, "Job Started", "Inference job #1235 started on worker-03", "5m ago", "info"
        )

        self._dashboard.add_activity(
            FluentIcons.WARNING, "Worker Warning", "Worker-05 memory usage above 90%", "12m ago", "warning"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # NAVIGATION
    # ═══════════════════════════════════════════════════════════════════════════

    def _on_page_changed(self, page_id: str):
        """Handle page navigation from sidebar"""
        self._navigate_to(page_id)

    def _navigate_to(self, page_id: str):
        """Navigate to a page"""
        if page_id not in self._views:
            return

        self._current_page = page_id
        self._sidebar.set_active_page(page_id)

        # Find page index
        view = self._views[page_id]
        index = self._content_stack.indexOf(view)
        if index >= 0:
            self._content_stack.setCurrentIndex(index)

        self.page_changed.emit(page_id)

        # Refresh page data
        if self._connected:
            self._refresh_page(page_id)

    def _on_sidebar_expanded(self, expanded: bool):
        """Handle sidebar expand/collapse"""
        pass  # Can animate content area if needed

    # ═══════════════════════════════════════════════════════════════════════════
    # CONNECTION
    # ═══════════════════════════════════════════════════════════════════════════

    def _show_connect_dialog(self):
        """Show server connection dialog"""
        dialog = ConnectionDialog(self)
        dialog.connection_requested.connect(self._handle_connection)
        dialog.exec()

    def _handle_connection(self, config: dict):
        """Handle connection request from dialog"""
        host = config.get("host", "localhost")
        port = config.get("port", 8765)

        # Simulate connection
        self.set_connected(True, f"{host}:{port}")

        # Show notification
        if self._windows:
            self._windows.show_notification("Connected", f"Successfully connected to {host}:{port}", "success")

    def set_connected(self, connected: bool, server_name: str = ""):
        """Update connection state"""
        self._connected = connected
        self._server_name = server_name

        self._update_connection_indicator()
        self._sidebar.set_connection_status(connected, server_name)

        if connected:
            self._status_label.setText(f"Connected to {server_name}")
            self.setWindowTitle(f"NebulaCompute - {server_name}")
            self._notifications.success("Connected", f"Connected to {server_name}")
            self.connected.emit()
        else:
            self._status_label.setText("Disconnected")
            self.setWindowTitle("NebulaCompute Desktop")
            self.disconnected.emit()

    # ═══════════════════════════════════════════════════════════════════════════
    # REFRESH
    # ═══════════════════════════════════════════════════════════════════════════

    def _refresh(self):
        """Manual refresh"""
        self._refresh_page(self._current_page)
        self._notifications.info("Refreshed", "Data updated")

    def _auto_refresh(self):
        """Auto-refresh current page"""
        if self._connected:
            self._refresh_page(self._current_page)

    def _refresh_page(self, page_id: str):
        """Refresh a specific page"""
        # Would call API client methods here
        pass

    # ═══════════════════════════════════════════════════════════════════════════
    # TERMINAL
    # ═══════════════════════════════════════════════════════════════════════════

    def _toggle_terminal(self):
        """Toggle terminal panel visibility"""
        is_visible = self._terminal.isVisible()
        self._terminal.setVisible(not is_visible)

        if not is_visible:
            self._splitter.setSizes([600, 200])
        else:
            self._splitter.setSizes([800, 0])

    # ═══════════════════════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════════════════════

    def show_notification(self, title: str, message: str = "", type: str = "info"):
        """Show a notification"""
        if type == "success":
            self._notifications.success(title, message)
        elif type == "warning":
            self._notifications.warning(title, message)
        elif type == "error":
            self._notifications.error(title, message)
        else:
            self._notifications.info(title, message)

    def update_dashboard(self, stats: dict):
        """Update dashboard with new stats"""
        self._dashboard.update_stats(
            jobs=stats.get("running_jobs", 0),
            workers=stats.get("active_workers", 0),
            pending=stats.get("pending_jobs", 0),
            failed=stats.get("failed_jobs", 0),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# نقطة الدخول
# ═══════════════════════════════════════════════════════════════════════════════


def create_fluent_app(show_splash: bool = True):
    """
    Create and configure the Fluent Design application.
    إنشاء وتكوين تطبيق Fluent Design

    Args:
        show_splash: Whether to show splash screen on startup

    Returns:
        Tuple of (QApplication, FluentMainWindow)
    """
    from .splash import SplashScreenManager

    # Check for PySide6
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is required. Install with: pip install PySide6")
        sys.exit(1)

    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)

    # Application metadata
    app.setApplicationName("NebulaCompute Desktop")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("NebulaCompute")
    app.setOrganizationDomain("nebulacompute.io")

    # Apply Fluent stylesheet
    design = FluentDesignSystem()
    app.setStyleSheet(design.generate_stylesheet())

    # Set default font
    font = QFont("Segoe UI Variable", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    # Show splash screen
    if show_splash:
        splash_manager = SplashScreenManager()
        splash_manager.create()

        # Add initialization steps
        splash_manager.add_step("Loading design system...", None)
        splash_manager.add_step("Initializing components...", None)
        splash_manager.add_step("Loading views...", None)
        splash_manager.add_step("Setting up Windows integration...", None)
        splash_manager.add_step("Preparing dashboard...", None)

        splash_manager.show()
        splash_manager.run_steps()

        # Create main window
        window = FluentMainWindow()
        window.resize(1400, 900)

        # Finish splash and show window
        splash_manager.finish(window)
    else:
        # Create main window directly
        window = FluentMainWindow()
        window.resize(1400, 900)
        window.show()

    return app, window


def run_app():
    """
    Run the NebulaCompute Desktop application.
    تشغيل تطبيق NebulaCompute Desktop
    """
    app, window = create_fluent_app(show_splash=True)
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
