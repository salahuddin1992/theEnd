"""
Advanced Fluent Data Table
جدول بيانات متقدم بتصميم Fluent

Features:
- Sortable columns
- Filterable data
- Row selection (single/multi)
- Context menu
- Pagination
- Column resizing
- Custom cell renderers
- Export functionality
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPoint, QSize, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .components import ButtonVariant, FluentButton
from .fluent_design import FluentDesignSystem
from .titlebar import FluentIcons

# ═══════════════════════════════════════════════════════════════════════════════
# COLUMN DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

class ColumnType(Enum):
    """Column data types"""
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    STATUS = "status"
    PROGRESS = "progress"
    BADGE = "badge"
    ACTIONS = "actions"
    CHECKBOX = "checkbox"


@dataclass
class Column:
    """Table column definition"""
    key: str
    label: str
    type: ColumnType = ColumnType.TEXT
    width: int = 150
    min_width: int = 50
    sortable: bool = True
    filterable: bool = True
    visible: bool = True
    align: Qt.AlignmentFlag = Qt.AlignLeft
    formatter: Optional[Callable[[Any], str]] = None
    status_colors: Optional[Dict[str, str]] = None


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class FluentTableModel(QAbstractTableModel):
    """
    Custom table model for Fluent data table.
    نموذج جدول مخصص لجدول Fluent
    """

    def __init__(self, columns: List[Column], parent=None):
        super().__init__(parent)
        self._columns = columns
        self._data: List[Dict[str, Any]] = []
        self._selected_rows: set = set()

    def rowCount(self, parent=None) -> int:
        return len(self._data)

    def columnCount(self, parent=None) -> int:
        return len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        column = self._columns[col]
        value = self._data[row].get(column.key, "")

        if role == Qt.DisplayRole:
            if column.formatter:
                return column.formatter(value)
            if column.type == ColumnType.DATE and isinstance(value, datetime):
                return value.strftime("%Y-%m-%d %H:%M")
            return str(value) if value is not None else ""

        elif role == Qt.TextAlignmentRole:
            return column.align | Qt.AlignVCenter

        elif role == Qt.UserRole:
            # Return raw data for custom rendering
            return value

        elif role == Qt.UserRole + 1:
            # Return column type
            return column.type

        elif role == Qt.UserRole + 2:
            # Return full row data
            return self._data[row]

        elif role == Qt.UserRole + 3:
            # Return status colors
            return column.status_colors

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._columns[section].label
        return None

    def set_data(self, data: List[Dict[str, Any]]):
        """Set table data"""
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def get_row_data(self, row: int) -> Optional[Dict[str, Any]]:
        """Get data for a specific row"""
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def add_row(self, row_data: Dict[str, Any]):
        """Add a new row"""
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        self._data.append(row_data)
        self.endInsertRows()

    def remove_row(self, row: int):
        """Remove a row"""
        if 0 <= row < len(self._data):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._data[row]
            self.endRemoveRows()

    def update_row(self, row: int, data: Dict[str, Any]):
        """Update a row's data"""
        if 0 <= row < len(self._data):
            self._data[row].update(data)
            self.dataChanged.emit(
                self.index(row, 0),
                self.index(row, len(self._columns) - 1)
            )

    def get_all_data(self) -> List[Dict[str, Any]]:
        """Get all data"""
        return self._data.copy()


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOM DELEGATE
# ═══════════════════════════════════════════════════════════════════════════════

class FluentTableDelegate(QStyledItemDelegate):
    """
    Custom delegate for Fluent table styling.
    مفوض مخصص لتنسيق جدول Fluent
    """

    action_clicked = Signal(int, str)  # row, action_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered_row = -1
        self._hovered_action = -1

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        """Custom paint for cells"""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        colors = FluentDesignSystem().colors
        rect = option.rect
        value = index.data(Qt.UserRole)
        col_type = index.data(Qt.UserRole + 1)
        status_colors = index.data(Qt.UserRole + 3)

        # Background
        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, QColor(colors.fill_subtle_secondary))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, QColor(colors.fill_subtle))

        # Content based on column type
        if col_type == ColumnType.STATUS:
            self._paint_status(painter, rect, value, status_colors, colors)
        elif col_type == ColumnType.PROGRESS:
            self._paint_progress(painter, rect, value, colors)
        elif col_type == ColumnType.BADGE:
            self._paint_badge(painter, rect, value, colors)
        else:
            # Default text rendering
            text = index.data(Qt.DisplayRole)
            painter.setPen(QColor(colors.text_primary))
            painter.drawText(
                rect.adjusted(12, 0, -12, 0),
                index.data(Qt.TextAlignmentRole) | Qt.AlignVCenter,
                str(text)
            )

        painter.restore()

    def _paint_status(self, painter: QPainter, rect, value, status_colors, colors):
        """Paint status badge"""
        if not value:
            return

        status = str(value).lower()

        # Default colors
        default_colors = {
            "running": colors.status_running,
            "active": colors.status_running,
            "completed": colors.status_completed,
            "success": colors.status_completed,
            "pending": colors.status_pending,
            "queued": colors.status_pending,
            "failed": colors.status_failed,
            "error": colors.status_failed,
            "idle": colors.status_idle,
            "offline": colors.status_idle,
        }

        if status_colors:
            color = status_colors.get(status, colors.text_secondary)
        else:
            color = default_colors.get(status, colors.text_secondary)

        # Draw status indicator
        indicator_rect = rect.adjusted(12, (rect.height() - 8) // 2, 0, 0)
        indicator_rect.setWidth(8)
        indicator_rect.setHeight(8)

        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(indicator_rect)

        # Draw text
        text_rect = rect.adjusted(28, 0, -12, 0)
        painter.setPen(QColor(color))
        font = painter.font()
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, str(value).title())

    def _paint_progress(self, painter: QPainter, rect, value, colors):
        """Paint progress bar"""
        try:
            progress = float(value) if value else 0
        except (ValueError, TypeError):
            progress = 0

        progress = max(0, min(100, progress))

        # Track
        track_rect = rect.adjusted(12, (rect.height() - 4) // 2, -12, 0)
        track_rect.setHeight(4)

        painter.setBrush(QColor(colors.stroke_control))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(track_rect, 2, 2)

        # Progress
        if progress > 0:
            progress_width = int(track_rect.width() * progress / 100)
            progress_rect = track_rect.adjusted(0, 0, 0, 0)
            progress_rect.setWidth(progress_width)

            painter.setBrush(QColor(colors.accent))
            painter.drawRoundedRect(progress_rect, 2, 2)

    def _paint_badge(self, painter: QPainter, rect, value, colors):
        """Paint badge"""
        if not value:
            return

        text = str(value)

        # Calculate badge size
        font = QFont("Segoe UI", 10)
        font.setWeight(QFont.DemiBold)
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(text)

        badge_rect = rect.adjusted(12, (rect.height() - 20) // 2, 0, 0)
        badge_rect.setWidth(text_width + 16)
        badge_rect.setHeight(20)

        # Draw badge background
        painter.setBrush(QColor(colors.fill_subtle))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(badge_rect, 4, 4)

        # Draw text
        painter.setPen(QColor(colors.text_primary))
        painter.setFont(font)
        painter.drawText(badge_rect, Qt.AlignCenter, text)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 44)


# ═══════════════════════════════════════════════════════════════════════════════
# FILTER PROXY MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class FluentFilterProxyModel(QSortFilterProxyModel):
    """
    Filter proxy model with multiple filter support.
    نموذج وسيط للفلترة مع دعم فلاتر متعددة
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filters: Dict[int, str] = {}
        self._global_filter = ""

    def set_filter(self, column: int, filter_text: str):
        """Set filter for a specific column"""
        if filter_text:
            self._filters[column] = filter_text.lower()
        elif column in self._filters:
            del self._filters[column]
        self.invalidateFilter()

    def set_global_filter(self, filter_text: str):
        """Set global filter (searches all columns)"""
        self._global_filter = filter_text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()

        # Check global filter
        if self._global_filter:
            found = False
            for col in range(model.columnCount()):
                index = model.index(source_row, col)
                value = str(model.data(index, Qt.DisplayRole) or "").lower()
                if self._global_filter in value:
                    found = True
                    break
            if not found:
                return False

        # Check column filters
        for col, filter_text in self._filters.items():
            index = model.index(source_row, col)
            value = str(model.data(index, Qt.DisplayRole) or "").lower()
            if filter_text not in value:
                return False

        return True


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT DATA TABLE
# ═══════════════════════════════════════════════════════════════════════════════

class FluentDataTable(QWidget):
    """
    Advanced Fluent Design data table.
    جدول بيانات متقدم بتصميم Fluent
    """

    row_clicked = Signal(int, dict)  # row index, row data
    row_double_clicked = Signal(int, dict)
    selection_changed = Signal(list)  # list of selected row data
    action_requested = Signal(str, dict)  # action name, row data

    def __init__(self, columns: List[Column], parent=None):
        super().__init__(parent)

        self._columns = columns
        self._selected_rows: List[int] = []

        self._setup_ui()
        self._setup_context_menu()

    def _setup_ui(self):
        """Setup table UI"""
        colors = FluentDesignSystem().colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Table
        self._model = FluentTableModel(self._columns)
        self._proxy_model = FluentFilterProxyModel()
        self._proxy_model.setSourceModel(self._model)

        self._table = QTableView()
        self._table.setModel(self._proxy_model)
        self._table.setItemDelegate(FluentTableDelegate(self))
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(False)
        self._table.setSortingEnabled(True)
        self._table.setMouseTracking(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)

        # Header styling
        header = self._table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(50)

        # Set column widths
        for i, col in enumerate(self._columns):
            header.resizeSection(i, col.width)

        # Styling
        self._table.setStyleSheet(f"""
            QTableView {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            QTableView::item {{
                padding: 8px 12px;
                border: none;
                border-bottom: 1px solid {colors.stroke_divider};
            }}
            QTableView::item:selected {{
                background-color: {colors.fill_subtle_secondary};
                color: {colors.text_primary};
            }}
            QTableView::item:hover {{
                background-color: {colors.fill_subtle};
            }}
            QHeaderView::section {{
                background-color: transparent;
                color: {colors.text_secondary};
                padding: 12px;
                border: none;
                border-bottom: 1px solid {colors.stroke_divider};
                font-weight: 600;
                font-size: 12px;
            }}
            QHeaderView::section:hover {{
                background-color: {colors.fill_subtle};
                color: {colors.text_primary};
            }}
        """)

        # Connect signals
        self._table.clicked.connect(self._on_row_clicked)
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self._table)

        # Footer (pagination)
        footer = self._create_footer()
        layout.addWidget(footer)

    def _create_toolbar(self) -> QWidget:
        """Create table toolbar"""
        colors = FluentDesignSystem().colors

        toolbar = QFrame()
        toolbar.setStyleSheet(f"""
            QFrame {{
                background-color: {colors.bg_card_default};
                border: 1px solid {colors.stroke_surface};
                border-radius: 8px;
                padding: 8px;
                margin-bottom: 8px;
            }}
        """)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search...")
        self._search_input.setMinimumWidth(250)
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {colors.accent};
            }}
            QLineEdit::placeholder {{
                color: {colors.text_tertiary};
            }}
        """)
        layout.addWidget(self._search_input)

        layout.addStretch()

        # Filter dropdown
        self._filter_combo = QComboBox()
        self._filter_combo.addItem("All Status", "")
        self._filter_combo.addItem("Running", "running")
        self._filter_combo.addItem("Pending", "pending")
        self._filter_combo.addItem("Completed", "completed")
        self._filter_combo.addItem("Failed", "failed")
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self._filter_combo.setMinimumWidth(140)
        self._filter_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QComboBox:hover {{
                background-color: {colors.fill_control_secondary};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors.bg_solid_secondary};
                border: 1px solid {colors.stroke_surface};
                border-radius: 6px;
                padding: 4px;
                selection-background-color: {colors.fill_subtle};
            }}
        """)
        layout.addWidget(self._filter_combo)

        # Refresh button
        refresh_btn = FluentButton("", FluentIcons.REFRESH, ButtonVariant.SUBTLE)
        refresh_btn.setFixedSize(36, 36)
        refresh_btn.setToolTip("Refresh")
        refresh_btn.clicked.connect(lambda: self.action_requested.emit("refresh", {}))
        layout.addWidget(refresh_btn)

        # Export button
        export_btn = FluentButton("Export", "", ButtonVariant.SUBTLE)
        export_btn.clicked.connect(lambda: self.action_requested.emit("export", {}))
        layout.addWidget(export_btn)

        return toolbar

    def _create_footer(self) -> QWidget:
        """Create table footer with pagination"""
        colors = FluentDesignSystem().colors

        footer = QFrame()
        footer.setStyleSheet("""
            QFrame {
                background-color: transparent;
                padding: 8px 0;
            }
        """)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # Row count
        self._row_count_label = QLabel("0 items")
        self._row_count_label.setStyleSheet(f"""
            color: {colors.text_secondary};
            font-size: 12px;
        """)
        layout.addWidget(self._row_count_label)

        layout.addStretch()

        # Selection info
        self._selection_label = QLabel("")
        self._selection_label.setStyleSheet(f"""
            color: {colors.text_secondary};
            font-size: 12px;
        """)
        layout.addWidget(self._selection_label)

        return footer

    def _setup_context_menu(self):
        """Setup context menu"""
        self._context_menu = QMenu(self)
        colors = FluentDesignSystem().colors

        self._context_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {colors.bg_solid_secondary};
                border: 1px solid {colors.stroke_surface};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px 8px 12px;
                border-radius: 4px;
                color: {colors.text_primary};
            }}
            QMenu::item:selected {{
                background-color: {colors.fill_subtle};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {colors.stroke_divider};
                margin: 4px 8px;
            }}
        """)

        # Add actions
        view_action = self._context_menu.addAction(FluentIcons.INFO + " View Details")
        view_action.triggered.connect(lambda: self._trigger_action("view"))

        edit_action = self._context_menu.addAction(FluentIcons.EDIT + " Edit")
        edit_action.triggered.connect(lambda: self._trigger_action("edit"))

        self._context_menu.addSeparator()

        copy_action = self._context_menu.addAction(FluentIcons.COPY + " Copy")
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(lambda: self._trigger_action("copy"))

        self._context_menu.addSeparator()

        delete_action = self._context_menu.addAction(FluentIcons.DELETE + " Delete")
        delete_action.triggered.connect(lambda: self._trigger_action("delete"))

    def _show_context_menu(self, pos: QPoint):
        """Show context menu"""
        global_pos = self._table.viewport().mapToGlobal(pos)
        self._context_menu.exec(global_pos)

    def _trigger_action(self, action: str):
        """Trigger an action on selected rows"""
        selected = self.get_selected_data()
        if selected:
            self.action_requested.emit(action, selected[0] if len(selected) == 1 else {"items": selected})

    def _on_search_changed(self, text: str):
        """Handle search input change"""
        self._proxy_model.set_global_filter(text)
        self._update_row_count()

    def _on_filter_changed(self, index: int):
        """Handle filter dropdown change"""
        status = self._filter_combo.currentData()
        # Find status column index
        for i, col in enumerate(self._columns):
            if col.type == ColumnType.STATUS:
                self._proxy_model.set_filter(i, status)
                break
        self._update_row_count()

    def _on_row_clicked(self, index: QModelIndex):
        """Handle row click"""
        source_index = self._proxy_model.mapToSource(index)
        row_data = self._model.get_row_data(source_index.row())
        if row_data:
            self.row_clicked.emit(source_index.row(), row_data)

    def _on_row_double_clicked(self, index: QModelIndex):
        """Handle row double click"""
        source_index = self._proxy_model.mapToSource(index)
        row_data = self._model.get_row_data(source_index.row())
        if row_data:
            self.row_double_clicked.emit(source_index.row(), row_data)

    def _on_selection_changed(self):
        """Handle selection change"""
        selected_data = self.get_selected_data()
        self.selection_changed.emit(selected_data)
        self._update_selection_label(len(selected_data))

    def _update_row_count(self):
        """Update row count label"""
        count = self._proxy_model.rowCount()
        total = self._model.rowCount()
        if count == total:
            self._row_count_label.setText(f"{count} items")
        else:
            self._row_count_label.setText(f"{count} of {total} items")

    def _update_selection_label(self, count: int):
        """Update selection label"""
        if count > 0:
            self._selection_label.setText(f"{count} selected")
        else:
            self._selection_label.setText("")

    # Public API
    def set_data(self, data: List[Dict[str, Any]]):
        """Set table data"""
        self._model.set_data(data)
        self._update_row_count()

    def add_row(self, data: Dict[str, Any]):
        """Add a row"""
        self._model.add_row(data)
        self._update_row_count()

    def remove_row(self, row: int):
        """Remove a row"""
        self._model.remove_row(row)
        self._update_row_count()

    def update_row(self, row: int, data: Dict[str, Any]):
        """Update a row"""
        self._model.update_row(row, data)

    def get_selected_data(self) -> List[Dict[str, Any]]:
        """Get selected rows data"""
        result = []
        for index in self._table.selectionModel().selectedRows():
            source_index = self._proxy_model.mapToSource(index)
            data = self._model.get_row_data(source_index.row())
            if data:
                result.append(data)
        return result

    def clear_selection(self):
        """Clear selection"""
        self._table.clearSelection()

    def select_row(self, row: int):
        """Select a specific row"""
        index = self._model.index(row, 0)
        proxy_index = self._proxy_model.mapFromSource(index)
        self._table.selectRow(proxy_index.row())

    def get_all_data(self) -> List[Dict[str, Any]]:
        """Get all table data"""
        return self._model.get_all_data()

    def export_to_json(self, filepath: str):
        """Export data to JSON file"""
        data = self.get_all_data()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)

    def refresh(self):
        """Refresh the table"""
        self._model.layoutChanged.emit()
