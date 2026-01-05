"""
Pub/Sub messaging patterns for event streaming.
"""

import asyncio
import logging
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from .events import Event, EventType

logger = logging.getLogger(__name__)


class DeliveryMode(Enum):
    """Message delivery modes."""
    AT_MOST_ONCE = "at_most_once"  # Fire and forget
    AT_LEAST_ONCE = "at_least_once"  # Acknowledge required
    EXACTLY_ONCE = "exactly_once"  # Deduplication


class SubscriptionType(Enum):
    """Types of subscriptions."""
    EXCLUSIVE = "exclusive"  # Only one subscriber receives each message
    SHARED = "shared"  # Multiple subscribers share messages
    FAILOVER = "failover"  # Backup subscribers
    KEY_SHARED = "key_shared"  # Partition by key


@dataclass
class TopicConfig:
    """Configuration for a topic."""
    name: str
    partitions: int = 1
    retention_hours: int = 24
    max_message_size: int = 1048576  # 1MB
    delivery_mode: DeliveryMode = DeliveryMode.AT_LEAST_ONCE
    enable_deduplication: bool = False
    deduplication_window_ms: int = 60000


@dataclass
class SubscriptionConfig:
    """Configuration for a subscription."""
    name: str
    topic: str
    subscription_type: SubscriptionType = SubscriptionType.SHARED
    ack_timeout_ms: int = 30000
    max_redeliveries: int = 3
    dead_letter_topic: Optional[str] = None
    filter_expression: Optional[str] = None
    initial_position: str = "latest"  # earliest, latest


@dataclass
class Message:
    """A message in the pub/sub system."""
    message_id: str
    topic: str
    payload: Dict[str, Any]
    key: Optional[str] = None
    properties: Dict[str, str] = field(default_factory=dict)
    publish_time: datetime = field(default_factory=datetime.utcnow)
    event_time: Optional[datetime] = None
    sequence_id: Optional[int] = None
    redelivery_count: int = 0

    def to_event(self) -> Event:
        """Convert message to Event."""
        return Event(
            event_id=self.message_id,
            event_type=EventType.CUSTOM,
            payload=self.payload,
            timestamp=self.event_time or self.publish_time,
        )

    @classmethod
    def from_event(cls, event: Event, topic: str, key: Optional[str] = None) -> "Message":
        """Create message from Event."""
        return cls(
            message_id=event.event_id,
            topic=topic,
            payload=event.payload,
            key=key,
            event_time=event.timestamp,
        )


@dataclass
class Topic:
    """Represents a topic in the pub/sub system."""
    config: TopicConfig
    subscriptions: Dict[str, "Subscription"] = field(default_factory=dict)
    partitions: Dict[int, List[Message]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    message_count: int = 0

    def __post_init__(self):
        # Initialize partitions
        for i in range(self.config.partitions):
            if i not in self.partitions:
                self.partitions[i] = []

    def get_partition(self, key: Optional[str]) -> int:
        """Get partition for a message key."""
        if key:
            return hash(key) % self.config.partitions
        return hash(str(time.time())) % self.config.partitions


@dataclass
class Subscription:
    """Represents a subscription to a topic."""
    config: SubscriptionConfig
    topic: "Topic" = None
    subscribers: List["Subscriber"] = field(default_factory=list)
    pending_acks: Dict[str, tuple] = field(default_factory=dict)  # message_id -> (message, subscriber, timestamp)
    cursor_positions: Dict[int, int] = field(default_factory=dict)  # partition -> position
    created_at: datetime = field(default_factory=datetime.utcnow)
    messages_delivered: int = 0
    messages_acked: int = 0

    @property
    def active_subscribers(self) -> List["Subscriber"]:
        return [s for s in self.subscribers if s.is_active]


class Publisher:
    """Publisher for sending messages to topics."""

    def __init__(self, manager: "PubSubManager"):
        self.manager = manager
        self._producer_name = f"producer-{uuid.uuid4().hex[:8]}"
        self._sequence_counters: Dict[str, int] = defaultdict(int)
        self._pending_messages: Dict[str, Message] = {}
        self._lock = threading.Lock()

    def publish(
        self,
        topic: str,
        payload: Dict[str, Any],
        key: Optional[str] = None,
        properties: Optional[Dict[str, str]] = None,
        event_time: Optional[datetime] = None
    ) -> str:
        """Publish a message to a topic."""
        with self._lock:
            message_id = str(uuid.uuid4())
            sequence_id = self._sequence_counters[topic]
            self._sequence_counters[topic] += 1

            message = Message(
                message_id=message_id,
                topic=topic,
                payload=payload,
                key=key,
                properties=properties or {},
                event_time=event_time,
                sequence_id=sequence_id,
            )

            success = self.manager._publish_message(message)
            if success:
                return message_id
            else:
                raise RuntimeError(f"Failed to publish message to topic {topic}")

    def publish_event(
        self,
        topic: str,
        event: Event,
        key: Optional[str] = None
    ) -> str:
        """Publish an event as a message."""
        return self.publish(
            topic=topic,
            payload=event.payload,
            key=key,
            properties={
                "event_type": event.event_type.name,
                "priority": event.priority.name,
            },
            event_time=event.timestamp,
        )

    async def publish_async(
        self,
        topic: str,
        payload: Dict[str, Any],
        key: Optional[str] = None,
        **kwargs
    ) -> str:
        """Async publish."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.publish(topic, payload, key, **kwargs)
        )


class Subscriber:
    """Subscriber for receiving messages from topics."""

    def __init__(
        self,
        subscription: Subscription,
        handler: Callable[[Message], bool],
        manager: "PubSubManager"
    ):
        self.subscription = subscription
        self.handler = handler
        self.manager = manager
        self.subscriber_id = str(uuid.uuid4())
        self._active = False
        self._receive_task: Optional[asyncio.Task] = None
        self._messages_received = 0
        self._messages_processed = 0

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self):
        """Start receiving messages."""
        self._active = True
        self.subscription.subscribers.append(self)
        logger.info(f"Subscriber {self.subscriber_id} started on {self.subscription.config.name}")

    async def start_async(self):
        """Start async message receiving."""
        self._active = True
        self.subscription.subscribers.append(self)
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self):
        """Background task to receive messages."""
        while self._active:
            try:
                message = self.manager._get_next_message(self.subscription, self)
                if message:
                    await self._process_message(message)
                else:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")
                await asyncio.sleep(1)

    async def _process_message(self, message: Message):
        """Process a received message."""
        self._messages_received += 1

        try:
            if asyncio.iscoroutinefunction(self.handler):
                success = await self.handler(message)
            else:
                success = self.handler(message)

            if success:
                self.acknowledge(message.message_id)
                self._messages_processed += 1
            else:
                self.negative_acknowledge(message.message_id)

        except Exception as e:
            logger.error(f"Error processing message {message.message_id}: {e}")
            self.negative_acknowledge(message.message_id)

    def acknowledge(self, message_id: str):
        """Acknowledge a message."""
        self.manager._acknowledge_message(self.subscription, message_id)

    def negative_acknowledge(self, message_id: str):
        """Negative acknowledge (request redelivery)."""
        self.manager._negative_acknowledge_message(self.subscription, message_id)

    def stop(self):
        """Stop receiving messages."""
        self._active = False
        if self in self.subscription.subscribers:
            self.subscription.subscribers.remove(self)
        logger.info(f"Subscriber {self.subscriber_id} stopped")

    async def stop_async(self):
        """Async stop."""
        self._active = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        self.stop()

    @property
    def messages_received(self) -> int:
        return self._messages_received

    @property
    def messages_processed(self) -> int:
        return self._messages_processed


class PubSubManager:
    """Central manager for the pub/sub system."""

    def __init__(self):
        self._topics: Dict[str, Topic] = {}
        self._subscriptions: Dict[str, Subscription] = {}
        self._publishers: List[Publisher] = []
        self._dedup_cache: Dict[str, Set[str]] = defaultdict(set)  # topic -> set of message_ids
        self._lock = threading.RLock()
        self._running = True
        self._cleanup_thread: Optional[threading.Thread] = None

        # Start cleanup thread
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """Start background cleanup thread."""
        def cleanup_loop():
            while self._running:
                time.sleep(60)  # Check every minute
                self._cleanup_expired_messages()
                self._cleanup_dedup_cache()
                self._check_ack_timeouts()

        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def create_topic(self, config: TopicConfig) -> Topic:
        """Create a new topic."""
        with self._lock:
            if config.name in self._topics:
                raise ValueError(f"Topic {config.name} already exists")

            topic = Topic(config=config)
            self._topics[config.name] = topic
            logger.info(f"Created topic: {config.name}")
            return topic

    def delete_topic(self, topic_name: str) -> bool:
        """Delete a topic."""
        with self._lock:
            if topic_name not in self._topics:
                return False

            topic = self._topics[topic_name]

            # Remove all subscriptions
            for sub_name in list(topic.subscriptions.keys()):
                self.delete_subscription(sub_name)

            del self._topics[topic_name]
            logger.info(f"Deleted topic: {topic_name}")
            return True

    def get_topic(self, topic_name: str) -> Optional[Topic]:
        """Get a topic by name."""
        return self._topics.get(topic_name)

    def list_topics(self) -> List[str]:
        """List all topic names."""
        return list(self._topics.keys())

    def create_subscription(self, config: SubscriptionConfig) -> Subscription:
        """Create a new subscription."""
        with self._lock:
            if config.name in self._subscriptions:
                raise ValueError(f"Subscription {config.name} already exists")

            topic = self._topics.get(config.topic)
            if not topic:
                raise ValueError(f"Topic {config.topic} does not exist")

            subscription = Subscription(config=config, topic=topic)

            # Initialize cursor positions
            for partition in range(topic.config.partitions):
                if config.initial_position == "earliest":
                    subscription.cursor_positions[partition] = 0
                else:  # latest
                    subscription.cursor_positions[partition] = len(topic.partitions[partition])

            self._subscriptions[config.name] = subscription
            topic.subscriptions[config.name] = subscription

            logger.info(f"Created subscription: {config.name} on topic {config.topic}")
            return subscription

    def delete_subscription(self, subscription_name: str) -> bool:
        """Delete a subscription."""
        with self._lock:
            if subscription_name not in self._subscriptions:
                return False

            subscription = self._subscriptions[subscription_name]

            # Stop all subscribers
            for subscriber in list(subscription.subscribers):
                subscriber.stop()

            # Remove from topic
            if subscription.topic:
                subscription.topic.subscriptions.pop(subscription_name, None)

            del self._subscriptions[subscription_name]
            logger.info(f"Deleted subscription: {subscription_name}")
            return True

    def get_subscription(self, subscription_name: str) -> Optional[Subscription]:
        """Get a subscription by name."""
        return self._subscriptions.get(subscription_name)

    def create_publisher(self) -> Publisher:
        """Create a new publisher."""
        publisher = Publisher(self)
        self._publishers.append(publisher)
        return publisher

    def create_subscriber(
        self,
        subscription_name: str,
        handler: Callable[[Message], bool]
    ) -> Subscriber:
        """Create a new subscriber."""
        subscription = self._subscriptions.get(subscription_name)
        if not subscription:
            raise ValueError(f"Subscription {subscription_name} does not exist")

        subscriber = Subscriber(subscription, handler, self)
        return subscriber

    def _publish_message(self, message: Message) -> bool:
        """Internal method to publish a message."""
        with self._lock:
            topic = self._topics.get(message.topic)
            if not topic:
                # Auto-create topic
                topic = self.create_topic(TopicConfig(name=message.topic))

            # Check deduplication
            if topic.config.enable_deduplication:
                if message.message_id in self._dedup_cache[message.topic]:
                    logger.debug(f"Duplicate message {message.message_id} ignored")
                    return True
                self._dedup_cache[message.topic].add(message.message_id)

            # Get partition
            partition = topic.get_partition(message.key)

            # Add to partition
            topic.partitions[partition].append(message)
            topic.message_count += 1

            logger.debug(f"Published message {message.message_id} to {message.topic}[{partition}]")
            return True

    def _get_next_message(
        self,
        subscription: Subscription,
        subscriber: Subscriber
    ) -> Optional[Message]:
        """Get the next message for a subscriber."""
        with self._lock:
            topic = subscription.topic
            if not topic:
                return None

            # Round-robin across partitions
            for partition in range(topic.config.partitions):
                position = subscription.cursor_positions.get(partition, 0)
                messages = topic.partitions.get(partition, [])

                if position < len(messages):
                    message = messages[position]

                    # Check filter if configured
                    if subscription.config.filter_expression:
                        if not self._matches_filter(message, subscription.config.filter_expression):
                            subscription.cursor_positions[partition] = position + 1
                            continue

                    # Handle subscription type
                    if subscription.config.subscription_type == SubscriptionType.EXCLUSIVE:
                        # Only first subscriber gets messages
                        if subscription.subscribers and subscription.subscribers[0] != subscriber:
                            continue

                    elif subscription.config.subscription_type == SubscriptionType.KEY_SHARED:
                        # Partition by key
                        if message.key:
                            subscriber_index = hash(message.key) % len(subscription.active_subscribers)
                            if subscription.active_subscribers[subscriber_index] != subscriber:
                                continue

                    # Track pending ack
                    if topic.config.delivery_mode != DeliveryMode.AT_MOST_ONCE:
                        subscription.pending_acks[message.message_id] = (
                            message,
                            subscriber,
                            datetime.now(timezone.utc)
                        )

                    subscription.cursor_positions[partition] = position + 1
                    subscription.messages_delivered += 1

                    return message

            return None

    def _acknowledge_message(self, subscription: Subscription, message_id: str):
        """Acknowledge a message."""
        with self._lock:
            if message_id in subscription.pending_acks:
                del subscription.pending_acks[message_id]
                subscription.messages_acked += 1

    def _negative_acknowledge_message(self, subscription: Subscription, message_id: str):
        """Handle negative acknowledgment."""
        with self._lock:
            if message_id not in subscription.pending_acks:
                return

            message, subscriber, timestamp = subscription.pending_acks[message_id]
            del subscription.pending_acks[message_id]

            message.redelivery_count += 1

            # Check max redeliveries
            if message.redelivery_count >= subscription.config.max_redeliveries:
                if subscription.config.dead_letter_topic:
                    # Send to dead letter topic
                    self._publish_message(Message(
                        message_id=str(uuid.uuid4()),
                        topic=subscription.config.dead_letter_topic,
                        payload=message.payload,
                        properties={
                            **message.properties,
                            "original_topic": message.topic,
                            "original_message_id": message.message_id,
                            "redelivery_count": str(message.redelivery_count),
                        }
                    ))
                logger.warning(f"Message {message_id} exceeded max redeliveries")
            else:
                # Re-add to topic for redelivery
                topic = subscription.topic
                partition = topic.get_partition(message.key)
                topic.partitions[partition].append(message)

    def _matches_filter(self, message: Message, expression: str) -> bool:
        """Check if a message matches a filter expression."""
        # Simple key=value filter implementation
        try:
            for part in expression.split(" AND "):
                part = part.strip()
                if "=" in part:
                    key, value = part.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'\"")

                    if key.startswith("properties."):
                        prop_key = key.replace("properties.", "")
                        if message.properties.get(prop_key) != value:
                            return False
                    elif key.startswith("payload."):
                        payload_key = key.replace("payload.", "")
                        if str(message.payload.get(payload_key)) != value:
                            return False
            return True
        except Exception:
            # On filter evaluation error, reject the message for safety
            return False

    def _cleanup_expired_messages(self):
        """Remove expired messages from topics."""
        with self._lock:
            for topic in self._topics.values():
                retention = timedelta(hours=topic.config.retention_hours)
                cutoff = datetime.now(timezone.utc) - retention

                for partition in topic.partitions.values():
                    while partition and partition[0].publish_time < cutoff:
                        partition.pop(0)

    def _cleanup_dedup_cache(self):
        """Clean up old entries from deduplication cache."""
        with self._lock:
            # Simple cleanup - clear cache for topics with deduplication
            for topic_name, topic in self._topics.items():
                if topic.config.enable_deduplication:
                    if len(self._dedup_cache[topic_name]) > 100000:
                        # Clear if too large
                        self._dedup_cache[topic_name].clear()

    def _check_ack_timeouts(self):
        """Check for acknowledgment timeouts and redeliver."""
        with self._lock:
            now = datetime.now(timezone.utc)

            for subscription in self._subscriptions.values():
                timeout = timedelta(milliseconds=subscription.config.ack_timeout_ms)

                for message_id, (message, subscriber, timestamp) in list(subscription.pending_acks.items()):
                    if now - timestamp > timeout:
                        logger.warning(f"Ack timeout for message {message_id}")
                        self._negative_acknowledge_message(subscription, message_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics."""
        with self._lock:
            return {
                "topics": len(self._topics),
                "subscriptions": len(self._subscriptions),
                "publishers": len(self._publishers),
                "topic_stats": {
                    name: {
                        "message_count": topic.message_count,
                        "subscriptions": len(topic.subscriptions),
                        "partitions": topic.config.partitions,
                    }
                    for name, topic in self._topics.items()
                },
                "subscription_stats": {
                    name: {
                        "messages_delivered": sub.messages_delivered,
                        "messages_acked": sub.messages_acked,
                        "pending_acks": len(sub.pending_acks),
                        "subscribers": len(sub.subscribers),
                    }
                    for name, sub in self._subscriptions.items()
                },
            }

    def shutdown(self):
        """Shutdown the pub/sub manager."""
        self._running = False

        # Stop all subscribers
        for subscription in self._subscriptions.values():
            for subscriber in list(subscription.subscribers):
                subscriber.stop()

        logger.info("PubSubManager shutdown complete")
