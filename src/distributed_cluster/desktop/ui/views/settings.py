"""
Fluent Settings View
صفحة الإعدادات بتصميم Fluent

Application settings with:
- Connection settings
- Appearance (themes)
- Notifications
- Keyboard shortcuts
- About
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..components import ButtonVariant, FluentButton, FluentCard, FluentInput, FluentSwitch
from ..fluent_design import FluentDesignSystem
from ..titlebar import FluentIcons

# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS SECTION
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsSection(QWidget):
    """Base class for settings sections"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)

        self._title = title
        colors = FluentDesignSystem().colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 24px;
            font-weight: 600;
        """)
        layout.addWidget(title_label)

        # Content
        self._content = QVBoxLayout()
        self._content.setSpacing(16)
        layout.addLayout(self._content)
        layout.addStretch()

    def add_setting(self, widget: QWidget):
        """Add a setting widget"""
        self._content.addWidget(widget)


# ═══════════════════════════════════════════════════════════════════════════════
# SETTING ITEM
# ═══════════════════════════════════════════════════════════════════════════════

class SettingItem(FluentCard):
    """A single setting item with label, description and control"""

    def __init__(self, title: str, description: str = "",
                 control: QWidget = None, parent=None):
        super().__init__(parent=parent)

        colors = FluentDesignSystem().colors

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 14px;
            font-weight: 500;
        """)
        text_layout.addWidget(title_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet(f"""
                color: {colors.text_secondary};
                font-size: 12px;
            """)
            desc_label.setWordWrap(True)
            text_layout.addWidget(desc_label)

        layout.addLayout(text_layout, 1)

        # Control
        if control:
            layout.addWidget(control)

        container = QWidget()
        container.setLayout(layout)
        self.add_content(container)


# ═══════════════════════════════════════════════════════════════════════════════
# CONNECTION SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

class ConnectionSettings(SettingsSection):
    """Connection settings section"""

    connection_requested = Signal(str, str)  # url, token

    def __init__(self, parent=None):
        super().__init__("Connection", parent)

        FluentDesignSystem().colors

        # Server URL
        url_input = FluentInput("Server URL", "http://localhost:8765")
        self.add_setting(url_input)
        self._url_input = url_input

        # API Token
        token_input = FluentInput("API Token", "Enter your API token")
        self.add_setting(token_input)
        self._token_input = token_input

        # Auto-connect
        auto_connect = SettingItem(
            "Auto-connect on startup",
            "Automatically connect to the last used server when the app starts",
            FluentSwitch()
        )
        self.add_setting(auto_connect)

        # Reconnect
        reconnect = SettingItem(
            "Auto-reconnect",
            "Automatically try to reconnect when connection is lost",
            FluentSwitch()
        )
        self.add_setting(reconnect)

        # Connect button
        connect_btn = FluentButton("Connect", "", ButtonVariant.ACCENT)
        connect_btn.clicked.connect(self._on_connect)
        self.add_setting(connect_btn)

    def _on_connect(self):
        url = self._url_input.text()
        token = self._token_input.text()
        self.connection_requested.emit(url, token)


# ═══════════════════════════════════════════════════════════════════════════════
# APPEARANCE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

class AppearanceSettings(SettingsSection):
    """Appearance settings section"""

    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Appearance", parent)

        colors = FluentDesignSystem().colors

        # Theme
        theme_combo = QComboBox()
        theme_combo.addItems(["Dark", "Light", "System"])
        theme_combo.setMinimumWidth(150)
        theme_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px 12px;
            }}
        """)
        theme_combo.currentTextChanged.connect(self.theme_changed.emit)

        theme_setting = SettingItem(
            "App theme",
            "Select which theme to use for the application",
            theme_combo
        )
        self.add_setting(theme_setting)

        # Accent color
        accent_card = FluentCard(title="Accent Color")
        accent_layout = QHBoxLayout()
        accent_layout.setSpacing(8)

        accent_colors = [
            ("#0078D4", "Blue"),
            ("#744DA9", "Purple"),
            ("#E81123", "Red"),
            ("#FF8C00", "Orange"),
            ("#107C10", "Green"),
            ("#00B294", "Teal"),
        ]

        for color, name in accent_colors:
            color_btn = QFrame()
            color_btn.setFixedSize(36, 36)
            color_btn.setCursor(Qt.PointingHandCursor)
            color_btn.setStyleSheet(f"""
                QFrame {{
                    background-color: {color};
                    border-radius: 6px;
                    border: 2px solid transparent;
                }}
                QFrame:hover {{
                    border-color: {colors.text_primary};
                }}
            """)
            color_btn.setToolTip(name)
            accent_layout.addWidget(color_btn)

        accent_layout.addStretch()
        accent_widget = QWidget()
        accent_widget.setLayout(accent_layout)
        accent_card.add_content(accent_widget)
        self.add_setting(accent_card)

        # Compact mode
        compact = SettingItem(
            "Compact mode",
            "Use smaller spacing and controls",
            FluentSwitch()
        )
        self.add_setting(compact)

        # Animations
        animations = SettingItem(
            "Enable animations",
            "Show smooth animations and transitions",
            FluentSwitch()
        )
        animations._content_layout.itemAt(0).widget().layout().itemAt(1).widget().setChecked(True)
        self.add_setting(animations)


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

class NotificationSettings(SettingsSection):
    """Notification settings section"""

    def __init__(self, parent=None):
        super().__init__("Notifications", parent)

        # Enable notifications
        enable = SettingItem(
            "Enable notifications",
            "Show notifications for important events",
            FluentSwitch()
        )
        self.add_setting(enable)

        # Sound
        sound = SettingItem(
            "Notification sounds",
            "Play sounds for notifications",
            FluentSwitch()
        )
        self.add_setting(sound)

        # Job completed
        job_complete = SettingItem(
            "Job completed",
            "Notify when a job finishes",
            FluentSwitch()
        )
        self.add_setting(job_complete)

        # Job failed
        job_failed = SettingItem(
            "Job failed",
            "Notify when a job fails",
            FluentSwitch()
        )
        self.add_setting(job_failed)

        # Worker status
        worker_status = SettingItem(
            "Worker status changes",
            "Notify when workers go online/offline",
            FluentSwitch()
        )
        self.add_setting(worker_status)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

class DataSettings(SettingsSection):
    """Data and refresh settings"""

    def __init__(self, parent=None):
        super().__init__("Data & Refresh", parent)

        colors = FluentDesignSystem().colors

        # Auto-refresh
        refresh_switch = FluentSwitch()
        refresh_switch._widget = refresh_switch
        auto_refresh = SettingItem(
            "Auto-refresh",
            "Automatically refresh data at regular intervals",
            refresh_switch
        )
        self.add_setting(auto_refresh)

        # Refresh interval
        interval_spin = QSpinBox()
        interval_spin.setRange(1, 60)
        interval_spin.setValue(5)
        interval_spin.setSuffix(" seconds")
        interval_spin.setMinimumWidth(120)
        interval_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """)

        interval = SettingItem(
            "Refresh interval",
            "How often to refresh data automatically",
            interval_spin
        )
        self.add_setting(interval)

        # History
        history_spin = QSpinBox()
        history_spin.setRange(1, 30)
        history_spin.setValue(7)
        history_spin.setSuffix(" days")
        history_spin.setMinimumWidth(120)
        history_spin.setStyleSheet(interval_spin.styleSheet())

        history = SettingItem(
            "Keep history for",
            "How long to keep job history",
            history_spin
        )
        self.add_setting(history)


# ═══════════════════════════════════════════════════════════════════════════════
# ABOUT SECTION
# ═══════════════════════════════════════════════════════════════════════════════

class AboutSection(SettingsSection):
    """About section"""

    def __init__(self, parent=None):
        super().__init__("About", parent)

        colors = FluentDesignSystem().colors

        # App info card
        info_card = FluentCard()
        info_layout = QVBoxLayout()
        info_layout.setSpacing(16)
        info_layout.setAlignment(Qt.AlignCenter)

        # Logo
        logo = QLabel("\uE90F")  # Constellation icon
        logo.setStyleSheet(f"""
            font-family: 'Segoe Fluent Icons';
            font-size: 64px;
            color: {colors.accent};
        """)
        logo.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(logo)

        # Name
        name = QLabel("NebulaCompute Desktop")
        name.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 24px;
            font-weight: 600;
        """)
        name.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(name)

        # Version
        version = QLabel("Version 0.1.0")
        version.setStyleSheet(f"color: {colors.text_secondary}; font-size: 14px;")
        version.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(version)

        # Description
        desc = QLabel("A modern desktop interface for managing distributed computing clusters")
        desc.setStyleSheet(f"color: {colors.text_secondary}; font-size: 13px;")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(desc)

        info_widget = QWidget()
        info_widget.setLayout(info_layout)
        info_card.add_content(info_widget)
        self.add_setting(info_card)

        # Links
        links_layout = QHBoxLayout()
        links_layout.setSpacing(12)

        website_btn = FluentButton("Website", "", ButtonVariant.SUBTLE)
        links_layout.addWidget(website_btn)

        github_btn = FluentButton("GitHub", "", ButtonVariant.SUBTLE)
        links_layout.addWidget(github_btn)

        docs_btn = FluentButton("Documentation", "", ButtonVariant.SUBTLE)
        links_layout.addWidget(docs_btn)

        links_layout.addStretch()

        links_widget = QWidget()
        links_widget.setLayout(links_layout)
        self.add_setting(links_widget)

        # Check for updates
        update_btn = FluentButton("Check for Updates", "", ButtonVariant.ACCENT)
        self.add_setting(update_btn)


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT SETTINGS VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class FluentSettingsView(QWidget):
    """
    Complete settings view with navigation.
    صفحة الإعدادات الكاملة مع التنقل
    """

    connection_requested = Signal(str, str)
    settings_changed = Signal(dict)

    SECTIONS = [
        ("Connection", FluentIcons.CONNECT),
        ("Appearance", "\uE790"),  # Paintbrush
        ("Notifications", "\uE7E7"),  # Bell
        ("Data", "\uE8A5"),  # Storage
        ("About", FluentIcons.INFO),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self):
        """Setup view UI"""
        colors = FluentDesignSystem().colors

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Navigation list
        nav_frame = QFrame()
        nav_frame.setFixedWidth(250)
        nav_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {colors.bg_mica_alt};
                border-right: 1px solid {colors.stroke_divider};
            }}
        """)

        nav_layout = QVBoxLayout(nav_frame)
        nav_layout.setContentsMargins(12, 24, 12, 24)
        nav_layout.setSpacing(4)

        # Title
        title = QLabel("Settings")
        title.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 28px;
            font-weight: 600;
            padding: 0 8px 16px 8px;
        """)
        nav_layout.addWidget(title)

        # Nav items
        self._nav_list = QListWidget()
        self._nav_list.setFrameShape(QFrame.NoFrame)
        self._nav_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 12px 16px;
                border-radius: 8px;
                color: {colors.text_secondary};
            }}
            QListWidget::item:hover {{
                background-color: {colors.fill_subtle};
                color: {colors.text_primary};
            }}
            QListWidget::item:selected {{
                background-color: {colors.fill_subtle_secondary};
                color: {colors.text_primary};
            }}
        """)

        for section_name, icon in self.SECTIONS:
            item = QListWidgetItem(f"  {icon}   {section_name}")
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint()))
            self._nav_list.addItem(item)

        self._nav_list.currentRowChanged.connect(self._on_section_changed)
        nav_layout.addWidget(self._nav_list)
        nav_layout.addStretch()

        layout.addWidget(nav_frame)

        # Content area
        content_scroll = QScrollArea()
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.NoFrame)
        content_scroll.setStyleSheet(f"background-color: {colors.bg_mica_base};")

        self._content_stack = QStackedWidget()
        self._content_stack.setStyleSheet("background: transparent;")

        # Add sections
        connection = ConnectionSettings()
        connection.connection_requested.connect(self.connection_requested.emit)
        self._content_stack.addWidget(connection)

        appearance = AppearanceSettings()
        self._content_stack.addWidget(appearance)

        notifications = NotificationSettings()
        self._content_stack.addWidget(notifications)

        data = DataSettings()
        self._content_stack.addWidget(data)

        about = AboutSection()
        self._content_stack.addWidget(about)

        # Wrap in scroll
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(32, 24, 32, 24)
        scroll_layout.addWidget(self._content_stack)

        content_scroll.setWidget(scroll_widget)
        layout.addWidget(content_scroll, 1)

        # Select first section
        self._nav_list.setCurrentRow(0)

    def _on_section_changed(self, index: int):
        """Handle section navigation"""
        self._content_stack.setCurrentIndex(index)
