"""
Advanced Fluent Design Components
مكونات Fluent Design المتقدمة

Includes:
- FluentButton (with reveal effect)
- FluentCard (with elevation)
- FluentInput (with validation)
- FluentSwitch (toggle)
- FluentSlider
- FluentProgressRing
- FluentBadge
- FluentAvatar
- FluentTooltip
- SkeletonLoader
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import (
    Qt, Signal, QSize, QTimer, QPropertyAnimation,
    Property, QRect, QRectF
)
from PySide6.QtGui import (
    QColor, QPainter, QFont, QPainterPath, QPen, QLinearGradient, QPixmap, QFontMetrics
)
from PySide6.QtWidgets import (
    QWidget, QPushButton, QFrame, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect,
    QSlider, QAbstractButton
)

from .fluent_design import FluentDesignSystem, RevealEffect
from .animations import FluentEasing


# ═══════════════════════════════════════════════════════════════════════════════
# BUTTON VARIANTS
# ═══════════════════════════════════════════════════════════════════════════════

class ButtonVariant(Enum):
    """Button style variants"""
    DEFAULT = "default"
    ACCENT = "accent"
    SUBTLE = "subtle"
    OUTLINE = "outline"
    DANGER = "danger"
    SUCCESS = "success"


class ButtonSize(Enum):
    """Button size variants"""
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT BUTTON
# زر Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentButton(QPushButton):
    """
    Modern Fluent Design button with reveal effect.
    زر حديث بتصميم Fluent مع تأثير Reveal
    """

    def __init__(self, text: str = "", icon: str = "",
                 variant: ButtonVariant = ButtonVariant.DEFAULT,
                 size: ButtonSize = ButtonSize.MEDIUM,
                 parent=None):
        super().__init__(text, parent)

        self._icon_char = icon
        self._variant = variant
        self._size = size
        self._hovered = False
        self._pressed = False
        self._loading = False
        self._loading_angle = 0

        self._setup_ui()
        self._setup_reveal()
        self._setup_loading()

    def _setup_ui(self):
        """Setup button UI"""
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        # Size configuration
        sizes = {
            ButtonSize.SMALL: (28, 8, 12, 12),
            ButtonSize.MEDIUM: (36, 12, 16, 14),
            ButtonSize.LARGE: (44, 16, 24, 16),
        }
        height, padding_v, padding_h, font_size = sizes[self._size]

        self.setMinimumHeight(height)
        self.setContentsMargins(padding_h, padding_v, padding_h, padding_v)

        self._update_style()

    def _setup_reveal(self):
        """Setup reveal effect"""
        self._reveal = RevealEffect(self, border_radius=6)

    def _setup_loading(self):
        """Setup loading animation"""
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._update_loading)
        self._loading_timer.setInterval(16)

    def _update_loading(self):
        """Update loading spinner angle"""
        self._loading_angle = (self._loading_angle + 6) % 360
        self.update()

    def set_loading(self, loading: bool):
        """Set loading state"""
        self._loading = loading
        self.setEnabled(not loading)

        if loading:
            self._loading_timer.start()
        else:
            self._loading_timer.stop()

        self.update()

    def _update_style(self):
        """Update button style based on variant and state"""
        colors = FluentDesignSystem().colors

        # Get colors based on variant
        if self._variant == ButtonVariant.ACCENT:
            if self._pressed:
                bg = colors.accent_dark_1
                text = "rgba(255, 255, 255, 0.8)"
            elif self._hovered:
                bg = colors.accent_light_1
                text = "#FFFFFF"
            else:
                bg = colors.accent
                text = "#FFFFFF"
            border = "transparent"

        elif self._variant == ButtonVariant.SUBTLE:
            if self._pressed:
                bg = colors.fill_subtle_secondary
            elif self._hovered:
                bg = colors.fill_subtle
            else:
                bg = "transparent"
            text = colors.text_primary
            border = "transparent"

        elif self._variant == ButtonVariant.OUTLINE:
            if self._pressed:
                bg = colors.fill_control_tertiary
            elif self._hovered:
                bg = colors.fill_control_secondary
            else:
                bg = "transparent"
            text = colors.text_primary
            border = colors.stroke_control_strong

        elif self._variant == ButtonVariant.DANGER:
            if self._pressed:
                bg = "#A41E1E"
            elif self._hovered:
                bg = "#D32F2F"
            else:
                bg = colors.error
            text = "#000000"
            border = "transparent"

        elif self._variant == ButtonVariant.SUCCESS:
            if self._pressed:
                bg = "#1B5E20"
            elif self._hovered:
                bg = "#388E3C"
            else:
                bg = colors.success
            text = "#000000"
            border = "transparent"

        else:  # DEFAULT
            if self._pressed:
                bg = colors.fill_control_tertiary
                text = colors.text_secondary
            elif self._hovered:
                bg = colors.fill_control_secondary
                text = colors.text_primary
            else:
                bg = colors.fill_control
                text = colors.text_primary
            border = colors.stroke_control

        # Font size based on size
        font_sizes = {
            ButtonSize.SMALL: 12,
            ButtonSize.MEDIUM: 14,
            ButtonSize.LARGE: 16,
        }

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 6px;
                font-size: {font_sizes[self._size]}px;
                font-weight: 500;
                padding: 0px 16px;
            }}
        """)

    def paintEvent(self, event):
        """Custom paint with icon and loading state"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw reveal effect
        self._reveal.paint(painter, self.rect())

        # Draw loading spinner
        if self._loading:
            self._draw_loading_spinner(painter)

        # Draw icon if present
        elif self._icon_char:
            self._draw_icon(painter)

        painter.end()

    def _draw_icon(self, painter: QPainter):
        """Draw Fluent icon"""
        colors = FluentDesignSystem().colors

        font = QFont("Segoe Fluent Icons", 14)
        painter.setFont(font)

        if self._variant in [ButtonVariant.ACCENT, ButtonVariant.DANGER, ButtonVariant.SUCCESS]:
            if self._variant == ButtonVariant.ACCENT:
                painter.setPen(QColor("#FFFFFF"))
            else:
                painter.setPen(QColor("#000000"))
        else:
            painter.setPen(QColor(colors.text_primary))

        # Draw icon on left side
        icon_rect = QRect(12, 0, 20, self.height())
        painter.drawText(icon_rect, Qt.AlignVCenter | Qt.AlignLeft, self._icon_char)

    def _draw_loading_spinner(self, painter: QPainter):
        """Draw loading spinner"""
        colors = FluentDesignSystem().colors

        center = self.rect().center()
        radius = 8

        # Draw arc
        pen = QPen(QColor(colors.text_primary))
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        rect = QRectF(
            center.x() - radius,
            center.y() - radius,
            radius * 2,
            radius * 2
        )

        painter.drawArc(rect, self._loading_angle * 16, 270 * 16)

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


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT CARD
# بطاقة Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentCard(QFrame):
    """
    Modern Fluent Design card with elevation.
    بطاقة حديثة بتصميم Fluent مع الارتفاع
    """

    clicked = Signal()

    def __init__(self, title: str = "", subtitle: str = "",
                 clickable: bool = False, elevated: bool = False,
                 parent=None):
        super().__init__(parent)

        self._title = title
        self._subtitle = subtitle
        self._clickable = clickable
        self._elevated = elevated
        self._hovered = False

        self._setup_ui()

        if clickable:
            self.setCursor(Qt.PointingHandCursor)
            self._reveal = RevealEffect(self, border_radius=12)

    def _setup_ui(self):
        """Setup card UI"""
        colors = FluentDesignSystem().colors

        self.setObjectName("fluent_card" if not self._elevated else "fluent_card_elevated")
        self.setMouseTracking(True)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Title
        if self._title:
            self._title_label = QLabel(self._title)
            self._title_label.setStyleSheet(f"""
                QLabel {{
                    color: {colors.text_primary};
                    font-size: 16px;
                    font-weight: 600;
                }}
            """)
            layout.addWidget(self._title_label)

        # Subtitle
        if self._subtitle:
            self._subtitle_label = QLabel(self._subtitle)
            self._subtitle_label.setStyleSheet(f"""
                QLabel {{
                    color: {colors.text_secondary};
                    font-size: 12px;
                }}
            """)
            layout.addWidget(self._subtitle_label)

        # Content area
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._content_widget)

        self._update_style()

        # Shadow for elevated cards
        if self._elevated:
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(16)
            shadow.setOffset(0, 4)
            shadow.setColor(QColor(0, 0, 0, 50))
            self.setGraphicsEffect(shadow)

    def set_content(self, widget: QWidget):
        """Set card content widget"""
        # Clear existing
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        self._content_layout.addWidget(widget)

    def add_content(self, widget: QWidget):
        """Add widget to card content"""
        self._content_layout.addWidget(widget)

    def _update_style(self):
        """Update card style"""
        colors = FluentDesignSystem().colors

        if self._elevated:
            bg = colors.bg_solid_secondary
        else:
            if self._hovered and self._clickable:
                bg = colors.bg_card_secondary
            else:
                bg = colors.bg_card_default

        self.setStyleSheet(f"""
            #{self.objectName()} {{
                background-color: {bg};
                border: 1px solid {colors.stroke_surface};
                border-radius: 12px;
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
        if self._clickable and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)

        if self._clickable and hasattr(self, '_reveal'):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            self._reveal.paint(painter, self.rect())
            painter.end()


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT INPUT
# حقل إدخال Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentInput(QWidget):
    """
    Modern Fluent Design text input with label and validation.
    حقل إدخال نصي حديث بتصميم Fluent مع التسمية والتحقق
    """

    text_changed = Signal(str)
    return_pressed = Signal()

    def __init__(self, label: str = "", placeholder: str = "",
                 icon: str = "", parent=None):
        super().__init__(parent)

        self._label = label
        self._placeholder = placeholder
        self._icon = icon
        self._error_message = ""
        self._has_error = False

        self._setup_ui()

    def _setup_ui(self):
        """Setup input UI"""
        colors = FluentDesignSystem().colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Label
        if self._label:
            self._label_widget = QLabel(self._label)
            self._label_widget.setStyleSheet(f"""
                QLabel {{
                    color: {colors.text_primary};
                    font-size: 14px;
                    font-weight: 500;
                }}
            """)
            layout.addWidget(self._label_widget)

        # Input container
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(0)

        # Icon
        if self._icon:
            icon_label = QLabel()
            icon_label.setFixedWidth(40)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setStyleSheet(f"""
                QLabel {{
                    font-family: 'Segoe Fluent Icons';
                    font-size: 14px;
                    color: {colors.text_secondary};
                    background-color: {colors.fill_control};
                    border: 1px solid {colors.stroke_control};
                    border-right: none;
                    border-radius: 6px 0 0 6px;
                    padding: 8px;
                }}
            """)
            icon_label.setText(self._icon)
            input_layout.addWidget(icon_label)

        # Input field
        self._input = QLineEdit()
        self._input.setPlaceholderText(self._placeholder)
        self._input.textChanged.connect(self.text_changed.emit)
        self._input.returnPressed.connect(self.return_pressed.emit)
        input_layout.addWidget(self._input)

        layout.addWidget(input_container)

        # Error message
        self._error_label = QLabel()
        self._error_label.setStyleSheet(f"""
            QLabel {{
                color: {colors.error};
                font-size: 12px;
            }}
        """)
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        self._update_style()

    def _update_style(self):
        """Update input style"""
        colors = FluentDesignSystem().colors

        border_color = colors.error if self._has_error else colors.stroke_control
        border_bottom = colors.error if self._has_error else colors.stroke_control_strong

        has_icon_radius = "0" if self._icon else "6px"

        self._input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {border_color};
                border-bottom: 2px solid {border_bottom};
                border-radius: {has_icon_radius} 6px 6px {has_icon_radius};
                padding: 8px 12px;
                font-size: 14px;
                min-height: 20px;
            }}
            QLineEdit:hover {{
                background-color: {colors.fill_control_secondary};
            }}
            QLineEdit:focus {{
                border-bottom-color: {colors.accent};
            }}
            QLineEdit::placeholder {{
                color: {colors.text_tertiary};
            }}
        """)

    def text(self) -> str:
        """Get input text"""
        return self._input.text()

    def set_text(self, text: str):
        """Set input text"""
        self._input.setText(text)

    def set_error(self, error: str):
        """Set error message"""
        self._error_message = error
        self._has_error = bool(error)
        self._error_label.setText(error)
        self._error_label.setVisible(self._has_error)
        self._update_style()

    def clear_error(self):
        """Clear error state"""
        self.set_error("")

    def setFocus(self):
        """Set focus to input"""
        self._input.setFocus()


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT SWITCH (TOGGLE)
# مفتاح تبديل Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentSwitch(QAbstractButton):
    """
    Modern Fluent Design toggle switch.
    مفتاح تبديل حديث بتصميم Fluent
    """

    toggled_value = Signal(bool)

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)

        self._text = text
        self._thumb_position = 0.0

        self.setCheckable(True)
        self.setChecked(False)
        self.setFixedSize(120, 24)
        self.setCursor(Qt.PointingHandCursor)

        self._setup_animation()
        self.toggled.connect(self._on_toggled)

    def _setup_animation(self):
        """Setup toggle animation"""
        self._anim = QPropertyAnimation(self, b"thumb_position")
        self._anim.setDuration(FluentEasing.DURATION_FAST)
        self._anim.setEasingCurve(FluentEasing.ease_out_cubic())

    def _get_thumb_position(self) -> float:
        return self._thumb_position

    def _set_thumb_position(self, value: float):
        self._thumb_position = value
        self.update()

    thumb_position = Property(float, _get_thumb_position, _set_thumb_position)

    def _on_toggled(self, checked: bool):
        """Handle toggle state change"""
        self._anim.stop()
        self._anim.setStartValue(self._thumb_position)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()
        self.toggled_value.emit(checked)

    def paintEvent(self, event):
        """Custom paint"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = FluentDesignSystem().colors

        # Track dimensions
        track_width = 40
        track_height = 20
        thumb_size = 12

        # Draw track
        track_rect = QRectF(0, 2, track_width, track_height)

        if self.isChecked():
            track_color = QColor(colors.accent)
        else:
            track_color = QColor(colors.stroke_control_strong)

        painter.setBrush(track_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(track_rect, track_height / 2, track_height / 2)

        # Draw thumb
        thumb_x = 4 + (track_width - thumb_size - 8) * self._thumb_position
        thumb_rect = QRectF(thumb_x, 6, thumb_size, thumb_size)

        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(thumb_rect)

        # Draw text
        if self._text:
            painter.setPen(QColor(colors.text_primary))
            font = QFont("Segoe UI", 14)
            painter.setFont(font)

            text_rect = QRect(track_width + 8, 0, self.width() - track_width - 8, self.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self._text)

        painter.end()

    def sizeHint(self):
        if self._text:
            fm = QFontMetrics(QFont("Segoe UI", 14))
            text_width = fm.horizontalAdvance(self._text)
            return QSize(48 + text_width, 24)
        return QSize(40, 24)


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT SLIDER
# منزلق Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentSlider(QSlider):
    """
    Modern Fluent Design slider.
    منزلق حديث بتصميم Fluent
    """

    def __init__(self, orientation: Qt.Orientation = Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)

        self._setup_style()

    def _setup_style(self):
        """Setup slider style"""
        colors = FluentDesignSystem().colors

        self.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background-color: {colors.stroke_control};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background-color: {colors.accent};
                border: 4px solid {colors.bg_solid_base};
                width: 20px;
                height: 20px;
                margin: -8px 0;
                border-radius: 10px;
            }}
            QSlider::handle:horizontal:hover {{
                background-color: {colors.accent_light_1};
            }}
            QSlider::sub-page:horizontal {{
                background-color: {colors.accent};
                border-radius: 2px;
            }}
        """)


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT PROGRESS RING
# حلقة تقدم Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentProgressRing(QWidget):
    """
    Modern Fluent Design progress ring (circular progress).
    حلقة تقدم حديثة بتصميم Fluent
    """

    def __init__(self, size: int = 32, thickness: int = 3,
                 indeterminate: bool = False, parent=None):
        super().__init__(parent)

        self._size = size
        self._thickness = thickness
        self._indeterminate = indeterminate
        self._progress = 0.0
        self._angle = 0

        self.setFixedSize(size, size)

        if indeterminate:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._update_animation)
            self._timer.setInterval(16)
            self._timer.start()

    def _update_animation(self):
        """Update indeterminate animation"""
        self._angle = (self._angle + 5) % 360
        self.update()

    def set_progress(self, progress: float):
        """Set progress (0.0 to 1.0)"""
        self._progress = max(0.0, min(1.0, progress))
        self.update()

    def paintEvent(self, event):
        """Custom paint"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = FluentDesignSystem().colors

        # Calculate dimensions
        margin = self._thickness
        rect = QRectF(margin, margin,
                     self._size - 2 * margin,
                     self._size - 2 * margin)

        # Draw background track
        pen = QPen(QColor(colors.stroke_control))
        pen.setWidth(self._thickness)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(rect)

        # Draw progress arc
        pen.setColor(QColor(colors.accent))
        painter.setPen(pen)

        if self._indeterminate:
            # Indeterminate animation
            start_angle = self._angle * 16
            span_angle = 90 * 16
            painter.drawArc(rect, start_angle, span_angle)
        else:
            # Determinate progress
            start_angle = 90 * 16  # Start from top
            span_angle = int(-self._progress * 360 * 16)
            painter.drawArc(rect, start_angle, span_angle)

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT BADGE
# شارة Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class BadgeVariant(Enum):
    """Badge color variants"""
    DEFAULT = "default"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"


class FluentBadge(QLabel):
    """
    Modern Fluent Design badge/tag.
    شارة/علامة حديثة بتصميم Fluent
    """

    def __init__(self, text: str = "", variant: BadgeVariant = BadgeVariant.DEFAULT,
                 parent=None):
        super().__init__(text, parent)

        self._variant = variant
        self._setup_style()

    def _setup_style(self):
        """Setup badge style"""
        colors = FluentDesignSystem().colors

        variant_colors = {
            BadgeVariant.DEFAULT: (colors.fill_subtle, colors.text_primary),
            BadgeVariant.SUCCESS: (colors.success, "#000000"),
            BadgeVariant.WARNING: (colors.warning, "#000000"),
            BadgeVariant.ERROR: (colors.error, "#000000"),
            BadgeVariant.INFO: (colors.info, "#000000"),
        }

        bg, text = variant_colors[self._variant]

        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {text};
                font-size: 12px;
                font-weight: 500;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)

        self.setAlignment(Qt.AlignCenter)


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT AVATAR
# صورة رمزية Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentAvatar(QWidget):
    """
    Modern Fluent Design avatar/profile picture.
    صورة رمزية حديثة بتصميم Fluent
    """

    clicked = Signal()

    def __init__(self, name: str = "", image_path: str = "",
                 size: int = 40, parent=None):
        super().__init__(parent)

        self._name = name
        self._image_path = image_path
        self._size = size

        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        """Custom paint"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = FluentDesignSystem().colors

        # Circle clip
        path = QPainterPath()
        path.addEllipse(self.rect())
        painter.setClipPath(path)

        if self._image_path:
            # Draw image
            pixmap = QPixmap(self._image_path)
            scaled = pixmap.scaled(self._size, self._size,
                                  Qt.KeepAspectRatioByExpanding,
                                  Qt.SmoothTransformation)
            painter.drawPixmap(0, 0, scaled)
        else:
            # Draw initials
            painter.fillRect(self.rect(), QColor(colors.accent))

            initials = "".join([word[0].upper() for word in self._name.split()[:2]])
            if not initials and self._name:
                initials = self._name[0].upper()

            painter.setPen(QColor("#FFFFFF"))
            font = QFont("Segoe UI", self._size // 3)
            font.setWeight(QFont.DemiBold)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, initials)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT TOOLTIP
# تلميح Fluent
# ═══════════════════════════════════════════════════════════════════════════════

class FluentTooltip(QLabel):
    """
    Modern Fluent Design tooltip.
    تلميح حديث بتصميم Fluent
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)

        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._setup_style()

    def _setup_style(self):
        """Setup tooltip style"""
        colors = FluentDesignSystem().colors

        self.setStyleSheet(f"""
            QLabel {{
                background-color: {colors.bg_solid_tertiary};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_surface};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
            }}
        """)

        # Shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)


# ═══════════════════════════════════════════════════════════════════════════════
# SKELETON LOADER
# هيكل التحميل
# ═══════════════════════════════════════════════════════════════════════════════

class SkeletonLoader(QWidget):
    """
    Skeleton loading placeholder with shimmer animation.
    عنصر نائب للتحميل مع تأثير لمعان
    """

    def __init__(self, width: int = 100, height: int = 20,
                 rounded: bool = False, parent=None):
        super().__init__(parent)

        self._width = width
        self._height = height
        self._rounded = rounded
        self._shimmer_position = 0.0

        self.setFixedSize(width, height)

        # Animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_shimmer)
        self._timer.setInterval(16)
        self._timer.start()

    def _update_shimmer(self):
        """Update shimmer position"""
        self._shimmer_position += 0.02
        if self._shimmer_position > 1.5:
            self._shimmer_position = -0.5
        self.update()

    def paintEvent(self, event):
        """Custom paint with shimmer"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = FluentDesignSystem().colors

        # Background
        radius = self._height // 2 if self._rounded else 4
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        painter.fillPath(path, QColor(colors.fill_control))

        # Shimmer gradient
        shimmer_width = self._width * 0.5
        shimmer_x = self._shimmer_position * (self._width + shimmer_width) - shimmer_width

        gradient = QLinearGradient(shimmer_x, 0, shimmer_x + shimmer_width, 0)
        gradient.setColorAt(0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.5, QColor(255, 255, 255, 30))
        gradient.setColorAt(1, QColor(255, 255, 255, 0))

        painter.setClipPath(path)
        painter.fillRect(self.rect(), gradient)

        painter.end()

    def stop(self):
        """Stop animation"""
        self._timer.stop()

    def start(self):
        """Start animation"""
        self._timer.start()
