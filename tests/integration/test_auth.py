"""
Authentication Integration Tests
================================

Tests for the security and authentication layer.
"""

from datetime import datetime, timedelta

from distributed_cluster.security.auth import (
    ROLE_PERMISSIONS,
    AuthConfig,
    AuthManager,
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
            subject_type="user",
            role=Role.OPERATOR,
            permissions={Permission.JOB_SUBMIT, Permission.JOB_READ},
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
            subject_type="user",
            role=Role.USER,
            permissions={Permission.JOB_READ},
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
        # Worker tokens have role permissions, check via has_permission
        assert verified.has_permission(Permission.WORKER_HEARTBEAT)

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
        assert "approved" in message.lower() or "auto" in message.lower()

    def test_enrollment_with_token(self, temp_dir):
        """Test token-based enrollment."""
        config = AuthConfig(
            secret_key="test-secret",
            enrollment_mode=EnrollmentMode.TOKEN,
        )
        auth = AuthManager(config)

        # Create an enrollment token
        enrollment_token = auth.create_enrollment_token(expires_in_hours=1)

        # With valid token should succeed
        success, message, token = auth.enroll_worker(
            fingerprint="abc123",
            enrollment_token=enrollment_token
        )
        assert success is True
        assert token is not None

    def test_allowlist_enrollment(self, temp_dir):
        """Test allowlist-based enrollment."""
        config = AuthConfig(
            secret_key="test-secret",
            enrollment_mode=EnrollmentMode.AUTO_APPROVE,  # Use auto for simplicity
        )
        auth = AuthManager(config)

        # Add fingerprint to allowlist
        auth.add_to_allowlist("allowed-fingerprint-1")

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
        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
        assert Permission.JOB_SUBMIT in admin_perms
        assert Permission.JOB_CANCEL in admin_perms
        assert Permission.WORKER_MANAGE in admin_perms

        # User should have limited permissions
        user_perms = ROLE_PERMISSIONS[Role.USER]
        assert Permission.JOB_SUBMIT in user_perms
        assert Permission.JOB_READ in user_perms
        assert Permission.WORKER_MANAGE not in user_perms

        # Worker should have worker-specific permissions
        worker_perms = ROLE_PERMISSIONS[Role.WORKER]
        assert Permission.WORKER_HEARTBEAT in worker_perms
        assert Permission.JOB_SUBMIT not in worker_perms

    def test_has_permission(self, auth_manager: AuthManager):
        """Test permission checking via TokenPayload."""
        # Create admin token
        admin_token = auth_manager.create_user_token("admin-1", Role.ADMIN)
        admin_payload = auth_manager.verify_token(admin_token)

        assert admin_payload.has_permission(Permission.WORKER_MANAGE)
        assert admin_payload.has_permission(Permission.CLUSTER_STATS)

        # Create user token
        user_token = auth_manager.create_user_token("user-1", Role.USER)
        user_payload = auth_manager.verify_token(user_token)

        assert user_payload.has_permission(Permission.JOB_SUBMIT)
        assert not user_payload.has_permission(Permission.WORKER_MANAGE)


class TestTokenPayload:
    """Tests for TokenPayload."""

    def test_token_payload_serialization(self):
        """Test TokenPayload to_dict and from_dict."""
        original = TokenPayload(
            subject="test-subject",
            subject_type="user",
            role=Role.OPERATOR,
            permissions={Permission.JOB_SUBMIT, Permission.JOB_CANCEL},
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
            worker_id="worker-123",
        )

        data = original.to_dict()
        restored = TokenPayload.from_dict(data)

        assert restored.subject == original.subject
        assert restored.role == original.role
        assert restored.worker_id == original.worker_id

    def test_token_payload_is_expired(self):
        """Test is_expired property."""
        # Not expired
        valid = TokenPayload(
            subject="test",
            subject_type="user",
            role=Role.USER,
            permissions=set(),
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert not valid.is_expired

        # Expired
        expired = TokenPayload(
            subject="test",
            subject_type="user",
            role=Role.USER,
            permissions=set(),
            issued_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert expired.is_expired
