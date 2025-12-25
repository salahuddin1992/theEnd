"""
WebSocket-based real-time event streaming.
"""

import asyncio
import json
import logging
import time
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Union
from enum import Enum
import threading

from .events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection states."""
    CONNECTING = "connecting"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class WebSocketConfig:
    """Configuration for WebSocket event streaming."""
    host: str = "0.0.0.0"
    port: int = 8765
    path: str = "/events"
    max_connections: int = 1000
    ping_interval: int = 30
    ping_timeout: int = 10
    max_message_size: int = 1048576  # 1MB
    compression: bool = True
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    auth_required: bool = False
    auth_handler: Optional[Callable[[str], bool]] = None
    heartbeat_interval: int = 5
    reconnect_interval: int = 5
    max_reconnect_attempts: int = 10
    buffer_size: int = 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "max_connections": self.max_connections,
            "ping_interval": self.ping_interval,
            "ping_timeout": self.ping_timeout,
            "max_message_size": self.max_message_size,
            "compression": self.compression,
            "auth_required": self.auth_required,
        }


@dataclass
class WebSocketClient:
    """Represents a connected WebSocket client."""
    client_id: str
    websocket: Any  # WebSocket connection object
    connected_at: datetime = field(default_factory=datetime.utcnow)
    subscriptions: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    authenticated: bool = False
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return self.websocket is not None

    def subscribe(self, topic: str):
        self.subscriptions.add(topic)

    def unsubscribe(self, topic: str):
        self.subscriptions.discard(topic)


class WebSocketEventServer:
    """WebSocket server for real-time event streaming."""

    def __init__(self, config: Optional[WebSocketConfig] = None):
        self.config = config or WebSocketConfig()
        self._clients: Dict[str, WebSocketClient] = {}
        self._topic_subscribers: Dict[str, Set[str]] = {}  # topic -> set of client_ids
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._server = None
        self._running = False
        self._lock = threading.Lock()
        self._metrics = {
            "connections_total": 0,
            "messages_sent": 0,
            "messages_received": 0,
            "errors": 0,
        }

    async def start(self):
        """Start the WebSocket server."""
        try:
            import websockets

            ssl_context = None
            if self.config.ssl_cert and self.config.ssl_key:
                import ssl
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(
                    self.config.ssl_cert,
                    self.config.ssl_key
                )

            self._server = await websockets.serve(
                self._handle_connection,
                self.config.host,
                self.config.port,
                ssl=ssl_context,
                max_size=self.config.max_message_size,
                ping_interval=self.config.ping_interval,
                ping_timeout=self.config.ping_timeout,
                compression="deflate" if self.config.compression else None,
            )

            self._running = True
            logger.info(f"WebSocket server started on ws://{self.config.host}:{self.config.port}{self.config.path}")

            # Start heartbeat task
            asyncio.create_task(self._heartbeat_loop())

        except ImportError:
            logger.error("websockets not installed. Run: pip install websockets")
            raise

    async def stop(self):
        """Stop the WebSocket server."""
        self._running = False

        # Close all client connections
        for client in list(self._clients.values()):
            await self._disconnect_client(client.client_id)

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        logger.info("WebSocket server stopped")

    async def _handle_connection(self, websocket, path):
        """Handle a new WebSocket connection."""
        if len(self._clients) >= self.config.max_connections:
            await websocket.close(1013, "Max connections reached")
            return

        client_id = str(uuid.uuid4())
        client = WebSocketClient(
            client_id=client_id,
            websocket=websocket,
        )

        # Authentication if required
        if self.config.auth_required:
            try:
                auth_message = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=10
                )
                auth_data = json.loads(auth_message)
                token = auth_data.get("token")

                if self.config.auth_handler and not self.config.auth_handler(token):
                    await websocket.close(4001, "Authentication failed")
                    return

                client.authenticated = True
                client.user_id = auth_data.get("user_id")
                client.tenant_id = auth_data.get("tenant_id")

            except asyncio.TimeoutError:
                await websocket.close(4002, "Authentication timeout")
                return

        with self._lock:
            self._clients[client_id] = client
            self._metrics["connections_total"] += 1

        logger.info(f"Client {client_id} connected")

        # Send welcome message
        await self._send_to_client(client_id, {
            "type": "connected",
            "client_id": client_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        try:
            async for message in websocket:
                await self._handle_message(client_id, message)
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
            self._metrics["errors"] += 1
        finally:
            await self._disconnect_client(client_id)

    async def _handle_message(self, client_id: str, message: str):
        """Handle a message from a client."""
        self._metrics["messages_received"] += 1

        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "subscribe":
                await self._handle_subscribe(client_id, data)
            elif msg_type == "unsubscribe":
                await self._handle_unsubscribe(client_id, data)
            elif msg_type == "publish":
                await self._handle_publish(client_id, data)
            elif msg_type == "ping":
                await self._send_to_client(client_id, {"type": "pong"})
            else:
                # Dispatch to registered handlers
                handlers = self._event_handlers.get(msg_type, [])
                for handler in handlers:
                    try:
                        await handler(client_id, data)
                    except Exception as e:
                        logger.error(f"Handler error: {e}")

        except json.JSONDecodeError:
            await self._send_to_client(client_id, {
                "type": "error",
                "message": "Invalid JSON"
            })

    async def _handle_subscribe(self, client_id: str, data: Dict):
        """Handle subscription request."""
        topics = data.get("topics", [])
        if isinstance(topics, str):
            topics = [topics]

        client = self._clients.get(client_id)
        if not client:
            return

        with self._lock:
            for topic in topics:
                client.subscribe(topic)
                if topic not in self._topic_subscribers:
                    self._topic_subscribers[topic] = set()
                self._topic_subscribers[topic].add(client_id)

        await self._send_to_client(client_id, {
            "type": "subscribed",
            "topics": topics,
        })

        logger.debug(f"Client {client_id} subscribed to: {topics}")

    async def _handle_unsubscribe(self, client_id: str, data: Dict):
        """Handle unsubscription request."""
        topics = data.get("topics", [])
        if isinstance(topics, str):
            topics = [topics]

        client = self._clients.get(client_id)
        if not client:
            return

        with self._lock:
            for topic in topics:
                client.unsubscribe(topic)
                if topic in self._topic_subscribers:
                    self._topic_subscribers[topic].discard(client_id)

        await self._send_to_client(client_id, {
            "type": "unsubscribed",
            "topics": topics,
        })

    async def _handle_publish(self, client_id: str, data: Dict):
        """Handle publish request from a client."""
        topic = data.get("topic")
        payload = data.get("payload", {})

        if not topic:
            await self._send_to_client(client_id, {
                "type": "error",
                "message": "Topic required"
            })
            return

        event = Event(
            event_type=EventType.CUSTOM,
            payload=payload,
        )
        event.metadata.source = f"websocket:{client_id}"

        await self.broadcast(topic, event)

    async def _disconnect_client(self, client_id: str):
        """Disconnect a client."""
        with self._lock:
            client = self._clients.pop(client_id, None)
            if client:
                # Remove from all topic subscriptions
                for topic in client.subscriptions:
                    if topic in self._topic_subscribers:
                        self._topic_subscribers[topic].discard(client_id)

                # Close WebSocket
                if client.websocket:
                    try:
                        await client.websocket.close()
                    except Exception:
                        pass

        logger.info(f"Client {client_id} disconnected")

    async def _send_to_client(self, client_id: str, data: Dict) -> bool:
        """Send data to a specific client."""
        client = self._clients.get(client_id)
        if not client or not client.websocket:
            return False

        try:
            await client.websocket.send(json.dumps(data))
            self._metrics["messages_sent"] += 1
            return True
        except Exception as e:
            logger.error(f"Error sending to client {client_id}: {e}")
            return False

    async def broadcast(self, topic: str, event: Event):
        """Broadcast an event to all subscribers of a topic."""
        subscribers = self._topic_subscribers.get(topic, set())
        if not subscribers:
            return

        message = {
            "type": "event",
            "topic": topic,
            "event": event.to_dict(),
        }

        tasks = [
            self._send_to_client(client_id, message)
            for client_id in subscribers
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_all(self, event: Event):
        """Broadcast an event to all connected clients."""
        message = {
            "type": "event",
            "topic": "__all__",
            "event": event.to_dict(),
        }

        tasks = [
            self._send_to_client(client_id, message)
            for client_id in self._clients.keys()
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def send_to_user(self, user_id: str, event: Event):
        """Send an event to all connections of a specific user."""
        message = {
            "type": "event",
            "topic": f"user:{user_id}",
            "event": event.to_dict(),
        }

        for client in self._clients.values():
            if client.user_id == user_id:
                await self._send_to_client(client.client_id, message)

    async def send_to_tenant(self, tenant_id: str, event: Event):
        """Send an event to all connections of a specific tenant."""
        message = {
            "type": "event",
            "topic": f"tenant:{tenant_id}",
            "event": event.to_dict(),
        }

        for client in self._clients.values():
            if client.tenant_id == tenant_id:
                await self._send_to_client(client.client_id, message)

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to all clients."""
        while self._running:
            await asyncio.sleep(self.config.heartbeat_interval)

            heartbeat = {
                "type": "heartbeat",
                "timestamp": datetime.utcnow().isoformat(),
            }

            for client_id in list(self._clients.keys()):
                await self._send_to_client(client_id, heartbeat)

    def on_message(self, msg_type: str, handler: Callable):
        """Register a handler for a message type."""
        if msg_type not in self._event_handlers:
            self._event_handlers[msg_type] = []
        self._event_handlers[msg_type].append(handler)

    def get_metrics(self) -> Dict[str, Any]:
        """Get server metrics."""
        return {
            **self._metrics,
            "active_connections": len(self._clients),
            "topics": len(self._topic_subscribers),
        }

    def get_clients(self) -> List[Dict[str, Any]]:
        """Get list of connected clients."""
        return [
            {
                "client_id": c.client_id,
                "connected_at": c.connected_at.isoformat(),
                "subscriptions": list(c.subscriptions),
                "authenticated": c.authenticated,
                "user_id": c.user_id,
                "tenant_id": c.tenant_id,
            }
            for c in self._clients.values()
        ]


class WebSocketEventClient:
    """WebSocket client for receiving real-time events."""

    def __init__(self, config: Optional[WebSocketConfig] = None):
        self.config = config or WebSocketConfig()
        self._websocket = None
        self._state = ConnectionState.CLOSED
        self._subscriptions: Set[str] = set()
        self._handlers: Dict[str, List[Callable]] = {}
        self._reconnect_attempts = 0
        self._receive_task = None
        self._buffer: asyncio.Queue = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.OPEN

    async def connect(self, url: Optional[str] = None, token: Optional[str] = None):
        """Connect to the WebSocket server."""
        try:
            import websockets

            if url is None:
                protocol = "wss" if self.config.ssl_cert else "ws"
                url = f"{protocol}://{self.config.host}:{self.config.port}{self.config.path}"

            self._state = ConnectionState.CONNECTING
            self._buffer = asyncio.Queue(maxsize=self.config.buffer_size)

            self._websocket = await websockets.connect(
                url,
                max_size=self.config.max_message_size,
                ping_interval=self.config.ping_interval,
                ping_timeout=self.config.ping_timeout,
            )

            # Authenticate if token provided
            if token:
                await self._websocket.send(json.dumps({
                    "token": token,
                }))

            # Wait for connected message
            response = await asyncio.wait_for(
                self._websocket.recv(),
                timeout=10
            )
            data = json.loads(response)
            if data.get("type") != "connected":
                raise ConnectionError("Failed to connect")

            self._state = ConnectionState.OPEN
            self._reconnect_attempts = 0

            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())

            logger.info(f"Connected to WebSocket server: {url}")

        except Exception as e:
            self._state = ConnectionState.CLOSED
            logger.error(f"Failed to connect: {e}")
            raise

    async def _receive_loop(self):
        """Background task to receive messages."""
        while self._state == ConnectionState.OPEN:
            try:
                message = await self._websocket.recv()
                data = json.loads(message)

                msg_type = data.get("type")

                if msg_type == "event":
                    topic = data.get("topic")
                    event_data = data.get("event", {})
                    event = Event.from_dict(event_data)

                    # Dispatch to handlers
                    for handler in self._handlers.get(topic, []):
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(event)
                            else:
                                handler(event)
                        except Exception as e:
                            logger.error(f"Handler error: {e}")

                    # Also dispatch to wildcard handlers
                    for handler in self._handlers.get("*", []):
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(topic, event)
                            else:
                                handler(topic, event)
                        except Exception as e:
                            logger.error(f"Handler error: {e}")

                elif msg_type == "heartbeat":
                    pass  # Ignore heartbeats

                elif msg_type == "error":
                    logger.error(f"Server error: {data.get('message')}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Receive error: {e}")
                if self._state == ConnectionState.OPEN:
                    await self._handle_disconnect()
                break

    async def _handle_disconnect(self):
        """Handle unexpected disconnection."""
        self._state = ConnectionState.CLOSED

        if self._reconnect_attempts < self.config.max_reconnect_attempts:
            self._reconnect_attempts += 1
            await asyncio.sleep(self.config.reconnect_interval)
            try:
                await self.connect()
                # Re-subscribe to topics
                for topic in self._subscriptions:
                    await self.subscribe(topic)
            except Exception as e:
                logger.error(f"Reconnect attempt {self._reconnect_attempts} failed: {e}")

    async def disconnect(self):
        """Disconnect from the server."""
        self._state = ConnectionState.CLOSING

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._websocket:
            await self._websocket.close()

        self._state = ConnectionState.CLOSED
        logger.info("Disconnected from WebSocket server")

    async def subscribe(self, topics: Union[str, List[str]]):
        """Subscribe to topics."""
        if isinstance(topics, str):
            topics = [topics]

        if not self.is_connected:
            raise RuntimeError("Not connected")

        await self._websocket.send(json.dumps({
            "type": "subscribe",
            "topics": topics,
        }))

        for topic in topics:
            self._subscriptions.add(topic)

    async def unsubscribe(self, topics: Union[str, List[str]]):
        """Unsubscribe from topics."""
        if isinstance(topics, str):
            topics = [topics]

        if not self.is_connected:
            return

        await self._websocket.send(json.dumps({
            "type": "unsubscribe",
            "topics": topics,
        }))

        for topic in topics:
            self._subscriptions.discard(topic)

    async def publish(self, topic: str, payload: Dict[str, Any]):
        """Publish an event to a topic."""
        if not self.is_connected:
            raise RuntimeError("Not connected")

        await self._websocket.send(json.dumps({
            "type": "publish",
            "topic": topic,
            "payload": payload,
        }))

    def on(self, topic: str, handler: Callable):
        """Register a handler for events on a topic."""
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

    def off(self, topic: str, handler: Optional[Callable] = None):
        """Remove a handler for a topic."""
        if topic not in self._handlers:
            return

        if handler:
            self._handlers[topic] = [h for h in self._handlers[topic] if h != handler]
        else:
            del self._handlers[topic]

    async def send_raw(self, data: Dict[str, Any]):
        """Send raw data to the server."""
        if not self.is_connected:
            raise RuntimeError("Not connected")

        await self._websocket.send(json.dumps(data))
