"""
Fluent Jobs View
صفحة المهام بتصميم Fluent

Complete job management interface with:
- Job list with filtering
- Job details panel
- Job submission dialog
- Real-time status updates
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSplitter, QScrollArea, QDialog, QTextEdit, QSpinBox, QComboBox, QTabWidget, QPlainTextEdit
)

from ..fluent_design import FluentDesignSystem
from ..components import (
    FluentButton, FluentCard, FluentInput, FluentBadge,
    FluentProgressRing, ButtonVariant
)
from ..data_table import FluentDataTable, Column, ColumnType
from ..titlebar import FluentIcons


# ═══════════════════════════════════════════════════════════════════════════════
# JOB DETAILS PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class JobDetailsPanel(QFrame):
    """
    Job details side panel.
    لوحة تفاصيل المهمة الجانبية
    """

    action_requested = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._job_data: Optional[Dict[str, Any]] = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        colors = FluentDesignSystem().colors

        self.setMinimumWidth(350)
        self.setMaximumWidth(400)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {colors.bg_card_default};
                border-left: 1px solid {colors.stroke_divider};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()

        self._title_label = QLabel("Job Details")
        self._title_label.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 18px;
            font-weight: 600;
        """)
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        close_btn = FluentButton("", FluentIcons.CANCEL, ButtonVariant.SUBTLE)
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(lambda: self.setVisible(False))
        header_layout.addWidget(close_btn)

        layout.addLayout(header_layout)

        # Status
        self._status_container = QWidget()
        status_layout = QHBoxLayout(self._status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)

        self._status_badge = FluentBadge("Unknown")
        status_layout.addWidget(self._status_badge)
        status_layout.addStretch()

        self._progress_ring = FluentProgressRing(24, 2)
        self._progress_ring.setVisible(False)
        status_layout.addWidget(self._progress_ring)

        layout.addWidget(self._status_container)

        # Info grid
        info_card = FluentCard()
        info_layout = QVBoxLayout()
        info_layout.setSpacing(12)

        self._info_fields = {}
        fields = [
            ("ID", "id"),
            ("Name", "name"),
            ("Command", "command"),
            ("Worker", "worker"),
            ("Priority", "priority"),
            ("Created", "created_at"),
            ("Started", "started_at"),
            ("Duration", "duration"),
        ]

        for label, key in fields:
            field_layout = QHBoxLayout()

            field_label = QLabel(label)
            field_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
            field_label.setFixedWidth(80)
            field_layout.addWidget(field_label)

            field_value = QLabel("-")
            field_value.setStyleSheet(f"color: {colors.text_primary}; font-size: 13px;")
            field_value.setWordWrap(True)
            field_layout.addWidget(field_value, 1)

            self._info_fields[key] = field_value
            info_layout.addLayout(field_layout)

        info_card.add_content(QWidget())
        info_card._content_layout.addLayout(info_layout)
        layout.addWidget(info_card)

        # Output tabs
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background-color: {colors.bg_solid_secondary};
                border: 1px solid {colors.stroke_surface};
                border-radius: 8px;
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {colors.text_secondary};
                padding: 8px 16px;
                border: none;
            }}
            QTabBar::tab:selected {{
                color: {colors.text_primary};
                border-bottom: 2px solid {colors.accent};
            }}
        """)

        # Stdout
        self._stdout_text = QPlainTextEdit()
        self._stdout_text.setReadOnly(True)
        self._stdout_text.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {colors.bg_solid_base};
                color: {colors.text_primary};
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 12px;
                border: none;
                padding: 12px;
            }}
        """)
        tabs.addTab(self._stdout_text, "Output")

        # Stderr
        self._stderr_text = QPlainTextEdit()
        self._stderr_text.setReadOnly(True)
        self._stderr_text.setStyleSheet(self._stdout_text.styleSheet())
        tabs.addTab(self._stderr_text, "Errors")

        layout.addWidget(tabs, 1)

        # Action buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self._cancel_btn = FluentButton("Cancel Job", "", ButtonVariant.DANGER)
        self._cancel_btn.clicked.connect(lambda: self._emit_action("cancel"))
        actions_layout.addWidget(self._cancel_btn)

        self._retry_btn = FluentButton("Retry", "", ButtonVariant.DEFAULT)
        self._retry_btn.clicked.connect(lambda: self._emit_action("retry"))
        actions_layout.addWidget(self._retry_btn)

        layout.addLayout(actions_layout)

    def _emit_action(self, action: str):
        """Emit action signal"""
        if self._job_data:
            self.action_requested.emit(action, self._job_data)

    def set_job(self, job_data: Dict[str, Any]):
        """Set job data to display"""
        self._job_data = job_data
        colors = FluentDesignSystem().colors

        # Update title
        job_name = job_data.get("name", job_data.get("id", "Unknown"))
        self._title_label.setText(f"Job: {job_name}")

        # Update status
        status = job_data.get("status", "unknown").lower()
        self._status_badge.setText(status.title())

        # Update badge style manually
        status_colors = {
            "running": colors.info,
            "completed": colors.success,
            "failed": colors.error,
            "pending": colors.warning,
        }
        color = status_colors.get(status, colors.text_secondary)
        self._status_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {color}30;
                color: {color};
                font-size: 12px;
                font-weight: 600;
                padding: 4px 12px;
                border-radius: 4px;
            }}
        """)

        # Show progress for running jobs
        self._progress_ring.setVisible(status == "running")

        # Update info fields
        for key, label in self._info_fields.items():
            value = job_data.get(key, "-")
            if value is None:
                value = "-"
            elif isinstance(value, datetime):
                value = value.strftime("%Y-%m-%d %H:%M:%S")
            label.setText(str(value))

        # Update output
        self._stdout_text.setPlainText(job_data.get("stdout", ""))
        self._stderr_text.setPlainText(job_data.get("stderr", ""))

        # Update button states
        self._cancel_btn.setEnabled(status in ["running", "pending"])
        self._retry_btn.setEnabled(status == "failed")

        self.setVisible(True)


# ═══════════════════════════════════════════════════════════════════════════════
# JOB SUBMISSION DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class JobSubmitDialog(QDialog):
    """
    Job submission dialog.
    حوار إرسال المهمة
    """

    job_submitted = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Submit New Job")
        self.setMinimumSize(500, 600)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI"""
        colors = FluentDesignSystem().colors

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {colors.bg_mica_base};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Header
        header = QLabel("Submit New Job")
        header.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 24px;
            font-weight: 600;
        """)
        layout.addWidget(header)

        # Form
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QFrame.NoFrame)
        form_scroll.setStyleSheet("background: transparent;")

        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setSpacing(16)

        # Job name
        self._name_input = FluentInput("Job Name", "Enter a name for this job")
        form_layout.addWidget(self._name_input)

        # Command
        command_label = QLabel("Command")
        command_label.setStyleSheet(f"color: {colors.text_primary}; font-size: 14px; font-weight: 500;")
        form_layout.addWidget(command_label)

        self._command_input = QTextEdit()
        self._command_input.setPlaceholderText("Enter command to execute...")
        self._command_input.setMinimumHeight(100)
        self._command_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 12px;
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 13px;
            }}
            QTextEdit:focus {{
                border-color: {colors.accent};
            }}
        """)
        form_layout.addWidget(self._command_input)

        # Docker image
        self._image_input = FluentInput("Docker Image (optional)", "e.g., python:3.10")
        form_layout.addWidget(self._image_input)

        # Resource requirements
        resources_card = FluentCard(title="Resource Requirements")

        res_layout = QHBoxLayout()
        res_layout.setSpacing(16)

        # CPU
        cpu_layout = QVBoxLayout()
        cpu_label = QLabel("CPU Cores")
        cpu_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        cpu_layout.addWidget(cpu_label)

        self._cpu_spin = QSpinBox()
        self._cpu_spin.setRange(1, 128)
        self._cpu_spin.setValue(1)
        self._cpu_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
                min-width: 80px;
            }}
        """)
        cpu_layout.addWidget(self._cpu_spin)
        res_layout.addLayout(cpu_layout)

        # Memory
        mem_layout = QVBoxLayout()
        mem_label = QLabel("Memory (GB)")
        mem_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        mem_layout.addWidget(mem_label)

        self._memory_spin = QSpinBox()
        self._memory_spin.setRange(1, 512)
        self._memory_spin.setValue(4)
        self._memory_spin.setStyleSheet(self._cpu_spin.styleSheet())
        mem_layout.addWidget(self._memory_spin)
        res_layout.addLayout(mem_layout)

        # GPU
        gpu_layout = QVBoxLayout()
        gpu_label = QLabel("GPUs")
        gpu_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        gpu_layout.addWidget(gpu_label)

        self._gpu_spin = QSpinBox()
        self._gpu_spin.setRange(0, 8)
        self._gpu_spin.setValue(0)
        self._gpu_spin.setStyleSheet(self._cpu_spin.styleSheet())
        gpu_layout.addWidget(self._gpu_spin)
        res_layout.addLayout(gpu_layout)

        res_layout.addStretch()

        res_widget = QWidget()
        res_widget.setLayout(res_layout)
        resources_card.add_content(res_widget)
        form_layout.addWidget(resources_card)

        # Priority
        priority_layout = QHBoxLayout()

        priority_label = QLabel("Priority")
        priority_label.setStyleSheet(f"color: {colors.text_primary}; font-size: 14px; font-weight: 500;")
        priority_layout.addWidget(priority_label)

        self._priority_combo = QComboBox()
        self._priority_combo.addItems(["Low", "Normal", "High", "Critical"])
        self._priority_combo.setCurrentIndex(1)
        self._priority_combo.setMinimumWidth(150)
        self._priority_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px 12px;
            }}
        """)
        priority_layout.addWidget(self._priority_combo)
        priority_layout.addStretch()

        form_layout.addLayout(priority_layout)

        form_layout.addStretch()
        form_scroll.setWidget(form_widget)
        layout.addWidget(form_scroll, 1)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = FluentButton("Cancel", "", ButtonVariant.SUBTLE)
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        submit_btn = FluentButton("Submit Job", "", ButtonVariant.ACCENT)
        submit_btn.clicked.connect(self._submit)
        buttons_layout.addWidget(submit_btn)

        layout.addLayout(buttons_layout)

    def _submit(self):
        """Submit the job"""
        job_data = {
            "name": self._name_input.text(),
            "command": self._command_input.toPlainText(),
            "image": self._image_input.text(),
            "cpu": self._cpu_spin.value(),
            "memory": self._memory_spin.value(),
            "gpu": self._gpu_spin.value(),
            "priority": self._priority_combo.currentText().lower(),
        }

        # Validate
        if not job_data["name"]:
            self._name_input.set_error("Job name is required")
            return

        if not job_data["command"]:
            # Focus command input
            return

        self.job_submitted.emit(job_data)
        self.accept()


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT JOBS VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class FluentJobsView(QWidget):
    """
    Complete jobs management view.
    صفحة إدارة المهام الكاملة
    """

    refresh_requested = Signal()
    job_action = Signal(str, dict)  # action, job_data

    # Table columns
    COLUMNS = [
        Column("id", "ID", ColumnType.TEXT, 120),
        Column("name", "Name", ColumnType.TEXT, 200),
        Column("status", "Status", ColumnType.STATUS, 120),
        Column("worker", "Worker", ColumnType.TEXT, 120),
        Column("progress", "Progress", ColumnType.PROGRESS, 150),
        Column("priority", "Priority", ColumnType.BADGE, 100),
        Column("created_at", "Created", ColumnType.DATE, 150),
        Column("duration", "Duration", ColumnType.TEXT, 100),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()
        self._load_demo_data()

    def _setup_ui(self):
        """Setup view UI"""
        colors = FluentDesignSystem().colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("Jobs")
        title.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 28px;
            font-weight: 600;
        """)
        header_layout.addWidget(title)

        header_layout.addStretch()

        # New job button
        new_job_btn = FluentButton("New Job", FluentIcons.ADD, ButtonVariant.ACCENT)
        new_job_btn.clicked.connect(self._show_submit_dialog)
        header_layout.addWidget(new_job_btn)

        layout.addLayout(header_layout)

        # Main content with splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {colors.stroke_divider};
            }}
        """)

        # Jobs table
        self._table = FluentDataTable(self.COLUMNS)
        self._table.row_clicked.connect(self._on_row_clicked)
        self._table.row_double_clicked.connect(self._on_row_double_clicked)
        self._table.action_requested.connect(self._on_action_requested)
        splitter.addWidget(self._table)

        # Details panel
        self._details_panel = JobDetailsPanel()
        self._details_panel.setVisible(False)
        self._details_panel.action_requested.connect(self.job_action.emit)
        splitter.addWidget(self._details_panel)

        splitter.setSizes([800, 0])
        layout.addWidget(splitter, 1)

    def _load_demo_data(self):
        """Load demo data"""
        demo_jobs = [
            {
                "id": "job-001",
                "name": "Training Model v2",
                "status": "running",
                "worker": "worker-01",
                "progress": 67,
                "priority": "High",
                "created_at": datetime.now(),
                "duration": "2h 15m",
            },
            {
                "id": "job-002",
                "name": "Data Processing",
                "status": "completed",
                "worker": "worker-02",
                "progress": 100,
                "priority": "Normal",
                "created_at": datetime.now(),
                "duration": "45m",
            },
            {
                "id": "job-003",
                "name": "Inference Batch",
                "status": "pending",
                "worker": "-",
                "progress": 0,
                "priority": "Low",
                "created_at": datetime.now(),
                "duration": "-",
            },
            {
                "id": "job-004",
                "name": "Model Export",
                "status": "failed",
                "worker": "worker-03",
                "progress": 45,
                "priority": "Normal",
                "created_at": datetime.now(),
                "duration": "12m",
            },
            {
                "id": "job-005",
                "name": "Dataset Validation",
                "status": "running",
                "worker": "worker-01",
                "progress": 23,
                "priority": "Critical",
                "created_at": datetime.now(),
                "duration": "8m",
            },
        ]

        self._table.set_data(demo_jobs)

    def _on_row_clicked(self, row: int, data: dict):
        """Handle row click"""
        self._details_panel.set_job(data)

    def _on_row_double_clicked(self, row: int, data: dict):
        """Handle row double click"""
        self._details_panel.set_job(data)

    def _on_action_requested(self, action: str, data: dict):
        """Handle table action"""
        if action == "refresh":
            self.refresh_requested.emit()
        elif action == "export":
            # Would show file dialog
            pass
        else:
            self.job_action.emit(action, data)

    def _show_submit_dialog(self):
        """Show job submission dialog"""
        dialog = JobSubmitDialog(self)
        dialog.job_submitted.connect(self._on_job_submitted)
        dialog.exec()

    def _on_job_submitted(self, job_data: dict):
        """Handle job submission"""
        # Add to table
        job_data["id"] = f"job-{len(self._table.get_all_data()) + 1:03d}"
        job_data["status"] = "pending"
        job_data["worker"] = "-"
        job_data["progress"] = 0
        job_data["created_at"] = datetime.now()
        job_data["duration"] = "-"

        self._table.add_row(job_data)
        self.job_action.emit("submit", job_data)

    def set_jobs(self, jobs: List[Dict[str, Any]]):
        """Set jobs data"""
        self._table.set_data(jobs)

    def update_job(self, job_id: str, data: Dict[str, Any]):
        """Update a specific job"""
        all_jobs = self._table.get_all_data()
        for i, job in enumerate(all_jobs):
            if job.get("id") == job_id:
                self._table.update_row(i, data)
                break
