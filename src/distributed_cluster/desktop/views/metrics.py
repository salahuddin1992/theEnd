"""
Metrics View - Advanced metrics and monitoring page
صفحة المقاييس والمراقبة المتقدمة
"""

from collections import deque
from typing import Optional, Dict, List
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from ..api.client import APIClient
from ..resources.styles import COLORS
from ..widgets.charts import LineChart, DonutChart, BarChart


class MetricCard(QFrame):
    """Card displaying a single metric with sparkline"""

    def __init__(self, title: str, unit: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._unit = unit
        self._history = deque(maxlen=60)
        self._setup_ui()

    def _setup_ui(self):
        """Setup card UI"""
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        self.setMinimumHeight(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()

        title_label = QLabel(self._title)
        title_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 12px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        """)
        header.addWidget(title_label)

        header.addStretch()

        self.change_label = QLabel("")
        self.change_label.setStyleSheet(f"font-size: 11px;")
        header.addWidget(self.change_label)

        layout.addLayout(header)

        # Value
        value_layout = QHBoxLayout()

        self.value_label = QLabel("0")
        self.value_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 28px;
            font-weight: 600;
        """)
        value_layout.addWidget(self.value_label)

        unit_label = QLabel(self._unit)
        unit_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px;")
        value_layout.addWidget(unit_label)

        value_layout.addStretch()

        layout.addLayout(value_layout)

        # Mini sparkline would go here (simplified for now)
        self.trend_label = QLabel("―")
        self.trend_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 18px;")
        layout.addWidget(self.trend_label)

    def set_value(self, value: float):
        """Update metric value"""
        old_value = float(self.value_label.text()) if self.value_label.text().replace('.', '').isdigit() else 0

        self._history.append(value)
        self.value_label.setText(f"{value:.1f}" if isinstance(value, float) else str(value))

        # Calculate change
        if len(self._history) >= 2:
            change = value - self._history[-2]
            if change > 0:
                self.change_label.setText(f"▲ +{change:.1f}")
                self.change_label.setStyleSheet(f"color: {COLORS['success']}; font-size: 11px;")
            elif change < 0:
                self.change_label.setText(f"▼ {change:.1f}")
                self.change_label.setStyleSheet(f"color: {COLORS['danger']}; font-size: 11px;")
            else:
                self.change_label.setText("―")
                self.change_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")

        # Update trend
        if len(self._history) >= 5:
            recent = list(self._history)[-5:]
            if all(recent[i] <= recent[i+1] for i in range(len(recent)-1)):
                self.trend_label.setText("↗ Increasing")
                self.trend_label.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
            elif all(recent[i] >= recent[i+1] for i in range(len(recent)-1)):
                self.trend_label.setText("↘ Decreasing")
                self.trend_label.setStyleSheet(f"color: {COLORS['success']}; font-size: 12px;")
            else:
                self.trend_label.setText("→ Stable")
                self.trend_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")


class MetricsTable(QFrame):
    """Table showing detailed metrics"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Setup table UI"""
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QFrame()
        header.setStyleSheet(f"""
            background-color: {COLORS['bg_medium']};
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            border-bottom: 1px solid {COLORS['border']};
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        title = QLabel("Detailed Metrics")
        title.setStyleSheet(f"font-weight: 600; color: {COLORS['text_primary']};")
        header_layout.addWidget(title)

        header_layout.addStretch()

        layout.addWidget(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Metric", "Current", "Average", "Min", "Max"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: transparent;
                border: none;
            }}
            QTableWidget::item {{
                padding: 8px;
            }}
            QHeaderView::section {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_secondary']};
                padding: 8px;
                border: none;
                font-weight: 600;
            }}
        """)

        layout.addWidget(self.table)

    def set_metrics(self, metrics: List[Dict]):
        """Set metrics data"""
        self.table.setRowCount(len(metrics))

        for row, metric in enumerate(metrics):
            self.table.setItem(row, 0, QTableWidgetItem(metric.get("name", "")))
            self.table.setItem(row, 1, QTableWidgetItem(f"{metric.get('current', 0):.2f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{metric.get('average', 0):.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{metric.get('min', 0):.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{metric.get('max', 0):.2f}"))


class MetricsView(QScrollArea):
    """Advanced metrics and monitoring view"""

    refresh_requested = Signal()

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._setup_ui()

    def _setup_ui(self):
        """Setup metrics view UI"""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("Metrics & Monitoring")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Time range selector
        time_label = QLabel("Time Range:")
        time_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        header_layout.addWidget(time_label)

        self.time_combo = QComboBox()
        self.time_combo.addItems(["Last 5 minutes", "Last 15 minutes", "Last 1 hour", "Last 24 hours"])
        header_layout.addWidget(self.time_combo)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondary_button")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        header_layout.addWidget(refresh_btn)

        layout.addLayout(header_layout)

        # Overview metrics cards
        cards_layout = QGridLayout()
        cards_layout.setSpacing(16)

        self.cpu_card = MetricCard("CPU Usage", "%")
        cards_layout.addWidget(self.cpu_card, 0, 0)

        self.memory_card = MetricCard("Memory Usage", "%")
        cards_layout.addWidget(self.memory_card, 0, 1)

        self.jobs_rate_card = MetricCard("Jobs/min", "")
        cards_layout.addWidget(self.jobs_rate_card, 0, 2)

        self.success_rate_card = MetricCard("Success Rate", "%")
        cards_layout.addWidget(self.success_rate_card, 0, 3)

        self.workers_card = MetricCard("Active Workers", "")
        cards_layout.addWidget(self.workers_card, 1, 0)

        self.queue_card = MetricCard("Queue Depth", "")
        cards_layout.addWidget(self.queue_card, 1, 1)

        self.latency_card = MetricCard("Avg Latency", "ms")
        cards_layout.addWidget(self.latency_card, 1, 2)

        self.throughput_card = MetricCard("Throughput", "MB/s")
        cards_layout.addWidget(self.throughput_card, 1, 3)

        layout.addLayout(cards_layout)

        # Tabs for different metric views
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                background-color: {COLORS['bg_card']};
            }}
            QTabBar::tab {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_secondary']};
                padding: 10px 20px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            QTabBar::tab:selected {{
                background-color: {COLORS['bg_card']};
                color: {COLORS['text_primary']};
            }}
        """)

        # Resource charts tab
        resource_tab = QWidget()
        resource_layout = QVBoxLayout(resource_tab)
        resource_layout.setContentsMargins(16, 16, 16, 16)

        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)

        self.cpu_chart = LineChart("CPU Usage Over Time", 120, 0, 100, "%", COLORS["primary"])
        charts_row.addWidget(self.cpu_chart)

        self.memory_chart = LineChart("Memory Usage Over Time", 120, 0, 100, "%", COLORS["info"])
        charts_row.addWidget(self.memory_chart)

        resource_layout.addLayout(charts_row)

        tabs.addTab(resource_tab, "Resources")

        # Jobs metrics tab
        jobs_tab = QWidget()
        jobs_layout = QVBoxLayout(jobs_tab)
        jobs_layout.setContentsMargins(16, 16, 16, 16)

        jobs_charts = QHBoxLayout()
        jobs_charts.setSpacing(16)

        self.jobs_chart = LineChart("Jobs Over Time", 120, 0, 100, "", COLORS["warning"])
        jobs_charts.addWidget(self.jobs_chart)

        self.jobs_donut = DonutChart("Jobs by Status")
        jobs_charts.addWidget(self.jobs_donut)

        jobs_layout.addLayout(jobs_charts)

        tabs.addTab(jobs_tab, "Jobs")

        # Workers metrics tab
        workers_tab = QWidget()
        workers_layout = QVBoxLayout(workers_tab)
        workers_layout.setContentsMargins(16, 16, 16, 16)

        self.workers_bar = BarChart("Worker Resource Usage")
        workers_layout.addWidget(self.workers_bar)

        tabs.addTab(workers_tab, "Workers")

        # Network metrics tab
        network_tab = QWidget()
        network_layout = QVBoxLayout(network_tab)
        network_layout.setContentsMargins(16, 16, 16, 16)

        network_charts = QHBoxLayout()
        network_charts.setSpacing(16)

        self.network_in_chart = LineChart("Network In", 120, 0, 100, "MB/s", COLORS["success"])
        network_charts.addWidget(self.network_in_chart)

        self.network_out_chart = LineChart("Network Out", 120, 0, 100, "MB/s", COLORS["danger"])
        network_charts.addWidget(self.network_out_chart)

        network_layout.addLayout(network_charts)

        tabs.addTab(network_tab, "Network")

        layout.addWidget(tabs)

        # Detailed metrics table
        self.metrics_table = MetricsTable()
        layout.addWidget(self.metrics_table)

        self.setWidget(container)

    def update_metrics(self, metrics: dict):
        """Update all metrics displays"""
        # Update cards
        self.cpu_card.set_value(metrics.get("cpu_percent", 0))
        self.memory_card.set_value(metrics.get("memory_percent", 0))
        self.jobs_rate_card.set_value(metrics.get("jobs_per_minute", 0))
        self.success_rate_card.set_value(metrics.get("success_rate", 0))
        self.workers_card.set_value(metrics.get("active_workers", 0))
        self.queue_card.set_value(metrics.get("queue_depth", 0))
        self.latency_card.set_value(metrics.get("avg_latency", 0))
        self.throughput_card.set_value(metrics.get("throughput", 0))

        # Update charts
        self.cpu_chart.add_value(metrics.get("cpu_percent", 0))
        self.memory_chart.add_value(metrics.get("memory_percent", 0))
        self.jobs_chart.add_value(metrics.get("running_jobs", 0))

        # Update donut chart
        self.jobs_donut.set_data([
            ("Running", metrics.get("running_jobs", 0), COLORS["warning"]),
            ("Pending", metrics.get("pending_jobs", 0), COLORS["info"]),
            ("Completed", metrics.get("completed_jobs", 0), COLORS["success"]),
            ("Failed", metrics.get("failed_jobs", 0), COLORS["danger"]),
        ])

        # Update workers bar chart
        workers = metrics.get("workers", [])
        if workers:
            self.workers_bar.set_data([
                (w.get("id", "")[:8], w.get("cpu_used", 0), w.get("cpu_total", 100), COLORS["primary"])
                for w in workers[:5]
            ])

        # Update table
        table_metrics = [
            {"name": "CPU Usage", "current": metrics.get("cpu_percent", 0), "average": metrics.get("cpu_avg", 0), "min": metrics.get("cpu_min", 0), "max": metrics.get("cpu_max", 0)},
            {"name": "Memory Usage", "current": metrics.get("memory_percent", 0), "average": metrics.get("memory_avg", 0), "min": metrics.get("memory_min", 0), "max": metrics.get("memory_max", 0)},
            {"name": "Jobs/Minute", "current": metrics.get("jobs_per_minute", 0), "average": metrics.get("jobs_avg", 0), "min": metrics.get("jobs_min", 0), "max": metrics.get("jobs_max", 0)},
            {"name": "Latency (ms)", "current": metrics.get("avg_latency", 0), "average": metrics.get("latency_avg", 0), "min": metrics.get("latency_min", 0), "max": metrics.get("latency_max", 0)},
        ]
        self.metrics_table.set_metrics(table_metrics)

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
