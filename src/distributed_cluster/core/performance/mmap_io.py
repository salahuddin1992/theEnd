"""
Memory-Mapped I/O - ملفات مخطوطة بالذاكرة
=========================================

Memory-Mapped File I/O
----------------------

This module provides memory-mapped file operations.

يوفر هذا الملف عمليات الملفات المخطوطة بالذاكرة.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import mmap
import os
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


class MemoryMappedFile:
    """
    ملف مخطوط بالذاكرة
    Memory-mapped file

    يوفر وصولاً سريعاً للملفات الكبيرة.
    Provides fast access to large files.
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        mode: str = "r",
        length: int = 0,
        offset: int = 0,
    ):
        """
        تهيئة الملف المخطوط

        Args:
            file_path: مسار الملف
            mode: وضع الوصول (r/w/rw)
            length: طول التخطيط (0 = الملف كاملاً)
            offset: موضع البداية
        """
        self.file_path = Path(file_path)
        self.mode = mode
        self.length = length
        self.offset = offset

        self._file = None
        self._mmap: Optional[mmap.mmap] = None

    def open(self) -> mmap.mmap:
        """فتح الملف المخطوط"""
        if self._mmap:
            return self._mmap

        # Determine access mode
        if self.mode == "r":
            file_mode = "rb"
            mmap_access = mmap.ACCESS_READ
        elif self.mode == "w":
            file_mode = "r+b"
            mmap_access = mmap.ACCESS_WRITE
        else:  # rw
            file_mode = "r+b"
            mmap_access = mmap.ACCESS_WRITE

        # Open file
        self._file = open(self.file_path, file_mode)

        # Create mmap
        self._mmap = mmap.mmap(
            self._file.fileno(),
            length=self.length,
            offset=self.offset,
            access=mmap_access,
        )

        logger.debug(f"Opened memory-mapped file: {self.file_path}")
        return self._mmap

    def close(self) -> None:
        """إغلاق الملف المخطوط"""
        if self._mmap:
            self._mmap.close()
            self._mmap = None

        if self._file:
            self._file.close()
            self._file = None

        logger.debug(f"Closed memory-mapped file: {self.file_path}")

    def __enter__(self) -> mmap.mmap:
        """دخول مدير السياق"""
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """خروج مدير السياق"""
        self.close()

    @property
    def data(self) -> mmap.mmap:
        """الحصول على البيانات"""
        if not self._mmap:
            self.open()
        return self._mmap

    def read(self, size: int = -1) -> bytes:
        """قراءة بيانات"""
        if not self._mmap:
            self.open()
        return self._mmap.read(size)

    def readline(self) -> bytes:
        """قراءة سطر"""
        if not self._mmap:
            self.open()
        return self._mmap.readline()

    def write(self, data: bytes) -> int:
        """كتابة بيانات"""
        if not self._mmap:
            self.open()
        return self._mmap.write(data)

    def seek(self, pos: int, whence: int = 0) -> int:
        """تحريك المؤشر"""
        if not self._mmap:
            self.open()
        return self._mmap.seek(pos, whence)

    def tell(self) -> int:
        """موضع المؤشر الحالي"""
        if not self._mmap:
            self.open()
        return self._mmap.tell()

    def flush(self) -> None:
        """مزامنة مع القرص"""
        if self._mmap:
            self._mmap.flush()

    def size(self) -> int:
        """حجم الملف"""
        if not self._mmap:
            self.open()
        return self._mmap.size()

    def find(self, sub: bytes, start: int = 0, end: int = -1) -> int:
        """البحث عن تسلسل"""
        if not self._mmap:
            self.open()
        if end == -1:
            return self._mmap.find(sub, start)
        return self._mmap.find(sub, start, end)


class MMapReader:
    """
    قارئ ملفات مخطوطة
    Memory-mapped file reader

    يوفر واجهة مبسطة لقراءة الملفات الكبيرة.
    Provides simplified interface for reading large files.
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        chunk_size: int = 1024 * 1024,  # 1 MB
    ):
        """
        تهيئة القارئ

        Args:
            file_path: مسار الملف
            chunk_size: حجم القطعة
        """
        self.file_path = Path(file_path)
        self.chunk_size = chunk_size

    async def read_all(self) -> bytes:
        """قراءة الملف كاملاً"""
        loop = asyncio.get_event_loop()

        def _read():
            with MemoryMappedFile(self.file_path, mode="r") as mm:
                return mm[:]

        return await loop.run_in_executor(None, _read)

    async def read_range(self, start: int, end: int) -> bytes:
        """قراءة نطاق محدد"""
        loop = asyncio.get_event_loop()

        def _read():
            with MemoryMappedFile(self.file_path, mode="r") as mm:
                return mm[start:end]

        return await loop.run_in_executor(None, _read)

    async def read_chunks(self):
        """قراءة الملف كقطع"""
        loop = asyncio.get_event_loop()

        def _get_chunks():
            chunks = []
            with MemoryMappedFile(self.file_path, mode="r") as mm:
                size = mm.size()
                for i in range(0, size, self.chunk_size):
                    end = min(i + self.chunk_size, size)
                    chunks.append(mm[i:end])
            return chunks

        chunks = await loop.run_in_executor(None, _get_chunks)

        for chunk in chunks:
            yield chunk

    async def search(self, pattern: bytes) -> list[int]:
        """البحث عن نمط"""
        loop = asyncio.get_event_loop()

        def _search():
            positions = []
            with MemoryMappedFile(self.file_path, mode="r") as mm:
                pos = 0
                while True:
                    pos = mm.find(pattern, pos)
                    if pos == -1:
                        break
                    positions.append(pos)
                    pos += 1
            return positions

        return await loop.run_in_executor(None, _search)


class MMapWriter:
    """
    كاتب ملفات مخطوطة
    Memory-mapped file writer

    يوفر واجهة مبسطة لكتابة الملفات الكبيرة.
    Provides simplified interface for writing large files.
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        size: int = 0,
    ):
        """
        تهيئة الكاتب

        Args:
            file_path: مسار الملف
            size: حجم الملف المبدئي
        """
        self.file_path = Path(file_path)
        self.initial_size = size

    async def create(self, size: int) -> None:
        """إنشاء ملف بحجم محدد"""
        loop = asyncio.get_event_loop()

        def _create():
            with open(self.file_path, "wb") as f:
                f.seek(size - 1)
                f.write(b"\0")

        await loop.run_in_executor(None, _create)

    async def write_at(self, offset: int, data: bytes) -> int:
        """كتابة في موضع محدد"""
        loop = asyncio.get_event_loop()

        def _write():
            # Ensure file is large enough
            file_size = os.path.getsize(self.file_path)
            if offset + len(data) > file_size:
                with open(self.file_path, "ab") as f:
                    f.seek(0, 2)  # End of file
                    needed = (offset + len(data)) - file_size
                    f.write(b"\0" * needed)

            with MemoryMappedFile(self.file_path, mode="w") as mm:
                mm.seek(offset)
                return mm.write(data)

        return await loop.run_in_executor(None, _write)

    async def replace_range(self, start: int, end: int, data: bytes) -> None:
        """استبدال نطاق"""
        loop = asyncio.get_event_loop()

        def _replace():
            with MemoryMappedFile(self.file_path, mode="w") as mm:
                mm[start:end] = data

        await loop.run_in_executor(None, _replace)

    async def append(self, data: bytes) -> int:
        """إضافة في نهاية الملف"""
        loop = asyncio.get_event_loop()

        def _append():
            with open(self.file_path, "ab") as f:
                return f.write(data)

        return await loop.run_in_executor(None, _append)
