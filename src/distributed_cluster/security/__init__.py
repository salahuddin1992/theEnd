"""
Security Module - وحدة الأمان
==============================

أمان وتشفير وتدقيق النظام:
- Authentication & Authorization
- Secrets Management
- Audit Logging
- Cryptographic Utilities
"""

from distributed_cluster.security.auth import (
    AuthConfig,
    AuthManager,
    EnrollmentMode,
    Permission,
    Role,
    TokenPayload,
    WorkerEnrollment,
)
from distributed_cluster.security.crypto import CryptoManager

from distributed_cluster.security.secrets import (
    Secret,
    SecretMetadata,
    SecretType,
    SecretsManager,
    SecretStore,
    FileSecretStore,
    MemorySecretStore,
    Encryptor,
)

from distributed_cluster.security.audit import (
    AuditAction,
    AuditEvent,
    AuditResult,
    AuditBackend,
    AuditLogger,
    FileAuditBackend,
    MemoryAuditBackend,
)

from distributed_cluster.security.audit_backends import (
    SQLiteAuditBackend,
    PostgreSQLAuditBackend,
    CompositeAuditBackend,
    create_audit_backend,
)

from distributed_cluster.security.vault_backends import (
    VaultConfig,
    VaultBackend,
    HashiCorpVaultStore,
    AWSSecretsManagerStore,
    AzureKeyVaultStore,
    create_vault_backend,
)

__all__ = [
    # Auth
    "AuthConfig",
    "AuthManager",
    "EnrollmentMode",
    "Permission",
    "Role",
    "TokenPayload",
    "WorkerEnrollment",
    # Crypto
    "CryptoManager",
    # Secrets
    "Secret",
    "SecretMetadata",
    "SecretType",
    "SecretsManager",
    "SecretStore",
    "FileSecretStore",
    "MemorySecretStore",
    "Encryptor",
    # Audit
    "AuditAction",
    "AuditEvent",
    "AuditResult",
    "AuditBackend",
    "AuditLogger",
    "FileAuditBackend",
    "MemoryAuditBackend",
    "SQLiteAuditBackend",
    "PostgreSQLAuditBackend",
    "CompositeAuditBackend",
    "create_audit_backend",
    # Vault Backends
    "VaultConfig",
    "VaultBackend",
    "HashiCorpVaultStore",
    "AWSSecretsManagerStore",
    "AzureKeyVaultStore",
    "create_vault_backend",
]
