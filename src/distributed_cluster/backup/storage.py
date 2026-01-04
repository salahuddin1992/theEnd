"""
Backup Storage - تخزين النسخ الاحتياطية
========================================

Storage Backends
----------------

This module provides storage backends for backups.

يوفر هذا الملف وسائط تخزين للنسخ الاحتياطية.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from distributed_cluster.backup.snapshot import Snapshot, SnapshotMetadata

logger = logging.getLogger(__name__)


@dataclass
class StorageStats:
    """
    إحصائيات التخزين
    Storage statistics
    """
    total_snapshots: int = 0
    total_size_bytes: int = 0
    oldest_snapshot: Optional[datetime] = None
    newest_snapshot: Optional[datetime] = None
    available_space_bytes: Optional[int] = None
    used_space_bytes: Optional[int] = None


class BackupStorage(ABC):
    """
    قاعدة تخزين النسخ الاحتياطية
    Abstract Backup Storage

    واجهة مجردة لتخزين واسترجاع النسخ الاحتياطية.
    Abstract interface for storing and retrieving backups.
    """

    @abstractmethod
    async def save(
        self,
        snapshot: Snapshot,
        data: bytes,
    ) -> str:
        """
        حفظ لقطة

        Args:
            snapshot: اللقطة
            data: البيانات

        Returns:
            معرف التخزين
        """
        pass

    @abstractmethod
    async def load(
        self,
        snapshot_id: str,
    ) -> tuple[SnapshotMetadata, bytes]:
        """
        تحميل لقطة

        Args:
            snapshot_id: معرف اللقطة

        Returns:
            (البيانات الوصفية, البيانات)
        """
        pass

    @abstractmethod
    async def delete(
        self,
        snapshot_id: str,
    ) -> bool:
        """
        حذف لقطة

        Args:
            snapshot_id: معرف اللقطة

        Returns:
            نجاح العملية
        """
        pass

    @abstractmethod
    async def list_snapshots(
        self,
        cluster_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SnapshotMetadata]:
        """
        قائمة اللقطات

        Args:
            cluster_id: تصفية حسب الكتلة
            limit: الحد الأقصى
            offset: البداية

        Returns:
            قائمة البيانات الوصفية
        """
        pass

    @abstractmethod
    async def get_stats(self) -> StorageStats:
        """الحصول على إحصائيات التخزين"""
        pass

    @abstractmethod
    async def exists(self, snapshot_id: str) -> bool:
        """التحقق من وجود لقطة"""
        pass


class LocalStorage(BackupStorage):
    """
    تخزين محلي
    Local File Storage

    يخزن النسخ الاحتياطية في نظام الملفات المحلي.
    Stores backups in the local filesystem.
    """

    def __init__(
        self,
        base_path: str | Path,
        create_if_missing: bool = True,
    ):
        """
        تهيئة التخزين المحلي

        Args:
            base_path: مسار المجلد الأساسي
            create_if_missing: إنشاء المجلد إذا لم يكن موجوداً
        """
        self.base_path = Path(base_path)

        if create_if_missing:
            self.base_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        self.data_path = self.base_path / "data"
        self.metadata_path = self.base_path / "metadata"
        self.data_path.mkdir(exist_ok=True)
        self.metadata_path.mkdir(exist_ok=True)

    async def save(
        self,
        snapshot: Snapshot,
        data: bytes,
    ) -> str:
        """حفظ لقطة محلياً"""
        snapshot_id = snapshot.metadata.snapshot_id

        # Save data
        data_file = self.data_path / f"{snapshot_id}.backup"
        await asyncio.to_thread(data_file.write_bytes, data)

        # Save metadata
        metadata_file = self.metadata_path / f"{snapshot_id}.json"
        metadata_json = json.dumps(snapshot.metadata.to_dict(), indent=2)
        await asyncio.to_thread(metadata_file.write_text, metadata_json)

        logger.info(f"Saved snapshot {snapshot_id} to {data_file}")
        return snapshot_id

    async def load(
        self,
        snapshot_id: str,
    ) -> tuple[SnapshotMetadata, bytes]:
        """تحميل لقطة من التخزين المحلي"""
        # Load metadata
        metadata_file = self.metadata_path / f"{snapshot_id}.json"
        if not metadata_file.exists():
            raise FileNotFoundError(f"Snapshot metadata not found: {snapshot_id}")

        metadata_json = await asyncio.to_thread(metadata_file.read_text)
        metadata = SnapshotMetadata.from_dict(json.loads(metadata_json))

        # Load data
        data_file = self.data_path / f"{snapshot_id}.backup"
        if not data_file.exists():
            raise FileNotFoundError(f"Snapshot data not found: {snapshot_id}")

        data = await asyncio.to_thread(data_file.read_bytes)

        return metadata, data

    async def delete(
        self,
        snapshot_id: str,
    ) -> bool:
        """حذف لقطة"""
        try:
            data_file = self.data_path / f"{snapshot_id}.backup"
            metadata_file = self.metadata_path / f"{snapshot_id}.json"

            if data_file.exists():
                await asyncio.to_thread(data_file.unlink)

            if metadata_file.exists():
                await asyncio.to_thread(metadata_file.unlink)

            logger.info(f"Deleted snapshot {snapshot_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False

    async def list_snapshots(
        self,
        cluster_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SnapshotMetadata]:
        """قائمة اللقطات"""
        snapshots = []

        for metadata_file in self.metadata_path.glob("*.json"):
            try:
                metadata_json = await asyncio.to_thread(metadata_file.read_text)
                metadata = SnapshotMetadata.from_dict(json.loads(metadata_json))

                if cluster_id is None or metadata.cluster_id == cluster_id:
                    snapshots.append(metadata)

            except Exception as e:
                logger.warning(f"Failed to read metadata {metadata_file}: {e}")

        # Sort by creation time (newest first)
        snapshots.sort(key=lambda s: s.created_at, reverse=True)

        # Apply pagination
        return snapshots[offset:offset + limit]

    async def get_stats(self) -> StorageStats:
        """الحصول على إحصائيات التخزين"""
        snapshots = await self.list_snapshots(limit=10000)

        total_size = 0
        for snapshot in snapshots:
            total_size += snapshot.compressed_size_bytes

        oldest = min((s.created_at for s in snapshots), default=None)
        newest = max((s.created_at for s in snapshots), default=None)

        # Get disk space
        try:
            stat = shutil.disk_usage(self.base_path)
            available_space = stat.free
            used_space = stat.used
        except Exception:
            available_space = None
            used_space = None

        return StorageStats(
            total_snapshots=len(snapshots),
            total_size_bytes=total_size,
            oldest_snapshot=oldest,
            newest_snapshot=newest,
            available_space_bytes=available_space,
            used_space_bytes=used_space,
        )

    async def exists(self, snapshot_id: str) -> bool:
        """التحقق من وجود لقطة"""
        data_file = self.data_path / f"{snapshot_id}.backup"
        return data_file.exists()


class S3Storage(BackupStorage):
    """
    تخزين S3
    AWS S3 Storage

    يخزن النسخ الاحتياطية في Amazon S3.
    Stores backups in Amazon S3.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "backups/",
        region: str = "us-east-1",
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        """
        تهيئة تخزين S3

        Args:
            bucket: اسم الـ bucket
            prefix: بادئة المسار
            region: المنطقة
            access_key_id: معرف المفتاح
            secret_access_key: المفتاح السري
            endpoint_url: عنوان مخصص (للتوافق مع MinIO)
        """
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/"
        self.region = region
        self.access_key_id = access_key_id or os.environ.get("AWS_ACCESS_KEY_ID")
        self.secret_access_key = secret_access_key or os.environ.get("AWS_SECRET_ACCESS_KEY")
        self.endpoint_url = endpoint_url

        self._client = None

    async def _get_client(self):
        """الحصول على عميل S3"""
        if self._client is None:
            try:
                import aioboto3

                session = aioboto3.Session(
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                    region_name=self.region,
                )

                self._client = await session.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                ).__aenter__()

            except ImportError:
                raise ImportError("aioboto3 is required for S3 storage")

        return self._client

    def _data_key(self, snapshot_id: str) -> str:
        """مفتاح ملف البيانات"""
        return f"{self.prefix}data/{snapshot_id}.backup"

    def _metadata_key(self, snapshot_id: str) -> str:
        """مفتاح ملف البيانات الوصفية"""
        return f"{self.prefix}metadata/{snapshot_id}.json"

    async def save(
        self,
        snapshot: Snapshot,
        data: bytes,
    ) -> str:
        """حفظ لقطة في S3"""
        client = await self._get_client()
        snapshot_id = snapshot.metadata.snapshot_id

        # Save data
        await client.put_object(
            Bucket=self.bucket,
            Key=self._data_key(snapshot_id),
            Body=data,
            ContentType="application/octet-stream",
            Metadata={
                "snapshot-id": snapshot_id,
                "cluster-id": snapshot.metadata.cluster_id,
                "snapshot-type": snapshot.metadata.snapshot_type.value,
            },
        )

        # Save metadata
        metadata_json = json.dumps(snapshot.metadata.to_dict())
        await client.put_object(
            Bucket=self.bucket,
            Key=self._metadata_key(snapshot_id),
            Body=metadata_json.encode(),
            ContentType="application/json",
        )

        logger.info(f"Saved snapshot {snapshot_id} to S3 bucket {self.bucket}")
        return snapshot_id

    async def load(
        self,
        snapshot_id: str,
    ) -> tuple[SnapshotMetadata, bytes]:
        """تحميل لقطة من S3"""
        client = await self._get_client()

        # Load metadata
        metadata_response = await client.get_object(
            Bucket=self.bucket,
            Key=self._metadata_key(snapshot_id),
        )
        metadata_body = await metadata_response["Body"].read()
        metadata = SnapshotMetadata.from_dict(json.loads(metadata_body))

        # Load data
        data_response = await client.get_object(
            Bucket=self.bucket,
            Key=self._data_key(snapshot_id),
        )
        data = await data_response["Body"].read()

        return metadata, data

    async def delete(
        self,
        snapshot_id: str,
    ) -> bool:
        """حذف لقطة من S3"""
        try:
            client = await self._get_client()

            await client.delete_object(
                Bucket=self.bucket,
                Key=self._data_key(snapshot_id),
            )

            await client.delete_object(
                Bucket=self.bucket,
                Key=self._metadata_key(snapshot_id),
            )

            logger.info(f"Deleted snapshot {snapshot_id} from S3")
            return True

        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False

    async def list_snapshots(
        self,
        cluster_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SnapshotMetadata]:
        """قائمة اللقطات في S3"""
        client = await self._get_client()
        snapshots = []

        paginator = client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(
            Bucket=self.bucket,
            Prefix=f"{self.prefix}metadata/",
        ):
            for obj in page.get("Contents", []):
                try:
                    response = await client.get_object(
                        Bucket=self.bucket,
                        Key=obj["Key"],
                    )
                    body = await response["Body"].read()
                    metadata = SnapshotMetadata.from_dict(json.loads(body))

                    if cluster_id is None or metadata.cluster_id == cluster_id:
                        snapshots.append(metadata)

                except Exception as e:
                    logger.warning(f"Failed to read metadata {obj['Key']}: {e}")

        # Sort and paginate
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        return snapshots[offset:offset + limit]

    async def get_stats(self) -> StorageStats:
        """الحصول على إحصائيات التخزين"""
        snapshots = await self.list_snapshots(limit=10000)

        total_size = sum(s.compressed_size_bytes for s in snapshots)
        oldest = min((s.created_at for s in snapshots), default=None)
        newest = max((s.created_at for s in snapshots), default=None)

        return StorageStats(
            total_snapshots=len(snapshots),
            total_size_bytes=total_size,
            oldest_snapshot=oldest,
            newest_snapshot=newest,
        )

    async def exists(self, snapshot_id: str) -> bool:
        """التحقق من وجود لقطة"""
        try:
            client = await self._get_client()
            await client.head_object(
                Bucket=self.bucket,
                Key=self._data_key(snapshot_id),
            )
            return True
        except Exception:
            return False


class AzureStorage(BackupStorage):
    """
    تخزين Azure Blob
    Azure Blob Storage

    يخزن النسخ الاحتياطية في Azure Blob Storage.
    Stores backups in Azure Blob Storage.
    """

    def __init__(
        self,
        container_name: str,
        connection_string: Optional[str] = None,
        account_name: Optional[str] = None,
        account_key: Optional[str] = None,
        prefix: str = "backups/",
    ):
        """
        تهيئة تخزين Azure

        Args:
            container_name: اسم الحاوية
            connection_string: سلسلة الاتصال
            account_name: اسم الحساب
            account_key: مفتاح الحساب
            prefix: بادئة المسار
        """
        self.container_name = container_name
        self.connection_string = connection_string or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        self.account_name = account_name or os.environ.get("AZURE_STORAGE_ACCOUNT")
        self.account_key = account_key or os.environ.get("AZURE_STORAGE_KEY")
        self.prefix = prefix.rstrip("/") + "/"

        self._client = None

    async def _get_client(self):
        """الحصول على عميل Azure"""
        if self._client is None:
            try:
                from azure.storage.blob.aio import BlobServiceClient

                if self.connection_string:
                    self._client = BlobServiceClient.from_connection_string(
                        self.connection_string
                    )
                else:
                    account_url = f"https://{self.account_name}.blob.core.windows.net"
                    self._client = BlobServiceClient(
                        account_url=account_url,
                        credential=self.account_key,
                    )

            except ImportError:
                raise ImportError("azure-storage-blob is required for Azure storage")

        return self._client

    def _data_key(self, snapshot_id: str) -> str:
        """مفتاح ملف البيانات"""
        return f"{self.prefix}data/{snapshot_id}.backup"

    def _metadata_key(self, snapshot_id: str) -> str:
        """مفتاح ملف البيانات الوصفية"""
        return f"{self.prefix}metadata/{snapshot_id}.json"

    async def save(
        self,
        snapshot: Snapshot,
        data: bytes,
    ) -> str:
        """حفظ لقطة في Azure"""
        client = await self._get_client()
        container = client.get_container_client(self.container_name)
        snapshot_id = snapshot.metadata.snapshot_id

        # Save data
        blob = container.get_blob_client(self._data_key(snapshot_id))
        await blob.upload_blob(data, overwrite=True)

        # Save metadata
        metadata_json = json.dumps(snapshot.metadata.to_dict())
        metadata_blob = container.get_blob_client(self._metadata_key(snapshot_id))
        await metadata_blob.upload_blob(metadata_json.encode(), overwrite=True)

        logger.info(f"Saved snapshot {snapshot_id} to Azure container {self.container_name}")
        return snapshot_id

    async def load(
        self,
        snapshot_id: str,
    ) -> tuple[SnapshotMetadata, bytes]:
        """تحميل لقطة من Azure"""
        client = await self._get_client()
        container = client.get_container_client(self.container_name)

        # Load metadata
        metadata_blob = container.get_blob_client(self._metadata_key(snapshot_id))
        metadata_download = await metadata_blob.download_blob()
        metadata_body = await metadata_download.readall()
        metadata = SnapshotMetadata.from_dict(json.loads(metadata_body))

        # Load data
        data_blob = container.get_blob_client(self._data_key(snapshot_id))
        data_download = await data_blob.download_blob()
        data = await data_download.readall()

        return metadata, data

    async def delete(
        self,
        snapshot_id: str,
    ) -> bool:
        """حذف لقطة من Azure"""
        try:
            client = await self._get_client()
            container = client.get_container_client(self.container_name)

            data_blob = container.get_blob_client(self._data_key(snapshot_id))
            await data_blob.delete_blob()

            metadata_blob = container.get_blob_client(self._metadata_key(snapshot_id))
            await metadata_blob.delete_blob()

            logger.info(f"Deleted snapshot {snapshot_id} from Azure")
            return True

        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False

    async def list_snapshots(
        self,
        cluster_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SnapshotMetadata]:
        """قائمة اللقطات في Azure"""
        client = await self._get_client()
        container = client.get_container_client(self.container_name)
        snapshots = []

        async for blob in container.list_blobs(name_starts_with=f"{self.prefix}metadata/"):
            try:
                blob_client = container.get_blob_client(blob.name)
                download = await blob_client.download_blob()
                body = await download.readall()
                metadata = SnapshotMetadata.from_dict(json.loads(body))

                if cluster_id is None or metadata.cluster_id == cluster_id:
                    snapshots.append(metadata)

            except Exception as e:
                logger.warning(f"Failed to read metadata {blob.name}: {e}")

        # Sort and paginate
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        return snapshots[offset:offset + limit]

    async def get_stats(self) -> StorageStats:
        """الحصول على إحصائيات التخزين"""
        snapshots = await self.list_snapshots(limit=10000)

        total_size = sum(s.compressed_size_bytes for s in snapshots)
        oldest = min((s.created_at for s in snapshots), default=None)
        newest = max((s.created_at for s in snapshots), default=None)

        return StorageStats(
            total_snapshots=len(snapshots),
            total_size_bytes=total_size,
            oldest_snapshot=oldest,
            newest_snapshot=newest,
        )

    async def exists(self, snapshot_id: str) -> bool:
        """التحقق من وجود لقطة"""
        try:
            client = await self._get_client()
            container = client.get_container_client(self.container_name)
            blob = container.get_blob_client(self._data_key(snapshot_id))
            return await blob.exists()
        except Exception:
            return False
