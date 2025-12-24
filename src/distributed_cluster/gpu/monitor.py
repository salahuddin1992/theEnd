# -*- coding: utf-8 -*-
"""
GPU Monitor for NebulaCompute.

Provides comprehensive GPU health monitoring, metrics collection,
and alerting capabilities.

مراقب GPU لـ NebulaCompute.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

try:
    import pynvml

    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

logger = logging.getLogger(__name__)


class GPUHealthStatus(str, Enum):
    """GPU health status."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    OFFLINE = "offline"


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class GPUMetrics:
    """
    GPU metrics snapshot.

    لقطة مقاييس GPU.
    """

    gpu_index: int
    timestamp: datetime
    name: str = ""
    uuid: str = ""

    # Utilization
    gpu_utilization: float = 0.0  # 0-100%
    memory_utilization: float = 0.0  # 0-100%
    encoder_utilization: float = 0.0  # 0-100%
    decoder_utilization: float = 0.0  # 0-100%

    # Memory
    memory_total_mb: int = 0
    memory_used_mb: int = 0
    memory_free_mb: int = 0

    # Temperature
    temperature_gpu: int = 0  # Celsius
    temperature_memory: Optional[int] = None

    # Power
    power_draw_watts: float = 0.0
    power_limit_watts: float = 0.0
    power_state: int = 0  # P0-P12

    # Clocks
    clock_graphics_mhz: int = 0
    clock_memory_mhz: int = 0
    clock_sm_mhz: int = 0

    # PCIe
    pcie_tx_throughput_kb: int = 0
    pcie_rx_throughput_kb: int = 0
    pcie_link_gen: int = 0
    pcie_link_width: int = 0

    # Processes
    process_count: int = 0
    compute_process_count: int = 0

    # ECC Errors
    ecc_errors_single: int = 0
    ecc_errors_double: int = 0

    # Fan
    fan_speed: int = 0  # 0-100%

    # Performance
    throttle_reasons: List[str] = field(default_factory=list)

    @property
    def memory_utilization_percent(self) -> float:
        """Calculate memory utilization percentage."""
        if self.memory_total_mb == 0:
            return 0.0
        return (self.memory_used_mb / self.memory_total_mb) * 100

    @property
    def power_utilization_percent(self) -> float:
        """Calculate power utilization percentage."""
        if self.power_limit_watts == 0:
            return 0.0
        return (self.power_draw_watts / self.power_limit_watts) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "gpu_index": self.gpu_index,
            "timestamp": self.timestamp.isoformat(),
            "name": self.name,
            "uuid": self.uuid,
            "utilization": {
                "gpu": self.gpu_utilization,
                "memory": self.memory_utilization,
                "encoder": self.encoder_utilization,
                "decoder": self.decoder_utilization,
            },
            "memory": {
                "total_mb": self.memory_total_mb,
                "used_mb": self.memory_used_mb,
                "free_mb": self.memory_free_mb,
                "utilization_percent": self.memory_utilization_percent,
            },
            "temperature": {
                "gpu": self.temperature_gpu,
                "memory": self.temperature_memory,
            },
            "power": {
                "draw_watts": self.power_draw_watts,
                "limit_watts": self.power_limit_watts,
                "utilization_percent": self.power_utilization_percent,
                "state": self.power_state,
            },
            "clocks": {
                "graphics_mhz": self.clock_graphics_mhz,
                "memory_mhz": self.clock_memory_mhz,
                "sm_mhz": self.clock_sm_mhz,
            },
            "pcie": {
                "tx_throughput_kb": self.pcie_tx_throughput_kb,
                "rx_throughput_kb": self.pcie_rx_throughput_kb,
                "link_gen": self.pcie_link_gen,
                "link_width": self.pcie_link_width,
            },
            "processes": {
                "total": self.process_count,
                "compute": self.compute_process_count,
            },
            "ecc": {
                "single_bit_errors": self.ecc_errors_single,
                "double_bit_errors": self.ecc_errors_double,
            },
            "fan_speed": self.fan_speed,
            "throttle_reasons": self.throttle_reasons,
        }


@dataclass
class GPUAlert:
    """
    GPU alert.

    تنبيه GPU.
    """

    alert_id: str
    gpu_index: int
    severity: AlertSeverity
    message: str
    metric_name: str
    metric_value: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class GPUMonitor:
    """
    Monitors GPU health and collects metrics.

    مراقب صحة GPU وجمع المقاييس.

    Features:
    - Real-time metrics collection
    - Health status tracking
    - Alerting with configurable thresholds
    - Historical data retention
    - Anomaly detection
    """

    DEFAULT_THRESHOLDS = {
        "temperature_warning": 80,  # Celsius
        "temperature_critical": 90,
        "memory_warning": 85,  # Percent
        "memory_critical": 95,
        "utilization_warning": 95,  # Percent
        "power_warning": 90,  # Percent of limit
        "ecc_warning": 10,  # Error count
        "ecc_critical": 100,
    }

    def __init__(
        self,
        poll_interval_seconds: float = 5.0,
        history_retention_minutes: int = 60,
        thresholds: Optional[Dict[str, float]] = None,
        alert_callback: Optional[Callable[[GPUAlert], None]] = None,
    ):
        """
        Initialize GPU Monitor.

        Args:
            poll_interval_seconds: Metrics collection interval
            history_retention_minutes: How long to keep historical data
            thresholds: Custom alert thresholds
            alert_callback: Callback for alerts
        """
        self.poll_interval = poll_interval_seconds
        self.history_retention = timedelta(minutes=history_retention_minutes)
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.alert_callback = alert_callback

        # State
        self._gpu_count = 0
        self._handles: Dict[int, Any] = {}
        self._latest_metrics: Dict[int, GPUMetrics] = {}
        self._metrics_history: Dict[int, List[GPUMetrics]] = {}
        self._alerts: Dict[str, GPUAlert] = {}
        self._health_status: Dict[int, GPUHealthStatus] = {}

        # Control
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # NVML initialization
        self._nvml_initialized = False
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self._nvml_initialized = True
                self._gpu_count = pynvml.nvmlDeviceGetCount()
                logger.info(f"NVML initialized, found {self._gpu_count} GPUs")
            except Exception as e:
                logger.warning(f"Failed to initialize NVML: {e}")

    async def start(self) -> None:
        """Start GPU monitoring."""
        if self._running:
            return

        self._running = True

        # Initialize GPU handles
        if self._nvml_initialized:
            for i in range(self._gpu_count):
                try:
                    self._handles[i] = pynvml.nvmlDeviceGetHandleByIndex(i)
                    self._metrics_history[i] = []
                    self._health_status[i] = GPUHealthStatus.UNKNOWN
                except Exception as e:
                    logger.error(f"Failed to get handle for GPU {i}: {e}")

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("GPU Monitor started")

    async def stop(self) -> None:
        """Stop GPU monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("GPU Monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._collect_all_metrics()
                await self._check_health()
                await self._cleanup_history()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in GPU monitor loop: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _collect_all_metrics(self) -> None:
        """Collect metrics from all GPUs."""
        if not self._nvml_initialized:
            return

        for gpu_index, handle in self._handles.items():
            try:
                metrics = await self._collect_gpu_metrics(gpu_index, handle)
                async with self._lock:
                    self._latest_metrics[gpu_index] = metrics
                    self._metrics_history[gpu_index].append(metrics)
            except Exception as e:
                logger.warning(f"Failed to collect metrics for GPU {gpu_index}: {e}")

    async def _collect_gpu_metrics(self, gpu_index: int, handle) -> GPUMetrics:
        """Collect metrics from a single GPU."""
        now = datetime.utcnow()
        metrics = GPUMetrics(gpu_index=gpu_index, timestamp=now)

        try:
            # Basic info
            name = pynvml.nvmlDeviceGetName(handle)
            metrics.name = name.decode() if isinstance(name, bytes) else name

            uuid_str = pynvml.nvmlDeviceGetUUID(handle)
            metrics.uuid = uuid_str.decode() if isinstance(uuid_str, bytes) else uuid_str

            # Utilization
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            metrics.gpu_utilization = util.gpu
            metrics.memory_utilization = util.memory

            # Try to get encoder/decoder utilization
            try:
                enc_util = pynvml.nvmlDeviceGetEncoderUtilization(handle)
                metrics.encoder_utilization = enc_util[0]
            except Exception:
                pass

            try:
                dec_util = pynvml.nvmlDeviceGetDecoderUtilization(handle)
                metrics.decoder_utilization = dec_util[0]
            except Exception:
                pass

            # Memory
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            metrics.memory_total_mb = mem_info.total // (1024 * 1024)
            metrics.memory_used_mb = mem_info.used // (1024 * 1024)
            metrics.memory_free_mb = mem_info.free // (1024 * 1024)

            # Temperature
            metrics.temperature_gpu = pynvml.nvmlDeviceGetTemperature(
                handle, pynvml.NVML_TEMPERATURE_GPU
            )

            # Power
            try:
                metrics.power_draw_watts = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000
            except Exception:
                pass

            try:
                metrics.power_limit_watts = (
                    pynvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000
                )
            except Exception:
                pass

            try:
                metrics.power_state = pynvml.nvmlDeviceGetPowerState(handle)
            except Exception:
                pass

            # Clocks
            try:
                metrics.clock_graphics_mhz = pynvml.nvmlDeviceGetClockInfo(
                    handle, pynvml.NVML_CLOCK_GRAPHICS
                )
                metrics.clock_memory_mhz = pynvml.nvmlDeviceGetClockInfo(
                    handle, pynvml.NVML_CLOCK_MEM
                )
                metrics.clock_sm_mhz = pynvml.nvmlDeviceGetClockInfo(
                    handle, pynvml.NVML_CLOCK_SM
                )
            except Exception:
                pass

            # PCIe
            try:
                metrics.pcie_tx_throughput_kb = pynvml.nvmlDeviceGetPcieThroughput(
                    handle, pynvml.NVML_PCIE_UTIL_TX_BYTES
                )
                metrics.pcie_rx_throughput_kb = pynvml.nvmlDeviceGetPcieThroughput(
                    handle, pynvml.NVML_PCIE_UTIL_RX_BYTES
                )
            except Exception:
                pass

            # Processes
            try:
                processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
                metrics.compute_process_count = len(processes)
                graphics = pynvml.nvmlDeviceGetGraphicsRunningProcesses(handle)
                metrics.process_count = len(processes) + len(graphics)
            except Exception:
                pass

            # ECC Errors
            try:
                metrics.ecc_errors_single = pynvml.nvmlDeviceGetTotalEccErrors(
                    handle,
                    pynvml.NVML_SINGLE_BIT_ECC,
                    pynvml.NVML_VOLATILE_ECC,
                )
                metrics.ecc_errors_double = pynvml.nvmlDeviceGetTotalEccErrors(
                    handle,
                    pynvml.NVML_DOUBLE_BIT_ECC,
                    pynvml.NVML_VOLATILE_ECC,
                )
            except Exception:
                pass

            # Fan
            try:
                metrics.fan_speed = pynvml.nvmlDeviceGetFanSpeed(handle)
            except Exception:
                pass

            # Throttle reasons
            try:
                reasons = pynvml.nvmlDeviceGetCurrentClocksThrottleReasons(handle)
                metrics.throttle_reasons = self._parse_throttle_reasons(reasons)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error collecting GPU {gpu_index} metrics: {e}")

        return metrics

    def _parse_throttle_reasons(self, reasons: int) -> List[str]:
        """Parse throttle reason bitmask."""
        result = []
        reason_map = {
            1: "gpu_idle",
            2: "applications_clocks_setting",
            4: "sw_power_cap",
            8: "hw_slowdown",
            16: "sync_boost",
            32: "sw_thermal_slowdown",
            64: "hw_thermal_slowdown",
            128: "hw_power_brake_slowdown",
            256: "display_clock_setting",
        }
        for bit, name in reason_map.items():
            if reasons & bit:
                result.append(name)
        return result

    async def _check_health(self) -> None:
        """Check GPU health and generate alerts."""
        for gpu_index, metrics in self._latest_metrics.items():
            health = GPUHealthStatus.HEALTHY
            alerts = []

            # Temperature check
            if metrics.temperature_gpu >= self.thresholds["temperature_critical"]:
                health = GPUHealthStatus.CRITICAL
                alerts.append(
                    self._create_alert(
                        gpu_index,
                        AlertSeverity.CRITICAL,
                        f"GPU temperature critical: {metrics.temperature_gpu}°C",
                        "temperature",
                        metrics.temperature_gpu,
                        self.thresholds["temperature_critical"],
                    )
                )
            elif metrics.temperature_gpu >= self.thresholds["temperature_warning"]:
                if health != GPUHealthStatus.CRITICAL:
                    health = GPUHealthStatus.WARNING
                alerts.append(
                    self._create_alert(
                        gpu_index,
                        AlertSeverity.WARNING,
                        f"GPU temperature high: {metrics.temperature_gpu}°C",
                        "temperature",
                        metrics.temperature_gpu,
                        self.thresholds["temperature_warning"],
                    )
                )

            # Memory check
            mem_util = metrics.memory_utilization_percent
            if mem_util >= self.thresholds["memory_critical"]:
                if health != GPUHealthStatus.CRITICAL:
                    health = GPUHealthStatus.CRITICAL
                alerts.append(
                    self._create_alert(
                        gpu_index,
                        AlertSeverity.CRITICAL,
                        f"GPU memory critical: {mem_util:.1f}%",
                        "memory_utilization",
                        mem_util,
                        self.thresholds["memory_critical"],
                    )
                )
            elif mem_util >= self.thresholds["memory_warning"]:
                if health == GPUHealthStatus.HEALTHY:
                    health = GPUHealthStatus.WARNING
                alerts.append(
                    self._create_alert(
                        gpu_index,
                        AlertSeverity.WARNING,
                        f"GPU memory high: {mem_util:.1f}%",
                        "memory_utilization",
                        mem_util,
                        self.thresholds["memory_warning"],
                    )
                )

            # ECC check
            total_ecc = metrics.ecc_errors_single + metrics.ecc_errors_double
            if total_ecc >= self.thresholds["ecc_critical"]:
                health = GPUHealthStatus.CRITICAL
                alerts.append(
                    self._create_alert(
                        gpu_index,
                        AlertSeverity.CRITICAL,
                        f"ECC errors critical: {total_ecc}",
                        "ecc_errors",
                        total_ecc,
                        self.thresholds["ecc_critical"],
                    )
                )
            elif total_ecc >= self.thresholds["ecc_warning"]:
                if health == GPUHealthStatus.HEALTHY:
                    health = GPUHealthStatus.WARNING
                alerts.append(
                    self._create_alert(
                        gpu_index,
                        AlertSeverity.WARNING,
                        f"ECC errors detected: {total_ecc}",
                        "ecc_errors",
                        total_ecc,
                        self.thresholds["ecc_warning"],
                    )
                )

            # Update health status
            self._health_status[gpu_index] = health

            # Process alerts
            for alert in alerts:
                await self._process_alert(alert)

    def _create_alert(
        self,
        gpu_index: int,
        severity: AlertSeverity,
        message: str,
        metric_name: str,
        metric_value: float,
        threshold: float,
    ) -> GPUAlert:
        """Create a GPU alert."""
        import uuid

        return GPUAlert(
            alert_id=str(uuid.uuid4()),
            gpu_index=gpu_index,
            severity=severity,
            message=message,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold=threshold,
        )

    async def _process_alert(self, alert: GPUAlert) -> None:
        """Process a GPU alert."""
        # Check for duplicate alerts

        # Only add if not a duplicate recent alert
        recent_cutoff = datetime.utcnow() - timedelta(minutes=5)
        is_duplicate = any(
            a.gpu_index == alert.gpu_index
            and a.metric_name == alert.metric_name
            and a.severity == alert.severity
            and a.timestamp > recent_cutoff
            and not a.resolved
            for a in self._alerts.values()
        )

        if not is_duplicate:
            self._alerts[alert.alert_id] = alert
            logger.warning(f"GPU Alert: {alert.message}")

            if self.alert_callback:
                try:
                    self.alert_callback(alert)
                except Exception as e:
                    logger.error(f"Alert callback error: {e}")

    async def _cleanup_history(self) -> None:
        """Clean up old metrics history."""
        cutoff = datetime.utcnow() - self.history_retention

        async with self._lock:
            for gpu_index in self._metrics_history:
                self._metrics_history[gpu_index] = [
                    m
                    for m in self._metrics_history[gpu_index]
                    if m.timestamp > cutoff
                ]

    async def get_metrics(self, gpu_index: int) -> Optional[GPUMetrics]:
        """Get latest metrics for a GPU."""
        return self._latest_metrics.get(gpu_index)

    async def get_all_metrics(self) -> Dict[int, GPUMetrics]:
        """Get latest metrics for all GPUs."""
        return dict(self._latest_metrics)

    async def get_health_status(self, gpu_index: int) -> GPUHealthStatus:
        """Get health status for a GPU."""
        return self._health_status.get(gpu_index, GPUHealthStatus.UNKNOWN)

    async def get_all_health_status(self) -> Dict[int, GPUHealthStatus]:
        """Get health status for all GPUs."""
        return dict(self._health_status)

    async def get_metrics_history(
        self,
        gpu_index: int,
        duration_minutes: int = 10,
    ) -> List[GPUMetrics]:
        """Get metrics history for a GPU."""
        cutoff = datetime.utcnow() - timedelta(minutes=duration_minutes)
        history = self._metrics_history.get(gpu_index, [])
        return [m for m in history if m.timestamp > cutoff]

    async def get_alerts(
        self,
        gpu_index: Optional[int] = None,
        include_resolved: bool = False,
    ) -> List[GPUAlert]:
        """Get alerts, optionally filtered by GPU."""
        alerts = list(self._alerts.values())

        if gpu_index is not None:
            alerts = [a for a in alerts if a.gpu_index == gpu_index]

        if not include_resolved:
            alerts = [a for a in alerts if not a.resolved]

        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        if alert_id in self._alerts:
            self._alerts[alert_id].acknowledged = True
            return True
        return False

    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        if alert_id in self._alerts:
            self._alerts[alert_id].resolved = True
            self._alerts[alert_id].resolved_at = datetime.utcnow()
            return True
        return False

    @property
    def gpu_count(self) -> int:
        """Get number of GPUs."""
        return self._gpu_count

    async def get_summary(self) -> Dict[str, Any]:
        """Get monitoring summary."""
        return {
            "gpu_count": self._gpu_count,
            "nvml_available": self._nvml_initialized,
            "monitoring_active": self._running,
            "poll_interval": self.poll_interval,
            "health_status": {
                idx: status.value for idx, status in self._health_status.items()
            },
            "active_alerts": len([a for a in self._alerts.values() if not a.resolved]),
            "total_alerts": len(self._alerts),
        }

    async def shutdown(self) -> None:
        """Shutdown GPU monitor."""
        await self.stop()
        if self._nvml_initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
        logger.info("GPU Monitor shutdown complete")
