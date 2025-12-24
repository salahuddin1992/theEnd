"""
AI Cost Optimizer - مُحسِّن تكاليف الذكاء الاصطناعي
==================================================

نظام ذكي لتحسين تكاليف استخدام نماذج الذكاء الاصطناعي:
- اختيار أفضل مزود بناءً على التكلفة/الجودة
- تحليل الاستخدام وتوقع التكاليف
- اقتراحات للتوفير
- مقارنة أداء المزودين
- موازنة الحمل الذكية
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from distributed_cluster.ai.llm.cost_tracker import (
    CostTracker,
    ModelPricing,
    DEFAULT_PRICING,
    CostSummary,
)

logger = logging.getLogger(__name__)


class OptimizationStrategy(str, Enum):
    """استراتيجيات التحسين."""

    CHEAPEST = "cheapest"  # أرخص خيار متاح
    BALANCED = "balanced"  # توازن بين التكلفة والجودة
    FASTEST = "fastest"  # أسرع استجابة
    BEST_QUALITY = "best_quality"  # أفضل جودة
    SMART = "smart"  # ذكي - يختار حسب المهمة


class TaskComplexity(str, Enum):
    """مستوى تعقيد المهمة."""

    SIMPLE = "simple"  # مهام بسيطة (إجابات قصيرة)
    MODERATE = "moderate"  # مهام متوسطة
    COMPLEX = "complex"  # مهام معقدة (تحليل، برمجة)
    CRITICAL = "critical"  # مهام حرجة (تحتاج أفضل نموذج)


@dataclass
class ProviderMetrics:
    """مقاييس أداء المزود."""

    provider: str
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0
    avg_quality_score: float = 0.5
    total_requests: int = 0
    total_cost: float = 0.0
    last_error: Optional[str] = None
    last_used: Optional[datetime] = None
    is_available: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "success_rate": round(self.success_rate, 4),
            "avg_quality_score": round(self.avg_quality_score, 4),
            "total_requests": self.total_requests,
            "total_cost": round(self.total_cost, 6),
            "last_error": self.last_error,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "is_available": self.is_available,
        }


@dataclass
class ModelRecommendation:
    """توصية نموذج."""

    model: str
    provider: str
    estimated_cost: float
    reason: str
    confidence: float  # 0-1
    alternatives: List[Tuple[str, str, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "provider": self.provider,
            "estimated_cost": round(self.estimated_cost, 6),
            "reason": self.reason,
            "confidence": round(self.confidence, 2),
            "alternatives": [
                {"model": m, "provider": p, "cost": round(c, 6)}
                for m, p, c in self.alternatives
            ],
        }


@dataclass
class SavingsOpportunity:
    """فرصة توفير."""

    description: str
    potential_savings: float
    current_cost: float
    suggested_cost: float
    action: str
    priority: str  # high, medium, low

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "potential_savings": round(self.potential_savings, 4),
            "current_cost": round(self.current_cost, 4),
            "suggested_cost": round(self.suggested_cost, 4),
            "action": self.action,
            "priority": self.priority,
        }


@dataclass
class CostForecast:
    """توقع التكاليف."""

    period: str  # daily, weekly, monthly
    predicted_cost: float
    confidence_interval: Tuple[float, float]
    trend: str  # increasing, stable, decreasing
    factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "period": self.period,
            "predicted_cost": round(self.predicted_cost, 4),
            "confidence_interval": [round(self.confidence_interval[0], 4), round(self.confidence_interval[1], 4)],
            "trend": self.trend,
            "factors": self.factors,
        }


class CostOptimizer:
    """
    مُحسِّن تكاليف الذكاء الاصطناعي.

    الاستخدام:
        optimizer = CostOptimizer(cost_tracker)

        # الحصول على توصية نموذج
        recommendation = optimizer.recommend_model(
            task="Write a hello world program",
            complexity=TaskComplexity.SIMPLE,
            strategy=OptimizationStrategy.BALANCED,
        )

        # تحليل فرص التوفير
        opportunities = optimizer.analyze_savings()

        # توقع التكاليف
        forecast = optimizer.forecast_costs(period="monthly")
    """

    # Model quality tiers (higher = better)
    MODEL_QUALITY_TIERS: Dict[str, float] = {
        # Tier 1 - Premium (0.9-1.0)
        "claude-3-opus-20240229": 1.0,
        "gpt-4o": 0.95,
        "o1": 0.95,
        "claude-3-5-sonnet-20241022": 0.92,
        "gemini-1.5-pro": 0.90,

        # Tier 2 - High (0.75-0.89)
        "gpt-4-turbo": 0.88,
        "claude-3-sonnet-20240229": 0.85,
        "mistral-large-latest": 0.83,
        "command-r-plus": 0.80,
        "deepseek-reasoner": 0.80,
        "llama-3.3-70b-versatile": 0.78,

        # Tier 3 - Medium (0.5-0.74)
        "claude-3-5-haiku-20241022": 0.72,
        "gpt-4o-mini": 0.70,
        "o1-mini": 0.70,
        "gemini-1.5-flash": 0.68,
        "claude-3-haiku-20240307": 0.65,
        "mistral-small-latest": 0.62,
        "deepseek-chat": 0.60,
        "command-r": 0.58,
        "mixtral-8x7b-32768": 0.55,

        # Tier 4 - Basic (0.3-0.49)
        "gpt-3.5-turbo": 0.45,
        "llama-3.1-8b-instant": 0.42,
        "gemini-2.0-flash": 0.40,

        # Local models (free but variable quality)
        "llama3": 0.50,
        "mistral": 0.45,
        "codellama": 0.48,
    }

    # Task complexity to minimum quality mapping
    COMPLEXITY_MIN_QUALITY: Dict[TaskComplexity, float] = {
        TaskComplexity.SIMPLE: 0.3,
        TaskComplexity.MODERATE: 0.5,
        TaskComplexity.COMPLEX: 0.7,
        TaskComplexity.CRITICAL: 0.85,
    }

    def __init__(
        self,
        cost_tracker: Optional[CostTracker] = None,
        pricing: Optional[Dict[str, ModelPricing]] = None,
        persist_path: Optional[str] = None,
    ):
        self.cost_tracker = cost_tracker or CostTracker()
        self.pricing = pricing or DEFAULT_PRICING.copy()
        self.persist_path = persist_path

        # Provider metrics
        self._provider_metrics: Dict[str, ProviderMetrics] = {}
        self._request_history: List[Dict[str, Any]] = []

        # Load persisted metrics
        if persist_path:
            self._load_metrics()

    def _load_metrics(self) -> None:
        """تحميل المقاييس المحفوظة."""
        if not self.persist_path:
            return

        path = Path(self.persist_path)
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    for provider, metrics in data.get("provider_metrics", {}).items():
                        self._provider_metrics[provider] = ProviderMetrics(
                            provider=provider,
                            avg_latency_ms=metrics.get("avg_latency_ms", 0),
                            success_rate=metrics.get("success_rate", 1.0),
                            avg_quality_score=metrics.get("avg_quality_score", 0.5),
                            total_requests=metrics.get("total_requests", 0),
                            total_cost=metrics.get("total_cost", 0),
                            is_available=metrics.get("is_available", True),
                        )
                logger.info(f"Loaded optimizer metrics for {len(self._provider_metrics)} providers")
            except Exception as e:
                logger.error(f"Failed to load optimizer metrics: {e}")

    def _save_metrics(self) -> None:
        """حفظ المقاييس."""
        if not self.persist_path:
            return

        try:
            path = Path(self.persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "provider_metrics": {
                    provider: metrics.to_dict()
                    for provider, metrics in self._provider_metrics.items()
                },
                "updated_at": datetime.utcnow().isoformat(),
            }

            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save optimizer metrics: {e}")

    def get_model_quality(self, model: str) -> float:
        """الحصول على درجة جودة النموذج."""
        # Try exact match
        if model in self.MODEL_QUALITY_TIERS:
            return self.MODEL_QUALITY_TIERS[model]

        # Try partial match
        for known_model, quality in self.MODEL_QUALITY_TIERS.items():
            if model.startswith(known_model) or known_model.startswith(model):
                return quality

        # Default quality
        return 0.5

    def estimate_cost(
        self,
        model: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
    ) -> float:
        """تقدير تكلفة الاستخدام."""
        return self.cost_tracker.calculate_cost(
            model=model,
            input_tokens=estimated_input_tokens,
            output_tokens=estimated_output_tokens,
        )

    def recommend_model(
        self,
        task: str,
        complexity: TaskComplexity = TaskComplexity.MODERATE,
        strategy: OptimizationStrategy = OptimizationStrategy.BALANCED,
        estimated_input_tokens: int = 500,
        estimated_output_tokens: int = 500,
        preferred_providers: Optional[List[str]] = None,
        excluded_providers: Optional[List[str]] = None,
        max_cost: Optional[float] = None,
    ) -> ModelRecommendation:
        """
        توصية بأفضل نموذج للمهمة.

        Args:
            task: وصف المهمة
            complexity: مستوى تعقيد المهمة
            strategy: استراتيجية التحسين
            estimated_input_tokens: عدد tokens المتوقع للإدخال
            estimated_output_tokens: عدد tokens المتوقع للإخراج
            preferred_providers: مزودين مفضلين
            excluded_providers: مزودين مستبعدين
            max_cost: الحد الأقصى للتكلفة

        Returns:
            توصية النموذج مع البدائل
        """
        min_quality = self.COMPLEXITY_MIN_QUALITY[complexity]
        candidates = []

        # Build candidate list
        for model_name, pricing in self.pricing.items():
            # Skip excluded providers
            if excluded_providers and pricing.provider in excluded_providers:
                continue

            # Check provider availability
            metrics = self._provider_metrics.get(pricing.provider)
            if metrics and not metrics.is_available:
                continue

            # Calculate cost
            cost = pricing.calculate_cost(estimated_input_tokens, estimated_output_tokens)

            # Check max cost
            if max_cost and cost > max_cost:
                continue

            # Get quality
            quality = self.get_model_quality(model_name)

            # Check minimum quality
            if quality < min_quality:
                continue

            # Calculate score based on strategy
            score = self._calculate_model_score(
                model_name=model_name,
                provider=pricing.provider,
                cost=cost,
                quality=quality,
                strategy=strategy,
                preferred_providers=preferred_providers,
            )

            candidates.append({
                "model": model_name,
                "provider": pricing.provider,
                "cost": cost,
                "quality": quality,
                "score": score,
            })

        if not candidates:
            # Fallback to a default
            return ModelRecommendation(
                model="gpt-4o-mini",
                provider="openai",
                estimated_cost=self.estimate_cost("gpt-4o-mini", estimated_input_tokens, estimated_output_tokens),
                reason="Default recommendation (no suitable candidates found)",
                confidence=0.5,
            )

        # Sort by score
        candidates.sort(key=lambda x: x["score"], reverse=True)

        best = candidates[0]

        # Build reason
        reason = self._build_recommendation_reason(best, strategy, complexity)

        # Get alternatives
        alternatives = [
            (c["model"], c["provider"], c["cost"])
            for c in candidates[1:4]  # Top 3 alternatives
        ]

        return ModelRecommendation(
            model=best["model"],
            provider=best["provider"],
            estimated_cost=best["cost"],
            reason=reason,
            confidence=min(0.95, best["score"]),
            alternatives=alternatives,
        )

    def _calculate_model_score(
        self,
        model_name: str,
        provider: str,
        cost: float,
        quality: float,
        strategy: OptimizationStrategy,
        preferred_providers: Optional[List[str]] = None,
    ) -> float:
        """حساب درجة النموذج."""
        # Normalize cost (inverse, lower is better)
        # Assuming max reasonable cost is $1 per request
        cost_score = max(0, 1 - (cost / 1.0))

        # Get provider metrics
        metrics = self._provider_metrics.get(provider)
        latency_score = 1.0
        reliability_score = 1.0

        if metrics:
            # Latency score (lower is better, normalize to 0-1)
            latency_score = max(0, 1 - (metrics.avg_latency_ms / 10000))  # 10s max
            reliability_score = metrics.success_rate

        # Preference bonus
        preference_bonus = 0.1 if preferred_providers and provider in preferred_providers else 0

        # Calculate final score based on strategy
        if strategy == OptimizationStrategy.CHEAPEST:
            score = cost_score * 0.8 + quality * 0.1 + reliability_score * 0.1
        elif strategy == OptimizationStrategy.FASTEST:
            score = latency_score * 0.6 + cost_score * 0.2 + quality * 0.1 + reliability_score * 0.1
        elif strategy == OptimizationStrategy.BEST_QUALITY:
            score = quality * 0.7 + reliability_score * 0.2 + cost_score * 0.1
        elif strategy == OptimizationStrategy.BALANCED:
            score = quality * 0.35 + cost_score * 0.35 + reliability_score * 0.2 + latency_score * 0.1
        else:  # SMART
            # Dynamic weights based on task
            score = quality * 0.4 + cost_score * 0.3 + reliability_score * 0.2 + latency_score * 0.1

        return score + preference_bonus

    def _build_recommendation_reason(
        self,
        candidate: Dict[str, Any],
        strategy: OptimizationStrategy,
        complexity: TaskComplexity,
    ) -> str:
        """بناء سبب التوصية."""
        model = candidate["model"]
        provider = candidate["provider"]
        cost = candidate["cost"]
        quality = candidate["quality"]

        reasons = []

        if strategy == OptimizationStrategy.CHEAPEST:
            reasons.append(f"Lowest cost at ${cost:.6f}")
        elif strategy == OptimizationStrategy.FASTEST:
            reasons.append("Optimized for speed")
        elif strategy == OptimizationStrategy.BEST_QUALITY:
            reasons.append(f"Highest quality (score: {quality:.2f})")
        elif strategy == OptimizationStrategy.BALANCED:
            reasons.append(f"Best balance of cost (${cost:.6f}) and quality ({quality:.2f})")
        else:
            reasons.append("Smart selection based on task requirements")

        reasons.append(f"Suitable for {complexity.value} tasks")

        return "; ".join(reasons)

    def analyze_savings(self) -> List[SavingsOpportunity]:
        """
        تحليل فرص التوفير.

        Returns:
            قائمة بفرص التوفير المحتملة
        """
        opportunities = []
        summary = self.cost_tracker.get_summary()

        # 1. Check for expensive models that could be replaced
        for model, cost in summary.by_model.items():
            if cost == 0:
                continue

            quality = self.get_model_quality(model)
            pricing = self.cost_tracker.get_pricing(model)

            if pricing:
                # Find cheaper alternatives with acceptable quality
                cheaper_alternatives = []
                for alt_model, alt_pricing in self.pricing.items():
                    alt_quality = self.get_model_quality(alt_model)

                    if alt_quality >= quality * 0.8 and alt_pricing.input_cost_per_1k < pricing.input_cost_per_1k * 0.7:
                        cheaper_alternatives.append((alt_model, alt_pricing))

                if cheaper_alternatives:
                    best_alt = min(cheaper_alternatives, key=lambda x: x[1].input_cost_per_1k)
                    savings_ratio = 1 - (best_alt[1].input_cost_per_1k / pricing.input_cost_per_1k)
                    potential_savings = cost * savings_ratio

                    opportunities.append(SavingsOpportunity(
                        description=f"Replace {model} with {best_alt[0]}",
                        potential_savings=potential_savings,
                        current_cost=cost,
                        suggested_cost=cost * (1 - savings_ratio),
                        action=f"Switch to {best_alt[0]} for similar quality at lower cost",
                        priority="high" if potential_savings > 10 else "medium",
                    ))

        # 2. Check for underutilized caching
        if summary.total_cached_tokens < summary.total_input_tokens * 0.1:
            # Less than 10% cache hit rate
            potential_savings = summary.total_cost * 0.2  # Assume 20% savings possible

            opportunities.append(SavingsOpportunity(
                description="Improve prompt caching",
                potential_savings=potential_savings,
                current_cost=summary.total_cost,
                suggested_cost=summary.total_cost * 0.8,
                action="Use consistent system prompts and enable caching for repeated patterns",
                priority="medium",
            ))

        # 3. Check for batch processing opportunities
        if summary.request_count > 100:
            # Many requests could benefit from batching
            potential_savings = summary.total_cost * 0.25  # 50% batch discount on half of requests

            opportunities.append(SavingsOpportunity(
                description="Use batch API for non-urgent requests",
                potential_savings=potential_savings,
                current_cost=summary.total_cost,
                suggested_cost=summary.total_cost * 0.75,
                action="Queue non-time-sensitive requests for batch processing",
                priority="medium",
            ))

        # 4. Check for expensive providers
        for provider, cost in summary.by_provider.items():
            if cost > summary.total_cost * 0.5:
                # Provider accounts for >50% of costs
                opportunities.append(SavingsOpportunity(
                    description=f"Diversify away from {provider}",
                    potential_savings=cost * 0.2,
                    current_cost=cost,
                    suggested_cost=cost * 0.8,
                    action=f"Route some {provider} requests to cheaper alternatives",
                    priority="low",
                ))

        # Sort by potential savings
        opportunities.sort(key=lambda x: x.potential_savings, reverse=True)

        return opportunities

    def forecast_costs(
        self,
        period: str = "monthly",
        days_history: int = 30,
    ) -> CostForecast:
        """
        توقع التكاليف المستقبلية.

        Args:
            period: الفترة (daily, weekly, monthly)
            days_history: أيام البيانات التاريخية للتحليل

        Returns:
            توقع التكاليف
        """
        daily_costs = []
        now = datetime.utcnow()

        # Get historical daily costs
        for i in range(days_history):
            day_start = (now - timedelta(days=i+1)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            summary = self.cost_tracker.get_summary(start_date=day_start, end_date=day_end)
            daily_costs.append(summary.total_cost)

        if not daily_costs or all(c == 0 for c in daily_costs):
            return CostForecast(
                period=period,
                predicted_cost=0,
                confidence_interval=(0, 0),
                trend="stable",
                factors=["Insufficient historical data"],
            )

        # Calculate statistics
        avg_daily = statistics.mean(daily_costs)
        std_daily = statistics.stdev(daily_costs) if len(daily_costs) > 1 else 0

        # Determine trend
        if len(daily_costs) >= 7:
            recent_avg = statistics.mean(daily_costs[:7])
            older_avg = statistics.mean(daily_costs[7:14]) if len(daily_costs) >= 14 else avg_daily

            if recent_avg > older_avg * 1.1:
                trend = "increasing"
            elif recent_avg < older_avg * 0.9:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"

        # Calculate period prediction
        if period == "daily":
            multiplier = 1
        elif period == "weekly":
            multiplier = 7
        else:  # monthly
            multiplier = 30

        predicted = avg_daily * multiplier

        # Adjust for trend
        if trend == "increasing":
            predicted *= 1.1
        elif trend == "decreasing":
            predicted *= 0.9

        # Confidence interval (95%)
        margin = 1.96 * std_daily * multiplier
        confidence_interval = (max(0, predicted - margin), predicted + margin)

        # Identify factors
        factors = []
        if trend == "increasing":
            factors.append("Usage is trending upward")
        elif trend == "decreasing":
            factors.append("Usage is trending downward")

        if std_daily > avg_daily * 0.5:
            factors.append("High usage variability")

        summary = self.cost_tracker.get_summary()
        if summary.by_provider:
            top_provider = max(summary.by_provider.items(), key=lambda x: x[1])
            factors.append(f"Primary provider: {top_provider[0]}")

        return CostForecast(
            period=period,
            predicted_cost=predicted,
            confidence_interval=confidence_interval,
            trend=trend,
            factors=factors,
        )

    async def record_request(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        success: bool,
        quality_score: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        تسجيل طلب جديد لتحديث المقاييس.

        Args:
            provider: اسم المزود
            model: اسم النموذج
            input_tokens: عدد tokens الإدخال
            output_tokens: عدد tokens الإخراج
            latency_ms: زمن الاستجابة بالمللي ثانية
            success: هل نجح الطلب
            quality_score: درجة الجودة (اختياري)
            error: رسالة الخطأ إن وجد
        """
        # Record in cost tracker
        await self.cost_tracker.record_usage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        # Update provider metrics
        if provider not in self._provider_metrics:
            self._provider_metrics[provider] = ProviderMetrics(provider=provider)

        metrics = self._provider_metrics[provider]
        old_count = metrics.total_requests
        new_count = old_count + 1

        # Update averages
        metrics.avg_latency_ms = (metrics.avg_latency_ms * old_count + latency_ms) / new_count
        metrics.success_rate = (metrics.success_rate * old_count + (1 if success else 0)) / new_count

        if quality_score is not None:
            metrics.avg_quality_score = (metrics.avg_quality_score * old_count + quality_score) / new_count

        metrics.total_requests = new_count
        metrics.total_cost += self.estimate_cost(model, input_tokens, output_tokens)
        metrics.last_used = datetime.utcnow()

        if error:
            metrics.last_error = error

        # Check if provider should be marked unavailable
        if metrics.success_rate < 0.5 and metrics.total_requests >= 10:
            metrics.is_available = False
            logger.warning(f"Provider {provider} marked as unavailable due to low success rate")

        # Save periodically
        if new_count % 50 == 0:
            self._save_metrics()

    def get_provider_metrics(self) -> Dict[str, Dict[str, Any]]:
        """الحصول على مقاييس جميع المزودين."""
        return {
            provider: metrics.to_dict()
            for provider, metrics in self._provider_metrics.items()
        }

    def compare_providers(
        self,
        estimated_input_tokens: int = 1000,
        estimated_output_tokens: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        مقارنة المزودين.

        Returns:
            قائمة مقارنة مرتبة حسب التكلفة
        """
        comparisons = []
        providers_seen = set()

        for model_name, pricing in self.pricing.items():
            if pricing.provider in providers_seen:
                continue
            providers_seen.add(pricing.provider)

            cost = pricing.calculate_cost(estimated_input_tokens, estimated_output_tokens)
            metrics = self._provider_metrics.get(pricing.provider)

            comparisons.append({
                "provider": pricing.provider,
                "sample_model": model_name,
                "estimated_cost": round(cost, 6),
                "cost_per_1k_input": pricing.input_cost_per_1k,
                "cost_per_1k_output": pricing.output_cost_per_1k,
                "supports_cache": pricing.cached_input_cost_per_1k is not None,
                "batch_discount": pricing.batch_discount,
                "avg_latency_ms": metrics.avg_latency_ms if metrics else None,
                "success_rate": metrics.success_rate if metrics else None,
                "is_available": metrics.is_available if metrics else True,
            })

        # Sort by cost
        comparisons.sort(key=lambda x: x["estimated_cost"])

        return comparisons

    def get_optimization_report(self) -> Dict[str, Any]:
        """
        تقرير تحسين شامل.

        Returns:
            تقرير مفصل بكل التحليلات
        """
        summary = self.cost_tracker.get_summary()
        savings = self.analyze_savings()
        forecast = self.forecast_costs()
        provider_comparison = self.compare_providers()

        return {
            "summary": summary.to_dict(),
            "savings_opportunities": [s.to_dict() for s in savings],
            "cost_forecast": forecast.to_dict(),
            "provider_comparison": provider_comparison,
            "provider_metrics": self.get_provider_metrics(),
            "recommendations": {
                "total_potential_savings": sum(s.potential_savings for s in savings),
                "top_action": savings[0].action if savings else None,
                "forecast_trend": forecast.trend,
            },
            "generated_at": datetime.utcnow().isoformat(),
        }


# =============================================================================
# Factory
# =============================================================================


def create_cost_optimizer(
    cost_tracker: Optional[CostTracker] = None,
    persist_path: Optional[str] = None,
) -> CostOptimizer:
    """
    إنشاء مُحسِّن التكاليف.

    Args:
        cost_tracker: مدير تتبع التكاليف (اختياري)
        persist_path: مسار حفظ المقاييس

    Returns:
        CostOptimizer instance
    """
    return CostOptimizer(
        cost_tracker=cost_tracker,
        persist_path=persist_path,
    )
