"""
Mesh Node - العقدة الأساسية في شبكة Mesh

Each node in the mesh network can act as both a worker and a coordinator.
Nodes discover each other automatically and share workload.
"""

import asyncio
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

# Suppress pynvml deprecation warning
warnings.filterwarnings("ignore", category=FutureWarning, module="pynvml")

from ..models.job import Job, JobStatus
from ..models.resources import ResourceSpec, ResourceUsage
from .consensus import LeaderElection
from .discovery import DiscoveryMethod, PeerDiscovery
from .gossip import GossipMessage, GossipProtocol, MessageType
from .peer import Peer, PeerConnection
from .router import RoutingStrategy, TaskRouter


class NodeState(str, Enum):
    """حالة العقدة في الشبكة"""

    INITIALIZING = "initializing"  # بدء التشغيل
    DISCOVERING = "discovering"  # البحث عن العقد الأخرى
    ACTIVE = "active"  # نشط ويعمل
    BUSY = "busy"  # مشغول بمهام
    DRAINING = "draining"  # يستنزف المهام قبل الإيقاف
    OFFLINE = "offline"  # غير متصل


@dataclass
class NodeInfo:
    """معلومات العقدة"""

    node_id: str
    hostname: str
    ip_address: str
    port: int
    resources: ResourceSpec
    current_usage: ResourceUsage
    state: NodeState
    tags: Set[str] = field(default_factory=set)
    joined_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "port": self.port,
            "resources": self.resources.to_dict(),
            "current_usage": {
                "cpu_percent": self.current_usage.cpu_percent,
                "memory_percent": self.current_usage.memory_percent,
            },
            "state": self.state.value,
            "tags": list(self.tags),
            "joined_at": self.joined_at.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeInfo":
        resources = ResourceSpec.from_dict(data["resources"])
        usage_data = data["current_usage"]
        return cls(
            node_id=data["node_id"],
            hostname=data["hostname"],
            ip_address=data["ip_address"],
            port=data["port"],
            resources=resources,
            current_usage=ResourceUsage(
                cpu_percent=usage_data.get("cpu_percent", 0.0),
                memory_used_mb=usage_data.get("memory_used_mb", 0),
                memory_total_mb=usage_data.get("memory_total_mb", resources.memory_mb),
                memory_percent=usage_data.get("memory_percent", 0.0),
            ),
            state=NodeState(data["state"]),
            tags=set(data.get("tags", [])),
            joined_at=datetime.fromisoformat(data["joined_at"]),
            last_seen=datetime.fromisoformat(data["last_seen"]),
            version=data.get("version", "1.0.0"),
        )


class MeshNode:
    """
    عقدة في شبكة Mesh اللامركزية

    كل عقدة يمكنها:
    - اكتشاف العقد الأخرى تلقائياً
    - تنفيذ المهام
    - توجيه المهام للعقد الأخرى
    - المشاركة في انتخاب القائد
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9000,
        node_id: Optional[str] = None,
        resources: Optional[ResourceSpec] = None,
        tags: Optional[Set[str]] = None,
        discovery_methods: Optional[List[DiscoveryMethod]] = None,
        routing_strategy: RoutingStrategy = RoutingStrategy.LEAST_LOADED,
        bootstrap_peers: Optional[List[str]] = None,
    ):
        self.node_id = node_id or str(uuid.uuid4())[:8]
        self.host = host
        self.port = port
        self.state = NodeState.INITIALIZING

        # الموارد
        self.resources = resources or self._detect_resources()
        self.current_usage = ResourceUsage(
            cpu_percent=0.0,
            memory_used_mb=0,
            memory_total_mb=self.resources.memory_mb,
            memory_percent=0.0,
        )
        self.tags = tags or set()

        # العقد المتصلة
        self.peers: Dict[str, Peer] = {}
        self.connections: Dict[str, PeerConnection] = {}

        # المكونات
        self.discovery = PeerDiscovery(
            node=self,
            methods=discovery_methods or [DiscoveryMethod.MULTICAST, DiscoveryMethod.GOSSIP],
            bootstrap_peers=bootstrap_peers or [],
        )
        self.gossip = GossipProtocol(node=self)
        self.router = TaskRouter(node=self, strategy=routing_strategy)
        self.leader_election = LeaderElection(node=self)

        # المهام
        self.local_jobs: Dict[str, Job] = {}
        self.pending_jobs: asyncio.Queue = asyncio.Queue()

        # الأحداث
        self._event_handlers: Dict[str, List[Callable]] = {}

        # التحكم
        self._running = False
        self._tasks: List[asyncio.Task] = []

    def _detect_resources(self) -> ResourceSpec:
        """اكتشاف موارد الجهاز تلقائياً"""
        try:
            import psutil

            cpu_count = psutil.cpu_count()
            memory_mb = psutil.virtual_memory().total // (1024 * 1024)

            # محاولة اكتشاف GPU
            gpu_count = 0
            try:
                import warnings as _w
                _w.filterwarnings("ignore", category=FutureWarning, module="pynvml")
                import pynvml
                pynvml.nvmlInit()
                gpu_count = pynvml.nvmlDeviceGetCount()
                pynvml.nvmlShutdown()
            except Exception:
                pass

            return ResourceSpec(
                cpu_cores=float(cpu_count),
                memory_mb=memory_mb,
                gpu_count=gpu_count,
            )
        except Exception:
            return ResourceSpec(cpu_cores=1.0, memory_mb=1024, gpu_count=0)

    @property
    def info(self) -> NodeInfo:
        """الحصول على معلومات العقدة"""
        import socket

        return NodeInfo(
            node_id=self.node_id,
            hostname=socket.gethostname(),
            ip_address=self.host,
            port=self.port,
            resources=self.resources,
            current_usage=self.current_usage,
            state=self.state,
            tags=self.tags,
        )

    @property
    def is_leader(self) -> bool:
        """هل هذه العقدة هي القائد الحالي"""
        return self.leader_election.is_leader

    @property
    def leader_id(self) -> Optional[str]:
        """معرف القائد الحالي"""
        return self.leader_election.current_leader

    @property
    def peer_count(self) -> int:
        """عدد العقد المتصلة"""
        return len(self.peers)

    async def start(self) -> None:
        """بدء تشغيل العقدة"""
        self._running = True
        self.state = NodeState.DISCOVERING

        # بدء الخدمات
        self._tasks = [
            asyncio.create_task(self._run_server()),
            asyncio.create_task(self.discovery.start()),
            asyncio.create_task(self.gossip.start()),
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._job_processor()),
            asyncio.create_task(self._resource_monitor()),
        ]

        self._emit("started", {"node_id": self.node_id})

        # انتظار اكتشاف العقد
        await asyncio.sleep(2)
        self.state = NodeState.ACTIVE

        # بدء انتخاب القائد
        await self.leader_election.start()

    async def stop(self) -> None:
        """إيقاف العقدة"""
        self.state = NodeState.DRAINING
        self._running = False

        # إيقاف المكونات
        await self.discovery.stop()
        await self.gossip.stop()
        await self.leader_election.stop()

        # إغلاق الاتصالات
        for conn in self.connections.values():
            await conn.close()

        # إلغاء المهام
        for task in self._tasks:
            task.cancel()

        self.state = NodeState.OFFLINE
        self._emit("stopped", {"node_id": self.node_id})

    async def _run_server(self) -> None:
        """تشغيل خادم الاتصالات"""
        server = await asyncio.start_server(
            self._handle_connection,
            self.host,
            self.port,
        )

        async with server:
            await server.serve_forever()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """معالجة اتصال وارد"""
        try:
            while self._running:
                data = await reader.readline()
                if not data:
                    break

                message = GossipMessage.from_json(data.decode())
                await self._process_message(message, writer)
        except Exception as e:
            self._emit("error", {"error": str(e)})
        finally:
            writer.close()
            await writer.wait_closed()

    async def _process_message(
        self,
        message: GossipMessage,
        writer: asyncio.StreamWriter,
    ) -> None:
        """معالجة رسالة واردة"""
        if message.type == MessageType.PING:
            # رد على ping
            response = GossipMessage(
                type=MessageType.PONG,
                sender_id=self.node_id,
                data=self.info.to_dict(),
            )
            writer.write(response.to_json().encode() + b"\n")
            await writer.drain()

        elif message.type == MessageType.PEER_LIST:
            # تحديث قائمة العقد
            peers_data = message.data.get("peers", [])
            for peer_data in peers_data:
                await self._add_peer_from_info(peer_data)

        elif message.type == MessageType.JOB_SUBMIT:
            # استلام مهمة جديدة
            job_data = message.data.get("job")
            if job_data:
                job = Job.from_dict(job_data)
                await self.submit_job(job, local=True)

        elif message.type == MessageType.JOB_RESULT:
            # استلام نتيجة مهمة
            job_id = message.data.get("job_id")
            result = message.data.get("result")
            self._emit("job_result", {"job_id": job_id, "result": result})

        elif message.type == MessageType.LEADER_ELECTION:
            # معالجة انتخاب القائد
            await self.leader_election.handle_election_message(message)

    async def _heartbeat_loop(self) -> None:
        """حلقة إرسال heartbeat للعقد المتصلة"""
        while self._running:
            try:
                for peer_id, peer in list(self.peers.items()):
                    try:
                        await self._send_ping(peer)
                        peer.last_seen = datetime.now(timezone.utc)
                    except Exception:
                        # العقدة غير متاحة
                        await self._remove_peer(peer_id)

                await asyncio.sleep(5)  # كل 5 ثواني
            except asyncio.CancelledError:
                break

    async def _job_processor(self) -> None:
        """معالج المهام"""
        while self._running:
            try:
                job = await asyncio.wait_for(
                    self.pending_jobs.get(),
                    timeout=1.0,
                )
                await self._execute_job(job)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _resource_monitor(self) -> None:
        """مراقبة استخدام الموارد"""
        import psutil

        while self._running:
            try:
                mem = psutil.virtual_memory()
                self.current_usage = ResourceUsage(
                    cpu_percent=psutil.cpu_percent(),
                    memory_used_mb=mem.used // (1024 * 1024),
                    memory_total_mb=mem.total // (1024 * 1024),
                    memory_percent=mem.percent,
                )

                # تحديث الحالة بناءً على الاستخدام
                if self.current_usage.cpu_percent > 90:
                    self.state = NodeState.BUSY
                elif self.state == NodeState.BUSY:
                    self.state = NodeState.ACTIVE

                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break

    async def submit_job(self, job: Job, local: bool = False) -> str:
        """
        إرسال مهمة للتنفيذ

        Args:
            job: المهمة المراد تنفيذها
            local: هل يتم تنفيذها محلياً فقط

        Returns:
            معرف المهمة
        """
        if local or self._can_execute_locally(job):
            # تنفيذ محلي
            self.local_jobs[job.job_id] = job
            await self.pending_jobs.put(job)
        else:
            # توجيه لعقدة أخرى
            target_peer = await self.router.find_best_peer(job)
            if target_peer:
                await self._forward_job(job, target_peer)
            else:
                # لا يوجد عقدة متاحة، تنفيذ محلي
                self.local_jobs[job.job_id] = job
                await self.pending_jobs.put(job)

        self._emit("job_submitted", {"job_id": job.job_id})
        return job.job_id

    def _can_execute_locally(self, job: Job) -> bool:
        """هل يمكن تنفيذ المهمة محلياً"""
        available = self.resources - self._get_used_resources()
        return job.resources.fits_in(available)

    def _get_used_resources(self) -> ResourceSpec:
        """حساب الموارد المستخدمة"""
        used = ResourceSpec(cpu_cores=0, memory_mb=0, gpu_count=0)
        for job in self.local_jobs.values():
            if job.status == JobStatus.RUNNING:
                used = used + job.resources
        return used

    async def _execute_job(self, job: Job) -> None:
        """تنفيذ مهمة"""
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)

        self._emit("job_started", {"job_id": job.job_id})

        try:
            # تنفيذ الأمر
            process = await asyncio.create_subprocess_shell(
                job.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=job.timeout_seconds,
            )

            job.status = JobStatus.COMPLETED if process.returncode == 0 else JobStatus.FAILED
            job.result = {
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "exit_code": process.returncode,
            }

        except asyncio.TimeoutError:
            job.status = JobStatus.TIMEOUT
            job.result = {"error": "Job timed out"}
        except Exception as e:
            job.status = JobStatus.FAILED
            job.result = {"error": str(e)}

        job.completed_at = datetime.now(timezone.utc)
        self._emit("job_completed", {"job_id": job.job_id, "status": job.status.value})

        # إرسال النتيجة للعقدة المصدر إذا كانت مهمة موجهة
        if hasattr(job, "source_node") and job.source_node != self.node_id:
            await self._send_job_result(job)

    async def _forward_job(self, job: Job, peer: Peer) -> None:
        """توجيه مهمة لعقدة أخرى"""
        job.source_node = self.node_id

        message = GossipMessage(
            type=MessageType.JOB_SUBMIT,
            sender_id=self.node_id,
            data={"job": job.to_dict()},
        )

        await self._send_to_peer(peer, message)

    async def _send_job_result(self, job: Job) -> None:
        """إرسال نتيجة المهمة للعقدة المصدر"""
        source_peer = self.peers.get(job.source_node)
        if source_peer:
            message = GossipMessage(
                type=MessageType.JOB_RESULT,
                sender_id=self.node_id,
                data={
                    "job_id": job.job_id,
                    "result": job.result,
                    "status": job.status.value,
                },
            )
            await self._send_to_peer(source_peer, message)

    async def _send_ping(self, peer: Peer) -> None:
        """إرسال ping لعقدة"""
        message = GossipMessage(
            type=MessageType.PING,
            sender_id=self.node_id,
            data=self.info.to_dict(),
        )
        await self._send_to_peer(peer, message)

    async def _send_to_peer(self, peer: Peer, message: GossipMessage) -> None:
        """إرسال رسالة لعقدة"""
        try:
            reader, writer = await asyncio.open_connection(
                peer.ip_address,
                peer.port,
            )

            writer.write(message.to_json().encode() + b"\n")
            await writer.drain()

            writer.close()
            await writer.wait_closed()
        except Exception as e:
            self._emit("send_error", {"peer_id": peer.node_id, "error": str(e)})
            raise

    async def add_peer(self, address: str) -> Optional[Peer]:
        """
        إضافة عقدة يدوياً

        Args:
            address: عنوان العقدة (host:port)
        """
        try:
            host, port = address.rsplit(":", 1)
            port = int(port)

            # محاولة الاتصال
            reader, writer = await asyncio.open_connection(host, port)

            # إرسال ping
            message = GossipMessage(
                type=MessageType.PING,
                sender_id=self.node_id,
                data=self.info.to_dict(),
            )
            writer.write(message.to_json().encode() + b"\n")
            await writer.drain()

            # انتظار الرد
            response_data = await asyncio.wait_for(reader.readline(), timeout=5.0)
            response = GossipMessage.from_json(response_data.decode())

            writer.close()
            await writer.wait_closed()

            # إنشاء Peer
            peer_info = NodeInfo.from_dict(response.data)
            peer = Peer(
                node_id=peer_info.node_id,
                hostname=peer_info.hostname,
                ip_address=host,
                port=port,
                resources=peer_info.resources,
                state=peer_info.state,
            )

            self.peers[peer.node_id] = peer
            self._emit("peer_added", {"peer_id": peer.node_id})

            return peer

        except Exception as e:
            self._emit("error", {"error": f"Failed to add peer {address}: {e}"})
            return None

    async def _add_peer_from_info(self, info_dict: Dict) -> None:
        """إضافة عقدة من معلومات"""
        peer_info = NodeInfo.from_dict(info_dict)
        if peer_info.node_id != self.node_id and peer_info.node_id not in self.peers:
            peer = Peer(
                node_id=peer_info.node_id,
                hostname=peer_info.hostname,
                ip_address=peer_info.ip_address,
                port=peer_info.port,
                resources=peer_info.resources,
                state=peer_info.state,
            )
            self.peers[peer.node_id] = peer
            self._emit("peer_added", {"peer_id": peer.node_id})

    async def _remove_peer(self, peer_id: str) -> None:
        """إزالة عقدة"""
        if peer_id in self.peers:
            del self.peers[peer_id]
            self._emit("peer_removed", {"peer_id": peer_id})

    def on(self, event: str, handler: Callable) -> None:
        """تسجيل معالج حدث"""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def _emit(self, event: str, data: Dict) -> None:
        """إطلاق حدث"""
        if event in self._event_handlers:
            for handler in self._event_handlers[event]:
                try:
                    handler(data)
                except Exception:
                    pass

    def get_cluster_info(self) -> Dict:
        """الحصول على معلومات الكلاستر"""
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "is_leader": self.is_leader,
            "leader_id": self.leader_id,
            "peer_count": self.peer_count,
            "peers": [p.to_dict() for p in self.peers.values()],
            "local_jobs": len(self.local_jobs),
            "resources": self.resources.to_dict(),
            "usage": {
                "cpu_percent": self.current_usage.cpu_percent,
                "memory_percent": self.current_usage.memory_percent,
            },
        }
