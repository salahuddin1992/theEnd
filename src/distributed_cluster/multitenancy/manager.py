"""
Tenant Manager - مدير المستأجرين
==================================

Manages tenant lifecycle and operations.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from distributed_cluster.multitenancy.tenant import (
    Tenant,
    TenantStatus,
    TenantTier,
    TenantQuotas,
    TenantConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class TenantManagerConfig:
    """تكوين مدير المستأجرين"""
    # Auto-provisioning
    auto_provision_namespace: bool = True
    namespace_prefix: str = "nc-tenant-"

    # Quotas
    enforce_quotas: bool = True
    quota_check_interval_seconds: int = 60
    quota_warning_threshold: float = 0.8  # 80%

    # Cleanup
    cleanup_terminated_after_days: int = 30
    cleanup_inactive_after_days: int = 90

    # Notifications
    notify_on_quota_warning: bool = True
    notify_on_suspension: bool = True

    # Defaults
    default_tier: TenantTier = TenantTier.FREE
    allow_self_registration: bool = False


class TenantManager:
    """
    مدير المستأجرين
    Tenant Manager

    يدير دورة حياة المستأجرين والعمليات المتعلقة بهم.
    Manages tenant lifecycle and operations.
    """

    def __init__(
        self,
        config: Optional[TenantManagerConfig] = None,
        storage: Any = None,
    ):
        self.config = config or TenantManagerConfig()
        self.storage = storage

        self._tenants: Dict[str, Tenant] = {}
        self._tenant_by_name: Dict[str, str] = {}  # name -> id
        self._lock = asyncio.Lock()

        # Event handlers
        self._on_tenant_created: List[Callable] = []
        self._on_tenant_updated: List[Callable] = []
        self._on_tenant_suspended: List[Callable] = []
        self._on_tenant_deleted: List[Callable] = []

        # Background tasks
        self._quota_check_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء المدير"""
        logger.info("Starting Tenant Manager")
        self._running = True

        # Load tenants from storage
        if self.storage:
            await self._load_tenants()

        # Start background tasks
        if self.config.enforce_quotas:
            self._quota_check_task = asyncio.create_task(self._quota_check_loop())

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(f"Tenant Manager started with {len(self._tenants)} tenants")

    async def stop(self) -> None:
        """إيقاف المدير"""
        logger.info("Stopping Tenant Manager")
        self._running = False

        if self._quota_check_task:
            self._quota_check_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()

        # Save tenants
        if self.storage:
            await self._save_tenants()

    async def _load_tenants(self) -> None:
        """تحميل المستأجرين من التخزين"""
        try:
            tenants_data = await self.storage.load("tenants")
            if tenants_data:
                for data in tenants_data:
                    tenant = Tenant.from_dict(data)
                    self._tenants[tenant.id] = tenant
                    self._tenant_by_name[tenant.name] = tenant.id
        except Exception as e:
            logger.error(f"Failed to load tenants: {e}")

    async def _save_tenants(self) -> None:
        """حفظ المستأجرين في التخزين"""
        try:
            tenants_data = [t.to_dict() for t in self._tenants.values()]
            await self.storage.save("tenants", tenants_data)
        except Exception as e:
            logger.error(f"Failed to save tenants: {e}")

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create_tenant(
        self,
        name: str,
        display_name: Optional[str] = None,
        admin_email: Optional[str] = None,
        tier: Optional[TenantTier] = None,
        quotas: Optional[TenantQuotas] = None,
        config: Optional[TenantConfig] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tenant:
        """
        إنشاء مستأجر جديد
        Create new tenant
        """
        async with self._lock:
            # Check if name already exists
            if name in self._tenant_by_name:
                raise ValueError(f"Tenant with name '{name}' already exists")

            # Create tenant
            tier = tier or self.config.default_tier
            tenant = Tenant(
                id=str(uuid.uuid4()),
                name=name,
                display_name=display_name or name,
                admin_email=admin_email,
                status=TenantStatus.PENDING,
                tier=tier,
                quotas=quotas or TenantQuotas.from_tier(tier),
                config=config or TenantConfig(),
                metadata=metadata or {},
            )

            # Provision resources
            await self._provision_tenant(tenant)

            # Activate
            tenant.status = TenantStatus.ACTIVE
            tenant.activated_at = datetime.utcnow()

            # Store
            self._tenants[tenant.id] = tenant
            self._tenant_by_name[tenant.name] = tenant.id

            # Notify
            await self._emit_event("created", tenant)

            logger.info(f"Created tenant: {tenant.name} ({tenant.id})")
            return tenant

    async def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """الحصول على مستأجر بالمعرف"""
        return self._tenants.get(tenant_id)

    async def get_tenant_by_name(self, name: str) -> Optional[Tenant]:
        """الحصول على مستأجر بالاسم"""
        tenant_id = self._tenant_by_name.get(name)
        if tenant_id:
            return self._tenants.get(tenant_id)
        return None

    async def list_tenants(
        self,
        status: Optional[TenantStatus] = None,
        tier: Optional[TenantTier] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Tenant]:
        """قائمة المستأجرين"""
        tenants = list(self._tenants.values())

        if status:
            tenants = [t for t in tenants if t.status == status]
        if tier:
            tenants = [t for t in tenants if t.tier == tier]

        # Sort by creation date
        tenants.sort(key=lambda t: t.created_at, reverse=True)

        return tenants[offset : offset + limit]

    async def update_tenant(
        self,
        tenant_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        tier: Optional[TenantTier] = None,
        quotas: Optional[TenantQuotas] = None,
        config: Optional[TenantConfig] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tenant:
        """تحديث مستأجر"""
        async with self._lock:
            tenant = self._tenants.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant not found: {tenant_id}")

            if display_name:
                tenant.display_name = display_name
            if description:
                tenant.description = description
            if tier:
                tenant.tier = tier
                if not quotas:
                    tenant.quotas = TenantQuotas.from_tier(tier)
            if quotas:
                tenant.quotas = quotas
            if config:
                tenant.config = config
            if metadata:
                tenant.metadata.update(metadata)

            tenant.updated_at = datetime.utcnow()

            await self._emit_event("updated", tenant)

            logger.info(f"Updated tenant: {tenant.name}")
            return tenant

    async def suspend_tenant(
        self,
        tenant_id: str,
        reason: Optional[str] = None,
    ) -> Tenant:
        """تعليق مستأجر"""
        async with self._lock:
            tenant = self._tenants.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant not found: {tenant_id}")

            tenant.status = TenantStatus.SUSPENDED
            tenant.suspended_at = datetime.utcnow()
            tenant.suspension_reason = reason
            tenant.updated_at = datetime.utcnow()

            # Cancel active jobs
            await self._cancel_tenant_jobs(tenant)

            await self._emit_event("suspended", tenant)

            logger.warning(f"Suspended tenant: {tenant.name}, reason: {reason}")
            return tenant

    async def activate_tenant(self, tenant_id: str) -> Tenant:
        """تفعيل مستأجر"""
        async with self._lock:
            tenant = self._tenants.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant not found: {tenant_id}")

            tenant.status = TenantStatus.ACTIVE
            tenant.suspended_at = None
            tenant.suspension_reason = None
            tenant.updated_at = datetime.utcnow()

            await self._emit_event("activated", tenant)

            logger.info(f"Activated tenant: {tenant.name}")
            return tenant

    async def delete_tenant(
        self,
        tenant_id: str,
        force: bool = False,
    ) -> None:
        """حذف مستأجر"""
        async with self._lock:
            tenant = self._tenants.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant not found: {tenant_id}")

            if not force and tenant.usage.active_jobs > 0:
                raise ValueError("Cannot delete tenant with active jobs")

            # Mark as terminating
            tenant.status = TenantStatus.TERMINATING
            tenant.updated_at = datetime.utcnow()

            # Cleanup resources
            await self._cleanup_tenant(tenant)

            # Remove from storage
            del self._tenants[tenant_id]
            if tenant.name in self._tenant_by_name:
                del self._tenant_by_name[tenant.name]

            await self._emit_event("deleted", tenant)

            logger.info(f"Deleted tenant: {tenant.name}")

    # =========================================================================
    # Quota Management
    # =========================================================================

    async def check_quota(
        self,
        tenant_id: str,
        resource: str,
        requested: float,
    ) -> tuple[bool, str]:
        """فحص الحصة"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False, "Tenant not found"

        if not tenant.is_active:
            return False, f"Tenant is {tenant.status.value}"

        return tenant.check_quota(resource, requested)

    async def update_usage(
        self,
        tenant_id: str,
        resource: str,
        delta: float,
    ) -> None:
        """تحديث الاستخدام"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return

        usage = tenant.usage
        if resource == "cpu":
            usage.cpu_used = max(0, usage.cpu_used + delta)
        elif resource == "memory":
            usage.memory_used_mb = max(0, usage.memory_used_mb + int(delta))
        elif resource == "gpu":
            usage.gpu_used = max(0, usage.gpu_used + int(delta))
        elif resource == "jobs":
            usage.active_jobs = max(0, usage.active_jobs + int(delta))
            if delta > 0:
                usage.jobs_today += int(delta)
                usage.total_jobs += int(delta)

        usage.last_activity = datetime.utcnow()

        # Check for quota exceeded
        if self.config.enforce_quotas:
            await self._check_quota_exceeded(tenant)

    async def get_usage_stats(self, tenant_id: str) -> Dict[str, Any]:
        """الحصول على إحصائيات الاستخدام"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return {}

        return {
            "usage": tenant.usage.to_dict(),
            "quotas": tenant.quotas.to_dict(),
            "quotaUsagePercent": tenant.quota_usage_percent,
            "canSubmitJobs": tenant.can_submit_jobs,
        }

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _provision_tenant(self, tenant: Tenant) -> None:
        """تجهيز موارد المستأجر"""
        if self.config.auto_provision_namespace:
            namespace = f"{self.config.namespace_prefix}{tenant.name}"
            tenant.config.dedicated_namespace = namespace
            # TODO: Create Kubernetes namespace if needed
            logger.debug(f"Provisioned namespace: {namespace}")

    async def _cleanup_tenant(self, tenant: Tenant) -> None:
        """تنظيف موارد المستأجر"""
        # Cancel all jobs
        await self._cancel_tenant_jobs(tenant)

        # TODO: Delete namespace, storage, etc.
        logger.debug(f"Cleaned up tenant: {tenant.name}")

    async def _cancel_tenant_jobs(self, tenant: Tenant) -> None:
        """إلغاء مهام المستأجر"""
        # TODO: Implement job cancellation
        logger.debug(f"Cancelling jobs for tenant: {tenant.name}")

    async def _check_quota_exceeded(self, tenant: Tenant) -> None:
        """فحص تجاوز الحصة"""
        usage_percent = tenant.quota_usage_percent

        # Check for quota exceeded
        exceeded = any(p >= 100 for p in usage_percent.values())
        if exceeded and tenant.status == TenantStatus.ACTIVE:
            tenant.status = TenantStatus.QUOTA_EXCEEDED
            tenant.updated_at = datetime.utcnow()
            logger.warning(f"Tenant {tenant.name} exceeded quota")

        # Check for warning
        elif self.config.notify_on_quota_warning:
            warning = any(p >= self.config.quota_warning_threshold * 100 for p in usage_percent.values())
            if warning:
                logger.info(f"Tenant {tenant.name} approaching quota limit")
                # TODO: Send notification

    async def _quota_check_loop(self) -> None:
        """حلقة فحص الحصص"""
        while self._running:
            try:
                await asyncio.sleep(self.config.quota_check_interval_seconds)

                for tenant in self._tenants.values():
                    if tenant.is_active:
                        await self._check_quota_exceeded(tenant)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in quota check loop: {e}")

    async def _cleanup_loop(self) -> None:
        """حلقة التنظيف"""
        while self._running:
            try:
                await asyncio.sleep(3600)  # Every hour

                now = datetime.utcnow()
                for tenant in list(self._tenants.values()):
                    # Cleanup terminated tenants
                    if tenant.status == TenantStatus.TERMINATED:
                        if tenant.updated_at:
                            days = (now - tenant.updated_at).days
                            if days >= self.config.cleanup_terminated_after_days:
                                await self.delete_tenant(tenant.id, force=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _emit_event(self, event_type: str, tenant: Tenant) -> None:
        """إرسال حدث"""
        handlers = {
            "created": self._on_tenant_created,
            "updated": self._on_tenant_updated,
            "suspended": self._on_tenant_suspended,
            "deleted": self._on_tenant_deleted,
        }

        for handler in handlers.get(event_type, []):
            try:
                await handler(tenant)
            except Exception as e:
                logger.error(f"Error in event handler: {e}")

    # =========================================================================
    # Event Registration
    # =========================================================================

    def on_tenant_created(self, handler: Callable) -> None:
        """تسجيل معالج إنشاء المستأجر"""
        self._on_tenant_created.append(handler)

    def on_tenant_updated(self, handler: Callable) -> None:
        """تسجيل معالج تحديث المستأجر"""
        self._on_tenant_updated.append(handler)

    def on_tenant_suspended(self, handler: Callable) -> None:
        """تسجيل معالج تعليق المستأجر"""
        self._on_tenant_suspended.append(handler)

    def on_tenant_deleted(self, handler: Callable) -> None:
        """تسجيل معالج حذف المستأجر"""
        self._on_tenant_deleted.append(handler)

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات"""
        tenants = list(self._tenants.values())

        by_status = {}
        by_tier = {}
        total_jobs = 0
        total_cpu = 0.0
        total_memory = 0

        for tenant in tenants:
            by_status[tenant.status.value] = by_status.get(tenant.status.value, 0) + 1
            by_tier[tenant.tier.value] = by_tier.get(tenant.tier.value, 0) + 1
            total_jobs += tenant.usage.active_jobs
            total_cpu += tenant.usage.cpu_used
            total_memory += tenant.usage.memory_used_mb

        return {
            "totalTenants": len(tenants),
            "byStatus": by_status,
            "byTier": by_tier,
            "totalActiveJobs": total_jobs,
            "totalCpuUsed": total_cpu,
            "totalMemoryUsedMb": total_memory,
        }
