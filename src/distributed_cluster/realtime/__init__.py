"""
Real-time Updates Module
========================

دعم التحديثات الفورية عبر WebSocket.
"""

from distributed_cluster.realtime.event_broadcaster import EventBroadcaster, EventSubscription
from distributed_cluster.realtime.websocket_manager import ConnectionInfo, WebSocketManager

__all__ = [
    "WebSocketManager",
    "ConnectionInfo",
    "EventBroadcaster",
    "EventSubscription",
]
