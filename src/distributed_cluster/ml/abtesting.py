"""
A/B Testing - اختبار A/B
=========================

A/B testing framework for ML model experiments.
"""

from __future__ import annotations

import hashlib
import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ABTestStatus(str, Enum):
    """A/B test lifecycle status."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AllocationMethod(str, Enum):
    """Traffic allocation methods."""

    RANDOM = "random"
    HASH = "hash"  # Consistent based on user ID
    STICKY = "sticky"  # Remember user's variant


@dataclass
class Variant:
    """A variant in an A/B test."""

    variant_id: str
    name: str
    model_version_id: str
    weight: float = 0.5  # Traffic weight

    # Metadata
    description: str = ""
    is_control: bool = False

    # Metrics
    requests: int = 0
    conversions: int = 0
    total_value: float = 0.0

    @property
    def conversion_rate(self) -> float:
        if self.requests == 0:
            return 0.0
        return self.conversions / self.requests

    @property
    def avg_value(self) -> float:
        if self.requests == 0:
            return 0.0
        return self.total_value / self.requests

    def record_request(self) -> None:
        self.requests += 1

    def record_conversion(self, value: float = 1.0) -> None:
        self.conversions += 1
        self.total_value += value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "name": self.name,
            "model_version_id": self.model_version_id,
            "weight": self.weight,
            "description": self.description,
            "is_control": self.is_control,
            "requests": self.requests,
            "conversions": self.conversions,
            "total_value": self.total_value,
            "conversion_rate": self.conversion_rate,
            "avg_value": self.avg_value,
        }


@dataclass
class TrafficSplit:
    """Traffic split configuration."""

    variants: List[Variant]
    allocation_method: AllocationMethod = AllocationMethod.HASH

    def get_weights(self) -> List[float]:
        return [v.weight for v in self.variants]

    def normalize_weights(self) -> None:
        """Normalize weights to sum to 1.0."""
        total = sum(v.weight for v in self.variants)
        if total > 0:
            for v in self.variants:
                v.weight /= total


@dataclass
class ABTestConfig:
    """A/B test configuration."""

    name: str
    model_id: str
    variants: List[Variant]

    # Traffic configuration
    traffic_percentage: float = 100.0  # Percentage of traffic to test
    allocation_method: AllocationMethod = AllocationMethod.HASH

    # Targeting
    target_users: Optional[List[str]] = None
    exclude_users: Optional[List[str]] = None
    target_segments: Optional[List[str]] = None

    # Duration
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    max_requests: Optional[int] = None

    # Statistical settings
    confidence_level: float = 0.95
    minimum_detectable_effect: float = 0.05
    required_sample_size: Optional[int] = None

    # Metrics
    primary_metric: str = "conversion_rate"
    secondary_metrics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "model_id": self.model_id,
            "variants": [v.to_dict() for v in self.variants],
            "traffic_percentage": self.traffic_percentage,
            "allocation_method": self.allocation_method.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "confidence_level": self.confidence_level,
            "primary_metric": self.primary_metric,
        }


@dataclass
class ABTestResult:
    """Results of an A/B test."""

    test_id: str
    status: str
    winner: Optional[str] = None
    confidence: float = 0.0

    # Variant results
    variant_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Statistical analysis
    p_value: Optional[float] = None
    is_significant: bool = False
    lift: Optional[float] = None  # Improvement over control

    # Summary
    total_requests: int = 0
    duration_hours: float = 0.0
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "status": self.status,
            "winner": self.winner,
            "confidence": self.confidence,
            "variant_results": self.variant_results,
            "p_value": self.p_value,
            "is_significant": self.is_significant,
            "lift": self.lift,
            "total_requests": self.total_requests,
            "duration_hours": self.duration_hours,
            "recommendation": self.recommendation,
        }


@dataclass
class ABTest:
    """An A/B test instance."""

    test_id: str
    config: ABTestConfig
    status: ABTestStatus = ABTestStatus.DRAFT

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # User assignments
    user_assignments: Dict[str, str] = field(default_factory=dict)  # user_id -> variant_id

    # Results
    result: Optional[ABTestResult] = None

    def start(self) -> None:
        """Start the test."""
        if self.status != ABTestStatus.DRAFT:
            raise RuntimeError(f"Cannot start test in status: {self.status}")

        self.status = ABTestStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        logger.info(f"Started A/B test: {self.test_id}")

    def pause(self) -> None:
        """Pause the test."""
        if self.status != ABTestStatus.RUNNING:
            raise RuntimeError(f"Cannot pause test in status: {self.status}")

        self.status = ABTestStatus.PAUSED
        logger.info(f"Paused A/B test: {self.test_id}")

    def resume(self) -> None:
        """Resume a paused test."""
        if self.status != ABTestStatus.PAUSED:
            raise RuntimeError(f"Cannot resume test in status: {self.status}")

        self.status = ABTestStatus.RUNNING
        logger.info(f"Resumed A/B test: {self.test_id}")

    def complete(self, result: ABTestResult) -> None:
        """Complete the test."""
        self.status = ABTestStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.result = result
        logger.info(f"Completed A/B test: {self.test_id}")

    def cancel(self) -> None:
        """Cancel the test."""
        self.status = ABTestStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc)
        logger.info(f"Cancelled A/B test: {self.test_id}")

    def assign_variant(self, user_id: str) -> Variant:
        """Assign a user to a variant."""
        # Check if already assigned
        if user_id in self.user_assignments:
            variant_id = self.user_assignments[user_id]
            for v in self.config.variants:
                if v.variant_id == variant_id:
                    return v

        # Check targeting
        if self.config.exclude_users and user_id in self.config.exclude_users:
            return self._get_control_variant()

        if self.config.target_users and user_id not in self.config.target_users:
            return self._get_control_variant()

        # Check traffic percentage
        if random.random() * 100 > self.config.traffic_percentage:
            return self._get_control_variant()

        # Allocate based on method
        if self.config.allocation_method == AllocationMethod.HASH:
            variant = self._hash_allocate(user_id)
        elif self.config.allocation_method == AllocationMethod.RANDOM:
            variant = self._random_allocate()
        else:
            variant = self._random_allocate()

        # Store assignment for sticky allocation
        self.user_assignments[user_id] = variant.variant_id

        return variant

    def _hash_allocate(self, user_id: str) -> Variant:
        """Allocate using consistent hashing."""
        hash_input = f"{self.test_id}:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        normalized = (hash_value % 10000) / 10000

        cumulative = 0.0
        for variant in self.config.variants:
            cumulative += variant.weight
            if normalized <= cumulative:
                return variant

        return self.config.variants[-1]

    def _random_allocate(self) -> Variant:
        """Allocate randomly based on weights."""
        weights = [v.weight for v in self.config.variants]
        return random.choices(self.config.variants, weights=weights, k=1)[0]

    def _get_control_variant(self) -> Variant:
        """Get the control variant."""
        for v in self.config.variants:
            if v.is_control:
                return v
        return self.config.variants[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result.to_dict() if self.result else None,
        }


class StatisticalAnalyzer:
    """Statistical analysis for A/B tests."""

    @staticmethod
    def calculate_sample_size(
        baseline_rate: float,
        minimum_detectable_effect: float,
        confidence_level: float = 0.95,
        power: float = 0.8,
    ) -> int:
        """Calculate required sample size per variant."""
        from math import ceil

        # Z-scores
        z_alpha = 1.96 if confidence_level == 0.95 else 2.576
        z_beta = 0.84 if power == 0.8 else 1.28

        p1 = baseline_rate
        p2 = baseline_rate * (1 + minimum_detectable_effect)
        p_avg = (p1 + p2) / 2

        n = 2 * p_avg * (1 - p_avg) * ((z_alpha + z_beta) ** 2) / ((p2 - p1) ** 2)

        return ceil(n)

    @staticmethod
    def calculate_z_test(
        conversions_a: int,
        samples_a: int,
        conversions_b: int,
        samples_b: int,
    ) -> Tuple[float, float]:
        """Calculate z-test for two proportions."""
        from math import sqrt

        if samples_a == 0 or samples_b == 0:
            return 0.0, 1.0

        p_a = conversions_a / samples_a
        p_b = conversions_b / samples_b
        p_pool = (conversions_a + conversions_b) / (samples_a + samples_b)

        se = sqrt(p_pool * (1 - p_pool) * (1 / samples_a + 1 / samples_b))

        if se == 0:
            return 0.0, 1.0

        z = (p_b - p_a) / se

        # Approximate p-value (two-tailed)
        p_value = 2 * (1 - StatisticalAnalyzer._norm_cdf(abs(z)))

        return z, p_value

    @staticmethod
    def _norm_cdf(x: float) -> float:
        """Approximate normal CDF."""
        from math import erf, sqrt

        return (1 + erf(x / sqrt(2))) / 2

    @staticmethod
    def analyze_test(test: ABTest) -> ABTestResult:
        """Analyze an A/B test and determine winner."""
        variants = test.config.variants
        control = test._get_control_variant()

        variant_results = {}
        for v in variants:
            variant_results[v.variant_id] = {
                "name": v.name,
                "requests": v.requests,
                "conversions": v.conversions,
                "conversion_rate": v.conversion_rate,
                "is_control": v.is_control,
            }

        # Find best performing variant
        treatment_variants = [v for v in variants if not v.is_control]
        if not treatment_variants:
            treatment_variants = variants[1:] if len(variants) > 1 else []

        winner = None
        is_significant = False
        p_value = None
        lift = None
        confidence = 0.0

        if treatment_variants and control.requests > 0:
            best_variant = max(treatment_variants, key=lambda v: v.conversion_rate)

            z, p = StatisticalAnalyzer.calculate_z_test(
                control.conversions, control.requests, best_variant.conversions, best_variant.requests
            )

            p_value = p
            is_significant = p < (1 - test.config.confidence_level)
            confidence = 1 - p

            if control.conversion_rate > 0:
                lift = (best_variant.conversion_rate - control.conversion_rate) / control.conversion_rate

            if is_significant and best_variant.conversion_rate > control.conversion_rate:
                winner = best_variant.variant_id

        # Calculate duration
        duration_hours = 0.0
        if test.started_at:
            end_time = test.completed_at or datetime.now(timezone.utc)
            duration_hours = (end_time - test.started_at).total_seconds() / 3600

        # Generate recommendation
        if winner:
            recommendation = f"Deploy variant '{variant_results[winner]['name']}' with {lift*100:.1f}% improvement"
        elif is_significant:
            recommendation = "Control variant performs better. Keep current model."
        else:
            recommendation = "No significant difference detected. Continue testing or increase sample size."

        return ABTestResult(
            test_id=test.test_id,
            status=test.status.value,
            winner=winner,
            confidence=confidence,
            variant_results=variant_results,
            p_value=p_value,
            is_significant=is_significant,
            lift=lift,
            total_requests=sum(v.requests for v in variants),
            duration_hours=duration_hours,
            recommendation=recommendation,
        )


class ABTestManager:
    """
    A/B Test Manager - مدير اختبارات A/B.

    Manages A/B tests for ML model experimentation.

    Example:
        manager = ABTestManager()

        # Create a test
        config = ABTestConfig(
            name="new-model-test",
            model_id="my-classifier",
            variants=[
                Variant(
                    variant_id="control",
                    name="Current Model",
                    model_version_id="v1",
                    weight=0.5,
                    is_control=True
                ),
                Variant(
                    variant_id="treatment",
                    name="New Model",
                    model_version_id="v2",
                    weight=0.5
                ),
            ]
        )
        test = manager.create_test(config)

        # Start the test
        manager.start_test(test.test_id)

        # Get variant for a user
        variant = manager.get_variant(test.test_id, user_id="user-123")

        # Record conversion
        manager.record_conversion(test.test_id, user_id="user-123", value=10.0)

        # Analyze results
        result = manager.analyze_test(test.test_id)
    """

    def __init__(self):
        self._tests: Dict[str, ABTest] = {}
        self._analyzer = StatisticalAnalyzer()

    def create_test(self, config: ABTestConfig) -> ABTest:
        """Create a new A/B test."""
        # Normalize weights
        total_weight = sum(v.weight for v in config.variants)
        if total_weight > 0:
            for v in config.variants:
                v.weight /= total_weight

        test = ABTest(
            test_id=str(uuid.uuid4()),
            config=config,
        )
        self._tests[test.test_id] = test

        logger.info(f"Created A/B test: {config.name}")
        return test

    def get_test(self, test_id: str) -> Optional[ABTest]:
        """Get a test by ID."""
        return self._tests.get(test_id)

    def list_tests(
        self,
        status: Optional[ABTestStatus] = None,
        model_id: Optional[str] = None,
    ) -> List[ABTest]:
        """List all tests."""
        tests = list(self._tests.values())

        if status:
            tests = [t for t in tests if t.status == status]
        if model_id:
            tests = [t for t in tests if t.config.model_id == model_id]

        return tests

    def start_test(self, test_id: str) -> None:
        """Start a test."""
        test = self._tests.get(test_id)
        if not test:
            raise ValueError(f"Test not found: {test_id}")
        test.start()

    def pause_test(self, test_id: str) -> None:
        """Pause a test."""
        test = self._tests.get(test_id)
        if not test:
            raise ValueError(f"Test not found: {test_id}")
        test.pause()

    def resume_test(self, test_id: str) -> None:
        """Resume a test."""
        test = self._tests.get(test_id)
        if not test:
            raise ValueError(f"Test not found: {test_id}")
        test.resume()

    def complete_test(self, test_id: str) -> ABTestResult:
        """Complete a test and return results."""
        test = self._tests.get(test_id)
        if not test:
            raise ValueError(f"Test not found: {test_id}")

        result = self._analyzer.analyze_test(test)
        test.complete(result)
        return result

    def cancel_test(self, test_id: str) -> None:
        """Cancel a test."""
        test = self._tests.get(test_id)
        if not test:
            raise ValueError(f"Test not found: {test_id}")
        test.cancel()

    def delete_test(self, test_id: str) -> None:
        """Delete a test."""
        if test_id in self._tests:
            del self._tests[test_id]

    def get_variant(
        self,
        test_id: str,
        user_id: str,
    ) -> Tuple[Variant, str]:
        """Get the variant for a user."""
        test = self._tests.get(test_id)
        if not test:
            raise ValueError(f"Test not found: {test_id}")

        if test.status != ABTestStatus.RUNNING:
            # Return control if test not running
            variant = test._get_control_variant()
        else:
            variant = test.assign_variant(user_id)
            variant.record_request()

        return variant, variant.model_version_id

    def record_conversion(
        self,
        test_id: str,
        user_id: str,
        value: float = 1.0,
    ) -> None:
        """Record a conversion for a user."""
        test = self._tests.get(test_id)
        if not test:
            raise ValueError(f"Test not found: {test_id}")

        variant_id = test.user_assignments.get(user_id)
        if variant_id:
            for v in test.config.variants:
                if v.variant_id == variant_id:
                    v.record_conversion(value)
                    break

    def analyze_test(self, test_id: str) -> ABTestResult:
        """Analyze a test without completing it."""
        test = self._tests.get(test_id)
        if not test:
            raise ValueError(f"Test not found: {test_id}")

        return self._analyzer.analyze_test(test)

    def get_required_sample_size(
        self,
        baseline_rate: float,
        minimum_detectable_effect: float = 0.05,
        confidence_level: float = 0.95,
    ) -> int:
        """Calculate required sample size for a test."""
        return self._analyzer.calculate_sample_size(
            baseline_rate,
            minimum_detectable_effect,
            confidence_level,
        )
