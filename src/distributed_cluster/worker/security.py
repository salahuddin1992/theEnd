"""
Worker Security - أمان العامل
==============================

حماية وتأمين العامل:
- API key authentication
- Command validation
- Rate limiting
- Audit logging
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException, Request
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)


# ==================== API Key Authentication ====================


@dataclass
class APIKey:
    """مفتاح API."""

    key_id: str
    key_hash: str  # SHA-256 hash of the actual key
    name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    permissions: Set[str] = field(default_factory=lambda: {"execute"})
    rate_limit: int = 100  # requests per minute
    enabled: bool = True

    @classmethod
    def create(cls, name: str, key_value: str, **kwargs) -> "APIKey":
        """إنشاء مفتاح API جديد."""
        key_hash = hashlib.sha256(key_value.encode()).hexdigest()
        key_id = key_hash[:16]
        return cls(key_id=key_id, key_hash=key_hash, name=name, **kwargs)

    def verify(self, provided_key: str) -> bool:
        """التحقق من المفتاح."""
        provided_hash = hashlib.sha256(provided_key.encode()).hexdigest()
        return hmac.compare_digest(self.key_hash, provided_hash)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions or "*" in self.permissions


class APIKeyManager:
    """مدير مفاتيح API."""

    def __init__(self):
        self._keys: Dict[str, APIKey] = {}
        self._key_hashes: Dict[str, str] = {}  # hash -> key_id lookup

    def add_key(self, api_key: APIKey) -> None:
        """إضافة مفتاح."""
        self._keys[api_key.key_id] = api_key
        self._key_hashes[api_key.key_hash] = api_key.key_id

    def remove_key(self, key_id: str) -> bool:
        """إزالة مفتاح."""
        if key_id in self._keys:
            key = self._keys[key_id]
            del self._key_hashes[key.key_hash]
            del self._keys[key_id]
            return True
        return False

    def verify_key(self, provided_key: str) -> Optional[APIKey]:
        """التحقق من صلاحية مفتاح."""
        key_hash = hashlib.sha256(provided_key.encode()).hexdigest()
        key_id = self._key_hashes.get(key_hash)

        if not key_id:
            return None

        api_key = self._keys.get(key_id)
        if not api_key:
            return None

        if not api_key.enabled:
            return None

        if api_key.is_expired:
            return None

        return api_key

    def get_key(self, key_id: str) -> Optional[APIKey]:
        return self._keys.get(key_id)

    def list_keys(self) -> List[APIKey]:
        return list(self._keys.values())


# ==================== Command Validation ====================


@dataclass
class CommandPolicy:
    """سياسة الأوامر المسموح بها."""

    # Allowed command patterns (regex)
    allowed_patterns: List[str] = field(default_factory=list)

    # Blocked command patterns (checked first)
    blocked_patterns: List[str] = field(default_factory=lambda: [
        r"rm\s+-rf\s+/",  # Prevent recursive root deletion
        r"mkfs\.",  # Prevent filesystem formatting
        r"dd\s+if=.*of=/dev/",  # Prevent device overwrites
        r":\(\)\{:\|:&\};:",  # Fork bomb
        r"wget.*\|.*sh",  # Remote code execution
        r"curl.*\|.*sh",
        r"chmod\s+777",  # Overly permissive permissions
        r"sudo\s+su\s*$",  # Root escalation
        r"nc\s+-e",  # Netcat reverse shell
        r"python.*-c.*import\s+os.*exec",  # Python code injection
    ])

    # Allowed command prefixes
    allowed_commands: Set[str] = field(default_factory=lambda: {
        "echo", "cat", "ls", "pwd", "date", "whoami", "hostname",
        "python", "python3", "pip", "pip3",
        "node", "npm", "npx",
        "git", "docker",
        "curl", "wget",  # Without piping to shell
    })

    # Blocked commands entirely
    blocked_commands: Set[str] = field(default_factory=lambda: {
        "rm", "rmdir", "mkfs", "fdisk", "shutdown", "reboot",
        "init", "systemctl", "service",
        "passwd", "useradd", "userdel", "groupadd",
        "chown", "chmod",  # File permission changes
        "kill", "killall", "pkill",
        "iptables", "ufw",
        "mount", "umount",
    })

    # Maximum command length
    max_length: int = 10000

    # Allow shell operators
    allow_pipes: bool = True
    allow_redirects: bool = True
    allow_background: bool = False


class CommandValidator:
    """مدقق الأوامر."""

    def __init__(self, policy: Optional[CommandPolicy] = None):
        self.policy = policy or CommandPolicy()
        self._compiled_blocked = [
            re.compile(p, re.IGNORECASE) for p in self.policy.blocked_patterns
        ]
        self._compiled_allowed = [
            re.compile(p, re.IGNORECASE) for p in self.policy.allowed_patterns
        ]

    def validate(self, command: str) -> tuple[bool, str]:
        """
        التحقق من صلاحية الأمر.

        Returns:
            (is_valid, error_message)
        """
        # Check length
        if len(command) > self.policy.max_length:
            return False, f"Command too long (max {self.policy.max_length} chars)"

        # Check blocked patterns
        for pattern in self._compiled_blocked:
            if pattern.search(command):
                return False, "Command matches blocked pattern"

        # Check shell operators
        if not self.policy.allow_background and "&" in command and "&&" not in command:
            return False, "Background execution not allowed"

        if not self.policy.allow_pipes and "|" in command:
            if "||" not in command:  # Allow || for error handling
                return False, "Pipes not allowed"

        # Check command prefix
        command_parts = command.split()
        if not command_parts:
            return False, "Empty command"

        base_command = command_parts[0].split("/")[-1]  # Handle full paths

        if base_command in self.policy.blocked_commands:
            return False, f"Command '{base_command}' is blocked"

        # Check if explicitly allowed
        if self.policy.allowed_commands:
            if base_command not in self.policy.allowed_commands:
                # Check if matches allowed patterns
                if not any(p.match(command) for p in self._compiled_allowed):
                    return False, f"Command '{base_command}' not in allowed list"

        return True, ""

    def sanitize(self, command: str) -> str:
        """تنظيف الأمر (إزالة أحرف خطرة)."""
        # Remove null bytes
        command = command.replace("\x00", "")

        # Remove escape sequences
        command = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", command)

        # Limit consecutive spaces
        command = re.sub(r"\s+", " ", command)

        return command.strip()


# ==================== Rate Limiting ====================


@dataclass
class RateLimitEntry:
    """إدخال rate limiting."""

    key: str
    requests: List[float] = field(default_factory=list)
    blocked_until: Optional[float] = None


class RateLimiter:
    """محدد معدل الطلبات."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        block_duration: int = 60,  # seconds
    ):
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.block_duration = block_duration
        self._entries: Dict[str, RateLimitEntry] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> tuple[bool, int]:
        """
        التحقق من rate limit.

        Returns:
            (allowed, remaining_requests)
        """
        async with self._lock:
            now = time.time()
            entry = self._entries.get(key)

            if entry is None:
                entry = RateLimitEntry(key=key)
                self._entries[key] = entry

            # Check if blocked
            if entry.blocked_until and now < entry.blocked_until:
                return False, 0

            # Clean old requests (older than 1 minute)
            entry.requests = [t for t in entry.requests if now - t < 60]

            # Check rate limit
            if len(entry.requests) >= self.requests_per_minute:
                # Check burst
                recent = [t for t in entry.requests if now - t < 1]
                if len(recent) >= self.burst_size:
                    entry.blocked_until = now + self.block_duration
                    logger.warning(f"Rate limit exceeded for {key}, blocking for {self.block_duration}s")
                    return False, 0

            # Allow request
            entry.requests.append(now)
            remaining = self.requests_per_minute - len(entry.requests)
            return True, remaining

    async def reset(self, key: str) -> None:
        """إعادة تعيين rate limit لمفتاح."""
        async with self._lock:
            if key in self._entries:
                del self._entries[key]


# ==================== Audit Logging ====================


@dataclass
class AuditLogEntry:
    """إدخال سجل التدقيق."""

    timestamp: datetime
    event_type: str
    client_ip: str
    api_key_id: Optional[str]
    command: Optional[str]
    success: bool
    error_message: Optional[str] = None
    execution_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuditLogger:
    """مسجل التدقيق."""

    def __init__(
        self,
        log_file: Optional[str] = None,
        max_entries: int = 10000,
    ):
        self.log_file = log_file
        self.max_entries = max_entries
        self._entries: List[AuditLogEntry] = []
        self._lock = asyncio.Lock()

    async def log(
        self,
        event_type: str,
        client_ip: str,
        success: bool,
        api_key_id: Optional[str] = None,
        command: Optional[str] = None,
        error_message: Optional[str] = None,
        execution_time: Optional[float] = None,
        **metadata,
    ) -> None:
        """تسجيل حدث."""
        entry = AuditLogEntry(
            timestamp=datetime.utcnow(),
            event_type=event_type,
            client_ip=client_ip,
            api_key_id=api_key_id,
            command=self._sanitize_command(command) if command else None,
            success=success,
            error_message=error_message,
            execution_time=execution_time,
            metadata=metadata,
        )

        async with self._lock:
            self._entries.append(entry)

            # Trim old entries
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries:]

            # Write to file
            if self.log_file:
                await self._write_to_file(entry)

        # Also log to standard logger
        log_msg = f"[AUDIT] {event_type} from {client_ip}"
        if api_key_id:
            log_msg += f" (key: {api_key_id[:8]}...)"
        if command:
            log_msg += f" cmd: {command[:50]}..."
        if not success:
            log_msg += f" FAILED: {error_message}"

        if success:
            logger.info(log_msg)
        else:
            logger.warning(log_msg)

    def _sanitize_command(self, command: str) -> str:
        """تنظيف الأمر للتسجيل (إخفاء البيانات الحساسة)."""
        # Hide potential passwords and tokens
        patterns = [
            (r"(password[=:]\s*)(\S+)", r"\1***"),
            (r"(token[=:]\s*)(\S+)", r"\1***"),
            (r"(secret[=:]\s*)(\S+)", r"\1***"),
            (r"(api[_-]?key[=:]\s*)(\S+)", r"\1***"),
        ]

        result = command
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        return result

    async def _write_to_file(self, entry: AuditLogEntry) -> None:
        """كتابة إلى ملف."""
        import json
        import aiofiles

        try:
            async with aiofiles.open(self.log_file, "a") as f:
                line = json.dumps({
                    "timestamp": entry.timestamp.isoformat(),
                    "event_type": entry.event_type,
                    "client_ip": entry.client_ip,
                    "api_key_id": entry.api_key_id,
                    "command": entry.command,
                    "success": entry.success,
                    "error_message": entry.error_message,
                    "execution_time": entry.execution_time,
                    **entry.metadata,
                })
                await f.write(line + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    def get_entries(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_type: Optional[str] = None,
        client_ip: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> List[AuditLogEntry]:
        """الحصول على إدخالات السجل."""
        entries = self._entries

        if start_time:
            entries = [e for e in entries if e.timestamp >= start_time]
        if end_time:
            entries = [e for e in entries if e.timestamp <= end_time]
        if event_type:
            entries = [e for e in entries if e.event_type == event_type]
        if client_ip:
            entries = [e for e in entries if e.client_ip == client_ip]
        if success is not None:
            entries = [e for e in entries if e.success == success]

        return entries


# ==================== Security Middleware for FastAPI ====================


class SecurityMiddleware:
    """
    Middleware للأمان في FastAPI.

    الاستخدام:
        security = SecurityMiddleware()
        security.add_api_key("my-key", "secret-value")

        @app.post("/execute")
        async def execute(request: Request):
            await security.authenticate(request)
            await security.validate_command(command)
            # ...
    """

    def __init__(
        self,
        rate_limit: int = 60,
        audit_log_file: Optional[str] = None,
    ):
        self.key_manager = APIKeyManager()
        self.command_validator = CommandValidator()
        self.rate_limiter = RateLimiter(requests_per_minute=rate_limit)
        self.audit_logger = AuditLogger(log_file=audit_log_file)

        self._api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def add_api_key(
        self,
        name: str,
        key_value: str,
        permissions: Optional[Set[str]] = None,
        rate_limit: int = 100,
    ) -> APIKey:
        """إضافة مفتاح API."""
        api_key = APIKey.create(
            name=name,
            key_value=key_value,
            permissions=permissions or {"execute"},
            rate_limit=rate_limit,
        )
        self.key_manager.add_key(api_key)
        return api_key

    async def authenticate(self, request: Request) -> APIKey:
        """المصادقة على الطلب."""
        client_ip = request.client.host if request.client else "unknown"

        # Get API key from header
        api_key_value = request.headers.get("X-API-Key")

        if not api_key_value:
            await self.audit_logger.log(
                event_type="auth_failed",
                client_ip=client_ip,
                success=False,
                error_message="Missing API key",
            )
            raise HTTPException(status_code=401, detail="Missing API key")

        # Verify key
        api_key = self.key_manager.verify_key(api_key_value)

        if not api_key:
            await self.audit_logger.log(
                event_type="auth_failed",
                client_ip=client_ip,
                success=False,
                error_message="Invalid API key",
            )
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Check rate limit
        allowed, remaining = await self.rate_limiter.check(api_key.key_id)
        if not allowed:
            await self.audit_logger.log(
                event_type="rate_limited",
                client_ip=client_ip,
                api_key_id=api_key.key_id,
                success=False,
                error_message="Rate limit exceeded",
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": "60"},
            )

        await self.audit_logger.log(
            event_type="auth_success",
            client_ip=client_ip,
            api_key_id=api_key.key_id,
            success=True,
        )

        return api_key

    async def validate_command(
        self,
        command: str,
        request: Request,
        api_key: APIKey,
    ) -> str:
        """التحقق من صلاحية الأمر."""
        client_ip = request.client.host if request.client else "unknown"

        # Sanitize first
        command = self.command_validator.sanitize(command)

        # Validate
        is_valid, error = self.command_validator.validate(command)

        if not is_valid:
            await self.audit_logger.log(
                event_type="command_rejected",
                client_ip=client_ip,
                api_key_id=api_key.key_id,
                command=command,
                success=False,
                error_message=error,
            )
            raise HTTPException(status_code=400, detail=f"Invalid command: {error}")

        # Check permission
        if not api_key.has_permission("execute"):
            await self.audit_logger.log(
                event_type="permission_denied",
                client_ip=client_ip,
                api_key_id=api_key.key_id,
                command=command,
                success=False,
                error_message="Missing execute permission",
            )
            raise HTTPException(status_code=403, detail="Permission denied")

        return command

    async def log_execution(
        self,
        request: Request,
        api_key: APIKey,
        command: str,
        success: bool,
        execution_time: float,
        error_message: Optional[str] = None,
    ) -> None:
        """تسجيل تنفيذ الأمر."""
        client_ip = request.client.host if request.client else "unknown"

        await self.audit_logger.log(
            event_type="command_executed",
            client_ip=client_ip,
            api_key_id=api_key.key_id,
            command=command,
            success=success,
            execution_time=execution_time,
            error_message=error_message,
        )
