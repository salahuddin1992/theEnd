"""
Azure Blob Storage - تخزين Azure Blob
======================================

Azure Blob Storage for Checkpoints
----------------------------------

This module provides Azure Blob storage for checkpoints.

يوفر هذا الملف تخزين نقاط الحفظ على Azure Blob Storage.

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


class AzureBlobStorage(CheckpointStorage):
    """
    تخزين نقاط الحفظ على Azure Blob Storage
    Azure Blob checkpoint storage

    يخزن نقاط الحفظ في container Azure مع
    دعم التشفير والوصول المستند إلى الهوية.

    Stores checkpoints in Azure container with
    encryption and identity-based access support.
    """

    def __init__(
        self,
        container_name: str,
        connection_string: Optional[str] = None,
        account_url: Optional[str] = None,
        account_name: Optional[str] = None,
        account_key: Optional[str] = None,
        sas_token: Optional[str] = None,
        prefix: str = "checkpoints",
        config: Optional[StorageConfig] = None,
    ):
        """
        تهيئة تخزين Azure Blob

        Args:
            container_name: اسم الـ container
            connection_string: سلسلة الاتصال
            account_url: URL الحساب
            account_name: اسم الحساب
            account_key: مفتاح الحساب
            sas_token: رمز SAS
            prefix: بادئة المسار
            config: إعدادات التخزين
        """
        super().__init__(config)

        self.container_name = container_name
        self.connection_string = connection_string
        self.account_url = account_url
        self.account_name = account_name
        self.account_key = account_key
        self.sas_token = sas_token
        self.prefix = prefix.strip("/")

        # Azure clients
        self._blob_service_client = None
        self._container_client = None
        self._executor = ThreadPoolExecutor(max_workers=4)

    # =========================================================================
    # Connection / الاتصال
    # =========================================================================

    async def connect(self) -> None:
        """الاتصال بـ Azure Blob Storage"""
        try:
            from azure.storage.blob import BlobServiceClient

            # Create client based on available credentials
            if self.connection_string:
                self._blob_service_client = BlobServiceClient.from_connection_string(
                    self.connection_string
                )
            elif self.account_url:
                if self.sas_token:
                    self._blob_service_client = BlobServiceClient(
                        account_url=f"{self.account_url}?{self.sas_token}"
                    )
                elif self.account_key:
                    from azure.storage.blob import (
                        BlobServiceClient as BSC,
                    )
                    self._blob_service_client = BSC(
                        account_url=self.account_url,
                        credential=self.account_key,
                    )
                else:
                    # Try DefaultAzureCredential
                    from azure.identity import DefaultAzureCredential
                    credential = DefaultAzureCredential()
                    self._blob_service_client = BlobServiceClient(
                        account_url=self.account_url,
                        credential=credential,
                    )
            elif self.account_name and self.account_key:
                account_url = f"https://{self.account_name}.blob.core.windows.net"
                self._blob_service_client = BlobServiceClient(
                    account_url=account_url,
                    credential=self.account_key,
                )
            else:
                raise ConnectionError(
                    "Azure credentials required: connection_string, "
                    "account_url with credentials, or account_name/key"
                )

            # Get container client
            self._container_client = self._blob_service_client.get_container_client(
                self.container_name
            )

            # Create container if not exists
            await self._run_in_executor(
                self._container_client.create_container
            )

            self._connected = True
            logger.info(f"AzureBlobStorage connected to container {self.container_name}")

        except ImportError:
            raise ConnectionError(
                "azure-storage-blob required for Azure storage. "
                "Install with: pip install azure-storage-blob"
            )
        except Exception as e:
            if "ContainerAlreadyExists" not in str(e):
                raise ConnectionError(f"Failed to connect to Azure Blob: {e}")
            self._connected = True
            logger.info(f"AzureBlobStorage connected to container {self.container_name}")

    async def disconnect(self) -> None:
        """قطع الاتصال"""
        self._blob_service_client = None
        self._container_client = None
        self._connected = False
        logger.info("AzureBlobStorage disconnected")

    async def _run_in_executor(self, func, *args, **kwargs):
        """تشغيل دالة Azure في thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, lambda: func(*args, **kwargs)
        )

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
            raise WriteError("Not connected to Azure Blob Storage")

        try:
            # Save data
            data_blob = self._get_data_blob_name(checkpoint_id)
            blob_client = self._container_client.get_blob_client(data_blob)

            await self._run_in_executor(
                blob_client.upload_blob,
                data,
                overwrite=True,
                metadata={
                    "job_id": metadata.job_id,
                    "task_id": metadata.task_id or "",
                    "sequence_number": str(metadata.sequence_number),
                },
            )

            # Save metadata
            metadata_blob = self._get_metadata_blob_name(checkpoint_id)
            metadata_client = self._container_client.get_blob_client(metadata_blob)
            metadata_json = json.dumps(metadata.to_dict())

            await self._run_in_executor(
                metadata_client.upload_blob,
                metadata_json.encode(),
                overwrite=True,
                content_settings={"content_type": "application/json"},
            )

            # Update job index
            await self._update_job_index(metadata)

            logger.debug(f"Saved checkpoint {checkpoint_id} to Azure Blob")
            return True

        except Exception as e:
            logger.error(f"Failed to save checkpoint {checkpoint_id}: {e}")
            raise WriteError(f"Failed to save checkpoint to Azure Blob: {e}")

    async def load_checkpoint(self, checkpoint_id: str) -> Optional[bytes]:
        """تحميل نقطة حفظ"""
        if not self._connected:
            raise ReadError("Not connected to Azure Blob Storage")

        try:
            data_blob = self._get_data_blob_name(checkpoint_id)
            blob_client = self._container_client.get_blob_client(data_blob)

            download = await self._run_in_executor(
                blob_client.download_blob
            )

            return await self._run_in_executor(download.readall)

        except Exception as e:
            if "BlobNotFound" in str(e):
                return None
            logger.error(f"Failed to load checkpoint {checkpoint_id}: {e}")
            raise ReadError(f"Failed to load checkpoint from Azure Blob: {e}")

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """حذف نقطة حفظ"""
        if not self._connected:
            return False

        try:
            # Get metadata for index cleanup
            metadata = await self.get_metadata(checkpoint_id)

            # Delete data blob
            data_blob = self._get_data_blob_name(checkpoint_id)
            blob_client = self._container_client.get_blob_client(data_blob)
            try:
                await self._run_in_executor(blob_client.delete_blob)
            except Exception:
                pass

            # Delete metadata blob
            metadata_blob = self._get_metadata_blob_name(checkpoint_id)
            meta_client = self._container_client.get_blob_client(metadata_blob)
            try:
                await self._run_in_executor(meta_client.delete_blob)
            except Exception:
                pass

            # Update job index
            if metadata:
                await self._remove_from_job_index(metadata)

            logger.debug(f"Deleted checkpoint {checkpoint_id} from Azure Blob")
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
            metadata_blob = self._get_metadata_blob_name(checkpoint_id)
            blob_client = self._container_client.get_blob_client(metadata_blob)

            download = await self._run_in_executor(
                blob_client.download_blob
            )

            data = await self._run_in_executor(download.readall)
            metadata_dict = json.loads(data.decode())

            return CheckpointMetadata.from_dict(metadata_dict)

        except Exception as e:
            if "BlobNotFound" not in str(e):
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
            index_blob = self._get_job_index_blob_name(job_id)
            blob_client = self._container_client.get_blob_client(index_blob)

            try:
                download = await self._run_in_executor(
                    blob_client.download_blob
                )
                data = await self._run_in_executor(download.readall)
                index = json.loads(data.decode())
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
            data_blob = self._get_data_blob_name(checkpoint_id)
            blob_client = self._container_client.get_blob_client(data_blob)

            await self._run_in_executor(blob_client.get_blob_properties)
            return True

        except Exception:
            return False

    # =========================================================================
    # Index Management / إدارة الفهرس
    # =========================================================================

    async def _update_job_index(self, metadata: CheckpointMetadata) -> None:
        """تحديث فهرس المهمة"""
        index_blob = self._get_job_index_blob_name(metadata.job_id)
        blob_client = self._container_client.get_blob_client(index_blob)

        try:
            download = await self._run_in_executor(
                blob_client.download_blob
            )
            data = await self._run_in_executor(download.readall)
            index = json.loads(data.decode())
        except Exception:
            index = {"job_id": metadata.job_id, "checkpoints": []}

        if metadata.checkpoint_id not in index["checkpoints"]:
            index["checkpoints"].append(metadata.checkpoint_id)

        await self._run_in_executor(
            blob_client.upload_blob,
            json.dumps(index).encode(),
            overwrite=True,
            content_settings={"content_type": "application/json"},
        )

    async def _remove_from_job_index(self, metadata: CheckpointMetadata) -> None:
        """إزالة من فهرس المهمة"""
        index_blob = self._get_job_index_blob_name(metadata.job_id)
        blob_client = self._container_client.get_blob_client(index_blob)

        try:
            download = await self._run_in_executor(
                blob_client.download_blob
            )
            data = await self._run_in_executor(download.readall)
            index = json.loads(data.decode())

            if metadata.checkpoint_id in index.get("checkpoints", []):
                index["checkpoints"].remove(metadata.checkpoint_id)

            await self._run_in_executor(
                blob_client.upload_blob,
                json.dumps(index).encode(),
                overwrite=True,
            )
        except Exception:
            pass

    # =========================================================================
    # Blob Name Helpers / مساعدات أسماء الـ Blobs
    # =========================================================================

    def _get_data_blob_name(self, checkpoint_id: str) -> str:
        """الحصول على اسم blob البيانات"""
        return f"{self.prefix}/data/{checkpoint_id}.ckpt"

    def _get_metadata_blob_name(self, checkpoint_id: str) -> str:
        """الحصول على اسم blob البيانات الوصفية"""
        return f"{self.prefix}/metadata/{checkpoint_id}.json"

    def _get_job_index_blob_name(self, job_id: str) -> str:
        """الحصول على اسم blob فهرس المهمة"""
        return f"{self.prefix}/index/{job_id}.json"

    # =========================================================================
    # Status / الحالة
    # =========================================================================

    def get_status(self) -> dict:
        """الحصول على حالة التخزين"""
        status = super().get_status()
        status.update({
            "container": self.container_name,
            "prefix": self.prefix,
            "account": self.account_name or "connection_string",
        })
        return status
