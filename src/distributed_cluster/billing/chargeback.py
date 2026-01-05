# -*- coding: utf-8 -*-
"""
Chargeback Manager for NebulaCompute.

Manages internal billing, budgets, and cost allocation
for teams and projects.

نظام المحاسبة الداخلية.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .tracker import CostTracker, UsageMetrics

logger = logging.getLogger(__name__)


class BudgetPeriod(str, Enum):
    """Budget period."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class BudgetStatus(str, Enum):
    """Budget status."""

    UNDER_BUDGET = "under_budget"
    WARNING = "warning"
    EXCEEDED = "exceeded"


class AllocationMethod(str, Enum):
    """Cost allocation method."""

    DIRECT = "direct"  # Direct attribution
    PROPORTIONAL = "proportional"  # Based on usage proportion
    EQUAL = "equal"  # Equal split
    CUSTOM = "custom"  # Custom formula


@dataclass
class Budget:
    """
    Budget definition.

    تعريف الميزانية.
    """

    budget_id: str
    name: str
    entity_type: str  # user, team, project
    entity_id: str
    amount: float
    currency: str = "USD"
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    warning_threshold: float = 80.0  # Percentage
    current_spend: float = 0.0
    period_start: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def remaining(self) -> float:
        """Calculate remaining budget."""
        return max(0, self.amount - self.current_spend)

    @property
    def utilization_percent(self) -> float:
        """Calculate budget utilization percentage."""
        if self.amount == 0:
            return 0.0
        return (self.current_spend / self.amount) * 100

    @property
    def status(self) -> BudgetStatus:
        """Get budget status."""
        if self.utilization_percent >= 100:
            return BudgetStatus.EXCEEDED
        elif self.utilization_percent >= self.warning_threshold:
            return BudgetStatus.WARNING
        else:
            return BudgetStatus.UNDER_BUDGET

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "budget_id": self.budget_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "amount": self.amount,
            "currency": self.currency,
            "period": self.period.value,
            "warning_threshold": self.warning_threshold,
            "current_spend": self.current_spend,
            "remaining": self.remaining,
            "utilization_percent": self.utilization_percent,
            "status": self.status.value,
            "period_start": self.period_start.isoformat(),
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


@dataclass
class ChargebackPolicy:
    """
    Chargeback policy configuration.

    سياسة المحاسبة.
    """

    policy_id: str
    name: str
    allocation_method: AllocationMethod
    applies_to: str  # team, project, department
    overhead_percent: float = 0.0  # Administrative overhead
    discount_percent: float = 0.0  # Discount for prepaid/reserved
    markup_rules: Dict[str, float] = field(default_factory=dict)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def calculate_final_cost(self, base_cost: float) -> float:
        """Calculate final cost with overhead and discounts."""
        # Apply markup
        cost = base_cost

        # Add overhead
        cost *= 1 + (self.overhead_percent / 100)

        # Apply discount
        cost *= 1 - (self.discount_percent / 100)

        return cost

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "allocation_method": self.allocation_method.value,
            "applies_to": self.applies_to,
            "overhead_percent": self.overhead_percent,
            "discount_percent": self.discount_percent,
            "markup_rules": self.markup_rules,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


@dataclass
class ChargebackReport:
    """
    Chargeback report.

    تقرير المحاسبة.
    """

    report_id: str
    period_start: datetime
    period_end: datetime
    entity_type: str
    entity_id: str
    entity_name: str
    total_cost: float
    currency: str
    breakdown: Dict[str, float]  # category -> cost
    usage_metrics: UsageMetrics
    budget_info: Optional[Dict[str, Any]] = None
    policy_applied: Optional[str] = None
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "report_id": self.report_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "total_cost": self.total_cost,
            "currency": self.currency,
            "breakdown": self.breakdown,
            "usage_metrics": self.usage_metrics.to_dict(),
            "budget_info": self.budget_info,
            "policy_applied": self.policy_applied,
            "generated_at": self.generated_at.isoformat(),
            "metadata": self.metadata,
        }


class ChargebackManager:
    """
    Manages chargeback and internal billing.

    مدير المحاسبة الداخلية.

    Features:
    - Budget management
    - Cost allocation policies
    - Chargeback reports
    - Budget alerts
    - Cost forecasting
    """

    def __init__(
        self,
        cost_tracker: CostTracker,
        alert_callback: Optional[Callable] = None,
        auto_reset_budgets: bool = True,
    ):
        """
        Initialize Chargeback Manager.

        Args:
            cost_tracker: Cost tracker instance
            alert_callback: Called when budget thresholds crossed
            auto_reset_budgets: Auto-reset budgets at period boundaries
        """
        self.cost_tracker = cost_tracker
        self.alert_callback = alert_callback
        self.auto_reset = auto_reset_budgets

        # Storage
        self._budgets: Dict[str, Budget] = {}
        self._policies: Dict[str, ChargebackPolicy] = {}
        self._reports: Dict[str, ChargebackReport] = {}
        self._alerts_sent: Dict[str, datetime] = {}  # budget_id -> last_alert_time
        self._lock = asyncio.Lock()

        # Entity names (would be populated from external source)
        self._entity_names: Dict[str, str] = {}

    async def create_budget(
        self,
        name: str,
        entity_type: str,
        entity_id: str,
        amount: float,
        period: BudgetPeriod = BudgetPeriod.MONTHLY,
        warning_threshold: float = 80.0,
        currency: str = "USD",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Budget:
        """
        Create a budget.

        إنشاء ميزانية.
        """
        import uuid

        budget = Budget(
            budget_id=str(uuid.uuid4()),
            name=name,
            entity_type=entity_type,
            entity_id=entity_id,
            amount=amount,
            currency=currency,
            period=period,
            warning_threshold=warning_threshold,
            period_start=self._get_period_start(period),
            metadata=metadata or {},
        )

        async with self._lock:
            self._budgets[budget.budget_id] = budget

        logger.info(f"Created budget {budget.budget_id}: " f"{entity_type}/{entity_id} = ${amount}/{period.value}")

        return budget

    async def update_budget(
        self,
        budget_id: str,
        amount: Optional[float] = None,
        warning_threshold: Optional[float] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[Budget]:
        """Update a budget."""
        async with self._lock:
            budget = self._budgets.get(budget_id)
            if not budget:
                return None

            if amount is not None:
                budget.amount = amount
            if warning_threshold is not None:
                budget.warning_threshold = warning_threshold
            if enabled is not None:
                budget.enabled = enabled

            return budget

    async def delete_budget(self, budget_id: str) -> bool:
        """Delete a budget."""
        async with self._lock:
            if budget_id in self._budgets:
                del self._budgets[budget_id]
                return True
            return False

    async def get_budget(self, budget_id: str) -> Optional[Budget]:
        """Get a budget by ID."""
        return self._budgets.get(budget_id)

    async def get_entity_budget(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Optional[Budget]:
        """Get budget for an entity."""
        for budget in self._budgets.values():
            if budget.entity_type == entity_type and budget.entity_id == entity_id:
                return budget
        return None

    async def list_budgets(
        self,
        entity_type: Optional[str] = None,
        status: Optional[BudgetStatus] = None,
    ) -> List[Budget]:
        """List budgets with optional filtering."""
        budgets = list(self._budgets.values())

        if entity_type:
            budgets = [b for b in budgets if b.entity_type == entity_type]

        if status:
            budgets = [b for b in budgets if b.status == status]

        return budgets

    async def record_cost(
        self,
        entity_type: str,
        entity_id: str,
        cost: float,
    ) -> Optional[BudgetStatus]:
        """
        Record cost against a budget.

        تسجيل تكلفة.
        """
        budget = await self.get_entity_budget(entity_type, entity_id)
        if not budget or not budget.enabled:
            return None

        async with self._lock:
            old_status = budget.status
            budget.current_spend += cost
            new_status = budget.status

            # Check for status change
            if new_status != old_status:
                await self._handle_status_change(budget, old_status, new_status)

        return new_status

    async def _handle_status_change(
        self,
        budget: Budget,
        old_status: BudgetStatus,
        new_status: BudgetStatus,
    ) -> None:
        """Handle budget status change."""
        # Check if we should send alert
        should_alert = False

        if new_status == BudgetStatus.WARNING and old_status == BudgetStatus.UNDER_BUDGET:
            should_alert = True
        elif new_status == BudgetStatus.EXCEEDED:
            should_alert = True

        if should_alert and self.alert_callback:
            # Check if we recently sent an alert
            last_alert = self._alerts_sent.get(budget.budget_id)
            if last_alert is None or (datetime.now(timezone.utc) - last_alert).seconds > 3600:
                try:
                    await self._safe_callback(
                        self.alert_callback,
                        budget,
                        old_status,
                        new_status,
                    )
                    self._alerts_sent[budget.budget_id] = datetime.now(timezone.utc)
                except Exception as e:
                    logger.error(f"Budget alert callback error: {e}")

        logger.info(
            f"Budget {budget.name} status: {old_status.value} -> {new_status.value} "
            f"({budget.utilization_percent:.1f}%)"
        )

    async def create_policy(
        self,
        name: str,
        applies_to: str,
        allocation_method: AllocationMethod = AllocationMethod.DIRECT,
        overhead_percent: float = 0.0,
        discount_percent: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChargebackPolicy:
        """
        Create a chargeback policy.

        إنشاء سياسة محاسبة.
        """
        import uuid

        policy = ChargebackPolicy(
            policy_id=str(uuid.uuid4()),
            name=name,
            allocation_method=allocation_method,
            applies_to=applies_to,
            overhead_percent=overhead_percent,
            discount_percent=discount_percent,
            metadata=metadata or {},
        )

        async with self._lock:
            self._policies[policy.policy_id] = policy

        return policy

    async def get_policy(self, policy_id: str) -> Optional[ChargebackPolicy]:
        """Get a policy by ID."""
        return self._policies.get(policy_id)

    async def generate_report(
        self,
        entity_type: str,
        entity_id: str,
        period_start: datetime,
        period_end: datetime,
        policy_id: Optional[str] = None,
    ) -> ChargebackReport:
        """
        Generate a chargeback report.

        إنشاء تقرير محاسبة.
        """
        import uuid

        # Get costs from tracker
        if entity_type == "user":
            costs = await self.cost_tracker.get_user_costs(entity_id, period_start, period_end)
        elif entity_type == "team":
            costs = await self.cost_tracker.get_team_costs(entity_id, period_start, period_end)
        elif entity_type == "project":
            costs = await self.cost_tracker.get_project_costs(entity_id, period_start, period_end)
        else:
            costs = {"total_cost": 0.0, "by_category": {}, "currency": "USD"}

        # Get usage metrics
        metrics = await self.cost_tracker.get_usage_metrics(
            user_id=entity_id if entity_type == "user" else None,
            team_id=entity_id if entity_type == "team" else None,
            project_id=entity_id if entity_type == "project" else None,
            start_date=period_start,
            end_date=period_end,
        )

        # Apply policy if specified
        total_cost = costs.get("total_cost", 0.0)
        policy = None

        if policy_id:
            policy = self._policies.get(policy_id)
            if policy:
                total_cost = policy.calculate_final_cost(total_cost)

        # Get budget info
        budget = await self.get_entity_budget(entity_type, entity_id)
        budget_info = budget.to_dict() if budget else None

        # Get entity name
        entity_name = self._entity_names.get(f"{entity_type}:{entity_id}", entity_id)

        report = ChargebackReport(
            report_id=str(uuid.uuid4()),
            period_start=period_start,
            period_end=period_end,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            total_cost=total_cost,
            currency=costs.get("currency", "USD"),
            breakdown=costs.get("by_category", {}),
            usage_metrics=metrics,
            budget_info=budget_info,
            policy_applied=policy.name if policy else None,
        )

        async with self._lock:
            self._reports[report.report_id] = report

        logger.info(f"Generated chargeback report for {entity_type}/{entity_id}: " f"${total_cost:.2f}")

        return report

    async def get_report(self, report_id: str) -> Optional[ChargebackReport]:
        """Get a report by ID."""
        return self._reports.get(report_id)

    async def list_reports(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[ChargebackReport]:
        """List reports with optional filtering."""
        reports = list(self._reports.values())

        if entity_type:
            reports = [r for r in reports if r.entity_type == entity_type]

        if entity_id:
            reports = [r for r in reports if r.entity_id == entity_id]

        # Sort by generated_at descending
        reports.sort(key=lambda r: r.generated_at, reverse=True)

        return reports[:limit]

    async def forecast_cost(
        self,
        entity_type: str,
        entity_id: str,
        days_ahead: int = 30,
    ) -> Dict[str, Any]:
        """
        Forecast future costs based on historical data.

        توقع التكاليف المستقبلية.
        """
        # Get historical data
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)

        if entity_type == "user":
            costs = await self.cost_tracker.get_user_costs(entity_id, start_date, end_date)
        elif entity_type == "team":
            costs = await self.cost_tracker.get_team_costs(entity_id, start_date, end_date)
        else:
            costs = await self.cost_tracker.get_project_costs(entity_id, start_date, end_date)

        historical_cost = costs.get("total_cost", 0.0)
        daily_average = historical_cost / 30

        forecast_cost = daily_average * days_ahead

        # Get budget for comparison
        budget = await self.get_entity_budget(entity_type, entity_id)

        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "historical_daily_average": daily_average,
            "forecast_days": days_ahead,
            "forecast_cost": forecast_cost,
            "currency": costs.get("currency", "USD"),
            "budget_amount": budget.amount if budget else None,
            "will_exceed_budget": (budget and forecast_cost > budget.remaining if budget else None),
        }

    async def reset_period_budgets(self) -> int:
        """Reset budgets that have crossed period boundaries."""
        now = datetime.now(timezone.utc)
        reset_count = 0

        async with self._lock:
            for budget in self._budgets.values():
                period_end = self._get_period_end(budget.period, budget.period_start)

                if now >= period_end:
                    budget.current_spend = 0.0
                    budget.period_start = self._get_period_start(budget.period)
                    reset_count += 1

        if reset_count:
            logger.info(f"Reset {reset_count} budgets for new period")

        return reset_count

    def _get_period_start(self, period: BudgetPeriod) -> datetime:
        """Get start of current period."""
        now = datetime.now(timezone.utc)

        if period == BudgetPeriod.DAILY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == BudgetPeriod.WEEKLY:
            return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == BudgetPeriod.MONTHLY:
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == BudgetPeriod.QUARTERLY:
            quarter_month = ((now.month - 1) // 3) * 3 + 1
            return now.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:  # YEARLY
            return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    def _get_period_end(self, period: BudgetPeriod, start: datetime) -> datetime:
        """Get end of period."""
        if period == BudgetPeriod.DAILY:
            return start + timedelta(days=1)
        elif period == BudgetPeriod.WEEKLY:
            return start + timedelta(weeks=1)
        elif period == BudgetPeriod.MONTHLY:
            if start.month == 12:
                return start.replace(year=start.year + 1, month=1)
            return start.replace(month=start.month + 1)
        elif period == BudgetPeriod.QUARTERLY:
            return start.replace(month=start.month + 3)
        else:  # YEARLY
            return start.replace(year=start.year + 1)

    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Callback error: {e}")

    async def get_statistics(self) -> Dict[str, Any]:
        """Get chargeback statistics."""
        budgets = list(self._budgets.values())

        return {
            "total_budgets": len(budgets),
            "budgets_exceeded": len([b for b in budgets if b.status == BudgetStatus.EXCEEDED]),
            "budgets_warning": len([b for b in budgets if b.status == BudgetStatus.WARNING]),
            "total_policies": len(self._policies),
            "total_reports": len(self._reports),
            "total_budget_amount": sum(b.amount for b in budgets),
            "total_current_spend": sum(b.current_spend for b in budgets),
        }

    async def shutdown(self) -> None:
        """Shutdown chargeback manager."""
        logger.info("Chargeback Manager shutdown complete")
