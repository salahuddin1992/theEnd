"""
Auto-Discovery Module - اكتشاف تلقائي للعمال
==============================================

Automatic worker discovery using mDNS/Zeroconf and broadcast.
"""

from .mdns import MDNSDiscovery, ServiceInfo
from .broadcast import BroadcastDiscovery
from .manager import DiscoveryManager

__all__ = [
    "MDNSDiscovery",
    "BroadcastDiscovery",
    "DiscoveryManager",
    "ServiceInfo",
]
