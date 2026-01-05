"""
Rate limiting implementations using various algorithms.
"""

import asyncio
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, limit: int, window: int, retry_after: float):
        self.limit = limit
        self.window = window
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Limit: {limit} requests per {window}s. Retry after {retry_after:.2f}s")


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    requests_per_second: float = 10.0
    burst_size: int = 20
    window_seconds: int = 60
    algorithm: str = "token_bucket"  # token_bucket, sliding_window, fixed_window
    key_prefix: str = "ratelimit"
    enable_headers: bool = True
    headers_prefix: str = "X-RateLimit"


@dataclass
class RateLimitInfo:
    """Rate limit status information."""

    limit: int
    remaining: int
    reset_at: datetime
    retry_after: Optional[float] = None

    def to_headers(self, prefix: str = "X-RateLimit") -> Dict[str, str]:
        return {
            f"{prefix}-Limit": str(self.limit),
            f"{prefix}-Remaining": str(self.remaining),
            f"{prefix}-Reset": str(int(self.reset_at.timestamp())),
        }


class RateLimiter(ABC):
    """Abstract base class for rate limiters."""

    @abstractmethod
    def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        """Acquire tokens from the rate limiter."""
        pass

    @abstractmethod
    def get_info(self, key: str = "default") -> RateLimitInfo:
        """Get current rate limit info."""
        pass

    def check(self, key: str = "default", tokens: int = 1) -> RateLimitInfo:
        """Check rate limit without consuming tokens."""
        return self.get_info(key)

    def reset(self, key: str = "default"):
        """Reset rate limit for a key."""
        pass


class TokenBucket(RateLimiter):
    """
    Token bucket rate limiter.

    Allows bursts up to bucket capacity, then limits to refill rate.
    """

    def __init__(
        self,
        rate: float = 10.0,  # Tokens per second
        capacity: int = 20,  # Max tokens (burst size)
    ):
        self.rate = rate
        self.capacity = capacity
        self._buckets: Dict[str, Tuple[float, float]] = {}  # key -> (tokens, last_update)
        self._lock = threading.Lock()

    def _refill(self, key: str) -> float:
        """Refill tokens based on elapsed time."""
        now = time.time()

        if key not in self._buckets:
            self._buckets[key] = (float(self.capacity), now)
            return float(self.capacity)

        tokens, last_update = self._buckets[key]
        elapsed = now - last_update
        new_tokens = min(self.capacity, tokens + elapsed * self.rate)
        self._buckets[key] = (new_tokens, now)

        return new_tokens

    def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        with self._lock:
            available = self._refill(key)

            if available >= tokens:
                self._buckets[key] = (available - tokens, time.time())
                return True

            return False

    def acquire_wait(self, key: str = "default", tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """Acquire tokens, waiting if necessary."""
        start = time.time()

        while True:
            if self.acquire(key, tokens):
                return True

            if timeout is not None and (time.time() - start) >= timeout:
                return False

            # Calculate wait time
            with self._lock:
                current, _ = self._buckets.get(key, (0, time.time()))
                needed = tokens - current
                wait_time = needed / self.rate

            time.sleep(min(wait_time, 0.1))

    async def acquire_async(self, key: str = "default", tokens: int = 1) -> bool:
        """Async acquire tokens."""
        while not self.acquire(key, tokens):
            with self._lock:
                current, _ = self._buckets.get(key, (0, time.time()))
                needed = tokens - current
                wait_time = needed / self.rate

            await asyncio.sleep(min(wait_time, 0.1))

        return True

    def get_info(self, key: str = "default") -> RateLimitInfo:
        with self._lock:
            tokens = self._refill(key)

            return RateLimitInfo(
                limit=self.capacity,
                remaining=int(tokens),
                reset_at=datetime.now(timezone.utc),
                retry_after=(1 - tokens) / self.rate if tokens < 1 else None,
            )

    def reset(self, key: str = "default"):
        with self._lock:
            self._buckets[key] = (float(self.capacity), time.time())


class SlidingWindow(RateLimiter):
    """
    Sliding window rate limiter.

    More accurate than fixed window but requires more memory.
    """

    def __init__(
        self,
        limit: int = 100,
        window_seconds: int = 60,
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: Dict[str, deque] = {}  # key -> deque of timestamps
        self._lock = threading.Lock()

    def _cleanup(self, key: str, now: float):
        """Remove expired entries."""
        if key not in self._requests:
            self._requests[key] = deque()
            return

        window_start = now - self.window_seconds
        while self._requests[key] and self._requests[key][0] < window_start:
            self._requests[key].popleft()

    def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        now = time.time()

        with self._lock:
            self._cleanup(key, now)

            if len(self._requests[key]) + tokens <= self.limit:
                for _ in range(tokens):
                    self._requests[key].append(now)
                return True

            return False

    def get_info(self, key: str = "default") -> RateLimitInfo:
        now = time.time()

        with self._lock:
            self._cleanup(key, now)

            count = len(self._requests.get(key, []))
            remaining = max(0, self.limit - count)

            # Calculate reset time
            if self._requests.get(key):
                oldest = self._requests[key][0]
                reset_at = datetime.fromtimestamp(oldest + self.window_seconds)
            else:
                reset_at = datetime.fromtimestamp(now + self.window_seconds)

            retry_after = None
            if remaining == 0 and self._requests.get(key):
                retry_after = self._requests[key][0] + self.window_seconds - now

            return RateLimitInfo(
                limit=self.limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
            )

    def reset(self, key: str = "default"):
        with self._lock:
            self._requests[key] = deque()


class FixedWindow(RateLimiter):
    """
    Fixed window rate limiter.

    Simple but can allow up to 2x burst at window boundaries.
    """

    def __init__(
        self,
        limit: int = 100,
        window_seconds: int = 60,
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: Dict[str, Tuple[int, int]] = {}  # key -> (count, window_id)
        self._lock = threading.Lock()

    def _get_window_id(self) -> int:
        """Get current window ID."""
        return int(time.time() // self.window_seconds)

    def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        window_id = self._get_window_id()

        with self._lock:
            if key not in self._windows:
                self._windows[key] = (0, window_id)

            count, stored_window = self._windows[key]

            # New window
            if stored_window != window_id:
                count = 0
                stored_window = window_id

            if count + tokens <= self.limit:
                self._windows[key] = (count + tokens, stored_window)
                return True

            return False

    def get_info(self, key: str = "default") -> RateLimitInfo:
        window_id = self._get_window_id()

        with self._lock:
            if key not in self._windows:
                return RateLimitInfo(
                    limit=self.limit,
                    remaining=self.limit,
                    reset_at=datetime.fromtimestamp((window_id + 1) * self.window_seconds),
                )

            count, stored_window = self._windows[key]

            if stored_window != window_id:
                count = 0

            remaining = max(0, self.limit - count)
            reset_at = datetime.fromtimestamp((window_id + 1) * self.window_seconds)
            retry_after = None

            if remaining == 0:
                retry_after = (window_id + 1) * self.window_seconds - time.time()

            return RateLimitInfo(
                limit=self.limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
            )

    def reset(self, key: str = "default"):
        with self._lock:
            if key in self._windows:
                del self._windows[key]


class AdaptiveRateLimiter(RateLimiter):
    """
    Adaptive rate limiter that adjusts limits based on system load.
    """

    def __init__(
        self,
        base_limit: int = 100,
        window_seconds: int = 60,
        min_limit: int = 10,
        max_limit: int = 1000,
        load_threshold: float = 0.8,
    ):
        self.base_limit = base_limit
        self.window_seconds = window_seconds
        self.min_limit = min_limit
        self.max_limit = max_limit
        self.load_threshold = load_threshold

        self._current_limit = base_limit
        self._sliding_window = SlidingWindow(base_limit, window_seconds)
        self._load: float = 0.0
        self._lock = threading.Lock()

    def set_load(self, load: float):
        """Update system load (0.0 to 1.0)."""
        with self._lock:
            self._load = max(0.0, min(1.0, load))
            self._adjust_limit()

    def _adjust_limit(self):
        """Adjust limit based on load."""
        if self._load >= self.load_threshold:
            # Reduce limit under high load
            reduction = (self._load - self.load_threshold) / (1 - self.load_threshold)
            self._current_limit = int(self.base_limit * (1 - reduction * 0.5))  # Reduce up to 50%
        else:
            # Increase limit under low load
            increase = 1 - (self._load / self.load_threshold)
            self._current_limit = int(self.base_limit * (1 + increase * 0.5))  # Increase up to 50%

        self._current_limit = max(self.min_limit, min(self.max_limit, self._current_limit))
        self._sliding_window.limit = self._current_limit

    def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        return self._sliding_window.acquire(key, tokens)

    def get_info(self, key: str = "default") -> RateLimitInfo:
        return self._sliding_window.get_info(key)

    def reset(self, key: str = "default"):
        self._sliding_window.reset(key)


class DistributedRateLimiter(RateLimiter):
    """
    Distributed rate limiter using Redis.
    """

    def __init__(
        self,
        redis_client: Any,
        limit: int = 100,
        window_seconds: int = 60,
        key_prefix: str = "ratelimit",
    ):
        self.redis = redis_client
        self.limit = limit
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

    def _make_key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def acquire(self, key: str = "default", tokens: int = 1) -> bool:
        redis_key = self._make_key(key)
        now = time.time()
        window_start = now - self.window_seconds

        try:
            pipe = self.redis.pipeline()

            # Remove expired entries
            pipe.zremrangebyscore(redis_key, 0, window_start)

            # Count current entries
            pipe.zcard(redis_key)

            # Add new entry if allowed
            results = pipe.execute()
            current_count = results[1]

            if current_count + tokens <= self.limit:
                # Add entries
                pipe = self.redis.pipeline()
                for i in range(tokens):
                    pipe.zadd(redis_key, {f"{now}:{i}": now})
                pipe.expire(redis_key, self.window_seconds)
                pipe.execute()
                return True

            return False

        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            return True  # Fail open

    def get_info(self, key: str = "default") -> RateLimitInfo:
        redis_key = self._make_key(key)
        now = time.time()
        window_start = now - self.window_seconds

        try:
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            pipe.zrange(redis_key, 0, 0, withscores=True)
            results = pipe.execute()

            count = results[1]
            remaining = max(0, self.limit - count)

            # Get oldest entry for reset time
            oldest_entries = results[2]
            if oldest_entries:
                oldest = oldest_entries[0][1]
                reset_at = datetime.fromtimestamp(oldest + self.window_seconds)
                retry_after = oldest + self.window_seconds - now if remaining == 0 else None
            else:
                reset_at = datetime.fromtimestamp(now + self.window_seconds)
                retry_after = None

            return RateLimitInfo(
                limit=self.limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
            )

        except Exception as e:
            logger.error(f"Redis rate limit info error: {e}")
            return RateLimitInfo(
                limit=self.limit,
                remaining=self.limit,
                reset_at=datetime.now(timezone.utc),
            )

    def reset(self, key: str = "default"):
        try:
            self.redis.delete(self._make_key(key))
        except Exception as e:
            logger.error(f"Redis rate limit reset error: {e}")


def rate_limit(rate: float = 10.0, burst: int = 20, key_func: Optional[Callable[..., str]] = None):
    """Decorator for rate limiting functions."""
    limiter = TokenBucket(rate=rate, capacity=burst)

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs) if key_func else "default"

            if not limiter.acquire(key):
                info = limiter.get_info(key)
                raise RateLimitExceeded(limit=info.limit, window=1, retry_after=info.retry_after or 0)

            return func(*args, **kwargs)

        async def async_wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs) if key_func else "default"

            if not limiter.acquire(key):
                info = limiter.get_info(key)
                raise RateLimitExceeded(limit=info.limit, window=1, retry_after=info.retry_after or 0)

            return await func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator
