"""
Vault Backends - مخازن الأسرار الخارجية
========================================

تكامل مع مخازن الأسرار الخارجية:
- HashiCorp Vault
- AWS Secrets Manager
- Azure Key Vault
- Google Cloud Secret Manager
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from distributed_cluster.security.secrets import (
    Secret,
    SecretMetadata,
    SecretStore,
    SecretType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Base Vault Backend
# =============================================================================


@dataclass
class VaultConfig:
    """إعدادات Vault."""

    address: str
    token: Optional[str] = None
    namespace: Optional[str] = None
    mount_point: str = "secret"
    verify_ssl: bool = True
    timeout: int = 30


class VaultBackend(SecretStore, ABC):
    """واجهة أساسية لـ Vault backends."""

    @abstractmethod
    async def health_check(self) -> bool:
        """فحص صحة الاتصال."""
        pass

    @abstractmethod
    async def list_keys(self, path: str = "") -> List[str]:
        """قائمة المفاتيح في مسار."""
        pass


# =============================================================================
# HashiCorp Vault
# =============================================================================


class HashiCorpVaultStore(VaultBackend):
    """
    مخزن أسرار HashiCorp Vault.

    يدعم:
    - KV Secrets Engine v2
    - Token و AppRole authentication
    - Namespaces
    - Dynamic secrets (read-only)
    """

    def __init__(self, config: VaultConfig):
        self.config = config
        self._client = None

    async def _get_client(self):
        """الحصول على HTTP client."""
        if self._client is None:
            try:
                import httpx

                self._client = httpx.AsyncClient(
                    base_url=self.config.address,
                    timeout=self.config.timeout,
                    verify=self.config.verify_ssl,
                )
            except ImportError:
                raise ImportError("httpx required: pip install httpx")
        return self._client

    def _headers(self) -> Dict[str, str]:
        """إنشاء headers للطلب."""
        headers = {}
        if self.config.token:
            headers["X-Vault-Token"] = self.config.token
        if self.config.namespace:
            headers["X-Vault-Namespace"] = self.config.namespace
        return headers

    def _secret_path(self, name: str, namespace: str) -> str:
        """بناء مسار السر."""
        return f"/v1/{self.config.mount_point}/data/{namespace}/{name}"

    def _metadata_path(self, name: str, namespace: str) -> str:
        """بناء مسار metadata."""
        return f"/v1/{self.config.mount_point}/metadata/{namespace}/{name}"

    async def health_check(self) -> bool:
        """فحص صحة Vault."""
        try:
            client = await self._get_client()
            resp = await client.get("/v1/sys/health", headers=self._headers())
            return resp.status_code in (200, 429, 472, 473)
        except Exception as e:
            logger.error(f"Vault health check failed: {e}")
            return False

    async def create(self, secret: Secret) -> bool:
        """إنشاء سر في Vault."""
        try:
            client = await self._get_client()
            path = self._secret_path(secret.metadata.name, secret.metadata.namespace)

            # Convert bytes to strings
            data = {k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in secret.data.items()}

            # Add metadata as custom metadata
            payload = {"data": data, "options": {"cas": 0}}  # Create only if doesn't exist

            resp = await client.post(path, json=payload, headers=self._headers())

            if resp.status_code in (200, 204):
                logger.info(f"Created secret in Vault: {secret.metadata.namespace}/{secret.metadata.name}")
                return True
            else:
                logger.error(f"Vault create failed: {resp.status_code} - {resp.text}")
                return False

        except Exception as e:
            logger.error(f"Vault create error: {e}")
            return False

    async def get(self, name: str, namespace: str = "default") -> Optional[Secret]:
        """الحصول على سر من Vault."""
        try:
            client = await self._get_client()
            path = self._secret_path(name, namespace)

            resp = await client.get(path, headers=self._headers())

            if resp.status_code == 404:
                return None

            if resp.status_code != 200:
                logger.error(f"Vault get failed: {resp.status_code}")
                return None

            vault_data = resp.json()
            secret_data = vault_data.get("data", {}).get("data", {})
            metadata_resp = vault_data.get("data", {}).get("metadata", {})

            # Build secret
            metadata = SecretMetadata(
                name=name,
                namespace=namespace,
                secret_type=SecretType.OPAQUE,
                version=metadata_resp.get("version", 1),
                created_at=datetime.fromisoformat(
                    metadata_resp.get("created_time", datetime.now(timezone.utc).isoformat()).replace("Z", "")
                ),
            )

            # Encode values as bytes
            data = {k: v.encode("utf-8") if isinstance(v, str) else v for k, v in secret_data.items()}

            return Secret(metadata=metadata, data=data)

        except Exception as e:
            logger.error(f"Vault get error: {e}")
            return None

    async def update(self, secret: Secret) -> bool:
        """تحديث سر في Vault."""
        try:
            client = await self._get_client()
            path = self._secret_path(secret.metadata.name, secret.metadata.namespace)

            data = {k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in secret.data.items()}

            payload = {"data": data}

            resp = await client.post(path, json=payload, headers=self._headers())

            if resp.status_code in (200, 204):
                logger.info(f"Updated secret in Vault: {secret.metadata.namespace}/{secret.metadata.name}")
                return True
            else:
                logger.error(f"Vault update failed: {resp.status_code}")
                return False

        except Exception as e:
            logger.error(f"Vault update error: {e}")
            return False

    async def delete(self, name: str, namespace: str = "default") -> bool:
        """حذف سر من Vault."""
        try:
            client = await self._get_client()
            # Delete metadata (permanently deletes all versions)
            path = self._metadata_path(name, namespace)

            resp = await client.delete(path, headers=self._headers())

            if resp.status_code in (200, 204):
                logger.info(f"Deleted secret from Vault: {namespace}/{name}")
                return True
            else:
                logger.error(f"Vault delete failed: {resp.status_code}")
                return False

        except Exception as e:
            logger.error(f"Vault delete error: {e}")
            return False

    async def list(self, namespace: Optional[str] = None) -> List[SecretMetadata]:
        """قائمة الأسرار في Vault."""
        try:
            client = await self._get_client()
            ns = namespace or "default"
            path = f"/v1/{self.config.mount_point}/metadata/{ns}"

            resp = await client.request("LIST", path, headers=self._headers())

            if resp.status_code == 404:
                return []

            if resp.status_code != 200:
                logger.error(f"Vault list failed: {resp.status_code}")
                return []

            keys = resp.json().get("data", {}).get("keys", [])
            secrets = []

            for key in keys:
                if not key.endswith("/"):
                    secrets.append(
                        SecretMetadata(
                            name=key,
                            namespace=ns,
                        )
                    )

            return secrets

        except Exception as e:
            logger.error(f"Vault list error: {e}")
            return []

    async def list_keys(self, path: str = "") -> List[str]:
        """قائمة المفاتيح في مسار."""
        try:
            client = await self._get_client()
            full_path = f"/v1/{self.config.mount_point}/metadata/{path}"

            resp = await client.request("LIST", full_path, headers=self._headers())

            if resp.status_code != 200:
                return []

            return resp.json().get("data", {}).get("keys", [])

        except Exception as e:
            logger.error(f"Vault list_keys error: {e}")
            return []

    async def close(self):
        """إغلاق الاتصال."""
        if self._client:
            await self._client.aclose()
            self._client = None


# =============================================================================
# AWS Secrets Manager
# =============================================================================


class AWSSecretsManagerStore(VaultBackend):
    """
    مخزن أسرار AWS Secrets Manager.

    يدعم:
    - إنشاء وقراءة وتحديث وحذف الأسرار
    - تدوير الأسرار
    - تشفير KMS
    - Resource policies
    """

    def __init__(
        self,
        region_name: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.endpoint_url = endpoint_url
        self._client = None

    def _get_client(self):
        """الحصول على boto3 client."""
        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise ImportError("boto3 required: pip install boto3")

            kwargs = {"region_name": self.region_name}

            if self.aws_access_key_id:
                kwargs["aws_access_key_id"] = self.aws_access_key_id
            if self.aws_secret_access_key:
                kwargs["aws_secret_access_key"] = self.aws_secret_access_key
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url

            self._client = boto3.client("secretsmanager", **kwargs)

        return self._client

    def _secret_name(self, name: str, namespace: str) -> str:
        """بناء اسم السر."""
        if namespace == "default":
            return f"nebula/{name}"
        return f"nebula/{namespace}/{name}"

    async def health_check(self) -> bool:
        """فحص صحة AWS."""
        try:
            client = self._get_client()
            client.list_secrets(MaxResults=1)
            return True
        except Exception as e:
            logger.error(f"AWS health check failed: {e}")
            return False

    async def create(self, secret: Secret) -> bool:
        """إنشاء سر في AWS."""
        try:
            client = self._get_client()
            name = self._secret_name(secret.metadata.name, secret.metadata.namespace)

            # Convert to JSON string
            data = {k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in secret.data.items()}

            client.create_secret(
                Name=name,
                SecretString=json.dumps(data),
                Description=f"NebulaCompute secret: {secret.metadata.name}",
                Tags=[
                    {"Key": "nebula:namespace", "Value": secret.metadata.namespace},
                    {"Key": "nebula:type", "Value": secret.metadata.secret_type.value},
                ],
            )

            logger.info(f"Created secret in AWS: {name}")
            return True

        except Exception as e:
            if "ResourceExistsException" in str(type(e).__name__):
                logger.warning(f"Secret already exists in AWS: {secret.metadata.name}")
                return False
            logger.error(f"AWS create error: {e}")
            return False

    async def get(self, name: str, namespace: str = "default") -> Optional[Secret]:
        """الحصول على سر من AWS."""
        try:
            client = self._get_client()
            aws_name = self._secret_name(name, namespace)

            response = client.get_secret_value(SecretId=aws_name)

            secret_string = response.get("SecretString")
            if not secret_string:
                return None

            secret_data = json.loads(secret_string)

            metadata = SecretMetadata(
                name=name,
                namespace=namespace,
                created_at=response.get("CreatedDate", datetime.now(timezone.utc)),
            )

            # Encode as bytes
            data = {k: v.encode("utf-8") for k, v in secret_data.items()}

            return Secret(metadata=metadata, data=data)

        except Exception as e:
            if "ResourceNotFoundException" in str(type(e).__name__):
                return None
            logger.error(f"AWS get error: {e}")
            return None

    async def update(self, secret: Secret) -> bool:
        """تحديث سر في AWS."""
        try:
            client = self._get_client()
            name = self._secret_name(secret.metadata.name, secret.metadata.namespace)

            data = {k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in secret.data.items()}

            client.put_secret_value(
                SecretId=name,
                SecretString=json.dumps(data),
            )

            logger.info(f"Updated secret in AWS: {name}")
            return True

        except Exception as e:
            logger.error(f"AWS update error: {e}")
            return False

    async def delete(self, name: str, namespace: str = "default") -> bool:
        """حذف سر من AWS."""
        try:
            client = self._get_client()
            aws_name = self._secret_name(name, namespace)

            client.delete_secret(
                SecretId=aws_name,
                ForceDeleteWithoutRecovery=True,
            )

            logger.info(f"Deleted secret from AWS: {aws_name}")
            return True

        except Exception as e:
            if "ResourceNotFoundException" in str(type(e).__name__):
                return False
            logger.error(f"AWS delete error: {e}")
            return False

    async def list(self, namespace: Optional[str] = None) -> List[SecretMetadata]:
        """قائمة الأسرار في AWS."""
        try:
            client = self._get_client()
            secrets = []

            paginator = client.get_paginator("list_secrets")

            filters = [{"Key": "name", "Values": ["nebula/"]}]

            for page in paginator.paginate(Filters=filters):
                for secret in page.get("SecretList", []):
                    aws_name = secret["Name"]

                    # Parse namespace and name from path
                    parts = aws_name.replace("nebula/", "").split("/")
                    if len(parts) == 1:
                        ns, name = "default", parts[0]
                    else:
                        ns, name = parts[0], "/".join(parts[1:])

                    if namespace and ns != namespace:
                        continue

                    secrets.append(
                        SecretMetadata(
                            name=name,
                            namespace=ns,
                            created_at=secret.get("CreatedDate", datetime.now(timezone.utc)),
                        )
                    )

            return secrets

        except Exception as e:
            logger.error(f"AWS list error: {e}")
            return []

    async def list_keys(self, path: str = "") -> List[str]:
        """قائمة المفاتيح."""
        secrets = await self.list()
        return [s.name for s in secrets]

    async def rotate(self, name: str, namespace: str = "default") -> bool:
        """تدوير سر في AWS."""
        try:
            client = self._get_client()
            aws_name = self._secret_name(name, namespace)

            client.rotate_secret(SecretId=aws_name)

            logger.info(f"Rotated secret in AWS: {aws_name}")
            return True

        except Exception as e:
            logger.error(f"AWS rotate error: {e}")
            return False


# =============================================================================
# Azure Key Vault
# =============================================================================


class AzureKeyVaultStore(VaultBackend):
    """
    مخزن أسرار Azure Key Vault.

    يدعم:
    - إنشاء وقراءة وتحديث وحذف الأسرار
    - Managed Identity authentication
    - Secret versioning
    """

    def __init__(
        self,
        vault_url: str,
        credential: Optional[Any] = None,
    ):
        self.vault_url = vault_url
        self._credential = credential
        self._client = None

    def _get_client(self):
        """الحصول على Azure client."""
        if self._client is None:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient
            except ImportError:
                raise ImportError("Azure SDK required: pip install azure-identity azure-keyvault-secrets")

            credential = self._credential or DefaultAzureCredential()
            self._client = SecretClient(vault_url=self.vault_url, credential=credential)

        return self._client

    def _secret_name(self, name: str, namespace: str) -> str:
        """بناء اسم السر (Azure لا يدعم / في الأسماء)."""
        if namespace == "default":
            return f"nebula-{name}"
        return f"nebula-{namespace}-{name}"

    async def health_check(self) -> bool:
        """فحص صحة Azure."""
        try:
            client = self._get_client()
            list(client.list_properties_of_secrets(max_page_size=1))
            return True
        except Exception as e:
            logger.error(f"Azure health check failed: {e}")
            return False

    async def create(self, secret: Secret) -> bool:
        """إنشاء سر في Azure."""
        try:
            client = self._get_client()
            name = self._secret_name(secret.metadata.name, secret.metadata.namespace)

            # Convert to JSON string
            data = {k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in secret.data.items()}

            client.set_secret(
                name,
                json.dumps(data),
                content_type="application/json",
                tags={
                    "nebula-namespace": secret.metadata.namespace,
                    "nebula-type": secret.metadata.secret_type.value,
                },
            )

            logger.info(f"Created secret in Azure: {name}")
            return True

        except Exception as e:
            logger.error(f"Azure create error: {e}")
            return False

    async def get(self, name: str, namespace: str = "default") -> Optional[Secret]:
        """الحصول على سر من Azure."""
        try:
            client = self._get_client()
            azure_name = self._secret_name(name, namespace)

            azure_secret = client.get_secret(azure_name)

            if not azure_secret.value:
                return None

            secret_data = json.loads(azure_secret.value)

            metadata = SecretMetadata(
                name=name,
                namespace=namespace,
                created_at=azure_secret.properties.created_on or datetime.now(timezone.utc),
                updated_at=azure_secret.properties.updated_on or datetime.now(timezone.utc),
            )

            data = {k: v.encode("utf-8") for k, v in secret_data.items()}

            return Secret(metadata=metadata, data=data)

        except Exception as e:
            if "SecretNotFound" in str(e):
                return None
            logger.error(f"Azure get error: {e}")
            return None

    async def update(self, secret: Secret) -> bool:
        """تحديث سر في Azure."""
        # Azure set_secret creates a new version
        return await self.create(secret)

    async def delete(self, name: str, namespace: str = "default") -> bool:
        """حذف سر من Azure."""
        try:
            client = self._get_client()
            azure_name = self._secret_name(name, namespace)

            poller = client.begin_delete_secret(azure_name)
            poller.wait()

            logger.info(f"Deleted secret from Azure: {azure_name}")
            return True

        except Exception as e:
            logger.error(f"Azure delete error: {e}")
            return False

    async def list(self, namespace: Optional[str] = None) -> List[SecretMetadata]:
        """قائمة الأسرار في Azure."""
        try:
            client = self._get_client()
            secrets = []

            for props in client.list_properties_of_secrets():
                if not props.name.startswith("nebula-"):
                    continue

                # Parse namespace and name
                parts = props.name.replace("nebula-", "").split("-", 1)
                if len(parts) == 1:
                    ns, name = "default", parts[0]
                else:
                    ns, name = parts[0], parts[1]

                if namespace and ns != namespace:
                    continue

                secrets.append(
                    SecretMetadata(
                        name=name,
                        namespace=ns,
                        created_at=props.created_on or datetime.now(timezone.utc),
                    )
                )

            return secrets

        except Exception as e:
            logger.error(f"Azure list error: {e}")
            return []

    async def list_keys(self, path: str = "") -> List[str]:
        """قائمة المفاتيح."""
        secrets = await self.list()
        return [s.name for s in secrets]


# =============================================================================
# Factory
# =============================================================================


def create_vault_backend(
    backend_type: str,
    **kwargs,
) -> VaultBackend:
    """
    إنشاء vault backend.

    Args:
        backend_type: نوع الـ backend (hashicorp, aws, azure)
        **kwargs: إعدادات الـ backend

    Returns:
        VaultBackend instance
    """
    if backend_type == "hashicorp":
        config = VaultConfig(
            address=kwargs.get("address", "http://localhost:8200"),
            token=kwargs.get("token"),
            namespace=kwargs.get("namespace"),
            mount_point=kwargs.get("mount_point", "secret"),
        )
        return HashiCorpVaultStore(config)

    elif backend_type == "aws":
        return AWSSecretsManagerStore(
            region_name=kwargs.get("region_name", "us-east-1"),
            aws_access_key_id=kwargs.get("aws_access_key_id"),
            aws_secret_access_key=kwargs.get("aws_secret_access_key"),
            endpoint_url=kwargs.get("endpoint_url"),
        )

    elif backend_type == "azure":
        return AzureKeyVaultStore(
            vault_url=kwargs["vault_url"],
            credential=kwargs.get("credential"),
        )

    else:
        raise ValueError(f"Unknown backend type: {backend_type}")
