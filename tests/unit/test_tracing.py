"""
Tracing Tests
=============

Tests for distributed tracing functionality.
"""

import asyncio

import pytest

from distributed_cluster.observability.tracing import (
    ConsoleSpanExporter,
    Span,
    SpanKind,
    SpanStatus,
    Tracer,
    get_tracer,
    set_tracer,
    traced,
)


class TestSpan:
    """Tests for Span class."""

    def test_span_creation(self):
        """Test basic span creation."""
        span = Span(
            name="test-span",
            trace_id="abc123",
            span_id="def456",
        )

        assert span.name == "test-span"
        assert span.trace_id == "abc123"
        assert span.span_id == "def456"
        assert span.status == SpanStatus.UNSET

    def test_set_attributes(self):
        """Test setting attributes."""
        span = Span(name="test", trace_id="t1", span_id="s1")

        span.set_attribute("key1", "value1")
        span.set_attributes({"key2": 123, "key3": True})

        assert span.attributes["key1"] == "value1"
        assert span.attributes["key2"] == 123
        assert span.attributes["key3"] is True

    def test_add_event(self):
        """Test adding events."""
        span = Span(name="test", trace_id="t1", span_id="s1")

        span.add_event("event1", {"detail": "value"})

        assert len(span.events) == 1
        assert span.events[0].name == "event1"
        assert span.events[0].attributes["detail"] == "value"

    def test_add_link(self):
        """Test adding links."""
        span = Span(name="test", trace_id="t1", span_id="s1")

        span.add_link("other-trace", "other-span", {"relationship": "parent"})

        assert len(span.links) == 1
        assert span.links[0].trace_id == "other-trace"
        assert span.links[0].span_id == "other-span"

    def test_set_status(self):
        """Test setting status."""
        span = Span(name="test", trace_id="t1", span_id="s1")

        span.set_status(SpanStatus.OK)
        assert span.status == SpanStatus.OK

        span.set_status(SpanStatus.ERROR, "Something failed")
        assert span.status == SpanStatus.ERROR
        assert span.status_message == "Something failed"

    def test_set_error(self):
        """Test setting error."""
        span = Span(name="test", trace_id="t1", span_id="s1")

        try:
            raise ValueError("Test error")
        except Exception as e:
            span.set_error(e)

        assert span.status == SpanStatus.ERROR
        assert "Test error" in span.status_message
        assert span.attributes["error.type"] == "ValueError"

    def test_duration(self):
        """Test duration calculation."""
        span = Span(name="test", trace_id="t1", span_id="s1")
        span.start_time = 1000.0
        span.end_time = 1000.5

        assert span.duration_ms == 500.0

    def test_to_dict(self):
        """Test converting to dict."""
        span = Span(
            name="test",
            trace_id="t1",
            span_id="s1",
            parent_span_id="p1",
            kind=SpanKind.SERVER,
        )
        span.set_status(SpanStatus.OK)
        span.set_attribute("key", "value")
        span.end()

        d = span.to_dict()

        assert d["name"] == "test"
        assert d["traceId"] == "t1"
        assert d["spanId"] == "s1"
        assert d["parentSpanId"] == "p1"
        assert d["kind"] == "server"
        assert d["status"]["code"] == "ok"
        assert d["attributes"]["key"] == "value"


class TestTracer:
    """Tests for Tracer class."""

    def test_tracer_creation(self):
        """Test tracer creation."""
        tracer = Tracer(
            service_name="test-service",
            service_version="1.0.0",
        )

        assert tracer.service_name == "test-service"
        assert tracer.service_version == "1.0.0"

    def test_start_span_sync(self):
        """Test starting a sync span."""
        tracer = Tracer(service_name="test")

        with tracer.start_span("my-operation") as span:
            assert span.name == "my-operation"
            assert tracer.get_current_span() == span

        # After context, status should be OK
        assert span.status == SpanStatus.OK
        assert span.end_time is not None

    def test_start_span_with_error(self):
        """Test span with exception."""
        tracer = Tracer(service_name="test")

        try:
            with tracer.start_span("failing-operation") as span:
                raise ValueError("Test error")
        except ValueError:
            pass

        assert span.status == SpanStatus.ERROR
        assert "ValueError" in span.attributes.get("error.type", "")

    @pytest.mark.asyncio
    async def test_start_async_span(self):
        """Test starting an async span."""
        tracer = Tracer(service_name="test")

        async with tracer.start_async_span("async-operation") as span:
            assert span.name == "async-operation"
            await asyncio.sleep(0.01)

        assert span.status == SpanStatus.OK

    def test_nested_spans(self):
        """Test nested spans share trace ID."""
        tracer = Tracer(service_name="test")

        with tracer.start_span("parent") as parent:
            parent_trace_id = parent.trace_id

            with tracer.start_span("child") as child:
                assert child.trace_id == parent_trace_id
                assert child.parent_span_id == parent.span_id

    def test_context_propagation(self):
        """Test context injection/extraction."""
        tracer = Tracer(service_name="test")

        with tracer.start_span("operation"):
            headers = tracer.inject_context()

            assert "traceparent" in headers
            parts = headers["traceparent"].split("-")
            assert len(parts) >= 3

        # Extract into new tracer
        tracer2 = Tracer(service_name="other")
        tracer2.extract_context(headers)

        assert tracer2.get_current_trace_id() == parts[1]

    @pytest.mark.asyncio
    async def test_flush(self):
        """Test flushing pending spans."""
        exporter = ConsoleSpanExporter()
        tracer = Tracer(
            service_name="test",
            exporters=[exporter],
        )

        with tracer.start_span("operation"):
            pass

        await tracer.flush()
        # Should complete without error


class TestTracedDecorator:
    """Tests for @traced decorator."""

    def test_traced_sync_function(self):
        """Test tracing a sync function."""
        tracer = Tracer(service_name="test")

        @traced(tracer)
        def my_function():
            return "result"

        result = my_function()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_traced_async_function(self):
        """Test tracing an async function."""
        tracer = Tracer(service_name="test")

        @traced(tracer)
        async def my_async_function():
            await asyncio.sleep(0.01)
            return "async result"

        result = await my_async_function()
        assert result == "async result"

    def test_traced_with_custom_name(self):
        """Test tracing with custom span name."""
        tracer = Tracer(service_name="test")

        @traced(tracer, name="custom-name", kind=SpanKind.CLIENT)
        def my_function():
            span = tracer.get_current_span()
            assert span.name == "custom-name"
            assert span.kind == SpanKind.CLIENT
            return True

        assert my_function() is True


class TestGlobalTracer:
    """Tests for global tracer management."""

    def test_get_set_tracer(self):
        """Test getting and setting global tracer."""
        original = get_tracer()

        custom_tracer = Tracer(service_name="custom")
        set_tracer(custom_tracer)

        assert get_tracer() is custom_tracer

        # Restore
        set_tracer(original)
