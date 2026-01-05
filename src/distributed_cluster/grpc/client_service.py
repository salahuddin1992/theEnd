"""
Client Service gRPC Implementation
==================================

تنفيذ ClientService لـ gRPC.
هذه الخدمة للمستخدمين لإرسال المهام ومتابعتها.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from distributed_cluster.models.events import Event, EventType
from distributed_cluster.models.job import Job, JobPriority, JobStatus, JobSubmission
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.worker import WorkerStatus
from distributed_cluster.observability.logging import StructuredLogger
from distributed_cluster.observability.metrics import MetricsCollector
from distributed_cluster.scheduler import Scheduler
from distributed_cluster.security.auth import AuthManager
from distributed_cluster.storage.database import Database

logger = StructuredLogger("grpc.client_service")


class ClientServicer:
    """
    تنفيذ ClientService.

    يتعامل مع:
    - إرسال المهام
    - الاستعلام عن المهام
    - إلغاء المهام
    - معلومات الكلاستر
    """

    def __init__(
        self,
        scheduler: Scheduler,
        auth_manager: AuthManager,
        database: Database,
        metrics: Optional[MetricsCollector] = None,
    ):
        self.scheduler = scheduler
        self.auth_manager = auth_manager
        self.database = database
        self.metrics = metrics or MetricsCollector()

        # Idempotency tracking
        self._idempotency_cache: Dict[str, str] = {}  # key -> job_id

    async def SubmitJob(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        إرسال مهمة جديدة.

        Args:
            request: بيانات المهمة
            context: gRPC context

        Returns:
            job_id و status
        """
        # Check idempotency
        idempotency_key = request.get("idempotency_key")
        if idempotency_key and idempotency_key in self._idempotency_cache:
            existing_job_id = self._idempotency_cache[idempotency_key]
            job = await self.database.get_job(existing_job_id)
            if job:
                logger.info("Returning existing job for idempotency key", job_id=existing_job_id, key=idempotency_key)
                return {
                    "job_id": existing_job_id,
                    "status": job.status.value,
                }

        # Parse spec
        spec = request.get("spec", {})

        # Create job submission
        resources_data = spec.get("resources", {})
        submission = JobSubmission(
            name=spec.get("name", "unnamed-job"),
            command=spec.get("runtime", {}).get("command", []),
            required_resources=ResourceSpec(
                cpu_cores=resources_data.get("cpu_cores", 1),
                memory_mb=resources_data.get("memory_bytes", 512 * 1024 * 1024) // (1024 * 1024),
                gpu_count=resources_data.get("gpu_count", 0),
            ),
            priority=JobPriority(spec.get("priority", 5)),
            timeout_seconds=spec.get("policy", {}).get("timeout_seconds", 3600),
            max_retries=spec.get("policy", {}).get("max_retries", 3),
            environment=spec.get("environment", {}),
            labels=spec.get("labels", {}),
            owner=spec.get("owner"),
            tags=spec.get("tags", []),
        )

        # Generate job ID
        job_id = f"job-{uuid.uuid4().hex[:16]}"

        # Create job
        job = Job(
            job_id=job_id,
            submission=submission,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        # Save to database
        await self.database.save_job(job)

        # Submit to scheduler
        self.scheduler.submit_job(job)

        # Track idempotency
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = job_id

        # Record event
        await self.database.save_event(
            Event(
                event_type=EventType.JOB_SUBMITTED,
                timestamp=datetime.now(timezone.utc),
                source="client",
                job_id=job_id,
                message=f"Job '{submission.name}' submitted",
                data={"name": submission.name, "priority": submission.priority.value},
            )
        )

        # Metrics
        self.metrics.counter("jobs_submitted_total", 1)
        self.metrics.gauge("jobs_queued", self.scheduler.pending_jobs_count)

        logger.info("Job submitted", job_id=job_id, name=submission.name)

        return {
            "job_id": job_id,
            "status": JobStatus.PENDING.value,
        }

    async def GetJob(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        الحصول على تفاصيل مهمة.

        Args:
            request: job_id
            context: gRPC context

        Returns:
            تفاصيل المهمة
        """
        job_id = request.get("job_id")

        job = await self.database.get_job(job_id)
        if not job:
            return {"job": None}

        return {"job": self._job_to_proto(job)}

    async def CancelJob(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        إلغاء مهمة.

        Args:
            request: job_id و reason
            context: gRPC context

        Returns:
            نتيجة الإلغاء
        """
        job_id = request.get("job_id")
        reason = request.get("reason", "User requested cancellation")

        job = await self.database.get_job(job_id)
        if not job:
            return {"canceled": False, "final_status": "unknown"}

        # Can only cancel pending or running jobs
        if job.status not in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.SCHEDULED):
            return {
                "canceled": False,
                "final_status": job.status.value,
            }

        # Update status
        old_status = job.status
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        await self.database.save_job(job)

        # Remove from scheduler if pending
        if old_status == JobStatus.PENDING:
            self.scheduler.cancel_job(job_id)

        # Record event
        await self.database.save_event(
            Event(
                event_type=EventType.JOB_CANCELLED,
                timestamp=datetime.now(timezone.utc),
                source="client",
                job_id=job_id,
                message=f"Job cancelled: {reason}",
            )
        )

        logger.info("Job cancelled", job_id=job_id, reason=reason)

        return {
            "canceled": True,
            "final_status": JobStatus.CANCELLED.value,
        }

    async def ListJobs(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        قائمة المهام.

        Args:
            request: filters و pagination
            context: gRPC context

        Returns:
            قائمة المهام
        """
        status_filter = request.get("status_filter", [])
        owner_filter = request.get("owner_filter")
        limit = request.get("limit", 100)
        offset = request.get("offset", 0)

        jobs = []

        if status_filter:
            for status_str in status_filter:
                try:
                    status = JobStatus(status_str)
                    status_jobs = await self.database.get_jobs_by_status(status)
                    jobs.extend(status_jobs)
                except ValueError:
                    pass
        else:
            # Get all jobs - we'd need to implement this in database
            # For now, get jobs by common statuses
            for status in [JobStatus.PENDING, JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.FAILED]:
                status_jobs = await self.database.get_jobs_by_status(status)
                jobs.extend(status_jobs)

        # Filter by owner
        if owner_filter:
            jobs = [j for j in jobs if j.submission.owner == owner_filter]

        # Sort by created_at desc
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        # Paginate
        total_count = len(jobs)
        jobs = jobs[offset : offset + limit]

        return {
            "jobs": [self._job_to_proto(j) for j in jobs],
            "total_count": total_count,
        }

    async def ListWorkers(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        قائمة Workers.

        Args:
            request: filters
            context: gRPC context

        Returns:
            قائمة Workers
        """
        status_filter = request.get("status_filter", [])
        tags_filter = request.get("tags_filter", [])
        limit = request.get("limit", 100)

        workers = await self.database.get_all_workers()

        # Filter by status
        if status_filter:
            workers = [w for w in workers if w.status.value in status_filter]

        # Filter by tags
        if tags_filter:
            workers = [w for w in workers if all(t in w.tags for t in tags_filter)]

        # Limit
        workers = workers[:limit]

        return {
            "workers": [self._worker_to_proto(w) for w in workers],
        }

    async def GetWorker(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        الحصول على تفاصيل worker.

        Args:
            request: worker_id
            context: gRPC context

        Returns:
            تفاصيل Worker
        """
        worker_id = request.get("worker_id")

        worker = await self.database.get_worker(worker_id)
        if not worker:
            return {"worker": None, "running_jobs": []}

        # Get running jobs
        running_jobs = await self.database.get_jobs_by_worker(worker_id)
        running_jobs = [j for j in running_jobs if j.status == JobStatus.RUNNING]

        return {
            "worker": self._worker_to_proto(worker),
            "running_jobs": [
                {
                    "job_id": j.job_id,
                    "lease_id": j.lease_id,
                    "status": j.status.value,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                }
                for j in running_jobs
            ],
        }

    async def GetClusterStats(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        إحصائيات الكلاستر.

        Args:
            request: (empty)
            context: gRPC context

        Returns:
            إحصائيات شاملة
        """
        workers = await self.database.get_all_workers()

        total_workers = len(workers)
        online_workers = sum(1 for w in workers if w.status in (WorkerStatus.READY, WorkerStatus.BUSY))
        busy_workers = sum(1 for w in workers if w.status == WorkerStatus.BUSY)

        # Count jobs
        pending_jobs = await self.database.get_jobs_by_status(JobStatus.PENDING)
        running_jobs = await self.database.get_jobs_by_status(JobStatus.RUNNING)
        completed_jobs = await self.database.get_jobs_by_status(JobStatus.COMPLETED)
        failed_jobs = await self.database.get_jobs_by_status(JobStatus.FAILED)

        # Calculate resources
        total_resources = ResourceSpec()
        free_resources = ResourceSpec()

        for worker in workers:
            if worker.status != WorkerStatus.OFFLINE:
                total_resources.cpu_cores += worker.total_resources.cpu_cores
                total_resources.memory_mb += worker.total_resources.memory_mb
                total_resources.gpu_count += worker.total_resources.gpu_count

                free_resources.cpu_cores += worker.available_resources.cpu_cores
                free_resources.memory_mb += worker.available_resources.memory_mb
                free_resources.gpu_count += worker.available_resources.gpu_count

        return {
            "total_workers": total_workers,
            "online_workers": online_workers,
            "busy_workers": busy_workers,
            "queued_jobs": len(pending_jobs),
            "running_jobs": len(running_jobs),
            "completed_jobs_total": len(completed_jobs),
            "failed_jobs_total": len(failed_jobs),
            "total_resources": {
                "cpu_cores": total_resources.cpu_cores,
                "memory_bytes": total_resources.memory_mb * 1024 * 1024,
                "gpu_count": total_resources.gpu_count,
            },
            "free_resources": {
                "cpu_cores": free_resources.cpu_cores,
                "memory_bytes": free_resources.memory_mb * 1024 * 1024,
                "gpu_count": free_resources.gpu_count,
            },
        }

    def _job_to_proto(self, job: Job) -> Dict:
        """تحويل Job إلى proto format."""
        return {
            "job_id": job.job_id,
            "spec": {
                "name": job.submission.name,
                "priority": job.submission.priority.value,
                "runtime": {
                    "type": "process",
                    "command": job.submission.command,
                },
                "resources": {
                    "cpu_cores": job.submission.required_resources.cpu_cores,
                    "memory_bytes": job.submission.required_resources.memory_mb * 1024 * 1024,
                    "gpu_count": job.submission.required_resources.gpu_count,
                },
                "environment": job.submission.environment,
                "labels": job.submission.labels,
                "owner": job.submission.owner,
            },
            "status": job.status.value,
            "assigned_worker": job.assigned_worker,
            "current_lease_id": job.lease_id,
            "attempt_count": job.retry_count,
            "created_at": job.created_at.isoformat(),
            "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "exit_code": job.result.exit_code if job.result else None,
            "error_message": job.result.error_message if job.result else None,
        }

    def _worker_to_proto(self, worker) -> Dict:
        """تحويل Worker إلى proto format."""
        return {
            "worker_id": worker.worker_id,
            "hostname": worker.hostname,
            "ip_address": worker.ip_address,
            "status": worker.status.value,
            "total_resources": {
                "cpu_cores": worker.total_resources.cpu_cores,
                "memory_bytes": worker.total_resources.memory_mb * 1024 * 1024,
                "gpu_count": worker.total_resources.gpu_count,
            },
            "free_resources": {
                "cpu_cores": worker.available_resources.cpu_cores,
                "memory_bytes": worker.available_resources.memory_mb * 1024 * 1024,
                "gpu_count": worker.available_resources.gpu_count,
            },
            "tags": worker.tags,
            "labels": worker.labels,
            "platform": worker.platform,
            "registered_at": worker.registered_at.isoformat(),
            "last_heartbeat_at": worker.last_heartbeat.isoformat() if worker.last_heartbeat else None,
            "active_jobs_count": len(worker.active_jobs),
            "completed_jobs_count": worker.completed_jobs_count,
            "failed_jobs_count": worker.failed_jobs_count,
        }
