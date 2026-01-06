"""
Cluster Overview - Visual cluster status page
صفحة عرض حالة الكلاستر البصرية

Features:
- Visual cluster representation (Nodes around Master)
- Circular resource gauges
- Cluster health card
- Quick stats
- Recent events
"""

import math
from typing import Optional, List, Dict, Any
from datetime import datetime

from PySide6.QtCore import Signal, Qt, QTimer, QPointF, QRectF, Property, QPropertyAnimation
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QLinearGradient,
    QRadialGradient, QPainterPath, QFontMetrics
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QFrame,
    QGridLayout,
    QScrollArea,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)

from ..api.client import APIClient
from ..resources.styles import COLORS


class CircularGauge(QWidget):
    """Circular gauge widget for resource visualization"""

    def __init__(self, title: str, value: float = 0, max_value: float = 100,
                 color: str = None, unit: str = "%", parent=None):
        super().__init__(parent)
        self._title = title
        self._value = value
        self._max_value = max_value
        self._color = color or COLORS.get('primary', '#3b82f6')
        self._unit = unit
        self._animated_value = 0

        self.setMinimumSize(120, 150)
        self.setMaximumSize(150, 180)

    def set_value(self, value: float, animate: bool = True):
        """Set gauge value with optional animation"""
        self._value = min(value, self._max_value)
        if animate:
            self._animate_value()
        else:
            self._animated_value = self._value
            self.update()

    def _animate_value(self):
        """Animate value change"""
        # Simple animation without QPropertyAnimation for gauge value
        self._animated_value = self._value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        size = min(width, height - 30)
        center_x = width / 2
        center_y = (height - 30) / 2

        # Draw background arc
        pen = QPen(QColor(COLORS.get('bg_medium', '#1e293b')))
        pen.setWidth(10)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        rect = QRectF(center_x - size/2 + 10, center_y - size/2 + 10,
                      size - 20, size - 20)
        painter.drawArc(rect, 225 * 16, -270 * 16)

        # Draw value arc
        percent = self._animated_value / self._max_value if self._max_value > 0 else 0
        color = QColor(self._color)

        # Gradient based on value
        if percent > 0.8:
            color = QColor(COLORS.get('danger', '#ef4444'))
        elif percent > 0.6:
            color = QColor(COLORS.get('warning', '#f59e0b'))

        pen = QPen(color)
        pen.setWidth(10)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        span_angle = int(-270 * percent * 16)
        painter.drawArc(rect, 225 * 16, span_angle)

        # Draw center value
        painter.setPen(QColor(COLORS.get('text_primary', '#f1f5f9')))
        font = QFont()
        font.setPixelSize(24)
        font.setBold(True)
        painter.setFont(font)

        value_text = f"{self._animated_value:.0f}{self._unit}"
        text_rect = QRectF(center_x - size/2, center_y - 15, size, 30)
        painter.drawText(text_rect, Qt.AlignCenter, value_text)

        # Draw title below gauge
        painter.setPen(QColor(COLORS.get('text_secondary', '#94a3b8')))
        font.setPixelSize(12)
        font.setBold(False)
        painter.setFont(font)

        title_rect = QRectF(0, height - 25, width, 20)
        painter.drawText(title_rect, Qt.AlignCenter, self._title)


class NodeWidget(QWidget):
    """Visual representation of a cluster node"""

    clicked = Signal(dict)

    def __init__(self, node_data: dict, is_master: bool = False, parent=None):
        super().__init__(parent)
        self.node_data = node_data
        self.is_master = is_master
        self._hovered = False

        size = 80 if is_master else 60
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        size = self.width()
        center = size / 2

        # Determine status color
        status = self.node_data.get("status", "unknown")
        status_colors = {
            "active": COLORS.get('success', '#10b981'),
            "idle": COLORS.get('info', '#3b82f6'),
            "busy": COLORS.get('warning', '#f59e0b'),
            "offline": COLORS.get('danger', '#ef4444'),
            "draining": COLORS.get('warning', '#f59e0b'),
        }
        node_color = QColor(status_colors.get(status, COLORS.get('text_secondary', '#94a3b8')))

        # Draw glow effect when hovered
        if self._hovered:
            glow = QRadialGradient(center, center, size/2)
            glow.setColorAt(0, QColor(node_color.red(), node_color.green(), node_color.blue(), 100))
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(0, 0, size, size))

        # Draw outer ring
        pen = QPen(node_color)
        pen.setWidth(3 if self.is_master else 2)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(COLORS.get('bg_dark', '#0f172a'))))

        margin = 5
        painter.drawEllipse(QRectF(margin, margin, size - margin*2, size - margin*2))

        # Draw inner circle
        inner_margin = 12 if self.is_master else 10
        painter.setBrush(QBrush(node_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(inner_margin, inner_margin,
                                   size - inner_margin*2, size - inner_margin*2))

        # Draw icon/label
        painter.setPen(QColor("white"))
        font = QFont()
        font.setPixelSize(14 if self.is_master else 10)
        font.setBold(True)
        painter.setFont(font)

        icon = "M" if self.is_master else "W"
        text_rect = QRectF(0, 0, size, size)
        painter.drawText(text_rect, Qt.AlignCenter, icon)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.node_data)


class ClusterVisualization(QWidget):
    """Visual cluster topology widget"""

    node_clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._master_data: Optional[Dict] = None
        self._workers_data: List[Dict] = []
        self._node_widgets: List[NodeWidget] = []

        self.setMinimumSize(400, 400)

    def set_cluster_data(self, master: dict, workers: list):
        """Update cluster data and refresh visualization"""
        self._master_data = master
        self._workers_data = workers
        self._rebuild_visualization()

    def _rebuild_visualization(self):
        """Rebuild the visual cluster representation"""
        # Remove existing widgets
        for widget in self._node_widgets:
            widget.deleteLater()
        self._node_widgets.clear()

        if not self._master_data:
            return

        center_x = self.width() / 2
        center_y = self.height() / 2
        radius = min(self.width(), self.height()) / 2 - 60

        # Create master node at center
        master_widget = NodeWidget(self._master_data, is_master=True, parent=self)
        master_widget.move(int(center_x - 40), int(center_y - 40))
        master_widget.clicked.connect(self.node_clicked.emit)
        master_widget.show()
        self._node_widgets.append(master_widget)

        # Create worker nodes in a circle around master
        num_workers = len(self._workers_data)
        if num_workers > 0:
            angle_step = 2 * math.pi / num_workers

            for i, worker in enumerate(self._workers_data):
                angle = i * angle_step - math.pi / 2  # Start from top
                x = center_x + radius * math.cos(angle) - 30
                y = center_y + radius * math.sin(angle) - 30

                worker_widget = NodeWidget(worker, is_master=False, parent=self)
                worker_widget.move(int(x), int(y))
                worker_widget.clicked.connect(self.node_clicked.emit)
                worker_widget.show()
                self._node_widgets.append(worker_widget)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self._master_data or not self._workers_data:
            # Draw empty state
            painter.setPen(QColor(COLORS.get('text_secondary', '#94a3b8')))
            font = QFont()
            font.setPixelSize(14)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter,
                           "No cluster data available\nConnect to a master server")
            return

        center_x = self.width() / 2
        center_y = self.height() / 2

        # Draw connection lines from master to workers
        pen = QPen(QColor(COLORS.get('border', '#334155')))
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)

        for i, widget in enumerate(self._node_widgets[1:]):  # Skip master
            worker_center = widget.geometry().center()
            painter.drawLine(QPointF(center_x, center_y),
                           QPointF(worker_center.x(), worker_center.y()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild_visualization()


class HealthCard(QFrame):
    """Cluster health status card"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("health_card")
        self._setup_ui()
        self._setup_shadow()

    def _setup_shadow(self):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QFrame#health_card {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 16px;
                padding: 20px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("Cluster Health")
        title.setStyleSheet(f"""
            font-size: 16px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.health_badge = QLabel("HEALTHY")
        self.health_badge.setStyleSheet(f"""
            background-color: {COLORS.get('success', '#10b981')}20;
            color: {COLORS.get('success', '#10b981')};
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        header_layout.addWidget(self.health_badge)

        layout.addLayout(header_layout)

        # Health indicators
        indicators_layout = QGridLayout()
        indicators_layout.setSpacing(12)

        self.indicators = {}
        indicator_items = [
            ("master", "Master Node", "✓"),
            ("workers", "Worker Nodes", "0/0"),
            ("scheduler", "Scheduler", "✓"),
            ("api", "API Server", "✓"),
        ]

        for i, (key, label, default) in enumerate(indicator_items):
            row = i // 2
            col = i % 2

            indicator = self._create_indicator(label, default, True)
            indicators_layout.addWidget(indicator, row, col)
            self.indicators[key] = indicator

        layout.addLayout(indicators_layout)

    def _create_indicator(self, label: str, value: str, is_healthy: bool) -> QWidget:
        """Create a health indicator widget"""
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS.get('bg_dark', '#0f172a')};
                border-radius: 8px;
                padding: 8px;
            }}
        """)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 8, 12, 8)

        status_color = COLORS.get('success', '#10b981') if is_healthy else COLORS.get('danger', '#ef4444')

        status_dot = QLabel("●")
        status_dot.setStyleSheet(f"color: {status_color}; font-size: 10px;")
        layout.addWidget(status_dot)

        label_widget = QLabel(label)
        label_widget.setStyleSheet(f"""
            color: {COLORS.get('text_secondary', '#94a3b8')};
            font-size: 12px;
        """)
        layout.addWidget(label_widget)
        layout.addStretch()

        value_widget = QLabel(value)
        value_widget.setStyleSheet(f"""
            color: {COLORS.get('text_primary', '#f1f5f9')};
            font-size: 12px;
            font-weight: 500;
        """)
        layout.addWidget(value_widget)

        container.value_widget = value_widget
        container.status_dot = status_dot
        return container

    def update_health(self, health_data: dict):
        """Update health display"""
        overall_health = health_data.get("status", "unknown")

        # Update badge
        if overall_health == "healthy":
            self.health_badge.setText("HEALTHY")
            self.health_badge.setStyleSheet(f"""
                background-color: {COLORS.get('success', '#10b981')}20;
                color: {COLORS.get('success', '#10b981')};
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
            """)
        elif overall_health == "degraded":
            self.health_badge.setText("DEGRADED")
            self.health_badge.setStyleSheet(f"""
                background-color: {COLORS.get('warning', '#f59e0b')}20;
                color: {COLORS.get('warning', '#f59e0b')};
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
            """)
        else:
            self.health_badge.setText("UNHEALTHY")
            self.health_badge.setStyleSheet(f"""
                background-color: {COLORS.get('danger', '#ef4444')}20;
                color: {COLORS.get('danger', '#ef4444')};
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
            """)

        # Update individual indicators
        components = health_data.get("components", {})

        for key, indicator in self.indicators.items():
            component = components.get(key, {})
            is_healthy = component.get("status") == "healthy"
            value = component.get("value", "N/A")

            status_color = COLORS.get('success', '#10b981') if is_healthy else COLORS.get('danger', '#ef4444')
            indicator.status_dot.setStyleSheet(f"color: {status_color}; font-size: 10px;")
            indicator.value_widget.setText(str(value))


class EventCard(QFrame):
    """Recent events card"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("event_card")
        self._events: List[Dict] = []
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QFrame#event_card {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 16px;
                padding: 16px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("Recent Events")
        title.setStyleSheet(f"""
            font-size: 16px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Events container
        self.events_layout = QVBoxLayout()
        self.events_layout.setSpacing(8)
        layout.addLayout(self.events_layout)

        # Placeholder
        self.placeholder = QLabel("No recent events")
        self.placeholder.setStyleSheet(f"""
            color: {COLORS.get('text_secondary', '#94a3b8')};
            font-size: 13px;
            padding: 20px;
        """)
        self.placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.placeholder)

        layout.addStretch()

    def set_events(self, events: list):
        """Update events list"""
        self._events = events

        # Clear existing events
        while self.events_layout.count():
            item = self.events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not events:
            self.placeholder.show()
            return

        self.placeholder.hide()

        # Add event items (max 5)
        for event in events[:5]:
            event_widget = self._create_event_item(event)
            self.events_layout.addWidget(event_widget)

    def _create_event_item(self, event: dict) -> QWidget:
        """Create an event item widget"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 4, 0, 4)

        # Event type icon
        event_type = event.get("type", "info")
        type_icons = {
            "info": ("ℹ️", COLORS.get('info', '#3b82f6')),
            "success": ("✅", COLORS.get('success', '#10b981')),
            "warning": ("⚠️", COLORS.get('warning', '#f59e0b')),
            "error": ("❌", COLORS.get('danger', '#ef4444')),
        }
        icon, color = type_icons.get(event_type, ("●", COLORS.get('text_secondary', '#94a3b8')))

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(icon_label)

        # Event message
        message = event.get("message", "Unknown event")
        message_label = QLabel(message)
        message_label.setStyleSheet(f"""
            color: {COLORS.get('text_primary', '#f1f5f9')};
            font-size: 12px;
        """)
        message_label.setWordWrap(True)
        layout.addWidget(message_label, 1)

        # Timestamp
        timestamp = event.get("timestamp", "")
        if timestamp:
            time_label = QLabel(timestamp)
            time_label.setStyleSheet(f"""
                color: {COLORS.get('text_secondary', '#94a3b8')};
                font-size: 11px;
            """)
            layout.addWidget(time_label)

        return container


class QuickStatCard(QFrame):
    """Quick stat display card"""

    def __init__(self, title: str, value: str, icon: str, color: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("quick_stat")
        self._color = color or COLORS.get('primary', '#3b82f6')
        self._setup_ui(title, value, icon)

    def _setup_ui(self, title: str, value: str, icon: str):
        self.setStyleSheet(f"""
            QFrame#quick_stat {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 12px;
                padding: 16px;
            }}
            QFrame#quick_stat:hover {{
                border-color: {self._color};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setSpacing(12)

        # Icon
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 28px;")
        layout.addWidget(icon_label)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"""
            font-size: 20px;
            font-weight: 700;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        text_layout.addWidget(self.value_label)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            font-size: 12px;
            color: {COLORS.get('text_secondary', '#94a3b8')};
        """)
        text_layout.addWidget(title_label)

        layout.addLayout(text_layout)
        layout.addStretch()

    def set_value(self, value: str):
        self.value_label.setText(value)


class ClusterOverviewView(QWidget):
    """Cluster overview page with visual representation"""

    refresh_requested = Signal()

    AUTO_REFRESH_INTERVAL = 10000  # 10 seconds

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._setup_ui()
        self._setup_auto_refresh()

    def _setup_ui(self):
        """Setup the cluster overview UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        self._setup_header(layout)

        # Main content area
        content_layout = QHBoxLayout()
        content_layout.setSpacing(24)

        # Left column - Cluster visualization
        left_column = QVBoxLayout()

        # Cluster visualization
        viz_container = QFrame()
        viz_container.setObjectName("viz_container")
        viz_container.setStyleSheet(f"""
            QFrame#viz_container {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 16px;
            }}
        """)

        viz_layout = QVBoxLayout(viz_container)
        viz_layout.setContentsMargins(16, 16, 16, 16)

        viz_title = QLabel("Cluster Topology")
        viz_title.setStyleSheet(f"""
            font-size: 16px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        viz_layout.addWidget(viz_title)

        self.cluster_viz = ClusterVisualization()
        self.cluster_viz.node_clicked.connect(self._on_node_clicked)
        viz_layout.addWidget(self.cluster_viz, 1)

        left_column.addWidget(viz_container, 1)

        # Resource gauges
        gauges_layout = QHBoxLayout()
        gauges_layout.setSpacing(16)

        self.cpu_gauge = CircularGauge("CPU Usage", 0, 100, COLORS.get('primary', '#3b82f6'))
        gauges_layout.addWidget(self.cpu_gauge)

        self.memory_gauge = CircularGauge("Memory", 0, 100, COLORS.get('success', '#10b981'))
        gauges_layout.addWidget(self.memory_gauge)

        self.disk_gauge = CircularGauge("Disk", 0, 100, COLORS.get('warning', '#f59e0b'))
        gauges_layout.addWidget(self.disk_gauge)

        self.network_gauge = CircularGauge("Network", 0, 100, COLORS.get('info', '#3b82f6'), "Mbps")
        gauges_layout.addWidget(self.network_gauge)

        left_column.addLayout(gauges_layout)

        content_layout.addLayout(left_column, 2)

        # Right column - Health and events
        right_column = QVBoxLayout()
        right_column.setSpacing(16)

        # Quick stats
        stats_layout = QGridLayout()
        stats_layout.setSpacing(12)

        self.workers_stat = QuickStatCard("Active Workers", "0", "👥", COLORS.get('primary', '#3b82f6'))
        stats_layout.addWidget(self.workers_stat, 0, 0)

        self.jobs_stat = QuickStatCard("Running Jobs", "0", "⚡", COLORS.get('success', '#10b981'))
        stats_layout.addWidget(self.jobs_stat, 0, 1)

        self.queued_stat = QuickStatCard("Queued Jobs", "0", "⏳", COLORS.get('warning', '#f59e0b'))
        stats_layout.addWidget(self.queued_stat, 1, 0)

        self.uptime_stat = QuickStatCard("Uptime", "0h", "⏱️", COLORS.get('info', '#3b82f6'))
        stats_layout.addWidget(self.uptime_stat, 1, 1)

        right_column.addLayout(stats_layout)

        # Health card
        self.health_card = HealthCard()
        right_column.addWidget(self.health_card)

        # Events card
        self.events_card = EventCard()
        right_column.addWidget(self.events_card, 1)

        content_layout.addLayout(right_column, 1)

        layout.addLayout(content_layout, 1)

    def _setup_header(self, parent_layout: QVBoxLayout):
        """Setup header"""
        header_layout = QHBoxLayout()

        title = QLabel("Cluster Overview")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 600;
            color: {COLORS.get('text_primary', '#f1f5f9')};
        """)
        header_layout.addWidget(title)

        subtitle = QLabel("Real-time cluster status and monitoring")
        subtitle.setStyleSheet(f"color: {COLORS.get('text_secondary', '#94a3b8')}; margin-left: 16px;")
        header_layout.addWidget(subtitle)

        header_layout.addStretch()

        # Last updated
        self.last_updated_label = QLabel("Last updated: --")
        self.last_updated_label.setStyleSheet(f"""
            color: {COLORS.get('text_secondary', '#94a3b8')};
            font-size: 12px;
        """)
        header_layout.addWidget(self.last_updated_label)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS.get('bg_medium', '#1e293b')};
                border: 1px solid {COLORS.get('border', '#334155')};
                border-radius: 8px;
                padding: 8px 16px;
                color: {COLORS.get('text_primary', '#f1f5f9')};
            }}
            QPushButton:hover {{
                background-color: {COLORS.get('bg_light', '#273548')};
            }}
        """)
        refresh_btn.clicked.connect(self._on_refresh)
        header_layout.addWidget(refresh_btn)

        parent_layout.addLayout(header_layout)

    def _setup_auto_refresh(self):
        """Setup auto-refresh timer"""
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_refresh)
        self.refresh_timer.start(self.AUTO_REFRESH_INTERVAL)

    def set_cluster_data(self, data: dict):
        """Update all cluster data"""
        # Update timestamp
        now = datetime.now().strftime("%H:%M:%S")
        self.last_updated_label.setText(f"Last updated: {now}")

        # Update cluster visualization
        master = data.get("master", {"name": "Master", "status": "active"})
        workers = data.get("workers", [])
        self.cluster_viz.set_cluster_data(master, workers)

        # Update resource gauges
        resources = data.get("resources", {})
        self.cpu_gauge.set_value(resources.get("cpu", 0))
        self.memory_gauge.set_value(resources.get("memory", 0))
        self.disk_gauge.set_value(resources.get("disk", 0))
        self.network_gauge.set_value(resources.get("network", 0))

        # Update quick stats
        stats = data.get("stats", {})
        self.workers_stat.set_value(str(stats.get("active_workers", 0)))
        self.jobs_stat.set_value(str(stats.get("running_jobs", 0)))
        self.queued_stat.set_value(str(stats.get("queued_jobs", 0)))
        self.uptime_stat.set_value(stats.get("uptime", "0h"))

        # Update health
        health = data.get("health", {"status": "healthy", "components": {}})
        self.health_card.update_health(health)

        # Update events
        events = data.get("events", [])
        self.events_card.set_events(events)

    def _on_refresh(self):
        """Handle refresh"""
        self.refresh_requested.emit()

    def _on_node_clicked(self, node_data: dict):
        """Handle node click"""
        # Could show node details dialog
        pass

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client

    def showEvent(self, event):
        """Start auto-refresh when view is shown"""
        super().showEvent(event)
        if not self.refresh_timer.isActive():
            self.refresh_timer.start(self.AUTO_REFRESH_INTERVAL)

    def hideEvent(self, event):
        """Stop auto-refresh when view is hidden"""
        super().hideEvent(event)
        self.refresh_timer.stop()
