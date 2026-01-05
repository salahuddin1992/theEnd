"""
Peer - تمثيل عقدة متصلة في الشبكة
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Set

from ..models.resources import ResourceSpec


class ConnectionState(str, Enum):
    """حالة الاتصال"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


@dataclass
class Peer:
    """
    عقدة متصلة في شبكة Mesh

    تمثل عقدة أخرى في الشبكة نتواصل معها
    """

    node_id: str
    hostname: str
    ip_address: str
    port: int
    resources: ResourceSpec
    state: str = "active"
    tags: Set[str] = field(default_factory=set)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    latency_ms: float = 0.0
    jobs_running: int = 0
    connection_failures: int = 0

    @property
    def address(self) -> str:
        """العنوان الكامل"""
        return f"{self.ip_address}:{self.port}"

    @property
    def is_healthy(self) -> bool:
        """هل العقدة صحية"""
        timeout = 30  # ثواني
        age = (datetime.now(timezone.utc) - self.last_seen).total_seconds()
        return age < timeout and self.connection_failures < 3

    @property
    def available_resources(self) -> ResourceSpec:
        """الموارد المتاحة (تقديرية)"""
        # تقدير بسيط - يمكن تحسينه
        return self.resources

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "port": self.port,
            "resources": self.resources.to_dict(),
            "state": self.state,
            "tags": list(self.tags),
            "last_seen": self.last_seen.isoformat(),
            "latency_ms": self.latency_ms,
            "jobs_running": self.jobs_running,
            "is_healthy": self.is_healthy,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Peer":
        return cls(
            node_id=data["node_id"],
            hostname=data["hostname"],
            ip_address=data["ip_address"],
            port=data["port"],
            resources=ResourceSpec.from_dict(data["resources"]),
            state=data.get("state", "active"),
            tags=set(data.get("tags", [])),
            last_seen=datetime.fromisoformat(data["last_seen"]) if "last_seen" in data else datetime.now(timezone.utc),
            latency_ms=data.get("latency_ms", 0.0),
            jobs_running=data.get("jobs_running", 0),
        )


class PeerConnection:
    """
    اتصال مستمر مع عقدة

    يحافظ على اتصال TCP مفتوح لتقليل overhead
    """

    def __init__(self, peer: Peer):
        self.peer = peer
        self.state = ConnectionState.DISCONNECTED
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected_at: Optional[datetime] = None
        self.messages_sent: int = 0
        self.messages_received: int = 0
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """إنشاء اتصال"""
        async with self._lock:
            if self.state == ConnectionState.CONNECTED:
                return True

            self.state = ConnectionState.CONNECTING

            try:
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        self.peer.ip_address,
                        self.peer.port,
                    ),
                    timeout=5.0,
                )
                self.state = ConnectionState.CONNECTED
                self.connected_at = datetime.now(timezone.utc)
                self.peer.connection_failures = 0
                return True

            except Exception:
                self.state = ConnectionState.FAILED
                self.peer.connection_failures += 1
                return False

    async def send(self, data: bytes) -> bool:
        """إرسال بيانات"""
        if self.state != ConnectionState.CONNECTED:
            if not await self.connect():
                return False

        try:
            self.writer.write(data)
            await self.writer.drain()
            self.messages_sent += 1
            return True
        except Exception:
            self.state = ConnectionState.DISCONNECTED
            return False

    async def receive(self, timeout: float = 5.0) -> Optional[bytes]:
        """استقبال بيانات"""
        if self.state != ConnectionState.CONNECTED:
            return None

        try:
            data = await asyncio.wait_for(
                self.reader.readline(),
                timeout=timeout,
            )
            if data:
                self.messages_received += 1
            return data
        except asyncio.TimeoutError:
            return None
        except Exception:
            self.state = ConnectionState.DISCONNECTED
            return None

    async def close(self) -> None:
        """إغلاق الاتصال"""
        async with self._lock:
            if self.writer:
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except Exception:
                    pass
            self.state = ConnectionState.DISCONNECTED
            self.reader = None
            self.writer = None

    @property
    def is_connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED

    def stats(self) -> Dict[str, Any]:
        """إحصائيات الاتصال"""
        return {
            "peer_id": self.peer.node_id,
            "state": self.state.value,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "uptime_seconds": (
                (datetime.now(timezone.utc) - self.connected_at).total_seconds()
                if self.connected_at else 0
            ),
        }
