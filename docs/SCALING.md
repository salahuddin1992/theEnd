# Scaling Guide

Guide to scaling NebulaCompute for different workloads.

## Table of Contents

- [Scaling Overview](#scaling-overview)
- [Horizontal Scaling](#horizontal-scaling)
- [Vertical Scaling](#vertical-scaling)
- [Database Scaling](#database-scaling)
- [High Availability](#high-availability)
- [Performance Tuning](#performance-tuning)
- [Capacity Planning](#capacity-planning)

## Scaling Overview

### Scaling Dimensions

```
                    ┌─────────────────┐
                    │   Load Balancer │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   Master 1    │   │   Master 2    │   │   Master 3    │
│   (Active)    │   │   (Standby)   │   │   (Standby)   │
└───────────────┘   └───────────────┘   └───────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   Worker 1    │   │   Worker 2    │   │   Worker N    │
└───────────────┘   └───────────────┘   └───────────────┘
```

### Scaling Factors

| Component | Scaling Method | Bottleneck |
|-----------|---------------|------------|
| Workers | Horizontal | Network bandwidth |
| Master | Vertical/HA | CPU, Memory |
| Database | Vertical/Replicas | I/O, Connections |
| Queue | Redis Cluster | Memory |

## Horizontal Scaling

### Adding Workers

```bash
# Add more workers dynamically
nebula worker start --master http://master:8000

# Using Docker
docker run -d \
  --name worker-$RANDOM \
  -e MASTER_URL=http://master:8000 \
  nebulacompute:latest worker

# Using Kubernetes
kubectl scale deployment nebula-worker --replicas=50
```

### Auto-Scaling Workers

#### Kubernetes HPA

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: nebula-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: nebula-worker
  minReplicas: 5
  maxReplicas: 100
  metrics:
    - type: External
      external:
        metric:
          name: nebula_jobs_pending
        target:
          type: AverageValue
          averageValue: 10  # 10 pending jobs per worker
```

#### Custom Auto-Scaler

```python
# autoscaler.py
import time
from nebulacompute import Client

client = Client("http://master:8000")

while True:
    status = client.get_cluster_status()
    pending = status['jobs']['pending']
    workers = status['workers']['active']

    # Target: 5 pending jobs per worker
    target_workers = max(5, pending // 5)

    if target_workers > workers:
        scale_up(target_workers - workers)
    elif target_workers < workers * 0.7:  # Scale down at 70%
        scale_down(workers - target_workers)

    time.sleep(60)
```

### Worker Pools

```yaml
# config.yaml
worker_pools:
  cpu-pool:
    min_workers: 10
    max_workers: 100
    tags: ["cpu"]
    resources:
      cpu: 8
      memory: 16384

  gpu-pool:
    min_workers: 2
    max_workers: 20
    tags: ["gpu", "nvidia"]
    resources:
      cpu: 4
      memory: 32768
      gpu: 1

  high-memory-pool:
    min_workers: 5
    max_workers: 25
    tags: ["high-memory"]
    resources:
      cpu: 4
      memory: 65536
```

## Vertical Scaling

### Master Node Sizing

| Cluster Size | CPU | Memory | Disk |
|-------------|-----|--------|------|
| Small (<50 workers) | 4 cores | 8GB | 50GB SSD |
| Medium (50-200 workers) | 8 cores | 16GB | 100GB SSD |
| Large (200-500 workers) | 16 cores | 32GB | 200GB SSD |
| XLarge (500+ workers) | 32 cores | 64GB | 500GB NVMe |

### Worker Node Sizing

| Job Type | CPU | Memory | GPU |
|----------|-----|--------|-----|
| Light | 2 cores | 4GB | - |
| Standard | 8 cores | 16GB | - |
| Compute | 16 cores | 32GB | - |
| GPU | 8 cores | 32GB | 1-4x V100 |
| Memory | 8 cores | 128GB | - |

### Resource Configuration

```yaml
# config.yaml for large deployment
master:
  max_workers: 1000
  max_jobs: 100000
  job_history_days: 7

  # Connection pool
  max_connections: 5000
  connection_timeout: 30

  # Threading
  workers: 8  # Uvicorn workers
  threads: 4  # Per worker

scheduler:
  policy: "first_fit"  # Faster for scale
  batch_size: 100  # Process jobs in batches
```

## Database Scaling

### PostgreSQL for Scale

```yaml
# config.yaml
database:
  type: postgresql
  host: postgres-primary
  database: nebulacompute
  username: nebula
  password: ${DB_PASSWORD}

  # Connection pooling
  pool_size: 50
  max_overflow: 100
  pool_timeout: 30

  # Read replicas
  read_replicas:
    - host: postgres-replica-1
    - host: postgres-replica-2
```

### Database Optimization

```sql
-- Create indexes for common queries
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created ON jobs(created_at);
CREATE INDEX idx_jobs_worker ON jobs(worker_id);
CREATE INDEX idx_workers_status ON workers(status);

-- Partitioning for large tables
CREATE TABLE jobs (
    job_id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    ...
) PARTITION BY RANGE (created_at);

CREATE TABLE jobs_2024_01 PARTITION OF jobs
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

### Redis for Caching

```yaml
# config.yaml
redis:
  enabled: true
  mode: cluster  # For large scale

  cluster_nodes:
    - redis-1:6379
    - redis-2:6379
    - redis-3:6379

  # Cache settings
  job_cache_ttl: 300  # 5 minutes
  worker_cache_ttl: 60  # 1 minute
```

## High Availability

### Active-Passive Setup

```yaml
# master-1 (primary)
ha:
  enabled: true
  mode: active-passive
  node_id: master-1
  redis:
    host: redis
    port: 6379
  election_timeout: 10
  heartbeat_interval: 3
```

```yaml
# master-2 (standby)
ha:
  enabled: true
  mode: active-passive
  node_id: master-2
  redis:
    host: redis
    port: 6379
  election_timeout: 10
  heartbeat_interval: 3
```

### Load Balancer Configuration

```nginx
# nginx.conf
upstream nebula_masters {
    server master-1:8000 max_fails=3 fail_timeout=30s;
    server master-2:8000 backup;
}

server {
    listen 80;
    location / {
        proxy_pass http://nebula_masters;
        proxy_next_upstream error timeout invalid_header http_500;
    }
}
```

### Kubernetes HA

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: nebula-master
spec:
  replicas: 3
  serviceName: nebula-master
  selector:
    matchLabels:
      app: nebula-master
  template:
    spec:
      containers:
        - name: master
          image: nebulacompute:latest
          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: HA_ENABLED
              value: "true"
            - name: HA_NODE_ID
              value: "$(POD_NAME)"
```

## Performance Tuning

### Scheduler Optimization

```yaml
scheduler:
  # Use faster policy at scale
  policy: first_fit

  # Batch processing
  batch_size: 100
  batch_interval_ms: 50

  # Reduce lock contention
  sharding_enabled: true
  shard_count: 4
```

### Network Optimization

```yaml
network:
  # Connection pooling
  max_connections: 1000
  keepalive: true
  keepalive_timeout: 60

  # Compression
  compression: true
  compression_level: 6

  # Timeouts
  connect_timeout: 5
  read_timeout: 30
```

### Memory Optimization

```yaml
memory:
  # Job result caching
  result_cache_size: 10000
  result_cache_ttl: 3600

  # Worker state caching
  worker_cache_size: 1000

  # Cleanup intervals
  cleanup_interval: 300
  max_memory_percent: 80
```

## Capacity Planning

### Sizing Calculator

```
Required Workers = (Jobs per Hour × Avg Job Duration) / (3600 × Worker Efficiency)

Example:
- Jobs per hour: 10,000
- Avg job duration: 60 seconds
- Worker efficiency: 0.8 (80% utilization)

Workers = (10,000 × 60) / (3600 × 0.8) = 208 workers
```

### Resource Planning

```
Master Resources:
- CPU: 1 core per 100 workers
- Memory: 100MB per 1000 jobs in history
- Disk: 1GB per 100,000 job records

Worker Resources:
- Based on job requirements
- Add 20% overhead for agent
- Consider peak vs average
```

### Growth Planning

| Phase | Workers | Jobs/Day | Master | Database |
|-------|---------|----------|--------|----------|
| MVP | 10 | 10K | 4C/8GB | SQLite |
| Growth | 50 | 100K | 8C/16GB | PostgreSQL |
| Scale | 200 | 1M | 16C/32GB | PG + Replicas |
| Enterprise | 1000+ | 10M+ | 32C/64GB HA | PG Cluster |

### Bottleneck Indicators

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| High schedule latency | Scheduler CPU | Faster policy, more master CPU |
| Job queue growing | Not enough workers | Add workers |
| API timeout | Master overloaded | Scale master, add caching |
| Worker disconnects | Network issues | Check network, increase timeouts |
| DB slow queries | Database overload | Add indexes, read replicas |

## See Also

- [Configuration Guide](CONFIGURATION.md)
- [Monitoring Guide](MONITORING.md)
- [Production Deployment](PRODUCTION_DEPLOYMENT.md)
