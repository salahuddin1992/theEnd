"""
Connection Dialog - Server connection interface
نافذة الاتصال بالخادم
"""

import json
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..resources.styles import COLORS


class ServerItem(QFrame):
    """A saved server item widget"""

    clicked = Signal(dict)
    delete_requested = Signal(str)

    def __init__(self, server_data: dict, parent=None):
        super().__init__(parent)
        self._data = server_data
        self._setup_ui()

    def _setup_ui(self):
        """Setup item UI"""
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {COLORS['bg_medium']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 12px;
            }}
            QFrame:hover {{
                border-color: {COLORS['primary']};
                background-color: {COLORS['bg_light']};
            }}
        """
        )
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # Server info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        name_label = QLabel(self._data.get("name", "Unknown Server"))
        name_label.setStyleSheet(f"font-weight: 600; color: {COLORS['text_primary']}; font-size: 14px;")
        info_layout.addWidget(name_label)

        url_label = QLabel(self._data.get("url", ""))
        url_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        info_layout.addWidget(url_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        # Delete button
        delete_btn = QPushButton("×")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_muted']};
                border: none;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {COLORS['danger']};
            }}
        """
        )
        delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(delete_btn)

    def mousePressEvent(self, event):
        """Handle mouse click"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._data)
        super().mousePressEvent(event)

    def _on_delete(self):
        """Handle delete button"""
        self.delete_requested.emit(self._data.get("url", ""))


class ConnectionDialog(QDialog):
    """Dialog for connecting to a master server"""

    connection_requested = Signal(str, str, str)  # url, token, name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._saved_servers = self._load_saved_servers()
        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI"""
        self.setWindowTitle("Connect to Server")
        self.setFixedSize(500, 600)
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {COLORS['bg_dark']};
            }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(8)

        logo_label = QLabel("☁ NebulaCompute")
        logo_label.setStyleSheet(
            f"""
            font-size: 24px;
            font-weight: bold;
            color: {COLORS['primary']};
        """
        )
        logo_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(logo_label)

        subtitle = QLabel("Connect to a master server")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        subtitle.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(subtitle)

        layout.addLayout(header_layout)

        # Saved servers section
        if self._saved_servers:
            saved_label = QLabel("Recent Servers")
            saved_label.setStyleSheet(
                f"""
                color: {COLORS['text_secondary']};
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 1px;
            """
            )
            layout.addWidget(saved_label)

            self.servers_container = QVBoxLayout()
            self.servers_container.setSpacing(8)

            for server in self._saved_servers[:5]:  # Show max 5 recent servers
                item = ServerItem(server)
                item.clicked.connect(self._on_server_selected)
                item.delete_requested.connect(self._on_delete_server)
                self.servers_container.addWidget(item)

            layout.addLayout(self.servers_container)

            # Divider
            divider = QFrame()
            divider.setFrameShape(QFrame.HLine)
            divider.setStyleSheet(f"background-color: {COLORS['border']};")
            divider.setFixedHeight(1)
            layout.addWidget(divider)

        # New connection section
        new_label = QLabel("New Connection")
        new_label.setStyleSheet(
            f"""
            color: {COLORS['text_secondary']};
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        """
        )
        layout.addWidget(new_label)

        # Connection form
        form_layout = QVBoxLayout()
        form_layout.setSpacing(16)

        # Server name
        name_layout = QVBoxLayout()
        name_layout.setSpacing(4)
        name_hint = QLabel("Server Name (optional)")
        name_hint.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        name_layout.addWidget(name_hint)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Production Cluster")
        self.name_input.setStyleSheet(
            f"""
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
        )
        name_layout.addWidget(self.name_input)
        form_layout.addLayout(name_layout)

        # Server URL
        url_layout = QVBoxLayout()
        url_layout.setSpacing(4)
        url_hint = QLabel("Server URL")
        url_hint.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        url_layout.addWidget(url_hint)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("http://localhost:8765")
        self.url_input.setText("http://localhost:8765")
        self.url_input.setStyleSheet(
            f"""
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
        )
        url_layout.addWidget(self.url_input)
        form_layout.addLayout(url_layout)

        # API Token
        token_layout = QVBoxLayout()
        token_layout.setSpacing(4)
        token_hint = QLabel("API Token (optional)")
        token_hint.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        token_layout.addWidget(token_hint)

        token_input_layout = QHBoxLayout()
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Enter API token if required")
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setStyleSheet(
            f"""
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
        )
        token_input_layout.addWidget(self.token_input)

        show_token_btn = QPushButton("Show")
        show_token_btn.setFixedWidth(60)
        show_token_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_secondary']};
                border: none;
                border-radius: 8px;
                padding: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['border']};
            }}
        """
        )
        show_token_btn.clicked.connect(self._toggle_token)
        token_input_layout.addWidget(show_token_btn)
        self._show_token_btn = show_token_btn

        token_layout.addLayout(token_input_layout)
        form_layout.addLayout(token_layout)

        # Remember checkbox
        self.remember_check = QCheckBox("Remember this server")
        self.remember_check.setChecked(True)
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
        form_layout.addWidget(self.remember_check)

        layout.addLayout(form_layout)

        layout.addStretch()

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: none;
                border-radius: 8px;
                padding: 14px 28px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['border']};
            }}
        """
        )
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        connect_btn = QPushButton("Connect")
        connect_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: {COLORS['text_primary']};
                border: none;
                border-radius: 8px;
                padding: 14px 28px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary_hover']};
            }}
        """
        )
        connect_btn.clicked.connect(self._on_connect)
        buttons_layout.addWidget(connect_btn)

        layout.addLayout(buttons_layout)

    def _toggle_token(self):
        """Toggle token visibility"""
        if self.token_input.echoMode() == QLineEdit.Password:
            self.token_input.setEchoMode(QLineEdit.Normal)
            self._show_token_btn.setText("Hide")
        else:
            self.token_input.setEchoMode(QLineEdit.Password)
            self._show_token_btn.setText("Show")

    def _on_server_selected(self, server_data: dict):
        """Handle saved server selection"""
        self.url_input.setText(server_data.get("url", ""))
        self.token_input.setText(server_data.get("token", ""))
        self.name_input.setText(server_data.get("name", ""))
        self._on_connect()

    def _on_delete_server(self, url: str):
        """Handle delete server request"""
        self._saved_servers = [s for s in self._saved_servers if s.get("url") != url]
        self._save_servers()
        # Refresh dialog
        self.close()
        new_dialog = ConnectionDialog(self.parent())
        new_dialog.exec()

    def _on_connect(self):
        """Handle connect button click"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a server URL")
            return

        token = self.token_input.text()
        name = self.name_input.text() or url

        # Save server if checkbox is checked
        if self.remember_check.isChecked():
            self._save_server(name, url, token)

        self.connection_requested.emit(url, token, name)
        self.accept()

    def _save_server(self, name: str, url: str, token: str):
        """Save server to recent list"""
        # Remove if already exists
        self._saved_servers = [s for s in self._saved_servers if s.get("url") != url]

        # Add to front
        self._saved_servers.insert(
            0,
            {
                "name": name,
                "url": url,
                "token": token,
            },
        )

        # Keep only last 10
        self._saved_servers = self._saved_servers[:10]

        self._save_servers()

    def _load_saved_servers(self) -> List[dict]:
        """Load saved servers from file"""
        config_path = Path.home() / ".nebula_desktop" / "servers.json"
        try:
            if config_path.exists():
                with open(config_path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_servers(self):
        """Save servers to file"""
        config_dir = Path.home() / ".nebula_desktop"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "servers.json"

        try:
            with open(config_path, "w") as f:
                json.dump(self._saved_servers, f, indent=2)
        except Exception:
            pass

    def get_connection_info(self) -> tuple:
        """Get connection info"""
        return (
            self.url_input.text().strip(),
            self.token_input.text(),
            self.name_input.text() or self.url_input.text().strip(),
        )
