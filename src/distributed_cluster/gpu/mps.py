# -*- coding: utf-8 -*-
"""
NVIDIA MPS (Multi-Process Service) Manager for NebulaCompute.

MPS allows multiple CUDA applications to share a single GPU,
improving utilization and reducing context switching overhead.

نظام إدارة MPS من NVIDIA لمشاركة GPU بين عدة عمليات.
"""

import asyncio
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MPSStatus(str, Enum):
    """MPS daemon status."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class MPSConfig:
    """
    MPS configuration.

    تكوين MPS.
    """

    gpu_index: int
    pipe_directory: str = "/tmp/nvidia-mps"
    log_directory: str = "/tmp/nvidia-mps-log"
    default_active_thread_percentage: int = 100
    default_pinned_device_memory_limit: Optional[str] = None  # e.g., "0=4G"
    enable_exclusive_mode: bool = True

    def to_env(self) -> Dict[str, str]:
        """Get environment variables for MPS."""
        env = {
            "CUDA_VISIBLE_DEVICES": str(self.gpu_index),
            "CUDA_MPS_PIPE_DIRECTORY": self.pipe_directory,
            "CUDA_MPS_LOG_DIRECTORY": self.log_directory,
        }

        if self.default_active_thread_percentage < 100:
            env["CUDA_MPS_ACTIVE_THREAD_PERCENTAGE"] = str(
                self.default_active_thread_percentage
            )

        if self.default_pinned_device_memory_limit:
            env["CUDA_MPS_PINNED_DEVICE_MEM_LIMIT"] = (
                self.default_pinned_device_memory_limit
            )

        return env


@dataclass
class MPSSession:
    """
    Represents an MPS client session.

    جلسة عميل MPS.
    """

    session_id: str
    job_id: str
    gpu_index: int
    active_thread_percentage: int = 100
    memory_limit_mb: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    pid: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        if self.pid is None:
            return False
        try:
            os.kill(self.pid, 0)
            return True
        except OSError:
            return False

    def get_env(self, pipe_directory: str) -> Dict[str, str]:
        """Get environment variables for this session."""
        env = {
            "CUDA_VISIBLE_DEVICES": str(self.gpu_index),
            "CUDA_MPS_PIPE_DIRECTORY": pipe_directory,
            "CUDA_MPS_ACTIVE_THREAD_PERCENTAGE": str(self.active_thread_percentage),
        }

        if self.memory_limit_mb:
            env["CUDA_MPS_PINNED_DEVICE_MEM_LIMIT"] = f"0={self.memory_limit_mb}M"

        return env


class MPSManager:
    """
    Manages NVIDIA MPS daemon and client sessions.

    مدير خدمة MPS من NVIDIA.

    Features:
    - MPS daemon lifecycle management
    - Client session tracking
    - Resource limit enforcement
    - Automatic recovery
    """

    def __init__(
        self,
        config: Optional[MPSConfig] = None,
        auto_start: bool = True,
    ):
        """
        Initialize MPS Manager.

        Args:
            config: MPS configuration
            auto_start: Automatically start MPS daemon
        """
        self.config = config or MPSConfig(gpu_index=0)
        self.auto_start = auto_start

        self._status = MPSStatus.STOPPED
        self._sessions: Dict[str, MPSSession] = {}
        self._daemon_process: Optional[subprocess.Popen] = None
        self._lock = asyncio.Lock()

        # Check for nvidia-cuda-mps-control
        self._mps_available = self._check_mps_available()

        if not self._mps_available:
            logger.warning("NVIDIA MPS tools not found in PATH")

    def _check_mps_available(self) -> bool:
        """Check if MPS tools are available."""
        return shutil.which("nvidia-cuda-mps-control") is not None

    async def initialize(self) -> bool:
        """
        Initialize MPS manager.

        Returns:
            True if initialization successful
        """
        if not self._mps_available:
            logger.error("MPS is not available on this system")
            return False

        # Create directories
        await self._ensure_directories()

        if self.auto_start:
            return await self.start_daemon()

        return True

    async def _ensure_directories(self) -> None:
        """Ensure MPS directories exist."""
        for directory in [self.config.pipe_directory, self.config.log_directory]:
            path = Path(directory)
            path.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o755)

    async def start_daemon(self) -> bool:
        """
        Start MPS daemon.

        بدء تشغيل MPS daemon.

        Returns:
            True if started successfully
        """
        async with self._lock:
            if self._status == MPSStatus.RUNNING:
                logger.info("MPS daemon already running")
                return True

            self._status = MPSStatus.STARTING
            logger.info(f"Starting MPS daemon for GPU {self.config.gpu_index}")

            try:
                # Set exclusive mode if enabled
                if self.config.enable_exclusive_mode:
                    await self._set_exclusive_mode()

                # Start control daemon
                env = os.environ.copy()
                env.update(self.config.to_env())

                # Start MPS control daemon
                await asyncio.create_subprocess_exec(
                    "nvidia-cuda-mps-control",
                    "-d",
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                # Wait briefly for daemon to start
                await asyncio.sleep(1)

                # Verify daemon is running
                if await self._is_daemon_running():
                    self._status = MPSStatus.RUNNING
                    logger.info("MPS daemon started successfully")
                    return True
                else:
                    self._status = MPSStatus.ERROR
                    logger.error("MPS daemon failed to start")
                    return False

            except Exception as e:
                self._status = MPSStatus.ERROR
                logger.error(f"Failed to start MPS daemon: {e}")
                return False

    async def _set_exclusive_mode(self) -> None:
        """Set GPU to exclusive compute mode."""
        try:
            await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "-i",
                str(self.config.gpu_index),
                "-c",
                "EXCLUSIVE_PROCESS",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception as e:
            logger.warning(f"Failed to set exclusive mode: {e}")

    async def _is_daemon_running(self) -> bool:
        """Check if MPS daemon is running."""
        try:
            env = os.environ.copy()
            env.update(self.config.to_env())

            process = await asyncio.create_subprocess_exec(
                "nvidia-cuda-mps-control",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, _ = await process.communicate(b"get_server_list\n")
            return process.returncode == 0

        except Exception:
            return False

    async def stop_daemon(self) -> bool:
        """
        Stop MPS daemon.

        إيقاف MPS daemon.

        Returns:
            True if stopped successfully
        """
        async with self._lock:
            if self._status == MPSStatus.STOPPED:
                return True

            self._status = MPSStatus.STOPPING
            logger.info("Stopping MPS daemon")

            try:
                env = os.environ.copy()
                env.update(self.config.to_env())

                # Send quit command
                process = await asyncio.create_subprocess_exec(
                    "nvidia-cuda-mps-control",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                await process.communicate(b"quit\n")

                # Wait for daemon to stop
                await asyncio.sleep(1)

                # Reset compute mode
                await asyncio.create_subprocess_exec(
                    "nvidia-smi",
                    "-i",
                    str(self.config.gpu_index),
                    "-c",
                    "DEFAULT",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )

                self._status = MPSStatus.STOPPED
                self._sessions.clear()
                logger.info("MPS daemon stopped")
                return True

            except Exception as e:
                self._status = MPSStatus.ERROR
                logger.error(f"Failed to stop MPS daemon: {e}")
                return False

    async def create_session(
        self,
        session_id: str,
        job_id: str,
        active_thread_percentage: int = 100,
        memory_limit_mb: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[MPSSession]:
        """
        Create an MPS client session.

        إنشاء جلسة عميل MPS.

        Args:
            session_id: Unique session identifier
            job_id: Associated job ID
            active_thread_percentage: GPU compute percentage (1-100)
            memory_limit_mb: Memory limit in MB
            metadata: Additional metadata

        Returns:
            Created MPSSession or None
        """
        async with self._lock:
            if self._status != MPSStatus.RUNNING:
                logger.error("Cannot create session: MPS daemon not running")
                return None

            if session_id in self._sessions:
                logger.warning(f"Session {session_id} already exists")
                return self._sessions[session_id]

            # Validate thread percentage
            active_thread_percentage = max(1, min(100, active_thread_percentage))

            # Check total thread allocation
            total_threads = sum(
                s.active_thread_percentage for s in self._sessions.values()
            )
            if total_threads + active_thread_percentage > 100:
                logger.warning(
                    f"Thread percentage exceeds 100%: "
                    f"{total_threads} + {active_thread_percentage}"
                )
                # Allow oversubscription with warning

            session = MPSSession(
                session_id=session_id,
                job_id=job_id,
                gpu_index=self.config.gpu_index,
                active_thread_percentage=active_thread_percentage,
                memory_limit_mb=memory_limit_mb,
                metadata=metadata or {},
            )

            self._sessions[session_id] = session
            logger.info(
                f"Created MPS session {session_id} for job {job_id} "
                f"({active_thread_percentage}% threads)"
            )

            return session

    async def destroy_session(self, session_id: str) -> bool:
        """
        Destroy an MPS session.

        Args:
            session_id: Session to destroy

        Returns:
            True if destroyed successfully
        """
        async with self._lock:
            if session_id not in self._sessions:
                return False

            session = self._sessions.pop(session_id)

            # Kill associated process if still running
            if session.pid:
                try:
                    os.kill(session.pid, 9)
                except OSError:
                    pass

            logger.info(f"Destroyed MPS session {session_id}")
            return True

    async def get_session(self, session_id: str) -> Optional[MPSSession]:
        """Get session by ID."""
        return self._sessions.get(session_id)

    async def get_session_env(self, session_id: str) -> Optional[Dict[str, str]]:
        """Get environment variables for a session."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return session.get_env(self.config.pipe_directory)

    async def list_sessions(self) -> List[MPSSession]:
        """List all active sessions."""
        return list(self._sessions.values())

    async def get_server_status(self) -> Dict[str, Any]:
        """
        Get MPS server status.

        الحصول على حالة خادم MPS.
        """
        status = {
            "status": self._status.value,
            "gpu_index": self.config.gpu_index,
            "sessions": len(self._sessions),
            "total_thread_percentage": sum(
                s.active_thread_percentage for s in self._sessions.values()
            ),
            "mps_available": self._mps_available,
        }

        if self._status == MPSStatus.RUNNING:
            try:
                # Get active clients from MPS control
                env = os.environ.copy()
                env.update(self.config.to_env())

                process = await asyncio.create_subprocess_exec(
                    "nvidia-cuda-mps-control",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                stdout, _ = await process.communicate(b"get_client_list\n")
                if stdout:
                    clients = stdout.decode().strip().split("\n")
                    status["active_clients"] = len([c for c in clients if c])

            except Exception as e:
                logger.warning(f"Failed to get MPS client list: {e}")

        return status

    async def cleanup_dead_sessions(self) -> List[str]:
        """
        Clean up dead sessions.

        تنظيف الجلسات الميتة.

        Returns:
            List of cleaned up session IDs
        """
        cleaned = []
        async with self._lock:
            dead_sessions = [
                session_id
                for session_id, session in self._sessions.items()
                if session.pid and not session.is_active
            ]

            for session_id in dead_sessions:
                self._sessions.pop(session_id)
                cleaned.append(session_id)

        if cleaned:
            logger.info(f"Cleaned up {len(cleaned)} dead MPS sessions")

        return cleaned

    @property
    def status(self) -> MPSStatus:
        """Get current MPS status."""
        return self._status

    @property
    def is_running(self) -> bool:
        """Check if MPS is running."""
        return self._status == MPSStatus.RUNNING

    async def shutdown(self) -> None:
        """Shutdown MPS manager."""
        await self.stop_daemon()
        logger.info("MPS Manager shutdown complete")
