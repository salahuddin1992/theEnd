"""
Windows 11 Fluent Sidebar / Navigation View
شريط جانبي بتصميم Windows 11

Features:
- Animated expand/collapse
- Fluent reveal effect on hover
- Active indicator with animation
- Icon and text support
- Grouped navigation items
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Callable, Dict

from PySide6.QtCore import (
    Qt, Signal, QSize, QPropertyAnimation, QEasingCurve,
    QPoint, QRect, QTimer, Property, QEvent, QParallelAnimationGroup
)
from PySide6.QtGui import (
    QColor, QPainter, QFont, QIcon, QPainterPath,
    QLinearGradient, QRadialGradient, QCursor, QPen, QBrush
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSpacerItem, QSizePolicy,
    QGraphicsOpacityEffect
)

from .fluent_design import FluentDesignSystem, FluentColors, RevealEffect
from .animations import FluentEasing, FadeAnimation, SlideAnimation
from .titlebar import FluentIcons


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR ITEM DATA
# بيانات عنصر الشريط الجانبي
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SidebarItem:
    """Data for a sidebar navigation item"""
    id: str
    label: str
    icon: str = ""  # Fluent Icon unicode or path
    badge: Optional[str] = None
    tooltip: str = ""
    enabled: bool = True
    visible: bool = True


@dataclass
class SidebarGroup:
    """Group of sidebar items"""
    label: str
    items: List[SidebarItem] = field(default_factory=list)
    collapsed: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# NAVIGATION ITEM WIDGET
# عنصر التنقل
# ═══════════════════════════════════════════════════════════════════════════════

class NavItem(QWidget):
    """
    Single navigation item with Fluent Design styling.
    عنصر تنقل واحد بتصميم Fluent
    """

    clicked = Signal(str)  # Emits item_id

    def __init__(self, item: SidebarItem, expanded: bool = True, parent=None):
        super().__init__(parent)

        self._item = item
        self._expanded = expanded
        self._active = False
        self._hovered = False
        self._pressed = False
        self._indicator_width = 0

        self._setup_ui()
        self._setup_animations()

        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setEnabled(item.enabled)

    def _setup_ui(self):
        """Setup item UI"""
        self.setFixedHeight(40)
        self.setMinimumWidth(48)

        # Layout
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 0, 12, 0)
        self._layout.setSpacing(12)

        # Icon
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(20, 20)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._update_icon()
        self._layout.addWidget(self._icon_label)

        # Text
        self._text_label = QLabel(self._item.label)
        self._text_label.setVisible(self._expanded)
        self._layout.addWidget(self._text_label, 1)

        # Badge
        self._badge_label = QLabel()
        self._badge_label.setVisible(bool(self._item.badge) and self._expanded)
        self._update_badge()
        self._layout.addWidget(self._badge_label)

        # Tooltip
        if self._item.tooltip:
            self.setToolTip(self._item.tooltip)
        elif not self._expanded:
            self.setToolTip(self._item.label)

    def _setup_animations(self):
        """Setup animations"""
        # Active indicator animation
        self._indicator_anim = QPropertyAnimation(self, b"indicator_width")
        self._indicator_anim.setDuration(FluentEasing.DURATION_FAST)
        self._indicator_anim.setEasingCurve(FluentEasing.ease_out_cubic())

    def _get_indicator_width(self) -> int:
        return self._indicator_width

    def _set_indicator_width(self, value: int):
        self._indicator_width = value
        self.update()

    indicator_width = Property(int, _get_indicator_width, _set_indicator_width)

    def _update_icon(self):
        """Update icon display"""
        colors = FluentDesignSystem().colors

        # Set icon as text (Fluent Icons font)
        self._icon_label.setStyleSheet(f"""
            QLabel {{
                font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets';
                font-size: 16px;
                color: {colors.text_primary if self._active else colors.text_secondary};
            }}
        """)
        self._icon_label.setText(self._item.icon)

    def _update_badge(self):
        """Update badge display"""
        if not self._item.badge:
            return

        colors = FluentDesignSystem().colors
        self._badge_label.setText(self._item.badge)
        self._badge_label.setStyleSheet(f"""
            QLabel {{
                background-color: {colors.accent};
                color: #FFFFFF;
                font-size: 10px;
                font-weight: 600;
                padding: 2px 6px;
                border-radius: 8px;
                min-width: 16px;
            }}
        """)

    def set_active(self, active: bool):
        """Set active state"""
        if self._active == active:
            return

        self._active = active
        self._update_icon()
        self._update_style()

        # Animate indicator
        self._indicator_anim.stop()
        self._indicator_anim.setStartValue(self._indicator_width)
        self._indicator_anim.setEndValue(16 if active else 0)
        self._indicator_anim.start()

    def set_expanded(self, expanded: bool):
        """Set expanded state"""
        self._expanded = expanded
        self._text_label.setVisible(expanded)
        self._badge_label.setVisible(bool(self._item.badge) and expanded)

        if not expanded:
            self.setToolTip(self._item.label)
        else:
            self.setToolTip(self._item.tooltip or "")

    def _update_style(self):
        """Update widget style based on state"""
        colors = FluentDesignSystem().colors

        if self._pressed:
            bg = colors.fill_control_tertiary
        elif self._hovered:
            bg = colors.fill_subtle
        elif self._active:
            bg = colors.fill_subtle_secondary
        else:
            bg = "transparent"

        text_color = colors.text_primary if self._active else colors.text_secondary

        self._text_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                font-size: 14px;
                font-weight: {'600' if self._active else '400'};
            }}
        """)

        self.setStyleSheet(f"""
            NavItem {{
                background-color: {bg};
                border-radius: 8px;
            }}
        """)

    def paintEvent(self, event):
        """Custom paint for active indicator"""
        super().paintEvent(event)

        if self._indicator_width <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = FluentDesignSystem().colors

        # Draw active indicator pill on left side
        indicator_rect = QRect(
            4,
            (self.height() - self._indicator_width) // 2,
            3,
            self._indicator_width
        )

        painter.setBrush(QColor(colors.accent))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(indicator_rect, 1.5, 1.5)

        painter.end()

    def enterEvent(self, event):
        self._hovered = True
        self._update_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._update_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._update_style()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = False
            self._update_style()
            if self.rect().contains(event.pos()):
                self.clicked.emit(self._item.id)
        super().mouseReleaseEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR HEADER
# رأس الشريط الجانبي
# ═══════════════════════════════════════════════════════════════════════════════

class SidebarHeader(QWidget):
    """
    Sidebar header with logo and toggle button.
    رأس الشريط الجانبي مع الشعار وزر التوسيع
    """

    toggle_clicked = Signal()

    def __init__(self, title: str = "NebulaCompute", parent=None):
        super().__init__(parent)

        self._title = title
        self._expanded = True

        self._setup_ui()

    def _setup_ui(self):
        """Setup header UI"""
        colors = FluentDesignSystem().colors

        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 8, 12)
        layout.setSpacing(12)

        # Logo/Icon
        self._logo_label = QLabel()
        self._logo_label.setFixedSize(24, 24)
        self._logo_label.setStyleSheet(f"""
            QLabel {{
                font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets';
                font-size: 18px;
                color: {colors.accent};
            }}
        """)
        self._logo_label.setText("\uE90F")  # Constellation icon
        layout.addWidget(self._logo_label)

        # Title
        self._title_label = QLabel(self._title)
        self._title_label.setStyleSheet(f"""
            QLabel {{
                color: {colors.text_primary};
                font-size: 14px;
                font-weight: 600;
            }}
        """)
        layout.addWidget(self._title_label, 1)

        # Toggle button
        self._toggle_btn = QPushButton()
        self._toggle_btn.setFixedSize(32, 32)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.clicked.connect(self.toggle_clicked.emit)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 6px;
                font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets';
                font-size: 12px;
                color: {colors.text_secondary};
            }}
            QPushButton:hover {{
                background-color: {colors.fill_subtle};
            }}
        """)
        self._toggle_btn.setText("\uE700")  # Hamburger menu
        layout.addWidget(self._toggle_btn)

    def set_expanded(self, expanded: bool):
        """Update header for expanded/collapsed state"""
        self._expanded = expanded
        self._title_label.setVisible(expanded)

        if expanded:
            self._toggle_btn.setText("\uE700")  # Hamburger
        else:
            self._toggle_btn.setText("\uE76C")  # Forward arrow


# ═══════════════════════════════════════════════════════════════════════════════
# CONNECTION STATUS WIDGET
# حالة الاتصال
# ═══════════════════════════════════════════════════════════════════════════════

class ConnectionStatus(QWidget):
    """
    Connection status indicator.
    مؤشر حالة الاتصال
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._connected = False
        self._server_name = ""
        self._expanded = True

        self._setup_ui()

    def _setup_ui(self):
        """Setup status UI"""
        colors = FluentDesignSystem().colors

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        # Status dot
        self._status_dot = QLabel()
        self._status_dot.setFixedSize(8, 8)
        self._update_status_dot()
        layout.addWidget(self._status_dot)

        # Status text
        self._status_text = QLabel("Disconnected")
        self._status_text.setStyleSheet(f"""
            QLabel {{
                color: {colors.text_secondary};
                font-size: 12px;
            }}
        """)
        layout.addWidget(self._status_text, 1)

    def _update_status_dot(self):
        """Update status indicator color"""
        colors = FluentDesignSystem().colors
        color = colors.status_running if self._connected else colors.text_disabled

        self._status_dot.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 4px;
            }}
        """)

    def set_connected(self, connected: bool, server_name: str = ""):
        """Update connection status"""
        self._connected = connected
        self._server_name = server_name

        self._update_status_dot()

        if connected:
            self._status_text.setText(server_name or "Connected")
        else:
            self._status_text.setText("Disconnected")

    def set_expanded(self, expanded: bool):
        """Update for expanded/collapsed state"""
        self._expanded = expanded
        self._status_text.setVisible(expanded)


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT SIDEBAR
# الشريط الجانبي بتصميم Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentSidebar(QWidget):
    """
    Windows 11 style navigation sidebar.
    شريط تنقل جانبي بنمط Windows 11
    """

    page_changed = Signal(str)
    expanded_changed = Signal(bool)

    # Default navigation items
    DEFAULT_ITEMS = [
        SidebarItem("dashboard", "Dashboard", FluentIcons.DASHBOARD),
        SidebarItem("jobs", "Jobs", FluentIcons.JOBS),
        SidebarItem("workers", "Workers", FluentIcons.WORKERS),
        SidebarItem("templates", "Templates", FluentIcons.TEMPLATES),
        SidebarItem("pools", "Pools", FluentIcons.POOLS),
        SidebarItem("queues", "Queues", FluentIcons.QUEUES),
        SidebarItem("logs", "Logs", FluentIcons.LOGS),
        SidebarItem("metrics", "Metrics", FluentIcons.METRICS),
    ]

    FOOTER_ITEMS = [
        SidebarItem("settings", "Settings", FluentIcons.SETTINGS),
    ]

    def __init__(self, items: List[SidebarItem] = None, parent=None):
        super().__init__(parent)

        self._items = items or self.DEFAULT_ITEMS
        self._nav_widgets: Dict[str, NavItem] = {}
        self._active_id = "dashboard"
        self._expanded = True
        self._collapsed_width = 48
        self._expanded_width = 280

        self._setup_ui()
        self._setup_animations()
        self.set_active_page("dashboard")

    def _setup_ui(self):
        """Setup sidebar UI"""
        colors = FluentDesignSystem().colors

        self.setObjectName("fluent_sidebar")
        self.setFixedWidth(self._expanded_width)
        self.setMinimumHeight(400)

        self.setStyleSheet(f"""
            #fluent_sidebar {{
                background-color: {colors.bg_mica_alt};
                border-right: 1px solid {colors.stroke_divider};
            }}
        """)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        self._header = SidebarHeader("NebulaCompute")
        self._header.toggle_clicked.connect(self.toggle_expanded)
        main_layout.addWidget(self._header)

        # Scroll area for navigation items
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        # Navigation container
        nav_container = QWidget()
        self._nav_layout = QVBoxLayout(nav_container)
        self._nav_layout.setContentsMargins(8, 8, 8, 8)
        self._nav_layout.setSpacing(4)

        # Add navigation items
        for item in self._items:
            nav_widget = NavItem(item, self._expanded)
            nav_widget.clicked.connect(self._on_item_clicked)
            self._nav_widgets[item.id] = nav_widget
            self._nav_layout.addWidget(nav_widget)

        self._nav_layout.addStretch()

        scroll.setWidget(nav_container)
        main_layout.addWidget(scroll, 1)

        # Divider
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {colors.stroke_divider};")
        main_layout.addWidget(divider)

        # Footer items (settings, etc.)
        footer_container = QWidget()
        footer_layout = QVBoxLayout(footer_container)
        footer_layout.setContentsMargins(8, 8, 8, 8)
        footer_layout.setSpacing(4)

        for item in self.FOOTER_ITEMS:
            nav_widget = NavItem(item, self._expanded)
            nav_widget.clicked.connect(self._on_item_clicked)
            self._nav_widgets[item.id] = nav_widget
            footer_layout.addWidget(nav_widget)

        main_layout.addWidget(footer_container)

        # Connection status
        self._connection_status = ConnectionStatus()
        main_layout.addWidget(self._connection_status)

    def _setup_animations(self):
        """Setup animations"""
        self._width_anim = QPropertyAnimation(self, b"minimumWidth")
        self._width_anim.setDuration(FluentEasing.DURATION_NORMAL)
        self._width_anim.setEasingCurve(FluentEasing.ease_out_cubic())

        self._max_width_anim = QPropertyAnimation(self, b"maximumWidth")
        self._max_width_anim.setDuration(FluentEasing.DURATION_NORMAL)
        self._max_width_anim.setEasingCurve(FluentEasing.ease_out_cubic())

    def _on_item_clicked(self, item_id: str):
        """Handle navigation item click"""
        self.set_active_page(item_id)
        self.page_changed.emit(item_id)

    def set_active_page(self, page_id: str):
        """Set the active navigation item"""
        # Deactivate previous
        if self._active_id in self._nav_widgets:
            self._nav_widgets[self._active_id].set_active(False)

        # Activate new
        self._active_id = page_id
        if page_id in self._nav_widgets:
            self._nav_widgets[page_id].set_active(True)

    def toggle_expanded(self):
        """Toggle sidebar expanded/collapsed state"""
        self._expanded = not self._expanded
        self._animate_expand()
        self.expanded_changed.emit(self._expanded)

    def _animate_expand(self):
        """Animate expand/collapse"""
        target_width = self._expanded_width if self._expanded else self._collapsed_width

        # Animate both min and max width
        self._width_anim.stop()
        self._width_anim.setStartValue(self.width())
        self._width_anim.setEndValue(target_width)

        self._max_width_anim.stop()
        self._max_width_anim.setStartValue(self.width())
        self._max_width_anim.setEndValue(target_width)

        # Create parallel animation group
        group = QParallelAnimationGroup(self)
        group.addAnimation(self._width_anim)
        group.addAnimation(self._max_width_anim)
        group.start()

        # Update child widgets
        self._header.set_expanded(self._expanded)
        self._connection_status.set_expanded(self._expanded)

        for nav_widget in self._nav_widgets.values():
            nav_widget.set_expanded(self._expanded)

    def set_connection_status(self, connected: bool, server_name: str = ""):
        """Update connection status indicator"""
        self._connection_status.set_connected(connected, server_name)

    def set_badge(self, item_id: str, badge: str):
        """Set badge on a navigation item"""
        if item_id in self._nav_widgets:
            # Would need to update the nav widget's badge
            pass

    def add_item(self, item: SidebarItem, index: int = -1):
        """Add a new navigation item"""
        nav_widget = NavItem(item, self._expanded)
        nav_widget.clicked.connect(self._on_item_clicked)
        self._nav_widgets[item.id] = nav_widget

        if index < 0:
            self._nav_layout.insertWidget(self._nav_layout.count() - 1, nav_widget)
        else:
            self._nav_layout.insertWidget(index, nav_widget)

    def remove_item(self, item_id: str):
        """Remove a navigation item"""
        if item_id in self._nav_widgets:
            widget = self._nav_widgets.pop(item_id)
            widget.setParent(None)
            widget.deleteLater()
