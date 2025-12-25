"""
Network Module - شبكة الاتصالات
================================

نظام اكتشاف والتواصل بين التطبيقات:
- الشبكة المحلية (Local Network Discovery)
- الإنترنت P2P (Internet P2P Connection)
"""

from distributed_cluster.network.peer_discovery import (
    DeviceInfo,
    AppInfo,
    PeerInfo,
    PeerStatus,
    PeerMessage,
    MessageType,
    PeerDiscovery,
    PeerConnection,
    PeerServer,
    PeerManager,
)

from distributed_cluster.network.internet_p2p import (
    ConnectionRequest,
    ConnectionRequestStatus,
    InternetMessageType,
    SharedInfo,
    InternetPeerConnection,
    InternetP2PServer,
    InternetP2PManager,
    generate_connection_code,
    parse_connection_code,
    get_public_ip,
)

from distributed_cluster.network.network_stack import (
    DNSRecordType,
    DNSRecord,
    NebulaNetworkRegistry,
    SimpleDNSServer,
    Route,
    NetworkRouter,
    RelaySession,
    RelayServer,
    NodeIdentity,
    NetworkNode,
    NetworkStackManager,
)

# Load Balancer
from distributed_cluster.network.load_balancer import (
    LoadBalancer,
    LoadBalancerAlgorithm,
    LoadBalancerPool,
    LoadBalancerStrategy,
    Backend,
    BackendStatus,
    LoadBalancerStats,
    RoundRobinStrategy,
    WeightedRoundRobinStrategy,
    LeastConnectionsStrategy,
    IPHashStrategy,
    LeastResponseTimeStrategy,
    RandomStrategy,
    ConsistentHashStrategy,
    load_balancer_pool,
    get_load_balancer,
    create_load_balancer,
)

# Service Discovery
from distributed_cluster.network.service_discovery import (
    ServiceRegistry,
    ServiceInstance,
    ServiceDefinition,
    ServiceStatus,
    ServiceDiscoveryBackend,
    InMemoryBackend,
    ConsulBackend,
    EtcdBackend,
    get_registry,
    set_registry,
    register_service,
    discover_services,
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
