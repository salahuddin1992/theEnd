"""
Circuit Breaker Pattern - نمط قاطع الدائرة
===========================================

نمط Circuit Breaker لحماية النظام من الأعطال المتتالية:
- حماية من الخدمات المتعطلة
- استرداد تلقائي
- Fallback للقيم البديلة
- مراقبة وإحصائيات
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    Union,
)


class CircuitState(str, Enum):
    """حالة الدائرة."""

    CLOSED = "closed"  # الدائرة مغلقة (طبيعي)
    OPEN = "open"  # الدائرة مفتوحة (رفض الطلبات)
    HALF_OPEN = "half_open"  # نصف مفتوحة (اختبار)


@dataclass
class CircuitBreakerConfig:
    """إعدادات Circuit Breaker."""

    # عتبات الفشل
    failure_threshold: int = 5  # عدد الأخطاء لفتح الدائرة
    success_threshold: int = 3  # عدد النجاحات لإغلاق الدائرة

    # المهلات
    timeout: float = 30.0  # مهلة العملية
    reset_timeout: float = 60.0  # وقت الانتظار قبل المحاولة مرة أخرى

    # النافذة الزمنية
    failure_window: float = 60.0  # نافذة حساب الأخطاء (ثانية)

    # Fallback
    fallback_value: Any = None  # القيمة البديلة

    # استثناءات
    excluded_exceptions: Tuple[type, ...] = ()  # استثناءات لا تُحتسب كفشل


@dataclass
class CircuitBreakerStats:
    """إحصائيات Circuit Breaker."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    timeout_requests: int = 0

    state_changes: int = 0
    last_state_change: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None

    time_in_open: float = 0.0
    time_in_closed: float = 0.0
    time_in_half_open: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "rejected_requests": self.rejected_requests,
            "timeout_requests": self.timeout_requests,
            "success_rate": (
                self.successful_requests / self.total_requests
                if self.total_requests > 0
                else 0.0
            ),
            "state_changes": self.state_changes,
            "last_state_change": (
                self.last_state_change.isoformat() if self.last_state_change else None
            ),
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
        }


class CircuitBreakerError(Exception):
    """خطأ Circuit Breaker."""

    pass


class CircuitOpenError(CircuitBreakerError):
    """خطأ: الدائرة مفتوحة."""

    def __init__(self, circuit_name: str, reset_time: float):
        self.circuit_name = circuit_name
        self.reset_time = reset_time
        super().__init__(
            f"Circuit '{circuit_name}' is open. "
            f"Will attempt reset in {reset_time:.1f} seconds."
        )


T = TypeVar("T")


class CircuitBreaker(Generic[T]):
    """
    Circuit Breaker للحماية من الأعطال.

    الاستخدام:
        cb = CircuitBreaker("my_service")

        @cb
        async def call_service():
            ...

        # أو
        result = await cb.call(call_service)
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        on_state_change: Optional[Callable[[CircuitState, CircuitState], None]] = None,
        on_failure: Optional[Callable[[Exception], None]] = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.on_state_change = on_state_change
        self.on_failure = on_failure

        self._state = CircuitState.CLOSED
        self._failures: Deque[float] = deque()
        self._successes = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None

        self._stats = CircuitBreakerStats()
        self._lock = threading.Lock()
        self._state_time = time.time()

    @property
    def state(self) -> CircuitState:
        """الحصول على الحالة الحالية."""
        with self._lock:
            self._check_state_transition()
            return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """الحصول على الإحصائيات."""
        return self._stats

    def _check_state_transition(self) -> None:
        """التحقق من انتقال الحالة."""
        now = time.time()

        if self._state == CircuitState.OPEN:
            # Check if reset timeout has passed
            if self._opened_at and (now - self._opened_at) >= self.config.reset_timeout:
                self._transition_to(CircuitState.HALF_OPEN)

        elif self._state == CircuitState.CLOSED:
            # Clean old failures outside the window
            cutoff = now - self.config.failure_window
            while self._failures and self._failures[0] < cutoff:
                self._failures.popleft()

    def _transition_to(self, new_state: CircuitState) -> None:
        """الانتقال إلى حالة جديدة."""
        if self._state == new_state:
            return

        old_state = self._state
        now = time.time()

        # Update time in state
        duration = now - self._state_time
        if old_state == CircuitState.OPEN:
            self._stats.time_in_open += duration
        elif old_state == CircuitState.CLOSED:
            self._stats.time_in_closed += duration
        elif old_state == CircuitState.HALF_OPEN:
            self._stats.time_in_half_open += duration

        self._state = new_state
        self._state_time = now
        self._stats.state_changes += 1
        self._stats.last_state_change = datetime.utcnow()

        if new_state == CircuitState.OPEN:
            self._opened_at = now
            self._successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._successes = 0
        elif new_state == CircuitState.CLOSED:
            self._failures.clear()
            self._successes = 0

        # Callback
        if self.on_state_change:
            try:
                self.on_state_change(old_state, new_state)
            except Exception:
                pass

    def _record_success(self) -> None:
        """تسجيل نجاح."""
        with self._lock:
            self._stats.total_requests += 1
            self._stats.successful_requests += 1
            self._stats.last_success = datetime.utcnow()

            if self._state == CircuitState.HALF_OPEN:
                self._successes += 1
                if self._successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def _record_failure(self, exception: Exception) -> None:
        """تسجيل فشل."""
        with self._lock:
            now = time.time()

            self._stats.total_requests += 1
            self._stats.failed_requests += 1
            self._stats.last_failure = datetime.utcnow()

            # Check if exception should be excluded
            if isinstance(exception, self.config.excluded_exceptions):
                return

            self._failures.append(now)
            self._last_failure_time = now

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._transition_to(CircuitState.OPEN)

            elif self._state == CircuitState.CLOSED:
                # Check if failure threshold reached
                if len(self._failures) >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

            # Callback
            if self.on_failure:
                try:
                    self.on_failure(exception)
                except Exception:
                    pass

    def _record_timeout(self) -> None:
        """تسجيل timeout."""
        self._stats.timeout_requests += 1

    def _record_rejection(self) -> None:
        """تسجيل رفض."""
        with self._lock:
            self._stats.total_requests += 1
            self._stats.rejected_requests += 1

    def _can_execute(self) -> bool:
        """هل يمكن التنفيذ؟"""
        with self._lock:
            self._check_state_transition()

            if self._state == CircuitState.CLOSED:
                return True
            elif self._state == CircuitState.HALF_OPEN:
                return True
            else:  # OPEN
                return False

    def _get_reset_time(self) -> float:
        """وقت إعادة التعيين المتبقي."""
        if self._opened_at is None:
            return 0.0
        elapsed = time.time() - self._opened_at
        return max(0.0, self.config.reset_timeout - elapsed)

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        fallback: Optional[Callable[..., T]] = None,
        **kwargs,
    ) -> T:
        """
        استدعاء الدالة مع Circuit Breaker.

        Args:
            func: الدالة للاستدعاء
            fallback: دالة بديلة
            *args, **kwargs: معاملات الدالة

        Returns:
            نتيجة الدالة أو القيمة البديلة

        Raises:
            CircuitOpenError: إذا كانت الدائرة مفتوحة ولا يوجد fallback
        """
        if not self._can_execute():
            self._record_rejection()

            reset_time = self._get_reset_time()

            # Try fallback
            if fallback:
                return fallback(*args, **kwargs)
            elif self.config.fallback_value is not None:
                return self.config.fallback_value

            raise CircuitOpenError(self.name, reset_time)

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.timeout,
            )
            self._record_success()
            return result

        except asyncio.TimeoutError:
            self._record_timeout()
            self._record_failure(TimeoutError("Operation timed out"))

            if fallback:
                return fallback(*args, **kwargs)
            elif self.config.fallback_value is not None:
                return self.config.fallback_value
            raise

        except Exception as e:
            self._record_failure(e)

            if fallback:
                return fallback(*args, **kwargs)
            elif self.config.fallback_value is not None:
                return self.config.fallback_value
            raise

    def call_sync(
        self,
        func: Callable[..., T],
        *args,
        fallback: Optional[Callable[..., T]] = None,
        **kwargs,
    ) -> T:
        """استدعاء متزامن."""
        if not self._can_execute():
            self._record_rejection()
            reset_time = self._get_reset_time()

            if fallback:
                return fallback(*args, **kwargs)
            elif self.config.fallback_value is not None:
                return self.config.fallback_value

            raise CircuitOpenError(self.name, reset_time)

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result

        except Exception as e:
            self._record_failure(e)

            if fallback:
                return fallback(*args, **kwargs)
            elif self.config.fallback_value is not None:
                return self.config.fallback_value
            raise

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """استخدام كـ decorator."""

        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await self.call(func, *args, **kwargs)

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                return self.call_sync(func, *args, **kwargs)

            return sync_wrapper

    def reset(self) -> None:
        """إعادة تعيين Circuit Breaker."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failures.clear()
            self._successes = 0
            self._last_failure_time = None
            self._opened_at = None

    def force_open(self) -> None:
        """فتح الدائرة قسرياً."""
        with self._lock:
            self._transition_to(CircuitState.OPEN)

    def get_info(self) -> Dict[str, Any]:
        """الحصول على معلومات Circuit Breaker."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": len(self._failures),
                "success_count": self._successes,
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "reset_timeout": self.config.reset_timeout,
                "time_until_reset": self._get_reset_time() if self._state == CircuitState.OPEN else 0,
                "stats": self._stats.to_dict(),
            }


# =============================================================================
# Circuit Breaker Registry
# =============================================================================


class CircuitBreakerRegistry:
    """
    سجل Circuit Breakers.

    يدير مجموعة من Circuit Breakers.
    """

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> CircuitBreaker:
        """الحصول على أو إنشاء Circuit Breaker."""
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """الحصول على Circuit Breaker."""
        return self._breakers.get(name)

    def get_all(self) -> Dict[str, CircuitBreaker]:
        """الحصول على كل Circuit Breakers."""
        return self._breakers.copy()

    def reset_all(self) -> None:
        """إعادة تعيين الكل."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """الحصول على إحصائيات الكل."""
        return {name: breaker.get_info() for name, breaker in self._breakers.items()}


# Global registry
_registry = CircuitBreakerRegistry()


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
) -> CircuitBreaker:
    """الحصول على Circuit Breaker من السجل العام."""
    return _registry.get_or_create(name, config)


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    success_threshold: int = 3,
    timeout: float = 30.0,
    reset_timeout: float = 60.0,
    fallback: Optional[Callable] = None,
):
    """
    Decorator لـ Circuit Breaker.

    الاستخدام:
        @circuit_breaker("my_service", failure_threshold=3)
        async def call_service():
            ...
    """
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout=timeout,
        reset_timeout=reset_timeout,
    )

    cb = get_circuit_breaker(name, config)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await cb.call(func, *args, fallback=fallback, **kwargs)

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                return cb.call_sync(func, *args, fallback=fallback, **kwargs)

            return sync_wrapper

    return decorator


# =============================================================================
# Bulkhead Pattern
# =============================================================================


class Bulkhead:
    """
    نمط Bulkhead للعزل.

    يحد من عدد العمليات المتزامنة لحماية الموارد.
    """

    def __init__(
        self,
        name: str,
        max_concurrent: int = 10,
        max_wait_time: float = 30.0,
    ):
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_wait_time = max_wait_time

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0
        self._waiting = 0
        self._rejected = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """الحصول على إذن."""
        async with self._lock:
            self._waiting += 1

        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.max_wait_time,
            )

            async with self._lock:
                self._waiting -= 1
                self._active += 1

            return True

        except asyncio.TimeoutError:
            async with self._lock:
                self._waiting -= 1
                self._rejected += 1
            return False

    async def release(self) -> None:
        """إطلاق الإذن."""
        async with self._lock:
            self._active -= 1
        self._semaphore.release()

    async def __aenter__(self):
        acquired = await self.acquire()
        if not acquired:
            raise asyncio.TimeoutError(f"Bulkhead '{self.name}' is full")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()
        return False

    def get_stats(self) -> Dict[str, Any]:
        """الحصول على الإحصائيات."""
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "active": self._active,
            "waiting": self._waiting,
            "rejected": self._rejected,
            "available": self.max_concurrent - self._active,
        }


def bulkhead(
    name: str,
    max_concurrent: int = 10,
    max_wait_time: float = 30.0,
):
    """
    Decorator لـ Bulkhead.

    الاستخدام:
        @bulkhead("database", max_concurrent=5)
        async def query_database():
            ...
    """
    bh = Bulkhead(name, max_concurrent, max_wait_time)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with bh:
                return await func(*args, **kwargs)

        return wrapper

    return decorator


# =============================================================================
# Retry with Backoff
# =============================================================================


@dataclass
class RetryConfig:
    """إعدادات المحاولة."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: float = 0.1  # Random jitter factor


class Retry:
    """
    محاولة إعادة مع backoff.
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()

    def _get_delay(self, attempt: int) -> float:
        """حساب وقت الانتظار."""
        import random

        delay = self.config.base_delay * (self.config.exponential_base ** attempt)
        delay = min(delay, self.config.max_delay)

        # Add jitter
        jitter = delay * self.config.jitter * random.uniform(-1, 1)
        return max(0, delay + jitter)

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        retryable_exceptions: Tuple[type, ...] = (Exception,),
        **kwargs,
    ) -> T:
        """تنفيذ مع محاولات إعادة."""
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                return await func(*args, **kwargs)

            except retryable_exceptions as e:
                last_exception = e

                if attempt < self.config.max_retries:
                    delay = self._get_delay(attempt)
                    await asyncio.sleep(delay)
                else:
                    raise

        raise last_exception  # type: ignore[misc]

    def __call__(
        self,
        retryable_exceptions: Tuple[type, ...] = (Exception,),
    ):
        """استخدام كـ decorator."""

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await self.execute(
                    func, *args, retryable_exceptions=retryable_exceptions, **kwargs
                )

            return wrapper

        return decorator


def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    retryable_exceptions: Tuple[type, ...] = (Exception,),
):
    """
    Decorator للمحاولة مع backoff.

    الاستخدام:
        @retry(max_retries=3, base_delay=1.0)
        async def call_api():
            ...
    """
    config = RetryConfig(max_retries=max_retries, base_delay=base_delay)
    retryer = Retry(config)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retryer.execute(
                func, *args, retryable_exceptions=retryable_exceptions, **kwargs
            )

        return wrapper

    return decorator


# =============================================================================
# Combined Resilience
# =============================================================================


class ResiliencePolicy:
    """
    سياسة المرونة المجمعة.

    تجمع بين Circuit Breaker, Bulkhead, و Retry.
    """

    def __init__(
        self,
        name: str,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        max_concurrent: int = 10,
        retry_config: Optional[RetryConfig] = None,
    ):
        self.name = name
        self.circuit_breaker = CircuitBreaker(name, circuit_breaker_config)
        self.bulkhead = Bulkhead(f"{name}_bulkhead", max_concurrent)
        self.retry = Retry(retry_config)

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        fallback: Optional[Callable[..., T]] = None,
        **kwargs,
    ) -> T:
        """تنفيذ مع كل سياسات المرونة."""

        async def protected_call():
            async with self.bulkhead:
                return await self.retry.execute(func, *args, **kwargs)

        return await self.circuit_breaker.call(protected_call, fallback=fallback)

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """استخدام كـ decorator."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.execute(func, *args, **kwargs)

        return wrapper

    def get_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات شاملة."""
        return {
            "circuit_breaker": self.circuit_breaker.get_info(),
            "bulkhead": self.bulkhead.get_stats(),
        }
