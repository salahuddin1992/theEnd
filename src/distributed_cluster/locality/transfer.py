"""
Data Transfer Manager - مدير نقل البيانات
==========================================

Manages data transfers between workers for locality optimization.
يدير نقل البيانات بين workers لتحسين المحلية.

Features:
- Prioritized transfer queue
- Concurrent transfers with throttling
- Progress tracking
- Retry logic with backoff
- Checksum verification
- Compression support
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

from .scorer import NetworkTopology
from .tracker import (
    DataLocation,
    DataLocationTracker,
    ReplicaState,
)

logger = logging.getLogger(__name__)


class TransferState(str, Enum):
    """State of a data transfer."""

    PENDING = "pending"  # Waiting to start
    QUEUED = "queued"  # In queue
    CONNECTING = "connecting"  # Establishing connection
    TRANSFERRING = "transferring"  # Data being transferred
    VERIFYING = "verifying"  # Verifying checksum
    COMPLETED = "completed"  # Transfer successful
    FAILED = "failed"  # Transfer failed
    CANCELLED = "cancelled"  # Transfer cancelled
    RETRYING = "retrying"  # Waiting for retry


class TransferPriority(int, Enum):
    """Priority levels for transfers."""

    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class TransferRequest:
    """
    A request to transfer data between workers.
    طلب لنقل البيانات بين workers.
    """

    transfer_id: str
    block_id: str
    source_worker: str
    target_worker: str
    source_path: str
    target_path: str

    # Priority and scheduling
    priority: TransferPriority = TransferPriority.NORMAL
    job_id: Optional[str] = None  # Associated job

    # Size info
    size_bytes: int = 0
    checksum: Optional[str] = None

    # Options
    verify_checksum: bool = True
    compress: bool = False
    delete_source: bool = False  # Move instead of copy

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    deadline: Optional[datetime] = None  # Must complete by

    # Metadata
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "transfer_id": self.transfer_id,
            "block_id": self.block_id,
            "source_worker": self.source_worker,
            "target_worker": self.target_worker,
            "source_path": self.source_path,
            "target_path": self.target_path,
            "priority": self.priority.value,
            "job_id": self.job_id,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "created_at": self.created_at.isoformat(),
            "deadline": self.deadline.isoformat() if self.deadline else None,
        }


@dataclass
class TransferProgress:
    """
    Progress of a data transfer.
    تقدم نقل البيانات.
    """

    transfer_id: str
    state: TransferState = TransferState.PENDING
    bytes_transferred: int = 0
    total_bytes: int = 0

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_update: Optional[datetime] = None

    # Speed
    current_speed_mbps: float = 0.0
    average_speed_mbps: float = 0.0

    # Attempts
    attempt: int = 0
    max_attempts: int = 3

    # Error info
    error_message: Optional[str] = None

    @property
    def progress_ratio(self) -> float:
        """Get progress as a ratio (0.0 to 1.0)."""
        if self.total_bytes == 0:
            return 0.0
        return self.bytes_transferred / self.total_bytes

    @property
    def progress_percent(self) -> float:
        """Get progress as a percentage."""
        return self.progress_ratio * 100

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    @property
    def eta_seconds(self) -> Optional[float]:
        """Estimate time remaining in seconds."""
        if self.average_speed_mbps <= 0:
            return None
        remaining_bytes = self.total_bytes - self.bytes_transferred
        remaining_mb = remaining_bytes / (1024 * 1024)
        return remaining_mb / (self.average_speed_mbps / 8)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "transfer_id": self.transfer_id,
            "state": self.state.value,
            "bytes_transferred": self.bytes_transferred,
            "total_bytes": self.total_bytes,
            "progress_percent": self.progress_percent,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "current_speed_mbps": self.current_speed_mbps,
            "average_speed_mbps": self.average_speed_mbps,
            "elapsed_seconds": self.elapsed_seconds,
            "eta_seconds": self.eta_seconds,
            "attempt": self.attempt,
            "error_message": self.error_message,
        }


@dataclass
class TransferResult:
    """
    Result of a completed transfer.
    نتيجة نقل مكتمل.
    """

    transfer_id: str
    success: bool
    block_id: str
    source_worker: str
    target_worker: str

    # Stats
    bytes_transferred: int = 0
    transfer_time_seconds: float = 0.0
    average_speed_mbps: float = 0.0

    # Verification
    checksum_verified: bool = False
    checksum: Optional[str] = None

    # Error info
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "transfer_id": self.transfer_id,
            "success": self.success,
            "block_id": self.block_id,
            "source_worker": self.source_worker,
            "target_worker": self.target_worker,
            "bytes_transferred": self.bytes_transferred,
            "transfer_time_seconds": self.transfer_time_seconds,
            "average_speed_mbps": self.average_speed_mbps,
            "checksum_verified": self.checksum_verified,
            "error_message": self.error_message,
        }


@dataclass
class TransferConfig:
    """
    Configuration for the transfer manager.
    إعدادات مدير النقل.
    """

    # Concurrency
    max_concurrent_transfers: int = 5
    max_transfers_per_worker: int = 2

    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    retry_backoff_multiplier: float = 2.0
    max_retry_delay_seconds: float = 60.0

    # Timeouts
    connection_timeout_seconds: float = 30.0
    transfer_timeout_seconds: float = 3600.0  # 1 hour

    # Verification
    verify_checksums: bool = True
    checksum_algorithm: str = "sha256"

    # Compression
    enable_compression: bool = False
    compression_min_size_bytes: int = 1024 * 1024  # 1MB

    # Throttling
    max_bandwidth_mbps: Optional[float] = None
    burst_bandwidth_mbps: Optional[float] = None

    # Queue settings
    max_queue_size: int = 1000
    queue_timeout_seconds: float = 300.0  # 5 minutes


class TransferHandler:
    """
    Abstract handler for performing actual data transfers.
    معالج مجرد لإجراء عمليات نقل البيانات الفعلية.

    Override this to implement actual transfer logic.
    """

    async def transfer(
        self,
        request: TransferRequest,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> TransferResult:
        """
        Perform a data transfer.

        Args:
            request: The transfer request
            progress_callback: Called with bytes transferred

        Returns:
            TransferResult
        """
        raise NotImplementedError


class SimulatedTransferHandler(TransferHandler):
    """
    Simulated transfer handler for testing.
    معالج نقل محاكى للاختبار.
    """

    def __init__(
        self,
        topology: Optional[NetworkTopology] = None,
        failure_rate: float = 0.0,
    ):
        self.topology = topology or NetworkTopology()
        self.failure_rate = failure_rate

    async def transfer(
        self,
        request: TransferRequest,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> TransferResult:
        """Simulate a data transfer."""
        import random

        # Check for simulated failure
        if random.random() < self.failure_rate:
            return TransferResult(
                transfer_id=request.transfer_id,
                success=False,
                block_id=request.block_id,
                source_worker=request.source_worker,
                target_worker=request.target_worker,
                error_message="Simulated transfer failure",
            )

        # Calculate transfer time based on topology
        level = self.topology.get_locality_level(
            request.source_worker,
            request.target_worker,
        )
        bandwidth = self.topology.get_bandwidth(level)
        latency = self.topology.get_latency(level) / 1000  # Convert to seconds

        size_mb = request.size_bytes / (1024 * 1024)
        transfer_time = latency + size_mb / (bandwidth / 8)

        # Simulate progress
        chunk_size = request.size_bytes // 10
        for i in range(10):
            await asyncio.sleep(transfer_time / 10)
            if progress_callback:
                progress_callback(chunk_size * (i + 1))

        # Generate checksum
        checksum = hashlib.sha256(f"{request.block_id}:{request.target_worker}".encode()).hexdigest()[:16]

        return TransferResult(
            transfer_id=request.transfer_id,
            success=True,
            block_id=request.block_id,
            source_worker=request.source_worker,
            target_worker=request.target_worker,
            bytes_transferred=request.size_bytes,
            transfer_time_seconds=transfer_time,
            average_speed_mbps=bandwidth,
            checksum_verified=True,
            checksum=checksum,
        )


class DataTransferManager:
    """
    Manages data transfers between workers.
    يدير نقل البيانات بين workers.
    """

    def __init__(
        self,
        tracker: DataLocationTracker,
        handler: Optional[TransferHandler] = None,
        config: Optional[TransferConfig] = None,
        topology: Optional[NetworkTopology] = None,
    ):
        self.tracker = tracker
        self.handler = handler or SimulatedTransferHandler(topology)
        self.config = config or TransferConfig()
        self.topology = topology or NetworkTopology()

        # Transfer queues
        self._pending_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=self.config.max_queue_size)
        self._active_transfers: Dict[str, TransferProgress] = {}
        self._completed_transfers: Dict[str, TransferResult] = {}

        # Worker tracking
        self._worker_transfers: Dict[str, Set[str]] = {}  # worker_id -> transfer_ids

        # Semaphores for concurrency control
        self._global_semaphore = asyncio.Semaphore(self.config.max_concurrent_transfers)
        self._worker_semaphores: Dict[str, asyncio.Semaphore] = {}

        # Background tasks
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

        # Callbacks
        self._on_transfer_complete: List[Callable] = []
        self._on_transfer_failed: List[Callable] = []

        # Statistics
        self._stats = {
            "total_transfers": 0,
            "successful_transfers": 0,
            "failed_transfers": 0,
            "total_bytes_transferred": 0,
            "total_transfer_time_seconds": 0.0,
        }

    async def start(self) -> None:
        """Start the transfer manager."""
        if self._running:
            return

        self._running = True
        self._processor_task = asyncio.create_task(self._process_queue())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("DataTransferManager started")

    async def stop(self) -> None:
        """Stop the transfer manager."""
        self._running = False

        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("DataTransferManager stopped")

    # ==================== Transfer Operations ====================

    async def request_transfer(
        self,
        block_id: str,
        target_worker: str,
        priority: TransferPriority = TransferPriority.NORMAL,
        job_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Request a transfer of a data block to a target worker.
        طلب نقل كتلة بيانات إلى worker مستهدف.

        Returns the transfer ID or None if transfer not needed.
        """
        # Get block info
        block = await self.tracker.get_block(block_id)
        if not block:
            logger.warning(f"Block {block_id} not found")
            return None

        # Check if already on target
        locations = await self.tracker.get_locations(block_id)
        for loc in locations:
            if loc.worker_id == target_worker and loc.is_healthy():
                logger.debug(f"Block {block_id} already on {target_worker}")
                return None

        # Find best source
        source_location = await self._find_best_source(block_id, target_worker)
        if not source_location:
            logger.warning(f"No source available for block {block_id}")
            return None

        # Create transfer request
        import uuid

        transfer_id = f"transfer-{uuid.uuid4().hex[:12]}"

        request = TransferRequest(
            transfer_id=transfer_id,
            block_id=block_id,
            source_worker=source_location.worker_id,
            target_worker=target_worker,
            source_path=source_location.local_path,
            target_path=f"/data/{block_id}",
            priority=priority,
            job_id=job_id,
            size_bytes=block.size_bytes,
            checksum=block.checksum,
            verify_checksum=self.config.verify_checksums,
        )

        # Queue transfer
        await self._queue_transfer(request)

        return transfer_id

    async def request_bulk_transfers(
        self,
        block_ids: List[str],
        target_worker: str,
        priority: TransferPriority = TransferPriority.NORMAL,
        job_id: Optional[str] = None,
    ) -> List[str]:
        """
        Request transfers for multiple blocks.
        طلب نقل لعدة كتل.
        """
        transfer_ids = []

        for block_id in block_ids:
            transfer_id = await self.request_transfer(
                block_id=block_id,
                target_worker=target_worker,
                priority=priority,
                job_id=job_id,
            )
            if transfer_id:
                transfer_ids.append(transfer_id)

        return transfer_ids

    async def cancel_transfer(self, transfer_id: str) -> bool:
        """Cancel a pending or active transfer."""
        if transfer_id in self._active_transfers:
            progress = self._active_transfers[transfer_id]
            progress.state = TransferState.CANCELLED
            return True

        # Can't cancel completed transfers
        return False

    async def get_transfer_progress(
        self,
        transfer_id: str,
    ) -> Optional[TransferProgress]:
        """Get progress of a transfer."""
        return self._active_transfers.get(transfer_id)

    async def get_transfer_result(
        self,
        transfer_id: str,
    ) -> Optional[TransferResult]:
        """Get result of a completed transfer."""
        return self._completed_transfers.get(transfer_id)

    async def wait_for_transfer(
        self,
        transfer_id: str,
        timeout: Optional[float] = None,
    ) -> Optional[TransferResult]:
        """Wait for a transfer to complete."""
        timeout = timeout or self.config.transfer_timeout_seconds
        start = time.time()

        while time.time() - start < timeout:
            # Check if completed
            result = self._completed_transfers.get(transfer_id)
            if result:
                return result

            # Check if failed/cancelled
            progress = self._active_transfers.get(transfer_id)
            if progress and progress.state in (
                TransferState.FAILED,
                TransferState.CANCELLED,
            ):
                return None

            await asyncio.sleep(0.5)

        return None

    async def wait_for_all_transfers(
        self,
        transfer_ids: List[str],
        timeout: Optional[float] = None,
    ) -> List[TransferResult]:
        """Wait for multiple transfers to complete."""
        results = []
        tasks = [self.wait_for_transfer(tid, timeout=timeout) for tid in transfer_ids]
        completed = await asyncio.gather(*tasks)

        for result in completed:
            if result:
                results.append(result)

        return results

    # ==================== Queue Management ====================

    async def _queue_transfer(self, request: TransferRequest) -> None:
        """Add a transfer to the queue."""
        # Priority queue uses (priority, time, request) tuples
        # Lower priority value = higher priority (so negate)
        priority_value = -request.priority.value
        queue_time = time.time()

        await self._pending_queue.put((priority_value, queue_time, request))

        # Create progress tracker
        self._active_transfers[request.transfer_id] = TransferProgress(
            transfer_id=request.transfer_id,
            state=TransferState.QUEUED,
            total_bytes=request.size_bytes,
        )

        logger.debug(f"Queued transfer {request.transfer_id}: " f"{request.block_id} -> {request.target_worker}")

    async def _process_queue(self) -> None:
        """Process the transfer queue."""
        while self._running:
            try:
                # Get next transfer from queue
                priority, queue_time, request = await asyncio.wait_for(
                    self._pending_queue.get(),
                    timeout=1.0,
                )

                # Process transfer
                asyncio.create_task(self._execute_transfer(request))

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue processing error: {e}")

    async def _execute_transfer(self, request: TransferRequest) -> None:
        """Execute a single transfer."""
        transfer_id = request.transfer_id
        progress = self._active_transfers.get(transfer_id)

        if not progress:
            return

        # Acquire semaphores
        await self._global_semaphore.acquire()

        worker_sem = self._get_worker_semaphore(request.target_worker)
        await worker_sem.acquire()

        try:
            # Track worker transfers
            if request.target_worker not in self._worker_transfers:
                self._worker_transfers[request.target_worker] = set()
            self._worker_transfers[request.target_worker].add(transfer_id)

            # Update progress
            progress.state = TransferState.CONNECTING
            progress.started_at = datetime.now(timezone.utc)
            progress.attempt += 1

            # Mark target location as syncing
            await self.tracker.update_location_state(
                request.block_id,
                request.target_worker,
                ReplicaState.SYNCING,
            )

            # Perform transfer
            progress.state = TransferState.TRANSFERRING

            def progress_callback(bytes_transferred: int):
                progress.bytes_transferred = bytes_transferred
                progress.last_update = datetime.now(timezone.utc)

                # Calculate speed
                elapsed = progress.elapsed_seconds
                if elapsed > 0:
                    mb_transferred = bytes_transferred / (1024 * 1024)
                    progress.average_speed_mbps = (mb_transferred / elapsed) * 8

            result = await self.handler.transfer(request, progress_callback)

            # Handle result
            if result.success:
                progress.state = TransferState.COMPLETED
                progress.completed_at = datetime.now(timezone.utc)
                progress.bytes_transferred = result.bytes_transferred

                # Update location as available
                await self.tracker.add_location(
                    block_id=request.block_id,
                    worker_id=request.target_worker,
                    local_path=request.target_path,
                    is_primary=False,
                    state=ReplicaState.AVAILABLE,
                )

                self._completed_transfers[transfer_id] = result
                self._stats["successful_transfers"] += 1
                self._stats["total_bytes_transferred"] += result.bytes_transferred
                self._stats["total_transfer_time_seconds"] += result.transfer_time_seconds

                # Fire callbacks
                for callback in self._on_transfer_complete:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(result)
                        else:
                            callback(result)
                    except Exception as e:
                        logger.error(f"Transfer complete callback error: {e}")

                logger.info(
                    f"Transfer {transfer_id} completed: "
                    f"{result.bytes_transferred / (1024*1024):.2f}MB "
                    f"in {result.transfer_time_seconds:.2f}s"
                )

            else:
                # Handle failure
                await self._handle_transfer_failure(request, progress, result)

        except Exception as e:
            logger.error(f"Transfer {transfer_id} error: {e}")
            progress.state = TransferState.FAILED
            progress.error_message = str(e)
            self._stats["failed_transfers"] += 1

        finally:
            # Release semaphores
            worker_sem.release()
            self._global_semaphore.release()

            # Clean up worker tracking
            if request.target_worker in self._worker_transfers:
                self._worker_transfers[request.target_worker].discard(transfer_id)

            self._stats["total_transfers"] += 1

    async def _handle_transfer_failure(
        self,
        request: TransferRequest,
        progress: TransferProgress,
        result: TransferResult,
    ) -> None:
        """Handle a failed transfer."""
        progress.error_message = result.error_message

        if progress.attempt < self.config.max_retries:
            # Retry with backoff
            progress.state = TransferState.RETRYING
            delay = self.config.retry_delay_seconds * (self.config.retry_backoff_multiplier ** (progress.attempt - 1))
            delay = min(delay, self.config.max_retry_delay_seconds)

            logger.warning(
                f"Transfer {request.transfer_id} failed (attempt {progress.attempt}), " f"retrying in {delay:.1f}s"
            )

            await asyncio.sleep(delay)
            await self._queue_transfer(request)

        else:
            progress.state = TransferState.FAILED
            progress.completed_at = datetime.now(timezone.utc)

            # Mark location as failed
            await self.tracker.update_location_state(
                request.block_id,
                request.target_worker,
                ReplicaState.FAILED,
            )

            self._stats["failed_transfers"] += 1

            # Fire callbacks
            for callback in self._on_transfer_failed:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(result)
                    else:
                        callback(result)
                except Exception as e:
                    logger.error(f"Transfer failed callback error: {e}")

            logger.error(
                f"Transfer {request.transfer_id} failed after " f"{progress.attempt} attempts: {result.error_message}"
            )

    async def _find_best_source(
        self,
        block_id: str,
        target_worker: str,
    ) -> Optional[DataLocation]:
        """Find the best source for a transfer."""
        locations = await self.tracker.get_locations(block_id, healthy_only=True)

        if not locations:
            return None

        # Score by network proximity
        scored = []
        for loc in locations:
            level = self.topology.get_locality_level(loc.worker_id, target_worker)
            bandwidth = self.topology.get_bandwidth(level)

            # Check if worker is busy with transfers
            active_count = len(self._worker_transfers.get(loc.worker_id, set()))

            # Score: higher bandwidth + lower active transfers = better
            score = bandwidth / (1 + active_count)

            # Bonus for primary
            if loc.is_primary:
                score *= 1.2

            scored.append((loc, score))

        if not scored:
            return None

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def _get_worker_semaphore(self, worker_id: str) -> asyncio.Semaphore:
        """Get or create semaphore for a worker."""
        if worker_id not in self._worker_semaphores:
            self._worker_semaphores[worker_id] = asyncio.Semaphore(self.config.max_transfers_per_worker)
        return self._worker_semaphores[worker_id]

    # ==================== Cleanup ====================

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of old transfers."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Every minute

                # Clean up old completed transfers (keep for 1 hour)
                cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
                to_remove = []

                for tid, result in self._completed_transfers.items():
                    progress = self._active_transfers.get(tid)
                    if progress and progress.completed_at:
                        if progress.completed_at < cutoff:
                            to_remove.append(tid)

                for tid in to_remove:
                    del self._completed_transfers[tid]
                    self._active_transfers.pop(tid, None)

                if to_remove:
                    logger.debug(f"Cleaned up {len(to_remove)} old transfers")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    # ==================== Callbacks ====================

    def on_transfer_complete(self, callback: Callable) -> None:
        """Register callback for completed transfers."""
        self._on_transfer_complete.append(callback)

    def on_transfer_failed(self, callback: Callable) -> None:
        """Register callback for failed transfers."""
        self._on_transfer_failed.append(callback)

    # ==================== Statistics ====================

    async def get_stats(self) -> Dict:
        """Get transfer statistics."""
        active_count = sum(
            1 for p in self._active_transfers.values() if p.state in (TransferState.QUEUED, TransferState.TRANSFERRING)
        )

        total = max(self._stats["total_transfers"], 1)

        return {
            **self._stats,
            "active_transfers": active_count,
            "queue_size": self._pending_queue.qsize(),
            "success_rate": self._stats["successful_transfers"] / total,
            "avg_transfer_size_mb": (
                self._stats["total_bytes_transferred"] / (1024 * 1024) / max(self._stats["successful_transfers"], 1)
            ),
            "avg_transfer_time_seconds": (
                self._stats["total_transfer_time_seconds"] / max(self._stats["successful_transfers"], 1)
            ),
        }

    async def get_active_transfers(self) -> List[TransferProgress]:
        """Get all active transfers."""
        return [
            p
            for p in self._active_transfers.values()
            if p.state not in (TransferState.COMPLETED, TransferState.FAILED, TransferState.CANCELLED)
        ]
