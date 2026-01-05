"""
Auto Start Manager - مدير التشغيل التلقائي
==========================================

Windows Auto-Start Manager
--------------------------

This module provides Windows auto-start functionality
using the Windows Registry and Task Scheduler.

يوفر هذا الملف إدارة التشغيل التلقائي لـ Windows:
- Windows Registry startup entries
- Task Scheduler integration
- Service installation support
- Startup delay configuration

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Check for Windows
import platform

IS_WINDOWS = platform.system() == "Windows"


class StartupMethod(str, Enum):
    """طريقة التشغيل التلقائي / Auto-start method"""

    REGISTRY = "registry"  # Windows Registry
    TASK_SCHEDULER = "task_scheduler"  # Task Scheduler
    STARTUP_FOLDER = "startup_folder"  # Startup folder shortcut
    SERVICE = "service"  # Windows Service


class StartupTrigger(str, Enum):
    """محفز التشغيل / Startup trigger"""

    LOGON = "logon"  # عند تسجيل الدخول
    BOOT = "boot"  # عند بدء التشغيل
    NETWORK = "network"  # عند الاتصال بالشبكة


@dataclass
class StartupConfig:
    """
    إعدادات التشغيل التلقائي
    Auto-start configuration
    """

    enabled: bool = True
    method: StartupMethod = StartupMethod.REGISTRY
    trigger: StartupTrigger = StartupTrigger.LOGON
    delay_seconds: int = 0
    run_as_admin: bool = False
    hidden: bool = False
    description: str = "Distributed Cluster Desktop"


class AutoStartManager:
    """
    مدير التشغيل التلقائي لـ Windows
    Windows Auto-Start Manager

    يوفر واجهة موحدة لإدارة التشغيل التلقائي
    عبر Registry و Task Scheduler.

    Provides unified interface for managing auto-start
    via Registry and Task Scheduler.
    """

    # Registry paths
    REGISTRY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    REGISTRY_RUN_ONCE_KEY = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"

    # Application info
    APP_NAME = "DistributedCluster"
    APP_DISPLAY_NAME = "Distributed Cluster Desktop"

    def __init__(
        self,
        app_name: Optional[str] = None,
        executable_path: Optional[str] = None,
        config: Optional[StartupConfig] = None,
    ):
        """
        تهيئة مدير التشغيل التلقائي

        Args:
            app_name: اسم التطبيق في السجل
            executable_path: مسار الملف التنفيذي
            config: إعدادات التشغيل التلقائي
        """
        self.app_name = app_name or self.APP_NAME
        self.executable_path = executable_path or sys.executable
        self.config = config or StartupConfig()

        # Detect if running as frozen executable
        self._is_frozen = getattr(sys, "frozen", False)
        if self._is_frozen:
            self.executable_path = sys.executable

    # =========================================================================
    # Main API / الواجهة الرئيسية
    # =========================================================================

    def enable_auto_start(self) -> bool:
        """
        تفعيل التشغيل التلقائي
        Enable auto-start

        Returns:
            True إذا تم التفعيل بنجاح
        """
        if not IS_WINDOWS:
            logger.warning("Auto-start is only supported on Windows")
            return False

        try:
            method = self.config.method

            if method == StartupMethod.REGISTRY:
                return self._add_registry_entry()
            elif method == StartupMethod.TASK_SCHEDULER:
                return self._create_scheduled_task()
            elif method == StartupMethod.STARTUP_FOLDER:
                return self._create_startup_shortcut()
            elif method == StartupMethod.SERVICE:
                return self._install_service()
            else:
                logger.error(f"Unknown startup method: {method}")
                return False

        except Exception as e:
            logger.error(f"Failed to enable auto-start: {e}")
            return False

    def disable_auto_start(self) -> bool:
        """
        إلغاء التشغيل التلقائي
        Disable auto-start

        Returns:
            True إذا تم الإلغاء بنجاح
        """
        if not IS_WINDOWS:
            return False

        try:
            # Try all methods to ensure cleanup
            results = [
                self._remove_registry_entry(),
                self._remove_scheduled_task(),
                self._remove_startup_shortcut(),
            ]

            return any(results)

        except Exception as e:
            logger.error(f"Failed to disable auto-start: {e}")
            return False

    def is_enabled(self) -> bool:
        """
        التحقق من حالة التشغيل التلقائي
        Check auto-start status

        Returns:
            True إذا كان مفعلاً
        """
        if not IS_WINDOWS:
            return False

        return self._check_registry_entry() or self._check_scheduled_task() or self._check_startup_shortcut()

    def get_status(self) -> dict:
        """
        الحصول على حالة التشغيل التلقائي
        Get auto-start status details
        """
        return {
            "enabled": self.is_enabled(),
            "method": self.config.method.value,
            "registry": self._check_registry_entry(),
            "task_scheduler": self._check_scheduled_task(),
            "startup_folder": self._check_startup_shortcut(),
            "executable": self.executable_path,
        }

    # =========================================================================
    # Registry Methods / طرق السجل
    # =========================================================================

    def _add_registry_entry(self) -> bool:
        """إضافة مدخل للسجل"""
        try:
            import winreg

            # Build command
            command = f'"{self.executable_path}"'
            if self.config.hidden:
                command += " --hidden"
            if self.config.delay_seconds > 0:
                command += f" --delay {self.config.delay_seconds}"

            # Open registry key
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.REGISTRY_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            )

            # Set value
            winreg.SetValueEx(
                key,
                self.app_name,
                0,
                winreg.REG_SZ,
                command,
            )

            winreg.CloseKey(key)

            logger.info(f"Added registry auto-start entry: {self.app_name}")
            return True

        except ImportError:
            logger.error("winreg not available")
            return False
        except Exception as e:
            logger.error(f"Failed to add registry entry: {e}")
            return False

    def _remove_registry_entry(self) -> bool:
        """إزالة مدخل من السجل"""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.REGISTRY_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            )

            try:
                winreg.DeleteValue(key, self.app_name)
                logger.info(f"Removed registry auto-start entry: {self.app_name}")
            except FileNotFoundError:
                pass  # Entry doesn't exist

            winreg.CloseKey(key)
            return True

        except Exception as e:
            logger.error(f"Failed to remove registry entry: {e}")
            return False

    def _check_registry_entry(self) -> bool:
        """التحقق من وجود مدخل في السجل"""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.REGISTRY_RUN_KEY,
                0,
                winreg.KEY_READ,
            )

            try:
                winreg.QueryValueEx(key, self.app_name)
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)

        except Exception:
            return False

    # =========================================================================
    # Task Scheduler Methods / طرق جدولة المهام
    # =========================================================================

    def _create_scheduled_task(self) -> bool:
        """إنشاء مهمة مجدولة"""
        try:
            # Build schtasks command
            task_name = f"\\{self.app_name}"

            # Delete existing task if any
            subprocess.run(
                ["schtasks", "/delete", "/tn", task_name, "/f"],
                capture_output=True,
            )

            # Build trigger
            if self.config.trigger == StartupTrigger.LOGON:
                trigger = "/sc onlogon"
            elif self.config.trigger == StartupTrigger.BOOT:
                trigger = "/sc onstart"
            else:
                trigger = "/sc onlogon"

            # Build command
            cmd = [
                "schtasks",
                "/create",
                "/tn",
                task_name,
                "/tr",
                f'"{self.executable_path}"',
            ] + trigger.split()

            if self.config.delay_seconds > 0:
                cmd.extend(["/delay", f"0000:00:{self.config.delay_seconds:02d}"])

            if self.config.run_as_admin:
                cmd.extend(["/rl", "highest"])

            # Execute command
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info(f"Created scheduled task: {task_name}")
                return True
            else:
                logger.error(f"Failed to create task: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Failed to create scheduled task: {e}")
            return False

    def _remove_scheduled_task(self) -> bool:
        """إزالة مهمة مجدولة"""
        try:
            task_name = f"\\{self.app_name}"

            result = subprocess.run(
                ["schtasks", "/delete", "/tn", task_name, "/f"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                logger.info(f"Removed scheduled task: {task_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove scheduled task: {e}")
            return False

    def _check_scheduled_task(self) -> bool:
        """التحقق من وجود مهمة مجدولة"""
        try:
            task_name = f"\\{self.app_name}"

            result = subprocess.run(
                ["schtasks", "/query", "/tn", task_name],
                capture_output=True,
            )

            return result.returncode == 0

        except Exception:
            return False

    # =========================================================================
    # Startup Folder Methods / طرق مجلد بدء التشغيل
    # =========================================================================

    def _get_startup_folder(self) -> Path:
        """الحصول على مجلد بدء التشغيل"""
        import os

        startup_path = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup",
        )
        return Path(startup_path)

    def _get_shortcut_path(self) -> Path:
        """الحصول على مسار الاختصار"""
        return self._get_startup_folder() / f"{self.app_name}.lnk"

    def _create_startup_shortcut(self) -> bool:
        """إنشاء اختصار في مجلد بدء التشغيل"""
        try:
            shortcut_path = self._get_shortcut_path()

            # Use PowerShell to create shortcut
            ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
$Shortcut.TargetPath = '{self.executable_path}'
$Shortcut.Description = '{self.config.description}'
$Shortcut.WorkingDirectory = '{Path(self.executable_path).parent}'
$Shortcut.Save()
"""

            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                logger.info(f"Created startup shortcut: {shortcut_path}")
                return True
            else:
                logger.error(f"Failed to create shortcut: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Failed to create startup shortcut: {e}")
            return False

    def _remove_startup_shortcut(self) -> bool:
        """إزالة اختصار من مجلد بدء التشغيل"""
        try:
            shortcut_path = self._get_shortcut_path()

            if shortcut_path.exists():
                shortcut_path.unlink()
                logger.info(f"Removed startup shortcut: {shortcut_path}")

            return True

        except Exception as e:
            logger.error(f"Failed to remove startup shortcut: {e}")
            return False

    def _check_startup_shortcut(self) -> bool:
        """التحقق من وجود اختصار في مجلد بدء التشغيل"""
        return self._get_shortcut_path().exists()

    # =========================================================================
    # Service Methods / طرق الخدمة
    # =========================================================================

    def _install_service(self) -> bool:
        """تثبيت كخدمة Windows"""
        try:
            # This requires pywin32 and running as admin
            import win32service  # noqa: F401
            import win32serviceutil  # noqa: F401

            # Service installation requires a proper service class
            # This is a placeholder for the actual implementation
            logger.warning("Service installation requires additional setup")
            return False

        except ImportError:
            logger.error("pywin32 required for service installation")
            return False
        except Exception as e:
            logger.error(f"Failed to install service: {e}")
            return False

    # =========================================================================
    # Helper Methods / طرق مساعدة
    # =========================================================================

    def set_method(self, method: StartupMethod) -> None:
        """تغيير طريقة التشغيل التلقائي"""
        self.config.method = method

    def set_delay(self, seconds: int) -> None:
        """تعيين تأخير التشغيل"""
        self.config.delay_seconds = max(0, seconds)

    def set_run_as_admin(self, enabled: bool) -> None:
        """تعيين التشغيل كمسؤول"""
        self.config.run_as_admin = enabled


# Convenience functions
def enable_auto_start(
    app_name: Optional[str] = None,
    executable_path: Optional[str] = None,
    method: StartupMethod = StartupMethod.REGISTRY,
    delay_seconds: int = 0,
) -> bool:
    """
    تفعيل التشغيل التلقائي (دالة مساعدة)
    Enable auto-start (convenience function)
    """
    config = StartupConfig(
        method=method,
        delay_seconds=delay_seconds,
    )

    manager = AutoStartManager(
        app_name=app_name,
        executable_path=executable_path,
        config=config,
    )

    return manager.enable_auto_start()


def disable_auto_start(app_name: Optional[str] = None) -> bool:
    """
    إلغاء التشغيل التلقائي (دالة مساعدة)
    Disable auto-start (convenience function)
    """
    manager = AutoStartManager(app_name=app_name)
    return manager.disable_auto_start()


def is_auto_start_enabled(app_name: Optional[str] = None) -> bool:
    """
    التحقق من حالة التشغيل التلقائي (دالة مساعدة)
    Check auto-start status (convenience function)
    """
    manager = AutoStartManager(app_name=app_name)
    return manager.is_enabled()
