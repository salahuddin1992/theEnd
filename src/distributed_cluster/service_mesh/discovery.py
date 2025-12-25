"""
Service discovery implementations for various backends.
"""

import asyncio
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Status of a service instance."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"
    UNKNOWN = "unknown"


@dataclass
class ServiceInstance:
    """Represents a service instance."""
    instance_id: str
    service_name: str
    host: str
    port: int
    status: ServiceStatus = ServiceStatus.UNKNOWN
    metadata: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    weight: int = 1
    zone: Optional[str] = None
    region: Optional[str] = None
    version: str = "v1"
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: Optional[datetime] = None
    health_check_url: Optional[str] = None

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def is_healthy(self) -> bool:
        return self.status == ServiceStatus.HEALTHY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "service_name": self.service_name,
            "host": self.host,
            "port": self.port,
            "status": self.status.value,
            "metadata": self.metadata,
            "tags": self.tags,
            "weight": self.weight,
            "zone": self.zone,
            "region": self.region,
            "version": self.version,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceInstance":
        return cls(
            instance_id=data["instance_id"],
            service_name=data["service_name"],
            host=data["host"],
            port=data["port"],
            status=ServiceStatus(data.get("status", "unknown")),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            weight=data.get("weight", 1),
            zone=data.get("zone"),
            region=data.get("region"),
            version=data.get("version", "v1"),
        )


class ServiceRegistry:
    """In-memory service registry."""

    def __init__(self):
        self._services: Dict[str, Dict[str, ServiceInstance]] = {}  # service_name -> {instance_id -> instance}
        self._lock = threading.RLock()
        self._watchers: Dict[str, List[Callable[[str, List[ServiceInstance]], None]]] = {}

    def register(self, instance: ServiceInstance) -> bool:
        """Register a service instance."""
        with self._lock:
            if instance.service_name not in self._services:
                self._services[instance.service_name] = {}

            self._services[instance.service_name][instance.instance_id] = instance
            instance.status = ServiceStatus.HEALTHY
            instance.last_heartbeat = datetime.utcnow()

            logger.info(f"Registered instance {instance.instance_id} for service {instance.service_name}")

            # Notify watchers
            self._notify_watchers(instance.service_name)

            return True

    def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister a service instance."""
        with self._lock:
            if service_name in self._services:
                if instance_id in self._services[service_name]:
                    del self._services[service_name][instance_id]
                    logger.info(f"Deregistered instance {instance_id} from service {service_name}")
                    self._notify_watchers(service_name)
                    return True
            return False

    def get_instances(
        self,
        service_name: str,
        healthy_only: bool = True,
        tags: Optional[List[str]] = None,
        zone: Optional[str] = None,
        version: Optional[str] = None
    ) -> List[ServiceInstance]:
        """Get instances of a service with optional filters."""
        with self._lock:
            instances = list(self._services.get(service_name, {}).values())

            if healthy_only:
                instances = [i for i in instances if i.is_healthy]

            if tags:
                instances = [i for i in instances if all(t in i.tags for t in tags)]

            if zone:
                instances = [i for i in instances if i.zone == zone]

            if version:
                instances = [i for i in instances if i.version == version]

            return instances

    def get_instance(self, service_name: str, instance_id: str) -> Optional[ServiceInstance]:
        """Get a specific instance."""
        with self._lock:
            return self._services.get(service_name, {}).get(instance_id)

    def heartbeat(self, service_name: str, instance_id: str) -> bool:
        """Update heartbeat for an instance."""
        with self._lock:
            instance = self.get_instance(service_name, instance_id)
            if instance:
                instance.last_heartbeat = datetime.utcnow()
                instance.status = ServiceStatus.HEALTHY
                return True
            return False

    def set_status(
        self,
        service_name: str,
        instance_id: str,
        status: ServiceStatus
    ) -> bool:
        """Set the status of an instance."""
        with self._lock:
            instance = self.get_instance(service_name, instance_id)
            if instance:
                instance.status = status
                self._notify_watchers(service_name)
                return True
            return False

    def list_services(self) -> List[str]:
        """List all registered service names."""
        with self._lock:
            return list(self._services.keys())

    def watch(
        self,
        service_name: str,
        callback: Callable[[str, List[ServiceInstance]], None]
    ):
        """Watch for changes to a service."""
        with self._lock:
            if service_name not in self._watchers:
                self._watchers[service_name] = []
            self._watchers[service_name].append(callback)

    def unwatch(
        self,
        service_name: str,
        callback: Callable[[str, List[ServiceInstance]], None]
    ):
        """Stop watching a service."""
        with self._lock:
            if service_name in self._watchers:
                self._watchers[service_name] = [
                    c for c in self._watchers[service_name] if c != callback
                ]

    def _notify_watchers(self, service_name: str):
        """Notify watchers of a service change."""
        watchers = self._watchers.get(service_name, [])
        instances = self.get_instances(service_name, healthy_only=False)

        for callback in watchers:
            try:
                callback(service_name, instances)
            except Exception as e:
                logger.error(f"Error in service watcher callback: {e}")


class ServiceDiscovery(ABC):
    """Abstract base class for service discovery backends."""

    @abstractmethod
    def register(self, instance: ServiceInstance) -> bool:
        pass

    @abstractmethod
    def deregister(self, service_name: str, instance_id: str) -> bool:
        pass

    @abstractmethod
    def get_instances(self, service_name: str) -> List[ServiceInstance]:
        pass

    @abstractmethod
    def watch(
        self,
        service_name: str,
        callback: Callable[[str, List[ServiceInstance]], None]
    ):
        pass

    @abstractmethod
    def close(self):
        pass


class ConsulDiscovery(ServiceDiscovery):
    """Consul-based service discovery."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8500,
        token: Optional[str] = None,
        datacenter: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.token = token
        self.datacenter = datacenter
        self._client = None
        self._watchers: Dict[str, threading.Thread] = {}
        self._running = True
        self._connect()

    def _connect(self):
        """Connect to Consul."""
        try:
            import consul
            self._client = consul.Consul(
                host=self.host,
                port=self.port,
                token=self.token,
                dc=self.datacenter,
            )
            logger.info(f"Connected to Consul at {self.host}:{self.port}")
        except ImportError:
            logger.error("python-consul not installed. Run: pip install python-consul")
            raise

    def register(self, instance: ServiceInstance) -> bool:
        """Register a service with Consul."""
        try:
            check = None
            if instance.health_check_url:
                check = consul.Check.http(
                    instance.health_check_url,
                    interval="10s",
                    timeout="5s"
                )

            self._client.agent.service.register(
                name=instance.service_name,
                service_id=instance.instance_id,
                address=instance.host,
                port=instance.port,
                tags=instance.tags,
                meta=instance.metadata,
                check=check,
            )
            logger.info(f"Registered {instance.instance_id} with Consul")
            return True
        except Exception as e:
            logger.error(f"Failed to register with Consul: {e}")
            return False

    def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister a service from Consul."""
        try:
            self._client.agent.service.deregister(instance_id)
            logger.info(f"Deregistered {instance_id} from Consul")
            return True
        except Exception as e:
            logger.error(f"Failed to deregister from Consul: {e}")
            return False

    def get_instances(self, service_name: str) -> List[ServiceInstance]:
        """Get healthy instances of a service from Consul."""
        try:
            _, services = self._client.health.service(service_name, passing=True)

            instances = []
            for service in services:
                node = service["Node"]
                svc = service["Service"]

                instance = ServiceInstance(
                    instance_id=svc["ID"],
                    service_name=svc["Service"],
                    host=svc.get("Address") or node["Address"],
                    port=svc["Port"],
                    status=ServiceStatus.HEALTHY,
                    tags=svc.get("Tags", []),
                    metadata=svc.get("Meta", {}),
                )
                instances.append(instance)

            return instances
        except Exception as e:
            logger.error(f"Failed to get instances from Consul: {e}")
            return []

    def watch(
        self,
        service_name: str,
        callback: Callable[[str, List[ServiceInstance]], None]
    ):
        """Watch for service changes in Consul."""
        def watch_loop():
            index = None
            while self._running:
                try:
                    index, services = self._client.health.service(
                        service_name,
                        passing=True,
                        index=index,
                        wait="30s"
                    )

                    instances = []
                    for service in services:
                        node = service["Node"]
                        svc = service["Service"]
                        instance = ServiceInstance(
                            instance_id=svc["ID"],
                            service_name=svc["Service"],
                            host=svc.get("Address") or node["Address"],
                            port=svc["Port"],
                            status=ServiceStatus.HEALTHY,
                            tags=svc.get("Tags", []),
                        )
                        instances.append(instance)

                    callback(service_name, instances)

                except Exception as e:
                    logger.error(f"Error watching service {service_name}: {e}")
                    time.sleep(5)

        thread = threading.Thread(target=watch_loop, daemon=True)
        thread.start()
        self._watchers[service_name] = thread

    def close(self):
        """Close Consul connection."""
        self._running = False


class KubernetesDiscovery(ServiceDiscovery):
    """Kubernetes-based service discovery."""

    def __init__(self, namespace: str = "default", in_cluster: bool = True):
        self.namespace = namespace
        self.in_cluster = in_cluster
        self._client = None
        self._core_api = None
        self._watchers: Dict[str, threading.Thread] = {}
        self._running = True
        self._connect()

    def _connect(self):
        """Connect to Kubernetes API."""
        try:
            from kubernetes import client, config

            if self.in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()

            self._client = client
            self._core_api = client.CoreV1Api()
            logger.info("Connected to Kubernetes API")
        except ImportError:
            logger.error("kubernetes not installed. Run: pip install kubernetes")
            raise

    def register(self, instance: ServiceInstance) -> bool:
        """Register is not needed for Kubernetes - handled by K8s."""
        logger.warning("Registration is managed by Kubernetes")
        return True

    def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregistration is not needed for Kubernetes - handled by K8s."""
        logger.warning("Deregistration is managed by Kubernetes")
        return True

    def get_instances(self, service_name: str) -> List[ServiceInstance]:
        """Get endpoints for a Kubernetes service."""
        try:
            endpoints = self._core_api.read_namespaced_endpoints(
                name=service_name,
                namespace=self.namespace
            )

            instances = []
            if endpoints.subsets:
                for subset in endpoints.subsets:
                    if subset.addresses:
                        for addr in subset.addresses:
                            for port in subset.ports or []:
                                instance = ServiceInstance(
                                    instance_id=f"{addr.ip}:{port.port}",
                                    service_name=service_name,
                                    host=addr.ip,
                                    port=port.port,
                                    status=ServiceStatus.HEALTHY,
                                    metadata={
                                        "node": addr.node_name or "",
                                        "pod": addr.target_ref.name if addr.target_ref else "",
                                    }
                                )
                                instances.append(instance)

            return instances
        except Exception as e:
            logger.error(f"Failed to get endpoints from Kubernetes: {e}")
            return []

    def watch(
        self,
        service_name: str,
        callback: Callable[[str, List[ServiceInstance]], None]
    ):
        """Watch for endpoint changes in Kubernetes."""
        def watch_loop():
            from kubernetes import watch as k8s_watch

            w = k8s_watch.Watch()
            while self._running:
                try:
                    for event in w.stream(
                        self._core_api.list_namespaced_endpoints,
                        namespace=self.namespace,
                        field_selector=f"metadata.name={service_name}"
                    ):
                        if event["type"] in ["ADDED", "MODIFIED", "DELETED"]:
                            instances = self.get_instances(service_name)
                            callback(service_name, instances)
                except Exception as e:
                    logger.error(f"Error watching Kubernetes endpoints: {e}")
                    time.sleep(5)

        thread = threading.Thread(target=watch_loop, daemon=True)
        thread.start()
        self._watchers[service_name] = thread

    def close(self):
        """Close Kubernetes watcher."""
        self._running = False


class EtcdDiscovery(ServiceDiscovery):
    """etcd-based service discovery."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 2379,
        prefix: str = "/services"
    ):
        self.host = host
        self.port = port
        self.prefix = prefix
        self._client = None
        self._watchers: Dict[str, threading.Thread] = {}
        self._running = True
        self._connect()

    def _connect(self):
        """Connect to etcd."""
        try:
            import etcd3
            self._client = etcd3.client(host=self.host, port=self.port)
            logger.info(f"Connected to etcd at {self.host}:{self.port}")
        except ImportError:
            logger.error("etcd3 not installed. Run: pip install etcd3")
            raise

    def _make_key(self, service_name: str, instance_id: str) -> str:
        return f"{self.prefix}/{service_name}/{instance_id}"

    def register(self, instance: ServiceInstance) -> bool:
        """Register a service with etcd."""
        try:
            key = self._make_key(instance.service_name, instance.instance_id)
            value = json.dumps(instance.to_dict())

            # Create lease for TTL
            lease = self._client.lease(ttl=30)
            self._client.put(key, value, lease=lease)

            logger.info(f"Registered {instance.instance_id} with etcd")
            return True
        except Exception as e:
            logger.error(f"Failed to register with etcd: {e}")
            return False

    def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister a service from etcd."""
        try:
            key = self._make_key(service_name, instance_id)
            self._client.delete(key)
            logger.info(f"Deregistered {instance_id} from etcd")
            return True
        except Exception as e:
            logger.error(f"Failed to deregister from etcd: {e}")
            return False

    def get_instances(self, service_name: str) -> List[ServiceInstance]:
        """Get instances of a service from etcd."""
        try:
            prefix = f"{self.prefix}/{service_name}/"
            instances = []

            for value, _ in self._client.get_prefix(prefix):
                if value:
                    data = json.loads(value.decode())
                    instance = ServiceInstance.from_dict(data)
                    instances.append(instance)

            return instances
        except Exception as e:
            logger.error(f"Failed to get instances from etcd: {e}")
            return []

    def watch(
        self,
        service_name: str,
        callback: Callable[[str, List[ServiceInstance]], None]
    ):
        """Watch for service changes in etcd."""
        def watch_loop():
            prefix = f"{self.prefix}/{service_name}/"
            events_iterator, cancel = self._client.watch_prefix(prefix)

            while self._running:
                try:
                    for event in events_iterator:
                        instances = self.get_instances(service_name)
                        callback(service_name, instances)
                except Exception as e:
                    logger.error(f"Error watching etcd: {e}")
                    time.sleep(5)

        thread = threading.Thread(target=watch_loop, daemon=True)
        thread.start()
        self._watchers[service_name] = thread

    def close(self):
        """Close etcd connection."""
        self._running = False
        if self._client:
            self._client.close()
