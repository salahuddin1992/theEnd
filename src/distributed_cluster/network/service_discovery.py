# -*- coding: utf-8 -*-
"""
Service Discovery for NebulaCompute.

نظام الكشف عن الخدمات.

Provides automatic service registration and discovery:
- Service registration with health checks
- Service lookup by name and tags
- Multi-backend support (memory, consul, etcd)
- Watch for service changes
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ServiceStatus(str, Enum):
    """Service instance status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


@dataclass
class ServiceInstance:
    """
    Service instance representation.

    تمثيل نسخة الخدمة.
    """

    id: str
    service_name: str
    host: str
    port: int
    status: ServiceStatus = ServiceStatus.HEALTHY
    metadata: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    weight: int = 1
    version: str = "1.0.0"
    zone: str = "default"
    registered_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    ttl_seconds: int = 30

    @property
    def address(self) -> str:
        """Get service address."""
        return f"{self.host}:{self.port}"

    @property
    def is_healthy(self) -> bool:
        """Check if service is healthy and heartbeat is fresh."""
        if self.status != ServiceStatus.HEALTHY:
            return False
        return datetime.now() - self.last_heartbeat < timedelta(seconds=self.ttl_seconds * 2)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "service_name": self.service_name,
            "host": self.host,
            "port": self.port,
            "address": self.address,
            "status": self.status.value,
            "metadata": self.metadata,
            "tags": self.tags,
            "weight": self.weight,
            "version": self.version,
            "zone": self.zone,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "is_healthy": self.is_healthy,
        }


@dataclass
class ServiceDefinition:
    """
    Service definition.

    تعريف الخدمة.
    """

    name: str
    description: str = ""
    default_port: int = 8080
    health_check_path: str = "/health"
    health_check_interval: int = 10
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


class ServiceDiscoveryBackend(ABC):
    """
    Abstract backend for service discovery.

    واجهة خلفية مجردة للكشف عن الخدمات.
    """

    @abstractmethod
    async def register(self, instance: ServiceInstance) -> bool:
        """Register a service instance."""
        pass

    @abstractmethod
    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister a service instance."""
        pass

    @abstractmethod
    async def heartbeat(self, service_name: str, instance_id: str) -> bool:
        """Send heartbeat for a service instance."""
        pass

    @abstractmethod
    async def get_instances(
        self,
        service_name: str,
        healthy_only: bool = True,
        tags: Optional[List[str]] = None,
    ) -> List[ServiceInstance]:
        """Get service instances."""
        pass

    @abstractmethod
    async def get_all_services(self) -> List[str]:
        """Get all registered service names."""
        pass


class InMemoryBackend(ServiceDiscoveryBackend):
    """
    In-memory service discovery backend.

    خلفية الكشف عن الخدمات في الذاكرة.

    Suitable for single-node or testing environments.
    """

    def __init__(self):
        self._services: Dict[str, Dict[str, ServiceInstance]] = {}
        self._lock = asyncio.Lock()

    async def register(self, instance: ServiceInstance) -> bool:
        """Register a service instance."""
        async with self._lock:
            if instance.service_name not in self._services:
                self._services[instance.service_name] = {}

            self._services[instance.service_name][instance.id] = instance
            logger.info(f"Registered service: {instance.service_name}/{instance.id} " f"at {instance.address}")
            return True

    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister a service instance."""
        async with self._lock:
            if service_name in self._services:
                if instance_id in self._services[service_name]:
                    del self._services[service_name][instance_id]
                    logger.info(f"Deregistered service: {service_name}/{instance_id}")
                    return True
            return False

    async def heartbeat(self, service_name: str, instance_id: str) -> bool:
        """Send heartbeat for a service instance."""
        async with self._lock:
            if service_name in self._services:
                if instance_id in self._services[service_name]:
                    self._services[service_name][instance_id].last_heartbeat = datetime.now()
                    return True
            return False

    async def get_instances(
        self,
        service_name: str,
        healthy_only: bool = True,
        tags: Optional[List[str]] = None,
    ) -> List[ServiceInstance]:
        """Get service instances."""
        async with self._lock:
            if service_name not in self._services:
                return []

            instances = list(self._services[service_name].values())

            # Filter by health
            if healthy_only:
                instances = [i for i in instances if i.is_healthy]

            # Filter by tags
            if tags:
                instances = [i for i in instances if all(t in i.tags for t in tags)]

            return instances

    async def get_all_services(self) -> List[str]:
        """Get all registered service names."""
        async with self._lock:
            return list(self._services.keys())

    async def cleanup_stale(self, max_age_seconds: int = 60) -> int:
        """Remove stale instances."""
        removed = 0
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)

        async with self._lock:
            for service_name in list(self._services.keys()):
                for instance_id in list(self._services[service_name].keys()):
                    instance = self._services[service_name][instance_id]
                    if instance.last_heartbeat < cutoff:
                        del self._services[service_name][instance_id]
                        removed += 1
                        logger.info(f"Removed stale instance: {service_name}/{instance_id}")

        return removed


class ConsulBackend(ServiceDiscoveryBackend):
    """
    Consul service discovery backend.

    خلفية Consul للكشف عن الخدمات.

    Requires consul-client library.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8500,
        token: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.token = token
        self._client = None

    async def _get_client(self):
        """Get or create Consul client."""
        if self._client is None:
            try:
                import consul.aio as consul

                self._client = consul.Consul(
                    host=self.host,
                    port=self.port,
                    token=self.token,
                )
            except ImportError:
                logger.error("consul library not installed")
                self._client = "mock"

        return self._client

    async def register(self, instance: ServiceInstance) -> bool:
        """Register service with Consul."""
        client = await self._get_client()
        if client == "mock":
            return False

        try:
            service_id = f"{instance.service_name}-{instance.id}"

            await client.agent.service.register(
                name=instance.service_name,
                service_id=service_id,
                address=instance.host,
                port=instance.port,
                tags=instance.tags,
                meta=instance.metadata,
                check={
                    "ttl": f"{instance.ttl_seconds}s",
                    "deregister_critical_service_after": "1m",
                },
            )

            logger.info(f"Registered with Consul: {service_id}")
            return True

        except Exception as e:
            logger.error(f"Consul registration failed: {e}")
            return False

    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister service from Consul."""
        client = await self._get_client()
        if client == "mock":
            return False

        try:
            service_id = f"{service_name}-{instance_id}"
            await client.agent.service.deregister(service_id)
            logger.info(f"Deregistered from Consul: {service_id}")
            return True

        except Exception as e:
            logger.error(f"Consul deregistration failed: {e}")
            return False

    async def heartbeat(self, service_name: str, instance_id: str) -> bool:
        """Send TTL heartbeat to Consul."""
        client = await self._get_client()
        if client == "mock":
            return False

        try:
            check_id = f"service:{service_name}-{instance_id}"
            await client.agent.check.ttl_pass(check_id)
            return True

        except Exception as e:
            logger.error(f"Consul heartbeat failed: {e}")
            return False

    async def get_instances(
        self,
        service_name: str,
        healthy_only: bool = True,
        tags: Optional[List[str]] = None,
    ) -> List[ServiceInstance]:
        """Get service instances from Consul."""
        client = await self._get_client()
        if client == "mock":
            return []

        try:
            index, services = await client.health.service(
                service_name,
                passing=healthy_only,
                tag=tags[0] if tags else None,
            )

            instances = []
            for entry in services:
                service = entry["Service"]
                instances.append(
                    ServiceInstance(
                        id=service["ID"].replace(f"{service_name}-", ""),
                        service_name=service_name,
                        host=service["Address"],
                        port=service["Port"],
                        status=ServiceStatus.HEALTHY,
                        tags=service.get("Tags", []),
                        metadata=service.get("Meta", {}),
                    )
                )

            return instances

        except Exception as e:
            logger.error(f"Consul query failed: {e}")
            return []

    async def get_all_services(self) -> List[str]:
        """Get all services from Consul."""
        client = await self._get_client()
        if client == "mock":
            return []

        try:
            index, services = await client.catalog.services()
            return list(services.keys())

        except Exception as e:
            logger.error(f"Consul services query failed: {e}")
            return []


class EtcdBackend(ServiceDiscoveryBackend):
    """
    etcd service discovery backend.

    خلفية etcd للكشف عن الخدمات.

    Requires etcd3 library.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 2379,
        prefix: str = "/services",
    ):
        self.host = host
        self.port = port
        self.prefix = prefix
        self._client = None

    async def _get_client(self):
        """Get or create etcd client."""
        if self._client is None:
            try:
                import etcd3

                self._client = etcd3.client(host=self.host, port=self.port)
            except ImportError:
                logger.error("etcd3 library not installed")
                self._client = "mock"

        return self._client

    def _make_key(self, service_name: str, instance_id: str) -> str:
        """Create etcd key."""
        return f"{self.prefix}/{service_name}/{instance_id}"

    async def register(self, instance: ServiceInstance) -> bool:
        """Register service with etcd."""
        client = await self._get_client()
        if client == "mock":
            return False

        try:
            import json

            key = self._make_key(instance.service_name, instance.id)
            value = json.dumps(instance.to_dict())

            # Create lease for TTL
            lease = client.lease(instance.ttl_seconds)
            client.put(key, value, lease=lease)

            logger.info(f"Registered with etcd: {key}")
            return True

        except Exception as e:
            logger.error(f"etcd registration failed: {e}")
            return False

    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister service from etcd."""
        client = await self._get_client()
        if client == "mock":
            return False

        try:
            key = self._make_key(service_name, instance_id)
            client.delete(key)
            logger.info(f"Deregistered from etcd: {key}")
            return True

        except Exception as e:
            logger.error(f"etcd deregistration failed: {e}")
            return False

    async def heartbeat(self, service_name: str, instance_id: str) -> bool:
        """Refresh lease in etcd."""
        # For etcd, we need to refresh the lease
        # This is typically done by the lease.refresh() method
        client = await self._get_client()
        if client == "mock":
            return False

        # Re-register to refresh
        instances = await self.get_instances(service_name)
        for instance in instances:
            if instance.id == instance_id:
                return await self.register(instance)

        return False

    async def get_instances(
        self,
        service_name: str,
        healthy_only: bool = True,
        tags: Optional[List[str]] = None,
    ) -> List[ServiceInstance]:
        """Get service instances from etcd."""
        client = await self._get_client()
        if client == "mock":
            return []

        try:
            import json

            prefix = f"{self.prefix}/{service_name}/"
            instances = []

            for value, metadata in client.get_prefix(prefix):
                try:
                    data = json.loads(value.decode())
                    instance = ServiceInstance(
                        id=data["id"],
                        service_name=data["service_name"],
                        host=data["host"],
                        port=data["port"],
                        status=ServiceStatus(data.get("status", "healthy")),
                        tags=data.get("tags", []),
                        metadata=data.get("metadata", {}),
                        weight=data.get("weight", 1),
                        version=data.get("version", "1.0.0"),
                    )

                    # Filter by tags
                    if tags and not all(t in instance.tags for t in tags):
                        continue

                    if healthy_only and not instance.is_healthy:
                        continue

                    instances.append(instance)

                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to parse etcd entry: {e}")

            return instances

        except Exception as e:
            logger.error(f"etcd query failed: {e}")
            return []

    async def get_all_services(self) -> List[str]:
        """Get all services from etcd."""
        client = await self._get_client()
        if client == "mock":
            return []

        try:
            services = set()
            for value, metadata in client.get_prefix(self.prefix):
                key = metadata.key.decode()
                parts = key.replace(self.prefix + "/", "").split("/")
                if parts:
                    services.add(parts[0])

            return list(services)

        except Exception as e:
            logger.error(f"etcd services query failed: {e}")
            return []


class ServiceRegistry:
    """
    Service Registry - main interface for service discovery.

    سجل الخدمات - الواجهة الرئيسية للكشف عن الخدمات.

    Usage:
        registry = ServiceRegistry()

        # Register a service
        instance = await registry.register(
            service_name="api",
            host="10.0.0.1",
            port=8080,
            tags=["production", "v2"],
        )

        # Discover services
        instances = await registry.discover("api")

        # Get healthy instance
        instance = await registry.get_one("api")
    """

    def __init__(
        self,
        backend: Optional[ServiceDiscoveryBackend] = None,
        heartbeat_interval: float = 10.0,
    ):
        """
        Initialize service registry.

        Args:
            backend: Service discovery backend
            heartbeat_interval: Heartbeat interval in seconds
        """
        self.backend = backend or InMemoryBackend()
        self.heartbeat_interval = heartbeat_interval
        self._local_instances: Dict[str, ServiceInstance] = {}
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self._watchers: Dict[str, List[Callable]] = {}
        self._running = False

    async def register(
        self,
        service_name: str,
        host: str,
        port: int,
        instance_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, str]] = None,
        weight: int = 1,
        version: str = "1.0.0",
        zone: str = "default",
        ttl_seconds: int = 30,
    ) -> ServiceInstance:
        """
        Register a service instance.

        تسجيل نسخة خدمة.

        Args:
            service_name: Service name
            host: Service host
            port: Service port
            instance_id: Instance ID (auto-generated if not provided)
            tags: Service tags
            metadata: Service metadata
            weight: Load balancing weight
            version: Service version
            zone: Availability zone
            ttl_seconds: TTL for health check

        Returns:
            Registered service instance
        """
        instance = ServiceInstance(
            id=instance_id or str(uuid.uuid4())[:8],
            service_name=service_name,
            host=host,
            port=port,
            tags=tags or [],
            metadata=metadata or {},
            weight=weight,
            version=version,
            zone=zone,
            ttl_seconds=ttl_seconds,
        )

        success = await self.backend.register(instance)
        if success:
            self._local_instances[instance.id] = instance
            self._start_heartbeat(instance)
            await self._notify_watchers(service_name, "register", instance)

        return instance

    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """
        Deregister a service instance.

        إلغاء تسجيل نسخة خدمة.
        """
        self._stop_heartbeat(instance_id)

        success = await self.backend.deregister(service_name, instance_id)
        if success:
            if instance_id in self._local_instances:
                instance = self._local_instances.pop(instance_id)
                await self._notify_watchers(service_name, "deregister", instance)

        return success

    async def discover(
        self,
        service_name: str,
        healthy_only: bool = True,
        tags: Optional[List[str]] = None,
    ) -> List[ServiceInstance]:
        """
        Discover service instances.

        اكتشاف نسخ الخدمة.

        Args:
            service_name: Service name
            healthy_only: Only return healthy instances
            tags: Filter by tags

        Returns:
            List of service instances
        """
        return await self.backend.get_instances(
            service_name,
            healthy_only=healthy_only,
            tags=tags,
        )

    async def get_one(
        self,
        service_name: str,
        tags: Optional[List[str]] = None,
        strategy: str = "random",
    ) -> Optional[ServiceInstance]:
        """
        Get a single service instance.

        الحصول على نسخة خدمة واحدة.

        Args:
            service_name: Service name
            tags: Filter by tags
            strategy: Selection strategy (random, first, least_connections)

        Returns:
            Service instance or None
        """
        instances = await self.discover(service_name, tags=tags)
        if not instances:
            return None

        if strategy == "random":
            import random

            return random.choice(instances)
        elif strategy == "first":
            return instances[0]
        elif strategy == "weighted":
            import random

            weights = [i.weight for i in instances]
            return random.choices(instances, weights=weights, k=1)[0]
        else:
            return instances[0]

    async def get_all_services(self) -> List[str]:
        """Get all registered service names."""
        return await self.backend.get_all_services()

    def watch(
        self,
        service_name: str,
        callback: Callable[[str, str, ServiceInstance], None],
    ) -> None:
        """
        Watch for service changes.

        مراقبة تغييرات الخدمة.

        Args:
            service_name: Service name to watch
            callback: Callback function (event_type, service_name, instance)
        """
        if service_name not in self._watchers:
            self._watchers[service_name] = []
        self._watchers[service_name].append(callback)

    def unwatch(
        self,
        service_name: str,
        callback: Callable,
    ) -> None:
        """Remove a watcher."""
        if service_name in self._watchers:
            if callback in self._watchers[service_name]:
                self._watchers[service_name].remove(callback)

    async def _notify_watchers(
        self,
        service_name: str,
        event_type: str,
        instance: ServiceInstance,
    ) -> None:
        """Notify watchers of service changes."""
        if service_name in self._watchers:
            for callback in self._watchers[service_name]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event_type, service_name, instance)
                    else:
                        callback(event_type, service_name, instance)
                except Exception as e:
                    logger.error(f"Watcher callback error: {e}")

    def _start_heartbeat(self, instance: ServiceInstance) -> None:
        """Start heartbeat task for instance."""
        if instance.id in self._heartbeat_tasks:
            return

        async def heartbeat_loop():
            while instance.id in self._local_instances:
                try:
                    await self.backend.heartbeat(instance.service_name, instance.id)
                    instance.last_heartbeat = datetime.now()
                except Exception as e:
                    logger.error(f"Heartbeat failed for {instance.id}: {e}")

                await asyncio.sleep(self.heartbeat_interval)

        task = asyncio.create_task(heartbeat_loop())
        self._heartbeat_tasks[instance.id] = task

    def _stop_heartbeat(self, instance_id: str) -> None:
        """Stop heartbeat task for instance."""
        if instance_id in self._heartbeat_tasks:
            self._heartbeat_tasks[instance_id].cancel()
            del self._heartbeat_tasks[instance_id]

    async def shutdown(self) -> None:
        """Shutdown registry and deregister all local instances."""
        # Stop all heartbeats
        for instance_id in list(self._heartbeat_tasks.keys()):
            self._stop_heartbeat(instance_id)

        # Deregister all local instances
        for instance in list(self._local_instances.values()):
            await self.deregister(instance.service_name, instance.id)


# Global service registry
_registry: Optional[ServiceRegistry] = None


def get_registry() -> ServiceRegistry:
    """Get global service registry."""
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry


def set_registry(registry: ServiceRegistry) -> None:
    """Set global service registry."""
    global _registry
    _registry = registry


async def register_service(
    service_name: str,
    host: str,
    port: int,
    **kwargs,
) -> ServiceInstance:
    """Register a service with the global registry."""
    return await get_registry().register(service_name, host, port, **kwargs)


async def discover_services(
    service_name: str,
    **kwargs,
) -> List[ServiceInstance]:
    """Discover services from the global registry."""
    return await get_registry().discover(service_name, **kwargs)
