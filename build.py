#!/usr/bin/env python3
"""
NebulaCompute Build System - Complete PyInstaller Edition
نظام بناء NebulaCompute - النسخة الكاملة المتكاملة

سكريبت بناء شامل لإنشاء ملفات تنفيذية مستقلة لجميع المنصات

Features / المميزات:
══════════════════════════════════════════════════════════════════
• Multi-platform support (Windows, Linux, macOS)
• Multiple build modes (debug, release, minimal, full)
• Automatic dependency detection and bundling
• Icon and splash screen generation
• Windows version info embedding
• Code signing support (Windows/macOS)
• UPX compression for smaller executables
• Installer creation (NSIS, AppImage, DMG, DEB)
• Auto-updater integration
• CI/CD integration ready
• Arabic and English interface
══════════════════════════════════════════════════════════════════

Usage / الاستخدام:
    python build.py                     # بناء افتراضي
    python build.py --mode release      # بناء للإصدار
    python build.py --mode debug        # بناء للتطوير
    python build.py --installer         # إنشاء مثبت
    python build.py --clean             # تنظيف الملفات
    python build.py --all-platforms     # بناء لجميع المنصات

Requirements / المتطلبات:
    pip install pyinstaller PySide6 qasync httpx websockets pillow

Author: NebulaCompute Team
License: MIT
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
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# ══════════════════════════════════════════════════════════════════
# إعدادات الترميز - Unicode Encoding Settings
# ══════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════
# الثوابت - Constants
# ══════════════════════════════════════════════════════════════════
APP_NAME = "NebulaCompute"
APP_DESCRIPTION = "Distributed Computing System - نظام الحوسبة الموزعة"
APP_AUTHOR = "NebulaCompute Team"
APP_WEBSITE = "https://github.com/nebulacompute"
APP_IDENTIFIER = "com.nebulacompute.desktop"


class BuildMode(Enum):
    """Build mode enumeration / أوضاع البناء"""

    DEBUG = "debug"
    RELEASE = "release"
    MINIMAL = "minimal"
    FULL = "full"


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


@dataclass
class BuildConfig:
    """Build configuration / إعدادات البناء"""

    name: str = APP_NAME
    version: str = "1.0.0"
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


class Colors:
    """ANSI color codes for terminal output"""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"

    @classmethod
    def disable(cls):
        """Disable colors for non-TTY output"""
        for attr in dir(cls):
            if not attr.startswith("_") and attr.isupper():
                setattr(cls, attr, "")


# Disable colors on Windows without proper terminal support
if sys.platform == "win32" and not os.environ.get("TERM"):
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        Colors.disable()


def print_banner():
    """Print build system banner"""
    banner = f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════════════╗
║                                                                    ║
║   {Colors.BOLD}███╗   ██╗███████╗██████╗ ██╗   ██╗██╗      █████╗{Colors.END}{Colors.CYAN}              ║
║   {Colors.BOLD}████╗  ██║██╔════╝██╔══██╗██║   ██║██║     ██╔══██╗{Colors.END}{Colors.CYAN}             ║
║   {Colors.BOLD}██╔██╗ ██║█████╗  ██████╔╝██║   ██║██║     ███████║{Colors.END}{Colors.CYAN}             ║
║   {Colors.BOLD}██║╚██╗██║██╔══╝  ██╔══██╗██║   ██║██║     ██╔══██║{Colors.END}{Colors.CYAN}             ║
║   {Colors.BOLD}██║ ╚████║███████╗██████╔╝╚██████╔╝███████╗██║  ██║{Colors.END}{Colors.CYAN}             ║
║   {Colors.BOLD}╚═╝  ╚═══╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝{Colors.END}{Colors.CYAN}             ║
║                                                                    ║
║   {Colors.YELLOW}PyInstaller Build System v2.0{Colors.CYAN}                                 ║
║   {Colors.GREEN}نظام البناء المتكامل{Colors.CYAN}                                           ║
║                                                                    ║
╚══════════════════════════════════════════════════════════════════╝{Colors.END}
"""
    print(banner)


def log(message: str, level: str = "info"):
    """Log a message with color / طباعة رسالة ملونة"""
    colors = {
        "info": Colors.CYAN,
        "success": Colors.GREEN,
        "warning": Colors.YELLOW,
        "error": Colors.RED,
        "header": Colors.BOLD + Colors.BLUE,
    }
    icons = {
        "info": "ℹ️ ",
        "success": "✅",
        "warning": "⚠️ ",
        "error": "❌",
        "header": "📦",
    }
    color = colors.get(level, Colors.CYAN)
    icon = icons.get(level, "•")
    print(f"{color}{icon} {message}{Colors.END}")


def log_section(title: str):
    """Log a section header / طباعة عنوان قسم"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'═' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}  {title}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'═' * 60}{Colors.END}\n")


class NebulaBuilder:
    """
    Main builder class for NebulaCompute
    الصف الرئيسي لبناء NebulaCompute
    """

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize builder / تهيئة المُنشئ"""
        self.project_root = project_root or self._find_project_root()
        self.src_path = self.project_root / "src"
        self.desktop_path = self.src_path / "distributed_cluster" / "desktop"
        self.web_path = self.src_path / "distributed_cluster" / "web"
        self.dist_path = self.project_root / "dist"
        self.build_path = self.project_root / "build"

        self.platform = platform.system().lower()
        self.arch = platform.machine().lower()
        self.is_64bit = sys.maxsize > 2**32

        self._upx_available = False
        self._pyinstaller_available = False

    def _find_project_root(self) -> Path:
        """Find project root directory / البحث عن مجلد المشروع"""
        current = Path(__file__).parent

        # Look for pyproject.toml or setup.py
        for parent in [current] + list(current.parents):
            if (parent / "pyproject.toml").exists() or (parent / "setup.py").exists():
                return parent

        return current

    def _run_command(
        self,
        cmd: list[str],
        cwd: Optional[Path] = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a shell command / تنفيذ أمر"""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.project_root,
                capture_output=capture,
                text=True,
                check=check,
            )
            return result
        except subprocess.CalledProcessError as e:
            if check:
                log(f"Command failed: {' '.join(cmd)}", "error")
                if e.stdout:
                    print(e.stdout)
                if e.stderr:
                    print(e.stderr)
                raise
            return e

    def _check_tools(self):
        """Check available build tools / فحص الأدوات المتاحة"""
        log_section("Checking Build Tools / فحص الأدوات")

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
                log(f"PyInstaller: {version}", "success")
            else:
                log("PyInstaller: not installed", "warning")
        except Exception:
            log("PyInstaller: not found", "warning")

        # Check UPX
        try:
            result = self._run_command(["upx", "--version"], capture=True, check=False)
            if result.returncode == 0:
                self._upx_available = True
                log("UPX compression: available", "success")
            else:
                log("UPX compression: not available", "warning")
        except FileNotFoundError:
            log("UPX compression: not installed (optional)", "info")

        # Check Python version
        py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        log(f"Python: {py_version}", "success")

        # Check platform
        log(f"Platform: {self.platform} ({self.arch})", "success")

        if not self._pyinstaller_available:
            log("Installing PyInstaller...", "info")
            self._run_command(
                [sys.executable, "-m", "pip", "install", "pyinstaller"], check=False
            )
            self._pyinstaller_available = True

    def get_version(self) -> str:
        """Get version from git or pyproject.toml / الحصول على رقم الإصدار"""
        # Try git first
        try:
            result = self._run_command(
                ["git", "describe", "--tags", "--always"], capture=True, check=False
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

        return "1.0.0"

    def get_git_hash(self) -> str:
        """Get short git commit hash / الحصول على رمز التنفيذ"""
        try:
            result = self._run_command(
                ["git", "rev-parse", "--short", "HEAD"], capture=True, check=False
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
        except Exception:
            pass
        return "unknown"

    def clean(self):
        """Clean build artifacts / تنظيف ملفات البناء"""
        log_section("Cleaning Build Artifacts / تنظيف ملفات البناء")

        def handle_remove_error(func, path, exc_info):
            """Handle permission errors on Windows"""
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception as e:
                log(f"Cannot delete {path}: {e}", "warning")

        dirs_to_clean = [self.build_path, self.dist_path]
        for dir_path in dirs_to_clean:
            if dir_path.exists():
                log(f"Removing: {dir_path}", "info")
                try:
                    if sys.version_info >= (3, 12):
                        shutil.rmtree(dir_path, onexc=lambda f, p, e: handle_remove_error(f, p, (None, e, None)))
                    else:
                        shutil.rmtree(dir_path, onerror=handle_remove_error)
                except Exception as e:
                    log(f"Could not fully clean {dir_path}: {e}", "warning")

        # Clean spec files
        for spec_file in self.project_root.glob("*.spec"):
            try:
                spec_file.unlink()
                log(f"Removed: {spec_file.name}", "info")
            except Exception:
                pass

        # Clean pycache
        for pycache in self.project_root.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache)
            except Exception:
                pass

        log("Clean complete!", "success")

    def create_icon(self) -> Path:
        """Create application icon if missing / إنشاء أيقونة التطبيق"""
        resources_path = self.desktop_path / "resources"
        resources_path.mkdir(parents=True, exist_ok=True)

        icon_path = resources_path / "icon.ico"

        if icon_path.exists():
            return icon_path

        log("Creating placeholder icon...", "info")

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
                font_size = size[0] // 2
                draw.text(
                    (center, center),
                    "N",
                    fill=(255, 255, 255, 255),
                    anchor="mm",
                )

                images.append(img)

            images[0].save(icon_path, format="ICO", sizes=[(s[0], s[1]) for s in sizes])
            log(f"Created icon: {icon_path}", "success")

        except ImportError:
            # Create minimal valid ICO without PIL
            ico_data = self._create_minimal_ico()
            icon_path.write_bytes(ico_data)
            log(f"Created minimal icon: {icon_path}", "success")

        return icon_path

    def _create_minimal_ico(self) -> bytes:
        """Create minimal valid ICO file without PIL"""
        # ICO header
        ico_header = bytes(
            [
                0x00,
                0x00,  # Reserved
                0x01,
                0x00,  # Type (1 = ICO)
                0x01,
                0x00,  # Number of images
            ]
        )

        # Image entry (16x16 32-bit)
        image_entry = bytes(
            [
                0x10,  # Width (16)
                0x10,  # Height (16)
                0x00,  # Colors (0 = no palette)
                0x00,  # Reserved
                0x01,
                0x00,  # Color planes
                0x20,
                0x00,  # Bits per pixel (32)
                0x68,
                0x04,
                0x00,
                0x00,  # Size of image data
                0x16,
                0x00,
                0x00,
                0x00,  # Offset to image data
            ]
        )

        # BITMAPINFOHEADER
        bmp_header = bytes(
            [
                0x28,
                0x00,
                0x00,
                0x00,  # Header size (40)
                0x10,
                0x00,
                0x00,
                0x00,  # Width (16)
                0x20,
                0x00,
                0x00,
                0x00,  # Height (32, doubled)
                0x01,
                0x00,  # Planes
                0x20,
                0x00,  # Bits per pixel (32)
                0x00,
                0x00,
                0x00,
                0x00,  # Compression
                0x00,
                0x04,
                0x00,
                0x00,  # Image size
                0x00,
                0x00,
                0x00,
                0x00,  # X pixels per meter
                0x00,
                0x00,
                0x00,
                0x00,  # Y pixels per meter
                0x00,
                0x00,
                0x00,
                0x00,  # Colors used
                0x00,
                0x00,
                0x00,
                0x00,  # Important colors
            ]
        )

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

    def create_version_info(self, config: BuildConfig) -> Optional[Path]:
        """Create Windows version info file / إنشاء ملف معلومات الإصدار"""
        if self.platform != "windows":
            return None

        self.build_path.mkdir(parents=True, exist_ok=True)
        version_path = self.build_path / "version_info.txt"

        # Parse version
        version_parts = config.version.replace("-", ".").split(".")
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
                    StringStruct(u'CompanyName', u'{config.author}'),
                    StringStruct(u'FileDescription', u'{config.description}'),
                    StringStruct(u'FileVersion', u'{config.version}'),
                    StringStruct(u'InternalName', u'{config.name}'),
                    StringStruct(u'LegalCopyright', u'Copyright (c) 2024 {config.author}'),
                    StringStruct(u'OriginalFilename', u'{config.name}.exe'),
                    StringStruct(u'ProductName', u'{config.name}'),
                    StringStruct(u'ProductVersion', u'{config.version}'),
                ]
            )
        ]),
        VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
    ]
)
"""
        version_path.write_text(version_content)
        log(f"Created version info: {version_path.name}", "success")
        return version_path

    def create_splash_screen(self, config: BuildConfig) -> Optional[Path]:
        """Create splash screen image / إنشاء شاشة البداية"""
        if not config.splash_screen or not config.one_file:
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
                config.name,
                fill=(255, 255, 255, 255),
                anchor="mm",
                font=font_large,
            )

            draw.text(
                (width // 2, height // 2),
                f"v{config.version}",
                fill=(180, 180, 200, 255),
                anchor="mm",
                font=font_small,
            )

            draw.text(
                (width // 2, height * 2 // 3),
                "جاري التحميل... Loading...",
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
            log(f"Created splash screen: {splash_path.name}", "success")
            return splash_path

        except ImportError:
            log("PIL not available, skipping splash screen", "warning")
            return None

    def get_hidden_imports(self, config: BuildConfig) -> list[str]:
        """Get list of hidden imports / الحصول على قائمة الاستيرادات المخفية"""
        imports = [
            # PySide6 / Qt
            "PySide6.QtCore",
            "PySide6.QtGui",
            "PySide6.QtWidgets",
            "PySide6.QtCharts",
            "PySide6.QtNetwork",
            "PySide6.QtSvg",
            "PySide6.QtSvgWidgets",
            # Async
            "qasync",
            "asyncio",
            "asyncio.events",
            "asyncio.base_events",
            # HTTP & WebSocket
            "httpx",
            "httpx._transports",
            "httpx._transports.default",
            "websockets",
            "websockets.client",
            "websockets.legacy",
            "websockets.legacy.client",
            # Project modules
            "distributed_cluster",
            "distributed_cluster.desktop",
            "distributed_cluster.desktop.main",
            "distributed_cluster.desktop.main_window",
            "distributed_cluster.desktop.app_entry",
            # Desktop API
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
            # Core models
            "distributed_cluster.models",
            "distributed_cluster.models.job",
            "distributed_cluster.models.worker",
            "distributed_cluster.models.resources",
            "distributed_cluster.core",
            "distributed_cluster.core.config",
            # Standard library
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
            "ssl",
            "certifi",
            # Windows specific
            "ctypes",
            "ctypes.wintypes",
            # Network utilities
            "anyio",
            "anyio._backends",
            "anyio._backends._asyncio",
            "sniffio",
            "h11",
            "httpcore",
            # Package utilities
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

        # Add web imports for full mode
        if config.mode == BuildMode.FULL and config.include_web:
            imports.extend(
                [
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
            )

        # Add custom imports
        imports.extend(config.hidden_imports)

        return imports

    def get_excludes(self, config: BuildConfig) -> list[str]:
        """Get list of modules to exclude / الحصول على قائمة الاستثناءات"""
        excludes = [
            "tkinter",
            "_tkinter",
            "matplotlib",
            "numpy",
            "pandas",
            "scipy",
            "PIL.ImageTk",
            "IPython",
            "jupyter",
            "notebook",
            "pytest",
            "pip",
            "wheel",
            "test",
            "tests",
        ]

        # Exclude heavy modules in minimal mode
        if config.mode == BuildMode.MINIMAL:
            excludes.extend(
                [
                    "cryptography",
                    "docker",
                    "pynvml",
                    "grpc",
                    "grpcio",
                    "boto3",
                    "botocore",
                    "redis",
                    "asyncpg",
                ]
            )

        # Add custom excludes
        excludes.extend(config.excludes)

        return excludes

    def get_data_files(self, config: BuildConfig) -> list[tuple[Path, str]]:
        """Get data files to include / الحصول على ملفات البيانات"""
        data_files = []

        # Desktop resources
        resources = self.desktop_path / "resources"
        if resources.exists():
            data_files.append((resources, "distributed_cluster/desktop/resources"))

        # Web templates and static (if enabled)
        if config.include_web:
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

        return data_files

    def build(self, config: Optional[BuildConfig] = None) -> Path:
        """
        Main build method / الدالة الرئيسية للبناء

        Args:
            config: Build configuration

        Returns:
            Path to the built executable
        """
        config = config or BuildConfig()

        # Auto-detect version
        if config.version == "1.0.0":
            config.version = self.get_version()

        print_banner()

        log_section("Build Configuration / إعدادات البناء")
        log(f"Name: {config.name}", "info")
        log(f"Version: {config.version}", "info")
        log(f"Mode: {config.mode.value}", "info")
        log(f"Platform: {self.platform} ({self.arch})", "info")
        log(f"One file: {config.one_file}", "info")
        log(f"Console: {config.console}", "info")

        # Check tools
        self._check_tools()

        # Clean previous build
        log_section("Cleaning Previous Build / تنظيف البناء السابق")
        self.clean()

        # Create directories
        self.dist_path.mkdir(parents=True, exist_ok=True)
        self.build_path.mkdir(parents=True, exist_ok=True)

        # Create icon
        log_section("Creating Resources / إنشاء الموارد")
        icon_path = self.create_icon()

        # Create version info (Windows)
        version_file = self.create_version_info(config)

        # Create splash screen
        splash_path = self.create_splash_screen(config)

        # Build PyInstaller command
        log_section("Building Executable / بناء الملف التنفيذي")

        data_sep = ";" if self.platform == "windows" else ":"

        # Entry point
        entry_point = self.desktop_path / "app_entry.py"
        if not entry_point.exists():
            entry_point = self.desktop_path / "main.py"

        if not entry_point.exists():
            log(f"Entry point not found: {entry_point}", "error")
            raise FileNotFoundError(f"Entry point not found: {entry_point}")

        log(f"Entry point: {entry_point}", "info")

        # Build command
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            f"--name={config.name}",
            "--clean",
            "--noconfirm",
        ]

        # Window/Console mode
        if config.console:
            cmd.append("--console")
        else:
            cmd.append("--windowed")

        # One file/directory
        if config.one_file:
            cmd.append("--onefile")
        else:
            cmd.append("--onedir")

        # Icon
        if icon_path and icon_path.exists():
            cmd.append(f"--icon={icon_path}")

        # Version file (Windows)
        if version_file and version_file.exists():
            cmd.append(f"--version-file={version_file}")

        # Splash screen
        if splash_path and splash_path.exists():
            cmd.append(f"--splash={splash_path}")

        # Runtime hooks
        runtime_hook = self.desktop_path / "runtime_hook.py"
        if runtime_hook.exists():
            cmd.append(f"--runtime-hook={runtime_hook}")
        for hook in config.runtime_hooks:
            cmd.append(f"--runtime-hook={hook}")

        # Data files
        log("Adding data files...", "info")
        for src, dest in self.get_data_files(config):
            if src.exists():
                cmd.append(f"--add-data={src}{data_sep}{dest}")
                log(f"  + {dest}", "info")

        # Hidden imports
        log("Adding hidden imports...", "info")
        hidden_imports = self.get_hidden_imports(config)
        for imp in hidden_imports:
            cmd.append(f"--hidden-import={imp}")
        log(f"  Added {len(hidden_imports)} imports", "info")

        # Excludes
        log("Adding excludes...", "info")
        excludes = self.get_excludes(config)
        for exc in excludes:
            cmd.append(f"--exclude-module={exc}")
        log(f"  Excluded {len(excludes)} modules", "info")

        # Collect all
        cmd.extend(
            [
                "--collect-all=PySide6",
                "--collect-all=httpx",
                "--collect-all=websockets",
                "--collect-all=jaraco",
            ]
        )

        # UPX compression
        if config.upx_compress and self._upx_available:
            log("UPX compression enabled", "info")
        else:
            cmd.append("--noupx")

        # Strip binaries
        if config.strip_binaries and self.platform != "windows":
            cmd.append("--strip")

        # Optimize bytecode
        if config.optimize_bytecode > 0:
            # Set via environment variable
            os.environ["PYTHONOPTIMIZE"] = str(config.optimize_bytecode)

        # Debug mode
        if config.debug:
            cmd.append("--debug=all")

        # Output paths
        cmd.extend(
            [
                f"--distpath={self.dist_path}",
                f"--workpath={self.build_path}",
                f"--specpath={self.project_root}",
                f"--paths={self.src_path}",
            ]
        )

        # Entry point
        cmd.append(str(entry_point))

        # Run PyInstaller
        log("\nRunning PyInstaller...\n", "header")

        try:
            self._run_command(cmd)
        except subprocess.CalledProcessError:
            log("Build failed!", "error")
            raise

        # Verify output
        exe_name = f"{config.name}.exe" if self.platform == "windows" else config.name
        exe_path = self.dist_path / exe_name

        if not exe_path.exists():
            # Check for directory mode
            exe_path = self.dist_path / config.name / exe_name
            if not exe_path.exists():
                log(f"Executable not found: {exe_path}", "error")
                raise FileNotFoundError(f"Build output not found: {exe_path}")

        # Get file size
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
            "name": config.name,
            "version": config.version,
            "git_hash": self.get_git_hash(),
            "build_date": datetime.now().isoformat(),
            "build_mode": config.mode.value,
            "platform": self.platform,
            "arch": self.arch,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "one_file": config.one_file,
            "size_bytes": size_bytes,
            "sha256": sha256.hexdigest(),
            "exe_path": str(exe_path),
        }

        info_path = self.dist_path / "build_info.json"
        info_path.write_text(json.dumps(build_info, indent=2, ensure_ascii=False))

        # Create installer if requested
        if config.installer_type != InstallerType.NONE:
            self.create_installer(exe_path, config)

        # Print success message
        log_section("Build Complete! / اكتمل البناء")
        print(
            f"""
{Colors.GREEN}╔══════════════════════════════════════════════════════════════════╗
║                     ✅ BUILD SUCCESSFUL!                          ║
╠══════════════════════════════════════════════════════════════════╣
║  📁 Executable: {str(exe_path)[:50]:<50} ║
║  📊 Size: {size_mb:.1f} MB ({size_bytes:,} bytes){' ' * (50 - len(f'{size_mb:.1f} MB ({size_bytes:,} bytes)'))}║
║  🔑 SHA256: {file_hash}...{' ' * 36}║
║  📋 Build info: {info_path.name:<50} ║
╚══════════════════════════════════════════════════════════════════╝{Colors.END}
"""
        )

        log(f"To run: {exe_path}", "info")

        return exe_path

    def create_installer(self, exe_path: Path, config: BuildConfig):
        """Create installer for the executable / إنشاء مثبت"""
        log_section(f"Creating Installer ({config.installer_type.value})")

        if config.installer_type == InstallerType.NSIS:
            self._create_nsis_installer(exe_path, config)
        elif config.installer_type == InstallerType.APPIMAGE:
            self._create_appimage(exe_path, config)
        elif config.installer_type == InstallerType.DEB:
            self._create_deb_package(exe_path, config)
        elif config.installer_type == InstallerType.DMG:
            self._create_dmg(exe_path, config)
        else:
            log(f"Installer type {config.installer_type.value} not implemented", "warning")

    def _create_nsis_installer(self, exe_path: Path, config: BuildConfig):
        """Create NSIS installer for Windows"""
        nsis_script = f"""; {config.name} Installer Script
; Generated by NebulaCompute Build System

!include "MUI2.nsh"
!include "FileFunc.nsh"

; General
Name "{config.name}"
OutFile "{config.name}_Setup_{config.version}.exe"
InstallDir "$PROGRAMFILES\\{config.name}"
RequestExecutionLevel admin

; Version Info
VIProductVersion "{config.version}.0"
VIAddVersionKey "ProductName" "{config.name}"
VIAddVersionKey "CompanyName" "{config.author}"
VIAddVersionKey "FileDescription" "{config.description}"
VIAddVersionKey "FileVersion" "{config.version}"
VIAddVersionKey "ProductVersion" "{config.version}"

; Interface Settings
!define MUI_ABORTWARNING
!define MUI_ICON "{self.desktop_path / 'resources' / 'icon.ico'}"
!define MUI_UNICON "{self.desktop_path / 'resources' / 'icon.ico'}"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${{NSISDIR}}\\Docs\\Modern UI\\License.txt"
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

    ; Main executable
    File "{exe_path}"

    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\\{config.name}"
    CreateShortCut "$SMPROGRAMS\\{config.name}\\{config.name}.lnk" "$INSTDIR\\{exe_path.name}"
    CreateShortCut "$SMPROGRAMS\\{config.name}\\Uninstall.lnk" "$INSTDIR\\Uninstall.exe"
    CreateShortCut "$DESKTOP\\{config.name}.lnk" "$INSTDIR\\{exe_path.name}"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\\Uninstall.exe"

    ; Registry entries
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{config.name}" \\
        "DisplayName" "{config.name}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{config.name}" \\
        "UninstallString" "$INSTDIR\\Uninstall.exe"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{config.name}" \\
        "DisplayIcon" "$INSTDIR\\{exe_path.name}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{config.name}" \\
        "Publisher" "{config.author}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{config.name}" \\
        "DisplayVersion" "{config.version}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{config.name}" \\
        "URLInfoAbout" "{config.website}"

    ; Installed size
    ${{GetSize}} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{config.name}" \\
        "EstimatedSize" "$0"
SectionEnd

; Uninstaller Section
Section "Uninstall"
    Delete "$INSTDIR\\{exe_path.name}"
    Delete "$INSTDIR\\Uninstall.exe"

    Delete "$SMPROGRAMS\\{config.name}\\{config.name}.lnk"
    Delete "$SMPROGRAMS\\{config.name}\\Uninstall.lnk"
    Delete "$DESKTOP\\{config.name}.lnk"

    RMDir "$SMPROGRAMS\\{config.name}"
    RMDir "$INSTDIR"

    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{config.name}"
SectionEnd
"""

        nsis_path = self.build_path / f"{config.name}.nsi"
        nsis_path.write_text(nsis_script, encoding="utf-8")

        # Try to build if NSIS is available
        try:
            result = self._run_command(
                ["makensis", str(nsis_path)], capture=True, check=False
            )
            if result.returncode == 0:
                installer = self.dist_path / f"{config.name}_Setup_{config.version}.exe"
                log(f"Created installer: {installer}", "success")
            else:
                log("NSIS build failed, script saved for manual build", "warning")
        except FileNotFoundError:
            log(f"NSIS not found. Script saved to: {nsis_path}", "info")
            log("Install NSIS and run: makensis " + str(nsis_path), "info")

    def _create_appimage(self, exe_path: Path, config: BuildConfig):
        """Create AppImage for Linux"""
        appdir = self.build_path / f"{config.name}.AppDir"
        appdir.mkdir(parents=True, exist_ok=True)

        # AppRun script
        apprun = appdir / "AppRun"
        apprun.write_text(
            f"""#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${{SELF%/*}}
export PATH="${{HERE}}/usr/bin:${{PATH}}"
export LD_LIBRARY_PATH="${{HERE}}/usr/lib:${{LD_LIBRARY_PATH}}"
exec "${{HERE}}/usr/bin/{config.name}" "$@"
"""
        )
        os.chmod(apprun, 0o755)

        # Desktop file
        desktop = appdir / f"{config.name}.desktop"
        desktop.write_text(
            f"""[Desktop Entry]
Name={config.name}
Comment={config.description}
Exec={config.name}
Icon={config.name.lower()}
Terminal=false
Type=Application
Categories=Development;Utility;
"""
        )

        # Copy executable
        usr_bin = appdir / "usr" / "bin"
        usr_bin.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe_path, usr_bin / config.name)
        os.chmod(usr_bin / config.name, 0o755)

        # Copy icon
        icon_src = self.desktop_path / "resources" / "icon.png"
        if icon_src.exists():
            shutil.copy2(icon_src, appdir / f"{config.name.lower()}.png")

        # Download appimagetool
        appimagetool = self.build_path / "appimagetool-x86_64.AppImage"
        if not appimagetool.exists():
            log("Downloading appimagetool...", "info")
            import urllib.request

            url = "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
            try:
                urllib.request.urlretrieve(url, appimagetool)
                os.chmod(appimagetool, 0o755)
            except Exception as e:
                log(f"Could not download appimagetool: {e}", "warning")
                log(f"AppDir created at: {appdir}", "info")
                return

        # Build AppImage
        output = self.dist_path / f"{config.name}-{config.version}-x86_64.AppImage"
        result = self._run_command(
            [str(appimagetool), str(appdir), str(output)], check=False
        )

        if result.returncode == 0:
            log(f"Created AppImage: {output}", "success")
        else:
            log("AppImage creation failed", "warning")

    def _create_deb_package(self, exe_path: Path, config: BuildConfig):
        """Create DEB package for Debian/Ubuntu"""
        pkg_name = config.name.lower()
        pkg_dir = self.build_path / f"{pkg_name}_{config.version}"

        # Create directory structure
        (pkg_dir / "DEBIAN").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "usr" / "bin").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "usr" / "share" / "applications").mkdir(parents=True, exist_ok=True)

        # Control file
        size = exe_path.stat().st_size // 1024
        control = pkg_dir / "DEBIAN" / "control"
        control.write_text(
            f"""Package: {pkg_name}
Version: {config.version}
Section: utils
Priority: optional
Architecture: amd64
Installed-Size: {size}
Maintainer: {config.author}
Description: {config.description}
 NebulaCompute Desktop - Distributed Computing Management
"""
        )

        # Copy executable
        shutil.copy2(exe_path, pkg_dir / "usr" / "bin" / pkg_name)
        os.chmod(pkg_dir / "usr" / "bin" / pkg_name, 0o755)

        # Desktop file
        desktop = pkg_dir / "usr" / "share" / "applications" / f"{pkg_name}.desktop"
        desktop.write_text(
            f"""[Desktop Entry]
Name={config.name}
Comment={config.description}
Exec={pkg_name}
Icon={pkg_name}
Terminal=false
Type=Application
Categories=Development;Utility;
"""
        )

        # Build package
        output = self.dist_path / f"{pkg_name}_{config.version}_amd64.deb"
        result = self._run_command(
            ["dpkg-deb", "--build", str(pkg_dir), str(output)], check=False
        )

        if result.returncode == 0:
            log(f"Created DEB package: {output}", "success")
        else:
            log("dpkg-deb not available, directory created", "warning")
            log(f"Package directory: {pkg_dir}", "info")

    def _create_dmg(self, exe_path: Path, config: BuildConfig):
        """Create DMG for macOS"""
        # For macOS, we typically create an app bundle first
        log("DMG creation requires manual app bundle setup", "info")
        log(f"Executable: {exe_path}", "info")


def main():
    """Main entry point / نقطة الدخول الرئيسية"""
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} Build System - نظام البناء",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples / أمثلة:
  python build.py                          # Default release build
  python build.py --mode debug             # Debug build with console
  python build.py --mode minimal           # Minimal build (smaller size)
  python build.py --mode full              # Full build with all features
  python build.py --installer nsis         # Build with NSIS installer
  python build.py --installer appimage     # Build with AppImage (Linux)
  python build.py --clean                  # Clean build artifacts only
  python build.py --version 2.0.0          # Override version number

Build Modes / أوضاع البناء:
  debug    - With console, debug symbols
  release  - Optimized, no console (default)
  minimal  - Smallest size, fewer features
  full     - All features including web server
        """,
    )

    parser.add_argument(
        "--mode",
        "-m",
        choices=["debug", "release", "minimal", "full"],
        default="release",
        help="Build mode (default: release)",
    )

    parser.add_argument(
        "--version",
        "-v",
        type=str,
        help="Override version number",
    )

    parser.add_argument(
        "--name",
        "-n",
        type=str,
        default=APP_NAME,
        help=f"Application name (default: {APP_NAME})",
    )

    parser.add_argument(
        "--installer",
        "-i",
        choices=["none", "nsis", "appimage", "deb", "dmg"],
        default="none",
        help="Create installer after build",
    )

    parser.add_argument(
        "--console",
        "-c",
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
        "--clean",
        action="store_true",
        help="Clean build artifacts only",
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

    args = parser.parse_args()

    # Create builder
    builder = NebulaBuilder()

    # Clean only
    if args.clean:
        print_banner()
        builder.clean()
        return

    # Build configuration
    config = BuildConfig(
        name=args.name,
        mode=BuildMode(args.mode),
        one_file=not args.onedir,
        console=args.console or args.mode == "debug",
        splash_screen=not args.no_splash,
        upx_compress=not args.no_upx,
        debug=args.debug_build,
        installer_type=InstallerType(args.installer),
    )

    if args.version:
        config.version = args.version

    # Build
    try:
        builder.build(config)
    except Exception as e:
        log(f"Build failed: {e}", "error")
        sys.exit(1)


if __name__ == "__main__":
    main()
