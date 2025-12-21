"""
Remote Controller - التحكم عن بعد
==================================

تنفيذ الأوامر على الحواسيب المتصلة بالشبكة.
"""

import asyncio
import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import httpx

from distributed_cluster.core.config import ClusterConfig


class CommandType(str, Enum):
    """أنواع الأوامر"""
    SHELL = "shell"           # أوامر Shell (bash/cmd/powershell)
    PYTHON = "python"         # كود Python
    SYSTEM = "system"         # أوامر النظام (restart, shutdown, etc)
    AI = "ai"                 # أوامر الذكاء الاصطناعي


@dataclass
class RemoteCommand:
    """أمر للتنفيذ عن بعد"""
    command: str
    command_type: CommandType = CommandType.SHELL
    timeout: int = 300  # 5 دقائق
    working_dir: Optional[str] = None
    env: dict = field(default_factory=dict)
    run_as_admin: bool = False
    target_workers: list[str] = field(default_factory=list)  # فارغ = جميع Workers


@dataclass
class CommandResult:
    """نتيجة تنفيذ الأمر"""
    worker_id: str
    success: bool
    output: str
    error: str
    exit_code: int
    execution_time: float
    timestamp: datetime = field(default_factory=datetime.now)


class RemoteController:
    """
    متحكم التنفيذ عن بعد

    يسمح بتنفيذ الأوامر على جميع الحواسيب المتصلة.

    مثال:
        controller = RemoteController("http://master:8765")

        # تنفيذ أمر على جميع الحواسيب
        results = await controller.execute_all("dir" if windows else "ls -la")

        # تنفيذ على حاسوب محدد
        result = await controller.execute_on("worker-1", "python script.py")
    """

    def __init__(self, master_url: str = "http://localhost:8765"):
        self.master_url = master_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=60.0)
        self._workers: dict[str, dict] = {}

    async def close(self):
        """إغلاق الاتصال"""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def get_workers(self) -> list[dict]:
        """الحصول على قائمة Workers المتصلين"""
        try:
            response = await self.client.get(f"{self.master_url}/api/workers")
            response.raise_for_status()
            self._workers = {w["worker_id"]: w for w in response.json()}
            return list(self._workers.values())
        except Exception as e:
            return []

    async def execute_on(
        self,
        worker_id: str,
        command: str,
        command_type: CommandType = CommandType.SHELL,
        timeout: int = 300,
        run_as_admin: bool = False,
    ) -> CommandResult:
        """
        تنفيذ أمر على Worker محدد

        Args:
            worker_id: معرف الـ Worker
            command: الأمر للتنفيذ
            command_type: نوع الأمر
            timeout: المهلة بالثواني
            run_as_admin: تشغيل كمسؤول
        """
        try:
            payload = {
                "command": command,
                "command_type": command_type.value,
                "timeout": timeout,
                "run_as_admin": run_as_admin,
            }

            start_time = datetime.now()
            response = await self.client.post(
                f"{self.master_url}/api/workers/{worker_id}/execute",
                json=payload,
                timeout=timeout + 10,
            )
            execution_time = (datetime.now() - start_time).total_seconds()

            if response.status_code == 200:
                data = response.json()
                return CommandResult(
                    worker_id=worker_id,
                    success=data.get("success", True),
                    output=data.get("output", ""),
                    error=data.get("error", ""),
                    exit_code=data.get("exit_code", 0),
                    execution_time=execution_time,
                )
            else:
                return CommandResult(
                    worker_id=worker_id,
                    success=False,
                    output="",
                    error=f"HTTP {response.status_code}: {response.text}",
                    exit_code=-1,
                    execution_time=execution_time,
                )

        except Exception as e:
            return CommandResult(
                worker_id=worker_id,
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                execution_time=0,
            )

    async def execute_all(
        self,
        command: str,
        command_type: CommandType = CommandType.SHELL,
        timeout: int = 300,
        run_as_admin: bool = False,
        exclude_workers: list[str] | None = None,
    ) -> list[CommandResult]:
        """
        تنفيذ أمر على جميع Workers

        Args:
            command: الأمر للتنفيذ
            command_type: نوع الأمر
            timeout: المهلة بالثواني
            run_as_admin: تشغيل كمسؤول
            exclude_workers: Workers للاستثناء
        """
        workers = await self.get_workers()
        exclude = set(exclude_workers or [])

        tasks = []
        for worker in workers:
            worker_id = worker["worker_id"]
            if worker_id not in exclude:
                tasks.append(
                    self.execute_on(worker_id, command, command_type, timeout, run_as_admin)
                )

        if tasks:
            return await asyncio.gather(*tasks)
        return []

    async def execute_local(
        self,
        command: str,
        shell: bool = True,
        timeout: int = 300,
    ) -> CommandResult:
        """
        تنفيذ أمر محلياً

        Args:
            command: الأمر للتنفيذ
            shell: استخدام Shell
            timeout: المهلة
        """
        start_time = datetime.now()

        try:
            # تحديد Shell حسب النظام
            if platform.system() == "Windows":
                # PowerShell بصلاحيات كاملة
                shell_cmd = [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy", "Bypass",
                    "-Command", command
                ]
            else:
                shell_cmd = command if shell else command.split()

            process = await asyncio.create_subprocess_shell(
                command if shell and platform.system() != "Windows" else " ".join(shell_cmd) if isinstance(shell_cmd, list) else shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            execution_time = (datetime.now() - start_time).total_seconds()

            return CommandResult(
                worker_id="local",
                success=process.returncode == 0,
                output=stdout.decode("utf-8", errors="replace"),
                error=stderr.decode("utf-8", errors="replace"),
                exit_code=process.returncode or 0,
                execution_time=execution_time,
            )

        except asyncio.TimeoutError:
            return CommandResult(
                worker_id="local",
                success=False,
                output="",
                error="Command timed out",
                exit_code=-1,
                execution_time=timeout,
            )
        except Exception as e:
            return CommandResult(
                worker_id="local",
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                execution_time=(datetime.now() - start_time).total_seconds(),
            )

    def execute_local_sync(
        self,
        command: str,
        shell: bool = True,
        timeout: int = 300,
    ) -> CommandResult:
        """
        تنفيذ أمر محلياً (متزامن)

        Args:
            command: الأمر للتنفيذ
            shell: استخدام Shell
            timeout: المهلة
        """
        start_time = datetime.now()

        try:
            # تحديد Shell حسب النظام
            if platform.system() == "Windows":
                # PowerShell بصلاحيات كاملة
                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy", "Bypass",
                        "-Command", command
                    ],
                    capture_output=True,
                    timeout=timeout,
                    text=True,
                )
            else:
                result = subprocess.run(
                    command,
                    shell=shell,
                    capture_output=True,
                    timeout=timeout,
                    text=True,
                )

            execution_time = (datetime.now() - start_time).total_seconds()

            return CommandResult(
                worker_id="local",
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
                exit_code=result.returncode,
                execution_time=execution_time,
            )

        except subprocess.TimeoutExpired:
            return CommandResult(
                worker_id="local",
                success=False,
                output="",
                error="Command timed out",
                exit_code=-1,
                execution_time=timeout,
            )
        except Exception as e:
            return CommandResult(
                worker_id="local",
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                execution_time=(datetime.now() - start_time).total_seconds(),
            )


def run_command(command: str, timeout: int = 300) -> CommandResult:
    """
    تنفيذ أمر محلي بأمر واحد فقط

    هذه الدالة الرئيسية للتحكم الكامل.

    مثال:
        from distributed_cluster.control import run_command

        # Windows PowerShell
        result = run_command("Get-Process | Select-Object -First 10")

        # Linux/Mac
        result = run_command("ps aux | head -10")

        print(result.output)
    """
    controller = RemoteController()
    return controller.execute_local_sync(command, timeout=timeout)


async def run_command_async(command: str, timeout: int = 300) -> CommandResult:
    """نسخة غير متزامنة من run_command"""
    async with RemoteController() as controller:
        return await controller.execute_local(command, timeout=timeout)
