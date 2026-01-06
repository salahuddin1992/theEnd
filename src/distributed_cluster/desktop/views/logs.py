"""
Logs View - Enhanced System logs viewer
صفحة عرض السجلات المحسّنة

Features:
- Syntax Highlighting for logs
- Text and Cards view modes
- Advanced filtering (Search/Level/Source)
- Pause/Resume streaming
- Export to TXT/JSON
- Statistics by level
- Keyboard shortcuts
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from PySide6.QtCore import Signal, Qt, QTimer, QRegularExpression
from PySide6.QtGui import (
    QColor, QTextCharFormat, QFont, QSyntaxHighlighter,
    QTextDocument, QKeySequence, QShortcut
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QFrame,
    QGridLayout,
    QScrollArea,
    QStackedWidget,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QSizePolicy,
    QToolButton,
    QMessageBox,
)

from ..api.client import APIClient
from ..resources.styles import COLORS


# Log level configurations
LOG_LEVELS = {
    "debug": {
        "color": COLORS.get('text_muted', '#64748b'),
        "icon": "🔍",
        "bg": "#64748b15",
    },
    "info": {
        "color": COLORS.get('info', '#3b82f6'),
        "icon": "ℹ️",
        "bg": "#3b82f615",
    },
    "warning": {
        "color": COLORS.get('warning', '#f59e0b'),
        "icon": "⚠️",
        "bg": "#f59e0b15",
    },
    "error": {
        "color": COLORS.get('danger', '#ef4444'),
        "icon": "❌",
        "bg": "#ef444415",
    },
    "critical": {
        "color": "#dc2626",
        "icon": "🔴",
        "bg": "#dc262615",
    },
}


class LogSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for log messages"""

    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._rules = []
        self._setup_rules()

    def _setup_rules(self):
        """Setup highlighting rules"""
        # Timestamp pattern [YYYY-MM-DD HH:MM:SS]
        timestamp_format = QTextCharFormat()
        timestamp_format.setForeground(QColor(COLORS.get('text_secondary', '#94a3b8')))
        self._rules.append((
            QRegularExpression(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?\]'),
            timestamp_format
        ))

        # Log levels
        for level, config in LOG_LEVELS.items():
            level_format = QTextCharFormat()
            level_format.setForeground(QColor(config['color']))
            level_format.setFontWeight(QFont.Bold)
            self._rules.append((
                QRegularExpression(rf'\[{level.upper()}\]', QRegularExpression.CaseInsensitiveOption),
                level_format
            ))

        # Source pattern [Source]
        source_format = QTextCharFormat()
        source_format.setForeground(QColor(COLORS.get('primary', '#3b82f6')))
        self._rules.append((
            QRegularExpression(r'\[(Master|Worker|Scheduler|API|System)\]', QRegularExpression.CaseInsensitiveOption),
            source_format
        ))

        # Strings in quotes
        string_format = QTextCharFormat()
        string_format.setForeground(QColor(COLORS.get('success', '#10b981')))
        self._rules.append((
            QRegularExpression(r'"[^"]*"'),
            string_format
        ))

        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor(COLORS.get('warning', '#f59e0b')))
        self._rules.append((
            QRegularExpression(r'\b\d+(\.\d+)?\b'),
            number_format
        ))

        # IP addresses
        ip_format = QTextCharFormat()
        ip_format.setForeground(QColor(COLORS.get('info', '#3b82f6')))
        self._rules.append((
            QRegularExpression(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?\b'),
            ip_format
        ))

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            match_iter = pattern.globalMatch(text)
            while match_iter.hasNext():
                match = match_iter.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class LogCard(QFrame):
    """Log entry card for cards view"""

    def __init__(self, log_entry: dict, parent=None):
        super().__init__(parent)
        self.log_entry = log_entry
        self.setObjectName("log_card")
        self._setup_ui()

    def _setup_ui(self):
        level = self.log_entry.get("level", "info").lower()
        config = LOG_LEVELS.get(level, LOG_LEVELS["info"])

        self.setStyleSheet(f"""
            QFrame#log_card {{
                background-color: {config['bg']};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-left: 4px solid {config['color']};
                border-radius: 8px;
                padding: 12px;
                margin: 4px 0;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 8, 12, 8)

        # Header row
        header_layout = QHBoxLayout()

        # Level badge
        level_badge = QLabel(f"{config['icon']} {level.upper()}")
        level_badge.setStyleSheet(f"""
            color: {config['color']};
            font-weight: 600;
            font-size: 11px;
        """)
        header_layout.addWidget(level_badge)

        # Source
        source = self.log_entry.get("source", "Unknown")
        source_label = QLabel(f"[{source}]")
        source_label.setStyleSheet(f"""
            color: {COLORS.get('primary', '#3b82f6')};
            font-size: 11px;
        """)
        header_layout.addWidget(source_label)

        header_layout.addStretch()

        # Timestamp
        timestamp = self.log_entry.get("timestamp", "")
        time_label = QLabel(timestamp)
        time_label.setStyleSheet(f"""
            color: {COLORS.get('text_secondary', '#94a3b8')};
            font-size: 11px;
        """)
        header_layout.addWidget(time_label)

        layout.addLayout(header_layout)

        # Message
        message = self.log_entry.get("message", "")
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet(f"""
            color: {COLORS.get('text_primary', '#f1f5f9')};
            font-size: 13px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        """)
        layout.addWidget(message_label)


class LevelStatCard(QFrame):
    """Statistics card for log level"""

    def __init__(self, level: str, count: int = 0, parent=None):
        super().__init__(parent)
        self.level = level
        self._count = count
        self.setObjectName("level_stat")
        self._setup_ui()

    def _setup_ui(self):
        config = LOG_LEVELS.get(self.level.lower(), LOG_LEVELS["info"])

        self.setStyleSheet(f"""
            QFrame#level_stat {{
                background-color: {config['bg']};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 8px;
                padding: 8px 12px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Icon
        icon_label = QLabel(config['icon'])
        icon_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(icon_label)

        # Level name
        level_label = QLabel(self.level.upper())
        level_label.setStyleSheet(f"""
            color: {config['color']};
            font-weight: 600;
            font-size: 11px;
        """)
        layout.addWidget(level_label)

        # Count
        self.count_label = QLabel(str(self._count))
        self.count_label.setStyleSheet(f"""
            color: {COLORS.get('text_primary', '#f1f5f9')};
            font-weight: 700;
            font-size: 14px;
        """)
        layout.addWidget(self.count_label)

    def set_count(self, count: int):
        self._count = count
        self.count_label.setText(str(count))


class LogsView(QWidget):
    """Enhanced system logs viewer"""

    refresh_requested = Signal()

    # Auto-refresh interval for streaming (1 second)
    STREAM_INTERVAL = 1000

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._logs_data: List[Dict] = []
        self._is_streaming = True
        self._auto_scroll = True
        self._current_view = "text"  # "text" or "cards"
        self._setup_ui()
        self._setup_shortcuts()
        self._setup_streaming()

    def _setup_ui(self):
        """Setup logs view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        # Stats row
        self._setup_stats_row(layout)

        # Header with controls
        self._setup_header(layout)

        # Filter bar
        self._setup_filter_bar(layout)

        # Content area
        self.content_stack = QStackedWidget()

        # Text view
        self._setup_text_view()

        # Cards view
        self._setup_cards_view()

        layout.addWidget(self.content_stack, 1)

        # Status bar
        self._setup_status_bar(layout)

    def _setup_stats_row(self, parent_layout: QVBoxLayout):
        """Setup statistics row"""
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)

        self.level_stats = {}
        for level in ["debug", "info", "warning", "error", "critical"]:
            stat_card = LevelStatCard(level, 0)
            stats_layout.addWidget(stat_card)
            self.level_stats[level] = stat_card

        stats_layout.addStretch()

        parent_layout.addLayout(stats_layout)

    def _setup_header(self, parent_layout: QVBoxLayout):
        """Setup header with title and controls"""
        header_layout = QHBoxLayout()

        title = QLabel("System Logs")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        header_layout.addWidget(title)

        header_layout.addStretch()

        # View toggle
        view_toggle_layout = QHBoxLayout()
        view_toggle_layout.setSpacing(0)

        self.text_view_btn = QPushButton("📝")
        self.text_view_btn.setCheckable(True)
        self.text_view_btn.setChecked(True)
        self.text_view_btn.setFixedSize(36, 36)
        self.text_view_btn.setToolTip("Text View (Ctrl+1)")
        self.text_view_btn.clicked.connect(lambda: self._switch_view("text"))

        self.cards_view_btn = QPushButton("🎴")
        self.cards_view_btn.setCheckable(True)
        self.cards_view_btn.setFixedSize(36, 36)
        self.cards_view_btn.setToolTip("Cards View (Ctrl+2)")
        self.cards_view_btn.clicked.connect(lambda: self._switch_view("cards"))

        view_btn_style = f"""
            QPushButton {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                color: {COLORS.get('text_primary', '#f1f5f9')};
                font-size: 16px;
            }}
            QPushButton:checked {{
                background-color: {COLORS.get('primary', '#3b82f6')};
                border-color: {COLORS.get('primary', '#3b82f6')};
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('bg_light', '#273548')};
            }}
        """
        self.text_view_btn.setStyleSheet(view_btn_style + "QPushButton { border-radius: 8px 0 0 8px; }")
        self.cards_view_btn.setStyleSheet(view_btn_style + "QPushButton { border-radius: 0 8px 8px 0; }")

        view_toggle_layout.addWidget(self.text_view_btn)
        view_toggle_layout.addWidget(self.cards_view_btn)
        header_layout.addLayout(view_toggle_layout)

        header_layout.addSpacing(16)

        # Stream toggle
        self.stream_btn = QPushButton("⏸️ Pause")
        self.stream_btn.setToolTip("Pause/Resume streaming (Space)")
        self.stream_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS.get('warning', '#f59e0b')};
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                color: white;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('warning', '#f59e0b')}dd;
            }}
        """)
        self.stream_btn.clicked.connect(self._toggle_streaming)
        header_layout.addWidget(self.stream_btn)

        # Export menu
        export_btn = QToolButton()
        export_btn.setText("📥 Export")
        export_btn.setPopupMode(QToolButton.InstantPopup)
        export_btn.setStyleSheet(f"""
            QToolButton {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 8px;
                padding: 8px 16px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
            }}
            QToolButton:hover {{
                background-color: {COLORS.get('bg_light', '#273548')};
            }}
            QToolButton::menu-indicator {{
                image: none;
            }}
        """)

        from PySide6.QtWidgets import QMenu
        export_menu = QMenu(export_btn)
        export_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 8px;
                padding: 8px;
            }}
            QMenu::item {{
                padding: 8px 16px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {COLORS.get('primary', '#3b82f6')};
            }}
        """)

        export_txt_action = export_menu.addAction("📄 Export as TXT")
        export_txt_action.triggered.connect(lambda: self._export_logs("txt"))

        export_json_action = export_menu.addAction("📋 Export as JSON")
        export_json_action.triggered.connect(lambda: self._export_logs("json"))

        export_btn.setMenu(export_menu)
        header_layout.addWidget(export_btn)

        # Clear button
        clear_btn = QPushButton("🗑️ Clear")
        clear_btn.setToolTip("Clear logs (Ctrl+L)")
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS.get('danger', '#ef4444')};
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                color: white;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('danger', '#ef4444')}dd;
            }}
        """)
        clear_btn.clicked.connect(self._on_clear)
        header_layout.addWidget(clear_btn)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setToolTip("Refresh logs (F5)")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 8px;
                padding: 8px 16px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('bg_light', '#273548')};
            }}
        """)
        refresh_btn.clicked.connect(self._on_refresh)
        header_layout.addWidget(refresh_btn)

        parent_layout.addLayout(header_layout)

    def _setup_filter_bar(self, parent_layout: QVBoxLayout):
        """Setup filter bar"""
        filter_layout = QHBoxLayout()

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search logs... (Ctrl+F)")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 8px;
                padding: 8px 12px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
                min-width: 250px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS.get('primary', '#3b82f6')};
            }}
        """)
        self.search_input.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.search_input)

        # Level filter
        level_label = QLabel("Level:")
        level_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')};")
        filter_layout.addWidget(level_label)

        self.level_combo = QComboBox()
        self.level_combo.addItems(["All", "Debug", "Info", "Warning", "Error", "Critical"])
        self.level_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 6px;
                padding: 6px 12px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
                min-width: 100px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """)
        self.level_combo.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.level_combo)

        # Source filter
        source_label = QLabel("Source:")
        source_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')};")
        filter_layout.addWidget(source_label)

        self.source_combo = QComboBox()
        self.source_combo.addItems(["All", "Master", "Worker", "Scheduler", "API", "System"])
        self.source_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 6px;
                padding: 6px 12px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
                min-width: 100px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """)
        self.source_combo.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.source_combo)

        filter_layout.addStretch()

        parent_layout.addLayout(filter_layout)

    def _setup_text_view(self):
        """Setup text view with syntax highlighting"""
        self.logs_text = QPlainTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setStyleSheet(f"""
            QPlainTextEdit {{
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 12px;
                background-color: {COLORS.get('bg_dark', '#0f172a')};
                color: {COLORS.get('text_primary', '#f1f5f9')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 8px;
                padding: 16px;
            }}
        """)
        self.logs_text.setPlaceholderText(
            "No logs to display.\n\n"
            "Connect to a master server to view system logs.\n\n"
            "Keyboard Shortcuts:\n"
            "  Space     - Pause/Resume streaming\n"
            "  Ctrl+F    - Focus search\n"
            "  Ctrl+L    - Clear logs\n"
            "  Ctrl+1    - Text view\n"
            "  Ctrl+2    - Cards view\n"
            "  F5        - Refresh"
        )

        # Apply syntax highlighter
        self.highlighter = LogSyntaxHighlighter(self.logs_text.document())

        self.content_stack.addWidget(self.logs_text)

    def _setup_cards_view(self):
        """Setup cards view"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: transparent; }
        """)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(8)
        self.cards_layout.setAlignment(Qt.AlignTop)

        scroll_area.setWidget(self.cards_container)
        self.content_stack.addWidget(scroll_area)

    def _setup_status_bar(self, parent_layout: QVBoxLayout):
        """Setup status bar"""
        status_layout = QHBoxLayout()

        self.status_label = QLabel("0 log entries")
        self.status_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')}; font-size: 12px;")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        # Streaming indicator
        self.streaming_indicator = QLabel("● Streaming")
        self.streaming_indicator.setStyleSheet(f"""
            color: {COLORS.get('success', '#10b981')};
            font-size: 12px;
        """)
        status_layout.addWidget(self.streaming_indicator)

        status_layout.addSpacing(16)

        # Auto-scroll toggle
        self.auto_scroll_btn = QPushButton("Auto-scroll: ON")
        self.auto_scroll_btn.setCheckable(True)
        self.auto_scroll_btn.setChecked(True)
        self.auto_scroll_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 6px;
                padding: 4px 12px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
                font-size: 12px;
            }}
            QPushButton:checked {{
                background-color: {COLORS.get('primary', '#3b82f6')};
                border-color: {COLORS.get('primary', '#3b82f6')};
            }}
        """)
        self.auto_scroll_btn.clicked.connect(self._toggle_auto_scroll)
        status_layout.addWidget(self.auto_scroll_btn)

        parent_layout.addLayout(status_layout)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Space - toggle streaming
        space_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        space_shortcut.activated.connect(self._toggle_streaming)

        # Ctrl+F - focus search
        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(lambda: self.search_input.setFocus())

        # Ctrl+L - clear logs
        clear_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        clear_shortcut.activated.connect(self._on_clear)

        # Ctrl+1 - text view
        text_view_shortcut = QShortcut(QKeySequence("Ctrl+1"), self)
        text_view_shortcut.activated.connect(lambda: self._switch_view("text"))

        # Ctrl+2 - cards view
        cards_view_shortcut = QShortcut(QKeySequence("Ctrl+2"), self)
        cards_view_shortcut.activated.connect(lambda: self._switch_view("cards"))

        # F5 - refresh
        refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        refresh_shortcut.activated.connect(self._on_refresh)

    def _setup_streaming(self):
        """Setup log streaming timer"""
        self.stream_timer = QTimer(self)
        self.stream_timer.timeout.connect(self._on_refresh)
        self.stream_timer.start(self.STREAM_INTERVAL)

    def _switch_view(self, view_type: str):
        """Switch between text and cards views"""
        self._current_view = view_type
        self.text_view_btn.setChecked(view_type == "text")
        self.cards_view_btn.setChecked(view_type == "cards")

        if view_type == "text":
            self.content_stack.setCurrentIndex(0)
        else:
            self.content_stack.setCurrentIndex(1)
            self._update_cards_view()

    def _toggle_streaming(self):
        """Toggle log streaming"""
        self._is_streaming = not self._is_streaming

        if self._is_streaming:
            self.stream_btn.setText("⏸️ Pause")
            self.stream_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS.get('warning', '#f59e0b')};
                    border: none;
                    border-radius: 8px;
                    padding: 8px 16px;
                    color: white;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {COLORS.get('warning', '#f59e0b')}dd;
                }}
            """)
            self.streaming_indicator.setText("● Streaming")
            self.streaming_indicator.setStyleSheet(f"color: {COLORS.get('success', '#10b981')}; font-size: 12px;")
            self.stream_timer.start(self.STREAM_INTERVAL)
        else:
            self.stream_btn.setText("▶️ Resume")
            self.stream_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS.get('success', '#10b981')};
                    border: none;
                    border-radius: 8px;
                    padding: 8px 16px;
                    color: white;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {COLORS.get('success', '#10b981')}dd;
                }}
            """)
            self.streaming_indicator.setText("● Paused")
            self.streaming_indicator.setStyleSheet(f"color: {COLORS.get('warning', '#f59e0b')}; font-size: 12px;")
            self.stream_timer.stop()

    def _toggle_auto_scroll(self):
        """Toggle auto-scroll"""
        self._auto_scroll = self.auto_scroll_btn.isChecked()
        self.auto_scroll_btn.setText(f"Auto-scroll: {'ON' if self._auto_scroll else 'OFF'}")

    def _apply_filters(self):
        """Apply filters and update display"""
        search_text = self.search_input.text().lower()
        level_filter = self.level_combo.currentText()
        source_filter = self.source_combo.currentText()

        filtered = []
        for log in self._logs_data:
            # Level filter
            if level_filter != "All":
                if log.get("level", "info").lower() != level_filter.lower():
                    continue

            # Source filter
            if source_filter != "All":
                if log.get("source", "").lower() != source_filter.lower():
                    continue

            # Search filter
            if search_text:
                message = log.get("message", "").lower()
                if search_text not in message:
                    continue

            filtered.append(log)

        self._update_text_view(filtered)
        if self._current_view == "cards":
            self._update_cards_view(filtered)

    def _update_stats(self):
        """Update level statistics"""
        counts = {level: 0 for level in LOG_LEVELS.keys()}

        for log in self._logs_data:
            level = log.get("level", "info").lower()
            if level in counts:
                counts[level] += 1

        for level, card in self.level_stats.items():
            card.set_count(counts.get(level, 0))

    def _update_text_view(self, logs: list = None):
        """Update text view with logs"""
        if logs is None:
            logs = self._logs_data

        self.logs_text.clear()

        for log in logs:
            level = log.get("level", "info")
            message = log.get("message", "")
            timestamp = log.get("timestamp", "")
            source = log.get("source", "")

            formatted = f"[{timestamp}] [{source}] [{level.upper()}] {message}"
            self.logs_text.appendPlainText(formatted)

        # Auto-scroll
        if self._auto_scroll:
            scrollbar = self.logs_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        self.status_label.setText(f"{len(logs)} log entries")

    def _update_cards_view(self, logs: list = None):
        """Update cards view with logs"""
        if logs is None:
            logs = self._logs_data

        # Clear existing cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new cards (show last 100 for performance)
        for log in logs[-100:]:
            card = LogCard(log)
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()

    def append_log(self, message: str, level: str = "info", source: str = "System"):
        """Append a log message"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "source": source,
            "message": message,
        }

        self._logs_data.append(log_entry)
        self._update_stats()

        # Apply current filters
        self._apply_filters()

    def set_logs(self, logs: list):
        """Set logs from list"""
        self._logs_data = logs
        self._update_stats()
        self._apply_filters()

    def _export_logs(self, format_type: str):
        """Export logs to file"""
        if not self._logs_data:
            QMessageBox.warning(self, "Export", "No logs to export.")
            return

        if format_type == "txt":
            default_name = f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            file_filter = "Text Files (*.txt)"
        else:
            default_name = f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            file_filter = "JSON Files (*.json)"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Logs", default_name, file_filter
        )

        if not file_path:
            return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                if format_type == "txt":
                    for log in self._logs_data:
                        line = f"[{log.get('timestamp', '')}] [{log.get('source', '')}] [{log.get('level', '').upper()}] {log.get('message', '')}\n"
                        f.write(line)
                else:
                    json.dump(self._logs_data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "Export", f"Logs exported successfully to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export logs:\n{str(e)}")

    def _on_clear(self):
        """Clear logs"""
        self._logs_data.clear()
        self.logs_text.clear()
        self._update_stats()

        # Clear cards view
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.status_label.setText("0 log entries")

    def _on_refresh(self):
        """Handle refresh"""
        self.refresh_requested.emit()

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

    def showEvent(self, event):
        """Start streaming when view is shown"""
        super().showEvent(event)
        if self._is_streaming and not self.stream_timer.isActive():
            self.stream_timer.start(self.STREAM_INTERVAL)

    def hideEvent(self, event):
        """Stop streaming when view is hidden"""
        super().hideEvent(event)
        self.stream_timer.stop()
