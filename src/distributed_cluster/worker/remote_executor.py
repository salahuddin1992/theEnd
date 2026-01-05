"""
Remote Executor - منفذ الأوامر عن بعد
======================================

يوفر endpoint للتنفيذ المباشر للأوامر على Worker.
يستخدم للتحكم الكامل عن بعد.
"""

import asyncio
import platform
import sys
from dataclasses import dataclass
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request


@dataclass
class ExecutionResult:
    """نتيجة التنفيذ"""

    success: bool
    output: str
    error: str
    exit_code: int
    execution_time: float


class RemoteExecutor:
    """
    منفذ الأوامر عن بعد.

    يقبل أوامر من الشبكة وينفذها محلياً.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8766):
        self.host = host
        self.port = port
        self.app = FastAPI(title="Remote Executor", version="1.0.0")
        self._setup_routes()

    def _setup_routes(self):
        """إعداد الـ routes"""

        @self.app.post("/execute")
        async def execute_command(request: Request):
            """تنفيذ أمر"""
            body = await request.json()
            command = body.get("command", "")
            command_type = body.get("command_type", "shell")
            timeout = body.get("timeout", 300)
            run_as_admin = body.get("run_as_admin", False)

            result = await self.execute(
                command,
                command_type=command_type,
                timeout=timeout,
                run_as_admin=run_as_admin,
            )

            return {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "exit_code": result.exit_code,
                "execution_time": result.execution_time,
            }

        @self.app.get("/health")
        async def health_check():
            """فحص الصحة"""
            return {"status": "ok", "platform": platform.system()}

        @self.app.get("/info")
        async def system_info():
            """معلومات النظام"""
            import psutil

            return {
                "platform": platform.system(),
                "platform_version": platform.version(),
                "hostname": platform.node(),
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
                "python_version": sys.version,
            }

    async def execute(
        self,
        command: str,
        command_type: str = "shell",
        timeout: int = 300,
        run_as_admin: bool = False,
    ) -> ExecutionResult:
        """
        تنفيذ أمر

        Args:
            command: الأمر للتنفيذ
            command_type: نوع الأمر (shell, python, powershell)
            timeout: المهلة بالثواني
            run_as_admin: تشغيل كمسؤول
        """
        start_time = datetime.now()

        try:
            # تحديد طريقة التنفيذ
            if command_type == "python":
                shell_cmd = [sys.executable, "-c", command]
            elif command_type == "powershell" or (platform.system() == "Windows" and command_type == "shell"):
                shell_cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
            else:
                # Linux/Mac bash
                shell_cmd = command

            # تنفيذ الأمر
            process = await asyncio.create_subprocess_shell(
                command if isinstance(shell_cmd, str) else " ".join(shell_cmd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

            execution_time = (datetime.now() - start_time).total_seconds()

            return ExecutionResult(
                success=process.returncode == 0,
                output=stdout.decode("utf-8", errors="replace"),
                error=stderr.decode("utf-8", errors="replace"),
                exit_code=process.returncode or 0,
                execution_time=execution_time,
            )

        except asyncio.TimeoutError:
            return ExecutionResult(
                success=False,
                output="",
                error="Command timed out",
                exit_code=-1,
                execution_time=timeout,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                execution_time=(datetime.now() - start_time).total_seconds(),
            )

    def run(self):
        """تشغيل الخادم"""
        uvicorn.run(self.app, host=self.host, port=self.port)

    async def run_async(self):
        """تشغيل الخادم بشكل غير متزامن"""
        config = uvicorn.Config(self.app, host=self.host, port=self.port)
        server = uvicorn.Server(config)
        await server.serve()


def start_remote_executor(host: str = "0.0.0.0", port: int = 8766):
    """تشغيل Remote Executor"""
    executor = RemoteExecutor(host=host, port=port)
    executor.run()


if __name__ == "__main__":
    start_remote_executor()
