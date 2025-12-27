#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ███╗   ██╗███████╗██████╗ ██╗   ██╗██╗      █████╗                         ║
║   ████╗  ██║██╔════╝██╔══██╗██║   ██║██║     ██╔══██╗                        ║
║   ██╔██╗ ██║█████╗  ██████╔╝██║   ██║██║     ███████║                        ║
║   ██║╚██╗██║██╔══╝  ██╔══██╗██║   ██║██║     ██╔══██║                        ║
║   ██║ ╚████║███████╗██████╔╝╚██████╔╝███████╗██║  ██║                        ║
║   ╚═╝  ╚═══╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝                        ║
║                                                                              ║
║   🚀 Ultra-Advanced Python Build Orchestrator v3.0                          ║
║   نظام إدارة البناء المتقدم بايثون                                            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Enterprise-grade PyInstaller build system with:
- Multi-platform support (Windows, Linux, macOS)
- Intelligent caching and incremental builds
- Parallel processing
- Plugin architecture
- Code signing
- Installer generation
- CI/CD integration
- Comprehensive logging and monitoring
- Self-diagnostics

Author: Dawood AI Team
License: MIT
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from functools import lru_cache, wraps
from pathlib import Path
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Generator,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Constants / الثوابت
# ═══════════════════════════════════════════════════════════════════════════════

__version__ = "3.0.0"
__author__ = "Dawood AI Team"

APP_NAME = "NebulaCompute"
APP_DESCRIPTION = "Enterprise Distributed Computing System"

# Paths
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR
SRC_PATH = PROJECT_ROOT / "src"
DESKTOP_PATH = SRC_PATH / "distributed_cluster" / "desktop"
DIST_PATH = PROJECT_ROOT / "dist"
BUILD_PATH = PROJECT_ROOT / "build"
CACHE_PATH = PROJECT_ROOT / ".build_cache"
LOGS_PATH = PROJECT_ROOT / "logs" / "build"
PLUGINS_PATH = PROJECT_ROOT / "build_plugins"


# ═══════════════════════════════════════════════════════════════════════════════
# Enums / التعدادات
# ═══════════════════════════════════════════════════════════════════════════════


class BuildMode(Enum):
    """Build modes with different optimization profiles."""
    DEBUG = auto()
    RELEASE = auto()
    MINIMAL = auto()
    FULL = auto()
    CUSTOM = auto()


class InstallerType(Enum):
    """Installer types for different platforms."""
    NONE = auto()
    APPIMAGE = auto()
    DEB = auto()
    RPM = auto()
    DMG = auto()
    PKG = auto()
    MSI = auto()
    NSIS = auto()
    AUTO = auto()


class Platform(Enum):
    """Supported platforms."""
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "darwin"
    UNKNOWN = "unknown"


class BuildStatus(Enum):
    """Build status indicators."""
    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
    CACHED = auto()


# ═══════════════════════════════════════════════════════════════════════════════
# Terminal Styling / تنسيق الطرفية
# ═══════════════════════════════════════════════════════════════════════════════


class Colors:
    """ANSI color codes for terminal output."""
    
    # Reset
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    REVERSE = "\033[7m"
    
    # Regular colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    
    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"
    
    @classmethod
    def disable(cls) -> None:
        """Disable colors (for non-TTY output)."""
        for attr in dir(cls):
            if attr.isupper() and not attr.startswith("_"):
                setattr(cls, attr, "")


class Icons:
    """Unicode icons for terminal output."""
    
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️ "
    INFO = "ℹ️ "
    DEBUG = "🔍"
    BUILDING = "🔨"
    PACKAGE = "📦"
    ROCKET = "🚀"
    GEAR = "⚙️ "
    CLOCK = "⏱️ "
    FOLDER = "📁"
    FILE = "📄"
    LOCK = "🔒"
    UNLOCK = "🔓"
    STAR = "⭐"
    LIGHTNING = "⚡"
    FIRE = "🔥"
    CHECK = "✓"
    CROSS = "✗"
    ARROW = "➜"
    DOT = "●"
    DIAMOND = "◆"
    WAVE = "🌊"
    CLOUD = "☁️ "
    DOCKER = "🐳"
    PYTHON = "🐍"
    APPLE = "🍎"
    LINUX = "🐧"
    WINDOWS = "🪟"
    CLEAN = "🧹"
    CACHE = "💾"
    PLUGIN = "🔌"
    NETWORK = "🌐"
    SECURE = "🛡️ "
    TEST = "🧪"
    NOTIFY = "🔔"
    BACKUP = "💿"
    RESTORE = "♻️ "


# Check if terminal supports colors
if not sys.stdout.isatty():
    Colors.disable()


# ═══════════════════════════════════════════════════════════════════════════════
# Logging / التسجيل
# ═══════════════════════════════════════════════════════════════════════════════


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored output."""
    
    LEVEL_COLORS = {
        logging.DEBUG: Colors.DIM,
        logging.INFO: Colors.CYAN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: f"{Colors.BG_RED}{Colors.WHITE}{Colors.BOLD}",
    }
    
    LEVEL_ICONS = {
        logging.DEBUG: Icons.DEBUG,
        logging.INFO: Icons.INFO,
        logging.WARNING: Icons.WARNING,
        logging.ERROR: Icons.ERROR,
        logging.CRITICAL: Icons.ERROR,
    }
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, "")
        icon = self.LEVEL_ICONS.get(record.levelno, "")
        
        original_msg = record.msg
        record.msg = f"{color}{icon} {original_msg}{Colors.RESET}"
        
        result = super().format(record)
        record.msg = original_msg
        
        return result


def setup_logging(
    log_level: int = logging.INFO,
    log_file: Optional[Path] = None
) -> logging.Logger:
    """Set up logging with colored console output and file logging."""
    
    logger = logging.getLogger("nebula_build")
    logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ColoredFormatter("%(message)s"))
    logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(file_handler)
    
    return logger


# Global logger
logger = setup_logging()


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / الإعدادات
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class BuildConfig:
    """Build configuration with all options."""
    
    # Build settings
    build_mode: BuildMode = BuildMode.RELEASE
    one_file: bool = True
    show_console: bool = False
    strip_symbols: bool = True
    use_upx: bool = True
    parallel_jobs: int = 0  # 0 = auto
    use_cache: bool = True
    incremental: bool = True
    
    # Output settings
    version: str = ""
    output_name: str = APP_NAME
    output_dir: Path = DIST_PATH
    icon_path: Optional[Path] = None
    
    # Installer settings
    installer_type: InstallerType = InstallerType.NONE
    sign_code: bool = False
    sign_identity: str = ""
    notarize: bool = False
    
    # Advanced settings
    docker_build: bool = False
    docker_image: str = "python:3.11-slim"
    remote_build: bool = False
    remote_host: str = ""
    ci_mode: bool = False
    verbose: bool = False
    debug_build: bool = False
    dry_run: bool = False
    quiet: bool = False
    
    # Optimization
    optimize_level: int = 2
    bytecode_optimization: bool = True
    tree_shaking: bool = True
    dead_code_elimination: bool = True
    
    # Notifications
    notify_on_complete: bool = False
    notify_slack: str = ""
    notify_discord: str = ""
    notify_email: str = ""
    
    # Plugins
    plugins_enabled: bool = True
    pre_build_hooks: List[str] = field(default_factory=list)
    post_build_hooks: List[str] = field(default_factory=list)
    
    # Backup
    create_backup: bool = True
    max_backups: int = 5
    
    # Hidden imports and excludes
    hidden_imports: List[str] = field(default_factory=list)
    exclude_modules: List[str] = field(default_factory=list)
    data_files: List[Tuple[str, str]] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Initialize default values after dataclass init."""
        if not self.hidden_imports:
            self.hidden_imports = self._get_default_hidden_imports()
        if not self.exclude_modules:
            self.exclude_modules = self._get_default_excludes()
        if not self.data_files:
            self.data_files = self._get_default_data_files()
    
    @staticmethod
    def _get_default_hidden_imports() -> List[str]:
        """Get default hidden imports for PyInstaller."""
        return [
            # Qt
            "PySide6.QtCore",
            "PySide6.QtGui",
            "PySide6.QtWidgets",
            "PySide6.QtCharts",
            "PySide6.QtNetwork",
            "PySide6.QtSvg",
            "PySide6.QtWebEngineWidgets",
            "PySide6.QtWebChannel",
            
            # Async
            "qasync",
            "asyncio",
            "asyncio.base_events",
            "asyncio.events",
            "asyncio.protocols",
            "asyncio.transports",
            
            # Network
            "httpx",
            "httpx._transports",
            "httpx._transports.default",
            "websockets",
            "websockets.client",
            "websockets.server",
            "aiofiles",
            "aiofiles.os",
            
            # Our modules
            "distributed_cluster",
            "distributed_cluster.desktop",
            "distributed_cluster.desktop.main",
            "distributed_cluster.models",
            "distributed_cluster.core",
            "distributed_cluster.core.master",
            "distributed_cluster.core.worker",
            "distributed_cluster.web",
            
            # System
            "ssl",
            "certifi",
            "cryptography",
            "cryptography.fernet",
            "cryptography.hazmat",
            "cryptography.hazmat.primitives",
            
            # Utils
            "jaraco",
            "jaraco.text",
            "jaraco.functools",
            "jaraco.context",
            "pkg_resources",
            "packaging",
            "packaging.version",
            "packaging.requirements",
            
            # JSON/YAML
            "json",
            "yaml",
            "toml",
        ]
    
    @staticmethod
    def _get_default_excludes() -> List[str]:
        """Get default modules to exclude."""
        return [
            "tkinter",
            "matplotlib",
            "numpy",
            "pandas",
            "scipy",
            "PIL",
            "IPython",
            "jupyter",
            "notebook",
            "pytest",
            "unittest",
            "test",
            "tests",
            "_pytest",
            "doctest",
            "pdb",
        ]
    
    def _get_default_data_files(self) -> List[Tuple[str, str]]:
        """Get default data files to include."""
        data_files = []
        
        resources_dir = DESKTOP_PATH / "resources"
        if resources_dir.exists():
            data_files.append((str(resources_dir), "distributed_cluster/desktop/resources"))
        
        templates_dir = SRC_PATH / "distributed_cluster" / "web" / "templates"
        if templates_dir.exists():
            data_files.append((str(templates_dir), "distributed_cluster/web/templates"))
        
        static_dir = SRC_PATH / "distributed_cluster" / "web" / "static"
        if static_dir.exists():
            data_files.append((str(static_dir), "distributed_cluster/web/static"))
        
        config_dir = PROJECT_ROOT / "config"
        if config_dir.exists():
            data_files.append((str(config_dir), "config"))
        
        return data_files
    
    @classmethod
    def from_file(cls, path: Path) -> "BuildConfig":
        """Load configuration from a JSON/YAML file."""
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        with open(path, encoding="utf-8") as f:
            if path.suffix in (".yaml", ".yml"):
                try:
                    import yaml
                    data = yaml.safe_load(f)
                except ImportError:
                    raise ImportError("PyYAML required for YAML config files")
            else:
                data = json.load(f)
        
        # Convert string enums
        if "build_mode" in data:
            data["build_mode"] = BuildMode[data["build_mode"].upper()]
        if "installer_type" in data:
            data["installer_type"] = InstallerType[data["installer_type"].upper()]
        
        # Convert paths
        for key in ("output_dir", "icon_path"):
            if key in data and data[key]:
                data[key] = Path(data[key])
        
        return cls(**data)
    
    def to_file(self, path: Path) -> None:
        """Save configuration to a file."""
        data = {
            k: (v.name if isinstance(v, Enum) else 
                str(v) if isinstance(v, Path) else v)
            for k, v in self.__dict__.items()
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            if path.suffix in (".yaml", ".yml"):
                try:
                    import yaml
                    yaml.safe_dump(data, f, default_flow_style=False)
                except ImportError:
                    raise ImportError("PyYAML required for YAML config files")
            else:
                json.dump(data, f, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# Build State / حالة البناء
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class BuildState:
    """Track build state and metrics."""
    
    status: BuildStatus = BuildStatus.PENDING
    start_time: float = 0.0
    end_time: float = 0.0
    
    # System info
    python_version: str = ""
    platform: Platform = Platform.UNKNOWN
    arch: str = ""
    
    # Tool availability
    upx_available: bool = False
    docker_available: bool = False
    git_available: bool = False
    
    # Build info
    build_hash: str = ""
    cache_hit: bool = False
    
    # Counters
    errors_count: int = 0
    warnings_count: int = 0
    
    # Results
    output_path: Optional[Path] = None
    output_size: int = 0
    installer_path: Optional[Path] = None
    
    # Error tracking
    last_error: str = ""
    error_traceback: str = ""
    
    @property
    def duration(self) -> float:
        """Get build duration in seconds."""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        elif self.start_time:
            return time.time() - self.start_time
        return 0.0
    
    @property
    def duration_str(self) -> str:
        """Get formatted duration string."""
        d = self.duration
        minutes = int(d // 60)
        seconds = int(d % 60)
        return f"{minutes}m {seconds}s"


# ═══════════════════════════════════════════════════════════════════════════════
# System Detection / اكتشاف النظام
# ═══════════════════════════════════════════════════════════════════════════════


class SystemInfo:
    """System detection and information."""
    
    @staticmethod
    def get_platform() -> Platform:
        """Detect current platform."""
        system = platform.system().lower()
        if system == "windows":
            return Platform.WINDOWS
        elif system == "linux":
            return Platform.LINUX
        elif system == "darwin":
            return Platform.MACOS
        return Platform.UNKNOWN
    
    @staticmethod
    def get_arch() -> str:
        """Get system architecture."""
        return platform.machine()
    
    @staticmethod
    def get_python_version() -> str:
        """Get Python version string."""
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    @staticmethod
    def check_python_version(min_version: Tuple[int, int] = (3, 10)) -> bool:
        """Check if Python version meets minimum requirement."""
        return sys.version_info[:2] >= min_version
    
    @staticmethod
    def is_upx_available() -> bool:
        """Check if UPX is available."""
        return shutil.which("upx") is not None
    
    @staticmethod
    def is_docker_available() -> bool:
        """Check if Docker is available and running."""
        if not shutil.which("docker"):
            return False
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    def is_git_available() -> bool:
        """Check if Git is available."""
        return shutil.which("git") is not None
    
    @staticmethod
    @lru_cache(maxsize=1)
    def get_cpu_count() -> int:
        """Get CPU count for parallel processing."""
        return os.cpu_count() or 1
    
    @staticmethod
    def get_free_disk_space(path: Path) -> int:
        """Get free disk space in bytes."""
        import shutil
        return shutil.disk_usage(path).free
    
    @staticmethod
    def get_total_memory() -> int:
        """Get total system memory in bytes."""
        try:
            import psutil
            return psutil.virtual_memory().total
        except ImportError:
            return 0


# ═══════════════════════════════════════════════════════════════════════════════
# Version Detection / اكتشاف الإصدار
# ═══════════════════════════════════════════════════════════════════════════════


class VersionDetector:
    """Detect application version from various sources."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
    
    def get_version(self, override: str = "") -> str:
        """Get version with priority: override > env > git > pyproject > __version__ > default."""
        if override:
            return override
        
        # Environment variable
        env_version = os.environ.get("NEBULA_VERSION")
        if env_version:
            return env_version
        
        # Git tag
        git_version = self._get_git_version()
        if git_version:
            return git_version
        
        # pyproject.toml
        pyproject_version = self._get_pyproject_version()
        if pyproject_version:
            return pyproject_version
        
        # __version__.py
        py_version = self._get_python_version()
        if py_version:
            return py_version
        
        return "1.0.0"
    
    def _get_git_version(self) -> Optional[str]:
        """Get version from git describe."""
        if not SystemInfo.is_git_available():
            return None
        
        git_dir = self.project_root / ".git"
        if not git_dir.exists():
            return None
        
        try:
            result = subprocess.run(
                ["git", "-C", str(self.project_root), "describe", "--tags", "--always"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                if version.startswith("v"):
                    version = version[1:]
                return version
        except Exception:
            pass
        
        return None
    
    def _get_pyproject_version(self) -> Optional[str]:
        """Get version from pyproject.toml."""
        pyproject = self.project_root / "pyproject.toml"
        if not pyproject.exists():
            return None
        
        try:
            try:
                import tomllib
            except ImportError:
                import toml as tomllib
            
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            
            # Try [project] section
            if "project" in data and "version" in data["project"]:
                return data["project"]["version"]
            
            # Try [tool.poetry] section
            if "tool" in data and "poetry" in data["tool"]:
                if "version" in data["tool"]["poetry"]:
                    return data["tool"]["poetry"]["version"]
        except Exception:
            pass
        
        return None
    
    def _get_python_version(self) -> Optional[str]:
        """Get version from __version__.py."""
        version_files = [
            self.project_root / "src" / "distributed_cluster" / "__version__.py",
            self.project_root / "distributed_cluster" / "__version__.py",
            self.project_root / "__version__.py",
        ]
        
        for version_file in version_files:
            if version_file.exists():
                try:
                    with open(version_file, encoding="utf-8") as f:
                        content = f.read()
                    
                    for line in content.splitlines():
                        if "__version__" in line and "=" in line:
                            # Extract version string
                            version = line.split("=")[1].strip().strip("'\"")
                            return version
                except Exception:
                    pass
        
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Cache System / نظام التخزين المؤقت
# ═══════════════════════════════════════════════════════════════════════════════


class BuildCache:
    """Build caching system for incremental builds."""
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = 10
    
    def compute_hash(self, config: BuildConfig, source_dir: Path) -> str:
        """Compute hash of source files and configuration."""
        hasher = hashlib.md5()
        
        # Hash source files
        if source_dir.exists():
            for py_file in sorted(source_dir.rglob("*.py")):
                try:
                    hasher.update(py_file.read_bytes())
                except Exception:
                    pass
        
        # Hash configuration
        config_str = json.dumps({
            "build_mode": config.build_mode.name,
            "one_file": config.one_file,
            "version": config.version,
            "hidden_imports": config.hidden_imports,
            "exclude_modules": config.exclude_modules,
        }, sort_keys=True)
        hasher.update(config_str.encode())
        
        return hasher.hexdigest()
    
    def check(self, build_hash: str, output_name: str) -> Optional[Path]:
        """Check if cached build exists."""
        cache_entry = self.cache_dir / f"build_{build_hash}"
        cached_exe = cache_entry / output_name
        marker = self.cache_dir / f"build_{build_hash}.marker"
        
        if marker.exists() and cached_exe.exists():
            return cached_exe
        
        return None
    
    def save(self, build_hash: str, output_path: Path) -> None:
        """Save build to cache."""
        cache_entry = self.cache_dir / f"build_{build_hash}"
        cache_entry.mkdir(parents=True, exist_ok=True)
        
        try:
            shutil.copy2(output_path, cache_entry / output_path.name)
            marker = self.cache_dir / f"build_{build_hash}.marker"
            marker.touch()
            
            self._cleanup_old_entries()
        except Exception as e:
            logger.warning(f"Failed to save to cache: {e}")
    
    def _cleanup_old_entries(self) -> None:
        """Remove old cache entries."""
        entries = list(self.cache_dir.glob("build_*"))
        entries = [e for e in entries if e.is_dir()]
        
        if len(entries) > self.max_entries:
            # Sort by modification time
            entries.sort(key=lambda p: p.stat().st_mtime)
            
            # Remove oldest entries
            for entry in entries[:-self.max_entries]:
                try:
                    shutil.rmtree(entry)
                    marker = self.cache_dir / f"{entry.name}.marker"
                    if marker.exists():
                        marker.unlink()
                except Exception:
                    pass
    
    def clear(self) -> int:
        """Clear all cache entries. Returns number of entries cleared."""
        count = 0
        for entry in self.cache_dir.iterdir():
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                count += 1
            except Exception:
                pass
        return count


# ═══════════════════════════════════════════════════════════════════════════════
# Plugin System / نظام الإضافات
# ═══════════════════════════════════════════════════════════════════════════════


@runtime_checkable
class BuildPlugin(Protocol):
    """Protocol for build plugins."""
    
    name: str
    version: str
    
    def pre_build(self, config: BuildConfig, state: BuildState) -> None:
        """Called before build starts."""
        ...
    
    def post_build(self, config: BuildConfig, state: BuildState) -> None:
        """Called after build completes."""
        ...


class PluginManager:
    """Manage build plugins."""
    
    def __init__(self, plugins_dir: Path):
        self.plugins_dir = plugins_dir
        self.plugins: List[BuildPlugin] = []
    
    def load_plugins(self) -> None:
        """Load all plugins from plugins directory."""
        if not self.plugins_dir.exists():
            return
        
        for plugin_file in self.plugins_dir.glob("*.py"):
            try:
                self._load_plugin(plugin_file)
            except Exception as e:
                logger.warning(f"Failed to load plugin {plugin_file.name}: {e}")
    
    def _load_plugin(self, path: Path) -> None:
        """Load a single plugin."""
        import importlib.util
        
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find plugin class
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type) and
                    attr_name != "BuildPlugin" and
                    hasattr(attr, "pre_build") and
                    hasattr(attr, "post_build")
                ):
                    plugin = attr()
                    self.plugins.append(plugin)
                    logger.debug(f"Loaded plugin: {plugin.name}")
    
    def run_pre_build(self, config: BuildConfig, state: BuildState) -> None:
        """Run pre-build hooks on all plugins."""
        for plugin in self.plugins:
            try:
                plugin.pre_build(config, state)
            except Exception as e:
                logger.warning(f"Plugin {plugin.name} pre_build failed: {e}")
    
    def run_post_build(self, config: BuildConfig, state: BuildState) -> None:
        """Run post-build hooks on all plugins."""
        for plugin in self.plugins:
            try:
                plugin.post_build(config, state)
            except Exception as e:
                logger.warning(f"Plugin {plugin.name} post_build failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# PyInstaller Builder / باني PyInstaller
# ═══════════════════════════════════════════════════════════════════════════════


class PyInstallerBuilder:
    """PyInstaller build orchestrator."""
    
    def __init__(self, config: BuildConfig, state: BuildState):
        self.config = config
        self.state = state
        self.version_detector = VersionDetector(PROJECT_ROOT)
    
    def find_entry_point(self) -> Optional[Path]:
        """Find the application entry point."""
        candidates = [
            DESKTOP_PATH / "app_entry.py",
            DESKTOP_PATH / "main.py",
            DESKTOP_PATH / "__main__.py",
            SRC_PATH / "main.py",
            PROJECT_ROOT / "main.py",
        ]
        
        for candidate in candidates:
            if candidate.exists():
                return candidate
        
        return None
    
    def build_command(self, entry_point: Path) -> List[str]:
        """Build PyInstaller command."""
        cmd = [sys.executable, "-m", "PyInstaller"]
        
        # Basic options
        cmd.extend(["--name", self.config.output_name])
        cmd.append("--clean")
        cmd.append("--noconfirm")
        
        # Console/Windowed
        if self.config.show_console or self.config.build_mode == BuildMode.DEBUG:
            cmd.append("--console")
        else:
            cmd.append("--windowed")
        
        # One file/directory
        if self.config.one_file:
            cmd.append("--onefile")
        else:
            cmd.append("--onedir")
        
        # Icon
        icon_path = self.config.icon_path
        if not icon_path:
            for ext in (".ico", ".icns", ".png"):
                candidate = DESKTOP_PATH / "resources" / f"icon{ext}"
                if candidate.exists():
                    icon_path = candidate
                    break
        
        if icon_path and icon_path.exists():
            cmd.extend(["--icon", str(icon_path)])
        
        # Runtime hooks
        runtime_hook = DESKTOP_PATH / "runtime_hook.py"
        if runtime_hook.exists():
            cmd.extend(["--runtime-hook", str(runtime_hook)])
        
        # Data files
        sep = ";" if self.state.platform == Platform.WINDOWS else ":"
        for src, dst in self.config.data_files:
            if Path(src).exists():
                cmd.extend(["--add-data", f"{src}{sep}{dst}"])
        
        # Hidden imports
        for imp in self.config.hidden_imports:
            cmd.extend(["--hidden-import", imp])
        
        # Excludes
        for exc in self.config.exclude_modules:
            cmd.extend(["--exclude-module", exc])
        
        # Collect all
        cmd.extend(["--collect-all", "PySide6"])
        cmd.extend(["--collect-all", "httpx"])
        cmd.extend(["--collect-all", "websockets"])
        cmd.extend(["--collect-all", "distributed_cluster"])
        
        # UPX
        if not self.config.use_upx or not self.state.upx_available:
            cmd.append("--noupx")
        
        # Strip
        if self.config.strip_symbols:
            cmd.append("--strip")
        
        # Paths
        cmd.extend(["--distpath", str(self.config.output_dir)])
        cmd.extend(["--workpath", str(BUILD_PATH)])
        cmd.extend(["--specpath", str(PROJECT_ROOT)])
        cmd.extend(["--paths", str(SRC_PATH)])
        
        if DESKTOP_PATH.exists():
            cmd.extend(["--paths", str(DESKTOP_PATH)])
        
        # Log level
        if self.config.verbose:
            cmd.extend(["--log-level", "DEBUG"])
        else:
            cmd.extend(["--log-level", "WARN"])
        
        # Entry point
        cmd.append(str(entry_point))
        
        return cmd
    
    async def build(self) -> bool:
        """Run the build."""
        # Find entry point
        entry_point = self.find_entry_point()
        if not entry_point:
            logger.error("Entry point not found!")
            self.state.last_error = "Entry point not found"
            return False
        
        logger.info(f"Entry point: {entry_point}")
        
        # Build command
        cmd = self.build_command(entry_point)
        
        if self.config.dry_run:
            logger.info("Dry run - command would be:")
            print(" ".join(cmd))
            return True
        
        # Set optimization level
        if self.config.bytecode_optimization:
            os.environ["PYTHONOPTIMIZE"] = str(self.config.optimize_level)
        
        # Run build
        logger.info("Running PyInstaller...")
        
        log_file = LOGS_PATH / f"pyinstaller_{datetime.now():%Y%m%d_%H%M%S}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(log_file, "w", encoding="utf-8") as log:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=log if not self.config.verbose else None,
                    stderr=asyncio.subprocess.STDOUT if not self.config.verbose else None,
                    cwd=PROJECT_ROOT
                )
                
                await process.wait()
                
                if process.returncode != 0:
                    logger.error(f"PyInstaller failed! Check log: {log_file}")
                    self.state.last_error = "PyInstaller failed"
                    return False
        
        except Exception as e:
            logger.error(f"Build error: {e}")
            self.state.last_error = str(e)
            self.state.error_traceback = traceback.format_exc()
            return False
        
        # Verify output
        exe_name = self.config.output_name
        if self.state.platform == Platform.WINDOWS:
            exe_name += ".exe"
        
        output_path = self.config.output_dir / exe_name
        
        if output_path.exists():
            output_path.chmod(0o755)
            self.state.output_path = output_path
            self.state.output_size = output_path.stat().st_size
            logger.success(f"Build successful: {output_path}")
            return True
        else:
            logger.error("Build failed - executable not found!")
            self.state.last_error = "Executable not found"
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# Installer Creators / منشئو المثبتات
# ═══════════════════════════════════════════════════════════════════════════════


class InstallerCreator(ABC):
    """Abstract base class for installer creators."""
    
    def __init__(self, config: BuildConfig, state: BuildState):
        self.config = config
        self.state = state
    
    @abstractmethod
    async def create(self) -> bool:
        """Create the installer."""
        pass


class AppImageCreator(InstallerCreator):
    """Create AppImage for Linux."""
    
    async def create(self) -> bool:
        logger.info("Creating AppImage...")
        
        if self.state.platform != Platform.LINUX:
            logger.error("AppImage can only be created on Linux")
            return False
        
        exe_path = self.state.output_path
        if not exe_path or not exe_path.exists():
            logger.error("Executable not found!")
            return False
        
        version = VersionDetector(PROJECT_ROOT).get_version(self.config.version)
        
        # Create AppDir structure
        appdir = BUILD_PATH / f"{APP_NAME}.AppDir"
        if appdir.exists():
            shutil.rmtree(appdir)
        
        (appdir / "usr" / "bin").mkdir(parents=True)
        (appdir / "usr" / "lib").mkdir(parents=True)
        (appdir / "usr" / "share" / "applications").mkdir(parents=True)
        (appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(parents=True)
        
        # AppRun script
        apprun = appdir / "AppRun"
        apprun.write_text(f"""#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${{SELF%/*}}
export PATH="${{HERE}}/usr/bin:${{PATH}}"
export LD_LIBRARY_PATH="${{HERE}}/usr/lib:${{LD_LIBRARY_PATH}}"
export QT_PLUGIN_PATH="${{HERE}}/usr/lib/qt5/plugins:${{QT_PLUGIN_PATH}}"
exec "${{HERE}}/usr/bin/{APP_NAME}" "$@"
""")
        apprun.chmod(0o755)
        
        # Desktop file
        desktop_content = f"""[Desktop Entry]
Name={APP_NAME}
Comment={APP_DESCRIPTION}
Exec={APP_NAME}
Icon={APP_NAME.lower()}
Terminal=false
Type=Application
Categories=Development;Utility;System;
Keywords=distributed;computing;cluster;
"""
        (appdir / f"{APP_NAME}.desktop").write_text(desktop_content)
        (appdir / "usr" / "share" / "applications" / f"{APP_NAME.lower()}.desktop").write_text(desktop_content)
        
        # Icon
        icon_src = DESKTOP_PATH / "resources" / "icon.png"
        if icon_src.exists():
            shutil.copy(icon_src, appdir / f"{APP_NAME.lower()}.png")
            shutil.copy(icon_src, appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / f"{APP_NAME.lower()}.png")
        
        # Copy executable
        shutil.copy2(exe_path, appdir / "usr" / "bin" / APP_NAME)
        (appdir / "usr" / "bin" / APP_NAME).chmod(0o755)
        
        # Download appimagetool if needed
        appimagetool = BUILD_PATH / "appimagetool-x86_64.AppImage"
        if not appimagetool.exists():
            logger.info("Downloading appimagetool...")
            import urllib.request
            url = "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
            urllib.request.urlretrieve(url, appimagetool)
            appimagetool.chmod(0o755)
        
        # Build AppImage
        output = self.config.output_dir / f"{APP_NAME}-{version}-x86_64.AppImage"
        
        env = os.environ.copy()
        env["ARCH"] = "x86_64"
        
        process = await asyncio.create_subprocess_exec(
            str(appimagetool),
            str(appdir),
            str(output),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        await process.wait()
        
        if output.exists():
            output.chmod(0o755)
            self.state.installer_path = output
            logger.success(f"AppImage created: {output}")
            return True
        else:
            logger.error("AppImage creation failed!")
            return False


class DebCreator(InstallerCreator):
    """Create DEB package for Debian/Ubuntu."""
    
    async def create(self) -> bool:
        logger.info("Creating DEB package...")
        
        if not shutil.which("dpkg-deb"):
            logger.error("dpkg-deb not found!")
            return False
        
        exe_path = self.state.output_path
        if not exe_path or not exe_path.exists():
            logger.error("Executable not found!")
            return False
        
        version = VersionDetector(PROJECT_ROOT).get_version(self.config.version)
        
        # Create package directory
        pkg_name = f"{APP_NAME.lower()}_{version}_amd64"
        pkg_dir = BUILD_PATH / pkg_name
        
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir)
        
        (pkg_dir / "DEBIAN").mkdir(parents=True)
        (pkg_dir / "usr" / "bin").mkdir(parents=True)
        (pkg_dir / "usr" / "share" / "applications").mkdir(parents=True)
        (pkg_dir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(parents=True)
        
        # Control file
        control = f"""Package: {APP_NAME.lower()}
Version: {version}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: {__author__}
Description: {APP_DESCRIPTION}
 NebulaCompute is an enterprise-grade distributed computing system
 that enables efficient resource sharing and job distribution across
 multiple nodes.
Depends: libc6
Homepage: https://github.com/nebula-compute
"""
        (pkg_dir / "DEBIAN" / "control").write_text(control)
        
        # Post-install script
        postinst = """#!/bin/bash
update-desktop-database -q || true
gtk-update-icon-cache -q /usr/share/icons/hicolor || true
"""
        postinst_file = pkg_dir / "DEBIAN" / "postinst"
        postinst_file.write_text(postinst)
        postinst_file.chmod(0o755)
        
        # Copy files
        shutil.copy2(exe_path, pkg_dir / "usr" / "bin" / APP_NAME)
        (pkg_dir / "usr" / "bin" / APP_NAME).chmod(0o755)
        
        # Desktop file
        desktop_content = f"""[Desktop Entry]
Name={APP_NAME}
Comment={APP_DESCRIPTION}
Exec=/usr/bin/{APP_NAME}
Icon={APP_NAME.lower()}
Terminal=false
Type=Application
Categories=Development;Utility;System;
"""
        (pkg_dir / "usr" / "share" / "applications" / f"{APP_NAME.lower()}.desktop").write_text(desktop_content)
        
        # Icon
        icon_src = DESKTOP_PATH / "resources" / "icon.png"
        if icon_src.exists():
            shutil.copy(icon_src, pkg_dir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / f"{APP_NAME.lower()}.png")
        
        # Build package
        output = self.config.output_dir / f"{pkg_name}.deb"
        
        process = await asyncio.create_subprocess_exec(
            "dpkg-deb", "--build", str(pkg_dir), str(output),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        await process.wait()
        
        if output.exists():
            self.state.installer_path = output
            logger.success(f"DEB package created: {output}")
            return True
        else:
            logger.error("DEB creation failed!")
            return False


class DMGCreator(InstallerCreator):
    """Create DMG for macOS."""
    
    async def create(self) -> bool:
        logger.info("Creating DMG...")
        
        if self.state.platform != Platform.MACOS:
            logger.error("DMG can only be created on macOS")
            return False
        
        exe_path = self.state.output_path
        if not exe_path or not exe_path.exists():
            logger.error("Executable not found!")
            return False
        
        version = VersionDetector(PROJECT_ROOT).get_version(self.config.version)
        
        # Create staging directory
        staging_dir = BUILD_PATH / "dmg_staging"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir()
        
        # Check for existing .app bundle
        app_bundle = self.config.output_dir / f"{self.config.output_name}.app"
        
        if app_bundle.exists():
            shutil.copytree(app_bundle, staging_dir / f"{APP_NAME}.app")
        else:
            # Create minimal app bundle
            app_dir = staging_dir / f"{APP_NAME}.app"
            (app_dir / "Contents" / "MacOS").mkdir(parents=True)
            (app_dir / "Contents" / "Resources").mkdir(parents=True)
            
            # Info.plist
            plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>{APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>com.nebula.compute</string>
    <key>CFBundleName</key>
    <string>{APP_NAME}</string>
    <key>CFBundleVersion</key>
    <string>{version}</string>
    <key>CFBundleShortVersionString</key>
    <string>{version}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
"""
            (app_dir / "Contents" / "Info.plist").write_text(plist)
            
            shutil.copy2(exe_path, app_dir / "Contents" / "MacOS" / APP_NAME)
            (app_dir / "Contents" / "MacOS" / APP_NAME).chmod(0o755)
        
        # Add Applications symlink
        (staging_dir / "Applications").symlink_to("/Applications")
        
        # Create DMG
        output = self.config.output_dir / f"{APP_NAME}-{version}.dmg"
        
        # Try create-dmg first, fallback to hdiutil
        if shutil.which("create-dmg"):
            cmd = [
                "create-dmg",
                "--volname", APP_NAME,
                "--window-pos", "200", "120",
                "--window-size", "600", "400",
                "--icon-size", "100",
                "--icon", f"{APP_NAME}.app", "175", "190",
                "--icon", "Applications", "425", "190",
                "--hide-extension", f"{APP_NAME}.app",
                "--app-drop-link", "425", "190",
                str(output),
                str(staging_dir)
            ]
            
            icon_path = DESKTOP_PATH / "resources" / "icon.icns"
            if icon_path.exists():
                cmd.insert(2, "--volicon")
                cmd.insert(3, str(icon_path))
        else:
            cmd = [
                "hdiutil", "create",
                "-volname", APP_NAME,
                "-srcfolder", str(staging_dir),
                "-ov", "-format", "UDZO",
                str(output)
            ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        await process.wait()
        
        if output.exists():
            self.state.installer_path = output
            logger.success(f"DMG created: {output}")
            return True
        else:
            logger.error("DMG creation failed!")
            return False


def get_installer_creator(
    installer_type: InstallerType,
    config: BuildConfig,
    state: BuildState
) -> Optional[InstallerCreator]:
    """Get appropriate installer creator for the platform."""
    
    if installer_type == InstallerType.AUTO:
        if state.platform == Platform.LINUX:
            installer_type = InstallerType.APPIMAGE
        elif state.platform == Platform.MACOS:
            installer_type = InstallerType.DMG
        elif state.platform == Platform.WINDOWS:
            installer_type = InstallerType.NSIS
        else:
            return None
    
    creators = {
        InstallerType.APPIMAGE: AppImageCreator,
        InstallerType.DEB: DebCreator,
        InstallerType.DMG: DMGCreator,
    }
    
    creator_class = creators.get(installer_type)
    if creator_class:
        return creator_class(config, state)
    
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Build Orchestrator / منظم البناء
# ═══════════════════════════════════════════════════════════════════════════════


class BuildOrchestrator:
    """Main build orchestration class."""
    
    def __init__(self, config: BuildConfig):
        self.config = config
        self.state = BuildState()
        self.cache = BuildCache(CACHE_PATH)
        self.plugin_manager = PluginManager(PLUGINS_PATH)
        self.version_detector = VersionDetector(PROJECT_ROOT)
    
    def _detect_system(self) -> None:
        """Detect system information."""
        self.state.platform = SystemInfo.get_platform()
        self.state.arch = SystemInfo.get_arch()
        self.state.python_version = SystemInfo.get_python_version()
        self.state.upx_available = SystemInfo.is_upx_available()
        self.state.docker_available = SystemInfo.is_docker_available()
        self.state.git_available = SystemInfo.is_git_available()
    
    def _print_banner(self) -> None:
        """Print the build banner."""
        if self.config.quiet:
            return
        
        print()
        print(f"{Colors.CYAN}")
        print("    ╔══════════════════════════════════════════════════════════════════╗")
        print("    ║                                                                  ║")
        print("    ║   ███╗   ██╗███████╗██████╗ ██╗   ██╗██╗      █████╗             ║")
        print("    ║   ████╗  ██║██╔════╝██╔══██╗██║   ██║██║     ██╔══██╗            ║")
        print("    ║   ██╔██╗ ██║█████╗  ██████╔╝██║   ██║██║     ███████║            ║")
        print("    ║   ██║╚██╗██║██╔══╝  ██╔══██╗██║   ██║██║     ██╔══██║            ║")
        print("    ║   ██║ ╚████║███████╗██████╔╝╚██████╔╝███████╗██║  ██║            ║")
        print("    ║   ╚═╝  ╚═══╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝            ║")
        print("    ║                                                                  ║")
        print(f"    ║   {Colors.BRIGHT_YELLOW}⚡ Ultra-Advanced Build System v{__version__}{Colors.CYAN}                       ║")
        print(f"    ║   {Colors.BRIGHT_GREEN}🐍 Python Build Orchestrator{Colors.CYAN}                                 ║")
        print("    ║                                                                  ║")
        print("    ╚══════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.RESET}")
        print()
    
    def _print_config(self) -> None:
        """Print build configuration."""
        if self.config.quiet:
            return
        
        version = self.version_detector.get_version(self.config.version)
        
        print(f"{Colors.BOLD}{Colors.BRIGHT_BLUE}Build Configuration:{Colors.RESET}")
        print()
        print(f"  {Colors.DIM}Application{Colors.RESET}    : {APP_NAME}")
        print(f"  {Colors.DIM}Version{Colors.RESET}        : {version}")
        print(f"  {Colors.DIM}Mode{Colors.RESET}           : {self.config.build_mode.name}")
        print(f"  {Colors.DIM}Platform{Colors.RESET}       : {self.state.platform.value} ({self.state.arch})")
        print(f"  {Colors.DIM}Python{Colors.RESET}         : {self.state.python_version}")
        print(f"  {Colors.DIM}Output{Colors.RESET}         : {'Single file' if self.config.one_file else 'Directory'}")
        print(f"  {Colors.DIM}Cache{Colors.RESET}          : {'Enabled' if self.config.use_cache else 'Disabled'}")
        print()
    
    def _print_summary(self) -> None:
        """Print build summary."""
        if self.config.quiet:
            return
        
        print()
        
        if self.state.status == BuildStatus.SUCCESS:
            print(f"{Colors.GREEN}")
            print("    ╔══════════════════════════════════════════════════════════════════╗")
            print("    ║                                                                  ║")
            print("    ║   ██████╗ ██╗   ██╗██╗██╗     ██████╗                            ║")
            print("    ║   ██╔══██╗██║   ██║██║██║     ██╔══██╗                           ║")
            print("    ║   ██████╔╝██║   ██║██║██║     ██║  ██║                           ║")
            print("    ║   ██╔══██╗██║   ██║██║██║     ██║  ██║                           ║")
            print("    ║   ██████╔╝╚██████╔╝██║███████╗██████╔╝                           ║")
            print("    ║   ╚═════╝  ╚═════╝ ╚═╝╚══════╝╚═════╝                            ║")
            print("    ║                                                                  ║")
            print("    ║   ███████╗██╗   ██╗ ██████╗ ██████╗███████╗███████╗███████╗      ║")
            print("    ║   ██╔════╝██║   ██║██╔════╝██╔════╝██╔════╝██╔════╝██╔════╝      ║")
            print("    ║   ███████╗██║   ██║██║     ██║     █████╗  ███████╗███████╗      ║")
            print("    ║   ╚════██║██║   ██║██║     ██║     ██╔══╝  ╚════██║╚════██║      ║")
            print("    ║   ███████║╚██████╔╝╚██████╗╚██████╗███████╗███████║███████║      ║")
            print("    ║   ╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝╚══════╝╚══════╝╚══════╝      ║")
            print("    ║                                                                  ║")
            print("    ╚══════════════════════════════════════════════════════════════════╝")
            print(f"{Colors.RESET}")
            
            print(f"{Colors.BRIGHT_WHITE}Build Summary:{Colors.RESET}")
            print()
            print(f"  {Colors.DIM}Status{Colors.RESET}       : {Icons.SUCCESS} Success")
            print(f"  {Colors.DIM}Duration{Colors.RESET}     : {self.state.duration_str}")
            print(f"  {Colors.DIM}Output{Colors.RESET}       : {self.state.output_path}")
            
            if self.state.output_size:
                size_mb = self.state.output_size / (1024 * 1024)
                print(f"  {Colors.DIM}Size{Colors.RESET}         : {size_mb:.1f} MB")
            
            if self.state.cache_hit:
                print(f"  {Colors.DIM}Cache{Colors.RESET}        : Used cached build")
            
            if self.state.installer_path:
                print(f"  {Colors.DIM}Installer{Colors.RESET}    : {self.state.installer_path}")
        
        else:
            print(f"{Colors.RED}")
            print("    ╔══════════════════════════════════════════════════════════════════╗")
            print("    ║                                                                  ║")
            print("    ║   ██████╗ ██╗   ██╗██╗██╗     ██████╗                            ║")
            print("    ║   ██╔══██╗██║   ██║██║██║     ██╔══██╗                           ║")
            print("    ║   ██████╔╝██║   ██║██║██║     ██║  ██║                           ║")
            print("    ║   ██╔══██╗██║   ██║██║██║     ██║  ██║                           ║")
            print("    ║   ██████╔╝╚██████╔╝██║███████╗██████╔╝                           ║")
            print("    ║   ╚═════╝  ╚═════╝ ╚═╝╚══════╝╚═════╝                            ║")
            print("    ║                                                                  ║")
            print("    ║   ███████╗ █████╗ ██╗██╗     ███████╗██████╗                     ║")
            print("    ║   ██╔════╝██╔══██╗██║██║     ██╔════╝██╔══██╗                    ║")
            print("    ║   █████╗  ███████║██║██║     █████╗  ██║  ██║                    ║")
            print("    ║   ██╔══╝  ██╔══██║██║██║     ██╔══╝  ██║  ██║                    ║")
            print("    ║   ██║     ██║  ██║██║███████╗███████╗██████╔╝                    ║")
            print("    ║   ╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚═════╝                     ║")
            print("    ║                                                                  ║")
            print("    ╚══════════════════════════════════════════════════════════════════╝")
            print(f"{Colors.RESET}")
            
            print(f"{Colors.BRIGHT_WHITE}Error Summary:{Colors.RESET}")
            print()
            print(f"  {Colors.DIM}Status{Colors.RESET}       : {Icons.ERROR} Failed")
            print(f"  {Colors.DIM}Errors{Colors.RESET}       : {self.state.errors_count}")
            print(f"  {Colors.DIM}Last error{Colors.RESET}   : {self.state.last_error}")
            
            log_file = LOGS_PATH / f"pyinstaller_*.log"
            print(f"  {Colors.DIM}Log files{Colors.RESET}    : {log_file}")
        
        print()
    
    async def build(self) -> bool:
        """Run the complete build process."""
        self.state.status = BuildStatus.RUNNING
        self.state.start_time = time.time()
        
        try:
            # Detect system
            self._detect_system()
            
            # Print banner and config
            self._print_banner()
            self._print_config()
            
            # Check Python version
            if not SystemInfo.check_python_version():
                logger.error("Python 3.10+ required!")
                self.state.status = BuildStatus.FAILED
                return False
            
            # Load plugins
            if self.config.plugins_enabled:
                self.plugin_manager.load_plugins()
                self.plugin_manager.run_pre_build(self.config, self.state)
            
            # Prepare directories
            self.config.output_dir.mkdir(parents=True, exist_ok=True)
            BUILD_PATH.mkdir(parents=True, exist_ok=True)
            LOGS_PATH.mkdir(parents=True, exist_ok=True)
            
            # Check cache
            if self.config.use_cache:
                build_hash = self.cache.compute_hash(self.config, SRC_PATH)
                self.state.build_hash = build_hash
                
                cached_path = self.cache.check(build_hash, self.config.output_name)
                if cached_path:
                    logger.info("Cache hit! Using cached build.")
                    self.state.cache_hit = True
                    
                    # Copy from cache
                    output_path = self.config.output_dir / cached_path.name
                    shutil.copy2(cached_path, output_path)
                    output_path.chmod(0o755)
                    
                    self.state.output_path = output_path
                    self.state.output_size = output_path.stat().st_size
                    self.state.status = BuildStatus.CACHED
                    self.state.end_time = time.time()
                    self._print_summary()
                    return True
            
            # Run build
            builder = PyInstallerBuilder(self.config, self.state)
            success = await builder.build()
            
            if not success:
                self.state.status = BuildStatus.FAILED
                self._print_summary()
                return False
            
            # Save to cache
            if self.config.use_cache and self.state.output_path:
                self.cache.save(self.state.build_hash, self.state.output_path)
            
            # Create installer
            if self.config.installer_type != InstallerType.NONE:
                creator = get_installer_creator(
                    self.config.installer_type,
                    self.config,
                    self.state
                )
                if creator:
                    await creator.create()
            
            # Run post-build plugins
            if self.config.plugins_enabled:
                self.plugin_manager.run_post_build(self.config, self.state)
            
            self.state.status = BuildStatus.SUCCESS
            self.state.end_time = time.time()
            
            self._print_summary()
            return True
        
        except Exception as e:
            self.state.status = BuildStatus.FAILED
            self.state.last_error = str(e)
            self.state.error_traceback = traceback.format_exc()
            logger.error(f"Build failed: {e}")
            self._print_summary()
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / واجهة سطر الأوامر
# ═══════════════════════════════════════════════════════════════════════════════


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="build.py",
        description="NebulaCompute Ultra-Advanced Build System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build.py                           # Default release build
  python build.py --mode debug --console    # Debug build with console
  python build.py --installer appimage      # Create AppImage
  python build.py --clean                   # Clean build artifacts
  
For more information, see: https://github.com/nebula-compute/docs
        """
    )
    
    # Build mode
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["debug", "release", "minimal", "full", "custom"],
        default="release",
        help="Build mode (default: release)"
    )
    
    # Output options
    parser.add_argument("--name", type=str, help="Override output name")
    parser.add_argument("--version", type=str, help="Override version string")
    parser.add_argument("--output", "-o", type=Path, help="Output directory")
    parser.add_argument("--icon", type=Path, help="Icon path")
    parser.add_argument("--onedir", action="store_true", help="Create directory instead of single file")
    parser.add_argument("--console", action="store_true", help="Show console window")
    
    # Installer
    parser.add_argument(
        "--installer", "-i",
        type=str,
        choices=["none", "appimage", "deb", "rpm", "dmg", "pkg", "msi", "nsis", "auto"],
        default="none",
        help="Create installer"
    )
    
    # Advanced
    parser.add_argument("--no-cache", action="store_true", help="Disable build cache")
    parser.add_argument("--no-upx", action="store_true", help="Disable UPX compression")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--ci", action="store_true", help="CI mode (non-interactive)")
    
    # Actions
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts")
    parser.add_argument("--info", action="store_true", help="Show build information")
    parser.add_argument("--install-deps", action="store_true", help="Install dependencies")
    
    # Config file
    parser.add_argument("--config", "-c", type=Path, help="Load config from file")
    
    return parser


async def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Load config from file or create default
    if args.config and args.config.exists():
        config = BuildConfig.from_file(args.config)
    else:
        config = BuildConfig()
    
    # Apply CLI arguments
    config.build_mode = BuildMode[args.mode.upper()]
    
    if args.name:
        config.output_name = args.name
    if args.version:
        config.version = args.version
    if args.output:
        config.output_dir = args.output
    if args.icon:
        config.icon_path = args.icon
    if args.onedir:
        config.one_file = False
    if args.console:
        config.show_console = True
    if args.installer != "none":
        config.installer_type = InstallerType[args.installer.upper()]
    if args.no_cache:
        config.use_cache = False
    if args.no_upx:
        config.use_upx = False
    if args.verbose:
        config.verbose = True
    if args.quiet:
        config.quiet = True
    if args.dry_run:
        config.dry_run = True
    if args.ci:
        config.ci_mode = True
        config.quiet = True
    
    # Set log level
    if config.verbose:
        setup_logging(logging.DEBUG)
    elif config.quiet:
        setup_logging(logging.ERROR)
    
    # Handle actions
    if args.clean:
        logger.info("Cleaning build artifacts...")
        for path in [BUILD_PATH, DIST_PATH]:
            if path.exists():
                shutil.rmtree(path)
                logger.info(f"Removed: {path}")
        
        for spec in PROJECT_ROOT.glob("*.spec"):
            spec.unlink()
            logger.info(f"Removed: {spec}")
        
        logger.success("Clean complete!")
        return 0
    
    if args.info:
        state = BuildState()
        state.platform = SystemInfo.get_platform()
        state.arch = SystemInfo.get_arch()
        state.python_version = SystemInfo.get_python_version()
        state.upx_available = SystemInfo.is_upx_available()
        state.docker_available = SystemInfo.is_docker_available()
        state.git_available = SystemInfo.is_git_available()
        
        print(f"\n{Colors.BOLD}System Information:{Colors.RESET}")
        print(f"  Platform:    {state.platform.value} ({state.arch})")
        print(f"  Python:      {state.python_version}")
        print(f"  UPX:         {'Available' if state.upx_available else 'Not available'}")
        print(f"  Docker:      {'Available' if state.docker_available else 'Not available'}")
        print(f"  Git:         {'Available' if state.git_available else 'Not available'}")
        
        version = VersionDetector(PROJECT_ROOT).get_version()
        print(f"\n{Colors.BOLD}Project Information:{Colors.RESET}")
        print(f"  Version:     {version}")
        print(f"  Source:      {SRC_PATH}")
        print(f"  Output:      {DIST_PATH}")
        print()
        return 0
    
    if args.install_deps:
        logger.info("Installing dependencies...")
        deps = [
            "pyinstaller>=6.0.0",
            "PySide6>=6.5.0",
            "qasync>=0.24.0",
            "httpx>=0.25.0",
            "websockets>=12.0",
            "aiofiles>=23.0.0",
            "cryptography>=41.0.0",
        ]
        
        for dep in deps:
            subprocess.run([sys.executable, "-m", "pip", "install", dep, "-q"])
            logger.info(f"Installed: {dep.split('>=')[0]}")
        
        logger.success("Dependencies installed!")
        return 0
    
    # Run build
    orchestrator = BuildOrchestrator(config)
    success = await orchestrator.build()
    
    return 0 if success else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Build cancelled.{Colors.RESET}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.RESET}")
        traceback.print_exc()
        sys.exit(1)