"""
API Gateway Core - نواة بوابة API
==================================

Core API Gateway implementation with request routing and proxying.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class GatewayStatus(str, Enum):
    """Gateway status."""
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ProxyConfig:
    """Proxy configuration for upstream services."""
    timeout_seconds: float = 30.0
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay_ms: int = 100
    follow_redirects: bool = True
    verify_ssl: bool = True
    buffer_size: int = 8192

    # Connection pooling
    pool_connections: int = 100
    pool_maxsize: int = 100
    pool_ttl_seconds: int = 300


@dataclass
class GatewayConfig:
    """API Gateway configuration."""
    name: str = "api-gateway"
    host: str = "0.0.0.0"
    port: int = 8080

    # SSL/TLS
    ssl_enabled: bool = False
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None

    # Proxy settings
    proxy: ProxyConfig = field(default_factory=ProxyConfig)

    # Request limits
    max_request_size_bytes: int = 10 * 1024 * 1024  # 10MB
    max_header_size_bytes: int = 16 * 1024  # 16KB

    # Timeouts
    request_timeout_seconds: float = 60.0
    idle_timeout_seconds: float = 300.0

    # Workers
    workers: int = 4

    # Logging
    access_log_enabled: bool = True
    access_log_format: str = "combined"

    # Health check
    health_check_path: str = "/health"
    ready_check_path: str = "/ready"

    # Metrics
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "ssl_enabled": self.ssl_enabled,
            "max_request_size_bytes": self.max_request_size_bytes,
            "request_timeout_seconds": self.request_timeout_seconds,
            "workers": self.workers,
        }


@dataclass
class GatewayRequest:
    """Represents an incoming gateway request."""
    request_id: str
    method: str
    path: str
    query_string: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    # Client info
    client_ip: str = ""
    client_port: int = 0

    # Timing
    received_at: datetime = field(default_factory=datetime.utcnow)

    # Context
    context: Dict[str, Any] = field(default_factory=dict)

    # Matched route info
    route_id: Optional[str] = None
    route_params: Dict[str, str] = field(default_factory=dict)

    @property
    def full_path(self) -> str:
        if self.query_string:
            return f"{self.path}?{self.query_string}"
        return self.path

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    @property
    def content_length(self) -> int:
        return int(self.headers.get("content-length", 0))

    def get_header(self, name: str, default: str = "") -> str:
        """Get header value (case-insensitive)."""
        return self.headers.get(name.lower(), default)

    def set_header(self, name: str, value: str) -> None:
        """Set header value."""
        self.headers[name.lower()] = value

    def get_json(self) -> Any:
        """Parse body as JSON."""
        if self.body:
            return json.loads(self.body.decode("utf-8"))
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "method": self.method,
            "path": self.path,
            "query_string": self.query_string,
            "headers": self.headers,
            "client_ip": self.client_ip,
            "received_at": self.received_at.isoformat(),
        }

    @classmethod
    def create(
        cls,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        body: bytes = b"",
        **kwargs
    ) -> GatewayRequest:
        """Factory method to create a request."""
        return cls(
            request_id=str(uuid.uuid4()),
            method=method.upper(),
            path=path,
            headers={k.lower(): v for k, v in (headers or {}).items()},
            body=body,
            **kwargs
        )


@dataclass
class GatewayResponse:
    """Represents a gateway response."""
    status_code: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Upstream info
    upstream_status: Optional[int] = None
    upstream_latency_ms: float = 0.0

    # Error info
    error: Optional[str] = None

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    @property
    def content_length(self) -> int:
        return len(self.body)

    def set_header(self, name: str, value: str) -> None:
        """Set header value."""
        self.headers[name.lower()] = value

    def set_json(self, data: Any) -> None:
        """Set body as JSON."""
        self.body = json.dumps(data).encode("utf-8")
        self.set_header("content-type", "application/json")

    @classmethod
    def ok(cls, body: Union[bytes, str, dict] = b"", headers: Optional[Dict[str, str]] = None) -> GatewayResponse:
        """Create a 200 OK response."""
        response = cls(status_code=200, headers=headers or {})
        if isinstance(body, dict):
            response.set_json(body)
        elif isinstance(body, str):
            response.body = body.encode("utf-8")
        else:
            response.body = body
        return response

    @classmethod
    def create_error(cls, status_code: int, message: str) -> "GatewayResponse":
        """Create an error response."""
        response = cls(status_code=status_code, error=message)
        response.set_json({"error": message, "status": status_code})
        return response

    @classmethod
    def not_found(cls, message: str = "Not Found") -> GatewayResponse:
        return cls.create_error(404, message)

    @classmethod
    def bad_request(cls, message: str = "Bad Request") -> GatewayResponse:
        return cls.create_error(400, message)

    @classmethod
    def unauthorized(cls, message: str = "Unauthorized") -> GatewayResponse:
        return cls.create_error(401, message)

    @classmethod
    def forbidden(cls, message: str = "Forbidden") -> GatewayResponse:
        return cls.create_error(403, message)

    @classmethod
    def internal_error(cls, message: str = "Internal Server Error") -> GatewayResponse:
        return cls.create_error(500, message)

    @classmethod
    def service_unavailable(cls, message: str = "Service Unavailable") -> GatewayResponse:
        return cls.create_error(503, message)

    @classmethod
    def gateway_timeout(cls, message: str = "Gateway Timeout") -> GatewayResponse:
        return cls.create_error(504, message)


class RequestHandler:
    """Base request handler interface."""

    async def handle(self, request: GatewayRequest) -> GatewayResponse:
        """Handle a request and return a response."""
        raise NotImplementedError


class ProxyHandler(RequestHandler):
    """Proxies requests to upstream services."""

    def __init__(
        self,
        upstream_url: str,
        config: Optional[ProxyConfig] = None,
    ):
        self.upstream_url = upstream_url.rstrip("/")
        self.config = config or ProxyConfig()
        self._session = None

    async def handle(self, request: GatewayRequest) -> GatewayResponse:
        """Proxy request to upstream."""
        import aiohttp

        start_time = time.time()

        # Build upstream URL
        target_url = f"{self.upstream_url}{request.full_path}"

        # Prepare headers
        headers = dict(request.headers)
        headers["x-forwarded-for"] = request.client_ip
        headers["x-request-id"] = request.request_id

        try:
            timeout = aiohttp.ClientTimeout(
                total=self.config.timeout_seconds,
                connect=self.config.connect_timeout_seconds,
            )

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    data=request.body if request.body else None,
                    ssl=self.config.verify_ssl,
                    allow_redirects=self.config.follow_redirects,
                ) as upstream_response:
                    body = await upstream_response.read()

                    response = GatewayResponse(
                        status_code=upstream_response.status,
                        headers=dict(upstream_response.headers),
                        body=body,
                        upstream_status=upstream_response.status,
                        upstream_latency_ms=(time.time() - start_time) * 1000,
                    )

                    return response

        except asyncio.TimeoutError:
            return GatewayResponse.gateway_timeout("Upstream timeout")
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            return GatewayResponse.service_unavailable(str(e))


class APIGateway:
    """
    API Gateway - بوابة API.

    Enterprise-grade API Gateway with routing, middleware, and proxying.

    Example:
        gateway = APIGateway(config)

        # Add routes
        gateway.add_route("/api/users/*", "http://users-service:8080")
        gateway.add_route("/api/orders/*", "http://orders-service:8080")

        # Add middleware
        gateway.use(AuthMiddleware())
        gateway.use(RateLimitMiddleware(rate=100))

        # Start gateway
        await gateway.start()
    """

    def __init__(self, config: Optional[GatewayConfig] = None):
        self.config = config or GatewayConfig()
        self._status = GatewayStatus.STOPPED
        self._routes: List[Tuple[str, str, RequestHandler]] = []
        self._middleware: List[Callable] = []
        self._plugins: List[Any] = []
        self._stats = GatewayStats()

        # Request/Response hooks
        self._request_hooks: List[Callable] = []
        self._response_hooks: List[Callable] = []

    @property
    def status(self) -> GatewayStatus:
        return self._status

    def add_route(
        self,
        path: str,
        upstream: str,
        methods: Optional[List[str]] = None,
        handler: Optional[RequestHandler] = None,
    ) -> None:
        """Add a route to the gateway."""
        if handler is None:
            handler = ProxyHandler(upstream, self.config.proxy)

        self._routes.append((path, upstream, handler))
        logger.info(f"Added route: {path} -> {upstream}")

    def remove_route(self, path: str) -> None:
        """Remove a route."""
        self._routes = [(p, u, h) for p, u, h in self._routes if p != path]

    def use(self, middleware: Callable) -> None:
        """Add middleware to the chain."""
        self._middleware.append(middleware)

    def add_plugin(self, plugin: Any) -> None:
        """Add a plugin."""
        self._plugins.append(plugin)
        if hasattr(plugin, "on_load"):
            plugin.on_load(self)

    def on_request(self, hook: Callable) -> None:
        """Add request hook."""
        self._request_hooks.append(hook)

    def on_response(self, hook: Callable) -> None:
        """Add response hook."""
        self._response_hooks.append(hook)

    async def handle_request(self, request: GatewayRequest) -> GatewayResponse:
        """Handle an incoming request."""
        start_time = time.time()
        self._stats.total_requests += 1

        try:
            # Run request hooks
            for hook in self._request_hooks:
                result = hook(request)
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, GatewayResponse):
                    return result

            # Run middleware chain
            for middleware in self._middleware:
                result = middleware(request)
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, GatewayResponse):
                    return result

            # Find matching route
            handler = self._match_route(request)
            if handler is None:
                return GatewayResponse.not_found(f"No route for {request.path}")

            # Handle request
            response = await handler.handle(request)

            # Run response hooks
            for hook in self._response_hooks:
                result = hook(request, response)
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, GatewayResponse):
                    response = result

            # Update stats
            if 200 <= response.status_code < 400:
                self._stats.successful_requests += 1
            elif response.status_code >= 500:
                self._stats.server_errors += 1
            else:
                self._stats.client_errors += 1

            self._stats.total_latency_ms += (time.time() - start_time) * 1000

            return response

        except Exception as e:
            logger.error(f"Request handling error: {e}")
            self._stats.server_errors += 1
            return GatewayResponse.internal_error(str(e))

    def _match_route(self, request: GatewayRequest) -> Optional[RequestHandler]:
        """Find handler for request path."""
        path = request.path

        for route_path, _, handler in self._routes:
            if self._path_matches(route_path, path):
                return handler

        return None

    def _path_matches(self, pattern: str, path: str) -> bool:
        """Check if path matches pattern."""
        # Handle exact match
        if pattern == path:
            return True

        # Handle wildcard
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            return path.startswith(prefix)

        # Handle prefix match
        if pattern.endswith("/"):
            return path.startswith(pattern)

        return False

    async def start(self) -> None:
        """Start the gateway."""
        self._status = GatewayStatus.STARTING

        # Initialize plugins
        for plugin in self._plugins:
            if hasattr(plugin, "on_start"):
                await plugin.on_start()

        self._status = GatewayStatus.RUNNING
        logger.info(f"API Gateway started on {self.config.host}:{self.config.port}")

    async def stop(self) -> None:
        """Stop the gateway."""
        self._status = GatewayStatus.STOPPING

        # Cleanup plugins
        for plugin in self._plugins:
            if hasattr(plugin, "on_stop"):
                await plugin.on_stop()

        self._status = GatewayStatus.STOPPED
        logger.info("API Gateway stopped")

    def get_stats(self) -> Dict[str, Any]:
        """Get gateway statistics."""
        return self._stats.to_dict()

    def health_check(self) -> Dict[str, Any]:
        """Health check endpoint."""
        return {
            "status": "healthy" if self._status == GatewayStatus.RUNNING else "unhealthy",
            "gateway_status": self._status.value,
            "routes": len(self._routes),
            "uptime_seconds": self._stats.uptime_seconds,
        }

    def list_routes(self) -> List[Dict[str, str]]:
        """List all registered routes."""
        return [
            {"path": path, "upstream": upstream}
            for path, upstream, _ in self._routes
        ]


@dataclass
class GatewayStats:
    """Gateway statistics."""
    total_requests: int = 0
    successful_requests: int = 0
    client_errors: int = 0
    server_errors: int = 0
    total_latency_ms: float = 0.0
    start_time: datetime = field(default_factory=datetime.utcnow)

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "client_errors": self.client_errors,
            "server_errors": self.server_errors,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "uptime_seconds": self.uptime_seconds,
        }
