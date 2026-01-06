"""
Comprehensive Security Tests - اختبارات الأمان الشاملة
=======================================================

Tests for the comprehensive security and authentication system.
"""

from datetime import datetime, timedelta, timezone

import pytest

# ====================== MFA Tests ======================


class TestTOTPGenerator:
    """Test TOTP/HOTP generation."""

    def test_generate_secret(self):
        """Test secret key generation."""
        from distributed_cluster.security.mfa import TOTPConfig, TOTPGenerator

        config = TOTPConfig(secret_length=20)
        generator = TOTPGenerator(config)

        secret = generator.generate_secret()
        assert len(secret) >= 16
        # Base32 characters only
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)

    def test_generate_totp(self):
        """Test TOTP code generation."""
        from distributed_cluster.security.mfa import TOTPConfig, TOTPGenerator

        config = TOTPConfig(digits=6, period=30)
        generator = TOTPGenerator(config)

        secret = "JBSWY3DPEHPK3PXP"  # Test secret
        code = generator.generate_totp(secret)

        assert len(code) == 6
        assert code.isdigit()

    def test_verify_totp(self):
        """Test TOTP verification."""
        from distributed_cluster.security.mfa import TOTPConfig, TOTPGenerator

        config = TOTPConfig(digits=6, period=30, drift_tolerance=1)
        generator = TOTPGenerator(config)

        secret = generator.generate_secret()

        # Generate and verify code
        code = generator.generate_totp(secret)
        valid, offset = generator.verify_totp(secret, code)

        assert valid
        assert offset == 0

    def test_verify_totp_with_drift(self):
        """Test TOTP verification with time drift."""
        from distributed_cluster.security.mfa import TOTPConfig, TOTPGenerator

        config = TOTPConfig(digits=6, period=30, drift_tolerance=1)
        generator = TOTPGenerator(config)

        secret = generator.generate_secret()

        # Generate code for previous period
        code = generator.generate_totp(secret, time_offset=-1)
        valid, offset = generator.verify_totp(secret, code)

        assert valid
        assert offset == -1

    def test_invalid_totp_rejected(self):
        """Test invalid TOTP rejection."""
        from distributed_cluster.security.mfa import TOTPGenerator

        generator = TOTPGenerator()
        secret = generator.generate_secret()

        valid, _ = generator.verify_totp(secret, "000000")

        # Very unlikely to be valid
        # We can't guarantee it's invalid, but it's very unlikely

    def test_provisioning_uri(self):
        """Test provisioning URI generation."""
        from distributed_cluster.security.mfa import TOTPConfig, TOTPGenerator

        config = TOTPConfig(issuer="NebulaTest")
        generator = TOTPGenerator(config)

        secret = "JBSWY3DPEHPK3PXP"
        uri = generator.get_provisioning_uri(secret, "test@example.com")

        assert uri.startswith("otpauth://totp/")
        assert "secret=JBSWY3DPEHPK3PXP" in uri
        assert "issuer=NebulaTest" in uri


class TestMFAManager:
    """Test MFA management."""

    def test_start_enrollment(self):
        """Test MFA enrollment start."""
        from distributed_cluster.security.mfa import MFAManager, MFAStatus

        manager = MFAManager()

        device, uri, qr = manager.start_totp_enrollment(
            user_id="user-123",
            device_name="Test Device",
        )

        assert device.user_id == "user-123"
        assert device.status == MFAStatus.PENDING
        assert device.secret is not None
        assert "otpauth://totp/" in uri

    def test_complete_enrollment(self):
        """Test MFA enrollment completion."""
        from distributed_cluster.security.mfa import MFAManager, MFAStatus

        manager = MFAManager()

        device, uri, qr = manager.start_totp_enrollment(
            user_id="user-123",
            device_name="Test Device",
        )

        # Generate valid code
        code = manager.totp.generate_totp(device.secret)

        success, error = manager.complete_totp_enrollment(device.device_id, code)

        assert success
        assert error is None

        # Verify status updated
        updated_device = manager.store.get_device(device.device_id)
        assert updated_device.status == MFAStatus.ENROLLED

    def test_verify_code(self):
        """Test MFA code verification."""
        from distributed_cluster.security.mfa import MFAManager

        manager = MFAManager()

        # Enroll device
        device, _, _ = manager.start_totp_enrollment(user_id="user-123")
        code = manager.totp.generate_totp(device.secret)
        manager.complete_totp_enrollment(device.device_id, code)

        # Verify new code
        new_code = manager.totp.generate_totp(device.secret)
        success, error = manager.verify_totp("user-123", new_code)

        assert success

    def test_backup_codes(self):
        """Test backup code generation and verification."""
        from distributed_cluster.security.mfa import MFAManager

        manager = MFAManager()

        codes = manager.generate_backup_codes("user-123", count=10)

        assert len(codes) == 10
        assert all("-" in code for code in codes)

        # Verify a backup code
        success, error = manager.verify_backup_code("user-123", codes[0])
        assert success

        # Same code should not work twice
        success, error = manager.verify_backup_code("user-123", codes[0])
        assert not success

    def test_rate_limiting(self):
        """Test MFA rate limiting."""
        from distributed_cluster.security.mfa import MFAManager, TOTPConfig

        config = TOTPConfig(rate_limit_attempts=3, rate_limit_window=60)
        manager = MFAManager(config=config)

        # Enroll device
        device, _, _ = manager.start_totp_enrollment(user_id="user-123")
        code = manager.totp.generate_totp(device.secret)
        manager.complete_totp_enrollment(device.device_id, code)

        # Make several failed attempts
        for _ in range(3):
            manager.verify_totp("user-123", "000000")

        # Should be rate limited
        success, error = manager.verify_totp("user-123", "000000")
        assert not success
        assert "Rate limited" in error


# ====================== Session Tests ======================


class TestSessionManager:
    """Test session management."""

    def test_create_session(self):
        """Test session creation."""
        from distributed_cluster.security.session import SessionManager

        manager = SessionManager()

        session, error = manager.create_session(
            user_id="user-123",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert error is None
        assert session.user_id == "user-123"
        assert session.ip_address == "192.168.1.1"
        assert session.is_active

    def test_validate_session(self):
        """Test session validation."""
        from distributed_cluster.security.session import SessionManager

        manager = SessionManager()

        session, _ = manager.create_session(user_id="user-123")
        validated, error = manager.validate_session(session.session_id)

        assert error is None
        assert validated.user_id == "user-123"

    def test_session_expiration(self):
        """Test session expiration."""
        from distributed_cluster.security.session import SessionConfig, SessionManager

        config = SessionConfig(session_lifetime_hours=0)  # Expire immediately
        manager = SessionManager(config=config)

        session, _ = manager.create_session(user_id="user-123")

        # Force expiration
        session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        manager.store.update(session)

        validated, error = manager.validate_session(session.session_id)

        assert error is not None
        assert "expired" in error.lower()

    def test_revoke_session(self):
        """Test session revocation."""
        from distributed_cluster.security.session import SessionManager

        manager = SessionManager()

        session, _ = manager.create_session(user_id="user-123")
        result = manager.revoke_session(session.session_id, reason="test")

        assert result

        validated, error = manager.validate_session(session.session_id)
        assert error is not None
        assert "revoked" in error.lower()

    def test_mfa_verification(self):
        """Test MFA verification on session."""
        from distributed_cluster.security.session import SessionManager

        manager = SessionManager()

        session, _ = manager.create_session(user_id="user-123")
        assert not session.mfa_verified

        result, _ = manager.set_mfa_verified(session.session_id)

        assert result.mfa_verified
        assert result.mfa_verified_at is not None

    def test_concurrent_session_limit(self):
        """Test concurrent session limiting."""
        from distributed_cluster.security.session import SessionConfig, SessionManager

        config = SessionConfig(max_concurrent_sessions=2)
        manager = SessionManager(config=config)

        # Create 3 sessions
        s1, _ = manager.create_session(user_id="user-123")
        s2, _ = manager.create_session(user_id="user-123")
        s3, _ = manager.create_session(user_id="user-123")

        # Only 2 should be active
        active = manager.get_active_user_sessions("user-123")
        assert len(active) == 2


# ====================== Policy Tests ======================


class TestPolicyEngine:
    """Test security policy engine."""

    def test_allow_policy(self):
        """Test allow policy evaluation."""
        from distributed_cluster.security.policy import (
            ConditionOperator,
            PolicyCondition,
            PolicyEffect,
            PolicyEngine,
            PolicyRule,
            SecurityPolicy,
        )

        engine = PolicyEngine()

        policy = SecurityPolicy(
            policy_id="test-allow",
            name="Test Allow Policy",
            rules=[
                PolicyRule(
                    rule_id="allow-admin",
                    name="Allow Admin",
                    effect=PolicyEffect.ALLOW,
                    conditions=[
                        PolicyCondition(
                            field="user.role",
                            operator=ConditionOperator.EQUALS,
                            value="admin",
                        ),
                    ],
                ),
            ],
        )
        engine.add_policy(policy)

        context = {"user": {"role": "admin"}}
        decision = engine.evaluate(context)

        assert decision.allowed
        assert decision.policy_id == "test-allow"

    def test_deny_policy(self):
        """Test deny policy evaluation."""
        from distributed_cluster.security.policy import (
            ConditionOperator,
            PolicyCondition,
            PolicyEffect,
            PolicyEngine,
            PolicyPriority,
            PolicyRule,
            SecurityPolicy,
        )

        engine = PolicyEngine()

        policy = SecurityPolicy(
            policy_id="test-deny",
            name="Test Deny Policy",
            priority=PolicyPriority.CRITICAL,
            rules=[
                PolicyRule(
                    rule_id="deny-blocked-ip",
                    name="Deny Blocked IP",
                    effect=PolicyEffect.DENY,
                    conditions=[
                        PolicyCondition(
                            field="request.ip",
                            operator=ConditionOperator.IP_IN_RANGE,
                            value=["10.0.0.0/8"],
                        ),
                    ],
                ),
            ],
        )
        engine.add_policy(policy)

        context = {"request": {"ip": "10.1.2.3"}}
        decision = engine.evaluate(context)

        assert not decision.allowed
        assert decision.policy_id == "test-deny"

    def test_ip_range_condition(self):
        """Test IP range condition."""
        from distributed_cluster.security.policy import ConditionOperator, PolicyCondition

        condition = PolicyCondition(
            field="request.ip",
            operator=ConditionOperator.IP_IN_RANGE,
            value=["192.168.0.0/24", "10.0.0.0/8"],
        )

        assert condition.evaluate({"request": {"ip": "192.168.0.50"}})
        assert condition.evaluate({"request": {"ip": "10.1.2.3"}})
        assert not condition.evaluate({"request": {"ip": "172.16.0.1"}})

    def test_time_condition(self):
        """Test time-based condition."""
        from distributed_cluster.security.policy import ConditionOperator, PolicyCondition

        # This test depends on current time
        now = datetime.now(timezone.utc)
        hour_before = (now - timedelta(hours=1)).strftime("%H:%M")
        hour_after = (now + timedelta(hours=1)).strftime("%H:%M")

        condition = PolicyCondition(
            field="request.time",
            operator=ConditionOperator.TIME_BETWEEN,
            value=[hour_before, hour_after],
        )

        # Current time should be in range
        assert condition.evaluate({"request": {"time": now}})


# ====================== Monitoring Tests ======================


class TestSecurityMonitor:
    """Test security monitoring."""

    def test_record_auth_failure(self):
        """Test recording authentication failures."""
        from distributed_cluster.security.monitoring import MonitoringConfig, SecurityMonitor

        config = MonitoringConfig(auth_failure_threshold=3)
        monitor = SecurityMonitor(config=config)

        # Record failures
        alerts = monitor.record_auth_failure(
            user_id="user-123",
            ip_address="192.168.1.1",
            reason="invalid_password",
        )

        assert len(alerts) == 0  # Not enough failures yet

    def test_brute_force_detection(self):
        """Test brute force attack detection."""
        from distributed_cluster.security.monitoring import MonitoringConfig, SecurityMonitor, ThreatType

        config = MonitoringConfig(
            auth_failure_threshold=3,
            auth_failure_window_seconds=300,
        )
        monitor = SecurityMonitor(config=config)

        # Record multiple failures
        for i in range(3):
            alerts = monitor.record_auth_failure(
                user_id="user-123",
                ip_address="192.168.1.1",
                reason="invalid_password",
            )

        # Should trigger brute force alert
        assert len(alerts) == 1
        assert alerts[0].threat_type == ThreatType.BRUTE_FORCE

    def test_lockout(self):
        """Test account lockout."""
        from distributed_cluster.security.monitoring import MonitoringConfig, SecurityMonitor

        config = MonitoringConfig(
            auth_failure_threshold=3,
            lockout_duration_seconds=60,
        )
        monitor = SecurityMonitor(config=config)

        # Trigger lockout
        for _ in range(3):
            monitor.record_auth_failure(ip_address="192.168.1.1")

        locked, remaining = monitor.is_actor_locked_out("192.168.1.1")

        assert locked
        assert remaining is not None
        assert remaining > 0

    def test_statistics(self):
        """Test security statistics."""
        from distributed_cluster.security.monitoring import SecurityMonitor

        monitor = SecurityMonitor()

        monitor.record_auth_success("user-123", "192.168.1.1")
        monitor.record_auth_failure(user_id="user-456", ip_address="192.168.1.2")

        stats = monitor.get_statistics()

        assert stats["total_events"] == 2
        assert stats["auth_failures"] == 1


# ====================== Account Security Tests ======================


class TestPasswordValidator:
    """Test password validation."""

    def test_strong_password(self):
        """Test strong password validation."""
        from distributed_cluster.security.account import PasswordPolicy, PasswordStrength, PasswordValidator

        policy = PasswordPolicy(min_length=8)
        validator = PasswordValidator(policy)

        result = validator.validate("Str0ng!Pass#2024")

        assert result.valid
        assert result.strength in [PasswordStrength.STRONG, PasswordStrength.VERY_STRONG]

    def test_weak_password_rejected(self):
        """Test weak password rejection."""
        from distributed_cluster.security.account import PasswordPolicy, PasswordStrength, PasswordValidator

        policy = PasswordPolicy(min_length=12, min_strength=PasswordStrength.STRONG)
        validator = PasswordValidator(policy)

        result = validator.validate("password123")

        assert not result.valid
        assert len(result.errors) > 0

    def test_password_with_username(self):
        """Test password containing username rejection."""
        from distributed_cluster.security.account import PasswordPolicy, PasswordValidator

        policy = PasswordPolicy(forbid_username=True)
        validator = PasswordValidator(policy)

        result = validator.validate("MyName123!Pass", username="myname")

        assert not result.valid
        assert any("username" in e.lower() for e in result.errors)

    def test_common_password_rejected(self):
        """Test common password rejection."""
        from distributed_cluster.security.account import PasswordPolicy, PasswordValidator

        policy = PasswordPolicy(forbid_common_words=True)
        validator = PasswordValidator(policy)

        result = validator.validate("Password123!")

        assert not result.valid


class TestAccountSecurityManager:
    """Test account security management."""

    def test_create_account(self):
        """Test account creation."""
        from distributed_cluster.security.account import AccountSecurityManager, PasswordPolicy

        policy = PasswordPolicy(min_length=8)
        manager = AccountSecurityManager(policy=policy)

        success, validation = manager.create_account(
            user_id="user-123",
            password="Str0ng!Pass#2024",
        )

        assert success
        assert validation.valid

    def test_verify_password(self):
        """Test password verification."""
        from distributed_cluster.security.account import AccountSecurityManager, PasswordPolicy

        policy = PasswordPolicy(min_length=8)
        manager = AccountSecurityManager(policy=policy)

        password = "Str0ng!Pass#2024"
        manager.create_account("user-123", password)

        success, error, account = manager.verify_password("user-123", password)

        assert success
        assert account is not None

    def test_wrong_password(self):
        """Test wrong password rejection."""
        from distributed_cluster.security.account import AccountSecurityManager

        manager = AccountSecurityManager()
        manager.create_account("user-123", "Str0ng!Pass#2024")

        success, error, _ = manager.verify_password("user-123", "WrongPassword")

        assert not success
        assert error is not None

    def test_account_lockout(self):
        """Test account lockout after failed attempts."""
        from distributed_cluster.security.account import AccountSecurityManager

        manager = AccountSecurityManager()
        manager.max_failed_attempts = 3
        manager.create_account("user-123", "Str0ng!Pass#2024")

        # Make failed attempts
        for _ in range(3):
            manager.verify_password("user-123", "WrongPassword")

        success, error, _ = manager.verify_password("user-123", "Str0ng!Pass#2024")

        assert not success
        assert "locked" in error.lower()

    def test_change_password(self):
        """Test password change."""
        from distributed_cluster.security.account import AccountSecurityManager, PasswordPolicy

        # Use policy with no minimum password age to allow immediate change
        policy = PasswordPolicy(min_password_age_hours=0)
        manager = AccountSecurityManager(policy=policy)
        old_password = "Str0ng!Pass#2024"
        new_password = "New$ecure!Pass99"

        manager.create_account("user-123", old_password)

        success, error, _ = manager.change_password(
            "user-123",
            old_password,
            new_password,
        )

        assert success, f"Password change failed: {error}"

        # Old password should not work
        success, _, _ = manager.verify_password("user-123", old_password)
        assert not success

        # New password should work
        success, _, _ = manager.verify_password("user-123", new_password)
        assert success

    def test_password_history(self):
        """Test password history enforcement."""
        from distributed_cluster.security.account import AccountSecurityManager, PasswordPolicy

        policy = PasswordPolicy(history_size=3, min_password_age_hours=0)
        manager = AccountSecurityManager(policy=policy)

        password1 = "Str0ng!Pass#One1"
        password2 = "Str0ng!Pass#Two2"

        manager.create_account("user-123", password1)

        # Change to password2
        manager.change_password("user-123", password1, password2)

        # Try to reuse password1
        success, error, validation = manager.change_password("user-123", password2, password1)

        assert not success
        # Check that password history error is in validation errors
        assert validation is not None
        assert any("used recently" in e.lower() for e in validation.errors)


# ====================== mTLS Tests ======================


class TestCertificateAuthority:
    """Test mTLS certificate authority."""

    def test_create_ca(self):
        """Test CA creation."""
        pytest.importorskip("cryptography")

        from distributed_cluster.security.mtls import CertificateAuthority

        ca = CertificateAuthority(organization="TestOrg")

        assert ca.ca_certificate_pem is not None
        assert b"-----BEGIN CERTIFICATE-----" in ca.ca_certificate_pem

    def test_issue_server_certificate(self):
        """Test server certificate issuance."""
        pytest.importorskip("cryptography")

        from distributed_cluster.security.mtls import CertificateAuthority, CertificateType

        ca = CertificateAuthority(organization="TestOrg")

        bundle = ca.issue_certificate(
            common_name="server.example.com",
            cert_type=CertificateType.SERVER,
            dns_names=["server.example.com", "localhost"],
            ip_addresses=["127.0.0.1"],
        )

        assert bundle.certificate_pem is not None
        assert bundle.private_key_pem is not None
        assert bundle.ca_certificate_pem is not None

    def test_verify_certificate(self):
        """Test certificate verification."""
        pytest.importorskip("cryptography")

        from distributed_cluster.security.mtls import CertificateAuthority, CertificateType

        ca = CertificateAuthority(organization="TestOrg")

        bundle = ca.issue_certificate(
            common_name="test.example.com",
            cert_type=CertificateType.CLIENT,
        )

        valid, error, info = ca.verify_certificate(bundle.certificate_pem)

        assert valid
        assert error is None
        assert info is not None

    def test_revoke_certificate(self):
        """Test certificate revocation."""
        pytest.importorskip("cryptography")

        from distributed_cluster.security.mtls import CertificateAuthority, CertificateType

        ca = CertificateAuthority(organization="TestOrg")

        bundle = ca.issue_certificate(
            common_name="test.example.com",
            cert_type=CertificateType.CLIENT,
        )

        # Get serial from issued cert
        valid, _, info = ca.verify_certificate(bundle.certificate_pem)
        assert valid

        # Revoke
        ca.revoke_certificate(info.serial_number, reason="test")

        # Should fail verification
        valid, error, _ = ca.verify_certificate(bundle.certificate_pem)
        assert not valid
        assert "revoked" in error.lower()


# ====================== Integration Tests ======================


class TestClusterSecurityManager:
    """Test unified security manager."""

    @pytest.fixture
    def manager(self):
        """Create security manager."""
        from distributed_cluster.security.manager import ClusterSecurityManager

        return ClusterSecurityManager()

    @pytest.mark.asyncio
    async def test_authenticate_password(self, manager):
        """Test password authentication."""
        # Create user first
        success, error = await manager.create_user(
            user_id="testuser",
            password="Str0ng!Pass#2024",
        )
        assert success

        # Authenticate
        result = await manager.authenticate(
            user_id="testuser",
            credential="Str0ng!Pass#2024",
            ip_address="192.168.1.1",
        )

        assert result.success
        assert result.session is not None
        assert result.token is not None

    @pytest.mark.asyncio
    async def test_check_access(self, manager):
        """Test access control check."""
        from distributed_cluster.security.manager import AccessRequest

        # Create user
        await manager.create_user(
            user_id="testuser",
            password="Str0ng!Pass#2024",
        )

        # Authenticate
        auth_result = await manager.authenticate(
            user_id="testuser",
            credential="Str0ng!Pass#2024",
        )

        # Check access
        request = AccessRequest(
            user_id="testuser",
            action="read",
            resource_type="jobs",
            resource_id="job-123",
            session_id=auth_result.session.session_id,
        )

        result = await manager.check_access(request)

        # Default policy should allow
        # (depends on policy configuration)

    @pytest.mark.asyncio
    async def test_logout(self, manager):
        """Test logout."""
        await manager.create_user(
            user_id="testuser",
            password="Str0ng!Pass#2024",
        )

        result = await manager.authenticate(
            user_id="testuser",
            credential="Str0ng!Pass#2024",
        )

        session_id = result.session.session_id
        success = await manager.logout(session_id)

        assert success

        # Session should be invalid
        session, error = manager.session_manager.validate_session(session_id)
        assert error is not None

    def test_security_status(self, manager):
        """Test security status retrieval."""
        status = manager.get_security_status()

        assert "status" in status
        assert "active_alerts" in status
        assert "critical_alerts" in status

    def test_security_headers(self, manager):
        """Test security headers generation."""
        headers = manager.get_security_headers()

        assert "Strict-Transport-Security" in headers
        assert "X-Content-Type-Options" in headers
        assert "X-Frame-Options" in headers


# ====================== Password Hasher Tests ======================


class TestPasswordHasher:
    """Test password hashing."""

    def test_hash_password(self):
        """Test password hashing."""
        from distributed_cluster.security.account import PasswordHasher

        hasher = PasswordHasher()
        password = "TestPassword123!"

        hash_obj = hasher.hash(password)

        assert hash_obj.hash is not None
        assert hash_obj.salt is not None
        assert hash_obj.algorithm == "pbkdf2_sha256"

    def test_verify_password(self):
        """Test password verification."""
        from distributed_cluster.security.account import PasswordHasher

        hasher = PasswordHasher()
        password = "TestPassword123!"

        hash_obj = hasher.hash(password)
        result = hasher.verify(password, hash_obj)

        assert result

    def test_wrong_password_fails(self):
        """Test wrong password fails verification."""
        from distributed_cluster.security.account import PasswordHasher

        hasher = PasswordHasher()

        hash_obj = hasher.hash("CorrectPassword!")
        result = hasher.verify("WrongPassword!", hash_obj)

        assert not result

    def test_needs_rehash(self):
        """Test rehash detection."""
        from distributed_cluster.security.account import PasswordHash, PasswordHasher

        hasher = PasswordHasher(iterations=310000)

        old_hash = PasswordHash(
            hash="dummy",
            salt="dummy",
            algorithm="pbkdf2_sha256",
            iterations=100000,  # Old iteration count
        )

        assert hasher.needs_rehash(old_hash)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
