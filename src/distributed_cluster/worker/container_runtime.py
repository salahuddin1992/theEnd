"""
Container Runtime - مدير الحاويات
==================================

واجهة موحدة لتشغيل الحاويات:
- Docker
- containerd (مستقبلاً)
- Podman (مستقبلاً)

ميزات:
- Resource limits (CPU, Memory, GPU)
- Network isolation
- Volume mounts
- Log streaming
- Health monitoring
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


class ContainerState(str, Enum):
    """حالة الحاوية."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    DEAD = "dead"
    UNKNOWN = "unknown"


class NetworkMode(str, Enum):
    """وضع الشبكة."""

    NONE = "none"
    BRIDGE = "bridge"
    HOST = "host"
    CUSTOM = "custom"


@dataclass
class ContainerConfig:
    """إعدادات الحاوية."""

    image: str
    command: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    entrypoint: Optional[List[str]] = None
    working_dir: str = "/workspace"
    user: Optional[str] = None

    # Environment
    environment: Dict[str, str] = field(default_factory=dict)

    # Resource limits
    cpu_cores: float = 1.0
    memory_mb: int = 512
    memory_swap_mb: int = -1  # -1 = same as memory, 0 = unlimited
    gpu_count: int = 0
    gpu_device_ids: List[str] = field(default_factory=list)

    # Volumes
    volumes: Dict[str, str] = field(default_factory=dict)  # host_path -> container_path
    read_only_volumes: Dict[str, str] = field(default_factory=dict)

    # Network
    network_mode: NetworkMode = NetworkMode.BRIDGE
    custom_network: Optional[str] = None
    ports: Dict[int, int] = field(default_factory=dict)  # container_port -> host_port
    dns: List[str] = field(default_factory=list)
    extra_hosts: Dict[str, str] = field(default_factory=dict)

    # Security
    privileged: bool = False
    read_only_rootfs: bool = False
    capabilities_add: List[str] = field(default_factory=list)
    capabilities_drop: List[str] = field(default_factory=list)
    security_opt: List[str] = field(default_factory=list)

    # Limits
    timeout_seconds: int = 3600
    pids_limit: int = 1000
    ulimits: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Labels
    labels: Dict[str, str] = field(default_factory=dict)

    # Health check
    healthcheck_cmd: Optional[List[str]] = None
    healthcheck_interval_seconds: int = 30
    healthcheck_timeout_seconds: int = 10
    healthcheck_retries: int = 3


@dataclass
class ContainerStats:
    """إحصائيات الحاوية."""

    cpu_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_limit_mb: float = 0.0
    memory_percent: float = 0.0
    network_rx_bytes: int = 0
    network_tx_bytes: int = 0
    block_read_bytes: int = 0
    block_write_bytes: int = 0
    pids: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ContainerInfo:
    """معلومات الحاوية."""

    container_id: str
    name: str
    image: str
    state: ContainerState
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    pid: Optional[int] = None
    ports: Dict[int, int] = field(default_factory=dict)


@dataclass
class ContainerResult:
    """نتيجة تشغيل الحاوية."""

    container_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    execution_time_seconds: float = 0.0
    peak_memory_mb: float = 0.0
    error_message: Optional[str] = None


class ContainerRuntime(ABC):
    """واجهة مجردة لـ Container Runtime."""

    @abstractmethod
    async def pull_image(self, image: str) -> bool:
        """تحميل صورة."""
        pass

    @abstractmethod
    async def create_container(self, config: ContainerConfig, name: Optional[str] = None) -> str:
        """إنشاء حاوية (بدون تشغيلها)."""
        pass

    @abstractmethod
    async def start_container(self, container_id: str) -> bool:
        """بدء تشغيل حاوية."""
        pass

    @abstractmethod
    async def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        """إيقاف حاوية."""
        pass

    @abstractmethod
    async def kill_container(self, container_id: str, signal: str = "SIGKILL") -> bool:
        """قتل حاوية."""
        pass

    @abstractmethod
    async def remove_container(self, container_id: str, force: bool = False) -> bool:
        """حذف حاوية."""
        pass

    @abstractmethod
    async def get_container_info(self, container_id: str) -> Optional[ContainerInfo]:
        """الحصول على معلومات الحاوية."""
        pass

    @abstractmethod
    async def get_container_stats(self, container_id: str) -> Optional[ContainerStats]:
        """الحصول على إحصائيات الحاوية."""
        pass

    @abstractmethod
    async def get_container_logs(
        self,
        container_id: str,
        stdout: bool = True,
        stderr: bool = True,
        tail: Optional[int] = None,
    ) -> str:
        """الحصول على logs الحاوية."""
        pass

    @abstractmethod
    async def wait_container(self, container_id: str, timeout: Optional[int] = None) -> int:
        """انتظار انتهاء الحاوية."""
        pass

    @abstractmethod
    async def run_container(self, config: ContainerConfig, name: Optional[str] = None) -> ContainerResult:
        """تشغيل حاوية وانتظار انتهائها."""
        pass

    @abstractmethod
    async def stream_logs(
        self,
        container_id: str,
        stdout: bool = True,
        stderr: bool = True,
    ) -> AsyncIterator[str]:
        """بث logs الحاوية."""
        pass


class DockerRuntime(ContainerRuntime):
    """
    Docker Container Runtime.

    يستخدم Docker SDK لـ Python.
    """

    def __init__(self):
        self._client = None
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        """تهيئة Docker client."""
        try:
            import docker

            self._client = docker.from_env()
            self._client.ping()
            self._available = True
            logger.info("Docker runtime initialized")
        except Exception as e:
            logger.warning(f"Docker not available: {e}")
            self._available = False

    @property
    def is_available(self) -> bool:
        """هل Docker متاح؟"""
        return self._available

    async def pull_image(self, image: str) -> bool:
        """تحميل صورة Docker."""
        if not self._available:
            return False

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._client.images.pull, image)
            logger.info(f"Pulled image: {image}")
            return True
        except Exception as e:
            logger.error(f"Failed to pull image {image}: {e}")
            return False

    async def create_container(self, config: ContainerConfig, name: Optional[str] = None) -> str:
        """إنشاء حاوية Docker."""
        if not self._available:
            raise RuntimeError("Docker not available")

        # Build container configuration
        container_config = self._build_docker_config(config)

        loop = asyncio.get_running_loop()
        container = await loop.run_in_executor(
            None,
            lambda: self._client.containers.create(
                image=config.image,
                name=name,
                **container_config,
            ),
        )

        logger.info(f"Created container: {container.id[:12]}")
        return container.id

    async def start_container(self, container_id: str) -> bool:
        """بدء تشغيل حاوية."""
        if not self._available:
            return False

        try:
            container = self._client.containers.get(container_id)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, container.start)
            logger.info(f"Started container: {container_id[:12]}")
            return True
        except Exception as e:
            logger.error(f"Failed to start container {container_id[:12]}: {e}")
            return False

    async def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        """إيقاف حاوية."""
        if not self._available:
            return False

        try:
            container = self._client.containers.get(container_id)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: container.stop(timeout=timeout))
            logger.info(f"Stopped container: {container_id[:12]}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop container {container_id[:12]}: {e}")
            return False

    async def kill_container(self, container_id: str, signal: str = "SIGKILL") -> bool:
        """قتل حاوية."""
        if not self._available:
            return False

        try:
            container = self._client.containers.get(container_id)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: container.kill(signal=signal))
            logger.info(f"Killed container: {container_id[:12]}")
            return True
        except Exception as e:
            logger.error(f"Failed to kill container {container_id[:12]}: {e}")
            return False

    async def remove_container(self, container_id: str, force: bool = False) -> bool:
        """حذف حاوية."""
        if not self._available:
            return False

        try:
            container = self._client.containers.get(container_id)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: container.remove(force=force))
            logger.info(f"Removed container: {container_id[:12]}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove container {container_id[:12]}: {e}")
            return False

    async def get_container_info(self, container_id: str) -> Optional[ContainerInfo]:
        """الحصول على معلومات الحاوية."""
        if not self._available:
            return None

        try:
            container = self._client.containers.get(container_id)
            container.reload()

            attrs = container.attrs
            state = attrs.get("State", {})

            # Parse state
            if state.get("Running"):
                container_state = ContainerState.RUNNING
            elif state.get("Paused"):
                container_state = ContainerState.PAUSED
            elif state.get("Dead"):
                container_state = ContainerState.DEAD
            elif state.get("Status") == "created":
                container_state = ContainerState.CREATED
            else:
                container_state = ContainerState.STOPPED

            return ContainerInfo(
                container_id=container.id,
                name=container.name,
                image=attrs.get("Config", {}).get("Image", ""),
                state=container_state,
                created_at=self._parse_datetime(attrs.get("Created")),
                started_at=self._parse_datetime(state.get("StartedAt")),
                finished_at=self._parse_datetime(state.get("FinishedAt")),
                exit_code=state.get("ExitCode"),
                error=state.get("Error"),
                pid=state.get("Pid"),
            )
        except Exception as e:
            logger.error(f"Failed to get container info: {e}")
            return None

    async def get_container_stats(self, container_id: str) -> Optional[ContainerStats]:
        """الحصول على إحصائيات الحاوية."""
        if not self._available:
            return None

        try:
            container = self._client.containers.get(container_id)
            loop = asyncio.get_running_loop()
            stats = await loop.run_in_executor(None, lambda: container.stats(stream=False))

            # Parse CPU
            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
            cpu_count = len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1]))

            cpu_percent = 0.0
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0

            # Parse memory
            memory_usage = stats["memory_stats"].get("usage", 0)
            memory_limit = stats["memory_stats"].get("limit", 0)
            memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0

            # Parse network
            networks = stats.get("networks", {})
            network_rx = sum(n.get("rx_bytes", 0) for n in networks.values())
            network_tx = sum(n.get("tx_bytes", 0) for n in networks.values())

            # Parse block I/O
            blkio = stats.get("blkio_stats", {}).get("io_service_bytes_recursive", []) or []
            block_read = sum(b.get("value", 0) for b in blkio if b.get("op") == "Read")
            block_write = sum(b.get("value", 0) for b in blkio if b.get("op") == "Write")

            return ContainerStats(
                cpu_percent=cpu_percent,
                memory_usage_mb=memory_usage / (1024 * 1024),
                memory_limit_mb=memory_limit / (1024 * 1024),
                memory_percent=memory_percent,
                network_rx_bytes=network_rx,
                network_tx_bytes=network_tx,
                block_read_bytes=block_read,
                block_write_bytes=block_write,
                pids=stats.get("pids_stats", {}).get("current", 0),
            )
        except Exception as e:
            logger.error(f"Failed to get container stats: {e}")
            return None

    async def get_container_logs(
        self,
        container_id: str,
        stdout: bool = True,
        stderr: bool = True,
        tail: Optional[int] = None,
    ) -> str:
        """الحصول على logs الحاوية."""
        if not self._available:
            return ""

        try:
            container = self._client.containers.get(container_id)
            loop = asyncio.get_running_loop()
            logs = await loop.run_in_executor(
                None,
                lambda: container.logs(
                    stdout=stdout,
                    stderr=stderr,
                    tail=tail or "all",
                ),
            )
            return logs.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to get container logs: {e}")
            return ""

    async def wait_container(self, container_id: str, timeout: Optional[int] = None) -> int:
        """انتظار انتهاء الحاوية."""
        if not self._available:
            return -1

        try:
            container = self._client.containers.get(container_id)
            loop = asyncio.get_running_loop()

            if timeout:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, container.wait),
                    timeout=timeout,
                )
            else:
                result = await loop.run_in_executor(None, container.wait)

            return result.get("StatusCode", -1)
        except asyncio.TimeoutError:
            logger.warning(f"Container {container_id[:12]} timed out")
            await self.kill_container(container_id)
            return -1
        except Exception as e:
            logger.error(f"Failed to wait for container: {e}")
            return -1

    async def run_container(self, config: ContainerConfig, name: Optional[str] = None) -> ContainerResult:
        """تشغيل حاوية وانتظار انتهائها."""
        if not self._available:
            return ContainerResult(
                container_id="",
                exit_code=-1,
                error_message="Docker not available",
            )

        start_time = time.time()
        container_id = ""
        peak_memory = 0.0

        try:
            # Create container
            container_id = await self.create_container(config, name)

            # Start container
            await self.start_container(container_id)

            # Monitor stats in background
            stats_task = asyncio.create_task(self._monitor_container_stats(container_id))

            # Wait for container
            exit_code = await self.wait_container(container_id, config.timeout_seconds)

            # Cancel stats monitoring
            stats_task.cancel()
            try:
                peak_memory = await stats_task
            except asyncio.CancelledError:
                pass

            # Get logs
            stdout = await self.get_container_logs(container_id, stdout=True, stderr=False)
            stderr = await self.get_container_logs(container_id, stdout=False, stderr=True)

            execution_time = time.time() - start_time

            return ContainerResult(
                container_id=container_id,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                execution_time_seconds=execution_time,
                peak_memory_mb=peak_memory,
            )

        except Exception as e:
            logger.error(f"Container execution error: {e}")
            return ContainerResult(
                container_id=container_id,
                exit_code=-1,
                execution_time_seconds=time.time() - start_time,
                error_message=str(e),
            )
        finally:
            # Cleanup
            if container_id:
                await self.remove_container(container_id, force=True)

    async def stream_logs(
        self,
        container_id: str,
        stdout: bool = True,
        stderr: bool = True,
    ) -> AsyncIterator[str]:
        """بث logs الحاوية."""
        if not self._available:
            return

        try:
            container = self._client.containers.get(container_id)

            for log_line in container.logs(
                stdout=stdout,
                stderr=stderr,
                stream=True,
                follow=True,
            ):
                yield log_line.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Log streaming error: {e}")

    async def _monitor_container_stats(self, container_id: str) -> float:
        """مراقبة إحصائيات الحاوية وإرجاع peak memory."""
        peak_memory = 0.0

        try:
            while True:
                stats = await self.get_container_stats(container_id)
                if stats and stats.memory_usage_mb > peak_memory:
                    peak_memory = stats.memory_usage_mb
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

        return peak_memory

    def _build_docker_config(self, config: ContainerConfig) -> Dict[str, Any]:
        """بناء إعدادات Docker من ContainerConfig."""
        docker_config: Dict[str, Any] = {
            "detach": True,
            "working_dir": config.working_dir,
            "environment": config.environment,
            "labels": config.labels,
        }

        # Command
        if config.command:
            docker_config["command"] = config.command + config.args
        if config.entrypoint:
            docker_config["entrypoint"] = config.entrypoint

        # User
        if config.user:
            docker_config["user"] = config.user

        # Resource limits
        docker_config["mem_limit"] = f"{config.memory_mb}m"
        if config.memory_swap_mb >= 0:
            docker_config["memswap_limit"] = f"{config.memory_swap_mb}m"

        # CPU limits
        cpu_period = 100000
        cpu_quota = int(config.cpu_cores * cpu_period)
        if cpu_quota > 0:
            docker_config["cpu_period"] = cpu_period
            docker_config["cpu_quota"] = cpu_quota

        # GPU
        if config.gpu_count > 0:
            docker_config["device_requests"] = [
                {
                    "Driver": "nvidia",
                    "Count": config.gpu_count,
                    "DeviceIDs": config.gpu_device_ids if config.gpu_device_ids else None,
                    "Capabilities": [["gpu"]],
                }
            ]

        # Volumes
        volumes = {}
        for host_path, container_path in config.volumes.items():
            volumes[host_path] = {"bind": container_path, "mode": "rw"}
        for host_path, container_path in config.read_only_volumes.items():
            volumes[host_path] = {"bind": container_path, "mode": "ro"}
        if volumes:
            docker_config["volumes"] = volumes

        # Network
        if config.network_mode == NetworkMode.NONE:
            docker_config["network_mode"] = "none"
        elif config.network_mode == NetworkMode.HOST:
            docker_config["network_mode"] = "host"
        elif config.network_mode == NetworkMode.CUSTOM and config.custom_network:
            docker_config["network"] = config.custom_network
        # Default is bridge

        # Ports
        if config.ports:
            docker_config["ports"] = {f"{cp}/tcp": hp for cp, hp in config.ports.items()}

        # DNS
        if config.dns:
            docker_config["dns"] = config.dns

        # Extra hosts
        if config.extra_hosts:
            docker_config["extra_hosts"] = config.extra_hosts

        # Security
        if config.privileged:
            docker_config["privileged"] = True
        if config.read_only_rootfs:
            docker_config["read_only"] = True
        if config.capabilities_add:
            docker_config["cap_add"] = config.capabilities_add
        if config.capabilities_drop:
            docker_config["cap_drop"] = config.capabilities_drop
        if config.security_opt:
            docker_config["security_opt"] = config.security_opt

        # Pids limit
        if config.pids_limit:
            docker_config["pids_limit"] = config.pids_limit

        # Health check
        if config.healthcheck_cmd:
            docker_config["healthcheck"] = {
                "test": config.healthcheck_cmd,
                "interval": config.healthcheck_interval_seconds * 1_000_000_000,  # ns
                "timeout": config.healthcheck_timeout_seconds * 1_000_000_000,
                "retries": config.healthcheck_retries,
            }

        return docker_config

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """تحويل string إلى datetime."""
        if not dt_str or dt_str.startswith("0001-01-01"):
            return None
        try:
            # Docker uses RFC3339 format
            dt_str = dt_str.replace("Z", "+00:00")
            if "." in dt_str:
                # Truncate nanoseconds to microseconds
                parts = dt_str.split(".")
                if len(parts) == 2:
                    frac = parts[1].split("+")[0].split("-")[0][:6]
                    tz = "+" + parts[1].split("+")[1] if "+" in parts[1] else ""
                    dt_str = f"{parts[0]}.{frac}{tz}"
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None


def create_container_runtime(runtime_type: str = "docker") -> ContainerRuntime:
    """إنشاء container runtime."""
    if runtime_type == "docker":
        return DockerRuntime()
    else:
        raise ValueError(f"Unsupported runtime: {runtime_type}")
