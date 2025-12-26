#!/usr/bin/env python3
"""
NebulaCompute PyInstaller Build Script
سكربت بناء NebulaCompute باستخدام PyInstaller

A comprehensive cross-platform build script for creating
standalone executables from the NebulaCompute desktop application.

Usage:
    python build.py                    # Default build (one-file, windowed)
    python build.py --mode fast        # Quick build with minimal optimization
    python build.py --mode optimized   # Optimized build
    python build.py --mode debug       # Debug build with console
    python build.py --onedir           # Create one-directory bundle
    python build.py --console          # Enable console window
    python build.py --clean            # Clean build artifacts
    python build.py --install-deps     # Install build dependencies
    python build.py --info             # Show build configuration info

Author: NebulaCompute Team
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


# =============================================================================
# Configuration
# =============================================================================

class BuildMode(Enum):
    """Build optimization modes"""
    FAST = "fast"           # Quick build, minimal optimization
    DEFAULT = "default"     # Balanced build
    OPTIMIZED = "optimized" # Maximum optimization
    DEBUG = "debug"         # Debug build with console


class ColorOutput:
    """Cross-platform colored terminal output"""
    # ANSI color codes
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

    @classmethod
    def init(cls):
        """Initialize colors for Windows"""
        if sys.platform == 'win32':
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                # Disable colors if not supported
                cls.HEADER = cls.BLUE = cls.CYAN = cls.GREEN = ''
                cls.YELLOW = cls.RED = cls.BOLD = cls.UNDERLINE = cls.END = ''

    @classmethod
    def print_header(cls, msg: str):
        print(f"\n{cls.BOLD}{cls.CYAN}{'═' * 60}{cls.END}")
        print(f"{cls.BOLD}{cls.CYAN}  {msg}{cls.END}")
        print(f"{cls.BOLD}{cls.CYAN}{'═' * 60}{cls.END}\n")

    @classmethod
    def print_step(cls, step: int, total: int, msg: str):
        print(f"{cls.YELLOW}[{step}/{total}]{cls.END} {msg}")

    @classmethod
    def print_success(cls, msg: str):
        print(f"{cls.GREEN}✓ {msg}{cls.END}")

    @classmethod
    def print_error(cls, msg: str):
        print(f"{cls.RED}✗ {msg}{cls.END}")

    @classmethod
    def print_warning(cls, msg: str):
        print(f"{cls.YELLOW}⚠ {msg}{cls.END}")

    @classmethod
    def print_info(cls, msg: str):
        print(f"{cls.BLUE}ℹ {msg}{cls.END}")


@dataclass
class BuildConfig:
    """Build configuration settings"""
    # Application info
    name: str = "NebulaCompute"
    version: str = "1.0.0"
    description: str = "NebulaCompute Desktop - Distributed Computing Management"
    author: str = "NebulaCompute Team"

    # Build settings
    mode: BuildMode = BuildMode.DEFAULT
    one_file: bool = True
    console: bool = False
    upx: bool = True
    strip: bool = False

    # Paths (will be set in __post_init__)
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
        self.project_root = Path(__file__).parent.resolve()
        self.src_path = self.project_root / "src"
        self.entry_point = self.src_path / "distributed_cluster" / "desktop" / "app_entry.py"
        self.resources_path = self.src_path / "distributed_cluster" / "desktop" / "resources"
        self.icon_path = self.resources_path / "icon.ico"
        self.output_dir = self.project_root / "dist"
        self.build_dir = self.project_root / "build"
        self.spec_file = self.project_root / f"{self.name}.spec"

        # Try to get version from git
        self.version = self._get_git_version()

    def _get_git_version(self) -> str:
        """Get version from git tags"""
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                capture_output=True, text=True, cwd=self.project_root
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return self.version


# =============================================================================
# Hidden Imports - Critical for PyInstaller
# =============================================================================

HIDDEN_IMPORTS = [
    # PySide6 Qt modules
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtCharts",
    "PySide6.QtNetwork",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",

    # Async Qt integration
    "qasync",

    # Async libraries
    "asyncio",
    "anyio",
    "anyio._backends",
    "anyio._backends._asyncio",
    "sniffio",

    # HTTP libraries
    "httpx",
    "httpx._transports",
    "httpx._transports.default",
    "httpcore",
    "h11",

    # WebSocket libraries
    "websockets",
    "websockets.client",
    "websockets.legacy",
    "websockets.legacy.client",

    # Distributed Cluster modules
    "distributed_cluster",
    "distributed_cluster.desktop",
    "distributed_cluster.desktop.main",
    "distributed_cluster.desktop.main_window",
    "distributed_cluster.desktop.api",
    "distributed_cluster.desktop.api.client",
    "distributed_cluster.desktop.views",
    "distributed_cluster.desktop.widgets",
    "distributed_cluster.desktop.resources",
    "distributed_cluster.models",
    "distributed_cluster.models.job",
    "distributed_cluster.models.worker",
    "distributed_cluster.models.resources",
    "distributed_cluster.core",
    "distributed_cluster.core.config",

    # Standard library modules
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

    # Packaging utilities
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

# Modules to exclude (reduce size)
EXCLUDES = [
    # Heavy UI libraries not needed
    "tkinter",
    "_tkinter",
    "tk",
    "tcl",

    # Heavy data science libraries
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PIL",
    "pillow",

    # Development tools
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "pip",
    "wheel",
    "setuptools",

    # Heavy crypto (use system SSL instead)
    "cryptography",
    "cryptography.hazmat",
    "cryptography.hazmat.backends",
    "cryptography.hazmat.backends.openssl",

    # Server-side libraries not needed in desktop
    "docker",
    "pynvml",
    "uvicorn",
    "fastapi",
    "starlette",
]

# Collect all data from these packages
COLLECT_ALL_PACKAGES = [
    "PySide6",
    "httpx",
    "websockets",
    "jaraco",
    "pkg_resources",
]


# =============================================================================
# Build Functions
# =============================================================================

def check_dependencies() -> bool:
    """Check if required dependencies are installed"""
    required = ["pyinstaller", "PySide6", "qasync"]
    missing = []

    for package in required:
        try:
            __import__(package.lower().replace("-", "_"))
        except ImportError:
            missing.append(package)

    if missing:
        ColorOutput.print_warning(f"Missing packages: {', '.join(missing)}")
        return False

    ColorOutput.print_success("All dependencies are installed")
    return True


def install_dependencies():
    """Install required build dependencies"""
    ColorOutput.print_step(1, 1, "Installing dependencies...")

    packages = [
        "pyinstaller>=6.0.0",
        "PySide6>=6.6.0",
        "qasync>=0.27.0",
        "httpx>=0.25.0",
        "websockets>=12.0",
        "aiofiles>=23.0.0",
        "aiosqlite>=0.19.0",
        "pydantic>=2.5.0",
    ]

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade"] + packages,
            check=True
        )
        ColorOutput.print_success("Dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        ColorOutput.print_error(f"Failed to install dependencies: {e}")
        return False


def clean_build(config: BuildConfig):
    """Clean build artifacts"""
    ColorOutput.print_step(1, 1, "Cleaning build artifacts...")

    dirs_to_clean = [config.build_dir, config.output_dir]
    files_to_clean = [config.spec_file]

    for d in dirs_to_clean:
        if d.exists():
            shutil.rmtree(d)
            ColorOutput.print_info(f"Removed: {d}")

    for f in files_to_clean:
        if f.exists():
            f.unlink()
            ColorOutput.print_info(f"Removed: {f}")

    # Clean __pycache__ directories
    for pycache in config.project_root.rglob("__pycache__"):
        shutil.rmtree(pycache)

    ColorOutput.print_success("Build artifacts cleaned!")


def generate_spec_file(config: BuildConfig) -> str:
    """Generate PyInstaller .spec file content"""

    # Prepare data files
    data_files = []

    # Add resources directory
    if config.resources_path.exists():
        data_files.append(
            f"(r'{config.resources_path}', 'distributed_cluster/desktop/resources')"
        )

    # Add web templates if they exist
    web_templates = config.src_path / "distributed_cluster" / "web" / "templates"
    if web_templates.exists():
        data_files.append(
            f"(r'{web_templates}', 'distributed_cluster/web/templates')"
        )

    # Add web static files if they exist
    web_static = config.src_path / "distributed_cluster" / "web" / "static"
    if web_static.exists():
        data_files.append(
            f"(r'{web_static}', 'distributed_cluster/web/static')"
        )

    # Add config directory if it exists
    config_dir = config.project_root / "config"
    if config_dir.exists():
        data_files.append(f"(r'{config_dir}', 'config')")

    # Generate collect_all calls
    collect_all_code = ""
    for package in COLLECT_ALL_PACKAGES:
        collect_all_code += f"""
tmp_ret = collect_all('{package}')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
"""

    # Determine optimization level
    optimize = 0
    if config.mode == BuildMode.OPTIMIZED:
        optimize = 2
    elif config.mode == BuildMode.DEFAULT:
        optimize = 1

    # Handle icon path
    icon_exists = config.icon_path.exists()
    icon_line = f"[r'{config.icon_path}']" if icon_exists else "[]"

    # Build EXE options based on one_file setting
    if config.one_file:
        exe_block = f"""
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='{config.name}',
    debug={config.mode == BuildMode.DEBUG},
    bootloader_ignore_signals=False,
    strip={config.strip},
    upx={config.upx},
    upx_exclude=[],
    runtime_tmpdir=None,
    console={config.console or config.mode == BuildMode.DEBUG},
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
    name='{config.name}',
    debug={config.mode == BuildMode.DEBUG},
    bootloader_ignore_signals=False,
    strip={config.strip},
    upx={config.upx},
    console={config.console or config.mode == BuildMode.DEBUG},
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
    strip={config.strip},
    upx={config.upx},
    upx_exclude=[],
    name='{config.name}',
)
"""

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
# Generated by NebulaCompute build.py
# نظام بناء NebulaCompute
#
# Build mode: {config.mode.value}
# Version: {config.version}

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

# Data files
datas = [{", ".join(data_files)}]

# Binary files
binaries = []

# Hidden imports
hiddenimports = {HIDDEN_IMPORTS}

# Collect all from packages
{collect_all_code}

# Analysis
a = Analysis(
    [r'{config.entry_point}'],
    pathex=[r'{config.src_path}'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={EXCLUDES},
    noarchive=False,
    optimize={optimize},
)

# Create PYZ archive
pyz = PYZ(a.pure)

# Create executable
{exe_block}
'''

    return spec_content


def run_pyinstaller(config: BuildConfig, spec_content: str) -> bool:
    """Run PyInstaller with the generated spec file"""

    # Write spec file
    with open(config.spec_file, 'w', encoding='utf-8') as f:
        f.write(spec_content)

    ColorOutput.print_info(f"Generated spec file: {config.spec_file}")

    # Build PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(config.spec_file),
        "--noconfirm",
        f"--distpath={config.output_dir}",
        f"--workpath={config.build_dir}",
    ]

    # Add log level based on mode
    if config.mode == BuildMode.DEBUG:
        cmd.append("--log-level=DEBUG")
    elif config.mode == BuildMode.FAST:
        cmd.append("--log-level=WARN")
    else:
        cmd.append("--log-level=INFO")

    ColorOutput.print_info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, cwd=config.project_root)
        return result.returncode == 0
    except Exception as e:
        ColorOutput.print_error(f"PyInstaller failed: {e}")
        return False


def verify_output(config: BuildConfig) -> bool:
    """Verify the build output exists"""
    if sys.platform == 'win32':
        exe_name = f"{config.name}.exe"
    else:
        exe_name = config.name

    if config.one_file:
        exe_path = config.output_dir / exe_name
    else:
        exe_path = config.output_dir / config.name / exe_name

    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        ColorOutput.print_success(f"Build successful!")
        ColorOutput.print_info(f"Output: {exe_path}")
        ColorOutput.print_info(f"Size: {size_mb:.2f} MB")
        return True
    else:
        ColorOutput.print_error(f"Build output not found: {exe_path}")
        return False


def show_build_info(config: BuildConfig):
    """Show build configuration information"""
    ColorOutput.print_header("Build Configuration Info")

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


def build(config: BuildConfig) -> bool:
    """Execute the full build process"""
    ColorOutput.print_header(f"NebulaCompute Build - {config.mode.value.upper()}")

    total_steps = 5

    # Step 1: Verify entry point
    ColorOutput.print_step(1, total_steps, "Verifying project structure...")
    if not config.entry_point.exists():
        ColorOutput.print_error(f"Entry point not found: {config.entry_point}")
        return False
    ColorOutput.print_success(f"Entry point found: {config.entry_point}")

    # Step 2: Check dependencies
    ColorOutput.print_step(2, total_steps, "Checking dependencies...")
    if not check_dependencies():
        ColorOutput.print_warning("Installing missing dependencies...")
        if not install_dependencies():
            return False

    # Step 3: Clean previous build (optional based on mode)
    if config.mode != BuildMode.FAST:
        ColorOutput.print_step(3, total_steps, "Cleaning previous build...")
        clean_build(config)
    else:
        ColorOutput.print_step(3, total_steps, "Skipping clean (fast mode)...")

    # Step 4: Generate spec and run PyInstaller
    ColorOutput.print_step(4, total_steps, "Running PyInstaller...")
    spec_content = generate_spec_file(config)

    if not run_pyinstaller(config, spec_content):
        ColorOutput.print_error("PyInstaller build failed!")
        return False

    # Step 5: Verify output
    ColorOutput.print_step(5, total_steps, "Verifying output...")
    if not verify_output(config):
        return False

    ColorOutput.print_header("BUILD COMPLETE!")
    return True


# =============================================================================
# CLI Interface
# =============================================================================

def create_parser() -> argparse.ArgumentParser:
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description="NebulaCompute PyInstaller Build Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build.py                    # Default build
  python build.py --mode fast        # Quick build
  python build.py --mode optimized   # Optimized build
  python build.py --mode debug       # Debug with console
  python build.py --onedir           # One-directory bundle
  python build.py --clean            # Clean build artifacts
  python build.py --install-deps     # Install dependencies
  python build.py --info             # Show build info

Build Modes:
  fast       - Quick build with minimal optimization
  default    - Balanced build (recommended)
  optimized  - Maximum optimization, slower build
  debug      - Debug build with console output
        """
    )

    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["fast", "default", "optimized", "debug"],
        default="default",
        help="Build mode (default: default)"
    )

    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Create one-directory bundle instead of one-file"
    )

    parser.add_argument(
        "--console",
        action="store_true",
        help="Enable console window"
    )

    parser.add_argument(
        "--no-upx",
        action="store_true",
        help="Disable UPX compression"
    )

    parser.add_argument(
        "--strip",
        action="store_true",
        help="Strip debug symbols (Linux/macOS)"
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build artifacts and exit"
    )

    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Install build dependencies and exit"
    )

    parser.add_argument(
        "--info",
        action="store_true",
        help="Show build configuration info and exit"
    )

    parser.add_argument(
        "--version", "-v",
        type=str,
        help="Override version string"
    )

    parser.add_argument(
        "--name", "-n",
        type=str,
        help="Override output name"
    )

    return parser


def main():
    """Main entry point"""
    ColorOutput.init()

    parser = create_parser()
    args = parser.parse_args()

    # Create config
    config = BuildConfig()

    # Apply CLI arguments
    if args.mode:
        config.mode = BuildMode(args.mode)
    if args.onedir:
        config.one_file = False
    if args.console:
        config.console = True
    if args.no_upx:
        config.upx = False
    if args.strip:
        config.strip = True
    if args.version:
        config.version = args.version
    if args.name:
        config.name = args.name
        config.spec_file = config.project_root / f"{args.name}.spec"

    # Handle special actions
    if args.info:
        show_build_info(config)
        return 0

    if args.install_deps:
        return 0 if install_dependencies() else 1

    if args.clean:
        clean_build(config)
        return 0

    # Run build
    success = build(config)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
