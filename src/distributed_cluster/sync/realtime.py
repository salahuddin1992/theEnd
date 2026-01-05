"""
Realtime Synchronization - المزامنة الفورية
============================================

Real-time synchronization via WebSocket:
- Instant updates across all nodes
- Pub/Sub channels
- Presence awareness
- Connection management
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """أنواع الرسائل."""

    # Sync messages
    STATE_UPDATE = "state_update"
    STATE_DELTA = "state_delta"
    STATE_REQUEST = "state_request"
    STATE_RESPONSE = "state_response"

    # Channel messages
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PUBLISH = "publish"
    BROADCAST = "broadcast"

    # Presence messages
    JOIN = "join"
    LEAVE = "leave"
    PRESENCE = "presence"

    # Control messages
    PING = "ping"
    PONG = "pong"
    ACK = "ack"
    ERROR = "error"


@dataclass
class SyncMessage:
    """رسالة مزامنة."""

    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message_type: MessageType = MessageType.STATE_UPDATE
    channel: str = "default"
    sender_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ttl_seconds: int = 0  # 0 = no expiry
    require_ack: bool = False

    def to_json(self) -> str:
        """تحويل إلى JSON."""
        return json.dumps(
            {
                "message_id": self.message_id,
                "message_type": self.message_type.value,
                "channel": self.channel,
                "sender_id": self.sender_id,
                "payload": self.payload,
                "timestamp": self.timestamp.isoformat(),
                "ttl_seconds": self.ttl_seconds,
                "require_ack": self.require_ack,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> SyncMessage:
        """إنشاء من JSON."""
        d = json.loads(data)
        return cls(
            message_id=d.get("message_id", str(uuid.uuid4())),
            message_type=MessageType(d.get("message_type", "state_update")),
            channel=d.get("channel", "default"),
            sender_id=d.get("sender_id", ""),
            payload=d.get("payload", {}),
            timestamp=datetime.fromisoformat(d["timestamp"]) if "timestamp" in d else datetime.now(timezone.utc),
            ttl_seconds=d.get("ttl_seconds", 0),
            require_ack=d.get("require_ack", False),
        )


@dataclass
class SyncChannel:
    """قناة مزامنة."""

    channel_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    subscribers: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.utcnow)
    message_count: int = 0
    last_activity: Optional[datetime] = None

    def add_subscriber(self, subscriber_id: str) -> None:
        """إضافة مشترك."""
        self.subscribers.add(subscriber_id)

    def remove_subscriber(self, subscriber_id: str) -> None:
        """إزالة مشترك."""
        self.subscribers.discard(subscriber_id)

    def has_subscriber(self, subscriber_id: str) -> bool:
        """هل يوجد مشترك؟"""
        return subscriber_id in self.subscribers


@dataclass
class Participant:
    """مشارك في المزامنة."""

    participant_id: str
    name: str = ""
    node_id: str = ""
    joined_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    channels: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    online: bool = True


class RealtimeSync:
    """
    المزامنة الفورية عبر WebSocket.

    Real-time synchronization with:
    - Instant state updates
    - Pub/Sub messaging
    - Presence awareness
    - Automatic reconnection
    """

    def __init__(self, node_id: str):
        self.node_id = node_id

        # Channels
        self._channels: Dict[str, SyncChannel] = {}
        self._default_channel = SyncChannel(name="default")
        self._channels["default"] = self._default_channel

        # Participants
        self._participants: Dict[str, Participant] = {}

        # Message handlers
        self._handlers: Dict[MessageType, List[Callable]] = {}
        self._channel_handlers: Dict[str, List[Callable]] = {}

        # Message queue
        self._outgoing_queue: asyncio.Queue = asyncio.Queue()
        self._pending_acks: Dict[str, asyncio.Future] = {}

        # State
        self._connected = False
        self._connection = None

        # Stats
        self._messages_sent = 0
        self._messages_received = 0

    # =========================================================================
    # Channel Management
    # =========================================================================

    def create_channel(self, name: str) -> SyncChannel:
        """إنشاء قناة جديدة."""
        if name in self._channels:
            return self._channels[name]

        channel = SyncChannel(name=name)
        self._channels[name] = channel
        logger.info(f"Created channel: {name}")
        return channel

    def get_channel(self, name: str) -> Optional[SyncChannel]:
        """الحصول على قناة."""
        return self._channels.get(name)

    def delete_channel(self, name: str) -> bool:
        """حذف قناة."""
        if name == "default":
            return False

        if name in self._channels:
            del self._channels[name]
            return True
        return False

    def list_channels(self) -> List[str]:
        """قائمة القنوات."""
        return list(self._channels.keys())

    # =========================================================================
    # Subscription
    # =========================================================================

    async def subscribe(
        self,
        channel_name: str,
        handler: Optional[Callable] = None,
    ) -> bool:
        """الاشتراك في قناة."""
        channel = self.get_channel(channel_name)
        if not channel:
            channel = self.create_channel(channel_name)

        channel.add_subscriber(self.node_id)

        if handler:
            if channel_name not in self._channel_handlers:
                self._channel_handlers[channel_name] = []
            self._channel_handlers[channel_name].append(handler)

        # Send subscribe message
        await self._send_message(
            SyncMessage(
                message_type=MessageType.SUBSCRIBE,
                channel=channel_name,
                sender_id=self.node_id,
            )
        )

        return True

    async def unsubscribe(self, channel_name: str) -> bool:
        """إلغاء الاشتراك."""
        channel = self.get_channel(channel_name)
        if not channel:
            return False

        channel.remove_subscriber(self.node_id)
        self._channel_handlers.pop(channel_name, None)

        await self._send_message(
            SyncMessage(
                message_type=MessageType.UNSUBSCRIBE,
                channel=channel_name,
                sender_id=self.node_id,
            )
        )

        return True

    # =========================================================================
    # Messaging
    # =========================================================================

    async def publish(
        self,
        channel_name: str,
        data: Dict[str, Any],
        require_ack: bool = False,
    ) -> Optional[str]:
        """نشر رسالة على قناة."""
        message = SyncMessage(
            message_type=MessageType.PUBLISH,
            channel=channel_name,
            sender_id=self.node_id,
            payload=data,
            require_ack=require_ack,
        )

        await self._send_message(message)

        # Update channel stats
        channel = self.get_channel(channel_name)
        if channel:
            channel.message_count += 1
            channel.last_activity = datetime.now(timezone.utc)

        # Wait for ack if required
        if require_ack:
            return await self._wait_for_ack(message.message_id)

        return message.message_id

    async def broadcast(
        self,
        data: Dict[str, Any],
        exclude_self: bool = True,
    ) -> str:
        """بث رسالة لجميع المتصلين."""
        message = SyncMessage(
            message_type=MessageType.BROADCAST,
            channel="*",
            sender_id=self.node_id,
            payload={
                **data,
                "exclude_sender": exclude_self,
            },
        )

        await self._send_message(message)
        return message.message_id

    async def send_state_update(
        self,
        key: str,
        value: Any,
        channel: str = "default",
    ) -> str:
        """إرسال تحديث حالة."""
        message = SyncMessage(
            message_type=MessageType.STATE_UPDATE,
            channel=channel,
            sender_id=self.node_id,
            payload={
                "key": key,
                "value": value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        await self._send_message(message)
        return message.message_id

    async def send_state_delta(
        self,
        deltas: List[Dict[str, Any]],
        channel: str = "default",
    ) -> str:
        """إرسال تغييرات الحالة."""
        message = SyncMessage(
            message_type=MessageType.STATE_DELTA,
            channel=channel,
            sender_id=self.node_id,
            payload={
                "deltas": deltas,
                "count": len(deltas),
            },
        )

        await self._send_message(message)
        return message.message_id

    async def request_state(
        self,
        channel: str = "default",
        since_version: int = 0,
    ) -> str:
        """طلب الحالة من العقد الأخرى."""
        message = SyncMessage(
            message_type=MessageType.STATE_REQUEST,
            channel=channel,
            sender_id=self.node_id,
            payload={
                "since_version": since_version,
            },
            require_ack=True,
        )

        await self._send_message(message)
        return message.message_id

    # =========================================================================
    # Message Handling
    # =========================================================================

    def on_message(
        self,
        message_type: MessageType,
        handler: Callable,
    ) -> None:
        """تسجيل معالج رسائل."""
        if message_type not in self._handlers:
            self._handlers[message_type] = []
        self._handlers[message_type].append(handler)

    async def handle_message(self, message: SyncMessage) -> None:
        """معالجة رسالة واردة."""
        self._messages_received += 1

        # Call type handlers
        handlers = self._handlers.get(message.message_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.error(f"Handler error: {e}")

        # Call channel handlers
        channel_handlers = self._channel_handlers.get(message.channel, [])
        for handler in channel_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.error(f"Channel handler error: {e}")

        # Send ack if required
        if message.require_ack:
            await self._send_ack(message.message_id)

        # Handle presence
        if message.message_type == MessageType.JOIN:
            await self._handle_join(message)
        elif message.message_type == MessageType.LEAVE:
            await self._handle_leave(message)
        elif message.message_type == MessageType.PING:
            await self._send_pong(message.sender_id)

    async def _send_message(self, message: SyncMessage) -> None:
        """إرسال رسالة."""
        await self._outgoing_queue.put(message)
        self._messages_sent += 1

    async def _send_ack(self, message_id: str) -> None:
        """إرسال تأكيد استلام."""
        await self._send_message(
            SyncMessage(
                message_type=MessageType.ACK,
                sender_id=self.node_id,
                payload={"message_id": message_id},
            )
        )

    async def _wait_for_ack(
        self,
        message_id: str,
        timeout: float = 10.0,
    ) -> Optional[str]:
        """انتظار تأكيد الاستلام."""
        future = asyncio.Future()
        self._pending_acks[message_id] = future

        try:
            await asyncio.wait_for(future, timeout=timeout)
            return message_id
        except asyncio.TimeoutError:
            logger.warning(f"Ack timeout for message: {message_id}")
            return None
        finally:
            self._pending_acks.pop(message_id, None)

    async def _send_pong(self, target_id: str) -> None:
        """إرسال pong."""
        await self._send_message(
            SyncMessage(
                message_type=MessageType.PONG,
                sender_id=self.node_id,
                payload={"target": target_id},
            )
        )

    # =========================================================================
    # Presence
    # =========================================================================

    async def join(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """الانضمام للمزامنة."""
        participant = Participant(
            participant_id=self.node_id,
            node_id=self.node_id,
            metadata=metadata or {},
        )
        self._participants[self.node_id] = participant

        await self._send_message(
            SyncMessage(
                message_type=MessageType.JOIN,
                sender_id=self.node_id,
                payload={
                    "participant": {
                        "id": participant.participant_id,
                        "name": participant.name,
                        "metadata": participant.metadata,
                    }
                },
            )
        )

    async def leave(self) -> None:
        """المغادرة."""
        await self._send_message(
            SyncMessage(
                message_type=MessageType.LEAVE,
                sender_id=self.node_id,
            )
        )

        self._participants.pop(self.node_id, None)

    async def _handle_join(self, message: SyncMessage) -> None:
        """معالجة انضمام مشارك."""
        participant_data = message.payload.get("participant", {})
        participant = Participant(
            participant_id=participant_data.get("id", message.sender_id),
            name=participant_data.get("name", ""),
            node_id=message.sender_id,
            metadata=participant_data.get("metadata", {}),
        )
        self._participants[message.sender_id] = participant
        logger.info(f"Participant joined: {message.sender_id}")

    async def _handle_leave(self, message: SyncMessage) -> None:
        """معالجة مغادرة مشارك."""
        if message.sender_id in self._participants:
            self._participants[message.sender_id].online = False
        logger.info(f"Participant left: {message.sender_id}")

    def get_participants(self) -> List[Participant]:
        """الحصول على قائمة المشاركين."""
        return list(self._participants.values())

    def get_online_participants(self) -> List[Participant]:
        """الحصول على المشاركين المتصلين."""
        return [p for p in self._participants.values() if p.online]

    # =========================================================================
    # Connection Management
    # =========================================================================

    async def get_outgoing_messages(self) -> asyncio.Queue:
        """الحصول على قائمة الرسائل الصادرة."""
        return self._outgoing_queue

    async def process_incoming(self, data: str) -> None:
        """معالجة بيانات واردة."""
        try:
            message = SyncMessage.from_json(data)
            await self.handle_message(message)

            # Handle acks
            if message.message_type == MessageType.ACK:
                ack_message_id = message.payload.get("message_id")
                if ack_message_id in self._pending_acks:
                    self._pending_acks[ack_message_id].set_result(True)

        except Exception as e:
            logger.error(f"Failed to process message: {e}")

    # =========================================================================
    # Status & Stats
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات."""
        return {
            "node_id": self.node_id,
            "channels": len(self._channels),
            "participants": len(self._participants),
            "online_participants": len(self.get_online_participants()),
            "messages_sent": self._messages_sent,
            "messages_received": self._messages_received,
            "pending_queue": self._outgoing_queue.qsize(),
            "pending_acks": len(self._pending_acks),
        }


# ============================================================================
# WebSocket Integration Helper
# ============================================================================


class WebSocketSyncAdapter:
    """
    محول WebSocket للمزامنة الفورية.

    Integrates RealtimeSync with WebSocket connections.
    """

    def __init__(self, realtime: RealtimeSync):
        self.realtime = realtime
        self._connections: Dict[str, Any] = {}  # WebSocket connections
        self._running = False

    async def start(self) -> None:
        """بدء المحول."""
        self._running = True
        asyncio.create_task(self._process_outgoing())

    async def stop(self) -> None:
        """إيقاف المحول."""
        self._running = False

    def add_connection(self, conn_id: str, websocket: Any) -> None:
        """إضافة اتصال."""
        self._connections[conn_id] = websocket

    def remove_connection(self, conn_id: str) -> None:
        """إزالة اتصال."""
        self._connections.pop(conn_id, None)

    async def _process_outgoing(self) -> None:
        """معالجة الرسائل الصادرة."""
        queue = await self.realtime.get_outgoing_messages()

        while self._running:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=1.0)
                await self._broadcast_to_connections(message.to_json())
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Outgoing process error: {e}")

    async def _broadcast_to_connections(self, data: str) -> None:
        """بث لجميع الاتصالات."""
        for conn_id, websocket in list(self._connections.items()):
            try:
                await websocket.send(data)
            except Exception as e:
                logger.warning(f"Failed to send to {conn_id}: {e}")
                self.remove_connection(conn_id)

    async def handle_incoming(self, conn_id: str, data: str) -> None:
        """معالجة رسالة واردة."""
        await self.realtime.process_incoming(data)
