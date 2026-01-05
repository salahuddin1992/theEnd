"""
Artifact Storage - تخزين الملفات
==================================

تخزين ملفات الإدخال والإخراج للـ Jobs:

1. **Local Storage**: للتطوير والاختبار
2. **S3 Storage**: للإنتاج (S3, MinIO, etc.)
3. **NFS**: (مستقبلاً)

**لماذا تفصل قناة الملفات عن قناة التحكم؟**
- ملفات الإدخال/الإخراج قد تكون ضخمة (GB)
- لا تريد إرسالها عبر نفس API
- S3/MinIO يوفر streaming و resumable uploads
- يمكن للـ Worker تنزيل مباشرة بدون تحميل على Master
"""

from __future__ import annotations

import asyncio
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Optional
from urllib.parse import urlparse

import aiofiles


@dataclass
class ArtifactMetadata:
    """معلومات artifact."""

    name: str
    uri: str
    size_bytes: int
    checksum: str  # sha256:...
    content_type: str = "application/octet-stream"
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """هل انتهت صلاحيته؟"""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


class ArtifactStorage(ABC):
    """
    واجهة تخزين Artifacts.

    كل implementation لازم يوفر:
    - upload: رفع ملف
    - download: تنزيل ملف
    - delete: حذف ملف
    - exists: التحقق من وجود
    - get_metadata: معلومات الملف
    - generate_url: توليد URL للوصول المباشر (إن أمكن)
    """

    @abstractmethod
    async def upload(
        self,
        source: str | Path | BinaryIO,
        destination: str,
        metadata: Optional[dict[str, str]] = None,
    ) -> ArtifactMetadata:
        """
        رفع ملف.

        Args:
            source: مسار الملف المحلي أو file object
            destination: المسار في التخزين
            metadata: معلومات إضافية

        Returns:
            ArtifactMetadata مع URI وchecksum
        """
        pass

    @abstractmethod
    async def download(
        self,
        uri: str,
        destination: str | Path,
    ) -> Path:
        """
        تنزيل ملف.

        Args:
            uri: URI الملف
            destination: مسار الحفظ المحلي

        Returns:
            Path للملف المحفوظ
        """
        pass

    @abstractmethod
    async def delete(self, uri: str) -> bool:
        """حذف ملف."""
        pass

    @abstractmethod
    async def exists(self, uri: str) -> bool:
        """التحقق من وجود ملف."""
        pass

    @abstractmethod
    async def get_metadata(self, uri: str) -> Optional[ArtifactMetadata]:
        """الحصول على معلومات ملف."""
        pass

    async def generate_presigned_url(
        self,
        uri: str,
        expires_in_seconds: int = 3600,
        method: str = "GET",
    ) -> Optional[str]:
        """
        توليد URL مؤقت للوصول المباشر.

        مفيد للـ S3 حتى Worker يقدر يتنزل مباشرة.
        """
        return None  # Default: not supported

    @staticmethod
    def compute_checksum(filepath: str | Path, algorithm: str = "sha256") -> str:
        """حساب checksum لملف."""
        hash_func = hashlib.new(algorithm)

        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)

        return f"{algorithm}:{hash_func.hexdigest()}"


class LocalStorage(ArtifactStorage):
    """
    تخزين محلي.

    للتطوير والاختبار. يحفظ في مجلد على الـ filesystem.
    """

    def __init__(self, base_path: str | Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, uri: str) -> Path:
        """تحويل URI إلى مسار محلي."""
        # Handle local:// URIs
        if uri.startswith("local://"):
            path = uri[8:]  # Remove "local://"
        elif uri.startswith("file://"):
            path = uri[7:]
        else:
            path = uri

        # Security: prevent path traversal
        resolved = (self.base_path / path).resolve()
        if not str(resolved).startswith(str(self.base_path.resolve())):
            raise ValueError(f"Invalid path: {uri}")

        return resolved

    async def upload(
        self,
        source: str | Path | BinaryIO,
        destination: str,
        metadata: Optional[dict[str, str]] = None,
    ) -> ArtifactMetadata:
        """رفع ملف للتخزين المحلي."""
        dest_path = self._resolve_path(destination)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        if isinstance(source, (str, Path)):
            source_path = Path(source)
            if not source_path.exists():
                raise FileNotFoundError(f"Source not found: {source}")

            # Async copy
            async with aiofiles.open(source_path, "rb") as src:
                async with aiofiles.open(dest_path, "wb") as dst:
                    while chunk := await src.read(8192):
                        await dst.write(chunk)

            size = source_path.stat().st_size
        else:
            # BinaryIO
            async with aiofiles.open(dest_path, "wb") as dst:
                size = 0
                while True:
                    chunk = source.read(8192)
                    if not chunk:
                        break
                    await dst.write(chunk)
                    size += len(chunk)

        # Compute checksum
        checksum = self.compute_checksum(dest_path)

        uri = f"local://{destination}"
        return ArtifactMetadata(
            name=dest_path.name,
            uri=uri,
            size_bytes=size,
            checksum=checksum,
            metadata=metadata or {},
        )

    async def download(
        self,
        uri: str,
        destination: str | Path,
    ) -> Path:
        """تنزيل ملف من التخزين المحلي."""
        source_path = self._resolve_path(uri)
        dest_path = Path(destination)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if not source_path.exists():
            raise FileNotFoundError(f"Artifact not found: {uri}")

        # Async copy
        async with aiofiles.open(source_path, "rb") as src:
            async with aiofiles.open(dest_path, "wb") as dst:
                while chunk := await src.read(8192):
                    await dst.write(chunk)

        return dest_path

    async def delete(self, uri: str) -> bool:
        """حذف ملف."""
        try:
            path = self._resolve_path(uri)
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception:
            return False

    async def exists(self, uri: str) -> bool:
        """التحقق من وجود ملف."""
        try:
            path = self._resolve_path(uri)
            return path.exists()
        except Exception:
            return False

    async def get_metadata(self, uri: str) -> Optional[ArtifactMetadata]:
        """الحصول على معلومات ملف."""
        try:
            path = self._resolve_path(uri)
            if not path.exists():
                return None

            stat = path.stat()
            checksum = self.compute_checksum(path)

            return ArtifactMetadata(
                name=path.name,
                uri=uri,
                size_bytes=stat.st_size,
                checksum=checksum,
                created_at=datetime.fromtimestamp(stat.st_ctime),
            )
        except Exception:
            return None


class S3Storage(ArtifactStorage):
    """
    تخزين S3 (AWS S3, MinIO, etc.).

    للإنتاج. يدعم:
    - Presigned URLs
    - Multipart upload
    - Bucket policies
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = "us-east-1",
        prefix: str = "",
    ):
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.prefix = prefix.strip("/")

        self._client = None

    def _get_client(self):
        """الحصول على S3 client (lazy initialization)."""
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config

                config = Config(
                    region_name=self.region,
                    signature_version="s3v4",
                )

                session_kwargs = {}
                if self.access_key and self.secret_key:
                    session_kwargs["aws_access_key_id"] = self.access_key
                    session_kwargs["aws_secret_access_key"] = self.secret_key

                session = boto3.Session(**session_kwargs)
                self._client = session.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    config=config,
                )
            except ImportError:
                raise RuntimeError("boto3 is required for S3 storage. Install with: pip install boto3")

        return self._client

    def _get_key(self, path: str) -> str:
        """تحويل path إلى S3 key."""
        if path.startswith("s3://"):
            # Parse S3 URI
            parsed = urlparse(path)
            return parsed.path.lstrip("/")
        if self.prefix:
            return f"{self.prefix}/{path.lstrip('/')}"
        return path.lstrip("/")

    def _get_uri(self, key: str) -> str:
        """تحويل S3 key إلى URI."""
        return f"s3://{self.bucket}/{key}"

    async def upload(
        self,
        source: str | Path | BinaryIO,
        destination: str,
        metadata: Optional[dict[str, str]] = None,
    ) -> ArtifactMetadata:
        """رفع ملف لـ S3."""
        client = self._get_client()
        key = self._get_key(destination)

        extra_args = {}
        if metadata:
            extra_args["Metadata"] = metadata

        # Upload
        loop = asyncio.get_running_loop()

        if isinstance(source, (str, Path)):
            source_path = Path(source)
            size = source_path.stat().st_size
            checksum = self.compute_checksum(source_path)

            await loop.run_in_executor(
                None,
                lambda: client.upload_file(
                    str(source_path),
                    self.bucket,
                    key,
                    ExtraArgs=extra_args if extra_args else None,
                ),
            )
        else:
            # BinaryIO - read all to get size (not ideal for large files)
            data = source.read()
            size = len(data)
            checksum = f"sha256:{hashlib.sha256(data).hexdigest()}"

            await loop.run_in_executor(
                None,
                lambda: client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=data,
                    **extra_args,
                ),
            )

        uri = self._get_uri(key)
        return ArtifactMetadata(
            name=Path(destination).name,
            uri=uri,
            size_bytes=size,
            checksum=checksum,
            metadata=metadata or {},
        )

    async def download(
        self,
        uri: str,
        destination: str | Path,
    ) -> Path:
        """تنزيل ملف من S3."""
        client = self._get_client()
        key = self._get_key(uri)
        dest_path = Path(destination)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: client.download_file(
                self.bucket,
                key,
                str(dest_path),
            ),
        )

        return dest_path

    async def delete(self, uri: str) -> bool:
        """حذف ملف من S3."""
        try:
            client = self._get_client()
            key = self._get_key(uri)

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: client.delete_object(
                    Bucket=self.bucket,
                    Key=key,
                ),
            )
            return True
        except Exception:
            return False

    async def exists(self, uri: str) -> bool:
        """التحقق من وجود ملف في S3."""
        try:
            client = self._get_client()
            key = self._get_key(uri)

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: client.head_object(
                    Bucket=self.bucket,
                    Key=key,
                ),
            )
            return True
        except Exception:
            return False

    async def get_metadata(self, uri: str) -> Optional[ArtifactMetadata]:
        """الحصول على معلومات ملف من S3."""
        try:
            client = self._get_client()
            key = self._get_key(uri)

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.head_object(
                    Bucket=self.bucket,
                    Key=key,
                ),
            )

            return ArtifactMetadata(
                name=Path(key).name,
                uri=self._get_uri(key),
                size_bytes=response["ContentLength"],
                checksum=response.get("ETag", "").strip('"'),
                content_type=response.get("ContentType", "application/octet-stream"),
                created_at=response.get("LastModified", datetime.now(timezone.utc)),
                metadata=response.get("Metadata", {}),
            )
        except Exception:
            return None

    async def generate_presigned_url(
        self,
        uri: str,
        expires_in_seconds: int = 3600,
        method: str = "GET",
    ) -> Optional[str]:
        """توليد URL مؤقت للوصول المباشر."""
        try:
            client = self._get_client()
            key = self._get_key(uri)

            client_method = "get_object" if method == "GET" else "put_object"

            loop = asyncio.get_running_loop()
            url = await loop.run_in_executor(
                None,
                lambda: client.generate_presigned_url(
                    ClientMethod=client_method,
                    Params={
                        "Bucket": self.bucket,
                        "Key": key,
                    },
                    ExpiresIn=expires_in_seconds,
                ),
            )
            return url
        except Exception:
            return None


def create_storage(storage_type: str, **kwargs) -> ArtifactStorage:
    """
    إنشاء storage حسب النوع.

    Args:
        storage_type: "local" or "s3"
        **kwargs: إعدادات حسب النوع
    """
    if storage_type == "local":
        return LocalStorage(kwargs.get("base_path", "./artifacts"))
    elif storage_type == "s3":
        return S3Storage(
            bucket=kwargs["bucket"],
            endpoint_url=kwargs.get("endpoint_url"),
            access_key=kwargs.get("access_key"),
            secret_key=kwargs.get("secret_key"),
            region=kwargs.get("region", "us-east-1"),
            prefix=kwargs.get("prefix", ""),
        )
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")
