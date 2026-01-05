"""
Auto-Discovery Module - اكتشاف تلقائي للعمال
==============================================

Automatic worker discovery using mDNS/Zeroconf and broadcast.
"""

from .broadcast import BroadcastDiscovery
from .manager import DiscoveryManager
from .mdns import MDNSDiscovery, ServiceInfo

__all__ = [
    "MDNSDiscovery",
    "BroadcastDiscovery",
    "DiscoveryManager",
    "ServiceInfo",
]
