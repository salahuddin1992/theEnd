"""
Pools View - Enhanced Worker pools management page
صفحة إدارة مجموعات العمال المحسّنة

Features:
- Interactive pool cards with statistics
- Cards and Table view modes
- Scale Pool dialog with slider
- Actions menu (Edit/Scale/Delete)
- Auto-refresh every 30 seconds
- General statistics at top
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from PySide6.QtCore import Signal, Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QColor, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QFrame,
    QGridLayout,
    QScrollArea,
    QStackedWidget,
    QDialog,
    QSlider,
    QSpinBox,
    QMenu,
    QGraphicsDropShadowEffect,
    QProgressBar,
    QButtonGroup,
    QSizePolicy,
    QToolButton,
    QLineEdit,
    QComboBox,
)

from ..api.client import APIClient
from ..resources.styles import COLORS
from ..ui.dialogs import PoolCreateDialog
from ..widgets.data_table import DataTable


class StatCard(QFrame):
    """Statistics card widget for summary display"""

    def __init__(self, title: str, value: str, icon: str = "", color: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("stat_card")
        self._color = color or COLORS.get('primary', '#3b82f6')
        self._setup_ui(title, value, icon)

    def _setup_ui(self, title: str, value: str, icon: str):
        self.setStyleSheet(f"""
            QFrame#stat_card {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 12px;
                padding: 16px;
            }}
            QFrame#stat_card:hover {{
                border-color: {self._color};
                background-color: {COLORS.get('bg_light', '#273548')};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Title row
        title_layout = QHBoxLayout()

        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"font-size: 20px; color: {self._color};")
            title_layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            font-size: 13px;
            color: {COLORS.get('text_secondary', '#94a3b8')};
            font-weight: 500;
        """)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # Value
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"""
            font-size: 28px;
            font-weight: 700;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        layout.addWidget(self.value_label)

    def set_value(self, value: str):
        self.value_label.setText(value)


class PoolCard(QFrame):
    """Interactive pool card widget"""

    clicked = Signal(dict)
    action_triggered = Signal(str, dict)  # action_name, pool_data

    def __init__(self, pool_data: dict, parent=None):
        super().__init__(parent)
        self.pool_data = pool_data
        self.setObjectName("pool_card")
        self._setup_ui()
        self._setup_shadow()
        self.setCursor(Qt.PointingHandCursor)

    def _setup_shadow(self):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

    def _setup_ui(self):
        pool = self.pool_data
        workers = pool.get("workers", [])
        worker_count = len(workers)
        min_workers = pool.get("min_workers", 0)
        max_workers = pool.get("max_workers", 10)
        status = "active" if workers else "empty"

        # Determine color based on status
        status_colors = {
            "active": COLORS.get('success', '#10b981'),
            "empty": COLORS.get('warning', '#f59e0b'),
            "scaling": COLORS.get('info', '#3b82f6'),
            "error": COLORS.get('danger', '#ef4444'),
        }
        status_color = status_colors.get(status, COLORS.get('text_secondary', '#94a3b8'))

        self.setStyleSheet(f"""
            QFrame#pool_card {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 16px;
                padding: 20px;
            }}
            QFrame#pool_card:hover {{
                border-color: {COLORS.get('primary', '#3b82f6')};
                background-color: {COLORS.get('bg_light', '#273548')};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header row with name and actions
        header_layout = QHBoxLayout()

        name_label = QLabel(pool.get("name", "Unknown Pool"))
        name_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        # Status badge
        status_badge = QLabel(status.upper())
        status_badge.setStyleSheet(f"""
            background-color: {status_color}20;
            color: {status_color};
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        header_layout.addWidget(status_badge)

        # Actions button
        actions_btn = QToolButton()
        actions_btn.setText("⋮")
        actions_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: none;
                color: {COLORS.get('text_secondary', '#94a3b8')};
                font-size: 18px;
                padding: 4px 8px;
            }}
            QToolButton:hover {{
                background-color: {COLORS.get('bg_light', '#273548')};
                border-radius: 4px;
            }}
        """)
        actions_btn.clicked.connect(self._show_actions_menu)
        header_layout.addWidget(actions_btn)

        layout.addLayout(header_layout)

        # Description
        description = pool.get("description", "No description")
        desc_label = QLabel(description)
        desc_label.setStyleSheet(f"""
            color: {COLORS.get('text_secondary', '#94a3b8')};
            font-size: 13px;
        """)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Stats grid
        stats_layout = QGridLayout()
        stats_layout.setSpacing(12)

        # Workers count
        self._add_stat(stats_layout, 0, 0, "👥", "Workers", str(worker_count))

        # Min/Max workers
        self._add_stat(stats_layout, 0, 1, "📊", "Range", f"{min_workers} - {max_workers}")

        # Utilization
        utilization = (worker_count / max_workers * 100) if max_workers > 0 else 0
        self._add_stat(stats_layout, 1, 0, "📈", "Utilization", f"{utilization:.0f}%")

        # Active jobs (if available)
        active_jobs = pool.get("active_jobs", 0)
        self._add_stat(stats_layout, 1, 1, "⚡", "Active Jobs", str(active_jobs))

        layout.addLayout(stats_layout)

        # Progress bar for utilization
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(int(utilization))
        progress.setTextVisible(False)
        progress.setFixedHeight(6)
        progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS.get('bg_dark', '#0f172a')};
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {status_color};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(progress)

    def _add_stat(self, layout: QGridLayout, row: int, col: int, icon: str, label: str, value: str):
        """Add a stat item to the grid"""
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 16px;")
        container_layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        label_widget = QLabel(label)
        label_widget.setStyleSheet(f"""
            font-size: 11px;
            color: {COLORS.get('text_secondary', '#94a3b8')};
        """)
        text_layout.addWidget(label_widget)

        value_widget = QLabel(value)
        value_widget.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        text_layout.addWidget(value_widget)

        container_layout.addLayout(text_layout)
        container_layout.addStretch()

        layout.addWidget(container, row, col)

    def _show_actions_menu(self):
        """Show actions dropdown menu"""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
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

        edit_action = menu.addAction("✏️  Edit Pool")
        edit_action.triggered.connect(lambda: self.action_triggered.emit("edit", self.pool_data))

        scale_action = menu.addAction("📊  Scale Pool")
        scale_action.triggered.connect(lambda: self.action_triggered.emit("scale", self.pool_data))

        menu.addSeparator()

        delete_action = menu.addAction("🗑️  Delete Pool")
        delete_action.triggered.connect(lambda: self.action_triggered.emit("delete", self.pool_data))

        menu.exec(self.mapToGlobal(self.rect().bottomRight()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.pool_data)
        super().mousePressEvent(event)


class ScalePoolDialog(QDialog):
    """Dialog for scaling a pool"""

    scale_confirmed = Signal(str, int)  # pool_name, new_count

    def __init__(self, pool_data: dict, parent=None):
        super().__init__(parent)
        self.pool_data = pool_data
        self.setWindowTitle(f"Scale Pool: {pool_data.get('name', 'Unknown')}")
        self.setFixedSize(450, 350)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS.get('bg_dark', '#0f172a')};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(24)
        layout.setContentsMargins(32, 32, 32, 32)

        # Title
        title = QLabel(f"Scale: {self.pool_data.get('name', 'Unknown')}")
        title.setStyleSheet(f"""
            font-size: 20px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        layout.addWidget(title)

        # Current info
        current_workers = len(self.pool_data.get("workers", []))
        min_workers = self.pool_data.get("min_workers", 0)
        max_workers = self.pool_data.get("max_workers", 20)

        info_label = QLabel(f"Current workers: {current_workers} (Min: {min_workers}, Max: {max_workers})")
        info_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')};")
        layout.addWidget(info_label)

        # Slider section
        slider_layout = QVBoxLayout()
        slider_layout.setSpacing(12)

        # Target count display
        self.target_label = QLabel(f"Target Workers: {current_workers}")
        self.target_label.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 700;
            color: {COLORS.get('primary', '#3b82f6')};
            text-align: center;
        """)
        self.target_label.setAlignment(Qt.AlignCenter)
        slider_layout.addWidget(self.target_label)

        # Slider
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(min_workers, max_workers)
        self.slider.setValue(current_workers)
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: none;
                height: 8px;
                background: {COLORS.get('bg_medium', '#1e293b')};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS.get('primary', '#3b82f6')};
                border: none;
                width: 20px;
                height: 20px;
                margin: -6px 0;
                border-radius: 10px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {COLORS.get('info', '#60a5fa')};
            }}
            QSlider::sub-page:horizontal {{
                background: {COLORS.get('primary', '#3b82f6')};
                border-radius: 4px;
            }}
        """)
        self.slider.valueChanged.connect(self._on_slider_changed)
        slider_layout.addWidget(self.slider)

        # Min/Max labels
        range_layout = QHBoxLayout()
        min_label = QLabel(str(min_workers))
        min_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')};")
        range_layout.addWidget(min_label)
        range_layout.addStretch()
        max_label = QLabel(str(max_workers))
        max_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')};")
        range_layout.addWidget(max_label)
        slider_layout.addLayout(range_layout)

        layout.addLayout(slider_layout)

        # Spinbox for precise control
        spinbox_layout = QHBoxLayout()
        spinbox_label = QLabel("Or enter exact value:")
        spinbox_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')};")
        spinbox_layout.addWidget(spinbox_label)

        self.spinbox = QSpinBox()
        self.spinbox.setRange(min_workers, max_workers)
        self.spinbox.setValue(current_workers)
        self.spinbox.setStyleSheet(f"""
            QSpinBox {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 6px;
                padding: 8px 12px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
                font-size: 14px;
            }}
        """)
        self.spinbox.valueChanged.connect(self._on_spinbox_changed)
        spinbox_layout.addWidget(self.spinbox)
        spinbox_layout.addStretch()

        layout.addLayout(spinbox_layout)
        layout.addStretch()

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 8px;
                padding: 10px 24px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('bg_light', '#273548')};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("Scale Pool")
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS.get('primary', '#3b82f6')};
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                color: white;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('info', '#60a5fa')};
            }}
        """)
        confirm_btn.clicked.connect(self._on_confirm)
        buttons_layout.addWidget(confirm_btn)

        layout.addLayout(buttons_layout)

    def _on_slider_changed(self, value: int):
        self.target_label.setText(f"Target Workers: {value}")
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(value)
        self.spinbox.blockSignals(False)

    def _on_spinbox_changed(self, value: int):
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self.target_label.setText(f"Target Workers: {value}")

    def _on_confirm(self):
        pool_name = self.pool_data.get("name", "")
        target_count = self.slider.value()
        self.scale_confirmed.emit(pool_name, target_count)
        self.accept()


class PoolsView(QWidget):
    """Enhanced worker pools management view"""

    refresh_requested = Signal()

    # Auto-refresh interval in milliseconds (30 seconds)
    AUTO_REFRESH_INTERVAL = 30000

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._pools_data: List[Dict[str, Any]] = []
        self._current_view = "cards"  # "cards" or "table"
        self._setup_ui()
        self._setup_auto_refresh()

    def _setup_ui(self):
        """Setup pools view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Stats section
        self._setup_stats_section(layout)

        # Header with controls
        self._setup_header(layout)

        # Content area (stacked widget for cards/table views)
        self.content_stack = QStackedWidget()

        # Cards view
        self._setup_cards_view()

        # Table view
        self._setup_table_view()

        layout.addWidget(self.content_stack)

    def _setup_stats_section(self, parent_layout: QVBoxLayout):
        """Setup summary statistics cards"""
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)

        self.total_pools_card = StatCard("Total Pools", "0", "📦", COLORS.get('primary', '#3b82f6'))
        stats_layout.addWidget(self.total_pools_card)

        self.active_pools_card = StatCard("Active Pools", "0", "✅", COLORS.get('success', '#10b981'))
        stats_layout.addWidget(self.active_pools_card)

        self.total_workers_card = StatCard("Total Workers", "0", "👥", COLORS.get('info', '#3b82f6'))
        stats_layout.addWidget(self.total_workers_card)

        self.avg_utilization_card = StatCard("Avg Utilization", "0%", "📈", COLORS.get('warning', '#f59e0b'))
        stats_layout.addWidget(self.avg_utilization_card)

        parent_layout.addLayout(stats_layout)

    def _setup_header(self, parent_layout: QVBoxLayout):
        """Setup header with title and controls"""
        header_layout = QHBoxLayout()

        title = QLabel("Worker Pools")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        header_layout.addWidget(title)

        subtitle = QLabel("Manage logical groups of workers")
        subtitle.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')}; margin-left: 16px;")
        header_layout.addWidget(subtitle)

        header_layout.addStretch()

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search pools...")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet(f"""
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
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        header_layout.addWidget(self.search_input)

        # View toggle buttons
        view_toggle_layout = QHBoxLayout()
        view_toggle_layout.setSpacing(0)

        self.cards_view_btn = QPushButton("🎴")
        self.cards_view_btn.setCheckable(True)
        self.cards_view_btn.setChecked(True)
        self.cards_view_btn.setFixedSize(36, 36)
        self.cards_view_btn.clicked.connect(lambda: self._switch_view("cards"))

        self.table_view_btn = QPushButton("📋")
        self.table_view_btn.setCheckable(True)
        self.table_view_btn.setFixedSize(36, 36)
        self.table_view_btn.clicked.connect(lambda: self._switch_view("table"))

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
        self.cards_view_btn.setStyleSheet(view_btn_style + "QPushButton { border-radius: 8px 0 0 8px; }")
        self.table_view_btn.setStyleSheet(view_btn_style + "QPushButton { border-radius: 0 8px 8px 0; }")

        view_toggle_layout.addWidget(self.cards_view_btn)
        view_toggle_layout.addWidget(self.table_view_btn)
        header_layout.addLayout(view_toggle_layout)

        header_layout.addSpacing(16)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
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

        # Create button
        create_btn = QPushButton("+ Create Pool")
        create_btn.setStyleSheet(f"""
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
        """)
        create_btn.clicked.connect(self._on_create_pool)
        header_layout.addWidget(create_btn)

        parent_layout.addLayout(header_layout)

    def _setup_cards_view(self):
        """Setup cards view with scroll area"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)

        self.cards_container = QWidget()
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setSpacing(20)
        self.cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll_area.setWidget(self.cards_container)
        self.content_stack.addWidget(scroll_area)

    def _setup_table_view(self):
        """Setup table view"""
        self.pools_table = DataTable(
            [
                ("Name", "name", 150),
                ("Description", "description", -1),
                ("Workers", "worker_count", 100),
                ("Min Workers", "min_workers", 100),
                ("Max Workers", "max_workers", 100),
                ("Status", "status", 100),
            ]
        )
        self.pools_table.set_status_column("status")
        self.pools_table.refresh_btn.clicked.connect(self._on_refresh)
        self.content_stack.addWidget(self.pools_table)

    def _setup_auto_refresh(self):
        """Setup auto-refresh timer"""
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_refresh)
        self.refresh_timer.start(self.AUTO_REFRESH_INTERVAL)

    def _switch_view(self, view_type: str):
        """Switch between cards and table views"""
        self._current_view = view_type
        self.cards_view_btn.setChecked(view_type == "cards")
        self.table_view_btn.setChecked(view_type == "table")

        if view_type == "cards":
            self.content_stack.setCurrentIndex(0)
        else:
            self.content_stack.setCurrentIndex(1)

    def _on_search_changed(self, text: str):
        """Handle search input changes"""
        filtered_pools = [
            pool for pool in self._pools_data
            if text.lower() in pool.get("name", "").lower()
            or text.lower() in pool.get("description", "").lower()
        ]
        self._update_cards_view(filtered_pools)

    def _update_stats(self):
        """Update statistics cards"""
        total_pools = len(self._pools_data)
        active_pools = sum(1 for p in self._pools_data if p.get("workers"))
        total_workers = sum(len(p.get("workers", [])) for p in self._pools_data)

        total_max = sum(p.get("max_workers", 10) for p in self._pools_data) or 1
        avg_utilization = (total_workers / total_max * 100) if total_max > 0 else 0

        self.total_pools_card.set_value(str(total_pools))
        self.active_pools_card.set_value(str(active_pools))
        self.total_workers_card.set_value(str(total_workers))
        self.avg_utilization_card.set_value(f"{avg_utilization:.0f}%")

    def _update_cards_view(self, pools: list):
        """Update cards view with pool data"""
        # Clear existing cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new cards
        cols = 3  # Number of columns
        for i, pool in enumerate(pools):
            card = PoolCard(pool)
            card.clicked.connect(self._on_pool_clicked)
            card.action_triggered.connect(self._on_pool_action)
            card.setMinimumWidth(300)
            card.setMaximumWidth(400)

            row = i // cols
            col = i % cols
            self.cards_layout.addWidget(card, row, col)

        # Add stretch to push cards to top-left
        self.cards_layout.setRowStretch(len(pools) // cols + 1, 1)
        self.cards_layout.setColumnStretch(cols, 1)

    def set_pools(self, pools: list):
        """Update pools list"""
        self._pools_data = pools

        # Update statistics
        self._update_stats()

        # Update cards view
        self._update_cards_view(pools)

        # Update table view
        display_data = []
        for pool in pools:
            display_data.append({
                **pool,
                "worker_count": len(pool.get("workers", [])),
                "status": "active" if pool.get("workers") else "empty",
            })
        self.pools_table.set_data(display_data)

    def _on_refresh(self):
        """Handle refresh"""
        self.refresh_requested.emit()

    def _on_pool_clicked(self, pool_data: dict):
        """Handle pool card click"""
        # Show pool details in detail panel
        if hasattr(self, 'detail_panel') and self.detail_panel:
            self.detail_panel.show_pool(pool_data)
        else:
            # Show details in a message box as fallback
            pool_name = pool_data.get("name", "Unknown")
            workers = pool_data.get("workers", 0)
            status = pool_data.get("status", "unknown")
            QMessageBox.information(
                self,
                f"Pool: {pool_name}",
                f"Workers: {workers}\nStatus: {status}\n\n"
                f"Use the Edit action to modify this pool."
            )

    def _on_pool_action(self, action: str, pool_data: dict):
        """Handle pool action from card menu"""
        if action == "edit":
            self._edit_pool(pool_data)
        elif action == "scale":
            self._scale_pool(pool_data)
        elif action == "delete":
            self._delete_pool(pool_data)

    def _edit_pool(self, pool_data: dict):
        """Open edit dialog for pool"""
        dialog = PoolCreateDialog(self)
        # Pre-fill with existing data
        dialog.name_input.setText(pool_data.get("name", ""))
        dialog.description_input.setText(pool_data.get("description", ""))
        dialog.min_workers_input.setValue(pool_data.get("min_workers", 0))
        dialog.max_workers_input.setValue(pool_data.get("max_workers", 10))
        dialog.pool_created.connect(self._handle_pool_updated)
        dialog.exec()

    def _scale_pool(self, pool_data: dict):
        """Open scale dialog for pool"""
        dialog = ScalePoolDialog(pool_data, self)
        dialog.scale_confirmed.connect(self._handle_pool_scaled)
        dialog.exec()

    def _handle_pool_scaled(self, pool_name: str, target_count: int):
        """Handle pool scaling"""
        if self.api_client:
            try:
                # Call API to scale pool
                self.api_client.scale_pool(pool_name, target_count)
                self.refresh_requested.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to scale pool: {str(e)}")
        else:
            self.refresh_requested.emit()

    def _delete_pool(self, pool_data: dict):
        """Confirm and delete pool"""
        pool_name = pool_data.get("name", "Unknown")
        reply = QMessageBox.question(
            self,
            "Delete Pool",
            f"Are you sure you want to delete pool '{pool_name}'?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.api_client:
                try:
                    self.api_client.delete_pool(pool_name)
                    self.refresh_requested.emit()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to delete pool: {str(e)}")
            else:
                self.refresh_requested.emit()

    def _on_create_pool(self):
        """Handle create pool"""
        dialog = PoolCreateDialog(self)
        dialog.pool_created.connect(self._handle_pool_created)
        dialog.exec()

    def _handle_pool_created(self, pool_config: dict):
        """Handle pool creation from dialog"""
        if self.api_client:
            try:
                # Call API to create pool
                self.api_client.create_pool(pool_config)
                self.refresh_requested.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create pool: {str(e)}")
        else:
            # No API client - just emit refresh
            self.refresh_requested.emit()

    def _handle_pool_updated(self, pool_config: dict):
        """Handle pool update from edit dialog"""
        if self.api_client:
            try:
                self.api_client.update_pool(pool_config)
                self.refresh_requested.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update pool: {str(e)}")
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
