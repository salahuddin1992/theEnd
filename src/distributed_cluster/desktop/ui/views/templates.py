"""
Fluent Templates View
صفحة القوالب

Job templates management with:
- Template cards grid
- Template creation wizard
- Template categories
- Import/Export functionality
"""

from __future__ import annotations

from typing import Optional, List
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QGridLayout, QTextEdit,
    QComboBox, QSpinBox
)

from ..fluent_design import FluentDesignSystem
from ..components import FluentButton, FluentInput, ButtonVariant


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class TemplateCategory(Enum):
    """Template categories"""
    MACHINE_LEARNING = "Machine Learning"
    DATA_PROCESSING = "Data Processing"
    SCIENTIFIC = "Scientific Computing"
    RENDERING = "Rendering"
    CUSTOM = "Custom"


@dataclass
class JobTemplate:
    """Job template definition"""
    id: str
    name: str
    description: str
    category: TemplateCategory
    cpu_cores: int
    memory_gb: int
    gpu_count: int
    timeout_hours: int
    script: str
    tags: List[str]
    usage_count: int = 0
    is_favorite: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE CARD
# ═══════════════════════════════════════════════════════════════════════════════

class TemplateCard(QFrame):
    """
    Card displaying a job template.
    بطاقة عرض قالب المهمة
    """

    clicked = Signal(str)  # template_id
    use_clicked = Signal(str)
    edit_clicked = Signal(str)
    favorite_clicked = Signal(str)

    def __init__(self, template: JobTemplate, parent=None):
        super().__init__(parent)
        self._template = template
        self._setup_ui()

    def _setup_ui(self):
        """Setup card UI"""
        colors = FluentDesignSystem().colors

        self.setFixedSize(280, 200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            TemplateCard {{
                background-color: {colors.bg_card};
                border: 1px solid {colors.stroke_card};
                border-radius: 8px;
            }}
            TemplateCard:hover {{
                background-color: {colors.fill_subtle};
                border-color: {colors.accent};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Header with category and favorite
        header = QHBoxLayout()

        # Category badge
        category_colors = {
            TemplateCategory.MACHINE_LEARNING: colors.accent,
            TemplateCategory.DATA_PROCESSING: colors.info,
            TemplateCategory.SCIENTIFIC: colors.success,
            TemplateCategory.RENDERING: colors.warning,
            TemplateCategory.CUSTOM: colors.text_secondary,
        }
        cat_color = category_colors.get(self._template.category, colors.accent)

        category_label = QLabel(self._template.category.value)
        category_label.setStyleSheet(f"""
            background-color: {cat_color}20;
            color: {cat_color};
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
        """)
        header.addWidget(category_label)

        header.addStretch()

        # Favorite button
        fav_icon = "★" if self._template.is_favorite else "☆"
        fav_color = colors.warning if self._template.is_favorite else colors.text_tertiary
        self._fav_btn = QLabel(fav_icon)
        self._fav_btn.setStyleSheet(f"color: {fav_color}; font-size: 18px;")
        self._fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(self._fav_btn)

        layout.addLayout(header)

        # Template name
        name_label = QLabel(self._template.name)
        name_label.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 16px;
            font-weight: 600;
        """)
        layout.addWidget(name_label)

        # Description
        desc_label = QLabel(self._template.description)
        desc_label.setWordWrap(True)
        desc_label.setMaximumHeight(40)
        desc_label.setStyleSheet(f"""
            color: {colors.text_secondary};
            font-size: 12px;
        """)
        layout.addWidget(desc_label)

        # Resource info
        resources = QHBoxLayout()
        resources.setSpacing(12)

        cpu_label = QLabel(f"🖥 {self._template.cpu_cores} CPU")
        cpu_label.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 11px;")
        resources.addWidget(cpu_label)

        mem_label = QLabel(f"💾 {self._template.memory_gb} GB")
        mem_label.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 11px;")
        resources.addWidget(mem_label)

        if self._template.gpu_count > 0:
            gpu_label = QLabel(f"🎮 {self._template.gpu_count} GPU")
            gpu_label.setStyleSheet(f"color: {colors.text_tertiary}; font-size: 11px;")
            resources.addWidget(gpu_label)

        resources.addStretch()
        layout.addLayout(resources)

        layout.addStretch()

        # Action buttons
        actions = QHBoxLayout()
        actions.setSpacing(8)

        use_btn = FluentButton("Use", "", ButtonVariant.ACCENT)
        use_btn.setFixedHeight(32)
        use_btn.clicked.connect(lambda: self.use_clicked.emit(self._template.id))
        actions.addWidget(use_btn)

        edit_btn = FluentButton("Edit", "", ButtonVariant.SUBTLE)
        edit_btn.setFixedHeight(32)
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self._template.id))
        actions.addWidget(edit_btn)

        layout.addLayout(actions)

    def mousePressEvent(self, event):
        """Handle click"""
        self.clicked.emit(self._template.id)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE DETAILS PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class TemplateDetailsPanel(QFrame):
    """
    Panel showing template details and edit form.
    لوحة تفاصيل القالب
    """

    template_updated = Signal(dict)
    template_deleted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._template: Optional[JobTemplate] = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        colors = FluentDesignSystem().colors

        self.setMinimumWidth(350)
        self.setStyleSheet(f"""
            TemplateDetailsPanel {{
                background-color: {colors.bg_solid_secondary};
                border-left: 1px solid {colors.stroke_divider};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        self._title = QLabel("Template Details")
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

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setSpacing(12)

        # Form fields
        # Name
        name_label = QLabel("Name")
        name_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        self._content_layout.addWidget(name_label)
        self._name_input = FluentInput("Template name")
        self._content_layout.addWidget(self._name_input)

        # Description
        desc_label = QLabel("Description")
        desc_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        self._content_layout.addWidget(desc_label)
        self._desc_input = QTextEdit()
        self._desc_input.setMaximumHeight(80)
        self._desc_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        self._content_layout.addWidget(self._desc_input)

        # Category
        cat_label = QLabel("Category")
        cat_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        self._content_layout.addWidget(cat_label)
        self._category_combo = QComboBox()
        self._category_combo.addItems([c.value for c in TemplateCategory])
        self._category_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        self._content_layout.addWidget(self._category_combo)

        # Resources section
        res_label = QLabel("Resources")
        res_label.setStyleSheet(f"color: {colors.text_primary}; font-size: 14px; font-weight: 600; margin-top: 8px;")
        self._content_layout.addWidget(res_label)

        # CPU
        cpu_row = QHBoxLayout()
        cpu_label = QLabel("CPU Cores:")
        cpu_label.setStyleSheet(f"color: {colors.text_secondary};")
        cpu_row.addWidget(cpu_label)
        self._cpu_spin = QSpinBox()
        self._cpu_spin.setRange(1, 128)
        self._cpu_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        cpu_row.addWidget(self._cpu_spin)
        self._content_layout.addLayout(cpu_row)

        # Memory
        mem_row = QHBoxLayout()
        mem_label = QLabel("Memory (GB):")
        mem_label.setStyleSheet(f"color: {colors.text_secondary};")
        mem_row.addWidget(mem_label)
        self._mem_spin = QSpinBox()
        self._mem_spin.setRange(1, 512)
        self._mem_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        mem_row.addWidget(self._mem_spin)
        self._content_layout.addLayout(mem_row)

        # GPU
        gpu_row = QHBoxLayout()
        gpu_label = QLabel("GPU Count:")
        gpu_label.setStyleSheet(f"color: {colors.text_secondary};")
        gpu_row.addWidget(gpu_label)
        self._gpu_spin = QSpinBox()
        self._gpu_spin.setRange(0, 8)
        self._gpu_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        gpu_row.addWidget(self._gpu_spin)
        self._content_layout.addLayout(gpu_row)

        # Script
        script_label = QLabel("Script Template")
        script_label.setStyleSheet(f"color: {colors.text_primary}; font-size: 14px; font-weight: 600; margin-top: 8px;")
        self._content_layout.addWidget(script_label)

        self._script_edit = QTextEdit()
        self._script_edit.setMinimumHeight(150)
        self._script_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {colors.bg_solid_base};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px;
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 12px;
            }}
        """)
        self._content_layout.addWidget(self._script_edit)

        self._content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Action buttons
        actions = QHBoxLayout()
        actions.setSpacing(8)

        delete_btn = FluentButton("Delete", "", ButtonVariant.STANDARD)
        delete_btn.clicked.connect(self._delete_template)
        actions.addWidget(delete_btn)

        actions.addStretch()

        save_btn = FluentButton("Save Changes", "", ButtonVariant.ACCENT)
        save_btn.clicked.connect(self._save_template)
        actions.addWidget(save_btn)

        layout.addLayout(actions)

        self.hide()

    def show_template(self, template: JobTemplate):
        """Show template details"""
        self._template = template
        self._title.setText(f"Edit: {template.name}")

        self._name_input.setText(template.name)
        self._desc_input.setPlainText(template.description)
        self._category_combo.setCurrentText(template.category.value)
        self._cpu_spin.setValue(template.cpu_cores)
        self._mem_spin.setValue(template.memory_gb)
        self._gpu_spin.setValue(template.gpu_count)
        self._script_edit.setPlainText(template.script)

        self.show()

    def _save_template(self):
        """Save template changes"""
        if not self._template:
            return

        data = {
            "id": self._template.id,
            "name": self._name_input.text(),
            "description": self._desc_input.toPlainText(),
            "category": self._category_combo.currentText(),
            "cpu_cores": self._cpu_spin.value(),
            "memory_gb": self._mem_spin.value(),
            "gpu_count": self._gpu_spin.value(),
            "script": self._script_edit.toPlainText()
        }
        self.template_updated.emit(data)

    def _delete_template(self):
        """Delete template"""
        if self._template:
            self.template_deleted.emit(self._template.id)


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATES VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class FluentTemplatesView(QWidget):
    """
    Templates management view.
    صفحة إدارة القوالب
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._templates: List[JobTemplate] = []
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

        title = QLabel("Job Templates")
        title.setStyleSheet(f"""
            color: {colors.text_primary};
            font-size: 28px;
            font-weight: 600;
        """)
        header.addWidget(title)

        header.addStretch()

        # Search
        self._search = FluentInput("Search templates...")
        self._search.setFixedWidth(250)
        self._search.textChanged.connect(self._filter_templates)
        header.addWidget(self._search)

        # Category filter
        self._category_filter = QComboBox()
        self._category_filter.addItem("All Categories")
        self._category_filter.addItems([c.value for c in TemplateCategory])
        self._category_filter.currentTextChanged.connect(self._filter_templates)
        self._category_filter.setStyleSheet(f"""
            QComboBox {{
                background-color: {colors.fill_control};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_control};
                border-radius: 6px;
                padding: 8px 16px;
                min-width: 150px;
            }}
        """)
        header.addWidget(self._category_filter)

        # New template button
        new_btn = FluentButton("New Template", "+", ButtonVariant.ACCENT)
        new_btn.clicked.connect(self._create_template)
        header.addWidget(new_btn)

        main_layout.addLayout(header)

        # Stats row
        stats = QHBoxLayout()
        stats.setSpacing(16)

        self._total_label = QLabel("Total: 0")
        self._total_label.setStyleSheet(f"color: {colors.text_secondary};")
        stats.addWidget(self._total_label)

        self._favorites_label = QLabel("Favorites: 0")
        self._favorites_label.setStyleSheet(f"color: {colors.text_secondary};")
        stats.addWidget(self._favorites_label)

        stats.addStretch()
        main_layout.addLayout(stats)

        # Templates grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(16)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(self._grid_container)
        main_layout.addWidget(scroll, 1)

        layout.addWidget(main, 1)

        # Details panel
        self._details_panel = TemplateDetailsPanel()
        self._details_panel.template_updated.connect(self._on_template_updated)
        self._details_panel.template_deleted.connect(self._on_template_deleted)
        layout.addWidget(self._details_panel)

    def _load_demo_data(self):
        """Load demo templates"""
        self._templates = [
            JobTemplate(
                id="tpl-001",
                name="PyTorch Training",
                description="Standard PyTorch model training with GPU acceleration",
                category=TemplateCategory.MACHINE_LEARNING,
                cpu_cores=8,
                memory_gb=32,
                gpu_count=2,
                timeout_hours=24,
                script="python train.py --epochs 100 --batch-size 32",
                tags=["pytorch", "gpu", "training"],
                usage_count=156,
                is_favorite=True
            ),
            JobTemplate(
                id="tpl-002",
                name="Data ETL Pipeline",
                description="Extract, transform, and load data processing pipeline",
                category=TemplateCategory.DATA_PROCESSING,
                cpu_cores=16,
                memory_gb=64,
                gpu_count=0,
                timeout_hours=12,
                script="python etl_pipeline.py --input $INPUT --output $OUTPUT",
                tags=["etl", "data", "pipeline"],
                usage_count=89
            ),
            JobTemplate(
                id="tpl-003",
                name="Molecular Dynamics",
                description="GROMACS molecular dynamics simulation",
                category=TemplateCategory.SCIENTIFIC,
                cpu_cores=32,
                memory_gb=128,
                gpu_count=4,
                timeout_hours=48,
                script="gmx mdrun -deffnm simulation -nsteps 1000000",
                tags=["gromacs", "md", "simulation"],
                usage_count=42,
                is_favorite=True
            ),
            JobTemplate(
                id="tpl-004",
                name="Blender Render",
                description="Blender animation rendering with GPU",
                category=TemplateCategory.RENDERING,
                cpu_cores=8,
                memory_gb=32,
                gpu_count=2,
                timeout_hours=8,
                script="blender -b scene.blend -o //output -a",
                tags=["blender", "render", "animation"],
                usage_count=78
            ),
            JobTemplate(
                id="tpl-005",
                name="TensorFlow Inference",
                description="TensorFlow model inference batch processing",
                category=TemplateCategory.MACHINE_LEARNING,
                cpu_cores=4,
                memory_gb=16,
                gpu_count=1,
                timeout_hours=4,
                script="python inference.py --model model.h5 --input data/",
                tags=["tensorflow", "inference", "batch"],
                usage_count=234
            ),
            JobTemplate(
                id="tpl-006",
                name="Custom Script",
                description="Custom user-defined script template",
                category=TemplateCategory.CUSTOM,
                cpu_cores=4,
                memory_gb=8,
                gpu_count=0,
                timeout_hours=1,
                script="#!/bin/bash\n# Your script here",
                tags=["custom", "script"],
                usage_count=12
            ),
        ]

        self._refresh_grid()
        self._update_stats()

    def _refresh_grid(self):
        """Refresh templates grid"""
        # Clear existing cards
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add template cards
        col = 0
        row = 0
        max_cols = 4

        for template in self._templates:
            card = TemplateCard(template)
            card.clicked.connect(self._on_template_clicked)
            card.use_clicked.connect(self._use_template)
            card.edit_clicked.connect(self._edit_template)
            self._grid_layout.addWidget(card, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def _update_stats(self):
        """Update statistics"""
        total = len(self._templates)
        favorites = sum(1 for t in self._templates if t.is_favorite)

        self._total_label.setText(f"Total: {total}")
        self._favorites_label.setText(f"Favorites: {favorites}")

    def _filter_templates(self):
        """Filter templates based on search and category"""
        self._search.text().lower()
        self._category_filter.currentText()

        # Would filter the grid based on criteria
        pass

    def _on_template_clicked(self, template_id: str):
        """Handle template card click"""
        template = next((t for t in self._templates if t.id == template_id), None)
        if template:
            self._details_panel.show_template(template)

    def _use_template(self, template_id: str):
        """Use template to create job"""
        # Would open job submission dialog with template values
        pass

    def _edit_template(self, template_id: str):
        """Edit template"""
        template = next((t for t in self._templates if t.id == template_id), None)
        if template:
            self._details_panel.show_template(template)

    def _create_template(self):
        """Create new template"""
        # Would open template creation wizard
        pass

    def _on_template_updated(self, data: dict):
        """Handle template update"""
        pass

    def _on_template_deleted(self, template_id: str):
        """Handle template deletion"""
        self._templates = [t for t in self._templates if t.id != template_id]
        self._refresh_grid()
        self._update_stats()
        self._details_panel.hide()


__all__ = ["FluentTemplatesView", "TemplateCard", "JobTemplate", "TemplateCategory"]
