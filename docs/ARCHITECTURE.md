# Architecture Guide

Detailed architecture documentation for NebulaCompute.

## Table of Contents

- [System Overview](#system-overview)
- [Component Architecture](#component-architecture)
- [Data Flow](#data-flow)
- [Scheduler Architecture](#scheduler-architecture)
- [Storage Architecture](#storage-architecture)
- [Security Architecture](#security-architecture)
- [Network Architecture](#network-architecture)
- [Extension Points](#extension-points)

## System Overview

### High-Level Architecture

```
                         ┌─────────────────────────────┐
                         │       Load Balancer         │
                         └─────────────┬───────────────┘
                                       │
                         ┌─────────────▼───────────────┐
                         │        Master Node          │
                         │  ┌──────────────────────┐   │
                         │  │      REST API        │   │
                         │  │   (FastAPI/Uvicorn)  │   │
                         │  └──────────┬───────────┘   │
                         │             │               │
                         │  ┌──────────▼───────────┐   │
                         │  │     Scheduler        │   │
                         │  │  (Job Assignment)    │   │
                         │  └──────────┬───────────┘   │
                         │             │               │
                         │  ┌──────────▼───────────┐   │
                         │  │   Worker Registry    │   │
                         │  │  (State Management)  │   │
                         │  └──────────────────────┘   │
                         └─────────────┬───────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
    ┌─────────▼─────────┐   ┌─────────▼─────────┐   ┌─────────▼─────────┐
    │   Worker Node 1   │   │   Worker Node 2   │   │   Worker Node N   │
    │  ┌─────────────┐  │   │  ┌─────────────┐  │   │  ┌─────────────┐  │
    │  │   Agent     │  │   │  │   Agent     │  │   │  │   Agent     │  │
    │  └──────┬──────┘  │   │  └──────┬──────┘  │   │  └──────┬──────┘  │
    │         │         │   │         │         │   │         │         │
    │  ┌──────▼──────┐  │   │  ┌──────▼──────┐  │   │  ┌──────▼──────┐  │
    │  │  Executor   │  │   │  │  Executor   │  │   │  │  Executor   │  │
    │  │(Docker/Bare)│  │   │  │(Docker/Bare)│  │   │  │(Docker/Bare)│  │
    │  └─────────────┘  │   │  └─────────────┘  │   │  └─────────────┘  │
    └───────────────────┘   └───────────────────┘   └───────────────────┘
```

### Design Principles

1. **Simplicity**: Easy to deploy and operate
2. **Scalability**: Handle thousands of workers
3. **Reliability**: Graceful failure handling
4. **Security**: Defense in depth
5. **Extensibility**: Plugin-based architecture

## Component Architecture

### Master Node

```
┌─────────────────────────────────────────────────────────┐
│                     Master Node                         │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐              │
│  │   REST API      │  │   WebSocket     │              │
│  │   (FastAPI)     │  │   Server        │              │
│  └────────┬────────┘  └────────┬────────┘              │
│           │                    │                        │
│  ┌────────▼────────────────────▼────────┐              │
│  │           Request Router              │              │
│  └────────────────┬─────────────────────┘              │
│                   │                                     │
│  ┌────────────────┼─────────────────────┐              │
│  │                │                     │              │
│  ▼                ▼                     ▼              │
│  ┌─────────┐  ┌─────────┐  ┌─────────────────┐        │
│  │Scheduler│  │ Worker  │  │  Job Manager    │        │
│  │         │  │ Manager │  │                 │        │
│  └────┬────┘  └────┬────┘  └────────┬────────┘        │
│       │            │                │                  │
│  ┌────▼────────────▼────────────────▼────┐            │
│  │              Storage Layer             │            │
│  │  (SQLite/PostgreSQL + Redis Cache)    │            │
│  └────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────┘
```

#### Components:

- **REST API**: HTTP endpoints for job submission, status queries
- **WebSocket Server**: Real-time updates to clients
- **Scheduler**: Job-to-worker assignment logic
- **Worker Manager**: Worker registration, health monitoring
- **Job Manager**: Job lifecycle management
- **Storage Layer**: Persistence and caching

### Worker Node

```
┌─────────────────────────────────────────────────────────┐
│                     Worker Node                         │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────┐               │
│  │            Worker Agent             │               │
│  │  ┌─────────────┐  ┌──────────────┐  │               │
│  │  │  Heartbeat  │  │  Job Fetch   │  │               │
│  │  │  Manager    │  │  Loop        │  │               │
│  │  └─────────────┘  └──────────────┘  │               │
│  └──────────────────┬──────────────────┘               │
│                     │                                   │
│  ┌──────────────────▼──────────────────┐               │
│  │           Job Executor               │               │
│  │  ┌─────────────────────────────┐    │               │
│  │  │     Execution Backends      │    │               │
│  │  │  ┌────────┐  ┌───────────┐  │    │               │
│  │  │  │ Docker │  │   Bare    │  │    │               │
│  │  │  │        │  │  Process  │  │    │               │
│  │  │  └────────┘  └───────────┘  │    │               │
│  │  └─────────────────────────────┘    │               │
│  └─────────────────────────────────────┘               │
│                                                         │
│  ┌─────────────────────────────────────┐               │
│  │         Resource Monitor            │               │
│  │  CPU │ Memory │ GPU │ Disk │ Network│               │
│  └─────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────┘
```

#### Components:

- **Worker Agent**: Main process coordinating worker operations
- **Heartbeat Manager**: Periodic health reports to master
- **Job Fetch Loop**: Polls master for new jobs
- **Job Executor**: Runs jobs in isolated environments
- **Resource Monitor**: Tracks system resource usage

## Data Flow

### Job Submission Flow

```
Client                Master                    Worker
  │                     │                         │
  │  POST /jobs         │                         │
  │────────────────────>│                         │
  │                     │                         │
  │                     │  Validate & Store       │
  │                     │─────────────────┐       │
  │                     │                 │       │
  │  Job ID             │<────────────────┘       │
  │<────────────────────│                         │
  │                     │                         │
  │                     │  Schedule Job           │
  │                     │─────────────────┐       │
  │                     │                 │       │
  │                     │<────────────────┘       │
  │                     │                         │
  │                     │  GET /jobs/assigned     │
  │                     │<────────────────────────│
  │                     │                         │
  │                     │  Job Details            │
  │                     │────────────────────────>│
  │                     │                         │
  │                     │                         │  Execute
  │                     │                         │────────┐
  │                     │                         │        │
  │                     │                         │<───────┘
  │                     │                         │
  │                     │  POST /jobs/{id}/result │
  │                     │<────────────────────────│
  │                     │                         │
  │  WebSocket: status  │                         │
  │<────────────────────│                         │
```

### Worker Registration Flow

```
Worker                  Master                  Redis (HA)
  │                       │                        │
  │  POST /workers        │                        │
  │──────────────────────>│                        │
  │                       │                        │
  │                       │  Validate Token        │
  │                       │───────────┐            │
  │                       │           │            │
  │                       │<──────────┘            │
  │                       │                        │
  │                       │  Store Worker State    │
  │                       │───────────────────────>│
  │                       │                        │
  │  Worker ID + Config   │                        │
  │<──────────────────────│                        │
  │                       │                        │
  │  Heartbeat Loop       │                        │
  │                       │                        │
  │  PUT /workers/{id}    │                        │
  │──────────────────────>│                        │
  │                       │  Update State          │
  │                       │───────────────────────>│
```

## Scheduler Architecture

### Scheduling Pipeline

```
                    ┌─────────────────────────────┐
                    │       Job Queue             │
                    │  (Priority Heap)            │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │     Policy Selection        │
                    │  ┌───────────────────────┐  │
                    │  │ First Fit │ Best Fit  │  │
                    │  │ Round Robin│ Priority │  │
                    │  └───────────────────────┘  │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │    Resource Matching        │
                    │  ┌───────────────────────┐  │
                    │  │ CPU │ Memory │ GPU    │  │
                    │  │ Tags│ Labels│ Affinity│  │
                    │  └───────────────────────┘  │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │    Constraint Evaluation    │
                    │  ┌───────────────────────┐  │
                    │  │ Anti-affinity │ Spread │  │
                    │  │ Node Selector │        │  │
                    │  └───────────────────────┘  │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │      Job Assignment         │
                    └─────────────────────────────┘
```

### Scheduling Policies

| Policy | Description | Use Case |
|--------|-------------|----------|
| First Fit | Assign to first available worker | Speed priority |
| Best Fit | Minimize resource waste | Efficiency priority |
| Round Robin | Even distribution | Fairness priority |
| Priority | Higher priority jobs first | Mixed workloads |
| Gang | Schedule multiple tasks together | Distributed jobs |

## Storage Architecture

### Data Model

```
┌─────────────────────────────────────────────────────────┐
│                    Storage Layer                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │    Jobs     │  │   Workers   │  │  Artifacts  │     │
│  │             │  │             │  │             │     │
│  │ - job_id    │  │ - worker_id │  │ - artifact_id│    │
│  │ - command   │  │ - hostname  │  │ - job_id    │     │
│  │ - status    │  │ - status    │  │ - path      │     │
│  │ - resources │  │ - resources │  │ - size      │     │
│  │ - result    │  │ - tags      │  │ - checksum  │     │
│  │ - created_at│  │ - last_seen │  │ - created_at│     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │                 Database Backend                 │   │
│  │  ┌───────────┐  ┌────────────┐  ┌────────────┐  │   │
│  │  │  SQLite   │  │ PostgreSQL │  │   Redis    │  │   │
│  │  │  (dev)    │  │  (prod)    │  │  (cache)   │  │   │
│  │  └───────────┘  └────────────┘  └────────────┘  │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Artifact Storage

```
                    ┌─────────────────────────────┐
                    │      Artifact Manager       │
                    └─────────────┬───────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
    ┌─────────▼─────────┐ ┌──────▼──────┐ ┌─────────▼─────────┐
    │   Local Storage   │ │     S3      │ │      MinIO        │
    │   (filesystem)    │ │             │ │                   │
    └───────────────────┘ └─────────────┘ └───────────────────┘
```

## Security Architecture

### Authentication Flow

```
Client              API Gateway           Auth Service          Master
  │                      │                     │                  │
  │  Login Request       │                     │                  │
  │─────────────────────>│                     │                  │
  │                      │                     │                  │
  │                      │  Validate Credentials                  │
  │                      │────────────────────>│                  │
  │                      │                     │                  │
  │                      │  JWT Token          │                  │
  │                      │<────────────────────│                  │
  │                      │                     │                  │
  │  JWT Token           │                     │                  │
  │<─────────────────────│                     │                  │
  │                      │                     │                  │
  │  API Request + JWT   │                     │                  │
  │─────────────────────>│                     │                  │
  │                      │                     │                  │
  │                      │  Verify JWT         │                  │
  │                      │────────────────────>│                  │
  │                      │                     │                  │
  │                      │  Valid + Claims     │                  │
  │                      │<────────────────────│                  │
  │                      │                     │                  │
  │                      │  Forward Request    │                  │
  │                      │───────────────────────────────────────>│
```

### Security Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                        Security Layers                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 1: Transport Security (TLS)                        │ │
│  │  - All connections encrypted                               │ │
│  │  - Certificate validation                                  │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 2: Authentication (JWT)                            │ │
│  │  - Token-based authentication                              │ │
│  │  - API key support                                         │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 3: Authorization (RBAC)                            │ │
│  │  - Role-based access control                               │ │
│  │  - Resource-level permissions                              │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 4: Job Isolation                                   │ │
│  │  - Container sandboxing                                    │ │
│  │  - Resource limits                                         │ │
│  │  - Network isolation                                       │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Network Architecture

### Communication Patterns

```
┌─────────────────────────────────────────────────────────────────┐
│                    Network Architecture                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Client ──HTTP/HTTPS──> Master                                 │
│                                                                 │
│  Client ──WebSocket───> Master  (real-time updates)            │
│                                                                 │
│  Worker ──HTTP/HTTPS──> Master  (heartbeat, job fetch)         │
│                                                                 │
│  Master ──HTTP/HTTPS──> Worker  (job push, optional)           │
│                                                                 │
│  Worker ──gRPC────────> Worker  (mesh networking, optional)    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 8000 | HTTP/HTTPS | Master API |
| 8001 | HTTP | Master metrics |
| 8081 | HTTP | Worker health check |
| 50051 | gRPC | Worker mesh (optional) |

## Extension Points

### Plugin Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Extension Points                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Scheduler Plugin│  │ Executor Plugin │  │ Storage Plugin  │ │
│  │                 │  │                 │  │                 │ │
│  │ - Custom policy │  │ - Custom runtime│  │ - Custom backend│ │
│  │ - ML scheduling │  │ - GPU executor  │  │ - Cloud storage │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   Auth Plugin   │  │  Metrics Plugin │  │ Notifier Plugin │ │
│  │                 │  │                 │  │                 │ │
│  │ - LDAP/AD       │  │ - Custom metrics│  │ - Slack/Email   │ │
│  │ - OAuth2        │  │ - APM export    │  │ - Webhook       │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Custom Scheduler Example

```python
from distributed_cluster.scheduler import SchedulerPlugin

class MLSchedulerPlugin(SchedulerPlugin):
    """Scheduler optimized for ML workloads."""

    def schedule(self, job, workers):
        # Prefer GPU workers for ML jobs
        if job.tags and "ml" in job.tags:
            gpu_workers = [w for w in workers if w.gpu_count > 0]
            if gpu_workers:
                return self.best_fit(job, gpu_workers)
        return self.default_schedule(job, workers)
```

## See Also

- [API Reference](API_REFERENCE.md)
- [Configuration Guide](CONFIGURATION.md)
- [Security Guide](SECURITY.md)
