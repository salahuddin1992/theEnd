"""
NVML Wrapper - Compatibility layer for nvidia-ml-py
غلاف NVML - طبقة توافق لـ nvidia-ml-py

This module provides a compatibility wrapper that suppresses the
deprecation warning from pynvml and provides a unified import.

يوفر هذا الملف غلاف توافق يكتم تحذير الإهمال من pynvml
ويوفر استيراد موحد.
"""

import warnings

# Suppress the FutureWarning from pynvml
warnings.filterwarnings("ignore", category=FutureWarning, module="pynvml")

try:
    # Try nvidia-ml-py first (the new package name)
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False
    pynvml = None  # type: ignore[assignment]

# Re-export everything from pynvml
if NVML_AVAILABLE:
    from pynvml import (
        nvmlInit,
        nvmlShutdown,
        nvmlDeviceGetCount,
        nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetName,
        nvmlDeviceGetUUID,
        nvmlDeviceGetMemoryInfo,
        nvmlDeviceGetUtilizationRates,
        nvmlDeviceGetTemperature,
        nvmlDeviceGetPowerUsage,
        nvmlDeviceGetComputeRunningProcesses,
        NVML_TEMPERATURE_GPU,
    )

__all__ = [
    "NVML_AVAILABLE",
    "pynvml",
    "nvmlInit",
    "nvmlShutdown",
    "nvmlDeviceGetCount",
    "nvmlDeviceGetHandleByIndex",
    "nvmlDeviceGetName",
    "nvmlDeviceGetUUID",
    "nvmlDeviceGetMemoryInfo",
    "nvmlDeviceGetUtilizationRates",
    "nvmlDeviceGetTemperature",
    "nvmlDeviceGetPowerUsage",
    "nvmlDeviceGetComputeRunningProcesses",
    "NVML_TEMPERATURE_GPU",
]
