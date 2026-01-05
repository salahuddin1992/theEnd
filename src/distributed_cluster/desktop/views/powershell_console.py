"""
PowerShell Console View - Integrated PowerShell Terminal
وحدة تحكم PowerShell المدمجة
"""

import platform
import subprocess
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..api.client import APIClient
from ..resources.styles import COLORS


class CommandHistory:
    """Command history manager"""

    def __init__(self, max_size: int = 100):
        self.history: List[str] = []
        self.max_size = max_size
        self.index = -1

    def add(self, command: str):
        """Add a command to history"""
        if command and (not self.history or self.history[-1] != command):
            self.history.append(command)
            if len(self.history) > self.max_size:
                self.history.pop(0)
        self.index = len(self.history)

    def previous(self) -> Optional[str]:
        """Get previous command"""
        if self.history and self.index > 0:
            self.index -= 1
            return self.history[self.index]
        return None

    def next(self) -> Optional[str]:
        """Get next command"""
        if self.history and self.index < len(self.history) - 1:
            self.index += 1
            return self.history[self.index]
        elif self.index == len(self.history) - 1:
            self.index = len(self.history)
            return ""
        return None

    def reset_index(self):
        """Reset navigation index"""
        self.index = len(self.history)


class ShellProcess(QProcess):
    """PowerShell/Bash process wrapper"""

    output_received = Signal(str)
    error_received = Signal(str)
    command_finished = Signal(int)  # exit code

    def __init__(self, shell_type: str = "auto", parent=None):
        super().__init__(parent)
        self.shell_type = shell_type
        self._setup_shell()

        # Connect signals
        self.readyReadStandardOutput.connect(self._on_stdout)
        self.readyReadStandardError.connect(self._on_stderr)
        self.finished.connect(self._on_finished)

    def _setup_shell(self):
        """Setup the shell process"""
        if self.shell_type == "auto":
            if platform.system() == "Windows":
                self.shell_type = "powershell"
            else:
                self.shell_type = "bash"

        if self.shell_type == "powershell":
            # Try PowerShell Core first, then Windows PowerShell
            if self._find_executable("pwsh"):
                self.setProgram("pwsh")
            else:
                self.setProgram("powershell")
            self.setArguments(["-NoLogo", "-NoExit", "-Command", "-"])
        elif self.shell_type == "bash":
            self.setProgram("/bin/bash")
            self.setArguments(["--norc", "-i"])
        elif self.shell_type == "cmd":
            self.setProgram("cmd.exe")
            self.setArguments(["/Q"])

    def _find_executable(self, name: str) -> bool:
        """Check if executable exists"""
        try:
            result = subprocess.run(
                ["which" if platform.system() != "Windows" else "where", name], capture_output=True, text=True
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def execute_command(self, command: str):
        """Execute a command"""
        if self.state() != QProcess.Running:
            self.start()
            self.waitForStarted()

        # Write command to process
        self.write((command + "\n").encode())

    def _on_stdout(self):
        """Handle stdout data"""
        data = self.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self.output_received.emit(data)

    def _on_stderr(self):
        """Handle stderr data"""
        data = self.readAllStandardError().data().decode("utf-8", errors="replace")
        self.error_received.emit(data)

    def _on_finished(self, exit_code: int, exit_status):
        """Handle process finished"""
        self.command_finished.emit(exit_code)


class PowerShellConsoleView(QWidget):
    """PowerShell Console with integrated terminal

    Features:
    - Interactive PowerShell/Bash terminal
    - Command history
    - Quick commands panel
    - Script execution
    - Cluster-aware commands
    """

    refresh_requested = Signal()

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._history = CommandHistory()
        self._process: Optional[ShellProcess] = None
        self._current_shell = "auto"

        self._setup_ui()
        self._start_shell()
        self._load_quick_commands()

    def _setup_ui(self):
        """Setup the console UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Main content with splitter
        main_splitter = QSplitter(Qt.Horizontal)

        # Left: Console
        console_container = self._create_console_container()
        main_splitter.addWidget(console_container)

        # Right: Quick commands and help
        side_panel = self._create_side_panel()
        main_splitter.addWidget(side_panel)

        main_splitter.setSizes([800, 250])

        layout.addWidget(main_splitter)

    def _create_toolbar(self) -> QFrame:
        """Create the toolbar"""
        toolbar = QFrame()
        toolbar.setStyleSheet(
            f"""
            QFrame {{
                background-color: {COLORS['bg_medium']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """
        )

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 8, 16, 8)

        # Title with shell icon
        title = QLabel("💻 Terminal")
        title.setStyleSheet(
            f"""
            font-size: 18px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """
        )
        layout.addWidget(title)

        layout.addSpacing(24)

        # Shell selector
        shell_label = QLabel("Shell:")
        shell_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(shell_label)

        self.shell_combo = QComboBox()
        self.shell_combo.addItems(["Auto", "PowerShell", "Bash", "CMD"])
        self.shell_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 120px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                border: none;
            }}
        """
        )
        self.shell_combo.currentTextChanged.connect(self._on_shell_changed)
        layout.addWidget(self.shell_combo)

        # Current directory
        layout.addSpacing(16)

        dir_label = QLabel("📁")
        dir_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(dir_label)

        self.cwd_label = QLabel(str(Path.home()))
        self.cwd_label.setStyleSheet(
            f"""
            color: {COLORS['text_secondary']};
            font-family: monospace;
            font-size: 12px;
        """
        )
        layout.addWidget(self.cwd_label)

        layout.addStretch()

        btn_style = f"""
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary']};
                border-color: {COLORS['primary']};
            }}
        """

        # Clear button
        clear_btn = QPushButton("🗑️ Clear")
        clear_btn.setStyleSheet(btn_style)
        clear_btn.clicked.connect(self._clear_console)
        layout.addWidget(clear_btn)

        # Kill button
        kill_btn = QPushButton("⏹️ Kill")
        kill_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['danger']};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #c62828;
            }}
        """
        )
        kill_btn.clicked.connect(self._kill_process)
        layout.addWidget(kill_btn)

        # New tab button
        new_tab_btn = QPushButton("➕ New Tab")
        new_tab_btn.setStyleSheet(btn_style)
        new_tab_btn.clicked.connect(self._new_tab)
        layout.addWidget(new_tab_btn)

        return toolbar

    def _create_console_container(self) -> QWidget:
        """Create the console container"""
        container = QWidget()
        container.setStyleSheet(f"background-color: {COLORS['bg_dark']};")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Console tabs
        self.console_tabs = QTabWidget()
        self.console_tabs.setTabsClosable(True)
        self.console_tabs.tabCloseRequested.connect(self._close_tab)
        self.console_tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: none;
                background-color: #1a1a1a;
            }}
            QTabBar::tab {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_secondary']};
                padding: 8px 16px;
                border: none;
                border-bottom: 2px solid transparent;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                color: {COLORS['text_primary']};
                border-bottom: 2px solid {COLORS['primary']};
            }}
            QTabBar::close-button {{
                image: none;
                subcontrol-position: right;
            }}
        """
        )

        # Create first terminal tab
        terminal_widget = self._create_terminal_widget()
        self.console_tabs.addTab(terminal_widget, "Terminal 1")

        layout.addWidget(self.console_tabs)

        return container

    def _create_terminal_widget(self) -> QWidget:
        """Create a terminal widget"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Output area
        output = QPlainTextEdit()
        output.setReadOnly(True)
        output.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: #1a1a1a;
                color: #00ff00;
                border: none;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                selection-background-color: {COLORS['primary']};
            }}
        """
        )
        output.setMaximumBlockCount(10000)  # Limit buffer size

        # Welcome message
        welcome = self._get_welcome_message()
        output.setPlainText(welcome)

        layout.addWidget(output)

        # Input area
        input_frame = QFrame()
        input_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: #0d0d0d;
                border-top: 1px solid {COLORS['border']};
            }}
        """
        )
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 4, 8, 4)

        # Prompt
        prompt = QLabel("❯")
        prompt.setStyleSheet(
            f"""
            color: {COLORS['primary']};
            font-size: 14px;
            font-weight: bold;
        """
        )
        input_layout.addWidget(prompt)

        # Input field
        input_field = QLineEdit()
        input_field.setStyleSheet(
            """
            QLineEdit {
                background-color: transparent;
                color: #00ff00;
                border: none;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                padding: 8px;
            }
        """
        )
        input_field.setPlaceholderText("Enter command...")
        input_field.returnPressed.connect(lambda: self._execute_command(input_field, output))

        # History navigation
        input_field.installEventFilter(self)
        input_layout.addWidget(input_field)

        layout.addWidget(input_frame)

        # Store references
        widget.output = output
        widget.input_field = input_field

        return widget

    def eventFilter(self, obj, event):
        """Handle key events for history navigation"""
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.KeyPress:
            key = event.key()

            if key == Qt.Key_Up:
                prev_cmd = self._history.previous()
                if prev_cmd is not None:
                    obj.setText(prev_cmd)
                return True

            elif key == Qt.Key_Down:
                next_cmd = self._history.next()
                if next_cmd is not None:
                    obj.setText(next_cmd)
                return True

        return super().eventFilter(obj, event)

    def _create_side_panel(self) -> QWidget:
        """Create the side panel with quick commands"""
        panel = QWidget()
        panel.setStyleSheet(
            f"""
            QWidget {{
                background-color: {COLORS['bg_dark']};
                border-left: 1px solid {COLORS['border']};
            }}
        """
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tabs for different panels
        side_tabs = QTabWidget()
        side_tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: none;
                background-color: {COLORS['bg_dark']};
            }}
            QTabBar::tab {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_secondary']};
                padding: 6px 12px;
                border: none;
                font-size: 11px;
            }}
            QTabBar::tab:selected {{
                color: {COLORS['text_primary']};
                border-bottom: 2px solid {COLORS['primary']};
            }}
        """
        )

        # Quick commands tab
        quick_widget = self._create_quick_commands_panel()
        side_tabs.addTab(quick_widget, "⚡ Quick")

        # History tab
        history_widget = self._create_history_panel()
        side_tabs.addTab(history_widget, "📜 History")

        # Snippets tab
        snippets_widget = self._create_snippets_panel()
        side_tabs.addTab(snippets_widget, "📋 Snippets")

        layout.addWidget(side_tabs)

        return panel

    def _create_quick_commands_panel(self) -> QWidget:
        """Create quick commands panel"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Section: System
        sys_label = QLabel("🖥️ System")
        sys_label.setStyleSheet(
            f"""
            color: {COLORS['text_muted']};
            font-size: 11px;
            font-weight: 600;
        """
        )
        layout.addWidget(sys_label)

        self.quick_commands = QListWidget()
        self.quick_commands.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: none;
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {COLORS['bg_light']};
            }}
            QListWidget::item:selected {{
                background-color: {COLORS['primary']};
            }}
        """
        )
        self.quick_commands.itemDoubleClicked.connect(self._on_quick_command_clicked)
        layout.addWidget(self.quick_commands)

        return widget

    def _create_history_panel(self) -> QWidget:
        """Create command history panel"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.history_list = QListWidget()
        self.history_list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: none;
                font-family: monospace;
                font-size: 11px;
            }}
            QListWidget::item {{
                padding: 6px;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QListWidget::item:selected {{
                background-color: {COLORS['primary']};
            }}
        """
        )
        self.history_list.itemDoubleClicked.connect(self._on_history_item_clicked)
        layout.addWidget(self.history_list)

        # Clear history button
        clear_btn = QPushButton("Clear History")
        clear_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['danger']};
                color: white;
            }}
        """
        )
        clear_btn.clicked.connect(self._clear_history)
        layout.addWidget(clear_btn)

        return widget

    def _create_snippets_panel(self) -> QWidget:
        """Create code snippets panel"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.snippets_list = QListWidget()
        self.snippets_list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: none;
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QListWidget::item:selected {{
                background-color: {COLORS['primary']};
            }}
        """
        )
        self.snippets_list.itemDoubleClicked.connect(self._on_snippet_clicked)

        # Add default snippets
        snippets = [
            ("📊 Get Cluster Stats", "curl http://localhost:8000/api/stats"),
            ("📋 List Jobs", "curl http://localhost:8000/api/jobs"),
            ("💻 List Workers", "curl http://localhost:8000/api/workers"),
            ("🔍 System Info", "Get-ComputerInfo" if platform.system() == "Windows" else "uname -a"),
            ("📁 List Processes", "Get-Process" if platform.system() == "Windows" else "ps aux"),
            ("🌐 Network Info", "Get-NetIPAddress" if platform.system() == "Windows" else "ip addr"),
            ("💾 Disk Usage", "Get-PSDrive" if platform.system() == "Windows" else "df -h"),
            ("🔧 Environment", "$env:PATH" if platform.system() == "Windows" else "echo $PATH"),
        ]

        for name, cmd in snippets:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, cmd)
            self.snippets_list.addItem(item)

        layout.addWidget(self.snippets_list)

        return widget

    def _get_welcome_message(self) -> str:
        """Get welcome message"""
        shell_name = "PowerShell" if platform.system() == "Windows" else "Bash"
        return f"""
╔══════════════════════════════════════════════════════════════╗
║  ☁ NebulaCompute Terminal                                    ║
║  {shell_name} Console - Type commands below                        ║
╚══════════════════════════════════════════════════════════════╝

Type 'help' for available commands.
────────────────────────────────────────────────────────────────

"""

    def _load_quick_commands(self):
        """Load quick commands"""
        if platform.system() == "Windows":
            commands = [
                ("📊 System Info", "systeminfo"),
                ("💻 CPU Info", "wmic cpu get name"),
                ("💾 Memory Info", "wmic memorychip get capacity"),
                ("🔍 Processes", "Get-Process | Sort-Object CPU -Descending | Select-Object -First 10"),
                ("🌐 IP Config", "ipconfig"),
                ("📁 Current Dir", "Get-ChildItem"),
                ("🔧 Services", "Get-Service | Where-Object {$_.Status -eq 'Running'}"),
                ("📋 Tasks", "schtasks /query"),
                ("🖥️ OS Info", "$PSVersionTable"),
                ("🔒 Firewall", "Get-NetFirewallProfile"),
            ]
        else:
            commands = [
                ("📊 System Info", "uname -a"),
                ("💻 CPU Info", "cat /proc/cpuinfo | head -20"),
                ("💾 Memory Info", "free -h"),
                ("🔍 Processes", "ps aux --sort=-%cpu | head -10"),
                ("🌐 IP Config", "ip addr"),
                ("📁 Current Dir", "ls -la"),
                ("🔧 Services", "systemctl list-units --type=service --state=running"),
                ("📋 Cron Jobs", "crontab -l"),
                ("🖥️ Disk Usage", "df -h"),
                ("🔒 Open Ports", "netstat -tuln"),
            ]

        for name, cmd in commands:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, cmd)
            self.quick_commands.addItem(item)

    def _start_shell(self):
        """Start the shell process"""
        shell_type = self.shell_combo.currentText().lower()
        self._process = ShellProcess(shell_type)
        self._process.output_received.connect(self._on_output)
        self._process.error_received.connect(self._on_error)
        self._process.start()

    def _execute_command(self, input_field: QLineEdit, output: QPlainTextEdit):
        """Execute a command"""
        command = input_field.text().strip()
        if not command:
            return

        # Add to history
        self._history.add(command)
        self._update_history_list()

        # Show command in output
        output.appendPlainText(f"❯ {command}")

        # Special commands
        if command.lower() == "clear" or command.lower() == "cls":
            output.clear()
            input_field.clear()
            return

        if command.lower() == "exit":
            self._kill_process()
            input_field.clear()
            return

        if command.lower() == "help":
            self._show_help(output)
            input_field.clear()
            return

        # Execute via process
        if self._process and self._process.state() == QProcess.Running:
            self._process.execute_command(command)
        else:
            # Restart process if needed
            self._start_shell()
            self._process.execute_command(command)

        input_field.clear()

    def _on_output(self, data: str):
        """Handle output from process"""
        current_widget = self.console_tabs.currentWidget()
        if current_widget and hasattr(current_widget, "output"):
            current_widget.output.appendPlainText(data.rstrip())

            # Update current directory if changed
            if "cd " in data or "Set-Location" in data:
                self._update_cwd()

    def _on_error(self, data: str):
        """Handle error from process"""
        current_widget = self.console_tabs.currentWidget()
        if current_widget and hasattr(current_widget, "output"):
            # Show errors in red (using HTML)
            current_widget.output.appendHtml(f'<span style="color: #ff6b6b;">{data.rstrip()}</span>')

    def _show_help(self, output: QPlainTextEdit):
        """Show help message"""
        help_text = """
╔══════════════════════════════════════════════════════════════╗
║  NebulaCompute Terminal - Help                               ║
╚══════════════════════════════════════════════════════════════╝

Built-in Commands:
  help     - Show this help message
  clear    - Clear the terminal
  exit     - Close the terminal session

Navigation:
  ↑/↓      - Browse command history
  Tab      - Auto-complete (where supported)

Quick Commands:
  Double-click items in the Quick panel to execute

Tips:
  • Use the snippets panel for common cluster operations
  • Command history is preserved across sessions
  • Multiple terminal tabs are supported

────────────────────────────────────────────────────────────────
"""
        output.appendPlainText(help_text)

    def _update_cwd(self):
        """Update current working directory display"""
        if self._process and self._process.state() == QProcess.Running:
            # Try to get current directory
            if platform.system() == "Windows":
                self._process.execute_command("(Get-Location).Path")
            else:
                self._process.execute_command("pwd")

    def _on_shell_changed(self, shell_type: str):
        """Handle shell type change"""
        self._kill_process()
        self._current_shell = shell_type.lower()
        self._start_shell()

        current_widget = self.console_tabs.currentWidget()
        if current_widget and hasattr(current_widget, "output"):
            current_widget.output.clear()
            current_widget.output.setPlainText(self._get_welcome_message())

    def _clear_console(self):
        """Clear the current console"""
        current_widget = self.console_tabs.currentWidget()
        if current_widget and hasattr(current_widget, "output"):
            current_widget.output.clear()

    def _kill_process(self):
        """Kill the current shell process"""
        if self._process:
            self._process.kill()
            self._process.waitForFinished()

    def _new_tab(self):
        """Create a new terminal tab"""
        tab_count = self.console_tabs.count() + 1
        terminal_widget = self._create_terminal_widget()
        self.console_tabs.addTab(terminal_widget, f"Terminal {tab_count}")
        self.console_tabs.setCurrentWidget(terminal_widget)

    def _close_tab(self, index: int):
        """Close a terminal tab"""
        if self.console_tabs.count() > 1:
            self.console_tabs.removeTab(index)

    def _on_quick_command_clicked(self, item: QListWidgetItem):
        """Execute a quick command"""
        command = item.data(Qt.UserRole)
        if command:
            current_widget = self.console_tabs.currentWidget()
            if current_widget and hasattr(current_widget, "input_field"):
                current_widget.input_field.setText(command)
                self._execute_command(current_widget.input_field, current_widget.output)

    def _on_history_item_clicked(self, item: QListWidgetItem):
        """Use a command from history"""
        command = item.text()
        current_widget = self.console_tabs.currentWidget()
        if current_widget and hasattr(current_widget, "input_field"):
            current_widget.input_field.setText(command)
            current_widget.input_field.setFocus()

    def _on_snippet_clicked(self, item: QListWidgetItem):
        """Execute a snippet"""
        command = item.data(Qt.UserRole)
        if command:
            current_widget = self.console_tabs.currentWidget()
            if current_widget and hasattr(current_widget, "input_field"):
                current_widget.input_field.setText(command)
                self._execute_command(current_widget.input_field, current_widget.output)

    def _update_history_list(self):
        """Update the history list widget"""
        self.history_list.clear()
        for cmd in reversed(self._history.history[-50:]):  # Show last 50
            self.history_list.addItem(cmd)

    def _clear_history(self):
        """Clear command history"""
        self._history.history.clear()
        self._history.reset_index()
        self.history_list.clear()

    def closeEvent(self, event):
        """Handle widget close"""
        self._kill_process()
        super().closeEvent(event)

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
