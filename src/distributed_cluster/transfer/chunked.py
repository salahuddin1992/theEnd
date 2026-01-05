"""
Chunked Transfer - نقل مقسم
=============================

Chunked file transfer with resume support.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ChunkInfo:
    """معلومات الجزء."""
    index: int
    offset: int
    size: int
    checksum: str
    received: bool = False


@dataclass
class ChunkedTransferState:
    """حالة النقل المقسم."""
    transfer_id: str
    filename: str
    total_size: int
    chunk_size: int
    total_chunks: int
    chunks: List[ChunkInfo] = field(default_factory=list)
    file_checksum: str = ""

    def to_dict(self) -> Dict:
        return {
            "transfer_id": self.transfer_id,
            "filename": self.filename,
            "total_size": self.total_size,
            "chunk_size": self.chunk_size,
            "total_chunks": self.total_chunks,
            "chunks": [
                {
                    "index": c.index,
                    "offset": c.offset,
                    "size": c.size,
                    "checksum": c.checksum,
                    "received": c.received,
                }
                for c in self.chunks
            ],
            "file_checksum": self.file_checksum,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ChunkedTransferState":
        state = cls(
            transfer_id=data["transfer_id"],
            filename=data["filename"],
            total_size=data["total_size"],
            chunk_size=data["chunk_size"],
            total_chunks=data["total_chunks"],
            file_checksum=data.get("file_checksum", ""),
        )
        state.chunks = [
            ChunkInfo(
                index=c["index"],
                offset=c["offset"],
                size=c["size"],
                checksum=c["checksum"],
                received=c["received"],
            )
            for c in data["chunks"]
        ]
        return state


class ChunkedTransfer:
    """
    نقل ملفات مقسم.

    Features:
    - Split files into chunks
    - Resume interrupted transfers
    - Verify chunk integrity
    - Parallel chunk transfer
    """

    def __init__(
        self,
        chunk_size: int = 1024 * 1024,  # 1MB
        state_dir: Optional[Path] = None,
    ):
        self.chunk_size = chunk_size
        self.state_dir = state_dir or Path.home() / ".nebula" / "transfer_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    async def prepare_upload(
        self,
        file_path: Path,
        transfer_id: str,
    ) -> ChunkedTransferState:
        """
        تجهيز الملف للرفع.

        Args:
            file_path: مسار الملف
            transfer_id: معرف النقل

        Returns:
            ChunkedTransferState: حالة النقل
        """
        file_size = file_path.stat().st_size
        total_chunks = (file_size + self.chunk_size - 1) // self.chunk_size

        state = ChunkedTransferState(
            transfer_id=transfer_id,
            filename=file_path.name,
            total_size=file_size,
            chunk_size=self.chunk_size,
            total_chunks=total_chunks,
        )

        # Calculate chunk info
        with open(file_path, "rb") as f:
            for i in range(total_chunks):
                offset = i * self.chunk_size
                f.seek(offset)
                chunk_data = f.read(self.chunk_size)
                chunk_checksum = hashlib.md5(chunk_data, usedforsecurity=False).hexdigest()

                state.chunks.append(
                    ChunkInfo(
                        index=i,
                        offset=offset,
                        size=len(chunk_data),
                        checksum=chunk_checksum,
                    )
                )

        # Calculate file checksum
        state.file_checksum = await self._calculate_file_checksum(file_path)

        # Save state
        await self._save_state(state)

        return state

    async def read_chunk(
        self,
        file_path: Path,
        chunk_index: int,
    ) -> bytes:
        """
        قراءة جزء من الملف.

        Args:
            file_path: مسار الملف
            chunk_index: رقم الجزء

        Returns:
            bytes: بيانات الجزء
        """
        offset = chunk_index * self.chunk_size

        try:
            import aiofiles
            async with aiofiles.open(file_path, "rb") as f:
                await f.seek(offset)
                return await f.read(self.chunk_size)
        except ImportError:
            with open(file_path, "rb") as f:
                f.seek(offset)
                return f.read(self.chunk_size)

    async def write_chunk(
        self,
        file_path: Path,
        chunk_index: int,
        data: bytes,
        state: ChunkedTransferState,
    ) -> bool:
        """
        كتابة جزء في الملف.

        Args:
            file_path: مسار الملف
            chunk_index: رقم الجزء
            data: بيانات الجزء
            state: حالة النقل

        Returns:
            bool: نجاح العملية
        """
        if chunk_index >= len(state.chunks):
            return False

        chunk_info = state.chunks[chunk_index]

        # Verify checksum
        received_checksum = hashlib.md5(data, usedforsecurity=False).hexdigest()
        if received_checksum != chunk_info.checksum:
            logger.error(f"Chunk {chunk_index} checksum mismatch")
            return False

        # Write chunk
        try:
            import aiofiles
            async with aiofiles.open(file_path, "r+b") as f:
                await f.seek(chunk_info.offset)
                await f.write(data)
        except ImportError:
            # Ensure file exists and is large enough
            if not file_path.exists():
                with open(file_path, "wb") as f:
                    f.write(b"\0" * state.total_size)

            with open(file_path, "r+b") as f:
                f.seek(chunk_info.offset)
                f.write(data)

        # Mark as received
        chunk_info.received = True
        await self._save_state(state)

        return True

    def get_missing_chunks(self, state: ChunkedTransferState) -> List[int]:
        """
        الحصول على الأجزاء المفقودة.

        Args:
            state: حالة النقل

        Returns:
            List[int]: قائمة أرقام الأجزاء المفقودة
        """
        return [c.index for c in state.chunks if not c.received]

    def get_progress(self, state: ChunkedTransferState) -> float:
        """
        حساب نسبة الإكمال.

        Args:
            state: حالة النقل

        Returns:
            float: نسبة الإكمال (0-100)
        """
        if not state.chunks:
            return 0.0

        received = sum(1 for c in state.chunks if c.received)
        return (received / len(state.chunks)) * 100

    async def verify_transfer(
        self,
        file_path: Path,
        state: ChunkedTransferState,
    ) -> bool:
        """
        التحقق من صحة النقل.

        Args:
            file_path: مسار الملف
            state: حالة النقل

        Returns:
            bool: صحة النقل
        """
        # Check all chunks received
        if not all(c.received for c in state.chunks):
            return False

        # Verify file checksum
        file_checksum = await self._calculate_file_checksum(file_path)
        return file_checksum == state.file_checksum

    async def resume_transfer(self, transfer_id: str) -> Optional[ChunkedTransferState]:
        """
        استئناف نقل.

        Args:
            transfer_id: معرف النقل

        Returns:
            ChunkedTransferState: حالة النقل أو None
        """
        return await self._load_state(transfer_id)

    async def _save_state(self, state: ChunkedTransferState) -> None:
        """حفظ حالة النقل."""
        state_path = self.state_dir / f"{state.transfer_id}.json"

        try:
            import aiofiles
            async with aiofiles.open(state_path, "w") as f:
                await f.write(json.dumps(state.to_dict(), indent=2))
        except ImportError:
            with open(state_path, "w") as f:
                json.dump(state.to_dict(), f, indent=2)

    async def _load_state(self, transfer_id: str) -> Optional[ChunkedTransferState]:
        """تحميل حالة النقل."""
        state_path = self.state_dir / f"{transfer_id}.json"

        if not state_path.exists():
            return None

        try:
            import aiofiles
            async with aiofiles.open(state_path, "r") as f:
                data = json.loads(await f.read())
        except ImportError:
            with open(state_path, "r") as f:
                data = json.load(f)

        return ChunkedTransferState.from_dict(data)

    async def _calculate_file_checksum(self, file_path: Path) -> str:
        """حساب checksum الملف."""
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
