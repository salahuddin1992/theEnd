"""
GraphQL Context - سياق GraphQL
===============================

Context management for GraphQL requests.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from distributed_cluster.graphql.dataloaders import DataLoaders

logger = logging.getLogger(__name__)


class AuthorizationError(Exception):
    """خطأ التصريح"""
    pass


@dataclass
class User:
    """معلومات المستخدم"""
    id: str
    username: str
    email: Optional[str] = None
    roles: list = field(default_factory=list)
    tenant_id: Optional[str] = None
    is_admin: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceRegistry:
    """سجل الخدمات"""
    job_service: Any = None
    worker_service: Any = None
    tenant_service: Any = None
    backup_service: Any = None
    cluster_service: Any = None
    event_service: Any = None
    analytics_service: Any = None


class GraphQLContext:
    """
    سياق طلب GraphQL
    GraphQL Request Context

    يحتوي على معلومات المستخدم والخدمات المتاحة.
    Contains user info and available services.
    """

    def __init__(
        self,
        request: Any = None,
        user: Optional[User] = None,
        services: Optional[ServiceRegistry] = None,
        dataloaders: Optional["DataLoaders"] = None,
    ):
        self.request = request
        self.user = user
        self.services = services or ServiceRegistry()
        self.dataloaders = dataloaders
        self._start_time = datetime.utcnow()
        self._query_count = 0
        self._mutation_count = 0

    @property
    def user_id(self) -> Optional[str]:
        """معرف المستخدم"""
        return self.user.id if self.user else None

    @property
    def tenant_id(self) -> Optional[str]:
        """معرف المستأجر"""
        return self.user.tenant_id if self.user else None

    @property
    def is_authenticated(self) -> bool:
        """هل المستخدم مصادق؟"""
        return self.user is not None

    @property
    def is_admin(self) -> bool:
        """هل المستخدم مسؤول؟"""
        return self.user.is_admin if self.user else False

    def require_auth(self) -> None:
        """التحقق من المصادقة"""
        if not self.is_authenticated:
            raise AuthorizationError("Authentication required")

    def require_admin(self) -> None:
        """التحقق من صلاحيات المسؤول"""
        self.require_auth()
        if not self.is_admin:
            raise AuthorizationError("Admin privileges required")

    def require_role(self, role: str) -> None:
        """التحقق من دور معين"""
        self.require_auth()
        if role not in (self.user.roles or []):
            raise AuthorizationError(f"Role '{role}' required")

    def require_tenant_access(self, tenant_id: str) -> None:
        """التحقق من الوصول للمستأجر"""
        self.require_auth()
        if self.is_admin:
            return
        if self.tenant_id != tenant_id:
            raise AuthorizationError("Access denied to this tenant")

    def has_permission(self, permission: str) -> bool:
        """التحقق من صلاحية معينة"""
        if not self.is_authenticated:
            return False
        if self.is_admin:
            return True
        # Check role-based permissions
        role_permissions = {
            "admin": ["*"],
            "operator": ["jobs:read", "jobs:write", "workers:read", "metrics:read"],
            "developer": ["jobs:read", "jobs:write", "metrics:read"],
            "viewer": ["jobs:read", "workers:read", "metrics:read"],
        }
        for role in self.user.roles:
            perms = role_permissions.get(role, [])
            if "*" in perms or permission in perms:
                return True
        return False

    def increment_query_count(self) -> None:
        """زيادة عداد الاستعلامات"""
        self._query_count += 1

    def increment_mutation_count(self) -> None:
        """زيادة عداد الطفرات"""
        self._mutation_count += 1

    @property
    def execution_time_ms(self) -> float:
        """وقت التنفيذ بالملي ثانية"""
        return (datetime.utcnow() - self._start_time).total_seconds() * 1000

    def get_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات السياق"""
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "is_admin": self.is_admin,
            "query_count": self._query_count,
            "mutation_count": self._mutation_count,
            "execution_time_ms": self.execution_time_ms,
        }


class ContextFactory:
    """
    مصنع السياق
    Context Factory

    ينشئ سياق GraphQL لكل طلب.
    Creates GraphQL context for each request.
    """

    def __init__(
        self,
        services: Optional[ServiceRegistry] = None,
        auth_enabled: bool = True,
    ):
        self.services = services or ServiceRegistry()
        self.auth_enabled = auth_enabled

    async def create_context(
        self,
        request: Any,
        ws: Any = None,
    ) -> GraphQLContext:
        """
        إنشاء سياق جديد
        Create new context
        """
        from distributed_cluster.graphql.dataloaders import DataLoaders

        # Extract user from request
        user = await self._extract_user(request)

        # Create dataloaders
        dataloaders = DataLoaders(services=self.services)

        return GraphQLContext(
            request=request,
            user=user,
            services=self.services,
            dataloaders=dataloaders,
        )

    async def _extract_user(self, request: Any) -> Optional[User]:
        """
        استخراج المستخدم من الطلب
        Extract user from request
        """
        if not self.auth_enabled:
            # Return a default admin user if auth is disabled
            return User(
                id="system",
                username="system",
                roles=["admin"],
                is_admin=True,
            )

        # Try to extract token from headers
        auth_header = None
        if hasattr(request, "headers"):
            auth_header = request.headers.get("Authorization")

        if not auth_header:
            return None

        # Parse Bearer token
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]

        # Verify token and extract user info
        try:
            user_data = await self._verify_token(token)
            return User(
                id=user_data.get("user_id", "unknown"),
                username=user_data.get("username", "unknown"),
                email=user_data.get("email"),
                roles=user_data.get("roles", []),
                tenant_id=user_data.get("tenant_id"),
                is_admin=user_data.get("is_admin", False),
            )
        except Exception as e:
            logger.warning(f"Token verification failed: {e}")
            return None

    async def _verify_token(self, token: str) -> Dict[str, Any]:
        """
        التحقق من التوكن
        Verify token
        """
        # This should integrate with your actual auth system
        # For now, return mock data
        try:
            import jwt
            # Decode without verification for demo
            # In production, verify with proper secret
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload
        except Exception:
            raise ValueError("Invalid token")
