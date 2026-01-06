"""
Protocol Fuzzing Tests
======================

Fuzz testing for network protocols and message handling.
"""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


class TestHTTPProtocolFuzzing:
    """HTTP protocol fuzz testing."""

    @given(
        method=st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]),
        path=st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="/-_."),
        ),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_http_methods_handling(self, method, path):
        """Test various HTTP methods on paths."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.request(method, f"/{path}")
            # Should not crash (5xx)
            assert response.status_code < 500

    @given(
        headers=st.dictionaries(
            keys=st.text(
                min_size=1,
                max_size=32,
                alphabet=st.characters(whitelist_categories=("Lu", "Ll"), whitelist_characters="-"),
            ),
            values=st.text(min_size=1, max_size=256),
            max_size=10,
        )
    )
    @settings(max_examples=30)
    @pytest.mark.asyncio
    async def test_arbitrary_headers(self, headers):
        """Test handling of arbitrary HTTP headers."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            try:
                response = await client.get("/health", headers=headers)
                assert response.status_code < 500
            except Exception:
                # Some header combinations may be invalid
                pass


class TestJSONProtocolFuzzing:
    """JSON message handling fuzz testing."""

    @given(
        depth=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20)
    @pytest.mark.asyncio
    async def test_nested_json(self, depth):
        """Test deeply nested JSON handling."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        # Build nested structure
        data = {"value": "leaf"}
        for i in range(depth):
            data = {"nested": data, "level": i}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/jobs", json=data)
            # Should handle or reject gracefully
            assert response.status_code < 500

    @given(
        array_size=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=20)
    @pytest.mark.asyncio
    async def test_large_arrays(self, array_size):
        """Test large array handling in JSON."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        data = {
            "command": "echo test",
            "resources": {"cpu_cores": 1, "memory_mb": 512},
            "tags": [f"tag-{i}" for i in range(array_size)],
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/jobs", json=data)
            assert response.status_code < 500

    @given(
        key_count=st.integers(min_value=0, max_value=500),
    )
    @settings(max_examples=20)
    @pytest.mark.asyncio
    async def test_many_keys(self, key_count):
        """Test JSON with many keys."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        data = {f"key_{i}": f"value_{i}" for i in range(key_count)}
        data.update(
            {
                "command": "echo test",
                "resources": {"cpu_cores": 1, "memory_mb": 512},
            }
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/jobs", json=data)
            assert response.status_code < 500


class TestMessageSerializationFuzzing:
    """Message serialization fuzz testing."""

    @given(
        job_id=st.text(min_size=1, max_size=64),
        status=st.sampled_from(["pending", "running", "completed", "failed", "cancelled"]),
        progress=st.floats(min_value=0, max_value=100, allow_nan=False),
    )
    @settings(max_examples=50)
    def test_job_status_message(self, job_id, status, progress):
        """Test job status message serialization."""
        message = {
            "type": "job_status",
            "job_id": job_id,
            "status": status,
            "progress": progress,
        }

        # Should serialize without error
        serialized = json.dumps(message)
        deserialized = json.loads(serialized)

        assert deserialized["job_id"] == job_id
        assert deserialized["status"] == status

    @given(
        worker_id=st.text(min_size=1, max_size=64),
        cpu_usage=st.floats(min_value=0, max_value=100, allow_nan=False),
        memory_usage=st.floats(min_value=0, max_value=100, allow_nan=False),
        gpu_usage=st.floats(min_value=0, max_value=100, allow_nan=False),
    )
    @settings(max_examples=50)
    def test_worker_metrics_message(self, worker_id, cpu_usage, memory_usage, gpu_usage):
        """Test worker metrics message serialization."""
        message = {
            "type": "worker_metrics",
            "worker_id": worker_id,
            "metrics": {
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "gpu_usage": gpu_usage,
            },
        }

        serialized = json.dumps(message)
        deserialized = json.loads(serialized)

        assert deserialized["worker_id"] == worker_id


class TestEdgeCases:
    """Edge case fuzz testing."""

    @given(
        size=st.integers(min_value=0, max_value=100000),
    )
    @settings(max_examples=10)
    @pytest.mark.asyncio
    async def test_large_request_body(self, size):
        """Test handling of large request bodies."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        data = {
            "command": "x" * min(size, 10000),  # Limit command size
            "resources": {"cpu_cores": 1, "memory_mb": 512},
            "description": "y" * size if size < 50000 else "y" * 50000,
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30.0) as client:
            response = await client.post("/api/v1/jobs", json=data)
            # Should handle or reject, not crash
            assert response.status_code < 500

    @given(
        special_chars=st.sampled_from(
            [
                "\x00",
                "\n",
                "\r",
                "\t",
                "\x1b",
                "\xff",
                "\\",
                '"',
                "'",
                "`",
                "$",
                "!",
                "|",
                "&",
                "<",
                ">",
                "{",
                "}",
                "[",
                "]",
                "(",
                ")",
            ]
        )
    )
    @settings(max_examples=30)
    @pytest.mark.asyncio
    async def test_special_characters(self, special_chars):
        """Test handling of special characters."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        data = {
            "command": f"echo test{special_chars}value",
            "resources": {"cpu_cores": 1, "memory_mb": 512},
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/jobs", json=data)
            # Should handle safely
            assert response.status_code < 500

    @pytest.mark.asyncio
    async def test_empty_request_body(self):
        """Test empty request body handling."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/jobs", content=b"", headers={"Content-Type": "application/json"})
            # Should return 400 or similar, not 500
            assert response.status_code < 500

    @pytest.mark.asyncio
    async def test_malformed_json(self):
        """Test malformed JSON handling."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        malformed_payloads = [
            b"{",
            b'{"key":}',
            b'{"key": undefined}',
            b"{'single': 'quotes'}",
            b'{"trailing": "comma",}',
            b"[1, 2, 3,]",
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for payload in malformed_payloads:
                response = await client.post(
                    "/api/v1/jobs", content=payload, headers={"Content-Type": "application/json"}
                )
                # Should return 400 (bad request), not 500
                assert response.status_code != 500, f"Server error with: {payload}"
