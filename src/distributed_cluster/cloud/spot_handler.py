# -*- coding: utf-8 -*-
"""
Spot Instance Handler for NebulaCompute.

Handles spot/preemptible instance termination notifications
and orchestrates graceful job evacuation.

معالج إنهاء Spot Instances.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class SpotProvider(str, Enum):
    """Cloud provider for spot instances."""

    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    GENERIC = "generic"


class SpotInstanceState(str, Enum):
    """Spot instance state."""

    RUNNING = "running"
    MARKED_FOR_TERMINATION = "marked_for_termination"
    EVACUATING = "evacuating"
    TERMINATED = "terminated"


class TerminationType(str, Enum):
    """Termination type."""

    SPOT_INTERRUPTION = "spot_interruption"
    PREEMPTION = "preemption"
    SCHEDULED_MAINTENANCE = "scheduled_maintenance"
    CAPACITY_REBALANCING = "capacity_rebalancing"


@dataclass
class SpotNotification:
    """
    Spot termination notification.

    إشعار إنهاء Spot Instance.
    """

    notification_id: str
    instance_id: str
    worker_id: str
    provider: SpotProvider
    termination_type: TerminationType
    termination_time: datetime
    received_at: datetime = field(default_factory=datetime.utcnow)
    warning_seconds: int = 120  # Default 2 minutes
    action_taken: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def time_remaining_seconds(self) -> float:
        """Calculate remaining time before termination."""
        remaining = (self.termination_time - datetime.now(timezone.utc)).total_seconds()
        return max(0, remaining)

    @property
    def is_urgent(self) -> bool:
        """Check if termination is urgent (< 60 seconds)."""
        return self.time_remaining_seconds < 60

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "notification_id": self.notification_id,
            "instance_id": self.instance_id,
            "worker_id": self.worker_id,
            "provider": self.provider.value,
            "termination_type": self.termination_type.value,
            "termination_time": self.termination_time.isoformat(),
            "received_at": self.received_at.isoformat(),
            "warning_seconds": self.warning_seconds,
            "time_remaining_seconds": self.time_remaining_seconds,
            "is_urgent": self.is_urgent,
            "action_taken": self.action_taken,
            "metadata": self.metadata,
        }


@dataclass
class EvacuationResult:
    """
    Evacuation result.

    نتيجة الإخلاء.
    """

    worker_id: str
    success: bool
    jobs_evacuated: int
    jobs_checkpointed: int
    jobs_lost: int
    duration_seconds: float
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "worker_id": self.worker_id,
            "success": self.success,
            "jobs_evacuated": self.jobs_evacuated,
            "jobs_checkpointed": self.jobs_checkpointed,
            "jobs_lost": self.jobs_lost,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
        }


class SpotInstanceHandler:
    """
    Handles spot instance termination and job evacuation.

    معالج إنهاء Spot Instances وإخلاء المهام.

    Features:
    - Multi-cloud support (AWS, GCP, Azure)
    - Automatic termination detection
    - Graceful job evacuation
    - Checkpoint-based recovery
    - Priority-based evacuation
    - Metrics and alerting
    """

    # Cloud metadata endpoints
    METADATA_ENDPOINTS = {
        SpotProvider.AWS: "http://169.254.169.254/latest/meta-data/spot/termination-time",
        SpotProvider.GCP: "http://metadata.google.internal/computeMetadata/v1/instance/preempted",
        SpotProvider.AZURE: "http://169.254.169.254/metadata/scheduledevents?api-version=2020-07-01",
    }

    def __init__(
        self,
        provider: SpotProvider = SpotProvider.AWS,
        poll_interval_seconds: float = 5.0,
        evacuation_callback: Optional[Callable] = None,
        checkpoint_callback: Optional[Callable] = None,
        notification_callback: Optional[Callable] = None,
        min_evacuation_time_seconds: int = 30,
    ):
        """
        Initialize Spot Instance Handler.

        Args:
            provider: Cloud provider
            poll_interval_seconds: Metadata polling interval
            evacuation_callback: Called when evacuation needed
            checkpoint_callback: Called to checkpoint jobs
            notification_callback: Called on termination notification
            min_evacuation_time_seconds: Minimum time required for evacuation
        """
        self.provider = provider
        self.poll_interval = poll_interval_seconds
        self.evacuation_callback = evacuation_callback
        self.checkpoint_callback = checkpoint_callback
        self.notification_callback = notification_callback
        self.min_evacuation_time = min_evacuation_time_seconds

        # State
        self._workers: Dict[str, Dict[str, Any]] = {}  # worker_id -> state
        self._notifications: Dict[str, SpotNotification] = {}
        self._running = False
        self._monitor_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "notifications_received": 0,
            "successful_evacuations": 0,
            "failed_evacuations": 0,
            "jobs_saved": 0,
            "jobs_lost": 0,
            "total_evacuation_time_seconds": 0.0,
        }

    async def register_worker(
        self,
        worker_id: str,
        instance_id: str,
        provider: Optional[SpotProvider] = None,
        is_spot: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a worker for spot monitoring.

        تسجيل Worker للمراقبة.

        Args:
            worker_id: Worker identifier
            instance_id: Cloud instance ID
            provider: Cloud provider (uses default if None)
            is_spot: Whether instance is spot/preemptible
            metadata: Additional metadata
        """
        async with self._lock:
            self._workers[worker_id] = {
                "worker_id": worker_id,
                "instance_id": instance_id,
                "provider": provider or self.provider,
                "is_spot": is_spot,
                "state": SpotInstanceState.RUNNING,
                "registered_at": datetime.now(timezone.utc),
                "metadata": metadata or {},
            }

            if is_spot and self._running:
                task = asyncio.create_task(self._monitor_worker(worker_id))
                self._monitor_tasks[worker_id] = task

        logger.info(f"Registered worker {worker_id} (spot={is_spot})")

    async def unregister_worker(self, worker_id: str) -> None:
        """Unregister a worker from spot monitoring."""
        async with self._lock:
            self._workers.pop(worker_id, None)

            if worker_id in self._monitor_tasks:
                self._monitor_tasks[worker_id].cancel()
                del self._monitor_tasks[worker_id]

        logger.info(f"Unregistered worker {worker_id}")

    async def start(self) -> None:
        """Start spot instance monitoring."""
        if self._running:
            return

        self._running = True

        # Start monitoring for all registered spot workers
        async with self._lock:
            for worker_id, worker in self._workers.items():
                if worker["is_spot"]:
                    task = asyncio.create_task(self._monitor_worker(worker_id))
                    self._monitor_tasks[worker_id] = task

        logger.info("Spot Instance Handler started")

    async def stop(self) -> None:
        """Stop spot instance monitoring."""
        self._running = False

        # Cancel all monitor tasks
        for task in self._monitor_tasks.values():
            task.cancel()

        self._monitor_tasks.clear()
        logger.info("Spot Instance Handler stopped")

    async def _monitor_worker(self, worker_id: str) -> None:
        """Monitor a single worker for termination notices."""
        worker = self._workers.get(worker_id)
        if not worker:
            return

        provider = worker["provider"]
        instance_id = worker["instance_id"]

        logger.debug(f"Starting spot monitor for {worker_id}")

        while self._running and worker_id in self._workers:
            try:
                notification = await self._check_termination(
                    worker_id, instance_id, provider
                )

                if notification:
                    await self._handle_termination(notification)

                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring {worker_id}: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _check_termination(
        self,
        worker_id: str,
        instance_id: str,
        provider: SpotProvider,
    ) -> Optional[SpotNotification]:
        """Check for termination notification from cloud metadata."""
        try:
            if provider == SpotProvider.AWS:
                return await self._check_aws_termination(worker_id, instance_id)
            elif provider == SpotProvider.GCP:
                return await self._check_gcp_termination(worker_id, instance_id)
            elif provider == SpotProvider.AZURE:
                return await self._check_azure_termination(worker_id, instance_id)
            else:
                return None

        except httpx.RequestError:
            # Metadata service not available (not on cloud)
            return None
        except Exception as e:
            logger.warning(f"Error checking termination for {worker_id}: {e}")
            return None

    async def _check_aws_termination(
        self,
        worker_id: str,
        instance_id: str,
    ) -> Optional[SpotNotification]:
        """Check AWS spot termination notice."""
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                # Check spot termination time
                response = await client.get(
                    self.METADATA_ENDPOINTS[SpotProvider.AWS]
                )

                if response.status_code == 200:
                    # Termination notice received
                    termination_time_str = response.text.strip()
                    termination_time = datetime.fromisoformat(
                        termination_time_str.replace("Z", "+00:00")
                    )

                    return SpotNotification(
                        notification_id=f"aws-{instance_id}-{int(time.time())}",
                        instance_id=instance_id,
                        worker_id=worker_id,
                        provider=SpotProvider.AWS,
                        termination_type=TerminationType.SPOT_INTERRUPTION,
                        termination_time=termination_time,
                        warning_seconds=120,  # AWS gives 2 minutes
                    )

                # Also check rebalance recommendation
                rebalance_response = await client.get(
                    "http://169.254.169.254/latest/meta-data/events/recommendations/rebalance"
                )
                if rebalance_response.status_code == 200:
                    # Rebalance recommended (not immediate termination)
                    return SpotNotification(
                        notification_id=f"aws-rebalance-{instance_id}-{int(time.time())}",
                        instance_id=instance_id,
                        worker_id=worker_id,
                        provider=SpotProvider.AWS,
                        termination_type=TerminationType.CAPACITY_REBALANCING,
                        termination_time=datetime.now(timezone.utc) + timedelta(minutes=10),
                        warning_seconds=600,
                        metadata={"type": "rebalance_recommendation"},
                    )

            except httpx.HTTPStatusError:
                pass

        return None

    async def _check_gcp_termination(
        self,
        worker_id: str,
        instance_id: str,
    ) -> Optional[SpotNotification]:
        """Check GCP preemption notice."""
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                response = await client.get(
                    self.METADATA_ENDPOINTS[SpotProvider.GCP],
                    headers={"Metadata-Flavor": "Google"},
                )

                if response.status_code == 200 and response.text.strip().lower() == "true":
                    # Preemption notice received
                    # GCP gives 30 seconds warning
                    return SpotNotification(
                        notification_id=f"gcp-{instance_id}-{int(time.time())}",
                        instance_id=instance_id,
                        worker_id=worker_id,
                        provider=SpotProvider.GCP,
                        termination_type=TerminationType.PREEMPTION,
                        termination_time=datetime.now(timezone.utc) + timedelta(seconds=30),
                        warning_seconds=30,
                    )

            except httpx.HTTPStatusError:
                pass

        return None

    async def _check_azure_termination(
        self,
        worker_id: str,
        instance_id: str,
    ) -> Optional[SpotNotification]:
        """Check Azure scheduled events."""
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                response = await client.get(
                    self.METADATA_ENDPOINTS[SpotProvider.AZURE],
                    headers={"Metadata": "true"},
                )

                if response.status_code == 200:
                    data = response.json()
                    events = data.get("Events", [])

                    for event in events:
                        event_type = event.get("EventType", "")
                        if event_type in ["Preempt", "Terminate"]:
                            not_before = event.get("NotBefore", "")
                            termination_time = datetime.fromisoformat(
                                not_before.replace("Z", "+00:00")
                            )

                            return SpotNotification(
                                notification_id=f"azure-{instance_id}-{event.get('EventId', '')}",
                                instance_id=instance_id,
                                worker_id=worker_id,
                                provider=SpotProvider.AZURE,
                                termination_type=TerminationType.SPOT_INTERRUPTION,
                                termination_time=termination_time,
                                warning_seconds=30,
                                metadata={"event": event},
                            )

            except httpx.HTTPStatusError:
                pass

        return None

    async def _handle_termination(self, notification: SpotNotification) -> None:
        """Handle termination notification."""
        worker_id = notification.worker_id

        # Check if already handling this notification
        if notification.notification_id in self._notifications:
            return

        self._notifications[notification.notification_id] = notification
        self._stats["notifications_received"] += 1

        logger.warning(
            f"Spot termination notice for {worker_id}: "
            f"type={notification.termination_type.value}, "
            f"time_remaining={notification.time_remaining_seconds:.0f}s"
        )

        # Update worker state
        if worker_id in self._workers:
            self._workers[worker_id]["state"] = SpotInstanceState.MARKED_FOR_TERMINATION

        # Call notification callback
        if self.notification_callback:
            await self._safe_callback(self.notification_callback, notification)

        # Start evacuation
        result = await self._evacuate_worker(notification)

        # Update state
        if worker_id in self._workers:
            self._workers[worker_id]["state"] = SpotInstanceState.EVACUATING

        # Log result
        if result.success:
            self._stats["successful_evacuations"] += 1
            self._stats["jobs_saved"] += result.jobs_evacuated + result.jobs_checkpointed
            logger.info(
                f"Evacuation complete for {worker_id}: "
                f"evacuated={result.jobs_evacuated}, "
                f"checkpointed={result.jobs_checkpointed}"
            )
        else:
            self._stats["failed_evacuations"] += 1
            self._stats["jobs_lost"] += result.jobs_lost
            logger.error(
                f"Evacuation failed for {worker_id}: "
                f"lost={result.jobs_lost}, errors={result.errors}"
            )

        self._stats["total_evacuation_time_seconds"] += result.duration_seconds

    async def _evacuate_worker(
        self,
        notification: SpotNotification,
    ) -> EvacuationResult:
        """Evacuate all jobs from a worker."""
        worker_id = notification.worker_id
        start_time = time.monotonic()

        jobs_evacuated = 0
        jobs_checkpointed = 0
        jobs_lost = 0
        errors: List[str] = []

        try:
            # Get jobs on this worker (simulated)
            jobs = await self._get_worker_jobs(worker_id)

            time_remaining = notification.time_remaining_seconds

            for job_id in jobs:
                try:
                    if time_remaining > self.min_evacuation_time:
                        # Enough time to migrate
                        if self.evacuation_callback:
                            await self._safe_callback(
                                self.evacuation_callback,
                                worker_id,
                                job_id,
                                notification,
                            )
                        jobs_evacuated += 1
                    else:
                        # Only checkpoint
                        if self.checkpoint_callback:
                            await self._safe_callback(
                                self.checkpoint_callback,
                                worker_id,
                                job_id,
                            )
                        jobs_checkpointed += 1

                    time_remaining = notification.time_remaining_seconds

                except Exception as e:
                    jobs_lost += 1
                    errors.append(f"Job {job_id}: {str(e)}")

        except Exception as e:
            errors.append(f"Evacuation error: {str(e)}")

        duration = time.monotonic() - start_time

        return EvacuationResult(
            worker_id=worker_id,
            success=jobs_lost == 0,
            jobs_evacuated=jobs_evacuated,
            jobs_checkpointed=jobs_checkpointed,
            jobs_lost=jobs_lost,
            duration_seconds=duration,
            errors=errors,
        )

    async def _get_worker_jobs(self, worker_id: str) -> List[str]:
        """Get jobs running on a worker (simulated)."""
        # In real implementation, would query cluster state
        return [f"job-{i}" for i in range(3)]

    async def simulate_termination(
        self,
        worker_id: str,
        warning_seconds: int = 120,
    ) -> SpotNotification:
        """
        Simulate a spot termination for testing.

        محاكاة إنهاء Spot للاختبار.
        """
        worker = self._workers.get(worker_id)
        if not worker:
            raise ValueError(f"Worker {worker_id} not found")

        notification = SpotNotification(
            notification_id=f"simulated-{worker_id}-{int(time.time())}",
            instance_id=worker["instance_id"],
            worker_id=worker_id,
            provider=worker["provider"],
            termination_type=TerminationType.SPOT_INTERRUPTION,
            termination_time=datetime.now(timezone.utc) + timedelta(seconds=warning_seconds),
            warning_seconds=warning_seconds,
            metadata={"simulated": True},
        )

        await self._handle_termination(notification)
        return notification

    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Callback error: {e}")

    async def get_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get worker spot status."""
        worker = self._workers.get(worker_id)
        if not worker:
            return None

        return {
            **worker,
            "notifications": [
                n.to_dict()
                for n in self._notifications.values()
                if n.worker_id == worker_id
            ],
        }

    async def get_all_notifications(self) -> List[SpotNotification]:
        """Get all termination notifications."""
        return list(self._notifications.values())

    async def get_statistics(self) -> Dict[str, Any]:
        """Get spot handler statistics."""
        return {
            **self._stats,
            "registered_workers": len(self._workers),
            "spot_workers": len([w for w in self._workers.values() if w["is_spot"]]),
            "active_monitors": len(self._monitor_tasks),
            "pending_notifications": len(
                [n for n in self._notifications.values() if n.time_remaining_seconds > 0]
            ),
            "provider": self.provider.value,
        }

    async def shutdown(self) -> None:
        """Shutdown spot instance handler."""
        await self.stop()
        logger.info("Spot Instance Handler shutdown complete")
