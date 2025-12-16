"""
Structured Logging - تسجيل منظّم
==================================

تسجيل منظّم (Structured Logging) للنظام:

- JSON output للتحليل الآلي
- Context propagation
- Log levels
- Correlation IDs

**لماذا Structured Logging؟**
- سهولة البحث والتحليل
- Integration مع أدوات مثل ELK/Loki
- تتبع العمليات عبر النظام
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Optional, Any, Dict
import json
import sys
import threading
import traceback
from contextlib import contextmanager


class LogLevel(IntEnum):
    """مستويات التسجيل."""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


@dataclass
class LogContext:
    """
    سياق التسجيل.

    يُحمل عبر العمليات لربط الـ logs.
    """
    request_id: Optional[str] = None
    job_id: Optional[str] = None
    worker_id: Optional[str] = None
    user_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def with_job(self, job_id: str) -> LogContext:
        """إنشاء سياق جديد مع job_id."""
        return LogContext(
            request_id=self.request_id,
            job_id=job_id,
            worker_id=self.worker_id,
            user_id=self.user_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
            extra=self.extra.copy(),
        )

    def with_worker(self, worker_id: str) -> LogContext:
        """إنشاء سياق جديد مع worker_id."""
        return LogContext(
            request_id=self.request_id,
            job_id=self.job_id,
            worker_id=worker_id,
            user_id=self.user_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
            extra=self.extra.copy(),
        )

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        d = {}
        if self.request_id:
            d["request_id"] = self.request_id
        if self.job_id:
            d["job_id"] = self.job_id
        if self.worker_id:
            d["worker_id"] = self.worker_id
        if self.user_id:
            d["user_id"] = self.user_id
        if self.trace_id:
            d["trace_id"] = self.trace_id
        if self.span_id:
            d["span_id"] = self.span_id
        if self.extra:
            d.update(self.extra)
        return d


# Thread-local context storage
_context_var = threading.local()


def get_current_context() -> LogContext:
    """الحصول على السياق الحالي."""
    return getattr(_context_var, "context", LogContext())


def set_current_context(ctx: LogContext) -> None:
    """تعيين السياق الحالي."""
    _context_var.context = ctx


@contextmanager
def log_context(**kwargs):
    """
    Context manager لتعيين سياق مؤقت.

    Example:
        with log_context(job_id="job-123"):
            logger.info("Processing job")
    """
    old_ctx = get_current_context()
    new_ctx = LogContext(
        request_id=kwargs.get("request_id", old_ctx.request_id),
        job_id=kwargs.get("job_id", old_ctx.job_id),
        worker_id=kwargs.get("worker_id", old_ctx.worker_id),
        user_id=kwargs.get("user_id", old_ctx.user_id),
        trace_id=kwargs.get("trace_id", old_ctx.trace_id),
        span_id=kwargs.get("span_id", old_ctx.span_id),
        extra={**old_ctx.extra, **{k: v for k, v in kwargs.items()
                                   if k not in ("request_id", "job_id", "worker_id",
                                                "user_id", "trace_id", "span_id")}},
    )
    set_current_context(new_ctx)
    try:
        yield new_ctx
    finally:
        set_current_context(old_ctx)


class StructuredLogger:
    """
    Logger منظّم.

    يُخرج logs بصيغة JSON مع:
    - timestamp
    - level
    - message
    - context (job_id, worker_id, etc.)
    - extra fields
    """

    def __init__(
        self,
        name: str,
        level: LogLevel = LogLevel.INFO,
        output: Any = None,  # File-like object
        json_output: bool = True,
    ):
        self.name = name
        self.level = level
        self.output = output or sys.stderr
        self.json_output = json_output
        self._lock = threading.Lock()

    def _format_message(
        self,
        level: LogLevel,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
    ) -> str:
        """تنسيق الرسالة."""
        ctx = get_current_context()

        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level.name,
            "logger": self.name,
            "message": message,
        }

        # Add context
        ctx_dict = ctx.to_dict()
        if ctx_dict:
            log_entry["context"] = ctx_dict

        # Add extra fields
        if extra:
            log_entry["extra"] = extra

        # Add exception info
        if exc_info:
            log_entry["exception"] = traceback.format_exc()

        if self.json_output:
            return json.dumps(log_entry, default=str)
        else:
            # Human-readable format
            parts = [
                f"{log_entry['timestamp']}",
                f"[{level.name}]",
                f"{self.name}:",
                message,
            ]
            if ctx_dict:
                parts.append(f"ctx={ctx_dict}")
            if extra:
                parts.append(f"extra={extra}")
            return " ".join(parts)

    def _log(
        self,
        level: LogLevel,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
    ) -> None:
        """كتابة log."""
        if level < self.level:
            return

        formatted = self._format_message(level, message, extra, exc_info)

        with self._lock:
            self.output.write(formatted + "\n")
            self.output.flush()

    def debug(self, message: str, **extra) -> None:
        """DEBUG log."""
        self._log(LogLevel.DEBUG, message, extra if extra else None)

    def info(self, message: str, **extra) -> None:
        """INFO log."""
        self._log(LogLevel.INFO, message, extra if extra else None)

    def warning(self, message: str, **extra) -> None:
        """WARNING log."""
        self._log(LogLevel.WARNING, message, extra if extra else None)

    def error(self, message: str, exc_info: bool = False, **extra) -> None:
        """ERROR log."""
        self._log(LogLevel.ERROR, message, extra if extra else None, exc_info)

    def critical(self, message: str, exc_info: bool = False, **extra) -> None:
        """CRITICAL log."""
        self._log(LogLevel.CRITICAL, message, extra if extra else None, exc_info)

    def exception(self, message: str, **extra) -> None:
        """Log exception with traceback."""
        self._log(LogLevel.ERROR, message, extra if extra else None, exc_info=True)

    # ==================== Convenience Methods ====================

    def job_submitted(self, job_id: str, name: str) -> None:
        """تسجيل job submitted."""
        with log_context(job_id=job_id):
            self.info("Job submitted", name=name)

    def job_scheduled(self, job_id: str, worker_id: str) -> None:
        """تسجيل job scheduled."""
        with log_context(job_id=job_id, worker_id=worker_id):
            self.info("Job scheduled")

    def job_started(self, job_id: str, worker_id: str) -> None:
        """تسجيل job started."""
        with log_context(job_id=job_id, worker_id=worker_id):
            self.info("Job started")

    def job_completed(
        self,
        job_id: str,
        worker_id: str,
        success: bool,
        execution_time: float,
    ) -> None:
        """تسجيل job completed."""
        with log_context(job_id=job_id, worker_id=worker_id):
            status = "succeeded" if success else "failed"
            self.info(
                f"Job {status}",
                success=success,
                execution_time_seconds=execution_time,
            )

    def worker_registered(self, worker_id: str, hostname: str) -> None:
        """تسجيل worker registered."""
        with log_context(worker_id=worker_id):
            self.info("Worker registered", hostname=hostname)

    def worker_offline(self, worker_id: str, reason: str) -> None:
        """تسجيل worker offline."""
        with log_context(worker_id=worker_id):
            self.warning("Worker went offline", reason=reason)

    def scheduler_decision(
        self,
        jobs_scheduled: int,
        decision_time_ms: float,
    ) -> None:
        """تسجيل scheduler decision."""
        self.debug(
            "Scheduler tick",
            jobs_scheduled=jobs_scheduled,
            decision_time_ms=decision_time_ms,
        )


# Global logger factory
_loggers: Dict[str, StructuredLogger] = {}


def get_logger(name: str, level: LogLevel = LogLevel.INFO) -> StructuredLogger:
    """الحصول على logger."""
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name, level)
    return _loggers[name]


# Default logger
default_logger = get_logger("distributed_cluster")
