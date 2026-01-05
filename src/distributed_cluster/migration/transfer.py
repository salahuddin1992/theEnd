# -*- coding: utf-8 -*-
"""
State Transfer for NebulaCompute Live Migration.

Handles the transfer of process state between workers
during live migration.

نقل حالة العملية بين Workers.
"""

import asyncio
import hashlib
import logging
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class TransferProtocol(str, Enum):
    """Transfer protocol."""

    TCP = "tcp"  # Standard TCP
    RDMA = "rdma"  # Remote Direct Memory Access
    RSYNC = "rsync"  # Rsync-based delta transfer
    MULTICAST = "multicast"  # Multicast for multiple targets
    ZEROCOPY = "zerocopy"  # Zero-copy transfer


class TransferStatus(str, Enum):
    """Transfer status."""

    PENDING = "pending"
    CONNECTING = "connecting"
    TRANSFERRING = "transferring"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CompressionType(str, Enum):
    """Compression type."""

    NONE = "none"
    LZ4 = "lz4"
    ZSTD = "zstd"
    GZIP = "gzip"


@dataclass
class TransferChunk:
    """
    Transfer chunk.

    جزء من البيانات المنقولة.
    """

    chunk_id: int
    offset: int
    size: int
    data: bytes
    checksum: str
    is_last: bool = False


@dataclass
class TransferProgress:
    """
    Transfer progress.

    تقدم النقل.
    """

    bytes_sent: int = 0
    bytes_received: int = 0
    bytes_total: int = 0
    chunks_sent: int = 0
    chunks_received: int = 0
    chunks_total: int = 0
    current_rate_mbps: float = 0.0
    average_rate_mbps: float = 0.0
    eta_seconds: float = 0.0

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.bytes_total == 0:
            return 0.0
        return (self.bytes_sent / self.bytes_total) * 100


@dataclass
class TransferSession:
    """
    Transfer session.

    جلسة نقل.
    """

    session_id: str
    source_host: str
    target_host: str
    protocol: TransferProtocol
    status: TransferStatus = TransferStatus.PENDING
    progress: TransferProgress = field(default_factory=TransferProgress)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        """Calculate transfer duration."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "source_host": self.source_host,
            "target_host": self.target_host,
            "protocol": self.protocol.value,
            "status": self.status.value,
            "progress": {
                "bytes_sent": self.progress.bytes_sent,
                "bytes_total": self.progress.bytes_total,
                "progress_percent": self.progress.progress_percent,
                "current_rate_mbps": self.progress.current_rate_mbps,
                "eta_seconds": self.progress.eta_seconds,
            },
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
        }


class StateTransfer:
    """
    Handles state transfer between workers.

    معالج نقل الحالة بين Workers.

    Features:
    - Chunked transfer with progress tracking
    - Multiple transfer protocols
    - Compression and encryption
    - Bandwidth throttling
    - Delta transfer for incremental updates
    - Checksum verification
    """

    DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB chunks
    DEFAULT_PORT = 9876

    def __init__(
        self,
        protocol: TransferProtocol = TransferProtocol.TCP,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        compression: CompressionType = CompressionType.LZ4,
        enable_encryption: bool = False,
        encryption_key: Optional[bytes] = None,
        bandwidth_limit_mbps: Optional[int] = None,
        verify_checksums: bool = True,
        max_retries: int = 3,
    ):
        """
        Initialize State Transfer.

        Args:
            protocol: Transfer protocol to use
            chunk_size: Size of transfer chunks
            compression: Compression type
            enable_encryption: Enable encryption
            encryption_key: Encryption key
            bandwidth_limit_mbps: Bandwidth limit
            verify_checksums: Verify chunk checksums
            max_retries: Maximum retry attempts
        """
        self.protocol = protocol
        self.chunk_size = chunk_size
        self.compression = compression
        self.enable_encryption = enable_encryption
        self.encryption_key = encryption_key
        self.bandwidth_limit_mbps = bandwidth_limit_mbps
        self.verify_checksums = verify_checksums
        self.max_retries = max_retries

        # Active sessions
        self._sessions: Dict[str, TransferSession] = {}
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "total_transfers": 0,
            "successful_transfers": 0,
            "failed_transfers": 0,
            "total_bytes_transferred": 0,
            "total_transfer_time_seconds": 0.0,
        }

    async def send_file(
        self,
        session_id: str,
        file_path: str,
        target_host: str,
        target_port: int = DEFAULT_PORT,
        target_path: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> TransferSession:
        """
        Send a file to target host.

        إرسال ملف لـ Worker آخر.

        Args:
            session_id: Unique session ID
            file_path: Path to file to send
            target_host: Target host address
            target_port: Target port
            target_path: Path on target (optional)
            progress_callback: Progress callback function

        Returns:
            TransferSession object
        """
        source_path = Path(file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = source_path.stat().st_size

        session = TransferSession(
            session_id=session_id,
            source_host="localhost",
            target_host=target_host,
            protocol=self.protocol,
            progress=TransferProgress(bytes_total=file_size),
        )

        self._sessions[session_id] = session
        self._stats["total_transfers"] += 1

        logger.info(
            f"Starting file transfer {session_id}: "
            f"{file_path} -> {target_host}:{target_port}"
        )

        try:
            session.status = TransferStatus.CONNECTING
            session.started_at = datetime.now(timezone.utc)

            # Connect to target
            reader, writer = await asyncio.open_connection(
                target_host, target_port
            )

            session.status = TransferStatus.TRANSFERRING

            # Send metadata
            metadata = {
                "session_id": session_id,
                "file_name": source_path.name,
                "file_size": file_size,
                "target_path": target_path or source_path.name,
                "compression": self.compression.value,
                "chunk_size": self.chunk_size,
            }

            await self._send_metadata(writer, metadata)

            # Send file in chunks
            start_time = time.monotonic()
            bytes_sent_window = 0
            window_start = start_time

            with open(source_path, "rb") as f:
                chunk_id = 0
                while True:
                    data = f.read(self.chunk_size)
                    if not data:
                        break

                    # Compress if enabled
                    if self.compression != CompressionType.NONE:
                        data = self._compress(data)

                    # Create chunk
                    chunk = TransferChunk(
                        chunk_id=chunk_id,
                        offset=chunk_id * self.chunk_size,
                        size=len(data),
                        data=data,
                        # nosec B324 - MD5 used for data integrity check, not security
                        checksum=hashlib.md5(data, usedforsecurity=False).hexdigest(),
                        is_last=len(data) < self.chunk_size,
                    )

                    # Send chunk
                    await self._send_chunk(writer, chunk)

                    # Update progress
                    session.progress.bytes_sent += len(data)
                    session.progress.chunks_sent += 1
                    bytes_sent_window += len(data)

                    # Calculate rate
                    elapsed = time.monotonic() - window_start
                    if elapsed >= 1.0:
                        session.progress.current_rate_mbps = (
                            bytes_sent_window * 8 / 1_000_000
                        )
                        bytes_sent_window = 0
                        window_start = time.monotonic()

                    # Apply bandwidth limit
                    if self.bandwidth_limit_mbps:
                        await self._throttle(
                            session.progress.bytes_sent,
                            start_time,
                            self.bandwidth_limit_mbps,
                        )

                    # Progress callback
                    if progress_callback:
                        await self._safe_callback(progress_callback, session)

                    chunk_id += 1

            # Wait for acknowledgment
            session.status = TransferStatus.VERIFYING
            ack = await self._receive_ack(reader)

            if not ack.get("success"):
                raise RuntimeError(f"Transfer failed: {ack.get('error')}")

            # Complete
            session.status = TransferStatus.COMPLETED
            session.completed_at = datetime.now(timezone.utc)

            total_time = time.monotonic() - start_time
            session.progress.average_rate_mbps = (
                file_size * 8 / (total_time * 1_000_000)
            )

            self._stats["successful_transfers"] += 1
            self._stats["total_bytes_transferred"] += file_size
            self._stats["total_transfer_time_seconds"] += total_time

            logger.info(
                f"Transfer {session_id} completed: "
                f"{file_size / (1024 * 1024):.1f}MB in {total_time:.1f}s "
                f"({session.progress.average_rate_mbps:.1f} Mbps)"
            )

            writer.close()
            await writer.wait_closed()

            return session

        except Exception as e:
            session.status = TransferStatus.FAILED
            session.error_message = str(e)
            self._stats["failed_transfers"] += 1
            logger.error(f"Transfer {session_id} failed: {e}")
            raise

    async def receive_file(
        self,
        port: int = DEFAULT_PORT,
        save_dir: str = "/tmp",
        on_complete: Optional[Callable] = None,
    ) -> None:
        """
        Start receiver server.

        بدء خادم استقبال الملفات.
        """
        server = await asyncio.start_server(
            lambda r, w: self._handle_incoming(r, w, save_dir, on_complete),
            "0.0.0.0",
            port,
        )

        logger.info(f"Transfer receiver listening on port {port}")

        async with server:
            await server.serve_forever()

    async def _handle_incoming(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        save_dir: str,
        on_complete: Optional[Callable],
    ) -> None:
        """Handle incoming transfer connection."""
        try:
            # Receive metadata
            metadata = await self._receive_metadata(reader)
            session_id = metadata["session_id"]
            file_name = metadata["file_name"]
            file_size = metadata["file_size"]
            target_path = metadata.get("target_path", file_name)

            logger.info(f"Receiving transfer {session_id}: {file_name}")

            # Create session
            session = TransferSession(
                session_id=session_id,
                source_host=writer.get_extra_info("peername")[0],
                target_host="localhost",
                protocol=self.protocol,
                status=TransferStatus.TRANSFERRING,
                progress=TransferProgress(bytes_total=file_size),
            )
            session.started_at = datetime.now(timezone.utc)

            # Prepare output file
            output_path = Path(save_dir) / target_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Receive chunks
            with open(output_path, "wb") as f:
                while True:
                    chunk = await self._receive_chunk(reader)
                    if chunk is None:
                        break

                    # Verify checksum
                    if self.verify_checksums:
                        # nosec B324 - MD5 used for data integrity check, not security
                        calculated = hashlib.md5(chunk.data, usedforsecurity=False).hexdigest()
                        if calculated != chunk.checksum:
                            raise RuntimeError(
                                f"Checksum mismatch for chunk {chunk.chunk_id}"
                            )

                    # Decompress if needed
                    data = chunk.data
                    if metadata.get("compression") != "none":
                        data = self._decompress(
                            data, CompressionType(metadata["compression"])
                        )

                    f.write(data)

                    session.progress.bytes_received += len(data)
                    session.progress.chunks_received += 1

                    if chunk.is_last:
                        break

            # Send acknowledgment
            session.status = TransferStatus.COMPLETED
            session.completed_at = datetime.now(timezone.utc)

            await self._send_ack(writer, {"success": True})

            logger.info(f"Transfer {session_id} received successfully")

            if on_complete:
                await self._safe_callback(on_complete, session, str(output_path))

        except Exception as e:
            logger.error(f"Error receiving transfer: {e}")
            await self._send_ack(writer, {"success": False, "error": str(e)})

        finally:
            writer.close()
            await writer.wait_closed()

    async def send_memory_pages(
        self,
        session_id: str,
        pages: AsyncIterator[Tuple[int, bytes]],
        target_host: str,
        target_port: int = DEFAULT_PORT,
        total_pages: int = 0,
        progress_callback: Optional[Callable] = None,
    ) -> TransferSession:
        """
        Send memory pages for live migration.

        إرسال صفحات الذاكرة للنقل الحي.

        Args:
            session_id: Session ID
            pages: Async iterator of (page_number, page_data)
            target_host: Target host
            target_port: Target port
            total_pages: Total number of pages
            progress_callback: Progress callback

        Returns:
            TransferSession object
        """
        page_size = 4096  # Standard page size

        session = TransferSession(
            session_id=session_id,
            source_host="localhost",
            target_host=target_host,
            protocol=self.protocol,
            progress=TransferProgress(
                bytes_total=total_pages * page_size,
                chunks_total=total_pages,
            ),
        )

        self._sessions[session_id] = session
        session.status = TransferStatus.TRANSFERRING
        session.started_at = datetime.now(timezone.utc)

        try:
            reader, writer = await asyncio.open_connection(
                target_host, target_port
            )

            # Send header
            header = {
                "session_id": session_id,
                "type": "memory_pages",
                "total_pages": total_pages,
                "page_size": page_size,
            }
            await self._send_metadata(writer, header)

            # Send pages
            async for page_num, page_data in pages:
                # Pack page header + data
                header = struct.pack("!QI", page_num, len(page_data))
                writer.write(header + page_data)
                await writer.drain()

                session.progress.bytes_sent += len(page_data)
                session.progress.chunks_sent += 1

                if progress_callback:
                    await self._safe_callback(progress_callback, session)

            # Send end marker
            writer.write(struct.pack("!QI", 0xFFFFFFFFFFFFFFFF, 0))
            await writer.drain()

            # Wait for ack
            session.status = TransferStatus.VERIFYING
            ack = await self._receive_ack(reader)

            if ack.get("success"):
                session.status = TransferStatus.COMPLETED
            else:
                session.status = TransferStatus.FAILED
                session.error_message = ack.get("error")

            session.completed_at = datetime.now(timezone.utc)

            writer.close()
            await writer.wait_closed()

            return session

        except Exception as e:
            session.status = TransferStatus.FAILED
            session.error_message = str(e)
            raise

    def _compress(self, data: bytes) -> bytes:
        """Compress data."""
        if self.compression == CompressionType.LZ4:
            try:
                import lz4.frame

                return lz4.frame.compress(data)
            except ImportError:
                pass
        elif self.compression == CompressionType.ZSTD:
            try:
                import zstandard

                cctx = zstandard.ZstdCompressor()
                return cctx.compress(data)
            except ImportError:
                pass
        elif self.compression == CompressionType.GZIP:
            import gzip

            return gzip.compress(data)

        return data

    def _decompress(self, data: bytes, compression: CompressionType) -> bytes:
        """Decompress data."""
        if compression == CompressionType.LZ4:
            try:
                import lz4.frame

                return lz4.frame.decompress(data)
            except ImportError:
                pass
        elif compression == CompressionType.ZSTD:
            try:
                import zstandard

                dctx = zstandard.ZstdDecompressor()
                return dctx.decompress(data)
            except ImportError:
                pass
        elif compression == CompressionType.GZIP:
            import gzip

            return gzip.decompress(data)

        return data

    async def _send_metadata(
        self,
        writer: asyncio.StreamWriter,
        metadata: Dict[str, Any],
    ) -> None:
        """Send metadata header."""
        import json

        data = json.dumps(metadata).encode()
        header = struct.pack("!I", len(data))
        writer.write(header + data)
        await writer.drain()

    async def _receive_metadata(
        self,
        reader: asyncio.StreamReader,
    ) -> Dict[str, Any]:
        """Receive metadata header."""
        import json

        header = await reader.readexactly(4)
        length = struct.unpack("!I", header)[0]
        data = await reader.readexactly(length)
        return json.loads(data.decode())

    async def _send_chunk(
        self,
        writer: asyncio.StreamWriter,
        chunk: TransferChunk,
    ) -> None:
        """Send a chunk."""
        # Chunk header: chunk_id (8), offset (8), size (4), checksum (32), is_last (1)
        header = struct.pack(
            "!QQI32s?",
            chunk.chunk_id,
            chunk.offset,
            chunk.size,
            chunk.checksum.encode(),
            chunk.is_last,
        )
        writer.write(header + chunk.data)
        await writer.drain()

    async def _receive_chunk(
        self,
        reader: asyncio.StreamReader,
    ) -> Optional[TransferChunk]:
        """Receive a chunk."""
        try:
            header = await reader.readexactly(53)  # 8 + 8 + 4 + 32 + 1
            chunk_id, offset, size, checksum, is_last = struct.unpack(
                "!QQI32s?", header
            )

            if size == 0:
                return None

            data = await reader.readexactly(size)

            return TransferChunk(
                chunk_id=chunk_id,
                offset=offset,
                size=size,
                data=data,
                checksum=checksum.decode().strip("\x00"),
                is_last=is_last,
            )
        except asyncio.IncompleteReadError:
            return None

    async def _send_ack(
        self,
        writer: asyncio.StreamWriter,
        ack: Dict[str, Any],
    ) -> None:
        """Send acknowledgment."""
        await self._send_metadata(writer, ack)

    async def _receive_ack(
        self,
        reader: asyncio.StreamReader,
    ) -> Dict[str, Any]:
        """Receive acknowledgment."""
        return await self._receive_metadata(reader)

    async def _throttle(
        self,
        bytes_sent: int,
        start_time: float,
        limit_mbps: int,
    ) -> None:
        """Apply bandwidth throttling."""
        elapsed = time.monotonic() - start_time
        expected_time = (bytes_sent * 8) / (limit_mbps * 1_000_000)

        if expected_time > elapsed:
            await asyncio.sleep(expected_time - elapsed)

    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Callback error: {e}")

    async def get_session(self, session_id: str) -> Optional[TransferSession]:
        """Get transfer session."""
        return self._sessions.get(session_id)

    async def cancel_transfer(self, session_id: str) -> bool:
        """Cancel a transfer."""
        session = self._sessions.get(session_id)
        if session and session.status == TransferStatus.TRANSFERRING:
            session.status = TransferStatus.CANCELLED
            return True
        return False

    async def get_statistics(self) -> Dict[str, Any]:
        """Get transfer statistics."""
        return {
            **self._stats,
            "active_transfers": len(
                [s for s in self._sessions.values() if s.status == TransferStatus.TRANSFERRING]
            ),
            "protocol": self.protocol.value,
            "compression": self.compression.value,
            "chunk_size": self.chunk_size,
        }
