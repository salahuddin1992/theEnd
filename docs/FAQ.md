# Frequently Asked Questions

Common questions and answers about NebulaCompute.

## General Questions

### What is NebulaCompute?

NebulaCompute is an open-source distributed computing system that allows you to run jobs across multiple machines. It uses a master/worker architecture where:

- **Master**: Coordinates job scheduling and worker management
- **Workers**: Execute jobs and report resource availability

### Who is NebulaCompute for?

NebulaCompute is designed for:

- **Data Scientists**: Running ML training and inference across multiple machines
- **Researchers**: Batch processing scientific computations
- **DevOps Teams**: Distributed build and test systems
- **Organizations**: Managing heterogeneous compute resources

### Is NebulaCompute free?

Yes! NebulaCompute is open-source under the MIT license. You can use it for personal, commercial, or educational purposes.

### How does it compare to other solutions?

| Feature | NebulaCompute | Kubernetes Jobs | AWS Batch | Slurm |
|---------|--------------|-----------------|-----------|-------|
| Setup Complexity | Low | High | Medium | High |
| GPU Support | Yes | Yes | Yes | Yes |
| Docker Support | Yes | Native | Native | Limited |
| On-premise | Yes | Yes | No | Yes |
| Cloud | Yes | Yes | Yes | Limited |
| Learning Curve | Easy | Steep | Moderate | Steep |

## Installation Questions

### What are the system requirements?

**Minimum:**
- Python 3.10+
- 2 CPU cores
- 4 GB RAM
- 10 GB disk space

**Recommended:**
- Python 3.11+
- 4+ CPU cores
- 8+ GB RAM
- 50+ GB SSD

### Can I run on Windows?

Yes! NebulaCompute supports Windows 10/11. Some features like Docker-in-Docker may have limitations. For production, Linux is recommended.

### Do I need Docker?

Docker is optional. It's required only if you want to run containerized jobs. For simple shell commands, Docker is not needed.

### How do I install on an air-gapped system?

```bash
# On internet-connected machine:
pip download distributed-cluster -d ./packages

# Transfer ./packages to air-gapped system

# On air-gapped system:
pip install --no-index --find-links=./packages distributed-cluster
```

## Configuration Questions

### Where is the configuration file?

Default locations (in order of precedence):
1. `--config` command line argument
2. `./config.yaml`
3. `~/.config/nebulacompute/config.yaml`
4. `/etc/nebulacompute/config.yaml`

### How do I use environment variables?

All config options can be set via environment variables:

```bash
export NEBULA_MASTER_PORT=8000
export NEBULA_DATABASE_TYPE=postgresql
export NEBULA_JWT_SECRET=your-secret-key
```

Pattern: `NEBULA_<SECTION>_<OPTION>=<VALUE>`

### How do I configure multiple environments?

Create separate config files:

```bash
# Development
nebula master start --config config.dev.yaml

# Production
nebula master start --config config.prod.yaml
```

## Job Questions

### How do I submit a job?

```bash
# Simple command
nebula job submit "echo 'Hello World'"

# With resources
nebula job submit --cpu 4 --memory 8192 "python train.py"

# With GPU
nebula job submit --gpu 1 "python inference.py"
```

### How do I pass environment variables to a job?

```bash
nebula job submit --env API_KEY=xxx --env DEBUG=true "python script.py"
```

Or use a file:

```bash
# job.env
API_KEY=xxx
DEBUG=true

nebula job submit --env-file job.env "python script.py"
```

### How do I get job output?

```bash
# View stdout/stderr
nebula job logs <job-id>

# Download output files
nebula job artifacts <job-id> --output ./results/
```

### Can I run interactive jobs?

Currently, NebulaCompute is designed for batch jobs. Interactive jobs (like Jupyter notebooks) are planned for future releases.

### What happens if a job fails?

By default, failed jobs are marked with status `FAILED`. You can:

```bash
# View failure reason
nebula job info <job-id>

# Retry job
nebula job retry <job-id>

# Configure auto-retry
nebula job submit --retries 3 "python script.py"
```

## Worker Questions

### How many workers can I have?

There's no hard limit. We've tested with 1000+ workers. The practical limit depends on your master node's resources.

### Can workers have different resources?

Yes! Workers automatically detect their resources. You can also add tags:

```bash
nebula worker start --tags gpu,high-memory
```

Then target specific workers:

```bash
nebula job submit --tags gpu "python train.py"
```

### How do I remove a worker?

```bash
# Graceful shutdown (finish running jobs)
nebula worker drain <worker-id>

# Force remove
nebula worker remove <worker-id>
```

### Can workers join from different networks?

Yes, as long as workers can reach the master. For NAT/firewall scenarios, consider:

1. Using a VPN
2. Exposing the master via public IP/DNS
3. Using a reverse proxy

## Security Questions

### Is data encrypted in transit?

Yes, when TLS is enabled:

```yaml
tls:
  enabled: true
  cert_file: /path/to/cert.crt
  key_file: /path/to/key.key
```

### How do I reset a forgotten admin password?

```bash
# Generate new token
nebula auth reset-admin --new-password

# Or use direct database access (SQLite)
sqlite3 data/cluster.db
UPDATE users SET password_hash='...' WHERE username='admin';
```

### Can I integrate with LDAP/Active Directory?

Not currently built-in, but you can use an authentication proxy or contribute an LDAP integration.

## Performance Questions

### How many jobs can the system handle?

Benchmarks show:
- **Job submission**: 1000+ jobs/second
- **Concurrent jobs**: 10,000+ across cluster
- **Workers**: 1000+ per master

### Why are my jobs slow to start?

Common causes:

1. **Resource contention**: Not enough available resources
2. **Docker pull**: Images being pulled (use local registry)
3. **Scheduler policy**: `best_fit` is slower than `first_fit`

### How do I improve performance?

1. Use SSD storage for database
2. Use PostgreSQL for large deployments
3. Enable Redis caching
4. Use `first_fit` scheduling for speed

## Troubleshooting Questions

### Where are the logs?

```bash
# View master logs
nebula logs

# View specific worker logs
nebula logs --worker <worker-id>

# Log file locations
~/.local/share/nebulacompute/logs/  # User
/var/log/nebulacompute/             # System
```

### How do I report a bug?

1. Search existing issues: https://github.com/salahuddin1992/theEnd/issues
2. Collect debug info: `nebula diagnose --output debug.tar.gz`
3. Open new issue with details

### How do I get support?

- **Community**: GitHub Discussions
- **Issues**: GitHub Issues
- **Commercial**: support@nebulacompute.io

## Contributing Questions

### How can I contribute?

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. Areas where help is welcome:

- Bug fixes
- Documentation
- New features
- Testing

### How do I set up a development environment?

```bash
git clone https://github.com/salahuddin1992/theEnd.git
cd theEnd
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest
```

### What's the release schedule?

We aim for regular releases:
- **Patch releases**: As needed for bug fixes
- **Minor releases**: Monthly with new features
- **Major releases**: When breaking changes are necessary

## Roadmap Questions

### What features are planned?

See [PROJECT_IDEAS.md](PROJECT_IDEAS.md) for the full roadmap. Highlights:

- **0.2.0**: High availability, better GPU scheduling
- **0.3.0**: Federation, multi-cluster support
- **1.0.0**: Production-ready stable release

### Can I request a feature?

Yes! Open a GitHub Discussion or Issue with the `feature-request` label.

## Still Have Questions?

- Check the [documentation](https://docs.nebulacompute.io)
- Ask on [GitHub Discussions](https://github.com/salahuddin1992/theEnd/discussions)
- Open an [Issue](https://github.com/salahuddin1992/theEnd/issues)
