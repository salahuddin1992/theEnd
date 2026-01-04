"""
Network Module - شبكة الاتصالات
================================

نظام اكتشاف والتواصل بين التطبيقات:
- الشبكة المحلية (Local Network Discovery)
- الإنترنت P2P (Internet P2P Connection)
"""

from distributed_cluster.network.internet_p2p import (
    ConnectionRequest,
    ConnectionRequestStatus,
    InternetMessageType,
    InternetP2PManager,
    InternetP2PServer,
    InternetPeerConnection,
    SharedInfo,
    generate_connection_code,
    get_public_ip,
    parse_connection_code,
)

# Load Balancer
from distributed_cluster.network.load_balancer import (
    Backend,
    BackendStatus,
    ConsistentHashStrategy,
    IPHashStrategy,
    LeastConnectionsStrategy,
    LeastResponseTimeStrategy,
    LoadBalancer,
    LoadBalancerAlgorithm,
    LoadBalancerPool,
    LoadBalancerStats,
    LoadBalancerStrategy,
    RandomStrategy,
    RoundRobinStrategy,
    WeightedRoundRobinStrategy,
    create_load_balancer,
    get_load_balancer,
    load_balancer_pool,
)
from distributed_cluster.network.network_stack import (
    DNSRecord,
    DNSRecordType,
    NebulaNetworkRegistry,
    NetworkNode,
    NetworkRouter,
    NetworkStackManager,
    NodeIdentity,
    RelayServer,
    RelaySession,
    Route,
    SimpleDNSServer,
)
from distributed_cluster.network.peer_discovery import (
    AppInfo,
    DeviceInfo,
    MessageType,
    PeerConnection,
    PeerDiscovery,
    PeerInfo,
    PeerManager,
    PeerMessage,
    PeerServer,
    PeerStatus,
)

# Service Discovery
from distributed_cluster.network.service_discovery import (
    ConsulBackend,
    EtcdBackend,
    InMemoryBackend,
    ServiceDefinition,
    ServiceDiscoveryBackend,
    ServiceInstance,
    ServiceRegistry,
    ServiceStatus,
    discover_services,
    get_registry,
    register_service,
    set_registry,
)

__all__ = [
    # Local Network
    "DeviceInfo",
    "AppInfo",
    "PeerInfo",
    "PeerStatus",
    "PeerMessage",
    "MessageType",
    "PeerDiscovery",
    "PeerConnection",
    "PeerServer",
    "PeerManager",
    # Internet P2P
    "ConnectionRequest",
    "ConnectionRequestStatus",
    "InternetMessageType",
    "SharedInfo",
    "InternetPeerConnection",
    "InternetP2PServer",
    "InternetP2PManager",
    "generate_connection_code",
    "parse_connection_code",
    "get_public_ip",
    # Network Stack
    "DNSRecordType",
    "DNSRecord",
    "NebulaNetworkRegistry",
    "SimpleDNSServer",
    "Route",
    "NetworkRouter",
    "RelaySession",
    "RelayServer",
    "NodeIdentity",
    "NetworkNode",
    "NetworkStackManager",
    # Load Balancer
    "LoadBalancer",
    "LoadBalancerAlgorithm",
    "LoadBalancerPool",
    "LoadBalancerStrategy",
    "Backend",
    "BackendStatus",
    "LoadBalancerStats",
    "RoundRobinStrategy",
    "WeightedRoundRobinStrategy",
    "LeastConnectionsStrategy",
    "IPHashStrategy",
    "LeastResponseTimeStrategy",
    "RandomStrategy",
    "ConsistentHashStrategy",
    "load_balancer_pool",
    "get_load_balancer",
    "create_load_balancer",
    # Service Discovery
    "ServiceRegistry",
    "ServiceInstance",
    "ServiceDefinition",
    "ServiceStatus",
    "ServiceDiscoveryBackend",
    "InMemoryBackend",
    "ConsulBackend",
    "EtcdBackend",
    "get_registry",
    "set_registry",
    "register_service",
    "discover_services",
]
