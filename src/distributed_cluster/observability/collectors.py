"""
System Collectors - جامعي مقاييس النظام
=======================================

جمع مقاييس النظام تلقائياً:
- CPU usage
- Memory usage
- Disk usage
- Network I/O
- GPU metrics
- Process metrics
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


@dataclass
class CPUMetrics:
    """مقاييس CPU."""

    percent: float = 0.0
    percent_per_core: List[float] = field(default_factory=list)
    count: int = 0
    count_logical: int = 0
    freq_current: float = 0.0
    freq_min: float = 0.0
    freq_max: float = 0.0
    load_avg_1m: float = 0.0
    load_avg_5m: float = 0.0
    load_avg_15m: float = 0.0
    ctx_switches: int = 0
    interrupts: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MemoryMetrics:
    """مقاييس الذاكرة."""

    total_bytes: int = 0
    available_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    percent: float = 0.0
    swap_total_bytes: int = 0
    swap_used_bytes: int = 0
    swap_free_bytes: int = 0
    swap_percent: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DiskMetrics:
    """مقاييس التخزين."""

    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    percent: float = 0.0
    read_bytes: int = 0
    write_bytes: int = 0
    read_count: int = 0
    write_count: int = 0
    read_time_ms: int = 0
    write_time_ms: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NetworkMetrics:
    """مقاييس الشبكة."""

    bytes_sent: int = 0
    bytes_recv: int = 0
    packets_sent: int = 0
    packets_recv: int = 0
    errors_in: int = 0
    errors_out: int = 0
    drops_in: int = 0
    drops_out: int = 0
    connections: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GPUMetrics:
    """مقاييس GPU."""

    index: int
    name: str = ""
    memory_total_mb: int = 0
    memory_used_mb: int = 0
    memory_free_mb: int = 0
    utilization_percent: float = 0.0
    temperature_c: float = 0.0
    power_usage_w: float = 0.0
    power_limit_w: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProcessMetrics:
    """مقاييس process."""

    pid: int
    name: str = ""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_rss_bytes: int = 0
    memory_vms_bytes: int = 0
    threads: int = 0
    open_files: int = 0
    connections: int = 0
    status: str = ""
    create_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


class SystemCollector:
    """
    جامع مقاييس النظام.

    الاستخدام:
        collector = SystemCollector()
        cpu = await collector.collect_cpu()
        memory = await collector.collect_memory()
        all_metrics = await collector.collect_all()
    """

    def __init__(
        self,
        disk_paths: Optional[List[str]] = None,
        collect_gpu: bool = True,
    ):
        self.disk_paths = disk_paths or ["/"]
        self.collect_gpu = collect_gpu

        # Previous values for rate calculations
        self._prev_disk_io = None
        self._prev_net_io = None
        self._prev_collect_time = None

    async def collect_cpu(self) -> CPUMetrics:
        """جمع مقاييس CPU."""
        loop = asyncio.get_running_loop()

        # Run CPU-intensive operations in executor
        cpu_percent = await loop.run_in_executor(
            None, psutil.cpu_percent, 0.1
        )
        cpu_percent_per_core = await loop.run_in_executor(
            None, psutil.cpu_percent, 0.1, True
        )

        cpu_count = psutil.cpu_count(logical=False) or 1
        cpu_count_logical = psutil.cpu_count(logical=True) or 1

        # Frequency
        try:
            freq = psutil.cpu_freq()
            freq_current = freq.current if freq else 0
            freq_min = freq.min if freq else 0
            freq_max = freq.max if freq else 0
        except Exception:
            freq_current = freq_min = freq_max = 0

        # Load average (Unix only)
        try:
            load_avg = os.getloadavg()
        except (AttributeError, OSError):
            load_avg = (0, 0, 0)

        # Context switches and interrupts
        try:
            stats = psutil.cpu_stats()
            ctx_switches = stats.ctx_switches
            interrupts = stats.interrupts
        except Exception:
            ctx_switches = interrupts = 0

        return CPUMetrics(
            percent=cpu_percent,
            percent_per_core=cpu_percent_per_core,
            count=cpu_count,
            count_logical=cpu_count_logical,
            freq_current=freq_current,
            freq_min=freq_min,
            freq_max=freq_max,
            load_avg_1m=load_avg[0],
            load_avg_5m=load_avg[1],
            load_avg_15m=load_avg[2],
            ctx_switches=ctx_switches,
            interrupts=interrupts,
        )

    async def collect_memory(self) -> MemoryMetrics:
        """جمع مقاييس الذاكرة."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return MemoryMetrics(
            total_bytes=mem.total,
            available_bytes=mem.available,
            used_bytes=mem.used,
            free_bytes=mem.free,
            percent=mem.percent,
            swap_total_bytes=swap.total,
            swap_used_bytes=swap.used,
            swap_free_bytes=swap.free,
            swap_percent=swap.percent,
        )

    async def collect_disk(self, path: str = "/") -> DiskMetrics:
        """جمع مقاييس التخزين."""
        try:
            usage = psutil.disk_usage(path)
        except Exception:
            usage = None

        # I/O counters
        try:
            io = psutil.disk_io_counters()
            read_bytes = io.read_bytes
            write_bytes = io.write_bytes
            read_count = io.read_count
            write_count = io.write_count
            read_time = io.read_time
            write_time = io.write_time
        except Exception:
            read_bytes = write_bytes = read_count = write_count = 0
            read_time = write_time = 0

        return DiskMetrics(
            total_bytes=usage.total if usage else 0,
            used_bytes=usage.used if usage else 0,
            free_bytes=usage.free if usage else 0,
            percent=usage.percent if usage else 0,
            read_bytes=read_bytes,
            write_bytes=write_bytes,
            read_count=read_count,
            write_count=write_count,
            read_time_ms=read_time,
            write_time_ms=write_time,
        )

    async def collect_network(self) -> NetworkMetrics:
        """جمع مقاييس الشبكة."""
        net = psutil.net_io_counters()

        # Active connections
        try:
            connections = len(psutil.net_connections())
        except Exception:
            connections = 0

        return NetworkMetrics(
            bytes_sent=net.bytes_sent,
            bytes_recv=net.bytes_recv,
            packets_sent=net.packets_sent,
            packets_recv=net.packets_recv,
            errors_in=net.errin,
            errors_out=net.errout,
            drops_in=net.dropin,
            drops_out=net.dropout,
            connections=connections,
        )

    async def collect_gpu(self) -> List[GPUMetrics]:
        """جمع مقاييس GPU (NVIDIA)."""
        if not self.collect_gpu:
            return []

        gpus = []

        try:
            # Try nvidia-smi via pynvml
            import pynvml

            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()

            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8")

                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)

                try:
                    temperature = pynvml.nvmlDeviceGetTemperature(
                        handle, pynvml.NVML_TEMPERATURE_GPU
                    )
                except Exception:
                    temperature = 0

                try:
                    power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000  # mW to W
                    power_limit = pynvml.nvmlDeviceGetEnforcedPowerLimit(handle) / 1000
                except Exception:
                    power = power_limit = 0

                gpus.append(GPUMetrics(
                    index=i,
                    name=name,
                    memory_total_mb=memory.total // (1024 * 1024),
                    memory_used_mb=memory.used // (1024 * 1024),
                    memory_free_mb=memory.free // (1024 * 1024),
                    utilization_percent=utilization.gpu,
                    temperature_c=temperature,
                    power_usage_w=power,
                    power_limit_w=power_limit,
                ))

            pynvml.nvmlShutdown()

        except ImportError:
            logger.debug("pynvml not available, GPU metrics disabled")
        except Exception as e:
            logger.debug(f"GPU metrics collection error: {e}")

        return gpus

    async def collect_process(self, pid: Optional[int] = None) -> ProcessMetrics:
        """جمع مقاييس process."""
        pid = pid or os.getpid()

        try:
            proc = psutil.Process(pid)

            # Memory info
            mem_info = proc.memory_info()

            # Open files and connections
            try:
                open_files = len(proc.open_files())
            except Exception:
                open_files = 0

            try:
                connections = len(proc.connections())
            except Exception:
                connections = 0

            return ProcessMetrics(
                pid=pid,
                name=proc.name(),
                cpu_percent=proc.cpu_percent(),
                memory_percent=proc.memory_percent(),
                memory_rss_bytes=mem_info.rss,
                memory_vms_bytes=mem_info.vms,
                threads=proc.num_threads(),
                open_files=open_files,
                connections=connections,
                status=proc.status(),
                create_time=proc.create_time(),
            )

        except psutil.NoSuchProcess:
            return ProcessMetrics(pid=pid)

    async def collect_all(self) -> Dict[str, Any]:
        """جمع جميع المقاييس."""
        cpu_task = self.collect_cpu()
        memory_task = self.collect_memory()
        disk_tasks = [self.collect_disk(path) for path in self.disk_paths]
        network_task = self.collect_network()
        process_task = self.collect_process()

        tasks = [cpu_task, memory_task, *disk_tasks, network_task, process_task]

        if self.collect_gpu:
            tasks.append(self.collect_gpu())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        cpu_metrics = results[0] if not isinstance(results[0], Exception) else None
        memory_metrics = results[1] if not isinstance(results[1], Exception) else None

        disk_results = results[2:2 + len(self.disk_paths)]
        disk_metrics = {
            path: result for path, result in zip(self.disk_paths, disk_results)
            if not isinstance(result, Exception)
        }

        network_idx = 2 + len(self.disk_paths)
        network_metrics = results[network_idx] if not isinstance(results[network_idx], Exception) else None

        process_idx = network_idx + 1
        process_metrics = results[process_idx] if not isinstance(results[process_idx], Exception) else None

        gpu_metrics = []
        if self.collect_gpu and len(results) > process_idx + 1:
            gpu_result = results[process_idx + 1]
            if not isinstance(gpu_result, Exception):
                gpu_metrics = gpu_result

        return {
            "cpu": cpu_metrics,
            "memory": memory_metrics,
            "disk": disk_metrics,
            "network": network_metrics,
            "process": process_metrics,
            "gpu": gpu_metrics,
            "timestamp": datetime.utcnow().isoformat(),
        }


class MetricsReporter:
    """
    مُرسِل مقاييس دوري.

    الاستخدام:
        reporter = MetricsReporter(collector, interval=10.0)
        reporter.add_callback(my_callback)
        await reporter.start()
    """

    def __init__(
        self,
        collector: SystemCollector,
        interval: float = 10.0,
    ):
        self.collector = collector
        self.interval = interval
        self._callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def add_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """إضافة callback لاستلام المقاييس."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """بدء الجمع الدوري."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._collect_loop())
        logger.info(f"Metrics reporter started with {self.interval}s interval")

    async def stop(self) -> None:
        """إيقاف الجمع."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Metrics reporter stopped")

    async def _collect_loop(self) -> None:
        """حلقة الجمع."""
        while self._running:
            try:
                metrics = await self.collector.collect_all()

                for callback in self._callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(metrics)
                        else:
                            callback(metrics)
                    except Exception as e:
                        logger.error(f"Metrics callback error: {e}")

            except Exception as e:
                logger.error(f"Metrics collection error: {e}")

            await asyncio.sleep(self.interval)

    async def collect_once(self) -> Dict[str, Any]:
        """جمع مرة واحدة."""
        return await self.collector.collect_all()


# ==================== Prometheus Integration ====================


class PrometheusSystemCollector:
    """
    جامع مقاييس النظام بصيغة Prometheus.

    الاستخدام:
        collector = PrometheusSystemCollector()
        await collector.start()
        metrics_text = await collector.format_metrics()
    """

    def __init__(
        self,
        prefix: str = "node",
        interval: float = 10.0,
    ):
        self.prefix = prefix
        self.interval = interval
        self._system_collector = SystemCollector()
        self._last_metrics: Optional[Dict[str, Any]] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """بدء الجمع الدوري."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._collect_loop())

    async def stop(self) -> None:
        """إيقاف الجمع."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _collect_loop(self) -> None:
        """حلقة الجمع."""
        while self._running:
            self._last_metrics = await self._system_collector.collect_all()
            await asyncio.sleep(self.interval)

    async def format_metrics(self) -> str:
        """تنسيق المقاييس بصيغة Prometheus."""
        if not self._last_metrics:
            self._last_metrics = await self._system_collector.collect_all()

        lines = []
        p = self.prefix

        # CPU metrics
        cpu = self._last_metrics.get("cpu")
        if cpu:
            lines.extend([
                f"# HELP {p}_cpu_percent CPU usage percentage",
                f"# TYPE {p}_cpu_percent gauge",
                f"{p}_cpu_percent {cpu.percent}",
                "",
                f"# HELP {p}_cpu_count Number of CPU cores",
                f"# TYPE {p}_cpu_count gauge",
                f"{p}_cpu_count{{type=\"physical\"}} {cpu.count}",
                f"{p}_cpu_count{{type=\"logical\"}} {cpu.count_logical}",
                "",
            ])

            if cpu.load_avg_1m:
                lines.extend([
                    f"# HELP {p}_load Load average",
                    f"# TYPE {p}_load gauge",
                    f"{p}_load{{interval=\"1m\"}} {cpu.load_avg_1m}",
                    f"{p}_load{{interval=\"5m\"}} {cpu.load_avg_5m}",
                    f"{p}_load{{interval=\"15m\"}} {cpu.load_avg_15m}",
                    "",
                ])

        # Memory metrics
        memory = self._last_metrics.get("memory")
        if memory:
            lines.extend([
                f"# HELP {p}_memory_bytes Memory in bytes",
                f"# TYPE {p}_memory_bytes gauge",
                f"{p}_memory_bytes{{type=\"total\"}} {memory.total_bytes}",
                f"{p}_memory_bytes{{type=\"available\"}} {memory.available_bytes}",
                f"{p}_memory_bytes{{type=\"used\"}} {memory.used_bytes}",
                "",
                f"# HELP {p}_memory_percent Memory usage percentage",
                f"# TYPE {p}_memory_percent gauge",
                f"{p}_memory_percent {memory.percent}",
                "",
            ])

            if memory.swap_total_bytes:
                lines.extend([
                    f"# HELP {p}_swap_bytes Swap in bytes",
                    f"# TYPE {p}_swap_bytes gauge",
                    f"{p}_swap_bytes{{type=\"total\"}} {memory.swap_total_bytes}",
                    f"{p}_swap_bytes{{type=\"used\"}} {memory.swap_used_bytes}",
                    f"{p}_swap_bytes{{type=\"free\"}} {memory.swap_free_bytes}",
                    "",
                ])

        # Disk metrics
        disk = self._last_metrics.get("disk", {})
        for path, disk_metrics in disk.items():
            if disk_metrics:
                path.replace("/", "_").strip("_") or "root"
                lines.extend([
                    f"# HELP {p}_disk_bytes Disk space in bytes",
                    f"# TYPE {p}_disk_bytes gauge",
                    f"{p}_disk_bytes{{path=\"{path}\",type=\"total\"}} {disk_metrics.total_bytes}",
                    f"{p}_disk_bytes{{path=\"{path}\",type=\"used\"}} {disk_metrics.used_bytes}",
                    f"{p}_disk_bytes{{path=\"{path}\",type=\"free\"}} {disk_metrics.free_bytes}",
                    "",
                    f"# HELP {p}_disk_percent Disk usage percentage",
                    f"# TYPE {p}_disk_percent gauge",
                    f"{p}_disk_percent{{path=\"{path}\"}} {disk_metrics.percent}",
                    "",
                ])

        # Network metrics
        network = self._last_metrics.get("network")
        if network:
            lines.extend([
                f"# HELP {p}_network_bytes Network bytes total",
                f"# TYPE {p}_network_bytes counter",
                f"{p}_network_bytes{{direction=\"sent\"}} {network.bytes_sent}",
                f"{p}_network_bytes{{direction=\"recv\"}} {network.bytes_recv}",
                "",
                f"# HELP {p}_network_packets Network packets total",
                f"# TYPE {p}_network_packets counter",
                f"{p}_network_packets{{direction=\"sent\"}} {network.packets_sent}",
                f"{p}_network_packets{{direction=\"recv\"}} {network.packets_recv}",
                "",
                f"# HELP {p}_network_errors Network errors total",
                f"# TYPE {p}_network_errors counter",
                f"{p}_network_errors{{direction=\"in\"}} {network.errors_in}",
                f"{p}_network_errors{{direction=\"out\"}} {network.errors_out}",
                "",
            ])

        # GPU metrics
        gpus = self._last_metrics.get("gpu", [])
        for gpu in gpus:
            lines.extend([
                f"# HELP {p}_gpu_memory_bytes GPU memory in bytes",
                f"# TYPE {p}_gpu_memory_bytes gauge",
                f"{p}_gpu_memory_bytes{{gpu=\"{gpu.index}\",name=\"{gpu.name}\",type=\"total\"}} {gpu.memory_total_mb * 1024 * 1024}",
                f"{p}_gpu_memory_bytes{{gpu=\"{gpu.index}\",name=\"{gpu.name}\",type=\"used\"}} {gpu.memory_used_mb * 1024 * 1024}",
                "",
                f"# HELP {p}_gpu_utilization GPU utilization percentage",
                f"# TYPE {p}_gpu_utilization gauge",
                f"{p}_gpu_utilization{{gpu=\"{gpu.index}\",name=\"{gpu.name}\"}} {gpu.utilization_percent}",
                "",
                f"# HELP {p}_gpu_temperature GPU temperature in Celsius",
                f"# TYPE {p}_gpu_temperature gauge",
                f"{p}_gpu_temperature{{gpu=\"{gpu.index}\",name=\"{gpu.name}\"}} {gpu.temperature_c}",
                "",
            ])

        return "\n".join(lines)
