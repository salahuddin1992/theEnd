# -*- coding: utf-8 -*-
"""
SLA Monitor for NebulaCompute.

Monitors service level agreements and tracks compliance
in real-time.

مراقب اتفاقيات مستوى الخدمة.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class SLAStatus(str, Enum):
    """SLA compliance status."""

    COMPLIANT = "compliant"
    AT_RISK = "at_risk"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


class SLAMetricType(str, Enum):
    """SLA metric type."""

    AVAILABILITY = "availability"  # Uptime percentage
    LATENCY = "latency"  # Response time
    THROUGHPUT = "throughput"  # Jobs per hour
    ERROR_RATE = "error_rate"  # Failure percentage
    QUEUE_TIME = "queue_time"  # Time in queue
    COMPLETION_TIME = "completion_time"  # Job duration
    RECOVERY_TIME = "recovery_time"  # Time to recover


class AggregationType(str, Enum):
    """Metric aggregation type."""

    AVERAGE = "average"
    PERCENTILE_50 = "p50"
    PERCENTILE_90 = "p90"
    PERCENTILE_95 = "p95"
    PERCENTILE_99 = "p99"
    MAX = "max"
    MIN = "min"
    SUM = "sum"


@dataclass
class SLAMetric:
    """
    SLA metric definition.

    تعريف مقياس SLA.
    """

    name: str
    metric_type: SLAMetricType
    target_value: float
    comparison: str  # "lt", "lte", "gt", "gte", "eq"
    unit: str
    aggregation: AggregationType = AggregationType.AVERAGE
    window_minutes: int = 60
    weight: float = 1.0  # Importance weight

    def evaluate(self, value: float) -> bool:
        """Evaluate if metric meets target."""
        if self.comparison == "lt":
            return value < self.target_value
        elif self.comparison == "lte":
            return value <= self.target_value
        elif self.comparison == "gt":
            return value > self.target_value
        elif self.comparison == "gte":
            return value >= self.target_value
        elif self.comparison == "eq":
            return value == self.target_value
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "metric_type": self.metric_type.value,
            "target_value": self.target_value,
            "comparison": self.comparison,
            "unit": self.unit,
            "aggregation": self.aggregation.value,
            "window_minutes": self.window_minutes,
            "weight": self.weight,
        }


@dataclass
class SLADefinition:
    """
    SLA definition.

    تعريف اتفاقية مستوى الخدمة.
    """

    sla_id: str
    name: str
    description: str
    metrics: List[SLAMetric]
    applies_to: str  # "all", "team:{id}", "user:{id}", "job_type:{type}"
    priority: int = 0  # Higher = more important
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    notification_channels: List[str] = field(default_factory=list)
    escalation_policy: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Check if SLA is currently active."""
        if not self.enabled:
            return False
        now = datetime.now(timezone.utc)
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sla_id": self.sla_id,
            "name": self.name,
            "description": self.description,
            "metrics": [m.to_dict() for m in self.metrics],
            "applies_to": self.applies_to,
            "priority": self.priority,
            "enabled": self.enabled,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "notification_channels": self.notification_channels,
            "escalation_policy": self.escalation_policy,
            "metadata": self.metadata,
        }


@dataclass
class SLAEvaluation:
    """
    SLA evaluation result.

    نتيجة تقييم SLA.
    """

    sla_id: str
    sla_name: str
    status: SLAStatus
    overall_score: float  # 0.0 to 1.0
    metric_results: Dict[str, Dict[str, Any]]
    evaluated_at: datetime = field(default_factory=datetime.utcnow)
    risk_level: float = 0.0  # 0.0 to 1.0
    time_to_violation: Optional[float] = None  # seconds

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sla_id": self.sla_id,
            "sla_name": self.sla_name,
            "status": self.status.value,
            "overall_score": self.overall_score,
            "metric_results": self.metric_results,
            "evaluated_at": self.evaluated_at.isoformat(),
            "risk_level": self.risk_level,
            "time_to_violation": self.time_to_violation,
        }


class SLAMonitor:
    """
    Monitors SLA compliance in real-time.

    مراقب امتثال SLA في الوقت الفعلي.

    Features:
    - Real-time SLA evaluation
    - Multi-metric SLA support
    - Risk prediction
    - Automatic alerting
    - Historical tracking
    """

    def __init__(
        self,
        evaluation_interval_seconds: float = 60.0,
        risk_threshold: float = 0.7,
        alert_callback: Optional[Callable] = None,
        metrics_provider: Optional[Callable] = None,
    ):
        """
        Initialize SLA Monitor.

        Args:
            evaluation_interval_seconds: How often to evaluate SLAs
            risk_threshold: Threshold for at-risk status (0.0-1.0)
            alert_callback: Called when SLA status changes
            metrics_provider: Function to get current metrics
        """
        self.evaluation_interval = evaluation_interval_seconds
        self.risk_threshold = risk_threshold
        self.alert_callback = alert_callback
        self.metrics_provider = metrics_provider

        # State
        self._slas: Dict[str, SLADefinition] = {}
        self._evaluations: Dict[str, SLAEvaluation] = {}
        self._evaluation_history: Dict[str, List[SLAEvaluation]] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Metrics cache
        self._metrics_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_max_age = timedelta(hours=2)

        # Statistics
        self._stats = {
            "total_evaluations": 0,
            "violations_detected": 0,
            "at_risk_detected": 0,
            "alerts_sent": 0,
        }

    async def start(self) -> None:
        """Start SLA monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("SLA Monitor started")

    async def stop(self) -> None:
        """Stop SLA monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("SLA Monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._evaluate_all_slas()
                await asyncio.sleep(self.evaluation_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SLA monitoring error: {e}")
                await asyncio.sleep(self.evaluation_interval)

    async def _evaluate_all_slas(self) -> None:
        """Evaluate all active SLAs."""
        for sla in self._slas.values():
            if sla.is_active:
                evaluation = await self.evaluate_sla(sla.sla_id)
                if evaluation:
                    await self._handle_evaluation(sla, evaluation)

    async def register_sla(self, sla: SLADefinition) -> None:
        """
        Register an SLA definition.

        تسجيل تعريف SLA.
        """
        async with self._lock:
            self._slas[sla.sla_id] = sla
            self._evaluation_history[sla.sla_id] = []

        logger.info(f"Registered SLA: {sla.name} ({sla.sla_id})")

    async def unregister_sla(self, sla_id: str) -> bool:
        """Unregister an SLA."""
        async with self._lock:
            if sla_id in self._slas:
                del self._slas[sla_id]
                return True
        return False

    async def evaluate_sla(self, sla_id: str) -> Optional[SLAEvaluation]:
        """
        Evaluate a specific SLA.

        تقييم SLA محدد.
        """
        sla = self._slas.get(sla_id)
        if not sla:
            return None

        self._stats["total_evaluations"] += 1

        # Get current metrics
        current_metrics = await self._get_metrics(sla)

        # Evaluate each metric
        metric_results = {}
        total_score = 0.0
        total_weight = 0.0

        for metric in sla.metrics:
            value = current_metrics.get(metric.name, 0.0)
            passed = metric.evaluate(value)

            # Calculate score (0.0 to 1.0)
            if passed:
                score = 1.0
            else:
                # Calculate how far off we are
                if metric.target_value != 0:
                    deviation = abs(value - metric.target_value) / metric.target_value
                    score = max(0.0, 1.0 - deviation)
                else:
                    score = 0.0

            metric_results[metric.name] = {
                "current_value": value,
                "target_value": metric.target_value,
                "passed": passed,
                "score": score,
                "unit": metric.unit,
            }

            total_score += score * metric.weight
            total_weight += metric.weight

        # Calculate overall score
        overall_score = total_score / total_weight if total_weight > 0 else 0.0

        # Determine status
        if overall_score >= 1.0:
            status = SLAStatus.COMPLIANT
        elif overall_score >= self.risk_threshold:
            status = SLAStatus.AT_RISK
            self._stats["at_risk_detected"] += 1
        else:
            status = SLAStatus.VIOLATED
            self._stats["violations_detected"] += 1

        # Calculate risk level
        risk_level = 1.0 - overall_score

        # Estimate time to violation (simplified)
        time_to_violation = None
        if status == SLAStatus.AT_RISK:
            # Rough estimate based on trend
            time_to_violation = (overall_score - self.risk_threshold) * 3600

        evaluation = SLAEvaluation(
            sla_id=sla_id,
            sla_name=sla.name,
            status=status,
            overall_score=overall_score,
            metric_results=metric_results,
            risk_level=risk_level,
            time_to_violation=time_to_violation,
        )

        # Store evaluation
        async with self._lock:
            self._evaluations[sla_id] = evaluation
            self._evaluation_history[sla_id].append(evaluation)

            # Keep only last 1000 evaluations per SLA
            if len(self._evaluation_history[sla_id]) > 1000:
                self._evaluation_history[sla_id] = self._evaluation_history[sla_id][-1000:]

        return evaluation

    async def _get_metrics(self, sla: SLADefinition) -> Dict[str, float]:
        """Get current metrics for SLA evaluation."""
        if self.metrics_provider:
            try:
                metrics = await self.metrics_provider(sla)
                return metrics
            except Exception as e:
                logger.error(f"Error getting metrics: {e}")

        # Return simulated metrics for testing
        return await self._get_simulated_metrics(sla)

    async def _get_simulated_metrics(self, sla: SLADefinition) -> Dict[str, float]:
        """Get simulated metrics for testing."""
        import random

        metrics = {}
        for metric in sla.metrics:
            # Simulate values around target with some variance
            variance = metric.target_value * 0.2
            value = metric.target_value + random.uniform(-variance, variance)
            metrics[metric.name] = max(0, value)

        return metrics

    async def _handle_evaluation(
        self,
        sla: SLADefinition,
        evaluation: SLAEvaluation,
    ) -> None:
        """Handle evaluation result."""
        # Check for status change
        previous = self._evaluations.get(sla.sla_id)

        if previous and previous.status != evaluation.status:
            logger.info(f"SLA {sla.name} status changed: " f"{previous.status.value} -> {evaluation.status.value}")

            # Send alert
            if self.alert_callback:
                try:
                    await self._safe_callback(
                        self.alert_callback,
                        sla,
                        evaluation,
                        previous.status,
                    )
                    self._stats["alerts_sent"] += 1
                except Exception as e:
                    logger.error(f"Alert callback error: {e}")

    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute callback."""
        result = callback(*args)
        if asyncio.iscoroutine(result):
            await result

    async def get_sla(self, sla_id: str) -> Optional[SLADefinition]:
        """Get SLA by ID."""
        return self._slas.get(sla_id)

    async def list_slas(
        self,
        active_only: bool = False,
    ) -> List[SLADefinition]:
        """List all SLAs."""
        slas = list(self._slas.values())
        if active_only:
            slas = [s for s in slas if s.is_active]
        return slas

    async def get_current_status(self, sla_id: str) -> Optional[SLAEvaluation]:
        """Get current SLA status."""
        return self._evaluations.get(sla_id)

    async def get_all_statuses(self) -> Dict[str, SLAEvaluation]:
        """Get all current SLA statuses."""
        return dict(self._evaluations)

    async def get_evaluation_history(
        self,
        sla_id: str,
        hours: int = 24,
    ) -> List[SLAEvaluation]:
        """Get evaluation history for an SLA."""
        history = self._evaluation_history.get(sla_id, [])
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [e for e in history if e.evaluated_at > cutoff]

    async def get_compliance_summary(self) -> Dict[str, Any]:
        """
        Get overall compliance summary.

        ملخص الامتثال العام.
        """
        total = len(self._slas)
        compliant = 0
        at_risk = 0
        violated = 0

        for sla_id, evaluation in self._evaluations.items():
            if evaluation.status == SLAStatus.COMPLIANT:
                compliant += 1
            elif evaluation.status == SLAStatus.AT_RISK:
                at_risk += 1
            elif evaluation.status == SLAStatus.VIOLATED:
                violated += 1

        compliance_rate = (compliant / total * 100) if total > 0 else 100.0

        return {
            "total_slas": total,
            "compliant": compliant,
            "at_risk": at_risk,
            "violated": violated,
            "compliance_rate": compliance_rate,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def record_metric(
        self,
        metric_name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a metric value.

        تسجيل قيمة مقياس.
        """
        async with self._lock:
            if metric_name not in self._metrics_cache:
                self._metrics_cache[metric_name] = []

            self._metrics_cache[metric_name].append(
                {
                    "value": value,
                    "labels": labels or {},
                    "timestamp": datetime.now(timezone.utc),
                }
            )

            # Cleanup old entries
            cutoff = datetime.now(timezone.utc) - self._cache_max_age
            self._metrics_cache[metric_name] = [m for m in self._metrics_cache[metric_name] if m["timestamp"] > cutoff]

    async def get_statistics(self) -> Dict[str, Any]:
        """Get monitor statistics."""
        return {
            **self._stats,
            "registered_slas": len(self._slas),
            "active_slas": len([s for s in self._slas.values() if s.is_active]),
            "running": self._running,
            "evaluation_interval": self.evaluation_interval,
            "risk_threshold": self.risk_threshold,
        }

    async def shutdown(self) -> None:
        """Shutdown SLA monitor."""
        await self.stop()
        logger.info("SLA Monitor shutdown complete")
