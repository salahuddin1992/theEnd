"""
Queues View - Priority queues management page
صفحة إدارة طوابير الأولوية
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


class QueuesView(QWidget):
    """Priority queues management view"""

    refresh_requested = Signal()

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._setup_ui()

    def _setup_ui(self):
        """Setup queues view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("Priority Queues")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        header_layout.addWidget(title)

        subtitle = QLabel("Manage job scheduling priorities")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; margin-left: 16px;")
        header_layout.addWidget(subtitle)

        header_layout.addStretch()

        # Create button
        create_btn = QPushButton("+ Create Queue")
        create_btn.clicked.connect(self._on_create_queue)
        header_layout.addWidget(create_btn)

        layout.addLayout(header_layout)

        # Queues table
        self.queues_table = DataTable([
            ("Name", "name", 150),
            ("Priority", "priority", 100),
            ("Pending Jobs", "pending_count", 120),
            ("Running Jobs", "running_count", 120),
            ("Weight", "weight", 80),
            ("Status", "status", 100),
        ])
        self.queues_table.set_status_column("status")
        self.queues_table.refresh_btn.clicked.connect(self._on_refresh)
        layout.addWidget(self.queues_table)

    def set_queues(self, queues: list):
        """Update queues list"""
        display_data = []
        for queue in queues:
            display_data.append({
                **queue,
                "pending_count": queue.get("pending_jobs", 0),
                "running_count": queue.get("running_jobs", 0),
                "status": "active" if queue.get("enabled", True) else "disabled",
            })
        self.queues_table.set_data(display_data)

    def _on_refresh(self):
        """Handle refresh"""
        self.refresh_requested.emit()

    def _on_create_queue(self):
        """Handle create queue"""
        # TODO: Implement queue creation dialog
        pass

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
