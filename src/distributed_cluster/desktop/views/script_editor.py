"""
Script Editor View - Python Scripting with Sandbox Execution
محرر السكربتات مع تنفيذ آمن في Sandbox
"""

import ast
import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QSyntaxHighlighter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
)

from ..api.client import APIClient
from ..resources.styles import COLORS


class PythonHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Python code"""

    KEYWORDS = [
        'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
        'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from',
        'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not',
        'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
        'True', 'False', 'None'
    ]

    BUILTINS = [
        'abs', 'all', 'any', 'bin', 'bool', 'bytes', 'callable', 'chr',
        'dict', 'dir', 'divmod', 'enumerate', 'eval', 'filter', 'float',
        'format', 'frozenset', 'getattr', 'globals', 'hasattr', 'hash',
        'help', 'hex', 'id', 'input', 'int', 'isinstance', 'issubclass',
        'iter', 'len', 'list', 'locals', 'map', 'max', 'min', 'next',
        'object', 'oct', 'open', 'ord', 'pow', 'print', 'range', 'repr',
        'reversed', 'round', 'set', 'setattr', 'slice', 'sorted', 'str',
        'sum', 'super', 'tuple', 'type', 'vars', 'zip'
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._formats = {}
        self._setup_formats()

    def _setup_formats(self):
        """Setup highlighting formats"""
        # Keywords
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6"))
        keyword_format.setFontWeight(QFont.Bold)
        self._formats['keyword'] = keyword_format

        # Builtins
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#DCDCAA"))
        self._formats['builtin'] = builtin_format

        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178"))
        self._formats['string'] = string_format

        # Comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))
        comment_format.setFontItalic(True)
        self._formats['comment'] = comment_format

        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))
        self._formats['number'] = number_format

        # Functions
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#DCDCAA"))
        self._formats['function'] = function_format

        # Classes
        class_format = QTextCharFormat()
        class_format.setForeground(QColor("#4EC9B0"))
        self._formats['class'] = class_format

    def highlightBlock(self, text: str):
        """Highlight a block of text"""
        import re

        # Keywords
        for keyword in self.KEYWORDS:
            pattern = rf'\b{keyword}\b'
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self._formats['keyword'])

        # Builtins
        for builtin in self.BUILTINS:
            pattern = rf'\b{builtin}\b'
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self._formats['builtin'])

        # Strings (single and double quotes)
        for pattern in [r'"[^"\\]*(\\.[^"\\]*)*"', r"'[^'\\]*(\\.[^'\\]*)*'"]:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self._formats['string'])

        # Comments
        for match in re.finditer(r'#.*$', text):
            self.setFormat(match.start(), match.end() - match.start(), self._formats['comment'])

        # Numbers
        for match in re.finditer(r'\b\d+\.?\d*\b', text):
            self.setFormat(match.start(), match.end() - match.start(), self._formats['number'])

        # Function definitions
        for match in re.finditer(r'(?<=def )\w+', text):
            self.setFormat(match.start(), match.end() - match.start(), self._formats['function'])

        # Class definitions
        for match in re.finditer(r'(?<=class )\w+', text):
            self.setFormat(match.start(), match.end() - match.start(), self._formats['class'])


class SandboxExecutor(QThread):
    """Thread for executing Python code in a sandboxed environment"""

    output_received = Signal(str)
    error_received = Signal(str)
    execution_finished = Signal(bool, str)  # success, result/error

    # Restricted built-ins for sandbox
    SAFE_BUILTINS = {
        'abs': abs, 'all': all, 'any': any, 'bin': bin, 'bool': bool,
        'bytes': bytes, 'callable': callable, 'chr': chr, 'dict': dict,
        'dir': dir, 'divmod': divmod, 'enumerate': enumerate, 'filter': filter,
        'float': float, 'format': format, 'frozenset': frozenset,
        'getattr': getattr, 'hasattr': hasattr, 'hash': hash, 'hex': hex,
        'id': id, 'int': int, 'isinstance': isinstance, 'issubclass': issubclass,
        'iter': iter, 'len': len, 'list': list, 'map': map, 'max': max,
        'min': min, 'next': next, 'object': object, 'oct': oct, 'ord': ord,
        'pow': pow, 'print': print, 'range': range, 'repr': repr,
        'reversed': reversed, 'round': round, 'set': set, 'slice': slice,
        'sorted': sorted, 'str': str, 'sum': sum, 'tuple': tuple,
        'type': type, 'vars': vars, 'zip': zip,
        'True': True, 'False': False, 'None': None,
    }

    # Blocked imports
    BLOCKED_MODULES = {
        'os', 'sys', 'subprocess', 'shutil', 'socket', 'http',
        'ftplib', 'smtplib', 'telnetlib', 'ssl', 'ctypes',
        'multiprocessing', 'threading', '_thread', 'concurrent',
        'asyncio', 'signal', 'resource', 'sysconfig', 'importlib'
    }

    def __init__(self, code: str, context: dict = None, parent=None):
        super().__init__(parent)
        self.code = code
        self.context = context or {}
        self._stdout = io.StringIO()
        self._stderr = io.StringIO()

    def run(self):
        """Execute code in sandbox"""
        try:
            # Validate code first (syntax check)
            try:
                ast.parse(self.code)
            except SyntaxError as e:
                self.error_received.emit(f"Syntax Error: {e}")
                self.execution_finished.emit(False, str(e))
                return

            # Check for dangerous imports
            if self._check_dangerous_imports():
                error = "Security Error: Blocked module import detected"
                self.error_received.emit(error)
                self.execution_finished.emit(False, error)
                return

            # Create sandboxed environment
            sandbox_globals = {
                '__builtins__': self.SAFE_BUILTINS,
                '__name__': '__sandbox__',
                '__doc__': None,
            }

            # Add safe context (API, etc.)
            sandbox_globals.update(self.context)

            # Capture output
            with redirect_stdout(self._stdout), redirect_stderr(self._stderr):
                exec(self.code, sandbox_globals)

            # Get output
            stdout_val = self._stdout.getvalue()
            stderr_val = self._stderr.getvalue()

            if stdout_val:
                self.output_received.emit(stdout_val)
            if stderr_val:
                self.error_received.emit(stderr_val)

            self.execution_finished.emit(True, stdout_val or "Execution completed successfully")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            self.error_received.emit(error_msg)
            self.execution_finished.emit(False, error_msg)

    def _check_dangerous_imports(self) -> bool:
        """Check for dangerous import statements"""
        try:
            tree = ast.parse(self.code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split('.')[0] in self.BLOCKED_MODULES:
                            return True
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split('.')[0] in self.BLOCKED_MODULES:
                        return True
            return False
        except:
            return True


class ScriptEditorView(QWidget):
    """Script Editor with Python sandbox execution

    Features:
    - Syntax highlighting
    - Code execution in sandbox
    - Script management (save/load)
    - Output console
    - API integration for cluster operations
    """

    refresh_requested = Signal()

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._current_script_name = "untitled.py"
        self._scripts = {}  # name -> code
        self._executor = None
        self._setup_ui()
        self._load_sample_scripts()

    def _setup_ui(self):
        """Setup the script editor UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Main content area with splitter
        main_splitter = QSplitter(Qt.Horizontal)

        # Left: Script list
        scripts_panel = self._create_scripts_panel()
        main_splitter.addWidget(scripts_panel)

        # Center: Editor + Output (vertical splitter)
        editor_output_splitter = QSplitter(Qt.Vertical)

        # Code editor
        editor_container = self._create_editor_container()
        editor_output_splitter.addWidget(editor_container)

        # Output console
        output_container = self._create_output_container()
        editor_output_splitter.addWidget(output_container)

        editor_output_splitter.setSizes([400, 200])
        main_splitter.addWidget(editor_output_splitter)

        # Right: API Documentation
        docs_panel = self._create_docs_panel()
        main_splitter.addWidget(docs_panel)

        main_splitter.setSizes([180, 600, 250])

        layout.addWidget(main_splitter)

    def _create_toolbar(self) -> QFrame:
        """Create the toolbar"""
        toolbar = QFrame()
        toolbar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_medium']};
                border-bottom: 1px solid {COLORS['border']};
                padding: 8px;
            }}
        """)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 8, 16, 8)

        # Title
        title = QLabel("🐍 Script Editor")
        title.setStyleSheet(f"""
            font-size: 18px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        layout.addWidget(title)

        layout.addSpacing(32)

        # Script name
        self.script_name_input = QLineEdit()
        self.script_name_input.setText(self._current_script_name)
        self.script_name_input.setPlaceholderText("Script name...")
        self.script_name_input.setMaximumWidth(200)
        self.script_name_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 12px;
            }}
        """)
        layout.addWidget(self.script_name_input)

        layout.addStretch()

        # Buttons
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
            QPushButton:pressed {{
                background-color: {COLORS['primary_dark']};
            }}
        """

        # New script
        new_btn = QPushButton("📄 New")
        new_btn.setStyleSheet(btn_style)
        new_btn.clicked.connect(self._on_new_script)
        layout.addWidget(new_btn)

        # Save script
        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet(btn_style)
        save_btn.clicked.connect(self._on_save_script)
        layout.addWidget(save_btn)

        # Load script
        load_btn = QPushButton("📂 Load")
        load_btn.setStyleSheet(btn_style)
        load_btn.clicked.connect(self._on_load_script)
        layout.addWidget(load_btn)

        layout.addSpacing(16)

        # Run button (prominent)
        run_btn = QPushButton("▶ Run Script")
        run_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['success']};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 24px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #2e7d32;
            }}
            QPushButton:pressed {{
                background-color: #1b5e20;
            }}
        """)
        run_btn.clicked.connect(self._on_run_script)
        layout.addWidget(run_btn)

        # Stop button
        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setStyleSheet(f"""
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
            QPushButton:disabled {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_muted']};
            }}
        """)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_script)
        layout.addWidget(self.stop_btn)

        return toolbar

    def _create_scripts_panel(self) -> QFrame:
        """Create the scripts list panel"""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_dark']};
                border-right: 1px solid {COLORS['border']};
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("  📁 Scripts")
        header.setStyleSheet(f"""
            font-size: 12px;
            font-weight: 600;
            color: {COLORS['text_muted']};
            padding: 12px 8px;
            background-color: {COLORS['bg_medium']};
        """)
        layout.addWidget(header)

        # Scripts list
        self.scripts_list = QListWidget()
        self.scripts_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 12px;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QListWidget::item:selected {{
                background-color: {COLORS['primary']};
            }}
            QListWidget::item:hover {{
                background-color: {COLORS['bg_light']};
            }}
        """)
        self.scripts_list.itemClicked.connect(self._on_script_selected)
        layout.addWidget(self.scripts_list)

        return panel

    def _create_editor_container(self) -> QFrame:
        """Create the code editor container"""
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_dark']};
            }}
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Editor header
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_medium']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)

        editor_label = QLabel("✏️ Code Editor")
        editor_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        header_layout.addWidget(editor_label)

        header_layout.addStretch()

        # Line/column indicator
        self.position_label = QLabel("Line 1, Col 1")
        self.position_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        header_layout.addWidget(self.position_label)

        layout.addWidget(header)

        # Code editor
        self.code_editor = QPlainTextEdit()
        self.code_editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: none;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                selection-background-color: {COLORS['primary']};
            }}
        """)
        self.code_editor.setPlaceholderText("# Write your Python script here...\n# Available APIs:\n#   - cluster: Cluster operations\n#   - jobs: Job management\n#   - workers: Worker control\n#   - log(msg): Print to console\n\nprint('Hello, NebulaCompute!')")
        self.code_editor.setTabStopDistance(40)
        self.code_editor.cursorPositionChanged.connect(self._update_position_label)

        # Add syntax highlighting
        self.highlighter = PythonHighlighter(self.code_editor.document())

        layout.addWidget(self.code_editor)

        return container

    def _create_output_container(self) -> QFrame:
        """Create the output console container"""
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_dark']};
                border-top: 1px solid {COLORS['border']};
            }}
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tabs for output/errors
        self.output_tabs = QTabWidget()
        self.output_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: {COLORS['bg_dark']};
            }}
            QTabBar::tab {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_secondary']};
                padding: 8px 16px;
                border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {COLORS['text_primary']};
                border-bottom: 2px solid {COLORS['primary']};
            }}
        """)

        # Output console
        self.output_console = QPlainTextEdit()
        self.output_console.setReadOnly(True)
        self.output_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1a1a1a;
                color: #00ff00;
                border: none;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 12px;
            }
        """)
        self.output_console.setPlaceholderText("Output will appear here...")
        self.output_tabs.addTab(self.output_console, "📤 Output")

        # Error console
        self.error_console = QPlainTextEdit()
        self.error_console.setReadOnly(True)
        self.error_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1a1a1a;
                color: #ff6b6b;
                border: none;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 12px;
            }
        """)
        self.error_console.setPlaceholderText("Errors will appear here...")
        self.output_tabs.addTab(self.error_console, "⚠️ Errors")

        layout.addWidget(self.output_tabs)

        # Status bar
        status_bar = QFrame()
        status_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_medium']};
                border-top: 1px solid {COLORS['border']};
            }}
        """)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(12, 4, 12, 4)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: none;
                border: none;
                color: {COLORS['text_secondary']};
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                color: {COLORS['text_primary']};
            }}
        """)
        clear_btn.clicked.connect(self._clear_output)
        status_layout.addWidget(clear_btn)

        layout.addWidget(status_bar)

        return container

    def _create_docs_panel(self) -> QFrame:
        """Create the API documentation panel"""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_dark']};
                border-left: 1px solid {COLORS['border']};
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("  📚 API Reference")
        header.setStyleSheet(f"""
            font-size: 12px;
            font-weight: 600;
            color: {COLORS['text_muted']};
            padding: 12px 8px;
            background-color: {COLORS['bg_medium']};
        """)
        layout.addWidget(header)

        # Documentation content
        docs = QTextEdit()
        docs.setReadOnly(True)
        docs.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: none;
                font-size: 12px;
                padding: 12px;
            }}
        """)
        docs.setHtml(self._get_api_docs_html())
        layout.addWidget(docs)

        return panel

    def _get_api_docs_html(self) -> str:
        """Get API documentation as HTML"""
        return f"""
        <style>
            h3 {{ color: {COLORS['primary']}; margin-top: 16px; }}
            code {{
                background-color: {COLORS['bg_light']};
                padding: 2px 6px;
                border-radius: 3px;
                font-family: monospace;
            }}
            .func {{ color: {COLORS['warning']}; }}
            .desc {{ color: {COLORS['text_secondary']}; font-size: 11px; }}
        </style>

        <h3>🔧 Available Objects</h3>

        <p><code class="func">cluster</code></p>
        <p class="desc">Cluster operations object</p>

        <p><code class="func">jobs</code></p>
        <p class="desc">Job management interface</p>

        <p><code class="func">workers</code></p>
        <p class="desc">Worker control interface</p>

        <h3>📝 Functions</h3>

        <p><code class="func">log(message)</code></p>
        <p class="desc">Print message to console</p>

        <p><code class="func">get_stats()</code></p>
        <p class="desc">Get cluster statistics</p>

        <p><code class="func">list_jobs()</code></p>
        <p class="desc">List all jobs</p>

        <p><code class="func">list_workers()</code></p>
        <p class="desc">List all workers</p>

        <p><code class="func">submit_job(name, command)</code></p>
        <p class="desc">Submit a new job</p>

        <h3>⚠️ Security</h3>
        <p class="desc">
        Scripts run in a <b>sandboxed environment</b>.
        The following are <b>blocked</b>:
        </p>
        <ul class="desc">
            <li>File system access (os, shutil)</li>
            <li>Network operations (socket, http)</li>
            <li>System calls (subprocess)</li>
            <li>Threading/multiprocessing</li>
        </ul>

        <h3>💡 Example</h3>
        <pre style="background: {COLORS['bg_light']}; padding: 8px; border-radius: 4px; font-size: 11px;">
# Get cluster stats
stats = get_stats()
log(f"Workers: {{stats['workers']}}")
log(f"Jobs: {{stats['jobs']}}")

# List jobs
for job in list_jobs():
    log(f"Job: {{job['name']}}")
        </pre>
        """

    def _load_sample_scripts(self):
        """Load sample scripts"""
        self._scripts = {
            "hello_world.py": '# Hello World Script\nprint("Hello, NebulaCompute!")\nprint("Welcome to scripting!")',
            "cluster_info.py": '''# Cluster Information Script
stats = get_stats()
log("=== Cluster Statistics ===")
log(f"Total Workers: {stats.get('workers', 0)}")
log(f"Active Jobs: {stats.get('jobs', 0)}")
log(f"CPU Usage: {stats.get('cpu', 0)}%")
log(f"Memory Usage: {stats.get('memory', 0)}%")
''',
            "job_monitor.py": '''# Job Monitor Script
jobs = list_jobs()
log(f"Found {len(jobs)} jobs")
for job in jobs[:10]:
    status = job.get('status', 'unknown')
    name = job.get('name', 'unnamed')
    log(f"[{status.upper()}] {name}")
''',
            "automation_example.py": '''# Automation Example
# This script runs periodic checks

def check_cluster():
    stats = get_stats()
    workers = stats.get('workers', 0)
    if workers < 3:
        log("⚠️ Warning: Low worker count!")
    else:
        log(f"✅ Cluster healthy: {workers} workers")

def check_jobs():
    jobs = list_jobs()
    pending = [j for j in jobs if j.get('status') == 'pending']
    if len(pending) > 10:
        log("⚠️ Warning: Many pending jobs!")
    log(f"📋 Pending jobs: {len(pending)}")

log("Starting cluster check...")
check_cluster()
check_jobs()
log("Check complete!")
'''
        }

        # Update scripts list
        self._update_scripts_list()

    def _update_scripts_list(self):
        """Update the scripts list widget"""
        self.scripts_list.clear()
        for name in sorted(self._scripts.keys()):
            item = QListWidgetItem(f"📄 {name}")
            item.setData(Qt.UserRole, name)
            self.scripts_list.addItem(item)

    def _update_position_label(self):
        """Update cursor position label"""
        cursor = self.code_editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.position_label.setText(f"Line {line}, Col {col}")

    def _on_new_script(self):
        """Create a new script"""
        self.code_editor.clear()
        self.script_name_input.setText("untitled.py")
        self._current_script_name = "untitled.py"
        self.status_label.setText("New script created")

    def _on_save_script(self):
        """Save current script"""
        name = self.script_name_input.text().strip()
        if not name:
            name = "untitled.py"
        if not name.endswith('.py'):
            name += '.py'

        code = self.code_editor.toPlainText()
        self._scripts[name] = code
        self._current_script_name = name
        self._update_scripts_list()
        self.status_label.setText(f"Saved: {name}")

    def _on_load_script(self):
        """Load script from file"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Script", "", "Python Files (*.py);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'r') as f:
                    code = f.read()

                name = filename.split('/')[-1]
                self.code_editor.setPlainText(code)
                self.script_name_input.setText(name)
                self._current_script_name = name
                self._scripts[name] = code
                self._update_scripts_list()
                self.status_label.setText(f"Loaded: {name}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load file: {e}")

    def _on_script_selected(self, item: QListWidgetItem):
        """Handle script selection from list"""
        name = item.data(Qt.UserRole)
        if name in self._scripts:
            self.code_editor.setPlainText(self._scripts[name])
            self.script_name_input.setText(name)
            self._current_script_name = name
            self.status_label.setText(f"Opened: {name}")

    def _on_run_script(self):
        """Run the current script"""
        code = self.code_editor.toPlainText()
        if not code.strip():
            self.status_label.setText("No code to execute")
            return

        # Clear previous output
        self._clear_output()

        # Update UI
        self.stop_btn.setEnabled(True)
        self.status_label.setText("Running...")
        self.output_console.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] Executing script...\n")

        # Create sandbox context with safe APIs
        context = self._create_sandbox_context()

        # Execute in thread
        self._executor = SandboxExecutor(code, context)
        self._executor.output_received.connect(self._on_output_received)
        self._executor.error_received.connect(self._on_error_received)
        self._executor.execution_finished.connect(self._on_execution_finished)
        self._executor.start()

    def _on_stop_script(self):
        """Stop the running script"""
        if self._executor and self._executor.isRunning():
            self._executor.terminate()
            self._executor.wait()
            self.status_label.setText("Execution stopped")
            self.output_console.appendPlainText("\n[Execution stopped by user]")
        self.stop_btn.setEnabled(False)

    def _create_sandbox_context(self) -> dict:
        """Create the sandbox execution context with safe APIs"""
        # Log function that writes to output
        def log(message):
            print(str(message))

        # Mock cluster stats
        def get_stats():
            if self.api_client:
                # Would fetch real stats
                pass
            return {
                'workers': 5,
                'jobs': 12,
                'cpu': 45.2,
                'memory': 62.8,
                'pending': 3,
                'running': 5,
                'completed': 4
            }

        # Mock job list
        def list_jobs():
            if self.api_client:
                # Would fetch real jobs
                pass
            return [
                {'id': '1', 'name': 'data_processing', 'status': 'running'},
                {'id': '2', 'name': 'ml_training', 'status': 'pending'},
                {'id': '3', 'name': 'batch_export', 'status': 'completed'},
            ]

        # Mock worker list
        def list_workers():
            if self.api_client:
                # Would fetch real workers
                pass
            return [
                {'id': 'w1', 'name': 'worker-1', 'status': 'online', 'cpu': 35},
                {'id': 'w2', 'name': 'worker-2', 'status': 'online', 'cpu': 78},
                {'id': 'w3', 'name': 'worker-3', 'status': 'offline', 'cpu': 0},
            ]

        # Submit job (mock)
        def submit_job(name: str, command: str):
            log(f"Job submitted: {name} -> {command}")
            return {'id': 'new-job-id', 'status': 'pending'}

        return {
            'log': log,
            'get_stats': get_stats,
            'list_jobs': list_jobs,
            'list_workers': list_workers,
            'submit_job': submit_job,
            'cluster': {'name': 'NebulaCompute', 'version': '0.1.0'},
            'datetime': datetime,
        }

    def _on_output_received(self, output: str):
        """Handle output from script"""
        self.output_console.appendPlainText(output)

    def _on_error_received(self, error: str):
        """Handle error from script"""
        self.error_console.appendPlainText(error)
        self.output_tabs.setCurrentIndex(1)  # Switch to errors tab

    def _on_execution_finished(self, success: bool, result: str):
        """Handle execution completion"""
        self.stop_btn.setEnabled(False)
        if success:
            self.status_label.setText("Execution completed successfully")
            self.output_console.appendPlainText(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✅ Completed")
        else:
            self.status_label.setText("Execution failed")
            self.output_console.appendPlainText(f"\n[{datetime.now().strftime('%H:%M:%S')}] ❌ Failed")

    def _clear_output(self):
        """Clear output consoles"""
        self.output_console.clear()
        self.error_console.clear()

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
