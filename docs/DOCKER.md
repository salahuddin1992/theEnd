# Docker Guide

Guide to running NebulaCompute with Docker.

## Table of Contents

- [Quick Start](#quick-start)
- [Docker Images](#docker-images)
- [Docker Compose](#docker-compose)
- [Configuration](#configuration)
- [Networking](#networking)
- [Volumes](#volumes)
- [GPU Support](#gpu-support)
- [Production Deployment](#production-deployment)

## Quick Start

### Pull Images

```bash
# Latest version
docker pull ghcr.io/salahuddin1992/theend:latest

# Specific version
docker pull ghcr.io/salahuddin1992/theend:0.1.0
```

### Run Master

```bash
docker run -d \
  --name nebula-master \
  -p 8000:8000 \
  -v nebula-data:/app/data \
  ghcr.io/salahuddin1992/theend:latest master
```

### Run Worker

```bash
docker run -d \
  --name nebula-worker \
  -e MASTER_URL=http://nebula-master:8000 \
  --link nebula-master \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/salahuddin1992/theend:latest worker
```

## Docker Images

### Available Images

| Image | Description |
|-------|-------------|
| `theend:latest` | Default multi-purpose image |
| `theend:master` | Optimized for master node |
| `theend:worker` | Optimized for worker node |

### Image Tags

| Tag | Description |
|-----|-------------|
| `latest` | Latest stable release |
| `0.1.0` | Specific version |
| `main` | Development build |
| `sha-xxxxx` | Specific commit |

### Building Images

```bash
# Build default image
docker build -t nebulacompute:local .

# Build master image
docker build -f Dockerfile.master -t nebulacompute-master:local .

# Build worker image
docker build -f Dockerfile.worker -t nebulacompute-worker:local .
```

## Docker Compose

### Basic Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  master:
    image: ghcr.io/salahuddin1992/theend:latest
    command: master --host 0.0.0.0
    ports:
      - "8000:8000"
    volumes:
      - nebula-data:/app/data
    environment:
      - NEBULA_LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  worker:
    image: ghcr.io/salahuddin1992/theend:latest
    command: worker --master http://master:8000
    depends_on:
      - master
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - MASTER_URL=http://master:8000
    deploy:
      replicas: 2

volumes:
  nebula-data:
```

### Development Setup

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  master:
    build: .
    command: master --host 0.0.0.0 --reload
    ports:
      - "8000:8000"
    volumes:
      - ./src:/app/src
      - ./data:/app/data
    environment:
      - NEBULA_LOG_LEVEL=DEBUG
      - NEBULA_ENV=development

  worker:
    build: .
    command: worker --master http://master:8000
    depends_on:
      - master
    volumes:
      - ./src:/app/src
      - /var/run/docker.sock:/var/run/docker.sock
```

### Production Setup

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  master:
    image: ghcr.io/salahuddin1992/theend:0.1.0
    command: master --host 0.0.0.0
    ports:
      - "8000:8000"
    volumes:
      - nebula-data:/app/data
      - ./config.prod.yaml:/app/config.yaml:ro
    environment:
      - NEBULA_ENV=production
      - NEBULA_DATABASE_TYPE=postgresql
      - NEBULA_DB_HOST=postgres
      - NEBULA_DB_PASSWORD=${DB_PASSWORD}
      - NEBULA_JWT_SECRET=${JWT_SECRET}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G

  worker:
    image: ghcr.io/salahuddin1992/theend:0.1.0
    command: worker --master http://master:8000
    depends_on:
      master:
        condition: service_healthy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - worker-jobs:/app/jobs
    environment:
      - MASTER_URL=http://master:8000
    restart: unless-stopped
    deploy:
      replicas: 5
      resources:
        limits:
          cpus: '8'
          memory: 16G

  postgres:
    image: postgres:15
    volumes:
      - postgres-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_USER=nebula
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=nebulacompute
    restart: unless-stopped

  redis:
    image: redis:7
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  nebula-data:
  worker-jobs:
  postgres-data:
  redis-data:
```

### High Availability Setup

```yaml
# docker-compose.ha.yml
version: '3.8'

services:
  master-1:
    image: ghcr.io/salahuddin1992/theend:latest
    command: master --host 0.0.0.0
    environment:
      - NEBULA_HA_ENABLED=true
      - NEBULA_HA_NODE_ID=master-1
      - NEBULA_REDIS_HOST=redis
    depends_on:
      - redis

  master-2:
    image: ghcr.io/salahuddin1992/theend:latest
    command: master --host 0.0.0.0
    environment:
      - NEBULA_HA_ENABLED=true
      - NEBULA_HA_NODE_ID=master-2
      - NEBULA_REDIS_HOST=redis
    depends_on:
      - redis

  nginx:
    image: nginx:latest
    ports:
      - "8000:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - master-1
      - master-2

  redis:
    image: redis:7
    volumes:
      - redis-data:/data

volumes:
  redis-data:
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEBULA_LOG_LEVEL` | Log level | INFO |
| `NEBULA_ENV` | Environment | production |
| `MASTER_URL` | Master URL (worker) | - |
| `NEBULA_DATABASE_TYPE` | Database type | sqlite |
| `NEBULA_DB_HOST` | Database host | localhost |
| `NEBULA_DB_PASSWORD` | Database password | - |
| `NEBULA_JWT_SECRET` | JWT secret key | - |
| `NEBULA_REDIS_HOST` | Redis host | - |

### Config File Mount

```bash
docker run -d \
  --name nebula-master \
  -v ./config.yaml:/app/config.yaml:ro \
  ghcr.io/salahuddin1992/theend:latest master --config /app/config.yaml
```

## Networking

### Bridge Network

```bash
# Create network
docker network create nebula-net

# Run master
docker run -d \
  --name nebula-master \
  --network nebula-net \
  -p 8000:8000 \
  ghcr.io/salahuddin1992/theend:latest master

# Run worker
docker run -d \
  --name nebula-worker \
  --network nebula-net \
  ghcr.io/salahuddin1992/theend:latest worker --master http://nebula-master:8000
```

### Host Network

```bash
# For better performance
docker run -d \
  --name nebula-master \
  --network host \
  ghcr.io/salahuddin1992/theend:latest master --host 0.0.0.0 --port 8000
```

## Volumes

### Data Persistence

```bash
# Create volumes
docker volume create nebula-data
docker volume create nebula-jobs

# Mount volumes
docker run -d \
  --name nebula-master \
  -v nebula-data:/app/data \
  ghcr.io/salahuddin1992/theend:latest master
```

### Docker Socket

```bash
# Allow worker to run Docker jobs
docker run -d \
  --name nebula-worker \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/salahuddin1992/theend:latest worker
```

## GPU Support

### NVIDIA GPU

```bash
# Install nvidia-container-toolkit first
# Then run with --gpus flag
docker run -d \
  --name nebula-gpu-worker \
  --gpus all \
  -e MASTER_URL=http://master:8000 \
  ghcr.io/salahuddin1992/theend:latest worker
```

### Docker Compose GPU

```yaml
services:
  gpu-worker:
    image: ghcr.io/salahuddin1992/theend:latest
    command: worker --master http://master:8000
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

## Production Deployment

### Security Checklist

- [ ] Use specific image tags, not `latest`
- [ ] Set resource limits
- [ ] Use secrets for sensitive data
- [ ] Enable health checks
- [ ] Configure restart policies
- [ ] Use read-only mounts where possible
- [ ] Run as non-root user

### Example Secure Deployment

```yaml
services:
  master:
    image: ghcr.io/salahuddin1992/theend:0.1.0
    user: "1000:1000"
    read_only: true
    security_opt:
      - no-new-privileges:true
    tmpfs:
      - /tmp
    secrets:
      - jwt_secret
      - db_password
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G

secrets:
  jwt_secret:
    external: true
  db_password:
    external: true
```

### Monitoring with Docker

```yaml
services:
  prometheus:
    image: prom/prometheus:v2.45.0
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:10.0.0
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
```

## See Also

- [Kubernetes Guide](KUBERNETES.md)
- [Configuration](CONFIGURATION.md)
- [Production Deployment](PRODUCTION_DEPLOYMENT.md)
