"""
Advanced Rate Limiter - محدد المعدل المتقدم
===========================================

نظام تحديد معدل متقدم يدعم:
- Token Bucket Algorithm
- Sliding Window
- Leaky Bucket
- Distributed Rate Limiting
- Per-Key Rate Limiting
- Adaptive Rate Limiting
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import (
    Any,
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


class RateLimitAlgorithm(str, Enum):
    """خوارزمية تحديد المعدل."""

    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"
    LEAKY_BUCKET = "leaky_bucket"


@dataclass
class RateLimitConfig:
    """إعدادات تحديد المعدل."""

    requests_per_second: float = 10.0  # معدل الطلبات في الثانية
    burst_size: int = 20  # الحد الأقصى للدفعة
    window_size: float = 1.0  # حجم النافذة بالثانية
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET


@dataclass
class RateLimitResult:
    """نتيجة فحص تحديد المعدل."""

    allowed: bool
    remaining: int
    reset_at: float  # Unix timestamp
    retry_after: float = 0.0  # ثواني للانتظار
    limit: int = 0
    current: int = 0

    def to_headers(self) -> Dict[str, str]:
        """تحويل إلى HTTP headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_at)),
        }

        if not self.allowed:
            headers["Retry-After"] = str(int(self.retry_after) + 1)

        return headers


class RateLimitExceeded(Exception):
    """استثناء تجاوز حد المعدل."""

    def __init__(self, result: RateLimitResult):
        self.result = result
        super().__init__(
            f"Rate limit exceeded. Retry after {result.retry_after:.1f} seconds."
        )


# =============================================================================
# Rate Limiters
# =============================================================================


class RateLimiter(ABC):
    """واجهة محدد المعدل."""

    @abstractmethod
    def acquire(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة الحصول على tokens."""
        pass

    @abstractmethod
    async def acquire_async(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة الحصول على tokens (غير متزامن)."""
        pass

    @abstractmethod
    def reset(self, key: str = "default") -> None:
        """إعادة تعيين."""
        pass


class TokenBucketLimiter(RateLimiter):
    """
    Token Bucket Rate Limiter.

    الخوارزمية الأكثر شيوعاً:
    - يُملأ الدلو بمعدل ثابت
    - كل طلب يستهلك token
    - إذا كان الدلو فارغاً، يُرفض الطلب
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._buckets: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, key: str) -> Dict[str, Any]:
        """الحصول على الدلو."""
        now = time.time()

        if key not in self._buckets:
            self._buckets[key] = {
                "tokens": float(self.config.burst_size),
                "last_refill": now,
            }
            return self._buckets[key]

        bucket = self._buckets[key]

        # Refill tokens
        elapsed = now - bucket["last_refill"]
        new_tokens = elapsed * self.config.requests_per_second
        bucket["tokens"] = min(
            self.config.burst_size,
            bucket["tokens"] + new_tokens,
        )
        bucket["last_refill"] = now

        return bucket

    def acquire(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة الحصول على tokens."""
        with self._lock:
            bucket = self._get_bucket(key)
            now = time.time()

            if bucket["tokens"] >= tokens:
                bucket["tokens"] -= tokens
                remaining = int(bucket["tokens"])

                return RateLimitResult(
                    allowed=True,
                    remaining=remaining,
                    reset_at=now + (self.config.burst_size - remaining) / self.config.requests_per_second,
                    limit=self.config.burst_size,
                    current=self.config.burst_size - remaining,
                )
            else:
                # Calculate retry time
                needed = tokens - bucket["tokens"]
                retry_after = needed / self.config.requests_per_second

                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_at=now + retry_after,
                    retry_after=retry_after,
                    limit=self.config.burst_size,
                    current=self.config.burst_size,
                )

    async def acquire_async(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة غير متزامنة."""
        return self.acquire(key, tokens)

    def reset(self, key: str = "default") -> None:
        """إعادة تعيين الدلو."""
        with self._lock:
            if key in self._buckets:
                del self._buckets[key]


class SlidingWindowLimiter(RateLimiter):
    """
    Sliding Window Rate Limiter.

    يتتبع الطلبات في نافذة زمنية منزلقة.
    أكثر دقة من Fixed Window لكن يستهلك ذاكرة أكثر.
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._windows: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._max_requests = int(config.requests_per_second * config.window_size)

    def _clean_window(self, key: str, now: float) -> None:
        """تنظيف الطلبات القديمة."""
        cutoff = now - self.config.window_size
        window = self._windows[key]

        while window and window[0] < cutoff:
            window.popleft()

    def acquire(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة الحصول على tokens."""
        with self._lock:
            now = time.time()
            self._clean_window(key, now)

            window = self._windows[key]
            current_count = len(window)

            if current_count + tokens <= self._max_requests:
                # Add requests
                for _ in range(tokens):
                    window.append(now)

                remaining = self._max_requests - len(window)
                reset_at = window[0] + self.config.window_size if window else now + self.config.window_size

                return RateLimitResult(
                    allowed=True,
                    remaining=remaining,
                    reset_at=reset_at,
                    limit=self._max_requests,
                    current=len(window),
                )
            else:
                # Calculate retry time
                if window:
                    retry_after = window[0] + self.config.window_size - now
                else:
                    retry_after = 0

                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_at=now + retry_after,
                    retry_after=max(0, retry_after),
                    limit=self._max_requests,
                    current=len(window),
                )

    async def acquire_async(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة غير متزامنة."""
        return self.acquire(key, tokens)

    def reset(self, key: str = "default") -> None:
        """إعادة تعيين النافذة."""
        with self._lock:
            if key in self._windows:
                self._windows[key].clear()


class FixedWindowLimiter(RateLimiter):
    """
    Fixed Window Rate Limiter.

    يستخدم نوافذ زمنية ثابتة.
    بسيط وفعال لكن يمكن أن يسمح بضعف المعدل عند الحدود.
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._windows: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._max_requests = int(config.requests_per_second * config.window_size)

    def _get_window_key(self, now: float) -> int:
        """الحصول على مفتاح النافذة."""
        return int(now // self.config.window_size)

    def acquire(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة الحصول على tokens."""
        with self._lock:
            now = time.time()
            window_key = self._get_window_key(now)
            full_key = f"{key}:{window_key}"

            if full_key not in self._windows:
                self._windows[full_key] = {"count": 0, "start": now}

                # Clean old windows
                old_threshold = window_key - 2
                keys_to_delete = [
                    k for k in self._windows.keys()
                    if int(k.split(":")[-1]) < old_threshold
                ]
                for k in keys_to_delete:
                    del self._windows[k]

            window = self._windows[full_key]
            reset_at = (window_key + 1) * self.config.window_size

            if window["count"] + tokens <= self._max_requests:
                window["count"] += tokens
                remaining = self._max_requests - window["count"]

                return RateLimitResult(
                    allowed=True,
                    remaining=remaining,
                    reset_at=reset_at,
                    limit=self._max_requests,
                    current=window["count"],
                )
            else:
                retry_after = reset_at - now

                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_at=reset_at,
                    retry_after=retry_after,
                    limit=self._max_requests,
                    current=window["count"],
                )

    async def acquire_async(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة غير متزامنة."""
        return self.acquire(key, tokens)

    def reset(self, key: str = "default") -> None:
        """إعادة تعيين النوافذ."""
        with self._lock:
            keys_to_delete = [k for k in self._windows.keys() if k.startswith(f"{key}:")]
            for k in keys_to_delete:
                del self._windows[k]


class LeakyBucketLimiter(RateLimiter):
    """
    Leaky Bucket Rate Limiter.

    يعالج الطلبات بمعدل ثابت.
    مناسب للتحكم في معدل الإخراج.
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._queues: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _get_queue(self, key: str) -> Dict[str, Any]:
        """الحصول على الطابور."""
        now = time.time()

        if key not in self._queues:
            self._queues[key] = {
                "level": 0.0,
                "last_leak": now,
            }
            return self._queues[key]

        queue = self._queues[key]

        # Leak water
        elapsed = now - queue["last_leak"]
        leaked = elapsed * self.config.requests_per_second
        queue["level"] = max(0, queue["level"] - leaked)
        queue["last_leak"] = now

        return queue

    def acquire(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة الحصول على tokens."""
        with self._lock:
            queue = self._get_queue(key)
            now = time.time()

            if queue["level"] + tokens <= self.config.burst_size:
                queue["level"] += tokens
                remaining = int(self.config.burst_size - queue["level"])

                return RateLimitResult(
                    allowed=True,
                    remaining=remaining,
                    reset_at=now + queue["level"] / self.config.requests_per_second,
                    limit=self.config.burst_size,
                    current=int(queue["level"]),
                )
            else:
                # Calculate wait time
                overflow = queue["level"] + tokens - self.config.burst_size
                retry_after = overflow / self.config.requests_per_second

                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_at=now + retry_after,
                    retry_after=retry_after,
                    limit=self.config.burst_size,
                    current=int(queue["level"]),
                )

    async def acquire_async(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة غير متزامنة."""
        return self.acquire(key, tokens)

    def reset(self, key: str = "default") -> None:
        """إعادة تعيين الطابور."""
        with self._lock:
            if key in self._queues:
                del self._queues[key]


# =============================================================================
# Rate Limiter Factory
# =============================================================================


def create_rate_limiter(config: RateLimitConfig) -> RateLimiter:
    """إنشاء محدد معدل حسب الخوارزمية."""
    if config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
        return TokenBucketLimiter(config)
    elif config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
        return SlidingWindowLimiter(config)
    elif config.algorithm == RateLimitAlgorithm.FIXED_WINDOW:
        return FixedWindowLimiter(config)
    elif config.algorithm == RateLimitAlgorithm.LEAKY_BUCKET:
        return LeakyBucketLimiter(config)
    else:
        return TokenBucketLimiter(config)


# =============================================================================
# Tiered Rate Limiting
# =============================================================================


@dataclass
class TierConfig:
    """إعدادات المستوى."""

    name: str
    requests_per_second: float
    burst_size: int
    priority: int = 0  # الأعلى = أولوية أعلى


class TieredRateLimiter:
    """
    Rate Limiter متعدد المستويات.

    يدعم مستويات مختلفة للمستخدمين:
    - Free tier
    - Pro tier
    - Enterprise tier
    """

    def __init__(self, default_tier: str = "free"):
        self.default_tier = default_tier
        self._tiers: Dict[str, RateLimiter] = {}
        self._user_tiers: Dict[str, str] = {}
        self._lock = threading.Lock()

    def add_tier(self, tier: TierConfig) -> None:
        """إضافة مستوى."""
        config = RateLimitConfig(
            requests_per_second=tier.requests_per_second,
            burst_size=tier.burst_size,
        )
        self._tiers[tier.name] = TokenBucketLimiter(config)

    def set_user_tier(self, user_id: str, tier: str) -> None:
        """تعيين مستوى المستخدم."""
        with self._lock:
            self._user_tiers[user_id] = tier

    def get_user_tier(self, user_id: str) -> str:
        """الحصول على مستوى المستخدم."""
        return self._user_tiers.get(user_id, self.default_tier)

    def acquire(self, user_id: str, tokens: int = 1) -> RateLimitResult:
        """محاولة الحصول على tokens للمستخدم."""
        tier = self.get_user_tier(user_id)

        if tier not in self._tiers:
            tier = self.default_tier

        if tier not in self._tiers:
            return RateLimitResult(
                allowed=True,
                remaining=999,
                reset_at=time.time() + 60,
                limit=999,
                current=0,
            )

        return self._tiers[tier].acquire(user_id, tokens)

    async def acquire_async(self, user_id: str, tokens: int = 1) -> RateLimitResult:
        """محاولة غير متزامنة."""
        return self.acquire(user_id, tokens)


# =============================================================================
# Adaptive Rate Limiting
# =============================================================================


class AdaptiveRateLimiter:
    """
    Rate Limiter تكيفي.

    يعدل المعدل تلقائياً بناءً على:
    - حمل النظام
    - معدل الأخطاء
    - زمن الاستجابة
    """

    def __init__(
        self,
        base_rate: float = 100.0,
        min_rate: float = 10.0,
        max_rate: float = 1000.0,
        adjustment_interval: float = 10.0,
    ):
        self.base_rate = base_rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.adjustment_interval = adjustment_interval

        self._current_rate = base_rate
        self._limiter = TokenBucketLimiter(
            RateLimitConfig(
                requests_per_second=base_rate,
                burst_size=int(base_rate * 2),
            )
        )

        self._success_count = 0
        self._error_count = 0
        self._latency_sum = 0.0
        self._latency_count = 0
        self._last_adjustment = time.time()
        self._lock = threading.Lock()

    def record_success(self, latency: float = 0.0) -> None:
        """تسجيل نجاح."""
        with self._lock:
            self._success_count += 1
            if latency > 0:
                self._latency_sum += latency
                self._latency_count += 1

    def record_error(self) -> None:
        """تسجيل خطأ."""
        with self._lock:
            self._error_count += 1

    def _maybe_adjust(self) -> None:
        """تعديل المعدل إذا لزم الأمر."""
        now = time.time()

        if now - self._last_adjustment < self.adjustment_interval:
            return

        with self._lock:
            total = self._success_count + self._error_count

            if total < 10:
                # Not enough data
                return

            error_rate = self._error_count / total
            avg_latency = self._latency_sum / max(1, self._latency_count)

            # Adjust rate based on metrics
            if error_rate > 0.1:
                # High error rate - decrease
                self._current_rate = max(
                    self.min_rate,
                    self._current_rate * 0.8,
                )
            elif error_rate < 0.01 and avg_latency < 0.1:
                # Low error, low latency - increase
                self._current_rate = min(
                    self.max_rate,
                    self._current_rate * 1.1,
                )

            # Update limiter
            self._limiter = TokenBucketLimiter(
                RateLimitConfig(
                    requests_per_second=self._current_rate,
                    burst_size=int(self._current_rate * 2),
                )
            )

            # Reset counters
            self._success_count = 0
            self._error_count = 0
            self._latency_sum = 0.0
            self._latency_count = 0
            self._last_adjustment = now

    def acquire(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة الحصول على tokens."""
        self._maybe_adjust()
        return self._limiter.acquire(key, tokens)

    async def acquire_async(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة غير متزامنة."""
        return self.acquire(key, tokens)

    def get_current_rate(self) -> float:
        """الحصول على المعدل الحالي."""
        return self._current_rate


# =============================================================================
# Rate Limiter Manager
# =============================================================================


class RateLimiterManager:
    """
    مدير محددات المعدل.

    يدير مجموعة من محددات المعدل للمسارات المختلفة.
    """

    def __init__(self, default_config: Optional[RateLimitConfig] = None):
        self.default_config = default_config or RateLimitConfig()
        self._limiters: Dict[str, RateLimiter] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        name: str,
        config: Optional[RateLimitConfig] = None,
    ) -> RateLimiter:
        """الحصول على أو إنشاء محدد معدل."""
        with self._lock:
            if name not in self._limiters:
                self._limiters[name] = create_rate_limiter(config or self.default_config)
            return self._limiters[name]

    def acquire(
        self,
        name: str,
        key: str = "default",
        tokens: int = 1,
    ) -> RateLimitResult:
        """محاولة الحصول على tokens."""
        limiter = self.get_or_create(name)
        return limiter.acquire(key, tokens)

    def get_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات."""
        return {
            "limiters": list(self._limiters.keys()),
            "count": len(self._limiters),
        }


# Global manager
_manager = RateLimiterManager()


def get_rate_limiter(name: str, config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """الحصول على محدد معدل من المدير العام."""
    return _manager.get_or_create(name, config)


# =============================================================================
# Decorators
# =============================================================================


T = TypeVar("T")


def rate_limit(
    requests_per_second: float = 10.0,
    burst_size: int = 20,
    key_func: Optional[Callable[..., str]] = None,
    on_limited: Optional[Callable[[RateLimitResult], Any]] = None,
):
    """
    Decorator لتحديد المعدل.

    الاستخدام:
        @rate_limit(requests_per_second=5, burst_size=10)
        async def my_endpoint():
            ...

        @rate_limit(key_func=lambda request: request.client.host)
        async def per_ip_endpoint(request):
            ...
    """
    config = RateLimitConfig(
        requests_per_second=requests_per_second,
        burst_size=burst_size,
    )
    limiter = TokenBucketLimiter(config)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        func_name = func.__name__

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = func_name

            result = limiter.acquire(key)

            if not result.allowed:
                if on_limited:
                    return on_limited(result)
                raise RateLimitExceeded(result)

            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Get key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = func_name

            result = limiter.acquire(key)

            if not result.allowed:
                if on_limited:
                    return on_limited(result)
                raise RateLimitExceeded(result)

            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# =============================================================================
# FastAPI Middleware
# =============================================================================


def create_rate_limit_middleware(
    limiter: RateLimiter,
    key_func: Optional[Callable] = None,
):
    """
    إنشاء middleware للـ rate limiting في FastAPI.

    الاستخدام:
        from fastapi import FastAPI
        app = FastAPI()

        limiter = TokenBucketLimiter(RateLimitConfig())
        app.middleware("http")(create_rate_limit_middleware(limiter))
    """

    async def rate_limit_middleware(request, call_next):
        # Get key
        if key_func:
            key = key_func(request)
        else:
            # Default: use client IP
            key = request.client.host if request.client else "unknown"

        result = await limiter.acquire_async(key)

        if not result.allowed:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "retry_after": result.retry_after,
                },
                headers=result.to_headers(),
            )

        response = await call_next(request)

        # Add rate limit headers
        for header, value in result.to_headers().items():
            response.headers[header] = value

        return response

    return rate_limit_middleware


# =============================================================================
# Distributed Rate Limiting (with Redis)
# =============================================================================


class RedisRateLimiter(RateLimiter):
    """
    Rate Limiter موزع باستخدام Redis.

    يدعم تحديد المعدل عبر عدة خوادم.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        config: Optional[RateLimitConfig] = None,
        key_prefix: str = "ratelimit",
    ):
        self.redis_url = redis_url
        self.config = config or RateLimitConfig()
        self.key_prefix = key_prefix
        self._client = None

    async def _get_client(self):
        """الحصول على Redis client."""
        if self._client is None:
            import redis.asyncio as redis

            self._client = redis.from_url(self.redis_url)
        return self._client

    def acquire(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة متزامنة (غير مدعومة للموزع)."""
        raise NotImplementedError("Use acquire_async for distributed rate limiting")

    async def acquire_async(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        """محاولة الحصول على tokens."""
        client = await self._get_client()
        now = time.time()
        redis_key = f"{self.key_prefix}:{key}"

        # Lua script for atomic token bucket
        script = """
        local key = KEYS[1]
        local tokens = tonumber(ARGV[1])
        local rate = tonumber(ARGV[2])
        local burst = tonumber(ARGV[3])
        local now = tonumber(ARGV[4])

        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local current_tokens = tonumber(bucket[1]) or burst
        local last_refill = tonumber(bucket[2]) or now

        -- Refill tokens
        local elapsed = now - last_refill
        local new_tokens = math.min(burst, current_tokens + elapsed * rate)

        if new_tokens >= tokens then
            new_tokens = new_tokens - tokens
            redis.call('HMSET', key, 'tokens', new_tokens, 'last_refill', now)
            redis.call('EXPIRE', key, 3600)
            return {1, new_tokens}
        else
            local needed = tokens - new_tokens
            local retry_after = needed / rate
            return {0, retry_after}
        end
        """

        try:
            result = await client.eval(
                script,
                1,
                redis_key,
                tokens,
                self.config.requests_per_second,
                self.config.burst_size,
                now,
            )

            allowed = result[0] == 1

            if allowed:
                remaining = int(result[1])
                return RateLimitResult(
                    allowed=True,
                    remaining=remaining,
                    reset_at=now + (self.config.burst_size - remaining) / self.config.requests_per_second,
                    limit=self.config.burst_size,
                    current=self.config.burst_size - remaining,
                )
            else:
                retry_after = float(result[1])
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_at=now + retry_after,
                    retry_after=retry_after,
                    limit=self.config.burst_size,
                    current=self.config.burst_size,
                )

        except Exception as e:
            # Fallback: allow if Redis fails
            return RateLimitResult(
                allowed=True,
                remaining=self.config.burst_size,
                reset_at=now + 60,
                limit=self.config.burst_size,
                current=0,
            )

    def reset(self, key: str = "default") -> None:
        """إعادة تعيين (غير متزامن)."""
        pass

    async def reset_async(self, key: str = "default") -> None:
        """إعادة تعيين غير متزامنة."""
        client = await self._get_client()
        redis_key = f"{self.key_prefix}:{key}"
        await client.delete(redis_key)
