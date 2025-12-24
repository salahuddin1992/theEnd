"""
Rate Limiting Algorithms for NebulaCompute.

Implements various rate limiting algorithms:
- Token Bucket
- Sliding Window
- Fixed Window
- Leaky Bucket
"""

import asyncio
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class RateLimitAlgorithm(ABC):
    """Abstract base class for rate limiting algorithms."""

    @abstractmethod
    def consume(self, tokens: float = 1.0) -> bool:
        """
        Try to consume tokens.

        Returns True if allowed, False if rate limited.
        """
        pass

    @abstractmethod
    def get_wait_time(self, tokens: float = 1.0) -> float:
        """
        Get time to wait before tokens are available.

        Returns 0 if tokens are available now.
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset the rate limiter state."""
        pass


class TokenBucket(RateLimitAlgorithm):
    """
    Token Bucket rate limiting algorithm.

    Allows bursts up to bucket capacity, then limits to refill rate.

    Properties:
    - Smooth rate limiting
    - Allows controlled bursts
    - Memory efficient
    """

    def __init__(
        self,
        capacity: float,
        refill_rate: float,
        initial_tokens: Optional[float] = None,
    ):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum tokens in bucket
            refill_rate: Tokens added per second
            initial_tokens: Starting tokens (default: capacity)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_update = time.time()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update
        self.last_update = now

        # Add tokens based on elapsed time
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate,
        )

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume tokens from the bucket."""
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    def get_wait_time(self, tokens: float = 1.0) -> float:
        """Get time to wait for tokens to be available."""
        self._refill()

        if self.tokens >= tokens:
            return 0.0

        needed = tokens - self.tokens
        return needed / self.refill_rate

    def reset(self) -> None:
        """Reset bucket to full capacity."""
        self.tokens = self.capacity
        self.last_update = time.time()

    @property
    def available(self) -> float:
        """Get currently available tokens."""
        self._refill()
        return self.tokens

    @property
    def utilization(self) -> float:
        """Get bucket utilization (1 - available/capacity)."""
        self._refill()
        return 1 - (self.tokens / self.capacity)


class SlidingWindow(RateLimitAlgorithm):
    """
    Sliding Window rate limiting algorithm.

    Tracks requests in a sliding time window.

    Properties:
    - Accurate rate limiting
    - Prevents burst at window boundaries
    - Higher memory usage
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        precision: int = 10,
    ):
        """
        Initialize sliding window.

        Args:
            limit: Maximum requests in window
            window_seconds: Window duration in seconds
            precision: Number of sub-windows for accuracy
        """
        self.limit = limit
        self.window_seconds = window_seconds
        self.precision = precision
        self.sub_window_seconds = window_seconds / precision

        # Circular buffer of sub-window counts
        self._counts: List[int] = [0] * precision
        self._current_idx = 0
        self._last_update = time.time()
        self._total_count = 0

    def _slide_window(self) -> None:
        """Slide the window based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_update

        # Calculate how many sub-windows to advance
        windows_to_advance = int(elapsed / self.sub_window_seconds)

        if windows_to_advance > 0:
            # Clear old sub-windows
            for i in range(min(windows_to_advance, self.precision)):
                idx = (self._current_idx + 1 + i) % self.precision
                self._total_count -= self._counts[idx]
                self._counts[idx] = 0

            # Advance current index
            self._current_idx = (
                self._current_idx + windows_to_advance
            ) % self.precision

            self._last_update = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to record a request."""
        self._slide_window()

        count = int(tokens)

        if self._total_count + count > self.limit:
            return False

        self._counts[self._current_idx] += count
        self._total_count += count
        return True

    def get_wait_time(self, tokens: float = 1.0) -> float:
        """Get time until request would be allowed."""
        self._slide_window()

        if self._total_count < self.limit:
            return 0.0

        # Wait for oldest sub-window to expire
        return self.sub_window_seconds

    def reset(self) -> None:
        """Reset the window."""
        self._counts = [0] * self.precision
        self._current_idx = 0
        self._last_update = time.time()
        self._total_count = 0

    @property
    def current_count(self) -> int:
        """Get current request count in window."""
        self._slide_window()
        return self._total_count

    @property
    def remaining(self) -> int:
        """Get remaining requests in window."""
        self._slide_window()
        return max(0, self.limit - self._total_count)


class FixedWindow(RateLimitAlgorithm):
    """
    Fixed Window rate limiting algorithm.

    Resets counter at fixed intervals.

    Properties:
    - Simple and efficient
    - Potential burst at window boundaries
    - Low memory usage
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
    ):
        """
        Initialize fixed window.

        Args:
            limit: Maximum requests per window
            window_seconds: Window duration in seconds
        """
        self.limit = limit
        self.window_seconds = window_seconds
        self._count = 0
        self._window_start = time.time()

    def _check_window(self) -> None:
        """Check if window should reset."""
        now = time.time()

        if now - self._window_start >= self.window_seconds:
            self._count = 0
            self._window_start = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to record a request."""
        self._check_window()

        count = int(tokens)

        if self._count + count > self.limit:
            return False

        self._count += count
        return True

    def get_wait_time(self, tokens: float = 1.0) -> float:
        """Get time until next window."""
        self._check_window()

        if self._count < self.limit:
            return 0.0

        elapsed = time.time() - self._window_start
        return self.window_seconds - elapsed

    def reset(self) -> None:
        """Reset the window."""
        self._count = 0
        self._window_start = time.time()

    @property
    def remaining(self) -> int:
        """Get remaining requests in window."""
        self._check_window()
        return max(0, self.limit - self._count)

    @property
    def window_reset_at(self) -> float:
        """Get timestamp when window resets."""
        return self._window_start + self.window_seconds


class LeakyBucket(RateLimitAlgorithm):
    """
    Leaky Bucket rate limiting algorithm.

    Processes requests at a constant rate, queuing excess.

    Properties:
    - Smooth output rate
    - Queues burst requests
    - Good for rate smoothing
    """

    def __init__(
        self,
        capacity: int,
        leak_rate: float,
    ):
        """
        Initialize leaky bucket.

        Args:
            capacity: Maximum queue size
            leak_rate: Requests processed per second
        """
        self.capacity = capacity
        self.leak_rate = leak_rate
        self._queue: Deque[float] = deque()  # Timestamps
        self._last_leak = time.time()

    def _leak(self) -> None:
        """Process (leak) requests from the bucket."""
        now = time.time()
        elapsed = now - self._last_leak

        # Calculate how many requests to leak
        to_leak = int(elapsed * self.leak_rate)

        if to_leak > 0:
            # Remove leaked requests
            for _ in range(min(to_leak, len(self._queue))):
                self._queue.popleft()

            self._last_leak = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to add request to the bucket."""
        self._leak()

        count = int(tokens)

        if len(self._queue) + count > self.capacity:
            return False

        # Add requests to queue
        now = time.time()
        for _ in range(count):
            self._queue.append(now)

        return True

    def get_wait_time(self, tokens: float = 1.0) -> float:
        """Get time until queue has space."""
        self._leak()

        if len(self._queue) < self.capacity:
            return 0.0

        # Wait for one leak
        return 1.0 / self.leak_rate

    def reset(self) -> None:
        """Clear the bucket."""
        self._queue.clear()
        self._last_leak = time.time()

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        self._leak()
        return len(self._queue)

    @property
    def available_capacity(self) -> int:
        """Get available queue capacity."""
        self._leak()
        return self.capacity - len(self._queue)


class AdaptiveTokenBucket(TokenBucket):
    """
    Adaptive Token Bucket that adjusts rate based on latency.

    Automatically reduces rate when latency increases.
    """

    def __init__(
        self,
        capacity: float,
        refill_rate: float,
        target_latency_ms: float = 100.0,
        min_rate: float = 1.0,
        max_rate: Optional[float] = None,
        adjustment_interval: float = 10.0,
    ):
        super().__init__(capacity, refill_rate)

        self.target_latency_ms = target_latency_ms
        self.min_rate = min_rate
        self.max_rate = max_rate or refill_rate * 2
        self.adjustment_interval = adjustment_interval
        self.original_rate = refill_rate

        self._latencies: Deque[float] = deque(maxlen=100)
        self._last_adjustment = time.time()

    def record_latency(self, latency_ms: float) -> None:
        """Record a request latency for adaptive adjustment."""
        self._latencies.append(latency_ms)
        self._maybe_adjust()

    def _maybe_adjust(self) -> None:
        """Adjust rate if needed."""
        now = time.time()

        if now - self._last_adjustment < self.adjustment_interval:
            return

        if len(self._latencies) < 10:
            return

        self._last_adjustment = now

        # Calculate average latency
        avg_latency = sum(self._latencies) / len(self._latencies)

        # Adjust rate
        if avg_latency > self.target_latency_ms * 1.5:
            # High latency - reduce rate
            new_rate = self.refill_rate * 0.8
            self.refill_rate = max(self.min_rate, new_rate)
            logger.info(
                "Reduced rate to %.2f/s due to high latency (%.2fms)",
                self.refill_rate,
                avg_latency,
            )

        elif avg_latency < self.target_latency_ms * 0.5:
            # Low latency - increase rate
            new_rate = self.refill_rate * 1.2
            self.refill_rate = min(self.max_rate, new_rate)
            logger.info(
                "Increased rate to %.2f/s due to low latency (%.2fms)",
                self.refill_rate,
                avg_latency,
            )

        self._latencies.clear()

    def get_stats(self) -> Dict:
        """Get adaptive bucket stats."""
        return {
            "current_rate": self.refill_rate,
            "original_rate": self.original_rate,
            "rate_ratio": self.refill_rate / self.original_rate,
            "target_latency_ms": self.target_latency_ms,
            "recent_latencies": len(self._latencies),
        }


class ConcurrencyLimiter:
    """
    Limits concurrent operations (not rate).

    Useful for limiting parallel connections or jobs.
    """

    def __init__(self, max_concurrent: int):
        """
        Initialize concurrency limiter.

        Args:
            max_concurrent: Maximum concurrent operations
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._current = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Acquire a slot. Returns True if acquired."""
        acquired = self._semaphore.locked() is False

        if acquired:
            await self._semaphore.acquire()
            async with self._lock:
                self._current += 1

        return acquired

    async def release(self) -> None:
        """Release a slot."""
        self._semaphore.release()
        async with self._lock:
            self._current -= 1

    async def __aenter__(self):
        """Context manager entry."""
        await self._semaphore.acquire()
        async with self._lock:
            self._current += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self._semaphore.release()
        async with self._lock:
            self._current -= 1

    @property
    def current(self) -> int:
        """Get current concurrent operations."""
        return self._current

    @property
    def available(self) -> int:
        """Get available slots."""
        return self.max_concurrent - self._current
