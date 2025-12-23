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

import asyncio
import gzip
import json
import os
import shutil
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


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
        extra={
            **old_ctx.extra,
            **{
                k: v
                for k, v in kwargs.items()
                if k not in ("request_id", "job_id", "worker_id", "user_id", "trace_id", "span_id")
            },
        },
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


# =============================================================================
# Log Rotation and Cleanup
# =============================================================================


class RotatingFileHandler:
    """
    معالج ملفات مع rotation.

    يدعم:
    - Rotation حسب الحجم
    - Rotation حسب الوقت
    - ضغط الملفات القديمة (اختياري)
    - حذف الملفات القديمة

    الاستخدام:
        handler = RotatingFileHandler(
            filename="app.log",
            max_bytes=10_000_000,      # 10 MB
            backup_count=5,
            compress=True,
        )

        logger = StructuredLogger("app", output=handler)
    """

    def __init__(
        self,
        filename: Union[str, Path],
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB default
        backup_count: int = 5,
        compress: bool = True,
        encoding: str = "utf-8",
    ):
        self.filename = Path(filename)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.compress = compress
        self.encoding = encoding

        self._lock = threading.Lock()
        self._file: Optional[Any] = None

        # Ensure directory exists
        self.filename.parent.mkdir(parents=True, exist_ok=True)

        # Open the file
        self._open()

    def _open(self) -> None:
        """فتح الملف."""
        self._file = open(self.filename, "a", encoding=self.encoding)

    def _close(self) -> None:
        """إغلاق الملف."""
        if self._file:
            self._file.close()
            self._file = None

    def write(self, data: str) -> None:
        """كتابة إلى الملف."""
        with self._lock:
            if self._should_rotate():
                self._do_rotate()

            if self._file:
                self._file.write(data)

    def flush(self) -> None:
        """تفريغ buffer."""
        with self._lock:
            if self._file:
                self._file.flush()

    def _should_rotate(self) -> bool:
        """هل يجب تدوير الملف؟"""
        if not self.filename.exists():
            return False

        return self.filename.stat().st_size >= self.max_bytes

    def _do_rotate(self) -> None:
        """تنفيذ التدوير."""
        self._close()

        # Rotate existing backups
        for i in range(self.backup_count - 1, 0, -1):
            src = self._get_backup_name(i)
            dst = self._get_backup_name(i + 1)

            if src.exists():
                # Delete oldest if at limit
                if i + 1 > self.backup_count:
                    src.unlink()
                else:
                    shutil.move(str(src), str(dst))

        # Move current file to backup 1
        if self.filename.exists():
            backup_name = self._get_backup_name(1)
            shutil.move(str(self.filename), str(backup_name))

            # Compress if enabled
            if self.compress:
                self._compress_file(backup_name)

        # Reopen for new writes
        self._open()

    def _get_backup_name(self, index: int) -> Path:
        """الحصول على اسم ملف النسخة الاحتياطية."""
        suffix = f".{index}"
        if self.compress:
            suffix += ".gz"
        return self.filename.with_suffix(self.filename.suffix + suffix)

    def _compress_file(self, filepath: Path) -> None:
        """ضغط ملف."""
        if not filepath.exists():
            return

        compressed_path = filepath.with_suffix(filepath.suffix + ".gz")

        try:
            with open(filepath, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove uncompressed file
            filepath.unlink()
        except Exception:
            # If compression fails, keep the uncompressed file
            pass

    def close(self) -> None:
        """إغلاق المعالج."""
        with self._lock:
            self._close()


class TimedRotatingFileHandler(RotatingFileHandler):
    """
    معالج ملفات مع rotation زمني.

    يدعم التدوير:
    - كل ساعة ('H')
    - يومياً ('D')
    - أسبوعياً ('W')
    - شهرياً ('M')

    الاستخدام:
        handler = TimedRotatingFileHandler(
            filename="app.log",
            when="D",              # Daily
            backup_count=7,        # Keep 7 days
            compress=True,
        )
    """

    def __init__(
        self,
        filename: Union[str, Path],
        when: str = "D",  # H=Hour, D=Day, W=Week, M=Month
        backup_count: int = 7,
        compress: bool = True,
        encoding: str = "utf-8",
    ):
        self.when = when.upper()
        self._next_rotation: Optional[datetime] = None

        # Don't use size-based rotation
        super().__init__(
            filename=filename,
            max_bytes=float("inf"),  # type: ignore
            backup_count=backup_count,
            compress=compress,
            encoding=encoding,
        )

        self._calculate_next_rotation()

    def _calculate_next_rotation(self) -> None:
        """حساب وقت التدوير التالي."""
        now = datetime.now()

        if self.when == "H":
            # Next hour
            self._next_rotation = now.replace(
                minute=0, second=0, microsecond=0
            ) + timedelta(hours=1)

        elif self.when == "D":
            # Next day at midnight
            self._next_rotation = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)

        elif self.when == "W":
            # Next Monday at midnight
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            self._next_rotation = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=days_until_monday)

        elif self.when == "M":
            # First day of next month
            if now.month == 12:
                self._next_rotation = now.replace(
                    year=now.year + 1, month=1, day=1,
                    hour=0, minute=0, second=0, microsecond=0
                )
            else:
                self._next_rotation = now.replace(
                    month=now.month + 1, day=1,
                    hour=0, minute=0, second=0, microsecond=0
                )

    def _should_rotate(self) -> bool:
        """هل يجب تدوير الملف؟"""
        if self._next_rotation is None:
            return False

        return datetime.now() >= self._next_rotation

    def _do_rotate(self) -> None:
        """تنفيذ التدوير."""
        super()._do_rotate()
        self._calculate_next_rotation()

    def _get_backup_name(self, index: int) -> Path:
        """الحصول على اسم ملف النسخة الاحتياطية مع التاريخ."""
        now = datetime.now()
        date_suffix = now.strftime("%Y%m%d")

        if self.when == "H":
            date_suffix = now.strftime("%Y%m%d_%H")

        suffix = f".{date_suffix}.{index}"
        if self.compress:
            suffix += ".gz"
        return self.filename.with_suffix(self.filename.suffix + suffix)


class LogCleaner:
    """
    منظف ملفات اللوغ.

    ينظف الملفات القديمة دورياً.

    الاستخدام:
        cleaner = LogCleaner(
            log_dir="/var/log/app",
            max_age_days=30,
            patterns=["*.log", "*.log.*.gz"],
        )
        await cleaner.start()
    """

    def __init__(
        self,
        log_dir: Union[str, Path],
        max_age_days: int = 30,
        patterns: Optional[List[str]] = None,
        check_interval: float = 3600.0,  # 1 hour
        on_delete: Optional[Callable[[Path], None]] = None,
    ):
        self.log_dir = Path(log_dir)
        self.max_age_days = max_age_days
        self.patterns = patterns or ["*.log", "*.log.*", "*.log.*.gz"]
        self.check_interval = check_interval
        self.on_delete = on_delete

        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """بدء التنظيف الدوري."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """إيقاف التنظيف."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _cleanup_loop(self) -> None:
        """حلقة التنظيف الدوري."""
        while self._running:
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None, self._do_cleanup
                )
            except Exception:
                pass

            await asyncio.sleep(self.check_interval)

    def _do_cleanup(self) -> None:
        """تنفيذ التنظيف."""
        if not self.log_dir.exists():
            return

        cutoff_time = time.time() - (self.max_age_days * 24 * 3600)
        deleted_count = 0
        deleted_size = 0

        for pattern in self.patterns:
            for filepath in self.log_dir.glob(pattern):
                if not filepath.is_file():
                    continue

                try:
                    if filepath.stat().st_mtime < cutoff_time:
                        file_size = filepath.stat().st_size
                        filepath.unlink()
                        deleted_count += 1
                        deleted_size += file_size

                        if self.on_delete:
                            try:
                                self.on_delete(filepath)
                            except Exception:
                                pass

                except (OSError, PermissionError):
                    pass

        return deleted_count, deleted_size

    def cleanup_now(self) -> tuple[int, int]:
        """تنظيف فوري."""
        return self._do_cleanup()

    def get_log_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات اللوغ."""
        if not self.log_dir.exists():
            return {"total_files": 0, "total_size": 0}

        total_files = 0
        total_size = 0
        oldest_file: Optional[datetime] = None
        newest_file: Optional[datetime] = None

        for pattern in self.patterns:
            for filepath in self.log_dir.glob(pattern):
                if not filepath.is_file():
                    continue

                try:
                    stat = filepath.stat()
                    total_files += 1
                    total_size += stat.st_size

                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    if oldest_file is None or mtime < oldest_file:
                        oldest_file = mtime
                    if newest_file is None or mtime > newest_file:
                        newest_file = mtime

                except (OSError, PermissionError):
                    pass

        return {
            "total_files": total_files,
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "oldest_file": oldest_file.isoformat() if oldest_file else None,
            "newest_file": newest_file.isoformat() if newest_file else None,
        }


def setup_logging(
    log_dir: Union[str, Path] = "logs",
    log_level: LogLevel = LogLevel.INFO,
    rotation: str = "size",  # "size" or "time"
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    when: str = "D",  # For time-based rotation
    backup_count: int = 5,
    compress: bool = True,
    json_output: bool = True,
    enable_cleanup: bool = True,
    max_age_days: int = 30,
) -> tuple[StructuredLogger, Optional[LogCleaner]]:
    """
    إعداد التسجيل مع rotation و cleanup.

    الاستخدام:
        logger, cleaner = setup_logging(
            log_dir="logs",
            rotation="time",
            when="D",
            backup_count=7,
            max_age_days=30,
        )

        # Start cleanup
        await cleaner.start()
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    log_file = log_path / "app.log"

    # Create handler
    if rotation == "time":
        handler = TimedRotatingFileHandler(
            filename=log_file,
            when=when,
            backup_count=backup_count,
            compress=compress,
        )
    else:
        handler = RotatingFileHandler(
            filename=log_file,
            max_bytes=max_bytes,
            backup_count=backup_count,
            compress=compress,
        )

    # Create logger
    logger = StructuredLogger(
        name="app",
        level=log_level,
        output=handler,
        json_output=json_output,
    )

    # Create cleaner
    cleaner = None
    if enable_cleanup:
        cleaner = LogCleaner(
            log_dir=log_path,
            max_age_days=max_age_days,
        )

    return logger, cleaner
