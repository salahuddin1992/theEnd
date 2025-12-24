"""
Federation Manager - مدير الاتحاد
==================================

Multi-Cluster Federation Management
-----------------------------------

This module provides the main federation manager.

يوفر هذا الملف مدير الاتحاد الرئيسي.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from distributed_cluster.federation.cluster import (
    FederatedCluster,
    ClusterInfo,
    ClusterStatus,
    ClusterRole,
)
from distributed_cluster.federation.router import (
    JobRouter,
    RoutingPolicy,
    RoutingResult,
)
from distributed_cluster.federation.sync import (
    StateSync,
    SyncConfig,
    SyncResult,
)
from distributed_cluster.federation.discovery import (
    ClusterDiscovery,
    DiscoveryConfig,
    DiscoveryMethod,
)

logger = logging.getLogger(__name__)


@dataclass
class FederationConfig:
    """
    إعدادات الاتحاد
    Federation Configuration
    """
    # Local cluster
    cluster_id: str
    cluster_name: str
    endpoint: str
    region: str = "default"
    role: ClusterRole = ClusterRole.PRIMARY

    # Discovery
    discovery_method: DiscoveryMethod = DiscoveryMethod.STATIC
    discovery_config: dict[str, Any] = field(default_factory=dict)

    # Sync
    enable_sync: bool = True
    sync_interval_seconds: float = 30.0

    # Routing
    default_routing_strategy: str = "least_loaded"

    # Health
    health_check_interval_seconds: float = 10.0
    unhealthy_threshold: int = 3

    # Authentication
    api_key: Optional[str] = None
    require_auth: bool = True


class FederationManager:
    """
    مدير الاتحاد
    Federation Manager

    يدير الاتحاد بين الكتل المتعددة.
    Manages federation between multiple clusters.
    """

    def __init__(
        self,
        config: FederationConfig,
    ):
        """
        تهيئة المدير

        Args:
            config: إعدادات الاتحاد
        """
        self.config = config

        # Local cluster info
        self.local_cluster = ClusterInfo(
            cluster_id=config.cluster_id,
            cluster_name=config.cluster_name,
            endpoint=config.endpoint,
            region=config.region,
            role=config.role,
            status=ClusterStatus.HEALTHY,
        )

        # Components
        self._discovery = ClusterDiscovery(
            config=DiscoveryConfig(
                method=config.discovery_method,
                **config.discovery_config,
            )
        )

        self._router = JobRouter()

        self._sync = StateSync(
            cluster_id=config.cluster_id,
            config=SyncConfig(
                sync_interval_seconds=config.sync_interval_seconds,
            ),
        ) if config.enable_sync else None

        # Clusters
        self._clusters: dict[str, FederatedCluster] = {}

        # State
        self._running = False
        self._health_task: Optional[asyncio.Task] = None

        # Stats
        self._stats = {
            "jobs_routed": 0,
            "jobs_failed": 0,
            "syncs_completed": 0,
            "clusters_connected": 0,
        }

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """بدء الاتحاد"""
        logger.info(f"Starting federation manager for {self.config.cluster_id}")

        # Register callbacks
        self._discovery.on_cluster_added(self._on_cluster_discovered)
        self._discovery.on_cluster_removed(self._on_cluster_removed)
        self._discovery.on_cluster_updated(self._on_cluster_updated)

        # Start discovery
        await self._discovery.start()

        # Connect to discovered clusters
        await self._connect_to_clusters()

        # Start sync if enabled
        if self._sync:
            await self._sync.start()

        # Start health check loop
        self._health_task = asyncio.create_task(self._health_check_loop())

        self._running = True
        logger.info(f"Federation manager started with {len(self._clusters)} clusters")

    async def stop(self) -> None:
        """إيقاف الاتحاد"""
        self._running = False

        # Stop health check
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        # Stop sync
        if self._sync:
            await self._sync.stop()

        # Stop discovery
        await self._discovery.stop()

        # Disconnect from clusters
        for cluster in self._clusters.values():
            await cluster.disconnect()

        self._clusters.clear()

        logger.info("Federation manager stopped")

    # =========================================================================
    # Cluster Management
    # =========================================================================

    async def _connect_to_clusters(self) -> None:
        """الاتصال بالكتل المكتشفة"""
        for info in self._discovery.get_clusters():
            if info.cluster_id == self.config.cluster_id:
                continue  # Skip self

            await self._connect_cluster(info)

    async def _connect_cluster(self, info: ClusterInfo) -> bool:
        """الاتصال بكتلة"""
        try:
            cluster = FederatedCluster(
                info=info,
                api_key=self.config.api_key,
            )

            if await cluster.connect():
                self._clusters[info.cluster_id] = cluster
                self._router.add_cluster(cluster)

                if self._sync:
                    self._sync.add_cluster(cluster)

                self._stats["clusters_connected"] += 1
                logger.info(f"Connected to cluster {info.cluster_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to connect to {info.cluster_id}: {e}")

        return False

    async def _disconnect_cluster(self, cluster_id: str) -> None:
        """قطع الاتصال بكتلة"""
        cluster = self._clusters.pop(cluster_id, None)
        if cluster:
            await cluster.disconnect()
            self._router.remove_cluster(cluster_id)

            if self._sync:
                self._sync.remove_cluster(cluster_id)

            logger.info(f"Disconnected from cluster {cluster_id}")

    def _on_cluster_discovered(self, info: ClusterInfo) -> None:
        """عند اكتشاف كتلة جديدة"""
        if info.cluster_id not in self._clusters:
            asyncio.create_task(self._connect_cluster(info))

    def _on_cluster_removed(self, info: ClusterInfo) -> None:
        """عند إزالة كتلة"""
        asyncio.create_task(self._disconnect_cluster(info.cluster_id))

    def _on_cluster_updated(self, info: ClusterInfo) -> None:
        """عند تحديث كتلة"""
        cluster = self._clusters.get(info.cluster_id)
        if cluster:
            cluster.info = info

    # =========================================================================
    # Job Routing
    # =========================================================================

    async def submit_job(
        self,
        job_data: dict[str, Any],
        policy: Optional[RoutingPolicy] = None,
        prefer_local: bool = True,
    ) -> RoutingResult:
        """
        إرسال مهمة للاتحاد

        Args:
            job_data: بيانات المهمة
            policy: سياسة التوجيه
            prefer_local: تفضيل الكتلة المحلية

        Returns:
            نتيجة التوجيه
        """
        self._stats["jobs_routed"] += 1

        # Check if should prefer local
        if prefer_local:
            # Check local capacity
            # In real implementation, would check local cluster capacity
            pass

        result = await self._router.route(job_data, policy)

        if not result.success:
            self._stats["jobs_failed"] += 1

        return result

    async def submit_batch(
        self,
        jobs: list[dict[str, Any]],
        policy: Optional[RoutingPolicy] = None,
        distribute: bool = True,
    ) -> list[RoutingResult]:
        """
        إرسال مجموعة مهام

        Args:
            jobs: قائمة المهام
            policy: سياسة التوجيه
            distribute: توزيع على كتل مختلفة

        Returns:
            قائمة النتائج
        """
        if distribute:
            return await self._router.route_batch(jobs, policy, parallel=True)
        else:
            results = []
            for job in jobs:
                result = await self.submit_job(job, policy)
                results.append(result)
            return results

    async def get_job_status(
        self,
        job_id: str,
        cluster_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """الحصول على حالة مهمة"""
        if cluster_id:
            cluster = self._clusters.get(cluster_id)
            if cluster:
                return await cluster.get_job_status(job_id)
        else:
            # Search all clusters
            for cluster in self._clusters.values():
                try:
                    status = await cluster.get_job_status(job_id)
                    if status:
                        return status
                except Exception:
                    continue

        return None

    async def cancel_job(
        self,
        job_id: str,
        cluster_id: Optional[str] = None,
    ) -> bool:
        """إلغاء مهمة"""
        if cluster_id:
            cluster = self._clusters.get(cluster_id)
            if cluster:
                return await cluster.cancel_job(job_id)
        else:
            for cluster in self._clusters.values():
                if await cluster.cancel_job(job_id):
                    return True

        return False

    # =========================================================================
    # State Sync
    # =========================================================================

    async def sync_state(self) -> list[SyncResult]:
        """مزامنة الحالة"""
        if not self._sync:
            return []

        results = await self._sync.sync()
        self._stats["syncs_completed"] += len(results)
        return results

    def set_shared_state(self, key: str, value: Any) -> None:
        """تعيين حالة مشتركة"""
        if self._sync:
            self._sync.set_local(key, value)

    def get_shared_state(self, key: str) -> Optional[Any]:
        """الحصول على حالة مشتركة"""
        if self._sync:
            return self._sync.get_local(key)
        return None

    # =========================================================================
    # Health Monitoring
    # =========================================================================

    async def _health_check_loop(self) -> None:
        """حلقة فحص الصحة"""
        while self._running:
            try:
                await self._check_clusters_health()
                await asyncio.sleep(self.config.health_check_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def _check_clusters_health(self) -> None:
        """فحص صحة الكتل"""
        for cluster in list(self._clusters.values()):
            try:
                status = await cluster.check_health()
                await cluster.update_capacity()

                if status == ClusterStatus.UNREACHABLE:
                    logger.warning(f"Cluster {cluster.info.cluster_id} is unreachable")

            except Exception as e:
                logger.warning(
                    f"Health check failed for {cluster.info.cluster_id}: {e}"
                )
                cluster.info.status = ClusterStatus.UNHEALTHY

    # =========================================================================
    # Cluster Info
    # =========================================================================

    def get_clusters(self) -> list[ClusterInfo]:
        """الحصول على معلومات الكتل"""
        return [c.info for c in self._clusters.values()]

    def get_healthy_clusters(self) -> list[ClusterInfo]:
        """الحصول على الكتل الصحية"""
        return [
            c.info for c in self._clusters.values()
            if c.info.is_healthy()
        ]

    def get_cluster(self, cluster_id: str) -> Optional[ClusterInfo]:
        """الحصول على معلومات كتلة"""
        cluster = self._clusters.get(cluster_id)
        return cluster.info if cluster else None

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """الحصول على الحالة"""
        return {
            "running": self._running,
            "local_cluster": self.local_cluster.to_dict(),
            "clusters": {
                cid: c.info.to_dict()
                for cid, c in self._clusters.items()
            },
            "cluster_count": len(self._clusters),
            "healthy_count": len(self.get_healthy_clusters()),
            "stats": self._stats,
            "discovery": self._discovery.get_status(),
            "sync": self._sync.get_status() if self._sync else None,
            "router": self._router.get_stats(),
        }

    def get_topology(self) -> dict[str, Any]:
        """الحصول على topology الاتحاد"""
        nodes = [self.local_cluster.to_dict()]
        edges = []

        for cluster in self._clusters.values():
            nodes.append(cluster.info.to_dict())
            edges.append({
                "source": self.config.cluster_id,
                "target": cluster.info.cluster_id,
                "latency_ms": cluster.info.latency_ms,
                "status": cluster.info.status.value,
            })

        return {
            "nodes": nodes,
            "edges": edges,
        }

    def get_capacity_overview(self) -> dict[str, Any]:
        """الحصول على نظرة عامة على السعة"""
        total_workers = 0
        available_workers = 0
        total_jobs = 0
        pending_jobs = 0

        for cluster in self._clusters.values():
            cap = cluster.info.capacity
            total_workers += cap.total_workers
            available_workers += cap.available_workers
            total_jobs += cap.running_jobs
            pending_jobs += cap.pending_jobs

        return {
            "total_clusters": len(self._clusters) + 1,  # +1 for local
            "healthy_clusters": len(self.get_healthy_clusters()),
            "total_workers": total_workers,
            "available_workers": available_workers,
            "total_running_jobs": total_jobs,
            "total_pending_jobs": pending_jobs,
        }


# =============================================================================
# Helper Functions
# =============================================================================

def create_federation_manager(
    cluster_id: str,
    cluster_name: str,
    endpoint: str,
    static_clusters: Optional[list[dict[str, Any]]] = None,
    **kwargs,
) -> FederationManager:
    """
    إنشاء مدير اتحاد

    Args:
        cluster_id: معرف الكتلة المحلية
        cluster_name: اسم الكتلة
        endpoint: نقطة النهاية
        static_clusters: قائمة الكتل الثابتة
        **kwargs: إعدادات إضافية

    Returns:
        مدير الاتحاد
    """
    config = FederationConfig(
        cluster_id=cluster_id,
        cluster_name=cluster_name,
        endpoint=endpoint,
        discovery_method=DiscoveryMethod.STATIC,
        discovery_config={
            "static_clusters": static_clusters or [],
        },
        **kwargs,
    )

    return FederationManager(config)
