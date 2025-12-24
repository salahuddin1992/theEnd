# -*- coding: utf-8 -*-
"""
GraphQL Resolvers for NebulaCompute.

Implements query and mutation resolvers.

محللات GraphQL للاستعلامات والتعديلات.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ResolverContext:
    """Context passed to resolvers."""

    user_id: Optional[str] = None
    auth_token: Optional[str] = None
    request_id: Optional[str] = None
    permissions: List[str] = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []

    def has_permission(self, permission: str) -> bool:
        """Check if context has a permission."""
        return permission in self.permissions or "admin" in self.permissions


@dataclass
class ResolverInfo:
    """Information about the resolver being executed."""

    field_name: str
    parent_type: str
    return_type: str
    path: List[str]


class ResolverError(Exception):
    """Error raised by resolvers."""

    def __init__(
        self,
        message: str,
        code: str = "RESOLVER_ERROR",
        extensions: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.extensions = extensions or {}


class QueryResolver:
    """
    Resolver for GraphQL queries.

    محلل استعلامات GraphQL.
    """

    def __init__(self, services: Dict[str, Any]):
        """
        Initialize query resolver.

        Args:
            services: Dictionary of service instances
        """
        self.services = services
        self._resolvers: Dict[str, Callable] = {}
        self._register_resolvers()

    def _register_resolvers(self) -> None:
        """Register all query resolvers."""
        self._resolvers = {
            "job": self.resolve_job,
            "jobs": self.resolve_jobs,
            "worker": self.resolve_worker,
            "workers": self.resolve_workers,
            "cluster": self.resolve_cluster,
            "queues": self.resolve_queues,
            "metrics": self.resolve_metrics,
            "slas": self.resolve_slas,
        }

    async def resolve(
        self,
        field_name: str,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Any:
        """
        Resolve a query field.

        حل حقل استعلام.
        """
        resolver = self._resolvers.get(field_name)
        if not resolver:
            raise ResolverError(
                f"Unknown query field: {field_name}",
                code="UNKNOWN_FIELD",
            )

        try:
            return await resolver(args, context, info)
        except ResolverError:
            raise
        except Exception as e:
            logger.error(f"Resolver error for {field_name}: {e}")
            raise ResolverError(str(e), code="INTERNAL_ERROR")

    async def resolve_job(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Optional[Dict[str, Any]]:
        """Resolve single job query."""
        job_id = args.get("id")
        if not job_id:
            raise ResolverError("Job ID is required", code="INVALID_ARGUMENT")

        job_manager = self.services.get("job_manager")
        if not job_manager:
            return self._mock_job(job_id)

        job = await job_manager.get_job(job_id)
        if not job:
            return None

        return self._format_job(job)

    async def resolve_jobs(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> List[Dict[str, Any]]:
        """Resolve jobs list query."""
        filter_input = args.get("filter", {})
        limit = args.get("limit", 100)
        offset = args.get("offset", 0)

        job_manager = self.services.get("job_manager")
        if not job_manager:
            return [self._mock_job(f"job-{i}") for i in range(min(limit, 5))]

        jobs = await job_manager.list_jobs(
            status=filter_input.get("status"),
            priority=filter_input.get("priority"),
            limit=limit,
            offset=offset,
        )

        return [self._format_job(job) for job in jobs]

    async def resolve_worker(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Optional[Dict[str, Any]]:
        """Resolve single worker query."""
        worker_id = args.get("id")
        if not worker_id:
            raise ResolverError("Worker ID is required", code="INVALID_ARGUMENT")

        worker_manager = self.services.get("worker_manager")
        if not worker_manager:
            return self._mock_worker(worker_id)

        worker = await worker_manager.get_worker(worker_id)
        if not worker:
            return None

        return self._format_worker(worker)

    async def resolve_workers(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> List[Dict[str, Any]]:
        """Resolve workers list query."""
        status = args.get("status")

        worker_manager = self.services.get("worker_manager")
        if not worker_manager:
            return [self._mock_worker(f"worker-{i}") for i in range(3)]

        workers = await worker_manager.list_workers(status=status)
        return [self._format_worker(w) for w in workers]

    async def resolve_cluster(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Dict[str, Any]:
        """Resolve cluster information query."""
        cluster_manager = self.services.get("cluster_manager")
        if not cluster_manager:
            return self._mock_cluster()

        stats = await cluster_manager.get_statistics()
        return self._format_cluster(stats)

    async def resolve_queues(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> List[Dict[str, Any]]:
        """Resolve queues query."""
        scheduler = self.services.get("scheduler")
        if not scheduler:
            return [
                {"name": "default", "size": 10, "priority": "NORMAL"},
                {"name": "high-priority", "size": 3, "priority": "HIGH"},
            ]

        queues = await scheduler.get_queues()
        return [self._format_queue(q) for q in queues]

    async def resolve_metrics(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> List[Dict[str, Any]]:
        """Resolve metrics query."""
        names = args.get("names", [])
        since = args.get("since")

        metrics_service = self.services.get("metrics")
        if not metrics_service:
            return [
                {"name": "cpu_usage", "value": 45.5, "timestamp": datetime.utcnow().isoformat()},
                {"name": "memory_usage", "value": 62.3, "timestamp": datetime.utcnow().isoformat()},
            ]

        metrics = await metrics_service.get_metrics(names=names, since=since)
        return [self._format_metric(m) for m in metrics]

    async def resolve_slas(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> List[Dict[str, Any]]:
        """Resolve SLAs query."""
        sla_monitor = self.services.get("sla_monitor")
        if not sla_monitor:
            return [
                {
                    "id": "sla-1",
                    "name": "Job Completion Time",
                    "target": 99.9,
                    "current": 99.5,
                    "status": "WARNING",
                    "violationsCount": 2,
                },
            ]

        slas = await sla_monitor.get_all_slas()
        return [self._format_sla(s) for s in slas]

    # Formatting helpers
    def _format_job(self, job: Any) -> Dict[str, Any]:
        """Format job object for GraphQL response."""
        if isinstance(job, dict):
            return job
        return {
            "id": getattr(job, "job_id", str(job)),
            "name": getattr(job, "name", "Unknown"),
            "status": getattr(job, "status", "PENDING"),
            "priority": getattr(job, "priority", "NORMAL"),
            "progress": getattr(job, "progress", 0),
            "createdAt": getattr(job, "created_at", datetime.utcnow()).isoformat(),
            "startedAt": getattr(job, "started_at", None),
            "completedAt": getattr(job, "completed_at", None),
            "cpuRequested": getattr(job, "cpu_requested", 1),
            "memoryRequested": getattr(job, "memory_requested", 1024),
            "gpuRequested": getattr(job, "gpu_requested", 0),
        }

    def _format_worker(self, worker: Any) -> Dict[str, Any]:
        """Format worker object for GraphQL response."""
        if isinstance(worker, dict):
            return worker
        return {
            "id": getattr(worker, "worker_id", str(worker)),
            "name": getattr(worker, "name", "Unknown"),
            "status": getattr(worker, "status", "ONLINE"),
            "host": getattr(worker, "host", "localhost"),
            "port": getattr(worker, "port", 5000),
            "cpuTotal": getattr(worker, "cpu_total", 8),
            "cpuUsed": getattr(worker, "cpu_used", 0),
            "memoryTotal": getattr(worker, "memory_total", 16384),
            "memoryUsed": getattr(worker, "memory_used", 0),
        }

    def _format_cluster(self, stats: Any) -> Dict[str, Any]:
        """Format cluster stats for GraphQL response."""
        if isinstance(stats, dict):
            return {
                "id": stats.get("cluster_id", "default"),
                "name": stats.get("name", "NebulaCompute"),
                "version": stats.get("version", "1.0.0"),
                **stats,
            }
        return self._mock_cluster()

    def _format_queue(self, queue: Any) -> Dict[str, Any]:
        """Format queue for GraphQL response."""
        if isinstance(queue, dict):
            return queue
        return {
            "name": getattr(queue, "name", "default"),
            "size": getattr(queue, "size", 0),
            "priority": getattr(queue, "priority", "NORMAL"),
        }

    def _format_metric(self, metric: Any) -> Dict[str, Any]:
        """Format metric for GraphQL response."""
        if isinstance(metric, dict):
            return metric
        return {
            "name": getattr(metric, "name", "unknown"),
            "value": getattr(metric, "value", 0),
            "timestamp": getattr(metric, "timestamp", datetime.utcnow()).isoformat(),
        }

    def _format_sla(self, sla: Any) -> Dict[str, Any]:
        """Format SLA for GraphQL response."""
        if isinstance(sla, dict):
            return sla
        return {
            "id": getattr(sla, "sla_id", str(sla)),
            "name": getattr(sla, "name", "Unknown"),
            "target": getattr(sla, "target", 99.9),
            "current": getattr(sla, "current", 99.9),
            "status": getattr(sla, "status", "OK"),
        }

    # Mock data for testing
    def _mock_job(self, job_id: str) -> Dict[str, Any]:
        """Generate mock job data."""
        return {
            "id": job_id,
            "name": f"Job {job_id}",
            "status": "RUNNING",
            "priority": "NORMAL",
            "progress": 50.0,
            "createdAt": datetime.utcnow().isoformat(),
            "cpuRequested": 2.0,
            "memoryRequested": 4096,
            "gpuRequested": 0,
        }

    def _mock_worker(self, worker_id: str) -> Dict[str, Any]:
        """Generate mock worker data."""
        return {
            "id": worker_id,
            "name": f"Worker {worker_id}",
            "status": "ONLINE",
            "host": "localhost",
            "port": 5000,
            "cpuTotal": 8.0,
            "cpuUsed": 2.0,
            "memoryTotal": 16384,
            "memoryUsed": 4096,
            "gpuTotal": 1.0,
            "gpuUsed": 0.5,
        }

    def _mock_cluster(self) -> Dict[str, Any]:
        """Generate mock cluster data."""
        return {
            "id": "cluster-1",
            "name": "NebulaCompute",
            "version": "1.0.0",
            "activeWorkers": 5,
            "totalJobs": 1000,
            "runningJobs": 15,
            "queuedJobs": 10,
            "completedJobs": 950,
            "failedJobs": 25,
            "cpuTotal": 40.0,
            "cpuUsed": 20.0,
            "cpuUtilization": 50.0,
            "memoryTotal": 81920,
            "memoryUsed": 40960,
            "memoryUtilization": 50.0,
            "uptime": 86400,
            "startedAt": datetime.utcnow().isoformat(),
        }


class MutationResolver:
    """
    Resolver for GraphQL mutations.

    محلل تعديلات GraphQL.
    """

    def __init__(self, services: Dict[str, Any]):
        """
        Initialize mutation resolver.

        Args:
            services: Dictionary of service instances
        """
        self.services = services
        self._resolvers: Dict[str, Callable] = {}
        self._register_resolvers()

    def _register_resolvers(self) -> None:
        """Register all mutation resolvers."""
        self._resolvers = {
            "submitJob": self.resolve_submit_job,
            "cancelJob": self.resolve_cancel_job,
            "retryJob": self.resolve_retry_job,
            "pauseJob": self.resolve_pause_job,
            "resumeJob": self.resolve_resume_job,
            "updateJobPriority": self.resolve_update_priority,
            "drainWorker": self.resolve_drain_worker,
            "activateWorker": self.resolve_activate_worker,
            "scaleCluster": self.resolve_scale_cluster,
        }

    async def resolve(
        self,
        field_name: str,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Any:
        """
        Resolve a mutation field.

        حل حقل تعديل.
        """
        resolver = self._resolvers.get(field_name)
        if not resolver:
            raise ResolverError(
                f"Unknown mutation field: {field_name}",
                code="UNKNOWN_FIELD",
            )

        try:
            return await resolver(args, context, info)
        except ResolverError:
            raise
        except Exception as e:
            logger.error(f"Mutation error for {field_name}: {e}")
            raise ResolverError(str(e), code="INTERNAL_ERROR")

    async def resolve_submit_job(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Dict[str, Any]:
        """Submit a new job."""
        if not context.has_permission("job:submit"):
            raise ResolverError("Permission denied", code="FORBIDDEN")

        input_data = args.get("input", {})

        job_manager = self.services.get("job_manager")
        if not job_manager:
            # Return mock response
            import uuid
            return {
                "id": str(uuid.uuid4()),
                "name": input_data.get("name", "New Job"),
                "status": "PENDING",
                "priority": input_data.get("priority", "NORMAL"),
                "createdAt": datetime.utcnow().isoformat(),
            }

        job = await job_manager.submit_job(
            name=input_data.get("name"),
            job_type=input_data.get("type"),
            priority=input_data.get("priority", "NORMAL"),
            cpu_requested=input_data.get("cpuRequested", 1),
            memory_requested=input_data.get("memoryRequested", 1024),
            gpu_requested=input_data.get("gpuRequested", 0),
            payload=input_data.get("payload"),
            dependencies=input_data.get("dependencies"),
            metadata=input_data.get("metadata"),
        )

        logger.info(f"Job submitted via GraphQL: {job.job_id}")
        return self._format_job(job)

    async def resolve_cancel_job(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Dict[str, Any]:
        """Cancel a job."""
        if not context.has_permission("job:cancel"):
            raise ResolverError("Permission denied", code="FORBIDDEN")

        job_id = args.get("id")

        job_manager = self.services.get("job_manager")
        if not job_manager:
            return {"id": job_id, "status": "CANCELLED"}

        job = await job_manager.cancel_job(job_id)
        logger.info(f"Job cancelled via GraphQL: {job_id}")
        return self._format_job(job)

    async def resolve_retry_job(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Dict[str, Any]:
        """Retry a failed job."""
        job_id = args.get("id")

        job_manager = self.services.get("job_manager")
        if not job_manager:
            return {"id": job_id, "status": "PENDING"}

        job = await job_manager.retry_job(job_id)
        logger.info(f"Job retried via GraphQL: {job_id}")
        return self._format_job(job)

    async def resolve_pause_job(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Dict[str, Any]:
        """Pause a running job."""
        job_id = args.get("id")

        job_manager = self.services.get("job_manager")
        if not job_manager:
            return {"id": job_id, "status": "PAUSED"}

        job = await job_manager.pause_job(job_id)
        return self._format_job(job)

    async def resolve_resume_job(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Dict[str, Any]:
        """Resume a paused job."""
        job_id = args.get("id")

        job_manager = self.services.get("job_manager")
        if not job_manager:
            return {"id": job_id, "status": "RUNNING"}

        job = await job_manager.resume_job(job_id)
        return self._format_job(job)

    async def resolve_update_priority(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Dict[str, Any]:
        """Update job priority."""
        job_id = args.get("id")
        priority = args.get("priority")

        job_manager = self.services.get("job_manager")
        if not job_manager:
            return {"id": job_id, "priority": priority}

        job = await job_manager.update_priority(job_id, priority)
        logger.info(f"Job priority updated via GraphQL: {job_id} -> {priority}")
        return self._format_job(job)

    async def resolve_drain_worker(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Dict[str, Any]:
        """Drain a worker for maintenance."""
        if not context.has_permission("worker:manage"):
            raise ResolverError("Permission denied", code="FORBIDDEN")

        worker_id = args.get("id")

        worker_manager = self.services.get("worker_manager")
        if not worker_manager:
            return {"id": worker_id, "status": "DRAINING"}

        worker = await worker_manager.drain_worker(worker_id)
        logger.info(f"Worker drained via GraphQL: {worker_id}")
        return self._format_worker(worker)

    async def resolve_activate_worker(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Dict[str, Any]:
        """Activate a drained worker."""
        if not context.has_permission("worker:manage"):
            raise ResolverError("Permission denied", code="FORBIDDEN")

        worker_id = args.get("id")

        worker_manager = self.services.get("worker_manager")
        if not worker_manager:
            return {"id": worker_id, "status": "ONLINE"}

        worker = await worker_manager.activate_worker(worker_id)
        logger.info(f"Worker activated via GraphQL: {worker_id}")
        return self._format_worker(worker)

    async def resolve_scale_cluster(
        self,
        args: Dict[str, Any],
        context: ResolverContext,
        info: ResolverInfo,
    ) -> Dict[str, Any]:
        """Scale the cluster."""
        if not context.has_permission("cluster:scale"):
            raise ResolverError("Permission denied", code="FORBIDDEN")

        worker_count = args.get("workerCount")

        cluster_manager = self.services.get("cluster_manager")
        if not cluster_manager:
            return {"id": "cluster-1", "activeWorkers": worker_count}

        stats = await cluster_manager.scale(worker_count)
        logger.info(f"Cluster scaled via GraphQL to {worker_count} workers")
        return self._format_cluster(stats)

    # Formatting helpers
    def _format_job(self, job: Any) -> Dict[str, Any]:
        """Format job object for GraphQL response."""
        if isinstance(job, dict):
            return job
        return {
            "id": getattr(job, "job_id", str(job)),
            "name": getattr(job, "name", "Unknown"),
            "status": getattr(job, "status", "PENDING"),
            "priority": getattr(job, "priority", "NORMAL"),
            "createdAt": getattr(job, "created_at", datetime.utcnow()).isoformat(),
        }

    def _format_worker(self, worker: Any) -> Dict[str, Any]:
        """Format worker object for GraphQL response."""
        if isinstance(worker, dict):
            return worker
        return {
            "id": getattr(worker, "worker_id", str(worker)),
            "name": getattr(worker, "name", "Unknown"),
            "status": getattr(worker, "status", "ONLINE"),
        }

    def _format_cluster(self, stats: Any) -> Dict[str, Any]:
        """Format cluster stats for GraphQL response."""
        if isinstance(stats, dict):
            return {"id": "cluster-1", **stats}
        return {"id": "cluster-1"}
