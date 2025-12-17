"""
Job Executor - منفّذ المهام
==============================

ينفذ Jobs على Worker:
- Process-based (مباشر)
- Docker container (معزول)
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging
import shutil

from distributed_cluster.models.job import Job, JobResult

logger = logging.getLogger(__name__)

# Windows compatibility
IS_WINDOWS = sys.platform == "win32"


@dataclass
class ExecutionContext:
    """سياق تنفيذ Job."""
    job: Job
    work_dir: Path
    start_time: float = 0.0
    process: Optional[subprocess.Popen] = None
    container_id: Optional[str] = None


class JobExecutor:
    """
    منفّذ الـ Jobs.

    يدعم التنفيذ:
    1. مباشر كـ subprocess
    2. داخل Docker container (sandbox)
    """

    def __init__(
        self,
        work_dir: Path,
        docker_enabled: bool = True,
        sandbox_enabled: bool = True,
        docker_network: str = "bridge",
    ):
        self.work_dir = Path(work_dir)
        self.docker_enabled = docker_enabled
        self.sandbox_enabled = sandbox_enabled
        self.docker_network = docker_network

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
        - هل الـ job يطلب Docker image؟
        - هل sandbox مفعّل؟
        """
        job_dir = self.work_dir / job.job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        context = ExecutionContext(job=job, work_dir=job_dir)
        self._active[job.job_id] = context

        try:
            # اختيار طريقة التنفيذ
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

                # Wait with timeout
                try:
                    exit_code = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, ctx.process.wait
                        ),
                        timeout=submission.timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    # Kill process - use platform-specific method
                    self._kill_process(ctx.process)

                    return JobResult(
                        exit_code=-1,
                        stdout=self._read_file(stdout_file),
                        stderr=self._read_file(stderr_file),
                        execution_time_seconds=time.time() - ctx.start_time,
                        error_message=f"Timeout after {submission.timeout_seconds}s",
                    )

            execution_time = time.time() - ctx.start_time

            return JobResult(
                exit_code=exit_code,
                stdout=self._read_file(stdout_file),
                stderr=self._read_file(stderr_file),
                execution_time_seconds=execution_time,
            )

        except Exception as e:
            logger.error(f"Job {job.job_id} execution error: {e}")
            return JobResult(
                exit_code=-1,
                stdout=self._read_file(stdout_file) if stdout_file.exists() else "",
                stderr=self._read_file(stderr_file) if stderr_file.exists() else "",
                execution_time_seconds=time.time() - ctx.start_time,
                error_message=str(e),
            )

    async def _execute_docker(self, ctx: ExecutionContext) -> JobResult:
        """تنفيذ داخل Docker container (image محدد)."""
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

            # Run container
            container = self._docker_client.containers.run(
                image=submission.docker_image,
                command=command,
                environment=submission.environment,
                working_dir=submission.working_dir or "/workspace",
                volumes={
                    str(ctx.work_dir): {"bind": "/workspace", "mode": "rw"},
                },
                network=self.docker_network,
                mem_limit=mem_limit,
                cpu_period=cpu_period,
                cpu_quota=cpu_quota if cpu_quota > 0 else None,
                device_requests=device_requests,
                remove=False,  # Keep for logs
                detach=True,
            )

            ctx.container_id = container.id

            # Wait with timeout
            try:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, container.wait
                    ),
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
