"""
Pools View - Worker pools management page
صفحة إدارة مجموعات العمال
"""

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..api.client import APIClient
from ..resources.styles import COLORS
from ..widgets.data_table import DataTable


class PoolsView(QWidget):
    """Worker pools management view"""

    refresh_requested = Signal()

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._setup_ui()

    def _setup_ui(self):
        """Setup pools view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("Worker Pools")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        header_layout.addWidget(title)

        subtitle = QLabel("Manage logical groups of workers")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; margin-left: 16px;")
        header_layout.addWidget(subtitle)

        header_layout.addStretch()

        # Create button
        create_btn = QPushButton("+ Create Pool")
        create_btn.clicked.connect(self._on_create_pool)
        header_layout.addWidget(create_btn)

        layout.addLayout(header_layout)

        # Pools table
        self.pools_table = DataTable([
            ("Name", "name", 150),
            ("Description", "description", -1),
            ("Workers", "worker_count", 100),
            ("Min Workers", "min_workers", 100),
            ("Max Workers", "max_workers", 100),
            ("Status", "status", 100),
        ])
        self.pools_table.set_status_column("status")
        self.pools_table.refresh_btn.clicked.connect(self._on_refresh)
        layout.addWidget(self.pools_table)

    def set_pools(self, pools: list):
        """Update pools list"""
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

    def _on_create_pool(self):
        """Handle create pool"""
        # TODO: Implement pool creation dialog
        pass

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
