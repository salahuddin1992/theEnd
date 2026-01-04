"""
Real-time Event Streaming System for NebulaCompute.

This module provides comprehensive event streaming capabilities including:
- WebSocket-based real-time event streaming
- Event aggregation and filtering
- Pub/Sub messaging patterns
- Event replay and persistence
- Kafka and Redis Streams integration
"""

from .brokers import (
    BrokerConfig,
    InMemoryBroker,
    KafkaBroker,
    MessageBroker,
    RedisBroker,
)
from .consumers import (
    AsyncEventConsumer,
    ConsumerConfig,
    ConsumerGroup,
    EventConsumer,
)
from .events import (
    ClusterEvent,
    Event,
    EventMetadata,
    EventPriority,
    EventType,
    JobEvent,
    MetricEvent,
    SystemEvent,
)
from .processing import (
    EventAggregator,
    EventFilter,
    EventTransformer,
    StreamProcessor,
    WindowedProcessor,
)
from .producers import (
    AsyncEventProducer,
    BatchEventProducer,
    EventProducer,
    ProducerConfig,
)
from .pubsub import (
    Publisher,
    PubSubManager,
    Subscriber,
    Subscription,
    Topic,
)
from .storage import (
    EventReplay,
    EventStore,
    FileEventStore,
    PostgresEventStore,
)
from .websocket import (
    WebSocketConfig,
    WebSocketEventClient,
    WebSocketEventServer,
)

__all__ = [
    # Events
    "Event",
    "EventType",
    "EventPriority",
    "EventMetadata",
    "SystemEvent",
    "JobEvent",
    "ClusterEvent",
    "MetricEvent",
    # Producers
    "EventProducer",
    "AsyncEventProducer",
    "BatchEventProducer",
    "ProducerConfig",
    # Consumers
    "EventConsumer",
    "AsyncEventConsumer",
    "ConsumerGroup",
    "ConsumerConfig",
    # Brokers
    "MessageBroker",
    "KafkaBroker",
    "RedisBroker",
    "InMemoryBroker",
    "BrokerConfig",
    # WebSocket
    "WebSocketEventServer",
    "WebSocketEventClient",
    "WebSocketConfig",
    # Processing
    "StreamProcessor",
    "EventAggregator",
    "EventFilter",
    "EventTransformer",
    "WindowedProcessor",
    # Storage
    "EventStore",
    "EventReplay",
    "PostgresEventStore",
    "FileEventStore",
    # PubSub
    "PubSubManager",
    "Topic",
    "Subscription",
    "Publisher",
    "Subscriber",
]
