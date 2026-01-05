"""
File Transfer Module - نقل الملفات
====================================

File transfer between Master and Workers.
"""

from .chunked import ChunkedTransfer
from .manager import FileTransferManager, TransferInfo, TransferStatus

__all__ = [
    "FileTransferManager",
    "TransferInfo",
    "TransferStatus",
    "ChunkedTransfer",
]
