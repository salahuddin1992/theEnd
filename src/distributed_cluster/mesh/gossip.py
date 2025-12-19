"""
Gossip Protocol - بروتوكول نشر المعلومات

بروتوكول لنشر المعلومات بين العقد بطريقة وبائية (epidemic).
كل عقدة تشارك معلوماتها مع عدد محدود من الجيران.
"""

import asyncio
import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from .node import MeshNode


class MessageType(str, Enum):
    """أنواع الرسائل"""
    PING = "ping"
    PONG = "pong"
    PEER_LIST = "peer_list"
    JOB_SUBMIT = "job_submit"
    JOB_RESULT = "job_result"
    JOB_STATUS = "job_status"
    LEADER_ELECTION = "leader_election"
    LEADER_ANNOUNCE = "leader_announce"
    STATE_SYNC = "state_sync"
    CUSTOM = "custom"


@dataclass
class GossipMessage:
    """رسالة Gossip"""
    type: MessageType
    sender_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    message_id: str = ""
    timestamp: str = ""
    ttl: int = 5  # Time-to-live (عدد القفزات المتبقية)

    def __post_init__(self):
        if not self.message_id:
            import uuid
            self.message_id = str(uuid.uuid4())[:12]
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "sender_id": self.sender_id,
            "data": self.data,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
        })

    @classmethod
    def from_json(cls, data: str) -> "GossipMessage":
        obj = json.loads(data.strip())
        return cls(
            type=MessageType(obj["type"]),
            sender_id=obj["sender_id"],
            data=obj.get("data", {}),
            message_id=obj.get("message_id", ""),
            timestamp=obj.get("timestamp", ""),
            ttl=obj.get("ttl", 5),
        )


class GossipProtocol:
    """
    بروتوكول Gossip لنشر المعلومات

    الخصائص:
    - انتشار سريع: O(log N) جولات للوصول لكل العقد
    - تحمل الأخطاء: يعمل حتى مع فقدان بعض الرسائل
    - لا مركزي: لا يحتاج منسق مركزي
    """

    def __init__(
        self,
        node: "MeshNode",
        fanout: int = 3,          # عدد العقد للإرسال في كل جولة
        interval: float = 1.0,    # الفترة بين الجولات (ثواني)
    ):
        self.node = node
        self.fanout = fanout
        self.interval = interval
        self._running = False
        self._seen_messages: Set[str] = set()  # الرسائل المعالجة
        self._message_buffer: List[GossipMessage] = []  # رسائل للنشر
        self._max_seen = 10000  # حد الرسائل المحفوظة
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """بدء البروتوكول"""
        self._running = True
        self._task = asyncio.create_task(self._gossip_loop())

    async def stop(self) -> None:
        """إيقاف البروتوكول"""
        self._running = False
        if self._task:
            self._task.cancel()

    async def broadcast(self, message: GossipMessage) -> None:
        """
        بث رسالة لجميع العقد

        الرسالة ستنتشر تدريجياً عبر الشبكة
        """
        if message.message_id not in self._seen_messages:
            self._seen_messages.add(message.message_id)
            self._message_buffer.append(message)

    async def _gossip_loop(self) -> None:
        """حلقة Gossip الرئيسية"""
        while self._running:
            try:
                await self._do_gossip_round()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(self.interval)

    async def _do_gossip_round(self) -> None:
        """تنفيذ جولة gossip واحدة"""
        if not self.node.peers or not self._message_buffer:
            return

        # اختيار عقد عشوائية
        peers = list(self.node.peers.values())
        selected = random.sample(peers, min(self.fanout, len(peers)))

        # إرسال الرسائل المعلقة
        messages_to_send = self._message_buffer[:10]  # حد 10 رسائل في الجولة
        self._message_buffer = self._message_buffer[10:]

        for peer in selected:
            for message in messages_to_send:
                if message.ttl > 0:
                    # تقليل TTL قبل الإرسال
                    forward_msg = GossipMessage(
                        type=message.type,
                        sender_id=message.sender_id,
                        data=message.data,
                        message_id=message.message_id,
                        timestamp=message.timestamp,
                        ttl=message.ttl - 1,
                    )
                    try:
                        await self.node._send_to_peer(peer, forward_msg)
                    except Exception:
                        pass

        # تنظيف الرسائل القديمة
        if len(self._seen_messages) > self._max_seen:
            # إزالة نصف الرسائل القديمة
            self._seen_messages = set(list(self._seen_messages)[self._max_seen // 2:])

    async def receive(self, message: GossipMessage) -> bool:
        """
        استقبال رسالة

        Returns:
            True إذا كانت رسالة جديدة، False إذا كانت مكررة
        """
        if message.message_id in self._seen_messages:
            return False

        self._seen_messages.add(message.message_id)

        # إضافة للنشر إذا كان TTL > 0
        if message.ttl > 0:
            self._message_buffer.append(message)

        return True

    def stats(self) -> Dict[str, Any]:
        """إحصائيات البروتوكول"""
        return {
            "fanout": self.fanout,
            "interval": self.interval,
            "seen_messages": len(self._seen_messages),
            "pending_messages": len(self._message_buffer),
            "running": self._running,
        }


class AntiEntropy:
    """
    Anti-Entropy لضمان تناسق البيانات

    يقارن حالة العقدة مع عقد أخرى ويحل الاختلافات
    """

    def __init__(self, node: "MeshNode", interval: float = 60.0):
        self.node = node
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """بدء Anti-Entropy"""
        self._running = True
        self._task = asyncio.create_task(self._sync_loop())

    async def stop(self) -> None:
        """إيقاف Anti-Entropy"""
        self._running = False
        if self._task:
            self._task.cancel()

    async def _sync_loop(self) -> None:
        """حلقة المزامنة"""
        while self._running:
            try:
                await self._sync_with_random_peer()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(self.interval)

    async def _sync_with_random_peer(self) -> None:
        """مزامنة مع عقدة عشوائية"""
        if not self.node.peers:
            return

        peer = random.choice(list(self.node.peers.values()))

        # إرسال طلب مزامنة
        message = GossipMessage(
            type=MessageType.STATE_SYNC,
            sender_id=self.node.node_id,
            data={
                "peers": [p.node_id for p in self.node.peers.values()],
                "jobs": list(self.node.local_jobs.keys()),
            },
        )

        try:
            await self.node._send_to_peer(peer, message)
        except Exception:
            pass
