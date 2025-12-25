"""
Gateway Analytics - تحليلات البوابة
====================================

Request tracking, metrics collection, and analytics.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .gateway import GatewayRequest, GatewayResponse

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsConfig:
    """Analytics configuration."""
    enabled: bool = True

    # Logging
    log_requests: bool = True
    log_responses: bool = True
    log_headers: bool = False
    log_body: bool = False
    log_file: Optional[str] = None

    # Metrics
    collect_metrics: bool = True
    metrics_interval_seconds: int = 60
    metrics_retention_hours: int = 24

    # Sampling
    sample_rate: float = 1.0  # 1.0 = 100% of requests

    # Excluded paths
    exclude_paths: List[str] = field(default_factory=lambda: ["/health", "/ready", "/metrics"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "log_requests": self.log_requests,
            "collect_metrics": self.collect_metrics,
            "sample_rate": self.sample_rate,
        }


@dataclass
class RequestMetrics:
    """Metrics for a single request."""
    request_id: str
    timestamp: datetime
    method: str
    path: str
    status_code: int
    latency_ms: float

    # Details
    client_ip: str = ""
    user_agent: str = ""
    content_length: int = 0
    response_size: int = 0

    # Context
    route_id: Optional[str] = None
    upstream_url: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "latency_ms": round(self.latency_ms, 2),
            "client_ip": self.client_ip,
            "response_size": self.response_size,
            "error": self.error,
        }


@dataclass
class EndpointMetrics:
    """Aggregated metrics for an endpoint."""
    path: str
    method: str

    # Counts
    total_requests: int = 0
    successful_requests: int = 0
    client_errors: int = 0
    server_errors: int = 0

    # Latency
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0

    # Size
    total_request_size: int = 0
    total_response_size: int = 0

    # Time window
    window_start: datetime = field(default_factory=datetime.utcnow)
    window_end: Optional[datetime] = None

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.client_errors + self.server_errors) / self.total_requests

    def record(self, metrics: RequestMetrics) -> None:
        """Record a request."""
        self.total_requests += 1

        if 200 <= metrics.status_code < 400:
            self.successful_requests += 1
        elif 400 <= metrics.status_code < 500:
            self.client_errors += 1
        else:
            self.server_errors += 1

        self.total_latency_ms += metrics.latency_ms
        self.min_latency_ms = min(self.min_latency_ms, metrics.latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, metrics.latency_ms)

        self.total_request_size += metrics.content_length
        self.total_response_size += metrics.response_size

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "method": self.method,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "client_errors": self.client_errors,
            "server_errors": self.server_errors,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "min_latency_ms": round(self.min_latency_ms, 2) if self.min_latency_ms != float("inf") else 0,
            "max_latency_ms": round(self.max_latency_ms, 2),
            "success_rate": round(self.success_rate, 4),
            "error_rate": round(self.error_rate, 4),
        }


class RequestLogger:
    """
    Request Logger - مسجل الطلبات.

    Logs request/response details for analytics and debugging.
    """

    def __init__(self, config: Optional[AnalyticsConfig] = None):
        self.config = config or AnalyticsConfig()
        self._log_file = None

        if self.config.log_file:
            self._log_file = Path(self.config.log_file)
            self._log_file.parent.mkdir(parents=True, exist_ok=True)

    def _should_log(self, request: GatewayRequest) -> bool:
        """Check if request should be logged."""
        if not self.config.enabled:
            return False

        # Check excluded paths
        for path in self.config.exclude_paths:
            if request.path.startswith(path):
                return False

        # Check sample rate
        if self.config.sample_rate < 1.0:
            import random
            if random.random() > self.config.sample_rate:
                return False

        return True

    def log_request(self, request: GatewayRequest) -> None:
        """Log incoming request."""
        if not self._should_log(request) or not self.config.log_requests:
            return

        log_data = {
            "type": "request",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request.request_id,
            "method": request.method,
            "path": request.path,
            "client_ip": request.client_ip,
        }

        if self.config.log_headers:
            log_data["headers"] = dict(request.headers)

        self._write_log(log_data)

    def log_response(
        self,
        request: GatewayRequest,
        response: GatewayResponse,
        latency_ms: float,
    ) -> None:
        """Log outgoing response."""
        if not self._should_log(request) or not self.config.log_responses:
            return

        log_data = {
            "type": "response",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request.request_id,
            "method": request.method,
            "path": request.path,
            "status_code": response.status_code,
            "latency_ms": round(latency_ms, 2),
            "response_size": len(response.body),
        }

        if response.error:
            log_data["error"] = response.error

        self._write_log(log_data)

    def _write_log(self, data: Dict[str, Any]) -> None:
        """Write log entry."""
        log_line = json.dumps(data)

        if self._log_file:
            with open(self._log_file, "a") as f:
                f.write(log_line + "\n")
        else:
            logger.info(f"ACCESS: {log_line}")


class MetricsCollector:
    """
    Metrics Collector - جامع المقاييس.

    Collects and aggregates gateway metrics.

    Example:
        collector = MetricsCollector()

        # Record request
        collector.record(request, response, latency_ms)

        # Get metrics
        metrics = collector.get_metrics()
        endpoint_metrics = collector.get_endpoint_metrics("/api/users")
    """

    def __init__(self, config: Optional[AnalyticsConfig] = None):
        self.config = config or AnalyticsConfig()
        self._request_times: Dict[str, float] = {}
        self._endpoint_metrics: Dict[str, EndpointMetrics] = {}
        self._recent_requests: List[RequestMetrics] = []
        self._max_recent = 1000
        self._lock = asyncio.Lock()

        # Global metrics
        self._total_requests = 0
        self._total_latency_ms = 0.0
        self._status_counts: Dict[int, int] = defaultdict(int)
        self._start_time = datetime.utcnow()

    def start_request(self, request: GatewayRequest) -> None:
        """Mark request start time."""
        self._request_times[request.request_id] = time.time()

    async def record(
        self,
        request: GatewayRequest,
        response: GatewayResponse,
        latency_ms: Optional[float] = None,
    ) -> None:
        """Record request metrics."""
        if not self.config.collect_metrics:
            return

        # Calculate latency if not provided
        if latency_ms is None:
            start_time = self._request_times.pop(request.request_id, None)
            if start_time:
                latency_ms = (time.time() - start_time) * 1000
            else:
                latency_ms = 0.0
        else:
            self._request_times.pop(request.request_id, None)

        # Create metrics record
        metrics = RequestMetrics(
            request_id=request.request_id,
            timestamp=datetime.utcnow(),
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
            client_ip=request.client_ip,
            user_agent=request.get_header("user-agent"),
            content_length=request.content_length,
            response_size=len(response.body),
            route_id=request.route_id,
            error=response.error,
        )

        async with self._lock:
            # Update global metrics
            self._total_requests += 1
            self._total_latency_ms += latency_ms
            self._status_counts[response.status_code] += 1

            # Update endpoint metrics
            key = f"{request.method}:{request.path}"
            if key not in self._endpoint_metrics:
                self._endpoint_metrics[key] = EndpointMetrics(
                    path=request.path,
                    method=request.method,
                )
            self._endpoint_metrics[key].record(metrics)

            # Store recent requests
            self._recent_requests.append(metrics)
            if len(self._recent_requests) > self._max_recent:
                self._recent_requests = self._recent_requests[-self._max_recent:]

    def get_metrics(self) -> Dict[str, Any]:
        """Get global metrics."""
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        rps = self._total_requests / uptime if uptime > 0 else 0

        return {
            "total_requests": self._total_requests,
            "requests_per_second": round(rps, 2),
            "avg_latency_ms": round(
                self._total_latency_ms / self._total_requests
                if self._total_requests > 0 else 0,
                2
            ),
            "status_codes": dict(self._status_counts),
            "uptime_seconds": round(uptime, 2),
            "start_time": self._start_time.isoformat(),
        }

    def get_endpoint_metrics(self, path: Optional[str] = None) -> Dict[str, Any]:
        """Get endpoint-specific metrics."""
        if path:
            # Find matching endpoints
            results = {}
            for key, metrics in self._endpoint_metrics.items():
                if metrics.path == path or metrics.path.startswith(path):
                    results[key] = metrics.to_dict()
            return results
        else:
            return {
                key: metrics.to_dict()
                for key, metrics in self._endpoint_metrics.items()
            }

    def get_recent_requests(
        self,
        limit: int = 100,
        status_code: Optional[int] = None,
        path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent request metrics."""
        results = self._recent_requests[-limit:]

        if status_code:
            results = [r for r in results if r.status_code == status_code]

        if path:
            results = [r for r in results if r.path.startswith(path)]

        return [r.to_dict() for r in results]

    def get_error_summary(self) -> Dict[str, Any]:
        """Get error summary."""
        errors = [r for r in self._recent_requests if r.status_code >= 400]

        error_by_path: Dict[str, int] = defaultdict(int)
        error_by_status: Dict[int, int] = defaultdict(int)

        for r in errors:
            error_by_path[r.path] += 1
            error_by_status[r.status_code] += 1

        return {
            "total_errors": len(errors),
            "by_path": dict(error_by_path),
            "by_status": dict(error_by_status),
        }

    def get_latency_percentiles(self) -> Dict[str, float]:
        """Get latency percentiles."""
        if not self._recent_requests:
            return {"p50": 0, "p90": 0, "p95": 0, "p99": 0}

        latencies = sorted([r.latency_ms for r in self._recent_requests])
        n = len(latencies)

        return {
            "p50": round(latencies[int(n * 0.50)], 2),
            "p90": round(latencies[int(n * 0.90)], 2),
            "p95": round(latencies[int(n * 0.95)], 2),
            "p99": round(latencies[min(int(n * 0.99), n - 1)], 2),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._total_requests = 0
        self._total_latency_ms = 0.0
        self._status_counts.clear()
        self._endpoint_metrics.clear()
        self._recent_requests.clear()
        self._start_time = datetime.utcnow()

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []

        # Total requests
        lines.append(f"# HELP gateway_requests_total Total number of requests")
        lines.append(f"# TYPE gateway_requests_total counter")
        lines.append(f"gateway_requests_total {self._total_requests}")

        # Requests by status
        lines.append(f"# HELP gateway_requests_by_status Requests by status code")
        lines.append(f"# TYPE gateway_requests_by_status counter")
        for status, count in self._status_counts.items():
            lines.append(f'gateway_requests_by_status{{status="{status}"}} {count}')

        # Latency
        if self._total_requests > 0:
            avg_latency = self._total_latency_ms / self._total_requests
            lines.append(f"# HELP gateway_request_duration_ms Request duration")
            lines.append(f"# TYPE gateway_request_duration_ms gauge")
            lines.append(f"gateway_request_duration_ms {round(avg_latency, 2)}")

        # Percentiles
        percentiles = self.get_latency_percentiles()
        lines.append(f"# HELP gateway_request_duration_percentile Request duration percentiles")
        lines.append(f"# TYPE gateway_request_duration_percentile gauge")
        for p, v in percentiles.items():
            lines.append(f'gateway_request_duration_percentile{{quantile="{p}"}} {v}')

        return "\n".join(lines)
