"""
Master Server - سيرفر الماستر
================================

REST API + WebSocket للتحكم بالكلاستر.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
import asyncio
import logging

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from distributed_cluster.core.config import MasterConfig
from distributed_cluster.master.state import ClusterState
from distributed_cluster.scheduler.scheduler import Scheduler, SchedulerLoop, SchedulingPolicy
from distributed_cluster.models.worker import WorkerRegistration, WorkerStatus
from distributed_cluster.models.job import JobSubmission, JobResult, JobPriority
from distributed_cluster.models.resources import ResourceSpec, ResourceUsage
from distributed_cluster.models.events import Event

logger = logging.getLogger(__name__)


# ==================== Pydantic Models (API) ====================

class ResourceSpecRequest(BaseModel):
    cpu_cores: float = 1.0
    memory_mb: int = 512
    gpu_count: int = 0
    gpu_memory_mb: int = 0
    custom: dict[str, float] = {}


class JobSubmitRequest(BaseModel):
    command: str
    args: list[str] = []
    docker_image: Optional[str] = None
    docker_command: Optional[str] = None
    resources: ResourceSpecRequest = ResourceSpecRequest()
    name: Optional[str] = None
    timeout_seconds: int = 3600
    max_retries: int = 3
    priority: int = 50
    required_tags: list[str] = []
    preferred_worker: Optional[str] = None
    environment: dict[str, str] = {}
    working_dir: Optional[str] = None
    labels: dict[str, str] = {}
    user_id: Optional[str] = None


class WorkerRegisterRequest(BaseModel):
    hostname: str
    ip_address: str
    port: int
    total_resources: ResourceSpecRequest
    tags: list[str] = []
    labels: dict[str, str] = {}
    platform: str = "linux"
    python_version: str = ""
    docker_available: bool = False
    gpu_driver_version: Optional[str] = None


class HeartbeatRequest(BaseModel):
    worker_id: str
    cpu_percent: float
    memory_used_mb: int
    memory_total_mb: int
    memory_percent: float
    gpus: list[dict] = []
    load_average: tuple[float, float, float] = (0.0, 0.0, 0.0)


class JobStartRequest(BaseModel):
    job_id: str
    worker_id: str


class JobCompleteRequest(BaseModel):
    job_id: str
    worker_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    execution_time_seconds: float = 0.0
    peak_memory_mb: int = 0
    error_message: Optional[str] = None


# ==================== Master Server ====================

class MasterServer:
    """
    Master Server الرئيسي.

    يدير:
    - REST API لإرسال jobs وإدارة workers
    - WebSocket للمراقبة الحية
    - Scheduler loop للجدولة التلقائية
    - Health check loop لمراقبة workers
    """

    def __init__(self, config: Optional[MasterConfig] = None):
        self.config = config or MasterConfig()
        self.state = ClusterState(
            heartbeat_timeout_seconds=self.config.heartbeat_timeout_seconds,
        )
        self.scheduler = Scheduler(
            policy=SchedulingPolicy.BEST_FIT,
            max_jobs_per_worker=self.config.max_concurrent_jobs_per_worker,
        )

        # WebSocket connections
        self._ws_connections: list[WebSocket] = []

        # Background tasks
        self._scheduler_loop: Optional[SchedulerLoop] = None
        self._health_check_task: Optional[asyncio.Task] = None

        # FastAPI app
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """إنشاء تطبيق FastAPI."""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Startup and shutdown."""
            await self._startup()
            yield
            await self._shutdown()

        app = FastAPI(
            title="Distributed Cluster API",
            description="نظام الحوسبة الموزّعة - Control Plane API",
            version="0.1.0",
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

        # Register routes
        self._register_routes(app)

        return app

    def _register_routes(self, app: FastAPI) -> None:
        """تسجيل الـ routes."""

        # ==================== Health & Info ====================

        @app.get("/")
        async def root():
            return {
                "name": "Distributed Cluster Master",
                "version": "0.1.0",
                "status": "running",
            }

        @app.get("/health")
        async def health():
            return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

        @app.get("/stats")
        async def get_stats():
            return self.state.get_stats()

        # ==================== Workers ====================

        @app.post("/workers/register")
        async def register_worker(req: WorkerRegisterRequest):
            """تسجيل worker جديد."""
            registration = WorkerRegistration(
                hostname=req.hostname,
                ip_address=req.ip_address,
                port=req.port,
                total_resources=ResourceSpec(
                    cpu_cores=req.total_resources.cpu_cores,
                    memory_mb=req.total_resources.memory_mb,
                    gpu_count=req.total_resources.gpu_count,
                    gpu_memory_mb=req.total_resources.gpu_memory_mb,
                    custom=req.total_resources.custom,
                ),
                tags=req.tags,
                labels=req.labels,
                platform=req.platform,
                python_version=req.python_version,
                docker_available=req.docker_available,
                gpu_driver_version=req.gpu_driver_version,
            )
            worker = self.state.register_worker(registration)
            return {"worker_id": worker.worker_id, "status": "registered"}

        @app.post("/workers/heartbeat")
        async def worker_heartbeat(req: HeartbeatRequest):
            """استلام heartbeat من worker."""
            from distributed_cluster.models.resources import GPUInfo

            gpus = []
            for g in req.gpus:
                gpus.append(GPUInfo(
                    index=g.get("index", 0),
                    name=g.get("name", ""),
                    uuid=g.get("uuid", ""),
                    memory_total_mb=g.get("memory_total_mb", 0),
                    memory_free_mb=g.get("memory_free_mb", 0),
                    memory_used_mb=g.get("memory_used_mb", 0),
                    utilization_percent=g.get("utilization_percent", 0),
                    temperature_c=g.get("temperature_c"),
                    power_draw_w=g.get("power_draw_w"),
                ))

            usage = ResourceUsage(
                cpu_percent=req.cpu_percent,
                memory_used_mb=req.memory_used_mb,
                memory_total_mb=req.memory_total_mb,
                memory_percent=req.memory_percent,
                gpus=gpus,
                load_average=req.load_average,
            )

            success = self.state.update_worker_heartbeat(req.worker_id, usage)
            if not success:
                raise HTTPException(status_code=404, detail="Worker not found")

            # إرجاع jobs المعينة لهذا الـ worker
            pending_jobs = self.state.get_jobs_by_worker(req.worker_id)
            scheduled_jobs = [
                j.to_dict() for j in pending_jobs
                if j.status.value in ("scheduled", "running")
            ]

            return {"status": "ok", "assigned_jobs": scheduled_jobs}

        @app.get("/workers")
        async def list_workers(
            status: Optional[str] = Query(None, description="Filter by status"),
        ):
            """قائمة كل workers."""
            workers = self.state.get_all_workers()
            if status:
                workers = [w for w in workers if w.status.value == status]
            return {"workers": [w.to_dict() for w in workers]}

        @app.get("/workers/{worker_id}")
        async def get_worker(worker_id: str):
            """معلومات worker محدد."""
            worker = self.state.get_worker(worker_id)
            if not worker:
                raise HTTPException(status_code=404, detail="Worker not found")
            return worker.to_dict()

        @app.delete("/workers/{worker_id}")
        async def remove_worker(worker_id: str):
            """إزالة worker."""
            worker = self.state.remove_worker(worker_id)
            if not worker:
                raise HTTPException(status_code=404, detail="Worker not found")
            return {"status": "removed", "worker_id": worker_id}

        # ==================== Jobs ====================

        @app.post("/jobs")
        async def submit_job(req: JobSubmitRequest):
            """إرسال job جديد."""
            submission = JobSubmission(
                command=req.command,
                args=req.args,
                docker_image=req.docker_image,
                docker_command=req.docker_command,
                resources=ResourceSpec(
                    cpu_cores=req.resources.cpu_cores,
                    memory_mb=req.resources.memory_mb,
                    gpu_count=req.resources.gpu_count,
                    gpu_memory_mb=req.resources.gpu_memory_mb,
                    custom=req.resources.custom,
                ),
                name=req.name,
                timeout_seconds=req.timeout_seconds,
                max_retries=req.max_retries,
                priority=JobPriority(req.priority),
                required_tags=req.required_tags,
                preferred_worker=req.preferred_worker,
                environment=req.environment,
                working_dir=req.working_dir,
                labels=req.labels,
                user_id=req.user_id,
            )
            job = self.state.submit_job(submission)
            return {"job_id": job.job_id, "status": "submitted"}

        @app.get("/jobs")
        async def list_jobs(
            status: Optional[str] = Query(None, description="Filter by status"),
            limit: int = Query(100, ge=1, le=1000),
        ):
            """قائمة jobs."""
            jobs = self.state.get_all_jobs()
            if status:
                jobs = [j for j in jobs if j.status.value == status]
            jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)[:limit]
            return {"jobs": [j.to_dict() for j in jobs]}

        @app.get("/jobs/{job_id}")
        async def get_job(job_id: str):
            """معلومات job محدد."""
            job = self.state.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            return job.to_dict()

        @app.delete("/jobs/{job_id}")
        async def cancel_job(job_id: str):
            """إلغاء job."""
            success = self.state.cancel_job(job_id)
            if not success:
                raise HTTPException(status_code=404, detail="Job not found or already terminal")
            return {"status": "cancelled", "job_id": job_id}

        @app.post("/jobs/{job_id}/start")
        async def job_started(job_id: str, req: JobStartRequest):
            """تأكيد بدء job (من Worker)."""
            success = self.state.start_job(job_id, req.worker_id)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to start job")
            return {"status": "started"}

        @app.post("/jobs/{job_id}/complete")
        async def job_completed(job_id: str, req: JobCompleteRequest):
            """تأكيد إكمال job (من Worker)."""
            result = JobResult(
                exit_code=req.exit_code,
                stdout=req.stdout,
                stderr=req.stderr,
                execution_time_seconds=req.execution_time_seconds,
                peak_memory_mb=req.peak_memory_mb,
                error_message=req.error_message,
            )
            success = self.state.complete_job(job_id, req.worker_id, result)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to complete job")
            return {"status": "completed"}

        # ==================== Events ====================

        @app.get("/events")
        async def get_events(limit: int = Query(100, ge=1, le=1000)):
            """آخر الأحداث."""
            events = self.state.get_recent_events(limit)
            return {"events": [e.to_dict() for e in events]}

        # ==================== WebSocket ====================

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket للمراقبة الحية."""
            await websocket.accept()
            self._ws_connections.append(websocket)

            try:
                # إرسال الحالة الأولية
                await websocket.send_json({
                    "type": "initial_state",
                    "stats": self.state.get_stats(),
                    "workers": [w.to_dict() for w in self.state.get_all_workers()],
                })

                while True:
                    # استلام رسائل من العميل (ping/pong)
                    data = await websocket.receive_text()
                    if data == "ping":
                        await websocket.send_text("pong")

            except WebSocketDisconnect:
                pass
            finally:
                if websocket in self._ws_connections:
                    self._ws_connections.remove(websocket)

    async def _startup(self) -> None:
        """بدء الخدمات الخلفية."""
        logger.info("Starting Master server...")

        # Event handler للـ WebSocket broadcast
        self.state.add_event_handler(self._broadcast_event)

        # Scheduler loop
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

        logger.info(f"Master server started on {self.config.host}:{self.config.port}")

    async def _shutdown(self) -> None:
        """إيقاف الخدمات الخلفية."""
        logger.info("Shutting down Master server...")

        if self._scheduler_loop:
            await self._scheduler_loop.stop()

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # إغلاق WebSocket connections
        for ws in self._ws_connections:
            try:
                await ws.close()
            except Exception:
                pass

    async def _health_check_loop(self) -> None:
        """حلقة فحص صحة workers."""
        while True:
            try:
                offline = self.state.check_worker_health()
                if offline:
                    logger.info(f"Workers marked offline: {offline}")
            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(self.config.worker_cleanup_interval_seconds)

    def _on_scheduling_decision(self, decision) -> None:
        """معالجة قرار جدولة."""
        self.state.schedule_job(
            decision.job.job_id,
            decision.worker.worker_id,
            decision.lease_id,
        )

    def _on_no_resources(self, job) -> None:
        """معالجة عدم توفر موارد."""
        logger.debug(f"No resources for job {job.job_id}")

    def _broadcast_event(self, event: Event) -> None:
        """بث حدث لكل WebSocket connections."""
        if not self._ws_connections:
            return

        message = {
            "type": "event",
            "event": event.to_dict(),
        }

        # Broadcast في background
        for ws in self._ws_connections[:]:
            try:
                asyncio.create_task(ws.send_json(message))
            except Exception:
                if ws in self._ws_connections:
                    self._ws_connections.remove(ws)

    def run(self) -> None:
        """تشغيل السيرفر."""
        import uvicorn
        uvicorn.run(
            self.app,
            host=self.config.host,
            port=self.config.port,
            log_level=self.config.log_level.lower(),
        )


def create_master_app(config: Optional[MasterConfig] = None) -> FastAPI:
    """إنشاء تطبيق FastAPI للـ Master."""
    server = MasterServer(config)
    return server.app
