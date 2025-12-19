"""
Login Dialog - Authentication interface
نافذة تسجيل الدخول
"""

import hashlib
import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..resources.styles import COLORS


class LoginDialog(QDialog):
    """Login dialog for user authentication"""

    login_successful = Signal(str, str, dict)  # username, token, user_info

    def __init__(self, parent=None):
        super().__init__(parent)
        self._credentials = self._load_saved_credentials()
        self._setup_ui()

    def _setup_ui(self):
        """Setup login dialog UI"""
        self.setWindowTitle("Login - NebulaCompute")
        self.setFixedSize(420, 520)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Main container with rounded corners
        container = QFrame(self)
        container.setGeometry(0, 0, 420, 520)
        container.setStyleSheet(
            f"""
            QFrame {{
                background-color: {COLORS['bg_dark']};
                border: 1px solid {COLORS['border']};
                border-radius: 16px;
            }}
        """
        )

        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_muted']};
                border: none;
                font-size: 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {COLORS['danger']};
            }}
        """
        )
        close_btn.clicked.connect(self.reject)

        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_layout.addWidget(close_btn)
        layout.addLayout(close_layout)

        # Logo
        logo_label = QLabel("☁")
        logo_label.setStyleSheet(
            f"""
            font-size: 48px;
            color: {COLORS['primary']};
        """
        )
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        # Title
        title = QLabel("NebulaCompute")
        title.setStyleSheet(
            f"""
            font-size: 24px;
            font-weight: bold;
            color: {COLORS['text_primary']};
        """
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Sign in to your account")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        # Username field
        username_label = QLabel("Username")
        username_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(username_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        self.username_input.setStyleSheet(self._input_style())
        if self._credentials.get("username"):
            self.username_input.setText(self._credentials["username"])
        layout.addWidget(self.username_input)

        # Password field
        password_label = QLabel("Password")
        password_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(password_label)

        password_layout = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet(self._input_style())
        self.password_input.returnPressed.connect(self._on_login)
        password_layout.addWidget(self.password_input)

        show_pass_btn = QPushButton("👁")
        show_pass_btn.setFixedSize(44, 44)
        show_pass_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['bg_medium']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_light']};
            }}
        """
        )
        show_pass_btn.pressed.connect(lambda: self.password_input.setEchoMode(QLineEdit.Normal))
        show_pass_btn.released.connect(lambda: self.password_input.setEchoMode(QLineEdit.Password))
        password_layout.addWidget(show_pass_btn)

        layout.addLayout(password_layout)

        # Remember me checkbox
        self.remember_check = QCheckBox("Remember me")
        self.remember_check.setChecked(self._credentials.get("remember", False))
        self.remember_check.setStyleSheet(
            f"""
            QCheckBox {{
                color: {COLORS['text_secondary']};
                font-size: 13px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid {COLORS['border']};
                background-color: {COLORS['bg_medium']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLORS['primary']};
                border-color: {COLORS['primary']};
            }}
        """
        )
        layout.addWidget(self.remember_check)

        layout.addSpacing(10)

        # Login button
        self.login_btn = QPushButton("Sign In")
        self.login_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: {COLORS['text_primary']};
                border: none;
                border-radius: 8px;
                padding: 14px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary_hover']};
            }}
            QPushButton:disabled {{
                background-color: {COLORS['secondary']};
            }}
        """
        )
        self.login_btn.clicked.connect(self._on_login)
        layout.addWidget(self.login_btn)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {COLORS['bg_light']};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['primary']};
                border-radius: 2px;
            }}
        """
        )
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color: {COLORS['danger']}; font-size: 12px;")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        layout.addStretch()

        # Skip login option
        skip_btn = QPushButton("Continue without login")
        skip_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_muted']};
                border: none;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {COLORS['text_secondary']};
                text-decoration: underline;
            }}
        """
        )
        skip_btn.clicked.connect(self._on_skip)
        layout.addWidget(skip_btn)

    def _input_style(self) -> str:
        """Get input field style"""
        return f"""
            QLineEdit {{
                background-color: {COLORS['bg_medium']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 12px;
                color: {COLORS['text_primary']};
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['primary']};
            }}
        """

    def _on_login(self):
        """Handle login attempt"""
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username:
            self._show_error("Please enter your username")
            return

        if not password:
            self._show_error("Please enter your password")
            return

        # Show loading state
        self.login_btn.setEnabled(False)
        self.login_btn.setText("Signing in...")
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.show()
        self.error_label.hide()

        # Simulate authentication (in real app, this would call API)
        QTimer.singleShot(1500, lambda: self._complete_login(username, password))

    def _complete_login(self, username: str, password: str):
        """Complete the login process"""
        self.progress_bar.hide()
        self.login_btn.setEnabled(True)
        self.login_btn.setText("Sign In")

        # In a real app, verify credentials with server
        # For now, accept any non-empty credentials
        token = self._generate_token(username, password)

        # Save credentials if remember is checked
        if self.remember_check.isChecked():
            self._save_credentials(username)
        else:
            self._clear_saved_credentials()

        user_info = {
            "username": username,
            "role": "admin",  # Would come from server
        }

        self.login_successful.emit(username, token, user_info)
        self.accept()

    def _generate_token(self, username: str, password: str) -> str:
        """Generate a simple token (in real app, server would provide this)"""
        data = f"{username}:{password}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _on_skip(self):
        """Skip login and continue as guest"""
        self.login_successful.emit("guest", "", {"username": "guest", "role": "readonly"})
        self.accept()

    def _show_error(self, message: str):
        """Show error message"""
        self.error_label.setText(message)
        self.error_label.show()

    def _load_saved_credentials(self) -> dict:
        """Load saved credentials"""
        config_path = Path.home() / ".nebula_desktop" / "credentials.json"
        try:
            if config_path.exists():
                with open(config_path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_credentials(self, username: str):
        """Save credentials"""
        config_dir = Path.home() / ".nebula_desktop"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "credentials.json"

        try:
            with open(config_path, "w") as f:
                json.dump({"username": username, "remember": True}, f)
        except Exception:
            pass

    def _clear_saved_credentials(self):
        """Clear saved credentials"""
        config_path = Path.home() / ".nebula_desktop" / "credentials.json"
        try:
            if config_path.exists():
                config_path.unlink()
        except Exception:
            pass

    # Make dialog draggable
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
