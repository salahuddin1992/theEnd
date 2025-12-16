"""
Master Service gRPC Implementation
==================================

تنفيذ MasterService لـ gRPC.
هذه الخدمة للـ Workers للتسجيل وإرسال heartbeats واستلام المهام.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import uuid

from distributed_cluster.scheduler import Scheduler
from distributed_cluster.security.auth import AuthManager, Permission
from distributed_cluster.models.lease import LeaseManager
from distributed_cluster.models.worker import WorkerInfo, WorkerStatus
from distributed_cluster.models.job import Job, JobStatus
from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.events import Event, EventType
from distributed_cluster.storage.database import Database
from distributed_cluster.observability.metrics import MetricsCollector
from distributed_cluster.observability.logging import StructuredLogger

logger = StructuredLogger("grpc.master_service")


class MasterServicer:
    """
    تنفيذ MasterService.

    يتعامل مع:
    - تسجيل Workers
    - Heartbeats
    - توزيع المهام
    - إدارة Leases
    """

    def __init__(
        self,
        scheduler: Scheduler,
        auth_manager: AuthManager,
        lease_manager: LeaseManager,
        database: Database,
        metrics: Optional[MetricsCollector] = None,
        heartbeat_interval: int = 30,
        lease_duration: int = 300,
    ):
        self.scheduler = scheduler
        self.auth_manager = auth_manager
        self.lease_manager = lease_manager
        self.database = database
        self.metrics = metrics or MetricsCollector()
        self.heartbeat_interval = heartbeat_interval
        self.lease_duration = lease_duration

        # Worker tracking
        self._workers: Dict[str, WorkerInfo] = {}
        self._worker_last_heartbeat: Dict[str, datetime] = {}

        # Pending commands for workers
        self._pending_commands: Dict[str, List[Dict]] = {}

    async def RegisterWorker(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        تسجيل worker جديد.

        Args:
            request: بيانات التسجيل
            context: gRPC context

        Returns:
            استجابة التسجيل مع worker_id و auth_token
        """
        logger.info("Worker registration request", hostname=request.get("hostname"))

        # Extract enrollment token
        enrollment_token = request.get("enrollment_token")
        fingerprint = request.get("public_key", "")[:32]  # Use first 32 bytes as fingerprint

        # Enroll worker
        approved, message, auth_token = self.auth_manager.enroll_worker(
            fingerprint=fingerprint,
            enrollment_token=enrollment_token,
        )

        if not approved:
            logger.warning("Worker registration rejected", reason=message)
            return {
                "worker_id": "",
                "approved": False,
                "rejection_reason": message,
            }

        # Generate worker ID
        worker_id = f"worker-{uuid.uuid4().hex[:12]}"

        # Parse resources
        total_resources = self._parse_resources(request.get("total_resources", {}))

        # Create worker info
        worker = WorkerInfo(
            worker_id=worker_id,
            hostname=request.get("hostname", "unknown"),
            ip_address=request.get("ip_address", "0.0.0.0"),
            port=request.get("port", 8081),
            status=WorkerStatus.READY,
            total_resources=total_resources,
            available_resources=total_resources,
            tags=request.get("tags", []),
            labels=request.get("labels", {}),
            platform=request.get("platform", "linux"),
            docker_available=request.get("docker_available", False),
            gpu_driver_version=request.get("docker_version"),
            registered_at=datetime.utcnow(),
        )

        # Save to database
        await self.database.save_worker(worker)

        # Add to scheduler
        self.scheduler.add_worker(worker)

        # Track locally
        self._workers[worker_id] = worker
        self._worker_last_heartbeat[worker_id] = datetime.utcnow()

        # Record event
        await self.database.save_event(Event(
            event_type=EventType.WORKER_REGISTERED,
            timestamp=datetime.utcnow(),
            source="master",
            worker_id=worker_id,
            message=f"Worker {worker.hostname} registered",
            data={"hostname": worker.hostname, "tags": worker.tags},
        ))

        # Metrics
        self.metrics.gauge("workers_total", len(self._workers))
        self.metrics.counter("worker_registrations_total", 1)

        logger.info("Worker registered successfully", worker_id=worker_id)

        return {
            "worker_id": worker_id,
            "approved": True,
            "rejection_reason": "",
            "heartbeat_interval_seconds": self.heartbeat_interval,
            "lease_duration_seconds": self.lease_duration,
            "auth_token": auth_token,
            "token_expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
        }

    async def Heartbeat(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        معالجة heartbeat من worker.

        Args:
            request: بيانات الـ heartbeat
            context: gRPC context

        Returns:
            استجابة مع أوامر و lease renewals
        """
        worker_id = request.get("worker_id")
        auth_token = request.get("auth_token")

        # Verify token
        payload = self.auth_manager.verify_token(auth_token)
        if not payload or not self.auth_manager.has_permission(payload, Permission.WORKER_HEARTBEAT):
            logger.warning("Invalid heartbeat token", worker_id=worker_id)
            return {"acknowledged": False}

        # Update worker
        worker = self._workers.get(worker_id)
        if not worker:
            worker = await self.database.get_worker(worker_id)
            if worker:
                self._workers[worker_id] = worker

        if not worker:
            logger.warning("Unknown worker heartbeat", worker_id=worker_id)
            return {"acknowledged": False}

        # Update resources
        free_resources = request.get("free_resources", {})
        if free_resources:
            worker.available_resources = self._parse_resources(free_resources)

        # Update status based on load
        cpu_util = request.get("cpu_utilization_percent", 0)
        running_jobs = request.get("running_jobs", [])

        if len(running_jobs) > 0:
            worker.status = WorkerStatus.BUSY
        else:
            worker.status = WorkerStatus.READY

        worker.last_heartbeat = datetime.utcnow()
        worker.active_jobs = [j.get("job_id") for j in running_jobs]

        # Update in database
        await self.database.update_worker_heartbeat(
            worker_id,
            worker.last_heartbeat,
            worker.status,
        )

        # Track heartbeat
        self._worker_last_heartbeat[worker_id] = datetime.utcnow()

        # Get pending commands
        commands = self._pending_commands.pop(worker_id, [])

        # Auto-renew leases for running jobs
        lease_renewals = []
        for job_info in running_jobs:
            lease_id = job_info.get("lease_id")
            if lease_id:
                lease = self.lease_manager.renew_lease(lease_id, worker_id)
                if lease:
                    lease_renewals.append({
                        "lease_id": lease.lease_id,
                        "job_id": lease.job_id,
                        "new_expires_at": lease.expires_at.isoformat(),
                    })

        # Metrics
        self.metrics.gauge(f"worker_cpu_utilization", cpu_util, {"worker_id": worker_id})
        self.metrics.gauge(f"worker_active_jobs", len(running_jobs), {"worker_id": worker_id})

        return {
            "acknowledged": True,
            "commands": commands,
            "lease_renewals": lease_renewals,
            "server_timestamp": datetime.utcnow().isoformat(),
        }

    async def DeregisterWorker(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        إلغاء تسجيل worker.

        Args:
            request: بيانات الإلغاء
            context: gRPC context

        Returns:
            استجابة مع المهام اليتيمة
        """
        worker_id = request.get("worker_id")
        reason = request.get("reason", "")
        graceful = request.get("graceful", True)

        logger.info("Worker deregistration", worker_id=worker_id, reason=reason)

        # Get worker's active jobs
        orphaned_jobs = []
        worker = self._workers.get(worker_id)
        if worker:
            orphaned_jobs = worker.active_jobs.copy()

            # Remove from scheduler
            self.scheduler.remove_worker(worker_id)

            # Update database
            worker.status = WorkerStatus.OFFLINE
            await self.database.save_worker(worker)

            # Remove from local tracking
            del self._workers[worker_id]
            self._worker_last_heartbeat.pop(worker_id, None)

        # Revoke all leases for this worker
        worker_leases = self.lease_manager.get_leases_by_worker(worker_id)
        for lease in worker_leases:
            self.lease_manager.revoke_lease(lease.lease_id)

        # Record event
        await self.database.save_event(Event(
            event_type=EventType.WORKER_DEREGISTERED,
            timestamp=datetime.utcnow(),
            source="master",
            worker_id=worker_id,
            message=f"Worker deregistered: {reason}",
        ))

        # Metrics
        self.metrics.gauge("workers_total", len(self._workers))
        self.metrics.counter("worker_deregistrations_total", 1)

        return {
            "acknowledged": True,
            "orphaned_jobs": orphaned_jobs,
        }

    async def PollAssignments(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        Worker يطلب مهام جديدة.

        Args:
            request: طلب المهام
            context: gRPC context

        Returns:
            قائمة المهام المعينة
        """
        worker_id = request.get("worker_id")
        auth_token = request.get("auth_token")
        max_jobs = request.get("max_jobs", 1)

        # Verify token
        payload = self.auth_manager.verify_token(auth_token)
        if not payload or not self.auth_manager.has_permission(payload, Permission.WORKER_POLL_JOBS):
            return {"assignments": []}

        # Update available resources
        available_resources = request.get("available_resources", {})
        worker = self._workers.get(worker_id)
        if worker and available_resources:
            worker.available_resources = self._parse_resources(available_resources)
            self.scheduler.update_worker(worker)

        # Get assignments
        assignments = []
        for _ in range(max_jobs):
            assignment = self.scheduler.schedule_next()
            if not assignment:
                break

            job_id, assigned_worker_id = assignment

            # Only assign if it's for this worker
            if assigned_worker_id != worker_id:
                # Put back in queue
                continue

            # Get job details
            job = await self.database.get_job(job_id)
            if not job:
                continue

            # Create lease
            lease = self.lease_manager.create_lease(
                job_id=job_id,
                worker_id=worker_id,
                duration_seconds=self.lease_duration,
            )
            if not lease:
                continue

            # Update job status
            job.status = JobStatus.SCHEDULED
            job.assigned_worker = worker_id
            job.lease_id = lease.lease_id
            job.scheduled_at = datetime.utcnow()
            await self.database.save_job(job)

            # Build assignment
            assignments.append({
                "job_id": job.job_id,
                "lease_id": lease.lease_id,
                "lease_duration_seconds": self.lease_duration,
                "lease_expires_at": lease.expires_at.isoformat(),
                "spec": self._job_to_spec(job),
                "inputs": [],  # TODO: Load from job spec
                "outputs": [],
            })

            # Record event
            await self.database.save_event(Event(
                event_type=EventType.JOB_ASSIGNED,
                timestamp=datetime.utcnow(),
                source="master",
                job_id=job_id,
                worker_id=worker_id,
                message=f"Job assigned to worker",
            ))

            logger.info("Job assigned", job_id=job_id, worker_id=worker_id)

        return {"assignments": assignments}

    async def ReportJobStarted(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        Worker يبلغ عن بدء مهمة.

        Args:
            request: بيانات البدء
            context: gRPC context

        Returns:
            استجابة مع إشارة الإلغاء
        """
        worker_id = request.get("worker_id")
        job_id = request.get("job_id")
        lease_id = request.get("lease_id")

        # Verify lease
        lease = self.lease_manager.get_lease(lease_id)
        if not lease or lease.worker_id != worker_id:
            return {"acknowledged": False, "should_cancel": True}

        # Update job
        job = await self.database.get_job(job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            await self.database.save_job(job)

        # Record event
        await self.database.save_event(Event(
            event_type=EventType.JOB_STARTED,
            timestamp=datetime.utcnow(),
            source="worker",
            job_id=job_id,
            worker_id=worker_id,
            message="Job started execution",
        ))

        self.metrics.counter("jobs_started_total", 1)

        return {"acknowledged": True, "should_cancel": False}

    async def ReportJobProgress(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        Worker يبلغ عن تقدم مهمة.

        Args:
            request: بيانات التقدم
            context: gRPC context

        Returns:
            استجابة مع إشارة الإلغاء
        """
        worker_id = request.get("worker_id")
        job_id = request.get("job_id")
        progress = request.get("progress_percent", 0)

        logger.debug("Job progress", job_id=job_id, progress=progress)

        # Check if job should be cancelled
        job = await self.database.get_job(job_id)
        should_cancel = job and job.status == JobStatus.CANCELLED

        return {"acknowledged": True, "should_cancel": should_cancel}

    async def ReportJobCompleted(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        Worker يبلغ عن اكتمال مهمة.

        Args:
            request: بيانات الاكتمال
            context: gRPC context

        Returns:
            استجابة
        """
        worker_id = request.get("worker_id")
        job_id = request.get("job_id")
        lease_id = request.get("lease_id")
        final_status = request.get("final_status", "succeeded")
        exit_code = request.get("exit_code", 0)
        error_message = request.get("error_message")

        logger.info("Job completed", job_id=job_id, status=final_status, exit_code=exit_code)

        # Release lease
        self.lease_manager.release_lease(lease_id, worker_id)

        # Update job
        job = await self.database.get_job(job_id)
        if job:
            if final_status == "succeeded" or exit_code == 0:
                job.status = JobStatus.COMPLETED
            else:
                job.status = JobStatus.FAILED

            job.completed_at = datetime.utcnow()

            # Parse result
            from distributed_cluster.models.job import JobResult
            job.result = JobResult(
                exit_code=exit_code,
                stdout=request.get("stdout_tail", ""),
                stderr=request.get("stderr_tail", ""),
                execution_time_seconds=request.get("execution_duration_seconds", 0),
                peak_memory_mb=request.get("resource_usage", {}).get("peak_memory_bytes", 0) // (1024 * 1024),
                error_message=error_message,
            )

            await self.database.save_job(job)

            # Update worker stats
            worker = self._workers.get(worker_id)
            if worker:
                if job.status == JobStatus.COMPLETED:
                    worker.completed_jobs_count += 1
                else:
                    worker.failed_jobs_count += 1
                if job_id in worker.active_jobs:
                    worker.active_jobs.remove(job_id)

        # Record event
        event_type = EventType.JOB_SUCCEEDED if exit_code == 0 else EventType.JOB_FAILED
        await self.database.save_event(Event(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            source="worker",
            job_id=job_id,
            worker_id=worker_id,
            message=f"Job completed with exit code {exit_code}",
            data={"exit_code": exit_code, "error": error_message},
        ))

        # Metrics
        if exit_code == 0:
            self.metrics.counter("jobs_succeeded_total", 1)
        else:
            self.metrics.counter("jobs_failed_total", 1)

        return {"acknowledged": True}

    async def RenewLease(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        تجديد lease.

        Args:
            request: بيانات التجديد
            context: gRPC context

        Returns:
            استجابة التجديد
        """
        worker_id = request.get("worker_id")
        lease_id = request.get("lease_id")

        lease = self.lease_manager.renew_lease(lease_id, worker_id)

        if lease:
            return {
                "renewed": True,
                "new_expires_at": lease.expires_at.isoformat(),
                "rejection_reason": "",
            }
        else:
            return {
                "renewed": False,
                "new_expires_at": "",
                "rejection_reason": "Lease not found or cannot be renewed",
            }

    async def ReleaseLease(
        self,
        request: Dict[str, Any],
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        إطلاق lease.

        Args:
            request: بيانات الإطلاق
            context: gRPC context

        Returns:
            استجابة
        """
        worker_id = request.get("worker_id")
        lease_id = request.get("lease_id")

        released = self.lease_manager.release_lease(lease_id, worker_id)

        return {"released": released}

    def send_command_to_worker(self, worker_id: str, command: Dict) -> None:
        """
        إرسال أمر لـ worker (سيستلمه في الـ heartbeat التالي).

        Args:
            worker_id: معرف الـ worker
            command: الأمر
        """
        if worker_id not in self._pending_commands:
            self._pending_commands[worker_id] = []
        self._pending_commands[worker_id].append(command)

    def _parse_resources(self, data: Dict) -> ResourceSpec:
        """تحويل بيانات الموارد."""
        return ResourceSpec(
            cpu_cores=data.get("cpu_cores", 1),
            memory_mb=data.get("memory_bytes", 0) // (1024 * 1024),
            gpu_count=data.get("gpu_count", 0),
            gpu_memory_mb=data.get("gpu_memory_bytes", 0) // (1024 * 1024),
        )

    def _job_to_spec(self, job: Job) -> Dict:
        """تحويل Job إلى spec dict."""
        return {
            "name": job.submission.name,
            "priority": job.submission.priority.value,
            "runtime": {
                "type": "process",
                "command": job.submission.command,
                "working_dir": job.submission.working_dir or "/tmp",
            },
            "resources": {
                "cpu_cores": job.submission.required_resources.cpu_cores,
                "memory_bytes": job.submission.required_resources.memory_mb * 1024 * 1024,
                "gpu_count": job.submission.required_resources.gpu_count,
            },
            "policy": {
                "max_retries": job.submission.max_retries,
                "timeout_seconds": job.submission.timeout_seconds,
            },
            "environment": job.submission.environment,
        }
