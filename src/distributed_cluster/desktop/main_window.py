"""
Main Application Window
النافذة الرئيسية للتطبيق
"""

import asyncio
from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QWidget,
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


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.api_client: Optional[APIClient] = None
        self._connected = False

        self._setup_window()
        self._setup_ui()
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

    def _setup_connections(self):
        """Setup signal connections"""
        pass

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
        self.statusBar.showMessage("Ready")

        # Refresh all data
        self._refresh_dashboard()

    def _on_disconnected(self):
        """Handle disconnection"""
        self._connected = False
        self.sidebar.set_connection_status(False)
        self.statusBar.showMessage("Disconnected")

    def _on_error(self, message: str):
        """Handle API error"""
        self.statusBar.showMessage(f"Error: {message}", 5000)
        self.logs_view.append_log(f"API Error: {message}", "error")

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

    # ============ Window Events ============

    def closeEvent(self, event):
        """Handle window close"""
        if self.api_client and self._connected:
            asyncio.ensure_future(self.api_client.disconnect())

        event.accept()
