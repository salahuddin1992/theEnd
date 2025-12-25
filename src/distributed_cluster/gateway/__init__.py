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

from distributed_cluster.gateway.gateway import (
    APIGateway,
    GatewayConfig,
    GatewayRequest,
    GatewayResponse,
    ProxyConfig,
)

from distributed_cluster.gateway.routing import (
    Route,
    Router,
    RouteMatch,
    PathMatcher,
    RoutingRule,
    ServiceBackend,
    BackendPool,
    LoadBalancerType,
)

from distributed_cluster.gateway.middleware import (
    Middleware,
    MiddlewareChain,
    AuthMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    CORSMiddleware,
    CompressionMiddleware,
    TimeoutMiddleware,
    RetryMiddleware,
    CacheMiddleware,
)

from distributed_cluster.gateway.transforms import (
    RequestTransform,
    ResponseTransform,
    HeaderTransform,
    BodyTransform,
    URLRewriteTransform,
    TransformChain,
)

from distributed_cluster.gateway.security import (
    SecurityConfig,
    JWTValidator,
    APIKeyValidator,
    OAuthValidator,
    IPWhitelist,
    SecurityMiddleware,
    RateLimiter,
)

from distributed_cluster.gateway.plugins import (
    Plugin,
    PluginManager,
    PluginConfig,
    PluginHook,
    PluginContext,
)

from distributed_cluster.gateway.analytics import (
    RequestLogger,
    MetricsCollector,
    AnalyticsConfig,
    RequestMetrics,
    EndpointMetrics,
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
