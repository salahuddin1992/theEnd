"""
Data Table Widget
ويدجت جدول البيانات
"""

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..resources.styles import COLORS, get_status_color


class StatusLabel(QLabel):
    """A label styled for status display"""

    def __init__(self, status: str, parent=None):
        super().__init__(status, parent)
        self.set_status(status)

    def set_status(self, status: str):
        """Update the status and styling"""
        self.setText(status)
        color = get_status_color(status)
        self.setStyleSheet(f"""
            color: {color};
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 4px;
            background-color: {color}20;
        """)


class DataTable(QFrame):
    """A styled data table with search and actions"""

    row_selected = Signal(int, dict)  # row index, row data
    row_double_clicked = Signal(int, dict)
    action_clicked = Signal(str, int, dict)  # action name, row index, row data

    def __init__(
        self,
        columns: List[tuple],  # [(column_name, column_key, width), ...]
        parent=None
    ):
        super().__init__(parent)
        self._columns = columns
        self._data: List[dict] = []
        self._actions: List[tuple] = []  # [(action_name, callback), ...]
        self._status_column: Optional[str] = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup table UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.setMinimumWidth(250)
        self.search_input.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search_input)

        toolbar.addStretch()

        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("secondary_button")
        toolbar.addWidget(self.refresh_btn)

        layout.addLayout(toolbar)

        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(len(self._columns))
        self.table.setHorizontalHeaderLabels([col[0] for col in self._columns])

        # Configure table
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)

        # Set column widths
        header = self.table.horizontalHeader()
        for i, (_, _, width) in enumerate(self._columns):
            if width == -1:
                header.setSectionResizeMode(i, QHeaderView.Stretch)
            else:
                self.table.setColumnWidth(i, width)

        # Connect signals
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_double_click)

        layout.addWidget(self.table)

        # Status bar
        self.status_label = QLabel("0 items")
        self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(self.status_label)

    def set_status_column(self, column_key: str):
        """Set which column should be rendered as status"""
        self._status_column = column_key

    def set_data(self, data: List[dict]):
        """Set table data"""
        self._data = data
        self._refresh_table()

    def _refresh_table(self, filter_text: str = ""):
        """Refresh table with current data"""
        self.table.setRowCount(0)

        filtered_data = self._data
        if filter_text:
            filter_lower = filter_text.lower()
            filtered_data = [
                row for row in self._data
                if any(
                    filter_lower in str(row.get(col[1], "")).lower()
                    for col in self._columns
                )
            ]

        self.table.setRowCount(len(filtered_data))

        for row_idx, row_data in enumerate(filtered_data):
            for col_idx, (_, col_key, _) in enumerate(self._columns):
                value = row_data.get(col_key, "")

                if col_key == self._status_column:
                    # Create status widget
                    status_widget = StatusLabel(str(value))
                    self.table.setCellWidget(row_idx, col_idx, status_widget)
                else:
                    item = QTableWidgetItem(str(value))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(row_idx, col_idx, item)

            # Set row height
            self.table.setRowHeight(row_idx, 48)

        self.status_label.setText(f"{len(filtered_data)} items")

    def _on_search(self, text: str):
        """Handle search input"""
        self._refresh_table(text)

    def _on_selection_changed(self):
        """Handle row selection"""
        rows = self.table.selectedItems()
        if rows:
            row_idx = rows[0].row()
            if row_idx < len(self._data):
                self.row_selected.emit(row_idx, self._data[row_idx])

    def _on_double_click(self, item: QTableWidgetItem):
        """Handle double click"""
        row_idx = item.row()
        if row_idx < len(self._data):
            self.row_double_clicked.emit(row_idx, self._data[row_idx])

    def get_selected_data(self) -> Optional[dict]:
        """Get currently selected row data"""
        rows = self.table.selectedItems()
        if rows:
            row_idx = rows[0].row()
            if row_idx < len(self._data):
                return self._data[row_idx]
        return None

    def clear(self):
        """Clear table data"""
        self._data = []
        self.table.setRowCount(0)
        self.status_label.setText("0 items")
