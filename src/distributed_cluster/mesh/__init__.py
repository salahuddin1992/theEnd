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

from .node import MeshNode, NodeState, NodeInfo
from .peer import Peer, PeerConnection
from .discovery import PeerDiscovery, DiscoveryMethod
from .gossip import GossipProtocol, GossipMessage
from .router import TaskRouter, RoutingStrategy
from .consensus import LeaderElection, ConsensusState

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
