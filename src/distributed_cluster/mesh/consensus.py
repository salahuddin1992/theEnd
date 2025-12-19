"""
Consensus & Leader Election - التوافق وانتخاب القائد

تطبيق خوارزمية Bully لانتخاب القائد في الشبكة اللامركزية.
القائد مسؤول عن:
- تنسيق المهام المعقدة
- حل النزاعات
- الحفاظ على حالة الكلاستر
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional, Set

if TYPE_CHECKING:
    from .gossip import GossipMessage
    from .node import MeshNode


class ConsensusState(str, Enum):
    """حالة التوافق"""

    FOLLOWER = "follower"  # تابع
    CANDIDATE = "candidate"  # مرشح
    LEADER = "leader"  # قائد
    ELECTION = "election"  # في انتخابات


class ElectionMessageType(str, Enum):
    """أنواع رسائل الانتخاب"""

    ELECTION = "election"  # بدء انتخاب
    ANSWER = "answer"  # رد على انتخاب
    VICTORY = "victory"  # إعلان الفوز
    HEARTBEAT = "heartbeat"  # نبض القائد


@dataclass
class ElectionState:
    """حالة الانتخاب"""

    state: ConsensusState
    current_leader: Optional[str]
    term: int  # رقم الدورة
    voted_for: Optional[str]
    last_heartbeat: datetime
    election_timeout: float  # ثواني


class LeaderElection:
    """
    نظام انتخاب القائد باستخدام خوارزمية Bully

    الخوارزمية:
    1. إذا لم يستلم العقدة heartbeat من القائد، تبدأ انتخاب
    2. ترسل رسالة ELECTION لكل العقد ذات ID أعلى
    3. إذا لم تستلم ANSWER، تعلن نفسها قائداً
    4. إذا استلمت ANSWER، تنتظر VICTORY
    """

    def __init__(
        self,
        node: "MeshNode",
        election_timeout: float = 10.0,
        heartbeat_interval: float = 3.0,
    ):
        self.node = node
        self.election_timeout = election_timeout
        self.heartbeat_interval = heartbeat_interval

        self.state = ElectionState(
            state=ConsensusState.FOLLOWER,
            current_leader=None,
            term=0,
            voted_for=None,
            last_heartbeat=datetime.utcnow(),
            election_timeout=election_timeout,
        )

        self._running = False
        self._tasks: list = []
        self._election_in_progress = False
        self._received_answers: Set[str] = set()

    @property
    def is_leader(self) -> bool:
        """هل هذه العقدة هي القائد"""
        return self.state.state == ConsensusState.LEADER

    @property
    def current_leader(self) -> Optional[str]:
        """معرف القائد الحالي"""
        return self.state.current_leader

    async def start(self) -> None:
        """بدء نظام الانتخاب"""
        self._running = True
        self._tasks = [
            asyncio.create_task(self._election_monitor()),
            asyncio.create_task(self._leader_heartbeat()),
        ]

    async def stop(self) -> None:
        """إيقاف النظام"""
        self._running = False
        for task in self._tasks:
            task.cancel()

    async def _election_monitor(self) -> None:
        """مراقبة الحاجة للانتخاب"""
        while self._running:
            try:
                if self.state.state != ConsensusState.LEADER:
                    # التحقق من timeout
                    elapsed = (datetime.utcnow() - self.state.last_heartbeat).total_seconds()
                    if elapsed > self.election_timeout:
                        await self._start_election()

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)

    async def _leader_heartbeat(self) -> None:
        """إرسال heartbeat إذا كنا القائد"""
        while self._running:
            try:
                if self.state.state == ConsensusState.LEADER:
                    await self._send_heartbeat()

                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(self.heartbeat_interval)

    async def _start_election(self) -> None:
        """بدء انتخاب جديد"""
        if self._election_in_progress:
            return

        self._election_in_progress = True
        self.state.state = ConsensusState.CANDIDATE
        self.state.term += 1
        self._received_answers.clear()

        # إرسال ELECTION للعقد ذات ID أعلى
        higher_peers = [p for p in self.node.peers.values() if p.node_id > self.node.node_id]

        if not higher_peers:
            # نحن أعلى ID، نعلن الفوز مباشرة
            await self._become_leader()
        else:
            # إرسال رسائل الانتخاب
            from .gossip import GossipMessage, MessageType

            for peer in higher_peers:
                message = GossipMessage(
                    type=MessageType.LEADER_ELECTION,
                    sender_id=self.node.node_id,
                    data={
                        "election_type": ElectionMessageType.ELECTION.value,
                        "term": self.state.term,
                    },
                )
                try:
                    await self.node._send_to_peer(peer, message)
                except Exception:
                    pass

            # انتظار الردود
            await asyncio.sleep(5)  # timeout للردود

            if not self._received_answers:
                # لم نستلم ردود، نعلن الفوز
                await self._become_leader()

        self._election_in_progress = False

    async def _become_leader(self) -> None:
        """الإعلان كقائد"""
        self.state.state = ConsensusState.LEADER
        self.state.current_leader = self.node.node_id

        # إعلان الفوز لجميع العقد
        from .gossip import GossipMessage, MessageType

        for peer in self.node.peers.values():
            message = GossipMessage(
                type=MessageType.LEADER_ELECTION,
                sender_id=self.node.node_id,
                data={
                    "election_type": ElectionMessageType.VICTORY.value,
                    "term": self.state.term,
                    "leader_id": self.node.node_id,
                },
            )
            try:
                await self.node._send_to_peer(peer, message)
            except Exception:
                pass

        self.node._emit("became_leader", {"term": self.state.term})

    async def _send_heartbeat(self) -> None:
        """إرسال heartbeat كقائد"""
        from .gossip import GossipMessage, MessageType

        for peer in self.node.peers.values():
            message = GossipMessage(
                type=MessageType.LEADER_ELECTION,
                sender_id=self.node.node_id,
                data={
                    "election_type": ElectionMessageType.HEARTBEAT.value,
                    "term": self.state.term,
                    "leader_id": self.node.node_id,
                },
            )
            try:
                await self.node._send_to_peer(peer, message)
            except Exception:
                pass

    async def handle_election_message(self, message: "GossipMessage") -> None:
        """معالجة رسالة انتخاب"""
        election_type = ElectionMessageType(message.data.get("election_type"))
        term = message.data.get("term", 0)

        if election_type == ElectionMessageType.ELECTION:
            # استلمنا طلب انتخاب من عقدة ذات ID أقل
            if message.sender_id < self.node.node_id:
                # نرد بـ ANSWER ونبدأ انتخابنا
                await self._send_answer(message.sender_id)
                await self._start_election()

        elif election_type == ElectionMessageType.ANSWER:
            # استلمنا رد من عقدة ذات ID أعلى
            self._received_answers.add(message.sender_id)
            # ننتظر VICTORY منها

        elif election_type == ElectionMessageType.VICTORY:
            # عقدة أعلنت نفسها قائداً
            if term >= self.state.term:
                self.state.state = ConsensusState.FOLLOWER
                self.state.current_leader = message.data.get("leader_id")
                self.state.term = term
                self.state.last_heartbeat = datetime.utcnow()
                self._election_in_progress = False
                self.node._emit("new_leader", {"leader_id": self.state.current_leader})

        elif election_type == ElectionMessageType.HEARTBEAT:
            # heartbeat من القائد
            leader_id = message.data.get("leader_id")
            if term >= self.state.term:
                self.state.current_leader = leader_id
                self.state.term = term
                self.state.last_heartbeat = datetime.utcnow()
                if self.state.state != ConsensusState.LEADER:
                    self.state.state = ConsensusState.FOLLOWER

    async def _send_answer(self, target_id: str) -> None:
        """إرسال ANSWER"""
        from .gossip import GossipMessage, MessageType

        target_peer = self.node.peers.get(target_id)
        if target_peer:
            message = GossipMessage(
                type=MessageType.LEADER_ELECTION,
                sender_id=self.node.node_id,
                data={
                    "election_type": ElectionMessageType.ANSWER.value,
                    "term": self.state.term,
                },
            )
            try:
                await self.node._send_to_peer(target_peer, message)
            except Exception:
                pass

    def step_down(self) -> None:
        """التنازل عن القيادة"""
        if self.state.state == ConsensusState.LEADER:
            self.state.state = ConsensusState.FOLLOWER
            self.state.current_leader = None
            self.node._emit("stepped_down", {})

    def stats(self) -> Dict[str, Any]:
        """إحصائيات الانتخاب"""
        return {
            "state": self.state.state.value,
            "term": self.state.term,
            "current_leader": self.state.current_leader,
            "is_leader": self.is_leader,
            "last_heartbeat": self.state.last_heartbeat.isoformat(),
            "election_in_progress": self._election_in_progress,
        }
