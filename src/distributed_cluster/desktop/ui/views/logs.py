"""
Fluent Logs View
صفحة السجلات بتصميم Fluent

Real-time log viewer with:
- Log level filtering
- Search
- Auto-scroll
- Export
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Any
from enum import Enum

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QComboBox, QCheckBox
)

from ..fluent_design import FluentDesignSystem
from ..components import FluentButton, ButtonVariant


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FluentLogsView(QWidget):
    """
    Real-time log viewer.
    عارض السجلات في الوقت الحقيقي
    """

    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._auto_scroll = True
        self._logs: List[Dict[str, Any]] = []

        self._setup_ui()
        self._load_demo_logs()

    def _setup_ui(self):
        """Setup view UI"""
        colors = FluentDesignSystem().colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()

        title = QLabel("Logs")
        title.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 28px;
            font-weight: 600;
        """)
        header.addWidget(title)

        header.addStretch()

        # Level filter
        level_label = QLabel("Level:")
        level_label.setStyleSheet(f"color: {colors.text_secondary};")
        header.addWidget(level_label)

        self._level_combo = QComboBox()
        self._level_combo.addItems(["All", "Debug", "Info", "Warning", "Error"])
        self._level_combo.setMinimumWidth(120)
        self._level_combo.currentTextChanged.connect(self._filter_logs)
        self._level_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 6px 12px;
            }}
        """)
        header.addWidget(self._level_combo)

        # Auto-scroll
        self._auto_scroll_check = QCheckBox("Auto-scroll")
        self._auto_scroll_check.setChecked(True)
        self._auto_scroll_check.setStyleSheet(f"color: {colors.text_secondary};")
        self._auto_scroll_check.toggled.connect(self._on_auto_scroll_changed)
        header.addWidget(self._auto_scroll_check)

        # Clear button
        clear_btn = FluentButton("Clear", "", ButtonVariant.SUBTLE)
        clear_btn.clicked.connect(self._clear_logs)
        header.addWidget(clear_btn)

        # Export button
        export_btn = FluentButton("Export", "", ButtonVariant.SUBTLE)
        export_btn.clicked.connect(self._export_logs)
        header.addWidget(export_btn)

        layout.addLayout(header)

        # Log viewer
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(10000)
        self._log_view.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {colors.bg_solid_base};
                color: {colors.text_primary};
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 12px;
                border: 1px solid {colors.stroke_surface};
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        layout.addWidget(self._log_view, 1)

        # Status bar
        status = QHBoxLayout()

        self._log_count = QLabel("0 log entries")
        self._log_count.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        status.addWidget(self._log_count)

        status.addStretch()

        self._connection_status = QLabel("Connected")
        self._connection_status.setStyleSheet(f"color: {colors.success}; font-size: 12px;")
        status.addWidget(self._connection_status)

        layout.addLayout(status)

    def _load_demo_logs(self):
        """Load demo log entries"""
        demo_logs = [
            {"level": "info", "timestamp": datetime.now(), "source": "master", "message": "Master node started on 0.0.0.0:8765"},
            {"level": "info", "timestamp": datetime.now(), "source": "worker-01", "message": "Worker connected from 192.168.1.101"},
            {"level": "info", "timestamp": datetime.now(), "source": "worker-02", "message": "Worker connected from 192.168.1.102"},
            {"level": "info", "timestamp": datetime.now(), "source": "scheduler", "message": "Scheduler initialized with 'best-fit' policy"},
            {"level": "debug", "timestamp": datetime.now(), "source": "api", "message": "API endpoint /jobs registered"},
            {"level": "info", "timestamp": datetime.now(), "source": "master", "message": "Job job-001 submitted: 'Training Model v2'"},
            {"level": "info", "timestamp": datetime.now(), "source": "scheduler", "message": "Job job-001 assigned to worker-01"},
            {"level": "debug", "timestamp": datetime.now(), "source": "worker-01", "message": "Starting container for job-001"},
            {"level": "info", "timestamp": datetime.now(), "source": "worker-01", "message": "Job job-001 started execution"},
            {"level": "warning", "timestamp": datetime.now(), "source": "worker-02", "message": "Memory usage above 80% threshold"},
            {"level": "info", "timestamp": datetime.now(), "source": "master", "message": "Job job-002 completed successfully"},
            {"level": "error", "timestamp": datetime.now(), "source": "worker-03", "message": "Connection lost to worker-03"},
        ]

        for log in demo_logs:
            self.append_log(log)

    def append_log(self, log: Dict[str, Any]):
        """Append a log entry"""
        colors = FluentDesignSystem().colors

        self._logs.append(log)

        level = log.get("level", "info").upper()
        timestamp = log.get("timestamp", datetime.now())
        if isinstance(timestamp, datetime):
            timestamp = timestamp.strftime("%H:%M:%S")
        source = log.get("source", "system")
        message = log.get("message", "")

        # Color based on level
        level_colors = {
            "DEBUG": colors.text_tertiary,
            "INFO": colors.info,
            "WARNING": colors.warning,
            "ERROR": colors.error,
        }
        level_colors.get(level, colors.text_primary)

        # Format log line
        line = f"[{timestamp}] [{level:7}] [{source}] {message}"

        self._log_view.appendPlainText(line)

        # Auto-scroll
        if self._auto_scroll:
            scrollbar = self._log_view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        # Update count
        self._log_count.setText(f"{len(self._logs)} log entries")

    def _filter_logs(self, level: str):
        """Filter logs by level"""
        # Would filter displayed logs
        pass

    def _on_auto_scroll_changed(self, checked: bool):
        """Handle auto-scroll toggle"""
        self._auto_scroll = checked

    def _clear_logs(self):
        """Clear all logs"""
        self._logs.clear()
        self._log_view.clear()
        self._log_count.setText("0 log entries")

    def _export_logs(self):
        """Export logs to file"""
        # Would show file dialog
        pass
