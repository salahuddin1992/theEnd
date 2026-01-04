"""
Traffic routing and management for service mesh.
"""

import logging
import random
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MatchType(Enum):
    """Types of request matching."""
    EXACT = "exact"
    PREFIX = "prefix"
    REGEX = "regex"
    HEADER = "header"
    QUERY = "query"


class RouteAction(Enum):
    """Actions for matched routes."""
    FORWARD = "forward"
    REDIRECT = "redirect"
    ABORT = "abort"
    MIRROR = "mirror"
    RETRY = "retry"


@dataclass
class HeaderMatch:
    """Header matching configuration."""
    name: str
    value: Optional[str] = None
    regex: Optional[str] = None
    present: Optional[bool] = None
    invert: bool = False

    def matches(self, headers: Dict[str, str]) -> bool:
        header_value = headers.get(self.name)

        if self.present is not None:
            result = (header_value is not None) == self.present
        elif self.value is not None:
            result = header_value == self.value
        elif self.regex:
            result = header_value is not None and bool(re.match(self.regex, header_value))
        else:
            result = header_value is not None

        return not result if self.invert else result


@dataclass
class RouteMatch:
    """Route matching criteria."""
    path: Optional[str] = None
    path_type: MatchType = MatchType.PREFIX
    headers: List[HeaderMatch] = field(default_factory=list)
    query_params: Dict[str, str] = field(default_factory=dict)
    methods: List[str] = field(default_factory=list)
    source_labels: Dict[str, str] = field(default_factory=dict)

    def matches(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, str]] = None,
        method: Optional[str] = None
    ) -> bool:
        headers = headers or {}
        query_params = query_params or {}

        # Match path
        if self.path:
            if self.path_type == MatchType.EXACT:
                if path != self.path:
                    return False
            elif self.path_type == MatchType.PREFIX:
                if not path.startswith(self.path):
                    return False
            elif self.path_type == MatchType.REGEX:
                if not re.match(self.path, path):
                    return False

        # Match headers
        for header_match in self.headers:
            if not header_match.matches(headers):
                return False

        # Match query params
        for key, value in self.query_params.items():
            if query_params.get(key) != value:
                return False

        # Match methods
        if self.methods and method:
            if method.upper() not in [m.upper() for m in self.methods]:
                return False

        return True


@dataclass
class RouteDestination:
    """Destination for a route."""
    host: str
    port: int = 80
    weight: int = 100
    subset: Optional[str] = None
    headers_to_add: Dict[str, str] = field(default_factory=dict)
    headers_to_remove: List[str] = field(default_factory=list)


@dataclass
class RetryConfig:
    """Retry configuration for routes."""
    attempts: int = 3
    per_try_timeout: float = 2.0
    retry_on: List[str] = field(default_factory=lambda: ["5xx", "reset", "connect-failure"])
    retry_priority: Optional[str] = None


@dataclass
class TimeoutConfig:
    """Timeout configuration for routes."""
    request_timeout: float = 15.0
    idle_timeout: float = 60.0


@dataclass
class FaultConfig:
    """Fault injection configuration."""
    delay_percent: float = 0.0
    delay_seconds: float = 0.0
    abort_percent: float = 0.0
    abort_code: int = 503


@dataclass
class Route:
    """A route definition."""
    name: str
    match: RouteMatch
    destinations: List[RouteDestination] = field(default_factory=list)
    action: RouteAction = RouteAction.FORWARD
    retry: Optional[RetryConfig] = None
    timeout: Optional[TimeoutConfig] = None
    fault: Optional[FaultConfig] = None
    mirror: Optional[RouteDestination] = None
    priority: int = 0
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def select_destination(self) -> Optional[RouteDestination]:
        """Select a destination based on weights."""
        if not self.destinations:
            return None

        if len(self.destinations) == 1:
            return self.destinations[0]

        # Weighted random selection
        total_weight = sum(d.weight for d in self.destinations)
        rand = random.randint(1, total_weight)
        cumulative = 0

        for dest in self.destinations:
            cumulative += dest.weight
            if rand <= cumulative:
                return dest

        return self.destinations[-1]


@dataclass
class RouteRule:
    """A rule containing multiple routes."""
    name: str
    hosts: List[str] = field(default_factory=list)
    routes: List[Route] = field(default_factory=list)
    gateways: List[str] = field(default_factory=list)
    enabled: bool = True

    def match_route(
        self,
        host: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, str]] = None,
        method: Optional[str] = None
    ) -> Optional[Route]:
        """Find matching route for a request."""
        if not self.enabled:
            return None

        # Check host match
        if self.hosts and host not in self.hosts:
            # Check wildcard hosts
            matched = False
            for h in self.hosts:
                if h.startswith("*.") and host.endswith(h[1:]):
                    matched = True
                    break
            if not matched:
                return None

        # Find matching route (sorted by priority)
        sorted_routes = sorted(
            [r for r in self.routes if r.enabled],
            key=lambda r: r.priority,
            reverse=True
        )

        for route in sorted_routes:
            if route.match.matches(path, headers, query_params, method):
                return route

        return None


@dataclass
class TrafficPolicy:
    """Traffic policy for a service."""
    connection_pool_size: int = 100
    max_requests_per_connection: int = 1000
    h2_upgrade: bool = True
    load_balancer: str = "round_robin"
    outlier_detection: bool = True
    outlier_consecutive_errors: int = 5
    outlier_interval: float = 10.0
    outlier_base_ejection_time: float = 30.0
    outlier_max_ejection_percent: int = 50


class Router:
    """Traffic router for service mesh."""

    def __init__(self):
        self._rules: Dict[str, RouteRule] = {}
        self._policies: Dict[str, TrafficPolicy] = {}
        self._lock = threading.RLock()

    def add_rule(self, rule: RouteRule):
        """Add a routing rule."""
        with self._lock:
            self._rules[rule.name] = rule
            logger.info(f"Added route rule: {rule.name}")

    def remove_rule(self, name: str):
        """Remove a routing rule."""
        with self._lock:
            self._rules.pop(name, None)
            logger.info(f"Removed route rule: {name}")

    def get_rule(self, name: str) -> Optional[RouteRule]:
        """Get a routing rule by name."""
        with self._lock:
            return self._rules.get(name)

    def list_rules(self) -> List[str]:
        """List all rule names."""
        with self._lock:
            return list(self._rules.keys())

    def set_policy(self, service: str, policy: TrafficPolicy):
        """Set traffic policy for a service."""
        with self._lock:
            self._policies[service] = policy

    def get_policy(self, service: str) -> Optional[TrafficPolicy]:
        """Get traffic policy for a service."""
        with self._lock:
            return self._policies.get(service)

    def route(
        self,
        host: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, str]] = None,
        method: Optional[str] = None
    ) -> Tuple[Optional[Route], Optional[RouteDestination]]:
        """Route a request and return matching route and destination."""
        with self._lock:
            for rule in self._rules.values():
                route = rule.match_route(host, path, headers, query_params, method)
                if route:
                    destination = route.select_destination()
                    return route, destination

        return None, None


class WeightedRouting:
    """Weighted traffic splitting between versions."""

    def __init__(self, service: str):
        self.service = service
        self._weights: Dict[str, int] = {}  # version -> weight
        self._lock = threading.Lock()

    def set_weight(self, version: str, weight: int):
        """Set weight for a version."""
        with self._lock:
            self._weights[version] = weight

    def remove_version(self, version: str):
        """Remove a version from routing."""
        with self._lock:
            self._weights.pop(version, None)

    def select_version(self) -> Optional[str]:
        """Select a version based on weights."""
        with self._lock:
            if not self._weights:
                return None

            total = sum(self._weights.values())
            rand = random.randint(1, total)
            cumulative = 0

            for version, weight in self._weights.items():
                cumulative += weight
                if rand <= cumulative:
                    return version

            return list(self._weights.keys())[-1]

    def get_weights(self) -> Dict[str, int]:
        """Get current weights."""
        with self._lock:
            return dict(self._weights)


class HeaderBasedRouting:
    """Route based on request headers."""

    def __init__(self, service: str):
        self.service = service
        self._routes: List[Tuple[Dict[str, str], str]] = []  # (headers, version)
        self._default_version: Optional[str] = None
        self._lock = threading.Lock()

    def add_route(self, headers: Dict[str, str], version: str):
        """Add a header-based route."""
        with self._lock:
            self._routes.append((headers, version))

    def set_default(self, version: str):
        """Set default version for unmatched requests."""
        with self._lock:
            self._default_version = version

    def select_version(self, request_headers: Dict[str, str]) -> Optional[str]:
        """Select version based on request headers."""
        with self._lock:
            for route_headers, version in self._routes:
                match = all(
                    request_headers.get(k) == v
                    for k, v in route_headers.items()
                )
                if match:
                    return version

            return self._default_version


class CanaryRouting:
    """Canary deployment routing."""

    def __init__(
        self,
        service: str,
        canary_version: str,
        stable_version: str,
        canary_weight: int = 10
    ):
        self.service = service
        self.canary_version = canary_version
        self.stable_version = stable_version
        self._canary_weight = canary_weight
        self._canary_headers: Dict[str, str] = {}
        self._lock = threading.Lock()

    @property
    def canary_weight(self) -> int:
        with self._lock:
            return self._canary_weight

    @canary_weight.setter
    def canary_weight(self, value: int):
        with self._lock:
            self._canary_weight = max(0, min(100, value))

    def set_canary_header(self, name: str, value: str):
        """Set header that forces canary routing."""
        with self._lock:
            self._canary_headers[name] = value

    def select_version(self, headers: Optional[Dict[str, str]] = None) -> str:
        """Select version for a request."""
        headers = headers or {}

        with self._lock:
            # Check for canary header
            for name, value in self._canary_headers.items():
                if headers.get(name) == value:
                    return self.canary_version

            # Random selection based on weight
            if random.randint(1, 100) <= self._canary_weight:
                return self.canary_version

            return self.stable_version

    def promote_canary(self):
        """Promote canary to stable (set weight to 100)."""
        with self._lock:
            self._canary_weight = 100

    def rollback(self):
        """Rollback to stable (set weight to 0)."""
        with self._lock:
            self._canary_weight = 0

    def gradual_increase(self, step: int = 10):
        """Gradually increase canary weight."""
        with self._lock:
            self._canary_weight = min(100, self._canary_weight + step)


class ABTestRouting:
    """A/B testing routing."""

    def __init__(self, service: str, experiment_name: str):
        self.service = service
        self.experiment_name = experiment_name
        self._variants: Dict[str, int] = {}  # variant -> weight
        self._user_assignments: Dict[str, str] = {}  # user_id -> variant
        self._lock = threading.Lock()

    def add_variant(self, variant: str, weight: int):
        """Add a variant with weight."""
        with self._lock:
            self._variants[variant] = weight

    def select_variant(self, user_id: Optional[str] = None) -> Optional[str]:
        """Select variant for a user."""
        with self._lock:
            if not self._variants:
                return None

            # Check if user is already assigned
            if user_id and user_id in self._user_assignments:
                return self._user_assignments[user_id]

            # Random selection based on weights
            total = sum(self._variants.values())
            rand = random.randint(1, total)
            cumulative = 0

            for variant, weight in self._variants.items():
                cumulative += weight
                if rand <= cumulative:
                    if user_id:
                        self._user_assignments[user_id] = variant
                    return variant

            return list(self._variants.keys())[-1]

    def get_variant_stats(self) -> Dict[str, int]:
        """Get count of users per variant."""
        with self._lock:
            stats: Dict[str, int] = {v: 0 for v in self._variants}
            for variant in self._user_assignments.values():
                stats[variant] = stats.get(variant, 0) + 1
            return stats
