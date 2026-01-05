"""
Unified Security Manager - مدير الأمان الموحد
==============================================

Central security orchestration for the distributed cluster.
تنسيق أمان مركزي للمجموعة الموزعة.

Features:
- Unified authentication flow
- Security component integration
- Access control enforcement
- Security event coordination
- Compliance enforcement
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .account import AccountSecurityManager, PasswordPolicy
from .audit import AuditAction, AuditLogger, AuditResult
from .auth import AuthConfig, AuthManager, Role, TokenPayload
from .mfa import MFAManager, TOTPConfig
from .monitoring import MonitoringConfig, SecurityAlert, SecurityMonitor, ThreatLevel
from .policy import PolicyDecision, PolicyEngine, SecurityPolicy
from .rbac import RBACManager
from .session import DeviceFingerprint, Session, SessionConfig, SessionManager

logger = logging.getLogger(__name__)


class AuthenticationMethod(str, Enum):
    """Authentication methods."""

    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    CERTIFICATE = "certificate"
    OAUTH = "oauth"
    SSO = "sso"


@dataclass
class SecurityConfig:
    """Unified security configuration."""

    # Authentication
    auth_config: AuthConfig = field(default_factory=AuthConfig)
    password_policy: PasswordPolicy = field(default_factory=PasswordPolicy)
    totp_config: TOTPConfig = field(default_factory=TOTPConfig)

    # Session
    session_config: SessionConfig = field(default_factory=SessionConfig)

    # Monitoring
    monitoring_config: MonitoringConfig = field(default_factory=MonitoringConfig)

    # Global settings
    enforce_mfa_for_roles: List[str] = field(default_factory=lambda: ["admin", "operator"])
    require_mfa_for_sensitive_ops: bool = True
    default_session_lifetime_hours: int = 24
    api_key_default_expiry_days: int = 365

    # Security headers
    enable_security_headers: bool = True
    hsts_max_age_seconds: int = 31536000  # 1 year

    # Compliance
    audit_all_access: bool = True
    log_sensitive_operations: bool = True


@dataclass
class AuthenticationResult:
    """Result of authentication attempt."""

    success: bool
    user_id: Optional[str] = None
    role: Optional[Role] = None
    session: Optional[Session] = None
    token: Optional[str] = None

    # MFA status
    mfa_required: bool = False
    mfa_challenge_id: Optional[str] = None

    # Errors
    error: Optional[str] = None
    error_code: Optional[str] = None

    # Recommendations
    password_expiring: bool = False
    days_until_expiry: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "user_id": self.user_id,
            "role": self.role.value if self.role else None,
            "mfa_required": self.mfa_required,
            "mfa_challenge_id": self.mfa_challenge_id,
            "error": self.error,
            "password_expiring": self.password_expiring,
            "days_until_expiry": self.days_until_expiry,
        }


@dataclass
class AccessRequest:
    """Access control request."""

    user_id: str
    action: str
    resource_type: str
    resource_id: str
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AccessResult:
    """Result of access control check."""

    allowed: bool
    reason: Optional[str] = None
    policy_id: Optional[str] = None
    audit_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "policy_id": self.policy_id,
        }


class ClusterSecurityManager:
    """
    Unified Security Manager for the Distributed Cluster.

    Orchestrates all security components and provides a unified interface.
    """

    def __init__(
        self,
        config: Optional[SecurityConfig] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self.config = config or SecurityConfig()
        self.audit = audit_logger or AuditLogger()

        # Initialize components
        self._init_components()

        self._lock = threading.RLock()
        self._initialized = True

        logger.info("ClusterSecurityManager initialized")

    def _init_components(self) -> None:
        """Initialize security components."""
        # Authentication
        self.auth_manager = AuthManager(config=self.config.auth_config)

        # RBAC
        self.rbac_manager = RBACManager()

        # MFA
        self.mfa_manager = MFAManager(config=self.config.totp_config)

        # Sessions
        self.session_manager = SessionManager(
            config=self.config.session_config,
            event_handler=self._handle_session_event,
        )

        # Policy engine
        self.policy_engine = PolicyEngine(
            audit_callback=self._handle_policy_audit,
        )

        # Security monitoring
        self.security_monitor = SecurityMonitor(
            config=self.config.monitoring_config,
            alert_handler=self._handle_security_alert,
        )

        # Account security
        self.account_manager = AccountSecurityManager(
            policy=self.config.password_policy,
        )

    def _handle_session_event(self, event, session, data) -> None:
        """Handle session events."""
        from .session import SessionEvent

        if self.config.audit_all_access:
            asyncio.create_task(
                self.audit.log(
                    action=AuditAction.AUTH_LOGIN if event == SessionEvent.CREATED else AuditAction.AUTH_LOGOUT,
                    result=AuditResult.SUCCESS,
                    actor_id=session.user_id,
                    resource_type="session",
                    resource_id=session.session_id,
                )
            )

    def _handle_policy_audit(self, decision: PolicyDecision, context: Dict) -> None:
        """Handle policy evaluation audit."""
        if self.config.log_sensitive_operations:
            logger.debug(f"Policy decision: {decision.to_dict()}")

    def _handle_security_alert(self, alert: SecurityAlert) -> None:
        """Handle security alerts."""
        # Log critical alerts
        if alert.threat_level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]:
            logger.warning(f"Security Alert [{alert.threat_level.value}]: {alert.title}")

        # Auto-actions for critical threats
        if alert.threat_level == ThreatLevel.CRITICAL:
            for actor in alert.affected_actors:
                # Auto-lockout on critical threats
                pass

    # ====================== Authentication ======================

    async def authenticate(
        self,
        user_id: str,
        credential: str,
        method: AuthenticationMethod = AuthenticationMethod.PASSWORD,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        device_fingerprint: Optional[DeviceFingerprint] = None,
    ) -> AuthenticationResult:
        """
        Authenticate a user.

        Handles password verification, MFA, and session creation.
        """
        # Check if locked out
        is_locked, remaining = self.security_monitor.is_actor_locked_out(ip_address or user_id)
        if is_locked:
            await self.audit.log(
                action=AuditAction.AUTH_LOGIN_FAILED,
                result=AuditResult.DENIED,
                actor_id=user_id,
                actor_ip=ip_address,
                error_message=f"Account locked, {remaining}s remaining",
            )
            return AuthenticationResult(
                success=False,
                error=f"Account locked. Try again in {remaining} seconds",
                error_code="account_locked",
            )

        # Authenticate based on method
        if method == AuthenticationMethod.PASSWORD:
            success, error, account = self.account_manager.verify_password(
                user_id,
                credential,
                ip_address=ip_address,
            )

            if not success:
                # Record failure for monitoring
                self.security_monitor.record_auth_failure(
                    user_id=user_id,
                    ip_address=ip_address,
                    reason=error or "invalid_credentials",
                )

                await self.audit.log(
                    action=AuditAction.AUTH_LOGIN_FAILED,
                    result=AuditResult.FAILURE,
                    actor_id=user_id,
                    actor_ip=ip_address,
                    error_message=error,
                )

                return AuthenticationResult(
                    success=False,
                    error=error,
                    error_code="auth_failed",
                )

            # Check password expiration warning
            password_expiring, days_left = self.account_manager.check_password_expiry(user_id)

        elif method == AuthenticationMethod.API_KEY:
            payload = self.auth_manager.verify_token(credential)
            if not payload or payload.subject_type != "api_key":
                return AuthenticationResult(
                    success=False,
                    error="Invalid API key",
                    error_code="invalid_api_key",
                )
            user_id = payload.subject
            password_expiring = False
            days_left = None

        elif method == AuthenticationMethod.TOKEN:
            payload = self.auth_manager.verify_token(credential)
            if not payload:
                return AuthenticationResult(
                    success=False,
                    error="Invalid token",
                    error_code="invalid_token",
                )
            user_id = payload.subject
            password_expiring = False
            days_left = None

        else:
            return AuthenticationResult(
                success=False,
                error=f"Unsupported authentication method: {method}",
                error_code="unsupported_method",
            )

        # Get user role from RBAC
        rbac_user = self.rbac_manager.get_user(user_id)
        user_role = Role.USER
        if rbac_user and rbac_user.roles:
            # Get highest role
            role_priority = {Role.ADMIN: 0, Role.OPERATOR: 1, Role.USER: 2, Role.READONLY: 3}
            for role_name in rbac_user.roles:
                try:
                    role = Role(role_name)
                    if role_priority.get(role, 99) < role_priority.get(user_role, 99):
                        user_role = role
                except ValueError:
                    pass

        # Check if MFA is required
        mfa_required = False
        mfa_challenge_id = None

        if user_role.value in self.config.enforce_mfa_for_roles:
            if self.mfa_manager.is_mfa_enabled(user_id):
                mfa_required = True
                challenge = self.mfa_manager.create_challenge(user_id)
                mfa_challenge_id = challenge.challenge_id

        # Create session
        session, session_error = self.session_manager.create_session(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint,
        )

        if session_error:
            return AuthenticationResult(
                success=False,
                error=session_error,
                error_code="session_error",
            )

        # Generate token
        token_payload = TokenPayload(
            subject=user_id,
            subject_type="user",
            role=user_role,
            session_id=session.session_id,
        )
        token = self.auth_manager.generate_token(token_payload)

        # Record success
        self.security_monitor.record_auth_success(user_id, ip_address)

        await self.audit.log(
            action=AuditAction.AUTH_LOGIN,
            result=AuditResult.SUCCESS,
            actor_id=user_id,
            actor_ip=ip_address,
            resource_type="session",
            resource_id=session.session_id,
            details={"method": method.value, "mfa_required": mfa_required},
        )

        return AuthenticationResult(
            success=True,
            user_id=user_id,
            role=user_role,
            session=session,
            token=token,
            mfa_required=mfa_required,
            mfa_challenge_id=mfa_challenge_id,
            password_expiring=password_expiring,
            days_until_expiry=days_left,
        )

    async def verify_mfa(
        self,
        session_id: str,
        mfa_code: str,
        challenge_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify MFA code.

        Returns:
            (success, error_message)
        """
        # Get session
        session, error = self.session_manager.validate_session(session_id)
        if error:
            return False, error

        # Verify MFA
        if challenge_id:
            success, error = self.mfa_manager.verify_challenge(challenge_id, mfa_code)
        else:
            success, error = self.mfa_manager.verify(session.user_id, mfa_code)

        if not success:
            await self.audit.log(
                action=AuditAction.AUTH_LOGIN_FAILED,
                result=AuditResult.FAILURE,
                actor_id=session.user_id,
                resource_type="mfa",
                error_message=error,
            )
            return False, error

        # Mark session as MFA verified
        self.session_manager.set_mfa_verified(session_id)

        await self.audit.log(
            action=AuditAction.AUTH_LOGIN,
            result=AuditResult.SUCCESS,
            actor_id=session.user_id,
            resource_type="mfa",
            details={"type": "totp"},
        )

        return True, None

    async def logout(
        self,
        session_id: str,
        revoke_all: bool = False,
    ) -> bool:
        """Logout user and invalidate session."""
        session = self.session_manager.get_session(session_id)
        if not session:
            return False

        if revoke_all:
            self.session_manager.revoke_all_user_sessions(session.user_id)
        else:
            self.session_manager.revoke_session(session_id)

        await self.audit.log(
            action=AuditAction.AUTH_LOGOUT,
            result=AuditResult.SUCCESS,
            actor_id=session.user_id,
            resource_type="session",
            resource_id=session_id,
            details={"revoke_all": revoke_all},
        )

        return True

    # ====================== Access Control ======================

    async def check_access(
        self,
        request: AccessRequest,
    ) -> AccessResult:
        """
        Check if access is allowed.

        Combines session validation, permission checking, and policy evaluation.
        """
        # Validate session if provided
        if request.session_id:
            session, error = self.session_manager.validate_session(
                request.session_id,
                ip_address=request.ip_address,
            )
            if error:
                return AccessResult(
                    allowed=False,
                    reason=error,
                )

            # Check MFA for sensitive operations
            if self.config.require_mfa_for_sensitive_ops:
                if request.action in ["delete", "admin", "configure"]:
                    if not session.mfa_verified:
                        return AccessResult(
                            allowed=False,
                            reason="MFA verification required for this operation",
                        )

        # Check RBAC permissions
        rbac_user = self.rbac_manager.get_user(request.user_id)
        if rbac_user:
            has_permission = self.rbac_manager.check_permission(
                rbac_user,
                f"{request.resource_type}/{request.resource_id}",
                request.action,
                context={
                    "ip": request.ip_address,
                    "user_id": request.user_id,
                },
            )

            if not has_permission:
                await self._audit_access_denied(request, "RBAC permission denied")
                return AccessResult(
                    allowed=False,
                    reason="Permission denied",
                )

        # Evaluate policies
        context = {
            "user": {"id": request.user_id, "role": rbac_user.roles if rbac_user else []},
            "request": {
                "action": request.action,
                "ip": request.ip_address,
                "time": datetime.now(timezone.utc),
            },
            "session": {"mfa_verified": session.mfa_verified if request.session_id else False},
            "resource": {"type": request.resource_type, "id": request.resource_id},
        }

        policy_decision = self.policy_engine.evaluate(
            context,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
        )

        if not policy_decision.allowed:
            await self._audit_access_denied(request, policy_decision.reason)
            return AccessResult(
                allowed=False,
                reason=policy_decision.reason,
                policy_id=policy_decision.policy_id,
            )

        # Access granted
        if self.config.audit_all_access:
            await self.audit.log(
                action=AuditAction.AUTH_LOGIN,  # Generic access log
                result=AuditResult.SUCCESS,
                actor_id=request.user_id,
                actor_ip=request.ip_address,
                resource_type=request.resource_type,
                resource_id=request.resource_id,
                details={"action": request.action},
            )

        return AccessResult(
            allowed=True,
            policy_id=policy_decision.policy_id,
        )

    async def _audit_access_denied(self, request: AccessRequest, reason: str) -> None:
        """Audit access denial."""
        await self.audit.log(
            action=AuditAction.AUTH_PERMISSION_DENIED,
            result=AuditResult.DENIED,
            actor_id=request.user_id,
            actor_ip=request.ip_address,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            error_message=reason,
            details={"action": request.action},
        )

        self.security_monitor.record_access_denied(
            request.user_id,
            request.resource_type,
            request.resource_id,
            reason,
            request.ip_address,
        )

    # ====================== User Management ======================

    async def create_user(
        self,
        user_id: str,
        password: str,
        role: Role = Role.USER,
        email: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Create a new user account."""
        # Create account with password
        success, validation = self.account_manager.create_account(
            user_id=user_id,
            password=password,
            username=user_id,
            email=email,
        )

        if not success:
            return False, "; ".join(validation.errors)

        # Add to RBAC
        from .rbac import User as RBACUser

        rbac_user = RBACUser(
            id=user_id,
            username=user_id,
            roles={role.value},
        )
        self.rbac_manager.add_user(rbac_user)

        await self.audit.log(
            action=AuditAction.ADMIN_USER_CREATED,
            result=AuditResult.SUCCESS,
            resource_type="user",
            resource_id=user_id,
            details={"role": role.value},
        )

        return True, None

    async def change_user_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> Tuple[bool, Optional[str]]:
        """Change user password."""
        success, error, validation = self.account_manager.change_password(
            user_id=user_id,
            current_password=current_password,
            new_password=new_password,
        )

        if not success:
            return False, error

        await self.audit.log(
            action=AuditAction.CONFIG_CHANGED,
            result=AuditResult.SUCCESS,
            actor_id=user_id,
            resource_type="password",
            resource_id=user_id,
        )

        return True, None

    # ====================== MFA Management ======================

    async def setup_mfa(
        self,
        user_id: str,
        device_name: str = "Authenticator",
    ) -> Tuple[str, Optional[bytes]]:
        """
        Start MFA setup.

        Returns:
            (provisioning_uri, qr_code_png)
        """
        device, uri, qr_code = self.mfa_manager.start_totp_enrollment(
            user_id=user_id,
            device_name=device_name,
            account_name=user_id,
        )

        return uri, qr_code

    async def verify_mfa_setup(
        self,
        device_id: str,
        verification_code: str,
    ) -> Tuple[bool, Optional[str], Optional[List[str]]]:
        """
        Complete MFA setup and generate backup codes.

        Returns:
            (success, error, backup_codes)
        """
        success, error = self.mfa_manager.complete_totp_enrollment(
            device_id=device_id,
            verification_code=verification_code,
        )

        if not success:
            return False, error, None

        # Get device to find user
        device = self.mfa_manager.store.get_device(device_id)
        if not device:
            return False, "Device not found", None

        # Generate backup codes
        backup_codes = self.mfa_manager.generate_backup_codes(device.user_id)

        await self.audit.log(
            action=AuditAction.CONFIG_CHANGED,
            result=AuditResult.SUCCESS,
            actor_id=device.user_id,
            resource_type="mfa",
            resource_id=device_id,
            details={"action": "setup_complete"},
        )

        return True, None, backup_codes

    # ====================== API Key Management ======================

    async def create_api_key(
        self,
        name: str,
        user_id: str,
        role: Role = Role.USER,
        expires_in_days: Optional[int] = None,
    ) -> Tuple[str, str]:
        """
        Create an API key.

        Returns:
            (api_key_id, api_key)
        """
        expires = expires_in_days or self.config.api_key_default_expiry_days

        api_key_full, token = self.auth_manager.create_api_key(
            name=name,
            role=role,
            expires_in_days=expires,
        )

        await self.audit.log(
            action=AuditAction.AUTH_TOKEN_CREATED,
            result=AuditResult.SUCCESS,
            actor_id=user_id,
            resource_type="api_key",
            resource_id=api_key_full.split(".")[0],
            details={"name": name, "role": role.value},
        )

        return api_key_full, token

    async def revoke_api_key(
        self,
        api_key_id: str,
        revoked_by: str,
    ) -> bool:
        """Revoke an API key."""
        result = self.auth_manager.revoke_api_key(api_key_id)

        if result:
            await self.audit.log(
                action=AuditAction.AUTH_TOKEN_REVOKED,
                result=AuditResult.SUCCESS,
                actor_id=revoked_by,
                resource_type="api_key",
                resource_id=api_key_id,
            )

        return result

    # ====================== Security Policies ======================

    async def add_security_policy(
        self,
        policy: SecurityPolicy,
        added_by: str,
    ) -> bool:
        """Add a security policy."""
        result = self.policy_engine.add_policy(policy)

        if result:
            await self.audit.log(
                action=AuditAction.CONFIG_POLICY_CHANGED,
                result=AuditResult.SUCCESS,
                actor_id=added_by,
                resource_type="policy",
                resource_id=policy.policy_id,
                details={"name": policy.name, "action": "add"},
            )

        return result

    async def remove_security_policy(
        self,
        policy_id: str,
        removed_by: str,
    ) -> bool:
        """Remove a security policy."""
        result = self.policy_engine.delete_policy(policy_id)

        if result:
            await self.audit.log(
                action=AuditAction.CONFIG_POLICY_CHANGED,
                result=AuditResult.SUCCESS,
                actor_id=removed_by,
                resource_type="policy",
                resource_id=policy_id,
                details={"action": "remove"},
            )

        return result

    # ====================== Security Status ======================

    def get_security_status(self) -> Dict[str, Any]:
        """Get overall security status."""
        stats = self.security_monitor.get_statistics()
        active_alerts = self.security_monitor.get_active_alerts()

        return {
            "status": "healthy" if stats["critical_alerts"] == 0 else "at_risk",
            "active_alerts": len(active_alerts),
            "critical_alerts": stats["critical_alerts"],
            "recent_auth_failures": stats.get("auth_failures", 0),
            "recent_access_denials": stats.get("access_denials", 0),
            "total_events": stats["total_events"],
        }

    def get_active_alerts(
        self,
        threat_level: Optional[ThreatLevel] = None,
    ) -> List[SecurityAlert]:
        """Get active security alerts."""
        return self.security_monitor.get_active_alerts(threat_level)

    def get_security_headers(self) -> Dict[str, str]:
        """Get security headers for HTTP responses."""
        if not self.config.enable_security_headers:
            return {}

        return {
            "Strict-Transport-Security": f"max-age={self.config.hsts_max_age_seconds}; includeSubDomains",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Content-Security-Policy": "default-src 'self'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }


def create_cluster_security_manager(
    config: Optional[SecurityConfig] = None,
    audit_logger: Optional[AuditLogger] = None,
) -> ClusterSecurityManager:
    """Create a ClusterSecurityManager instance."""
    return ClusterSecurityManager(config=config, audit_logger=audit_logger)
