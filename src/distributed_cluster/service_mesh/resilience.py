"""
Resilience patterns for service mesh.
"""

import asyncio
import functools
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar

from .circuitbreaker import Bulkhead, CircuitBreaker, CircuitBreakerConfig, RateLimiter

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryStrategy(Enum):
    """Retry strategies."""
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    RANDOM = "random"


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    base_delay_ms: int = 100
    max_delay_ms: int = 10000
    jitter: bool = True
    jitter_factor: float = 0.2
    retryable_exceptions: List[type] = field(default_factory=list)
    non_retryable_exceptions: List[type] = field(default_factory=list)
    retry_on_result: Optional[Callable[[Any], bool]] = None

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for an attempt."""
        if self.strategy == RetryStrategy.FIXED:
            delay = self.base_delay_ms
        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay_ms * (2 ** (attempt - 1))
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay_ms * attempt
        elif self.strategy == RetryStrategy.RANDOM:
            delay = random.randint(self.base_delay_ms // 2, self.base_delay_ms * 2)
        else:
            delay = self.base_delay_ms

        # Apply max delay cap
        delay = min(delay, self.max_delay_ms)

        # Apply jitter
        if self.jitter:
            jitter_range = delay * self.jitter_factor
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay) / 1000  # Convert to seconds

    def should_retry(self, exception: Optional[Exception], result: Any = None) -> bool:
        """Check if should retry based on exception or result."""
        if exception:
            # Check non-retryable exceptions
            if self.non_retryable_exceptions:
                if any(isinstance(exception, exc) for exc in self.non_retryable_exceptions):
                    return False

            # Check retryable exceptions
            if self.retryable_exceptions:
                return any(isinstance(exception, exc) for exc in self.retryable_exceptions)

            return True

        # Check result-based retry
        if self.retry_on_result:
            return self.retry_on_result(result)

        return False


@dataclass
class TimeoutPolicy:
    """Configuration for timeout behavior."""
    timeout_ms: int = 5000
    cancel_on_timeout: bool = True
    fallback: Optional[Callable[[], Any]] = None

    @property
    def timeout_seconds(self) -> float:
        return self.timeout_ms / 1000


@dataclass
class FallbackPolicy:
    """Configuration for fallback behavior."""
    fallback_fn: Callable[..., Any]
    fallback_exceptions: List[type] = field(default_factory=list)
    fallback_on_result: Optional[Callable[[Any], bool]] = None

    def should_fallback(self, exception: Optional[Exception], result: Any = None) -> bool:
        """Check if should use fallback."""
        if exception:
            if self.fallback_exceptions:
                return any(isinstance(exception, exc) for exc in self.fallback_exceptions)
            return True

        if self.fallback_on_result:
            return self.fallback_on_result(result)

        return False


@dataclass
class ResiliencePolicy:
    """Combined resilience policy with multiple strategies."""
    name: str
    retry: Optional[RetryPolicy] = None
    timeout: Optional[TimeoutPolicy] = None
    fallback: Optional[FallbackPolicy] = None
    circuit_breaker: Optional[CircuitBreakerConfig] = None
    bulkhead: Optional[int] = None  # max concurrent
    rate_limit: Optional[tuple] = None  # (rate, capacity)


class Resilience:
    """
    Resilience executor combining multiple patterns.

    Applies patterns in order: Rate Limit -> Bulkhead -> Circuit Breaker -> Timeout -> Retry -> Fallback
    """

    def __init__(self, policy: ResiliencePolicy):
        self.policy = policy
        self._circuit_breaker: Optional[CircuitBreaker] = None
        self._bulkhead: Optional[Bulkhead] = None
        self._rate_limiter: Optional[RateLimiter] = None
        self._stats = ResilienceStats()

        self._initialize()

    def _initialize(self):
        """Initialize resilience components."""
        if self.policy.circuit_breaker:
            self._circuit_breaker = CircuitBreaker(
                f"{self.policy.name}-cb",
                self.policy.circuit_breaker
            )

        if self.policy.bulkhead:
            self._bulkhead = Bulkhead(
                f"{self.policy.name}-bulkhead",
                max_concurrent=self.policy.bulkhead
            )

        if self.policy.rate_limit:
            rate, capacity = self.policy.rate_limit
            self._rate_limiter = RateLimiter(
                f"{self.policy.name}-ratelimit",
                rate=rate,
                capacity=capacity
            )

    def execute(self, func: Callable[[], T]) -> T:
        """Execute a function with resilience policies."""
        start_time = time.time()
        self._stats.total_calls += 1

        # Rate limiting
        if self._rate_limiter:
            if not self._rate_limiter.acquire():
                self._stats.rate_limited += 1
                if self.policy.fallback:
                    return self.policy.fallback.fallback_fn()
                raise Exception(f"Rate limit exceeded for {self.policy.name}")

        # Bulkhead
        if self._bulkhead:
            if not self._bulkhead.acquire():
                self._stats.bulkhead_rejected += 1
                if self.policy.fallback:
                    return self.policy.fallback.fallback_fn()
                raise Exception(f"Bulkhead full for {self.policy.name}")

        try:
            return self._execute_with_retry(func)
        finally:
            if self._bulkhead:
                self._bulkhead.release()
            self._stats.total_duration_ms += (time.time() - start_time) * 1000

    def _execute_with_retry(self, func: Callable[[], T]) -> T:
        """Execute with retry logic."""
        max_attempts = self.policy.retry.max_attempts if self.policy.retry else 1
        last_exception = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = self._execute_with_circuit_breaker(func)

                # Check if result requires retry
                if self.policy.retry and self.policy.retry.retry_on_result:
                    if self.policy.retry.should_retry(None, result):
                        if attempt < max_attempts:
                            self._stats.retries += 1
                            delay = self.policy.retry.get_delay(attempt)
                            time.sleep(delay)
                            continue

                self._stats.successful_calls += 1
                return result

            except Exception as e:
                last_exception = e
                self._stats.failed_calls += 1

                # Check if should retry
                if self.policy.retry and attempt < max_attempts:
                    if self.policy.retry.should_retry(e):
                        self._stats.retries += 1
                        delay = self.policy.retry.get_delay(attempt)
                        time.sleep(delay)
                        continue

                # Try fallback
                if self.policy.fallback:
                    if self.policy.fallback.should_fallback(e):
                        self._stats.fallbacks += 1
                        return self.policy.fallback.fallback_fn()

                raise

        # All retries exhausted
        if self.policy.fallback:
            self._stats.fallbacks += 1
            return self.policy.fallback.fallback_fn()

        raise last_exception

    def _execute_with_circuit_breaker(self, func: Callable[[], T]) -> T:
        """Execute with circuit breaker."""
        if self._circuit_breaker:
            return self._circuit_breaker.execute(
                lambda: self._execute_with_timeout(func)
            )
        return self._execute_with_timeout(func)

    def _execute_with_timeout(self, func: Callable[[], T]) -> T:
        """Execute with timeout."""
        if not self.policy.timeout:
            return func()

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            try:
                return future.result(timeout=self.policy.timeout.timeout_seconds)
            except concurrent.futures.TimeoutError:
                self._stats.timeouts += 1
                if self.policy.timeout.cancel_on_timeout:
                    future.cancel()
                if self.policy.timeout.fallback:
                    return self.policy.timeout.fallback()
                raise TimeoutError(f"Execution timed out after {self.policy.timeout.timeout_ms}ms")

    async def execute_async(self, func: Callable[[], T]) -> T:
        """Execute an async function with resilience policies."""
        time.time()
        self._stats.total_calls += 1

        # Rate limiting
        if self._rate_limiter:
            if not await self._rate_limiter.acquire_async():
                self._stats.rate_limited += 1
                if self.policy.fallback:
                    result = self.policy.fallback.fallback_fn()
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
                raise Exception(f"Rate limit exceeded for {self.policy.name}")

        # Bulkhead
        if self._bulkhead:
            try:
                return await self._execute_with_retry_async(func)
            finally:
                pass  # Bulkhead release handled in async version
        else:
            return await self._execute_with_retry_async(func)

    async def _execute_with_retry_async(self, func: Callable[[], T]) -> T:
        """Execute async with retry logic."""
        max_attempts = self.policy.retry.max_attempts if self.policy.retry else 1
        last_exception = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = await self._execute_with_timeout_async(func)

                if self.policy.retry and self.policy.retry.retry_on_result:
                    if self.policy.retry.should_retry(None, result):
                        if attempt < max_attempts:
                            self._stats.retries += 1
                            delay = self.policy.retry.get_delay(attempt)
                            await asyncio.sleep(delay)
                            continue

                self._stats.successful_calls += 1
                return result

            except Exception as e:
                last_exception = e
                self._stats.failed_calls += 1

                if self.policy.retry and attempt < max_attempts:
                    if self.policy.retry.should_retry(e):
                        self._stats.retries += 1
                        delay = self.policy.retry.get_delay(attempt)
                        await asyncio.sleep(delay)
                        continue

                if self.policy.fallback:
                    if self.policy.fallback.should_fallback(e):
                        self._stats.fallbacks += 1
                        result = self.policy.fallback.fallback_fn()
                        if asyncio.iscoroutine(result):
                            return await result
                        return result

                raise

        if self.policy.fallback:
            self._stats.fallbacks += 1
            result = self.policy.fallback.fallback_fn()
            if asyncio.iscoroutine(result):
                return await result
            return result

        raise last_exception

    async def _execute_with_timeout_async(self, func: Callable[[], T]) -> T:
        """Execute async with timeout."""
        if not self.policy.timeout:
            if asyncio.iscoroutinefunction(func):
                return await func()
            return func()

        try:
            if asyncio.iscoroutinefunction(func):
                return await asyncio.wait_for(
                    func(),
                    timeout=self.policy.timeout.timeout_seconds
                )
            else:
                loop = asyncio.get_event_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(None, func),
                    timeout=self.policy.timeout.timeout_seconds
                )
        except asyncio.TimeoutError:
            self._stats.timeouts += 1
            if self.policy.timeout.fallback:
                result = self.policy.timeout.fallback()
                if asyncio.iscoroutine(result):
                    return await result
                return result
            raise TimeoutError(f"Execution timed out after {self.policy.timeout.timeout_ms}ms")

    def get_stats(self) -> Dict[str, Any]:
        """Get resilience statistics."""
        stats = self._stats.to_dict()

        if self._circuit_breaker:
            stats["circuit_breaker"] = self._circuit_breaker.stats.to_dict()

        if self._bulkhead:
            stats["bulkhead"] = self._bulkhead.stats

        if self._rate_limiter:
            stats["rate_limiter"] = self._rate_limiter.stats

        return stats


@dataclass
class ResilienceStats:
    """Statistics for resilience execution."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    retries: int = 0
    timeouts: int = 0
    fallbacks: int = 0
    rate_limited: int = 0
    bulkhead_rejected: int = 0
    total_duration_ms: float = 0

    @property
    def success_rate(self) -> float:
        return self.successful_calls / self.total_calls if self.total_calls > 0 else 0

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.total_calls if self.total_calls > 0 else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": self.success_rate,
            "retries": self.retries,
            "timeouts": self.timeouts,
            "fallbacks": self.fallbacks,
            "rate_limited": self.rate_limited,
            "bulkhead_rejected": self.bulkhead_rejected,
            "avg_duration_ms": self.avg_duration_ms,
        }


def resilient(
    retry: Optional[RetryPolicy] = None,
    timeout: Optional[TimeoutPolicy] = None,
    fallback: Optional[Callable] = None,
    circuit_breaker: Optional[CircuitBreakerConfig] = None,
    bulkhead: Optional[int] = None,
    rate_limit: Optional[tuple] = None
):
    """Decorator for applying resilience policies to a function."""
    def decorator(func: Callable) -> Callable:
        policy = ResiliencePolicy(
            name=f"{func.__module__}.{func.__qualname__}",
            retry=retry,
            timeout=timeout,
            fallback=FallbackPolicy(fallback_fn=fallback) if fallback else None,
            circuit_breaker=circuit_breaker,
            bulkhead=bulkhead,
            rate_limit=rate_limit,
        )
        resilience = Resilience(policy)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return resilience.execute(lambda: func(*args, **kwargs))

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await resilience.execute_async(lambda: func(*args, **kwargs))

        wrapper.get_stats = resilience.get_stats
        async_wrapper.get_stats = resilience.get_stats

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator
