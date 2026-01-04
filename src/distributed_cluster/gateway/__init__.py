"""
API Gateway - بوابة API المتقدمة
================================

Enterprise-grade API Gateway with advanced features.

Components:
- Core Gateway: Request routing and proxying
- Middleware: Authentication, logging, rate limiting
- Routing: Path matching, load balancing, service discovery
- Transforms: Request/Response modification
- Security: JWT, API keys, OAuth, CORS
- Plugins: Extensible plugin system
- Analytics: Request tracking and metrics
"""

from distributed_cluster.gateway.analytics import (
    AnalyticsConfig,
    EndpointMetrics,
    MetricsCollector,
    RequestLogger,
    RequestMetrics,
)
from distributed_cluster.gateway.gateway import (
    APIGateway,
    GatewayConfig,
    GatewayRequest,
    GatewayResponse,
    ProxyConfig,
)
from distributed_cluster.gateway.middleware import (
    AuthMiddleware,
    CacheMiddleware,
    CompressionMiddleware,
    CORSMiddleware,
    LoggingMiddleware,
    Middleware,
    MiddlewareChain,
    RateLimitMiddleware,
    RetryMiddleware,
    TimeoutMiddleware,
)
from distributed_cluster.gateway.plugins import (
    Plugin,
    PluginConfig,
    PluginContext,
    PluginHook,
    PluginManager,
)
from distributed_cluster.gateway.routing import (
    BackendPool,
    LoadBalancerType,
    PathMatcher,
    Route,
    RouteMatch,
    Router,
    RoutingRule,
    ServiceBackend,
)
from distributed_cluster.gateway.security import (
    APIKeyValidator,
    IPWhitelist,
    JWTValidator,
    OAuthValidator,
    RateLimiter,
    SecurityConfig,
    SecurityMiddleware,
)
from distributed_cluster.gateway.transforms import (
    BodyTransform,
    HeaderTransform,
    RequestTransform,
    ResponseTransform,
    TransformChain,
    URLRewriteTransform,
)

__all__ = [
    # Gateway
    "APIGateway",
    "GatewayConfig",
    "GatewayRequest",
    "GatewayResponse",
    "ProxyConfig",
    # Routing
    "Route",
    "Router",
    "RouteMatch",
    "PathMatcher",
    "RoutingRule",
    "ServiceBackend",
    "BackendPool",
    "LoadBalancerType",
    # Middleware
    "Middleware",
    "MiddlewareChain",
    "AuthMiddleware",
    "LoggingMiddleware",
    "RateLimitMiddleware",
    "CORSMiddleware",
    "CompressionMiddleware",
    "TimeoutMiddleware",
    "RetryMiddleware",
    "CacheMiddleware",
    # Transforms
    "RequestTransform",
    "ResponseTransform",
    "HeaderTransform",
    "BodyTransform",
    "URLRewriteTransform",
    "TransformChain",
    # Security
    "SecurityConfig",
    "JWTValidator",
    "APIKeyValidator",
    "OAuthValidator",
    "IPWhitelist",
    "SecurityMiddleware",
    "RateLimiter",
    # Plugins
    "Plugin",
    "PluginManager",
    "PluginConfig",
    "PluginHook",
    "PluginContext",
    # Analytics
    "RequestLogger",
    "MetricsCollector",
    "AnalyticsConfig",
    "RequestMetrics",
    "EndpointMetrics",
]
