"""
Inference Router - موجه الاستنتاج الموزع
==========================================

Routes inference requests across multiple nodes for:
- Load balancing
- High availability
- Model sharding
- Parallel inference
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

from distributed_cluster.ai.llm.provider import (
    GenerationConfig,
    LLMProvider,
    LLMResponse,
    create_provider,
)

logger = logging.getLogger(__name__)


class RoutingStrategy(str, Enum):
    """استراتيجيات التوجيه."""

    ROUND_ROBIN = "round_robin"  # دوري
    LEAST_CONNECTIONS = "least_connections"  # أقل اتصالات
    RANDOM = "random"  # عشوائي
    WEIGHTED = "weighted"  # موزون
    HASH = "hash"  # تجزئة (للاتساق)
    LATENCY = "latency"  # أقل تأخير
    CAPACITY = "capacity"  # أعلى سعة


class NodeStatus(str, Enum):
    """حالة العقدة."""

    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    DRAINING = "draining"


@dataclass
class NodeMetrics:
    """مقاييس العقدة."""

    requests_total: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    active_requests: int = 0

    # Latency
    avg_latency_ms: float = 0
    p95_latency_ms: float = 0
    p99_latency_ms: float = 0

    # Throughput
    tokens_per_second: float = 0

    # Resources
    gpu_utilization: float = 0
    memory_used_gb: float = 0

    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class InferenceNode:
    """عقدة استنتاج."""

    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    url: str = ""
    provider_type: str = "ollama"

    # Status
    status: NodeStatus = NodeStatus.OFFLINE
    healthy: bool = False
    last_health_check: Optional[datetime] = None

    # Configuration
    models: List[str] = field(default_factory=list)
    weight: float = 1.0
    max_concurrent: int = 10
    priority: int = 50

    # Metrics
    metrics: NodeMetrics = field(default_factory=NodeMetrics)

    # Internal
    _provider: Optional[LLMProvider] = field(default=None, repr=False)

    def __post_init__(self):
        if not self.name:
            self.name = f"node-{self.node_id[:8]}"

    async def connect(self) -> bool:
        """الاتصال بالعقدة."""
        try:
            self._provider = create_provider(
                self.provider_type,
                base_url=self.url,
            )

            healthy = await self._provider.health_check()

            if healthy:
                self.status = NodeStatus.ONLINE
                self.healthy = True

                # Get available models
                models = await self._provider.list_models()
                self.models = [m.name for m in models]

            self.last_health_check = datetime.now(timezone.utc)

            return healthy

        except Exception as e:
            logger.error(f"Failed to connect to node {self.name}: {e}")
            self.status = NodeStatus.OFFLINE
            self.healthy = False
            return False

    async def disconnect(self) -> None:
        """قطع الاتصال."""
        if self._provider:
            await self._provider.close()
            self._provider = None

        self.status = NodeStatus.OFFLINE

    async def generate(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """توليد استنتاج."""
        if not self._provider:
            raise RuntimeError("Node not connected")

        start_time = time.time()
        self.metrics.active_requests += 1

        try:
            response = await self._provider.generate(
                prompt=prompt,
                model=model,
                config=config,
                system_prompt=system_prompt,
            )

            # Update metrics
            self.metrics.requests_total += 1
            self.metrics.requests_success += 1

            latency = (time.time() - start_time) * 1000
            self._update_latency(latency)

            if response.tokens_per_second > 0:
                self.metrics.tokens_per_second = 0.9 * self.metrics.tokens_per_second + 0.1 * response.tokens_per_second

            return response

        except Exception:
            self.metrics.requests_total += 1
            self.metrics.requests_failed += 1
            raise

        finally:
            self.metrics.active_requests -= 1
            self.metrics.last_updated = datetime.now(timezone.utc)

    async def generate_stream(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """توليد مع streaming."""
        if not self._provider:
            raise RuntimeError("Node not connected")

        self.metrics.active_requests += 1

        try:
            async for chunk in self._provider.generate_stream(
                prompt=prompt,
                model=model,
                config=config,
                system_prompt=system_prompt,
            ):
                yield chunk

            self.metrics.requests_total += 1
            self.metrics.requests_success += 1

        except Exception:
            self.metrics.requests_total += 1
            self.metrics.requests_failed += 1
            raise

        finally:
            self.metrics.active_requests -= 1

    def _update_latency(self, latency_ms: float) -> None:
        """تحديث إحصائيات التأخير."""
        # Exponential moving average
        alpha = 0.1
        self.metrics.avg_latency_ms = alpha * latency_ms + (1 - alpha) * self.metrics.avg_latency_ms


class LoadBalancer:
    """
    موازن الحمل.

    Distributes requests across inference nodes.
    """

    def __init__(
        self,
        strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN,
    ):
        self.strategy = strategy
        self._nodes: Dict[str, InferenceNode] = {}
        self._round_robin_index = 0
        self._lock = asyncio.Lock()

    def add_node(self, node: InferenceNode) -> None:
        """إضافة عقدة."""
        self._nodes[node.node_id] = node
        logger.info(f"Added node: {node.name} ({node.url})")

    def remove_node(self, node_id: str) -> None:
        """إزالة عقدة."""
        if node_id in self._nodes:
            del self._nodes[node_id]

    def get_healthy_nodes(self, model: Optional[str] = None) -> List[InferenceNode]:
        """الحصول على العقد السليمة."""
        nodes = [n for n in self._nodes.values() if n.healthy and n.status == NodeStatus.ONLINE]

        if model:
            nodes = [n for n in nodes if model in n.models]

        return nodes

    async def select_node(
        self,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> Optional[InferenceNode]:
        """اختيار عقدة."""
        nodes = self.get_healthy_nodes(model)

        if not nodes:
            return None

        async with self._lock:
            if self.strategy == RoutingStrategy.ROUND_ROBIN:
                return self._round_robin(nodes)

            elif self.strategy == RoutingStrategy.LEAST_CONNECTIONS:
                return self._least_connections(nodes)

            elif self.strategy == RoutingStrategy.RANDOM:
                return random.choice(nodes)

            elif self.strategy == RoutingStrategy.WEIGHTED:
                return self._weighted(nodes)

            elif self.strategy == RoutingStrategy.HASH:
                return self._hash_based(nodes, prompt or "")

            elif self.strategy == RoutingStrategy.LATENCY:
                return self._lowest_latency(nodes)

            elif self.strategy == RoutingStrategy.CAPACITY:
                return self._highest_capacity(nodes)

            else:
                return nodes[0]

    def _round_robin(self, nodes: List[InferenceNode]) -> InferenceNode:
        """اختيار دوري."""
        node = nodes[self._round_robin_index % len(nodes)]
        self._round_robin_index += 1
        return node

    def _least_connections(self, nodes: List[InferenceNode]) -> InferenceNode:
        """اختيار أقل اتصالات."""
        return min(nodes, key=lambda n: n.metrics.active_requests)

    def _weighted(self, nodes: List[InferenceNode]) -> InferenceNode:
        """اختيار موزون."""
        total_weight = sum(n.weight for n in nodes)
        r = random.uniform(0, total_weight)

        cumulative = 0
        for node in nodes:
            cumulative += node.weight
            if r <= cumulative:
                return node

        return nodes[-1]

    def _hash_based(
        self,
        nodes: List[InferenceNode],
        key: str,
    ) -> InferenceNode:
        """اختيار بالتجزئة (للاتساق)."""
        # nosec B324 - MD5 used for consistent hashing, not security
        hash_val = int(hashlib.md5(key.encode(), usedforsecurity=False).hexdigest(), 16)
        index = hash_val % len(nodes)
        return nodes[index]

    def _lowest_latency(self, nodes: List[InferenceNode]) -> InferenceNode:
        """اختيار أقل تأخير."""
        return min(nodes, key=lambda n: n.metrics.avg_latency_ms)

    def _highest_capacity(self, nodes: List[InferenceNode]) -> InferenceNode:
        """اختيار أعلى سعة."""
        return max(
            nodes,
            key=lambda n: n.max_concurrent - n.metrics.active_requests,
        )


class InferenceRouter:
    """
    موجه الاستنتاج الموزع.

    Main class for distributed inference across multiple nodes.

    Features:
    - Automatic load balancing
    - Health monitoring
    - Failover
    - Model routing
    """

    def __init__(
        self,
        strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN,
        health_check_interval: float = 30.0,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ):
        self.load_balancer = LoadBalancer(strategy)
        self.health_check_interval = health_check_interval
        self.retry_count = retry_count
        self.retry_delay = retry_delay

        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False

    async def add_node(
        self,
        url: str,
        provider_type: str = "ollama",
        name: Optional[str] = None,
        weight: float = 1.0,
        max_concurrent: int = 10,
    ) -> InferenceNode:
        """إضافة عقدة استنتاج."""
        node = InferenceNode(
            name=name or f"node-{len(self.load_balancer._nodes)}",
            url=url,
            provider_type=provider_type,
            weight=weight,
            max_concurrent=max_concurrent,
        )

        # Connect and verify
        connected = await node.connect()

        if connected:
            self.load_balancer.add_node(node)
            logger.info(f"Node {node.name} connected with models: {node.models}")
        else:
            logger.warning(f"Node {node.name} failed to connect")

        return node

    async def remove_node(self, node_id: str) -> None:
        """إزالة عقدة."""
        node = self.load_balancer._nodes.get(node_id)
        if node:
            await node.disconnect()
            self.load_balancer.remove_node(node_id)

    async def start(self) -> None:
        """بدء الموجه."""
        if self._running:
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        logger.info("Inference router started")

    async def stop(self) -> None:
        """إيقاف الموجه."""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Disconnect all nodes
        for node in list(self.load_balancer._nodes.values()):
            await node.disconnect()

        logger.info("Inference router stopped")

    async def generate(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """توليد استنتاج موزع."""
        last_error: Optional[Exception] = None

        for attempt in range(self.retry_count):
            # Select node
            node = await self.load_balancer.select_node(model=model, prompt=prompt)

            if not node:
                raise RuntimeError(f"No healthy nodes available for model: {model}")

            try:
                return await node.generate(
                    prompt=prompt,
                    model=model,
                    config=config,
                    system_prompt=system_prompt,
                )

            except Exception as e:
                last_error = e
                logger.warning(f"Node {node.name} failed (attempt {attempt + 1}): {e}")

                # Mark node as degraded
                node.healthy = False
                node.status = NodeStatus.DEGRADED

                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

        raise RuntimeError(f"All nodes failed: {last_error}")

    async def generate_stream(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """توليد مع streaming."""
        node = await self.load_balancer.select_node(model=model, prompt=prompt)

        if not node:
            raise RuntimeError(f"No healthy nodes available for model: {model}")

        async for chunk in node.generate_stream(
            prompt=prompt,
            model=model,
            config=config,
            system_prompt=system_prompt,
        ):
            yield chunk

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        config: Optional[GenerationConfig] = None,
    ) -> LLMResponse:
        """محادثة موزعة."""
        node = await self.load_balancer.select_node(model=model)

        if not node:
            raise RuntimeError(f"No healthy nodes available for model: {model}")

        if not node._provider:
            raise RuntimeError("Node not connected")

        return await node._provider.chat(
            messages=messages,
            model=model,
            config=config,
        )

    async def parallel_generate(
        self,
        prompts: List[str],
        model: str,
        config: Optional[GenerationConfig] = None,
    ) -> List[LLMResponse]:
        """توليد متوازي لعدة prompts."""
        tasks = [self.generate(prompt, model, config) for prompt in prompts]

        return await asyncio.gather(*tasks, return_exceptions=True)

    def list_nodes(self) -> List[Dict[str, Any]]:
        """قائمة العقد."""
        return [
            {
                "node_id": node.node_id,
                "name": node.name,
                "url": node.url,
                "status": node.status.value,
                "healthy": node.healthy,
                "models": node.models,
                "metrics": {
                    "requests_total": node.metrics.requests_total,
                    "active_requests": node.metrics.active_requests,
                    "avg_latency_ms": node.metrics.avg_latency_ms,
                    "tokens_per_second": node.metrics.tokens_per_second,
                },
            }
            for node in self.load_balancer._nodes.values()
        ]

    def list_models(self) -> List[str]:
        """قائمة النماذج المتاحة."""
        models = set()
        for node in self.load_balancer._nodes.values():
            if node.healthy:
                models.update(node.models)
        return list(models)

    async def _health_check_loop(self) -> None:
        """حلقة فحص الصحة."""
        while self._running:
            try:
                await asyncio.sleep(self.health_check_interval)

                for node in list(self.load_balancer._nodes.values()):
                    try:
                        healthy = await node.connect()

                        if not healthy and node.healthy:
                            logger.warning(f"Node {node.name} became unhealthy")
                        elif healthy and not node.healthy:
                            logger.info(f"Node {node.name} recovered")

                    except Exception as e:
                        logger.error(f"Health check failed for {node.name}: {e}")
                        node.healthy = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")


# Convenience function
async def create_router_from_config(
    nodes: List[Dict[str, Any]],
    strategy: str = "round_robin",
) -> InferenceRouter:
    """إنشاء موجه من التكوين."""
    router = InferenceRouter(
        strategy=RoutingStrategy(strategy),
    )

    for node_config in nodes:
        await router.add_node(
            url=node_config["url"],
            provider_type=node_config.get("provider", "ollama"),
            name=node_config.get("name"),
            weight=node_config.get("weight", 1.0),
            max_concurrent=node_config.get("max_concurrent", 10),
        )

    await router.start()

    return router
