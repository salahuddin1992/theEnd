"""
Scaling Policies - سياسات التوسع التلقائي
==========================================

Auto-Scaling Policies
---------------------

This module provides various scaling policies that determine when and
how to scale the worker pool. Policies can be combined for complex behavior.

توفر هذه الوحدة سياسات متنوعة للتوسع:
- QueueBasedPolicy: بناءً على عمق الطابور
- ResourceBasedPolicy: بناءً على استخدام الموارد
- CompositePolicy: دمج سياسات متعددة
- CostAwarePolicy: مراعاة التكلفة
- PredictivePolicy: تنبؤية باستخدام الاتجاهات
- ScheduleBasedPolicy: بناءً على جدول زمني

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from datetime import time as dtime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from distributed_cluster.autoscaling.metrics import MetricsCollector, ResourceMetrics

logger = logging.getLogger(__name__)


class ScalingDirection(str, Enum):
    """
    اتجاه التوسع
    Scaling direction
    """

    UP = "up"  # توسع / Scale up
    DOWN = "down"  # تقليص / Scale down
    NONE = "none"  # لا تغيير / No change


@dataclass
class ScalingDecision:
    """
    قرار التوسع
    Scaling decision

    يحتوي على معلومات حول قرار التوسع المتخذ.
    Contains information about the scaling decision made.
    """

    direction: ScalingDirection
    count: int  # عدد العمال للإضافة/الإزالة
    reason: str  # سبب القرار
    confidence: float = 1.0  # مستوى الثقة (0-1)
    policy_name: str = ""  # اسم السياسة التي اتخذت القرار
    metrics_snapshot: Optional[dict[str, Any]] = None  # لقطة المقاييس
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: int = 0  # أولوية القرار (أعلى = أهم)
    target_worker_count: Optional[int] = None  # العدد المستهدف

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس / Convert to dictionary"""
        return {
            "direction": self.direction.value,
            "count": self.count,
            "reason": self.reason,
            "confidence": self.confidence,
            "policy_name": self.policy_name,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority,
            "target_worker_count": self.target_worker_count,
        }


@dataclass
class PolicyConfig:
    """
    إعدادات السياسة الأساسية
    Base policy configuration
    """

    name: str = "default"
    min_workers: int = 1  # الحد الأدنى للعمال
    max_workers: int = 100  # الحد الأقصى للعمال
    enabled: bool = True  # هل السياسة مفعلة


class ScalingPolicy(ABC):
    """
    السياسة الأساسية للتوسع
    Base scaling policy

    جميع السياسات ترث من هذه الفئة وتنفذ evaluate().
    All policies inherit from this class and implement evaluate().
    """

    def __init__(
        self,
        name: str = "base",
        min_workers: int = 1,
        max_workers: int = 100,
        enabled: bool = True,
    ):
        self.name = name
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.enabled = enabled

    @abstractmethod
    async def evaluate(
        self,
        metrics: ResourceMetrics,
        current_workers: int,
        metrics_collector: Optional[MetricsCollector] = None,
    ) -> ScalingDecision:
        """
        تقييم المقاييس واتخاذ قرار التوسع
        Evaluate metrics and make scaling decision

        Args:
            metrics: المقاييس الحالية / Current metrics
            current_workers: عدد العمال الحاليين / Current worker count
            metrics_collector: جامع المقاييس للوصول للتاريخ / Metrics collector for history

        Returns:
            ScalingDecision: قرار التوسع / Scaling decision
        """
        pass

    def _clamp_worker_count(self, target: int) -> int:
        """تقييد عدد العمال ضمن الحدود / Clamp worker count within limits"""
        return max(self.min_workers, min(self.max_workers, target))

    def _no_scaling(self, reason: str = "No scaling needed") -> ScalingDecision:
        """إنشاء قرار عدم التوسع / Create no-scaling decision"""
        return ScalingDecision(
            direction=ScalingDirection.NONE,
            count=0,
            reason=reason,
            policy_name=self.name,
        )

    def get_config(self) -> dict[str, Any]:
        """الحصول على إعدادات السياسة / Get policy configuration"""
        return {
            "name": self.name,
            "type": self.__class__.__name__,
            "min_workers": self.min_workers,
            "max_workers": self.max_workers,
            "enabled": self.enabled,
        }


class QueueBasedPolicy(ScalingPolicy):
    """
    سياسة التوسع بناءً على الطابور
    Queue-based scaling policy

    تقوم بالتوسع بناءً على:
    - عمق الطابور (عدد المهام المنتظرة)
    - وقت الانتظار
    - معدل نمو الطابور

    Scales based on:
    - Queue depth (pending jobs count)
    - Wait time
    - Queue growth rate
    """

    def __init__(
        self,
        name: str = "queue-based",
        min_workers: int = 1,
        max_workers: int = 100,
        # Queue depth thresholds
        target_queue_depth: int = 10,  # العمق المستهدف
        scale_up_threshold: int = 20,  # عتبة التوسع
        scale_down_threshold: int = 5,  # عتبة التقليص
        # Wait time thresholds (seconds)
        max_wait_time_seconds: float = 60.0,  # أقصى وقت انتظار قبل التوسع
        # Scaling parameters
        jobs_per_worker: int = 10,  # المهام المتوقعة لكل عامل
        scale_up_increment: int = 1,  # الزيادة عند التوسع
        scale_down_increment: int = 1,  # النقصان عند التقليص
        # Sensitivity
        evaluation_periods: int = 3,  # عدد فترات التقييم
        enabled: bool = True,
    ):
        super().__init__(name, min_workers, max_workers, enabled)
        self.target_queue_depth = target_queue_depth
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.max_wait_time_seconds = max_wait_time_seconds
        self.jobs_per_worker = jobs_per_worker
        self.scale_up_increment = scale_up_increment
        self.scale_down_increment = scale_down_increment
        self.evaluation_periods = evaluation_periods

        # حفظ التاريخ للتقييم
        self._history: list[int] = []

    async def evaluate(
        self,
        metrics: ResourceMetrics,
        current_workers: int,
        metrics_collector: Optional[MetricsCollector] = None,
    ) -> ScalingDecision:
        """
        تقييم حالة الطابور واتخاذ قرار
        Evaluate queue state and make decision
        """
        if not self.enabled:
            return self._no_scaling("Policy disabled")

        queue_depth = metrics.queue_depth
        wait_time = metrics.queue_wait_time_avg

        # تحديث التاريخ
        self._history.append(queue_depth)
        if len(self._history) > self.evaluation_periods:
            self._history = self._history[-self.evaluation_periods:]

        # التحقق من وقت الانتظار أولاً (أولوية عالية)
        if wait_time > self.max_wait_time_seconds:
            # حساب العمال المطلوبين بناءً على وقت الانتظار
            required = math.ceil(queue_depth / max(self.jobs_per_worker, 1))
            target = self._clamp_worker_count(required)
            if target > current_workers:
                return ScalingDecision(
                    direction=ScalingDirection.UP,
                    count=target - current_workers,
                    reason=f"Wait time ({wait_time:.1f}s) exceeds max ({self.max_wait_time_seconds}s)",
                    confidence=0.9,
                    policy_name=self.name,
                    target_worker_count=target,
                    priority=2,
                )

        # التحقق من عمق الطابور للتوسع
        if len(self._history) >= self.evaluation_periods:
            if all(d >= self.scale_up_threshold for d in self._history):
                # حساب العمال المطلوبين
                required = math.ceil(queue_depth / max(self.jobs_per_worker, 1))
                target = self._clamp_worker_count(max(required, current_workers + self.scale_up_increment))

                if target > current_workers:
                    return ScalingDecision(
                        direction=ScalingDirection.UP,
                        count=min(target - current_workers, self.scale_up_increment * 2),
                        reason=(
                            f"Queue depth ({queue_depth}) >= threshold ({self.scale_up_threshold}) "
                            f"for {self.evaluation_periods} periods"
                        ),
                        confidence=0.8,
                        policy_name=self.name,
                        target_worker_count=target,
                        priority=1,
                    )

            # التحقق للتقليص
            if all(d <= self.scale_down_threshold for d in self._history):
                if current_workers > self.min_workers:
                    # حساب العمال المطلوبين
                    required = max(
                        math.ceil(queue_depth / max(self.jobs_per_worker, 1)),
                        self.min_workers
                    )
                    target = self._clamp_worker_count(required)

                    if target < current_workers:
                        return ScalingDecision(
                            direction=ScalingDirection.DOWN,
                            count=min(current_workers - target, self.scale_down_increment),
                            reason=(
                                f"Queue depth ({queue_depth}) <= threshold ({self.scale_down_threshold}) "
                                f"for {self.evaluation_periods} periods"
                            ),
                            confidence=0.7,
                            policy_name=self.name,
                            target_worker_count=target,
                            priority=0,
                        )

        return self._no_scaling(f"Queue depth ({queue_depth}) within normal range")

    def get_config(self) -> dict[str, Any]:
        """الحصول على إعدادات السياسة"""
        config = super().get_config()
        config.update({
            "target_queue_depth": self.target_queue_depth,
            "scale_up_threshold": self.scale_up_threshold,
            "scale_down_threshold": self.scale_down_threshold,
            "max_wait_time_seconds": self.max_wait_time_seconds,
            "jobs_per_worker": self.jobs_per_worker,
            "evaluation_periods": self.evaluation_periods,
        })
        return config


class ResourceBasedPolicy(ScalingPolicy):
    """
    سياسة التوسع بناءً على الموارد
    Resource-based scaling policy

    تقوم بالتوسع بناءً على:
    - استخدام CPU
    - استخدام RAM
    - استخدام GPU

    Scales based on:
    - CPU utilization
    - Memory utilization
    - GPU utilization
    """

    def __init__(
        self,
        name: str = "resource-based",
        min_workers: int = 1,
        max_workers: int = 100,
        # CPU thresholds
        cpu_scale_up_threshold: float = 80.0,  # نسبة CPU للتوسع
        cpu_scale_down_threshold: float = 30.0,  # نسبة CPU للتقليص
        # Memory thresholds
        memory_scale_up_threshold: float = 85.0,  # نسبة RAM للتوسع
        memory_scale_down_threshold: float = 40.0,  # نسبة RAM للتقليص
        # GPU thresholds
        gpu_scale_up_threshold: float = 80.0,  # نسبة GPU للتوسع
        gpu_scale_down_threshold: float = 20.0,  # نسبة GPU للتقليص
        gpu_enabled: bool = True,  # تفعيل مراقبة GPU
        # Scaling parameters
        scale_up_increment: int = 1,
        scale_down_increment: int = 1,
        # Sensitivity
        evaluation_periods: int = 3,
        enabled: bool = True,
    ):
        super().__init__(name, min_workers, max_workers, enabled)
        self.cpu_scale_up_threshold = cpu_scale_up_threshold
        self.cpu_scale_down_threshold = cpu_scale_down_threshold
        self.memory_scale_up_threshold = memory_scale_up_threshold
        self.memory_scale_down_threshold = memory_scale_down_threshold
        self.gpu_scale_up_threshold = gpu_scale_up_threshold
        self.gpu_scale_down_threshold = gpu_scale_down_threshold
        self.gpu_enabled = gpu_enabled
        self.scale_up_increment = scale_up_increment
        self.scale_down_increment = scale_down_increment
        self.evaluation_periods = evaluation_periods

        # تاريخ المقاييس
        self._cpu_history: list[float] = []
        self._memory_history: list[float] = []
        self._gpu_history: list[float] = []

    async def evaluate(
        self,
        metrics: ResourceMetrics,
        current_workers: int,
        metrics_collector: Optional[MetricsCollector] = None,
    ) -> ScalingDecision:
        """
        تقييم استخدام الموارد واتخاذ قرار
        Evaluate resource utilization and make decision
        """
        if not self.enabled:
            return self._no_scaling("Policy disabled")

        # تحديث التاريخ
        self._cpu_history.append(metrics.cpu_utilization_avg)
        self._memory_history.append(metrics.memory_utilization_avg)
        self._gpu_history.append(metrics.gpu_utilization_avg)

        # تقليم التاريخ
        max_history = self.evaluation_periods
        self._cpu_history = self._cpu_history[-max_history:]
        self._memory_history = self._memory_history[-max_history:]
        self._gpu_history = self._gpu_history[-max_history:]

        if len(self._cpu_history) < self.evaluation_periods:
            return self._no_scaling("Not enough history for evaluation")

        # فحص التوسع (أي مورد يتجاوز العتبة)
        cpu_high = all(c >= self.cpu_scale_up_threshold for c in self._cpu_history)
        memory_high = all(m >= self.memory_scale_up_threshold for m in self._memory_history)
        gpu_high = (
            self.gpu_enabled
            and metrics.gpu_count_total > 0
            and all(g >= self.gpu_scale_up_threshold for g in self._gpu_history)
        )

        if cpu_high or memory_high or gpu_high:
            reasons = []
            if cpu_high:
                reasons.append(f"CPU ({metrics.cpu_utilization_avg:.1f}%)")
            if memory_high:
                reasons.append(f"Memory ({metrics.memory_utilization_avg:.1f}%)")
            if gpu_high:
                reasons.append(f"GPU ({metrics.gpu_utilization_avg:.1f}%)")

            if current_workers < self.max_workers:
                return ScalingDecision(
                    direction=ScalingDirection.UP,
                    count=self.scale_up_increment,
                    reason=f"High utilization: {', '.join(reasons)}",
                    confidence=0.85,
                    policy_name=self.name,
                    priority=2 if memory_high else 1,
                )

        # فحص التقليص (جميع الموارد أقل من العتبة)
        cpu_low = all(c <= self.cpu_scale_down_threshold for c in self._cpu_history)
        memory_low = all(m <= self.memory_scale_down_threshold for m in self._memory_history)
        gpu_low = (
            not self.gpu_enabled
            or metrics.gpu_count_total == 0
            or all(g <= self.gpu_scale_down_threshold for g in self._gpu_history)
        )

        if cpu_low and memory_low and gpu_low:
            if current_workers > self.min_workers:
                return ScalingDecision(
                    direction=ScalingDirection.DOWN,
                    count=self.scale_down_increment,
                    reason=(
                        f"Low utilization: CPU={metrics.cpu_utilization_avg:.1f}%, "
                        f"Memory={metrics.memory_utilization_avg:.1f}%"
                    ),
                    confidence=0.7,
                    policy_name=self.name,
                    priority=0,
                )

        return self._no_scaling("Resource utilization within normal range")

    def get_config(self) -> dict[str, Any]:
        """الحصول على إعدادات السياسة"""
        config = super().get_config()
        config.update({
            "cpu_scale_up_threshold": self.cpu_scale_up_threshold,
            "cpu_scale_down_threshold": self.cpu_scale_down_threshold,
            "memory_scale_up_threshold": self.memory_scale_up_threshold,
            "memory_scale_down_threshold": self.memory_scale_down_threshold,
            "gpu_scale_up_threshold": self.gpu_scale_up_threshold,
            "gpu_scale_down_threshold": self.gpu_scale_down_threshold,
            "gpu_enabled": self.gpu_enabled,
            "evaluation_periods": self.evaluation_periods,
        })
        return config


class CompositePolicy(ScalingPolicy):
    """
    سياسة مركبة تجمع سياسات متعددة
    Composite policy combining multiple policies

    يمكن تحديد طريقة دمج القرارات:
    - ANY: أي سياسة توصي بالتوسع
    - ALL: جميع السياسات توصي بنفس الاتجاه
    - PRIORITY: السياسة ذات الأولوية الأعلى
    - WEIGHTED: بناءً على أوزان السياسات

    Can specify how to combine decisions:
    - ANY: Any policy recommending scale
    - ALL: All policies agree on direction
    - PRIORITY: Highest priority policy wins
    - WEIGHTED: Based on policy weights
    """

    class CombineMode(str, Enum):
        ANY = "any"  # أي سياسة
        ALL = "all"  # جميع السياسات
        PRIORITY = "priority"  # الأولوية
        WEIGHTED = "weighted"  # الوزن

    def __init__(
        self,
        name: str = "composite",
        policies: Optional[list[ScalingPolicy]] = None,
        combine_mode: CombineMode = CombineMode.PRIORITY,
        weights: Optional[dict[str, float]] = None,
        min_workers: int = 1,
        max_workers: int = 100,
        enabled: bool = True,
    ):
        super().__init__(name, min_workers, max_workers, enabled)
        self.policies = policies or []
        self.combine_mode = combine_mode
        self.weights = weights or {}

    def add_policy(self, policy: ScalingPolicy, weight: float = 1.0) -> None:
        """إضافة سياسة / Add policy"""
        self.policies.append(policy)
        self.weights[policy.name] = weight

    async def evaluate(
        self,
        metrics: ResourceMetrics,
        current_workers: int,
        metrics_collector: Optional[MetricsCollector] = None,
    ) -> ScalingDecision:
        """
        تقييم جميع السياسات ودمج القرارات
        Evaluate all policies and combine decisions
        """
        if not self.enabled or not self.policies:
            return self._no_scaling("Policy disabled or no sub-policies")

        # جمع قرارات جميع السياسات
        decisions: list[ScalingDecision] = []
        for policy in self.policies:
            if policy.enabled:
                try:
                    decision = await policy.evaluate(metrics, current_workers, metrics_collector)
                    decisions.append(decision)
                except Exception as e:
                    logger.error(f"Policy {policy.name} evaluation failed: {e}")

        if not decisions:
            return self._no_scaling("No valid decisions from sub-policies")

        # دمج القرارات حسب الوضع
        if self.combine_mode == self.CombineMode.ANY:
            return self._combine_any(decisions, current_workers)
        elif self.combine_mode == self.CombineMode.ALL:
            return self._combine_all(decisions, current_workers)
        elif self.combine_mode == self.CombineMode.PRIORITY:
            return self._combine_priority(decisions)
        elif self.combine_mode == self.CombineMode.WEIGHTED:
            return self._combine_weighted(decisions, current_workers)

        return self._no_scaling("Unknown combine mode")

    def _combine_any(
        self,
        decisions: list[ScalingDecision],
        current_workers: int,
    ) -> ScalingDecision:
        """دمج: أي سياسة توصي بالتوسع تفوز"""
        # التوسع له أولوية
        scale_up = [d for d in decisions if d.direction == ScalingDirection.UP]
        if scale_up:
            best = max(scale_up, key=lambda d: d.priority)
            return ScalingDecision(
                direction=ScalingDirection.UP,
                count=best.count,
                reason=f"[{best.policy_name}] {best.reason}",
                confidence=best.confidence,
                policy_name=self.name,
                priority=best.priority,
            )

        # ثم التقليص
        scale_down = [d for d in decisions if d.direction == ScalingDirection.DOWN]
        if scale_down:
            best = max(scale_down, key=lambda d: d.confidence)
            return ScalingDecision(
                direction=ScalingDirection.DOWN,
                count=best.count,
                reason=f"[{best.policy_name}] {best.reason}",
                confidence=best.confidence,
                policy_name=self.name,
                priority=best.priority,
            )

        return self._no_scaling("No scaling recommended by any policy")

    def _combine_all(
        self,
        decisions: list[ScalingDecision],
        current_workers: int,
    ) -> ScalingDecision:
        """دمج: جميع السياسات يجب أن توافق"""
        directions = [d.direction for d in decisions]

        # التوسع يتطلب موافقة الجميع
        if all(d == ScalingDirection.UP for d in directions):
            counts = [d.count for d in decisions if d.direction == ScalingDirection.UP]
            avg_count = int(sum(counts) / len(counts))
            return ScalingDecision(
                direction=ScalingDirection.UP,
                count=avg_count,
                reason="All policies agree on scale up",
                confidence=0.95,
                policy_name=self.name,
                priority=2,
            )

        # التقليص يتطلب موافقة الجميع
        if all(d == ScalingDirection.DOWN for d in directions):
            counts = [d.count for d in decisions if d.direction == ScalingDirection.DOWN]
            min_count = min(counts)
            return ScalingDecision(
                direction=ScalingDirection.DOWN,
                count=min_count,
                reason="All policies agree on scale down",
                confidence=0.9,
                policy_name=self.name,
                priority=0,
            )

        return self._no_scaling("Policies do not agree on scaling direction")

    def _combine_priority(self, decisions: list[ScalingDecision]) -> ScalingDecision:
        """دمج: السياسة ذات الأولوية الأعلى"""
        # فلترة القرارات الفعلية
        active = [d for d in decisions if d.direction != ScalingDirection.NONE]

        if not active:
            return self._no_scaling("No active scaling recommendations")

        # اختيار ذات الأولوية الأعلى
        best = max(active, key=lambda d: (d.priority, d.confidence))
        return ScalingDecision(
            direction=best.direction,
            count=best.count,
            reason=f"[{best.policy_name}] {best.reason}",
            confidence=best.confidence,
            policy_name=self.name,
            priority=best.priority,
        )

    def _combine_weighted(
        self,
        decisions: list[ScalingDecision],
        current_workers: int,
    ) -> ScalingDecision:
        """دمج: بناءً على الأوزان"""
        up_score = 0.0
        down_score = 0.0
        up_count = 0
        down_count = 0

        for d in decisions:
            weight = self.weights.get(d.policy_name, 1.0)
            if d.direction == ScalingDirection.UP:
                up_score += weight * d.confidence
                up_count += d.count * weight
            elif d.direction == ScalingDirection.DOWN:
                down_score += weight * d.confidence
                down_count += d.count * weight

        if up_score > down_score and up_score > 0.5:
            return ScalingDecision(
                direction=ScalingDirection.UP,
                count=max(1, int(up_count)),
                reason=f"Weighted score favors scale up ({up_score:.2f} vs {down_score:.2f})",
                confidence=up_score / (up_score + down_score + 0.001),
                policy_name=self.name,
                priority=1,
            )
        elif down_score > up_score and down_score > 0.5:
            return ScalingDecision(
                direction=ScalingDirection.DOWN,
                count=max(1, int(down_count)),
                reason=f"Weighted score favors scale down ({down_score:.2f} vs {up_score:.2f})",
                confidence=down_score / (up_score + down_score + 0.001),
                policy_name=self.name,
                priority=0,
            )

        return self._no_scaling("Weighted scores do not favor scaling")

    def get_config(self) -> dict[str, Any]:
        """الحصول على إعدادات السياسة"""
        config = super().get_config()
        config.update({
            "combine_mode": self.combine_mode.value,
            "policies": [p.get_config() for p in self.policies],
            "weights": self.weights,
        })
        return config


class CostAwarePolicy(ScalingPolicy):
    """
    سياسة التوسع مع مراعاة التكلفة
    Cost-aware scaling policy

    تأخذ في الاعتبار:
    - تكلفة العامل بالساعة
    - الميزانية القصوى
    - نسبة التكلفة/الأداء

    Considers:
    - Worker cost per hour
    - Maximum budget
    - Cost/performance ratio
    """

    def __init__(
        self,
        name: str = "cost-aware",
        min_workers: int = 1,
        max_workers: int = 100,
        cost_per_worker_hour: float = 1.0,  # تكلفة العامل بالساعة
        max_hourly_budget: float = 100.0,  # الميزانية القصوى بالساعة
        target_cost_per_job: float = 0.1,  # التكلفة المستهدفة لكل مهمة
        base_policy: Optional[ScalingPolicy] = None,  # السياسة الأساسية
        enabled: bool = True,
    ):
        super().__init__(name, min_workers, max_workers, enabled)
        self.cost_per_worker_hour = cost_per_worker_hour
        self.max_hourly_budget = max_hourly_budget
        self.target_cost_per_job = target_cost_per_job
        self.base_policy = base_policy

    async def evaluate(
        self,
        metrics: ResourceMetrics,
        current_workers: int,
        metrics_collector: Optional[MetricsCollector] = None,
    ) -> ScalingDecision:
        """
        تقييم مع مراعاة التكلفة
        Evaluate with cost awareness
        """
        if not self.enabled:
            return self._no_scaling("Policy disabled")

        # الحصول على القرار من السياسة الأساسية
        if self.base_policy:
            base_decision = await self.base_policy.evaluate(
                metrics, current_workers, metrics_collector
            )
        else:
            base_decision = self._no_scaling("No base policy")

        # حساب التكلفة الحالية
        current_hourly_cost = current_workers * self.cost_per_worker_hour

        # حساب التكلفة لكل مهمة
        jobs_per_hour = metrics.jobs_completed_last_minute * 60
        if jobs_per_hour > 0:
            cost_per_job = current_hourly_cost / jobs_per_hour
        else:
            cost_per_job = float('inf') if current_workers > 0 else 0

        # التحقق من الميزانية
        if base_decision.direction == ScalingDirection.UP:
            new_workers = current_workers + base_decision.count
            new_cost = new_workers * self.cost_per_worker_hour

            if new_cost > self.max_hourly_budget:
                # تقليل عدد العمال المطلوبين
                max_new_workers = int(self.max_hourly_budget / self.cost_per_worker_hour)
                if max_new_workers <= current_workers:
                    return self._no_scaling(
                        f"Budget limit reached (${current_hourly_cost:.2f}/hr of ${self.max_hourly_budget:.2f}/hr max)"
                    )
                else:
                    adjusted_count = max_new_workers - current_workers
                    return ScalingDecision(
                        direction=ScalingDirection.UP,
                        count=adjusted_count,
                        reason=(
                            f"Scale up limited by budget (${new_cost:.2f}/hr would exceed "
                            f"${self.max_hourly_budget:.2f}/hr)"
                        ),
                        confidence=base_decision.confidence * 0.8,
                        policy_name=self.name,
                        priority=base_decision.priority,
                    )

            return ScalingDecision(
                direction=ScalingDirection.UP,
                count=base_decision.count,
                reason=f"[Cost: ${new_cost:.2f}/hr] {base_decision.reason}",
                confidence=base_decision.confidence,
                policy_name=self.name,
                priority=base_decision.priority,
            )

        # التقليص المحسن للتكلفة
        if base_decision.direction == ScalingDirection.DOWN:
            return ScalingDecision(
                direction=ScalingDirection.DOWN,
                count=base_decision.count,
                reason=f"[Saving: ${base_decision.count * self.cost_per_worker_hour:.2f}/hr] {base_decision.reason}",
                confidence=base_decision.confidence,
                policy_name=self.name,
                priority=base_decision.priority,
            )

        # التقليص التلقائي للتكلفة العالية
        if cost_per_job > self.target_cost_per_job * 2 and current_workers > self.min_workers:
            return ScalingDecision(
                direction=ScalingDirection.DOWN,
                count=1,
                reason=f"High cost per job (${cost_per_job:.3f} vs target ${self.target_cost_per_job:.3f})",
                confidence=0.6,
                policy_name=self.name,
                priority=0,
            )

        return self._no_scaling(f"Cost within budget (${current_hourly_cost:.2f}/hr)")

    def get_config(self) -> dict[str, Any]:
        """الحصول على إعدادات السياسة"""
        config = super().get_config()
        config.update({
            "cost_per_worker_hour": self.cost_per_worker_hour,
            "max_hourly_budget": self.max_hourly_budget,
            "target_cost_per_job": self.target_cost_per_job,
            "base_policy": self.base_policy.get_config() if self.base_policy else None,
        })
        return config


class PredictivePolicy(ScalingPolicy):
    """
    سياسة التوسع التنبؤية
    Predictive scaling policy

    تستخدم اتجاهات المقاييس للتنبؤ بالحاجة للتوسع
    قبل حدوث المشكلة.

    Uses metric trends to predict scaling needs
    before issues occur.
    """

    def __init__(
        self,
        name: str = "predictive",
        min_workers: int = 1,
        max_workers: int = 100,
        # Prediction parameters
        prediction_window_seconds: float = 300.0,  # نافذة التنبؤ (5 دقائق)
        trend_threshold: float = 10.0,  # عتبة الاتجاه (%)
        # Thresholds
        queue_growth_threshold: float = 5.0,  # معدل نمو الطابور في الثانية
        # Scaling
        scale_up_increment: int = 2,  # توسع استباقي أكبر
        scale_down_increment: int = 1,
        enabled: bool = True,
    ):
        super().__init__(name, min_workers, max_workers, enabled)
        self.prediction_window_seconds = prediction_window_seconds
        self.trend_threshold = trend_threshold
        self.queue_growth_threshold = queue_growth_threshold
        self.scale_up_increment = scale_up_increment
        self.scale_down_increment = scale_down_increment

    async def evaluate(
        self,
        metrics: ResourceMetrics,
        current_workers: int,
        metrics_collector: Optional[MetricsCollector] = None,
    ) -> ScalingDecision:
        """
        تقييم باستخدام التنبؤ
        Evaluate using prediction
        """
        if not self.enabled:
            return self._no_scaling("Policy disabled")

        if not metrics_collector:
            return self._no_scaling("Metrics collector required for prediction")

        # حساب الاتجاهات
        from distributed_cluster.autoscaling.metrics import MetricType

        queue_trend = metrics_collector.get_trend(
            MetricType.QUEUE_DEPTH,
            self.prediction_window_seconds,
        )
        cpu_trend = metrics_collector.get_trend(
            MetricType.CPU_UTILIZATION,
            self.prediction_window_seconds,
        )
        memory_trend = metrics_collector.get_trend(
            MetricType.MEMORY_UTILIZATION,
            self.prediction_window_seconds,
        )

        # التحقق من نمو الطابور السريع
        if metrics.queue_growth_rate > self.queue_growth_threshold:
            return ScalingDecision(
                direction=ScalingDirection.UP,
                count=self.scale_up_increment,
                reason=f"Queue growing rapidly ({metrics.queue_growth_rate:.1f}/s)",
                confidence=0.85,
                policy_name=self.name,
                priority=2,
            )

        # التحقق من الاتجاهات الصاعدة
        if queue_trend > self.trend_threshold:
            return ScalingDecision(
                direction=ScalingDirection.UP,
                count=self.scale_up_increment,
                reason=f"Predicted queue growth (trend: +{queue_trend:.1f}%)",
                confidence=0.75,
                policy_name=self.name,
                priority=1,
            )

        if cpu_trend > self.trend_threshold or memory_trend > self.trend_threshold:
            resource_info = []
            if cpu_trend > self.trend_threshold:
                resource_info.append(f"CPU +{cpu_trend:.1f}%")
            if memory_trend > self.trend_threshold:
                resource_info.append(f"Memory +{memory_trend:.1f}%")

            if current_workers < self.max_workers:
                return ScalingDecision(
                    direction=ScalingDirection.UP,
                    count=1,
                    reason=f"Predicted resource pressure ({', '.join(resource_info)})",
                    confidence=0.7,
                    policy_name=self.name,
                    priority=1,
                )

        # التحقق من الاتجاهات الهابطة للتقليص
        if (
            queue_trend < -self.trend_threshold
            and cpu_trend < -self.trend_threshold
            and memory_trend < -self.trend_threshold
        ):
            if current_workers > self.min_workers:
                return ScalingDecision(
                    direction=ScalingDirection.DOWN,
                    count=self.scale_down_increment,
                    reason=f"Predicted reduced demand (queue: {queue_trend:.1f}%, CPU: {cpu_trend:.1f}%)",
                    confidence=0.65,
                    policy_name=self.name,
                    priority=0,
                )

        return self._no_scaling("No significant trends detected")

    def get_config(self) -> dict[str, Any]:
        """الحصول على إعدادات السياسة"""
        config = super().get_config()
        config.update({
            "prediction_window_seconds": self.prediction_window_seconds,
            "trend_threshold": self.trend_threshold,
            "queue_growth_threshold": self.queue_growth_threshold,
        })
        return config


class ScheduleBasedPolicy(ScalingPolicy):
    """
    سياسة التوسع بناءً على الجدول الزمني
    Schedule-based scaling policy

    تسمح بتحديد عدد العمال بناءً على:
    - أوقات اليوم
    - أيام الأسبوع
    - تواريخ محددة

    Allows specifying worker counts based on:
    - Time of day
    - Days of week
    - Specific dates
    """

    @dataclass
    class ScheduleEntry:
        """إدخال في الجدول / Schedule entry"""
        start_time: dtime  # وقت البدء
        end_time: dtime  # وقت الانتهاء
        target_workers: int  # العدد المستهدف
        days: list[int] = field(default_factory=lambda: list(range(7)))  # أيام الأسبوع (0=الاثنين)
        name: str = ""  # اسم الفترة

    def __init__(
        self,
        name: str = "schedule-based",
        min_workers: int = 1,
        max_workers: int = 100,
        schedules: Optional[list[ScheduleEntry]] = None,
        default_workers: int = 5,  # العدد الافتراضي
        transition_increment: int = 2,  # معدل التغيير
        enabled: bool = True,
    ):
        super().__init__(name, min_workers, max_workers, enabled)
        self.schedules = schedules or []
        self.default_workers = default_workers
        self.transition_increment = transition_increment

    def add_schedule(
        self,
        start_time: dtime,
        end_time: dtime,
        target_workers: int,
        days: Optional[list[int]] = None,
        name: str = "",
    ) -> None:
        """
        إضافة فترة للجدول
        Add schedule entry
        """
        entry = self.ScheduleEntry(
            start_time=start_time,
            end_time=end_time,
            target_workers=target_workers,
            days=days or list(range(7)),
            name=name,
        )
        self.schedules.append(entry)

    def _get_current_target(self) -> int:
        """الحصول على العدد المستهدف الحالي / Get current target"""
        now = datetime.now()
        current_time = now.time()
        current_day = now.weekday()

        for schedule in self.schedules:
            if current_day not in schedule.days:
                continue

            # التحقق من الوقت
            if schedule.start_time <= schedule.end_time:
                # نفس اليوم
                if schedule.start_time <= current_time <= schedule.end_time:
                    return schedule.target_workers
            else:
                # عبر منتصف الليل
                if current_time >= schedule.start_time or current_time <= schedule.end_time:
                    return schedule.target_workers

        return self.default_workers

    async def evaluate(
        self,
        metrics: ResourceMetrics,
        current_workers: int,
        metrics_collector: Optional[MetricsCollector] = None,
    ) -> ScalingDecision:
        """
        تقييم بناءً على الجدول
        Evaluate based on schedule
        """
        if not self.enabled:
            return self._no_scaling("Policy disabled")

        target = self._clamp_worker_count(self._get_current_target())

        if target > current_workers:
            count = min(target - current_workers, self.transition_increment)
            return ScalingDecision(
                direction=ScalingDirection.UP,
                count=count,
                reason=f"Scheduled target: {target} workers",
                confidence=1.0,
                policy_name=self.name,
                target_worker_count=target,
                priority=3,  # أولوية عالية للجدول
            )
        elif target < current_workers:
            count = min(current_workers - target, self.transition_increment)
            return ScalingDecision(
                direction=ScalingDirection.DOWN,
                count=count,
                reason=f"Scheduled target: {target} workers",
                confidence=1.0,
                policy_name=self.name,
                target_worker_count=target,
                priority=3,
            )

        return self._no_scaling(f"At scheduled target ({target} workers)")

    def get_config(self) -> dict[str, Any]:
        """الحصول على إعدادات السياسة"""
        config = super().get_config()
        config.update({
            "default_workers": self.default_workers,
            "transition_increment": self.transition_increment,
            "schedules": [
                {
                    "name": s.name,
                    "start_time": s.start_time.isoformat(),
                    "end_time": s.end_time.isoformat(),
                    "target_workers": s.target_workers,
                    "days": s.days,
                }
                for s in self.schedules
            ],
        })
        return config


# =============================================================================
# Pre-built Policies / سياسات جاهزة
# =============================================================================


class PolicyTemplates:
    """
    قوالب سياسات جاهزة للاستخدام
    Ready-to-use policy templates
    """

    @staticmethod
    def aggressive() -> CompositePolicy:
        """
        سياسة عدوانية للتوسع السريع
        Aggressive policy for fast scaling
        """
        return CompositePolicy(
            name="aggressive",
            policies=[
                QueueBasedPolicy(
                    name="queue-aggressive",
                    scale_up_threshold=10,
                    scale_down_threshold=2,
                    jobs_per_worker=5,
                    evaluation_periods=2,
                ),
                ResourceBasedPolicy(
                    name="resource-aggressive",
                    cpu_scale_up_threshold=70,
                    memory_scale_up_threshold=75,
                    evaluation_periods=2,
                ),
            ],
            combine_mode=CompositePolicy.CombineMode.ANY,
            min_workers=1,
            max_workers=100,
        )

    @staticmethod
    def conservative() -> CompositePolicy:
        """
        سياسة محافظة للتوسع البطيء
        Conservative policy for slow scaling
        """
        return CompositePolicy(
            name="conservative",
            policies=[
                QueueBasedPolicy(
                    name="queue-conservative",
                    scale_up_threshold=50,
                    scale_down_threshold=5,
                    jobs_per_worker=20,
                    evaluation_periods=5,
                ),
                ResourceBasedPolicy(
                    name="resource-conservative",
                    cpu_scale_up_threshold=90,
                    memory_scale_up_threshold=90,
                    evaluation_periods=5,
                ),
            ],
            combine_mode=CompositePolicy.CombineMode.ALL,
            min_workers=2,
            max_workers=50,
        )

    @staticmethod
    def cost_optimized(
        cost_per_worker: float = 1.0,
        max_budget: float = 50.0,
    ) -> CostAwarePolicy:
        """
        سياسة محسنة للتكلفة
        Cost-optimized policy
        """
        base = QueueBasedPolicy(
            name="queue-cost-base",
            scale_up_threshold=30,
            scale_down_threshold=10,
            jobs_per_worker=15,
        )
        return CostAwarePolicy(
            name="cost-optimized",
            base_policy=base,
            cost_per_worker_hour=cost_per_worker,
            max_hourly_budget=max_budget,
            target_cost_per_job=0.05,
            min_workers=1,
            max_workers=int(max_budget / cost_per_worker),
        )

    @staticmethod
    def gpu_focused() -> ResourceBasedPolicy:
        """
        سياسة مركزة على GPU
        GPU-focused policy
        """
        return ResourceBasedPolicy(
            name="gpu-focused",
            cpu_scale_up_threshold=90,
            cpu_scale_down_threshold=40,
            gpu_scale_up_threshold=70,
            gpu_scale_down_threshold=20,
            gpu_enabled=True,
            scale_up_increment=1,
            evaluation_periods=3,
            min_workers=0,
            max_workers=16,
        )

    @staticmethod
    def business_hours(
        peak_workers: int = 20,
        off_peak_workers: int = 5,
        weekend_workers: int = 2,
    ) -> ScheduleBasedPolicy:
        """
        سياسة ساعات العمل
        Business hours policy
        """
        policy = ScheduleBasedPolicy(
            name="business-hours",
            default_workers=off_peak_workers,
            min_workers=1,
            max_workers=peak_workers,
        )

        # ساعات الذروة (9 صباحاً - 6 مساءً) أيام العمل
        policy.add_schedule(
            start_time=dtime(9, 0),
            end_time=dtime(18, 0),
            target_workers=peak_workers,
            days=[0, 1, 2, 3, 4],  # الاثنين-الجمعة
            name="peak-hours",
        )

        # عطلة نهاية الأسبوع
        policy.add_schedule(
            start_time=dtime(0, 0),
            end_time=dtime(23, 59),
            target_workers=weekend_workers,
            days=[5, 6],  # السبت-الأحد
            name="weekend",
        )

        return policy
