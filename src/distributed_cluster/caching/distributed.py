"""
Distributed cache implementation with consistent hashing and clustering.
"""

import hashlib
import logging
import threading
import time
from bisect import bisect_left, insort
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .backends import CacheBackend, RedisBackend
from .cache import Cache, CacheConfig, CacheStats

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """Status of a cache node."""

    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    DRAINING = "draining"


@dataclass
class CacheNode:
    """Represents a node in the distributed cache cluster."""

    node_id: str
    host: str
    port: int
    status: NodeStatus = NodeStatus.ONLINE
    weight: int = 1
    backend: Optional[CacheBackend] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: Optional[datetime] = None
    stats: CacheStats = field(default_factory=CacheStats)

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def is_healthy(self) -> bool:
        return self.status == NodeStatus.ONLINE

    def connect(self) -> bool:
        """Establish connection to the node."""
        if self.backend:
            return True

        try:
            self.backend = RedisBackend(host=self.host, port=self.port)
            self.status = NodeStatus.ONLINE
            self.last_heartbeat = datetime.now(timezone.utc)
            return True
        except Exception as e:
            logger.error(f"Failed to connect to node {self.node_id}: {e}")
            self.status = NodeStatus.OFFLINE
            return False

    def disconnect(self):
        """Disconnect from the node."""
        if self.backend:
            self.backend.close()
            self.backend = None

    def health_check(self) -> bool:
        """Check if the node is healthy."""
        if not self.backend:
            return False

        try:
            # Try a simple operation
            self.backend.set("__health_check__", b"1", ttl=10)
            self.last_heartbeat = datetime.now(timezone.utc)
            self.status = NodeStatus.ONLINE
            return True
        except Exception:
            self.status = NodeStatus.OFFLINE
            return False


class ConsistentHashing:
    """
    Consistent hashing implementation for distributing keys across nodes.

    Uses virtual nodes for better distribution.
    """

    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self._ring: List[Tuple[int, str]] = []  # (hash, node_id)
        self._nodes: Dict[str, CacheNode] = {}
        self._lock = threading.RLock()

    def _hash(self, key: str) -> int:
        """Generate a hash for a key."""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node: CacheNode):
        """Add a node to the hash ring."""
        with self._lock:
            if node.node_id in self._nodes:
                return

            self._nodes[node.node_id] = node

            # Add virtual nodes
            for i in range(self.virtual_nodes * node.weight):
                virtual_key = f"{node.node_id}:{i}"
                hash_value = self._hash(virtual_key)
                insort(self._ring, (hash_value, node.node_id))

    def remove_node(self, node_id: str):
        """Remove a node from the hash ring."""
        with self._lock:
            if node_id not in self._nodes:
                return

            self._nodes[node_id]

            # Remove virtual nodes
            self._ring = [(h, nid) for h, nid in self._ring if nid != node_id]

            del self._nodes[node_id]

    def get_node(self, key: str) -> Optional[CacheNode]:
        """Get the node responsible for a key."""
        with self._lock:
            if not self._ring:
                return None

            hash_value = self._hash(key)

            # Find the first node with hash >= key hash
            idx = bisect_left(self._ring, (hash_value,))
            if idx >= len(self._ring):
                idx = 0

            _, node_id = self._ring[idx]
            return self._nodes.get(node_id)

    def get_nodes(self, key: str, count: int = 1) -> List[CacheNode]:
        """Get multiple nodes for a key (for replication)."""
        with self._lock:
            if not self._ring or count <= 0:
                return []

            hash_value = self._hash(key)
            idx = bisect_left(self._ring, (hash_value,))

            nodes = []
            seen_node_ids: Set[str] = set()

            for _ in range(len(self._ring)):
                if len(nodes) >= count:
                    break

                if idx >= len(self._ring):
                    idx = 0

                _, node_id = self._ring[idx]

                if node_id not in seen_node_ids:
                    node = self._nodes.get(node_id)
                    if node and node.is_healthy:
                        nodes.append(node)
                        seen_node_ids.add(node_id)

                idx += 1

            return nodes

    def get_all_nodes(self) -> List[CacheNode]:
        """Get all nodes in the ring."""
        with self._lock:
            return list(self._nodes.values())

    @property
    def node_count(self) -> int:
        return len(self._nodes)


class ReplicationStrategy(Enum):
    """Replication strategies for distributed cache."""

    NONE = "none"  # No replication
    SYNC = "sync"  # Synchronous replication
    ASYNC = "async"  # Asynchronous replication
    QUORUM = "quorum"  # Quorum-based replication


@dataclass
class ClusterConfig:
    """Configuration for a cache cluster."""

    replication_factor: int = 2
    replication_strategy: ReplicationStrategy = ReplicationStrategy.ASYNC
    read_quorum: int = 1
    write_quorum: int = 1
    health_check_interval_ms: int = 5000
    connection_timeout_ms: int = 3000
    operation_timeout_ms: int = 1000
    retry_attempts: int = 3
    retry_delay_ms: int = 100
    virtual_nodes: int = 150


class CacheCluster:
    """
    Distributed cache cluster with consistent hashing and replication.
    """

    def __init__(self, config: Optional[ClusterConfig] = None):
        self.config = config or ClusterConfig()
        self._hasher = ConsistentHashing(self.config.virtual_nodes)
        self._lock = threading.RLock()
        self._running = True
        self._health_thread: Optional[threading.Thread] = None
        self._stats = CacheStats()

        self._start_health_check()

    def _start_health_check(self):
        """Start background health check thread."""

        def health_loop():
            while self._running:
                time.sleep(self.config.health_check_interval_ms / 1000)
                self._check_all_nodes()

        self._health_thread = threading.Thread(target=health_loop, daemon=True)
        self._health_thread.start()

    def _check_all_nodes(self):
        """Check health of all nodes."""
        for node in self._hasher.get_all_nodes():
            if not node.health_check():
                logger.warning(f"Node {node.node_id} is unhealthy")

    def add_node(self, node_id: str, host: str, port: int, weight: int = 1) -> bool:
        """Add a node to the cluster."""
        node = CacheNode(
            node_id=node_id,
            host=host,
            port=port,
            weight=weight,
        )

        if not node.connect():
            return False

        self._hasher.add_node(node)
        logger.info(f"Added node {node_id} to cluster")
        return True

    def remove_node(self, node_id: str):
        """Remove a node from the cluster."""
        nodes = self._hasher.get_all_nodes()
        for node in nodes:
            if node.node_id == node_id:
                node.disconnect()
                break

        self._hasher.remove_node(node_id)
        logger.info(f"Removed node {node_id} from cluster")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the cluster."""
        start = time.time()
        nodes = self._hasher.get_nodes(key, self.config.read_quorum)

        if not nodes:
            self._stats.record_miss()
            return default

        for node in nodes:
            try:
                value = node.backend.get(key)
                if value is not None:
                    elapsed = (time.time() - start) * 1000
                    self._stats.record_hit(elapsed, len(value))
                    node.stats.record_hit(elapsed, len(value))
                    return value
            except Exception as e:
                logger.error(f"Error getting from node {node.node_id}: {e}")
                node.status = NodeStatus.DEGRADED

        elapsed = (time.time() - start) * 1000
        self._stats.record_miss(elapsed)
        return default

    def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        """Set a value in the cluster."""
        time.time()
        nodes = self._hasher.get_nodes(key, self.config.replication_factor)

        if not nodes:
            return False

        if self.config.replication_strategy == ReplicationStrategy.NONE:
            # Write to primary only
            return self._write_to_node(nodes[0], key, value, ttl)

        elif self.config.replication_strategy == ReplicationStrategy.SYNC:
            # Synchronous replication to all nodes
            success_count = 0
            for node in nodes:
                if self._write_to_node(node, key, value, ttl):
                    success_count += 1

            return success_count >= self.config.write_quorum

        elif self.config.replication_strategy == ReplicationStrategy.ASYNC:
            # Write to primary, async replicate
            success = self._write_to_node(nodes[0], key, value, ttl)
            if success and len(nodes) > 1:
                threading.Thread(target=self._async_replicate, args=(nodes[1:], key, value, ttl), daemon=True).start()
            return success

        elif self.config.replication_strategy == ReplicationStrategy.QUORUM:
            # Quorum-based writes
            success_count = 0
            for node in nodes:
                if self._write_to_node(node, key, value, ttl):
                    success_count += 1
                    if success_count >= self.config.write_quorum:
                        # Async replicate to remaining
                        remaining = nodes[nodes.index(node) + 1 :]
                        if remaining:
                            threading.Thread(
                                target=self._async_replicate, args=(remaining, key, value, ttl), daemon=True
                            ).start()
                        return True
            return False

        return False

    def _write_to_node(self, node: CacheNode, key: str, value: bytes, ttl: Optional[int]) -> bool:
        """Write to a single node with retries."""
        for attempt in range(self.config.retry_attempts):
            try:
                result = node.backend.set(key, value, ttl)
                if result:
                    node.stats.record_set(0, len(value))
                    return True
            except Exception as e:
                logger.error(f"Write error on node {node.node_id}, attempt {attempt + 1}: {e}")
                if attempt < self.config.retry_attempts - 1:
                    time.sleep(self.config.retry_delay_ms / 1000)

        node.status = NodeStatus.DEGRADED
        return False

    def _async_replicate(self, nodes: List[CacheNode], key: str, value: bytes, ttl: Optional[int]):
        """Asynchronously replicate to nodes."""
        for node in nodes:
            self._write_to_node(node, key, value, ttl)

    def delete(self, key: str) -> bool:
        """Delete a value from the cluster."""
        nodes = self._hasher.get_nodes(key, self.config.replication_factor)

        if not nodes:
            return False

        success = False
        for node in nodes:
            try:
                if node.backend.delete(key):
                    success = True
                    node.stats.record_delete()
            except Exception as e:
                logger.error(f"Delete error on node {node.node_id}: {e}")

        if success:
            self._stats.record_delete()

        return success

    def exists(self, key: str) -> bool:
        """Check if a key exists in the cluster."""
        nodes = self._hasher.get_nodes(key, 1)

        if not nodes:
            return False

        for node in nodes:
            try:
                if node.backend.exists(key):
                    return True
            except Exception:
                pass

        return False

    def get_node_for_key(self, key: str) -> Optional[CacheNode]:
        """Get the primary node for a key."""
        return self._hasher.get_node(key)

    def get_cluster_stats(self) -> Dict[str, Any]:
        """Get cluster statistics."""
        nodes_stats = {}
        for node in self._hasher.get_all_nodes():
            nodes_stats[node.node_id] = {
                "address": node.address,
                "status": node.status.value,
                "stats": node.stats.to_dict(),
            }

        return {
            "node_count": self._hasher.node_count,
            "replication_factor": self.config.replication_factor,
            "replication_strategy": self.config.replication_strategy.value,
            "nodes": nodes_stats,
            "overall_stats": self._stats.to_dict(),
        }

    def shutdown(self):
        """Shutdown the cluster."""
        self._running = False

        for node in self._hasher.get_all_nodes():
            node.disconnect()


class DistributedCache(Cache):
    """
    Distributed cache implementation using a cluster backend.
    """

    def __init__(self, cluster: CacheCluster, config: Optional[CacheConfig] = None):
        super().__init__(config)
        self.cluster = cluster

    def get(self, key: str, default: Any = None) -> Any:
        full_key = self._make_key(key)
        value = self.cluster.get(full_key)

        if value is not None:
            try:
                return self.serializer.deserialize(value)
            except Exception:
                pass

        return default

    def set(self, key: str, value: Any, ttl: Optional[int] = None, **kwargs) -> bool:
        full_key = self._make_key(key)

        try:
            serialized = self.serializer.serialize(value)
        except Exception as e:
            logger.error(f"Serialization error: {e}")
            return False

        return self.cluster.set(full_key, serialized, ttl or self.config.default_ttl_seconds)

    def delete(self, key: str) -> bool:
        full_key = self._make_key(key)
        return self.cluster.delete(full_key)

    def exists(self, key: str) -> bool:
        full_key = self._make_key(key)
        return self.cluster.exists(full_key)

    def clear(self) -> int:
        # Distributed clear is expensive - iterate all keys
        count = 0
        for key in self.keys():
            if self.delete(key):
                count += 1
        return count

    def keys(self, pattern: str = "*") -> List[str]:
        full_pattern = self._make_key(pattern)
        all_keys = set()

        for node in self.cluster._hasher.get_all_nodes():
            if node.backend:
                try:
                    keys = node.backend.keys(full_pattern)
                    all_keys.update(keys)
                except Exception:
                    pass

        return list(all_keys)

    def get_stats(self) -> Dict[str, Any]:
        return self.cluster.get_cluster_stats()
