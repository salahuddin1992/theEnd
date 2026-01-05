"""
Webhook Manager - مدير الـ Webhooks
===================================

Core Webhook System
-------------------

This module provides the core webhook management system.

يوفر هذا الملف نظام إدارة الـ webhooks الأساسي.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """نوع الحدث / Event type"""

    # Cluster events
    CLUSTER_CREATED = "cluster.created"
    CLUSTER_UPDATED = "cluster.updated"
    CLUSTER_DELETED = "cluster.deleted"
    CLUSTER_SCALED = "cluster.scaled"

    # Worker events
    WORKER_JOINED = "worker.joined"
    WORKER_LEFT = "worker.left"
    WORKER_FAILED = "worker.failed"
    WORKER_RECOVERED = "worker.recovered"

    # Job events
    JOB_SUBMITTED = "job.submitted"
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"

    # Alert events
    ALERT_FIRED = "alert.fired"
    ALERT_RESOLVED = "alert.resolved"

    # System events
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"


class WebhookStatus(str, Enum):
    """حالة الـ Webhook / Webhook status"""

    PENDING = "pending"
    SENDING = "sending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class WebhookEvent:
    """
    حدث الـ Webhook
    Webhook event
    """

    event_id: str
    event_type: EventType
    timestamp: datetime
    data: dict[str, Any]
    source: str = "distributed-cluster"
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "eventType": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "version": self.version,
            "data": self.data,
        }

    @classmethod
    def create(
        cls,
        event_type: EventType,
        data: dict[str, Any],
        source: str = "distributed-cluster",
    ) -> WebhookEvent:
        return cls(
            event_id=str(uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            data=data,
            source=source,
        )


@dataclass
class WebhookResult:
    """
    نتيجة إرسال Webhook
    Webhook send result
    """

    event_id: str
    webhook_id: str
    status: WebhookStatus
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "webhookId": self.webhook_id,
            "status": self.status.value,
            "statusCode": self.status_code,
            "error": self.error,
            "attempts": self.attempts,
            "durationMs": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class WebhookConfig:
    """
    إعدادات الـ Webhook
    Webhook configuration
    """

    webhook_id: str
    url: str
    enabled: bool = True

    # Authentication
    secret: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)

    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    retry_multiplier: float = 2.0
    max_retry_delay_seconds: float = 60.0

    # Timeouts
    timeout_seconds: float = 30.0
    connect_timeout_seconds: float = 10.0

    # Filtering
    event_types: Optional[list[EventType]] = None  # None = all events

    # Provider-specific
    provider: str = "custom"
    provider_config: dict[str, Any] = field(default_factory=dict)

    def accepts_event(self, event_type: EventType) -> bool:
        """هل يقبل الـ Webhook هذا الحدث؟"""
        if self.event_types is None:
            return True
        return event_type in self.event_types


class WebhookProvider(ABC):
    """
    مزود Webhook أساسي
    Base webhook provider
    """

    @abstractmethod
    def format_payload(self, event: WebhookEvent) -> dict[str, Any]:
        """تنسيق البيانات للمزود"""
        pass

    @abstractmethod
    def get_headers(self, config: WebhookConfig) -> dict[str, str]:
        """الحصول على الـ headers"""
        pass

    def sign_payload(
        self,
        payload: bytes,
        secret: str,
    ) -> str:
        """توقيع البيانات"""
        signature = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={signature}"


class WebhookManager:
    """
    مدير الـ Webhooks
    Webhook Manager

    يدير إرسال الإشعارات عبر webhooks.
    Manages webhook notification delivery.
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        queue_size: int = 1000,
    ):
        """
        تهيئة المدير

        Args:
            max_concurrent: الحد الأقصى للطلبات المتزامنة
            queue_size: حجم قائمة الانتظار
        """
        self.max_concurrent = max_concurrent
        self.queue_size = queue_size

        # Webhooks
        self._webhooks: dict[str, WebhookConfig] = {}
        self._providers: dict[str, WebhookProvider] = {}

        # Queue
        self._queue: asyncio.Queue[tuple[WebhookEvent, WebhookConfig]] = asyncio.Queue(maxsize=queue_size)

        # Results
        self._results: list[WebhookResult] = []
        self._result_handlers: list[Callable[[WebhookResult], None]] = []

        # State
        self._running = False
        self._workers: list[asyncio.Task] = []
        self._client: Optional[httpx.AsyncClient] = None

        # Stats
        self._stats = {
            "total_sent": 0,
            "successful": 0,
            "failed": 0,
            "retried": 0,
        }

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء المدير"""
        self._running = True

        # Create HTTP client
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

        # Start workers
        for i in range(self.max_concurrent):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)

        logger.info(f"WebhookManager started with {self.max_concurrent} workers")

    async def stop(self) -> None:
        """إيقاف المدير"""
        self._running = False

        # Cancel workers
        for worker in self._workers:
            worker.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        # Close client
        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("WebhookManager stopped")

    # =========================================================================
    # Registration
    # =========================================================================

    def register_webhook(self, config: WebhookConfig) -> None:
        """تسجيل webhook"""
        self._webhooks[config.webhook_id] = config
        logger.info(f"Registered webhook: {config.webhook_id}")

    def unregister_webhook(self, webhook_id: str) -> None:
        """إلغاء تسجيل webhook"""
        self._webhooks.pop(webhook_id, None)

    def register_provider(self, name: str, provider: WebhookProvider) -> None:
        """تسجيل مزود"""
        self._providers[name] = provider

    def get_webhook(self, webhook_id: str) -> Optional[WebhookConfig]:
        """الحصول على webhook"""
        return self._webhooks.get(webhook_id)

    # =========================================================================
    # Sending
    # =========================================================================

    async def send(self, event: WebhookEvent) -> list[WebhookResult]:
        """
        إرسال حدث لجميع الـ webhooks المسجلة

        Args:
            event: الحدث للإرسال

        Returns:
            قائمة النتائج
        """
        results = []

        for config in self._webhooks.values():
            if not config.enabled:
                continue

            if not config.accepts_event(event.event_type):
                continue

            try:
                await self._queue.put((event, config))
            except asyncio.QueueFull:
                logger.warning(f"Webhook queue full, dropping event {event.event_id}")
                results.append(
                    WebhookResult(
                        event_id=event.event_id,
                        webhook_id=config.webhook_id,
                        status=WebhookStatus.FAILED,
                        error="Queue full",
                    )
                )

        return results

    async def send_immediate(
        self,
        event: WebhookEvent,
        webhook_id: Optional[str] = None,
    ) -> list[WebhookResult]:
        """
        إرسال فوري بدون استخدام القائمة

        Args:
            event: الحدث
            webhook_id: معرف الـ webhook (اختياري)

        Returns:
            قائمة النتائج
        """
        results = []

        webhooks = (
            [self._webhooks[webhook_id]] if webhook_id and webhook_id in self._webhooks else self._webhooks.values()
        )

        for config in webhooks:
            if not config.enabled:
                continue

            if not config.accepts_event(event.event_type):
                continue

            result = await self._send_webhook(event, config)
            results.append(result)

        return results

    # =========================================================================
    # Worker
    # =========================================================================

    async def _worker(self, worker_id: int) -> None:
        """عامل معالجة الـ webhooks"""
        while self._running:
            try:
                event, config = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0,
                )

                result = await self._send_webhook(event, config)
                self._handle_result(result)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

    async def _send_webhook(
        self,
        event: WebhookEvent,
        config: WebhookConfig,
    ) -> WebhookResult:
        """إرسال webhook واحد"""
        start_time = time.time()
        attempts = 0
        delay = config.retry_delay_seconds

        while attempts <= config.max_retries:
            attempts += 1

            try:
                result = await self._attempt_send(event, config, attempts)

                if result.status == WebhookStatus.SUCCESS:
                    result.duration_ms = (time.time() - start_time) * 1000
                    self._stats["total_sent"] += 1
                    self._stats["successful"] += 1
                    return result

                # Check if retryable
                if result.status_code and result.status_code >= 500:
                    if attempts <= config.max_retries:
                        self._stats["retried"] += 1
                        await asyncio.sleep(delay)
                        delay = min(
                            delay * config.retry_multiplier,
                            config.max_retry_delay_seconds,
                        )
                        continue

                # Non-retryable error
                result.duration_ms = (time.time() - start_time) * 1000
                self._stats["total_sent"] += 1
                self._stats["failed"] += 1
                return result

            except Exception as e:
                if attempts <= config.max_retries:
                    self._stats["retried"] += 1
                    await asyncio.sleep(delay)
                    delay = min(
                        delay * config.retry_multiplier,
                        config.max_retry_delay_seconds,
                    )
                else:
                    self._stats["total_sent"] += 1
                    self._stats["failed"] += 1
                    return WebhookResult(
                        event_id=event.event_id,
                        webhook_id=config.webhook_id,
                        status=WebhookStatus.FAILED,
                        error=str(e),
                        attempts=attempts,
                        duration_ms=(time.time() - start_time) * 1000,
                    )

        # Should not reach here
        return WebhookResult(
            event_id=event.event_id,
            webhook_id=config.webhook_id,
            status=WebhookStatus.FAILED,
            error="Max retries exceeded",
            attempts=attempts,
            duration_ms=(time.time() - start_time) * 1000,
        )

    async def _attempt_send(
        self,
        event: WebhookEvent,
        config: WebhookConfig,
        attempt: int,
    ) -> WebhookResult:
        """محاولة إرسال واحدة"""
        # Get provider
        provider = self._providers.get(config.provider)

        # Format payload
        if provider:
            payload = provider.format_payload(event)
        else:
            payload = event.to_dict()

        payload_bytes = json.dumps(payload).encode()

        # Build headers
        headers = {"Content-Type": "application/json"}

        if provider:
            headers.update(provider.get_headers(config))

        headers.update(config.headers)

        # Add signature if secret is configured
        if config.secret:
            if provider:
                signature = provider.sign_payload(payload_bytes, config.secret)
            else:
                signature = hmac.new(
                    config.secret.encode(),
                    payload_bytes,
                    hashlib.sha256,
                ).hexdigest()
                signature = f"sha256={signature}"

            headers["X-Webhook-Signature"] = signature

        # Send request
        if not self._client:
            raise RuntimeError("HTTP client not initialized")

        response = await self._client.post(
            config.url,
            content=payload_bytes,
            headers=headers,
            timeout=httpx.Timeout(
                config.timeout_seconds,
                connect=config.connect_timeout_seconds,
            ),
        )

        # Check response
        if 200 <= response.status_code < 300:
            return WebhookResult(
                event_id=event.event_id,
                webhook_id=config.webhook_id,
                status=WebhookStatus.SUCCESS,
                status_code=response.status_code,
                response_body=response.text[:1000],  # Limit response size
                attempts=attempt,
            )
        else:
            return WebhookResult(
                event_id=event.event_id,
                webhook_id=config.webhook_id,
                status=WebhookStatus.FAILED,
                status_code=response.status_code,
                response_body=response.text[:1000],
                error=f"HTTP {response.status_code}",
                attempts=attempt,
            )

    # =========================================================================
    # Results
    # =========================================================================

    def _handle_result(self, result: WebhookResult) -> None:
        """معالجة النتيجة"""
        self._results.append(result)

        # Keep only last 1000 results
        if len(self._results) > 1000:
            self._results = self._results[-1000:]

        # Notify handlers
        for handler in self._result_handlers:
            try:
                handler(result)
            except Exception as e:
                logger.error(f"Result handler error: {e}")

    def register_result_handler(
        self,
        handler: Callable[[WebhookResult], None],
    ) -> None:
        """تسجيل معالج النتائج"""
        self._result_handlers.append(handler)

    def get_recent_results(self, limit: int = 100) -> list[WebhookResult]:
        """الحصول على النتائج الأخيرة"""
        return self._results[-limit:]

    # =========================================================================
    # Stats
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """الحصول على الإحصائيات"""
        return {
            **self._stats,
            "queue_size": self._queue.qsize(),
            "webhooks_registered": len(self._webhooks),
            "providers_registered": len(self._providers),
        }

    def get_status(self) -> dict[str, Any]:
        """الحصول على الحالة"""
        return {
            "running": self._running,
            "stats": self.get_stats(),
            "webhooks": {
                wid: {
                    "url": w.url,
                    "enabled": w.enabled,
                    "provider": w.provider,
                }
                for wid, w in self._webhooks.items()
            },
        }
