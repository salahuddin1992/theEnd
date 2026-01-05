"""
Distributed Cache Coordinator - Enhanced coordination between cache nodes.

This module provides sophisticated coordination for distributed caching
including consistent hashing, replication management, partition handling,
and cross-node cache synchronization.
"""

import asyncio
import bisect
import hashlib
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """Status of a cache node."""

    ONLINE = "online"
    OFFLINE = "offline"
    JOINING = "joining"
    LEAVING = "leaving"
    DRAINING = "draining"
    DEGRADED = "degraded"


class ReplicationStrategy(Enum):
    """Replication strategies."""

    NONE = "none"
    SYNC = "sync"
    ASYNC = "async"
    QUORUM = "quorum"


class ConsistencyLevel(Enum):
    """Consistency levels for operations."""

    ONE = 1
    QUORUM = 2
    ALL = 3
    LOCAL_ONE = 4
    LOCAL_QUORUM = 5


@dataclass
class CacheNode:
    """Represents a cache node in the cluster."""

    node_id: str
    host: str
    port: int
    status: NodeStatus = NodeStatus.ONLINE
    weight: int = 100
    zone: str = "default"
    capacity_mb: int = 1024
    used_mb: int = 0
    last_heartbeat: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        """Check if node is available for operations."""
        return self.status in (NodeStatus.ONLINE, NodeStatus.DEGRADED)

    @property
    def utilization(self) -> float:
        """Get node utilization."""
        return self.used_mb / self.capacity_mb if self.capacity_mb > 0 else 0


@dataclass
class Partition:
    """Represents a partition in the cache cluster."""

    partition_id: int
    primary_node: str
    replica_nodes: List[str] = field(default_factory=list)
    key_count: int = 0
    size_bytes: int = 0
    status: str = "active"


@dataclass
class ReplicationEvent:
    """Event for cache replication."""

    event_id: str
    key: str
    operation: str  # 'set', 'delete', 'invalidate'
    value: Optional[bytes] = None
    timestamp: float = field(default_factory=time.time)
    source_node: str = ""
    ttl_seconds: Optional[int] = None


class ConsistentHash:
    """
    Consistent hashing ring for distributing keys across nodes.
    """

    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.ring: List[Tuple[int, str]] = []
        self.nodes: Dict[str, CacheNode] = {}
        self._lock = threading.Lock()

    def _hash(self, key: str) -> int:
        """Hash a key to a position on the ring."""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node: CacheNode):
        """Add a node to the hash ring."""
        with self._lock:
            self.nodes[node.node_id] = node

            # Add virtual nodes
            for i in range(self.virtual_nodes):
                vnode_key = f"{node.node_id}:{i}"
                vnode_hash = self._hash(vnode_key)
                bisect.insort(self.ring, (vnode_hash, node.node_id))

            logger.info(f"Added node {node.node_id} to hash ring")

    def remove_node(self, node_id: str):
        """Remove a node from the hash ring."""
        with self._lock:
            if node_id not in self.nodes:
                return

            # Remove virtual nodes
            self.ring = [(h, n) for h, n in self.ring if n != node_id]

            del self.nodes[node_id]
            logger.info(f"Removed node {node_id} from hash ring")

    def get_node(self, key: str) -> Optional[str]:
        """Get the primary node for a key."""
        with self._lock:
            if not self.ring:
                return None

            key_hash = self._hash(key)

            # Find the first node with hash >= key_hash
            idx = bisect.bisect_left(self.ring, (key_hash,))
            if idx == len(self.ring):
                idx = 0

            return self.ring[idx][1]

    def get_nodes(self, key: str, count: int = 3) -> List[str]:
        """Get multiple nodes for a key (for replication)."""
        with self._lock:
            if not self.ring:
                return []

            key_hash = self._hash(key)
            idx = bisect.bisect_left(self.ring, (key_hash,))

            result = []
            seen = set()

            for i in range(len(self.ring)):
                ring_idx = (idx + i) % len(self.ring)
                node_id = self.ring[ring_idx][1]

                if node_id not in seen:
                    # Check if node is available
                    node = self.nodes.get(node_id)
                    if node and node.is_available:
                        result.append(node_id)
                        seen.add(node_id)

                if len(result) >= count:
                    break

            return result

    def get_keys_for_node(self, node_id: str, total_keys: int) -> Tuple[int, int]:
        """Estimate the key range for a node."""
        with self._lock:
            if node_id not in self.nodes or not self.ring:
                return (0, 0)

            # Find all virtual nodes for this node
            node_hashes = sorted([h for h, n in self.ring if n == node_id])

            if not node_hashes:
                return (0, 0)

            # Estimate keys based on ring coverage
            ring_size = 2**128  # MD5 produces 128-bit hashes
            coverage = 0

            for i, h in enumerate(node_hashes):
                if i == 0:
                    prev_h = self.ring[-1][0]
                else:
                    prev_h = node_hashes[i - 1]

                if h > prev_h:
                    coverage += h - prev_h
                else:
                    coverage += ring_size - prev_h + h

            ratio = coverage / ring_size
            estimated_keys = int(total_keys * ratio)

            return (estimated_keys, int(ratio * 100))


class ReplicationManager:
    """
    Manages data replication across cache nodes.
    """

    def __init__(
        self,
        strategy: ReplicationStrategy = ReplicationStrategy.ASYNC,
        replication_factor: int = 2,
        consistency: ConsistencyLevel = ConsistencyLevel.ONE,
    ):
        self.strategy = strategy
        self.replication_factor = replication_factor
        self.consistency = consistency

        # Pending replications
        self.pending_queue: deque = deque(maxlen=100000)
        self.in_progress: Dict[str, ReplicationEvent] = {}
        self.failed_events: deque = deque(maxlen=1000)

        # Statistics
        self.replicated_count = 0
        self.failed_count = 0
        self.lag_ms = 0.0

        # Replication handlers
        self.replication_handlers: Dict[str, Callable[[ReplicationEvent, str], bool]] = {}

        # Control
        self._lock = threading.Lock()
        self._running = False
        self._replication_task: Optional[asyncio.Task] = None

    def register_handler(self, node_id: str, handler: Callable[[ReplicationEvent, str], bool]):
        """Register a replication handler for a node."""
        self.replication_handlers[node_id] = handler

    def queue_replication(self, event: ReplicationEvent, target_nodes: List[str]):
        """Queue a replication event."""
        with self._lock:
            for node_id in target_nodes:
                self.pending_queue.append((event, node_id))

    async def replicate_sync(self, event: ReplicationEvent, target_nodes: List[str]) -> int:
        """Synchronously replicate to nodes."""
        success_count = 0

        for node_id in target_nodes:
            handler = self.replication_handlers.get(node_id)
            if handler:
                try:
                    if await asyncio.to_thread(handler, event, node_id):
                        success_count += 1
                except Exception as e:
                    logger.error(f"Replication to {node_id} failed: {e}")

        return success_count

    async def replicate_quorum(self, event: ReplicationEvent, target_nodes: List[str]) -> bool:
        """Replicate with quorum consistency."""
        required = len(target_nodes) // 2 + 1
        success_count = await self.replicate_sync(event, target_nodes)
        return success_count >= required

    async def start_replication_loop(self):
        """Start async replication loop."""
        if self._running:
            return

        self._running = True
        self._replication_task = asyncio.create_task(self._replication_loop())
        logger.info("Replication loop started")

    async def stop_replication_loop(self):
        """Stop async replication loop."""
        self._running = False
        if self._replication_task:
            self._replication_task.cancel()
            try:
                await self._replication_task
            except asyncio.CancelledError:
                pass
        logger.info("Replication loop stopped")

    async def _replication_loop(self):
        """Background loop for async replication."""
        while self._running:
            try:
                if not self.pending_queue:
                    await asyncio.sleep(0.01)
                    continue

                with self._lock:
                    if not self.pending_queue:
                        continue
                    event, target_node = self.pending_queue.popleft()
                    self.in_progress[event.event_id] = event

                # Execute replication
                handler = self.replication_handlers.get(target_node)
                if handler:
                    try:
                        success = await asyncio.to_thread(handler, event, target_node)
                        if success:
                            self.replicated_count += 1
                            self.lag_ms = (time.time() - event.timestamp) * 1000
                        else:
                            self.failed_count += 1
                            self.failed_events.append((event, target_node))
                    except Exception as e:
                        logger.error(f"Replication error: {e}")
                        self.failed_count += 1

                with self._lock:
                    self.in_progress.pop(event.event_id, None)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Replication loop error: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get replication statistics."""
        with self._lock:
            return {
                "strategy": self.strategy.value,
                "replication_factor": self.replication_factor,
                "consistency": self.consistency.value,
                "pending_count": len(self.pending_queue),
                "in_progress_count": len(self.in_progress),
                "replicated_count": self.replicated_count,
                "failed_count": self.failed_count,
                "lag_ms": self.lag_ms,
            }


class PartitionManager:
    """
    Manages cache partitions for distributed data placement.
    """

    def __init__(self, num_partitions: int = 256):
        self.num_partitions = num_partitions
        self.partitions: Dict[int, Partition] = {}
        self.node_partitions: Dict[str, Set[int]] = defaultdict(set)
        self._lock = threading.Lock()

        # Initialize partitions
        for i in range(num_partitions):
            self.partitions[i] = Partition(partition_id=i, primary_node="")

    def _get_partition_id(self, key: str) -> int:
        """Get partition ID for a key."""
        key_hash = int(hashlib.md5(key.encode()).hexdigest(), 16)
        return key_hash % self.num_partitions

    def assign_partition(self, partition_id: int, primary_node: str, replica_nodes: List[str]):
        """Assign a partition to nodes."""
        with self._lock:
            partition = self.partitions[partition_id]

            # Remove old assignments
            if partition.primary_node:
                self.node_partitions[partition.primary_node].discard(partition_id)
            for replica in partition.replica_nodes:
                self.node_partitions[replica].discard(partition_id)

            # Set new assignments
            partition.primary_node = primary_node
            partition.replica_nodes = replica_nodes

            self.node_partitions[primary_node].add(partition_id)
            for replica in replica_nodes:
                self.node_partitions[replica].add(partition_id)

    def get_partition(self, key: str) -> Partition:
        """Get the partition for a key."""
        partition_id = self._get_partition_id(key)
        return self.partitions[partition_id]

    def get_node_partitions(self, node_id: str) -> Set[int]:
        """Get all partitions for a node."""
        with self._lock:
            return self.node_partitions[node_id].copy()

    def rebalance(self, nodes: List[CacheNode]) -> Dict[int, Tuple[str, List[str]]]:
        """Rebalance partitions across nodes."""
        if not nodes:
            return {}

        available_nodes = [n for n in nodes if n.is_available]
        if not available_nodes:
            return {}

        changes = {}

        with self._lock:
            # Calculate target partitions per node
            self.num_partitions // len(available_nodes)

            # Simple round-robin assignment with replication
            for i, partition in self.partitions.items():
                primary_idx = i % len(available_nodes)
                primary_node = available_nodes[primary_idx].node_id

                replicas = []
                for r in range(1, 3):  # Up to 2 replicas
                    replica_idx = (primary_idx + r) % len(available_nodes)
                    if available_nodes[replica_idx].node_id != primary_node:
                        replicas.append(available_nodes[replica_idx].node_id)

                if partition.primary_node != primary_node or partition.replica_nodes != replicas:
                    changes[i] = (primary_node, replicas)
                    self.assign_partition(i, primary_node, replicas)

        return changes

    def get_stats(self) -> Dict[str, Any]:
        """Get partition statistics."""
        with self._lock:
            node_counts = {node_id: len(partitions) for node_id, partitions in self.node_partitions.items()}

            return {
                "num_partitions": self.num_partitions,
                "partitions_per_node": node_counts,
                "total_keys": sum(p.key_count for p in self.partitions.values()),
                "total_size_bytes": sum(p.size_bytes for p in self.partitions.values()),
            }


class DistributedCacheCoordinator:
    """
    Comprehensive coordinator for distributed caching with consistent
    hashing, replication, and partition management.
    """

    def __init__(
        self,
        node_id: str,
        replication_factor: int = 2,
        replication_strategy: ReplicationStrategy = ReplicationStrategy.ASYNC,
        consistency_level: ConsistencyLevel = ConsistencyLevel.ONE,
        num_partitions: int = 256,
    ):
        self.node_id = node_id
        self.replication_factor = replication_factor

        # Components
        self.hash_ring = ConsistentHash()
        self.replication_manager = ReplicationManager(
            strategy=replication_strategy, replication_factor=replication_factor, consistency=consistency_level
        )
        self.partition_manager = PartitionManager(num_partitions)

        # Node tracking
        self.nodes: Dict[str, CacheNode] = {}
        self.local_node: Optional[CacheNode] = None

        # Callbacks
        self.node_change_callbacks: List[Callable[[str, NodeStatus], None]] = []
        self.rebalance_callbacks: List[Callable[[Dict[int, Tuple[str, List[str]]]], None]] = []

        # Control
        self._lock = threading.RLock()
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None

    def initialize_local_node(self, host: str, port: int, capacity_mb: int = 1024, zone: str = "default"):
        """Initialize the local node."""
        self.local_node = CacheNode(
            node_id=self.node_id,
            host=host,
            port=port,
            capacity_mb=capacity_mb,
            zone=zone,
            status=NodeStatus.ONLINE,
        )
        self.register_node(self.local_node)

    def register_node(self, node: CacheNode):
        """Register a node with the coordinator."""
        with self._lock:
            self.nodes[node.node_id] = node
            self.hash_ring.add_node(node)

            # Rebalance partitions
            changes = self.partition_manager.rebalance(list(self.nodes.values()))
            if changes:
                self._notify_rebalance(changes)

            # Notify callbacks
            for callback in self.node_change_callbacks:
                try:
                    callback(node.node_id, node.status)
                except Exception as e:
                    logger.error(f"Node change callback error: {e}")

            logger.info(f"Registered node {node.node_id}")

    def deregister_node(self, node_id: str):
        """Deregister a node from the coordinator."""
        with self._lock:
            if node_id not in self.nodes:
                return

            node = self.nodes[node_id]
            node.status = NodeStatus.LEAVING

            self.hash_ring.remove_node(node_id)
            del self.nodes[node_id]

            # Rebalance partitions
            changes = self.partition_manager.rebalance(list(self.nodes.values()))
            if changes:
                self._notify_rebalance(changes)

            # Notify callbacks
            for callback in self.node_change_callbacks:
                try:
                    callback(node_id, NodeStatus.OFFLINE)
                except Exception as e:
                    logger.error(f"Node change callback error: {e}")

            logger.info(f"Deregistered node {node_id}")

    def update_node_status(self, node_id: str, status: NodeStatus):
        """Update a node's status."""
        with self._lock:
            if node_id in self.nodes:
                self.nodes[node_id].status = status
                self.nodes[node_id].last_heartbeat = time.time()

                for callback in self.node_change_callbacks:
                    try:
                        callback(node_id, status)
                    except Exception as e:
                        logger.error(f"Node change callback error: {e}")

    def get_nodes_for_key(self, key: str) -> List[str]:
        """Get the nodes responsible for a key."""
        return self.hash_ring.get_nodes(key, self.replication_factor + 1)

    def get_primary_node(self, key: str) -> Optional[str]:
        """Get the primary node for a key."""
        return self.hash_ring.get_node(key)

    def is_local_key(self, key: str) -> bool:
        """Check if a key belongs to the local node."""
        primary = self.get_primary_node(key)
        return primary == self.node_id

    async def coordinate_write(self, key: str, value: bytes, ttl_seconds: Optional[int] = None) -> bool:
        """Coordinate a write operation across nodes."""
        nodes = self.get_nodes_for_key(key)
        if not nodes:
            return False

        event = ReplicationEvent(
            event_id=f"{key}:{time.time()}",
            key=key,
            operation="set",
            value=value,
            source_node=self.node_id,
            ttl_seconds=ttl_seconds,
        )

        # Replicate based on strategy
        if self.replication_manager.strategy == ReplicationStrategy.SYNC:
            success_count = await self.replication_manager.replicate_sync(event, nodes)
            return success_count >= 1
        elif self.replication_manager.strategy == ReplicationStrategy.QUORUM:
            return await self.replication_manager.replicate_quorum(event, nodes)
        else:  # ASYNC
            self.replication_manager.queue_replication(event, nodes[1:])  # Exclude primary
            return True

    async def coordinate_delete(self, key: str) -> bool:
        """Coordinate a delete operation across nodes."""
        nodes = self.get_nodes_for_key(key)
        if not nodes:
            return False

        event = ReplicationEvent(
            event_id=f"{key}:{time.time()}",
            key=key,
            operation="delete",
            source_node=self.node_id,
        )

        if self.replication_manager.strategy in (ReplicationStrategy.SYNC, ReplicationStrategy.QUORUM):
            success_count = await self.replication_manager.replicate_sync(event, nodes)
            return success_count >= 1
        else:
            self.replication_manager.queue_replication(event, nodes[1:])
            return True

    def _notify_rebalance(self, changes: Dict[int, Tuple[str, List[str]]]):
        """Notify callbacks of partition rebalance."""
        for callback in self.rebalance_callbacks:
            try:
                callback(changes)
            except Exception as e:
                logger.error(f"Rebalance callback error: {e}")

    def register_node_callback(self, callback: Callable[[str, NodeStatus], None]):
        """Register a callback for node changes."""
        self.node_change_callbacks.append(callback)

    def register_rebalance_callback(self, callback: Callable[[Dict[int, Tuple[str, List[str]]]], None]):
        """Register a callback for rebalance events."""
        self.rebalance_callbacks.append(callback)

    async def start_heartbeat(self, interval_seconds: float = 5.0):
        """Start heartbeat loop."""
        if self._running:
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval_seconds))
        await self.replication_manager.start_replication_loop()
        logger.info("Coordinator heartbeat started")

    async def stop_heartbeat(self):
        """Stop heartbeat loop."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        await self.replication_manager.stop_replication_loop()
        logger.info("Coordinator heartbeat stopped")

    async def _heartbeat_loop(self, interval_seconds: float):
        """Background heartbeat loop."""
        while self._running:
            try:
                await asyncio.sleep(interval_seconds)

                # Check for failed nodes
                current_time = time.time()
                timeout = interval_seconds * 3

                with self._lock:
                    for node_id, node in list(self.nodes.items()):
                        if node_id == self.node_id:
                            continue

                        if node.last_heartbeat and current_time - node.last_heartbeat > timeout:
                            if node.status == NodeStatus.ONLINE:
                                self.update_node_status(node_id, NodeStatus.DEGRADED)
                        elif current_time - (node.last_heartbeat or 0) > timeout * 2:
                            self.update_node_status(node_id, NodeStatus.OFFLINE)

                # Update local node heartbeat
                if self.local_node:
                    self.local_node.last_heartbeat = current_time

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")

    def get_cluster_stats(self) -> Dict[str, Any]:
        """Get cluster statistics."""
        with self._lock:
            online_nodes = sum(1 for n in self.nodes.values() if n.status == NodeStatus.ONLINE)

            total_capacity = sum(n.capacity_mb for n in self.nodes.values())
            total_used = sum(n.used_mb for n in self.nodes.values())

            return {
                "node_id": self.node_id,
                "total_nodes": len(self.nodes),
                "online_nodes": online_nodes,
                "replication_factor": self.replication_factor,
                "total_capacity_mb": total_capacity,
                "total_used_mb": total_used,
                "cluster_utilization": total_used / total_capacity if total_capacity > 0 else 0,
                "partition_stats": self.partition_manager.get_stats(),
                "replication_stats": self.replication_manager.get_stats(),
                "nodes": [
                    {
                        "node_id": n.node_id,
                        "status": n.status.value,
                        "host": n.host,
                        "port": n.port,
                        "zone": n.zone,
                        "utilization": n.utilization,
                    }
                    for n in self.nodes.values()
                ],
            }
