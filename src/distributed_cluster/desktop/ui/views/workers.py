"""
Fluent Workers View
صفحة العمال بتصميم Fluent

Worker management interface with:
- Worker cards grid
- Worker details
- Resource monitoring
- Actions (enable/disable)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..components import ButtonVariant, FluentButton, FluentCard
from ..dashboard import CircularProgressChart
from ..fluent_design import FluentDesignSystem
from ..titlebar import FluentIcons

# ═══════════════════════════════════════════════════════════════════════════════
# WORKER CARD
# ═══════════════════════════════════════════════════════════════════════════════

class WorkerCard(QFrame):
    """
    Individual worker status card.
    بطاقة حالة العامل الفردي
    """

    clicked = Signal(dict)
    action_requested = Signal(str, dict)

    def __init__(self, worker_data: Dict[str, Any], parent=None):
        super().__init__(parent)

        self._data = worker_data
        self._hovered = False

        self._setup_ui()

    def _setup_ui(self):
        """Setup card UI"""
        colors = FluentDesignSystem().colors

        self.setFixedSize(300, 220)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        status = self._data.get("status", "offline").lower()
        status_colors = {
            "online": colors.success,
            "active": colors.success,
            "busy": colors.warning,
            "offline": colors.text_disabled,
            "error": colors.error,
        }
        accent = status_colors.get(status, colors.text_disabled)

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {colors.bg_card_default};
                border: 1px solid {colors.stroke_surface};
                border-radius: 12px;
            }}
            QFrame:hover {{
                background-color: {colors.bg_card_secondary};
                border-color: {accent};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()

        # Status indicator
        status_dot = QLabel()
        status_dot.setFixedSize(10, 10)
        status_dot.setStyleSheet(f"""
            background-color: {accent};
            border-radius: 5px;
        """)
        header.addWidget(status_dot)

        # Worker name
        name_label = QLabel(self._data.get("name", "Unknown"))
        name_label.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 16px;
            font-weight: 600;
        """)
        header.addWidget(name_label)

        header.addStretch()

        # Status badge
        status_badge = QLabel(status.title())
        status_badge.setStyleSheet(f"""
            background-color: {accent}30;
            color: {accent};
            font-size: 11px;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 4px;
        """)
        header.addWidget(status_badge)

        layout.addLayout(header)

        # Host info
        host_label = QLabel(self._data.get("host", "127.0.0.1"))
        host_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        layout.addWidget(host_label)

        # Resource meters
        resources_layout = QHBoxLayout()
        resources_layout.setSpacing(16)

        # CPU
        cpu_widget = self._create_resource_meter(
            "CPU",
            self._data.get("cpu_percent", 0),
            colors.accent
        )
        resources_layout.addWidget(cpu_widget)

        # Memory
        mem_widget = self._create_resource_meter(
            "Memory",
            self._data.get("memory_percent", 0),
            colors.success
        )
        resources_layout.addWidget(mem_widget)

        # GPU (if available)
        if self._data.get("gpu_count", 0) > 0:
            gpu_widget = self._create_resource_meter(
                "GPU",
                self._data.get("gpu_percent", 0),
                colors.warning
            )
            resources_layout.addWidget(gpu_widget)

        resources_layout.addStretch()
        layout.addLayout(resources_layout)

        # Jobs info
        jobs_layout = QHBoxLayout()

        running_jobs = self._data.get("running_jobs", 0)
        jobs_label = QLabel(f"{running_jobs} active job{'s' if running_jobs != 1 else ''}")
        jobs_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        jobs_layout.addWidget(jobs_label)

        jobs_layout.addStretch()

        # Uptime
        uptime = self._data.get("uptime", "0h")
        uptime_label = QLabel(f"Up: {uptime}")
        uptime_label.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 11px;")
        jobs_layout.addWidget(uptime_label)

        layout.addLayout(jobs_layout)

        # Actions
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        if status == "offline":
            enable_btn = FluentButton("Enable", "", ButtonVariant.ACCENT)
            enable_btn.clicked.connect(lambda: self.action_requested.emit("enable", self._data))
            actions_layout.addWidget(enable_btn)
        else:
            disable_btn = FluentButton("Disable", "", ButtonVariant.SUBTLE)
            disable_btn.clicked.connect(lambda: self.action_requested.emit("disable", self._data))
            actions_layout.addWidget(disable_btn)

        details_btn = FluentButton("", FluentIcons.INFO, ButtonVariant.SUBTLE)
        details_btn.setFixedSize(36, 36)
        details_btn.clicked.connect(lambda: self.clicked.emit(self._data))
        actions_layout.addWidget(details_btn)

        layout.addLayout(actions_layout)

    def _create_resource_meter(self, label: str, percent: float, color: str) -> QWidget:
        """Create a mini resource meter"""
        colors = FluentDesignSystem().colors

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Label
        label_widget = QLabel(label)
        label_widget.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 10px;")
        label_widget.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_widget)

        # Value
        value_widget = QLabel(f"{int(percent)}%")
        value_widget.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 600;")
        value_widget.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_widget)

        return widget

    def update_data(self, data: Dict[str, Any]):
        """Update worker data"""
        self._data = data
        # Would need to refresh UI components

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._data)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# WORKER DETAILS DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class WorkerDetailsPanel(QFrame):
    """
    Worker details panel.
    لوحة تفاصيل العامل
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._worker_data: Optional[Dict[str, Any]] = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        colors = FluentDesignSystem().colors

        self.setMinimumWidth(400)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {colors.bg_card_default};
                border-left: 1px solid {colors.stroke_divider};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Header
        header = QHBoxLayout()

        self._title = QLabel("Worker Details")
        self._title.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 20px;
            font-weight: 600;
        """)
        header.addWidget(self._title)

        header.addStretch()

        close_btn = FluentButton("", FluentIcons.CANCEL, ButtonVariant.SUBTLE)
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(lambda: self.setVisible(False))
        header.addWidget(close_btn)

        layout.addLayout(header)

        # Resource charts
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(20)

        self._cpu_chart = CircularProgressChart("CPU Usage", 0, 100, 100, colors.accent)
        charts_layout.addWidget(self._cpu_chart)

        self._mem_chart = CircularProgressChart("Memory", 0, 100, 100, colors.success)
        charts_layout.addWidget(self._mem_chart)

        self._gpu_chart = CircularProgressChart("GPU", 0, 100, 100, colors.warning)
        charts_layout.addWidget(self._gpu_chart)

        layout.addLayout(charts_layout)

        # Info card
        info_card = FluentCard(title="System Information")

        self._info_labels = {}
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)

        fields = [
            ("Hostname", "hostname"),
            ("IP Address", "host"),
            ("OS", "os"),
            ("CPU Cores", "cpu_count"),
            ("Total Memory", "total_memory"),
            ("GPUs", "gpu_count"),
            ("Uptime", "uptime"),
            ("Jobs Completed", "completed_jobs"),
        ]

        for label, key in fields:
            row = QHBoxLayout()

            label_widget = QLabel(label)
            label_widget.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
            label_widget.setFixedWidth(120)
            row.addWidget(label_widget)

            value_widget = QLabel("-")
            value_widget.setStyleSheet(f"color: {colors.text_primary}; font-size: 13px;")
            row.addWidget(value_widget, 1)

            self._info_labels[key] = value_widget
            info_layout.addLayout(row)

        info_widget = QWidget()
        info_widget.setLayout(info_layout)
        info_card.add_content(info_widget)
        layout.addWidget(info_card)

        layout.addStretch()

    def set_worker(self, data: Dict[str, Any]):
        """Set worker data"""
        self._worker_data = data
        FluentDesignSystem().colors

        self._title.setText(f"Worker: {data.get('name', 'Unknown')}")

        # Update charts
        self._cpu_chart.animate_to(data.get("cpu_percent", 0))
        self._mem_chart.animate_to(data.get("memory_percent", 0))
        self._gpu_chart.animate_to(data.get("gpu_percent", 0))

        # Update info
        for key, label in self._info_labels.items():
            value = data.get(key, "-")
            if value is None:
                value = "-"
            label.setText(str(value))

        self.setVisible(True)


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT WORKERS VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class FluentWorkersView(QWidget):
    """
    Complete workers management view.
    صفحة إدارة العمال الكاملة
    """

    refresh_requested = Signal()
    worker_action = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._worker_cards: List[WorkerCard] = []
        self._setup_ui()
        self._load_demo_data()

    def _setup_ui(self):
        """Setup view UI"""
        colors = FluentDesignSystem().colors

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main content
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()

        title = QLabel("Workers")
        title.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 28px;
            font-weight: 600;
        """)
        header.addWidget(title)

        header.addStretch()

        # Stats
        self._online_label = QLabel("0 online")
        self._online_label.setStyleSheet(f"""
            color: {colors.success};
            font-size: 14px;
            font-weight: 500;
        """)
        header.addWidget(self._online_label)

        self._total_label = QLabel("• 0 total")
        self._total_label.setStyleSheet(f"""
            color: {colors.text_secondary};
            font-size: 14px;
        """)
        header.addWidget(self._total_label)

        # Refresh button
        refresh_btn = FluentButton("", FluentIcons.REFRESH, ButtonVariant.SUBTLE)
        refresh_btn.setFixedSize(36, 36)
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # Workers grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(16)

        scroll.setWidget(self._grid_widget)
        layout.addWidget(scroll, 1)

        main_layout.addWidget(content, 1)

        # Details panel
        self._details_panel = WorkerDetailsPanel()
        self._details_panel.setVisible(False)
        main_layout.addWidget(self._details_panel)

    def _load_demo_data(self):
        """Load demo workers"""
        demo_workers = [
            {
                "id": "worker-01",
                "name": "Worker-01",
                "host": "192.168.1.101",
                "status": "online",
                "cpu_percent": 45,
                "memory_percent": 62,
                "gpu_percent": 78,
                "gpu_count": 2,
                "running_jobs": 2,
                "uptime": "5d 12h",
                "hostname": "gpu-node-01",
                "os": "Ubuntu 22.04",
                "cpu_count": 32,
                "total_memory": "128 GB",
                "completed_jobs": 1247,
            },
            {
                "id": "worker-02",
                "name": "Worker-02",
                "host": "192.168.1.102",
                "status": "busy",
                "cpu_percent": 92,
                "memory_percent": 88,
                "gpu_percent": 95,
                "gpu_count": 4,
                "running_jobs": 4,
                "uptime": "12d 3h",
                "hostname": "gpu-node-02",
                "os": "Ubuntu 22.04",
                "cpu_count": 64,
                "total_memory": "256 GB",
                "completed_jobs": 3421,
            },
            {
                "id": "worker-03",
                "name": "Worker-03",
                "host": "192.168.1.103",
                "status": "online",
                "cpu_percent": 12,
                "memory_percent": 25,
                "gpu_percent": 0,
                "gpu_count": 0,
                "running_jobs": 0,
                "uptime": "2d 8h",
                "hostname": "cpu-node-01",
                "os": "Ubuntu 22.04",
                "cpu_count": 16,
                "total_memory": "64 GB",
                "completed_jobs": 892,
            },
            {
                "id": "worker-04",
                "name": "Worker-04",
                "host": "192.168.1.104",
                "status": "offline",
                "cpu_percent": 0,
                "memory_percent": 0,
                "gpu_percent": 0,
                "gpu_count": 1,
                "running_jobs": 0,
                "uptime": "-",
                "hostname": "gpu-node-03",
                "os": "Ubuntu 22.04",
                "cpu_count": 16,
                "total_memory": "64 GB",
                "completed_jobs": 567,
            },
        ]

        self.set_workers(demo_workers)

    def set_workers(self, workers: List[Dict[str, Any]]):
        """Set workers data"""
        # Clear existing cards
        for card in self._worker_cards:
            card.deleteLater()
        self._worker_cards.clear()

        # Create new cards
        cols = 3
        for i, worker in enumerate(workers):
            card = WorkerCard(worker)
            card.clicked.connect(self._on_worker_clicked)
            card.action_requested.connect(self.worker_action.emit)

            row = i // cols
            col = i % cols
            self._grid_layout.addWidget(card, row, col)
            self._worker_cards.append(card)

        # Update stats
        online = sum(1 for w in workers if w.get("status") in ["online", "busy", "active"])
        self._online_label.setText(f"{online} online")
        self._total_label.setText(f"• {len(workers)} total")

    def _on_worker_clicked(self, data: dict):
        """Handle worker card click"""
        self._details_panel.set_worker(data)

    def update_worker(self, worker_id: str, data: Dict[str, Any]):
        """Update a specific worker"""
        for card in self._worker_cards:
            if card._data.get("id") == worker_id:
                card.update_data(data)
                break
