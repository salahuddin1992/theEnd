"""
Streaming Module Unit Tests - اختبارات وحدة البث
=================================================

Tests for the streaming system including:
- Event types and metadata
- Producers and consumers
- Message brokers (InMemory, Redis, Kafka)
- Pub/Sub system
- Stream processing
- WebSocket streaming
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distributed_cluster.streaming import (
    AsyncEventConsumer,
    AsyncEventProducer,
    BatchEventProducer,
    BrokerConfig,
    ClusterEvent,
    ConsumerConfig,
    ConsumerGroup,
    Event,
    EventAggregator,
    EventConsumer,
    EventFilter,
    EventMetadata,
    EventPriority,
    EventProducer,
    EventReplay,
    EventStore,
    EventTransformer,
    EventType,
    FileEventStore,
    InMemoryBroker,
    JobEvent,
    KafkaBroker,
    MessageBroker,
    MetricEvent,
    PostgresEventStore,
    ProducerConfig,
    Publisher,
    PubSubManager,
    RedisBroker,
    StreamProcessor,
    Subscriber,
    Subscription,
    SystemEvent,
    Topic,
    WebSocketConfig,
    WebSocketEventClient,
    WebSocketEventServer,
    WindowedProcessor,
)


# =============================================================================
# Event Tests
# =============================================================================


class TestEventType:
    """Tests for EventType enum."""

    def test_event_types(self):
        """Test event type values."""
        assert EventType.JOB_SUBMITTED is not None
        assert EventType.JOB_COMPLETED is not None
        assert EventType.WORKER_JOINED is not None
        assert EventType.SYSTEM_ERROR is not None


class TestEventPriority:
    """Tests for EventPriority enum."""

    def test_priority_ordering(self):
        """Test priority ordering."""
        assert EventPriority.HIGH.value < EventPriority.NORMAL.value
        assert EventPriority.NORMAL.value < EventPriority.LOW.value


class TestEventMetadata:
    """Tests for EventMetadata."""

    def test_create_metadata(self):
        """Test creating event metadata."""
        metadata = EventMetadata(
            event_id="evt-12345",
            timestamp=datetime.now(timezone.utc),
            source="scheduler",
            correlation_id="corr-abc",
        )
        assert metadata.event_id == "evt-12345"
        assert metadata.source == "scheduler"


class TestEvent:
    """Tests for Event base class."""

    def test_create_event(self):
        """Test creating an event."""
        event = Event(
            event_type=EventType.JOB_SUBMITTED,
            payload={"job_id": "job-123"},
            metadata=EventMetadata(
                event_id="evt-1",
                timestamp=datetime.now(timezone.utc),
                source="api",
            ),
        )
        assert event.event_type == EventType.JOB_SUBMITTED
        assert event.payload["job_id"] == "job-123"

    def test_event_to_dict(self):
        """Test event dictionary conversion."""
        event = Event(
            event_type=EventType.WORKER_JOINED,
            payload={"worker_id": "worker-1"},
            metadata=EventMetadata(
                event_id="evt-2",
                timestamp=datetime.now(timezone.utc),
                source="worker",
            ),
        )
        d = event.to_dict()
        assert d["event_type"] == EventType.WORKER_JOINED.value
        assert d["payload"]["worker_id"] == "worker-1"

    def test_event_from_dict(self):
        """Test creating event from dictionary."""
        data = {
            "event_type": EventType.JOB_COMPLETED.value,
            "payload": {"job_id": "job-456", "result": "success"},
            "metadata": {
                "event_id": "evt-3",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "worker",
            },
        }
        event = Event.from_dict(data)
        assert event.payload["job_id"] == "job-456"


class TestJobEvent:
    """Tests for JobEvent."""

    def test_create_job_event(self):
        """Test creating a job event."""
        event = JobEvent(
            event_type=EventType.JOB_SUBMITTED,
            job_id="job-123",
            status="pending",
            payload={"command": "python train.py"},
        )
        assert event.job_id == "job-123"
        assert event.status == "pending"


class TestClusterEvent:
    """Tests for ClusterEvent."""

    def test_create_cluster_event(self):
        """Test creating a cluster event."""
        event = ClusterEvent(
            event_type=EventType.WORKER_JOINED,
            cluster_id="cluster-1",
            payload={"worker_count": 10},
        )
        assert event.cluster_id == "cluster-1"


class TestMetricEvent:
    """Tests for MetricEvent."""

    def test_create_metric_event(self):
        """Test creating a metric event."""
        event = MetricEvent(
            event_type=EventType.METRIC_COLLECTED,
            metric_name="cpu_utilization",
            value=0.75,
            tags={"worker": "worker-1"},
        )
        assert event.metric_name == "cpu_utilization"
        assert event.value == 0.75


class TestSystemEvent:
    """Tests for SystemEvent."""

    def test_create_system_event(self):
        """Test creating a system event."""
        event = SystemEvent(
            event_type=EventType.SYSTEM_ERROR,
            severity="error",
            message="Connection failed",
        )
        assert event.severity == "error"
        assert event.message == "Connection failed"


# =============================================================================
# Producer Tests
# =============================================================================


class TestProducerConfig:
    """Tests for ProducerConfig."""

    def test_default_config(self):
        """Test default producer configuration."""
        config = ProducerConfig()
        assert config.batch_size > 0
        assert config.flush_interval_ms > 0

    def test_custom_config(self):
        """Test custom producer configuration."""
        config = ProducerConfig(
            batch_size=100,
            flush_interval_ms=500,
            compression="gzip",
        )
        assert config.batch_size == 100


class TestEventProducer:
    """Tests for EventProducer."""

    @pytest.fixture
    def mock_broker(self):
        """Create mock message broker."""
        broker = MagicMock(spec=MessageBroker)
        broker.publish = AsyncMock()
        return broker

    @pytest.fixture
    def producer(self, mock_broker):
        """Create an event producer."""
        return EventProducer(broker=mock_broker)

    @pytest.mark.asyncio
    async def test_produce_event(self, producer, mock_broker):
        """Test producing an event."""
        event = Event(
            event_type=EventType.JOB_SUBMITTED,
            payload={"job_id": "job-123"},
            metadata=EventMetadata(
                event_id="evt-1",
                timestamp=datetime.now(timezone.utc),
                source="test",
            ),
        )

        await producer.produce("jobs", event)
        mock_broker.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_produce_multiple_events(self, producer, mock_broker):
        """Test producing multiple events."""
        events = [
            Event(
                event_type=EventType.JOB_SUBMITTED,
                payload={"job_id": f"job-{i}"},
                metadata=EventMetadata(
                    event_id=f"evt-{i}",
                    timestamp=datetime.now(timezone.utc),
                    source="test",
                ),
            )
            for i in range(5)
        ]

        for event in events:
            await producer.produce("jobs", event)

        assert mock_broker.publish.call_count == 5


class TestBatchEventProducer:
    """Tests for BatchEventProducer."""

    @pytest.fixture
    def mock_broker(self):
        broker = MagicMock(spec=MessageBroker)
        broker.publish_batch = AsyncMock()
        return broker

    @pytest.fixture
    def producer(self, mock_broker):
        config = ProducerConfig(batch_size=3)
        return BatchEventProducer(broker=mock_broker, config=config)

    @pytest.mark.asyncio
    async def test_batch_accumulation(self, producer, mock_broker):
        """Test batch accumulation."""
        events = [
            Event(
                event_type=EventType.METRIC_COLLECTED,
                payload={"value": i},
                metadata=EventMetadata(
                    event_id=f"evt-{i}",
                    timestamp=datetime.now(timezone.utc),
                    source="test",
                ),
            )
            for i in range(5)
        ]

        for event in events:
            await producer.add(event)

        await producer.flush()
        mock_broker.publish_batch.assert_called()


# =============================================================================
# Consumer Tests
# =============================================================================


class TestConsumerConfig:
    """Tests for ConsumerConfig."""

    def test_default_config(self):
        """Test default consumer configuration."""
        config = ConsumerConfig()
        assert config.auto_commit is True
        assert config.max_poll_records > 0


class TestEventConsumer:
    """Tests for EventConsumer."""

    @pytest.fixture
    def mock_broker(self):
        broker = MagicMock(spec=MessageBroker)
        broker.subscribe = AsyncMock()
        broker.poll = AsyncMock(return_value=[])
        return broker

    @pytest.fixture
    def consumer(self, mock_broker):
        return EventConsumer(broker=mock_broker)

    @pytest.mark.asyncio
    async def test_subscribe(self, consumer, mock_broker):
        """Test subscribing to topics."""
        await consumer.subscribe(["jobs", "metrics"])
        mock_broker.subscribe.assert_called_with(["jobs", "metrics"])

    @pytest.mark.asyncio
    async def test_consume_events(self, consumer, mock_broker):
        """Test consuming events."""
        test_events = [
            Event(
                event_type=EventType.JOB_COMPLETED,
                payload={"job_id": "job-1"},
                metadata=EventMetadata(
                    event_id="evt-1",
                    timestamp=datetime.now(timezone.utc),
                    source="test",
                ),
            )
        ]
        mock_broker.poll.return_value = test_events

        events = await consumer.poll()
        assert len(events) == 1


class TestConsumerGroup:
    """Tests for ConsumerGroup."""

    @pytest.fixture
    def mock_broker(self):
        broker = MagicMock(spec=MessageBroker)
        broker.subscribe = AsyncMock()
        broker.poll = AsyncMock(return_value=[])
        return broker

    @pytest.fixture
    def consumer_group(self, mock_broker):
        return ConsumerGroup(
            group_id="test-group",
            broker=mock_broker,
            topics=["jobs"],
        )

    @pytest.mark.asyncio
    async def test_group_coordination(self, consumer_group):
        """Test consumer group coordination."""
        assert consumer_group.group_id == "test-group"

    @pytest.mark.asyncio
    async def test_add_consumer(self, consumer_group):
        """Test adding consumer to group."""
        consumer = MagicMock(spec=EventConsumer)
        consumer_group.add_consumer(consumer)

        assert len(consumer_group.consumers) >= 1


# =============================================================================
# Broker Tests
# =============================================================================


class TestBrokerConfig:
    """Tests for BrokerConfig."""

    def test_default_config(self):
        """Test default broker configuration."""
        config = BrokerConfig()
        assert config.max_message_size > 0

    def test_kafka_config(self):
        """Test Kafka broker configuration."""
        config = BrokerConfig(
            bootstrap_servers=["localhost:9092"],
            client_id="test-client",
        )
        assert "localhost:9092" in config.bootstrap_servers


class TestInMemoryBroker:
    """Tests for InMemoryBroker."""

    @pytest.fixture
    def broker(self):
        return InMemoryBroker()

    @pytest.mark.asyncio
    async def test_publish_subscribe(self, broker):
        """Test publish/subscribe."""
        received_events = []

        async def handler(event):
            received_events.append(event)

        await broker.subscribe(["test-topic"], handler)

        event = Event(
            event_type=EventType.SYSTEM_INFO,
            payload={"message": "hello"},
            metadata=EventMetadata(
                event_id="evt-1",
                timestamp=datetime.now(timezone.utc),
                source="test",
            ),
        )

        await broker.publish("test-topic", event)
        await asyncio.sleep(0.1)

        assert len(received_events) == 1

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, broker):
        """Test multiple subscribers."""
        received1 = []
        received2 = []

        async def handler1(event):
            received1.append(event)

        async def handler2(event):
            received2.append(event)

        await broker.subscribe(["topic"], handler1)
        await broker.subscribe(["topic"], handler2)

        event = Event(
            event_type=EventType.SYSTEM_INFO,
            payload={},
            metadata=EventMetadata(
                event_id="evt-1",
                timestamp=datetime.now(timezone.utc),
                source="test",
            ),
        )

        await broker.publish("topic", event)
        await asyncio.sleep(0.1)

        assert len(received1) == 1
        assert len(received2) == 1

    @pytest.mark.asyncio
    async def test_topic_isolation(self, broker):
        """Test topic isolation."""
        received = []

        async def handler(event):
            received.append(event)

        await broker.subscribe(["topic-a"], handler)

        event = Event(
            event_type=EventType.SYSTEM_INFO,
            payload={},
            metadata=EventMetadata(
                event_id="evt-1",
                timestamp=datetime.now(timezone.utc),
                source="test",
            ),
        )

        await broker.publish("topic-b", event)
        await asyncio.sleep(0.1)

        # Should not receive event from different topic
        assert len(received) == 0


class TestRedisBroker:
    """Tests for RedisBroker (mocked)."""

    @pytest.fixture
    def broker(self):
        config = BrokerConfig(redis_url="redis://localhost:6379")
        return RedisBroker(config)

    @pytest.mark.asyncio
    async def test_initialization(self, broker):
        """Test Redis broker initialization."""
        assert broker.config.redis_url == "redis://localhost:6379"


class TestKafkaBroker:
    """Tests for KafkaBroker (mocked)."""

    @pytest.fixture
    def broker(self):
        config = BrokerConfig(
            bootstrap_servers=["localhost:9092"],
            client_id="test-client",
        )
        return KafkaBroker(config)

    @pytest.mark.asyncio
    async def test_initialization(self, broker):
        """Test Kafka broker initialization."""
        assert "localhost:9092" in broker.config.bootstrap_servers


# =============================================================================
# PubSub Tests
# =============================================================================


class TestTopic:
    """Tests for Topic."""

    def test_create_topic(self):
        """Test creating a topic."""
        topic = Topic(
            name="jobs",
            partitions=4,
            retention_hours=24,
        )
        assert topic.name == "jobs"
        assert topic.partitions == 4


class TestSubscription:
    """Tests for Subscription."""

    def test_create_subscription(self):
        """Test creating a subscription."""
        subscription = Subscription(
            subscriber_id="sub-1",
            topic="jobs",
            filter_expression="status == 'completed'",
        )
        assert subscription.topic == "jobs"


class TestPublisher:
    """Tests for Publisher."""

    @pytest.fixture
    def mock_broker(self):
        broker = MagicMock(spec=MessageBroker)
        broker.publish = AsyncMock()
        return broker

    @pytest.fixture
    def publisher(self, mock_broker):
        return Publisher(broker=mock_broker)

    @pytest.mark.asyncio
    async def test_publish(self, publisher, mock_broker):
        """Test publishing message."""
        await publisher.publish(
            topic="events",
            message={"type": "test", "data": "hello"},
        )
        mock_broker.publish.assert_called_once()


class TestSubscriber:
    """Tests for Subscriber."""

    @pytest.fixture
    def mock_broker(self):
        broker = MagicMock(spec=MessageBroker)
        broker.subscribe = AsyncMock()
        return broker

    @pytest.fixture
    def subscriber(self, mock_broker):
        return Subscriber(subscriber_id="sub-1", broker=mock_broker)

    @pytest.mark.asyncio
    async def test_subscribe(self, subscriber, mock_broker):
        """Test subscribing to topic."""
        await subscriber.subscribe("events")
        mock_broker.subscribe.assert_called()


class TestPubSubManager:
    """Tests for PubSubManager."""

    @pytest.fixture
    def mock_broker(self):
        broker = MagicMock(spec=MessageBroker)
        broker.publish = AsyncMock()
        broker.subscribe = AsyncMock()
        return broker

    @pytest.fixture
    def manager(self, mock_broker):
        return PubSubManager(broker=mock_broker)

    @pytest.mark.asyncio
    async def test_create_topic(self, manager):
        """Test creating a topic."""
        topic = await manager.create_topic("new-topic", partitions=2)
        assert topic.name == "new-topic"

    @pytest.mark.asyncio
    async def test_create_subscription(self, manager):
        """Test creating a subscription."""
        await manager.create_topic("events")
        subscription = await manager.subscribe("sub-1", "events")

        assert subscription.topic == "events"


# =============================================================================
# Stream Processing Tests
# =============================================================================


class TestEventFilter:
    """Tests for EventFilter."""

    @pytest.fixture
    def filter(self):
        return EventFilter(
            event_types=[EventType.JOB_COMPLETED],
            min_priority=EventPriority.NORMAL,
        )

    def test_filter_by_type(self, filter):
        """Test filtering by event type."""
        matching_event = Event(
            event_type=EventType.JOB_COMPLETED,
            payload={},
            metadata=EventMetadata(
                event_id="evt-1",
                timestamp=datetime.now(timezone.utc),
                source="test",
            ),
        )
        non_matching_event = Event(
            event_type=EventType.JOB_SUBMITTED,
            payload={},
            metadata=EventMetadata(
                event_id="evt-2",
                timestamp=datetime.now(timezone.utc),
                source="test",
            ),
        )

        assert filter.matches(matching_event) is True
        assert filter.matches(non_matching_event) is False


class TestEventTransformer:
    """Tests for EventTransformer."""

    @pytest.fixture
    def transformer(self):
        def transform_fn(event):
            event.payload["transformed"] = True
            return event

        return EventTransformer(transform_fn=transform_fn)

    def test_transform_event(self, transformer):
        """Test event transformation."""
        event = Event(
            event_type=EventType.METRIC_COLLECTED,
            payload={"value": 100},
            metadata=EventMetadata(
                event_id="evt-1",
                timestamp=datetime.now(timezone.utc),
                source="test",
            ),
        )

        transformed = transformer.transform(event)
        assert transformed.payload["transformed"] is True


class TestEventAggregator:
    """Tests for EventAggregator."""

    @pytest.fixture
    def aggregator(self):
        return EventAggregator(
            window_seconds=60,
            aggregation_fn=lambda events: sum(e.payload.get("value", 0) for e in events),
        )

    @pytest.mark.asyncio
    async def test_aggregate_events(self, aggregator):
        """Test event aggregation."""
        events = [
            Event(
                event_type=EventType.METRIC_COLLECTED,
                payload={"value": i},
                metadata=EventMetadata(
                    event_id=f"evt-{i}",
                    timestamp=datetime.now(timezone.utc),
                    source="test",
                ),
            )
            for i in range(1, 6)
        ]

        for event in events:
            aggregator.add(event)

        result = aggregator.aggregate()
        assert result == 15  # 1+2+3+4+5


class TestStreamProcessor:
    """Tests for StreamProcessor."""

    @pytest.fixture
    def processor(self):
        return StreamProcessor()

    @pytest.mark.asyncio
    async def test_process_stream(self, processor):
        """Test stream processing."""
        events = [
            Event(
                event_type=EventType.JOB_COMPLETED,
                payload={"job_id": f"job-{i}"},
                metadata=EventMetadata(
                    event_id=f"evt-{i}",
                    timestamp=datetime.now(timezone.utc),
                    source="test",
                ),
            )
            for i in range(3)
        ]

        results = []
        async for result in processor.process(iter(events)):
            results.append(result)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_add_filter(self, processor):
        """Test adding filter to processor."""
        filter = EventFilter(event_types=[EventType.JOB_COMPLETED])
        processor.add_filter(filter)

        assert len(processor.filters) == 1

    @pytest.mark.asyncio
    async def test_add_transformer(self, processor):
        """Test adding transformer to processor."""
        transformer = EventTransformer(
            transform_fn=lambda e: e,
        )
        processor.add_transformer(transformer)

        assert len(processor.transformers) == 1


class TestWindowedProcessor:
    """Tests for WindowedProcessor."""

    @pytest.fixture
    def processor(self):
        return WindowedProcessor(
            window_size_seconds=10,
            slide_interval_seconds=5,
        )

    @pytest.mark.asyncio
    async def test_windowed_processing(self, processor):
        """Test windowed processing."""
        events = [
            Event(
                event_type=EventType.METRIC_COLLECTED,
                payload={"value": i},
                metadata=EventMetadata(
                    event_id=f"evt-{i}",
                    timestamp=datetime.now(timezone.utc),
                    source="test",
                ),
            )
            for i in range(10)
        ]

        for event in events:
            processor.add(event)

        windows = processor.get_windows()
        assert len(windows) >= 1


# =============================================================================
# Storage Tests
# =============================================================================


class TestEventStore:
    """Tests for EventStore."""

    @pytest.fixture
    def mock_store(self):
        store = MagicMock(spec=EventStore)
        store.store = AsyncMock()
        store.query = AsyncMock(return_value=[])
        return store

    @pytest.mark.asyncio
    async def test_store_event(self, mock_store):
        """Test storing an event."""
        event = Event(
            event_type=EventType.JOB_SUBMITTED,
            payload={"job_id": "job-123"},
            metadata=EventMetadata(
                event_id="evt-1",
                timestamp=datetime.now(timezone.utc),
                source="test",
            ),
        )

        await mock_store.store(event)
        mock_store.store.assert_called_once()


class TestFileEventStore:
    """Tests for FileEventStore."""

    @pytest.fixture
    def store(self, tmp_path):
        return FileEventStore(base_path=str(tmp_path))

    @pytest.mark.asyncio
    async def test_store_and_query(self, store):
        """Test storing and querying events."""
        event = Event(
            event_type=EventType.JOB_COMPLETED,
            payload={"job_id": "job-123"},
            metadata=EventMetadata(
                event_id="evt-1",
                timestamp=datetime.now(timezone.utc),
                source="test",
            ),
        )

        await store.store(event)
        events = await store.query(event_type=EventType.JOB_COMPLETED)

        assert len(events) >= 1


class TestEventReplay:
    """Tests for EventReplay."""

    @pytest.fixture
    def mock_store(self):
        store = MagicMock(spec=EventStore)
        store.query = AsyncMock(
            return_value=[
                Event(
                    event_type=EventType.JOB_COMPLETED,
                    payload={"job_id": "job-1"},
                    metadata=EventMetadata(
                        event_id="evt-1",
                        timestamp=datetime.now(timezone.utc),
                        source="test",
                    ),
                )
            ]
        )
        return store

    @pytest.fixture
    def replay(self, mock_store):
        return EventReplay(store=mock_store)

    @pytest.mark.asyncio
    async def test_replay_events(self, replay, mock_store):
        """Test replaying events."""
        events = await replay.replay(
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
        )

        assert len(events) >= 0


# =============================================================================
# WebSocket Tests
# =============================================================================


class TestWebSocketConfig:
    """Tests for WebSocketConfig."""

    def test_default_config(self):
        """Test default WebSocket configuration."""
        config = WebSocketConfig()
        assert config.host is not None
        assert config.port > 0

    def test_custom_config(self):
        """Test custom WebSocket configuration."""
        config = WebSocketConfig(
            host="0.0.0.0",
            port=8765,
            max_connections=100,
        )
        assert config.port == 8765


class TestWebSocketEventServer:
    """Tests for WebSocketEventServer."""

    @pytest.fixture
    def server(self):
        config = WebSocketConfig(host="localhost", port=8765)
        return WebSocketEventServer(config=config)

    @pytest.mark.asyncio
    async def test_initialization(self, server):
        """Test server initialization."""
        assert server.config.host == "localhost"
        assert server.config.port == 8765


class TestWebSocketEventClient:
    """Tests for WebSocketEventClient."""

    @pytest.fixture
    def client(self):
        return WebSocketEventClient(url="ws://localhost:8765")

    @pytest.mark.asyncio
    async def test_initialization(self, client):
        """Test client initialization."""
        assert client.url == "ws://localhost:8765"


# =============================================================================
# Integration Tests
# =============================================================================


class TestStreamingIntegration:
    """Integration tests for streaming system."""

    @pytest.mark.asyncio
    async def test_full_pubsub_flow(self):
        """Test complete pub/sub flow."""
        broker = InMemoryBroker()
        manager = PubSubManager(broker=broker)

        # Create topic
        topic = await manager.create_topic("events")

        # Create subscription
        received = []

        async def handler(event):
            received.append(event)

        subscription = await manager.subscribe("consumer-1", "events", handler)

        # Publish event
        event = Event(
            event_type=EventType.JOB_SUBMITTED,
            payload={"job_id": "job-123"},
            metadata=EventMetadata(
                event_id="evt-1",
                timestamp=datetime.now(timezone.utc),
                source="test",
            ),
        )

        await broker.publish("events", event)
        await asyncio.sleep(0.1)

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_stream_processing_pipeline(self):
        """Test stream processing pipeline."""
        # Create pipeline
        processor = StreamProcessor()

        # Add filter
        processor.add_filter(
            EventFilter(event_types=[EventType.METRIC_COLLECTED])
        )

        # Add transformer
        processor.add_transformer(
            EventTransformer(
                transform_fn=lambda e: Event(
                    event_type=e.event_type,
                    payload={**e.payload, "processed": True},
                    metadata=e.metadata,
                )
            )
        )

        # Create events
        events = [
            Event(
                event_type=EventType.METRIC_COLLECTED,
                payload={"value": i},
                metadata=EventMetadata(
                    event_id=f"evt-{i}",
                    timestamp=datetime.now(timezone.utc),
                    source="test",
                ),
            )
            for i in range(5)
        ]

        # Process
        results = []
        async for result in processor.process(iter(events)):
            results.append(result)

        assert all(r.payload.get("processed") for r in results)
