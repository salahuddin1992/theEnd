# -*- coding: utf-8 -*-
"""
Cluster Health Aggregator - مجمع صحة العنقود
=============================================

Unified health monitoring for the entire cluster:
- Aggregates health from all components
- Calculates cluster health score
- Smart alerting with severity levels
- Health history and trend analysis
- Dependency checking

مراقبة صحة موحدة للعنقود بالكامل:
- تجميع الصحة من جميع المكونات
- حساب درجة صحة العنقود
- تنبيهات ذكية مع مستويات الخطورة
- سجل الصحة وتحليل الاتجاهات
- فحص التبعيات
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"


class ComponentType(str, Enum):
    """Types of cluster components."""

    MASTER = "master"
    WORKER = "worker"
    SCHEDULER = "scheduler"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    STORAGE = "storage"
    NETWORK = "network"
    GATEWAY = "gateway"
    MONITOR = "monitor"
    EXTERNAL = "external"


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class HealthCheck:
    """Result of a single health check."""

    check_id: str
    name: str
    status: HealthStatus
    message: str
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class ComponentHealth:
    """Health status of a cluster component."""

    component_id: str
    component_type: ComponentType
    name: str
    status: HealthStatus
    checks: List[HealthCheck] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    uptime_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: Optional[str] = None
    host: Optional[str] = None

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY

    @property
    def check_pass_rate(self) -> float:
        if not self.checks:
            return 1.0
        passed = sum(1 for c in self.checks if c.status == HealthStatus.HEALTHY)
        return passed / len(self.checks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_type": self.component_type.value,
            "name": self.name,
            "status": self.status.value,
            "checks": [c.to_dict() for c in self.checks],
            "dependencies": self.dependencies,
            "last_seen": self.last_seen.isoformat(),
            "uptime_seconds": round(self.uptime_seconds, 0),
            "check_pass_rate": round(self.check_pass_rate, 4),
            "version": self.version,
            "host": self.host,
        }


@dataclass
class HealthAlert:
    """Health-related alert."""

    alert_id: str
    severity: AlertSeverity
    component_id: str
    title: str
    message: str
    triggered_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    acknowledged: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.resolved_at is None

    @property
    def duration_seconds(self) -> float:
        end = self.resolved_at or datetime.now(timezone.utc)
        return (end - self.triggered_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "severity": self.severity.value,
            "component_id": self.component_id,
            "title": self.title,
            "message": self.message,
            "triggered_at": self.triggered_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "is_active": self.is_active,
            "acknowledged": self.acknowledged,
            "duration_seconds": round(self.duration_seconds, 0),
        }


@dataclass
class ClusterHealthSummary:
    """Summary of cluster health."""

    overall_status: HealthStatus
    health_score: float  # 0.0 - 1.0
    total_components: int
    healthy_components: int
    degraded_components: int
    unhealthy_components: int
    unknown_components: int
    active_alerts: int
    critical_alerts: int
    components_by_type: Dict[str, Dict[str, int]] = field(default_factory=dict)
    check_timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "health_score": round(self.health_score, 4),
            "total_components": self.total_components,
            "healthy_components": self.healthy_components,
            "degraded_components": self.degraded_components,
            "unhealthy_components": self.unhealthy_components,
            "unknown_components": self.unknown_components,
            "active_alerts": self.active_alerts,
            "critical_alerts": self.critical_alerts,
            "components_by_type": self.components_by_type,
            "check_timestamp": self.check_timestamp.isoformat(),
        }


@dataclass
class HealthHistoryEntry:
    """Historical health record."""

    timestamp: datetime
    health_score: float
    overall_status: HealthStatus
    component_count: int
    unhealthy_count: int
    alert_count: int


class ClusterHealthAggregator:
    """
    Unified cluster health monitoring and aggregation.

    Collects health data from all components and provides:
    - Aggregated health status
    - Health score calculation
    - Alert management
    - Trend analysis
    - Dependency tracking

    Usage:
        aggregator = ClusterHealthAggregator()

        # Register components
        aggregator.register_component(ComponentHealth(...))

        # Update health
        await aggregator.update_component_health(component_id, checks)

        # Get summary
        summary = aggregator.get_cluster_summary()

        # Get alerts
        alerts = aggregator.get_active_alerts()
    """

    # Weight factors for health score calculation
    STATUS_WEIGHTS = {
        HealthStatus.HEALTHY: 1.0,
        HealthStatus.DEGRADED: 0.5,
        HealthStatus.UNHEALTHY: 0.0,
        HealthStatus.UNKNOWN: 0.25,
        HealthStatus.MAINTENANCE: 0.75,
    }

    # Component type importance weights
    TYPE_WEIGHTS = {
        ComponentType.MASTER: 2.0,
        ComponentType.DATABASE: 1.8,
        ComponentType.SCHEDULER: 1.5,
        ComponentType.WORKER: 1.0,
        ComponentType.CACHE: 1.2,
        ComponentType.QUEUE: 1.3,
        ComponentType.STORAGE: 1.4,
        ComponentType.NETWORK: 1.3,
        ComponentType.GATEWAY: 1.2,
        ComponentType.MONITOR: 0.8,
        ComponentType.EXTERNAL: 0.6,
    }

    def __init__(
        self,
        stale_threshold_seconds: float = 60.0,
        history_retention_hours: int = 24,
        alert_callbacks: Optional[List[Callable[[HealthAlert], None]]] = None,
        persist_path: Optional[str] = None,
    ):
        """
        Initialize the health aggregator.

        Args:
            stale_threshold_seconds: Seconds before a component is considered stale
            history_retention_hours: Hours to retain health history
            alert_callbacks: Callbacks to invoke on new alerts
            persist_path: Path to persist health data
        """
        self.stale_threshold_seconds = stale_threshold_seconds
        self.history_retention_hours = history_retention_hours
        self.alert_callbacks = alert_callbacks or []
        self.persist_path = persist_path

        # Components
        self._components: Dict[str, ComponentHealth] = {}
        self._component_checks: Dict[str, List[Callable[[], asyncio.coroutine]]] = {}

        # Alerts
        self._alerts: Dict[str, HealthAlert] = {}
        self._alert_counter = 0

        # History
        self._history: List[HealthHistoryEntry] = []

        # Dependencies
        self._dependency_graph: Dict[str, Set[str]] = defaultdict(set)

        # State
        self._lock = asyncio.Lock()
        self._last_check = datetime.now(timezone.utc)

        # Load persisted data
        if persist_path:
            self._load_state()

    def _load_state(self) -> None:
        """Load persisted state."""
        if not self.persist_path:
            return

        path = Path(self.persist_path)
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    # Load alert counter
                    self._alert_counter = data.get("alert_counter", 0)
                    logger.info("Loaded health aggregator state")
            except Exception as e:
                logger.error(f"Failed to load health state: {e}")

    def _save_state(self) -> None:
        """Save state to disk."""
        if not self.persist_path:
            return

        try:
            path = Path(self.persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "alert_counter": self._alert_counter,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }

            with open(path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"Failed to save health state: {e}")

    def register_component(
        self,
        component: ComponentHealth,
        health_checks: Optional[List[Callable[[], asyncio.coroutine]]] = None,
    ) -> None:
        """
        Register a component for health monitoring.

        Args:
            component: Component health information
            health_checks: Optional list of health check coroutines
        """
        self._components[component.component_id] = component

        if health_checks:
            self._component_checks[component.component_id] = health_checks

        # Build dependency graph
        for dep_id in component.dependencies:
            self._dependency_graph[dep_id].add(component.component_id)

        logger.info(f"Registered component: {component.name} ({component.component_id})")

    def unregister_component(self, component_id: str) -> None:
        """Unregister a component."""
        self._components.pop(component_id, None)
        self._component_checks.pop(component_id, None)

        # Remove from dependency graph
        self._dependency_graph.pop(component_id, None)
        for dependents in self._dependency_graph.values():
            dependents.discard(component_id)

    async def update_component_health(
        self,
        component_id: str,
        checks: List[HealthCheck],
        uptime_seconds: Optional[float] = None,
    ) -> ComponentHealth:
        """
        Update health status for a component.

        Args:
            component_id: ID of the component
            checks: List of health check results
            uptime_seconds: Optional updated uptime

        Returns:
            Updated component health
        """
        async with self._lock:
            if component_id not in self._components:
                raise ValueError(f"Unknown component: {component_id}")

            component = self._components[component_id]
            old_status = component.status

            # Update checks and status
            component.checks = checks
            component.last_seen = datetime.now(timezone.utc)

            if uptime_seconds is not None:
                component.uptime_seconds = uptime_seconds

            # Calculate new status based on checks
            component.status = self._calculate_component_status(checks)

            # Check for status changes and generate alerts
            await self._check_status_change(component, old_status)

            return component

    def _calculate_component_status(self, checks: List[HealthCheck]) -> HealthStatus:
        """Calculate component status from health checks."""
        if not checks:
            return HealthStatus.UNKNOWN

        statuses = [c.status for c in checks]

        # Any unhealthy check = unhealthy
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY

        # Any degraded check = degraded
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED

        # Any unknown check = degraded
        if HealthStatus.UNKNOWN in statuses:
            return HealthStatus.DEGRADED

        # All healthy
        return HealthStatus.HEALTHY

    async def _check_status_change(
        self,
        component: ComponentHealth,
        old_status: HealthStatus,
    ) -> None:
        """Check for status changes and generate alerts."""
        new_status = component.status

        if old_status == new_status:
            return

        # Status degraded
        if new_status in (HealthStatus.DEGRADED, HealthStatus.UNHEALTHY):
            if old_status == HealthStatus.HEALTHY:
                # New problem
                severity = AlertSeverity.CRITICAL if new_status == HealthStatus.UNHEALTHY else AlertSeverity.WARNING

                await self._create_alert(
                    severity=severity,
                    component_id=component.component_id,
                    title=f"{component.name} is {new_status.value}",
                    message=self._build_alert_message(component),
                )

        # Status recovered
        elif new_status == HealthStatus.HEALTHY:
            if old_status in (HealthStatus.DEGRADED, HealthStatus.UNHEALTHY):
                # Resolve active alerts for this component
                for alert_id, alert in self._alerts.items():
                    if alert.component_id == component.component_id and alert.is_active:
                        alert.resolved_at = datetime.now(timezone.utc)

    def _build_alert_message(self, component: ComponentHealth) -> str:
        """Build detailed alert message."""
        failed_checks = [c for c in component.checks if c.status != HealthStatus.HEALTHY]

        if not failed_checks:
            return f"Component {component.name} status changed"

        messages = [f"{c.name}: {c.message}" for c in failed_checks[:3]]
        result = "; ".join(messages)

        if len(failed_checks) > 3:
            result += f" (+{len(failed_checks) - 3} more)"

        return result

    async def _create_alert(
        self,
        severity: AlertSeverity,
        component_id: str,
        title: str,
        message: str,
    ) -> HealthAlert:
        """Create and notify about a new alert."""
        self._alert_counter += 1

        alert = HealthAlert(
            alert_id=f"alert-{self._alert_counter:06d}",
            severity=severity,
            component_id=component_id,
            title=title,
            message=message,
        )

        self._alerts[alert.alert_id] = alert

        # Notify callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

        logger.warning(f"Health alert: [{severity.value}] {title}")

        return alert

    async def run_health_checks(self) -> None:
        """Run all registered health checks."""
        for component_id, checks in self._component_checks.items():
            check_results = []

            for i, check_func in enumerate(checks):
                start_time = datetime.now(timezone.utc)
                try:
                    result = await check_func()
                    duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

                    if isinstance(result, HealthCheck):
                        result.duration_ms = duration_ms
                        check_results.append(result)
                    else:
                        check_results.append(
                            HealthCheck(
                                check_id=f"{component_id}-check-{i}",
                                name=f"Check {i}",
                                status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                                message="OK" if result else "Failed",
                                duration_ms=duration_ms,
                            )
                        )

                except Exception as e:
                    duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    check_results.append(
                        HealthCheck(
                            check_id=f"{component_id}-check-{i}",
                            name=f"Check {i}",
                            status=HealthStatus.UNHEALTHY,
                            message=str(e),
                            duration_ms=duration_ms,
                        )
                    )

            if check_results:
                await self.update_component_health(component_id, check_results)

        # Mark stale components
        await self._check_stale_components()

        # Record history
        self._record_history()

        self._last_check = datetime.now(timezone.utc)

    async def _check_stale_components(self) -> None:
        """Check for and mark stale components."""
        now = datetime.now(timezone.utc)
        stale_threshold = timedelta(seconds=self.stale_threshold_seconds)

        for component in self._components.values():
            if now - component.last_seen > stale_threshold:
                if component.status != HealthStatus.UNKNOWN:
                    old_status = component.status
                    component.status = HealthStatus.UNKNOWN

                    if old_status == HealthStatus.HEALTHY:
                        await self._create_alert(
                            severity=AlertSeverity.WARNING,
                            component_id=component.component_id,
                            title=f"{component.name} is unresponsive",
                            message=f"No health update for {self.stale_threshold_seconds}s",
                        )

    def _record_history(self) -> None:
        """Record current health to history."""
        summary = self.get_cluster_summary()

        self._history.append(
            HealthHistoryEntry(
                timestamp=datetime.now(timezone.utc),
                health_score=summary.health_score,
                overall_status=summary.overall_status,
                component_count=summary.total_components,
                unhealthy_count=summary.unhealthy_components,
                alert_count=summary.active_alerts,
            )
        )

        # Trim old history
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.history_retention_hours)
        self._history = [h for h in self._history if h.timestamp > cutoff]

    def get_cluster_summary(self) -> ClusterHealthSummary:
        """
        Get aggregated cluster health summary.

        Returns:
            ClusterHealthSummary with overall status and metrics
        """
        if not self._components:
            return ClusterHealthSummary(
                overall_status=HealthStatus.UNKNOWN,
                health_score=0.0,
                total_components=0,
                healthy_components=0,
                degraded_components=0,
                unhealthy_components=0,
                unknown_components=0,
                active_alerts=0,
                critical_alerts=0,
            )

        # Count by status
        status_counts = defaultdict(int)
        for component in self._components.values():
            status_counts[component.status] += 1

        # Count by type
        type_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for component in self._components.values():
            type_counts[component.component_type.value][component.status.value] += 1

        # Calculate health score
        health_score = self._calculate_health_score()

        # Determine overall status
        if status_counts[HealthStatus.UNHEALTHY] > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif status_counts[HealthStatus.DEGRADED] > 0:
            overall_status = HealthStatus.DEGRADED
        elif status_counts[HealthStatus.UNKNOWN] > len(self._components) // 2:
            overall_status = HealthStatus.UNKNOWN
        else:
            overall_status = HealthStatus.HEALTHY

        # Count alerts
        active_alerts = sum(1 for a in self._alerts.values() if a.is_active)
        critical_alerts = sum(1 for a in self._alerts.values() if a.is_active and a.severity == AlertSeverity.CRITICAL)

        return ClusterHealthSummary(
            overall_status=overall_status,
            health_score=health_score,
            total_components=len(self._components),
            healthy_components=status_counts[HealthStatus.HEALTHY],
            degraded_components=status_counts[HealthStatus.DEGRADED],
            unhealthy_components=status_counts[HealthStatus.UNHEALTHY],
            unknown_components=status_counts[HealthStatus.UNKNOWN],
            active_alerts=active_alerts,
            critical_alerts=critical_alerts,
            components_by_type={k: dict(v) for k, v in type_counts.items()},
        )

    def _calculate_health_score(self) -> float:
        """Calculate weighted health score (0.0 - 1.0)."""
        if not self._components:
            return 0.0

        total_weight = 0.0
        weighted_score = 0.0

        for component in self._components.values():
            type_weight = self.TYPE_WEIGHTS.get(component.component_type, 1.0)
            status_score = self.STATUS_WEIGHTS.get(component.status, 0.0)

            # Also consider check pass rate
            check_factor = component.check_pass_rate

            component_score = status_score * check_factor
            weighted_score += component_score * type_weight
            total_weight += type_weight

        return weighted_score / total_weight if total_weight > 0 else 0.0

    def get_component_health(self, component_id: str) -> Optional[ComponentHealth]:
        """Get health for a specific component."""
        return self._components.get(component_id)

    def get_all_components(self) -> List[ComponentHealth]:
        """Get health for all components."""
        return list(self._components.values())

    def get_components_by_type(self, component_type: ComponentType) -> List[ComponentHealth]:
        """Get components of a specific type."""
        return [c for c in self._components.values() if c.component_type == component_type]

    def get_unhealthy_components(self) -> List[ComponentHealth]:
        """Get all unhealthy or degraded components."""
        return [c for c in self._components.values() if c.status in (HealthStatus.UNHEALTHY, HealthStatus.DEGRADED)]

    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[HealthAlert]:
        """Get all active alerts, optionally filtered by severity."""
        alerts = [a for a in self._alerts.values() if a.is_active]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        # Sort by severity and time
        severity_order = {AlertSeverity.CRITICAL: 0, AlertSeverity.WARNING: 1, AlertSeverity.INFO: 2}
        alerts.sort(key=lambda a: (severity_order[a.severity], a.triggered_at))

        return alerts

    def get_alert_history(self, hours: int = 24) -> List[HealthAlert]:
        """Get alert history for the specified period."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        alerts = [a for a in self._alerts.values() if a.triggered_at > cutoff]
        alerts.sort(key=lambda a: a.triggered_at, reverse=True)
        return alerts

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        if alert_id in self._alerts:
            self._alerts[alert_id].acknowledged = True
            return True
        return False

    def resolve_alert(self, alert_id: str) -> bool:
        """Manually resolve an alert."""
        if alert_id in self._alerts:
            self._alerts[alert_id].resolved_at = datetime.now(timezone.utc)
            return True
        return False

    def get_health_history(
        self,
        hours: int = 24,
        resolution_minutes: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Get health history with specified resolution.

        Args:
            hours: Number of hours of history
            resolution_minutes: Time resolution in minutes

        Returns:
            List of health data points
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        relevant = [h for h in self._history if h.timestamp > cutoff]

        if not relevant:
            return []

        # Bucket by resolution
        timedelta(minutes=resolution_minutes)
        buckets: Dict[datetime, List[HealthHistoryEntry]] = defaultdict(list)

        for entry in relevant:
            # Round to resolution
            bucket_time = entry.timestamp.replace(
                minute=(entry.timestamp.minute // resolution_minutes) * resolution_minutes,
                second=0,
                microsecond=0,
            )
            buckets[bucket_time].append(entry)

        # Average each bucket
        result = []
        for bucket_time in sorted(buckets.keys()):
            entries = buckets[bucket_time]
            avg_score = sum(e.health_score for e in entries) / len(entries)
            max_unhealthy = max(e.unhealthy_count for e in entries)
            max_alerts = max(e.alert_count for e in entries)

            result.append(
                {
                    "timestamp": bucket_time.isoformat(),
                    "health_score": round(avg_score, 4),
                    "unhealthy_count": max_unhealthy,
                    "alert_count": max_alerts,
                }
            )

        return result

    def get_dependency_health(self, component_id: str) -> Dict[str, Any]:
        """
        Get health status of a component's dependencies.

        Args:
            component_id: ID of the component

        Returns:
            Dictionary with dependency health information
        """
        component = self._components.get(component_id)
        if not component:
            return {"error": "Component not found"}

        dependencies = []
        for dep_id in component.dependencies:
            dep = self._components.get(dep_id)
            if dep:
                dependencies.append(
                    {
                        "component_id": dep_id,
                        "name": dep.name,
                        "status": dep.status.value,
                        "is_healthy": dep.is_healthy,
                    }
                )
            else:
                dependencies.append(
                    {
                        "component_id": dep_id,
                        "name": "Unknown",
                        "status": HealthStatus.UNKNOWN.value,
                        "is_healthy": False,
                    }
                )

        # Check if all dependencies are healthy
        all_healthy = all(d["is_healthy"] for d in dependencies)

        return {
            "component_id": component_id,
            "dependencies": dependencies,
            "all_dependencies_healthy": all_healthy,
            "dependency_count": len(dependencies),
        }

    def get_dependents(self, component_id: str) -> List[str]:
        """Get components that depend on the specified component."""
        return list(self._dependency_graph.get(component_id, set()))

    def get_health_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive health report.

        Returns:
            Dictionary with full health report
        """
        summary = self.get_cluster_summary()
        active_alerts = self.get_active_alerts()
        unhealthy = self.get_unhealthy_components()

        return {
            "summary": summary.to_dict(),
            "active_alerts": [a.to_dict() for a in active_alerts],
            "unhealthy_components": [c.to_dict() for c in unhealthy],
            "components": [c.to_dict() for c in self._components.values()],
            "health_trend": self.get_health_history(hours=6, resolution_minutes=10),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def start_monitoring(
        self,
        check_interval_seconds: float = 30.0,
    ) -> None:
        """
        Start continuous health monitoring.

        Args:
            check_interval_seconds: Interval between health checks
        """
        logger.info(f"Starting health monitoring (interval: {check_interval_seconds}s)")

        while True:
            try:
                await self.run_health_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(check_interval_seconds)


# =============================================================================
# Factory Functions
# =============================================================================


def create_health_aggregator(
    stale_threshold_seconds: float = 60.0,
    persist_path: Optional[str] = None,
) -> ClusterHealthAggregator:
    """
    Create a configured health aggregator.

    Args:
        stale_threshold_seconds: Seconds before component is considered stale
        persist_path: Path to persist health data

    Returns:
        Configured ClusterHealthAggregator instance
    """
    return ClusterHealthAggregator(
        stale_threshold_seconds=stale_threshold_seconds,
        persist_path=persist_path,
    )
