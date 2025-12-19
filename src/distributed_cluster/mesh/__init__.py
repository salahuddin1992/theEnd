"""
Mesh Network Module - شبكة لامركزية للحوسبة الموزعة

This module provides a decentralized mesh network where nodes can communicate
directly without a central master. Features:

- Peer-to-peer communication
- Automatic peer discovery (mDNS, gossip)
- Distributed task routing
- Leader election for coordination
- Fault tolerance and self-healing
"""

from .consensus import ConsensusState, LeaderElection
from .discovery import DiscoveryMethod, PeerDiscovery
from .gossip import GossipMessage, GossipProtocol
from .node import MeshNode, NodeInfo, NodeState
from .peer import Peer, PeerConnection
from .router import RoutingStrategy, TaskRouter

__all__ = [
    "MeshNode",
    "NodeState",
    "NodeInfo",
    "Peer",
    "PeerConnection",
    "PeerDiscovery",
    "DiscoveryMethod",
    "GossipProtocol",
    "GossipMessage",
    "TaskRouter",
    "RoutingStrategy",
    "LeaderElection",
    "ConsensusState",
]
