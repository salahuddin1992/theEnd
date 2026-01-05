"""
HTTP Connection Pool for NebulaCompute.

Provides efficient HTTP client pooling with:
- Connection reuse
- Automatic retry
- Circuit breaker
- Request tracing
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class HTTPClientConfig:
    """Configuration for HTTP connection pool."""

    # Connection settings
    max_connections: int = 100
    max_connections_per_host: int = 10
    connection_timeout: float = 10.0
    read_timeout: float = 30.0
    keepalive_timeout: float = 30.0

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    retry_statuses: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])

    # Circuit breaker
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: float = 30.0

    # Request settings
    default_headers: Dict[str, str] = field(default_factory=dict)
    follow_redirects: bool = True
    max_redirects: int = 10


@dataclass
class CircuitBreaker:
    """Circuit breaker for HTTP endpoints."""

    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None
    failure_threshold: int = 5
    recovery_timeout: float = 30.0

    def record_success(self) -> None:
        """Record a successful request."""
        self.failures = 0
        self.last_success = datetime.now()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info("Circuit closed after recovery")

    def record_failure(self) -> None:
        """Record a failed request."""
        self.failures += 1
        self.last_failure = datetime.now()

        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                "Circuit opened after %d failures",
                self.failures,
            )

    def can_execute(self) -> bool:
        """Check if requests can be executed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure:
                elapsed = (datetime.now() - self.last_failure).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit half-open, testing recovery")
                    return True
            return False

        # HALF_OPEN - allow one request
        return True


class HTTPConnectionPool:
    """
    HTTP connection pool with advanced features.

    Features:
    - Connection pooling per host
    - Automatic retry with backoff
    - Circuit breaker per host
    - Request tracing
    - Rate limiting integration
    """

    def __init__(self, config: Optional[HTTPClientConfig] = None):
        """
        Initialize HTTP connection pool.

        Args:
            config: Pool configuration
        """
        self.config = config or HTTPClientConfig()
        self._client = None
        self._circuits: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
        self._request_count = 0
        self._error_count = 0
        self._total_time = 0.0

    async def start(self) -> None:
        """Start the connection pool."""
        try:
            import httpx

            self._client = httpx.AsyncClient(
                limits=httpx.Limits(
                    max_connections=self.config.max_connections,
                    max_keepalive_connections=self.config.max_connections_per_host,
                ),
                timeout=httpx.Timeout(
                    connect=self.config.connection_timeout,
                    read=self.config.read_timeout,
                ),
                follow_redirects=self.config.follow_redirects,
                headers=self.config.default_headers,
            )

            logger.info("HTTPConnectionPool started")

        except ImportError:
            logger.warning("httpx not installed, using aiohttp fallback")
            await self._start_aiohttp()

    async def _start_aiohttp(self) -> None:
        """Start with aiohttp backend."""
        try:
            import aiohttp

            connector = aiohttp.TCPConnector(
                limit=self.config.max_connections,
                limit_per_host=self.config.max_connections_per_host,
                keepalive_timeout=self.config.keepalive_timeout,
            )

            timeout = aiohttp.ClientTimeout(
                connect=self.config.connection_timeout,
                total=self.config.read_timeout,
            )

            self._client = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=self.config.default_headers,
            )

            logger.info("HTTPConnectionPool started with aiohttp")

        except ImportError:
            raise RuntimeError("No HTTP client library available")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._client:
            await self._client.aclose() if hasattr(self._client, "aclose") else await self._client.close()
            self._client = None

        logger.info("HTTPConnectionPool closed")

    def _get_circuit(self, host: str) -> CircuitBreaker:
        """Get or create circuit breaker for host."""
        if host not in self._circuits:
            self._circuits[host] = CircuitBreaker(
                failure_threshold=self.config.circuit_failure_threshold,
                recovery_timeout=self.config.circuit_recovery_timeout,
            )
        return self._circuits[host]

    async def request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> "HTTPResponse":
        """
        Make an HTTP request with retry and circuit breaker.

        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional request arguments

        Returns:
            HTTPResponse object
        """
        from urllib.parse import urlparse

        # Extract host for circuit breaker
        parsed = urlparse(url)
        host = parsed.netloc

        # Check circuit breaker
        circuit = self._get_circuit(host)
        if not circuit.can_execute():
            raise ConnectionError(f"Circuit open for {host}")

        # Retry loop
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self._do_request(method, url, **kwargs)

                # Check if should retry based on status
                if response.status_code in self.config.retry_statuses:
                    if attempt < self.config.max_retries:
                        delay = self.config.retry_delay * (self.config.retry_backoff**attempt)
                        logger.warning(
                            "Retrying %s %s after %s status (attempt %d)",
                            method,
                            url,
                            response.status_code,
                            attempt + 1,
                        )
                        await asyncio.sleep(delay)
                        continue

                circuit.record_success()
                return response

            except Exception as e:
                last_error = e
                circuit.record_failure()
                self._error_count += 1

                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * (self.config.retry_backoff**attempt)
                    logger.warning(
                        "Retrying %s %s after error: %s (attempt %d)",
                        method,
                        url,
                        e,
                        attempt + 1,
                    )
                    await asyncio.sleep(delay)

        raise last_error or ConnectionError("Request failed")

    async def _do_request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> "HTTPResponse":
        """Execute single request."""
        start_time = time.perf_counter()

        try:
            self._request_count += 1

            if hasattr(self._client, "request"):
                # httpx
                response = await self._client.request(method, url, **kwargs)
                return HTTPResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content=response.content,
                    elapsed=time.perf_counter() - start_time,
                )
            else:
                # aiohttp
                async with self._client.request(method, url, **kwargs) as response:
                    content = await response.read()
                    return HTTPResponse(
                        status_code=response.status,
                        headers=dict(response.headers),
                        content=content,
                        elapsed=time.perf_counter() - start_time,
                    )

        finally:
            self._total_time += time.perf_counter() - start_time

    async def get(self, url: str, **kwargs) -> "HTTPResponse":
        """Make GET request."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> "HTTPResponse":
        """Make POST request."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> "HTTPResponse":
        """Make PUT request."""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> "HTTPResponse":
        """Make DELETE request."""
        return await self.request("DELETE", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> "HTTPResponse":
        """Make PATCH request."""
        return await self.request("PATCH", url, **kwargs)

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        avg_time = self._total_time / self._request_count if self._request_count else 0

        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "error_rate": (self._error_count / self._request_count if self._request_count else 0),
            "avg_request_time_ms": avg_time * 1000,
            "circuits": {
                host: {
                    "state": circuit.state.value,
                    "failures": circuit.failures,
                }
                for host, circuit in self._circuits.items()
            },
        }


@dataclass
class HTTPResponse:
    """HTTP response wrapper."""

    status_code: int
    headers: Dict[str, str]
    content: bytes
    elapsed: float

    @property
    def text(self) -> str:
        """Get response as text."""
        return self.content.decode("utf-8")

    def json(self) -> Any:
        """Parse response as JSON."""
        import json

        return json.loads(self.content)

    @property
    def ok(self) -> bool:
        """Check if response is successful."""
        return 200 <= self.status_code < 300

    def raise_for_status(self) -> None:
        """Raise exception for error status codes."""
        if not self.ok:
            raise HTTPError(self.status_code, self.text)


class HTTPError(Exception):
    """HTTP error exception."""

    def __init__(self, status_code: int, message: str):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
