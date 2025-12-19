"""
Admin Dashboard API
===================

API لوحة تحكم المدير:
- إحصائيات الكلاستر
- إدارة العمال
- إدارة المهام
- المقاييس والرسوم البيانية
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class ClusterOverview(BaseModel):
    """نظرة عامة على الكلاستر."""

    cluster_name: str
    status: str
    uptime_seconds: float

    # Workers
    total_workers: int
    online_workers: int
    busy_workers: int
    offline_workers: int

    # Jobs
    pending_jobs: int
    running_jobs: int
    completed_jobs_24h: int
    failed_jobs_24h: int

    # Resources
    total_cpu_cores: float
    used_cpu_cores: float
    total_memory_gb: float
    used_memory_gb: float
    total_gpus: int
    used_gpus: int

    # Performance
    avg_queue_time_seconds: float
    avg_execution_time_seconds: float
    job_success_rate: float


class WorkerSummary(BaseModel):
    """ملخص worker."""

    worker_id: str
    hostname: str
    status: str
    cpu_cores: float
    memory_gb: float
    gpu_count: int
    active_jobs: int
    completed_jobs: int
    failed_jobs: int
    last_heartbeat: Optional[str]
    uptime_seconds: Optional[float]
    tags: List[str]


class JobSummary(BaseModel):
    """ملخص مهمة."""

    job_id: str
    name: str
    status: str
    priority: int
    owner: Optional[str]
    assigned_worker: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    execution_time_seconds: Optional[float]
    exit_code: Optional[int]


class TimeSeriesPoint(BaseModel):
    """نقطة بيانات زمنية."""

    timestamp: str
    value: float


class MetricsSummary(BaseModel):
    """ملخص المقاييس."""

    name: str
    current_value: float
    min_value: float
    max_value: float
    avg_value: float
    data_points: List[TimeSeriesPoint]


class AlertSummary(BaseModel):
    """ملخص تنبيه."""

    alert_id: str
    name: str
    severity: str
    state: str
    message: str
    started_at: str
    resolved_at: Optional[str]


class EventSummary(BaseModel):
    """ملخص حدث."""

    event_type: str
    timestamp: str
    source: str
    message: str
    job_id: Optional[str]
    worker_id: Optional[str]


class QuotaUsage(BaseModel):
    """استخدام الحصة."""

    scope: str
    scope_id: str
    cpu_used: float
    cpu_limit: float
    memory_used_gb: float
    memory_limit_gb: float
    gpu_used: int
    gpu_limit: int
    concurrent_jobs: int
    concurrent_jobs_limit: int


# =============================================================================
# Dashboard API Router
# =============================================================================


def create_dashboard_router(
    scheduler,
    database,
    health_checker,
    alert_manager,
    quota_manager,
    autoscaler=None,
) -> APIRouter:
    """
    إنشاء router لـ Dashboard API.

    Args:
        scheduler: المجدول
        database: قاعدة البيانات
        health_checker: مدقق الصحة
        alert_manager: مدير التنبيهات
        quota_manager: مدير الحصص
        autoscaler: محجم تلقائي (اختياري)
    """
    router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

    start_time = datetime.utcnow()

    # =========================================================================
    # Cluster Overview
    # =========================================================================

    @router.get("/overview", response_model=ClusterOverview)
    async def get_cluster_overview():
        """نظرة عامة على الكلاستر."""
        workers = await database.get_all_workers()
        now = datetime.utcnow()

        # Worker stats
        online = [w for w in workers if w.status.value in ("ready", "busy")]
        busy = [w for w in workers if w.status.value == "busy"]
        offline = [w for w in workers if w.status.value == "offline"]

        # Resource stats
        total_cpu = sum(w.total_resources.cpu_cores for w in online)
        used_cpu = sum(w.total_resources.cpu_cores - w.available_resources.cpu_cores for w in online)
        total_mem = sum(w.total_resources.memory_mb for w in online) / 1024
        used_mem = sum(w.total_resources.memory_mb - w.available_resources.memory_mb for w in online) / 1024
        total_gpu = sum(w.total_resources.gpu_count for w in online)
        used_gpu = sum(w.total_resources.gpu_count - w.available_resources.gpu_count for w in online)

        # Job stats
        from distributed_cluster.models.job import JobStatus

        pending = await database.get_jobs_by_status(JobStatus.PENDING)
        running = await database.get_jobs_by_status(JobStatus.RUNNING)
        completed = await database.get_jobs_by_status(JobStatus.COMPLETED)
        failed = await database.get_jobs_by_status(JobStatus.FAILED)

        # Filter 24h
        day_ago = now - timedelta(days=1)
        completed_24h = [j for j in completed if j.completed_at and j.completed_at > day_ago]
        failed_24h = [j for j in failed if j.completed_at and j.completed_at > day_ago]

        # Performance stats
        avg_queue = 0
        avg_exec = 0
        success_rate = 0

        recent_completed = completed_24h + failed_24h
        if recent_completed:
            queue_times = []
            exec_times = []
            for j in recent_completed:
                if j.started_at and j.created_at:
                    queue_times.append((j.started_at - j.created_at).total_seconds())
                if j.completed_at and j.started_at:
                    exec_times.append((j.completed_at - j.started_at).total_seconds())

            avg_queue = sum(queue_times) / len(queue_times) if queue_times else 0
            avg_exec = sum(exec_times) / len(exec_times) if exec_times else 0
            success_rate = len(completed_24h) / len(recent_completed) * 100

        return ClusterOverview(
            cluster_name="nebula-cluster",
            status="healthy" if len(online) > 0 else "degraded",
            uptime_seconds=(now - start_time).total_seconds(),
            total_workers=len(workers),
            online_workers=len(online),
            busy_workers=len(busy),
            offline_workers=len(offline),
            pending_jobs=len(pending),
            running_jobs=len(running),
            completed_jobs_24h=len(completed_24h),
            failed_jobs_24h=len(failed_24h),
            total_cpu_cores=total_cpu,
            used_cpu_cores=used_cpu,
            total_memory_gb=total_mem,
            used_memory_gb=used_mem,
            total_gpus=total_gpu,
            used_gpus=used_gpu,
            avg_queue_time_seconds=avg_queue,
            avg_execution_time_seconds=avg_exec,
            job_success_rate=success_rate,
        )

    # =========================================================================
    # Workers
    # =========================================================================

    @router.get("/workers", response_model=List[WorkerSummary])
    async def list_workers(
        status: Optional[str] = Query(None),
        tag: Optional[str] = Query(None),
    ):
        """قائمة العمال."""
        workers = await database.get_all_workers()

        # Filter
        if status:
            workers = [w for w in workers if w.status.value == status]
        if tag:
            workers = [w for w in workers if tag in w.tags]

        return [
            WorkerSummary(
                worker_id=w.worker_id,
                hostname=w.hostname,
                status=w.status.value,
                cpu_cores=w.total_resources.cpu_cores,
                memory_gb=w.total_resources.memory_mb / 1024,
                gpu_count=w.total_resources.gpu_count,
                active_jobs=len(w.active_jobs),
                completed_jobs=w.completed_jobs_count,
                failed_jobs=w.failed_jobs_count,
                last_heartbeat=w.last_heartbeat.isoformat() if w.last_heartbeat else None,
                uptime_seconds=(datetime.utcnow() - w.registered_at).total_seconds() if w.registered_at else None,
                tags=w.tags,
            )
            for w in workers
        ]

    @router.get("/workers/{worker_id}")
    async def get_worker_details(worker_id: str):
        """تفاصيل worker."""
        worker = await database.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")

        jobs = await database.get_jobs_by_worker(worker_id)

        return {
            "worker": WorkerSummary(
                worker_id=worker.worker_id,
                hostname=worker.hostname,
                status=worker.status.value,
                cpu_cores=worker.total_resources.cpu_cores,
                memory_gb=worker.total_resources.memory_mb / 1024,
                gpu_count=worker.total_resources.gpu_count,
                active_jobs=len(worker.active_jobs),
                completed_jobs=worker.completed_jobs_count,
                failed_jobs=worker.failed_jobs_count,
                last_heartbeat=worker.last_heartbeat.isoformat() if worker.last_heartbeat else None,
                uptime_seconds=(datetime.utcnow() - worker.registered_at).total_seconds(),
                tags=worker.tags,
            ),
            "active_jobs": [j.job_id for j in jobs if j.status.value == "running"],
            "recent_jobs": [
                JobSummary(
                    job_id=j.job_id,
                    name=j.submission.name,
                    status=j.status.value,
                    priority=j.submission.priority.value,
                    owner=j.submission.owner,
                    assigned_worker=j.assigned_worker,
                    created_at=j.created_at.isoformat(),
                    started_at=j.started_at.isoformat() if j.started_at else None,
                    completed_at=j.completed_at.isoformat() if j.completed_at else None,
                    execution_time_seconds=(
                        (j.completed_at - j.started_at).total_seconds() if j.completed_at and j.started_at else None
                    ),
                    exit_code=j.result.exit_code if j.result else None,
                )
                for j in sorted(jobs, key=lambda x: x.created_at, reverse=True)[:10]
            ],
        }

    @router.post("/workers/{worker_id}/drain")
    async def drain_worker(worker_id: str):
        """إفراغ worker (إيقاف قبول مهام جديدة)."""
        worker = await database.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")

        from distributed_cluster.models.worker import WorkerStatus

        worker.status = WorkerStatus.DRAINING
        await database.save_worker(worker)

        return {"status": "draining", "worker_id": worker_id}

    # =========================================================================
    # Jobs
    # =========================================================================

    @router.get("/jobs", response_model=List[JobSummary])
    async def list_jobs(
        status: Optional[str] = Query(None),
        owner: Optional[str] = Query(None),
        limit: int = Query(100, le=1000),
        offset: int = Query(0),
    ):
        """قائمة المهام."""
        from distributed_cluster.models.job import JobStatus

        if status:
            try:
                job_status = JobStatus(status)
                jobs = await database.get_jobs_by_status(job_status)
            except ValueError:
                jobs = []
        else:
            # Get all statuses
            jobs = []
            for s in JobStatus:
                jobs.extend(await database.get_jobs_by_status(s))

        # Filter by owner
        if owner:
            jobs = [j for j in jobs if j.submission.owner == owner]

        # Sort and paginate
        jobs.sort(key=lambda x: x.created_at, reverse=True)
        jobs = jobs[offset : offset + limit]

        return [
            JobSummary(
                job_id=j.job_id,
                name=j.submission.name,
                status=j.status.value,
                priority=j.submission.priority.value,
                owner=j.submission.owner,
                assigned_worker=j.assigned_worker,
                created_at=j.created_at.isoformat(),
                started_at=j.started_at.isoformat() if j.started_at else None,
                completed_at=j.completed_at.isoformat() if j.completed_at else None,
                execution_time_seconds=(
                    (j.completed_at - j.started_at).total_seconds() if j.completed_at and j.started_at else None
                ),
                exit_code=j.result.exit_code if j.result else None,
            )
            for j in jobs
        ]

    @router.get("/jobs/{job_id}")
    async def get_job_details(job_id: str):
        """تفاصيل مهمة."""
        job = await database.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return {
            "job": JobSummary(
                job_id=job.job_id,
                name=job.submission.name,
                status=job.status.value,
                priority=job.submission.priority.value,
                owner=job.submission.owner,
                assigned_worker=job.assigned_worker,
                created_at=job.created_at.isoformat(),
                started_at=job.started_at.isoformat() if job.started_at else None,
                completed_at=job.completed_at.isoformat() if job.completed_at else None,
                execution_time_seconds=(
                    (job.completed_at - job.started_at).total_seconds() if job.completed_at and job.started_at else None
                ),
                exit_code=job.result.exit_code if job.result else None,
            ),
            "submission": {
                "command": job.submission.command,
                "args": job.submission.args if hasattr(job.submission, "args") else [],
                "environment": job.submission.environment,
                "resources": {
                    "cpu_cores": job.submission.required_resources.cpu_cores,
                    "memory_mb": job.submission.required_resources.memory_mb,
                    "gpu_count": job.submission.required_resources.gpu_count,
                },
                "timeout_seconds": job.submission.timeout_seconds,
                "max_retries": job.submission.max_retries,
            },
            "result": (
                {
                    "exit_code": job.result.exit_code,
                    "stdout": job.result.stdout[:1000] if job.result and job.result.stdout else None,
                    "stderr": job.result.stderr[:1000] if job.result and job.result.stderr else None,
                    "error_message": job.result.error_message if job.result else None,
                }
                if job.result
                else None
            ),
        }

    # =========================================================================
    # Metrics
    # =========================================================================

    @router.get("/metrics/summary")
    async def get_metrics_summary():
        """ملخص المقاييس."""
        # This would integrate with the Prometheus metrics
        workers = await database.get_all_workers()
        online = [w for w in workers if w.status.value in ("ready", "busy")]

        return {
            "cpu_utilization": {
                "current": (
                    sum(
                        (w.total_resources.cpu_cores - w.available_resources.cpu_cores)
                        / w.total_resources.cpu_cores
                        * 100
                        for w in online
                        if w.total_resources.cpu_cores > 0
                    )
                    / len(online)
                    if online
                    else 0
                ),
                "unit": "percent",
            },
            "memory_utilization": {
                "current": (
                    sum(
                        (w.total_resources.memory_mb - w.available_resources.memory_mb)
                        / w.total_resources.memory_mb
                        * 100
                        for w in online
                        if w.total_resources.memory_mb > 0
                    )
                    / len(online)
                    if online
                    else 0
                ),
                "unit": "percent",
            },
            "pending_jobs": {
                "current": scheduler.pending_jobs_count,
                "unit": "count",
            },
            "running_jobs": {
                "current": len([w for w in workers for _ in w.active_jobs]),
                "unit": "count",
            },
        }

    # =========================================================================
    # Alerts
    # =========================================================================

    @router.get("/alerts", response_model=List[AlertSummary])
    async def list_alerts(active_only: bool = Query(True)):
        """قائمة التنبيهات."""
        if active_only:
            alerts = alert_manager.get_active_alerts()
        else:
            alerts = alert_manager.get_all_alerts()

        return [
            AlertSummary(
                alert_id=a.alert_id,
                name=a.name,
                severity=a.severity.value,
                state=a.state.value,
                message=a.message,
                started_at=a.started_at.isoformat(),
                resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
            )
            for a in alerts
        ]

    # =========================================================================
    # Health
    # =========================================================================

    @router.get("/health")
    async def get_health_status():
        """حالة الصحة."""
        report = await health_checker.check_all()
        return report.to_dict()

    # =========================================================================
    # Events
    # =========================================================================

    @router.get("/events", response_model=List[EventSummary])
    async def list_events(limit: int = Query(50, le=200)):
        """قائمة الأحداث."""
        events = await database.get_recent_events(limit=limit)

        return [
            EventSummary(
                event_type=e.event_type.value,
                timestamp=e.timestamp.isoformat(),
                source=e.source,
                message=e.message or "",
                job_id=e.job_id,
                worker_id=e.worker_id,
            )
            for e in events
        ]

    # =========================================================================
    # Quotas
    # =========================================================================

    @router.get("/quotas")
    async def list_quotas():
        """قائمة الحصص."""
        quotas = quota_manager.get_all_quotas()
        return {"quotas": quotas}

    # =========================================================================
    # Auto-scaling
    # =========================================================================

    if autoscaler:

        @router.get("/autoscaler/status")
        async def get_autoscaler_status():
            """حالة التحجيم التلقائي."""
            return autoscaler.get_status()

        @router.get("/autoscaler/metrics")
        async def get_autoscaler_metrics():
            """مقاييس التحجيم التلقائي."""
            return autoscaler.get_current_metrics()

    return router


# =============================================================================
# Standalone Dashboard Server
# =============================================================================


def create_dashboard_app(
    scheduler,
    database,
    health_checker,
    alert_manager,
    quota_manager,
    autoscaler=None,
):
    """
    إنشاء تطبيق FastAPI لـ Dashboard.

    Usage:
        app = create_dashboard_app(scheduler, database, ...)
        uvicorn.run(app, host="0.0.0.0", port=8081)
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="NebulaCompute Dashboard",
        description="Admin Dashboard API for NebulaCompute",
        version="0.1.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Dashboard router
    router = create_dashboard_router(
        scheduler=scheduler,
        database=database,
        health_checker=health_checker,
        alert_manager=alert_manager,
        quota_manager=quota_manager,
        autoscaler=autoscaler,
    )
    app.include_router(router)

    @app.get("/")
    async def root():
        return {"message": "NebulaCompute Dashboard API", "docs": "/docs"}

    return app
