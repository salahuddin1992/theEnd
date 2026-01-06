"""
Load Test Runner
================

Pytest-based load tests that can run without Locust server.
"""

import asyncio
import statistics
import time

import pytest


class TestLoadScenarios:
    """Load test scenarios using pytest."""

    @pytest.mark.asyncio
    async def test_burst_requests(self):
        """Test handling of burst traffic."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()
        burst_size = 100

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30.0) as client:
            # Send burst of requests
            start = time.perf_counter()
            tasks = [client.get("/health") for _ in range(burst_size)]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.perf_counter() - start

            successes = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)

            print(f"\nBurst test: {burst_size} requests")
            print(f"Completed in: {elapsed:.2f}s")
            print(f"Success rate: {successes/burst_size*100:.1f}%")
            print(f"Throughput: {burst_size/elapsed:.1f} req/s")

            assert successes / burst_size >= 0.95  # 95% success rate

    @pytest.mark.asyncio
    async def test_sustained_high_load(self):
        """Test under sustained high load."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()
        duration = 5  # seconds
        concurrency = 20

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=10.0) as client:
            results = {"success": 0, "failure": 0, "latencies": []}
            end_time = time.perf_counter() + duration

            async def worker():
                while time.perf_counter() < end_time:
                    start = time.perf_counter()
                    try:
                        response = await client.get("/health")
                        latency = (time.perf_counter() - start) * 1000
                        if response.status_code == 200:
                            results["success"] += 1
                            results["latencies"].append(latency)
                        else:
                            results["failure"] += 1
                    except Exception:
                        results["failure"] += 1

            # Run concurrent workers
            await asyncio.gather(*[worker() for _ in range(concurrency)])

            total = results["success"] + results["failure"]
            if results["latencies"]:
                avg_latency = statistics.mean(results["latencies"])
                p99_latency = sorted(results["latencies"])[int(len(results["latencies"]) * 0.99)]
            else:
                avg_latency = p99_latency = 0

            print(f"\nSustained load test ({duration}s, {concurrency} workers)")
            print(f"Total requests: {total}")
            print(f"Success rate: {results['success']/total*100:.1f}%" if total > 0 else "N/A")
            print(f"Throughput: {total/duration:.1f} req/s")
            print(f"Avg latency: {avg_latency:.2f}ms")
            print(f"P99 latency: {p99_latency:.2f}ms")

            assert results["success"] / total >= 0.99 if total > 0 else True

    @pytest.mark.asyncio
    async def test_mixed_workload(self):
        """Test with mixed read/write workload."""
        import random

        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()
        operations = 100

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30.0) as client:
            read_latencies = []
            write_latencies = []

            for _ in range(operations):
                if random.random() < 0.8:  # 80% reads
                    start = time.perf_counter()
                    await client.get("/health")
                    read_latencies.append((time.perf_counter() - start) * 1000)
                else:  # 20% writes
                    start = time.perf_counter()
                    await client.post(
                        "/api/v1/jobs", json={"command": "echo test", "resources": {"cpu_cores": 1, "memory_mb": 512}}
                    )
                    write_latencies.append((time.perf_counter() - start) * 1000)

            print(f"\nMixed workload test ({operations} operations)")
            print(f"Reads: {len(read_latencies)}, avg={statistics.mean(read_latencies):.2f}ms")
            print(
                f"Writes: {len(write_latencies)}, avg={statistics.mean(write_latencies):.2f}ms"
                if write_latencies
                else "No writes"
            )

    @pytest.mark.asyncio
    async def test_gradual_ramp_up(self):
        """Test gradual increase in load."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30.0) as client:
            results = []

            for concurrency in [1, 5, 10, 20, 50]:
                start = time.perf_counter()
                tasks = [client.get("/health") for _ in range(concurrency)]
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                elapsed = time.perf_counter() - start

                successes = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)

                results.append(
                    {
                        "concurrency": concurrency,
                        "success_rate": successes / concurrency,
                        "duration": elapsed,
                        "rps": concurrency / elapsed,
                    }
                )

            print("\nGradual ramp-up test:")
            print(f"{'Concurrency':>12} {'Success%':>10} {'Duration':>10} {'RPS':>10}")
            for r in results:
                print(f"{r['concurrency']:>12} {r['success_rate']*100:>9.1f}% {r['duration']:>9.3f}s {r['rps']:>9.1f}")

            # All levels should maintain high success rate
            for r in results:
                assert r["success_rate"] >= 0.95


class TestResourceExhaustion:
    """Test behavior under resource exhaustion."""

    @pytest.mark.asyncio
    async def test_connection_limit(self):
        """Test behavior when approaching connection limits."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()
        max_connections = 200

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=60.0) as client:
            # Try to create many concurrent connections
            tasks = [client.get("/health") for _ in range(max_connections)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successes = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)

            print(f"\nConnection limit test: {max_connections} concurrent")
            print(f"Successful: {successes}")
            print(f"Success rate: {successes/max_connections*100:.1f}%")

            # Should handle most connections gracefully
            assert successes / max_connections >= 0.90

    @pytest.mark.asyncio
    async def test_slow_client_simulation(self):
        """Test behavior with slow clients."""
        import random

        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30.0) as client:

            async def slow_client():
                await asyncio.sleep(random.uniform(0, 0.5))  # Variable delay
                return await client.get("/health")

            tasks = [slow_client() for _ in range(50)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successes = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)

            print("\nSlow client test: 50 clients with variable delays")
            print(f"Success rate: {successes/50*100:.1f}%")

            assert successes >= 45  # At least 90% success
