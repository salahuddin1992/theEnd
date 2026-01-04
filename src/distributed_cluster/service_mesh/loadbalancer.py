"""
Load balancing implementations for service mesh.
"""

import hashlib
import logging
import random
import threading
import time
from abc import ABC, abstractmethod
from bisect import bisect_left, insort
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .discovery import ServiceInstance

logger = logging.getLogger(__name__)


@dataclass
class LoadBalancerStats:
    """Statistics for load balancer."""
    requests: int = 0
    successful: int = 0
    failed: int = 0
    instance_requests: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    instance_errors: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    avg_response_time_ms: float = 0.0
    _response_times: List[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_request(self, instance_id: str, success: bool, response_time_ms: float = 0):
        with self._lock:
            self.requests += 1
            self.instance_requests[instance_id] += 1

            if success:
                self.successful += 1
            else:
                self.failed += 1
                self.instance_errors[instance_id] += 1

            if response_time_ms > 0:
                self._response_times.append(response_time_ms)
                if len(self._response_times) > 1000:
                    self._response_times = self._response_times[-1000:]
                self.avg_response_time_ms = sum(self._response_times) / len(self._response_times)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "requests": self.requests,
                "successful": self.successful,
                "failed": self.failed,
                "success_rate": self.successful / self.requests if self.requests > 0 else 0,
                "avg_response_time_ms": self.avg_response_time_ms,
                "instance_requests": dict(self.instance_requests),
                "instance_errors": dict(self.instance_errors),
            }


class LoadBalancer(ABC):
    """Abstract base class for load balancers."""

    def __init__(self):
        self.stats = LoadBalancerStats()
        self._instances: List[ServiceInstance] = []
        self._lock = threading.RLock()

    def update_instances(self, instances: List[ServiceInstance]):
        """Update the list of available instances."""
        with self._lock:
            self._instances = [i for i in instances if i.is_healthy]

    @abstractmethod
    def select(self) -> Optional[ServiceInstance]:
        """Select an instance for the next request."""
        pass

    def record_result(
        self,
        instance: ServiceInstance,
        success: bool,
        response_time_ms: float = 0
    ):
        """Record the result of a request."""
        self.stats.record_request(instance.instance_id, success, response_time_ms)

    def get_stats(self) -> Dict[str, Any]:
        """Get load balancer statistics."""
        return self.stats.to_dict()


class RoundRobinBalancer(LoadBalancer):
    """Round-robin load balancer."""

    def __init__(self):
        super().__init__()
        self._index = 0

    def select(self) -> Optional[ServiceInstance]:
        with self._lock:
            if not self._instances:
                return None

            instance = self._instances[self._index % len(self._instances)]
            self._index += 1
            return instance


class LeastConnectionsBalancer(LoadBalancer):
    """Least connections load balancer."""

    def __init__(self):
        super().__init__()
        self._connections: Dict[str, int] = defaultdict(int)

    def select(self) -> Optional[ServiceInstance]:
        with self._lock:
            if not self._instances:
                return None

            # Find instance with least connections
            min_conn = float('inf')
            selected = None

            for instance in self._instances:
                conn_count = self._connections[instance.instance_id]
                if conn_count < min_conn:
                    min_conn = conn_count
                    selected = instance

            if selected:
                self._connections[selected.instance_id] += 1

            return selected

    def release(self, instance: ServiceInstance):
        """Release a connection from an instance."""
        with self._lock:
            if self._connections[instance.instance_id] > 0:
                self._connections[instance.instance_id] -= 1


class WeightedBalancer(LoadBalancer):
    """Weighted load balancer based on instance weights."""

    def __init__(self):
        super().__init__()
        self._cumulative_weights: List[Tuple[int, ServiceInstance]] = []

    def update_instances(self, instances: List[ServiceInstance]):
        with self._lock:
            super().update_instances(instances)
            self._build_weights()

    def _build_weights(self):
        """Build cumulative weight distribution."""
        self._cumulative_weights = []
        cumulative = 0

        for instance in self._instances:
            cumulative += instance.weight
            self._cumulative_weights.append((cumulative, instance))

    def select(self) -> Optional[ServiceInstance]:
        with self._lock:
            if not self._cumulative_weights:
                return None

            total_weight = self._cumulative_weights[-1][0]
            rand = random.randint(1, total_weight)

            for weight, instance in self._cumulative_weights:
                if rand <= weight:
                    return instance

            return self._cumulative_weights[-1][1]


class ConsistentHashBalancer(LoadBalancer):
    """Consistent hash load balancer for sticky sessions."""

    def __init__(self, virtual_nodes: int = 150):
        super().__init__()
        self.virtual_nodes = virtual_nodes
        self._ring: List[Tuple[int, ServiceInstance]] = []

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def update_instances(self, instances: List[ServiceInstance]):
        with self._lock:
            super().update_instances(instances)
            self._build_ring()

    def _build_ring(self):
        """Build the hash ring."""
        self._ring = []

        for instance in self._instances:
            for i in range(self.virtual_nodes * instance.weight):
                key = f"{instance.instance_id}:{i}"
                hash_value = self._hash(key)
                insort(self._ring, (hash_value, instance))

    def select(self, key: Optional[str] = None) -> Optional[ServiceInstance]:
        with self._lock:
            if not self._ring:
                return None

            if key is None:
                key = str(time.time())

            hash_value = self._hash(key)

            # Find first node with hash >= key hash
            idx = bisect_left(self._ring, (hash_value,))
            if idx >= len(self._ring):
                idx = 0

            return self._ring[idx][1]


class HealthAwareBalancer(LoadBalancer):
    """
    Health-aware load balancer that considers instance health scores.

    Combines round-robin with health-based weighting.
    """

    def __init__(
        self,
        health_check_interval: float = 5.0,
        error_threshold: int = 5,
        recovery_time: float = 30.0
    ):
        super().__init__()
        self._health_scores: Dict[str, float] = {}  # 0.0 to 1.0
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._last_error_time: Dict[str, float] = {}
        self._index = 0
        self.error_threshold = error_threshold
        self.recovery_time = recovery_time

    def update_instances(self, instances: List[ServiceInstance]):
        with self._lock:
            super().update_instances(instances)

            # Initialize health scores for new instances
            for instance in self._instances:
                if instance.instance_id not in self._health_scores:
                    self._health_scores[instance.instance_id] = 1.0

    def select(self) -> Optional[ServiceInstance]:
        with self._lock:
            if not self._instances:
                return None

            # Filter by minimum health score
            healthy = [
                i for i in self._instances
                if self._health_scores.get(i.instance_id, 1.0) > 0.1
            ]

            if not healthy:
                # Fall back to all instances if none are healthy enough
                healthy = self._instances

            # Weighted selection by health score
            total_weight = sum(
                self._health_scores.get(i.instance_id, 1.0) * i.weight
                for i in healthy
            )

            if total_weight <= 0:
                return healthy[self._index % len(healthy)]

            rand = random.uniform(0, total_weight)
            cumulative = 0

            for instance in healthy:
                weight = self._health_scores.get(instance.instance_id, 1.0) * instance.weight
                cumulative += weight
                if rand <= cumulative:
                    return instance

            return healthy[-1]

    def record_result(
        self,
        instance: ServiceInstance,
        success: bool,
        response_time_ms: float = 0
    ):
        super().record_result(instance, success, response_time_ms)

        with self._lock:
            if success:
                # Gradually increase health score on success
                current = self._health_scores.get(instance.instance_id, 1.0)
                self._health_scores[instance.instance_id] = min(1.0, current + 0.1)
                self._error_counts[instance.instance_id] = 0
            else:
                # Decrease health score on failure
                self._error_counts[instance.instance_id] += 1
                self._last_error_time[instance.instance_id] = time.time()

                if self._error_counts[instance.instance_id] >= self.error_threshold:
                    # Mark as unhealthy
                    self._health_scores[instance.instance_id] = 0.0
                else:
                    current = self._health_scores.get(instance.instance_id, 1.0)
                    self._health_scores[instance.instance_id] = max(0.1, current - 0.2)

    def recover_instances(self):
        """Attempt to recover unhealthy instances."""
        now = time.time()
        with self._lock:
            for instance_id, last_error in list(self._last_error_time.items()):
                if now - last_error > self.recovery_time:
                    if self._health_scores.get(instance_id, 1.0) < 1.0:
                        self._health_scores[instance_id] = 0.5  # Partial recovery
                        self._error_counts[instance_id] = 0

    def get_health_scores(self) -> Dict[str, float]:
        """Get health scores for all instances."""
        with self._lock:
            return dict(self._health_scores)


class RandomBalancer(LoadBalancer):
    """Random load balancer."""

    def select(self) -> Optional[ServiceInstance]:
        with self._lock:
            if not self._instances:
                return None
            return random.choice(self._instances)


class ZoneAwareBalancer(LoadBalancer):
    """Zone-aware load balancer that prefers local zone."""

    def __init__(self, local_zone: str, fallback_balancer: Optional[LoadBalancer] = None):
        super().__init__()
        self.local_zone = local_zone
        self._fallback = fallback_balancer or RoundRobinBalancer()
        self._local_instances: List[ServiceInstance] = []
        self._remote_instances: List[ServiceInstance] = []
        self._local_index = 0
        self._remote_index = 0

    def update_instances(self, instances: List[ServiceInstance]):
        with self._lock:
            super().update_instances(instances)
            self._local_instances = [i for i in self._instances if i.zone == self.local_zone]
            self._remote_instances = [i for i in self._instances if i.zone != self.local_zone]

    def select(self) -> Optional[ServiceInstance]:
        with self._lock:
            # Prefer local zone (90% of requests)
            if self._local_instances and random.random() < 0.9:
                instance = self._local_instances[self._local_index % len(self._local_instances)]
                self._local_index += 1
                return instance

            # Fall back to remote instances
            if self._remote_instances:
                instance = self._remote_instances[self._remote_index % len(self._remote_instances)]
                self._remote_index += 1
                return instance

            # Last resort: any local instance
            if self._local_instances:
                return self._local_instances[self._local_index % len(self._local_instances)]

            return None


class LoadBalancerFactory:
    """Factory for creating load balancers."""

    _balancers: Dict[str, type] = {
        "round_robin": RoundRobinBalancer,
        "least_connections": LeastConnectionsBalancer,
        "weighted": WeightedBalancer,
        "consistent_hash": ConsistentHashBalancer,
        "health_aware": HealthAwareBalancer,
        "random": RandomBalancer,
    }

    @classmethod
    def create(cls, algorithm: str, **kwargs) -> LoadBalancer:
        """Create a load balancer."""
        balancer_class = cls._balancers.get(algorithm.lower())
        if not balancer_class:
            raise ValueError(f"Unknown load balancer algorithm: {algorithm}")
        return balancer_class(**kwargs)

    @classmethod
    def register(cls, name: str, balancer_class: type):
        """Register a new load balancer type."""
        cls._balancers[name.lower()] = balancer_class
