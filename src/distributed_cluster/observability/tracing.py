"""
Distributed Tracing - التتبع الموزع
===================================

دعم التتبع الموزع باستخدام OpenTelemetry-compatible:
- Span creation and management
- Context propagation
- Trace export
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

logger = logging.getLogger(__name__)


class SpanKind(str, Enum):
    """أنواع الـ Span."""

    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus(str, Enum):
    """حالة الـ Span."""

    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class SpanEvent:
    """حدث داخل Span."""

    name: str
    timestamp: float
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpanLink:
    """رابط لـ Span آخر."""

    trace_id: str
    span_id: str
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """
    Span واحد في التتبع.

    يمثل وحدة عمل واحدة مع بداية ونهاية.
    """

    name: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    kind: SpanKind = SpanKind.INTERNAL
    status: SpanStatus = SpanStatus.UNSET
    status_message: str = ""

    # Timing
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    # Attributes and events
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[SpanEvent] = field(default_factory=list)
    links: List[SpanLink] = field(default_factory=list)

    # Service info
    service_name: str = "nebula-cluster"
    service_version: str = "1.0.0"

    def set_attribute(self, key: str, value: Any) -> None:
        """تعيين attribute."""
        self.attributes[key] = value

    def set_attributes(self, attributes: Dict[str, Any]) -> None:
        """تعيين عدة attributes."""
        self.attributes.update(attributes)

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """إضافة حدث."""
        self.events.append(SpanEvent(
            name=name,
            timestamp=time.time(),
            attributes=attributes or {},
        ))

    def add_link(self, trace_id: str, span_id: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """إضافة رابط."""
        self.links.append(SpanLink(
            trace_id=trace_id,
            span_id=span_id,
            attributes=attributes or {},
        ))

    def set_status(self, status: SpanStatus, message: str = "") -> None:
        """تعيين حالة الـ Span."""
        self.status = status
        self.status_message = message

    def set_error(self, error: Exception) -> None:
        """تعيين خطأ."""
        self.status = SpanStatus.ERROR
        self.status_message = str(error)
        self.set_attribute("error.type", type(error).__name__)
        self.set_attribute("error.message", str(error))

    def end(self) -> None:
        """إنهاء الـ Span."""
        if self.end_time is None:
            self.end_time = time.time()

    @property
    def duration_ms(self) -> float:
        """مدة الـ Span بالميلي ثانية."""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dict."""
        return {
            "name": self.name,
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "parentSpanId": self.parent_span_id,
            "kind": self.kind.value,
            "status": {
                "code": self.status.value,
                "message": self.status_message,
            },
            "startTimeUnixNano": int(self.start_time * 1e9),
            "endTimeUnixNano": int((self.end_time or time.time()) * 1e9),
            "attributes": self.attributes,
            "events": [
                {
                    "name": e.name,
                    "timeUnixNano": int(e.timestamp * 1e9),
                    "attributes": e.attributes,
                }
                for e in self.events
            ],
            "links": [
                {
                    "traceId": l.trace_id,
                    "spanId": l.span_id,
                    "attributes": l.attributes,
                }
                for l in self.links
            ],
            "resource": {
                "service.name": self.service_name,
                "service.version": self.service_version,
            },
        }


class SpanExporter(ABC):
    """واجهة تصدير الـ Spans."""

    @abstractmethod
    async def export(self, spans: List[Span]) -> bool:
        """تصدير spans."""
        pass


class ConsoleSpanExporter(SpanExporter):
    """تصدير للـ console (للتطوير)."""

    async def export(self, spans: List[Span]) -> bool:
        for span in spans:
            duration = span.duration_ms
            status_icon = "✓" if span.status == SpanStatus.OK else "✗" if span.status == SpanStatus.ERROR else "○"
            logger.info(
                f"[TRACE] {status_icon} {span.name} "
                f"trace={span.trace_id[:8]}... span={span.span_id[:8]}... "
                f"duration={duration:.2f}ms"
            )
        return True


class OTLPSpanExporter(SpanExporter):
    """تصدير لـ OTLP (OpenTelemetry Protocol)."""

    def __init__(
        self,
        endpoint: str = "http://localhost:4318/v1/traces",
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ):
        self.endpoint = endpoint
        self.headers = headers or {}
        self.timeout = timeout

    async def export(self, spans: List[Span]) -> bool:
        """تصدير spans إلى OTLP endpoint."""
        import httpx

        if not spans:
            return True

        # Format as OTLP JSON
        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": spans[0].service_name}},
                            {"key": "service.version", "value": {"stringValue": spans[0].service_version}},
                        ],
                    },
                    "scopeSpans": [
                        {
                            "spans": [span.to_dict() for span in spans],
                        },
                    ],
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        **self.headers,
                    },
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to export spans to OTLP: {e}")
            return False


class JaegerSpanExporter(SpanExporter):
    """تصدير لـ Jaeger."""

    def __init__(
        self,
        endpoint: str = "http://localhost:14268/api/traces",
        timeout: float = 30.0,
    ):
        self.endpoint = endpoint
        self.timeout = timeout

    async def export(self, spans: List[Span]) -> bool:
        """تصدير spans إلى Jaeger."""
        import httpx

        if not spans:
            return True

        # Convert to Jaeger format
        jaeger_spans = []
        for span in spans:
            jaeger_spans.append({
                "traceIdLow": int(span.trace_id[:16], 16),
                "traceIdHigh": int(span.trace_id[16:], 16) if len(span.trace_id) > 16 else 0,
                "spanId": int(span.span_id, 16),
                "parentSpanId": int(span.parent_span_id, 16) if span.parent_span_id else 0,
                "operationName": span.name,
                "startTime": int(span.start_time * 1e6),  # microseconds
                "duration": int(span.duration_ms * 1000),  # microseconds
                "tags": [
                    {"key": k, "type": "string", "vStr": str(v)}
                    for k, v in span.attributes.items()
                ],
                "logs": [
                    {
                        "timestamp": int(e.timestamp * 1e6),
                        "fields": [
                            {"key": "event", "type": "string", "vStr": e.name},
                        ],
                    }
                    for e in span.events
                ],
            })

        payload = {
            "process": {
                "serviceName": spans[0].service_name,
            },
            "spans": jaeger_spans,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to export spans to Jaeger: {e}")
            return False


class Tracer:
    """
    مدير التتبع.

    الاستخدام:
        tracer = Tracer(service_name="my-service")

        with tracer.start_span("my-operation") as span:
            span.set_attribute("key", "value")
            # ... do work ...

        # Async version
        async with tracer.start_async_span("async-operation") as span:
            await do_async_work()
    """

    def __init__(
        self,
        service_name: str = "nebula-cluster",
        service_version: str = "1.0.0",
        exporters: Optional[List[SpanExporter]] = None,
        batch_size: int = 100,
        flush_interval: float = 5.0,
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.exporters = exporters or [ConsoleSpanExporter()]
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        # Current context
        self._current_trace_id: Optional[str] = None
        self._current_span_id: Optional[str] = None
        self._span_stack: List[Span] = []

        # Batch export
        self._pending_spans: List[Span] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None

    def _generate_trace_id(self) -> str:
        """توليد trace ID."""
        return secrets.token_hex(16)

    def _generate_span_id(self) -> str:
        """توليد span ID."""
        return secrets.token_hex(8)

    @contextmanager
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
        links: Optional[List[SpanLink]] = None,
    ) -> Iterator[Span]:
        """بدء span جديد (sync)."""
        # Determine trace and parent
        if self._current_trace_id:
            trace_id = self._current_trace_id
            parent_span_id = self._current_span_id
        else:
            trace_id = self._generate_trace_id()
            parent_span_id = None

        span_id = self._generate_span_id()

        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            kind=kind,
            service_name=self.service_name,
            service_version=self.service_version,
        )

        if attributes:
            span.set_attributes(attributes)

        if links:
            span.links = links

        # Push to stack
        old_trace_id = self._current_trace_id
        old_span_id = self._current_span_id
        self._current_trace_id = trace_id
        self._current_span_id = span_id
        self._span_stack.append(span)

        try:
            yield span
            if span.status == SpanStatus.UNSET:
                span.set_status(SpanStatus.OK)
        except Exception as e:
            span.set_error(e)
            raise
        finally:
            span.end()
            self._span_stack.pop()
            self._current_trace_id = old_trace_id
            self._current_span_id = old_span_id

            # Queue for export
            self._pending_spans.append(span)

    @asynccontextmanager
    async def start_async_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
        links: Optional[List[SpanLink]] = None,
    ):
        """بدء span جديد (async)."""
        with self.start_span(name, kind, attributes, links) as span:
            yield span

    def get_current_trace_id(self) -> Optional[str]:
        """الحصول على trace ID الحالي."""
        return self._current_trace_id

    def get_current_span_id(self) -> Optional[str]:
        """الحصول على span ID الحالي."""
        return self._current_span_id

    def get_current_span(self) -> Optional[Span]:
        """الحصول على الـ span الحالي."""
        return self._span_stack[-1] if self._span_stack else None

    def inject_context(self) -> Dict[str, str]:
        """استخراج السياق لنقله."""
        if self._current_trace_id and self._current_span_id:
            return {
                "traceparent": f"00-{self._current_trace_id}-{self._current_span_id}-01",
            }
        return {}

    def extract_context(self, headers: Dict[str, str]) -> None:
        """استخراج السياق من headers."""
        traceparent = headers.get("traceparent")
        if traceparent:
            parts = traceparent.split("-")
            if len(parts) >= 3:
                self._current_trace_id = parts[1]
                self._current_span_id = parts[2]

    async def flush(self) -> None:
        """تصدير الـ spans المعلقة."""
        async with self._lock:
            if not self._pending_spans:
                return

            spans_to_export = self._pending_spans.copy()
            self._pending_spans.clear()

        for exporter in self.exporters:
            try:
                await exporter.export(spans_to_export)
            except Exception as e:
                logger.error(f"Exporter error: {e}")

    async def start_background_flush(self) -> None:
        """بدء التصدير الدوري."""
        async def flush_loop():
            while True:
                await asyncio.sleep(self.flush_interval)
                if len(self._pending_spans) >= self.batch_size:
                    await self.flush()

        self._flush_task = asyncio.create_task(flush_loop())

    async def stop(self) -> None:
        """إيقاف وتصدير النهائي."""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        await self.flush()


# ==================== Convenience Decorators ====================


def traced(
    tracer: Tracer,
    name: Optional[str] = None,
    kind: SpanKind = SpanKind.INTERNAL,
):
    """Decorator لتتبع function."""
    def decorator(func: Callable):
        span_name = name or func.__name__

        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                async with tracer.start_async_span(span_name, kind) as span:
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                with tracer.start_span(span_name, kind) as span:
                    return func(*args, **kwargs)
            return sync_wrapper

    return decorator


# ==================== Global Tracer ====================

_global_tracer: Optional[Tracer] = None


def get_tracer() -> Tracer:
    """الحصول على الـ tracer العام."""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = Tracer()
    return _global_tracer


def set_tracer(tracer: Tracer) -> None:
    """تعيين الـ tracer العام."""
    global _global_tracer
    _global_tracer = tracer
