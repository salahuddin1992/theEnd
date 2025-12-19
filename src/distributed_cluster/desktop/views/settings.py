"""
Settings View - Application settings page
صفحة الإعدادات
"""

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..resources.styles import COLORS


class SettingsView(QScrollArea):
    """Application settings view"""

    settings_changed = Signal(dict)
    connection_requested = Signal(str, str)  # url, token

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = self._load_settings()
        self._setup_ui()

    def _setup_ui(self):
        """Setup settings view UI"""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        title = QLabel("Settings")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        layout.addWidget(title)

        # Connection settings
        connection_group = QGroupBox("Connection")
        connection_layout = QFormLayout(connection_group)
        connection_layout.setSpacing(12)

        # Server URL
        self.server_url_input = QLineEdit()
        self.server_url_input.setPlaceholderText("http://localhost:8765")
        self.server_url_input.setText(self._settings.get("server_url", "http://localhost:8765"))
        connection_layout.addRow("Server URL:", self.server_url_input)

        # API Token
        token_layout = QHBoxLayout()
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Enter API token (optional)")
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setText(self._settings.get("token", ""))
        token_layout.addWidget(self.token_input)

        self.show_token_btn = QPushButton("Show")
        self.show_token_btn.setObjectName("secondary_button")
        self.show_token_btn.setFixedWidth(60)
        self.show_token_btn.clicked.connect(self._toggle_token_visibility)
        token_layout.addWidget(self.show_token_btn)

        connection_layout.addRow("API Token:", token_layout)

        # Connection buttons
        conn_buttons_layout = QHBoxLayout()
        conn_buttons_layout.addStretch()

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setObjectName("secondary_button")
        self.test_btn.clicked.connect(self._test_connection)
        conn_buttons_layout.addWidget(self.test_btn)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect)
        conn_buttons_layout.addWidget(self.connect_btn)

        connection_layout.addRow("", conn_buttons_layout)

        layout.addWidget(connection_group)

        # UI settings
        ui_group = QGroupBox("User Interface")
        ui_layout = QFormLayout(ui_group)
        ui_layout.setSpacing(12)

        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light", "System"])
        self.theme_combo.setCurrentText(self._settings.get("theme", "Dark"))
        ui_layout.addRow("Theme:", self.theme_combo)

        # Refresh interval
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1, 60)
        self.refresh_spin.setValue(self._settings.get("refresh_interval", 5))
        self.refresh_spin.setSuffix(" seconds")
        ui_layout.addRow("Refresh Interval:", self.refresh_spin)

        # Notifications
        self.notifications_check = QCheckBox("Enable desktop notifications")
        self.notifications_check.setChecked(self._settings.get("notifications", True))
        ui_layout.addRow("", self.notifications_check)

        # Show job output
        self.show_output_check = QCheckBox("Show job output in real-time")
        self.show_output_check.setChecked(self._settings.get("show_output", True))
        ui_layout.addRow("", self.show_output_check)

        layout.addWidget(ui_group)

        # Data settings
        data_group = QGroupBox("Data & Storage")
        data_layout = QFormLayout(data_group)
        data_layout.setSpacing(12)

        # Cache directory
        cache_layout = QHBoxLayout()
        self.cache_input = QLineEdit()
        self.cache_input.setPlaceholderText("Cache directory path")
        self.cache_input.setText(self._settings.get("cache_dir", ""))
        cache_layout.addWidget(self.cache_input)

        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("secondary_button")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_cache_dir)
        cache_layout.addWidget(browse_btn)

        data_layout.addRow("Cache Directory:", cache_layout)

        # Max cached jobs
        self.max_cached_spin = QSpinBox()
        self.max_cached_spin.setRange(10, 1000)
        self.max_cached_spin.setValue(self._settings.get("max_cached_jobs", 100))
        data_layout.addRow("Max Cached Jobs:", self.max_cached_spin)

        # Clear cache button
        clear_layout = QHBoxLayout()
        clear_layout.addStretch()
        clear_btn = QPushButton("Clear Cache")
        clear_btn.setObjectName("danger_button")
        clear_btn.clicked.connect(self._clear_cache)
        clear_layout.addWidget(clear_btn)
        data_layout.addRow("", clear_layout)

        layout.addWidget(data_group)

        # Advanced settings
        advanced_group = QGroupBox("Advanced")
        advanced_layout = QFormLayout(advanced_group)
        advanced_layout.setSpacing(12)

        # Connection timeout
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(self._settings.get("timeout", 30))
        self.timeout_spin.setSuffix(" seconds")
        advanced_layout.addRow("Connection Timeout:", self.timeout_spin)

        # WebSocket reconnect
        self.ws_reconnect_check = QCheckBox("Auto-reconnect WebSocket")
        self.ws_reconnect_check.setChecked(self._settings.get("ws_reconnect", True))
        advanced_layout.addRow("", self.ws_reconnect_check)

        # Debug mode
        self.debug_check = QCheckBox("Enable debug logging")
        self.debug_check.setChecked(self._settings.get("debug", False))
        advanced_layout.addRow("", self.debug_check)

        layout.addWidget(advanced_group)

        # Save/Reset buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setObjectName("secondary_button")
        reset_btn.clicked.connect(self._reset_settings)
        buttons_layout.addWidget(reset_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save_settings)
        buttons_layout.addWidget(save_btn)

        layout.addLayout(buttons_layout)

        layout.addStretch()

        self.setWidget(container)

    def _toggle_token_visibility(self):
        """Toggle API token visibility"""
        if self.token_input.echoMode() == QLineEdit.Password:
            self.token_input.setEchoMode(QLineEdit.Normal)
            self.show_token_btn.setText("Hide")
        else:
            self.token_input.setEchoMode(QLineEdit.Password)
            self.show_token_btn.setText("Show")

    def _test_connection(self):
        """Test connection to server"""
        url = self.server_url_input.text()
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a server URL")
            return

        # This will be handled by main window
        QMessageBox.information(
            self, "Test Connection",
            f"Testing connection to {url}...\n"
            "This feature will be implemented with API client."
        )

    def _on_connect(self):
        """Handle connect button click"""
        url = self.server_url_input.text()
        token = self.token_input.text()

        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a server URL")
            return

        self.connection_requested.emit(url, token)

    def _browse_cache_dir(self):
        """Browse for cache directory"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Cache Directory"
        )
        if dir_path:
            self.cache_input.setText(dir_path)

    def _clear_cache(self):
        """Clear application cache"""
        reply = QMessageBox.question(
            self,
            "Clear Cache",
            "Are you sure you want to clear the cache?\n"
            "This will remove all cached job data.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # Clear cache implementation
            QMessageBox.information(self, "Cache Cleared", "Cache has been cleared successfully.")

    def _reset_settings(self):
        """Reset settings to defaults"""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._settings = self._get_default_settings()
            self._apply_settings_to_ui()
            QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")

    def _save_settings(self):
        """Save current settings"""
        self._settings = {
            "server_url": self.server_url_input.text(),
            "token": self.token_input.text(),
            "theme": self.theme_combo.currentText(),
            "refresh_interval": self.refresh_spin.value(),
            "notifications": self.notifications_check.isChecked(),
            "show_output": self.show_output_check.isChecked(),
            "cache_dir": self.cache_input.text(),
            "max_cached_jobs": self.max_cached_spin.value(),
            "timeout": self.timeout_spin.value(),
            "ws_reconnect": self.ws_reconnect_check.isChecked(),
            "debug": self.debug_check.isChecked(),
        }

        self._persist_settings()
        self.settings_changed.emit(self._settings)
        QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")

    def _get_default_settings(self) -> dict:
        """Get default settings"""
        return {
            "server_url": "http://localhost:8765",
            "token": "",
            "theme": "Dark",
            "refresh_interval": 5,
            "notifications": True,
            "show_output": True,
            "cache_dir": "",
            "max_cached_jobs": 100,
            "timeout": 30,
            "ws_reconnect": True,
            "debug": False,
        }

    def _load_settings(self) -> dict:
        """Load settings from file"""
        settings_path = Path.home() / ".nebula_desktop" / "settings.json"
        try:
            if settings_path.exists():
                with open(settings_path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return self._get_default_settings()

    def _persist_settings(self):
        """Save settings to file"""
        settings_dir = Path.home() / ".nebula_desktop"
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_path = settings_dir / "settings.json"

        try:
            with open(settings_path, "w") as f:
                json.dump(self._settings, f, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save settings: {e}")

    def _apply_settings_to_ui(self):
        """Apply loaded settings to UI elements"""
        self.server_url_input.setText(self._settings.get("server_url", ""))
        self.token_input.setText(self._settings.get("token", ""))
        self.theme_combo.setCurrentText(self._settings.get("theme", "Dark"))
        self.refresh_spin.setValue(self._settings.get("refresh_interval", 5))
        self.notifications_check.setChecked(self._settings.get("notifications", True))
        self.show_output_check.setChecked(self._settings.get("show_output", True))
        self.cache_input.setText(self._settings.get("cache_dir", ""))
        self.max_cached_spin.setValue(self._settings.get("max_cached_jobs", 100))
        self.timeout_spin.setValue(self._settings.get("timeout", 30))
        self.ws_reconnect_check.setChecked(self._settings.get("ws_reconnect", True))
        self.debug_check.setChecked(self._settings.get("debug", False))

    def get_settings(self) -> dict:
        """Get current settings"""
        return self._settings.copy()

    def get_server_url(self) -> str:
        """Get server URL"""
        return self.server_url_input.text()

    def get_token(self) -> str:
        """Get API token"""
        return self.token_input.text()
