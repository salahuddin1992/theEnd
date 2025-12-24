"""
Observability Module - وحدة المراقبة
=====================================

مراقبة وتتبع النظام:
- Structured Logging
- Metrics Collection
- Distributed Tracing
- Health Checks
- Alerting
- System Collectors
"""

from distributed_cluster.observability.logging import (
    LogContext,
    LogLevel,
    StructuredLogger,
    log_context,
    get_logger,
    RotatingFileHandler,
    TimedRotatingFileHandler,
    LogCleaner,
    setup_logging,
)

from distributed_cluster.observability.metrics import (
    MetricsCollector,
    MetricType,
    MetricValue,
    Histogram,
)

from distributed_cluster.observability.health import (
    HealthCheck,
    HealthChecker,
    HealthReport,
    HealthStatus,
    Alert,
    AlertManager,
    AlertRule,
    AlertSeverity,
    AlertState,
    NotificationChannel,
    LogChannel,
    WebhookChannel,
    SlackChannel,
    create_standard_alert_rules,
)

from distributed_cluster.observability.prometheus import (
    PrometheusMetric,
    Counter,
    Gauge,
    Histogram as PrometheusHistogram,
    Summary,
    PrometheusRegistry,
    NebulaMetrics,
    PrometheusMiddleware,
    create_metrics_endpoint,
)

from distributed_cluster.observability.tracing import (
    Span,
    SpanEvent,
    SpanKind,
    SpanLink,
    SpanStatus,
    SpanExporter,
    ConsoleSpanExporter,
    OTLPSpanExporter,
    JaegerSpanExporter,
    Tracer,
    traced,
    get_tracer,
    set_tracer,
)

from distributed_cluster.observability.collectors import (
    CPUMetrics,
    MemoryMetrics,
    DiskMetrics,
    NetworkMetrics,
    GPUMetrics,
    ProcessMetrics,
    SystemCollector,
    MetricsReporter,
    PrometheusSystemCollector,
)

__all__ = [
    # Logging
    "LogContext",
    "LogLevel",
    "StructuredLogger",
    "log_context",
    "get_logger",
    "RotatingFileHandler",
    "TimedRotatingFileHandler",
    "LogCleaner",
    "setup_logging",
    # Metrics
    "MetricsCollector",
    "MetricType",
    "MetricValue",
    "Histogram",
    # Health & Alerts
    "HealthCheck",
    "HealthChecker",
    "HealthReport",
    "HealthStatus",
    "Alert",
    "AlertManager",
    "AlertRule",
    "AlertSeverity",
    "AlertState",
    "NotificationChannel",
    "LogChannel",
    "WebhookChannel",
    "SlackChannel",
    "create_standard_alert_rules",
    # Prometheus
    "PrometheusMetric",
    "Counter",
    "Gauge",
    "PrometheusHistogram",
    "Summary",
    "PrometheusRegistry",
    "NebulaMetrics",
    "PrometheusMiddleware",
    "create_metrics_endpoint",
    # Tracing
    "Span",
    "SpanEvent",
    "SpanKind",
    "SpanLink",
    "SpanStatus",
    "SpanExporter",
    "ConsoleSpanExporter",
    "OTLPSpanExporter",
    "JaegerSpanExporter",
    "Tracer",
    "traced",
    "get_tracer",
    "set_tracer",
    # System Collectors
    "CPUMetrics",
    "MemoryMetrics",
    "DiskMetrics",
    "NetworkMetrics",
    "GPUMetrics",
    "ProcessMetrics",
    "SystemCollector",
    "MetricsReporter",
    "PrometheusSystemCollector",
]
