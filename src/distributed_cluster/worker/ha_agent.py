"""
HA Worker Agent - وكيل العامل عالي التوفر
==========================================

يدعم الاتصال بأكثر من Master مع:
- اكتشاف القائد تلقائياً
- التبديل التلقائي عند فشل القائد
- إعادة المحاولة مع Masters المختلفة
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import logging
import signal

import httpx

from distributed_cluster.core.config import WorkerConfig
from distributed_cluster.core.resource_detector import ResourceDetector
from distributed_cluster.models.worker import WorkerRegistration
from distributed_cluster.models.job import Job, JobSubmission
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.worker.executor import JobExecutor

logger = logging.getLogger(__name__)


@dataclass
class MasterEndpoint:
    """معلومات Master endpoint"""
    address: str
    port: int
    is_leader: bool = False
    is_healthy: bool = True
    last_success: Optional[datetime] = None
    consecutive_failures: int = 0

    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.port}"

    def mark_success(self) -> None:
        self.is_healthy = True
        self.last_success = datetime.utcnow()
        self.consecutive_failures = 0

    def mark_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.is_healthy = False


@dataclass
class HAWorkerConfig:
    """إعدادات Worker عالي التوفر"""
    # قائمة Masters ["host1:8080", "host2:8080", "host3:8080"]
    masters: list[str] = field(default_factory=list)

    # إعدادات Failover
    failover_timeout_seconds: float = 5.0
    max_retries_per_master: int = 3
    master_health_check_interval_seconds: float = 30.0

    # هل نبحث عن القائد تلقائياً
    auto_discover_leader: bool = True


class HAWorkerAgent:
    """
    Worker Agent عالي التوفر

    يتصل بأكثر من Master مع:
    - اكتشاف القائد الفعلي
    - التبديل التلقائي عند الفشل
    - توزيع الطلبات على Masters الصحية
    """

    def __init__(
        self,
        config: Optional[WorkerConfig] = None,
        ha_config: Optional[HAWorkerConfig] = None,
    ):
        self.config = config or WorkerConfig()
        self.ha_config = ha_config or HAWorkerConfig()

        # تهيئة قائمة Masters
        self._masters: list[MasterEndpoint] = []
        self._current_master: Optional[MasterEndpoint] = None
        self._init_masters()

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
        self._registered = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._master_check_task: Optional[asyncio.Task] = None
        self._job_tasks: dict[str, asyncio.Task] = {}

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

    def _init_masters(self) -> None:
        """تهيئة قائمة Masters"""
        # من ha_config
        for master_addr in self.ha_config.masters:
            try:
                if ":" in master_addr:
                    host, port = master_addr.rsplit(":", 1)
                    port = int(port)
                else:
                    host = master_addr
                    port = 8080

                self._masters.append(MasterEndpoint(
                    address=host,
                    port=port,
                ))
            except Exception as e:
                logger.warning(f"Invalid master address {master_addr}: {e}")

        # من config.master_url (للتوافق مع الإصدار القديم)
        if not self._masters and self.config.master_url:
            url = self.config.master_url.replace("http://", "").replace("https://", "")
            if ":" in url:
                host, port = url.rsplit(":", 1)
                port = int(port.split("/")[0])  # إزالة أي path
            else:
                host = url.split("/")[0]
                port = 8080

            self._masters.append(MasterEndpoint(
                address=host,
                port=port,
            ))

    async def start(self) -> None:
        """بدء العامل"""
        logger.info("Starting HA Worker Agent...")
        logger.info(f"Configured masters: {[m.url for m in self._masters]}")

        # Setup signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                asyncio.get_event_loop().add_signal_handler(
                    sig, lambda s=sig: asyncio.create_task(self._shutdown(s))
                )
            except NotImplementedError:
                pass

        # Create HTTP client
        self._client = httpx.AsyncClient(
            timeout=self.ha_config.failover_timeout_seconds,
            headers={"X-API-Key": self.config.master_api_key} if self.config.master_api_key else {},
        )

        self._running = True

        # اكتشاف القائد والتسجيل
        if not await self._discover_and_register():
            logger.error("Failed to register with any master")
            await self.stop()
            return

        # بدء المهام الخلفية
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._master_check_task = asyncio.create_task(self._master_health_loop())

        logger.info(f"HA Worker Agent started: {self.worker_id}")
        logger.info(f"Connected to master: {self._current_master.url}")

        # Keep running
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """إيقاف العامل"""
        logger.info("Stopping HA Worker Agent...")
        self._running = False

        # Cancel tasks
        for task in [self._heartbeat_task, self._master_check_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Cancel running jobs
        for job_id, task in list(self._job_tasks.items()):
            task.cancel()
            await self.executor.cancel(job_id)

        # Close HTTP client
        if self._client:
            await self._client.aclose()

        logger.info("HA Worker Agent stopped")

    async def _shutdown(self, sig: signal.Signals) -> None:
        """Handle shutdown signal"""
        logger.info(f"Received signal {sig.name}, shutting down...")
        await self.stop()

    async def _discover_and_register(self) -> bool:
        """اكتشاف القائد والتسجيل معه"""
        # جرب كل master
        for master in self._masters:
            try:
                # فحص إذا كان هذا هو القائد
                if self.ha_config.auto_discover_leader:
                    is_leader = await self._check_if_leader(master)
                    master.is_leader = is_leader

                    if not is_leader:
                        logger.debug(f"{master.url} is not the leader, skipping")
                        # نحصل على معلومات القائد الفعلي
                        leader_info = await self._get_leader_info(master)
                        if leader_info:
                            await self._add_leader_from_info(leader_info)
                        continue

                # محاولة التسجيل
                if await self._register_with_master(master):
                    self._current_master = master
                    master.mark_success()
                    return True

            except Exception as e:
                logger.warning(f"Failed to connect to {master.url}: {e}")
                master.mark_failure()

        return False

    async def _check_if_leader(self, master: MasterEndpoint) -> bool:
        """فحص إذا كان الـ master هو القائد"""
        try:
            resp = await self._client.get(
                f"{master.url}/ha/status",
                timeout=3.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("is_leader", True)  # افتراضي True للتوافق
        except Exception:
            pass

        # إذا فشل الفحص، نفترض أنه القائد (للتوافق مع non-HA setup)
        return True

    async def _get_leader_info(self, master: MasterEndpoint) -> Optional[dict]:
        """الحصول على معلومات القائد من master"""
        try:
            resp = await self._client.get(
                f"{master.url}/ha/status",
                timeout=3.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("current_leader")
        except Exception:
            pass
        return None

    async def _add_leader_from_info(self, leader_info: dict) -> None:
        """إضافة القائد الفعلي للقائمة"""
        address = leader_info.get("address")
        port = leader_info.get("port", 8080)

        if not address:
            return

        # تحقق إذا موجود
        for master in self._masters:
            if master.address == address and master.port == port:
                master.is_leader = True
                return

        # أضفه
        self._masters.insert(0, MasterEndpoint(
            address=address,
            port=port,
            is_leader=True,
        ))

    async def _register_with_master(self, master: MasterEndpoint) -> bool:
        """التسجيل مع master معين"""
        try:
            resources = self.detector.get_total_resources()

            response = await self._client.post(
                f"{master.url}/workers/register",
                json={
                    "hostname": self.detector.get_hostname(),
                    "ip_address": self.detector.get_ip_address(),
                    "port": self.config.port,
                    "total_resources": {
                        "cpu_cores": resources.cpu_cores,
                        "memory_mb": resources.memory_mb,
                        "gpu_count": resources.gpu_count,
                        "gpu_memory_mb": resources.gpu_memory_mb,
                        "custom": resources.custom,
                    },
                    "tags": self.config.tags,
                    "labels": self.config.labels,
                    "platform": self.detector.get_platform(),
                    "python_version": self.detector.get_python_version(),
                    "docker_available": self.executor.docker_available,
                    "gpu_driver_version": self.detector.get_gpu_driver_version(),
                },
                timeout=10.0,
            )
            response.raise_for_status()

            data = response.json()
            self.worker_id = data["worker_id"]
            self._registered = True

            logger.info(f"Registered with {master.url} as {self.worker_id}")
            return True

        except Exception as e:
            logger.warning(f"Registration with {master.url} failed: {e}")
            return False

    async def _heartbeat_loop(self) -> None:
        """حلقة إرسال heartbeat"""
        while self._running:
            try:
                await self._send_heartbeat()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                # محاولة التبديل لـ master آخر
                await self._handle_master_failure()

            await asyncio.sleep(self.config.heartbeat_interval_seconds)

    async def _send_heartbeat(self) -> None:
        """إرسال heartbeat للـ master الحالي"""
        if not self._current_master or not self.worker_id:
            return

        usage = self.detector.get_current_usage()

        gpus_data = []
        for gpu in usage.gpus:
            gpus_data.append({
                "index": gpu.index,
                "name": gpu.name,
                "uuid": gpu.uuid,
                "memory_total_mb": gpu.memory_total_mb,
                "memory_free_mb": gpu.memory_free_mb,
                "memory_used_mb": gpu.memory_used_mb,
                "utilization_percent": gpu.utilization_percent,
                "temperature_c": gpu.temperature_c,
                "power_draw_w": gpu.power_draw_w,
            })

        response = await self._client.post(
            f"{self._current_master.url}/workers/heartbeat",
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

        self._current_master.mark_success()

        data = response.json()

        # معالجة jobs المعينة
        assigned_jobs = data.get("assigned_jobs", [])
        for job_data in assigned_jobs:
            job_id = job_data["job_id"]

            if job_id in self._job_tasks:
                continue

            if job_data["status"] != "scheduled":
                continue

            job = self._parse_job(job_data)
            task = asyncio.create_task(self._execute_job(job))
            self._job_tasks[job_id] = task

    async def _master_health_loop(self) -> None:
        """فحص صحة Masters دورياً"""
        while self._running:
            try:
                await asyncio.sleep(self.ha_config.master_health_check_interval_seconds)

                # فحص كل Masters
                for master in self._masters:
                    try:
                        resp = await self._client.get(
                            f"{master.url}/health",
                            timeout=3.0,
                        )
                        if resp.status_code == 200:
                            master.is_healthy = True

                            # فحص إذا أصبح القائد
                            if self.ha_config.auto_discover_leader:
                                is_leader = await self._check_if_leader(master)
                                master.is_leader = is_leader
                        else:
                            master.mark_failure()
                    except Exception:
                        master.mark_failure()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Master health check error: {e}")

    async def _handle_master_failure(self) -> None:
        """معالجة فشل الـ master الحالي"""
        if self._current_master:
            self._current_master.mark_failure()
            logger.warning(f"Master {self._current_master.url} failed")

        # البحث عن master بديل
        for master in self._masters:
            if master == self._current_master:
                continue

            if not master.is_healthy:
                continue

            # فحص إذا هو القائد
            if self.ha_config.auto_discover_leader:
                is_leader = await self._check_if_leader(master)
                if not is_leader:
                    continue

            # محاولة إعادة التسجيل
            logger.info(f"Trying to failover to {master.url}")

            if await self._register_with_master(master):
                self._current_master = master
                logger.info(f"Successfully failed over to {master.url}")
                return

        logger.error("No healthy master available for failover")

    def _parse_job(self, data: dict) -> Job:
        """تحويل job data إلى Job object"""
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

        return Job(
            job_id=data["job_id"],
            submission=submission,
        )

    async def _execute_job(self, job: Job) -> None:
        """تنفيذ job"""
        job_id = job.job_id

        try:
            # إبلاغ الـ master ببدء التنفيذ
            await self._notify_job_started(job_id)

            # تنفيذ
            result = await self.executor.execute(job)

            # إبلاغ الـ master بالانتهاء
            await self._notify_job_completed(job_id, result)

        except asyncio.CancelledError:
            logger.info(f"Job {job_id} cancelled")
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            await self._notify_job_failed(job_id, str(e))
        finally:
            self._job_tasks.pop(job_id, None)

    async def _notify_job_started(self, job_id: str) -> None:
        """إبلاغ الـ master ببدء job"""
        if not self._current_master:
            return

        try:
            await self._client.post(
                f"{self._current_master.url}/jobs/{job_id}/start",
                json={"job_id": job_id, "worker_id": self.worker_id},
            )
        except Exception as e:
            logger.warning(f"Failed to notify job start: {e}")

    async def _notify_job_completed(self, job_id: str, result) -> None:
        """إبلاغ الـ master بإكمال job"""
        if not self._current_master:
            return

        try:
            await self._client.post(
                f"{self._current_master.url}/jobs/{job_id}/complete",
                json={
                    "job_id": job_id,
                    "worker_id": self.worker_id,
                    "exit_code": result.exit_code,
                    "stdout": result.stdout[:10000] if result.stdout else "",
                    "stderr": result.stderr[:10000] if result.stderr else "",
                    "execution_time_seconds": result.execution_time_seconds,
                    "peak_memory_mb": result.peak_memory_mb,
                    "error_message": result.error_message,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to notify job completion: {e}")

    async def _notify_job_failed(self, job_id: str, error: str) -> None:
        """إبلاغ الـ master بفشل job"""
        if not self._current_master:
            return

        try:
            await self._client.post(
                f"{self._current_master.url}/jobs/{job_id}/complete",
                json={
                    "job_id": job_id,
                    "worker_id": self.worker_id,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": error,
                    "error_message": error,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to notify job failure: {e}")

    def get_status(self) -> dict:
        """الحصول على حالة العامل"""
        return {
            "worker_id": self.worker_id,
            "registered": self._registered,
            "running": self._running,
            "current_master": self._current_master.url if self._current_master else None,
            "masters": [
                {
                    "url": m.url,
                    "is_leader": m.is_leader,
                    "is_healthy": m.is_healthy,
                    "consecutive_failures": m.consecutive_failures,
                }
                for m in self._masters
            ],
            "active_jobs": len(self._job_tasks),
        }
