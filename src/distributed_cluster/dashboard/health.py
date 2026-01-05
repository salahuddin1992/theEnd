"""
Health Checker - فاحص الصحة
===========================

Health Checking System
----------------------

This module provides health checking for components.

يوفر هذا الملف فحص صحة المكونات.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """حالة الصحة / Health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """
    صحة المكون
    Component health
    """
    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    last_check: Optional[datetime] = None
    check_duration_ms: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "lastCheck": self.last_check.isoformat() if self.last_check else None,
            "checkDurationMs": self.check_duration_ms,
            "consecutiveFailures": self.consecutive_failures,
            "consecutiveSuccesses": self.consecutive_successes,
            "metadata": self.metadata,
        }


@dataclass
class HealthCheckConfig:
    """
    إعدادات فحص الصحة
    Health check configuration
    """
    interval_seconds: float = 30.0
    timeout_seconds: float = 10.0
    failure_threshold: int = 3
    success_threshold: int = 1
    initial_delay_seconds: float = 0.0


class HealthChecker:
    """
    فاحص الصحة
    Health Checker

    يفحص صحة المكونات بشكل دوري.
    Periodically checks component health.
    """

    def __init__(
        self,
        default_config: Optional[HealthCheckConfig] = None,
    ):
        """
        تهيئة الفاحص

        Args:
            default_config: الإعدادات الافتراضية
        """
        self.default_config = default_config or HealthCheckConfig()

        # Components
        self._components: dict[str, ComponentHealth] = {}
        self._checks: dict[str, tuple[Callable, HealthCheckConfig]] = {}

        # State
        self._running = False
        self._check_tasks: dict[str, asyncio.Task] = {}

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء الفاحص"""
        self._running = True

        # Start check tasks
        for name in self._checks:
            await self._start_check_task(name)

        logger.info("HealthChecker started")

    async def stop(self) -> None:
        """إيقاف الفاحص"""
        self._running = False

        # Cancel all tasks
        for task in self._check_tasks.values():
            task.cancel()

        await asyncio.gather(*self._check_tasks.values(), return_exceptions=True)
        self._check_tasks.clear()

        logger.info("HealthChecker stopped")

    # =========================================================================
    # Registration
    # =========================================================================

    def register(
        self,
        name: str,
        check_fn: Callable[[], bool],
        config: Optional[HealthCheckConfig] = None,
    ) -> None:
        """
        تسجيل مكون للفحص
        Register component for health checking
        """
        cfg = config or self.default_config

        self._components[name] = ComponentHealth(name=name)
        self._checks[name] = (check_fn, cfg)

        logger.debug(f"Registered health check: {name}")

        # Start task if already running
        if self._running:
            asyncio.create_task(self._start_check_task(name))

    def unregister(self, name: str) -> None:
        """إلغاء تسجيل مكون"""
        if name in self._check_tasks:
            self._check_tasks[name].cancel()
            del self._check_tasks[name]

        self._components.pop(name, None)
        self._checks.pop(name, None)

    async def _start_check_task(self, name: str) -> None:
        """بدء مهمة الفحص"""
        if name in self._check_tasks:
            return

        check_fn, config = self._checks[name]

        # Initial delay
        if config.initial_delay_seconds > 0:
            await asyncio.sleep(config.initial_delay_seconds)

        task = asyncio.create_task(
            self._check_loop(name, check_fn, config)
        )
        self._check_tasks[name] = task

    async def _check_loop(
        self,
        name: str,
        check_fn: Callable,
        config: HealthCheckConfig,
    ) -> None:
        """حلقة الفحص"""
        while self._running:
            try:
                await self._run_check(name, check_fn, config)
                await asyncio.sleep(config.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Check loop error for {name}: {e}")
                await asyncio.sleep(5)

    async def _run_check(
        self,
        name: str,
        check_fn: Callable,
        config: HealthCheckConfig,
    ) -> None:
        """تشغيل فحص واحد"""
        component = self._components[name]
        start_time = datetime.now(timezone.utc)

        try:
            # Run check with timeout
            if asyncio.iscoroutinefunction(check_fn):
                result = await asyncio.wait_for(
                    check_fn(),
                    timeout=config.timeout_seconds,
                )
            else:
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, check_fn),
                    timeout=config.timeout_seconds,
                )

            # Update component
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            component.check_duration_ms = duration
            component.last_check = datetime.now(timezone.utc)

            if result:
                component.consecutive_successes += 1
                component.consecutive_failures = 0

                if component.consecutive_successes >= config.success_threshold:
                    component.status = HealthStatus.HEALTHY
                    component.message = "All checks passing"
            else:
                await self._handle_failure(component, config, "Check returned false")

        except asyncio.TimeoutError:
            await self._handle_failure(component, config, "Check timed out")
        except Exception as e:
            await self._handle_failure(component, config, str(e))

    async def _handle_failure(
        self,
        component: ComponentHealth,
        config: HealthCheckConfig,
        message: str,
    ) -> None:
        """معالجة فشل الفحص"""
        component.consecutive_failures += 1
        component.consecutive_successes = 0
        component.message = message
        component.last_check = datetime.now(timezone.utc)

        if component.consecutive_failures >= config.failure_threshold:
            component.status = HealthStatus.UNHEALTHY
        else:
            component.status = HealthStatus.DEGRADED

        logger.warning(
            f"Health check failed for {component.name}: {message} "
            f"(failures: {component.consecutive_failures})"
        )

    # =========================================================================
    # Query
    # =========================================================================

    def get_component(self, name: str) -> Optional[ComponentHealth]:
        """الحصول على صحة مكون"""
        return self._components.get(name)

    def get_all_components(self) -> dict[str, ComponentHealth]:
        """الحصول على جميع المكونات"""
        return self._components.copy()

    def is_healthy(self) -> bool:
        """هل جميع المكونات سليمة؟"""
        if not self._components:
            return True

        return all(
            c.status == HealthStatus.HEALTHY
            for c in self._components.values()
        )

    def get_status(self) -> dict[str, Any]:
        """الحصول على الحالة الكاملة"""
        components = self._components.values()

        healthy_count = sum(
            1 for c in components if c.status == HealthStatus.HEALTHY
        )
        degraded_count = sum(
            1 for c in components if c.status == HealthStatus.DEGRADED
        )
        unhealthy_count = sum(
            1 for c in components if c.status == HealthStatus.UNHEALTHY
        )

        # Overall status
        if unhealthy_count > 0:
            overall = HealthStatus.UNHEALTHY
        elif degraded_count > 0:
            overall = HealthStatus.DEGRADED
        elif healthy_count == len(components):
            overall = HealthStatus.HEALTHY
        else:
            overall = HealthStatus.UNKNOWN

        return {
            "status": overall.value,
            "healthy": healthy_count,
            "degraded": degraded_count,
            "unhealthy": unhealthy_count,
            "total": len(components),
            "components": {
                name: comp.to_dict()
                for name, comp in self._components.items()
            },
        }

    async def check_now(self) -> dict[str, HealthStatus]:
        """تشغيل جميع الفحوصات الآن"""
        for name, (check_fn, config) in self._checks.items():
            await self._run_check(name, check_fn, config)

        return {
            name: comp.status
            for name, comp in self._components.items()
        }


# =============================================================================
# Predefined Checks
# =============================================================================

def create_http_check(
    url: str,
    expected_status: int = 200,
    timeout: float = 10.0,
) -> Callable[[], bool]:
    """إنشاء فحص HTTP"""
    async def check():
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            return response.status_code == expected_status

    return check


def create_tcp_check(
    host: str,
    port: int,
    timeout: float = 5.0,
) -> Callable[[], bool]:
    """إنشاء فحص TCP"""
    async def check():
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    return check


def create_disk_check(
    path: str = "/",
    threshold_percent: float = 90.0,
) -> Callable[[], bool]:
    """إنشاء فحص القرص"""
    def check():
        import shutil

        total, used, free = shutil.disk_usage(path)
        percent = (used / total) * 100
        return percent < threshold_percent

    return check


def create_memory_check(
    threshold_percent: float = 90.0,
) -> Callable[[], bool]:
    """إنشاء فحص الذاكرة"""
    def check():
        import psutil

        memory = psutil.virtual_memory()
        return memory.percent < threshold_percent

    return check
