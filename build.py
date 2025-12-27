#!/usr/bin/env python3
"""
NebulaCompute Build System - Ultimate PyInstaller Edition
نظام بناء NebulaCompute - النسخة المتكاملة النهائية

═══════════════════════════════════════════════════════════════════════════════
A comprehensive cross-platform build system for creating standalone executables
from the NebulaCompute desktop application with advanced features.
═══════════════════════════════════════════════════════════════════════════════

Features / المميزات:
────────────────────────────────────────────────────────────────────────────────
• Multi-platform support (Windows, Linux, macOS)
• Multiple build modes (debug, release, minimal, full, fast, optimized)
• Automatic dependency detection and bundling
• Icon and splash screen generation
• Windows version info embedding
• Code signing support (Windows/macOS)
• UPX compression for smaller executables
• Installer creation (NSIS, Inno Setup, AppImage, DMG, DEB, RPM)
• Auto-updater integration ready
• CI/CD integration with GitHub Actions
• Arabic and English bilingual interface
• Comprehensive hidden imports management
• Smart resource bundling
────────────────────────────────────────────────────────────────────────────────

Usage / الاستخدام:
    python build.py                          # Default release build
    python build.py --mode debug             # Debug build with console
    python build.py --mode release           # Optimized release build
    python build.py --mode minimal           # Minimal build (smaller size)
    python build.py --mode full              # Full build with all features
    python build.py --mode fast              # Quick build, minimal optimization
    python build.py --installer nsis         # Build with NSIS installer
    python build.py --installer appimage     # Build with AppImage (Linux)
    python build.py --onedir                 # Create directory bundle
    python build.py --console                # Enable console window
    python build.py --clean                  # Clean build artifacts
    python build.py --install-deps           # Install build dependencies
    python build.py --info                   # Show build configuration
    python build.py --all-platforms          # Build for all platforms (CI)

Requirements / المتطلبات:
    pip install pyinstaller PySide6 qasync httpx websockets pillow

Author: NebulaCompute Team
License: MIT
Version: 2.0.0
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# إعدادات الترميز - Unicode Encoding Settings
# ═══════════════════════════════════════════════════════════════════════════════
def setup_encoding():
    """Setup UTF-8 encoding for Windows console"""
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            else:
                sys.stdout = io.TextIOWrapper(
                    sys.stdout.buffer, encoding="utf-8", errors="replace"
                )
                sys.stderr = io.TextIOWrapper(
                    sys.stderr.buffer, encoding="utf-8", errors="replace"
                )
        except Exception:
            pass


setup_encoding()


# ═══════════════════════════════════════════════════════════════════════════════
# الثوابت - Constants
# ═══════════════════════════════════════════════════════════════════════════════
APP_NAME = "NebulaCompute"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Distributed Computing System - نظام الحوسبة الموزعة"
APP_AUTHOR = "NebulaCompute Team"
APP_WEBSITE = "https://github.com/nebulacompute"
APP_IDENTIFIER = "com.nebulacompute.desktop"


# ═══════════════════════════════════════════════════════════════════════════════
# التعدادات - Enumerations
# ═══════════════════════════════════════════════════════════════════════════════
class BuildMode(Enum):
    """Build mode enumeration / أوضاع البناء"""
    DEBUG = "debug"
    RELEASE = "release"
    MINIMAL = "minimal"
    FULL = "full"
    FAST = "fast"
    OPTIMIZED = "optimized"


class InstallerType(Enum):
    """Installer types / أنواع المثبتات"""
    NONE = "none"
    NSIS = "nsis"
    INNO = "inno"
    MSI = "msi"
    APPIMAGE = "appimage"
    DEB = "deb"
    RPM = "rpm"
    DMG = "dmg"
    PKG = "pkg"


# ═══════════════════════════════════════════════════════════════════════════════
# الألوان - Color Output System
# ═══════════════════════════════════════════════════════════════════════════════
class Colors:
    """ANSI color codes for terminal output with cross-platform support"""
    
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    DIM = "\033[2m"
    END = "\033[0m"
    
    _initialized = False
    
    @classmethod
    def init(cls):
        """Initialize colors for Windows"""
        if cls._initialized:
            return
        cls._initialized = True
        
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                cls.disable()
    
    @classmethod
    def disable(cls):
        """Disable colors for non-TTY output"""
        for attr in dir(cls):
            if not attr.startswith("_") and attr.isupper():
                setattr(cls, attr, "")
    
    @classmethod
    def colorize(cls, text: str, *colors: str) -> str:
        """Apply colors to text"""
        prefix = "".join(colors)
        return f"{prefix}{text}{cls.END}" if prefix else text


# Initialize colors
Colors.init()


# ═══════════════════════════════════════════════════════════════════════════════
# نظام السجلات - Logging System
# ═══════════════════════════════════════════════════════════════════════════════
class Logger:
    """Advanced logging system with colors and icons"""
    
    ICONS = {
        "info": "ℹ️ ",
        "success": "✅",
        "warning": "⚠️ ",
        "error": "❌",
        "header": "📦",
        "step": "▶️ ",
        "build": "🔨",
        "clean": "🧹",
        "package": "📦",
        "config": "⚙️ ",
    }
    
    COLORS = {
        "info": Colors.CYAN,
        "success": Colors.GREEN,
        "warning": Colors.YELLOW,
        "error": Colors.RED,
        "header": Colors.BOLD + Colors.BLUE,
        "step": Colors.YELLOW,
    }
    
    @classmethod
    def log(cls, message: str, level: str = "info"):
        """Log a message with color and icon"""
        color = cls.COLORS.get(level, Colors.CYAN)
        icon = cls.ICONS.get(level, "•")
        print(f"{color}{icon} {message}{Colors.END}")
    
    @classmethod
    def section(cls, title: str):
        """Print a section header"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'═' * 70}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}  {title}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'═' * 70}{Colors.END}\n")
    
    @classmethod
    def step(cls, current: int, total: int, message: str):
        """Print a step progress"""
        print(f"{Colors.YELLOW}[{current}/{total}]{Colors.END} {message}")
    
    @classmethod
    def success(cls, message: str):
        cls.log(message, "success")
    
    @classmethod
    def error(cls, message: str):
        cls.log(message, "error")
    
    @classmethod
    def warning(cls, message: str):
        cls.log(message, "warning")
    
    @classmethod
    def info(cls, message: str):
        cls.log(message, "info")


def print_banner():
    """Print build system banner"""
    banner = f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║   {Colors.BOLD}███╗   ██╗███████╗██████╗ ██╗   ██╗██╗      █████╗{Colors.END}{Colors.CYAN}                      ║
║   {Colors.BOLD}████╗  ██║██╔════╝██╔══██╗██║   ██║██║     ██╔══██╗{Colors.END}{Colors.CYAN}                     ║
║   {Colors.BOLD}██╔██╗ ██║█████╗  ██████╔╝██║   ██║██║     ███████║{Colors.END}{Colors.CYAN}                     ║
║   {Colors.BOLD}██║╚██╗██║██╔══╝  ██╔══██╗██║   ██║██║     ██╔══██║{Colors.END}{Colors.CYAN}                     ║
║   {Colors.BOLD}██║ ╚████║███████╗██████╔╝╚██████╔╝███████╗██║  ██║{Colors.END}{Colors.CYAN}                     ║
║   {Colors.BOLD}╚═╝  ╚═══╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝{Colors.END}{Colors.CYAN}                     ║
║                                                                            ║
║   {Colors.YELLOW}PyInstaller Build System v2.0{Colors.CYAN}                                         ║
║   {Colors.GREEN}نظام البناء المتكامل - Ultimate Edition{Colors.CYAN}                              ║
║                                                                            ║
╚══════════════════════════════════════════════════════════════════════════╝{Colors.END}
"""
    print(banner)


# ═══════════════════════════════════════════════════════════════════════════════
# إعدادات البناء - Build Configuration
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class BuildConfig:
    """Comprehensive build configuration / إعدادات البناء الشاملة"""
    
    # Application info
    name: str = APP_NAME
    version: str = APP_VERSION
    description: str = APP_DESCRIPTION
    author: str = APP_AUTHOR
    website: str = APP_WEBSITE
    identifier: str = APP_IDENTIFIER
    
    # Build options
    mode: BuildMode = BuildMode.RELEASE
    one_file: bool = True
    console: bool = False
    debug: bool = False
    
    # Optimization
    upx_compress: bool = True
    strip_binaries: bool = True
    optimize_bytecode: int = 2
    
    # Features
    splash_screen: bool = True
    auto_updater: bool = True
    include_web: bool = True
    
    # Signing
    sign_code: bool = False
    sign_cert: Optional[str] = None
    sign_password: Optional[str] = None
    
    # Installer
    installer_type: InstallerType = InstallerType.NONE
    
    # Custom options
    extra_data: list = field(default_factory=list)
    extra_binaries: list = field(default_factory=list)
    hidden_imports: list = field(default_factory=list)
    excludes: list = field(default_factory=list)
    runtime_hooks: list = field(default_factory=list)
    
    # Paths (set in __post_init__)
    project_root: Path = field(default_factory=Path)
    src_path: Path = field(default_factory=Path)
    entry_point: Path = field(default_factory=Path)
    resources_path: Path = field(default_factory=Path)
    icon_path: Path = field(default_factory=Path)
    output_dir: Path = field(default_factory=Path)
    build_dir: Path = field(default_factory=Path)
    spec_file: Path = field(default_factory=Path)
    
    def __post_init__(self):
        """Initialize paths based on project root"""
        if not self.project_root or self.project_root == Path():
            self.project_root = self._find_project_root()
        
        self.src_path = self.project_root / "src"
        self.entry_point = self.src_path / "distributed_cluster" / "desktop" / "app_entry.py"
        self.resources_path = self.src_path / "distributed_cluster" / "desktop" / "resources"
        self.icon_path = self.resources_path / "icon.ico"
        self.output_dir = self.project_root / "dist"
        self.build_dir = self.project_root / "build"
        self.spec_file = self.project_root / f"{self.name}.spec"
    
    def _find_project_root(self) -> Path:
        """Find project root directory"""
        current = Path(__file__).parent
        
        # Look for pyproject.toml or setup.py
        for parent in [current] + list(current.parents):
            if (parent / "pyproject.toml").exists() or (parent / "setup.py").exists():
                return parent
        
        return current


# ═══════════════════════════════════════════════════════════════════════════════
# الاستيرادات المخفية - Hidden Imports Registry
# ═══════════════════════════════════════════════════════════════════════════════
class HiddenImportsRegistry:
    """Comprehensive hidden imports management"""
    
    # PySide6 / Qt modules
    QT_MODULES = [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtCharts",
        "PySide6.QtNetwork",
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
        "PySide6.QtPrintSupport",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
    ]
    
    # Async modules
    ASYNC_MODULES = [
        "qasync",
        "asyncio",
        "asyncio.events",
        "asyncio.base_events",
        "asyncio.selector_events",
        "asyncio.proactor_events",
        "anyio",
        "anyio._backends",
        "anyio._backends._asyncio",
        "sniffio",
    ]
    
    # HTTP & WebSocket modules
    NETWORK_MODULES = [
        "httpx",
        "httpx._transports",
        "httpx._transports.default",
        "httpx._transports.asgi",
        "httpx._content",
        "httpcore",
        "h11",
        "h2",
        "websockets",
        "websockets.client",
        "websockets.legacy",
        "websockets.legacy.client",
        "websockets.server",
        "ssl",
        "certifi",
    ]
    
    # Distributed Cluster - Desktop modules
    DESKTOP_MODULES = [
        "distributed_cluster",
        "distributed_cluster.desktop",
        "distributed_cluster.desktop.main",
        "distributed_cluster.desktop.main_window",
        "distributed_cluster.desktop.app_entry",
        # API
        "distributed_cluster.desktop.api",
        "distributed_cluster.desktop.api.client",
        # Views
        "distributed_cluster.desktop.views",
        "distributed_cluster.desktop.views.dashboard",
        "distributed_cluster.desktop.views.jobs",
        "distributed_cluster.desktop.views.workers",
        "distributed_cluster.desktop.views.templates",
        "distributed_cluster.desktop.views.pools",
        "distributed_cluster.desktop.views.queues",
        "distributed_cluster.desktop.views.settings",
        "distributed_cluster.desktop.views.logs",
        "distributed_cluster.desktop.views.metrics",
        "distributed_cluster.desktop.views.script_editor",
        "distributed_cluster.desktop.views.plugin_manager",
        "distributed_cluster.desktop.views.powershell_console",
        # Widgets
        "distributed_cluster.desktop.widgets",
        "distributed_cluster.desktop.widgets.sidebar",
        "distributed_cluster.desktop.widgets.terminal",
        "distributed_cluster.desktop.widgets.notifications",
        "distributed_cluster.desktop.widgets.system_tray",
        "distributed_cluster.desktop.widgets.connection_dialog",
        "distributed_cluster.desktop.widgets.login_dialog",
        "distributed_cluster.desktop.widgets.charts",
        "distributed_cluster.desktop.widgets.stat_card",
        "distributed_cluster.desktop.widgets.data_table",
        # UI components
        "distributed_cluster.desktop.ui",
        "distributed_cluster.desktop.ui.main_window",
        "distributed_cluster.desktop.ui.sidebar",
        "distributed_cluster.desktop.ui.dashboard",
        "distributed_cluster.desktop.ui.dialogs",
        "distributed_cluster.desktop.ui.components",
        "distributed_cluster.desktop.ui.titlebar",
        "distributed_cluster.desktop.ui.splash",
        "distributed_cluster.desktop.ui.notifications",
        "distributed_cluster.desktop.ui.fluent_design",
        "distributed_cluster.desktop.ui.animations",
        "distributed_cluster.desktop.ui.data_table",
        "distributed_cluster.desktop.ui.windows_integration",
        "distributed_cluster.desktop.ui.views",
        "distributed_cluster.desktop.ui.views.jobs",
        "distributed_cluster.desktop.ui.views.logs",
        # Resources
        "distributed_cluster.desktop.resources",
        "distributed_cluster.desktop.resources.styles",
        "distributed_cluster.desktop.resources.themes",
    ]
    
    # Core & Models modules
    CORE_MODULES = [
        "distributed_cluster.models",
        "distributed_cluster.models.job",
        "distributed_cluster.models.worker",
        "distributed_cluster.models.resources",
        "distributed_cluster.models.cluster",
        "distributed_cluster.models.task",
        "distributed_cluster.core",
        "distributed_cluster.core.config",
        "distributed_cluster.core.logger",
        "distributed_cluster.core.exceptions",
    ]
    
    # Web modules (for full mode)
    WEB_MODULES = [
        "distributed_cluster.web",
        "distributed_cluster.web.app",
        "distributed_cluster.master",
        "distributed_cluster.master.state",
        "fastapi",
        "starlette",
        "uvicorn",
        "jinja2",
        "pydantic",
    ]
    
    # Standard library modules
    STDLIB_MODULES = [
        "json",
        "datetime",
        "dataclasses",
        "enum",
        "typing",
        "pathlib",
        "uuid",
        "threading",
        "queue",
        "collections",
        "collections.abc",
        "functools",
        "itertools",
        "operator",
        "contextlib",
        "weakref",
        "copy",
        "pickle",
        "base64",
        "hashlib",
        "hmac",
        "secrets",
        "tempfile",
        "shutil",
        "glob",
        "fnmatch",
        "os.path",
        "stat",
        "struct",
        "codecs",
        "io",
        "re",
        "urllib",
        "urllib.parse",
        "urllib.request",
        "email",
        "email.mime",
        "email.mime.text",
        "email.mime.multipart",
        "ctypes",
        "ctypes.wintypes",
    ]
    
    # Package utilities
    PACKAGING_MODULES = [
        "jaraco",
        "jaraco.text",
        "jaraco.functools",
        "jaraco.context",
        "jaraco.classes",
        "jaraco.collections",
        "pkg_resources",
        "pkg_resources.extern",
        "importlib_metadata",
        "importlib_resources",
        "packaging",
        "packaging.version",
        "packaging.specifiers",
        "packaging.requirements",
        "packaging.markers",
        "zipp",
        "more_itertools",
    ]
    
    @classmethod
    def get_all(cls, include_web: bool = False) -> list[str]:
        """Get all hidden imports"""
        imports = []
        imports.extend(cls.QT_MODULES)
        imports.extend(cls.ASYNC_MODULES)
        imports.extend(cls.NETWORK_MODULES)
        imports.extend(cls.DESKTOP_MODULES)
        imports.extend(cls.CORE_MODULES)
        imports.extend(cls.STDLIB_MODULES)
        imports.extend(cls.PACKAGING_MODULES)
        
        if include_web:
            imports.extend(cls.WEB_MODULES)
        
        return imports
    
    @classmethod
    def get_minimal(cls) -> list[str]:
        """Get minimal hidden imports for smaller builds"""
        imports = []
        imports.extend(cls.QT_MODULES[:6])  # Basic Qt modules only
        imports.extend(cls.ASYNC_MODULES[:4])
        imports.extend(cls.NETWORK_MODULES[:8])
        imports.extend(cls.DESKTOP_MODULES[:10])
        imports.extend(cls.CORE_MODULES)
        return imports


# ═══════════════════════════════════════════════════════════════════════════════
# الاستثناءات - Excludes Registry
# ═══════════════════════════════════════════════════════════════════════════════
class ExcludesRegistry:
    """Modules to exclude from build"""
    
    # Heavy UI libraries not needed
    UI_EXCLUDES = [
        "tkinter",
        "_tkinter",
        "tk",
        "tcl",
        "wx",
        "PyQt5",
        "PyQt6",
    ]
    
    # Heavy data science libraries
    DATA_SCIENCE_EXCLUDES = [
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL.ImageTk",
        "sklearn",
        "tensorflow",
        "torch",
        "keras",
    ]
    
    # Development tools
    DEV_EXCLUDES = [
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
        "pip",
        "wheel",
        "setuptools",
        "distutils",
        "test",
        "tests",
        "unittest",
        "doctest",
        "pdb",
        "pydoc",
    ]
    
    # Server-side libraries (for minimal mode)
    SERVER_EXCLUDES = [
        "docker",
        "pynvml",
        "uvicorn",
        "fastapi",
        "starlette",
        "grpc",
        "grpcio",
        "boto3",
        "botocore",
        "redis",
        "asyncpg",
        "psycopg2",
        "mysql",
        "pymongo",
    ]
    
    # Heavy crypto (for minimal mode)
    CRYPTO_EXCLUDES = [
        "cryptography",
        "cryptography.hazmat",
        "cryptography.hazmat.backends",
        "cryptography.hazmat.backends.openssl",
    ]
    
    @classmethod
    def get_standard(cls) -> list[str]:
        """Get standard excludes"""
        excludes = []
        excludes.extend(cls.UI_EXCLUDES)
        excludes.extend(cls.DATA_SCIENCE_EXCLUDES)
        excludes.extend(cls.DEV_EXCLUDES)
        return excludes
    
    @classmethod
    def get_minimal(cls) -> list[str]:
        """Get extensive excludes for minimal builds"""
        excludes = cls.get_standard()
        excludes.extend(cls.SERVER_EXCLUDES)
        excludes.extend(cls.CRYPTO_EXCLUDES)
        return excludes


# Packages to collect all data from
COLLECT_ALL_PACKAGES = [
    "PySide6",
    "httpx",
    "websockets",
    "jaraco",
    "pkg_resources",
    "certifi",
]


# ═══════════════════════════════════════════════════════════════════════════════
# المُنشئ الرئيسي - Main Builder Class
# ═══════════════════════════════════════════════════════════════════════════════
class NebulaBuilder:
    """
    Main builder class for NebulaCompute
    الصف الرئيسي لبناء NebulaCompute
    """
    
    def __init__(self, config: Optional[BuildConfig] = None):
        """Initialize builder"""
        self.config = config or BuildConfig()
        self.project_root = self.config.project_root
        self.src_path = self.config.src_path
        self.desktop_path = self.src_path / "distributed_cluster" / "desktop"
        self.web_path = self.src_path / "distributed_cluster" / "web"
        self.dist_path = self.config.output_dir
        self.build_path = self.config.build_dir
        
        self.platform = platform.system().lower()
        self.arch = platform.machine().lower()
        self.is_64bit = sys.maxsize > 2**32
        
        self._upx_available = False
        self._pyinstaller_available = False
        self._nsis_available = False
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Utility Methods
    # ═══════════════════════════════════════════════════════════════════════════
    def _run_command(
        self,
        cmd: list[str],
        cwd: Optional[Path] = None,
        capture: bool = False,
        check: bool = True,
        env: Optional[dict] = None,
    ) -> subprocess.CompletedProcess:
        """Run a shell command"""
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.project_root,
                capture_output=capture,
                text=True,
                check=check,
                env=run_env,
            )
            return result
        except subprocess.CalledProcessError as e:
            if check:
                Logger.error(f"Command failed: {' '.join(cmd)}")
                if e.stdout:
                    print(e.stdout)
                if e.stderr:
                    print(e.stderr)
                raise
            return e
    
    def _check_tools(self):
        """Check available build tools"""
        Logger.section("Checking Build Tools / فحص الأدوات")
        
        # Check PyInstaller
        try:
            result = self._run_command(
                [sys.executable, "-m", "PyInstaller", "--version"],
                capture=True,
                check=False,
            )
            if result.returncode == 0:
                self._pyinstaller_available = True
                version = result.stdout.strip() if result.stdout else "unknown"
                Logger.success(f"PyInstaller: {version}")
            else:
                Logger.warning("PyInstaller: not installed")
        except Exception:
            Logger.warning("PyInstaller: not found")
        
        # Check UPX
        try:
            result = self._run_command(["upx", "--version"], capture=True, check=False)
            if result.returncode == 0:
                self._upx_available = True
                Logger.success("UPX compression: available")
            else:
                Logger.warning("UPX compression: not available")
        except FileNotFoundError:
            Logger.info("UPX compression: not installed (optional)")
        
        # Check NSIS (Windows)
        if self.platform == "windows":
            try:
                result = self._run_command(["makensis", "/VERSION"], capture=True, check=False)
                if result.returncode == 0:
                    self._nsis_available = True
                    Logger.success("NSIS: available")
            except FileNotFoundError:
                Logger.info("NSIS: not installed (optional)")
        
        # Check Python version
        py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        Logger.success(f"Python: {py_version}")
        
        # Check platform
        Logger.success(f"Platform: {self.platform} ({self.arch})")
        
        # Install PyInstaller if missing
        if not self._pyinstaller_available:
            Logger.info("Installing PyInstaller...")
            self._run_command(
                [sys.executable, "-m", "pip", "install", "pyinstaller"],
                check=False,
            )
            self._pyinstaller_available = True
    
    def get_version(self) -> str:
        """Get version from git or pyproject.toml"""
        # Try git first
        try:
            result = self._run_command(
                ["git", "describe", "--tags", "--always"],
                capture=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip().lstrip("v")
        except Exception:
            pass
        
        # Try pyproject.toml
        pyproject = self.project_root / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                for line in content.split("\n"):
                    if line.strip().startswith("version"):
                        version = line.split("=")[1].strip().strip('"').strip("'")
                        return version
            except Exception:
                pass
        
        return self.config.version
    
    def get_git_hash(self) -> str:
        """Get short git commit hash"""
        try:
            result = self._run_command(
                ["git", "rev-parse", "--short", "HEAD"],
                capture=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
        except Exception:
            pass
        return "unknown"
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Clean Methods
    # ═══════════════════════════════════════════════════════════════════════════
    def clean(self):
        """Clean build artifacts"""
        Logger.section("Cleaning Build Artifacts / تنظيف ملفات البناء")
        
        def handle_remove_error(func, path, exc_info):
            """Handle permission errors on Windows"""
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception as e:
                Logger.warning(f"Cannot delete {path}: {e}")
        
        dirs_to_clean = [self.build_path, self.dist_path]
        for dir_path in dirs_to_clean:
            if dir_path.exists():
                Logger.info(f"Removing: {dir_path}")
                try:
                    if sys.version_info >= (3, 12):
                        shutil.rmtree(dir_path, onexc=lambda f, p, e: handle_remove_error(f, p, (None, e, None)))
                    else:
                        shutil.rmtree(dir_path, onerror=handle_remove_error)
                except Exception as e:
                    Logger.warning(f"Could not fully clean {dir_path}: {e}")
        
        # Clean spec files
        for spec_file in self.project_root.glob("*.spec"):
            try:
                spec_file.unlink()
                Logger.info(f"Removed: {spec_file.name}")
            except Exception:
                pass
        
        # Clean pycache
        pycache_count = 0
        for pycache in self.project_root.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache)
                pycache_count += 1
            except Exception:
                pass
        
        if pycache_count > 0:
            Logger.info(f"Removed {pycache_count} __pycache__ directories")
        
        Logger.success("Clean complete!")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Resource Creation Methods
    # ═══════════════════════════════════════════════════════════════════════════
    def create_icon(self) -> Path:
        """Create application icon if missing"""
        resources_path = self.desktop_path / "resources"
        resources_path.mkdir(parents=True, exist_ok=True)
        
        icon_path = resources_path / "icon.ico"
        
        if icon_path.exists():
            Logger.info(f"Using existing icon: {icon_path.name}")
            return icon_path
        
        Logger.info("Creating application icon...")
        
        # Try to use PIL if available
        try:
            from PIL import Image, ImageDraw
            
            # Create gradient icon
            sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
            images = []
            
            for size in sizes:
                img = Image.new("RGBA", size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                
                # Draw gradient circle
                for i in range(min(size) // 2):
                    r = int(30 + (i / (size[0] / 2)) * 100)
                    g = int(60 + (i / (size[0] / 2)) * 80)
                    b = int(120 + (i / (size[0] / 2)) * 100)
                    draw.ellipse(
                        [i, i, size[0] - i - 1, size[1] - i - 1],
                        outline=(r, g, b, 255),
                    )
                
                # Draw "N" letter
                center = size[0] // 2
                draw.text(
                    (center, center),
                    "N",
                    fill=(255, 255, 255, 255),
                    anchor="mm",
                )
                
                images.append(img)
            
            images[0].save(icon_path, format="ICO", sizes=[(s[0], s[1]) for s in sizes])
            Logger.success(f"Created icon: {icon_path.name}")
        
        except ImportError:
            # Create minimal valid ICO without PIL
            ico_data = self._create_minimal_ico()
            icon_path.write_bytes(ico_data)
            Logger.success(f"Created minimal icon: {icon_path.name}")
        
        return icon_path
    
    def _create_minimal_ico(self) -> bytes:
        """Create minimal valid ICO file without PIL"""
        # ICO header
        ico_header = bytes([
            0x00, 0x00,  # Reserved
            0x01, 0x00,  # Type (1 = ICO)
            0x01, 0x00,  # Number of images
        ])
        
        # Image entry (16x16 32-bit)
        image_entry = bytes([
            0x10,  # Width (16)
            0x10,  # Height (16)
            0x00,  # Colors (0 = no palette)
            0x00,  # Reserved
            0x01, 0x00,  # Color planes
            0x20, 0x00,  # Bits per pixel (32)
            0x68, 0x04, 0x00, 0x00,  # Size of image data
            0x16, 0x00, 0x00, 0x00,  # Offset to image data
        ])
        
        # BITMAPINFOHEADER
        bmp_header = bytes([
            0x28, 0x00, 0x00, 0x00,  # Header size (40)
            0x10, 0x00, 0x00, 0x00,  # Width (16)
            0x20, 0x00, 0x00, 0x00,  # Height (32, doubled)
            0x01, 0x00,  # Planes
            0x20, 0x00,  # Bits per pixel (32)
            0x00, 0x00, 0x00, 0x00,  # Compression
            0x00, 0x04, 0x00, 0x00,  # Image size
            0x00, 0x00, 0x00, 0x00,  # X pixels per meter
            0x00, 0x00, 0x00, 0x00,  # Y pixels per meter
            0x00, 0x00, 0x00, 0x00,  # Colors used
            0x00, 0x00, 0x00, 0x00,  # Important colors
        ])
        
        # Pixel data (16x16 BGRA) - gradient
        pixels = []
        for y in range(16):
            for x in range(16):
                b = int((x / 15) * 200 + 55)
                g = int((y / 15) * 100 + 80)
                r = int(100 + (x + y) / 30 * 50)
                a = 255
                pixels.extend([b, g, r, a])
        
        # AND mask
        and_mask = bytes([0x00] * 64)
        
        return ico_header + image_entry + bmp_header + bytes(pixels) + and_mask
    
    def create_version_info(self) -> Optional[Path]:
        """Create Windows version info file"""
        if self.platform != "windows":
            return None
        
        self.build_path.mkdir(parents=True, exist_ok=True)
        version_path = self.build_path / "version_info.txt"
        
        # Parse version
        version_parts = self.config.version.replace("-", ".").split(".")
        while len(version_parts) < 4:
            version_parts.append("0")
        version_tuple = tuple(
            int(p) if p.isdigit() else 0 for p in version_parts[:4]
        )
        
        version_content = f"""# UTF-8
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers={version_tuple},
        prodvers={version_tuple},
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0)
    ),
    kids=[
        StringFileInfo([
            StringTable(
                u'040904B0',
                [
                    StringStruct(u'CompanyName', u'{self.config.author}'),
                    StringStruct(u'FileDescription', u'{self.config.description}'),
                    StringStruct(u'FileVersion', u'{self.config.version}'),
                    StringStruct(u'InternalName', u'{self.config.name}'),
                    StringStruct(u'LegalCopyright', u'Copyright (c) 2024 {self.config.author}'),
                    StringStruct(u'OriginalFilename', u'{self.config.name}.exe'),
                    StringStruct(u'ProductName', u'{self.config.name}'),
                    StringStruct(u'ProductVersion', u'{self.config.version}'),
                ]
            )
        ]),
        VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
    ]
)
"""
        version_path.write_text(version_content)
        Logger.success(f"Created version info: {version_path.name}")
        return version_path
    
    def create_splash_screen(self) -> Optional[Path]:
        """Create splash screen image"""
        if not self.config.splash_screen or not self.config.one_file:
            return None
        
        self.build_path.mkdir(parents=True, exist_ok=True)
        splash_path = self.build_path / "splash.png"
        
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            width, height = 600, 400
            img = Image.new("RGBA", (width, height))
            
            # Gradient background
            for y in range(height):
                for x in range(width):
                    r = int(25 + (y / height) * 25)
                    g = int(35 + (y / height) * 35)
                    b = int(70 + (y / height) * 70)
                    img.putpixel((x, y), (r, g, b, 255))
            
            draw = ImageDraw.Draw(img)
            
            # Try to load font
            try:
                if self.platform == "windows":
                    font_large = ImageFont.truetype("arial.ttf", 48)
                    font_small = ImageFont.truetype("arial.ttf", 20)
                else:
                    font_large = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48
                    )
                    font_small = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20
                    )
            except Exception:
                font_large = ImageFont.load_default()
                font_small = font_large
            
            # Draw text
            draw.text(
                (width // 2, height // 3),
                self.config.name,
                fill=(255, 255, 255, 255),
                anchor="mm",
                font=font_large,
            )
            
            draw.text(
                (width // 2, height // 2),
                f"v{self.config.version}",
                fill=(180, 180, 200, 255),
                anchor="mm",
                font=font_small,
            )
            
            draw.text(
                (width // 2, height * 2 // 3),
                "Loading... جاري التحميل",
                fill=(150, 150, 180, 255),
                anchor="mm",
                font=font_small,
            )
            
            # Progress bar background
            bar_y = height - 60
            bar_width = width - 100
            bar_height = 8
            draw.rectangle(
                [50, bar_y, 50 + bar_width, bar_y + bar_height],
                fill=(50, 50, 80, 255),
            )
            
            img.save(splash_path)
            Logger.success(f"Created splash screen: {splash_path.name}")
            return splash_path
        
        except ImportError:
            Logger.warning("PIL not available, skipping splash screen")
            return None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Build Configuration Methods
    # ═══════════════════════════════════════════════════════════════════════════
    def get_hidden_imports(self) -> list[str]:
        """Get list of hidden imports based on build mode"""
        if self.config.mode == BuildMode.MINIMAL:
            imports = HiddenImportsRegistry.get_minimal()
        else:
            include_web = (
                self.config.mode == BuildMode.FULL and 
                self.config.include_web
            )
            imports = HiddenImportsRegistry.get_all(include_web)
        
        # Add custom imports
        imports.extend(self.config.hidden_imports)
        
        return list(set(imports))  # Remove duplicates
    
    def get_excludes(self) -> list[str]:
        """Get list of modules to exclude based on build mode"""
        if self.config.mode == BuildMode.MINIMAL:
            excludes = ExcludesRegistry.get_minimal()
        else:
            excludes = ExcludesRegistry.get_standard()
        
        # Add custom excludes
        excludes.extend(self.config.excludes)
        
        return list(set(excludes))  # Remove duplicates
    
    def get_data_files(self) -> list[tuple[Path, str]]:
        """Get data files to include"""
        data_files = []
        
        # Desktop resources
        resources = self.desktop_path / "resources"
        if resources.exists():
            data_files.append((resources, "distributed_cluster/desktop/resources"))
        
        # Web templates and static (if enabled)
        if self.config.include_web and self.config.mode in (BuildMode.FULL, BuildMode.RELEASE):
            templates = self.web_path / "templates"
            if templates.exists():
                data_files.append((templates, "distributed_cluster/web/templates"))
            
            static = self.web_path / "static"
            if static.exists():
                data_files.append((static, "distributed_cluster/web/static"))
        
        # Config files
        config_dir = self.project_root / "config"
        if config_dir.exists():
            data_files.append((config_dir, "config"))
        
        # Add custom data files
        for src, dest in self.config.extra_data:
            src_path = Path(src)
            if src_path.exists():
                data_files.append((src_path, dest))
        
        return data_files
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Spec File Generation
    # ═══════════════════════════════════════════════════════════════════════════
    def generate_spec_file(self) -> str:
        """Generate PyInstaller .spec file content"""
        
        # Prepare data files
        data_files_str = []
        for src, dest in self.get_data_files():
            data_files_str.append(f"(r'{src}', '{dest}')")
        
        # Generate collect_all calls
        collect_all_code = ""
        for package in COLLECT_ALL_PACKAGES:
            collect_all_code += f"""
tmp_ret = collect_all('{package}')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
"""
        
        # Determine optimization level
        optimize = 0
        if self.config.mode in (BuildMode.OPTIMIZED, BuildMode.RELEASE):
            optimize = 2
        elif self.config.mode == BuildMode.MINIMAL:
            optimize = 1
        
        # Handle icon
        icon_exists = self.config.icon_path.exists()
        icon_line = f"[r'{self.config.icon_path}']" if icon_exists else "[]"
        
        # Determine console mode
        console_mode = (
            self.config.console or 
            self.config.mode == BuildMode.DEBUG
        )
        
        # Build EXE options
        if self.config.one_file:
            exe_block = f"""
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='{self.config.name}',
    debug={self.config.debug},
    bootloader_ignore_signals=False,
    strip={self.config.strip_binaries and self.platform != 'windows'},
    upx={self.config.upx_compress and self._upx_available},
    upx_exclude=[],
    runtime_tmpdir=None,
    console={console_mode},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon_line},
)
"""
        else:
            exe_block = f"""
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{self.config.name}',
    debug={self.config.debug},
    bootloader_ignore_signals=False,
    strip={self.config.strip_binaries and self.platform != 'windows'},
    upx={self.config.upx_compress and self._upx_available},
    console={console_mode},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon_line},
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip={self.config.strip_binaries and self.platform != 'windows'},
    upx={self.config.upx_compress and self._upx_available},
    upx_exclude=[],
    name='{self.config.name}',
)
"""
        
        hidden_imports = self.get_hidden_imports()
        excludes = self.get_excludes()
        
        spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════════════════
# NebulaCompute Build Spec File
# Generated by NebulaCompute Build System v2.0
# نظام بناء NebulaCompute - ملف الإعدادات
# ═══════════════════════════════════════════════════════════════════════════════
#
# Build Configuration:
#   Mode: {self.config.mode.value}
#   Version: {self.config.version}
#   Platform: {self.platform}
#   One-File: {self.config.one_file}
#   Console: {console_mode}
#
# Generated: {datetime.now().isoformat()}
# ═══════════════════════════════════════════════════════════════════════════════

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

# Data files
datas = [{", ".join(data_files_str)}]

# Binary files
binaries = []

# Hidden imports
hiddenimports = {hidden_imports}

# Collect all from packages
{collect_all_code}

# Analysis
a = Analysis(
    [r'{self.config.entry_point}'],
    pathex=[r'{self.src_path}'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={excludes},
    noarchive=False,
    optimize={optimize},
)

# Create PYZ archive
pyz = PYZ(a.pure)

# Create executable
{exe_block}
'''
        
        return spec_content
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Main Build Method
    # ═══════════════════════════════════════════════════════════════════════════
    def build(self) -> Path:
        """
        Main build method
        الدالة الرئيسية للبناء
        
        Returns:
            Path to the built executable
        """
        # Auto-detect version
        if self.config.version == APP_VERSION:
            self.config.version = self.get_version()
        
        print_banner()
        
        total_steps = 7
        
        # Step 1: Show configuration
        Logger.section("Build Configuration / إعدادات البناء")
        Logger.step(1, total_steps, "Showing configuration...")
        Logger.info(f"Name: {self.config.name}")
        Logger.info(f"Version: {self.config.version}")
        Logger.info(f"Mode: {self.config.mode.value}")
        Logger.info(f"Platform: {self.platform} ({self.arch})")
        Logger.info(f"One file: {self.config.one_file}")
        Logger.info(f"Console: {self.config.console}")
        
        # Step 2: Check tools
        Logger.step(2, total_steps, "Checking build tools...")
        self._check_tools()
        
        # Step 3: Clean previous build
        if self.config.mode != BuildMode.FAST:
            Logger.step(3, total_steps, "Cleaning previous build...")
            self.clean()
        else:
            Logger.step(3, total_steps, "Skipping clean (fast mode)...")
        
        # Create directories
        self.dist_path.mkdir(parents=True, exist_ok=True)
        self.build_path.mkdir(parents=True, exist_ok=True)
        
        # Step 4: Create resources
        Logger.section("Creating Resources / إنشاء الموارد")
        Logger.step(4, total_steps, "Creating resources...")
        icon_path = self.create_icon()
        self.config.icon_path = icon_path
        version_file = self.create_version_info()
        splash_path = self.create_splash_screen()
        
        # Step 5: Verify entry point
        Logger.step(5, total_steps, "Verifying entry point...")
        entry_point = self.config.entry_point
        if not entry_point.exists():
            # Try alternative entry points
            alternatives = [
                self.desktop_path / "main.py",
                self.desktop_path / "__main__.py",
            ]
            for alt in alternatives:
                if alt.exists():
                    entry_point = alt
                    self.config.entry_point = alt
                    break
        
        if not entry_point.exists():
            Logger.error(f"Entry point not found: {entry_point}")
            raise FileNotFoundError(f"Entry point not found: {entry_point}")
        
        Logger.success(f"Entry point: {entry_point}")
        
        # Step 6: Run PyInstaller
        Logger.section("Building Executable / بناء الملف التنفيذي")
        Logger.step(6, total_steps, "Running PyInstaller...")
        
        # Generate and write spec file
        spec_content = self.generate_spec_file()
        self.config.spec_file.write_text(spec_content, encoding="utf-8")
        Logger.info(f"Generated spec file: {self.config.spec_file.name}")
        
        # Build PyInstaller command
        cmd = [
            sys.executable, "-m", "PyInstaller",
            str(self.config.spec_file),
            "--noconfirm",
            f"--distpath={self.dist_path}",
            f"--workpath={self.build_path}",
        ]
        
        # Add log level based on mode
        if self.config.mode == BuildMode.DEBUG:
            cmd.append("--log-level=DEBUG")
        elif self.config.mode == BuildMode.FAST:
            cmd.append("--log-level=WARN")
        else:
            cmd.append("--log-level=INFO")
        
        Logger.info(f"Running: {' '.join(cmd[:5])}...")
        
        try:
            self._run_command(cmd)
        except subprocess.CalledProcessError:
            Logger.error("PyInstaller build failed!")
            raise
        
        # Step 7: Verify output
        Logger.step(7, total_steps, "Verifying output...")
        
        exe_name = f"{self.config.name}.exe" if self.platform == "windows" else self.config.name
        exe_path = self.dist_path / exe_name
        
        if not exe_path.exists():
            # Check for directory mode
            exe_path = self.dist_path / self.config.name / exe_name
            if not exe_path.exists():
                Logger.error(f"Executable not found: {exe_path}")
                raise FileNotFoundError(f"Build output not found: {exe_path}")
        
        # Get file info
        size_bytes = exe_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        
        # Calculate hash
        sha256 = hashlib.sha256()
        with open(exe_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()[:16]
        
        # Create build info
        build_info = {
            "name": self.config.name,
            "version": self.config.version,
            "git_hash": self.get_git_hash(),
            "build_date": datetime.now().isoformat(),
            "build_mode": self.config.mode.value,
            "platform": self.platform,
            "arch": self.arch,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "one_file": self.config.one_file,
            "size_bytes": size_bytes,
            "sha256": sha256.hexdigest(),
            "exe_path": str(exe_path),
        }
        
        info_path = self.dist_path / "build_info.json"
        info_path.write_text(json.dumps(build_info, indent=2, ensure_ascii=False))
        
        # Create installer if requested
        if self.config.installer_type != InstallerType.NONE:
            self._create_installer(exe_path)
        
        # Print success message
        Logger.section("Build Complete! / اكتمل البناء")
        print(f"""
{Colors.GREEN}╔══════════════════════════════════════════════════════════════════════════╗
║                         ✅ BUILD SUCCESSFUL!                               ║
╠══════════════════════════════════════════════════════════════════════════╣
║  📁 Executable: {str(exe_path.name):<58} ║
║  📊 Size: {size_mb:.1f} MB ({size_bytes:,} bytes){' ' * (48 - len(f'{size_mb:.1f} MB ({size_bytes:,} bytes)'))}║
║  🔑 SHA256: {file_hash}...{' ' * 44}║
║  📋 Build info: {info_path.name:<57} ║
╚══════════════════════════════════════════════════════════════════════════╝{Colors.END}
""")
        
        Logger.info(f"Output: {exe_path}")
        Logger.info(f"To run: {exe_path}")
        
        return exe_path
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Installer Creation Methods
    # ═══════════════════════════════════════════════════════════════════════════
    def _create_installer(self, exe_path: Path):
        """Create installer for the executable"""
        Logger.section(f"Creating Installer ({self.config.installer_type.value})")
        
        if self.config.installer_type == InstallerType.NSIS:
            self._create_nsis_installer(exe_path)
        elif self.config.installer_type == InstallerType.APPIMAGE:
            self._create_appimage(exe_path)
        elif self.config.installer_type == InstallerType.DEB:
            self._create_deb_package(exe_path)
        elif self.config.installer_type == InstallerType.DMG:
            self._create_dmg(exe_path)
        else:
            Logger.warning(f"Installer type {self.config.installer_type.value} not implemented")
    
    def _create_nsis_installer(self, exe_path: Path):
        """Create NSIS installer for Windows"""
        nsis_script = f"""; {self.config.name} Installer Script
; Generated by NebulaCompute Build System

!include "MUI2.nsh"
!include "FileFunc.nsh"

; General
Name "{self.config.name}"
OutFile "{self.config.name}_Setup_{self.config.version}.exe"
InstallDir "$PROGRAMFILES\\{self.config.name}"
RequestExecutionLevel admin

; Version Info
VIProductVersion "{self.config.version}.0"
VIAddVersionKey "ProductName" "{self.config.name}"
VIAddVersionKey "CompanyName" "{self.config.author}"
VIAddVersionKey "FileDescription" "{self.config.description}"
VIAddVersionKey "FileVersion" "{self.config.version}"
VIAddVersionKey "ProductVersion" "{self.config.version}"

; Interface Settings
!define MUI_ABORTWARNING

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Languages
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Arabic"

; Installer Section
Section "Install"
    SetOutPath $INSTDIR
    File "{exe_path}"

    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\\{self.config.name}"
    CreateShortCut "$SMPROGRAMS\\{self.config.name}\\{self.config.name}.lnk" "$INSTDIR\\{exe_path.name}"
    CreateShortCut "$SMPROGRAMS\\{self.config.name}\\Uninstall.lnk" "$INSTDIR\\Uninstall.exe"
    CreateShortCut "$DESKTOP\\{self.config.name}.lnk" "$INSTDIR\\{exe_path.name}"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\\Uninstall.exe"

    ; Registry entries
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{self.config.name}" "DisplayName" "{self.config.name}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{self.config.name}" "UninstallString" "$INSTDIR\\Uninstall.exe"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{self.config.name}" "Publisher" "{self.config.author}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{self.config.name}" "DisplayVersion" "{self.config.version}"
SectionEnd

; Uninstaller Section
Section "Uninstall"
    Delete "$INSTDIR\\{exe_path.name}"
    Delete "$INSTDIR\\Uninstall.exe"

    Delete "$SMPROGRAMS\\{self.config.name}\\{self.config.name}.lnk"
    Delete "$SMPROGRAMS\\{self.config.name}\\Uninstall.lnk"
    Delete "$DESKTOP\\{self.config.name}.lnk"

    RMDir "$SMPROGRAMS\\{self.config.name}"
    RMDir "$INSTDIR"

    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{self.config.name}"
SectionEnd
"""
        
        nsis_path = self.build_path / f"{self.config.name}.nsi"
        nsis_path.write_text(nsis_script, encoding="utf-8")
        
        # Try to build if NSIS is available
        if self._nsis_available:
            try:
                result = self._run_command(
                    ["makensis", str(nsis_path)],
                    capture=True,
                    check=False,
                )
                if result.returncode == 0:
                    installer = self.dist_path / f"{self.config.name}_Setup_{self.config.version}.exe"
                    Logger.success(f"Created installer: {installer}")
                else:
                    Logger.warning("NSIS build failed, script saved for manual build")
            except Exception as e:
                Logger.warning(f"NSIS error: {e}")
        else:
            Logger.info(f"NSIS script saved to: {nsis_path}")
            Logger.info("Install NSIS and run: makensis " + str(nsis_path))
    
    def _create_appimage(self, exe_path: Path):
        """Create AppImage for Linux"""
        appdir = self.build_path / f"{self.config.name}.AppDir"
        appdir.mkdir(parents=True, exist_ok=True)
        
        # AppRun script
        apprun = appdir / "AppRun"
        apprun.write_text(f"""#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${{SELF%/*}}
export PATH="${{HERE}}/usr/bin:${{PATH}}"
export LD_LIBRARY_PATH="${{HERE}}/usr/lib:${{LD_LIBRARY_PATH}}"
exec "${{HERE}}/usr/bin/{self.config.name}" "$@"
""")
        os.chmod(apprun, 0o755)
        
        # Desktop file
        desktop = appdir / f"{self.config.name}.desktop"
        desktop.write_text(f"""[Desktop Entry]
Name={self.config.name}
Comment={self.config.description}
Exec={self.config.name}
Icon={self.config.name.lower()}
Terminal=false
Type=Application
Categories=Development;Utility;
""")
        
        # Copy executable
        usr_bin = appdir / "usr" / "bin"
        usr_bin.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe_path, usr_bin / self.config.name)
        os.chmod(usr_bin / self.config.name, 0o755)
        
        Logger.success(f"AppImage directory created: {appdir}")
        Logger.info("To create AppImage, use appimagetool")
    
    def _create_deb_package(self, exe_path: Path):
        """Create DEB package for Debian/Ubuntu"""
        pkg_name = self.config.name.lower()
        pkg_dir = self.build_path / f"{pkg_name}_{self.config.version}"
        
        # Create directory structure
        (pkg_dir / "DEBIAN").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "usr" / "bin").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "usr" / "share" / "applications").mkdir(parents=True, exist_ok=True)
        
        # Control file
        size = exe_path.stat().st_size // 1024
        control = pkg_dir / "DEBIAN" / "control"
        control.write_text(f"""Package: {pkg_name}
Version: {self.config.version}
Section: utils
Priority: optional
Architecture: amd64
Installed-Size: {size}
Maintainer: {self.config.author}
Description: {self.config.description}
 NebulaCompute Desktop - Distributed Computing Management
""")
        
        # Copy executable
        shutil.copy2(exe_path, pkg_dir / "usr" / "bin" / pkg_name)
        os.chmod(pkg_dir / "usr" / "bin" / pkg_name, 0o755)
        
        # Desktop file
        desktop = pkg_dir / "usr" / "share" / "applications" / f"{pkg_name}.desktop"
        desktop.write_text(f"""[Desktop Entry]
Name={self.config.name}
Comment={self.config.description}
Exec={pkg_name}
Icon={pkg_name}
Terminal=false
Type=Application
Categories=Development;Utility;
""")
        
        Logger.success(f"DEB package directory created: {pkg_dir}")
        Logger.info(f"To build: dpkg-deb --build {pkg_dir}")
    
    def _create_dmg(self, exe_path: Path):
        """Create DMG for macOS"""
        Logger.info("DMG creation requires manual app bundle setup")
        Logger.info(f"Executable: {exe_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════════
def install_dependencies() -> bool:
    """Install required build dependencies"""
    Logger.section("Installing Dependencies / تثبيت المتطلبات")
    
    packages = [
        "pyinstaller>=6.0.0",
        "PySide6>=6.6.0",
        "qasync>=0.27.0",
        "httpx>=0.25.0",
        "websockets>=12.0",
        "aiofiles>=23.0.0",
        "aiosqlite>=0.19.0",
        "pydantic>=2.5.0",
        "pillow>=10.0.0",
    ]
    
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade"] + packages,
            check=True,
        )
        Logger.success("Dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        Logger.error(f"Failed to install dependencies: {e}")
        return False


def show_build_info():
    """Show build configuration information"""
    print_banner()
    Logger.section("Build Configuration Info")
    
    config = BuildConfig()
    
    print(f"  Application Name:  {config.name}")
    print(f"  Version:           {config.version}")
    print(f"  Platform:          {platform.system()} {platform.machine()}")
    print(f"  Python:            {sys.version}")
    print(f"  Project Root:      {config.project_root}")
    print(f"  Entry Point:       {config.entry_point}")
    print(f"  Output Directory:  {config.output_dir}")
    print()
    
    print(f"  PyInstaller:       ", end="")
    try:
        import PyInstaller
        print(f"v{PyInstaller.__version__}")
    except ImportError:
        print("Not installed")
    
    print(f"  PySide6:           ", end="")
    try:
        from PySide6 import __version__
        print(f"v{__version__}")
    except ImportError:
        print("Not installed")
    
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════════════════════
def create_parser() -> argparse.ArgumentParser:
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} Build System - نظام البناء المتكامل",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples / أمثلة:
════════════════════════════════════════════════════════════════════════════════
  python build.py                          # Default release build
  python build.py --mode debug             # Debug build with console
  python build.py --mode release           # Optimized release build
  python build.py --mode minimal           # Minimal build (smaller size)
  python build.py --mode full              # Full build with all features
  python build.py --mode fast              # Quick build, skip optimizations
  python build.py --installer nsis         # Build with NSIS installer (Windows)
  python build.py --installer appimage     # Build with AppImage (Linux)
  python build.py --installer deb          # Build with DEB package (Debian)
  python build.py --onedir                 # Create directory bundle
  python build.py --console                # Enable console window
  python build.py --clean                  # Clean build artifacts only
  python build.py --install-deps           # Install build dependencies
  python build.py --info                   # Show build configuration
════════════════════════════════════════════════════════════════════════════════

Build Modes / أوضاع البناء:
────────────────────────────────────────────────────────────────────────────────
  debug      - Debug build with console and debug symbols
  release    - Optimized release build (default)
  minimal    - Smallest size, fewer features
  full       - All features including web server
  fast       - Quick build, skip clean and optimization
  optimized  - Maximum optimization (slower build)
────────────────────────────────────────────────────────────────────────────────
        """,
    )
    
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["debug", "release", "minimal", "full", "fast", "optimized"],
        default="release",
        help="Build mode (default: release)",
    )
    
    parser.add_argument(
        "--version", "-v",
        type=str,
        help="Override version number",
    )
    
    parser.add_argument(
        "--name", "-n",
        type=str,
        default=APP_NAME,
        help=f"Application name (default: {APP_NAME})",
    )
    
    parser.add_argument(
        "--installer", "-i",
        choices=["none", "nsis", "appimage", "deb", "dmg"],
        default="none",
        help="Create installer after build",
    )
    
    parser.add_argument(
        "--console", "-c",
        action="store_true",
        help="Show console window",
    )
    
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Create directory instead of single file",
    )
    
    parser.add_argument(
        "--no-splash",
        action="store_true",
        help="Disable splash screen",
    )
    
    parser.add_argument(
        "--no-upx",
        action="store_true",
        help="Disable UPX compression",
    )
    
    parser.add_argument(
        "--strip",
        action="store_true",
        help="Strip debug symbols (Linux/macOS)",
    )
    
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build artifacts only",
    )
    
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Install build dependencies and exit",
    )
    
    parser.add_argument(
        "--info",
        action="store_true",
        help="Show build configuration info and exit",
    )
    
    parser.add_argument(
        "--debug-build",
        action="store_true",
        help="Enable PyInstaller debug mode",
    )
    
    # CI/CD arguments
    parser.add_argument(
        "--type",
        choices=["debug", "release", "release-optimized", "profile"],
        default="release",
        help="Build type (for CI compatibility)",
    )
    
    parser.add_argument(
        "--platform",
        choices=["windows", "linux", "macos", "auto"],
        default="auto",
        help="Target platform",
    )
    
    parser.add_argument(
        "--arch",
        choices=["x64", "x86", "arm64", "auto"],
        default="auto",
        help="Target architecture",
    )
    
    return parser


def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Handle special actions first
    if args.info:
        show_build_info()
        return 0
    
    if args.install_deps:
        return 0 if install_dependencies() else 1
    
    # Create configuration
    config = BuildConfig(
        name=args.name,
        mode=BuildMode(args.mode),
        one_file=not args.onedir,
        console=args.console or args.mode == "debug",
        splash_screen=not args.no_splash,
        upx_compress=not args.no_upx,
        strip_binaries=args.strip,
        debug=args.debug_build,
        installer_type=InstallerType(args.installer),
    )
    
    if args.version:
        config.version = args.version
    
    # Create builder
    builder = NebulaBuilder(config)
    
    # Clean only
    if args.clean:
        print_banner()
        builder.clean()
        return 0
    
    # Build
    try:
        builder.build()
        return 0
    except Exception as e:
        Logger.error(f"Build failed: {e}")
        if args.debug_build:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())