"""
Chart Widgets for Dashboard
ويدجت الرسوم البيانية للوحة التحكم
"""

from typing import List, Tuple
from collections import deque
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath, QLinearGradient, QFont
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget

from ..resources.styles import COLORS


class LineChart(QFrame):
    """Real-time line chart widget"""

    def __init__(
        self,
        title: str = "Chart",
        max_points: int = 60,
        min_value: float = 0,
        max_value: float = 100,
        unit: str = "%",
        color: str = None,
        parent=None
    ):
        super().__init__(parent)
        self._title = title
        self._max_points = max_points
        self._min_value = min_value
        self._max_value = max_value
        self._unit = unit
        self._color = QColor(color or COLORS["primary"])
        self._data: deque = deque(maxlen=max_points)
        self._current_value = 0

        self.setMinimumHeight(150)
        self.setStyleSheet(f"""
            background-color: {COLORS['bg_card']};
            border: 1px solid {COLORS['border']};
            border-radius: 12px;
        """)

    def add_value(self, value: float):
        """Add a new value to the chart"""
        self._data.append(value)
        self._current_value = value
        self.update()

    def set_data(self, data: List[float]):
        """Set chart data"""
        self._data.clear()
        for value in data[-self._max_points:]:
            self._data.append(value)
        if data:
            self._current_value = data[-1]
        self.update()

    def paintEvent(self, event):
        """Custom paint for chart"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        padding = 16
        chart_rect = QRectF(
            padding,
            padding + 30,  # Space for title
            rect.width() - padding * 2,
            rect.height() - padding * 2 - 30
        )

        # Draw title and current value
        painter.setPen(QColor(COLORS["text_primary"]))
        painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        painter.drawText(padding, padding + 16, self._title)

        # Current value
        value_text = f"{self._current_value:.1f}{self._unit}"
        painter.setFont(QFont("Segoe UI", 18, QFont.Bold))
        painter.setPen(self._color)
        value_rect = painter.fontMetrics().boundingRect(value_text)
        painter.drawText(
            int(rect.width() - padding - value_rect.width()),
            padding + 20,
            value_text
        )

        if len(self._data) < 2:
            return

        # Draw grid lines
        painter.setPen(QPen(QColor(COLORS["border"]), 1, Qt.DashLine))
        for i in range(5):
            y = chart_rect.top() + (chart_rect.height() / 4) * i
            painter.drawLine(
                QPointF(chart_rect.left(), y),
                QPointF(chart_rect.right(), y)
            )

        # Calculate points
        points = []
        data_list = list(self._data)
        for i, value in enumerate(data_list):
            x = chart_rect.left() + (chart_rect.width() / (self._max_points - 1)) * i
            normalized = (value - self._min_value) / (self._max_value - self._min_value)
            normalized = max(0, min(1, normalized))  # Clamp
            y = chart_rect.bottom() - (normalized * chart_rect.height())
            points.append(QPointF(x, y))

        # Draw gradient fill
        if points:
            gradient = QLinearGradient(0, chart_rect.top(), 0, chart_rect.bottom())
            gradient.setColorAt(0, QColor(self._color.red(), self._color.green(), self._color.blue(), 80))
            gradient.setColorAt(1, QColor(self._color.red(), self._color.green(), self._color.blue(), 10))

            fill_path = QPainterPath()
            fill_path.moveTo(QPointF(points[0].x(), chart_rect.bottom()))
            for point in points:
                fill_path.lineTo(point)
            fill_path.lineTo(QPointF(points[-1].x(), chart_rect.bottom()))
            fill_path.closeSubpath()

            painter.fillPath(fill_path, QBrush(gradient))

        # Draw line
        path = QPainterPath()
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)

        painter.setPen(QPen(self._color, 2))
        painter.drawPath(path)

        # Draw current point
        if points:
            painter.setBrush(QBrush(self._color))
            painter.setPen(QPen(QColor(COLORS["bg_card"]), 2))
            painter.drawEllipse(points[-1], 5, 5)


class DonutChart(QFrame):
    """Donut/Ring chart widget"""

    def __init__(
        self,
        title: str = "Chart",
        parent=None
    ):
        super().__init__(parent)
        self._title = title
        self._segments: List[Tuple[str, float, str]] = []  # (label, value, color)
        self._total = 0

        self.setMinimumSize(200, 200)
        self.setStyleSheet(f"""
            background-color: {COLORS['bg_card']};
            border: 1px solid {COLORS['border']};
            border-radius: 12px;
        """)

    def set_data(self, segments: List[Tuple[str, float, str]]):
        """Set chart segments: [(label, value, color), ...]"""
        self._segments = segments
        self._total = sum(s[1] for s in segments)
        self.update()

    def paintEvent(self, event):
        """Custom paint for donut chart"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        padding = 16

        # Draw title
        painter.setPen(QColor(COLORS["text_primary"]))
        painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        painter.drawText(padding, padding + 16, self._title)

        if not self._segments or self._total == 0:
            return

        # Chart area
        chart_size = min(rect.width(), rect.height() - 60) - padding * 2
        chart_rect = QRectF(
            (rect.width() - chart_size) / 2,
            40 + (rect.height() - 40 - chart_size) / 2,
            chart_size,
            chart_size
        )

        # Draw segments
        start_angle = 90 * 16  # Start from top (12 o'clock)
        for label, value, color in self._segments:
            span_angle = int((value / self._total) * 360 * 16)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(color)))
            painter.drawPie(chart_rect, start_angle, -span_angle)

            start_angle -= span_angle

        # Draw inner circle (donut hole)
        inner_size = chart_size * 0.6
        inner_rect = QRectF(
            chart_rect.center().x() - inner_size / 2,
            chart_rect.center().y() - inner_size / 2,
            inner_size,
            inner_size
        )
        painter.setBrush(QBrush(QColor(COLORS["bg_card"])))
        painter.drawEllipse(inner_rect)

        # Draw total in center
        painter.setPen(QColor(COLORS["text_primary"]))
        painter.setFont(QFont("Segoe UI", 16, QFont.Bold))
        total_text = str(int(self._total))
        text_rect = painter.fontMetrics().boundingRect(total_text)
        painter.drawText(
            int(chart_rect.center().x() - text_rect.width() / 2),
            int(chart_rect.center().y() + text_rect.height() / 4),
            total_text
        )

        # Label below
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor(COLORS["text_secondary"]))
        painter.drawText(
            int(chart_rect.center().x() - 20),
            int(chart_rect.center().y() + 20),
            "Total"
        )


class BarChart(QFrame):
    """Horizontal bar chart widget"""

    def __init__(
        self,
        title: str = "Chart",
        parent=None
    ):
        super().__init__(parent)
        self._title = title
        self._bars: List[Tuple[str, float, float, str]] = []  # (label, value, max_value, color)

        self.setMinimumHeight(150)
        self.setStyleSheet(f"""
            background-color: {COLORS['bg_card']};
            border: 1px solid {COLORS['border']};
            border-radius: 12px;
        """)

    def set_data(self, bars: List[Tuple[str, float, float, str]]):
        """Set bar data: [(label, value, max_value, color), ...]"""
        self._bars = bars
        self.update()

    def paintEvent(self, event):
        """Custom paint for bar chart"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        padding = 16

        # Draw title
        painter.setPen(QColor(COLORS["text_primary"]))
        painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        painter.drawText(padding, padding + 16, self._title)

        if not self._bars:
            return

        # Bar area
        bar_area_top = padding + 35
        bar_height = 24
        bar_spacing = 12
        label_width = 80
        value_width = 60

        for i, (label, value, max_value, color) in enumerate(self._bars):
            y = bar_area_top + i * (bar_height + bar_spacing)

            # Draw label
            painter.setPen(QColor(COLORS["text_secondary"]))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(
                padding,
                int(y + bar_height / 2 + 5),
                label
            )

            # Bar background
            bar_x = padding + label_width
            bar_width = rect.width() - padding * 2 - label_width - value_width

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(COLORS["bg_light"])))
            painter.drawRoundedRect(
                QRectF(bar_x, y, bar_width, bar_height),
                4, 4
            )

            # Bar fill
            if max_value > 0:
                fill_width = (value / max_value) * bar_width
                painter.setBrush(QBrush(QColor(color)))
                painter.drawRoundedRect(
                    QRectF(bar_x, y, fill_width, bar_height),
                    4, 4
                )

            # Draw value
            painter.setPen(QColor(COLORS["text_primary"]))
            painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
            value_text = f"{value:.0f}/{max_value:.0f}"
            painter.drawText(
                int(bar_x + bar_width + 8),
                int(y + bar_height / 2 + 5),
                value_text
            )


class MiniChart(QWidget):
    """Mini sparkline chart for compact displays"""

    def __init__(
        self,
        max_points: int = 20,
        color: str = None,
        parent=None
    ):
        super().__init__(parent)
        self._max_points = max_points
        self._color = QColor(color or COLORS["primary"])
        self._data: deque = deque(maxlen=max_points)

        self.setFixedHeight(40)
        self.setMinimumWidth(100)

    def add_value(self, value: float):
        """Add a new value"""
        self._data.append(value)
        self.update()

    def set_data(self, data: List[float]):
        """Set chart data"""
        self._data.clear()
        for value in data[-self._max_points:]:
            self._data.append(value)
        self.update()

    def paintEvent(self, event):
        """Paint sparkline"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()

        if len(self._data) < 2:
            return

        data_list = list(self._data)
        min_val = min(data_list)
        max_val = max(data_list)
        value_range = max_val - min_val or 1

        # Calculate points
        points = []
        for i, value in enumerate(data_list):
            x = (rect.width() / (self._max_points - 1)) * i
            normalized = (value - min_val) / value_range
            y = rect.height() - (normalized * rect.height() * 0.8) - rect.height() * 0.1
            points.append(QPointF(x, y))

        # Draw line
        path = QPainterPath()
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)

        painter.setPen(QPen(self._color, 2))
        painter.drawPath(path)
