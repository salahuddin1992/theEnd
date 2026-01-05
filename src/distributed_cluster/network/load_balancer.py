# -*- coding: utf-8 -*-
"""
Smart Load Balancer for NebulaCompute.

نظام موازنة الحمل الذكي.

Supports multiple algorithms:
- Round Robin
- Least Connections
- IP Hash
- Weighted Round Robin
- Least Response Time
- Random
"""

import asyncio
import hashlib
import logging
import random
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LoadBalancerAlgorithm(str, Enum):
    """Load balancer algorithm types."""

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    IP_HASH = "ip_hash"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_RESPONSE_TIME = "least_response_time"
    RANDOM = "random"
    CONSISTENT_HASH = "consistent_hash"


class BackendStatus(str, Enum):
    """Backend server status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"
    MAINTENANCE = "maintenance"


@dataclass
class Backend:
    """
    Backend server representation.

    تمثيل خادم خلفي.
    """

    id: str
    host: str
    port: int
    weight: int = 1
    max_connections: int = 1000
    status: BackendStatus = BackendStatus.HEALTHY
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Runtime stats
    current_connections: int = 0
    total_requests: int = 0
    total_failures: int = 0
    avg_response_time_ms: float = 0.0
    last_health_check: Optional[datetime] = None

    @property
    def address(self) -> str:
        """Get backend address."""
        return f"{self.host}:{self.port}"

    @property
    def is_available(self) -> bool:
        """Check if backend is available."""
        return self.status == BackendStatus.HEALTHY and self.current_connections < self.max_connections

    @property
    def connection_ratio(self) -> float:
        """Get connection ratio (0-1)."""
        return self.current_connections / self.max_connections if self.max_connections > 0 else 1.0

    @property
    def success_rate(self) -> float:
        """Get request success rate."""
        if self.total_requests == 0:
            return 1.0
        return (self.total_requests - self.total_failures) / self.total_requests

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "host": self.host,
            "port": self.port,
            "weight": self.weight,
            "max_connections": self.max_connections,
            "status": self.status.value,
            "current_connections": self.current_connections,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "avg_response_time_ms": self.avg_response_time_ms,
            "success_rate": self.success_rate,
            "metadata": self.metadata,
        }


@dataclass
class LoadBalancerStats:
    """Load balancer statistics."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time_ms: float = 0.0
    backends_healthy: int = 0
    backends_unhealthy: int = 0

    @property
    def avg_response_time_ms(self) -> float:
        """Average response time."""
        if self.total_requests == 0:
            return 0.0
        return self.total_response_time_ms / self.total_requests

    @property
    def success_rate(self) -> float:
        """Request success rate."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests


class LoadBalancerStrategy(ABC):
    """
    Abstract base class for load balancing strategies.

    فئة أساسية مجردة لاستراتيجيات موازنة الحمل.
    """

    @abstractmethod
    def select(
        self,
        backends: List[Backend],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Backend]:
        """Select a backend server."""
        pass

    @abstractmethod
    def name(self) -> str:
        """Strategy name."""
        pass


class RoundRobinStrategy(LoadBalancerStrategy):
    """
    Round Robin load balancing.

    موازنة الحمل الدورية.

    يختار الخوادم بالتناوب.
    Selects backends in circular order.
    """

    def __init__(self):
        self._index = 0
        self._lock = asyncio.Lock()

    def name(self) -> str:
        return "round_robin"

    def select(
        self,
        backends: List[Backend],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Backend]:
        available = [b for b in backends if b.is_available]
        if not available:
            return None

        backend = available[self._index % len(available)]
        self._index = (self._index + 1) % len(available)
        return backend


class WeightedRoundRobinStrategy(LoadBalancerStrategy):
    """
    Weighted Round Robin load balancing.

    موازنة الحمل الدورية المرجحة.

    يختار الخوادم بناءً على أوزانها.
    Selects backends based on their weights.
    """

    def __init__(self):
        self._current_weights: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    def name(self) -> str:
        return "weighted_round_robin"

    def select(
        self,
        backends: List[Backend],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Backend]:
        available = [b for b in backends if b.is_available]
        if not available:
            return None

        # Initialize weights
        for b in available:
            if b.id not in self._current_weights:
                self._current_weights[b.id] = 0

        # Smooth Weighted Round Robin
        total_weight = sum(b.weight for b in available)

        # Add weight to current weight
        for b in available:
            self._current_weights[b.id] += b.weight

        # Select backend with highest current weight
        selected = max(available, key=lambda b: self._current_weights[b.id])

        # Subtract total weight from selected
        self._current_weights[selected.id] -= total_weight

        return selected


class LeastConnectionsStrategy(LoadBalancerStrategy):
    """
    Least Connections load balancing.

    موازنة الحمل بأقل الاتصالات.

    يختار الخادم ذو أقل عدد من الاتصالات النشطة.
    Selects the backend with fewest active connections.
    """

    def name(self) -> str:
        return "least_connections"

    def select(
        self,
        backends: List[Backend],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Backend]:
        available = [b for b in backends if b.is_available]
        if not available:
            return None

        # Select backend with least connections
        # Consider weight: effective_connections = connections / weight
        return min(available, key=lambda b: b.current_connections / b.weight if b.weight > 0 else float("inf"))


class IPHashStrategy(LoadBalancerStrategy):
    """
    IP Hash load balancing.

    موازنة الحمل بتجزئة IP.

    يستخدم عنوان IP للعميل لاختيار الخادم.
    Uses client IP to consistently select the same backend.
    """

    def name(self) -> str:
        return "ip_hash"

    def select(
        self,
        backends: List[Backend],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Backend]:
        available = [b for b in backends if b.is_available]
        if not available:
            return None

        # Get client IP from context
        client_ip = "0.0.0.0"
        if request_context:
            client_ip = request_context.get("client_ip", "0.0.0.0")

        # Hash the IP
        hash_value = int(hashlib.md5(client_ip.encode(), usedforsecurity=False).hexdigest(), 16)

        # Select backend based on hash
        index = hash_value % len(available)
        return available[index]


class LeastResponseTimeStrategy(LoadBalancerStrategy):
    """
    Least Response Time load balancing.

    موازنة الحمل بأقل وقت استجابة.

    يختار الخادم ذو أقل متوسط وقت استجابة.
    Selects the backend with lowest average response time.
    """

    def name(self) -> str:
        return "least_response_time"

    def select(
        self,
        backends: List[Backend],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Backend]:
        available = [b for b in backends if b.is_available]
        if not available:
            return None

        # Select backend with lowest response time
        # Weight factor: effective_time = response_time / weight
        return min(
            available, key=lambda b: (b.avg_response_time_ms or 1.0) / b.weight if b.weight > 0 else float("inf")
        )


class RandomStrategy(LoadBalancerStrategy):
    """
    Random load balancing.

    موازنة الحمل العشوائية.

    يختار خادم عشوائياً من الخوادم المتاحة.
    Randomly selects an available backend.
    """

    def name(self) -> str:
        return "random"

    def select(
        self,
        backends: List[Backend],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Backend]:
        available = [b for b in backends if b.is_available]
        if not available:
            return None

        # Weighted random selection
        weights = [b.weight for b in available]
        return random.choices(available, weights=weights, k=1)[0]


class ConsistentHashStrategy(LoadBalancerStrategy):
    """
    Consistent Hash load balancing.

    موازنة الحمل بالتجزئة المتسقة.

    يستخدم حلقة تجزئة متسقة لتوزيع الحمل.
    Uses consistent hashing ring for distribution.
    """

    def __init__(self, replicas: int = 100):
        self.replicas = replicas
        self._ring: Dict[int, str] = {}
        self._sorted_keys: List[int] = []

    def name(self) -> str:
        return "consistent_hash"

    def _build_ring(self, backends: List[Backend]) -> None:
        """Build the hash ring."""
        self._ring.clear()
        self._sorted_keys.clear()

        for backend in backends:
            for i in range(self.replicas):
                key = f"{backend.id}:{i}"
                hash_val = int(hashlib.md5(key.encode(), usedforsecurity=False).hexdigest(), 16)
                self._ring[hash_val] = backend.id
                self._sorted_keys.append(hash_val)

        self._sorted_keys.sort()

    def _get_backend_id(self, key: str) -> Optional[str]:
        """Get backend ID for a key."""
        if not self._ring:
            return None

        hash_val = int(hashlib.md5(key.encode(), usedforsecurity=False).hexdigest(), 16)

        # Find first node clockwise
        for ring_key in self._sorted_keys:
            if hash_val <= ring_key:
                return self._ring[ring_key]

        # Wrap around
        return self._ring[self._sorted_keys[0]]

    def select(
        self,
        backends: List[Backend],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Backend]:
        available = [b for b in backends if b.is_available]
        if not available:
            return None

        # Rebuild ring if backends changed
        current_ids = set(b.id for b in available)
        ring_ids = set(self._ring.values())
        if current_ids != ring_ids:
            self._build_ring(available)

        # Get request key
        request_key = "default"
        if request_context:
            request_key = request_context.get("request_key", request_context.get("client_ip", "default"))

        # Find backend
        backend_id = self._get_backend_id(request_key)
        if backend_id:
            for b in available:
                if b.id == backend_id:
                    return b

        return available[0] if available else None


class LoadBalancer:
    """
    Smart Load Balancer.

    موازن الحمل الذكي.

    يدعم خوارزميات متعددة لتوزيع الحمل.
    Supports multiple algorithms for load distribution.

    Usage:
        lb = LoadBalancer(algorithm=LoadBalancerAlgorithm.LEAST_CONNECTIONS)

        lb.add_backend(Backend(id="server1", host="10.0.0.1", port=8080))
        lb.add_backend(Backend(id="server2", host="10.0.0.2", port=8080))

        backend = lb.select()
        if backend:
            # Use backend
            lb.record_request(backend.id, success=True, response_time_ms=50)
    """

    STRATEGIES: Dict[LoadBalancerAlgorithm, type] = {
        LoadBalancerAlgorithm.ROUND_ROBIN: RoundRobinStrategy,
        LoadBalancerAlgorithm.WEIGHTED_ROUND_ROBIN: WeightedRoundRobinStrategy,
        LoadBalancerAlgorithm.LEAST_CONNECTIONS: LeastConnectionsStrategy,
        LoadBalancerAlgorithm.IP_HASH: IPHashStrategy,
        LoadBalancerAlgorithm.LEAST_RESPONSE_TIME: LeastResponseTimeStrategy,
        LoadBalancerAlgorithm.RANDOM: RandomStrategy,
        LoadBalancerAlgorithm.CONSISTENT_HASH: ConsistentHashStrategy,
    }

    def __init__(
        self,
        algorithm: LoadBalancerAlgorithm = LoadBalancerAlgorithm.ROUND_ROBIN,
        health_check_interval: float = 30.0,
        health_check_timeout: float = 5.0,
        health_check_path: str = "/health",
        max_failures_before_unhealthy: int = 3,
        recovery_check_interval: float = 60.0,
    ):
        """
        Initialize load balancer.

        Args:
            algorithm: Load balancing algorithm
            health_check_interval: Health check interval in seconds
            health_check_timeout: Health check timeout in seconds
            health_check_path: Health check endpoint path
            max_failures_before_unhealthy: Failures before marking unhealthy
            recovery_check_interval: Interval to check unhealthy backends
        """
        self.algorithm = algorithm
        self.health_check_interval = health_check_interval
        self.health_check_timeout = health_check_timeout
        self.health_check_path = health_check_path
        self.max_failures_before_unhealthy = max_failures_before_unhealthy
        self.recovery_check_interval = recovery_check_interval

        self._backends: Dict[str, Backend] = {}
        self._strategy: LoadBalancerStrategy = self.STRATEGIES[algorithm]()
        self._stats = LoadBalancerStats()
        self._lock = asyncio.Lock()
        self._failure_counts: Dict[str, int] = defaultdict(int)
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False

    def add_backend(self, backend: Backend) -> None:
        """
        Add a backend server.

        إضافة خادم خلفي.
        """
        self._backends[backend.id] = backend
        logger.info(f"Added backend: {backend.id} ({backend.address})")

    def remove_backend(self, backend_id: str) -> bool:
        """
        Remove a backend server.

        إزالة خادم خلفي.
        """
        if backend_id in self._backends:
            del self._backends[backend_id]
            logger.info(f"Removed backend: {backend_id}")
            return True
        return False

    def get_backend(self, backend_id: str) -> Optional[Backend]:
        """Get a backend by ID."""
        return self._backends.get(backend_id)

    def get_backends(self) -> List[Backend]:
        """Get all backends."""
        return list(self._backends.values())

    def select(
        self,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Backend]:
        """
        Select a backend for the request.

        اختيار خادم للطلب.

        Args:
            request_context: Request context (client_ip, request_key, etc.)

        Returns:
            Selected backend or None if no backends available
        """
        backends = list(self._backends.values())
        if not backends:
            return None

        backend = self._strategy.select(backends, request_context)

        if backend:
            backend.current_connections += 1
            backend.total_requests += 1
            self._stats.total_requests += 1

        return backend

    def release(self, backend_id: str) -> None:
        """
        Release a connection from a backend.

        تحرير اتصال من خادم.
        """
        if backend_id in self._backends:
            backend = self._backends[backend_id]
            if backend.current_connections > 0:
                backend.current_connections -= 1

    def record_request(
        self,
        backend_id: str,
        success: bool,
        response_time_ms: float,
    ) -> None:
        """
        Record a request result.

        تسجيل نتيجة طلب.

        Args:
            backend_id: Backend ID
            success: Whether request succeeded
            response_time_ms: Response time in milliseconds
        """
        if backend_id not in self._backends:
            return

        backend = self._backends[backend_id]

        # Update response time (exponential moving average)
        alpha = 0.3  # Smoothing factor
        if backend.avg_response_time_ms == 0:
            backend.avg_response_time_ms = response_time_ms
        else:
            backend.avg_response_time_ms = alpha * response_time_ms + (1 - alpha) * backend.avg_response_time_ms

        # Update stats
        self._stats.total_response_time_ms += response_time_ms

        if success:
            self._stats.successful_requests += 1
            self._failure_counts[backend_id] = 0
        else:
            backend.total_failures += 1
            self._stats.failed_requests += 1
            self._failure_counts[backend_id] += 1

            # Check if backend should be marked unhealthy
            if self._failure_counts[backend_id] >= self.max_failures_before_unhealthy:
                self._mark_unhealthy(backend_id)

    def _mark_unhealthy(self, backend_id: str) -> None:
        """Mark a backend as unhealthy."""
        if backend_id in self._backends:
            backend = self._backends[backend_id]
            backend.status = BackendStatus.UNHEALTHY
            logger.warning(f"Backend marked unhealthy: {backend_id}")
            self._update_health_stats()

    def _mark_healthy(self, backend_id: str) -> None:
        """Mark a backend as healthy."""
        if backend_id in self._backends:
            backend = self._backends[backend_id]
            backend.status = BackendStatus.HEALTHY
            self._failure_counts[backend_id] = 0
            logger.info(f"Backend marked healthy: {backend_id}")
            self._update_health_stats()

    def _update_health_stats(self) -> None:
        """Update health statistics."""
        healthy = sum(1 for b in self._backends.values() if b.status == BackendStatus.HEALTHY)
        unhealthy = len(self._backends) - healthy
        self._stats.backends_healthy = healthy
        self._stats.backends_unhealthy = unhealthy

    async def start_health_checks(self) -> None:
        """Start health check background task."""
        if self._running:
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Health checks started")

    async def stop_health_checks(self) -> None:
        """Stop health check background task."""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("Health checks stopped")

    async def _health_check_loop(self) -> None:
        """Health check loop."""
        while self._running:
            try:
                await self._check_all_backends()
            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(self.health_check_interval)

    async def _check_all_backends(self) -> None:
        """Check health of all backends."""
        tasks = []
        for backend in self._backends.values():
            tasks.append(self._check_backend_health(backend))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_backend_health(self, backend: Backend) -> None:
        """Check health of a single backend."""
        import aiohttp

        url = f"http://{backend.host}:{backend.port}{self.health_check_path}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.health_check_timeout),
                ) as response:
                    if response.status == 200:
                        if backend.status == BackendStatus.UNHEALTHY:
                            self._mark_healthy(backend.id)
                        backend.last_health_check = datetime.now()
                    else:
                        self._failure_counts[backend.id] += 1
                        if self._failure_counts[backend.id] >= self.max_failures_before_unhealthy:
                            self._mark_unhealthy(backend.id)

        except ImportError:
            # aiohttp not available, skip health checks
            pass
        except Exception:
            self._failure_counts[backend.id] += 1
            if self._failure_counts[backend.id] >= self.max_failures_before_unhealthy:
                self._mark_unhealthy(backend.id)

    def set_algorithm(self, algorithm: LoadBalancerAlgorithm) -> None:
        """Change load balancing algorithm."""
        self.algorithm = algorithm
        self._strategy = self.STRATEGIES[algorithm]()
        logger.info(f"Load balancer algorithm changed to: {algorithm.value}")

    def drain_backend(self, backend_id: str) -> bool:
        """
        Start draining a backend (stop accepting new connections).

        بدء تفريغ خادم (إيقاف قبول اتصالات جديدة).
        """
        if backend_id in self._backends:
            self._backends[backend_id].status = BackendStatus.DRAINING
            logger.info(f"Backend draining: {backend_id}")
            return True
        return False

    def maintenance_backend(self, backend_id: str) -> bool:
        """
        Put backend in maintenance mode.

        وضع الخادم في وضع الصيانة.
        """
        if backend_id in self._backends:
            self._backends[backend_id].status = BackendStatus.MAINTENANCE
            logger.info(f"Backend in maintenance: {backend_id}")
            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get load balancer statistics."""
        self._update_health_stats()
        return {
            "algorithm": self.algorithm.value,
            "total_backends": len(self._backends),
            "backends_healthy": self._stats.backends_healthy,
            "backends_unhealthy": self._stats.backends_unhealthy,
            "total_requests": self._stats.total_requests,
            "successful_requests": self._stats.successful_requests,
            "failed_requests": self._stats.failed_requests,
            "success_rate": self._stats.success_rate,
            "avg_response_time_ms": self._stats.avg_response_time_ms,
            "backends": [b.to_dict() for b in self._backends.values()],
        }


class LoadBalancerPool:
    """
    Load Balancer Pool - manages multiple load balancers.

    مجموعة موازنات الحمل - يدير موازنات متعددة.

    Usage:
        pool = LoadBalancerPool()

        pool.create("api", algorithm=LoadBalancerAlgorithm.LEAST_CONNECTIONS)
        pool.create("websocket", algorithm=LoadBalancerAlgorithm.IP_HASH)

        lb = pool.get("api")
        lb.add_backend(Backend(...))
    """

    def __init__(self):
        self._balancers: Dict[str, LoadBalancer] = {}

    def create(
        self,
        name: str,
        algorithm: LoadBalancerAlgorithm = LoadBalancerAlgorithm.ROUND_ROBIN,
        **kwargs,
    ) -> LoadBalancer:
        """Create a new load balancer."""
        lb = LoadBalancer(algorithm=algorithm, **kwargs)
        self._balancers[name] = lb
        return lb

    def get(self, name: str) -> Optional[LoadBalancer]:
        """Get a load balancer by name."""
        return self._balancers.get(name)

    def remove(self, name: str) -> bool:
        """Remove a load balancer."""
        if name in self._balancers:
            del self._balancers[name]
            return True
        return False

    def list(self) -> List[str]:
        """List all load balancer names."""
        return list(self._balancers.keys())

    async def start_all(self) -> None:
        """Start health checks for all load balancers."""
        for lb in self._balancers.values():
            await lb.start_health_checks()

    async def stop_all(self) -> None:
        """Stop health checks for all load balancers."""
        for lb in self._balancers.values():
            await lb.stop_health_checks()


# Global load balancer pool
load_balancer_pool = LoadBalancerPool()


def get_load_balancer(name: str = "default") -> Optional[LoadBalancer]:
    """Get load balancer from global pool."""
    return load_balancer_pool.get(name)


def create_load_balancer(
    name: str = "default",
    algorithm: LoadBalancerAlgorithm = LoadBalancerAlgorithm.ROUND_ROBIN,
    **kwargs,
) -> LoadBalancer:
    """Create and register a load balancer."""
    return load_balancer_pool.create(name, algorithm, **kwargs)
