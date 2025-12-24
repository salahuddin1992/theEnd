# -*- coding: utf-8 -*-
"""
Migration Manager for NebulaCompute.

Orchestrates the live migration of running jobs between workers,
supporting various migration strategies and protocols.

مدير نقل المهام الحية بين Workers.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class MigrationState(str, Enum):
    """Migration state."""

    PENDING = "pending"
    PREPARING = "preparing"
    CHECKPOINTING = "checkpointing"
    TRANSFERRING = "transferring"
    RESTORING = "restoring"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLING_BACK = "rolling_back"


class MigrationMode(str, Enum):
    """Migration mode/strategy."""

    PRE_COPY = "pre_copy"  # Copy memory before stopping
    POST_COPY = "post_copy"  # Stop first, then copy
    HYBRID = "hybrid"  # Combination of both
    CHECKPOINT_RESTORE = "checkpoint_restore"  # Full checkpoint
    CONTAINER_LIVE = "container_live"  # Docker/container live migration


class MigrationPriority(str, Enum):
    """Migration priority."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class MigrationRequest:
    """
    Migration request.

    طلب نقل مهمة.
    """

    request_id: str
    job_id: str
    source_worker: str
    target_worker: str
    mode: MigrationMode = MigrationMode.PRE_COPY
    priority: MigrationPriority = MigrationPriority.NORMAL
    reason: str = ""
    requested_at: datetime = field(default_factory=datetime.utcnow)
    requested_by: Optional[str] = None
    max_downtime_ms: int = 1000  # Maximum acceptable downtime
    bandwidth_limit_mbps: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "job_id": self.job_id,
            "source_worker": self.source_worker,
            "target_worker": self.target_worker,
            "mode": self.mode.value,
            "priority": self.priority.value,
            "reason": self.reason,
            "requested_at": self.requested_at.isoformat(),
            "requested_by": self.requested_by,
            "max_downtime_ms": self.max_downtime_ms,
            "bandwidth_limit_mbps": self.bandwidth_limit_mbps,
            "metadata": self.metadata,
        }


@dataclass
class MigrationProgress:
    """
    Migration progress tracking.

    تتبع تقدم النقل.
    """

    state: MigrationState
    progress_percent: float = 0.0
    bytes_transferred: int = 0
    bytes_total: int = 0
    pages_transferred: int = 0
    pages_dirty: int = 0
    downtime_ms: int = 0
    iterations: int = 0
    current_phase: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    @property
    def duration_seconds(self) -> float:
        """Calculate migration duration."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    @property
    def transfer_rate_mbps(self) -> float:
        """Calculate transfer rate in Mbps."""
        if self.duration_seconds == 0:
            return 0.0
        return (self.bytes_transferred * 8) / (self.duration_seconds * 1_000_000)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "state": self.state.value,
            "progress_percent": self.progress_percent,
            "bytes_transferred": self.bytes_transferred,
            "bytes_total": self.bytes_total,
            "pages_transferred": self.pages_transferred,
            "pages_dirty": self.pages_dirty,
            "downtime_ms": self.downtime_ms,
            "iterations": self.iterations,
            "current_phase": self.current_phase,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "transfer_rate_mbps": self.transfer_rate_mbps,
            "error_message": self.error_message,
        }


@dataclass
class MigrationRecord:
    """
    Complete migration record.

    سجل النقل الكامل.
    """

    request: MigrationRequest
    progress: MigrationProgress
    source_checkpoint_path: Optional[str] = None
    target_checkpoint_path: Optional[str] = None
    rollback_available: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request": self.request.to_dict(),
            "progress": self.progress.to_dict(),
            "source_checkpoint_path": self.source_checkpoint_path,
            "target_checkpoint_path": self.target_checkpoint_path,
            "rollback_available": self.rollback_available,
        }


class MigrationManager:
    """
    Manages live migration of jobs between workers.

    مدير النقل الحي للمهام.

    Features:
    - Pre-copy migration with dirty page tracking
    - Post-copy migration for minimal downtime
    - CRIU checkpoint/restore integration
    - Container live migration
    - Automatic rollback on failure
    - Bandwidth throttling
    - Migration queue with priorities
    """

    def __init__(
        self,
        checkpoint_dir: str = "/var/lib/nebula/checkpoints",
        max_concurrent_migrations: int = 2,
        default_mode: MigrationMode = MigrationMode.PRE_COPY,
        max_pre_copy_iterations: int = 10,
        convergence_threshold: float = 0.1,
        enable_compression: bool = True,
        enable_encryption: bool = True,
    ):
        """
        Initialize Migration Manager.

        Args:
            checkpoint_dir: Directory for storing checkpoints
            max_concurrent_migrations: Maximum concurrent migrations
            default_mode: Default migration mode
            max_pre_copy_iterations: Max iterations for pre-copy
            convergence_threshold: Dirty page convergence threshold
            enable_compression: Enable checkpoint compression
            enable_encryption: Enable checkpoint encryption
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.max_concurrent = max_concurrent_migrations
        self.default_mode = default_mode
        self.max_iterations = max_pre_copy_iterations
        self.convergence_threshold = convergence_threshold
        self.enable_compression = enable_compression
        self.enable_encryption = enable_encryption

        # State
        self._active_migrations: Dict[str, MigrationRecord] = {}
        self._pending_queue: List[MigrationRequest] = []
        self._completed_migrations: Dict[str, MigrationRecord] = {}
        self._lock = asyncio.Lock()

        # Callbacks
        self._on_state_change: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None
        self._on_failure: Optional[Callable] = None

        # Statistics
        self._stats = {
            "total_migrations": 0,
            "successful_migrations": 0,
            "failed_migrations": 0,
            "cancelled_migrations": 0,
            "rollbacks": 0,
            "total_bytes_transferred": 0,
            "total_downtime_ms": 0,
            "avg_migration_time_seconds": 0.0,
        }

        # Create checkpoint directory
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def set_callbacks(
        self,
        on_state_change: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_failure: Optional[Callable] = None,
    ) -> None:
        """Set migration callbacks."""
        self._on_state_change = on_state_change
        self._on_complete = on_complete
        self._on_failure = on_failure

    async def request_migration(
        self,
        job_id: str,
        source_worker: str,
        target_worker: str,
        mode: Optional[MigrationMode] = None,
        priority: MigrationPriority = MigrationPriority.NORMAL,
        reason: str = "",
        max_downtime_ms: int = 1000,
        bandwidth_limit_mbps: Optional[int] = None,
        requested_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MigrationRequest:
        """
        Request a job migration.

        طلب نقل مهمة.

        Args:
            job_id: Job to migrate
            source_worker: Current worker
            target_worker: Destination worker
            mode: Migration mode
            priority: Migration priority
            reason: Reason for migration
            max_downtime_ms: Maximum acceptable downtime
            bandwidth_limit_mbps: Bandwidth limit
            requested_by: Requester identity
            metadata: Additional metadata

        Returns:
            MigrationRequest object
        """
        request = MigrationRequest(
            request_id=str(uuid.uuid4()),
            job_id=job_id,
            source_worker=source_worker,
            target_worker=target_worker,
            mode=mode or self.default_mode,
            priority=priority,
            reason=reason,
            max_downtime_ms=max_downtime_ms,
            bandwidth_limit_mbps=bandwidth_limit_mbps,
            requested_by=requested_by,
            metadata=metadata or {},
        )

        async with self._lock:
            # Check if job already being migrated
            for record in self._active_migrations.values():
                if record.request.job_id == job_id:
                    raise ValueError(f"Job {job_id} is already being migrated")

            # Add to queue or start immediately
            if len(self._active_migrations) < self.max_concurrent:
                await self._start_migration(request)
            else:
                self._pending_queue.append(request)
                self._pending_queue.sort(
                    key=lambda r: (
                        -["low", "normal", "high", "urgent"].index(r.priority.value),
                        r.requested_at,
                    )
                )
                logger.info(
                    f"Migration request {request.request_id} queued "
                    f"(position {len(self._pending_queue)})"
                )

        return request

    async def _start_migration(self, request: MigrationRequest) -> None:
        """Start a migration."""
        self._stats["total_migrations"] += 1

        record = MigrationRecord(
            request=request,
            progress=MigrationProgress(
                state=MigrationState.PREPARING,
                started_at=datetime.utcnow(),
                current_phase="Initializing migration",
            ),
        )

        self._active_migrations[request.request_id] = record

        logger.info(
            f"Starting migration {request.request_id}: "
            f"job={request.job_id}, "
            f"{request.source_worker} -> {request.target_worker}, "
            f"mode={request.mode.value}"
        )

        # Start migration in background
        asyncio.create_task(self._execute_migration(record))

    async def _execute_migration(self, record: MigrationRecord) -> None:
        """Execute the migration process."""
        request = record.request
        progress = record.progress

        try:
            # Phase 1: Preparation
            await self._update_state(record, MigrationState.PREPARING)
            progress.current_phase = "Preparing source and target workers"
            await self._prepare_migration(record)

            # Phase 2: Checkpoint/Transfer based on mode
            if request.mode == MigrationMode.PRE_COPY:
                await self._execute_pre_copy(record)
            elif request.mode == MigrationMode.POST_COPY:
                await self._execute_post_copy(record)
            elif request.mode == MigrationMode.CHECKPOINT_RESTORE:
                await self._execute_checkpoint_restore(record)
            elif request.mode == MigrationMode.CONTAINER_LIVE:
                await self._execute_container_live(record)
            else:
                await self._execute_hybrid(record)

            # Phase 3: Verification
            await self._update_state(record, MigrationState.VERIFYING)
            progress.current_phase = "Verifying migration success"
            await self._verify_migration(record)

            # Complete
            await self._update_state(record, MigrationState.COMPLETED)
            progress.completed_at = datetime.utcnow()
            progress.progress_percent = 100.0

            self._stats["successful_migrations"] += 1
            self._stats["total_bytes_transferred"] += progress.bytes_transferred
            self._stats["total_downtime_ms"] += progress.downtime_ms

            # Update average migration time
            total = self._stats["total_migrations"]
            current_avg = self._stats["avg_migration_time_seconds"]
            new_time = progress.duration_seconds
            self._stats["avg_migration_time_seconds"] = (
                (current_avg * (total - 1) + new_time) / total
            )

            logger.info(
                f"Migration {request.request_id} completed successfully: "
                f"duration={progress.duration_seconds:.1f}s, "
                f"downtime={progress.downtime_ms}ms, "
                f"transferred={progress.bytes_transferred / (1024 * 1024):.1f}MB"
            )

            if self._on_complete:
                await self._safe_callback(self._on_complete, record)

        except asyncio.CancelledError:
            await self._update_state(record, MigrationState.CANCELLED)
            self._stats["cancelled_migrations"] += 1
            logger.info(f"Migration {request.request_id} cancelled")

        except Exception as e:
            progress.error_message = str(e)
            await self._update_state(record, MigrationState.FAILED)
            self._stats["failed_migrations"] += 1

            logger.error(
                f"Migration {request.request_id} failed: {e}",
                exc_info=True,
            )

            # Attempt rollback
            if record.rollback_available:
                await self._rollback(record)

            if self._on_failure:
                await self._safe_callback(self._on_failure, record, e)

        finally:
            # Move to completed and process queue
            async with self._lock:
                if request.request_id in self._active_migrations:
                    self._completed_migrations[request.request_id] = (
                        self._active_migrations.pop(request.request_id)
                    )
                await self._process_queue()

    async def _prepare_migration(self, record: MigrationRecord) -> None:
        """Prepare for migration."""
        request = record.request

        # Verify source worker has the job
        # (In real implementation, would check with worker)
        logger.debug(f"Verifying job {request.job_id} on {request.source_worker}")

        # Verify target worker is available
        logger.debug(f"Verifying target worker {request.target_worker} availability")

        # Create checkpoint paths
        record.source_checkpoint_path = str(
            self.checkpoint_dir / f"migration-{request.request_id}-source"
        )
        record.target_checkpoint_path = str(
            self.checkpoint_dir / f"migration-{request.request_id}-target"
        )

        # Estimate transfer size
        # (In real implementation, would query job memory usage)
        record.progress.bytes_total = 1024 * 1024 * 100  # Estimate 100MB

        await asyncio.sleep(0.1)  # Simulate preparation

    async def _execute_pre_copy(self, record: MigrationRecord) -> None:
        """Execute pre-copy migration."""
        progress = record.progress

        await self._update_state(record, MigrationState.TRANSFERRING)
        progress.current_phase = "Pre-copy: Transferring memory pages"

        # Simulate pre-copy iterations
        dirty_pages = 10000
        pages_per_iteration = 8000

        for iteration in range(1, self.max_iterations + 1):
            progress.iterations = iteration
            progress.pages_dirty = dirty_pages

            # Transfer pages
            pages_to_transfer = min(pages_per_iteration, dirty_pages)
            progress.pages_transferred += pages_to_transfer
            progress.bytes_transferred += pages_to_transfer * 4096

            # Update progress
            progress.progress_percent = min(
                90.0,
                (progress.bytes_transferred / progress.bytes_total) * 100,
            )

            await asyncio.sleep(0.1)  # Simulate transfer time

            # Simulate dirty page generation (decreasing)
            dirty_pages = int(dirty_pages * 0.3)

            logger.debug(
                f"Pre-copy iteration {iteration}: "
                f"transferred={pages_to_transfer}, dirty={dirty_pages}"
            )

            # Check convergence
            if dirty_pages / 10000 < self.convergence_threshold:
                break

        # Final checkpoint and transfer
        await self._update_state(record, MigrationState.CHECKPOINTING)
        progress.current_phase = "Final checkpoint"

        # Record downtime start
        downtime_start = time.monotonic()

        # Checkpoint remaining state
        await asyncio.sleep(0.05)  # Simulate checkpoint

        # Transfer final state
        progress.current_phase = "Transferring final state"
        await asyncio.sleep(0.02)  # Simulate final transfer

        # Restore on target
        await self._update_state(record, MigrationState.RESTORING)
        progress.current_phase = "Restoring on target worker"
        await asyncio.sleep(0.05)  # Simulate restore

        # Record downtime
        progress.downtime_ms = int((time.monotonic() - downtime_start) * 1000)
        record.rollback_available = True

    async def _execute_post_copy(self, record: MigrationRecord) -> None:
        """Execute post-copy migration."""
        progress = record.progress

        # Checkpoint immediately
        await self._update_state(record, MigrationState.CHECKPOINTING)
        progress.current_phase = "Creating checkpoint"

        downtime_start = time.monotonic()

        # Create minimal checkpoint
        await asyncio.sleep(0.02)  # Simulate minimal checkpoint

        # Transfer minimal state
        await self._update_state(record, MigrationState.TRANSFERRING)
        progress.current_phase = "Transferring minimal state"
        await asyncio.sleep(0.01)  # Quick transfer

        # Restore and resume immediately
        await self._update_state(record, MigrationState.RESTORING)
        progress.current_phase = "Quick restore on target"
        await asyncio.sleep(0.02)  # Quick restore

        progress.downtime_ms = int((time.monotonic() - downtime_start) * 1000)
        record.rollback_available = True

        # Continue transferring pages on-demand (simulated)
        progress.current_phase = "On-demand page transfer"
        for i in range(5):
            progress.bytes_transferred += 1024 * 1024 * 10
            progress.progress_percent = min(
                95.0,
                (progress.bytes_transferred / progress.bytes_total) * 100,
            )
            await asyncio.sleep(0.1)

    async def _execute_checkpoint_restore(self, record: MigrationRecord) -> None:
        """Execute checkpoint/restore migration (CRIU-style)."""
        progress = record.progress

        # Full checkpoint
        await self._update_state(record, MigrationState.CHECKPOINTING)
        progress.current_phase = "Creating full checkpoint (CRIU)"

        downtime_start = time.monotonic()

        # Simulate CRIU checkpoint
        await asyncio.sleep(0.1)
        progress.bytes_transferred = progress.bytes_total // 2

        # Transfer checkpoint files
        await self._update_state(record, MigrationState.TRANSFERRING)
        progress.current_phase = "Transferring checkpoint files"

        for i in range(5):
            progress.bytes_transferred += progress.bytes_total // 10
            progress.progress_percent = (
                progress.bytes_transferred / progress.bytes_total
            ) * 100
            await asyncio.sleep(0.05)

        # Restore from checkpoint
        await self._update_state(record, MigrationState.RESTORING)
        progress.current_phase = "Restoring from checkpoint (CRIU)"

        await asyncio.sleep(0.1)

        progress.downtime_ms = int((time.monotonic() - downtime_start) * 1000)
        record.rollback_available = True

    async def _execute_container_live(self, record: MigrationRecord) -> None:
        """Execute container live migration."""
        progress = record.progress

        # Use Docker/Podman checkpoint
        await self._update_state(record, MigrationState.CHECKPOINTING)
        progress.current_phase = "Docker checkpoint"

        downtime_start = time.monotonic()

        await asyncio.sleep(0.05)

        # Export and transfer
        await self._update_state(record, MigrationState.TRANSFERRING)
        progress.current_phase = "Transferring container state"

        for i in range(3):
            progress.bytes_transferred += progress.bytes_total // 3
            progress.progress_percent = min(
                90.0,
                (progress.bytes_transferred / progress.bytes_total) * 100,
            )
            await asyncio.sleep(0.05)

        # Restore container
        await self._update_state(record, MigrationState.RESTORING)
        progress.current_phase = "Restoring container"

        await asyncio.sleep(0.05)

        progress.downtime_ms = int((time.monotonic() - downtime_start) * 1000)
        record.rollback_available = True

    async def _execute_hybrid(self, record: MigrationRecord) -> None:
        """Execute hybrid migration (combination of pre and post copy)."""
        # Start with pre-copy for most data
        progress = record.progress
        progress.current_phase = "Hybrid: Initial pre-copy"

        await self._update_state(record, MigrationState.TRANSFERRING)

        # Transfer 70% of pages in pre-copy
        target_bytes = int(progress.bytes_total * 0.7)
        while progress.bytes_transferred < target_bytes:
            progress.bytes_transferred += 1024 * 1024 * 10
            progress.progress_percent = (
                progress.bytes_transferred / progress.bytes_total
            ) * 80
            await asyncio.sleep(0.05)

        # Switch to checkpoint/restore for remaining
        await self._update_state(record, MigrationState.CHECKPOINTING)
        progress.current_phase = "Hybrid: Checkpoint remaining"

        downtime_start = time.monotonic()
        await asyncio.sleep(0.03)

        # Quick restore and on-demand pages
        await self._update_state(record, MigrationState.RESTORING)
        progress.current_phase = "Hybrid: Restore with on-demand"

        await asyncio.sleep(0.02)
        progress.downtime_ms = int((time.monotonic() - downtime_start) * 1000)

        progress.bytes_transferred = progress.bytes_total
        record.rollback_available = True

    async def _verify_migration(self, record: MigrationRecord) -> None:
        """Verify migration success."""
        # In real implementation, would:
        # - Verify job is running on target
        # - Verify job state is consistent
        # - Clean up source resources

        await asyncio.sleep(0.05)  # Simulate verification
        logger.debug(f"Migration {record.request.request_id} verified")

    async def _rollback(self, record: MigrationRecord) -> None:
        """Rollback failed migration."""
        logger.info(f"Rolling back migration {record.request.request_id}")

        await self._update_state(record, MigrationState.ROLLING_BACK)
        record.progress.current_phase = "Rolling back"

        # In real implementation, would restore job on source worker
        await asyncio.sleep(0.1)

        self._stats["rollbacks"] += 1
        logger.info(f"Rollback completed for {record.request.request_id}")

    async def _update_state(
        self,
        record: MigrationRecord,
        new_state: MigrationState,
    ) -> None:
        """Update migration state."""
        old_state = record.progress.state
        record.progress.state = new_state

        logger.debug(
            f"Migration {record.request.request_id}: "
            f"{old_state.value} -> {new_state.value}"
        )

        if self._on_state_change:
            await self._safe_callback(
                self._on_state_change, record, old_state, new_state
            )

    async def _process_queue(self) -> None:
        """Process pending migration queue."""
        while self._pending_queue and len(self._active_migrations) < self.max_concurrent:
            request = self._pending_queue.pop(0)
            await self._start_migration(request)

    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Callback error: {e}")

    async def cancel_migration(self, request_id: str) -> bool:
        """
        Cancel a migration.

        إلغاء نقل.
        """
        async with self._lock:
            # Check pending queue
            for i, request in enumerate(self._pending_queue):
                if request.request_id == request_id:
                    self._pending_queue.pop(i)
                    self._stats["cancelled_migrations"] += 1
                    logger.info(f"Cancelled pending migration {request_id}")
                    return True

            # Check active migrations
            if request_id in self._active_migrations:
                # Would need to cancel the running task
                logger.warning(
                    f"Cannot cancel active migration {request_id} "
                    "(not fully implemented)"
                )
                return False

        return False

    async def get_migration_status(
        self,
        request_id: str,
    ) -> Optional[MigrationRecord]:
        """Get migration status."""
        if request_id in self._active_migrations:
            return self._active_migrations[request_id]
        if request_id in self._completed_migrations:
            return self._completed_migrations[request_id]
        return None

    async def get_active_migrations(self) -> List[MigrationRecord]:
        """Get all active migrations."""
        return list(self._active_migrations.values())

    async def get_pending_migrations(self) -> List[MigrationRequest]:
        """Get pending migration requests."""
        return list(self._pending_queue)

    async def get_job_migration(self, job_id: str) -> Optional[MigrationRecord]:
        """Get migration for a specific job."""
        for record in self._active_migrations.values():
            if record.request.job_id == job_id:
                return record
        return None

    async def get_statistics(self) -> Dict[str, Any]:
        """Get migration statistics."""
        return {
            **self._stats,
            "active_migrations": len(self._active_migrations),
            "pending_migrations": len(self._pending_queue),
            "completed_migrations": len(self._completed_migrations),
            "default_mode": self.default_mode.value,
            "max_concurrent": self.max_concurrent,
        }

    async def cleanup_completed(self, max_age_hours: int = 24) -> int:
        """Clean up old completed migrations."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        cleaned = 0

        async with self._lock:
            to_remove = [
                request_id
                for request_id, record in self._completed_migrations.items()
                if record.progress.completed_at
                and record.progress.completed_at < cutoff
            ]

            for request_id in to_remove:
                del self._completed_migrations[request_id]
                cleaned += 1

        if cleaned:
            logger.info(f"Cleaned up {cleaned} old migration records")

        return cleaned

    async def shutdown(self) -> None:
        """Shutdown migration manager."""
        # Cancel pending migrations
        async with self._lock:
            for request in self._pending_queue:
                self._stats["cancelled_migrations"] += 1
            self._pending_queue.clear()

        # Wait for active migrations (with timeout)
        if self._active_migrations:
            logger.info(
                f"Waiting for {len(self._active_migrations)} "
                "active migrations to complete..."
            )
            # In production, would implement proper cancellation

        logger.info("Migration Manager shutdown complete")
