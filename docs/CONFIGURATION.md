# Configuration Guide

Complete reference for configuring NebulaCompute.

## Table of Contents

- [Configuration Methods](#configuration-methods)
- [Master Configuration](#master-configuration)
- [Worker Configuration](#worker-configuration)
- [Database Configuration](#database-configuration)
- [Security Configuration](#security-configuration)
- [Logging Configuration](#logging-configuration)
- [Monitoring Configuration](#monitoring-configuration)
- [Environment Variables](#environment-variables)

## Configuration Methods

NebulaCompute can be configured through:

1. **Configuration file** (YAML/JSON)
2. **Environment variables**
3. **Command-line arguments**

Priority order (highest to lowest):
1. Command-line arguments
2. Environment variables
3. Configuration file
4. Default values

### Configuration File

```bash
# Use default location
nebula master start  # Looks for config.yaml

# Specify custom file
nebula master start --config /path/to/config.yaml
```

## Master Configuration

### Basic Settings

```yaml
master:
  # Network settings
  host: "0.0.0.0"           # Listen address
  port: 8000                 # Listen port

  # Cluster settings
  cluster_name: "default"    # Cluster identifier
  node_id: "master-1"        # Unique node ID

  # Performance
  max_workers: 1000          # Maximum workers
  max_jobs: 10000            # Maximum concurrent jobs
  job_history_days: 30       # Job history retention

  # Timeouts
  worker_timeout: 60         # Worker heartbeat timeout (seconds)
  job_timeout_default: 3600  # Default job timeout (seconds)

  # Features
  enable_dashboard: true     # Web dashboard
  enable_api_docs: true      # Swagger UI
  enable_metrics: true       # Prometheus metrics
```

### Scheduler Settings

```yaml
scheduler:
  # Policy: first_fit, best_fit, round_robin, priority, gang
  policy: "best_fit"

  # Queue settings
  max_queue_size: 10000
  priority_levels: 5

  # Fairness
  enable_fair_share: true
  fair_share_window: 3600    # seconds

  # Gang scheduling
  gang_timeout: 300          # seconds to wait for all tasks

  # Resource settings
  oversubscription_cpu: 1.0  # CPU oversubscription ratio
  oversubscription_mem: 1.0  # Memory oversubscription ratio
```

### High Availability

```yaml
ha:
  enabled: true
  mode: "active-passive"     # or "active-active"

  # Redis for state coordination
  redis:
    host: "redis.example.com"
    port: 6379
    password: "${REDIS_PASSWORD}"
    db: 0

  # Leader election
  election_timeout: 10       # seconds
  heartbeat_interval: 3      # seconds
```

## Worker Configuration

### Basic Settings

```yaml
worker:
  # Connection
  master_url: "http://master:8000"

  # Identity
  worker_id: ""              # Auto-generated if empty
  hostname: ""               # Auto-detected if empty

  # Tags and labels
  tags:
    - "cpu"
    - "docker"
    - "gpu"
  labels:
    zone: "us-east-1"
    tier: "compute"
    environment: "production"

  # Heartbeat
  heartbeat_interval: 10     # seconds

  # Job settings
  max_concurrent_jobs: 4
  job_workspace: "/var/nebula/jobs"
```

### Resource Settings

```yaml
resources:
  # Auto-detect or override
  cpu_cores: 0               # 0 = auto-detect
  memory_mb: 0               # 0 = auto-detect
  gpu_count: 0               # 0 = auto-detect

  # Reservations (keep for system)
  reserved_cpu: 1
  reserved_memory_mb: 1024

  # GPU settings
  gpu_memory_fraction: 0.9   # Fraction of GPU memory to use
```

### Docker Settings

```yaml
docker:
  enabled: true
  socket: "/var/run/docker.sock"

  # Default image
  default_image: "python:3.11-slim"

  # Network
  network_mode: "bridge"

  # Resource limits
  memory_limit: "8g"
  cpu_limit: "4"

  # Security
  privileged: false
  capabilities: []

  # Volumes
  volumes:
    - "/data:/data:ro"
```

## Database Configuration

### SQLite (Default)

```yaml
database:
  type: "sqlite"
  path: "data/cluster.db"

  # Connection pool
  pool_size: 5
  max_overflow: 10
```

### PostgreSQL

```yaml
database:
  type: "postgresql"
  host: "postgres.example.com"
  port: 5432
  database: "nebulacompute"
  username: "${DB_USER}"
  password: "${DB_PASSWORD}"

  # SSL
  ssl_mode: "require"
  ssl_ca: "/path/to/ca.crt"

  # Connection pool
  pool_size: 20
  max_overflow: 40
  pool_timeout: 30
```

### Redis (Caching/HA)

```yaml
redis:
  enabled: true
  host: "redis.example.com"
  port: 6379
  password: "${REDIS_PASSWORD}"
  db: 0

  # Connection pool
  max_connections: 50

  # Cluster mode
  cluster: false
  # cluster_nodes:
  #   - "redis-1:6379"
  #   - "redis-2:6379"
  #   - "redis-3:6379"
```

## Security Configuration

### Authentication

```yaml
security:
  enabled: true

  # JWT settings
  secret_key: "${JWT_SECRET}"
  algorithm: "HS256"
  token_expiry_hours: 24
  refresh_token_expiry_days: 7

  # Enrollment
  enrollment_mode: "manual"  # auto_approve, manual, disabled

  # Password policy
  min_password_length: 12
  require_uppercase: true
  require_numbers: true
  require_special: true
```

### TLS/SSL

```yaml
tls:
  enabled: true
  cert_file: "/path/to/server.crt"
  key_file: "/path/to/server.key"
  ca_file: "/path/to/ca.crt"

  # Client verification
  verify_client: false
  client_ca_file: "/path/to/client-ca.crt"

  # Protocols
  min_version: "TLSv1.2"
  ciphers: "ECDHE+AESGCM:DHE+AESGCM"
```

### Authorization

```yaml
authorization:
  enabled: true

  # Role-based access
  default_role: "user"

  roles:
    admin:
      - "*"
    operator:
      - "jobs:*"
      - "workers:read"
    user:
      - "jobs:create"
      - "jobs:read:own"
```

## Logging Configuration

```yaml
logging:
  level: "INFO"              # DEBUG, INFO, WARNING, ERROR
  format: "json"             # json, text

  # File logging
  file:
    enabled: true
    path: "/var/log/nebula/nebula.log"
    max_size_mb: 100
    max_files: 10

  # Structured logging
  include_timestamp: true
  include_caller: true

  # Log filtering
  exclude_paths:
    - "/health"
    - "/metrics"
```

## Monitoring Configuration

### Prometheus Metrics

```yaml
metrics:
  enabled: true
  path: "/metrics"

  # Custom labels
  labels:
    environment: "production"
    cluster: "us-east"
```

### OpenTelemetry

```yaml
telemetry:
  enabled: true

  # Tracing
  tracing:
    enabled: true
    exporter: "otlp"
    endpoint: "http://collector:4317"
    sample_rate: 0.1

  # Metrics
  metrics:
    enabled: true
    exporter: "prometheus"
```

### Health Checks

```yaml
health:
  # Liveness probe
  liveness:
    path: "/health/live"
    interval: 10

  # Readiness probe
  readiness:
    path: "/health/ready"
    interval: 5
```

## Environment Variables

All configuration options can be set via environment variables:

```bash
# Master settings
export NEBULA_MASTER_HOST="0.0.0.0"
export NEBULA_MASTER_PORT="8000"

# Worker settings
export NEBULA_WORKER_MASTER_URL="http://master:8000"

# Database
export NEBULA_DATABASE_TYPE="postgresql"
export NEBULA_DATABASE_HOST="postgres.example.com"
export NEBULA_DB_PASSWORD="secret"

# Security
export NEBULA_SECURITY_ENABLED="true"
export NEBULA_JWT_SECRET="your-secret-key"

# Logging
export NEBULA_LOG_LEVEL="INFO"
export NEBULA_LOG_FORMAT="json"
```

## Complete Example

```yaml
# config.yaml - Production configuration
master:
  host: "0.0.0.0"
  port: 8000
  cluster_name: "production"
  max_workers: 500
  enable_dashboard: true

scheduler:
  policy: "best_fit"
  enable_fair_share: true

database:
  type: "postgresql"
  host: "${DB_HOST}"
  database: "nebulacompute"
  username: "${DB_USER}"
  password: "${DB_PASSWORD}"

redis:
  enabled: true
  host: "${REDIS_HOST}"
  password: "${REDIS_PASSWORD}"

security:
  enabled: true
  secret_key: "${JWT_SECRET}"
  enrollment_mode: "manual"

tls:
  enabled: true
  cert_file: "/etc/nebula/tls/server.crt"
  key_file: "/etc/nebula/tls/server.key"

logging:
  level: "INFO"
  format: "json"

metrics:
  enabled: true

telemetry:
  tracing:
    enabled: true
    endpoint: "${OTEL_ENDPOINT}"
```

## See Also

- [Installation Guide](INSTALLATION.md)
- [Security Guide](SECURITY.md)
- [Production Deployment](PRODUCTION_DEPLOYMENT.md)
