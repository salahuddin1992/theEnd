"""
Resource Quotas - حصص الموارد
=============================

نظام إدارة حصص الموارد:
- حصص لكل مستخدم/فريق/namespace
- تتبع الاستخدام الفعلي
- تطبيق الحدود
- تقارير الاستخدام
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List, Set, Any
import logging
from collections import defaultdict

from distributed_cluster.models.resources import ResourceSpec
from distributed_cluster.models.job import Job, JobStatus

logger = logging.getLogger(__name__)


class QuotaScope(str, Enum):
    """نطاق الحصة."""
    USER = "user"
    TEAM = "team"
    NAMESPACE = "namespace"
    PROJECT = "project"
    GLOBAL = "global"


class QuotaMetric(str, Enum):
    """مقاييس الحصة."""
    CPU_CORES = "cpu_cores"
    MEMORY_MB = "memory_mb"
    GPU_COUNT = "gpu_count"
    CONCURRENT_JOBS = "concurrent_jobs"
    TOTAL_JOBS_PER_HOUR = "total_jobs_per_hour"
    TOTAL_JOBS_PER_DAY = "total_jobs_per_day"
    STORAGE_MB = "storage_mb"
    NETWORK_EGRESS_MB = "network_egress_mb"


@dataclass
class QuotaLimit:
    """حد واحد من الحصة."""
    metric: QuotaMetric
    limit: float
    current_usage: float = 0.0
    reserved: float = 0.0  # محجوز للمهام المجدولة

    @property
    def available(self) -> float:
        """المتاح."""
        return max(0, self.limit - self.current_usage - self.reserved)

    @property
    def utilization_percent(self) -> float:
        """نسبة الاستخدام."""
        if self.limit == 0:
            return 0
        return ((self.current_usage + self.reserved) / self.limit) * 100

    def can_allocate(self, amount: float) -> bool:
        """هل يمكن تخصيص هذا المقدار؟"""
        return self.available >= amount

    def reserve(self, amount: float) -> bool:
        """حجز موارد."""
        if not self.can_allocate(amount):
            return False
        self.reserved += amount
        return True

    def confirm_reservation(self, amount: float) -> None:
        """تأكيد الحجز (تحويل من reserved إلى current)."""
        self.reserved = max(0, self.reserved - amount)
        self.current_usage += amount

    def release(self, amount: float) -> None:
        """تحرير موارد."""
        self.current_usage = max(0, self.current_usage - amount)

    def cancel_reservation(self, amount: float) -> None:
        """إلغاء حجز."""
        self.reserved = max(0, self.reserved - amount)


@dataclass
class Quota:
    """حصة موارد."""
    quota_id: str
    name: str
    scope: QuotaScope
    scope_id: str  # user_id, team_id, etc.
    limits: Dict[QuotaMetric, QuotaLimit] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    enabled: bool = True
    priority: int = 0  # أعلى = أولوية أكبر للموارد

    def get_limit(self, metric: QuotaMetric) -> Optional[QuotaLimit]:
        """الحصول على حد معين."""
        return self.limits.get(metric)

    def set_limit(self, metric: QuotaMetric, limit: float) -> None:
        """تعيين حد."""
        if metric in self.limits:
            self.limits[metric].limit = limit
        else:
            self.limits[metric] = QuotaLimit(metric=metric, limit=limit)
        self.updated_at = datetime.utcnow()

    def can_submit_job(self, job: Job) -> tuple[bool, str]:
        """هل يمكن إرسال مهمة؟"""
        if not self.enabled:
            return True, ""

        resources = job.submission.required_resources

        # Check CPU
        cpu_limit = self.limits.get(QuotaMetric.CPU_CORES)
        if cpu_limit and not cpu_limit.can_allocate(resources.cpu_cores):
            return False, f"CPU quota exceeded: need {resources.cpu_cores}, available {cpu_limit.available}"

        # Check Memory
        mem_limit = self.limits.get(QuotaMetric.MEMORY_MB)
        if mem_limit and not mem_limit.can_allocate(resources.memory_mb):
            return False, f"Memory quota exceeded: need {resources.memory_mb}MB, available {mem_limit.available}MB"

        # Check GPU
        gpu_limit = self.limits.get(QuotaMetric.GPU_COUNT)
        if gpu_limit and not gpu_limit.can_allocate(resources.gpu_count):
            return False, f"GPU quota exceeded: need {resources.gpu_count}, available {gpu_limit.available}"

        # Check concurrent jobs
        concurrent_limit = self.limits.get(QuotaMetric.CONCURRENT_JOBS)
        if concurrent_limit and not concurrent_limit.can_allocate(1):
            return False, f"Concurrent jobs limit reached: {int(concurrent_limit.limit)}"

        return True, ""

    def reserve_for_job(self, job: Job) -> bool:
        """حجز موارد لمهمة."""
        resources = job.submission.required_resources

        # Reserve all resources
        reservations = []

        cpu_limit = self.limits.get(QuotaMetric.CPU_CORES)
        if cpu_limit:
            if cpu_limit.reserve(resources.cpu_cores):
                reservations.append((cpu_limit, resources.cpu_cores))
            else:
                self._rollback_reservations(reservations)
                return False

        mem_limit = self.limits.get(QuotaMetric.MEMORY_MB)
        if mem_limit:
            if mem_limit.reserve(resources.memory_mb):
                reservations.append((mem_limit, resources.memory_mb))
            else:
                self._rollback_reservations(reservations)
                return False

        gpu_limit = self.limits.get(QuotaMetric.GPU_COUNT)
        if gpu_limit:
            if gpu_limit.reserve(resources.gpu_count):
                reservations.append((gpu_limit, resources.gpu_count))
            else:
                self._rollback_reservations(reservations)
                return False

        concurrent_limit = self.limits.get(QuotaMetric.CONCURRENT_JOBS)
        if concurrent_limit:
            if concurrent_limit.reserve(1):
                reservations.append((concurrent_limit, 1))
            else:
                self._rollback_reservations(reservations)
                return False

        return True

    def _rollback_reservations(self, reservations: list) -> None:
        """التراجع عن الحجوزات."""
        for limit, amount in reservations:
            limit.cancel_reservation(amount)

    def confirm_job_started(self, job: Job) -> None:
        """تأكيد بدء مهمة."""
        resources = job.submission.required_resources

        cpu_limit = self.limits.get(QuotaMetric.CPU_CORES)
        if cpu_limit:
            cpu_limit.confirm_reservation(resources.cpu_cores)

        mem_limit = self.limits.get(QuotaMetric.MEMORY_MB)
        if mem_limit:
            mem_limit.confirm_reservation(resources.memory_mb)

        gpu_limit = self.limits.get(QuotaMetric.GPU_COUNT)
        if gpu_limit:
            gpu_limit.confirm_reservation(resources.gpu_count)

        concurrent_limit = self.limits.get(QuotaMetric.CONCURRENT_JOBS)
        if concurrent_limit:
            concurrent_limit.confirm_reservation(1)

    def release_job_resources(self, job: Job) -> None:
        """تحرير موارد مهمة."""
        resources = job.submission.required_resources

        cpu_limit = self.limits.get(QuotaMetric.CPU_CORES)
        if cpu_limit:
            cpu_limit.release(resources.cpu_cores)

        mem_limit = self.limits.get(QuotaMetric.MEMORY_MB)
        if mem_limit:
            mem_limit.release(resources.memory_mb)

        gpu_limit = self.limits.get(QuotaMetric.GPU_COUNT)
        if gpu_limit:
            gpu_limit.release(resources.gpu_count)

        concurrent_limit = self.limits.get(QuotaMetric.CONCURRENT_JOBS)
        if concurrent_limit:
            concurrent_limit.release(1)

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dict."""
        return {
            "quota_id": self.quota_id,
            "name": self.name,
            "scope": self.scope.value,
            "scope_id": self.scope_id,
            "enabled": self.enabled,
            "priority": self.priority,
            "limits": {
                metric.value: {
                    "limit": limit.limit,
                    "current_usage": limit.current_usage,
                    "reserved": limit.reserved,
                    "available": limit.available,
                    "utilization_percent": limit.utilization_percent,
                }
                for metric, limit in self.limits.items()
            },
        }


@dataclass
class UsageRecord:
    """سجل استخدام."""
    scope: QuotaScope
    scope_id: str
    metric: QuotaMetric
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    job_id: Optional[str] = None


class QuotaManager:
    """
    مدير الحصص.

    يدير:
    - تعريف الحصص
    - تتبع الاستخدام
    - تطبيق الحدود
    - تقارير الاستخدام
    """

    def __init__(self):
        # Quotas: scope -> scope_id -> Quota
        self._quotas: Dict[QuotaScope, Dict[str, Quota]] = defaultdict(dict)

        # Job to quota mapping
        self._job_quotas: Dict[str, str] = {}  # job_id -> quota_id

        # Usage history (for rate limits)
        self._hourly_jobs: Dict[str, List[datetime]] = defaultdict(list)  # scope_id -> timestamps
        self._daily_jobs: Dict[str, List[datetime]] = defaultdict(list)

        # Default quotas
        self._default_quotas: Dict[QuotaScope, Quota] = {}

    def create_quota(
        self,
        name: str,
        scope: QuotaScope,
        scope_id: str,
        limits: Optional[Dict[QuotaMetric, float]] = None,
        priority: int = 0,
    ) -> Quota:
        """
        إنشاء حصة جديدة.

        Args:
            name: اسم الحصة
            scope: نطاق الحصة
            scope_id: معرف النطاق
            limits: الحدود
            priority: الأولوية

        Returns:
            Quota
        """
        quota_id = f"quota-{scope.value}-{scope_id}"

        quota = Quota(
            quota_id=quota_id,
            name=name,
            scope=scope,
            scope_id=scope_id,
            priority=priority,
        )

        if limits:
            for metric, limit in limits.items():
                quota.set_limit(metric, limit)

        self._quotas[scope][scope_id] = quota

        logger.info(f"Created quota {quota_id}: {name}")
        return quota

    def get_quota(self, scope: QuotaScope, scope_id: str) -> Optional[Quota]:
        """الحصول على حصة."""
        return self._quotas.get(scope, {}).get(scope_id)

    def get_or_create_quota(
        self,
        scope: QuotaScope,
        scope_id: str,
        default_limits: Optional[Dict[QuotaMetric, float]] = None,
    ) -> Quota:
        """الحصول على حصة أو إنشاؤها."""
        quota = self.get_quota(scope, scope_id)
        if quota:
            return quota

        # Check for default
        if scope in self._default_quotas:
            default = self._default_quotas[scope]
            return self.create_quota(
                name=f"Default {scope.value} quota",
                scope=scope,
                scope_id=scope_id,
                limits={m: l.limit for m, l in default.limits.items()},
            )

        # Create with provided defaults
        return self.create_quota(
            name=f"{scope.value} quota for {scope_id}",
            scope=scope,
            scope_id=scope_id,
            limits=default_limits,
        )

    def set_default_quota(self, scope: QuotaScope, limits: Dict[QuotaMetric, float]) -> None:
        """تعيين الحصة الافتراضية لنطاق."""
        quota = Quota(
            quota_id=f"default-{scope.value}",
            name=f"Default {scope.value} quota",
            scope=scope,
            scope_id="default",
        )
        for metric, limit in limits.items():
            quota.set_limit(metric, limit)

        self._default_quotas[scope] = quota
        logger.info(f"Set default quota for {scope.value}")

    def delete_quota(self, scope: QuotaScope, scope_id: str) -> bool:
        """حذف حصة."""
        if scope_id in self._quotas.get(scope, {}):
            del self._quotas[scope][scope_id]
            logger.info(f"Deleted quota for {scope.value}:{scope_id}")
            return True
        return False

    def check_quota(
        self,
        job: Job,
        scope: QuotaScope,
        scope_id: str,
    ) -> tuple[bool, str]:
        """
        التحقق من الحصة لمهمة.

        Args:
            job: المهمة
            scope: النطاق
            scope_id: معرف النطاق

        Returns:
            (allowed, message)
        """
        quota = self.get_quota(scope, scope_id)
        if not quota:
            # No quota defined = allowed
            return True, ""

        # Check job submission
        allowed, message = quota.can_submit_job(job)
        if not allowed:
            return False, message

        # Check rate limits
        allowed, message = self._check_rate_limits(quota)
        if not allowed:
            return False, message

        return True, ""

    def _check_rate_limits(self, quota: Quota) -> tuple[bool, str]:
        """التحقق من حدود المعدل."""
        now = datetime.utcnow()
        scope_id = quota.scope_id

        # Hourly limit
        hourly_limit = quota.limits.get(QuotaMetric.TOTAL_JOBS_PER_HOUR)
        if hourly_limit:
            # Clean old entries
            hour_ago = now - timedelta(hours=1)
            self._hourly_jobs[scope_id] = [
                t for t in self._hourly_jobs[scope_id] if t > hour_ago
            ]
            if len(self._hourly_jobs[scope_id]) >= hourly_limit.limit:
                return False, f"Hourly job limit reached: {int(hourly_limit.limit)}"

        # Daily limit
        daily_limit = quota.limits.get(QuotaMetric.TOTAL_JOBS_PER_DAY)
        if daily_limit:
            day_ago = now - timedelta(days=1)
            self._daily_jobs[scope_id] = [
                t for t in self._daily_jobs[scope_id] if t > day_ago
            ]
            if len(self._daily_jobs[scope_id]) >= daily_limit.limit:
                return False, f"Daily job limit reached: {int(daily_limit.limit)}"

        return True, ""

    def reserve_quota(
        self,
        job: Job,
        scope: QuotaScope,
        scope_id: str,
    ) -> bool:
        """حجز حصة لمهمة."""
        quota = self.get_quota(scope, scope_id)
        if not quota:
            return True

        if quota.reserve_for_job(job):
            self._job_quotas[job.job_id] = quota.quota_id
            return True
        return False

    def confirm_job_started(self, job: Job) -> None:
        """تأكيد بدء مهمة."""
        quota_id = self._job_quotas.get(job.job_id)
        if not quota_id:
            return

        # Find quota
        for scope_quotas in self._quotas.values():
            for quota in scope_quotas.values():
                if quota.quota_id == quota_id:
                    quota.confirm_job_started(job)

                    # Record rate limit
                    now = datetime.utcnow()
                    self._hourly_jobs[quota.scope_id].append(now)
                    self._daily_jobs[quota.scope_id].append(now)
                    return

    def release_job_quota(self, job: Job) -> None:
        """تحرير حصة مهمة."""
        quota_id = self._job_quotas.pop(job.job_id, None)
        if not quota_id:
            return

        for scope_quotas in self._quotas.values():
            for quota in scope_quotas.values():
                if quota.quota_id == quota_id:
                    quota.release_job_resources(job)
                    return

    def get_usage_report(
        self,
        scope: QuotaScope,
        scope_id: str,
    ) -> Dict[str, Any]:
        """تقرير الاستخدام."""
        quota = self.get_quota(scope, scope_id)
        if not quota:
            return {"error": "Quota not found"}

        return quota.to_dict()

    def get_all_quotas(self, scope: Optional[QuotaScope] = None) -> List[Dict[str, Any]]:
        """الحصول على كل الحصص."""
        quotas = []

        if scope:
            for quota in self._quotas.get(scope, {}).values():
                quotas.append(quota.to_dict())
        else:
            for scope_quotas in self._quotas.values():
                for quota in scope_quotas.values():
                    quotas.append(quota.to_dict())

        return quotas

    @property
    def stats(self) -> Dict[str, Any]:
        """إحصائيات."""
        total_quotas = sum(len(q) for q in self._quotas.values())
        return {
            "total_quotas": total_quotas,
            "tracked_jobs": len(self._job_quotas),
            "scopes": list(self._quotas.keys()),
        }


# =============================================================================
# Predefined Quota Templates
# =============================================================================

class QuotaTemplates:
    """قوالب حصص جاهزة."""

    @staticmethod
    def small_user() -> Dict[QuotaMetric, float]:
        """حصة مستخدم صغير."""
        return {
            QuotaMetric.CPU_CORES: 4,
            QuotaMetric.MEMORY_MB: 8192,
            QuotaMetric.GPU_COUNT: 0,
            QuotaMetric.CONCURRENT_JOBS: 5,
            QuotaMetric.TOTAL_JOBS_PER_HOUR: 20,
            QuotaMetric.TOTAL_JOBS_PER_DAY: 100,
        }

    @staticmethod
    def medium_user() -> Dict[QuotaMetric, float]:
        """حصة مستخدم متوسط."""
        return {
            QuotaMetric.CPU_CORES: 16,
            QuotaMetric.MEMORY_MB: 32768,
            QuotaMetric.GPU_COUNT: 1,
            QuotaMetric.CONCURRENT_JOBS: 20,
            QuotaMetric.TOTAL_JOBS_PER_HOUR: 100,
            QuotaMetric.TOTAL_JOBS_PER_DAY: 500,
        }

    @staticmethod
    def large_user() -> Dict[QuotaMetric, float]:
        """حصة مستخدم كبير."""
        return {
            QuotaMetric.CPU_CORES: 64,
            QuotaMetric.MEMORY_MB: 131072,
            QuotaMetric.GPU_COUNT: 4,
            QuotaMetric.CONCURRENT_JOBS: 50,
            QuotaMetric.TOTAL_JOBS_PER_HOUR: 500,
            QuotaMetric.TOTAL_JOBS_PER_DAY: 2000,
        }

    @staticmethod
    def team_standard() -> Dict[QuotaMetric, float]:
        """حصة فريق عادية."""
        return {
            QuotaMetric.CPU_CORES: 128,
            QuotaMetric.MEMORY_MB: 262144,
            QuotaMetric.GPU_COUNT: 8,
            QuotaMetric.CONCURRENT_JOBS: 100,
            QuotaMetric.TOTAL_JOBS_PER_HOUR: 1000,
            QuotaMetric.TOTAL_JOBS_PER_DAY: 5000,
        }

    @staticmethod
    def unlimited() -> Dict[QuotaMetric, float]:
        """حصة غير محدودة."""
        return {
            QuotaMetric.CPU_CORES: float('inf'),
            QuotaMetric.MEMORY_MB: float('inf'),
            QuotaMetric.GPU_COUNT: float('inf'),
            QuotaMetric.CONCURRENT_JOBS: float('inf'),
            QuotaMetric.TOTAL_JOBS_PER_HOUR: float('inf'),
            QuotaMetric.TOTAL_JOBS_PER_DAY: float('inf'),
        }
