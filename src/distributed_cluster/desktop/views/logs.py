"""
Logs View - System logs viewer
صفحة عرض السجلات
"""

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..api.client import APIClient
from ..resources.styles import COLORS


class LogsView(QWidget):
    """System logs viewer"""

    refresh_requested = Signal()

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._setup_ui()

    def _setup_ui(self):
        """Setup logs view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("System Logs")
        title.setStyleSheet(
            f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """
        )
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Filter by level
        level_label = QLabel("Level:")
        level_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        header_layout.addWidget(level_label)

        self.level_combo = QComboBox()
        self.level_combo.addItems(["All", "Debug", "Info", "Warning", "Error"])
        self.level_combo.currentTextChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.level_combo)

        # Filter by source
        source_label = QLabel("Source:")
        source_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        header_layout.addWidget(source_label)

        self.source_combo = QComboBox()
        self.source_combo.addItems(["All", "Master", "Worker", "Scheduler", "API"])
        self.source_combo.currentTextChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.source_combo)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondary_button")
        refresh_btn.clicked.connect(self._on_refresh)
        header_layout.addWidget(refresh_btn)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("danger_button")
        clear_btn.clicked.connect(self._on_clear)
        header_layout.addWidget(clear_btn)

        layout.addLayout(header_layout)

        # Logs text area
        self.logs_text = QPlainTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setStyleSheet(
            f"""
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 12px;
            background-color: {COLORS['bg_dark']};
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['border']};
            border-radius: 8px;
        """
        )
        self.logs_text.setPlaceholderText("No logs to display.\n\nConnect to a master server to view system logs.")
        layout.addWidget(self.logs_text)

        # Status bar
        status_layout = QHBoxLayout()

        self.status_label = QLabel("0 log entries")
        self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        # Auto-scroll checkbox
        self.auto_scroll_btn = QPushButton("Auto-scroll: ON")
        self.auto_scroll_btn.setObjectName("secondary_button")
        self.auto_scroll_btn.setCheckable(True)
        self.auto_scroll_btn.setChecked(True)
        self.auto_scroll_btn.clicked.connect(self._toggle_auto_scroll)
        status_layout.addWidget(self.auto_scroll_btn)

        layout.addLayout(status_layout)

        self._auto_scroll = True

    def append_log(self, message: str, level: str = "info"):
        """Append a log message"""
        # Color based on level
        level_colors = {
            "debug": COLORS["text_muted"],
            "info": COLORS["text_primary"],
            "warning": COLORS["warning"],
            "error": COLORS["danger"],
        }
        color = level_colors.get(level.lower(), COLORS["text_primary"])

        # Format and append
        self.logs_text.appendHtml(f'<span style="color: {color}">{message}</span>')

        # Auto-scroll if enabled
        if self._auto_scroll:
            scrollbar = self.logs_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        # Update status
        line_count = self.logs_text.document().blockCount()
        self.status_label.setText(f"{line_count} log entries")

    def set_logs(self, logs: list):
        """Set logs from list"""
        self.logs_text.clear()
        for log in logs:
            level = log.get("level", "info")
            message = log.get("message", "")
            timestamp = log.get("timestamp", "")
            source = log.get("source", "")

            formatted = f"[{timestamp}] [{source}] [{level.upper()}] {message}"
            self.append_log(formatted, level)

    def _on_filter_changed(self, _):
        """Handle filter change"""
        self.refresh_requested.emit()

    def _on_refresh(self):
        """Handle refresh"""
        self.refresh_requested.emit()

    def _on_clear(self):
        """Clear logs"""
        self.logs_text.clear()
        self.status_label.setText("0 log entries")

    def _toggle_auto_scroll(self):
        """Toggle auto-scroll"""
        self._auto_scroll = self.auto_scroll_btn.isChecked()
        self.auto_scroll_btn.setText(f"Auto-scroll: {'ON' if self._auto_scroll else 'OFF'}")

    def get_filter_level(self) -> Optional[str]:
        """Get current level filter"""
        level = self.level_combo.currentText()
        return None if level == "All" else level.lower()

    def get_filter_source(self) -> Optional[str]:
        """Get current source filter"""
        source = self.source_combo.currentText()
        return None if source == "All" else source.lower()

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
