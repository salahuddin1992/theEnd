"""
Multi-Tenancy Module - وحدة تعدد المستأجرين
=============================================

Enterprise multi-tenancy support for NebulaCompute.
دعم تعدد المستأجرين للمؤسسات.

Features | الميزات:
- Tenant isolation (namespace, resource, network)
- Resource quotas and limits
- Billing and cost tracking
- Tenant-specific configurations
- Cross-tenant admin access

Author: NebulaCompute Team
License: MIT
"""

from distributed_cluster.multitenancy.tenant import (
    Tenant,
    TenantStatus,
    TenantTier,
    TenantConfig,
)
from distributed_cluster.multitenancy.manager import (
    TenantManager,
    TenantManagerConfig,
)
from distributed_cluster.multitenancy.quotas import (
    ResourceQuota,
    QuotaManager,
    QuotaEnforcer,
)
from distributed_cluster.multitenancy.isolation import (
    IsolationLevel,
    TenantIsolator,
)
from distributed_cluster.multitenancy.billing import (
    BillingManager,
    UsageTracker,
    Invoice,
)

__all__ = [
    # Tenant
    "Tenant",
    "TenantStatus",
    "TenantTier",
    "TenantConfig",
    # Manager
    "TenantManager",
    "TenantManagerConfig",
    # Quotas
    "ResourceQuota",
    "QuotaManager",
    "QuotaEnforcer",
    # Isolation
    "IsolationLevel",
    "TenantIsolator",
    # Billing
    "BillingManager",
    "UsageTracker",
    "Invoice",
]
