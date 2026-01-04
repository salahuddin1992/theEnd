"""
Windows Terminal Integration - تكامل Windows Terminal
======================================================

Provides integration with Windows Terminal for:
- Creating custom terminal profiles
- Launching terminals with specific configurations
- PowerShell and CMD integration
- SSH session management

يوفر التكامل مع Windows Terminal:
- إنشاء ملفات تعريف مخصصة
- تشغيل الطرفيات بإعدادات محددة
- تكامل PowerShell و CMD
- إدارة جلسات SSH

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    pass


class TerminalType(str, Enum):
    """Terminal type enumeration"""
    WINDOWS_TERMINAL = "wt"
    POWERSHELL = "powershell"
    POWERSHELL_CORE = "pwsh"
    CMD = "cmd"
    WSL = "wsl"


@dataclass
class TerminalProfile:
    """
    Windows Terminal Profile Configuration
    إعدادات ملف تعريف Windows Terminal
    """
    name: str
    guid: str = ""
    command_line: str = ""
    starting_directory: str = "%USERPROFILE%"
    icon: str = ""
    color_scheme: str = "Campbell"
    font_face: str = "Cascadia Code"
    font_size: int = 12
    background_image: str = ""
    background_opacity: float = 1.0
    use_acrylic: bool = False
    acrylic_opacity: float = 0.8
    cursor_shape: str = "bar"
    hidden: bool = False
    tab_title: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Windows Terminal JSON format"""
        profile = {
            "name": self.name,
            "commandline": self.command_line,
            "startingDirectory": self.starting_directory,
            "colorScheme": self.color_scheme,
            "font": {
                "face": self.font_face,
                "size": self.font_size,
            },
            "hidden": self.hidden,
        }

        if self.guid:
            profile["guid"] = self.guid
        if self.icon:
            profile["icon"] = self.icon
        if self.background_image:
            profile["backgroundImage"] = self.background_image
            profile["backgroundImageOpacity"] = self.background_opacity
        if self.use_acrylic:
            profile["useAcrylic"] = True
            profile["acrylicOpacity"] = self.acrylic_opacity
        if self.tab_title:
            profile["tabTitle"] = self.tab_title
        if self.cursor_shape:
            profile["cursorShape"] = self.cursor_shape

        return profile


@dataclass
class TerminalSettings:
    """
    Windows Terminal Settings
    إعدادات Windows Terminal
    """
    default_profile: str = ""
    always_show_tabs: bool = True
    copy_on_select: bool = False
    confirm_close_all_tabs: bool = True
    theme: str = "dark"
    tab_width_mode: str = "titleLength"
    use_acrylic_in_tab_row: bool = False
    show_tabs_in_titlebar: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to settings format"""
        return {
            "defaultProfile": self.default_profile,
            "alwaysShowTabs": self.always_show_tabs,
            "copyOnSelect": self.copy_on_select,
            "confirmCloseAllTabs": self.confirm_close_all_tabs,
            "theme": self.theme,
            "tabWidthMode": self.tab_width_mode,
            "useAcrylicInTabRow": self.use_acrylic_in_tab_row,
            "showTabsInTitlebar": self.show_tabs_in_titlebar,
        }


class WindowsTerminalManager:
    """
    Windows Terminal Manager
    مدير Windows Terminal

    Manages Windows Terminal profiles and launching terminal sessions.
    """

    APP_NAME = "NebulaCompute"
    PROFILE_GUID = "{dc714688-f8b3-4c3a-9a22-1b2c4d5e6f7a}"

    def __init__(self):
        self._wt_path: Optional[Path] = None
        self._settings_path: Optional[Path] = None
        self._profiles: List[TerminalProfile] = []

        if IS_WINDOWS:
            self._find_windows_terminal()
            self._find_settings_path()

    def _find_windows_terminal(self) -> None:
        """Find Windows Terminal executable"""
        # Check common locations
        locations = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "wt.exe",
            Path("C:/Program Files/WindowsApps/Microsoft.WindowsTerminal_*/wt.exe"),
        ]

        for loc in locations:
            if "*" in str(loc):
                # Handle glob patterns
                parent = loc.parent
                if parent.exists():
                    matches = list(parent.glob(loc.name))
                    if matches:
                        self._wt_path = matches[0]
                        return
            elif loc.exists():
                self._wt_path = loc
                return

        # Try to find via PATH
        try:
            result = subprocess.run(
                ["where", "wt.exe"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                path = result.stdout.strip().split("\n")[0]
                self._wt_path = Path(path)
        except Exception:
            pass

    def _find_settings_path(self) -> None:
        """Find Windows Terminal settings.json"""
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))

        # Windows Terminal (Store version)
        store_path = (
            local_app_data / "Packages" / "Microsoft.WindowsTerminal_8wekyb3d8bbwe"
            / "LocalState" / "settings.json"
        )
        if store_path.exists():
            self._settings_path = store_path
            return

        # Windows Terminal Preview
        preview_path = (
            local_app_data / "Packages" / "Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe"
            / "LocalState" / "settings.json"
        )
        if preview_path.exists():
            self._settings_path = preview_path
            return

        # Scoop or other installations
        roaming = Path(os.environ.get("APPDATA", ""))
        alt_path = roaming / "Microsoft" / "Windows Terminal" / "settings.json"
        if alt_path.exists():
            self._settings_path = alt_path

    @property
    def is_available(self) -> bool:
        """Check if Windows Terminal is available"""
        return self._wt_path is not None and self._wt_path.exists()

    def create_cluster_profile(self) -> TerminalProfile:
        """
        Create a custom profile for the distributed cluster
        إنشاء ملف تعريف مخصص للكلاستر
        """
        python_path = sys.executable

        return TerminalProfile(
            name=f"{self.APP_NAME} Console",
            guid=self.PROFILE_GUID,
            command_line=f'"{python_path}" -m distributed_cluster.cli.interactive',
            starting_directory="%USERPROFILE%",
            icon="🚀",
            color_scheme="One Half Dark",
            font_face="Cascadia Code PL",
            font_size=11,
            use_acrylic=True,
            acrylic_opacity=0.85,
            cursor_shape="filledBox",
            tab_title=self.APP_NAME,
        )

    def create_ssh_profile(
        self,
        name: str,
        host: str,
        user: str = "",
        port: int = 22,
        identity_file: str = "",
    ) -> TerminalProfile:
        """
        Create SSH connection profile
        إنشاء ملف تعريف اتصال SSH
        """
        ssh_cmd = "ssh"
        if user:
            ssh_cmd += f" {user}@{host}"
        else:
            ssh_cmd += f" {host}"

        if port != 22:
            ssh_cmd += f" -p {port}"

        if identity_file:
            ssh_cmd += f' -i "{identity_file}"'

        import uuid
        guid = "{" + str(uuid.uuid4()) + "}"

        return TerminalProfile(
            name=f"SSH: {name}",
            guid=guid,
            command_line=ssh_cmd,
            icon="🔐",
            color_scheme="Campbell",
            tab_title=f"SSH: {name}",
        )

    def install_profile(self, profile: TerminalProfile) -> bool:
        """
        Install profile to Windows Terminal settings
        تثبيت ملف التعريف في إعدادات Windows Terminal
        """
        if not self._settings_path or not self._settings_path.exists():
            return False

        try:
            # Read current settings
            with open(self._settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)

            # Get profiles list
            profiles = settings.get("profiles", {})
            if isinstance(profiles, dict):
                profile_list = profiles.get("list", [])
            else:
                profile_list = profiles

            # Check if profile already exists
            profile_dict = profile.to_dict()
            existing_idx = None
            for idx, p in enumerate(profile_list):
                if p.get("guid") == profile.guid or p.get("name") == profile.name:
                    existing_idx = idx
                    break

            if existing_idx is not None:
                # Update existing profile
                profile_list[existing_idx] = profile_dict
            else:
                # Add new profile
                profile_list.append(profile_dict)

            # Update settings
            if isinstance(profiles, dict):
                profiles["list"] = profile_list
            else:
                settings["profiles"] = {"list": profile_list}

            # Write back
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)

            return True

        except Exception as e:
            print(f"Error installing profile: {e}")
            return False

    def uninstall_profile(self, profile_name: str) -> bool:
        """
        Remove profile from Windows Terminal settings
        إزالة ملف التعريف من إعدادات Windows Terminal
        """
        if not self._settings_path or not self._settings_path.exists():
            return False

        try:
            with open(self._settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)

            profiles = settings.get("profiles", {})
            if isinstance(profiles, dict):
                profile_list = profiles.get("list", [])
            else:
                profile_list = profiles

            # Remove matching profile
            profile_list = [p for p in profile_list if p.get("name") != profile_name]

            if isinstance(profiles, dict):
                profiles["list"] = profile_list
            else:
                settings["profiles"] = {"list": profile_list}

            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)

            return True

        except Exception:
            return False

    def launch_terminal(
        self,
        profile: Optional[str] = None,
        command: Optional[str] = None,
        working_dir: Optional[str] = None,
        new_tab: bool = False,
        split: Optional[str] = None,  # "horizontal" or "vertical"
        title: Optional[str] = None,
    ) -> bool:
        """
        Launch Windows Terminal with options
        تشغيل Windows Terminal مع الخيارات

        Args:
            profile: Profile name or GUID
            command: Command to run
            working_dir: Starting directory
            new_tab: Open in new tab
            split: Split pane direction
            title: Tab/window title
        """
        if not self.is_available:
            return False

        args = [str(self._wt_path)]

        if new_tab:
            args.append("new-tab")
        elif split:
            args.append("split-pane")
            args.extend(["-H" if split == "horizontal" else "-V"])

        if profile:
            args.extend(["-p", profile])

        if working_dir:
            args.extend(["-d", working_dir])

        if title:
            args.extend(["--title", title])

        if command:
            args.append(command)

        try:
            subprocess.Popen(args, shell=False)
            return True
        except Exception as e:
            print(f"Error launching terminal: {e}")
            return False

    def launch_powershell(
        self,
        command: Optional[str] = None,
        admin: bool = False,
        core: bool = True,
        working_dir: Optional[str] = None,
    ) -> bool:
        """
        Launch PowerShell
        تشغيل PowerShell

        Args:
            command: Command to execute
            admin: Run as administrator
            core: Use PowerShell Core (pwsh) if available
            working_dir: Working directory
        """
        ps_exe = "pwsh" if core else "powershell"

        args = [ps_exe]

        if command:
            args.extend(["-Command", command])

        if working_dir:
            args.extend(["-WorkingDirectory", working_dir])

        try:
            if admin and IS_WINDOWS:
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    ps_exe,
                    " ".join(args[1:]) if len(args) > 1 else "",
                    working_dir or "",
                    1,  # SW_SHOWNORMAL
                )
            else:
                subprocess.Popen(args, shell=False)
            return True
        except Exception as e:
            print(f"Error launching PowerShell: {e}")
            return False

    async def run_command_async(
        self,
        command: str,
        shell: TerminalType = TerminalType.POWERSHELL_CORE,
        timeout: float = 60.0,
    ) -> tuple[int, str, str]:
        """
        Run command asynchronously
        تشغيل أمر بشكل غير متزامن

        Args:
            command: Command to run
            shell: Shell type to use
            timeout: Timeout in seconds

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        shell_cmd = {
            TerminalType.POWERSHELL: ["powershell", "-Command"],
            TerminalType.POWERSHELL_CORE: ["pwsh", "-Command"],
            TerminalType.CMD: ["cmd", "/c"],
            TerminalType.WSL: ["wsl", "--"],
        }.get(shell, ["powershell", "-Command"])

        full_cmd = shell_cmd + [command]

        try:
            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            return (
                process.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )

        except asyncio.TimeoutError:
            process.kill()
            return (-1, "", "Command timed out")
        except Exception as e:
            return (-1, "", str(e))

    def get_installed_profiles(self) -> List[Dict[str, Any]]:
        """
        Get list of installed Windows Terminal profiles
        الحصول على قائمة ملفات التعريف المثبتة
        """
        if not self._settings_path or not self._settings_path.exists():
            return []

        try:
            with open(self._settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)

            profiles = settings.get("profiles", {})
            if isinstance(profiles, dict):
                return profiles.get("list", [])
            return profiles

        except Exception:
            return []

    def get_status(self) -> Dict[str, Any]:
        """Get terminal manager status"""
        return {
            "available": self.is_available,
            "wt_path": str(self._wt_path) if self._wt_path else None,
            "settings_path": str(self._settings_path) if self._settings_path else None,
            "profiles_count": len(self.get_installed_profiles()),
        }
