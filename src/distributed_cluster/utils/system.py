"""
System Utilities - أدوات النظام
================================

System information and monitoring utilities.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import os
import platform
import socket
from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class MemoryInfo:
    """معلومات الذاكرة"""

    total_mb: int
    available_mb: int
    used_mb: int
    percent: float

    @property
    def free_mb(self) -> int:
        return self.available_mb


@dataclass
class DiskUsage:
    """معلومات استخدام القرص"""

    path: str
    total_mb: int
    used_mb: int
    free_mb: int
    percent: float


@dataclass
class NetworkInterface:
    """معلومات واجهة الشبكة"""

    name: str
    ip_address: Optional[str]
    mac_address: Optional[str]
    is_up: bool
    speed_mbps: Optional[int]


@dataclass
class ProcessInfo:
    """معلومات العملية"""

    pid: int
    name: str
    status: str
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    threads: int
    create_time: float


# =============================================================================
# CPU Functions
# =============================================================================


def get_cpu_count(logical: bool = True) -> int:
    """
    الحصول على عدد المعالجات
    Get CPU count

    Args:
        logical: Include logical cores (hyperthreading)

    Returns:
        CPU count
    """
    if PSUTIL_AVAILABLE:
        return psutil.cpu_count(logical=logical) or 1

    # Fallback
    return os.cpu_count() or 1


def get_cpu_percent(interval: float = 0.1) -> float:
    """
    الحصول على نسبة استخدام المعالج
    Get CPU usage percent

    Args:
        interval: Measurement interval

    Returns:
        CPU percent (0-100)
    """
    if PSUTIL_AVAILABLE:
        return psutil.cpu_percent(interval=interval)
    return 0.0


def get_cpu_freq() -> Optional[Dict[str, float]]:
    """
    الحصول على تردد المعالج
    Get CPU frequency

    Returns:
        Dict with current, min, max frequencies in MHz
    """
    if PSUTIL_AVAILABLE:
        freq = psutil.cpu_freq()
        if freq:
            return {
                "current": freq.current,
                "min": freq.min,
                "max": freq.max,
            }
    return None


# =============================================================================
# Memory Functions
# =============================================================================


def get_memory_info() -> MemoryInfo:
    """
    الحصول على معلومات الذاكرة
    Get memory information

    Returns:
        MemoryInfo object
    """
    if PSUTIL_AVAILABLE:
        mem = psutil.virtual_memory()
        return MemoryInfo(
            total_mb=mem.total // (1024 * 1024),
            available_mb=mem.available // (1024 * 1024),
            used_mb=mem.used // (1024 * 1024),
            percent=mem.percent,
        )

    # Fallback - try to read from /proc/meminfo on Linux
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    value = int(parts[1])
                    meminfo[key] = value

            total = meminfo.get("MemTotal", 0) // 1024
            available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0)) // 1024
            used = total - available
            percent = (used / total * 100) if total > 0 else 0

            return MemoryInfo(
                total_mb=total,
                available_mb=available,
                used_mb=used,
                percent=percent,
            )
    except Exception:
        return MemoryInfo(
            total_mb=0,
            available_mb=0,
            used_mb=0,
            percent=0.0,
        )


# =============================================================================
# Disk Functions
# =============================================================================


def get_disk_usage(path: str = "/") -> DiskUsage:
    """
    الحصول على استخدام القرص
    Get disk usage

    Args:
        path: Path to check

    Returns:
        DiskUsage object
    """
    if PSUTIL_AVAILABLE:
        usage = psutil.disk_usage(path)
        return DiskUsage(
            path=path,
            total_mb=usage.total // (1024 * 1024),
            used_mb=usage.used // (1024 * 1024),
            free_mb=usage.free // (1024 * 1024),
            percent=usage.percent,
        )

    # Fallback using os.statvfs
    try:
        stat = os.statvfs(path)
        total = (stat.f_blocks * stat.f_frsize) // (1024 * 1024)
        free = (stat.f_bavail * stat.f_frsize) // (1024 * 1024)
        used = total - free
        percent = (used / total * 100) if total > 0 else 0

        return DiskUsage(
            path=path,
            total_mb=total,
            used_mb=used,
            free_mb=free,
            percent=percent,
        )
    except Exception:
        return DiskUsage(
            path=path,
            total_mb=0,
            used_mb=0,
            free_mb=0,
            percent=0.0,
        )


# =============================================================================
# Network Functions
# =============================================================================


def get_network_interfaces() -> List[NetworkInterface]:
    """
    الحصول على واجهات الشبكة
    Get network interfaces

    Returns:
        List of NetworkInterface objects
    """
    interfaces = []

    if PSUTIL_AVAILABLE:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        for name, addresses in addrs.items():
            ip_address = None
            mac_address = None

            for addr in addresses:
                if addr.family == socket.AF_INET:
                    ip_address = addr.address
                elif addr.family == psutil.AF_LINK:
                    mac_address = addr.address

            stat = stats.get(name)
            is_up = stat.isup if stat else False
            speed = stat.speed if stat else None

            interfaces.append(
                NetworkInterface(
                    name=name,
                    ip_address=ip_address,
                    mac_address=mac_address,
                    is_up=is_up,
                    speed_mbps=speed,
                )
            )

    return interfaces


def get_hostname() -> str:
    """
    الحصول على اسم المضيف
    Get hostname

    Returns:
        Hostname
    """
    return socket.gethostname()


def get_local_ip() -> Optional[str]:
    """
    الحصول على عنوان IP المحلي
    Get local IP address

    Returns:
        Local IP or None
    """
    try:
        # Create a socket to determine the outgoing IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


# =============================================================================
# Process Functions
# =============================================================================


def get_process_info(pid: Optional[int] = None) -> Optional[ProcessInfo]:
    """
    الحصول على معلومات العملية
    Get process information

    Args:
        pid: Process ID (current process if None)

    Returns:
        ProcessInfo or None
    """
    if not PSUTIL_AVAILABLE:
        return None

    try:
        if pid is None:
            pid = os.getpid()

        proc = psutil.Process(pid)

        with proc.oneshot():
            return ProcessInfo(
                pid=proc.pid,
                name=proc.name(),
                status=proc.status(),
                cpu_percent=proc.cpu_percent(),
                memory_percent=proc.memory_percent(),
                memory_mb=proc.memory_info().rss / (1024 * 1024),
                threads=proc.num_threads(),
                create_time=proc.create_time(),
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


# =============================================================================
# Port Functions
# =============================================================================


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """
    التحقق من توفر المنفذ
    Check if port is available

    Args:
        port: Port number
        host: Host to check

    Returns:
        True if port is available
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind((host, port))
            return True
    except (OSError, socket.error):
        return False


def find_available_port(
    start_port: int = 8000,
    end_port: int = 9000,
    host: str = "127.0.0.1",
) -> Optional[int]:
    """
    البحث عن منفذ متاح
    Find an available port

    Args:
        start_port: Start of port range
        end_port: End of port range
        host: Host to check

    Returns:
        Available port or None
    """
    for port in range(start_port, end_port + 1):
        if is_port_available(port, host):
            return port
    return None


# =============================================================================
# System Information
# =============================================================================


def get_system_info() -> Dict[str, str]:
    """
    الحصول على معلومات النظام
    Get system information

    Returns:
        Dictionary with system info
    """
    return {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "hostname": socket.gethostname(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
    }


def get_load_average() -> Optional[tuple]:
    """
    الحصول على متوسط الحمل
    Get system load average

    Returns:
        Tuple of 1, 5, 15 minute averages or None
    """
    try:
        return os.getloadavg()
    except (AttributeError, OSError):
        return None
