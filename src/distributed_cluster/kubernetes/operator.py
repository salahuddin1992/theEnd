"""
Cluster Operator - مشغّل الكلاستر
================================

Kubernetes Operator
-------------------

This module implements the main Kubernetes operator.

يطبق هذا الملف مشغّل Kubernetes الرئيسي.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from distributed_cluster.kubernetes.controller import (
    ClusterController,
    ControllerConfig,
)
from distributed_cluster.kubernetes.crds import CRDManager
from distributed_cluster.kubernetes.health import HealthMonitor

logger = logging.getLogger(__name__)


@dataclass
class OperatorConfig:
    """
    إعدادات المشغّل
    Operator configuration
    """
    # Controller
    controller: ControllerConfig = field(default_factory=ControllerConfig)

    # CRDs
    install_crds: bool = True
    manage_crds: bool = True

    # Health monitoring
    health_check_enabled: bool = True
    health_check_port: int = 8081

    # Metrics
    metrics_enabled: bool = True
    metrics_port: int = 8080

    # Webhook
    webhook_enabled: bool = False
    webhook_port: int = 9443
    webhook_cert_dir: str = "/tmp/k8s-webhook-server/serving-certs"

    # Leader election
    leader_election: bool = True

    # Logging
    log_level: str = "INFO"

    def to_dict(self) -> dict[str, Any]:
        return {
            "controller": self.controller.to_dict(),
            "installCRDs": self.install_crds,
            "healthCheck": {
                "enabled": self.health_check_enabled,
                "port": self.health_check_port,
            },
            "metrics": {
                "enabled": self.metrics_enabled,
                "port": self.metrics_port,
            },
            "webhook": {
                "enabled": self.webhook_enabled,
                "port": self.webhook_port,
            },
            "leaderElection": self.leader_election,
        }


class ClusterOperator:
    """
    مشغّل الكلاستر الموزع
    Distributed Cluster Operator

    يدير دورة حياة الكلاستر في Kubernetes.
    Manages cluster lifecycle in Kubernetes.
    """

    def __init__(
        self,
        config: Optional[OperatorConfig] = None,
        kubeconfig: Optional[str] = None,
    ):
        """
        تهيئة المشغّل

        Args:
            config: إعدادات المشغّل
            kubeconfig: مسار kubeconfig
        """
        self.config = config or OperatorConfig()
        self.kubeconfig = kubeconfig

        # Components
        self._crd_manager = CRDManager(kubeconfig=kubeconfig)
        self._controller = ClusterController(
            config=self.config.controller,
            kubeconfig=kubeconfig,
        )
        self._health_monitor: Optional[HealthMonitor] = None

        # State
        self._running = False
        self._started_at: Optional[datetime] = None
        self._shutdown_event = asyncio.Event()

        # HTTP servers
        self._health_server = None
        self._metrics_server = None

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> bool:
        """
        بدء المشغّل
        Start the operator
        """
        try:
            logger.info("Starting Cluster Operator...")

            # Install CRDs if enabled
            if self.config.install_crds:
                if await self._crd_manager.initialize():
                    await self._crd_manager.install_crds()
                else:
                    logger.warning("Could not initialize CRD manager")

            # Start controller
            if not await self._controller.start():
                logger.error("Failed to start controller")
                return False

            # Start health monitor
            if self.config.health_check_enabled:
                self._health_monitor = HealthMonitor()
                await self._health_monitor.start()

            # Start health server
            if self.config.health_check_enabled:
                await self._start_health_server()

            # Start metrics server
            if self.config.metrics_enabled:
                await self._start_metrics_server()

            # Setup signal handlers
            self._setup_signals()

            self._running = True
            self._started_at = datetime.utcnow()

            logger.info("Cluster Operator started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start operator: {e}")
            return False

    async def stop(self) -> None:
        """
        إيقاف المشغّل
        Stop the operator
        """
        logger.info("Stopping Cluster Operator...")

        self._running = False
        self._shutdown_event.set()

        # Stop components
        await self._controller.stop()

        if self._health_monitor:
            await self._health_monitor.stop()

        if self._health_server:
            self._health_server.close()
            await self._health_server.wait_closed()

        if self._metrics_server:
            self._metrics_server.close()
            await self._metrics_server.wait_closed()

        logger.info("Cluster Operator stopped")

    async def run(self) -> None:
        """
        تشغيل المشغّل حتى الإيقاف
        Run operator until shutdown
        """
        if not await self.start():
            return

        try:
            # Wait for shutdown signal
            await self._shutdown_event.wait()
        finally:
            await self.stop()

    def _setup_signals(self) -> None:
        """إعداد معالجات الإشارات"""
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._handle_signal(sig)),
            )

    async def _handle_signal(self, sig: signal.Signals) -> None:
        """معالجة الإشارة"""
        logger.info(f"Received signal {sig.name}")
        self._shutdown_event.set()

    # =========================================================================
    # HTTP Servers
    # =========================================================================

    async def _start_health_server(self) -> None:
        """بدء خادم الصحة"""
        async def handle_health(reader, writer):
            request = await reader.read(1024)

            # Parse path
            path = "/healthz"
            if b"GET " in request:
                parts = request.split(b" ")
                if len(parts) > 1:
                    path = parts[1].decode()

            # Check health
            if path == "/healthz":
                status = b"HTTP/1.1 200 OK\r\n\r\nok"
            elif path == "/readyz":
                if self._running and self._controller:
                    status = b"HTTP/1.1 200 OK\r\n\r\nready"
                else:
                    status = b"HTTP/1.1 503 Service Unavailable\r\n\r\nnot ready"
            else:
                status = b"HTTP/1.1 404 Not Found\r\n\r\nnot found"

            writer.write(status)
            await writer.drain()
            writer.close()

        self._health_server = await asyncio.start_server(
            handle_health,
            "0.0.0.0",
            self.config.health_check_port,
        )

        logger.info(f"Health server started on port {self.config.health_check_port}")

    async def _start_metrics_server(self) -> None:
        """بدء خادم المقاييس"""
        async def handle_metrics(reader, writer):
            request = await reader.read(1024)

            # Generate Prometheus metrics
            metrics = self._generate_metrics()

            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain; version=0.0.4\r\n\r\n"
            ) + metrics.encode()

            writer.write(response)
            await writer.drain()
            writer.close()

        self._metrics_server = await asyncio.start_server(
            handle_metrics,
            "0.0.0.0",
            self.config.metrics_port,
        )

        logger.info(f"Metrics server started on port {self.config.metrics_port}")

    def _generate_metrics(self) -> str:
        """توليد مقاييس Prometheus"""
        lines = []

        # Operator info
        lines.append(
            '# HELP operator_info Operator information'
        )
        lines.append(
            '# TYPE operator_info gauge'
        )
        lines.append(
            f'operator_info{{version="1.0.0"}} 1'
        )

        # Uptime
        if self._started_at:
            uptime = (datetime.utcnow() - self._started_at).total_seconds()
            lines.append(
                '# HELP operator_uptime_seconds Operator uptime in seconds'
            )
            lines.append(
                '# TYPE operator_uptime_seconds counter'
            )
            lines.append(
                f'operator_uptime_seconds {uptime}'
            )

        # Controller metrics
        controller_status = self._controller.get_status()

        lines.append(
            '# HELP controller_reconcile_total Total number of reconciliations'
        )
        lines.append(
            '# TYPE controller_reconcile_total counter'
        )
        lines.append(
            f'controller_reconcile_total {controller_status["reconcile_count"]}'
        )

        lines.append(
            '# HELP controller_reconcile_errors_total Total reconciliation errors'
        )
        lines.append(
            '# TYPE controller_reconcile_errors_total counter'
        )
        lines.append(
            f'controller_reconcile_errors_total {controller_status["reconcile_errors"]}'
        )

        lines.append(
            '# HELP controller_queue_size Current reconcile queue size'
        )
        lines.append(
            '# TYPE controller_queue_size gauge'
        )
        lines.append(
            f'controller_queue_size {controller_status["queue_size"]}'
        )

        return "\n".join(lines)

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """الحصول على حالة المشغّل"""
        return {
            "running": self._running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "uptime_seconds": (datetime.utcnow() - self._started_at).total_seconds()
                if self._started_at else 0,
            "config": self.config.to_dict(),
            "controller": self._controller.get_status(),
        }


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """نقطة دخول CLI"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Distributed Cluster Kubernetes Operator"
    )
    parser.add_argument(
        "--kubeconfig",
        help="Path to kubeconfig file",
    )
    parser.add_argument(
        "--health-port",
        type=int,
        default=8081,
        help="Health check port",
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=8080,
        help="Metrics port",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create config
    config = OperatorConfig(
        health_check_port=args.health_port,
        metrics_port=args.metrics_port,
        log_level=args.log_level,
    )

    # Run operator
    operator = ClusterOperator(
        config=config,
        kubeconfig=args.kubeconfig,
    )

    await operator.run()


if __name__ == "__main__":
    asyncio.run(main())
