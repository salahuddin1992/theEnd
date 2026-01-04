"""
Windows 11 Integration Module
تكامل ويندوز 11

Comprehensive Windows 11 integration featuring:
- Native Toast Notifications
- Taskbar Progress Indicator
- Jump Lists
- System Tray Integration
- Dark Mode Detection
- Windows Registry Integration
- Startup Registration
- File Associations
- Windows Credential Manager
"""

from __future__ import annotations

import ctypes
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QSettings, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

# Windows-specific imports (conditionally loaded)
IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    try:
        import ctypes.wintypes  # noqa: F401
        import winreg
        from ctypes import byref, c_int, sizeof, windll  # noqa: F401
        HAS_WINREG = True
    except ImportError:
        HAS_WINREG = False

    try:
        # Windows Toast Notifications
        from win10toast_click import ToastNotifier
        HAS_TOAST = True
    except ImportError:
        try:
            from win10toast import ToastNotifier
            HAS_TOAST = True
        except ImportError:
            HAS_TOAST = False

    try:
        # Windows Credential Manager
        import keyring
        HAS_KEYRING = True
    except ImportError:
        HAS_KEYRING = False

    try:
        # Taskbar COM interfaces
        import comtypes  # noqa: F401
        from comtypes import GUID  # noqa: F401
        from comtypes.client import CreateObject  # noqa: F401
        HAS_COMTYPES = True
    except ImportError:
        HAS_COMTYPES = False
else:
    HAS_WINREG = False
    HAS_TOAST = False
    HAS_KEYRING = False
    HAS_COMTYPES = False


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

APP_ID = "NebulaCompute.Desktop"
APP_NAME = "NebulaCompute"
COMPANY_NAME = "NebulaCompute"


class TaskbarProgressState(Enum):
    """Taskbar progress indicator states"""
    NO_PROGRESS = 0
    INDETERMINATE = 1
    NORMAL = 2
    ERROR = 4
    PAUSED = 8


class NotificationType(Enum):
    """Windows notification types"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class JumpListItem:
    """Jump list item definition"""
    title: str
    path: str
    arguments: str = ""
    icon_path: str = ""
    description: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# DARK MODE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

class WindowsThemeDetector(QObject):
    """
    Detects Windows system theme (dark/light mode).
    كشف سمة نظام ويندوز
    """

    theme_changed = Signal(bool)  # True = dark mode

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = self._detect_dark_mode()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_theme_change)
        self._timer.start(1000)  # Check every second

    def _detect_dark_mode(self) -> bool:
        """Detect if Windows is using dark mode"""
        if not IS_WINDOWS or not HAS_WINREG:
            return True  # Default to dark

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0  # 0 = dark mode, 1 = light mode
        except Exception:
            return True

    def _check_theme_change(self):
        """Check if theme has changed"""
        current = self._detect_dark_mode()
        if current != self._is_dark:
            self._is_dark = current
            self.theme_changed.emit(current)

    @property
    def is_dark_mode(self) -> bool:
        """Get current dark mode state"""
        return self._is_dark

    def stop_monitoring(self):
        """Stop theme monitoring"""
        self._timer.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# WINDOWS TOAST NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════════════

class WindowsToastNotifications(QObject):
    """
    Native Windows 11 Toast Notifications.
    إشعارات ويندوز 11 الأصلية
    """

    notification_clicked = Signal(str)  # notification_id
    notification_dismissed = Signal(str)

    def __init__(self, app_id: str = APP_ID, parent=None):
        super().__init__(parent)
        self._app_id = app_id
        self._notifier = None

        if IS_WINDOWS and HAS_TOAST:
            try:
                self._notifier = ToastNotifier()
            except Exception:
                pass

        # Fallback icon path
        self._icon_path = self._get_icon_path()

    def _get_icon_path(self) -> str:
        """Get application icon path"""
        # Look for icon in common locations
        possible_paths = [
            Path(__file__).parent / "assets" / "icon.ico",
            Path(__file__).parent.parent / "assets" / "icon.ico",
            Path(__file__).parent.parent.parent / "assets" / "icon.ico",
        ]
        for path in possible_paths:
            if path.exists():
                return str(path)
        return ""

    def show(
        self,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        duration: int = 5,
        callback: Optional[Callable] = None,
        icon_path: str = None
    ) -> bool:
        """
        Show a Windows toast notification.

        Args:
            title: Notification title
            message: Notification message
            notification_type: Type of notification
            duration: Duration in seconds
            callback: Optional callback when clicked
            icon_path: Optional custom icon path

        Returns:
            True if notification was shown
        """
        if not IS_WINDOWS or not self._notifier:
            return False

        try:
            icon = icon_path or self._icon_path

            # Use threaded notification to avoid blocking
            self._notifier.show_toast(
                title,
                message,
                icon_path=icon if icon else None,
                duration=duration,
                threaded=True,
                callback_on_click=callback
            )
            return True
        except Exception as e:
            print(f"Toast notification error: {e}")
            return False

    def show_info(self, title: str, message: str, **kwargs):
        """Show info notification"""
        return self.show(title, message, NotificationType.INFO, **kwargs)

    def show_success(self, title: str, message: str, **kwargs):
        """Show success notification"""
        return self.show(title, message, NotificationType.SUCCESS, **kwargs)

    def show_warning(self, title: str, message: str, **kwargs):
        """Show warning notification"""
        return self.show(title, message, NotificationType.WARNING, **kwargs)

    def show_error(self, title: str, message: str, **kwargs):
        """Show error notification"""
        return self.show(title, message, NotificationType.ERROR, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# TASKBAR PROGRESS
# ═══════════════════════════════════════════════════════════════════════════════

class TaskbarProgress(QObject):
    """
    Windows Taskbar Progress Indicator.
    مؤشر التقدم في شريط المهام
    """

    def __init__(self, window_handle: int = None, parent=None):
        super().__init__(parent)
        self._hwnd = window_handle
        self._taskbar = None
        self._state = TaskbarProgressState.NO_PROGRESS
        self._value = 0

        if IS_WINDOWS:
            self._init_taskbar()

    def _init_taskbar(self):
        """Initialize taskbar COM interface"""
        if not HAS_COMTYPES:
            return

        try:
            # ITaskbarList3 GUID
            CLSID_TaskbarList = GUID("{56FDF344-FD6D-11d0-958A-006097C9A090}")
            self._taskbar = CreateObject(CLSID_TaskbarList)
            if hasattr(self._taskbar, 'HrInit'):
                self._taskbar.HrInit()
        except Exception as e:
            print(f"Taskbar init error: {e}")
            self._taskbar = None

    def set_window(self, window: QWidget):
        """Set the window for taskbar progress"""
        if IS_WINDOWS and window:
            self._hwnd = int(window.winId())

    def set_progress(self, value: int, maximum: int = 100):
        """
        Set progress value (0-100 by default).

        Args:
            value: Current progress value
            maximum: Maximum value (default 100)
        """
        if not IS_WINDOWS or not self._taskbar or not self._hwnd:
            return

        try:
            self._value = value
            self._state = TaskbarProgressState.NORMAL

            if hasattr(self._taskbar, 'SetProgressValue'):
                self._taskbar.SetProgressValue(self._hwnd, value, maximum)
            if hasattr(self._taskbar, 'SetProgressState'):
                self._taskbar.SetProgressState(self._hwnd, self._state.value)
        except Exception as e:
            print(f"Taskbar progress error: {e}")

    def set_state(self, state: TaskbarProgressState):
        """Set progress state"""
        if not IS_WINDOWS or not self._taskbar or not self._hwnd:
            return

        try:
            self._state = state
            if hasattr(self._taskbar, 'SetProgressState'):
                self._taskbar.SetProgressState(self._hwnd, state.value)
        except Exception:
            pass

    def set_indeterminate(self):
        """Set indeterminate progress (spinning)"""
        self.set_state(TaskbarProgressState.INDETERMINATE)

    def set_error(self):
        """Set error state (red progress)"""
        self.set_state(TaskbarProgressState.ERROR)

    def set_paused(self):
        """Set paused state (yellow progress)"""
        self.set_state(TaskbarProgressState.PAUSED)

    def clear(self):
        """Clear progress indicator"""
        self.set_state(TaskbarProgressState.NO_PROGRESS)


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM TRAY
# ═══════════════════════════════════════════════════════════════════════════════

class FluentSystemTray(QObject):
    """
    Windows 11 System Tray Integration.
    تكامل علبة النظام
    """

    activated = Signal()  # Double-click
    show_window = Signal()
    hide_window = Signal()
    quit_requested = Signal()
    action_triggered = Signal(str)  # Action name

    def __init__(self, parent=None):
        super().__init__(parent)

        self._tray = QSystemTrayIcon(parent)
        self._menu = QMenu()
        self._actions: Dict[str, QAction] = {}

        self._setup_default_menu()
        self._setup_signals()

    def _setup_default_menu(self):
        """Setup default tray menu"""
        # Show action
        show_action = QAction("Show NebulaCompute", self._menu)
        show_action.triggered.connect(self.show_window.emit)
        self._menu.addAction(show_action)
        self._actions["show"] = show_action

        # Hide action
        hide_action = QAction("Hide to Tray", self._menu)
        hide_action.triggered.connect(self.hide_window.emit)
        self._menu.addAction(hide_action)
        self._actions["hide"] = hide_action

        self._menu.addSeparator()

        # Status submenu
        status_menu = self._menu.addMenu("Status")
        status_menu.addAction("Connected to cluster")
        status_menu.addAction("3 active jobs")
        status_menu.addAction("5 workers online")

        self._menu.addSeparator()

        # Quick actions
        quick_menu = self._menu.addMenu("Quick Actions")

        submit_action = QAction("Submit New Job", quick_menu)
        submit_action.triggered.connect(lambda: self.action_triggered.emit("submit_job"))
        quick_menu.addAction(submit_action)

        refresh_action = QAction("Refresh Status", quick_menu)
        refresh_action.triggered.connect(lambda: self.action_triggered.emit("refresh"))
        quick_menu.addAction(refresh_action)

        self._menu.addSeparator()

        # Settings action
        settings_action = QAction("Settings", self._menu)
        settings_action.triggered.connect(lambda: self.action_triggered.emit("settings"))
        self._menu.addAction(settings_action)
        self._actions["settings"] = settings_action

        self._menu.addSeparator()

        # Quit action
        quit_action = QAction("Quit", self._menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(quit_action)
        self._actions["quit"] = quit_action

        self._tray.setContextMenu(self._menu)

    def _setup_signals(self):
        """Setup tray signals"""
        self._tray.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """Handle tray activation"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.activated.emit()
            self.show_window.emit()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single click - show menu on some systems
            pass

    def set_icon(self, icon: QIcon):
        """Set tray icon"""
        self._tray.setIcon(icon)

    def set_icon_from_path(self, path: str):
        """Set tray icon from file path"""
        self._tray.setIcon(QIcon(path))

    def set_tooltip(self, tooltip: str):
        """Set tray tooltip"""
        self._tray.setToolTip(tooltip)

    def show(self):
        """Show tray icon"""
        self._tray.show()

    def hide(self):
        """Hide tray icon"""
        self._tray.hide()

    def show_message(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
        timeout: int = 5000
    ):
        """Show tray balloon message"""
        self._tray.showMessage(title, message, icon, timeout)

    def add_action(self, name: str, text: str, callback: Callable = None) -> QAction:
        """Add custom action to menu"""
        action = QAction(text, self._menu)
        if callback:
            action.triggered.connect(callback)
        else:
            action.triggered.connect(lambda: self.action_triggered.emit(name))

        # Insert before quit
        if "quit" in self._actions:
            self._menu.insertAction(self._actions["quit"], action)
        else:
            self._menu.addAction(action)

        self._actions[name] = action
        return action

    def update_status(self, connected: bool, jobs: int, workers: int):
        """Update status in menu"""
        # Would update the status submenu dynamically
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# WINDOWS REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

class WindowsRegistry:
    """
    Windows Registry Operations.
    عمليات سجل ويندوز
    """

    @staticmethod
    def set_startup(enabled: bool, app_path: str = None) -> bool:
        """
        Set application to run at Windows startup.

        Args:
            enabled: Enable or disable startup
            app_path: Path to executable (defaults to current)

        Returns:
            True if successful
        """
        if not IS_WINDOWS or not HAS_WINREG:
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
            )

            if enabled:
                path = app_path or sys.executable
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{path}"')
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass

            winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f"Registry error: {e}")
            return False

    @staticmethod
    def is_startup_enabled() -> bool:
        """Check if startup is enabled"""
        if not IS_WINDOWS or not HAS_WINREG:
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_QUERY_VALUE
            )
            try:
                winreg.QueryValueEx(key, APP_NAME)
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        except Exception:
            return False

    @staticmethod
    def register_file_association(extension: str, description: str, icon_path: str = None) -> bool:
        """
        Register file association.

        Args:
            extension: File extension (e.g., ".ncjob")
            description: File type description
            icon_path: Optional icon path

        Returns:
            True if successful
        """
        if not IS_WINDOWS or not HAS_WINREG:
            return False

        try:
            prog_id = f"{APP_NAME}.{extension.lstrip('.')}"
            exe_path = sys.executable

            # Create extension key
            ext_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{extension}")
            winreg.SetValueEx(ext_key, "", 0, winreg.REG_SZ, prog_id)
            winreg.CloseKey(ext_key)

            # Create ProgID key
            prog_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}")
            winreg.SetValueEx(prog_key, "", 0, winreg.REG_SZ, description)
            winreg.CloseKey(prog_key)

            # Set icon
            if icon_path:
                icon_key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    f"Software\\Classes\\{prog_id}\\DefaultIcon"
                )
                winreg.SetValueEx(icon_key, "", 0, winreg.REG_SZ, icon_path)
                winreg.CloseKey(icon_key)

            # Set open command
            cmd_key = winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                f"Software\\Classes\\{prog_id}\\shell\\open\\command"
            )
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, f'"{exe_path}" "%1"')
            winreg.CloseKey(cmd_key)

            return True
        except Exception as e:
            print(f"File association error: {e}")
            return False

    @staticmethod
    def save_setting(key: str, value: Any) -> bool:
        """Save setting to registry"""
        if not IS_WINDOWS or not HAS_WINREG:
            return False

        try:
            reg_key = winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                f"Software\\{COMPANY_NAME}\\{APP_NAME}"
            )

            if isinstance(value, bool):
                winreg.SetValueEx(reg_key, key, 0, winreg.REG_DWORD, int(value))
            elif isinstance(value, int):
                winreg.SetValueEx(reg_key, key, 0, winreg.REG_DWORD, value)
            elif isinstance(value, str):
                winreg.SetValueEx(reg_key, key, 0, winreg.REG_SZ, value)
            else:
                # Serialize as JSON
                winreg.SetValueEx(reg_key, key, 0, winreg.REG_SZ, json.dumps(value))

            winreg.CloseKey(reg_key)
            return True
        except Exception:
            return False

    @staticmethod
    def load_setting(key: str, default: Any = None) -> Any:
        """Load setting from registry"""
        if not IS_WINDOWS or not HAS_WINREG:
            return default

        try:
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                f"Software\\{COMPANY_NAME}\\{APP_NAME}",
                0,
                winreg.KEY_QUERY_VALUE
            )
            value, reg_type = winreg.QueryValueEx(reg_key, key)
            winreg.CloseKey(reg_key)

            if reg_type == winreg.REG_DWORD:
                return value
            elif reg_type == winreg.REG_SZ:
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    return value

            return value
        except Exception:
            return default


# ═══════════════════════════════════════════════════════════════════════════════
# CREDENTIAL MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class WindowsCredentialManager:
    """
    Windows Credential Manager Integration.
    تكامل مدير بيانات الاعتماد
    """

    SERVICE_NAME = APP_ID

    @staticmethod
    def save_credential(username: str, password: str, service: str = None) -> bool:
        """
        Save credential to Windows Credential Manager.

        Args:
            username: Username/key
            password: Password/secret
            service: Optional service name

        Returns:
            True if successful
        """
        if not HAS_KEYRING:
            return False

        try:
            service = service or WindowsCredentialManager.SERVICE_NAME
            keyring.set_password(service, username, password)
            return True
        except Exception as e:
            print(f"Credential save error: {e}")
            return False

    @staticmethod
    def get_credential(username: str, service: str = None) -> Optional[str]:
        """
        Get credential from Windows Credential Manager.

        Args:
            username: Username/key
            service: Optional service name

        Returns:
            Password/secret or None
        """
        if not HAS_KEYRING:
            return None

        try:
            service = service or WindowsCredentialManager.SERVICE_NAME
            return keyring.get_password(service, username)
        except Exception:
            return None

    @staticmethod
    def delete_credential(username: str, service: str = None) -> bool:
        """
        Delete credential from Windows Credential Manager.

        Args:
            username: Username/key
            service: Optional service name

        Returns:
            True if successful
        """
        if not HAS_KEYRING:
            return False

        try:
            service = service or WindowsCredentialManager.SERVICE_NAME
            keyring.delete_password(service, username)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# JUMP LISTS
# ═══════════════════════════════════════════════════════════════════════════════

class WindowsJumpList:
    """
    Windows 11 Jump List Integration.
    قائمة الانتقال السريع
    """

    def __init__(self):
        self._tasks: List[JumpListItem] = []
        self._recent: List[JumpListItem] = []

    def add_task(self, item: JumpListItem):
        """Add task to jump list"""
        self._tasks.append(item)

    def add_recent(self, item: JumpListItem):
        """Add recent item to jump list"""
        self._recent.append(item)

    def clear_recent(self):
        """Clear recent items"""
        self._recent.clear()

    def apply(self) -> bool:
        """Apply jump list changes"""
        if not IS_WINDOWS:
            return False

        # Note: Full implementation requires COM interface
        # This is a simplified version using QSettings for recent files
        settings = QSettings(COMPANY_NAME, APP_NAME)
        settings.beginGroup("JumpList")

        # Save recent files
        recent_data = [
            {
                "title": item.title,
                "path": item.path,
                "arguments": item.arguments
            }
            for item in self._recent[:10]  # Max 10 recent
        ]
        settings.setValue("recent", json.dumps(recent_data))

        settings.endGroup()
        return True

    @staticmethod
    def get_recent() -> List[JumpListItem]:
        """Get recent items"""
        settings = QSettings(COMPANY_NAME, APP_NAME)
        settings.beginGroup("JumpList")

        try:
            data = json.loads(settings.value("recent", "[]"))
            items = [
                JumpListItem(
                    title=item.get("title", ""),
                    path=item.get("path", ""),
                    arguments=item.get("arguments", "")
                )
                for item in data
            ]
        except Exception:
            items = []

        settings.endGroup()
        return items


# ═══════════════════════════════════════════════════════════════════════════════
# WINDOWS 11 VISUAL EFFECTS
# ═══════════════════════════════════════════════════════════════════════════════

class Windows11Effects:
    """
    Windows 11 Visual Effects API.
    تأثيرات ويندوز 11 المرئية
    """

    # DWM attribute constants
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWA_MICA_EFFECT = 1029
    DWMWA_SYSTEMBACKDROP_TYPE = 38

    # Window corner preferences
    DWMWCP_DEFAULT = 0
    DWMWCP_DONOTROUND = 1
    DWMWCP_ROUND = 2
    DWMWCP_ROUNDSMALL = 3

    # System backdrop types
    DWMSBT_AUTO = 0
    DWMSBT_NONE = 1
    DWMSBT_MAINWINDOW = 2  # Mica
    DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
    DWMSBT_TABBEDWINDOW = 4  # Tabbed

    @staticmethod
    def enable_dark_mode(hwnd: int, enable: bool = True) -> bool:
        """Enable/disable dark mode for window"""
        if not IS_WINDOWS:
            return False

        try:
            value = c_int(1 if enable else 0)
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                Windows11Effects.DWMWA_USE_IMMERSIVE_DARK_MODE,
                byref(value),
                sizeof(value)
            )
            return True
        except Exception:
            return False

    @staticmethod
    def set_window_corners(hwnd: int, rounded: bool = True, small: bool = False) -> bool:
        """Set window corner style"""
        if not IS_WINDOWS:
            return False

        try:
            if rounded:
                pref = Windows11Effects.DWMWCP_ROUNDSMALL if small else Windows11Effects.DWMWCP_ROUND
            else:
                pref = Windows11Effects.DWMWCP_DONOTROUND

            value = c_int(pref)
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                Windows11Effects.DWMWA_WINDOW_CORNER_PREFERENCE,
                byref(value),
                sizeof(value)
            )
            return True
        except Exception:
            return False

    @staticmethod
    def enable_mica(hwnd: int) -> bool:
        """Enable Mica backdrop effect"""
        if not IS_WINDOWS:
            return False

        try:
            value = c_int(Windows11Effects.DWMSBT_MAINWINDOW)
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                Windows11Effects.DWMWA_SYSTEMBACKDROP_TYPE,
                byref(value),
                sizeof(value)
            )
            return True
        except Exception:
            return False

    @staticmethod
    def enable_acrylic(hwnd: int) -> bool:
        """Enable Acrylic backdrop effect"""
        if not IS_WINDOWS:
            return False

        try:
            value = c_int(Windows11Effects.DWMSBT_TRANSIENTWINDOW)
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                Windows11Effects.DWMWA_SYSTEMBACKDROP_TYPE,
                byref(value),
                sizeof(value)
            )
            return True
        except Exception:
            return False

    @staticmethod
    def disable_backdrop(hwnd: int) -> bool:
        """Disable backdrop effects"""
        if not IS_WINDOWS:
            return False

        try:
            value = c_int(Windows11Effects.DWMSBT_NONE)
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                Windows11Effects.DWMWA_SYSTEMBACKDROP_TYPE,
                byref(value),
                sizeof(value)
            )
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATED WINDOWS MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class WindowsIntegrationManager(QObject):
    """
    Unified Windows 11 Integration Manager.
    مدير تكامل ويندوز 11 الموحد

    Provides a single interface for all Windows 11 features.
    """

    theme_changed = Signal(bool)
    tray_activated = Signal()
    notification_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Components
        self.theme_detector = WindowsThemeDetector(self)
        self.notifications = WindowsToastNotifications(parent=self)
        self.taskbar = TaskbarProgress(parent=self)
        self.tray = FluentSystemTray(parent=self)
        self.jump_list = WindowsJumpList()
        self.registry = WindowsRegistry()
        self.credentials = WindowsCredentialManager()
        self.effects = Windows11Effects()

        # Connect signals
        self.theme_detector.theme_changed.connect(self.theme_changed.emit)
        self.tray.activated.connect(self.tray_activated.emit)

    def setup_for_window(self, window: QWidget):
        """
        Setup all integrations for a window.

        Args:
            window: Main application window
        """
        if not IS_WINDOWS:
            return

        hwnd = int(window.winId())

        # Setup taskbar
        self.taskbar.set_window(window)

        # Apply Windows 11 effects
        self.effects.enable_dark_mode(hwnd, self.theme_detector.is_dark_mode)
        self.effects.set_window_corners(hwnd, rounded=True)
        self.effects.enable_mica(hwnd)

        # Setup tray
        self.tray.set_tooltip(f"{APP_NAME} - Distributed Computing")
        self.tray.show()

    def show_notification(
        self,
        title: str,
        message: str,
        notification_type: str = "info"
    ):
        """Show a system notification"""
        type_map = {
            "info": NotificationType.INFO,
            "success": NotificationType.SUCCESS,
            "warning": NotificationType.WARNING,
            "error": NotificationType.ERROR
        }
        nt = type_map.get(notification_type, NotificationType.INFO)
        self.notifications.show(title, message, nt)

    def set_progress(self, value: int, maximum: int = 100):
        """Set taskbar progress"""
        self.taskbar.set_progress(value, maximum)

    def clear_progress(self):
        """Clear taskbar progress"""
        self.taskbar.clear()

    @property
    def is_dark_mode(self) -> bool:
        """Get current theme mode"""
        return self.theme_detector.is_dark_mode

    def cleanup(self):
        """Cleanup resources"""
        self.theme_detector.stop_monitoring()
        self.tray.hide()
        self.taskbar.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Main manager
    "WindowsIntegrationManager",

    # Components
    "WindowsThemeDetector",
    "WindowsToastNotifications",
    "TaskbarProgress",
    "FluentSystemTray",
    "WindowsRegistry",
    "WindowsCredentialManager",
    "WindowsJumpList",
    "Windows11Effects",

    # Types
    "TaskbarProgressState",
    "NotificationType",
    "JumpListItem",

    # Constants
    "IS_WINDOWS",
    "APP_ID",
    "APP_NAME",
]
