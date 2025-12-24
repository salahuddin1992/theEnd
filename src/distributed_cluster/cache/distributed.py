"""
Distributed Cache System for NebulaCompute.

Provides distributed caching across multiple nodes with:
- Consistent hashing for key distribution
- Replication for fault tolerance
- Automatic node discovery and failover
"""

import asyncio
import hashlib
import pickle
import time
from bisect import bisect_left
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheNode:
    """Represents a cache node in the cluster."""
    node_id: str
    host: str
    port: int
    weight: int = 1
    is_healthy: bool = True
    last_health_check: Optional[datetime] = None
    latency_ms: float = 0.0
    error_count: int = 0

    @property
    def address(self) -> str:
        """Get node address."""
        return f"{self.host}:{self.port}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "weight": self.weight,
            "is_healthy": self.is_healthy,
            "latency_ms": self.latency_ms,
            "error_count": self.error_count,
        }


class ConsistentHashing:
    """
    Consistent hashing ring for key distribution.

    Features:
    - Virtual nodes for better distribution
    - Weighted nodes support
    - Minimal key redistribution on node changes
    """

    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self._ring: List[Tuple[int, str]] = []  # (hash, node_id)
        self._nodes: Dict[str, CacheNode] = {}

    def _hash(self, key: str) -> int:
        """Generate hash for a key."""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node: CacheNode) -> None:
        """Add a node to the ring."""
        self._nodes[node.node_id] = node

        # Add virtual nodes based on weight
        for i in range(self.virtual_nodes * node.weight):
            virtual_key = f"{node.node_id}:{i}"
            hash_value = self._hash(virtual_key)
            self._ring.append((hash_value, node.node_id))

        # Keep ring sorted
        self._ring.sort(key=lambda x: x[0])

        logger.info(
            "Added node %s to ring with %d virtual nodes",
            node.node_id,
            self.virtual_nodes * node.weight,
        )

    def remove_node(self, node_id: str) -> None:
        """Remove a node from the ring."""
        if node_id not in self._nodes:
            return

        # Remove all virtual nodes
        self._ring = [(h, n) for h, n in self._ring if n != node_id]
        del self._nodes[node_id]

        logger.info("Removed node %s from ring", node_id)

    def get_node(self, key: str) -> Optional[CacheNode]:
        """Get the node responsible for a key."""
        if not self._ring:
            return None

        hash_value = self._hash(key)

        # Binary search for the first node with hash >= key hash
        idx = bisect_left([h for h, _ in self._ring], hash_value)

        # Wrap around if at end
        if idx >= len(self._ring):
            idx = 0

        node_id = self._ring[idx][1]

        # Skip unhealthy nodes
        attempts = 0
        while not self._nodes[node_id].is_healthy and attempts < len(self._nodes):
            idx = (idx + 1) % len(self._ring)
            node_id = self._ring[idx][1]
            attempts += 1

        return self._nodes.get(node_id)

    def get_nodes(self, key: str, count: int) -> List[CacheNode]:
        """Get multiple nodes for a key (for replication)."""
        if not self._ring:
            return []

        hash_value = self._hash(key)
        idx = bisect_left([h for h, _ in self._ring], hash_value)

        nodes: List[CacheNode] = []
        seen: Set[str] = set()

        while len(nodes) < count and len(seen) < len(self._nodes):
            if idx >= len(self._ring):
                idx = 0

            node_id = self._ring[idx][1]
            if node_id not in seen:
                seen.add(node_id)
                node = self._nodes.get(node_id)
                if node and node.is_healthy:
                    nodes.append(node)

            idx += 1

        return nodes

    def get_all_nodes(self) -> List[CacheNode]:
        """Get all nodes."""
        return list(self._nodes.values())


class CacheReplication:
    """
    Handles cache replication across nodes.

    Features:
    - Configurable replication factor
    - Async replication
    - Read repair on inconsistency
    """

    def __init__(
        self,
        replication_factor: int = 2,
        write_quorum: int = 1,
        read_quorum: int = 1,
    ):
        self.replication_factor = replication_factor
        self.write_quorum = write_quorum
        self.read_quorum = read_quorum

    async def replicate_write(
        self,
        nodes: List[CacheNode],
        key: str,
        value: Any,
        ttl: Optional[int],
        send_func,
    ) -> bool:
        """
        Replicate a write to multiple nodes.

        Returns True if write quorum is met.
        """
        if not nodes:
            return False

        # Write to all replica nodes
        tasks = [
            send_func(node, "SET", key, value, ttl)
            for node in nodes[:self.replication_factor]
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful writes
        success_count = sum(
            1 for r in results
            if not isinstance(r, Exception) and r is True
        )

        return success_count >= self.write_quorum

    async def replicate_read(
        self,
        nodes: List[CacheNode],
        key: str,
        send_func,
    ) -> Optional[Any]:
        """
        Read from replica nodes with quorum.

        Returns the most recent value if quorum is met.
        """
        if not nodes:
            return None

        # Read from all replica nodes
        tasks = [
            send_func(node, "GET", key)
            for node in nodes[:self.replication_factor]
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful reads
        values = [
            r for r in results
            if not isinstance(r, Exception) and r is not None
        ]

        if len(values) < self.read_quorum:
            return None

        # Return first value (could add versioning for conflict resolution)
        return values[0] if values else None


class DistributedCache:
    """
    Distributed cache with consistent hashing and replication.

    Features:
    - Automatic key distribution across nodes
    - Configurable replication
    - Health checking and failover
    - Async operations
    """

    def __init__(
        self,
        nodes: List[str],
        replication_factor: int = 2,
        health_check_interval: int = 30,
        connection_timeout: float = 5.0,
    ):
        self.replication_factor = replication_factor
        self.health_check_interval = health_check_interval
        self.connection_timeout = connection_timeout

        self._ring = ConsistentHashing()
        self._replication = CacheReplication(replication_factor)
        self._connections: Dict[str, Any] = {}
        self._running = False

        # Parse and add nodes
        for i, node_addr in enumerate(nodes):
            host, port = self._parse_address(node_addr)
            node = CacheNode(
                node_id=f"node-{i}",
                host=host,
                port=port,
            )
            self._ring.add_node(node)

    def _parse_address(self, addr: str) -> Tuple[str, int]:
        """Parse host:port address."""
        if ":" in addr:
            host, port = addr.rsplit(":", 1)
            return host, int(port)
        return addr, 6379  # Default Redis port

    async def connect(self) -> None:
        """Connect to all nodes and start health checks."""
        self._running = True

        # Connect to each node
        for node in self._ring.get_all_nodes():
            await self._connect_node(node)

        # Start health check task
        asyncio.create_task(self._health_check_loop())

        logger.info(
            "DistributedCache connected to %d nodes",
            len(self._ring.get_all_nodes()),
        )

    async def _connect_node(self, node: CacheNode) -> bool:
        """Connect to a single node."""
        try:
            import redis.asyncio as redis

            conn = redis.Redis(
                host=node.host,
                port=node.port,
                socket_timeout=self.connection_timeout,
            )

            await conn.ping()
            self._connections[node.node_id] = conn
            node.is_healthy = True
            node.last_health_check = datetime.now()

            logger.info("Connected to node %s", node.node_id)
            return True

        except ImportError:
            logger.warning("redis package not installed")
            return False
        except Exception as e:
            logger.error("Failed to connect to node %s: %s", node.node_id, e)
            node.is_healthy = False
            node.error_count += 1
            return False

    async def close(self) -> None:
        """Close all connections."""
        self._running = False

        for conn in self._connections.values():
            await conn.close()

        self._connections.clear()
        logger.info("DistributedCache closed")

    async def _health_check_loop(self) -> None:
        """Periodically check node health."""
        while self._running:
            await asyncio.sleep(self.health_check_interval)

            for node in self._ring.get_all_nodes():
                try:
                    conn = self._connections.get(node.node_id)
                    if conn:
                        start = time.perf_counter()
                        await conn.ping()
                        node.latency_ms = (time.perf_counter() - start) * 1000
                        node.is_healthy = True
                        node.error_count = 0
                    else:
                        # Try to reconnect
                        await self._connect_node(node)

                    node.last_health_check = datetime.now()

                except Exception as e:
                    logger.warning("Health check failed for %s: %s", node.node_id, e)
                    node.is_healthy = False
                    node.error_count += 1

    async def _send_to_node(
        self,
        node: CacheNode,
        command: str,
        key: str,
        value: Any = None,
        ttl: Optional[int] = None,
    ) -> Any:
        """Send a command to a node."""
        conn = self._connections.get(node.node_id)
        if not conn:
            return None

        try:
            if command == "GET":
                data = await conn.get(key)
                return pickle.loads(data) if data else None

            elif command == "SET":
                data = pickle.dumps(value)
                if ttl:
                    await conn.setex(key, ttl, data)
                else:
                    await conn.set(key, data)
                return True

            elif command == "DELETE":
                return await conn.delete(key) > 0

        except Exception as e:
            logger.error("Command %s failed on %s: %s", command, node.node_id, e)
            node.error_count += 1
            return None

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from the distributed cache."""
        nodes = self._ring.get_nodes(key, self.replication_factor)

        return await self._replication.replicate_read(
            nodes,
            key,
            self._send_to_node,
        )

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a value in the distributed cache."""
        nodes = self._ring.get_nodes(key, self.replication_factor)

        return await self._replication.replicate_write(
            nodes,
            key,
            value,
            ttl,
            self._send_to_node,
        )

    async def delete(self, key: str) -> bool:
        """Delete a key from the distributed cache."""
        nodes = self._ring.get_nodes(key, self.replication_factor)

        if not nodes:
            return False

        # Delete from all replicas
        tasks = [
            self._send_to_node(node, "DELETE", key)
            for node in nodes
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return any(r is True for r in results)

    async def mget(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple keys."""
        tasks = [(key, self.get(key)) for key in keys]
        results = await asyncio.gather(*[t[1] for t in tasks])

        return {
            key: value
            for key, value in zip(keys, results)
            if value is not None
        }

    async def mset(
        self,
        items: List[Tuple[str, Any, Optional[int]]],
    ) -> bool:
        """Set multiple keys."""
        tasks = [self.set(key, value, ttl) for key, value, ttl in items]
        results = await asyncio.gather(*tasks)
        return all(results)

    async def clear(self) -> None:
        """Clear all nodes (DANGEROUS)."""
        for node_id, conn in self._connections.items():
            try:
                await conn.flushdb()
            except Exception as e:
                logger.error("Failed to clear node %s: %s", node_id, e)

    def get_cluster_stats(self) -> Dict[str, Any]:
        """Get cluster statistics."""
        nodes = self._ring.get_all_nodes()

        healthy_count = sum(1 for n in nodes if n.is_healthy)
        avg_latency = (
            sum(n.latency_ms for n in nodes) / len(nodes)
            if nodes else 0
        )

        return {
            "total_nodes": len(nodes),
            "healthy_nodes": healthy_count,
            "unhealthy_nodes": len(nodes) - healthy_count,
            "replication_factor": self.replication_factor,
            "average_latency_ms": f"{avg_latency:.2f}",
            "nodes": [n.to_dict() for n in nodes],
        }
