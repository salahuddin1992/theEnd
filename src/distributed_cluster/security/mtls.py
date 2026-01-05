"""
Mutual TLS (mTLS) Authentication - مصادقة TLS المتبادلة
=======================================================

Secure node-to-node authentication using certificates.
مصادقة آمنة بين العقد باستخدام الشهادات.

Features:
- Certificate generation and signing
- Certificate validation and revocation
- Automatic certificate rotation
- Certificate chain verification
"""

from __future__ import annotations

import logging
import os
import ssl
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

logger = logging.getLogger(__name__)


class CertificateType(str, Enum):
    """Certificate types."""

    CA = "ca"  # Certificate Authority
    SERVER = "server"  # Server/Master certificate
    CLIENT = "client"  # Client/Worker certificate
    PEER = "peer"  # Peer-to-peer certificate


class CertificateStatus(str, Enum):
    """Certificate status."""

    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    NOT_YET_VALID = "not_yet_valid"
    INVALID = "invalid"


class KeyAlgorithm(str, Enum):
    """Key generation algorithms."""

    RSA_2048 = "rsa_2048"
    RSA_4096 = "rsa_4096"
    ECDSA_P256 = "ecdsa_p256"
    ECDSA_P384 = "ecdsa_p384"


@dataclass
class CertificateInfo:
    """Certificate information."""

    serial_number: str
    subject: Dict[str, str]
    issuer: Dict[str, str]
    not_before: datetime
    not_after: datetime
    fingerprint_sha256: str
    cert_type: CertificateType
    status: CertificateStatus = CertificateStatus.VALID

    # Additional metadata
    node_id: Optional[str] = None
    hostname: Optional[str] = None
    ip_addresses: List[str] = field(default_factory=list)
    dns_names: List[str] = field(default_factory=list)

    # Revocation info
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.not_after

    @property
    def is_valid(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.status == CertificateStatus.VALID and self.not_before <= now <= self.not_after

    @property
    def days_until_expiry(self) -> int:
        return (self.not_after - datetime.now(timezone.utc)).days

    def to_dict(self) -> Dict[str, Any]:
        return {
            "serial_number": self.serial_number,
            "subject": self.subject,
            "issuer": self.issuer,
            "not_before": self.not_before.isoformat(),
            "not_after": self.not_after.isoformat(),
            "fingerprint_sha256": self.fingerprint_sha256,
            "cert_type": self.cert_type.value,
            "status": self.status.value,
            "node_id": self.node_id,
            "hostname": self.hostname,
            "ip_addresses": self.ip_addresses,
            "dns_names": self.dns_names,
            "is_valid": self.is_valid,
            "days_until_expiry": self.days_until_expiry,
        }


@dataclass
class CertificateBundle:
    """Certificate bundle with key material."""

    certificate_pem: bytes
    private_key_pem: bytes
    ca_certificate_pem: Optional[bytes] = None
    chain_pem: Optional[bytes] = None

    def save(self, cert_path: str, key_path: str, ca_path: Optional[str] = None) -> None:
        """Save certificate bundle to files."""
        Path(cert_path).parent.mkdir(parents=True, exist_ok=True)

        with open(cert_path, "wb") as f:
            f.write(self.certificate_pem)
            if self.chain_pem:
                f.write(b"\n")
                f.write(self.chain_pem)

        with open(key_path, "wb") as f:
            f.write(self.private_key_pem)
        os.chmod(key_path, 0o600)

        if ca_path and self.ca_certificate_pem:
            with open(ca_path, "wb") as f:
                f.write(self.ca_certificate_pem)

    @classmethod
    def load(cls, cert_path: str, key_path: str, ca_path: Optional[str] = None) -> CertificateBundle:
        """Load certificate bundle from files."""
        with open(cert_path, "rb") as f:
            certificate_pem = f.read()

        with open(key_path, "rb") as f:
            private_key_pem = f.read()

        ca_certificate_pem = None
        if ca_path and Path(ca_path).exists():
            with open(ca_path, "rb") as f:
                ca_certificate_pem = f.read()

        return cls(
            certificate_pem=certificate_pem,
            private_key_pem=private_key_pem,
            ca_certificate_pem=ca_certificate_pem,
        )


class CertificateStore(ABC):
    """Abstract certificate store."""

    @abstractmethod
    def store_certificate(self, cert_info: CertificateInfo, cert_pem: bytes) -> bool:
        pass

    @abstractmethod
    def get_certificate(self, serial_number: str) -> Optional[Tuple[CertificateInfo, bytes]]:
        pass

    @abstractmethod
    def revoke_certificate(self, serial_number: str, reason: str) -> bool:
        pass

    @abstractmethod
    def list_certificates(
        self,
        cert_type: Optional[CertificateType] = None,
        status: Optional[CertificateStatus] = None,
    ) -> List[CertificateInfo]:
        pass

    @abstractmethod
    def get_revoked_serials(self) -> Set[str]:
        pass


class MemoryCertificateStore(CertificateStore):
    """In-memory certificate store for testing."""

    def __init__(self):
        self._certificates: Dict[str, Tuple[CertificateInfo, bytes]] = {}
        self._revoked: Set[str] = set()
        self._lock = threading.RLock()

    def store_certificate(self, cert_info: CertificateInfo, cert_pem: bytes) -> bool:
        with self._lock:
            self._certificates[cert_info.serial_number] = (cert_info, cert_pem)
            return True

    def get_certificate(self, serial_number: str) -> Optional[Tuple[CertificateInfo, bytes]]:
        with self._lock:
            return self._certificates.get(serial_number)

    def revoke_certificate(self, serial_number: str, reason: str) -> bool:
        with self._lock:
            if serial_number in self._certificates:
                info, pem = self._certificates[serial_number]
                info.status = CertificateStatus.REVOKED
                info.revoked_at = datetime.now(timezone.utc)
                info.revocation_reason = reason
                self._revoked.add(serial_number)
                return True
            return False

    def list_certificates(
        self,
        cert_type: Optional[CertificateType] = None,
        status: Optional[CertificateStatus] = None,
    ) -> List[CertificateInfo]:
        with self._lock:
            results = []
            for info, _ in self._certificates.values():
                if cert_type and info.cert_type != cert_type:
                    continue
                if status and info.status != status:
                    continue
                results.append(info)
            return results

    def get_revoked_serials(self) -> Set[str]:
        with self._lock:
            return self._revoked.copy()


class FileCertificateStore(CertificateStore):
    """File-based certificate store."""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._index_file = self.base_path / "index.json"
        self._revoked_file = self.base_path / "revoked.json"
        self._lock = threading.RLock()
        self._load_index()

    def _load_index(self) -> None:
        import json

        self._index: Dict[str, Dict] = {}
        self._revoked: Set[str] = set()

        if self._index_file.exists():
            with open(self._index_file) as f:
                self._index = json.load(f)

        if self._revoked_file.exists():
            with open(self._revoked_file) as f:
                self._revoked = set(json.load(f))

    def _save_index(self) -> None:
        import json

        with open(self._index_file, "w") as f:
            json.dump(self._index, f, indent=2, default=str)

        with open(self._revoked_file, "w") as f:
            json.dump(list(self._revoked), f)

    def store_certificate(self, cert_info: CertificateInfo, cert_pem: bytes) -> bool:
        with self._lock:
            cert_file = self.base_path / f"{cert_info.serial_number}.pem"
            with open(cert_file, "wb") as f:
                f.write(cert_pem)

            self._index[cert_info.serial_number] = cert_info.to_dict()
            self._save_index()
            return True

    def get_certificate(self, serial_number: str) -> Optional[Tuple[CertificateInfo, bytes]]:
        with self._lock:
            if serial_number not in self._index:
                return None

            cert_file = self.base_path / f"{serial_number}.pem"
            if not cert_file.exists():
                return None

            with open(cert_file, "rb") as f:
                cert_pem = f.read()

            data = self._index[serial_number]
            info = CertificateInfo(
                serial_number=data["serial_number"],
                subject=data["subject"],
                issuer=data["issuer"],
                not_before=datetime.fromisoformat(data["not_before"]),
                not_after=datetime.fromisoformat(data["not_after"]),
                fingerprint_sha256=data["fingerprint_sha256"],
                cert_type=CertificateType(data["cert_type"]),
                status=CertificateStatus(data["status"]),
                node_id=data.get("node_id"),
                hostname=data.get("hostname"),
                ip_addresses=data.get("ip_addresses", []),
                dns_names=data.get("dns_names", []),
            )
            return info, cert_pem

    def revoke_certificate(self, serial_number: str, reason: str) -> bool:
        with self._lock:
            if serial_number not in self._index:
                return False

            self._index[serial_number]["status"] = CertificateStatus.REVOKED.value
            self._index[serial_number]["revoked_at"] = datetime.now(timezone.utc).isoformat()
            self._index[serial_number]["revocation_reason"] = reason
            self._revoked.add(serial_number)
            self._save_index()
            return True

    def list_certificates(
        self,
        cert_type: Optional[CertificateType] = None,
        status: Optional[CertificateStatus] = None,
    ) -> List[CertificateInfo]:
        with self._lock:
            results = []
            for data in self._index.values():
                if cert_type and data["cert_type"] != cert_type.value:
                    continue
                if status and data["status"] != status.value:
                    continue

                info = CertificateInfo(
                    serial_number=data["serial_number"],
                    subject=data["subject"],
                    issuer=data["issuer"],
                    not_before=datetime.fromisoformat(data["not_before"]),
                    not_after=datetime.fromisoformat(data["not_after"]),
                    fingerprint_sha256=data["fingerprint_sha256"],
                    cert_type=CertificateType(data["cert_type"]),
                    status=CertificateStatus(data["status"]),
                )
                results.append(info)
            return results

    def get_revoked_serials(self) -> Set[str]:
        with self._lock:
            return self._revoked.copy()


class CertificateAuthority:
    """
    Certificate Authority for the distributed cluster.

    Manages certificate issuance, validation, and revocation.
    """

    def __init__(
        self,
        ca_cert_path: Optional[str] = None,
        ca_key_path: Optional[str] = None,
        store: Optional[CertificateStore] = None,
        organization: str = "NebulaCompute",
        validity_days: int = 365,
        key_algorithm: KeyAlgorithm = KeyAlgorithm.ECDSA_P256,
    ):
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError("cryptography library required for mTLS")

        self.organization = organization
        self.validity_days = validity_days
        self.key_algorithm = key_algorithm
        self.store = store or MemoryCertificateStore()

        self._ca_cert: Optional[x509.Certificate] = None
        self._ca_key: Optional[PrivateKeyTypes] = None
        self._lock = threading.RLock()

        if ca_cert_path and ca_key_path:
            self._load_ca(ca_cert_path, ca_key_path)
        else:
            self._generate_ca()

    def _generate_key(self) -> PrivateKeyTypes:
        """Generate a private key."""
        if self.key_algorithm == KeyAlgorithm.RSA_2048:
            return rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )
        elif self.key_algorithm == KeyAlgorithm.RSA_4096:
            return rsa.generate_private_key(
                public_exponent=65537,
                key_size=4096,
                backend=default_backend(),
            )
        elif self.key_algorithm == KeyAlgorithm.ECDSA_P256:
            return ec.generate_private_key(ec.SECP256R1(), default_backend())
        elif self.key_algorithm == KeyAlgorithm.ECDSA_P384:
            return ec.generate_private_key(ec.SECP384R1(), default_backend())
        else:
            raise ValueError(f"Unknown algorithm: {self.key_algorithm}")

    def _generate_ca(self) -> None:
        """Generate a new CA certificate."""
        self._ca_key = self._generate_key()

        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.organization),
                x509.NameAttribute(NameOID.COMMON_NAME, f"{self.organization} Root CA"),
            ]
        )

        now = datetime.now(timezone.utc)
        self._ca_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(self._ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=3650))  # 10 years
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(self._ca_key.public_key()),
                critical=False,
            )
            .sign(self._ca_key, hashes.SHA256(), default_backend())
        )

        logger.info("Generated new CA certificate")

    def _load_ca(self, cert_path: str, key_path: str) -> None:
        """Load existing CA certificate."""
        with open(cert_path, "rb") as f:
            self._ca_cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        with open(key_path, "rb") as f:
            self._ca_key = serialization.load_pem_private_key(
                f.read(),
                password=None,
                backend=default_backend(),
            )

        logger.info(f"Loaded CA certificate from {cert_path}")

    def save_ca(self, cert_path: str, key_path: str) -> None:
        """Save CA certificate and key."""
        Path(cert_path).parent.mkdir(parents=True, exist_ok=True)

        with open(cert_path, "wb") as f:
            f.write(self._ca_cert.public_bytes(serialization.Encoding.PEM))

        with open(key_path, "wb") as f:
            f.write(
                self._ca_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        os.chmod(key_path, 0o600)

    @property
    def ca_certificate_pem(self) -> bytes:
        """Get CA certificate in PEM format."""
        return self._ca_cert.public_bytes(serialization.Encoding.PEM)

    def issue_certificate(
        self,
        common_name: str,
        cert_type: CertificateType,
        node_id: Optional[str] = None,
        dns_names: Optional[List[str]] = None,
        ip_addresses: Optional[List[str]] = None,
        validity_days: Optional[int] = None,
    ) -> CertificateBundle:
        """
        Issue a new certificate.

        Args:
            common_name: Common name for the certificate
            cert_type: Type of certificate (server, client, peer)
            node_id: Optional node identifier
            dns_names: Optional DNS SANs
            ip_addresses: Optional IP SANs
            validity_days: Optional validity period

        Returns:
            CertificateBundle with certificate and key
        """
        import ipaddress

        with self._lock:
            private_key = self._generate_key()

            subject = x509.Name(
                [
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.organization),
                    x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                ]
            )

            now = datetime.now(timezone.utc)
            days = validity_days or self.validity_days

            builder = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(self._ca_cert.subject)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now)
                .not_valid_after(now + timedelta(days=days))
                .add_extension(
                    x509.BasicConstraints(ca=False, path_length=None),
                    critical=True,
                )
                .add_extension(
                    x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
                    critical=False,
                )
                .add_extension(
                    x509.AuthorityKeyIdentifier.from_issuer_public_key(self._ca_key.public_key()),
                    critical=False,
                )
            )

            # Add key usage based on type
            if cert_type == CertificateType.SERVER:
                builder = builder.add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        content_commitment=False,
                        key_encipherment=True,
                        data_encipherment=False,
                        key_agreement=False,
                        key_cert_sign=False,
                        crl_sign=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                builder = builder.add_extension(
                    x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                    critical=False,
                )
            elif cert_type == CertificateType.CLIENT:
                builder = builder.add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        content_commitment=False,
                        key_encipherment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        key_cert_sign=False,
                        crl_sign=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                builder = builder.add_extension(
                    x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                    critical=False,
                )
            else:  # PEER
                builder = builder.add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        content_commitment=False,
                        key_encipherment=True,
                        data_encipherment=False,
                        key_agreement=False,
                        key_cert_sign=False,
                        crl_sign=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                builder = builder.add_extension(
                    x509.ExtendedKeyUsage(
                        [
                            ExtendedKeyUsageOID.SERVER_AUTH,
                            ExtendedKeyUsageOID.CLIENT_AUTH,
                        ]
                    ),
                    critical=False,
                )

            # Add Subject Alternative Names
            san_list = []
            if dns_names:
                san_list.extend([x509.DNSName(name) for name in dns_names])
            if ip_addresses:
                san_list.extend([x509.IPAddress(ipaddress.ip_address(ip)) for ip in ip_addresses])
            if san_list:
                builder = builder.add_extension(
                    x509.SubjectAlternativeName(san_list),
                    critical=False,
                )

            certificate = builder.sign(self._ca_key, hashes.SHA256(), default_backend())

            # Create certificate info
            cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
            cert_info = CertificateInfo(
                serial_number=str(certificate.serial_number),
                subject={"CN": common_name, "O": self.organization},
                issuer={"CN": self._ca_cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value},
                not_before=certificate.not_valid_before,
                not_after=certificate.not_valid_after,
                fingerprint_sha256=certificate.fingerprint(hashes.SHA256()).hex(),
                cert_type=cert_type,
                node_id=node_id,
                hostname=common_name,
                ip_addresses=ip_addresses or [],
                dns_names=dns_names or [],
            )

            # Store certificate
            self.store.store_certificate(cert_info, cert_pem)

            # Create bundle
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )

            logger.info(f"Issued {cert_type.value} certificate for {common_name}")

            return CertificateBundle(
                certificate_pem=cert_pem,
                private_key_pem=key_pem,
                ca_certificate_pem=self.ca_certificate_pem,
            )

    def verify_certificate(
        self,
        cert_pem: bytes,
        check_revocation: bool = True,
    ) -> Tuple[bool, Optional[str], Optional[CertificateInfo]]:
        """
        Verify a certificate.

        Returns:
            (is_valid, error_message, cert_info)
        """
        try:
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

            # Check validity period
            # Note: cryptography returns naive datetimes, so we add UTC timezone for comparison
            now = datetime.now(timezone.utc)
            cert_not_valid_before = cert.not_valid_before.replace(tzinfo=timezone.utc)
            cert_not_valid_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
            if now < cert_not_valid_before:
                return False, "Certificate not yet valid", None
            if now > cert_not_valid_after:
                return False, "Certificate expired", None

            # Verify signature
            try:
                self._ca_cert.public_key().verify(
                    cert.signature,
                    cert.tbs_certificate_bytes,
                    cert.signature_algorithm_parameters,
                )
            except Exception:
                return False, "Invalid certificate signature", None

            # Check revocation
            if check_revocation:
                serial = str(cert.serial_number)
                if serial in self.store.get_revoked_serials():
                    return False, "Certificate revoked", None

            # Build cert info
            cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            cert_info = CertificateInfo(
                serial_number=str(cert.serial_number),
                subject={"CN": cn},
                issuer={"CN": self._ca_cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value},
                not_before=cert.not_valid_before,
                not_after=cert.not_valid_after,
                fingerprint_sha256=cert.fingerprint(hashes.SHA256()).hex(),
                cert_type=CertificateType.CLIENT,  # Will be determined later
            )

            return True, None, cert_info

        except Exception as e:
            return False, f"Certificate verification failed: {e}", None

    def revoke_certificate(self, serial_number: str, reason: str = "unspecified") -> bool:
        """Revoke a certificate."""
        result = self.store.revoke_certificate(serial_number, reason)
        if result:
            logger.info(f"Revoked certificate {serial_number}: {reason}")
        return result

    def list_certificates(
        self,
        cert_type: Optional[CertificateType] = None,
        status: Optional[CertificateStatus] = None,
    ) -> List[CertificateInfo]:
        """List certificates."""
        return self.store.list_certificates(cert_type, status)

    def get_expiring_certificates(self, days: int = 30) -> List[CertificateInfo]:
        """Get certificates expiring within specified days."""
        certs = self.store.list_certificates(status=CertificateStatus.VALID)
        return [c for c in certs if c.days_until_expiry <= days]

    def create_ssl_context(
        self,
        cert_bundle: CertificateBundle,
        verify_client: bool = True,
    ) -> ssl.SSLContext:
        """
        Create an SSL context for mTLS.

        Args:
            cert_bundle: Certificate bundle with key material
            verify_client: Whether to verify client certificates

        Returns:
            Configured SSL context
        """
        import tempfile

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        # Write certificate and key to temp files
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pem") as cert_file:
            cert_file.write(cert_bundle.certificate_pem)
            cert_path = cert_file.name

        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".key") as key_file:
            key_file.write(cert_bundle.private_key_pem)
            key_path = key_file.name

        try:
            context.load_cert_chain(cert_path, key_path)
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)

        if verify_client and cert_bundle.ca_certificate_pem:
            context.verify_mode = ssl.CERT_REQUIRED

            with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pem") as ca_file:
                ca_file.write(cert_bundle.ca_certificate_pem)
                ca_path = ca_file.name

            try:
                context.load_verify_locations(ca_path)
            finally:
                os.unlink(ca_path)

        return context


class MTLSAuthenticator:
    """
    mTLS Authenticator for distributed cluster.

    Provides certificate-based authentication for nodes.
    """

    def __init__(
        self,
        ca: CertificateAuthority,
        require_client_cert: bool = True,
        allowed_cert_types: Optional[List[CertificateType]] = None,
    ):
        self.ca = ca
        self.require_client_cert = require_client_cert
        self.allowed_cert_types = allowed_cert_types or [
            CertificateType.CLIENT,
            CertificateType.PEER,
        ]
        self._authenticated_nodes: Dict[str, CertificateInfo] = {}
        self._lock = threading.RLock()

    def authenticate(
        self,
        client_cert_pem: bytes,
        client_ip: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[CertificateInfo]]:
        """
        Authenticate a client certificate.

        Returns:
            (authenticated, error_message, cert_info)
        """
        valid, error, cert_info = self.ca.verify_certificate(client_cert_pem)

        if not valid:
            return False, error, None

        # Additional validation
        if cert_info.cert_type not in self.allowed_cert_types:
            return False, f"Certificate type {cert_info.cert_type} not allowed", None

        # Track authenticated node
        with self._lock:
            self._authenticated_nodes[cert_info.fingerprint_sha256] = cert_info

        logger.debug(f"Authenticated node: {cert_info.subject.get('CN')}")
        return True, None, cert_info

    def is_authenticated(self, fingerprint: str) -> bool:
        """Check if a node is authenticated."""
        with self._lock:
            return fingerprint in self._authenticated_nodes

    def get_authenticated_node(self, fingerprint: str) -> Optional[CertificateInfo]:
        """Get authenticated node info."""
        with self._lock:
            return self._authenticated_nodes.get(fingerprint)

    def revoke_authentication(self, fingerprint: str) -> bool:
        """Revoke node authentication."""
        with self._lock:
            if fingerprint in self._authenticated_nodes:
                del self._authenticated_nodes[fingerprint]
                return True
            return False

    def list_authenticated_nodes(self) -> List[CertificateInfo]:
        """List all authenticated nodes."""
        with self._lock:
            return list(self._authenticated_nodes.values())


def create_cluster_ca(
    base_path: str,
    organization: str = "NebulaCompute",
    key_algorithm: KeyAlgorithm = KeyAlgorithm.ECDSA_P256,
) -> CertificateAuthority:
    """
    Create or load a Certificate Authority for the cluster.

    Args:
        base_path: Base path for CA files
        organization: Organization name
        key_algorithm: Key generation algorithm

    Returns:
        Configured CertificateAuthority
    """
    base = Path(base_path)
    ca_cert_path = base / "ca.crt"
    ca_key_path = base / "ca.key"
    certs_path = base / "certs"

    store = FileCertificateStore(str(certs_path))

    if ca_cert_path.exists() and ca_key_path.exists():
        ca = CertificateAuthority(
            ca_cert_path=str(ca_cert_path),
            ca_key_path=str(ca_key_path),
            store=store,
            organization=organization,
            key_algorithm=key_algorithm,
        )
    else:
        ca = CertificateAuthority(
            store=store,
            organization=organization,
            key_algorithm=key_algorithm,
        )
        ca.save_ca(str(ca_cert_path), str(ca_key_path))

    return ca
