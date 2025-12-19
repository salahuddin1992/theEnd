"""
Resource Detector - كاشف الموارد
===================================

يكتشف موارد الجهاز تلقائياً:
- CPU cores
- RAM
- GPUs (NVIDIA via pynvml/nvidia-ml-py)
- Disk space
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import sys
import warnings
from typing import Optional

import psutil

# Windows compatibility
IS_WINDOWS = sys.platform == "win32"

# Suppress pynvml deprecation warning (use nvidia-ml-py instead)
warnings.filterwarnings("ignore", category=FutureWarning, module="pynvml")

from distributed_cluster.models.resources import GPUInfo, ResourceSpec, ResourceUsage

logger = logging.getLogger(__name__)


class ResourceDetector:
    """
    كاشف موارد الجهاز.

    يستخدمه Worker لمعرفة الموارد المتاحة وإرسالها للـ Master.
    """

    def __init__(
        self,
        cpu_override: Optional[float] = None,
        memory_override: Optional[int] = None,
        gpu_indices: Optional[list[int]] = None,
    ):
        """
        Initialize the resource detector.

        Args:
            cpu_override: Override detected CPU cores
            memory_override: Override detected memory (MB)
            gpu_indices: Specific GPU indices to use (None = all)
        """
        self.cpu_override = cpu_override
        self.memory_override = memory_override
        self.gpu_indices = gpu_indices

        # Try to initialize NVIDIA ML
        self._nvml_initialized = False
        self._init_nvml()

    def _init_nvml(self) -> None:
        """Initialize NVIDIA Management Library."""
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_initialized = True
            logger.info("NVIDIA ML initialized successfully")
        except ImportError:
            logger.debug("pynvml not installed, GPU detection disabled")
        except Exception as e:
            logger.debug(f"Failed to initialize NVIDIA ML: {e}")

    def _shutdown_nvml(self) -> None:
        """Shutdown NVIDIA ML."""
        if self._nvml_initialized:
            try:
                import pynvml
                pynvml.nvmlShutdown()
            except Exception:
                pass

    def get_hostname(self) -> str:
        """الحصول على اسم الجهاز."""
        return socket.gethostname()

    def get_ip_address(self) -> str:
        """الحصول على عنوان IP."""
        try:
            # محاولة الحصول على IP الخارجي
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_platform(self) -> str:
        """الحصول على نوع النظام."""
        return platform.system().lower()

    def get_python_version(self) -> str:
        """الحصول على إصدار Python."""
        return platform.python_version()

    def get_cpu_count(self) -> int:
        """عدد أنوية CPU."""
        if self.cpu_override is not None:
            return int(self.cpu_override)
        return psutil.cpu_count(logical=True) or 1

    def get_memory_total_mb(self) -> int:
        """إجمالي الذاكرة بالميغابايت."""
        if self.memory_override is not None:
            return self.memory_override
        return int(psutil.virtual_memory().total / (1024 * 1024))

    def get_gpu_info(self) -> list[GPUInfo]:
        """معلومات GPUs المتاحة."""
        if not self._nvml_initialized:
            return []

        try:
            import pynvml

            gpus = []
            device_count = pynvml.nvmlDeviceGetCount()

            for i in range(device_count):
                # تخطي إذا لم يكن في القائمة المحددة
                if self.gpu_indices is not None and i not in self.gpu_indices:
                    continue

                try:
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    name = pynvml.nvmlDeviceGetName(handle)
                    if isinstance(name, bytes):
                        name = name.decode("utf-8")

                    uuid = pynvml.nvmlDeviceGetUUID(handle)
                    if isinstance(uuid, bytes):
                        uuid = uuid.decode("utf-8")

                    memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)

                    # Temperature (optional)
                    try:
                        temp = pynvml.nvmlDeviceGetTemperature(
                            handle, pynvml.NVML_TEMPERATURE_GPU
                        )
                    except Exception:
                        temp = None

                    # Power (optional)
                    try:
                        power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
                    except Exception:
                        power = None

                    gpus.append(
                        GPUInfo(
                            index=i,
                            name=name,
                            uuid=uuid,
                            memory_total_mb=int(memory.total / (1024 * 1024)),
                            memory_free_mb=int(memory.free / (1024 * 1024)),
                            memory_used_mb=int(memory.used / (1024 * 1024)),
                            utilization_percent=float(utilization.gpu),
                            temperature_c=temp,
                            power_draw_w=power,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to get info for GPU {i}: {e}")

            return gpus
        except Exception as e:
            logger.warning(f"Failed to enumerate GPUs: {e}")
            return []

    def get_gpu_driver_version(self) -> Optional[str]:
        """إصدار driver الـ GPU."""
        if not self._nvml_initialized:
            return None

        try:
            import pynvml
            version = pynvml.nvmlSystemGetDriverVersion()
            if isinstance(version, bytes):
                version = version.decode("utf-8")
            return version
        except Exception:
            return None

    def get_total_resources(self) -> ResourceSpec:
        """
        الموارد الإجمالية المتاحة للتخصيص.

        هذا ما يُرسل للـ Master عند التسجيل.
        """
        gpus = self.get_gpu_info()

        return ResourceSpec(
            cpu_cores=float(self.get_cpu_count()),
            memory_mb=self.get_memory_total_mb(),
            gpu_count=len(gpus),
            gpu_memory_mb=min(g.memory_total_mb for g in gpus) if gpus else 0,
        )

    def _get_disk_path(self) -> str:
        """Get the appropriate disk path based on the platform."""
        if IS_WINDOWS:
            # Use the system drive (usually C:)
            return os.environ.get("SystemDrive", "C:") + "\\"
        return "/"

    def get_current_usage(self) -> ResourceUsage:
        """
        الاستخدام الحالي للموارد.

        يُرسل مع كل heartbeat.
        """
        memory = psutil.virtual_memory()

        # Get disk usage with platform-aware path
        try:
            disk = psutil.disk_usage(self._get_disk_path())
            disk_used_gb = disk.used / (1024 ** 3)
            disk_total_gb = disk.total / (1024 ** 3)
        except Exception:
            disk_used_gb = 0.0
            disk_total_gb = 0.0

        # Network I/O
        net_io = psutil.net_io_counters()

        return ResourceUsage(
            cpu_percent=psutil.cpu_percent(interval=0.1),
            memory_used_mb=int(memory.used / (1024 * 1024)),
            memory_total_mb=int(memory.total / (1024 * 1024)),
            memory_percent=memory.percent,
            gpus=self.get_gpu_info(),
            load_average=psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0.0, 0.0, 0.0),
            disk_used_gb=disk_used_gb,
            disk_total_gb=disk_total_gb,
            network_recv_mb=net_io.bytes_recv / (1024 * 1024),
            network_sent_mb=net_io.bytes_sent / (1024 * 1024),
        )

    def check_docker_available(self) -> bool:
        """التحقق من توفر Docker."""
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return True
        except Exception:
            return False

    def get_system_info(self) -> dict:
        """معلومات النظام الكاملة."""
        return {
            "hostname": self.get_hostname(),
            "ip_address": self.get_ip_address(),
            "platform": self.get_platform(),
            "python_version": self.get_python_version(),
            "cpu_count": self.get_cpu_count(),
            "memory_total_mb": self.get_memory_total_mb(),
            "gpu_count": len(self.get_gpu_info()),
            "gpu_driver_version": self.get_gpu_driver_version(),
            "docker_available": self.check_docker_available(),
        }

    def __del__(self):
        """Cleanup."""
        self._shutdown_nvml()
