"""
Multi-Factor Authentication (MFA) - المصادقة متعددة العوامل
============================================================

TOTP/HOTP-based multi-factor authentication.
مصادقة متعددة العوامل قائمة على كلمات المرور لمرة واحدة.

Features:
- TOTP (Time-based One-Time Password) - RFC 6238
- HOTP (HMAC-based One-Time Password) - RFC 4226
- Backup/Recovery codes
- Device registration and management
- Rate limiting for failed attempts
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import struct
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from io import BytesIO

    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

logger = logging.getLogger(__name__)


class MFAType(str, Enum):
    """MFA method types."""
    TOTP = "totp"  # Time-based OTP (Authenticator apps)
    HOTP = "hotp"  # Counter-based OTP
    BACKUP_CODE = "backup_code"  # Recovery codes
    EMAIL = "email"  # Email OTP (not recommended)
    SMS = "sms"  # SMS OTP (not recommended)
    HARDWARE_KEY = "hardware_key"  # Hardware security keys (FIDO2)


class MFAStatus(str, Enum):
    """MFA enrollment status."""
    NOT_ENROLLED = "not_enrolled"
    PENDING = "pending"  # Awaiting verification
    ENROLLED = "enrolled"
    DISABLED = "disabled"


@dataclass
class TOTPConfig:
    """TOTP configuration."""
    digits: int = 6  # OTP length (6 or 8)
    period: int = 30  # Time step in seconds
    algorithm: str = "SHA1"  # SHA1, SHA256, SHA512
    issuer: str = "NebulaCompute"
    secret_length: int = 20  # Secret key length in bytes
    drift_tolerance: int = 1  # Number of periods to allow for clock drift
    rate_limit_attempts: int = 5  # Max failed attempts
    rate_limit_window: int = 300  # Rate limit window in seconds
    lockout_duration: int = 900  # Lockout duration after max attempts (15 min)


@dataclass
class MFADevice:
    """Registered MFA device."""
    device_id: str
    user_id: str
    device_name: str
    mfa_type: MFAType
    status: MFAStatus = MFAStatus.NOT_ENROLLED
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    verified_at: Optional[datetime] = None

    # TOTP-specific fields
    secret: Optional[str] = None  # Base32-encoded secret
    counter: int = 0  # For HOTP

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "user_id": self.user_id,
            "device_name": self.device_name,
            "mfa_type": self.mfa_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
        }


@dataclass
class BackupCodes:
    """Backup recovery codes."""
    user_id: str
    codes: Set[str] = field(default_factory=set)  # Hashed codes
    created_at: datetime = field(default_factory=datetime.utcnow)
    used_codes: Set[str] = field(default_factory=set)  # Used code hashes

    def remaining_count(self) -> int:
        return len(self.codes - self.used_codes)


@dataclass
class MFAChallenge:
    """Active MFA challenge."""
    challenge_id: str
    user_id: str
    mfa_type: MFAType
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=5))
    verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at


class TOTPGenerator:
    """
    TOTP/HOTP One-Time Password Generator.

    Implements RFC 4226 (HOTP) and RFC 6238 (TOTP).
    """

    def __init__(self, config: Optional[TOTPConfig] = None):
        self.config = config or TOTPConfig()
        self._hash_algorithms = {
            "SHA1": hashlib.sha1,
            "SHA256": hashlib.sha256,
            "SHA512": hashlib.sha512,
        }

    def generate_secret(self) -> str:
        """Generate a random secret key."""
        secret = os.urandom(self.config.secret_length)
        return base64.b32encode(secret).decode("utf-8").rstrip("=")

    def _get_hash_func(self):
        """Get the hash function based on configuration."""
        return self._hash_algorithms.get(self.config.algorithm, hashlib.sha1)

    def _hotp(self, secret: str, counter: int) -> str:
        """
        Generate HOTP code.

        RFC 4226 implementation.
        """
        # Decode secret
        secret_bytes = self._decode_secret(secret)

        # Pack counter as 8-byte big-endian
        counter_bytes = struct.pack(">Q", counter)

        # Compute HMAC
        hash_func = self._get_hash_func()
        hmac_hash = hmac.new(secret_bytes, counter_bytes, hash_func).digest()

        # Dynamic truncation
        offset = hmac_hash[-1] & 0x0F
        truncated = struct.unpack(">I", hmac_hash[offset:offset + 4])[0] & 0x7FFFFFFF

        # Generate OTP
        otp = truncated % (10 ** self.config.digits)
        return str(otp).zfill(self.config.digits)

    def _decode_secret(self, secret: str) -> bytes:
        """Decode base32 secret."""
        # Add padding if necessary
        padding = 8 - len(secret) % 8
        if padding != 8:
            secret += "=" * padding
        return base64.b32decode(secret.upper())

    def generate_totp(self, secret: str, time_offset: int = 0) -> str:
        """
        Generate TOTP code.

        RFC 6238 implementation.
        """
        counter = (int(time.time()) // self.config.period) + time_offset
        return self._hotp(secret, counter)

    def verify_totp(
        self,
        secret: str,
        code: str,
        drift_tolerance: Optional[int] = None,
    ) -> Tuple[bool, int]:
        """
        Verify TOTP code.

        Returns:
            (is_valid, time_offset)
        """
        if drift_tolerance is None:
            drift_tolerance = self.config.drift_tolerance

        for offset in range(-drift_tolerance, drift_tolerance + 1):
            expected = self.generate_totp(secret, offset)
            if hmac.compare_digest(expected, code):
                return True, offset

        return False, 0

    def generate_hotp(self, secret: str, counter: int) -> str:
        """Generate HOTP code."""
        return self._hotp(secret, counter)

    def verify_hotp(
        self,
        secret: str,
        code: str,
        counter: int,
        look_ahead: int = 5,
    ) -> Tuple[bool, int]:
        """
        Verify HOTP code.

        Returns:
            (is_valid, new_counter)
        """
        for i in range(look_ahead):
            expected = self._hotp(secret, counter + i)
            if hmac.compare_digest(expected, code):
                return True, counter + i + 1

        return False, counter

    def get_provisioning_uri(
        self,
        secret: str,
        account_name: str,
        issuer: Optional[str] = None,
    ) -> str:
        """
        Generate otpauth:// URI for QR code.

        Compatible with Google Authenticator and similar apps.
        """
        issuer = issuer or self.config.issuer

        # URL encode the account name and issuer
        from urllib.parse import quote

        label = f"{quote(issuer)}:{quote(account_name)}" if issuer else quote(account_name)

        params = {
            "secret": secret,
            "issuer": issuer,
            "algorithm": self.config.algorithm,
            "digits": str(self.config.digits),
            "period": str(self.config.period),
        }

        param_str = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
        return f"otpauth://totp/{label}?{param_str}"

    def generate_qr_code(
        self,
        secret: str,
        account_name: str,
        issuer: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Generate QR code image.

        Returns PNG image data or None if qrcode library not available.
        """
        if not QRCODE_AVAILABLE:
            return None

        uri = self.get_provisioning_uri(secret, account_name, issuer)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()


class MFAStore(ABC):
    """Abstract MFA storage."""

    @abstractmethod
    def save_device(self, device: MFADevice) -> bool:
        pass

    @abstractmethod
    def get_device(self, device_id: str) -> Optional[MFADevice]:
        pass

    @abstractmethod
    def get_user_devices(self, user_id: str) -> List[MFADevice]:
        pass

    @abstractmethod
    def delete_device(self, device_id: str) -> bool:
        pass

    @abstractmethod
    def save_backup_codes(self, backup_codes: BackupCodes) -> bool:
        pass

    @abstractmethod
    def get_backup_codes(self, user_id: str) -> Optional[BackupCodes]:
        pass


class MemoryMFAStore(MFAStore):
    """In-memory MFA store for testing."""

    def __init__(self):
        self._devices: Dict[str, MFADevice] = {}
        self._backup_codes: Dict[str, BackupCodes] = {}
        self._lock = threading.RLock()

    def save_device(self, device: MFADevice) -> bool:
        with self._lock:
            self._devices[device.device_id] = device
            return True

    def get_device(self, device_id: str) -> Optional[MFADevice]:
        with self._lock:
            return self._devices.get(device_id)

    def get_user_devices(self, user_id: str) -> List[MFADevice]:
        with self._lock:
            return [d for d in self._devices.values() if d.user_id == user_id]

    def delete_device(self, device_id: str) -> bool:
        with self._lock:
            if device_id in self._devices:
                del self._devices[device_id]
                return True
            return False

    def save_backup_codes(self, backup_codes: BackupCodes) -> bool:
        with self._lock:
            self._backup_codes[backup_codes.user_id] = backup_codes
            return True

    def get_backup_codes(self, user_id: str) -> Optional[BackupCodes]:
        with self._lock:
            return self._backup_codes.get(user_id)


class MFAManager:
    """
    Multi-Factor Authentication Manager.

    Handles MFA enrollment, verification, and management.
    """

    def __init__(
        self,
        store: Optional[MFAStore] = None,
        config: Optional[TOTPConfig] = None,
    ):
        self.store = store or MemoryMFAStore()
        self.config = config or TOTPConfig()
        self.totp = TOTPGenerator(self.config)

        # Rate limiting
        self._failed_attempts: Dict[str, List[float]] = {}  # user_id -> timestamps
        self._lockouts: Dict[str, float] = {}  # user_id -> lockout_until
        self._lock = threading.RLock()

        # Active challenges
        self._challenges: Dict[str, MFAChallenge] = {}

    def _generate_device_id(self) -> str:
        """Generate a unique device ID."""
        return f"mfa_{secrets.token_hex(12)}"

    def _hash_code(self, code: str) -> str:
        """Hash a backup code for storage."""
        return hashlib.sha256(code.encode()).hexdigest()

    def _check_rate_limit(self, user_id: str) -> Tuple[bool, Optional[int]]:
        """
        Check if user is rate limited.

        Returns:
            (allowed, seconds_until_allowed)
        """
        with self._lock:
            now = time.time()

            # Check lockout
            if user_id in self._lockouts:
                lockout_until = self._lockouts[user_id]
                if now < lockout_until:
                    return False, int(lockout_until - now)
                else:
                    del self._lockouts[user_id]

            # Check recent failures
            if user_id in self._failed_attempts:
                window_start = now - self.config.rate_limit_window
                self._failed_attempts[user_id] = [
                    t for t in self._failed_attempts[user_id]
                    if t > window_start
                ]

                if len(self._failed_attempts[user_id]) >= self.config.rate_limit_attempts:
                    self._lockouts[user_id] = now + self.config.lockout_duration
                    return False, self.config.lockout_duration

            return True, None

    def _record_failed_attempt(self, user_id: str) -> None:
        """Record a failed verification attempt."""
        with self._lock:
            if user_id not in self._failed_attempts:
                self._failed_attempts[user_id] = []
            self._failed_attempts[user_id].append(time.time())

    def _clear_failed_attempts(self, user_id: str) -> None:
        """Clear failed attempts on successful verification."""
        with self._lock:
            self._failed_attempts.pop(user_id, None)
            self._lockouts.pop(user_id, None)

    # ====================== Enrollment ======================

    def start_totp_enrollment(
        self,
        user_id: str,
        device_name: str = "Authenticator App",
        account_name: Optional[str] = None,
    ) -> Tuple[MFADevice, str, Optional[bytes]]:
        """
        Start TOTP enrollment.

        Returns:
            (device, provisioning_uri, qr_code_png)
        """
        secret = self.totp.generate_secret()
        device_id = self._generate_device_id()

        device = MFADevice(
            device_id=device_id,
            user_id=user_id,
            device_name=device_name,
            mfa_type=MFAType.TOTP,
            status=MFAStatus.PENDING,
            secret=secret,
        )

        self.store.save_device(device)

        account = account_name or user_id
        uri = self.totp.get_provisioning_uri(secret, account)
        qr_code = self.totp.generate_qr_code(secret, account)

        logger.info(f"Started TOTP enrollment for user {user_id}")
        return device, uri, qr_code

    def complete_totp_enrollment(
        self,
        device_id: str,
        verification_code: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Complete TOTP enrollment by verifying first code.

        Returns:
            (success, error_message)
        """
        device = self.store.get_device(device_id)
        if not device:
            return False, "Device not found"

        if device.status != MFAStatus.PENDING:
            return False, "Device not in pending state"

        if not device.secret:
            return False, "Device secret not configured"

        # Verify the code
        valid, _ = self.totp.verify_totp(device.secret, verification_code)
        if not valid:
            return False, "Invalid verification code"

        # Complete enrollment
        device.status = MFAStatus.ENROLLED
        device.verified_at = datetime.now(timezone.utc)
        self.store.save_device(device)

        logger.info(f"Completed TOTP enrollment for device {device_id}")
        return True, None

    def generate_backup_codes(
        self,
        user_id: str,
        count: int = 10,
        code_length: int = 8,
    ) -> List[str]:
        """
        Generate backup recovery codes.

        Returns list of plain-text codes (show to user only once).
        """
        plain_codes = []
        hashed_codes = set()

        for _ in range(count):
            code = secrets.token_hex(code_length // 2).upper()
            # Format as XXXX-XXXX for readability
            formatted = f"{code[:4]}-{code[4:]}"
            plain_codes.append(formatted)
            hashed_codes.add(self._hash_code(code))

        backup = BackupCodes(
            user_id=user_id,
            codes=hashed_codes,
        )
        self.store.save_backup_codes(backup)

        logger.info(f"Generated {count} backup codes for user {user_id}")
        return plain_codes

    # ====================== Verification ======================

    def verify_totp(
        self,
        user_id: str,
        code: str,
        device_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify a TOTP code.

        Returns:
            (success, error_message)
        """
        # Check rate limit
        allowed, retry_after = self._check_rate_limit(user_id)
        if not allowed:
            return False, f"Rate limited. Retry after {retry_after} seconds"

        # Get user's TOTP devices
        devices = self.store.get_user_devices(user_id)
        totp_devices = [
            d for d in devices
            if d.mfa_type == MFAType.TOTP and d.status == MFAStatus.ENROLLED
        ]

        if device_id:
            totp_devices = [d for d in totp_devices if d.device_id == device_id]

        if not totp_devices:
            return False, "No enrolled TOTP devices"

        # Try verification against all devices
        for device in totp_devices:
            if not device.secret:
                continue

            valid, offset = self.totp.verify_totp(device.secret, code)
            if valid:
                # Update last used
                device.last_used = datetime.now(timezone.utc)
                self.store.save_device(device)
                self._clear_failed_attempts(user_id)

                logger.debug(f"TOTP verification successful for user {user_id}")
                return True, None

        self._record_failed_attempt(user_id)
        return False, "Invalid code"

    def verify_backup_code(
        self,
        user_id: str,
        code: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify and consume a backup code.

        Returns:
            (success, error_message)
        """
        # Check rate limit
        allowed, retry_after = self._check_rate_limit(user_id)
        if not allowed:
            return False, f"Rate limited. Retry after {retry_after} seconds"

        backup = self.store.get_backup_codes(user_id)
        if not backup:
            return False, "No backup codes configured"

        # Normalize code
        normalized = code.replace("-", "").replace(" ", "").upper()
        code_hash = self._hash_code(normalized)

        if code_hash not in backup.codes:
            self._record_failed_attempt(user_id)
            return False, "Invalid backup code"

        if code_hash in backup.used_codes:
            self._record_failed_attempt(user_id)
            return False, "Backup code already used"

        # Mark as used
        backup.used_codes.add(code_hash)
        self.store.save_backup_codes(backup)
        self._clear_failed_attempts(user_id)

        remaining = backup.remaining_count()
        logger.info(f"Backup code used for user {user_id}. {remaining} codes remaining")

        return True, None

    def verify(
        self,
        user_id: str,
        code: str,
        mfa_type: Optional[MFAType] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify any MFA code.

        Automatically detects type if not specified.
        """
        # Try backup code first if it looks like one
        if len(code.replace("-", "").replace(" ", "")) == 8:
            success, error = self.verify_backup_code(user_id, code)
            if success:
                return True, None

        # Try TOTP
        if mfa_type is None or mfa_type == MFAType.TOTP:
            success, error = self.verify_totp(user_id, code)
            if success:
                return True, None
            if mfa_type == MFAType.TOTP:
                return False, error

        return False, "Invalid MFA code"

    # ====================== Challenges ======================

    def create_challenge(
        self,
        user_id: str,
        mfa_type: MFAType = MFAType.TOTP,
        ttl_seconds: int = 300,
    ) -> MFAChallenge:
        """Create an MFA challenge."""
        challenge = MFAChallenge(
            challenge_id=f"mfa_challenge_{secrets.token_hex(16)}",
            user_id=user_id,
            mfa_type=mfa_type,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )

        with self._lock:
            self._challenges[challenge.challenge_id] = challenge

        return challenge

    def verify_challenge(
        self,
        challenge_id: str,
        code: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify an MFA challenge.

        Returns:
            (success, error_message)
        """
        with self._lock:
            challenge = self._challenges.get(challenge_id)

        if not challenge:
            return False, "Challenge not found"

        if challenge.is_expired:
            with self._lock:
                self._challenges.pop(challenge_id, None)
            return False, "Challenge expired"

        if challenge.verified:
            return False, "Challenge already verified"

        success, error = self.verify(challenge.user_id, code, challenge.mfa_type)

        if success:
            challenge.verified = True
            with self._lock:
                self._challenges.pop(challenge_id, None)

        return success, error

    # ====================== Management ======================

    def get_user_devices(self, user_id: str) -> List[MFADevice]:
        """Get all MFA devices for a user."""
        return self.store.get_user_devices(user_id)

    def get_enrolled_methods(self, user_id: str) -> List[MFAType]:
        """Get enrolled MFA methods for a user."""
        devices = self.store.get_user_devices(user_id)
        return list(set(
            d.mfa_type for d in devices
            if d.status == MFAStatus.ENROLLED
        ))

    def is_mfa_enabled(self, user_id: str) -> bool:
        """Check if user has MFA enabled."""
        return len(self.get_enrolled_methods(user_id)) > 0

    def disable_device(self, device_id: str) -> bool:
        """Disable an MFA device."""
        device = self.store.get_device(device_id)
        if not device:
            return False

        device.status = MFAStatus.DISABLED
        self.store.save_device(device)

        logger.info(f"Disabled MFA device {device_id}")
        return True

    def delete_device(self, device_id: str) -> bool:
        """Delete an MFA device."""
        result = self.store.delete_device(device_id)
        if result:
            logger.info(f"Deleted MFA device {device_id}")
        return result

    def get_backup_codes_count(self, user_id: str) -> int:
        """Get remaining backup codes count."""
        backup = self.store.get_backup_codes(user_id)
        if not backup:
            return 0
        return backup.remaining_count()

    def regenerate_backup_codes(self, user_id: str) -> List[str]:
        """Regenerate backup codes (invalidates existing ones)."""
        return self.generate_backup_codes(user_id)


class MFAMiddleware:
    """
    MFA Middleware for API routes.

    Enforces MFA verification for protected operations.
    """

    def __init__(
        self,
        mfa_manager: MFAManager,
        required_roles: Optional[List[str]] = None,
        exempt_paths: Optional[List[str]] = None,
    ):
        self.mfa_manager = mfa_manager
        self.required_roles = required_roles or ["admin", "operator"]
        self.exempt_paths = exempt_paths or ["/auth/login", "/auth/mfa/verify"]

    def is_mfa_required(
        self,
        user_id: str,
        user_role: str,
        path: str,
    ) -> bool:
        """Check if MFA is required for this request."""
        if path in self.exempt_paths:
            return False

        if user_role not in self.required_roles:
            return False

        return self.mfa_manager.is_mfa_enabled(user_id)

    async def verify_mfa_session(
        self,
        session_data: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that the session has passed MFA.

        Returns:
            (verified, error_message)
        """
        mfa_verified = session_data.get("mfa_verified", False)
        mfa_verified_at = session_data.get("mfa_verified_at")

        if not mfa_verified:
            return False, "MFA verification required"

        # Check if MFA verification is still valid (e.g., 24 hours)
        if mfa_verified_at:
            verified_at = datetime.fromisoformat(mfa_verified_at)
            if datetime.now(timezone.utc) - verified_at > timedelta(hours=24):
                return False, "MFA verification expired"

        return True, None


def create_mfa_manager(
    config: Optional[TOTPConfig] = None,
    store: Optional[MFAStore] = None,
) -> MFAManager:
    """Create an MFA manager instance."""
    return MFAManager(store=store, config=config)
