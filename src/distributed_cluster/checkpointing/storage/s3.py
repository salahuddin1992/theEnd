"""
S3 Storage - تخزين Amazon S3
============================

Amazon S3 Checkpoint Storage
----------------------------

This module provides S3 storage for checkpoints.

يوفر هذا الملف تخزين نقاط الحفظ على Amazon S3.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from distributed_cluster.checkpointing.checkpoint import CheckpointMetadata
from distributed_cluster.checkpointing.storage.base import (
    CheckpointStorage,
    ConnectionError,
    ReadError,
    StorageConfig,
    WriteError,
)

logger = logging.getLogger(__name__)


class S3Storage(CheckpointStorage):
    """
    تخزين نقاط الحفظ على Amazon S3
    Amazon S3 checkpoint storage

    يخزن نقاط الحفظ في bucket S3 مع
    دعم إصدارات متعددة وتشفير.

    Stores checkpoints in S3 bucket with
    multi-version support and encryption.
    """

    def __init__(
        self,
        bucket_name: str,
        prefix: str = "checkpoints",
        region: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        server_side_encryption: str = "AES256",
        config: Optional[StorageConfig] = None,
    ):
        """
        تهيئة تخزين S3

        Args:
            bucket_name: اسم الـ bucket
            prefix: بادئة المسار
            region: منطقة AWS
            aws_access_key_id: مفتاح الوصول
            aws_secret_access_key: المفتاح السري
            endpoint_url: URL مخصص (لـ MinIO/LocalStack)
            server_side_encryption: نوع التشفير
            config: إعدادات التخزين
        """
        super().__init__(config)

        self.bucket_name = bucket_name
        self.prefix = prefix.strip("/")
        self.region = region
        self.endpoint_url = endpoint_url
        self.server_side_encryption = server_side_encryption

        # Credentials
        self._aws_access_key_id = aws_access_key_id
        self._aws_secret_access_key = aws_secret_access_key

        # S3 client
        self._s3_client = None
        self._executor = ThreadPoolExecutor(max_workers=4)

    # =========================================================================
    # Connection / الاتصال
    # =========================================================================

    async def connect(self) -> None:
        """الاتصال بـ S3"""
        try:
            import boto3

            session_kwargs = {"region_name": self.region}

            if self._aws_access_key_id and self._aws_secret_access_key:
                session_kwargs["aws_access_key_id"] = self._aws_access_key_id
                session_kwargs["aws_secret_access_key"] = self._aws_secret_access_key

            session = boto3.Session(**session_kwargs)

            client_kwargs = {}
            if self.endpoint_url:
                client_kwargs["endpoint_url"] = self.endpoint_url

            self._s3_client = session.client("s3", **client_kwargs)

            # Test connection
            await self._run_in_executor(self._s3_client.head_bucket, Bucket=self.bucket_name)

            self._connected = True
            logger.info(f"S3Storage connected to bucket {self.bucket_name}")

        except ImportError:
            raise ConnectionError("boto3 required for S3 storage. Install with: pip install boto3")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to S3: {e}")

    async def disconnect(self) -> None:
        """قطع الاتصال"""
        self._s3_client = None
        self._connected = False
        logger.info("S3Storage disconnected")

    async def _run_in_executor(self, func, *args, **kwargs):
        """تشغيل دالة boto3 في thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, lambda: func(*args, **kwargs))

    # =========================================================================
    # Checkpoint Operations / عمليات نقاط الحفظ
    # =========================================================================

    async def save_checkpoint(
        self,
        checkpoint_id: str,
        data: bytes,
        metadata: CheckpointMetadata,
    ) -> bool:
        """حفظ نقطة حفظ"""
        if not self._connected:
            raise WriteError("Not connected to S3")

        try:
            # Save data
            data_key = self._get_data_key(checkpoint_id)
            await self._run_in_executor(
                self._s3_client.put_object,
                Bucket=self.bucket_name,
                Key=data_key,
                Body=data,
                ServerSideEncryption=self.server_side_encryption,
                ContentType="application/octet-stream",
                Metadata={
                    "job_id": metadata.job_id,
                    "task_id": metadata.task_id or "",
                    "sequence_number": str(metadata.sequence_number),
                },
            )

            # Save metadata
            metadata_key = self._get_metadata_key(checkpoint_id)
            metadata_json = json.dumps(metadata.to_dict())
            await self._run_in_executor(
                self._s3_client.put_object,
                Bucket=self.bucket_name,
                Key=metadata_key,
                Body=metadata_json.encode(),
                ContentType="application/json",
            )

            # Update job index
            await self._update_job_index(metadata)

            logger.debug(f"Saved checkpoint {checkpoint_id} to S3")
            return True

        except Exception as e:
            logger.error(f"Failed to save checkpoint {checkpoint_id}: {e}")
            raise WriteError(f"Failed to save checkpoint to S3: {e}")

    async def load_checkpoint(self, checkpoint_id: str) -> Optional[bytes]:
        """تحميل نقطة حفظ"""
        if not self._connected:
            raise ReadError("Not connected to S3")

        try:
            data_key = self._get_data_key(checkpoint_id)

            response = await self._run_in_executor(
                self._s3_client.get_object,
                Bucket=self.bucket_name,
                Key=data_key,
            )

            return response["Body"].read()

        except self._s3_client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.error(f"Failed to load checkpoint {checkpoint_id}: {e}")
            raise ReadError(f"Failed to load checkpoint from S3: {e}")

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """حذف نقطة حفظ"""
        if not self._connected:
            return False

        try:
            # Get metadata for index cleanup
            metadata = await self.get_metadata(checkpoint_id)

            # Delete data
            data_key = self._get_data_key(checkpoint_id)
            await self._run_in_executor(
                self._s3_client.delete_object,
                Bucket=self.bucket_name,
                Key=data_key,
            )

            # Delete metadata
            metadata_key = self._get_metadata_key(checkpoint_id)
            await self._run_in_executor(
                self._s3_client.delete_object,
                Bucket=self.bucket_name,
                Key=metadata_key,
            )

            # Update job index
            if metadata:
                await self._remove_from_job_index(metadata)

            logger.debug(f"Deleted checkpoint {checkpoint_id} from S3")
            return True

        except Exception as e:
            logger.error(f"Failed to delete checkpoint {checkpoint_id}: {e}")
            return False

    async def get_metadata(
        self,
        checkpoint_id: str,
    ) -> Optional[CheckpointMetadata]:
        """الحصول على البيانات الوصفية"""
        if not self._connected:
            return None

        try:
            metadata_key = self._get_metadata_key(checkpoint_id)

            response = await self._run_in_executor(
                self._s3_client.get_object,
                Bucket=self.bucket_name,
                Key=metadata_key,
            )

            data = response["Body"].read()
            metadata_dict = json.loads(data.decode())

            return CheckpointMetadata.from_dict(metadata_dict)

        except self._s3_client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.error(f"Failed to get metadata for {checkpoint_id}: {e}")
            return None

    async def list_checkpoints(
        self,
        job_id: str,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[CheckpointMetadata]:
        """قائمة نقاط الحفظ"""
        if not self._connected:
            return []

        try:
            # Load job index
            index_key = self._get_job_index_key(job_id)

            try:
                response = await self._run_in_executor(
                    self._s3_client.get_object,
                    Bucket=self.bucket_name,
                    Key=index_key,
                )
                index = json.loads(response["Body"].read().decode())
            except Exception:
                return []

            checkpoints: list[CheckpointMetadata] = []

            for checkpoint_id in index.get("checkpoints", []):
                metadata = await self.get_metadata(checkpoint_id)
                if metadata:
                    if task_id and metadata.task_id != task_id:
                        continue

                    checkpoints.append(metadata)

                    if len(checkpoints) >= limit:
                        break

            return checkpoints

        except Exception as e:
            logger.error(f"Failed to list checkpoints for job {job_id}: {e}")
            return []

    async def checkpoint_exists(self, checkpoint_id: str) -> bool:
        """التحقق من وجود نقطة حفظ"""
        if not self._connected:
            return False

        try:
            data_key = self._get_data_key(checkpoint_id)

            await self._run_in_executor(
                self._s3_client.head_object,
                Bucket=self.bucket_name,
                Key=data_key,
            )

            return True

        except Exception:
            return False

    # =========================================================================
    # Index Management / إدارة الفهرس
    # =========================================================================

    async def _update_job_index(self, metadata: CheckpointMetadata) -> None:
        """تحديث فهرس المهمة"""
        index_key = self._get_job_index_key(metadata.job_id)

        try:
            response = await self._run_in_executor(
                self._s3_client.get_object,
                Bucket=self.bucket_name,
                Key=index_key,
            )
            index = json.loads(response["Body"].read().decode())
        except Exception:
            index = {"job_id": metadata.job_id, "checkpoints": []}

        if metadata.checkpoint_id not in index["checkpoints"]:
            index["checkpoints"].append(metadata.checkpoint_id)

        await self._run_in_executor(
            self._s3_client.put_object,
            Bucket=self.bucket_name,
            Key=index_key,
            Body=json.dumps(index).encode(),
            ContentType="application/json",
        )

    async def _remove_from_job_index(self, metadata: CheckpointMetadata) -> None:
        """إزالة من فهرس المهمة"""
        index_key = self._get_job_index_key(metadata.job_id)

        try:
            response = await self._run_in_executor(
                self._s3_client.get_object,
                Bucket=self.bucket_name,
                Key=index_key,
            )
            index = json.loads(response["Body"].read().decode())

            if metadata.checkpoint_id in index.get("checkpoints", []):
                index["checkpoints"].remove(metadata.checkpoint_id)

            await self._run_in_executor(
                self._s3_client.put_object,
                Bucket=self.bucket_name,
                Key=index_key,
                Body=json.dumps(index).encode(),
                ContentType="application/json",
            )
        except Exception:
            pass

    # =========================================================================
    # Key Helpers / مساعدات المفاتيح
    # =========================================================================

    def _get_data_key(self, checkpoint_id: str) -> str:
        """الحصول على مفتاح البيانات"""
        return f"{self.prefix}/data/{checkpoint_id}.ckpt"

    def _get_metadata_key(self, checkpoint_id: str) -> str:
        """الحصول على مفتاح البيانات الوصفية"""
        return f"{self.prefix}/metadata/{checkpoint_id}.json"

    def _get_job_index_key(self, job_id: str) -> str:
        """الحصول على مفتاح فهرس المهمة"""
        return f"{self.prefix}/index/{job_id}.json"

    # =========================================================================
    # Status / الحالة
    # =========================================================================

    def get_status(self) -> dict:
        """الحصول على حالة التخزين"""
        status = super().get_status()
        status.update(
            {
                "bucket": self.bucket_name,
                "prefix": self.prefix,
                "region": self.region,
                "encryption": self.server_side_encryption,
            }
        )
        return status
