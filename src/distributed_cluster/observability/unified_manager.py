"""
Unified Observability Manager - مدير المراقبة الموحد
====================================================

مدير موحد يجمع بين:
- Advanced Metrics
- Enhanced Logging
- Comprehensive Health Checks
- Circuit Breakers
- Rate Limiters
- Distributed Tracing

يوفر واجهة موحدة للمراقبة والإدارة.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import our modules
from .advanced_metrics import (
    MetricsAggregator,
    RequestMetrics,
    SLODefinition,
    create_default_slos,
    get_metrics_aggregator,
)
from .comprehensive_health import (
    CPUHealthCheck,
    DiskHealthCheck,
    HealthCheck,
    HealthCheckManager,
    HealthStatus,
    LivenessProbe,
    MemoryHealthCheck,
    ReadinessProbe,
)
from .enhanced_logging import (
    AsyncFileHandler,
    ConsoleHandler,
    CorrelationContext,
    EnhancedLogger,
    LogAggregator,
    LoggerFactory,
    LogLevel,
    generate_correlation_id,
)


class ObservabilityStatus(str, Enum):
    """حالة نظام المراقبة."""

    RUNNING = "running"
    STOPPED = "stopped"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass
class ObservabilityConfig:
    """إعدادات نظام المراقبة."""

    # Service info
    service_name: str = "distributed_cluster"
    service_version: str = "0.1.0"
    environment: str = "production"

    # Logging
    log_level: LogLevel = LogLevel.INFO
    log_to_console: bool = True
    log_to_file: bool = True
    log_file_path: str = "logs/app.log"
    log_json_format: bool = True

    # Metrics
    metrics_enabled: bool = True
    metrics_endpoint: str = "/metrics"

    # Health
    health_check_interval: float = 30.0
    health_endpoint: str = "/health"

    # Tracing
    tracing_enabled: bool = True
    tracing_sample_rate: float = 1.0

    # Alerting
    alerting_enabled: bool = True
    alert_evaluation_interval: float = 30.0


@dataclass
class SystemStatus:
    """حالة النظام الشاملة."""

    status: ObservabilityStatus
    health: HealthStatus
    uptime_seconds: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Components
    logging_active: bool = True
    metrics_active: bool = True
    health_checks_active: bool = True
    alerting_active: bool = True

    # Stats
    total_requests: int = 0
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0
    active_alerts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        return {
            "status": self.status.value,
            "health": self.health.value,
            "uptime_seconds": self.uptime_seconds,
            "timestamp": self.timestamp.isoformat(),
            "components": {
                "logging": self.logging_active,
                "metrics": self.metrics_active,
                "health_checks": self.health_checks_active,
                "alerting": self.alerting_active,
            },
            "stats": {
                "total_requests": self.total_requests,
                "error_rate": self.error_rate,
                "avg_latency_ms": self.avg_latency_ms,
                "active_alerts": self.active_alerts,
            },
        }


class UnifiedObservabilityManager:
    """
    مدير المراقبة الموحد.

    يوفر واجهة موحدة لكل أنظمة المراقبة.

    الاستخدام:
        manager = UnifiedObservabilityManager(config)
        await manager.start()

        # الحصول على logger
        logger = manager.get_logger("my_module")

        # تسجيل metrics
        manager.record_request(...)

        # فحص الصحة
        health = await manager.check_health()

        await manager.stop()
    """

    def __init__(self, config: Optional[ObservabilityConfig] = None):
        self.config = config or ObservabilityConfig()

        self._status = ObservabilityStatus.STOPPED
        self._start_time: Optional[datetime] = None
        self._lock = threading.Lock()

        # Initialize components
        self._logger_factory: Optional[LoggerFactory] = None
        self._log_aggregator: Optional[LogAggregator] = None
        self._metrics_aggregator: Optional[MetricsAggregator] = None
        self._health_manager: Optional[HealthCheckManager] = None
        self._readiness_probe: Optional[ReadinessProbe] = None
        self._liveness_probe: Optional[LivenessProbe] = None

        # Background tasks
        self._tasks: List[asyncio.Task] = []

        # Callbacks
        self._on_alert: Optional[Callable[[str, str, str], None]] = None
        self._on_health_change: Optional[Callable[[HealthStatus], None]] = None

        # Internal logger
        self._internal_logger: Optional[EnhancedLogger] = None

    async def start(self) -> None:
        """بدء نظام المراقبة."""
        if self._status == ObservabilityStatus.RUNNING:
            return

        with self._lock:
            self._start_time = datetime.now(timezone.utc)
            self._status = ObservabilityStatus.RUNNING

        # Initialize logging
        self._setup_logging()

        # Initialize metrics
        self._setup_metrics()

        # Initialize health checks
        self._setup_health_checks()

        # Start background tasks
        await self._start_background_tasks()

        self._internal_logger.info(
            "Observability system started",
            service=self.config.service_name,
            version=self.config.service_version,
            environment=self.config.environment,
        )

    async def stop(self) -> None:
        """إيقاف نظام المراقبة."""
        if self._status == ObservabilityStatus.STOPPED:
            return

        self._internal_logger.info("Stopping observability system...")

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._tasks.clear()

        # Stop health checks
        if self._health_manager:
            await self._health_manager.stop_background_checks()

        # Close logging
        if self._logger_factory:
            self._logger_factory.close_all()

        with self._lock:
            self._status = ObservabilityStatus.STOPPED

    def _setup_logging(self) -> None:
        """إعداد نظام التسجيل."""
        self._logger_factory = LoggerFactory(
            default_level=self.config.log_level,
            service_name=self.config.service_name,
            environment=self.config.environment,
        )

        # Add console handler
        if self.config.log_to_console:
            self._logger_factory.add_handler(
                ConsoleHandler(
                    level=self.config.log_level,
                    json_format=self.config.log_json_format,
                )
            )

        # Add file handler
        if self.config.log_to_file:
            self._logger_factory.add_handler(
                AsyncFileHandler(
                    self.config.log_file_path,
                    level=self.config.log_level,
                    json_format=self.config.log_json_format,
                )
            )

        # Add log aggregator
        self._log_aggregator = LogAggregator()
        self._logger_factory.set_aggregator(self._log_aggregator)

        # Get internal logger
        self._internal_logger = self._logger_factory.get_logger("observability")

    def _setup_metrics(self) -> None:
        """إعداد نظام المقاييس."""
        if not self.config.metrics_enabled:
            return

        self._metrics_aggregator = get_metrics_aggregator()

        # Register default SLOs
        for slo in create_default_slos():
            self._metrics_aggregator.slo_monitor.register_slo(slo)

    def _setup_health_checks(self) -> None:
        """إعداد فحوصات الصحة."""
        self._health_manager = HealthCheckManager(
            service_name=self.config.service_name,
            version=self.config.service_version,
        )

        # Register default checks
        self._health_manager.register(CPUHealthCheck())
        self._health_manager.register(MemoryHealthCheck())
        self._health_manager.register(DiskHealthCheck())

        # Create probes
        self._readiness_probe = ReadinessProbe(self._health_manager)
        self._liveness_probe = LivenessProbe()

    async def _start_background_tasks(self) -> None:
        """بدء المهام الخلفية."""
        # Start health check loop
        if self._health_manager:
            await self._health_manager.start_background_checks(
                interval=self.config.health_check_interval
            )

        # Start heartbeat task
        self._tasks.append(
            asyncio.create_task(self._heartbeat_loop())
        )

        # Start metrics collection task
        if self._metrics_aggregator:
            self._tasks.append(
                asyncio.create_task(self._metrics_collection_loop())
            )

    async def _heartbeat_loop(self) -> None:
        """حلقة نبضات القلب."""
        while self._status == ObservabilityStatus.RUNNING:
            try:
                if self._liveness_probe:
                    self._liveness_probe.heartbeat()
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._internal_logger.error(f"Heartbeat error: {e}")

    async def _metrics_collection_loop(self) -> None:
        """حلقة جمع المقاييس."""
        while self._status == ObservabilityStatus.RUNNING:
            try:
                # Collect system metrics
                # (يمكن إضافة جمع مقاييس إضافية هنا)
                await asyncio.sleep(15)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._internal_logger.error(f"Metrics collection error: {e}")

    # =========================================================================
    # Logging
    # =========================================================================

    def get_logger(self, name: str) -> EnhancedLogger:
        """الحصول على logger."""
        if not self._logger_factory:
            self._setup_logging()
        return self._logger_factory.get_logger(name)

    def search_logs(
        self,
        level: Optional[LogLevel] = None,
        message_contains: Optional[str] = None,
        correlation_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """البحث في السجلات."""
        if not self._log_aggregator:
            return []

        if correlation_id:
            records = self._log_aggregator.get_by_correlation(correlation_id)
        else:
            records = self._log_aggregator.search(
                level=level,
                message_contains=message_contains,
                since=since,
                limit=limit,
            )

        return [r.to_dict() for r in records]

    # =========================================================================
    # Metrics
    # =========================================================================

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
        request_size: int = 0,
        response_size: int = 0,
    ) -> None:
        """تسجيل طلب HTTP."""
        if not self._metrics_aggregator:
            return

        metrics = RequestMetrics(
            method=method,
            path=path,
            status_code=status_code,
            duration_seconds=duration_seconds,
            request_size_bytes=request_size,
            response_size_bytes=response_size,
        )

        self._metrics_aggregator.request_metrics.record(metrics)

    def record_business_metric(
        self,
        name: str,
        value: float,
        unit: str = "",
        **labels,
    ) -> None:
        """تسجيل مقياس عمل."""
        if not self._metrics_aggregator:
            return

        self._metrics_aggregator.business_metrics.record(name, value, unit, **labels)

    def get_metrics_summary(self) -> Dict[str, Any]:
        """الحصول على ملخص المقاييس."""
        if not self._metrics_aggregator:
            return {}

        return self._metrics_aggregator.get_all_metrics()

    def export_prometheus_metrics(self) -> str:
        """تصدير المقاييس بصيغة Prometheus."""
        if not self._metrics_aggregator:
            return ""

        return self._metrics_aggregator.export_prometheus()

    def register_slo(self, slo: SLODefinition) -> None:
        """تسجيل SLO."""
        if self._metrics_aggregator:
            self._metrics_aggregator.slo_monitor.register_slo(slo)

    # =========================================================================
    # Health
    # =========================================================================

    def register_health_check(self, check: HealthCheck) -> None:
        """تسجيل فحص صحة."""
        if self._health_manager:
            self._health_manager.register(check)

    async def check_health(self) -> Dict[str, Any]:
        """فحص الصحة الشامل."""
        if not self._health_manager:
            return {"status": "unknown"}

        await self._health_manager.check_all()
        return self._health_manager.get_health_report()

    async def is_ready(self) -> Tuple[bool, str]:
        """هل النظام جاهز؟"""
        if not self._readiness_probe:
            return True, "No readiness probe configured"
        return await self._readiness_probe.is_ready()

    def is_alive(self) -> Tuple[bool, str]:
        """هل النظام حي؟"""
        if not self._liveness_probe:
            return True, "No liveness probe configured"
        return self._liveness_probe.is_alive()

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> SystemStatus:
        """الحصول على حالة النظام."""
        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()

        # Get health status
        health = HealthStatus.UNKNOWN
        if self._health_manager:
            health = self._health_manager.get_overall_status()

        # Get metrics stats
        total_requests = 0
        error_rate = 0.0
        avg_latency = 0.0

        if self._metrics_aggregator:
            summary = self._metrics_aggregator.request_metrics.get_summary()
            error_rate = summary.get("error_rate", 0)
            avg_latency = summary.get("avg_latency_ms", 0)

        return SystemStatus(
            status=self._status,
            health=health,
            uptime_seconds=uptime,
            logging_active=self._logger_factory is not None,
            metrics_active=self._metrics_aggregator is not None,
            health_checks_active=self._health_manager is not None,
            alerting_active=self.config.alerting_enabled,
            total_requests=total_requests,
            error_rate=error_rate,
            avg_latency_ms=avg_latency,
        )

    # =========================================================================
    # Context Managers
    # =========================================================================

    def correlation_context(
        self,
        correlation_id: Optional[str] = None,
        **extra,
    ) -> CorrelationContext:
        """Context manager لـ correlation."""
        return CorrelationContext(
            correlation_id=correlation_id or generate_correlation_id(),
            **extra,
        )

    # =========================================================================
    # Callbacks
    # =========================================================================

    def on_alert(self, callback: Callable[[str, str, str], None]) -> None:
        """تعيين callback للتنبيهات."""
        self._on_alert = callback

    def on_health_change(self, callback: Callable[[HealthStatus], None]) -> None:
        """تعيين callback لتغيير الصحة."""
        self._on_health_change = callback


# =============================================================================
# FastAPI Integration
# =============================================================================


def create_observability_routes(manager: UnifiedObservabilityManager):
    """
    إنشاء routes للمراقبة في FastAPI.

    الاستخدام:
        from fastapi import FastAPI
        app = FastAPI()

        manager = UnifiedObservabilityManager()
        app.include_router(create_observability_routes(manager))
    """
    from fastapi import APIRouter, Response

    router = APIRouter(prefix="/observability", tags=["Observability"])

    @router.get("/status")
    async def get_status():
        """System status endpoint."""
        status = manager.get_status()
        return status.to_dict()

    @router.get("/health")
    async def health_check():
        """Health check endpoint."""
        report = await manager.check_health()
        status_code = 200 if report.get("status") == "healthy" else 503
        return Response(
            content=json.dumps(report),
            media_type="application/json",
            status_code=status_code,
        )

    @router.get("/health/live")
    async def liveness():
        """Liveness probe endpoint."""
        is_alive, message = manager.is_alive()
        if is_alive:
            return {"status": "alive", "message": message}
        return Response(
            content=json.dumps({"status": "dead", "message": message}),
            media_type="application/json",
            status_code=503,
        )

    @router.get("/health/ready")
    async def readiness():
        """Readiness probe endpoint."""
        is_ready, message = await manager.is_ready()
        if is_ready:
            return {"status": "ready", "message": message}
        return Response(
            content=json.dumps({"status": "not_ready", "message": message}),
            media_type="application/json",
            status_code=503,
        )

    @router.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint."""
        prometheus_output = manager.export_prometheus_metrics()
        return Response(
            content=prometheus_output,
            media_type="text/plain; charset=utf-8",
        )

    @router.get("/metrics/json")
    async def metrics_json():
        """JSON metrics endpoint."""
        return manager.get_metrics_summary()

    @router.get("/logs")
    async def search_logs(
        level: Optional[str] = None,
        message: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ):
        """Search logs endpoint."""
        log_level = None
        if level:
            log_level = LogLevel[level.upper()]

        logs = manager.search_logs(
            level=log_level,
            message_contains=message,
            correlation_id=correlation_id,
            limit=limit,
        )
        return {"logs": logs, "count": len(logs)}

    return router


def create_observability_middleware(manager: UnifiedObservabilityManager):
    """
    إنشاء middleware للمراقبة في FastAPI.

    الاستخدام:
        app.middleware("http")(create_observability_middleware(manager))
    """

    async def observability_middleware(request, call_next):
        # Generate correlation ID
        correlation_id = (
            request.headers.get("X-Correlation-ID") or generate_correlation_id()
        )

        start_time = time.time()

        with manager.correlation_context(correlation_id=correlation_id):
            # Log request
            logger = manager.get_logger("http")
            logger.info(
                "Request started",
                method=request.method,
                path=request.url.path,
            )

            try:
                response = await call_next(request)
                duration = time.time() - start_time

                # Record metrics
                manager.record_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_seconds=duration,
                )

                # Log response
                logger.info(
                    "Request completed",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration * 1000,
                )

                # Add correlation ID to response
                response.headers["X-Correlation-ID"] = correlation_id

                return response

            except Exception as e:
                duration = time.time() - start_time

                # Record error
                manager.record_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=500,
                    duration_seconds=duration,
                )

                logger.error(
                    "Request failed",
                    exc_info=True,
                    method=request.method,
                    path=request.url.path,
                    error=str(e),
                )

                raise

    return observability_middleware


# =============================================================================
# Global Instance
# =============================================================================


_manager: Optional[UnifiedObservabilityManager] = None


def get_observability_manager() -> UnifiedObservabilityManager:
    """الحصول على مدير المراقبة العام."""
    global _manager
    if _manager is None:
        _manager = UnifiedObservabilityManager()
    return _manager


async def setup_observability(config: Optional[ObservabilityConfig] = None) -> UnifiedObservabilityManager:
    """إعداد نظام المراقبة."""
    global _manager
    _manager = UnifiedObservabilityManager(config)
    await _manager.start()
    return _manager


async def shutdown_observability() -> None:
    """إيقاف نظام المراقبة."""
    global _manager
    if _manager:
        await _manager.stop()
        _manager = None
