"""
Main Application Window
النافذة الرئيسية للتطبيق
"""

import asyncio
from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QShortcut, QKeySequence, QAction
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QWidget,
    QMenu,
    QMenuBar,
)

from .api.client import APIClient, ClusterStats
from .resources.styles import COLORS, MAIN_STYLESHEET
from .views.dashboard import DashboardView
from .views.jobs import JobsView
from .views.logs import LogsView
from .views.pools import PoolsView
from .views.queues import QueuesView
from .views.settings import SettingsView
from .views.templates import TemplatesView
from .views.workers import WorkersView
from .widgets.sidebar import Sidebar
from .widgets.connection_dialog import ConnectionDialog
from .widgets.notifications import NotificationManager, NotificationType


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.api_client: Optional[APIClient] = None
        self._connected = False
        self._server_name = ""

        self._setup_window()
        self._setup_ui()
        self._setup_menu()
        self._setup_shortcuts()
        self._setup_notifications()
        self._setup_connections()
        self._setup_refresh_timer()

    def _setup_window(self):
        """Configure main window"""
        self.setWindowTitle("NebulaCompute Desktop")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # Apply stylesheet
        self.setStyleSheet(MAIN_STYLESHEET)

    def _setup_ui(self):
        """Setup main UI layout"""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._on_page_changed)
        main_layout.addWidget(self.sidebar)

        # Content area (stacked widget for pages)
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack)

        # Create views
        self._create_views()

        # Status bar
        self.statusBar = QStatusBar()
        self.statusBar.setStyleSheet(f"""
            background-color: {COLORS['bg_medium']};
            color: {COLORS['text_secondary']};
            border-top: 1px solid {COLORS['border']};
        """)
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Disconnected")

    def _create_views(self):
        """Create all view pages"""
        # Dashboard
        self.dashboard_view = DashboardView()
        self.content_stack.addWidget(self.dashboard_view)

        # Jobs
        self.jobs_view = JobsView()
        self.jobs_view.refresh_requested.connect(self._refresh_jobs)
        self.content_stack.addWidget(self.jobs_view)

        # Workers
        self.workers_view = WorkersView()
        self.workers_view.refresh_requested.connect(self._refresh_workers)
        self.content_stack.addWidget(self.workers_view)

        # Templates
        self.templates_view = TemplatesView()
        self.templates_view.refresh_requested.connect(self._refresh_templates)
        self.content_stack.addWidget(self.templates_view)

        # Pools
        self.pools_view = PoolsView()
        self.pools_view.refresh_requested.connect(self._refresh_pools)
        self.content_stack.addWidget(self.pools_view)

        # Queues
        self.queues_view = QueuesView()
        self.queues_view.refresh_requested.connect(self._refresh_queues)
        self.content_stack.addWidget(self.queues_view)

        # Settings
        self.settings_view = SettingsView()
        self.settings_view.connection_requested.connect(self._on_connection_requested)
        self.settings_view.settings_changed.connect(self._on_settings_changed)
        self.content_stack.addWidget(self.settings_view)

        # Logs
        self.logs_view = LogsView()
        self.logs_view.refresh_requested.connect(self._refresh_logs)
        self.content_stack.addWidget(self.logs_view)

        # Map page names to stack indices
        self._page_indices = {
            "dashboard": 0,
            "jobs": 1,
            "workers": 2,
            "templates": 3,
            "pools": 4,
            "queues": 5,
            "settings": 6,
            "logs": 7,
        }

    def _setup_menu(self):
        """Setup menu bar"""
        menubar = self.menuBar()
        menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_primary']};
                border-bottom: 1px solid {COLORS['border']};
                padding: 4px;
            }}
            QMenuBar::item:selected {{
                background-color: {COLORS['bg_light']};
            }}
        """)

        # File menu
        file_menu = menubar.addMenu("&File")

        connect_action = QAction("&Connect to Server...", self)
        connect_action.setShortcut("Ctrl+K")
        connect_action.triggered.connect(self._show_connection_dialog)
        file_menu.addAction(connect_action)

        disconnect_action = QAction("&Disconnect", self)
        disconnect_action.triggered.connect(self._disconnect)
        file_menu.addAction(disconnect_action)

        file_menu.addSeparator()

        export_action = QAction("&Export Data...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._export_data)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        dashboard_action = QAction("&Dashboard", self)
        dashboard_action.setShortcut("Ctrl+1")
        dashboard_action.triggered.connect(lambda: self._navigate_to("dashboard"))
        view_menu.addAction(dashboard_action)

        jobs_action = QAction("&Jobs", self)
        jobs_action.setShortcut("Ctrl+2")
        jobs_action.triggered.connect(lambda: self._navigate_to("jobs"))
        view_menu.addAction(jobs_action)

        workers_action = QAction("&Workers", self)
        workers_action.setShortcut("Ctrl+3")
        workers_action.triggered.connect(lambda: self._navigate_to("workers"))
        view_menu.addAction(workers_action)

        view_menu.addSeparator()

        settings_action = QAction("&Settings", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(lambda: self._navigate_to("settings"))
        view_menu.addAction(settings_action)

        # Actions menu
        actions_menu = menubar.addMenu("&Actions")

        refresh_action = QAction("&Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._manual_refresh)
        actions_menu.addAction(refresh_action)

        submit_job_action = QAction("&Submit Job...", self)
        submit_job_action.setShortcut("Ctrl+N")
        submit_job_action.triggered.connect(self._show_submit_job_dialog)
        actions_menu.addAction(submit_job_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        shortcuts_action = QAction("Keyboard &Shortcuts", self)
        shortcuts_action.setShortcut("Ctrl+/")
        shortcuts_action.triggered.connect(self._show_shortcuts_help)
        help_menu.addAction(shortcuts_action)

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Navigation shortcuts
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self._navigate_to("dashboard"))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self._navigate_to("jobs"))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self._navigate_to("workers"))
        QShortcut(QKeySequence("Ctrl+4"), self, lambda: self._navigate_to("templates"))
        QShortcut(QKeySequence("Ctrl+5"), self, lambda: self._navigate_to("pools"))
        QShortcut(QKeySequence("Ctrl+6"), self, lambda: self._navigate_to("queues"))
        QShortcut(QKeySequence("Ctrl+7"), self, lambda: self._navigate_to("logs"))

        # Action shortcuts
        QShortcut(QKeySequence("F5"), self, self._manual_refresh)
        QShortcut(QKeySequence("Ctrl+R"), self, self._manual_refresh)

    def _setup_notifications(self):
        """Setup notification system"""
        self.notifications = NotificationManager(self)
        self.notifications.setGeometry(
            self.width() - 370, 20,
            360, self.height() - 40
        )

    def _setup_connections(self):
        """Setup signal connections"""
        pass

    def resizeEvent(self, event):
        """Handle window resize"""
        super().resizeEvent(event)
        # Reposition notifications
        if hasattr(self, 'notifications'):
            self.notifications.setGeometry(
                self.width() - 370, 20,
                360, self.height() - 40
            )

    def _setup_refresh_timer(self):
        """Setup auto-refresh timer"""
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.start(5000)  # 5 seconds

    def _on_page_changed(self, page_id: str):
        """Handle page navigation"""
        index = self._page_indices.get(page_id, 0)
        self.content_stack.setCurrentIndex(index)

        # Refresh data for the page
        if self._connected:
            self._refresh_page(page_id)

    def _refresh_page(self, page_id: str):
        """Refresh data for a specific page"""
        if page_id == "dashboard":
            self._refresh_dashboard()
        elif page_id == "jobs":
            self._refresh_jobs()
        elif page_id == "workers":
            self._refresh_workers()
        elif page_id == "templates":
            self._refresh_templates()
        elif page_id == "pools":
            self._refresh_pools()
        elif page_id == "queues":
            self._refresh_queues()
        elif page_id == "logs":
            self._refresh_logs()

    def _auto_refresh(self):
        """Auto-refresh current page data"""
        if not self._connected:
            return

        current_index = self.content_stack.currentIndex()
        page_id = list(self._page_indices.keys())[current_index]
        self._refresh_page(page_id)

    # ============ Connection Management ============

    def _on_connection_requested(self, url: str, token: str):
        """Handle connection request from settings"""
        asyncio.ensure_future(self._connect_to_server(url, token))

    async def _connect_to_server(self, url: str, token: str):
        """Connect to master server"""
        self.statusBar.showMessage(f"Connecting to {url}...")

        self.api_client = APIClient(url, token)

        # Connect signals
        self.api_client.connected.connect(self._on_connected)
        self.api_client.disconnected.connect(self._on_disconnected)
        self.api_client.error_occurred.connect(self._on_error)
        self.api_client.stats_updated.connect(self._on_stats_updated)

        success = await self.api_client.connect()
        if success:
            # Set API client on all views
            self._set_api_client_on_views()
        else:
            QMessageBox.warning(
                self, "Connection Failed",
                f"Could not connect to {url}"
            )

    def _set_api_client_on_views(self):
        """Set API client on all views"""
        self.dashboard_view.set_api_client(self.api_client)
        self.jobs_view.set_api_client(self.api_client)
        self.workers_view.set_api_client(self.api_client)
        self.templates_view.set_api_client(self.api_client)
        self.pools_view.set_api_client(self.api_client)
        self.queues_view.set_api_client(self.api_client)
        self.logs_view.set_api_client(self.api_client)

    def _on_connected(self):
        """Handle successful connection"""
        self._connected = True
        self.sidebar.set_connection_status(True)
        self.statusBar.showMessage("Connected", 3000)
        self.setWindowTitle(f"NebulaCompute Desktop - {self._server_name}")

        # Show notification
        self.notifications.success(
            "Connected",
            f"Successfully connected to {self._server_name}"
        )

        # Refresh all data
        self._refresh_dashboard()

    def _on_disconnected(self):
        """Handle disconnection"""
        self._connected = False
        self.sidebar.set_connection_status(False)
        self.statusBar.showMessage("Disconnected")
        self.setWindowTitle("NebulaCompute Desktop")

        # Show notification
        self.notifications.warning(
            "Disconnected",
            "Connection to server lost"
        )

    def _on_error(self, message: str):
        """Handle API error"""
        self.statusBar.showMessage(f"Error: {message}", 5000)
        self.logs_view.append_log(f"API Error: {message}", "error")

        # Show notification for errors
        self.notifications.error("Error", message)

    def _on_settings_changed(self, settings: dict):
        """Handle settings change"""
        # Update refresh interval
        interval = settings.get("refresh_interval", 5) * 1000
        self.refresh_timer.setInterval(interval)

    # ============ Data Refresh Methods ============

    def _on_stats_updated(self, data):
        """Handle real-time stats update"""
        if isinstance(data, dict):
            stats = ClusterStats(**data)
            self.dashboard_view.update_stats(stats)

    def _refresh_dashboard(self):
        """Refresh dashboard data"""
        if self.api_client and self._connected:
            asyncio.ensure_future(self._async_refresh_dashboard())

    async def _async_refresh_dashboard(self):
        """Async refresh dashboard"""
        try:
            stats = await self.api_client.get_stats()
            self.dashboard_view.update_stats(stats)

            health = await self.api_client.get_health()
            self.dashboard_view.update_health(health)
        except Exception as e:
            self._on_error(f"Failed to refresh dashboard: {e}")

    def _refresh_jobs(self):
        """Refresh jobs data"""
        if self.api_client and self._connected:
            asyncio.ensure_future(self._async_refresh_jobs())

    async def _async_refresh_jobs(self):
        """Async refresh jobs"""
        try:
            status_filter = self.jobs_view.get_status_filter()
            jobs = await self.api_client.get_jobs(status=status_filter)
            self.jobs_view.set_jobs(jobs)
        except Exception as e:
            self._on_error(f"Failed to refresh jobs: {e}")

    def _refresh_workers(self):
        """Refresh workers data"""
        if self.api_client and self._connected:
            asyncio.ensure_future(self._async_refresh_workers())

    async def _async_refresh_workers(self):
        """Async refresh workers"""
        try:
            workers = await self.api_client.get_workers()
            self.workers_view.set_workers(workers)
        except Exception as e:
            self._on_error(f"Failed to refresh workers: {e}")

    def _refresh_templates(self):
        """Refresh templates data"""
        if self.api_client and self._connected:
            asyncio.ensure_future(self._async_refresh_templates())

    async def _async_refresh_templates(self):
        """Async refresh templates"""
        try:
            templates = await self.api_client.get_templates()
            self.templates_view.set_templates(templates)
        except Exception as e:
            self._on_error(f"Failed to refresh templates: {e}")

    def _refresh_pools(self):
        """Refresh pools data"""
        if self.api_client and self._connected:
            asyncio.ensure_future(self._async_refresh_pools())

    async def _async_refresh_pools(self):
        """Async refresh pools"""
        try:
            pools = await self.api_client.get_pools()
            self.pools_view.set_pools(pools)
        except Exception as e:
            self._on_error(f"Failed to refresh pools: {e}")

    def _refresh_queues(self):
        """Refresh queues data"""
        if self.api_client and self._connected:
            asyncio.ensure_future(self._async_refresh_queues())

    async def _async_refresh_queues(self):
        """Async refresh queues"""
        try:
            queues = await self.api_client.get_queues()
            self.queues_view.set_queues(queues)
        except Exception as e:
            self._on_error(f"Failed to refresh queues: {e}")

    def _refresh_logs(self):
        """Refresh logs"""
        # Logs are typically streamed via WebSocket
        pass

    # ============ Menu Actions ============

    def _show_connection_dialog(self):
        """Show connection dialog"""
        dialog = ConnectionDialog(self)
        dialog.connection_requested.connect(self._on_dialog_connection_requested)
        dialog.exec()

    def _on_dialog_connection_requested(self, url: str, token: str, name: str):
        """Handle connection request from dialog"""
        self._server_name = name
        asyncio.ensure_future(self._connect_to_server(url, token))

    def _disconnect(self):
        """Disconnect from server"""
        if self.api_client and self._connected:
            asyncio.ensure_future(self.api_client.disconnect())
            self.notifications.info("Disconnected", f"Disconnected from {self._server_name}")

    def _navigate_to(self, page_id: str):
        """Navigate to a page"""
        self.sidebar.set_active_page(page_id)
        self._on_page_changed(page_id)

    def _manual_refresh(self):
        """Manual refresh current page"""
        current_index = self.content_stack.currentIndex()
        page_id = list(self._page_indices.keys())[current_index]
        self._refresh_page(page_id)
        self.statusBar.showMessage("Refreshed", 2000)

    def _show_submit_job_dialog(self):
        """Show submit job dialog"""
        self._navigate_to("jobs")
        # The jobs view has its own submit dialog

    def _export_data(self):
        """Export current view data"""
        from PySide6.QtWidgets import QFileDialog
        import json
        import csv
        from datetime import datetime

        current_index = self.content_stack.currentIndex()
        page_id = list(self._page_indices.keys())[current_index]

        # Get data based on current view
        data = []
        if page_id == "jobs":
            data = self.jobs_view.jobs_table._data
        elif page_id == "workers":
            data = self.workers_view.workers_table._data
        elif page_id == "templates":
            data = self.templates_view.templates_table._data

        if not data:
            QMessageBox.information(self, "Export", "No data to export")
            return

        # Ask for file location
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Data",
            f"nebula_{page_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json);;CSV Files (*.csv)"
        )

        if not filename:
            return

        try:
            if filename.endswith('.csv'):
                with open(filename, 'w', newline='') as f:
                    if data:
                        writer = csv.DictWriter(f, fieldnames=data[0].keys())
                        writer.writeheader()
                        writer.writerows(data)
            else:
                with open(filename, 'w') as f:
                    json.dump(data, f, indent=2, default=str)

            self.notifications.success("Export Complete", f"Data exported to {filename}")
        except Exception as e:
            self.notifications.error("Export Failed", str(e))

    def _show_shortcuts_help(self):
        """Show keyboard shortcuts help"""
        shortcuts_text = """
<h3>Keyboard Shortcuts</h3>
<table>
<tr><td><b>Ctrl+K</b></td><td>Connect to server</td></tr>
<tr><td><b>Ctrl+Q</b></td><td>Quit application</td></tr>
<tr><td><b>Ctrl+E</b></td><td>Export data</td></tr>
<tr><td><b>F5 / Ctrl+R</b></td><td>Refresh</td></tr>
<tr><td><b>Ctrl+N</b></td><td>Submit new job</td></tr>
<tr><td><b>Ctrl+1</b></td><td>Dashboard</td></tr>
<tr><td><b>Ctrl+2</b></td><td>Jobs</td></tr>
<tr><td><b>Ctrl+3</b></td><td>Workers</td></tr>
<tr><td><b>Ctrl+4</b></td><td>Templates</td></tr>
<tr><td><b>Ctrl+5</b></td><td>Pools</td></tr>
<tr><td><b>Ctrl+6</b></td><td>Queues</td></tr>
<tr><td><b>Ctrl+7</b></td><td>Logs</td></tr>
<tr><td><b>Ctrl+,</b></td><td>Settings</td></tr>
</table>
        """
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)

    def _show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About NebulaCompute Desktop",
            """
<h2>NebulaCompute Desktop</h2>
<p>Version 0.1.0</p>
<p>A modern desktop interface for managing distributed computing clusters.</p>
<p><b>Features:</b></p>
<ul>
<li>Real-time cluster monitoring</li>
<li>Job submission and management</li>
<li>Worker monitoring and control</li>
<li>Resource visualization</li>
</ul>
<p>Built with PySide6 (Qt6)</p>
            """
        )

    def show_startup_dialog(self):
        """Show connection dialog on startup"""
        # Small delay to allow window to fully initialize
        QTimer.singleShot(100, self._show_connection_dialog)

    # ============ Window Events ============

    def closeEvent(self, event):
        """Handle window close"""
        if self.api_client and self._connected:
            asyncio.ensure_future(self.api_client.disconnect())

        event.accept()
