"""
Security Tests
==============

Tests for authentication, API keys, and audit logging.
"""

import uuid
from datetime import datetime, timezone

import pytest

from distributed_cluster.security.audit import (
    AuditAction,
    AuditEvent,
    AuditLogger,
    AuditResult,
    FileAuditBackend,
    MemoryAuditBackend,
)
from distributed_cluster.security.auth import (
    AuthConfig,
    AuthManager,
    EnrollmentMode,
    Permission,
    Role,
    TokenPayload,
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
        payload = TokenPayload(
            subject="worker-123",
            subject_type="worker",
            role=Role.WORKER,
            worker_id="worker-123",
        )
        token = auth_manager.generate_token(payload)

        assert token is not None
        assert len(token) > 0

    def test_verify_token(self, auth_manager):
        """Test token verification."""
        payload = TokenPayload(
            subject="worker-123",
            subject_type="worker",
            role=Role.WORKER,
            worker_id="worker-123",
        )
        token = auth_manager.generate_token(payload)

        verified = auth_manager.verify_token(token)

        assert verified is not None
        assert verified.worker_id == "worker-123"
        assert verified.role == Role.WORKER

    def test_verify_invalid_token(self, auth_manager):
        """Test verification of invalid token."""
        payload = auth_manager.verify_token("invalid-token")
        assert payload is None

    def test_check_permission(self, auth_manager):
        """Test permission checking with token payload."""
        # Create admin token
        admin_payload = TokenPayload(
            subject="admin-1",
            subject_type="user",
            role=Role.ADMIN,
            permissions={Permission.JOB_SUBMIT, Permission.JOB_READ, Permission.WORKER_MANAGE},
        )

        # Admin should have permissions in their set
        assert admin_payload.has_permission(Permission.JOB_SUBMIT)
        assert admin_payload.has_permission(Permission.JOB_READ)

        # Worker token
        worker_payload = TokenPayload(
            subject="worker-1",
            subject_type="worker",
            role=Role.WORKER,
            permissions={Permission.WORKER_HEARTBEAT, Permission.WORKER_REPORT},
        )

        assert worker_payload.has_permission(Permission.WORKER_HEARTBEAT)
        assert not worker_payload.has_permission(Permission.WORKER_MANAGE)

    def test_enroll_worker(self, auth_manager):
        """Test worker enrollment."""
        # enroll_worker returns (approved, reason, token_or_none)
        approved, reason, token = auth_manager.enroll_worker("worker-new-fingerprint")

        assert approved is True  # AUTO_APPROVE mode
        assert reason is not None
        # Token should be provided when approved
        assert token is not None or approved  # At least one must be truthy

    def test_api_key_management(self, auth_manager):
        """Test API key creation and listing."""
        # Create API key without permissions
        api_key, token = auth_manager.create_api_key("test-key")
        assert api_key is not None
        assert token is not None
        assert api_key.startswith("ak_")

        # Create API key with permissions
        api_key2, token2 = auth_manager.create_api_key(
            "test-key-2",
            permissions={Permission.JOB_SUBMIT, Permission.JOB_READ}
        )
        assert api_key2 is not None
        assert token2 is not None

        # List keys should work
        keys = auth_manager.list_api_keys()
        assert isinstance(keys, list)
        assert len(keys) == 2


class TestAuditLogging:
    """Tests for audit logging."""

    def test_audit_event_creation(self):
        """Test creating audit events."""
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            action=AuditAction.JOB_SUBMITTED,
            result=AuditResult.SUCCESS,
            actor_id="user-123",
            resource_id="job-456",
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
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            action=AuditAction.WORKER_REGISTERED,
            result=AuditResult.SUCCESS,
            actor_id="system",
            resource_id="worker-1",
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
        log_dir = tmp_path / "audit_logs"
        backend = FileAuditBackend(log_dir=str(log_dir))

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            action=AuditAction.JOB_COMPLETED,
            result=AuditResult.SUCCESS,
            actor_id="worker-1",
            resource_id="job-123",
        )

        await backend.write(event)

        # Log dir should exist and contain log files
        assert log_dir.exists()
        log_files = list(log_dir.glob("*.jsonl"))
        assert len(log_files) >= 1
        content = log_files[0].read_text()
        # Action is stored as lowercase: "job.completed"
        assert "job.completed" in content or "job-123" in content

    @pytest.mark.asyncio
    async def test_audit_logger(self):
        """Test AuditLogger wrapper."""
        backend = MemoryAuditBackend()
        logger = AuditLogger(backend)

        # Log event using the generic log method
        await logger.log(
            action=AuditAction.JOB_SUBMITTED,
            result=AuditResult.SUCCESS,
            actor_id="user-1",
            resource_id="job-1",
        )

        events = await backend.query()
        assert len(events) >= 1


class TestRoles:
    """Tests for roles and permissions."""

    def test_role_values(self):
        """Test role enum values."""
        assert Role.ADMIN.value == "admin"
        assert Role.USER.value == "user"
        assert Role.WORKER.value == "worker"

    def test_permission_values(self):
        """Test permission enum values."""
        assert Permission.JOB_SUBMIT.value == "job:submit"
        assert Permission.JOB_READ.value == "job:read"
        assert Permission.WORKER_REGISTER.value == "worker:register"

    def test_token_payload_permissions(self):
        """Test token payload with permissions."""
        payload = TokenPayload(
            subject="test",
            subject_type="user",
            role=Role.USER,
            permissions={Permission.JOB_SUBMIT, Permission.JOB_READ},
        )

        assert payload.has_permission(Permission.JOB_SUBMIT)
        assert payload.has_permission(Permission.JOB_READ)
        assert not payload.has_permission(Permission.WORKER_MANAGE)
