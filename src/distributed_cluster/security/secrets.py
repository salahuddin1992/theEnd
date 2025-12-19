"""
Secrets Management - إدارة الأسرار
==================================

نظام آمن لإدارة الأسرار:
- تخزين مشفر
- إدارة الوصول
- حقن الأسرار للمهام
- تدوير الأسرار
- تكامل مع Vault (اختياري)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets as py_secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class SecretType(str, Enum):
    """نوع السر."""

    OPAQUE = "opaque"  # بيانات عامة
    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    CERTIFICATE = "certificate"
    SSH_KEY = "ssh_key"
    DOCKER_CONFIG = "docker_config"
    ENV_FILE = "env_file"


@dataclass
class SecretMetadata:
    """بيانات وصفية للسر."""

    name: str
    namespace: str = "default"
    secret_type: SecretType = SecretType.OPAQUE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    version: int = 1
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    owner: Optional[str] = None

    # Access control
    allowed_jobs: Set[str] = field(default_factory=set)  # job patterns
    allowed_users: Set[str] = field(default_factory=set)
    allowed_teams: Set[str] = field(default_factory=set)


@dataclass
class Secret:
    """سر واحد."""

    metadata: SecretMetadata
    data: Dict[str, bytes] = field(default_factory=dict)  # key -> encrypted value

    def get(self, key: str) -> Optional[bytes]:
        """الحصول على قيمة."""
        return self.data.get(key)

    def set(self, key: str, value: bytes) -> None:
        """تعيين قيمة."""
        self.data[key] = value
        self.metadata.updated_at = datetime.utcnow()

    def delete(self, key: str) -> bool:
        """حذف مفتاح."""
        if key in self.data:
            del self.data[key]
            self.metadata.updated_at = datetime.utcnow()
            return True
        return False

    def keys(self) -> List[str]:
        """قائمة المفاتيح."""
        return list(self.data.keys())

    def is_expired(self) -> bool:
        """هل انتهت صلاحية السر؟"""
        if self.metadata.expires_at:
            return datetime.utcnow() > self.metadata.expires_at
        return False

    def can_access(self, user_id: Optional[str], team_id: Optional[str], job_pattern: Optional[str]) -> bool:
        """التحقق من الصلاحية."""
        meta = self.metadata

        # Empty = allow all
        if not meta.allowed_users and not meta.allowed_teams and not meta.allowed_jobs:
            return True

        # Check user
        if user_id and (user_id in meta.allowed_users or "*" in meta.allowed_users):
            return True

        # Check team
        if team_id and (team_id in meta.allowed_teams or "*" in meta.allowed_teams):
            return True

        # Check job pattern
        if job_pattern:
            for pattern in meta.allowed_jobs:
                if pattern == "*" or pattern == job_pattern:
                    return True
                # Simple wildcard matching
                if pattern.endswith("*") and job_pattern.startswith(pattern[:-1]):
                    return True

        return False


class Encryptor:
    """مشفر الأسرار."""

    def __init__(self, master_key: Optional[str] = None):
        """
        تهيئة المشفر.

        Args:
            master_key: المفتاح الرئيسي (إذا لم يُعطَ، يُولَّد عشوائياً)
        """
        if master_key:
            # Derive key from master key
            self._key = self._derive_key(master_key.encode())
        else:
            # Generate random key
            self._key = Fernet.generate_key()

        self._fernet = Fernet(self._key)

    def _derive_key(self, password: bytes, salt: Optional[bytes] = None) -> bytes:
        """اشتقاق مفتاح من كلمة مرور."""
        if salt is None:
            salt = b"nebula-secrets-salt"  # Fixed salt for reproducibility

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key

    def encrypt(self, data: bytes) -> bytes:
        """تشفير البيانات."""
        return self._fernet.encrypt(data)

    def decrypt(self, encrypted: bytes) -> bytes:
        """فك التشفير."""
        return self._fernet.decrypt(encrypted)

    def encrypt_string(self, data: str) -> str:
        """تشفير نص."""
        encrypted = self.encrypt(data.encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    def decrypt_string(self, encrypted: str) -> str:
        """فك تشفير نص."""
        data = base64.b64decode(encrypted.encode("ascii"))
        return self.decrypt(data).decode("utf-8")


class SecretStore(ABC):
    """واجهة مخزن الأسرار."""

    @abstractmethod
    async def create(self, secret: Secret) -> bool:
        """إنشاء سر."""
        pass

    @abstractmethod
    async def get(self, name: str, namespace: str = "default") -> Optional[Secret]:
        """الحصول على سر."""
        pass

    @abstractmethod
    async def update(self, secret: Secret) -> bool:
        """تحديث سر."""
        pass

    @abstractmethod
    async def delete(self, name: str, namespace: str = "default") -> bool:
        """حذف سر."""
        pass

    @abstractmethod
    async def list(self, namespace: Optional[str] = None) -> List[SecretMetadata]:
        """قائمة الأسرار."""
        pass


class FileSecretStore(SecretStore):
    """
    مخزن أسرار ملفي.

    للتطوير والاختبار. لا يُنصح به للإنتاج.
    """

    def __init__(self, base_path: str, encryptor: Encryptor):
        self.base_path = Path(base_path)
        self.encryptor = encryptor
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _secret_path(self, name: str, namespace: str) -> Path:
        """مسار ملف السر."""
        ns_path = self.base_path / namespace
        ns_path.mkdir(exist_ok=True)
        return ns_path / f"{name}.secret"

    async def create(self, secret: Secret) -> bool:
        """إنشاء سر."""
        path = self._secret_path(secret.metadata.name, secret.metadata.namespace)

        if path.exists():
            return False

        # Encrypt all data
        encrypted_data = {}
        for key, value in secret.data.items():
            encrypted_data[key] = base64.b64encode(self.encryptor.encrypt(value)).decode("ascii")

        # Serialize
        data = {
            "metadata": {
                "name": secret.metadata.name,
                "namespace": secret.metadata.namespace,
                "secret_type": secret.metadata.secret_type.value,
                "created_at": secret.metadata.created_at.isoformat(),
                "updated_at": secret.metadata.updated_at.isoformat(),
                "expires_at": secret.metadata.expires_at.isoformat() if secret.metadata.expires_at else None,
                "version": secret.metadata.version,
                "labels": secret.metadata.labels,
                "annotations": secret.metadata.annotations,
                "owner": secret.metadata.owner,
                "allowed_jobs": list(secret.metadata.allowed_jobs),
                "allowed_users": list(secret.metadata.allowed_users),
                "allowed_teams": list(secret.metadata.allowed_teams),
            },
            "data": encrypted_data,
        }

        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Created secret: {secret.metadata.namespace}/{secret.metadata.name}")
        return True

    async def get(self, name: str, namespace: str = "default") -> Optional[Secret]:
        """الحصول على سر."""
        path = self._secret_path(name, namespace)

        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        meta_data = data["metadata"]

        metadata = SecretMetadata(
            name=meta_data["name"],
            namespace=meta_data["namespace"],
            secret_type=SecretType(meta_data["secret_type"]),
            created_at=datetime.fromisoformat(meta_data["created_at"]),
            updated_at=datetime.fromisoformat(meta_data["updated_at"]),
            expires_at=datetime.fromisoformat(meta_data["expires_at"]) if meta_data["expires_at"] else None,
            version=meta_data["version"],
            labels=meta_data.get("labels", {}),
            annotations=meta_data.get("annotations", {}),
            owner=meta_data.get("owner"),
            allowed_jobs=set(meta_data.get("allowed_jobs", [])),
            allowed_users=set(meta_data.get("allowed_users", [])),
            allowed_teams=set(meta_data.get("allowed_teams", [])),
        )

        # Decrypt data
        decrypted_data = {}
        for key, encrypted in data["data"].items():
            decrypted_data[key] = self.encryptor.decrypt(base64.b64decode(encrypted.encode("ascii")))

        return Secret(metadata=metadata, data=decrypted_data)

    async def update(self, secret: Secret) -> bool:
        """تحديث سر."""
        path = self._secret_path(secret.metadata.name, secret.metadata.namespace)

        if not path.exists():
            return False

        # Increment version
        secret.metadata.version += 1
        secret.metadata.updated_at = datetime.utcnow()

        # Delete and recreate
        path.unlink()
        return await self.create(secret)

    async def delete(self, name: str, namespace: str = "default") -> bool:
        """حذف سر."""
        path = self._secret_path(name, namespace)

        if not path.exists():
            return False

        path.unlink()
        logger.info(f"Deleted secret: {namespace}/{name}")
        return True

    async def list(self, namespace: Optional[str] = None) -> List[SecretMetadata]:
        """قائمة الأسرار."""
        secrets = []

        if namespace:
            ns_path = self.base_path / namespace
            if ns_path.exists():
                for path in ns_path.glob("*.secret"):
                    secret = await self.get(path.stem, namespace)
                    if secret:
                        secrets.append(secret.metadata)
        else:
            for ns_path in self.base_path.iterdir():
                if ns_path.is_dir():
                    for path in ns_path.glob("*.secret"):
                        secret = await self.get(path.stem, ns_path.name)
                        if secret:
                            secrets.append(secret.metadata)

        return secrets


class MemorySecretStore(SecretStore):
    """مخزن أسرار في الذاكرة (للاختبار)."""

    def __init__(self, encryptor: Encryptor):
        self.encryptor = encryptor
        self._secrets: Dict[str, Secret] = {}

    def _key(self, name: str, namespace: str) -> str:
        return f"{namespace}/{name}"

    async def create(self, secret: Secret) -> bool:
        key = self._key(secret.metadata.name, secret.metadata.namespace)
        if key in self._secrets:
            return False
        self._secrets[key] = secret
        return True

    async def get(self, name: str, namespace: str = "default") -> Optional[Secret]:
        key = self._key(name, namespace)
        return self._secrets.get(key)

    async def update(self, secret: Secret) -> bool:
        key = self._key(secret.metadata.name, secret.metadata.namespace)
        if key not in self._secrets:
            return False
        secret.metadata.version += 1
        secret.metadata.updated_at = datetime.utcnow()
        self._secrets[key] = secret
        return True

    async def delete(self, name: str, namespace: str = "default") -> bool:
        key = self._key(name, namespace)
        if key not in self._secrets:
            return False
        del self._secrets[key]
        return True

    async def list(self, namespace: Optional[str] = None) -> List[SecretMetadata]:
        secrets = []
        for key, secret in self._secrets.items():
            if namespace is None or secret.metadata.namespace == namespace:
                secrets.append(secret.metadata)
        return secrets


class SecretsManager:
    """
    مدير الأسرار الرئيسي.

    يوفر واجهة عالية المستوى لإدارة الأسرار.
    """

    def __init__(self, store: SecretStore, encryptor: Encryptor):
        self.store = store
        self.encryptor = encryptor

    async def create_secret(
        self,
        name: str,
        data: Dict[str, str],
        namespace: str = "default",
        secret_type: SecretType = SecretType.OPAQUE,
        expires_in: Optional[timedelta] = None,
        labels: Optional[Dict[str, str]] = None,
        owner: Optional[str] = None,
        allowed_jobs: Optional[List[str]] = None,
        allowed_users: Optional[List[str]] = None,
    ) -> bool:
        """
        إنشاء سر جديد.

        Args:
            name: اسم السر
            data: البيانات (key -> value)
            namespace: مساحة الاسم
            secret_type: نوع السر
            expires_in: مدة الصلاحية
            labels: تصنيفات
            owner: المالك
            allowed_jobs: المهام المسموح لها
            allowed_users: المستخدمون المسموح لهم
        """
        metadata = SecretMetadata(
            name=name,
            namespace=namespace,
            secret_type=secret_type,
            expires_at=datetime.utcnow() + expires_in if expires_in else None,
            labels=labels or {},
            owner=owner,
            allowed_jobs=set(allowed_jobs or []),
            allowed_users=set(allowed_users or []),
        )

        # Encode data as bytes
        secret_data = {k: v.encode("utf-8") for k, v in data.items()}

        secret = Secret(metadata=metadata, data=secret_data)
        return await self.store.create(secret)

    async def get_secret(
        self,
        name: str,
        namespace: str = "default",
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        job_pattern: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """
        الحصول على سر.

        يتحقق من الصلاحيات والصلاحية.
        """
        secret = await self.store.get(name, namespace)

        if not secret:
            return None

        # Check expiration
        if secret.is_expired():
            logger.warning(f"Secret {namespace}/{name} has expired")
            return None

        # Check access
        if not secret.can_access(user_id, team_id, job_pattern):
            logger.warning(f"Access denied to secret {namespace}/{name}")
            return None

        # Decode data
        return {k: v.decode("utf-8") for k, v in secret.data.items()}

    async def update_secret(
        self,
        name: str,
        data: Dict[str, str],
        namespace: str = "default",
    ) -> bool:
        """تحديث سر."""
        secret = await self.store.get(name, namespace)
        if not secret:
            return False

        # Update data
        secret.data = {k: v.encode("utf-8") for k, v in data.items()}
        return await self.store.update(secret)

    async def delete_secret(self, name: str, namespace: str = "default") -> bool:
        """حذف سر."""
        return await self.store.delete(name, namespace)

    async def list_secrets(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """قائمة الأسرار (metadata فقط)."""
        secrets = await self.store.list(namespace)
        return [
            {
                "name": s.name,
                "namespace": s.namespace,
                "type": s.secret_type.value,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "version": s.version,
                "labels": s.labels,
            }
            for s in secrets
        ]

    async def inject_secrets(
        self,
        secret_refs: List[str],  # ["namespace/name", "name"]
        user_id: Optional[str] = None,
        job_pattern: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        حقن أسرار متعددة.

        يُستخدم لحقن الأسرار كمتغيرات بيئة للمهام.

        Args:
            secret_refs: قائمة مراجع الأسرار
            user_id: معرف المستخدم
            job_pattern: نمط المهمة

        Returns:
            Dict من المتغيرات البيئية
        """
        env_vars = {}

        for ref in secret_refs:
            if "/" in ref:
                namespace, name = ref.split("/", 1)
            else:
                namespace, name = "default", ref

            secret_data = await self.get_secret(
                name,
                namespace,
                user_id=user_id,
                job_pattern=job_pattern,
            )

            if secret_data:
                for key, value in secret_data.items():
                    env_name = f"{name.upper().replace('-', '_')}_{key.upper()}"
                    env_vars[env_name] = value

        return env_vars

    async def rotate_secret(
        self,
        name: str,
        namespace: str = "default",
        generator: Optional[Callable[[], str]] = None,
    ) -> bool:
        """
        تدوير سر (توليد قيم جديدة).

        Args:
            name: اسم السر
            namespace: مساحة الاسم
            generator: دالة توليد القيم (افتراضي: كلمة مرور عشوائية)
        """
        secret = await self.store.get(name, namespace)
        if not secret:
            return False

        if generator is None:

            def generator():
                return py_secrets.token_urlsafe(32)

        # Generate new values for all keys
        new_data = {}
        for key in secret.data.keys():
            new_data[key] = generator().encode("utf-8")

        secret.data = new_data
        return await self.store.update(secret)

    def generate_password(self, length: int = 32) -> str:
        """توليد كلمة مرور آمنة."""
        return py_secrets.token_urlsafe(length)

    def generate_api_key(self, prefix: str = "neb") -> str:
        """توليد مفتاح API."""
        return f"{prefix}_{py_secrets.token_urlsafe(32)}"


# =============================================================================
# Helper Functions
# =============================================================================


def create_secrets_manager(
    master_key: Optional[str] = None,
    store_type: str = "memory",
    store_path: Optional[str] = None,
) -> SecretsManager:
    """
    إنشاء مدير أسرار.

    Args:
        master_key: المفتاح الرئيسي (من البيئة إذا لم يُعطَ)
        store_type: نوع المخزن (memory, file)
        store_path: مسار المخزن (للملفات)
    """
    # Get master key
    if master_key is None:
        master_key = os.environ.get("NEBULA_SECRET_KEY")

    if not master_key:
        logger.warning("No master key provided, generating random key")

    encryptor = Encryptor(master_key)

    if store_type == "file":
        if not store_path:
            store_path = "./data/secrets"
        store = FileSecretStore(store_path, encryptor)
    else:
        store = MemorySecretStore(encryptor)

    return SecretsManager(store, encryptor)
