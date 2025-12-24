"""
Plugin Manager View - Plugin Management with Hot-Reload Support
مدير البلجنات مع دعم إعادة التحميل أثناء التشغيل
"""

import importlib
import importlib.util
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QFileSystemWatcher, QThread, Signal, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QProgressBar,
    QCheckBox,
)

from ..api.client import APIClient
from ..resources.styles import COLORS


class PluginInfo:
    """Information about a loaded plugin"""

    def __init__(
        self,
        name: str,
        path: str,
        version: str = "1.0.0",
        description: str = "",
        author: str = "Unknown",
        enabled: bool = True,
        module: Any = None
    ):
        self.name = name
        self.path = path
        self.version = version
        self.description = description
        self.author = author
        self.enabled = enabled
        self.module = module
        self.loaded_at = datetime.now()
        self.last_reload = None
        self.error = None


class PluginLoader(QThread):
    """Thread for loading plugins"""

    plugin_loaded = Signal(object)  # PluginInfo
    plugin_error = Signal(str, str)  # plugin_name, error_message
    loading_complete = Signal()

    def __init__(self, plugin_dir: str, parent=None):
        super().__init__(parent)
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, PluginInfo] = {}

    def run(self):
        """Load all plugins from directory"""
        plugin_path = Path(self.plugin_dir)

        if not plugin_path.exists():
            plugin_path.mkdir(parents=True, exist_ok=True)

        # Find all Python files
        for py_file in plugin_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            try:
                plugin_info = self._load_plugin(py_file)
                if plugin_info:
                    self.plugins[plugin_info.name] = plugin_info
                    self.plugin_loaded.emit(plugin_info)
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                self.plugin_error.emit(py_file.stem, error_msg)

        # Also check for package plugins (directories with __init__.py)
        for subdir in plugin_path.iterdir():
            if subdir.is_dir() and (subdir / "__init__.py").exists():
                try:
                    plugin_info = self._load_plugin(subdir / "__init__.py", package=True)
                    if plugin_info:
                        self.plugins[plugin_info.name] = plugin_info
                        self.plugin_loaded.emit(plugin_info)
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    self.plugin_error.emit(subdir.name, error_msg)

        self.loading_complete.emit()

    def _load_plugin(self, path: Path, package: bool = False) -> Optional[PluginInfo]:
        """Load a single plugin"""
        module_name = path.parent.name if package else path.stem

        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Extract plugin metadata
        name = getattr(module, 'PLUGIN_NAME', module_name)
        version = getattr(module, 'PLUGIN_VERSION', '1.0.0')
        description = getattr(module, 'PLUGIN_DESCRIPTION', getattr(module, '__doc__', '') or '')
        author = getattr(module, 'PLUGIN_AUTHOR', 'Unknown')

        return PluginInfo(
            name=name,
            path=str(path),
            version=version,
            description=description.strip(),
            author=author,
            enabled=True,
            module=module
        )


class PluginCard(QFrame):
    """A card widget displaying plugin information"""

    toggle_requested = Signal(str, bool)  # plugin_name, enabled
    reload_requested = Signal(str)  # plugin_name
    unload_requested = Signal(str)  # plugin_name
    configure_requested = Signal(str)  # plugin_name

    def __init__(self, plugin: PluginInfo, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self._setup_ui()

    def _setup_ui(self):
        """Setup the card UI"""
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_medium']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 16px;
            }}
            QFrame:hover {{
                border-color: {COLORS['primary']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header row
        header_layout = QHBoxLayout()

        # Enable checkbox
        self.enable_checkbox = QCheckBox()
        self.enable_checkbox.setChecked(self.plugin.enabled)
        self.enable_checkbox.toggled.connect(
            lambda checked: self.toggle_requested.emit(self.plugin.name, checked)
        )
        header_layout.addWidget(self.enable_checkbox)

        # Plugin icon and name
        icon_label = QLabel("🔌")
        icon_label.setStyleSheet("font-size: 24px;")
        header_layout.addWidget(icon_label)

        name_label = QLabel(self.plugin.name)
        name_label.setStyleSheet(f"""
            font-size: 16px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        header_layout.addWidget(name_label)

        version_label = QLabel(f"v{self.plugin.version}")
        version_label.setStyleSheet(f"""
            font-size: 11px;
            color: {COLORS['text_muted']};
            background-color: {COLORS['bg_light']};
            padding: 2px 8px;
            border-radius: 4px;
        """)
        header_layout.addWidget(version_label)

        header_layout.addStretch()

        # Status indicator
        self.status_label = QLabel("●")
        self.status_label.setStyleSheet(f"""
            font-size: 10px;
            color: {COLORS['success'] if self.plugin.enabled else COLORS['text_muted']};
        """)
        header_layout.addWidget(self.status_label)

        layout.addLayout(header_layout)

        # Description
        if self.plugin.description:
            desc_label = QLabel(self.plugin.description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(f"""
                color: {COLORS['text_secondary']};
                font-size: 12px;
            """)
            layout.addWidget(desc_label)

        # Author and path
        info_layout = QHBoxLayout()

        author_label = QLabel(f"👤 {self.plugin.author}")
        author_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        info_layout.addWidget(author_label)

        info_layout.addStretch()

        path_label = QLabel(f"📁 {Path(self.plugin.path).name}")
        path_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        info_layout.addWidget(path_label)

        layout.addLayout(info_layout)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_style = f"""
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary']};
                color: white;
                border-color: {COLORS['primary']};
            }}
        """

        # Configure button
        config_btn = QPushButton("⚙️ Configure")
        config_btn.setStyleSheet(btn_style)
        config_btn.clicked.connect(lambda: self.configure_requested.emit(self.plugin.name))
        btn_layout.addWidget(config_btn)

        # Reload button
        reload_btn = QPushButton("🔄 Reload")
        reload_btn.setStyleSheet(btn_style)
        reload_btn.clicked.connect(lambda: self.reload_requested.emit(self.plugin.name))
        btn_layout.addWidget(reload_btn)

        # Unload button
        unload_btn = QPushButton("❌ Unload")
        unload_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['danger']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['danger']};
                color: white;
                border-color: {COLORS['danger']};
            }}
        """)
        unload_btn.clicked.connect(lambda: self.unload_requested.emit(self.plugin.name))
        btn_layout.addWidget(unload_btn)

        layout.addLayout(btn_layout)

    def update_status(self, enabled: bool):
        """Update the plugin status display"""
        self.plugin.enabled = enabled
        self.enable_checkbox.setChecked(enabled)
        self.status_label.setStyleSheet(f"""
            font-size: 10px;
            color: {COLORS['success'] if enabled else COLORS['text_muted']};
        """)


class PluginManagerView(QWidget):
    """Plugin Manager with Hot-Reload support

    Features:
    - Load/unload plugins dynamically
    - Hot-reload on file changes
    - Plugin configuration
    - Plugin marketplace (future)
    - Event hooks integration
    """

    refresh_requested = Signal()

    def __init__(self, api_client: Optional[APIClient] = None, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self._plugins: Dict[str, PluginInfo] = {}
        self._plugin_cards: Dict[str, PluginCard] = {}
        self._watcher = QFileSystemWatcher()
        self._plugin_dir = self._get_plugin_directory()

        self._setup_ui()
        self._setup_file_watcher()
        self._load_plugins()
        self._create_sample_plugins()

    def _get_plugin_directory(self) -> str:
        """Get the plugins directory path"""
        # Use a user-specific plugins directory
        home = Path.home()
        plugin_dir = home / ".nebulacompute" / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        return str(plugin_dir)

    def _setup_ui(self):
        """Setup the plugin manager UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Main content with splitter
        main_splitter = QSplitter(Qt.Horizontal)

        # Left: Plugin list/grid
        plugins_container = self._create_plugins_container()
        main_splitter.addWidget(plugins_container)

        # Right: Details and logs
        details_container = self._create_details_container()
        main_splitter.addWidget(details_container)

        main_splitter.setSizes([700, 350])

        layout.addWidget(main_splitter)

    def _create_toolbar(self) -> QFrame:
        """Create the toolbar"""
        toolbar = QFrame()
        toolbar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_medium']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 12, 16, 12)

        # Title
        title = QLabel("🔌 Plugin Manager")
        title.setStyleSheet(f"""
            font-size: 18px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        layout.addWidget(title)

        layout.addSpacing(24)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search plugins...")
        self.search_input.setMaximumWidth(300)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['primary']};
            }}
        """)
        self.search_input.textChanged.connect(self._filter_plugins)
        layout.addWidget(self.search_input)

        layout.addStretch()

        # Stats
        self.stats_label = QLabel("0 plugins loaded")
        self.stats_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        layout.addWidget(self.stats_label)

        layout.addSpacing(16)

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

        # Open plugins folder
        folder_btn = QPushButton("📁 Open Folder")
        folder_btn.setStyleSheet(btn_style)
        folder_btn.clicked.connect(self._open_plugins_folder)
        layout.addWidget(folder_btn)

        # Install plugin
        install_btn = QPushButton("📥 Install Plugin")
        install_btn.setStyleSheet(btn_style)
        install_btn.clicked.connect(self._install_plugin)
        layout.addWidget(install_btn)

        # Create plugin
        create_btn = QPushButton("➕ Create Plugin")
        create_btn.setStyleSheet(btn_style)
        create_btn.clicked.connect(self._create_plugin)
        layout.addWidget(create_btn)

        # Refresh
        refresh_btn = QPushButton("🔄 Refresh All")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['success']};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #2e7d32;
            }}
        """)
        refresh_btn.clicked.connect(self._refresh_plugins)
        layout.addWidget(refresh_btn)

        return toolbar

    def _create_plugins_container(self) -> QWidget:
        """Create the plugins list container"""
        container = QWidget()
        container.setStyleSheet(f"background-color: {COLORS['bg_dark']};")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Category tabs
        self.category_tabs = QTabWidget()
        self.category_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: transparent;
            }}
            QTabBar::tab {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_secondary']};
                padding: 8px 16px;
                border: none;
                border-bottom: 2px solid transparent;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                color: {COLORS['text_primary']};
                border-bottom: 2px solid {COLORS['primary']};
            }}
        """)

        # All plugins tab
        all_scroll = QScrollArea()
        all_scroll.setWidgetResizable(True)
        all_scroll.setStyleSheet("border: none;")

        self.plugins_grid_widget = QWidget()
        self.plugins_grid_widget.setStyleSheet("background-color: transparent;")
        self.plugins_grid = QVBoxLayout(self.plugins_grid_widget)
        self.plugins_grid.setSpacing(12)
        self.plugins_grid.addStretch()

        all_scroll.setWidget(self.plugins_grid_widget)
        self.category_tabs.addTab(all_scroll, "📦 All Plugins")

        # Enabled tab
        enabled_widget = QWidget()
        enabled_layout = QVBoxLayout(enabled_widget)
        self.enabled_list = QListWidget()
        self.enabled_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: none;
            }}
            QListWidget::item {{
                padding: 12px;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QListWidget::item:selected {{
                background-color: {COLORS['primary']};
            }}
        """)
        enabled_layout.addWidget(self.enabled_list)
        self.category_tabs.addTab(enabled_widget, "✅ Enabled")

        # Disabled tab
        disabled_widget = QWidget()
        disabled_layout = QVBoxLayout(disabled_widget)
        self.disabled_list = QListWidget()
        self.disabled_list.setStyleSheet(self.enabled_list.styleSheet())
        disabled_layout.addWidget(self.disabled_list)
        self.category_tabs.addTab(disabled_widget, "⏸️ Disabled")

        layout.addWidget(self.category_tabs)

        return container

    def _create_details_container(self) -> QWidget:
        """Create the details panel"""
        container = QWidget()
        container.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['bg_dark']};
                border-left: 1px solid {COLORS['border']};
            }}
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Details tabs
        details_tabs = QTabWidget()
        details_tabs.setStyleSheet(f"""
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

        # Logs tab
        logs_widget = QWidget()
        logs_layout = QVBoxLayout(logs_widget)
        logs_layout.setContentsMargins(12, 12, 12, 12)

        self.logs_console = QPlainTextEdit()
        self.logs_console.setReadOnly(True)
        self.logs_console.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #1a1a1a;
                color: {COLORS['text_primary']};
                border: none;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
            }}
        """)
        self.logs_console.setPlaceholderText("Plugin activity logs will appear here...")
        logs_layout.addWidget(self.logs_console)

        details_tabs.addTab(logs_widget, "📜 Activity Log")

        # Events tab
        events_widget = QWidget()
        events_layout = QVBoxLayout(events_widget)
        events_layout.setContentsMargins(12, 12, 12, 12)

        events_label = QLabel("Available Hook Events")
        events_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-weight: 600;")
        events_layout.addWidget(events_label)

        events_list = QListWidget()
        events_list.setStyleSheet(self.enabled_list.styleSheet())
        events = [
            "🚀 JOB_SUBMITTED - When a job is submitted",
            "▶️ JOB_STARTED - When a job starts running",
            "✅ JOB_COMPLETED - When a job completes",
            "❌ JOB_FAILED - When a job fails",
            "💻 WORKER_REGISTERED - When a worker joins",
            "🟢 WORKER_ONLINE - When a worker comes online",
            "🔴 WORKER_OFFLINE - When a worker goes offline",
            "⏰ SCHEDULER_TICK - Scheduler cycle event",
            "🏁 MASTER_STARTED - When master starts",
        ]
        for event in events:
            events_list.addItem(event)
        events_layout.addWidget(events_list)

        details_tabs.addTab(events_widget, "⚡ Events")

        # Help tab
        help_widget = QWidget()
        help_layout = QVBoxLayout(help_widget)
        help_layout.setContentsMargins(12, 12, 12, 12)

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: none;
            }}
        """)
        help_text.setHtml(self._get_help_html())
        help_layout.addWidget(help_text)

        details_tabs.addTab(help_widget, "❓ Help")

        layout.addWidget(details_tabs)

        return container

    def _get_help_html(self) -> str:
        """Get help documentation HTML"""
        return f"""
        <style>
            h3 {{ color: {COLORS['primary']}; margin-top: 16px; }}
            code {{
                background-color: {COLORS['bg_light']};
                padding: 2px 6px;
                border-radius: 3px;
                font-family: monospace;
            }}
            pre {{
                background-color: {COLORS['bg_medium']};
                padding: 12px;
                border-radius: 4px;
                overflow-x: auto;
            }}
        </style>

        <h3>🔌 Creating a Plugin</h3>
        <p>Create a Python file in the plugins folder with the following structure:</p>

        <pre>
# my_plugin.py

PLUGIN_NAME = "My Plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "A sample plugin"
PLUGIN_AUTHOR = "Your Name"

def on_load():
    \"\"\"Called when plugin loads\"\"\"
    print("Plugin loaded!")

def on_unload():
    \"\"\"Called when plugin unloads\"\"\"
    print("Plugin unloaded!")

def on_job_submitted(job):
    \"\"\"Hook: Called when a job is submitted\"\"\"
    print(f"Job submitted: {{job['name']}}")
        </pre>

        <h3>📁 Plugin Location</h3>
        <p>Plugins are loaded from:</p>
        <code>~/.nebulacompute/plugins/</code>

        <h3>🔄 Hot Reload</h3>
        <p>Plugins are automatically reloaded when their files change.
        You can also manually reload using the <b>🔄 Reload</b> button.</p>

        <h3>⚡ Available Hooks</h3>
        <ul>
            <li><code>on_load()</code> - Plugin initialization</li>
            <li><code>on_unload()</code> - Plugin cleanup</li>
            <li><code>on_job_submitted(job)</code></li>
            <li><code>on_job_started(job)</code></li>
            <li><code>on_job_completed(job)</code></li>
            <li><code>on_worker_registered(worker)</code></li>
        </ul>
        """

    def _setup_file_watcher(self):
        """Setup file system watcher for hot reload"""
        self._watcher.addPath(self._plugin_dir)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _on_directory_changed(self, path: str):
        """Handle directory change (new/deleted files)"""
        self._log(f"📁 Directory changed: {path}")
        # Debounce reloads
        QTimer.singleShot(500, self._refresh_plugins)

    def _on_file_changed(self, path: str):
        """Handle file change (hot reload)"""
        filename = Path(path).stem
        self._log(f"📄 File changed: {filename}")

        if filename in self._plugins:
            self._reload_plugin(filename)

    def _load_plugins(self):
        """Load all plugins from directory"""
        self._log("🔄 Loading plugins...")

        loader = PluginLoader(self._plugin_dir)
        loader.plugin_loaded.connect(self._on_plugin_loaded)
        loader.plugin_error.connect(self._on_plugin_error)
        loader.loading_complete.connect(self._on_loading_complete)
        loader.start()
        loader.wait()  # Wait for loading to complete

    def _on_plugin_loaded(self, plugin: PluginInfo):
        """Handle plugin loaded"""
        self._plugins[plugin.name] = plugin
        self._add_plugin_card(plugin)
        self._log(f"✅ Loaded: {plugin.name} v{plugin.version}")

        # Watch the plugin file
        self._watcher.addPath(plugin.path)

        # Call on_load if exists
        if plugin.module and hasattr(plugin.module, 'on_load'):
            try:
                plugin.module.on_load()
            except Exception as e:
                self._log(f"❌ {plugin.name}.on_load() error: {e}")

    def _on_plugin_error(self, name: str, error: str):
        """Handle plugin load error"""
        self._log(f"❌ Failed to load {name}: {error}")

    def _on_loading_complete(self):
        """Handle loading complete"""
        self._update_stats()
        self._log(f"✨ Loading complete: {len(self._plugins)} plugins")

    def _add_plugin_card(self, plugin: PluginInfo):
        """Add a plugin card to the grid"""
        card = PluginCard(plugin)
        card.toggle_requested.connect(self._toggle_plugin)
        card.reload_requested.connect(self._reload_plugin)
        card.unload_requested.connect(self._unload_plugin)
        card.configure_requested.connect(self._configure_plugin)

        self._plugin_cards[plugin.name] = card

        # Insert before the stretch
        count = self.plugins_grid.count()
        self.plugins_grid.insertWidget(count - 1, card)

        # Update category lists
        self._update_category_lists()

    def _toggle_plugin(self, name: str, enabled: bool):
        """Toggle plugin enabled state"""
        if name in self._plugins:
            self._plugins[name].enabled = enabled
            if name in self._plugin_cards:
                self._plugin_cards[name].update_status(enabled)
            self._log(f"{'✅' if enabled else '⏸️'} {name}: {'enabled' if enabled else 'disabled'}")
            self._update_category_lists()
            self._update_stats()

    def _reload_plugin(self, name: str):
        """Reload a plugin"""
        if name not in self._plugins:
            return

        plugin = self._plugins[name]
        self._log(f"🔄 Reloading: {name}")

        try:
            # Call on_unload if exists
            if plugin.module and hasattr(plugin.module, 'on_unload'):
                plugin.module.on_unload()

            # Reload the module
            if plugin.module:
                importlib.reload(plugin.module)
                plugin.last_reload = datetime.now()

            # Call on_load if exists
            if plugin.module and hasattr(plugin.module, 'on_load'):
                plugin.module.on_load()

            self._log(f"✅ Reloaded: {name}")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            plugin.error = error_msg
            self._log(f"❌ Reload failed: {error_msg}")

    def _unload_plugin(self, name: str):
        """Unload a plugin"""
        if name not in self._plugins:
            return

        reply = QMessageBox.question(
            self, "Unload Plugin",
            f"Are you sure you want to unload '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        plugin = self._plugins[name]

        try:
            # Call on_unload if exists
            if plugin.module and hasattr(plugin.module, 'on_unload'):
                plugin.module.on_unload()

            # Remove from tracking
            del self._plugins[name]

            # Remove card
            if name in self._plugin_cards:
                card = self._plugin_cards[name]
                self.plugins_grid.removeWidget(card)
                card.deleteLater()
                del self._plugin_cards[name]

            # Remove from sys.modules
            module_name = Path(plugin.path).stem
            if module_name in sys.modules:
                del sys.modules[module_name]

            self._log(f"❌ Unloaded: {name}")
            self._update_category_lists()
            self._update_stats()

        except Exception as e:
            self._log(f"❌ Unload failed: {e}")

    def _configure_plugin(self, name: str):
        """Open plugin configuration"""
        if name not in self._plugins:
            return

        plugin = self._plugins[name]

        # Check if plugin has configure method
        if plugin.module and hasattr(plugin.module, 'configure'):
            try:
                plugin.module.configure()
            except Exception as e:
                self._log(f"❌ Configure error: {e}")
        else:
            QMessageBox.information(
                self, "Configure",
                f"Plugin '{name}' does not have a configure() method."
            )

    def _filter_plugins(self, text: str):
        """Filter plugins by search text"""
        text = text.lower()
        for name, card in self._plugin_cards.items():
            visible = text in name.lower() or text in card.plugin.description.lower()
            card.setVisible(visible)

    def _refresh_plugins(self):
        """Refresh all plugins"""
        self._log("🔄 Refreshing plugins...")

        # Clear existing cards
        for card in self._plugin_cards.values():
            self.plugins_grid.removeWidget(card)
            card.deleteLater()
        self._plugin_cards.clear()
        self._plugins.clear()

        # Reload
        self._load_plugins()

    def _open_plugins_folder(self):
        """Open the plugins folder in file explorer"""
        import subprocess
        import platform

        path = self._plugin_dir

        if platform.system() == "Windows":
            subprocess.Popen(f'explorer "{path}"')
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

        self._log(f"📂 Opened: {path}")

    def _install_plugin(self):
        """Install a plugin from file"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Install Plugin",
            "", "Python Files (*.py);;ZIP Archives (*.zip)"
        )

        if not filename:
            return

        try:
            import shutil
            dest = Path(self._plugin_dir) / Path(filename).name
            shutil.copy(filename, dest)
            self._log(f"📥 Installed: {Path(filename).name}")
            self._refresh_plugins()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to install: {e}")

    def _create_plugin(self):
        """Create a new plugin from template"""
        name, ok = QMessageBox.getText(
            self, "Create Plugin",
            "Enter plugin name:"
        ) if hasattr(QMessageBox, 'getText') else (None, False)

        # Fallback if getText doesn't exist
        if not ok or not name:
            name = "my_plugin"

        template = f'''"""
{name} - A NebulaCompute Plugin
"""

PLUGIN_NAME = "{name}"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Description of your plugin"
PLUGIN_AUTHOR = "Your Name"


def on_load():
    """Called when plugin is loaded"""
    print(f"{{PLUGIN_NAME}} loaded!")


def on_unload():
    """Called when plugin is unloaded"""
    print(f"{{PLUGIN_NAME}} unloaded!")


def on_job_submitted(job):
    """Called when a job is submitted"""
    print(f"Job submitted: {{job.get('name', 'unknown')}}")


def on_job_completed(job):
    """Called when a job completes"""
    print(f"Job completed: {{job.get('name', 'unknown')}}")


# Add more hooks as needed...
'''

        filepath = Path(self._plugin_dir) / f"{name.lower().replace(' ', '_')}.py"
        filepath.write_text(template)

        self._log(f"➕ Created: {filepath.name}")
        self._refresh_plugins()

    def _create_sample_plugins(self):
        """Create sample plugins if none exist"""
        plugin_dir = Path(self._plugin_dir)

        if any(plugin_dir.glob("*.py")):
            return  # Plugins already exist

        # Sample: Logger plugin
        logger_plugin = '''"""
Logger Plugin - Logs all cluster events
"""

PLUGIN_NAME = "Event Logger"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Logs all cluster events to console"
PLUGIN_AUTHOR = "NebulaCompute Team"


def on_load():
    print("📝 Event Logger plugin loaded!")


def on_unload():
    print("📝 Event Logger plugin unloaded!")


def on_job_submitted(job):
    print(f"📝 [LOG] Job submitted: {job.get('name', 'unknown')}")


def on_job_completed(job):
    print(f"📝 [LOG] Job completed: {job.get('name', 'unknown')}")


def on_worker_registered(worker):
    print(f"📝 [LOG] Worker registered: {worker.get('id', 'unknown')}")
'''
        (plugin_dir / "event_logger.py").write_text(logger_plugin)

        # Sample: Stats plugin
        stats_plugin = '''"""
Stats Plugin - Collects and displays cluster statistics
"""

PLUGIN_NAME = "Stats Collector"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Collects cluster statistics"
PLUGIN_AUTHOR = "NebulaCompute Team"

_stats = {
    "jobs_submitted": 0,
    "jobs_completed": 0,
    "jobs_failed": 0
}


def on_load():
    print("📊 Stats Collector loaded!")


def on_unload():
    print(f"📊 Final stats: {_stats}")


def on_job_submitted(job):
    _stats["jobs_submitted"] += 1


def on_job_completed(job):
    _stats["jobs_completed"] += 1


def on_job_failed(job):
    _stats["jobs_failed"] += 1


def get_stats():
    return _stats.copy()
'''
        (plugin_dir / "stats_collector.py").write_text(stats_plugin)

        self._log("📦 Created sample plugins")

    def _update_category_lists(self):
        """Update enabled/disabled category lists"""
        self.enabled_list.clear()
        self.disabled_list.clear()

        for plugin in self._plugins.values():
            item = QListWidgetItem(f"🔌 {plugin.name} v{plugin.version}")
            item.setData(Qt.UserRole, plugin.name)

            if plugin.enabled:
                self.enabled_list.addItem(item)
            else:
                self.disabled_list.addItem(item)

    def _update_stats(self):
        """Update the stats label"""
        total = len(self._plugins)
        enabled = sum(1 for p in self._plugins.values() if p.enabled)
        self.stats_label.setText(f"{total} plugins ({enabled} enabled)")

    def _log(self, message: str):
        """Add a log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs_console.appendPlainText(f"[{timestamp}] {message}")

    def set_api_client(self, client: APIClient):
        """Set the API client"""
        self.api_client = client
