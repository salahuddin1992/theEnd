"""
Jobs View - Job management page
صفحة إدارة المهام
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..api.client import APIClient
from ..resources.styles import COLORS
from ..widgets.data_table import DataTable


class SubmitJobDialog(QDialog):
    """Dialog for submitting new jobs"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Submit New Job")
        self.setMinimumSize(500, 400)
        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Form
        form = QFormLayout()
        form.setSpacing(12)

        # Job name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter job name...")
        form.addRow("Name:", self.name_input)

        # Command
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("e.g., python script.py --arg value")
        form.addRow("Command:", self.command_input)

        # Job type
        self.type_combo = QComboBox()
        self.type_combo.addItems(["direct", "docker"])
        form.addRow("Type:", self.type_combo)

        # Docker image (shown only for docker type)
        self.image_input = QLineEdit()
        self.image_input.setPlaceholderText("e.g., python:3.11-slim")
        self.image_label = QLabel("Image:")
        form.addRow(self.image_label, self.image_input)

        # Priority
        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(0, 100)
        self.priority_spin.setValue(50)
        form.addRow("Priority:", self.priority_spin)

        # Resources section
        resources_label = QLabel("Resources")
        resources_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']}; margin-top: 8px;")
        form.addRow(resources_label)

        # CPU
        self.cpu_spin = QSpinBox()
        self.cpu_spin.setRange(1, 128)
        self.cpu_spin.setValue(1)
        form.addRow("CPU Cores:", self.cpu_spin)

        # Memory
        self.memory_spin = QSpinBox()
        self.memory_spin.setRange(128, 65536)
        self.memory_spin.setValue(512)
        self.memory_spin.setSuffix(" MB")
        form.addRow("Memory:", self.memory_spin)

        # GPU
        self.gpu_spin = QSpinBox()
        self.gpu_spin.setRange(0, 8)
        self.gpu_spin.setValue(0)
        form.addRow("GPUs:", self.gpu_spin)

        # Timeout
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(0, 86400)
        self.timeout_spin.setValue(3600)
        self.timeout_spin.setSuffix(" sec")
        form.addRow("Timeout:", self.timeout_spin)

        layout.addLayout(form)

        # Toggle docker image visibility
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self._on_type_changed(self.type_combo.currentText())

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_type_changed(self, job_type: str):
        """Handle job type change"""
        is_docker = job_type == "docker"
        self.image_input.setVisible(is_docker)
        self.image_label.setVisible(is_docker)

    def get_job_spec(self) -> dict:
        """Get the job specification from form"""
        spec = {
            "name": self.name_input.text() or None,
            "command": self.command_input.text(),
            "job_type": self.type_combo.currentText(),
            "priority": self.priority_spin.value(),
            "resources": {
                "cpu_cores": self.cpu_spin.value(),
                "memory_mb": self.memory_spin.value(),
                "gpu_count": self.gpu_spin.value(),
            },
            "timeout": self.timeout_spin.value(),
        }

        if self.type_combo.currentText() == "docker":
            spec["image"] = self.image_input.text()

        return spec


class JobDetailPanel(QFrame):
    """Panel showing job details"""

    cancel_requested = Signal(str)
    retry_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stat_card")
        self._current_job = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()
        self.title_label = QLabel("Job Details")
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

        self.name_label = QLabel("-")
        info_layout.addRow("Name:", self.name_label)

        self.command_label = QLabel("-")
        self.command_label.setWordWrap(True)
        info_layout.addRow("Command:", self.command_label)

        self.worker_label = QLabel("-")
        info_layout.addRow("Worker:", self.worker_label)

        self.created_label = QLabel("-")
        info_layout.addRow("Created:", self.created_label)

        self.started_label = QLabel("-")
        info_layout.addRow("Started:", self.started_label)

        self.finished_label = QLabel("-")
        info_layout.addRow("Finished:", self.finished_label)

        tabs.addTab(info_widget, "Info")

        # Resources tab
        resources_widget = QWidget()
        resources_layout = QFormLayout(resources_widget)
        resources_layout.setSpacing(8)

        self.cpu_label = QLabel("-")
        resources_layout.addRow("CPU:", self.cpu_label)

        self.memory_label = QLabel("-")
        resources_layout.addRow("Memory:", self.memory_label)

        self.gpu_label = QLabel("-")
        resources_layout.addRow("GPU:", self.gpu_label)

        tabs.addTab(resources_widget, "Resources")

        # Output tab
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 8, 0, 0)

        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet(
            f"""
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 12px;
            background-color: {COLORS['bg_dark']};
        """
        )
        output_layout.addWidget(self.output_text)

        tabs.addTab(output_widget, "Output")

        layout.addWidget(tabs)

        # Actions
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("danger_button")
        self.cancel_btn.clicked.connect(self._on_cancel)
        actions_layout.addWidget(self.cancel_btn)

        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setObjectName("secondary_button")
        self.retry_btn.clicked.connect(self._on_retry)
        actions_layout.addWidget(self.retry_btn)

        layout.addLayout(actions_layout)

    def set_job(self, job: dict):
        """Display job details"""
        self._current_job = job

        self.id_label.setText(job.get("id", "-"))
        self.name_label.setText(job.get("name", "-") or "-")
        self.command_label.setText(job.get("command", "-"))
        self.worker_label.setText(job.get("worker_id", "-") or "Not assigned")
        self.created_label.setText(job.get("created_at", "-"))
        self.started_label.setText(job.get("started_at", "-") or "-")
        self.finished_label.setText(job.get("finished_at", "-") or "-")

        # Status
        status = job.get("status", "unknown")
        from ..resources.styles import get_status_color

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
        resources = job.get("resources", {})
        self.cpu_label.setText(f"{resources.get('cpu_cores', '-')} cores")
        self.memory_label.setText(f"{resources.get('memory_mb', '-')} MB")
        self.gpu_label.setText(f"{resources.get('gpu_count', 0)} units")

        # Output
        output = job.get("output", "") or job.get("logs", "") or ""
        self.output_text.setPlainText(output)

        # Enable/disable actions based on status
        self.cancel_btn.setEnabled(status in ("pending", "running", "queued"))
        self.retry_btn.setEnabled(status in ("failed", "cancelled"))

    def clear(self):
        """Clear job details"""
        self._current_job = None
        self.id_label.setText("-")
        self.name_label.setText("-")
        self.command_label.setText("-")
        self.worker_label.setText("-")
        self.created_label.setText("-")
        self.started_label.setText("-")
        self.finished_label.setText("-")
        self.status_label.setText("")
        self.cpu_label.setText("-")
        self.memory_label.setText("-")
        self.gpu_label.setText("-")
        self.output_text.clear()

    def _on_cancel(self):
        """Handle cancel button click"""
        if self._current_job:
            self.cancel_requested.emit(self._current_job.get("id"))

    def _on_retry(self):
        """Handle retry button click"""
        if self._current_job:
            self.retry_requested.emit(self._current_job.get("id"))


class JobsView(QWidget):
    """Jobs management view"""

    refresh_requested = Signal()

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._setup_ui()

    def _setup_ui(self):
        """Setup jobs view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("Jobs")
        title.setStyleSheet(
            f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """
        )
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Filter combo
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Pending", "Running", "Completed", "Failed", "Cancelled"])
        self.status_filter.currentTextChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.status_filter)

        # Submit button
        submit_btn = QPushButton("+ Submit Job")
        submit_btn.clicked.connect(self._on_submit_job)
        header_layout.addWidget(submit_btn)

        layout.addLayout(header_layout)

        # Splitter for table and details
        splitter = QSplitter(Qt.Horizontal)

        # Jobs table
        self.jobs_table = DataTable(
            [
                ("ID", "id", 120),
                ("Name", "name", 150),
                ("Status", "status", 100),
                ("Command", "command", -1),
                ("Worker", "worker_id", 120),
                ("Created", "created_at", 150),
            ]
        )
        self.jobs_table.set_status_column("status")
        self.jobs_table.row_selected.connect(self._on_job_selected)
        self.jobs_table.refresh_btn.clicked.connect(self._on_refresh)
        splitter.addWidget(self.jobs_table)

        # Detail panel
        self.detail_panel = JobDetailPanel()
        self.detail_panel.cancel_requested.connect(self._on_cancel_job)
        self.detail_panel.retry_requested.connect(self._on_retry_job)
        splitter.addWidget(self.detail_panel)

        splitter.setSizes([600, 400])
        layout.addWidget(splitter)

    def set_jobs(self, jobs: list):
        """Update jobs list"""
        self.jobs_table.set_data(jobs)

    def _on_job_selected(self, row_idx: int, job_data: dict):
        """Handle job selection"""
        self.detail_panel.set_job(job_data)

    def _on_filter_changed(self, status: str):
        """Handle status filter change"""
        self.refresh_requested.emit()

    def _on_refresh(self):
        """Handle refresh button click"""
        self.refresh_requested.emit()

    def _on_submit_job(self):
        """Handle submit job button click"""
        dialog = SubmitJobDialog(self)
        if dialog.exec() == QDialog.Accepted:
            spec = dialog.get_job_spec()
            # Submit job via API client (handled by main window)
            self._submit_job_spec = spec
            self.refresh_requested.emit()

    def _on_cancel_job(self, job_id: str):
        """Handle cancel job request"""
        reply = QMessageBox.question(
            self,
            "Cancel Job",
            f"Are you sure you want to cancel job {job_id}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # Cancel via API client
            if self.api_client:
                import asyncio

                async def do_cancel():
                    success = await self.api_client.cancel_job(job_id)
                    if success:
                        QMessageBox.information(self, "Success", f"Job {job_id} has been cancelled.")
                        self.refresh_requested.emit()
                    else:
                        QMessageBox.warning(self, "Error", f"Failed to cancel job {job_id}.")

                asyncio.create_task(do_cancel())

    def _on_retry_job(self, job_id: str):
        """Handle retry job request"""
        # Retry via API client
        if self.api_client:
            import asyncio

            async def do_retry():
                success = await self.api_client.retry_job(job_id)
                if success:
                    QMessageBox.information(self, "Success", f"Job {job_id} has been resubmitted.")
                    self.refresh_requested.emit()
                else:
                    QMessageBox.warning(self, "Error", f"Failed to retry job {job_id}.")

            asyncio.create_task(do_retry())

    def get_status_filter(self) -> Optional[str]:
        """Get current status filter"""
        status = self.status_filter.currentText()
        return None if status == "All" else status.lower()

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
