"""
Fluent Design Widgets - عناصر واجهة Fluent
==========================================

Windows 11 Fluent Design Widgets
--------------------------------

This module provides custom Qt widgets styled with
Windows 11 Fluent Design principles.

يوفر هذا الملف عناصر واجهة مستخدم مصممة بأسلوب
Windows 11 Fluent Design:
- FluentButton (أزرار)
- FluentCard (بطاقات)
- FluentProgressBar (شريط تقدم)
- FluentToggleSwitch (مفتاح تبديل)
- FluentTextBox (مربع نص)
- FluentComboBox (قائمة منسدلة)

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import Qt
try:
    from PySide6.QtCore import (
        Property,
        QEasingCurve,
        QPoint,
        QPropertyAnimation,
        QRect,
        QSize,
        Qt,
        Signal,
    )
    from PySide6.QtGui import (
        QBrush,
        QColor,
        QFont,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
    )
    from PySide6.QtWidgets import (
        QAbstractButton,
        QComboBox,
        QFrame,
        QGraphicsDropShadowEffect,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QProgressBar,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    HAS_QT = True
except ImportError:
    HAS_QT = False
    logger.warning("PySide6 not available. Fluent widgets disabled.")


# =============================================================================
# Color Palette / لوحة الألوان
# =============================================================================

class FluentColors:
    """ألوان Fluent Design / Fluent Design colors"""

    # Accent colors
    ACCENT = "#0078D4"
    ACCENT_LIGHT = "#429CE3"
    ACCENT_DARK = "#005A9E"

    # Background colors
    BACKGROUND_PRIMARY = "#FFFFFF"
    BACKGROUND_SECONDARY = "#F3F3F3"
    BACKGROUND_TERTIARY = "#F9F9F9"
    BACKGROUND_ACRYLIC = "rgba(255, 255, 255, 0.7)"

    # Dark mode
    DARK_BACKGROUND_PRIMARY = "#202020"
    DARK_BACKGROUND_SECONDARY = "#2D2D2D"
    DARK_BACKGROUND_TERTIARY = "#1A1A1A"
    DARK_BACKGROUND_ACRYLIC = "rgba(32, 32, 32, 0.7)"

    # Text colors
    TEXT_PRIMARY = "#000000"
    TEXT_SECONDARY = "#666666"
    TEXT_DISABLED = "#999999"

    DARK_TEXT_PRIMARY = "#FFFFFF"
    DARK_TEXT_SECONDARY = "#999999"
    DARK_TEXT_DISABLED = "#666666"

    # Border colors
    BORDER = "#E0E0E0"
    BORDER_FOCUS = "#0078D4"

    DARK_BORDER = "#404040"
    DARK_BORDER_FOCUS = "#429CE3"

    # Status colors
    SUCCESS = "#107C10"
    WARNING = "#FFB900"
    ERROR = "#E81123"
    INFO = "#0078D4"


if HAS_QT:
    # =========================================================================
    # FluentButton / زر Fluent
    # =========================================================================

    class FluentButton(QPushButton):
        """
        زر بأسلوب Fluent Design
        Fluent Design styled button
        """

        # Button variants
        STANDARD = "standard"
        ACCENT = "accent"
        SUBTLE = "subtle"
        HYPERLINK = "hyperlink"

        def __init__(
            self,
            text: str = "",
            variant: str = STANDARD,
            icon: Optional[str] = None,
            parent: Optional[QWidget] = None,
        ):
            super().__init__(text, parent)

            self._variant = variant
            self._icon_path = icon
            self._dark_mode = False
            self._hovered = False
            self._pressed = False

            self._setup_style()
            self._setup_animation()

        def _setup_style(self):
            """إعداد الأنماط"""
            self.setMinimumHeight(32)
            self.setCursor(Qt.PointingHandCursor)

            font = QFont("Segoe UI Variable", 10)
            self.setFont(font)

            self._apply_style()

        def _setup_animation(self):
            """إعداد الرسوم المتحركة"""
            # Hover animation
            self._hover_animation = QPropertyAnimation(self, b"minimumHeight")
            self._hover_animation.setDuration(100)
            self._hover_animation.setEasingCurve(QEasingCurve.OutQuad)

        def _apply_style(self):
            """تطبيق النمط"""
            if self._variant == self.ACCENT:
                bg = FluentColors.ACCENT
                bg_hover = FluentColors.ACCENT_LIGHT
                bg_pressed = FluentColors.ACCENT_DARK
                text_color = "#FFFFFF"
                border = "transparent"
            elif self._variant == self.SUBTLE:
                bg = "transparent"
                bg_hover = "rgba(0, 0, 0, 0.05)"
                bg_pressed = "rgba(0, 0, 0, 0.1)"
                text_color = FluentColors.TEXT_PRIMARY
                border = "transparent"
            elif self._variant == self.HYPERLINK:
                bg = "transparent"
                bg_hover = "transparent"
                bg_pressed = "transparent"
                text_color = FluentColors.ACCENT
                border = "transparent"
            else:  # STANDARD
                bg = FluentColors.BACKGROUND_SECONDARY
                bg_hover = "#E5E5E5"
                bg_pressed = "#D0D0D0"
                text_color = FluentColors.TEXT_PRIMARY
                border = FluentColors.BORDER

            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: {text_color};
                    border: 1px solid {border};
                    border-radius: 4px;
                    padding: 5px 15px;
                }}
                QPushButton:hover {{
                    background-color: {bg_hover};
                }}
                QPushButton:pressed {{
                    background-color: {bg_pressed};
                }}
                QPushButton:disabled {{
                    background-color: #F0F0F0;
                    color: {FluentColors.TEXT_DISABLED};
                }}
            """)

        def set_variant(self, variant: str):
            """تغيير نوع الزر"""
            self._variant = variant
            self._apply_style()

        def set_dark_mode(self, enabled: bool):
            """تفعيل الوضع الداكن"""
            self._dark_mode = enabled
            self._apply_style()


    # =========================================================================
    # FluentCard / بطاقة Fluent
    # =========================================================================

    class FluentCard(QFrame):
        """
        بطاقة بأسلوب Fluent Design
        Fluent Design styled card
        """

        clicked = Signal()

        def __init__(
            self,
            title: str = "",
            description: str = "",
            clickable: bool = False,
            parent: Optional[QWidget] = None,
        ):
            super().__init__(parent)

            self._title = title
            self._description = description
            self._clickable = clickable
            self._hovered = False

            self._setup_ui()
            self._setup_style()
            self._setup_shadow()

        def _setup_ui(self):
            """إعداد واجهة المستخدم"""
            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(8)

            # Title
            if self._title:
                self._title_label = QLabel(self._title)
                self._title_label.setFont(QFont("Segoe UI Variable", 14, QFont.DemiBold))
                layout.addWidget(self._title_label)

            # Description
            if self._description:
                self._desc_label = QLabel(self._description)
                self._desc_label.setFont(QFont("Segoe UI Variable", 10))
                self._desc_label.setWordWrap(True)
                self._desc_label.setStyleSheet(f"color: {FluentColors.TEXT_SECONDARY}")
                layout.addWidget(self._desc_label)

            # Content area
            self._content_widget = QWidget()
            self._content_layout = QVBoxLayout(self._content_widget)
            self._content_layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._content_widget)

        def _setup_style(self):
            """إعداد الأنماط"""
            if self._clickable:
                self.setCursor(Qt.PointingHandCursor)

            self.setStyleSheet(f"""
                FluentCard {{
                    background-color: {FluentColors.BACKGROUND_PRIMARY};
                    border: 1px solid {FluentColors.BORDER};
                    border-radius: 8px;
                }}
                FluentCard:hover {{
                    background-color: {FluentColors.BACKGROUND_TERTIARY};
                    border-color: {FluentColors.BORDER_FOCUS};
                }}
            """)

        def _setup_shadow(self):
            """إعداد الظل"""
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(16)
            shadow.setXOffset(0)
            shadow.setYOffset(4)
            shadow.setColor(QColor(0, 0, 0, 30))
            self.setGraphicsEffect(shadow)

        def add_widget(self, widget: QWidget):
            """إضافة عنصر للبطاقة"""
            self._content_layout.addWidget(widget)

        def set_title(self, title: str):
            """تعيين العنوان"""
            if hasattr(self, "_title_label"):
                self._title_label.setText(title)

        def set_description(self, description: str):
            """تعيين الوصف"""
            if hasattr(self, "_desc_label"):
                self._desc_label.setText(description)

        def mousePressEvent(self, event):
            """معالجة النقر"""
            if self._clickable:
                self.clicked.emit()
            super().mousePressEvent(event)


    # =========================================================================
    # FluentProgressBar / شريط تقدم Fluent
    # =========================================================================

    class FluentProgressBar(QProgressBar):
        """
        شريط تقدم بأسلوب Fluent Design
        Fluent Design styled progress bar
        """

        def __init__(
            self,
            parent: Optional[QWidget] = None,
            indeterminate: bool = False,
        ):
            super().__init__(parent)

            self._indeterminate = indeterminate
            self._animation_offset = 0

            self._setup_style()

            if indeterminate:
                self._setup_indeterminate_animation()

        def _setup_style(self):
            """إعداد الأنماط"""
            self.setTextVisible(False)
            self.setMinimumHeight(4)
            self.setMaximumHeight(4)

            self.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {FluentColors.BACKGROUND_SECONDARY};
                    border: none;
                    border-radius: 2px;
                }}
                QProgressBar::chunk {{
                    background-color: {FluentColors.ACCENT};
                    border-radius: 2px;
                }}
            """)

        def _setup_indeterminate_animation(self):
            """إعداد رسوم متحركة غير محددة"""
            self._animation = QPropertyAnimation(self, b"_animation_offset")
            self._animation.setDuration(1500)
            self._animation.setStartValue(0)
            self._animation.setEndValue(100)
            self._animation.setLoopCount(-1)
            self._animation.start()

        def paintEvent(self, event):
            """رسم مخصص للوضع غير المحدد"""
            if self._indeterminate:
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)

                # Background
                painter.setBrush(QColor(FluentColors.BACKGROUND_SECONDARY))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(self.rect(), 2, 2)

                # Animated bar
                width = self.width() // 3
                x = int((self._animation_offset / 100) * (self.width() + width)) - width

                painter.setBrush(QColor(FluentColors.ACCENT))
                painter.drawRoundedRect(x, 0, width, self.height(), 2, 2)

                painter.end()
            else:
                super().paintEvent(event)

        def set_indeterminate(self, enabled: bool):
            """تعيين الوضع غير المحدد"""
            self._indeterminate = enabled
            if enabled:
                self._setup_indeterminate_animation()
            else:
                if hasattr(self, "_animation"):
                    self._animation.stop()


    # =========================================================================
    # FluentToggleSwitch / مفتاح تبديل Fluent
    # =========================================================================

    class FluentToggleSwitch(QAbstractButton):
        """
        مفتاح تبديل بأسلوب Fluent Design
        Fluent Design styled toggle switch
        """

        toggled_state = Signal(bool)

        def __init__(
            self,
            checked: bool = False,
            parent: Optional[QWidget] = None,
        ):
            super().__init__(parent)

            self._checked = checked
            self._track_color = QColor(FluentColors.BACKGROUND_SECONDARY)
            self._thumb_position = 0.0

            self.setCheckable(True)
            self.setChecked(checked)
            self.setFixedSize(40, 20)
            self.setCursor(Qt.PointingHandCursor)

            self._setup_animation()

        def _setup_animation(self):
            """إعداد الرسوم المتحركة"""
            self._animation = QPropertyAnimation(self, b"thumb_position")
            self._animation.setDuration(150)
            self._animation.setEasingCurve(QEasingCurve.OutQuad)

        def get_thumb_position(self) -> float:
            return self._thumb_position

        def set_thumb_position(self, pos: float):
            self._thumb_position = pos
            self.update()

        thumb_position = Property(float, get_thumb_position, set_thumb_position)

        def paintEvent(self, event):
            """رسم المفتاح"""
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Track
            track_rect = QRect(0, 0, self.width(), self.height())

            if self.isChecked():
                track_color = QColor(FluentColors.ACCENT)
            else:
                track_color = QColor(FluentColors.BORDER)

            painter.setBrush(track_color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(track_rect, 10, 10)

            # Thumb
            thumb_x = int(self._thumb_position * (self.width() - 16)) + 2
            thumb_rect = QRect(thumb_x, 2, 16, 16)

            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(thumb_rect)

            painter.end()

        def mouseReleaseEvent(self, event):
            """معالجة النقر"""
            if event.button() == Qt.LeftButton:
                self.setChecked(not self.isChecked())
                self.toggled_state.emit(self.isChecked())
            super().mouseReleaseEvent(event)

        def setChecked(self, checked: bool):
            """تعيين حالة التفعيل"""
            super().setChecked(checked)

            self._animation.setStartValue(self._thumb_position)
            self._animation.setEndValue(1.0 if checked else 0.0)
            self._animation.start()


    # =========================================================================
    # FluentTextBox / مربع نص Fluent
    # =========================================================================

    class FluentTextBox(QLineEdit):
        """
        مربع نص بأسلوب Fluent Design
        Fluent Design styled text box
        """

        def __init__(
            self,
            placeholder: str = "",
            parent: Optional[QWidget] = None,
        ):
            super().__init__(parent)

            self.setPlaceholderText(placeholder)
            self._setup_style()

        def _setup_style(self):
            """إعداد الأنماط"""
            self.setMinimumHeight(32)
            self.setFont(QFont("Segoe UI Variable", 10))

            self.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {FluentColors.BACKGROUND_PRIMARY};
                    color: {FluentColors.TEXT_PRIMARY};
                    border: 1px solid {FluentColors.BORDER};
                    border-bottom: 2px solid {FluentColors.BORDER};
                    border-radius: 4px;
                    padding: 5px 10px;
                }}
                QLineEdit:focus {{
                    border-bottom: 2px solid {FluentColors.ACCENT};
                }}
                QLineEdit:hover {{
                    background-color: {FluentColors.BACKGROUND_TERTIARY};
                }}
                QLineEdit:disabled {{
                    background-color: #F0F0F0;
                    color: {FluentColors.TEXT_DISABLED};
                }}
            """)


    # =========================================================================
    # FluentComboBox / قائمة منسدلة Fluent
    # =========================================================================

    class FluentComboBox(QComboBox):
        """
        قائمة منسدلة بأسلوب Fluent Design
        Fluent Design styled combo box
        """

        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self._setup_style()

        def _setup_style(self):
            """إعداد الأنماط"""
            self.setMinimumHeight(32)
            self.setFont(QFont("Segoe UI Variable", 10))

            self.setStyleSheet(f"""
                QComboBox {{
                    background-color: {FluentColors.BACKGROUND_PRIMARY};
                    color: {FluentColors.TEXT_PRIMARY};
                    border: 1px solid {FluentColors.BORDER};
                    border-radius: 4px;
                    padding: 5px 10px;
                    padding-right: 30px;
                }}
                QComboBox:hover {{
                    background-color: {FluentColors.BACKGROUND_TERTIARY};
                }}
                QComboBox:focus {{
                    border-color: {FluentColors.ACCENT};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 30px;
                }}
                QComboBox::down-arrow {{
                    image: none;
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 5px solid {FluentColors.TEXT_PRIMARY};
                }}
                QComboBox QAbstractItemView {{
                    background-color: {FluentColors.BACKGROUND_PRIMARY};
                    border: 1px solid {FluentColors.BORDER};
                    border-radius: 4px;
                    selection-background-color: {FluentColors.ACCENT};
                }}
            """)


    # =========================================================================
    # FluentSpinner / مؤشر تحميل Fluent
    # =========================================================================

    class FluentSpinner(QWidget):
        """
        مؤشر تحميل بأسلوب Fluent Design
        Fluent Design styled loading spinner
        """

        def __init__(
            self,
            size: int = 32,
            parent: Optional[QWidget] = None,
        ):
            super().__init__(parent)

            self._size = size
            self._angle = 0
            self._spinning = False

            self.setFixedSize(size, size)

            self._animation = QPropertyAnimation(self, b"rotation_angle")
            self._animation.setDuration(1000)
            self._animation.setStartValue(0)
            self._animation.setEndValue(360)
            self._animation.setLoopCount(-1)

        def get_rotation_angle(self) -> int:
            return self._angle

        def set_rotation_angle(self, angle: int):
            self._angle = angle
            self.update()

        rotation_angle = Property(int, get_rotation_angle, set_rotation_angle)

        def start(self):
            """بدء الدوران"""
            self._spinning = True
            self._animation.start()

        def stop(self):
            """إيقاف الدوران"""
            self._spinning = False
            self._animation.stop()

        def paintEvent(self, event):
            """رسم المؤشر"""
            if not self._spinning:
                return

            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Center and rotate
            painter.translate(self.width() / 2, self.height() / 2)
            painter.rotate(self._angle)

            # Draw arcs
            pen = QPen(QColor(FluentColors.ACCENT))
            pen.setWidth(3)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)

            rect = QRect(-self._size // 2 + 4, -self._size // 2 + 4,
                         self._size - 8, self._size - 8)

            painter.drawArc(rect, 0, 270 * 16)

            painter.end()


    # =========================================================================
    # FluentBadge / شارة Fluent
    # =========================================================================

    class FluentBadge(QLabel):
        """
        شارة بأسلوب Fluent Design
        Fluent Design styled badge
        """

        def __init__(
            self,
            text: str = "",
            variant: str = "default",
            parent: Optional[QWidget] = None,
        ):
            super().__init__(text, parent)

            self._variant = variant
            self._setup_style()

        def _setup_style(self):
            """إعداد الأنماط"""
            self.setFont(QFont("Segoe UI Variable", 9))
            self.setAlignment(Qt.AlignCenter)

            # Variant colors
            colors = {
                "default": (FluentColors.BACKGROUND_SECONDARY, FluentColors.TEXT_PRIMARY),
                "accent": (FluentColors.ACCENT, "#FFFFFF"),
                "success": (FluentColors.SUCCESS, "#FFFFFF"),
                "warning": (FluentColors.WARNING, "#000000"),
                "error": (FluentColors.ERROR, "#FFFFFF"),
            }

            bg, text_color = colors.get(self._variant, colors["default"])

            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {bg};
                    color: {text_color};
                    border-radius: 10px;
                    padding: 2px 8px;
                }}
            """)

        def set_variant(self, variant: str):
            """تغيير نوع الشارة"""
            self._variant = variant
            self._setup_style()


else:
    # Fallback classes when Qt is not available
    class FluentButton:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 required for Fluent widgets")

    class FluentCard:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 required for Fluent widgets")

    class FluentProgressBar:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 required for Fluent widgets")

    class FluentToggleSwitch:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 required for Fluent widgets")

    class FluentTextBox:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 required for Fluent widgets")

    class FluentComboBox:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 required for Fluent widgets")

    class FluentSpinner:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 required for Fluent widgets")

    class FluentBadge:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 required for Fluent widgets")
