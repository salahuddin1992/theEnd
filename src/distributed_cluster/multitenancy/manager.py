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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from distributed_cluster.multitenancy.tenant import (
    Tenant,
    TenantConfig,
    TenantQuotas,
    TenantStatus,
    TenantTier,
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
            tenant.activated_at = datetime.now(timezone.utc)

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

            tenant.updated_at = datetime.now(timezone.utc)

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
            tenant.suspended_at = datetime.now(timezone.utc)
            tenant.suspension_reason = reason
            tenant.updated_at = datetime.now(timezone.utc)

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
            tenant.updated_at = datetime.now(timezone.utc)

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
            tenant.updated_at = datetime.now(timezone.utc)

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

        usage.last_activity = datetime.now(timezone.utc)

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
            # Create Kubernetes namespace if k8s client is available
            await self._create_kubernetes_namespace(namespace, tenant)
            logger.debug(f"Provisioned namespace: {namespace}")

    async def _create_kubernetes_namespace(self, namespace: str, tenant: Tenant) -> bool:
        """
        إنشاء مساحة أسماء Kubernetes للمستأجر
        Create Kubernetes namespace for tenant
        """
        try:
            # Try to import kubernetes client
            try:
                from kubernetes import client
                from kubernetes import config as k8s_config
                from kubernetes.client.rest import ApiException
            except ImportError:
                logger.debug("Kubernetes client not available, skipping namespace creation")
                return False

            # Load config
            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                try:
                    k8s_config.load_kube_config()
                except k8s_config.ConfigException:
                    logger.debug("No Kubernetes config available")
                    return False

            v1 = client.CoreV1Api()

            # Check if namespace already exists
            try:
                v1.read_namespace(name=namespace)
                logger.debug(f"Namespace {namespace} already exists")
                return True
            except ApiException as e:
                if e.status != 404:
                    raise

            # Create namespace
            ns_manifest = client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name=namespace,
                    labels={
                        "app.kubernetes.io/managed-by": "nebulacompute",
                        "nebulacompute.io/tenant-id": tenant.id,
                        "nebulacompute.io/tenant-name": tenant.name,
                        "nebulacompute.io/tier": tenant.tier.value,
                    },
                    annotations={
                        "nebulacompute.io/created-at": tenant.created_at.isoformat(),
                        "nebulacompute.io/admin-email": tenant.admin_email or "",
                    },
                )
            )

            v1.create_namespace(body=ns_manifest)
            logger.info(f"Created Kubernetes namespace: {namespace}")
            return True

        except Exception as e:
            logger.warning(f"Failed to create Kubernetes namespace {namespace}: {e}")
            return False

    async def _cleanup_tenant(self, tenant: Tenant) -> None:
        """تنظيف موارد المستأجر"""
        # Cancel all jobs
        await self._cancel_tenant_jobs(tenant)

        # Delete Kubernetes namespace if exists
        if tenant.config.dedicated_namespace:
            await self._delete_kubernetes_namespace(tenant.config.dedicated_namespace)

        # Cleanup tenant storage
        await self._cleanup_tenant_storage(tenant)

        logger.debug(f"Cleaned up tenant: {tenant.name}")

    async def _delete_kubernetes_namespace(self, namespace: str) -> bool:
        """
        حذف مساحة أسماء Kubernetes
        Delete Kubernetes namespace
        """
        try:
            try:
                from kubernetes import client
                from kubernetes import config as k8s_config
                from kubernetes.client.rest import ApiException
            except ImportError:
                return False

            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                try:
                    k8s_config.load_kube_config()
                except k8s_config.ConfigException:
                    return False

            v1 = client.CoreV1Api()

            try:
                v1.delete_namespace(
                    name=namespace,
                    body=client.V1DeleteOptions(
                        propagation_policy="Foreground",
                        grace_period_seconds=30,
                    ),
                )
                logger.info(f"Deleted Kubernetes namespace: {namespace}")
                return True
            except ApiException as e:
                if e.status == 404:
                    logger.debug(f"Namespace {namespace} not found")
                    return True
                raise

        except Exception as e:
            logger.warning(f"Failed to delete Kubernetes namespace {namespace}: {e}")
            return False

    async def _cleanup_tenant_storage(self, tenant: Tenant) -> None:
        """
        تنظيف تخزين المستأجر
        Cleanup tenant storage
        """
        try:
            if self.storage:
                # Remove tenant-specific data
                await self.storage.delete(f"tenant:{tenant.id}:*")
                logger.debug(f"Cleaned up storage for tenant: {tenant.name}")
        except Exception as e:
            logger.warning(f"Failed to cleanup storage for tenant {tenant.name}: {e}")

    async def _cancel_tenant_jobs(self, tenant: Tenant) -> None:
        """
        إلغاء مهام المستأجر
        Cancel all jobs for a tenant
        """
        try:
            # Get scheduler instance if available
            scheduler = getattr(self, '_scheduler', None)
            if scheduler and hasattr(scheduler, 'cancel_jobs_by_tenant'):
                cancelled_count = await scheduler.cancel_jobs_by_tenant(tenant.id)
                logger.info(f"Cancelled {cancelled_count} jobs for tenant: {tenant.name}")
                return

            # Alternative: Use storage to mark jobs as cancelled
            if self.storage and hasattr(self.storage, 'query'):
                jobs = await self.storage.query(
                    "jobs",
                    {"tenant_id": tenant.id, "status": {"$in": ["pending", "running"]}}
                )
                cancelled_count = 0
                for job in jobs:
                    job["status"] = "cancelled"
                    job["cancelled_at"] = datetime.now(timezone.utc).isoformat()
                    job["cancellation_reason"] = f"Tenant {tenant.status.value}"
                    await self.storage.save(f"job:{job['id']}", job)
                    cancelled_count += 1

                logger.info(f"Cancelled {cancelled_count} jobs for tenant: {tenant.name}")
                tenant.usage.active_jobs = 0
            else:
                # Reset active jobs count as fallback
                tenant.usage.active_jobs = 0
                logger.debug(f"Reset active jobs for tenant: {tenant.name}")

        except Exception as e:
            logger.error(f"Failed to cancel jobs for tenant {tenant.name}: {e}")

    async def _check_quota_exceeded(self, tenant: Tenant) -> None:
        """فحص تجاوز الحصة"""
        usage_percent = tenant.quota_usage_percent

        # Check for quota exceeded
        exceeded = any(p >= 100 for p in usage_percent.values())
        if exceeded and tenant.status == TenantStatus.ACTIVE:
            tenant.status = TenantStatus.QUOTA_EXCEEDED
            tenant.updated_at = datetime.now(timezone.utc)
            logger.warning(f"Tenant {tenant.name} exceeded quota")

        # Check for warning
        elif self.config.notify_on_quota_warning:
            warning = any(p >= self.config.quota_warning_threshold * 100 for p in usage_percent.values())
            if warning:
                logger.info(f"Tenant {tenant.name} approaching quota limit")
                # Send quota warning notification
                await self._send_quota_warning_notification(tenant, usage_percent)

    async def _send_quota_warning_notification(
        self,
        tenant: Tenant,
        usage_percent: Dict[str, float],
    ) -> None:
        """
        إرسال إشعار تحذير الحصة
        Send quota warning notification
        """
        try:
            # Find resources approaching limit
            warning_resources = [
                f"{resource}: {percent:.1f}%"
                for resource, percent in usage_percent.items()
                if percent >= self.config.quota_warning_threshold * 100
            ]

            if not warning_resources:
                return

            # Build notification message
            message = {
                "type": "quota_warning",
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "tier": tenant.tier.value,
                "warning_resources": warning_resources,
                "usage_percent": usage_percent,
                "threshold": self.config.quota_warning_threshold * 100,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Send via configured notification channels
            if tenant.config.notification_emails:
                await self._send_email_notification(
                    emails=tenant.config.notification_emails,
                    subject=f"[NebulaCompute] Quota Warning for {tenant.display_name}",
                    body=self._format_quota_warning_email(tenant, warning_resources, usage_percent),
                )

            if tenant.config.slack_webhook:
                await self._send_slack_notification(
                    webhook_url=tenant.config.slack_webhook,
                    message=message,
                )

            if tenant.config.webhook_url:
                await self._send_webhook_notification(
                    webhook_url=tenant.config.webhook_url,
                    payload=message,
                )

            logger.debug(f"Sent quota warning notification for tenant: {tenant.name}")

        except Exception as e:
            logger.warning(f"Failed to send quota warning notification: {e}")

    def _format_quota_warning_email(
        self,
        tenant: Tenant,
        warning_resources: List[str],
        usage_percent: Dict[str, float],
    ) -> str:
        """Format quota warning email body"""
        return f"""
Quota Warning for Tenant: {tenant.display_name}
================================================

Your resource usage is approaching the quota limit:

{chr(10).join(f'  - {r}' for r in warning_resources)}

Current Usage:
  - Jobs: {usage_percent.get('jobs', 0):.1f}%
  - CPU: {usage_percent.get('cpu', 0):.1f}%
  - Memory: {usage_percent.get('memory', 0):.1f}%
  - GPU: {usage_percent.get('gpu', 0):.1f}%
  - Storage: {usage_percent.get('storage', 0):.1f}%

Tier: {tenant.tier.value}

Please consider upgrading your plan or reducing resource usage to avoid service interruption.

--
NebulaCompute Team
"""

    async def _send_email_notification(
        self,
        emails: List[str],
        subject: str,
        body: str,
    ) -> bool:
        """Send email notification (placeholder for email integration)"""
        # This would integrate with an email service like SMTP, SendGrid, etc.
        logger.debug(f"Email notification: {subject} to {emails}")
        return True

    async def _send_slack_notification(
        self,
        webhook_url: str,
        message: Dict[str, Any],
    ) -> bool:
        """Send Slack notification"""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json={
                        "text": f":warning: Quota Warning for {message['tenant_name']}",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": (
                                        f"*Quota Warning*\n"
                                        f"Tenant: {message['tenant_name']}\n"
                                        f"Resources: {', '.join(message['warning_resources'])}"
                                    ),
                                },
                            }
                        ],
                    },
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Failed to send Slack notification: {e}")
            return False

    async def _send_webhook_notification(
        self,
        webhook_url: str,
        payload: Dict[str, Any],
    ) -> bool:
        """Send webhook notification"""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    timeout=10.0,
                )
                return response.status_code in (200, 201, 202, 204)
        except Exception as e:
            logger.warning(f"Failed to send webhook notification: {e}")
            return False

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

                now = datetime.now(timezone.utc)
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
