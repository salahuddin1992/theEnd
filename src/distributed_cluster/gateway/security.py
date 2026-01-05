"""
Gateway Security - أمان البوابة
================================

Security features including JWT, API keys, OAuth, and rate limiting.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ipaddress import ip_address, ip_network
from typing import Any, Callable, Dict, List, Optional, Tuple

from .gateway import GatewayRequest, GatewayResponse

logger = logging.getLogger(__name__)


@dataclass
class SecurityConfig:
    """Security configuration."""
    # JWT settings
    jwt_enabled: bool = True
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600
    jwt_refresh_enabled: bool = True

    # API Key settings
    api_key_enabled: bool = True
    api_key_header: str = "X-API-Key"
    api_key_query_param: str = "api_key"

    # OAuth settings
    oauth_enabled: bool = False
    oauth_provider_url: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""

    # IP filtering
    ip_whitelist_enabled: bool = False
    ip_whitelist: List[str] = field(default_factory=list)
    ip_blacklist: List[str] = field(default_factory=list)

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # CORS
    cors_enabled: bool = True
    cors_origins: List[str] = field(default_factory=lambda: ["*"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jwt_enabled": self.jwt_enabled,
            "api_key_enabled": self.api_key_enabled,
            "oauth_enabled": self.oauth_enabled,
            "ip_whitelist_enabled": self.ip_whitelist_enabled,
            "rate_limit_enabled": self.rate_limit_enabled,
            "cors_enabled": self.cors_enabled,
        }


class Validator(ABC):
    """Base validator interface."""

    @abstractmethod
    async def validate(self, request: GatewayRequest) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Validate request.

        Returns:
            (is_valid, claims, error_message)
        """
        pass


class JWTValidator(Validator):
    """
    JWT Token Validator.

    Validates JWT tokens in Authorization header.
    """

    def __init__(
        self,
        secret: str,
        algorithm: str = "HS256",
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
    ):
        self.secret = secret
        self.algorithm = algorithm
        self.issuer = issuer
        self.audience = audience

    async def validate(self, request: GatewayRequest) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        auth_header = request.get_header("authorization")

        if not auth_header:
            return False, None, "Missing Authorization header"

        if not auth_header.startswith("Bearer "):
            return False, None, "Invalid Authorization format"

        token = auth_header[7:]

        try:
            claims = self._decode_token(token)

            # Validate claims
            if self.issuer and claims.get("iss") != self.issuer:
                return False, None, "Invalid issuer"

            if self.audience and claims.get("aud") != self.audience:
                return False, None, "Invalid audience"

            # Check expiration
            exp = claims.get("exp")
            if exp and time.time() > exp:
                return False, None, "Token expired"

            return True, claims, None

        except Exception as e:
            return False, None, f"Token validation failed: {e}"

    def _decode_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate JWT token."""
        try:
            import jwt
            return jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={"verify_exp": True}
            )
        except ImportError:
            # Fallback: manual validation
            return self._manual_decode(token)

    def _manual_decode(self, token: str) -> Dict[str, Any]:
        """Manual JWT decode without library."""
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token format")

        # Decode header and payload
        json.loads(base64.urlsafe_b64decode(parts[0] + "=="))
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))

        # Verify signature
        message = f"{parts[0]}.{parts[1]}"
        signature = base64.urlsafe_b64decode(parts[2] + "==")

        expected = hmac.new(
            self.secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()

        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid signature")

        return payload

    def create_token(
        self,
        subject: str,
        claims: Optional[Dict[str, Any]] = None,
        expiry_seconds: int = 3600,
    ) -> str:
        """Create a JWT token."""
        now = int(time.time())
        payload = {
            "sub": subject,
            "iat": now,
            "exp": now + expiry_seconds,
            **(claims or {})
        }

        if self.issuer:
            payload["iss"] = self.issuer
        if self.audience:
            payload["aud"] = self.audience

        try:
            import jwt
            return jwt.encode(payload, self.secret, algorithm=self.algorithm)
        except ImportError:
            return self._manual_encode(payload)

    def _manual_encode(self, payload: Dict[str, Any]) -> str:
        """Manual JWT encode without library."""
        header = {"alg": self.algorithm, "typ": "JWT"}

        def b64_encode(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header_b64 = b64_encode(json.dumps(header).encode())
        payload_b64 = b64_encode(json.dumps(payload).encode())

        message = f"{header_b64}.{payload_b64}"
        signature = hmac.new(
            self.secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        signature_b64 = b64_encode(signature)

        return f"{message}.{signature_b64}"


class APIKeyValidator(Validator):
    """
    API Key Validator.

    Validates API keys from header or query parameter.
    """

    def __init__(
        self,
        api_keys: Optional[Dict[str, Dict[str, Any]]] = None,
        header_name: str = "X-API-Key",
        query_param: str = "api_key",
    ):
        self.api_keys = api_keys or {}
        self.header_name = header_name
        self.query_param = query_param

    def add_key(
        self,
        key: str,
        name: str,
        roles: Optional[List[str]] = None,
        rate_limit: Optional[int] = None,
    ) -> None:
        """Add an API key."""
        hashed = hashlib.sha256(key.encode()).hexdigest()
        self.api_keys[hashed] = {
            "name": name,
            "roles": roles or [],
            "rate_limit": rate_limit,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def revoke_key(self, key: str) -> None:
        """Revoke an API key."""
        hashed = hashlib.sha256(key.encode()).hexdigest()
        self.api_keys.pop(hashed, None)

    async def validate(self, request: GatewayRequest) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        # Check header
        api_key = request.get_header(self.header_name.lower())

        # Check query parameter
        if not api_key and request.query_string:
            params = dict(
                p.split("=") for p in request.query_string.split("&")
                if "=" in p
            )
            api_key = params.get(self.query_param)

        if not api_key:
            return False, None, "Missing API key"

        # Validate key
        hashed = hashlib.sha256(api_key.encode()).hexdigest()
        key_info = self.api_keys.get(hashed)

        if not key_info:
            return False, None, "Invalid API key"

        return True, key_info, None

    def generate_key(self) -> str:
        """Generate a new API key."""
        import secrets
        return secrets.token_urlsafe(32)


class OAuthValidator(Validator):
    """
    OAuth2 Token Validator.

    Validates OAuth2 access tokens with provider.
    """

    def __init__(
        self,
        provider_url: str,
        client_id: str,
        client_secret: str,
    ):
        self.provider_url = provider_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token_cache: Dict[str, Tuple[Dict, float]] = {}

    async def validate(self, request: GatewayRequest) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        auth_header = request.get_header("authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            return False, None, "Missing or invalid Authorization header"

        token = auth_header[7:]

        # Check cache
        if token in self._token_cache:
            info, expires = self._token_cache[token]
            if time.time() < expires:
                return True, info, None
            del self._token_cache[token]

        # Validate with provider
        try:
            import aiohttp

            introspect_url = f"{self.provider_url}/oauth/introspect"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    introspect_url,
                    data={
                        "token": token,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    }
                ) as response:
                    if response.status != 200:
                        return False, None, "Token introspection failed"

                    data = await response.json()

                    if not data.get("active"):
                        return False, None, "Token is not active"

                    # Cache token info
                    exp = data.get("exp", time.time() + 300)
                    self._token_cache[token] = (data, exp)

                    return True, data, None

        except Exception as e:
            logger.error(f"OAuth validation error: {e}")
            return False, None, str(e)


class IPWhitelist:
    """
    IP address whitelist/blacklist.
    """

    def __init__(
        self,
        whitelist: Optional[List[str]] = None,
        blacklist: Optional[List[str]] = None,
    ):
        self.whitelist = [ip_network(ip, strict=False) for ip in (whitelist or [])]
        self.blacklist = [ip_network(ip, strict=False) for ip in (blacklist or [])]

    def is_allowed(self, client_ip: str) -> bool:
        """Check if IP is allowed."""
        try:
            ip = ip_address(client_ip)

            # Check blacklist first
            for network in self.blacklist:
                if ip in network:
                    return False

            # If whitelist exists, check it
            if self.whitelist:
                for network in self.whitelist:
                    if ip in network:
                        return True
                return False

            return True

        except ValueError:
            return False


class RateLimiter:
    """
    Rate limiter with sliding window.
    """

    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        key_func: Optional[Callable[[GatewayRequest], str]] = None,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.key_func = key_func or (lambda r: r.client_ip)
        self._windows: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, request: GatewayRequest) -> Tuple[bool, int, int]:
        """
        Check rate limit.

        Returns:
            (allowed, remaining, reset_seconds)
        """
        key = self.key_func(request)
        now = time.time()
        window_start = now - self.window_seconds

        async with self._lock:
            if key not in self._windows:
                self._windows[key] = []

            # Remove old entries
            self._windows[key] = [
                t for t in self._windows[key]
                if t > window_start
            ]

            current_count = len(self._windows[key])
            remaining = max(0, self.requests_per_window - current_count - 1)

            if current_count >= self.requests_per_window:
                # Rate limited
                oldest = min(self._windows[key]) if self._windows[key] else now
                reset = int(oldest + self.window_seconds - now)
                return False, 0, reset

            # Allow request
            self._windows[key].append(now)
            reset = self.window_seconds

            return True, remaining, reset


class SecurityMiddleware:
    """
    Combined security middleware.

    Applies multiple security checks.
    """

    def __init__(self, config: SecurityConfig):
        self.config = config
        self._validators: List[Validator] = []
        self._ip_filter: Optional[IPWhitelist] = None
        self._rate_limiter: Optional[RateLimiter] = None

        self._initialize()

    def _initialize(self) -> None:
        """Initialize security components."""
        if self.config.jwt_enabled and self.config.jwt_secret:
            self._validators.append(JWTValidator(
                secret=self.config.jwt_secret,
                algorithm=self.config.jwt_algorithm,
            ))

        if self.config.api_key_enabled:
            self._validators.append(APIKeyValidator(
                header_name=self.config.api_key_header,
                query_param=self.config.api_key_query_param,
            ))

        if self.config.oauth_enabled:
            self._validators.append(OAuthValidator(
                provider_url=self.config.oauth_provider_url,
                client_id=self.config.oauth_client_id,
                client_secret=self.config.oauth_client_secret,
            ))

        if self.config.ip_whitelist_enabled:
            self._ip_filter = IPWhitelist(
                whitelist=self.config.ip_whitelist,
                blacklist=self.config.ip_blacklist,
            )

        if self.config.rate_limit_enabled:
            self._rate_limiter = RateLimiter(
                requests_per_window=self.config.rate_limit_requests,
                window_seconds=self.config.rate_limit_window_seconds,
            )

    async def validate(self, request: GatewayRequest) -> Tuple[bool, Optional[GatewayResponse]]:
        """
        Validate request.

        Returns:
            (is_valid, error_response)
        """
        # IP filtering
        if self._ip_filter:
            if not self._ip_filter.is_allowed(request.client_ip):
                return False, GatewayResponse.forbidden("IP not allowed")

        # Rate limiting
        if self._rate_limiter:
            allowed, remaining, reset = await self._rate_limiter.check(request)
            if not allowed:
                response = GatewayResponse.error(429, "Rate limit exceeded")
                response.set_header("x-ratelimit-limit", str(self.config.rate_limit_requests))
                response.set_header("x-ratelimit-remaining", str(remaining))
                response.set_header("x-ratelimit-reset", str(reset))
                response.set_header("retry-after", str(reset))
                return False, response

        # Authentication
        if self._validators:
            for validator in self._validators:
                valid, claims, error = await validator.validate(request)
                if valid:
                    request.context["auth"] = claims
                    return True, None

            return False, GatewayResponse.unauthorized("Authentication required")

        return True, None

    def add_validator(self, validator: Validator) -> None:
        """Add a custom validator."""
        self._validators.append(validator)
