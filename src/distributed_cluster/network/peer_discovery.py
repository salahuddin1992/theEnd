"""
Peer Discovery & Communication - اكتشاف والتواصل مع التطبيقات المحلية
=====================================================================

نظام اكتشاف وتواصل بين التطبيقات المحلية:
- اكتشاف تلقائي للتطبيقات على الشبكة المحلية
- تبادل المعلومات بين الأطراف
- سهولة الاتصال والإلغاء
- لوحة تحكم لإدارة الاتصالات

Features:
- UDP broadcast للاكتشاف التلقائي
- TCP للاتصال المباشر
- تبادل معلومات الجهاز والتطبيق
- إشعارات عند اتصال/انفصال الأطراف
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import socket
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PeerStatus(str, Enum):
    """حالة الـ Peer."""
    DISCOVERED = "discovered"      # تم اكتشافه
    CONNECTING = "connecting"      # جاري الاتصال
    CONNECTED = "connected"        # متصل
    DISCONNECTED = "disconnected"  # منفصل
    BLOCKED = "blocked"            # محظور


class MessageType(str, Enum):
    """أنواع الرسائل."""
    DISCOVERY = "discovery"        # رسالة اكتشاف
    HELLO = "hello"                # تحية (معلومات)
    PING = "ping"                  # فحص الاتصال
    PONG = "pong"                  # رد الفحص
    INFO_REQUEST = "info_request"  # طلب معلومات
    INFO_RESPONSE = "info_response"  # رد المعلومات
    MESSAGE = "message"            # رسالة عادية
    DISCONNECT = "disconnect"      # إنهاء الاتصال
    COMMAND = "command"            # أمر للتنفيذ
    COMMAND_RESULT = "command_result"  # نتيجة الأمر


@dataclass
class DeviceInfo:
    """معلومات الجهاز."""
    hostname: str
    platform: str              # Windows, Linux, macOS
    platform_version: str
    architecture: str          # x64, arm64
    cpu_count: int
    memory_gb: float
    ip_addresses: List[str] = field(default_factory=list)
    username: str = ""

    @classmethod
    def from_system(cls) -> DeviceInfo:
        """جمع معلومات الجهاز الحالي."""
        import os

        import psutil

        # Get IP addresses
        ip_addresses = []
        try:
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                        ip_addresses.append(addr.address)
        except Exception:
            ip_addresses = [socket.gethostbyname(socket.gethostname())]

        return cls(
            hostname=socket.gethostname(),
            platform=platform.system(),
            platform_version=platform.version(),
            architecture=platform.machine(),
            cpu_count=os.cpu_count() or 1,
            memory_gb=round(psutil.virtual_memory().total / (1024**3), 2),
            ip_addresses=ip_addresses,
            username=os.getenv("USER") or os.getenv("USERNAME") or "unknown",
        )


@dataclass
class AppInfo:
    """معلومات التطبيق."""
    app_name: str = "NebulaCompute"
    app_version: str = "1.0.0"
    app_type: str = "worker"       # master, worker, desktop
    capabilities: List[str] = field(default_factory=list)
    services: Dict[str, int] = field(default_factory=dict)  # service -> port


@dataclass
class PeerInfo:
    """معلومات الطرف الآخر."""
    peer_id: str
    device: DeviceInfo
    app: AppInfo
    status: PeerStatus = PeerStatus.DISCOVERED
    last_seen: float = 0.0
    connected_at: Optional[float] = None
    address: str = ""
    port: int = 0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """تحويل إلى dictionary."""
        return {
            "peer_id": self.peer_id,
            "device": asdict(self.device),
            "app": asdict(self.app),
            "status": self.status.value,
            "last_seen": self.last_seen,
            "connected_at": self.connected_at,
            "address": self.address,
            "port": self.port,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }


@dataclass
class PeerMessage:
    """رسالة بين الأطراف."""
    msg_type: MessageType
    sender_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_json(self) -> str:
        return json.dumps({
            "msg_type": self.msg_type.value,
            "sender_id": self.sender_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "msg_id": self.msg_id,
        })

    @classmethod
    def from_json(cls, data: str) -> PeerMessage:
        d = json.loads(data)
        return cls(
            msg_type=MessageType(d["msg_type"]),
            sender_id=d["sender_id"],
            payload=d.get("payload", {}),
            timestamp=d.get("timestamp", time.time()),
            msg_id=d.get("msg_id", str(uuid.uuid4())),
        )


class PeerDiscovery:
    """
    نظام اكتشاف الأطراف على الشبكة المحلية.

    يستخدم UDP broadcast للاكتشاف التلقائي.
    """

    def __init__(
        self,
        my_id: Optional[str] = None,
        discovery_port: int = 5959,
        broadcast_interval: float = 5.0,
        peer_timeout: float = 30.0,
    ):
        self.my_id = my_id or str(uuid.uuid4())[:8]
        self.discovery_port = discovery_port
        self.broadcast_interval = broadcast_interval
        self.peer_timeout = peer_timeout

        # معلوماتي
        self.my_device = DeviceInfo.from_system()
        self.my_app = AppInfo()

        # الأطراف المكتشفة
        self.peers: Dict[str, PeerInfo] = {}
        self.blocked_peers: Set[str] = set()

        # Callbacks
        self._on_peer_discovered: List[Callable[[PeerInfo], None]] = []
        self._on_peer_lost: List[Callable[[PeerInfo], None]] = []
        self._on_peer_updated: List[Callable[[PeerInfo], None]] = []

        # Tasks
        self._broadcast_task: Optional[asyncio.Task] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

        # Socket
        self._socket: Optional[socket.socket] = None

    def set_app_info(
        self,
        app_name: str = "NebulaCompute",
        app_version: str = "1.0.0",
        app_type: str = "worker",
        capabilities: Optional[List[str]] = None,
        services: Optional[Dict[str, int]] = None,
    ) -> None:
        """تعيين معلومات التطبيق."""
        self.my_app = AppInfo(
            app_name=app_name,
            app_version=app_version,
            app_type=app_type,
            capabilities=capabilities or [],
            services=services or {},
        )

    def on_peer_discovered(self, callback: Callable[[PeerInfo], None]) -> None:
        """إضافة callback عند اكتشاف peer جديد."""
        self._on_peer_discovered.append(callback)

    def on_peer_lost(self, callback: Callable[[PeerInfo], None]) -> None:
        """إضافة callback عند فقدان peer."""
        self._on_peer_lost.append(callback)

    def on_peer_updated(self, callback: Callable[[PeerInfo], None]) -> None:
        """إضافة callback عند تحديث معلومات peer."""
        self._on_peer_updated.append(callback)

    async def start(self) -> None:
        """بدء الاكتشاف."""
        if self._running:
            return

        self._running = True

        # Create UDP socket
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self._socket.bind(("", self.discovery_port))
        except OSError as e:
            logger.warning(f"Could not bind to port {self.discovery_port}: {e}")
            # Try alternative port
            self._socket.bind(("", 0))
            self.discovery_port = self._socket.getsockname()[1]

        self._socket.setblocking(False)

        # Start tasks
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        self._listen_task = asyncio.create_task(self._listen_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(f"Peer discovery started (ID: {self.my_id}, Port: {self.discovery_port})")

    async def stop(self) -> None:
        """إيقاف الاكتشاف."""
        self._running = False

        # Cancel tasks
        for task in [self._broadcast_task, self._listen_task, self._cleanup_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close socket
        if self._socket:
            self._socket.close()
            self._socket = None

        logger.info("Peer discovery stopped")

    async def _broadcast_loop(self) -> None:
        """إرسال رسائل الاكتشاف بشكل دوري."""
        while self._running:
            try:
                await self._send_discovery()
                await asyncio.sleep(self.broadcast_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                await asyncio.sleep(1)

    async def _send_discovery(self) -> None:
        """إرسال رسالة اكتشاف."""
        if not self._socket:
            return

        msg = PeerMessage(
            msg_type=MessageType.DISCOVERY,
            sender_id=self.my_id,
            payload={
                "device": asdict(self.my_device),
                "app": asdict(self.my_app),
            },
        )

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._socket.sendto(
                    msg.to_json().encode(),
                    ("<broadcast>", self.discovery_port),
                ),
            )
        except Exception as e:
            logger.debug(f"Broadcast send error: {e}")

    async def _listen_loop(self) -> None:
        """الاستماع لرسائل الاكتشاف."""
        while self._running:
            try:
                loop = asyncio.get_event_loop()
                data, addr = await loop.run_in_executor(
                    None,
                    lambda: self._socket.recvfrom(4096) if self._socket else (b"", ("", 0)),
                )

                if data:
                    await self._handle_discovery_message(data, addr)

            except BlockingIOError:
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Listen error: {e}")
                await asyncio.sleep(0.1)

    async def _handle_discovery_message(self, data: bytes, addr: tuple) -> None:
        """معالجة رسالة اكتشاف."""
        try:
            msg = PeerMessage.from_json(data.decode())

            # تجاهل رسائلي
            if msg.sender_id == self.my_id:
                return

            # تجاهل المحظورين
            if msg.sender_id in self.blocked_peers:
                return

            if msg.msg_type == MessageType.DISCOVERY:
                await self._process_discovery(msg, addr)

        except Exception as e:
            logger.debug(f"Error processing discovery message: {e}")

    async def _process_discovery(self, msg: PeerMessage, addr: tuple) -> None:
        """معالجة رسالة اكتشاف peer."""
        peer_id = msg.sender_id
        is_new = peer_id not in self.peers

        # Build peer info
        device_data = msg.payload.get("device", {})
        app_data = msg.payload.get("app", {})

        device = DeviceInfo(
            hostname=device_data.get("hostname", "unknown"),
            platform=device_data.get("platform", "unknown"),
            platform_version=device_data.get("platform_version", ""),
            architecture=device_data.get("architecture", ""),
            cpu_count=device_data.get("cpu_count", 1),
            memory_gb=device_data.get("memory_gb", 0),
            ip_addresses=device_data.get("ip_addresses", [addr[0]]),
            username=device_data.get("username", ""),
        )

        app = AppInfo(
            app_name=app_data.get("app_name", "Unknown"),
            app_version=app_data.get("app_version", "0.0.0"),
            app_type=app_data.get("app_type", "unknown"),
            capabilities=app_data.get("capabilities", []),
            services=app_data.get("services", {}),
        )

        if is_new:
            peer = PeerInfo(
                peer_id=peer_id,
                device=device,
                app=app,
                status=PeerStatus.DISCOVERED,
                last_seen=time.time(),
                address=addr[0],
                port=addr[1],
            )
            self.peers[peer_id] = peer

            # Notify callbacks
            for cb in self._on_peer_discovered:
                try:
                    cb(peer)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

            logger.info(f"Discovered peer: {peer_id} ({device.hostname}) at {addr[0]}")

        else:
            peer = self.peers[peer_id]
            peer.device = device
            peer.app = app
            peer.last_seen = time.time()
            peer.address = addr[0]
            peer.port = addr[1]

            # Notify update
            for cb in self._on_peer_updated:
                try:
                    cb(peer)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

    async def _cleanup_loop(self) -> None:
        """تنظيف الأطراف غير النشطة."""
        while self._running:
            try:
                await asyncio.sleep(self.peer_timeout / 2)

                now = time.time()
                lost_peers = []

                for peer_id, peer in list(self.peers.items()):
                    if now - peer.last_seen > self.peer_timeout:
                        lost_peers.append(peer_id)

                for peer_id in lost_peers:
                    peer = self.peers.pop(peer_id, None)
                    if peer:
                        peer.status = PeerStatus.DISCONNECTED

                        for cb in self._on_peer_lost:
                            try:
                                cb(peer)
                            except Exception as e:
                                logger.error(f"Callback error: {e}")

                        logger.info(f"Lost peer: {peer_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    def get_peers(self) -> List[PeerInfo]:
        """الحصول على قائمة الأطراف."""
        return list(self.peers.values())

    def get_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """الحصول على معلومات peer محدد."""
        return self.peers.get(peer_id)

    def block_peer(self, peer_id: str) -> None:
        """حظر peer."""
        self.blocked_peers.add(peer_id)
        if peer_id in self.peers:
            self.peers[peer_id].status = PeerStatus.BLOCKED

    def unblock_peer(self, peer_id: str) -> None:
        """إلغاء حظر peer."""
        self.blocked_peers.discard(peer_id)
        if peer_id in self.peers:
            self.peers[peer_id].status = PeerStatus.DISCOVERED

    def get_my_info(self) -> Dict:
        """الحصول على معلوماتي."""
        return {
            "peer_id": self.my_id,
            "device": asdict(self.my_device),
            "app": asdict(self.my_app),
        }


class PeerConnection:
    """
    اتصال مباشر مع peer.

    يستخدم TCP للاتصال الموثوق.
    """

    def __init__(
        self,
        my_id: str,
        peer_info: PeerInfo,
        on_message: Optional[Callable[[PeerMessage], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
    ):
        self.my_id = my_id
        self.peer = peer_info
        self._on_message = on_message
        self._on_disconnect = on_disconnect

        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._receive_task: Optional[asyncio.Task] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self, port: int = 5960, timeout: float = 10.0) -> bool:
        """الاتصال بالـ peer."""
        try:
            self.peer.status = PeerStatus.CONNECTING

            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.peer.address, port),
                timeout=timeout,
            )

            # Send hello
            hello = PeerMessage(
                msg_type=MessageType.HELLO,
                sender_id=self.my_id,
                payload={"peer_id": self.my_id},
            )
            await self._send(hello)

            self._connected = True
            self.peer.status = PeerStatus.CONNECTED
            self.peer.connected_at = time.time()

            # Start receiving
            self._receive_task = asyncio.create_task(self._receive_loop())

            logger.info(f"Connected to peer: {self.peer.peer_id}")
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.peer.status = PeerStatus.DISCONNECTED
            return False

    async def disconnect(self) -> None:
        """قطع الاتصال."""
        if not self._connected:
            return

        try:
            # Send disconnect message
            msg = PeerMessage(
                msg_type=MessageType.DISCONNECT,
                sender_id=self.my_id,
            )
            await self._send(msg)
        except Exception:
            pass

        self._connected = False
        self.peer.status = PeerStatus.DISCONNECTED

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

        if self._on_disconnect:
            self._on_disconnect()

        logger.info(f"Disconnected from peer: {self.peer.peer_id}")

    async def send_message(self, content: str, metadata: Optional[Dict] = None) -> bool:
        """إرسال رسالة."""
        if not self._connected:
            return False

        msg = PeerMessage(
            msg_type=MessageType.MESSAGE,
            sender_id=self.my_id,
            payload={
                "content": content,
                "metadata": metadata or {},
            },
        )
        return await self._send(msg)

    async def request_info(self) -> Optional[Dict]:
        """طلب معلومات من الـ peer."""
        if not self._connected:
            return None

        msg = PeerMessage(
            msg_type=MessageType.INFO_REQUEST,
            sender_id=self.my_id,
        )
        await self._send(msg)
        # Response will come through callback
        return None

    async def ping(self) -> float:
        """فحص الاتصال وقياس الـ latency."""
        if not self._connected:
            return -1

        start = time.time()
        msg = PeerMessage(
            msg_type=MessageType.PING,
            sender_id=self.my_id,
            payload={"timestamp": start},
        )
        await self._send(msg)

        # Wait for pong (simplified - in real impl would use event)
        await asyncio.sleep(0.1)
        return (time.time() - start) * 1000

    async def _send(self, msg: PeerMessage) -> bool:
        """إرسال رسالة."""
        if not self._writer:
            return False

        try:
            data = msg.to_json().encode() + b"\n"
            self._writer.write(data)
            await self._writer.drain()
            return True
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    async def _receive_loop(self) -> None:
        """استقبال الرسائل."""
        while self._connected and self._reader:
            try:
                data = await self._reader.readline()
                if not data:
                    break

                msg = PeerMessage.from_json(data.decode().strip())

                if msg.msg_type == MessageType.DISCONNECT:
                    break

                if msg.msg_type == MessageType.PING:
                    # Send pong
                    pong = PeerMessage(
                        msg_type=MessageType.PONG,
                        sender_id=self.my_id,
                        payload=msg.payload,
                    )
                    await self._send(pong)

                elif msg.msg_type == MessageType.PONG:
                    # Calculate latency
                    sent_time = msg.payload.get("timestamp", 0)
                    self.peer.latency_ms = (time.time() - sent_time) * 1000

                elif self._on_message:
                    self._on_message(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Receive error: {e}")
                break

        await self.disconnect()


class PeerServer:
    """
    سيرفر لاستقبال اتصالات الأطراف.
    """

    def __init__(
        self,
        my_id: str,
        port: int = 5960,
        on_connection: Optional[Callable[[PeerConnection], None]] = None,
    ):
        self.my_id = my_id
        self.port = port
        self._on_connection = on_connection

        self._server: Optional[asyncio.Server] = None
        self._connections: Dict[str, PeerConnection] = {}

    async def start(self) -> None:
        """بدء السيرفر."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            "0.0.0.0",
            self.port,
        )
        logger.info(f"Peer server started on port {self.port}")

    async def stop(self) -> None:
        """إيقاف السيرفر."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        for conn in list(self._connections.values()):
            await conn.disconnect()

        logger.info("Peer server stopped")

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """معالجة اتصال جديد."""
        addr = writer.get_extra_info("peername")
        logger.info(f"New connection from {addr}")

        try:
            # Wait for hello
            data = await asyncio.wait_for(reader.readline(), timeout=10.0)
            msg = PeerMessage.from_json(data.decode().strip())

            if msg.msg_type != MessageType.HELLO:
                writer.close()
                return

            peer_id = msg.payload.get("peer_id", msg.sender_id)

            # Create peer info
            peer = PeerInfo(
                peer_id=peer_id,
                device=DeviceInfo(
                    hostname="unknown",
                    platform="unknown",
                    platform_version="",
                    architecture="",
                    cpu_count=1,
                    memory_gb=0,
                ),
                app=AppInfo(),
                status=PeerStatus.CONNECTED,
                address=addr[0],
                port=addr[1],
                connected_at=time.time(),
            )

            # Create connection
            conn = PeerConnection(self.my_id, peer)
            conn._reader = reader
            conn._writer = writer
            conn._connected = True

            self._connections[peer_id] = conn

            if self._on_connection:
                self._on_connection(conn)

            # Start receiving
            await conn._receive_loop()

        except Exception as e:
            logger.error(f"Connection handling error: {e}")
        finally:
            writer.close()

    def get_connections(self) -> List[PeerConnection]:
        """الحصول على الاتصالات النشطة."""
        return list(self._connections.values())


class PeerManager:
    """
    مدير الاتصالات الموحد.

    يجمع بين الاكتشاف والاتصالات في واجهة واحدة.
    """

    def __init__(
        self,
        my_id: Optional[str] = None,
        discovery_port: int = 5959,
        connection_port: int = 5960,
    ):
        self.my_id = my_id or str(uuid.uuid4())[:8]
        self.discovery_port = discovery_port
        self.connection_port = connection_port

        # Components
        self.discovery = PeerDiscovery(
            my_id=self.my_id,
            discovery_port=discovery_port,
        )
        self.server = PeerServer(
            my_id=self.my_id,
            port=connection_port,
        )

        # Active connections
        self.connections: Dict[str, PeerConnection] = {}

        # Callbacks
        self._on_peer_discovered: List[Callable] = []
        self._on_peer_connected: List[Callable] = []
        self._on_peer_disconnected: List[Callable] = []
        self._on_message: List[Callable] = []

        # Setup internal callbacks
        self.discovery.on_peer_discovered(self._handle_peer_discovered)
        self.discovery.on_peer_lost(self._handle_peer_lost)
        self.server._on_connection = self._handle_incoming_connection

    def on_peer_discovered(self, callback: Callable) -> None:
        """إضافة callback عند اكتشاف peer."""
        self._on_peer_discovered.append(callback)

    def on_peer_connected(self, callback: Callable) -> None:
        """إضافة callback عند اتصال peer."""
        self._on_peer_connected.append(callback)

    def on_peer_disconnected(self, callback: Callable) -> None:
        """إضافة callback عند انفصال peer."""
        self._on_peer_disconnected.append(callback)

    def on_message(self, callback: Callable) -> None:
        """إضافة callback عند استلام رسالة."""
        self._on_message.append(callback)

    async def start(self) -> None:
        """بدء المدير."""
        await self.discovery.start()
        await self.server.start()
        logger.info(f"Peer manager started (ID: {self.my_id})")

    async def stop(self) -> None:
        """إيقاف المدير."""
        # Disconnect all
        for conn in list(self.connections.values()):
            await conn.disconnect()

        await self.server.stop()
        await self.discovery.stop()
        logger.info("Peer manager stopped")

    def _handle_peer_discovered(self, peer: PeerInfo) -> None:
        """معالجة اكتشاف peer جديد."""
        for cb in self._on_peer_discovered:
            try:
                cb(peer)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _handle_peer_lost(self, peer: PeerInfo) -> None:
        """معالجة فقدان peer."""
        if peer.peer_id in self.connections:
            conn = self.connections.pop(peer.peer_id)
            asyncio.create_task(conn.disconnect())

        for cb in self._on_peer_disconnected:
            try:
                cb(peer)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _handle_incoming_connection(self, conn: PeerConnection) -> None:
        """معالجة اتصال وارد."""
        self.connections[conn.peer.peer_id] = conn

        conn._on_message = self._handle_message
        conn._on_disconnect = lambda: self._handle_disconnection(conn.peer.peer_id)

        for cb in self._on_peer_connected:
            try:
                cb(conn.peer)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _handle_message(self, msg: PeerMessage) -> None:
        """معالجة رسالة."""
        for cb in self._on_message:
            try:
                cb(msg)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _handle_disconnection(self, peer_id: str) -> None:
        """معالجة انفصال."""
        peer = self.discovery.get_peer(peer_id)
        if peer:
            for cb in self._on_peer_disconnected:
                try:
                    cb(peer)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

    async def connect_to_peer(self, peer_id: str) -> bool:
        """الاتصال بـ peer."""
        peer = self.discovery.get_peer(peer_id)
        if not peer:
            return False

        conn = PeerConnection(
            my_id=self.my_id,
            peer_info=peer,
            on_message=self._handle_message,
            on_disconnect=lambda: self._handle_disconnection(peer_id),
        )

        if await conn.connect(self.connection_port):
            self.connections[peer_id] = conn
            for cb in self._on_peer_connected:
                try:
                    cb(peer)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
            return True

        return False

    async def disconnect_from_peer(self, peer_id: str) -> None:
        """قطع الاتصال مع peer."""
        if peer_id in self.connections:
            conn = self.connections.pop(peer_id)
            await conn.disconnect()

    async def send_message(self, peer_id: str, content: str, metadata: Optional[Dict] = None) -> bool:
        """إرسال رسالة لـ peer."""
        conn = self.connections.get(peer_id)
        if conn:
            return await conn.send_message(content, metadata)
        return False

    async def broadcast_message(self, content: str, metadata: Optional[Dict] = None) -> int:
        """إرسال رسالة لجميع المتصلين."""
        sent = 0
        for conn in self.connections.values():
            if await conn.send_message(content, metadata):
                sent += 1
        return sent

    def get_peers(self) -> List[Dict]:
        """الحصول على قائمة الأطراف."""
        return [peer.to_dict() for peer in self.discovery.get_peers()]

    def get_connected_peers(self) -> List[Dict]:
        """الحصول على الأطراف المتصلة."""
        return [
            conn.peer.to_dict()
            for conn in self.connections.values()
            if conn.is_connected
        ]

    def get_my_info(self) -> Dict:
        """الحصول على معلوماتي."""
        return self.discovery.get_my_info()

    def block_peer(self, peer_id: str) -> None:
        """حظر peer."""
        self.discovery.block_peer(peer_id)
        if peer_id in self.connections:
            asyncio.create_task(self.disconnect_from_peer(peer_id))

    def unblock_peer(self, peer_id: str) -> None:
        """إلغاء حظر peer."""
        self.discovery.unblock_peer(peer_id)
