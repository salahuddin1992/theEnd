"""
Rate Limiting Middleware for NebulaCompute.

Provides FastAPI middleware and decorators for rate limiting.
"""

import functools
import hashlib
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_client_id(request) -> str:
    """
    Extract client identifier from request.

    Priority:
    1. API key from header
    2. User ID from auth token
    3. Client IP address
    """
    # Check for API key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"api:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

    # Check for authenticated user
    user = getattr(request.state, "user", None)
    if user:
        user_id = getattr(user, "id", None) or getattr(user, "user_id", None)
        if user_id:
            return f"user:{user_id}"

    # Fall back to IP address
    client_ip = request.client.host if request.client else "unknown"

    # Check for forwarded IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    return f"ip:{client_ip}"


class RateLimitMiddleware:
    """
    FastAPI middleware for rate limiting.

    Usage:
        from fastapi import FastAPI
        from distributed_cluster.ratelimit import RateLimitMiddleware, RateLimitConfig

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            config=RateLimitConfig(requests_per_second=10),
        )
    """

    def __init__(
        self,
        app,
        config=None,
        exclude_paths: Optional[List[str]] = None,
        include_paths: Optional[List[str]] = None,
        key_func: Optional[Callable] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            config: RateLimitConfig
            exclude_paths: Paths to exclude from rate limiting
            include_paths: Only rate limit these paths (if set)
            key_func: Custom function to extract client ID
        """
        self.app = app
        self.exclude_paths = exclude_paths or ["/health", "/metrics"]
        self.include_paths = include_paths
        self.key_func = key_func or get_client_id

        from .limiter import RateLimitConfig, RateLimiter
        self.config = config or RateLimitConfig()
        self.limiter = RateLimiter(self.config)

    async def __call__(self, scope, receive, send):
        """ASGI middleware handler."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Import here to avoid circular imports
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        request = Request(scope, receive)
        path = request.url.path

        # Check exclusions
        if self._should_skip(path):
            await self.app(scope, receive, send)
            return

        # Get client ID
        client_id = self.key_func(request)

        # Check rate limit
        result = await self.limiter.check(client_id)

        if not result.allowed:
            # Return rate limit response
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "limit": result.limit,
                    "retry_after": result.retry_after,
                },
                headers=result.to_headers(),
            )
            await response(scope, receive, send)
            return

        # Add rate limit headers to response
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                for key, value in result.to_headers().items():
                    headers[key.encode()] = value.encode()
                message["headers"] = list(headers.items())
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _should_skip(self, path: str) -> bool:
        """Check if path should skip rate limiting."""
        # Check include paths
        if self.include_paths:
            return not any(path.startswith(p) for p in self.include_paths)

        # Check exclude paths
        return any(path.startswith(p) for p in self.exclude_paths)


def rate_limit(
    requests_per_second: float = 10.0,
    requests_per_minute: Optional[float] = None,
    burst_size: int = 20,
    key_func: Optional[Callable] = None,
    scope: str = "endpoint",
):
    """
    Decorator for rate limiting individual endpoints.

    Usage:
        @app.get("/api/data")
        @rate_limit(requests_per_second=5, burst_size=10)
        async def get_data():
            return {"data": "value"}

    Args:
        requests_per_second: Maximum requests per second
        requests_per_minute: Maximum requests per minute
        burst_size: Allowed burst size
        key_func: Custom function to extract client ID
        scope: Rate limit scope (endpoint, global)
    """
    from .limiter import RateLimitConfig, RateLimiter

    # Create limiter for this endpoint
    config = RateLimitConfig(
        requests_per_second=requests_per_second,
        requests_per_minute=requests_per_minute or requests_per_second * 60,
        burst_size=burst_size,
    )

    _limiter = RateLimiter(config)
    _key_func = key_func or get_client_id

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get request from args or kwargs
            request = kwargs.get("request")
            if not request and args:
                for arg in args:
                    if hasattr(arg, "client"):
                        request = arg
                        break

            # Get client ID
            if request:
                client_id = _key_func(request)
            else:
                client_id = "default"

            # Add scope to client ID
            if scope == "endpoint":
                client_id = f"{func.__name__}:{client_id}"

            # Check rate limit
            result = await _limiter.check(client_id)

            if not result.allowed:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "limit": result.limit,
                        "retry_after": result.retry_after,
                    },
                    headers=result.to_headers(),
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


class RateLimitGroup:
    """
    Group multiple endpoints under a shared rate limit.

    Usage:
        group = RateLimitGroup("api", requests_per_second=100)

        @app.get("/api/users")
        @group.limit()
        async def get_users():
            pass

        @app.get("/api/items")
        @group.limit()
        async def get_items():
            pass
    """

    def __init__(
        self,
        name: str,
        requests_per_second: float = 10.0,
        requests_per_minute: Optional[float] = None,
        burst_size: int = 20,
    ):
        """
        Initialize rate limit group.

        Args:
            name: Group name
            requests_per_second: Maximum requests per second for group
            requests_per_minute: Maximum requests per minute
            burst_size: Allowed burst size
        """
        from .limiter import RateLimitConfig, RateLimiter

        self.name = name
        self.config = RateLimitConfig(
            requests_per_second=requests_per_second,
            requests_per_minute=requests_per_minute or requests_per_second * 60,
            burst_size=burst_size,
        )
        self._limiter = RateLimiter(self.config)

    def limit(
        self,
        cost: float = 1.0,
        key_func: Optional[Callable] = None,
    ):
        """
        Decorator to apply group rate limit.

        Args:
            cost: Cost of this endpoint in the group budget
            key_func: Custom function to extract client ID
        """
        _key_func = key_func or get_client_id
        _cost = cost

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Get request
                request = kwargs.get("request")
                if not request and args:
                    for arg in args:
                        if hasattr(arg, "client"):
                            request = arg
                            break

                # Get client ID with group prefix
                if request:
                    client_id = f"{self.name}:{_key_func(request)}"
                else:
                    client_id = f"{self.name}:default"

                # Check rate limit
                result = await self._limiter.check(client_id, cost=_cost)

                if not result.allowed:
                    from fastapi import HTTPException
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": f"Rate limit exceeded for group '{self.name}'",
                            "limit": result.limit,
                            "retry_after": result.retry_after,
                        },
                        headers=result.to_headers(),
                    )

                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def get_stats(self) -> Dict[str, Any]:
        """Get group statistics."""
        stats = self._limiter.get_stats()
        stats["group_name"] = self.name
        return stats
