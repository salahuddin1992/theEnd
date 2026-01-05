# Troubleshooting Guide

Solutions for common issues with NebulaCompute.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Master Node Issues](#master-node-issues)
- [Worker Node Issues](#worker-node-issues)
- [Job Issues](#job-issues)
- [Network Issues](#network-issues)
- [Database Issues](#database-issues)
- [Performance Issues](#performance-issues)
- [Docker Issues](#docker-issues)
- [GPU Issues](#gpu-issues)
- [Getting Help](#getting-help)

## Quick Diagnostics

### System Health Check

```bash
# Check overall health
nebula health

# Detailed diagnostics
nebula diagnose

# View logs
nebula logs --tail 100
nebula logs --level ERROR
```

### Common Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| `HEALTHY` | All systems operational | None |
| `DEGRADED` | Some issues detected | Check logs |
| `UNHEALTHY` | Critical issues | Immediate attention |

## Master Node Issues

### Master Won't Start

**Symptom**: Master fails to start or crashes immediately.

**Check 1**: Port already in use
```bash
# Check what's using port 8000
lsof -i :8000
netstat -tulpn | grep 8000

# Solution: Kill process or use different port
kill <pid>
# or
nebula master start --port 8001
```

**Check 2**: Configuration error
```bash
# Validate configuration
nebula config validate

# Check config file syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

**Check 3**: Permission denied
```bash
# Check file permissions
ls -la config.yaml data/

# Fix permissions
chmod 644 config.yaml
chmod 755 data/
```

### Master Not Accepting Connections

**Symptom**: Workers can't connect to master.

```bash
# Check master is listening
ss -tlnp | grep 8000

# Check firewall
sudo ufw status
sudo iptables -L

# Allow connections
sudo ufw allow 8000/tcp
```

### High Memory Usage

**Symptom**: Master consuming excessive memory.

```bash
# Check memory usage
nebula status --metrics

# Reduce job history
nebula admin cleanup --older-than 7d

# Configure lower limits
# config.yaml
master:
  max_jobs: 5000
  job_history_days: 7
```

## Worker Node Issues

### Worker Can't Connect to Master

**Symptom**: Worker fails to register with master.

**Check 1**: Network connectivity
```bash
# Test connectivity
curl http://master:8000/health
telnet master 8000
```

**Check 2**: DNS resolution
```bash
# Check DNS
nslookup master
dig master

# Use IP address instead
nebula worker start --master http://192.168.1.100:8000
```

**Check 3**: TLS/SSL issues
```bash
# Test TLS connection
openssl s_client -connect master:8000

# Skip TLS verification (not for production!)
nebula worker start --master https://master:8000 --insecure
```

### Worker Stuck in OFFLINE Status

**Symptom**: Worker shows as offline even though it's running.

```bash
# Check heartbeat
nebula worker status

# Restart worker
nebula worker restart

# Check for network issues
ping master
traceroute master
```

### Worker Resource Detection Failed

**Symptom**: Worker shows 0 CPUs or memory.

```bash
# Manual resource check
python -c "import psutil; print(psutil.cpu_count(), psutil.virtual_memory().total)"

# Override resources
nebula worker start --cpu 8 --memory 16384
```

## Job Issues

### Jobs Stuck in PENDING

**Symptom**: Jobs remain pending indefinitely.

**Check 1**: Available workers
```bash
nebula worker list
# Ensure workers have status READY
```

**Check 2**: Resource requirements
```bash
# Check job requirements vs available
nebula job info <job-id>
nebula worker list --show-resources

# Reduce requirements
nebula job submit --cpu 2 --memory 2048 "echo test"
```

**Check 3**: Scheduler issues
```bash
# Check scheduler logs
nebula logs --component scheduler

# Force reschedule
nebula admin reschedule
```

### Jobs Failing Immediately

**Symptom**: Jobs fail within seconds of starting.

```bash
# Check job output
nebula job logs <job-id>

# Check worker logs
nebula logs --worker <worker-id>

# Common causes:
# - Command not found
# - Missing dependencies
# - Permission denied
```

### Job Output Not Available

**Symptom**: Can't retrieve job output.

```bash
# Check job status
nebula job status <job-id>

# Check artifact storage
nebula admin check-storage

# Retrieve from worker directly
nebula job logs <job-id> --source worker
```

## Network Issues

### Connection Timeouts

**Symptom**: Frequent timeouts between components.

```bash
# Check network latency
ping master
mtr master

# Increase timeouts in config
# config.yaml
network:
  connect_timeout: 30
  read_timeout: 60
```

### WebSocket Connection Failures

**Symptom**: Real-time updates not working.

```bash
# Test WebSocket
wscat -c ws://master:8000/ws

# Check proxy configuration (nginx)
# nginx.conf
location /ws {
    proxy_pass http://master:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

## Database Issues

### Database Connection Failed

**Symptom**: Master can't connect to database.

```bash
# Test connection
psql -h db-host -U nebula -d nebulacompute

# Check PostgreSQL is running
systemctl status postgresql

# Check credentials
echo $NEBULA_DB_PASSWORD
```

### Database Migration Errors

**Symptom**: Schema migration fails.

```bash
# Check current version
nebula db version

# Run migrations manually
nebula db migrate

# Reset database (caution!)
nebula db reset --confirm
```

### Database Performance

**Symptom**: Slow database queries.

```bash
# Check slow queries
nebula db analyze

# Add indexes
nebula db optimize

# Vacuum (PostgreSQL)
vacuumdb -z nebulacompute
```

## Performance Issues

### High CPU Usage

**Symptom**: Master or worker at 100% CPU.

```bash
# Profile the process
py-spy record -o profile.svg --pid <pid>

# Check for runaway jobs
nebula job list --status running

# Kill problematic jobs
nebula job cancel <job-id>
```

### Slow Job Scheduling

**Symptom**: Jobs take long to be scheduled.

```bash
# Check scheduler metrics
nebula metrics | grep scheduler

# Switch to faster policy
# config.yaml
scheduler:
  policy: "first_fit"  # Instead of best_fit
```

### Memory Leaks

**Symptom**: Memory usage grows over time.

```bash
# Monitor memory
watch -n 5 'nebula status --metrics | grep memory'

# Check for leak
tracemalloc -o trace.log nebula master start

# Restart periodically (workaround)
0 */6 * * * systemctl restart nebula-master
```

## Docker Issues

### Docker Socket Permission Denied

**Symptom**: Worker can't run Docker jobs.

```bash
# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Or change socket permissions (less secure)
sudo chmod 666 /var/run/docker.sock
```

### Container Fails to Start

**Symptom**: Docker jobs fail with container errors.

```bash
# Check Docker daemon
systemctl status docker
docker info

# Pull image manually
docker pull python:3.11

# Check disk space
df -h
docker system df
```

### Image Pull Failures

**Symptom**: Can't pull Docker images.

```bash
# Check registry access
curl https://registry.example.com/v2/

# Login to registry
docker login registry.example.com

# Use mirror registry
# config.yaml
docker:
  registry_mirror: "https://mirror.example.com"
```

## GPU Issues

### GPU Not Detected

**Symptom**: Worker shows 0 GPUs.

```bash
# Check NVIDIA driver
nvidia-smi

# Check nvidia-docker
docker run --gpus all nvidia/cuda:11.0-base nvidia-smi

# Install nvidia-container-toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### GPU Out of Memory

**Symptom**: GPU jobs fail with OOM errors.

```bash
# Check GPU memory
nvidia-smi

# Clear GPU memory
sudo fuser -v /dev/nvidia*
sudo kill <pids>

# Limit GPU memory per job
# config.yaml
gpu:
  memory_fraction: 0.8
```

## Getting Help

### Collecting Debug Information

```bash
# Generate debug bundle
nebula diagnose --output debug-bundle.tar.gz

# Include in issue report:
# - Debug bundle
# - Steps to reproduce
# - Expected vs actual behavior
```

### Community Support

- GitHub Discussions: https://github.com/salahuddin1992/theEnd/discussions
- GitHub Issues: https://github.com/salahuddin1992/theEnd/issues

### Commercial Support

Contact support@nebulacompute.io for:
- Priority support
- Custom development
- Training and consulting

## See Also

- [Installation Guide](INSTALLATION.md)
- [Configuration Guide](CONFIGURATION.md)
- [FAQ](FAQ.md)
