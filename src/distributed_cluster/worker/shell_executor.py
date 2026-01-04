"""
Shell Executor - منفّذ الأوامر متعدد البيئات
==============================================

دعم كامل لجميع بيئات الـ Shell مع صلاحيات المدير:
- CMD (Windows Command Prompt)
- PowerShell (Windows PowerShell 5.1)
- PowerShell 7 (pwsh - Cross-platform)
- Linux Shells (bash, sh, zsh)
- WSL (Windows Subsystem for Linux)
- Ubuntu, Debian, Kali (via WSL)
- Git Bash (MINGW)

جميع البيئات تعمل بصلاحيات المدير الكاملة (Admin/Root)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Platform detection
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"


class ShellType(str, Enum):
    """أنواع الـ Shell المدعومة."""

    # Windows Shells
    CMD = "cmd"                    # Windows Command Prompt
    POWERSHELL = "powershell"      # Windows PowerShell 5.1
    POWERSHELL_7 = "pwsh"          # PowerShell 7 (Cross-platform)

    # Linux/Unix Shells
    BASH = "bash"                  # Bash shell
    SH = "sh"                      # POSIX shell
    ZSH = "zsh"                    # Z shell

    # WSL Distributions
    WSL = "wsl"                    # Default WSL
    WSL_UBUNTU = "ubuntu"          # Ubuntu via WSL
    WSL_DEBIAN = "debian"          # Debian via WSL
    WSL_KALI = "kali"              # Kali Linux via WSL

    # Git Bash
    GIT_BASH = "git-bash"          # Git Bash (MINGW)

    # Auto-detect
    AUTO = "auto"                  # تلقائي - يختار الأفضل


@dataclass
class ShellConfig:
    """إعدادات الـ Shell."""

    shell_type: ShellType = ShellType.AUTO
    run_as_admin: bool = True          # تشغيل كمدير
    working_dir: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 3600
    encoding: str = "utf-8"

    # WSL specific
    wsl_distribution: Optional[str] = None
    wsl_user: Optional[str] = None     # المستخدم في WSL (root للصلاحيات الكاملة)

    # Admin elevation
    elevate_privileges: bool = True    # رفع الصلاحيات تلقائياً


@dataclass
class ShellResult:
    """نتيجة تنفيذ الأمر."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    shell_type: ShellType = ShellType.AUTO
    execution_time_seconds: float = 0.0
    error_message: Optional[str] = None
    ran_as_admin: bool = False


class ShellDetector:
    """اكتشاف بيئات الـ Shell المتاحة."""

    _cache: Dict[ShellType, Optional[str]] = {}

    @classmethod
    def detect_available_shells(cls) -> Dict[ShellType, str]:
        """اكتشاف جميع الـ Shells المتاحة."""
        available = {}

        if IS_WINDOWS:
            # Windows shells
            available.update(cls._detect_windows_shells())
            available.update(cls._detect_wsl_distributions())
            available.update(cls._detect_git_bash())
        else:
            # Linux/macOS shells
            available.update(cls._detect_unix_shells())

        return available

    @classmethod
    def _detect_windows_shells(cls) -> Dict[ShellType, str]:
        """اكتشاف Shells الويندوز."""
        shells = {}

        # CMD - always available on Windows
        cmd_path = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        if os.path.exists(cmd_path):
            shells[ShellType.CMD] = cmd_path

        # PowerShell 5.1 (Windows PowerShell)
        ps_paths = [
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            shutil.which("powershell.exe"),
        ]
        for path in ps_paths:
            if path and os.path.exists(path):
                shells[ShellType.POWERSHELL] = path
                break

        # PowerShell 7 (pwsh)
        pwsh_paths = [
            r"C:\Program Files\PowerShell\7\pwsh.exe",
            r"C:\Program Files (x86)\PowerShell\7\pwsh.exe",
            shutil.which("pwsh.exe"),
            shutil.which("pwsh"),
        ]
        for path in pwsh_paths:
            if path and os.path.exists(path):
                shells[ShellType.POWERSHELL_7] = path
                break

        return shells

    @classmethod
    def _detect_wsl_distributions(cls) -> Dict[ShellType, str]:
        """اكتشاف توزيعات WSL."""
        shells = {}

        wsl_path = shutil.which("wsl.exe") or r"C:\Windows\System32\wsl.exe"
        if not os.path.exists(wsl_path):
            return shells

        try:
            # Get list of installed distributions
            result = subprocess.run(
                [wsl_path, "--list", "--quiet"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                distributions = result.stdout.strip().split("\n")
                distributions = [d.strip() for d in distributions if d.strip()]

                # Map distribution names
                distro_map = {
                    "ubuntu": ShellType.WSL_UBUNTU,
                    "debian": ShellType.WSL_DEBIAN,
                    "kali": ShellType.WSL_KALI,
                    "kali-linux": ShellType.WSL_KALI,
                }

                for distro in distributions:
                    distro_lower = distro.lower().replace("\x00", "")
                    for key, shell_type in distro_map.items():
                        if key in distro_lower:
                            shells[shell_type] = f"{wsl_path} -d {distro}"
                            break

                # Default WSL
                if distributions:
                    shells[ShellType.WSL] = wsl_path

        except Exception as e:
            logger.debug(f"Error detecting WSL: {e}")

        return shells

    @classmethod
    def _detect_git_bash(cls) -> Dict[ShellType, str]:
        """اكتشاف Git Bash."""
        shells = {}

        git_bash_paths = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
            shutil.which("bash.exe"),
        ]

        for path in git_bash_paths:
            if path and os.path.exists(path):
                shells[ShellType.GIT_BASH] = path
                break

        return shells

    @classmethod
    def _detect_unix_shells(cls) -> Dict[ShellType, str]:
        """اكتشاف Shells على Linux/macOS."""
        shells = {}

        shell_binaries = {
            ShellType.BASH: ["bash", "/bin/bash", "/usr/bin/bash"],
            ShellType.SH: ["sh", "/bin/sh", "/usr/bin/sh"],
            ShellType.ZSH: ["zsh", "/bin/zsh", "/usr/bin/zsh"],
        }

        for shell_type, paths in shell_binaries.items():
            for path in paths:
                found = shutil.which(path) or (os.path.exists(path) and path)
                if found:
                    shells[shell_type] = found
                    break

        return shells

    @classmethod
    def get_default_shell(cls) -> ShellType:
        """الحصول على الـ Shell الافتراضي."""
        if IS_WINDOWS:
            # Prefer PowerShell 7 > PowerShell > CMD
            available = cls.detect_available_shells()
            for shell in [ShellType.POWERSHELL_7, ShellType.POWERSHELL, ShellType.CMD]:
                if shell in available:
                    return shell
            return ShellType.CMD
        else:
            return ShellType.BASH


class ShellExecutor:
    """
    منفّذ الأوامر متعدد البيئات مع صلاحيات المدير الكاملة.

    Supports:
    - CMD, PowerShell, PowerShell 7
    - Bash, sh, zsh
    - WSL (Ubuntu, Debian, Kali)
    - Git Bash

    All with full admin/root privileges.
    """

    def __init__(
        self,
        default_shell: ShellType = ShellType.AUTO,
        run_as_admin: bool = True,
        working_dir: Optional[Path] = None,
    ):
        self.default_shell = default_shell
        self.run_as_admin = run_as_admin
        self.working_dir = working_dir or Path.cwd()

        # Detect available shells
        self.available_shells = ShellDetector.detect_available_shells()
        logger.info(f"Available shells: {list(self.available_shells.keys())}")

    def get_shell_path(self, shell_type: ShellType) -> Optional[str]:
        """الحصول على مسار الـ Shell."""
        if shell_type == ShellType.AUTO:
            shell_type = ShellDetector.get_default_shell()
        return self.available_shells.get(shell_type)

    async def execute(
        self,
        command: str,
        shell_type: ShellType = ShellType.AUTO,
        config: Optional[ShellConfig] = None,
    ) -> ShellResult:
        """
        تنفيذ أمر في الـ Shell المحدد.

        Args:
            command: الأمر المراد تنفيذه
            shell_type: نوع الـ Shell
            config: إعدادات إضافية

        Returns:
            ShellResult مع النتيجة
        """
        import time
        start_time = time.time()

        config = config or ShellConfig()

        if shell_type == ShellType.AUTO:
            shell_type = config.shell_type if config.shell_type != ShellType.AUTO else ShellDetector.get_default_shell()

        shell_path = self.get_shell_path(shell_type)
        if not shell_path:
            return ShellResult(
                exit_code=-1,
                shell_type=shell_type,
                error_message=f"Shell not available: {shell_type.value}",
            )

        try:
            # Build command based on shell type
            cmd_args, env = self._build_command(
                command=command,
                shell_type=shell_type,
                shell_path=shell_path,
                config=config,
            )

            logger.info(f"Executing in {shell_type.value}: {command[:100]}...")

            # Execute
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=config.working_dir or str(self.working_dir),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=config.timeout_seconds,
                )
            except asyncio.TimeoutError:
                process.kill()
                return ShellResult(
                    exit_code=-1,
                    shell_type=shell_type,
                    execution_time_seconds=time.time() - start_time,
                    error_message=f"Timeout after {config.timeout_seconds}s",
                )

            return ShellResult(
                exit_code=process.returncode or 0,
                stdout=stdout.decode(config.encoding, errors="replace"),
                stderr=stderr.decode(config.encoding, errors="replace"),
                shell_type=shell_type,
                execution_time_seconds=time.time() - start_time,
                ran_as_admin=config.run_as_admin,
            )

        except Exception as e:
            logger.error(f"Shell execution error: {e}")
            return ShellResult(
                exit_code=-1,
                shell_type=shell_type,
                execution_time_seconds=time.time() - start_time,
                error_message=str(e),
            )

    def _build_command(
        self,
        command: str,
        shell_type: ShellType,
        shell_path: str,
        config: ShellConfig,
    ) -> Tuple[List[str], Dict[str, str]]:
        """بناء الأمر حسب نوع الـ Shell."""
        env = os.environ.copy()
        env.update(config.environment)

        # Add admin environment variables
        if config.run_as_admin:
            env["NEBULA_ADMIN_MODE"] = "1"
            env["NEBULA_ELEVATED"] = "true"

        if shell_type == ShellType.CMD:
            # CMD: cmd.exe /c "command"
            cmd_args = [shell_path, "/c", command]

        elif shell_type == ShellType.POWERSHELL:
            # PowerShell 5.1
            ps_command = command
            if config.run_as_admin:
                ps_command = f"Set-ExecutionPolicy Bypass -Scope Process -Force; {command}"
            cmd_args = [
                shell_path,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command", ps_command,
            ]

        elif shell_type == ShellType.POWERSHELL_7:
            # PowerShell 7 (pwsh)
            ps_command = command
            if config.run_as_admin:
                ps_command = f"Set-ExecutionPolicy Bypass -Scope Process -Force; {command}"
            cmd_args = [
                shell_path,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command", ps_command,
            ]

        elif shell_type in (ShellType.WSL, ShellType.WSL_UBUNTU, ShellType.WSL_DEBIAN, ShellType.WSL_KALI):
            # WSL execution
            wsl_user = config.wsl_user or ("root" if config.run_as_admin else None)

            if shell_type == ShellType.WSL:
                cmd_args = ["wsl.exe"]
            else:
                # Specific distribution
                distro_map = {
                    ShellType.WSL_UBUNTU: "Ubuntu",
                    ShellType.WSL_DEBIAN: "Debian",
                    ShellType.WSL_KALI: "kali-linux",
                }
                distro = config.wsl_distribution or distro_map.get(shell_type, "")
                cmd_args = ["wsl.exe", "-d", distro]

            if wsl_user:
                cmd_args.extend(["-u", wsl_user])

            cmd_args.extend(["--", "bash", "-c", command])

        elif shell_type == ShellType.GIT_BASH:
            # Git Bash
            cmd_args = [shell_path, "-c", command]

        elif shell_type in (ShellType.BASH, ShellType.SH, ShellType.ZSH):
            # Unix shells
            if config.run_as_admin and os.geteuid() != 0:  # type: ignore[attr-defined]
                # Use sudo for admin
                cmd_args = ["sudo", shell_path, "-c", command]
            else:
                cmd_args = [shell_path, "-c", command]
        else:
            # Fallback
            cmd_args = [shell_path, "-c", command]

        return cmd_args, env

    async def execute_script(
        self,
        script_content: str,
        shell_type: ShellType = ShellType.AUTO,
        config: Optional[ShellConfig] = None,
    ) -> ShellResult:
        """
        تنفيذ سكريبت كامل.

        Args:
            script_content: محتوى السكريبت
            shell_type: نوع الـ Shell
            config: إعدادات إضافية
        """
        import tempfile
        import time

        start_time = time.time()
        config = config or ShellConfig()

        if shell_type == ShellType.AUTO:
            shell_type = ShellDetector.get_default_shell()

        # Determine file extension
        ext_map = {
            ShellType.CMD: ".bat",
            ShellType.POWERSHELL: ".ps1",
            ShellType.POWERSHELL_7: ".ps1",
            ShellType.BASH: ".sh",
            ShellType.SH: ".sh",
            ShellType.ZSH: ".zsh",
            ShellType.GIT_BASH: ".sh",
            ShellType.WSL: ".sh",
            ShellType.WSL_UBUNTU: ".sh",
            ShellType.WSL_DEBIAN: ".sh",
            ShellType.WSL_KALI: ".sh",
        }
        ext = ext_map.get(shell_type, ".sh")

        # Create temp script file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=ext,
            delete=False,
            encoding=config.encoding,
        ) as f:
            # Add shebang for Unix scripts
            if ext == ".sh" and not script_content.startswith("#!"):
                f.write("#!/bin/bash\n")
            f.write(script_content)
            script_path = f.name

        try:
            # Make executable on Unix
            if not IS_WINDOWS:
                # nosec B103 - script needs 755 permissions to execute
                os.chmod(script_path, 0o755)

            # Execute script
            if shell_type in (ShellType.POWERSHELL, ShellType.POWERSHELL_7):
                command = f"& '{script_path}'"
            elif shell_type == ShellType.CMD:
                command = f'call "{script_path}"'
            else:
                command = script_path

            result = await self.execute(command, shell_type, config)
            result.execution_time_seconds = time.time() - start_time
            return result

        finally:
            # Cleanup
            try:
                os.unlink(script_path)
            except Exception:
                pass

    def execute_sync(
        self,
        command: str,
        shell_type: ShellType = ShellType.AUTO,
        config: Optional[ShellConfig] = None,
    ) -> ShellResult:
        """
        تنفيذ متزامن (Synchronous).

        للاستخدام خارج async context.
        """
        return asyncio.run(self.execute(command, shell_type, config))

    def list_available_shells(self) -> Dict[str, bool]:
        """قائمة الـ Shells المتاحة."""
        all_shells = list(ShellType)
        return {
            shell.value: shell in self.available_shells
            for shell in all_shells
            if shell != ShellType.AUTO
        }


# === Convenience Functions ===

async def run_cmd(command: str, admin: bool = True) -> ShellResult:
    """تنفيذ أمر في CMD."""
    executor = ShellExecutor(run_as_admin=admin)
    return await executor.execute(command, ShellType.CMD)


async def run_powershell(command: str, admin: bool = True, version: int = 5) -> ShellResult:
    """تنفيذ أمر في PowerShell."""
    executor = ShellExecutor(run_as_admin=admin)
    shell = ShellType.POWERSHELL if version == 5 else ShellType.POWERSHELL_7
    return await executor.execute(command, shell)


async def run_bash(command: str, admin: bool = True) -> ShellResult:
    """تنفيذ أمر في Bash."""
    executor = ShellExecutor(run_as_admin=admin)
    return await executor.execute(command, ShellType.BASH)


async def run_wsl(
    command: str,
    distribution: str = "Ubuntu",
    as_root: bool = True,
) -> ShellResult:
    """تنفيذ أمر في WSL."""
    executor = ShellExecutor(run_as_admin=as_root)

    shell_map = {
        "ubuntu": ShellType.WSL_UBUNTU,
        "debian": ShellType.WSL_DEBIAN,
        "kali": ShellType.WSL_KALI,
    }
    shell_type = shell_map.get(distribution.lower(), ShellType.WSL)

    config = ShellConfig(
        run_as_admin=as_root,
        wsl_user="root" if as_root else None,
    )

    return await executor.execute(command, shell_type, config)


async def run_git_bash(command: str) -> ShellResult:
    """تنفيذ أمر في Git Bash."""
    executor = ShellExecutor()
    return await executor.execute(command, ShellType.GIT_BASH)


# === Admin Privilege Helpers ===

def is_admin() -> bool:
    """التحقق من صلاحيات المدير."""
    if IS_WINDOWS:
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0  # type: ignore[attr-defined]


def get_elevation_command(command: str, shell_type: ShellType) -> str:
    """الحصول على أمر رفع الصلاحيات."""
    if IS_WINDOWS:
        if shell_type in (ShellType.POWERSHELL, ShellType.POWERSHELL_7):
            return f'Start-Process powershell -Verb RunAs -ArgumentList "-Command {command}"'
        else:
            return f'runas /user:Administrator "{command}"'
    else:
        return f"sudo {command}"
