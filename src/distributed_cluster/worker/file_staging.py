"""
File Staging - تجهيز الملفات
============================

إدارة ملفات الإدخال والإخراج للـ Jobs:
- Stage input files from storage
- Collect output artifacts
- Compress and archive results
"""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import logging
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import aiofiles.os

logger = logging.getLogger(__name__)


@dataclass
class StagedFile:
    """ملف مُجهَّز."""

    source_path: str
    target_path: str
    size_bytes: int
    checksum: str
    staged_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CollectedArtifact:
    """ملف مُجمَّع (output)."""

    source_path: str
    pattern: str
    size_bytes: int
    checksum: str
    collected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StagingResult:
    """نتيجة عملية التجهيز."""

    success: bool
    staged_files: List[StagedFile] = field(default_factory=list)
    total_size_bytes: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None


@dataclass
class CollectionResult:
    """نتيجة عملية جمع الملفات."""

    success: bool
    collected_files: List[CollectedArtifact] = field(default_factory=list)
    archive_path: Optional[str] = None
    archive_size_bytes: int = 0
    total_size_bytes: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None


class FileStager:
    """
    مدير تجهيز الملفات.

    الاستخدام:
        stager = FileStager(work_dir="/tmp/jobs")

        # Stage input files
        result = await stager.stage_inputs(
            job_id="job-123",
            input_files={"data.csv": "/storage/data.csv"}
        )

        # Collect outputs
        result = await stager.collect_outputs(
            job_id="job-123",
            patterns=["*.json", "results/**/*.csv"]
        )
    """

    def __init__(
        self,
        work_dir: Path,
        storage_base: Optional[Path] = None,
        max_file_size: int = 100 * 1024 * 1024,  # 100MB
        compression: str = "gzip",  # gzip, bz2, xz, none
    ):
        self.work_dir = Path(work_dir)
        self.storage_base = Path(storage_base) if storage_base else self.work_dir / "storage"
        self.max_file_size = max_file_size
        self.compression = compression

        # Ensure directories exist
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.storage_base.mkdir(parents=True, exist_ok=True)

    def _get_job_dir(self, job_id: str) -> Path:
        """مسار مجلد الـ job."""
        return self.work_dir / job_id

    def _calculate_checksum(self, file_path: Path, algorithm: str = "sha256") -> str:
        """حساب checksum لملف."""
        hash_func = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()

    async def _calculate_checksum_async(self, file_path: Path, algorithm: str = "sha256") -> str:
        """حساب checksum لملف بشكل async."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._calculate_checksum, file_path, algorithm
        )

    async def stage_inputs(
        self,
        job_id: str,
        input_files: Dict[str, str],
        validate_checksums: bool = True,
    ) -> StagingResult:
        """
        تجهيز ملفات الإدخال للـ job.

        Args:
            job_id: معرف الـ job
            input_files: {target_name: source_path}
            validate_checksums: التحقق من checksums بعد النسخ

        Returns:
            StagingResult مع قائمة الملفات المُجهَّزة
        """
        start_time = asyncio.get_event_loop().time()
        job_dir = self._get_job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        staged_files: List[StagedFile] = []
        total_size = 0

        try:
            for target_name, source_path in input_files.items():
                source = Path(source_path)

                # Resolve from storage if relative
                if not source.is_absolute():
                    source = self.storage_base / source_path

                if not source.exists():
                    return StagingResult(
                        success=False,
                        error=f"Source file not found: {source_path}",
                        duration_seconds=asyncio.get_event_loop().time() - start_time,
                    )

                # Check file size
                file_size = source.stat().st_size
                if file_size > self.max_file_size:
                    return StagingResult(
                        success=False,
                        error=f"File too large: {source_path} ({file_size} bytes, max {self.max_file_size})",
                        duration_seconds=asyncio.get_event_loop().time() - start_time,
                    )

                # Target path
                target = job_dir / target_name
                target.parent.mkdir(parents=True, exist_ok=True)

                # Copy file
                await asyncio.get_event_loop().run_in_executor(
                    None, shutil.copy2, source, target
                )

                # Calculate checksum
                source_checksum = ""
                if validate_checksums:
                    source_checksum = await self._calculate_checksum_async(source)
                    target_checksum = await self._calculate_checksum_async(target)

                    if source_checksum != target_checksum:
                        return StagingResult(
                            success=False,
                            error=f"Checksum mismatch for {target_name}",
                            duration_seconds=asyncio.get_event_loop().time() - start_time,
                        )

                staged_files.append(StagedFile(
                    source_path=str(source),
                    target_path=str(target),
                    size_bytes=file_size,
                    checksum=source_checksum,
                ))
                total_size += file_size

                logger.debug(f"Staged {source_path} -> {target_name} ({file_size} bytes)")

            return StagingResult(
                success=True,
                staged_files=staged_files,
                total_size_bytes=total_size,
                duration_seconds=asyncio.get_event_loop().time() - start_time,
            )

        except Exception as e:
            logger.error(f"Staging error for job {job_id}: {e}")
            return StagingResult(
                success=False,
                error=str(e),
                duration_seconds=asyncio.get_event_loop().time() - start_time,
            )

    async def collect_outputs(
        self,
        job_id: str,
        patterns: List[str],
        create_archive: bool = True,
        archive_name: Optional[str] = None,
    ) -> CollectionResult:
        """
        جمع ملفات الإخراج من الـ job.

        Args:
            job_id: معرف الـ job
            patterns: أنماط glob للملفات المطلوبة
            create_archive: إنشاء أرشيف tar
            archive_name: اسم الأرشيف (اختياري)

        Returns:
            CollectionResult مع قائمة الملفات المُجمَّعة
        """
        start_time = asyncio.get_event_loop().time()
        job_dir = self._get_job_dir(job_id)

        if not job_dir.exists():
            return CollectionResult(
                success=False,
                error=f"Job directory not found: {job_id}",
                duration_seconds=asyncio.get_event_loop().time() - start_time,
            )

        collected_files: List[CollectedArtifact] = []
        total_size = 0

        try:
            # Find matching files
            for pattern in patterns:
                # Use glob to find files
                if "**" in pattern:
                    matches = list(job_dir.glob(pattern))
                else:
                    matches = list(job_dir.glob("**/" + pattern))

                for match in matches:
                    if not match.is_file():
                        continue

                    file_size = match.stat().st_size
                    checksum = await self._calculate_checksum_async(match)

                    collected_files.append(CollectedArtifact(
                        source_path=str(match.relative_to(job_dir)),
                        pattern=pattern,
                        size_bytes=file_size,
                        checksum=checksum,
                    ))
                    total_size += file_size

            # Create archive if requested
            archive_path = None
            archive_size = 0

            if create_archive and collected_files:
                archive_name = archive_name or f"{job_id}_outputs.tar"

                if self.compression == "gzip":
                    archive_name += ".gz"
                    mode = "w:gz"
                elif self.compression == "bz2":
                    archive_name += ".bz2"
                    mode = "w:bz2"
                elif self.compression == "xz":
                    archive_name += ".xz"
                    mode = "w:xz"
                else:
                    mode = "w"

                archive_path = str(self.storage_base / archive_name)

                # Create tar archive
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._create_archive,
                    archive_path,
                    mode,
                    job_dir,
                    [c.source_path for c in collected_files],
                )

                archive_size = Path(archive_path).stat().st_size

            return CollectionResult(
                success=True,
                collected_files=collected_files,
                archive_path=archive_path,
                archive_size_bytes=archive_size,
                total_size_bytes=total_size,
                duration_seconds=asyncio.get_event_loop().time() - start_time,
            )

        except Exception as e:
            logger.error(f"Collection error for job {job_id}: {e}")
            return CollectionResult(
                success=False,
                error=str(e),
                duration_seconds=asyncio.get_event_loop().time() - start_time,
            )

    def _create_archive(
        self,
        archive_path: str,
        mode: str,
        base_dir: Path,
        files: List[str],
    ) -> None:
        """إنشاء أرشيف tar."""
        with tarfile.open(archive_path, mode) as tar:
            for file_path in files:
                full_path = base_dir / file_path
                if full_path.exists():
                    tar.add(full_path, arcname=file_path)

    async def cleanup_job(self, job_id: str) -> bool:
        """حذف مجلد الـ job."""
        job_dir = self._get_job_dir(job_id)

        try:
            if job_dir.exists():
                await asyncio.get_event_loop().run_in_executor(
                    None, shutil.rmtree, job_dir
                )
                logger.debug(f"Cleaned up job directory: {job_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Cleanup error for job {job_id}: {e}")
            return False

    async def get_job_storage_usage(self, job_id: str) -> int:
        """حساب المساحة المستخدمة للـ job."""
        job_dir = self._get_job_dir(job_id)

        if not job_dir.exists():
            return 0

        total = 0
        for dirpath, _, filenames in os.walk(job_dir):
            for filename in filenames:
                file_path = Path(dirpath) / filename
                total += file_path.stat().st_size

        return total

    async def list_job_files(self, job_id: str) -> List[Dict[str, Any]]:
        """قائمة ملفات الـ job."""
        job_dir = self._get_job_dir(job_id)

        if not job_dir.exists():
            return []

        files = []
        for file_path in job_dir.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "path": str(file_path.relative_to(job_dir)),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })

        return files


# ==================== Streaming Uploads/Downloads ====================


class StreamingFileTransfer:
    """نقل ملفات بشكل متدفق (streaming)."""

    def __init__(self, chunk_size: int = 64 * 1024):  # 64KB chunks
        self.chunk_size = chunk_size

    async def stream_upload(
        self,
        reader: asyncio.StreamReader,
        target_path: Path,
        expected_size: Optional[int] = None,
    ) -> Tuple[int, str]:
        """
        استلام ملف من stream.

        Returns:
            (bytes_received, checksum)
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)
        hash_func = hashlib.sha256()
        bytes_received = 0

        async with aiofiles.open(target_path, "wb") as f:
            while True:
                chunk = await reader.read(self.chunk_size)
                if not chunk:
                    break

                await f.write(chunk)
                hash_func.update(chunk)
                bytes_received += len(chunk)

        if expected_size and bytes_received != expected_size:
            raise ValueError(
                f"Size mismatch: expected {expected_size}, received {bytes_received}"
            )

        return bytes_received, hash_func.hexdigest()

    async def stream_download(
        self,
        source_path: Path,
        writer: asyncio.StreamWriter,
    ) -> Tuple[int, str]:
        """
        إرسال ملف عبر stream.

        Returns:
            (bytes_sent, checksum)
        """
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {source_path}")

        hash_func = hashlib.sha256()
        bytes_sent = 0

        async with aiofiles.open(source_path, "rb") as f:
            while True:
                chunk = await f.read(self.chunk_size)
                if not chunk:
                    break

                writer.write(chunk)
                await writer.drain()
                hash_func.update(chunk)
                bytes_sent += len(chunk)

        return bytes_sent, hash_func.hexdigest()
