"""
Gateway Middleware - وسيط البوابة
==================================

Middleware chain for request/response processing.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .gateway import GatewayRequest, GatewayResponse

logger = logging.getLogger(__name__)


class Middleware(ABC):
    """Base middleware class."""

    @abstractmethod
    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        """Process request and call next handler."""
        pass


class MiddlewareChain:
    """Chain of middleware handlers."""

    def __init__(self):
        self._middleware: List[Middleware] = []

    def use(self, middleware: Middleware) -> None:
        """Add middleware to chain."""
        self._middleware.append(middleware)

    def remove(self, middleware_type: type) -> None:
        """Remove middleware by type."""
        self._middleware = [
            m for m in self._middleware
            if not isinstance(m, middleware_type)
        ]

    async def execute(
        self,
        request: GatewayRequest,
        final_handler: Callable,
    ) -> GatewayResponse:
        """Execute middleware chain."""
        async def create_chain(index: int) -> Callable:
            if index >= len(self._middleware):
                return final_handler

            middleware = self._middleware[index]

            async def next_handler(req: GatewayRequest) -> GatewayResponse:
                next_fn = await create_chain(index + 1)
                return await next_fn(req)

            async def handler(req: GatewayRequest) -> GatewayResponse:
                return await middleware.process(req, next_handler)

            return handler

        chain = await create_chain(0)
        return await chain(request)


class AuthMiddleware(Middleware):
    """
    Authentication middleware.

    Validates JWT tokens, API keys, or other credentials.
    """

    def __init__(
        self,
        jwt_secret: Optional[str] = None,
        api_keys: Optional[Set[str]] = None,
        exempt_paths: Optional[List[str]] = None,
    ):
        self.jwt_secret = jwt_secret
        self.api_keys = api_keys or set()
        self.exempt_paths = exempt_paths or ["/health", "/ready", "/metrics"]

    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        # Check exempt paths
        for path in self.exempt_paths:
            if request.path.startswith(path):
                return await next_handler(request)

        # Check API key
        api_key = request.get_header("x-api-key")
        if api_key and api_key in self.api_keys:
            request.context["auth_type"] = "api_key"
            return await next_handler(request)

        # Check JWT
        auth_header = request.get_header("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = self._validate_jwt(token)
                request.context["auth_type"] = "jwt"
                request.context["user"] = payload
                return await next_handler(request)
            except Exception as e:
                logger.warning(f"JWT validation failed: {e}")
                return GatewayResponse.unauthorized("Invalid token")

        return GatewayResponse.unauthorized("Authentication required")

    def _validate_jwt(self, token: str) -> Dict[str, Any]:
        """Validate JWT token."""
        try:
            import jwt
            return jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
        except ImportError:
            # Fallback: basic validation
            parts = token.split(".")
            if len(parts) == 3:
                import base64
                payload = parts[1] + "=="  # Add padding
                return json.loads(base64.b64decode(payload))
            raise ValueError("Invalid token format")


class LoggingMiddleware(Middleware):
    """
    Request/Response logging middleware.
    """

    def __init__(
        self,
        log_body: bool = False,
        log_headers: bool = True,
        exclude_paths: Optional[List[str]] = None,
    ):
        self.log_body = log_body
        self.log_headers = log_headers
        self.exclude_paths = exclude_paths or ["/health", "/ready"]

    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        # Check exclusions
        for path in self.exclude_paths:
            if request.path.startswith(path):
                return await next_handler(request)

        start_time = time.time()

        # Log request
        log_data = {
            "request_id": request.request_id,
            "method": request.method,
            "path": request.path,
            "client_ip": request.client_ip,
        }

        if self.log_headers:
            log_data["headers"] = dict(request.headers)

        logger.info(f"Request: {json.dumps(log_data)}")

        # Process request
        response = await next_handler(request)

        # Log response
        duration_ms = (time.time() - start_time) * 1000
        log_data = {
            "request_id": request.request_id,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        }

        logger.info(f"Response: {json.dumps(log_data)}")

        return response


class RateLimitMiddleware(Middleware):
    """
    Rate limiting middleware.

    Implements token bucket algorithm.
    """

    def __init__(
        self,
        rate: int = 100,  # Requests per second
        burst: int = 200,
        key_func: Optional[Callable[[GatewayRequest], str]] = None,
    ):
        self.rate = rate
        self.burst = burst
        self.key_func = key_func or (lambda r: r.client_ip)
        self._buckets: Dict[str, Tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        key = self.key_func(request)

        allowed = await self._check_rate_limit(key)
        if not allowed:
            response = GatewayResponse.error(429, "Rate limit exceeded")
            response.set_header("retry-after", "1")
            return response

        return await next_handler(request)

    async def _check_rate_limit(self, key: str) -> bool:
        """Check if request is within rate limit."""
        now = time.time()

        async with self._lock:
            if key not in self._buckets:
                self._buckets[key] = (float(self.burst), now)
                return True

            tokens, last_update = self._buckets[key]

            # Refill tokens
            elapsed = now - last_update
            tokens = min(self.burst, tokens + elapsed * self.rate)

            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return True

            self._buckets[key] = (tokens, now)
            return False


class CORSMiddleware(Middleware):
    """
    CORS (Cross-Origin Resource Sharing) middleware.

    Security Note:
        Default is empty list (no CORS) for security.
        Use specific origins in production, never ["*"] with credentials.
    """

    def __init__(
        self,
        allowed_origins: Optional[List[str]] = None,
        allowed_methods: Optional[List[str]] = None,
        allowed_headers: Optional[List[str]] = None,
        allow_credentials: bool = False,
        max_age: int = 86400,
    ):
        # Security: default to empty list (no CORS) instead of ["*"]
        self.allowed_origins = allowed_origins or []
        self.allowed_methods = allowed_methods or [
            "GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"
        ]
        self.allowed_headers = allowed_headers or [
            "Content-Type", "Authorization", "X-Request-ID"
        ]
        self.allow_credentials = allow_credentials
        self.max_age = max_age

    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        origin = request.get_header("origin")

        # Handle preflight
        if request.method == "OPTIONS":
            response = GatewayResponse.ok()
            self._add_cors_headers(response, origin)
            return response

        # Process request
        response = await next_handler(request)
        self._add_cors_headers(response, origin)
        return response

    def _add_cors_headers(self, response: GatewayResponse, origin: str) -> None:
        """Add CORS headers to response."""
        if not self.allowed_origins:
            # No CORS configured - don't add any headers
            return
        elif "*" in self.allowed_origins:
            response.set_header("access-control-allow-origin", "*")
        elif origin in self.allowed_origins:
            response.set_header("access-control-allow-origin", origin)

        response.set_header(
            "access-control-allow-methods",
            ", ".join(self.allowed_methods)
        )
        response.set_header(
            "access-control-allow-headers",
            ", ".join(self.allowed_headers)
        )
        response.set_header("access-control-max-age", str(self.max_age))

        if self.allow_credentials:
            response.set_header("access-control-allow-credentials", "true")


class CompressionMiddleware(Middleware):
    """
    Response compression middleware.
    """

    def __init__(
        self,
        min_size: int = 1024,
        level: int = 6,
    ):
        self.min_size = min_size
        self.level = level

    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        response = await next_handler(request)

        # Check if client accepts gzip
        accept_encoding = request.get_header("accept-encoding")
        if "gzip" not in accept_encoding:
            return response

        # Check size threshold
        if len(response.body) < self.min_size:
            return response

        # Compress response
        compressed = gzip.compress(response.body, compresslevel=self.level)

        if len(compressed) < len(response.body):
            response.body = compressed
            response.set_header("content-encoding", "gzip")
            response.set_header("content-length", str(len(compressed)))

        return response


class TimeoutMiddleware(Middleware):
    """
    Request timeout middleware.
    """

    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds

    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        try:
            return await asyncio.wait_for(
                next_handler(request),
                timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            return GatewayResponse.gateway_timeout(
                f"Request timed out after {self.timeout_seconds}s"
            )


class RetryMiddleware(Middleware):
    """
    Retry middleware for failed requests.
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay_ms: int = 100,
        retry_on_status: Optional[List[int]] = None,
    ):
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self.retry_on_status = retry_on_status or [502, 503, 504]

    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        last_response = None

        for attempt in range(self.max_retries + 1):
            response = await next_handler(request)

            if response.status_code not in self.retry_on_status:
                return response

            last_response = response

            if attempt < self.max_retries:
                delay = self.retry_delay_ms * (2 ** attempt) / 1000
                await asyncio.sleep(delay)

        return last_response


class CacheMiddleware(Middleware):
    """
    Response caching middleware.
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        cache_methods: Optional[List[str]] = None,
        vary_headers: Optional[List[str]] = None,
    ):
        self.ttl_seconds = ttl_seconds
        self.cache_methods = cache_methods or ["GET"]
        self.vary_headers = vary_headers or []
        self._cache: Dict[str, Tuple[GatewayResponse, float]] = {}
        self._lock = asyncio.Lock()

    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        # Only cache specified methods
        if request.method not in self.cache_methods:
            return await next_handler(request)

        cache_key = self._build_cache_key(request)

        # Check cache
        async with self._lock:
            if cache_key in self._cache:
                response, expires_at = self._cache[cache_key]
                if time.time() < expires_at:
                    response.set_header("x-cache", "HIT")
                    return response
                else:
                    del self._cache[cache_key]

        # Get fresh response
        response = await next_handler(request)

        # Cache successful responses
        if 200 <= response.status_code < 300:
            async with self._lock:
                self._cache[cache_key] = (
                    response,
                    time.time() + self.ttl_seconds
                )
            response.set_header("x-cache", "MISS")

        return response

    def _build_cache_key(self, request: GatewayRequest) -> str:
        """Build cache key from request."""
        parts = [request.method, request.path]

        for header in self.vary_headers:
            parts.append(request.get_header(header))

        return hashlib.md5(":".join(parts).encode()).hexdigest()

    async def clear(self) -> None:
        """Clear cache."""
        async with self._lock:
            self._cache.clear()


class RequestIdMiddleware(Middleware):
    """
    Adds unique request ID to each request.
    """

    def __init__(self, header_name: str = "x-request-id"):
        self.header_name = header_name

    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        # Use existing or generate new request ID
        request_id = request.get_header(self.header_name)
        if not request_id:
            request_id = str(uuid.uuid4())
            request.set_header(self.header_name, request_id)

        request.context["request_id"] = request_id

        response = await next_handler(request)
        response.set_header(self.header_name, request_id)

        return response


class MetricsMiddleware(Middleware):
    """
    Collects request metrics.
    """

    def __init__(self):
        self._metrics = {
            "requests_total": 0,
            "requests_by_status": {},
            "requests_by_path": {},
            "latency_sum_ms": 0.0,
        }
        self._lock = asyncio.Lock()

    async def process(
        self,
        request: GatewayRequest,
        next_handler: Callable,
    ) -> GatewayResponse:
        start_time = time.time()

        response = await next_handler(request)

        latency_ms = (time.time() - start_time) * 1000

        async with self._lock:
            self._metrics["requests_total"] += 1
            self._metrics["latency_sum_ms"] += latency_ms

            status = str(response.status_code)
            self._metrics["requests_by_status"][status] = \
                self._metrics["requests_by_status"].get(status, 0) + 1

            path = request.path.split("?")[0]
            self._metrics["requests_by_path"][path] = \
                self._metrics["requests_by_path"].get(path, 0) + 1

        return response

    def get_metrics(self) -> Dict[str, Any]:
        """Get collected metrics."""
        total = self._metrics["requests_total"]
        return {
            **self._metrics,
            "avg_latency_ms": (
                self._metrics["latency_sum_ms"] / total if total > 0 else 0
            ),
        }
