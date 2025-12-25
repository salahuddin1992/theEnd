"""
Message broker implementations for Kafka, Redis Streams, and in-memory.
"""

import asyncio
import json
import logging
import time
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from queue import Queue, Empty
import uuid

from .events import Event
from .consumers import Offset

logger = logging.getLogger(__name__)


@dataclass
class BrokerConfig:
    """Configuration for message brokers."""
    bootstrap_servers: List[str] = field(default_factory=lambda: ["localhost:9092"])
    client_id: str = "nebulacompute-client"
    security_protocol: str = "PLAINTEXT"  # PLAINTEXT, SSL, SASL_PLAINTEXT, SASL_SSL
    sasl_mechanism: Optional[str] = None  # PLAIN, SCRAM-SHA-256, SCRAM-SHA-512
    sasl_username: Optional[str] = None
    sasl_password: Optional[str] = None
    ssl_cafile: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
    connection_timeout_ms: int = 30000
    request_timeout_ms: int = 30000
    metadata_max_age_ms: int = 300000
    max_message_size: int = 1048576  # 1MB
    compression_type: str = "none"  # none, gzip, snappy, lz4, zstd

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "client_id": self.client_id,
            "security_protocol": self.security_protocol,
            "connection_timeout_ms": self.connection_timeout_ms,
            "request_timeout_ms": self.request_timeout_ms,
        }


@dataclass
class TopicConfig:
    """Configuration for a topic."""
    name: str
    num_partitions: int = 8
    replication_factor: int = 3
    retention_ms: int = 604800000  # 7 days
    retention_bytes: int = -1  # unlimited
    segment_bytes: int = 1073741824  # 1GB
    cleanup_policy: str = "delete"  # delete, compact, delete,compact
    compression_type: str = "producer"
    min_insync_replicas: int = 2
    max_message_bytes: int = 1048576  # 1MB


class MessageBroker(ABC):
    """Abstract base class for message brokers."""

    def __init__(self, config: Optional[BrokerConfig] = None):
        self.config = config or BrokerConfig()
        self._connected = False

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the broker."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass

    @abstractmethod
    def create_topic(self, config: TopicConfig) -> bool:
        """Create a new topic."""
        pass

    @abstractmethod
    def delete_topic(self, topic: str) -> bool:
        """Delete a topic."""
        pass

    @abstractmethod
    def list_topics(self) -> List[str]:
        """List all topics."""
        pass

    @abstractmethod
    def send(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        """Send an event to a topic."""
        pass

    @abstractmethod
    def send_batch(self, topic: str, events: List[Event]) -> bool:
        """Send a batch of events."""
        pass

    @abstractmethod
    def poll(
        self,
        topics: List[str],
        timeout_ms: int,
        group_id: Optional[str] = None
    ) -> List[Tuple[str, int, int, Dict]]:
        """Poll for events. Returns list of (topic, partition, offset, event_data)."""
        pass

    @abstractmethod
    def commit(self, offsets: List[Offset], group_id: str) -> None:
        """Commit offsets for a consumer group."""
        pass

    @abstractmethod
    def get_offsets(self, topic: str, group_id: str) -> Dict[int, int]:
        """Get committed offsets for a topic and group."""
        pass

    def is_connected(self) -> bool:
        return self._connected


class InMemoryBroker(MessageBroker):
    """In-memory message broker for testing and development."""

    def __init__(self, config: Optional[BrokerConfig] = None):
        super().__init__(config)
        self._topics: Dict[str, Dict[int, List[Tuple[str, Dict]]]] = {}  # topic -> partition -> [(key, event)]
        self._topic_configs: Dict[str, TopicConfig] = {}
        self._offsets: Dict[str, Dict[str, Dict[int, int]]] = {}  # topic -> group -> partition -> offset
        self._consumer_positions: Dict[str, Dict[str, Dict[int, int]]] = {}
        self._lock = threading.RLock()

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def create_topic(self, config: TopicConfig) -> bool:
        with self._lock:
            if config.name in self._topics:
                return False

            self._topics[config.name] = {
                p: [] for p in range(config.num_partitions)
            }
            self._topic_configs[config.name] = config
            self._offsets[config.name] = {}
            return True

    def delete_topic(self, topic: str) -> bool:
        with self._lock:
            if topic not in self._topics:
                return False

            del self._topics[topic]
            del self._topic_configs[topic]
            self._offsets.pop(topic, None)
            return True

    def list_topics(self) -> List[str]:
        with self._lock:
            return list(self._topics.keys())

    def _get_partition(self, topic: str, key: Optional[str]) -> int:
        """Determine partition for a key."""
        config = self._topic_configs.get(topic)
        if not config:
            return 0

        if key:
            return hash(key) % config.num_partitions
        else:
            return hash(str(time.time())) % config.num_partitions

    def send(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        with self._lock:
            if topic not in self._topics:
                # Auto-create topic
                self.create_topic(TopicConfig(name=topic))

            partition = self._get_partition(topic, key)
            event_data = event.to_dict()
            self._topics[topic][partition].append((key, event_data))
            return True

    def send_batch(self, topic: str, events: List[Event]) -> bool:
        for event in events:
            if not self.send(topic, event):
                return False
        return True

    def poll(
        self,
        topics: List[str],
        timeout_ms: int,
        group_id: Optional[str] = None
    ) -> List[Tuple[str, int, int, Dict]]:
        results = []
        group_id = group_id or "default"

        with self._lock:
            for topic in topics:
                if topic not in self._topics:
                    continue

                if topic not in self._consumer_positions:
                    self._consumer_positions[topic] = {}
                if group_id not in self._consumer_positions[topic]:
                    self._consumer_positions[topic][group_id] = {
                        p: 0 for p in range(len(self._topics[topic]))
                    }

                for partition, messages in self._topics[topic].items():
                    pos = self._consumer_positions[topic][group_id].get(partition, 0)

                    if pos < len(messages):
                        key, event_data = messages[pos]
                        results.append((topic, partition, pos, event_data))
                        self._consumer_positions[topic][group_id][partition] = pos + 1

        return results

    def commit(self, offsets: List[Offset], group_id: str) -> None:
        with self._lock:
            for offset in offsets:
                if offset.topic not in self._offsets:
                    self._offsets[offset.topic] = {}
                if group_id not in self._offsets[offset.topic]:
                    self._offsets[offset.topic][group_id] = {}
                self._offsets[offset.topic][group_id][offset.partition] = offset.offset

    def get_offsets(self, topic: str, group_id: str) -> Dict[int, int]:
        with self._lock:
            return self._offsets.get(topic, {}).get(group_id, {})


class KafkaBroker(MessageBroker):
    """Apache Kafka message broker implementation."""

    def __init__(self, config: Optional[BrokerConfig] = None):
        super().__init__(config)
        self._producer = None
        self._consumer = None
        self._admin_client = None

    def connect(self) -> bool:
        """Connect to Kafka cluster."""
        try:
            from kafka import KafkaProducer, KafkaConsumer, KafkaAdminClient
            from kafka.admin import NewTopic

            bootstrap_servers = ",".join(self.config.bootstrap_servers)

            # Create producer
            self._producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                client_id=f"{self.config.client_id}-producer",
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                compression_type=self.config.compression_type if self.config.compression_type != "none" else None,
                max_request_size=self.config.max_message_size,
            )

            # Create admin client
            self._admin_client = KafkaAdminClient(
                bootstrap_servers=bootstrap_servers,
                client_id=f"{self.config.client_id}-admin",
            )

            self._connected = True
            logger.info(f"Connected to Kafka cluster: {bootstrap_servers}")
            return True

        except ImportError:
            logger.error("kafka-python not installed. Run: pip install kafka-python")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Kafka."""
        if self._producer:
            self._producer.close()
        if self._consumer:
            self._consumer.close()
        if self._admin_client:
            self._admin_client.close()
        self._connected = False

    def create_topic(self, config: TopicConfig) -> bool:
        """Create a Kafka topic."""
        try:
            from kafka.admin import NewTopic

            topic = NewTopic(
                name=config.name,
                num_partitions=config.num_partitions,
                replication_factor=config.replication_factor,
                topic_configs={
                    "retention.ms": str(config.retention_ms),
                    "retention.bytes": str(config.retention_bytes),
                    "segment.bytes": str(config.segment_bytes),
                    "cleanup.policy": config.cleanup_policy,
                    "compression.type": config.compression_type,
                    "min.insync.replicas": str(config.min_insync_replicas),
                    "max.message.bytes": str(config.max_message_bytes),
                }
            )

            self._admin_client.create_topics([topic])
            logger.info(f"Created topic: {config.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create topic {config.name}: {e}")
            return False

    def delete_topic(self, topic: str) -> bool:
        """Delete a Kafka topic."""
        try:
            self._admin_client.delete_topics([topic])
            logger.info(f"Deleted topic: {topic}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete topic {topic}: {e}")
            return False

    def list_topics(self) -> List[str]:
        """List all Kafka topics."""
        try:
            metadata = self._admin_client.list_topics()
            return list(metadata)
        except Exception as e:
            logger.error(f"Failed to list topics: {e}")
            return []

    def send(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        """Send an event to Kafka."""
        try:
            future = self._producer.send(
                topic,
                value=event.to_dict(),
                key=key
            )
            future.get(timeout=10)
            return True
        except Exception as e:
            logger.error(f"Failed to send event to {topic}: {e}")
            return False

    def send_batch(self, topic: str, events: List[Event]) -> bool:
        """Send a batch of events to Kafka."""
        try:
            for event in events:
                self._producer.send(topic, value=event.to_dict())
            self._producer.flush()
            return True
        except Exception as e:
            logger.error(f"Failed to send batch to {topic}: {e}")
            return False

    def poll(
        self,
        topics: List[str],
        timeout_ms: int,
        group_id: Optional[str] = None
    ) -> List[Tuple[str, int, int, Dict]]:
        """Poll for events from Kafka."""
        try:
            from kafka import KafkaConsumer

            if self._consumer is None:
                bootstrap_servers = ",".join(self.config.bootstrap_servers)
                self._consumer = KafkaConsumer(
                    *topics,
                    bootstrap_servers=bootstrap_servers,
                    group_id=group_id or "default",
                    auto_offset_reset="latest",
                    enable_auto_commit=False,
                    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                    consumer_timeout_ms=timeout_ms,
                )

            results = []
            for message in self._consumer:
                results.append((
                    message.topic,
                    message.partition,
                    message.offset,
                    message.value
                ))

            return results

        except Exception as e:
            logger.error(f"Failed to poll from Kafka: {e}")
            return []

    def commit(self, offsets: List[Offset], group_id: str) -> None:
        """Commit offsets to Kafka."""
        try:
            if self._consumer:
                from kafka import TopicPartition, OffsetAndMetadata

                offset_dict = {
                    TopicPartition(o.topic, o.partition): OffsetAndMetadata(o.offset + 1, o.metadata)
                    for o in offsets
                }
                self._consumer.commit(offset_dict)

        except Exception as e:
            logger.error(f"Failed to commit offsets: {e}")

    def get_offsets(self, topic: str, group_id: str) -> Dict[int, int]:
        """Get committed offsets from Kafka."""
        try:
            from kafka import TopicPartition

            if self._consumer:
                partitions = self._consumer.partitions_for_topic(topic)
                if partitions:
                    tps = [TopicPartition(topic, p) for p in partitions]
                    committed = self._consumer.committed(tps)
                    return {
                        tp.partition: (offset.offset if offset else 0)
                        for tp, offset in committed.items()
                    }
            return {}
        except Exception as e:
            logger.error(f"Failed to get offsets: {e}")
            return {}


class RedisBroker(MessageBroker):
    """Redis Streams message broker implementation."""

    def __init__(self, config: Optional[BrokerConfig] = None):
        super().__init__(config)
        self._redis = None
        self._consumer_groups: Dict[str, Set[str]] = {}  # topic -> set of groups

    def connect(self) -> bool:
        """Connect to Redis."""
        try:
            import redis

            host = self.config.bootstrap_servers[0].split(":")[0] if self.config.bootstrap_servers else "localhost"
            port = int(self.config.bootstrap_servers[0].split(":")[1]) if ":" in self.config.bootstrap_servers[0] else 6379

            self._redis = redis.Redis(
                host=host,
                port=port,
                decode_responses=True,
                socket_timeout=self.config.connection_timeout_ms / 1000,
            )

            self._redis.ping()
            self._connected = True
            logger.info(f"Connected to Redis: {host}:{port}")
            return True

        except ImportError:
            logger.error("redis not installed. Run: pip install redis")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._redis:
            self._redis.close()
        self._connected = False

    def create_topic(self, config: TopicConfig) -> bool:
        """Create a Redis stream (topic)."""
        try:
            # Redis streams are created automatically on first write
            # We can set max length for retention
            stream_key = f"stream:{config.name}"
            self._redis.xadd(
                stream_key,
                {"__init__": "1"},
                maxlen=config.retention_bytes if config.retention_bytes > 0 else None
            )
            return True
        except Exception as e:
            logger.error(f"Failed to create stream {config.name}: {e}")
            return False

    def delete_topic(self, topic: str) -> bool:
        """Delete a Redis stream."""
        try:
            stream_key = f"stream:{topic}"
            self._redis.delete(stream_key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete stream {topic}: {e}")
            return False

    def list_topics(self) -> List[str]:
        """List all Redis streams."""
        try:
            keys = self._redis.keys("stream:*")
            return [k.replace("stream:", "") for k in keys]
        except Exception as e:
            logger.error(f"Failed to list streams: {e}")
            return []

    def send(self, topic: str, event: Event, key: Optional[str] = None) -> bool:
        """Send an event to Redis stream."""
        try:
            stream_key = f"stream:{topic}"
            event_data = event.to_dict()

            # Flatten for Redis (Redis streams don't support nested structures directly)
            flat_data = {
                "event_json": json.dumps(event_data),
                "event_id": event.event_id,
                "event_type": event.event_type.name,
                "timestamp": event.timestamp.isoformat(),
            }
            if key:
                flat_data["key"] = key

            self._redis.xadd(stream_key, flat_data)
            return True
        except Exception as e:
            logger.error(f"Failed to send to Redis stream {topic}: {e}")
            return False

    def send_batch(self, topic: str, events: List[Event]) -> bool:
        """Send a batch of events to Redis stream."""
        try:
            pipeline = self._redis.pipeline()
            stream_key = f"stream:{topic}"

            for event in events:
                flat_data = {
                    "event_json": json.dumps(event.to_dict()),
                    "event_id": event.event_id,
                    "event_type": event.event_type.name,
                    "timestamp": event.timestamp.isoformat(),
                }
                pipeline.xadd(stream_key, flat_data)

            pipeline.execute()
            return True
        except Exception as e:
            logger.error(f"Failed to send batch to Redis stream {topic}: {e}")
            return False

    def _ensure_consumer_group(self, topic: str, group_id: str):
        """Ensure consumer group exists."""
        stream_key = f"stream:{topic}"

        if topic not in self._consumer_groups:
            self._consumer_groups[topic] = set()

        if group_id not in self._consumer_groups[topic]:
            try:
                self._redis.xgroup_create(stream_key, group_id, id="0", mkstream=True)
                self._consumer_groups[topic].add(group_id)
            except Exception:
                # Group might already exist
                self._consumer_groups[topic].add(group_id)

    def poll(
        self,
        topics: List[str],
        timeout_ms: int,
        group_id: Optional[str] = None
    ) -> List[Tuple[str, int, int, Dict]]:
        """Poll for events from Redis streams."""
        try:
            group_id = group_id or "default"
            consumer_name = f"consumer-{uuid.uuid4().hex[:8]}"
            results = []

            for topic in topics:
                self._ensure_consumer_group(topic, group_id)
                stream_key = f"stream:{topic}"

                messages = self._redis.xreadgroup(
                    group_id,
                    consumer_name,
                    {stream_key: ">"},
                    count=100,
                    block=timeout_ms
                )

                if messages:
                    for stream, entries in messages:
                        for message_id, data in entries:
                            event_data = json.loads(data.get("event_json", "{}"))
                            # Use message ID as offset (Redis stream IDs are like "1234567890123-0")
                            offset_str = message_id.split("-")[0]
                            offset = int(offset_str) if offset_str.isdigit() else 0
                            results.append((topic, 0, offset, event_data))

            return results
        except Exception as e:
            logger.error(f"Failed to poll from Redis streams: {e}")
            return []

    def commit(self, offsets: List[Offset], group_id: str) -> None:
        """Acknowledge messages in Redis streams."""
        try:
            for offset in offsets:
                stream_key = f"stream:{offset.topic}"
                # In Redis Streams, we acknowledge by message ID
                # This is a simplified version
                pass
        except Exception as e:
            logger.error(f"Failed to commit in Redis: {e}")

    def get_offsets(self, topic: str, group_id: str) -> Dict[int, int]:
        """Get pending message info from Redis stream."""
        try:
            stream_key = f"stream:{topic}"
            info = self._redis.xinfo_groups(stream_key)

            for group_info in info:
                if group_info.get("name") == group_id:
                    return {0: group_info.get("last-delivered-id", 0)}

            return {}
        except Exception as e:
            logger.error(f"Failed to get offsets from Redis: {e}")
            return {}


class BrokerFactory:
    """Factory for creating message brokers."""

    _brokers: Dict[str, type] = {
        "memory": InMemoryBroker,
        "kafka": KafkaBroker,
        "redis": RedisBroker,
    }

    @classmethod
    def create(cls, broker_type: str, config: Optional[BrokerConfig] = None) -> MessageBroker:
        """Create a broker of the specified type."""
        broker_class = cls._brokers.get(broker_type.lower())
        if not broker_class:
            raise ValueError(f"Unknown broker type: {broker_type}")

        return broker_class(config)

    @classmethod
    def register(cls, name: str, broker_class: type):
        """Register a new broker type."""
        cls._brokers[name.lower()] = broker_class
