"""
HA Master Server - سيرفر الماستر عالي التوفر
=============================================

يجمع بين:
- Leader Election (انتخاب القائد)
- State Synchronization (مزامنة الحالة)
- Health Monitoring (مراقبة الصحة)
- Automatic Failover (التبديل التلقائي)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from distributed_cluster.core.config import MasterConfig
from distributed_cluster.master.state import ClusterState
from distributed_cluster.scheduler.scheduler import Scheduler, SchedulerLoop, SchedulingPolicy

from .health_monitor import HAHealthMonitor, HealthConfig
from .leader_election import ElectionConfig, LeaderElection, LeaderInfo
from .state_sync import StateSync, SyncConfig

logger = logging.getLogger(__name__)


class HAMode(str, Enum):
    """أنماط التوفر العالي"""

    STANDALONE = "standalone"  # Master واحد (بدون HA)
    ACTIVE_STANDBY = "active_standby"  # قائد + احتياط
    ACTIVE_ACTIVE = "active_active"  # كلهم نشطين (يحتاج DB مشتركة)


@dataclass
class HAConfig:
    """إعدادات التوفر العالي"""

    # نمط التشغيل
    mode: HAMode = HAMode.STANDALONE

    # معرف هذا الـ Master
    master_id: str = ""

    # عنوان ومنفذ هذا الـ Master
    address: str = "0.0.0.0"
    port: int = 8080

    # أولوية هذا الـ Master (أعلى = أولوية أكبر للقيادة)
    priority: int = 0

    # قائمة Masters الأخرى ["host1:8080", "host2:8080"]
    peers: list[str] = field(default_factory=list)

    # إعدادات الانتخاب
    election_timeout_seconds: float = 10.0
    heartbeat_interval_seconds: float = 3.0

    # إعدادات المزامنة
    sync_interval_seconds: float = 1.0
    full_sync_interval_seconds: float = 60.0

    # إعدادات مراقبة الصحة
    health_check_interval_seconds: float = 5.0
    unhealthy_threshold: int = 3

    # التبديل التلقائي
    auto_failover: bool = True


# ==================== API Models ====================


class ElectionRequest(BaseModel):
    master_id: str
    term: int
    priority: int


class LeaderAnnouncement(BaseModel):
    master_id: str
    address: str
    port: int
    elected_at: str
    term: int


class HeartbeatMessage(BaseModel):
    master_id: str
    term: int
    timestamp: str


class SyncUpdatesRequest(BaseModel):
    updates: list[dict]


# ==================== HA Master Server ====================


class HAMasterServer:
    """
    Master Server عالي التوفر

    يدعم تشغيل عدة Masters مع:
    - انتخاب قائد تلقائي
    - مزامنة الحالة بين Masters
    - تبديل تلقائي عند الفشل
    """

    def __init__(
        self,
        config: Optional[MasterConfig] = None,
        ha_config: Optional[HAConfig] = None,
    ):
        self.config = config or MasterConfig()
        self.ha_config = ha_config or HAConfig()

        # تحديث ha_config من config
        if not self.ha_config.address or self.ha_config.address == "0.0.0.0":
            self.ha_config.address = self.config.host
        if self.ha_config.port == 8080:
            self.ha_config.port = self.config.port

        # حالة الكلاستر
        self.state = ClusterState(
            heartbeat_timeout_seconds=self.config.heartbeat_timeout_seconds,
        )

        # Scheduler
        self.scheduler = Scheduler(
            policy=SchedulingPolicy.BEST_FIT,
            max_jobs_per_worker=self.config.max_concurrent_jobs_per_worker,
        )

        # مكونات HA
        self._election: Optional[LeaderElection] = None
        self._state_sync: Optional[StateSync] = None
        self._health_monitor: Optional[HAHealthMonitor] = None

        # حالة HA
        self._is_active = False  # هل هذا الـ Master نشط (يقبل jobs)

        # Background tasks
        self._scheduler_loop: Optional[SchedulerLoop] = None
        self._health_check_task: Optional[asyncio.Task] = None

        # WebSocket connections
        self._ws_connections: list = []

        # FastAPI app
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """إنشاء تطبيق FastAPI"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await self._startup()
            yield
            await self._shutdown()

        app = FastAPI(
            title="HA Distributed Cluster API",
            description="نظام الحوسبة الموزّعة عالي التوفر",
            version="0.2.0",
            lifespan=lifespan,
        )

        # CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # تسجيل routes
        self._register_ha_routes(app)
        self._register_main_routes(app)

        return app

    def _register_ha_routes(self, app: FastAPI) -> None:
        """تسجيل routes الـ HA"""

        @app.get("/ha/status")
        async def ha_status():
            """حالة التوفر العالي"""
            return {
                "mode": self.ha_config.mode.value,
                "master_id": self.ha_config.master_id,
                "priority": self.ha_config.priority,
                "role": self._election.role.value if self._election else "standalone",
                "is_leader": self.is_leader,
                "is_active": self._is_active,
                "current_leader": (
                    self._election.current_leader.to_dict()
                    if self._election and self._election.current_leader
                    else None
                ),
                "election": (self._election.get_status() if self._election else None),
                "sync": (self._state_sync.get_sync_status() if self._state_sync else None),
                "health": (self._health_monitor.get_cluster_health() if self._health_monitor else None),
            }

        @app.post("/ha/election")
        async def handle_election(req: ElectionRequest):
            """معالجة طلب انتخاب"""
            if not self._election:
                raise HTTPException(status_code=503, detail="HA not enabled")
            return await self._election.handle_election(req.master_id, req.term, req.priority)

        @app.post("/ha/leader")
        async def handle_leader(req: LeaderAnnouncement):
            """معالجة إعلان قائد"""
            if not self._election:
                raise HTTPException(status_code=503, detail="HA not enabled")
            return await self._election.handle_leader_announcement(req.model_dump())

        @app.post("/ha/heartbeat")
        async def handle_heartbeat(req: HeartbeatMessage):
            """معالجة heartbeat من القائد"""
            if not self._election:
                raise HTTPException(status_code=503, detail="HA not enabled")
            return await self._election.handle_heartbeat(req.master_id, req.term)

        @app.post("/ha/sync/updates")
        async def handle_sync_updates(req: SyncUpdatesRequest):
            """معالجة تحديثات المزامنة"""
            if not self._state_sync:
                raise HTTPException(status_code=503, detail="HA not enabled")
            return await self._state_sync.handle_updates(req.updates)

        @app.post("/ha/sync/full")
        async def handle_full_sync(request: Request):
            """معالجة مزامنة كاملة"""
            if not self._state_sync:
                raise HTTPException(status_code=503, detail="HA not enabled")
            data = await request.json()
            return await self._state_sync.handle_full_sync(data)

        @app.get("/ha/health")
        async def ha_health():
            """صحة الـ HA"""
            if self._health_monitor:
                return self._health_monitor.get_health_response()
            return {"status": "healthy", "mode": "standalone"}

    def _register_main_routes(self, app: FastAPI) -> None:
        """تسجيل routes الرئيسية (نسخة من MasterServer مع تعديلات HA)"""

        # ==================== Health & Info ====================

        @app.get("/")
        async def root():
            return {
                "name": "HA Distributed Cluster Master",
                "version": "0.2.0",
                "status": "running",
                "ha_mode": self.ha_config.mode.value,
                "is_leader": self.is_leader,
                "is_active": self._is_active,
            }

        @app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "is_leader": self.is_leader,
            }

        @app.get("/stats")
        async def get_stats():
            stats = self.state.get_stats()
            stats["ha"] = {
                "mode": self.ha_config.mode.value,
                "is_leader": self.is_leader,
                "is_active": self._is_active,
            }
            return stats

        # ==================== Workers ====================

        @app.post("/workers/register")
        async def register_worker(request: Request):
            """تسجيل worker جديد"""
            self._check_active()
            data = await request.json()

            from distributed_cluster.models.resources import ResourceSpec
            from distributed_cluster.models.worker import WorkerRegistration

            res = data.get("total_resources", {})
            registration = WorkerRegistration(
                hostname=data.get("hostname", ""),
                ip_address=data.get("ip_address", ""),
                port=data.get("port", 0),
                total_resources=ResourceSpec(
                    cpu_cores=res.get("cpu_cores", 1),
                    memory_mb=res.get("memory_mb", 512),
                    gpu_count=res.get("gpu_count", 0),
                    gpu_memory_mb=res.get("gpu_memory_mb", 0),
                ),
                tags=data.get("tags", []),
                labels=data.get("labels", {}),
                platform=data.get("platform", "linux"),
                python_version=data.get("python_version", ""),
                docker_available=data.get("docker_available", False),
            )

            worker = self.state.register_worker(registration)

            # مزامنة التحديث
            if self._state_sync:
                self._state_sync.queue_worker_update(
                    worker.worker_id,
                    "registered",
                    {"registration": data},
                )

            return {"worker_id": worker.worker_id, "status": "registered"}

        @app.post("/workers/heartbeat")
        async def worker_heartbeat(request: Request):
            """استلام heartbeat من worker"""
            data = await request.json()
            worker_id = data.get("worker_id")

            from distributed_cluster.models.resources import GPUInfo, ResourceUsage

            gpus = []
            for g in data.get("gpus", []):
                gpus.append(
                    GPUInfo(
                        index=g.get("index", 0),
                        name=g.get("name", ""),
                        uuid=g.get("uuid", ""),
                        memory_total_mb=g.get("memory_total_mb", 0),
                        memory_free_mb=g.get("memory_free_mb", 0),
                        memory_used_mb=g.get("memory_used_mb", 0),
                        utilization_percent=g.get("utilization_percent", 0),
                    )
                )

            usage = ResourceUsage(
                cpu_percent=data.get("cpu_percent", 0),
                memory_used_mb=data.get("memory_used_mb", 0),
                memory_total_mb=data.get("memory_total_mb", 0),
                memory_percent=data.get("memory_percent", 0),
                gpus=gpus,
                load_average=tuple(data.get("load_average", (0, 0, 0))),
            )

            success = self.state.update_worker_heartbeat(worker_id, usage)
            if not success:
                raise HTTPException(status_code=404, detail="Worker not found")

            # إرجاع jobs المعينة
            pending_jobs = self.state.get_jobs_by_worker(worker_id)
            scheduled_jobs = [j.to_dict() for j in pending_jobs if j.status.value in ("scheduled", "running")]

            return {"status": "ok", "assigned_jobs": scheduled_jobs}

        @app.get("/workers")
        async def list_workers():
            """قائمة كل workers"""
            workers = self.state.get_all_workers()
            return {"workers": [w.to_dict() for w in workers]}

        @app.get("/workers/{worker_id}")
        async def get_worker(worker_id: str):
            """معلومات worker محدد"""
            worker = self.state.get_worker(worker_id)
            if not worker:
                raise HTTPException(status_code=404, detail="Worker not found")
            return worker.to_dict()

        @app.delete("/workers/{worker_id}")
        async def remove_worker(worker_id: str):
            """إزالة worker"""
            self._check_active()
            worker = self.state.remove_worker(worker_id)
            if not worker:
                raise HTTPException(status_code=404, detail="Worker not found")

            if self._state_sync:
                self._state_sync.queue_worker_update(worker_id, "removed", {})

            return {"status": "removed", "worker_id": worker_id}

        # ==================== Jobs ====================

        @app.post("/jobs")
        async def submit_job(request: Request):
            """إرسال job جديد"""
            self._check_active()
            data = await request.json()

            from distributed_cluster.models.job import JobPriority, JobSubmission
            from distributed_cluster.models.resources import ResourceSpec

            res = data.get("resources", {})
            submission = JobSubmission(
                command=data.get("command", ""),
                args=data.get("args", []),
                docker_image=data.get("docker_image"),
                docker_command=data.get("docker_command"),
                resources=ResourceSpec(
                    cpu_cores=res.get("cpu_cores", 1),
                    memory_mb=res.get("memory_mb", 512),
                    gpu_count=res.get("gpu_count", 0),
                ),
                name=data.get("name"),
                timeout_seconds=data.get("timeout_seconds", 3600),
                max_retries=data.get("max_retries", 3),
                priority=JobPriority(data.get("priority", 50)),
                required_tags=data.get("required_tags", []),
                environment=data.get("environment", {}),
            )

            job = self.state.submit_job(submission)

            if self._state_sync:
                self._state_sync.queue_job_update(
                    job.job_id,
                    "submitted",
                    {"submission": data},
                )

            return {"job_id": job.job_id, "status": "submitted"}

        @app.get("/jobs")
        async def list_jobs(status: Optional[str] = None, limit: int = 100):
            """قائمة jobs"""
            jobs = self.state.get_all_jobs()
            if status:
                jobs = [j for j in jobs if j.status.value == status]
            jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)[:limit]
            return {"jobs": [j.to_dict() for j in jobs]}

        @app.get("/jobs/{job_id}")
        async def get_job(job_id: str):
            """معلومات job محدد"""
            job = self.state.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            return job.to_dict()

        @app.delete("/jobs/{job_id}")
        async def cancel_job(job_id: str):
            """إلغاء job"""
            self._check_active()
            success = self.state.cancel_job(job_id)
            if not success:
                raise HTTPException(status_code=404, detail="Job not found")

            if self._state_sync:
                self._state_sync.queue_job_update(job_id, "cancelled", {})

            return {"status": "cancelled", "job_id": job_id}

        @app.post("/jobs/{job_id}/start")
        async def job_started(job_id: str, request: Request):
            """تأكيد بدء job"""
            data = await request.json()
            worker_id = data.get("worker_id")

            success = self.state.start_job(job_id, worker_id)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to start job")

            if self._state_sync:
                self._state_sync.queue_job_update(job_id, "started", {"worker_id": worker_id})

            return {"status": "started"}

        @app.post("/jobs/{job_id}/complete")
        async def job_completed(job_id: str, request: Request):
            """تأكيد إكمال job"""
            data = await request.json()
            worker_id = data.get("worker_id")

            from distributed_cluster.models.job import JobResult

            result = JobResult(
                exit_code=data.get("exit_code", 0),
                stdout=data.get("stdout", ""),
                stderr=data.get("stderr", ""),
                execution_time_seconds=data.get("execution_time_seconds", 0),
                peak_memory_mb=data.get("peak_memory_mb", 0),
                error_message=data.get("error_message"),
            )

            success = self.state.complete_job(job_id, worker_id, result)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to complete job")

            if self._state_sync:
                self._state_sync.queue_job_update(
                    job_id,
                    "completed",
                    {"worker_id": worker_id, "result": data},
                )

            return {"status": "completed"}

    def _check_active(self) -> None:
        """التحقق من أن هذا الـ Master نشط"""
        if self.ha_config.mode != HAMode.STANDALONE and not self._is_active:
            raise HTTPException(
                status_code=503,
                detail="This master is not active. Please contact the leader.",
            )

    @property
    def is_leader(self) -> bool:
        """هل هذا الـ Master هو القائد"""
        if self.ha_config.mode == HAMode.STANDALONE:
            return True
        return self._election.is_leader if self._election else False

    async def _startup(self) -> None:
        """بدء الخدمات"""
        logger.info(f"Starting HA Master server (mode: {self.ha_config.mode.value})...")

        if self.ha_config.mode != HAMode.STANDALONE:
            await self._start_ha_services()

        # في وضع standalone أو كقائد، نبدأ الـ scheduler
        if self.ha_config.mode == HAMode.STANDALONE:
            self._is_active = True
            await self._start_scheduler()

        logger.info(
            f"HA Master server started on {self.config.host}:{self.config.port} " f"(mode: {self.ha_config.mode.value})"
        )

    async def _shutdown(self) -> None:
        """إيقاف الخدمات"""
        logger.info("Shutting down HA Master server...")

        await self._stop_scheduler()

        if self._election:
            await self._election.stop()
        if self._state_sync:
            await self._state_sync.stop()
        if self._health_monitor:
            await self._health_monitor.stop()

        logger.info("HA Master server stopped")

    async def _start_ha_services(self) -> None:
        """بدء خدمات HA"""
        # Leader Election
        election_config = ElectionConfig(
            master_id=self.ha_config.master_id,
            address=self.ha_config.address,
            port=self.ha_config.port,
            priority=self.ha_config.priority,
            peers=self.ha_config.peers,
            election_timeout_seconds=self.ha_config.election_timeout_seconds,
            heartbeat_interval_seconds=self.ha_config.heartbeat_interval_seconds,
        )

        self._election = LeaderElection(
            config=election_config,
            on_became_leader=self._on_became_leader,
            on_lost_leadership=self._on_lost_leadership,
            on_leader_changed=self._on_leader_changed,
        )

        # State Sync
        sync_config = SyncConfig(
            master_id=self.ha_config.master_id,
            incremental_sync_interval_seconds=self.ha_config.sync_interval_seconds,
            full_sync_interval_seconds=self.ha_config.full_sync_interval_seconds,
            peers=self.ha_config.peers,
        )

        self._state_sync = StateSync(
            config=sync_config,
            state=self.state,
            is_leader_func=lambda: self.is_leader,
        )

        # Health Monitor
        health_config = HealthConfig(
            master_id=self.ha_config.master_id,
            address=self.ha_config.address,
            port=self.ha_config.port,
            peers=self.ha_config.peers,
            check_interval_seconds=self.ha_config.health_check_interval_seconds,
            unhealthy_threshold=self.ha_config.unhealthy_threshold,
            auto_failover_enabled=self.ha_config.auto_failover,
        )

        self._health_monitor = HAHealthMonitor(
            config=health_config,
            trigger_election=self._trigger_election,
        )

        # بدء الخدمات
        await self._election.start()
        await self._state_sync.start()
        await self._health_monitor.start()

    async def _on_became_leader(self) -> None:
        """عند أصبحنا القائد"""
        logger.info("This master became the leader!")
        self._is_active = True
        await self._start_scheduler()

    async def _on_lost_leadership(self) -> None:
        """عند فقدان القيادة"""
        logger.info("This master lost leadership")
        self._is_active = False
        await self._stop_scheduler()

    async def _on_leader_changed(self, leader: LeaderInfo) -> None:
        """عند تغير القائد"""
        logger.info(f"Leader changed to: {leader.master_id}")

    async def _trigger_election(self) -> None:
        """تحفيز انتخاب جديد"""
        if self._election:
            await self._election._start_election()

    async def _start_scheduler(self) -> None:
        """بدء الـ scheduler"""
        if self._scheduler_loop:
            return

        self._scheduler_loop = SchedulerLoop(
            scheduler=self.scheduler,
            get_pending_jobs=self.state.get_pending_jobs,
            get_workers=self.state.get_healthy_workers,
            on_decision=self._on_scheduling_decision,
            on_no_resources=self._on_no_resources,
            interval_seconds=self.config.scheduler_interval_seconds,
        )
        await self._scheduler_loop.start()

        # Health check loop
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        logger.info("Scheduler started")

    async def _stop_scheduler(self) -> None:
        """إيقاف الـ scheduler"""
        if self._scheduler_loop:
            await self._scheduler_loop.stop()
            self._scheduler_loop = None

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

        logger.info("Scheduler stopped")

    async def _health_check_loop(self) -> None:
        """حلقة فحص صحة workers"""
        while True:
            try:
                offline = self.state.check_worker_health()
                if offline:
                    logger.info(f"Workers marked offline: {offline}")

                # تحديث مقاييس health monitor
                if self._health_monitor:
                    stats = self.state.get_stats()
                    self._health_monitor.update_self_metrics(
                        jobs_count=stats.get("total_jobs", 0),
                        workers_count=stats.get("total_workers", 0),
                    )

            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(self.config.worker_cleanup_interval_seconds)

    def _on_scheduling_decision(self, decision) -> None:
        """معالجة قرار جدولة"""
        self.state.schedule_job(
            decision.job.job_id,
            decision.worker.worker_id,
            decision.lease_id,
        )

        if self._state_sync:
            self._state_sync.queue_job_update(
                decision.job.job_id,
                "scheduled",
                {
                    "worker_id": decision.worker.worker_id,
                    "lease_id": decision.lease_id,
                },
            )

    def _on_no_resources(self, job) -> None:
        """معالجة عدم توفر موارد"""
        logger.debug(f"No resources for job {job.job_id}")

    def run(self) -> None:
        """تشغيل السيرفر"""
        import uvicorn

        uvicorn.run(
            self.app,
            host=self.config.host,
            port=self.config.port,
            log_level=self.config.log_level.lower(),
        )


def create_ha_master_app(
    config: Optional[MasterConfig] = None,
    ha_config: Optional[HAConfig] = None,
) -> FastAPI:
    """إنشاء تطبيق FastAPI للـ HA Master"""
    server = HAMasterServer(config, ha_config)
    return server.app
