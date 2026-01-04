"""
Fluent Job Queues View
صفحة طوابير المهام

Job queue management with:
- Queue overview and statistics
- Queue priority management
- Job reordering
- Queue policies
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..components import ButtonVariant, FluentButton
from ..fluent_design import FluentDesignSystem

# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class QueueStatus(Enum):
    """Queue status"""
    RUNNING = "Running"
    PAUSED = "Paused"
    DRAINING = "Draining"
    EMPTY = "Empty"


class QueuePolicy(Enum):
    """Queue scheduling policy"""
    FIFO = "First In, First Out"
    PRIORITY = "Priority Based"
    FAIR_SHARE = "Fair Share"
    DEADLINE = "Deadline Aware"


@dataclass
class QueuedJob:
    """Job in queue"""
    id: str
    name: str
    user: str
    priority: int
    submitted_at: datetime
    estimated_runtime: int  # minutes
    resources: Dict[str, int]
    position: int


@dataclass
class JobQueue:
    """Job queue definition"""
    id: str
    name: str
    description: str
    status: QueueStatus
    policy: QueuePolicy
    max_concurrent: int
    current_running: int
    pending_count: int
    completed_today: int
    avg_wait_time: int  # minutes
    priority: int
    jobs: List[QueuedJob]


# ═══════════════════════════════════════════════════════════════════════════════
# QUEUE ITEM WIDGET
# ═══════════════════════════════════════════════════════════════════════════════

class QueueJobItem(QFrame):
    """
    Widget for a job in the queue.
    عنصر المهمة في الطابور
    """

    move_up = Signal(str)
    move_down = Signal(str)
    cancel_job = Signal(str)

    def __init__(self, job: QueuedJob, parent=None):
        super().__init__(parent)
        self._job = job
        self._setup_ui()

    def _setup_ui(self):
        """Setup item UI"""
        colors = FluentDesignSystem().colors

        self.setStyleSheet(f"""
            QueueJobItem {{
                background-color: {colors.bg_card};
                border: 1px solid {colors.stroke_card};
                border-radius: 6px;
            }}
            QueueJobItem:hover {{
                background-color: {colors.fill_subtle};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # Position indicator
        pos_label = QLabel(f"#{self._job.position}")
        pos_label.setFixedWidth(35)
        pos_label.setStyleSheet(f"""
            color: {colors.accent};
            font-size: 14px;
            font-weight: 600;
        """)
        layout.addWidget(pos_label)

        # Job info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(self._job.name)
        name_label.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 13px;
            font-weight: 500;
        """)
        info_layout.addWidget(name_label)

        meta_label = QLabel(f"by {self._job.user} • ~{self._job.estimated_runtime}m")
        meta_label.setStyleSheet(f"""
            color: {colors.text_tertiary};
            font-size: 11px;
        """)
        info_layout.addWidget(meta_label)

        layout.addLayout(info_layout, 1)

        # Priority badge
        priority_colors = {
            1: colors.text_tertiary,
            2: colors.text_secondary,
            3: colors.info,
            4: colors.warning,
            5: colors.error,
        }
        p_color = priority_colors.get(self._job.priority, colors.text_secondary)

        priority_label = QLabel(f"P{self._job.priority}")
        priority_label.setStyleSheet(f"""
            background-color: {p_color}20;
            color: {p_color};
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
        """)
        layout.addWidget(priority_label)

        # Wait time
        wait_time = datetime.now() - self._job.submitted_at
        wait_mins = int(wait_time.total_seconds() / 60)
        wait_label = QLabel(f"{wait_mins}m wait")
        wait_label.setStyleSheet(f"""
            color: {colors.text_tertiary};
            font-size: 11px;
        """)
        layout.addWidget(wait_label)

        # Action buttons
        up_btn = FluentButton("", "▲", ButtonVariant.SUBTLE)
        up_btn.setFixedSize(28, 28)
        up_btn.clicked.connect(lambda: self.move_up.emit(self._job.id))
        layout.addWidget(up_btn)

        down_btn = FluentButton("", "▼", ButtonVariant.SUBTLE)
        down_btn.setFixedSize(28, 28)
        down_btn.clicked.connect(lambda: self.move_down.emit(self._job.id))
        layout.addWidget(down_btn)

        cancel_btn = FluentButton("", "✕", ButtonVariant.SUBTLE)
        cancel_btn.setFixedSize(28, 28)
        cancel_btn.clicked.connect(lambda: self.cancel_job.emit(self._job.id))
        layout.addWidget(cancel_btn)


# ═══════════════════════════════════════════════════════════════════════════════
# QUEUE CARD
# ═══════════════════════════════════════════════════════════════════════════════

class QueueCard(QFrame):
    """
    Card displaying a job queue.
    بطاقة عرض طابور المهام
    """

    clicked = Signal(str)
    pause_clicked = Signal(str)
    resume_clicked = Signal(str)

    def __init__(self, queue: JobQueue, parent=None):
        super().__init__(parent)
        self._queue = queue
        self._setup_ui()

    def _setup_ui(self):
        """Setup card UI"""
        colors = FluentDesignSystem().colors

        self.setFixedWidth(320)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QueueCard {{
                background-color: {colors.bg_card};
                border: 1px solid {colors.stroke_card};
                border-radius: 8px;
            }}
            QueueCard:hover {{
                border-color: {colors.accent};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()

        name_label = QLabel(self._queue.name)
        name_label.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 16px;
            font-weight: 600;
        """)
        header.addWidget(name_label)

        header.addStretch()

        # Status indicator
        status_colors = {
            QueueStatus.RUNNING: colors.success,
            QueueStatus.PAUSED: colors.warning,
            QueueStatus.DRAINING: colors.info,
            QueueStatus.EMPTY: colors.text_disabled,
        }
        status_color = status_colors.get(self._queue.status, colors.text_secondary)

        status_dot = QLabel("●")
        status_dot.setStyleSheet(f"color: {status_color}; font-size: 12px;")
        header.addWidget(status_dot)

        status_label = QLabel(self._queue.status.value)
        status_label.setStyleSheet(f"color: {status_color}; font-size: 12px;")
        header.addWidget(status_label)

        layout.addLayout(header)

        # Policy badge
        policy_label = QLabel(self._queue.policy.value)
        policy_label.setStyleSheet(f"""
            color: {colors.text_secondary};
            font-size: 11px;
        """)
        layout.addWidget(policy_label)

        # Stats
        stats_layout = QGridLayout()
        stats_layout.setSpacing(8)

        # Running
        running_label = QLabel("Running")
        running_label.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 11px;")
        stats_layout.addWidget(running_label, 0, 0)

        running_value = QLabel(f"{self._queue.current_running}/{self._queue.max_concurrent}")
        running_value.setStyleSheet(f"color: {colors.success}; font-size: 14px; font-weight: 600;")
        stats_layout.addWidget(running_value, 1, 0)

        # Pending
        pending_label = QLabel("Pending")
        pending_label.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 11px;")
        stats_layout.addWidget(pending_label, 0, 1)

        pending_value = QLabel(str(self._queue.pending_count))
        pending_value.setStyleSheet(f"color: {colors.warning}; font-size: 14px; font-weight: 600;")
        stats_layout.addWidget(pending_value, 1, 1)

        # Completed
        completed_label = QLabel("Today")
        completed_label.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 11px;")
        stats_layout.addWidget(completed_label, 0, 2)

        completed_value = QLabel(str(self._queue.completed_today))
        completed_value.setStyleSheet(f"color: {colors.info}; font-size: 14px; font-weight: 600;")
        stats_layout.addWidget(completed_value, 1, 2)

        # Avg wait
        wait_label = QLabel("Avg Wait")
        wait_label.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 11px;")
        stats_layout.addWidget(wait_label, 0, 3)

        wait_value = QLabel(f"{self._queue.avg_wait_time}m")
        wait_value.setStyleSheet(f"color: {colors.text_secondary}; font-size: 14px; font-weight: 600;")
        stats_layout.addWidget(wait_value, 1, 3)

        layout.addLayout(stats_layout)

        # Progress bar showing queue fill
        fill_pct = min(100, (self._queue.pending_count / 50) * 100) if self._queue.pending_count > 0 else 0
        progress = QProgressBar()
        progress.setValue(int(fill_pct))
        progress.setFixedHeight(4)
        progress.setTextVisible(False)
        progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {colors.fill_control};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {colors.accent};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(progress)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(8)

        if self._queue.status == QueueStatus.RUNNING:
            pause_btn = FluentButton("Pause", "", ButtonVariant.SUBTLE)
            pause_btn.setFixedHeight(32)
            pause_btn.clicked.connect(lambda: self.pause_clicked.emit(self._queue.id))
            actions.addWidget(pause_btn)
        else:
            resume_btn = FluentButton("Resume", "", ButtonVariant.ACCENT)
            resume_btn.setFixedHeight(32)
            resume_btn.clicked.connect(lambda: self.resume_clicked.emit(self._queue.id))
            actions.addWidget(resume_btn)

        view_btn = FluentButton("View Jobs", "", ButtonVariant.STANDARD)
        view_btn.setFixedHeight(32)
        view_btn.clicked.connect(lambda: self.clicked.emit(self._queue.id))
        actions.addWidget(view_btn)

        layout.addLayout(actions)

    def mousePressEvent(self, event):
        """Handle click"""
        self.clicked.emit(self._queue.id)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# QUEUE DETAILS PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class QueueDetailsPanel(QFrame):
    """
    Panel showing queue details and job list.
    لوحة تفاصيل الطابور
    """

    job_moved = Signal(str, int)  # job_id, new_position
    job_cancelled = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: Optional[JobQueue] = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        colors = FluentDesignSystem().colors

        self.setMinimumWidth(400)
        self.setStyleSheet(f"""
            QueueDetailsPanel {{
                background-color: {colors.bg_solid_secondary};
                border-left: 1px solid {colors.stroke_divider};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        self._title = QLabel("Queue Details")
        self._title.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 18px;
            font-weight: 600;
        """)
        header.addWidget(self._title)
        header.addStretch()

        close_btn = FluentButton("", "✕", ButtonVariant.SUBTLE)
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)

        layout.addLayout(header)

        # Queue info
        self._info_label = QLabel()
        self._info_label.setStyleSheet(f"color: {colors.text_secondary};")
        layout.addWidget(self._info_label)

        # Actions bar
        actions = QHBoxLayout()
        actions.setSpacing(8)

        clear_btn = FluentButton("Clear Completed", "", ButtonVariant.SUBTLE)
        actions.addWidget(clear_btn)

        reorder_btn = FluentButton("Reorder by Priority", "", ButtonVariant.SUBTLE)
        actions.addWidget(reorder_btn)

        actions.addStretch()
        layout.addLayout(actions)

        # Jobs list header
        list_header = QHBoxLayout()
        list_title = QLabel("Queued Jobs")
        list_title.setStyleSheet(f"color: {colors.text_primary}; font-size: 14px; font-weight: 600;")
        list_header.addWidget(list_title)

        self._count_label = QLabel("0 jobs")
        self._count_label.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 12px;")
        list_header.addWidget(self._count_label)

        list_header.addStretch()
        layout.addLayout(list_header)

        # Jobs scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._jobs_container = QWidget()
        self._jobs_layout = QVBoxLayout(self._jobs_container)
        self._jobs_layout.setSpacing(8)
        self._jobs_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._jobs_container)
        layout.addWidget(scroll, 1)

        self.hide()

    def show_queue(self, queue: JobQueue):
        """Show queue details"""
        self._queue = queue
        self._title.setText(f"Queue: {queue.name}")
        self._info_label.setText(f"Policy: {queue.policy.value} • Priority: {queue.priority}")
        self._count_label.setText(f"{len(queue.jobs)} jobs")

        # Clear existing items
        while self._jobs_layout.count():
            item = self._jobs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add job items
        for job in queue.jobs:
            item = QueueJobItem(job)
            item.move_up.connect(self._move_job_up)
            item.move_down.connect(self._move_job_down)
            item.cancel_job.connect(self._cancel_job)
            self._jobs_layout.addWidget(item)

        self.show()

    def _move_job_up(self, job_id: str):
        """Move job up in queue"""
        if self._queue:
            job = next((j for j in self._queue.jobs if j.id == job_id), None)
            if job and job.position > 1:
                self.job_moved.emit(job_id, job.position - 1)

    def _move_job_down(self, job_id: str):
        """Move job down in queue"""
        if self._queue:
            job = next((j for j in self._queue.jobs if j.id == job_id), None)
            if job and job.position < len(self._queue.jobs):
                self.job_moved.emit(job_id, job.position + 1)

    def _cancel_job(self, job_id: str):
        """Cancel job"""
        self.job_cancelled.emit(job_id)


# ═══════════════════════════════════════════════════════════════════════════════
# QUEUES VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class FluentQueuesView(QWidget):
    """
    Job queues management view.
    صفحة إدارة طوابير المهام
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queues: List[JobQueue] = []
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

        title = QLabel("Job Queues")
        title.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 28px;
            font-weight: 600;
        """)
        header.addWidget(title)

        header.addStretch()

        # Filter by status
        self._status_filter = QComboBox()
        self._status_filter.addItem("All Queues")
        self._status_filter.addItems([s.value for s in QueueStatus])
        self._status_filter.setStyleSheet(f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px 16px;
                min-width: 130px;
            }}
        """)
        header.addWidget(self._status_filter)

        # Create queue button
        new_btn = FluentButton("Create Queue", "+", ButtonVariant.ACCENT)
        new_btn.clicked.connect(self._create_queue)
        header.addWidget(new_btn)

        main_layout.addLayout(header)

        # Summary stats
        stats_row = QHBoxLayout()
        stats_row.setSpacing(24)

        self._total_pending = QLabel("0")
        self._total_pending.setStyleSheet(f"color: {colors.warning}; font-size: 32px; font-weight: 700;")
        pending_container = QVBoxLayout()
        pending_container.addWidget(self._total_pending)
        pending_label = QLabel("Total Pending")
        pending_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        pending_container.addWidget(pending_label)
        stats_row.addLayout(pending_container)

        self._total_running = QLabel("0")
        self._total_running.setStyleSheet(f"color: {colors.success}; font-size: 32px; font-weight: 700;")
        running_container = QVBoxLayout()
        running_container.addWidget(self._total_running)
        running_label = QLabel("Total Running")
        running_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        running_container.addWidget(running_label)
        stats_row.addLayout(running_container)

        self._avg_wait = QLabel("0m")
        self._avg_wait.setStyleSheet(f"color: {colors.info}; font-size: 32px; font-weight: 700;")
        wait_container = QVBoxLayout()
        wait_container.addWidget(self._avg_wait)
        wait_label = QLabel("Avg Wait Time")
        wait_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        wait_container.addWidget(wait_label)
        stats_row.addLayout(wait_container)

        stats_row.addStretch()
        main_layout.addLayout(stats_row)

        # Queues scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._queues_container = QWidget()
        self._queues_layout = QHBoxLayout(self._queues_container)
        self._queues_layout.setSpacing(16)
        self._queues_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(self._queues_container)
        main_layout.addWidget(scroll, 1)

        layout.addWidget(main, 1)

        # Details panel
        self._details_panel = QueueDetailsPanel()
        self._details_panel.job_moved.connect(self._on_job_moved)
        self._details_panel.job_cancelled.connect(self._on_job_cancelled)
        layout.addWidget(self._details_panel)

    def _load_demo_data(self):
        """Load demo queues"""
        now = datetime.now()

        self._queues = [
            JobQueue(
                id="queue-001",
                name="High Priority",
                description="High priority jobs queue",
                status=QueueStatus.RUNNING,
                policy=QueuePolicy.PRIORITY,
                max_concurrent=10,
                current_running=8,
                pending_count=12,
                completed_today=45,
                avg_wait_time=5,
                priority=10,
                jobs=[
                    QueuedJob(
                        "job-101", "Critical Model Training", "admin", 5,
                        now - timedelta(minutes=3), 120, {"cpu": 8, "gpu": 2}, 1
                    ),
                    QueuedJob(
                        "job-102", "Urgent Data Processing", "user1", 4,
                        now - timedelta(minutes=8), 45, {"cpu": 16}, 2
                    ),
                    QueuedJob(
                        "job-103", "Priority Inference", "user2", 4,
                        now - timedelta(minutes=12), 30, {"cpu": 4, "gpu": 1}, 3
                    ),
                ]
            ),
            JobQueue(
                id="queue-002",
                name="Default",
                description="Default job queue",
                status=QueueStatus.RUNNING,
                policy=QueuePolicy.FIFO,
                max_concurrent=20,
                current_running=15,
                pending_count=35,
                completed_today=128,
                avg_wait_time=15,
                priority=5,
                jobs=[
                    QueuedJob(
                        "job-201", "Batch Processing A", "user3", 3,
                        now - timedelta(minutes=20), 60, {"cpu": 8}, 1
                    ),
                    QueuedJob(
                        "job-202", "Batch Processing B", "user4", 3,
                        now - timedelta(minutes=18), 60, {"cpu": 8}, 2
                    ),
                    QueuedJob(
                        "job-203", "Analysis Job", "user1", 2,
                        now - timedelta(minutes=15), 90, {"cpu": 4}, 3
                    ),
                    QueuedJob(
                        "job-204", "Report Generation", "user2", 2,
                        now - timedelta(minutes=10), 15, {"cpu": 2}, 4
                    ),
                ]
            ),
            JobQueue(
                id="queue-003",
                name="GPU Training",
                description="GPU-intensive training jobs",
                status=QueueStatus.RUNNING,
                policy=QueuePolicy.FAIR_SHARE,
                max_concurrent=4,
                current_running=4,
                pending_count=8,
                completed_today=12,
                avg_wait_time=45,
                priority=7,
                jobs=[
                    QueuedJob(
                        "job-301", "Deep Learning Model", "mlteam", 3,
                        now - timedelta(minutes=45), 240, {"gpu": 4}, 1
                    ),
                    QueuedJob(
                        "job-302", "GAN Training", "researcher", 3,
                        now - timedelta(minutes=30), 180, {"gpu": 2}, 2
                    ),
                ]
            ),
            JobQueue(
                id="queue-004",
                name="Batch",
                description="Low priority batch jobs",
                status=QueueStatus.PAUSED,
                policy=QueuePolicy.FIFO,
                max_concurrent=50,
                current_running=0,
                pending_count=85,
                completed_today=0,
                avg_wait_time=0,
                priority=1,
                jobs=[]
            ),
        ]

        self._refresh_queues()
        self._update_stats()

    def _refresh_queues(self):
        """Refresh queues display"""
        # Clear existing cards
        while self._queues_layout.count():
            item = self._queues_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add queue cards
        for queue in self._queues:
            card = QueueCard(queue)
            card.clicked.connect(self._on_queue_clicked)
            card.pause_clicked.connect(self._pause_queue)
            card.resume_clicked.connect(self._resume_queue)
            self._queues_layout.addWidget(card)

    def _update_stats(self):
        """Update summary statistics"""
        total_pending = sum(q.pending_count for q in self._queues)
        total_running = sum(q.current_running for q in self._queues)
        avg_wait = sum(q.avg_wait_time * q.pending_count for q in self._queues)
        avg_wait = avg_wait // total_pending if total_pending > 0 else 0

        self._total_pending.setText(str(total_pending))
        self._total_running.setText(str(total_running))
        self._avg_wait.setText(f"{avg_wait}m")

    def _on_queue_clicked(self, queue_id: str):
        """Handle queue click"""
        queue = next((q for q in self._queues if q.id == queue_id), None)
        if queue:
            self._details_panel.show_queue(queue)

    def _pause_queue(self, queue_id: str):
        """Pause queue"""
        pass

    def _resume_queue(self, queue_id: str):
        """Resume queue"""
        pass

    def _create_queue(self):
        """Create new queue"""
        pass

    def _on_job_moved(self, job_id: str, new_position: int):
        """Handle job reorder"""
        pass

    def _on_job_cancelled(self, job_id: str):
        """Handle job cancellation"""
        pass


__all__ = ["FluentQueuesView", "QueueCard", "JobQueue", "QueueStatus", "QueuePolicy", "QueuedJob"]
