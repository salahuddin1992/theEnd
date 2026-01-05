# Quick Start Guide

Get up and running with NebulaCompute in under 5 minutes.

## Prerequisites

- Python 3.10+ installed
- pip package manager
- Docker (optional, for container jobs)

## Step 1: Install NebulaCompute

```bash
pip install distributed-cluster
```

## Step 2: Start the Master Node

Open a terminal and run:

```bash
nebula master start
```

You should see:

```
INFO: NebulaCompute Master starting on http://0.0.0.0:8000
INFO: Dashboard available at http://localhost:8000
INFO: API docs at http://localhost:8000/docs
```

## Step 3: Start a Worker Node

Open a new terminal and run:

```bash
nebula worker start --master http://localhost:8000
```

You should see:

```
INFO: Worker registered with master
INFO: Worker ID: worker-abc123
INFO: Resources: 8 CPU cores, 16384 MB RAM
INFO: Ready to accept jobs
```

## Step 4: Submit Your First Job

Open a new terminal and submit a job:

```bash
nebula job submit "echo 'Hello from NebulaCompute!'"
```

Output:

```
Job submitted successfully
Job ID: job-xyz789
Status: pending
```

## Step 5: Check Job Status

```bash
nebula job status job-xyz789
```

Output:

```
Job: job-xyz789
Status: completed
Duration: 0.5s
Output: Hello from NebulaCompute!
```

## Step 6: Access the Dashboard

Open your browser and navigate to:

```
http://localhost:8000
```

You'll see:
- Cluster overview
- Worker status
- Job queue
- Real-time metrics

## Quick Examples

### Submit a Python Script

```bash
nebula job submit "python -c 'import sys; print(sys.version)'"
```

### Submit with Resource Requirements

```bash
nebula job submit \
  --cpu 4 \
  --memory 4096 \
  "python heavy_computation.py"
```

### Submit with GPU

```bash
nebula job submit \
  --gpu 1 \
  "python train_model.py"
```

### Submit Multiple Jobs

```bash
for i in {1..10}; do
  nebula job submit "echo 'Task $i'"
done
```

### List All Jobs

```bash
nebula job list
```

### List Workers

```bash
nebula worker list
```

### View Cluster Status

```bash
nebula status
```

## Docker Quick Start

If you prefer Docker:

```bash
# Start cluster
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f

# Submit job (inside container)
docker exec nebula-master nebula job submit "echo 'Hello!'"

# Stop cluster
docker-compose down
```

## Configuration File

Create `config.yaml` for custom settings:

```yaml
master:
  host: "0.0.0.0"
  port: 8000

worker:
  tags: ["cpu", "docker", "gpu"]
  max_jobs: 4

logging:
  level: INFO
```

Use with:

```bash
nebula master start --config config.yaml
```

## What's Next?

- **[Installation Guide](INSTALLATION.md)** - Detailed installation options
- **[Configuration Guide](CONFIGURATION.md)** - Full configuration reference
- **[Examples](EXAMPLES.md)** - More usage examples
- **[CLI Reference](CLI_REFERENCE.md)** - Complete CLI documentation
- **[API Reference](API_REFERENCE.md)** - REST API documentation

## Need Help?

- Documentation: https://docs.nebulacompute.io
- GitHub Issues: https://github.com/salahuddin1992/theEnd/issues
- Discussions: https://github.com/salahuddin1992/theEnd/discussions
