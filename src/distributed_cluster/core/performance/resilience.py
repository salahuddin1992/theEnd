"""
Unified Resilience Module - وحدة المرونة الموحدة
=================================================

A comprehensive resilience module providing fault tolerance patterns:
- Enhanced Circuit Breaker with health checks and metrics
- Advanced Rate Limiting with multiple algorithms
- Sliding Window Counter for precise rate limiting
- Health monitoring and self-healing capabilities
- Unified Resilience Manager for coordinated protection

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import (
    Any,
    Awaitable,
    Callable,
    Deque,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    TypeVar,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# Health States and Events
# =============================================================================


class HealthState(str, Enum):
    """Health states for services."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ResilienceEvent(str, Enum):
    """Events emitted by resilience components."""

    CIRCUIT_OPENED = "circuit_opened"
    CIRCUIT_CLOSED = "circuit_closed"
    CIRCUIT_HALF_OPEN = "circuit_half_open"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    BULKHEAD_REJECTED = "bulkhead_rejected"
    RETRY_ATTEMPTED = "retry_attempted"
    RETRY_EXHAUSTED = "retry_exhausted"
    FALLBACK_EXECUTED = "fallback_executed"
    HEALTH_CHECK_FAILED = "health_check_failed"
    HEALTH_CHECK_PASSED = "health_check_passed"
    SELF_HEAL_TRIGGERED = "self_heal_triggered"


@dataclass
class ResilienceEventData:
    """Data associated with a resilience event."""

    event_type: ResilienceEvent
    component_name: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type.value,
            "component_name": self.component_name,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


# =============================================================================
# Event Listener Interface
# =============================================================================


class ResilienceEventListener(ABC):
    """Interface for listening to resilience events."""

    @abstractmethod
    def on_event(self, event: ResilienceEventData) -> None:
        """Handle a resilience event."""
        pass


class LoggingEventListener(ResilienceEventListener):
    """Event listener that logs events."""

    def __init__(self, log_level: int = logging.INFO):
        self.log_level = log_level

    def on_event(self, event: ResilienceEventData) -> None:
        """Log the event."""
        logger.log(
            self.log_level,
            f"Resilience Event: {event.event_type.value} - {event.component_name}",
            extra=event.to_dict(),
        )


# =============================================================================
# Enhanced Circuit Breaker
# =============================================================================


class EnhancedCircuitState(str, Enum):
    """Enhanced circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    FORCED_OPEN = "forced_open"
    DISABLED = "disabled"


@dataclass
class EnhancedCircuitBreakerConfig:
    """Configuration for enhanced circuit breaker."""

    # Failure thresholds
    failure_threshold: int = 5
    failure_rate_threshold: float = 0.5  # 50% failure rate
    slow_call_threshold: float = 5.0  # seconds
    slow_call_rate_threshold: float = 0.8  # 80% slow calls

    # Recovery settings
    success_threshold: int = 3
    reset_timeout: float = 60.0
    half_open_max_calls: int = 10

    # Time windows
    sliding_window_size: int = 100
    sliding_window_type: str = "count"  # "count" or "time"
    sliding_window_time: float = 60.0  # seconds for time-based

    # Health check
    health_check_interval: float = 30.0
    health_check_timeout: float = 5.0

    # Fallback
    fallback_enabled: bool = True

    # Self-healing
    auto_reset_after: float = 300.0  # Auto reset after 5 minutes


@dataclass
class EnhancedCircuitBreakerStats:
    """Statistics for enhanced circuit breaker."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    slow_calls: int = 0
    timeout_calls: int = 0

    state_transitions: int = 0
    last_state_change: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None

    current_failure_rate: float = 0.0
    current_slow_rate: float = 0.0

    time_in_open: float = 0.0
    time_in_closed: float = 0.0
    time_in_half_open: float = 0.0

    consecutive_successes: int = 0
    consecutive_failures: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "rejected_calls": self.rejected_calls,
            "slow_calls": self.slow_calls,
            "timeout_calls": self.timeout_calls,
            "success_rate": (self.successful_calls / self.total_calls if self.total_calls > 0 else 1.0),
            "failure_rate": self.current_failure_rate,
            "slow_rate": self.current_slow_rate,
            "state_transitions": self.state_transitions,
            "last_state_change": (self.last_state_change.isoformat() if self.last_state_change else None),
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
        }


class EnhancedCircuitBreakerError(Exception):
    """Base exception for enhanced circuit breaker."""

    pass


class EnhancedCircuitOpenError(EnhancedCircuitBreakerError):
    """Exception raised when circuit is open."""

    def __init__(self, name: str, reset_time: float, stats: EnhancedCircuitBreakerStats):
        self.name = name
        self.reset_time = reset_time
        self.stats = stats
        super().__init__(
            f"Circuit '{name}' is open. Reset in {reset_time:.1f}s. " f"Failure rate: {stats.current_failure_rate:.1%}"
        )


class EnhancedCircuitBreaker(Generic[T]):
    """
    Enhanced Circuit Breaker with advanced features.

    Features:
    - Sliding window for failure rate calculation
    - Slow call detection
    - Health checks
    - Self-healing capabilities
    - Comprehensive metrics
    - Event notifications

    Usage:
        cb = EnhancedCircuitBreaker("my_service")

        @cb
        async def call_service():
            ...

        # Or direct call
        result = await cb.execute(call_service)
    """

    def __init__(
        self,
        name: str,
        config: Optional[EnhancedCircuitBreakerConfig] = None,
        health_check: Optional[Callable[[], Awaitable[bool]]] = None,
        event_listeners: Optional[List[ResilienceEventListener]] = None,
    ):
        self.name = name
        self.config = config or EnhancedCircuitBreakerConfig()
        self.health_check = health_check
        self._event_listeners = event_listeners or []

        self._state = EnhancedCircuitState.CLOSED
        self._stats = EnhancedCircuitBreakerStats()
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()

        # Sliding window data
        self._call_results: Deque[Tuple[float, bool, float]] = deque(maxlen=self.config.sliding_window_size)
        self._half_open_calls = 0
        self._opened_at: Optional[float] = None
        self._state_time = time.time()

        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None

    @property
    def state(self) -> EnhancedCircuitState:
        """Get current state."""
        with self._lock:
            self._check_state_transition()
            return self._state

    @property
    def stats(self) -> EnhancedCircuitBreakerStats:
        """Get statistics."""
        return self._stats

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed."""
        return self.state == EnhancedCircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self.state in (EnhancedCircuitState.OPEN, EnhancedCircuitState.FORCED_OPEN)

    def _emit_event(self, event_type: ResilienceEvent, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to listeners."""
        event = ResilienceEventData(
            event_type=event_type,
            component_name=self.name,
            metadata=metadata or {},
        )
        for listener in self._event_listeners:
            try:
                listener.on_event(event)
            except Exception as e:
                logger.warning(f"Event listener error: {e}")

    def _check_state_transition(self) -> None:
        """Check and perform state transitions."""
        now = time.time()

        if self._state == EnhancedCircuitState.OPEN:
            if self._opened_at and (now - self._opened_at) >= self.config.reset_timeout:
                self._transition_to(EnhancedCircuitState.HALF_OPEN)

            # Auto-reset after configured time
            if self._opened_at and (now - self._opened_at) >= self.config.auto_reset_after:
                self._transition_to(EnhancedCircuitState.CLOSED)

        # Calculate failure rate
        self._update_failure_metrics()

    def _update_failure_metrics(self) -> None:
        """Update failure rate metrics."""
        if not self._call_results:
            self._stats.current_failure_rate = 0.0
            self._stats.current_slow_rate = 0.0
            return

        now = time.time()

        if self.config.sliding_window_type == "time":
            cutoff = now - self.config.sliding_window_time
            valid_results = [(t, s, d) for t, s, d in self._call_results if t >= cutoff]
        else:
            valid_results = list(self._call_results)

        if not valid_results:
            self._stats.current_failure_rate = 0.0
            self._stats.current_slow_rate = 0.0
            return

        total = len(valid_results)
        failures = sum(1 for _, success, _ in valid_results if not success)
        slow_calls = sum(1 for _, _, duration in valid_results if duration > self.config.slow_call_threshold)

        self._stats.current_failure_rate = failures / total
        self._stats.current_slow_rate = slow_calls / total

    def _transition_to(self, new_state: EnhancedCircuitState) -> None:
        """Transition to a new state."""
        if self._state == new_state:
            return

        old_state = self._state
        now = time.time()

        # Update time in state
        duration = now - self._state_time
        if old_state == EnhancedCircuitState.OPEN:
            self._stats.time_in_open += duration
        elif old_state == EnhancedCircuitState.CLOSED:
            self._stats.time_in_closed += duration
        elif old_state == EnhancedCircuitState.HALF_OPEN:
            self._stats.time_in_half_open += duration

        self._state = new_state
        self._state_time = now
        self._stats.state_transitions += 1
        self._stats.last_state_change = datetime.now(timezone.utc)

        # State-specific actions
        if new_state == EnhancedCircuitState.OPEN:
            self._opened_at = now
            self._half_open_calls = 0
            self._emit_event(
                ResilienceEvent.CIRCUIT_OPENED,
                {
                    "failure_rate": self._stats.current_failure_rate,
                    "consecutive_failures": self._stats.consecutive_failures,
                },
            )
        elif new_state == EnhancedCircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._emit_event(ResilienceEvent.CIRCUIT_HALF_OPEN)
        elif new_state == EnhancedCircuitState.CLOSED:
            self._call_results.clear()
            self._stats.consecutive_failures = 0
            self._emit_event(ResilienceEvent.CIRCUIT_CLOSED)

        logger.info(f"Circuit '{self.name}' transitioned: {old_state.value} -> {new_state.value}")

    def _record_call(self, success: bool, duration: float) -> None:
        """Record a call result."""
        now = time.time()

        with self._lock:
            self._call_results.append((now, success, duration))
            self._stats.total_calls += 1

            if success:
                self._stats.successful_calls += 1
                self._stats.last_success = datetime.now(timezone.utc)
                self._stats.consecutive_successes += 1
                self._stats.consecutive_failures = 0
            else:
                self._stats.failed_calls += 1
                self._stats.last_failure = datetime.now(timezone.utc)
                self._stats.consecutive_failures += 1
                self._stats.consecutive_successes = 0

            if duration > self.config.slow_call_threshold:
                self._stats.slow_calls += 1

            self._update_failure_metrics()

            # Check for state transitions
            if self._state == EnhancedCircuitState.CLOSED:
                should_open = False

                # Check failure count threshold
                if self._stats.consecutive_failures >= self.config.failure_threshold:
                    should_open = True

                # Check failure rate threshold
                if len(self._call_results) >= self.config.sliding_window_size:
                    if self._stats.current_failure_rate >= self.config.failure_rate_threshold:
                        should_open = True

                # Check slow call rate threshold
                if self._stats.current_slow_rate >= self.config.slow_call_rate_threshold:
                    should_open = True

                if should_open:
                    self._transition_to(EnhancedCircuitState.OPEN)

            elif self._state == EnhancedCircuitState.HALF_OPEN:
                if not success:
                    self._transition_to(EnhancedCircuitState.OPEN)
                elif self._stats.consecutive_successes >= self.config.success_threshold:
                    self._transition_to(EnhancedCircuitState.CLOSED)

    def _can_execute(self) -> bool:
        """Check if execution is allowed."""
        with self._lock:
            self._check_state_transition()

            if self._state == EnhancedCircuitState.CLOSED:
                return True
            elif self._state == EnhancedCircuitState.DISABLED:
                return True
            elif self._state == EnhancedCircuitState.HALF_OPEN:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            else:
                return False

    def _get_reset_time(self) -> float:
        """Get time until reset."""
        if self._opened_at is None:
            return 0.0
        elapsed = time.time() - self._opened_at
        return max(0.0, self.config.reset_timeout - elapsed)

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        fallback: Optional[Callable[..., T]] = None,
        **kwargs,
    ) -> T:
        """Execute a function with circuit breaker protection."""
        if not self._can_execute():
            self._stats.rejected_calls += 1
            reset_time = self._get_reset_time()

            if fallback and self.config.fallback_enabled:
                self._emit_event(ResilienceEvent.FALLBACK_EXECUTED)
                result = fallback(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    return await result
                return result

            raise EnhancedCircuitOpenError(self.name, reset_time, self._stats)

        start_time = time.time()
        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.health_check_timeout * 2,
            )
            duration = time.time() - start_time
            self._record_call(True, duration)
            return result

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            self._stats.timeout_calls += 1
            self._record_call(False, duration)

            if fallback and self.config.fallback_enabled:
                self._emit_event(ResilienceEvent.FALLBACK_EXECUTED)
                result = fallback(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    return await result
                return result
            raise

        except Exception:
            duration = time.time() - start_time
            self._record_call(False, duration)

            if fallback and self.config.fallback_enabled:
                self._emit_event(ResilienceEvent.FALLBACK_EXECUTED)
                result = fallback(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    return await result
                return result
            raise

    def execute_sync(
        self,
        func: Callable[..., T],
        *args,
        fallback: Optional[Callable[..., T]] = None,
        **kwargs,
    ) -> T:
        """Execute a synchronous function with circuit breaker protection."""
        if not self._can_execute():
            self._stats.rejected_calls += 1
            reset_time = self._get_reset_time()

            if fallback and self.config.fallback_enabled:
                return fallback(*args, **kwargs)

            raise EnhancedCircuitOpenError(self.name, reset_time, self._stats)

        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            self._record_call(True, duration)
            return result

        except Exception:
            duration = time.time() - start_time
            self._record_call(False, duration)

            if fallback and self.config.fallback_enabled:
                return fallback(*args, **kwargs)
            raise

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Use as decorator."""
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await self.execute(func, *args, **kwargs)

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                return self.execute_sync(func, *args, **kwargs)

            return sync_wrapper

    def reset(self) -> None:
        """Reset the circuit breaker."""
        with self._lock:
            self._transition_to(EnhancedCircuitState.CLOSED)
            self._call_results.clear()
            self._half_open_calls = 0
            self._opened_at = None

    def force_open(self) -> None:
        """Force the circuit to open state."""
        with self._lock:
            self._transition_to(EnhancedCircuitState.FORCED_OPEN)

    def disable(self) -> None:
        """Disable the circuit breaker (always allow calls)."""
        with self._lock:
            self._transition_to(EnhancedCircuitState.DISABLED)

    def enable(self) -> None:
        """Enable the circuit breaker."""
        with self._lock:
            if self._state == EnhancedCircuitState.DISABLED:
                self._transition_to(EnhancedCircuitState.CLOSED)

    def get_info(self) -> Dict[str, Any]:
        """Get circuit breaker info."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_rate": self._stats.current_failure_rate,
                "slow_call_rate": self._stats.current_slow_rate,
                "reset_time": self._get_reset_time() if self.is_open else 0,
                "stats": self._stats.to_dict(),
                "config": {
                    "failure_threshold": self.config.failure_threshold,
                    "failure_rate_threshold": self.config.failure_rate_threshold,
                    "success_threshold": self.config.success_threshold,
                    "reset_timeout": self.config.reset_timeout,
                },
            }


# =============================================================================
# Sliding Window Counter Rate Limiter
# =============================================================================


@dataclass
class SlidingWindowCounterConfig:
    """Configuration for sliding window counter rate limiter."""

    requests_per_window: int = 100
    window_size_seconds: float = 60.0
    precision_segments: int = 10  # Number of sub-windows for precision


@dataclass
class SlidingWindowCounterResult:
    """Result of a sliding window counter check."""

    allowed: bool
    current_count: int
    limit: int
    remaining: int
    reset_at: float
    retry_after: float = 0.0
    window_start: float = 0.0
    window_end: float = 0.0

    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_at)),
        }
        if not self.allowed:
            headers["Retry-After"] = str(int(self.retry_after) + 1)
        return headers


class SlidingWindowCounterLimiter:
    """
    Sliding Window Counter Rate Limiter.

    Uses a hybrid approach combining fixed window and sliding window:
    - Divides time into fixed segments
    - Calculates rate based on weighted combination of current and previous segment
    - More accurate than fixed window, more memory-efficient than pure sliding window

    Example:
        limiter = SlidingWindowCounterLimiter(
            SlidingWindowCounterConfig(
                requests_per_window=100,
                window_size_seconds=60.0,
                precision_segments=10
            )
        )

        result = limiter.acquire("user-123")
        if result.allowed:
            # Process request
            ...
    """

    def __init__(self, config: SlidingWindowCounterConfig):
        self.config = config
        self._segments: Dict[str, Dict[int, int]] = {}
        self._lock = threading.Lock()
        self._segment_duration = config.window_size_seconds / config.precision_segments

    def _get_segment_key(self, timestamp: float) -> int:
        """Get the segment key for a timestamp."""
        return int(timestamp / self._segment_duration)

    def _get_weighted_count(self, key: str, now: float) -> Tuple[int, float]:
        """
        Get the weighted count for the current sliding window.

        Returns (count, weight_of_oldest_segment)
        """
        current_segment = self._get_segment_key(now)
        window_segments = self.config.precision_segments

        if key not in self._segments:
            return 0, 0.0

        segments = self._segments[key]

        # Calculate position within current segment (0.0 to 1.0)
        segment_progress = (now % self._segment_duration) / self._segment_duration

        total_count = 0.0
        for i in range(window_segments):
            segment_key = current_segment - i
            segment_count = segments.get(segment_key, 0)

            if i == window_segments - 1:
                # Oldest segment: weight by remaining portion
                weight = 1.0 - segment_progress
                total_count += segment_count * weight
            else:
                total_count += segment_count

        return int(math.ceil(total_count)), segment_progress

    def _cleanup_old_segments(self, key: str, current_segment: int) -> None:
        """Remove segments older than the window."""
        if key not in self._segments:
            return

        min_segment = current_segment - self.config.precision_segments - 1
        old_keys = [k for k in self._segments[key].keys() if k < min_segment]
        for old_key in old_keys:
            del self._segments[key][old_key]

    def acquire(self, key: str = "default", tokens: int = 1) -> SlidingWindowCounterResult:
        """Attempt to acquire tokens."""
        now = time.time()

        with self._lock:
            current_segment = self._get_segment_key(now)
            weighted_count, _ = self._get_weighted_count(key, now)

            # Calculate window boundaries
            window_end = (current_segment + 1) * self._segment_duration
            window_start = window_end - self.config.window_size_seconds

            if weighted_count + tokens <= self.config.requests_per_window:
                # Initialize key if needed
                if key not in self._segments:
                    self._segments[key] = {}

                # Increment current segment
                self._segments[key][current_segment] = self._segments[key].get(current_segment, 0) + tokens

                # Cleanup old segments
                self._cleanup_old_segments(key, current_segment)

                remaining = self.config.requests_per_window - weighted_count - tokens

                return SlidingWindowCounterResult(
                    allowed=True,
                    current_count=weighted_count + tokens,
                    limit=self.config.requests_per_window,
                    remaining=remaining,
                    reset_at=window_end,
                    window_start=window_start,
                    window_end=window_end,
                )
            else:
                # Calculate retry time
                retry_after = self._segment_duration

                return SlidingWindowCounterResult(
                    allowed=False,
                    current_count=weighted_count,
                    limit=self.config.requests_per_window,
                    remaining=0,
                    reset_at=window_end,
                    retry_after=retry_after,
                    window_start=window_start,
                    window_end=window_end,
                )

    async def acquire_async(self, key: str = "default", tokens: int = 1) -> SlidingWindowCounterResult:
        """Async version of acquire."""
        return self.acquire(key, tokens)

    def reset(self, key: str = "default") -> None:
        """Reset counts for a key."""
        with self._lock:
            if key in self._segments:
                del self._segments[key]

    def get_stats(self, key: str = "default") -> Dict[str, Any]:
        """Get statistics for a key."""
        now = time.time()

        with self._lock:
            weighted_count, _ = self._get_weighted_count(key, now)

            return {
                "key": key,
                "current_count": weighted_count,
                "limit": self.config.requests_per_window,
                "remaining": max(0, self.config.requests_per_window - weighted_count),
                "window_size_seconds": self.config.window_size_seconds,
                "precision_segments": self.config.precision_segments,
            }


# =============================================================================
# Token Bucket with Burst Control
# =============================================================================


@dataclass
class TokenBucketConfig:
    """Configuration for token bucket rate limiter."""

    rate: float = 10.0  # Tokens per second
    capacity: int = 100  # Maximum burst size
    initial_tokens: Optional[int] = None  # Initial token count (defaults to capacity)


class TokenBucketRateLimiter:
    """
    Token Bucket Rate Limiter with precise burst control.

    Features:
    - Configurable refill rate
    - Burst capacity control
    - Smooth rate limiting
    - Thread-safe operation
    """

    def __init__(self, config: TokenBucketConfig):
        self.config = config
        self._buckets: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, key: str) -> Dict[str, Any]:
        """Get or create a bucket for a key."""
        now = time.time()

        if key not in self._buckets:
            initial = self.config.initial_tokens if self.config.initial_tokens is not None else self.config.capacity
            self._buckets[key] = {
                "tokens": float(initial),
                "last_refill": now,
            }
            return self._buckets[key]

        bucket = self._buckets[key]

        # Refill tokens based on elapsed time
        elapsed = now - bucket["last_refill"]
        new_tokens = elapsed * self.config.rate
        bucket["tokens"] = min(self.config.capacity, bucket["tokens"] + new_tokens)
        bucket["last_refill"] = now

        return bucket

    def acquire(self, key: str = "default", tokens: int = 1) -> SlidingWindowCounterResult:
        """Attempt to acquire tokens."""
        now = time.time()

        with self._lock:
            bucket = self._get_bucket(key)

            if bucket["tokens"] >= tokens:
                bucket["tokens"] -= tokens
                remaining = int(bucket["tokens"])

                # Time until bucket is full again
                tokens_needed = self.config.capacity - bucket["tokens"]
                reset_time = now + (tokens_needed / self.config.rate)

                return SlidingWindowCounterResult(
                    allowed=True,
                    current_count=self.config.capacity - remaining,
                    limit=self.config.capacity,
                    remaining=remaining,
                    reset_at=reset_time,
                )
            else:
                # Calculate wait time for requested tokens
                needed = tokens - bucket["tokens"]
                retry_after = needed / self.config.rate

                return SlidingWindowCounterResult(
                    allowed=False,
                    current_count=self.config.capacity,
                    limit=self.config.capacity,
                    remaining=0,
                    reset_at=now + retry_after,
                    retry_after=retry_after,
                )

    async def acquire_async(self, key: str = "default", tokens: int = 1) -> SlidingWindowCounterResult:
        """Async version of acquire."""
        return self.acquire(key, tokens)

    def reset(self, key: str = "default") -> None:
        """Reset a bucket."""
        with self._lock:
            if key in self._buckets:
                del self._buckets[key]

    def get_tokens(self, key: str = "default") -> float:
        """Get current token count."""
        with self._lock:
            bucket = self._get_bucket(key)
            return bucket["tokens"]


# =============================================================================
# Unified Rate Limiter
# =============================================================================


class RateLimitStrategy(str, Enum):
    """Rate limiting strategies."""

    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    FIXED_WINDOW = "fixed_window"


@dataclass
class UnifiedRateLimitConfig:
    """Configuration for unified rate limiter."""

    # Common settings
    requests_per_second: float = 10.0
    burst_size: int = 20
    window_size_seconds: float = 60.0

    # Strategy
    strategy: RateLimitStrategy = RateLimitStrategy.TOKEN_BUCKET

    # Multi-level limits
    per_second_limit: Optional[int] = None
    per_minute_limit: Optional[int] = None
    per_hour_limit: Optional[int] = None

    # Sliding window counter settings
    precision_segments: int = 10

    # Behavior
    block_duration_seconds: float = 0.0  # How long to block after limit exceeded
    warn_threshold: float = 0.8  # Warn at 80% of limit


class UnifiedRateLimiter:
    """
    Unified Rate Limiter supporting multiple strategies and multi-level limits.

    Features:
    - Multiple algorithm support
    - Multi-level rate limits (per-second, per-minute, per-hour)
    - Warning thresholds
    - Block durations
    - Comprehensive statistics
    """

    def __init__(
        self,
        name: str,
        config: UnifiedRateLimitConfig,
        event_listeners: Optional[List[ResilienceEventListener]] = None,
    ):
        self.name = name
        self.config = config
        self._event_listeners = event_listeners or []

        # Initialize limiters based on strategy
        self._primary_limiter = self._create_limiter()

        # Multi-level limiters
        self._level_limiters: Dict[str, Any] = {}
        if config.per_second_limit:
            self._level_limiters["second"] = TokenBucketRateLimiter(
                TokenBucketConfig(
                    rate=float(config.per_second_limit),
                    capacity=config.per_second_limit,
                )
            )
        if config.per_minute_limit:
            self._level_limiters["minute"] = SlidingWindowCounterLimiter(
                SlidingWindowCounterConfig(
                    requests_per_window=config.per_minute_limit,
                    window_size_seconds=60.0,
                )
            )
        if config.per_hour_limit:
            self._level_limiters["hour"] = SlidingWindowCounterLimiter(
                SlidingWindowCounterConfig(
                    requests_per_window=config.per_hour_limit,
                    window_size_seconds=3600.0,
                )
            )

        # Blocking state
        self._blocked_until: Dict[str, float] = {}
        self._lock = threading.Lock()

        # Statistics
        self._stats = {
            "total_requests": 0,
            "allowed_requests": 0,
            "denied_requests": 0,
            "blocked_requests": 0,
            "warnings_issued": 0,
        }

    def _create_limiter(self):
        """Create the primary limiter based on strategy."""
        if self.config.strategy == RateLimitStrategy.TOKEN_BUCKET:
            return TokenBucketRateLimiter(
                TokenBucketConfig(
                    rate=self.config.requests_per_second,
                    capacity=self.config.burst_size,
                )
            )
        elif self.config.strategy == RateLimitStrategy.SLIDING_WINDOW_COUNTER:
            return SlidingWindowCounterLimiter(
                SlidingWindowCounterConfig(
                    requests_per_window=int(self.config.requests_per_second * self.config.window_size_seconds),
                    window_size_seconds=self.config.window_size_seconds,
                    precision_segments=self.config.precision_segments,
                )
            )
        else:
            # Default to token bucket
            return TokenBucketRateLimiter(
                TokenBucketConfig(
                    rate=self.config.requests_per_second,
                    capacity=self.config.burst_size,
                )
            )

    def _emit_event(self, event_type: ResilienceEvent, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to listeners."""
        event = ResilienceEventData(
            event_type=event_type,
            component_name=self.name,
            metadata=metadata or {},
        )
        for listener in self._event_listeners:
            try:
                listener.on_event(event)
            except Exception as e:
                logger.warning(f"Event listener error: {e}")

    def acquire(self, key: str = "default", tokens: int = 1) -> SlidingWindowCounterResult:
        """Attempt to acquire tokens."""
        now = time.time()

        with self._lock:
            self._stats["total_requests"] += 1

            # Check if blocked
            if key in self._blocked_until:
                if now < self._blocked_until[key]:
                    self._stats["blocked_requests"] += 1
                    return SlidingWindowCounterResult(
                        allowed=False,
                        current_count=0,
                        limit=self.config.burst_size,
                        remaining=0,
                        reset_at=self._blocked_until[key],
                        retry_after=self._blocked_until[key] - now,
                    )
                else:
                    del self._blocked_until[key]

        # Check multi-level limits first
        for level_name, limiter in self._level_limiters.items():
            result = limiter.acquire(key, tokens)
            if not result.allowed:
                with self._lock:
                    self._stats["denied_requests"] += 1

                    # Apply block duration if configured
                    if self.config.block_duration_seconds > 0:
                        self._blocked_until[key] = now + self.config.block_duration_seconds

                self._emit_event(
                    ResilienceEvent.RATE_LIMIT_EXCEEDED,
                    {"level": level_name, "key": key},
                )
                return result

        # Check primary limiter
        result = self._primary_limiter.acquire(key, tokens)

        with self._lock:
            if result.allowed:
                self._stats["allowed_requests"] += 1

                # Check warning threshold
                usage_ratio = result.current_count / result.limit if result.limit > 0 else 0
                if usage_ratio >= self.config.warn_threshold:
                    self._stats["warnings_issued"] += 1
            else:
                self._stats["denied_requests"] += 1

                # Apply block duration if configured
                if self.config.block_duration_seconds > 0:
                    self._blocked_until[key] = now + self.config.block_duration_seconds

                self._emit_event(
                    ResilienceEvent.RATE_LIMIT_EXCEEDED,
                    {"key": key, "retry_after": result.retry_after},
                )

        return result

    async def acquire_async(self, key: str = "default", tokens: int = 1) -> SlidingWindowCounterResult:
        """Async version of acquire."""
        return self.acquire(key, tokens)

    def reset(self, key: str = "default") -> None:
        """Reset limits for a key."""
        self._primary_limiter.reset(key)
        for limiter in self._level_limiters.values():
            limiter.reset(key)
        with self._lock:
            if key in self._blocked_until:
                del self._blocked_until[key]

    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        with self._lock:
            return {
                "name": self.name,
                "strategy": self.config.strategy.value,
                **self._stats.copy(),
            }


# =============================================================================
# Health Monitor
# =============================================================================


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    healthy: bool
    state: HealthState
    latency_ms: float
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class HealthMonitor:
    """
    Health Monitor for tracking service health.

    Features:
    - Periodic health checks
    - Health state tracking
    - Latency monitoring
    - Self-healing triggers
    """

    def __init__(
        self,
        name: str,
        health_check: Callable[[], Awaitable[bool]],
        check_interval: float = 30.0,
        timeout: float = 5.0,
        unhealthy_threshold: int = 3,
        healthy_threshold: int = 2,
        event_listeners: Optional[List[ResilienceEventListener]] = None,
    ):
        self.name = name
        self.health_check = health_check
        self.check_interval = check_interval
        self.timeout = timeout
        self.unhealthy_threshold = unhealthy_threshold
        self.healthy_threshold = healthy_threshold
        self._event_listeners = event_listeners or []

        self._state = HealthState.UNKNOWN
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_check: Optional[HealthCheckResult] = None
        self._check_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()

        # History
        self._check_history: Deque[HealthCheckResult] = deque(maxlen=100)

    @property
    def state(self) -> HealthState:
        """Get current health state."""
        return self._state

    @property
    def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return self._state == HealthState.HEALTHY

    def _emit_event(self, event_type: ResilienceEvent, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to listeners."""
        event = ResilienceEventData(
            event_type=event_type,
            component_name=self.name,
            metadata=metadata or {},
        )
        for listener in self._event_listeners:
            try:
                listener.on_event(event)
            except Exception as e:
                logger.warning(f"Event listener error: {e}")

    async def check_health(self) -> HealthCheckResult:
        """Perform a health check."""
        start_time = time.time()

        try:
            healthy = await asyncio.wait_for(
                self.health_check(),
                timeout=self.timeout,
            )
            latency_ms = (time.time() - start_time) * 1000

            result = HealthCheckResult(
                healthy=healthy,
                state=HealthState.HEALTHY if healthy else HealthState.UNHEALTHY,
                latency_ms=latency_ms,
                message="Health check passed" if healthy else "Health check failed",
            )

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            result = HealthCheckResult(
                healthy=False,
                state=HealthState.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"Health check timed out after {self.timeout}s",
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            result = HealthCheckResult(
                healthy=False,
                state=HealthState.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"Health check error: {str(e)}",
            )

        async with self._lock:
            self._last_check = result
            self._check_history.append(result)

            # Update state based on consecutive results
            if result.healthy:
                self._consecutive_failures = 0
                self._consecutive_successes += 1
                self._emit_event(ResilienceEvent.HEALTH_CHECK_PASSED)

                if self._consecutive_successes >= self.healthy_threshold:
                    if self._state != HealthState.HEALTHY:
                        old_state = self._state
                        self._state = HealthState.HEALTHY
                        logger.info(f"Health Monitor '{self.name}': {old_state.value} -> healthy")
            else:
                self._consecutive_successes = 0
                self._consecutive_failures += 1
                self._emit_event(
                    ResilienceEvent.HEALTH_CHECK_FAILED,
                    {"message": result.message, "consecutive_failures": self._consecutive_failures},
                )

                if self._consecutive_failures >= self.unhealthy_threshold:
                    if self._state != HealthState.UNHEALTHY:
                        old_state = self._state
                        self._state = HealthState.UNHEALTHY
                        logger.warning(f"Health Monitor '{self.name}': {old_state.value} -> unhealthy")
                elif self._state == HealthState.HEALTHY:
                    self._state = HealthState.DEGRADED

        return result

    async def start(self) -> None:
        """Start periodic health checking."""
        if self._running:
            return

        self._running = True

        async def check_loop():
            while self._running:
                try:
                    await self.check_health()
                except Exception as e:
                    logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(self.check_interval)

        self._check_task = asyncio.create_task(check_loop())

    async def stop(self) -> None:
        """Stop periodic health checking."""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

    def get_stats(self) -> Dict[str, Any]:
        """Get health monitor statistics."""
        recent_checks = list(self._check_history)
        successful = sum(1 for r in recent_checks if r.healthy)
        avg_latency = sum(r.latency_ms for r in recent_checks) / len(recent_checks) if recent_checks else 0.0

        return {
            "name": self.name,
            "state": self._state.value,
            "consecutive_successes": self._consecutive_successes,
            "consecutive_failures": self._consecutive_failures,
            "total_checks": len(recent_checks),
            "successful_checks": successful,
            "success_rate": successful / len(recent_checks) if recent_checks else 0.0,
            "avg_latency_ms": avg_latency,
            "last_check": self._last_check.timestamp.isoformat() if self._last_check else None,
        }


# =============================================================================
# Unified Resilience Manager
# =============================================================================


@dataclass
class ResilienceConfig:
    """Configuration for unified resilience manager."""

    # Circuit breaker
    circuit_breaker_enabled: bool = True
    circuit_breaker_config: Optional[EnhancedCircuitBreakerConfig] = None

    # Rate limiting
    rate_limiter_enabled: bool = True
    rate_limiter_config: Optional[UnifiedRateLimitConfig] = None

    # Health monitoring
    health_monitor_enabled: bool = False
    health_check_interval: float = 30.0
    health_check_timeout: float = 5.0

    # Fallback
    fallback_enabled: bool = True


class ResilienceManager:
    """
    Unified Resilience Manager.

    Combines circuit breaker, rate limiting, and health monitoring
    into a single coordinated resilience layer.

    Usage:
        manager = ResilienceManager(
            "my_service",
            ResilienceConfig(
                circuit_breaker_enabled=True,
                rate_limiter_enabled=True,
            )
        )

        @manager.protect
        async def call_service():
            ...

        # Or direct execution
        result = await manager.execute(call_service, arg1, arg2)
    """

    def __init__(
        self,
        name: str,
        config: ResilienceConfig,
        health_check: Optional[Callable[[], Awaitable[bool]]] = None,
        fallback: Optional[Callable[..., Any]] = None,
        event_listeners: Optional[List[ResilienceEventListener]] = None,
    ):
        self.name = name
        self.config = config
        self.fallback = fallback
        self._event_listeners = event_listeners or [LoggingEventListener()]

        # Initialize components
        self._circuit_breaker: Optional[EnhancedCircuitBreaker] = None
        self._rate_limiter: Optional[UnifiedRateLimiter] = None
        self._health_monitor: Optional[HealthMonitor] = None

        if config.circuit_breaker_enabled:
            self._circuit_breaker = EnhancedCircuitBreaker(
                f"{name}-cb",
                config.circuit_breaker_config or EnhancedCircuitBreakerConfig(),
                event_listeners=self._event_listeners,
            )

        if config.rate_limiter_enabled:
            self._rate_limiter = UnifiedRateLimiter(
                f"{name}-rl",
                config.rate_limiter_config or UnifiedRateLimitConfig(),
                event_listeners=self._event_listeners,
            )

        if config.health_monitor_enabled and health_check:
            self._health_monitor = HealthMonitor(
                f"{name}-hm",
                health_check,
                config.health_check_interval,
                config.health_check_timeout,
                event_listeners=self._event_listeners,
            )

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        key: str = "default",
        fallback: Optional[Callable[..., T]] = None,
        **kwargs,
    ) -> T:
        """Execute a function with full resilience protection."""
        effective_fallback = fallback or self.fallback

        # Rate limiting check
        if self._rate_limiter:
            result = self._rate_limiter.acquire(key)
            if not result.allowed:
                if effective_fallback and self.config.fallback_enabled:
                    result = effective_fallback(*args, **kwargs)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
                raise Exception(f"Rate limit exceeded for '{self.name}'. " f"Retry after {result.retry_after:.1f}s")

        # Circuit breaker execution
        if self._circuit_breaker:
            return await self._circuit_breaker.execute(func, *args, fallback=effective_fallback, **kwargs)
        else:
            try:
                return await func(*args, **kwargs)
            except Exception:
                if effective_fallback and self.config.fallback_enabled:
                    result = effective_fallback(*args, **kwargs)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
                raise

    def protect(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to protect a function."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.execute(func, *args, **kwargs)

        return wrapper

    async def start(self) -> None:
        """Start background tasks (health monitoring)."""
        if self._health_monitor:
            await self._health_monitor.start()

    async def stop(self) -> None:
        """Stop background tasks."""
        if self._health_monitor:
            await self._health_monitor.stop()

    def reset(self) -> None:
        """Reset all resilience components."""
        if self._circuit_breaker:
            self._circuit_breaker.reset()
        if self._rate_limiter:
            self._rate_limiter.reset()

    def get_health_state(self) -> HealthState:
        """Get overall health state."""
        if self._health_monitor:
            return self._health_monitor.state

        if self._circuit_breaker:
            if self._circuit_breaker.is_open:
                return HealthState.UNHEALTHY
            elif self._circuit_breaker.state == EnhancedCircuitState.HALF_OPEN:
                return HealthState.DEGRADED

        return HealthState.HEALTHY

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        stats = {
            "name": self.name,
            "health_state": self.get_health_state().value,
        }

        if self._circuit_breaker:
            stats["circuit_breaker"] = self._circuit_breaker.get_info()

        if self._rate_limiter:
            stats["rate_limiter"] = self._rate_limiter.get_stats()

        if self._health_monitor:
            stats["health_monitor"] = self._health_monitor.get_stats()

        return stats


# =============================================================================
# Factory Functions and Decorators
# =============================================================================


_managers: Dict[str, ResilienceManager] = {}
_managers_lock = threading.Lock()


def get_resilience_manager(
    name: str,
    config: Optional[ResilienceConfig] = None,
) -> ResilienceManager:
    """Get or create a resilience manager by name."""
    with _managers_lock:
        if name not in _managers:
            _managers[name] = ResilienceManager(name, config or ResilienceConfig())
        return _managers[name]


def resilient(
    name: str,
    circuit_breaker: bool = True,
    rate_limiter: bool = True,
    fallback: Optional[Callable] = None,
    **kwargs,
):
    """
    Decorator for applying resilience patterns.

    Usage:
        @resilient("my_service", circuit_breaker=True, rate_limiter=True)
        async def call_service():
            ...
    """
    config = ResilienceConfig(
        circuit_breaker_enabled=circuit_breaker,
        rate_limiter_enabled=rate_limiter,
        fallback_enabled=fallback is not None,
    )

    manager = get_resilience_manager(name, config)
    manager.fallback = fallback

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        return manager.protect(func)

    return decorator


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Health states and events
    "HealthState",
    "ResilienceEvent",
    "ResilienceEventData",
    "ResilienceEventListener",
    "LoggingEventListener",
    # Enhanced Circuit Breaker
    "EnhancedCircuitState",
    "EnhancedCircuitBreakerConfig",
    "EnhancedCircuitBreakerStats",
    "EnhancedCircuitBreakerError",
    "EnhancedCircuitOpenError",
    "EnhancedCircuitBreaker",
    # Rate Limiters
    "SlidingWindowCounterConfig",
    "SlidingWindowCounterResult",
    "SlidingWindowCounterLimiter",
    "TokenBucketConfig",
    "TokenBucketRateLimiter",
    "RateLimitStrategy",
    "UnifiedRateLimitConfig",
    "UnifiedRateLimiter",
    # Health Monitoring
    "HealthCheckResult",
    "HealthMonitor",
    # Resilience Manager
    "ResilienceConfig",
    "ResilienceManager",
    # Factory and Decorators
    "get_resilience_manager",
    "resilient",
]
