"""
Real-time Updates Module
========================

دعم التحديثات الفورية عبر WebSocket.
"""

from distributed_cluster.realtime.websocket_manager import WebSocketManager, ConnectionInfo
from distributed_cluster.realtime.event_broadcaster import EventBroadcaster, EventSubscription

__all__ = [
    "WebSocketManager",
    "ConnectionInfo",
    "EventBroadcaster",
    "EventSubscription",
]
