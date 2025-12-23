"""
Logging Tests
=============

Tests for StructuredLogger, RotatingFileHandler, and LogCleaner.
"""

import asyncio
import gzip
import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from distributed_cluster.observability.logging import (
    LogLevel,
    LogContext,
    StructuredLogger,
    RotatingFileHandler,
    TimedRotatingFileHandler,
    LogCleaner,
    setup_logging,
    log_context,
    get_current_context,
)


class TestLogContext:
    """Tests for LogContext."""

    def test_context_creation(self):
        """Test basic context creation."""
        ctx = LogContext(
            request_id="req-123",
            job_id="job-456",
            worker_id="worker-1",
        )

        assert ctx.request_id == "req-123"
        assert ctx.job_id == "job-456"
        assert ctx.worker_id == "worker-1"

    def test_context_with_job(self):
        """Test creating context with job."""
        ctx = LogContext(worker_id="worker-1")
        new_ctx = ctx.with_job("job-789")

        assert new_ctx.job_id == "job-789"
        assert new_ctx.worker_id == "worker-1"
        # Original unchanged
        assert ctx.job_id is None

    def test_context_to_dict(self):
        """Test converting context to dict."""
        ctx = LogContext(
            job_id="job-123",
            extra={"custom": "value"},
        )

        d = ctx.to_dict()
        assert d["job_id"] == "job-123"
        assert d["custom"] == "value"

    def test_log_context_manager(self):
        """Test log context manager."""
        with log_context(job_id="job-123", custom_field="test"):
            ctx = get_current_context()
            assert ctx.job_id == "job-123"
            assert ctx.extra.get("custom_field") == "test"

        # Context restored after exit
        ctx = get_current_context()
        assert ctx.job_id is None


class TestStructuredLogger:
    """Tests for StructuredLogger."""

    def test_json_output(self, tmp_path):
        """Test JSON log output."""
        log_file = tmp_path / "test.log"

        with open(log_file, "w") as f:
            logger = StructuredLogger("test", output=f, json_output=True)
            logger.info("Test message", extra_field="extra_value")

        # Read and parse
        content = log_file.read_text().strip()
        log_entry = json.loads(content)

        assert log_entry["level"] == "INFO"
        assert log_entry["message"] == "Test message"
        assert log_entry["extra"]["extra_field"] == "extra_value"

    def test_log_levels(self, tmp_path):
        """Test log level filtering."""
        log_file = tmp_path / "test.log"

        with open(log_file, "w") as f:
            # Set level to WARNING
            logger = StructuredLogger("test", level=LogLevel.WARNING, output=f)
            logger.debug("Debug message")  # Should be filtered
            logger.info("Info message")    # Should be filtered
            logger.warning("Warning message")  # Should appear
            logger.error("Error message")  # Should appear

        content = log_file.read_text()
        assert "Debug message" not in content
        assert "Info message" not in content
        assert "Warning message" in content
        assert "Error message" in content

    def test_exception_logging(self, tmp_path):
        """Test exception logging."""
        log_file = tmp_path / "test.log"

        with open(log_file, "w") as f:
            logger = StructuredLogger("test", output=f, json_output=True)
            try:
                raise ValueError("Test error")
            except Exception:
                logger.exception("An error occurred")

        content = log_file.read_text().strip()
        log_entry = json.loads(content)

        assert "exception" in log_entry
        assert "ValueError" in log_entry["exception"]


class TestRotatingFileHandler:
    """Tests for RotatingFileHandler."""

    def test_basic_write(self, tmp_path):
        """Test basic file writing."""
        log_file = tmp_path / "test.log"
        handler = RotatingFileHandler(log_file, max_bytes=1000, backup_count=3)

        handler.write("Test log line\n")
        handler.flush()

        assert log_file.exists()
        assert "Test log line" in log_file.read_text()

        handler.close()

    def test_size_rotation(self, tmp_path):
        """Test rotation based on size."""
        log_file = tmp_path / "test.log"
        handler = RotatingFileHandler(
            log_file,
            max_bytes=100,  # Small size to trigger rotation
            backup_count=3,
            compress=False,
        )

        # Write enough to trigger rotation
        for i in range(20):
            handler.write(f"Log line {i}: " + "x" * 50 + "\n")
            handler.flush()

        handler.close()

        # Check backups were created
        assert log_file.exists()
        # At least one backup should exist
        backup_files = list(tmp_path.glob("*.log.*"))
        assert len(backup_files) > 0

    def test_compression(self, tmp_path):
        """Test compressed rotation."""
        log_file = tmp_path / "test.log"
        handler = RotatingFileHandler(
            log_file,
            max_bytes=100,
            backup_count=3,
            compress=True,
        )

        # Write enough to trigger rotation
        for i in range(20):
            handler.write(f"Log line {i}: " + "x" * 50 + "\n")
            handler.flush()

        handler.close()

        # Check for compressed backups
        compressed_files = list(tmp_path.glob("*.gz"))
        assert len(compressed_files) > 0

        # Verify compressed file is readable
        with gzip.open(compressed_files[0], "rt") as f:
            content = f.read()
            assert "Log line" in content


class TestTimedRotatingFileHandler:
    """Tests for TimedRotatingFileHandler."""

    def test_hourly_rotation_calculation(self, tmp_path):
        """Test hourly rotation time calculation."""
        log_file = tmp_path / "test.log"
        handler = TimedRotatingFileHandler(
            log_file,
            when="H",
            backup_count=24,
        )

        now = datetime.now()
        expected = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        assert handler._next_rotation is not None
        # Allow some slack for test execution time
        diff = abs((handler._next_rotation - expected).total_seconds())
        assert diff < 2

        handler.close()

    def test_daily_rotation_calculation(self, tmp_path):
        """Test daily rotation time calculation."""
        log_file = tmp_path / "test.log"
        handler = TimedRotatingFileHandler(
            log_file,
            when="D",
            backup_count=7,
        )

        now = datetime.now()
        expected = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

        assert handler._next_rotation is not None
        diff = abs((handler._next_rotation - expected).total_seconds())
        assert diff < 2

        handler.close()


class TestLogCleaner:
    """Tests for LogCleaner."""

    def test_cleanup_old_files(self, tmp_path):
        """Test cleaning up old log files."""
        # Create old log files
        old_time = time.time() - (40 * 24 * 3600)  # 40 days ago

        old_file = tmp_path / "old.log"
        old_file.write_text("old content")
        os.utime(old_file, (old_time, old_time))

        new_file = tmp_path / "new.log"
        new_file.write_text("new content")

        cleaner = LogCleaner(
            log_dir=tmp_path,
            max_age_days=30,
        )

        deleted, size = cleaner.cleanup_now()

        # Old file should be deleted
        assert not old_file.exists()
        # New file should remain
        assert new_file.exists()
        assert deleted >= 1

    def test_log_stats(self, tmp_path):
        """Test getting log statistics."""
        # Create some log files
        for i in range(5):
            f = tmp_path / f"test{i}.log"
            f.write_text("content " * 100)

        cleaner = LogCleaner(log_dir=tmp_path)
        stats = cleaner.get_log_stats()

        assert stats["total_files"] == 5
        assert stats["total_size"] > 0
        assert stats["total_size_mb"] >= 0

    @pytest.mark.asyncio
    async def test_async_cleanup_loop(self, tmp_path):
        """Test async cleanup loop."""
        cleaner = LogCleaner(
            log_dir=tmp_path,
            max_age_days=30,
            check_interval=0.1,  # Very short for testing
        )

        await cleaner.start()
        await asyncio.sleep(0.3)  # Let it run a few cycles
        await cleaner.stop()

        # Should complete without error


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_size_based_rotation(self, tmp_path):
        """Test setting up size-based rotation."""
        logger, cleaner = setup_logging(
            log_dir=tmp_path,
            rotation="size",
            max_bytes=1000,
            backup_count=3,
            enable_cleanup=True,
        )

        assert logger is not None
        assert cleaner is not None

        # Write some logs
        logger.info("Test message")

        # Check log file exists
        log_file = tmp_path / "app.log"
        assert log_file.exists()

    def test_setup_time_based_rotation(self, tmp_path):
        """Test setting up time-based rotation."""
        logger, cleaner = setup_logging(
            log_dir=tmp_path,
            rotation="time",
            when="D",
            backup_count=7,
            enable_cleanup=False,
        )

        assert logger is not None
        assert cleaner is None  # Disabled

        logger.info("Test message")
