"""
Advanced Fluent Dashboard View
لوحة القيادة المتقدمة بتصميم Fluent

Features:
- Animated stat cards
- Real-time charts
- System health indicators
- Activity feed
- Quick actions
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from PySide6.QtCore import Property, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from .animations import FluentEasing
from .components import FluentCard
from .fluent_design import FluentDesignSystem
from .titlebar import FluentIcons

# ═══════════════════════════════════════════════════════════════════════════════
# ANIMATED STAT CARD
# بطاقة إحصائيات متحركة
# ═══════════════════════════════════════════════════════════════════════════════


class AnimatedStatCard(QFrame):
    """
    Animated statistics card with number counter effect.
    بطاقة إحصائيات متحركة مع تأثير عداد
    """

    clicked = Signal()

    def __init__(
        self,
        title: str,
        value: int = 0,
        icon: str = "",
        trend: float = 0,
        trend_label: str = "",
        color: str = None,
        parent=None,
    ):
        super().__init__(parent)

        self._title = title
        self._target_value = value
        self._current_value = 0.0
        self._icon = icon
        self._trend = trend
        self._trend_label = trend_label
        self._color = color
        self._hovered = False

        self._setup_ui()
        self._setup_animation()
        self.animate_to(value)

    def _setup_ui(self):
        """Setup card UI"""
        colors = FluentDesignSystem().colors

        self.setObjectName("stat_card")
        self.setMinimumSize(200, 140)
        self.setMaximumHeight(160)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        accent = self._color or colors.accent

        self.setStyleSheet(
            f"""
            #stat_card {{
                background-color: {colors.bg_card_default};
                border: 1px solid {colors.stroke_surface};
                border-radius: 12px;
            }}
            #stat_card:hover {{
                background-color: {colors.bg_card_secondary};
                border-color: {accent};
            }}
        """
        )

        # Shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.setGraphicsEffect(shadow)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # Header row (icon + title)
        header = QHBoxLayout()
        header.setSpacing(10)

        # Icon
        if self._icon:
            icon_container = QWidget()
            icon_container.setFixedSize(36, 36)
            icon_container.setStyleSheet(
                f"""
                background-color: {accent}20;
                border-radius: 8px;
            """
            )
            icon_layout = QVBoxLayout(icon_container)
            icon_layout.setContentsMargins(0, 0, 0, 0)

            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setStyleSheet(
                f"""
                font-family: 'Segoe Fluent Icons';
                font-size: 16px;
                color: {accent};
            """
            )
            icon_label.setText(self._icon)
            icon_layout.addWidget(icon_label)

            header.addWidget(icon_container)

        # Title
        title_label = QLabel(self._title)
        title_label.setStyleSheet(
            f"""
            color: {colors.text_secondary};
            font-size: 13px;
            font-weight: 500;
        """
        )
        header.addWidget(title_label)
        header.addStretch()

        layout.addLayout(header)

        # Value
        self._value_label = QLabel("0")
        self._value_label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 36px;
            font-weight: 600;
        """
        )
        layout.addWidget(self._value_label)

        # Trend
        if self._trend != 0:
            trend_layout = QHBoxLayout()
            trend_layout.setSpacing(4)

            trend_icon = "\ue70e" if self._trend > 0 else "\ue70d"  # Up/Down arrows
            trend_color = colors.success if self._trend > 0 else colors.error

            trend_icon_label = QLabel(trend_icon)
            trend_icon_label.setStyleSheet(
                f"""
                font-family: 'Segoe Fluent Icons';
                font-size: 12px;
                color: {trend_color};
            """
            )
            trend_layout.addWidget(trend_icon_label)

            trend_value = QLabel(f"{abs(self._trend):.1f}%")
            trend_value.setStyleSheet(
                f"""
                color: {trend_color};
                font-size: 12px;
                font-weight: 500;
            """
            )
            trend_layout.addWidget(trend_value)

            if self._trend_label:
                trend_text = QLabel(self._trend_label)
                trend_text.setStyleSheet(
                    f"""
                    color: {colors.text_tertiary};
                    font-size: 12px;
                """
                )
                trend_layout.addWidget(trend_text)

            trend_layout.addStretch()
            layout.addLayout(trend_layout)
        else:
            layout.addStretch()

    def _setup_animation(self):
        """Setup number animation"""
        self._anim = QPropertyAnimation(self, b"animated_value")
        self._anim.setDuration(1000)
        self._anim.setEasingCurve(FluentEasing.ease_out_expo())

    def _get_animated_value(self) -> float:
        return self._current_value

    def _set_animated_value(self, value: float):
        self._current_value = value
        self._value_label.setText(f"{int(value):,}")

    animated_value = Property(float, _get_animated_value, _set_animated_value)

    def animate_to(self, value: int):
        """Animate to new value"""
        self._target_value = value
        self._anim.stop()
        self._anim.setStartValue(self._current_value)
        self._anim.setEndValue(float(value))
        self._anim.start()

    def set_value(self, value: int, animate: bool = True):
        """Set card value"""
        if animate:
            self.animate_to(value)
        else:
            self._current_value = float(value)
            self._value_label.setText(f"{value:,}")

    def enterEvent(self, event):
        self._hovered = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# CIRCULAR PROGRESS CHART
# مخطط تقدم دائري
# ═══════════════════════════════════════════════════════════════════════════════


class CircularProgressChart(QWidget):
    """
    Circular progress chart with animation.
    مخطط تقدم دائري متحرك
    """

    def __init__(
        self, title: str = "", value: float = 0, max_value: float = 100, size: int = 120, color: str = None, parent=None
    ):
        super().__init__(parent)

        self._title = title
        self._target_value = value
        self._current_value = 0.0
        self._max_value = max_value
        self._size = size
        self._color = color

        self.setFixedSize(size + 80, size + 60)
        self._setup_animation()

        # Delay animation start
        QTimer.singleShot(100, lambda: self.animate_to(value))

    def _setup_animation(self):
        """Setup progress animation"""
        self._anim = QPropertyAnimation(self, b"progress_value")
        self._anim.setDuration(1200)
        self._anim.setEasingCurve(FluentEasing.ease_out_expo())

    def _get_progress_value(self) -> float:
        return self._current_value

    def _set_progress_value(self, value: float):
        self._current_value = value
        self.update()

    progress_value = Property(float, _get_progress_value, _set_progress_value)

    def animate_to(self, value: float):
        """Animate to new value"""
        self._target_value = value
        self._anim.stop()
        self._anim.setStartValue(self._current_value)
        self._anim.setEndValue(value)
        self._anim.start()

    def paintEvent(self, event):
        """Paint circular progress"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = FluentDesignSystem().colors
        accent = self._color or colors.accent

        # Center position
        center_x = self.width() // 2
        center_y = (self.height() - 30) // 2
        radius = self._size // 2 - 10
        thickness = 10

        # Background circle
        rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)

        pen = QPen(QColor(colors.stroke_control))
        pen.setWidth(thickness)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(rect)

        # Progress arc
        progress = self._current_value / self._max_value if self._max_value > 0 else 0
        span_angle = int(progress * 360 * 16)

        # Gradient for progress
        gradient = QConicalGradient(center_x, center_y, 90)
        gradient.setColorAt(0, QColor(accent))
        gradient.setColorAt(1, QColor(colors.accent_light_1))

        pen = QPen(QBrush(gradient), thickness)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, -span_angle)

        # Center text (percentage)
        percentage = int(progress * 100)
        painter.setPen(QColor(colors.text_primary))
        font = QFont("Segoe UI", 24, QFont.DemiBold)
        painter.setFont(font)
        painter.drawText(QRectF(center_x - 40, center_y - 20, 80, 40), Qt.AlignCenter, f"{percentage}%")

        # Title below
        if self._title:
            painter.setPen(QColor(colors.text_secondary))
            font = QFont("Segoe UI", 12)
            painter.setFont(font)
            painter.drawText(QRectF(0, self.height() - 30, self.width(), 24), Qt.AlignCenter, self._title)

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════════
# LINE CHART
# مخطط خطي
# ═══════════════════════════════════════════════════════════════════════════════


class LineChart(QWidget):
    """
    Animated line chart with gradient fill.
    مخطط خطي متحرك مع تعبئة متدرجة
    """

    def __init__(self, title: str = "", data: List[float] = None, color: str = None, parent=None):
        super().__init__(parent)

        self._title = title
        self._data = data or []
        self._color = color
        self._animation_progress = 0.0

        self.setMinimumHeight(150)
        self._setup_animation()

    def _setup_animation(self):
        """Setup line draw animation"""
        self._anim = QPropertyAnimation(self, b"draw_progress")
        self._anim.setDuration(1500)
        self._anim.setEasingCurve(FluentEasing.ease_out_expo())

    def _get_draw_progress(self) -> float:
        return self._animation_progress

    def _set_draw_progress(self, value: float):
        self._animation_progress = value
        self.update()

    draw_progress = Property(float, _get_draw_progress, _set_draw_progress)

    def set_data(self, data: List[float], animate: bool = True):
        """Set chart data"""
        self._data = data
        if animate:
            self._anim.stop()
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        else:
            self._animation_progress = 1.0
            self.update()

    def paintEvent(self, event):
        """Paint line chart"""
        if not self._data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = FluentDesignSystem().colors
        accent = self._color or colors.accent

        # Chart area
        margin = 10
        chart_rect = QRectF(
            margin, margin + 20, self.width() - 2 * margin, self.height() - 2 * margin - 20  # Space for title
        )

        # Title
        if self._title:
            painter.setPen(QColor(colors.text_secondary))
            font = QFont("Segoe UI", 12, QFont.DemiBold)
            painter.setFont(font)
            painter.drawText(QRectF(margin, 0, chart_rect.width(), 24), Qt.AlignLeft | Qt.AlignVCenter, self._title)

        # Calculate points
        max_val = max(self._data) if self._data else 1
        min_val = min(self._data) if self._data else 0
        val_range = max_val - min_val if max_val != min_val else 1

        points = []
        for i, val in enumerate(self._data):
            x = chart_rect.left() + (i / (len(self._data) - 1)) * chart_rect.width()
            y = chart_rect.bottom() - ((val - min_val) / val_range) * chart_rect.height()
            points.append(QPointF(x, y))

        if len(points) < 2:
            return

        # Apply animation (draw only part of the line)
        num_points = max(2, int(len(points) * self._animation_progress))
        animated_points = points[:num_points]

        # Create path for line
        line_path = QPainterPath()
        line_path.moveTo(animated_points[0])
        for point in animated_points[1:]:
            line_path.lineTo(point)

        # Draw gradient fill
        fill_path = QPainterPath(line_path)
        fill_path.lineTo(animated_points[-1].x(), chart_rect.bottom())
        fill_path.lineTo(animated_points[0].x(), chart_rect.bottom())
        fill_path.closeSubpath()

        gradient = QLinearGradient(0, chart_rect.top(), 0, chart_rect.bottom())
        gradient.setColorAt(0, QColor(accent + "40"))
        gradient.setColorAt(1, QColor(accent + "00"))
        painter.fillPath(fill_path, gradient)

        # Draw line
        pen = QPen(QColor(accent))
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(line_path)

        # Draw points
        painter.setBrush(QColor(accent))
        for point in animated_points:
            painter.drawEllipse(point, 3, 3)

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVITY ITEM
# عنصر النشاط
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ActivityItemData:
    """Activity item data"""

    icon: str
    title: str
    description: str
    time: str
    type: str = "info"  # info, success, warning, error


class ActivityItem(QFrame):
    """Single activity feed item"""

    def __init__(self, data: ActivityItemData, parent=None):
        super().__init__(parent)

        self._data = data
        self._setup_ui()

    def _setup_ui(self):
        """Setup activity item UI"""
        colors = FluentDesignSystem().colors

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: transparent;
                border-radius: 8px;
                padding: 8px;
            }}
            QFrame:hover {{
                background-color: {colors.fill_subtle};
            }}
        """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # Type colors
        type_colors = {
            "info": colors.info,
            "success": colors.success,
            "warning": colors.warning,
            "error": colors.error,
        }
        accent = type_colors.get(self._data.type, colors.info)

        # Icon
        icon_container = QWidget()
        icon_container.setFixedSize(32, 32)
        icon_container.setStyleSheet(
            f"""
            background-color: {accent}20;
            border-radius: 6px;
        """
        )

        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            f"""
            font-family: 'Segoe Fluent Icons';
            font-size: 14px;
            color: {accent};
        """
        )
        icon_label.setText(self._data.icon)
        icon_layout.addWidget(icon_label)

        layout.addWidget(icon_container)

        # Content
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)

        title = QLabel(self._data.title)
        title.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 13px;
            font-weight: 500;
        """
        )
        content_layout.addWidget(title)

        description = QLabel(self._data.description)
        description.setStyleSheet(
            f"""
            color: {colors.text_secondary};
            font-size: 12px;
        """
        )
        content_layout.addWidget(description)

        layout.addLayout(content_layout, 1)

        # Time
        time_label = QLabel(self._data.time)
        time_label.setStyleSheet(
            f"""
            color: {colors.text_tertiary};
            font-size: 11px;
        """
        )
        layout.addWidget(time_label)


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVITY FEED
# تغذية النشاط
# ═══════════════════════════════════════════════════════════════════════════════


class ActivityFeed(FluentCard):
    """
    Activity feed card.
    بطاقة تغذية النشاط
    """

    def __init__(self, parent=None):
        super().__init__(title="Recent Activity", parent=parent)

        self._activities: List[ActivityItem] = []
        self._setup_content()

    def _setup_content(self):
        """Setup feed content"""
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent;")

        self._container = QWidget()
        self._feed_layout = QVBoxLayout(self._container)
        self._feed_layout.setContentsMargins(0, 0, 0, 0)
        self._feed_layout.setSpacing(4)
        self._feed_layout.addStretch()

        self._scroll.setWidget(self._container)
        self.add_content(self._scroll)

    def add_activity(self, data: ActivityItemData):
        """Add activity item"""
        item = ActivityItem(data)
        self._activities.insert(0, item)
        self._feed_layout.insertWidget(0, item)

        # Keep max 20 items
        while len(self._activities) > 20:
            old_item = self._activities.pop()
            old_item.deleteLater()

    def clear(self):
        """Clear all activities"""
        for item in self._activities:
            item.deleteLater()
        self._activities.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM HEALTH CARD
# بطاقة صحة النظام
# ═══════════════════════════════════════════════════════════════════════════════


class SystemHealthCard(FluentCard):
    """
    System health overview card.
    بطاقة نظرة عامة على صحة النظام
    """

    def __init__(self, parent=None):
        super().__init__(title="System Health", parent=parent)

        self._setup_content()

    def _setup_content(self):
        """Setup health content"""
        colors = FluentDesignSystem().colors

        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(20)

        # CPU
        self._cpu_chart = CircularProgressChart("CPU", 0, 100, 80, colors.accent)
        layout.addWidget(self._cpu_chart)

        # Memory
        self._memory_chart = CircularProgressChart("Memory", 0, 100, 80, colors.success)
        layout.addWidget(self._memory_chart)

        # Disk
        self._disk_chart = CircularProgressChart("Disk", 0, 100, 80, colors.warning)
        layout.addWidget(self._disk_chart)

        layout.addStretch()
        self.add_content(content)

    def update_metrics(self, cpu: float, memory: float, disk: float):
        """Update health metrics"""
        self._cpu_chart.animate_to(cpu)
        self._memory_chart.animate_to(memory)
        self._disk_chart.animate_to(disk)


# ═══════════════════════════════════════════════════════════════════════════════
# FLUENT DASHBOARD VIEW
# عرض لوحة القيادة بتصميم Fluent
# ═══════════════════════════════════════════════════════════════════════════════


class FluentDashboard(QWidget):
    """
    Complete Fluent Design dashboard view.
    عرض لوحة القيادة الكامل بتصميم Fluent
    """

    job_clicked = Signal(str)
    worker_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self):
        """Setup dashboard UI"""
        colors = FluentDesignSystem().colors

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background: {colors.bg_mica_base};")

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(24)

        # Header
        header = QLabel("Dashboard")
        header.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 28px;
            font-weight: 600;
        """
        )
        main_layout.addWidget(header)

        # Stats cards row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)

        self._jobs_card = AnimatedStatCard(
            "Active Jobs", 0, icon=FluentIcons.JOBS, trend=12.5, trend_label="vs last week", color=colors.accent
        )
        stats_layout.addWidget(self._jobs_card)

        self._workers_card = AnimatedStatCard(
            "Workers", 0, icon=FluentIcons.WORKERS, trend=5.2, trend_label="vs last week", color=colors.success
        )
        stats_layout.addWidget(self._workers_card)

        self._pending_card = AnimatedStatCard(
            "Pending", 0, icon="\ue823", trend=-8.3, trend_label="vs last week", color=colors.warning  # Clock icon
        )
        stats_layout.addWidget(self._pending_card)

        self._failed_card = AnimatedStatCard(
            "Failed", 0, icon=FluentIcons.ERROR, trend=-15.0, trend_label="vs last week", color=colors.error
        )
        stats_layout.addWidget(self._failed_card)

        stats_layout.addStretch()
        main_layout.addLayout(stats_layout)

        # Charts row
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(16)

        # Jobs chart
        jobs_chart_card = FluentCard(title="Jobs Over Time")
        self._jobs_chart = LineChart(color=colors.accent)
        jobs_chart_card.add_content(self._jobs_chart)
        charts_layout.addWidget(jobs_chart_card, 2)

        # System health
        self._health_card = SystemHealthCard()
        charts_layout.addWidget(self._health_card, 1)

        main_layout.addLayout(charts_layout)

        # Activity feed
        self._activity_feed = ActivityFeed()
        self._activity_feed.setMaximumHeight(300)
        main_layout.addWidget(self._activity_feed)

        main_layout.addStretch()

        scroll.setWidget(container)

        # Set scroll as main widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def update_stats(self, jobs: int, workers: int, pending: int, failed: int):
        """Update dashboard statistics"""
        self._jobs_card.set_value(jobs)
        self._workers_card.set_value(workers)
        self._pending_card.set_value(pending)
        self._failed_card.set_value(failed)

    def update_chart(self, data: List[float]):
        """Update jobs chart"""
        self._jobs_chart.set_data(data)

    def update_health(self, cpu: float, memory: float, disk: float):
        """Update system health"""
        self._health_card.update_metrics(cpu, memory, disk)

    def add_activity(self, icon: str, title: str, description: str, time: str, type: str = "info"):
        """Add activity to feed"""
        self._activity_feed.add_activity(
            ActivityItemData(icon=icon, title=title, description=description, time=time, type=type)
        )
