"""
Dashboard View - Main overview page
صفحة لوحة التحكم الرئيسية
"""

from collections import deque
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..api.client import APIClient, ClusterStats
from ..resources.styles import COLORS
from ..widgets.charts import BarChart, DonutChart, LineChart
from ..widgets.stat_card import ResourceCard, StatCard


class DashboardView(QScrollArea):
    """Main dashboard view showing cluster overview"""

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._stats = ClusterStats()

        self._setup_ui()
        self._setup_refresh_timer()

    def _setup_ui(self):
        """Setup dashboard UI"""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Main container
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        header = QLabel("Dashboard")
        header.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        layout.addWidget(header)

        subtitle = QLabel("Cluster overview and real-time statistics")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; margin-bottom: 16px;")
        layout.addWidget(subtitle)

        # Stats cards row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)

        self.workers_card = StatCard("Total Workers", "0", "🖥", COLORS["primary"])
        stats_layout.addWidget(self.workers_card)

        self.active_workers_card = StatCard("Active Workers", "0", "✓", COLORS["success"])
        stats_layout.addWidget(self.active_workers_card)

        self.jobs_card = StatCard("Total Jobs", "0", "📋", COLORS["info"])
        stats_layout.addWidget(self.jobs_card)

        self.running_jobs_card = StatCard("Running Jobs", "0", "▶", COLORS["warning"])
        stats_layout.addWidget(self.running_jobs_card)

        layout.addLayout(stats_layout)

        # Job statistics row
        job_stats_layout = QHBoxLayout()
        job_stats_layout.setSpacing(16)

        self.pending_card = StatCard("Pending", "0", "⏳", COLORS["warning"])
        job_stats_layout.addWidget(self.pending_card)

        self.completed_card = StatCard("Completed", "0", "✓", COLORS["success"])
        job_stats_layout.addWidget(self.completed_card)

        self.failed_card = StatCard("Failed", "0", "✗", COLORS["danger"])
        job_stats_layout.addWidget(self.failed_card)

        layout.addLayout(job_stats_layout)

        # Resources section
        resources_label = QLabel("Resource Usage")
        resources_label.setObjectName("section_header")
        resources_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: 600;
            color: {COLORS['text_primary']};
            margin-top: 16px;
        """)
        layout.addWidget(resources_label)

        resources_layout = QHBoxLayout()
        resources_layout.setSpacing(16)

        self.cpu_card = ResourceCard("CPU Cores", 0, 0, "cores")
        resources_layout.addWidget(self.cpu_card)

        self.memory_card = ResourceCard("Memory", 0, 0, "MB")
        resources_layout.addWidget(self.memory_card)

        self.gpu_card = ResourceCard("GPUs", 0, 0, "units")
        resources_layout.addWidget(self.gpu_card)

        layout.addLayout(resources_layout)

        # Health status section
        health_label = QLabel("Cluster Health")
        health_label.setObjectName("section_header")
        health_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: 600;
            color: {COLORS['text_primary']};
            margin-top: 16px;
        """)
        layout.addWidget(health_label)

        self.health_frame = QFrame()
        self.health_frame.setObjectName("stat_card")
        health_layout = QHBoxLayout(self.health_frame)
        health_layout.setContentsMargins(20, 16, 20, 16)

        self.health_indicator = QLabel("●")
        self.health_indicator.setStyleSheet(f"font-size: 24px; color: {COLORS['text_muted']};")
        health_layout.addWidget(self.health_indicator)

        self.health_text = QLabel("Checking cluster health...")
        self.health_text.setStyleSheet(f"font-size: 16px; color: {COLORS['text_secondary']};")
        health_layout.addWidget(self.health_text)

        health_layout.addStretch()

        self.health_details = QLabel("")
        self.health_details.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        health_layout.addWidget(self.health_details)

        layout.addWidget(self.health_frame)

        # Charts section
        charts_label = QLabel("Real-time Metrics")
        charts_label.setObjectName("section_header")
        charts_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: 600;
            color: {COLORS['text_primary']};
            margin-top: 16px;
        """)
        layout.addWidget(charts_label)

        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(16)

        # CPU usage chart
        self.cpu_chart = LineChart(
            title="CPU Usage",
            max_points=60,
            min_value=0,
            max_value=100,
            unit="%",
            color=COLORS["primary"]
        )
        charts_layout.addWidget(self.cpu_chart)

        # Memory usage chart
        self.memory_chart = LineChart(
            title="Memory Usage",
            max_points=60,
            min_value=0,
            max_value=100,
            unit="%",
            color=COLORS["info"]
        )
        charts_layout.addWidget(self.memory_chart)

        layout.addLayout(charts_layout)

        # Jobs distribution section
        distribution_layout = QHBoxLayout()
        distribution_layout.setSpacing(16)

        # Jobs by status donut chart
        self.jobs_donut = DonutChart(title="Jobs by Status")
        distribution_layout.addWidget(self.jobs_donut)

        # Resource allocation bar chart
        self.resource_bar = BarChart(title="Resource Allocation")
        distribution_layout.addWidget(self.resource_bar)

        layout.addLayout(distribution_layout)

        layout.addStretch()

        self.setWidget(container)

        # Initialize history for charts
        self._cpu_history = deque(maxlen=60)
        self._memory_history = deque(maxlen=60)

    def _setup_refresh_timer(self):
        """Setup auto-refresh timer"""
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._request_refresh)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds

    def _request_refresh(self):
        """Request data refresh (to be called from async context)"""
        if self.api_client:
            # This will be handled by the main window's event loop
            pass

    def update_stats(self, stats: ClusterStats):
        """Update dashboard with new statistics"""
        self._stats = stats

        # Update worker cards
        self.workers_card.set_value(str(stats.total_workers))
        self.active_workers_card.set_value(str(stats.active_workers))

        # Update job cards
        self.jobs_card.set_value(str(stats.total_jobs))
        self.running_jobs_card.set_value(str(stats.running_jobs))
        self.pending_card.set_value(str(stats.pending_jobs))
        self.completed_card.set_value(str(stats.completed_jobs))
        self.failed_card.set_value(str(stats.failed_jobs))

        # Update resource cards
        self.cpu_card.set_values(stats.used_cpu, stats.total_cpu)
        self.memory_card.set_values(stats.used_memory, stats.total_memory)
        self.gpu_card.set_values(stats.used_gpu, stats.total_gpu)

        # Update charts
        if stats.total_cpu > 0:
            cpu_percent = (stats.used_cpu / stats.total_cpu) * 100
            self._cpu_history.append(cpu_percent)
            self.cpu_chart.add_value(cpu_percent)

        if stats.total_memory > 0:
            mem_percent = (stats.used_memory / stats.total_memory) * 100
            self._memory_history.append(mem_percent)
            self.memory_chart.add_value(mem_percent)

        # Update jobs donut chart
        self.jobs_donut.set_data([
            ("Running", stats.running_jobs, COLORS["warning"]),
            ("Pending", stats.pending_jobs, COLORS["info"]),
            ("Completed", stats.completed_jobs, COLORS["success"]),
            ("Failed", stats.failed_jobs, COLORS["danger"]),
        ])

        # Update resource bar chart
        self.resource_bar.set_data([
            ("CPU", stats.used_cpu, stats.total_cpu, COLORS["primary"]),
            ("Memory", stats.used_memory / 1024, stats.total_memory / 1024, COLORS["info"]),  # Convert to GB
            ("GPU", stats.used_gpu, max(stats.total_gpu, 1), COLORS["warning"]),
        ])

    def update_health(self, health_data: dict):
        """Update health status display"""
        status = health_data.get("status", "unknown")

        if status == "healthy":
            self.health_indicator.setStyleSheet(f"font-size: 24px; color: {COLORS['success']};")
            self.health_text.setText("Cluster is healthy")
            self.health_text.setStyleSheet(f"font-size: 16px; color: {COLORS['success']};")
        elif status == "degraded":
            self.health_indicator.setStyleSheet(f"font-size: 24px; color: {COLORS['warning']};")
            self.health_text.setText("Cluster is degraded")
            self.health_text.setStyleSheet(f"font-size: 16px; color: {COLORS['warning']};")
        else:
            self.health_indicator.setStyleSheet(f"font-size: 24px; color: {COLORS['danger']};")
            self.health_text.setText("Cluster is unhealthy")
            self.health_text.setStyleSheet(f"font-size: 16px; color: {COLORS['danger']};")

        # Show additional details if available
        details = health_data.get("message", "")
        self.health_details.setText(details)

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
