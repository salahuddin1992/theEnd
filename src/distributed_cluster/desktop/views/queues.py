"""
Queues View - Enhanced Priority queues management page
صفحة إدارة طوابير الأولوية المحسّنة

Features:
- Priority badges (Critical/High/Medium/Low)
- Filtering by type and status
- Side panel for details
- Progress bar for queue load
- Pause/Resume for queues
- Auto sort by priority
"""

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..api.client import APIClient
from ..resources.styles import COLORS
from ..ui.dialogs import QueueCreateDialog

# Priority level configurations
PRIORITY_CONFIG = {
    "critical": {
        "label": "CRITICAL",
        "color": "#ef4444",
        "bg": "#ef444420",
        "icon": "🔴",
        "order": 0,
    },
    "high": {
        "label": "HIGH",
        "color": "#f97316",
        "bg": "#f9731620",
        "icon": "🟠",
        "order": 1,
    },
    "medium": {
        "label": "MEDIUM",
        "color": "#eab308",
        "bg": "#eab30820",
        "icon": "🟡",
        "order": 2,
    },
    "low": {
        "label": "LOW",
        "color": "#22c55e",
        "bg": "#22c55e20",
        "icon": "🟢",
        "order": 3,
    },
    "default": {
        "label": "DEFAULT",
        "color": "#64748b",
        "bg": "#64748b20",
        "icon": "⚪",
        "order": 4,
    },
}


class PriorityBadge(QLabel):
    """Priority level badge widget"""

    def __init__(self, priority: str, parent=None):
        super().__init__(parent)
        self._setup_ui(priority)

    def _setup_ui(self, priority: str):
        config = PRIORITY_CONFIG.get(priority.lower(), PRIORITY_CONFIG["default"])

        self.setText(f"{config['icon']} {config['label']}")
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {config['bg']};
                color: {config['color']};
                padding: 4px 10px;
                border-radius: 10px;
                font-size: 11px;
                font-weight: 600;
            }}
        """
        )


class QueueCard(QFrame):
    """Interactive queue card widget"""

    clicked = Signal(dict)
    action_triggered = Signal(str, dict)  # action_name, queue_data

    def __init__(self, queue_data: dict, parent=None):
        super().__init__(parent)
        self.queue_data = queue_data
        self.setObjectName("queue_card")
        self._setup_ui()
        self._setup_shadow()
        self.setCursor(Qt.PointingHandCursor)

    def _setup_shadow(self):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 50))
        self.setGraphicsEffect(shadow)

    def _setup_ui(self):
        queue = self.queue_data
        priority = queue.get("priority", "default")
        priority_config = PRIORITY_CONFIG.get(priority.lower(), PRIORITY_CONFIG["default"])
        is_enabled = queue.get("enabled", True)
        is_paused = queue.get("paused", False)

        status_color = (
            COLORS.get("success", "#10b981") if is_enabled and not is_paused else COLORS.get("danger", "#ef4444")
        )

        self.setStyleSheet(
            f"""
            QFrame#queue_card {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-left: 4px solid {priority_config['color']};
                border-radius: 12px;
                padding: 16px;
            }}
            QFrame#queue_card:hover {{
                border-color: {priority_config['color']};
                background-color: {COLORS.get('bg_light', '#273548')};
            }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header row
        header_layout = QHBoxLayout()

        name_label = QLabel(queue.get("name", "Unknown Queue"))
        name_label.setStyleSheet(
            f"""
            font-size: 16px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """
        )
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        # Priority badge
        priority_badge = PriorityBadge(priority)
        header_layout.addWidget(priority_badge)

        # Status indicator
        status_text = "PAUSED" if is_paused else ("ACTIVE" if is_enabled else "DISABLED")
        status_label = QLabel(status_text)
        status_label.setStyleSheet(
            f"""
            background-color: {status_color}20;
            color: {status_color};
            padding: 4px 10px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 600;
        """
        )
        header_layout.addWidget(status_label)

        # Actions button
        actions_btn = QToolButton()
        actions_btn.setText("⋮")
        actions_btn.setStyleSheet(
            f"""
            QToolButton {{
                background: transparent;
                border: none;
                color: {COLORS.get('text_secondary', '#94a3b8')};
                font-size: 16px;
                padding: 4px 8px;
            }}
            QToolButton:hover {{
                background-color: {COLORS.get('bg_light', '#273548')};
                border-radius: 4px;
            }}
        """
        )
        actions_btn.clicked.connect(self._show_actions_menu)
        header_layout.addWidget(actions_btn)

        layout.addLayout(header_layout)

        # Stats row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(24)

        pending_jobs = queue.get("pending_jobs", 0)
        running_jobs = queue.get("running_jobs", 0)
        weight = queue.get("weight", 1)

        # Pending jobs
        pending_container = self._create_stat_widget("⏳", "Pending", str(pending_jobs))
        stats_layout.addWidget(pending_container)

        # Running jobs
        running_container = self._create_stat_widget("▶️", "Running", str(running_jobs))
        stats_layout.addWidget(running_container)

        # Weight
        weight_container = self._create_stat_widget("⚖️", "Weight", str(weight))
        stats_layout.addWidget(weight_container)

        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        # Load progress bar
        max_capacity = queue.get("max_capacity", 100)
        total_jobs = pending_jobs + running_jobs
        load_percent = min(100, (total_jobs / max_capacity * 100)) if max_capacity > 0 else 0

        load_layout = QHBoxLayout()
        load_label = QLabel(f"Load: {load_percent:.0f}%")
        load_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')}; font-size: 12px;")
        load_layout.addWidget(load_label)

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(int(load_percent))
        progress.setTextVisible(False)
        progress.setFixedHeight(6)

        # Color based on load
        if load_percent > 80:
            progress_color = COLORS.get("danger", "#ef4444")
        elif load_percent > 50:
            progress_color = COLORS.get("warning", "#f59e0b")
        else:
            progress_color = COLORS.get("success", "#10b981")

        progress.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {COLORS.get('bg_dark', '#0f172a')};
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {progress_color};
                border-radius: 3px;
            }}
        """
        )
        load_layout.addWidget(progress, 1)

        layout.addLayout(load_layout)

    def _create_stat_widget(self, icon: str, label: str, value: str) -> QWidget:
        """Create a stat display widget"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)

        label_widget = QLabel(label)
        label_widget.setStyleSheet(
            f"""
            font-size: 11px;
            color: {COLORS.get('text_secondary', '#94a3b8')};
        """
        )
        text_layout.addWidget(label_widget)

        value_widget = QLabel(value)
        value_widget.setStyleSheet(
            f"""
            font-size: 14px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """
        )
        text_layout.addWidget(value_widget)

        layout.addLayout(text_layout)
        return container

    def _show_actions_menu(self):
        """Show actions dropdown menu"""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setStyleSheet(
            f"""
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
        """
        )

        is_paused = self.queue_data.get("paused", False)

        edit_action = menu.addAction("✏️  Edit Queue")
        edit_action.triggered.connect(lambda: self.action_triggered.emit("edit", self.queue_data))

        if is_paused:
            resume_action = menu.addAction("▶️  Resume Queue")
            resume_action.triggered.connect(lambda: self.action_triggered.emit("resume", self.queue_data))
        else:
            pause_action = menu.addAction("⏸️  Pause Queue")
            pause_action.triggered.connect(lambda: self.action_triggered.emit("pause", self.queue_data))

        menu.addSeparator()

        delete_action = menu.addAction("🗑️  Delete Queue")
        delete_action.triggered.connect(lambda: self.action_triggered.emit("delete", self.queue_data))

        menu.exec(self.mapToGlobal(self.rect().bottomRight()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.queue_data)
        super().mousePressEvent(event)


class QueueDetailsPanel(QFrame):
    """Side panel showing queue details"""

    close_requested = Signal()
    action_triggered = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("details_panel")
        self._queue_data: Optional[Dict] = None
        self._setup_ui()
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)

    def _setup_ui(self):
        self.setStyleSheet(
            f"""
            QFrame#details_panel {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border-left: 1px solid {COLORS.get('border', '#334155')};
            }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()

        self.title_label = QLabel("Queue Details")
        self.title_label.setStyleSheet(
            f"""
            font-size: 18px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """
        )
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {COLORS.get('text_secondary', '#94a3b8')};
                font-size: 16px;
            }}
            QPushButton:hover {{
                color: {COLORS.get('text_primary', '#f1f5f9')};
                background-color: {COLORS.get('bg_light', '#273548')};
                border-radius: 4px;
            }}
        """
        )
        close_btn.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(close_btn)

        layout.addLayout(header_layout)

        # Content area (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(16)
        self.content_layout.setAlignment(Qt.AlignTop)

        scroll.setWidget(self.content_widget)
        layout.addWidget(scroll, 1)

        # Action buttons
        actions_layout = QHBoxLayout()

        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS.get('warning', '#f59e0b')};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                color: white;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('warning', '#f59e0b')}dd;
            }}
        """
        )
        self.pause_btn.clicked.connect(self._on_pause_resume)
        actions_layout.addWidget(self.pause_btn)

        edit_btn = QPushButton("✏️ Edit")
        edit_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS.get('primary', '#3b82f6')};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                color: white;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('info', '#60a5fa')};
            }}
        """
        )
        edit_btn.clicked.connect(lambda: self.action_triggered.emit("edit", self._queue_data))
        actions_layout.addWidget(edit_btn)

        layout.addLayout(actions_layout)

    def set_queue(self, queue_data: dict):
        """Set queue data to display"""
        self._queue_data = queue_data

        # Clear existing content
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Queue name
        self.title_label.setText(queue_data.get("name", "Unknown Queue"))

        # Priority
        priority = queue_data.get("priority", "default")
        priority_badge = PriorityBadge(priority)
        self.content_layout.addWidget(priority_badge)

        # Status
        is_paused = queue_data.get("paused", False)
        is_enabled = queue_data.get("enabled", True)

        if is_paused:
            self.pause_btn.setText("▶️ Resume")
            status = "Paused"
            status_color = COLORS.get("warning", "#f59e0b")
        elif is_enabled:
            self.pause_btn.setText("⏸️ Pause")
            status = "Active"
            status_color = COLORS.get("success", "#10b981")
        else:
            self.pause_btn.setText("▶️ Enable")
            status = "Disabled"
            status_color = COLORS.get("danger", "#ef4444")

        self._add_detail_row("Status", status, status_color)

        # Stats
        self._add_detail_row("Pending Jobs", str(queue_data.get("pending_jobs", 0)))
        self._add_detail_row("Running Jobs", str(queue_data.get("running_jobs", 0)))
        self._add_detail_row("Completed Jobs", str(queue_data.get("completed_jobs", 0)))
        self._add_detail_row("Failed Jobs", str(queue_data.get("failed_jobs", 0)))
        self._add_detail_row("Weight", str(queue_data.get("weight", 1)))
        self._add_detail_row("Max Capacity", str(queue_data.get("max_capacity", 100)))

        # Description
        description = queue_data.get("description", "")
        if description:
            desc_label = QLabel("Description")
            desc_label.setStyleSheet(
                f"""
                font-size: 12px;
                color: {COLORS.get('text_secondary', '#94a3b8')};
                margin-top: 8px;
            """
            )
            self.content_layout.addWidget(desc_label)

            desc_text = QLabel(description)
            desc_text.setWordWrap(True)
            desc_text.setStyleSheet(
                f"""
                color: {COLORS.get('text_primary', '#f1f5f9')};
                font-size: 13px;
                padding: 8px;
                background-color: {COLORS.get('bg_dark', '#0f172a')};
                border-radius: 6px;
            """
            )
            self.content_layout.addWidget(desc_text)

        self.content_layout.addStretch()

    def _add_detail_row(self, label: str, value: str, color: str = None):
        """Add a detail row to the panel"""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        label_widget = QLabel(label)
        label_widget.setStyleSheet(
            f"""
            color: {COLORS.get('text_secondary', '#94a3b8')};
            font-size: 13px;
        """
        )
        row_layout.addWidget(label_widget)
        row_layout.addStretch()

        value_color = color or COLORS.get("text_primary", "#f1f5f9")
        value_widget = QLabel(value)
        value_widget.setStyleSheet(
            f"""
            color: {value_color};
            font-size: 13px;
            font-weight: 500;
        """
        )
        row_layout.addWidget(value_widget)

        self.content_layout.addWidget(row)

    def _on_pause_resume(self):
        """Handle pause/resume button"""
        if self._queue_data:
            is_paused = self._queue_data.get("paused", False)
            action = "resume" if is_paused else "pause"
            self.action_triggered.emit(action, self._queue_data)


class QueuesView(QWidget):
    """Enhanced priority queues management view"""

    refresh_requested = Signal()

    # Auto-refresh interval in milliseconds (30 seconds)
    AUTO_REFRESH_INTERVAL = 30000

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._queues_data: List[Dict[str, Any]] = []
        self._selected_queue: Optional[Dict] = None
        self._setup_ui()
        self._setup_auto_refresh()

    def _setup_ui(self):
        """Setup queues view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main content with optional details panel
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        # Left side - main content
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(32, 32, 32, 32)
        main_layout.setSpacing(24)

        # Header with controls
        self._setup_header(main_layout)

        # Filter bar
        self._setup_filter_bar(main_layout)

        # Queues grid
        self._setup_queues_grid(main_layout)

        main_splitter.addWidget(main_widget)

        # Right side - details panel
        self.details_panel = QueueDetailsPanel()
        self.details_panel.close_requested.connect(self._hide_details)
        self.details_panel.action_triggered.connect(self._on_queue_action)
        self.details_panel.hide()
        main_splitter.addWidget(self.details_panel)

        main_splitter.setSizes([700, 350])
        layout.addWidget(main_splitter)

    def _setup_header(self, parent_layout: QVBoxLayout):
        """Setup header with title and controls"""
        header_layout = QHBoxLayout()

        title = QLabel("Priority Queues")
        title.setStyleSheet(
            f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """
        )
        header_layout.addWidget(title)

        subtitle = QLabel("Manage job scheduling priorities")
        subtitle.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')}; margin-left: 16px;")
        header_layout.addWidget(subtitle)

        header_layout.addStretch()

        # Stats badges
        self.total_queues_badge = QLabel("0 queues")
        self.total_queues_badge.setStyleSheet(
            f"""
            background-color: {COLORS.get('bg_medium', '#1e293b')};
            color: {COLORS.get('text_secondary', '#94a3b8')};
            padding: 6px 12px;
            border-radius: 12px;
            font-size: 12px;
        """
        )
        header_layout.addWidget(self.total_queues_badge)

        self.total_pending_badge = QLabel("0 pending")
        self.total_pending_badge.setStyleSheet(
            f"""
            background-color: {COLORS.get('warning', '#f59e0b')}20;
            color: {COLORS.get('warning', '#f59e0b')};
            padding: 6px 12px;
            border-radius: 12px;
            font-size: 12px;
        """
        )
        header_layout.addWidget(self.total_pending_badge)

        header_layout.addSpacing(16)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet(
            f"""
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
        """
        )
        refresh_btn.clicked.connect(self._on_refresh)
        header_layout.addWidget(refresh_btn)

        # Create button
        create_btn = QPushButton("+ Create Queue")
        create_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS.get('primary', '#3b82f6')};
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                color: white;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('info', '#60a5fa')};
            }}
        """
        )
        create_btn.clicked.connect(self._on_create_queue)
        header_layout.addWidget(create_btn)

        parent_layout.addLayout(header_layout)

    def _setup_filter_bar(self, parent_layout: QVBoxLayout):
        """Setup filter bar"""
        filter_layout = QHBoxLayout()

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search queues...")
        self.search_input.setFixedWidth(250)
        self.search_input.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 8px;
                padding: 8px 12px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
            }}
            QLineEdit:focus {{
                border-color: {COLORS.get('primary', '#3b82f6')};
            }}
        """
        )
        self.search_input.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.search_input)

        # Priority filter
        priority_label = QLabel("Priority:")
        priority_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')};")
        filter_layout.addWidget(priority_label)

        self.priority_filter = QComboBox()
        self.priority_filter.addItems(["All", "Critical", "High", "Medium", "Low"])
        self.priority_filter.setStyleSheet(
            f"""
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
        """
        )
        self.priority_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.priority_filter)

        # Status filter
        status_label = QLabel("Status:")
        status_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')};")
        filter_layout.addWidget(status_label)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Active", "Paused", "Disabled"])
        self.status_filter.setStyleSheet(
            f"""
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
        """
        )
        self.status_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.status_filter)

        # Sort by priority checkbox
        self.sort_by_priority = QPushButton("📊 Sort by Priority")
        self.sort_by_priority.setCheckable(True)
        self.sort_by_priority.setChecked(True)
        self.sort_by_priority.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 6px;
                padding: 6px 12px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
            }}
            QPushButton:checked {{
                background-color: {COLORS.get('primary', '#3b82f6')};
                border-color: {COLORS.get('primary', '#3b82f6')};
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('bg_light', '#273548')};
            }}
        """
        )
        self.sort_by_priority.clicked.connect(self._apply_filters)
        filter_layout.addWidget(self.sort_by_priority)

        filter_layout.addStretch()

        parent_layout.addLayout(filter_layout)

    def _setup_queues_grid(self, parent_layout: QVBoxLayout):
        """Setup queues grid view"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(
            """
            QScrollArea { border: none; background-color: transparent; }
        """
        )

        self.queues_container = QWidget()
        self.queues_layout = QGridLayout(self.queues_container)
        self.queues_layout.setSpacing(16)
        self.queues_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll_area.setWidget(self.queues_container)
        parent_layout.addWidget(scroll_area)

    def _setup_auto_refresh(self):
        """Setup auto-refresh timer"""
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_refresh)
        self.refresh_timer.start(self.AUTO_REFRESH_INTERVAL)

    def _apply_filters(self):
        """Apply filters and update view"""
        search_text = self.search_input.text().lower()
        priority_filter = self.priority_filter.currentText()
        status_filter = self.status_filter.currentText()
        sort_by_priority = self.sort_by_priority.isChecked()

        filtered = []
        for queue in self._queues_data:
            # Search filter
            if search_text:
                if search_text not in queue.get("name", "").lower():
                    continue

            # Priority filter
            if priority_filter != "All":
                if queue.get("priority", "default").lower() != priority_filter.lower():
                    continue

            # Status filter
            if status_filter != "All":
                is_paused = queue.get("paused", False)
                is_enabled = queue.get("enabled", True)

                if status_filter == "Active" and (is_paused or not is_enabled):
                    continue
                elif status_filter == "Paused" and not is_paused:
                    continue
                elif status_filter == "Disabled" and is_enabled:
                    continue

            filtered.append(queue)

        # Sort by priority if enabled
        if sort_by_priority:
            filtered.sort(
                key=lambda q: PRIORITY_CONFIG.get(q.get("priority", "default").lower(), PRIORITY_CONFIG["default"])[
                    "order"
                ]
            )

        self._update_queues_grid(filtered)

    def _update_queues_grid(self, queues: list):
        """Update queues grid with queue data"""
        # Clear existing cards
        while self.queues_layout.count():
            item = self.queues_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new cards
        cols = 2  # Number of columns
        for i, queue in enumerate(queues):
            card = QueueCard(queue)
            card.clicked.connect(self._on_queue_clicked)
            card.action_triggered.connect(self._on_queue_action)
            card.setMinimumWidth(350)

            row = i // cols
            col = i % cols
            self.queues_layout.addWidget(card, row, col)

        # Add stretch
        self.queues_layout.setRowStretch(len(queues) // cols + 1, 1)
        self.queues_layout.setColumnStretch(cols, 1)

    def _update_stats(self):
        """Update statistics badges"""
        total_queues = len(self._queues_data)
        total_pending = sum(q.get("pending_jobs", 0) for q in self._queues_data)

        self.total_queues_badge.setText(f"{total_queues} queues")
        self.total_pending_badge.setText(f"{total_pending} pending")

    def set_queues(self, queues: list):
        """Update queues list"""
        self._queues_data = queues
        self._update_stats()
        self._apply_filters()

    def _on_refresh(self):
        """Handle refresh"""
        self.refresh_requested.emit()

    def _on_queue_clicked(self, queue_data: dict):
        """Handle queue card click - show details panel"""
        self._selected_queue = queue_data
        self.details_panel.set_queue(queue_data)
        self.details_panel.show()

    def _hide_details(self):
        """Hide details panel"""
        self._selected_queue = None
        self.details_panel.hide()

    def _on_queue_action(self, action: str, queue_data: dict):
        """Handle queue action"""
        if action == "edit":
            self._edit_queue(queue_data)
        elif action == "pause":
            self._pause_queue(queue_data)
        elif action == "resume":
            self._resume_queue(queue_data)
        elif action == "delete":
            self._delete_queue(queue_data)

    def _edit_queue(self, queue_data: dict):
        """Open edit dialog for queue"""
        dialog = QueueCreateDialog(self)
        # Pre-fill with existing data
        if hasattr(dialog, "name_input"):
            dialog.name_input.setText(queue_data.get("name", ""))
        if hasattr(dialog, "priority_combo"):
            priority = queue_data.get("priority", "medium")
            index = dialog.priority_combo.findText(priority.capitalize())
            if index >= 0:
                dialog.priority_combo.setCurrentIndex(index)
        dialog.queue_created.connect(self._handle_queue_updated)
        dialog.exec()

    def _pause_queue(self, queue_data: dict):
        """Pause queue"""
        queue_name = queue_data.get("name", "")
        if self.api_client:
            try:
                self.api_client.pause_queue(queue_name)
                self.refresh_requested.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to pause queue: {str(e)}")
        else:
            self.refresh_requested.emit()

    def _resume_queue(self, queue_data: dict):
        """Resume queue"""
        queue_name = queue_data.get("name", "")
        if self.api_client:
            try:
                self.api_client.resume_queue(queue_name)
                self.refresh_requested.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to resume queue: {str(e)}")
        else:
            self.refresh_requested.emit()

    def _delete_queue(self, queue_data: dict):
        """Confirm and delete queue"""
        queue_name = queue_data.get("name", "Unknown")
        reply = QMessageBox.question(
            self,
            "Delete Queue",
            f"Are you sure you want to delete queue '{queue_name}'?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            if self.api_client:
                try:
                    self.api_client.delete_queue(queue_name)
                    self._hide_details()
                    self.refresh_requested.emit()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to delete queue: {str(e)}")
            else:
                self._hide_details()
                self.refresh_requested.emit()

    def _on_create_queue(self):
        """Handle create queue"""
        dialog = QueueCreateDialog(self)
        dialog.queue_created.connect(self._handle_queue_created)
        dialog.exec()

    def _handle_queue_created(self, queue_config: dict):
        """Handle queue creation from dialog"""
        if self.api_client:
            try:
                self.api_client.create_queue(queue_config)
                self.refresh_requested.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create queue: {str(e)}")
        else:
            self.refresh_requested.emit()

    def _handle_queue_updated(self, queue_config: dict):
        """Handle queue update from edit dialog"""
        if self.api_client:
            try:
                self.api_client.update_queue(queue_config)
                self.refresh_requested.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update queue: {str(e)}")
        else:
            self.refresh_requested.emit()

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client

    def showEvent(self, event):
        """Start auto-refresh when view is shown"""
        super().showEvent(event)
        if not self.refresh_timer.isActive():
            self.refresh_timer.start(self.AUTO_REFRESH_INTERVAL)

    def hideEvent(self, event):
        """Stop auto-refresh when view is hidden"""
        super().hideEvent(event)
        self.refresh_timer.stop()
