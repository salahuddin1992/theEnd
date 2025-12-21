"""
Enhanced Master API - واجهة الماستر المحسّنة
==============================================

REST API مع:
- Security (authentication + authorization)
- Rate limiting
- Request validation
- Proper error handling
- Metrics collection
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Optional

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from distributed_cluster.core.config import MasterConfig
from distributed_cluster.master.state import ClusterState
from distributed_cluster.models.job import JobPriority, JobResult, JobSubmission
from distributed_cluster.models.lease import LeaseManager
from distributed_cluster.models.resources import ResourceSpec, ResourceUsage
from distributed_cluster.models.worker import WorkerRegistration
from distributed_cluster.observability.logging import get_logger
from distributed_cluster.observability.metrics import get_metrics
from distributed_cluster.scheduler.scheduler import Scheduler, SchedulingPolicy
from distributed_cluster.scheduler.scoring import SCORING_PROFILES, CompositeScorer
from distributed_cluster.security.auth import (
    AuthManager,
    Permission,
    Role,
    TokenPayload,
)

logger = get_logger("master.api")
metrics = get_metrics()


# ==================== Pydantic Models ====================


class ResourceSpecRequest(BaseModel):
    cpu_cores: float = Field(default=1.0, ge=0.1, le=1000)
    memory_mb: int = Field(default=512, ge=64, le=1024 * 1024)
    gpu_count: int = Field(default=0, ge=0, le=100)
    gpu_memory_mb: int = Field(default=0, ge=0)
    custom: dict[str, float] = Field(default_factory=dict)


class JobSubmitRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=10000)
    args: list[str] = Field(default_factory=list)
    docker_image: Optional[str] = Field(default=None, max_length=500)
    docker_command: Optional[str] = None
    resources: ResourceSpecRequest = Field(default_factory=ResourceSpecRequest)
    name: Optional[str] = Field(default=None, max_length=200)
    timeout_seconds: int = Field(default=3600, ge=1, le=86400 * 7)
    max_retries: int = Field(default=3, ge=0, le=100)
    priority: int = Field(default=50, ge=0, le=200)
    required_tags: list[str] = Field(default_factory=list)
    preferred_worker: Optional[str] = None
    environment: dict[str, str] = Field(default_factory=dict)
    working_dir: Optional[str] = None
    labels: dict[str, str] = Field(default_factory=dict)

    # Idempotency
    idempotency_key: Optional[str] = Field(default=None, max_length=100)


class WorkerRegisterRequest(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=255)
    ip_address: str = Field(..., min_length=7, max_length=45)
    port: int = Field(..., ge=1, le=65535)
    total_resources: ResourceSpecRequest
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    platform: str = Field(default="linux", max_length=50)
    python_version: str = Field(default="", max_length=20)
    docker_available: bool = False
    gpu_driver_version: Optional[str] = None

    # Security
    enrollment_token: Optional[str] = None
    fingerprint: Optional[str] = None


class HeartbeatRequest(BaseModel):
    worker_id: str
    cpu_percent: float = Field(ge=0, le=100)
    memory_used_mb: int = Field(ge=0)
    memory_total_mb: int = Field(ge=0)
    memory_percent: float = Field(ge=0, le=100)
    gpus: list[dict] = Field(default_factory=list)
    load_average: tuple[float, float, float] = (0.0, 0.0, 0.0)


class JobCompleteRequest(BaseModel):
    job_id: str
    worker_id: str
    exit_code: int
    stdout: str = Field(default="", max_length=1024 * 1024)
    stderr: str = Field(default="", max_length=1024 * 1024)
    execution_time_seconds: float = Field(default=0.0, ge=0)
    peak_memory_mb: int = Field(default=0, ge=0)
    error_message: Optional[str] = Field(default=None, max_length=10000)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: str


# ==================== Dependencies ====================


class APIState:
    """حالة الـ API المشتركة."""

    def __init__(self, config: MasterConfig):
        self.config = config
        self.state = ClusterState(
            heartbeat_timeout_seconds=config.heartbeat_timeout_seconds,
        )
        self.scheduler = Scheduler(
            policy=SchedulingPolicy.BEST_FIT,
            max_jobs_per_worker=config.max_concurrent_jobs_per_worker,
        )
        self.scorer = CompositeScorer(weights=SCORING_PROFILES["best_fit"])
        self.lease_manager = LeaseManager(
            default_duration_seconds=60,
        )

        # Security
        self.auth = AuthManager(
            secret_key=config.auth_secret_key or "dev-secret-key-change-in-production",
            auto_approve_workers=not config.auth_enabled,
        )

        # WebSocket connections
        self.ws_connections: list[WebSocket] = []


# Global state (initialized in lifespan)
_api_state: Optional[APIState] = None


def get_api_state() -> APIState:
    """الحصول على حالة الـ API."""
    if _api_state is None:
        raise RuntimeError("API not initialized")
    return _api_state


async def get_current_token(
    authorization: Annotated[Optional[str], Header()] = None,
    x_api_key: Annotated[Optional[str], Header()] = None,
) -> Optional[TokenPayload]:
    """
    استخراج والتحقق من token.

    يدعم:
    - Bearer token في Authorization header
    - API key في X-API-Key header
    """
    state = get_api_state()

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif x_api_key:
        token = x_api_key

    if not token:
        if state.config.auth_enabled:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None

    payload = state.auth.verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def require_permission(permission: Permission):
    """
    Dependency للتحقق من صلاحية.

    Usage:
        @app.get("/admin", dependencies=[Depends(require_permission(Permission.ADMIN_CONFIG))])
    """

    async def checker(
        token: Annotated[Optional[TokenPayload], Depends(get_current_token)],
    ):
        state = get_api_state()
        if not state.config.auth_enabled:
            return

        if token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        if not token.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value}",
            )

    return checker


# ==================== App Factory ====================


def create_app(config: Optional[MasterConfig] = None) -> FastAPI:
    """إنشاء تطبيق FastAPI."""

    config = config or MasterConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Startup and shutdown."""
        global _api_state
        _api_state = APIState(config)

        # Start background tasks
        scheduler_task = asyncio.create_task(_scheduler_loop())
        health_task = asyncio.create_task(_health_check_loop())
        metrics_task = asyncio.create_task(_metrics_update_loop())

        logger.info("Master API started", host=config.host, port=config.port)

        yield

        # Shutdown
        scheduler_task.cancel()
        health_task.cancel()
        metrics_task.cancel()

        for ws in _api_state.ws_connections:
            try:
                await ws.close()
            except Exception:
                pass

        logger.info("Master API stopped")

    app = FastAPI(
        title="NebulaCompute - Distributed Cluster API",
        description="نظام الحوسبة الموزّعة - Control Plane API",
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

    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=exc.detail,
                code=f"HTTP_{exc.status_code}",
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception", exc_info=True, path=request.url.path)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="Internal server error",
                code="INTERNAL_ERROR",
            ).model_dump(),
        )

    # Register routes
    _register_routes(app)

    return app


def _register_routes(app: FastAPI) -> None:
    """تسجيل الـ routes."""

    # ==================== Health & Info ====================

    @app.get("/", tags=["Info"])
    async def root():
        return {
            "name": "NebulaCompute Distributed Cluster",
            "version": "0.2.0",
            "status": "running",
        }

    @app.get("/health", tags=["Info"])
    async def health():
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
        }

    @app.get("/stats", tags=["Info"])
    async def get_stats():
        state = get_api_state()
        return state.state.get_stats()

    @app.get("/metrics", tags=["Info"])
    async def get_metrics_endpoint():
        return metrics.get_all_metrics()

    # ==================== Authentication ====================

    @app.post("/auth/token", tags=["Auth"])
    async def create_token(
        role: Role = Query(default=Role.USER),
        expires_hours: int = Query(default=24, ge=1, le=8760),
    ):
        """إنشاء token جديد (للتطوير)."""
        state = get_api_state()
        if state.config.auth_enabled:
            raise HTTPException(
                status_code=403,
                detail="Token creation disabled in production",
            )

        token = state.auth.create_user_token(
            user_id=f"dev-user-{int(time.time())}",
            role=role,
        )
        return {"token": token, "role": role.value}

    @app.post("/auth/enrollment-token", tags=["Auth"])
    async def create_enrollment_token(
        _: None = Depends(require_permission(Permission.ADMIN_USERS)),
    ):
        """إنشاء enrollment token لـ worker جديد."""
        state = get_api_state()
        token = state.auth.create_enrollment_token(expires_in_hours=24)
        return {"enrollment_token": token, "expires_in_hours": 24}

    # ==================== Workers ====================

    @app.post("/workers/register", tags=["Workers"])
    async def register_worker(req: WorkerRegisterRequest):
        """تسجيل worker جديد."""
        state = get_api_state()

        # Security: enrollment
        fingerprint = req.fingerprint or f"fp-{req.hostname}-{req.ip_address}"
        approved, reason, worker_token = state.auth.enroll_worker(
            fingerprint=fingerprint,
            enrollment_token=req.enrollment_token,
            hostname=req.hostname,
            ip_address=req.ip_address,
        )

        if not approved:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=reason,
            )

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
        worker = state.state.register_worker(registration)

        metrics.worker_registered()
        logger.worker_registered(worker.worker_id, worker.hostname)

        return {
            "worker_id": worker.worker_id,
            "status": "registered",
            "auth_token": worker_token,
            "heartbeat_interval_seconds": state.config.heartbeat_interval_seconds,
        }

    @app.post("/workers/heartbeat", tags=["Workers"])
    async def worker_heartbeat(
        req: HeartbeatRequest,
        token: Annotated[Optional[TokenPayload], Depends(get_current_token)] = None,
    ):
        """استلام heartbeat من worker."""
        state = get_api_state()
        start_time = time.time()

        # Validate worker ownership
        if token and token.worker_id and token.worker_id != req.worker_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Worker ID mismatch",
            )

        from distributed_cluster.models.resources import GPUInfo

        gpus = []
        for g in req.gpus:
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
            cpu_percent=req.cpu_percent,
            memory_used_mb=req.memory_used_mb,
            memory_total_mb=req.memory_total_mb,
            memory_percent=req.memory_percent,
            gpus=gpus,
            load_average=req.load_average,
        )

        success = state.state.update_worker_heartbeat(req.worker_id, usage)
        if not success:
            raise HTTPException(status_code=404, detail="Worker not found")

        latency = time.time() - start_time
        metrics.worker_heartbeat(req.worker_id, latency)

        # Return assigned jobs and lease renewals
        pending_jobs = state.state.get_jobs_by_worker(req.worker_id)
        scheduled_jobs = [j.to_dict() for j in pending_jobs if j.status.value in ("scheduled", "running")]

        # Renew leases
        lease_renewals = []
        for job in pending_jobs:
            if job.lease_id:
                lease = state.lease_manager.renew_lease(job.lease_id, req.worker_id)
                if lease:
                    lease_renewals.append(
                        {
                            "lease_id": lease.lease_id,
                            "job_id": job.job_id,
                            "expires_at": lease.expires_at.isoformat() if lease.expires_at else None,
                        }
                    )

        return {
            "status": "ok",
            "assigned_jobs": scheduled_jobs,
            "lease_renewals": lease_renewals,
        }

    @app.get("/workers", tags=["Workers"])
    async def list_workers(
        status_filter: Optional[str] = Query(None, alias="status"),
        _: None = Depends(require_permission(Permission.WORKER_READ)),
    ):
        """قائمة كل workers."""
        state = get_api_state()
        workers = state.state.get_all_workers()
        if status_filter:
            workers = [w for w in workers if w.status.value == status_filter]
        return {"workers": [w.to_dict() for w in workers]}

    @app.get("/workers/{worker_id}", tags=["Workers"])
    async def get_worker(
        worker_id: str,
        _: None = Depends(require_permission(Permission.WORKER_READ)),
    ):
        """معلومات worker محدد."""
        state = get_api_state()
        worker = state.state.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")
        return worker.to_dict()

    @app.delete("/workers/{worker_id}", tags=["Workers"])
    async def remove_worker(
        worker_id: str,
        _: None = Depends(require_permission(Permission.WORKER_MANAGE)),
    ):
        """إزالة worker."""
        state = get_api_state()
        worker = state.state.remove_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")

        # Revoke leases
        orphaned_jobs = state.lease_manager.revoke_worker_leases(worker_id)

        return {
            "status": "removed",
            "worker_id": worker_id,
            "orphaned_jobs": orphaned_jobs,
        }

    @app.post("/workers/{worker_id}/execute", tags=["Workers"])
    async def execute_on_worker(
        worker_id: str,
        request: Request,
        _: None = Depends(require_permission(Permission.WORKER_MANAGE)),
    ):
        """
        تنفيذ أمر على Worker محدد.

        يستخدم للتحكم عن بعد في الحواسيب المتصلة.
        """
        state = get_api_state()
        worker = state.state.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")

        body = await request.json()
        command = body.get("command", "")
        timeout = body.get("timeout", 300)
        command_type = body.get("command_type", "shell")

        # إرسال الأمر للـ Worker عبر HTTP
        import httpx

        worker_url = f"http://{worker.ip_address}:{worker.port}"

        try:
            async with httpx.AsyncClient(timeout=timeout + 10) as client:
                response = await client.post(
                    f"{worker_url}/execute",
                    json={
                        "command": command,
                        "command_type": command_type,
                        "timeout": timeout,
                    },
                )
                return response.json()
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": -1,
            }

    @app.post("/scheduler/distribution", tags=["Scheduler"])
    async def set_load_distribution(
        request: Request,
        _: None = Depends(require_permission(Permission.WORKER_MANAGE)),
    ):
        """
        تعيين توزيع الحمل بين Workers.

        يسمح بتحديد نسبة الحمل لكل Worker.
        """
        body = await request.json()
        distributions = body.get("distributions", [])

        state = get_api_state()

        # تخزين التوزيع في الحالة
        state.load_distribution = {
            d["worker_id"]: d for d in distributions
        }

        logger.info(f"Load distribution updated: {distributions}")

        return {"status": "ok", "distributions": distributions}

    # ==================== Jobs ====================

    @app.post("/jobs", tags=["Jobs"])
    async def submit_job(
        req: JobSubmitRequest,
        token: Annotated[Optional[TokenPayload], Depends(get_current_token)] = None,
        _: None = Depends(require_permission(Permission.JOB_SUBMIT)),
    ):
        """إرسال job جديد."""
        state = get_api_state()

        user_id = token.user_id if token else None

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
            user_id=user_id,
        )

        job = state.state.submit_job(submission)

        metrics.job_submitted()
        logger.job_submitted(job.job_id, job.name)

        return {"job_id": job.job_id, "status": "submitted"}

    @app.get("/jobs", tags=["Jobs"])
    async def list_jobs(
        status_filter: Optional[str] = Query(None, alias="status"),
        limit: int = Query(100, ge=1, le=1000),
        token: Annotated[Optional[TokenPayload], Depends(get_current_token)] = None,
        _: None = Depends(require_permission(Permission.JOB_READ)),
    ):
        """قائمة jobs."""
        state = get_api_state()
        jobs = state.state.get_all_jobs()

        # Filter by owner if not admin
        if token and not token.has_permission(Permission.JOB_READ_ALL):
            jobs = [j for j in jobs if j.submission.user_id == token.user_id]

        if status_filter:
            jobs = [j for j in jobs if j.status.value == status_filter]

        jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)[:limit]
        return {"jobs": [j.to_dict() for j in jobs]}

    @app.get("/jobs/{job_id}", tags=["Jobs"])
    async def get_job(
        job_id: str,
        _: None = Depends(require_permission(Permission.JOB_READ)),
    ):
        """معلومات job محدد."""
        state = get_api_state()
        job = state.state.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job.to_dict()

    @app.delete("/jobs/{job_id}", tags=["Jobs"])
    async def cancel_job(
        job_id: str,
        _: None = Depends(require_permission(Permission.JOB_CANCEL)),
    ):
        """إلغاء job."""
        state = get_api_state()
        success = state.state.cancel_job(job_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Job not found or already terminal",
            )
        return {"status": "cancelled", "job_id": job_id}

    @app.post("/jobs/{job_id}/start", tags=["Jobs"])
    async def job_started(
        job_id: str,
        worker_id: str = Query(...),
        token: Annotated[Optional[TokenPayload], Depends(get_current_token)] = None,
    ):
        """تأكيد بدء job (من Worker)."""
        state = get_api_state()

        # Validate worker
        if token and token.worker_id and token.worker_id != worker_id:
            raise HTTPException(status_code=403, detail="Worker ID mismatch")

        success = state.state.start_job(job_id, worker_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to start job")

        logger.job_started(job_id, worker_id)
        return {"status": "started"}

    @app.post("/jobs/{job_id}/complete", tags=["Jobs"])
    async def job_completed(
        job_id: str,
        req: JobCompleteRequest,
        token: Annotated[Optional[TokenPayload], Depends(get_current_token)] = None,
    ):
        """تأكيد إكمال job (من Worker)."""
        state = get_api_state()

        # Validate worker
        if token and token.worker_id and token.worker_id != req.worker_id:
            raise HTTPException(status_code=403, detail="Worker ID mismatch")

        job = state.state.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Release lease (idempotent)
        if job.lease_id:
            state.lease_manager.release_lease(job.lease_id, req.worker_id)

        result = JobResult(
            exit_code=req.exit_code,
            stdout=req.stdout,
            stderr=req.stderr,
            execution_time_seconds=req.execution_time_seconds,
            peak_memory_mb=req.peak_memory_mb,
            error_message=req.error_message,
        )

        success = state.state.complete_job(job_id, req.worker_id, result)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to complete job")

        # Metrics
        queue_time = (job.started_at - job.created_at).total_seconds() if job.started_at else 0
        metrics.job_completed(result.success, req.execution_time_seconds, queue_time)
        logger.job_completed(job_id, req.worker_id, result.success, req.execution_time_seconds)

        return {"status": "completed"}

    # ==================== Events ====================

    @app.get("/events", tags=["Events"])
    async def get_events(
        limit: int = Query(100, ge=1, le=1000),
        _: None = Depends(require_permission(Permission.CLUSTER_EVENTS)),
    ):
        """آخر الأحداث."""
        state = get_api_state()
        events = state.state.get_recent_events(limit)
        return {"events": [e.to_dict() for e in events]}

    # ==================== WebSocket ====================

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket للمراقبة الحية."""
        await websocket.accept()
        state = get_api_state()
        state.ws_connections.append(websocket)

        try:
            await websocket.send_json(
                {
                    "type": "connected",
                    "stats": state.state.get_stats(),
                }
            )

            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")

        except WebSocketDisconnect:
            pass
        finally:
            if websocket in state.ws_connections:
                state.ws_connections.remove(websocket)


# ==================== Background Tasks ====================


async def _scheduler_loop():
    """حلقة الجدولة."""
    while True:
        try:
            state = get_api_state()
            start = time.time()

            pending = state.state.get_pending_jobs()
            workers = state.state.get_healthy_workers()

            if pending and workers:
                decisions = state.scheduler.schedule(pending, workers)

                for decision in decisions:
                    # Create lease
                    lease = state.lease_manager.create_lease(
                        decision.job.job_id,
                        decision.worker.worker_id,
                    )

                    if lease:
                        state.state.schedule_job(
                            decision.job.job_id,
                            decision.worker.worker_id,
                            lease.lease_id,
                        )

                if decisions:
                    decision_time = time.time() - start
                    metrics.scheduler_decision(decision_time, len(decisions))

            # Check expired leases
            expired = state.lease_manager.check_expired_leases()
            for lease in expired:
                job = state.state.get_job(lease.job_id)
                if job and not job.is_terminal:
                    job.prepare_retry()
                    metrics.lease_expired()
                    logger.warning("Lease expired, job returned to queue", job_id=lease.job_id)

        except Exception:
            logger.error("Scheduler error", exc_info=True)

        await asyncio.sleep(1.0)


async def _health_check_loop():
    """حلقة فحص صحة workers."""
    while True:
        try:
            state = get_api_state()
            offline = state.state.check_worker_health()

            for worker_id in offline:
                # Revoke leases for offline workers
                orphaned = state.lease_manager.revoke_worker_leases(worker_id)
                for job_id in orphaned:
                    job = state.state.get_job(job_id)
                    if job and not job.is_terminal:
                        job.prepare_retry()

                metrics.worker_offline(worker_id)
                logger.worker_offline(worker_id, "heartbeat timeout")

        except Exception:
            logger.error("Health check error", exc_info=True)

        await asyncio.sleep(30)


async def _metrics_update_loop():
    """حلقة تحديث metrics."""
    while True:
        try:
            state = get_api_state()
            stats = state.state.get_stats()

            metrics.update_cluster_gauges(
                total_workers=stats["total_workers"],
                online_workers=stats["active_workers"],
                pending_jobs=stats["pending_jobs"],
                running_jobs=stats["running_jobs"],
                total_cpu=stats["total_cpu_cores"],
                available_cpu=stats["available_cpu_cores"],
                total_memory_gb=stats["total_memory_gb"],
                available_memory_gb=stats["available_memory_gb"],
                total_gpus=stats["total_gpus"],
                available_gpus=stats["available_gpus"],
            )

        except Exception:
            pass

        await asyncio.sleep(10)
