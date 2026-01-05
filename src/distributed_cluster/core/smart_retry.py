# -*- coding: utf-8 -*-
"""
Smart Retry Manager - مدير إعادة المحاولة الذكي
================================================

Intelligent retry mechanism with:
- Multiple backoff strategies (exponential, linear, fibonacci, adaptive)
- Jitter for avoiding thundering herd
- Retry budgets and rate limiting
- Circuit breaker integration
- Context-aware retry decisions

نظام ذكي لإعادة المحاولة:
- استراتيجيات تأخير متعددة
- تجنب ازدحام الطلبات
- ميزانية إعادة المحاولة
- تكامل مع قاطع الدائرة
- قرارات ذكية حسب السياق
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BackoffStrategy(str, Enum):
    """Backoff strategies for retry delays."""

    CONSTANT = "constant"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIBONACCI = "fibonacci"
    DECORRELATED_JITTER = "decorrelated_jitter"
    ADAPTIVE = "adaptive"


class RetryOutcome(str, Enum):
    """Outcome of a retry attempt."""

    SUCCESS = "success"
    RETRY = "retry"
    FAILURE = "failure"
    CIRCUIT_OPEN = "circuit_open"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass
class RetryContext:
    """Context information for a retry operation."""

    operation_name: str
    attempt: int
    total_attempts: int
    start_time: datetime
    last_delay_seconds: float
    total_delay_seconds: float
    last_exception: Optional[Exception]
    exception_history: List[Tuple[int, str, datetime]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_seconds(self) -> float:
        """Total elapsed time since first attempt."""
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_name": self.operation_name,
            "attempt": self.attempt,
            "total_attempts": self.total_attempts,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "total_delay_seconds": round(self.total_delay_seconds, 2),
            "exception_count": len(self.exception_history),
        }


@dataclass
class RetryStats:
    """Statistics for retry operations."""

    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    total_retries: int = 0
    total_delay_seconds: float = 0.0
    exceptions_by_type: Dict[str, int] = field(default_factory=dict)
    operations_by_outcome: Dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_operations == 0:
            return 0.0
        return self.successful_operations / self.total_operations

    @property
    def avg_retries_per_operation(self) -> float:
        if self.total_operations == 0:
            return 0.0
        return self.total_retries / self.total_operations

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_operations": self.total_operations,
            "successful_operations": self.successful_operations,
            "failed_operations": self.failed_operations,
            "success_rate": round(self.success_rate, 4),
            "total_retries": self.total_retries,
            "avg_retries_per_operation": round(self.avg_retries_per_operation, 2),
            "total_delay_seconds": round(self.total_delay_seconds, 2),
            "exceptions_by_type": self.exceptions_by_type,
            "operations_by_outcome": self.operations_by_outcome,
        }


class BackoffCalculator(ABC):
    """Base class for backoff delay calculators."""

    @abstractmethod
    def calculate(self, attempt: int, base_delay: float, max_delay: float) -> float:
        """Calculate delay for the given attempt number."""
        pass


class ConstantBackoff(BackoffCalculator):
    """Constant delay between retries."""

    def calculate(self, attempt: int, base_delay: float, max_delay: float) -> float:
        return min(base_delay, max_delay)


class LinearBackoff(BackoffCalculator):
    """Linear increase in delay."""

    def calculate(self, attempt: int, base_delay: float, max_delay: float) -> float:
        return min(base_delay * attempt, max_delay)


class ExponentialBackoff(BackoffCalculator):
    """Exponential increase in delay (2^attempt)."""

    def __init__(self, multiplier: float = 2.0):
        self.multiplier = multiplier

    def calculate(self, attempt: int, base_delay: float, max_delay: float) -> float:
        delay = base_delay * (self.multiplier ** (attempt - 1))
        return min(delay, max_delay)


class FibonacciBackoff(BackoffCalculator):
    """Fibonacci sequence for delay progression."""

    def __init__(self):
        self._cache = {0: 0, 1: 1}

    def _fib(self, n: int) -> int:
        if n in self._cache:
            return self._cache[n]
        self._cache[n] = self._fib(n - 1) + self._fib(n - 2)
        return self._cache[n]

    def calculate(self, attempt: int, base_delay: float, max_delay: float) -> float:
        fib_value = self._fib(attempt + 1)
        delay = base_delay * fib_value
        return min(delay, max_delay)


class DecorrelatedJitterBackoff(BackoffCalculator):
    """AWS-style decorrelated jitter for better distribution."""

    def __init__(self):
        self._last_delay = 0.0

    def calculate(self, attempt: int, base_delay: float, max_delay: float) -> float:
        if attempt == 1:
            self._last_delay = base_delay
        else:
            self._last_delay = random.uniform(base_delay, self._last_delay * 3)
        return min(self._last_delay, max_delay)


class AdaptiveBackoff(BackoffCalculator):
    """
    Adaptive backoff that adjusts based on recent success/failure patterns.

    Increases delay on consecutive failures, decreases on successes.
    """

    def __init__(self):
        self._success_streak = 0
        self._failure_streak = 0

    def calculate(self, attempt: int, base_delay: float, max_delay: float) -> float:
        # Base exponential calculation
        delay = base_delay * (2 ** (attempt - 1))

        # Adjust based on failure streak
        if self._failure_streak > 3:
            delay *= 1.5  # Increase delay after multiple failures

        return min(delay, max_delay)

    def record_success(self) -> None:
        self._success_streak += 1
        self._failure_streak = 0

    def record_failure(self) -> None:
        self._failure_streak += 1
        self._success_streak = 0


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    # Basic retry settings
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0

    # Backoff strategy
    strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    backoff_multiplier: float = 2.0

    # Jitter settings
    jitter_enabled: bool = True
    jitter_factor: float = 0.25  # ±25% jitter

    # Timeout
    per_attempt_timeout_seconds: Optional[float] = None
    total_timeout_seconds: Optional[float] = None

    # Budget settings
    budget_enabled: bool = False
    budget_tokens: int = 100  # Initial tokens
    budget_tokens_per_retry: int = 10  # Tokens consumed per retry
    budget_refill_rate: float = 1.0  # Tokens per second

    # Exception handling
    retryable_exceptions: Optional[Set[Type[Exception]]] = None
    non_retryable_exceptions: Optional[Set[Type[Exception]]] = None

    # Callbacks
    on_retry: Optional[Callable[[RetryContext], None]] = None
    on_success: Optional[Callable[[RetryContext], None]] = None
    on_failure: Optional[Callable[[RetryContext], None]] = None

    def should_retry_exception(self, exc: Exception) -> bool:
        """Determine if an exception should trigger a retry."""
        exc_type = type(exc)

        # Check non-retryable first
        if self.non_retryable_exceptions:
            if exc_type in self.non_retryable_exceptions:
                return False
            for non_retry_type in self.non_retryable_exceptions:
                if isinstance(exc, non_retry_type):
                    return False

        # Check retryable (if specified)
        if self.retryable_exceptions:
            for retry_type in self.retryable_exceptions:
                if isinstance(exc, retry_type):
                    return True
            return False

        # Default: retry on any exception
        return True


class RetryBudget:
    """
    Token bucket rate limiter for retry attempts.

    Prevents retry storms by limiting the rate of retries.
    """

    def __init__(
        self,
        initial_tokens: int = 100,
        tokens_per_retry: int = 10,
        refill_rate: float = 1.0,
    ):
        self.max_tokens = initial_tokens
        self.tokens_per_retry = tokens_per_retry
        self.refill_rate = refill_rate

        self._tokens = float(initial_tokens)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Try to acquire tokens for a retry. Returns True if allowed."""
        async with self._lock:
            self._refill()

            if self._tokens >= self.tokens_per_retry:
                self._tokens -= self.tokens_per_retry
                return True

            return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self.max_tokens,
            self._tokens + elapsed * self.refill_rate
        )
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        """Current available tokens."""
        return self._tokens


class CircuitBreaker:
    """
    Circuit breaker for preventing cascading failures.

    States:
    - CLOSED: Normal operation
    - OPEN: Failing, reject all attempts
    - HALF_OPEN: Testing if service recovered
    """

    class State(str, Enum):
        CLOSED = "closed"
        OPEN = "open"
        HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds

        self._state = self.State.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == self.State.CLOSED

    async def can_execute(self) -> bool:
        """Check if execution is allowed."""
        async with self._lock:
            if self._state == self.State.CLOSED:
                return True

            if self._state == self.State.OPEN:
                # Check if timeout has elapsed
                if self._last_failure_time:
                    elapsed = time.monotonic() - self._last_failure_time
                    if elapsed >= self.timeout_seconds:
                        self._state = self.State.HALF_OPEN
                        self._success_count = 0
                        logger.info("Circuit breaker entering HALF_OPEN state")
                        return True
                return False

            # HALF_OPEN - allow execution
            return True

    async def record_success(self) -> None:
        """Record a successful execution."""
        async with self._lock:
            if self._state == self.State.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = self.State.CLOSED
                    self._failure_count = 0
                    logger.info("Circuit breaker CLOSED after recovery")
            elif self._state == self.State.CLOSED:
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed execution."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == self.State.HALF_OPEN:
                self._state = self.State.OPEN
                logger.warning("Circuit breaker OPEN (failed in half-open)")
            elif self._state == self.State.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = self.State.OPEN
                    logger.warning(f"Circuit breaker OPEN after {self._failure_count} failures")

    def reset(self) -> None:
        """Reset the circuit breaker."""
        self._state = self.State.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None


class SmartRetryManager:
    """
    Intelligent retry manager with multiple strategies and safeguards.

    Features:
    - Multiple backoff strategies
    - Jitter for avoiding thundering herd
    - Retry budget to prevent retry storms
    - Circuit breaker integration
    - Comprehensive statistics

    Usage:
        retry_manager = SmartRetryManager()

        # Configure
        config = RetryConfig(
            max_attempts=5,
            strategy=BackoffStrategy.EXPONENTIAL,
            base_delay_seconds=1.0,
        )

        # Execute with retries
        result = await retry_manager.execute(
            operation=my_async_function,
            config=config,
            operation_name="my_operation",
        )

        # Or use as decorator
        @retry_manager.retry(max_attempts=3)
        async def my_function():
            ...
    """

    def __init__(
        self,
        default_config: Optional[RetryConfig] = None,
        enable_circuit_breaker: bool = True,
        circuit_breaker_config: Optional[Dict[str, Any]] = None,
    ):
        self.default_config = default_config or RetryConfig()
        self.enable_circuit_breaker = enable_circuit_breaker

        # Circuit breaker per operation
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._circuit_breaker_config = circuit_breaker_config or {}

        # Retry budget
        self._budget: Optional[RetryBudget] = None

        # Backoff calculators
        self._backoff_calculators: Dict[BackoffStrategy, BackoffCalculator] = {
            BackoffStrategy.CONSTANT: ConstantBackoff(),
            BackoffStrategy.LINEAR: LinearBackoff(),
            BackoffStrategy.EXPONENTIAL: ExponentialBackoff(),
            BackoffStrategy.FIBONACCI: FibonacciBackoff(),
            BackoffStrategy.DECORRELATED_JITTER: DecorrelatedJitterBackoff(),
            BackoffStrategy.ADAPTIVE: AdaptiveBackoff(),
        }

        # Statistics
        self._stats = RetryStats()
        self._stats_by_operation: Dict[str, RetryStats] = {}

    def _get_circuit_breaker(self, operation_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for an operation."""
        if operation_name not in self._circuit_breakers:
            self._circuit_breakers[operation_name] = CircuitBreaker(
                **self._circuit_breaker_config
            )
        return self._circuit_breakers[operation_name]

    def _get_operation_stats(self, operation_name: str) -> RetryStats:
        """Get or create stats for an operation."""
        if operation_name not in self._stats_by_operation:
            self._stats_by_operation[operation_name] = RetryStats()
        return self._stats_by_operation[operation_name]

    def _calculate_delay(
        self,
        attempt: int,
        config: RetryConfig,
    ) -> float:
        """Calculate delay for the given attempt."""
        calculator = self._backoff_calculators.get(
            config.strategy,
            self._backoff_calculators[BackoffStrategy.EXPONENTIAL]
        )

        delay = calculator.calculate(
            attempt=attempt,
            base_delay=config.base_delay_seconds,
            max_delay=config.max_delay_seconds,
        )

        # Apply jitter
        if config.jitter_enabled:
            jitter_range = delay * config.jitter_factor
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

    async def execute(
        self,
        operation: Callable[[], Awaitable[T]],
        config: Optional[RetryConfig] = None,
        operation_name: Optional[str] = None,
    ) -> T:
        """
        Execute an operation with retry logic.

        Args:
            operation: Async function to execute
            config: Retry configuration (uses default if not provided)
            operation_name: Name for circuit breaker and stats

        Returns:
            Result of the operation

        Raises:
            Exception: The last exception if all retries failed
        """
        cfg = config or self.default_config
        op_name = operation_name or operation.__name__

        # Initialize context
        context = RetryContext(
            operation_name=op_name,
            attempt=0,
            total_attempts=cfg.max_attempts,
            start_time=datetime.now(timezone.utc),
            last_delay_seconds=0.0,
            total_delay_seconds=0.0,
            last_exception=None,
        )

        # Check circuit breaker
        if self.enable_circuit_breaker:
            cb = self._get_circuit_breaker(op_name)
            if not await cb.can_execute():
                self._record_outcome(op_name, RetryOutcome.CIRCUIT_OPEN)
                raise CircuitBreakerOpenError(f"Circuit breaker open for {op_name}")

        # Check budget
        if cfg.budget_enabled and self._budget:
            if not await self._budget.acquire():
                self._record_outcome(op_name, RetryOutcome.BUDGET_EXHAUSTED)
                raise RetryBudgetExhaustedError("Retry budget exhausted")

        last_exception: Optional[Exception] = None

        for attempt in range(1, cfg.max_attempts + 1):
            context.attempt = attempt

            try:
                # Apply per-attempt timeout if configured
                if cfg.per_attempt_timeout_seconds:
                    result = await asyncio.wait_for(
                        operation(),
                        timeout=cfg.per_attempt_timeout_seconds,
                    )
                else:
                    result = await operation()

                # Success!
                self._record_success(op_name, context)
                if self.enable_circuit_breaker:
                    await self._get_circuit_breaker(op_name).record_success()

                if cfg.on_success:
                    cfg.on_success(context)

                return result

            except asyncio.CancelledError:
                raise  # Don't retry on cancellation

            except Exception as e:
                last_exception = e
                context.last_exception = e
                context.exception_history.append((attempt, type(e).__name__, datetime.now(timezone.utc)))

                # Update exception stats
                exc_type = type(e).__name__
                self._stats.exceptions_by_type[exc_type] = \
                    self._stats.exceptions_by_type.get(exc_type, 0) + 1

                # Check if we should retry this exception
                if not cfg.should_retry_exception(e):
                    logger.debug(f"Exception {exc_type} is not retryable, failing immediately")
                    break

                # Check total timeout
                if cfg.total_timeout_seconds:
                    if context.elapsed_seconds >= cfg.total_timeout_seconds:
                        logger.debug(f"Total timeout exceeded after {context.elapsed_seconds:.1f}s")
                        break

                # Check if more attempts available
                if attempt >= cfg.max_attempts:
                    break

                # Calculate and apply delay
                delay = self._calculate_delay(attempt, cfg)
                context.last_delay_seconds = delay
                context.total_delay_seconds += delay

                # Log and callback
                logger.debug(
                    f"Retry {attempt}/{cfg.max_attempts} for {op_name} "
                    f"after {delay:.2f}s delay: {e}"
                )

                if cfg.on_retry:
                    cfg.on_retry(context)

                # Wait before retry
                await asyncio.sleep(delay)

        # All retries exhausted
        self._record_failure(op_name, context)
        if self.enable_circuit_breaker:
            await self._get_circuit_breaker(op_name).record_failure()

        if cfg.on_failure:
            cfg.on_failure(context)

        if last_exception:
            raise last_exception
        raise RuntimeError(f"Operation {op_name} failed without exception")

    def _record_success(self, operation_name: str, context: RetryContext) -> None:
        """Record successful operation."""
        self._stats.total_operations += 1
        self._stats.successful_operations += 1
        self._stats.total_retries += context.attempt - 1
        self._stats.total_delay_seconds += context.total_delay_seconds
        self._stats.operations_by_outcome[RetryOutcome.SUCCESS.value] = \
            self._stats.operations_by_outcome.get(RetryOutcome.SUCCESS.value, 0) + 1

        op_stats = self._get_operation_stats(operation_name)
        op_stats.total_operations += 1
        op_stats.successful_operations += 1
        op_stats.total_retries += context.attempt - 1

    def _record_failure(self, operation_name: str, context: RetryContext) -> None:
        """Record failed operation."""
        self._stats.total_operations += 1
        self._stats.failed_operations += 1
        self._stats.total_retries += context.attempt - 1
        self._stats.total_delay_seconds += context.total_delay_seconds
        self._stats.operations_by_outcome[RetryOutcome.FAILURE.value] = \
            self._stats.operations_by_outcome.get(RetryOutcome.FAILURE.value, 0) + 1

        op_stats = self._get_operation_stats(operation_name)
        op_stats.total_operations += 1
        op_stats.failed_operations += 1
        op_stats.total_retries += context.attempt - 1

    def _record_outcome(self, operation_name: str, outcome: RetryOutcome) -> None:
        """Record a non-execution outcome."""
        self._stats.operations_by_outcome[outcome.value] = \
            self._stats.operations_by_outcome.get(outcome.value, 0) + 1

    def retry(
        self,
        max_attempts: Optional[int] = None,
        base_delay_seconds: Optional[float] = None,
        strategy: Optional[BackoffStrategy] = None,
        retryable_exceptions: Optional[Set[Type[Exception]]] = None,
        operation_name: Optional[str] = None,
    ) -> Callable:
        """
        Decorator for adding retry logic to async functions.

        Usage:
            @retry_manager.retry(max_attempts=5)
            async def my_function():
                ...
        """
        def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs) -> T:
                config = RetryConfig(
                    max_attempts=max_attempts or self.default_config.max_attempts,
                    base_delay_seconds=base_delay_seconds or self.default_config.base_delay_seconds,
                    strategy=strategy or self.default_config.strategy,
                    retryable_exceptions=retryable_exceptions or self.default_config.retryable_exceptions,
                )

                async def operation():
                    return await func(*args, **kwargs)

                return await self.execute(
                    operation=operation,
                    config=config,
                    operation_name=operation_name or func.__name__,
                )

            return wrapper
        return decorator

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive retry statistics."""
        return {
            "global": self._stats.to_dict(),
            "by_operation": {
                name: stats.to_dict()
                for name, stats in self._stats_by_operation.items()
            },
            "circuit_breakers": {
                name: {
                    "state": cb.state.value,
                    "failure_count": cb._failure_count,
                }
                for name, cb in self._circuit_breakers.items()
            },
        }

    def reset_stats(self) -> None:
        """Reset all statistics."""
        self._stats = RetryStats()
        self._stats_by_operation.clear()

    def reset_circuit_breaker(self, operation_name: str) -> None:
        """Reset circuit breaker for a specific operation."""
        if operation_name in self._circuit_breakers:
            self._circuit_breakers[operation_name].reset()

    def reset_all_circuit_breakers(self) -> None:
        """Reset all circuit breakers."""
        for cb in self._circuit_breakers.values():
            cb.reset()


# =============================================================================
# Custom Exceptions
# =============================================================================


class RetryError(Exception):
    """Base exception for retry errors."""
    pass


class CircuitBreakerOpenError(RetryError):
    """Raised when circuit breaker is open."""
    pass


class RetryBudgetExhaustedError(RetryError):
    """Raised when retry budget is exhausted."""
    pass


# =============================================================================
# Factory Functions
# =============================================================================


def create_retry_manager(
    max_attempts: int = 3,
    strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
    base_delay_seconds: float = 1.0,
    enable_circuit_breaker: bool = True,
) -> SmartRetryManager:
    """
    Create a configured SmartRetryManager.

    Args:
        max_attempts: Default maximum retry attempts
        strategy: Default backoff strategy
        base_delay_seconds: Default base delay
        enable_circuit_breaker: Whether to enable circuit breaker

    Returns:
        Configured SmartRetryManager instance
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        strategy=strategy,
        base_delay_seconds=base_delay_seconds,
    )

    return SmartRetryManager(
        default_config=config,
        enable_circuit_breaker=enable_circuit_breaker,
    )


def with_retry(
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
    retryable_exceptions: Optional[Set[Type[Exception]]] = None,
) -> Callable:
    """
    Standalone decorator for adding retry logic.

    Usage:
        @with_retry(max_attempts=5)
        async def my_function():
            ...
    """
    manager = SmartRetryManager(
        default_config=RetryConfig(
            max_attempts=max_attempts,
            base_delay_seconds=base_delay_seconds,
            strategy=strategy,
            retryable_exceptions=retryable_exceptions,
        ),
        enable_circuit_breaker=False,  # Disable for standalone decorator
    )

    return manager.retry()
