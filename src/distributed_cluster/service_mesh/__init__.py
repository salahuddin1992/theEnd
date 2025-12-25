"""
Service Mesh Integration for NebulaCompute.

This module provides comprehensive service mesh capabilities including:
- Istio/Envoy sidecar support
- Traffic management and routing
- Circuit breaker patterns
- Service discovery and load balancing
"""

from .discovery import (
    ServiceRegistry,
    ServiceInstance,
    ServiceDiscovery,
    ConsulDiscovery,
    KubernetesDiscovery,
    EtcdDiscovery,
)
from .routing import (
    Router,
    Route,
    RouteRule,
    TrafficPolicy,
    WeightedRouting,
    HeaderBasedRouting,
    CanaryRouting,
)
from .loadbalancer import (
    LoadBalancer,
    RoundRobinBalancer,
    LeastConnectionsBalancer,
    WeightedBalancer,
    ConsistentHashBalancer,
    HealthAwareBalancer,
)
from .circuitbreaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    Bulkhead,
    RateLimiter,
)
from .sidecar import (
    SidecarProxy,
    EnvoyConfig,
    IstioConfig,
    ProxyConfig,
    TrafficInterceptor,
)
from .resilience import (
    RetryPolicy,
    TimeoutPolicy,
    FallbackPolicy,
    ResiliencePolicy,
    Resilience,
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
