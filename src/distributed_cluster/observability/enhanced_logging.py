"""
Enhanced Logging System - نظام التسجيل المحسن
==============================================

نظام تسجيل متقدم يشمل:
- Async Logging للأداء العالي
- Correlation ID Propagation
- Distributed Log Aggregation
- Log Sampling و Filtering
- Structured Output مع OpenTelemetry compatibility
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import queue
import sys
import threading
import time
import traceback
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from functools import wraps
from pathlib import Path
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    List,
    Optional,
    TypeVar,
    Union,
)

# =============================================================================
# Log Levels
# =============================================================================


class LogLevel(IntEnum):
    """مستويات التسجيل."""

    TRACE = 5
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


LEVEL_NAMES = {
    LogLevel.TRACE: "TRACE",
    LogLevel.DEBUG: "DEBUG",
    LogLevel.INFO: "INFO",
    LogLevel.WARNING: "WARNING",
    LogLevel.ERROR: "ERROR",
    LogLevel.CRITICAL: "CRITICAL",
}


# =============================================================================
# Correlation Context
# =============================================================================


# Context variables للـ async context propagation
_correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("correlation_id", default=None)
_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id", default=None)
_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("span_id", default=None)
_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("user_id", default=None)
_extra_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar("extra_context", default={})


def generate_correlation_id() -> str:
    """إنشاء Correlation ID جديد."""
    return str(uuid.uuid4())


def get_correlation_id() -> Optional[str]:
    """الحصول على Correlation ID الحالي."""
    return _correlation_id.get()


def set_correlation_id(cid: str) -> contextvars.Token:
    """تعيين Correlation ID."""
    return _correlation_id.set(cid)


def get_trace_context() -> Dict[str, Optional[str]]:
    """الحصول على سياق التتبع الكامل."""
    return {
        "correlation_id": _correlation_id.get(),
        "trace_id": _trace_id.get(),
        "span_id": _span_id.get(),
        "request_id": _request_id.get(),
        "user_id": _user_id.get(),
    }


def set_trace_context(
    correlation_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    **extra,
) -> Dict[str, contextvars.Token]:
    """تعيين سياق التتبع."""
    tokens = {}

    if correlation_id is not None:
        tokens["correlation_id"] = _correlation_id.set(correlation_id)
    if trace_id is not None:
        tokens["trace_id"] = _trace_id.set(trace_id)
    if span_id is not None:
        tokens["span_id"] = _span_id.set(span_id)
    if request_id is not None:
        tokens["request_id"] = _request_id.set(request_id)
    if user_id is not None:
        tokens["user_id"] = _user_id.set(user_id)
    if extra:
        current = _extra_context.get().copy()
        current.update(extra)
        tokens["extra"] = _extra_context.set(current)

    return tokens


def clear_trace_context() -> None:
    """مسح سياق التتبع."""
    _correlation_id.set(None)
    _trace_id.set(None)
    _span_id.set(None)
    _request_id.set(None)
    _user_id.set(None)
    _extra_context.set({})


class CorrelationContext:
    """
    Context manager لسياق الـ correlation.

    الاستخدام:
        with CorrelationContext(correlation_id="abc-123"):
            logger.info("Processing request")
    """

    def __init__(
        self,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        auto_generate: bool = True,
        **extra,
    ):
        self.correlation_id = correlation_id or (generate_correlation_id() if auto_generate else None)
        self.trace_id = trace_id
        self.span_id = span_id
        self.request_id = request_id
        self.user_id = user_id
        self.extra = extra
        self._tokens: Dict[str, contextvars.Token] = {}

    def __enter__(self):
        self._tokens = set_trace_context(
            correlation_id=self.correlation_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
            request_id=self.request_id,
            user_id=self.user_id,
            **self.extra,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for name, token in self._tokens.items():
            var = {
                "correlation_id": _correlation_id,
                "trace_id": _trace_id,
                "span_id": _span_id,
                "request_id": _request_id,
                "user_id": _user_id,
                "extra": _extra_context,
            }.get(name)
            if var:
                var.reset(token)
        return False


# =============================================================================
# Log Record
# =============================================================================


@dataclass
class LogRecord:
    """سجل log واحد."""

    level: LogLevel
    message: str
    logger_name: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Context
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None

    # Additional data
    extra: Dict[str, Any] = field(default_factory=dict)
    exception: Optional[str] = None
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    source_function: Optional[str] = None

    # Metadata
    service_name: str = "distributed_cluster"
    environment: str = "production"
    host: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        d = {
            "timestamp": self.timestamp.isoformat() + "Z",
            "level": LEVEL_NAMES.get(self.level, str(self.level)),
            "message": self.message,
            "logger": self.logger_name,
            "service": self.service_name,
            "environment": self.environment,
        }

        if self.host:
            d["host"] = self.host

        # Add trace context
        if self.correlation_id:
            d["correlation_id"] = self.correlation_id
        if self.trace_id:
            d["trace_id"] = self.trace_id
        if self.span_id:
            d["span_id"] = self.span_id
        if self.request_id:
            d["request_id"] = self.request_id
        if self.user_id:
            d["user_id"] = self.user_id

        # Add source info
        if self.source_file:
            d["source"] = {
                "file": self.source_file,
                "line": self.source_line,
                "function": self.source_function,
            }

        # Add exception
        if self.exception:
            d["exception"] = self.exception

        # Add extra fields
        if self.extra:
            d["extra"] = self.extra

        return d

    def to_json(self) -> str:
        """تحويل إلى JSON."""
        return json.dumps(self.to_dict(), default=str)


# =============================================================================
# Log Handlers
# =============================================================================


class LogHandler(ABC):
    """معالج log مجرد."""

    def __init__(self, level: LogLevel = LogLevel.DEBUG):
        self.level = level

    @abstractmethod
    def emit(self, record: LogRecord) -> None:
        """كتابة سجل."""
        pass

    @abstractmethod
    def close(self) -> None:
        """إغلاق المعالج."""
        pass


class ConsoleHandler(LogHandler):
    """معالج الكونسول."""

    def __init__(
        self,
        level: LogLevel = LogLevel.DEBUG,
        json_format: bool = True,
        colorize: bool = True,
    ):
        super().__init__(level)
        self.json_format = json_format
        self.colorize = colorize
        self._lock = threading.Lock()

    def emit(self, record: LogRecord) -> None:
        """كتابة إلى الكونسول."""
        if record.level < self.level:
            return

        if self.json_format:
            output = record.to_json()
        else:
            output = self._format_human_readable(record)

        with self._lock:
            print(output, file=sys.stderr)

    def _format_human_readable(self, record: LogRecord) -> str:
        """تنسيق قابل للقراءة."""
        level_name = LEVEL_NAMES.get(record.level, str(record.level))

        # Colors for different levels
        if self.colorize:
            colors = {
                LogLevel.TRACE: "\033[90m",  # Gray
                LogLevel.DEBUG: "\033[36m",  # Cyan
                LogLevel.INFO: "\033[32m",  # Green
                LogLevel.WARNING: "\033[33m",  # Yellow
                LogLevel.ERROR: "\033[31m",  # Red
                LogLevel.CRITICAL: "\033[35m",  # Magenta
            }
            reset = "\033[0m"
            color = colors.get(record.level, "")
        else:
            color = ""
            reset = ""

        parts = [
            f"{record.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}",
            f"{color}[{level_name:8s}]{reset}",
            f"{record.logger_name}:",
            record.message,
        ]

        if record.correlation_id:
            parts.append(f"[cid={record.correlation_id[:8]}]")

        if record.extra:
            parts.append(f"{record.extra}")

        if record.exception:
            parts.append(f"\n{record.exception}")

        return " ".join(parts)

    def close(self) -> None:
        """إغلاق المعالج."""
        pass


class AsyncFileHandler(LogHandler):
    """
    معالج ملفات غير متزامن.

    يستخدم queue للكتابة غير المحجوبة.
    """

    def __init__(
        self,
        filename: Union[str, Path],
        level: LogLevel = LogLevel.DEBUG,
        max_queue_size: int = 10000,
        flush_interval: float = 1.0,
        json_format: bool = True,
    ):
        super().__init__(level)
        self.filename = Path(filename)
        self.max_queue_size = max_queue_size
        self.flush_interval = flush_interval
        self.json_format = json_format

        # Ensure directory exists
        self.filename.parent.mkdir(parents=True, exist_ok=True)

        # Create queue and worker
        self._queue: queue.Queue[Optional[LogRecord]] = queue.Queue(maxsize=max_queue_size)
        self._running = True
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

        # File handle
        self._file = open(self.filename, "a", encoding="utf-8")
        self._last_flush = time.time()

    def emit(self, record: LogRecord) -> None:
        """إضافة سجل إلى الـ queue."""
        if record.level < self.level:
            return

        try:
            self._queue.put_nowait(record)
        except queue.Full:
            # Drop the record if queue is full
            pass

    def _worker_loop(self) -> None:
        """حلقة العمل للكتابة."""
        batch: List[LogRecord] = []

        while self._running or not self._queue.empty():
            try:
                record = self._queue.get(timeout=self.flush_interval)

                if record is None:
                    # Signal to stop
                    break

                batch.append(record)

                # Process batch
                if len(batch) >= 100 or time.time() - self._last_flush >= self.flush_interval:
                    self._flush_batch(batch)
                    batch = []

            except queue.Empty:
                if batch:
                    self._flush_batch(batch)
                    batch = []

        # Final flush
        if batch:
            self._flush_batch(batch)

    def _flush_batch(self, batch: List[LogRecord]) -> None:
        """كتابة batch إلى الملف."""
        if not batch:
            return

        try:
            for record in batch:
                if self.json_format:
                    line = record.to_json()
                else:
                    line = f"{record.timestamp.isoformat()} [{LEVEL_NAMES[record.level]}] {record.message}"
                self._file.write(line + "\n")

            self._file.flush()
            self._last_flush = time.time()
        except Exception:
            pass

    def close(self) -> None:
        """إغلاق المعالج."""
        self._running = False
        self._queue.put(None)  # Signal to stop

        if self._worker.is_alive():
            self._worker.join(timeout=5.0)

        if self._file:
            self._file.close()


# =============================================================================
# Log Aggregator
# =============================================================================


class LogAggregator:
    """
    مجمع الـ logs من مصادر متعددة.

    يدعم:
    - تجميع من عدة nodes
    - تصفية وبحث
    - تجميع حسب correlation_id
    """

    def __init__(self, max_size: int = 100000):
        self._logs: Deque[LogRecord] = deque(maxlen=max_size)
        self._by_correlation: Dict[str, List[LogRecord]] = {}
        self._lock = threading.Lock()

    def add(self, record: LogRecord) -> None:
        """إضافة سجل."""
        with self._lock:
            self._logs.append(record)

            if record.correlation_id:
                if record.correlation_id not in self._by_correlation:
                    self._by_correlation[record.correlation_id] = []
                self._by_correlation[record.correlation_id].append(record)

    def get_by_correlation(self, correlation_id: str) -> List[LogRecord]:
        """الحصول على logs حسب correlation_id."""
        with self._lock:
            return self._by_correlation.get(correlation_id, []).copy()

    def search(
        self,
        level: Optional[LogLevel] = None,
        logger_name: Optional[str] = None,
        message_contains: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[LogRecord]:
        """بحث في الـ logs."""
        results = []

        with self._lock:
            for record in reversed(self._logs):
                if len(results) >= limit:
                    break

                if level is not None and record.level < level:
                    continue

                if logger_name is not None and logger_name not in record.logger_name:
                    continue

                if message_contains is not None and message_contains not in record.message:
                    continue

                if since is not None and record.timestamp < since:
                    continue

                if until is not None and record.timestamp > until:
                    continue

                results.append(record)

        return results

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات الـ logs."""
        with self._lock:
            level_counts = {}
            for level in LogLevel:
                level_counts[LEVEL_NAMES[level]] = sum(1 for r in self._logs if r.level == level)

            return {
                "total_logs": len(self._logs),
                "unique_correlations": len(self._by_correlation),
                "by_level": level_counts,
            }


# =============================================================================
# Enhanced Logger
# =============================================================================


class EnhancedLogger:
    """
    Logger محسن.

    يدعم:
    - Async handlers
    - Auto context propagation
    - Structured logging
    - Sampling
    """

    def __init__(
        self,
        name: str,
        level: LogLevel = LogLevel.INFO,
        service_name: str = "distributed_cluster",
        environment: str = "production",
    ):
        self.name = name
        self.level = level
        self.service_name = service_name
        self.environment = environment

        self._handlers: List[LogHandler] = []
        self._aggregator: Optional[LogAggregator] = None
        self._sample_rate: float = 1.0
        self._lock = threading.Lock()

        # Get hostname
        import socket

        try:
            self._host = socket.gethostname()
        except Exception:
            self._host = "unknown"

    def add_handler(self, handler: LogHandler) -> None:
        """إضافة معالج."""
        with self._lock:
            self._handlers.append(handler)

    def remove_handler(self, handler: LogHandler) -> None:
        """إزالة معالج."""
        with self._lock:
            if handler in self._handlers:
                self._handlers.remove(handler)

    def set_aggregator(self, aggregator: LogAggregator) -> None:
        """تعيين المجمع."""
        self._aggregator = aggregator

    def set_sample_rate(self, rate: float) -> None:
        """تعيين معدل العينات (0.0 - 1.0)."""
        self._sample_rate = max(0.0, min(1.0, rate))

    def _should_sample(self) -> bool:
        """هل يجب تسجيل هذا السجل؟"""
        if self._sample_rate >= 1.0:
            return True
        import random

        return random.random() < self._sample_rate

    def _create_record(
        self,
        level: LogLevel,
        message: str,
        exc_info: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> LogRecord:
        """إنشاء سجل."""
        # Get caller info
        import inspect

        frame = inspect.currentframe()
        source_file = None
        source_line = None
        source_function = None

        if frame:
            # Go up the call stack to find the actual caller
            for _ in range(4):  # Skip _create_record, _log, and level method
                if frame.f_back:
                    frame = frame.f_back

            source_file = frame.f_code.co_filename
            source_line = frame.f_lineno
            source_function = frame.f_code.co_name

        # Get exception info
        exception = None
        if exc_info:
            exception = traceback.format_exc()

        # Get trace context
        context = get_trace_context()

        return LogRecord(
            level=level,
            message=message,
            logger_name=self.name,
            correlation_id=context.get("correlation_id"),
            trace_id=context.get("trace_id"),
            span_id=context.get("span_id"),
            request_id=context.get("request_id"),
            user_id=context.get("user_id"),
            extra=extra or {},
            exception=exception,
            source_file=source_file,
            source_line=source_line,
            source_function=source_function,
            service_name=self.service_name,
            environment=self.environment,
            host=self._host,
        )

    def _log(
        self,
        level: LogLevel,
        message: str,
        exc_info: bool = False,
        **extra,
    ) -> None:
        """كتابة log."""
        if level < self.level:
            return

        if not self._should_sample():
            return

        record = self._create_record(level, message, exc_info, extra if extra else None)

        # Send to handlers
        with self._lock:
            for handler in self._handlers:
                try:
                    handler.emit(record)
                except Exception:
                    pass

        # Send to aggregator
        if self._aggregator:
            self._aggregator.add(record)

    def trace(self, message: str, **extra) -> None:
        """TRACE log."""
        self._log(LogLevel.TRACE, message, **extra)

    def debug(self, message: str, **extra) -> None:
        """DEBUG log."""
        self._log(LogLevel.DEBUG, message, **extra)

    def info(self, message: str, **extra) -> None:
        """INFO log."""
        self._log(LogLevel.INFO, message, **extra)

    def warning(self, message: str, **extra) -> None:
        """WARNING log."""
        self._log(LogLevel.WARNING, message, **extra)

    def error(self, message: str, exc_info: bool = False, **extra) -> None:
        """ERROR log."""
        self._log(LogLevel.ERROR, message, exc_info=exc_info, **extra)

    def critical(self, message: str, exc_info: bool = False, **extra) -> None:
        """CRITICAL log."""
        self._log(LogLevel.CRITICAL, message, exc_info=exc_info, **extra)

    def exception(self, message: str, **extra) -> None:
        """Log exception with traceback."""
        self._log(LogLevel.ERROR, message, exc_info=True, **extra)

    def close(self) -> None:
        """إغلاق Logger."""
        with self._lock:
            for handler in self._handlers:
                try:
                    handler.close()
                except Exception:
                    pass


# =============================================================================
# Logger Factory
# =============================================================================


class LoggerFactory:
    """
    مصنع الـ loggers.

    يدير إنشاء وتكوين الـ loggers.
    """

    def __init__(
        self,
        default_level: LogLevel = LogLevel.INFO,
        service_name: str = "distributed_cluster",
        environment: str = "production",
    ):
        self.default_level = default_level
        self.service_name = service_name
        self.environment = environment

        self._loggers: Dict[str, EnhancedLogger] = {}
        self._handlers: List[LogHandler] = []
        self._aggregator: Optional[LogAggregator] = None
        self._lock = threading.Lock()

    def add_handler(self, handler: LogHandler) -> None:
        """إضافة معالج لكل الـ loggers."""
        with self._lock:
            self._handlers.append(handler)
            for logger in self._loggers.values():
                logger.add_handler(handler)

    def set_aggregator(self, aggregator: LogAggregator) -> None:
        """تعيين المجمع لكل الـ loggers."""
        self._aggregator = aggregator
        with self._lock:
            for logger in self._loggers.values():
                logger.set_aggregator(aggregator)

    def get_logger(self, name: str, level: Optional[LogLevel] = None) -> EnhancedLogger:
        """الحصول على logger."""
        with self._lock:
            if name not in self._loggers:
                logger = EnhancedLogger(
                    name=name,
                    level=level or self.default_level,
                    service_name=self.service_name,
                    environment=self.environment,
                )

                for handler in self._handlers:
                    logger.add_handler(handler)

                if self._aggregator:
                    logger.set_aggregator(self._aggregator)

                self._loggers[name] = logger

            return self._loggers[name]

    def close_all(self) -> None:
        """إغلاق كل الـ loggers."""
        with self._lock:
            for logger in self._loggers.values():
                logger.close()
            self._loggers.clear()


# =============================================================================
# Decorators
# =============================================================================


T = TypeVar("T")


def with_correlation(
    func: Optional[Callable[..., T]] = None,
    *,
    auto_generate: bool = True,
) -> Callable[..., T]:
    """
    Decorator لإضافة correlation context.

    الاستخدام:
        @with_correlation
        def my_function():
            ...

        @with_correlation(auto_generate=False)
        def my_function(correlation_id: str):
            ...
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def sync_wrapper(*args, **kwargs):
            cid = kwargs.get("correlation_id") if not auto_generate else generate_correlation_id()
            with CorrelationContext(correlation_id=cid):
                return fn(*args, **kwargs)

        @wraps(fn)
        async def async_wrapper(*args, **kwargs):
            cid = kwargs.get("correlation_id") if not auto_generate else generate_correlation_id()
            with CorrelationContext(correlation_id=cid):
                return await fn(*args, **kwargs)

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    if func is not None:
        return decorator(func)
    return decorator


def log_execution(
    logger: EnhancedLogger,
    level: LogLevel = LogLevel.DEBUG,
    include_args: bool = False,
    include_result: bool = False,
):
    """
    Decorator لتسجيل تنفيذ الدالة.

    الاستخدام:
        @log_execution(logger, level=LogLevel.INFO)
        def my_function():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            func_name = func.__name__

            extra = {"function": func_name}
            if include_args:
                extra["args"] = str(args)[:100]
                extra["kwargs"] = str(kwargs)[:100]

            logger._log(level, f"Calling {func_name}", **extra)

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start

                result_extra = {"function": func_name, "duration_ms": duration * 1000}
                if include_result:
                    result_extra["result"] = str(result)[:100]

                logger._log(level, f"Completed {func_name}", **result_extra)
                return result

            except Exception as e:
                duration = time.time() - start
                logger.error(
                    f"Failed {func_name}",
                    exc_info=True,
                    function=func_name,
                    duration_ms=duration * 1000,
                    error=str(e),
                )
                raise

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            func_name = func.__name__

            extra = {"function": func_name}
            if include_args:
                extra["args"] = str(args)[:100]
                extra["kwargs"] = str(kwargs)[:100]

            logger._log(level, f"Calling {func_name}", **extra)

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start

                result_extra = {"function": func_name, "duration_ms": duration * 1000}
                if include_result:
                    result_extra["result"] = str(result)[:100]

                logger._log(level, f"Completed {func_name}", **result_extra)
                return result

            except Exception as e:
                duration = time.time() - start
                logger.error(
                    f"Failed {func_name}",
                    exc_info=True,
                    function=func_name,
                    duration_ms=duration * 1000,
                    error=str(e),
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# =============================================================================
# FastAPI Middleware
# =============================================================================


def create_logging_middleware(logger: EnhancedLogger):
    """
    إنشاء middleware للـ logging في FastAPI.

    الاستخدام:
        app.middleware("http")(create_logging_middleware(logger))
    """

    async def logging_middleware(request, call_next):
        # Generate or extract correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or generate_correlation_id()
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        user_id = request.headers.get("X-User-ID")

        with CorrelationContext(
            correlation_id=correlation_id,
            request_id=request_id,
            user_id=user_id,
            auto_generate=False,
        ):
            start = time.time()

            logger.info(
                "Request started",
                method=request.method,
                path=request.url.path,
                client=request.client.host if request.client else "unknown",
            )

            try:
                response = await call_next(request)
                duration = time.time() - start

                logger.info(
                    "Request completed",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration * 1000,
                )

                # Add correlation ID to response headers
                response.headers["X-Correlation-ID"] = correlation_id
                response.headers["X-Request-ID"] = request_id

                return response

            except Exception as e:
                duration = time.time() - start
                logger.error(
                    "Request failed",
                    exc_info=True,
                    method=request.method,
                    path=request.url.path,
                    duration_ms=duration * 1000,
                    error=str(e),
                )
                raise

    return logging_middleware


# =============================================================================
# Global Setup
# =============================================================================


_factory: Optional[LoggerFactory] = None


def setup_logging(
    level: LogLevel = LogLevel.INFO,
    service_name: str = "distributed_cluster",
    environment: str = "production",
    console: bool = True,
    console_json: bool = True,
    file_path: Optional[str] = None,
    aggregator: bool = True,
) -> LoggerFactory:
    """
    إعداد نظام الـ logging.

    الاستخدام:
        factory = setup_logging(
            level=LogLevel.INFO,
            console=True,
            file_path="logs/app.log",
        )
        logger = factory.get_logger("my_module")
    """
    global _factory

    _factory = LoggerFactory(
        default_level=level,
        service_name=service_name,
        environment=environment,
    )

    # Add console handler
    if console:
        _factory.add_handler(ConsoleHandler(level=level, json_format=console_json))

    # Add file handler
    if file_path:
        _factory.add_handler(AsyncFileHandler(file_path, level=level))

    # Add aggregator
    if aggregator:
        _factory.set_aggregator(LogAggregator())

    return _factory


def get_logger(name: str) -> EnhancedLogger:
    """الحصول على logger."""
    global _factory

    if _factory is None:
        _factory = setup_logging()

    return _factory.get_logger(name)
