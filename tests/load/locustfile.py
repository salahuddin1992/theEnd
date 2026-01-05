"""
Locust Load Tests
=================

Load testing scenarios for the distributed cluster API.

Run with:
    locust -f tests/load/locustfile.py --host=http://localhost:8000

Or headless:
    locust -f tests/load/locustfile.py --host=http://localhost:8000 \
           --users=100 --spawn-rate=10 --run-time=60s --headless
"""

import json
import random
import string
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner


class ClusterAPIUser(HttpUser):
    """Simulates a typical cluster API user."""

    wait_time = between(0.5, 2.0)  # Wait between requests

    def on_start(self):
        """Called when user starts."""
        self.job_ids = []

    @task(10)
    def health_check(self):
        """Check cluster health - most common operation."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(5)
    def get_cluster_status(self):
        """Get cluster status."""
        self.client.get("/api/v1/cluster/status")

    @task(5)
    def list_workers(self):
        """List all workers."""
        self.client.get("/api/v1/workers")

    @task(3)
    def list_jobs(self):
        """List jobs with pagination."""
        page = random.randint(1, 5)
        self.client.get(f"/api/v1/jobs?page={page}&per_page=20")

    @task(2)
    def submit_job(self):
        """Submit a new job."""
        job_data = {
            "command": f"python -c 'import time; time.sleep({random.uniform(0.1, 1.0)})'",
            "resources": {
                "cpu_cores": random.randint(1, 4),
                "memory_mb": random.choice([512, 1024, 2048, 4096]),
            },
            "priority": random.choice(["low", "normal", "high"]),
            "timeout_seconds": random.randint(30, 300),
            "environment": {"LOAD_TEST": "true"},
            "tags": ["load-test"],
        }

        with self.client.post(
            "/api/v1/jobs",
            json=job_data,
            catch_response=True
        ) as response:
            if response.status_code in [200, 201, 202]:
                try:
                    data = response.json()
                    if "job_id" in data:
                        self.job_ids.append(data["job_id"])
                    response.success()
                except Exception:
                    response.success()  # Accept any 2xx
            else:
                response.failure(f"Job submission failed: {response.status_code}")

    @task(3)
    def get_job_status(self):
        """Get status of a submitted job."""
        if self.job_ids:
            job_id = random.choice(self.job_ids)
            self.client.get(f"/api/v1/jobs/{job_id}")

    @task(2)
    def get_metrics(self):
        """Get Prometheus metrics."""
        self.client.get("/metrics")

    @task(1)
    def get_worker_stats(self):
        """Get detailed worker statistics."""
        self.client.get("/api/v1/workers/stats")


class HeavyJobSubmitter(HttpUser):
    """User that primarily submits jobs."""

    wait_time = between(0.1, 0.5)
    weight = 3  # Less common user type

    @task
    def submit_heavy_job(self):
        """Submit resource-intensive jobs."""
        job_data = {
            "command": "python -c 'import numpy as np; np.random.rand(1000, 1000)'",
            "resources": {
                "cpu_cores": random.randint(4, 16),
                "memory_mb": random.choice([4096, 8192, 16384]),
                "gpu_count": random.choice([0, 0, 0, 1]),  # 25% GPU jobs
            },
            "priority": "high",
            "timeout_seconds": 600,
        }

        self.client.post("/api/v1/jobs", json=job_data)


class MonitoringUser(HttpUser):
    """User that primarily monitors the cluster."""

    wait_time = between(1.0, 3.0)
    weight = 2

    @task(5)
    def get_metrics(self):
        """Scrape metrics endpoint like Prometheus."""
        self.client.get("/metrics")

    @task(3)
    def get_health(self):
        """Health check like a load balancer."""
        self.client.get("/health")

    @task(2)
    def get_dashboard_data(self):
        """Get data for dashboard."""
        self.client.get("/api/v1/cluster/status")
        self.client.get("/api/v1/workers")
        self.client.get("/api/v1/jobs?status=running")


class WebSocketUser(HttpUser):
    """Test WebSocket connections (simulated via polling)."""

    wait_time = between(0.5, 1.0)
    weight = 1

    @task
    def poll_updates(self):
        """Simulate polling for real-time updates."""
        self.client.get("/api/v1/cluster/status")
        self.client.get("/api/v1/jobs?status=running&limit=10")


# Event handlers for custom reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    print("=" * 60)
    print("Starting load test")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    print("=" * 60)
    print("Load test completed")
    print("=" * 60)


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Called on each request - can be used for custom metrics."""
    pass


# Custom shape for ramping users
class StagesShape:
    """
    Custom load shape for staged testing.

    Usage:
        locust -f locustfile.py --host=http://localhost:8000 --class-picker
    """

    stages = [
        {"duration": 60, "users": 10, "spawn_rate": 2},
        {"duration": 120, "users": 50, "spawn_rate": 5},
        {"duration": 180, "users": 100, "spawn_rate": 10},
        {"duration": 240, "users": 50, "spawn_rate": 10},
        {"duration": 300, "users": 10, "spawn_rate": 10},
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])

        return None
