"""
WebSocket Connection Pool for NebulaCompute.

Provides efficient WebSocket connection management with:
- Connection pooling per endpoint
- Automatic reconnection
- Health monitoring
- Message buffering
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
from contextlib import asynccontextmanager
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class WebSocketState(Enum):
    """WebSocket connection state."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    CLOSED = "closed"


@dataclass
class WebSocketConfig:
    """Configuration for WebSocket connection pool."""
    # Connection settings
    max_connections: int = 100
    max_connections_per_endpoint: int = 10
    connection_timeout: float = 10.0
    ping_interval: float = 30.0
    ping_timeout: float = 10.0

    # Reconnection settings
    auto_reconnect: bool = True
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 60.0
    max_reconnect_attempts: int = 10

    # Buffer settings
    message_buffer_size: int = 1000
    send_buffer_size: int = 100

    # Heartbeat
    heartbeat_interval: float = 30.0


@dataclass
class WebSocketConnection:
    """WebSocket connection wrapper with metadata."""
    ws: Any
    endpoint: str
    state: WebSocketState = WebSocketState.CONNECTING
    created_at: datetime = field(default_factory=datetime.now)
    last_message: Optional[datetime] = None
    message_count: int = 0
    reconnect_count: int = 0

    @property
    def age_seconds(self) -> float:
        """Get connection age."""
        return (datetime.now() - self.created_at).total_seconds()

    @property
    def idle_seconds(self) -> float:
        """Get idle time since last message."""
        if self.last_message:
            return (datetime.now() - self.last_message).total_seconds()
        return self.age_seconds


class WebSocketPool:
    """
    WebSocket connection pool.

    Features:
    - Connection pooling per endpoint
    - Automatic reconnection with backoff
    - Message buffering
    - Health monitoring
    - Event callbacks
    """

    def __init__(self, config: Optional[WebSocketConfig] = None):
        """
        Initialize WebSocket pool.

        Args:
            config: Pool configuration
        """
        self.config = config or WebSocketConfig()

        self._connections: Dict[str, List[WebSocketConnection]] = {}
        self._available: Dict[str, asyncio.Queue] = {}
        self._message_handlers: Dict[str, List[Callable]] = {}
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}

        self._lock = asyncio.Lock()
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Stats
        self._total_connections = 0
        self._total_messages = 0
        self._total_errors = 0

    async def start(self) -> None:
        """Start the WebSocket pool."""
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("WebSocketPool started")

    async def close(self) -> None:
        """Close the pool and all connections."""
        self._running = False

        # Cancel heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Cancel reconnect tasks
        for task in self._reconnect_tasks.values():
            task.cancel()

        # Close all connections
        for endpoint, connections in self._connections.items():
            for conn in connections:
                await self._close_connection(conn)

        self._connections.clear()
        self._available.clear()

        logger.info("WebSocketPool closed")

    async def connect(self, endpoint: str) -> WebSocketConnection:
        """
        Connect to a WebSocket endpoint.

        Args:
            endpoint: WebSocket URL

        Returns:
            WebSocket connection
        """
        async with self._lock:
            # Check if we have available connection
            if endpoint in self._available:
                try:
                    conn = self._available[endpoint].get_nowait()
                    if conn.state == WebSocketState.CONNECTED:
                        return conn
                except asyncio.QueueEmpty:
                    pass

            # Check connection limit
            current = len(self._connections.get(endpoint, []))
            if current >= self.config.max_connections_per_endpoint:
                raise ConnectionError(
                    f"Connection limit reached for {endpoint}"
                )

            # Create new connection
            return await self._create_connection(endpoint)

    async def _create_connection(self, endpoint: str) -> WebSocketConnection:
        """Create a new WebSocket connection."""
        try:
            import websockets

            ws = await asyncio.wait_for(
                websockets.connect(
                    endpoint,
                    ping_interval=self.config.ping_interval,
                    ping_timeout=self.config.ping_timeout,
                ),
                timeout=self.config.connection_timeout,
            )

            conn = WebSocketConnection(
                ws=ws,
                endpoint=endpoint,
                state=WebSocketState.CONNECTED,
            )

            # Track connection
            if endpoint not in self._connections:
                self._connections[endpoint] = []
                self._available[endpoint] = asyncio.Queue()

            self._connections[endpoint].append(conn)
            self._total_connections += 1

            logger.info("Connected to %s", endpoint)
            return conn

        except ImportError:
            raise RuntimeError("websockets library not installed")
        except Exception as e:
            logger.error("Failed to connect to %s: %s", endpoint, e)
            raise

    async def _close_connection(self, conn: WebSocketConnection) -> None:
        """Close a WebSocket connection."""
        try:
            if conn.ws and conn.state != WebSocketState.CLOSED:
                await conn.ws.close()
                conn.state = WebSocketState.CLOSED
        except Exception as e:
            logger.error("Error closing connection: %s", e)

    async def release(self, conn: WebSocketConnection) -> None:
        """Release a connection back to the pool."""
        if conn.state == WebSocketState.CONNECTED:
            try:
                self._available[conn.endpoint].put_nowait(conn)
            except asyncio.QueueFull:
                await self._close_connection(conn)
        else:
            await self._close_connection(conn)

    @asynccontextmanager
    async def connection(self, endpoint: str):
        """
        Context manager for WebSocket connection.

        Usage:
            async with pool.connection("ws://localhost:8080") as ws:
                await ws.send("hello")
                response = await ws.recv()
        """
        conn = await self.connect(endpoint)
        try:
            yield conn.ws
        finally:
            await self.release(conn)

    async def send(
        self,
        endpoint: str,
        message: Any,
    ) -> None:
        """
        Send a message to an endpoint.

        Args:
            endpoint: WebSocket URL
            message: Message to send
        """
        async with self.connection(endpoint) as ws:
            if isinstance(message, (dict, list)):
                import json
                message = json.dumps(message)

            await ws.send(message)
            self._total_messages += 1

    async def receive(
        self,
        endpoint: str,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Receive a message from an endpoint.

        Args:
            endpoint: WebSocket URL
            timeout: Receive timeout

        Returns:
            Received message
        """
        async with self.connection(endpoint) as ws:
            if timeout:
                message = await asyncio.wait_for(ws.recv(), timeout=timeout)
            else:
                message = await ws.recv()

            self._total_messages += 1
            return message

    def on_message(
        self,
        endpoint: str,
        handler: Callable[[Any], None],
    ) -> None:
        """
        Register a message handler for an endpoint.

        Args:
            endpoint: WebSocket URL
            handler: Message handler function
        """
        if endpoint not in self._message_handlers:
            self._message_handlers[endpoint] = []

        self._message_handlers[endpoint].append(handler)

    async def _listen(self, conn: WebSocketConnection) -> None:
        """Listen for messages on a connection."""
        try:
            async for message in conn.ws:
                conn.last_message = datetime.now()
                conn.message_count += 1
                self._total_messages += 1

                # Call handlers
                handlers = self._message_handlers.get(conn.endpoint, [])
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                    except Exception as e:
                        logger.error("Handler error: %s", e)

        except Exception as e:
            logger.error("Listen error: %s", e)
            conn.state = WebSocketState.DISCONNECTED

            # Auto reconnect
            if self.config.auto_reconnect:
                asyncio.create_task(self._reconnect(conn))

    async def _reconnect(self, conn: WebSocketConnection) -> None:
        """Reconnect a disconnected connection."""
        conn.state = WebSocketState.RECONNECTING
        delay = self.config.reconnect_delay

        for attempt in range(self.config.max_reconnect_attempts):
            try:
                await asyncio.sleep(delay)

                import websockets
                ws = await asyncio.wait_for(
                    websockets.connect(conn.endpoint),
                    timeout=self.config.connection_timeout,
                )

                conn.ws = ws
                conn.state = WebSocketState.CONNECTED
                conn.reconnect_count += 1

                logger.info(
                    "Reconnected to %s (attempt %d)",
                    conn.endpoint,
                    attempt + 1,
                )

                # Resume listening
                asyncio.create_task(self._listen(conn))
                return

            except Exception as e:
                logger.warning(
                    "Reconnect failed for %s: %s (attempt %d)",
                    conn.endpoint,
                    e,
                    attempt + 1,
                )

                # Exponential backoff
                delay = min(
                    delay * 2,
                    self.config.max_reconnect_delay,
                )

        # Give up
        conn.state = WebSocketState.CLOSED
        logger.error(
            "Failed to reconnect to %s after %d attempts",
            conn.endpoint,
            self.config.max_reconnect_attempts,
        )

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)

                for endpoint, connections in self._connections.items():
                    for conn in connections:
                        if conn.state == WebSocketState.CONNECTED:
                            try:
                                await conn.ws.ping()
                            except Exception as e:
                                logger.warning(
                                    "Heartbeat failed for %s: %s",
                                    endpoint,
                                    e,
                                )
                                conn.state = WebSocketState.DISCONNECTED

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Heartbeat error: %s", e)

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        endpoint_stats = {}

        for endpoint, connections in self._connections.items():
            connected = sum(
                1 for c in connections
                if c.state == WebSocketState.CONNECTED
            )

            endpoint_stats[endpoint] = {
                "total": len(connections),
                "connected": connected,
                "available": self._available[endpoint].qsize(),
            }

        return {
            "total_connections": self._total_connections,
            "total_messages": self._total_messages,
            "total_errors": self._total_errors,
            "endpoints": endpoint_stats,
        }
