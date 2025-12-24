"""
Rate Limiter Core Implementation for NebulaCompute.

Provides flexible rate limiting with multiple algorithms,
configurable limits, and detailed statistics.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .algorithms import TokenBucket
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        limit: int,
        remaining: int,
        reset_at: datetime,
        retry_after: float,
    ):
        super().__init__(message)
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
        self.retry_after = retry_after


class LimitType(Enum):
    """Types of rate limits."""
    REQUESTS = "requests"      # Number of requests
    BANDWIDTH = "bandwidth"    # Bytes transferred
    CPU_TIME = "cpu_time"      # CPU seconds used
    TOKENS = "tokens"          # API tokens (for AI)
    JOBS = "jobs"              # Number of jobs


class LimitScope(Enum):
    """Scope of rate limiting."""
    GLOBAL = "global"          # All clients combined
    PER_CLIENT = "per_client"  # Per client/IP
    PER_USER = "per_user"      # Per authenticated user
    PER_API_KEY = "per_api_key"  # Per API key
    PER_ENDPOINT = "per_endpoint"  # Per API endpoint


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    # Limit settings
    requests_per_second: float = 10.0
    requests_per_minute: float = 100.0
    requests_per_hour: float = 1000.0
    requests_per_day: float = 10000.0

    # Burst settings
    burst_size: int = 20
    burst_period_seconds: float = 1.0

    # Scope
    scope: LimitScope = LimitScope.PER_CLIENT
    limit_type: LimitType = LimitType.REQUESTS

    # Behavior
    block_duration_seconds: float = 60.0
    warn_threshold: float = 0.8  # Warn at 80% usage

    # Advanced
    enable_sliding_window: bool = True
    enable_adaptive: bool = False
    adaptive_target_latency_ms: float = 100.0


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime
    retry_after: Optional[float] = None
    current_usage: float = 0.0
    warning: Optional[str] = None

    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(self.reset_at.timestamp())),
        }

        if self.retry_after:
            headers["Retry-After"] = str(int(self.retry_after))

        if self.warning:
            headers["X-RateLimit-Warning"] = self.warning

        return headers


@dataclass
class RateLimitStats:
    """Statistics for rate limiting."""
    total_requests: int = 0
    allowed_requests: int = 0
    denied_requests: int = 0
    current_rate: float = 0.0
    peak_rate: float = 0.0
    blocked_clients: int = 0
    warnings_issued: int = 0
    start_time: datetime = field(default_factory=datetime.now)

    @property
    def denial_rate(self) -> float:
        """Get denial rate."""
        if self.total_requests == 0:
            return 0.0
        return self.denied_requests / self.total_requests

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_requests": self.total_requests,
            "allowed_requests": self.allowed_requests,
            "denied_requests": self.denied_requests,
            "denial_rate": f"{self.denial_rate:.2%}",
            "current_rate": f"{self.current_rate:.2f}/s",
            "peak_rate": f"{self.peak_rate:.2f}/s",
            "blocked_clients": self.blocked_clients,
            "warnings_issued": self.warnings_issued,
        }


class RateLimiter:
    """
    Comprehensive rate limiter for NebulaCompute.

    Features:
    - Multiple time windows (second, minute, hour, day)
    - Burst handling
    - Per-client and global limits
    - Adaptive rate limiting
    - Statistics and monitoring
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._stats = RateLimitStats()

        # Per-client state
        self._client_buckets: Dict[str, "TokenBucket"] = {}
        self._blocked_clients: Dict[str, datetime] = {}

        # Rate tracking
        self._request_times: List[float] = []
        self._lock = asyncio.Lock()

        # Import algorithm
        from .algorithms import TokenBucket
        self._bucket_class = TokenBucket

        logger.info("RateLimiter initialized with config: %s", self.config)

    async def check(
        self,
        client_id: str,
        cost: float = 1.0,
        endpoint: Optional[str] = None,
    ) -> RateLimitResult:
        """
        Check if a request should be allowed.

        Args:
            client_id: Identifier for the client
            cost: Cost of this request (default 1.0)
            endpoint: Optional endpoint for per-endpoint limits

        Returns:
            RateLimitResult with decision and metadata
        """
        async with self._lock:
            self._stats.total_requests += 1
            now = datetime.now()

            # Check if client is blocked
            if client_id in self._blocked_clients:
                block_expires = self._blocked_clients[client_id]
                if now < block_expires:
                    self._stats.denied_requests += 1
                    retry_after = (block_expires - now).total_seconds()
                    return RateLimitResult(
                        allowed=False,
                        limit=int(self.config.requests_per_minute),
                        remaining=0,
                        reset_at=block_expires,
                        retry_after=retry_after,
                    )
                else:
                    del self._blocked_clients[client_id]
                    self._stats.blocked_clients -= 1

            # Get or create bucket for client
            bucket = self._get_bucket(client_id)

            # Try to consume tokens
            allowed = bucket.consume(cost)

            # Calculate remaining and reset
            remaining = int(bucket.tokens)
            reset_at = now + timedelta(seconds=1.0 / bucket.refill_rate)

            # Update stats
            self._update_rate_stats()

            if allowed:
                self._stats.allowed_requests += 1

                # Check for warning threshold
                warning = None
                usage_ratio = 1 - (remaining / bucket.capacity)
                if usage_ratio >= self.config.warn_threshold:
                    warning = f"Rate limit {usage_ratio:.0%} used"
                    self._stats.warnings_issued += 1

                return RateLimitResult(
                    allowed=True,
                    limit=int(bucket.capacity),
                    remaining=remaining,
                    reset_at=reset_at,
                    current_usage=usage_ratio,
                    warning=warning,
                )

            else:
                self._stats.denied_requests += 1

                # Block client if exceeding limit
                block_until = now + timedelta(
                    seconds=self.config.block_duration_seconds
                )
                self._blocked_clients[client_id] = block_until
                self._stats.blocked_clients += 1

                retry_after = self.config.block_duration_seconds

                return RateLimitResult(
                    allowed=False,
                    limit=int(bucket.capacity),
                    remaining=0,
                    reset_at=block_until,
                    retry_after=retry_after,
                )

    async def acquire(
        self,
        client_id: str,
        cost: float = 1.0,
        timeout: Optional[float] = None,
    ) -> RateLimitResult:
        """
        Acquire rate limit permission, waiting if necessary.

        Args:
            client_id: Identifier for the client
            cost: Cost of this request
            timeout: Maximum time to wait

        Returns:
            RateLimitResult when allowed

        Raises:
            RateLimitExceeded if timeout exceeded
        """
        start_time = time.time()

        while True:
            result = await self.check(client_id, cost)

            if result.allowed:
                return result

            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise RateLimitExceeded(
                        message="Rate limit timeout exceeded",
                        limit=result.limit,
                        remaining=result.remaining,
                        reset_at=result.reset_at,
                        retry_after=result.retry_after or 0,
                    )

            # Wait before retry
            wait_time = min(result.retry_after or 1.0, 1.0)
            await asyncio.sleep(wait_time)

    def _get_bucket(self, client_id: str) -> "TokenBucket":
        """Get or create a token bucket for a client."""
        if client_id not in self._client_buckets:
            from .algorithms import TokenBucket

            self._client_buckets[client_id] = TokenBucket(
                capacity=self.config.burst_size,
                refill_rate=self.config.requests_per_second,
            )

        return self._client_buckets[client_id]

    def _update_rate_stats(self) -> None:
        """Update rate statistics."""
        now = time.time()

        # Add current request time
        self._request_times.append(now)

        # Remove old entries (older than 1 second)
        self._request_times = [
            t for t in self._request_times
            if now - t < 1.0
        ]

        # Calculate current rate
        self._stats.current_rate = len(self._request_times)

        # Update peak
        if self._stats.current_rate > self._stats.peak_rate:
            self._stats.peak_rate = self._stats.current_rate

    async def reset(self, client_id: Optional[str] = None) -> None:
        """Reset rate limit for a client or all clients."""
        async with self._lock:
            if client_id:
                self._client_buckets.pop(client_id, None)
                self._blocked_clients.pop(client_id, None)
            else:
                self._client_buckets.clear()
                self._blocked_clients.clear()
                self._stats = RateLimitStats()

    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiting statistics."""
        return self._stats.to_dict()

    def get_client_status(self, client_id: str) -> Dict[str, Any]:
        """Get status for a specific client."""
        bucket = self._client_buckets.get(client_id)
        blocked_until = self._blocked_clients.get(client_id)

        return {
            "client_id": client_id,
            "tokens_remaining": bucket.tokens if bucket else None,
            "capacity": bucket.capacity if bucket else None,
            "is_blocked": blocked_until is not None,
            "blocked_until": blocked_until.isoformat() if blocked_until else None,
        }

    async def cleanup(self) -> int:
        """Clean up expired entries."""
        async with self._lock:
            now = datetime.now()

            # Remove expired blocks
            expired = [
                client_id for client_id, expires in self._blocked_clients.items()
                if now >= expires
            ]

            for client_id in expired:
                del self._blocked_clients[client_id]

            # Remove inactive buckets (no activity for 1 hour)
            inactive_threshold = time.time() - 3600
            inactive = [
                client_id for client_id, bucket in self._client_buckets.items()
                if bucket.last_update < inactive_threshold
            ]

            for client_id in inactive:
                del self._client_buckets[client_id]

            cleaned = len(expired) + len(inactive)
            if cleaned > 0:
                logger.info(
                    "Cleaned up %d expired blocks and %d inactive buckets",
                    len(expired),
                    len(inactive),
                )

            return cleaned


class MultiTierRateLimiter:
    """
    Multi-tier rate limiter with different limits for different tiers.

    Useful for implementing usage tiers (free, basic, premium).
    """

    def __init__(self):
        self._tiers: Dict[str, RateLimiter] = {}
        self._client_tiers: Dict[str, str] = {}
        self._default_tier = "free"

    def add_tier(self, name: str, config: RateLimitConfig) -> None:
        """Add a rate limit tier."""
        self._tiers[name] = RateLimiter(config)
        logger.info("Added rate limit tier: %s", name)

    def set_client_tier(self, client_id: str, tier: str) -> None:
        """Set the tier for a client."""
        if tier not in self._tiers:
            raise ValueError(f"Unknown tier: {tier}")
        self._client_tiers[client_id] = tier

    async def check(
        self,
        client_id: str,
        cost: float = 1.0,
    ) -> RateLimitResult:
        """Check rate limit using client's tier."""
        tier = self._client_tiers.get(client_id, self._default_tier)
        limiter = self._tiers.get(tier)

        if not limiter:
            # No limiter for tier, allow
            return RateLimitResult(
                allowed=True,
                limit=0,
                remaining=0,
                reset_at=datetime.now(),
            )

        return await limiter.check(client_id, cost)

    def get_tier_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all tiers."""
        return {
            tier: limiter.get_stats()
            for tier, limiter in self._tiers.items()
        }
