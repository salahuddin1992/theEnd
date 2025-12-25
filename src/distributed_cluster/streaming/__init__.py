"""
Real-time Event Streaming System for NebulaCompute.

This module provides comprehensive event streaming capabilities including:
- WebSocket-based real-time event streaming
- Event aggregation and filtering
- Pub/Sub messaging patterns
- Event replay and persistence
- Kafka and Redis Streams integration
"""

from .events import (
    Event,
    EventType,
    EventPriority,
    EventMetadata,
    SystemEvent,
    JobEvent,
    ClusterEvent,
    MetricEvent,
)
from .producers import (
    EventProducer,
    AsyncEventProducer,
    BatchEventProducer,
    ProducerConfig,
)
from .consumers import (
    EventConsumer,
    AsyncEventConsumer,
    ConsumerGroup,
    ConsumerConfig,
)
from .brokers import (
    MessageBroker,
    KafkaBroker,
    RedisBroker,
    InMemoryBroker,
    BrokerConfig,
)
from .websocket import (
    WebSocketEventServer,
    WebSocketEventClient,
    WebSocketConfig,
)
from .processing import (
    StreamProcessor,
    EventAggregator,
    EventFilter,
    EventTransformer,
    WindowedProcessor,
)
from .storage import (
    EventStore,
    EventReplay,
    PostgresEventStore,
    FileEventStore,
)
from .pubsub import (
    PubSubManager,
    Topic,
    Subscription,
    Publisher,
    Subscriber,
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
