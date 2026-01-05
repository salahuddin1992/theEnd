"""
Fluent Metrics View
صفحة المقاييس بتصميم Fluent

Real-time metrics dashboard with:
- Performance charts
- Resource usage
- Job statistics
- Cluster health
"""

from __future__ import annotations

import random
from typing import Any, Dict, List

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..components import ButtonVariant, FluentButton, FluentCard
from ..dashboard import AnimatedStatCard, CircularProgressChart, LineChart
from ..fluent_design import FluentDesignSystem
from ..titlebar import FluentIcons

# ═══════════════════════════════════════════════════════════════════════════════
# METRIC CHART CARD
# ═══════════════════════════════════════════════════════════════════════════════


class MetricChartCard(FluentCard):
    """A card containing a line chart for metrics"""

    def __init__(self, title: str, color: str = None, parent=None):
        super().__init__(title=title, parent=parent)

        colors = FluentDesignSystem().colors
        self._color = color or colors.accent

        self._chart = LineChart(color=self._color)
        self._chart.setMinimumHeight(120)
        self.add_content(self._chart)

    def set_data(self, data: List[float]):
        """Set chart data"""
        self._chart.set_data(data)

    def update_value(self, value: float):
        """Add a new value to the chart"""
        # Would append to existing data
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT METRICS VIEW
# ═══════════════════════════════════════════════════════════════════════════════


class FluentMetricsView(QWidget):
    """
    Complete metrics dashboard.
    لوحة المقاييس الكاملة
    """

    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()
        self._start_demo_updates()

    def _setup_ui(self):
        """Setup view UI"""
        colors = FluentDesignSystem().colors

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background: {colors.bg_mica_base};")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Header
        header = QHBoxLayout()

        title = QLabel("Metrics")
        title.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 28px;
            font-weight: 600;
        """
        )
        header.addWidget(title)

        header.addStretch()

        # Time range
        range_label = QLabel("Time range:")
        range_label.setStyleSheet(f"color: {colors.text_secondary};")
        header.addWidget(range_label)

        range_combo = QComboBox()
        range_combo.addItems(["Last hour", "Last 6 hours", "Last 24 hours", "Last 7 days"])
        range_combo.setMinimumWidth(140)
        range_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 6px 12px;
            }}
        """
        )
        header.addWidget(range_combo)

        # Refresh
        refresh_btn = FluentButton("", FluentIcons.REFRESH, ButtonVariant.SUBTLE)
        refresh_btn.setFixedSize(36, 36)
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # Stats row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)

        self._jobs_card = AnimatedStatCard("Jobs/Hour", 0, icon=FluentIcons.JOBS, color=colors.accent)
        stats_layout.addWidget(self._jobs_card)

        self._success_card = AnimatedStatCard("Success Rate", 0, icon=FluentIcons.CHECKMARK, color=colors.success)
        stats_layout.addWidget(self._success_card)

        self._latency_card = AnimatedStatCard("Avg Latency", 0, icon="\ue916", color=colors.info)  # Timer
        stats_layout.addWidget(self._latency_card)

        self._throughput_card = AnimatedStatCard("Throughput", 0, icon="\ue9d9", color=colors.warning)  # Chart
        stats_layout.addWidget(self._throughput_card)

        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        # Charts row 1
        charts1_layout = QHBoxLayout()
        charts1_layout.setSpacing(16)

        self._cpu_chart = MetricChartCard("CPU Usage (%)", colors.accent)
        charts1_layout.addWidget(self._cpu_chart, 1)

        self._memory_chart = MetricChartCard("Memory Usage (%)", colors.success)
        charts1_layout.addWidget(self._memory_chart, 1)

        layout.addLayout(charts1_layout)

        # Charts row 2
        charts2_layout = QHBoxLayout()
        charts2_layout.setSpacing(16)

        self._jobs_chart = MetricChartCard("Jobs Over Time", colors.info)
        charts2_layout.addWidget(self._jobs_chart, 1)

        self._queue_chart = MetricChartCard("Queue Depth", colors.warning)
        charts2_layout.addWidget(self._queue_chart, 1)

        layout.addLayout(charts2_layout)

        # System health section
        health_title = QLabel("System Health")
        health_title.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 20px;
            font-weight: 600;
        """
        )
        layout.addWidget(health_title)

        health_layout = QHBoxLayout()
        health_layout.setSpacing(16)

        # Health gauges
        self._overall_health = CircularProgressChart("Overall", 0, 100, 120, colors.success)
        health_layout.addWidget(self._overall_health)

        self._network_health = CircularProgressChart("Network", 0, 100, 120, colors.info)
        health_layout.addWidget(self._network_health)

        self._storage_health = CircularProgressChart("Storage", 0, 100, 120, colors.warning)
        health_layout.addWidget(self._storage_health)

        health_layout.addStretch()
        layout.addLayout(health_layout)

        layout.addStretch()

        scroll.setWidget(container)

        # Set scroll as main widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        # Initialize with demo data
        self._load_demo_data()

    def _load_demo_data(self):
        """Load demo data"""
        # Stats
        self._jobs_card.set_value(127)
        self._success_card.set_value(94)
        self._latency_card.set_value(245)
        self._throughput_card.set_value(1847)

        # Generate chart data
        cpu_data = [random.randint(30, 70) for _ in range(20)]
        memory_data = [random.randint(50, 80) for _ in range(20)]
        jobs_data = [random.randint(10, 50) for _ in range(20)]
        queue_data = [random.randint(5, 25) for _ in range(20)]

        self._cpu_chart.set_data(cpu_data)
        self._memory_chart.set_data(memory_data)
        self._jobs_chart.set_data(jobs_data)
        self._queue_chart.set_data(queue_data)

        # Health
        self._overall_health.animate_to(92)
        self._network_health.animate_to(98)
        self._storage_health.animate_to(67)

    def _start_demo_updates(self):
        """Start demo update timer"""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_demo)
        self._timer.start(3000)  # Update every 3 seconds

    def _update_demo(self):
        """Update with random demo data"""
        # Update stats with small changes
        current = self._jobs_card._target_value
        self._jobs_card.animate_to(current + random.randint(-5, 10))

        # Update health
        self._overall_health.animate_to(random.randint(85, 98))

    def update_metrics(self, metrics: Dict[str, Any]):
        """Update metrics from real data"""
        if "jobs_per_hour" in metrics:
            self._jobs_card.set_value(metrics["jobs_per_hour"])
        if "success_rate" in metrics:
            self._success_card.set_value(int(metrics["success_rate"]))
        if "avg_latency" in metrics:
            self._latency_card.set_value(int(metrics["avg_latency"]))
        if "throughput" in metrics:
            self._throughput_card.set_value(metrics["throughput"])
