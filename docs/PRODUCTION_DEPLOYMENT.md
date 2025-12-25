# Production Deployment Guide
# دليل النشر الإنتاجي

This guide covers deploying NebulaCompute in production environments.

يغطي هذا الدليل نشر NebulaCompute في بيئات الإنتاج.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Architecture Overview](#architecture-overview)
3. [Kubernetes Deployment](#kubernetes-deployment)
4. [Docker Compose Deployment](#docker-compose-deployment)
5. [High Availability Setup](#high-availability-setup)
6. [Security Configuration](#security-configuration)
7. [Monitoring & Observability](#monitoring--observability)
8. [Backup & Disaster Recovery](#backup--disaster-recovery)
9. [Performance Tuning](#performance-tuning)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| Memory | 8 GB | 16+ GB |
| Disk | 50 GB SSD | 200+ GB NVMe |
| Network | 1 Gbps | 10 Gbps |

### Software Requirements

- Python 3.10+
- Docker 24.0+
- Kubernetes 1.28+ (for K8s deployment)
- PostgreSQL 15+ (for production database)
- Redis 7.0+ (for caching)

---

## Architecture Overview

```
                    ┌─────────────────┐
                    │   Load Balancer │
                    │   (nginx/HAProxy)│
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
    ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
    │   Master 1  │   │   Master 2  │   │   Master 3  │
    │  (Primary)  │   │  (Standby)  │   │  (Standby)  │
    └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
           │                 │                 │
           └─────────────────┼─────────────────┘
                             │
                    ┌────────▼────────┐
                    │    PostgreSQL   │
                    │   (Primary/HA)  │
                    └────────┬────────┘
                             │
    ┌────────────────────────┼────────────────────────┐
    │         │              │              │         │
┌───▼───┐ ┌───▼───┐     ┌───▼───┐     ┌───▼───┐ ┌───▼───┐
│Worker1│ │Worker2│ ... │WorkerN│ ... │GPU W1 │ │GPU W2 │
└───────┘ └───────┘     └───────┘     └───────┘ └───────┘
```

---

## Kubernetes Deployment

### Step 1: Create Namespace

```bash
kubectl create namespace nebulacompute
kubectl config set-context --current --namespace=nebulacompute
```

### Step 2: Create Secrets

```bash
# Database credentials
kubectl create secret generic db-credentials \
  --from-literal=username=nebula \
  --from-literal=password=<secure-password>

# JWT secret
kubectl create secret generic jwt-secret \
  --from-literal=secret=<256-bit-random-string>

# API keys
kubectl create secret generic api-keys \
  --from-literal=admin-key=<admin-api-key>
```

### Step 3: Deploy with Helm

```bash
# Add Helm repository (if available)
# helm repo add nebulacompute https://charts.nebulacompute.io

# Or install from local chart
helm install nebulacompute ./deploy/helm/nebulacompute \
  --namespace nebulacompute \
  --values ./deploy/helm/nebulacompute/values-production.yaml
```

### Step 4: Verify Deployment

```bash
kubectl get pods -n nebulacompute
kubectl get services -n nebulacompute
kubectl logs -f deployment/nebulacompute-master -n nebulacompute
```

### Example values-production.yaml

```yaml
# Production values for NebulaCompute Helm chart
replicaCount:
  master: 3
  worker: 10

image:
  repository: nebulacompute/master
  tag: latest
  pullPolicy: Always

resources:
  master:
    requests:
      cpu: "2"
      memory: "4Gi"
    limits:
      cpu: "4"
      memory: "8Gi"
  worker:
    requests:
      cpu: "4"
      memory: "8Gi"
    limits:
      cpu: "8"
      memory: "16Gi"

persistence:
  enabled: true
  storageClass: "fast-ssd"
  size: 100Gi

database:
  type: postgresql
  host: postgres-ha.database.svc
  port: 5432
  name: nebulacompute
  existingSecret: db-credentials

redis:
  enabled: true
  cluster:
    enabled: true
    replicas: 3

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: compute.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: nebulacompute-tls
      hosts:
        - compute.example.com

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 50
  targetCPUUtilizationPercentage: 70

monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
  grafanaDashboard:
    enabled: true
```

---

## Docker Compose Deployment

### Production docker-compose.yml

```bash
cd /opt/nebulacompute
docker-compose -f docker-compose.prod.yml up -d
```

### Environment Variables

Create `.env` file:

```bash
# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=nebulacompute
DB_USER=nebula
DB_PASSWORD=<secure-password>

# Redis
REDIS_URL=redis://redis:6379

# Security
JWT_SECRET=<256-bit-random-string>
ADMIN_API_KEY=<admin-api-key>

# TLS
TLS_ENABLED=true
TLS_CERT_FILE=/certs/server.crt
TLS_KEY_FILE=/certs/server.key

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Metrics
METRICS_ENABLED=true
METRICS_PORT=9090
```

---

## High Availability Setup

### Master HA Configuration

Edit `config.yaml`:

```yaml
ha:
  enabled: true
  mode: active-standby

  # Cluster membership
  cluster:
    nodes:
      - id: master-1
        host: master-1.internal
        port: 8080
      - id: master-2
        host: master-2.internal
        port: 8080
      - id: master-3
        host: master-3.internal
        port: 8080

  # Leader election
  election:
    timeout_seconds: 10
    heartbeat_interval_seconds: 2

  # State synchronization
  sync:
    enabled: true
    interval_seconds: 5
    batch_size: 100
```

### Database HA

For PostgreSQL:

```bash
# Using Patroni for PostgreSQL HA
docker-compose -f docker-compose.patroni.yml up -d
```

---

## Security Configuration

### TLS/SSL Setup

```yaml
# config.yaml
http:
  tls:
    enabled: true
    cert_file: /etc/nebulacompute/certs/server.crt
    key_file: /etc/nebulacompute/certs/server.key
    min_version: TLS1.2
    cipher_suites:
      - TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
      - TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
```

### Authentication

```yaml
security:
  auth:
    enabled: true
    jwt:
      secret_env: JWT_SECRET
      expiry_hours: 24
      refresh_enabled: true

  rbac:
    enabled: true
    default_role: viewer

  rate_limiting:
    enabled: true
    requests_per_minute: 1000
    burst: 100
```

### Network Policies

```yaml
# Kubernetes NetworkPolicy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: nebulacompute-master
spec:
  podSelector:
    matchLabels:
      app: nebulacompute-master
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: nebulacompute-worker
      ports:
        - port: 8080
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - port: 5432
```

---

## Monitoring & Observability

### Prometheus Metrics

Metrics are exposed at `/metrics` endpoint:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'nebulacompute-master'
    static_configs:
      - targets: ['master:9090']

  - job_name: 'nebulacompute-workers'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: nebulacompute-worker
        action: keep
```

### Grafana Dashboard

Import dashboards from `deploy/grafana/`:

- `cluster-overview.json` - Cluster health and metrics
- `job-metrics.json` - Job execution metrics
- `worker-metrics.json` - Worker performance
- `gpu-metrics.json` - GPU utilization

### Logging

```yaml
# config.yaml
logging:
  level: INFO
  format: json
  output:
    - type: stdout
    - type: file
      path: /var/log/nebulacompute/master.log
      rotate:
        max_size_mb: 100
        max_files: 10
    - type: elasticsearch
      hosts:
        - http://elasticsearch:9200
      index: nebulacompute-logs
```

### Alerting

```yaml
# alertmanager rules
groups:
  - name: nebulacompute
    rules:
      - alert: MasterDown
        expr: up{job="nebulacompute-master"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Master node is down"

      - alert: HighJobFailureRate
        expr: rate(jobs_failed_total[5m]) / rate(jobs_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High job failure rate (>10%)"

      - alert: WorkerOffline
        expr: worker_status{status="offline"} > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Worker node offline"
```

---

## Backup & Disaster Recovery

### Database Backup

```bash
# Automated backup script
#!/bin/bash
BACKUP_DIR=/backups/postgres
DATE=$(date +%Y%m%d_%H%M%S)

pg_dump -h postgres -U nebula nebulacompute | \
  gzip > $BACKUP_DIR/nebulacompute_$DATE.sql.gz

# Upload to S3
aws s3 cp $BACKUP_DIR/nebulacompute_$DATE.sql.gz \
  s3://nebulacompute-backups/postgres/

# Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
```

### Disaster Recovery Procedure

1. **Restore Database**
```bash
gunzip -c backup.sql.gz | psql -h postgres -U nebula nebulacompute
```

2. **Restore Configuration**
```bash
kubectl apply -f backup/configmaps.yaml
kubectl apply -f backup/secrets.yaml
```

3. **Restart Services**
```bash
kubectl rollout restart deployment/nebulacompute-master
kubectl rollout restart daemonset/nebulacompute-worker
```

---

## Performance Tuning

### Master Optimization

```yaml
# config.yaml
scheduler:
  algorithm: balanced  # or: binpack, spread
  queue_size: 10000
  batch_size: 100
  scheduling_interval_ms: 100

database:
  pool:
    min_connections: 10
    max_connections: 100
    idle_timeout_seconds: 300

http:
  max_connections: 10000
  read_timeout_seconds: 30
  write_timeout_seconds: 60
```

### Worker Optimization

```yaml
# worker-config.yaml
worker:
  max_concurrent_jobs: 10
  heartbeat_interval_seconds: 5
  job_timeout_seconds: 3600

  resources:
    cpu_overcommit: 1.5
    memory_overcommit: 1.2

  container:
    runtime: docker  # or: containerd
    image_pull_policy: IfNotPresent
    cache_images: true
```

### GPU Optimization

```yaml
gpu:
  sharing:
    enabled: true
    mode: time_slicing  # or: mps, mig
    max_oversubscription: 1.5

  monitoring:
    interval_seconds: 5
    metrics:
      - utilization
      - memory
      - temperature
      - power
```

---

## Troubleshooting

### Common Issues

#### 1. Master Not Starting

```bash
# Check logs
kubectl logs deployment/nebulacompute-master

# Common causes:
# - Database connection failed
# - Port already in use
# - Missing configuration
```

#### 2. Workers Not Connecting

```bash
# Check worker logs
kubectl logs daemonset/nebulacompute-worker

# Verify network connectivity
kubectl exec -it worker-pod -- curl http://master:8080/health

# Check firewall rules
```

#### 3. Jobs Stuck in Pending

```bash
# Check scheduler status
curl http://master:8080/api/v1/scheduler/status

# Check available resources
curl http://master:8080/api/v1/workers/resources

# Check job queue
curl http://master:8080/api/v1/jobs?status=pending
```

#### 4. High Memory Usage

```bash
# Check memory metrics
kubectl top pods

# Adjust resource limits
kubectl patch deployment nebulacompute-master -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"master","resources":{"limits":{"memory":"8Gi"}}}]}}}}'
```

### Debug Mode

Enable debug logging:

```bash
# Environment variable
export LOG_LEVEL=DEBUG

# Or in config.yaml
logging:
  level: DEBUG
```

### Health Checks

```bash
# Master health
curl http://master:8080/health
curl http://master:8080/ready

# Worker health
curl http://worker:8080/health

# Cluster status
curl http://master:8080/api/v1/cluster/status
```

---

## Support

For issues and support:
- GitHub Issues: https://github.com/nebulacompute/nebulacompute/issues
- Documentation: https://docs.nebulacompute.io
