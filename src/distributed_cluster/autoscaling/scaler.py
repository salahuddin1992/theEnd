"""
Auto-Scaling Manager - مدير التوسع التلقائي الرئيسي
===================================================

Main Auto-Scaling Manager
-------------------------

This module provides the main orchestrator for auto-scaling workers.
It coordinates between metrics collection, policy evaluation, and
cloud provider actions.

يوفر هذا الملف المنسق الرئيسي للتوسع التلقائي:
- جمع المقاييس
- تقييم السياسات
- تنفيذ قرارات التوسع
- إدارة فترات التهدئة
- تتبع الأحداث

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from distributed_cluster.autoscaling.metrics import MetricsCollector, ResourceMetrics
    from distributed_cluster.autoscaling.policies import ScalingDecision, ScalingPolicy
    from distributed_cluster.autoscaling.providers import CloudProvider
    from distributed_cluster.master.state import ClusterState

logger = logging.getLogger(__name__)


class AutoScalingStatus(str, Enum):
    """
    حالة نظام التوسع التلقائي
    Auto-scaling system status
    """

    IDLE = "idle"  # خامل
    STARTING = "starting"  # يبدأ
    RUNNING = "running"  # يعمل
    SCALING_UP = "scaling_up"  # يوسّع
    SCALING_DOWN = "scaling_down"  # يقلّص
    COOLDOWN = "cooldown"  # فترة تهدئة
    PAUSED = "paused"  # متوقف مؤقتاً
    STOPPED = "stopped"  # متوقف
    ERROR = "error"  # خطأ


@dataclass
class AutoScalingConfig:
    """
    إعدادات التوسع التلقائي
    Auto-scaling configuration
    """

    # General settings
    enabled: bool = True
    evaluation_interval_seconds: float = 30.0  # فترة التقييم

    # Cooldown periods / فترات التهدئة
    cooldown_up_seconds: float = 60.0  # تهدئة بعد التوسع
    cooldown_down_seconds: float = 300.0  # تهدئة بعد التقليص
    cooldown_error_seconds: float = 120.0  # تهدئة بعد الخطأ

    # Limits / الحدود
    min_workers: int = 1  # الحد الأدنى للعمال
    max_workers: int = 100  # الحد الأقصى للعمال
    max_scale_up_per_cycle: int = 5  # أقصى توسع في دورة واحدة
    max_scale_down_per_cycle: int = 2  # أقصى تقليص في دورة واحدة

    # Safety / الأمان
    grace_period_seconds: float = 60.0  # فترة الانتظار قبل التقليص
    drain_timeout_seconds: float = 300.0  # مهلة تفريغ العامل
    health_check_before_scale: bool = True  # فحص الصحة قبل التوسع

    # Worker configuration / إعدادات العامل
    worker_tags: list[str] = field(default_factory=list)
    worker_labels: dict[str, str] = field(default_factory=dict)
    worker_instance_type: str = "default"

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس / Convert to dictionary"""
        return {
            "enabled": self.enabled,
            "evaluation_interval_seconds": self.evaluation_interval_seconds,
            "cooldown_up_seconds": self.cooldown_up_seconds,
            "cooldown_down_seconds": self.cooldown_down_seconds,
            "cooldown_error_seconds": self.cooldown_error_seconds,
            "min_workers": self.min_workers,
            "max_workers": self.max_workers,
            "max_scale_up_per_cycle": self.max_scale_up_per_cycle,
            "max_scale_down_per_cycle": self.max_scale_down_per_cycle,
            "grace_period_seconds": self.grace_period_seconds,
            "drain_timeout_seconds": self.drain_timeout_seconds,
            "health_check_before_scale": self.health_check_before_scale,
            "worker_tags": self.worker_tags,
            "worker_labels": self.worker_labels,
            "worker_instance_type": self.worker_instance_type,
        }


@dataclass
class AutoScalingEvent:
    """
    حدث توسع تلقائي
    Auto-scaling event
    """

    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    event_type: str = "scaling"  # scaling, cooldown, error, info
    direction: str = "none"  # up, down, none
    requested_count: int = 0
    actual_count: int = 0
    reason: str = ""
    policy_name: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    success: bool = True
    error_message: Optional[str] = None
    worker_ids: list[str] = field(default_factory=list)
    metrics_snapshot: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس / Convert to dictionary"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "direction": self.direction,
            "requested_count": self.requested_count,
            "actual_count": self.actual_count,
            "reason": self.reason,
            "policy_name": self.policy_name,
            "timestamp": self.timestamp.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "success": self.success,
            "error_message": self.error_message,
            "worker_ids": self.worker_ids,
        }


@dataclass
class AutoScalingState:
    """
    حالة نظام التوسع التلقائي
    Auto-scaling system state
    """

    status: AutoScalingStatus = AutoScalingStatus.IDLE
    current_worker_count: int = 0
    target_worker_count: int = 0
    last_scale_up: Optional[datetime] = None
    last_scale_down: Optional[datetime] = None
    last_evaluation: Optional[datetime] = None
    last_error: Optional[str] = None
    consecutive_errors: int = 0
    total_scale_ups: int = 0
    total_scale_downs: int = 0
    total_workers_provisioned: int = 0
    total_workers_terminated: int = 0

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس / Convert to dictionary"""
        return {
            "status": self.status.value,
            "current_worker_count": self.current_worker_count,
            "target_worker_count": self.target_worker_count,
            "last_scale_up": self.last_scale_up.isoformat() if self.last_scale_up else None,
            "last_scale_down": self.last_scale_down.isoformat() if self.last_scale_down else None,
            "last_evaluation": self.last_evaluation.isoformat() if self.last_evaluation else None,
            "last_error": self.last_error,
            "consecutive_errors": self.consecutive_errors,
            "total_scale_ups": self.total_scale_ups,
            "total_scale_downs": self.total_scale_downs,
            "total_workers_provisioned": self.total_workers_provisioned,
            "total_workers_terminated": self.total_workers_terminated,
        }


class AutoScalingManager:
    """
    مدير التوسع التلقائي الرئيسي
    Main Auto-Scaling Manager

    ينسق بين جمع المقاييس وتقييم السياسات وتنفيذ
    قرارات التوسع عبر مزود السحابة.

    Coordinates between metrics collection, policy evaluation,
    and scaling execution via cloud provider.
    """

    def __init__(
        self,
        metrics_collector: MetricsCollector,
        policy: ScalingPolicy,
        provider: CloudProvider,
        cluster_state: Optional[ClusterState] = None,
        config: Optional[AutoScalingConfig] = None,
    ):
        """
        تهيئة مدير التوسع التلقائي

        Args:
            metrics_collector: جامع المقاييس
            policy: سياسة التوسع
            provider: مزود السحابة
            cluster_state: حالة الكلاستر (اختياري)
            config: الإعدادات (اختياري)
        """
        self.metrics_collector = metrics_collector
        self.policy = policy
        self.provider = provider
        self.cluster_state = cluster_state
        self.config = config or AutoScalingConfig()

        # الحالة
        self.state = AutoScalingState()

        # سجل الأحداث
        self._events: list[AutoScalingEvent] = []
        self._max_events = 1000

        # التحكم
        self._running = False
        self._paused = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Callbacks
        self._on_scale_up: list[Callable[[AutoScalingEvent], None]] = []
        self._on_scale_down: list[Callable[[AutoScalingEvent], None]] = []
        self._on_error: list[Callable[[AutoScalingEvent], None]] = []

        logger.info(
            f"AutoScalingManager initialized: policy={policy.name}, "
            f"provider={provider.__class__.__name__}"
        )

    # =========================================================================
    # Lifecycle / دورة الحياة
    # =========================================================================

    async def start(self) -> None:
        """
        بدء التوسع التلقائي
        Start auto-scaling
        """
        if self._running:
            logger.warning("AutoScalingManager already running")
            return

        self._running = True
        self._paused = False
        self.state.status = AutoScalingStatus.STARTING

        # التحقق من الاتصال بمزود السحابة
        try:
            await self.provider.connect()
            logger.info(f"Connected to cloud provider: {self.provider.__class__.__name__}")
        except Exception as e:
            logger.error(f"Failed to connect to cloud provider: {e}")
            self.state.status = AutoScalingStatus.ERROR
            self.state.last_error = str(e)
            raise

        # بدء حلقة التوسع
        self._task = asyncio.create_task(self._scaling_loop())
        self.state.status = AutoScalingStatus.RUNNING

        self._add_event(AutoScalingEvent(
            event_type="info",
            reason="Auto-scaling started",
        ))

        logger.info("AutoScalingManager started")

    async def stop(self) -> None:
        """
        إيقاف التوسع التلقائي
        Stop auto-scaling
        """
        if not self._running:
            return

        self._running = False
        self.state.status = AutoScalingStatus.STOPPED

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        try:
            await self.provider.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting from provider: {e}")

        self._add_event(AutoScalingEvent(
            event_type="info",
            reason="Auto-scaling stopped",
        ))

        logger.info("AutoScalingManager stopped")

    def pause(self) -> None:
        """
        إيقاف مؤقت للتوسع
        Pause auto-scaling
        """
        self._paused = True
        self.state.status = AutoScalingStatus.PAUSED
        logger.info("AutoScalingManager paused")

    def resume(self) -> None:
        """
        استئناف التوسع
        Resume auto-scaling
        """
        self._paused = False
        self.state.status = AutoScalingStatus.RUNNING
        logger.info("AutoScalingManager resumed")

    # =========================================================================
    # Scaling Loop / حلقة التوسع
    # =========================================================================

    async def _scaling_loop(self) -> None:
        """حلقة التوسع الرئيسية / Main scaling loop"""
        while self._running:
            try:
                if not self._paused and self.config.enabled:
                    await self._evaluate_and_scale()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scaling loop error: {e}")
                self.state.consecutive_errors += 1
                self.state.last_error = str(e)

                if self.state.consecutive_errors >= 5:
                    self.state.status = AutoScalingStatus.ERROR
                    logger.critical("Too many consecutive errors, entering error state")

            await asyncio.sleep(self.config.evaluation_interval_seconds)

    async def _evaluate_and_scale(self) -> None:
        """
        تقييم المقاييس وتنفيذ التوسع
        Evaluate metrics and execute scaling
        """
        async with self._lock:
            self.state.last_evaluation = datetime.now(timezone.utc)

            # جمع المقاييس
            try:
                metrics = await self.metrics_collector.collect_now()
            except Exception as e:
                logger.error(f"Failed to collect metrics: {e}")
                return

            # تحديث عدد العمال الحالي
            current_workers = await self._get_current_worker_count()
            self.state.current_worker_count = current_workers

            # التحقق من فترة التهدئة
            if self._in_cooldown():
                self.state.status = AutoScalingStatus.COOLDOWN
                return

            # تقييم السياسة
            try:
                decision = await self.policy.evaluate(
                    metrics, current_workers, self.metrics_collector
                )
            except Exception as e:
                logger.error(f"Policy evaluation failed: {e}")
                return

            # تنفيذ القرار
            from distributed_cluster.autoscaling.policies import ScalingDirection

            if decision.direction == ScalingDirection.UP:
                await self._scale_up(decision, metrics)
            elif decision.direction == ScalingDirection.DOWN:
                await self._scale_down(decision, metrics)
            else:
                self.state.status = AutoScalingStatus.RUNNING
                logger.debug(f"No scaling needed: {decision.reason}")

            # إعادة تعيين عداد الأخطاء عند النجاح
            self.state.consecutive_errors = 0

    async def _scale_up(
        self,
        decision: ScalingDecision,
        metrics: ResourceMetrics,
    ) -> None:
        """
        تنفيذ التوسع
        Execute scale up
        """
        self.state.status = AutoScalingStatus.SCALING_UP

        # تحديد العدد الفعلي للتوسع
        count = min(decision.count, self.config.max_scale_up_per_cycle)
        max_possible = self.config.max_workers - self.state.current_worker_count
        count = min(count, max_possible)

        if count <= 0:
            logger.info(f"Scale up blocked: at max workers ({self.config.max_workers})")
            self.state.status = AutoScalingStatus.RUNNING
            return

        event = AutoScalingEvent(
            event_type="scaling",
            direction="up",
            requested_count=decision.count,
            actual_count=0,
            reason=decision.reason,
            policy_name=decision.policy_name,
            metrics_snapshot=metrics.to_dict(),
        )

        try:
            logger.info(f"Scaling UP by {count}: {decision.reason}")

            # إنشاء العمال
            worker_ids = await self.provider.provision_workers(
                count=count,
                instance_type=self.config.worker_instance_type,
                tags=self.config.worker_tags,
                labels=self.config.worker_labels,
            )

            event.actual_count = len(worker_ids)
            event.worker_ids = worker_ids
            event.success = True
            event.completed_at = datetime.now(timezone.utc)

            # تحديث الحالة
            self.state.last_scale_up = datetime.now(timezone.utc)
            self.state.total_scale_ups += 1
            self.state.total_workers_provisioned += len(worker_ids)
            self.state.target_worker_count = self.state.current_worker_count + len(worker_ids)

            logger.info(f"Scale UP completed: {len(worker_ids)} workers created")

            # استدعاء callbacks
            for callback in self._on_scale_up:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Scale up callback error: {e}")

        except Exception as e:
            event.success = False
            event.error_message = str(e)
            event.completed_at = datetime.now(timezone.utc)
            logger.error(f"Scale UP failed: {e}")

            for callback in self._on_error:
                try:
                    callback(event)
                except Exception as cb_e:
                    logger.error(f"Error callback error: {cb_e}")

        self._add_event(event)
        self.state.status = AutoScalingStatus.RUNNING

    async def _scale_down(
        self,
        decision: ScalingDecision,
        metrics: ResourceMetrics,
    ) -> None:
        """
        تنفيذ التقليص
        Execute scale down
        """
        self.state.status = AutoScalingStatus.SCALING_DOWN

        # تحديد العدد الفعلي للتقليص
        count = min(decision.count, self.config.max_scale_down_per_cycle)
        min_possible = self.state.current_worker_count - self.config.min_workers
        count = min(count, min_possible)

        if count <= 0:
            logger.info(f"Scale down blocked: at min workers ({self.config.min_workers})")
            self.state.status = AutoScalingStatus.RUNNING
            return

        event = AutoScalingEvent(
            event_type="scaling",
            direction="down",
            requested_count=decision.count,
            actual_count=0,
            reason=decision.reason,
            policy_name=decision.policy_name,
            metrics_snapshot=metrics.to_dict(),
        )

        try:
            logger.info(f"Scaling DOWN by {count}: {decision.reason}")

            # الحصول على العمال القابلين للإنهاء
            terminable = await self.provider.get_terminable_workers(count)

            if not terminable:
                logger.warning("No terminable workers found")
                event.reason = "No terminable workers found"
                self.state.status = AutoScalingStatus.RUNNING
                self._add_event(event)
                return

            # تفريغ العمال (drain) إذا لزم الأمر
            if self.config.drain_timeout_seconds > 0:
                await self._drain_workers(terminable[:count])

            # إنهاء العمال
            terminated = await self.provider.terminate_workers(terminable[:count])

            event.actual_count = terminated
            event.worker_ids = terminable[:terminated]
            event.success = True
            event.completed_at = datetime.now(timezone.utc)

            # تحديث الحالة
            self.state.last_scale_down = datetime.now(timezone.utc)
            self.state.total_scale_downs += 1
            self.state.total_workers_terminated += terminated
            self.state.target_worker_count = self.state.current_worker_count - terminated

            logger.info(f"Scale DOWN completed: {terminated} workers terminated")

            # استدعاء callbacks
            for callback in self._on_scale_down:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Scale down callback error: {e}")

        except Exception as e:
            event.success = False
            event.error_message = str(e)
            event.completed_at = datetime.now(timezone.utc)
            logger.error(f"Scale DOWN failed: {e}")

            for callback in self._on_error:
                try:
                    callback(event)
                except Exception as cb_e:
                    logger.error(f"Error callback error: {cb_e}")

        self._add_event(event)
        self.state.status = AutoScalingStatus.RUNNING

    async def _drain_workers(self, worker_ids: list[str]) -> None:
        """
        تفريغ العمال قبل الإنهاء
        Drain workers before termination

        يمنع تعيين مهام جديدة وينتظر انتهاء المهام الحالية.
        Prevents new job assignment and waits for current jobs to complete.
        """
        if not self.cluster_state:
            logger.debug("No cluster state, skipping drain")
            return

        for worker_id in worker_ids:
            worker = self.cluster_state.get_worker(worker_id)
            if worker:
                # وضع العامل في حالة التفريغ
                worker.draining = True
                logger.debug(f"Worker {worker_id} set to draining")

        # انتظار انتهاء المهام
        timeout = self.config.drain_timeout_seconds
        start_time = datetime.now(timezone.utc)

        while (datetime.now(timezone.utc) - start_time).total_seconds() < timeout:
            all_drained = True

            for worker_id in worker_ids:
                worker = self.cluster_state.get_worker(worker_id)
                if worker and len(worker.active_jobs) > 0:
                    all_drained = False
                    break

            if all_drained:
                logger.debug("All workers drained")
                return

            await asyncio.sleep(5)

        logger.warning(f"Drain timeout reached after {timeout}s")

    # =========================================================================
    # Helper Methods / طرق مساعدة
    # =========================================================================

    async def _get_current_worker_count(self) -> int:
        """الحصول على عدد العمال الحاليين / Get current worker count"""
        if self.cluster_state:
            return len(self.cluster_state.get_healthy_workers())
        else:
            return await self.provider.get_worker_count()

    def _in_cooldown(self) -> bool:
        """هل في فترة تهدئة؟ / Is in cooldown period?"""
        now = datetime.now(timezone.utc)

        # تهدئة بعد التوسع
        if self.state.last_scale_up:
            elapsed = (now - self.state.last_scale_up).total_seconds()
            if elapsed < self.config.cooldown_up_seconds:
                remaining = self.config.cooldown_up_seconds - elapsed
                logger.debug(f"In scale-up cooldown: {remaining:.0f}s remaining")
                return True

        # تهدئة بعد التقليص
        if self.state.last_scale_down:
            elapsed = (now - self.state.last_scale_down).total_seconds()
            if elapsed < self.config.cooldown_down_seconds:
                remaining = self.config.cooldown_down_seconds - elapsed
                logger.debug(f"In scale-down cooldown: {remaining:.0f}s remaining")
                return True

        return False

    def _add_event(self, event: AutoScalingEvent) -> None:
        """إضافة حدث للسجل / Add event to log"""
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

    # =========================================================================
    # Manual Scaling / التوسع اليدوي
    # =========================================================================

    async def scale_to(self, target_count: int) -> AutoScalingEvent:
        """
        التوسع إلى عدد محدد من العمال
        Scale to specific worker count

        Args:
            target_count: العدد المستهدف

        Returns:
            AutoScalingEvent: حدث التوسع
        """
        async with self._lock:
            current = await self._get_current_worker_count()
            target_count = max(self.config.min_workers, min(self.config.max_workers, target_count))

            if target_count == current:
                event = AutoScalingEvent(
                    event_type="info",
                    reason=f"Already at target count ({current})",
                )
                self._add_event(event)
                return event

            from distributed_cluster.autoscaling.policies import ScalingDecision, ScalingDirection

            if target_count > current:
                decision = ScalingDecision(
                    direction=ScalingDirection.UP,
                    count=target_count - current,
                    reason=f"Manual scale to {target_count}",
                    policy_name="manual",
                )
                metrics = await self.metrics_collector.collect_now()
                await self._scale_up(decision, metrics)
            else:
                decision = ScalingDecision(
                    direction=ScalingDirection.DOWN,
                    count=current - target_count,
                    reason=f"Manual scale to {target_count}",
                    policy_name="manual",
                )
                metrics = await self.metrics_collector.collect_now()
                await self._scale_down(decision, metrics)

            return self._events[-1] if self._events else AutoScalingEvent()

    async def scale_up_by(self, count: int) -> AutoScalingEvent:
        """
        التوسع بعدد معين
        Scale up by count
        """
        current = await self._get_current_worker_count()
        return await self.scale_to(current + count)

    async def scale_down_by(self, count: int) -> AutoScalingEvent:
        """
        التقليص بعدد معين
        Scale down by count
        """
        current = await self._get_current_worker_count()
        return await self.scale_to(current - count)

    # =========================================================================
    # Callbacks / الاستدعاءات
    # =========================================================================

    def on_scale_up(self, callback: Callable[[AutoScalingEvent], None]) -> None:
        """تسجيل callback عند التوسع / Register scale up callback"""
        self._on_scale_up.append(callback)

    def on_scale_down(self, callback: Callable[[AutoScalingEvent], None]) -> None:
        """تسجيل callback عند التقليص / Register scale down callback"""
        self._on_scale_down.append(callback)

    def on_error(self, callback: Callable[[AutoScalingEvent], None]) -> None:
        """تسجيل callback عند الخطأ / Register error callback"""
        self._on_error.append(callback)

    # =========================================================================
    # Status & Events / الحالة والأحداث
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """
        الحصول على حالة التوسع التلقائي
        Get auto-scaling status
        """
        return {
            "enabled": self.config.enabled,
            "paused": self._paused,
            "running": self._running,
            "state": self.state.to_dict(),
            "policy": self.policy.get_config(),
            "provider": self.provider.get_status(),
            "config": self.config.to_dict(),
            "in_cooldown": self._in_cooldown(),
        }

    def get_events(
        self,
        limit: int = 50,
        event_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        الحصول على سجل الأحداث
        Get event log
        """
        events = self._events

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return [e.to_dict() for e in events[-limit:]]

    def get_recent_scaling_events(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        الحصول على أحداث التوسع الأخيرة
        Get recent scaling events
        """
        return self.get_events(limit=limit, event_type="scaling")

    # =========================================================================
    # Configuration / الإعدادات
    # =========================================================================

    def update_config(self, **kwargs: Any) -> None:
        """
        تحديث الإعدادات
        Update configuration
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"Config updated: {key}={value}")
            else:
                logger.warning(f"Unknown config key: {key}")

    def set_policy(self, policy: ScalingPolicy) -> None:
        """
        تغيير السياسة
        Change policy
        """
        self.policy = policy
        logger.info(f"Policy changed to: {policy.name}")

    def set_limits(self, min_workers: int, max_workers: int) -> None:
        """
        تغيير حدود العمال
        Change worker limits
        """
        self.config.min_workers = max(0, min_workers)
        self.config.max_workers = max(min_workers, max_workers)
        self.policy.min_workers = self.config.min_workers
        self.policy.max_workers = self.config.max_workers
        logger.info(f"Limits updated: min={min_workers}, max={max_workers}")


# =============================================================================
# Factory Functions / دوال المصنع
# =============================================================================


def create_autoscaler(
    cluster_state: ClusterState,
    policy_type: str = "queue-based",
    provider_type: str = "local",
    **kwargs: Any,
) -> AutoScalingManager:
    """
    إنشاء مدير التوسع التلقائي بسهولة
    Create auto-scaling manager easily

    Args:
        cluster_state: حالة الكلاستر
        policy_type: نوع السياسة (queue-based, resource-based, composite, etc.)
        provider_type: نوع المزود (local, aws, gcp, azure)
        **kwargs: خيارات إضافية

    Returns:
        AutoScalingManager: مدير التوسع التلقائي
    """
    from distributed_cluster.autoscaling.metrics import MetricsCollector
    from distributed_cluster.autoscaling.policies import (
        PolicyTemplates,
        QueueBasedPolicy,
        ResourceBasedPolicy,
    )
    from distributed_cluster.autoscaling.providers import (
        AWSProvider,
        AzureProvider,
        GCPProvider,
        LocalProvider,
    )

    # إنشاء جامع المقاييس
    metrics = MetricsCollector(cluster_state)

    # إنشاء السياسة
    min_workers = kwargs.get("min_workers", 1)
    max_workers = kwargs.get("max_workers", 100)

    if policy_type == "queue-based":
        policy = QueueBasedPolicy(
            min_workers=min_workers,
            max_workers=max_workers,
            **{k: v for k, v in kwargs.items() if k.startswith("queue_") or k.startswith("scale_")}
        )
    elif policy_type == "resource-based":
        resource_kwargs = {
            k: v for k, v in kwargs.items()
            if k.startswith("cpu_") or k.startswith("memory_") or k.startswith("gpu_")
        }
        policy = ResourceBasedPolicy(
            min_workers=min_workers,
            max_workers=max_workers,
            **resource_kwargs
        )
    elif policy_type == "aggressive":
        policy = PolicyTemplates.aggressive()
    elif policy_type == "conservative":
        policy = PolicyTemplates.conservative()
    elif policy_type == "cost-optimized":
        policy = PolicyTemplates.cost_optimized(
            cost_per_worker=kwargs.get("cost_per_worker", 1.0),
            max_budget=kwargs.get("max_budget", 50.0),
        )
    else:
        policy = QueueBasedPolicy(min_workers=min_workers, max_workers=max_workers)

    # إنشاء المزود
    if provider_type == "aws":
        provider = AWSProvider(
            region=kwargs.get("aws_region", "us-east-1"),
            instance_type=kwargs.get("instance_type", "t3.large"),
        )
    elif provider_type == "gcp":
        provider = GCPProvider(
            project=kwargs.get("gcp_project", ""),
            zone=kwargs.get("gcp_zone", "us-central1-a"),
            machine_type=kwargs.get("machine_type", "n1-standard-4"),
        )
    elif provider_type == "azure":
        provider = AzureProvider(
            subscription_id=kwargs.get("azure_subscription", ""),
            resource_group=kwargs.get("azure_resource_group", ""),
            location=kwargs.get("azure_location", "eastus"),
            vm_size=kwargs.get("vm_size", "Standard_D4s_v3"),
        )
    else:
        provider = LocalProvider(cluster_state=cluster_state)

    # إنشاء الإعدادات
    config = AutoScalingConfig(
        min_workers=min_workers,
        max_workers=max_workers,
        evaluation_interval_seconds=kwargs.get("evaluation_interval", 30.0),
        cooldown_up_seconds=kwargs.get("cooldown_up", 60.0),
        cooldown_down_seconds=kwargs.get("cooldown_down", 300.0),
        worker_tags=kwargs.get("worker_tags", []),
        worker_labels=kwargs.get("worker_labels", {}),
    )

    return AutoScalingManager(
        metrics_collector=metrics,
        policy=policy,
        provider=provider,
        cluster_state=cluster_state,
        config=config,
    )
