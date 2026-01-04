"""
Health Monitor - مراقب الصحة
============================

Kubernetes Health Monitoring
----------------------------

This module provides health monitoring and auto-recovery.

يوفر هذا الملف مراقبة الصحة والتعافي التلقائي.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """حالة الصحة / Health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class RecoveryAction(str, Enum):
    """إجراء التعافي / Recovery action"""
    NONE = "none"
    RESTART_POD = "restart_pod"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    REPLACE_NODE = "replace_node"
    ALERT = "alert"
    CUSTOM = "custom"


@dataclass
class HealthCheck:
    """
    فحص صحة
    Health check definition
    """
    name: str
    check_fn: Callable[[], bool]
    interval_seconds: int = 30
    timeout_seconds: int = 10
    failure_threshold: int = 3
    success_threshold: int = 1
    recovery_action: RecoveryAction = RecoveryAction.ALERT

    # State
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_check_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    status: HealthStatus = HealthStatus.UNKNOWN


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
    checks: dict[str, HealthCheck] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "lastCheck": self.last_check.isoformat() if self.last_check else None,
            "checks": {
                name: {
                    "status": check.status.value,
                    "lastSuccess": check.last_success_time.isoformat()
                        if check.last_success_time else None,
                    "lastFailure": check.last_failure_time.isoformat()
                        if check.last_failure_time else None,
                    "consecutiveFailures": check.consecutive_failures,
                }
                for name, check in self.checks.items()
            },
        }


class HealthMonitor:
    """
    مراقب الصحة
    Health Monitor

    يراقب صحة المكونات ويتخذ إجراءات التعافي.
    Monitors component health and takes recovery actions.
    """

    def __init__(
        self,
        check_interval_seconds: int = 30,
        recovery_enabled: bool = True,
    ):
        """
        تهيئة مراقب الصحة

        Args:
            check_interval_seconds: فترة الفحص
            recovery_enabled: تفعيل التعافي التلقائي
        """
        self.check_interval_seconds = check_interval_seconds
        self.recovery_enabled = recovery_enabled

        # Components
        self._components: dict[str, ComponentHealth] = {}

        # Recovery handlers
        self._recovery_handlers: dict[RecoveryAction, Callable] = {}

        # State
        self._running = False
        self._check_tasks: list[asyncio.Task] = []

        # Statistics
        self._total_checks = 0
        self._failed_checks = 0
        self._recoveries_triggered = 0

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء المراقب"""
        self._running = True

        # Register default recovery handlers
        self._register_default_handlers()

        # Start check loop
        task = asyncio.create_task(self._check_loop())
        self._check_tasks.append(task)

        logger.info("HealthMonitor started")

    async def stop(self) -> None:
        """إيقاف المراقب"""
        self._running = False

        for task in self._check_tasks:
            task.cancel()

        await asyncio.gather(*self._check_tasks, return_exceptions=True)
        self._check_tasks.clear()

        logger.info("HealthMonitor stopped")

    # =========================================================================
    # Registration
    # =========================================================================

    def register_component(
        self,
        name: str,
        checks: Optional[list[HealthCheck]] = None,
    ) -> ComponentHealth:
        """
        تسجيل مكون للمراقبة
        Register component for monitoring
        """
        component = ComponentHealth(name=name)

        if checks:
            for check in checks:
                component.checks[check.name] = check

        self._components[name] = component
        logger.info(f"Registered component: {name}")

        return component

    def add_check(
        self,
        component_name: str,
        check: HealthCheck,
    ) -> None:
        """إضافة فحص لمكون"""
        if component_name not in self._components:
            self.register_component(component_name)

        self._components[component_name].checks[check.name] = check

    def register_recovery_handler(
        self,
        action: RecoveryAction,
        handler: Callable,
    ) -> None:
        """تسجيل معالج تعافي"""
        self._recovery_handlers[action] = handler

    def _register_default_handlers(self) -> None:
        """تسجيل المعالجات الافتراضية"""
        self.register_recovery_handler(
            RecoveryAction.ALERT,
            self._handle_alert,
        )
        self.register_recovery_handler(
            RecoveryAction.RESTART_POD,
            self._handle_restart_pod,
        )

    # =========================================================================
    # Health Checking
    # =========================================================================

    async def _check_loop(self) -> None:
        """حلقة الفحص"""
        while self._running:
            try:
                await self._run_all_checks()
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Check loop error: {e}")
                await asyncio.sleep(5)

    async def _run_all_checks(self) -> None:
        """تشغيل جميع الفحوصات"""
        for component in self._components.values():
            for check in component.checks.values():
                await self._run_check(component, check)

            # Update component status
            self._update_component_status(component)

    async def _run_check(
        self,
        component: ComponentHealth,
        check: HealthCheck,
    ) -> None:
        """تشغيل فحص واحد"""
        self._total_checks += 1
        check.last_check_time = datetime.utcnow()

        try:
            # Run check with timeout
            if asyncio.iscoroutinefunction(check.check_fn):
                result = await asyncio.wait_for(
                    check.check_fn(),
                    timeout=check.timeout_seconds,
                )
            else:
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, check.check_fn),
                    timeout=check.timeout_seconds,
                )

            if result:
                await self._handle_success(component, check)
            else:
                await self._handle_failure(component, check, "Check returned false")

        except asyncio.TimeoutError:
            await self._handle_failure(component, check, "Check timed out")
        except Exception as e:
            await self._handle_failure(component, check, str(e))

    async def _handle_success(
        self,
        component: ComponentHealth,
        check: HealthCheck,
    ) -> None:
        """معالجة نجاح الفحص"""
        check.consecutive_successes += 1
        check.consecutive_failures = 0
        check.last_success_time = datetime.utcnow()

        if check.consecutive_successes >= check.success_threshold:
            check.status = HealthStatus.HEALTHY

    async def _handle_failure(
        self,
        component: ComponentHealth,
        check: HealthCheck,
        message: str,
    ) -> None:
        """معالجة فشل الفحص"""
        self._failed_checks += 1
        check.consecutive_failures += 1
        check.consecutive_successes = 0
        check.last_failure_time = datetime.utcnow()

        logger.warning(
            f"Health check failed: {component.name}/{check.name}: {message}"
        )

        if check.consecutive_failures >= check.failure_threshold:
            check.status = HealthStatus.UNHEALTHY

            # Trigger recovery
            if self.recovery_enabled:
                await self._trigger_recovery(component, check)

    def _update_component_status(self, component: ComponentHealth) -> None:
        """تحديث حالة المكون"""
        component.last_check = datetime.utcnow()

        if not component.checks:
            component.status = HealthStatus.UNKNOWN
            return

        statuses = [check.status for check in component.checks.values()]

        if all(s == HealthStatus.HEALTHY for s in statuses):
            component.status = HealthStatus.HEALTHY
            component.message = "All checks passing"
        elif any(s == HealthStatus.UNHEALTHY for s in statuses):
            unhealthy = [
                name for name, check in component.checks.items()
                if check.status == HealthStatus.UNHEALTHY
            ]
            component.status = HealthStatus.UNHEALTHY
            component.message = f"Failed checks: {', '.join(unhealthy)}"
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            component.status = HealthStatus.DEGRADED
            component.message = "Some checks degraded"
        else:
            component.status = HealthStatus.UNKNOWN
            component.message = "Status unknown"

    # =========================================================================
    # Recovery
    # =========================================================================

    async def _trigger_recovery(
        self,
        component: ComponentHealth,
        check: HealthCheck,
    ) -> None:
        """تنفيذ إجراء التعافي"""
        action = check.recovery_action
        handler = self._recovery_handlers.get(action)

        if not handler:
            logger.warning(f"No handler for recovery action: {action}")
            return

        logger.info(
            f"Triggering recovery action {action.value} for "
            f"{component.name}/{check.name}"
        )

        self._recoveries_triggered += 1

        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(component, check)
            else:
                handler(component, check)

            logger.info(f"Recovery action completed: {action.value}")

        except Exception as e:
            logger.error(f"Recovery action failed: {e}")

    async def _handle_alert(
        self,
        component: ComponentHealth,
        check: HealthCheck,
    ) -> None:
        """معالج التنبيه"""
        logger.error(
            f"ALERT: Component {component.name} check {check.name} "
            f"failed {check.consecutive_failures} times"
        )
        # Here you would integrate with your alerting system

    async def _handle_restart_pod(
        self,
        component: ComponentHealth,
        check: HealthCheck,
    ) -> None:
        """معالج إعادة تشغيل Pod"""
        logger.info(f"Restarting pod for component: {component.name}")
        # Here you would use Kubernetes API to restart the pod

    # =========================================================================
    # API
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """الحصول على حالة المراقب"""
        return {
            "running": self._running,
            "total_checks": self._total_checks,
            "failed_checks": self._failed_checks,
            "recoveries_triggered": self._recoveries_triggered,
            "components": {
                name: component.to_dict()
                for name, component in self._components.items()
            },
        }

    def get_component_status(
        self,
        component_name: str,
    ) -> Optional[ComponentHealth]:
        """الحصول على حالة مكون"""
        return self._components.get(component_name)

    def is_healthy(self) -> bool:
        """هل جميع المكونات سليمة؟"""
        if not self._components:
            return True

        return all(
            c.status == HealthStatus.HEALTHY
            for c in self._components.values()
        )

    async def check_now(self) -> dict[str, HealthStatus]:
        """تشغيل جميع الفحوصات الآن"""
        await self._run_all_checks()

        return {
            name: component.status
            for name, component in self._components.items()
        }


# =============================================================================
# Predefined Health Checks
# =============================================================================

def create_http_health_check(
    name: str,
    url: str,
    expected_status: int = 200,
    timeout: int = 10,
) -> HealthCheck:
    """إنشاء فحص صحة HTTP"""
    import httpx

    async def check():
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            return response.status_code == expected_status

    return HealthCheck(
        name=name,
        check_fn=check,
        timeout_seconds=timeout,
    )


def create_tcp_health_check(
    name: str,
    host: str,
    port: int,
    timeout: int = 5,
) -> HealthCheck:
    """إنشاء فحص صحة TCP"""
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

    return HealthCheck(
        name=name,
        check_fn=check,
        timeout_seconds=timeout,
    )


def create_dns_health_check(
    name: str,
    hostname: str,
    timeout: int = 5,
) -> HealthCheck:
    """إنشاء فحص صحة DNS"""
    import socket

    def check():
        try:
            socket.gethostbyname(hostname)
            return True
        except socket.gaierror:
            return False

    return HealthCheck(
        name=name,
        check_fn=check,
        timeout_seconds=timeout,
    )
