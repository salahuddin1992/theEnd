# Contributing Guide | دليل المساهمة

Thank you for your interest in contributing to the Distributed Computing System! This guide will help you get started.

شكراً لاهتمامك بالمساهمة في نظام الحوسبة الموزّعة! هذا الدليل سيساعدك على البدء.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Setup](#development-setup)
3. [Code Style](#code-style)
4. [Testing](#testing)
5. [Pull Request Process](#pull-request-process)
6. [Architecture Overview](#architecture-overview)
7. [Adding New Features](#adding-new-features)

---

## Getting Started

### Prerequisites

- Python 3.10+
- Docker (optional, for container execution)
- Git

### Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/theEnd.git
cd theEnd

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL_OWNER/theEnd.git
```

---

## Development Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows
```

### 2. Install Dependencies

```bash
# Install in development mode with all extras
pip install -e ".[dev,grpc,desktop]"

# Or just the basics
pip install -e ".[dev]"
```

### 3. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=distributed_cluster --cov-report=html

# Run specific test file
pytest tests/test_scheduler.py -v
```

### 4. Start Development Server

```bash
# Start master
dc-master start --port 8765

# In another terminal, start worker
dc-worker start --master http://localhost:8765
```

---

## Code Style

### Python Style Guide

We follow PEP 8 with some modifications:

```python
# Good: Clear, descriptive names
def calculate_resource_slack(available: ResourceSpec, required: ResourceSpec) -> float:
    """Calculate remaining resources after allocation."""
    remaining = available.subtract(required)
    return remaining.cpu_cores / max(available.cpu_cores, 1)

# Good: Type hints
def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
    return self._workers.get(worker_id)

# Good: Bilingual docstrings (English + Arabic)
def submit_job(self, submission: JobSubmission) -> Job:
    """
    Submit a new job to the cluster.
    إرسال job جديد للكلاستر.
    """
    pass
```

### Formatting Tools

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking
mypy src/distributed_cluster
```

### Pre-commit Hooks (Recommended)

```bash
pip install pre-commit
pre-commit install
```

---

## Testing

### Test Structure

```
tests/
├── test_scheduler.py      # Unit tests for scheduler
├── test_mesh.py           # Unit tests for mesh network
├── test_resources.py      # Unit tests for resource detection
├── test_web.py            # Unit tests for web dashboard
└── integration/
    ├── test_auth.py       # Auth integration tests
    ├── test_database.py   # Database integration tests
    ├── test_lease.py      # Lease manager tests
    └── test_scheduler.py  # Scheduler integration tests
```

### Writing Tests

```python
import pytest
from distributed_cluster.scheduler import Scheduler, SchedulingPolicy

class TestScheduler:
    """Test cases for the Scheduler class."""

    @pytest.fixture
    def scheduler(self):
        """Create a scheduler instance for testing."""
        return Scheduler(policy=SchedulingPolicy.BEST_FIT)

    def test_schedule_single_job(self, scheduler):
        """Test scheduling a single job to a worker."""
        # Arrange
        worker = create_test_worker(cpu_cores=8)
        job = create_test_job(cpu_cores=2)

        # Act
        decisions = scheduler.schedule([job], [worker])

        # Assert
        assert len(decisions) == 1
        assert decisions[0].worker == worker
        assert decisions[0].job == job

    @pytest.mark.asyncio
    async def test_async_operation(self):
        """Test async operations."""
        result = await some_async_function()
        assert result is not None
```

### Test Coverage Requirements

- Minimum 80% coverage for new code
- All public APIs must have tests
- Integration tests for critical paths

---

## Pull Request Process

### 1. Create Feature Branch

```bash
git checkout -b feature/my-new-feature
# or
git checkout -b fix/bug-description
```

### 2. Make Changes

- Write code following style guide
- Add/update tests
- Update documentation if needed

### 3. Commit Messages

Follow conventional commits:

```
feat: add GPU scheduling optimization
fix: resolve memory leak in worker agent
docs: update API reference
test: add scheduler integration tests
refactor: simplify resource allocation logic
chore: update dependencies
```

### 4. Push and Create PR

```bash
git push origin feature/my-new-feature
```

Then create a Pull Request on GitHub with:
- Clear description of changes
- Link to related issues
- Screenshots for UI changes
- Test results

### 5. Review Process

- At least 1 approval required
- All tests must pass
- No merge conflicts

---

## Architecture Overview

### Module Structure

```
src/distributed_cluster/
├── core/                 # Core utilities
│   ├── config.py         # Configuration classes
│   └── resource_detector.py  # System resource detection
│
├── models/               # Data models (Pydantic)
│   ├── job.py            # Job, JobSubmission, JobResult
│   ├── worker.py         # WorkerInfo, WorkerStatus
│   ├── resources.py      # ResourceSpec, ResourceUsage
│   └── events.py         # Event types
│
├── master/               # Control plane
│   ├── server.py         # FastAPI REST API
│   └── state.py          # Cluster state management
│
├── worker/               # Data plane
│   ├── agent.py          # Worker agent
│   └── executor.py       # Job execution (process/Docker)
│
├── scheduler/            # Scheduling engine
│   ├── scheduler.py      # Core scheduler
│   ├── scoring.py        # Worker scoring
│   ├── pools.py          # Worker pools
│   ├── priority_queues.py # Priority queues
│   └── autoscaler.py     # Auto-scaling logic
│
├── mesh/                 # P2P mesh network
│   ├── node.py           # Mesh node
│   ├── gossip.py         # Gossip protocol
│   └── consensus.py      # Consensus algorithms
│
├── security/             # Security components
│   ├── auth.py           # Authentication
│   └── secrets.py        # Secrets management
│
├── storage/              # Persistence
│   └── database.py       # SQLite storage
│
├── observability/        # Monitoring
│   ├── metrics.py        # Prometheus metrics
│   └── health.py         # Health checks
│
└── cli/                  # Command-line interfaces
    ├── master_cli.py     # dc-master
    ├── worker_cli.py     # dc-worker
    └── submit_cli.py     # dc-submit
```

### Key Concepts

1. **Master/Worker Architecture**: Central control plane with distributed workers
2. **Resource-based Scheduling**: Jobs are scheduled based on CPU/RAM/GPU requirements
3. **Bin Packing**: Best-fit algorithm minimizes resource fragmentation
4. **Fault Tolerance**: Heartbeats, retries, and job recovery

---

## Adding New Features

### Adding a New Scheduling Policy

1. Add policy to enum in `scheduler/scheduler.py`:

```python
class SchedulingPolicy(str, Enum):
    FIRST_FIT = "first_fit"
    BEST_FIT = "best_fit"
    MY_NEW_POLICY = "my_new_policy"  # Add here
```

2. Implement selection logic:

```python
def _select_worker(self, job: Job, candidates: list[WorkerInfo]):
    # ...
    elif self.policy == SchedulingPolicy.MY_NEW_POLICY:
        return self._my_new_policy_select(job, candidates)
```

3. Add tests:

```python
def test_my_new_policy(self, scheduler):
    scheduler.policy = SchedulingPolicy.MY_NEW_POLICY
    # Test implementation
```

### Adding a New CLI Command

1. Create command in appropriate CLI file:

```python
@app.command()
def my_command(
    arg: str = typer.Argument(..., help="Description"),
    option: str = typer.Option("default", "--option", "-o"),
):
    """Command description."""
    console.print(f"Running with {arg}")
```

2. Add to `pyproject.toml` if new entry point needed:

```toml
[project.scripts]
dc-mycommand = "distributed_cluster.cli.my_cli:app"
```

### Adding a New API Endpoint

1. Add to `master/server.py`:

```python
@app.get("/my-endpoint")
async def my_endpoint(param: str = Query(None)):
    """Endpoint description."""
    return {"result": "data"}
```

2. Add to API documentation in `docs/API_REFERENCE.md`

3. Add integration test

---

## Questions?

- Open an issue for bugs or feature requests
- Join discussions for general questions
- Check existing issues before creating new ones

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Happy Contributing! 🚀**

نتمنى لك مساهمة سعيدة! 🚀
