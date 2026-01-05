# -*- coding: utf-8 -*-
"""
SLA Tracker for NebulaCompute.

Tracks SLA violations and generates compliance reports.

متتبع انتهاكات SLA وتقارير الامتثال.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .monitor import SLADefinition, SLAEvaluation

logger = logging.getLogger(__name__)


class ViolationSeverity(str, Enum):
    """Violation severity level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SLAViolation:
    """
    SLA violation record.

    سجل انتهاك SLA.
    """

    violation_id: str
    sla_id: str
    sla_name: str
    metric_name: str
    expected_value: float
    actual_value: float
    severity: ViolationSeverity
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    impact: Optional[str] = None
    root_cause: Optional[str] = None
    resolution: Optional[str] = None
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Check if violation is still active."""
        return self.ended_at is None

    @property
    def current_duration(self) -> float:
        """Get current duration in seconds."""
        if self.ended_at:
            return self.duration_seconds
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "violation_id": self.violation_id,
            "sla_id": self.sla_id,
            "sla_name": self.sla_name,
            "metric_name": self.metric_name,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "severity": self.severity.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.current_duration,
            "is_active": self.is_active,
            "impact": self.impact,
            "root_cause": self.root_cause,
            "resolution": self.resolution,
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "metadata": self.metadata,
        }


@dataclass
class ComplianceReport:
    """
    SLA compliance report.

    تقرير امتثال SLA.
    """

    report_id: str
    period_start: datetime
    period_end: datetime
    sla_id: Optional[str] = None  # None = all SLAs
    sla_name: Optional[str] = None

    # Metrics
    total_time_seconds: float = 0.0
    compliant_time_seconds: float = 0.0
    violated_time_seconds: float = 0.0
    compliance_percentage: float = 100.0

    # Violations
    total_violations: int = 0
    violations_by_severity: Dict[str, int] = field(default_factory=dict)
    violations_by_metric: Dict[str, int] = field(default_factory=dict)
    mean_time_to_resolve: float = 0.0

    # Trends
    trend_vs_previous: float = 0.0  # Percentage change

    generated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "report_id": self.report_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "sla_id": self.sla_id,
            "sla_name": self.sla_name,
            "total_time_seconds": self.total_time_seconds,
            "compliant_time_seconds": self.compliant_time_seconds,
            "violated_time_seconds": self.violated_time_seconds,
            "compliance_percentage": self.compliance_percentage,
            "total_violations": self.total_violations,
            "violations_by_severity": self.violations_by_severity,
            "violations_by_metric": self.violations_by_metric,
            "mean_time_to_resolve": self.mean_time_to_resolve,
            "trend_vs_previous": self.trend_vs_previous,
            "generated_at": self.generated_at.isoformat(),
            "metadata": self.metadata,
        }


class SLATracker:
    """
    Tracks SLA violations and generates reports.

    متتبع انتهاكات SLA ومولد التقارير.

    Features:
    - Violation tracking
    - Automatic severity classification
    - Compliance reporting
    - Trend analysis
    - Export capabilities
    """

    def __init__(
        self,
        retention_days: int = 365,
        severity_thresholds: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize SLA Tracker.

        Args:
            retention_days: How long to keep violation records
            severity_thresholds: Custom severity thresholds
        """
        self.retention_days = retention_days
        self.severity_thresholds = severity_thresholds or {
            "critical": 0.5,  # < 50% of target
            "high": 0.7,  # < 70% of target
            "medium": 0.9,  # < 90% of target
            "low": 1.0,  # < 100% of target
        }

        # Storage
        self._violations: Dict[str, SLAViolation] = {}
        self._active_violations: Dict[str, str] = {}  # sla_id:metric -> violation_id
        self._reports: Dict[str, ComplianceReport] = {}
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "total_violations": 0,
            "active_violations": 0,
            "resolved_violations": 0,
            "reports_generated": 0,
        }

    async def record_violation(
        self,
        sla: SLADefinition,
        evaluation: SLAEvaluation,
    ) -> List[SLAViolation]:
        """
        Record violations from an evaluation.

        تسجيل الانتهاكات من التقييم.
        """
        violations = []

        for metric_name, result in evaluation.metric_results.items():
            if not result["passed"]:
                violation = await self._create_or_update_violation(sla, metric_name, result)
                if violation:
                    violations.append(violation)

        # Close violations that are now passing
        await self._close_resolved_violations(sla.sla_id, evaluation)

        return violations

    async def _create_or_update_violation(
        self,
        sla: SLADefinition,
        metric_name: str,
        result: Dict[str, Any],
    ) -> Optional[SLAViolation]:
        """Create or update a violation."""
        import uuid

        key = f"{sla.sla_id}:{metric_name}"

        async with self._lock:
            # Check if violation already exists
            existing_id = self._active_violations.get(key)
            if existing_id:
                # Update existing violation
                violation = self._violations.get(existing_id)
                if violation:
                    violation.actual_value = result["current_value"]
                    return None  # Return None for existing violation

            # Create new violation
            severity = self._calculate_severity(
                result["current_value"],
                result["target_value"],
            )

            violation = SLAViolation(
                violation_id=str(uuid.uuid4()),
                sla_id=sla.sla_id,
                sla_name=sla.name,
                metric_name=metric_name,
                expected_value=result["target_value"],
                actual_value=result["current_value"],
                severity=severity,
                started_at=datetime.now(timezone.utc),
            )

            self._violations[violation.violation_id] = violation
            self._active_violations[key] = violation.violation_id
            self._stats["total_violations"] += 1
            self._stats["active_violations"] += 1

            logger.warning(
                f"SLA Violation: {sla.name} - {metric_name} "
                f"(expected: {result['target_value']}, "
                f"actual: {result['current_value']}, "
                f"severity: {severity.value})"
            )

            return violation

    async def _close_resolved_violations(
        self,
        sla_id: str,
        evaluation: SLAEvaluation,
    ) -> None:
        """Close violations that are now resolved."""
        async with self._lock:
            keys_to_remove = []

            for key, violation_id in self._active_violations.items():
                if not key.startswith(f"{sla_id}:"):
                    continue

                metric_name = key.split(":", 1)[1]
                result = evaluation.metric_results.get(metric_name)

                if result and result["passed"]:
                    # Violation resolved
                    violation = self._violations.get(violation_id)
                    if violation:
                        violation.ended_at = datetime.now(timezone.utc)
                        violation.duration_seconds = (violation.ended_at - violation.started_at).total_seconds()

                        self._stats["active_violations"] -= 1
                        self._stats["resolved_violations"] += 1

                        logger.info(
                            f"SLA Violation resolved: {violation.sla_name} - "
                            f"{violation.metric_name} "
                            f"(duration: {violation.duration_seconds:.0f}s)"
                        )

                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._active_violations[key]

    def _calculate_severity(
        self,
        actual: float,
        target: float,
    ) -> ViolationSeverity:
        """Calculate violation severity."""
        if target == 0:
            return ViolationSeverity.CRITICAL

        ratio = actual / target

        if ratio < self.severity_thresholds["critical"]:
            return ViolationSeverity.CRITICAL
        elif ratio < self.severity_thresholds["high"]:
            return ViolationSeverity.HIGH
        elif ratio < self.severity_thresholds["medium"]:
            return ViolationSeverity.MEDIUM
        else:
            return ViolationSeverity.LOW

    async def acknowledge_violation(
        self,
        violation_id: str,
        acknowledged_by: str,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Acknowledge a violation.

        الاعتراف بالانتهاك.
        """
        async with self._lock:
            violation = self._violations.get(violation_id)
            if not violation:
                return False

            violation.acknowledged = True
            violation.acknowledged_by = acknowledged_by
            violation.acknowledged_at = datetime.now(timezone.utc)
            if notes:
                violation.metadata["acknowledgment_notes"] = notes

            return True

    async def set_root_cause(
        self,
        violation_id: str,
        root_cause: str,
        resolution: Optional[str] = None,
    ) -> bool:
        """Set root cause for a violation."""
        async with self._lock:
            violation = self._violations.get(violation_id)
            if not violation:
                return False

            violation.root_cause = root_cause
            if resolution:
                violation.resolution = resolution

            return True

    async def get_violation(
        self,
        violation_id: str,
    ) -> Optional[SLAViolation]:
        """Get violation by ID."""
        return self._violations.get(violation_id)

    async def get_active_violations(
        self,
        sla_id: Optional[str] = None,
    ) -> List[SLAViolation]:
        """Get active violations."""
        violations = [self._violations[vid] for vid in self._active_violations.values()]

        if sla_id:
            violations = [v for v in violations if v.sla_id == sla_id]

        return violations

    async def get_violations(
        self,
        sla_id: Optional[str] = None,
        severity: Optional[ViolationSeverity] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SLAViolation]:
        """Get violations with optional filtering."""
        violations = list(self._violations.values())

        if sla_id:
            violations = [v for v in violations if v.sla_id == sla_id]

        if severity:
            violations = [v for v in violations if v.severity == severity]

        if start_date:
            violations = [v for v in violations if v.started_at >= start_date]

        if end_date:
            violations = [v for v in violations if v.started_at <= end_date]

        # Sort by start time descending
        violations.sort(key=lambda v: v.started_at, reverse=True)

        return violations[:limit]

    async def generate_report(
        self,
        period_start: datetime,
        period_end: datetime,
        sla_id: Optional[str] = None,
    ) -> ComplianceReport:
        """
        Generate compliance report.

        إنشاء تقرير الامتثال.
        """
        import uuid

        # Get violations for period
        violations = await self.get_violations(
            sla_id=sla_id,
            start_date=period_start,
            end_date=period_end,
            limit=10000,
        )

        # Calculate metrics
        total_time = (period_end - period_start).total_seconds()
        violated_time = sum(v.current_duration for v in violations)
        compliant_time = total_time - violated_time

        # Violations by severity
        by_severity = {}
        for v in violations:
            sev = v.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

        # Violations by metric
        by_metric = {}
        for v in violations:
            by_metric[v.metric_name] = by_metric.get(v.metric_name, 0) + 1

        # Mean time to resolve
        resolved = [v for v in violations if v.ended_at]
        mttr = 0.0
        if resolved:
            mttr = sum(v.duration_seconds for v in resolved) / len(resolved)

        # Calculate compliance percentage
        compliance = (compliant_time / total_time * 100) if total_time > 0 else 100.0

        report = ComplianceReport(
            report_id=str(uuid.uuid4()),
            period_start=period_start,
            period_end=period_end,
            sla_id=sla_id,
            total_time_seconds=total_time,
            compliant_time_seconds=compliant_time,
            violated_time_seconds=violated_time,
            compliance_percentage=compliance,
            total_violations=len(violations),
            violations_by_severity=by_severity,
            violations_by_metric=by_metric,
            mean_time_to_resolve=mttr,
        )

        async with self._lock:
            self._reports[report.report_id] = report
            self._stats["reports_generated"] += 1

        logger.info(f"Generated compliance report: {compliance:.1f}% compliance, " f"{len(violations)} violations")

        return report

    async def generate_weekly_report(
        self,
        sla_id: Optional[str] = None,
    ) -> ComplianceReport:
        """Generate weekly compliance report."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        return await self.generate_report(start, end, sla_id)

    async def generate_monthly_report(
        self,
        sla_id: Optional[str] = None,
    ) -> ComplianceReport:
        """Generate monthly compliance report."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=30)
        return await self.generate_report(start, end, sla_id)

    async def get_report(self, report_id: str) -> Optional[ComplianceReport]:
        """Get report by ID."""
        return self._reports.get(report_id)

    async def list_reports(self, limit: int = 50) -> List[ComplianceReport]:
        """List recent reports."""
        reports = list(self._reports.values())
        reports.sort(key=lambda r: r.generated_at, reverse=True)
        return reports[:limit]

    async def cleanup_old_data(self) -> int:
        """Clean up old violation records."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        removed = 0

        async with self._lock:
            to_remove = [vid for vid, v in self._violations.items() if v.started_at < cutoff and not v.is_active]

            for vid in to_remove:
                del self._violations[vid]
                removed += 1

        if removed:
            logger.info(f"Cleaned up {removed} old violation records")

        return removed

    async def get_statistics(self) -> Dict[str, Any]:
        """Get tracker statistics."""
        return {
            **self._stats,
            "stored_violations": len(self._violations),
            "stored_reports": len(self._reports),
            "retention_days": self.retention_days,
        }

    async def shutdown(self) -> None:
        """Shutdown tracker."""
        logger.info("SLA Tracker shutdown complete")
