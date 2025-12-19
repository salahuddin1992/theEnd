"""
🔔 Notification Channels - قنوات الإشعارات المتقدمة
====================================================

Enterprise-Grade Multi-Channel Notification System
نظام إشعارات متعدد القنوات بمستوى المؤسسات

Channels | القنوات:
- EmailChannel: إرسال بريد إلكتروني عبر SMTP
- SlackChannel: إشعارات Slack
- DiscordChannel: إشعارات Discord
- TelegramChannel: إشعارات Telegram
- WebhookChannel: أي webhook عام
- PagerDutyChannel: تنبيهات PagerDuty
- MicrosoftTeamsChannel: إشعارات MS Teams
- PushoverChannel: إشعارات Pushover
- TwilioSMSChannel: رسائل SMS عبر Twilio
- ConsoleChannel: طباعة للتطوير

Features | الميزات:
- Rate limiting | تحديد معدل الإرسال
- Circuit breaker | قاطع الدائرة للحماية
- Retry with exponential backoff | إعادة المحاولة
- Message templating | قوالب الرسائل
- Priority-based routing | توجيه حسب الأولوية
- Async batching | تجميع غير متزامن
- Health monitoring | مراقبة الصحة
- Metrics collection | جمع المقاييس

Author: Dawood AI Assistant
License: MIT
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
import hmac
import json
import logging
import smtplib
import ssl
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
)

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    import aiofiles  # noqa: F401

    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False

try:
    from jinja2 import BaseLoader, Environment, TemplateError  # noqa: F401

    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════
# 📝 LOGGING SETUP
# ═══════════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 🎯 ENUMS & CONSTANTS
# ═══════════════════════════════════════════════════════════════


class NotificationPriority(str, Enum):
    """
    أولوية الإشعار.
    Notification Priority Levels.
    """

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"
    EMERGENCY = "emergency"  # أعلى مستوى

    @property
    def numeric_value(self) -> int:
        """قيمة رقمية للمقارنة."""
        return {
            self.LOW: 1,
            self.NORMAL: 2,
            self.HIGH: 3,
            self.CRITICAL: 4,
            self.EMERGENCY: 5,
        }.get(self, 2)

    @property
    def color_hex(self) -> str:
        """لون hex للعرض."""
        return {
            self.LOW: "#6c757d",  # رمادي
            self.NORMAL: "#17a2b8",  # أزرق فاتح
            self.HIGH: "#ffc107",  # أصفر
            self.CRITICAL: "#dc3545",  # أحمر
            self.EMERGENCY: "#7b1fa2",  # بنفسجي غامق
        }.get(self, "#17a2b8")

    @property
    def color_int(self) -> int:
        """لون integer للـ Discord."""
        return {
            self.LOW: 0x6C757D,
            self.NORMAL: 0x17A2B8,
            self.HIGH: 0xFFC107,
            self.CRITICAL: 0xDC3545,
            self.EMERGENCY: 0x7B1FA2,
        }.get(self, 0x17A2B8)

    @property
    def emoji(self) -> str:
        """رمز تعبيري."""
        return {
            self.LOW: "ℹ️",
            self.NORMAL: "📢",
            self.HIGH: "⚠️",
            self.CRITICAL: "🚨",
            self.EMERGENCY: "🆘",
        }.get(self, "📢")


class NotificationCategory(str, Enum):
    """تصنيف الإشعار."""

    SYSTEM = "system"
    SECURITY = "security"
    PERFORMANCE = "performance"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    ALERT = "alert"
    AUDIT = "audit"
    DEPLOYMENT = "deployment"
    HEALTH = "health"


class ChannelStatus(str, Enum):
    """حالة القناة."""

    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"
    DISABLED = "disabled"
    RATE_LIMITED = "rate_limited"
    CIRCUIT_OPEN = "circuit_open"


class DeliveryStatus(str, Enum):
    """حالة التسليم."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    EXPIRED = "expired"


# ═══════════════════════════════════════════════════════════════
# 📦 DATA CLASSES
# ═══════════════════════════════════════════════════════════════


@dataclass
class Notification:
    """
    كائن الإشعار الرئيسي.
    Main Notification Object.
    """

    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    category: NotificationCategory = NotificationCategory.INFO
    source: str = "dawood-ai-assistant"
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # بيانات إضافية
    metadata: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    # للتتبع
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    parent_id: Optional[str] = None

    # حالة التسليم
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING
    error: Optional[str] = None
    retry_count: int = 0

    # إعدادات إضافية
    ttl_seconds: Optional[int] = None  # مدة الصلاحية
    dedupe_key: Optional[str] = None  # مفتاح منع التكرار
    target_channels: Optional[List[str]] = None  # قنوات محددة

    # مرفقات
    attachments: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def color(self) -> str:
        """لون الإشعار."""
        return self.priority.color_hex

    @property
    def emoji(self) -> str:
        """رمز الإشعار."""
        return self.priority.emoji

    @property
    def is_expired(self) -> bool:
        """هل انتهت صلاحية الإشعار؟"""
        if self.ttl_seconds is None:
            return False
        return datetime.utcnow() > self.timestamp + timedelta(seconds=self.ttl_seconds)

    @property
    def age_seconds(self) -> float:
        """عمر الإشعار بالثواني."""
        return (datetime.utcnow() - self.timestamp).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس."""
        return {
            "notification_id": self.notification_id,
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value,
            "category": self.category.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "data": self.data,
            "tags": self.tags,
            "correlation_id": self.correlation_id,
            "delivery_status": self.delivery_status.value,
        }

    def to_json(self) -> str:
        """تحويل لـ JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Notification":
        """إنشاء من قاموس."""
        return cls(
            title=data.get("title", ""),
            message=data.get("message", ""),
            priority=NotificationPriority(data.get("priority", "normal")),
            category=NotificationCategory(data.get("category", "info")),
            source=data.get("source", "unknown"),
            notification_id=data.get("notification_id", str(uuid.uuid4())),
            metadata=data.get("metadata", {}),
            data=data.get("data", {}),
            tags=data.get("tags", []),
        )

    def clone(self, **overrides) -> "Notification":
        """نسخ الإشعار مع تعديلات."""
        data = self.to_dict()
        data.update(overrides)
        new_notification = self.from_dict(data)
        new_notification.notification_id = str(uuid.uuid4())
        return new_notification


@dataclass
class DeliveryResult:
    """نتيجة تسليم الإشعار."""

    success: bool
    channel_name: str
    notification_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "channel_name": self.channel_name,
            "notification_id": self.notification_id,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
            "latency_ms": self.latency_ms,
            "retry_count": self.retry_count,
        }


@dataclass
class ChannelMetrics:
    """مقاييس القناة."""

    channel_name: str
    total_sent: int = 0
    total_success: int = 0
    total_failed: int = 0
    total_retries: int = 0
    avg_latency_ms: float = 0.0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_error: Optional[str] = None

    # نافذة زمنية
    success_rate_1h: float = 0.0
    success_rate_24h: float = 0.0

    @property
    def success_rate(self) -> float:
        """معدل النجاح."""
        if self.total_sent == 0:
            return 0.0
        return (self.total_success / self.total_sent) * 100


@dataclass
class RateLimitConfig:
    """إعدادات تحديد المعدل."""

    max_requests: int = 100
    window_seconds: int = 60
    burst_limit: int = 10
    cooldown_seconds: int = 30


@dataclass
class CircuitBreakerConfig:
    """إعدادات قاطع الدائرة."""

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: int = 60
    half_open_max_calls: int = 3


@dataclass
class RetryConfig:
    """إعدادات إعادة المحاولة."""

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


# ═══════════════════════════════════════════════════════════════
# 🛡️ RATE LIMITER
# ═══════════════════════════════════════════════════════════════


class RateLimiter:
    """
    محدد المعدل المتقدم.
    Advanced Rate Limiter with Sliding Window.
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._requests: List[float] = []
        self._lock = asyncio.Lock()
        self._cooldown_until: Optional[float] = None

    async def acquire(self) -> bool:
        """محاولة الحصول على إذن."""
        async with self._lock:
            now = time.time()

            # تحقق من cooldown
            if self._cooldown_until and now < self._cooldown_until:
                return False

            # تنظيف الطلبات القديمة
            cutoff = now - self.config.window_seconds
            self._requests = [t for t in self._requests if t > cutoff]

            # تحقق من الحد
            if len(self._requests) >= self.config.max_requests:
                return False

            # تحقق من burst
            recent_cutoff = now - 1.0  # آخر ثانية
            recent_count = sum(1 for t in self._requests if t > recent_cutoff)
            if recent_count >= self.config.burst_limit:
                return False

            self._requests.append(now)
            return True

    async def wait_and_acquire(self, timeout: float = 30.0) -> bool:
        """انتظار والحصول على إذن."""
        start = time.time()
        while time.time() - start < timeout:
            if await self.acquire():
                return True
            await asyncio.sleep(0.1)
        return False

    def trigger_cooldown(self) -> None:
        """تفعيل فترة التبريد."""
        self._cooldown_until = time.time() + self.config.cooldown_seconds

    @property
    def current_usage(self) -> int:
        """الاستخدام الحالي."""
        now = time.time()
        cutoff = now - self.config.window_seconds
        return sum(1 for t in self._requests if t > cutoff)

    @property
    def remaining(self) -> int:
        """المتبقي."""
        return max(0, self.config.max_requests - self.current_usage)


# ═══════════════════════════════════════════════════════════════
# ⚡ CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════════


class CircuitState(Enum):
    """حالات قاطع الدائرة."""

    CLOSED = auto()  # طبيعي
    OPEN = auto()  # مفتوح (يمنع الطلبات)
    HALF_OPEN = auto()  # نصف مفتوح (اختبار)


class CircuitBreaker:
    """
    قاطع الدائرة للحماية من الفشل المتتالي.
    Circuit Breaker Pattern Implementation.
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """الحالة الحالية."""
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    async def can_execute(self) -> bool:
        """هل يمكن تنفيذ الطلب؟"""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # تحقق من انتهاء المهلة
                if self._last_failure_time:
                    elapsed = time.time() - self._last_failure_time
                    if elapsed >= self.config.timeout_seconds:
                        self._state = CircuitState.HALF_OPEN
                        self._half_open_calls = 0
                        return True
                return False

            # HALF_OPEN
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    async def record_success(self) -> None:
        """تسجيل نجاح."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    async def record_failure(self) -> None:
        """تسجيل فشل."""
        async with self._lock:
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN

    async def reset(self) -> None:
        """إعادة تعيين."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None


# ═══════════════════════════════════════════════════════════════
# 🔄 RETRY HANDLER
# ═══════════════════════════════════════════════════════════════


class RetryHandler:
    """
    معالج إعادة المحاولة.
    Retry Handler with Exponential Backoff.
    """

    def __init__(self, config: RetryConfig):
        self.config = config

    def get_delay(self, attempt: int) -> float:
        """حساب فترة الانتظار."""
        import random

        delay = self.config.base_delay_seconds * (self.config.exponential_base**attempt)
        delay = min(delay, self.config.max_delay_seconds)

        if self.config.jitter:
            delay *= 0.5 + random.random()

        return delay

    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Tuple[bool, Any, int]:
        """
        تنفيذ مع إعادة المحاولة.
        Returns: (success, result, attempts)
        """
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                return True, result, attempt + 1
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1}/{self.config.max_retries + 1} failed: {e}")

                if attempt < self.config.max_retries:
                    delay = self.get_delay(attempt)
                    await asyncio.sleep(delay)

        return False, last_error, self.config.max_retries + 1


# ═══════════════════════════════════════════════════════════════
# 📧 BASE CHANNEL CLASS
# ═══════════════════════════════════════════════════════════════


class NotificationChannel(abc.ABC):
    """
    قناة الإشعارات الأساسية.
    Abstract Base Notification Channel.
    """

    def __init__(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        retry_config: Optional[RetryConfig] = None,
    ):
        self.name = name
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self._status = ChannelStatus.ACTIVE

        # مكونات المرونة
        self._rate_limiter = RateLimiter(rate_limit_config or RateLimitConfig())
        self._circuit_breaker = CircuitBreaker(circuit_breaker_config or CircuitBreakerConfig())
        self._retry_handler = RetryHandler(retry_config or RetryConfig())

        # مقاييس
        self._metrics = ChannelMetrics(channel_name=name)
        self._latencies: List[float] = []

        # فلترة
        self._min_priority = NotificationPriority(self.config.get("min_priority", "low"))
        self._allowed_categories: Optional[Set[NotificationCategory]] = None
        if "allowed_categories" in self.config:
            self._allowed_categories = {NotificationCategory(c) for c in self.config["allowed_categories"]}

    @property
    def status(self) -> ChannelStatus:
        """حالة القناة."""
        if not self.enabled:
            return ChannelStatus.DISABLED
        if self._circuit_breaker.is_open:
            return ChannelStatus.CIRCUIT_OPEN
        if self._rate_limiter.remaining == 0:
            return ChannelStatus.RATE_LIMITED
        return self._status

    @property
    def metrics(self) -> ChannelMetrics:
        """مقاييس القناة."""
        return self._metrics

    def should_send(self, notification: Notification) -> bool:
        """هل يجب إرسال هذا الإشعار؟"""
        if not self.enabled:
            return False

        if notification.priority.numeric_value < self._min_priority.numeric_value:
            return False

        if self._allowed_categories:
            if notification.category not in self._allowed_categories:
                return False

        if notification.target_channels:
            if self.name not in notification.target_channels:
                return False

        return True

    async def send_notification(self, notification: Notification) -> DeliveryResult:
        """
        إرسال إشعار مع كل الحمايات.
        Send notification with all protections.
        """
        start_time = time.time()

        # تحقق من الفلاتر
        if not self.should_send(notification):
            return DeliveryResult(
                success=False,
                channel_name=self.name,
                notification_id=notification.notification_id,
                error="Filtered out",
            )

        # تحقق من قاطع الدائرة
        if not await self._circuit_breaker.can_execute():
            return DeliveryResult(
                success=False,
                channel_name=self.name,
                notification_id=notification.notification_id,
                error="Circuit breaker open",
            )

        # تحقق من محدد المعدل
        if not await self._rate_limiter.acquire():
            return DeliveryResult(
                success=False,
                channel_name=self.name,
                notification_id=notification.notification_id,
                error="Rate limited",
            )

        # محاولة الإرسال مع إعادة المحاولة
        success, result, attempts = await self._retry_handler.execute_with_retry(self._do_send, notification)

        latency_ms = (time.time() - start_time) * 1000

        # تحديث المقاييس
        self._metrics.total_sent += 1
        if success:
            self._metrics.total_success += 1
            self._metrics.last_success = datetime.utcnow()
            await self._circuit_breaker.record_success()
        else:
            self._metrics.total_failed += 1
            self._metrics.last_failure = datetime.utcnow()
            self._metrics.last_error = str(result)
            await self._circuit_breaker.record_failure()

        self._metrics.total_retries += max(0, attempts - 1)
        self._latencies.append(latency_ms)
        if len(self._latencies) > 100:
            self._latencies = self._latencies[-100:]
        self._metrics.avg_latency_ms = sum(self._latencies) / len(self._latencies)

        return DeliveryResult(
            success=success,
            channel_name=self.name,
            notification_id=notification.notification_id,
            error=str(result) if not success else None,
            latency_ms=latency_ms,
            retry_count=attempts - 1,
        )

    @abc.abstractmethod
    async def _do_send(self, notification: Notification) -> bool:
        """
        الإرسال الفعلي - يجب تنفيذه في الفئات الفرعية.
        Actual send implementation - must be overridden.
        """
        pass

    async def test_connection(self) -> bool:
        """اختبار الاتصال."""
        return True

    async def health_check(self) -> Dict[str, Any]:
        """فحص صحة القناة."""
        return {
            "name": self.name,
            "status": self.status.value,
            "enabled": self.enabled,
            "circuit_breaker_state": self._circuit_breaker.state.name,
            "rate_limit_remaining": self._rate_limiter.remaining,
            "metrics": {
                "total_sent": self._metrics.total_sent,
                "success_rate": self._metrics.success_rate,
                "avg_latency_ms": self._metrics.avg_latency_ms,
            },
        }


# ═══════════════════════════════════════════════════════════════
# 📺 CONSOLE CHANNEL
# ═══════════════════════════════════════════════════════════════


class ConsoleChannel(NotificationChannel):
    """
    قناة الـ Console للتطوير.
    Console Channel for Development.
    """

    def __init__(
        self,
        name: str = "console",
        config: Optional[Dict[str, Any]] = None,
        colored: bool = True,
        show_metadata: bool = False,
    ):
        super().__init__(name, config)
        self.colored = colored
        self.show_metadata = show_metadata

    async def _do_send(self, notification: Notification) -> bool:
        """طباعة الإشعار."""
        if self.colored:
            color_codes = {
                NotificationPriority.LOW: "\033[90m",  # رمادي
                NotificationPriority.NORMAL: "\033[94m",  # أزرق
                NotificationPriority.HIGH: "\033[93m",  # أصفر
                NotificationPriority.CRITICAL: "\033[91m",  # أحمر
                NotificationPriority.EMERGENCY: "\033[95m",  # بنفسجي
            }
            reset = "\033[0m"
            bold = "\033[1m"
            color = color_codes.get(notification.priority, reset)
        else:
            color = reset = bold = ""

        output = f"""
{color}{bold}{'═' * 60}{reset}
{color}{notification.emoji} [{notification.priority.value.upper()}] {notification.title}{reset}
{color}{'─' * 60}{reset}
{notification.message}

{color}📂 Category:{reset} {notification.category.value}
{color}🕐 Time:{reset} {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
{color}🔗 Source:{reset} {notification.source}
{color}🆔 ID:{reset} {notification.notification_id}
"""
        if self.show_metadata and notification.metadata:
            output += f"\n{color}📋 Metadata:{reset}\n"
            for key, value in notification.metadata.items():
                output += f"   • {key}: {value}\n"

        if notification.tags:
            output += f"\n{color}🏷️ Tags:{reset} {', '.join(notification.tags)}\n"

        output += f"{color}{'═' * 60}{reset}\n"

        print(output)
        return True


# ═══════════════════════════════════════════════════════════════
# 📧 EMAIL CHANNEL
# ═══════════════════════════════════════════════════════════════


@dataclass
class EmailConfig:
    """إعدادات البريد الإلكتروني."""

    smtp_host: str = "localhost"
    smtp_port: int = 587
    username: Optional[str] = None
    password: Optional[str] = None
    from_email: str = "noreply@dawood-ai.local"
    from_name: str = "Dawood AI Assistant"
    use_tls: bool = True
    use_ssl: bool = False
    timeout: int = 30

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmailConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class EmailChannel(NotificationChannel):
    """
    قناة البريد الإلكتروني.
    Email Notification Channel via SMTP.
    """

    def __init__(
        self,
        name: str = "email",
        config: Optional[Dict[str, Any]] = None,
        email_config: Optional[EmailConfig] = None,
        recipients: Optional[List[str]] = None,
    ):
        super().__init__(name, config)

        if email_config:
            self.email_config = email_config
        elif config:
            self.email_config = EmailConfig.from_dict(config)
        else:
            self.email_config = EmailConfig()

        self.recipients = recipients or config.get("recipients", []) if config else []

    async def _do_send(self, notification: Notification) -> bool:
        """إرسال بريد إلكتروني."""
        if not self.recipients:
            raise ValueError("No recipients configured")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._send_email_sync, notification)

    def _send_email_sync(self, notification: Notification) -> bool:
        """إرسال البريد بشكل متزامن."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{notification.priority.value.upper()}] {notification.title}"
        msg["From"] = f"{self.email_config.from_name} <{self.email_config.from_email}>"
        msg["To"] = ", ".join(self.recipients)
        msg["X-Priority"] = str(6 - notification.priority.numeric_value)

        # نص عادي
        text_content = self._build_text_content(notification)

        # HTML
        html_content = self._build_html_content(notification)

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # إرسال
        if self.email_config.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(
                self.email_config.smtp_host,
                self.email_config.smtp_port,
                timeout=self.email_config.timeout,
                context=context,
            )
        else:
            server = smtplib.SMTP(
                self.email_config.smtp_host,
                self.email_config.smtp_port,
                timeout=self.email_config.timeout,
            )
            if self.email_config.use_tls:
                server.starttls()

        try:
            if self.email_config.username and self.email_config.password:
                server.login(self.email_config.username, self.email_config.password)
            server.send_message(msg)
            return True
        finally:
            server.quit()

    def _build_text_content(self, notification: Notification) -> str:
        """بناء محتوى نصي."""
        return f"""
{notification.emoji} {notification.title}
{'=' * len(notification.title)}

{notification.message}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Details
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Priority: {notification.priority.value}
Category: {notification.category.value}
Time: {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
Source: {notification.source}
ID: {notification.notification_id}

---
🤖 Dawood AI Assistant
Notification System
        """.strip()

    def _build_html_content(self, notification: Notification) -> str:
        """بناء محتوى HTML."""
        return f"""
<!DOCTYPE html>
<html dir="auto">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: {notification.priority.color_hex};
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 24px;
            margin-bottom: 10px;
        }}
        .header .emoji {{
            font-size: 48px;
            margin-bottom: 15px;
        }}
        .priority-badge {{
            display: inline-block;
            background: rgba(255,255,255,0.2);
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .content {{
            padding: 30px;
        }}
        .message {{
            font-size: 16px;
            line-height: 1.6;
            color: #333;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            border-left: 4px solid {notification.priority.color_hex};
        }}
        .meta {{
            margin-top: 25px;
            padding: 20px;
            background: #f1f3f4;
            border-radius: 10px;
        }}
        .meta-item {{
            display: flex;
            align-items: center;
            margin-bottom: 10px;
            font-size: 14px;
            color: #5f6368;
        }}
        .meta-item:last-child {{
            margin-bottom: 0;
        }}
        .meta-item strong {{
            min-width: 100px;
            color: #202124;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px 30px;
            text-align: center;
            font-size: 12px;
            color: #6c757d;
            border-top: 1px solid #e9ecef;
        }}
        .footer .logo {{
            font-weight: bold;
            color: #667eea;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="emoji">{notification.emoji}</div>
            <h1>{notification.title}</h1>
            <span class="priority-badge">{notification.priority.value} Priority</span>
        </div>
        <div class="content">
            <div class="message">
                {notification.message}
            </div>
            <div class="meta">
                <div class="meta-item">
                    <strong>📂 Category:</strong>
                    <span>{notification.category.value}</span>
                </div>
                <div class="meta-item">
                    <strong>🕐 Time:</strong>
                    <span>{notification.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</span>
                </div>
                <div class="meta-item">
                    <strong>🔗 Source:</strong>
                    <span>{notification.source}</span>
                </div>
                <div class="meta-item">
                    <strong>🆔 ID:</strong>
                    <span style="font-family: monospace; font-size: 12px;">{notification.notification_id}</span>
                </div>
            </div>
        </div>
        <div class="footer">
            <span class="logo">🤖 Dawood AI Assistant</span><br>
            Enterprise Notification System
        </div>
    </div>
</body>
</html>
        """

    async def test_connection(self) -> bool:
        """اختبار اتصال SMTP."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._test_smtp_sync)
        except Exception as e:
            logger.error(f"SMTP test failed: {e}")
            return False

    def _test_smtp_sync(self) -> bool:
        """اختبار SMTP متزامن."""
        if self.email_config.use_ssl:
            server = smtplib.SMTP_SSL(
                self.email_config.smtp_host,
                self.email_config.smtp_port,
                timeout=10,
            )
        else:
            server = smtplib.SMTP(
                self.email_config.smtp_host,
                self.email_config.smtp_port,
                timeout=10,
            )
            if self.email_config.use_tls:
                server.starttls()

        try:
            if self.email_config.username and self.email_config.password:
                server.login(self.email_config.username, self.email_config.password)
            return True
        finally:
            server.quit()


# ═══════════════════════════════════════════════════════════════
# 💬 SLACK CHANNEL
# ═══════════════════════════════════════════════════════════════


class SlackChannel(NotificationChannel):
    """
    قناة Slack.
    Slack Notification Channel via Webhook.
    """

    def __init__(
        self,
        name: str = "slack",
        config: Optional[Dict[str, Any]] = None,
        webhook_url: str = "",
        channel: Optional[str] = None,
        username: str = "Dawood AI Bot",
        icon_emoji: str = ":robot_face:",
    ):
        super().__init__(name, config)
        self.webhook_url = webhook_url or (config.get("webhook_url", "") if config else "")
        self.channel = channel or (config.get("channel") if config else None)
        self.username = username
        self.icon_emoji = icon_emoji

    async def _do_send(self, notification: Notification) -> bool:
        """إرسال لـ Slack."""
        if not self.webhook_url:
            raise ValueError("Slack webhook URL not configured")

        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx library is required for Slack notifications")

        payload = self._build_payload(notification)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.status_code == 200

    def _build_payload(self, notification: Notification) -> Dict[str, Any]:
        """بناء payload لـ Slack."""
        payload = {
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "attachments": [
                {
                    "color": notification.priority.color_hex,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"{notification.emoji} {notification.title}",
                                "emoji": True,
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": notification.message,
                            },
                        },
                        {
                            "type": "divider",
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Priority:* {notification.priority.value} | "
                                    f"*Category:* {notification.category.value} | "
                                    f"*Source:* {notification.source}",
                                },
                            ],
                        },
                    ],
                    "fallback": f"[{notification.priority.value}] {notification.title}: {notification.message}",
                    "footer": "Dawood AI Assistant",
                    "ts": int(notification.timestamp.timestamp()),
                },
            ],
        }

        if self.channel:
            payload["channel"] = self.channel

        # إضافة حقول البيانات
        if notification.data:
            fields_block = {
                "type": "section",
                "fields": [{"type": "mrkdwn", "text": f"*{k}:*\n{v}"} for k, v in list(notification.data.items())[:10]],
            }
            payload["attachments"][0]["blocks"].insert(-1, fields_block)

        return payload

    async def test_connection(self) -> bool:
        """اختبار webhook."""
        if not self.webhook_url or not HTTPX_AVAILABLE:
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={"text": "🔔 Test notification from Dawood AI Assistant"},
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# 🎮 DISCORD CHANNEL
# ═══════════════════════════════════════════════════════════════


class DiscordChannel(NotificationChannel):
    """
    قناة Discord.
    Discord Notification Channel via Webhook.
    """

    def __init__(
        self,
        name: str = "discord",
        config: Optional[Dict[str, Any]] = None,
        webhook_url: str = "",
        username: str = "Dawood AI Bot",
        avatar_url: Optional[str] = None,
    ):
        super().__init__(name, config)
        self.webhook_url = webhook_url or (config.get("webhook_url", "") if config else "")
        self.username = username
        self.avatar_url = avatar_url

    async def _do_send(self, notification: Notification) -> bool:
        """إرسال لـ Discord."""
        if not self.webhook_url:
            raise ValueError("Discord webhook URL not configured")

        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx library is required for Discord notifications")

        payload = self._build_payload(notification)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                json=payload,
                timeout=30.0,
            )
            return response.status_code in (200, 204)

    def _build_payload(self, notification: Notification) -> Dict[str, Any]:
        """بناء payload لـ Discord."""
        embed = {
            "title": f"{notification.emoji} {notification.title}",
            "description": notification.message,
            "color": notification.priority.color_int,
            "timestamp": notification.timestamp.isoformat(),
            "footer": {
                "text": f"Dawood AI Assistant | {notification.category.value}",
            },
            "fields": [
                {
                    "name": "🎯 Priority",
                    "value": notification.priority.value.upper(),
                    "inline": True,
                },
                {
                    "name": "🔗 Source",
                    "value": notification.source,
                    "inline": True,
                },
            ],
        }

        # إضافة حقول البيانات
        if notification.data:
            for key, value in list(notification.data.items())[:6]:
                embed["fields"].append(
                    {
                        "name": key,
                        "value": str(value)[:1024],
                        "inline": True,
                    }
                )

        payload = {
            "username": self.username,
            "embeds": [embed],
        }

        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url

        return payload


# ═══════════════════════════════════════════════════════════════
# 📱 TELEGRAM CHANNEL
# ═══════════════════════════════════════════════════════════════


class TelegramChannel(NotificationChannel):
    """
    قناة Telegram.
    Telegram Notification Channel via Bot API.
    """

    API_BASE = "https://api.telegram.org/bot"

    def __init__(
        self,
        name: str = "telegram",
        config: Optional[Dict[str, Any]] = None,
        bot_token: str = "",
        chat_id: str = "",
        parse_mode: str = "HTML",
        disable_notification: bool = False,
    ):
        super().__init__(name, config)
        self.bot_token = bot_token or (config.get("bot_token", "") if config else "")
        self.chat_id = chat_id or (config.get("chat_id", "") if config else "")
        self.parse_mode = parse_mode
        self.disable_notification = disable_notification

    @property
    def api_url(self) -> str:
        return f"{self.API_BASE}{self.bot_token}"

    async def _do_send(self, notification: Notification) -> bool:
        """إرسال لـ Telegram."""
        if not self.bot_token or not self.chat_id:
            raise ValueError("Telegram bot_token and chat_id are required")

        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx library is required for Telegram notifications")

        text = self._format_message(notification)

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": self.parse_mode,
            "disable_notification": self.disable_notification and notification.priority.numeric_value < 3,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/sendMessage",
                json=payload,
                timeout=30.0,
            )
            return response.status_code == 200

    def _format_message(self, notification: Notification) -> str:
        """تنسيق الرسالة."""
        if self.parse_mode == "HTML":
            return f"""
{notification.emoji} <b>{notification.title}</b>

{notification.message}

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Priority:</b> <code>{notification.priority.value}</code>
📂 <b>Category:</b> <code>{notification.category.value}</code>
🔗 <b>Source:</b> <code>{notification.source}</code>
🕐 <b>Time:</b> <code>{notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</code>

🤖 <i>Dawood AI Assistant</i>
            """.strip()
        else:
            return f"""
{notification.emoji} *{notification.title}*

{notification.message}

━━━━━━━━━━━━━━━━━━━━━
📊 *Priority:* `{notification.priority.value}`
📂 *Category:* `{notification.category.value}`
🔗 *Source:* `{notification.source}`

🤖 _Dawood AI Assistant_
            """.strip()

    async def test_connection(self) -> bool:
        """اختبار Bot."""
        if not self.bot_token or not HTTPX_AVAILABLE:
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/getMe",
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
# 🔗 WEBHOOK CHANNEL
# ═══════════════════════════════════════════════════════════════


class WebhookChannel(NotificationChannel):
    """
    قناة Webhook عامة.
    Generic Webhook Notification Channel.
    """

    def __init__(
        self,
        name: str = "webhook",
        config: Optional[Dict[str, Any]] = None,
        url: str = "",
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        secret: Optional[str] = None,
        timeout: float = 30.0,
    ):
        super().__init__(name, config)
        self.url = url or (config.get("url", "") if config else "")
        self.method = method.upper()
        self.headers = headers or (config.get("headers", {}) if config else {})
        self.secret = secret or (config.get("secret") if config else None)
        self.timeout = timeout

    async def _do_send(self, notification: Notification) -> bool:
        """إرسال webhook."""
        if not self.url:
            raise ValueError("Webhook URL not configured")

        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx library is required for webhook notifications")

        payload = notification.to_dict()
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DawoodAI-NotificationSystem/1.0",
            "X-Notification-ID": notification.notification_id,
            "X-Notification-Priority": notification.priority.value,
            **self.headers,
        }

        # توقيع HMAC إذا تم تكوينه
        if self.secret:
            signature = hmac.new(
                self.secret.encode(),
                payload_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Signature-256"] = f"sha256={signature}"
            headers["X-Hub-Signature-256"] = f"sha256={signature}"

        async with httpx.AsyncClient() as client:
            if self.method == "POST":
                response = await client.post(
                    self.url,
                    content=payload_bytes,
                    headers=headers,
                    timeout=self.timeout,
                )
            elif self.method == "PUT":
                response = await client.put(
                    self.url,
                    content=payload_bytes,
                    headers=headers,
                    timeout=self.timeout,
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {self.method}")

            return response.status_code < 400


# ═══════════════════════════════════════════════════════════════
# 🚨 PAGERDUTY CHANNEL
# ═══════════════════════════════════════════════════════════════


class PagerDutyChannel(NotificationChannel):
    """
    قناة PagerDuty.
    PagerDuty Events API v2 Integration.
    """

    EVENTS_API = "https://events.pagerduty.com/v2/enqueue"

    def __init__(
        self,
        name: str = "pagerduty",
        config: Optional[Dict[str, Any]] = None,
        routing_key: str = "",
        service_name: str = "Dawood AI Assistant",
    ):
        super().__init__(name, config)
        self.routing_key = routing_key or (config.get("routing_key", "") if config else "")
        self.service_name = service_name

    async def _do_send(self, notification: Notification) -> bool:
        """إرسال حدث PagerDuty."""
        if not self.routing_key:
            raise ValueError("PagerDuty routing key not configured")

        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx library is required for PagerDuty notifications")

        severity = {
            NotificationPriority.LOW: "info",
            NotificationPriority.NORMAL: "warning",
            NotificationPriority.HIGH: "error",
            NotificationPriority.CRITICAL: "critical",
            NotificationPriority.EMERGENCY: "critical",
        }.get(notification.priority, "warning")

        payload = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "dedup_key": notification.dedupe_key or notification.notification_id,
            "payload": {
                "summary": f"[{notification.category.value}] {notification.title}",
                "source": notification.source,
                "severity": severity,
                "timestamp": notification.timestamp.isoformat(),
                "component": self.service_name,
                "group": notification.category.value,
                "class": notification.priority.value,
                "custom_details": {
                    "message": notification.message,
                    "notification_id": notification.notification_id,
                    **notification.metadata,
                    **notification.data,
                },
            },
            "links": [
                {
                    "href": f"https://dawood-ai.local/notifications/{notification.notification_id}",
                    "text": "View Notification Details",
                },
            ],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.EVENTS_API,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            return True


# ═══════════════════════════════════════════════════════════════
# 👥 MICROSOFT TEAMS CHANNEL
# ═══════════════════════════════════════════════════════════════


class MicrosoftTeamsChannel(NotificationChannel):
    """
    قناة Microsoft Teams.
    Microsoft Teams Webhook Integration.
    """

    def __init__(
        self,
        name: str = "teams",
        config: Optional[Dict[str, Any]] = None,
        webhook_url: str = "",
    ):
        super().__init__(name, config)
        self.webhook_url = webhook_url or (config.get("webhook_url", "") if config else "")

    async def _do_send(self, notification: Notification) -> bool:
        """إرسال لـ MS Teams."""
        if not self.webhook_url:
            raise ValueError("Teams webhook URL not configured")

        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx library is required for Teams notifications")

        payload = self._build_adaptive_card(notification)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                json=payload,
                timeout=30.0,
            )
            return response.status_code == 200

    def _build_adaptive_card(self, notification: Notification) -> Dict[str, Any]:
        """بناء Adaptive Card لـ Teams."""
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "Container",
                                "style": "emphasis",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": f"{notification.emoji} {notification.title}",
                                        "weight": "Bolder",
                                        "size": "Large",
                                        "wrap": True,
                                    },
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": notification.message,
                                "wrap": True,
                                "spacing": "Medium",
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Priority", "value": notification.priority.value.upper()},
                                    {"title": "Category", "value": notification.category.value},
                                    {"title": "Source", "value": notification.source},
                                    {"title": "Time", "value": notification.timestamp.strftime("%Y-%m-%d %H:%M:%S")},
                                ],
                            },
                        ],
                        "actions": [
                            {
                                "type": "Action.OpenUrl",
                                "title": "View Details",
                                "url": f"https://dawood-ai.local/notifications/{notification.notification_id}",
                            },
                        ],
                    },
                },
            ],
        }


# ═══════════════════════════════════════════════════════════════
# 📲 PUSHOVER CHANNEL
# ═══════════════════════════════════════════════════════════════


class PushoverChannel(NotificationChannel):
    """
    قناة Pushover.
    Pushover Push Notification Service.
    """

    API_URL = "https://api.pushover.net/1/messages.json"

    def __init__(
        self,
        name: str = "pushover",
        config: Optional[Dict[str, Any]] = None,
        api_token: str = "",
        user_key: str = "",
        device: Optional[str] = None,
    ):
        super().__init__(name, config)
        self.api_token = api_token or (config.get("api_token", "") if config else "")
        self.user_key = user_key or (config.get("user_key", "") if config else "")
        self.device = device

    async def _do_send(self, notification: Notification) -> bool:
        """إرسال لـ Pushover."""
        if not self.api_token or not self.user_key:
            raise ValueError("Pushover api_token and user_key are required")

        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx library is required for Pushover notifications")

        # تحويل الأولوية لصيغة Pushover
        priority = {
            NotificationPriority.LOW: -1,
            NotificationPriority.NORMAL: 0,
            NotificationPriority.HIGH: 1,
            NotificationPriority.CRITICAL: 2,
            NotificationPriority.EMERGENCY: 2,
        }.get(notification.priority, 0)

        payload = {
            "token": self.api_token,
            "user": self.user_key,
            "title": notification.title,
            "message": notification.message,
            "priority": priority,
            "timestamp": int(notification.timestamp.timestamp()),
        }

        if priority == 2:
            payload["retry"] = 60
            payload["expire"] = 3600

        if self.device:
            payload["device"] = self.device

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.API_URL,
                data=payload,
                timeout=30.0,
            )
            return response.status_code == 200


# ═══════════════════════════════════════════════════════════════
# 📱 TWILIO SMS CHANNEL
# ═══════════════════════════════════════════════════════════════


class TwilioSMSChannel(NotificationChannel):
    """
    قناة Twilio SMS.
    Twilio SMS Notification Channel.
    """

    API_BASE = "https://api.twilio.com/2010-04-01/Accounts"

    def __init__(
        self,
        name: str = "twilio_sms",
        config: Optional[Dict[str, Any]] = None,
        account_sid: str = "",
        auth_token: str = "",
        from_number: str = "",
        to_numbers: Optional[List[str]] = None,
    ):
        super().__init__(name, config)
        self.account_sid = account_sid or (config.get("account_sid", "") if config else "")
        self.auth_token = auth_token or (config.get("auth_token", "") if config else "")
        self.from_number = from_number or (config.get("from_number", "") if config else "")
        self.to_numbers = to_numbers or (config.get("to_numbers", []) if config else [])

    async def _do_send(self, notification: Notification) -> bool:
        """إرسال SMS عبر Twilio."""
        if not all([self.account_sid, self.auth_token, self.from_number, self.to_numbers]):
            raise ValueError("Twilio configuration incomplete")

        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx library is required for Twilio notifications")

        # تقصير الرسالة لـ SMS
        message = f"[{notification.priority.value.upper()}] {notification.title}\n{notification.message}"
        if len(message) > 1600:
            message = message[:1597] + "..."

        url = f"{self.API_BASE}/{self.account_sid}/Messages.json"

        async with httpx.AsyncClient() as client:
            for to_number in self.to_numbers:
                response = await client.post(
                    url,
                    auth=(self.account_sid, self.auth_token),
                    data={
                        "From": self.from_number,
                        "To": to_number,
                        "Body": message,
                    },
                    timeout=30.0,
                )
                if response.status_code not in (200, 201):
                    logger.error(f"Failed to send SMS to {to_number}")

        return True


# ═══════════════════════════════════════════════════════════════
# 🎛️ NOTIFICATION MANAGER
# ═══════════════════════════════════════════════════════════════


class NotificationManager:
    """
    مدير الإشعارات الرئيسي.
    Main Notification Manager with Multi-Channel Support.
    """

    def __init__(self):
        self._channels: Dict[str, NotificationChannel] = {}
        self._default_channels: List[str] = []
        self._notification_history: List[Notification] = []
        self._max_history = 1000
        self._dedupe_cache: Dict[str, datetime] = {}
        self._dedupe_window = timedelta(minutes=5)
        self._lock = asyncio.Lock()

    def register_channel(
        self,
        channel: NotificationChannel,
        is_default: bool = True,
    ) -> None:
        """تسجيل قناة."""
        self._channels[channel.name] = channel
        if is_default and channel.name not in self._default_channels:
            self._default_channels.append(channel.name)
        logger.info(f"Registered notification channel: {channel.name}")

    def unregister_channel(self, name: str) -> None:
        """إلغاء تسجيل قناة."""
        if name in self._channels:
            del self._channels[name]
        if name in self._default_channels:
            self._default_channels.remove(name)

    def get_channel(self, name: str) -> Optional[NotificationChannel]:
        """الحصول على قناة."""
        return self._channels.get(name)

    @property
    def channels(self) -> Dict[str, NotificationChannel]:
        """جميع القنوات."""
        return self._channels.copy()

    async def send(
        self,
        notification: Notification,
        channels: Optional[List[str]] = None,
        parallel: bool = True,
    ) -> Dict[str, DeliveryResult]:
        """
        إرسال إشعار لقنوات محددة أو الافتراضية.
        Send notification to specified or default channels.
        """
        # فحص انتهاء الصلاحية
        if notification.is_expired:
            logger.warning(f"Notification {notification.notification_id} has expired")
            return {}

        # فحص التكرار
        if notification.dedupe_key:
            async with self._lock:
                if notification.dedupe_key in self._dedupe_cache:
                    last_sent = self._dedupe_cache[notification.dedupe_key]
                    if datetime.utcnow() - last_sent < self._dedupe_window:
                        logger.debug(f"Deduplicated notification: {notification.dedupe_key}")
                        return {}
                self._dedupe_cache[notification.dedupe_key] = datetime.utcnow()

        # تحديد القنوات
        target_channels = channels or notification.target_channels or self._default_channels

        results: Dict[str, DeliveryResult] = {}

        if parallel:
            # إرسال متوازي
            tasks = []
            for channel_name in target_channels:
                channel = self._channels.get(channel_name)
                if channel:
                    tasks.append(self._send_to_channel(channel, notification))

            if tasks:
                channel_results = await asyncio.gather(*tasks, return_exceptions=True)
                for channel_name, result in zip(target_channels, channel_results):
                    if isinstance(result, Exception):
                        results[channel_name] = DeliveryResult(
                            success=False,
                            channel_name=channel_name,
                            notification_id=notification.notification_id,
                            error=str(result),
                        )
                    else:
                        results[channel_name] = result
        else:
            # إرسال تسلسلي
            for channel_name in target_channels:
                channel = self._channels.get(channel_name)
                if channel:
                    try:
                        result = await self._send_to_channel(channel, notification)
                        results[channel_name] = result
                    except Exception as e:
                        results[channel_name] = DeliveryResult(
                            success=False,
                            channel_name=channel_name,
                            notification_id=notification.notification_id,
                            error=str(e),
                        )

        # حفظ في التاريخ
        self._add_to_history(notification)

        return results

    async def _send_to_channel(
        self,
        channel: NotificationChannel,
        notification: Notification,
    ) -> DeliveryResult:
        """إرسال لقناة واحدة."""
        return await channel.send_notification(notification)

    def _add_to_history(self, notification: Notification) -> None:
        """إضافة للتاريخ."""
        self._notification_history.append(notification)
        if len(self._notification_history) > self._max_history:
            self._notification_history = self._notification_history[-self._max_history :]

    async def broadcast(
        self,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        **kwargs,
    ) -> Dict[str, DeliveryResult]:
        """
        بث إشعار لجميع القنوات الافتراضية.
        Broadcast notification to all default channels.
        """
        notification = Notification(
            title=title,
            message=message,
            priority=priority,
            **kwargs,
        )
        return await self.send(notification)

    async def health_check(self) -> Dict[str, Any]:
        """فحص صحة جميع القنوات."""
        results = {}
        for name, channel in self._channels.items():
            results[name] = await channel.health_check()
        return results

    async def test_all_channels(self) -> Dict[str, bool]:
        """اختبار جميع القنوات."""
        results = {}
        for name, channel in self._channels.items():
            results[name] = await channel.test_connection()
        return results

    def get_metrics(self) -> Dict[str, ChannelMetrics]:
        """الحصول على مقاييس جميع القنوات."""
        return {name: channel.metrics for name, channel in self._channels.items()}

    def clear_history(self) -> None:
        """مسح التاريخ."""
        self._notification_history.clear()
        self._dedupe_cache.clear()


# ═══════════════════════════════════════════════════════════════
# 🏭 CHANNEL FACTORY
# ═══════════════════════════════════════════════════════════════


class ChannelFactory:
    """
    مصنع القنوات.
    Factory for Creating Notification Channels.
    """

    _registry: Dict[str, Type[NotificationChannel]] = {
        "console": ConsoleChannel,
        "email": EmailChannel,
        "slack": SlackChannel,
        "discord": DiscordChannel,
        "telegram": TelegramChannel,
        "webhook": WebhookChannel,
        "pagerduty": PagerDutyChannel,
        "teams": MicrosoftTeamsChannel,
        "pushover": PushoverChannel,
        "twilio_sms": TwilioSMSChannel,
    }

    @classmethod
    def register(cls, channel_type: str, channel_class: Type[NotificationChannel]) -> None:
        """تسجيل نوع قناة جديد."""
        cls._registry[channel_type] = channel_class

    @classmethod
    def create(
        cls,
        channel_type: str,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> NotificationChannel:
        """إنشاء قناة."""
        if channel_type not in cls._registry:
            raise ValueError(f"Unknown channel type: {channel_type}")

        channel_class = cls._registry[channel_type]
        return channel_class(
            name=name or channel_type,
            config=config,
            **kwargs,
        )

    @classmethod
    def create_from_config(cls, config: Dict[str, Any]) -> NotificationChannel:
        """إنشاء من تكوين."""
        channel_type = config.pop("type")
        name = config.pop("name", channel_type)
        return cls.create(channel_type, name, config)

    @classmethod
    def available_types(cls) -> List[str]:
        """أنواع القنوات المتاحة."""
        return list(cls._registry.keys())


# ═══════════════════════════════════════════════════════════════
# 🚀 QUICK START HELPERS
# ═══════════════════════════════════════════════════════════════


def create_notification_manager(
    config: Optional[Dict[str, Any]] = None,
) -> NotificationManager:
    """
    إنشاء مدير إشعارات بسرعة.
    Quick creation of notification manager.
    """
    manager = NotificationManager()

    # إضافة console بشكل افتراضي
    manager.register_channel(ConsoleChannel(colored=True))

    if config:
        for channel_config in config.get("channels", []):
            try:
                channel = ChannelFactory.create_from_config(channel_config.copy())
                manager.register_channel(
                    channel,
                    is_default=channel_config.get("default", True),
                )
            except Exception as e:
                logger.error(f"Failed to create channel: {e}")

    return manager


async def quick_notify(
    title: str,
    message: str,
    priority: str = "normal",
    **kwargs,
) -> None:
    """
    إرسال إشعار سريع (console فقط).
    Quick notification (console only).
    """
    channel = ConsoleChannel()
    notification = Notification(
        title=title,
        message=message,
        priority=NotificationPriority(priority),
        **kwargs,
    )
    await channel.send_notification(notification)


# ═══════════════════════════════════════════════════════════════
# 📝 EXAMPLE USAGE
# ═══════════════════════════════════════════════════════════════


async def example_usage():
    """مثال على الاستخدام."""

    # إنشاء مدير
    manager = NotificationManager()

    # إضافة قنوات
    manager.register_channel(ConsoleChannel(colored=True, show_metadata=True))

    # إرسال إشعار
    notification = Notification(
        title="🚀 System Started",
        message="Dawood AI Assistant notification system is now active!",
        priority=NotificationPriority.HIGH,
        category=NotificationCategory.SYSTEM,
        metadata={"version": "1.0.0", "environment": "production"},
        tags=["startup", "system"],
    )

    results = await manager.send(notification)

    print("\nDelivery Results:")
    for channel_name, result in results.items():
        status = "✅" if result.success else "❌"
        print(f"  {status} {channel_name}: {result.latency_ms:.2f}ms")

    # فحص الصحة
    health = await manager.health_check()
    print("\nHealth Check:")
    for channel_name, status in health.items():
        print(f"  {channel_name}: {status['status']}")


if __name__ == "__main__":
    asyncio.run(example_usage())
