"""
Sidebar Navigation Widget
ويدجت الشريط الجانبي للتنقل
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..resources.styles import COLORS


class SidebarButton(QPushButton):
    """A styled button for sidebar navigation"""

    def __init__(self, text: str, icon: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar_button")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)

        # Set text with icon
        if icon:
            self.setText(f"  {icon}   {text}")
        else:
            self.setText(f"  {text}")

        self.setMinimumHeight(44)


class Sidebar(QFrame):
    """Main sidebar navigation widget"""

    page_changed = Signal(str)  # Emits page name when navigation changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(220)

        self._buttons: dict[str, SidebarButton] = {}
        self._setup_ui()

    def _setup_ui(self):
        """Setup sidebar UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo/Brand section
        logo_frame = QFrame()
        logo_layout = QHBoxLayout(logo_frame)
        logo_layout.setContentsMargins(20, 20, 20, 20)

        logo_icon = QLabel("☁")
        logo_icon.setStyleSheet(f"font-size: 24px; color: {COLORS['primary']};")
        logo_layout.addWidget(logo_icon)

        logo_text = QLabel("NebulaCompute")
        logo_text.setObjectName("sidebar_logo")
        logo_text.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {COLORS['text_primary']};")
        logo_layout.addWidget(logo_text)
        logo_layout.addStretch()

        layout.addWidget(logo_frame)

        # Navigation section label
        nav_label = QLabel("  NAVIGATION")
        nav_label.setStyleSheet(
            f"""
            color: {COLORS['text_muted']};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 1px;
            padding: 16px 16px 8px 16px;
        """
        )
        layout.addWidget(nav_label)

        # Navigation buttons
        nav_items = [
            ("dashboard", "Dashboard", "📊"),
            ("jobs", "Jobs", "📋"),
            ("workers", "Workers", "🖥"),
            ("templates", "Templates", "📄"),
            ("pools", "Pools", "🏊"),
            ("queues", "Queues", "📬"),
            ("metrics", "Metrics", "📈"),
        ]

        for page_id, text, icon in nav_items:
            btn = SidebarButton(text, icon)
            btn.clicked.connect(lambda checked, pid=page_id: self._on_button_clicked(pid))
            self._buttons[page_id] = btn
            layout.addWidget(btn)

        # Developer section label
        dev_label = QLabel("  DEVELOPER")
        dev_label.setStyleSheet(
            f"""
            color: {COLORS['text_muted']};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 1px;
            padding: 16px 16px 8px 16px;
        """
        )
        layout.addWidget(dev_label)

        # Developer tools
        dev_items = [
            ("scripts", "Script Editor", "🐍"),
            ("plugins", "Plugins", "🔌"),
            ("terminal", "Terminal", "💻"),
        ]

        for page_id, text, icon in dev_items:
            btn = SidebarButton(text, icon)
            btn.clicked.connect(lambda checked, pid=page_id: self._on_button_clicked(pid))
            self._buttons[page_id] = btn
            layout.addWidget(btn)

        layout.addStretch()

        # Settings section label
        settings_label = QLabel("  SYSTEM")
        settings_label.setStyleSheet(
            f"""
            color: {COLORS['text_muted']};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 1px;
            padding: 16px 16px 8px 16px;
        """
        )
        layout.addWidget(settings_label)

        # System buttons
        system_items = [
            ("settings", "Settings", "⚙"),
            ("logs", "Logs", "📜"),
        ]

        for page_id, text, icon in system_items:
            btn = SidebarButton(text, icon)
            btn.clicked.connect(lambda checked, pid=page_id: self._on_button_clicked(pid))
            self._buttons[page_id] = btn
            layout.addWidget(btn)

        # Connection status
        self.status_frame = QFrame()
        status_layout = QHBoxLayout(self.status_frame)
        status_layout.setContentsMargins(16, 16, 16, 16)

        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
        status_layout.addWidget(self.status_indicator)

        self.status_text = QLabel("Disconnected")
        self.status_text.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        status_layout.addWidget(self.status_text)
        status_layout.addStretch()

        layout.addWidget(self.status_frame)

        # Set default selection
        self.set_active_page("dashboard")

    def _on_button_clicked(self, page_id: str):
        """Handle navigation button click"""
        self.set_active_page(page_id)
        self.page_changed.emit(page_id)

    def set_active_page(self, page_id: str):
        """Set the active page in sidebar"""
        for pid, btn in self._buttons.items():
            btn.setChecked(pid == page_id)

    def set_connection_status(self, connected: bool, server: str = ""):
        """Update connection status display"""
        if connected:
            self.status_indicator.setStyleSheet(f"color: {COLORS['success']}; font-size: 10px;")
            self.status_text.setText("Connected")
            self.status_text.setStyleSheet(f"color: {COLORS['success']}; font-size: 12px;")
        else:
            self.status_indicator.setStyleSheet(f"color: {COLORS['danger']}; font-size: 10px;")
            self.status_text.setText("Disconnected")
            self.status_text.setStyleSheet(f"color: {COLORS['danger']}; font-size: 12px;")
