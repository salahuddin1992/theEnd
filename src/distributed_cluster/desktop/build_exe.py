"""
Build Script for NebulaCompute Desktop - Complete Edition
سكريبت بناء تطبيق سطح المكتب - النسخة الكاملة المتكاملة

Usage:
    python build_exe.py
    python build_exe.py --mode full     # تضمين كل شيء (افتراضي)
    python build_exe.py --mode minimal  # نسخة خفيفة

Requirements:
    pip install pyinstaller PySide6 qasync httpx websockets

This will create a standalone executable with everything included.
"""

import os
import shutil
import subprocess
import sys
import io

# Fix Unicode encoding issues on Windows
if sys.platform == 'win32':
        try:
                    # Try to set UTF-8 encoding for stdout/stderr
                    if hasattr(sys.stdout, 'reconfigure'):
                                    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                                    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
                    else:
                                    # Python < 3.7 fallback
                                    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
                                    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception:
                    pass  # Ignore if reconfiguration fails
from pathlib import Path



def get_project_root():
    """Get project root directory"""
    return Path(__file__).parent.parent.parent.parent


def get_src_path():
    """Get src directory"""
    return get_project_root() / "src"


def clean_build():
    """Clean previous build artifacts"""
    project_root = get_project_root()

    def handle_remove_error(func, path, exc_info):
        """Handle permission errors on Windows (for Python < 3.12)"""
        import stat
        if isinstance(exc_info[1], PermissionError):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception as e:
                print(f"⚠️ Cannot delete {path}: {e}")
        else:
            raise exc_info[1]

    def handle_remove_exc(func, path, exc):
        """Handle permission errors on Windows (for Python >= 3.12)"""
        import stat
        if isinstance(exc, PermissionError):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception as e:
                print(f"⚠️ Cannot delete {path}: {e}")
        else:
            raise exc

    dirs_to_clean = ["build", "dist"]
    for dir_name in dirs_to_clean:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print(f"[CLEAN] Cleaning {dir_path}...")
            try:
                # Python 3.12+ uses onexc, older versions use onerror
                if sys.version_info >= (3, 12):
                    shutil.rmtree(dir_path, onexc=handle_remove_exc)
                else:
                    shutil.rmtree(dir_path, onerror=handle_remove_error)
            except Exception as e:
                print(f"⚠️ Could not fully clean {dir_path}: {e}")
                print("   Tip: Close NebulaCompute.exe if it's running, then try again.")
                # Continue anyway - PyInstaller will overwrite

    # Clean .spec file
    spec_file = project_root / "NebulaCompute.spec"
    if spec_file.exists():
        try:
            spec_file.unlink()
        except PermissionError:
            print(f"⚠️ Cannot delete {spec_file} - file may be in use")


def create_icon_if_missing():
    """Create a placeholder icon if missing"""
    project_root = get_project_root()
    desktop_path = project_root / "src" / "distributed_cluster" / "desktop"
    resources_path = desktop_path / "resources"
    icon_path = resources_path / "icon.ico"

    # Ensure resources directory exists
    resources_path.mkdir(parents=True, exist_ok=True)

    if not icon_path.exists():
        print("📦 Creating placeholder icon...")
        # Create a simple 16x16 ICO file (minimal valid ICO)
        # This is a minimal valid ICO file with a 16x16 1-bit icon
        ico_data = bytes([
            0x00, 0x00,  # Reserved
            0x01, 0x00,  # Type (1 = ICO)
            0x01, 0x00,  # Number of images
            # Image entry
            0x10,        # Width (16)
            0x10,        # Height (16)
            0x00,        # Colors (0 = no palette)
            0x00,        # Reserved
            0x01, 0x00,  # Color planes
            0x20, 0x00,  # Bits per pixel (32)
            0x68, 0x04, 0x00, 0x00,  # Size of image data
            0x16, 0x00, 0x00, 0x00,  # Offset to image data
        ])
        # Add minimal BITMAPINFOHEADER and pixel data for 16x16 RGBA
        bmp_header = bytes([
            0x28, 0x00, 0x00, 0x00,  # Header size (40)
            0x10, 0x00, 0x00, 0x00,  # Width (16)
            0x20, 0x00, 0x00, 0x00,  # Height (32, doubled for AND mask)
            0x01, 0x00,              # Planes
            0x20, 0x00,              # Bits per pixel (32)
            0x00, 0x00, 0x00, 0x00,  # Compression
            0x00, 0x04, 0x00, 0x00,  # Image size
            0x00, 0x00, 0x00, 0x00,  # X pixels per meter
            0x00, 0x00, 0x00, 0x00,  # Y pixels per meter
            0x00, 0x00, 0x00, 0x00,  # Colors used
            0x00, 0x00, 0x00, 0x00,  # Important colors
        ])
        # Blue/purple gradient pixel data (16x16 BGRA, bottom-up)
        pixels = []
        for y in range(16):
            for x in range(16):
                # Create a nice gradient
                b = int((x / 15) * 200 + 55)  # Blue
                g = int((y / 15) * 100 + 50)  # Green
                r = int(150)                   # Red
                a = 255                        # Alpha
                pixels.extend([b, g, r, a])
        # AND mask (16x16 bits = 64 bytes, all zeros = fully opaque)
        and_mask = bytes([0x00] * 64)

        with open(icon_path, 'wb') as f:
            f.write(ico_data)
            f.write(bmp_header)
            f.write(bytes(pixels))
            f.write(and_mask)

        print(f"   Created: {icon_path}")

    return icon_path


def build_exe(mode="full"):
    """Build the executable using PyInstaller"""
    project_root = get_project_root()
    src_path = get_src_path()
    desktop_path = src_path / "distributed_cluster" / "desktop"
    web_path = src_path / "distributed_cluster" / "web"
    # Use app_entry.py which has absolute imports for PyInstaller
    main_script = desktop_path / "app_entry.py"

    # Create icon if missing
    icon_path = create_icon_if_missing()

    # Determine separator based on platform
    data_sep = ";" if sys.platform == "win32" else ":"

    print("\n" + "=" * 60)
    print("🚀 NebulaCompute Desktop Builder")
    print("=" * 60)
    print(f"📁 Project root: {project_root}")
    print(f"📦 Build mode: {mode}")
    print(f"🖥️  Platform: {sys.platform}")
    print("=" * 60 + "\n")

    # Runtime hook for frozen environment setup
    runtime_hook = desktop_path / "runtime_hook.py"

    # Base options
    options = [
        "pyinstaller",
        "--name=NebulaCompute",
        "--windowed",      # No console window (GUI app)
        "--onefile",       # Single executable file
        "--clean",         # Clean PyInstaller cache
        "--noconfirm",     # Don't ask for confirmation
    ]

    # Add runtime hook if exists
    if runtime_hook.exists():
        options.append(f"--runtime-hook={runtime_hook}")
        print("   ✓ Runtime hook added")

    # Add icon
    if icon_path.exists():
        options.append(f"--icon={icon_path}")

    # ============ Data Files ============
    print("📦 Adding data files...")

    # Desktop resources
    if (desktop_path / "resources").exists():
        options.append(f'--add-data={desktop_path / "resources"}{data_sep}distributed_cluster/desktop/resources')
        print("   ✓ Desktop resources")

    # Web templates and static files (for embedded web server)
    if (web_path / "templates").exists():
        options.append(f'--add-data={web_path / "templates"}{data_sep}distributed_cluster/web/templates')
        print("   ✓ Web templates")

    if (web_path / "static").exists():
        options.append(f'--add-data={web_path / "static"}{data_sep}distributed_cluster/web/static')
        print("   ✓ Web static files")

    # Config files
    config_path = project_root / "config"
    if config_path.exists():
        options.append(f'--add-data={config_path}{data_sep}config')
        print("   ✓ Config files")

    # ============ Hidden Imports ============
    print("\n📦 Adding hidden imports...")

    hidden_imports = [
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

        # HTTP & WebSocket
        "httpx",
        "httpx._transports",
        "httpx._transports.default",
        "websockets",
        "websockets.client",
        "websockets.legacy",
        "websockets.legacy.client",

        # Distributed Cluster modules
        "distributed_cluster",
        "distributed_cluster.desktop",
        "distributed_cluster.desktop.main",
        "distributed_cluster.desktop.main_window",
        "distributed_cluster.desktop.app_entry",

        # Desktop API
        "distributed_cluster.desktop.api",
        "distributed_cluster.desktop.api.client",

        # Desktop Views (ALL views must be explicitly listed)
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

        # Desktop Widgets (ALL widgets must be explicitly listed)
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

        # Desktop Resources (styles, themes, icons)
        "distributed_cluster.desktop.resources",
        "distributed_cluster.desktop.resources.styles",
        "distributed_cluster.desktop.resources.themes",
        "distributed_cluster.desktop.resources.icon",

        # Desktop UI components
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

        # Windows-specific modules (for Windows 11 integration)
        "ctypes",
        "ctypes.wintypes",
        "winreg",
        "subprocess",
        "platform",

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

        # SSL/TLS
        "ssl",
        "certifi",

        # Other utilities
        "anyio",
        "anyio._backends",
        "anyio._backends._asyncio",
        "sniffio",
        "h11",
        "httpcore",

        # Required for pkg_resources (fixes jaraco error)
        "jaraco",
        "jaraco.text",
        "jaraco.functools",
        "jaraco.context",
        "jaraco.classes",
        "jaraco.collections",
        "pkg_resources",
        "pkg_resources.extern",

        # More dependencies
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

    if mode == "full":
        # Add more imports for full mode
        hidden_imports.extend([
            # Web server (if running embedded)
            "distributed_cluster.web",
            "distributed_cluster.web.app",
            "distributed_cluster.master",
            "distributed_cluster.master.state",
            # Note: distributed_cluster.master.api removed to avoid cryptography deps
            # Note: distributed_cluster.scheduler removed to avoid heavy deps
            # Note: distributed_cluster.security removed to avoid cryptography deps
            # Note: distributed_cluster.ai removed to avoid heavy deps

            # FastAPI (for embedded server)
            "fastapi",
            "starlette",
            "uvicorn",
            "jinja2",
            "pydantic",
        ])

    for imp in hidden_imports:
        options.append(f"--hidden-import={imp}")
    print(f"   ✓ Added {len(hidden_imports)} hidden imports")

    # ============ Collect All ============
    print("\n📦 Collecting packages...")

    collect_all = [
        "PySide6",
        "httpx",
        "websockets",
        # Required for pkg_resources compatibility
        "jaraco",
        "jaraco.text",
        "jaraco.functools",
        "jaraco.context",
    ]

    # Note: We don't collect all of distributed_cluster even in full mode
    # because it may pull in cryptography/docker/pynvml dependencies
    # that cause PyInstaller issues. Hidden imports handle the needed modules.

    for pkg in collect_all:
        options.append(f"--collect-all={pkg}")
    print(f"   ✓ Collecting {len(collect_all)} packages")

    # ============ Exclusions ============
    print("\n📦 Excluding unnecessary modules...")

    exclude_modules = [
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
        "setuptools",
        "pip",
        "wheel",
        # Cryptography causes issues with PyInstaller
        "cryptography",
        "cryptography.hazmat",
        "cryptography.hazmat.backends",
        "cryptography.hazmat.backends.openssl",
        # Docker not needed for desktop GUI
        "docker",
        # pynvml not needed for desktop GUI
        "pynvml",
        # pkg_resources causes jaraco issues - exclude if not needed
        "pkg_resources",
    ]

    for mod in exclude_modules:
        options.append(f"--exclude-module={mod}")
    print(f"   ✓ Excluding {len(exclude_modules)} modules")

    # ============ Output Paths ============
    options.extend([
        f'--distpath={project_root / "dist"}',
        f'--workpath={project_root / "build"}',
        f"--specpath={project_root}",
    ])

    # Add paths
    options.append(f"--paths={src_path}")

    # Add main script
    options.append(str(main_script))

    # ============ Build ============
    print("\n" + "=" * 60)
    print("🔨 Building executable...")
    print("=" * 60 + "\n")

    # Run PyInstaller
    result = subprocess.run(options, cwd=project_root)

    if result.returncode == 0:
        # Determine output filename based on platform
        if sys.platform == "win32":
            exe_name = "NebulaCompute.exe"
        elif sys.platform == "darwin":
            exe_name = "NebulaCompute"  # or .app bundle
        else:
            exe_name = "NebulaCompute"

        exe_path = project_root / "dist" / exe_name

        print("\n" + "=" * 60)
        print("✅ BUILD SUCCESSFUL!")
        print("=" * 60)
        print(f"📁 Executable: {exe_path}")

        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"📊 Size: {size_mb:.1f} MB")

        print("\n🚀 To run the application:")
        print(f"   {exe_path}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ BUILD FAILED!")
        print("=" * 60)
        sys.exit(1)


def create_installer_script():
    """Create NSIS installer script for Windows"""
    project_root = get_project_root()

    nsis_script = '''
; NebulaCompute Desktop Installer
; NSIS Installer Script

!include "MUI2.nsh"

; General
Name "NebulaCompute Desktop"
OutFile "NebulaCompute_Setup.exe"
InstallDir "$PROGRAMFILES\\NebulaCompute"
RequestExecutionLevel admin

; Interface
!define MUI_ABORTWARNING
!define MUI_ICON "src\\distributed_cluster\\desktop\\resources\\icon.ico"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Languages
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Arabic"

; Installer Section
Section "Install"
    SetOutPath $INSTDIR

    ; Copy files
    File "dist\\NebulaCompute.exe"

    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\\NebulaCompute"
    CreateShortCut "$SMPROGRAMS\\NebulaCompute\\NebulaCompute.lnk" "$INSTDIR\\NebulaCompute.exe"
    CreateShortCut "$DESKTOP\\NebulaCompute.lnk" "$INSTDIR\\NebulaCompute.exe"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\\Uninstall.exe"

    ; Registry entries
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\NebulaCompute" \\
        "DisplayName" "NebulaCompute Desktop"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\NebulaCompute" \\
        "UninstallString" "$INSTDIR\\Uninstall.exe"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\NebulaCompute" \\
        "DisplayIcon" "$INSTDIR\\NebulaCompute.exe"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\NebulaCompute" \\
        "Publisher" "NebulaCompute Team"
SectionEnd

; Uninstaller Section
Section "Uninstall"
    Delete "$INSTDIR\\NebulaCompute.exe"
    Delete "$INSTDIR\\Uninstall.exe"

    Delete "$SMPROGRAMS\\NebulaCompute\\NebulaCompute.lnk"
    Delete "$DESKTOP\\NebulaCompute.lnk"
    RMDir "$SMPROGRAMS\\NebulaCompute"
    RMDir "$INSTDIR"

    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\NebulaCompute"
SectionEnd
'''

    nsis_path = project_root / "installer.nsi"
    with open(nsis_path, "w") as f:
        f.write(nsis_script)

    print(f"✅ NSIS installer script created: {nsis_path}")


def main():
    """Main build function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build NebulaCompute Desktop Application",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build_exe.py                  # Build full version
  python build_exe.py --mode minimal   # Build minimal version
  python build_exe.py --clean          # Clean build artifacts
  python build_exe.py --installer      # Create Windows installer script
        """
    )
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts only")
    parser.add_argument("--installer", action="store_true", help="Create NSIS installer script")
    parser.add_argument("--mode", choices=["full", "minimal", "standard", "ultra"], default="full",
                        help="Build mode: full (all features) or minimal (basic)")
    # CI/CD arguments (for GitHub Actions compatibility)
    parser.add_argument("--type", choices=["debug", "release", "release-optimized", "profile"],
                        default="release", help="Build type (for CI)")
    parser.add_argument("--platform", choices=["windows", "linux", "macos"],
                        default=None, help="Target platform (for CI)")
    parser.add_argument("--arch", choices=["x64", "arm64", "universal"],
                        default="x64", help="Target architecture (for CI)")
    parser.add_argument("--version", type=str, default=None,
                        help="Version string (for CI)")
    args = parser.parse_args()

    if args.clean:
        clean_build()
        print("✅ Build cleaned.")
        return

    if args.installer:
        create_installer_script()
        return

    # Check for PyInstaller
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("📦 PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Clean and build
    clean_build()
    build_exe(mode=args.mode)


if __name__ == "__main__":
    main()
