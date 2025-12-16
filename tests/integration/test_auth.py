"""
Authentication Integration Tests
================================

Tests for the security and authentication layer.
"""

import pytest
from datetime import datetime, timedelta

from distributed_cluster.security.auth import (
    AuthManager,
    AuthConfig,
    EnrollmentMode,
    Permission,
    Role,
    TokenPayload,
)


class TestAuthManager:
    """Tests for AuthManager."""

    def test_auth_manager_creation(self, auth_manager: AuthManager):
        """Test auth manager can be created."""
        assert auth_manager is not None
        assert auth_manager.config.enrollment_mode == EnrollmentMode.AUTO_APPROVE

    def test_generate_and_verify_token(self, auth_manager: AuthManager):
        """Test token generation and verification."""
        payload = TokenPayload(
            subject="user-123",
            role=Role.OPERATOR,
            permissions={Permission.SUBMIT_JOB, Permission.VIEW_JOBS},
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

        token = auth_manager.generate_token(payload)
        assert token is not None
        assert len(token) > 0

        verified = auth_manager.verify_token(token)
        assert verified is not None
        assert verified.subject == "user-123"
        assert verified.role == Role.OPERATOR

    def test_expired_token(self, auth_manager: AuthManager):
        """Test that expired tokens are rejected."""
        payload = TokenPayload(
            subject="user-123",
            role=Role.USER,
            permissions={Permission.VIEW_JOBS},
            issued_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )

        token = auth_manager.generate_token(payload)
        verified = auth_manager.verify_token(token)

        assert verified is None

    def test_invalid_token(self, auth_manager: AuthManager):
        """Test that invalid tokens are rejected."""
        verified = auth_manager.verify_token("invalid-token-string")
        assert verified is None

    def test_create_worker_token(self, auth_manager: AuthManager):
        """Test creating worker tokens."""
        token = auth_manager.create_worker_token("worker-1")

        assert token is not None

        verified = auth_manager.verify_token(token)
        assert verified is not None
        assert verified.subject == "worker-1"
        assert verified.role == Role.WORKER
        assert Permission.WORKER_HEARTBEAT in verified.permissions
        assert Permission.WORKER_POLL_JOBS in verified.permissions

    def test_create_user_token(self, auth_manager: AuthManager):
        """Test creating user tokens."""
        token = auth_manager.create_user_token("user-123", Role.OPERATOR)

        verified = auth_manager.verify_token(token)
        assert verified is not None
        assert verified.subject == "user-123"
        assert verified.role == Role.OPERATOR


class TestWorkerEnrollment:
    """Tests for worker enrollment."""

    def test_auto_approve_enrollment(self, auth_manager: AuthManager):
        """Test auto-approve enrollment mode."""
        success, message, token = auth_manager.enroll_worker(
            fingerprint="abc123def456",
            enrollment_token=None
        )

        assert success is True
        assert token is not None
        assert "approved" in message.lower() or "enrolled" in message.lower()

    def test_enrollment_with_token(self, temp_dir):
        """Test token-based enrollment."""
        config = AuthConfig(
            secret_key="test-secret",
            enrollment_mode=EnrollmentMode.TOKEN,
            enrollment_tokens={"valid-enrollment-token"},
        )
        auth = AuthManager(config)

        # Without token should fail
        success, message, token = auth.enroll_worker(
            fingerprint="abc123",
            enrollment_token=None
        )
        assert success is False

        # With valid token should succeed
        success, message, token = auth.enroll_worker(
            fingerprint="abc123",
            enrollment_token="valid-enrollment-token"
        )
        assert success is True
        assert token is not None

    def test_allowlist_enrollment(self, temp_dir):
        """Test allowlist-based enrollment."""
        config = AuthConfig(
            secret_key="test-secret",
            enrollment_mode=EnrollmentMode.ALLOWLIST,
            allowed_fingerprints={"allowed-fingerprint-1", "allowed-fingerprint-2"},
        )
        auth = AuthManager(config)

        # Non-allowed fingerprint should fail
        success, _, _ = auth.enroll_worker(
            fingerprint="not-in-allowlist",
            enrollment_token=None
        )
        assert success is False

        # Allowed fingerprint should succeed
        success, _, token = auth.enroll_worker(
            fingerprint="allowed-fingerprint-1",
            enrollment_token=None
        )
        assert success is True
        assert token is not None


class TestPermissions:
    """Tests for permission checking."""

    def test_role_permissions(self):
        """Test that roles have expected permissions."""
        # Admin should have all permissions
        admin_perms = Role.ADMIN.get_permissions()
        assert Permission.SUBMIT_JOB in admin_perms
        assert Permission.CANCEL_JOB in admin_perms
        assert Permission.MANAGE_WORKERS in admin_perms

        # User should have limited permissions
        user_perms = Role.USER.get_permissions()
        assert Permission.SUBMIT_JOB in user_perms
        assert Permission.VIEW_JOBS in user_perms
        assert Permission.MANAGE_WORKERS not in user_perms

        # Worker should have worker-specific permissions
        worker_perms = Role.WORKER.get_permissions()
        assert Permission.WORKER_HEARTBEAT in worker_perms
        assert Permission.WORKER_POLL_JOBS in worker_perms
        assert Permission.SUBMIT_JOB not in worker_perms

    def test_has_permission(self, auth_manager: AuthManager):
        """Test permission checking."""
        # Create admin token
        admin_token = auth_manager.create_user_token("admin-1", Role.ADMIN)
        admin_payload = auth_manager.verify_token(admin_token)

        assert auth_manager.has_permission(admin_payload, Permission.MANAGE_WORKERS)
        assert auth_manager.has_permission(admin_payload, Permission.VIEW_METRICS)

        # Create user token
        user_token = auth_manager.create_user_token("user-1", Role.USER)
        user_payload = auth_manager.verify_token(user_token)

        assert auth_manager.has_permission(user_payload, Permission.SUBMIT_JOB)
        assert not auth_manager.has_permission(user_payload, Permission.MANAGE_WORKERS)


class TestTokenPayload:
    """Tests for TokenPayload."""

    def test_token_payload_serialization(self):
        """Test TokenPayload to_dict and from_dict."""
        original = TokenPayload(
            subject="test-subject",
            role=Role.OPERATOR,
            permissions={Permission.SUBMIT_JOB, Permission.CANCEL_JOB},
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
            worker_id="worker-123",
            metadata={"custom": "value"},
        )

        data = original.to_dict()
        restored = TokenPayload.from_dict(data)

        assert restored.subject == original.subject
        assert restored.role == original.role
        assert restored.permissions == original.permissions
        assert restored.worker_id == original.worker_id
        assert restored.metadata == original.metadata

    def test_token_payload_is_expired(self):
        """Test is_expired method."""
        # Not expired
        valid = TokenPayload(
            subject="test",
            role=Role.USER,
            permissions=set(),
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert not valid.is_expired()

        # Expired
        expired = TokenPayload(
            subject="test",
            role=Role.USER,
            permissions=set(),
            issued_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert expired.is_expired()
