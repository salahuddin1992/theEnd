"""
Advanced Animation System for Fluent Design
نظام الرسوم المتحركة المتقدم

Provides:
- Smooth transitions
- Spring physics animations
- Fade, slide, scale effects
- Staggered animations
- Custom easing curves
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from PySide6.QtCore import (
    QObject, Signal, QPropertyAnimation, QParallelAnimationGroup,
    QSequentialAnimationGroup, QAbstractAnimation, QEasingCurve,
    QPoint, QSize, QTimer, QVariantAnimation
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT EASING CURVES
# منحنيات التسهيل
# ═══════════════════════════════════════════════════════════════════════════════

class FluentEasing:
    """
    Windows 11 Fluent Design easing curves.
    منحنيات التحريك الخاصة بـ Windows 11
    """

    # Standard curves
    @staticmethod
    def ease_out_expo() -> QEasingCurve:
        """Fast start, slow end - for enter animations"""
        curve = QEasingCurve(QEasingCurve.OutExpo)
        return curve

    @staticmethod
    def ease_in_expo() -> QEasingCurve:
        """Slow start, fast end - for exit animations"""
        curve = QEasingCurve(QEasingCurve.InExpo)
        return curve

    @staticmethod
    def ease_out_cubic() -> QEasingCurve:
        """Smooth deceleration"""
        return QEasingCurve(QEasingCurve.OutCubic)

    @staticmethod
    def ease_in_out_cubic() -> QEasingCurve:
        """Smooth acceleration and deceleration"""
        return QEasingCurve(QEasingCurve.InOutCubic)

    @staticmethod
    def ease_out_back() -> QEasingCurve:
        """Slight overshoot at end"""
        return QEasingCurve(QEasingCurve.OutBack)

    @staticmethod
    def ease_out_elastic() -> QEasingCurve:
        """Bouncy spring effect"""
        return QEasingCurve(QEasingCurve.OutElastic)

    @staticmethod
    def linear() -> QEasingCurve:
        """Constant speed"""
        return QEasingCurve(QEasingCurve.Linear)

    # Fluent-specific durations (in ms)
    DURATION_FASTEST = 83
    DURATION_FASTER = 127
    DURATION_FAST = 167
    DURATION_NORMAL = 250
    DURATION_SLOW = 333
    DURATION_SLOWER = 500


# ═══════════════════════════════════════════════════════════════════════════════
# SPRING ANIMATION
# رسوم متحركة نابضية
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SpringConfig:
    """Spring physics configuration"""
    stiffness: float = 170.0  # Spring stiffness
    damping: float = 26.0     # Damping ratio
    mass: float = 1.0         # Mass
    velocity: float = 0.0     # Initial velocity

    @classmethod
    def default(cls) -> "SpringConfig":
        return cls()

    @classmethod
    def gentle(cls) -> "SpringConfig":
        return cls(stiffness=120, damping=14)

    @classmethod
    def wobbly(cls) -> "SpringConfig":
        return cls(stiffness=180, damping=12)

    @classmethod
    def stiff(cls) -> "SpringConfig":
        return cls(stiffness=210, damping=20)

    @classmethod
    def slow(cls) -> "SpringConfig":
        return cls(stiffness=280, damping=60)


class SpringAnimation(QObject):
    """
    Physics-based spring animation.
    رسوم متحركة قائمة على فيزياء النوابض
    """

    value_changed = Signal(float)
    finished = Signal()

    def __init__(self, config: SpringConfig = None, parent: QObject = None):
        super().__init__(parent)

        self._config = config or SpringConfig.default()
        self._target_value = 0.0
        self._current_value = 0.0
        self._velocity = 0.0
        self._running = False

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps
        self._timer.timeout.connect(self._step)

    @property
    def value(self) -> float:
        return self._current_value

    def set_target(self, target: float, from_value: float = None):
        """Set target value and start animation"""
        if from_value is not None:
            self._current_value = from_value
        self._target_value = target
        self._velocity = self._config.velocity
        self._running = True
        self._timer.start()

    def stop(self):
        """Stop animation"""
        self._running = False
        self._timer.stop()

    def _step(self):
        """Physics step"""
        if not self._running:
            return

        # Spring physics calculation
        dt = 0.016  # 16ms timestep

        # Spring force: F = -k * x
        spring_force = -self._config.stiffness * (self._current_value - self._target_value)

        # Damping force: F = -d * v
        damping_force = -self._config.damping * self._velocity

        # Acceleration: a = F / m
        acceleration = (spring_force + damping_force) / self._config.mass

        # Update velocity and position
        self._velocity += acceleration * dt
        self._current_value += self._velocity * dt

        self.value_changed.emit(self._current_value)

        # Check if animation should stop
        if (abs(self._velocity) < 0.01 and
            abs(self._current_value - self._target_value) < 0.01):
            self._current_value = self._target_value
            self._running = False
            self._timer.stop()
            self.finished.emit()


# ═══════════════════════════════════════════════════════════════════════════════
# FADE ANIMATION
# رسوم التلاشي
# ═══════════════════════════════════════════════════════════════════════════════

class FadeAnimation(QObject):
    """
    Opacity fade animation for widgets.
    رسوم تلاشي الشفافية
    """

    finished = Signal()

    def __init__(self, widget: QWidget, parent: QObject = None):
        super().__init__(parent)

        self._widget = widget
        self._opacity_effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(self._opacity_effect)

        self._animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._animation.finished.connect(self.finished.emit)

    def fade_in(self, duration: int = FluentEasing.DURATION_NORMAL,
                from_opacity: float = 0.0, to_opacity: float = 1.0):
        """Fade in animation"""
        self._animation.stop()
        self._animation.setDuration(duration)
        self._animation.setStartValue(from_opacity)
        self._animation.setEndValue(to_opacity)
        self._animation.setEasingCurve(FluentEasing.ease_out_cubic())
        self._widget.show()
        self._animation.start()

    def fade_out(self, duration: int = FluentEasing.DURATION_NORMAL,
                 from_opacity: float = 1.0, to_opacity: float = 0.0,
                 hide_on_finish: bool = True):
        """Fade out animation"""
        self._animation.stop()
        self._animation.setDuration(duration)
        self._animation.setStartValue(from_opacity)
        self._animation.setEndValue(to_opacity)
        self._animation.setEasingCurve(FluentEasing.ease_out_cubic())

        if hide_on_finish:
            self._animation.finished.connect(lambda: self._widget.hide())

        self._animation.start()

    def set_opacity(self, opacity: float):
        """Set opacity directly without animation"""
        self._opacity_effect.setOpacity(opacity)


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE ANIMATION
# رسوم الانزلاق
# ═══════════════════════════════════════════════════════════════════════════════

class SlideDirection(Enum):
    """Slide animation directions"""
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


class SlideAnimation(QObject):
    """
    Slide animation for widgets.
    رسوم الانزلاق للعناصر
    """

    finished = Signal()

    def __init__(self, widget: QWidget, parent: QObject = None):
        super().__init__(parent)

        self._widget = widget
        self._animation = QPropertyAnimation(widget, b"pos")
        self._animation.finished.connect(self.finished.emit)

    def slide_in(self, direction: SlideDirection = SlideDirection.RIGHT,
                 duration: int = FluentEasing.DURATION_NORMAL,
                 distance: int = 50):
        """Slide in from direction"""
        self._animation.stop()

        current_pos = self._widget.pos()
        start_pos = QPoint(current_pos)

        if direction == SlideDirection.LEFT:
            start_pos.setX(current_pos.x() - distance)
        elif direction == SlideDirection.RIGHT:
            start_pos.setX(current_pos.x() + distance)
        elif direction == SlideDirection.UP:
            start_pos.setY(current_pos.y() - distance)
        elif direction == SlideDirection.DOWN:
            start_pos.setY(current_pos.y() + distance)

        self._animation.setDuration(duration)
        self._animation.setStartValue(start_pos)
        self._animation.setEndValue(current_pos)
        self._animation.setEasingCurve(FluentEasing.ease_out_expo())

        self._widget.show()
        self._animation.start()

    def slide_out(self, direction: SlideDirection = SlideDirection.LEFT,
                  duration: int = FluentEasing.DURATION_NORMAL,
                  distance: int = 50,
                  hide_on_finish: bool = True):
        """Slide out in direction"""
        self._animation.stop()

        current_pos = self._widget.pos()
        end_pos = QPoint(current_pos)

        if direction == SlideDirection.LEFT:
            end_pos.setX(current_pos.x() - distance)
        elif direction == SlideDirection.RIGHT:
            end_pos.setX(current_pos.x() + distance)
        elif direction == SlideDirection.UP:
            end_pos.setY(current_pos.y() - distance)
        elif direction == SlideDirection.DOWN:
            end_pos.setY(current_pos.y() + distance)

        self._animation.setDuration(duration)
        self._animation.setStartValue(current_pos)
        self._animation.setEndValue(end_pos)
        self._animation.setEasingCurve(FluentEasing.ease_in_expo())

        if hide_on_finish:
            self._animation.finished.connect(lambda: self._widget.hide())

        self._animation.start()

    def slide_to(self, target_pos: QPoint,
                 duration: int = FluentEasing.DURATION_NORMAL):
        """Slide to specific position"""
        self._animation.stop()
        self._animation.setDuration(duration)
        self._animation.setStartValue(self._widget.pos())
        self._animation.setEndValue(target_pos)
        self._animation.setEasingCurve(FluentEasing.ease_out_cubic())
        self._animation.start()


# ═══════════════════════════════════════════════════════════════════════════════
# SCALE ANIMATION
# رسوم التكبير والتصغير
# ═══════════════════════════════════════════════════════════════════════════════

class ScaleAnimation(QObject):
    """
    Scale animation for widgets.
    رسوم التكبير والتصغير
    """

    finished = Signal()

    def __init__(self, widget: QWidget, parent: QObject = None):
        super().__init__(parent)

        self._widget = widget
        self._original_size = widget.size()
        self._animation = QPropertyAnimation(widget, b"size")
        self._animation.finished.connect(self.finished.emit)

    def scale_in(self, duration: int = FluentEasing.DURATION_NORMAL,
                 from_scale: float = 0.9, to_scale: float = 1.0):
        """Scale in animation"""
        self._animation.stop()

        original = self._original_size
        start_size = QSize(int(original.width() * from_scale),
                          int(original.height() * from_scale))
        end_size = QSize(int(original.width() * to_scale),
                        int(original.height() * to_scale))

        self._animation.setDuration(duration)
        self._animation.setStartValue(start_size)
        self._animation.setEndValue(end_size)
        self._animation.setEasingCurve(FluentEasing.ease_out_cubic())

        self._widget.show()
        self._animation.start()

    def scale_out(self, duration: int = FluentEasing.DURATION_NORMAL,
                  from_scale: float = 1.0, to_scale: float = 0.9,
                  hide_on_finish: bool = True):
        """Scale out animation"""
        self._animation.stop()

        original = self._original_size
        start_size = QSize(int(original.width() * from_scale),
                          int(original.height() * from_scale))
        end_size = QSize(int(original.width() * to_scale),
                        int(original.height() * to_scale))

        self._animation.setDuration(duration)
        self._animation.setStartValue(start_size)
        self._animation.setEndValue(end_size)
        self._animation.setEasingCurve(FluentEasing.ease_in_expo())

        if hide_on_finish:
            self._animation.finished.connect(lambda: self._widget.hide())

        self._animation.start()

    def pulse(self, duration: int = 300, scale: float = 1.05):
        """Pulse animation (scale up then back)"""
        original = self._original_size
        scaled_size = QSize(int(original.width() * scale),
                           int(original.height() * scale))

        # Create sequential animation
        group = QSequentialAnimationGroup(self)

        # Scale up
        scale_up = QPropertyAnimation(self._widget, b"size")
        scale_up.setDuration(duration // 2)
        scale_up.setStartValue(original)
        scale_up.setEndValue(scaled_size)
        scale_up.setEasingCurve(FluentEasing.ease_out_cubic())

        # Scale down
        scale_down = QPropertyAnimation(self._widget, b"size")
        scale_down.setDuration(duration // 2)
        scale_down.setStartValue(scaled_size)
        scale_down.setEndValue(original)
        scale_down.setEasingCurve(FluentEasing.ease_out_cubic())

        group.addAnimation(scale_up)
        group.addAnimation(scale_down)
        group.finished.connect(self.finished.emit)
        group.start()


# ═══════════════════════════════════════════════════════════════════════════════
# COLOR ANIMATION
# رسوم الألوان
# ═══════════════════════════════════════════════════════════════════════════════

class ColorAnimation(QVariantAnimation):
    """
    Smooth color transition animation.
    رسوم انتقال الألوان السلسة
    """

    color_changed = Signal(QColor)

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self.valueChanged.connect(self._on_value_changed)

    def _on_value_changed(self, value):
        if isinstance(value, QColor):
            self.color_changed.emit(value)

    def animate_to(self, from_color: QColor, to_color: QColor,
                   duration: int = FluentEasing.DURATION_NORMAL):
        """Animate between colors"""
        self.stop()
        self.setDuration(duration)
        self.setStartValue(from_color)
        self.setEndValue(to_color)
        self.setEasingCurve(FluentEasing.ease_out_cubic())
        self.start()


# ═══════════════════════════════════════════════════════════════════════════════
# STAGGERED ANIMATION
# رسوم متدرجة
# ═══════════════════════════════════════════════════════════════════════════════

class StaggeredAnimation(QObject):
    """
    Staggered animation for multiple widgets.
    رسوم متدرجة لعناصر متعددة
    """

    all_finished = Signal()

    def __init__(self, widgets: List[QWidget], parent: QObject = None):
        super().__init__(parent)
        self._widgets = widgets
        self._finished_count = 0

    def fade_in_stagger(self, delay: int = 50,
                        duration: int = FluentEasing.DURATION_NORMAL):
        """Fade in widgets with staggered delay"""
        self._finished_count = 0

        for i, widget in enumerate(self._widgets):
            fade = FadeAnimation(widget)
            fade.finished.connect(self._on_animation_finished)

            QTimer.singleShot(i * delay, lambda w=widget, f=fade: f.fade_in(duration))

    def slide_in_stagger(self, direction: SlideDirection = SlideDirection.UP,
                         delay: int = 50,
                         duration: int = FluentEasing.DURATION_NORMAL):
        """Slide in widgets with staggered delay"""
        self._finished_count = 0

        for i, widget in enumerate(self._widgets):
            slide = SlideAnimation(widget)
            slide.finished.connect(self._on_animation_finished)

            QTimer.singleShot(
                i * delay,
                lambda w=widget, s=slide: s.slide_in(direction, duration)
            )

    def _on_animation_finished(self):
        self._finished_count += 1
        if self._finished_count >= len(self._widgets):
            self.all_finished.emit()


# ═══════════════════════════════════════════════════════════════════════════════
# ANIMATION MANAGER
# مدير الرسوم المتحركة
# ═══════════════════════════════════════════════════════════════════════════════

class AnimationManager(QObject):
    """
    Central manager for coordinating animations.
    مدير مركزي لتنسيق الرسوم المتحركة
    """

    _instance: Optional["AnimationManager"] = None

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
        self._active_animations: List[QAbstractAnimation] = []
        self._animation_enabled = True

    @property
    def enabled(self) -> bool:
        return self._animation_enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._animation_enabled = value

    def fade_in(self, widget: QWidget, duration: int = None) -> FadeAnimation:
        """Create and start fade in animation"""
        if not self._animation_enabled:
            widget.show()
            return None

        duration = duration or FluentEasing.DURATION_NORMAL
        anim = FadeAnimation(widget)
        anim.fade_in(duration)
        return anim

    def fade_out(self, widget: QWidget, duration: int = None,
                 hide: bool = True) -> FadeAnimation:
        """Create and start fade out animation"""
        if not self._animation_enabled:
            if hide:
                widget.hide()
            return None

        duration = duration or FluentEasing.DURATION_NORMAL
        anim = FadeAnimation(widget)
        anim.fade_out(duration, hide_on_finish=hide)
        return anim

    def slide_in(self, widget: QWidget,
                 direction: SlideDirection = SlideDirection.RIGHT,
                 duration: int = None) -> SlideAnimation:
        """Create and start slide in animation"""
        if not self._animation_enabled:
            widget.show()
            return None

        duration = duration or FluentEasing.DURATION_NORMAL
        anim = SlideAnimation(widget)
        anim.slide_in(direction, duration)
        return anim

    def slide_out(self, widget: QWidget,
                  direction: SlideDirection = SlideDirection.LEFT,
                  duration: int = None,
                  hide: bool = True) -> SlideAnimation:
        """Create and start slide out animation"""
        if not self._animation_enabled:
            if hide:
                widget.hide()
            return None

        duration = duration or FluentEasing.DURATION_NORMAL
        anim = SlideAnimation(widget)
        anim.slide_out(direction, duration, hide_on_finish=hide)
        return anim

    def scale_in(self, widget: QWidget,
                 duration: int = None) -> ScaleAnimation:
        """Create and start scale in animation"""
        if not self._animation_enabled:
            widget.show()
            return None

        duration = duration or FluentEasing.DURATION_NORMAL
        anim = ScaleAnimation(widget)
        anim.scale_in(duration)
        return anim

    def parallel(self, *animations: QAbstractAnimation) -> QParallelAnimationGroup:
        """Run multiple animations in parallel"""
        group = QParallelAnimationGroup()
        for anim in animations:
            group.addAnimation(anim)
        group.start()
        return group

    def sequential(self, *animations: QAbstractAnimation) -> QSequentialAnimationGroup:
        """Run animations sequentially"""
        group = QSequentialAnimationGroup()
        for anim in animations:
            group.addAnimation(anim)
        group.start()
        return group

    def staggered(self, widgets: List[QWidget],
                  animation_type: str = "fade",
                  delay: int = 50) -> StaggeredAnimation:
        """Create staggered animation for multiple widgets"""
        stagger = StaggeredAnimation(widgets)

        if animation_type == "fade":
            stagger.fade_in_stagger(delay)
        elif animation_type == "slide":
            stagger.slide_in_stagger(delay=delay)

        return stagger


# Global animation manager
animations = AnimationManager()
