"""
Async I/O - عمليات الإدخال/الإخراج غير المتزامنة
================================================

Async I/O Utilities
-------------------

This module provides async file I/O operations.

يوفر هذا الملف عمليات ملفات I/O غير متزامنة.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Union

logger = logging.getLogger(__name__)

# Try to import aiofiles for async file I/O
try:
    import aiofiles
    import aiofiles.os

    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False
    logger.warning("aiofiles not installed. Using thread pool fallback.")


class AsyncFileReader:
    """
    قارئ ملفات غير متزامن
    Async file reader

    يوفر واجهة موحدة لقراءة الملفات بشكل غير متزامن.
    Provides unified interface for async file reading.
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        encoding: str = "utf-8",
        chunk_size: int = 8192,
    ):
        """
        تهيئة القارئ

        Args:
            file_path: مسار الملف
            encoding: الترميز
            chunk_size: حجم القطعة للقراءة
        """
        self.file_path = Path(file_path)
        self.encoding = encoding
        self.chunk_size = chunk_size

    async def read(self) -> str:
        """قراءة الملف كاملاً"""
        if HAS_AIOFILES:
            async with aiofiles.open(self.file_path, mode="r", encoding=self.encoding) as f:
                return await f.read()
        else:
            return await self._read_with_executor()

    async def read_bytes(self) -> bytes:
        """قراءة الملف كـ bytes"""
        if HAS_AIOFILES:
            async with aiofiles.open(self.file_path, mode="rb") as f:
                return await f.read()
        else:
            return await self._read_bytes_with_executor()

    async def read_lines(self) -> list[str]:
        """قراءة الملف كقائمة أسطر"""
        if HAS_AIOFILES:
            async with aiofiles.open(self.file_path, mode="r", encoding=self.encoding) as f:
                return await f.readlines()
        else:
            content = await self._read_with_executor()
            return content.splitlines(keepends=True)

    async def read_chunks(self):
        """قراءة الملف كقطع"""
        if HAS_AIOFILES:
            async with aiofiles.open(self.file_path, mode="rb") as f:
                while True:
                    chunk = await f.read(self.chunk_size)
                    if not chunk:
                        break
                    yield chunk
        else:
            content = await self._read_bytes_with_executor()
            for i in range(0, len(content), self.chunk_size):
                yield content[i : i + self.chunk_size]

    async def _read_with_executor(self) -> str:
        """قراءة باستخدام thread pool"""
        loop = asyncio.get_event_loop()

        def _read():
            with open(self.file_path, "r", encoding=self.encoding) as f:
                return f.read()

        return await loop.run_in_executor(None, _read)

    async def _read_bytes_with_executor(self) -> bytes:
        """قراءة bytes باستخدام thread pool"""
        loop = asyncio.get_event_loop()

        def _read():
            with open(self.file_path, "rb") as f:
                return f.read()

        return await loop.run_in_executor(None, _read)


class AsyncFileWriter:
    """
    كاتب ملفات غير متزامن
    Async file writer

    يوفر واجهة موحدة لكتابة الملفات بشكل غير متزامن.
    Provides unified interface for async file writing.
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        encoding: str = "utf-8",
        create_dirs: bool = True,
    ):
        """
        تهيئة الكاتب

        Args:
            file_path: مسار الملف
            encoding: الترميز
            create_dirs: إنشاء المجلدات تلقائياً
        """
        self.file_path = Path(file_path)
        self.encoding = encoding
        self.create_dirs = create_dirs

    async def write(self, content: str) -> int:
        """كتابة نص إلى الملف"""
        await self._ensure_dir()

        if HAS_AIOFILES:
            async with aiofiles.open(self.file_path, mode="w", encoding=self.encoding) as f:
                return await f.write(content)
        else:
            return await self._write_with_executor(content)

    async def write_bytes(self, content: bytes) -> int:
        """كتابة bytes إلى الملف"""
        await self._ensure_dir()

        if HAS_AIOFILES:
            async with aiofiles.open(self.file_path, mode="wb") as f:
                return await f.write(content)
        else:
            return await self._write_bytes_with_executor(content)

    async def append(self, content: str) -> int:
        """إضافة نص إلى الملف"""
        await self._ensure_dir()

        if HAS_AIOFILES:
            async with aiofiles.open(self.file_path, mode="a", encoding=self.encoding) as f:
                return await f.write(content)
        else:
            return await self._append_with_executor(content)

    async def write_lines(self, lines: list[str]) -> None:
        """كتابة قائمة أسطر"""
        await self._ensure_dir()

        if HAS_AIOFILES:
            async with aiofiles.open(self.file_path, mode="w", encoding=self.encoding) as f:
                await f.writelines(lines)
        else:
            content = "".join(lines)
            await self._write_with_executor(content)

    async def _ensure_dir(self) -> None:
        """التأكد من وجود المجلد"""
        if self.create_dirs:
            parent = self.file_path.parent
            if not parent.exists():
                if HAS_AIOFILES:
                    await aiofiles.os.makedirs(parent, exist_ok=True)
                else:
                    parent.mkdir(parents=True, exist_ok=True)

    async def _write_with_executor(self, content: str) -> int:
        """كتابة باستخدام thread pool"""
        loop = asyncio.get_event_loop()

        def _write():
            with open(self.file_path, "w", encoding=self.encoding) as f:
                return f.write(content)

        return await loop.run_in_executor(None, _write)

    async def _write_bytes_with_executor(self, content: bytes) -> int:
        """كتابة bytes باستخدام thread pool"""
        loop = asyncio.get_event_loop()

        def _write():
            with open(self.file_path, "wb") as f:
                return f.write(content)

        return await loop.run_in_executor(None, _write)

    async def _append_with_executor(self, content: str) -> int:
        """إضافة باستخدام thread pool"""
        loop = asyncio.get_event_loop()

        def _append():
            with open(self.file_path, "a", encoding=self.encoding) as f:
                return f.write(content)

        return await loop.run_in_executor(None, _append)


# =============================================================================
# Convenience Functions / دوال مساعدة
# =============================================================================


async def async_read_file(
    file_path: Union[str, Path],
    encoding: str = "utf-8",
) -> str:
    """
    قراءة ملف نصي بشكل غير متزامن
    Async read text file
    """
    reader = AsyncFileReader(file_path, encoding=encoding)
    return await reader.read()


async def async_write_file(
    file_path: Union[str, Path],
    content: str,
    encoding: str = "utf-8",
) -> int:
    """
    كتابة ملف نصي بشكل غير متزامن
    Async write text file
    """
    writer = AsyncFileWriter(file_path, encoding=encoding)
    return await writer.write(content)


async def async_read_json(
    file_path: Union[str, Path],
    encoding: str = "utf-8",
) -> Any:
    """
    قراءة ملف JSON بشكل غير متزامن
    Async read JSON file
    """
    reader = AsyncFileReader(file_path, encoding=encoding)
    content = await reader.read()
    return json.loads(content)


async def async_write_json(
    file_path: Union[str, Path],
    data: Any,
    encoding: str = "utf-8",
    indent: int = 2,
) -> int:
    """
    كتابة ملف JSON بشكل غير متزامن
    Async write JSON file
    """
    content = json.dumps(data, indent=indent, ensure_ascii=False)
    writer = AsyncFileWriter(file_path, encoding=encoding)
    return await writer.write(content)


async def async_file_exists(file_path: Union[str, Path]) -> bool:
    """
    التحقق من وجود ملف بشكل غير متزامن
    Async check if file exists
    """
    path = Path(file_path)

    if HAS_AIOFILES:
        return await aiofiles.os.path.exists(path)
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, path.exists)


async def async_remove_file(file_path: Union[str, Path]) -> bool:
    """
    حذف ملف بشكل غير متزامن
    Async remove file
    """
    path = Path(file_path)

    try:
        if HAS_AIOFILES:
            await aiofiles.os.remove(path)
        else:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, path.unlink)
        return True
    except Exception:
        return False
