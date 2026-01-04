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
            # Validate image registry
            if not self._validate_image_registry(tenant_id, image, policy):
                errors.append(f"Image '{image}' not allowed by tenant isolation policy")

        # Check network access
        if policy.network_isolated and not policy.allow_egress:
            if job_spec.get("needs_network", False):
                errors.append("Network access not allowed for this tenant")

        # Check resource requests against dedicated nodes
        if policy.level == IsolationLevel.DEDICATED:
            resources = job_spec.get("resources", {})
            # Validate against dedicated node capacity
            capacity_valid, capacity_error = self._validate_dedicated_node_capacity(
                tenant_id, resources, policy
            )
            if not capacity_valid:
                errors.append(capacity_error)

        return len(errors) == 0, errors

    def _validate_image_registry(
        self,
        tenant_id: str,
        image: str,
        policy: IsolationPolicy,
    ) -> bool:
        """
        التحقق من صحة سجل الصور
        Validate image registry against tenant policy

        Args:
            tenant_id: Tenant identifier
            image: Container image name
            policy: Tenant isolation policy

        Returns:
            True if image is allowed
        """
        if not image:
            return False

        # Default allowed registries
        default_allowed = [
            "docker.io",
            "gcr.io",
            "ghcr.io",
            "quay.io",
            "registry.k8s.io",
        ]

        # Get allowed registries from policy metadata
        allowed_registries = (
            policy.metadata.get("allowed_registries", default_allowed)
            if hasattr(policy, 'metadata')
            else default_allowed
        )

        # Parse image to extract registry
        registry = self._extract_registry(image)

        # Check if registry is allowed
        if registry in allowed_registries:
            return True

        # Check for private registry patterns
        if policy.level == IsolationLevel.DEDICATED:
            # Dedicated tenants can use private registries
            private_registry_pattern = f"{tenant_id}.registry"
            if registry.startswith(private_registry_pattern):
                return True

        return False

    def _extract_registry(self, image: str) -> str:
        """Extract registry from image name"""
        # Handle images like "nginx" (docker.io), "gcr.io/project/image"
        if "/" not in image:
            return "docker.io"

        parts = image.split("/")
        first_part = parts[0]

        # Check if first part looks like a registry (contains . or :)
        if "." in first_part or ":" in first_part:
            return first_part.split(":")[0]

        # Otherwise it's docker.io with a namespace
        return "docker.io"

    def _validate_dedicated_node_capacity(
        self,
        tenant_id: str,
        resources: Dict[str, Any],
        policy: IsolationPolicy,
    ) -> tuple[bool, str]:
        """
        التحقق من سعة العقد المخصصة
        Validate resources against dedicated node capacity

        Args:
            tenant_id: Tenant identifier
            resources: Requested resources
            policy: Tenant isolation policy

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not policy.dedicated_nodes:
            return True, ""

        # Get requested resources
        requested_cpu = resources.get("cpu", 0)
        requested_memory = resources.get("memory_mb", 0)
        requested_gpu = resources.get("gpu", 0)

        # Get dedicated node capacity from policy metadata
        node_capacity = getattr(policy, 'metadata', {}).get("node_capacity", {}) if hasattr(policy, 'metadata') else {}

        if not node_capacity:
            # If no capacity info, assume sufficient capacity
            return True, ""

        total_cpu = node_capacity.get("total_cpu", float("inf"))
        total_memory = node_capacity.get("total_memory_mb", float("inf"))
        total_gpu = node_capacity.get("total_gpu", float("inf"))
        used_cpu = node_capacity.get("used_cpu", 0)
        used_memory = node_capacity.get("used_memory_mb", 0)
        used_gpu = node_capacity.get("used_gpu", 0)

        available_cpu = total_cpu - used_cpu
        available_memory = total_memory - used_memory
        available_gpu = total_gpu - used_gpu

        # Check CPU
        if requested_cpu > available_cpu:
            return False, f"Insufficient CPU: requested {requested_cpu}, available {available_cpu}"

        # Check Memory
        if requested_memory > available_memory:
            return False, f"Insufficient memory: requested {requested_memory}MB, available {available_memory}MB"

        # Check GPU
        if requested_gpu > available_gpu:
            return False, f"Insufficient GPU: requested {requested_gpu}, available {available_gpu}"

        return True, ""

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
