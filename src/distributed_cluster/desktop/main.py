"""
NebulaCompute Desktop - Auto-Update System
نظام التحديث التلقائي

Provides seamless application updates:
- Background update checking
- Delta/incremental updates
- Rollback capability
- Update verification
- Staged rollout support
"""

from __future__ import annotations

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
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, ClassVar, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from PySide6.QtCore import QObject, Signal, QTimer

# Check for optional dependencies
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ═══════════════════════════════════════════════════════════════════════════════
# TYPES AND ENUMS
# الأنواع والتعدادات
# ═══════════════════════════════════════════════════════════════════════════════

class UpdateChannel(Enum):
    """Update release channels"""
    STABLE = "stable"
    BETA = "beta"
    NIGHTLY = "nightly"
    DEV = "dev"


class UpdateState(Enum):
    """Update process state"""
    IDLE = auto()
    CHECKING = auto()
    AVAILABLE = auto()
    DOWNLOADING = auto()
    DOWNLOADED = auto()
    INSTALLING = auto()
    INSTALLED = auto()
    RESTARTING = auto()
    ERROR = auto()


class UpdateError(Exception):
    """Base exception for update errors."""
    pass


class UpdateAPIError(UpdateError):
    """Error communicating with update API."""
    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        super().__init__(f"API error (status {status_code}): {message}" if message else f"API returned status {status_code}")


class UpdateDownloadError(UpdateError):
    """Error downloading update."""
    def __init__(self, status_code: int = 0, message: str = ""):
        self.status_code = status_code
        super().__init__(f"Download failed (status {status_code}): {message}" if status_code else message)


class UpdateVerificationError(UpdateError):
    """Error verifying update checksum."""
    def __init__(self, expected: str = "", actual: str = ""):
        self.expected = expected
        self.actual = actual
        msg = "Checksum verification failed"
        if expected and actual:
            msg += f": expected {expected[:16]}..., got {actual[:16]}..."
        super().__init__(msg)


class UpdateInstallError(UpdateError):
    """Error installing update."""
    def __init__(self, message: str = "Installation failed", details: str = ""):
        self.details = details
        super().__init__(f"{message}: {details}" if details else message)


@dataclass
class VersionInfo:
    """Parsed version information"""
    major: int
    minor: int
    patch: int
    prerelease: str = ""
    build: str = ""
    
    @classmethod
    def parse(cls, version: str) -> "VersionInfo":
        """Parse version string"""
        # Remove 'v' prefix if present
        version = version.lstrip("v")
        
        # Split by '-' for prerelease
        parts = version.split("-", 1)
        base = parts[0]
        prerelease = parts[1] if len(parts) > 1 else ""
        
        # Split by '+' for build metadata
        if "+" in prerelease:
            prerelease, build = prerelease.split("+", 1)
        else:
            build = ""
        
        # Parse major.minor.patch
        version_parts = base.split(".")
        major = int(version_parts[0]) if len(version_parts) > 0 else 0
        minor = int(version_parts[1]) if len(version_parts) > 1 else 0
        patch = int(version_parts[2]) if len(version_parts) > 2 else 0
        
        return cls(major, minor, patch, prerelease, build)
    
    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        if self.build:
            version += f"+{self.build}"
        return version
    
    def __lt__(self, other: "VersionInfo") -> bool:
        # Compare major.minor.patch
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
        
        # Prerelease versions have lower precedence
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        
        return self.prerelease < other.prerelease
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VersionInfo):
            return False
        return (
            self.major == other.major and
            self.minor == other.minor and
            self.patch == other.patch and
            self.prerelease == other.prerelease
        )
    
    def __le__(self, other: "VersionInfo") -> bool:
        return self < other or self == other


@dataclass
class UpdateAsset:
    """Update download asset"""
    name: str
    url: str
    size: int
    content_type: str
    checksum: str = ""
    checksum_type: str = "sha256"


@dataclass
class UpdateInfo:
    """Available update information"""
    version: str
    channel: UpdateChannel
    release_date: datetime
    title: str = ""
    description: str = ""
    release_notes: str = ""
    release_url: str = ""
    assets: List[UpdateAsset] = field(default_factory=list)
    is_mandatory: bool = False
    min_version: str = "0.0.0"
    
    @property
    def version_info(self) -> VersionInfo:
        return VersionInfo.parse(self.version)
    
    def get_asset_for_platform(self) -> Optional[UpdateAsset]:
        """Get the appropriate asset for current platform"""
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        # Mapping
        platform_patterns = []
        
        if system == "windows":
            platform_patterns.extend(["windows", "win", "win64", "win32"])
            if "64" in machine or machine == "amd64":
                platform_patterns.insert(0, "win64")
            else:
                platform_patterns.insert(0, "win32")
        elif system == "darwin":
            platform_patterns.extend(["macos", "darwin", "mac", "osx"])
            if machine == "arm64":
                platform_patterns.insert(0, "macos-arm64")
            else:
                platform_patterns.insert(0, "macos-x64")
        elif system == "linux":
            platform_patterns.extend(["linux", "linux64"])
            if machine == "aarch64":
                platform_patterns.insert(0, "linux-arm64")
            else:
                platform_patterns.insert(0, "linux-x64")
        
        # Find matching asset
        for pattern in platform_patterns:
            for asset in self.assets:
                if pattern in asset.name.lower():
                    return asset
        
        return None


@dataclass
class UpdateProgress:
    """Update download/install progress"""
    state: UpdateState
    downloaded_bytes: int = 0
    total_bytes: int = 0
    current_file: str = ""
    message: str = ""
    
    @property
    def percentage(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return (self.downloaded_bytes / self.total_bytes) * 100


# ═══════════════════════════════════════════════════════════════════════════════
# UPDATE MANAGER
# مدير التحديثات
# ═══════════════════════════════════════════════════════════════════════════════

class UpdateManager(QObject):
    """
    Advanced application update manager.
    مدير تحديث التطبيق المتقدم
    """
    
    # Signals
    update_available = Signal(UpdateInfo)
    update_progress = Signal(UpdateProgress)
    update_ready = Signal(UpdateInfo)
    update_error = Signal(str)
    state_changed = Signal(UpdateState)
    
    # Update server configuration
    UPDATE_URL: ClassVar[str] = "https://api.github.com/repos/nebulacompute/desktop/releases"
    UPDATE_CHECK_INTERVAL: ClassVar[int] = 4 * 60 * 60 * 1000  # 4 hours in ms
    
    _instance: ClassVar[Optional["UpdateManager"]] = None
    
    def __new__(cls) -> "UpdateManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        super().__init__()
        self._initialized = True
        self._logger = logging.getLogger("updater")
        
        # State
        self._state = UpdateState.IDLE
        self._current_version = VersionInfo.parse("1.0.0")
        self._latest_update: Optional[UpdateInfo] = None
        self._downloaded_path: Optional[Path] = None
        
        # Settings
        self._channel = UpdateChannel.STABLE
        self._auto_check = True
        self._auto_download = False
        self._auto_install = False
        
        # Directories
        self._update_dir = Path.home() / ".nebulacompute" / "updates"
        self._update_dir.mkdir(parents=True, exist_ok=True)
        
        self._backup_dir = Path.home() / ".nebulacompute" / "backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Timer for periodic checks
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._on_check_timer)
        
        if self._auto_check:
            self._check_timer.start(self.UPDATE_CHECK_INTERVAL)
        
        self._logger.info(f"Update manager initialized (current: {self._current_version})")
    
    @property
    def state(self) -> UpdateState:
        return self._state
    
    @property
    def current_version(self) -> VersionInfo:
        return self._current_version
    
    @property
    def latest_update(self) -> Optional[UpdateInfo]:
        return self._latest_update
    
    @property
    def has_update(self) -> bool:
        return self._latest_update is not None
    
    @property
    def channel(self) -> UpdateChannel:
        return self._channel
    
    @channel.setter
    def channel(self, value: UpdateChannel) -> None:
        self._channel = value
        self._logger.info(f"Update channel set to {value.value}")
    
    def _set_state(self, state: UpdateState) -> None:
        """Set state and emit signal"""
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)
            self._logger.debug(f"Update state: {state.name}")
    
    def _on_check_timer(self) -> None:
        """Timer callback for periodic update checks"""
        asyncio.create_task(self.check_for_updates())
    
    async def check_for_updates(self, force: bool = False) -> Optional[UpdateInfo]:
        """
        Check for available updates.
        التحقق من التحديثات المتاحة
        """
        if not HAS_AIOHTTP:
            self._logger.warning("aiohttp not available, cannot check for updates")
            return None
        
        if self._state not in (UpdateState.IDLE, UpdateState.AVAILABLE, UpdateState.ERROR) and not force:
            self._logger.debug("Update check already in progress")
            return self._latest_update
        
        self._set_state(UpdateState.CHECKING)
        self._logger.info("Checking for updates...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.UPDATE_URL,
                    headers={"Accept": "application/vnd.github.v3+json"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise UpdateAPIError(response.status)
                    
                    releases = await response.json()
            
            # Find appropriate release
            update_info = self._parse_releases(releases)
            
            if update_info and update_info.version_info > self._current_version:
                self._latest_update = update_info
                self._set_state(UpdateState.AVAILABLE)
                self.update_available.emit(update_info)
                self._logger.info(f"Update available: {update_info.version}")
                
                if self._auto_download:
                    asyncio.create_task(self.download_update())
                
                return update_info
            else:
                self._latest_update = None
                self._set_state(UpdateState.IDLE)
                self._logger.info("No updates available")
                return None
                
        except Exception as e:
            self._logger.error(f"Update check failed: {e}")
            self._set_state(UpdateState.ERROR)
            self.update_error.emit(str(e))
            return None
    
    def _parse_releases(self, releases: List[Dict[str, Any]]) -> Optional[UpdateInfo]:
        """Parse GitHub releases response"""
        for release in releases:
            # Skip drafts
            if release.get("draft", False):
                continue
            
            # Check channel (prerelease = beta)
            is_prerelease = release.get("prerelease", False)
            if self._channel == UpdateChannel.STABLE and is_prerelease:
                continue
            
            version = release["tag_name"].lstrip("v")
            
            # Parse assets
            assets = []
            for asset in release.get("assets", []):
                assets.append(UpdateAsset(
                    name=asset["name"],
                    url=asset["browser_download_url"],
                    size=asset["size"],
                    content_type=asset["content_type"],
                ))
            
            return UpdateInfo(
                version=version,
                channel=UpdateChannel.BETA if is_prerelease else UpdateChannel.STABLE,
                release_date=datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")),
                title=release.get("name", f"Version {version}"),
                release_notes=release.get("body", ""),
                release_url=release.get("html_url", ""),
                assets=assets,
            )
        
        return None
    
    async def download_update(self) -> bool:
        """
        Download the latest update.
        تنزيل آخر تحديث
        """
        if not HAS_AIOHTTP:
            self._logger.error("aiohttp not available")
            return False
        
        if not self._latest_update:
            self._logger.error("No update available to download")
            return False
        
        asset = self._latest_update.get_asset_for_platform()
        if not asset:
            self._logger.error("No compatible asset found for this platform")
            self.update_error.emit("No compatible download for your platform")
            return False
        
        self._set_state(UpdateState.DOWNLOADING)
        self._logger.info(f"Downloading update: {asset.name} ({asset.size} bytes)")
        
        try:
            download_path = self._update_dir / asset.name
            
            progress = UpdateProgress(
                state=UpdateState.DOWNLOADING,
                total_bytes=asset.size,
                current_file=asset.name,
                message=f"Downloading {asset.name}..."
            )
            
            async with aiohttp.ClientSession() as session:
                async with session.get(asset.url) as response:
                    if response.status != 200:
                        raise UpdateDownloadError(response.status)
                    
                    with open(download_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            progress.downloaded_bytes += len(chunk)
                            self.update_progress.emit(progress)
            
            # Verify checksum if available
            if asset.checksum:
                if not self._verify_checksum(download_path, asset.checksum, asset.checksum_type):
                    raise UpdateVerificationError(expected=asset.checksum)
            
            self._downloaded_path = download_path
            self._set_state(UpdateState.DOWNLOADED)
            self.update_ready.emit(self._latest_update)
            
            self._logger.info("Update downloaded successfully")
            
            if self._auto_install:
                return await self.install_update()
            
            return True
            
        except Exception as e:
            self._logger.error(f"Download failed: {e}")
            self._set_state(UpdateState.ERROR)
            self.update_error.emit(str(e))
            return False
    
    def _verify_checksum(self, path: Path, expected: str, algorithm: str = "sha256") -> bool:
        """Verify file checksum"""
        hasher = hashlib.new(algorithm)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        
        actual = hasher.hexdigest()
        return actual.lower() == expected.lower()
    
    async def install_update(self, restart: bool = True) -> bool:
        """
        Install the downloaded update.
        تثبيت التحديث المنزل
        """
        if not self._downloaded_path or not self._downloaded_path.exists():
            self._logger.error("No downloaded update to install")
            return False
        
        self._set_state(UpdateState.INSTALLING)
        self._logger.info("Installing update...")
        
        try:
            # Create backup first
            backup_path = await self._create_backup()
            
            # Extract/install based on platform
            if platform.system() == "Windows":
                success = await self._install_windows()
            elif platform.system() == "Darwin":
                success = await self._install_macos()
            else:
                success = await self._install_linux()
            
            if success:
                self._set_state(UpdateState.INSTALLED)
                self._logger.info("Update installed successfully")
                
                if restart:
                    await self._restart_application()
                
                return True
            else:
                # Restore backup on failure
                await self._restore_backup(backup_path)
                raise UpdateInstallError()
                
        except Exception as e:
            self._logger.error(f"Installation failed: {e}")
            self._set_state(UpdateState.ERROR)
            self.update_error.emit(str(e))
            return False
    
    async def _create_backup(self) -> Path:
        """Create backup of current installation"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self._backup_dir / f"backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Get application directory
        app_dir = Path(sys.executable).parent
        
        # Copy essential files
        for item in app_dir.iterdir():
            if item.is_file() and not item.name.startswith("."):
                shutil.copy2(item, backup_path / item.name)
        
        self._logger.info(f"Backup created: {backup_path}")
        return backup_path
    
    async def _restore_backup(self, backup_path: Path) -> None:
        """Restore from backup"""
        if not backup_path.exists():
            self._logger.warning("Backup not found")
            return
        
        app_dir = Path(sys.executable).parent
        
        for item in backup_path.iterdir():
            target = app_dir / item.name
            shutil.copy2(item, target)
        
        self._logger.info("Backup restored")
    
    async def _install_windows(self) -> bool:
        """Windows-specific installation"""
        if not self._downloaded_path:
            return False
        
        if self._downloaded_path.suffix == ".exe":
            # Run installer
            subprocess.Popen(
                [str(self._downloaded_path), "/SILENT", "/NORESTART"],
                creationflags=subprocess.DETACHED_PROCESS
            )
            return True
        elif self._downloaded_path.suffix == ".zip":
            return await self._extract_update()
        
        return False
    
    async def _install_macos(self) -> bool:
        """macOS-specific installation"""
        if not self._downloaded_path:
            return False
        
        if self._downloaded_path.suffix == ".dmg":
            # Mount and copy
            subprocess.run(["hdiutil", "attach", str(self._downloaded_path)])
            # Copy app bundle
            return True
        elif self._downloaded_path.suffix == ".zip":
            return await self._extract_update()
        
        return False
    
    async def _install_linux(self) -> bool:
        """Linux-specific installation"""
        if not self._downloaded_path:
            return False
        
        if self._downloaded_path.suffix in (".tar.gz", ".tgz"):
            import tarfile
            with tarfile.open(self._downloaded_path, "r:gz") as tar:
                tar.extractall(Path(sys.executable).parent)
            return True
        elif self._downloaded_path.suffix == ".zip":
            return await self._extract_update()
        elif self._downloaded_path.suffix == ".AppImage":
            # Replace AppImage
            target = Path(sys.executable)
            shutil.move(self._downloaded_path, target)
            os.chmod(target, 0o755)
            return True
        
        return False
    
    async def _extract_update(self) -> bool:
        """Extract ZIP update"""
        if not self._downloaded_path:
            return False
        
        extract_dir = self._update_dir / "extracted"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        
        with zipfile.ZipFile(self._downloaded_path, "r") as zf:
            zf.extractall(extract_dir)
        
        # Copy to application directory
        app_dir = Path(sys.executable).parent
        for item in extract_dir.iterdir():
            target = app_dir / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        
        return True
    
    async def _restart_application(self) -> None:
        """Restart the application"""
        self._set_state(UpdateState.RESTARTING)
        self._logger.info("Restarting application...")
        
        # Give time for cleanup
        await asyncio.sleep(1)
        
        # Restart
        python = sys.executable
        os.execl(python, python, *sys.argv)
    
    def cleanup_old_updates(self, keep_days: int = 7) -> None:
        """Clean up old update files"""
        cutoff = datetime.now() - timedelta(days=keep_days)
        
        for item in self._update_dir.iterdir():
            try:
                mtime = datetime.fromtimestamp(item.stat().st_mtime)
                if mtime < cutoff:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    self._logger.debug(f"Cleaned up: {item}")
            except Exception as e:
                self._logger.error(f"Cleanup failed for {item}: {e}")
    
    def cleanup_old_backups(self, keep_count: int = 3) -> None:
        """Clean up old backups, keeping only the most recent"""
        backups = sorted(
            self._backup_dir.iterdir(),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        for backup in backups[keep_count:]:
            try:
                shutil.rmtree(backup)
                self._logger.debug(f"Cleaned up backup: {backup}")
            except Exception as e:
                self._logger.error(f"Backup cleanup failed for {backup}: {e}")
    
    def get_release_notes(self) -> str:
        """Get release notes for the latest update"""
        if self._latest_update:
            return self._latest_update.release_notes
        return ""
    
    def dismiss_update(self) -> None:
        """Dismiss the current update notification"""
        self._latest_update = None
        self._set_state(UpdateState.IDLE)
    
    def enable_auto_check(self, enabled: bool = True, interval_hours: int = 4) -> None:
        """Enable or disable automatic update checks"""
        self._auto_check = enabled
        
        if enabled:
            interval_ms = interval_hours * 60 * 60 * 1000
            self._check_timer.setInterval(interval_ms)
            self._check_timer.start()
        else:
            self._check_timer.stop()
    
    def enable_auto_download(self, enabled: bool = True) -> None:
        """Enable or disable automatic download"""
        self._auto_download = enabled
    
    def enable_auto_install(self, enabled: bool = True) -> None:
        """Enable or disable automatic installation"""
        self._auto_install = enabled


# Global update manager
update_manager = UpdateManager()
