"""
Role-Based Access Control (RBAC) implementation.
"""

import fnmatch
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class AccessDecision(Enum):
    """Access decision results."""

    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


class Effect(Enum):
    """Policy effect."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass
class Permission:
    """Represents a permission."""

    name: str
    resource: str
    actions: Set[str]
    conditions: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def matches(self, resource: str, action: str) -> bool:
        """Check if permission matches resource and action."""
        # Check action
        if "*" not in self.actions and action not in self.actions:
            return False

        # Check resource (supports wildcards)
        if self.resource == "*":
            return True

        return fnmatch.fnmatch(resource, self.resource)


@dataclass
class Role:
    """Represents a role with permissions."""

    name: str
    permissions: List[Permission] = field(default_factory=list)
    parent_roles: List[str] = field(default_factory=list)
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_permission(self, permission: Permission):
        """Add a permission to the role."""
        self.permissions.append(permission)

    def remove_permission(self, permission_name: str):
        """Remove a permission from the role."""
        self.permissions = [p for p in self.permissions if p.name != permission_name]

    def has_permission(self, resource: str, action: str) -> bool:
        """Check if role has permission for resource and action."""
        return any(p.matches(resource, action) for p in self.permissions)


@dataclass
class Resource:
    """Represents a protected resource."""

    type: str
    id: str
    owner: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def path(self) -> str:
        return f"{self.type}/{self.id}"


@dataclass
class User:
    """Represents a user with roles."""

    id: str
    username: str
    roles: Set[str] = field(default_factory=set)
    attributes: Dict[str, Any] = field(default_factory=dict)
    groups: Set[str] = field(default_factory=set)
    tenant_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    is_active: bool = True

    def add_role(self, role_name: str):
        """Add a role to the user."""
        self.roles.add(role_name)

    def remove_role(self, role_name: str):
        """Remove a role from the user."""
        self.roles.discard(role_name)

    def has_role(self, role_name: str) -> bool:
        """Check if user has a role."""
        return role_name in self.roles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "roles": list(self.roles),
            "groups": list(self.groups),
            "tenant_id": self.tenant_id,
            "is_active": self.is_active,
        }


@dataclass
class Policy:
    """Access control policy."""

    name: str
    effect: Effect
    principals: List[str]  # user/role/group patterns
    resources: List[str]  # resource patterns
    actions: List[str]
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0

    def matches_principal(self, user: User) -> bool:
        """Check if policy matches user."""
        for principal in self.principals:
            if principal == "*":
                return True
            if principal.startswith("user:"):
                if user.id == principal[5:] or user.username == principal[5:]:
                    return True
            elif principal.startswith("role:"):
                if principal[5:] in user.roles:
                    return True
            elif principal.startswith("group:"):
                if principal[6:] in user.groups:
                    return True
        return False

    def matches_resource(self, resource: str) -> bool:
        """Check if policy matches resource."""
        for pattern in self.resources:
            if pattern == "*" or fnmatch.fnmatch(resource, pattern):
                return True
        return False

    def matches_action(self, action: str) -> bool:
        """Check if policy matches action."""
        return "*" in self.actions or action in self.actions

    def evaluate_conditions(self, context: Dict[str, Any]) -> bool:
        """Evaluate policy conditions."""
        if not self.conditions:
            return True

        for condition_type, condition_value in self.conditions.items():
            if condition_type == "ip_range":
                # Check if request IP is in allowed range
                request_ip = context.get("ip")
                if request_ip and not self._ip_in_range(request_ip, condition_value):
                    return False

            elif condition_type == "time_range":
                # Check if current time is within range
                now = datetime.now(timezone.utc).time()
                start = datetime.strptime(condition_value["start"], "%H:%M").time()
                end = datetime.strptime(condition_value["end"], "%H:%M").time()
                if not (start <= now <= end):
                    return False

            elif condition_type == "tenant_id":
                # Check tenant ID
                if context.get("tenant_id") != condition_value:
                    return False

            elif condition_type == "custom":
                # Custom condition function
                if callable(condition_value):
                    if not condition_value(context):
                        return False

        return True

    def _ip_in_range(self, ip: str, ranges: List[str]) -> bool:
        """Check if IP is in any of the ranges."""
        try:
            import ipaddress

            ip_addr = ipaddress.ip_address(ip)
            for range_str in ranges:
                if "/" in range_str:
                    network = ipaddress.ip_network(range_str, strict=False)
                    if ip_addr in network:
                        return True
                elif ip == range_str:
                    return True
        except Exception:
            pass
        return False


class PolicyEngine:
    """Evaluates access control policies."""

    def __init__(self):
        self._policies: List[Policy] = []
        self._lock = threading.RLock()
        self._default_effect = Effect.DENY

    def add_policy(self, policy: Policy):
        """Add a policy."""
        with self._lock:
            self._policies.append(policy)
            # Sort by priority (higher first)
            self._policies.sort(key=lambda p: p.priority, reverse=True)

    def remove_policy(self, policy_name: str):
        """Remove a policy by name."""
        with self._lock:
            self._policies = [p for p in self._policies if p.name != policy_name]

    def evaluate(
        self, user: User, resource: str, action: str, context: Optional[Dict[str, Any]] = None
    ) -> AccessDecision:
        """Evaluate access for a user on a resource."""
        context = context or {}

        with self._lock:
            for policy in self._policies:
                if not policy.matches_principal(user):
                    continue
                if not policy.matches_resource(resource):
                    continue
                if not policy.matches_action(action):
                    continue
                if not policy.evaluate_conditions(context):
                    continue

                # Policy matches
                if policy.effect == Effect.DENY:
                    logger.debug(f"Access denied by policy {policy.name}")
                    return AccessDecision.DENY
                else:
                    logger.debug(f"Access allowed by policy {policy.name}")
                    return AccessDecision.ALLOW

        # No matching policy
        if self._default_effect == Effect.DENY:
            return AccessDecision.DENY
        return AccessDecision.ALLOW

    def list_policies(self) -> List[Policy]:
        """List all policies."""
        with self._lock:
            return list(self._policies)


class RBACManager:
    """Main RBAC management class."""

    def __init__(self):
        self._roles: Dict[str, Role] = {}
        self._users: Dict[str, User] = {}
        self._groups: Dict[str, Set[str]] = {}  # group -> set of user_ids
        self._policy_engine = PolicyEngine()
        self._lock = threading.RLock()

        self._init_default_roles()

    def _init_default_roles(self):
        """Initialize default roles."""
        # Admin role with all permissions
        admin_role = Role(
            name="admin",
            description="Administrator with full access",
            permissions=[Permission(name="admin_all", resource="*", actions={"*"})],
        )
        self.add_role(admin_role)

        # Operator role
        operator_role = Role(
            name="operator",
            description="Operator with operational access",
            permissions=[
                Permission(name="jobs_manage", resource="jobs/*", actions={"read", "create", "update", "cancel"}),
                Permission(name="clusters_manage", resource="clusters/*", actions={"read", "scale"}),
                Permission(name="workers_view", resource="workers/*", actions={"read"}),
            ],
        )
        self.add_role(operator_role)

        # Viewer role
        viewer_role = Role(
            name="viewer",
            description="Read-only access",
            permissions=[Permission(name="read_all", resource="*", actions={"read", "list"})],
        )
        self.add_role(viewer_role)

    def add_role(self, role: Role):
        """Add a role."""
        with self._lock:
            self._roles[role.name] = role
            logger.info(f"Added role: {role.name}")

    def get_role(self, role_name: str) -> Optional[Role]:
        """Get a role by name."""
        with self._lock:
            return self._roles.get(role_name)

    def remove_role(self, role_name: str):
        """Remove a role."""
        with self._lock:
            if role_name in self._roles:
                del self._roles[role_name]
                # Remove role from all users
                for user in self._users.values():
                    user.roles.discard(role_name)

    def list_roles(self) -> List[Role]:
        """List all roles."""
        with self._lock:
            return list(self._roles.values())

    def add_user(self, user: User):
        """Add a user."""
        with self._lock:
            self._users[user.id] = user
            logger.info(f"Added user: {user.username}")

    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        with self._lock:
            return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username."""
        with self._lock:
            for user in self._users.values():
                if user.username == username:
                    return user
            return None

    def remove_user(self, user_id: str):
        """Remove a user."""
        with self._lock:
            if user_id in self._users:
                del self._users[user_id]

    def list_users(self) -> List[User]:
        """List all users."""
        with self._lock:
            return list(self._users.values())

    def assign_role(self, user_id: str, role_name: str) -> bool:
        """Assign a role to a user."""
        with self._lock:
            user = self._users.get(user_id)
            role = self._roles.get(role_name)

            if not user or not role:
                return False

            user.add_role(role_name)
            logger.info(f"Assigned role {role_name} to user {user.username}")
            return True

    def revoke_role(self, user_id: str, role_name: str) -> bool:
        """Revoke a role from a user."""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False

            user.remove_role(role_name)
            logger.info(f"Revoked role {role_name} from user {user.username}")
            return True

    def create_group(self, group_name: str):
        """Create a group."""
        with self._lock:
            if group_name not in self._groups:
                self._groups[group_name] = set()

    def add_user_to_group(self, user_id: str, group_name: str):
        """Add a user to a group."""
        with self._lock:
            if group_name not in self._groups:
                self._groups[group_name] = set()
            self._groups[group_name].add(user_id)

            user = self._users.get(user_id)
            if user:
                user.groups.add(group_name)

    def remove_user_from_group(self, user_id: str, group_name: str):
        """Remove a user from a group."""
        with self._lock:
            if group_name in self._groups:
                self._groups[group_name].discard(user_id)

            user = self._users.get(user_id)
            if user:
                user.groups.discard(group_name)

    def get_effective_permissions(self, user: User) -> List[Permission]:
        """Get all effective permissions for a user."""
        permissions = []

        with self._lock:
            # Collect permissions from all roles (including inherited)
            visited = set()
            roles_to_process = list(user.roles)

            while roles_to_process:
                role_name = roles_to_process.pop(0)
                if role_name in visited:
                    continue
                visited.add(role_name)

                role = self._roles.get(role_name)
                if role:
                    permissions.extend(role.permissions)
                    roles_to_process.extend(role.parent_roles)

        return permissions

    def check_permission(
        self, user: User, resource: str, action: str, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if user has permission for resource and action."""
        if not user.is_active:
            return False

        # Check direct permissions from roles
        permissions = self.get_effective_permissions(user)
        for permission in permissions:
            if permission.matches(resource, action):
                # Check conditions
                if permission.conditions:
                    if not self._evaluate_conditions(permission.conditions, context or {}):
                        continue
                return True

        # Check policy engine
        decision = self._policy_engine.evaluate(user, resource, action, context)
        return decision == AccessDecision.ALLOW

    def _evaluate_conditions(self, conditions: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate permission conditions."""
        for key, value in conditions.items():
            if key == "owner_only":
                if value and context.get("owner") != context.get("user_id"):
                    return False
            elif key == "tenant_match":
                if value and context.get("resource_tenant") != context.get("user_tenant"):
                    return False
        return True

    def add_policy(self, policy: Policy):
        """Add an access control policy."""
        self._policy_engine.add_policy(policy)

    def remove_policy(self, policy_name: str):
        """Remove an access control policy."""
        self._policy_engine.remove_policy(policy_name)

    def list_policies(self) -> List[Policy]:
        """List all policies."""
        return self._policy_engine.list_policies()


def require_permission(resource: str, action: str):
    """Decorator for requiring permission on a resource."""

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # Get user from context (implementation depends on framework)
            user = kwargs.get("current_user") or getattr(args[0], "current_user", None)
            if not user:
                raise PermissionError("Authentication required")

            # Get RBAC manager
            rbac = kwargs.get("rbac_manager") or getattr(args[0], "rbac_manager", None)
            if not rbac:
                raise RuntimeError("RBAC manager not configured")

            # Check permission
            if not rbac.check_permission(user, resource, action):
                raise PermissionError(f"Permission denied: {action} on {resource}")

            return func(*args, **kwargs)

        return wrapper

    return decorator
