"""
Resource Manager - مدير الموارد المتقدم
=======================================

Full resource management for:
- CPU (all cores, multi-threading)
- GPU (NVIDIA CUDA, AMD ROCm, Apple Metal)
- RAM (full memory utilization)
- Disk (storage management)
- Network (bandwidth optimization)
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GPUVendor(str, Enum):
    """أنواع GPU المدعومة."""

    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"
    UNKNOWN = "unknown"


class ResourceMode(str, Enum):
    """أوضاع استخدام الموارد."""

    CONSERVATIVE = "conservative"  # استخدام حذر (50%)
    BALANCED = "balanced"  # متوازن (75%)
    AGGRESSIVE = "aggressive"  # كامل (90%)
    MAXIMUM = "maximum"  # أقصى استخدام (100%)


@dataclass
class CPUConfig:
    """إعدادات المعالج."""

    use_all_cores: bool = True
    max_cores: Optional[int] = None
    max_threads: Optional[int] = None
    affinity: Optional[List[int]] = None
    priority: str = "normal"  # low, normal, high, realtime

    @property
    def available_cores(self) -> int:
        """عدد الأنوية المتاحة."""
        total = os.cpu_count() or 1
        if self.max_cores:
            return min(self.max_cores, total)
        return total

    @property
    def available_threads(self) -> int:
        """عدد الخيوط المتاحة."""
        total = os.cpu_count() or 1
        if self.max_threads:
            return min(self.max_threads, total * 2)
        return total * 2


@dataclass
class GPUConfig:
    """إعدادات GPU."""

    enabled: bool = True
    use_all_gpus: bool = True
    gpu_ids: Optional[List[int]] = None
    memory_fraction: float = 0.95  # نسبة الذاكرة المسموح باستخدامها
    allow_growth: bool = True  # السماح بنمو الذاكرة تدريجياً
    mixed_precision: bool = True  # الدقة المختلطة لأداء أفضل
    tensor_cores: bool = True  # استخدام Tensor Cores (NVIDIA)


@dataclass
class MemoryConfig:
    """إعدادات الذاكرة."""

    max_memory_mb: Optional[int] = None  # None = استخدام كل الذاكرة
    memory_fraction: float = 0.90  # نسبة الذاكرة المسموح باستخدامها
    swap_enabled: bool = True  # السماح باستخدام swap
    memory_mapping: bool = True  # استخدام memory-mapped files
    large_pages: bool = True  # استخدام صفحات كبيرة


@dataclass
class DiskConfig:
    """إعدادات القرص."""

    temp_dir: Optional[str] = None
    max_temp_size_gb: float = 100.0
    async_io: bool = True
    cache_size_mb: int = 1024


@dataclass
class NetworkConfig:
    """إعدادات الشبكة."""

    max_connections: int = 1000
    connection_timeout: float = 30.0
    keep_alive: bool = True
    compression: bool = True


@dataclass
class FullResourceConfig:
    """
    تكوين كامل لجميع الموارد.

    Full configuration for maximum resource utilization.
    """

    cpu: CPUConfig = field(default_factory=CPUConfig)
    gpu: GPUConfig = field(default_factory=GPUConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    disk: DiskConfig = field(default_factory=DiskConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    mode: ResourceMode = ResourceMode.MAXIMUM

    @classmethod
    def maximum_performance(cls) -> FullResourceConfig:
        """إعدادات الأداء الأقصى."""
        return cls(
            cpu=CPUConfig(
                use_all_cores=True,
                priority="high",
            ),
            gpu=GPUConfig(
                enabled=True,
                use_all_gpus=True,
                memory_fraction=0.98,
                mixed_precision=True,
                tensor_cores=True,
            ),
            memory=MemoryConfig(
                memory_fraction=0.95,
                swap_enabled=True,
                memory_mapping=True,
                large_pages=True,
            ),
            disk=DiskConfig(
                async_io=True,
                cache_size_mb=2048,
            ),
            network=NetworkConfig(
                max_connections=2000,
                compression=True,
            ),
            mode=ResourceMode.MAXIMUM,
        )


@dataclass
class GPUDevice:
    """معلومات جهاز GPU."""

    index: int
    name: str
    vendor: GPUVendor
    uuid: str = ""

    # Memory
    total_memory_mb: int = 0
    free_memory_mb: int = 0
    used_memory_mb: int = 0

    # Utilization
    utilization_percent: float = 0.0
    memory_utilization_percent: float = 0.0

    # Capabilities
    compute_capability: str = ""
    cuda_cores: int = 0
    tensor_cores: int = 0

    # Status
    temperature_c: float = 0.0
    power_draw_w: float = 0.0
    power_limit_w: float = 0.0
    fan_speed_percent: float = 0.0

    @property
    def is_available(self) -> bool:
        """هل GPU متاحة؟"""
        return self.utilization_percent < 95 and self.free_memory_mb > 500


@dataclass
class SystemResources:
    """
    معلومات موارد النظام الكاملة.

    Complete system resource information.
    """

    # CPU
    cpu_count: int = 0
    cpu_threads: int = 0
    cpu_percent: float = 0.0
    cpu_freq_mhz: float = 0.0
    cpu_model: str = ""

    # Memory
    ram_total_mb: int = 0
    ram_available_mb: int = 0
    ram_used_mb: int = 0
    ram_percent: float = 0.0
    swap_total_mb: int = 0
    swap_used_mb: int = 0

    # GPU
    gpus: List[GPUDevice] = field(default_factory=list)
    total_gpu_memory_mb: int = 0
    total_gpu_free_mb: int = 0

    # Disk
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    disk_used_gb: float = 0.0

    # System
    platform: str = ""
    hostname: str = ""
    os_version: str = ""
    python_version: str = ""

    # Timestamp
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def gpu_count(self) -> int:
        """عدد GPUs."""
        return len(self.gpus)

    @property
    def has_gpu(self) -> bool:
        """هل يوجد GPU؟"""
        return len(self.gpus) > 0

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        return {
            "cpu": {
                "count": self.cpu_count,
                "threads": self.cpu_threads,
                "percent": self.cpu_percent,
                "freq_mhz": self.cpu_freq_mhz,
                "model": self.cpu_model,
            },
            "memory": {
                "total_mb": self.ram_total_mb,
                "available_mb": self.ram_available_mb,
                "used_mb": self.ram_used_mb,
                "percent": self.ram_percent,
                "swap_total_mb": self.swap_total_mb,
                "swap_used_mb": self.swap_used_mb,
            },
            "gpu": {
                "count": self.gpu_count,
                "total_memory_mb": self.total_gpu_memory_mb,
                "free_memory_mb": self.total_gpu_free_mb,
                "devices": [
                    {
                        "index": g.index,
                        "name": g.name,
                        "vendor": g.vendor.value,
                        "total_memory_mb": g.total_memory_mb,
                        "free_memory_mb": g.free_memory_mb,
                        "utilization_percent": g.utilization_percent,
                        "temperature_c": g.temperature_c,
                    }
                    for g in self.gpus
                ],
            },
            "disk": {
                "total_gb": self.disk_total_gb,
                "free_gb": self.disk_free_gb,
                "used_gb": self.disk_used_gb,
            },
            "system": {
                "platform": self.platform,
                "hostname": self.hostname,
                "os_version": self.os_version,
                "python_version": self.python_version,
            },
            "timestamp": self.timestamp.isoformat(),
        }


class ResourceManager:
    """
    مدير الموارد الشامل.

    Comprehensive resource manager for maximum utilization of:
    - CPU (all cores)
    - GPU (all devices)
    - RAM (full memory)
    - Disk
    - Network
    """

    def __init__(self, config: Optional[FullResourceConfig] = None):
        self.config = config or FullResourceConfig.maximum_performance()
        self._lock = threading.Lock()
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None

    def get_system_resources(self) -> SystemResources:
        """
        الحصول على معلومات موارد النظام الكاملة.

        Get complete system resource information.
        """
        resources = SystemResources()

        # Platform info
        resources.platform = platform.system()
        resources.hostname = platform.node()
        resources.os_version = platform.version()
        resources.python_version = platform.python_version()

        # CPU info
        resources.cpu_count = os.cpu_count() or 1
        resources.cpu_threads = resources.cpu_count * 2

        # Try to get detailed CPU info
        try:
            import psutil

            resources.cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                resources.cpu_freq_mhz = cpu_freq.current

            # Memory
            mem = psutil.virtual_memory()
            resources.ram_total_mb = mem.total // (1024 * 1024)
            resources.ram_available_mb = mem.available // (1024 * 1024)
            resources.ram_used_mb = mem.used // (1024 * 1024)
            resources.ram_percent = mem.percent

            # Swap
            swap = psutil.swap_memory()
            resources.swap_total_mb = swap.total // (1024 * 1024)
            resources.swap_used_mb = swap.used // (1024 * 1024)

            # Disk
            disk = psutil.disk_usage("/")
            resources.disk_total_gb = disk.total / (1024**3)
            resources.disk_free_gb = disk.free / (1024**3)
            resources.disk_used_gb = disk.used / (1024**3)

        except ImportError:
            logger.warning("psutil not available, limited resource info")

        # GPU info
        resources.gpus = self._get_gpu_info()
        resources.total_gpu_memory_mb = sum(g.total_memory_mb for g in resources.gpus)
        resources.total_gpu_free_mb = sum(g.free_memory_mb for g in resources.gpus)

        # CPU model
        resources.cpu_model = self._get_cpu_model()

        return resources

    def _get_gpu_info(self) -> List[GPUDevice]:
        """الحصول على معلومات GPU."""
        gpus = []

        # Try NVIDIA first
        nvidia_gpus = self._get_nvidia_gpus()
        if nvidia_gpus:
            gpus.extend(nvidia_gpus)

        # Try AMD
        amd_gpus = self._get_amd_gpus()
        if amd_gpus:
            gpus.extend(amd_gpus)

        # Try Apple Metal
        if platform.system() == "Darwin":
            apple_gpus = self._get_apple_gpus()
            if apple_gpus:
                gpus.extend(apple_gpus)

        return gpus

    def _get_nvidia_gpus(self) -> List[GPUDevice]:
        """الحصول على معلومات NVIDIA GPU."""
        gpus = []

        try:
            # Try nvidia-smi
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,uuid,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu,power.draw,power.limit",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) >= 10:
                            gpu = GPUDevice(
                                index=int(parts[0]),
                                name=parts[1],
                                vendor=GPUVendor.NVIDIA,
                                uuid=parts[2],
                                total_memory_mb=int(float(parts[3])),
                                free_memory_mb=int(float(parts[4])),
                                used_memory_mb=int(float(parts[5])),
                                utilization_percent=float(parts[6]) if parts[6] != "[N/A]" else 0,
                                temperature_c=float(parts[7]) if parts[7] != "[N/A]" else 0,
                                power_draw_w=float(parts[8]) if parts[8] != "[N/A]" else 0,
                                power_limit_w=float(parts[9]) if parts[9] != "[N/A]" else 0,
                            )
                            gpus.append(gpu)

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"nvidia-smi not available: {e}")

        # Try pynvml as fallback
        if not gpus:
            try:
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
                        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                    except Exception:
                        temp = 0

                    try:
                        power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000  # mW to W
                    except Exception:
                        power = 0

                    gpu = GPUDevice(
                        index=i,
                        name=name,
                        vendor=GPUVendor.NVIDIA,
                        total_memory_mb=memory.total // (1024 * 1024),
                        free_memory_mb=memory.free // (1024 * 1024),
                        used_memory_mb=memory.used // (1024 * 1024),
                        utilization_percent=utilization.gpu,
                        memory_utilization_percent=utilization.memory,
                        temperature_c=temp,
                        power_draw_w=power,
                    )
                    gpus.append(gpu)

                pynvml.nvmlShutdown()

            except Exception as e:
                logger.debug(f"pynvml not available: {e}")

        return gpus

    def _get_amd_gpus(self) -> List[GPUDevice]:
        """الحصول على معلومات AMD GPU."""
        gpus = []

        try:
            # Try rocm-smi
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                import json

                data = json.loads(result.stdout)
                for card_id, card_info in data.items():
                    if card_id.startswith("card"):
                        gpu = GPUDevice(
                            index=int(card_id.replace("card", "")),
                            name=f"AMD GPU {card_id}",
                            vendor=GPUVendor.AMD,
                            total_memory_mb=int(card_info.get("VRAM Total Memory (B)", 0)) // (1024 * 1024),
                            free_memory_mb=int(card_info.get("VRAM Total Usable Memory (B)", 0)) // (1024 * 1024),
                        )
                        gpus.append(gpu)

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"rocm-smi not available: {e}")

        return gpus

    def _get_apple_gpus(self) -> List[GPUDevice]:
        """الحصول على معلومات Apple GPU (Metal)."""
        gpus = []

        try:
            # Try to get Metal GPU info on macOS
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                import json

                data = json.loads(result.stdout)
                displays = data.get("SPDisplaysDataType", [])

                for i, display in enumerate(displays):
                    gpu = GPUDevice(
                        index=i,
                        name=display.get("sppci_model", "Apple GPU"),
                        vendor=GPUVendor.APPLE,
                        total_memory_mb=int(
                            display.get("spdisplays_vram", "0").replace(" MB", "").replace(" GB", "000") or 0
                        ),
                    )
                    gpus.append(gpu)

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"system_profiler not available: {e}")

        return gpus

    def _get_cpu_model(self) -> str:
        """الحصول على اسم المعالج."""
        system = platform.system()

        try:
            if system == "Linux":
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if "model name" in line:
                            return line.split(":")[1].strip()

            elif system == "Darwin":
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return result.stdout.strip()

            elif system == "Windows":
                import winreg

                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                return winreg.QueryValueEx(key, "ProcessorNameString")[0]

        except Exception:
            pass

        return platform.processor() or "Unknown CPU"

    def optimize_for_ai(self) -> Dict[str, Any]:
        """
        تحسين النظام لأعمال الذكاء الاصطناعي.

        Optimize system for AI workloads.
        Returns optimization settings applied.
        """
        optimizations = {}

        # CPU optimizations
        if self.config.cpu.use_all_cores:
            # Set thread count for common libraries
            cores = self.config.cpu.available_cores
            threads = self.config.cpu.available_threads

            os.environ["OMP_NUM_THREADS"] = str(threads)
            os.environ["MKL_NUM_THREADS"] = str(threads)
            os.environ["OPENBLAS_NUM_THREADS"] = str(threads)
            os.environ["VECLIB_MAXIMUM_THREADS"] = str(threads)
            os.environ["NUMEXPR_NUM_THREADS"] = str(threads)

            optimizations["cpu"] = {
                "cores": cores,
                "threads": threads,
                "env_vars_set": True,
            }

        # GPU optimizations
        if self.config.gpu.enabled:
            gpu_ids = self._get_available_gpu_ids()

            if gpu_ids:
                # CUDA visible devices
                os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, gpu_ids))

                # Memory growth
                if self.config.gpu.allow_growth:
                    os.environ["TF_FORCE_GPU_ALLOW_GROWTH"] = "true"

                # Mixed precision
                if self.config.gpu.mixed_precision:
                    os.environ["TF_ENABLE_AUTO_MIXED_PRECISION"] = "1"

                optimizations["gpu"] = {
                    "devices": gpu_ids,
                    "memory_fraction": self.config.gpu.memory_fraction,
                    "allow_growth": self.config.gpu.allow_growth,
                    "mixed_precision": self.config.gpu.mixed_precision,
                }

        # Memory optimizations
        if self.config.memory.memory_mapping:
            # Enable memory-mapped file support
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

        optimizations["memory"] = {
            "fraction": self.config.memory.memory_fraction,
            "swap_enabled": self.config.memory.swap_enabled,
        }

        return optimizations

    def _get_available_gpu_ids(self) -> List[int]:
        """الحصول على معرفات GPU المتاحة."""
        if self.config.gpu.gpu_ids:
            return self.config.gpu.gpu_ids

        gpus = self._get_gpu_info()
        return [g.index for g in gpus if g.is_available or self.config.mode == ResourceMode.MAXIMUM]

    def allocate_resources(
        self,
        cpu_cores: Optional[int] = None,
        memory_mb: Optional[int] = None,
        gpu_count: Optional[int] = None,
        gpu_memory_mb: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        تخصيص موارد محددة.

        Allocate specific resources for a task.
        """
        resources = self.get_system_resources()

        allocation = {
            "cpu_cores": cpu_cores or resources.cpu_count,
            "memory_mb": memory_mb or int(resources.ram_available_mb * self.config.memory.memory_fraction),
            "gpu_count": gpu_count or resources.gpu_count,
            "gpu_memory_mb": gpu_memory_mb or int(resources.total_gpu_free_mb * self.config.gpu.memory_fraction),
        }

        return allocation

    async def monitor_resources(
        self,
        interval: float = 5.0,
        callback: Optional[callable] = None,
    ) -> None:
        """
        مراقبة الموارد بشكل مستمر.

        Continuously monitor system resources.
        """
        self._monitoring = True

        while self._monitoring:
            try:
                resources = self.get_system_resources()

                if callback:
                    await callback(resources)

                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                await asyncio.sleep(interval)

    def stop_monitoring(self) -> None:
        """إيقاف المراقبة."""
        self._monitoring = False

    def get_optimal_batch_size(
        self,
        model_size_mb: int,
        input_size_mb: int,
    ) -> int:
        """
        حساب حجم الدفعة الأمثل.

        Calculate optimal batch size based on available memory.
        """
        resources = self.get_system_resources()

        if resources.has_gpu:
            available_mb = resources.total_gpu_free_mb * self.config.gpu.memory_fraction
        else:
            available_mb = resources.ram_available_mb * self.config.memory.memory_fraction

        # Reserve memory for model
        available_mb -= model_size_mb

        if available_mb <= 0:
            return 1

        # Calculate batch size
        batch_size = int(available_mb / input_size_mb)
        return max(1, batch_size)

    def get_resource_summary(self) -> str:
        """
        ملخص الموارد كنص.

        Get a human-readable resource summary.
        """
        resources = self.get_system_resources()

        lines = [
            "=" * 50,
            "System Resources Summary",
            "=" * 50,
            "",
            f"Platform: {resources.platform} ({resources.os_version})",
            f"Hostname: {resources.hostname}",
            "",
            "CPU:",
            f"  Model: {resources.cpu_model}",
            f"  Cores: {resources.cpu_count}",
            f"  Threads: {resources.cpu_threads}",
            f"  Usage: {resources.cpu_percent:.1f}%",
            "",
            "Memory (RAM):",
            f"  Total: {resources.ram_total_mb:,} MB",
            f"  Available: {resources.ram_available_mb:,} MB",
            f"  Used: {resources.ram_used_mb:,} MB ({resources.ram_percent:.1f}%)",
            f"  Swap: {resources.swap_used_mb:,} / {resources.swap_total_mb:,} MB",
            "",
        ]

        if resources.has_gpu:
            lines.extend(
                [
                    f"GPU ({resources.gpu_count} device(s)):",
                    f"  Total Memory: {resources.total_gpu_memory_mb:,} MB",
                    f"  Free Memory: {resources.total_gpu_free_mb:,} MB",
                    "",
                ]
            )

            for gpu in resources.gpus:
                lines.extend(
                    [
                        f"  [{gpu.index}] {gpu.name} ({gpu.vendor.value})",
                        f"      Memory: {gpu.free_memory_mb:,} / {gpu.total_memory_mb:,} MB",
                        f"      Utilization: {gpu.utilization_percent:.1f}%",
                        f"      Temperature: {gpu.temperature_c:.0f}°C",
                    ]
                )
        else:
            lines.append("GPU: Not detected")

        lines.extend(
            [
                "",
                "Disk:",
                f"  Total: {resources.disk_total_gb:.1f} GB",
                f"  Free: {resources.disk_free_gb:.1f} GB",
                f"  Used: {resources.disk_used_gb:.1f} GB",
                "",
                "=" * 50,
            ]
        )

        return "\n".join(lines)


# ============================================================================
# Convenience Functions
# ============================================================================


def get_resource_manager(mode: ResourceMode = ResourceMode.MAXIMUM) -> ResourceManager:
    """
    الحصول على مدير الموارد.

    Get a resource manager with the specified mode.
    """
    config = FullResourceConfig(mode=mode)

    if mode == ResourceMode.MAXIMUM:
        config = FullResourceConfig.maximum_performance()
    elif mode == ResourceMode.CONSERVATIVE:
        config.cpu.max_cores = (os.cpu_count() or 1) // 2
        config.gpu.memory_fraction = 0.5
        config.memory.memory_fraction = 0.5

    return ResourceManager(config)


def optimize_system_for_ai() -> Dict[str, Any]:
    """
    تحسين النظام للذكاء الاصطناعي.

    Quick function to optimize the system for AI workloads.
    """
    manager = get_resource_manager(ResourceMode.MAXIMUM)
    return manager.optimize_for_ai()


def print_resources() -> None:
    """
    طباعة ملخص الموارد.

    Print a summary of system resources.
    """
    manager = get_resource_manager()
    print(manager.get_resource_summary())


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Enums
    "GPUVendor",
    "ResourceMode",
    # Configs
    "CPUConfig",
    "GPUConfig",
    "MemoryConfig",
    "DiskConfig",
    "NetworkConfig",
    "FullResourceConfig",
    # Data Classes
    "GPUDevice",
    "SystemResources",
    # Manager
    "ResourceManager",
    # Functions
    "get_resource_manager",
    "optimize_system_for_ai",
    "print_resources",
]
