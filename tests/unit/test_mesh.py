"""
Tests for Mesh Network module
اختبارات وحدة Mesh Network
"""

from datetime import datetime

from distributed_cluster.mesh.consensus import ConsensusState, LeaderElection
from distributed_cluster.mesh.discovery import DiscoveryMessage, DiscoveryMethod
from distributed_cluster.mesh.gossip import GossipMessage, MessageType
from distributed_cluster.mesh.node import MeshNode, NodeInfo, NodeState
from distributed_cluster.mesh.peer import Peer
from distributed_cluster.mesh.router import RoutingStrategy, TaskRouter
from distributed_cluster.models.job import Job
from distributed_cluster.models.resources import ResourceSpec


class TestMeshNode:
    """اختبارات MeshNode"""

    def test_node_creation(self):
        """اختبار إنشاء عقدة"""
        node = MeshNode(port=9000)
        assert node.port == 9000
        assert node.state == NodeState.INITIALIZING
        assert node.node_id is not None
        assert len(node.peers) == 0

    def test_node_with_custom_id(self):
        """اختبار إنشاء عقدة بمعرف مخصص"""
        node = MeshNode(port=9000, node_id="test-node-1")
        assert node.node_id == "test-node-1"

    def test_node_with_tags(self):
        """اختبار إنشاء عقدة بعلامات"""
        node = MeshNode(port=9000, tags={"gpu", "high-memory"})
        assert "gpu" in node.tags
        assert "high-memory" in node.tags

    def test_node_info(self):
        """اختبار معلومات العقدة"""
        node = MeshNode(port=9000, node_id="test-1")
        info = node.info
        assert isinstance(info, NodeInfo)
        assert info.node_id == "test-1"
        assert info.port == 9000

    def test_node_info_to_dict(self):
        """اختبار تحويل معلومات العقدة لـ dict"""
        node = MeshNode(port=9000, node_id="test-1")
        info_dict = node.info.to_dict()
        assert info_dict["node_id"] == "test-1"
        assert info_dict["port"] == 9000
        assert "resources" in info_dict

    def test_cluster_info(self):
        """اختبار معلومات الكلاستر"""
        node = MeshNode(port=9000)
        cluster_info = node.get_cluster_info()
        assert "node_id" in cluster_info
        assert "state" in cluster_info
        assert "peer_count" in cluster_info
        assert cluster_info["peer_count"] == 0


class TestPeer:
    """اختبارات Peer"""

    def test_peer_creation(self):
        """اختبار إنشاء peer"""
        resources = ResourceSpec(cpu_cores=4.0, memory_mb=8192, gpu_count=1)
        peer = Peer(
            node_id="peer-1",
            hostname="worker-1",
            ip_address="192.168.1.10",
            port=9000,
            resources=resources,
        )
        assert peer.node_id == "peer-1"
        assert peer.address == "192.168.1.10:9000"

    def test_peer_health(self):
        """اختبار صحة peer"""
        resources = ResourceSpec(cpu_cores=4.0, memory_mb=8192, gpu_count=0)
        peer = Peer(
            node_id="peer-1",
            hostname="worker-1",
            ip_address="192.168.1.10",
            port=9000,
            resources=resources,
            last_seen=datetime.utcnow(),
        )
        assert peer.is_healthy is True

    def test_peer_unhealthy_after_failures(self):
        """اختبار عدم صحة peer بعد فشل متعدد"""
        resources = ResourceSpec(cpu_cores=4.0, memory_mb=8192, gpu_count=0)
        peer = Peer(
            node_id="peer-1",
            hostname="worker-1",
            ip_address="192.168.1.10",
            port=9000,
            resources=resources,
            connection_failures=5,
        )
        assert peer.is_healthy is False

    def test_peer_to_dict(self):
        """اختبار تحويل peer لـ dict"""
        resources = ResourceSpec(cpu_cores=4.0, memory_mb=8192, gpu_count=1)
        peer = Peer(
            node_id="peer-1",
            hostname="worker-1",
            ip_address="192.168.1.10",
            port=9000,
            resources=resources,
        )
        peer_dict = peer.to_dict()
        assert peer_dict["node_id"] == "peer-1"
        assert peer_dict["ip_address"] == "192.168.1.10"


class TestGossipMessage:
    """اختبارات GossipMessage"""

    def test_message_creation(self):
        """اختبار إنشاء رسالة"""
        msg = GossipMessage(
            type=MessageType.PING,
            sender_id="node-1",
            data={"key": "value"},
        )
        assert msg.type == MessageType.PING
        assert msg.sender_id == "node-1"
        assert msg.data["key"] == "value"
        assert msg.message_id != ""

    def test_message_to_json(self):
        """اختبار تحويل الرسالة لـ JSON"""
        msg = GossipMessage(
            type=MessageType.PING,
            sender_id="node-1",
        )
        json_str = msg.to_json()
        assert "ping" in json_str
        assert "node-1" in json_str

    def test_message_from_json(self):
        """اختبار إنشاء رسالة من JSON"""
        msg = GossipMessage(
            type=MessageType.PONG,
            sender_id="node-2",
            data={"status": "ok"},
        )
        json_str = msg.to_json()
        parsed = GossipMessage.from_json(json_str)
        assert parsed.type == MessageType.PONG
        assert parsed.sender_id == "node-2"
        assert parsed.data["status"] == "ok"

    def test_message_ttl(self):
        """اختبار TTL"""
        msg = GossipMessage(
            type=MessageType.PEER_LIST,
            sender_id="node-1",
            ttl=3,
        )
        assert msg.ttl == 3


class TestDiscoveryMessage:
    """اختبارات DiscoveryMessage"""

    def test_discovery_message_creation(self):
        """اختبار إنشاء رسالة اكتشاف"""
        msg = DiscoveryMessage(
            node_id="node-1",
            hostname="worker-1",
            ip_address="192.168.1.10",
            port=9000,
        )
        assert msg.node_id == "node-1"
        assert msg.port == 9000

    def test_discovery_message_json(self):
        """اختبار تحويل رسالة الاكتشاف"""
        msg = DiscoveryMessage(
            node_id="node-1",
            hostname="worker-1",
            ip_address="192.168.1.10",
            port=9000,
        )
        json_str = msg.to_json()
        parsed = DiscoveryMessage.from_json(json_str)
        assert parsed is not None
        assert parsed.node_id == "node-1"


class TestTaskRouter:
    """اختبارات TaskRouter"""

    def create_mock_node(self):
        """إنشاء عقدة وهمية للاختبار"""
        return MeshNode(port=9000, node_id="test-node")

    def create_mock_peer(self, node_id: str, cpu: float, memory: int, jobs: int = 0) -> Peer:
        """إنشاء peer وهمي"""
        return Peer(
            node_id=node_id,
            hostname=f"worker-{node_id}",
            ip_address="192.168.1.10",
            port=9000,
            resources=ResourceSpec(cpu_cores=cpu, memory_mb=memory, gpu_count=0),
            jobs_running=jobs,
        )

    def create_mock_job(self, cpu: float = 1.0, memory: int = 512) -> Job:
        """إنشاء مهمة وهمية"""
        from distributed_cluster.models.job import JobSubmission

        submission = JobSubmission(
            command="echo hello",
            resources=ResourceSpec(cpu_cores=cpu, memory_mb=memory, gpu_count=0),
        )
        return Job(
            job_id="job-1",
            submission=submission,
        )

    def test_router_creation(self):
        """اختبار إنشاء router"""
        node = self.create_mock_node()
        router = TaskRouter(node=node, strategy=RoutingStrategy.LEAST_LOADED)
        assert router.strategy == RoutingStrategy.LEAST_LOADED

    def test_least_loaded_routing(self):
        """اختبار التوجيه للأقل حملاً"""
        node = self.create_mock_node()
        router = TaskRouter(node=node, strategy=RoutingStrategy.LEAST_LOADED)

        # إضافة peers
        peer1 = self.create_mock_peer("p1", 4, 8192, jobs=5)
        peer2 = self.create_mock_peer("p2", 4, 8192, jobs=1)
        peer3 = self.create_mock_peer("p3", 4, 8192, jobs=3)

        node.peers = {"p1": peer1, "p2": peer2, "p3": peer3}

        self.create_mock_job()
        selected = router._route_least_loaded([peer1, peer2, peer3])

        assert selected.node_id == "p2"  # الأقل حملاً

    def test_best_fit_routing(self):
        """اختبار التوجيه الأفضل تطابقاً"""
        node = self.create_mock_node()
        router = TaskRouter(node=node, strategy=RoutingStrategy.BEST_FIT)

        peer1 = self.create_mock_peer("p1", 8, 16384)  # موارد كبيرة
        peer2 = self.create_mock_peer("p2", 2, 1024)  # موارد صغيرة
        peer3 = self.create_mock_peer("p3", 4, 4096)  # موارد متوسطة

        job = self.create_mock_job(cpu=2.0, memory=1024)
        selected = router._route_best_fit([peer1, peer2, peer3], job)

        assert selected.node_id == "p2"  # أقل هدر

    def test_round_robin_routing(self):
        """اختبار التوجيه بالتناوب"""
        node = self.create_mock_node()
        router = TaskRouter(node=node, strategy=RoutingStrategy.ROUND_ROBIN)

        peers = [
            self.create_mock_peer("p1", 4, 8192),
            self.create_mock_peer("p2", 4, 8192),
            self.create_mock_peer("p3", 4, 8192),
        ]

        selections = []
        for _ in range(6):
            selected = router._route_round_robin(peers)
            selections.append(selected.node_id)

        # يجب أن يكون بالتناوب
        assert len(set(selections)) == 3


class TestConsensusState:
    """اختبارات ConsensusState"""

    def test_consensus_states(self):
        """اختبار حالات التوافق"""
        assert ConsensusState.FOLLOWER.value == "follower"
        assert ConsensusState.CANDIDATE.value == "candidate"
        assert ConsensusState.LEADER.value == "leader"


class TestLeaderElection:
    """اختبارات LeaderElection"""

    def test_election_creation(self):
        """اختبار إنشاء نظام الانتخاب"""
        node = MeshNode(port=9000, node_id="test-node")
        election = LeaderElection(node=node)
        assert election.is_leader is False
        assert election.current_leader is None

    def test_election_initial_state(self):
        """اختبار الحالة الأولية"""
        node = MeshNode(port=9000)
        election = LeaderElection(node=node)
        assert election.state.state == ConsensusState.FOLLOWER
        assert election.state.term == 0

    def test_election_stats(self):
        """اختبار إحصائيات الانتخاب"""
        node = MeshNode(port=9000)
        election = LeaderElection(node=node)
        stats = election.stats()
        assert "state" in stats
        assert "term" in stats
        assert "is_leader" in stats


class TestNodeInfo:
    """اختبارات NodeInfo"""

    def test_node_info_from_dict(self):
        """اختبار إنشاء NodeInfo من dict"""
        data = {
            "node_id": "test-1",
            "hostname": "worker-1",
            "ip_address": "192.168.1.10",
            "port": 9000,
            "resources": {"cpu_cores": 4.0, "memory_mb": 8192, "gpu_count": 0},
            "current_usage": {
                "cpu_percent": 25.0,
                "memory_used_mb": 4096,
                "memory_total_mb": 8192,
                "memory_percent": 50.0,
            },
            "state": "active",
            "tags": ["gpu"],
            "joined_at": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
        }

        info = NodeInfo.from_dict(data)
        assert info.node_id == "test-1"
        assert info.port == 9000
        assert info.state == NodeState.ACTIVE


class TestRoutingStrategy:
    """اختبارات RoutingStrategy"""

    def test_all_strategies_exist(self):
        """اختبار وجود جميع الاستراتيجيات"""
        strategies = [
            RoutingStrategy.RANDOM,
            RoutingStrategy.ROUND_ROBIN,
            RoutingStrategy.LEAST_LOADED,
            RoutingStrategy.BEST_FIT,
            RoutingStrategy.NEAREST,
            RoutingStrategy.RESOURCE_AWARE,
        ]
        assert len(strategies) == 6


class TestDiscoveryMethod:
    """اختبارات DiscoveryMethod"""

    def test_all_methods_exist(self):
        """اختبار وجود جميع طرق الاكتشاف"""
        methods = [
            DiscoveryMethod.MULTICAST,
            DiscoveryMethod.BOOTSTRAP,
            DiscoveryMethod.GOSSIP,
        ]
        assert len(methods) == 3
