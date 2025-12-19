"""
Worker Auto-scaler - التحجيم التلقائي
=====================================

نظام تحجيم تلقائي للـ Workers:
- مراقبة الحمل
- قواعد التحجيم
- Cool-down periods
- تكامل مع مزودي السحابة
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ScalingDirection(str, Enum):
    """اتجاه التحجيم."""
    UP = "up"
    DOWN = "down"
    NONE = "none"


class ScalingMetric(str, Enum):
    """مقياس التحجيم."""
    PENDING_JOBS = "pending_jobs"
    QUEUE_TIME = "queue_time"
    CPU_UTILIZATION = "cpu_utilization"
    MEMORY_UTILIZATION = "memory_utilization"
    GPU_UTILIZATION = "gpu_utilization"
    WORKER_COUNT = "worker_count"


@dataclass
class ScalingRule:
    """قاعدة تحجيم واحدة."""
    name: str
    metric: ScalingMetric
    threshold_up: float  # قيمة للتحجيم لأعلى
    threshold_down: float  # قيمة للتحجيم لأسفل
    scale_up_by: int = 1  # عدد العمال للإضافة
    scale_down_by: int = 1  # عدد العمال للإزالة
    evaluation_periods: int = 3  # عدد الفترات للتقييم
    enabled: bool = True


@dataclass
class ScalingPolicy:
    """سياسة التحجيم."""
    name: str
    rules: List[ScalingRule] = field(default_factory=list)

    # Limits
    min_workers: int = 1
    max_workers: int = 100

    # Cool-down
    scale_up_cooldown_seconds: int = 60
    scale_down_cooldown_seconds: int = 300

    # Timing
    evaluation_interval_seconds: int = 30

    # Tags for workers
    worker_tags: List[str] = field(default_factory=list)
    worker_labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class ScalingDecision:
    """قرار تحجيم."""
    direction: ScalingDirection
    count: int
    reason: str
    metric_values: Dict[str, float]
    rule_triggered: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ScalingEvent:
    """حدث تحجيم."""
    event_id: str
    direction: ScalingDirection
    requested_count: int
    actual_count: int
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    success: bool = False
    error: Optional[str] = None


class MetricsProvider(ABC):
    """مزود المقاييس."""

    @abstractmethod
    async def get_metric(self, metric: ScalingMetric) -> float:
        """الحصول على قيمة مقياس."""
        pass

    @abstractmethod
    async def get_current_worker_count(self) -> int:
        """عدد العمال الحاليين."""
        pass


class WorkerProvisioner(ABC):
    """مزود العمال (للتحجيم الفعلي)."""

    @abstractmethod
    async def provision_workers(self, count: int, tags: List[str], labels: Dict[str, str]) -> List[str]:
        """
        إنشاء عمال جدد.

        Returns:
            قائمة معرفات العمال الجدد
        """
        pass

    @abstractmethod
    async def terminate_workers(self, worker_ids: List[str]) -> int:
        """
        إنهاء عمال.

        Returns:
            عدد العمال الذين تم إنهاؤهم
        """
        pass

    @abstractmethod
    async def get_terminable_workers(self, count: int) -> List[str]:
        """
        الحصول على قائمة العمال القابلين للإنهاء.

        يجب تجنب العمال الذين يعملون على مهام.
        """
        pass


class DefaultMetricsProvider(MetricsProvider):
    """مزود مقاييس افتراضي من الـ Scheduler."""

    def __init__(self, scheduler, workers_func: Callable[[], List[Any]]):
        self.scheduler = scheduler
        self.get_workers = workers_func

    async def get_metric(self, metric: ScalingMetric) -> float:
        """الحصول على قيمة مقياس."""
        if metric == ScalingMetric.PENDING_JOBS:
            return float(self.scheduler.pending_jobs_count)

        elif metric == ScalingMetric.QUEUE_TIME:
            # Average queue time for pending jobs
            pending = self.scheduler.get_pending_jobs()
            if not pending:
                return 0.0
            now = datetime.utcnow()
            times = [(now - job.created_at).total_seconds() for job in pending]
            return statistics.mean(times) if times else 0.0

        elif metric == ScalingMetric.WORKER_COUNT:
            return float(len(self.get_workers()))

        elif metric == ScalingMetric.CPU_UTILIZATION:
            workers = self.get_workers()
            if not workers:
                return 0.0
            total_cpu = sum(w.total_resources.cpu_cores for w in workers)
            used_cpu = sum(
                w.total_resources.cpu_cores - w.available_resources.cpu_cores
                for w in workers
            )
            return (used_cpu / total_cpu * 100) if total_cpu > 0 else 0.0

        elif metric == ScalingMetric.MEMORY_UTILIZATION:
            workers = self.get_workers()
            if not workers:
                return 0.0
            total_mem = sum(w.total_resources.memory_mb for w in workers)
            used_mem = sum(
                w.total_resources.memory_mb - w.available_resources.memory_mb
                for w in workers
            )
            return (used_mem / total_mem * 100) if total_mem > 0 else 0.0

        elif metric == ScalingMetric.GPU_UTILIZATION:
            workers = self.get_workers()
            if not workers:
                return 0.0
            total_gpu = sum(w.total_resources.gpu_count for w in workers)
            used_gpu = sum(
                w.total_resources.gpu_count - w.available_resources.gpu_count
                for w in workers
            )
            return (used_gpu / total_gpu * 100) if total_gpu > 0 else 0.0

        return 0.0

    async def get_current_worker_count(self) -> int:
        return len(self.get_workers())


class DryRunProvisioner(WorkerProvisioner):
    """مزود وهمي للاختبار."""

    def __init__(self):
        self._workers: List[str] = []
        self._counter = 0

    async def provision_workers(self, count: int, tags: List[str], labels: Dict[str, str]) -> List[str]:
        new_workers = []
        for _ in range(count):
            self._counter += 1
            worker_id = f"dry-run-worker-{self._counter}"
            self._workers.append(worker_id)
            new_workers.append(worker_id)
        logger.info(f"[DRY RUN] Would provision {count} workers: {new_workers}")
        return new_workers

    async def terminate_workers(self, worker_ids: List[str]) -> int:
        terminated = 0
        for wid in worker_ids:
            if wid in self._workers:
                self._workers.remove(wid)
                terminated += 1
        logger.info(f"[DRY RUN] Would terminate {terminated} workers: {worker_ids}")
        return terminated

    async def get_terminable_workers(self, count: int) -> List[str]:
        return self._workers[:count]


class AutoScaler:
    """
    مدير التحجيم التلقائي.

    يراقب المقاييس ويتخذ قرارات التحجيم.
    """

    def __init__(
        self,
        policy: ScalingPolicy,
        metrics_provider: MetricsProvider,
        provisioner: WorkerProvisioner,
    ):
        self.policy = policy
        self.metrics = metrics_provider
        self.provisioner = provisioner

        # State
        self._last_scale_up: Optional[datetime] = None
        self._last_scale_down: Optional[datetime] = None
        self._metric_history: Dict[ScalingMetric, List[float]] = {}
        self._events: List[ScalingEvent] = []

        # Control
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """بدء التحجيم التلقائي."""
        self._running = True
        self._task = asyncio.create_task(self._scaling_loop())
        logger.info(f"AutoScaler started with policy '{self.policy.name}'")

    async def stop(self) -> None:
        """إيقاف التحجيم التلقائي."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AutoScaler stopped")

    async def _scaling_loop(self) -> None:
        """حلقة التحجيم."""
        while self._running:
            try:
                await self._evaluate_and_scale()
            except Exception as e:
                logger.error(f"AutoScaler error: {e}")

            await asyncio.sleep(self.policy.evaluation_interval_seconds)

    async def _evaluate_and_scale(self) -> None:
        """تقييم واتخاذ قرار التحجيم."""
        # Collect metrics
        current_metrics = {}
        for rule in self.policy.rules:
            if rule.enabled:
                value = await self.metrics.get_metric(rule.metric)
                current_metrics[rule.metric] = value

                # Update history
                if rule.metric not in self._metric_history:
                    self._metric_history[rule.metric] = []
                self._metric_history[rule.metric].append(value)

                # Keep only recent history
                max_history = max(r.evaluation_periods for r in self.policy.rules) + 1
                self._metric_history[rule.metric] = self._metric_history[rule.metric][-max_history:]

        # Get current worker count
        current_workers = await self.metrics.get_current_worker_count()

        # Evaluate rules
        decision = await self._evaluate_rules(current_metrics, current_workers)

        if decision.direction != ScalingDirection.NONE:
            await self._execute_scaling(decision, current_workers)

    async def _evaluate_rules(
        self,
        current_metrics: Dict[ScalingMetric, float],
        current_workers: int,
    ) -> ScalingDecision:
        """تقييم القواعد."""
        # Check scale up first
        for rule in self.policy.rules:
            if not rule.enabled:
                continue

            history = self._metric_history.get(rule.metric, [])
            if len(history) < rule.evaluation_periods:
                continue

            recent = history[-rule.evaluation_periods:]

            # Scale up check
            if all(v >= rule.threshold_up for v in recent):
                if current_workers >= self.policy.max_workers:
                    continue

                if not self._can_scale_up():
                    continue

                return ScalingDecision(
                    direction=ScalingDirection.UP,
                    count=min(rule.scale_up_by, self.policy.max_workers - current_workers),
                    reason=f"Rule '{rule.name}': {rule.metric.value} >= {rule.threshold_up}",
                    metric_values=current_metrics,
                    rule_triggered=rule.name,
                )

        # Check scale down
        for rule in self.policy.rules:
            if not rule.enabled:
                continue

            history = self._metric_history.get(rule.metric, [])
            if len(history) < rule.evaluation_periods:
                continue

            recent = history[-rule.evaluation_periods:]

            # Scale down check
            if all(v <= rule.threshold_down for v in recent):
                if current_workers <= self.policy.min_workers:
                    continue

                if not self._can_scale_down():
                    continue

                return ScalingDecision(
                    direction=ScalingDirection.DOWN,
                    count=min(rule.scale_down_by, current_workers - self.policy.min_workers),
                    reason=f"Rule '{rule.name}': {rule.metric.value} <= {rule.threshold_down}",
                    metric_values=current_metrics,
                    rule_triggered=rule.name,
                )

        return ScalingDecision(
            direction=ScalingDirection.NONE,
            count=0,
            reason="No scaling needed",
            metric_values=current_metrics,
        )

    def _can_scale_up(self) -> bool:
        """هل يمكن التحجيم لأعلى (cool-down)؟"""
        if self._last_scale_up is None:
            return True
        elapsed = (datetime.utcnow() - self._last_scale_up).total_seconds()
        return elapsed >= self.policy.scale_up_cooldown_seconds

    def _can_scale_down(self) -> bool:
        """هل يمكن التحجيم لأسفل (cool-down)؟"""
        if self._last_scale_down is None:
            return True
        elapsed = (datetime.utcnow() - self._last_scale_down).total_seconds()
        return elapsed >= self.policy.scale_down_cooldown_seconds

    async def _execute_scaling(self, decision: ScalingDecision, current_workers: int) -> None:
        """تنفيذ قرار التحجيم."""
        event = ScalingEvent(
            event_id=f"scale-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            direction=decision.direction,
            requested_count=decision.count,
            actual_count=0,
            reason=decision.reason,
        )

        try:
            if decision.direction == ScalingDirection.UP:
                logger.info(f"Scaling UP by {decision.count}: {decision.reason}")

                new_workers = await self.provisioner.provision_workers(
                    decision.count,
                    self.policy.worker_tags,
                    self.policy.worker_labels,
                )

                event.actual_count = len(new_workers)
                event.success = True
                self._last_scale_up = datetime.utcnow()

            elif decision.direction == ScalingDirection.DOWN:
                logger.info(f"Scaling DOWN by {decision.count}: {decision.reason}")

                workers_to_terminate = await self.provisioner.get_terminable_workers(decision.count)
                terminated = await self.provisioner.terminate_workers(workers_to_terminate)

                event.actual_count = terminated
                event.success = True
                self._last_scale_down = datetime.utcnow()

        except Exception as e:
            event.success = False
            event.error = str(e)
            logger.error(f"Scaling failed: {e}")

        event.completed_at = datetime.utcnow()
        self._events.append(event)

        # Keep only recent events
        self._events = self._events[-100:]

    def get_status(self) -> Dict[str, Any]:
        """حالة المحجم."""
        return {
            "running": self._running,
            "policy": self.policy.name,
            "min_workers": self.policy.min_workers,
            "max_workers": self.policy.max_workers,
            "last_scale_up": self._last_scale_up.isoformat() if self._last_scale_up else None,
            "last_scale_down": self._last_scale_down.isoformat() if self._last_scale_down else None,
            "recent_events": [
                {
                    "event_id": e.event_id,
                    "direction": e.direction.value,
                    "count": e.actual_count,
                    "success": e.success,
                    "reason": e.reason,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in self._events[-10:]
            ],
        }

    def get_current_metrics(self) -> Dict[str, List[float]]:
        """المقاييس الحالية."""
        return {
            metric.value: values
            for metric, values in self._metric_history.items()
        }


# =============================================================================
# Predefined Policies
# =============================================================================

class ScalingPolicies:
    """سياسات تحجيم جاهزة."""

    @staticmethod
    def aggressive() -> ScalingPolicy:
        """سياسة عدوانية (تحجيم سريع)."""
        return ScalingPolicy(
            name="aggressive",
            rules=[
                ScalingRule(
                    name="pending-jobs-up",
                    metric=ScalingMetric.PENDING_JOBS,
                    threshold_up=10,
                    threshold_down=2,
                    scale_up_by=2,
                    scale_down_by=1,
                    evaluation_periods=2,
                ),
                ScalingRule(
                    name="cpu-utilization",
                    metric=ScalingMetric.CPU_UTILIZATION,
                    threshold_up=70,
                    threshold_down=30,
                    scale_up_by=1,
                    scale_down_by=1,
                    evaluation_periods=2,
                ),
            ],
            min_workers=1,
            max_workers=50,
            scale_up_cooldown_seconds=30,
            scale_down_cooldown_seconds=120,
            evaluation_interval_seconds=15,
        )

    @staticmethod
    def conservative() -> ScalingPolicy:
        """سياسة محافظة (تحجيم بطيء)."""
        return ScalingPolicy(
            name="conservative",
            rules=[
                ScalingRule(
                    name="pending-jobs-up",
                    metric=ScalingMetric.PENDING_JOBS,
                    threshold_up=50,
                    threshold_down=5,
                    scale_up_by=1,
                    scale_down_by=1,
                    evaluation_periods=5,
                ),
                ScalingRule(
                    name="cpu-utilization",
                    metric=ScalingMetric.CPU_UTILIZATION,
                    threshold_up=85,
                    threshold_down=20,
                    scale_up_by=1,
                    scale_down_by=1,
                    evaluation_periods=5,
                ),
            ],
            min_workers=2,
            max_workers=20,
            scale_up_cooldown_seconds=120,
            scale_down_cooldown_seconds=600,
            evaluation_interval_seconds=60,
        )

    @staticmethod
    def queue_based() -> ScalingPolicy:
        """سياسة قائمة على طابور المهام."""
        return ScalingPolicy(
            name="queue-based",
            rules=[
                ScalingRule(
                    name="queue-time",
                    metric=ScalingMetric.QUEUE_TIME,
                    threshold_up=60,  # 60 seconds average wait
                    threshold_down=10,
                    scale_up_by=2,
                    scale_down_by=1,
                    evaluation_periods=3,
                ),
                ScalingRule(
                    name="pending-jobs",
                    metric=ScalingMetric.PENDING_JOBS,
                    threshold_up=100,
                    threshold_down=10,
                    scale_up_by=3,
                    scale_down_by=1,
                    evaluation_periods=2,
                ),
            ],
            min_workers=1,
            max_workers=100,
            scale_up_cooldown_seconds=60,
            scale_down_cooldown_seconds=300,
            evaluation_interval_seconds=30,
        )

    @staticmethod
    def gpu_optimized() -> ScalingPolicy:
        """سياسة محسنة لـ GPU."""
        return ScalingPolicy(
            name="gpu-optimized",
            rules=[
                ScalingRule(
                    name="gpu-utilization",
                    metric=ScalingMetric.GPU_UTILIZATION,
                    threshold_up=80,
                    threshold_down=20,
                    scale_up_by=1,
                    scale_down_by=1,
                    evaluation_periods=3,
                ),
                ScalingRule(
                    name="pending-jobs",
                    metric=ScalingMetric.PENDING_JOBS,
                    threshold_up=5,
                    threshold_down=0,
                    scale_up_by=1,
                    scale_down_by=1,
                    evaluation_periods=3,
                ),
            ],
            min_workers=0,
            max_workers=8,
            scale_up_cooldown_seconds=120,
            scale_down_cooldown_seconds=600,
            evaluation_interval_seconds=60,
            worker_tags=["gpu", "nvidia"],
        )
