"""
Peer Discovery - اكتشاف العقد في الشبكة

يدعم عدة طرق للاكتشاف:
- Multicast/mDNS: للشبكات المحلية
- Bootstrap: قائمة عقد معروفة
- Gossip: تبادل قوائم العقد
"""

import asyncio
import json
import socket
import struct
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from .node import MeshNode


class DiscoveryMethod(str, Enum):
    """طرق اكتشاف العقد"""
    MULTICAST = "multicast"  # UDP multicast للشبكة المحلية
    BOOTSTRAP = "bootstrap"  # قائمة عقد معروفة
    GOSSIP = "gossip"        # تبادل مع العقد المتصلة


# إعدادات Multicast
MULTICAST_GROUP = "239.255.255.250"
MULTICAST_PORT = 9999
DISCOVERY_INTERVAL = 10  # ثواني


@dataclass
class DiscoveryMessage:
    """رسالة اكتشاف"""
    node_id: str
    hostname: str
    ip_address: str
    port: int
    version: str = "1.0"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_json(self) -> str:
        return json.dumps({
            "type": "discovery",
            "node_id": self.node_id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "port": self.port,
            "version": self.version,
            "timestamp": self.timestamp,
        })

    @classmethod
    def from_json(cls, data: str) -> Optional["DiscoveryMessage"]:
        try:
            obj = json.loads(data)
            if obj.get("type") != "discovery":
                return None
            return cls(
                node_id=obj["node_id"],
                hostname=obj["hostname"],
                ip_address=obj["ip_address"],
                port=obj["port"],
                version=obj.get("version", "1.0"),
                timestamp=obj.get("timestamp", ""),
            )
        except Exception:
            return None


class PeerDiscovery:
    """
    نظام اكتشاف العقد

    يجمع بين عدة طرق لاكتشاف العقد في الشبكة
    """

    def __init__(
        self,
        node: "MeshNode",
        methods: List[DiscoveryMethod],
        bootstrap_peers: List[str] = None,
    ):
        self.node = node
        self.methods = methods
        self.bootstrap_peers = bootstrap_peers or []
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._discovered: Set[str] = set()  # node_ids المكتشفة

    async def start(self) -> None:
        """بدء الاكتشاف"""
        self._running = True

        if DiscoveryMethod.MULTICAST in self.methods:
            self._tasks.append(
                asyncio.create_task(self._multicast_listener())
            )
            self._tasks.append(
                asyncio.create_task(self._multicast_announcer())
            )

        if DiscoveryMethod.BOOTSTRAP in self.methods:
            self._tasks.append(
                asyncio.create_task(self._bootstrap_connector())
            )

        if DiscoveryMethod.GOSSIP in self.methods:
            self._tasks.append(
                asyncio.create_task(self._gossip_exchanger())
            )

    async def stop(self) -> None:
        """إيقاف الاكتشاف"""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    async def _multicast_listener(self) -> None:
        """الاستماع لرسائل multicast"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind(("", MULTICAST_PORT))

            # الانضمام لمجموعة multicast
            mreq = struct.pack(
                "4sl",
                socket.inet_aton(MULTICAST_GROUP),
                socket.INADDR_ANY,
            )
            sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_ADD_MEMBERSHIP,
                mreq,
            )

            sock.setblocking(False)

            while self._running:
                try:
                    # استخدام asyncio للقراءة
                    loop = asyncio.get_event_loop()
                    data, addr = await loop.sock_recvfrom(sock, 1024)

                    message = DiscoveryMessage.from_json(data.decode())
                    if message and message.node_id != self.node.node_id:
                        await self._handle_discovery(message, addr[0])

                except Exception:
                    await asyncio.sleep(0.1)

        except Exception:
            # Multicast قد لا يعمل في بعض البيئات
            pass
        finally:
            sock.close()

    async def _multicast_announcer(self) -> None:
        """إعلان الوجود عبر multicast"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

        try:
            while self._running:
                message = DiscoveryMessage(
                    node_id=self.node.node_id,
                    hostname=socket.gethostname(),
                    ip_address=self._get_local_ip(),
                    port=self.node.port,
                )

                try:
                    sock.sendto(
                        message.to_json().encode(),
                        (MULTICAST_GROUP, MULTICAST_PORT),
                    )
                except Exception:
                    pass

                await asyncio.sleep(DISCOVERY_INTERVAL)
        finally:
            sock.close()

    async def _bootstrap_connector(self) -> None:
        """الاتصال بالعقد المعروفة"""
        for peer_address in self.bootstrap_peers:
            if not self._running:
                break

            try:
                await self.node.add_peer(peer_address)
            except Exception:
                pass

            await asyncio.sleep(1)

    async def _gossip_exchanger(self) -> None:
        """تبادل قوائم العقد مع المتصلين"""
        while self._running:
            try:
                # كل 30 ثانية، أرسل قائمة العقد للمتصلين
                if self.node.peers:
                    from .gossip import GossipMessage, MessageType

                    peers_list = [
                        p.to_dict() for p in self.node.peers.values()
                    ]

                    message = GossipMessage(
                        type=MessageType.PEER_LIST,
                        sender_id=self.node.node_id,
                        data={"peers": peers_list},
                    )

                    # إرسال لجميع المتصلين
                    for peer in list(self.node.peers.values()):
                        try:
                            await self.node._send_to_peer(peer, message)
                        except Exception:
                            pass

                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5)

    async def _handle_discovery(self, message: DiscoveryMessage, source_ip: str) -> None:
        """معالجة رسالة اكتشاف"""
        if message.node_id in self._discovered:
            return

        self._discovered.add(message.node_id)

        # محاولة الاتصال
        address = f"{source_ip}:{message.port}"
        await self.node.add_peer(address)

    def _get_local_ip(self) -> str:
        """الحصول على IP المحلي"""
        try:
            # إنشاء socket للحصول على IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def stats(self) -> Dict[str, Any]:
        """إحصائيات الاكتشاف"""
        return {
            "methods": [m.value for m in self.methods],
            "bootstrap_peers": self.bootstrap_peers,
            "discovered_count": len(self._discovered),
            "running": self._running,
        }
