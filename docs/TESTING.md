# Testing Guide

Comprehensive guide to testing NebulaCompute.

## Table of Contents

- [Test Organization](#test-organization)
- [Running Tests](#running-tests)
- [Test Types](#test-types)
- [Writing Tests](#writing-tests)
- [Test Configuration](#test-configuration)
- [CI/CD Integration](#cicd-integration)
- [Coverage](#coverage)
- [Best Practices](#best-practices)

## Test Organization

```
tests/
├── unit/                    # Unit tests
│   ├── test_scheduler.py
│   ├── test_security.py
│   ├── test_worker_metrics.py
│   ├── test_resources.py
│   ├── test_web.py
│   ├── test_mesh.py
│   ├── test_logging.py
│   └── test_tracing.py
│
├── integration/             # Integration tests
│   ├── test_scheduler.py
│   ├── test_auth.py
│   ├── test_database.py
│   ├── test_lease.py
│   └── test_resilience.py
│
├── e2e/                     # End-to-end tests
│   └── tests/
│       ├── dashboard.spec.ts
│       ├── auth.spec.ts
│       └── api.spec.ts
│
├── performance/             # Performance benchmarks
│   ├── test_scheduler_performance.py
│   └── test_api_benchmark.py
│
├── load/                    # Load tests
│   ├── locustfile.py
│   └── test_load.py
│
├── security/                # Security tests
│   ├── test_api_security.py
│   └── test_crypto_security.py
│
├── fuzz/                    # Fuzz tests
│   ├── test_model_fuzzing.py
│   └── test_protocol_fuzzing.py
│
└── conftest.py              # Shared fixtures
```

## Running Tests

### Quick Start

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/distributed_cluster

# Run specific test file
pytest tests/unit/test_scheduler.py

# Run specific test
pytest tests/unit/test_scheduler.py::test_schedule_job
```

### Test Categories

```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Performance tests
pytest tests/performance/

# Security tests
pytest tests/security/

# Fuzz tests
pytest tests/fuzz/
```

### Test Markers

```bash
# Run slow tests
pytest -m slow

# Skip slow tests
pytest -m "not slow"

# Run async tests only
pytest -m asyncio

# Run GPU tests (if available)
pytest -m gpu
```

### Parallel Execution

```bash
# Run tests in parallel
pytest -n auto

# Use specific number of workers
pytest -n 4
```

### Verbose Output

```bash
# Verbose output
pytest -v

# Very verbose
pytest -vv

# Show print statements
pytest -s
```

## Test Types

### Unit Tests

Test individual components in isolation.

```python
# tests/unit/test_scheduler.py
import pytest
from distributed_cluster.scheduler import Scheduler, SchedulingPolicy

class TestScheduler:
    def test_create_scheduler(self):
        scheduler = Scheduler(policy=SchedulingPolicy.BEST_FIT)
        assert scheduler is not None
        assert scheduler.policy == SchedulingPolicy.BEST_FIT

    def test_register_worker(self, sample_worker):
        scheduler = Scheduler(policy=SchedulingPolicy.BEST_FIT)
        scheduler.register_worker(sample_worker)
        assert sample_worker.worker_id in scheduler.workers
```

### Integration Tests

Test component interactions.

```python
# tests/integration/test_database.py
import pytest
from distributed_cluster.storage.database import SQLiteDatabase

@pytest.mark.asyncio
async def test_job_persistence(database):
    job = create_test_job()
    await database.save_job(job)

    retrieved = await database.get_job(job.job_id)
    assert retrieved.job_id == job.job_id
    assert retrieved.command == job.command
```

### E2E Tests

Test complete workflows using Playwright.

```typescript
// tests/e2e/tests/dashboard.spec.ts
import { test, expect } from '@playwright/test';

test('dashboard loads successfully', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('h1')).toContainText('NebulaCompute');
  await expect(page.locator('[data-testid="cluster-status"]')).toBeVisible();
});
```

### Performance Tests

Benchmark critical paths.

```python
# tests/performance/test_scheduler_performance.py
def test_scheduling_throughput(benchmark, scheduler, many_jobs):
    def schedule_all():
        for job in many_jobs:
            scheduler.schedule_job(job)

    result = benchmark(schedule_all)
    assert result is not None
```

### Load Tests

Stress test the system using Locust.

```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class ClusterUser(HttpUser):
    wait_time = between(0.5, 2)

    @task(10)
    def health_check(self):
        self.client.get("/health")

    @task(2)
    def submit_job(self):
        self.client.post("/api/v1/jobs", json={
            "command": "echo test",
            "resources": {"cpu_cores": 1, "memory_mb": 512}
        })
```

### Security Tests

Validate security measures.

```python
# tests/security/test_api_security.py
@pytest.mark.asyncio
async def test_sql_injection_prevention(client):
    payloads = ["'; DROP TABLE jobs;--", "1' OR '1'='1"]
    for payload in payloads:
        response = await client.get(f"/api/v1/jobs?search={payload}")
        assert response.status_code != 500
```

### Fuzz Tests

Property-based testing with Hypothesis.

```python
# tests/fuzz/test_model_fuzzing.py
from hypothesis import given, strategies as st

@given(
    cpu=st.integers(min_value=1, max_value=1024),
    memory=st.integers(min_value=512, max_value=1048576)
)
def test_resource_spec_fuzzing(cpu, memory):
    spec = ResourceSpec(cpu_cores=cpu, memory_mb=memory)
    assert spec.cpu_cores == cpu
```

## Writing Tests

### Using Fixtures

```python
# tests/conftest.py
import pytest
from distributed_cluster.scheduler import Scheduler

@pytest.fixture
def scheduler():
    """Create test scheduler."""
    return Scheduler(policy=SchedulingPolicy.BEST_FIT)

@pytest.fixture
def sample_job():
    """Create sample job."""
    return JobSubmission(
        command="echo test",
        resources=ResourceSpec(cpu_cores=2, memory_mb=1024),
        priority=JobPriority.NORMAL,
    )
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result is not None
```

### Parametrized Tests

```python
@pytest.mark.parametrize("policy,expected", [
    (SchedulingPolicy.FIRST_FIT, "first_fit"),
    (SchedulingPolicy.BEST_FIT, "best_fit"),
    (SchedulingPolicy.ROUND_ROBIN, "round_robin"),
])
def test_policy_names(policy, expected):
    assert policy.value == expected
```

### Mocking

```python
from unittest.mock import Mock, patch

def test_with_mock():
    with patch('distributed_cluster.worker.docker') as mock_docker:
        mock_docker.from_env.return_value = Mock()
        worker = Worker()
        assert worker.docker_available
```

## Test Configuration

### pytest.ini / pyproject.toml

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "slow: marks tests as slow",
    "gpu: marks tests requiring GPU",
    "integration: marks integration tests",
]
filterwarnings = [
    "ignore::DeprecationWarning",
]
```

### conftest.py

```python
# tests/conftest.py
import pytest
import asyncio

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def temp_dir(tmp_path):
    """Provide temporary directory."""
    return tmp_path
```

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run tests
        run: pytest --cov=src/distributed_cluster --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest tests/unit/ -x -q
        language: system
        pass_filenames: false
        always_run: true
```

## Coverage

### Running with Coverage

```bash
# Generate coverage report
pytest --cov=src/distributed_cluster --cov-report=html

# Open report
open htmlcov/index.html
```

### Coverage Configuration

```toml
# pyproject.toml
[tool.coverage.run]
source = ["src/distributed_cluster"]
omit = ["*/tests/*", "*/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
fail_under = 80
```

## Best Practices

### 1. Test Naming

```python
# Good
def test_scheduler_assigns_job_to_available_worker():
    ...

def test_scheduler_rejects_job_when_no_resources():
    ...

# Avoid
def test_scheduler():  # Too vague
    ...
```

### 2. Arrange-Act-Assert

```python
def test_job_completion():
    # Arrange
    scheduler = Scheduler()
    job = create_test_job()
    worker = create_test_worker()
    scheduler.register_worker(worker)

    # Act
    result = scheduler.schedule_job(job)

    # Assert
    assert result is not None
    assert result.worker_id == worker.worker_id
```

### 3. One Assertion Per Concept

```python
# Good - testing one concept
def test_job_is_assigned_to_worker():
    result = scheduler.schedule_job(job)
    assert result.worker_id is not None

def test_job_status_is_scheduled():
    result = scheduler.schedule_job(job)
    assert result.status == JobStatus.SCHEDULED

# Avoid - multiple unrelated assertions
def test_job_scheduling():
    result = scheduler.schedule_job(job)
    assert result.worker_id is not None
    assert result.status == JobStatus.SCHEDULED
    assert scheduler.pending_jobs == 0
```

### 4. Independent Tests

```python
# Good - each test is independent
def test_first_job():
    scheduler = Scheduler()
    ...

def test_second_job():
    scheduler = Scheduler()  # Fresh instance
    ...
```

### 5. Fast Tests

```python
# Use mocks for slow operations
@patch('distributed_cluster.network.httpx.AsyncClient')
async def test_with_mock_network(mock_client):
    mock_client.get.return_value = Mock(status_code=200)
    ...
```

## See Also

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [CI/CD Configuration](../.github/workflows/)
