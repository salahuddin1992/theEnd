"""
Data Synchronization - مزامنة البيانات
======================================

Efficient data transfer and synchronization:
- Chunked transfers for large data
- Compression support
- Resume capability
- Bandwidth optimization
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


class TransferStatus(str, Enum):
    """حالة النقل."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class DataChunk:
    """قطعة بيانات."""
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    transfer_id: str = ""
    sequence: int = 0
    data: bytes = b""
    checksum: str = ""
    compressed: bool = False
    size_bytes: int = 0

    def __post_init__(self):
        if not self.checksum:
            self.checksum = hashlib.md5(self.data).hexdigest()
        if not self.size_bytes:
            self.size_bytes = len(self.data)

    def verify(self) -> bool:
        """التحقق من صحة القطعة."""
        return hashlib.md5(self.data).hexdigest() == self.checksum

    def compress(self) -> DataChunk:
        """ضغط القطعة."""
        if self.compressed:
            return self

        compressed_data = zlib.compress(self.data)
        return DataChunk(
            chunk_id=self.chunk_id,
            transfer_id=self.transfer_id,
            sequence=self.sequence,
            data=compressed_data,
            compressed=True,
        )

    def decompress(self) -> DataChunk:
        """فك ضغط القطعة."""
        if not self.compressed:
            return self

        decompressed_data = zlib.decompress(self.data)
        return DataChunk(
            chunk_id=self.chunk_id,
            transfer_id=self.transfer_id,
            sequence=self.sequence,
            data=decompressed_data,
            compressed=False,
        )

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        import base64
        return {
            "chunk_id": self.chunk_id,
            "transfer_id": self.transfer_id,
            "sequence": self.sequence,
            "data": base64.b64encode(self.data).decode(),
            "checksum": self.checksum,
            "compressed": self.compressed,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> DataChunk:
        """إنشاء من dictionary."""
        import base64
        return cls(
            chunk_id=d.get("chunk_id", str(uuid.uuid4())),
            transfer_id=d.get("transfer_id", ""),
            sequence=d.get("sequence", 0),
            data=base64.b64decode(d.get("data", "")),
            checksum=d.get("checksum", ""),
            compressed=d.get("compressed", False),
            size_bytes=d.get("size_bytes", 0),
        )


@dataclass
class DataTransfer:
    """عملية نقل بيانات."""
    transfer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_node: str = ""
    target_node: str = ""
    status: TransferStatus = TransferStatus.PENDING
    total_chunks: int = 0
    completed_chunks: int = 0
    total_bytes: int = 0
    transferred_bytes: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def progress(self) -> float:
        """نسبة التقدم."""
        if self.total_chunks == 0:
            return 0.0
        return self.completed_chunks / self.total_chunks

    @property
    def speed_bps(self) -> float:
        """سرعة النقل (bytes/second)."""
        if not self.started_at:
            return 0.0
        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        if elapsed == 0:
            return 0.0
        return self.transferred_bytes / elapsed

    @property
    def eta_seconds(self) -> float:
        """الوقت المتبقي المقدر."""
        if self.speed_bps == 0:
            return float('inf')
        remaining = self.total_bytes - self.transferred_bytes
        return remaining / self.speed_bps

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        return {
            "transfer_id": self.transfer_id,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "status": self.status.value,
            "total_chunks": self.total_chunks,
            "completed_chunks": self.completed_chunks,
            "total_bytes": self.total_bytes,
            "transferred_bytes": self.transferred_bytes,
            "progress": self.progress,
            "speed_bps": self.speed_bps,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "metadata": self.metadata,
        }


class DataSync:
    """
    مزامنة البيانات الكبيرة.

    Handles large data synchronization with:
    - Chunked transfers
    - Compression
    - Resume support
    - Parallel transfers
    """

    def __init__(
        self,
        node_id: str,
        chunk_size: int = 1024 * 1024,  # 1MB default
        enable_compression: bool = True,
        max_parallel: int = 4,
    ):
        self.node_id = node_id
        self.chunk_size = chunk_size
        self.enable_compression = enable_compression
        self.max_parallel = max_parallel

        self._transfers: Dict[str, DataTransfer] = {}
        self._pending_chunks: Dict[str, List[DataChunk]] = {}
        self._received_chunks: Dict[str, Dict[int, DataChunk]] = {}

    # =========================================================================
    # Chunking
    # =========================================================================

    def create_chunks(
        self,
        data: bytes,
        transfer_id: Optional[str] = None,
    ) -> List[DataChunk]:
        """تقسيم البيانات إلى قطع."""
        transfer_id = transfer_id or str(uuid.uuid4())
        chunks = []

        for i in range(0, len(data), self.chunk_size):
            chunk_data = data[i:i + self.chunk_size]

            chunk = DataChunk(
                transfer_id=transfer_id,
                sequence=len(chunks),
                data=chunk_data,
            )

            if self.enable_compression:
                chunk = chunk.compress()

            chunks.append(chunk)

        return chunks

    def assemble_chunks(self, chunks: List[DataChunk]) -> bytes:
        """تجميع القطع إلى بيانات."""
        # Sort by sequence
        sorted_chunks = sorted(chunks, key=lambda c: c.sequence)

        # Decompress and join
        data_parts = []
        for chunk in sorted_chunks:
            if chunk.compressed:
                chunk = chunk.decompress()
            data_parts.append(chunk.data)

        return b"".join(data_parts)

    # =========================================================================
    # Transfer Management
    # =========================================================================

    async def start_transfer(
        self,
        data: bytes,
        target_node: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DataTransfer:
        """بدء نقل بيانات."""
        transfer_id = str(uuid.uuid4())

        transfer = DataTransfer(
            transfer_id=transfer_id,
            source_node=self.node_id,
            target_node=target_node,
            total_bytes=len(data),
            metadata=metadata or {},
            started_at=datetime.utcnow(),
        )

        # Create chunks
        chunks = self.create_chunks(data, transfer_id)
        transfer.total_chunks = len(chunks)

        self._transfers[transfer_id] = transfer
        self._pending_chunks[transfer_id] = chunks

        logger.info(f"Started transfer {transfer_id}: {len(chunks)} chunks")

        return transfer

    async def send_chunks(
        self,
        transfer_id: str,
        send_func: callable,
    ) -> bool:
        """إرسال قطع النقل."""
        transfer = self._transfers.get(transfer_id)
        if not transfer:
            return False

        chunks = self._pending_chunks.get(transfer_id, [])
        if not chunks:
            return False

        transfer.status = TransferStatus.IN_PROGRESS

        try:
            # Send chunks (with parallelism)
            semaphore = asyncio.Semaphore(self.max_parallel)

            async def send_chunk(chunk: DataChunk):
                async with semaphore:
                    await send_func(chunk)
                    transfer.completed_chunks += 1
                    transfer.transferred_bytes += chunk.size_bytes

            await asyncio.gather(*(send_chunk(c) for c in chunks))

            transfer.status = TransferStatus.COMPLETED
            transfer.completed_at = datetime.utcnow()

            # Cleanup
            del self._pending_chunks[transfer_id]

            return True

        except Exception as e:
            transfer.status = TransferStatus.FAILED
            transfer.error = str(e)
            logger.error(f"Transfer {transfer_id} failed: {e}")
            return False

    async def receive_chunk(self, chunk: DataChunk) -> bool:
        """استقبال قطعة."""
        transfer_id = chunk.transfer_id

        # Verify chunk
        if not chunk.verify():
            logger.warning(f"Chunk verification failed: {chunk.chunk_id}")
            return False

        # Store chunk
        if transfer_id not in self._received_chunks:
            self._received_chunks[transfer_id] = {}

        self._received_chunks[transfer_id][chunk.sequence] = chunk

        return True

    def get_received_data(self, transfer_id: str) -> Optional[bytes]:
        """الحصول على البيانات المستلمة."""
        chunks_dict = self._received_chunks.get(transfer_id)
        if not chunks_dict:
            return None

        chunks = list(chunks_dict.values())
        return self.assemble_chunks(chunks)

    def is_transfer_complete(
        self,
        transfer_id: str,
        expected_chunks: int,
    ) -> bool:
        """هل اكتمل النقل؟"""
        chunks = self._received_chunks.get(transfer_id, {})
        return len(chunks) >= expected_chunks

    # =========================================================================
    # Transfer Control
    # =========================================================================

    def pause_transfer(self, transfer_id: str) -> bool:
        """إيقاف نقل مؤقتاً."""
        transfer = self._transfers.get(transfer_id)
        if transfer and transfer.status == TransferStatus.IN_PROGRESS:
            transfer.status = TransferStatus.PAUSED
            return True
        return False

    def resume_transfer(self, transfer_id: str) -> bool:
        """استئناف نقل."""
        transfer = self._transfers.get(transfer_id)
        if transfer and transfer.status == TransferStatus.PAUSED:
            transfer.status = TransferStatus.IN_PROGRESS
            return True
        return False

    def cancel_transfer(self, transfer_id: str) -> bool:
        """إلغاء نقل."""
        transfer = self._transfers.get(transfer_id)
        if transfer:
            transfer.status = TransferStatus.CANCELLED
            # Cleanup
            self._pending_chunks.pop(transfer_id, None)
            self._received_chunks.pop(transfer_id, None)
            return True
        return False

    def get_missing_chunks(
        self,
        transfer_id: str,
        total_chunks: int,
    ) -> List[int]:
        """الحصول على القطع المفقودة."""
        received = self._received_chunks.get(transfer_id, {})
        received_sequences = set(received.keys())
        all_sequences = set(range(total_chunks))
        return sorted(all_sequences - received_sequences)

    # =========================================================================
    # Status & Info
    # =========================================================================

    def get_transfer(self, transfer_id: str) -> Optional[DataTransfer]:
        """الحصول على معلومات نقل."""
        return self._transfers.get(transfer_id)

    def get_active_transfers(self) -> List[DataTransfer]:
        """الحصول على عمليات النقل النشطة."""
        return [
            t for t in self._transfers.values()
            if t.status in [TransferStatus.PENDING, TransferStatus.IN_PROGRESS]
        ]

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات النقل."""
        transfers = list(self._transfers.values())
        return {
            "total_transfers": len(transfers),
            "completed": sum(1 for t in transfers if t.status == TransferStatus.COMPLETED),
            "failed": sum(1 for t in transfers if t.status == TransferStatus.FAILED),
            "in_progress": sum(1 for t in transfers if t.status == TransferStatus.IN_PROGRESS),
            "total_bytes_sent": sum(t.transferred_bytes for t in transfers if t.source_node == self.node_id),
            "pending_chunks": sum(len(c) for c in self._pending_chunks.values()),
        }

    def cleanup_completed(self, max_age_hours: int = 24) -> int:
        """تنظيف عمليات النقل القديمة."""
        cutoff = datetime.utcnow()
        from datetime import timedelta
        cutoff = cutoff - timedelta(hours=max_age_hours)

        to_remove = []
        for transfer_id, transfer in self._transfers.items():
            if transfer.status in [TransferStatus.COMPLETED, TransferStatus.FAILED, TransferStatus.CANCELLED]:
                if transfer.completed_at and transfer.completed_at < cutoff:
                    to_remove.append(transfer_id)

        for transfer_id in to_remove:
            del self._transfers[transfer_id]
            self._received_chunks.pop(transfer_id, None)

        return len(to_remove)


# ============================================================================
# Streaming Support
# ============================================================================

async def stream_data(
    data: bytes,
    chunk_size: int = 1024 * 1024,
) -> AsyncIterator[DataChunk]:
    """تدفق البيانات كقطع."""
    transfer_id = str(uuid.uuid4())

    for i, offset in enumerate(range(0, len(data), chunk_size)):
        chunk_data = data[offset:offset + chunk_size]

        yield DataChunk(
            transfer_id=transfer_id,
            sequence=i,
            data=chunk_data,
        )


async def collect_stream(
    stream: AsyncIterator[DataChunk],
) -> bytes:
    """تجميع تدفق البيانات."""
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return b"".join(c.data for c in sorted(chunks, key=lambda x: x.sequence))
