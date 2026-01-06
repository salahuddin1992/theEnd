"""
Fluent Resource Pools View
صفحة مجموعات الموارد

Resource pool management with:
- Pool overview cards
- Resource allocation charts
- Pool configuration
- Worker assignment
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from ..components import ButtonVariant, FluentButton, FluentCard
from ..fluent_design import FluentDesignSystem

# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class PoolStatus(Enum):
    """Pool status"""

    ACTIVE = "Active"
    SCALING = "Scaling"
    DRAINING = "Draining"
    OFFLINE = "Offline"


@dataclass
class ResourcePool:
    """Resource pool definition"""

    id: str
    name: str
    description: str
    status: PoolStatus
    total_cpu: int
    used_cpu: int
    total_memory_gb: int
    used_memory_gb: int
    total_gpu: int
    used_gpu: int
    worker_count: int
    active_workers: int
    queued_jobs: int
    running_jobs: int
    priority: int
    auto_scale: bool
    min_workers: int
    max_workers: int


# ═══════════════════════════════════════════════════════════════════════════════
# RESOURCE GAUGE
# ═══════════════════════════════════════════════════════════════════════════════


class ResourceGauge(QWidget):
    """
    Circular gauge for resource usage.
    مقياس دائري لاستخدام الموارد
    """

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._value = 0
        self._max_value = 100
        self._unit = ""

        self.setFixedSize(100, 120)

    def set_value(self, value: float, max_value: float, unit: str = ""):
        """Set gauge value"""
        self._value = value
        self._max_value = max_value
        self._unit = unit
        self.update()

    def paintEvent(self, event):
        """Paint the gauge"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = FluentDesignSystem().colors

        # Calculate percentage
        percentage = (self._value / self._max_value * 100) if self._max_value > 0 else 0

        # Determine color based on usage
        if percentage > 90:
            gauge_color = QColor(colors.error)
        elif percentage > 70:
            gauge_color = QColor(colors.warning)
        else:
            gauge_color = QColor(colors.accent)

        # Draw background arc
        center_x = self.width() // 2
        center_y = 50
        radius = 40

        rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)

        bg_pen = QPen(QColor(colors.fill_control))
        bg_pen.setWidth(8)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 225 * 16, -270 * 16)

        # Draw value arc
        value_pen = QPen(gauge_color)
        value_pen.setWidth(8)
        value_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(value_pen)

        span = int(-270 * (percentage / 100) * 16)
        painter.drawArc(rect, 225 * 16, span)

        # Draw percentage text
        painter.setPen(QColor(colors.text_primary))
        painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        painter.drawText(
            QRectF(0, center_y - 15, self.width(), 30), Qt.AlignmentFlag.AlignCenter, f"{int(percentage)}%"
        )

        # Draw label
        painter.setPen(QColor(colors.text_secondary))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QRectF(0, 95, self.width(), 20), Qt.AlignmentFlag.AlignCenter, self._label)

        # Draw value info
        painter.setPen(QColor(colors.text_tertiary))
        painter.setFont(QFont("Segoe UI", 9))
        value_text = f"{self._value:.0f}/{self._max_value:.0f} {self._unit}"
        painter.drawText(QRectF(0, 108, self.width(), 15), Qt.AlignmentFlag.AlignCenter, value_text)


# ═══════════════════════════════════════════════════════════════════════════════
# POOL CARD
# ═══════════════════════════════════════════════════════════════════════════════


class PoolCard(QFrame):
    """
    Card displaying a resource pool.
    بطاقة عرض مجموعة الموارد
    """

    clicked = Signal(str)
    manage_clicked = Signal(str)

    def __init__(self, pool: ResourcePool, parent=None):
        super().__init__(parent)
        self._pool = pool
        self._setup_ui()

    def _setup_ui(self):
        """Setup card UI"""
        colors = FluentDesignSystem().colors

        self.setFixedHeight(220)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"""
            PoolCard {{
                background-color: {colors.bg_card};
                border: 1px solid {colors.stroke_card};
                border-radius: 8px;
            }}
            PoolCard:hover {{
                background-color: {colors.fill_subtle};
                border-color: {colors.accent};
            }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()

        name_label = QLabel(self._pool.name)
        name_label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 18px;
            font-weight: 600;
        """
        )
        header.addWidget(name_label)

        header.addStretch()

        # Status badge
        status_colors = {
            PoolStatus.ACTIVE: (colors.success, "Active"),
            PoolStatus.SCALING: (colors.info, "Scaling"),
            PoolStatus.DRAINING: (colors.warning, "Draining"),
            PoolStatus.OFFLINE: (colors.text_disabled, "Offline"),
        }
        color, text = status_colors.get(self._pool.status, (colors.text_secondary, "Unknown"))

        status_badge = QLabel(text)
        status_badge.setStyleSheet(
            f"""
            background-color: {color}20;
            color: {color};
            padding: 4px 10px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 500;
        """
        )
        header.addWidget(status_badge)

        layout.addLayout(header)

        # Resource gauges
        gauges = QHBoxLayout()
        gauges.setSpacing(8)

        # CPU gauge
        cpu_gauge = ResourceGauge("CPU")
        cpu_gauge.set_value(self._pool.used_cpu, self._pool.total_cpu, "cores")
        gauges.addWidget(cpu_gauge)

        # Memory gauge
        mem_gauge = ResourceGauge("Memory")
        mem_gauge.set_value(self._pool.used_memory_gb, self._pool.total_memory_gb, "GB")
        gauges.addWidget(mem_gauge)

        # GPU gauge (if available)
        if self._pool.total_gpu > 0:
            gpu_gauge = ResourceGauge("GPU")
            gpu_gauge.set_value(self._pool.used_gpu, self._pool.total_gpu, "")
            gauges.addWidget(gpu_gauge)

        gauges.addStretch()
        layout.addLayout(gauges)

        # Stats row
        stats = QHBoxLayout()
        stats.setSpacing(16)

        workers_label = QLabel(f"👥 {self._pool.active_workers}/{self._pool.worker_count} workers")
        workers_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        stats.addWidget(workers_label)

        jobs_label = QLabel(f"🔄 {self._pool.running_jobs} running")
        jobs_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        stats.addWidget(jobs_label)

        queued_label = QLabel(f"⏳ {self._pool.queued_jobs} queued")
        queued_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        stats.addWidget(queued_label)

        stats.addStretch()

        if self._pool.auto_scale:
            auto_label = QLabel("⚡ Auto-scale")
            auto_label.setStyleSheet(f"color: {colors.accent}; font-size: 11px;")
            stats.addWidget(auto_label)

        layout.addLayout(stats)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(8)

        manage_btn = FluentButton("Manage", "", ButtonVariant.ACCENT)
        manage_btn.setFixedHeight(32)
        manage_btn.clicked.connect(lambda: self.manage_clicked.emit(self._pool.id))
        actions.addWidget(manage_btn)

        actions.addStretch()

        layout.addLayout(actions)

    def mousePressEvent(self, event):
        """Handle click"""
        self.clicked.emit(self._pool.id)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# POOL DETAILS PANEL
# ═══════════════════════════════════════════════════════════════════════════════


class PoolDetailsPanel(QFrame):
    """
    Panel showing pool details and configuration.
    لوحة تفاصيل المجموعة
    """

    pool_updated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool: Optional[ResourcePool] = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        colors = FluentDesignSystem().colors

        self.setMinimumWidth(380)
        self.setStyleSheet(
            f"""
            PoolDetailsPanel {{
                background-color: {colors.bg_solid_secondary};
                border-left: 1px solid {colors.stroke_divider};
            }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        self._title = QLabel("Pool Configuration")
        self._title.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 18px;
            font-weight: 600;
        """
        )
        header.addWidget(self._title)
        header.addStretch()

        close_btn = FluentButton("", "✕", ButtonVariant.SUBTLE)
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)

        layout.addLayout(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setSpacing(16)

        # Overview section
        overview_card = FluentCard("Overview")
        overview_layout = QVBoxLayout()

        self._status_label = QLabel()
        self._status_label.setStyleSheet(f"color: {colors.text_secondary};")
        overview_layout.addWidget(self._status_label)

        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet(f"color: {colors.text_secondary};")
        overview_layout.addWidget(self._desc_label)

        overview_widget = QWidget()
        overview_widget.setLayout(overview_layout)
        overview_card.add_content(overview_widget)
        self._content_layout.addWidget(overview_card)

        # Scaling section
        scaling_card = FluentCard("Auto-Scaling")
        scaling_layout = QVBoxLayout()

        self._auto_scale_check = QCheckBox("Enable auto-scaling")
        self._auto_scale_check.setStyleSheet(f"color: {colors.text_primary};")
        scaling_layout.addWidget(self._auto_scale_check)

        min_row = QHBoxLayout()
        min_label = QLabel("Min Workers:")
        min_label.setStyleSheet(f"color: {colors.text_secondary};")
        min_row.addWidget(min_label)
        self._min_spin = QSpinBox()
        self._min_spin.setRange(0, 100)
        self._min_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 6px;
            }}
        """
        )
        min_row.addWidget(self._min_spin)
        scaling_layout.addLayout(min_row)

        max_row = QHBoxLayout()
        max_label = QLabel("Max Workers:")
        max_label.setStyleSheet(f"color: {colors.text_secondary};")
        max_row.addWidget(max_label)
        self._max_spin = QSpinBox()
        self._max_spin.setRange(1, 1000)
        self._max_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 6px;
            }}
        """
        )
        max_row.addWidget(self._max_spin)
        scaling_layout.addLayout(max_row)

        scaling_widget = QWidget()
        scaling_widget.setLayout(scaling_layout)
        scaling_card.add_content(scaling_widget)
        self._content_layout.addWidget(scaling_card)

        # Priority section
        priority_card = FluentCard("Priority")
        priority_layout = QVBoxLayout()

        priority_row = QHBoxLayout()
        priority_label = QLabel("Pool Priority:")
        priority_label.setStyleSheet(f"color: {colors.text_secondary};")
        priority_row.addWidget(priority_label)
        self._priority_spin = QSpinBox()
        self._priority_spin.setRange(1, 10)
        self._priority_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 6px;
            }}
        """
        )
        priority_row.addWidget(self._priority_spin)
        priority_layout.addLayout(priority_row)

        priority_hint = QLabel("Higher priority pools get resources first")
        priority_hint.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 11px;")
        priority_layout.addWidget(priority_hint)

        priority_widget = QWidget()
        priority_widget.setLayout(priority_layout)
        priority_card.add_content(priority_widget)
        self._content_layout.addWidget(priority_card)

        self._content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Actions
        actions = QHBoxLayout()

        drain_btn = FluentButton("Drain Pool", "", ButtonVariant.STANDARD)
        actions.addWidget(drain_btn)

        actions.addStretch()

        save_btn = FluentButton("Save Changes", "", ButtonVariant.ACCENT)
        save_btn.clicked.connect(self._save_changes)
        actions.addWidget(save_btn)

        layout.addLayout(actions)

        self.hide()

    def show_pool(self, pool: ResourcePool):
        """Show pool configuration"""
        self._pool = pool
        self._title.setText(f"Configure: {pool.name}")
        self._status_label.setText(f"Status: {pool.status.value}")
        self._desc_label.setText(pool.description)
        self._auto_scale_check.setChecked(pool.auto_scale)
        self._min_spin.setValue(pool.min_workers)
        self._max_spin.setValue(pool.max_workers)
        self._priority_spin.setValue(pool.priority)
        self.show()

    def _save_changes(self):
        """Save pool configuration"""
        if not self._pool:
            return

        data = {
            "id": self._pool.id,
            "auto_scale": self._auto_scale_check.isChecked(),
            "min_workers": self._min_spin.value(),
            "max_workers": self._max_spin.value(),
            "priority": self._priority_spin.value(),
        }
        self.pool_updated.emit(data)


# ═══════════════════════════════════════════════════════════════════════════════
# POOLS VIEW
# ═══════════════════════════════════════════════════════════════════════════════


class FluentPoolsView(QWidget):
    """
    Resource pools management view.
    صفحة إدارة مجموعات الموارد
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pools: List[ResourcePool] = []
        self._setup_ui()
        self._load_demo_data()

    def _setup_ui(self):
        """Setup view UI"""
        colors = FluentDesignSystem().colors

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main content
        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # Header
        header = QHBoxLayout()

        title = QLabel("Resource Pools")
        title.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 28px;
            font-weight: 600;
        """
        )
        header.addWidget(title)

        header.addStretch()

        # Create pool button
        new_btn = FluentButton("Create Pool", "+", ButtonVariant.ACCENT)
        new_btn.clicked.connect(self._create_pool)
        header.addWidget(new_btn)

        main_layout.addLayout(header)

        # Summary stats
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)

        self._total_pools = self._create_stat_widget("Total Pools", "0", colors.accent)
        stats_row.addWidget(self._total_pools)

        self._active_pools = self._create_stat_widget("Active", "0", colors.success)
        stats_row.addWidget(self._active_pools)

        self._total_workers = self._create_stat_widget("Workers", "0", colors.info)
        stats_row.addWidget(self._total_workers)

        self._total_jobs = self._create_stat_widget("Running Jobs", "0", colors.warning)
        stats_row.addWidget(self._total_jobs)

        stats_row.addStretch()
        main_layout.addLayout(stats_row)

        # Pools grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._grid_container = QWidget()
        self._grid_layout = QVBoxLayout(self._grid_container)
        self._grid_layout.setSpacing(16)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._grid_container)
        main_layout.addWidget(scroll, 1)

        layout.addWidget(main, 1)

        # Details panel
        self._details_panel = PoolDetailsPanel()
        self._details_panel.pool_updated.connect(self._on_pool_updated)
        layout.addWidget(self._details_panel)

    def _create_stat_widget(self, label: str, value: str, color: str) -> QFrame:
        """Create a stat widget"""
        colors = FluentDesignSystem().colors

        frame = QFrame()
        frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {colors.bg_card};
                border: 1px solid {colors.stroke_card};
                border-radius: 8px;
                padding: 12px;
            }}
        """
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        value_label = QLabel(value)
        value_label.setObjectName("value")
        value_label.setStyleSheet(
            f"""
            color: {color};
            font-size: 24px;
            font-weight: 700;
        """
        )
        layout.addWidget(value_label)

        text_label = QLabel(label)
        text_label.setStyleSheet(
            f"""
            color: {colors.text_secondary};
            font-size: 12px;
        """
        )
        layout.addWidget(text_label)

        return frame

    def _load_demo_data(self):
        """Load demo pools"""
        self._pools = [
            ResourcePool(
                id="pool-001",
                name="GPU Compute",
                description="High-performance GPU cluster for ML training",
                status=PoolStatus.ACTIVE,
                total_cpu=256,
                used_cpu=180,
                total_memory_gb=1024,
                used_memory_gb=720,
                total_gpu=16,
                used_gpu=12,
                worker_count=8,
                active_workers=8,
                queued_jobs=5,
                running_jobs=12,
                priority=10,
                auto_scale=True,
                min_workers=4,
                max_workers=16,
            ),
            ResourcePool(
                id="pool-002",
                name="CPU Batch",
                description="General purpose CPU workers for batch processing",
                status=PoolStatus.ACTIVE,
                total_cpu=512,
                used_cpu=350,
                total_memory_gb=2048,
                used_memory_gb=1400,
                total_gpu=0,
                used_gpu=0,
                worker_count=16,
                active_workers=14,
                queued_jobs=23,
                running_jobs=45,
                priority=5,
                auto_scale=True,
                min_workers=8,
                max_workers=32,
            ),
            ResourcePool(
                id="pool-003",
                name="Development",
                description="Development and testing pool",
                status=PoolStatus.ACTIVE,
                total_cpu=64,
                used_cpu=20,
                total_memory_gb=256,
                used_memory_gb=80,
                total_gpu=2,
                used_gpu=1,
                worker_count=4,
                active_workers=3,
                queued_jobs=2,
                running_jobs=5,
                priority=3,
                auto_scale=False,
                min_workers=2,
                max_workers=8,
            ),
            ResourcePool(
                id="pool-004",
                name="Rendering Farm",
                description="3D rendering and video processing",
                status=PoolStatus.SCALING,
                total_cpu=128,
                used_cpu=128,
                total_memory_gb=512,
                used_memory_gb=480,
                total_gpu=8,
                used_gpu=8,
                worker_count=4,
                active_workers=4,
                queued_jobs=15,
                running_jobs=8,
                priority=7,
                auto_scale=True,
                min_workers=2,
                max_workers=12,
            ),
        ]

        self._refresh_grid()
        self._update_stats()

    def _refresh_grid(self):
        """Refresh pools grid"""
        # Clear existing cards
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add pool cards in rows of 2
        row_layout = None
        for i, pool in enumerate(self._pools):
            if i % 2 == 0:
                row_layout = QHBoxLayout()
                row_layout.setSpacing(16)
                self._grid_layout.addLayout(row_layout)

            card = PoolCard(pool)
            card.clicked.connect(self._on_pool_clicked)
            card.manage_clicked.connect(self._manage_pool)
            row_layout.addWidget(card, 1)

        # Fill remaining space
        if row_layout and len(self._pools) % 2 == 1:
            row_layout.addStretch(1)

    def _update_stats(self):
        """Update summary statistics"""
        total = len(self._pools)
        active = sum(1 for p in self._pools if p.status == PoolStatus.ACTIVE)
        workers = sum(p.active_workers for p in self._pools)
        jobs = sum(p.running_jobs for p in self._pools)

        self._total_pools.findChild(QLabel, "value").setText(str(total))
        self._active_pools.findChild(QLabel, "value").setText(str(active))
        self._total_workers.findChild(QLabel, "value").setText(str(workers))
        self._total_jobs.findChild(QLabel, "value").setText(str(jobs))

    def _on_pool_clicked(self, pool_id: str):
        """Handle pool click"""
        pool = next((p for p in self._pools if p.id == pool_id), None)
        if pool:
            self._details_panel.show_pool(pool)

    def _manage_pool(self, pool_id: str):
        """Manage pool"""
        pool = next((p for p in self._pools if p.id == pool_id), None)
        if pool:
            self._details_panel.show_pool(pool)

    def _create_pool(self):
        """Create new pool"""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QTextEdit

        dialog = QDialog(self)
        dialog.setWindowTitle("Create New Pool")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        name_input = QLineEdit()
        desc_input = QTextEdit()
        desc_input.setMaximumHeight(80)
        min_workers = QSpinBox()
        min_workers.setRange(0, 100)
        max_workers = QSpinBox()
        max_workers.setRange(1, 1000)
        max_workers.setValue(10)
        auto_scale = QCheckBox("Enable auto-scaling")

        form.addRow("Pool Name:", name_input)
        form.addRow("Description:", desc_input)
        form.addRow("Min Workers:", min_workers)
        form.addRow("Max Workers:", max_workers)
        form.addRow("", auto_scale)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            pool_data = {
                "name": name_input.text(),
                "description": desc_input.toPlainText(),
                "min_workers": min_workers.value(),
                "max_workers": max_workers.value(),
                "auto_scale": auto_scale.isChecked(),
            }
            self._on_pool_updated(pool_data)

    def _on_pool_updated(self, data: dict):
        """Handle pool update"""
        # Create new ResourcePool from data and add to list
        new_pool = ResourcePool(
            id=f"pool-{len(self._pools) + 1:03d}",
            name=data.get("name", "New Pool"),
            description=data.get("description", ""),
            status=PoolStatus.ACTIVE,
            total_cpu=0,
            used_cpu=0,
            total_memory_gb=0,
            used_memory_gb=0,
            total_gpu=0,
            used_gpu=0,
            worker_count=0,
            active_workers=0,
            queued_jobs=0,
            running_jobs=0,
            priority=1,
            auto_scale=data.get("auto_scale", False),
            min_workers=data.get("min_workers", 0),
            max_workers=data.get("max_workers", 10),
        )
        self._pools.append(new_pool)
        self._refresh_grid()
        self._update_stats()


__all__ = ["FluentPoolsView", "PoolCard", "ResourcePool", "PoolStatus", "ResourceGauge"]
