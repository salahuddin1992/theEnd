"""
Tenant Isolation - عزل المستأجرين
===================================

Tenant isolation and security boundaries.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IsolationLevel(str, Enum):
    """مستوى العزل"""
    SHARED = "shared"           # مشترك - نفس مساحة الأسماء
    NAMESPACE = "namespace"     # معزول بمساحة أسماء
    DEDICATED = "dedicated"     # معزول بعقد مخصصة
    CLUSTER = "cluster"         # كلاستر منفصل


@dataclass
class IsolationPolicy:
    """سياسة العزل"""
    level: IsolationLevel
    network_isolated: bool = False
    storage_isolated: bool = False
    compute_isolated: bool = False

    # Network policies
    allow_egress: bool = True
    allow_ingress: bool = False
    allowed_namespaces: List[str] = None
    allowed_ips: List[str] = None
    blocked_ips: List[str] = None

    # Resource isolation
    dedicated_nodes: List[str] = None
    node_selector: Dict[str, str] = None
    tolerations: List[Dict[str, Any]] = None

    def __post_init__(self):
        self.allowed_namespaces = self.allowed_namespaces or []
        self.allowed_ips = self.allowed_ips or []
        self.blocked_ips = self.blocked_ips or []
        self.dedicated_nodes = self.dedicated_nodes or []
        self.node_selector = self.node_selector or {}
        self.tolerations = self.tolerations or []


class TenantIsolator:
    """
    عازل المستأجرين
    Tenant Isolator

    يضمن عزل المستأجرين حسب السياسة المحددة.
    Ensures tenant isolation according to policy.
    """

    def __init__(self):
        self._policies: Dict[str, IsolationPolicy] = {}

    def set_policy(self, tenant_id: str, policy: IsolationPolicy) -> None:
        """تعيين سياسة العزل"""
        self._policies[tenant_id] = policy
        logger.info(f"Set isolation policy for {tenant_id}: {policy.level.value}")

    def get_policy(self, tenant_id: str) -> Optional[IsolationPolicy]:
        """الحصول على سياسة العزل"""
        return self._policies.get(tenant_id)

    def check_access(
        self,
        source_tenant: str,
        target_tenant: str,
        access_type: str = "read",
    ) -> bool:
        """
        فحص الوصول بين المستأجرين
        Check access between tenants
        """
        if source_tenant == target_tenant:
            return True

        source_policy = self._policies.get(source_tenant)
        target_policy = self._policies.get(target_tenant)

        # If either has dedicated isolation, deny cross-tenant access
        if source_policy and source_policy.level in (IsolationLevel.DEDICATED, IsolationLevel.CLUSTER):
            return False
        if target_policy and target_policy.level in (IsolationLevel.DEDICATED, IsolationLevel.CLUSTER):
            return False

        return False  # Default deny

    def get_namespace(self, tenant_id: str, prefix: str = "nc-") -> str:
        """الحصول على مساحة الأسماء"""
        policy = self._policies.get(tenant_id)
        if policy and policy.level != IsolationLevel.SHARED:
            return f"{prefix}{tenant_id}"
        return "default"

    def get_node_selector(self, tenant_id: str) -> Dict[str, str]:
        """الحصول على محدد العقد"""
        policy = self._policies.get(tenant_id)
        if policy and policy.node_selector:
            return policy.node_selector
        if policy and policy.level == IsolationLevel.DEDICATED:
            return {"dedicated-tenant": tenant_id}
        return {}

    def get_network_policy(self, tenant_id: str) -> Dict[str, Any]:
        """
        الحصول على سياسة الشبكة
        Get network policy for Kubernetes
        """
        policy = self._policies.get(tenant_id)
        if not policy or not policy.network_isolated:
            return {}

        namespace = self.get_namespace(tenant_id)

        network_policy = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": f"tenant-{tenant_id}-isolation",
                "namespace": namespace,
            },
            "spec": {
                "podSelector": {},
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [],
                "egress": [],
            },
        }

        # Allow ingress from same namespace
        network_policy["spec"]["ingress"].append({
            "from": [{"podSelector": {}}]
        })

        # Allow egress if permitted
        if policy.allow_egress:
            network_policy["spec"]["egress"].append({
                "to": [{"podSelector": {}}]  # Same namespace
            })
            # Allow DNS
            network_policy["spec"]["egress"].append({
                "to": [{"namespaceSelector": {"matchLabels": {"name": "kube-system"}}}],
                "ports": [{"protocol": "UDP", "port": 53}],
            })

        # Add allowed namespaces
        for ns in policy.allowed_namespaces:
            network_policy["spec"]["ingress"].append({
                "from": [{"namespaceSelector": {"matchLabels": {"name": ns}}}]
            })

        # Add allowed IPs for egress
        if policy.allowed_ips:
            for ip in policy.allowed_ips:
                network_policy["spec"]["egress"].append({
                    "to": [{"ipBlock": {"cidr": ip}}]
                })

        return network_policy

    def validate_job_submission(
        self,
        tenant_id: str,
        job_spec: Dict[str, Any],
    ) -> tuple[bool, List[str]]:
        """
        التحقق من صحة إرسال المهمة
        Validate job submission against isolation policy
        """
        policy = self._policies.get(tenant_id)
        errors = []

        if not policy:
            return True, []

        # Check image restrictions
        if policy.level in (IsolationLevel.DEDICATED, IsolationLevel.NAMESPACE):
            image = job_spec.get("image", "")
            # TODO: Add image registry validation
            pass

        # Check network access
        if policy.network_isolated and not policy.allow_egress:
            if job_spec.get("needs_network", False):
                errors.append("Network access not allowed for this tenant")

        # Check resource requests against dedicated nodes
        if policy.level == IsolationLevel.DEDICATED:
            resources = job_spec.get("resources", {})
            # TODO: Validate against dedicated node capacity
            pass

        return len(errors) == 0, errors

    def apply_isolation_to_job(
        self,
        tenant_id: str,
        job_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        تطبيق العزل على المهمة
        Apply isolation settings to job spec
        """
        policy = self._policies.get(tenant_id)
        if not policy:
            return job_spec

        # Set namespace
        job_spec["namespace"] = self.get_namespace(tenant_id)

        # Set node selector
        node_selector = self.get_node_selector(tenant_id)
        if node_selector:
            job_spec["nodeSelector"] = node_selector

        # Set tolerations
        if policy.tolerations:
            job_spec["tolerations"] = policy.tolerations

        # Add tenant labels
        if "labels" not in job_spec:
            job_spec["labels"] = {}
        job_spec["labels"]["tenant"] = tenant_id
        job_spec["labels"]["isolation-level"] = policy.level.value

        return job_spec
