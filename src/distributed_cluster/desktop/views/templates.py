"""
Templates View - Job templates management page
صفحة إدارة قوالب المهام
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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
    QVBoxLayout,
    QWidget,
)

from ..api.client import APIClient
from ..resources.styles import COLORS
from ..widgets.data_table import DataTable


class CreateTemplateDialog(QDialog):
    """Dialog for creating new job templates"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Job Template")
        self.setMinimumSize(500, 500)
        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)

        # Template name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter template name...")
        form.addRow("Name:", self.name_input)

        # Description
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Template description...")
        form.addRow("Description:", self.desc_input)

        # Command
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("e.g., python {script} --arg {value}")
        form.addRow("Command:", self.command_input)

        # Resources
        resources_label = QLabel("Default Resources")
        resources_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']}; margin-top: 8px;")
        form.addRow(resources_label)

        self.cpu_spin = QSpinBox()
        self.cpu_spin.setRange(1, 128)
        self.cpu_spin.setValue(1)
        form.addRow("CPU Cores:", self.cpu_spin)

        self.memory_spin = QSpinBox()
        self.memory_spin.setRange(128, 65536)
        self.memory_spin.setValue(512)
        self.memory_spin.setSuffix(" MB")
        form.addRow("Memory:", self.memory_spin)

        self.gpu_spin = QSpinBox()
        self.gpu_spin.setRange(0, 8)
        self.gpu_spin.setValue(0)
        form.addRow("GPUs:", self.gpu_spin)

        # Variables
        variables_label = QLabel("Variables (JSON)")
        variables_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']}; margin-top: 8px;")
        form.addRow(variables_label)

        self.variables_input = QPlainTextEdit()
        self.variables_input.setPlaceholderText('{\n  "script": "main.py",\n  "value": "default"\n}')
        self.variables_input.setMaximumHeight(100)
        form.addRow(self.variables_input)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_template_spec(self) -> dict:
        """Get template specification from form"""
        import json

        variables = {}
        try:
            var_text = self.variables_input.toPlainText().strip()
            if var_text:
                variables = json.loads(var_text)
        except json.JSONDecodeError:
            pass

        return {
            "name": self.name_input.text(),
            "description": self.desc_input.text(),
            "command": self.command_input.text(),
            "resources": {
                "cpu_cores": self.cpu_spin.value(),
                "memory_mb": self.memory_spin.value(),
                "gpu_count": self.gpu_spin.value(),
            },
            "variables": variables,
        }


class TemplateDetailPanel(QFrame):
    """Panel showing template details"""

    use_template = Signal(dict)
    delete_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stat_card")
        self._current_template = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        self.title_label = QLabel("Template Details")
        self.title_label.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {COLORS['text_primary']};")
        layout.addWidget(self.title_label)

        # Form
        form = QFormLayout()
        form.setSpacing(8)

        self.name_label = QLabel("-")
        form.addRow("Name:", self.name_label)

        self.desc_label = QLabel("-")
        self.desc_label.setWordWrap(True)
        form.addRow("Description:", self.desc_label)

        self.command_label = QLabel("-")
        self.command_label.setWordWrap(True)
        form.addRow("Command:", self.command_label)

        self.cpu_label = QLabel("-")
        form.addRow("CPU:", self.cpu_label)

        self.memory_label = QLabel("-")
        form.addRow("Memory:", self.memory_label)

        self.gpu_label = QLabel("-")
        form.addRow("GPU:", self.gpu_label)

        layout.addLayout(form)

        # Variables
        var_label = QLabel("Variables:")
        var_label.setStyleSheet(f"color: {COLORS['text_secondary']}; margin-top: 8px;")
        layout.addWidget(var_label)

        self.variables_text = QPlainTextEdit()
        self.variables_text.setReadOnly(True)
        self.variables_text.setMaximumHeight(100)
        layout.addWidget(self.variables_text)

        layout.addStretch()

        # Actions
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()

        self.use_btn = QPushButton("Use Template")
        self.use_btn.clicked.connect(self._on_use)
        actions_layout.addWidget(self.use_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("danger_button")
        self.delete_btn.clicked.connect(self._on_delete)
        actions_layout.addWidget(self.delete_btn)

        layout.addLayout(actions_layout)

    def set_template(self, template: dict):
        """Display template details"""
        import json

        self._current_template = template

        self.name_label.setText(template.get("name", "-"))
        self.desc_label.setText(template.get("description", "-") or "-")
        self.command_label.setText(template.get("command", "-"))

        resources = template.get("resources", {})
        self.cpu_label.setText(f"{resources.get('cpu_cores', '-')} cores")
        self.memory_label.setText(f"{resources.get('memory_mb', '-')} MB")
        self.gpu_label.setText(f"{resources.get('gpu_count', 0)} units")

        variables = template.get("variables", {})
        self.variables_text.setPlainText(json.dumps(variables, indent=2) if variables else "{}")

    def clear(self):
        """Clear template details"""
        self._current_template = None
        self.name_label.setText("-")
        self.desc_label.setText("-")
        self.command_label.setText("-")
        self.cpu_label.setText("-")
        self.memory_label.setText("-")
        self.gpu_label.setText("-")
        self.variables_text.clear()

    def _on_use(self):
        """Handle use template button"""
        if self._current_template:
            self.use_template.emit(self._current_template)

    def _on_delete(self):
        """Handle delete button"""
        if self._current_template:
            self.delete_requested.emit(self._current_template.get("name"))


class TemplatesView(QWidget):
    """Templates management view"""

    refresh_requested = Signal()

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._setup_ui()

    def _setup_ui(self):
        """Setup templates view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("Job Templates")
        title.setStyleSheet(
            f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """
        )
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Create button
        create_btn = QPushButton("+ Create Template")
        create_btn.clicked.connect(self._on_create_template)
        header_layout.addWidget(create_btn)

        layout.addLayout(header_layout)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)

        # Templates table
        self.templates_table = DataTable(
            [
                ("Name", "name", 150),
                ("Description", "description", -1),
                ("CPU", "cpu_display", 80),
                ("Memory", "memory_display", 100),
            ]
        )
        self.templates_table.row_selected.connect(self._on_template_selected)
        self.templates_table.refresh_btn.clicked.connect(self._on_refresh)
        splitter.addWidget(self.templates_table)

        # Detail panel
        self.detail_panel = TemplateDetailPanel()
        self.detail_panel.use_template.connect(self._on_use_template)
        self.detail_panel.delete_requested.connect(self._on_delete_template)
        splitter.addWidget(self.detail_panel)

        splitter.setSizes([600, 400])
        layout.addWidget(splitter)

    def set_templates(self, templates: list):
        """Update templates list"""
        display_data = []
        for template in templates:
            resources = template.get("resources", {})
            display_data.append(
                {
                    **template,
                    "cpu_display": f"{resources.get('cpu_cores', '-')} cores",
                    "memory_display": f"{resources.get('memory_mb', '-')} MB",
                }
            )
        self.templates_table.set_data(display_data)

    def _on_template_selected(self, row_idx: int, template_data: dict):
        """Handle template selection"""
        self.detail_panel.set_template(template_data)

    def _on_refresh(self):
        """Handle refresh"""
        self.refresh_requested.emit()

    def _on_create_template(self):
        """Handle create template"""
        dialog = CreateTemplateDialog(self)
        if dialog.exec() == QDialog.Accepted:
            dialog.get_template_spec()
            # Create template via API
            self.refresh_requested.emit()

    def _on_use_template(self, template: dict):
        """Handle use template"""
        QMessageBox.information(
            self,
            "Use Template",
            f"Template '{template.get('name')}' selected.\n" "Navigate to Jobs to submit a job using this template.",
        )

    def _on_delete_template(self, name: str):
        """Handle delete template"""
        reply = QMessageBox.question(
            self,
            "Delete Template",
            f"Are you sure you want to delete template '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # Delete via API
            self.refresh_requested.emit()

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
