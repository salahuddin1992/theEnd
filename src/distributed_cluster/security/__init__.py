"""
Security Module - وحدة الأمان
==============================

Comprehensive security and authentication system for the distributed cluster.
نظام أمان ومصادقة شامل للمجموعة الموزعة.

Components:
- Authentication & Authorization (auth.py)
- Role-Based Access Control (rbac.py)
- Multi-Factor Authentication (mfa.py)
- Session Management (session.py)
- Security Policies (policy.py)
- Security Monitoring (monitoring.py)
- Account Security (account.py)
- mTLS Certificates (mtls.py)
- Secrets Management (secrets.py)
- Audit Logging (audit.py)
- Rate Limiting (ratelimit.py)
- OAuth/OIDC (oauth.py)
- Cryptographic Utilities (crypto.py)
"""

# ====================== Core Authentication ======================
# ====================== Account Security ======================
from distributed_cluster.security.account import (
    AccountSecurityInfo,
    AccountSecurityManager,
    AccountStatus,
    PasswordHash,
    PasswordHasher,
    PasswordPolicy,
    PasswordStrength,
    PasswordValidationResult,
    PasswordValidator,
    create_account_security_manager,
)

# ====================== Audit Logging ======================
from distributed_cluster.security.audit import (
    AuditAction,
    AuditBackend,
    AuditEvent,
    AuditLogger,
    AuditResult,
    FileAuditBackend,
    MemoryAuditBackend,
)
from distributed_cluster.security.audit_backends import (
    CompositeAuditBackend,
    PostgreSQLAuditBackend,
    SQLiteAuditBackend,
    create_audit_backend,
)
from distributed_cluster.security.auth import (
    AuthConfig,
    AuthManager,
    EnrollmentMode,
    Permission,
    Role,
    TokenPayload,
    WorkerEnrollment,
)

# ====================== Cryptography ======================
from distributed_cluster.security.crypto import CryptoManager

# ====================== Unified Security Manager ======================
from distributed_cluster.security.manager import (
    AccessRequest,
    AccessResult,
    AuthenticationMethod,
    AuthenticationResult,
    ClusterSecurityManager,
    SecurityConfig,
    create_cluster_security_manager,
)

# ====================== Multi-Factor Authentication ======================
from distributed_cluster.security.mfa import (
    MFADevice,
    MFAManager,
    MFAMiddleware,
    MFAStatus,
    MFAType,
    TOTPConfig,
    TOTPGenerator,
    create_mfa_manager,
)

# ====================== Security Monitoring ======================
from distributed_cluster.security.monitoring import (
    AnomalyDetector,
    BruteForceDetector,
    MonitoringConfig,
    SecurityAlert,
    SecurityEventType,
    SecurityMonitor,
    ThreatDetector,
    ThreatLevel,
    ThreatType,
    create_security_monitor,
)
from distributed_cluster.security.monitoring import (
    SecurityEvent as MonitoringSecurityEvent,
)

# ====================== mTLS Certificates ======================
from distributed_cluster.security.mtls import (
    CertificateAuthority,
    CertificateBundle,
    CertificateInfo,
    CertificateStatus,
    CertificateStore,
    CertificateType,
    FileCertificateStore,
    KeyAlgorithm,
    MemoryCertificateStore,
    MTLSAuthenticator,
    create_cluster_ca,
)

# ====================== OAuth/OIDC ======================
from distributed_cluster.security.oauth import (
    GrantType,
    JWTHandler,
    OAuth2Client,
    OAuth2Config,
    OAuth2Error,
    OIDCProvider,
    TokenInfo,
    TokenManager,
    TokenType,
)

# ====================== Security Policies ======================
from distributed_cluster.security.policy import (
    AccessControlPolicies,
    ConditionOperator,
    NetworkSecurityPolicies,
    PolicyCondition,
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyPriority,
    PolicyRule,
    RiskBasedPolicies,
    SecurityPolicy,
    TimeBasedPolicies,
    create_policy_engine,
)

# ====================== Rate Limiting ======================
from distributed_cluster.security.ratelimit import (
    AdaptiveRateLimiter,
    DistributedRateLimiter,
    FixedWindow,
    RateLimitConfig,
    RateLimiter,
    RateLimitExceeded,
    RateLimitInfo,
    SlidingWindow,
    TokenBucket,
    rate_limit,
)

# ====================== RBAC ======================
from distributed_cluster.security.rbac import (
    AccessDecision,
    Effect,
    RBACManager,
    Resource,
    require_permission,
)
from distributed_cluster.security.rbac import (
    Permission as RBACPermission,
)
from distributed_cluster.security.rbac import (
    Policy as RBACPolicy,
)
from distributed_cluster.security.rbac import (
    PolicyEngine as RBACPolicyEngine,
)
from distributed_cluster.security.rbac import (
    Role as RBACRole,
)
from distributed_cluster.security.rbac import (
    User as RBACUser,
)

# ====================== Secrets Management ======================
from distributed_cluster.security.secrets import (
    Encryptor,
    FileSecretStore,
    MemorySecretStore,
    Secret,
    SecretMetadata,
    SecretsManager,
    SecretStore,
    SecretType,
)

# ====================== Session Management ======================
from distributed_cluster.security.session import (
    DeviceFingerprint,
    GeoLocation,
    Session,
    SessionConfig,
    SessionEvent,
    SessionManager,
    SessionStatus,
    SessionTokenManager,
    create_session_manager,
)

# ====================== Vault Backends ======================
from distributed_cluster.security.vault_backends import (
    AWSSecretsManagerStore,
    AzureKeyVaultStore,
    HashiCorpVaultStore,
    VaultBackend,
    VaultConfig,
    create_vault_backend,
)

__all__ = [
    # Core Auth
    "AuthConfig",
    "AuthManager",
    "EnrollmentMode",
    "Permission",
    "Role",
    "TokenPayload",
    "WorkerEnrollment",
    # Crypto
    "CryptoManager",
    # RBAC
    "AccessDecision",
    "Effect",
    "RBACPermission",
    "RBACPolicy",
    "RBACPolicyEngine",
    "RBACManager",
    "Resource",
    "RBACRole",
    "RBACUser",
    "require_permission",
    # MFA
    "MFADevice",
    "MFAManager",
    "MFAMiddleware",
    "MFAStatus",
    "MFAType",
    "TOTPConfig",
    "TOTPGenerator",
    "create_mfa_manager",
    # Session
    "DeviceFingerprint",
    "GeoLocation",
    "Session",
    "SessionConfig",
    "SessionEvent",
    "SessionManager",
    "SessionStatus",
    "SessionTokenManager",
    "create_session_manager",
    # Policy
    "AccessControlPolicies",
    "ConditionOperator",
    "NetworkSecurityPolicies",
    "PolicyCondition",
    "PolicyDecision",
    "PolicyEffect",
    "PolicyEngine",
    "PolicyPriority",
    "PolicyRule",
    "RiskBasedPolicies",
    "SecurityPolicy",
    "TimeBasedPolicies",
    "create_policy_engine",
    # Monitoring
    "AnomalyDetector",
    "BruteForceDetector",
    "MonitoringConfig",
    "SecurityAlert",
    "MonitoringSecurityEvent",
    "SecurityEventType",
    "SecurityMonitor",
    "ThreatDetector",
    "ThreatLevel",
    "ThreatType",
    "create_security_monitor",
    # Account
    "AccountSecurityInfo",
    "AccountSecurityManager",
    "AccountStatus",
    "PasswordHash",
    "PasswordHasher",
    "PasswordPolicy",
    "PasswordStrength",
    "PasswordValidationResult",
    "PasswordValidator",
    "create_account_security_manager",
    # mTLS
    "CertificateAuthority",
    "CertificateBundle",
    "CertificateInfo",
    "CertificateStatus",
    "CertificateStore",
    "CertificateType",
    "FileCertificateStore",
    "KeyAlgorithm",
    "MemoryCertificateStore",
    "MTLSAuthenticator",
    "create_cluster_ca",
    # Secrets
    "Encryptor",
    "FileSecretStore",
    "MemorySecretStore",
    "Secret",
    "SecretMetadata",
    "SecretsManager",
    "SecretStore",
    "SecretType",
    # Audit
    "AuditAction",
    "AuditBackend",
    "AuditEvent",
    "AuditLogger",
    "AuditResult",
    "FileAuditBackend",
    "MemoryAuditBackend",
    "CompositeAuditBackend",
    "PostgreSQLAuditBackend",
    "SQLiteAuditBackend",
    "create_audit_backend",
    # Vault
    "AWSSecretsManagerStore",
    "AzureKeyVaultStore",
    "HashiCorpVaultStore",
    "VaultBackend",
    "VaultConfig",
    "create_vault_backend",
    # Rate Limiting
    "AdaptiveRateLimiter",
    "DistributedRateLimiter",
    "FixedWindow",
    "RateLimitConfig",
    "RateLimitExceeded",
    "RateLimitInfo",
    "RateLimiter",
    "SlidingWindow",
    "TokenBucket",
    "rate_limit",
    # OAuth
    "GrantType",
    "JWTHandler",
    "OAuth2Client",
    "OAuth2Config",
    "OAuth2Error",
    "OIDCProvider",
    "TokenInfo",
    "TokenManager",
    "TokenType",
    # Unified Security Manager
    "AccessRequest",
    "AccessResult",
    "AuthenticationMethod",
    "AuthenticationResult",
    "ClusterSecurityManager",
    "SecurityConfig",
    "create_cluster_security_manager",
]
