"""
Service Mesh Integration for NebulaCompute.

This module provides comprehensive service mesh capabilities including:
- Istio/Envoy sidecar support
- Traffic management and routing
- Circuit breaker patterns
- Service discovery and load balancing
"""

from .circuitbreaker import (
    Bulkhead,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
    RateLimiter,
)
from .discovery import (
    ConsulDiscovery,
    EtcdDiscovery,
    KubernetesDiscovery,
    ServiceDiscovery,
    ServiceInstance,
    ServiceRegistry,
)
from .loadbalancer import (
    ConsistentHashBalancer,
    HealthAwareBalancer,
    LeastConnectionsBalancer,
    LoadBalancer,
    RoundRobinBalancer,
    WeightedBalancer,
)
from .resilience import (
    FallbackPolicy,
    Resilience,
    ResiliencePolicy,
    RetryPolicy,
    TimeoutPolicy,
)
from .routing import (
    CanaryRouting,
    HeaderBasedRouting,
    Route,
    Router,
    RouteRule,
    TrafficPolicy,
    WeightedRouting,
)
from .sidecar import (
    EnvoyConfig,
    IstioConfig,
    ProxyConfig,
    SidecarProxy,
    TrafficInterceptor,
)

__all__ = [
    # Discovery
    "ServiceRegistry",
    "ServiceInstance",
    "ServiceDiscovery",
    "ConsulDiscovery",
    "KubernetesDiscovery",
    "EtcdDiscovery",
    # Routing
    "Router",
    "Route",
    "RouteRule",
    "TrafficPolicy",
    "WeightedRouting",
    "HeaderBasedRouting",
    "CanaryRouting",
    # Load Balancer
    "LoadBalancer",
    "RoundRobinBalancer",
    "LeastConnectionsBalancer",
    "WeightedBalancer",
    "ConsistentHashBalancer",
    "HealthAwareBalancer",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreakerRegistry",
    "Bulkhead",
    "RateLimiter",
    # Sidecar
    "SidecarProxy",
    "EnvoyConfig",
    "IstioConfig",
    "ProxyConfig",
    "TrafficInterceptor",
    # Resilience
    "RetryPolicy",
    "TimeoutPolicy",
    "FallbackPolicy",
    "ResiliencePolicy",
    "Resilience",
]
