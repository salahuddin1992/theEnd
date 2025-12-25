"""
WebSocket Gateway - بوابة WebSocket
====================================

Real-time WebSocket support for the API Gateway.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class WebSocketState(str, Enum):
    """WebSocket connection state."""
    CONNECTING = "connecting"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


class MessageType(str, Enum):
    """WebSocket message types."""
    TEXT = "text"
    BINARY = "binary"
    PING = "ping"
    PONG = "pong"
    CLOSE = "close"


@dataclass
class WebSocketMessage:
    """WebSocket message."""
    message_id: str
    message_type: MessageType
    data: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps({
            "id": self.message_id,
            "type": self.message_type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        })

    @classmethod
    def text(cls, data: Any) -> WebSocketMessage:
        """Create text message."""
        return cls(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.TEXT,
            data=data,
        )

    @classmethod
    def from_json(cls, json_str: str) -> WebSocketMessage:
        """Parse from JSON string."""
        data = json.loads(json_str)
        return cls(
            message_id=data.get("id", str(uuid.uuid4())),
            message_type=MessageType(data.get("type", "text")),
            data=data.get("data"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
        )


@dataclass
class WebSocketConnection:
    """Represents a WebSocket connection."""
    connection_id: str
    client_ip: str
    state: WebSocketState = WebSocketState.CONNECTING

    # Connection info
    path: str = "/"
    query_params: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)

    # Subscriptions
    subscriptions: Set[str] = field(default_factory=set)

    # User info
    user_id: Optional[str] = None
    user_data: Dict[str, Any] = field(default_factory=dict)

    # Timing
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_message_at: Optional[datetime] = None
    last_ping_at: Optional[datetime] = None

    # Stats
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0

    def subscribe(self, channel: str) -> None:
        """Subscribe to a channel."""
        self.subscriptions.add(channel)

    def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel."""
        self.subscriptions.discard(channel)

    def is_subscribed(self, channel: str) -> bool:
        """Check if subscribed to channel."""
        return channel in self.subscriptions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "client_ip": self.client_ip,
            "state": self.state.value,
            "path": self.path,
            "user_id": self.user_id,
            "subscriptions": list(self.subscriptions),
            "connected_at": self.connected_at.isoformat(),
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
        }


class WebSocketHandler:
    """Handler for WebSocket messages."""

    async def on_connect(self, connection: WebSocketConnection) -> bool:
        """
        Called when a new connection is established.

        Return False to reject the connection.
        """
        return True

    async def on_disconnect(self, connection: WebSocketConnection) -> None:
        """Called when a connection is closed."""
        pass

    async def on_message(
        self,
        connection: WebSocketConnection,
        message: WebSocketMessage,
    ) -> Optional[WebSocketMessage]:
        """
        Called when a message is received.

        Return a message to send back to the client.
        """
        return None

    async def on_error(
        self,
        connection: WebSocketConnection,
        error: Exception,
    ) -> None:
        """Called when an error occurs."""
        logger.error(f"WebSocket error for {connection.connection_id}: {error}")


class ConnectionManager:
    """
    WebSocket Connection Manager.

    Manages WebSocket connections, channels, and broadcasting.
    """

    def __init__(self, max_connections: int = 10000):
        self.max_connections = max_connections
        self._connections: Dict[str, WebSocketConnection] = {}
        self._user_connections: Dict[str, Set[str]] = {}  # user_id -> connection_ids
        self._channel_connections: Dict[str, Set[str]] = {}  # channel -> connection_ids
        self._handlers: List[WebSocketHandler] = []
        self._lock = asyncio.Lock()

    async def connect(
        self,
        connection: WebSocketConnection,
    ) -> bool:
        """Register a new connection."""
        async with self._lock:
            if len(self._connections) >= self.max_connections:
                logger.warning("Max connections reached")
                return False

            # Call handlers
            for handler in self._handlers:
                if not await handler.on_connect(connection):
                    return False

            self._connections[connection.connection_id] = connection
            connection.state = WebSocketState.OPEN

            # Track user connection
            if connection.user_id:
                if connection.user_id not in self._user_connections:
                    self._user_connections[connection.user_id] = set()
                self._user_connections[connection.user_id].add(connection.connection_id)

            logger.info(f"WebSocket connected: {connection.connection_id}")
            return True

    async def disconnect(self, connection_id: str) -> None:
        """Remove a connection."""
        async with self._lock:
            connection = self._connections.pop(connection_id, None)
            if not connection:
                return

            connection.state = WebSocketState.CLOSED

            # Remove from user tracking
            if connection.user_id and connection.user_id in self._user_connections:
                self._user_connections[connection.user_id].discard(connection_id)
                if not self._user_connections[connection.user_id]:
                    del self._user_connections[connection.user_id]

            # Remove from channels
            for channel in connection.subscriptions:
                if channel in self._channel_connections:
                    self._channel_connections[channel].discard(connection_id)

            # Call handlers
            for handler in self._handlers:
                await handler.on_disconnect(connection)

            logger.info(f"WebSocket disconnected: {connection_id}")

    def get_connection(self, connection_id: str) -> Optional[WebSocketConnection]:
        """Get connection by ID."""
        return self._connections.get(connection_id)

    def get_user_connections(self, user_id: str) -> List[WebSocketConnection]:
        """Get all connections for a user."""
        connection_ids = self._user_connections.get(user_id, set())
        return [
            self._connections[cid]
            for cid in connection_ids
            if cid in self._connections
        ]

    async def subscribe(self, connection_id: str, channel: str) -> None:
        """Subscribe a connection to a channel."""
        async with self._lock:
            connection = self._connections.get(connection_id)
            if not connection:
                return

            connection.subscribe(channel)

            if channel not in self._channel_connections:
                self._channel_connections[channel] = set()
            self._channel_connections[channel].add(connection_id)

    async def unsubscribe(self, connection_id: str, channel: str) -> None:
        """Unsubscribe a connection from a channel."""
        async with self._lock:
            connection = self._connections.get(connection_id)
            if connection:
                connection.unsubscribe(channel)

            if channel in self._channel_connections:
                self._channel_connections[channel].discard(connection_id)

    def add_handler(self, handler: WebSocketHandler) -> None:
        """Add a message handler."""
        self._handlers.append(handler)

    async def handle_message(
        self,
        connection_id: str,
        message: WebSocketMessage,
    ) -> Optional[WebSocketMessage]:
        """Handle an incoming message."""
        connection = self._connections.get(connection_id)
        if not connection:
            return None

        connection.messages_received += 1
        connection.last_message_at = datetime.utcnow()

        # Call handlers
        for handler in self._handlers:
            try:
                response = await handler.on_message(connection, message)
                if response:
                    return response
            except Exception as e:
                await handler.on_error(connection, e)

        return None

    async def send_to_connection(
        self,
        connection_id: str,
        message: WebSocketMessage,
        send_fn: Callable,
    ) -> bool:
        """Send message to a specific connection."""
        connection = self._connections.get(connection_id)
        if not connection or connection.state != WebSocketState.OPEN:
            return False

        try:
            await send_fn(message.to_json())
            connection.messages_sent += 1
            connection.bytes_sent += len(message.to_json())
            return True
        except Exception as e:
            logger.error(f"Send error for {connection_id}: {e}")
            await self.disconnect(connection_id)
            return False

    async def broadcast_to_channel(
        self,
        channel: str,
        message: WebSocketMessage,
        send_fn: Callable,
        exclude: Optional[Set[str]] = None,
    ) -> int:
        """Broadcast message to all subscribers of a channel."""
        exclude = exclude or set()
        sent = 0

        connection_ids = self._channel_connections.get(channel, set()).copy()
        for connection_id in connection_ids:
            if connection_id in exclude:
                continue
            if await self.send_to_connection(connection_id, message, send_fn):
                sent += 1

        return sent

    async def broadcast_to_user(
        self,
        user_id: str,
        message: WebSocketMessage,
        send_fn: Callable,
    ) -> int:
        """Broadcast message to all connections of a user."""
        sent = 0

        connection_ids = self._user_connections.get(user_id, set()).copy()
        for connection_id in connection_ids:
            if await self.send_to_connection(connection_id, message, send_fn):
                sent += 1

        return sent

    async def broadcast_all(
        self,
        message: WebSocketMessage,
        send_fn: Callable,
        exclude: Optional[Set[str]] = None,
    ) -> int:
        """Broadcast message to all connections."""
        exclude = exclude or set()
        sent = 0

        for connection_id in list(self._connections.keys()):
            if connection_id in exclude:
                continue
            if await self.send_to_connection(connection_id, message, send_fn):
                sent += 1

        return sent

    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            "total_connections": len(self._connections),
            "total_users": len(self._user_connections),
            "total_channels": len(self._channel_connections),
            "connections_by_state": {
                state.value: sum(
                    1 for c in self._connections.values()
                    if c.state == state
                )
                for state in WebSocketState
            },
        }

    def list_connections(self) -> List[Dict[str, Any]]:
        """List all connections."""
        return [c.to_dict() for c in self._connections.values()]

    def list_channels(self) -> Dict[str, int]:
        """List channels and subscriber counts."""
        return {
            channel: len(connections)
            for channel, connections in self._channel_connections.items()
        }


class WebSocketGateway:
    """
    WebSocket Gateway - بوابة WebSocket.

    Provides WebSocket support for the API Gateway.

    Example:
        gateway = WebSocketGateway()

        # Add handler
        gateway.add_handler(MyHandler())

        # Handle connection
        connection = WebSocketConnection(
            connection_id=str(uuid.uuid4()),
            client_ip="127.0.0.1",
            path="/ws",
        )

        await gateway.connect(connection)

        # Handle message
        response = await gateway.handle_message(
            connection.connection_id,
            WebSocketMessage.text({"action": "subscribe", "channel": "updates"})
        )

        # Broadcast
        await gateway.broadcast("updates", WebSocketMessage.text({"event": "new_data"}))
    """

    def __init__(self, max_connections: int = 10000):
        self.connection_manager = ConnectionManager(max_connections)
        self._running = False

    def add_handler(self, handler: WebSocketHandler) -> None:
        """Add a message handler."""
        self.connection_manager.add_handler(handler)

    async def connect(self, connection: WebSocketConnection) -> bool:
        """Handle new connection."""
        return await self.connection_manager.connect(connection)

    async def disconnect(self, connection_id: str) -> None:
        """Handle disconnection."""
        await self.connection_manager.disconnect(connection_id)

    async def handle_message(
        self,
        connection_id: str,
        message: WebSocketMessage,
    ) -> Optional[WebSocketMessage]:
        """Handle incoming message."""
        return await self.connection_manager.handle_message(connection_id, message)

    async def subscribe(self, connection_id: str, channel: str) -> None:
        """Subscribe to channel."""
        await self.connection_manager.subscribe(connection_id, channel)

    async def unsubscribe(self, connection_id: str, channel: str) -> None:
        """Unsubscribe from channel."""
        await self.connection_manager.unsubscribe(connection_id, channel)

    async def send(
        self,
        connection_id: str,
        data: Any,
        send_fn: Callable,
    ) -> bool:
        """Send message to connection."""
        message = WebSocketMessage.text(data)
        return await self.connection_manager.send_to_connection(
            connection_id, message, send_fn
        )

    async def broadcast(
        self,
        channel: str,
        data: Any,
        send_fn: Callable,
        exclude: Optional[Set[str]] = None,
    ) -> int:
        """Broadcast to channel."""
        message = WebSocketMessage.text(data)
        return await self.connection_manager.broadcast_to_channel(
            channel, message, send_fn, exclude
        )

    async def broadcast_to_user(
        self,
        user_id: str,
        data: Any,
        send_fn: Callable,
    ) -> int:
        """Broadcast to user."""
        message = WebSocketMessage.text(data)
        return await self.connection_manager.broadcast_to_user(
            user_id, message, send_fn
        )

    async def broadcast_all(
        self,
        data: Any,
        send_fn: Callable,
        exclude: Optional[Set[str]] = None,
    ) -> int:
        """Broadcast to all."""
        message = WebSocketMessage.text(data)
        return await self.connection_manager.broadcast_all(
            message, send_fn, exclude
        )

    def get_connection(self, connection_id: str) -> Optional[WebSocketConnection]:
        """Get connection by ID."""
        return self.connection_manager.get_connection(connection_id)

    def get_user_connections(self, user_id: str) -> List[WebSocketConnection]:
        """Get user connections."""
        return self.connection_manager.get_user_connections(user_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get gateway statistics."""
        return self.connection_manager.get_stats()

    def list_channels(self) -> Dict[str, int]:
        """List channels."""
        return self.connection_manager.list_channels()

    async def start(self) -> None:
        """Start the gateway."""
        self._running = True
        logger.info("WebSocket Gateway started")

    async def stop(self) -> None:
        """Stop the gateway."""
        self._running = False

        # Close all connections
        for connection_id in list(self.connection_manager._connections.keys()):
            await self.disconnect(connection_id)

        logger.info("WebSocket Gateway stopped")
