# -*- coding: utf-8 -*-
"""
System Metrics Collectors for Prometheus
=========================================

جامعات مقاييس النظام لـ Prometheus:
- مقاييس CPU
- مقاييس الذاكرة
- مقاييس الشبكة
- مقاييس القرص
- مقاييس GPU
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False

from .prometheus import PrometheusRegistry, Gauge, Counter, Histogram

logger = logging.getLogger(__name__)


# =============================================================================
# System Information
# =============================================================================


@dataclass
class SystemInfo:
    """System information data class."""

    hostname: str
    platform: str
    platform_version: str
    architecture: str
    cpu_count: int
    cpu_count_logical: int
    memory_total: int  # bytes
    boot_time: float
    python_version: str

    @classmethod
    def collect(cls) -> "SystemInfo":
        """Collect system information."""
        return cls(
            hostname=platform.node(),
            platform=platform.system(),
            platform_version=platform.release(),
            architecture=platform.machine(),
            cpu_count=psutil.cpu_count(logical=False) if PSUTIL_AVAILABLE else os.cpu_count() or 1,
            cpu_count_logical=psutil.cpu_count(logical=True) if PSUTIL_AVAILABLE else os.cpu_count() or 1,
            memory_total=psutil.virtual_memory().total if PSUTIL_AVAILABLE else 0,
            boot_time=psutil.boot_time() if PSUTIL_AVAILABLE else time.time(),
            python_version=platform.python_version(),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hostname": self.hostname,
            "platform": self.platform,
            "platform_version": self.platform_version,
            "architecture": self.architecture,
            "cpu_count": self.cpu_count,
            "cpu_count_logical": self.cpu_count_logical,
            "memory_total": self.memory_total,
            "boot_time": self.boot_time,
            "python_version": self.python_version,
        }


# =============================================================================
# CPU Collector
# =============================================================================


class CPUCollector:
    """
    Collector for CPU metrics.

    جامع مقاييس وحدة المعالجة المركزية.
    """

    def __init__(self, registry: PrometheusRegistry):
        self.registry = registry

        # CPU usage gauges
        self.cpu_usage_percent = registry.gauge(
            "cpu_usage_percent",
            "CPU usage percentage (0-100)",
            ["cpu", "mode"],
        )

        self.cpu_usage_total = registry.gauge(
            "cpu_usage_total_percent",
            "Total CPU usage percentage",
        )

        # CPU times
        self.cpu_time_seconds = registry.counter(
            "cpu_time_seconds_total",
            "Time spent in different CPU modes",
            ["cpu", "mode"],
        )

        # CPU frequency
        self.cpu_frequency_hz = registry.gauge(
            "cpu_frequency_hz",
            "Current CPU frequency in Hz",
            ["cpu"],
        )

        # Load average
        self.load_average = registry.gauge(
            "load_average",
            "System load average",
            ["period"],  # 1min, 5min, 15min
        )

        # Context switches and interrupts
        self.context_switches_total = registry.counter(
            "context_switches_total",
            "Total context switches",
        )

        self.interrupts_total = registry.counter(
            "interrupts_total",
            "Total interrupts",
        )

        # Internal state for delta calculations
        self._last_ctx_switches = 0
        self._last_interrupts = 0

    def collect(self) -> None:
        """Collect CPU metrics."""
        if not PSUTIL_AVAILABLE:
            logger.debug("psutil not available, skipping CPU collection")
            return

        try:
            # Per-CPU usage
            cpu_percents = psutil.cpu_percent(percpu=True)
            for i, percent in enumerate(cpu_percents):
                self.cpu_usage_percent.set(percent, {"cpu": str(i), "mode": "total"})

            # Total CPU usage
            self.cpu_usage_total.set(psutil.cpu_percent())

            # CPU times per CPU
            cpu_times = psutil.cpu_times(percpu=True)
            for i, times in enumerate(cpu_times):
                cpu_label = str(i)
                self.cpu_usage_percent.set(times.user, {"cpu": cpu_label, "mode": "user"})
                self.cpu_usage_percent.set(times.system, {"cpu": cpu_label, "mode": "system"})
                self.cpu_usage_percent.set(times.idle, {"cpu": cpu_label, "mode": "idle"})
                if hasattr(times, "iowait"):
                    self.cpu_usage_percent.set(times.iowait, {"cpu": cpu_label, "mode": "iowait"})

            # CPU frequency
            try:
                freq = psutil.cpu_freq(percpu=True)
                if freq:
                    for i, f in enumerate(freq):
                        self.cpu_frequency_hz.set(f.current * 1e6, {"cpu": str(i)})
            except Exception:
                pass

            # Load average (Unix only)
            try:
                load = psutil.getloadavg()
                self.load_average.set(load[0], {"period": "1min"})
                self.load_average.set(load[1], {"period": "5min"})
                self.load_average.set(load[2], {"period": "15min"})
            except (AttributeError, OSError):
                pass

            # Context switches and interrupts
            stats = psutil.cpu_stats()

            if self._last_ctx_switches > 0:
                delta = stats.ctx_switches - self._last_ctx_switches
                if delta > 0:
                    self.context_switches_total.inc(value=delta)
            self._last_ctx_switches = stats.ctx_switches

            if self._last_interrupts > 0:
                delta = stats.interrupts - self._last_interrupts
                if delta > 0:
                    self.interrupts_total.inc(value=delta)
            self._last_interrupts = stats.interrupts

        except Exception as e:
            logger.error(f"Error collecting CPU metrics: {e}")


# =============================================================================
# Memory Collector
# =============================================================================


class MemoryCollector:
    """
    Collector for memory metrics.

    جامع مقاييس الذاكرة.
    """

    def __init__(self, registry: PrometheusRegistry):
        self.registry = registry

        # Virtual memory
        self.memory_bytes = registry.gauge(
            "memory_bytes",
            "Memory in bytes",
            ["type"],  # total, available, used, free, cached, buffers
        )

        self.memory_percent = registry.gauge(
            "memory_percent",
            "Memory usage percentage",
        )

        # Swap memory
        self.swap_bytes = registry.gauge(
            "swap_bytes",
            "Swap memory in bytes",
            ["type"],  # total, used, free
        )

        self.swap_percent = registry.gauge(
            "swap_percent",
            "Swap usage percentage",
        )

        # Page statistics
        self.page_faults_total = registry.counter(
            "page_faults_total",
            "Total page faults",
            ["type"],  # minor, major
        )

    def collect(self) -> None:
        """Collect memory metrics."""
        if not PSUTIL_AVAILABLE:
            return

        try:
            # Virtual memory
            vm = psutil.virtual_memory()
            self.memory_bytes.set(vm.total, {"type": "total"})
            self.memory_bytes.set(vm.available, {"type": "available"})
            self.memory_bytes.set(vm.used, {"type": "used"})
            self.memory_bytes.set(vm.free, {"type": "free"})

            if hasattr(vm, "cached"):
                self.memory_bytes.set(vm.cached, {"type": "cached"})
            if hasattr(vm, "buffers"):
                self.memory_bytes.set(vm.buffers, {"type": "buffers"})

            self.memory_percent.set(vm.percent)

            # Swap memory
            swap = psutil.swap_memory()
            self.swap_bytes.set(swap.total, {"type": "total"})
            self.swap_bytes.set(swap.used, {"type": "used"})
            self.swap_bytes.set(swap.free, {"type": "free"})
            self.swap_percent.set(swap.percent)

        except Exception as e:
            logger.error(f"Error collecting memory metrics: {e}")


# =============================================================================
# Disk Collector
# =============================================================================


class DiskCollector:
    """
    Collector for disk metrics.

    جامع مقاييس القرص.
    """

    def __init__(
        self,
        registry: PrometheusRegistry,
        monitored_paths: Optional[List[str]] = None,
    ):
        self.registry = registry
        self.monitored_paths = monitored_paths or ["/"]

        # Disk usage
        self.disk_bytes = registry.gauge(
            "disk_bytes",
            "Disk space in bytes",
            ["mountpoint", "type"],  # total, used, free
        )

        self.disk_percent = registry.gauge(
            "disk_percent",
            "Disk usage percentage",
            ["mountpoint"],
        )

        # Disk I/O
        self.disk_io_bytes = registry.counter(
            "disk_io_bytes_total",
            "Disk I/O bytes",
            ["device", "direction"],  # read, write
        )

        self.disk_io_operations = registry.counter(
            "disk_io_operations_total",
            "Disk I/O operations",
            ["device", "direction"],
        )

        self.disk_io_time_seconds = registry.counter(
            "disk_io_time_seconds_total",
            "Time spent on disk I/O",
            ["device"],
        )

        # Internal state
        self._last_io: Dict[str, Any] = {}

    def collect(self) -> None:
        """Collect disk metrics."""
        if not PSUTIL_AVAILABLE:
            return

        try:
            # Disk usage for monitored paths
            for path in self.monitored_paths:
                try:
                    usage = psutil.disk_usage(path)
                    self.disk_bytes.set(usage.total, {"mountpoint": path, "type": "total"})
                    self.disk_bytes.set(usage.used, {"mountpoint": path, "type": "used"})
                    self.disk_bytes.set(usage.free, {"mountpoint": path, "type": "free"})
                    self.disk_percent.set(usage.percent, {"mountpoint": path})
                except (PermissionError, FileNotFoundError):
                    pass

            # Disk I/O counters
            try:
                io_counters = psutil.disk_io_counters(perdisk=True)
                if io_counters:
                    for device, counters in io_counters.items():
                        last = self._last_io.get(device, {})

                        # Calculate deltas
                        if last:
                            read_delta = counters.read_bytes - last.get("read_bytes", 0)
                            write_delta = counters.write_bytes - last.get("write_bytes", 0)
                            read_ops_delta = counters.read_count - last.get("read_count", 0)
                            write_ops_delta = counters.write_count - last.get("write_count", 0)
                            time_delta = counters.read_time + counters.write_time - last.get("time", 0)

                            if read_delta > 0:
                                self.disk_io_bytes.inc({"device": device, "direction": "read"}, read_delta)
                            if write_delta > 0:
                                self.disk_io_bytes.inc({"device": device, "direction": "write"}, write_delta)
                            if read_ops_delta > 0:
                                self.disk_io_operations.inc({"device": device, "direction": "read"}, read_ops_delta)
                            if write_ops_delta > 0:
                                self.disk_io_operations.inc({"device": device, "direction": "write"}, write_ops_delta)
                            if time_delta > 0:
                                self.disk_io_time_seconds.inc({"device": device}, time_delta / 1000)

                        self._last_io[device] = {
                            "read_bytes": counters.read_bytes,
                            "write_bytes": counters.write_bytes,
                            "read_count": counters.read_count,
                            "write_count": counters.write_count,
                            "time": counters.read_time + counters.write_time,
                        }
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error collecting disk metrics: {e}")


# =============================================================================
# Network Collector
# =============================================================================


class NetworkCollector:
    """
    Collector for network metrics.

    جامع مقاييس الشبكة.
    """

    def __init__(self, registry: PrometheusRegistry):
        self.registry = registry

        # Network I/O
        self.network_bytes = registry.counter(
            "network_bytes_total",
            "Network bytes transferred",
            ["interface", "direction"],  # sent, recv
        )

        self.network_packets = registry.counter(
            "network_packets_total",
            "Network packets transferred",
            ["interface", "direction"],
        )

        self.network_errors = registry.counter(
            "network_errors_total",
            "Network errors",
            ["interface", "direction"],
        )

        self.network_drops = registry.counter(
            "network_drops_total",
            "Network dropped packets",
            ["interface", "direction"],
        )

        # Connection counts
        self.network_connections = registry.gauge(
            "network_connections",
            "Number of network connections",
            ["status"],  # ESTABLISHED, TIME_WAIT, etc.
        )

        # Internal state
        self._last_io: Dict[str, Any] = {}

    def collect(self) -> None:
        """Collect network metrics."""
        if not PSUTIL_AVAILABLE:
            return

        try:
            # Network I/O per interface
            io_counters = psutil.net_io_counters(pernic=True)
            for interface, counters in io_counters.items():
                last = self._last_io.get(interface, {})

                if last:
                    sent_delta = counters.bytes_sent - last.get("bytes_sent", 0)
                    recv_delta = counters.bytes_recv - last.get("bytes_recv", 0)

                    if sent_delta > 0:
                        self.network_bytes.inc({"interface": interface, "direction": "sent"}, sent_delta)
                    if recv_delta > 0:
                        self.network_bytes.inc({"interface": interface, "direction": "recv"}, recv_delta)

                    packets_sent_delta = counters.packets_sent - last.get("packets_sent", 0)
                    packets_recv_delta = counters.packets_recv - last.get("packets_recv", 0)

                    if packets_sent_delta > 0:
                        self.network_packets.inc({"interface": interface, "direction": "sent"}, packets_sent_delta)
                    if packets_recv_delta > 0:
                        self.network_packets.inc({"interface": interface, "direction": "recv"}, packets_recv_delta)

                self._last_io[interface] = {
                    "bytes_sent": counters.bytes_sent,
                    "bytes_recv": counters.bytes_recv,
                    "packets_sent": counters.packets_sent,
                    "packets_recv": counters.packets_recv,
                }

            # Connection counts
            try:
                connections = psutil.net_connections(kind="inet")
                status_counts: Dict[str, int] = {}
                for conn in connections:
                    status = conn.status if hasattr(conn, "status") else "UNKNOWN"
                    status_counts[status] = status_counts.get(status, 0) + 1

                for status, count in status_counts.items():
                    self.network_connections.set(count, {"status": status})
            except (psutil.AccessDenied, PermissionError):
                pass

        except Exception as e:
            logger.error(f"Error collecting network metrics: {e}")


# =============================================================================
# GPU Collector
# =============================================================================


class GPUCollector:
    """
    Collector for GPU metrics (NVIDIA).

    جامع مقاييس GPU.
    """

    def __init__(self, registry: PrometheusRegistry):
        self.registry = registry
        self._initialized = False

        # GPU info
        self.gpu_info = registry.gauge(
            "gpu_info",
            "GPU information",
            ["gpu", "name", "uuid"],
        )

        # GPU utilization
        self.gpu_utilization_percent = registry.gauge(
            "gpu_utilization_percent",
            "GPU utilization percentage",
            ["gpu"],
        )

        # GPU memory
        self.gpu_memory_bytes = registry.gauge(
            "gpu_memory_bytes",
            "GPU memory in bytes",
            ["gpu", "type"],  # total, used, free
        )

        self.gpu_memory_percent = registry.gauge(
            "gpu_memory_percent",
            "GPU memory usage percentage",
            ["gpu"],
        )

        # GPU temperature
        self.gpu_temperature_celsius = registry.gauge(
            "gpu_temperature_celsius",
            "GPU temperature in Celsius",
            ["gpu"],
        )

        # GPU power
        self.gpu_power_watts = registry.gauge(
            "gpu_power_watts",
            "GPU power consumption in Watts",
            ["gpu"],
        )

        # GPU clock speeds
        self.gpu_clock_hz = registry.gauge(
            "gpu_clock_hz",
            "GPU clock speed in Hz",
            ["gpu", "type"],  # graphics, memory, sm
        )

        # GPU processes
        self.gpu_processes = registry.gauge(
            "gpu_processes",
            "Number of GPU processes",
            ["gpu"],
        )

        self._init_nvml()

    def _init_nvml(self) -> None:
        """Initialize NVML."""
        if not PYNVML_AVAILABLE:
            logger.debug("pynvml not available, GPU metrics disabled")
            return

        try:
            pynvml.nvmlInit()
            self._initialized = True
            self._device_count = pynvml.nvmlDeviceGetCount()
            logger.info(f"NVML initialized, found {self._device_count} GPU(s)")
        except Exception as e:
            logger.debug(f"Failed to initialize NVML: {e}")
            self._initialized = False
            self._device_count = 0

    def collect(self) -> None:
        """Collect GPU metrics."""
        if not self._initialized:
            return

        try:
            for i in range(self._device_count):
                gpu_label = str(i)
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)

                # GPU info
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8")
                uuid = pynvml.nvmlDeviceGetUUID(handle)
                if isinstance(uuid, bytes):
                    uuid = uuid.decode("utf-8")
                self.gpu_info.set(1, {"gpu": gpu_label, "name": name, "uuid": uuid})

                # Utilization
                try:
                    utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    self.gpu_utilization_percent.set(utilization.gpu, {"gpu": gpu_label})
                except pynvml.NVMLError:
                    pass

                # Memory
                try:
                    memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    self.gpu_memory_bytes.set(memory.total, {"gpu": gpu_label, "type": "total"})
                    self.gpu_memory_bytes.set(memory.used, {"gpu": gpu_label, "type": "used"})
                    self.gpu_memory_bytes.set(memory.free, {"gpu": gpu_label, "type": "free"})
                    self.gpu_memory_percent.set(
                        (memory.used / memory.total) * 100 if memory.total > 0 else 0,
                        {"gpu": gpu_label}
                    )
                except pynvml.NVMLError:
                    pass

                # Temperature
                try:
                    temp = pynvml.nvmlDeviceGetTemperature(
                        handle,
                        pynvml.NVML_TEMPERATURE_GPU
                    )
                    self.gpu_temperature_celsius.set(temp, {"gpu": gpu_label})
                except pynvml.NVMLError:
                    pass

                # Power
                try:
                    power = pynvml.nvmlDeviceGetPowerUsage(handle)
                    self.gpu_power_watts.set(power / 1000.0, {"gpu": gpu_label})
                except pynvml.NVMLError:
                    pass

                # Clock speeds
                try:
                    graphics_clock = pynvml.nvmlDeviceGetClockInfo(
                        handle,
                        pynvml.NVML_CLOCK_GRAPHICS
                    )
                    memory_clock = pynvml.nvmlDeviceGetClockInfo(
                        handle,
                        pynvml.NVML_CLOCK_MEM
                    )
                    sm_clock = pynvml.nvmlDeviceGetClockInfo(
                        handle,
                        pynvml.NVML_CLOCK_SM
                    )
                    self.gpu_clock_hz.set(graphics_clock * 1e6, {"gpu": gpu_label, "type": "graphics"})
                    self.gpu_clock_hz.set(memory_clock * 1e6, {"gpu": gpu_label, "type": "memory"})
                    self.gpu_clock_hz.set(sm_clock * 1e6, {"gpu": gpu_label, "type": "sm"})
                except pynvml.NVMLError:
                    pass

                # GPU processes
                try:
                    processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
                    self.gpu_processes.set(len(processes), {"gpu": gpu_label})
                except pynvml.NVMLError:
                    pass

        except Exception as e:
            logger.error(f"Error collecting GPU metrics: {e}")

    def shutdown(self) -> None:
        """Shutdown NVML."""
        if self._initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
            self._initialized = False


# =============================================================================
# Process Collector
# =============================================================================


class ProcessCollector:
    """
    Collector for process-level metrics.

    جامع مقاييس العمليات.
    """

    def __init__(self, registry: PrometheusRegistry, pid: Optional[int] = None):
        self.registry = registry
        self.pid = pid or os.getpid()
        self._process: Optional[Any] = None

        # Process info
        self.process_info = registry.gauge(
            "process_info",
            "Process information",
            ["pid", "name"],
        )

        # CPU usage
        self.process_cpu_percent = registry.gauge(
            "process_cpu_percent",
            "Process CPU usage percentage",
        )

        self.process_cpu_seconds = registry.counter(
            "process_cpu_seconds_total",
            "Total CPU seconds used by process",
            ["mode"],  # user, system
        )

        # Memory usage
        self.process_memory_bytes = registry.gauge(
            "process_memory_bytes",
            "Process memory usage in bytes",
            ["type"],  # rss, vms, shared
        )

        self.process_memory_percent = registry.gauge(
            "process_memory_percent",
            "Process memory usage percentage",
        )

        # Thread count
        self.process_threads = registry.gauge(
            "process_threads",
            "Number of threads in process",
        )

        # File descriptors
        self.process_fds = registry.gauge(
            "process_open_fds",
            "Number of open file descriptors",
        )

        # Uptime
        self.process_start_time = registry.gauge(
            "process_start_time_seconds",
            "Process start time (Unix timestamp)",
        )

        self._init_process()

    def _init_process(self) -> None:
        """Initialize process handle."""
        if PSUTIL_AVAILABLE:
            try:
                self._process = psutil.Process(self.pid)
            except psutil.NoSuchProcess:
                logger.error(f"Process {self.pid} not found")

    def collect(self) -> None:
        """Collect process metrics."""
        if not self._process:
            return

        try:
            # Process info
            self.process_info.set(1, {"pid": str(self.pid), "name": self._process.name()})

            # CPU usage
            self.process_cpu_percent.set(self._process.cpu_percent())

            cpu_times = self._process.cpu_times()
            self.process_cpu_seconds.inc({"mode": "user"}, cpu_times.user)
            self.process_cpu_seconds.inc({"mode": "system"}, cpu_times.system)

            # Memory usage
            memory_info = self._process.memory_info()
            self.process_memory_bytes.set(memory_info.rss, {"type": "rss"})
            self.process_memory_bytes.set(memory_info.vms, {"type": "vms"})
            if hasattr(memory_info, "shared"):
                self.process_memory_bytes.set(memory_info.shared, {"type": "shared"})

            self.process_memory_percent.set(self._process.memory_percent())

            # Thread count
            self.process_threads.set(self._process.num_threads())

            # File descriptors
            try:
                self.process_fds.set(self._process.num_fds())
            except (AttributeError, psutil.AccessDenied):
                pass

            # Start time
            self.process_start_time.set(self._process.create_time())

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.error(f"Error collecting process metrics: {e}")


# =============================================================================
# Unified System Collector
# =============================================================================


class UnifiedSystemCollector:
    """
    Unified system metrics collector.

    جامع مقاييس النظام الموحد.

    Collects all system metrics in one place.
    """

    def __init__(
        self,
        registry: PrometheusRegistry,
        collect_cpu: bool = True,
        collect_memory: bool = True,
        collect_disk: bool = True,
        collect_network: bool = True,
        collect_gpu: bool = True,
        collect_process: bool = True,
        disk_paths: Optional[List[str]] = None,
    ):
        """
        Initialize unified collector.

        Args:
            registry: Prometheus registry
            collect_cpu: Enable CPU metrics
            collect_memory: Enable memory metrics
            collect_disk: Enable disk metrics
            collect_network: Enable network metrics
            collect_gpu: Enable GPU metrics
            collect_process: Enable process metrics
            disk_paths: Disk paths to monitor
        """
        self.registry = registry
        self.collectors: List[Any] = []

        # System info gauge
        self.system_info_gauge = registry.gauge(
            "system_info",
            "System information",
            ["hostname", "platform", "architecture", "python_version"],
        )

        # Build info gauge
        self.build_info = registry.gauge(
            "build_info",
            "Build information",
            ["version", "commit"],
        )

        # Initialize collectors
        if collect_cpu:
            self.cpu_collector = CPUCollector(registry)
            self.collectors.append(self.cpu_collector)

        if collect_memory:
            self.memory_collector = MemoryCollector(registry)
            self.collectors.append(self.memory_collector)

        if collect_disk:
            self.disk_collector = DiskCollector(registry, disk_paths)
            self.collectors.append(self.disk_collector)

        if collect_network:
            self.network_collector = NetworkCollector(registry)
            self.collectors.append(self.network_collector)

        if collect_gpu:
            self.gpu_collector = GPUCollector(registry)
            self.collectors.append(self.gpu_collector)

        if collect_process:
            self.process_collector = ProcessCollector(registry)
            self.collectors.append(self.process_collector)

        # Set system info
        self._set_system_info()

    def _set_system_info(self) -> None:
        """Set system information gauge."""
        info = SystemInfo.collect()
        self.system_info_gauge.set(1, {
            "hostname": info.hostname,
            "platform": info.platform,
            "architecture": info.architecture,
            "python_version": info.python_version,
        })

    def set_build_info(self, version: str, commit: str = "unknown") -> None:
        """Set build information."""
        self.build_info.set(1, {"version": version, "commit": commit})

    def collect(self) -> None:
        """Collect all system metrics."""
        for collector in self.collectors:
            try:
                collector.collect()
            except Exception as e:
                logger.error(f"Collector error: {e}")

    def shutdown(self) -> None:
        """Shutdown all collectors."""
        if hasattr(self, "gpu_collector"):
            self.gpu_collector.shutdown()


# =============================================================================
# Async Collector Runner
# =============================================================================


class AsyncCollectorRunner:
    """
    Async runner for periodic metric collection.

    منفذ غير متزامن لجمع المقاييس الدوري.
    """

    def __init__(
        self,
        collector: UnifiedSystemCollector,
        interval_seconds: float = 15.0,
    ):
        """
        Initialize async runner.

        Args:
            collector: System collector instance
            interval_seconds: Collection interval in seconds
        """
        self.collector = collector
        self.interval = interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Collection stats
        self._collection_count = 0
        self._last_collection: Optional[datetime] = None
        self._collection_duration_sum = 0.0

    async def start(self) -> None:
        """Start periodic collection."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Metric collection started (interval: {self.interval}s)")

    async def stop(self) -> None:
        """Stop periodic collection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self.collector.shutdown()
        logger.info("Metric collection stopped")

    async def _run_loop(self) -> None:
        """Run collection loop."""
        while self._running:
            start = time.time()

            try:
                # Run collection in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.collector.collect)

                duration = time.time() - start
                self._collection_count += 1
                self._collection_duration_sum += duration
                self._last_collection = datetime.utcnow()

            except Exception as e:
                logger.error(f"Collection error: {e}")

            # Wait for next interval
            elapsed = time.time() - start
            sleep_time = max(0, self.interval - elapsed)
            await asyncio.sleep(sleep_time)

    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        avg_duration = (
            self._collection_duration_sum / self._collection_count
            if self._collection_count > 0 else 0
        )

        return {
            "running": self._running,
            "collection_count": self._collection_count,
            "last_collection": (
                self._last_collection.isoformat()
                if self._last_collection else None
            ),
            "avg_collection_duration_seconds": avg_duration,
            "interval_seconds": self.interval,
        }
