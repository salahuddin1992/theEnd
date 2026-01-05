"""
Cluster Discovery - اكتشاف الكتل
==================================

Cluster Discovery Mechanisms
----------------------------

This module provides cluster discovery mechanisms.

يوفر هذا الملف آليات اكتشاف الكتل.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from distributed_cluster.federation.cluster import (
    ClusterInfo,
    ClusterRole,
    ClusterStatus,
)

logger = logging.getLogger(__name__)


class DiscoveryMethod(str, Enum):
    """طريقة الاكتشاف / Discovery method"""

    STATIC = "static"  # قائمة ثابتة
    DNS = "dns"  # DNS SRV records
    CONSUL = "consul"  # Consul service discovery
    ETCD = "etcd"  # etcd registry
    KUBERNETES = "kubernetes"  # Kubernetes services
    MULTICAST = "multicast"  # UDP multicast


@dataclass
class DiscoveryConfig:
    """
    إعدادات الاكتشاف
    Discovery Configuration
    """

    method: DiscoveryMethod = DiscoveryMethod.STATIC

    # Polling
    poll_interval_seconds: float = 30.0
    timeout_seconds: float = 10.0

    # Static discovery
    static_clusters: list[dict[str, Any]] = field(default_factory=list)

    # DNS discovery
    dns_name: str = ""
    dns_port: int = 8080

    # Consul discovery
    consul_address: str = "http://localhost:8500"
    consul_service: str = "distributed-cluster"
    consul_datacenter: str = ""

    # etcd discovery
    etcd_endpoints: list[str] = field(default_factory=list)
    etcd_prefix: str = "/clusters/"

    # Kubernetes discovery
    k8s_namespace: str = "default"
    k8s_label_selector: str = "app=distributed-cluster"
    k8s_service_name: str = "distributed-cluster"

    # Health check
    health_check_enabled: bool = True
    health_check_path: str = "/health"
    unhealthy_threshold: int = 3


class DiscoveryBackend(ABC):
    """قاعدة الاكتشاف"""

    @abstractmethod
    async def discover(self) -> list[ClusterInfo]:
        """اكتشاف الكتل"""
        pass

    @abstractmethod
    async def register(self, cluster: ClusterInfo) -> bool:
        """تسجيل كتلة"""
        pass

    @abstractmethod
    async def deregister(self, cluster_id: str) -> bool:
        """إلغاء تسجيل كتلة"""
        pass


class StaticDiscovery(DiscoveryBackend):
    """اكتشاف ثابت"""

    def __init__(self, clusters: list[dict[str, Any]]):
        self.clusters = clusters

    async def discover(self) -> list[ClusterInfo]:
        """اكتشاف من قائمة ثابتة"""
        result = []

        for c in self.clusters:
            info = ClusterInfo(
                cluster_id=c.get("cluster_id", c.get("id")),
                cluster_name=c.get("cluster_name", c.get("name")),
                endpoint=c.get("endpoint", c.get("url")),
                region=c.get("region", "default"),
                role=ClusterRole(c.get("role", "secondary")),
                status=ClusterStatus.UNKNOWN,
            )
            result.append(info)

        return result

    async def register(self, cluster: ClusterInfo) -> bool:
        """تسجيل كتلة"""
        self.clusters.append(
            {
                "cluster_id": cluster.cluster_id,
                "cluster_name": cluster.cluster_name,
                "endpoint": cluster.endpoint,
                "region": cluster.region,
            }
        )
        return True

    async def deregister(self, cluster_id: str) -> bool:
        """إلغاء تسجيل"""
        self.clusters = [c for c in self.clusters if c.get("cluster_id") != cluster_id]
        return True


class ConsulDiscovery(DiscoveryBackend):
    """اكتشاف عبر Consul"""

    def __init__(
        self,
        address: str,
        service: str,
        datacenter: str = "",
    ):
        self.address = address
        self.service = service
        self.datacenter = datacenter
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(base_url=self.address)
        return self._client

    async def discover(self) -> list[ClusterInfo]:
        """اكتشاف من Consul"""
        client = await self._get_client()

        params = {}
        if self.datacenter:
            params["dc"] = self.datacenter

        response = await client.get(
            f"/v1/health/service/{self.service}",
            params=params,
        )
        response.raise_for_status()

        services = response.json()
        result = []

        for svc in services:
            node = svc.get("Node", {})
            service = svc.get("Service", {})
            checks = svc.get("Checks", [])

            # Determine status from checks
            status = ClusterStatus.HEALTHY
            for check in checks:
                if check.get("Status") == "critical":
                    status = ClusterStatus.UNHEALTHY
                    break
                elif check.get("Status") == "warning":
                    status = ClusterStatus.DEGRADED

            meta = service.get("Meta", {})

            info = ClusterInfo(
                cluster_id=service.get("ID"),
                cluster_name=meta.get("cluster_name", service.get("Service")),
                endpoint=f"http://{service.get('Address')}:{service.get('Port')}",
                region=meta.get("region", node.get("Datacenter", "default")),
                role=ClusterRole(meta.get("role", "secondary")),
                status=status,
                tags=dict(service.get("Tags", [])),
            )
            result.append(info)

        return result

    async def register(self, cluster: ClusterInfo) -> bool:
        """تسجيل في Consul"""
        client = await self._get_client()

        # Parse endpoint
        from urllib.parse import urlparse

        parsed = urlparse(cluster.endpoint)

        service = {
            "ID": cluster.cluster_id,
            "Name": self.service,
            "Address": parsed.hostname,
            "Port": parsed.port or 8080,
            "Meta": {
                "cluster_name": cluster.cluster_name,
                "region": cluster.region,
                "role": cluster.role.value,
            },
            "Check": {
                "HTTP": f"{cluster.endpoint}/health",
                "Interval": "10s",
                "Timeout": "5s",
            },
        }

        response = await client.put(
            "/v1/agent/service/register",
            json=service,
        )

        return response.status_code == 200

    async def deregister(self, cluster_id: str) -> bool:
        """إلغاء التسجيل من Consul"""
        client = await self._get_client()
        response = await client.put(
            f"/v1/agent/service/deregister/{cluster_id}",
        )
        return response.status_code == 200


class KubernetesDiscovery(DiscoveryBackend):
    """اكتشاف عبر Kubernetes"""

    def __init__(
        self,
        namespace: str = "default",
        label_selector: str = "app=distributed-cluster",
        service_name: str = "",
    ):
        self.namespace = namespace
        self.label_selector = label_selector
        self.service_name = service_name
        self._client = None

    async def _get_client(self):
        if self._client is None:
            try:
                from kubernetes_asyncio import client, config

                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    await config.load_kube_config()

                self._client = client.CoreV1Api()
            except ImportError:
                raise ImportError("kubernetes_asyncio is required")
        return self._client

    async def discover(self) -> list[ClusterInfo]:
        """اكتشاف من Kubernetes"""
        client = await self._get_client()
        result = []

        if self.service_name:
            # Discover from service endpoints
            endpoints = await client.read_namespaced_endpoints(
                name=self.service_name,
                namespace=self.namespace,
            )

            for subset in endpoints.subsets or []:
                for addr in subset.addresses or []:
                    for port in subset.ports or []:
                        info = ClusterInfo(
                            cluster_id=f"{addr.ip}:{port.port}",
                            cluster_name=f"cluster-{addr.ip}",
                            endpoint=f"http://{addr.ip}:{port.port}",
                            region=self.namespace,
                            status=ClusterStatus.HEALTHY,
                        )
                        result.append(info)
        else:
            # Discover from pods
            pods = await client.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=self.label_selector,
            )

            for pod in pods.items:
                if pod.status.phase != "Running":
                    continue

                labels = pod.metadata.labels or {}
                annotations = pod.metadata.annotations or {}

                info = ClusterInfo(
                    cluster_id=pod.metadata.uid,
                    cluster_name=pod.metadata.name,
                    endpoint=f"http://{pod.status.pod_ip}:8080",
                    region=annotations.get("region", self.namespace),
                    role=ClusterRole(labels.get("role", "secondary")),
                    status=ClusterStatus.HEALTHY,
                )
                result.append(info)

        return result

    async def register(self, cluster: ClusterInfo) -> bool:
        """تسجيل - غير مدعوم في K8s"""
        return False

    async def deregister(self, cluster_id: str) -> bool:
        """إلغاء التسجيل - غير مدعوم في K8s"""
        return False


class ClusterDiscovery:
    """
    اكتشاف الكتل
    Cluster Discovery

    يكتشف ويتتبع الكتل المتحدة.
    Discovers and tracks federated clusters.
    """

    def __init__(
        self,
        config: DiscoveryConfig,
    ):
        """
        تهيئة الاكتشاف

        Args:
            config: إعدادات الاكتشاف
        """
        self.config = config
        self._backend = self._create_backend()

        # Discovered clusters
        self._clusters: dict[str, ClusterInfo] = {}
        self._unhealthy_counts: dict[str, int] = {}

        # State
        self._running = False
        self._discovery_task: Optional[asyncio.Task] = None
        self._last_discovery: Optional[datetime] = None

        # Callbacks
        self._on_cluster_added: list = []
        self._on_cluster_removed: list = []
        self._on_cluster_updated: list = []

    def _create_backend(self) -> DiscoveryBackend:
        """إنشاء الـ backend"""
        method = self.config.method

        if method == DiscoveryMethod.STATIC:
            return StaticDiscovery(self.config.static_clusters)

        elif method == DiscoveryMethod.CONSUL:
            return ConsulDiscovery(
                address=self.config.consul_address,
                service=self.config.consul_service,
                datacenter=self.config.consul_datacenter,
            )

        elif method == DiscoveryMethod.KUBERNETES:
            return KubernetesDiscovery(
                namespace=self.config.k8s_namespace,
                label_selector=self.config.k8s_label_selector,
                service_name=self.config.k8s_service_name,
            )

        else:
            return StaticDiscovery([])

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء الاكتشاف"""
        self._running = True

        # Initial discovery
        await self.discover()

        # Start background polling
        self._discovery_task = asyncio.create_task(self._discovery_loop())

        logger.info(f"ClusterDiscovery started with method {self.config.method.value}")

    async def stop(self) -> None:
        """إيقاف الاكتشاف"""
        self._running = False
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass
        logger.info("ClusterDiscovery stopped")

    # =========================================================================
    # Discovery
    # =========================================================================

    async def discover(self) -> list[ClusterInfo]:
        """اكتشاف الكتل"""
        try:
            discovered = await self._backend.discover()
            self._last_discovery = datetime.now(timezone.utc)

            # Process discovered clusters
            current_ids = set(self._clusters.keys())
            discovered_ids = set(c.cluster_id for c in discovered)

            # New clusters
            for cluster in discovered:
                if cluster.cluster_id not in current_ids:
                    self._clusters[cluster.cluster_id] = cluster
                    self._notify_added(cluster)
                else:
                    # Update existing
                    old = self._clusters[cluster.cluster_id]
                    self._clusters[cluster.cluster_id] = cluster
                    if cluster.status != old.status:
                        self._notify_updated(cluster)

            # Removed clusters
            for cluster_id in current_ids - discovered_ids:
                removed = self._clusters.pop(cluster_id, None)
                if removed:
                    self._notify_removed(removed)

            # Health check if enabled
            if self.config.health_check_enabled:
                await self._health_check_all()

            return list(self._clusters.values())

        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            return list(self._clusters.values())

    async def _health_check_all(self) -> None:
        """فحص صحة كل الكتل"""
        import httpx

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            for cluster_id, cluster in list(self._clusters.items()):
                try:
                    url = f"{cluster.endpoint}{self.config.health_check_path}"
                    response = await client.get(url)

                    if response.status_code == 200:
                        cluster.status = ClusterStatus.HEALTHY
                        cluster.last_seen = datetime.now(timezone.utc)
                        self._unhealthy_counts[cluster_id] = 0
                    else:
                        self._mark_unhealthy(cluster_id)

                except Exception:
                    self._mark_unhealthy(cluster_id)

    def _mark_unhealthy(self, cluster_id: str) -> None:
        """تعليم كتلة كغير صحية"""
        self._unhealthy_counts[cluster_id] = self._unhealthy_counts.get(cluster_id, 0) + 1

        if self._unhealthy_counts[cluster_id] >= self.config.unhealthy_threshold:
            cluster = self._clusters.get(cluster_id)
            if cluster:
                cluster.status = ClusterStatus.UNHEALTHY
                self._notify_updated(cluster)

    # =========================================================================
    # Background Loop
    # =========================================================================

    async def _discovery_loop(self) -> None:
        """حلقة الاكتشاف الخلفية"""
        while self._running:
            try:
                await asyncio.sleep(self.config.poll_interval_seconds)
                await self.discover()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Discovery loop error: {e}")

    # =========================================================================
    # Registration
    # =========================================================================

    async def register(self, cluster: ClusterInfo) -> bool:
        """تسجيل كتلة"""
        success = await self._backend.register(cluster)
        if success:
            self._clusters[cluster.cluster_id] = cluster
            self._notify_added(cluster)
        return success

    async def deregister(self, cluster_id: str) -> bool:
        """إلغاء تسجيل كتلة"""
        success = await self._backend.deregister(cluster_id)
        if success:
            removed = self._clusters.pop(cluster_id, None)
            if removed:
                self._notify_removed(removed)
        return success

    # =========================================================================
    # Getters
    # =========================================================================

    def get_clusters(self) -> list[ClusterInfo]:
        """الحصول على كل الكتل"""
        return list(self._clusters.values())

    def get_healthy_clusters(self) -> list[ClusterInfo]:
        """الحصول على الكتل الصحية"""
        return [c for c in self._clusters.values() if c.is_healthy()]

    def get_cluster(self, cluster_id: str) -> Optional[ClusterInfo]:
        """الحصول على كتلة"""
        return self._clusters.get(cluster_id)

    # =========================================================================
    # Callbacks
    # =========================================================================

    def on_cluster_added(self, callback) -> None:
        """تسجيل callback لإضافة كتلة"""
        self._on_cluster_added.append(callback)

    def on_cluster_removed(self, callback) -> None:
        """تسجيل callback لإزالة كتلة"""
        self._on_cluster_removed.append(callback)

    def on_cluster_updated(self, callback) -> None:
        """تسجيل callback لتحديث كتلة"""
        self._on_cluster_updated.append(callback)

    def _notify_added(self, cluster: ClusterInfo) -> None:
        for cb in self._on_cluster_added:
            try:
                cb(cluster)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    def _notify_removed(self, cluster: ClusterInfo) -> None:
        for cb in self._on_cluster_removed:
            try:
                cb(cluster)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    def _notify_updated(self, cluster: ClusterInfo) -> None:
        for cb in self._on_cluster_updated:
            try:
                cb(cluster)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """الحصول على الحالة"""
        return {
            "method": self.config.method.value,
            "running": self._running,
            "last_discovery": (self._last_discovery.isoformat() if self._last_discovery else None),
            "cluster_count": len(self._clusters),
            "healthy_count": len(self.get_healthy_clusters()),
            "clusters": [c.to_dict() for c in self._clusters.values()],
        }
