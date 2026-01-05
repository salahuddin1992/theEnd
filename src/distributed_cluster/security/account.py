"""
Account Security & Password Policies - أمان الحساب وسياسات كلمات المرور
==========================================================================

Comprehensive account security with password policies and protection.
أمان شامل للحساب مع سياسات كلمات المرور والحماية.

Features:
- Strong password requirements
- Password history
- Account lockout
- Password expiration
- Secure password storage
- Password breach checking
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PasswordStrength(str, Enum):
    """Password strength levels."""

    VERY_WEAK = "very_weak"
    WEAK = "weak"
    FAIR = "fair"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class AccountStatus(str, Enum):
    """Account status."""

    ACTIVE = "active"
    LOCKED = "locked"
    SUSPENDED = "suspended"
    PASSWORD_EXPIRED = "password_expired"
    PENDING_VERIFICATION = "pending_verification"
    DISABLED = "disabled"


@dataclass
class PasswordPolicy:
    """Password policy configuration."""

    # Length requirements
    min_length: int = 12
    max_length: int = 128

    # Character requirements
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digits: bool = True
    require_special: bool = True
    min_unique_chars: int = 8

    # Special characters allowed
    special_chars: str = "!@#$%^&*()_+-=[]{}|;':\",./<>?"

    # Password history
    history_size: int = 12  # Number of previous passwords to remember
    min_password_age_hours: int = 1  # Min time before can change again

    # Expiration
    max_password_age_days: int = 90
    warn_before_expiry_days: int = 14

    # Complexity
    min_strength: PasswordStrength = PasswordStrength.STRONG

    # Forbidden patterns
    forbid_username: bool = True
    forbid_email_parts: bool = True
    forbid_common_words: bool = True
    forbid_sequences: bool = True  # 123, abc, etc.
    forbid_repeated_chars: int = 3  # Max consecutive same chars

    # Breach checking
    check_breached_passwords: bool = False  # Requires external service


@dataclass
class PasswordValidationResult:
    """Result of password validation."""

    valid: bool
    strength: PasswordStrength
    score: int  # 0-100
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "strength": self.strength.value,
            "score": self.score,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
        }


@dataclass
class PasswordHash:
    """Stored password hash."""

    hash: str
    salt: str
    algorithm: str = "pbkdf2_sha256"
    iterations: int = 310000
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_storage_format(self) -> str:
        """Convert to storage string format."""
        return f"{self.algorithm}${self.iterations}${self.salt}${self.hash}"

    @classmethod
    def from_storage_format(cls, stored: str) -> PasswordHash:
        """Parse from storage string format."""
        parts = stored.split("$")
        if len(parts) != 4:
            raise ValueError("Invalid password hash format")

        return cls(
            algorithm=parts[0],
            iterations=int(parts[1]),
            salt=parts[2],
            hash=parts[3],
        )


@dataclass
class AccountSecurityInfo:
    """Account security information."""

    user_id: str
    status: AccountStatus = AccountStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Password info
    password_hash: Optional[PasswordHash] = None
    password_changed_at: Optional[datetime] = None
    password_expires_at: Optional[datetime] = None
    password_history: List[str] = field(default_factory=list)  # Hash storage formats
    must_change_password: bool = False

    # Lockout info
    failed_login_count: int = 0
    last_failed_login: Optional[datetime] = None
    locked_until: Optional[datetime] = None
    lockout_count: int = 0

    # Security metadata
    last_login: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    security_questions_set: bool = False
    mfa_enabled: bool = False

    @property
    def is_locked(self) -> bool:
        if self.status == AccountStatus.LOCKED:
            if self.locked_until and datetime.now(timezone.utc) > self.locked_until:
                return False
            return True
        return False

    @property
    def is_password_expired(self) -> bool:
        if self.password_expires_at:
            return datetime.now(timezone.utc) > self.password_expires_at
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "status": self.status.value,
            "is_locked": self.is_locked,
            "is_password_expired": self.is_password_expired,
            "password_changed_at": self.password_changed_at.isoformat() if self.password_changed_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "failed_login_count": self.failed_login_count,
            "mfa_enabled": self.mfa_enabled,
        }


class PasswordHasher:
    """Secure password hashing."""

    def __init__(
        self,
        algorithm: str = "pbkdf2_sha256",
        iterations: int = 310000,
        salt_length: int = 16,
    ):
        self.algorithm = algorithm
        self.iterations = iterations
        self.salt_length = salt_length

    def hash(self, password: str) -> PasswordHash:
        """Hash a password."""
        salt = os.urandom(self.salt_length)
        salt_b64 = base64.b64encode(salt).decode("ascii")

        if self.algorithm == "pbkdf2_sha256":
            key = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                self.iterations,
            )
        elif self.algorithm == "pbkdf2_sha512":
            key = hashlib.pbkdf2_hmac(
                "sha512",
                password.encode("utf-8"),
                salt,
                self.iterations,
            )
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")

        hash_b64 = base64.b64encode(key).decode("ascii")

        return PasswordHash(
            hash=hash_b64,
            salt=salt_b64,
            algorithm=self.algorithm,
            iterations=self.iterations,
        )

    def verify(self, password: str, stored_hash: PasswordHash) -> bool:
        """Verify a password against stored hash."""
        salt = base64.b64decode(stored_hash.salt)

        if stored_hash.algorithm == "pbkdf2_sha256":
            key = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                stored_hash.iterations,
            )
        elif stored_hash.algorithm == "pbkdf2_sha512":
            key = hashlib.pbkdf2_hmac(
                "sha512",
                password.encode("utf-8"),
                salt,
                stored_hash.iterations,
            )
        else:
            return False

        computed_hash = base64.b64encode(key).decode("ascii")
        return hmac.compare_digest(computed_hash, stored_hash.hash)

    def needs_rehash(self, stored_hash: PasswordHash) -> bool:
        """Check if password needs to be rehashed (algorithm/iterations changed)."""
        return stored_hash.algorithm != self.algorithm or stored_hash.iterations < self.iterations


class PasswordValidator:
    """Validates passwords against policy."""

    # Common weak passwords to check against
    COMMON_PASSWORDS = {
        "password",
        "123456",
        "12345678",
        "qwerty",
        "abc123",
        "monkey",
        "master",
        "dragon",
        "111111",
        "baseball",
        "iloveyou",
        "trustno1",
        "sunshine",
        "princess",
        "welcome",
        "password1",
        "password123",
        "admin",
        "letmein",
        "login",
    }

    KEYBOARD_SEQUENCES = [
        "qwerty",
        "asdfgh",
        "zxcvbn",
        "qwertyuiop",
        "asdfghjkl",
        "zxcvbnm",
        "1234567890",
    ]

    def __init__(self, policy: Optional[PasswordPolicy] = None):
        self.policy = policy or PasswordPolicy()

    def validate(
        self,
        password: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        previous_hashes: Optional[List[str]] = None,
        hasher: Optional[PasswordHasher] = None,
    ) -> PasswordValidationResult:
        """Validate a password against the policy."""
        errors = []
        warnings = []
        suggestions = []
        score = 0

        # Length checks
        if len(password) < self.policy.min_length:
            errors.append(f"Password must be at least {self.policy.min_length} characters")
        elif len(password) >= self.policy.min_length:
            score += 20

        if len(password) > self.policy.max_length:
            errors.append(f"Password must be at most {self.policy.max_length} characters")

        # Character type checks
        has_upper = bool(re.search(r"[A-Z]", password))
        has_lower = bool(re.search(r"[a-z]", password))
        has_digit = bool(re.search(r"\d", password))
        has_special = bool(re.search(r"[" + re.escape(self.policy.special_chars) + r"]", password))

        if self.policy.require_uppercase and not has_upper:
            errors.append("Password must contain uppercase letters")
        elif has_upper:
            score += 10

        if self.policy.require_lowercase and not has_lower:
            errors.append("Password must contain lowercase letters")
        elif has_lower:
            score += 10

        if self.policy.require_digits and not has_digit:
            errors.append("Password must contain numbers")
        elif has_digit:
            score += 10

        if self.policy.require_special and not has_special:
            errors.append(f"Password must contain special characters ({self.policy.special_chars})")
        elif has_special:
            score += 15

        # Unique characters
        unique_chars = len(set(password))
        if unique_chars < self.policy.min_unique_chars:
            errors.append(f"Password must contain at least {self.policy.min_unique_chars} unique characters")
        else:
            score += min(15, unique_chars)

        # Username/email checks
        if self.policy.forbid_username and username:
            if username.lower() in password.lower():
                errors.append("Password cannot contain username")

        if self.policy.forbid_email_parts and email:
            email_parts = email.lower().replace("@", " ").replace(".", " ").split()
            for part in email_parts:
                if len(part) > 3 and part in password.lower():
                    errors.append("Password cannot contain parts of email address")
                    break

        # Common words check
        if self.policy.forbid_common_words:
            password_lower = password.lower()
            for common in self.COMMON_PASSWORDS:
                if common in password_lower:
                    errors.append("Password contains a common weak pattern")
                    break

        # Sequence check
        if self.policy.forbid_sequences:
            password_lower = password.lower()
            for seq in self.KEYBOARD_SEQUENCES:
                if seq in password_lower or seq[::-1] in password_lower:
                    warnings.append("Password contains a keyboard sequence")
                    score -= 10
                    break

            # Numeric sequences
            for i in range(len(password) - 2):
                if password[i : i + 3].isdigit():
                    chars = [int(c) for c in password[i : i + 3]]
                    if chars[1] - chars[0] == chars[2] - chars[1] == 1:
                        warnings.append("Password contains a numeric sequence")
                        score -= 5
                        break

        # Repeated characters
        if self.policy.forbid_repeated_chars:
            for i in range(len(password) - self.policy.forbid_repeated_chars + 1):
                if len(set(password[i : i + self.policy.forbid_repeated_chars])) == 1:
                    errors.append(
                        f"Password cannot have {self.policy.forbid_repeated_chars}+ "
                        f"consecutive identical characters"
                    )
                    break

        # Password history check
        if previous_hashes and hasher:
            for stored_format in previous_hashes:
                try:
                    stored_hash = PasswordHash.from_storage_format(stored_format)
                    if hasher.verify(password, stored_hash):
                        errors.append("Password was used recently. Choose a different password.")
                        break
                except Exception:
                    pass

        # Calculate strength
        score = max(0, min(100, score))
        if score >= 80:
            strength = PasswordStrength.VERY_STRONG
        elif score >= 60:
            strength = PasswordStrength.STRONG
        elif score >= 40:
            strength = PasswordStrength.FAIR
        elif score >= 20:
            strength = PasswordStrength.WEAK
        else:
            strength = PasswordStrength.VERY_WEAK

        # Check minimum strength
        strength_order = [
            PasswordStrength.VERY_WEAK,
            PasswordStrength.WEAK,
            PasswordStrength.FAIR,
            PasswordStrength.STRONG,
            PasswordStrength.VERY_STRONG,
        ]
        if strength_order.index(strength) < strength_order.index(self.policy.min_strength):
            errors.append(f"Password is too weak. Minimum required: {self.policy.min_strength.value}")

        # Generate suggestions
        if not has_upper:
            suggestions.append("Add uppercase letters")
        if not has_special:
            suggestions.append("Add special characters")
        if len(password) < 16:
            suggestions.append("Use a longer password (16+ characters recommended)")
        if unique_chars < 10:
            suggestions.append("Use more unique characters")

        return PasswordValidationResult(
            valid=len(errors) == 0,
            strength=strength,
            score=score,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
        )


class AccountStore(ABC):
    """Abstract account store."""

    @abstractmethod
    def get(self, user_id: str) -> Optional[AccountSecurityInfo]:
        pass

    @abstractmethod
    def save(self, account: AccountSecurityInfo) -> bool:
        pass

    @abstractmethod
    def delete(self, user_id: str) -> bool:
        pass


class MemoryAccountStore(AccountStore):
    """In-memory account store."""

    def __init__(self):
        self._accounts: Dict[str, AccountSecurityInfo] = {}
        self._lock = threading.RLock()

    def get(self, user_id: str) -> Optional[AccountSecurityInfo]:
        with self._lock:
            return self._accounts.get(user_id)

    def save(self, account: AccountSecurityInfo) -> bool:
        with self._lock:
            self._accounts[account.user_id] = account
            return True

    def delete(self, user_id: str) -> bool:
        with self._lock:
            if user_id in self._accounts:
                del self._accounts[user_id]
                return True
            return False


class AccountSecurityManager:
    """
    Account Security Manager.

    Manages password security, lockouts, and account protection.
    """

    def __init__(
        self,
        store: Optional[AccountStore] = None,
        policy: Optional[PasswordPolicy] = None,
        hasher: Optional[PasswordHasher] = None,
    ):
        self.store = store or MemoryAccountStore()
        self.policy = policy or PasswordPolicy()
        self.hasher = hasher or PasswordHasher()
        self.validator = PasswordValidator(self.policy)

        # Lockout settings
        self.max_failed_attempts = 5
        self.lockout_duration_minutes = 15
        self.progressive_lockout = True  # Increase lockout duration after repeated lockouts

        self._lock = threading.RLock()

    def create_account(
        self,
        user_id: str,
        password: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Tuple[bool, PasswordValidationResult]:
        """
        Create a new account with password.

        Returns:
            (success, validation_result)
        """
        # Validate password
        validation = self.validator.validate(
            password,
            username=username,
            email=email,
        )

        if not validation.valid:
            return False, validation

        # Hash password
        password_hash = self.hasher.hash(password)

        # Calculate expiration
        password_expires_at = None
        if self.policy.max_password_age_days > 0:
            password_expires_at = datetime.now(timezone.utc) + timedelta(days=self.policy.max_password_age_days)

        # Create account
        account = AccountSecurityInfo(
            user_id=user_id,
            password_hash=password_hash,
            password_changed_at=datetime.now(timezone.utc),
            password_expires_at=password_expires_at,
            password_history=[password_hash.to_storage_format()],
        )

        self.store.save(account)
        logger.info(f"Created account for user {user_id}")

        return True, validation

    def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        force: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[PasswordValidationResult]]:
        """
        Change user password.

        Returns:
            (success, error_message, validation_result)
        """
        account = self.store.get(user_id)
        if not account:
            return False, "Account not found", None

        # Verify current password (unless forced)
        if not force:
            if not account.password_hash:
                return False, "No password set", None

            if not self.hasher.verify(current_password, account.password_hash):
                return False, "Current password is incorrect", None

        # Check minimum password age
        if not force and account.password_changed_at:
            min_age = timedelta(hours=self.policy.min_password_age_hours)
            if datetime.now(timezone.utc) - account.password_changed_at < min_age:
                error_msg = (
                    f"Cannot change password within {self.policy.min_password_age_hours} " f"hours of last change"
                )
                return False, error_msg, None

        # Validate new password
        validation = self.validator.validate(
            new_password,
            username=username,
            email=email,
            previous_hashes=account.password_history,
            hasher=self.hasher,
        )

        if not validation.valid:
            return False, "Password does not meet requirements", validation

        # Hash new password
        new_hash = self.hasher.hash(new_password)

        # Update password history
        account.password_history.append(new_hash.to_storage_format())
        if len(account.password_history) > self.policy.history_size:
            account.password_history = account.password_history[-self.policy.history_size :]

        # Update account
        account.password_hash = new_hash
        account.password_changed_at = datetime.now(timezone.utc)
        account.must_change_password = False

        if self.policy.max_password_age_days > 0:
            account.password_expires_at = datetime.now(timezone.utc) + timedelta(days=self.policy.max_password_age_days)

        # Clear lockout on password change
        account.failed_login_count = 0
        account.locked_until = None
        if account.status == AccountStatus.LOCKED:
            account.status = AccountStatus.ACTIVE

        self.store.save(account)
        logger.info(f"Password changed for user {user_id}")

        return True, None, validation

    def verify_password(
        self,
        user_id: str,
        password: str,
        ip_address: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[AccountSecurityInfo]]:
        """
        Verify a password for login.

        Returns:
            (success, error_message, account_info)
        """
        account = self.store.get(user_id)
        if not account:
            return False, "Invalid credentials", None

        # Check account status
        if account.status == AccountStatus.DISABLED:
            return False, "Account is disabled", None

        if account.status == AccountStatus.SUSPENDED:
            return False, "Account is suspended", None

        # Check lockout
        if account.is_locked:
            remaining = None
            if account.locked_until:
                remaining = int((account.locked_until - datetime.now(timezone.utc)).total_seconds())
            return False, f"Account is locked. Try again in {remaining} seconds", None

        # Clear expired lockout
        if account.status == AccountStatus.LOCKED and not account.is_locked:
            account.status = AccountStatus.ACTIVE

        # Verify password
        if not account.password_hash:
            return False, "No password set", None

        if not self.hasher.verify(password, account.password_hash):
            # Record failed attempt
            account.failed_login_count += 1
            account.last_failed_login = datetime.now(timezone.utc)

            # Check for lockout
            if account.failed_login_count >= self.max_failed_attempts:
                lockout_minutes = self.lockout_duration_minutes
                if self.progressive_lockout:
                    lockout_minutes *= account.lockout_count + 1

                account.locked_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)
                account.status = AccountStatus.LOCKED
                account.lockout_count += 1

                self.store.save(account)
                error_msg = (
                    f"Account locked due to too many failed attempts. " f"Try again in {lockout_minutes} minutes"
                )
                return False, error_msg, None

            self.store.save(account)
            remaining = self.max_failed_attempts - account.failed_login_count
            return False, f"Invalid credentials. {remaining} attempts remaining", None

        # Successful login - check for password expiration
        if account.is_password_expired:
            account.status = AccountStatus.PASSWORD_EXPIRED
            self.store.save(account)
            return False, "Password has expired. Please change your password", account

        # Clear failed attempts
        account.failed_login_count = 0
        account.last_failed_login = None
        account.last_login = datetime.now(timezone.utc)
        account.last_login_ip = ip_address

        self.store.save(account)
        return True, None, account

    def require_password_change(self, user_id: str) -> bool:
        """Require user to change password on next login."""
        account = self.store.get(user_id)
        if not account:
            return False

        account.must_change_password = True
        self.store.save(account)
        return True

    def unlock_account(self, user_id: str) -> bool:
        """Manually unlock an account."""
        account = self.store.get(user_id)
        if not account:
            return False

        account.status = AccountStatus.ACTIVE
        account.locked_until = None
        account.failed_login_count = 0
        self.store.save(account)

        logger.info(f"Account unlocked for user {user_id}")
        return True

    def disable_account(self, user_id: str, reason: str = "") -> bool:
        """Disable an account."""
        account = self.store.get(user_id)
        if not account:
            return False

        account.status = AccountStatus.DISABLED
        self.store.save(account)

        logger.info(f"Account disabled for user {user_id}: {reason}")
        return True

    def get_account_status(self, user_id: str) -> Optional[AccountSecurityInfo]:
        """Get account security status."""
        return self.store.get(user_id)

    def check_password_expiry(self, user_id: str) -> Tuple[bool, Optional[int]]:
        """
        Check if password is expiring soon.

        Returns:
            (is_expiring_soon, days_until_expiry)
        """
        account = self.store.get(user_id)
        if not account or not account.password_expires_at:
            return False, None

        days_until_expiry = (account.password_expires_at - datetime.now(timezone.utc)).days

        if days_until_expiry <= self.policy.warn_before_expiry_days:
            return True, days_until_expiry

        return False, days_until_expiry

    def generate_secure_password(self, length: int = 16) -> str:
        """Generate a secure random password."""
        import string

        # Ensure we have at least one of each required character type
        chars = []
        chars.append(secrets.choice(string.ascii_uppercase))
        chars.append(secrets.choice(string.ascii_lowercase))
        chars.append(secrets.choice(string.digits))
        chars.append(secrets.choice(self.policy.special_chars))

        # Fill remaining length
        all_chars = string.ascii_letters + string.digits + self.policy.special_chars
        chars.extend(secrets.choice(all_chars) for _ in range(length - 4))

        # Shuffle
        result = list(chars)
        for i in range(len(result) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            result[i], result[j] = result[j], result[i]

        return "".join(result)


def create_account_security_manager(
    policy: Optional[PasswordPolicy] = None,
    store: Optional[AccountStore] = None,
) -> AccountSecurityManager:
    """Create an account security manager instance."""
    return AccountSecurityManager(store=store, policy=policy)
