"""
Worker Agent - وكيل العامل
==============================

يعمل على كل جهاز "عامل":
- يسجل نفسه مع الـ Master
- يرسل heartbeat دورياً
- يستلم وينفذ jobs
- يرفع النتائج
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Optional

import httpx

from distributed_cluster.core.config import WorkerConfig
from distributed_cluster.core.resource_detector import ResourceDetector
from distributed_cluster.models.job import Job, JobSubmission
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerRegistration
from distributed_cluster.worker.executor import JobExecutor

logger = logging.getLogger(__name__)


class WorkerAgent:
    """
    Worker Agent الرئيسي.

    المسؤوليات:
    1. التسجيل مع Master
    2. إرسال heartbeat
    3. استلام وتنفيذ jobs
    4. إرسال النتائج
    """

    def __init__(self, config: Optional[WorkerConfig] = None):
        self.config = config or WorkerConfig()

        # Resource detection
        self.detector = ResourceDetector(
            cpu_override=self.config.cpu_cores_override,
            memory_override=self.config.memory_mb_override,
            gpu_indices=self.config.gpu_indices,
        )

        # Job executor
        self.executor = JobExecutor(
            work_dir=self.config.work_dir,
            docker_enabled=self.config.docker_enabled,
            sandbox_enabled=self.config.sandbox_enabled,
            docker_network=self.config.docker_default_network,
        )

        # State
        self.worker_id: Optional[str] = None
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._job_tasks: dict[str, asyncio.Task] = {}

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def master_url(self) -> str:
        """URL الـ Master."""
        return self.config.master_url.rstrip("/")

    async def start(self) -> None:
        """بدء العامل."""
        logger.info("Starting Worker Agent...")

        # Setup signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                asyncio.get_running_loop().add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._shutdown(s)))
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        # Create HTTP client
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"X-API-Key": self.config.master_api_key} if self.config.master_api_key else {},
        )

        self._running = True

        # Register with master
        if not await self._register():
            logger.error("Failed to register with master")
            await self.stop()
            return

        # Start heartbeat loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(f"Worker Agent started: {self.worker_id}")

        # Keep running
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """إيقاف العامل."""
        logger.info("Stopping Worker Agent...")
        self._running = False

        # Cancel heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Cancel running jobs
        for job_id, task in list(self._job_tasks.items()):
            task.cancel()
            await self.executor.cancel(job_id)

        # Close HTTP client
        if self._client:
            await self._client.aclose()

        logger.info("Worker Agent stopped")

    async def _shutdown(self, sig: signal.Signals) -> None:
        """Handle shutdown signal."""
        logger.info(f"Received signal {sig.name}, shutting down...")
        await self.stop()

    async def _register(self) -> bool:
        """التسجيل مع Master."""
        try:
            resources = self.detector.get_total_resources()

            registration = WorkerRegistration(
                hostname=self.detector.get_hostname(),
                ip_address=self.detector.get_ip_address(),
                port=self.config.port,
                total_resources=resources,
                tags=self.config.tags,
                labels=self.config.labels,
                platform=self.detector.get_platform(),
                python_version=self.detector.get_python_version(),
                docker_available=self.executor.docker_available,
                gpu_driver_version=self.detector.get_gpu_driver_version(),
            )

            response = await self._client.post(
                f"{self.master_url}/workers/register",
                json={
                    "hostname": registration.hostname,
                    "ip_address": registration.ip_address,
                    "port": registration.port,
                    "total_resources": {
                        "cpu_cores": resources.cpu_cores,
                        "memory_mb": resources.memory_mb,
                        "gpu_count": resources.gpu_count,
                        "gpu_memory_mb": resources.gpu_memory_mb,
                        "custom": resources.custom,
                    },
                    "tags": registration.tags,
                    "labels": registration.labels,
                    "platform": registration.platform,
                    "python_version": registration.python_version,
                    "docker_available": registration.docker_available,
                    "gpu_driver_version": registration.gpu_driver_version,
                },
            )
            response.raise_for_status()

            data = response.json()
            self.worker_id = data["worker_id"]

            logger.info(f"Registered with master as {self.worker_id}")
            logger.info(f"Resources: CPU={resources.cpu_cores}, RAM={resources.memory_mb}MB, GPU={resources.gpu_count}")

            return True

        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False

    async def _heartbeat_loop(self) -> None:
        """حلقة إرسال heartbeat."""
        while self._running:
            try:
                await self._send_heartbeat()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            await asyncio.sleep(self.config.heartbeat_interval_seconds)

    async def _send_heartbeat(self) -> None:
        """إرسال heartbeat واستلام jobs جديدة."""
        usage = self.detector.get_current_usage()

        gpus_data = []
        for gpu in usage.gpus:
            gpus_data.append(
                {
                    "index": gpu.index,
                    "name": gpu.name,
                    "uuid": gpu.uuid,
                    "memory_total_mb": gpu.memory_total_mb,
                    "memory_free_mb": gpu.memory_free_mb,
                    "memory_used_mb": gpu.memory_used_mb,
                    "utilization_percent": gpu.utilization_percent,
                    "temperature_c": gpu.temperature_c,
                    "power_draw_w": gpu.power_draw_w,
                }
            )

        response = await self._client.post(
            f"{self.master_url}/workers/heartbeat",
            json={
                "worker_id": self.worker_id,
                "cpu_percent": usage.cpu_percent,
                "memory_used_mb": usage.memory_used_mb,
                "memory_total_mb": usage.memory_total_mb,
                "memory_percent": usage.memory_percent,
                "gpus": gpus_data,
                "load_average": list(usage.load_average),
            },
        )
        response.raise_for_status()

        data = response.json()

        # معالجة jobs المعينة
        assigned_jobs = data.get("assigned_jobs", [])
        for job_data in assigned_jobs:
            job_id = job_data["job_id"]

            # تخطي إذا قيد التنفيذ
            if job_id in self._job_tasks:
                continue

            # تخطي إذا مو scheduled
            if job_data["status"] != "scheduled":
                continue

            # بدء تنفيذ
            job = self._parse_job(job_data)
            task = asyncio.create_task(self._execute_job(job))
            self._job_tasks[job_id] = task

    def _parse_job(self, data: dict) -> Job:
        """تحويل job data إلى Job object."""
        submission_data = data["submission"]

        submission = JobSubmission(
            command=submission_data["command"],
            args=submission_data.get("args", []),
            docker_image=submission_data.get("docker_image"),
            docker_command=submission_data.get("docker_command"),
            resources=ResourceSpec(
                cpu_cores=submission_data["resources"].get("cpu_cores", 1.0),
                memory_mb=submission_data["resources"].get("memory_mb", 512),
                gpu_count=submission_data["resources"].get("gpu_count", 0),
                gpu_memory_mb=submission_data["resources"].get("gpu_memory_mb", 0),
            ),
            name=submission_data.get("name"),
            timeout_seconds=submission_data.get("timeout_seconds", 3600),
            max_retries=submission_data.get("max_retries", 3),
            environment=submission_data.get("environment", {}),
            working_dir=submission_data.get("working_dir"),
        )

        job = Job(
            job_id=data["job_id"],
            submission=submission,
        )

        return job

    async def _execute_job(self, job: Job) -> None:
        """تنفيذ job واحد."""
        job_id = job.job_id

        try:
            # إبلاغ Master ببدء التنفيذ
            await self._client.post(
                f"{self.master_url}/jobs/{job_id}/start",
                json={"job_id": job_id, "worker_id": self.worker_id},
            )

            logger.info(f"Starting job {job_id}: {job.submission.command}")

            # تنفيذ
            result = await self.executor.execute(job)

            # إبلاغ Master بالنتيجة
            await self._client.post(
                f"{self.master_url}/jobs/{job_id}/complete",
                json={
                    "job_id": job_id,
                    "worker_id": self.worker_id,
                    "exit_code": result.exit_code,
                    "stdout": result.stdout[:100000],  # Limit size
                    "stderr": result.stderr[:100000],
                    "execution_time_seconds": result.execution_time_seconds,
                    "peak_memory_mb": result.peak_memory_mb,
                    "error_message": result.error_message,
                },
            )

            status = "completed" if result.success else "failed"
            logger.info(
                f"Job {job_id} {status}: exit_code={result.exit_code}, " f"time={result.execution_time_seconds:.2f}s"
            )

        except asyncio.CancelledError:
            logger.info(f"Job {job_id} cancelled")
            raise
        except Exception as e:
            logger.error(f"Job {job_id} error: {e}")
            try:
                await self._client.post(
                    f"{self.master_url}/jobs/{job_id}/complete",
                    json={
                        "job_id": job_id,
                        "worker_id": self.worker_id,
                        "exit_code": -1,
                        "error_message": str(e),
                    },
                )
            except Exception as report_error:
                logger.debug(f"Failed to report job {job_id} error to master: {report_error}")
        finally:
            if job_id in self._job_tasks:
                del self._job_tasks[job_id]


async def run_worker(config: Optional[WorkerConfig] = None) -> None:
    """تشغيل Worker Agent."""
    agent = WorkerAgent(config)
    await agent.start()
