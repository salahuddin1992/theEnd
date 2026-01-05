# -*- coding: utf-8 -*-
"""
Cost Tracker for NebulaCompute.

Tracks resource usage and calculates costs for jobs,
users, teams, and projects.

متتبع التكاليف لـ NebulaCompute.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CostCategory(str, Enum):
    """Cost category."""

    COMPUTE = "compute"  # CPU/GPU time
    MEMORY = "memory"  # Memory usage
    STORAGE = "storage"  # Disk storage
    NETWORK = "network"  # Network transfer
    AI_API = "ai_api"  # AI/LLM API calls
    LICENSE = "license"  # Software licenses
    ELECTRICITY = "electricity"  # Power consumption
    OTHER = "other"


class ResourceType(str, Enum):
    """Resource type."""

    CPU = "cpu"
    GPU = "gpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK_INGRESS = "network_ingress"
    NETWORK_EGRESS = "network_egress"
    LLM_TOKENS = "llm_tokens"


@dataclass
class ResourceCost:
    """
    Cost for a specific resource.

    تكلفة مورد معين.
    """

    resource_type: ResourceType
    quantity: float
    unit: str
    unit_price: float
    total_cost: float
    currency: str = "USD"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_type": self.resource_type.value,
            "quantity": self.quantity,
            "unit": self.unit,
            "unit_price": self.unit_price,
            "total_cost": self.total_cost,
            "currency": self.currency,
            "metadata": self.metadata,
        }


@dataclass
class CostEntry:
    """
    Cost entry for a job or time period.

    إدخال تكلفة لمهمة أو فترة زمنية.
    """

    entry_id: str
    job_id: Optional[str]
    user_id: str
    team_id: Optional[str]
    project_id: Optional[str]
    worker_id: str
    start_time: datetime
    end_time: datetime
    category: CostCategory
    resource_costs: List[ResourceCost] = field(default_factory=list)
    total_cost: float = 0.0
    currency: str = "USD"
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        """Calculate duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()

    @property
    def duration_hours(self) -> float:
        """Calculate duration in hours."""
        return self.duration_seconds / 3600

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry_id": self.entry_id,
            "job_id": self.job_id,
            "user_id": self.user_id,
            "team_id": self.team_id,
            "project_id": self.project_id,
            "worker_id": self.worker_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_hours": self.duration_hours,
            "category": self.category.value,
            "resource_costs": [rc.to_dict() for rc in self.resource_costs],
            "total_cost": self.total_cost,
            "currency": self.currency,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class UsageMetrics:
    """
    Resource usage metrics.

    مقاييس استخدام الموارد.
    """

    cpu_hours: float = 0.0
    gpu_hours: float = 0.0
    memory_gb_hours: float = 0.0
    storage_gb_hours: float = 0.0
    network_ingress_gb: float = 0.0
    network_egress_gb: float = 0.0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    job_count: int = 0
    total_duration_hours: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cpu_hours": self.cpu_hours,
            "gpu_hours": self.gpu_hours,
            "memory_gb_hours": self.memory_gb_hours,
            "storage_gb_hours": self.storage_gb_hours,
            "network_ingress_gb": self.network_ingress_gb,
            "network_egress_gb": self.network_egress_gb,
            "llm_input_tokens": self.llm_input_tokens,
            "llm_output_tokens": self.llm_output_tokens,
            "job_count": self.job_count,
            "total_duration_hours": self.total_duration_hours,
        }


class CostTracker:
    """
    Tracks and calculates resource costs.

    متتبع ومحسب تكاليف الموارد.

    Features:
    - Real-time cost tracking
    - Per-job cost breakdown
    - User/team/project aggregation
    - Multiple cost categories
    - Historical cost data
    - Cost alerts
    """

    # Default pricing (per hour)
    DEFAULT_PRICES = {
        ResourceType.CPU: 0.05,  # per CPU core hour
        ResourceType.GPU: 1.50,  # per GPU hour
        ResourceType.MEMORY: 0.01,  # per GB hour
        ResourceType.DISK: 0.001,  # per GB hour
        ResourceType.NETWORK_INGRESS: 0.01,  # per GB
        ResourceType.NETWORK_EGRESS: 0.05,  # per GB
        ResourceType.LLM_TOKENS: 0.00001,  # per token
    }

    def __init__(
        self,
        prices: Optional[Dict[ResourceType, float]] = None,
        currency: str = "USD",
        retention_days: int = 365,
        enable_alerts: bool = True,
        alert_threshold_percent: float = 80.0,
    ):
        """
        Initialize Cost Tracker.

        Args:
            prices: Custom pricing per resource type
            currency: Currency for costs
            retention_days: Days to retain cost data
            enable_alerts: Enable cost alerts
            alert_threshold_percent: Alert threshold as % of budget
        """
        self.prices = {**self.DEFAULT_PRICES, **(prices or {})}
        self.currency = currency
        self.retention_days = retention_days
        self.enable_alerts = enable_alerts
        self.alert_threshold = alert_threshold_percent

        # Storage
        self._entries: Dict[str, CostEntry] = {}
        self._job_entries: Dict[str, List[str]] = {}  # job_id -> entry_ids
        self._user_entries: Dict[str, List[str]] = {}  # user_id -> entry_ids
        self._team_entries: Dict[str, List[str]] = {}  # team_id -> entry_ids
        self._project_entries: Dict[str, List[str]] = {}  # project_id -> entry_ids
        self._lock = asyncio.Lock()

        # Active tracking
        self._active_jobs: Dict[str, Dict[str, Any]] = {}  # job_id -> tracking info

        # Statistics
        self._stats = {
            "total_entries": 0,
            "total_cost": 0.0,
            "total_compute_cost": 0.0,
            "total_ai_cost": 0.0,
            "total_storage_cost": 0.0,
        }

    async def start_job_tracking(
        self,
        job_id: str,
        user_id: str,
        worker_id: str,
        team_id: Optional[str] = None,
        project_id: Optional[str] = None,
        resources: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Start tracking costs for a job.

        بدء تتبع تكاليف مهمة.
        """
        async with self._lock:
            self._active_jobs[job_id] = {
                "job_id": job_id,
                "user_id": user_id,
                "team_id": team_id,
                "project_id": project_id,
                "worker_id": worker_id,
                "start_time": datetime.now(timezone.utc),
                "resources": resources or {},
                "metadata": metadata or {},
                "ai_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "requests": 0,
                },
            }

        logger.debug(f"Started cost tracking for job {job_id}")

    async def stop_job_tracking(
        self,
        job_id: str,
        final_resources: Optional[Dict[str, Any]] = None,
    ) -> Optional[CostEntry]:
        """
        Stop tracking and calculate final cost for a job.

        إيقاف التتبع وحساب التكلفة النهائية.
        """
        async with self._lock:
            if job_id not in self._active_jobs:
                logger.warning(f"Job {job_id} not being tracked")
                return None

            job_info = self._active_jobs.pop(job_id)
            end_time = datetime.now(timezone.utc)

            # Merge final resources
            resources = {**job_info["resources"], **(final_resources or {})}

            # Calculate costs
            entry = await self._calculate_job_cost(job_info, end_time, resources)

            # Store entry
            self._entries[entry.entry_id] = entry
            self._stats["total_entries"] += 1
            self._stats["total_cost"] += entry.total_cost

            # Index by job, user, team, project
            if entry.job_id:
                if entry.job_id not in self._job_entries:
                    self._job_entries[entry.job_id] = []
                self._job_entries[entry.job_id].append(entry.entry_id)

            if entry.user_id not in self._user_entries:
                self._user_entries[entry.user_id] = []
            self._user_entries[entry.user_id].append(entry.entry_id)

            if entry.team_id:
                if entry.team_id not in self._team_entries:
                    self._team_entries[entry.team_id] = []
                self._team_entries[entry.team_id].append(entry.entry_id)

            if entry.project_id:
                if entry.project_id not in self._project_entries:
                    self._project_entries[entry.project_id] = []
                self._project_entries[entry.project_id].append(entry.entry_id)

        logger.info(
            f"Job {job_id} cost: ${entry.total_cost:.4f} "
            f"({entry.duration_hours:.2f} hours)"
        )

        return entry

    async def _calculate_job_cost(
        self,
        job_info: Dict[str, Any],
        end_time: datetime,
        resources: Dict[str, Any],
    ) -> CostEntry:
        """Calculate cost for a job."""
        import uuid

        start_time = job_info["start_time"]
        duration_hours = (end_time - start_time).total_seconds() / 3600

        resource_costs = []
        total_cost = 0.0

        # CPU cost
        cpu_cores = resources.get("cpu_cores", 1)
        cpu_cost = ResourceCost(
            resource_type=ResourceType.CPU,
            quantity=cpu_cores * duration_hours,
            unit="core-hour",
            unit_price=self.prices[ResourceType.CPU],
            total_cost=cpu_cores * duration_hours * self.prices[ResourceType.CPU],
            currency=self.currency,
        )
        resource_costs.append(cpu_cost)
        total_cost += cpu_cost.total_cost

        # GPU cost
        gpu_count = resources.get("gpu_count", 0)
        if gpu_count > 0:
            gpu_cost = ResourceCost(
                resource_type=ResourceType.GPU,
                quantity=gpu_count * duration_hours,
                unit="gpu-hour",
                unit_price=self.prices[ResourceType.GPU],
                total_cost=gpu_count * duration_hours * self.prices[ResourceType.GPU],
                currency=self.currency,
            )
            resource_costs.append(gpu_cost)
            total_cost += gpu_cost.total_cost

        # Memory cost
        memory_gb = resources.get("memory_gb", 1)
        memory_cost = ResourceCost(
            resource_type=ResourceType.MEMORY,
            quantity=memory_gb * duration_hours,
            unit="GB-hour",
            unit_price=self.prices[ResourceType.MEMORY],
            total_cost=memory_gb * duration_hours * self.prices[ResourceType.MEMORY],
            currency=self.currency,
        )
        resource_costs.append(memory_cost)
        total_cost += memory_cost.total_cost

        # Network cost
        network_egress_gb = resources.get("network_egress_gb", 0)
        if network_egress_gb > 0:
            network_cost = ResourceCost(
                resource_type=ResourceType.NETWORK_EGRESS,
                quantity=network_egress_gb,
                unit="GB",
                unit_price=self.prices[ResourceType.NETWORK_EGRESS],
                total_cost=network_egress_gb * self.prices[ResourceType.NETWORK_EGRESS],
                currency=self.currency,
            )
            resource_costs.append(network_cost)
            total_cost += network_cost.total_cost

        # LLM token cost
        ai_usage = job_info.get("ai_usage", {})
        total_tokens = ai_usage.get("input_tokens", 0) + ai_usage.get("output_tokens", 0)
        if total_tokens > 0:
            llm_cost = ResourceCost(
                resource_type=ResourceType.LLM_TOKENS,
                quantity=total_tokens,
                unit="tokens",
                unit_price=self.prices[ResourceType.LLM_TOKENS],
                total_cost=total_tokens * self.prices[ResourceType.LLM_TOKENS],
                currency=self.currency,
                metadata={
                    "input_tokens": ai_usage.get("input_tokens", 0),
                    "output_tokens": ai_usage.get("output_tokens", 0),
                },
            )
            resource_costs.append(llm_cost)
            total_cost += llm_cost.total_cost

        return CostEntry(
            entry_id=str(uuid.uuid4()),
            job_id=job_info["job_id"],
            user_id=job_info["user_id"],
            team_id=job_info.get("team_id"),
            project_id=job_info.get("project_id"),
            worker_id=job_info["worker_id"],
            start_time=start_time,
            end_time=end_time,
            category=CostCategory.COMPUTE,
            resource_costs=resource_costs,
            total_cost=total_cost,
            currency=self.currency,
            metadata=job_info.get("metadata", {}),
        )

    async def record_ai_usage(
        self,
        job_id: str,
        input_tokens: int,
        output_tokens: int,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> None:
        """
        Record AI/LLM usage for a job.

        تسجيل استخدام AI لمهمة.
        """
        async with self._lock:
            if job_id in self._active_jobs:
                ai_usage = self._active_jobs[job_id]["ai_usage"]
                ai_usage["input_tokens"] += input_tokens
                ai_usage["output_tokens"] += output_tokens
                ai_usage["requests"] += 1

                if model:
                    ai_usage["model"] = model
                if provider:
                    ai_usage["provider"] = provider

    async def get_job_cost(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get cost summary for a job."""
        entry_ids = self._job_entries.get(job_id, [])
        if not entry_ids:
            return None

        entries = [self._entries[eid] for eid in entry_ids if eid in self._entries]
        if not entries:
            return None

        total_cost = sum(e.total_cost for e in entries)
        total_duration = sum(e.duration_hours for e in entries)

        return {
            "job_id": job_id,
            "total_cost": total_cost,
            "currency": self.currency,
            "total_duration_hours": total_duration,
            "entries": [e.to_dict() for e in entries],
        }

    async def get_user_costs(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get cost summary for a user."""
        return await self._get_entity_costs(
            self._user_entries.get(user_id, []),
            "user_id",
            user_id,
            start_date,
            end_date,
        )

    async def get_team_costs(
        self,
        team_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get cost summary for a team."""
        return await self._get_entity_costs(
            self._team_entries.get(team_id, []),
            "team_id",
            team_id,
            start_date,
            end_date,
        )

    async def get_project_costs(
        self,
        project_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get cost summary for a project."""
        return await self._get_entity_costs(
            self._project_entries.get(project_id, []),
            "project_id",
            project_id,
            start_date,
            end_date,
        )

    async def _get_entity_costs(
        self,
        entry_ids: List[str],
        entity_type: str,
        entity_id: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> Dict[str, Any]:
        """Get costs for an entity."""
        entries = []
        for eid in entry_ids:
            entry = self._entries.get(eid)
            if not entry:
                continue

            if start_date and entry.start_time < start_date:
                continue
            if end_date and entry.end_time > end_date:
                continue

            entries.append(entry)

        # Calculate totals
        total_cost = sum(e.total_cost for e in entries)
        total_duration = sum(e.duration_hours for e in entries)

        # Break down by category
        by_category = {}
        for entry in entries:
            cat = entry.category.value
            if cat not in by_category:
                by_category[cat] = 0.0
            by_category[cat] += entry.total_cost

        # Break down by resource type
        by_resource = {}
        for entry in entries:
            for rc in entry.resource_costs:
                rt = rc.resource_type.value
                if rt not in by_resource:
                    by_resource[rt] = 0.0
                by_resource[rt] += rc.total_cost

        return {
            entity_type: entity_id,
            "total_cost": total_cost,
            "currency": self.currency,
            "total_duration_hours": total_duration,
            "job_count": len(set(e.job_id for e in entries if e.job_id)),
            "by_category": by_category,
            "by_resource": by_resource,
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
        }

    async def get_usage_metrics(
        self,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        project_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> UsageMetrics:
        """
        Get resource usage metrics.

        الحصول على مقاييس استخدام الموارد.
        """
        entries = []

        # Filter entries
        for entry in self._entries.values():
            if user_id and entry.user_id != user_id:
                continue
            if team_id and entry.team_id != team_id:
                continue
            if project_id and entry.project_id != project_id:
                continue
            if start_date and entry.start_time < start_date:
                continue
            if end_date and entry.end_time > end_date:
                continue
            entries.append(entry)

        metrics = UsageMetrics(
            job_count=len(set(e.job_id for e in entries if e.job_id)),
            total_duration_hours=sum(e.duration_hours for e in entries),
        )

        # Aggregate resource usage
        for entry in entries:
            for rc in entry.resource_costs:
                if rc.resource_type == ResourceType.CPU:
                    metrics.cpu_hours += rc.quantity
                elif rc.resource_type == ResourceType.GPU:
                    metrics.gpu_hours += rc.quantity
                elif rc.resource_type == ResourceType.MEMORY:
                    metrics.memory_gb_hours += rc.quantity
                elif rc.resource_type == ResourceType.DISK:
                    metrics.storage_gb_hours += rc.quantity
                elif rc.resource_type == ResourceType.NETWORK_INGRESS:
                    metrics.network_ingress_gb += rc.quantity
                elif rc.resource_type == ResourceType.NETWORK_EGRESS:
                    metrics.network_egress_gb += rc.quantity
                elif rc.resource_type == ResourceType.LLM_TOKENS:
                    input_tokens = rc.metadata.get("input_tokens", 0)
                    output_tokens = rc.metadata.get("output_tokens", 0)
                    metrics.llm_input_tokens += input_tokens
                    metrics.llm_output_tokens += output_tokens

        return metrics

    async def get_cost_trend(
        self,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        project_id: Optional[str] = None,
        days: int = 30,
        granularity: str = "day",
    ) -> List[Dict[str, Any]]:
        """
        Get cost trend over time.

        الحصول على اتجاه التكاليف.
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Get entries in range
        entries = []
        for entry in self._entries.values():
            if user_id and entry.user_id != user_id:
                continue
            if team_id and entry.team_id != team_id:
                continue
            if project_id and entry.project_id != project_id:
                continue
            if entry.start_time < start_date:
                continue
            entries.append(entry)

        # Group by granularity
        trend = {}
        for entry in entries:
            if granularity == "day":
                key = entry.start_time.strftime("%Y-%m-%d")
            elif granularity == "week":
                key = entry.start_time.strftime("%Y-W%W")
            elif granularity == "month":
                key = entry.start_time.strftime("%Y-%m")
            else:
                key = entry.start_time.strftime("%Y-%m-%d")

            if key not in trend:
                trend[key] = {"period": key, "cost": 0.0, "jobs": 0}

            trend[key]["cost"] += entry.total_cost
            trend[key]["jobs"] += 1

        # Sort by period
        return sorted(trend.values(), key=lambda x: x["period"])

    async def update_prices(
        self,
        prices: Dict[ResourceType, float],
    ) -> None:
        """Update resource prices."""
        self.prices.update(prices)
        logger.info(f"Updated prices: {prices}")

    async def get_statistics(self) -> Dict[str, Any]:
        """Get cost tracker statistics."""
        return {
            **self._stats,
            "active_jobs": len(self._active_jobs),
            "total_users": len(self._user_entries),
            "total_teams": len(self._team_entries),
            "total_projects": len(self._project_entries),
            "currency": self.currency,
            "prices": {rt.value: price for rt, price in self.prices.items()},
        }

    async def cleanup_old_entries(self) -> int:
        """Clean up old cost entries."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        removed = 0

        async with self._lock:
            to_remove = [
                eid
                for eid, entry in self._entries.items()
                if entry.created_at < cutoff
            ]

            for eid in to_remove:
                del self._entries[eid]
                removed += 1

        if removed:
            logger.info(f"Cleaned up {removed} old cost entries")

        return removed

    async def shutdown(self) -> None:
        """Shutdown cost tracker."""
        # Stop tracking any active jobs
        for job_id in list(self._active_jobs.keys()):
            await self.stop_job_tracking(job_id)

        logger.info("Cost Tracker shutdown complete")
