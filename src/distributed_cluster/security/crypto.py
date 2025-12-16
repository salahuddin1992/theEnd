"""
Cryptography Utilities - أدوات التشفير
========================================

أدوات مساعدة للتشفير:
- توليد مفاتيح
- Fingerprints
- Checksums
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import base64
from typing import Optional
import os


class CryptoManager:
    """
    مدير التشفير.

    يوفر أدوات موحدة للتشفير في النظام.
    """

    @staticmethod
    def generate_secret_key(length: int = 32) -> str:
        """توليد مفتاح سري."""
        return secrets.token_hex(length)

    @staticmethod
    def generate_token(length: int = 32) -> str:
        """توليد token آمن."""
        return secrets.token_urlsafe(length)

    @staticmethod
    def hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
        """
        تشفير كلمة مرور.

        Returns:
            (hash, salt) كلاهما base64
        """
        if salt is None:
            salt = os.urandom(16)

        # Use PBKDF2
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            salt,
            iterations=100000,
        )

        return (
            base64.b64encode(key).decode(),
            base64.b64encode(salt).decode(),
        )

    @staticmethod
    def verify_password(password: str, hash_b64: str, salt_b64: str) -> bool:
        """التحقق من كلمة مرور."""
        salt = base64.b64decode(salt_b64)
        expected_key = base64.b64decode(hash_b64)

        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            salt,
            iterations=100000,
        )

        return hmac.compare_digest(key, expected_key)

    @staticmethod
    def compute_fingerprint(data: bytes) -> str:
        """
        حساب fingerprint.

        يُستخدم للـ:
        - Worker public keys
        - Machine IDs
        - File checksums
        """
        return f"sha256:{hashlib.sha256(data).hexdigest()}"

    @staticmethod
    def compute_file_checksum(filepath: str, algorithm: str = "sha256") -> str:
        """حساب checksum لملف."""
        hash_func = hashlib.new(algorithm)

        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_func.update(chunk)

        return f"{algorithm}:{hash_func.hexdigest()}"

    @staticmethod
    def verify_checksum(filepath: str, expected: str) -> bool:
        """التحقق من checksum ملف."""
        if ":" not in expected:
            return False

        algorithm, expected_hash = expected.split(":", 1)
        actual = CryptoManager.compute_file_checksum(filepath, algorithm)
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def generate_machine_fingerprint() -> str:
        """
        توليد fingerprint للجهاز.

        يحاول استخدام معرّفات ثابتة:
        - Machine ID (Linux)
        - Hardware UUID (Mac)
        - Volume serial (Windows)
        """
        identifiers = []

        # Try Linux machine-id
        try:
            with open("/etc/machine-id", "r") as f:
                identifiers.append(f.read().strip())
        except Exception:
            pass

        # Try DMI product UUID
        try:
            with open("/sys/class/dmi/id/product_uuid", "r") as f:
                identifiers.append(f.read().strip())
        except Exception:
            pass

        # Fallback to hostname + random
        if not identifiers:
            import socket
            identifiers.append(socket.gethostname())
            identifiers.append(secrets.token_hex(16))

        combined = ":".join(identifiers)
        return CryptoManager.compute_fingerprint(combined.encode())

    @staticmethod
    def constant_time_compare(a: str, b: str) -> bool:
        """مقارنة آمنة ضد timing attacks."""
        return hmac.compare_digest(a.encode(), b.encode())
