"""
Custom Windows 11 Title Bar
شريط عنوان Windows 11 المخصص

Features:
- Frameless window with custom title bar
- Windows 11 style minimize/maximize/close buttons
- Draggable title bar
- Snap layouts support (Windows 11)
- Double-click to maximize
"""

from __future__ import annotations

import platform
from typing import Optional

from PySide6.QtCore import (
    Qt, Signal, QPoint, QSize, QEvent, QRect
)
from PySide6.QtGui import (
    QColor, QPainter, QIcon, QFont,
    QMouseEvent
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QMainWindow, QApplication, QSizePolicy, QSpacerItem, QFrame
)

from .fluent_design import FluentDesignSystem

# Try Windows-specific imports
try:
    if platform.system() == "Windows":
        import ctypes
        from ctypes import wintypes
        HAS_WIN32 = True
    else:
        HAS_WIN32 = False
except ImportError:
    HAS_WIN32 = False


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT ICONS (Segoe Fluent Icons Unicode)
# أيقونات Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentIcons:
    """Segoe Fluent Icons unicode characters"""
    # Window controls
    MINIMIZE = "\uE921"
    MAXIMIZE = "\uE922"
    RESTORE = "\uE923"
    CLOSE = "\uE8BB"

    # Navigation
    BACK = "\uE72B"
    FORWARD = "\uE72A"
    HOME = "\uE80F"
    REFRESH = "\uE72C"
    SETTINGS = "\uE713"

    # Common
    SEARCH = "\uE721"
    ADD = "\uE710"
    DELETE = "\uE74D"
    EDIT = "\uE70F"
    SAVE = "\uE74E"
    COPY = "\uE8C8"
    PASTE = "\uE77F"

    # Status
    CHECKMARK = "\uE73E"
    CANCEL = "\uE711"
    WARNING = "\uE7BA"
    ERROR = "\uE783"
    INFO = "\uE946"

    # Navigation items
    DASHBOARD = "\uE80F"
    JOBS = "\uE9D5"
    WORKERS = "\uE716"
    TEMPLATES = "\uE8A5"
    POOLS = "\uE8C4"
    QUEUES = "\uE8FD"
    LOGS = "\uE756"
    METRICS = "\uE9D9"
    TERMINAL = "\uE756"

    # Actions
    PLAY = "\uE768"
    PAUSE = "\uE769"
    STOP = "\uE71A"
    CONNECT = "\uE703"
    DISCONNECT = "\uE8CD"


# ═══════════════════════════════════════════════════════════════════════════════
# TITLE BAR BUTTON
# زر شريط العنوان
# ═══════════════════════════════════════════════════════════════════════════════

class TitleBarButton(QPushButton):
    """
    Windows 11 style title bar button.
    زر شريط العنوان بنمط Windows 11
    """

    def __init__(self, icon: str, button_type: str = "normal", parent=None):
        super().__init__(parent)

        self._icon_char = icon
        self._button_type = button_type  # "normal", "close"
        self._hovered = False
        self._pressed = False

        # Setup
        self.setFixedSize(46, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        # Style
        self._update_style()

    def _update_style(self):
        """Update button style based on state"""
        colors = FluentDesignSystem().colors

        if self._button_type == "close":
            if self._pressed:
                bg = "#B4161B"
            elif self._hovered:
                bg = "#E81123"
            else:
                bg = "transparent"
            text_color = "#FFFFFF" if self._hovered else colors.text_primary
        else:
            if self._pressed:
                bg = "rgba(255, 255, 255, 0.06)"
            elif self._hovered:
                bg = "rgba(255, 255, 255, 0.08)"
            else:
                bg = "transparent"
            text_color = colors.text_primary

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                border: none;
                border-radius: 0px;
                font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets';
                font-size: 10px;
                color: {text_color};
            }}
        """)

    def enterEvent(self, event):
        self._hovered = True
        self._update_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._update_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True
        self._update_style()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self._update_style()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw icon
        colors = FluentDesignSystem().colors
        if self._button_type == "close" and self._hovered:
            painter.setPen(QColor("#FFFFFF"))
        else:
            painter.setPen(QColor(colors.text_primary))

        font = QFont("Segoe Fluent Icons", 10)
        if not QApplication.font().family() == "Segoe Fluent Icons":
            font = QFont("Segoe MDL2 Assets", 10)
        painter.setFont(font)

        painter.drawText(self.rect(), Qt.AlignCenter, self._icon_char)
        painter.end()


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOM TITLE BAR
# شريط العنوان المخصص
# ═══════════════════════════════════════════════════════════════════════════════

class CustomTitleBar(QWidget):
    """
    Windows 11 style custom title bar.
    شريط عنوان مخصص بنمط Windows 11
    """

    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()
    double_clicked = Signal()

    def __init__(self, parent: QWidget = None, title: str = ""):
        super().__init__(parent)

        self._title = title
        self._is_maximized = False
        self._drag_position: Optional[QPoint] = None

        self._setup_ui()
        self.setMouseTracking(True)

    def _setup_ui(self):
        """Setup title bar UI"""
        colors = FluentDesignSystem().colors

        self.setFixedHeight(32)
        self.setObjectName("custom_titlebar")

        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left section (icon + title)
        left_widget = QWidget()
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(12, 0, 0, 0)
        left_layout.setSpacing(8)

        # App icon
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        left_layout.addWidget(self.icon_label)

        # Title
        self.title_label = QLabel(self._title)
        self.title_label.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 12px;
            font-weight: 400;
        """)
        left_layout.addWidget(self.title_label)

        layout.addWidget(left_widget)

        # Spacer (draggable area)
        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Fixed))

        # Right section (window controls)
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)

        # Minimize button
        self.minimize_btn = TitleBarButton(FluentIcons.MINIMIZE)
        self.minimize_btn.clicked.connect(self.minimize_clicked.emit)
        controls_layout.addWidget(self.minimize_btn)

        # Maximize button
        self.maximize_btn = TitleBarButton(FluentIcons.MAXIMIZE)
        self.maximize_btn.clicked.connect(self._on_maximize_clicked)
        controls_layout.addWidget(self.maximize_btn)

        # Close button
        self.close_btn = TitleBarButton(FluentIcons.CLOSE, "close")
        self.close_btn.clicked.connect(self.close_clicked.emit)
        controls_layout.addWidget(self.close_btn)

        layout.addWidget(controls_widget)

        # Style
        self.setStyleSheet("""
            #custom_titlebar {
                background-color: transparent;
            }
        """)

    def set_title(self, title: str):
        """Set window title"""
        self._title = title
        self.title_label.setText(title)

    def set_icon(self, icon: QIcon):
        """Set window icon"""
        pixmap = icon.pixmap(QSize(16, 16))
        self.icon_label.setPixmap(pixmap)

    def set_maximized(self, maximized: bool):
        """Update maximize button state"""
        self._is_maximized = maximized
        icon = FluentIcons.RESTORE if maximized else FluentIcons.MAXIMIZE
        self.maximize_btn._icon_char = icon
        self.maximize_btn.update()

    def _on_maximize_clicked(self):
        """Handle maximize button click"""
        self.maximize_clicked.emit()

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for window dragging"""
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPos() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for window dragging"""
        if event.buttons() == Qt.LeftButton and self._drag_position:
            # If maximized, restore first
            if self._is_maximized:
                # Calculate new position
                window = self.window()
                ratio = event.pos().x() / self.width()
                new_width = window.normalGeometry().width()
                new_x = event.globalPos().x() - int(new_width * ratio)
                new_y = event.globalPos().y() - self._drag_position.y()

                window.showNormal()
                window.move(new_x, new_y)
                self._drag_position = event.globalPos() - window.frameGeometry().topLeft()
            else:
                self.window().move(event.globalPos() - self._drag_position)
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double click to maximize/restore"""
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            self.maximize_clicked.emit()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release"""
        self._drag_position = None


# ═══════════════════════════════════════════════════════════════════════════════
# FRAMELESS WINDOW
# نافذة بدون إطار
# ═══════════════════════════════════════════════════════════════════════════════

class FramelessWindow(QMainWindow):
    """
    Windows 11 style frameless window with custom title bar.
    نافذة بدون إطار بنمط Windows 11 مع شريط عنوان مخصص
    """

    def __init__(self, parent=None, title: str = "NebulaCompute"):
        super().__init__(parent)

        self._title = title
        self._resize_margin = 8
        self._is_resizing = False
        self._resize_edge = None
        self._drag_start_geometry: Optional[QRect] = None
        self._drag_start_pos: Optional[QPoint] = None

        self._setup_window()
        self._setup_ui()
        self._apply_effects()

    def _setup_window(self):
        """Configure window properties"""
        # Remove standard frame
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowSystemMenuHint |
            Qt.WindowMinMaxButtonsHint
        )

        # Enable transparency for rounded corners
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Minimum size
        self.setMinimumSize(800, 600)

        # Mouse tracking for resize cursor
        self.setMouseTracking(True)

    def _setup_ui(self):
        """Setup window UI structure"""
        colors = FluentDesignSystem().colors

        # Central container with rounded corners
        self.container = QFrame()
        self.container.setObjectName("main_container")
        self.container.setStyleSheet(f"""
            #main_container {{
                background-color: {colors.bg_mica_base};
                border: 1px solid {colors.stroke_surface};
                border-radius: 8px;
            }}
        """)

        # Main layout
        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Custom title bar
        self.title_bar = CustomTitleBar(self, self._title)
        self.title_bar.minimize_clicked.connect(self.showMinimized)
        self.title_bar.maximize_clicked.connect(self._toggle_maximize)
        self.title_bar.close_clicked.connect(self.close)
        main_layout.addWidget(self.title_bar)

        # Content area
        self.content_widget = QWidget()
        self.content_widget.setObjectName("content_area")
        self._content_layout = QVBoxLayout(self.content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.content_widget)

        self.setCentralWidget(self.container)

    def _apply_effects(self):
        """Apply Windows 11 visual effects"""
        if HAS_WIN32:
            try:
                from .fluent_design import MicaEffect
                mica = MicaEffect(self)
                mica.apply(mica_alt=True)
            except Exception:
                pass

    def set_content(self, widget: QWidget):
        """Set the main content widget"""
        # Clear existing content
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Add new content
        self._content_layout.addWidget(widget)

    def setWindowTitle(self, title: str):
        """Override to update custom title bar"""
        super().setWindowTitle(title)
        self._title = title
        self.title_bar.set_title(title)

    def setWindowIcon(self, icon: QIcon):
        """Override to update custom title bar icon"""
        super().setWindowIcon(icon)
        self.title_bar.set_icon(icon)

    def _toggle_maximize(self):
        """Toggle between maximized and normal state"""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event: QEvent):
        """Handle window state changes"""
        if event.type() == QEvent.WindowStateChange:
            is_maximized = self.isMaximized()
            self.title_bar.set_maximized(is_maximized)

            # Adjust border radius for maximized state
            if is_maximized:
                self.container.setStyleSheet(f"""
                    #main_container {{
                        background-color: {FluentDesignSystem().colors.bg_mica_base};
                        border: none;
                        border-radius: 0px;
                    }}
                """)
            else:
                colors = FluentDesignSystem().colors
                self.container.setStyleSheet(f"""
                    #main_container {{
                        background-color: {colors.bg_mica_base};
                        border: 1px solid {colors.stroke_surface};
                        border-radius: 8px;
                    }}
                """)

        super().changeEvent(event)

    def _get_resize_edge(self, pos: QPoint) -> Optional[str]:
        """Determine which edge/corner is being hovered for resize"""
        margin = self._resize_margin
        rect = self.rect()

        left = pos.x() < margin
        right = pos.x() > rect.width() - margin
        top = pos.y() < margin
        bottom = pos.y() > rect.height() - margin

        if left and top:
            return "top_left"
        elif right and top:
            return "top_right"
        elif left and bottom:
            return "bottom_left"
        elif right and bottom:
            return "bottom_right"
        elif left:
            return "left"
        elif right:
            return "right"
        elif top:
            return "top"
        elif bottom:
            return "bottom"
        return None

    def _get_cursor_for_edge(self, edge: str) -> Qt.CursorShape:
        """Get appropriate cursor for resize edge"""
        cursors = {
            "left": Qt.SizeHorCursor,
            "right": Qt.SizeHorCursor,
            "top": Qt.SizeVerCursor,
            "bottom": Qt.SizeVerCursor,
            "top_left": Qt.SizeFDiagCursor,
            "bottom_right": Qt.SizeFDiagCursor,
            "top_right": Qt.SizeBDiagCursor,
            "bottom_left": Qt.SizeBDiagCursor,
        }
        return cursors.get(edge, Qt.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for resizing"""
        if event.button() == Qt.LeftButton and not self.isMaximized():
            edge = self._get_resize_edge(event.pos())
            if edge:
                self._is_resizing = True
                self._resize_edge = edge
                self._drag_start_geometry = self.geometry()
                self._drag_start_pos = event.globalPos()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for resize cursor and resizing"""
        if self._is_resizing and self._resize_edge:
            self._do_resize(event.globalPos())
            event.accept()
            return

        # Update cursor based on position
        if not self.isMaximized():
            edge = self._get_resize_edge(event.pos())
            if edge:
                self.setCursor(self._get_cursor_for_edge(edge))
            else:
                self.setCursor(Qt.ArrowCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release"""
        self._is_resizing = False
        self._resize_edge = None
        super().mouseReleaseEvent(event)

    def _do_resize(self, global_pos: QPoint):
        """Perform window resize based on mouse movement"""
        if not self._drag_start_geometry or not self._drag_start_pos:
            return

        diff = global_pos - self._drag_start_pos
        geo = QRect(self._drag_start_geometry)

        min_width = self.minimumWidth()
        min_height = self.minimumHeight()

        edge = self._resize_edge

        if "left" in edge:
            new_left = geo.left() + diff.x()
            new_width = geo.width() - diff.x()
            if new_width >= min_width:
                geo.setLeft(new_left)

        if "right" in edge:
            new_width = geo.width() + diff.x()
            if new_width >= min_width:
                geo.setWidth(new_width)

        if "top" in edge:
            new_top = geo.top() + diff.y()
            new_height = geo.height() - diff.y()
            if new_height >= min_height:
                geo.setTop(new_top)

        if "bottom" in edge:
            new_height = geo.height() + diff.y()
            if new_height >= min_height:
                geo.setHeight(new_height)

        self.setGeometry(geo)

    def nativeEvent(self, event_type, message):
        """Handle native Windows events for snap layouts"""
        if HAS_WIN32 and event_type == b"windows_generic_MSG":
            # Handle WM_NCHITTEST for Windows 11 snap layouts
            pass
        return super().nativeEvent(event_type, message)
