"""
Security Policy Engine - محرك سياسات الأمان
=============================================

Comprehensive policy engine for cluster-wide security enforcement.
محرك سياسات شامل لفرض الأمان على مستوى المجموعة.

Features:
- Policy-based access control
- Network security policies
- Resource access policies
- Time-based access rules
- Risk-based authentication
- Compliance enforcement
"""

from __future__ import annotations

import fnmatch
import ipaddress
import logging
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PolicyEffect(str, Enum):
    """Policy effect."""
    ALLOW = "allow"
    DENY = "deny"
    AUDIT = "audit"  # Log but don't enforce


class PolicyPriority(int, Enum):
    """Policy priority levels."""
    EMERGENCY = 0  # Highest - security incidents
    CRITICAL = 10
    HIGH = 20
    MEDIUM = 50  # Default
    LOW = 80
    BASELINE = 100  # Lowest - default policies


class ConditionOperator(str, Enum):
    """Condition operators."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"  # Regex
    IN = "in"
    NOT_IN = "not_in"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    BETWEEN = "between"
    IP_IN_RANGE = "ip_in_range"
    TIME_BETWEEN = "time_between"


@dataclass
class PolicyCondition:
    """Single policy condition."""
    field: str  # Field to evaluate (e.g., "request.ip", "user.role")
    operator: ConditionOperator
    value: Any  # Expected value
    negate: bool = False

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate condition against context."""
        actual = self._get_field_value(context, self.field)
        result = self._evaluate_operator(actual)
        return not result if self.negate else result

    def _get_field_value(self, context: Dict[str, Any], field_path: str) -> Any:
        """Get nested field value from context."""
        parts = field_path.split(".")
        value = context

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                return None

        return value

    def _evaluate_operator(self, actual: Any) -> bool:
        """Evaluate the condition operator."""
        if actual is None:
            return False

        if self.operator == ConditionOperator.EQUALS:
            return actual == self.value

        elif self.operator == ConditionOperator.NOT_EQUALS:
            return actual != self.value

        elif self.operator == ConditionOperator.CONTAINS:
            if isinstance(actual, str):
                return self.value in actual
            elif isinstance(actual, (list, set)):
                return self.value in actual
            return False

        elif self.operator == ConditionOperator.NOT_CONTAINS:
            if isinstance(actual, str):
                return self.value not in actual
            elif isinstance(actual, (list, set)):
                return self.value not in actual
            return True

        elif self.operator == ConditionOperator.STARTS_WITH:
            return str(actual).startswith(str(self.value))

        elif self.operator == ConditionOperator.ENDS_WITH:
            return str(actual).endswith(str(self.value))

        elif self.operator == ConditionOperator.MATCHES:
            try:
                return bool(re.match(self.value, str(actual)))
            except re.error:
                return False

        elif self.operator == ConditionOperator.IN:
            return actual in self.value

        elif self.operator == ConditionOperator.NOT_IN:
            return actual not in self.value

        elif self.operator == ConditionOperator.GREATER_THAN:
            return actual > self.value

        elif self.operator == ConditionOperator.LESS_THAN:
            return actual < self.value

        elif self.operator == ConditionOperator.BETWEEN:
            if isinstance(self.value, (list, tuple)) and len(self.value) == 2:
                return self.value[0] <= actual <= self.value[1]
            return False

        elif self.operator == ConditionOperator.IP_IN_RANGE:
            try:
                ip = ipaddress.ip_address(actual)
                for range_str in (self.value if isinstance(self.value, list) else [self.value]):
                    if "/" in range_str:
                        network = ipaddress.ip_network(range_str, strict=False)
                        if ip in network:
                            return True
                    elif ip == ipaddress.ip_address(range_str):
                        return True
                return False
            except (ValueError, TypeError):
                return False

        elif self.operator == ConditionOperator.TIME_BETWEEN:
            try:
                now = datetime.now(timezone.utc).time()
                start = datetime.strptime(self.value[0], "%H:%M").time()
                end = datetime.strptime(self.value[1], "%H:%M").time()

                if start <= end:
                    return start <= now <= end
                else:  # Wraps midnight
                    return now >= start or now <= end
            except (ValueError, IndexError, TypeError):
                return False

        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value,
            "negate": self.negate,
        }


@dataclass
class PolicyRule:
    """Policy rule with conditions and effect."""
    rule_id: str
    name: str
    effect: PolicyEffect
    conditions: List[PolicyCondition] = field(default_factory=list)
    condition_logic: str = "all"  # "all" (AND) or "any" (OR)
    description: str = ""
    enabled: bool = True

    def evaluate(self, context: Dict[str, Any]) -> Optional[PolicyEffect]:
        """
        Evaluate rule against context.

        Returns effect if conditions match, None otherwise.
        """
        if not self.enabled:
            return None

        if not self.conditions:
            return self.effect

        if self.condition_logic == "any":
            if any(c.evaluate(context) for c in self.conditions):
                return self.effect
        else:  # all
            if all(c.evaluate(context) for c in self.conditions):
                return self.effect

        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "effect": self.effect.value,
            "conditions": [c.to_dict() for c in self.conditions],
            "condition_logic": self.condition_logic,
            "description": self.description,
            "enabled": self.enabled,
        }


@dataclass
class SecurityPolicy:
    """Security policy with multiple rules."""
    policy_id: str
    name: str
    description: str = ""
    priority: PolicyPriority = PolicyPriority.MEDIUM
    enabled: bool = True
    rules: List[PolicyRule] = field(default_factory=list)

    # Targeting
    targets: Dict[str, List[str]] = field(default_factory=dict)  # resource_type -> patterns

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    version: int = 1

    def matches_target(self, resource_type: str, resource_id: str) -> bool:
        """Check if policy targets this resource."""
        if not self.targets:
            return True  # No targets = applies to all

        patterns = self.targets.get(resource_type, [])
        if not patterns:
            return False

        for pattern in patterns:
            if pattern == "*" or fnmatch.fnmatch(resource_id, pattern):
                return True

        return False

    def evaluate(
        self,
        context: Dict[str, Any],
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> Tuple[Optional[PolicyEffect], Optional[PolicyRule]]:
        """
        Evaluate policy against context.

        Returns:
            (effect, matching_rule)
        """
        if not self.enabled:
            return None, None

        if resource_type and resource_id:
            if not self.matches_target(resource_type, resource_id):
                return None, None

        for rule in self.rules:
            effect = rule.evaluate(context)
            if effect is not None:
                return effect, rule

        return None, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority.value,
            "enabled": self.enabled,
            "rules": [r.to_dict() for r in self.rules],
            "targets": self.targets,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
        }


@dataclass
class PolicyDecision:
    """Result of policy evaluation."""
    allowed: bool
    effect: PolicyEffect
    policy_id: Optional[str] = None
    rule_id: Optional[str] = None
    reason: str = ""
    audit_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "effect": self.effect.value,
            "policy_id": self.policy_id,
            "rule_id": self.rule_id,
            "reason": self.reason,
        }


class PolicyStore(ABC):
    """Abstract policy store."""

    @abstractmethod
    def add_policy(self, policy: SecurityPolicy) -> bool:
        pass

    @abstractmethod
    def get_policy(self, policy_id: str) -> Optional[SecurityPolicy]:
        pass

    @abstractmethod
    def update_policy(self, policy: SecurityPolicy) -> bool:
        pass

    @abstractmethod
    def delete_policy(self, policy_id: str) -> bool:
        pass

    @abstractmethod
    def list_policies(self, enabled_only: bool = True) -> List[SecurityPolicy]:
        pass


class MemoryPolicyStore(PolicyStore):
    """In-memory policy store."""

    def __init__(self):
        self._policies: Dict[str, SecurityPolicy] = {}
        self._lock = threading.RLock()

    def add_policy(self, policy: SecurityPolicy) -> bool:
        with self._lock:
            if policy.policy_id in self._policies:
                return False
            self._policies[policy.policy_id] = policy
            return True

    def get_policy(self, policy_id: str) -> Optional[SecurityPolicy]:
        with self._lock:
            return self._policies.get(policy_id)

    def update_policy(self, policy: SecurityPolicy) -> bool:
        with self._lock:
            if policy.policy_id not in self._policies:
                return False
            policy.updated_at = datetime.now(timezone.utc)
            policy.version += 1
            self._policies[policy.policy_id] = policy
            return True

    def delete_policy(self, policy_id: str) -> bool:
        with self._lock:
            if policy_id in self._policies:
                del self._policies[policy_id]
                return True
            return False

    def list_policies(self, enabled_only: bool = True) -> List[SecurityPolicy]:
        with self._lock:
            policies = list(self._policies.values())
            if enabled_only:
                policies = [p for p in policies if p.enabled]
            return sorted(policies, key=lambda p: p.priority.value)


class PolicyEngine:
    """
    Security Policy Engine.

    Evaluates security policies for access control decisions.
    """

    def __init__(
        self,
        store: Optional[PolicyStore] = None,
        default_effect: PolicyEffect = PolicyEffect.DENY,
        audit_callback: Optional[Callable[[PolicyDecision, Dict], None]] = None,
    ):
        self.store = store or MemoryPolicyStore()
        self.default_effect = default_effect
        self.audit_callback = audit_callback
        self._lock = threading.RLock()

        # Initialize default policies
        self._init_default_policies()

    def _init_default_policies(self) -> None:
        """Initialize default security policies."""
        # Default deny-all policy
        default_policy = SecurityPolicy(
            policy_id="default-deny",
            name="Default Deny Policy",
            description="Deny all unmatched requests",
            priority=PolicyPriority.BASELINE,
            rules=[
                PolicyRule(
                    rule_id="deny-all",
                    name="Deny All",
                    effect=PolicyEffect.DENY,
                ),
            ],
        )
        self.store.add_policy(default_policy)

    def evaluate(
        self,
        context: Dict[str, Any],
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> PolicyDecision:
        """
        Evaluate all policies against context.

        Returns the first matching decision.
        """
        policies = self.store.list_policies(enabled_only=True)

        for policy in policies:
            effect, rule = policy.evaluate(context, resource_type, resource_id)

            if effect is not None:
                decision = PolicyDecision(
                    allowed=effect == PolicyEffect.ALLOW,
                    effect=effect,
                    policy_id=policy.policy_id,
                    rule_id=rule.rule_id if rule else None,
                    reason=rule.description if rule else "",
                )

                # Audit if needed
                if effect == PolicyEffect.AUDIT or self.audit_callback:
                    self._audit_decision(decision, context)

                if effect != PolicyEffect.AUDIT:
                    return decision

        # No matching policy - use default
        return PolicyDecision(
            allowed=self.default_effect == PolicyEffect.ALLOW,
            effect=self.default_effect,
            reason="No matching policy - default effect applied",
        )

    def _audit_decision(self, decision: PolicyDecision, context: Dict[str, Any]) -> None:
        """Record audit for policy decision."""
        if self.audit_callback:
            try:
                self.audit_callback(decision, context)
            except Exception as e:
                logger.error(f"Policy audit callback error: {e}")

    def add_policy(self, policy: SecurityPolicy) -> bool:
        """Add a security policy."""
        result = self.store.add_policy(policy)
        if result:
            logger.info(f"Added policy: {policy.name} ({policy.policy_id})")
        return result

    def update_policy(self, policy: SecurityPolicy) -> bool:
        """Update a security policy."""
        result = self.store.update_policy(policy)
        if result:
            logger.info(f"Updated policy: {policy.name} ({policy.policy_id})")
        return result

    def delete_policy(self, policy_id: str) -> bool:
        """Delete a security policy."""
        result = self.store.delete_policy(policy_id)
        if result:
            logger.info(f"Deleted policy: {policy_id}")
        return result

    def get_policy(self, policy_id: str) -> Optional[SecurityPolicy]:
        """Get a policy by ID."""
        return self.store.get_policy(policy_id)

    def list_policies(self) -> List[SecurityPolicy]:
        """List all policies."""
        return self.store.list_policies(enabled_only=False)


# ====================== Pre-built Policies ======================


class NetworkSecurityPolicies:
    """Pre-built network security policies."""

    @staticmethod
    def create_ip_whitelist_policy(
        policy_id: str,
        name: str,
        allowed_ips: List[str],
        priority: PolicyPriority = PolicyPriority.HIGH,
    ) -> SecurityPolicy:
        """Create IP whitelist policy."""
        return SecurityPolicy(
            policy_id=policy_id,
            name=name,
            description=f"Allow access from whitelisted IPs: {allowed_ips}",
            priority=priority,
            rules=[
                PolicyRule(
                    rule_id=f"{policy_id}-allow",
                    name="Allow Whitelisted IPs",
                    effect=PolicyEffect.ALLOW,
                    conditions=[
                        PolicyCondition(
                            field="request.ip",
                            operator=ConditionOperator.IP_IN_RANGE,
                            value=allowed_ips,
                        ),
                    ],
                ),
            ],
        )

    @staticmethod
    def create_ip_blacklist_policy(
        policy_id: str,
        name: str,
        blocked_ips: List[str],
        priority: PolicyPriority = PolicyPriority.CRITICAL,
    ) -> SecurityPolicy:
        """Create IP blacklist policy."""
        return SecurityPolicy(
            policy_id=policy_id,
            name=name,
            description="Block access from blacklisted IPs",
            priority=priority,
            rules=[
                PolicyRule(
                    rule_id=f"{policy_id}-block",
                    name="Block Blacklisted IPs",
                    effect=PolicyEffect.DENY,
                    conditions=[
                        PolicyCondition(
                            field="request.ip",
                            operator=ConditionOperator.IP_IN_RANGE,
                            value=blocked_ips,
                        ),
                    ],
                ),
            ],
        )


class AccessControlPolicies:
    """Pre-built access control policies."""

    @staticmethod
    def create_role_based_policy(
        policy_id: str,
        name: str,
        role: str,
        allowed_actions: List[str],
        resource_patterns: Optional[Dict[str, List[str]]] = None,
        priority: PolicyPriority = PolicyPriority.MEDIUM,
    ) -> SecurityPolicy:
        """Create role-based access policy."""
        return SecurityPolicy(
            policy_id=policy_id,
            name=name,
            description=f"Allow {role} to perform {allowed_actions}",
            priority=priority,
            targets=resource_patterns or {},
            rules=[
                PolicyRule(
                    rule_id=f"{policy_id}-allow",
                    name=f"Allow {role}",
                    effect=PolicyEffect.ALLOW,
                    conditions=[
                        PolicyCondition(
                            field="user.role",
                            operator=ConditionOperator.EQUALS,
                            value=role,
                        ),
                        PolicyCondition(
                            field="request.action",
                            operator=ConditionOperator.IN,
                            value=allowed_actions,
                        ),
                    ],
                ),
            ],
        )

    @staticmethod
    def create_admin_policy() -> SecurityPolicy:
        """Create admin full-access policy."""
        return SecurityPolicy(
            policy_id="admin-full-access",
            name="Admin Full Access",
            description="Full access for administrators",
            priority=PolicyPriority.HIGH,
            rules=[
                PolicyRule(
                    rule_id="admin-allow-all",
                    name="Allow All for Admin",
                    effect=PolicyEffect.ALLOW,
                    conditions=[
                        PolicyCondition(
                            field="user.role",
                            operator=ConditionOperator.EQUALS,
                            value="admin",
                        ),
                    ],
                ),
            ],
        )


class TimeBasedPolicies:
    """Pre-built time-based policies."""

    @staticmethod
    def create_business_hours_policy(
        policy_id: str,
        name: str,
        start_time: str = "09:00",
        end_time: str = "17:00",
        priority: PolicyPriority = PolicyPriority.MEDIUM,
    ) -> SecurityPolicy:
        """Create business hours access policy."""
        return SecurityPolicy(
            policy_id=policy_id,
            name=name,
            description=f"Restrict access to {start_time}-{end_time}",
            priority=priority,
            rules=[
                PolicyRule(
                    rule_id=f"{policy_id}-business-hours",
                    name="Allow During Business Hours",
                    effect=PolicyEffect.ALLOW,
                    conditions=[
                        PolicyCondition(
                            field="request.time",
                            operator=ConditionOperator.TIME_BETWEEN,
                            value=[start_time, end_time],
                        ),
                    ],
                ),
                PolicyRule(
                    rule_id=f"{policy_id}-deny-outside",
                    name="Deny Outside Business Hours",
                    effect=PolicyEffect.DENY,
                ),
            ],
        )

    @staticmethod
    def create_maintenance_window_policy(
        policy_id: str,
        name: str,
        start_time: str,
        end_time: str,
        priority: PolicyPriority = PolicyPriority.EMERGENCY,
    ) -> SecurityPolicy:
        """Create maintenance window policy that blocks non-admin access."""
        return SecurityPolicy(
            policy_id=policy_id,
            name=name,
            description="Block non-admin access during maintenance",
            priority=priority,
            rules=[
                PolicyRule(
                    rule_id=f"{policy_id}-allow-admin",
                    name="Allow Admin During Maintenance",
                    effect=PolicyEffect.ALLOW,
                    conditions=[
                        PolicyCondition(
                            field="user.role",
                            operator=ConditionOperator.EQUALS,
                            value="admin",
                        ),
                        PolicyCondition(
                            field="request.time",
                            operator=ConditionOperator.TIME_BETWEEN,
                            value=[start_time, end_time],
                        ),
                    ],
                ),
                PolicyRule(
                    rule_id=f"{policy_id}-deny-all",
                    name="Deny All During Maintenance",
                    effect=PolicyEffect.DENY,
                    conditions=[
                        PolicyCondition(
                            field="request.time",
                            operator=ConditionOperator.TIME_BETWEEN,
                            value=[start_time, end_time],
                        ),
                    ],
                ),
            ],
        )


class RiskBasedPolicies:
    """Pre-built risk-based policies."""

    @staticmethod
    def create_mfa_required_policy(
        policy_id: str,
        name: str,
        for_roles: Optional[List[str]] = None,
        for_actions: Optional[List[str]] = None,
        priority: PolicyPriority = PolicyPriority.HIGH,
    ) -> SecurityPolicy:
        """Create MFA requirement policy."""
        conditions = [
            PolicyCondition(
                field="session.mfa_verified",
                operator=ConditionOperator.EQUALS,
                value=False,
            ),
        ]

        if for_roles:
            conditions.append(PolicyCondition(
                field="user.role",
                operator=ConditionOperator.IN,
                value=for_roles,
            ))

        if for_actions:
            conditions.append(PolicyCondition(
                field="request.action",
                operator=ConditionOperator.IN,
                value=for_actions,
            ))

        return SecurityPolicy(
            policy_id=policy_id,
            name=name,
            description="Require MFA for sensitive operations",
            priority=priority,
            rules=[
                PolicyRule(
                    rule_id=f"{policy_id}-require-mfa",
                    name="Require MFA",
                    effect=PolicyEffect.DENY,
                    conditions=conditions,
                    description="MFA verification required",
                ),
            ],
        )

    @staticmethod
    def create_high_risk_ip_policy(
        policy_id: str,
        name: str,
        high_risk_countries: List[str],
        priority: PolicyPriority = PolicyPriority.HIGH,
    ) -> SecurityPolicy:
        """Create policy requiring extra verification for high-risk locations."""
        return SecurityPolicy(
            policy_id=policy_id,
            name=name,
            description="Require MFA for high-risk locations",
            priority=priority,
            rules=[
                PolicyRule(
                    rule_id=f"{policy_id}-require-mfa",
                    name="Require MFA for High-Risk Location",
                    effect=PolicyEffect.DENY,
                    conditions=[
                        PolicyCondition(
                            field="request.geo.country_code",
                            operator=ConditionOperator.IN,
                            value=high_risk_countries,
                        ),
                        PolicyCondition(
                            field="session.mfa_verified",
                            operator=ConditionOperator.EQUALS,
                            value=False,
                        ),
                    ],
                    description="Additional verification required for high-risk location",
                ),
            ],
        )


def create_policy_engine(
    store: Optional[PolicyStore] = None,
    default_effect: PolicyEffect = PolicyEffect.DENY,
) -> PolicyEngine:
    """Create a policy engine instance."""
    return PolicyEngine(store=store, default_effect=default_effect)
