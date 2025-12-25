"""
Comprehensive Health Checks - فحوصات الصحة الشاملة
===================================================

نظام فحوصات صحة شامل يشمل:
- Network Health Checks
- Service Dependency Checks
- Database Health Checks
- External API Health Checks
- Cascading Health Checks
- gRPC Health Protocol
"""

from __future__ import annotations

import asyncio
import socket
import ssl
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# =============================================================================
# Health Status
# =============================================================================


class HealthStatus(str, Enum):
    """حالة الصحة."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class DependencyType(str, Enum):
    """نوع التبعية."""

    REQUIRED = "required"  # مطلوب للعمل
    OPTIONAL = "optional"  # اختياري
    SOFT = "soft"  # لا يؤثر على الحالة العامة


@dataclass
class HealthCheckResult:
    """نتيجة فحص الصحة."""

    name: str
    status: HealthStatus
    message: str = ""
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    children: List["HealthCheckResult"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        d = {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp.isoformat(),
        }

        if self.metadata:
            d["metadata"] = self.metadata

        if self.children:
            d["children"] = [c.to_dict() for c in self.children]

        return d


@dataclass
class DependencyConfig:
    """إعدادات التبعية."""

    name: str
    dependency_type: DependencyType = DependencyType.REQUIRED
    timeout_seconds: float = 5.0
    retry_count: int = 1
    retry_delay_seconds: float = 0.5
    description: str = ""


# =============================================================================
# Health Check Interface
# =============================================================================


class HealthCheck(ABC):
    """واجهة فحص الصحة."""

    def __init__(self, name: str, config: Optional[DependencyConfig] = None):
        self.name = name
        self.config = config or DependencyConfig(name=name)

    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص."""
        pass


# =============================================================================
# Network Health Checks
# =============================================================================


class TCPHealthCheck(HealthCheck):
    """
    فحص صحة TCP.

    يتحقق من إمكانية الاتصال بمنفذ TCP.
    """

    def __init__(
        self,
        name: str,
        host: str,
        port: int,
        timeout: float = 5.0,
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.host = host
        self.port = port
        self.timeout = timeout

    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص."""
        start = time.time()

        try:
            # Create connection with timeout
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
            writer.close()
            await writer.wait_closed()

            duration = (time.time() - start) * 1000

            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message=f"TCP connection to {self.host}:{self.port} successful",
                duration_ms=duration,
                metadata={"host": self.host, "port": self.port},
            )

        except asyncio.TimeoutError:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Connection to {self.host}:{self.port} timed out",
                duration_ms=duration,
                metadata={"host": self.host, "port": self.port},
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Connection failed: {str(e)}",
                duration_ms=duration,
                metadata={"host": self.host, "port": self.port, "error": str(e)},
            )


class HTTPHealthCheck(HealthCheck):
    """
    فحص صحة HTTP.

    يتحقق من endpoint HTTP.
    """

    def __init__(
        self,
        name: str,
        url: str,
        method: str = "GET",
        expected_status: int = 200,
        timeout: float = 10.0,
        headers: Optional[Dict[str, str]] = None,
        verify_ssl: bool = True,
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.url = url
        self.method = method
        self.expected_status = expected_status
        self.timeout = timeout
        self.headers = headers or {}
        self.verify_ssl = verify_ssl

    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص."""
        start = time.time()

        try:
            import httpx

            async with httpx.AsyncClient(verify=self.verify_ssl) as client:
                response = await client.request(
                    method=self.method,
                    url=self.url,
                    headers=self.headers,
                    timeout=self.timeout,
                )

                duration = (time.time() - start) * 1000

                if response.status_code == self.expected_status:
                    return HealthCheckResult(
                        name=self.name,
                        status=HealthStatus.HEALTHY,
                        message=f"HTTP {self.method} {self.url} returned {response.status_code}",
                        duration_ms=duration,
                        metadata={
                            "url": self.url,
                            "status_code": response.status_code,
                            "method": self.method,
                        },
                    )
                else:
                    return HealthCheckResult(
                        name=self.name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Unexpected status code: {response.status_code} (expected {self.expected_status})",
                        duration_ms=duration,
                        metadata={
                            "url": self.url,
                            "status_code": response.status_code,
                            "expected_status": self.expected_status,
                        },
                    )

        except ImportError:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNKNOWN,
                message="httpx not available",
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"HTTP request failed: {str(e)}",
                duration_ms=duration,
                metadata={"url": self.url, "error": str(e)},
            )


class DNSHealthCheck(HealthCheck):
    """
    فحص صحة DNS.

    يتحقق من إمكانية حل اسم النطاق.
    """

    def __init__(
        self,
        name: str,
        hostname: str,
        timeout: float = 5.0,
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.hostname = hostname
        self.timeout = timeout

    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص."""
        start = time.time()

        try:
            loop = asyncio.get_running_loop()

            # Resolve hostname
            result = await asyncio.wait_for(
                loop.getaddrinfo(self.hostname, None),
                timeout=self.timeout,
            )

            duration = (time.time() - start) * 1000
            addresses = [r[4][0] for r in result]

            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message=f"DNS resolution successful for {self.hostname}",
                duration_ms=duration,
                metadata={
                    "hostname": self.hostname,
                    "addresses": addresses[:5],  # Limit to 5
                },
            )

        except asyncio.TimeoutError:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"DNS resolution timed out for {self.hostname}",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"DNS resolution failed: {str(e)}",
                duration_ms=duration,
                metadata={"error": str(e)},
            )


class SSLCertificateCheck(HealthCheck):
    """
    فحص شهادة SSL.

    يتحقق من صلاحية الشهادة وتاريخ انتهائها.
    """

    def __init__(
        self,
        name: str,
        hostname: str,
        port: int = 443,
        warning_days: int = 30,
        timeout: float = 10.0,
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.hostname = hostname
        self.port = port
        self.warning_days = warning_days
        self.timeout = timeout

    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص."""
        start = time.time()

        try:
            loop = asyncio.get_running_loop()

            def get_cert():
                context = ssl.create_default_context()
                with socket.create_connection((self.hostname, self.port), timeout=self.timeout) as sock:
                    with context.wrap_socket(sock, server_hostname=self.hostname) as ssock:
                        return ssock.getpeercert()

            cert = await loop.run_in_executor(None, get_cert)
            duration = (time.time() - start) * 1000

            # Parse expiry date
            not_after = cert.get("notAfter", "")
            # Format: 'Dec 31 23:59:59 2024 GMT'
            from datetime import datetime as dt
            expiry = dt.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
            days_until_expiry = (expiry - dt.utcnow()).days

            if days_until_expiry < 0:
                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"SSL certificate expired {abs(days_until_expiry)} days ago",
                    duration_ms=duration,
                    metadata={
                        "hostname": self.hostname,
                        "expiry": expiry.isoformat(),
                        "days_until_expiry": days_until_expiry,
                    },
                )

            if days_until_expiry < self.warning_days:
                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.DEGRADED,
                    message=f"SSL certificate expires in {days_until_expiry} days",
                    duration_ms=duration,
                    metadata={
                        "hostname": self.hostname,
                        "expiry": expiry.isoformat(),
                        "days_until_expiry": days_until_expiry,
                    },
                )

            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message=f"SSL certificate valid for {days_until_expiry} days",
                duration_ms=duration,
                metadata={
                    "hostname": self.hostname,
                    "expiry": expiry.isoformat(),
                    "days_until_expiry": days_until_expiry,
                    "subject": dict(x[0] for x in cert.get("subject", [])),
                },
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"SSL check failed: {str(e)}",
                duration_ms=duration,
                metadata={"error": str(e)},
            )


# =============================================================================
# Database Health Checks
# =============================================================================


class PostgreSQLHealthCheck(HealthCheck):
    """
    فحص صحة PostgreSQL.
    """

    def __init__(
        self,
        name: str,
        connection_string: str,
        timeout: float = 5.0,
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.connection_string = connection_string
        self.timeout = timeout

    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص."""
        start = time.time()

        try:
            import asyncpg

            conn = await asyncio.wait_for(
                asyncpg.connect(self.connection_string),
                timeout=self.timeout,
            )

            try:
                # Execute a simple query
                version = await conn.fetchval("SELECT version()")
                duration = (time.time() - start) * 1000

                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.HEALTHY,
                    message="PostgreSQL connection successful",
                    duration_ms=duration,
                    metadata={"version": version[:50] if version else "unknown"},
                )
            finally:
                await conn.close()

        except ImportError:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNKNOWN,
                message="asyncpg not available",
            )

        except asyncio.TimeoutError:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message="PostgreSQL connection timed out",
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"PostgreSQL error: {str(e)}",
                duration_ms=duration,
                metadata={"error": str(e)},
            )


class RedisHealthCheck(HealthCheck):
    """
    فحص صحة Redis.
    """

    def __init__(
        self,
        name: str,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        timeout: float = 5.0,
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout

    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص."""
        start = time.time()

        try:
            import redis.asyncio as redis

            client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                socket_timeout=self.timeout,
            )

            try:
                info = await asyncio.wait_for(
                    client.info("server"),
                    timeout=self.timeout,
                )
                duration = (time.time() - start) * 1000

                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.HEALTHY,
                    message="Redis connection successful",
                    duration_ms=duration,
                    metadata={
                        "version": info.get("redis_version", "unknown"),
                        "connected_clients": info.get("connected_clients", 0),
                    },
                )
            finally:
                await client.close()

        except ImportError:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNKNOWN,
                message="redis not available",
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Redis error: {str(e)}",
                duration_ms=duration,
                metadata={"error": str(e)},
            )


# =============================================================================
# Resource Health Checks
# =============================================================================


class CPUHealthCheck(HealthCheck):
    """
    فحص صحة CPU.
    """

    def __init__(
        self,
        name: str = "cpu",
        warning_threshold: float = 80.0,
        critical_threshold: float = 95.0,
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص."""
        start = time.time()

        try:
            import psutil

            # Get CPU percent over a short interval
            loop = asyncio.get_running_loop()
            cpu_percent = await loop.run_in_executor(
                None, lambda: psutil.cpu_percent(interval=0.5)
            )

            duration = (time.time() - start) * 1000
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0, 0, 0)

            if cpu_percent >= self.critical_threshold:
                status = HealthStatus.UNHEALTHY
                message = f"Critical CPU usage: {cpu_percent:.1f}%"
            elif cpu_percent >= self.warning_threshold:
                status = HealthStatus.DEGRADED
                message = f"High CPU usage: {cpu_percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"CPU usage: {cpu_percent:.1f}%"

            return HealthCheckResult(
                name=self.name,
                status=status,
                message=message,
                duration_ms=duration,
                metadata={
                    "cpu_percent": cpu_percent,
                    "cpu_count": cpu_count,
                    "load_avg_1m": load_avg[0],
                    "load_avg_5m": load_avg[1],
                    "load_avg_15m": load_avg[2],
                },
            )

        except ImportError:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNKNOWN,
                message="psutil not available",
            )

        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNKNOWN,
                message=f"CPU check failed: {str(e)}",
            )


class MemoryHealthCheck(HealthCheck):
    """
    فحص صحة الذاكرة.
    """

    def __init__(
        self,
        name: str = "memory",
        warning_threshold: float = 80.0,
        critical_threshold: float = 95.0,
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص."""
        start = time.time()

        try:
            import psutil

            memory = psutil.virtual_memory()
            duration = (time.time() - start) * 1000

            if memory.percent >= self.critical_threshold:
                status = HealthStatus.UNHEALTHY
                message = f"Critical memory usage: {memory.percent:.1f}%"
            elif memory.percent >= self.warning_threshold:
                status = HealthStatus.DEGRADED
                message = f"High memory usage: {memory.percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage: {memory.percent:.1f}%"

            return HealthCheckResult(
                name=self.name,
                status=status,
                message=message,
                duration_ms=duration,
                metadata={
                    "percent": memory.percent,
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "used_gb": round(memory.used / (1024**3), 2),
                },
            )

        except ImportError:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNKNOWN,
                message="psutil not available",
            )

        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNKNOWN,
                message=f"Memory check failed: {str(e)}",
            )


class DiskHealthCheck(HealthCheck):
    """
    فحص صحة القرص.
    """

    def __init__(
        self,
        name: str = "disk",
        path: str = "/",
        warning_threshold: float = 80.0,
        critical_threshold: float = 95.0,
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.path = path
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص."""
        start = time.time()

        try:
            import psutil

            disk = psutil.disk_usage(self.path)
            duration = (time.time() - start) * 1000

            if disk.percent >= self.critical_threshold:
                status = HealthStatus.UNHEALTHY
                message = f"Critical disk usage: {disk.percent:.1f}%"
            elif disk.percent >= self.warning_threshold:
                status = HealthStatus.DEGRADED
                message = f"High disk usage: {disk.percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk usage: {disk.percent:.1f}%"

            return HealthCheckResult(
                name=self.name,
                status=status,
                message=message,
                duration_ms=duration,
                metadata={
                    "path": self.path,
                    "percent": disk.percent,
                    "total_gb": round(disk.total / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                },
            )

        except ImportError:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNKNOWN,
                message="psutil not available",
            )

        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNKNOWN,
                message=f"Disk check failed: {str(e)}",
            )


# =============================================================================
# Composite Health Checks
# =============================================================================


class CompositeHealthCheck(HealthCheck):
    """
    فحص صحة مركب.

    يجمع عدة فحوصات ويحدد الحالة الإجمالية.
    """

    def __init__(
        self,
        name: str,
        checks: List[HealthCheck],
        aggregation: str = "worst",  # "worst" or "majority"
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.checks = checks
        self.aggregation = aggregation

    async def check(self) -> HealthCheckResult:
        """تنفيذ كل الفحوصات."""
        start = time.time()

        # Run all checks concurrently
        results = await asyncio.gather(
            *[c.check() for c in self.checks],
            return_exceptions=True,
        )

        children = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                children.append(
                    HealthCheckResult(
                        name=self.checks[i].name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Check failed: {str(result)}",
                    )
                )
            else:
                children.append(result)

        duration = (time.time() - start) * 1000

        # Determine overall status
        if self.aggregation == "worst":
            overall_status = self._worst_status(children)
        else:
            overall_status = self._majority_status(children)

        healthy_count = sum(1 for c in children if c.status == HealthStatus.HEALTHY)
        total_count = len(children)

        return HealthCheckResult(
            name=self.name,
            status=overall_status,
            message=f"{healthy_count}/{total_count} checks healthy",
            duration_ms=duration,
            children=children,
            metadata={
                "healthy": healthy_count,
                "total": total_count,
                "aggregation": self.aggregation,
            },
        )

    def _worst_status(self, results: List[HealthCheckResult]) -> HealthStatus:
        """أسوأ حالة."""
        statuses = [r.status for r in results]

        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        if HealthStatus.UNKNOWN in statuses:
            return HealthStatus.UNKNOWN
        return HealthStatus.HEALTHY

    def _majority_status(self, results: List[HealthCheckResult]) -> HealthStatus:
        """حالة الأغلبية."""
        statuses = [r.status for r in results]
        healthy_count = statuses.count(HealthStatus.HEALTHY)

        if healthy_count > len(statuses) / 2:
            return HealthStatus.HEALTHY
        elif statuses.count(HealthStatus.UNHEALTHY) > len(statuses) / 2:
            return HealthStatus.UNHEALTHY
        else:
            return HealthStatus.DEGRADED


class DependencyChainCheck(HealthCheck):
    """
    فحص سلسلة التبعيات.

    يفحص سلسلة من الخدمات التي تعتمد على بعضها.
    """

    def __init__(
        self,
        name: str,
        checks: List[Tuple[HealthCheck, DependencyType]],
        config: Optional[DependencyConfig] = None,
    ):
        super().__init__(name, config)
        self.checks = checks

    async def check(self) -> HealthCheckResult:
        """تنفيذ الفحص بالترتيب."""
        start = time.time()
        children = []
        failed_required = False

        for health_check, dep_type in self.checks:
            # If a required dependency failed, skip subsequent checks
            if failed_required:
                children.append(
                    HealthCheckResult(
                        name=health_check.name,
                        status=HealthStatus.UNKNOWN,
                        message="Skipped due to failed dependency",
                    )
                )
                continue

            result = await health_check.check()
            children.append(result)

            if result.status == HealthStatus.UNHEALTHY:
                if dep_type == DependencyType.REQUIRED:
                    failed_required = True

        duration = (time.time() - start) * 1000

        # Determine overall status
        if failed_required:
            overall_status = HealthStatus.UNHEALTHY
            message = "Required dependency failed"
        else:
            unhealthy = sum(1 for c in children if c.status == HealthStatus.UNHEALTHY)
            degraded = sum(1 for c in children if c.status == HealthStatus.DEGRADED)

            if unhealthy > 0:
                overall_status = HealthStatus.DEGRADED
                message = f"{unhealthy} optional dependencies unhealthy"
            elif degraded > 0:
                overall_status = HealthStatus.DEGRADED
                message = f"{degraded} dependencies degraded"
            else:
                overall_status = HealthStatus.HEALTHY
                message = "All dependencies healthy"

        return HealthCheckResult(
            name=self.name,
            status=overall_status,
            message=message,
            duration_ms=duration,
            children=children,
        )


# =============================================================================
# Health Check Manager
# =============================================================================


class HealthCheckManager:
    """
    مدير فحوصات الصحة.

    يدير تسجيل وتنفيذ فحوصات الصحة.
    """

    def __init__(
        self,
        service_name: str = "distributed_cluster",
        version: str = "0.1.0",
    ):
        self.service_name = service_name
        self.version = version

        self._checks: Dict[str, HealthCheck] = {}
        self._results: Dict[str, HealthCheckResult] = {}
        self._start_time = datetime.utcnow()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register(self, check: HealthCheck) -> None:
        """تسجيل فحص."""
        self._checks[check.name] = check

    def unregister(self, name: str) -> None:
        """إلغاء تسجيل فحص."""
        self._checks.pop(name, None)
        self._results.pop(name, None)

    async def check(self, name: str) -> HealthCheckResult:
        """تنفيذ فحص واحد."""
        if name not in self._checks:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=f"Check '{name}' not found",
            )

        result = await self._checks[name].check()
        self._results[name] = result
        return result

    async def check_all(self) -> Dict[str, HealthCheckResult]:
        """تنفيذ كل الفحوصات."""
        tasks = {name: self.check(name) for name in self._checks}
        results = await asyncio.gather(*tasks.values())

        return dict(zip(tasks.keys(), results))

    def get_overall_status(self) -> HealthStatus:
        """الحصول على الحالة الإجمالية."""
        if not self._results:
            return HealthStatus.UNKNOWN

        statuses = [r.status for r in self._results.values()]

        # Consider dependency types
        for name, result in self._results.items():
            if name in self._checks:
                dep_type = self._checks[name].config.dependency_type
                if dep_type == DependencyType.SOFT:
                    # Remove soft dependencies from consideration
                    statuses.remove(result.status)

        if not statuses:
            return HealthStatus.HEALTHY

        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        if HealthStatus.UNKNOWN in statuses:
            return HealthStatus.UNKNOWN

        return HealthStatus.HEALTHY

    def get_health_report(self) -> Dict[str, Any]:
        """الحصول على تقرير الصحة الكامل."""
        uptime = (datetime.utcnow() - self._start_time).total_seconds()

        return {
            "status": self.get_overall_status().value,
            "service": self.service_name,
            "version": self.version,
            "uptime_seconds": uptime,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {name: result.to_dict() for name, result in self._results.items()},
        }

    async def start_background_checks(self, interval: float = 30.0) -> None:
        """بدء الفحص الدوري في الخلفية."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._check_loop(interval))

    async def stop_background_checks(self) -> None:
        """إيقاف الفحص الدوري."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _check_loop(self, interval: float) -> None:
        """حلقة الفحص الدوري."""
        while self._running:
            try:
                await self.check_all()
            except Exception:
                pass

            await asyncio.sleep(interval)


# =============================================================================
# Readiness & Liveness Probes
# =============================================================================


class ReadinessProbe:
    """
    فحص الجاهزية (Kubernetes Readiness).

    يحدد ما إذا كان التطبيق جاهزاً لاستقبال الطلبات.
    """

    def __init__(self, manager: HealthCheckManager):
        self.manager = manager
        self._custom_checks: List[Callable[[], bool]] = []

    def add_check(self, check: Callable[[], bool]) -> None:
        """إضافة فحص مخصص."""
        self._custom_checks.append(check)

    async def is_ready(self) -> Tuple[bool, str]:
        """هل التطبيق جاهز؟"""
        # Check health manager
        await self.manager.check_all()
        overall = self.manager.get_overall_status()

        if overall == HealthStatus.UNHEALTHY:
            return False, "Health checks failing"

        # Check custom conditions
        for i, check in enumerate(self._custom_checks):
            try:
                if not check():
                    return False, f"Custom check {i} failed"
            except Exception as e:
                return False, f"Custom check {i} error: {str(e)}"

        return True, "Ready"


class LivenessProbe:
    """
    فحص الحياة (Kubernetes Liveness).

    يحدد ما إذا كان التطبيق حياً ويعمل.
    """

    def __init__(self):
        self._last_heartbeat = datetime.utcnow()
        self._max_heartbeat_age = timedelta(seconds=60)
        self._custom_checks: List[Callable[[], bool]] = []

    def heartbeat(self) -> None:
        """تسجيل نبضة قلب."""
        self._last_heartbeat = datetime.utcnow()

    def add_check(self, check: Callable[[], bool]) -> None:
        """إضافة فحص مخصص."""
        self._custom_checks.append(check)

    def is_alive(self) -> Tuple[bool, str]:
        """هل التطبيق حي؟"""
        # Check heartbeat
        age = datetime.utcnow() - self._last_heartbeat
        if age > self._max_heartbeat_age:
            return False, f"No heartbeat for {age.total_seconds():.0f}s"

        # Check custom conditions
        for i, check in enumerate(self._custom_checks):
            try:
                if not check():
                    return False, f"Liveness check {i} failed"
            except Exception as e:
                return False, f"Liveness check {i} error: {str(e)}"

        return True, "Alive"


# =============================================================================
# FastAPI Integration
# =============================================================================


def create_health_routes(manager: HealthCheckManager):
    """
    إنشاء routes للـ health checks في FastAPI.

    الاستخدام:
        from fastapi import FastAPI
        app = FastAPI()

        manager = HealthCheckManager()
        app.include_router(create_health_routes(manager))
    """
    from fastapi import APIRouter, Response

    router = APIRouter(tags=["Health"])

    @router.get("/health")
    async def health():
        """Health check endpoint."""
        await manager.check_all()
        report = manager.get_health_report()

        status_code = 200 if report["status"] == "healthy" else 503
        return Response(
            content=__import__("json").dumps(report),
            media_type="application/json",
            status_code=status_code,
        )

    @router.get("/health/live")
    async def liveness():
        """Liveness probe endpoint."""
        return {"status": "alive"}

    @router.get("/health/ready")
    async def readiness():
        """Readiness probe endpoint."""
        await manager.check_all()
        overall = manager.get_overall_status()

        if overall in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]:
            return {"status": "ready"}
        else:
            return Response(
                content='{"status": "not ready"}',
                media_type="application/json",
                status_code=503,
            )

    @router.get("/health/{check_name}")
    async def check_specific(check_name: str):
        """Check specific health check."""
        result = await manager.check(check_name)
        status_code = 200 if result.status == HealthStatus.HEALTHY else 503

        return Response(
            content=__import__("json").dumps(result.to_dict()),
            media_type="application/json",
            status_code=status_code,
        )

    return router


# =============================================================================
# Default Health Checks Setup
# =============================================================================


def setup_default_checks(
    manager: HealthCheckManager,
    database_url: Optional[str] = None,
    redis_host: Optional[str] = None,
    redis_port: int = 6379,
) -> None:
    """
    إعداد فحوصات الصحة الافتراضية.
    """
    # System resources
    manager.register(CPUHealthCheck())
    manager.register(MemoryHealthCheck())
    manager.register(DiskHealthCheck())

    # Database
    if database_url:
        manager.register(PostgreSQLHealthCheck("database", database_url))

    # Redis
    if redis_host:
        manager.register(RedisHealthCheck("redis", redis_host, redis_port))
