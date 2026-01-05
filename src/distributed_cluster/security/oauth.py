"""
OAuth2 and OIDC authentication implementation.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class OAuth2Error(Exception):
    """Base OAuth2 error."""

    def __init__(self, error: str, description: str = "", status_code: int = 400):
        self.error = error
        self.description = description
        self.status_code = status_code
        super().__init__(f"{error}: {description}")


class GrantType(Enum):
    """OAuth2 grant types."""
    AUTHORIZATION_CODE = "authorization_code"
    CLIENT_CREDENTIALS = "client_credentials"
    REFRESH_TOKEN = "refresh_token"
    PASSWORD = "password"
    DEVICE_CODE = "device_code"
    IMPLICIT = "implicit"


class TokenType(Enum):
    """Token types."""
    BEARER = "Bearer"
    MAC = "mac"


@dataclass
class OAuth2Config:
    """OAuth2 configuration."""
    client_id: str
    client_secret: Optional[str] = None
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    userinfo_endpoint: str = ""
    revocation_endpoint: str = ""
    jwks_uri: str = ""
    issuer: str = ""
    redirect_uri: str = ""
    scopes: List[str] = field(default_factory=lambda: ["openid", "profile", "email"])
    response_type: str = "code"
    grant_type: GrantType = GrantType.AUTHORIZATION_CODE
    pkce_enabled: bool = True
    state_ttl_seconds: int = 600

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "scopes": self.scopes,
            "pkce_enabled": self.pkce_enabled,
        }


@dataclass
class TokenInfo:
    """OAuth2 token information."""
    access_token: str
    token_type: TokenType = TokenType.BEARER
    expires_in: int = 3600
    refresh_token: Optional[str] = None
    scope: str = ""
    id_token: Optional[str] = None
    issued_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(seconds=self.expires_in)

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type.value,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "id_token": self.id_token,
        }


class JWTHandler:
    """JWT token handler."""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self._public_keys: Dict[str, str] = {}  # kid -> public_key

    def encode(self, payload: Dict[str, Any], expires_in: int = 3600) -> str:
        """Encode a JWT token."""
        header = {
            "alg": self.algorithm,
            "typ": "JWT"
        }

        now = int(time.time())
        payload = {
            **payload,
            "iat": now,
            "exp": now + expires_in,
        }

        header_b64 = self._base64url_encode(json.dumps(header))
        payload_b64 = self._base64url_encode(json.dumps(payload))

        message = f"{header_b64}.{payload_b64}"
        signature = self._sign(message)
        signature_b64 = self._base64url_encode(signature)

        return f"{message}.{signature_b64}"

    def decode(self, token: str, verify: bool = True) -> Dict[str, Any]:
        """Decode and verify a JWT token."""
        parts = token.split(".")
        if len(parts) != 3:
            raise OAuth2Error("invalid_token", "Invalid JWT format")

        header_b64, payload_b64, signature_b64 = parts

        try:
            json.loads(self._base64url_decode(header_b64))
            payload = json.loads(self._base64url_decode(payload_b64))
        except (json.JSONDecodeError, ValueError) as e:
            raise OAuth2Error("invalid_token", f"Failed to decode token: {e}")

        if verify:
            # Verify signature
            message = f"{header_b64}.{payload_b64}"
            expected_signature = self._sign(message)
            actual_signature = self._base64url_decode(signature_b64)

            if not hmac.compare_digest(expected_signature, actual_signature):
                raise OAuth2Error("invalid_token", "Invalid signature")

            # Verify expiration
            exp = payload.get("exp")
            if exp and int(time.time()) >= exp:
                raise OAuth2Error("invalid_token", "Token expired")

        return payload

    def _sign(self, message: str) -> bytes:
        """Sign a message."""
        if self.algorithm == "HS256":
            return hmac.new(
                self.secret_key.encode(),
                message.encode(),
                hashlib.sha256
            ).digest()
        else:
            raise OAuth2Error("unsupported_algorithm", f"Algorithm {self.algorithm} not supported")

    def _base64url_encode(self, data: str) -> str:
        """Base64url encode."""
        if isinstance(data, str):
            data = data.encode()
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    def _base64url_decode(self, data: str) -> bytes:
        """Base64url decode."""
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)


class TokenManager:
    """Manages OAuth2 tokens."""

    def __init__(self, jwt_handler: Optional[JWTHandler] = None):
        self.jwt_handler = jwt_handler or JWTHandler(secrets.token_hex(32))
        self._tokens: Dict[str, TokenInfo] = {}
        self._refresh_tokens: Dict[str, str] = {}  # refresh_token -> access_token
        self._lock = threading.RLock()

    def create_token(
        self,
        user_id: str,
        scopes: List[str],
        client_id: str,
        expires_in: int = 3600,
        include_refresh: bool = True
    ) -> TokenInfo:
        """Create a new access token."""
        payload = {
            "sub": user_id,
            "client_id": client_id,
            "scope": " ".join(scopes),
            "jti": secrets.token_hex(16),
        }

        access_token = self.jwt_handler.encode(payload, expires_in)

        refresh_token = None
        if include_refresh:
            refresh_token = secrets.token_urlsafe(32)

        token_info = TokenInfo(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token,
            scope=" ".join(scopes),
        )

        with self._lock:
            self._tokens[access_token] = token_info
            if refresh_token:
                self._refresh_tokens[refresh_token] = access_token

        return token_info

    def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate an access token."""
        try:
            payload = self.jwt_handler.decode(token)
            return payload
        except OAuth2Error:
            raise
        except Exception as e:
            raise OAuth2Error("invalid_token", str(e))

    def refresh_access_token(self, refresh_token: str) -> TokenInfo:
        """Refresh an access token."""
        with self._lock:
            if refresh_token not in self._refresh_tokens:
                raise OAuth2Error("invalid_grant", "Invalid refresh token")

            old_access_token = self._refresh_tokens[refresh_token]
            old_token_info = self._tokens.get(old_access_token)

            if not old_token_info:
                raise OAuth2Error("invalid_grant", "Token not found")

            # Get user info from old token
            old_payload = self.jwt_handler.decode(old_access_token, verify=False)

            # Create new token
            new_token = self.create_token(
                user_id=old_payload["sub"],
                scopes=old_payload.get("scope", "").split(),
                client_id=old_payload.get("client_id", ""),
                expires_in=old_token_info.expires_in,
                include_refresh=True
            )

            # Revoke old tokens
            del self._tokens[old_access_token]
            del self._refresh_tokens[refresh_token]

            return new_token

    def revoke_token(self, token: str, token_type_hint: str = "access_token") -> bool:
        """Revoke a token."""
        with self._lock:
            if token_type_hint == "refresh_token":
                if token in self._refresh_tokens:
                    access_token = self._refresh_tokens.pop(token)
                    self._tokens.pop(access_token, None)
                    return True
            else:
                if token in self._tokens:
                    token_info = self._tokens.pop(token)
                    if token_info.refresh_token:
                        self._refresh_tokens.pop(token_info.refresh_token, None)
                    return True
            return False


class OAuth2Client:
    """OAuth2 client for authentication flows."""

    def __init__(self, config: OAuth2Config):
        self.config = config
        self._states: Dict[str, tuple] = {}  # state -> (code_verifier, timestamp)
        self._lock = threading.Lock()

    def get_authorization_url(self, extra_params: Optional[Dict[str, str]] = None) -> tuple:
        """Generate authorization URL for OAuth2 flow."""
        state = secrets.token_urlsafe(32)

        params = {
            "client_id": self.config.client_id,
            "response_type": self.config.response_type,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
        }

        code_verifier = None
        if self.config.pkce_enabled:
            code_verifier = secrets.token_urlsafe(64)
            code_challenge = self._generate_code_challenge(code_verifier)
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        if extra_params:
            params.update(extra_params)

        with self._lock:
            self._states[state] = (code_verifier, time.time())

        url = f"{self.config.authorization_endpoint}?{urlencode(params)}"
        return url, state

    def _generate_code_challenge(self, code_verifier: str) -> str:
        """Generate PKCE code challenge."""
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def validate_state(self, state: str) -> Optional[str]:
        """Validate state and return code verifier."""
        with self._lock:
            if state not in self._states:
                return None

            code_verifier, timestamp = self._states.pop(state)

            if time.time() - timestamp > self.config.state_ttl_seconds:
                return None

            return code_verifier

    async def exchange_code(
        self,
        code: str,
        state: str,
        http_client: Any
    ) -> TokenInfo:
        """Exchange authorization code for tokens."""
        code_verifier = self.validate_state(state)
        if code_verifier is None and self.config.pkce_enabled:
            raise OAuth2Error("invalid_state", "Invalid or expired state")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
        }

        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret

        if code_verifier:
            data["code_verifier"] = code_verifier

        try:
            response = await http_client.post(
                self.config.token_endpoint,
                data=data
            )
            token_data = response.json()

            if "error" in token_data:
                raise OAuth2Error(
                    token_data["error"],
                    token_data.get("error_description", "")
                )

            return TokenInfo(
                access_token=token_data["access_token"],
                token_type=TokenType(token_data.get("token_type", "Bearer")),
                expires_in=token_data.get("expires_in", 3600),
                refresh_token=token_data.get("refresh_token"),
                scope=token_data.get("scope", ""),
                id_token=token_data.get("id_token"),
            )
        except Exception as e:
            if isinstance(e, OAuth2Error):
                raise
            raise OAuth2Error("token_exchange_failed", str(e))


class OIDCProvider:
    """OpenID Connect provider for user authentication."""

    def __init__(
        self,
        issuer: str,
        jwt_handler: JWTHandler,
        token_manager: TokenManager
    ):
        self.issuer = issuer
        self.jwt_handler = jwt_handler
        self.token_manager = token_manager
        self._clients: Dict[str, Dict] = {}  # client_id -> client_config
        self._users: Dict[str, Dict] = {}  # user_id -> user_info
        self._authorization_codes: Dict[str, Dict] = {}  # code -> code_info
        self._lock = threading.RLock()

    def register_client(
        self,
        client_id: str,
        client_secret: str,
        redirect_uris: List[str],
        grant_types: List[str] = None,
        scopes: List[str] = None
    ):
        """Register an OAuth2 client."""
        with self._lock:
            self._clients[client_id] = {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": redirect_uris,
                "grant_types": grant_types or ["authorization_code"],
                "scopes": scopes or ["openid", "profile", "email"],
            }

    def register_user(self, user_id: str, user_info: Dict[str, Any]):
        """Register a user."""
        with self._lock:
            self._users[user_id] = user_info

    def create_authorization_code(
        self,
        client_id: str,
        user_id: str,
        redirect_uri: str,
        scopes: List[str],
        code_challenge: Optional[str] = None,
        code_challenge_method: str = "S256"
    ) -> str:
        """Create an authorization code."""
        code = secrets.token_urlsafe(32)

        with self._lock:
            self._authorization_codes[code] = {
                "client_id": client_id,
                "user_id": user_id,
                "redirect_uri": redirect_uri,
                "scopes": scopes,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "created_at": time.time(),
            }

        return code

    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: Optional[str] = None
    ) -> TokenInfo:
        """Exchange authorization code for tokens."""
        with self._lock:
            if code not in self._authorization_codes:
                raise OAuth2Error("invalid_grant", "Invalid authorization code")

            code_info = self._authorization_codes.pop(code)

            # Validate code expiration (10 minutes)
            if time.time() - code_info["created_at"] > 600:
                raise OAuth2Error("invalid_grant", "Authorization code expired")

            # Validate client
            if code_info["client_id"] != client_id:
                raise OAuth2Error("invalid_client", "Client mismatch")

            if code_info["redirect_uri"] != redirect_uri:
                raise OAuth2Error("invalid_grant", "Redirect URI mismatch")

            # Validate client credentials
            client = self._clients.get(client_id)
            if not client or client["client_secret"] != client_secret:
                raise OAuth2Error("invalid_client", "Invalid client credentials")

            # Validate PKCE
            if code_info["code_challenge"]:
                if not code_verifier:
                    raise OAuth2Error("invalid_grant", "Code verifier required")

                expected = hashlib.sha256(code_verifier.encode()).digest()
                expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b"=").decode()

                if expected_b64 != code_info["code_challenge"]:
                    raise OAuth2Error("invalid_grant", "Invalid code verifier")

            # Create tokens
            token_info = self.token_manager.create_token(
                user_id=code_info["user_id"],
                scopes=code_info["scopes"],
                client_id=client_id,
            )

            # Create ID token if openid scope
            if "openid" in code_info["scopes"]:
                user_info = self._users.get(code_info["user_id"], {})
                id_token_payload = {
                    "iss": self.issuer,
                    "sub": code_info["user_id"],
                    "aud": client_id,
                    "nonce": secrets.token_hex(16),
                    **{k: v for k, v in user_info.items() if k in ["name", "email", "picture"]},
                }
                token_info.id_token = self.jwt_handler.encode(id_token_payload)

            return token_info

    def get_userinfo(self, access_token: str) -> Dict[str, Any]:
        """Get user info from access token."""
        payload = self.token_manager.validate_token(access_token)
        user_id = payload.get("sub")

        with self._lock:
            user_info = self._users.get(user_id, {})

        # Filter by scopes
        scopes = payload.get("scope", "").split()
        result = {"sub": user_id}

        if "profile" in scopes:
            for key in ["name", "family_name", "given_name", "nickname", "picture"]:
                if key in user_info:
                    result[key] = user_info[key]

        if "email" in scopes:
            if "email" in user_info:
                result["email"] = user_info["email"]
                result["email_verified"] = user_info.get("email_verified", False)

        return result

    def get_discovery_document(self) -> Dict[str, Any]:
        """Get OIDC discovery document."""
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "userinfo_endpoint": f"{self.issuer}/userinfo",
            "jwks_uri": f"{self.issuer}/.well-known/jwks.json",
            "response_types_supported": ["code", "token", "id_token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256", "HS256"],
            "scopes_supported": ["openid", "profile", "email"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
            "claims_supported": ["sub", "iss", "aud", "exp", "iat", "name", "email"],
            "code_challenge_methods_supported": ["S256"],
        }
