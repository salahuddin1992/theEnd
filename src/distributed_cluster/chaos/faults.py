# -*- coding: utf-8 -*-
"""
Fault Injector for NebulaCompute Chaos Engineering.

Provides various fault injection capabilities for testing
system resilience.

حاقن الأخطاء لاختبار متانة النظام.
"""

import asyncio
import logging
import os
import random
import signal
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class FaultType(str, Enum):
    """Fault type."""

    # Process faults
    PROCESS_KILL = "process_kill"
    PROCESS_PAUSE = "process_pause"
    PROCESS_CPU_HOG = "process_cpu_hog"
    PROCESS_MEMORY_HOG = "process_memory_hog"

    # Network faults
    NETWORK_DELAY = "network_delay"
    NETWORK_LOSS = "network_loss"
    NETWORK_PARTITION = "network_partition"
    NETWORK_BANDWIDTH = "network_bandwidth"
    NETWORK_CORRUPT = "network_corrupt"

    # Disk faults
    DISK_FILL = "disk_fill"
    DISK_SLOW = "disk_slow"
    DISK_ERROR = "disk_error"

    # Resource faults
    RESOURCE_EXHAUST_CPU = "resource_exhaust_cpu"
    RESOURCE_EXHAUST_MEMORY = "resource_exhaust_memory"
    RESOURCE_EXHAUST_FD = "resource_exhaust_fd"

    # Time faults
    TIME_SKEW = "time_skew"

    # Custom
    CUSTOM = "custom"


@dataclass
class FaultConfig:
    """
    Fault configuration.

    تكوين الخطأ.
    """

    fault_type: FaultType
    parameters: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: int = 60
    probability: float = 1.0  # 0.0 to 1.0
    jitter_seconds: int = 0
    repeat_count: int = 1
    repeat_interval_seconds: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "fault_type": self.fault_type.value,
            "parameters": self.parameters,
            "duration_seconds": self.duration_seconds,
            "probability": self.probability,
            "jitter_seconds": self.jitter_seconds,
            "repeat_count": self.repeat_count,
            "repeat_interval_seconds": self.repeat_interval_seconds,
        }


@dataclass
class FaultResult:
    """
    Fault injection result.

    نتيجة حقن الخطأ.
    """

    fault_id: str
    fault_type: FaultType
    success: bool
    targets_affected: List[str]
    started_at: datetime
    ended_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        """Get fault duration."""
        if not self.ended_at:
            return 0.0
        return (self.ended_at - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "fault_id": self.fault_id,
            "fault_type": self.fault_type.value,
            "success": self.success,
            "targets_affected": self.targets_affected,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


class FaultInjector:
    """
    Injects faults for chaos experiments.

    حاقن الأخطاء لتجارب الفوضى.

    Features:
    - Multiple fault types
    - Target selection
    - Probabilistic injection
    - Automatic cleanup
    - Safe rollback
    """

    def __init__(
        self,
        dry_run: bool = False,
        safe_mode: bool = True,
        target_resolver: Optional[Callable] = None,
    ):
        """
        Initialize Fault Injector.

        Args:
            dry_run: Simulate faults without actual injection
            safe_mode: Enable safety checks
            target_resolver: Function to resolve targets
        """
        self.dry_run = dry_run
        self.safe_mode = safe_mode
        self.target_resolver = target_resolver

        # Active faults
        self._active_faults: Dict[str, Dict[str, Any]] = {}
        self._cleanup_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

        # Fault handlers
        self._handlers: Dict[FaultType, Callable] = {
            FaultType.PROCESS_KILL: self._inject_process_kill,
            FaultType.PROCESS_PAUSE: self._inject_process_pause,
            FaultType.PROCESS_CPU_HOG: self._inject_cpu_hog,
            FaultType.PROCESS_MEMORY_HOG: self._inject_memory_hog,
            FaultType.NETWORK_DELAY: self._inject_network_delay,
            FaultType.NETWORK_LOSS: self._inject_network_loss,
            FaultType.NETWORK_PARTITION: self._inject_network_partition,
            FaultType.DISK_FILL: self._inject_disk_fill,
            FaultType.RESOURCE_EXHAUST_CPU: self._inject_cpu_exhaust,
            FaultType.RESOURCE_EXHAUST_MEMORY: self._inject_memory_exhaust,
        }

        # Statistics
        self._stats = {
            "total_injections": 0,
            "successful_injections": 0,
            "failed_injections": 0,
            "active_faults": 0,
        }

    async def inject(
        self,
        fault_type: str,
        config: Dict[str, Any],
        target_selector: Dict[str, Any],
    ) -> FaultResult:
        """
        Inject a fault.

        حقن خطأ.

        Args:
            fault_type: Type of fault to inject
            config: Fault configuration
            target_selector: Target selection criteria

        Returns:
            FaultResult object
        """
        import uuid

        fault_id = str(uuid.uuid4())
        fault_type_enum = FaultType(fault_type)
        now = datetime.utcnow()

        self._stats["total_injections"] += 1

        try:
            # Resolve targets
            targets = await self._resolve_targets(target_selector)

            if not targets:
                return FaultResult(
                    fault_id=fault_id,
                    fault_type=fault_type_enum,
                    success=False,
                    targets_affected=[],
                    started_at=now,
                    ended_at=now,
                    error_message="No targets found",
                )

            # Apply probability
            probability = config.get("probability", 1.0)
            if random.random() > probability:
                return FaultResult(
                    fault_id=fault_id,
                    fault_type=fault_type_enum,
                    success=True,
                    targets_affected=[],
                    started_at=now,
                    ended_at=now,
                    metadata={"skipped_by_probability": True},
                )

            # Add jitter
            jitter = config.get("jitter_seconds", 0)
            if jitter > 0:
                await asyncio.sleep(random.uniform(0, jitter))

            # Get handler
            handler = self._handlers.get(fault_type_enum)
            if not handler:
                return FaultResult(
                    fault_id=fault_id,
                    fault_type=fault_type_enum,
                    success=False,
                    targets_affected=[],
                    started_at=now,
                    ended_at=now,
                    error_message=f"No handler for fault type: {fault_type}",
                )

            # Inject fault
            affected_targets = []

            if self.dry_run:
                logger.info(f"[DRY RUN] Would inject {fault_type} on {targets}")
                affected_targets = targets
            else:
                for target in targets:
                    try:
                        await handler(target, config)
                        affected_targets.append(target)
                    except Exception as e:
                        logger.error(f"Failed to inject fault on {target}: {e}")

            # Track active fault
            async with self._lock:
                self._active_faults[fault_id] = {
                    "fault_type": fault_type_enum,
                    "config": config,
                    "targets": affected_targets,
                    "started_at": now,
                }
                self._stats["active_faults"] = len(self._active_faults)

            self._stats["successful_injections"] += 1

            logger.info(
                f"Injected {fault_type} on {len(affected_targets)} targets"
            )

            return FaultResult(
                fault_id=fault_id,
                fault_type=fault_type_enum,
                success=True,
                targets_affected=affected_targets,
                started_at=now,
            )

        except Exception as e:
            self._stats["failed_injections"] += 1
            logger.error(f"Fault injection failed: {e}")

            return FaultResult(
                fault_id=fault_id,
                fault_type=fault_type_enum,
                success=False,
                targets_affected=[],
                started_at=now,
                ended_at=datetime.utcnow(),
                error_message=str(e),
            )

    async def remove(
        self,
        fault_type: str,
        config: Dict[str, Any],
        target_selector: Dict[str, Any],
    ) -> bool:
        """
        Remove an injected fault.

        إزالة خطأ محقون.
        """
        fault_type_enum = FaultType(fault_type)
        targets = await self._resolve_targets(target_selector)

        if self.dry_run:
            logger.info(f"[DRY RUN] Would remove {fault_type} from {targets}")
            return True

        success = True

        for target in targets:
            try:
                await self._remove_fault(fault_type_enum, target, config)
            except Exception as e:
                logger.error(f"Failed to remove fault from {target}: {e}")
                success = False

        logger.info(f"Removed {fault_type} from targets")
        return success

    async def _resolve_targets(
        self,
        selector: Dict[str, Any],
    ) -> List[str]:
        """Resolve targets from selector."""
        if self.target_resolver:
            return await self.target_resolver(selector)

        # Default: return explicitly listed targets
        return selector.get("targets", [])

    async def _inject_process_kill(
        self,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Kill a process."""
        pid = config.get("pid") or await self._get_process_pid(target)
        if pid:
            sig = config.get("signal", signal.SIGKILL)
            os.kill(pid, sig)
            logger.info(f"Killed process {pid} with signal {sig}")

    async def _inject_process_pause(
        self,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Pause a process with SIGSTOP."""
        pid = config.get("pid") or await self._get_process_pid(target)
        if pid:
            os.kill(pid, signal.SIGSTOP)
            logger.info(f"Paused process {pid}")

    async def _inject_cpu_hog(
        self,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Consume CPU resources."""
        cores = config.get("cores", 1)
        duration = config.get("duration_seconds", 60)

        async def cpu_loop():
            end_time = asyncio.get_event_loop().time() + duration
            while asyncio.get_event_loop().time() < end_time:
                # Busy loop
                _ = sum(i * i for i in range(10000))
                await asyncio.sleep(0)

        for _ in range(cores):
            asyncio.create_task(cpu_loop())

        logger.info(f"Started CPU hog on {cores} cores for {duration}s")

    async def _inject_memory_hog(
        self,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Consume memory resources."""
        mb = config.get("megabytes", 100)

        # Allocate memory
        data = bytearray(mb * 1024 * 1024)

        # Store reference to prevent GC
        self._active_faults[target] = {"memory": data}

        logger.info(f"Allocated {mb}MB of memory")

    async def _inject_network_delay(
        self,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Add network delay using tc (traffic control)."""
        delay_ms = config.get("delay_ms", 100)
        jitter_ms = config.get("jitter_ms", 10)
        interface = config.get("interface", "eth0")

        # Use tc to add delay (requires root)
        cmd = (
            f"tc qdisc add dev {interface} root netem "
            f"delay {delay_ms}ms {jitter_ms}ms"
        )

        if not self.dry_run:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

        logger.info(f"Added {delay_ms}ms network delay on {interface}")

    async def _inject_network_loss(
        self,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Add packet loss using tc."""
        loss_percent = config.get("loss_percent", 10)
        interface = config.get("interface", "eth0")

        cmd = f"tc qdisc add dev {interface} root netem loss {loss_percent}%"

        if not self.dry_run:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

        logger.info(f"Added {loss_percent}% packet loss on {interface}")

    async def _inject_network_partition(
        self,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Create network partition using iptables."""
        partition_hosts = config.get("hosts", [])

        for host in partition_hosts:
            cmd = f"iptables -A INPUT -s {host} -j DROP"

            if not self.dry_run:
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await process.communicate()

        logger.info(f"Created network partition blocking {partition_hosts}")

    async def _inject_disk_fill(
        self,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Fill disk space."""
        # nosec B108 - chaos testing requires predictable temp path
        path = config.get("path", "/tmp/chaos-fill")
        size_mb = config.get("size_mb", 100)

        if not self.dry_run:
            with open(path, "wb") as f:
                f.write(os.urandom(size_mb * 1024 * 1024))

        logger.info(f"Created {size_mb}MB file at {path}")

    async def _inject_cpu_exhaust(
        self,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Exhaust CPU resources."""
        await self._inject_cpu_hog(target, config)

    async def _inject_memory_exhaust(
        self,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Exhaust memory resources."""
        await self._inject_memory_hog(target, config)

    async def _remove_fault(
        self,
        fault_type: FaultType,
        target: str,
        config: Dict[str, Any],
    ) -> None:
        """Remove a specific fault."""
        if fault_type == FaultType.PROCESS_PAUSE:
            # Resume process
            pid = config.get("pid") or await self._get_process_pid(target)
            if pid:
                os.kill(pid, signal.SIGCONT)

        elif fault_type in [FaultType.NETWORK_DELAY, FaultType.NETWORK_LOSS]:
            # Remove tc rules
            interface = config.get("interface", "eth0")
            cmd = f"tc qdisc del dev {interface} root"
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

        elif fault_type == FaultType.NETWORK_PARTITION:
            # Remove iptables rules
            partition_hosts = config.get("hosts", [])
            for host in partition_hosts:
                cmd = f"iptables -D INPUT -s {host} -j DROP"
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await process.communicate()

        elif fault_type == FaultType.DISK_FILL:
            # Remove fill file
            # nosec B108 - chaos testing requires predictable temp path
            path = config.get("path", "/tmp/chaos-fill")
            if os.path.exists(path):
                os.remove(path)

        elif fault_type == FaultType.PROCESS_MEMORY_HOG:
            # Release memory
            if target in self._active_faults:
                del self._active_faults[target]

    async def _get_process_pid(self, target: str) -> Optional[int]:
        """Get process PID from target identifier."""
        # In real implementation, would resolve from worker/job ID
        return None

    async def get_active_faults(self) -> List[Dict[str, Any]]:
        """Get list of active faults."""
        return [
            {
                "fault_id": fid,
                **info,
                "started_at": info["started_at"].isoformat(),
            }
            for fid, info in self._active_faults.items()
        ]

    async def cleanup_all(self) -> int:
        """Clean up all active faults."""
        cleaned = 0
        async with self._lock:
            for fault_id, info in list(self._active_faults.items()):
                try:
                    for target in info["targets"]:
                        await self._remove_fault(
                            info["fault_type"],
                            target,
                            info["config"],
                        )
                    del self._active_faults[fault_id]
                    cleaned += 1
                except Exception as e:
                    logger.error(f"Failed to cleanup fault {fault_id}: {e}")

            self._stats["active_faults"] = len(self._active_faults)

        logger.info(f"Cleaned up {cleaned} faults")
        return cleaned

    async def get_statistics(self) -> Dict[str, Any]:
        """Get fault injector statistics."""
        return {
            **self._stats,
            "dry_run_mode": self.dry_run,
            "safe_mode": self.safe_mode,
        }

    async def shutdown(self) -> None:
        """Shutdown fault injector."""
        await self.cleanup_all()
        logger.info("Fault Injector shutdown complete")
