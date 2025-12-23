"""
Security Tests
==============

Tests for authentication, API keys, and audit logging.
"""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from distributed_cluster.security.auth import (
    AuthConfig,
    AuthManager,
    EnrollmentMode,
    Permission,
    Role,
)
from distributed_cluster.security.audit import (
    AuditAction,
    AuditEvent,
    AuditResult,
    AuditLogger,
    FileAuditBackend,
    MemoryAuditBackend,
)
from distributed_cluster.security.audit_backends import (
    SQLiteAuditBackend,
    CompositeAuditBackend,
    create_audit_backend,
)


class TestAuthManager:
    """Tests for AuthManager."""

    @pytest.fixture
    def auth_config(self):
        """Create test auth config."""
        return AuthConfig(
            secret_key="test-secret-key-minimum-32-characters-long",
            token_expiry_hours=24,
            enrollment_mode=EnrollmentMode.AUTO_APPROVE,
        )

    @pytest.fixture
    def auth_manager(self, auth_config):
        """Create test auth manager."""
        return AuthManager(auth_config)

    def test_generate_token(self, auth_manager):
        """Test token generation."""
        token = auth_manager.generate_token(
            worker_id="worker-123",
            role=Role.WORKER,
        )

        assert token is not None
        assert len(token) > 0

    def test_verify_token(self, auth_manager):
        """Test token verification."""
        token = auth_manager.generate_token(
            worker_id="worker-123",
            role=Role.WORKER,
        )

        payload = auth_manager.verify_token(token)

        assert payload is not None
        assert payload.worker_id == "worker-123"
        assert payload.role == Role.WORKER

    def test_verify_invalid_token(self, auth_manager):
        """Test verification of invalid token."""
        payload = auth_manager.verify_token("invalid-token")
        assert payload is None

    def test_check_permission(self, auth_manager):
        """Test permission checking."""
        # Admin should have all permissions
        assert auth_manager.check_permission(Role.ADMIN, Permission.READ)
        assert auth_manager.check_permission(Role.ADMIN, Permission.WRITE)
        assert auth_manager.check_permission(Role.ADMIN, Permission.ADMIN)

        # Worker should have limited permissions
        assert auth_manager.check_permission(Role.WORKER, Permission.READ)
        assert auth_manager.check_permission(Role.WORKER, Permission.EXECUTE)
        assert not auth_manager.check_permission(Role.WORKER, Permission.ADMIN)

    @pytest.mark.asyncio
    async def test_enroll_worker(self, auth_manager):
        """Test worker enrollment."""
        result = await auth_manager.enroll_worker("worker-new")

        assert result is not None
        assert result.worker_id == "worker-new"
        assert result.approved is True  # AUTO_APPROVE mode

    def test_api_key_management(self, auth_manager):
        """Test API key creation and verification."""
        # Create API key
        api_key = auth_manager.create_api_key(
            name="test-key",
            permissions=[Permission.READ, Permission.WRITE],
        )

        assert api_key is not None
        assert len(api_key) > 0

        # Get key info
        info = auth_manager.get_api_key_info(api_key)
        assert info is not None
        assert info["name"] == "test-key"
        assert Permission.READ in info["permissions"]

        # List keys
        keys = auth_manager.list_api_keys()
        assert len(keys) >= 1

        # Revoke
        assert auth_manager.revoke_api_key(api_key) is True
        assert auth_manager.get_api_key_info(api_key) is None


class TestAuditLogging:
    """Tests for audit logging."""

    def test_audit_event_creation(self):
        """Test creating audit events."""
        event = AuditEvent(
            action=AuditAction.JOB_SUBMITTED,
            actor_id="user-123",
            resource_id="job-456",
            result=AuditResult.SUCCESS,
            details={"priority": "high"},
        )

        assert event.action == AuditAction.JOB_SUBMITTED
        assert event.actor_id == "user-123"
        assert event.result == AuditResult.SUCCESS

    @pytest.mark.asyncio
    async def test_memory_backend(self):
        """Test memory audit backend."""
        backend = MemoryAuditBackend(max_events=100)

        event = AuditEvent(
            action=AuditAction.WORKER_REGISTERED,
            actor_id="system",
            resource_id="worker-1",
            result=AuditResult.SUCCESS,
        )

        await backend.write(event)

        # Query
        events = await backend.query()
        assert len(events) >= 1

        # Count
        count = await backend.count()
        assert count >= 1

    @pytest.mark.asyncio
    async def test_file_backend(self, tmp_path):
        """Test file audit backend."""
        log_file = tmp_path / "audit.log"
        backend = FileAuditBackend(str(log_file))

        event = AuditEvent(
            action=AuditAction.JOB_COMPLETED,
            actor_id="worker-1",
            resource_id="job-123",
            result=AuditResult.SUCCESS,
        )

        await backend.write(event)

        # File should exist and contain event
        assert log_file.exists()
        content = log_file.read_text()
        assert "JOB_COMPLETED" in content

    @pytest.mark.asyncio
    async def test_audit_logger(self):
        """Test AuditLogger wrapper."""
        backend = MemoryAuditBackend()
        logger = AuditLogger(backend)

        # Log various events
        await logger.log_job_submitted("job-1", "user-1")
        await logger.log_job_completed("job-1", "worker-1", success=True)
        await logger.log_worker_registered("worker-1")

        events = await backend.query()
        assert len(events) == 3


class TestAuditBackends:
    """Tests for audit backends."""

    @pytest.mark.asyncio
    async def test_sqlite_backend(self, tmp_path):
        """Test SQLite audit backend."""
        db_path = tmp_path / "audit.db"
        backend = SQLiteAuditBackend(str(db_path))

        await backend.initialize()

        event = AuditEvent(
            action=AuditAction.AUTH_LOGIN,
            actor_id="user-1",
            resource_id="session-1",
            result=AuditResult.SUCCESS,
            ip_address="192.168.1.1",
        )

        await backend.write(event)

        # Query all
        events = await backend.query()
        assert len(events) >= 1

        # Query by action
        events = await backend.query(action=AuditAction.AUTH_LOGIN)
        assert len(events) >= 1

        # Query by actor
        events = await backend.query(actor_id="user-1")
        assert len(events) >= 1

        # Count
        count = await backend.count()
        assert count >= 1

        await backend.close()

    @pytest.mark.asyncio
    async def test_composite_backend(self, tmp_path):
        """Test composite audit backend."""
        memory = MemoryAuditBackend()
        file_path = tmp_path / "audit.log"
        file_backend = FileAuditBackend(str(file_path))

        composite = CompositeAuditBackend([memory, file_backend])

        event = AuditEvent(
            action=AuditAction.API_CALL,
            actor_id="user-1",
            resource_id="/api/jobs",
            result=AuditResult.SUCCESS,
        )

        await composite.write(event)

        # Both backends should have the event
        assert await memory.count() >= 1
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_create_audit_backend(self, tmp_path):
        """Test factory function."""
        # Memory backend
        backend = await create_audit_backend("memory")
        assert isinstance(backend, MemoryAuditBackend)

        # File backend
        log_file = tmp_path / "audit.log"
        backend = await create_audit_backend("file", path=str(log_file))
        assert isinstance(backend, FileAuditBackend)

        # SQLite backend
        db_file = tmp_path / "audit.db"
        backend = await create_audit_backend("sqlite", path=str(db_file))
        assert isinstance(backend, SQLiteAuditBackend)
        await backend.close()


class TestRoles:
    """Tests for role definitions."""

    def test_role_values(self):
        """Test role enum values."""
        assert Role.ADMIN.value == "admin"
        assert Role.WORKER.value == "worker"
        assert Role.USER.value == "user"

    def test_permission_values(self):
        """Test permission enum values."""
        assert Permission.READ.value == "read"
        assert Permission.WRITE.value == "write"
        assert Permission.EXECUTE.value == "execute"
        assert Permission.ADMIN.value == "admin"
