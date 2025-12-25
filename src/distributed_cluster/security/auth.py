"""
Authentication & Authorization - المصادقة والتفويض
=====================================================

نظام أمان للـ distributed cluster:

1. **Worker Enrollment**: تسجيل workers بأمان
   - Token لمرة واحدة
   - Allowlist بالـ fingerprint
   - mTLS (اختياري)

2. **Token-based Auth**: JWT للجلسات
   - Worker tokens
   - Client/API tokens
   - Token refresh

3. **RBAC**: صلاحيات مبنية على الأدوار
   - Admin: كل شيء
   - Operator: إدارة jobs و workers
   - User: إرسال jobs فقط
   - Worker: heartbeat و report فقط
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Set


class EnrollmentMode(str, Enum):
    """طرق تسجيل Workers."""

    AUTO_APPROVE = "auto_approve"  # موافقة تلقائية (للتطوير فقط!)
    TOKEN = "token"  # تسجيل بـ token
    ALLOWLIST = "allowlist"  # تسجيل بـ fingerprint allowlist


@dataclass
class AuthConfig:
    """إعدادات المصادقة."""

    secret_key: str = "change-me-in-production"
    token_expiry_hours: int = 24
    enrollment_mode: EnrollmentMode = EnrollmentMode.AUTO_APPROVE
    allowlist_fingerprints: list[str] = field(default_factory=list)
    # Aliases for compatibility
    enrollment_tokens: set = field(default_factory=set)  # One-time tokens
    allowed_fingerprints: set = field(default_factory=set)  # Allowed fingerprints


class Permission(str, Enum):
    """صلاحيات النظام."""

    # Job permissions
    JOB_SUBMIT = "job:submit"
    JOB_READ = "job:read"
    JOB_CANCEL = "job:cancel"
    JOB_READ_ALL = "job:read_all"

    # Worker permissions
    WORKER_REGISTER = "worker:register"
    WORKER_HEARTBEAT = "worker:heartbeat"
    WORKER_REPORT = "worker:report"
    WORKER_READ = "worker:read"
    WORKER_MANAGE = "worker:manage"  # ban, drain, remove
    WORKER_POLL_JOBS = "worker:poll_jobs"

    # Admin permissions
    ADMIN_CONFIG = "admin:config"
    ADMIN_USERS = "admin:users"
    ADMIN_AUDIT = "admin:audit"

    # Cluster permissions
    CLUSTER_STATS = "cluster:stats"
    CLUSTER_EVENTS = "cluster:events"

    # Aliases for compatibility with tests
    SUBMIT_JOB = "job:submit"
    VIEW_JOBS = "job:read"
    CANCEL_JOB = "job:cancel"
    MANAGE_WORKERS = "worker:manage"
    VIEW_METRICS = "cluster:stats"


class Role(str, Enum):
    """أدوار المستخدمين."""

    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"
    WORKER = "worker"
    READONLY = "readonly"


# Role -> Permissions mapping
ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.ADMIN: set(Permission),  # كل الصلاحيات
    Role.OPERATOR: {
        Permission.JOB_SUBMIT,
        Permission.JOB_READ,
        Permission.JOB_CANCEL,
        Permission.JOB_READ_ALL,
        Permission.WORKER_READ,
        Permission.WORKER_MANAGE,
        Permission.CLUSTER_STATS,
        Permission.CLUSTER_EVENTS,
    },
    Role.USER: {
        Permission.JOB_SUBMIT,
        Permission.JOB_READ,
        Permission.JOB_CANCEL,
        Permission.CLUSTER_STATS,
    },
    Role.WORKER: {
        Permission.WORKER_REGISTER,
        Permission.WORKER_HEARTBEAT,
        Permission.WORKER_REPORT,
        Permission.WORKER_POLL_JOBS,
    },
    Role.READONLY: {
        Permission.JOB_READ,
        Permission.WORKER_READ,
        Permission.CLUSTER_STATS,
    },
}


@dataclass
class TokenPayload:
    """محتوى الـ Token (JWT-like)."""

    subject: str  # user_id or worker_id
    subject_type: str  # "user", "worker", "api_key"
    role: Role
    permissions: Set[Permission] = field(default_factory=set)

    issued_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    not_before: Optional[datetime] = None

    # Additional claims
    worker_id: Optional[str] = None
    user_id: Optional[str] = None
    api_key_id: Optional[str] = None
    session_id: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        """هل انتهت صلاحية الـ token؟"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """هل الـ token صالح؟"""
        now = datetime.utcnow()
        if self.expires_at and now > self.expires_at:
            return False
        if self.not_before and now < self.not_before:
            return False
        return True

    def has_permission(self, permission: Permission) -> bool:
        """هل يملك صلاحية معينة؟"""
        # Check explicit permissions first
        if permission in self.permissions:
            return True
        # Check role permissions
        role_perms = ROLE_PERMISSIONS.get(self.role, set())
        return permission in role_perms

    def to_dict(self) -> dict:
        """تحويل إلى dictionary (للـ encoding)."""
        return {
            "sub": self.subject,
            "sub_type": self.subject_type,
            "role": self.role.value,
            "perms": [p.value for p in self.permissions],
            "iat": int(self.issued_at.timestamp()),
            "exp": int(self.expires_at.timestamp()) if self.expires_at else None,
            "nbf": int(self.not_before.timestamp()) if self.not_before else None,
            "worker_id": self.worker_id,
            "user_id": self.user_id,
            "api_key_id": self.api_key_id,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TokenPayload:
        """إنشاء من dictionary."""
        return cls(
            subject=data["sub"],
            subject_type=data["sub_type"],
            role=Role(data["role"]),
            permissions={Permission(p) for p in data.get("perms", [])},
            issued_at=datetime.fromtimestamp(data["iat"]),
            expires_at=datetime.fromtimestamp(data["exp"]) if data.get("exp") else None,
            not_before=datetime.fromtimestamp(data["nbf"]) if data.get("nbf") else None,
            worker_id=data.get("worker_id"),
            user_id=data.get("user_id"),
            api_key_id=data.get("api_key_id"),
            session_id=data.get("session_id"),
        )


@dataclass
class WorkerEnrollment:
    """
    تسجيل Worker.

    ثلاث طرق للتسجيل:
    1. Enrollment Token: token لمرة واحدة يُعطى للـ worker مسبقاً
    2. Allowlist: قائمة بـ fingerprints المسموحة
    3. Auto-approve: موافقة تلقائية (للتطوير فقط!)
    """

    enrollment_id: str
    worker_fingerprint: str  # SHA256 of public key or machine ID
    status: str = "pending"  # pending, approved, rejected, revoked

    # Token-based enrollment
    enrollment_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None

    # Metadata
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    requested_at: datetime = field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    rejection_reason: Optional[str] = None

    @classmethod
    def create_token(cls, expires_in_hours: int = 24) -> tuple[str, WorkerEnrollment]:
        """
        إنشاء enrollment token.

        Returns:
            (token, enrollment) حيث token يُعطى للـ worker
        """
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        enrollment = cls(
            enrollment_id=f"enroll-{secrets.token_hex(8)}",
            worker_fingerprint="",  # Will be set when worker registers
            enrollment_token=token_hash,
            token_expires_at=datetime.utcnow() + timedelta(hours=expires_in_hours),
        )

        return token, enrollment

    def validate_token(self, provided_token: str) -> bool:
        """التحقق من صحة token."""
        if not self.enrollment_token:
            return False
        if self.token_expires_at and datetime.utcnow() > self.token_expires_at:
            return False

        provided_hash = hashlib.sha256(provided_token.encode()).hexdigest()
        return hmac.compare_digest(self.enrollment_token, provided_hash)


class AuthManager:
    """
    مدير المصادقة والتفويض.

    المسؤوليات:
    1. إنشاء والتحقق من tokens
    2. إدارة worker enrollment
    3. التحقق من الصلاحيات
    """

    def __init__(
        self,
        config: Optional[AuthConfig] = None,
        # Legacy parameters for backwards compatibility
        secret_key: Optional[str] = None,
        token_expiry_hours: int = 24,
        auto_approve_workers: bool = False,
    ):
        """
        Args:
            config: AuthConfig object (recommended)
            secret_key: مفتاح سري للـ signing (legacy)
            token_expiry_hours: مدة صلاحية الـ token (legacy)
            auto_approve_workers: موافقة تلقائية (legacy)
        """
        if config is not None:
            self.config = config
            self.secret_key = config.secret_key.encode() if isinstance(config.secret_key, str) else config.secret_key
            self.token_expiry_hours = config.token_expiry_hours
            self.auto_approve_workers = config.enrollment_mode == EnrollmentMode.AUTO_APPROVE
        else:
            # Legacy mode
            key = secret_key or "default-secret-key"
            self.secret_key = key.encode() if isinstance(key, str) else key
            self.token_expiry_hours = token_expiry_hours
            self.auto_approve_workers = auto_approve_workers
            self.config = AuthConfig(
                secret_key=secret_key or "default-secret-key",
                token_expiry_hours=token_expiry_hours,
                enrollment_mode=EnrollmentMode.AUTO_APPROVE if auto_approve_workers else EnrollmentMode.TOKEN,
            )

        # Storage
        self._enrollments: dict[str, WorkerEnrollment] = {}
        self._enrollment_tokens: dict[str, str] = {}  # token_hash -> enrollment_id
        self._fingerprint_allowlist: Set[str] = set()
        self._revoked_tokens: Set[str] = set()
        self._api_keys: dict[str, dict] = {}  # api_key_id -> key info

    def generate_token(self, payload: TokenPayload) -> str:
        """
        إنشاء token موقّع.

        يستخدم HMAC-SHA256 (مشابه لـ JWT بدون header).
        """
        if payload.expires_at is None:
            payload.expires_at = datetime.utcnow() + timedelta(hours=self.token_expiry_hours)

        payload.session_id = secrets.token_hex(16)

        # Encode payload
        payload_json = json.dumps(payload.to_dict(), sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()

        # Sign
        signature = hmac.new(self.secret_key, payload_b64.encode(), hashlib.sha256).hexdigest()

        return f"{payload_b64}.{signature}"

    def verify_token(self, token: str) -> Optional[TokenPayload]:
        """
        التحقق من token وإرجاع الـ payload.

        Returns:
            TokenPayload إذا صالح، None إذا غير صالح
        """
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return None

            payload_b64, signature = parts

            # Verify signature
            expected_sig = hmac.new(self.secret_key, payload_b64.encode(), hashlib.sha256).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return None

            # Decode payload
            payload_json = base64.urlsafe_b64decode(payload_b64).decode()
            payload_dict = json.loads(payload_json)
            payload = TokenPayload.from_dict(payload_dict)

            # Check if revoked
            if payload.session_id in self._revoked_tokens:
                return None

            # Check validity
            if not payload.is_valid:
                return None

            return payload

        except Exception:
            return None

    def revoke_token(self, token: str) -> bool:
        """إلغاء token."""
        payload = self.verify_token(token)
        if payload and payload.session_id:
            self._revoked_tokens.add(payload.session_id)
            return True
        return False

    def create_worker_token(
        self,
        worker_id: str,
        extra_permissions: Optional[Set[Permission]] = None,
    ) -> str:
        """إنشاء token لـ worker."""
        payload = TokenPayload(
            subject=worker_id,
            subject_type="worker",
            role=Role.WORKER,
            permissions=extra_permissions or set(),
            worker_id=worker_id,
        )
        return self.generate_token(payload)

    def create_user_token(
        self,
        user_id: str,
        role: Role = Role.USER,
        extra_permissions: Optional[Set[Permission]] = None,
    ) -> str:
        """إنشاء token لـ user."""
        payload = TokenPayload(
            subject=user_id,
            subject_type="user",
            role=role,
            permissions=extra_permissions or set(),
            user_id=user_id,
        )
        return self.generate_token(payload)

    def create_api_key(
        self,
        name: str,
        role: Role = Role.USER,
        expires_in_days: int = 365,
        permissions: Optional[set[Permission]] = None,
    ) -> tuple[str, str]:
        """
        إنشاء API key.

        Args:
            name: اسم وصفي للـ API key
            role: الدور المطلوب
            expires_in_days: مدة الصلاحية بالأيام
            permissions: أذونات مخصصة (اختياري)

        Returns:
            (api_key_id, api_key) - الـ api_key يُعطى للمستخدم مرة واحدة
        """
        api_key_id = f"ak_{secrets.token_hex(8)}"
        api_key_secret = secrets.token_urlsafe(32)

        # Store API key info
        self._api_keys[api_key_id] = {
            "name": name,
            "role": role,
            "permissions": permissions,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=expires_in_days),
        }

        payload = TokenPayload(
            subject=api_key_id,
            subject_type="api_key",
            role=role,
            api_key_id=api_key_id,
            permissions=set(permissions) if permissions else set(),
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
        )

        # الـ API key هو token موقّع
        token = self.generate_token(payload)

        # Return both the ID and full key (ID + secret for user to store)
        full_api_key = f"{api_key_id}.{api_key_secret}"
        return full_api_key, token

    def revoke_api_key(self, api_key_id: str) -> bool:
        """
        إلغاء API key.

        Args:
            api_key_id: معرف الـ API key

        Returns:
            True إذا تم الإلغاء بنجاح
        """
        # Extract key ID if full key provided
        if "." in api_key_id:
            api_key_id = api_key_id.split(".")[0]

        if api_key_id in self._api_keys:
            del self._api_keys[api_key_id]
            self._revoked_tokens.add(api_key_id)
            return True
        return False

    def get_api_key_info(self, api_key_id: str) -> Optional[dict]:
        """
        الحصول على معلومات API key.

        Args:
            api_key_id: معرف الـ API key

        Returns:
            معلومات الـ API key أو None
        """
        if "." in api_key_id:
            api_key_id = api_key_id.split(".")[0]
        return self._api_keys.get(api_key_id)

    def list_api_keys(self) -> list[dict]:
        """
        قائمة جميع الـ API keys.

        Returns:
            قائمة معلومات الـ API keys
        """
        return [
            {"id": key_id, **info}
            for key_id, info in self._api_keys.items()
        ]

    # ==================== Worker Enrollment ====================

    def create_enrollment_token(self, expires_in_hours: int = 24) -> str:
        """
        إنشاء enrollment token لـ worker جديد.

        Returns:
            Token يُعطى للـ worker
        """
        token, enrollment = WorkerEnrollment.create_token(expires_in_hours)
        self._enrollments[enrollment.enrollment_id] = enrollment
        self._enrollment_tokens[enrollment.enrollment_token] = enrollment.enrollment_id
        return token

    def add_to_allowlist(self, fingerprint: str) -> None:
        """إضافة fingerprint للقائمة المسموحة."""
        self._fingerprint_allowlist.add(fingerprint)

    def remove_from_allowlist(self, fingerprint: str) -> None:
        """إزالة fingerprint من القائمة المسموحة."""
        self._fingerprint_allowlist.discard(fingerprint)

    def enroll_worker(
        self,
        fingerprint: str,
        enrollment_token: Optional[str] = None,
        hostname: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[bool, str, Optional[str]]:
        """
        محاولة تسجيل worker.

        Returns:
            (approved, reason, worker_token_or_none)
        """
        # Method 1: Check enrollment token
        if enrollment_token:
            token_hash = hashlib.sha256(enrollment_token.encode()).hexdigest()
            enrollment_id = self._enrollment_tokens.get(token_hash)

            if enrollment_id:
                enrollment = self._enrollments.get(enrollment_id)
                if enrollment and enrollment.validate_token(enrollment_token):
                    enrollment.status = "approved"
                    enrollment.worker_fingerprint = fingerprint
                    enrollment.hostname = hostname
                    enrollment.ip_address = ip_address
                    enrollment.approved_at = datetime.utcnow()

                    # Remove used token
                    del self._enrollment_tokens[token_hash]

                    # Generate worker token
                    worker_id = f"worker-{secrets.token_hex(6)}"
                    token = self.create_worker_token(worker_id)

                    return True, "Enrolled via token", token

                return False, "Invalid or expired enrollment token", None

        # Method 2: Check allowlist
        if fingerprint in self._fingerprint_allowlist:
            worker_id = f"worker-{secrets.token_hex(6)}"
            token = self.create_worker_token(worker_id)
            return True, "Enrolled via allowlist", token

        # Method 3: Auto-approve (dangerous!)
        if self.auto_approve_workers:
            worker_id = f"worker-{secrets.token_hex(6)}"
            token = self.create_worker_token(worker_id)
            return True, "Auto-approved (WARNING: insecure mode)", token

        return False, "Worker not authorized. Provide enrollment token or contact admin.", None

    def check_permission(
        self,
        token: str,
        required_permission: Permission,
    ) -> tuple[bool, Optional[str]]:
        """
        التحقق من صلاحية معينة.

        Returns:
            (allowed, error_message)
        """
        payload = self.verify_token(token)
        if not payload:
            return False, "Invalid or expired token"

        if payload.has_permission(required_permission):
            return True, None

        return False, f"Permission denied: {required_permission.value}"

    def require_permission(self, token: str, permission: Permission) -> TokenPayload:
        """
        التحقق من صلاحية أو رفع exception.

        للاستخدام في API handlers.
        """
        allowed, error = self.check_permission(token, permission)
        if not allowed:
            raise PermissionError(error)

        return self.verify_token(token)
