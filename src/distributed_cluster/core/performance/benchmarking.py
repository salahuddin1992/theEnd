# -*- coding: utf-8 -*-
"""
Performance Benchmarking Utilities for NebulaCompute.

أدوات قياس الأداء لنظام NebulaCompute.

This module provides:
- Function timing decorators
- Memory profiling
- CPU profiling
- I/O benchmarking
- Network latency testing
- Comprehensive benchmark reports
"""

import asyncio
import functools
import gc
import logging
import os
import statistics
import sys
import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class BenchmarkUnit(str, Enum):
    """Units for benchmark measurements."""

    NANOSECONDS = "ns"
    MICROSECONDS = "us"
    MILLISECONDS = "ms"
    SECONDS = "s"
    BYTES = "B"
    KILOBYTES = "KB"
    MEGABYTES = "MB"
    GIGABYTES = "GB"


@dataclass
class TimingResult:
    """
    Result of a timing benchmark.

    نتيجة قياس الوقت.
    """

    name: str
    iterations: int
    total_time: float  # seconds
    min_time: float
    max_time: float
    mean_time: float
    median_time: float
    std_dev: float
    percentile_95: float
    percentile_99: float
    throughput: float  # operations per second
    unit: BenchmarkUnit = BenchmarkUnit.MILLISECONDS

    def __str__(self) -> str:
        return (
            f"TimingResult(name='{self.name}', iterations={self.iterations}, "
            f"mean={self.mean_time:.4f}{self.unit.value}, "
            f"p95={self.percentile_95:.4f}{self.unit.value}, "
            f"throughput={self.throughput:.2f} ops/s)"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "iterations": self.iterations,
            "total_time_s": self.total_time,
            "min_time": self.min_time,
            "max_time": self.max_time,
            "mean_time": self.mean_time,
            "median_time": self.median_time,
            "std_dev": self.std_dev,
            "percentile_95": self.percentile_95,
            "percentile_99": self.percentile_99,
            "throughput_ops_per_s": self.throughput,
            "unit": self.unit.value,
        }


@dataclass
class MemoryResult:
    """
    Result of a memory benchmark.

    نتيجة قياس الذاكرة.
    """

    name: str
    peak_memory_bytes: int
    current_memory_bytes: int
    allocated_blocks: int
    memory_diff_bytes: int
    top_allocations: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def peak_memory_mb(self) -> float:
        """Peak memory in MB."""
        return self.peak_memory_bytes / (1024 * 1024)

    @property
    def current_memory_mb(self) -> float:
        """Current memory in MB."""
        return self.current_memory_bytes / (1024 * 1024)

    def __str__(self) -> str:
        return (
            f"MemoryResult(name='{self.name}', "
            f"peak={self.peak_memory_mb:.2f}MB, "
            f"diff={self.memory_diff_bytes / 1024:.2f}KB)"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "peak_memory_bytes": self.peak_memory_bytes,
            "peak_memory_mb": self.peak_memory_mb,
            "current_memory_bytes": self.current_memory_bytes,
            "current_memory_mb": self.current_memory_mb,
            "allocated_blocks": self.allocated_blocks,
            "memory_diff_bytes": self.memory_diff_bytes,
            "top_allocations": self.top_allocations,
        }


@dataclass
class BenchmarkReport:
    """
    Comprehensive benchmark report.

    تقرير قياس الأداء الشامل.
    """

    name: str
    description: str
    timestamp: datetime
    timing_results: List[TimingResult] = field(default_factory=list)
    memory_results: List[MemoryResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_timing(self, result: TimingResult) -> None:
        """Add timing result."""
        self.timing_results.append(result)

    def add_memory(self, result: MemoryResult) -> None:
        """Add memory result."""
        self.memory_results.append(result)

    def summary(self) -> str:
        """Generate summary string."""
        lines = [
            f"=== Benchmark Report: {self.name} ===",
            f"Description: {self.description}",
            f"Timestamp: {self.timestamp.isoformat()}",
            "",
            "--- Timing Results ---",
        ]

        for tr in self.timing_results:
            lines.append(
                f"  {tr.name}: mean={tr.mean_time:.4f}{tr.unit.value}, "
                f"p95={tr.percentile_95:.4f}{tr.unit.value}, "
                f"throughput={tr.throughput:.2f} ops/s"
            )

        lines.append("")
        lines.append("--- Memory Results ---")

        for mr in self.memory_results:
            lines.append(
                f"  {mr.name}: peak={mr.peak_memory_mb:.2f}MB, "
                f"diff={mr.memory_diff_bytes / 1024:.2f}KB"
            )

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "timing_results": [tr.to_dict() for tr in self.timing_results],
            "memory_results": [mr.to_dict() for mr in self.memory_results],
            "metadata": self.metadata,
        }


class Benchmarker:
    """
    Performance benchmarking utility.

    أداة قياس الأداء.

    Usage:
        benchmarker = Benchmarker("My Benchmark")

        # Time a function
        result = benchmarker.time_function(my_func, iterations=1000)

        # Profile memory
        with benchmarker.memory_profile("operation"):
            # ... code to profile ...

        # Generate report
        report = benchmarker.generate_report()
    """

    def __init__(
        self,
        name: str = "Benchmark",
        description: str = "",
        warmup_iterations: int = 10,
    ):
        """
        Initialize benchmarker.

        Args:
            name: Benchmark name
            description: Description
            warmup_iterations: Number of warmup iterations before timing
        """
        self.name = name
        self.description = description
        self.warmup_iterations = warmup_iterations
        self._timing_results: List[TimingResult] = []
        self._memory_results: List[MemoryResult] = []
        self._metadata: Dict[str, Any] = {
            "python_version": sys.version,
            "platform": sys.platform,
            "cpu_count": os.cpu_count(),
        }

    def time_function(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: Optional[Dict] = None,
        iterations: int = 100,
        name: Optional[str] = None,
        unit: BenchmarkUnit = BenchmarkUnit.MILLISECONDS,
    ) -> TimingResult:
        """
        Time a synchronous function.

        قياس وقت تنفيذ دالة متزامنة.

        Args:
            func: Function to benchmark
            args: Positional arguments
            kwargs: Keyword arguments
            iterations: Number of iterations
            name: Result name (defaults to function name)
            unit: Time unit for results

        Returns:
            TimingResult with statistics
        """
        kwargs = kwargs or {}
        func_name = name or getattr(func, "__name__", "anonymous")

        # Warmup
        for _ in range(self.warmup_iterations):
            func(*args, **kwargs)

        # Force garbage collection before timing
        gc.collect()

        # Timing runs
        times = []
        start_total = time.perf_counter()

        for _ in range(iterations):
            start = time.perf_counter()
            func(*args, **kwargs)
            end = time.perf_counter()
            times.append(end - start)

        end_total = time.perf_counter()
        total_time = end_total - start_total

        # Convert to requested unit
        multiplier = self._get_time_multiplier(unit)
        times_converted = [t * multiplier for t in times]

        # Calculate statistics
        result = TimingResult(
            name=func_name,
            iterations=iterations,
            total_time=total_time,
            min_time=min(times_converted),
            max_time=max(times_converted),
            mean_time=statistics.mean(times_converted),
            median_time=statistics.median(times_converted),
            std_dev=statistics.stdev(times_converted) if len(times_converted) > 1 else 0,
            percentile_95=self._percentile(times_converted, 95),
            percentile_99=self._percentile(times_converted, 99),
            throughput=iterations / total_time if total_time > 0 else 0,
            unit=unit,
        )

        self._timing_results.append(result)
        return result

    async def time_async_function(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: Optional[Dict] = None,
        iterations: int = 100,
        name: Optional[str] = None,
        unit: BenchmarkUnit = BenchmarkUnit.MILLISECONDS,
    ) -> TimingResult:
        """
        Time an asynchronous function.

        قياس وقت تنفيذ دالة غير متزامنة.

        Args:
            func: Async function to benchmark
            args: Positional arguments
            kwargs: Keyword arguments
            iterations: Number of iterations
            name: Result name
            unit: Time unit

        Returns:
            TimingResult with statistics
        """
        kwargs = kwargs or {}
        func_name = name or getattr(func, "__name__", "anonymous")

        # Warmup
        for _ in range(self.warmup_iterations):
            await func(*args, **kwargs)

        # Force garbage collection
        gc.collect()

        # Timing runs
        times = []
        start_total = time.perf_counter()

        for _ in range(iterations):
            start = time.perf_counter()
            await func(*args, **kwargs)
            end = time.perf_counter()
            times.append(end - start)

        end_total = time.perf_counter()
        total_time = end_total - start_total

        # Convert to requested unit
        multiplier = self._get_time_multiplier(unit)
        times_converted = [t * multiplier for t in times]

        result = TimingResult(
            name=func_name,
            iterations=iterations,
            total_time=total_time,
            min_time=min(times_converted),
            max_time=max(times_converted),
            mean_time=statistics.mean(times_converted),
            median_time=statistics.median(times_converted),
            std_dev=statistics.stdev(times_converted) if len(times_converted) > 1 else 0,
            percentile_95=self._percentile(times_converted, 95),
            percentile_99=self._percentile(times_converted, 99),
            throughput=iterations / total_time if total_time > 0 else 0,
            unit=unit,
        )

        self._timing_results.append(result)
        return result

    @contextmanager
    def memory_profile(self, name: str = "memory_profile"):
        """
        Context manager for memory profiling.

        مدير سياق لتحليل الذاكرة.

        Usage:
            with benchmarker.memory_profile("my_operation"):
                # code to profile
        """
        gc.collect()
        tracemalloc.start()

        snapshot_start = tracemalloc.take_snapshot()
        start_stats = tracemalloc.get_traced_memory()

        try:
            yield
        finally:
            gc.collect()
            snapshot_end = tracemalloc.take_snapshot()
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            # Get top allocations
            top_stats = snapshot_end.compare_to(snapshot_start, "lineno")
            top_allocations = []
            for stat in top_stats[:10]:
                top_allocations.append(
                    {
                        "file": str(stat.traceback),
                        "size_diff": stat.size_diff,
                        "count_diff": stat.count_diff,
                    }
                )

            result = MemoryResult(
                name=name,
                peak_memory_bytes=peak,
                current_memory_bytes=current,
                allocated_blocks=len(top_stats),
                memory_diff_bytes=current - start_stats[0],
                top_allocations=top_allocations,
            )

            self._memory_results.append(result)

    def benchmark_io(
        self,
        file_path: str,
        data_size_mb: float = 10,
        iterations: int = 5,
    ) -> Dict[str, TimingResult]:
        """
        Benchmark file I/O operations.

        قياس أداء عمليات الملفات.

        Args:
            file_path: Path for test file
            data_size_mb: Size of test data in MB
            iterations: Number of iterations

        Returns:
            Dictionary with read/write timing results
        """

        data = os.urandom(int(data_size_mb * 1024 * 1024))

        results = {}

        # Benchmark write
        def write_test():
            with open(file_path, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())

        results["write"] = self.time_function(
            write_test,
            iterations=iterations,
            name=f"write_{data_size_mb}MB",
        )

        # Benchmark read
        def read_test():
            with open(file_path, "rb") as f:
                f.read()

        results["read"] = self.time_function(
            read_test,
            iterations=iterations,
            name=f"read_{data_size_mb}MB",
        )

        # Calculate throughput
        write_throughput_mbps = (
            data_size_mb * iterations / results["write"].total_time
        )
        read_throughput_mbps = (
            data_size_mb * iterations / results["read"].total_time
        )

        self._metadata["io_write_throughput_mbps"] = write_throughput_mbps
        self._metadata["io_read_throughput_mbps"] = read_throughput_mbps

        # Cleanup
        try:
            os.remove(file_path)
        except OSError:
            pass

        return results

    async def benchmark_network_latency(
        self,
        host: str = "127.0.0.1",
        port: int = 80,
        iterations: int = 10,
        timeout: float = 5.0,
    ) -> TimingResult:
        """
        Benchmark network latency to a host.

        قياس تأخير الشبكة.

        Args:
            host: Target host
            port: Target port
            iterations: Number of connection attempts
            timeout: Connection timeout

        Returns:
            TimingResult with latency statistics
        """
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=timeout,
                )
                writer.close()
                await writer.wait_closed()
                end = time.perf_counter()
                times.append(end - start)
            except (OSError, asyncio.TimeoutError):
                times.append(timeout)

        times_ms = [t * 1000 for t in times]

        result = TimingResult(
            name=f"latency_{host}:{port}",
            iterations=iterations,
            total_time=sum(times),
            min_time=min(times_ms),
            max_time=max(times_ms),
            mean_time=statistics.mean(times_ms),
            median_time=statistics.median(times_ms),
            std_dev=statistics.stdev(times_ms) if len(times_ms) > 1 else 0,
            percentile_95=self._percentile(times_ms, 95),
            percentile_99=self._percentile(times_ms, 99),
            throughput=iterations / sum(times) if sum(times) > 0 else 0,
            unit=BenchmarkUnit.MILLISECONDS,
        )

        self._timing_results.append(result)
        return result

    def generate_report(self) -> BenchmarkReport:
        """
        Generate comprehensive benchmark report.

        إنشاء تقرير قياس الأداء الشامل.
        """
        return BenchmarkReport(
            name=self.name,
            description=self.description,
            timestamp=datetime.now(),
            timing_results=self._timing_results.copy(),
            memory_results=self._memory_results.copy(),
            metadata=self._metadata.copy(),
        )

    def reset(self) -> None:
        """Reset all collected results."""
        self._timing_results.clear()
        self._memory_results.clear()

    @staticmethod
    def _get_time_multiplier(unit: BenchmarkUnit) -> float:
        """Get multiplier to convert seconds to target unit."""
        multipliers = {
            BenchmarkUnit.NANOSECONDS: 1e9,
            BenchmarkUnit.MICROSECONDS: 1e6,
            BenchmarkUnit.MILLISECONDS: 1e3,
            BenchmarkUnit.SECONDS: 1,
        }
        return multipliers.get(unit, 1e3)

    @staticmethod
    def _percentile(data: List[float], percentile: float) -> float:
        """Calculate percentile value."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        lower = int(index)
        upper = lower + 1
        if upper >= len(sorted_data):
            return sorted_data[-1]
        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight


def timed(
    name: Optional[str] = None,
    log_result: bool = True,
    threshold_ms: Optional[float] = None,
) -> Callable[[F], F]:
    """
    Decorator to time function execution.

    مزخرف لقياس وقت تنفيذ الدالة.

    Args:
        name: Custom name for the measurement
        log_result: Whether to log the result
        threshold_ms: Log warning if execution exceeds threshold

    Usage:
        @timed()
        def my_function():
            pass

        @timed(name="custom_name", threshold_ms=100)
        async def my_async_function():
            pass
    """

    def decorator(func: F) -> F:
        func_name = name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    if log_result:
                        logger.debug(f"{func_name} took {elapsed_ms:.2f}ms")
                    if threshold_ms and elapsed_ms > threshold_ms:
                        logger.warning(
                            f"{func_name} exceeded threshold: "
                            f"{elapsed_ms:.2f}ms > {threshold_ms}ms"
                        )

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return func(*args, **kwargs)
                finally:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    if log_result:
                        logger.debug(f"{func_name} took {elapsed_ms:.2f}ms")
                    if threshold_ms and elapsed_ms > threshold_ms:
                        logger.warning(
                            f"{func_name} exceeded threshold: "
                            f"{elapsed_ms:.2f}ms > {threshold_ms}ms"
                        )

            return sync_wrapper  # type: ignore[return-value]

    return decorator


def profile_memory(
    name: Optional[str] = None,
    log_result: bool = True,
    threshold_mb: Optional[float] = None,
) -> Callable[[F], F]:
    """
    Decorator to profile memory usage of a function.

    مزخرف لتحليل استخدام الذاكرة.

    Args:
        name: Custom name for the measurement
        log_result: Whether to log the result
        threshold_mb: Log warning if peak memory exceeds threshold

    Usage:
        @profile_memory()
        def memory_intensive_function():
            pass
    """

    def decorator(func: F) -> F:
        func_name = name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                gc.collect()
                tracemalloc.start()
                try:
                    return await func(*args, **kwargs)
                finally:
                    current, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    peak_mb = peak / (1024 * 1024)
                    if log_result:
                        logger.debug(f"{func_name} peak memory: {peak_mb:.2f}MB")
                    if threshold_mb and peak_mb > threshold_mb:
                        logger.warning(
                            f"{func_name} exceeded memory threshold: "
                            f"{peak_mb:.2f}MB > {threshold_mb}MB"
                        )

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                gc.collect()
                tracemalloc.start()
                try:
                    return func(*args, **kwargs)
                finally:
                    current, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    peak_mb = peak / (1024 * 1024)
                    if log_result:
                        logger.debug(f"{func_name} peak memory: {peak_mb:.2f}MB")
                    if threshold_mb and peak_mb > threshold_mb:
                        logger.warning(
                            f"{func_name} exceeded memory threshold: "
                            f"{peak_mb:.2f}MB > {threshold_mb}MB"
                        )

            return sync_wrapper  # type: ignore[return-value]

    return decorator


class PerformanceMonitor:
    """
    Continuous performance monitoring.

    مراقبة الأداء المستمرة.

    Usage:
        monitor = PerformanceMonitor()
        monitor.start()

        # ... application runs ...

        stats = monitor.get_stats()
        monitor.stop()
    """

    def __init__(self, sample_interval: float = 1.0):
        """
        Initialize performance monitor.

        Args:
            sample_interval: Sampling interval in seconds
        """
        self.sample_interval = sample_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._samples: List[Dict[str, Any]] = []

    async def start(self) -> None:
        """Start monitoring."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Performance monitoring started")

    async def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Performance monitoring stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        import resource

        while self._running:
            try:
                # Collect sample
                rusage = resource.getrusage(resource.RUSAGE_SELF)

                sample = {
                    "timestamp": time.time(),
                    "user_time": rusage.ru_utime,
                    "system_time": rusage.ru_stime,
                    "max_rss_kb": rusage.ru_maxrss,
                    "page_faults": rusage.ru_majflt,
                    "voluntary_ctx_switches": rusage.ru_nvcsw,
                    "involuntary_ctx_switches": rusage.ru_nivcsw,
                }

                # Add process-specific metrics
                try:
                    import psutil

                    process = psutil.Process()
                    sample["cpu_percent"] = process.cpu_percent()
                    sample["memory_percent"] = process.memory_percent()
                    sample["num_threads"] = process.num_threads()
                    sample["num_fds"] = process.num_fds()
                except ImportError:
                    pass

                self._samples.append(sample)

                # Keep only last hour of samples
                cutoff = time.time() - 3600
                self._samples = [s for s in self._samples if s["timestamp"] > cutoff]

            except Exception as e:
                logger.error(f"Error in performance monitor: {e}")

            await asyncio.sleep(self.sample_interval)

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics."""
        if not self._samples:
            return {}

        # Calculate averages
        def avg(key: str) -> float:
            values = [s.get(key, 0) for s in self._samples if key in s]
            return sum(values) / len(values) if values else 0

        return {
            "sample_count": len(self._samples),
            "duration_seconds": (
                self._samples[-1]["timestamp"] - self._samples[0]["timestamp"]
                if len(self._samples) > 1
                else 0
            ),
            "avg_cpu_percent": avg("cpu_percent"),
            "avg_memory_percent": avg("memory_percent"),
            "max_rss_mb": max(
                s.get("max_rss_kb", 0) for s in self._samples
            ) / 1024,
            "avg_threads": avg("num_threads"),
            "total_ctx_switches": sum(
                s.get("voluntary_ctx_switches", 0)
                + s.get("involuntary_ctx_switches", 0)
                for s in self._samples
            ),
        }

    def get_samples(self) -> List[Dict[str, Any]]:
        """Get all samples."""
        return self._samples.copy()


# Convenience functions


def quick_benchmark(
    func: Callable,
    args: tuple = (),
    kwargs: Optional[Dict] = None,
    iterations: int = 100,
) -> TimingResult:
    """
    Quick benchmark of a function.

    قياس سريع لأداء دالة.

    Usage:
        result = quick_benchmark(my_function, args=(1, 2), iterations=1000)
        print(f"Mean time: {result.mean_time}ms")
    """
    benchmarker = Benchmarker("quick_benchmark", warmup_iterations=5)
    return benchmarker.time_function(func, args, kwargs, iterations)


async def quick_async_benchmark(
    func: Callable,
    args: tuple = (),
    kwargs: Optional[Dict] = None,
    iterations: int = 100,
) -> TimingResult:
    """
    Quick benchmark of an async function.

    قياس سريع لأداء دالة غير متزامنة.
    """
    benchmarker = Benchmarker("quick_async_benchmark", warmup_iterations=5)
    return await benchmarker.time_async_function(func, args, kwargs, iterations)


def compare_functions(
    functions: List[Callable],
    args: tuple = (),
    kwargs: Optional[Dict] = None,
    iterations: int = 100,
) -> Dict[str, TimingResult]:
    """
    Compare performance of multiple functions.

    مقارنة أداء عدة دوال.

    Usage:
        results = compare_functions([func1, func2, func3], iterations=1000)
        for name, result in results.items():
            print(f"{name}: {result.mean_time}ms")
    """
    benchmarker = Benchmarker("comparison")
    results = {}

    for func in functions:
        name = getattr(func, "__name__", str(func))
        result = benchmarker.time_function(func, args, kwargs, iterations, name)
        results[name] = result

    # Sort by mean time
    return dict(sorted(results.items(), key=lambda x: x[1].mean_time))
