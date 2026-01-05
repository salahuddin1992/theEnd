"""
Gateway Routing - توجيه البوابة
================================

Advanced routing with path matching, load balancing, and service discovery.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Pattern, Tuple

logger = logging.getLogger(__name__)


class LoadBalancerType(str, Enum):
    """Load balancing algorithms."""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED = "weighted"
    IP_HASH = "ip_hash"
    CONSISTENT_HASH = "consistent_hash"


class BackendStatus(str, Enum):
    """Backend health status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"
    UNKNOWN = "unknown"


@dataclass
class ServiceBackend:
    """Represents an upstream service backend."""
    backend_id: str
    host: str
    port: int
    weight: int = 1

    # Health
    status: BackendStatus = BackendStatus.UNKNOWN
    last_health_check: Optional[datetime] = None
    consecutive_failures: int = 0

    # Metrics
    active_connections: int = 0
    total_requests: int = 0
    total_failures: int = 0
    total_latency_ms: float = 0.0

    # Metadata
    tags: Dict[str, str] = field(default_factory=dict)
    zone: str = ""

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    def mark_healthy(self) -> None:
        self.status = BackendStatus.HEALTHY
        self.consecutive_failures = 0
        self.last_health_check = datetime.now(timezone.utc)

    def mark_unhealthy(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.status = BackendStatus.UNHEALTHY
        self.last_health_check = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "host": self.host,
            "port": self.port,
            "weight": self.weight,
            "status": self.status.value,
            "active_connections": self.active_connections,
            "total_requests": self.total_requests,
            "avg_latency_ms": self.avg_latency_ms,
        }


class BackendPool:
    """
    Pool of backends with load balancing.

    Supports multiple load balancing strategies.
    """

    def __init__(
        self,
        name: str,
        backends: Optional[List[ServiceBackend]] = None,
        lb_type: LoadBalancerType = LoadBalancerType.ROUND_ROBIN,
    ):
        self.name = name
        self._backends: List[ServiceBackend] = backends or []
        self.lb_type = lb_type
        self._current_index = 0
        self._lock = asyncio.Lock()

    def add_backend(self, backend: ServiceBackend) -> None:
        """Add a backend to the pool."""
        self._backends.append(backend)
        logger.info(f"Added backend {backend.backend_id} to pool {self.name}")

    def remove_backend(self, backend_id: str) -> None:
        """Remove a backend from the pool."""
        self._backends = [b for b in self._backends if b.backend_id != backend_id]

    def get_healthy_backends(self) -> List[ServiceBackend]:
        """Get all healthy backends."""
        return [b for b in self._backends if b.status == BackendStatus.HEALTHY]

    async def get_backend(self, key: Optional[str] = None) -> Optional[ServiceBackend]:
        """Get next backend based on load balancing strategy."""
        healthy = self.get_healthy_backends()
        if not healthy:
            # Fallback to all backends if none healthy
            healthy = self._backends

        if not healthy:
            return None

        async with self._lock:
            if self.lb_type == LoadBalancerType.ROUND_ROBIN:
                backend = healthy[self._current_index % len(healthy)]
                self._current_index += 1

            elif self.lb_type == LoadBalancerType.RANDOM:
                backend = random.choice(healthy)

            elif self.lb_type == LoadBalancerType.LEAST_CONNECTIONS:
                backend = min(healthy, key=lambda b: b.active_connections)

            elif self.lb_type == LoadBalancerType.WEIGHTED:
                total_weight = sum(b.weight for b in healthy)
                r = random.randint(1, total_weight)
                current = 0
                backend = healthy[0]
                for b in healthy:
                    current += b.weight
                    if r <= current:
                        backend = b
                        break

            elif self.lb_type == LoadBalancerType.IP_HASH:
                if key:
                    hash_val = int(hashlib.md5(key.encode()).hexdigest(), 16)
                    backend = healthy[hash_val % len(healthy)]
                else:
                    backend = healthy[0]

            elif self.lb_type == LoadBalancerType.CONSISTENT_HASH:
                if key:
                    backend = self._consistent_hash_select(healthy, key)
                else:
                    backend = healthy[0]

            else:
                backend = healthy[0]

            backend.active_connections += 1
            return backend

    def _consistent_hash_select(
        self,
        backends: List[ServiceBackend],
        key: str,
    ) -> ServiceBackend:
        """Select backend using consistent hashing."""
        key_hash = int(hashlib.md5(key.encode()).hexdigest(), 16)

        # Create virtual nodes
        ring: List[Tuple[int, ServiceBackend]] = []
        for backend in backends:
            for i in range(100):  # 100 virtual nodes per backend
                node_hash = int(hashlib.md5(
                    f"{backend.backend_id}:{i}".encode()
                ).hexdigest(), 16)
                ring.append((node_hash, backend))

        ring.sort(key=lambda x: x[0])

        # Find first node >= key_hash
        for node_hash, backend in ring:
            if node_hash >= key_hash:
                return backend

        return ring[0][1]

    def release_backend(self, backend: ServiceBackend) -> None:
        """Release a backend connection."""
        backend.active_connections = max(0, backend.active_connections - 1)

    async def health_check(self) -> Dict[str, Any]:
        """Run health check on all backends."""
        results = {}
        for backend in self._backends:
            try:
                # Simple TCP check
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((backend.host, backend.port))
                sock.close()

                if result == 0:
                    backend.mark_healthy()
                    results[backend.backend_id] = "healthy"
                else:
                    backend.mark_unhealthy()
                    results[backend.backend_id] = "unhealthy"

            except Exception as e:
                backend.mark_unhealthy()
                results[backend.backend_id] = f"error: {e}"

        return results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "lb_type": self.lb_type.value,
            "backends": [b.to_dict() for b in self._backends],
            "healthy_count": len(self.get_healthy_backends()),
        }


@dataclass
class RouteMatch:
    """Result of route matching."""
    matched: bool
    route: Optional[Route] = None
    params: Dict[str, str] = field(default_factory=dict)
    score: int = 0  # Higher score = better match


@dataclass
class RoutingRule:
    """Conditional routing rule."""
    name: str
    conditions: List[Dict[str, Any]]
    backend_pool: str
    priority: int = 0

    def matches(self, request: Any) -> bool:
        """Check if request matches all conditions."""
        for condition in self.conditions:
            if not self._check_condition(condition, request):
                return False
        return True

    def _check_condition(self, condition: Dict[str, Any], request: Any) -> bool:
        """Check a single condition."""
        cond_type = condition.get("type")

        if cond_type == "header":
            header_name = condition.get("name", "").lower()
            expected = condition.get("value")
            actual = request.headers.get(header_name, "")
            op = condition.get("operator", "eq")

            if op == "eq":
                return actual == expected
            elif op == "contains":
                return expected in actual
            elif op == "regex":
                return bool(re.match(expected, actual))

        elif cond_type == "path":
            pattern = condition.get("pattern")
            return bool(re.match(pattern, request.path))

        elif cond_type == "method":
            methods = condition.get("methods", [])
            return request.method in methods

        elif cond_type == "query":
            param_name = condition.get("name")
            expected = condition.get("value")
            # Parse query string
            query_params = dict(
                p.split("=") for p in request.query_string.split("&")
                if "=" in p
            ) if request.query_string else {}
            return query_params.get(param_name) == expected

        return True


class PathMatcher:
    """Advanced path matching with patterns."""

    def __init__(self):
        self._patterns: Dict[str, Pattern] = {}

    def compile_pattern(self, pattern: str) -> Pattern:
        """Compile path pattern to regex."""
        if pattern in self._patterns:
            return self._patterns[pattern]

        # Convert path pattern to regex
        regex = pattern

        # Handle path parameters: /users/:id -> /users/(?P<id>[^/]+)
        regex = re.sub(r":(\w+)", r"(?P<\1>[^/]+)", regex)

        # Handle wildcards: /api/* -> /api/.*
        regex = regex.replace("*", ".*")

        # Anchor pattern
        if not regex.endswith("$"):
            regex += "$"
        if not regex.startswith("^"):
            regex = "^" + regex

        compiled = re.compile(regex)
        self._patterns[pattern] = compiled
        return compiled

    def match(self, pattern: str, path: str) -> Optional[Dict[str, str]]:
        """Match path against pattern, return captured params."""
        compiled = self.compile_pattern(pattern)
        match = compiled.match(path)

        if match:
            return match.groupdict()
        return None


@dataclass
class Route:
    """Represents a gateway route."""
    route_id: str
    path: str
    methods: List[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "PATCH"])
    backend_pool: Optional[str] = None
    upstream_url: Optional[str] = None

    # Matching
    priority: int = 0
    exact_match: bool = False
    regex_pattern: Optional[str] = None

    # Routing rules
    rules: List[RoutingRule] = field(default_factory=list)

    # Transforms
    strip_prefix: Optional[str] = None
    add_prefix: Optional[str] = None
    rewrite_path: Optional[str] = None

    # Timeouts
    timeout_seconds: float = 30.0

    # Retry
    retry_count: int = 0
    retry_delay_ms: int = 100

    # Rate limiting
    rate_limit: Optional[int] = None  # Requests per second

    # Circuit breaker
    circuit_breaker_enabled: bool = False

    # Authentication
    auth_required: bool = False
    auth_roles: List[str] = field(default_factory=list)

    # Metadata
    description: str = ""
    tags: List[str] = field(default_factory=list)
    enabled: bool = True

    def transform_path(self, original_path: str) -> str:
        """Apply path transformations."""
        path = original_path

        if self.strip_prefix and path.startswith(self.strip_prefix):
            path = path[len(self.strip_prefix):]

        if self.add_prefix:
            path = self.add_prefix + path

        if self.rewrite_path:
            # Simple rewrite - could be extended with regex
            path = self.rewrite_path

        return path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_id": self.route_id,
            "path": self.path,
            "methods": self.methods,
            "backend_pool": self.backend_pool,
            "upstream_url": self.upstream_url,
            "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
            "auth_required": self.auth_required,
            "enabled": self.enabled,
        }


class Router:
    """
    Advanced Router - الموجه المتقدم.

    Handles route matching, path parameters, and routing rules.

    Example:
        router = Router()

        # Add routes
        router.add_route(Route(
            route_id="users",
            path="/api/users/:id",
            backend_pool="users-service",
        ))

        # Match request
        match = router.match(request)
        if match.matched:
            pool = match.route.backend_pool
    """

    def __init__(self):
        self._routes: Dict[str, Route] = {}
        self._backend_pools: Dict[str, BackendPool] = {}
        self._path_matcher = PathMatcher()
        self._routing_rules: List[RoutingRule] = []

    def add_route(self, route: Route) -> None:
        """Add a route."""
        self._routes[route.route_id] = route
        logger.info(f"Added route: {route.route_id} -> {route.path}")

    def remove_route(self, route_id: str) -> None:
        """Remove a route."""
        if route_id in self._routes:
            del self._routes[route_id]

    def get_route(self, route_id: str) -> Optional[Route]:
        """Get route by ID."""
        return self._routes.get(route_id)

    def add_backend_pool(self, pool: BackendPool) -> None:
        """Add a backend pool."""
        self._backend_pools[pool.name] = pool

    def get_backend_pool(self, name: str) -> Optional[BackendPool]:
        """Get backend pool by name."""
        return self._backend_pools.get(name)

    def add_routing_rule(self, rule: RoutingRule) -> None:
        """Add a routing rule."""
        self._routing_rules.append(rule)
        self._routing_rules.sort(key=lambda r: r.priority, reverse=True)

    def match(self, request: Any) -> RouteMatch:
        """Match request to a route."""
        best_match: Optional[RouteMatch] = None

        # Sort routes by priority
        routes = sorted(
            [r for r in self._routes.values() if r.enabled],
            key=lambda r: r.priority,
            reverse=True
        )

        for route in routes:
            # Check method
            if request.method not in route.methods:
                continue

            # Check path
            if route.exact_match:
                if request.path == route.path:
                    params = {}
                    score = 100
                else:
                    continue
            elif route.regex_pattern:
                match = re.match(route.regex_pattern, request.path)
                if match:
                    params = match.groupdict()
                    score = 80
                else:
                    continue
            else:
                params = self._path_matcher.match(route.path, request.path)
                if params is None:
                    continue
                score = 50 + len(route.path)

            # Check routing rules
            for rule in route.rules:
                if rule.matches(request):
                    # Rule matched - use rule's backend
                    return RouteMatch(
                        matched=True,
                        route=route,
                        params=params,
                        score=score + 1000,  # Rules have higher priority
                    )

            current_match = RouteMatch(
                matched=True,
                route=route,
                params=params,
                score=score,
            )

            if best_match is None or current_match.score > best_match.score:
                best_match = current_match

        if best_match:
            return best_match

        return RouteMatch(matched=False)

    async def get_backend(
        self,
        route: Route,
        request: Any,
    ) -> Optional[ServiceBackend]:
        """Get backend for a route."""
        if route.backend_pool:
            pool = self._backend_pools.get(route.backend_pool)
            if pool:
                return await pool.get_backend(request.client_ip)
        return None

    def list_routes(self) -> List[Dict[str, Any]]:
        """List all routes."""
        return [r.to_dict() for r in self._routes.values()]

    def list_backend_pools(self) -> List[Dict[str, Any]]:
        """List all backend pools."""
        return [p.to_dict() for p in self._backend_pools.values()]
