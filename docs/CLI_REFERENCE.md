# CLI Reference

Complete command-line interface reference for NebulaCompute.

## Table of Contents

- [Overview](#overview)
- [Global Options](#global-options)
- [Master Commands](#master-commands)
- [Worker Commands](#worker-commands)
- [Job Commands](#job-commands)
- [Cluster Commands](#cluster-commands)
- [Admin Commands](#admin-commands)

## Overview

### Main CLI

```bash
nebula [OPTIONS] COMMAND [ARGS]...
```

### Getting Help

```bash
nebula --help
nebula <command> --help
```

## Global Options

| Option | Description |
|--------|-------------|
| `--config FILE` | Configuration file path |
| `--master URL` | Master node URL |
| `--api-key KEY` | API key for authentication |
| `--verbose, -v` | Increase verbosity |
| `--quiet, -q` | Suppress output |
| `--json` | Output in JSON format |
| `--version` | Show version |
| `--help` | Show help |

## Master Commands

### nebula master start

Start the master node.

```bash
nebula master start [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | 0.0.0.0 | Listen address |
| `--port` | 8000 | Listen port |
| `--config` | config.yaml | Config file |
| `--workers` | 4 | Uvicorn workers |
| `--log-level` | INFO | Log level |
| `--reload` | false | Auto-reload on changes |

**Examples:**

```bash
# Start with defaults
nebula master start

# Custom port
nebula master start --port 8080

# With config file
nebula master start --config production.yaml

# Development mode
nebula master start --reload --log-level DEBUG
```

### nebula master stop

Stop the master node.

```bash
nebula master stop [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--force` | Force stop without draining |
| `--timeout` | Shutdown timeout (seconds) |

### nebula master status

Show master node status.

```bash
nebula master status [OPTIONS]
```

## Worker Commands

### nebula worker start

Start a worker node.

```bash
nebula worker start [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--master` | http://localhost:8000 | Master URL |
| `--id` | auto | Worker ID |
| `--tags` | | Comma-separated tags |
| `--labels` | | Key=value labels |
| `--max-jobs` | 4 | Max concurrent jobs |
| `--enrollment-token` | | Enrollment token |

**Examples:**

```bash
# Basic start
nebula worker start --master http://master:8000

# With tags
nebula worker start --tags cpu,docker,high-memory

# With labels
nebula worker start --labels zone=us-east,tier=compute

# Limited concurrent jobs
nebula worker start --max-jobs 2
```

### nebula worker stop

Stop a worker.

```bash
nebula worker stop [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--drain` | Finish current jobs before stopping |
| `--force` | Force stop immediately |

### nebula worker list

List all workers.

```bash
nebula worker list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--status` | Filter by status |
| `--tags` | Filter by tags |
| `--show-resources` | Show resource details |

**Examples:**

```bash
# List all workers
nebula worker list

# Only active workers
nebula worker list --status ready

# Workers with GPU
nebula worker list --tags gpu

# With resources
nebula worker list --show-resources
```

### nebula worker info

Show worker details.

```bash
nebula worker info <WORKER_ID>
```

### nebula worker drain

Drain a worker (finish jobs, stop accepting new ones).

```bash
nebula worker drain <WORKER_ID>
```

## Job Commands

### nebula job submit

Submit a new job.

```bash
nebula job submit [OPTIONS] COMMAND
```

| Option | Default | Description |
|--------|---------|-------------|
| `--name` | auto | Job name |
| `--cpu` | 1 | CPU cores required |
| `--memory` | 1024 | Memory (MB) required |
| `--gpu` | 0 | GPUs required |
| `--priority` | normal | Priority (low/normal/high/critical) |
| `--timeout` | 3600 | Timeout in seconds |
| `--tags` | | Required worker tags |
| `--env` | | Environment variable (KEY=VALUE) |
| `--env-file` | | File with environment variables |
| `--docker` | | Docker image to use |
| `--retries` | 0 | Number of retries on failure |
| `--depends-on` | | Job IDs to wait for |

**Examples:**

```bash
# Simple command
nebula job submit "echo 'Hello World'"

# With resources
nebula job submit --cpu 4 --memory 8192 "python train.py"

# GPU job
nebula job submit --gpu 1 --docker nvidia/cuda:11.8 "python inference.py"

# High priority
nebula job submit --priority high "critical_task.sh"

# With environment
nebula job submit --env API_KEY=xxx --env DEBUG=true "python script.py"

# Docker job
nebula job submit --docker python:3.11 "python -c 'print(1)'"

# With retry
nebula job submit --retries 3 "flaky_command.sh"

# Dependent job
nebula job submit --depends-on job-123,job-456 "final_step.sh"
```

### nebula job list

List jobs.

```bash
nebula job list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--status` | Filter by status |
| `--limit` | Maximum jobs to show |
| `--offset` | Offset for pagination |
| `--since` | Jobs since timestamp |
| `--user` | Filter by user |

**Examples:**

```bash
# All jobs
nebula job list

# Running jobs
nebula job list --status running

# Recent 10 jobs
nebula job list --limit 10

# Jobs from last hour
nebula job list --since "1 hour ago"
```

### nebula job status

Show job status.

```bash
nebula job status <JOB_ID>
```

### nebula job info

Show detailed job information.

```bash
nebula job info <JOB_ID>
```

### nebula job logs

Show job output.

```bash
nebula job logs [OPTIONS] <JOB_ID>
```

| Option | Description |
|--------|-------------|
| `--follow, -f` | Follow log output |
| `--tail` | Show last N lines |
| `--timestamps` | Include timestamps |

**Examples:**

```bash
# View logs
nebula job logs job-123

# Follow logs
nebula job logs -f job-123

# Last 100 lines
nebula job logs --tail 100 job-123
```

### nebula job cancel

Cancel a job.

```bash
nebula job cancel <JOB_ID>
```

### nebula job wait

Wait for job completion.

```bash
nebula job wait [OPTIONS] <JOB_ID>
```

| Option | Description |
|--------|-------------|
| `--timeout` | Wait timeout |
| `--poll` | Poll interval |

### nebula job artifacts

Download job artifacts.

```bash
nebula job artifacts [OPTIONS] <JOB_ID>
```

| Option | Description |
|--------|-------------|
| `--output, -o` | Output directory |
| `--file` | Specific file to download |

### nebula job retry

Retry a failed job.

```bash
nebula job retry <JOB_ID>
```

## Cluster Commands

### nebula status

Show cluster status.

```bash
nebula status [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--verbose` | Show detailed status |
| `--watch` | Continuously update |

**Output:**

```
Cluster: production
Status: healthy

Workers: 10 active / 12 total
  CPU: 80/96 cores available
  Memory: 128/192 GB available
  GPU: 4/8 available

Jobs:
  Pending: 25
  Running: 45
  Completed (24h): 1,234
  Failed (24h): 12
```

### nebula health

Check cluster health.

```bash
nebula health [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--verbose` | Show component details |
| `--json` | JSON output |

### nebula metrics

Show cluster metrics.

```bash
nebula metrics [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--format` | Output format (text/json/prometheus) |
| `--filter` | Filter metrics by name |

## Admin Commands

### nebula db migrate

Run database migrations.

```bash
nebula db migrate [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--to` | Migrate to specific version |
| `--dry-run` | Show migrations without applying |

### nebula db backup

Backup database.

```bash
nebula db backup [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--output` | Output directory |
| `--format` | Backup format |

### nebula db restore

Restore database.

```bash
nebula db restore [OPTIONS] <BACKUP_FILE>
```

### nebula auth create-key

Create API key.

```bash
nebula auth create-key [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--name` | Key name |
| `--role` | Role (admin/user) |
| `--expires` | Expiration (e.g., 30d) |

### nebula config validate

Validate configuration.

```bash
nebula config validate [OPTIONS]
```

### nebula diagnose

Run diagnostics.

```bash
nebula diagnose [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--output` | Save to file |
| `--include-logs` | Include recent logs |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NEBULA_MASTER_URL` | Default master URL |
| `NEBULA_API_KEY` | API key for authentication |
| `NEBULA_CONFIG` | Config file path |
| `NEBULA_LOG_LEVEL` | Log level |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Connection error |
| 4 | Authentication error |
| 5 | Job failed |

## See Also

- [Quick Start](QUICKSTART.md)
- [Configuration](CONFIGURATION.md)
- [Examples](EXAMPLES.md)
