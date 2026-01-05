# Monitoring Guide

Comprehensive guide to monitoring NebulaCompute deployments.

## Table of Contents

- [Overview](#overview)
- [Metrics](#metrics)
- [Prometheus Integration](#prometheus-integration)
- [Grafana Dashboards](#grafana-dashboards)
- [Alerting](#alerting)
- [Logging](#logging)
- [Tracing](#tracing)
- [Health Checks](#health-checks)

## Overview

NebulaCompute provides multiple monitoring capabilities:

```
┌─────────────────────────────────────────────────────┐
│                  NebulaCompute                      │
├─────────────────────────────────────────────────────┤
│  Metrics      │  Logging      │  Tracing           │
│  (Prometheus) │  (Structured) │  (OpenTelemetry)   │
└───────┬───────┴───────┬───────┴───────┬────────────┘
        │               │               │
        ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Prometheus │ │    Loki     │ │   Jaeger    │
│  + Grafana  │ │ (optional)  │ │  (optional) │
└─────────────┘ └─────────────┘ └─────────────┘
```

## Metrics

### Available Metrics

#### Cluster Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `nebula_workers_total` | Gauge | Total registered workers |
| `nebula_workers_active` | Gauge | Workers with status READY/BUSY |
| `nebula_workers_offline` | Gauge | Workers offline |
| `nebula_jobs_total` | Counter | Total jobs submitted |
| `nebula_jobs_pending` | Gauge | Jobs in queue |
| `nebula_jobs_running` | Gauge | Currently running jobs |
| `nebula_jobs_completed_total` | Counter | Completed jobs |
| `nebula_jobs_failed_total` | Counter | Failed jobs |

#### Performance Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `nebula_schedule_duration_seconds` | Histogram | Time to schedule a job |
| `nebula_job_duration_seconds` | Histogram | Job execution time |
| `nebula_api_request_duration_seconds` | Histogram | API response time |
| `nebula_api_requests_total` | Counter | API requests by endpoint |

#### Resource Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `nebula_cluster_cpu_total` | Gauge | Total CPU cores |
| `nebula_cluster_cpu_available` | Gauge | Available CPU cores |
| `nebula_cluster_memory_total_bytes` | Gauge | Total memory |
| `nebula_cluster_memory_available_bytes` | Gauge | Available memory |
| `nebula_cluster_gpu_total` | Gauge | Total GPUs |
| `nebula_cluster_gpu_available` | Gauge | Available GPUs |

### Accessing Metrics

```bash
# View metrics endpoint
curl http://localhost:8000/metrics

# Sample output
# HELP nebula_workers_total Total registered workers
# TYPE nebula_workers_total gauge
nebula_workers_total 10

# HELP nebula_jobs_pending Jobs waiting to be scheduled
# TYPE nebula_jobs_pending gauge
nebula_jobs_pending 25
```

## Prometheus Integration

### Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'nebulacompute'
    static_configs:
      - targets: ['master:8000']
    metrics_path: /metrics
```

### Docker Compose Setup

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:v2.45.0
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus

  grafana:
    image: grafana/grafana:10.0.0
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

volumes:
  prometheus-data:
  grafana-data:
```

### Kubernetes Setup

```yaml
# servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: nebulacompute
spec:
  selector:
    matchLabels:
      app: nebulacompute
  endpoints:
    - port: http
      path: /metrics
      interval: 15s
```

## Grafana Dashboards

### Import Dashboard

1. Open Grafana (http://localhost:3000)
2. Go to Dashboards → Import
3. Import from JSON or ID

### Sample Dashboard JSON

```json
{
  "dashboard": {
    "title": "NebulaCompute Overview",
    "panels": [
      {
        "title": "Workers",
        "type": "stat",
        "targets": [
          {
            "expr": "nebula_workers_active",
            "legendFormat": "Active"
          }
        ]
      },
      {
        "title": "Jobs Queue",
        "type": "timeseries",
        "targets": [
          {
            "expr": "nebula_jobs_pending",
            "legendFormat": "Pending"
          },
          {
            "expr": "nebula_jobs_running",
            "legendFormat": "Running"
          }
        ]
      },
      {
        "title": "Job Throughput",
        "type": "timeseries",
        "targets": [
          {
            "expr": "rate(nebula_jobs_completed_total[5m])",
            "legendFormat": "Completed/s"
          }
        ]
      },
      {
        "title": "API Latency",
        "type": "heatmap",
        "targets": [
          {
            "expr": "histogram_quantile(0.99, sum(rate(nebula_api_request_duration_seconds_bucket[5m])) by (le))",
            "legendFormat": "p99"
          }
        ]
      }
    ]
  }
}
```

### Key Panels

1. **Cluster Overview**
   - Worker count (active/total)
   - Resource utilization (CPU/Memory/GPU)
   - Job queue depth

2. **Job Metrics**
   - Submission rate
   - Completion rate
   - Failure rate
   - Duration histogram

3. **Performance**
   - API latency percentiles
   - Scheduling time
   - Queue wait time

4. **Resources**
   - CPU utilization per worker
   - Memory utilization
   - GPU utilization

## Alerting

### Prometheus Alert Rules

```yaml
# alerts.yml
groups:
  - name: nebulacompute
    rules:
      - alert: HighJobFailureRate
        expr: rate(nebula_jobs_failed_total[5m]) / rate(nebula_jobs_completed_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High job failure rate"
          description: "Job failure rate is above 10%"

      - alert: NoActiveWorkers
        expr: nebula_workers_active == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "No active workers"
          description: "All workers are offline"

      - alert: JobQueueBacklog
        expr: nebula_jobs_pending > 1000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Large job queue backlog"
          description: "More than 1000 jobs pending"

      - alert: HighAPILatency
        expr: histogram_quantile(0.99, rate(nebula_api_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency"
          description: "P99 API latency exceeds 1 second"

      - alert: LowResourceAvailability
        expr: nebula_cluster_cpu_available / nebula_cluster_cpu_total < 0.1
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Low CPU availability"
          description: "Less than 10% CPU available"
```

### Alertmanager Configuration

```yaml
# alertmanager.yml
global:
  smtp_smarthost: 'smtp.example.com:587'
  smtp_from: 'alerts@nebulacompute.io'

route:
  group_by: ['alertname']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'email'
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'

receivers:
  - name: 'email'
    email_configs:
      - to: 'team@example.com'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '<key>'
```

## Logging

### Configuration

```yaml
# config.yaml
logging:
  level: INFO
  format: json

  file:
    enabled: true
    path: /var/log/nebula/nebula.log
    max_size_mb: 100
    max_files: 10
    compress: true

  # Structured logging fields
  include_timestamp: true
  include_caller: true
  include_request_id: true
```

### Log Format

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "message": "Job scheduled",
  "job_id": "job-abc123",
  "worker_id": "worker-xyz789",
  "duration_ms": 15,
  "request_id": "req-123456"
}
```

### Centralized Logging (Loki)

```yaml
# loki/promtail.yml
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: nebulacompute
    static_configs:
      - targets:
          - localhost
        labels:
          job: nebulacompute
          __path__: /var/log/nebula/*.log
```

### Log Queries (LogQL)

```logql
# All errors
{job="nebulacompute"} |= "ERROR"

# Job failures
{job="nebulacompute"} | json | level="ERROR" | message=~".*job.*failed.*"

# Slow API requests
{job="nebulacompute"} | json | duration_ms > 1000
```

## Tracing

### OpenTelemetry Configuration

```yaml
# config.yaml
telemetry:
  enabled: true

  tracing:
    enabled: true
    exporter: otlp
    endpoint: http://jaeger:4317
    sample_rate: 0.1  # Sample 10% of traces
```

### Jaeger Setup

```yaml
# docker-compose.tracing.yml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.50
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
    environment:
      - COLLECTOR_OTLP_ENABLED=true
```

### Viewing Traces

1. Open Jaeger UI (http://localhost:16686)
2. Select service "nebulacompute"
3. Search for traces by:
   - Job ID
   - Request ID
   - Duration
   - Status

## Health Checks

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `/health` | Basic health check |
| `/health/live` | Liveness probe |
| `/health/ready` | Readiness probe |

### Health Response

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "checks": {
    "database": "healthy",
    "workers": "healthy",
    "scheduler": "healthy"
  }
}
```

### Kubernetes Probes

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: master
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
```

### CLI Health Check

```bash
# Quick health check
nebula health

# Detailed status
nebula health --verbose

# JSON output
nebula health --json
```

## See Also

- [Configuration Guide](CONFIGURATION.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Scaling Guide](SCALING.md)
