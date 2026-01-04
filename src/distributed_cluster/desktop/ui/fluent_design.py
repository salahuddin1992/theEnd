"""
Windows 11 Fluent Design System
نظام تصميم Fluent لـ Windows 11

Implements:
- Mica Effect (translucent background)
- Acrylic Effect (blur + noise)
- Reveal Effect (lighting on hover)
- Fluent color system
- Typography system
- Spacing system
- Elevation system
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

# Try to import Windows-specific modules
try:
    if platform.system() == "Windows":
        import ctypes  # noqa: F401
        from ctypes import wintypes  # noqa: F401
        HAS_WIN32 = True
    else:
        HAS_WIN32 = False
except ImportError:
    HAS_WIN32 = False


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT COLOR SYSTEM
# نظام ألوان Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentAccentColor(Enum):
    """Windows 11 accent colors"""
    DEFAULT = "#0078D4"      # Windows Blue
    PURPLE = "#744DA9"
    RED = "#E81123"
    ORANGE = "#FF8C00"
    YELLOW = "#FFB900"
    GREEN = "#107C10"
    TEAL = "#00B294"
    CYAN = "#0099BC"


@dataclass
class FluentColors:
    """
    Complete Fluent Design color palette.
    لوحة ألوان Fluent الكاملة
    """
    # Accent colors
    accent: str = "#0078D4"
    accent_light_1: str = "#429CE3"
    accent_light_2: str = "#7BC0EE"
    accent_light_3: str = "#B4DAF7"
    accent_dark_1: str = "#005A9E"
    accent_dark_2: str = "#004578"
    accent_dark_3: str = "#002D4D"

    # Text colors (Dark theme)
    text_primary: str = "#FFFFFF"
    text_secondary: str = "#C5C5C5"
    text_tertiary: str = "#9E9E9E"
    text_disabled: str = "#5C5C5C"

    # Background colors (Dark theme)
    bg_solid_base: str = "#202020"
    bg_solid_secondary: str = "#2D2D2D"
    bg_solid_tertiary: str = "#383838"
    bg_solid_quaternary: str = "#444444"

    # Mica backgrounds
    bg_mica_base: str = "#1C1C1C"
    bg_mica_alt: str = "#282828"

    # Acrylic backgrounds
    bg_acrylic: str = "rgba(32, 32, 32, 0.7)"
    bg_acrylic_thin: str = "rgba(32, 32, 32, 0.5)"

    # Card backgrounds
    bg_card_default: str = "rgba(255, 255, 255, 0.05)"
    bg_card_secondary: str = "rgba(255, 255, 255, 0.03)"

    # Stroke/Border colors
    stroke_control: str = "rgba(255, 255, 255, 0.08)"
    stroke_control_strong: str = "rgba(255, 255, 255, 0.55)"
    stroke_surface: str = "rgba(255, 255, 255, 0.07)"
    stroke_divider: str = "rgba(255, 255, 255, 0.08)"
    stroke_focus: str = "#FFFFFF"

    # Fill colors
    fill_control: str = "rgba(255, 255, 255, 0.06)"
    fill_control_secondary: str = "rgba(255, 255, 255, 0.08)"
    fill_control_tertiary: str = "rgba(255, 255, 255, 0.03)"
    fill_control_disabled: str = "rgba(255, 255, 255, 0.02)"
    fill_subtle: str = "rgba(255, 255, 255, 0.04)"
    fill_subtle_secondary: str = "rgba(255, 255, 255, 0.06)"

    # System colors
    success: str = "#6CCB5F"
    warning: str = "#FCE100"
    error: str = "#FF99A4"
    info: str = "#60CDFF"

    # Semantic status
    status_running: str = "#6CCB5F"
    status_pending: str = "#FCE100"
    status_failed: str = "#FF99A4"
    status_completed: str = "#60CDFF"
    status_idle: str = "#9E9E9E"

    @classmethod
    def light_theme(cls) -> "FluentColors":
        """Get light theme colors"""
        return cls(
            text_primary="#1A1A1A",
            text_secondary="#5C5C5C",
            text_tertiary="#8C8C8C",
            text_disabled="#BABABA",
            bg_solid_base="#F3F3F3",
            bg_solid_secondary="#EEEEEE",
            bg_solid_tertiary="#E8E8E8",
            bg_solid_quaternary="#E0E0E0",
            bg_mica_base="#F9F9F9",
            bg_mica_alt="#E8E8E8",
            bg_acrylic="rgba(243, 243, 243, 0.7)",
            bg_acrylic_thin="rgba(243, 243, 243, 0.5)",
            bg_card_default="rgba(255, 255, 255, 0.7)",
            bg_card_secondary="rgba(255, 255, 255, 0.5)",
            stroke_control="rgba(0, 0, 0, 0.06)",
            stroke_control_strong="rgba(0, 0, 0, 0.45)",
            stroke_surface="rgba(0, 0, 0, 0.05)",
            stroke_divider="rgba(0, 0, 0, 0.08)",
            stroke_focus="#000000",
            fill_control="rgba(255, 255, 255, 0.7)",
            fill_control_secondary="rgba(249, 249, 249, 0.5)",
            fill_control_tertiary="rgba(249, 249, 249, 0.3)",
            fill_control_disabled="rgba(249, 249, 249, 0.3)",
            fill_subtle="rgba(0, 0, 0, 0.04)",
            fill_subtle_secondary="rgba(0, 0, 0, 0.03)",
            success="#0F7B0F",
            warning="#9D5D00",
            error="#C42B1C",
            info="#0067C0",
            status_running="#0F7B0F",
            status_pending="#9D5D00",
            status_failed="#C42B1C",
            status_completed="#0067C0",
            status_idle="#8C8C8C",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TYPOGRAPHY SYSTEM
# نظام الخطوط
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FluentTypography:
    """Fluent Design typography specifications"""

    # Font families
    font_family: str = "Segoe UI Variable"
    font_family_display: str = "Segoe UI Variable Display"
    font_family_text: str = "Segoe UI Variable Text"
    font_family_mono: str = "Cascadia Code"
    font_family_icon: str = "Segoe Fluent Icons"

    # Display styles
    display: Tuple[int, int] = (68, 92)    # size, line-height
    title_large: Tuple[int, int] = (40, 52)
    title: Tuple[int, int] = (28, 36)
    subtitle: Tuple[int, int] = (20, 28)

    # Body styles
    body_large: Tuple[int, int] = (18, 24)
    body: Tuple[int, int] = (14, 20)
    body_strong: Tuple[int, int] = (14, 20)

    # Caption styles
    caption: Tuple[int, int] = (12, 16)
    caption_strong: Tuple[int, int] = (12, 16)

    @staticmethod
    def get_font(style: str = "body", weight: int = 400) -> QFont:
        """Get a configured QFont for the specified style"""
        typography = FluentTypography()

        sizes = {
            "display": typography.display,
            "title_large": typography.title_large,
            "title": typography.title,
            "subtitle": typography.subtitle,
            "body_large": typography.body_large,
            "body": typography.body,
            "body_strong": typography.body_strong,
            "caption": typography.caption,
            "caption_strong": typography.caption_strong,
        }

        size, _ = sizes.get(style, typography.body)

        font = QFont(typography.font_family, size)
        font.setWeight(weight)

        if style.endswith("_strong"):
            font.setWeight(QFont.Weight.DemiBold)

        return font


# ═══════════════════════════════════════════════════════════════════════════════
# SPACING & ELEVATION SYSTEM
# نظام المسافات والارتفاعات
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FluentSpacing:
    """Fluent Design spacing tokens"""
    xxs: int = 2
    xs: int = 4
    s: int = 8
    m: int = 12
    large: int = 16
    xl: int = 20
    xxl: int = 24
    xxxl: int = 32


@dataclass
class FluentCorners:
    """Fluent Design corner radius tokens"""
    none: int = 0
    small: int = 4
    medium: int = 8
    large: int = 12
    extra_large: int = 16
    circular: int = 9999


class FluentElevation:
    """Shadow/elevation definitions for depth"""

    @staticmethod
    def get_shadow(level: int) -> QGraphicsDropShadowEffect:
        """Get drop shadow effect for elevation level (1-4)"""
        effect = QGraphicsDropShadowEffect()
        effect.setColor(QColor(0, 0, 0, 100))

        if level == 1:
            effect.setBlurRadius(2)
            effect.setOffset(0, 1)
        elif level == 2:
            effect.setBlurRadius(4)
            effect.setOffset(0, 2)
        elif level == 3:
            effect.setBlurRadius(8)
            effect.setOffset(0, 4)
        elif level == 4:
            effect.setBlurRadius(16)
            effect.setOffset(0, 8)
        else:
            effect.setBlurRadius(32)
            effect.setOffset(0, 16)

        return effect


# ═══════════════════════════════════════════════════════════════════════════════
# MICA EFFECT
# تأثير Mica
# ═══════════════════════════════════════════════════════════════════════════════

class MicaEffect(QObject):
    """
    Windows 11 Mica material effect.
    تأثير Mica من Windows 11

    Mica creates a translucent background that samples colors
    from the desktop wallpaper.
    """

    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_MICA_EFFECT = 1029
    DWMWA_SYSTEMBACKDROP_TYPE = 38

    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self._enabled = False

    def apply(self, mica_alt: bool = False) -> bool:
        """
        Apply Mica effect to window.
        تطبيق تأثير Mica على النافذة
        """
        if not HAS_WIN32:
            # Fallback: use gradient background
            self._apply_fallback()
            return False

        try:
            hwnd = int(self._window.winId())

            # Enable dark mode
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                self.DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value)
            )

            # Set backdrop type (2 = Mica, 3 = Mica Alt, 4 = Acrylic)
            backdrop_type = 3 if mica_alt else 2
            value = ctypes.c_int(backdrop_type)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                self.DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(value),
                ctypes.sizeof(value)
            )

            self._enabled = True
            return True

        except Exception as e:
            print(f"Mica effect not available: {e}")
            self._apply_fallback()
            return False

    def _apply_fallback(self):
        """Apply fallback gradient when Mica not available"""
        self._window.setStyleSheet("""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #1a1a2e,
                stop:0.5 #16213e,
                stop:1 #0f3460
            );
        """)


# ═══════════════════════════════════════════════════════════════════════════════
# ACRYLIC EFFECT
# تأثير Acrylic
# ═══════════════════════════════════════════════════════════════════════════════

class AcrylicEffect(QWidget):
    """
    Windows 11 Acrylic blur effect.
    تأثير Acrylic (الضبابية) من Windows 11
    """

    def __init__(self, parent: QWidget = None,
                 tint_color: QColor = None,
                 tint_opacity: float = 0.7,
                 blur_amount: int = 30,
                 noise_opacity: float = 0.02):
        super().__init__(parent)

        self._tint_color = tint_color or QColor(32, 32, 32)
        self._tint_opacity = tint_opacity
        self._blur_amount = blur_amount
        self._noise_opacity = noise_opacity

        self.setAttribute(Qt.WA_TranslucentBackground)
        self._noise_texture = self._generate_noise()

    def _generate_noise(self) -> QPixmap:
        """Generate noise texture for acrylic effect"""
        size = 128
        image = QImage(size, size, QImage.Format_ARGB32)

        import random
        for x in range(size):
            for y in range(size):
                noise = random.randint(0, 255)
                alpha = int(255 * self._noise_opacity)
                image.setPixelColor(x, y, QColor(noise, noise, noise, alpha))

        return QPixmap.fromImage(image)

    def paintEvent(self, event):
        """Paint acrylic effect"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw tint color with opacity
        tint = QColor(self._tint_color)
        tint.setAlphaF(self._tint_opacity)
        painter.fillRect(self.rect(), tint)

        # Draw noise texture (tiled)
        painter.setOpacity(self._noise_opacity)
        for x in range(0, self.width(), self._noise_texture.width()):
            for y in range(0, self.height(), self._noise_texture.height()):
                painter.drawPixmap(x, y, self._noise_texture)

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════════
# REVEAL EFFECT
# تأثير Reveal (الإضاءة)
# ═══════════════════════════════════════════════════════════════════════════════

class RevealEffect(QObject):
    """
    Windows Fluent Design Reveal highlight effect.
    تأثير Reveal (الإضاءة عند التمرير)

    Creates a lighting effect that follows the mouse cursor.
    """

    def __init__(self, widget: QWidget,
                 border_radius: int = 8,
                 light_color: QColor = None,
                 border_light_color: QColor = None):
        super().__init__(widget)

        self._widget = widget
        self._border_radius = border_radius
        self._light_color = light_color or QColor(255, 255, 255, 30)
        self._border_light_color = border_light_color or QColor(255, 255, 255, 80)

        self._mouse_pos = QPoint()
        self._is_hovered = False
        self._animation_progress = 0.0

        # Install event filter
        widget.installEventFilter(self)
        widget.setMouseTracking(True)

        # Animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_animation)
        self._timer.setInterval(16)  # ~60fps

    def eventFilter(self, obj, event):
        if obj == self._widget:
            if event.type() == QEvent.Enter:
                self._is_hovered = True
                self._timer.start()
            elif event.type() == QEvent.Leave:
                self._is_hovered = False
                self._timer.start()
            elif event.type() == QEvent.MouseMove:
                self._mouse_pos = event.pos()
                self._widget.update()

        return super().eventFilter(obj, event)

    def _update_animation(self):
        """Update reveal animation"""
        if self._is_hovered and self._animation_progress < 1.0:
            self._animation_progress = min(1.0, self._animation_progress + 0.1)
            self._widget.update()
        elif not self._is_hovered and self._animation_progress > 0.0:
            self._animation_progress = max(0.0, self._animation_progress - 0.1)
            self._widget.update()
        else:
            self._timer.stop()

    def paint(self, painter: QPainter, rect: QRect):
        """Paint the reveal effect"""
        if self._animation_progress <= 0:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # Create radial gradient from mouse position
        gradient = QRadialGradient(self._mouse_pos, 150)

        # Light color with animation
        light = QColor(self._light_color)
        light.setAlpha(int(self._light_color.alpha() * self._animation_progress))

        gradient.setColorAt(0, light)
        gradient.setColorAt(1, QColor(0, 0, 0, 0))

        # Draw reveal gradient
        path = QPainterPath()
        path.addRoundedRect(rect, self._border_radius, self._border_radius)
        painter.fillPath(path, gradient)

        # Draw border light effect
        if self._is_hovered:
            border_gradient = QRadialGradient(self._mouse_pos, 200)
            border_light = QColor(self._border_light_color)
            border_light.setAlpha(int(border_light.alpha() * self._animation_progress))

            border_gradient.setColorAt(0, border_light)
            border_gradient.setColorAt(0.5, QColor(255, 255, 255, 20))
            border_gradient.setColorAt(1, QColor(0, 0, 0, 0))

            pen = QPen(QBrush(border_gradient), 1)
            painter.setPen(pen)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1),
                                   self._border_radius - 1,
                                   self._border_radius - 1)

        painter.restore()


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT THEME & DESIGN SYSTEM
# نظام السمات والتصميم
# ═══════════════════════════════════════════════════════════════════════════════

class FluentTheme(Enum):
    """Available themes"""
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"


class FluentDesignSystem(QObject):
    """
    Main Fluent Design System manager.
    مدير نظام تصميم Fluent الرئيسي

    Provides unified access to:
    - Colors
    - Typography
    - Spacing
    - Effects
    - Stylesheet generation
    """

    theme_changed = Signal(FluentTheme)
    accent_changed = Signal(str)

    _instance: Optional["FluentDesignSystem"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        super().__init__()
        self._initialized = True

        self._theme = FluentTheme.DARK
        self._colors = FluentColors()
        self._typography = FluentTypography()
        self._spacing = FluentSpacing()
        self._corners = FluentCorners()
        self._accent_color = "#0078D4"
        self._listeners: List[Callable] = []

    @property
    def colors(self) -> FluentColors:
        return self._colors

    @property
    def typography(self) -> FluentTypography:
        return self._typography

    @property
    def spacing(self) -> FluentSpacing:
        return self._spacing

    @property
    def corners(self) -> FluentCorners:
        return self._corners

    @property
    def theme(self) -> FluentTheme:
        return self._theme

    @property
    def accent(self) -> str:
        return self._accent_color

    def set_theme(self, theme: FluentTheme):
        """Set application theme"""
        self._theme = theme

        if theme == FluentTheme.LIGHT:
            self._colors = FluentColors.light_theme()
        else:
            self._colors = FluentColors()

        self.theme_changed.emit(theme)
        self._notify_listeners()

    def set_accent(self, color: str):
        """Set accent color"""
        self._accent_color = color
        self._colors.accent = color
        self.accent_changed.emit(color)
        self._notify_listeners()

    def add_listener(self, callback: Callable):
        """Add theme change listener"""
        self._listeners.append(callback)

    def _notify_listeners(self):
        """Notify all listeners of changes"""
        for listener in self._listeners:
            listener()

    def generate_stylesheet(self) -> str:
        """
        Generate complete Qt stylesheet for Fluent Design.
        توليد stylesheet كامل لتصميم Fluent
        """
        c = self._colors
        s = self._spacing
        r = self._corners

        return f"""
/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT DESIGN SYSTEM - WINDOWS 11 STYLE
   نظام تصميم Fluent - نمط Windows 11
   ═══════════════════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════════════════
   GLOBAL STYLES
   ═══════════════════════════════════════════════════════════════════════════ */

* {{
    font-family: 'Segoe UI Variable', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 14px;
    outline: none;
}}

QMainWindow, QWidget {{
    background-color: {c.bg_mica_base};
    color: {c.text_primary};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT BUTTONS
   ═══════════════════════════════════════════════════════════════════════════ */

QPushButton {{
    background-color: {c.fill_control};
    color: {c.text_primary};
    border: 1px solid {c.stroke_control};
    border-radius: {r.medium}px;
    padding: {s.s}px {s.large}px;
    font-weight: 400;
    min-height: 32px;
}}

QPushButton:hover {{
    background-color: {c.fill_control_secondary};
    border-color: {c.stroke_control};
}}

QPushButton:pressed {{
    background-color: {c.fill_control_tertiary};
    color: {c.text_secondary};
}}

QPushButton:disabled {{
    background-color: {c.fill_control_disabled};
    color: {c.text_disabled};
    border-color: transparent;
}}

/* Accent Button */
QPushButton#accent_button, QPushButton[accent="true"] {{
    background-color: {c.accent};
    color: #FFFFFF;
    border: 1px solid transparent;
}}

QPushButton#accent_button:hover, QPushButton[accent="true"]:hover {{
    background-color: {c.accent_light_1};
}}

QPushButton#accent_button:pressed, QPushButton[accent="true"]:pressed {{
    background-color: {c.accent_dark_1};
    color: rgba(255, 255, 255, 0.7);
}}

/* Subtle Button */
QPushButton#subtle_button, QPushButton[subtle="true"] {{
    background-color: transparent;
    border: none;
}}

QPushButton#subtle_button:hover, QPushButton[subtle="true"]:hover {{
    background-color: {c.fill_subtle};
}}

/* Icon Button */
QPushButton#icon_button {{
    background-color: transparent;
    border: none;
    border-radius: {r.medium}px;
    padding: {s.s}px;
    min-width: 36px;
    min-height: 36px;
    max-width: 36px;
    max-height: 36px;
}}

QPushButton#icon_button:hover {{
    background-color: {c.fill_subtle};
}}

/* Danger Button */
QPushButton#danger_button {{
    background-color: {c.error};
    color: #000000;
    border: none;
}}

/* Success Button */
QPushButton#success_button {{
    background-color: {c.success};
    color: #000000;
    border: none;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT CARDS
   ═══════════════════════════════════════════════════════════════════════════ */

QFrame#fluent_card {{
    background-color: {c.bg_card_default};
    border: 1px solid {c.stroke_surface};
    border-radius: {r.large}px;
    padding: {s.large}px;
}}

QFrame#fluent_card:hover {{
    background-color: {c.bg_card_secondary};
    border-color: {c.stroke_control};
}}

/* Elevated Card */
QFrame#fluent_card_elevated {{
    background-color: {c.bg_solid_secondary};
    border: 1px solid {c.stroke_surface};
    border-radius: {r.large}px;
    padding: {s.large}px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT INPUTS
   ═══════════════════════════════════════════════════════════════════════════ */

QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {c.fill_control};
    color: {c.text_primary};
    border: 1px solid {c.stroke_control};
    border-bottom: 2px solid {c.stroke_control_strong};
    border-radius: {r.medium}px;
    padding: {s.s}px {s.m}px;
    selection-background-color: {c.accent};
    selection-color: #FFFFFF;
}}

QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {{
    background-color: {c.fill_control_secondary};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    background-color: {c.fill_control_secondary};
    border-bottom-color: {c.accent};
}}

QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
    background-color: {c.fill_control_disabled};
    color: {c.text_disabled};
    border-color: transparent;
}}

QLineEdit[hasError="true"] {{
    border-bottom-color: {c.error};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT COMBOBOX
   ═══════════════════════════════════════════════════════════════════════════ */

QComboBox {{
    background-color: {c.fill_control};
    color: {c.text_primary};
    border: 1px solid {c.stroke_control};
    border-radius: {r.medium}px;
    padding: {s.s}px {s.m}px;
    min-height: 32px;
}}

QComboBox:hover {{
    background-color: {c.fill_control_secondary};
}}

QComboBox:focus {{
    border-color: {c.accent};
}}

QComboBox::drop-down {{
    border: none;
    width: 32px;
}}

QComboBox::down-arrow {{
    image: none;
    width: 12px;
    height: 12px;
}}

QComboBox QAbstractItemView {{
    background-color: {c.bg_solid_secondary};
    border: 1px solid {c.stroke_surface};
    border-radius: {r.medium}px;
    padding: {s.xs}px;
    selection-background-color: {c.fill_subtle};
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    padding: {s.s}px {s.m}px;
    border-radius: {r.small}px;
    min-height: 32px;
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: {c.fill_subtle};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT SIDEBAR / NAVIGATION
   ═══════════════════════════════════════════════════════════════════════════ */

QWidget#fluent_sidebar {{
    background-color: {c.bg_mica_alt};
    border-right: 1px solid {c.stroke_divider};
}}

QWidget#nav_item {{
    background-color: transparent;
    border: none;
    border-radius: {r.medium}px;
    padding: {s.m}px {s.large}px;
    text-align: left;
    min-height: 40px;
}}

QWidget#nav_item:hover {{
    background-color: {c.fill_subtle};
}}

QWidget#nav_item[active="true"] {{
    background-color: {c.fill_subtle_secondary};
}}

QWidget#nav_item[active="true"]::before {{
    content: "";
    position: absolute;
    left: 0;
    top: 25%;
    height: 50%;
    width: 3px;
    background-color: {c.accent};
    border-radius: 2px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT TABLES
   ═══════════════════════════════════════════════════════════════════════════ */

QTableWidget, QTableView {{
    background-color: transparent;
    border: none;
    gridline-color: {c.stroke_divider};
    selection-background-color: {c.fill_subtle};
    alternate-background-color: {c.bg_card_secondary};
}}

QTableWidget::item, QTableView::item {{
    padding: {s.s}px {s.m}px;
    border: none;
    border-bottom: 1px solid {c.stroke_divider};
}}

QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {c.fill_subtle_secondary};
    color: {c.text_primary};
}}

QTableWidget::item:hover, QTableView::item:hover {{
    background-color: {c.fill_subtle};
}}

QHeaderView::section {{
    background-color: transparent;
    color: {c.text_secondary};
    padding: {s.m}px;
    border: none;
    border-bottom: 1px solid {c.stroke_divider};
    font-weight: 600;
    font-size: 12px;
}}

QHeaderView::section:hover {{
    background-color: {c.fill_subtle};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT SCROLLBARS
   ═══════════════════════════════════════════════════════════════════════════ */

QScrollBar:vertical {{
    background-color: transparent;
    width: 14px;
    margin: 0;
}}

QScrollBar:horizontal {{
    background-color: transparent;
    height: 14px;
    margin: 0;
}}

QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background-color: {c.stroke_control};
    border-radius: 3px;
    margin: 4px;
    min-height: 40px;
    min-width: 40px;
}}

QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background-color: {c.stroke_control_strong};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}

QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT TABS
   ═══════════════════════════════════════════════════════════════════════════ */

QTabWidget::pane {{
    background-color: {c.bg_card_default};
    border: 1px solid {c.stroke_surface};
    border-radius: {r.large}px;
    margin-top: -1px;
}}

QTabBar {{
    background: transparent;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {c.text_secondary};
    padding: {s.m}px {s.xl}px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: {s.xs}px;
}}

QTabBar::tab:hover {{
    color: {c.text_primary};
    background-color: {c.fill_subtle};
}}

QTabBar::tab:selected {{
    color: {c.text_primary};
    border-bottom-color: {c.accent};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT PROGRESS INDICATORS
   ═══════════════════════════════════════════════════════════════════════════ */

QProgressBar {{
    background-color: {c.stroke_control};
    border: none;
    border-radius: 2px;
    height: 4px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {c.accent};
    border-radius: 2px;
}}

/* Indeterminate style via animation would need custom widget */

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT CHECKBOXES & RADIO BUTTONS
   ═══════════════════════════════════════════════════════════════════════════ */

QCheckBox {{
    spacing: {s.s}px;
    color: {c.text_primary};
}}

QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border-radius: {r.small}px;
    border: 2px solid {c.stroke_control_strong};
    background-color: transparent;
}}

QCheckBox::indicator:hover {{
    background-color: {c.fill_subtle};
}}

QCheckBox::indicator:checked {{
    background-color: {c.accent};
    border-color: {c.accent};
}}

QCheckBox::indicator:checked:hover {{
    background-color: {c.accent_light_1};
    border-color: {c.accent_light_1};
}}

QRadioButton {{
    spacing: {s.s}px;
    color: {c.text_primary};
}}

QRadioButton::indicator {{
    width: 20px;
    height: 20px;
    border-radius: 10px;
    border: 2px solid {c.stroke_control_strong};
    background-color: transparent;
}}

QRadioButton::indicator:checked {{
    background-color: {c.accent};
    border-color: {c.accent};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT SLIDERS
   ═══════════════════════════════════════════════════════════════════════════ */

QSlider::groove:horizontal {{
    background-color: {c.stroke_control};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {c.accent};
    border: 4px solid {c.bg_solid_base};
    width: 20px;
    height: 20px;
    margin: -8px 0;
    border-radius: 10px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {c.accent_light_1};
}}

QSlider::sub-page:horizontal {{
    background-color: {c.accent};
    border-radius: 2px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT TOOLTIPS
   ═══════════════════════════════════════════════════════════════════════════ */

QToolTip {{
    background-color: {c.bg_solid_tertiary};
    color: {c.text_primary};
    border: 1px solid {c.stroke_surface};
    border-radius: {r.medium}px;
    padding: {s.s}px {s.m}px;
    font-size: 12px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT MENUS
   ═══════════════════════════════════════════════════════════════════════════ */

QMenu {{
    background-color: {c.bg_solid_secondary};
    border: 1px solid {c.stroke_surface};
    border-radius: {r.large}px;
    padding: {s.xs}px;
}}

QMenu::item {{
    padding: {s.s}px {s.xl}px {s.s}px {s.large}px;
    border-radius: {r.medium}px;
    min-height: 32px;
}}

QMenu::item:selected {{
    background-color: {c.fill_subtle};
}}

QMenu::separator {{
    height: 1px;
    background-color: {c.stroke_divider};
    margin: {s.xs}px {s.s}px;
}}

QMenuBar {{
    background-color: transparent;
    color: {c.text_primary};
    padding: {s.xs}px;
}}

QMenuBar::item {{
    padding: {s.s}px {s.m}px;
    border-radius: {r.medium}px;
}}

QMenuBar::item:selected {{
    background-color: {c.fill_subtle};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT DIALOGS
   ═══════════════════════════════════════════════════════════════════════════ */

QDialog {{
    background-color: {c.bg_mica_base};
}}

QMessageBox {{
    background-color: {c.bg_mica_base};
}}

QMessageBox QLabel {{
    color: {c.text_primary};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT GROUPBOX
   ═══════════════════════════════════════════════════════════════════════════ */

QGroupBox {{
    background-color: {c.bg_card_default};
    border: 1px solid {c.stroke_surface};
    border-radius: {r.large}px;
    margin-top: 24px;
    padding: {s.large}px;
    padding-top: {s.xl}px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: {s.large}px;
    top: 0;
    padding: 0 {s.s}px;
    color: {c.text_primary};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT STATUS BAR
   ═══════════════════════════════════════════════════════════════════════════ */

QStatusBar {{
    background-color: transparent;
    color: {c.text_secondary};
    border-top: 1px solid {c.stroke_divider};
    padding: {s.xs}px {s.m}px;
    font-size: 12px;
}}

QStatusBar::item {{
    border: none;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   FLUENT SPLITTER
   ═══════════════════════════════════════════════════════════════════════════ */

QSplitter::handle {{
    background-color: {c.stroke_divider};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}

QSplitter::handle:hover {{
    background-color: {c.accent};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   STATUS BADGES
   ═══════════════════════════════════════════════════════════════════════════ */

QLabel#status_running {{
    color: {c.status_running};
    font-weight: 600;
}}

QLabel#status_pending {{
    color: {c.status_pending};
    font-weight: 600;
}}

QLabel#status_failed {{
    color: {c.status_failed};
    font-weight: 600;
}}

QLabel#status_completed {{
    color: {c.status_completed};
    font-weight: 600;
}}

QLabel#status_idle {{
    color: {c.status_idle};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   CUSTOM TITLE BAR
   ═══════════════════════════════════════════════════════════════════════════ */

QWidget#custom_titlebar {{
    background-color: transparent;
    min-height: 32px;
    max-height: 32px;
}}

QWidget#titlebar_button {{
    background-color: transparent;
    border: none;
    border-radius: 0;
    min-width: 46px;
    min-height: 32px;
}}

QWidget#titlebar_button:hover {{
    background-color: {c.fill_subtle};
}}

QWidget#close_button:hover {{
    background-color: #C42B1C;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   NOTIFICATION TOAST
   ═══════════════════════════════════════════════════════════════════════════ */

QFrame#toast {{
    background-color: {c.bg_solid_secondary};
    border: 1px solid {c.stroke_surface};
    border-radius: {r.large}px;
    padding: {s.large}px;
}}

QFrame#toast_success {{
    border-left: 3px solid {c.success};
}}

QFrame#toast_error {{
    border-left: 3px solid {c.error};
}}

QFrame#toast_warning {{
    border-left: 3px solid {c.warning};
}}

QFrame#toast_info {{
    border-left: 3px solid {c.info};
}}
"""


# Global design system instance
fluent = FluentDesignSystem()
