"""
Workers View - Worker management page
صفحة إدارة العمال
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..api.client import APIClient
from ..resources.styles import COLORS, get_status_color
from ..widgets.data_table import DataTable


class WorkerDetailPanel(QFrame):
    """Panel showing worker details"""

    drain_requested = Signal(str)
    undrain_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stat_card")
        self._current_worker = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()
        self.title_label = QLabel("Worker Details")
        self.title_label.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {COLORS['text_primary']};")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.status_label = QLabel("")
        header_layout.addWidget(self.status_label)

        layout.addLayout(header_layout)

        # Tabs
        tabs = QTabWidget()

        # Info tab
        info_widget = QWidget()
        info_layout = QFormLayout(info_widget)
        info_layout.setSpacing(8)

        self.id_label = QLabel("-")
        info_layout.addRow("ID:", self.id_label)

        self.hostname_label = QLabel("-")
        info_layout.addRow("Hostname:", self.hostname_label)

        self.address_label = QLabel("-")
        info_layout.addRow("Address:", self.address_label)

        self.registered_label = QLabel("-")
        info_layout.addRow("Registered:", self.registered_label)

        self.heartbeat_label = QLabel("-")
        info_layout.addRow("Last Heartbeat:", self.heartbeat_label)

        self.tags_label = QLabel("-")
        self.tags_label.setWordWrap(True)
        info_layout.addRow("Tags:", self.tags_label)

        tabs.addTab(info_widget, "Info")

        # Resources tab
        resources_widget = QWidget()
        resources_layout = QVBoxLayout(resources_widget)
        resources_layout.setSpacing(16)

        # CPU
        cpu_frame = QFrame()
        cpu_layout = QVBoxLayout(cpu_frame)
        cpu_layout.setContentsMargins(0, 0, 0, 0)
        cpu_header = QHBoxLayout()
        cpu_header.addWidget(QLabel("CPU"))
        self.cpu_value_label = QLabel("-")
        self.cpu_value_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        cpu_header.addWidget(self.cpu_value_label)
        cpu_header.addStretch()
        cpu_layout.addLayout(cpu_header)
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setFixedHeight(8)
        self.cpu_progress.setTextVisible(False)
        cpu_layout.addWidget(self.cpu_progress)
        resources_layout.addWidget(cpu_frame)

        # Memory
        mem_frame = QFrame()
        mem_layout = QVBoxLayout(mem_frame)
        mem_layout.setContentsMargins(0, 0, 0, 0)
        mem_header = QHBoxLayout()
        mem_header.addWidget(QLabel("Memory"))
        self.mem_value_label = QLabel("-")
        self.mem_value_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        mem_header.addWidget(self.mem_value_label)
        mem_header.addStretch()
        mem_layout.addLayout(mem_header)
        self.mem_progress = QProgressBar()
        self.mem_progress.setFixedHeight(8)
        self.mem_progress.setTextVisible(False)
        mem_layout.addWidget(self.mem_progress)
        resources_layout.addWidget(mem_frame)

        # GPU
        gpu_frame = QFrame()
        gpu_layout = QVBoxLayout(gpu_frame)
        gpu_layout.setContentsMargins(0, 0, 0, 0)
        gpu_header = QHBoxLayout()
        gpu_header.addWidget(QLabel("GPU"))
        self.gpu_value_label = QLabel("-")
        self.gpu_value_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        gpu_header.addWidget(self.gpu_value_label)
        gpu_header.addStretch()
        gpu_layout.addLayout(gpu_header)
        self.gpu_progress = QProgressBar()
        self.gpu_progress.setFixedHeight(8)
        self.gpu_progress.setTextVisible(False)
        gpu_layout.addWidget(self.gpu_progress)
        resources_layout.addWidget(gpu_frame)

        resources_layout.addStretch()
        tabs.addTab(resources_widget, "Resources")

        # Jobs tab
        jobs_widget = QWidget()
        jobs_layout = QVBoxLayout(jobs_widget)
        jobs_layout.setContentsMargins(0, 8, 0, 0)

        self.running_jobs_label = QLabel("Running Jobs: 0")
        self.running_jobs_label.setStyleSheet("font-weight: 600;")
        jobs_layout.addWidget(self.running_jobs_label)

        self.completed_jobs_label = QLabel("Completed Jobs: 0")
        jobs_layout.addWidget(self.completed_jobs_label)

        self.failed_jobs_label = QLabel("Failed Jobs: 0")
        jobs_layout.addWidget(self.failed_jobs_label)

        jobs_layout.addStretch()
        tabs.addTab(jobs_widget, "Jobs")

        layout.addWidget(tabs)

        # Actions
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()

        self.drain_btn = QPushButton("Drain")
        self.drain_btn.setObjectName("secondary_button")
        self.drain_btn.clicked.connect(self._on_drain)
        actions_layout.addWidget(self.drain_btn)

        self.undrain_btn = QPushButton("Undrain")
        self.undrain_btn.setObjectName("success_button")
        self.undrain_btn.clicked.connect(self._on_undrain)
        actions_layout.addWidget(self.undrain_btn)

        layout.addLayout(actions_layout)

    def set_worker(self, worker: dict):
        """Display worker details"""
        self._current_worker = worker

        self.id_label.setText(worker.get("id", "-"))
        self.hostname_label.setText(worker.get("hostname", "-"))
        self.address_label.setText(worker.get("address", "-"))
        self.registered_label.setText(worker.get("registered_at", "-"))
        self.heartbeat_label.setText(worker.get("last_heartbeat", "-"))

        # Tags
        tags = worker.get("tags", [])
        self.tags_label.setText(", ".join(tags) if tags else "None")

        # Status
        status = worker.get("status", "unknown")
        color = get_status_color(status)
        self.status_label.setText(status.upper())
        self.status_label.setStyleSheet(
            f"""
            color: {color};
            font-weight: 600;
            padding: 4px 12px;
            border-radius: 4px;
            background-color: {color}20;
        """
        )

        # Resources
        resources = worker.get("resources", {})
        usage = worker.get("usage", {})

        # CPU
        total_cpu = resources.get("cpu_cores", 0)
        used_cpu = usage.get("cpu_cores", 0)
        self.cpu_value_label.setText(f"{used_cpu}/{total_cpu} cores")
        cpu_percent = int((used_cpu / total_cpu * 100) if total_cpu > 0 else 0)
        self.cpu_progress.setValue(cpu_percent)

        # Memory
        total_mem = resources.get("memory_mb", 0)
        used_mem = usage.get("memory_mb", 0)
        self.mem_value_label.setText(f"{used_mem}/{total_mem} MB")
        mem_percent = int((used_mem / total_mem * 100) if total_mem > 0 else 0)
        self.mem_progress.setValue(mem_percent)

        # GPU
        total_gpu = resources.get("gpu_count", 0)
        used_gpu = usage.get("gpu_count", 0)
        self.gpu_value_label.setText(f"{used_gpu}/{total_gpu} units")
        gpu_percent = int((used_gpu / total_gpu * 100) if total_gpu > 0 else 0)
        self.gpu_progress.setValue(gpu_percent)

        # Jobs stats
        stats = worker.get("stats", {})
        self.running_jobs_label.setText(f"Running Jobs: {stats.get('running_jobs', 0)}")
        self.completed_jobs_label.setText(f"Completed Jobs: {stats.get('completed_jobs', 0)}")
        self.failed_jobs_label.setText(f"Failed Jobs: {stats.get('failed_jobs', 0)}")

        # Enable/disable actions based on status
        is_draining = status == "draining"
        self.drain_btn.setEnabled(not is_draining and status == "active")
        self.undrain_btn.setEnabled(is_draining)

    def clear(self):
        """Clear worker details"""
        self._current_worker = None
        self.id_label.setText("-")
        self.hostname_label.setText("-")
        self.address_label.setText("-")
        self.registered_label.setText("-")
        self.heartbeat_label.setText("-")
        self.tags_label.setText("-")
        self.status_label.setText("")
        self.cpu_value_label.setText("-")
        self.mem_value_label.setText("-")
        self.gpu_value_label.setText("-")
        self.cpu_progress.setValue(0)
        self.mem_progress.setValue(0)
        self.gpu_progress.setValue(0)
        self.running_jobs_label.setText("Running Jobs: 0")
        self.completed_jobs_label.setText("Completed Jobs: 0")
        self.failed_jobs_label.setText("Failed Jobs: 0")

    def _on_drain(self):
        """Handle drain button click"""
        if self._current_worker:
            self.drain_requested.emit(self._current_worker.get("id"))

    def _on_undrain(self):
        """Handle undrain button click"""
        if self._current_worker:
            self.undrain_requested.emit(self._current_worker.get("id"))


class WorkersView(QWidget):
    """Workers management view"""

    refresh_requested = Signal()

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._setup_ui()

    def _setup_ui(self):
        """Setup workers view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("Workers")
        title.setStyleSheet(
            f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """
        )
        header_layout.addWidget(title)

        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Stats row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)

        self.total_label = self._create_stat_label("Total", "0")
        stats_layout.addWidget(self.total_label)

        self.active_label = self._create_stat_label("Active", "0", COLORS["success"])
        stats_layout.addWidget(self.active_label)

        self.draining_label = self._create_stat_label("Draining", "0", COLORS["warning"])
        stats_layout.addWidget(self.draining_label)

        self.offline_label = self._create_stat_label("Offline", "0", COLORS["danger"])
        stats_layout.addWidget(self.offline_label)

        stats_layout.addStretch()

        layout.addLayout(stats_layout)

        # Splitter for table and details
        splitter = QSplitter(Qt.Horizontal)

        # Workers table
        self.workers_table = DataTable(
            [
                ("ID", "id", 120),
                ("Hostname", "hostname", 150),
                ("Status", "status", 100),
                ("CPU", "cpu_display", 100),
                ("Memory", "memory_display", 100),
                ("GPU", "gpu_display", 80),
                ("Jobs", "running_jobs", 80),
            ]
        )
        self.workers_table.set_status_column("status")
        self.workers_table.row_selected.connect(self._on_worker_selected)
        self.workers_table.refresh_btn.clicked.connect(self._on_refresh)
        splitter.addWidget(self.workers_table)

        # Detail panel
        self.detail_panel = WorkerDetailPanel()
        self.detail_panel.drain_requested.connect(self._on_drain_worker)
        self.detail_panel.undrain_requested.connect(self._on_undrain_worker)
        splitter.addWidget(self.detail_panel)

        splitter.setSizes([600, 400])
        layout.addWidget(splitter)

    def _create_stat_label(self, title: str, value: str, color: str = None) -> QFrame:
        """Create a stat display label"""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        title_label = QLabel(f"{title}:")
        title_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setObjectName(f"{title.lower()}_value")
        if color:
            value_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        else:
            value_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-weight: 600;")
        layout.addWidget(value_label)

        return frame

    def set_workers(self, workers: list):
        """Update workers list"""
        # Transform data for display
        display_data = []
        stats = {"total": 0, "active": 0, "draining": 0, "offline": 0}

        for worker in workers:
            resources = worker.get("resources", {})
            usage = worker.get("usage", {})
            status = worker.get("status", "unknown")

            # Count stats
            stats["total"] += 1
            if status == "active":
                stats["active"] += 1
            elif status == "draining":
                stats["draining"] += 1
            elif status in ("offline", "unhealthy"):
                stats["offline"] += 1

            display_data.append(
                {
                    **worker,
                    "cpu_display": f"{usage.get('cpu_cores', 0)}/{resources.get('cpu_cores', 0)}",
                    "memory_display": f"{usage.get('memory_mb', 0)}/{resources.get('memory_mb', 0)}",
                    "gpu_display": f"{usage.get('gpu_count', 0)}/{resources.get('gpu_count', 0)}",
                    "running_jobs": worker.get("stats", {}).get("running_jobs", 0),
                }
            )

        self.workers_table.set_data(display_data)

        # Update stats labels
        self._update_stat_value("total", str(stats["total"]))
        self._update_stat_value("active", str(stats["active"]))
        self._update_stat_value("draining", str(stats["draining"]))
        self._update_stat_value("offline", str(stats["offline"]))

    def _update_stat_value(self, name: str, value: str):
        """Update a stat label value"""
        label = self.findChild(QLabel, f"{name}_value")
        if label:
            label.setText(value)

    def _on_worker_selected(self, row_idx: int, worker_data: dict):
        """Handle worker selection"""
        self.detail_panel.set_worker(worker_data)

    def _on_refresh(self):
        """Handle refresh button click"""
        self.refresh_requested.emit()

    def _on_drain_worker(self, worker_id: str):
        """Handle drain worker request"""
        reply = QMessageBox.question(
            self,
            "Drain Worker",
            f"Are you sure you want to drain worker {worker_id}?\n" "The worker will stop accepting new jobs.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # Drain via API client
            pass

    def _on_undrain_worker(self, worker_id: str):
        """Handle undrain worker request"""
        # Undrain via API client
        pass

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
