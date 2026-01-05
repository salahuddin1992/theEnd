# Installation Guide

This guide covers all installation methods for NebulaCompute distributed computing system.

## Table of Contents

- [Requirements](#requirements)
- [Quick Install](#quick-install)
- [Installation Methods](#installation-methods)
  - [pip Install](#pip-install)
  - [From Source](#from-source)
  - [Docker](#docker)
  - [Kubernetes](#kubernetes)
- [Post-Installation](#post-installation)
- [Troubleshooting](#troubleshooting)

## Requirements

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| Memory | 4 GB | 8+ GB |
| Storage | 10 GB | 50+ GB SSD |
| Network | 100 Mbps | 1 Gbps |

### Software Requirements

- **Python**: 3.10, 3.11, 3.12, or 3.13
- **Operating System**: Linux, macOS, or Windows 10/11
- **Docker**: 20.10+ (optional, for container jobs)
- **Node.js**: 20+ (for frontend development)

### GPU Support (Optional)

- NVIDIA GPU with CUDA 11.0+
- NVIDIA Driver 450+
- nvidia-docker2 (for containerized GPU jobs)

## Quick Install

### Using pip (Recommended)

```bash
# Install from PyPI
pip install distributed-cluster

# Verify installation
nebula --version
```

### Using Docker

```bash
# Pull the latest image
docker pull ghcr.io/salahuddin1992/theend:latest

# Run master node
docker run -d -p 8000:8000 ghcr.io/salahuddin1992/theend:latest master
```

## Installation Methods

### pip Install

#### Basic Installation

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install package
pip install distributed-cluster
```

#### Installation with Optional Dependencies

```bash
# Install with PostgreSQL support
pip install distributed-cluster[postgres]

# Install with Redis support
pip install distributed-cluster[redis]

# Install with S3/MinIO support
pip install distributed-cluster[s3]

# Install with all optional features
pip install distributed-cluster[all]

# Install development dependencies
pip install distributed-cluster[dev]

# Install desktop GUI
pip install distributed-cluster[desktop]
```

### From Source

#### Clone Repository

```bash
git clone https://github.com/salahuddin1992/theEnd.git
cd theEnd
```

#### Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Install pre-commit hooks (optional)
pre-commit install
```

#### Build from Source

```bash
# Build wheel package
pip install build
python -m build

# Install built package
pip install dist/distributed_cluster-*.whl
```

### Docker

#### Using Docker Compose

```bash
# Clone repository
git clone https://github.com/salahuddin1992/theEnd.git
cd theEnd

# Start with docker-compose (development)
docker-compose up -d

# Start with production configuration
docker-compose -f docker-compose.prod.yml up -d

# Start with high-availability setup
docker-compose -f docker-compose.ha.yml up -d
```

#### Building Custom Image

```bash
# Build default image
docker build -t nebulacompute:local .

# Build master node image
docker build -f Dockerfile.master -t nebulacompute-master:local .

# Build worker node image
docker build -f Dockerfile.worker -t nebulacompute-worker:local .
```

#### Running Containers

```bash
# Run master node
docker run -d \
  --name nebula-master \
  -p 8000:8000 \
  -v nebula-data:/app/data \
  nebulacompute:local master --host 0.0.0.0

# Run worker node
docker run -d \
  --name nebula-worker \
  --link nebula-master \
  -e MASTER_URL=http://nebula-master:8000 \
  nebulacompute:local worker --master http://nebula-master:8000

# Run with GPU support
docker run -d \
  --name nebula-gpu-worker \
  --gpus all \
  --link nebula-master \
  -e MASTER_URL=http://nebula-master:8000 \
  nebulacompute:local worker --master http://nebula-master:8000
```

### Kubernetes

#### Using kubectl

```bash
# Apply namespace and configmap
kubectl apply -f deploy/kubernetes/namespace.yaml
kubectl apply -f deploy/kubernetes/configmap.yaml

# Deploy master
kubectl apply -f deploy/kubernetes/master-deployment.yaml

# Deploy workers
kubectl apply -f deploy/kubernetes/worker-deployment.yaml

# (Optional) Deploy GPU workers
kubectl apply -f deploy/kubernetes/worker-gpu-deployment.yaml

# Apply ingress
kubectl apply -f deploy/kubernetes/ingress.yaml

# Apply autoscaling
kubectl apply -f deploy/kubernetes/hpa.yaml
```

#### Using Helm

```bash
# Add Helm repository
helm repo add nebulacompute https://charts.nebulacompute.io
helm repo update

# Install with default values
helm install nebula nebulacompute/distributed-cluster

# Install with custom values
helm install nebula nebulacompute/distributed-cluster \
  --set master.replicas=3 \
  --set worker.replicas=10 \
  --set persistence.enabled=true

# Install from local chart
helm install nebula ./deploy/helm/distributed-cluster
```

## Post-Installation

### Verify Installation

```bash
# Check CLI version
nebula --version

# Check system health
nebula health

# Start master (if not using Docker/K8s)
nebula master start

# Start worker
nebula worker start --master http://localhost:8000

# Submit test job
nebula job submit "echo 'Hello NebulaCompute!'"
```

### Configuration

Create a configuration file:

```bash
# Copy example configuration
cp config.example.yaml config.yaml

# Edit configuration
nano config.yaml
```

Key configuration options:

```yaml
master:
  host: "0.0.0.0"
  port: 8000

worker:
  master_url: "http://localhost:8000"
  tags: ["cpu", "docker"]

database:
  type: "sqlite"  # or "postgresql"
  path: "data/cluster.db"

security:
  enabled: true
  secret_key: "your-secret-key"
```

### Enable Services (Linux)

```bash
# Copy systemd service files
sudo cp deploy/systemd/nebula-master.service /etc/systemd/system/
sudo cp deploy/systemd/nebula-worker.service /etc/systemd/system/

# Enable and start services
sudo systemctl enable nebula-master
sudo systemctl start nebula-master

sudo systemctl enable nebula-worker
sudo systemctl start nebula-worker
```

## Troubleshooting

### Common Issues

#### Port Already in Use

```bash
# Check what's using port 8000
lsof -i :8000

# Use different port
nebula master start --port 8001
```

#### Permission Denied

```bash
# Run with appropriate permissions
sudo nebula master start

# Or use non-privileged port
nebula master start --port 8080
```

#### Docker Socket Access

```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Restart session or run
newgrp docker
```

#### GPU Not Detected

```bash
# Verify NVIDIA driver
nvidia-smi

# Install nvidia-container-toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Getting Help

- Check logs: `nebula logs --tail 100`
- Health check: `nebula health`
- Documentation: https://docs.nebulacompute.io
- Issues: https://github.com/salahuddin1992/theEnd/issues

## Next Steps

- [Quick Start Guide](QUICKSTART.md)
- [Configuration Guide](CONFIGURATION.md)
- [Security Setup](SECURITY.md)
- [Production Deployment](PRODUCTION_DEPLOYMENT.md)
