"""
Dashboard Server - خادم لوحة المراقبة
=====================================

Dashboard HTTP Server
---------------------

This module provides the HTTP server for the dashboard.

يوفر هذا الملف خادم HTTP للوحة المراقبة.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from distributed_cluster.dashboard.alerts import AlertManager
from distributed_cluster.dashboard.health import HealthChecker
from distributed_cluster.dashboard.metrics import MetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class DashboardConfig:
    """
    إعدادات لوحة المراقبة
    Dashboard configuration
    """
    host: str = "0.0.0.0"
    port: int = 8080
    static_dir: Optional[str] = None
    enable_cors: bool = True
    api_prefix: str = "/api"
    metrics_path: str = "/metrics"
    health_path: str = "/health"


class DashboardServer:
    """
    خادم لوحة المراقبة
    Dashboard Server

    يوفر واجهة HTTP للوحة المراقبة.
    Provides HTTP interface for the dashboard.
    """

    def __init__(
        self,
        config: Optional[DashboardConfig] = None,
        metrics: Optional[MetricsCollector] = None,
        health: Optional[HealthChecker] = None,
        alerts: Optional[AlertManager] = None,
    ):
        """
        تهيئة الخادم

        Args:
            config: إعدادات الخادم
            metrics: جامع المقاييس
            health: فاحص الصحة
            alerts: مدير التنبيهات
        """
        self.config = config or DashboardConfig()
        self.metrics = metrics or MetricsCollector()
        self.health = health or HealthChecker()
        self.alerts = alerts or AlertManager()

        # State
        self._running = False
        self._server = None
        self._started_at: Optional[datetime] = None

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء الخادم"""
        # Start components
        await self.metrics.start()
        await self.health.start()
        await self.alerts.start()

        # Start HTTP server
        self._server = await asyncio.start_server(
            self._handle_request,
            self.config.host,
            self.config.port,
        )

        self._running = True
        self._started_at = datetime.now(timezone.utc)

        logger.info(
            f"Dashboard server started at http://{self.config.host}:{self.config.port}"
        )

    async def stop(self) -> None:
        """إيقاف الخادم"""
        self._running = False

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        await self.alerts.stop()
        await self.health.stop()
        await self.metrics.stop()

        logger.info("Dashboard server stopped")

    async def run(self) -> None:
        """تشغيل الخادم حتى الإيقاف"""
        await self.start()

        try:
            await self._server.serve_forever()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    # =========================================================================
    # Request Handling
    # =========================================================================

    async def _handle_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """معالجة طلب HTTP"""
        try:
            # Read request
            request_data = await asyncio.wait_for(
                reader.read(8192),
                timeout=30.0,
            )

            if not request_data:
                return

            # Parse request
            request_text = request_data.decode("utf-8", errors="ignore")
            lines = request_text.split("\r\n")

            if not lines:
                return

            # Parse request line
            parts = lines[0].split(" ")
            if len(parts) < 2:
                return

            method = parts[0]
            path = parts[1]

            # Route request
            response = await self._route_request(method, path)

            # Send response
            writer.write(response.encode())
            await writer.drain()

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.error(f"Request handling error: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _route_request(self, method: str, path: str) -> str:
        """توجيه الطلب"""
        api_prefix = self.config.api_prefix

        # CORS headers
        cors_headers = ""
        if self.config.enable_cors:
            cors_headers = (
                "Access-Control-Allow-Origin: *\r\n"
                "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                "Access-Control-Allow-Headers: Content-Type\r\n"
            )

        # Handle OPTIONS (CORS preflight)
        if method == "OPTIONS":
            return f"HTTP/1.1 200 OK\r\n{cors_headers}\r\n"

        # Route to handlers
        handlers = {
            self.config.metrics_path: self._handle_metrics,
            self.config.health_path: self._handle_health,
            f"{api_prefix}/status": self._handle_status,
            f"{api_prefix}/metrics": self._handle_api_metrics,
            f"{api_prefix}/health": self._handle_api_health,
            f"{api_prefix}/alerts": self._handle_api_alerts,
            f"{api_prefix}/workers": self._handle_api_workers,
            f"{api_prefix}/jobs": self._handle_api_jobs,
        }

        handler = handlers.get(path)
        if handler:
            try:
                content = await handler()
                return self._build_response(200, content, cors_headers)
            except Exception as e:
                logger.error(f"Handler error for {path}: {e}")
                return self._build_response(
                    500,
                    {"error": str(e)},
                    cors_headers,
                )

        # Static files
        if self.config.static_dir:
            static_response = await self._handle_static(path)
            if static_response:
                return static_response

        # 404
        return self._build_response(
            404,
            {"error": "Not found"},
            cors_headers,
        )

    def _build_response(
        self,
        status: int,
        content: Any,
        extra_headers: str = "",
    ) -> str:
        """بناء استجابة HTTP"""
        status_text = {
            200: "OK",
            404: "Not Found",
            500: "Internal Server Error",
        }.get(status, "Unknown")

        if isinstance(content, dict) or isinstance(content, list):
            body = json.dumps(content, indent=2, default=str)
            content_type = "application/json"
        else:
            body = str(content)
            content_type = "text/plain"

        return (
            f"HTTP/1.1 {status} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"{extra_headers}"
            f"\r\n"
            f"{body}"
        )

    # =========================================================================
    # Handlers
    # =========================================================================

    async def _handle_metrics(self) -> str:
        """معالج المقاييس (Prometheus format)"""
        return self.metrics.export_prometheus()

    async def _handle_health(self) -> dict[str, Any]:
        """معالج الصحة"""
        return {
            "status": "healthy" if self.health.is_healthy() else "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _handle_status(self) -> dict[str, Any]:
        """معالج الحالة العامة"""
        return {
            "status": "running",
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "uptime_seconds": (
                (datetime.now(timezone.utc) - self._started_at).total_seconds()
                if self._started_at else 0
            ),
            "health": self.health.get_status(),
            "alerts": self.alerts.get_status(),
        }

    async def _handle_api_metrics(self) -> dict[str, Any]:
        """معالج API المقاييس"""
        return self.metrics.export_json()

    async def _handle_api_health(self) -> dict[str, Any]:
        """معالج API الصحة"""
        return self.health.get_status()

    async def _handle_api_alerts(self) -> dict[str, Any]:
        """معالج API التنبيهات"""
        return self.alerts.get_status()

    async def _handle_api_workers(self) -> dict[str, Any]:
        """معالج API العمال"""
        # This would integrate with the cluster manager
        return {
            "workers": [],
            "total": 0,
            "healthy": 0,
        }

    async def _handle_api_jobs(self) -> dict[str, Any]:
        """معالج API المهام"""
        # This would integrate with the job scheduler
        return {
            "jobs": [],
            "pending": 0,
            "running": 0,
            "completed": 0,
        }

    async def _handle_static(self, path: str) -> Optional[str]:
        """معالج الملفات الثابتة"""
        if not self.config.static_dir:
            return None

        # Security: prevent path traversal
        if ".." in path:
            return None

        file_path = Path(self.config.static_dir) / path.lstrip("/")

        if not file_path.exists() or not file_path.is_file():
            return None

        # Determine content type
        content_type = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
        }.get(file_path.suffix, "application/octet-stream")

        content = file_path.read_bytes()

        return (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(content)}\r\n"
            f"\r\n"
        ) + content.decode("utf-8", errors="replace")

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """الحصول على حالة الخادم"""
        return {
            "running": self._running,
            "host": self.config.host,
            "port": self.config.port,
            "started_at": self._started_at.isoformat() if self._started_at else None,
        }


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """نقطة دخول CLI"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Distributed Cluster Dashboard"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind")
    parser.add_argument("--static-dir", help="Static files directory")

    args = parser.parse_args()

    config = DashboardConfig(
        host=args.host,
        port=args.port,
        static_dir=args.static_dir,
    )

    server = DashboardServer(config=config)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
