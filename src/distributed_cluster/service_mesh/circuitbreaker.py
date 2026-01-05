"""
Circuit breaker pattern implementation for service resilience.
"""

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """States of a circuit breaker."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes before closing from half-open
    timeout: float = 30.0  # Seconds before transitioning from open to half-open
    half_open_max_calls: int = 3  # Max calls allowed in half-open state
    window_size: int = 10  # Rolling window size for failure counting
    failure_rate_threshold: float = 0.5  # Failure rate to trigger open
    slow_call_duration_threshold: float = 5.0  # Seconds for a call to be considered slow
    slow_call_rate_threshold: float = 0.5  # Slow call rate to trigger open
    excluded_exceptions: List[type] = field(default_factory=list)
    recorded_exceptions: List[type] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout": self.timeout,
            "half_open_max_calls": self.half_open_max_calls,
            "window_size": self.window_size,
            "failure_rate_threshold": self.failure_rate_threshold,
        }


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker."""

    state: CircuitState = CircuitState.CLOSED
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    slow_calls: int = 0
    state_transitions: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_state_change: Optional[datetime] = None
    current_failure_streak: int = 0
    current_success_streak: int = 0

    @property
    def failure_rate(self) -> float:
        total = self.successful_calls + self.failed_calls
        return self.failed_calls / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "rejected_calls": self.rejected_calls,
            "slow_calls": self.slow_calls,
            "failure_rate": self.failure_rate,
            "state_transitions": self.state_transitions,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, name: str, remaining_time: float):
        self.name = name
        self.remaining_time = remaining_time
        super().__init__(f"Circuit breaker '{name}' is open. Retry in {remaining_time:.2f}s")


class CircuitBreaker:
    """
    Circuit breaker implementation for protecting services.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Requests fail immediately
    - HALF_OPEN: Limited requests allowed to test recovery
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._lock = threading.RLock()

        # Sliding window for failure tracking
        self._window: deque = deque(maxlen=self.config.window_size)

        # Timing
        self._last_failure_time: Optional[float] = None
        self._open_time: Optional[float] = None
        self._half_open_calls = 0
        self._half_open_successes = 0

        # Listeners
        self._state_listeners: List[Callable[[CircuitState, CircuitState], None]] = []

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_state_transition()
            return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        with self._lock:
            self._stats.state = self._state
            return self._stats

    def _check_state_transition(self):
        """Check if state should transition."""
        now = time.time()

        if self._state == CircuitState.OPEN:
            if self._open_time and (now - self._open_time) >= self.config.timeout:
                self._transition_to(CircuitState.HALF_OPEN)

    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._stats.state = new_state
        self._stats.state_transitions += 1
        self._stats.last_state_change = datetime.now(timezone.utc)

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._half_open_successes = 0
        elif new_state == CircuitState.OPEN:
            self._open_time = time.time()
        elif new_state == CircuitState.CLOSED:
            self._window.clear()

        logger.info(f"Circuit breaker '{self.name}' transitioned from {old_state.value} to {new_state.value}")

        # Notify listeners
        for listener in self._state_listeners:
            try:
                listener(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state listener: {e}")

    def _should_open(self) -> bool:
        """Check if circuit should open based on failure rate."""
        if len(self._window) < self.config.window_size:
            # Not enough data yet, use absolute threshold
            failures = sum(1 for result in self._window if not result[0])
            return failures >= self.config.failure_threshold

        # Check failure rate
        failures = sum(1 for result in self._window if not result[0])
        failure_rate = failures / len(self._window)

        if failure_rate >= self.config.failure_rate_threshold:
            return True

        # Check slow call rate
        slow_calls = sum(1 for result in self._window if result[1] >= self.config.slow_call_duration_threshold)
        slow_rate = slow_calls / len(self._window)

        return slow_rate >= self.config.slow_call_rate_threshold

    def can_execute(self) -> bool:
        """Check if a call can be executed."""
        with self._lock:
            self._check_state_transition()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                return False

            if self._state == CircuitState.HALF_OPEN:
                return self._half_open_calls < self.config.half_open_max_calls

        return False

    def record_success(self, duration: float = 0):
        """Record a successful call."""
        with self._lock:
            self._stats.total_calls += 1
            self._stats.successful_calls += 1
            self._stats.last_success_time = datetime.now(timezone.utc)
            self._stats.current_success_streak += 1
            self._stats.current_failure_streak = 0

            if duration >= self.config.slow_call_duration_threshold:
                self._stats.slow_calls += 1

            self._window.append((True, duration))

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def record_failure(self, exception: Optional[Exception] = None, duration: float = 0):
        """Record a failed call."""
        # Check if exception should be excluded
        if exception and self.config.excluded_exceptions:
            if any(isinstance(exception, exc) for exc in self.config.excluded_exceptions):
                self.record_success(duration)
                return

        with self._lock:
            self._stats.total_calls += 1
            self._stats.failed_calls += 1
            self._stats.last_failure_time = datetime.now(timezone.utc)
            self._stats.current_failure_streak += 1
            self._stats.current_success_streak = 0
            self._last_failure_time = time.time()

            if duration >= self.config.slow_call_duration_threshold:
                self._stats.slow_calls += 1

            self._window.append((False, duration))

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._should_open():
                    self._transition_to(CircuitState.OPEN)

    def record_rejection(self):
        """Record a rejected call (when circuit is open)."""
        with self._lock:
            self._stats.rejected_calls += 1

    def execute(self, func: Callable[[], T]) -> T:
        """Execute a function with circuit breaker protection."""
        if not self.can_execute():
            self.record_rejection()
            remaining = self.config.timeout - (time.time() - self._open_time) if self._open_time else 0
            raise CircuitBreakerOpenError(self.name, max(0, remaining))

        if self._state == CircuitState.HALF_OPEN:
            with self._lock:
                self._half_open_calls += 1

        start = time.time()
        try:
            result = func()
            duration = time.time() - start
            self.record_success(duration)
            return result
        except Exception as e:
            duration = time.time() - start
            self.record_failure(e, duration)
            raise

    async def execute_async(self, func: Callable[[], T]) -> T:
        """Execute an async function with circuit breaker protection."""
        if not self.can_execute():
            self.record_rejection()
            remaining = self.config.timeout - (time.time() - self._open_time) if self._open_time else 0
            raise CircuitBreakerOpenError(self.name, max(0, remaining))

        if self._state == CircuitState.HALF_OPEN:
            with self._lock:
                self._half_open_calls += 1

        start = time.time()
        try:
            result = await func()
            duration = time.time() - start
            self.record_success(duration)
            return result
        except Exception as e:
            duration = time.time() - start
            self.record_failure(e, duration)
            raise

    def reset(self):
        """Reset the circuit breaker to closed state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._window.clear()
            self._last_failure_time = None
            self._open_time = None

    def on_state_change(self, listener: Callable[[CircuitState, CircuitState], None]):
        """Register a state change listener."""
        self._state_listeners.append(listener)


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    _instance: Optional["CircuitBreakerRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._breakers: Dict[str, CircuitBreaker] = {}
                    cls._instance._registry_lock = threading.RLock()
        return cls._instance

    def get_or_create(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create a circuit breaker by name."""
        with self._registry_lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        with self._registry_lock:
            return self._breakers.get(name)

    def remove(self, name: str):
        """Remove a circuit breaker."""
        with self._registry_lock:
            self._breakers.pop(name, None)

    def list_all(self) -> List[str]:
        """List all circuit breaker names."""
        with self._registry_lock:
            return list(self._breakers.keys())

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics from all circuit breakers."""
        with self._registry_lock:
            return {name: breaker.stats.to_dict() for name, breaker in self._breakers.items()}

    def reset_all(self):
        """Reset all circuit breakers."""
        with self._registry_lock:
            for breaker in self._breakers.values():
                breaker.reset()


def circuit_breaker(
    name: Optional[str] = None, config: Optional[CircuitBreakerConfig] = None, fallback: Optional[Callable] = None
):
    """Decorator for applying circuit breaker to a function."""

    def decorator(func: Callable) -> Callable:
        cb_name = name or f"{func.__module__}.{func.__qualname__}"
        registry = CircuitBreakerRegistry()
        cb = registry.get_or_create(cb_name, config)

        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return cb.execute(lambda: func(*args, **kwargs))
            except CircuitBreakerOpenError:
                if fallback:
                    return fallback(*args, **kwargs)
                raise

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await cb.execute_async(lambda: func(*args, **kwargs))
            except CircuitBreakerOpenError:
                if fallback:
                    if asyncio.iscoroutinefunction(fallback):
                        return await fallback(*args, **kwargs)
                    return fallback(*args, **kwargs)
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


class Bulkhead:
    """
    Bulkhead pattern for limiting concurrent executions.

    Prevents resource exhaustion by limiting parallelism.
    """

    def __init__(self, name: str, max_concurrent: int = 10, max_wait_ms: int = 0):
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_wait_ms = max_wait_ms
        self._semaphore = threading.Semaphore(max_concurrent)
        self._async_semaphore: Optional[asyncio.Semaphore] = None
        self._current = 0
        self._rejected = 0
        self._lock = threading.Lock()

    @property
    def available(self) -> int:
        with self._lock:
            return self.max_concurrent - self._current

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "max_concurrent": self.max_concurrent,
                "current": self._current,
                "available": self.available,
                "rejected": self._rejected,
            }

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """Acquire a slot."""
        wait_time = timeout if timeout is not None else (self.max_wait_ms / 1000 if self.max_wait_ms > 0 else None)

        acquired = self._semaphore.acquire(blocking=wait_time is not None, timeout=wait_time)

        with self._lock:
            if acquired:
                self._current += 1
            else:
                self._rejected += 1

        return acquired

    def release(self):
        """Release a slot."""
        self._semaphore.release()
        with self._lock:
            self._current = max(0, self._current - 1)

    def execute(self, func: Callable[[], T]) -> T:
        """Execute a function with bulkhead protection."""
        if not self.acquire():
            raise RuntimeError(f"Bulkhead '{self.name}' is full")

        try:
            return func()
        finally:
            self.release()

    async def execute_async(self, func: Callable[[], T]) -> T:
        """Execute an async function with bulkhead protection."""
        if self._async_semaphore is None:
            self._async_semaphore = asyncio.Semaphore(self.max_concurrent)

        async with self._async_semaphore:
            with self._lock:
                self._current += 1
            try:
                return await func()
            finally:
                with self._lock:
                    self._current = max(0, self._current - 1)


class RateLimiter:
    """
    Rate limiter using token bucket algorithm.
    """

    def __init__(self, name: str, rate: float, capacity: int = 10):  # Tokens per second  # Max tokens
        self.name = name
        self.rate = rate
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last_update = time.time()
        self._lock = threading.Lock()
        self._rejected = 0
        self._accepted = 0

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_update
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_update = now

    def acquire(self, tokens: int = 1, wait: bool = False) -> bool:
        """Acquire tokens from the bucket."""
        with self._lock:
            self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                self._accepted += 1
                return True

            if wait:
                # Calculate wait time
                needed = tokens - self._tokens
                wait_time = needed / self.rate

                self._lock.release()
                time.sleep(wait_time)
                self._lock.acquire()

                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    self._accepted += 1
                    return True

            self._rejected += 1
            return False

    async def acquire_async(self, tokens: int = 1, wait: bool = False) -> bool:
        """Async acquire tokens."""
        with self._lock:
            self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                self._accepted += 1
                return True

        if wait:
            needed = tokens - self._tokens
            wait_time = needed / self.rate
            await asyncio.sleep(wait_time)
            return await self.acquire_async(tokens, wait=False)

        with self._lock:
            self._rejected += 1
        return False

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            self._refill()
            return {
                "name": self.name,
                "rate": self.rate,
                "capacity": self.capacity,
                "available_tokens": self._tokens,
                "accepted": self._accepted,
                "rejected": self._rejected,
            }

    def execute(self, func: Callable[[], T], tokens: int = 1) -> T:
        """Execute a function with rate limiting."""
        if not self.acquire(tokens):
            raise RuntimeError(f"Rate limit exceeded for '{self.name}'")
        return func()
