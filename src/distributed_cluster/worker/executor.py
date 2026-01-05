"""
Job Executor - منفّذ المهام
==============================

ينفذ Jobs على Worker:
- Process-based (مباشر)
- Docker container (معزول)
- Multi-shell support (CMD, PowerShell, WSL, Bash, Git Bash)

دعم كامل لجميع بيئات الـ Shell مع صلاحيات المدير:
- CMD (Windows Command Prompt)
- PowerShell (Windows PowerShell 5.1)
- PowerShell 7 (pwsh - Cross-platform)
- Linux Shells (bash, sh, zsh)
- WSL (Windows Subsystem for Linux)
- Ubuntu, Debian, Kali (via WSL)
- Git Bash (MINGW)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from distributed_cluster.models.job import Job, JobResult
from distributed_cluster.worker.metrics import ProcessMemoryTracker, WorkerMetricsCollector

logger = logging.getLogger(__name__)

# Windows compatibility
IS_WINDOWS = sys.platform == "win32"


class ShellType(str, Enum):
    """أنواع الـ Shell المدعومة."""

    # Windows Shells
    CMD = "cmd"  # Windows Command Prompt
    POWERSHELL = "powershell"  # Windows PowerShell 5.1
    POWERSHELL_7 = "pwsh"  # PowerShell 7 (Cross-platform)

    # Linux/Unix Shells
    BASH = "bash"  # Bash shell
    SH = "sh"  # POSIX shell
    ZSH = "zsh"  # Z shell

    # WSL Distributions
    WSL = "wsl"  # Default WSL
    WSL_UBUNTU = "ubuntu"  # Ubuntu via WSL
    WSL_DEBIAN = "debian"  # Debian via WSL
    WSL_KALI = "kali"  # Kali Linux via WSL

    # Git Bash
    GIT_BASH = "git-bash"  # Git Bash (MINGW)

    # Auto-detect
    AUTO = "auto"  # تلقائي - يختار الأفضل


@dataclass
class ExecutionContext:
    """سياق تنفيذ Job."""

    job: Job
    work_dir: Path
    start_time: float = 0.0
    process: Optional[subprocess.Popen] = None
    container_id: Optional[str] = None
    memory_tracker: Optional[ProcessMemoryTracker] = None


class JobExecutor:
    """
    منفّذ الـ Jobs.

    يدعم التنفيذ:
    1. مباشر كـ subprocess
    2. داخل Docker container (sandbox)
    3. متعدد الـ Shells (CMD, PowerShell, WSL, Bash, Git Bash)

    Execution Mode:
    - execution_mode="auto": تلقائي - يستخدم Docker إذا متاح، وإلا مباشر
    - execution_mode="docker": يجب استخدام Docker فقط
    - execution_mode="direct": تنفيذ مباشر على الحاسوب بدون Docker

    Shell Support (صلاحيات المدير الكاملة):
    - CMD: Windows Command Prompt
    - PowerShell: Windows PowerShell 5.1
    - PowerShell 7: Cross-platform PowerShell
    - Bash/sh/zsh: Linux shells
    - WSL: Ubuntu, Debian, Kali
    - Git Bash: MINGW environment
    """

    # Shell paths cache
    _shell_paths: Dict[ShellType, str] = {}

    def __init__(
        self,
        work_dir: Path,
        docker_enabled: bool = True,
        sandbox_enabled: bool = True,
        docker_network: str = "bridge",
        metrics_collector: Optional[WorkerMetricsCollector] = None,
        track_memory: bool = True,
        memory_sample_interval: float = 0.5,
        # خيارات جديدة للصلاحيات الكاملة
        execution_mode: str = "auto",  # auto, docker, direct
        docker_privileged: bool = False,  # صلاحيات كاملة للـ Docker
        docker_capabilities: Optional[list] = None,  # capabilities إضافية
        allow_host_network: bool = False,  # السماح بشبكة المضيف
        allow_host_pid: bool = False,  # السماح بـ PID namespace المضيف
        allow_all_devices: bool = False,  # السماح بكل الأجهزة
        # === Shell Configuration - إعدادات الـ Shell ===
        default_shell: ShellType = ShellType.AUTO,  # الـ Shell الافتراضي
        run_as_admin: bool = True,  # تشغيل كمدير (Admin/Root)
        shell_timeout: int = 3600,  # مهلة الـ Shell بالثواني
        enable_wsl: bool = True,  # تفعيل WSL
        wsl_default_user: str = "root",  # المستخدم الافتراضي في WSL
    ):
        self.work_dir = Path(work_dir)
        self.docker_enabled = docker_enabled
        self.sandbox_enabled = sandbox_enabled
        self.docker_network = docker_network
        self.metrics_collector = metrics_collector
        self.track_memory = track_memory
        self.memory_sample_interval = memory_sample_interval

        # إعدادات الصلاحيات الكاملة
        self.execution_mode = execution_mode
        self.docker_privileged = docker_privileged
        self.docker_capabilities = docker_capabilities or []
        self.allow_host_network = allow_host_network
        self.allow_host_pid = allow_host_pid
        self.allow_all_devices = allow_all_devices

        # إعدادات الـ Shell
        self.default_shell = default_shell
        self.run_as_admin = run_as_admin
        self.shell_timeout = shell_timeout
        self.enable_wsl = enable_wsl
        self.wsl_default_user = wsl_default_user

        # اكتشاف الـ Shells المتاحة
        self._detect_shells()

        # Ensure work directory exists
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Active executions
        self._active: dict[str, ExecutionContext] = {}

        # Docker client
        self._docker_client = None
        if docker_enabled:
            self._init_docker()

    def _init_docker(self) -> None:
        """Initialize Docker client."""
        try:
            import docker

            self._docker_client = docker.from_env()
            self._docker_client.ping()
            logger.info("Docker client initialized")
        except Exception as e:
            logger.warning(f"Docker not available: {e}")
            self._docker_client = None

    @property
    def docker_available(self) -> bool:
        """Is Docker available?"""
        return self._docker_client is not None

    async def execute(self, job: Job) -> JobResult:
        """
        تنفيذ Job.

        يختار طريقة التنفيذ بناءً على:
        - execution_mode: auto, docker, direct
        - هل الـ job يطلب Docker image؟
        - هل sandbox مفعّل؟
        """
        job_dir = self.work_dir / job.job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        context = ExecutionContext(job=job, work_dir=job_dir)
        self._active[job.job_id] = context

        try:
            # اختيار طريقة التنفيذ بناءً على execution_mode
            if self.execution_mode == "direct":
                # تنفيذ مباشر على الحاسوب - بدون Docker
                logger.info(f"Executing job {job.job_id} directly (no Docker)")
                return await self._execute_process(context)

            elif self.execution_mode == "docker":
                # يجب استخدام Docker فقط
                if not self.docker_available:
                    return JobResult(
                        exit_code=-1,
                        error_message=(
                            "Docker required but not available. Install Docker or "
                            "change execution_mode to 'direct' or 'auto'"
                        ),
                    )
                if job.submission.docker_image:
                    return await self._execute_docker(context)
                else:
                    return await self._execute_docker_sandbox(context)

            else:  # auto mode
                # تلقائي - يستخدم Docker إذا متاح ومطلوب
                if job.submission.docker_image and self.docker_available:
                    return await self._execute_docker(context)
                elif self.sandbox_enabled and self.docker_available:
                    return await self._execute_docker_sandbox(context)
                else:
                    return await self._execute_process(context)
        finally:
            del self._active[job.job_id]
            # Cleanup
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
            except Exception:
                pass

    async def _execute_process(self, ctx: ExecutionContext) -> JobResult:
        """تنفيذ كـ subprocess مباشر."""
        job = ctx.job
        submission = job.submission

        # Build command
        cmd = [submission.command] + submission.args

        # Environment
        env = os.environ.copy()
        env.update(submission.environment)

        # Working directory
        cwd = submission.working_dir or str(ctx.work_dir)

        logger.info(f"Executing job {job.job_id}: {' '.join(cmd)}")
        ctx.start_time = time.time()

        stdout_file = ctx.work_dir / "stdout.log"
        stderr_file = ctx.work_dir / "stderr.log"

        try:
            # Windows doesn't support start_new_session, use CREATE_NEW_PROCESS_GROUP instead
            popen_kwargs = {
                "stdout": None,
                "stderr": None,
                "env": env,
                "cwd": cwd,
            }

            if IS_WINDOWS:
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True

            with open(stdout_file, "w") as stdout_f, open(stderr_file, "w") as stderr_f:
                popen_kwargs["stdout"] = stdout_f
                popen_kwargs["stderr"] = stderr_f
                ctx.process = subprocess.Popen(cmd, **popen_kwargs)

                # Start memory tracking if enabled
                peak_memory_mb = 0
                if self.track_memory and ctx.process.pid:
                    ctx.memory_tracker = ProcessMemoryTracker(
                        pid=ctx.process.pid,
                        sample_interval=self.memory_sample_interval,
                        include_children=True,
                    )
                    await ctx.memory_tracker.start()

                    # Also notify metrics collector if available
                    if self.metrics_collector:
                        self.metrics_collector.start_job_tracking(job.job_id, ctx.process.pid)

                # Wait with timeout
                try:
                    exit_code = await asyncio.wait_for(
                        asyncio.get_running_loop().run_in_executor(None, ctx.process.wait),
                        timeout=submission.timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    # Kill process - use platform-specific method
                    self._kill_process(ctx.process)

                    # Stop memory tracking
                    if ctx.memory_tracker:
                        await ctx.memory_tracker.stop()
                        peak_memory_mb = int(ctx.memory_tracker.peak_memory_mb)

                    if self.metrics_collector:
                        await self.metrics_collector.stop_job_tracking(job.job_id, -1)

                    return JobResult(
                        exit_code=-1,
                        stdout=self._read_file(stdout_file),
                        stderr=self._read_file(stderr_file),
                        execution_time_seconds=time.time() - ctx.start_time,
                        peak_memory_mb=peak_memory_mb,
                        error_message=f"Timeout after {submission.timeout_seconds}s",
                    )

            # Stop memory tracking and get peak
            if ctx.memory_tracker:
                await ctx.memory_tracker.stop()
                peak_memory_mb = int(ctx.memory_tracker.peak_memory_mb)

            if self.metrics_collector:
                await self.metrics_collector.stop_job_tracking(job.job_id, exit_code)

            execution_time = time.time() - ctx.start_time

            return JobResult(
                exit_code=exit_code,
                stdout=self._read_file(stdout_file),
                stderr=self._read_file(stderr_file),
                execution_time_seconds=execution_time,
                peak_memory_mb=peak_memory_mb,
            )

        except Exception as e:
            logger.error(f"Job {job.job_id} execution error: {e}")

            # Stop memory tracking on error
            peak_memory_mb = 0
            if ctx.memory_tracker:
                await ctx.memory_tracker.stop()
                peak_memory_mb = int(ctx.memory_tracker.peak_memory_mb)

            if self.metrics_collector:
                await self.metrics_collector.stop_job_tracking(job.job_id, -1)

            return JobResult(
                exit_code=-1,
                stdout=self._read_file(stdout_file) if stdout_file.exists() else "",
                stderr=self._read_file(stderr_file) if stderr_file.exists() else "",
                execution_time_seconds=time.time() - ctx.start_time,
                peak_memory_mb=peak_memory_mb,
                error_message=str(e),
            )

    async def _execute_docker(self, ctx: ExecutionContext) -> JobResult:
        """تنفيذ داخل Docker container (image محدد) مع صلاحيات كاملة."""
        job = ctx.job
        submission = job.submission

        if not self._docker_client:
            return JobResult(
                exit_code=-1,
                error_message="Docker not available",
            )

        logger.info(f"Executing job {job.job_id} in Docker: {submission.docker_image}")
        ctx.start_time = time.time()

        try:
            # Build command
            if submission.docker_command:
                command = submission.docker_command
            else:
                command = f"{submission.command} {' '.join(submission.args)}"

            # Resource limits
            mem_limit = f"{submission.resources.memory_mb}m"
            cpu_period = 100000
            cpu_quota = int(submission.resources.cpu_cores * cpu_period)

            # GPU support
            device_requests = None
            if submission.resources.gpu_count > 0:
                device_requests = [
                    {
                        "Driver": "nvidia",
                        "Count": submission.resources.gpu_count,
                        "Capabilities": [["gpu"]],
                    }
                ]

            # إعدادات الشبكة
            network_mode = self.docker_network
            if self.allow_host_network:
                network_mode = "host"

            # إعدادات الصلاحيات الكاملة
            run_kwargs = {
                "image": submission.docker_image,
                "command": command,
                "environment": submission.environment,
                "working_dir": submission.working_dir or "/workspace",
                "volumes": {
                    str(ctx.work_dir): {"bind": "/workspace", "mode": "rw"},
                },
                "network_mode": network_mode,
                "mem_limit": mem_limit,
                "cpu_period": cpu_period,
                "cpu_quota": cpu_quota if cpu_quota > 0 else None,
                "device_requests": device_requests,
                "remove": False,  # Keep for logs
                "detach": True,
            }

            # صلاحيات Docker الكاملة (privileged mode)
            if self.docker_privileged:
                run_kwargs["privileged"] = True
                logger.info(f"Running job {job.job_id} with privileged mode")

            # إضافة capabilities
            if self.docker_capabilities:
                run_kwargs["cap_add"] = self.docker_capabilities
                logger.info(f"Adding capabilities: {self.docker_capabilities}")

            # السماح بـ PID namespace المضيف
            if self.allow_host_pid:
                run_kwargs["pid_mode"] = "host"

            # السماح بكل الأجهزة
            if self.allow_all_devices:
                run_kwargs["devices"] = ["/dev:/dev:rwm"]

            # Run container
            container = self._docker_client.containers.run(**run_kwargs)

            ctx.container_id = container.id

            # Wait with timeout
            try:
                result = await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(None, container.wait),
                    timeout=submission.timeout_seconds,
                )
                exit_code = result["StatusCode"]
            except asyncio.TimeoutError:
                container.kill()
                return JobResult(
                    exit_code=-1,
                    stdout=container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace"),
                    stderr=container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace"),
                    execution_time_seconds=time.time() - ctx.start_time,
                    error_message=f"Timeout after {submission.timeout_seconds}s",
                )
            finally:
                # Get logs
                stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
                stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
                container.remove(force=True)

            execution_time = time.time() - ctx.start_time

            return JobResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                execution_time_seconds=execution_time,
            )

        except Exception as e:
            logger.error(f"Docker execution error for job {job.job_id}: {e}")
            return JobResult(
                exit_code=-1,
                execution_time_seconds=time.time() - ctx.start_time,
                error_message=str(e),
            )

    async def _execute_docker_sandbox(self, ctx: ExecutionContext) -> JobResult:
        """تنفيذ داخل Docker container عام (sandbox)."""
        job = ctx.job
        submission = job.submission

        # Use a generic Python image as sandbox
        original_image = submission.docker_image
        submission.docker_image = "python:3.11-slim"

        result = await self._execute_docker(ctx)

        # Restore
        submission.docker_image = original_image
        return result

    def _kill_process(self, process: subprocess.Popen) -> None:
        """Kill a process in a cross-platform way."""
        if process is None or process.poll() is not None:
            return

        try:
            if IS_WINDOWS:
                # On Windows, use taskkill to kill the process tree
                subprocess.call(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # On Unix, kill the process group
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    process.kill()
        except Exception:
            # Fallback: just kill the main process
            try:
                process.kill()
            except Exception:
                pass

    async def cancel(self, job_id: str) -> bool:
        """إلغاء job قيد التنفيذ."""
        ctx = self._active.get(job_id)
        if not ctx:
            return False

        try:
            if ctx.process and ctx.process.poll() is None:
                self._kill_process(ctx.process)
                logger.info(f"Process killed for job {job_id}")

            if ctx.container_id and self._docker_client:
                try:
                    container = self._docker_client.containers.get(ctx.container_id)
                    container.kill()
                    logger.info(f"Container killed for job {job_id}")
                except Exception:
                    pass

            return True
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False

    def _read_file(self, path: Path, max_size: int = 1024 * 1024) -> str:
        """قراءة ملف مع حد أقصى للحجم."""
        try:
            if not path.exists():
                return ""
            content = path.read_text(errors="replace")
            if len(content) > max_size:
                content = content[:max_size] + f"\n... (truncated, total {len(content)} bytes)"
            return content
        except Exception as e:
            return f"(Error reading file: {e})"

    def get_active_jobs(self) -> list[str]:
        """قائمة jobs قيد التنفيذ."""
        return list(self._active.keys())

    # ==========================================
    # Shell Support - دعم الـ Shells المتعددة
    # ==========================================

    def _detect_shells(self) -> None:
        """اكتشاف الـ Shells المتاحة على النظام."""
        self._shell_paths = {}

        if IS_WINDOWS:
            self._detect_windows_shells()
            if self.enable_wsl:
                self._detect_wsl_shells()
            self._detect_git_bash()
        else:
            self._detect_unix_shells()

        logger.info(f"Detected shells: {list(self._shell_paths.keys())}")

    def _detect_windows_shells(self) -> None:
        """اكتشاف Shells الويندوز."""
        # CMD
        cmd_path = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        if os.path.exists(cmd_path):
            self._shell_paths[ShellType.CMD] = cmd_path

        # PowerShell 5.1
        ps_paths = [
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            shutil.which("powershell.exe"),
        ]
        for path in ps_paths:
            if path and os.path.exists(path):
                self._shell_paths[ShellType.POWERSHELL] = path
                break

        # PowerShell 7
        pwsh_paths = [
            r"C:\Program Files\PowerShell\7\pwsh.exe",
            r"C:\Program Files (x86)\PowerShell\7\pwsh.exe",
            shutil.which("pwsh.exe"),
            shutil.which("pwsh"),
        ]
        for path in pwsh_paths:
            if path and os.path.exists(path):
                self._shell_paths[ShellType.POWERSHELL_7] = path
                break

    def _detect_wsl_shells(self) -> None:
        """اكتشاف توزيعات WSL."""
        wsl_path = shutil.which("wsl.exe") or r"C:\Windows\System32\wsl.exe"
        if not os.path.exists(wsl_path):
            return

        try:
            result = subprocess.run(
                [wsl_path, "--list", "--quiet"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                distributions = [d.strip().replace("\x00", "") for d in result.stdout.strip().split("\n") if d.strip()]

                distro_map = {
                    "ubuntu": ShellType.WSL_UBUNTU,
                    "debian": ShellType.WSL_DEBIAN,
                    "kali": ShellType.WSL_KALI,
                }

                for distro in distributions:
                    distro_lower = distro.lower()
                    for key, shell_type in distro_map.items():
                        if key in distro_lower:
                            self._shell_paths[shell_type] = f"{wsl_path} -d {distro}"
                            break

                if distributions:
                    self._shell_paths[ShellType.WSL] = wsl_path

        except Exception as e:
            logger.debug(f"Error detecting WSL: {e}")

    def _detect_git_bash(self) -> None:
        """اكتشاف Git Bash."""
        git_bash_paths = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
            shutil.which("bash.exe"),
        ]

        for path in git_bash_paths:
            if path and os.path.exists(path):
                self._shell_paths[ShellType.GIT_BASH] = path
                break

    def _detect_unix_shells(self) -> None:
        """اكتشاف Shells على Linux/macOS."""
        shell_binaries = {
            ShellType.BASH: ["bash", "/bin/bash", "/usr/bin/bash"],
            ShellType.SH: ["sh", "/bin/sh", "/usr/bin/sh"],
            ShellType.ZSH: ["zsh", "/bin/zsh", "/usr/bin/zsh"],
        }

        for shell_type, paths in shell_binaries.items():
            for path in paths:
                found = shutil.which(path) or (os.path.exists(path) and path)
                if found:
                    self._shell_paths[shell_type] = found
                    break

    def get_available_shells(self) -> Dict[str, str]:
        """الحصول على قائمة الـ Shells المتاحة."""
        return {shell.value: path for shell, path in self._shell_paths.items()}

    def get_default_shell_type(self) -> ShellType:
        """الحصول على الـ Shell الافتراضي."""
        if self.default_shell != ShellType.AUTO:
            return self.default_shell

        if IS_WINDOWS:
            for shell in [ShellType.POWERSHELL_7, ShellType.POWERSHELL, ShellType.CMD]:
                if shell in self._shell_paths:
                    return shell
            return ShellType.CMD
        else:
            return ShellType.BASH if ShellType.BASH in self._shell_paths else ShellType.SH

    async def execute_shell(
        self,
        command: str,
        shell_type: ShellType = ShellType.AUTO,
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        as_admin: Optional[bool] = None,
    ) -> JobResult:
        """
        تنفيذ أمر في Shell محدد مع صلاحيات المدير.

        Args:
            command: الأمر المراد تنفيذه
            shell_type: نوع الـ Shell (AUTO للاختيار التلقائي)
            working_dir: مجلد العمل
            environment: متغيرات البيئة الإضافية
            timeout: مهلة التنفيذ بالثواني
            as_admin: تشغيل كمدير (None للاستخدام الافتراضي)

        Returns:
            JobResult مع نتيجة التنفيذ
        """
        start_time = time.time()

        # تحديد الـ Shell
        if shell_type == ShellType.AUTO:
            shell_type = self.get_default_shell_type()

        shell_path = self._shell_paths.get(shell_type)
        if not shell_path:
            return JobResult(
                exit_code=-1,
                error_message=f"Shell not available: {shell_type.value}. Available: {list(self._shell_paths.keys())}",
            )

        # إعدادات التنفيذ
        run_admin = as_admin if as_admin is not None else self.run_as_admin
        exec_timeout = timeout or self.shell_timeout
        cwd = working_dir or str(self.work_dir)

        # بناء البيئة
        env = os.environ.copy()
        if environment:
            env.update(environment)

        # إضافة متغيرات بيئة المدير
        if run_admin:
            env["NEBULA_ADMIN_MODE"] = "1"
            env["NEBULA_ELEVATED"] = "true"
            env["NEBULA_SHELL"] = shell_type.value

        try:
            # بناء الأمر حسب نوع الـ Shell
            cmd_args = self._build_shell_command(command, shell_type, shell_path, run_admin)

            logger.info(f"Executing in {shell_type.value} (admin={run_admin}): {command[:100]}...")

            # تنفيذ الأمر
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=exec_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return JobResult(
                    exit_code=-1,
                    execution_time_seconds=time.time() - start_time,
                    error_message=f"Timeout after {exec_timeout}s",
                )

            return JobResult(
                exit_code=process.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                execution_time_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Shell execution error: {e}")
            return JobResult(
                exit_code=-1,
                execution_time_seconds=time.time() - start_time,
                error_message=str(e),
            )

    def _build_shell_command(
        self,
        command: str,
        shell_type: ShellType,
        shell_path: str,
        as_admin: bool,
    ) -> List[str]:
        """بناء الأمر حسب نوع الـ Shell."""

        if shell_type == ShellType.CMD:
            return [shell_path, "/c", command]

        elif shell_type == ShellType.POWERSHELL:
            ps_command = command
            if as_admin:
                ps_command = f"Set-ExecutionPolicy Bypass -Scope Process -Force; {command}"
            return [
                shell_path,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_command,
            ]

        elif shell_type == ShellType.POWERSHELL_7:
            ps_command = command
            if as_admin:
                ps_command = f"Set-ExecutionPolicy Bypass -Scope Process -Force; {command}"
            return [
                shell_path,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_command,
            ]

        elif shell_type in (ShellType.WSL, ShellType.WSL_UBUNTU, ShellType.WSL_DEBIAN, ShellType.WSL_KALI):
            # WSL execution
            cmd_args = ["wsl.exe"]

            if shell_type != ShellType.WSL:
                distro_map = {
                    ShellType.WSL_UBUNTU: "Ubuntu",
                    ShellType.WSL_DEBIAN: "Debian",
                    ShellType.WSL_KALI: "kali-linux",
                }
                if shell_type in distro_map:
                    cmd_args.extend(["-d", distro_map[shell_type]])

            if as_admin:
                cmd_args.extend(["-u", self.wsl_default_user])

            cmd_args.extend(["--", "bash", "-c", command])
            return cmd_args

        elif shell_type == ShellType.GIT_BASH:
            return [shell_path, "-c", command]

        elif shell_type in (ShellType.BASH, ShellType.SH, ShellType.ZSH):
            if as_admin and not IS_WINDOWS:
                try:
                    if os.geteuid() != 0:  # type: ignore[attr-defined]
                        return ["sudo", shell_path, "-c", command]
                except AttributeError:
                    pass
            return [shell_path, "-c", command]

        else:
            return [shell_path, "-c", command]

    # === Convenience methods for specific shells ===

    async def run_cmd(self, command: str, **kwargs) -> JobResult:
        """تنفيذ أمر في CMD."""
        return await self.execute_shell(command, ShellType.CMD, **kwargs)

    async def run_powershell(self, command: str, version: int = 5, **kwargs) -> JobResult:
        """تنفيذ أمر في PowerShell."""
        shell = ShellType.POWERSHELL if version == 5 else ShellType.POWERSHELL_7
        return await self.execute_shell(command, shell, **kwargs)

    async def run_bash(self, command: str, **kwargs) -> JobResult:
        """تنفيذ أمر في Bash."""
        return await self.execute_shell(command, ShellType.BASH, **kwargs)

    async def run_wsl(self, command: str, distro: str = "ubuntu", **kwargs) -> JobResult:
        """تنفيذ أمر في WSL."""
        shell_map = {
            "ubuntu": ShellType.WSL_UBUNTU,
            "debian": ShellType.WSL_DEBIAN,
            "kali": ShellType.WSL_KALI,
        }
        shell = shell_map.get(distro.lower(), ShellType.WSL)
        return await self.execute_shell(command, shell, **kwargs)

    async def run_git_bash(self, command: str, **kwargs) -> JobResult:
        """تنفيذ أمر في Git Bash."""
        return await self.execute_shell(command, ShellType.GIT_BASH, **kwargs)
