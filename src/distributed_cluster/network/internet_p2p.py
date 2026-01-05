"""
Internet P2P - التواصل عبر الإنترنت
=====================================

نظام P2P للتواصل عبر الإنترنت:
- اتصال مباشر عبر IP العام
- نظام موافقة/رفض الاتصالات
- مشاركة كاملة للمعلومات
- كود اتصال سهل للمشاركة
- دعم NAT traversal

Features:
- Direct internet connection via public IP
- Connection approval/rejection system
- Full info sharing between peers
- Easy connection codes
- Signaling server for NAT traversal
"""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from distributed_cluster.network.peer_discovery import (
    AppInfo,
    DeviceInfo,
    MessageType,
    PeerMessage,
    PeerStatus,
)

logger = logging.getLogger(__name__)


class ConnectionRequestStatus(str, Enum):
    """حالة طلب الاتصال."""

    PENDING = "pending"  # في الانتظار
    APPROVED = "approved"  # موافق عليه
    REJECTED = "rejected"  # مرفوض
    EXPIRED = "expired"  # منتهي الصلاحية
    CANCELLED = "cancelled"  # ملغي


class InternetMessageType(str, Enum):
    """أنواع رسائل الإنترنت."""

    # Connection handshake
    CONNECTION_REQUEST = "connection_request"  # طلب اتصال
    CONNECTION_RESPONSE = "connection_response"  # رد على طلب الاتصال
    CONNECTION_APPROVED = "connection_approved"  # موافقة على الاتصال
    CONNECTION_REJECTED = "connection_rejected"  # رفض الاتصال

    # Info sharing
    FULL_INFO_REQUEST = "full_info_request"  # طلب معلومات كاملة
    FULL_INFO_RESPONSE = "full_info_response"  # رد المعلومات الكاملة

    # Keepalive
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"

    # Data
    DATA = "data"
    FILE_TRANSFER = "file_transfer"
    COMMAND = "command"
    COMMAND_RESULT = "command_result"


@dataclass
class ConnectionRequest:
    """طلب اتصال."""

    request_id: str
    requester_id: str
    requester_info: Dict[str, Any]
    target_id: str
    status: ConnectionRequestStatus = ConnectionRequestStatus.PENDING
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    message: str = ""
    connection_code: str = ""

    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + 300  # 5 minutes default

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> Dict:
        return {
            "request_id": self.request_id,
            "requester_id": self.requester_id,
            "requester_info": self.requester_info,
            "target_id": self.target_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "message": self.message,
            "connection_code": self.connection_code,
        }


@dataclass
class SharedInfo:
    """المعلومات المشاركة الكاملة."""

    peer_id: str
    device: DeviceInfo
    app: AppInfo

    # معلومات إضافية
    public_ip: str = ""
    local_ips: List[str] = field(default_factory=list)
    connection_port: int = 5960

    # قدرات
    capabilities: List[str] = field(default_factory=list)
    services: Dict[str, Any] = field(default_factory=dict)

    # معلومات النظام
    uptime_seconds: float = 0.0
    connected_peers_count: int = 0

    # إحصائيات
    total_connections: int = 0
    successful_jobs: int = 0
    failed_jobs: int = 0

    # metadata
    custom_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "peer_id": self.peer_id,
            "device": asdict(self.device),
            "app": asdict(self.app),
            "public_ip": self.public_ip,
            "local_ips": self.local_ips,
            "connection_port": self.connection_port,
            "capabilities": self.capabilities,
            "services": self.services,
            "uptime_seconds": self.uptime_seconds,
            "connected_peers_count": self.connected_peers_count,
            "total_connections": self.total_connections,
            "successful_jobs": self.successful_jobs,
            "failed_jobs": self.failed_jobs,
            "custom_data": self.custom_data,
        }


def generate_connection_code(peer_id: str, address: str, port: int, secret: str = "") -> str:
    """
    إنشاء كود اتصال سهل المشاركة.

    الكود يحتوي على: IP:PORT:PEER_ID:TOKEN
    مشفر بـ base64 للسهولة
    """
    if not secret:
        secret = secrets.token_hex(8)

    data = f"{address}:{port}:{peer_id}:{secret}"
    encoded = base64.urlsafe_b64encode(data.encode()).decode()

    # تقسيم لسهولة القراءة: XXXX-XXXX-XXXX
    chunks = [encoded[i : i + 4] for i in range(0, len(encoded), 4)]
    return "-".join(chunks[:4])  # أول 4 أجزاء فقط


def parse_connection_code(code: str) -> Optional[Dict[str, str]]:
    """
    تحليل كود الاتصال.

    Returns:
        Dict with address, port, peer_id, token or None if invalid
    """
    try:
        # إزالة الفواصل
        clean_code = code.replace("-", "")

        # إضافة padding إذا لزم
        padding = 4 - len(clean_code) % 4
        if padding != 4:
            clean_code += "=" * padding

        decoded = base64.urlsafe_b64decode(clean_code).decode()
        parts = decoded.split(":")

        if len(parts) >= 3:
            return {
                "address": parts[0],
                "port": int(parts[1]),
                "peer_id": parts[2],
                "token": parts[3] if len(parts) > 3 else "",
            }
    except Exception as e:
        logger.debug(f"Invalid connection code: {e}")

    return None


async def get_public_ip() -> str:
    """الحصول على عنوان IP العام."""
    import aiohttp

    services = [
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://ifconfig.me/ip",
        "https://api.my-ip.io/ip",
    ]

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
        for service in services:
            try:
                async with session.get(service) as resp:
                    if resp.status == 200:
                        ip = (await resp.text()).strip()
                        if ip:
                            return ip
            except Exception:
                continue

    return ""


class InternetPeerConnection:
    """
    اتصال P2P عبر الإنترنت.

    يدعم:
    - الاتصال المباشر عبر IP العام
    - نظام الموافقة على الاتصالات
    - مشاركة المعلومات الكاملة
    """

    def __init__(
        self,
        my_id: str,
        my_info: SharedInfo,
        peer_id: str,
        on_message: Optional[Callable[[PeerMessage], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
        on_info_updated: Optional[Callable[[SharedInfo], None]] = None,
    ):
        self.my_id = my_id
        self.my_info = my_info
        self.peer_id = peer_id

        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._on_info_updated = on_info_updated

        # Peer info
        self.peer_info: Optional[SharedInfo] = None
        self.peer_status = PeerStatus.DISCONNECTED

        # Connection
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._approved = False

        # Tasks
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Stats
        self.connected_at: Optional[float] = None
        self.last_heartbeat: float = 0.0
        self.latency_ms: float = 0.0
        self.bytes_sent: int = 0
        self.bytes_received: int = 0

    @property
    def is_connected(self) -> bool:
        return self._connected and self._approved

    async def connect(
        self,
        address: str,
        port: int,
        timeout: float = 30.0,
        connection_code: str = "",
    ) -> bool:
        """الاتصال بـ peer عبر الإنترنت."""
        try:
            logger.info(f"Connecting to {address}:{port}...")
            self.peer_status = PeerStatus.CONNECTING

            # Open connection
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(address, port),
                timeout=timeout,
            )

            self._connected = True

            # Send connection request
            request = PeerMessage(
                msg_type=MessageType.HELLO,
                sender_id=self.my_id,
                payload={
                    "type": InternetMessageType.CONNECTION_REQUEST.value,
                    "peer_id": self.my_id,
                    "info": self.my_info.to_dict(),
                    "connection_code": connection_code,
                    "message": "طلب اتصال P2P عبر الإنترنت",
                },
            )
            await self._send(request)

            # Wait for response
            response = await self._receive_one(timeout=30.0)

            if not response:
                await self._close()
                return False

            resp_type = response.payload.get("type")

            if resp_type == InternetMessageType.CONNECTION_APPROVED.value:
                self._approved = True
                self.connected_at = time.time()
                self.peer_status = PeerStatus.CONNECTED

                # Parse peer info
                peer_info_data = response.payload.get("info", {})
                self.peer_info = self._parse_shared_info(peer_info_data)

                # Start background tasks
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                logger.info(f"Connected and approved by {self.peer_id}")
                return True

            elif resp_type == InternetMessageType.CONNECTION_REJECTED.value:
                reason = response.payload.get("reason", "غير محدد")
                logger.warning(f"Connection rejected: {reason}")
                await self._close()
                return False

            else:
                logger.warning(f"Unexpected response: {resp_type}")
                await self._close()
                return False

        except asyncio.TimeoutError:
            logger.error("Connection timeout")
            await self._close()
            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            await self._close()
            return False

    async def disconnect(self) -> None:
        """قطع الاتصال."""
        if not self._connected:
            return

        try:
            msg = PeerMessage(
                msg_type=MessageType.DISCONNECT,
                sender_id=self.my_id,
            )
            await self._send(msg)
        except Exception:
            pass

        await self._close()

    async def _close(self) -> None:
        """إغلاق الاتصال."""
        self._connected = False
        self._approved = False
        self.peer_status = PeerStatus.DISCONNECTED

        # Cancel tasks
        for task in [self._receive_task, self._heartbeat_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close writer
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass

        self._reader = None
        self._writer = None

        if self._on_disconnect:
            self._on_disconnect()

    async def send_message(self, content: str, metadata: Optional[Dict] = None) -> bool:
        """إرسال رسالة."""
        if not self.is_connected:
            return False

        msg = PeerMessage(
            msg_type=MessageType.MESSAGE,
            sender_id=self.my_id,
            payload={
                "type": InternetMessageType.DATA.value,
                "content": content,
                "metadata": metadata or {},
            },
        )
        return await self._send(msg)

    async def request_full_info(self) -> Optional[SharedInfo]:
        """طلب المعلومات الكاملة من الـ peer."""
        if not self.is_connected:
            return None

        msg = PeerMessage(
            msg_type=MessageType.INFO_REQUEST,
            sender_id=self.my_id,
            payload={"type": InternetMessageType.FULL_INFO_REQUEST.value},
        )
        await self._send(msg)

        # Wait for response (simplified)
        await asyncio.sleep(0.5)
        return self.peer_info

    async def send_command(self, command: str, args: Optional[Dict] = None) -> bool:
        """إرسال أمر للتنفيذ."""
        if not self.is_connected:
            return False

        msg = PeerMessage(
            msg_type=MessageType.COMMAND,
            sender_id=self.my_id,
            payload={
                "type": InternetMessageType.COMMAND.value,
                "command": command,
                "args": args or {},
            },
        )
        return await self._send(msg)

    async def _send(self, msg: PeerMessage) -> bool:
        """إرسال رسالة."""
        if not self._writer:
            return False

        try:
            data = msg.to_json().encode() + b"\n"
            self._writer.write(data)
            await self._writer.drain()
            self.bytes_sent += len(data)
            return True
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    async def _receive_one(self, timeout: float = 10.0) -> Optional[PeerMessage]:
        """استقبال رسالة واحدة."""
        if not self._reader:
            return None

        try:
            data = await asyncio.wait_for(
                self._reader.readline(),
                timeout=timeout,
            )

            if not data:
                return None

            self.bytes_received += len(data)
            return PeerMessage.from_json(data.decode().strip())

        except Exception as e:
            logger.debug(f"Receive error: {e}")
            return None

    async def _receive_loop(self) -> None:
        """حلقة استقبال الرسائل."""
        while self._connected and self._reader:
            try:
                data = await self._reader.readline()

                if not data:
                    break

                self.bytes_received += len(data)
                msg = PeerMessage.from_json(data.decode().strip())

                await self._handle_message(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Receive loop error: {e}")
                await asyncio.sleep(0.1)

        await self._close()

    async def _handle_message(self, msg: PeerMessage) -> None:
        """معالجة رسالة."""
        msg_type = msg.payload.get("type", msg.msg_type.value)

        if msg_type == InternetMessageType.HEARTBEAT.value:
            # Respond to heartbeat
            ack = PeerMessage(
                msg_type=MessageType.PONG,
                sender_id=self.my_id,
                payload={
                    "type": InternetMessageType.HEARTBEAT_ACK.value,
                    "timestamp": msg.payload.get("timestamp"),
                },
            )
            await self._send(ack)

        elif msg_type == InternetMessageType.HEARTBEAT_ACK.value:
            sent_time = msg.payload.get("timestamp", 0)
            if sent_time:
                self.latency_ms = (time.time() - sent_time) * 1000
            self.last_heartbeat = time.time()

        elif msg_type == InternetMessageType.FULL_INFO_RESPONSE.value:
            info_data = msg.payload.get("info", {})
            self.peer_info = self._parse_shared_info(info_data)

            if self._on_info_updated and self.peer_info:
                self._on_info_updated(self.peer_info)

        elif msg.msg_type == MessageType.DISCONNECT:
            await self._close()

        elif self._on_message:
            self._on_message(msg)

    async def _heartbeat_loop(self) -> None:
        """حلقة heartbeat للحفاظ على الاتصال."""
        while self._connected:
            try:
                await asyncio.sleep(15)

                if not self._connected:
                    break

                msg = PeerMessage(
                    msg_type=MessageType.PING,
                    sender_id=self.my_id,
                    payload={
                        "type": InternetMessageType.HEARTBEAT.value,
                        "timestamp": time.time(),
                    },
                )
                await self._send(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Heartbeat error: {e}")

    def _parse_shared_info(self, data: Dict) -> SharedInfo:
        """تحليل معلومات مشتركة."""
        device_data = data.get("device", {})
        app_data = data.get("app", {})

        device = DeviceInfo(
            hostname=device_data.get("hostname", "unknown"),
            platform=device_data.get("platform", "unknown"),
            platform_version=device_data.get("platform_version", ""),
            architecture=device_data.get("architecture", ""),
            cpu_count=device_data.get("cpu_count", 1),
            memory_gb=device_data.get("memory_gb", 0),
            ip_addresses=device_data.get("ip_addresses", []),
            username=device_data.get("username", ""),
        )

        app = AppInfo(
            app_name=app_data.get("app_name", "Unknown"),
            app_version=app_data.get("app_version", "0.0.0"),
            app_type=app_data.get("app_type", "unknown"),
            capabilities=app_data.get("capabilities", []),
            services=app_data.get("services", {}),
        )

        return SharedInfo(
            peer_id=data.get("peer_id", ""),
            device=device,
            app=app,
            public_ip=data.get("public_ip", ""),
            local_ips=data.get("local_ips", []),
            connection_port=data.get("connection_port", 5960),
            capabilities=data.get("capabilities", []),
            services=data.get("services", {}),
            uptime_seconds=data.get("uptime_seconds", 0),
            connected_peers_count=data.get("connected_peers_count", 0),
            total_connections=data.get("total_connections", 0),
            successful_jobs=data.get("successful_jobs", 0),
            failed_jobs=data.get("failed_jobs", 0),
            custom_data=data.get("custom_data", {}),
        )


class InternetP2PServer:
    """
    سيرفر P2P عبر الإنترنت.

    يستقبل الاتصالات ويدير نظام الموافقة.
    """

    def __init__(
        self,
        my_id: str,
        my_info: SharedInfo,
        port: int = 5960,
        auto_approve: bool = False,
        on_connection_request: Optional[Callable[[ConnectionRequest], None]] = None,
        on_connection: Optional[Callable[[InternetPeerConnection], None]] = None,
    ):
        self.my_id = my_id
        self.my_info = my_info
        self.port = port
        self.auto_approve = auto_approve

        self._on_connection_request = on_connection_request
        self._on_connection = on_connection

        self._server: Optional[asyncio.Server] = None
        self._connections: Dict[str, InternetPeerConnection] = {}
        self._pending_requests: Dict[str, ConnectionRequest] = {}
        self._pending_writers: Dict[str, asyncio.StreamWriter] = {}

        # Stats
        self.total_connections = 0
        self.start_time = time.time()

    async def start(self) -> None:
        """بدء السيرفر."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            "0.0.0.0",
            self.port,
        )

        # Get public IP
        self.my_info.public_ip = await get_public_ip()

        logger.info(f"Internet P2P server started on port {self.port}")
        logger.info(f"Public IP: {self.my_info.public_ip}")

    async def stop(self) -> None:
        """إيقاف السيرفر."""
        # Disconnect all
        for conn in list(self._connections.values()):
            await conn.disconnect()

        # Close pending
        for writer in self._pending_writers.values():
            try:
                writer.close()
            except Exception:
                pass

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        logger.info("Internet P2P server stopped")

    def get_connection_code(self) -> str:
        """الحصول على كود الاتصال للمشاركة."""
        return generate_connection_code(
            self.my_id,
            self.my_info.public_ip or "localhost",
            self.port,
        )

    def get_pending_requests(self) -> List[Dict]:
        """الحصول على طلبات الاتصال المعلقة."""
        # Clean expired
        time.time()
        expired = [req_id for req_id, req in self._pending_requests.items() if req.is_expired()]
        for req_id in expired:
            self._pending_requests.pop(req_id, None)
            self._pending_writers.pop(req_id, None)

        return [req.to_dict() for req in self._pending_requests.values()]

    async def approve_request(self, request_id: str) -> bool:
        """الموافقة على طلب اتصال."""
        request = self._pending_requests.get(request_id)
        writer = self._pending_writers.get(request_id)

        if not request or not writer:
            return False

        try:
            # Send approval
            response = PeerMessage(
                msg_type=MessageType.HELLO,
                sender_id=self.my_id,
                payload={
                    "type": InternetMessageType.CONNECTION_APPROVED.value,
                    "peer_id": self.my_id,
                    "info": self.my_info.to_dict(),
                },
            )

            data = response.to_json().encode() + b"\n"
            writer.write(data)
            await writer.drain()

            request.status = ConnectionRequestStatus.APPROVED

            # Clean up pending
            self._pending_requests.pop(request_id, None)
            self._pending_writers.pop(request_id, None)

            logger.info(f"Approved connection request: {request_id}")
            return True

        except Exception as e:
            logger.error(f"Error approving request: {e}")
            return False

    async def reject_request(self, request_id: str, reason: str = "") -> bool:
        """رفض طلب اتصال."""
        request = self._pending_requests.get(request_id)
        writer = self._pending_writers.get(request_id)

        if not request or not writer:
            return False

        try:
            response = PeerMessage(
                msg_type=MessageType.HELLO,
                sender_id=self.my_id,
                payload={
                    "type": InternetMessageType.CONNECTION_REJECTED.value,
                    "reason": reason or "تم رفض الاتصال",
                },
            )

            data = response.to_json().encode() + b"\n"
            writer.write(data)
            await writer.drain()

            request.status = ConnectionRequestStatus.REJECTED

            # Close and clean
            writer.close()
            self._pending_requests.pop(request_id, None)
            self._pending_writers.pop(request_id, None)

            logger.info(f"Rejected connection request: {request_id}")
            return True

        except Exception as e:
            logger.error(f"Error rejecting request: {e}")
            return False

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """معالجة اتصال وارد."""
        addr = writer.get_extra_info("peername")
        logger.info(f"Incoming connection from {addr}")

        self.total_connections += 1

        try:
            # Wait for connection request
            data = await asyncio.wait_for(reader.readline(), timeout=30.0)
            msg = PeerMessage.from_json(data.decode().strip())

            req_type = msg.payload.get("type")

            if req_type != InternetMessageType.CONNECTION_REQUEST.value:
                writer.close()
                return

            peer_id = msg.payload.get("peer_id", msg.sender_id)
            peer_info = msg.payload.get("info", {})
            connection_code = msg.payload.get("connection_code", "")
            request_message = msg.payload.get("message", "")

            # Create request
            request = ConnectionRequest(
                request_id=str(uuid.uuid4()),
                requester_id=peer_id,
                requester_info=peer_info,
                target_id=self.my_id,
                message=request_message,
                connection_code=connection_code,
            )

            if self.auto_approve:
                # Auto approve
                await self._complete_connection(reader, writer, request, peer_info)
            else:
                # Store for manual approval
                self._pending_requests[request.request_id] = request
                self._pending_writers[request.request_id] = writer

                # Notify
                if self._on_connection_request:
                    self._on_connection_request(request)

                logger.info(f"Connection request pending: {request.request_id} from {peer_id}")

        except asyncio.TimeoutError:
            logger.debug("Connection timeout")
            writer.close()
        except Exception as e:
            logger.error(f"Connection handling error: {e}")
            writer.close()

    async def _complete_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        request: ConnectionRequest,
        peer_info: Dict,
    ) -> None:
        """إتمام الاتصال بعد الموافقة."""
        try:
            # Send approval
            response = PeerMessage(
                msg_type=MessageType.HELLO,
                sender_id=self.my_id,
                payload={
                    "type": InternetMessageType.CONNECTION_APPROVED.value,
                    "peer_id": self.my_id,
                    "info": self.my_info.to_dict(),
                },
            )

            data = response.to_json().encode() + b"\n"
            writer.write(data)
            await writer.drain()

            # Create connection
            device_data = peer_info.get("device", {})
            app_data = peer_info.get("app", {})

            device = DeviceInfo(
                hostname=device_data.get("hostname", "unknown"),
                platform=device_data.get("platform", "unknown"),
                platform_version=device_data.get("platform_version", ""),
                architecture=device_data.get("architecture", ""),
                cpu_count=device_data.get("cpu_count", 1),
                memory_gb=device_data.get("memory_gb", 0),
                ip_addresses=device_data.get("ip_addresses", []),
                username=device_data.get("username", ""),
            )

            app = AppInfo(
                app_name=app_data.get("app_name", "Unknown"),
                app_version=app_data.get("app_version", "0.0.0"),
                app_type=app_data.get("app_type", "unknown"),
                capabilities=app_data.get("capabilities", []),
                services=app_data.get("services", {}),
            )

            shared_info = SharedInfo(
                peer_id=request.requester_id,
                device=device,
                app=app,
                public_ip=peer_info.get("public_ip", ""),
                local_ips=peer_info.get("local_ips", []),
                connection_port=peer_info.get("connection_port", 5960),
                capabilities=peer_info.get("capabilities", []),
                services=peer_info.get("services", {}),
            )

            conn = InternetPeerConnection(
                my_id=self.my_id,
                my_info=self.my_info,
                peer_id=request.requester_id,
            )

            conn._reader = reader
            conn._writer = writer
            conn._connected = True
            conn._approved = True
            conn.connected_at = time.time()
            conn.peer_info = shared_info
            conn.peer_status = PeerStatus.CONNECTED

            self._connections[request.requester_id] = conn

            # Start receive loop
            conn._receive_task = asyncio.create_task(conn._receive_loop())
            conn._heartbeat_task = asyncio.create_task(conn._heartbeat_loop())

            if self._on_connection:
                self._on_connection(conn)

            logger.info(f"Connection completed: {request.requester_id}")
            request.status = ConnectionRequestStatus.APPROVED

        except Exception as e:
            logger.error(f"Error completing connection: {e}")
            writer.close()

    def get_connections(self) -> List[InternetPeerConnection]:
        """الحصول على الاتصالات النشطة."""
        return [c for c in self._connections.values() if c.is_connected]


class InternetP2PManager:
    """
    مدير P2P عبر الإنترنت الموحد.

    يجمع بين السيرفر والاتصالات الصادرة.
    """

    def __init__(
        self,
        my_id: Optional[str] = None,
        port: int = 5960,
        auto_approve: bool = False,
    ):
        self.my_id = my_id or str(uuid.uuid4())[:8]
        self.port = port
        self.auto_approve = auto_approve

        # My info
        self.my_info = SharedInfo(
            peer_id=self.my_id,
            device=DeviceInfo.from_system(),
            app=AppInfo(),
            connection_port=port,
        )

        # Server
        self.server = InternetP2PServer(
            my_id=self.my_id,
            my_info=self.my_info,
            port=port,
            auto_approve=auto_approve,
        )

        # Outgoing connections
        self.connections: Dict[str, InternetPeerConnection] = {}

        # Callbacks
        self._on_connection_request: List[Callable] = []
        self._on_connected: List[Callable] = []
        self._on_disconnected: List[Callable] = []
        self._on_message: List[Callable] = []

        # Setup server callbacks
        self.server._on_connection_request = self._handle_connection_request
        self.server._on_connection = self._handle_incoming_connection

        # Start time
        self.start_time = time.time()

    def on_connection_request(self, callback: Callable) -> None:
        """إضافة callback لطلب اتصال جديد."""
        self._on_connection_request.append(callback)

    def on_connected(self, callback: Callable) -> None:
        """إضافة callback للاتصال."""
        self._on_connected.append(callback)

    def on_disconnected(self, callback: Callable) -> None:
        """إضافة callback للانفصال."""
        self._on_disconnected.append(callback)

    def on_message(self, callback: Callable) -> None:
        """إضافة callback للرسائل."""
        self._on_message.append(callback)

    async def start(self) -> None:
        """بدء المدير."""
        await self.server.start()
        self.my_info.public_ip = self.server.my_info.public_ip
        logger.info(f"Internet P2P manager started (ID: {self.my_id})")

    async def stop(self) -> None:
        """إيقاف المدير."""
        for conn in list(self.connections.values()):
            await conn.disconnect()

        await self.server.stop()
        logger.info("Internet P2P manager stopped")

    def get_connection_code(self) -> str:
        """الحصول على كود الاتصال."""
        return self.server.get_connection_code()

    async def connect_by_code(self, code: str) -> bool:
        """الاتصال باستخدام كود."""
        parsed = parse_connection_code(code)
        if not parsed:
            logger.error("Invalid connection code")
            return False

        return await self.connect_to(
            address=parsed["address"],
            port=parsed["port"],
            connection_code=code,
        )

    async def connect_to(
        self,
        address: str,
        port: int = 5960,
        connection_code: str = "",
    ) -> bool:
        """الاتصال بـ peer."""
        peer_id = f"{address}:{port}"

        conn = InternetPeerConnection(
            my_id=self.my_id,
            my_info=self.my_info,
            peer_id=peer_id,
            on_message=self._handle_message,
            on_disconnect=lambda: self._handle_disconnect(peer_id),
        )

        if await conn.connect(address, port, connection_code=connection_code):
            # Update peer_id with actual ID
            if conn.peer_info:
                actual_id = conn.peer_info.peer_id
                conn.peer_id = actual_id
                peer_id = actual_id

            self.connections[peer_id] = conn

            for cb in self._on_connected:
                try:
                    cb(conn)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

            return True

        return False

    async def disconnect(self, peer_id: str) -> None:
        """قطع الاتصال."""
        conn = self.connections.pop(peer_id, None)
        if conn:
            await conn.disconnect()

    async def send_message(self, peer_id: str, content: str, metadata: Optional[Dict] = None) -> bool:
        """إرسال رسالة."""
        conn = self.connections.get(peer_id) or self._get_server_connection(peer_id)
        if conn:
            return await conn.send_message(content, metadata)
        return False

    async def broadcast(self, content: str, metadata: Optional[Dict] = None) -> int:
        """إرسال للجميع."""
        sent = 0
        all_conns = list(self.connections.values()) + self.server.get_connections()

        for conn in all_conns:
            if await conn.send_message(content, metadata):
                sent += 1

        return sent

    def get_pending_requests(self) -> List[Dict]:
        """الحصول على طلبات الاتصال المعلقة."""
        return self.server.get_pending_requests()

    async def approve_request(self, request_id: str) -> bool:
        """الموافقة على طلب اتصال."""
        return await self.server.approve_request(request_id)

    async def reject_request(self, request_id: str, reason: str = "") -> bool:
        """رفض طلب اتصال."""
        return await self.server.reject_request(request_id, reason)

    def get_all_connections(self) -> List[Dict]:
        """الحصول على جميع الاتصالات."""
        result = []

        for conn in self.connections.values():
            if conn.peer_info:
                result.append(
                    {
                        "peer_id": conn.peer_id,
                        "direction": "outgoing",
                        "connected": conn.is_connected,
                        "connected_at": conn.connected_at,
                        "latency_ms": conn.latency_ms,
                        "info": conn.peer_info.to_dict(),
                    }
                )

        for conn in self.server.get_connections():
            if conn.peer_info:
                result.append(
                    {
                        "peer_id": conn.peer_id,
                        "direction": "incoming",
                        "connected": conn.is_connected,
                        "connected_at": conn.connected_at,
                        "latency_ms": conn.latency_ms,
                        "info": conn.peer_info.to_dict(),
                    }
                )

        return result

    def get_my_info(self) -> Dict:
        """الحصول على معلوماتي."""
        self.my_info.uptime_seconds = time.time() - self.start_time
        self.my_info.connected_peers_count = len(self.get_all_connections())
        return self.my_info.to_dict()

    def _get_server_connection(self, peer_id: str) -> Optional[InternetPeerConnection]:
        """البحث عن اتصال في السيرفر."""
        return self.server._connections.get(peer_id)

    def _handle_connection_request(self, request: ConnectionRequest) -> None:
        """معالجة طلب اتصال."""
        for cb in self._on_connection_request:
            try:
                cb(request)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _handle_incoming_connection(self, conn: InternetPeerConnection) -> None:
        """معالجة اتصال وارد."""
        conn._on_message = self._handle_message
        conn._on_disconnect = lambda: self._handle_disconnect(conn.peer_id)

        for cb in self._on_connected:
            try:
                cb(conn)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _handle_message(self, msg: PeerMessage) -> None:
        """معالجة رسالة."""
        for cb in self._on_message:
            try:
                cb(msg)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _handle_disconnect(self, peer_id: str) -> None:
        """معالجة انفصال."""
        self.connections.pop(peer_id, None)

        for cb in self._on_disconnected:
            try:
                cb(peer_id)
            except Exception as e:
                logger.error(f"Callback error: {e}")
