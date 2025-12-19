"""
Leader Election - انتخاب القائد
================================

تطبيق خوارزمية Bully لانتخاب القائد بين Masters.
القائد (Leader) هو الوحيد الذي:
- يقبل jobs جديدة
- يجدول المهام
- يدير الـ workers

الباقون (Followers) يبقون جاهزين للتبديل.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import socket
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger(__name__)


class HARole(str, Enum):
    """دور الـ Master في الكلاستر"""

    LEADER = "leader"  # القائد - يعمل بشكل كامل
    FOLLOWER = "follower"  # تابع - جاهز للتبديل
    CANDIDATE = "candidate"  # مرشح - في انتخابات
    UNKNOWN = "unknown"  # غير معروف - قبل الانتخاب


@dataclass
class LeaderInfo:
    """معلومات القائد الحالي"""

    master_id: str
    address: str
    port: int
    elected_at: datetime
    term: int  # رقم الدورة الانتخابية

    def to_dict(self) -> dict:
        return {
            "master_id": self.master_id,
            "address": self.address,
            "port": self.port,
            "elected_at": self.elected_at.isoformat(),
            "term": self.term,
        }


@dataclass
class MasterPeer:
    """معلومات Master آخر"""

    master_id: str
    address: str
    port: int
    role: HARole = HARole.UNKNOWN
    last_seen: datetime = field(default_factory=datetime.utcnow)
    priority: int = 0  # أعلى = أولوية أكبر للقيادة

    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.port}"

    def is_alive(self, timeout_seconds: float = 30.0) -> bool:
        """هل الـ Master متصل"""
        return (datetime.utcnow() - self.last_seen).total_seconds() < timeout_seconds


@dataclass
class ElectionConfig:
    """إعدادات انتخاب القائد"""

    # معرف هذا الـ Master (فريد)
    master_id: str = ""

    # عنوان ومنفذ هذا الـ Master
    address: str = "0.0.0.0"
    port: int = 8080

    # أولوية هذا الـ Master (أعلى = أولوية أكبر)
    priority: int = 0

    # قائمة Masters الأخرى
    peers: list[str] = field(default_factory=list)  # ["host1:8080", "host2:8080"]

    # Timeouts
    election_timeout_seconds: float = 10.0
    heartbeat_interval_seconds: float = 3.0
    peer_timeout_seconds: float = 15.0

    # HTTP timeout
    http_timeout_seconds: float = 5.0

    def __post_init__(self):
        if not self.master_id:
            # توليد ID فريد من hostname + port
            hostname = socket.gethostname()
            raw = f"{hostname}:{self.port}:{datetime.utcnow().timestamp()}"
            self.master_id = hashlib.sha256(raw.encode()).hexdigest()[:12]


class LeaderElection:
    """
    نظام انتخاب القائد بين Masters

    الخوارزمية (Bully Algorithm):
    1. إذا لم يستلم heartbeat من القائد → يبدأ انتخاب
    2. يرسل ELECTION لكل Masters ذات أولوية أعلى
    3. إذا لم يستلم رد → يعلن نفسه قائداً
    4. إذا استلم رد → ينتظر إعلان القائد الجديد
    """

    def __init__(
        self,
        config: ElectionConfig,
        on_became_leader: Optional[Callable[[], Any]] = None,
        on_lost_leadership: Optional[Callable[[], Any]] = None,
        on_leader_changed: Optional[Callable[[LeaderInfo], Any]] = None,
    ):
        self.config = config
        self._on_became_leader = on_became_leader
        self._on_lost_leadership = on_lost_leadership
        self._on_leader_changed = on_leader_changed

        # الحالة
        self._role = HARole.UNKNOWN
        self._term = 0
        self._current_leader: Optional[LeaderInfo] = None
        self._last_heartbeat = datetime.utcnow()
        self._peers: dict[str, MasterPeer] = {}

        # التحكم
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._election_lock = asyncio.Lock()
        self._election_in_progress = False

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def role(self) -> HARole:
        """الدور الحالي"""
        return self._role

    @property
    def is_leader(self) -> bool:
        """هل هذا الـ Master هو القائد"""
        return self._role == HARole.LEADER

    @property
    def current_leader(self) -> Optional[LeaderInfo]:
        """معلومات القائد الحالي"""
        return self._current_leader

    @property
    def term(self) -> int:
        """رقم الدورة الانتخابية الحالية"""
        return self._term

    @property
    def peers(self) -> dict[str, MasterPeer]:
        """قائمة Masters الأخرى"""
        return self._peers.copy()

    async def start(self) -> None:
        """بدء نظام الانتخاب"""
        logger.info(f"Starting Leader Election for master {self.config.master_id}")

        self._client = httpx.AsyncClient(
            timeout=self.config.http_timeout_seconds,
        )

        # تهيئة قائمة الـ peers
        await self._initialize_peers()

        self._running = True
        self._role = HARole.FOLLOWER

        # بدء المهام الخلفية
        self._tasks = [
            asyncio.create_task(self._election_monitor()),
            asyncio.create_task(self._heartbeat_sender()),
            asyncio.create_task(self._peer_discovery()),
        ]

        # بدء انتخاب أولي
        await self._start_election()

        logger.info(f"Leader Election started, role: {self._role.value}")

    async def stop(self) -> None:
        """إيقاف نظام الانتخاب"""
        logger.info("Stopping Leader Election...")

        self._running = False

        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._client:
            await self._client.aclose()

        logger.info("Leader Election stopped")

    async def _initialize_peers(self) -> None:
        """تهيئة قائمة Masters الأخرى"""
        for peer_addr in self.config.peers:
            try:
                if ":" in peer_addr:
                    host, port = peer_addr.rsplit(":", 1)
                    port = int(port)
                else:
                    host = peer_addr
                    port = 8080

                # لا نضيف أنفسنا
                if host in ("localhost", "127.0.0.1", self.config.address) and port == self.config.port:
                    continue

                peer_id = f"{host}:{port}"
                self._peers[peer_id] = MasterPeer(
                    master_id=peer_id,
                    address=host,
                    port=port,
                )
            except Exception as e:
                logger.warning(f"Invalid peer address {peer_addr}: {e}")

    async def _election_monitor(self) -> None:
        """مراقبة صحة القائد وبدء انتخاب إذا لزم"""
        while self._running:
            try:
                await asyncio.sleep(1.0)

                if self._role == HARole.LEADER:
                    continue

                # فحص آخر heartbeat من القائد
                elapsed = (datetime.utcnow() - self._last_heartbeat).total_seconds()
                if elapsed > self.config.election_timeout_seconds:
                    logger.warning(f"Leader timeout ({elapsed:.1f}s), starting election")
                    await self._start_election()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Election monitor error: {e}")

    async def _heartbeat_sender(self) -> None:
        """إرسال heartbeat للـ peers إذا كنا القائد"""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval_seconds)

                if self._role == HARole.LEADER:
                    await self._send_leader_heartbeat()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat sender error: {e}")

    async def _peer_discovery(self) -> None:
        """اكتشاف وتحديث حالة الـ peers"""
        while self._running:
            try:
                await asyncio.sleep(5.0)

                for peer_id, peer in list(self._peers.items()):
                    try:
                        resp = await self._client.get(
                            f"{peer.url}/ha/status",
                            timeout=3.0,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            peer.last_seen = datetime.utcnow()
                            peer.role = HARole(data.get("role", "unknown"))
                            peer.priority = data.get("priority", 0)
                            peer.master_id = data.get("master_id", peer_id)
                    except Exception:
                        pass  # Peer غير متاح

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Peer discovery error: {e}")

    async def _start_election(self) -> None:
        """بدء انتخاب جديد"""
        async with self._election_lock:
            if self._election_in_progress:
                return

            self._election_in_progress = True
            self._role = HARole.CANDIDATE
            self._term += 1

            logger.info(f"Starting election for term {self._term}")

        try:
            # إرسال ELECTION لكل peer بأولوية أعلى
            higher_priority_responded = False

            for peer_id, peer in self._peers.items():
                if peer.priority > self.config.priority or (
                    peer.priority == self.config.priority and peer.master_id > self.config.master_id
                ):
                    try:
                        resp = await self._client.post(
                            f"{peer.url}/ha/election",
                            json={
                                "master_id": self.config.master_id,
                                "term": self._term,
                                "priority": self.config.priority,
                            },
                            timeout=self.config.election_timeout_seconds / 2,
                        )
                        if resp.status_code == 200:
                            higher_priority_responded = True
                            logger.info(f"Higher priority master {peer_id} responded")
                    except Exception:
                        pass  # Peer غير متاح

            if not higher_priority_responded:
                # لم يرد أحد بأولوية أعلى → نصبح القائد
                await self._become_leader()
            else:
                # ننتظر إعلان القائد الجديد
                self._role = HARole.FOLLOWER
                logger.info("Waiting for higher priority master to become leader")

        finally:
            self._election_in_progress = False

    async def _become_leader(self) -> None:
        """أصبح القائد"""
        logger.info(f"Becoming leader for term {self._term}")

        old_role = self._role
        self._role = HARole.LEADER

        self._current_leader = LeaderInfo(
            master_id=self.config.master_id,
            address=self.config.address,
            port=self.config.port,
            elected_at=datetime.utcnow(),
            term=self._term,
        )

        # إعلان القيادة للـ peers
        await self._announce_leadership()

        # استدعاء callback
        if old_role != HARole.LEADER and self._on_became_leader:
            try:
                result = self._on_became_leader()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"on_became_leader callback error: {e}")

    async def _announce_leadership(self) -> None:
        """إعلان القيادة للـ peers"""
        for peer_id, peer in self._peers.items():
            try:
                await self._client.post(
                    f"{peer.url}/ha/leader",
                    json=self._current_leader.to_dict(),
                    timeout=3.0,
                )
            except Exception:
                pass  # لا بأس إذا فشل

    async def _send_leader_heartbeat(self) -> None:
        """إرسال heartbeat كقائد"""
        for peer_id, peer in self._peers.items():
            try:
                await self._client.post(
                    f"{peer.url}/ha/heartbeat",
                    json={
                        "master_id": self.config.master_id,
                        "term": self._term,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    timeout=2.0,
                )
            except Exception:
                pass

    # ==================== API Handlers ====================

    async def handle_election(self, master_id: str, term: int, priority: int) -> dict:
        """معالجة طلب انتخاب من peer"""
        logger.info(f"Received election request from {master_id} (term={term})")

        # إذا كنا بأولوية أعلى أو نفس الأولوية مع ID أكبر
        if self.config.priority > priority or (self.config.priority == priority and self.config.master_id > master_id):
            # نبدأ انتخابنا الخاص
            asyncio.create_task(self._start_election())
            return {"status": "ok", "message": "Starting own election"}

        return {"status": "ok", "message": "Acknowledged"}

    async def handle_leader_announcement(self, leader_info: dict) -> dict:
        """معالجة إعلان قائد جديد"""
        new_leader = LeaderInfo(
            master_id=leader_info["master_id"],
            address=leader_info["address"],
            port=leader_info["port"],
            elected_at=datetime.fromisoformat(leader_info["elected_at"]),
            term=leader_info["term"],
        )

        logger.info(f"New leader announced: {new_leader.master_id} (term={new_leader.term})")

        old_leader = self._current_leader
        old_role = self._role

        self._current_leader = new_leader
        self._term = new_leader.term
        self._last_heartbeat = datetime.utcnow()

        if new_leader.master_id != self.config.master_id:
            self._role = HARole.FOLLOWER

            if old_role == HARole.LEADER and self._on_lost_leadership:
                try:
                    result = self._on_lost_leadership()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"on_lost_leadership callback error: {e}")

        # استدعاء callback
        if self._on_leader_changed and (not old_leader or old_leader.master_id != new_leader.master_id):
            try:
                result = self._on_leader_changed(new_leader)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"on_leader_changed callback error: {e}")

        return {"status": "ok"}

    async def handle_heartbeat(self, master_id: str, term: int) -> dict:
        """معالجة heartbeat من القائد"""
        if self._current_leader and self._current_leader.master_id == master_id:
            self._last_heartbeat = datetime.utcnow()
            if term > self._term:
                self._term = term

        return {"status": "ok"}

    def get_status(self) -> dict:
        """الحصول على حالة الانتخاب"""
        return {
            "master_id": self.config.master_id,
            "role": self._role.value,
            "term": self._term,
            "priority": self.config.priority,
            "is_leader": self.is_leader,
            "current_leader": self._current_leader.to_dict() if self._current_leader else None,
            "peers_count": len(self._peers),
            "peers": {
                pid: {
                    "role": p.role.value,
                    "alive": p.is_alive(self.config.peer_timeout_seconds),
                    "last_seen": p.last_seen.isoformat(),
                }
                for pid, p in self._peers.items()
            },
        }
