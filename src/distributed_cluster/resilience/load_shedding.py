# -*- coding: utf-8 -*-
"""
Load Shedding and Graceful Degradation for NebulaCompute.

Implements intelligent load shedding strategies to maintain system
stability under high load conditions.

تفريغ الحمل والتدهور الرشيق.

Features:
- Priority-based request queuing
- Adaptive load shedding thresholds
- Multiple shedding strategies
- Request admission control
- Quality of Service (QoS) tiers
- Graceful degradation policies
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, IntEnum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PriorityLevel(IntEnum):
    """Request priority levels for QoS."""

    CRITICAL = 0  # System-critical, never shed
    HIGH = 1  # Important business operations
    NORMAL = 2  # Standard requests
    LOW = 3  # Background/batch jobs
    BEST_EFFORT = 4  # Shed first under load


class LoadSheddingStrategy(str, Enum):
    """Load shedding strategy."""

    LIFO = "lifo"  # Last in, first out (newest requests shed first)
    FIFO = "fifo"  # First in, first out (oldest requests shed first)
    PRIORITY = "priority"  # Shed lowest priority first
    RANDOM = "random"  # Random shedding
    ADAPTIVE = "adaptive"  # Adaptive based on load patterns
    FAIR = "fair"  # Fair shedding across clients


class SheddingDecision(str, Enum):
    """Decision for a request."""

    ACCEPT = "accept"  # Process immediately
    QUEUE = "queue"  # Queue for later processing
    SHED = "shed"  # Reject request
    DEGRADE = "degrade"  # Process with degraded features


@dataclass
class QueuedRequest:
    """Represents a queued request."""

    request_id: str
    priority: PriorityLevel
    client_id: str
    payload: Any
    enqueued_at: datetime
    deadline: Optional[datetime] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        """Get request age in seconds."""
        return (datetime.utcnow() - self.enqueued_at).total_seconds()

    @property
    def is_expired(self) -> bool:
        """Check if request has expired."""
        if self.deadline:
            return datetime.utcnow() > self.deadline
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "priority": self.priority.name,
            "client_id": self.client_id,
            "enqueued_at": self.enqueued_at.isoformat(),
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "age_seconds": self.age_seconds,
            "is_expired": self.is_expired,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
        }


@dataclass
class LoadSheddingPolicy:
    """
    Load shedding policy configuration.

    سياسة تفريغ الحمل.
    """

    # Load thresholds (0.0 - 1.0)
    soft_limit: float = 0.7  # Start queuing at 70% load
    hard_limit: float = 0.9  # Start shedding at 90% load
    critical_limit: float = 0.95  # Shed aggressively at 95% load

    # Queue configuration
    max_queue_size: int = 1000
    max_queue_wait_seconds: float = 30.0
    queue_timeout_seconds: float = 60.0

    # Priority configuration
    protect_priorities: List[PriorityLevel] = field(
        default_factory=lambda: [PriorityLevel.CRITICAL]
    )
    shed_priorities: List[PriorityLevel] = field(
        default_factory=lambda: [PriorityLevel.BEST_EFFORT, PriorityLevel.LOW]
    )

    # Rate limiting per client
    max_requests_per_client: int = 100
    client_window_seconds: float = 60.0

    # Degradation settings
    enable_degradation: bool = True
    degradation_features: List[str] = field(
        default_factory=lambda: ["caching", "compression", "pagination"]
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "soft_limit": self.soft_limit,
            "hard_limit": self.hard_limit,
            "critical_limit": self.critical_limit,
            "max_queue_size": self.max_queue_size,
            "max_queue_wait_seconds": self.max_queue_wait_seconds,
            "queue_timeout_seconds": self.queue_timeout_seconds,
            "protect_priorities": [p.name for p in self.protect_priorities],
            "shed_priorities": [p.name for p in self.shed_priorities],
            "max_requests_per_client": self.max_requests_per_client,
            "client_window_seconds": self.client_window_seconds,
            "enable_degradation": self.enable_degradation,
            "degradation_features": self.degradation_features,
        }


@dataclass
class LoadMetrics:
    """Current system load metrics."""

    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    queue_depth: int = 0
    active_requests: int = 0
    requests_per_second: float = 0.0
    average_latency_ms: float = 0.0
    error_rate: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def overall_load(self) -> float:
        """Calculate overall system load (0.0 - 1.0)."""
        # Weighted average of different load indicators
        return min(1.0, (
            self.cpu_utilization * 0.4 +
            self.memory_utilization * 0.3 +
            min(1.0, self.queue_depth / 100) * 0.2 +
            min(1.0, self.error_rate * 10) * 0.1
        ))


class LoadShedder:
    """
    Intelligent load shedding controller.

    وحدة تحكم ذكية لتفريغ الحمل.

    Implements multiple strategies for handling overload:
    1. Admission control - prevent new requests when overloaded
    2. Priority queuing - queue lower priority requests
    3. Request shedding - drop requests when necessary
    4. Graceful degradation - reduce feature set under load
    5. Client fairness - prevent single clients from dominating
    """

    def __init__(
        self,
        policy: Optional[LoadSheddingPolicy] = None,
        strategy: LoadSheddingStrategy = LoadSheddingStrategy.PRIORITY,
        metrics_callback: Optional[Callable[[], LoadMetrics]] = None,
        shed_callback: Optional[Callable[[QueuedRequest, str], None]] = None,
    ):
        """
        Initialize LoadShedder.

        Args:
            policy: Load shedding policy configuration
            strategy: Primary shedding strategy
            metrics_callback: Function to get current load metrics
            shed_callback: Called when a request is shed
        """
        self.policy = policy or LoadSheddingPolicy()
        self.strategy = strategy
        self.metrics_callback = metrics_callback
        self.shed_callback = shed_callback

        # Request queues by priority
        self._queues: Dict[PriorityLevel, Deque[QueuedRequest]] = {
            p: deque() for p in PriorityLevel
        }

        # Client tracking
        self._client_requests: Dict[str, List[float]] = {}
        self._client_lock = asyncio.Lock()

        # State
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Current load state
        self._current_metrics: Optional[LoadMetrics] = None
        self._is_shedding = False
        self._is_degraded = False

        # Statistics
        self._stats = {
            "requests_accepted": 0,
            "requests_queued": 0,
            "requests_shed": 0,
            "requests_degraded": 0,
            "requests_expired": 0,
            "requests_processed": 0,
            "total_queue_time_ms": 0.0,
            "clients_rate_limited": 0,
        }

        # Event handlers
        self._handlers: Dict[str, List[Callable]] = {
            "request_accepted": [],
            "request_shed": [],
            "load_critical": [],
            "load_normal": [],
        }

    async def start(self) -> None:
        """Start the load shedder."""
        if self._running:
            return

        self._running = True
        self._processor_task = asyncio.create_task(self._process_queues())
        logger.info("LoadShedder started")

    async def stop(self) -> None:
        """Stop the load shedder."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("LoadShedder stopped")

    async def admit(
        self,
        request_id: Optional[str] = None,
        priority: PriorityLevel = PriorityLevel.NORMAL,
        client_id: str = "anonymous",
        payload: Any = None,
        deadline_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[SheddingDecision, Optional[QueuedRequest]]:
        """
        Request admission control.

        التحكم في قبول الطلبات.

        Args:
            request_id: Unique request identifier
            priority: Request priority level
            client_id: Client/tenant identifier
            payload: Request payload
            deadline_seconds: Maximum time to wait
            metadata: Additional metadata

        Returns:
            Tuple of (decision, queued_request if queued)
        """
        request_id = request_id or str(uuid.uuid4())
        deadline = None
        if deadline_seconds:
            deadline = datetime.utcnow() + timedelta(seconds=deadline_seconds)

        request = QueuedRequest(
            request_id=request_id,
            priority=priority,
            client_id=client_id,
            payload=payload,
            enqueued_at=datetime.utcnow(),
            deadline=deadline,
            metadata=metadata or {},
        )

        # Get current load
        metrics = await self._get_metrics()
        load = metrics.overall_load

        # Check client rate limit first
        if not await self._check_client_rate(client_id):
            self._stats["clients_rate_limited"] += 1
            self._stats["requests_shed"] += 1
            await self._notify_shed(request, "client_rate_limited")
            return SheddingDecision.SHED, None

        # Protected priorities always accepted
        if priority in self.policy.protect_priorities:
            self._stats["requests_accepted"] += 1
            return SheddingDecision.ACCEPT, request

        # Check load thresholds
        if load >= self.policy.critical_limit:
            # Critical load - aggressive shedding
            if priority in self.policy.shed_priorities:
                self._stats["requests_shed"] += 1
                await self._notify_shed(request, "critical_load")
                return SheddingDecision.SHED, None

        if load >= self.policy.hard_limit:
            # Hard limit - start shedding low priority
            if priority >= PriorityLevel.LOW:
                self._stats["requests_shed"] += 1
                await self._notify_shed(request, "hard_limit")
                return SheddingDecision.SHED, None

            # Queue normal priority if not shedding
            if self._total_queue_size() < self.policy.max_queue_size:
                await self._enqueue(request)
                self._stats["requests_queued"] += 1
                return SheddingDecision.QUEUE, request

            # Queue full, shed
            self._stats["requests_shed"] += 1
            await self._notify_shed(request, "queue_full")
            return SheddingDecision.SHED, None

        if load >= self.policy.soft_limit:
            # Soft limit - degrade if enabled
            if self.policy.enable_degradation:
                self._is_degraded = True
                self._stats["requests_degraded"] += 1
                return SheddingDecision.DEGRADE, request

        # Accept request
        self._is_degraded = False
        self._stats["requests_accepted"] += 1
        return SheddingDecision.ACCEPT, request

    async def _check_client_rate(self, client_id: str) -> bool:
        """Check if client is within rate limits."""
        async with self._client_lock:
            now = time.time()
            window_start = now - self.policy.client_window_seconds

            # Clean old entries
            if client_id in self._client_requests:
                self._client_requests[client_id] = [
                    t for t in self._client_requests[client_id]
                    if t > window_start
                ]
            else:
                self._client_requests[client_id] = []

            # Check rate
            if len(self._client_requests[client_id]) >= self.policy.max_requests_per_client:
                return False

            # Record request
            self._client_requests[client_id].append(now)
            return True

    async def _enqueue(self, request: QueuedRequest) -> None:
        """Add request to priority queue."""
        async with self._lock:
            self._queues[request.priority].append(request)

    async def _dequeue(self) -> Optional[QueuedRequest]:
        """Get next request from queues (highest priority first)."""
        async with self._lock:
            for priority in PriorityLevel:
                queue = self._queues[priority]
                while queue:
                    request = queue.popleft()
                    if not request.is_expired:
                        return request
                    self._stats["requests_expired"] += 1
        return None

    def _total_queue_size(self) -> int:
        """Get total queue size across all priorities."""
        return sum(len(q) for q in self._queues.values())

    async def _get_metrics(self) -> LoadMetrics:
        """Get current load metrics."""
        if self.metrics_callback:
            try:
                metrics = self.metrics_callback()
                if asyncio.iscoroutine(metrics):
                    metrics = await metrics
                self._current_metrics = metrics
                return metrics
            except Exception as e:
                logger.error(f"Error getting metrics: {e}")

        # Generate estimated metrics
        return LoadMetrics(
            queue_depth=self._total_queue_size(),
            active_requests=self._stats["requests_accepted"] - self._stats["requests_processed"],
        )

    async def _process_queues(self) -> None:
        """Process queued requests."""
        while self._running:
            try:
                request = await self._dequeue()
                if request:
                    # Calculate queue time
                    queue_time = request.age_seconds * 1000
                    self._stats["total_queue_time_ms"] += queue_time
                    self._stats["requests_processed"] += 1

                    # Emit event
                    await self._emit("request_accepted", request)

                await asyncio.sleep(0.01)  # Small delay to prevent tight loop
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
                await asyncio.sleep(1.0)

    async def _notify_shed(self, request: QueuedRequest, reason: str) -> None:
        """Notify that a request was shed."""
        if self.shed_callback:
            try:
                result = self.shed_callback(request, reason)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Shed callback error: {e}")

        await self._emit("request_shed", request, reason)

    def on(self, event: str, handler: Callable) -> None:
        """Register event handler."""
        if event in self._handlers:
            self._handlers[event].append(handler)

    async def _emit(self, event: str, *args) -> None:
        """Emit event to handlers."""
        for handler in self._handlers.get(event, []):
            try:
                result = handler(*args)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Event handler error for {event}: {e}")

    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        queue_sizes = {
            p.name: len(self._queues[p]) for p in PriorityLevel
        }
        return {
            "total_queued": self._total_queue_size(),
            "by_priority": queue_sizes,
            "is_shedding": self._is_shedding,
            "is_degraded": self._is_degraded,
        }

    async def get_statistics(self) -> Dict[str, Any]:
        """Get load shedder statistics."""
        avg_queue_time = 0.0
        if self._stats["requests_processed"] > 0:
            avg_queue_time = (
                self._stats["total_queue_time_ms"] /
                self._stats["requests_processed"]
            )

        return {
            **self._stats,
            "average_queue_time_ms": avg_queue_time,
            "queue_size": self._total_queue_size(),
            "is_shedding": self._is_shedding,
            "is_degraded": self._is_degraded,
            "strategy": self.strategy.value,
            "policy": self.policy.to_dict(),
            "running": self._running,
        }

    async def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """Get statistics for a specific client."""
        async with self._client_lock:
            requests = self._client_requests.get(client_id, [])
            now = time.time()
            window_start = now - self.policy.client_window_seconds

            recent_requests = [t for t in requests if t > window_start]

            return {
                "client_id": client_id,
                "requests_in_window": len(recent_requests),
                "window_seconds": self.policy.client_window_seconds,
                "limit": self.policy.max_requests_per_client,
                "remaining": max(0, self.policy.max_requests_per_client - len(recent_requests)),
            }

    async def clear_queues(self) -> int:
        """Clear all queues. Returns number of requests cleared."""
        async with self._lock:
            total = self._total_queue_size()
            for queue in self._queues.values():
                queue.clear()
            return total

    async def shed_by_strategy(self, count: int) -> List[QueuedRequest]:
        """
        Shed requests according to configured strategy.

        تفريغ الطلبات وفقًا للاستراتيجية.

        Args:
            count: Number of requests to shed

        Returns:
            List of shed requests
        """
        shed_requests = []

        async with self._lock:
            if self.strategy == LoadSheddingStrategy.PRIORITY:
                # Shed lowest priority first
                for priority in reversed(list(PriorityLevel)):
                    if priority in self.policy.protect_priorities:
                        continue
                    queue = self._queues[priority]
                    while queue and len(shed_requests) < count:
                        request = queue.pop()
                        shed_requests.append(request)

            elif self.strategy == LoadSheddingStrategy.LIFO:
                # Shed newest first
                for priority in PriorityLevel:
                    if priority in self.policy.protect_priorities:
                        continue
                    queue = self._queues[priority]
                    while queue and len(shed_requests) < count:
                        request = queue.pop()
                        shed_requests.append(request)

            elif self.strategy == LoadSheddingStrategy.FIFO:
                # Shed oldest first
                for priority in reversed(list(PriorityLevel)):
                    if priority in self.policy.protect_priorities:
                        continue
                    queue = self._queues[priority]
                    while queue and len(shed_requests) < count:
                        request = queue.popleft()
                        shed_requests.append(request)

            elif self.strategy == LoadSheddingStrategy.RANDOM:
                # Random shedding
                import random
                all_requests = []
                for priority in PriorityLevel:
                    if priority in self.policy.protect_priorities:
                        continue
                    all_requests.extend(list(self._queues[priority]))
                    self._queues[priority].clear()

                random.shuffle(all_requests)
                shed_requests = all_requests[:count]

                # Put back the ones we're keeping
                for request in all_requests[count:]:
                    self._queues[request.priority].append(request)

        # Notify shed
        for request in shed_requests:
            self._stats["requests_shed"] += 1
            await self._notify_shed(request, f"strategy_{self.strategy.value}")

        return shed_requests

    async def update_policy(self, policy: LoadSheddingPolicy) -> None:
        """Update load shedding policy."""
        self.policy = policy
        logger.info("Load shedding policy updated")

    async def shutdown(self) -> None:
        """Shutdown load shedder."""
        await self.stop()
        cleared = await self.clear_queues()
        logger.info(f"LoadShedder shutdown, cleared {cleared} queued requests")


# Convenience function to create a pre-configured load shedder
def create_load_shedder(
    soft_limit: float = 0.7,
    hard_limit: float = 0.9,
    strategy: str = "priority",
    max_queue_size: int = 1000,
) -> LoadShedder:
    """
    Create a pre-configured load shedder.

    إنشاء مفرغ حمل مُعد مسبقًا.
    """
    policy = LoadSheddingPolicy(
        soft_limit=soft_limit,
        hard_limit=hard_limit,
        max_queue_size=max_queue_size,
    )

    strategy_enum = LoadSheddingStrategy(strategy.lower())

    return LoadShedder(policy=policy, strategy=strategy_enum)
