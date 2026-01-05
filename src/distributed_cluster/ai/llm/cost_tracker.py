"""
LLM Cost Tracker - تتبع تكاليف الذكاء الاصطناعي
==============================================

تتبع وإدارة تكاليف استخدام مزودي LLM:
- Per-provider cost tracking
- Token usage analytics
- Budget enforcement
- Cost alerts
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CostCurrency(str, Enum):
    """عملات التكلفة."""

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


@dataclass
class ModelPricing:
    """تسعير نموذج محدد."""

    model_name: str
    provider: str
    input_cost_per_1k: float  # Cost per 1K input tokens
    output_cost_per_1k: float  # Cost per 1K output tokens
    currency: CostCurrency = CostCurrency.USD

    # Optional per-request cost (some APIs charge per call)
    per_request_cost: float = 0.0

    # Special pricing
    cached_input_cost_per_1k: Optional[float] = None  # Discounted cached input
    batch_discount: float = 1.0  # Multiplier for batch API (e.g., 0.5 for 50% off)

    def calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        is_batch: bool = False,
    ) -> float:
        """حساب تكلفة الاستخدام."""
        # Input cost (regular + cached)
        regular_input = input_tokens - cached_tokens
        input_cost = (regular_input / 1000) * self.input_cost_per_1k

        # Cached input (if supported)
        if cached_tokens > 0 and self.cached_input_cost_per_1k is not None:
            input_cost += (cached_tokens / 1000) * self.cached_input_cost_per_1k

        # Output cost
        output_cost = (output_tokens / 1000) * self.output_cost_per_1k

        # Total with batch discount
        total = input_cost + output_cost + self.per_request_cost

        if is_batch:
            total *= self.batch_discount

        return total


# ==================== Default Pricing Database ====================

# Prices as of December 2024 (update regularly)
DEFAULT_PRICING: Dict[str, ModelPricing] = {
    # Claude (Anthropic)
    "claude-3-5-sonnet-20241022": ModelPricing(
        model_name="claude-3-5-sonnet-20241022",
        provider="anthropic",
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
        cached_input_cost_per_1k=0.0003,
    ),
    "claude-3-5-haiku-20241022": ModelPricing(
        model_name="claude-3-5-haiku-20241022",
        provider="anthropic",
        input_cost_per_1k=0.001,
        output_cost_per_1k=0.005,
        cached_input_cost_per_1k=0.0001,
    ),
    "claude-3-opus-20240229": ModelPricing(
        model_name="claude-3-opus-20240229",
        provider="anthropic",
        input_cost_per_1k=0.015,
        output_cost_per_1k=0.075,
        cached_input_cost_per_1k=0.00188,
    ),
    "claude-3-sonnet-20240229": ModelPricing(
        model_name="claude-3-sonnet-20240229",
        provider="anthropic",
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
    ),
    "claude-3-haiku-20240307": ModelPricing(
        model_name="claude-3-haiku-20240307",
        provider="anthropic",
        input_cost_per_1k=0.00025,
        output_cost_per_1k=0.00125,
        cached_input_cost_per_1k=0.00003,
    ),
    # OpenAI
    "gpt-4o": ModelPricing(
        model_name="gpt-4o",
        provider="openai",
        input_cost_per_1k=0.0025,
        output_cost_per_1k=0.01,
        cached_input_cost_per_1k=0.00125,
    ),
    "gpt-4o-mini": ModelPricing(
        model_name="gpt-4o-mini",
        provider="openai",
        input_cost_per_1k=0.00015,
        output_cost_per_1k=0.0006,
        cached_input_cost_per_1k=0.000075,
    ),
    "gpt-4-turbo": ModelPricing(
        model_name="gpt-4-turbo",
        provider="openai",
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.03,
    ),
    "gpt-3.5-turbo": ModelPricing(
        model_name="gpt-3.5-turbo",
        provider="openai",
        input_cost_per_1k=0.0005,
        output_cost_per_1k=0.0015,
    ),
    "o1": ModelPricing(
        model_name="o1",
        provider="openai",
        input_cost_per_1k=0.015,
        output_cost_per_1k=0.06,
        cached_input_cost_per_1k=0.0075,
    ),
    "o1-mini": ModelPricing(
        model_name="o1-mini",
        provider="openai",
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.012,
        cached_input_cost_per_1k=0.0015,
    ),
    # Gemini (Google)
    "gemini-1.5-pro": ModelPricing(
        model_name="gemini-1.5-pro",
        provider="google",
        input_cost_per_1k=0.00125,  # < 128K context
        output_cost_per_1k=0.005,
    ),
    "gemini-1.5-flash": ModelPricing(
        model_name="gemini-1.5-flash",
        provider="google",
        input_cost_per_1k=0.000075,
        output_cost_per_1k=0.0003,
    ),
    "gemini-2.0-flash": ModelPricing(
        model_name="gemini-2.0-flash",
        provider="google",
        input_cost_per_1k=0.0,  # Free tier
        output_cost_per_1k=0.0,
    ),
    # Groq
    "llama-3.3-70b-versatile": ModelPricing(
        model_name="llama-3.3-70b-versatile",
        provider="groq",
        input_cost_per_1k=0.00059,
        output_cost_per_1k=0.00079,
    ),
    "llama-3.1-8b-instant": ModelPricing(
        model_name="llama-3.1-8b-instant",
        provider="groq",
        input_cost_per_1k=0.00005,
        output_cost_per_1k=0.00008,
    ),
    "mixtral-8x7b-32768": ModelPricing(
        model_name="mixtral-8x7b-32768",
        provider="groq",
        input_cost_per_1k=0.00024,
        output_cost_per_1k=0.00024,
    ),
    # Mistral
    "mistral-large-latest": ModelPricing(
        model_name="mistral-large-latest",
        provider="mistral",
        input_cost_per_1k=0.002,
        output_cost_per_1k=0.006,
    ),
    "mistral-small-latest": ModelPricing(
        model_name="mistral-small-latest",
        provider="mistral",
        input_cost_per_1k=0.0002,
        output_cost_per_1k=0.0006,
    ),
    # DeepSeek
    "deepseek-chat": ModelPricing(
        model_name="deepseek-chat",
        provider="deepseek",
        input_cost_per_1k=0.00014,  # Cache miss
        output_cost_per_1k=0.00028,
        cached_input_cost_per_1k=0.000014,  # Cache hit
    ),
    "deepseek-reasoner": ModelPricing(
        model_name="deepseek-reasoner",
        provider="deepseek",
        input_cost_per_1k=0.00055,
        output_cost_per_1k=0.00219,
        cached_input_cost_per_1k=0.000055,
    ),
    # Cohere
    "command-r-plus": ModelPricing(
        model_name="command-r-plus",
        provider="cohere",
        input_cost_per_1k=0.0025,
        output_cost_per_1k=0.01,
    ),
    "command-r": ModelPricing(
        model_name="command-r",
        provider="cohere",
        input_cost_per_1k=0.00015,
        output_cost_per_1k=0.0006,
    ),
    # Ollama (local - free)
    "llama3": ModelPricing(
        model_name="llama3",
        provider="ollama",
        input_cost_per_1k=0.0,
        output_cost_per_1k=0.0,
    ),
    "mistral": ModelPricing(
        model_name="mistral",
        provider="ollama",
        input_cost_per_1k=0.0,
        output_cost_per_1k=0.0,
    ),
    "codellama": ModelPricing(
        model_name="codellama",
        provider="ollama",
        input_cost_per_1k=0.0,
        output_cost_per_1k=0.0,
    ),
}


@dataclass
class UsageRecord:
    """سجل استخدام واحد."""

    timestamp: datetime
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost: float
    currency: CostCurrency
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "cost": self.cost,
            "currency": self.currency.value,
            "request_id": self.request_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UsageRecord":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            provider=data["provider"],
            model=data["model"],
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            cached_tokens=data.get("cached_tokens", 0),
            cost=data["cost"],
            currency=CostCurrency(data["currency"]),
            request_id=data.get("request_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class BudgetConfig:
    """إعدادات الميزانية."""

    # Budget limits
    daily_limit: Optional[float] = None
    weekly_limit: Optional[float] = None
    monthly_limit: Optional[float] = None
    total_limit: Optional[float] = None

    # Per-provider limits
    provider_limits: Dict[str, float] = field(default_factory=dict)

    # Alert thresholds (percentage of limit)
    alert_threshold: float = 0.8  # 80%
    critical_threshold: float = 0.95  # 95%

    # Actions
    block_on_limit: bool = False  # Block requests when limit reached
    alert_callback: Optional[Callable[[str, float, float], None]] = None


@dataclass
class CostSummary:
    """ملخص التكاليف."""

    total_cost: float
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    request_count: int
    currency: CostCurrency = CostCurrency.USD

    # Breakdown by provider
    by_provider: Dict[str, float] = field(default_factory=dict)

    # Breakdown by model
    by_model: Dict[str, float] = field(default_factory=dict)

    # Time range
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # Cost savings from cache
    estimated_savings: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cost": round(self.total_cost, 6),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "request_count": self.request_count,
            "currency": self.currency.value,
            "by_provider": {k: round(v, 6) for k, v in self.by_provider.items()},
            "by_model": {k: round(v, 6) for k, v in self.by_model.items()},
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "estimated_savings": round(self.estimated_savings, 6),
        }


class CostTracker:
    """
    مدير تتبع التكاليف.

    الاستخدام:
        tracker = CostTracker()

        # Record usage
        tracker.record_usage(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500,
        )

        # Get summary
        summary = tracker.get_summary()
        print(f"Total cost: ${summary.total_cost:.4f}")
    """

    def __init__(
        self,
        budget: Optional[BudgetConfig] = None,
        pricing: Optional[Dict[str, ModelPricing]] = None,
        persist_path: Optional[str] = None,
    ):
        self.budget = budget or BudgetConfig()
        self.pricing = pricing or DEFAULT_PRICING.copy()
        self.persist_path = persist_path
        self._records: List[UsageRecord] = []
        self._lock = asyncio.Lock()

        # Load persisted data if exists
        if persist_path:
            self._load_records()

    def _load_records(self) -> None:
        """تحميل السجلات المحفوظة."""
        if not self.persist_path:
            return

        path = Path(self.persist_path)
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    self._records = [UsageRecord.from_dict(r) for r in data]
                logger.info(f"Loaded {len(self._records)} cost records")
            except Exception as e:
                logger.error(f"Failed to load cost records: {e}")

    def _save_records(self) -> None:
        """حفظ السجلات."""
        if not self.persist_path:
            return

        try:
            path = Path(self.persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump([r.to_dict() for r in self._records], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cost records: {e}")

    def add_pricing(self, pricing: ModelPricing) -> None:
        """إضافة أو تحديث تسعير نموذج."""
        self.pricing[pricing.model_name] = pricing

    def get_pricing(self, model: str) -> Optional[ModelPricing]:
        """الحصول على تسعير نموذج."""
        # Try exact match first
        if model in self.pricing:
            return self.pricing[model]

        # Try partial match
        for name, pricing in self.pricing.items():
            if model.startswith(name) or name.startswith(model):
                return pricing

        return None

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        is_batch: bool = False,
    ) -> float:
        """حساب تكلفة استخدام."""
        pricing = self.get_pricing(model)
        if not pricing:
            logger.warning(f"No pricing found for model: {model}")
            return 0.0

        return pricing.calculate_cost(input_tokens, output_tokens, cached_tokens, is_batch)

    async def record_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        is_batch: bool = False,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageRecord:
        """تسجيل استخدام جديد."""
        async with self._lock:
            cost = self.calculate_cost(model, input_tokens, output_tokens, cached_tokens, is_batch)

            pricing = self.get_pricing(model)
            currency = pricing.currency if pricing else CostCurrency.USD

            record = UsageRecord(
                timestamp=datetime.now(timezone.utc),
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                cost=cost,
                currency=currency,
                request_id=request_id,
                metadata=metadata or {},
            )

            self._records.append(record)

            # Check budget alerts
            await self._check_budget_alerts()

            # Save periodically (every 100 records)
            if len(self._records) % 100 == 0:
                self._save_records()

            return record

    async def _check_budget_alerts(self) -> None:
        """فحص تنبيهات الميزانية."""
        if not self.budget.alert_callback:
            return

        now = datetime.now(timezone.utc)

        # Check daily limit
        if self.budget.daily_limit:
            daily = self._get_cost_since(now - timedelta(days=1))
            ratio = daily / self.budget.daily_limit
            if ratio >= self.budget.critical_threshold:
                self.budget.alert_callback("daily_critical", daily, self.budget.daily_limit)
            elif ratio >= self.budget.alert_threshold:
                self.budget.alert_callback("daily_warning", daily, self.budget.daily_limit)

        # Check weekly limit
        if self.budget.weekly_limit:
            weekly = self._get_cost_since(now - timedelta(weeks=1))
            ratio = weekly / self.budget.weekly_limit
            if ratio >= self.budget.critical_threshold:
                self.budget.alert_callback("weekly_critical", weekly, self.budget.weekly_limit)
            elif ratio >= self.budget.alert_threshold:
                self.budget.alert_callback("weekly_warning", weekly, self.budget.weekly_limit)

        # Check monthly limit
        if self.budget.monthly_limit:
            monthly = self._get_cost_since(now - timedelta(days=30))
            ratio = monthly / self.budget.monthly_limit
            if ratio >= self.budget.critical_threshold:
                self.budget.alert_callback("monthly_critical", monthly, self.budget.monthly_limit)
            elif ratio >= self.budget.alert_threshold:
                self.budget.alert_callback("monthly_warning", monthly, self.budget.monthly_limit)

    def _get_cost_since(self, since: datetime) -> float:
        """حساب التكلفة منذ تاريخ معين."""
        return sum(r.cost for r in self._records if r.timestamp >= since)

    def is_budget_exceeded(self, provider: Optional[str] = None) -> bool:
        """فحص إذا تم تجاوز الميزانية."""
        if not self.budget.block_on_limit:
            return False

        now = datetime.now(timezone.utc)

        # Check global limits
        if self.budget.daily_limit:
            if self._get_cost_since(now - timedelta(days=1)) >= self.budget.daily_limit:
                return True

        if self.budget.weekly_limit:
            if self._get_cost_since(now - timedelta(weeks=1)) >= self.budget.weekly_limit:
                return True

        if self.budget.monthly_limit:
            if self._get_cost_since(now - timedelta(days=30)) >= self.budget.monthly_limit:
                return True

        # Check provider limit
        if provider and provider in self.budget.provider_limits:
            provider_cost = sum(
                r.cost for r in self._records if r.provider == provider and r.timestamp >= now - timedelta(days=30)
            )
            if provider_cost >= self.budget.provider_limits[provider]:
                return True

        return False

    def get_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        provider: Optional[str] = None,
    ) -> CostSummary:
        """الحصول على ملخص التكاليف."""
        records = self._records

        # Filter by date
        if start_date:
            records = [r for r in records if r.timestamp >= start_date]
        if end_date:
            records = [r for r in records if r.timestamp <= end_date]
        if provider:
            records = [r for r in records if r.provider == provider]

        # Calculate totals
        total_cost = sum(r.cost for r in records)
        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_cached = sum(r.cached_tokens for r in records)

        # Breakdown by provider
        by_provider: Dict[str, float] = {}
        for r in records:
            by_provider[r.provider] = by_provider.get(r.provider, 0) + r.cost

        # Breakdown by model
        by_model: Dict[str, float] = {}
        for r in records:
            by_model[r.model] = by_model.get(r.model, 0) + r.cost

        # Estimate savings from caching
        estimated_savings = 0.0
        for r in records:
            if r.cached_tokens > 0:
                pricing = self.get_pricing(r.model)
                if pricing and pricing.cached_input_cost_per_1k is not None:
                    regular_cost = (r.cached_tokens / 1000) * pricing.input_cost_per_1k
                    cached_cost = (r.cached_tokens / 1000) * pricing.cached_input_cost_per_1k
                    estimated_savings += regular_cost - cached_cost

        return CostSummary(
            total_cost=total_cost,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cached_tokens=total_cached,
            request_count=len(records),
            by_provider=by_provider,
            by_model=by_model,
            start_date=start_date or (records[0].timestamp if records else None),
            end_date=end_date or (records[-1].timestamp if records else None),
            estimated_savings=estimated_savings,
        )

    def get_daily_report(self, days: int = 7) -> List[Dict[str, Any]]:
        """تقرير يومي."""
        now = datetime.now(timezone.utc)
        report = []

        for i in range(days):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            summary = self.get_summary(start_date=day_start, end_date=day_end)
            report.append(
                {
                    "date": day_start.strftime("%Y-%m-%d"),
                    **summary.to_dict(),
                }
            )

        return list(reversed(report))

    def get_provider_comparison(self) -> List[Dict[str, Any]]:
        """مقارنة تكاليف المزودين."""
        summary = self.get_summary()
        comparison = []

        for provider, cost in sorted(summary.by_provider.items(), key=lambda x: -x[1]):
            provider_records = [r for r in self._records if r.provider == provider]
            tokens = sum(r.input_tokens + r.output_tokens for r in provider_records)
            cost_per_1k = (cost / tokens * 1000) if tokens > 0 else 0

            comparison.append(
                {
                    "provider": provider,
                    "total_cost": round(cost, 6),
                    "total_tokens": tokens,
                    "cost_per_1k_tokens": round(cost_per_1k, 6),
                    "request_count": len(provider_records),
                    "percentage": round(cost / summary.total_cost * 100, 2) if summary.total_cost > 0 else 0,
                }
            )

        return comparison

    def export_records(self, format: str = "json") -> str:
        """تصدير السجلات."""
        if format == "json":
            return json.dumps([r.to_dict() for r in self._records], indent=2)
        elif format == "csv":
            if not self._records:
                return ""

            headers = [
                "timestamp",
                "provider",
                "model",
                "input_tokens",
                "output_tokens",
                "cached_tokens",
                "cost",
                "currency",
            ]
            lines = [",".join(headers)]

            for r in self._records:
                line = (
                    f"{r.timestamp.isoformat()},{r.provider},{r.model},"
                    f"{r.input_tokens},{r.output_tokens},{r.cached_tokens},"
                    f"{r.cost},{r.currency.value}"
                )
                lines.append(line)

            return "\n".join(lines)
        else:
            raise ValueError(f"Unknown format: {format}")

    async def cleanup_old_records(self, days: int = 90) -> int:
        """حذف السجلات القديمة."""
        async with self._lock:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            old_count = len(self._records)
            self._records = [r for r in self._records if r.timestamp >= cutoff]
            removed = old_count - len(self._records)

            if removed > 0:
                self._save_records()
                logger.info(f"Removed {removed} old cost records")

            return removed

    def save(self) -> None:
        """حفظ السجلات يدوياً."""
        self._save_records()


# ==================== Factory ====================


def create_cost_tracker(
    persist_path: Optional[str] = None,
    daily_limit: Optional[float] = None,
    monthly_limit: Optional[float] = None,
) -> CostTracker:
    """إنشاء مدير تتبع التكاليف."""
    budget = BudgetConfig(
        daily_limit=daily_limit,
        monthly_limit=monthly_limit,
    )
    return CostTracker(budget=budget, persist_path=persist_path)
