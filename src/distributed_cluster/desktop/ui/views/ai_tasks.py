"""
Fluent AI Tasks View
صفحة مهام AI بتصميم Fluent

Features:
- Built-in AI tasks gallery
- Distributed prompt execution
- Task progress monitoring
- Results display
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..components import (
    ButtonVariant,
    FluentBadge,
    FluentButton,
    FluentCard,
    FluentInput,
    FluentToggle,
)
from ..fluent_design import FluentDesignSystem
from ..titlebar import FluentIcons

# ═══════════════════════════════════════════════════════════════════════════════
# AI TASK CARD
# ═══════════════════════════════════════════════════════════════════════════════


class AITaskCard(FluentCard):
    """
    بطاقة مهمة AI.

    Displays an AI task with icon, name, and description.
    """

    clicked = Signal(dict)

    def __init__(self, task_data: Dict[str, Any], parent=None):
        super().__init__(parent)

        self.task_data = task_data
        self._setup_ui()
        self.setCursor(Qt.PointingHandCursor)

    def _setup_ui(self):
        """Setup card UI"""
        colors = FluentDesignSystem().colors

        self.setFixedHeight(120)
        self.setMinimumWidth(200)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Header with icon and name
        header = QHBoxLayout()

        # Icon
        icon_label = QLabel(self.task_data.get("icon", "🤖"))
        icon_label.setStyleSheet("font-size: 24px;")
        header.addWidget(icon_label)

        # Name
        name = self.task_data.get("name_ar", self.task_data.get("name", "Task"))
        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 14px;
            font-weight: 600;
        """
        )
        header.addWidget(name_label)
        header.addStretch()

        layout.addLayout(header)

        # Description
        desc = self.task_data.get("description_ar", self.task_data.get("description", ""))
        desc_label = QLabel(desc[:80] + "..." if len(desc) > 80 else desc)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            f"""
            color: {colors.text_secondary};
            font-size: 12px;
        """
        )
        layout.addWidget(desc_label)

        layout.addStretch()

        # Tags
        tags = self.task_data.get("tags", [])
        if tags:
            tags_layout = QHBoxLayout()
            tags_layout.setSpacing(4)

            for tag in tags[:3]:
                badge = FluentBadge(tag)
                tags_layout.addWidget(badge)

            tags_layout.addStretch()
            layout.addLayout(tags_layout)

        self.add_content(QWidget())
        self._content_layout.addLayout(layout)

    def mousePressEvent(self, event):
        """Handle click"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.task_data)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK PARAMETER WIDGET
# ═══════════════════════════════════════════════════════════════════════════════


class TaskParameterWidget(QWidget):
    """
    ويدجت لمعامل مهمة.

    Creates appropriate input widget based on parameter type.
    """

    value_changed = Signal()

    def __init__(self, param: Dict[str, Any], parent=None):
        super().__init__(parent)

        self.param = param
        self._input_widget = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup parameter UI"""
        colors = FluentDesignSystem().colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(4)

        # Label
        label_text = self.param.get("label", self.param.get("name", "Parameter"))
        if self.param.get("required", True):
            label_text += " *"

        label = QLabel(label_text)
        label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 13px;
            font-weight: 500;
        """
        )
        layout.addWidget(label)

        # Description
        if self.param.get("description"):
            desc = QLabel(self.param["description"])
            desc.setWordWrap(True)
            desc.setStyleSheet(
                f"""
                color: {colors.text_secondary};
                font-size: 11px;
            """
            )
            layout.addWidget(desc)

        # Input widget based on type
        param_type = self.param.get("type", "string")

        if param_type in ["text"]:
            self._input_widget = QPlainTextEdit()
            self._input_widget.setPlaceholderText(self.param.get("placeholder", ""))
            self._input_widget.setMinimumHeight(100)
            self._input_widget.setStyleSheet(
                f"""
                QPlainTextEdit {{
                    background-color: {colors.bg_solid_secondary};
                    color: {colors.text_primary};
                    border: 1px solid {colors.stroke_default};
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 13px;
                }}
                QPlainTextEdit:focus {{
                    border-color: {colors.accent_default};
                }}
            """
            )
            if self.param.get("default"):
                self._input_widget.setPlainText(str(self.param["default"]))
            self._input_widget.textChanged.connect(self.value_changed.emit)

        elif param_type == "select":
            self._input_widget = QComboBox()
            self._input_widget.addItems(self.param.get("options", []))
            if self.param.get("default"):
                index = self._input_widget.findText(str(self.param["default"]))
                if index >= 0:
                    self._input_widget.setCurrentIndex(index)
            self._input_widget.setStyleSheet(
                f"""
                QComboBox {{
                    background-color: {colors.bg_solid_secondary};
                    color: {colors.text_primary};
                    border: 1px solid {colors.stroke_default};
                    border-radius: 4px;
                    padding: 8px;
                    min-height: 32px;
                }}
            """
            )
            self._input_widget.currentTextChanged.connect(self.value_changed.emit)

        elif param_type == "boolean":
            self._input_widget = QCheckBox()
            self._input_widget.setChecked(self.param.get("default", False))
            self._input_widget.setStyleSheet(f"color: {colors.text_primary};")
            self._input_widget.stateChanged.connect(self.value_changed.emit)

        elif param_type in ["number", "integer"]:
            self._input_widget = QSpinBox()
            self._input_widget.setRange(int(self.param.get("min_value", 0)), int(self.param.get("max_value", 999999)))
            if self.param.get("default"):
                self._input_widget.setValue(int(self.param["default"]))
            self._input_widget.setStyleSheet(
                f"""
                QSpinBox {{
                    background-color: {colors.bg_solid_secondary};
                    color: {colors.text_primary};
                    border: 1px solid {colors.stroke_default};
                    border-radius: 4px;
                    padding: 8px;
                }}
            """
            )
            self._input_widget.valueChanged.connect(self.value_changed.emit)

        elif param_type == "multi_select":
            # Use multiple checkboxes
            self._input_widget = QWidget()
            cb_layout = QVBoxLayout(self._input_widget)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb_layout.setSpacing(4)
            self._checkboxes = {}

            for option in self.param.get("options", []):
                cb = QCheckBox(option)
                cb.setStyleSheet(f"color: {colors.text_primary};")
                if option in self.param.get("default", []):
                    cb.setChecked(True)
                cb.stateChanged.connect(self.value_changed.emit)
                cb_layout.addWidget(cb)
                self._checkboxes[option] = cb

        else:  # string
            self._input_widget = FluentInput()
            self._input_widget.setPlaceholderText(self.param.get("placeholder", ""))
            if self.param.get("default"):
                self._input_widget.setText(str(self.param["default"]))
            self._input_widget.textChanged.connect(self.value_changed.emit)

        layout.addWidget(self._input_widget)

    def get_value(self) -> Any:
        """Get the parameter value"""
        param_type = self.param.get("type", "string")

        if param_type == "text":
            return self._input_widget.toPlainText()
        elif param_type == "select":
            return self._input_widget.currentText()
        elif param_type == "boolean":
            return self._input_widget.isChecked()
        elif param_type in ["number", "integer"]:
            return self._input_widget.value()
        elif param_type == "multi_select":
            return [k for k, cb in self._checkboxes.items() if cb.isChecked()]
        else:
            return self._input_widget.text()


# ═══════════════════════════════════════════════════════════════════════════════
# TASK EXECUTION PANEL
# ═══════════════════════════════════════════════════════════════════════════════


class TaskExecutionPanel(QFrame):
    """
    لوحة تنفيذ المهمة.

    Shows task parameters and execution controls.
    """

    execute_requested = Signal(str, dict, bool)  # task_id, params, distributed
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._task_data: Optional[Dict[str, Any]] = None
        self._param_widgets: Dict[str, TaskParameterWidget] = {}
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        colors = FluentDesignSystem().colors

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {colors.bg_card_default};
            }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()

        back_btn = FluentButton("", FluentIcons.ARROW_LEFT, ButtonVariant.SUBTLE)
        back_btn.setFixedSize(36, 36)
        back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(back_btn)

        self._icon_label = QLabel("🤖")
        self._icon_label.setStyleSheet("font-size: 28px;")
        header.addWidget(self._icon_label)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)

        self._title_label = QLabel("AI Task")
        self._title_label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 20px;
            font-weight: 600;
        """
        )
        title_layout.addWidget(self._title_label)

        self._desc_label = QLabel("")
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet(
            f"""
            color: {colors.text_secondary};
            font-size: 13px;
        """
        )
        title_layout.addWidget(self._desc_label)

        header.addLayout(title_layout)
        header.addStretch()

        layout.addLayout(header)

        # Parameters scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self._params_container = QWidget()
        self._params_layout = QVBoxLayout(self._params_container)
        self._params_layout.setContentsMargins(0, 0, 0, 0)
        self._params_layout.setSpacing(12)

        scroll.setWidget(self._params_container)
        layout.addWidget(scroll, 1)

        # Execution options
        options_card = FluentCard()
        options_layout = QVBoxLayout()
        options_layout.setSpacing(12)

        # Distributed toggle
        dist_layout = QHBoxLayout()
        dist_label = QLabel("التنفيذ الموزع (Distributed)")
        dist_label.setStyleSheet(f"color: {colors.text_primary}; font-size: 13px;")
        dist_layout.addWidget(dist_label)
        dist_layout.addStretch()

        self._distributed_toggle = FluentToggle()
        dist_layout.addWidget(self._distributed_toggle)

        options_layout.addLayout(dist_layout)

        # Model selection
        model_layout = QHBoxLayout()
        model_label = QLabel("النموذج:")
        model_label.setStyleSheet(f"color: {colors.text_primary}; font-size: 13px;")
        model_layout.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.addItems(["llama3.2", "mistral", "codellama", "deepseek-coder"])
        self._model_combo.setMinimumWidth(200)
        self._model_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {colors.bg_solid_secondary};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_default};
                border-radius: 4px;
                padding: 6px 12px;
            }}
        """
        )
        model_layout.addWidget(self._model_combo)
        model_layout.addStretch()

        options_layout.addLayout(model_layout)

        options_card.add_content(QWidget())
        options_card._content_layout.addLayout(options_layout)
        layout.addWidget(options_card)

        # Execute button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._execute_btn = FluentButton("تنفيذ المهمة", FluentIcons.PLAY, ButtonVariant.ACCENT)
        self._execute_btn.setMinimumWidth(150)
        self._execute_btn.clicked.connect(self._on_execute)
        btn_layout.addWidget(self._execute_btn)

        layout.addLayout(btn_layout)

    def set_task(self, task_data: Dict[str, Any]):
        """Set the task to execute"""
        self._task_data = task_data
        self._param_widgets.clear()

        # Clear old parameters
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Update header
        self._icon_label.setText(task_data.get("icon", "🤖"))
        self._title_label.setText(task_data.get("name_ar", task_data.get("name", "Task")))
        self._desc_label.setText(task_data.get("description_ar", task_data.get("description", "")))

        # Create parameter widgets
        for param in task_data.get("parameters", []):
            widget = TaskParameterWidget(param)
            self._param_widgets[param["name"]] = widget
            self._params_layout.addWidget(widget)

        self._params_layout.addStretch()

        # Update model combo
        recommended = task_data.get("recommended_models", [])
        if recommended:
            self._model_combo.clear()
            self._model_combo.addItems(recommended)

    def _on_execute(self):
        """Handle execute button click"""
        if not self._task_data:
            return

        # Collect parameters
        params = {}
        for name, widget in self._param_widgets.items():
            params[name] = widget.get_value()

        self.execute_requested.emit(
            self._task_data["task_id"],
            params,
            self._distributed_toggle.isChecked(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTION RESULTS PANEL
# ═══════════════════════════════════════════════════════════════════════════════


class ExecutionResultsPanel(QFrame):
    """
    لوحة نتائج التنفيذ.

    Shows execution progress and results.
    """

    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._execution_id: Optional[str] = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        colors = FluentDesignSystem().colors

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {colors.bg_card_default};
            }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()

        back_btn = FluentButton("", FluentIcons.ARROW_LEFT, ButtonVariant.SUBTLE)
        back_btn.setFixedSize(36, 36)
        back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(back_btn)

        self._title_label = QLabel("نتائج التنفيذ")
        self._title_label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 20px;
            font-weight: 600;
        """
        )
        header.addWidget(self._title_label)
        header.addStretch()

        self._status_badge = FluentBadge("جاري التنفيذ")
        header.addWidget(self._status_badge)

        layout.addLayout(header)

        # Progress section
        progress_card = FluentCard()
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(12)

        # Progress bar area
        self._progress_label = QLabel("التقدم: 0%")
        self._progress_label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 14px;
            font-weight: 500;
        """
        )
        progress_layout.addWidget(self._progress_label)

        self._progress_bar = QFrame()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setStyleSheet(
            f"""
            QFrame {{
                background-color: {colors.bg_solid_secondary};
                border-radius: 4px;
            }}
        """
        )

        self._progress_fill = QFrame(self._progress_bar)
        self._progress_fill.setFixedHeight(8)
        self._progress_fill.setStyleSheet(
            f"""
            QFrame {{
                background-color: {colors.accent_default};
                border-radius: 4px;
            }}
        """
        )
        self._progress_fill.setFixedWidth(0)

        progress_layout.addWidget(self._progress_bar)

        # Chunks info
        self._chunks_label = QLabel("")
        self._chunks_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 12px;")
        progress_layout.addWidget(self._chunks_label)

        progress_card.add_content(QWidget())
        progress_card._content_layout.addLayout(progress_layout)
        layout.addWidget(progress_card)

        # Results
        results_label = QLabel("النتيجة:")
        results_label.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 14px;
            font-weight: 500;
        """
        )
        layout.addWidget(results_label)

        self._results_text = QPlainTextEdit()
        self._results_text.setReadOnly(True)
        self._results_text.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {colors.bg_solid_secondary};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_default};
                border-radius: 4px;
                padding: 12px;
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 13px;
            }}
        """
        )
        layout.addWidget(self._results_text, 1)

        # Metadata
        self._metadata_label = QLabel("")
        self._metadata_label.setStyleSheet(f"color: {colors.text_secondary}; font-size: 11px;")
        layout.addWidget(self._metadata_label)

    def set_execution(self, execution_id: str, task_name: str):
        """Set the execution to monitor"""
        self._execution_id = execution_id
        self._title_label.setText(f"نتائج التنفيذ: {task_name}")
        self._results_text.clear()
        self.update_progress(0, "جاري التنفيذ...", 0, 0)

    def update_progress(self, progress: float, status: str, completed: int = 0, total: int = 0):
        """Update progress display"""
        self._progress_label.setText(f"التقدم: {progress:.0f}%")

        # Update progress bar
        bar_width = self._progress_bar.width()
        fill_width = int((progress / 100) * bar_width)
        self._progress_fill.setFixedWidth(max(0, fill_width))

        # Update status badge
        if status == "completed":
            self._status_badge.setText("مكتمل ✓")
            self._status_badge.setStyleSheet(
                """
                background-color: #10b981;
                color: white;
                padding: 4px 12px;
                border-radius: 12px;
            """
            )
        elif status == "failed":
            self._status_badge.setText("فشل ✗")
            self._status_badge.setStyleSheet(
                """
                background-color: #ef4444;
                color: white;
                padding: 4px 12px;
                border-radius: 12px;
            """
            )
        else:
            self._status_badge.setText("جاري التنفيذ")

        # Update chunks info
        if total > 0:
            self._chunks_label.setText(f"القطع: {completed}/{total}")

    def set_result(self, result: Any, error: Optional[str] = None, metadata: Optional[Dict] = None):
        """Set the execution result"""
        if error:
            self._results_text.setPlainText(f"خطأ: {error}")
        elif result:
            if isinstance(result, (dict, list)):
                self._results_text.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                self._results_text.setPlainText(str(result))

        if metadata:
            meta_text = " | ".join([f"{k}: {v}" for k, v in metadata.items()])
            self._metadata_label.setText(meta_text)


# ═══════════════════════════════════════════════════════════════════════════════
# DISTRIBUTED PROMPTS VIEW
# ═══════════════════════════════════════════════════════════════════════════════


class DistributedPromptsPanel(QFrame):
    """
    لوحة إرسال prompts موزعة.

    Send custom prompts distributed across workers.
    """

    execute_requested = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Setup panel UI"""
        colors = FluentDesignSystem().colors

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {colors.bg_card_default};
            }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("إرسال Prompts موزعة")
        title.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 20px;
            font-weight: 600;
        """
        )
        layout.addWidget(title)

        desc = QLabel("أرسل prompts مخصصة يتم تقسيمها وتوزيعها على عدة Workers تلقائياً")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {colors.text_secondary}; font-size: 13px;")
        layout.addWidget(desc)

        # System prompt
        sys_label = QLabel("System Prompt (اختياري):")
        sys_label.setStyleSheet(f"color: {colors.text_primary}; font-size: 13px;")
        layout.addWidget(sys_label)

        self._system_prompt = QPlainTextEdit()
        self._system_prompt.setMaximumHeight(80)
        self._system_prompt.setPlaceholderText("أدخل system prompt هنا...")
        self._system_prompt.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {colors.bg_solid_secondary};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_default};
                border-radius: 4px;
                padding: 8px;
            }}
        """
        )
        layout.addWidget(self._system_prompt)

        # Main prompt
        prompt_label = QLabel("Prompt:")
        prompt_label.setStyleSheet(f"color: {colors.text_primary}; font-size: 13px;")
        layout.addWidget(prompt_label)

        self._prompt_input = QPlainTextEdit()
        self._prompt_input.setPlaceholderText("أدخل الـ prompt هنا... يمكنك إدخال نص طويل وسيتم تقسيمه تلقائياً")
        self._prompt_input.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {colors.bg_solid_secondary};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_default};
                border-radius: 4px;
                padding: 12px;
                font-size: 13px;
            }}
        """
        )
        layout.addWidget(self._prompt_input, 1)

        # Options
        options_layout = QHBoxLayout()

        # Model
        model_label = QLabel("النموذج:")
        model_label.setStyleSheet(f"color: {colors.text_primary};")
        options_layout.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.addItems(["llama3.2", "mistral", "gpt-4", "codellama"])
        self._model_combo.setMinimumWidth(150)
        self._model_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {colors.bg_solid_secondary};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_default};
                border-radius: 4px;
                padding: 6px 12px;
            }}
        """
        )
        options_layout.addWidget(self._model_combo)

        options_layout.addSpacing(20)

        # Temperature
        temp_label = QLabel("Temperature:")
        temp_label.setStyleSheet(f"color: {colors.text_primary};")
        options_layout.addWidget(temp_label)

        self._temp_spin = QSpinBox()
        self._temp_spin.setRange(0, 100)
        self._temp_spin.setValue(70)
        self._temp_spin.setSuffix("%")
        self._temp_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: {colors.bg_solid_secondary};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_default};
                border-radius: 4px;
                padding: 6px;
            }}
        """
        )
        options_layout.addWidget(self._temp_spin)

        options_layout.addStretch()

        # Distributed toggle
        self._distributed_check = QCheckBox("تفعيل التوزيع التلقائي")
        self._distributed_check.setChecked(True)
        self._distributed_check.setStyleSheet(f"color: {colors.text_primary};")
        options_layout.addWidget(self._distributed_check)

        layout.addLayout(options_layout)

        # Execute button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._execute_btn = FluentButton("إرسال", FluentIcons.SEND, ButtonVariant.ACCENT)
        self._execute_btn.setMinimumWidth(120)
        self._execute_btn.clicked.connect(self._on_execute)
        btn_layout.addWidget(self._execute_btn)

        layout.addLayout(btn_layout)

    def _on_execute(self):
        """Handle execute"""
        prompt = self._prompt_input.toPlainText().strip()
        if not prompt:
            return

        params = {
            "prompt": prompt,
            "system_prompt": self._system_prompt.toPlainText().strip(),
            "model": self._model_combo.currentText(),
            "temperature": self._temp_spin.value() / 100,
            "distributed": self._distributed_check.isChecked(),
        }

        self.execute_requested.emit("raw_prompt", params)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN AI TASKS VIEW
# ═══════════════════════════════════════════════════════════════════════════════


class AITasksView(QWidget):
    """
    صفحة مهام AI الرئيسية.

    Main AI Tasks page with:
    - Task gallery
    - Task execution
    - Distributed prompts
    - Results monitoring
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._tasks: List[Dict[str, Any]] = []
        self._setup_ui()
        self._load_sample_tasks()

    def _setup_ui(self):
        """Setup main UI"""
        colors = FluentDesignSystem().colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: none;
                background-color: {colors.bg_primary};
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {colors.text_secondary};
                padding: 12px 24px;
                border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {colors.accent_default};
                border-bottom: 2px solid {colors.accent_default};
            }}
            QTabBar::tab:hover {{
                color: {colors.text_primary};
            }}
        """
        )

        # Tab 1: Built-in Tasks
        tasks_tab = QWidget()
        tasks_layout = QVBoxLayout(tasks_tab)
        tasks_layout.setContentsMargins(0, 0, 0, 0)

        # Stacked widget for navigation
        self._stack = QStackedWidget()

        # Gallery view
        self._gallery = self._create_gallery()
        self._stack.addWidget(self._gallery)

        # Execution panel
        self._execution_panel = TaskExecutionPanel()
        self._execution_panel.back_requested.connect(lambda: self._stack.setCurrentIndex(0))
        self._execution_panel.execute_requested.connect(self._on_task_execute)
        self._stack.addWidget(self._execution_panel)

        # Results panel
        self._results_panel = ExecutionResultsPanel()
        self._results_panel.back_requested.connect(lambda: self._stack.setCurrentIndex(1))
        self._stack.addWidget(self._results_panel)

        tasks_layout.addWidget(self._stack)

        self._tabs.addTab(tasks_tab, "🤖 مهام AI الجاهزة")

        # Tab 2: Distributed Prompts
        self._prompts_panel = DistributedPromptsPanel()
        self._prompts_panel.execute_requested.connect(self._on_prompt_execute)
        self._tabs.addTab(self._prompts_panel, "📤 Prompts موزعة")

        layout.addWidget(self._tabs)

    def _create_gallery(self) -> QWidget:
        """Create the tasks gallery"""
        colors = FluentDesignSystem().colors

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()

        title = QLabel("مهام AI الجاهزة")
        title.setStyleSheet(
            f"""
            color: {colors.text_primary};
            font-size: 24px;
            font-weight: 600;
        """
        )
        header.addWidget(title)

        header.addStretch()

        # Search
        self._search_input = FluentInput()
        self._search_input.setPlaceholderText("بحث...")
        self._search_input.setMinimumWidth(200)
        self._search_input.textChanged.connect(self._filter_tasks)
        header.addWidget(self._search_input)

        # Category filter
        self._category_combo = QComboBox()
        self._category_combo.addItems(["جميع الفئات", "معالجة النصوص", "البرمجة", "التحليل", "الترجمة", "التوليد"])
        self._category_combo.setMinimumWidth(150)
        self._category_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {colors.bg_solid_secondary};
                color: {colors.text_primary};
                border: 1px solid {colors.stroke_default};
                border-radius: 4px;
                padding: 8px 12px;
            }}
        """
        )
        self._category_combo.currentTextChanged.connect(self._filter_tasks)
        header.addWidget(self._category_combo)

        layout.addLayout(header)

        # Tasks grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(16)

        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll)

        return widget

    def _load_sample_tasks(self):
        """Load sample tasks for display"""
        # These would normally come from the API
        self._tasks = [
            {
                "task_id": "summarize",
                "name": "Text Summarization",
                "name_ar": "تلخيص النصوص",
                "description": "Summarize long texts",
                "description_ar": "تلخيص النصوص الطويلة إلى ملخصات موجزة",
                "category": "text_processing",
                "icon": "📝",
                "tags": ["text", "summarization"],
                "supports_distributed": True,
                "parameters": [
                    {
                        "name": "text",
                        "label": "النص",
                        "type": "text",
                        "required": True,
                        "placeholder": "أدخل النص هنا...",
                    },
                    {
                        "name": "style",
                        "label": "الأسلوب",
                        "type": "select",
                        "options": ["concise", "detailed", "bullet_points"],
                        "default": "concise",
                    },
                    {
                        "name": "length",
                        "label": "الطول",
                        "type": "select",
                        "options": ["short", "medium", "long"],
                        "default": "medium",
                    },
                ],
                "recommended_models": ["llama3.2", "mistral"],
            },
            {
                "task_id": "translate",
                "name": "Translation",
                "name_ar": "الترجمة",
                "description": "Translate text between languages",
                "description_ar": "ترجمة النصوص بين اللغات",
                "category": "translation",
                "icon": "🌐",
                "tags": ["translation", "language"],
                "supports_distributed": True,
                "parameters": [
                    {"name": "text", "label": "النص", "type": "text", "required": True},
                    {
                        "name": "source_language",
                        "label": "اللغة المصدر",
                        "type": "select",
                        "options": ["auto", "english", "arabic", "french"],
                        "default": "auto",
                    },
                    {
                        "name": "target_language",
                        "label": "اللغة الهدف",
                        "type": "select",
                        "options": ["english", "arabic", "french", "spanish"],
                        "default": "english",
                    },
                ],
                "recommended_models": ["llama3.2", "mistral"],
            },
            {
                "task_id": "code_gen",
                "name": "Code Generation",
                "name_ar": "توليد الكود",
                "description": "Generate code from descriptions",
                "description_ar": "توليد الكود من وصف باللغة الطبيعية",
                "category": "code",
                "icon": "💻",
                "tags": ["code", "programming"],
                "supports_distributed": True,
                "parameters": [
                    {"name": "description", "label": "الوصف", "type": "text", "required": True},
                    {
                        "name": "language",
                        "label": "اللغة",
                        "type": "select",
                        "options": ["python", "javascript", "java", "go"],
                        "default": "python",
                    },
                    {"name": "include_comments", "label": "إضافة تعليقات", "type": "boolean", "default": True},
                ],
                "recommended_models": ["codellama", "deepseek-coder"],
            },
            {
                "task_id": "sentiment",
                "name": "Sentiment Analysis",
                "name_ar": "تحليل المشاعر",
                "description": "Analyze text sentiment",
                "description_ar": "تحليل مشاعر النصوص",
                "category": "analysis",
                "icon": "😊",
                "tags": ["sentiment", "analysis"],
                "supports_distributed": True,
                "parameters": [
                    {"name": "text", "label": "النص", "type": "text", "required": True},
                    {
                        "name": "detail_level",
                        "label": "مستوى التفصيل",
                        "type": "select",
                        "options": ["basic", "medium", "detailed"],
                        "default": "medium",
                    },
                ],
                "recommended_models": ["llama3.2", "mistral"],
            },
            {
                "task_id": "content_gen",
                "name": "Content Generation",
                "name_ar": "توليد المحتوى",
                "description": "Generate various content types",
                "description_ar": "توليد أنواع مختلفة من المحتوى",
                "category": "generation",
                "icon": "✍️",
                "tags": ["content", "writing"],
                "supports_distributed": True,
                "parameters": [
                    {"name": "topic", "label": "الموضوع", "type": "string", "required": True},
                    {
                        "name": "content_type",
                        "label": "نوع المحتوى",
                        "type": "select",
                        "options": ["article", "blog_post", "email", "story"],
                        "default": "article",
                    },
                    {
                        "name": "tone",
                        "label": "النبرة",
                        "type": "select",
                        "options": ["professional", "casual", "formal"],
                        "default": "professional",
                    },
                ],
                "recommended_models": ["llama3.2", "mistral", "gpt-4"],
            },
            {
                "task_id": "code_review",
                "name": "Code Review",
                "name_ar": "مراجعة الكود",
                "description": "Review code for issues",
                "description_ar": "مراجعة الكود للأخطاء والتحسينات",
                "category": "code",
                "icon": "🔍",
                "tags": ["code", "review"],
                "supports_distributed": True,
                "parameters": [
                    {"name": "code", "label": "الكود", "type": "text", "required": True},
                    {
                        "name": "language",
                        "label": "اللغة",
                        "type": "select",
                        "options": ["python", "javascript", "java"],
                        "default": "python",
                    },
                ],
                "recommended_models": ["codellama", "deepseek-coder"],
            },
        ]

        self._display_tasks(self._tasks)

    def _display_tasks(self, tasks: List[Dict[str, Any]]):
        """Display tasks in grid"""
        # Clear existing cards
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add task cards
        cols = 3
        for i, task in enumerate(tasks):
            card = AITaskCard(task)
            card.clicked.connect(self._on_task_selected)
            row = i // cols
            col = i % cols
            self._grid_layout.addWidget(card, row, col)

    def _filter_tasks(self):
        """Filter tasks by search and category"""
        search = self._search_input.text().lower()
        category = self._category_combo.currentText()

        category_map = {
            "معالجة النصوص": "text_processing",
            "البرمجة": "code",
            "التحليل": "analysis",
            "الترجمة": "translation",
            "التوليد": "generation",
        }

        filtered = []
        for task in self._tasks:
            # Check search
            if search:
                if not (
                    search in task.get("name", "").lower()
                    or search in task.get("name_ar", "")
                    or search in task.get("description", "").lower()
                    or any(search in tag for tag in task.get("tags", []))
                ):
                    continue

            # Check category
            if category != "جميع الفئات":
                cat_value = category_map.get(category)
                if cat_value and task.get("category") != cat_value:
                    continue

            filtered.append(task)

        self._display_tasks(filtered)

    def _on_task_selected(self, task_data: Dict[str, Any]):
        """Handle task selection"""
        self._execution_panel.set_task(task_data)
        self._stack.setCurrentIndex(1)

    def _on_task_execute(self, task_id: str, params: Dict[str, Any], distributed: bool):
        """Handle task execution"""
        # Find task name
        task_name = task_id
        for task in self._tasks:
            if task["task_id"] == task_id:
                task_name = task.get("name_ar", task.get("name", task_id))
                break

        self._results_panel.set_execution(f"exec-{task_id}", task_name)
        self._stack.setCurrentIndex(2)

        # Simulate progress
        self._simulate_execution()

    def _on_prompt_execute(self, prompt_type: str, params: Dict[str, Any]):
        """Handle prompt execution"""
        self._results_panel.set_execution("exec-prompt", "Prompt موزع")
        self._tabs.setCurrentIndex(0)
        self._stack.setCurrentIndex(2)

        self._simulate_execution()

    def _simulate_execution(self):
        """Simulate execution progress"""
        progress = 0
        timer = QTimer(self)

        def update():
            nonlocal progress
            progress += 10
            if progress <= 100:
                self._results_panel.update_progress(
                    progress,
                    "running" if progress < 100 else "completed",
                    progress // 10,
                    10,
                )
                if progress == 100:
                    self._results_panel.set_result(
                        "هذه نتيجة تجريبية للمهمة.\n\nتم التنفيذ بنجاح!",
                        metadata={"execution_time_ms": 1234, "tokens": 500},
                    )
                    timer.stop()
            else:
                timer.stop()

        timer.timeout.connect(update)
        timer.start(200)
