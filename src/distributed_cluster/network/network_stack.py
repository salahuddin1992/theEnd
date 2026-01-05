"""
Network Stack - مكدس الشبكة الكامل
===================================

نظام شبكة متكامل يعمل بشكل مستقل:
- DNS Server: خادم أسماء محلي
- Router: توجيه الحزم بين الأطراف
- NAT Traversal: اختراق الـ NAT
- Relay Server: سيرفر وسيط للاتصالات
- Peer Registry: سجل الأطراف

كل شيء تحت لوحة تحكم واحدة.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ==========================================
# DNS Server - خادم الأسماء
# ==========================================


class DNSRecordType(str, Enum):
    """أنواع سجلات DNS."""

    A = "A"  # IPv4 address
    AAAA = "AAAA"  # IPv6 address
    CNAME = "CNAME"  # Canonical name
    TXT = "TXT"  # Text record
    SRV = "SRV"  # Service record
    PTR = "PTR"  # Pointer (reverse DNS)
    PEER = "PEER"  # Custom peer record


@dataclass
class DNSRecord:
    """سجل DNS."""

    name: str
    record_type: DNSRecordType
    value: str
    ttl: int = 300  # Time to live in seconds
    priority: int = 0  # For SRV records
    port: int = 0  # For SRV records
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        return time.time() - self.updated_at > self.ttl

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.record_type.value,
            "value": self.value,
            "ttl": self.ttl,
            "priority": self.priority,
            "port": self.port,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


class NebulaNetworkRegistry:
    """
    سجل الشبكة المركزي.

    يدير:
    - أسماء الأطراف (DNS)
    - عناوين IP
    - الخدمات المتاحة
    - معلومات التوجيه
    """

    def __init__(self, domain: str = "nebula.local"):
        self.domain = domain
        self.records: Dict[str, List[DNSRecord]] = {}
        self.reverse_records: Dict[str, str] = {}  # IP -> name
        self.peer_names: Dict[str, str] = {}  # peer_id -> name
        self.name_to_peer: Dict[str, str] = {}  # name -> peer_id

        # Statistics
        self.queries = 0
        self.cache_hits = 0

    def register_peer(
        self,
        peer_id: str,
        name: str,
        ip_address: str,
        port: int = 5960,
        services: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """تسجيل peer في الشبكة."""
        # Normalize name
        if not name.endswith(f".{self.domain}"):
            full_name = f"{name}.{self.domain}"
        else:
            full_name = name

        # A record for IP
        self._add_record(
            DNSRecord(
                name=full_name,
                record_type=DNSRecordType.A,
                value=ip_address,
                metadata={"peer_id": peer_id},
            )
        )

        # SRV record for main service
        self._add_record(
            DNSRecord(
                name=f"_nebula._tcp.{full_name}",
                record_type=DNSRecordType.SRV,
                value=full_name,
                port=port,
                priority=10,
            )
        )

        # Register additional services
        if services:
            for service_name, service_port in services.items():
                self._add_record(
                    DNSRecord(
                        name=f"_{service_name}._tcp.{full_name}",
                        record_type=DNSRecordType.SRV,
                        value=full_name,
                        port=service_port,
                        priority=10,
                    )
                )

        # PEER record with full info
        self._add_record(
            DNSRecord(
                name=full_name,
                record_type=DNSRecordType.PEER,
                value=json.dumps(
                    {
                        "peer_id": peer_id,
                        "ip": ip_address,
                        "port": port,
                        "services": services or {},
                        **(metadata or {}),
                    }
                ),
            )
        )

        # Reverse DNS
        self.reverse_records[ip_address] = full_name

        # Name mappings
        self.peer_names[peer_id] = full_name
        self.name_to_peer[full_name] = peer_id
        self.name_to_peer[name] = peer_id

        logger.info(f"Registered peer: {full_name} -> {ip_address}:{port}")
        return full_name

    def unregister_peer(self, peer_id: str) -> None:
        """إلغاء تسجيل peer."""
        name = self.peer_names.pop(peer_id, None)
        if name:
            self.records.pop(name, None)
            self.name_to_peer.pop(name, None)
            # Remove from reverse
            for ip, n in list(self.reverse_records.items()):
                if n == name:
                    del self.reverse_records[ip]
            logger.info(f"Unregistered peer: {name}")

    def _add_record(self, record: DNSRecord) -> None:
        """إضافة سجل."""
        if record.name not in self.records:
            self.records[record.name] = []

        # Update existing or add new
        for i, existing in enumerate(self.records[record.name]):
            if existing.record_type == record.record_type:
                self.records[record.name][i] = record
                return

        self.records[record.name].append(record)

    def resolve(self, name: str, record_type: DNSRecordType = DNSRecordType.A) -> Optional[DNSRecord]:
        """البحث عن سجل DNS."""
        self.queries += 1

        # Normalize name
        if not name.endswith(f".{self.domain}") and "." not in name:
            name = f"{name}.{self.domain}"

        records = self.records.get(name, [])
        for record in records:
            if record.record_type == record_type and not record.is_expired():
                self.cache_hits += 1
                return record

        return None

    def resolve_peer(self, name_or_id: str) -> Optional[Dict]:
        """البحث عن معلومات peer كاملة."""
        # Try as peer_id first
        if name_or_id in self.peer_names:
            name = self.peer_names[name_or_id]
        else:
            name = name_or_id

        record = self.resolve(name, DNSRecordType.PEER)
        if record:
            try:
                return json.loads(record.value)
            except json.JSONDecodeError:
                pass

        return None

    def reverse_lookup(self, ip_address: str) -> Optional[str]:
        """البحث العكسي عن اسم من IP."""
        return self.reverse_records.get(ip_address)

    def list_all_peers(self) -> List[Dict]:
        """قائمة جميع الأطراف المسجلين."""
        peers = []
        for peer_id, name in self.peer_names.items():
            info = self.resolve_peer(peer_id)
            if info:
                info["name"] = name
                peers.append(info)
        return peers

    def get_stats(self) -> Dict:
        """إحصائيات الـ DNS."""
        return {
            "total_records": sum(len(r) for r in self.records.values()),
            "total_peers": len(self.peer_names),
            "total_queries": self.queries,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": (self.cache_hits / self.queries * 100) if self.queries > 0 else 0,
        }


class SimpleDNSServer:
    """
    خادم DNS بسيط.

    يستجيب لاستعلامات DNS على المنفذ 5353 (mDNS).
    """

    def __init__(self, registry: NebulaNetworkRegistry, port: int = 5353):
        self.registry = registry
        self.port = port
        self._transport = None
        self._protocol = None

    async def start(self) -> None:
        """بدء خادم DNS."""
        loop = asyncio.get_event_loop()

        # Create UDP endpoint
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: DNSProtocol(self.registry),
            local_addr=("0.0.0.0", self.port),
        )

        logger.info(f"DNS server started on port {self.port}")

    async def stop(self) -> None:
        """إيقاف خادم DNS."""
        if self._transport:
            self._transport.close()
        logger.info("DNS server stopped")


class DNSProtocol(asyncio.DatagramProtocol):
    """بروتوكول DNS."""

    def __init__(self, registry: NebulaNetworkRegistry):
        self.registry = registry
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        """معالجة استعلام DNS."""
        try:
            # Simple DNS query parsing
            # This is a simplified implementation
            if len(data) < 12:
                return

            # Extract query name (simplified)
            query_start = 12
            name_parts = []
            pos = query_start

            while pos < len(data) and data[pos] != 0:
                length = data[pos]
                pos += 1
                if pos + length <= len(data):
                    name_parts.append(data[pos : pos + length].decode("utf-8", errors="ignore"))
                    pos += length

            if name_parts:
                query_name = ".".join(name_parts)
                record = self.registry.resolve(query_name, DNSRecordType.A)

                if record:
                    # Build simple response
                    response = self._build_response(data[:2], query_name, record.value)
                    self.transport.sendto(response, addr)

        except Exception as e:
            logger.debug(f"DNS query error: {e}")

    def _build_response(self, query_id: bytes, name: str, ip: str) -> bytes:
        """بناء رد DNS بسيط."""
        # This is a simplified DNS response
        # Transaction ID + Flags + Questions + Answers + Authority + Additional
        response = bytearray()
        response.extend(query_id)  # Transaction ID
        response.extend(b"\x81\x80")  # Flags: Standard response, no error
        response.extend(b"\x00\x01")  # Questions: 1
        response.extend(b"\x00\x01")  # Answers: 1
        response.extend(b"\x00\x00")  # Authority: 0
        response.extend(b"\x00\x00")  # Additional: 0

        # Question section
        for part in name.split("."):
            response.append(len(part))
            response.extend(part.encode())
        response.append(0)
        response.extend(b"\x00\x01")  # Type: A
        response.extend(b"\x00\x01")  # Class: IN

        # Answer section
        response.extend(b"\xc0\x0c")  # Pointer to name
        response.extend(b"\x00\x01")  # Type: A
        response.extend(b"\x00\x01")  # Class: IN
        response.extend(b"\x00\x00\x01\x2c")  # TTL: 300
        response.extend(b"\x00\x04")  # Data length: 4

        # IP address
        for octet in ip.split("."):
            response.append(int(octet))

        return bytes(response)


# ==========================================
# Router - الراوتر
# ==========================================


@dataclass
class Route:
    """مسار شبكي."""

    destination: str  # IP or CIDR
    gateway: str  # Next hop
    interface: str = "default"
    metric: int = 100
    peer_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


class NetworkRouter:
    """
    راوتر الشبكة.

    يدير:
    - جدول التوجيه
    - توجيه الحزم
    - NAT
    """

    def __init__(self, my_id: str):
        self.my_id = my_id
        self.routes: List[Route] = []
        self.nat_table: Dict[str, str] = {}  # internal -> external
        self.connections: Dict[str, "NetworkRouter"] = {}  # peer_id -> router

        # Statistics
        self.packets_routed = 0
        self.packets_dropped = 0

    def add_route(self, destination: str, gateway: str, metric: int = 100, peer_id: Optional[str] = None) -> None:
        """إضافة مسار."""
        route = Route(
            destination=destination,
            gateway=gateway,
            metric=metric,
            peer_id=peer_id,
        )
        self.routes.append(route)
        self.routes.sort(key=lambda r: r.metric)
        logger.info(f"Added route: {destination} via {gateway}")

    def remove_route(self, destination: str) -> None:
        """إزالة مسار."""
        self.routes = [r for r in self.routes if r.destination != destination]

    def get_route(self, destination: str) -> Optional[Route]:
        """البحث عن مسار للوجهة."""
        for route in self.routes:
            if self._matches(destination, route.destination):
                return route
        return None

    def _matches(self, ip: str, pattern: str) -> bool:
        """التحقق من تطابق IP مع النمط."""
        if pattern == "0.0.0.0/0" or pattern == "default":
            return True

        if "/" in pattern:
            # CIDR notation
            network, prefix = pattern.split("/")
            prefix = int(prefix)
            ip_int = self._ip_to_int(ip)
            net_int = self._ip_to_int(network)
            mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
            return (ip_int & mask) == (net_int & mask)

        return ip == pattern

    def _ip_to_int(self, ip: str) -> int:
        """تحويل IP إلى عدد."""
        parts = ip.split(".")
        return (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])

    def add_nat_mapping(self, internal: str, external: str) -> None:
        """إضافة تعيين NAT."""
        self.nat_table[internal] = external

    def translate_address(self, internal: str) -> str:
        """ترجمة عنوان عبر NAT."""
        return self.nat_table.get(internal, internal)

    def connect_router(self, peer_id: str, router: "NetworkRouter") -> None:
        """ربط براوتر آخر."""
        self.connections[peer_id] = router
        # Exchange routes
        for route in router.routes:
            if route.destination != "default":
                self.add_route(route.destination, router.my_id, route.metric + 1, peer_id)

    def get_routing_table(self) -> List[Dict]:
        """الحصول على جدول التوجيه."""
        return [route.to_dict() for route in self.routes]

    def get_stats(self) -> Dict:
        """إحصائيات الراوتر."""
        return {
            "routes": len(self.routes),
            "nat_mappings": len(self.nat_table),
            "connected_routers": len(self.connections),
            "packets_routed": self.packets_routed,
            "packets_dropped": self.packets_dropped,
        }


# ==========================================
# Relay Server - سيرفر الترحيل
# ==========================================


@dataclass
class RelaySession:
    """جلسة ترحيل."""

    session_id: str
    peer_a: str
    peer_b: str
    created_at: float = field(default_factory=time.time)
    bytes_transferred: int = 0
    last_activity: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "peer_a": self.peer_a,
            "peer_b": self.peer_b,
            "created_at": self.created_at,
            "bytes_transferred": self.bytes_transferred,
            "duration": time.time() - self.created_at,
        }


class RelayServer:
    """
    سيرفر ترحيل للاتصالات.

    يستخدم عندما لا يمكن الاتصال المباشر (NAT).
    """

    def __init__(self, port: int = 5961):
        self.port = port
        self.sessions: Dict[str, RelaySession] = {}
        self.peer_connections: Dict[str, asyncio.StreamWriter] = {}

        self._server: Optional[asyncio.Server] = None

        # Statistics
        self.total_bytes = 0
        self.total_sessions = 0

    async def start(self) -> None:
        """بدء سيرفر الترحيل."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            "0.0.0.0",
            self.port,
        )
        logger.info(f"Relay server started on port {self.port}")

    async def stop(self) -> None:
        """إيقاف سيرفر الترحيل."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        for writer in self.peer_connections.values():
            writer.close()

        logger.info("Relay server stopped")

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """معالجة اتصال وارد."""
        try:
            # Read registration
            data = await asyncio.wait_for(reader.readline(), timeout=10.0)
            msg = json.loads(data.decode())

            if msg.get("type") == "register":
                peer_id = msg.get("peer_id")
                self.peer_connections[peer_id] = writer
                logger.info(f"Relay: Peer registered: {peer_id}")

                # Handle relay requests
                while True:
                    data = await reader.readline()
                    if not data:
                        break

                    await self._handle_relay(peer_id, data)

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.debug(f"Relay connection error: {e}")
        finally:
            writer.close()

    async def _handle_relay(self, sender: str, data: bytes) -> None:
        """معالجة طلب ترحيل."""
        try:
            msg = json.loads(data.decode())
            target = msg.get("target")

            if target in self.peer_connections:
                writer = self.peer_connections[target]
                msg["sender"] = sender
                writer.write(json.dumps(msg).encode() + b"\n")
                await writer.drain()

                self.total_bytes += len(data)

                # Update or create session
                session_id = f"{min(sender, target)}-{max(sender, target)}"
                if session_id not in self.sessions:
                    self.sessions[session_id] = RelaySession(
                        session_id=session_id,
                        peer_a=sender,
                        peer_b=target,
                    )
                    self.total_sessions += 1

                self.sessions[session_id].bytes_transferred += len(data)
                self.sessions[session_id].last_activity = time.time()

        except Exception as e:
            logger.debug(f"Relay error: {e}")

    def get_sessions(self) -> List[Dict]:
        """الحصول على الجلسات النشطة."""
        return [s.to_dict() for s in self.sessions.values()]

    def get_stats(self) -> Dict:
        """إحصائيات سيرفر الترحيل."""
        return {
            "active_peers": len(self.peer_connections),
            "active_sessions": len(self.sessions),
            "total_sessions": self.total_sessions,
            "total_bytes": self.total_bytes,
            "total_mb": round(self.total_bytes / (1024 * 1024), 2),
        }


# ==========================================
# Network Node - عقدة الشبكة الكاملة
# ==========================================


@dataclass
class NodeIdentity:
    """هوية العقدة."""

    node_id: str
    name: str
    public_key: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def generate(cls, name: str) -> "NodeIdentity":
        """إنشاء هوية جديدة."""
        node_id = str(uuid.uuid4())[:8]
        # Simplified public key (in production, use proper crypto)
        public_key = hashlib.sha256(f"{node_id}-{name}-{time.time()}".encode()).hexdigest()[:32]

        return cls(
            node_id=node_id,
            name=name,
            public_key=public_key,
        )

    def to_dict(self) -> Dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "public_key": self.public_key,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


class NetworkNode:
    """
    عقدة شبكة كاملة.

    تجمع كل المكونات:
    - DNS
    - Router
    - Relay
    - Identity
    """

    def __init__(
        self,
        name: str,
        domain: str = "nebula.local",
        dns_port: int = 5353,
        relay_port: int = 5961,
        p2p_port: int = 5960,
    ):
        # Identity
        self.identity = NodeIdentity.generate(name)

        # Network components
        self.registry = NebulaNetworkRegistry(domain)
        self.dns_server = SimpleDNSServer(self.registry, dns_port)
        self.router = NetworkRouter(self.identity.node_id)
        self.relay = RelayServer(relay_port)

        # Configuration
        self.domain = domain
        self.p2p_port = p2p_port
        self.dns_port = dns_port
        self.relay_port = relay_port

        # State
        self.public_ip: str = ""
        self.local_ips: List[str] = []
        self.is_running = False
        self.start_time: float = 0

        # Callbacks
        self._on_peer_joined: List[Callable] = []
        self._on_peer_left: List[Callable] = []

    def on_peer_joined(self, callback: Callable) -> None:
        self._on_peer_joined.append(callback)

    def on_peer_left(self, callback: Callable) -> None:
        self._on_peer_left.append(callback)

    async def start(self) -> None:
        """بدء عقدة الشبكة."""
        if self.is_running:
            return

        self.start_time = time.time()

        # Get IPs
        await self._discover_ips()

        # Start components
        try:
            await self.dns_server.start()
        except Exception as e:
            logger.warning(f"Could not start DNS server: {e}")

        await self.relay.start()

        # Register self
        ip = self.local_ips[0] if self.local_ips else "127.0.0.1"
        self.registry.register_peer(
            peer_id=self.identity.node_id,
            name=self.identity.name,
            ip_address=ip,
            port=self.p2p_port,
            metadata=self.identity.to_dict(),
        )

        self.is_running = True
        logger.info(f"Network node started: {self.identity.name} ({self.identity.node_id})")

    async def stop(self) -> None:
        """إيقاف عقدة الشبكة."""
        if not self.is_running:
            return

        await self.dns_server.stop()
        await self.relay.stop()

        self.registry.unregister_peer(self.identity.node_id)
        self.is_running = False

        logger.info("Network node stopped")

    async def _discover_ips(self) -> None:
        """اكتشاف عناوين IP."""
        import socket

        # Local IPs
        try:
            import psutil

            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                        self.local_ips.append(addr.address)
        except ImportError:
            self.local_ips = [socket.gethostbyname(socket.gethostname())]

        # Public IP
        try:
            import aiohttp

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get("https://api.ipify.org") as resp:
                    if resp.status == 200:
                        self.public_ip = (await resp.text()).strip()
        except Exception:
            pass

    def register_peer(
        self,
        peer_id: str,
        name: str,
        ip_address: str,
        port: int = 5960,
        services: Optional[Dict[str, int]] = None,
    ) -> str:
        """تسجيل peer في الشبكة."""
        full_name = self.registry.register_peer(peer_id, name, ip_address, port, services)

        # Add route
        self.router.add_route(ip_address, ip_address, peer_id=peer_id)

        # Notify
        for cb in self._on_peer_joined:
            try:
                cb(peer_id, name, ip_address)
            except Exception as e:
                logger.error(f"Callback error: {e}")

        return full_name

    def unregister_peer(self, peer_id: str) -> None:
        """إلغاء تسجيل peer."""
        info = self.registry.resolve_peer(peer_id)
        self.registry.unregister_peer(peer_id)

        if info:
            self.router.remove_route(info.get("ip", ""))

        # Notify
        for cb in self._on_peer_left:
            try:
                cb(peer_id)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def resolve(self, name: str) -> Optional[Dict]:
        """البحث عن peer بالاسم."""
        return self.registry.resolve_peer(name)

    def get_all_peers(self) -> List[Dict]:
        """قائمة جميع الأطراف."""
        return self.registry.list_all_peers()

    def get_my_info(self) -> Dict:
        """معلوماتي."""
        return {
            "identity": self.identity.to_dict(),
            "domain": self.domain,
            "public_ip": self.public_ip,
            "local_ips": self.local_ips,
            "ports": {
                "p2p": self.p2p_port,
                "dns": self.dns_port,
                "relay": self.relay_port,
            },
            "uptime": time.time() - self.start_time if self.is_running else 0,
        }

    def get_network_stats(self) -> Dict:
        """إحصائيات الشبكة."""
        return {
            "node": self.get_my_info(),
            "dns": self.registry.get_stats(),
            "router": self.router.get_stats(),
            "relay": self.relay.get_stats(),
        }

    def get_routing_table(self) -> List[Dict]:
        """جدول التوجيه."""
        return self.router.get_routing_table()

    def get_dns_records(self) -> List[Dict]:
        """سجلات DNS."""
        records = []
        for name, recs in self.registry.records.items():
            for rec in recs:
                records.append(rec.to_dict())
        return records


# ==========================================
# Full Network Stack Manager
# ==========================================


class NetworkStackManager:
    """
    مدير مكدس الشبكة الكامل.

    يجمع كل شيء تحت واجهة واحدة.
    """

    def __init__(
        self,
        name: str = "NebulaNode",
        domain: str = "nebula.local",
    ):
        self.node = NetworkNode(name=name, domain=domain)

        # Integration with P2P
        self._p2p_manager = None

        # State
        self.is_initialized = False

    def set_p2p_manager(self, p2p_manager) -> None:
        """ربط مع مدير P2P."""
        self._p2p_manager = p2p_manager

        # Sync peers
        if p2p_manager:
            p2p_manager.on_connected(
                lambda conn: self.node.register_peer(
                    conn.peer_id,
                    conn.peer_info.device.hostname if conn.peer_info else conn.peer_id,
                    conn.peer_info.public_ip if conn.peer_info else "",
                )
            )
            p2p_manager.on_disconnected(lambda peer_id: self.node.unregister_peer(peer_id))

    async def start(self) -> None:
        """بدء مكدس الشبكة."""
        await self.node.start()
        self.is_initialized = True
        logger.info("Network stack started")

    async def stop(self) -> None:
        """إيقاف مكدس الشبكة."""
        await self.node.stop()
        self.is_initialized = False
        logger.info("Network stack stopped")

    # === DNS Operations ===

    def resolve_name(self, name: str) -> Optional[Dict]:
        """البحث عن اسم."""
        return self.node.resolve(name)

    def register_service(self, name: str, port: int) -> None:
        """تسجيل خدمة."""
        self.node.registry.register_peer(
            peer_id=self.node.identity.node_id,
            name=self.node.identity.name,
            ip_address=self.node.local_ips[0] if self.node.local_ips else "127.0.0.1",
            port=self.node.p2p_port,
            services={name: port},
        )

    # === Routing Operations ===

    def add_route(self, destination: str, gateway: str, metric: int = 100) -> None:
        """إضافة مسار."""
        self.node.router.add_route(destination, gateway, metric)

    def get_route(self, destination: str) -> Optional[Dict]:
        """البحث عن مسار."""
        route = self.node.router.get_route(destination)
        return route.to_dict() if route else None

    # === Status and Stats ===

    def get_status(self) -> Dict:
        """حالة الشبكة."""
        return {
            "running": self.is_initialized,
            "node_id": self.node.identity.node_id,
            "name": self.node.identity.name,
            "domain": self.node.domain,
            "public_ip": self.node.public_ip,
            "local_ips": self.node.local_ips,
        }

    def get_full_stats(self) -> Dict:
        """إحصائيات كاملة."""
        return self.node.get_network_stats()

    def get_peers(self) -> List[Dict]:
        """قائمة الأطراف."""
        return self.node.get_all_peers()

    def get_dns_records(self) -> List[Dict]:
        """سجلات DNS."""
        return self.node.get_dns_records()

    def get_routing_table(self) -> List[Dict]:
        """جدول التوجيه."""
        return self.node.get_routing_table()

    def get_relay_sessions(self) -> List[Dict]:
        """جلسات الترحيل."""
        return self.node.relay.get_sessions()
