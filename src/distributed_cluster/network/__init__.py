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
]
