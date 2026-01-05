"""
Tenant Model - نموذج المستأجر
==============================

Tenant data model and configuration.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TenantStatus(str, Enum):
    """حالة المستأجر"""

    PENDING = "pending"  # قيد الإنشاء
    ACTIVE = "active"  # نشط
    SUSPENDED = "suspended"  # معلق
    QUOTA_EXCEEDED = "quota_exceeded"  # تجاوز الحصة
    TERMINATING = "terminating"  # قيد الإنهاء
    TERMINATED = "terminated"  # منتهي


class TenantTier(str, Enum):
    """مستوى المستأجر"""

    FREE = "free"  # مجاني
    STARTER = "starter"  # مبتدئ
    PROFESSIONAL = "professional"  # محترف
    ENTERPRISE = "enterprise"  # مؤسسة
    CUSTOM = "custom"  # مخصص


@dataclass
class TenantQuotas:
    """حصص المستأجر"""

    # Job limits
    max_concurrent_jobs: int = 10
    max_jobs_per_day: int = 100
    max_job_duration_seconds: int = 86400  # 24 hours
    max_job_retries: int = 3

    # Resource limits
    max_cpu_cores: float = 100.0
    max_memory_mb: int = 204800  # 200 GB
    max_gpu_count: int = 4
    max_storage_mb: int = 524288  # 500 GB

    # Worker limits
    max_dedicated_workers: int = 10

    # Rate limits
    api_requests_per_minute: int = 1000
    api_requests_per_day: int = 100000

    # Network limits
    max_bandwidth_mbps: int = 1000
    max_egress_gb_per_month: int = 1000

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس"""
        return {
            "maxConcurrentJobs": self.max_concurrent_jobs,
            "maxJobsPerDay": self.max_jobs_per_day,
            "maxJobDurationSeconds": self.max_job_duration_seconds,
            "maxJobRetries": self.max_job_retries,
            "maxCpuCores": self.max_cpu_cores,
            "maxMemoryMb": self.max_memory_mb,
            "maxGpuCount": self.max_gpu_count,
            "maxStorageMb": self.max_storage_mb,
            "maxDedicatedWorkers": self.max_dedicated_workers,
            "apiRequestsPerMinute": self.api_requests_per_minute,
            "apiRequestsPerDay": self.api_requests_per_day,
        }

    @classmethod
    def from_tier(cls, tier: TenantTier) -> "TenantQuotas":
        """إنشاء حصص حسب المستوى"""
        tier_quotas = {
            TenantTier.FREE: cls(
                max_concurrent_jobs=2,
                max_jobs_per_day=10,
                max_cpu_cores=4.0,
                max_memory_mb=8192,
                max_gpu_count=0,
                max_storage_mb=10240,
                max_dedicated_workers=0,
                api_requests_per_minute=60,
            ),
            TenantTier.STARTER: cls(
                max_concurrent_jobs=10,
                max_jobs_per_day=100,
                max_cpu_cores=32.0,
                max_memory_mb=65536,
                max_gpu_count=1,
                max_storage_mb=102400,
                max_dedicated_workers=2,
                api_requests_per_minute=300,
            ),
            TenantTier.PROFESSIONAL: cls(
                max_concurrent_jobs=50,
                max_jobs_per_day=500,
                max_cpu_cores=128.0,
                max_memory_mb=262144,
                max_gpu_count=4,
                max_storage_mb=524288,
                max_dedicated_workers=10,
                api_requests_per_minute=1000,
            ),
            TenantTier.ENTERPRISE: cls(
                max_concurrent_jobs=500,
                max_jobs_per_day=10000,
                max_cpu_cores=1000.0,
                max_memory_mb=2097152,
                max_gpu_count=100,
                max_storage_mb=10485760,
                max_dedicated_workers=100,
                api_requests_per_minute=10000,
            ),
        }
        return tier_quotas.get(tier, cls())


@dataclass
class TenantUsage:
    """استخدام المستأجر الحالي"""

    # Jobs
    active_jobs: int = 0
    jobs_today: int = 0
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0

    # Resources
    cpu_used: float = 0.0
    memory_used_mb: int = 0
    gpu_used: int = 0
    storage_used_mb: int = 0

    # Workers
    dedicated_workers: int = 0

    # API
    api_requests_today: int = 0
    api_requests_this_minute: int = 0

    # Cost
    current_month_cost: float = 0.0
    total_cost: float = 0.0

    # Timestamps
    last_activity: Optional[datetime] = None
    last_job_submitted: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس"""
        return {
            "activeJobs": self.active_jobs,
            "jobsToday": self.jobs_today,
            "totalJobs": self.total_jobs,
            "completedJobs": self.completed_jobs,
            "failedJobs": self.failed_jobs,
            "cpuUsed": self.cpu_used,
            "memoryUsedMb": self.memory_used_mb,
            "gpuUsed": self.gpu_used,
            "storageUsedMb": self.storage_used_mb,
            "dedicatedWorkers": self.dedicated_workers,
            "currentMonthCost": self.current_month_cost,
            "lastActivity": self.last_activity.isoformat() if self.last_activity else None,
        }


@dataclass
class TenantConfig:
    """تكوين المستأجر"""

    # Scheduling
    default_priority: int = 50
    priority_boost: int = 0

    # Isolation
    isolation_level: str = "shared"  # shared, namespace, dedicated
    dedicated_namespace: Optional[str] = None

    # Notifications
    notification_emails: List[str] = field(default_factory=list)
    slack_webhook: Optional[str] = None
    webhook_url: Optional[str] = None

    # Features
    gpu_enabled: bool = True
    docker_enabled: bool = True
    custom_images_allowed: bool = False
    network_access_enabled: bool = True

    # Security
    allowed_ip_ranges: List[str] = field(default_factory=list)
    require_mfa: bool = False
    api_key_enabled: bool = True

    # Labels and tags
    labels: Dict[str, str] = field(default_factory=dict)
    default_job_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس"""
        return {
            "defaultPriority": self.default_priority,
            "priorityBoost": self.priority_boost,
            "isolationLevel": self.isolation_level,
            "dedicatedNamespace": self.dedicated_namespace,
            "notificationEmails": self.notification_emails,
            "gpuEnabled": self.gpu_enabled,
            "dockerEnabled": self.docker_enabled,
            "customImagesAllowed": self.custom_images_allowed,
            "labels": self.labels,
        }


@dataclass
class Tenant:
    """
    نموذج المستأجر
    Tenant Model
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    display_name: str = ""
    description: str = ""

    # Status
    status: TenantStatus = TenantStatus.PENDING
    tier: TenantTier = TenantTier.FREE

    # Admin
    admin_user_id: Optional[str] = None
    admin_email: Optional[str] = None
    owner_organization: Optional[str] = None

    # Quotas and usage
    quotas: TenantQuotas = field(default_factory=TenantQuotas)
    usage: TenantUsage = field(default_factory=TenantUsage)
    config: TenantConfig = field(default_factory=TenantConfig)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    suspension_reason: Optional[str] = None

    # Billing
    billing_enabled: bool = False
    billing_email: Optional[str] = None
    payment_method_id: Optional[str] = None
    credit_balance: float = 0.0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name

    @property
    def is_active(self) -> bool:
        """هل المستأجر نشط؟"""
        return self.status == TenantStatus.ACTIVE

    @property
    def is_suspended(self) -> bool:
        """هل المستأجر معلق؟"""
        return self.status == TenantStatus.SUSPENDED

    @property
    def can_submit_jobs(self) -> bool:
        """هل يمكن إرسال مهام؟"""
        if not self.is_active:
            return False
        if self.usage.active_jobs >= self.quotas.max_concurrent_jobs:
            return False
        if self.usage.jobs_today >= self.quotas.max_jobs_per_day:
            return False
        return True

    @property
    def quota_usage_percent(self) -> Dict[str, float]:
        """نسبة استخدام الحصص"""

        def safe_percent(used: float, max_val: float) -> float:
            return (used / max_val * 100) if max_val > 0 else 0

        return {
            "jobs": safe_percent(self.usage.active_jobs, self.quotas.max_concurrent_jobs),
            "cpu": safe_percent(self.usage.cpu_used, self.quotas.max_cpu_cores),
            "memory": safe_percent(self.usage.memory_used_mb, self.quotas.max_memory_mb),
            "gpu": safe_percent(self.usage.gpu_used, self.quotas.max_gpu_count),
            "storage": safe_percent(self.usage.storage_used_mb, self.quotas.max_storage_mb),
            "workers": safe_percent(self.usage.dedicated_workers, self.quotas.max_dedicated_workers),
        }

    def check_quota(self, resource: str, requested: float) -> tuple[bool, str]:
        """
        فحص الحصة لمورد معين
        Check quota for resource
        """
        usage_map = {
            "cpu": (self.usage.cpu_used, self.quotas.max_cpu_cores),
            "memory": (self.usage.memory_used_mb, self.quotas.max_memory_mb),
            "gpu": (self.usage.gpu_used, self.quotas.max_gpu_count),
            "storage": (self.usage.storage_used_mb, self.quotas.max_storage_mb),
            "jobs": (self.usage.active_jobs, self.quotas.max_concurrent_jobs),
        }

        if resource not in usage_map:
            return True, ""

        current, maximum = usage_map[resource]
        if current + requested > maximum:
            return False, f"Quota exceeded for {resource}: {current + requested} > {maximum}"

        return True, ""

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس"""
        return {
            "id": self.id,
            "name": self.name,
            "displayName": self.display_name,
            "description": self.description,
            "status": self.status.value,
            "tier": self.tier.value,
            "adminEmail": self.admin_email,
            "quotas": self.quotas.to_dict(),
            "usage": self.usage.to_dict(),
            "config": self.config.to_dict(),
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            "isActive": self.is_active,
            "canSubmitJobs": self.can_submit_jobs,
            "quotaUsagePercent": self.quota_usage_percent,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Tenant":
        """إنشاء من قاموس"""
        tenant = cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            display_name=data.get("displayName", data.get("name", "")),
            description=data.get("description", ""),
            status=TenantStatus(data.get("status", "pending")),
            tier=TenantTier(data.get("tier", "free")),
            admin_email=data.get("adminEmail"),
        )
        return tenant
