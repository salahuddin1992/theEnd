"""
Embedded Terminal Widget
ويدجت الطرفية المدمجة
"""

from datetime import datetime
from typing import Callable, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..resources.styles import COLORS


class TerminalOutput(QPlainTextEdit):
    """Terminal output display"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 11))
        self.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #0d1117;
                color: #c9d1d9;
                border: none;
                padding: 8px;
            }
        """
        )
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

        # Color formats
        self._formats = {
            "default": self._create_format("#c9d1d9"),
            "error": self._create_format("#f85149"),
            "success": self._create_format("#3fb950"),
            "warning": self._create_format("#d29922"),
            "info": self._create_format("#58a6ff"),
            "command": self._create_format("#a5d6ff"),
            "timestamp": self._create_format("#8b949e"),
        }

    def _create_format(self, color: str) -> QTextCharFormat:
        """Create text format with color"""
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        return fmt

    def append_text(self, text: str, style: str = "default", show_timestamp: bool = True):
        """Append text with styling"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        if show_timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")
            cursor.insertText(f"[{timestamp}] ", self._formats["timestamp"])

        cursor.insertText(text + "\n", self._formats.get(style, self._formats["default"]))

        # Auto-scroll to bottom
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def append_command(self, command: str):
        """Append command with special styling"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        timestamp = datetime.now().strftime("%H:%M:%S")
        cursor.insertText(f"[{timestamp}] ", self._formats["timestamp"])
        cursor.insertText("$ ", self._formats["success"])
        cursor.insertText(command + "\n", self._formats["command"])

        self.setTextCursor(cursor)
        self.ensureCursorVisible()


class CommandInput(QLineEdit):
    """Command input with history"""

    command_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: List[str] = []
        self._history_index = -1

        self.setFont(QFont("Consolas", 11))
        self.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: #161b22;
                color: #c9d1d9;
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['primary']};
            }}
        """
        )
        self.setPlaceholderText("Enter command...")

        self.returnPressed.connect(self._on_submit)

    def keyPressEvent(self, event):
        """Handle key events for history navigation"""
        if event.key() == Qt.Key_Up:
            self._navigate_history(-1)
        elif event.key() == Qt.Key_Down:
            self._navigate_history(1)
        else:
            super().keyPressEvent(event)

    def _navigate_history(self, direction: int):
        """Navigate command history"""
        if not self._history:
            return

        new_index = self._history_index + direction

        if new_index < 0:
            new_index = 0
        elif new_index >= len(self._history):
            new_index = len(self._history) - 1
            self.clear()
            self._history_index = -1
            return

        self._history_index = new_index
        self.setText(self._history[self._history_index])

    def _on_submit(self):
        """Handle command submission"""
        command = self.text().strip()
        if command:
            # Add to history
            if not self._history or self._history[-1] != command:
                self._history.append(command)
            self._history_index = len(self._history)

            self.command_submitted.emit(command)
            self.clear()


class TerminalWidget(QFrame):
    """Embedded terminal widget for running commands"""

    command_executed = Signal(str, str)  # command, output

    def __init__(self, parent=None):
        super().__init__(parent)
        self._command_handlers = {}
        self._api_client = None
        self._setup_ui()
        self._register_default_commands()

    def _setup_ui(self):
        """Setup terminal UI"""
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: #0d1117;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet(
            f"""
            background-color: #161b22;
            border-bottom: 1px solid {COLORS['border']};
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        """
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        # Terminal buttons (decorative)
        for color in ["#ff5f56", "#ffbd2e", "#27c93f"]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 12px;")
            header_layout.addWidget(dot)

        header_layout.addSpacing(12)

        # Title
        title = QLabel("Terminal")
        title.setStyleSheet(f"color: {COLORS['text_primary']}; font-weight: 500;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Target selector
        self.target_combo = QComboBox()
        self.target_combo.addItems(["Local", "Master", "All Workers"])
        self.target_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 100px;
            }}
        """
        )
        header_layout.addWidget(self.target_combo)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_light']};
            }}
        """
        )
        clear_btn.clicked.connect(self._clear_output)
        header_layout.addWidget(clear_btn)

        layout.addWidget(header)

        # Output area
        self.output = TerminalOutput()
        layout.addWidget(self.output)

        # Input area
        input_frame = QFrame()
        input_frame.setStyleSheet(
            f"""
            background-color: #161b22;
            border-top: 1px solid {COLORS['border']};
            border-bottom-left-radius: 8px;
            border-bottom-right-radius: 8px;
        """
        )
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)

        # Prompt
        prompt = QLabel("$")
        prompt.setStyleSheet("color: #3fb950; font-family: Consolas; font-size: 14px;")
        input_layout.addWidget(prompt)

        # Command input
        self.input = CommandInput()
        self.input.command_submitted.connect(self._execute_command)
        input_layout.addWidget(self.input)

        layout.addWidget(input_frame)

        # Welcome message
        self._show_welcome()

    def _show_welcome(self):
        """Show welcome message"""
        self.output.append_text("NebulaCompute Terminal v0.1.0", "info", False)
        self.output.append_text("Type 'help' for available commands", "default", False)
        self.output.append_text("", "default", False)

    def _register_default_commands(self):
        """Register default command handlers"""
        self.register_command("help", self._cmd_help, "Show available commands")
        self.register_command("clear", self._cmd_clear, "Clear terminal output")
        self.register_command("status", self._cmd_status, "Show cluster status")
        self.register_command("jobs", self._cmd_jobs, "List recent jobs")
        self.register_command("workers", self._cmd_workers, "List workers")
        self.register_command("submit", self._cmd_submit, "Submit a job: submit <command>")
        self.register_command("cancel", self._cmd_cancel, "Cancel a job: cancel <job_id>")
        self.register_command("logs", self._cmd_logs, "View job logs: logs <job_id>")
        self.register_command("echo", self._cmd_echo, "Echo text")

    def register_command(self, name: str, handler: Callable, description: str = ""):
        """Register a command handler"""
        self._command_handlers[name] = {"handler": handler, "description": description}

    def _execute_command(self, command: str):
        """Execute a command"""
        self.output.append_command(command)

        parts = command.split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd_name in self._command_handlers:
            try:
                result = self._command_handlers[cmd_name]["handler"](args)
                if result:
                    self.output.append_text(result, "default", False)
            except Exception as e:
                self.output.append_text(f"Error: {str(e)}", "error", False)
        else:
            self.output.append_text(f"Unknown command: {cmd_name}", "error", False)
            self.output.append_text("Type 'help' for available commands", "info", False)

        self.command_executed.emit(command, "")

    def _clear_output(self):
        """Clear terminal output"""
        self.output.clear()
        self._show_welcome()

    # Command handlers
    def _cmd_help(self, args: str) -> str:
        """Help command handler"""
        lines = ["Available commands:", ""]
        for name, info in sorted(self._command_handlers.items()):
            desc = info.get("description", "")
            lines.append(f"  {name:<12} {desc}")
        return "\n".join(lines)

    def _cmd_clear(self, args: str) -> str:
        """Clear command handler"""
        self._clear_output()
        return ""

    def _cmd_status(self, args: str) -> str:
        """Status command handler"""
        # This would normally query the API
        return "Cluster Status: Connected\nWorkers: 3 active\nJobs: 2 running, 5 pending"

    def _cmd_jobs(self, args: str) -> str:
        """Jobs command handler"""
        return (
            "Recent jobs:\n  job-001  running   python train.py\n"
            "  job-002  pending   ./process.sh\n  job-003  completed python test.py"
        )

    def _cmd_workers(self, args: str) -> str:
        """Workers command handler"""
        return "Workers:\n  worker-001  active   CPU: 4/8  MEM: 8GB/16GB\n  worker-002  active   CPU: 2/4  MEM: 4GB/8GB"

    def _cmd_submit(self, args: str) -> str:
        """Submit command handler"""
        if not args:
            return "Usage: submit <command>\nExample: submit python script.py"
        return f"Job submitted: {args}\nJob ID: job-{datetime.now().strftime('%H%M%S')}"

    def _cmd_cancel(self, args: str) -> str:
        """Cancel command handler"""
        if not args:
            return "Usage: cancel <job_id>"
        return f"Cancelling job: {args}..."

    def _cmd_logs(self, args: str) -> str:
        """Logs command handler"""
        if not args:
            return "Usage: logs <job_id>"
        return f"Fetching logs for {args}...\n[Output would appear here]"

    def _cmd_echo(self, args: str) -> str:
        """Echo command handler"""
        return args

    def write(self, text: str, style: str = "default"):
        """Write text to terminal output"""
        self.output.append_text(text, style)

    def write_error(self, text: str):
        """Write error text"""
        self.output.append_text(text, "error")

    def write_success(self, text: str):
        """Write success text"""
        self.output.append_text(text, "success")

    def write_info(self, text: str):
        """Write info text"""
        self.output.append_text(text, "info")

    def set_api_client(self, client):
        """Set the API client for remote commands"""
        self._api_client = client
        self.output.append_text("Connected to cluster", "success")
