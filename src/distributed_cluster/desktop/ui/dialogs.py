"""
Fluent Design Dialogs
نوافذ الحوار بتصميم Fluent

Modern Windows 11 style dialogs:
- Connection Dialog
- Confirmation Dialog
- Input Dialog
- Progress Dialog
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, List

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .components import ButtonVariant, FluentButton, FluentCard, FluentInput
from .fluent_design import FluentDesignSystem
from .splash import SplashProgressRing

# ═══════════════════════════════════════════════════════════════════════════════
# BASE DIALOG
# ═══════════════════════════════════════════════════════════════════════════════


class FluentDialog(QDialog):
    """
    Base Fluent Design dialog.
    نافذة الحوار الأساسية بتصميم Fluent
    """

    def __init__(self, title: str = "", parent: QWidget = None, width: int = 480, closable: bool = True):
        super().__init__(parent)

        self._title_text = title
        self._closable = closable

        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(width)
        self.setModal(True)

        self._setup_base_ui()
        self._setup_animations()

    def _setup_base_ui(self):
        """Setup base dialog UI"""
        colors = FluentDesignSystem().colors

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Dialog container
        self._container = QFrame()
        self._container.setObjectName("dialogContainer")
        self._container.setStyleSheet(
            f"""
            #dialogContainer {{
                background-color: {colors.bg_solid_base};
                border-radius: 12px;
                border: 1px solid {colors.stroke_surface};
            }}
        """
        )

        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(24, 20, 24, 24)
        container_layout.setSpacing(16)

        # Header
        header = QHBoxLayout()

        self._title_label = QLabel(self._title_text)
        self._title_label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 20px;
            font-weight: 600;
        """
        )
        header.addWidget(self._title_label)

        header.addStretch()

        if self._closable:
            close_btn = FluentButton("", "✕", ButtonVariant.SUBTLE)
            close_btn.setFixedSize(32, 32)
            close_btn.clicked.connect(self.reject)
            header.addWidget(close_btn)

        container_layout.addLayout(header)

        # Content area (to be filled by subclasses)
        self._content_layout = QVBoxLayout()
        self._content_layout.setSpacing(16)
        container_layout.addLayout(self._content_layout)

        # Button area
        self._button_layout = QHBoxLayout()
        self._button_layout.setSpacing(8)
        self._button_layout.addStretch()
        container_layout.addLayout(self._button_layout)

        main_layout.addWidget(self._container)

        # Shadow effect
        self._opacity = QGraphicsOpacityEffect(self._container)
        self._opacity.setOpacity(1.0)

    def _setup_animations(self):
        """Setup dialog animations"""
        pass  # Can be overridden

    def add_content(self, widget: QWidget):
        """Add widget to content area"""
        self._content_layout.addWidget(widget)

    def add_button(
        self, text: str, variant: ButtonVariant = ButtonVariant.STANDARD, callback: Callable = None
    ) -> FluentButton:
        """Add button to dialog"""
        btn = FluentButton(text, "", variant)
        if callback:
            btn.clicked.connect(callback)
        self._button_layout.addWidget(btn)
        return btn

    def set_title(self, title: str):
        """Set dialog title"""
        self._title_text = title
        self._title_label.setText(title)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle key presses"""
        if event.key() == Qt.Key.Key_Escape and self._closable:
            self.reject()
        else:
            super().keyPressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# CONNECTION DIALOG
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ConnectionProfile:
    """Saved connection profile"""

    name: str
    host: str
    port: int
    use_ssl: bool = True
    username: str = ""
    password: str = ""
    auto_connect: bool = False


class ConnectionDialog(FluentDialog):
    """
    Connection dialog for cluster connection.
    نافذة الاتصال بالكلستر

    Features:
    - Host/Port configuration
    - SSL/TLS option
    - Connection profiles
    - Connection testing
    - Credential saving
    """

    connection_requested = Signal(dict)  # Connection config
    test_requested = Signal(dict)  # Test connection

    def __init__(self, parent=None):
        super().__init__("Connect to Cluster", parent, width=520)

        self._profiles: List[ConnectionProfile] = []
        self._is_testing = False

        self._setup_content()
        self._load_default_profile()

    def _setup_content(self):
        """Setup dialog content"""
        colors = FluentDesignSystem().colors

        # Profile selection
        profile_layout = QHBoxLayout()
        profile_layout.setSpacing(8)

        profile_label = QLabel("Profile:")
        profile_label.setStyleSheet(f"color: {colors.text_secondary};")
        profile_layout.addWidget(profile_label)

        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(200)
        self._profile_combo.addItems(["New Connection", "Local Development", "Production Cluster"])
        self._profile_combo.currentTextChanged.connect(self._on_profile_changed)
        self._profile_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px 12px;
            }}
            QComboBox:hover {{
                background-color: {colors.fill_control_secondary};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
            }}
        """
        )
        profile_layout.addWidget(self._profile_combo, 1)

        save_profile_btn = FluentButton("Save", "", ButtonVariant.SUBTLE)
        save_profile_btn.clicked.connect(self._save_profile)
        profile_layout.addWidget(save_profile_btn)

        self.add_content(self._wrap_layout(profile_layout))

        # Separator
        self._add_separator()

        # Connection settings card
        conn_card = FluentCard("Connection Settings")
        conn_layout = QVBoxLayout()
        conn_layout.setSpacing(12)

        # Host
        host_layout = QHBoxLayout()
        host_label = QLabel("Host:")
        host_label.setFixedWidth(80)
        host_label.setStyleSheet(f"color: {colors.text_secondary};")
        host_layout.addWidget(host_label)

        self._host_input = FluentInput("Enter cluster host address")
        self._host_input.setText("localhost")
        host_layout.addWidget(self._host_input, 1)
        conn_layout.addLayout(host_layout)

        # Port
        port_layout = QHBoxLayout()
        port_label = QLabel("Port:")
        port_label.setFixedWidth(80)
        port_label.setStyleSheet(f"color: {colors.text_secondary};")
        port_layout.addWidget(port_label)

        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(8765)
        self._port_input.setFixedWidth(100)
        self._port_input.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """
        )
        port_layout.addWidget(self._port_input)
        port_layout.addStretch()
        conn_layout.addLayout(port_layout)

        # SSL
        ssl_layout = QHBoxLayout()
        ssl_label = QLabel("Security:")
        ssl_label.setFixedWidth(80)
        ssl_label.setStyleSheet(f"color: {colors.text_secondary};")
        ssl_layout.addWidget(ssl_label)

        self._ssl_check = QCheckBox("Use SSL/TLS encryption")
        self._ssl_check.setChecked(True)
        self._ssl_check.setStyleSheet(f"color: {colors.text_primary};")
        ssl_layout.addWidget(self._ssl_check)
        ssl_layout.addStretch()
        conn_layout.addLayout(ssl_layout)

        conn_card.add_content(self._wrap_layout(conn_layout))
        self.add_content(conn_card)

        # Authentication card
        auth_card = FluentCard("Authentication (Optional)")
        auth_layout = QVBoxLayout()
        auth_layout.setSpacing(12)

        # Username
        user_layout = QHBoxLayout()
        user_label = QLabel("Username:")
        user_label.setFixedWidth(80)
        user_label.setStyleSheet(f"color: {colors.text_secondary};")
        user_layout.addWidget(user_label)

        self._username_input = FluentInput("Enter username")
        user_layout.addWidget(self._username_input, 1)
        auth_layout.addLayout(user_layout)

        # Password
        pass_layout = QHBoxLayout()
        pass_label = QLabel("Password:")
        pass_label.setFixedWidth(80)
        pass_label.setStyleSheet(f"color: {colors.text_secondary};")
        pass_layout.addWidget(pass_label)

        self._password_input = FluentInput("Enter password")
        self._password_input._line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pass_layout.addWidget(self._password_input, 1)
        auth_layout.addLayout(pass_layout)

        # Remember credentials
        remember_layout = QHBoxLayout()
        remember_layout.addSpacing(80)
        self._remember_check = QCheckBox("Remember credentials")
        self._remember_check.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        remember_layout.addWidget(self._remember_check)
        remember_layout.addStretch()
        auth_layout.addLayout(remember_layout)

        auth_card.add_content(self._wrap_layout(auth_layout))
        self.add_content(auth_card)

        # Options
        options_layout = QHBoxLayout()
        self._auto_connect = QCheckBox("Auto-connect on startup")
        self._auto_connect.setStyleSheet(f"color: {colors.text_secondary};")
        options_layout.addWidget(self._auto_connect)
        options_layout.addStretch()
        self.add_content(self._wrap_layout(options_layout))

        # Test result area
        self._test_result = QLabel("")
        self._test_result.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        self._test_result.hide()
        self.add_content(self._test_result)

        # Buttons
        test_btn = self.add_button("Test Connection", ButtonVariant.SUBTLE, self._test_connection)
        self._test_btn = test_btn

        self.add_button("Cancel", ButtonVariant.STANDARD, self.reject)
        connect_btn = self.add_button("Connect", ButtonVariant.ACCENT, self._connect)
        self._connect_btn = connect_btn

    def _wrap_layout(self, layout) -> QWidget:
        """Wrap layout in widget"""
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _add_separator(self):
        """Add separator line"""
        colors = FluentDesignSystem().colors
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {colors.stroke_divider};")
        sep.setFixedHeight(1)
        self.add_content(sep)

    def _on_profile_changed(self, name: str):
        """Handle profile selection change"""
        if name == "Local Development":
            self._host_input.setText("localhost")
            self._port_input.setValue(8765)
            self._ssl_check.setChecked(False)
        elif name == "Production Cluster":
            self._host_input.setText("cluster.nebulacompute.io")
            self._port_input.setValue(443)
            self._ssl_check.setChecked(True)

    def _save_profile(self):
        """Save current settings as profile"""
        import json
        from pathlib import Path

        from PySide6.QtWidgets import QInputDialog, QMessageBox

        # Get profile name from user
        name, ok = QInputDialog.getText(self, "Save Profile", "Profile name:")
        if not ok or not name.strip():
            return

        profile_data = {
            "name": name.strip(),
            "host": self._host_input.text(),
            "port": self._port_input.value(),
            "ssl": self._ssl_check.isChecked(),
        }

        # Save to profiles directory
        profiles_dir = Path.home() / ".nebula_desktop" / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)

        profile_path = profiles_dir / f"{name.strip().lower().replace(' ', '_')}.json"
        try:
            with open(profile_path, "w") as f:
                json.dump(profile_data, f, indent=2)
            QMessageBox.information(self, "Success", f"Profile '{name}' saved successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save profile: {e}")

    def _load_default_profile(self):
        """Load default connection profile"""
        self._host_input.setText("localhost")
        self._port_input.setValue(8765)
        self._ssl_check.setChecked(False)
        self._profile_combo.setCurrentText("Local Development")

    def _test_connection(self):
        """Test connection with current settings"""
        if self._is_testing:
            return

        FluentDesignSystem().colors

        self._is_testing = True
        self._test_btn.setEnabled(False)
        self._test_btn.setText("Testing...")

        config = self._get_config()
        self.test_requested.emit(config)

        # Simulate test (in real app, this would be async)
        QTimer.singleShot(1500, self._show_test_result)

    def _show_test_result(self, success: bool = True):
        """Show test result"""
        colors = FluentDesignSystem().colors

        self._is_testing = False
        self._test_btn.setEnabled(True)
        self._test_btn.setText("Test Connection")

        if success:
            self._test_result.setText("✓ Connection successful!")
            self._test_result.setStyleSheet(f"color: {colors.success};")
        else:
            self._test_result.setText("✕ Connection failed. Check settings.")
            self._test_result.setStyleSheet(f"color: {colors.error};")

        self._test_result.show()

    def _connect(self):
        """Initiate connection"""
        config = self._get_config()
        self.connection_requested.emit(config)
        self.accept()

    def _get_config(self) -> dict:
        """Get current configuration"""
        return {
            "host": self._host_input.text(),
            "port": self._port_input.value(),
            "use_ssl": self._ssl_check.isChecked(),
            "username": self._username_input.text(),
            "password": self._password_input.text(),
            "remember": self._remember_check.isChecked(),
            "auto_connect": self._auto_connect.isChecked(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIRMATION DIALOG
# ═══════════════════════════════════════════════════════════════════════════════


class ConfirmationType(Enum):
    """Confirmation dialog types"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    QUESTION = "question"


class ConfirmationDialog(FluentDialog):
    """
    Confirmation dialog with icon and message.
    نافذة التأكيد
    """

    confirmed = Signal()
    cancelled = Signal()

    def __init__(
        self,
        title: str,
        message: str,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        dialog_type: ConfirmationType = ConfirmationType.QUESTION,
        parent=None,
    ):
        super().__init__(title, parent, width=420)

        self._message = message
        self._confirm_text = confirm_text
        self._cancel_text = cancel_text
        self._type = dialog_type

        self._setup_content()

    def _setup_content(self):
        """Setup confirmation content"""
        colors = FluentDesignSystem().colors

        # Icon and message layout
        content = QHBoxLayout()
        content.setSpacing(16)

        # Icon
        icon_map = {
            ConfirmationType.INFO: ("ℹ", colors.info),
            ConfirmationType.WARNING: ("⚠", colors.warning),
            ConfirmationType.ERROR: ("✕", colors.error),
            ConfirmationType.QUESTION: ("?", colors.accent),
        }
        icon_char, icon_color = icon_map.get(self._type, ("?", colors.accent))

        icon_label = QLabel(icon_char)
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(
            f"""
            background-color: {icon_color}20;
            color: {icon_color};
            font-size: 24px;
            border-radius: 24px;
        """
        )
        content.addWidget(icon_label)

        # Message
        msg_label = QLabel(self._message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 14px;
        """
        )
        content.addWidget(msg_label, 1)

        self.add_content(self._wrap_layout(content))

        # Buttons
        self.add_button(self._cancel_text, ButtonVariant.STANDARD, self._on_cancel)
        self.add_button(self._confirm_text, ButtonVariant.ACCENT, self._on_confirm)

    def _wrap_layout(self, layout) -> QWidget:
        """Wrap layout in widget"""
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _on_confirm(self):
        """Handle confirm"""
        self.confirmed.emit()
        self.accept()

    def _on_cancel(self):
        """Handle cancel"""
        self.cancelled.emit()
        self.reject()


# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS DIALOG
# ═══════════════════════════════════════════════════════════════════════════════


class ProgressDialog(FluentDialog):
    """
    Progress dialog for long operations.
    نافذة التقدم
    """

    cancelled = Signal()

    def __init__(self, title: str, message: str = "", cancellable: bool = True, parent=None):
        super().__init__(title, parent, width=400, closable=False)

        self._message = message
        self._cancellable = cancellable
        self._progress = 0

        self._setup_content()

    def _setup_content(self):
        """Setup progress content"""
        colors = FluentDesignSystem().colors

        # Progress indicator
        progress_layout = QHBoxLayout()
        progress_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._progress_ring = SplashProgressRing(48)
        progress_layout.addWidget(self._progress_ring)

        self.add_content(self._wrap_layout(progress_layout))

        # Message
        self._message_label = QLabel(self._message)
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet(
            f"""
            color: {colors.text_secondary};
            font-size: 14px;
        """
        )
        self.add_content(self._message_label)

        # Progress percentage
        self._percent_label = QLabel("")
        self._percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._percent_label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 24px;
            font-weight: 600;
        """
        )
        self.add_content(self._percent_label)

        # Cancel button
        if self._cancellable:
            cancel_btn = self.add_button("Cancel", ButtonVariant.SUBTLE, self._on_cancel)
            self._cancel_btn = cancel_btn

    def _wrap_layout(self, layout) -> QWidget:
        """Wrap layout in widget"""
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def set_message(self, message: str):
        """Update message"""
        self._message = message
        self._message_label.setText(message)

    def set_progress(self, value: int):
        """Set progress value (0-100)"""
        self._progress = value
        self._percent_label.setText(f"{value}%")

    def _on_cancel(self):
        """Handle cancel"""
        self.cancelled.emit()
        self.reject()


# ═══════════════════════════════════════════════════════════════════════════════
# INPUT DIALOG
# ═══════════════════════════════════════════════════════════════════════════════


class InputDialog(FluentDialog):
    """
    Input dialog for getting user input.
    نافذة الإدخال
    """

    value_submitted = Signal(str)

    def __init__(self, title: str, label: str, placeholder: str = "", default_value: str = "", parent=None):
        super().__init__(title, parent, width=400)

        self._label = label
        self._placeholder = placeholder
        self._default_value = default_value

        self._setup_content()

    def _setup_content(self):
        """Setup input content"""
        colors = FluentDesignSystem().colors

        # Label
        label = QLabel(self._label)
        label.setStyleSheet(f"color: {colors.text_secondary}; margin-bottom: 4px;")
        self.add_content(label)

        # Input
        self._input = FluentInput(self._placeholder)
        self._input.setText(self._default_value)
        self.add_content(self._input)

        # Buttons
        self.add_button("Cancel", ButtonVariant.STANDARD, self.reject)
        self.add_button("Submit", ButtonVariant.ACCENT, self._on_submit)

    def _on_submit(self):
        """Handle submit"""
        self.value_submitted.emit(self._input.text())
        self.accept()

    def get_value(self) -> str:
        """Get input value"""
        return self._input.text()


# ═══════════════════════════════════════════════════════════════════════════════
# JOB SUBMISSION DIALOG
# ═══════════════════════════════════════════════════════════════════════════════


class JobSubmitDialog(FluentDialog):
    """
    Job submission dialog.
    نافذة إرسال المهمة
    """

    job_submitted = Signal(dict)

    def __init__(self, parent=None):
        super().__init__("Submit New Job", parent, width=560)
        self._setup_content()

    def _setup_content(self):
        """Setup job submission form"""
        colors = FluentDesignSystem().colors

        # Scroll area for form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(400)

        form = QWidget()
        form_layout = QVBoxLayout(form)
        form_layout.setSpacing(16)

        # Job name
        name_card = FluentCard("Job Information")
        name_layout = QVBoxLayout()

        name_label = QLabel("Job Name:")
        name_label.setStyleSheet(f"color: {colors.text_secondary};")
        name_layout.addWidget(name_label)

        self._name_input = FluentInput("Enter job name")
        name_layout.addWidget(self._name_input)

        desc_label = QLabel("Description:")
        desc_label.setStyleSheet(f"color: {colors.text_secondary}; margin-top: 8px;")
        name_layout.addWidget(desc_label)

        self._desc_input = FluentInput("Enter job description")
        name_layout.addWidget(self._desc_input)

        name_card.add_content(self._wrap_layout(name_layout))
        form_layout.addWidget(name_card)

        # Job type
        type_card = FluentCard("Job Configuration")
        type_layout = QVBoxLayout()

        type_label = QLabel("Job Type:")
        type_label.setStyleSheet(f"color: {colors.text_secondary};")
        type_layout.addWidget(type_label)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["Python Script", "Container Image", "Binary Executable", "Shell Script"])
        self._type_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px 12px;
            }}
        """
        )
        type_layout.addWidget(self._type_combo)

        # Priority
        priority_layout = QHBoxLayout()
        priority_label = QLabel("Priority:")
        priority_label.setStyleSheet(f"color: {colors.text_secondary};")
        priority_layout.addWidget(priority_label)

        self._priority_combo = QComboBox()
        self._priority_combo.addItems(["Low", "Normal", "High", "Critical"])
        self._priority_combo.setCurrentIndex(1)
        self._priority_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px 12px;
            }}
        """
        )
        priority_layout.addWidget(self._priority_combo)
        priority_layout.addStretch()
        type_layout.addLayout(priority_layout)

        type_card.add_content(self._wrap_layout(type_layout))
        form_layout.addWidget(type_card)

        # Resources
        resource_card = FluentCard("Resource Requirements")
        resource_layout = QVBoxLayout()

        # CPU
        cpu_layout = QHBoxLayout()
        cpu_label = QLabel("CPU Cores:")
        cpu_label.setFixedWidth(100)
        cpu_label.setStyleSheet(f"color: {colors.text_secondary};")
        cpu_layout.addWidget(cpu_label)

        self._cpu_spin = QSpinBox()
        self._cpu_spin.setRange(1, 128)
        self._cpu_spin.setValue(4)
        self._cpu_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """
        )
        cpu_layout.addWidget(self._cpu_spin)
        cpu_layout.addStretch()
        resource_layout.addLayout(cpu_layout)

        # Memory
        mem_layout = QHBoxLayout()
        mem_label = QLabel("Memory (GB):")
        mem_label.setFixedWidth(100)
        mem_label.setStyleSheet(f"color: {colors.text_secondary};")
        mem_layout.addWidget(mem_label)

        self._mem_spin = QSpinBox()
        self._mem_spin.setRange(1, 512)
        self._mem_spin.setValue(8)
        self._mem_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """
        )
        mem_layout.addWidget(self._mem_spin)
        mem_layout.addStretch()
        resource_layout.addLayout(mem_layout)

        # GPU
        gpu_layout = QHBoxLayout()
        self._gpu_check = QCheckBox("Requires GPU")
        self._gpu_check.setStyleSheet(f"color: {colors.text_secondary};")
        gpu_layout.addWidget(self._gpu_check)

        self._gpu_spin = QSpinBox()
        self._gpu_spin.setRange(0, 8)
        self._gpu_spin.setValue(0)
        self._gpu_spin.setEnabled(False)
        self._gpu_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """
        )
        self._gpu_check.toggled.connect(self._gpu_spin.setEnabled)
        gpu_layout.addWidget(self._gpu_spin)
        gpu_layout.addStretch()
        resource_layout.addLayout(gpu_layout)

        resource_card.add_content(self._wrap_layout(resource_layout))
        form_layout.addWidget(resource_card)

        scroll.setWidget(form)
        self.add_content(scroll)

        # Buttons
        self.add_button("Cancel", ButtonVariant.STANDARD, self.reject)
        self.add_button("Submit Job", ButtonVariant.ACCENT, self._on_submit)

    def _wrap_layout(self, layout) -> QWidget:
        """Wrap layout in widget"""
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _on_submit(self):
        """Handle job submission"""
        job_config = {
            "name": self._name_input.text(),
            "description": self._desc_input.text(),
            "type": self._type_combo.currentText(),
            "priority": self._priority_combo.currentText().lower(),
            "resources": {
                "cpu": self._cpu_spin.value(),
                "memory_gb": self._mem_spin.value(),
                "gpu": self._gpu_spin.value() if self._gpu_check.isChecked() else 0,
            },
        }
        self.job_submitted.emit(job_config)
        self.accept()


# ═══════════════════════════════════════════════════════════════════════════════
# POOL CREATION DIALOG
# ═══════════════════════════════════════════════════════════════════════════════


class PoolCreateDialog(FluentDialog):
    """
    Pool creation dialog.
    نافذة إنشاء مجموعة العمال
    """

    pool_created = Signal(dict)

    def __init__(self, parent=None):
        super().__init__("Create Worker Pool", parent, width=520)
        self._setup_content()

    def _setup_content(self):
        """Setup pool creation form"""
        colors = FluentDesignSystem().colors

        # Pool name
        name_card = FluentCard("Pool Information")
        name_layout = QVBoxLayout()

        name_label = QLabel("Pool Name:")
        name_label.setStyleSheet(f"color: {colors.text_secondary};")
        name_layout.addWidget(name_label)

        self._name_input = FluentInput("Enter pool name (e.g., gpu-workers)")
        name_layout.addWidget(self._name_input)

        desc_label = QLabel("Description:")
        desc_label.setStyleSheet(f"color: {colors.text_secondary}; margin-top: 8px;")
        name_layout.addWidget(desc_label)

        self._desc_input = FluentInput("Enter pool description")
        name_layout.addWidget(self._desc_input)

        name_card.add_content(self._wrap_layout(name_layout))
        self.add_content(name_card)

        # Scaling configuration
        scaling_card = FluentCard("Scaling Configuration")
        scaling_layout = QVBoxLayout()

        # Min workers
        min_layout = QHBoxLayout()
        min_label = QLabel("Min Workers:")
        min_label.setFixedWidth(120)
        min_label.setStyleSheet(f"color: {colors.text_secondary};")
        min_layout.addWidget(min_label)

        self._min_spin = QSpinBox()
        self._min_spin.setRange(0, 1000)
        self._min_spin.setValue(1)
        self._min_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """
        )
        min_layout.addWidget(self._min_spin)
        min_layout.addStretch()
        scaling_layout.addLayout(min_layout)

        # Max workers
        max_layout = QHBoxLayout()
        max_label = QLabel("Max Workers:")
        max_label.setFixedWidth(120)
        max_label.setStyleSheet(f"color: {colors.text_secondary};")
        max_layout.addWidget(max_label)

        self._max_spin = QSpinBox()
        self._max_spin.setRange(1, 10000)
        self._max_spin.setValue(10)
        self._max_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """
        )
        max_layout.addWidget(self._max_spin)
        max_layout.addStretch()
        scaling_layout.addLayout(max_layout)

        # Auto-scaling
        autoscale_layout = QHBoxLayout()
        self._autoscale_check = QCheckBox("Enable auto-scaling")
        self._autoscale_check.setStyleSheet(f"color: {colors.text_secondary};")
        autoscale_layout.addWidget(self._autoscale_check)
        autoscale_layout.addStretch()
        scaling_layout.addLayout(autoscale_layout)

        scaling_card.add_content(self._wrap_layout(scaling_layout))
        self.add_content(scaling_card)

        # Worker requirements
        req_card = FluentCard("Worker Requirements")
        req_layout = QVBoxLayout()

        # Tags
        tags_label = QLabel("Required Tags (comma-separated):")
        tags_label.setStyleSheet(f"color: {colors.text_secondary};")
        req_layout.addWidget(tags_label)

        self._tags_input = FluentInput("e.g., gpu, cuda, high-memory")
        req_layout.addWidget(self._tags_input)

        # Labels
        labels_label = QLabel("Labels (key=value, comma-separated):")
        labels_label.setStyleSheet(f"color: {colors.text_secondary}; margin-top: 8px;")
        req_layout.addWidget(labels_label)

        self._labels_input = FluentInput("e.g., zone=us-east-1, env=production")
        req_layout.addWidget(self._labels_input)

        req_card.add_content(self._wrap_layout(req_layout))
        self.add_content(req_card)

        # Buttons
        self.add_button("Cancel", ButtonVariant.STANDARD, self.reject)
        self.add_button("Create Pool", ButtonVariant.ACCENT, self._on_create)

    def _wrap_layout(self, layout) -> QWidget:
        """Wrap layout in widget"""
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _on_create(self):
        """Handle pool creation"""
        # Parse tags
        tags = [t.strip() for t in self._tags_input.text().split(",") if t.strip()]

        # Parse labels
        labels = {}
        for item in self._labels_input.text().split(","):
            if "=" in item:
                key, value = item.split("=", 1)
                labels[key.strip()] = value.strip()

        pool_config = {
            "name": self._name_input.text(),
            "description": self._desc_input.text(),
            "min_workers": self._min_spin.value(),
            "max_workers": self._max_spin.value(),
            "auto_scaling": self._autoscale_check.isChecked(),
            "tags": tags,
            "labels": labels,
        }
        self.pool_created.emit(pool_config)
        self.accept()


# ═══════════════════════════════════════════════════════════════════════════════
# QUEUE CREATION DIALOG
# ═══════════════════════════════════════════════════════════════════════════════


class QueueCreateDialog(FluentDialog):
    """
    Queue creation dialog.
    نافذة إنشاء طابور المهام
    """

    queue_created = Signal(dict)

    def __init__(self, parent=None):
        super().__init__("Create Job Queue", parent, width=520)
        self._setup_content()

    def _setup_content(self):
        """Setup queue creation form"""
        colors = FluentDesignSystem().colors

        # Queue name
        name_card = FluentCard("Queue Information")
        name_layout = QVBoxLayout()

        name_label = QLabel("Queue Name:")
        name_label.setStyleSheet(f"color: {colors.text_secondary};")
        name_layout.addWidget(name_label)

        self._name_input = FluentInput("Enter queue name (e.g., high-priority)")
        name_layout.addWidget(self._name_input)

        desc_label = QLabel("Description:")
        desc_label.setStyleSheet(f"color: {colors.text_secondary}; margin-top: 8px;")
        name_layout.addWidget(desc_label)

        self._desc_input = FluentInput("Enter queue description")
        name_layout.addWidget(self._desc_input)

        name_card.add_content(self._wrap_layout(name_layout))
        self.add_content(name_card)

        # Priority settings
        priority_card = FluentCard("Priority Settings")
        priority_layout = QVBoxLayout()

        # Base priority
        base_layout = QHBoxLayout()
        base_label = QLabel("Base Priority:")
        base_label.setFixedWidth(120)
        base_label.setStyleSheet(f"color: {colors.text_secondary};")
        base_layout.addWidget(base_label)

        self._priority_combo = QComboBox()
        self._priority_combo.addItems(["Low", "Normal", "High", "Critical"])
        self._priority_combo.setCurrentIndex(1)
        self._priority_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px 12px;
            }}
        """
        )
        base_layout.addWidget(self._priority_combo)
        base_layout.addStretch()
        priority_layout.addLayout(base_layout)

        # Weight
        weight_layout = QHBoxLayout()
        weight_label = QLabel("Weight:")
        weight_label.setFixedWidth(120)
        weight_label.setStyleSheet(f"color: {colors.text_secondary};")
        weight_layout.addWidget(weight_label)

        self._weight_spin = QSpinBox()
        self._weight_spin.setRange(1, 100)
        self._weight_spin.setValue(10)
        self._weight_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """
        )
        weight_layout.addWidget(self._weight_spin)
        weight_layout.addStretch()
        priority_layout.addLayout(weight_layout)

        priority_card.add_content(self._wrap_layout(priority_layout))
        self.add_content(priority_card)

        # Limits
        limits_card = FluentCard("Queue Limits")
        limits_layout = QVBoxLayout()

        # Max jobs
        max_jobs_layout = QHBoxLayout()
        max_jobs_label = QLabel("Max Jobs:")
        max_jobs_label.setFixedWidth(120)
        max_jobs_label.setStyleSheet(f"color: {colors.text_secondary};")
        max_jobs_layout.addWidget(max_jobs_label)

        self._max_jobs_spin = QSpinBox()
        self._max_jobs_spin.setRange(0, 100000)
        self._max_jobs_spin.setValue(1000)
        self._max_jobs_spin.setSpecialValueText("Unlimited")
        self._max_jobs_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """
        )
        max_jobs_layout.addWidget(self._max_jobs_spin)
        max_jobs_layout.addStretch()
        limits_layout.addLayout(max_jobs_layout)

        # Max concurrent
        max_concurrent_layout = QHBoxLayout()
        max_concurrent_label = QLabel("Max Concurrent:")
        max_concurrent_label.setFixedWidth(120)
        max_concurrent_label.setStyleSheet(f"color: {colors.text_secondary};")
        max_concurrent_layout.addWidget(max_concurrent_label)

        self._max_concurrent_spin = QSpinBox()
        self._max_concurrent_spin.setRange(0, 10000)
        self._max_concurrent_spin.setValue(100)
        self._max_concurrent_spin.setSpecialValueText("Unlimited")
        self._max_concurrent_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """
        )
        max_concurrent_layout.addWidget(self._max_concurrent_spin)
        max_concurrent_layout.addStretch()
        limits_layout.addLayout(max_concurrent_layout)

        limits_card.add_content(self._wrap_layout(limits_layout))
        self.add_content(limits_card)

        # Target pool
        pool_card = FluentCard("Target Pool (Optional)")
        pool_layout = QVBoxLayout()

        pool_label = QLabel("Target Worker Pool:")
        pool_label.setStyleSheet(f"color: {colors.text_secondary};")
        pool_layout.addWidget(pool_label)

        self._pool_input = FluentInput("Enter pool name (leave empty for any pool)")
        pool_layout.addWidget(self._pool_input)

        pool_card.add_content(self._wrap_layout(pool_layout))
        self.add_content(pool_card)

        # Buttons
        self.add_button("Cancel", ButtonVariant.STANDARD, self.reject)
        self.add_button("Create Queue", ButtonVariant.ACCENT, self._on_create)

    def _wrap_layout(self, layout) -> QWidget:
        """Wrap layout in widget"""
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _on_create(self):
        """Handle queue creation"""
        queue_config = {
            "name": self._name_input.text(),
            "description": self._desc_input.text(),
            "priority": self._priority_combo.currentText().lower(),
            "weight": self._weight_spin.value(),
            "max_jobs": self._max_jobs_spin.value() if self._max_jobs_spin.value() > 0 else None,
            "max_concurrent": self._max_concurrent_spin.value() if self._max_concurrent_spin.value() > 0 else None,
            "target_pool": self._pool_input.text() if self._pool_input.text() else None,
        }
        self.queue_created.emit(queue_config)
        self.accept()


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "FluentDialog",
    "ConnectionDialog",
    "ConfirmationDialog",
    "ConfirmationType",
    "ProgressDialog",
    "InputDialog",
    "JobSubmitDialog",
    "ConnectionProfile",
    "PoolCreateDialog",
    "QueueCreateDialog",
]
