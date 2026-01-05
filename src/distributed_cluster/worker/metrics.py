"""
Worker Metrics - مقاييس العامل
================================

مراقبة أداء العامل وجمع المقاييس:
- Memory tracking for processes
- CPU usage monitoring
- Job execution metrics
- Resource utilization
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


@dataclass
class ProcessMetrics:
    """مقاييس process."""

    pid: int
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    peak_memory_mb: float = 0.0
    threads: int = 0
    open_files: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class JobMetrics:
    """مقاييس job."""

    job_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    execution_time_seconds: float = 0.0
    peak_memory_mb: float = 0.0
    average_cpu_percent: float = 0.0
    samples_collected: int = 0
    exit_code: Optional[int] = None


@dataclass
class WorkerMetrics:
    """مقاييس العامل الإجمالية."""

    worker_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # System resources
    cpu_percent: float = 0.0
    cpu_count: int = 0
    memory_total_mb: float = 0.0
    memory_used_mb: float = 0.0
    memory_percent: float = 0.0
    disk_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_percent: float = 0.0

    # Job statistics
    jobs_completed: int = 0
    jobs_failed: int = 0
    jobs_active: int = 0
    total_execution_time_seconds: float = 0.0

    # Network (if available)
    network_bytes_sent: int = 0
    network_bytes_recv: int = 0


class ProcessMemoryTracker:
    """
    تتبع استخدام الذاكرة لـ process.

    الاستخدام:
        tracker = ProcessMemoryTracker(pid=12345)
        await tracker.start()
        # ... wait for process ...
        await tracker.stop()
        print(f"Peak memory: {tracker.peak_memory_mb} MB")
    """

    def __init__(
        self,
        pid: int,
        sample_interval: float = 0.5,  # Sample every 500ms
        include_children: bool = True,
    ):
        self.pid = pid
        self.sample_interval = sample_interval
        self.include_children = include_children

        # Tracking state
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._samples: List[ProcessMetrics] = []
        self._peak_memory_mb: float = 0.0
        self._total_cpu_samples: float = 0.0

    async def start(self) -> None:
        """بدء التتبع."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.debug(f"Started memory tracking for PID {self.pid}")

    async def stop(self) -> None:
        """إيقاف التتبع."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.debug(f"Stopped memory tracking for PID {self.pid}")

    async def _monitor_loop(self) -> None:
        """حلقة المراقبة."""
        while self._running:
            try:
                metrics = await self._collect_sample()
                if metrics:
                    self._samples.append(metrics)

                    # Update peak
                    if metrics.memory_mb > self._peak_memory_mb:
                        self._peak_memory_mb = metrics.memory_mb

                    self._total_cpu_samples += metrics.cpu_percent

                await asyncio.sleep(self.sample_interval)

            except psutil.NoSuchProcess:
                # Process ended
                logger.debug(f"Process {self.pid} no longer exists")
                break
            except Exception as e:
                logger.warning(f"Memory tracking error: {e}")
                await asyncio.sleep(self.sample_interval)

    async def _collect_sample(self) -> Optional[ProcessMetrics]:
        """جمع عينة واحدة."""
        try:
            proc = psutil.Process(self.pid)

            # Memory info
            mem_info = proc.memory_info()
            memory_mb = mem_info.rss / (1024 * 1024)
            memory_percent = proc.memory_percent()

            # Include children if requested
            if self.include_children:
                try:
                    for child in proc.children(recursive=True):
                        try:
                            child_mem = child.memory_info()
                            memory_mb += child_mem.rss / (1024 * 1024)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # CPU percent
            cpu_percent = proc.cpu_percent()

            # Thread count
            threads = proc.num_threads()

            # Open files (optional)
            try:
                open_files = len(proc.open_files())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                open_files = 0

            return ProcessMetrics(
                pid=self.pid,
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                memory_percent=memory_percent,
                peak_memory_mb=max(memory_mb, self._peak_memory_mb),
                threads=threads,
                open_files=open_files,
            )

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    @property
    def peak_memory_mb(self) -> float:
        """ذروة استخدام الذاكرة."""
        return self._peak_memory_mb

    @property
    def average_cpu_percent(self) -> float:
        """متوسط استخدام CPU."""
        if not self._samples:
            return 0.0
        return self._total_cpu_samples / len(self._samples)

    @property
    def samples(self) -> List[ProcessMetrics]:
        """جميع العينات المُجمَّعة."""
        return self._samples.copy()


class WorkerMetricsCollector:
    """
    جامع مقاييس العامل.

    الاستخدام:
        collector = WorkerMetricsCollector(worker_id="worker-1")
        await collector.start()

        # Record job completion
        collector.record_job_completed("job-123", 60.5, 0)

        # Get metrics
        metrics = collector.get_current_metrics()
    """

    def __init__(
        self,
        worker_id: str,
        collect_interval: float = 10.0,  # Collect every 10 seconds
        history_size: int = 1000,
    ):
        self.worker_id = worker_id
        self.collect_interval = collect_interval
        self.history_size = history_size

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._history: List[WorkerMetrics] = []

        # Counters
        self._jobs_completed = 0
        self._jobs_failed = 0
        self._jobs_active = 0
        self._total_execution_time = 0.0

        # Job trackers
        self._job_metrics: Dict[str, JobMetrics] = {}
        self._process_trackers: Dict[str, ProcessMemoryTracker] = {}

        # Callbacks
        self._on_metrics: Optional[Callable[[WorkerMetrics], None]] = None

    async def start(self) -> None:
        """بدء الجمع."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._collect_loop())
        logger.info(f"Started metrics collection for worker {self.worker_id}")

    async def stop(self) -> None:
        """إيقاف الجمع."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Stop all process trackers
        for tracker in self._process_trackers.values():
            await tracker.stop()

        logger.info(f"Stopped metrics collection for worker {self.worker_id}")

    async def _collect_loop(self) -> None:
        """حلقة الجمع."""
        while self._running:
            try:
                metrics = await self._collect_metrics()
                self._history.append(metrics)

                # Trim history
                if len(self._history) > self.history_size:
                    self._history = self._history[-self.history_size:]

                # Callback
                if self._on_metrics:
                    try:
                        self._on_metrics(metrics)
                    except Exception as e:
                        logger.warning(f"Metrics callback error: {e}")

                await asyncio.sleep(self.collect_interval)

            except Exception as e:
                logger.error(f"Metrics collection error: {e}")
                await asyncio.sleep(self.collect_interval)

    async def _collect_metrics(self) -> WorkerMetrics:
        """جمع المقاييس الحالية."""
        # CPU
        cpu_percent = psutil.cpu_percent()
        cpu_count = psutil.cpu_count()

        # Memory
        mem = psutil.virtual_memory()
        memory_total_mb = mem.total / (1024 * 1024)
        memory_used_mb = mem.used / (1024 * 1024)
        memory_percent = mem.percent

        # Disk
        disk = psutil.disk_usage("/")
        disk_total_gb = disk.total / (1024 * 1024 * 1024)
        disk_used_gb = disk.used / (1024 * 1024 * 1024)
        disk_percent = disk.percent

        # Network
        net = psutil.net_io_counters()
        network_bytes_sent = net.bytes_sent
        network_bytes_recv = net.bytes_recv

        return WorkerMetrics(
            worker_id=self.worker_id,
            cpu_percent=cpu_percent,
            cpu_count=cpu_count or 1,
            memory_total_mb=memory_total_mb,
            memory_used_mb=memory_used_mb,
            memory_percent=memory_percent,
            disk_total_gb=disk_total_gb,
            disk_used_gb=disk_used_gb,
            disk_percent=disk_percent,
            jobs_completed=self._jobs_completed,
            jobs_failed=self._jobs_failed,
            jobs_active=self._jobs_active,
            total_execution_time_seconds=self._total_execution_time,
            network_bytes_sent=network_bytes_sent,
            network_bytes_recv=network_bytes_recv,
        )

    def start_job_tracking(self, job_id: str, pid: Optional[int] = None) -> None:
        """بدء تتبع job."""
        self._job_metrics[job_id] = JobMetrics(
            job_id=job_id,
            start_time=datetime.now(timezone.utc),
        )
        self._jobs_active += 1

        if pid:
            tracker = ProcessMemoryTracker(pid)
            self._process_trackers[job_id] = tracker
            asyncio.create_task(tracker.start())

        logger.debug(f"Started tracking job {job_id}")

    async def stop_job_tracking(
        self,
        job_id: str,
        exit_code: Optional[int] = None,
    ) -> Optional[JobMetrics]:
        """إيقاف تتبع job."""
        job_metrics = self._job_metrics.pop(job_id, None)

        if job_metrics:
            job_metrics.end_time = datetime.now(timezone.utc)
            job_metrics.execution_time_seconds = (
                job_metrics.end_time - job_metrics.start_time
            ).total_seconds()
            job_metrics.exit_code = exit_code

            # Get memory tracker results
            if job_id in self._process_trackers:
                tracker = self._process_trackers.pop(job_id)
                await tracker.stop()
                job_metrics.peak_memory_mb = tracker.peak_memory_mb
                job_metrics.average_cpu_percent = tracker.average_cpu_percent
                job_metrics.samples_collected = len(tracker.samples)

            # Update counters
            self._jobs_active = max(0, self._jobs_active - 1)
            if exit_code == 0:
                self._jobs_completed += 1
            else:
                self._jobs_failed += 1
            self._total_execution_time += job_metrics.execution_time_seconds

        logger.debug(f"Stopped tracking job {job_id}")
        return job_metrics

    def record_job_completed(
        self,
        job_id: str,
        execution_time: float,
        exit_code: int,
    ) -> None:
        """تسجيل اكتمال job (للاستخدام بدون تتبع)."""
        if exit_code == 0:
            self._jobs_completed += 1
        else:
            self._jobs_failed += 1
        self._total_execution_time += execution_time

    def get_current_metrics(self) -> Optional[WorkerMetrics]:
        """الحصول على المقاييس الحالية."""
        if self._history:
            return self._history[-1]
        return None

    def get_metrics_history(
        self,
        minutes: int = 60,
    ) -> List[WorkerMetrics]:
        """الحصول على سجل المقاييس."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return [m for m in self._history if m.timestamp >= cutoff]

    def get_job_metrics(self, job_id: str) -> Optional[JobMetrics]:
        """الحصول على مقاييس job محددة."""
        return self._job_metrics.get(job_id)

    def set_on_metrics_callback(
        self,
        callback: Callable[[WorkerMetrics], None],
    ) -> None:
        """تعيين callback للمقاييس."""
        self._on_metrics = callback

    def to_prometheus_format(self) -> str:
        """تصدير المقاييس بصيغة Prometheus."""
        metrics = self.get_current_metrics()
        if not metrics:
            return ""

        lines = [
            '# HELP worker_cpu_percent CPU usage percentage',
            '# TYPE worker_cpu_percent gauge',
            f'worker_cpu_percent{{worker="{self.worker_id}"}} {metrics.cpu_percent}',
            '',
            '# HELP worker_memory_used_mb Memory used in MB',
            '# TYPE worker_memory_used_mb gauge',
            f'worker_memory_used_mb{{worker="{self.worker_id}"}} {metrics.memory_used_mb:.2f}',
            '',
            '# HELP worker_memory_percent Memory usage percentage',
            '# TYPE worker_memory_percent gauge',
            f'worker_memory_percent{{worker="{self.worker_id}"}} {metrics.memory_percent}',
            '',
            '# HELP worker_disk_percent Disk usage percentage',
            '# TYPE worker_disk_percent gauge',
            f'worker_disk_percent{{worker="{self.worker_id}"}} {metrics.disk_percent}',
            '',
            '# HELP worker_jobs_completed_total Total completed jobs',
            '# TYPE worker_jobs_completed_total counter',
            f'worker_jobs_completed_total{{worker="{self.worker_id}"}} {metrics.jobs_completed}',
            '',
            '# HELP worker_jobs_failed_total Total failed jobs',
            '# TYPE worker_jobs_failed_total counter',
            f'worker_jobs_failed_total{{worker="{self.worker_id}"}} {metrics.jobs_failed}',
            '',
            '# HELP worker_jobs_active Current active jobs',
            '# TYPE worker_jobs_active gauge',
            f'worker_jobs_active{{worker="{self.worker_id}"}} {metrics.jobs_active}',
        ]

        return "\n".join(lines)


# ==================== Retry Logic with Backoff ====================


@dataclass
class RetryConfig:
    """إعدادات إعادة المحاولة."""

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: float = 0.1  # Random jitter percentage


class RetryHandler:
    """
    معالج إعادة المحاولة مع exponential backoff.

    الاستخدام:
        retry = RetryHandler(RetryConfig(max_retries=3))

        async for attempt in retry:
            try:
                result = await some_operation()
                break
            except Exception as e:
                if not retry.should_retry(e):
                    raise
    """

    def __init__(self, config: RetryConfig):
        self.config = config
        self._attempt = 0
        self._last_delay = 0.0

    def __aiter__(self):
        self._attempt = 0
        return self

    async def __anext__(self) -> int:
        if self._attempt >= self.config.max_retries:
            raise StopAsyncIteration

        if self._attempt > 0:
            delay = self._calculate_delay()
            self._last_delay = delay
            logger.debug(f"Retry attempt {self._attempt}, waiting {delay:.2f}s")
            await asyncio.sleep(delay)

        self._attempt += 1
        return self._attempt

    def _calculate_delay(self) -> float:
        """حساب تأخير إعادة المحاولة."""
        import random

        delay = min(
            self.config.initial_delay * (self.config.exponential_base ** (self._attempt - 1)),
            self.config.max_delay,
        )

        # Add jitter
        jitter = delay * self.config.jitter
        delay += random.uniform(-jitter, jitter)

        return max(0, delay)

    def should_retry(self, exception: Exception) -> bool:
        """تحديد إذا يجب إعادة المحاولة."""
        # Default: retry on connection errors
        retryable = (
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
        )

        return (
            isinstance(exception, retryable)
            and self._attempt < self.config.max_retries
        )

    @property
    def attempts(self) -> int:
        return self._attempt

    @property
    def last_delay(self) -> float:
        return self._last_delay
