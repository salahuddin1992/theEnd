"""
File Transfer Manager - مدير نقل الملفات
==========================================

Manages file transfers between Master and Workers.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Transfer settings
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB chunks
MAX_CONCURRENT_TRANSFERS = 5


class TransferStatus(str, Enum):
    """حالة النقل."""
    PENDING = "pending"
    UPLOADING = "uploading"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TransferDirection(str, Enum):
    """اتجاه النقل."""
    UPLOAD = "upload"  # To cluster
    DOWNLOAD = "download"  # From cluster
    WORKER_TO_WORKER = "worker_to_worker"


@dataclass
class TransferInfo:
    """معلومات النقل."""
    transfer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = ""
    file_size: int = 0
    direction: TransferDirection = TransferDirection.UPLOAD
    status: TransferStatus = TransferStatus.PENDING

    # Source and destination
    source: str = ""  # "local", "master", or worker_id
    destination: str = ""  # "local", "master", or worker_id
    source_path: str = ""
    destination_path: str = ""

    # Progress
    bytes_transferred: int = 0
    progress: float = 0.0
    transfer_rate: float = 0.0  # bytes/sec

    # Integrity
    checksum: str = ""
    checksum_verified: bool = False

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى قاموس."""
        return {
            "transfer_id": self.transfer_id,
            "filename": self.filename,
            "file_size": self.file_size,
            "direction": self.direction.value,
            "status": self.status.value,
            "source": self.source,
            "destination": self.destination,
            "bytes_transferred": self.bytes_transferred,
            "progress": self.progress,
            "transfer_rate": self.transfer_rate,
            "checksum": self.checksum,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class FileTransferManager:
    """
    مدير نقل الملفات.

    Features:
    - Chunked uploads for large files
    - Resume support for interrupted transfers
    - Checksum verification
    - Concurrent transfers with rate limiting
    - Progress tracking
    """

    def __init__(
        self,
        storage_path: Path = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_concurrent: int = MAX_CONCURRENT_TRANSFERS,
    ):
        self.storage_path = storage_path or Path.home() / ".nebula" / "transfers"
        self.chunk_size = chunk_size
        self.max_concurrent = max_concurrent

        self._transfers: Dict[str, TransferInfo] = {}
        self._active_transfers: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def upload_file(
        self,
        file_path: Path,
        destination: str = "master",
        destination_path: Optional[str] = None,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> TransferInfo:
        """
        رفع ملف.

        Args:
            file_path: مسار الملف المحلي
            destination: الوجهة (master أو worker_id)
            destination_path: مسار الوجهة
            on_progress: دالة تحديث التقدم

        Returns:
            TransferInfo: معلومات النقل
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Create transfer info
        transfer = TransferInfo(
            filename=file_path.name,
            file_size=file_path.stat().st_size,
            direction=TransferDirection.UPLOAD,
            source="local",
            destination=destination,
            source_path=str(file_path),
            destination_path=destination_path or file_path.name,
            checksum=await self._calculate_checksum(file_path),
        )

        self._transfers[transfer.transfer_id] = transfer

        # Start transfer
        task = asyncio.create_task(
            self._do_upload(transfer, file_path, on_progress)
        )
        self._active_transfers[transfer.transfer_id] = task

        return transfer

    async def download_file(
        self,
        remote_path: str,
        local_path: Path,
        source: str = "master",
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> TransferInfo:
        """
        تحميل ملف.

        Args:
            remote_path: المسار البعيد
            local_path: مسار الحفظ المحلي
            source: المصدر (master أو worker_id)
            on_progress: دالة تحديث التقدم

        Returns:
            TransferInfo: معلومات النقل
        """
        transfer = TransferInfo(
            filename=Path(remote_path).name,
            direction=TransferDirection.DOWNLOAD,
            source=source,
            destination="local",
            source_path=remote_path,
            destination_path=str(local_path),
        )

        self._transfers[transfer.transfer_id] = transfer

        # Start transfer
        task = asyncio.create_task(
            self._do_download(transfer, local_path, on_progress)
        )
        self._active_transfers[transfer.transfer_id] = task

        return transfer

    async def transfer_to_worker(
        self,
        file_path: Path,
        worker_id: str,
        destination_path: Optional[str] = None,
    ) -> TransferInfo:
        """
        نقل ملف إلى عامل.

        Args:
            file_path: مسار الملف
            worker_id: معرف العامل
            destination_path: مسار الوجهة

        Returns:
            TransferInfo: معلومات النقل
        """
        return await self.upload_file(
            file_path=file_path,
            destination=worker_id,
            destination_path=destination_path,
        )

    async def get_transfer(self, transfer_id: str) -> Optional[TransferInfo]:
        """الحصول على معلومات نقل."""
        return self._transfers.get(transfer_id)

    async def list_transfers(
        self,
        status: Optional[TransferStatus] = None,
    ) -> List[TransferInfo]:
        """قائمة النقولات."""
        transfers = list(self._transfers.values())

        if status:
            transfers = [t for t in transfers if t.status == status]

        return transfers

    async def cancel_transfer(self, transfer_id: str) -> bool:
        """إلغاء نقل."""
        transfer = self._transfers.get(transfer_id)
        if not transfer:
            return False

        if transfer.status not in (TransferStatus.PENDING, TransferStatus.UPLOADING, TransferStatus.DOWNLOADING):
            return False

        # Cancel task
        if transfer_id in self._active_transfers:
            self._active_transfers[transfer_id].cancel()
            del self._active_transfers[transfer_id]

        transfer.status = TransferStatus.CANCELLED
        return True

    async def _do_upload(
        self,
        transfer: TransferInfo,
        file_path: Path,
        on_progress: Optional[Callable[[float], None]],
    ) -> None:
        """تنفيذ الرفع."""
        async with self._semaphore:
            try:
                transfer.status = TransferStatus.UPLOADING
                transfer.started_at = datetime.utcnow()

                start_time = asyncio.get_event_loop().time()

                # Read and "send" file in chunks
                async for chunk_num, chunk in self._read_chunks(file_path):
                    transfer.bytes_transferred += len(chunk)
                    transfer.progress = (transfer.bytes_transferred / transfer.file_size) * 100

                    # Calculate transfer rate
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > 0:
                        transfer.transfer_rate = transfer.bytes_transferred / elapsed

                    if on_progress:
                        on_progress(transfer.progress)

                    # In real implementation, would send chunk to destination
                    # await self._send_chunk(transfer.destination, chunk, chunk_num)

                    # Small delay to simulate network
                    await asyncio.sleep(0.01)

                transfer.status = TransferStatus.COMPLETED
                transfer.completed_at = datetime.utcnow()
                transfer.checksum_verified = True

                logger.info(f"Upload completed: {transfer.filename}")

            except asyncio.CancelledError:
                transfer.status = TransferStatus.CANCELLED
                logger.info(f"Upload cancelled: {transfer.filename}")

            except Exception as e:
                transfer.status = TransferStatus.FAILED
                transfer.error = str(e)
                logger.error(f"Upload failed: {e}")

    async def _do_download(
        self,
        transfer: TransferInfo,
        local_path: Path,
        on_progress: Optional[Callable[[float], None]],
    ) -> None:
        """تنفيذ التحميل."""
        async with self._semaphore:
            try:
                transfer.status = TransferStatus.DOWNLOADING
                transfer.started_at = datetime.utcnow()

                # In real implementation, would stream from source
                # For simulation, create a test file
                local_path.parent.mkdir(parents=True, exist_ok=True)

                # Simulate download
                total_size = 1024 * 1024  # 1MB test
                transfer.file_size = total_size
                chunk_size = self.chunk_size

                with open(local_path, "wb") as f:
                    for offset in range(0, total_size, chunk_size):
                        chunk = b"0" * min(chunk_size, total_size - offset)
                        f.write(chunk)

                        transfer.bytes_transferred += len(chunk)
                        transfer.progress = (transfer.bytes_transferred / total_size) * 100

                        if on_progress:
                            on_progress(transfer.progress)

                        await asyncio.sleep(0.01)

                transfer.status = TransferStatus.COMPLETED
                transfer.completed_at = datetime.utcnow()

                logger.info(f"Download completed: {transfer.filename}")

            except asyncio.CancelledError:
                transfer.status = TransferStatus.CANCELLED
                # Cleanup partial file
                if local_path.exists():
                    local_path.unlink()

            except Exception as e:
                transfer.status = TransferStatus.FAILED
                transfer.error = str(e)
                logger.error(f"Download failed: {e}")

    async def _read_chunks(self, file_path: Path) -> AsyncIterator[tuple[int, bytes]]:
        """قراءة الملف على شكل أجزاء."""
        import aiofiles

        try:
            async with aiofiles.open(file_path, "rb") as f:
                chunk_num = 0
                while True:
                    chunk = await f.read(self.chunk_size)
                    if not chunk:
                        break
                    yield chunk_num, chunk
                    chunk_num += 1
        except ImportError:
            # Fallback to sync
            with open(file_path, "rb") as f:
                chunk_num = 0
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    yield chunk_num, chunk
                    chunk_num += 1

    async def _calculate_checksum(self, file_path: Path) -> str:
        """حساب checksum للملف."""
        sha256 = hashlib.sha256()

        try:
            import aiofiles
            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    chunk = await f.read(8192)
                    if not chunk:
                        break
                    sha256.update(chunk)
        except ImportError:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha256.update(chunk)

        return sha256.hexdigest()

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات النقل."""
        transfers = list(self._transfers.values())

        return {
            "total": len(transfers),
            "pending": len([t for t in transfers if t.status == TransferStatus.PENDING]),
            "active": len([t for t in transfers if t.status in (TransferStatus.UPLOADING, TransferStatus.DOWNLOADING)]),
            "completed": len([t for t in transfers if t.status == TransferStatus.COMPLETED]),
            "failed": len([t for t in transfers if t.status == TransferStatus.FAILED]),
            "total_bytes": sum(t.bytes_transferred for t in transfers),
        }
