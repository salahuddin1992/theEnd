# API Reference | مرجع API

Complete REST API documentation for the Distributed Computing System.

## Base URL

```
http://localhost:8765
```

## Authentication

Currently, the API supports token-based authentication (optional).

```bash
# With authentication header
curl -H "Authorization: Bearer <token>" http://localhost:8765/jobs
```

---

## Health & Status

### GET /

Root endpoint - basic server info.

**Response:**
```json
{
  "name": "Distributed Cluster Master",
  "version": "0.1.0",
  "status": "running"
}
```

---

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

---

### GET /stats

Cluster statistics and resource overview.

**Response:**
```json
{
  "total_workers": 5,
  "active_workers": 4,
  "offline_workers": 1,
  "total_jobs": 150,
  "pending_jobs": 10,
  "running_jobs": 25,
  "completed_jobs": 100,
  "failed_jobs": 15,
  "total_cpu_cores": 64.0,
  "available_cpu_cores": 32.0,
  "total_memory_gb": 256.0,
  "available_memory_gb": 128.0,
  "total_gpus": 8,
  "available_gpus": 4
}
```

---

## Workers

### POST /workers/register

Register a new worker node.

**Request Body:**
```json
{
  "hostname": "worker-01",
  "ip_address": "192.168.1.100",
  "port": 9000,
  "total_resources": {
    "cpu_cores": 8.0,
    "memory_mb": 16384,
    "gpu_count": 2,
    "gpu_memory_mb": 16000
  },
  "tags": ["gpu", "high-memory"],
  "labels": {
    "region": "us-east",
    "tier": "production"
  },
  "platform": "linux",
  "python_version": "3.11.0",
  "docker_available": true,
  "gpu_driver_version": "535.104.05"
}
```

**Response:**
```json
{
  "worker_id": "worker-abc123def456",
  "status": "registered"
}
```

---

### POST /workers/heartbeat

Send heartbeat from worker to master.

**Request Body:**
```json
{
  "worker_id": "worker-abc123def456",
  "cpu_percent": 45.5,
  "memory_used_mb": 8192,
  "memory_total_mb": 16384,
  "memory_percent": 50.0,
  "gpus": [
    {
      "index": 0,
      "name": "NVIDIA RTX 4090",
      "uuid": "GPU-xxx-xxx",
      "memory_total_mb": 24576,
      "memory_free_mb": 20000,
      "memory_used_mb": 4576,
      "utilization_percent": 35,
      "temperature_c": 65
    }
  ],
  "load_average": [2.5, 2.0, 1.8]
}
```

**Response:**
```json
{
  "status": "ok",
  "assigned_jobs": [
    {
      "job_id": "job-xyz789",
      "command": "python train.py",
      "status": "scheduled"
    }
  ]
}
```

---

### GET /workers

List all workers.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| status | string | Filter by status: `ready`, `busy`, `offline`, `draining` |

**Response:**
```json
{
  "workers": [
    {
      "worker_id": "worker-abc123",
      "hostname": "worker-01",
      "ip_address": "192.168.1.100",
      "port": 9000,
      "status": "ready",
      "total_resources": {
        "cpu_cores": 8.0,
        "memory_mb": 16384,
        "gpu_count": 2
      },
      "available_resources": {
        "cpu_cores": 4.0,
        "memory_mb": 8192,
        "gpu_count": 1
      },
      "tags": ["gpu", "high-memory"],
      "active_jobs": ["job-123", "job-456"],
      "last_heartbeat": "2024-01-15T10:30:00.000Z"
    }
  ]
}
```

---

### GET /workers/{worker_id}

Get detailed worker information.

**Response:** Same as single worker object above.

---

### DELETE /workers/{worker_id}

Remove a worker from the cluster.

**Response:**
```json
{
  "status": "removed",
  "worker_id": "worker-abc123"
}
```

---

### POST /workers/{worker_id}/drain

Drain a worker (stop accepting new jobs, wait for current jobs to complete).

**Response:**
```json
{
  "status": "draining",
  "worker_id": "worker-abc123"
}
```

---

### POST /workers/{worker_id}/undrain

Resume accepting jobs on a drained worker.

**Response:**
```json
{
  "status": "ready",
  "worker_id": "worker-abc123"
}
```

---

## Jobs

### POST /jobs

Submit a new job.

**Request Body:**
```json
{
  "command": "python",
  "args": ["-c", "print('Hello World')"],
  "name": "my-job",
  "resources": {
    "cpu_cores": 2.0,
    "memory_mb": 1024,
    "gpu_count": 0
  },
  "docker_image": "python:3.11",
  "timeout_seconds": 3600,
  "max_retries": 3,
  "priority": 50,
  "required_tags": ["gpu"],
  "preferred_worker": "worker-abc123",
  "environment": {
    "MY_VAR": "value"
  },
  "working_dir": "/app",
  "labels": {
    "project": "ml-training"
  }
}
```

**Response:**
```json
{
  "job_id": "job-xyz789abc123",
  "status": "submitted"
}
```

**Priority Levels:**
| Value | Level | Description |
|-------|-------|-------------|
| 0-25 | Low | Background tasks |
| 26-75 | Normal | Standard priority |
| 76-150 | High | Important tasks |
| 151-200 | Critical | Urgent tasks |

---

### GET /jobs

List jobs with optional filtering.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| status | string | Filter: `pending`, `scheduled`, `running`, `completed`, `failed`, `cancelled`, `timeout` |
| limit | int | Max results (1-1000, default: 100) |
| queue | string | Filter by queue name |
| user_id | string | Filter by user ID |

**Response:**
```json
{
  "jobs": [
    {
      "job_id": "job-xyz789",
      "name": "my-job",
      "status": "running",
      "command": "python train.py",
      "created_at": "2024-01-15T10:00:00.000Z",
      "started_at": "2024-01-15T10:01:00.000Z",
      "assigned_worker": "worker-abc123",
      "resources": {
        "cpu_cores": 2.0,
        "memory_mb": 1024,
        "gpu_count": 0
      },
      "priority": 50,
      "execution_time_seconds": 120.5,
      "wait_time_seconds": 60.0
    }
  ]
}
```

---

### GET /jobs/{job_id}

Get detailed job information.

**Response:**
```json
{
  "job_id": "job-xyz789",
  "name": "my-job",
  "status": "completed",
  "command": "python",
  "args": ["-c", "print('Hello')"],
  "resources": {
    "cpu_cores": 2.0,
    "memory_mb": 1024,
    "gpu_count": 0
  },
  "created_at": "2024-01-15T10:00:00.000Z",
  "started_at": "2024-01-15T10:01:00.000Z",
  "completed_at": "2024-01-15T10:05:00.000Z",
  "assigned_worker": "worker-abc123",
  "execution_time_seconds": 240.5,
  "result": {
    "exit_code": 0,
    "stdout": "Hello\n",
    "stderr": "",
    "peak_memory_mb": 512
  },
  "retry_count": 0,
  "max_retries": 3
}
```

---

### DELETE /jobs/{job_id}

Cancel a pending or running job.

**Response:**
```json
{
  "status": "cancelled",
  "job_id": "job-xyz789"
}
```

---

### POST /jobs/{job_id}/start

Internal endpoint for workers to report job start.

**Request Body:**
```json
{
  "job_id": "job-xyz789",
  "worker_id": "worker-abc123"
}
```

---

### POST /jobs/{job_id}/complete

Internal endpoint for workers to report job completion.

**Request Body:**
```json
{
  "job_id": "job-xyz789",
  "worker_id": "worker-abc123",
  "exit_code": 0,
  "stdout": "Job output...",
  "stderr": "",
  "execution_time_seconds": 120.5,
  "peak_memory_mb": 512
}
```

---

## Templates

### GET /templates

List all job templates.

**Response:**
```json
{
  "templates": [
    {
      "name": "gpu-training",
      "description": "Template for GPU training jobs",
      "resources": {
        "cpu_cores": 4.0,
        "memory_mb": 8192,
        "gpu_count": 1
      },
      "docker_image": "pytorch/pytorch:2.0-cuda11.8",
      "timeout_seconds": 86400
    }
  ]
}
```

---

### POST /templates

Create a new job template.

**Request Body:**
```json
{
  "name": "ml-inference",
  "description": "Template for ML inference jobs",
  "resources": {
    "cpu_cores": 2.0,
    "memory_mb": 4096,
    "gpu_count": 1
  },
  "docker_image": "my-inference:latest",
  "timeout_seconds": 300,
  "environment": {
    "MODEL_PATH": "/models"
  }
}
```

---

### DELETE /templates/{name}

Delete a job template.

---

## Pools

### GET /pools

List worker pools.

**Response:**
```json
{
  "pools": [
    {
      "name": "gpu-pool",
      "description": "Pool for GPU workers",
      "worker_count": 4,
      "min_workers": 2,
      "max_workers": 10,
      "labels": ["gpu", "training"],
      "autoscale_enabled": true
    }
  ]
}
```

---

### POST /pools

Create a new worker pool.

**Request Body:**
```json
{
  "name": "cpu-pool",
  "description": "Pool for CPU-only workers",
  "min_workers": 1,
  "max_workers": 20,
  "labels": ["cpu"],
  "autoscale_enabled": true
}
```

---

## Queues

### GET /queues

List priority queues.

**Response:**
```json
{
  "queues": [
    {
      "name": "high-priority",
      "priority": 100,
      "weight": 2,
      "pending_jobs": 5,
      "running_jobs": 10,
      "state": "active"
    }
  ]
}
```

---

### POST /queues

Create a new priority queue.

**Request Body:**
```json
{
  "name": "batch-queue",
  "priority": 25,
  "weight": 1,
  "max_concurrent_jobs": 50,
  "target_pool": "cpu-pool"
}
```

---

### POST /queues/{name}/pause

Pause a queue (stop scheduling new jobs from this queue).

---

### POST /queues/{name}/resume

Resume a paused queue.

---

## Events

### GET /events

Get recent cluster events.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| limit | int | Max events (1-1000, default: 100) |

**Response:**
```json
{
  "events": [
    {
      "event_id": "evt-abc123",
      "event_type": "job_completed",
      "timestamp": "2024-01-15T10:30:00.000Z",
      "data": {
        "job_id": "job-xyz789",
        "exit_code": 0,
        "execution_time": 120.5
      }
    }
  ]
}
```

**Event Types:**
- `worker_registered`
- `worker_offline`
- `worker_online`
- `job_submitted`
- `job_scheduled`
- `job_started`
- `job_completed`
- `job_failed`
- `job_cancelled`
- `job_timeout`

---

## WebSocket

### WS /ws

Real-time updates via WebSocket.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8765/ws');

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'initial_state') {
    // Initial cluster state
    console.log('Workers:', data.workers);
    console.log('Stats:', data.stats);
  } else if (data.type === 'event') {
    // Real-time event
    console.log('Event:', data.event);
  }
};

// Keep-alive
setInterval(() => {
  ws.send('ping');
}, 30000);
```

**Initial State Message:**
```json
{
  "type": "initial_state",
  "stats": { ... },
  "workers": [ ... ]
}
```

**Event Message:**
```json
{
  "type": "event",
  "event": {
    "event_id": "evt-abc123",
    "event_type": "job_completed",
    "timestamp": "2024-01-15T10:30:00.000Z",
    "data": { ... }
  }
}
```

---

## Error Responses

All endpoints return errors in this format:

```json
{
  "detail": "Error message here"
}
```

**HTTP Status Codes:**
| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 404 | Not Found |
| 409 | Conflict |
| 422 | Validation Error |
| 500 | Internal Server Error |

---

## Rate Limiting

Default rate limits:
- 100 requests/second per IP
- 1000 requests/minute per API token

---

## SDK Examples

### Python

```python
import httpx

client = httpx.Client(base_url="http://localhost:8765")

# Submit a job
response = client.post("/jobs", json={
    "command": "python",
    "args": ["-c", "print('Hello')"],
    "resources": {"cpu_cores": 1.0, "memory_mb": 512}
})
job_id = response.json()["job_id"]

# Check status
job = client.get(f"/jobs/{job_id}").json()
print(f"Status: {job['status']}")
```

### JavaScript/Node.js

```javascript
const axios = require('axios');

const client = axios.create({
  baseURL: 'http://localhost:8765'
});

// Submit a job
const { data } = await client.post('/jobs', {
  command: 'python',
  args: ['-c', "print('Hello')"],
  resources: { cpu_cores: 1.0, memory_mb: 512 }
});

console.log('Job ID:', data.job_id);
```

### cURL

```bash
# Submit a job
curl -X POST http://localhost:8765/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "command": "python",
    "args": ["-c", "print(\"Hello\")"],
    "resources": {"cpu_cores": 1.0, "memory_mb": 512}
  }'

# List jobs
curl http://localhost:8765/jobs?status=running

# Get cluster stats
curl http://localhost:8765/stats
```
