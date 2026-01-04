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

# Advanced Metrics
from distributed_cluster.observability.advanced_metrics import (
    BusinessMetric,
    BusinessMetricsCollector,
    MetricsAggregator,
    RequestMetrics,
    RequestMetricsCollector,
    SlidingWindowCounter,
    SLODefinition,
    SLOMonitor,
    SLOStatus,
    SLOType,
    create_default_slos,
    create_metrics_middleware,
    get_metrics_aggregator,
    track_calls,
    track_latency,
)
from distributed_cluster.observability.cluster_monitoring import (
    CentralizedLogger,
    # Metrics Registry
    ClusterMetricsRegistry,
    # Main Monitor
    ClusterMonitor,
    ConsoleLogHandler,
    FileLogHandler,
    LogHandler,
    create_monitoring_middleware,
    # FastAPI Integration
    create_monitoring_routes,
    get_cluster_monitor,
    setup_cluster_monitoring,
    shutdown_cluster_monitoring,
)

# Cluster Monitoring
from distributed_cluster.observability.cluster_monitoring import (
    # Log Levels
    LogLevel as ClusterLogLevel,
)
from distributed_cluster.observability.cluster_monitoring import (
    # Logging
    LogRecord as ClusterLogRecord,
)
from distributed_cluster.observability.cluster_monitoring import (
    # Metric Types
    MetricType as ClusterMetricType,
)
from distributed_cluster.observability.cluster_monitoring import (
    # Prometheus Metrics
    PrometheusCounter as ClusterCounter,
)
from distributed_cluster.observability.cluster_monitoring import (
    PrometheusGauge as ClusterGauge,
)
from distributed_cluster.observability.cluster_monitoring import (
    PrometheusHistogram as ClusterHistogram,
)
from distributed_cluster.observability.cluster_monitoring import (
    PrometheusSummary as ClusterSummary,
)
from distributed_cluster.observability.collectors import (
    CPUMetrics,
    DiskMetrics,
    GPUMetrics,
    MemoryMetrics,
    MetricsReporter,
    NetworkMetrics,
    ProcessMetrics,
    PrometheusSystemCollector,
    SystemCollector,
)

# Comprehensive Health Checks
from distributed_cluster.observability.comprehensive_health import (
    CompositeHealthCheck,
    CPUHealthCheck,
    DependencyChainCheck,
    DependencyConfig,
    DependencyType,
    DiskHealthCheck,
    DNSHealthCheck,
    HealthCheckManager,
    HealthCheckResult,
    HTTPHealthCheck,
    LivenessProbe,
    MemoryHealthCheck,
    PostgreSQLHealthCheck,
    ReadinessProbe,
    RedisHealthCheck,
    SSLCertificateCheck,
    TCPHealthCheck,
    create_health_routes,
    setup_default_checks,
)
from distributed_cluster.observability.comprehensive_health import (
    HealthCheck as ComprehensiveHealthCheck,
)
from distributed_cluster.observability.comprehensive_health import (
    HealthStatus as ComprehensiveHealthStatus,
)

# Enhanced Logging
from distributed_cluster.observability.enhanced_logging import (
    AsyncFileHandler,
    ConsoleHandler,
    CorrelationContext,
    EnhancedLogger,
    LogAggregator,
    LoggerFactory,
    LogRecord,
    create_logging_middleware,
    generate_correlation_id,
    get_correlation_id,
    get_trace_context,
    log_execution,
    set_correlation_id,
    set_trace_context,
    with_correlation,
)
from distributed_cluster.observability.enhanced_logging import (
    LogLevel as EnhancedLogLevel,
)
from distributed_cluster.observability.enhanced_logging import (
    get_logger as get_enhanced_logger,
)
from distributed_cluster.observability.enhanced_logging import (
    setup_logging as setup_enhanced_logging,
)
from distributed_cluster.observability.health import (
    Alert,
    AlertManager,
    AlertRule,
    AlertSeverity,
    AlertState,
    HealthCheck,
    HealthChecker,
    HealthReport,
    HealthStatus,
    LogChannel,
    NotificationChannel,
    SlackChannel,
    WebhookChannel,
    create_standard_alert_rules,
)
from distributed_cluster.observability.logging import (
    LogCleaner,
    LogContext,
    LogLevel,
    RotatingFileHandler,
    StructuredLogger,
    TimedRotatingFileHandler,
    get_logger,
    log_context,
    setup_logging,
)
from distributed_cluster.observability.metrics import (
    Histogram,
    MetricsCollector,
    MetricType,
    MetricValue,
)
from distributed_cluster.observability.prometheus import (
    Counter,
    Gauge,
    NebulaMetrics,
    PrometheusMetric,
    PrometheusMiddleware,
    PrometheusRegistry,
    Summary,
    create_metrics_endpoint,
)
from distributed_cluster.observability.prometheus import (
    Histogram as PrometheusHistogram,
)
from distributed_cluster.observability.tracing import (
    ConsoleSpanExporter,
    JaegerSpanExporter,
    OTLPSpanExporter,
    Span,
    SpanEvent,
    SpanExporter,
    SpanKind,
    SpanLink,
    SpanStatus,
    Tracer,
    get_tracer,
    set_tracer,
    traced,
)

# Unified Manager
from distributed_cluster.observability.unified_manager import (
    ObservabilityConfig,
    ObservabilityStatus,
    SystemStatus,
    UnifiedObservabilityManager,
    create_observability_middleware,
    create_observability_routes,
    get_observability_manager,
    setup_observability,
    shutdown_observability,
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
    # Advanced Metrics
    "MetricsAggregator",
    "RequestMetrics",
    "RequestMetricsCollector",
    "SLODefinition",
    "SLOMonitor",
    "SLOStatus",
    "SLOType",
    "BusinessMetric",
    "BusinessMetricsCollector",
    "SlidingWindowCounter",
    "create_default_slos",
    "create_metrics_middleware",
    "get_metrics_aggregator",
    "track_latency",
    "track_calls",
    # Enhanced Logging
    "EnhancedLogger",
    "LoggerFactory",
    "LogAggregator",
    "ConsoleHandler",
    "AsyncFileHandler",
    "LogRecord",
    "CorrelationContext",
    "generate_correlation_id",
    "get_correlation_id",
    "set_correlation_id",
    "get_trace_context",
    "set_trace_context",
    "with_correlation",
    "log_execution",
    "create_logging_middleware",
    "EnhancedLogLevel",
    "setup_enhanced_logging",
    "get_enhanced_logger",
    # Comprehensive Health
    "HealthCheckManager",
    "HealthCheckResult",
    "ComprehensiveHealthStatus",
    "DependencyType",
    "DependencyConfig",
    "ComprehensiveHealthCheck",
    "TCPHealthCheck",
    "HTTPHealthCheck",
    "DNSHealthCheck",
    "SSLCertificateCheck",
    "PostgreSQLHealthCheck",
    "RedisHealthCheck",
    "CPUHealthCheck",
    "MemoryHealthCheck",
    "DiskHealthCheck",
    "CompositeHealthCheck",
    "DependencyChainCheck",
    "ReadinessProbe",
    "LivenessProbe",
    "create_health_routes",
    "setup_default_checks",
    # Unified Manager
    "UnifiedObservabilityManager",
    "ObservabilityConfig",
    "ObservabilityStatus",
    "SystemStatus",
    "create_observability_routes",
    "create_observability_middleware",
    "get_observability_manager",
    "setup_observability",
    "shutdown_observability",
    # Cluster Monitoring
    "ClusterLogLevel",
    "ClusterMetricType",
    "ClusterCounter",
    "ClusterGauge",
    "ClusterHistogram",
    "ClusterSummary",
    "ClusterLogRecord",
    "LogHandler",
    "ConsoleLogHandler",
    "FileLogHandler",
    "CentralizedLogger",
    "ClusterMetricsRegistry",
    "ClusterMonitor",
    "get_cluster_monitor",
    "setup_cluster_monitoring",
    "shutdown_cluster_monitoring",
    "create_monitoring_routes",
    "create_monitoring_middleware",
]
