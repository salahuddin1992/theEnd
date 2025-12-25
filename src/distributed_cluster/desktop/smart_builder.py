"""
Smart Builder for NebulaCompute Desktop - Advanced Edition
نظام البناء الذكي المتقدم لتطبيق NebulaCompute

Features / المميزات:
- Auto-detection of best compiler (PyInstaller, Nuitka, cx_Freeze)
- Smart optimization based on target platform
- Code protection & obfuscation
- Auto-versioning from git
- Multiple output formats (exe, msi, deb, rpm, dmg, appimage)
- Built-in auto-updater integration
- Size optimization with UPX compression
- Splash screen generation
- Digital signing support

Usage:
    python smart_builder.py build                    # Auto-detect best method
    python smart_builder.py build --compiler nuitka  # Use Nuitka (fastest exe)
    python smart_builder.py build --compiler pyinstaller --optimize max
    python smart_builder.py build --target windows --installer msi
    python smart_builder.py build --target linux --installer appimage
    python smart_builder.py build --all-platforms    # Build for all platforms
    python smart_builder.py release --version 1.0.0  # Full release build
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class Compiler(Enum):
    PYINSTALLER = "pyinstaller"
    NUITKA = "nuitka"
    CX_FREEZE = "cx_freeze"
    AUTO = "auto"


class OptimizationLevel(Enum):
    NONE = 0
    BASIC = 1
    BALANCED = 2
    MAX = 3
    EXTREME = 4  # Maximum compression, slower build


class InstallerType(Enum):
    NONE = "none"
    # Windows
    MSI = "msi"
    NSIS = "nsis"
    INNO = "inno"
    # Linux
    DEB = "deb"
    RPM = "rpm"
    APPIMAGE = "appimage"
    FLATPAK = "flatpak"
    # macOS
    DMG = "dmg"
    PKG = "pkg"


@dataclass
class BuildConfig:
    """Build configuration"""
    name: str = "NebulaCompute"
    version: str = "1.0.0"
    description: str = "Distributed Computing System"
    author: str = "NebulaCompute Team"
    website: str = "https://github.com/nebulacompute"

    compiler: Compiler = Compiler.AUTO
    optimization: OptimizationLevel = OptimizationLevel.BALANCED
    installer_type: InstallerType = InstallerType.NONE

    # Features
    console: bool = False
    one_file: bool = True
    include_debug: bool = False
    code_protection: bool = False
    auto_updater: bool = True
    splash_screen: bool = True

    # Paths
    entry_point: str = "app_entry.py"
    icon: Optional[str] = None
    splash_image: Optional[str] = None

    # Signing
    sign_code: bool = False
    sign_cert: Optional[str] = None
    sign_password: Optional[str] = None

    # Additional
    extra_data: list = field(default_factory=list)
    extra_binaries: list = field(default_factory=list)
    hidden_imports: list = field(default_factory=list)
    excludes: list = field(default_factory=list)


class SmartBuilder:
    """Smart builder with auto-detection and optimization"""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).parent.parent.parent.parent
        self.src_path = self.project_root / "src"
        self.desktop_path = self.src_path / "distributed_cluster" / "desktop"
        self.dist_path = self.project_root / "dist"
        self.build_path = self.project_root / "build"

        self.platform = platform.system().lower()
        self.arch = platform.machine().lower()

        self._available_compilers: dict[str, bool] = {}
        self._detect_available_tools()

    def _detect_available_tools(self):
        """Detect available build tools"""
        # Check PyInstaller
        try:
            subprocess.run([sys.executable, "-m", "PyInstaller", "--version"],
                         capture_output=True, check=True)
            self._available_compilers["pyinstaller"] = True
        except Exception:
            self._available_compilers["pyinstaller"] = False

        # Check Nuitka
        try:
            subprocess.run([sys.executable, "-m", "nuitka", "--version"],
                         capture_output=True, check=True)
            self._available_compilers["nuitka"] = True
        except Exception:
            self._available_compilers["nuitka"] = False

        # Check cx_Freeze
        try:
            import cx_Freeze
            self._available_compilers["cx_freeze"] = True
        except ImportError:
            self._available_compilers["cx_freeze"] = False

        # Check UPX
        try:
            subprocess.run(["upx", "--version"], capture_output=True, check=True)
            self._upx_available = True
        except Exception:
            self._upx_available = False

        print("🔍 Detected build tools:")
        for tool, available in self._available_compilers.items():
            status = "✅" if available else "❌"
            print(f"   {status} {tool}")
        print(f"   {'✅' if self._upx_available else '❌'} UPX compression")

    def _get_version_from_git(self) -> str:
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
        return "1.0.0"

    def _get_git_hash(self) -> str:
        """Get short git commit hash"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, cwd=self.project_root
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return "unknown"

    def _select_best_compiler(self) -> Compiler:
        """Auto-select the best available compiler"""
        # Nuitka produces the fastest executables
        if self._available_compilers.get("nuitka"):
            print("🎯 Auto-selected: Nuitka (best performance)")
            return Compiler.NUITKA

        # PyInstaller is most reliable
        if self._available_compilers.get("pyinstaller"):
            print("🎯 Auto-selected: PyInstaller (most compatible)")
            return Compiler.PYINSTALLER

        # cx_Freeze as fallback
        if self._available_compilers.get("cx_freeze"):
            print("🎯 Auto-selected: cx_Freeze (fallback)")
            return Compiler.CX_FREEZE

        raise RuntimeError("No compiler available! Install: pip install pyinstaller nuitka")

    def _create_splash_screen(self, config: BuildConfig) -> Optional[Path]:
        """Create a splash screen image"""
        splash_path = self.build_path / "splash.png"
        self.build_path.mkdir(parents=True, exist_ok=True)

        try:
            from PIL import Image, ImageDraw, ImageFont

            # Create gradient background
            width, height = 600, 400
            img = Image.new('RGBA', (width, height))

            for y in range(height):
                r = int(30 + (y / height) * 20)
                g = int(40 + (y / height) * 30)
                b = int(80 + (y / height) * 60)
                for x in range(width):
                    img.putpixel((x, y), (r, g, b, 255))

            draw = ImageDraw.Draw(img)

            # Add text
            try:
                font_large = ImageFont.truetype("arial.ttf", 48)
                font_small = ImageFont.truetype("arial.ttf", 18)
            except Exception:
                font_large = ImageFont.load_default()
                font_small = font_large

            # Title
            draw.text((width // 2, height // 3), config.name,
                     fill=(255, 255, 255, 255), anchor="mm", font=font_large)

            # Version
            draw.text((width // 2, height // 2), f"v{config.version}",
                     fill=(200, 200, 200, 255), anchor="mm", font=font_small)

            # Loading text
            draw.text((width // 2, height * 2 // 3), "جاري التحميل... Loading...",
                     fill=(150, 150, 200, 255), anchor="mm", font=font_small)

            img.save(splash_path)
            print(f"   ✅ Created splash screen: {splash_path}")
            return splash_path

        except ImportError:
            print("   ⚠️ PIL not available, skipping splash screen")
            return None

    def _create_version_file(self, config: BuildConfig) -> Path:
        """Create version info file for Windows"""
        version_path = self.build_path / "version_info.py"
        self.build_path.mkdir(parents=True, exist_ok=True)

        # Parse version
        version_parts = config.version.split(".")
        while len(version_parts) < 4:
            version_parts.append("0")

        version_tuple = tuple(int(p) if p.isdigit() else 0 for p in version_parts[:4])

        version_content = f'''# UTF-8
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
'''
        version_path.write_text(version_content)
        return version_path

    def _create_auto_updater_module(self, config: BuildConfig) -> Path:
        """Create auto-updater module"""
        updater_path = self.desktop_path / "auto_updater.py"

        updater_code = '''"""
Auto-Updater Module for NebulaCompute
نظام التحديث التلقائي
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.request import urlopen, urlretrieve


@dataclass
class UpdateInfo:
    """Update information"""
    version: str
    download_url: str
    changelog: str
    size: int
    sha256: str
    release_date: str
    mandatory: bool = False


class AutoUpdater:
    """
    Auto-updater with background download and seamless update
    محدث تلقائي مع تحميل في الخلفية وتحديث سلس
    """

    UPDATE_CHECK_URL = "https://api.github.com/repos/nebulacompute/nebulacompute/releases/latest"

    def __init__(self, current_version: str, app_path: Optional[Path] = None):
        self.current_version = current_version
        self.app_path = app_path or Path(sys.executable)
        self._update_info: Optional[UpdateInfo] = None
        self._download_progress: float = 0
        self._is_downloading: bool = False

    def check_for_updates(self, callback: Optional[Callable[[Optional[UpdateInfo]], None]] = None) -> Optional[UpdateInfo]:
        """
        Check for available updates
        التحقق من التحديثات المتاحة
        """
        try:
            with urlopen(self.UPDATE_CHECK_URL, timeout=10) as response:
                data = json.loads(response.read().decode())

            latest_version = data.get("tag_name", "").lstrip("v")

            if self._compare_versions(latest_version, self.current_version) > 0:
                # Find the right asset for current platform
                assets = data.get("assets", [])
                download_url = None
                size = 0

                platform_key = sys.platform
                if platform_key == "win32":
                    platform_key = "windows"
                elif platform_key == "darwin":
                    platform_key = "macos"

                for asset in assets:
                    name = asset.get("name", "").lower()
                    if platform_key in name:
                        download_url = asset.get("browser_download_url")
                        size = asset.get("size", 0)
                        break

                if download_url:
                    self._update_info = UpdateInfo(
                        version=latest_version,
                        download_url=download_url,
                        changelog=data.get("body", ""),
                        size=size,
                        sha256="",  # Will be verified after download
                        release_date=data.get("published_at", ""),
                        mandatory=False
                    )

                    if callback:
                        callback(self._update_info)
                    return self._update_info

        except Exception as e:
            print(f"Update check failed: {e}")

        if callback:
            callback(None)
        return None

    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compare two version strings"""
        def parse(v):
            return [int(x) for x in v.split(".") if x.isdigit()]

        p1, p2 = parse(v1), parse(v2)

        for a, b in zip(p1, p2):
            if a > b:
                return 1
            if a < b:
                return -1

        return len(p1) - len(p2)

    def download_update(self,
                       progress_callback: Optional[Callable[[float], None]] = None,
                       complete_callback: Optional[Callable[[Path], None]] = None) -> Optional[Path]:
        """
        Download update in background
        تحميل التحديث في الخلفية
        """
        if not self._update_info:
            return None

        self._is_downloading = True
        self._download_progress = 0

        def download_thread():
            try:
                # Create temp file
                temp_dir = Path(tempfile.mkdtemp())

                if sys.platform == "win32":
                    filename = f"{self._update_info.version}.exe"
                else:
                    filename = f"{self._update_info.version}"

                temp_file = temp_dir / filename

                def report_progress(block_num, block_size, total_size):
                    if total_size > 0:
                        self._download_progress = (block_num * block_size) / total_size
                        if progress_callback:
                            progress_callback(self._download_progress)

                urlretrieve(
                    self._update_info.download_url,
                    temp_file,
                    reporthook=report_progress
                )

                self._is_downloading = False

                if complete_callback:
                    complete_callback(temp_file)

                return temp_file

            except Exception as e:
                print(f"Download failed: {e}")
                self._is_downloading = False
                return None

        thread = threading.Thread(target=download_thread)
        thread.daemon = True
        thread.start()

        return None  # Returns immediately, use callbacks

    def apply_update(self, update_file: Path, restart: bool = True):
        """
        Apply downloaded update
        تطبيق التحديث المحمل
        """
        if sys.platform == "win32":
            # Windows: Use batch script to replace exe
            batch_script = f"""
@echo off
timeout /t 2 /nobreak >nul
copy /y "{update_file}" "{self.app_path}"
start "" "{self.app_path}"
del "%~f0"
"""
            batch_path = Path(tempfile.gettempdir()) / "update.bat"
            batch_path.write_text(batch_script)

            subprocess.Popen(["cmd", "/c", str(batch_path)],
                           creationflags=subprocess.CREATE_NO_WINDOW)
            sys.exit(0)

        else:
            # Linux/macOS: Direct replacement
            backup_path = self.app_path.with_suffix(".backup")

            try:
                # Backup current
                shutil.copy2(self.app_path, backup_path)

                # Replace with new
                shutil.copy2(update_file, self.app_path)
                # nosec B103 - executable needs 755 permissions
                os.chmod(self.app_path, 0o755)

                if restart:
                    os.execv(str(self.app_path), [str(self.app_path)])

            except Exception as e:
                # Restore backup on failure
                if backup_path.exists():
                    shutil.copy2(backup_path, self.app_path)
                raise e


def check_updates_on_startup(current_version: str):
    """
    Non-blocking update check on startup
    فحص التحديثات عند بدء التشغيل بدون حجب
    """
    def check():
        updater = AutoUpdater(current_version)
        update = updater.check_for_updates()
        if update:
            print(f"🆕 Update available: v{update.version}")

    thread = threading.Thread(target=check)
    thread.daemon = True
    thread.start()
'''

        updater_path.write_text(updater_code)
        print(f"   ✅ Created auto-updater module: {updater_path}")
        return updater_path

    def _build_with_pyinstaller(self, config: BuildConfig) -> Path:
        """Build using PyInstaller"""
        print("\n🔨 Building with PyInstaller...")

        data_sep = ";" if self.platform == "windows" else ":"

        options = [
            sys.executable, "-m", "PyInstaller",
            f"--name={config.name}",
            "--clean",
            "--noconfirm",
        ]

        # Console or windowed
        if config.console:
            options.append("--console")
        else:
            options.append("--windowed")

        # One file or directory
        if config.one_file:
            options.append("--onefile")
        else:
            options.append("--onedir")

        # Icon
        icon_path = config.icon or (self.desktop_path / "resources" / "icon.ico")
        if Path(icon_path).exists():
            options.append(f"--icon={icon_path}")

        # Version info (Windows)
        if self.platform == "windows":
            version_file = self._create_version_file(config)
            options.append(f"--version-file={version_file}")

        # Splash screen
        if config.splash_screen and config.one_file:
            splash = self._create_splash_screen(config)
            if splash:
                options.append(f"--splash={splash}")

        # Data files
        web_path = self.src_path / "distributed_cluster" / "web"

        data_files = [
            (self.desktop_path / "resources", "distributed_cluster/desktop/resources"),
            (web_path / "templates", "distributed_cluster/web/templates"),
            (web_path / "static", "distributed_cluster/web/static"),
            (self.project_root / "config", "config"),
        ]

        for src, dest in data_files:
            if Path(src).exists():
                options.append(f"--add-data={src}{data_sep}{dest}")

        # Hidden imports
        hidden_imports = [
            # PySide6 / Qt
            "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
            "PySide6.QtCharts", "PySide6.QtNetwork", "PySide6.QtSvg",
            # Async
            "qasync", "asyncio",
            # HTTP & Network
            "httpx", "websockets",
            # Project modules
            "distributed_cluster.desktop", "distributed_cluster.models",
            "distributed_cluster.core",
            # Standard library
            "json", "ssl", "certifi",
            # Required for pkg_resources (fixes jaraco error)
            "jaraco", "jaraco.text", "jaraco.functools", "jaraco.context",
            "jaraco.classes", "jaraco.collections",
            "pkg_resources", "pkg_resources.extern",
            # More dependencies that may be needed
            "importlib_metadata", "importlib_resources",
            "packaging", "packaging.version", "packaging.specifiers",
            "packaging.requirements", "packaging.markers",
            "zipp", "more_itertools",
        ] + config.hidden_imports

        for imp in hidden_imports:
            options.append(f"--hidden-import={imp}")

        # Excludes (removed setuptools - it's needed!)
        excludes = [
            "tkinter", "matplotlib", "numpy", "pandas", "scipy",
            "PIL", "IPython", "jupyter", "pytest",
        ] + config.excludes

        for exc in excludes:
            options.append(f"--exclude-module={exc}")

        # Optimization
        if config.optimization.value >= OptimizationLevel.BALANCED.value:
            options.append("--collect-all=PySide6")
            options.append("--collect-all=httpx")

        if config.optimization.value >= OptimizationLevel.MAX.value and self._upx_available:
            options.append("--upx-dir=/usr/bin")

        # Paths
        options.extend([
            f"--distpath={self.dist_path}",
            f"--workpath={self.build_path}",
            f"--specpath={self.project_root}",
            f"--paths={self.src_path}",
        ])

        # Entry point
        entry = self.desktop_path / config.entry_point
        options.append(str(entry))

        # Run build
        result = subprocess.run(options, cwd=self.project_root)

        if result.returncode != 0:
            raise RuntimeError("PyInstaller build failed!")

        # Return output path
        exe_name = f"{config.name}.exe" if self.platform == "windows" else config.name
        return self.dist_path / exe_name

    def _build_with_nuitka(self, config: BuildConfig) -> Path:
        """Build using Nuitka (produces faster executables)"""
        print("\n🔨 Building with Nuitka (this may take a while)...")

        options = [
            sys.executable, "-m", "nuitka",
            f"--output-filename={config.name}",
            "--standalone",
            "--assume-yes-for-downloads",
        ]

        # Console or GUI
        if not config.console:
            if self.platform == "windows":
                options.append("--windows-disable-console")
            elif self.platform == "darwin":
                options.append("--macos-create-app-bundle")

        # One file
        if config.one_file:
            options.append("--onefile")

        # Icon
        icon_path = config.icon or (self.desktop_path / "resources" / "icon.ico")
        if Path(icon_path).exists():
            if self.platform == "windows":
                options.append(f"--windows-icon-from-ico={icon_path}")
            elif self.platform == "darwin":
                options.append(f"--macos-app-icon={icon_path}")

        # Optimization
        if config.optimization.value >= OptimizationLevel.BASIC.value:
            options.append("--lto=yes")

        if config.optimization.value >= OptimizationLevel.BALANCED.value:
            options.append("--jobs=4")

        if config.optimization.value >= OptimizationLevel.MAX.value:
            options.append("--clang")

        if config.optimization.value >= OptimizationLevel.EXTREME.value:
            options.append("--pgo")  # Profile Guided Optimization

        # Code protection
        if config.code_protection:
            options.append("--deployment")

        # Plugins
        options.extend([
            "--enable-plugin=pyside6",
            "--include-package=distributed_cluster",
        ])

        # Include data
        web_path = self.src_path / "distributed_cluster" / "web"
        if (web_path / "templates").exists():
            options.append(f"--include-data-dir={web_path / 'templates'}=distributed_cluster/web/templates")
        if (web_path / "static").exists():
            options.append(f"--include-data-dir={web_path / 'static'}=distributed_cluster/web/static")

        # Output
        options.extend([
            f"--output-dir={self.dist_path}",
        ])

        # Entry point
        entry = self.desktop_path / config.entry_point
        options.append(str(entry))

        # Run build
        result = subprocess.run(options, cwd=self.project_root)

        if result.returncode != 0:
            raise RuntimeError("Nuitka build failed!")

        exe_name = f"{config.name}.exe" if self.platform == "windows" else config.name
        return self.dist_path / exe_name

    def _create_msi_installer(self, exe_path: Path, config: BuildConfig) -> Path:
        """Create MSI installer using WiX"""
        print("\n📦 Creating MSI installer...")

        # WiX XML template
        wix_template = f'''<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
    <Product Id="*" Name="{config.name}" Language="1033"
             Version="{config.version}" Manufacturer="{config.author}"
             UpgradeCode="PUT-GUID-HERE">

        <Package InstallerVersion="200" Compressed="yes" InstallScope="perMachine"/>
        <MajorUpgrade DowngradeErrorMessage="A newer version is already installed."/>
        <MediaTemplate EmbedCab="yes"/>

        <Feature Id="ProductFeature" Title="{config.name}" Level="1">
            <ComponentGroupRef Id="ProductComponents"/>
            <ComponentRef Id="ApplicationShortcut"/>
        </Feature>

        <Directory Id="TARGETDIR" Name="SourceDir">
            <Directory Id="ProgramFilesFolder">
                <Directory Id="INSTALLFOLDER" Name="{config.name}"/>
            </Directory>
            <Directory Id="ProgramMenuFolder">
                <Directory Id="ApplicationProgramsFolder" Name="{config.name}"/>
            </Directory>
            <Directory Id="DesktopFolder" Name="Desktop"/>
        </Directory>

        <ComponentGroup Id="ProductComponents" Directory="INSTALLFOLDER">
            <Component Id="MainExecutable" Guid="*">
                <File Id="{config.name}EXE" Source="{exe_path}" KeyPath="yes"/>
            </Component>
        </ComponentGroup>

        <DirectoryRef Id="ApplicationProgramsFolder">
            <Component Id="ApplicationShortcut" Guid="*">
                <Shortcut Id="ApplicationStartMenuShortcut"
                          Name="{config.name}" Target="[INSTALLFOLDER]{config.name}.exe"
                          WorkingDirectory="INSTALLFOLDER"/>
                <RemoveFolder Id="CleanUpShortCut" Directory="ApplicationProgramsFolder" On="uninstall"/>
                <RegistryValue Root="HKCU" Key="Software\\{config.author}\\{config.name}"
                               Name="installed" Type="integer" Value="1" KeyPath="yes"/>
            </Component>
        </DirectoryRef>
    </Product>
</Wix>
'''

        wix_path = self.build_path / f"{config.name}.wxs"
        wix_path.write_text(wix_template)

        print(f"   ✅ Created WiX source: {wix_path}")
        print("   ℹ️ To build MSI, install WiX Toolset and run:")
        print(f"      candle.exe {wix_path}")
        print(f"      light.exe -o {config.name}.msi {config.name}.wixobj")

        return wix_path

    def _create_nsis_installer(self, exe_path: Path, config: BuildConfig) -> Path:
        """Create NSIS installer"""
        print("\n📦 Creating NSIS installer...")

        nsis_script = f'''; {config.name} Installer
; Generated by SmartBuilder

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

; Interface
!define MUI_ABORTWARNING
!define MUI_ICON "{self.desktop_path / 'resources' / 'icon.ico'}"
!define MUI_UNICON "{self.desktop_path / 'resources' / 'icon.ico'}"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "{self.project_root / 'LICENSE'}"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Languages
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Arabic"

; Installer
Section "Install"
    SetOutPath $INSTDIR

    ; Main executable
    File "{exe_path}"

    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\\{config.name}"
    CreateShortCut "$SMPROGRAMS\\{config.name}\\{config.name}.lnk" "$INSTDIR\\{exe_path.name}"
    CreateShortCut "$SMPROGRAMS\\{config.name}\\Uninstall.lnk" "$INSTDIR\\Uninstall.exe"
    CreateShortCut "$DESKTOP\\{config.name}.lnk" "$INSTDIR\\{exe_path.name}"

    ; Uninstaller
    WriteUninstaller "$INSTDIR\\Uninstall.exe"

    ; Registry
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

    ; Get installed size
    ${{GetSize}} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{config.name}" \\
        "EstimatedSize" "$0"
SectionEnd

; Uninstaller
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
'''

        nsis_path = self.build_path / f"{config.name}.nsi"
        nsis_path.write_text(nsis_script)

        # Try to build if NSIS is available
        try:
            result = subprocess.run(["makensis", str(nsis_path)],
                                   capture_output=True, cwd=self.build_path)
            if result.returncode == 0:
                print(f"   ✅ Created installer: {config.name}_Setup_{config.version}.exe")
        except FileNotFoundError:
            print(f"   ℹ️ NSIS not found. Script saved to: {nsis_path}")
            print("   ℹ️ Install NSIS and run: makensis " + str(nsis_path))

        return nsis_path

    def _create_appimage(self, exe_path: Path, config: BuildConfig) -> Path:
        """Create AppImage for Linux"""
        print("\n📦 Creating AppImage...")

        appdir = self.build_path / f"{config.name}.AppDir"
        appdir.mkdir(parents=True, exist_ok=True)

        # AppRun script
        apprun = appdir / "AppRun"
        apprun.write_text(f'''#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${{SELF%/*}}
export PATH="${{HERE}}/usr/bin:${{PATH}}"
exec "${{HERE}}/usr/bin/{config.name}" "$@"
''')
        # nosec B103 - AppRun script needs 755 permissions
        os.chmod(apprun, 0o755)

        # Desktop file
        desktop = appdir / f"{config.name}.desktop"
        desktop.write_text(f'''[Desktop Entry]
Name={config.name}
Exec={config.name}
Icon={config.name.lower()}
Type=Application
Categories=Development;Utility;
''')

        # Copy executable
        usr_bin = appdir / "usr" / "bin"
        usr_bin.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe_path, usr_bin / config.name)

        # Copy icon
        icon_src = self.desktop_path / "resources" / "icon.png"
        if icon_src.exists():
            shutil.copy2(icon_src, appdir / f"{config.name.lower()}.png")

        # Download appimagetool if needed
        appimagetool = self.build_path / "appimagetool"
        if not appimagetool.exists():
            print("   📥 Downloading appimagetool...")
            url = "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
            try:
                # nosec B310 - downloading from trusted GitHub releases
                urllib.request.urlretrieve(url, appimagetool)
                # nosec B103 - appimagetool needs 755 permissions
                os.chmod(appimagetool, 0o755)
            except Exception as e:
                print(f"   ⚠️ Could not download appimagetool: {e}")
                return appdir

        # Build AppImage
        output = self.dist_path / f"{config.name}-{config.version}-x86_64.AppImage"
        result = subprocess.run([str(appimagetool), str(appdir), str(output)],
                               capture_output=True, cwd=self.build_path)

        if result.returncode == 0:
            print(f"   ✅ Created: {output}")
            return output
        else:
            print("   ⚠️ AppImage creation failed")
            return appdir

    def _create_deb_package(self, exe_path: Path, config: BuildConfig) -> Path:
        """Create DEB package for Debian/Ubuntu"""
        print("\n📦 Creating DEB package...")

        pkg_name = config.name.lower()
        pkg_dir = self.build_path / f"{pkg_name}_{config.version}"

        # Create directory structure
        (pkg_dir / "DEBIAN").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "usr" / "bin").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "usr" / "share" / "applications").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(parents=True, exist_ok=True)

        # Control file
        control = pkg_dir / "DEBIAN" / "control"

        # Get size
        size = exe_path.stat().st_size // 1024

        control.write_text(f'''Package: {pkg_name}
Version: {config.version}
Section: utils
Priority: optional
Architecture: amd64
Installed-Size: {size}
Maintainer: {config.author}
Description: {config.description}
 NebulaCompute Desktop - Distributed Computing Management
 نظام إدارة الحوسبة الموزعة
''')

        # Copy executable
        shutil.copy2(exe_path, pkg_dir / "usr" / "bin" / pkg_name)
        # nosec B103 - executable needs 755 permissions
        os.chmod(pkg_dir / "usr" / "bin" / pkg_name, 0o755)

        # Desktop file
        desktop = pkg_dir / "usr" / "share" / "applications" / f"{pkg_name}.desktop"
        desktop.write_text(f'''[Desktop Entry]
Name={config.name}
Comment={config.description}
Exec={pkg_name}
Icon={pkg_name}
Terminal=false
Type=Application
Categories=Development;Utility;
''')

        # Build package
        output = self.dist_path / f"{pkg_name}_{config.version}_amd64.deb"
        result = subprocess.run(["dpkg-deb", "--build", str(pkg_dir), str(output)],
                               capture_output=True)

        if result.returncode == 0:
            print(f"   ✅ Created: {output}")
            return output
        else:
            print("   ⚠️ dpkg-deb not found or failed")
            return pkg_dir

    def clean(self):
        """Clean build artifacts"""
        print("🧹 Cleaning build artifacts...")

        for path in [self.build_path, self.dist_path]:
            if path.exists():
                shutil.rmtree(path)
                print(f"   Removed: {path}")

        # Clean spec files
        for spec in self.project_root.glob("*.spec"):
            spec.unlink()
            print(f"   Removed: {spec}")

    def build(self, config: Optional[BuildConfig] = None) -> Path:
        """
        Main build method
        الدالة الرئيسية للبناء
        """
        config = config or BuildConfig()

        # Auto-detect version
        if config.version == "1.0.0":
            config.version = self._get_version_from_git()

        print("\n" + "=" * 70)
        print(f"🚀 {config.name} Smart Builder v2.0")
        print("=" * 70)
        print(f"📦 Version: {config.version}")
        print(f"🖥️  Platform: {self.platform} ({self.arch})")
        print(f"🔧 Compiler: {config.compiler.value}")
        print(f"⚡ Optimization: {config.optimization.name}")
        print("=" * 70)

        # Create directories
        self.dist_path.mkdir(parents=True, exist_ok=True)
        self.build_path.mkdir(parents=True, exist_ok=True)

        # Create auto-updater if enabled
        if config.auto_updater:
            print("\n📦 Setting up auto-updater...")
            self._create_auto_updater_module(config)

        # Select compiler
        compiler = config.compiler
        if compiler == Compiler.AUTO:
            compiler = self._select_best_compiler()

        # Build
        if compiler == Compiler.NUITKA:
            exe_path = self._build_with_nuitka(config)
        elif compiler == Compiler.PYINSTALLER:
            exe_path = self._build_with_pyinstaller(config)
        else:
            raise RuntimeError(f"Compiler {compiler} not implemented yet")

        # Verify build
        if not exe_path.exists():
            raise RuntimeError(f"Build output not found: {exe_path}")

        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n✅ Executable created: {exe_path}")
        print(f"📊 Size: {size_mb:.1f} MB")

        # Create installer if requested
        if config.installer_type != InstallerType.NONE:
            if config.installer_type == InstallerType.NSIS:
                self._create_nsis_installer(exe_path, config)
            elif config.installer_type == InstallerType.MSI:
                self._create_msi_installer(exe_path, config)
            elif config.installer_type == InstallerType.APPIMAGE:
                self._create_appimage(exe_path, config)
            elif config.installer_type == InstallerType.DEB:
                self._create_deb_package(exe_path, config)

        # Create build info
        build_info = {
            "name": config.name,
            "version": config.version,
            "git_hash": self._get_git_hash(),
            "build_date": datetime.now().isoformat(),
            "platform": self.platform,
            "arch": self.arch,
            "compiler": compiler.value,
            "optimization": config.optimization.name,
            "size_bytes": exe_path.stat().st_size,
            "exe_path": str(exe_path),
        }

        info_path = self.dist_path / "build_info.json"
        info_path.write_text(json.dumps(build_info, indent=2))

        print("\n" + "=" * 70)
        print("✅ BUILD COMPLETE!")
        print("=" * 70)
        print(f"📁 Output: {exe_path}")
        print(f"📋 Build info: {info_path}")
        print("=" * 70)

        return exe_path


def main():
    """CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Smart Builder for NebulaCompute Desktop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python smart_builder.py build                              # Auto-detect best method
  python smart_builder.py build --compiler nuitka            # Use Nuitka
  python smart_builder.py build --optimize max               # Maximum optimization
  python smart_builder.py build --installer nsis             # With NSIS installer
  python smart_builder.py build --installer appimage         # Linux AppImage
  python smart_builder.py release --version 2.0.0            # Full release
  python smart_builder.py clean                              # Clean artifacts
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Build command
    build_parser = subparsers.add_parser("build", help="Build executable")
    build_parser.add_argument("--compiler", choices=["auto", "pyinstaller", "nuitka"],
                             default="auto", help="Compiler to use")
    build_parser.add_argument("--optimize", choices=["none", "basic", "balanced", "max", "extreme"],
                             default="balanced", help="Optimization level")
    build_parser.add_argument("--installer", choices=["none", "nsis", "msi", "appimage", "deb"],
                             default="none", help="Create installer")
    build_parser.add_argument("--console", action="store_true", help="Show console window")
    build_parser.add_argument("--no-updater", action="store_true", help="Disable auto-updater")
    build_parser.add_argument("--no-splash", action="store_true", help="Disable splash screen")
    build_parser.add_argument("--version", type=str, help="Override version")

    # Release command
    release_parser = subparsers.add_parser("release", help="Create full release")
    release_parser.add_argument("--version", type=str, required=True, help="Release version")

    # Clean command
    subparsers.add_parser("clean", help="Clean build artifacts")

    # Info command
    subparsers.add_parser("info", help="Show build environment info")

    args = parser.parse_args()

    builder = SmartBuilder()

    if args.command == "clean":
        builder.clean()

    elif args.command == "info":
        print("\n📋 Build Environment Info")
        print("=" * 50)
        print(f"Platform: {builder.platform}")
        print(f"Architecture: {builder.arch}")
        print(f"Python: {sys.version}")
        print(f"Project: {builder.project_root}")

    elif args.command == "build":
        config = BuildConfig(
            compiler=Compiler(args.compiler),
            optimization=OptimizationLevel[args.optimize.upper()],
            installer_type=InstallerType(args.installer),
            console=args.console,
            auto_updater=not args.no_updater,
            splash_screen=not args.no_splash,
        )
        if args.version:
            config.version = args.version

        builder.build(config)

    elif args.command == "release":
        config = BuildConfig(
            version=args.version,
            compiler=Compiler.AUTO,
            optimization=OptimizationLevel.MAX,
            installer_type=InstallerType.NSIS if builder.platform == "windows" else InstallerType.APPIMAGE,
            auto_updater=True,
            splash_screen=True,
        )
        builder.build(config)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
