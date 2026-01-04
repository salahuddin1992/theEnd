"""
Job Router - موجه المهام
=========================

Cross-Cluster Job Routing
-------------------------

This module provides job routing across federated clusters.

يوفر هذا الملف توجيه المهام عبر الكتل المتحدة.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from distributed_cluster.federation.cluster import (
    FederatedCluster,
)

logger = logging.getLogger(__name__)


class RoutingStrategy(str, Enum):
    """استراتيجية التوجيه / Routing strategy"""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    LOWEST_LATENCY = "lowest_latency"
    RANDOM = "random"
    WEIGHTED = "weighted"
    AFFINITY = "affinity"
    LOCALITY = "locality"
    CUSTOM = "custom"


class RoutingStatus(str, Enum):
    """حالة التوجيه / Routing status"""
    SUCCESS = "success"
    FAILED = "failed"
    NO_CLUSTER = "no_cluster"
    RETRIED = "retried"


@dataclass
class RoutingResult:
    """
    نتيجة التوجيه
    Routing Result
    """
    status: RoutingStatus
    cluster_id: Optional[str] = None
    cluster_name: Optional[str] = None
    job_id: Optional[str] = None
    attempts: int = 1
    latency_ms: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "cluster_id": self.cluster_id,
            "cluster_name": self.cluster_name,
            "job_id": self.job_id,
            "attempts": self.attempts,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RoutingPolicy:
    """
    سياسة التوجيه
    Routing Policy
    """
    strategy: RoutingStrategy = RoutingStrategy.LEAST_LOADED

    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: float = 1.0

    # Filtering
    required_features: list[str] = field(default_factory=list)
    preferred_regions: list[str] = field(default_factory=list)
    excluded_clusters: list[str] = field(default_factory=list)

    # Resource requirements
    min_cpu_cores: float = 0.0
    min_memory_gb: float = 0.0
    require_gpu: bool = False

    # Weights for weighted routing
    weights: dict[str, float] = field(default_factory=dict)

    # Affinity
    affinity_key: Optional[str] = None
    affinity_cluster: Optional[str] = None

    # Locality preference
    prefer_local: bool = True
    local_region: Optional[str] = None

    # Load thresholds
    max_load_score: float = 0.9
    max_queue_depth: int = 1000


class RoutingAlgorithm(ABC):
    """قاعدة خوارزمية التوجيه"""

    @abstractmethod
    def select(
        self,
        clusters: list[FederatedCluster],
        policy: RoutingPolicy,
        job_data: dict[str, Any],
    ) -> Optional[FederatedCluster]:
        """اختيار كتلة"""
        pass


class RoundRobinRouter(RoutingAlgorithm):
    """توجيه دائري"""

    def __init__(self):
        self._index = 0
        self._lock = asyncio.Lock()

    def select(
        self,
        clusters: list[FederatedCluster],
        policy: RoutingPolicy,
        job_data: dict[str, Any],
    ) -> Optional[FederatedCluster]:
        if not clusters:
            return None

        # Simple round robin
        cluster = clusters[self._index % len(clusters)]
        self._index += 1
        return cluster


class LeastLoadedRouter(RoutingAlgorithm):
    """توجيه للأقل حملاً"""

    def select(
        self,
        clusters: list[FederatedCluster],
        policy: RoutingPolicy,
        job_data: dict[str, Any],
    ) -> Optional[FederatedCluster]:
        if not clusters:
            return None

        # Filter by load threshold
        eligible = [
            c for c in clusters
            if c.info.capacity.get_load_score() < policy.max_load_score
        ]

        if not eligible:
            eligible = clusters

        # Select least loaded
        return min(eligible, key=lambda c: c.info.capacity.get_load_score())


class LowestLatencyRouter(RoutingAlgorithm):
    """توجيه للأقل تأخيراً"""

    def select(
        self,
        clusters: list[FederatedCluster],
        policy: RoutingPolicy,
        job_data: dict[str, Any],
    ) -> Optional[FederatedCluster]:
        if not clusters:
            return None

        return min(clusters, key=lambda c: c.info.latency_ms)


class RandomRouter(RoutingAlgorithm):
    """توجيه عشوائي"""

    def select(
        self,
        clusters: list[FederatedCluster],
        policy: RoutingPolicy,
        job_data: dict[str, Any],
    ) -> Optional[FederatedCluster]:
        if not clusters:
            return None

        return random.choice(clusters)


class WeightedRouter(RoutingAlgorithm):
    """توجيه موزون"""

    def select(
        self,
        clusters: list[FederatedCluster],
        policy: RoutingPolicy,
        job_data: dict[str, Any],
    ) -> Optional[FederatedCluster]:
        if not clusters:
            return None

        # Build weighted list
        weighted_clusters = []
        for cluster in clusters:
            weight = policy.weights.get(cluster.info.cluster_id, 1.0)
            weighted_clusters.extend([cluster] * int(weight * 10))

        if not weighted_clusters:
            return random.choice(clusters)

        return random.choice(weighted_clusters)


class LocalityRouter(RoutingAlgorithm):
    """توجيه حسب الموقع"""

    def select(
        self,
        clusters: list[FederatedCluster],
        policy: RoutingPolicy,
        job_data: dict[str, Any],
    ) -> Optional[FederatedCluster]:
        if not clusters:
            return None

        # Prefer local region
        if policy.local_region:
            local = [
                c for c in clusters
                if c.info.region == policy.local_region
            ]
            if local:
                return min(local, key=lambda c: c.info.capacity.get_load_score())

        # Prefer preferred regions
        if policy.preferred_regions:
            preferred = [
                c for c in clusters
                if c.info.region in policy.preferred_regions
            ]
            if preferred:
                return min(preferred, key=lambda c: c.info.capacity.get_load_score())

        # Fall back to least loaded
        return min(clusters, key=lambda c: c.info.capacity.get_load_score())


class JobRouter:
    """
    موجه المهام
    Job Router

    يوجه المهام للكتل المتحدة بناءً على السياسات.
    Routes jobs to federated clusters based on policies.
    """

    def __init__(
        self,
        default_policy: Optional[RoutingPolicy] = None,
    ):
        """
        تهيئة الموجه

        Args:
            default_policy: السياسة الافتراضية
        """
        self.default_policy = default_policy or RoutingPolicy()

        self._clusters: dict[str, FederatedCluster] = {}
        self._algorithms: dict[RoutingStrategy, RoutingAlgorithm] = {
            RoutingStrategy.ROUND_ROBIN: RoundRobinRouter(),
            RoutingStrategy.LEAST_LOADED: LeastLoadedRouter(),
            RoutingStrategy.LOWEST_LATENCY: LowestLatencyRouter(),
            RoutingStrategy.RANDOM: RandomRouter(),
            RoutingStrategy.WEIGHTED: WeightedRouter(),
            RoutingStrategy.LOCALITY: LocalityRouter(),
        }

        self._custom_algorithm: Optional[RoutingAlgorithm] = None

        # Stats
        self._stats = {
            "total_routed": 0,
            "successful": 0,
            "failed": 0,
            "retries": 0,
        }

    # =========================================================================
    # Cluster Management
    # =========================================================================

    def add_cluster(self, cluster: FederatedCluster) -> None:
        """إضافة كتلة"""
        self._clusters[cluster.info.cluster_id] = cluster
        logger.info(f"Added cluster to router: {cluster.info.cluster_id}")

    def remove_cluster(self, cluster_id: str) -> None:
        """إزالة كتلة"""
        self._clusters.pop(cluster_id, None)

    def get_cluster(self, cluster_id: str) -> Optional[FederatedCluster]:
        """الحصول على كتلة"""
        return self._clusters.get(cluster_id)

    def set_custom_algorithm(self, algorithm: RoutingAlgorithm) -> None:
        """تعيين خوارزمية مخصصة"""
        self._custom_algorithm = algorithm

    # =========================================================================
    # Routing
    # =========================================================================

    async def route(
        self,
        job_data: dict[str, Any],
        policy: Optional[RoutingPolicy] = None,
    ) -> RoutingResult:
        """
        توجيه مهمة

        Args:
            job_data: بيانات المهمة
            policy: سياسة التوجيه

        Returns:
            نتيجة التوجيه
        """
        policy = policy or self.default_policy
        self._stats["total_routed"] += 1

        # Filter eligible clusters
        eligible = self._filter_clusters(policy, job_data)

        if not eligible:
            self._stats["failed"] += 1
            return RoutingResult(
                status=RoutingStatus.NO_CLUSTER,
                error="No eligible clusters available",
            )

        # Try routing with retries
        attempts = 0
        last_error = None

        while attempts <= policy.max_retries:
            attempts += 1

            # Select cluster
            cluster = self._select_cluster(eligible, policy, job_data)

            if not cluster:
                continue

            try:
                # Submit job
                import time
                start = time.time()
                result = await cluster.submit_job(job_data)
                latency = (time.time() - start) * 1000

                self._stats["successful"] += 1

                return RoutingResult(
                    status=RoutingStatus.SUCCESS,
                    cluster_id=cluster.info.cluster_id,
                    cluster_name=cluster.info.cluster_name,
                    job_id=result.get("job_id"),
                    attempts=attempts,
                    latency_ms=latency,
                )

            except Exception as e:
                last_error = str(e)
                self._stats["retries"] += 1
                logger.warning(
                    f"Routing attempt {attempts} failed for {cluster.info.cluster_id}: {e}"
                )

                # Remove from eligible for next attempt
                eligible = [c for c in eligible if c != cluster]

                if attempts <= policy.max_retries and eligible:
                    await asyncio.sleep(policy.retry_delay_seconds)

        self._stats["failed"] += 1

        return RoutingResult(
            status=RoutingStatus.FAILED,
            attempts=attempts,
            error=last_error,
        )

    def _filter_clusters(
        self,
        policy: RoutingPolicy,
        job_data: dict[str, Any],
    ) -> list[FederatedCluster]:
        """تصفية الكتل المؤهلة"""
        eligible = []

        for cluster in self._clusters.values():
            # Check health
            if not cluster.info.is_available():
                continue

            # Check exclusions
            if cluster.info.cluster_id in policy.excluded_clusters:
                continue

            # Check required features
            if policy.required_features:
                if not all(
                    f in cluster.info.supported_features
                    for f in policy.required_features
                ):
                    continue

            # Check capacity
            capacity = cluster.info.capacity
            if not capacity.can_accept_job(
                required_cpu=policy.min_cpu_cores,
                required_memory_gb=policy.min_memory_gb,
                required_gpu=1 if policy.require_gpu else 0,
            ):
                continue

            # Check queue depth
            if capacity.queue_depth > policy.max_queue_depth:
                continue

            eligible.append(cluster)

        return eligible

    def _select_cluster(
        self,
        clusters: list[FederatedCluster],
        policy: RoutingPolicy,
        job_data: dict[str, Any],
    ) -> Optional[FederatedCluster]:
        """اختيار كتلة"""
        # Check affinity first
        if policy.affinity_cluster:
            for cluster in clusters:
                if cluster.info.cluster_id == policy.affinity_cluster:
                    return cluster

        # Use routing algorithm
        if policy.strategy == RoutingStrategy.CUSTOM and self._custom_algorithm:
            return self._custom_algorithm.select(clusters, policy, job_data)

        algorithm = self._algorithms.get(policy.strategy)
        if algorithm:
            return algorithm.select(clusters, policy, job_data)

        # Default to least loaded
        return self._algorithms[RoutingStrategy.LEAST_LOADED].select(
            clusters, policy, job_data
        )

    # =========================================================================
    # Batch Routing
    # =========================================================================

    async def route_batch(
        self,
        jobs: list[dict[str, Any]],
        policy: Optional[RoutingPolicy] = None,
        parallel: bool = True,
    ) -> list[RoutingResult]:
        """
        توجيه مجموعة مهام

        Args:
            jobs: قائمة المهام
            policy: سياسة التوجيه
            parallel: التوجيه بالتوازي

        Returns:
            قائمة النتائج
        """
        if parallel:
            tasks = [self.route(job, policy) for job in jobs]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for job in jobs:
                result = await self.route(job, policy)
                results.append(result)
            return results

    # =========================================================================
    # Stats
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """الحصول على الإحصائيات"""
        success_rate = (
            self._stats["successful"] / self._stats["total_routed"]
            if self._stats["total_routed"] > 0
            else 0
        )

        return {
            **self._stats,
            "success_rate": success_rate,
            "cluster_count": len(self._clusters),
            "clusters": {
                cid: c.get_stats()
                for cid, c in self._clusters.items()
            },
        }

    def get_cluster_stats(self) -> dict[str, dict[str, Any]]:
        """الحصول على إحصائيات الكتل"""
        return {
            cid: {
                "status": c.info.status.value,
                "load_score": c.info.capacity.get_load_score(),
                "available_workers": c.info.capacity.available_workers,
                "latency_ms": c.info.latency_ms,
            }
            for cid, c in self._clusters.items()
        }
