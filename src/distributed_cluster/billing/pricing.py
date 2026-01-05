# -*- coding: utf-8 -*-
"""
Pricing Engine for NebulaCompute.

Flexible pricing configuration and calculation
for resources and services.

محرك التسعير.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PricingModel(str, Enum):
    """Pricing model type."""

    FIXED = "fixed"  # Fixed price per unit
    TIERED = "tiered"  # Price tiers based on usage
    TIME_BASED = "time_based"  # Different prices by time of day
    SPOT = "spot"  # Dynamic spot pricing


@dataclass
class ResourcePrice:
    """
    Resource price definition.

    تعريف سعر المورد.
    """

    resource_type: str
    unit: str
    base_price: float
    currency: str = "USD"
    model: PricingModel = PricingModel.FIXED
    tiers: List[Dict[str, Any]] = field(default_factory=list)
    time_rates: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def calculate_cost(
        self,
        quantity: float,
        usage_time: Optional[datetime] = None,
    ) -> float:
        """Calculate cost for given quantity."""
        if self.model == PricingModel.FIXED:
            return quantity * self.base_price

        elif self.model == PricingModel.TIERED:
            return self._calculate_tiered_cost(quantity)

        elif self.model == PricingModel.TIME_BASED:
            return self._calculate_time_based_cost(quantity, usage_time)

        else:
            return quantity * self.base_price

    def _calculate_tiered_cost(self, quantity: float) -> float:
        """Calculate cost using tiered pricing."""
        if not self.tiers:
            return quantity * self.base_price

        total_cost = 0.0
        remaining = quantity

        for tier in sorted(self.tiers, key=lambda t: t.get("min", 0)):
            tier_min = tier.get("min", 0)
            tier_max = tier.get("max", float("inf"))
            tier_price = tier.get("price", self.base_price)

            if remaining <= 0:
                break

            tier_quantity = min(remaining, tier_max - tier_min)
            total_cost += tier_quantity * tier_price
            remaining -= tier_quantity

        return total_cost

    def _calculate_time_based_cost(
        self,
        quantity: float,
        usage_time: Optional[datetime],
    ) -> float:
        """Calculate cost based on time of day."""
        if not usage_time or not self.time_rates:
            return quantity * self.base_price

        hour = usage_time.hour
        rate = self.base_price

        # Find applicable rate
        for time_range, multiplier in self.time_rates.items():
            # Parse time range like "00:00-06:00"
            try:
                start_str, end_str = time_range.split("-")
                start_hour = int(start_str.split(":")[0])
                end_hour = int(end_str.split(":")[0])

                if start_hour <= hour < end_hour:
                    rate = self.base_price * multiplier
                    break
            except (ValueError, IndexError):
                continue

        return quantity * rate

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_type": self.resource_type,
            "unit": self.unit,
            "base_price": self.base_price,
            "currency": self.currency,
            "model": self.model.value,
            "tiers": self.tiers,
            "time_rates": self.time_rates,
            "metadata": self.metadata,
        }


@dataclass
class PricingRule:
    """
    Pricing rule for special conditions.

    قاعدة تسعير.
    """

    rule_id: str
    name: str
    condition_type: str  # user, team, instance_type, region
    condition_value: str
    discount_percent: float = 0.0
    markup_percent: float = 0.0
    priority: int = 0  # Higher priority rules applied first
    enabled: bool = True
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def applies_to(
        self,
        context: Dict[str, Any],
    ) -> bool:
        """Check if rule applies to given context."""
        if not self.enabled:
            return False

        now = datetime.now(timezone.utc)
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False

        return context.get(self.condition_type) == self.condition_value

    def apply(self, base_cost: float) -> float:
        """Apply rule to base cost."""
        cost = base_cost

        # Apply discount
        if self.discount_percent > 0:
            cost *= 1 - (self.discount_percent / 100)

        # Apply markup
        if self.markup_percent > 0:
            cost *= 1 + (self.markup_percent / 100)

        return cost

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "condition_type": self.condition_type,
            "condition_value": self.condition_value,
            "discount_percent": self.discount_percent,
            "markup_percent": self.markup_percent,
            "priority": self.priority,
            "enabled": self.enabled,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "metadata": self.metadata,
        }


class PricingEngine:
    """
    Pricing engine for cost calculation.

    محرك التسعير لحساب التكاليف.

    Features:
    - Multiple pricing models
    - Tiered pricing
    - Time-based pricing
    - Custom pricing rules
    - Discount and markup support
    """

    def __init__(
        self,
        default_currency: str = "USD",
    ):
        """Initialize Pricing Engine."""
        self.default_currency = default_currency
        self._prices: Dict[str, ResourcePrice] = {}
        self._rules: Dict[str, PricingRule] = {}

        # Initialize default prices
        self._initialize_defaults()

    def _initialize_defaults(self) -> None:
        """Initialize default resource prices."""
        defaults = [
            ResourcePrice(
                resource_type="cpu",
                unit="core-hour",
                base_price=0.05,
                model=PricingModel.FIXED,
            ),
            ResourcePrice(
                resource_type="gpu",
                unit="gpu-hour",
                base_price=1.50,
                model=PricingModel.FIXED,
            ),
            ResourcePrice(
                resource_type="memory",
                unit="GB-hour",
                base_price=0.01,
                model=PricingModel.FIXED,
            ),
            ResourcePrice(
                resource_type="storage",
                unit="GB-month",
                base_price=0.10,
                model=PricingModel.TIERED,
                tiers=[
                    {"min": 0, "max": 100, "price": 0.10},
                    {"min": 100, "max": 1000, "price": 0.08},
                    {"min": 1000, "max": float("inf"), "price": 0.05},
                ],
            ),
            ResourcePrice(
                resource_type="network_egress",
                unit="GB",
                base_price=0.05,
                model=PricingModel.TIERED,
                tiers=[
                    {"min": 0, "max": 10, "price": 0.00},  # Free tier
                    {"min": 10, "max": 100, "price": 0.05},
                    {"min": 100, "max": float("inf"), "price": 0.03},
                ],
            ),
            ResourcePrice(
                resource_type="llm_tokens",
                unit="1K tokens",
                base_price=0.01,
                model=PricingModel.FIXED,
            ),
        ]

        for price in defaults:
            self._prices[price.resource_type] = price

    def set_price(self, price: ResourcePrice) -> None:
        """Set or update a resource price."""
        self._prices[price.resource_type] = price
        logger.info(
            f"Updated price for {price.resource_type}: "
            f"${price.base_price}/{price.unit}"
        )

    def get_price(self, resource_type: str) -> Optional[ResourcePrice]:
        """Get price for a resource type."""
        return self._prices.get(resource_type)

    def list_prices(self) -> List[ResourcePrice]:
        """List all resource prices."""
        return list(self._prices.values())

    def add_rule(self, rule: PricingRule) -> None:
        """Add a pricing rule."""
        self._rules[rule.rule_id] = rule
        logger.info(f"Added pricing rule: {rule.name}")

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a pricing rule."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def get_rule(self, rule_id: str) -> Optional[PricingRule]:
        """Get a pricing rule by ID."""
        return self._rules.get(rule_id)

    def list_rules(self) -> List[PricingRule]:
        """List all pricing rules."""
        return list(self._rules.values())

    def calculate_cost(
        self,
        resource_type: str,
        quantity: float,
        context: Optional[Dict[str, Any]] = None,
        usage_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Calculate cost for a resource.

        حساب تكلفة مورد.

        Args:
            resource_type: Type of resource
            quantity: Quantity used
            context: Context for rule matching
            usage_time: Time of usage for time-based pricing

        Returns:
            Cost breakdown dictionary
        """
        price = self._prices.get(resource_type)
        if not price:
            logger.warning(f"No price defined for {resource_type}")
            return {
                "resource_type": resource_type,
                "quantity": quantity,
                "base_cost": 0.0,
                "final_cost": 0.0,
                "currency": self.default_currency,
                "error": "Price not defined",
            }

        # Calculate base cost
        base_cost = price.calculate_cost(quantity, usage_time)

        # Apply rules
        final_cost = base_cost
        applied_rules = []
        context = context or {}

        # Sort rules by priority
        sorted_rules = sorted(
            self._rules.values(),
            key=lambda r: r.priority,
            reverse=True,
        )

        for rule in sorted_rules:
            if rule.applies_to(context):
                final_cost = rule.apply(final_cost)
                applied_rules.append(rule.name)

        return {
            "resource_type": resource_type,
            "quantity": quantity,
            "unit": price.unit,
            "unit_price": price.base_price,
            "pricing_model": price.model.value,
            "base_cost": base_cost,
            "final_cost": final_cost,
            "currency": price.currency,
            "applied_rules": applied_rules,
            "discount": base_cost - final_cost if base_cost > final_cost else 0.0,
        }

    def calculate_job_cost(
        self,
        resources: Dict[str, float],
        context: Optional[Dict[str, Any]] = None,
        usage_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Calculate total cost for a job.

        حساب التكلفة الإجمالية لمهمة.

        Args:
            resources: Dictionary of resource_type -> quantity
            context: Context for rule matching
            usage_time: Time of usage

        Returns:
            Total cost breakdown
        """
        breakdown = []
        total_base_cost = 0.0
        total_final_cost = 0.0

        for resource_type, quantity in resources.items():
            cost_info = self.calculate_cost(
                resource_type, quantity, context, usage_time
            )
            breakdown.append(cost_info)
            total_base_cost += cost_info["base_cost"]
            total_final_cost += cost_info["final_cost"]

        return {
            "breakdown": breakdown,
            "total_base_cost": total_base_cost,
            "total_final_cost": total_final_cost,
            "total_discount": total_base_cost - total_final_cost,
            "currency": self.default_currency,
        }

    def get_price_estimate(
        self,
        resource_type: str,
        quantity: float,
        hours: int = 1,
    ) -> Dict[str, Any]:
        """
        Get price estimate for planning.

        تقدير السعر للتخطيط.
        """
        hourly = self.calculate_cost(resource_type, quantity)
        daily = self.calculate_cost(resource_type, quantity * 24)
        monthly = self.calculate_cost(resource_type, quantity * 24 * 30)

        return {
            "resource_type": resource_type,
            "quantity_per_hour": quantity,
            "hourly_cost": hourly["final_cost"],
            "daily_cost": daily["final_cost"],
            "monthly_cost": monthly["final_cost"],
            "currency": self.default_currency,
        }

    def export_pricing(self) -> Dict[str, Any]:
        """Export all pricing configuration."""
        return {
            "prices": {rt: p.to_dict() for rt, p in self._prices.items()},
            "rules": {rid: r.to_dict() for rid, r in self._rules.items()},
            "default_currency": self.default_currency,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def import_pricing(self, config: Dict[str, Any]) -> None:
        """Import pricing configuration."""
        for rt, price_dict in config.get("prices", {}).items():
            price = ResourcePrice(
                resource_type=price_dict["resource_type"],
                unit=price_dict["unit"],
                base_price=price_dict["base_price"],
                currency=price_dict.get("currency", "USD"),
                model=PricingModel(price_dict.get("model", "fixed")),
                tiers=price_dict.get("tiers", []),
                time_rates=price_dict.get("time_rates", {}),
                metadata=price_dict.get("metadata", {}),
            )
            self._prices[rt] = price

        for rid, rule_dict in config.get("rules", {}).items():
            rule = PricingRule(
                rule_id=rule_dict["rule_id"],
                name=rule_dict["name"],
                condition_type=rule_dict["condition_type"],
                condition_value=rule_dict["condition_value"],
                discount_percent=rule_dict.get("discount_percent", 0.0),
                markup_percent=rule_dict.get("markup_percent", 0.0),
                priority=rule_dict.get("priority", 0),
                enabled=rule_dict.get("enabled", True),
                metadata=rule_dict.get("metadata", {}),
            )
            self._rules[rid] = rule

        logger.info(
            f"Imported pricing: {len(self._prices)} prices, "
            f"{len(self._rules)} rules"
        )
