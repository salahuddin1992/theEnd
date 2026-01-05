"""
Broadcast Discovery - اكتشاف عبر البث
========================================

UDP broadcast-based service discovery for networks where mDNS is not available.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Broadcast settings
BROADCAST_PORT = 18765
MULTICAST_GROUP = "224.0.0.251"
DISCOVERY_MAGIC = b"NEBULA"


@dataclass
class BroadcastMessage:
    """رسالة البث."""
    message_type: str  # "announce", "discover", "response"
    service_type: str  # "master", "worker"
    name: str
    host: str
    port: int
    properties: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())

    def to_bytes(self) -> bytes:
        """تحويل إلى بايتات."""
        data = json.dumps({
            "type": self.message_type,
            "service": self.service_type,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "props": self.properties,
            "ts": self.timestamp,
        }).encode()
        return DISCOVERY_MAGIC + data

    @classmethod
    def from_bytes(cls, data: bytes) -> Optional["BroadcastMessage"]:
        """إنشاء من بايتات."""
        if not data.startswith(DISCOVERY_MAGIC):
            return None

        try:
            payload = json.loads(data[len(DISCOVERY_MAGIC):].decode())
            return cls(
                message_type=payload["type"],
                service_type=payload["service"],
                name=payload["name"],
                host=payload["host"],
                port=payload["port"],
                properties=payload.get("props", {}),
                timestamp=payload.get("ts", datetime.now(timezone.utc).timestamp()),
            )
        except Exception as e:
            logger.error(f"Failed to parse message: {e}")
            return None


class BroadcastDiscovery:
    """
    اكتشاف الخدمات عبر البث UDP.

    Features:
    - Works on networks without mDNS support
    - Automatic service announcement
    - Periodic heartbeat
    - Cross-subnet support via multicast
    """

    def __init__(
        self,
        service_type: str = "master",
        service_name: Optional[str] = None,
        port: int = 8765,
        on_discovered: Optional[Callable[[BroadcastMessage], None]] = None,
    ):
        self.service_type = service_type
        self.service_name = service_name or socket.gethostname()
        self.port = port
        self.on_discovered = on_discovered

        self._discovered: Dict[str, BroadcastMessage] = {}
        self._running = False
        self._socket = None
        self._announce_task = None
        self._listen_task = None

    async def start(self) -> None:
        """بدء الاكتشاف."""
        self._running = True

        # Create UDP socket
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._socket.setblocking(False)

        try:
            self._socket.bind(("", BROADCAST_PORT))
        except OSError:
            logger.warning(f"Could not bind to port {BROADCAST_PORT}")

        # Join multicast group
        try:
            mreq = struct.pack(
                "4sl",
                socket.inet_aton(MULTICAST_GROUP),
                socket.INADDR_ANY
            )
            self._socket.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_ADD_MEMBERSHIP,
                mreq
            )
        except Exception as e:
            logger.warning(f"Could not join multicast group: {e}")

        # Start tasks
        self._listen_task = asyncio.create_task(self._listen_loop())
        self._announce_task = asyncio.create_task(self._announce_loop())

        logger.info("Broadcast discovery started")

    async def stop(self) -> None:
        """إيقاف الاكتشاف."""
        self._running = False

        if self._announce_task:
            self._announce_task.cancel()
            try:
                await self._announce_task
            except asyncio.CancelledError:
                pass

        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        if self._socket:
            self._socket.close()
            self._socket = None

        logger.info("Broadcast discovery stopped")

    async def discover(self, timeout: float = 3.0) -> List[BroadcastMessage]:
        """
        البحث عن الخدمات.

        Args:
            timeout: مدة البحث

        Returns:
            قائمة الخدمات المكتشفة
        """
        # Send discovery request
        await self._send_discover()

        # Wait for responses
        await asyncio.sleep(timeout)

        # Return discovered services
        return list(self._discovered.values())

    async def announce(self) -> None:
        """إعلان الخدمة."""
        message = BroadcastMessage(
            message_type="announce",
            service_type=self.service_type,
            name=self.service_name,
            host=self._get_local_ip(),
            port=self.port,
            properties={
                "version": "1.0.0",
                "hostname": socket.gethostname(),
            },
        )

        await self._broadcast(message)

    async def _send_discover(self) -> None:
        """إرسال طلب اكتشاف."""
        message = BroadcastMessage(
            message_type="discover",
            service_type="*",
            name=self.service_name,
            host=self._get_local_ip(),
            port=0,
        )

        await self._broadcast(message)

    async def _broadcast(self, message: BroadcastMessage) -> None:
        """بث رسالة."""
        if not self._socket:
            return

        data = message.to_bytes()

        try:
            # Broadcast
            self._socket.sendto(data, ("<broadcast>", BROADCAST_PORT))
        except Exception as e:
            logger.debug(f"Broadcast failed: {e}")

        try:
            # Multicast
            self._socket.sendto(data, (MULTICAST_GROUP, BROADCAST_PORT))
        except Exception as e:
            logger.debug(f"Multicast failed: {e}")

    async def _listen_loop(self) -> None:
        """حلقة الاستماع."""
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # Non-blocking receive
                data, addr = await loop.sock_recvfrom(self._socket, 4096)

                message = BroadcastMessage.from_bytes(data)
                if message:
                    await self._handle_message(message, addr)

            except asyncio.CancelledError:
                break
            except BlockingIOError:
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.debug(f"Listen error: {e}")
                await asyncio.sleep(0.5)

    async def _announce_loop(self) -> None:
        """حلقة الإعلان."""
        while self._running:
            try:
                await self.announce()
                await asyncio.sleep(30)  # Announce every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Announce error: {e}")
                await asyncio.sleep(5)

    async def _handle_message(
        self,
        message: BroadcastMessage,
        addr: tuple,
    ) -> None:
        """معالجة رسالة واردة."""
        # Ignore our own messages
        if message.name == self.service_name and message.host == self._get_local_ip():
            return

        if message.message_type == "discover":
            # Someone is looking for services, respond
            await self.announce()

        elif message.message_type in ("announce", "response"):
            # Service announcement
            key = f"{message.service_type}:{message.host}:{message.port}"

            if key not in self._discovered:
                logger.info(
                    f"Discovered {message.service_type}: "
                    f"{message.name} at {message.host}:{message.port}"
                )

            self._discovered[key] = message

            if self.on_discovered:
                self.on_discovered(message)

    def get_masters(self) -> List[BroadcastMessage]:
        """الحصول على الماسترات المكتشفة."""
        return [m for m in self._discovered.values() if m.service_type == "master"]

    def get_workers(self) -> List[BroadcastMessage]:
        """الحصول على العمال المكتشفين."""
        return [m for m in self._discovered.values() if m.service_type == "worker"]

    def _get_local_ip(self) -> str:
        """الحصول على IP المحلي."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


async def discover_cluster(timeout: float = 5.0) -> Dict[str, List[BroadcastMessage]]:
    """
    اكتشاف الكلاستر.

    Returns:
        قاموس بالماسترات والعمال المكتشفين
    """
    discovery = BroadcastDiscovery()
    await discovery.start()

    services = await discovery.discover(timeout)

    await discovery.stop()

    return {
        "masters": [s for s in services if s.service_type == "master"],
        "workers": [s for s in services if s.service_type == "worker"],
    }
