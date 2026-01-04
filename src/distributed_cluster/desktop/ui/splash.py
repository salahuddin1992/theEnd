"""
Windows 11 Fluent Splash Screen
شاشة البداية بتصميم Fluent

Modern splash screen with:
- Mica/Acrylic backdrop
- Animated logo
- Progress indicator
- Status messages
"""

from __future__ import annotations

import math
from typing import List, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .fluent_design import FluentDesignSystem

# ═══════════════════════════════════════════════════════════════════════════════
# ANIMATED LOGO
# ═══════════════════════════════════════════════════════════════════════════════

class AnimatedLogo(QWidget):
    """
    Animated NebulaCompute logo.
    شعار متحرك
    """

    def __init__(self, size: int = 120, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

        # Animation properties
        self._rotation = 0.0
        self._pulse = 0.0
        self._particles: List[dict] = []

        # Colors
        colors = FluentDesignSystem().colors
        self._primary = QColor(colors.accent)
        self._secondary = QColor(colors.accent_light)
        self._glow = QColor(colors.accent)
        self._glow.setAlpha(100)

        # Animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(16)  # ~60 FPS

        # Initialize particles
        self._init_particles()

    def _init_particles(self):
        """Initialize orbital particles"""
        import random
        for i in range(8):
            self._particles.append({
                "angle": i * 45,
                "radius": self._size * 0.35,
                "speed": random.uniform(0.5, 1.5),
                "size": random.uniform(3, 6),
                "opacity": random.uniform(0.5, 1.0)
            })

    def _animate(self):
        """Animation frame"""
        self._rotation += 0.8
        self._pulse = (self._pulse + 0.05) % (2 * math.pi)

        # Update particles
        for p in self._particles:
            p["angle"] += p["speed"]

        self.update()

    def paintEvent(self, event):
        """Paint the animated logo"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = self._size / 2
        painter.translate(center, center)

        # Draw glow
        glow_size = self._size * 0.4 + math.sin(self._pulse) * 5
        gradient = QRadialGradient(0, 0, glow_size)
        gradient.setColorAt(0, self._glow)
        gradient.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(-glow_size, -glow_size, glow_size * 2, glow_size * 2))

        # Draw outer ring
        ring_size = self._size * 0.38
        pen = QPen(self._secondary)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(-ring_size, -ring_size, ring_size * 2, ring_size * 2))

        # Draw rotating arcs
        painter.save()
        painter.rotate(self._rotation)
        arc_pen = QPen(self._primary)
        arc_pen.setWidth(3)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)

        arc_rect = QRectF(-ring_size, -ring_size, ring_size * 2, ring_size * 2)
        painter.drawArc(arc_rect, 0 * 16, 60 * 16)
        painter.drawArc(arc_rect, 120 * 16, 60 * 16)
        painter.drawArc(arc_rect, 240 * 16, 60 * 16)
        painter.restore()

        # Draw orbital particles
        for p in self._particles:
            angle_rad = math.radians(p["angle"])
            x = math.cos(angle_rad) * p["radius"]
            y = math.sin(angle_rad) * p["radius"]

            color = QColor(self._primary)
            color.setAlphaF(p["opacity"])
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(x - p["size"]/2, y - p["size"]/2, p["size"], p["size"]))

        # Draw center hexagon
        painter.save()
        painter.rotate(self._rotation * 0.5)

        hex_size = self._size * 0.15
        path = QPainterPath()
        for i in range(6):
            angle = math.radians(i * 60 - 90)
            x = math.cos(angle) * hex_size
            y = math.sin(angle) * hex_size
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()

        gradient = QLinearGradient(-hex_size, -hex_size, hex_size, hex_size)
        gradient.setColorAt(0, self._primary)
        gradient.setColorAt(1, self._secondary)
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        painter.restore()

        # Draw "N" letter
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI", int(self._size * 0.12), QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(-20, -15, 40, 30), Qt.AlignmentFlag.AlignCenter, "N")

    def stop(self):
        """Stop animation"""
        self._timer.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT PROGRESS RING
# ═══════════════════════════════════════════════════════════════════════════════

class SplashProgressRing(QWidget):
    """
    Indeterminate progress ring for splash screen.
    حلقة التقدم لشاشة البداية
    """

    def __init__(self, size: int = 32, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

        colors = FluentDesignSystem().colors
        self._color = QColor(colors.accent)

        self._angle = 0
        self._arc_length = 90

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(16)

    def _animate(self):
        """Animate progress ring"""
        self._angle = (self._angle + 5) % 360

        # Vary arc length for dynamic effect
        self._arc_length = 60 + 30 * math.sin(math.radians(self._angle * 2))

        self.update()

    def paintEvent(self, event):
        """Paint progress ring"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(self._color)
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        margin = 4
        rect = QRectF(margin, margin, self._size - margin * 2, self._size - margin * 2)

        painter.drawArc(rect, self._angle * 16, int(self._arc_length) * 16)

    def stop(self):
        """Stop animation"""
        self._timer.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# SPLASH SCREEN
# ═══════════════════════════════════════════════════════════════════════════════

class FluentSplashScreen(QWidget):
    """
    Modern Windows 11 Fluent Design splash screen.
    شاشة البداية بتصميم ويندوز 11

    Features:
    - Frameless window with Mica effect
    - Animated logo
    - Progress indicator
    - Status messages
    - Fade in/out animations
    """

    finished = Signal()
    progress_updated = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._progress = 0
        self._status = "Initializing..."

        self._setup_window()
        self._setup_ui()
        self._setup_animations()

    def _setup_window(self):
        """Setup frameless window"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(480, 360)

        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _setup_ui(self):
        """Setup splash UI"""
        colors = FluentDesignSystem().colors

        # Main container with rounded corners
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QWidget()
        container.setObjectName("splashContainer")
        container.setStyleSheet(f"""
            #splashContainer {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {colors.bg_mica_base},
                    stop:1 {colors.bg_solid_base}
                );
                border-radius: 16px;
                border: 1px solid {colors.stroke_surface};
            }}
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(40, 50, 40, 40)
        container_layout.setSpacing(20)

        # Animated logo
        logo_container = QHBoxLayout()
        logo_container.addStretch()
        self._logo = AnimatedLogo(140)
        logo_container.addWidget(self._logo)
        logo_container.addStretch()
        container_layout.addLayout(logo_container)

        # App name
        name_label = QLabel("NebulaCompute")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 32px;
            font-weight: 700;
            font-family: 'Segoe UI Variable Display', 'Segoe UI', sans-serif;
        """)
        container_layout.addWidget(name_label)

        # Tagline
        tagline = QLabel("Distributed Computing Platform")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(f"""
            color: {colors.text_secondary};
            font-size: 14px;
            font-weight: 400;
        """)
        container_layout.addWidget(tagline)

        container_layout.addSpacing(20)

        # Progress area
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(12)

        # Progress ring
        self._progress_ring = SplashProgressRing(28)
        progress_layout.addWidget(self._progress_ring)

        # Status text
        self._status_label = QLabel("Initializing...")
        self._status_label.setStyleSheet(f"""
            color: {colors.text_secondary};
            font-size: 13px;
        """)
        progress_layout.addWidget(self._status_label)
        progress_layout.addStretch()

        container_layout.addLayout(progress_layout)

        # Version
        version_label = QLabel("Version 1.0.0")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet(f"""
            color: {colors.text_tertiary};
            font-size: 11px;
        """)
        container_layout.addWidget(version_label)

        layout.addWidget(container)

        # Opacity effect for fade animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0)
        self.setGraphicsEffect(self._opacity_effect)

    def _setup_animations(self):
        """Setup fade animations"""
        # Fade in animation
        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(600)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Fade out animation
        self._fade_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_out.setDuration(400)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out.finished.connect(self._on_fade_out_finished)

    def show(self):
        """Show with fade in"""
        super().show()
        self._fade_in.start()

    def set_status(self, status: str, progress: int = None):
        """
        Update status message.

        Args:
            status: Status message
            progress: Optional progress (0-100)
        """
        self._status = status
        self._status_label.setText(status)

        if progress is not None:
            self._progress = progress

        self.progress_updated.emit(self._progress, status)
        QApplication.processEvents()

    def finish(self, main_window: QWidget = None):
        """
        Close splash and show main window.

        Args:
            main_window: Main window to show after splash
        """
        self._main_window = main_window
        self._fade_out.start()

    def _on_fade_out_finished(self):
        """Handle fade out complete"""
        self._logo.stop()
        self._progress_ring.stop()

        if hasattr(self, '_main_window') and self._main_window:
            self._main_window.show()

        self.finished.emit()
        self.close()


# ═══════════════════════════════════════════════════════════════════════════════
# SPLASH SCREEN MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class SplashScreenManager:
    """
    Manager for splash screen lifecycle.
    مدير دورة حياة شاشة البداية

    Provides a simple interface for showing splash during app startup.
    """

    def __init__(self):
        self._splash: Optional[FluentSplashScreen] = None
        self._steps: List[tuple] = []
        self._current_step = 0

    def create(self) -> FluentSplashScreen:
        """Create and return splash screen"""
        self._splash = FluentSplashScreen()
        return self._splash

    def add_step(self, message: str, callback=None):
        """
        Add initialization step.

        Args:
            message: Status message for this step
            callback: Function to call during this step
        """
        self._steps.append((message, callback))

    def show(self):
        """Show splash screen"""
        if self._splash:
            self._splash.show()
            QApplication.processEvents()

    def run_steps(self):
        """Run all initialization steps"""
        total = len(self._steps)

        for i, (message, callback) in enumerate(self._steps):
            progress = int((i / total) * 100)
            self._splash.set_status(message, progress)

            if callback:
                try:
                    callback()
                except Exception as e:
                    print(f"Splash step error: {e}")

            QApplication.processEvents()

        self._splash.set_status("Ready!", 100)

    def finish(self, main_window: QWidget):
        """Finish splash and show main window"""
        if self._splash:
            # Small delay before finishing
            QTimer.singleShot(500, lambda: self._splash.finish(main_window))


# ═══════════════════════════════════════════════════════════════════════════════
# LOADING OVERLAY
# ═══════════════════════════════════════════════════════════════════════════════

class LoadingOverlay(QWidget):
    """
    Loading overlay for async operations.
    طبقة التحميل للعمليات المتزامنة
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._setup_ui()

        # Opacity animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(200)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)

        self._fade_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_out.setDuration(200)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.finished.connect(self.hide)

    def _setup_ui(self):
        """Setup overlay UI"""
        colors = FluentDesignSystem().colors

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Background
        self.setStyleSheet("""
            LoadingOverlay {
                background-color: rgba(0, 0, 0, 0.5);
            }
        """)

        # Card
        card = QWidget()
        card.setFixedSize(200, 150)
        card.setStyleSheet(f"""
            background-color: {colors.bg_solid_base};
            border-radius: 12px;
            border: 1px solid {colors.stroke_surface};
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)

        # Progress ring
        self._progress = SplashProgressRing(40)
        ring_container = QHBoxLayout()
        ring_container.addStretch()
        ring_container.addWidget(self._progress)
        ring_container.addStretch()
        card_layout.addLayout(ring_container)

        # Message
        self._message = QLabel("Loading...")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 14px;
        """)
        card_layout.addWidget(self._message)

        layout.addWidget(card)

    def show_loading(self, message: str = "Loading..."):
        """Show overlay with message"""
        self._message.setText(message)
        self.show()
        self.raise_()
        self._fade_in.start()

    def hide_loading(self):
        """Hide overlay"""
        self._fade_out.start()

    def set_message(self, message: str):
        """Update loading message"""
        self._message.setText(message)

    def resizeEvent(self, event):
        """Resize to parent"""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "FluentSplashScreen",
    "SplashScreenManager",
    "AnimatedLogo",
    "SplashProgressRing",
    "LoadingOverlay",
]
