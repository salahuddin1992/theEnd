"""
Quota Management - إدارة الحصص
================================

Resource quota management and enforcement.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class QuotaType(str, Enum):
    """نوع الحصة"""
    HARD = "hard"      # لا يمكن تجاوزها
    SOFT = "soft"      # يمكن تجاوزها مع تحذير
    BURST = "burst"    # يمكن تجاوزها مؤقتاً


class QuotaScope(str, Enum):
    """نطاق الحصة"""
    TENANT = "tenant"
    USER = "user"
    NAMESPACE = "namespace"
    PROJECT = "project"


@dataclass
class ResourceQuota:
    """
    حصة المورد
    Resource Quota
    """
    name: str
    resource: str
    limit: float
    used: float = 0.0
    quota_type: QuotaType = QuotaType.HARD
    scope: QuotaScope = QuotaScope.TENANT
    scope_id: Optional[str] = None

    # Time-based limits
    period_seconds: Optional[int] = None  # للحصص الدورية
    period_start: Optional[datetime] = None

    # Burst settings
    burst_limit: Optional[float] = None
    burst_duration_seconds: int = 60

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    @property
    def remaining(self) -> float:
        """المتبقي من الحصة"""
        return max(0, self.limit - self.used)

    @property
    def usage_percent(self) -> float:
        """نسبة الاستخدام"""
        if self.limit <= 0:
            return 0
        return (self.used / self.limit) * 100

    @property
    def is_exceeded(self) -> bool:
        """هل تم تجاوز الحصة؟"""
        return self.used >= self.limit

    @property
    def is_near_limit(self) -> bool:
        """هل الاستخدام قريب من الحد؟"""
        return self.usage_percent >= 80

    def can_allocate(self, amount: float) -> bool:
        """هل يمكن تخصيص هذا المقدار؟"""
        if self.quota_type == QuotaType.SOFT:
            return True
        if self.quota_type == QuotaType.BURST:
            burst = self.burst_limit or (self.limit * 1.5)
            return self.used + amount <= burst
        return self.used + amount <= self.limit

    def allocate(self, amount: float) -> bool:
        """تخصيص مقدار"""
        if not self.can_allocate(amount):
            return False
        self.used += amount
        self.updated_at = datetime.utcnow()
        return True

    def release(self, amount: float) -> None:
        """تحرير مقدار"""
        self.used = max(0, self.used - amount)
        self.updated_at = datetime.utcnow()

    def reset(self) -> None:
        """إعادة تعيين"""
        self.used = 0
        self.period_start = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس"""
        return {
            "name": self.name,
            "resource": self.resource,
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "usagePercent": self.usage_percent,
            "quotaType": self.quota_type.value,
            "scope": self.scope.value,
            "scopeId": self.scope_id,
            "isExceeded": self.is_exceeded,
            "isNearLimit": self.is_near_limit,
        }


@dataclass
class QuotaViolation:
    """انتهاك الحصة"""
    quota_name: str
    resource: str
    requested: float
    available: float
    limit: float
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


class QuotaManager:
    """
    مدير الحصص
    Quota Manager

    يدير حصص الموارد للمستأجرين.
    Manages resource quotas for tenants.
    """

    def __init__(self):
        self._quotas: Dict[str, Dict[str, ResourceQuota]] = {}  # scope_id -> resource -> quota
        self._lock = asyncio.Lock()

        # Violation handlers
        self._violation_handlers: List[Callable] = []

        # Background task
        self._reset_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """بدء المدير"""
        self._running = True
        self._reset_task = asyncio.create_task(self._reset_loop())
        logger.info("Quota Manager started")

    async def stop(self) -> None:
        """إيقاف المدير"""
        self._running = False
        if self._reset_task:
            self._reset_task.cancel()

    def set_quota(
        self,
        scope_id: str,
        resource: str,
        limit: float,
        quota_type: QuotaType = QuotaType.HARD,
        period_seconds: Optional[int] = None,
    ) -> ResourceQuota:
        """تعيين حصة"""
        quota = ResourceQuota(
            name=f"{scope_id}:{resource}",
            resource=resource,
            limit=limit,
            quota_type=quota_type,
            scope_id=scope_id,
            period_seconds=period_seconds,
            period_start=datetime.utcnow() if period_seconds else None,
        )

        if scope_id not in self._quotas:
            self._quotas[scope_id] = {}
        self._quotas[scope_id][resource] = quota

        logger.debug(f"Set quota: {scope_id}/{resource} = {limit}")
        return quota

    def get_quota(self, scope_id: str, resource: str) -> Optional[ResourceQuota]:
        """الحصول على حصة"""
        if scope_id in self._quotas:
            return self._quotas[scope_id].get(resource)
        return None

    def get_all_quotas(self, scope_id: str) -> List[ResourceQuota]:
        """الحصول على جميع حصص النطاق"""
        if scope_id in self._quotas:
            return list(self._quotas[scope_id].values())
        return []

    async def check_quota(
        self,
        scope_id: str,
        resource: str,
        requested: float,
    ) -> tuple[bool, Optional[QuotaViolation]]:
        """
        فحص الحصة
        Check quota
        """
        async with self._lock:
            quota = self.get_quota(scope_id, resource)
            if not quota:
                return True, None  # No quota = unlimited

            if quota.can_allocate(requested):
                return True, None

            violation = QuotaViolation(
                quota_name=quota.name,
                resource=resource,
                requested=requested,
                available=quota.remaining,
                limit=quota.limit,
                message=(
                    f"Quota exceeded for {resource}: requested {requested}, "
                    f"available {quota.remaining}, limit {quota.limit}"
                ),
            )

            # Notify handlers
            await self._notify_violation(violation)

            return False, violation

    async def allocate(
        self,
        scope_id: str,
        resource: str,
        amount: float,
    ) -> bool:
        """تخصيص موارد"""
        async with self._lock:
            quota = self.get_quota(scope_id, resource)
            if not quota:
                return True

            if quota.allocate(amount):
                logger.debug(f"Allocated {amount} {resource} for {scope_id}")
                return True

            return False

    async def release(
        self,
        scope_id: str,
        resource: str,
        amount: float,
    ) -> None:
        """تحرير موارد"""
        async with self._lock:
            quota = self.get_quota(scope_id, resource)
            if quota:
                quota.release(amount)
                logger.debug(f"Released {amount} {resource} for {scope_id}")

    async def get_usage(self, scope_id: str) -> Dict[str, Any]:
        """الحصول على الاستخدام"""
        quotas = self.get_all_quotas(scope_id)
        return {
            "quotas": [q.to_dict() for q in quotas],
            "summary": {
                "total": len(quotas),
                "exceeded": sum(1 for q in quotas if q.is_exceeded),
                "nearLimit": sum(1 for q in quotas if q.is_near_limit),
            },
        }

    def on_violation(self, handler: Callable) -> None:
        """تسجيل معالج الانتهاك"""
        self._violation_handlers.append(handler)

    async def _notify_violation(self, violation: QuotaViolation) -> None:
        """إرسال إشعار الانتهاك"""
        for handler in self._violation_handlers:
            try:
                await handler(violation)
            except Exception as e:
                logger.error(f"Error in violation handler: {e}")

    async def _reset_loop(self) -> None:
        """حلقة إعادة التعيين الدورية"""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute

                now = datetime.utcnow()
                async with self._lock:
                    for scope_quotas in self._quotas.values():
                        for quota in scope_quotas.values():
                            if quota.period_seconds and quota.period_start:
                                elapsed = (now - quota.period_start).total_seconds()
                                if elapsed >= quota.period_seconds:
                                    quota.reset()
                                    logger.debug(f"Reset periodic quota: {quota.name}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reset loop: {e}")


class QuotaEnforcer:
    """
    منفذ الحصص
    Quota Enforcer

    Middleware for enforcing quotas on requests.
    """

    def __init__(self, quota_manager: QuotaManager):
        self.quota_manager = quota_manager

    async def enforce(
        self,
        scope_id: str,
        resources: Dict[str, float],
    ) -> tuple[bool, List[QuotaViolation]]:
        """
        تنفيذ الحصص لعدة موارد
        Enforce quotas for multiple resources
        """
        violations = []

        for resource, amount in resources.items():
            allowed, violation = await self.quota_manager.check_quota(
                scope_id, resource, amount
            )
            if not allowed and violation:
                violations.append(violation)

        if violations:
            return False, violations

        # Allocate all resources
        for resource, amount in resources.items():
            await self.quota_manager.allocate(scope_id, resource, amount)

        return True, []

    async def release_all(
        self,
        scope_id: str,
        resources: Dict[str, float],
    ) -> None:
        """تحرير جميع الموارد"""
        for resource, amount in resources.items():
            await self.quota_manager.release(scope_id, resource, amount)
