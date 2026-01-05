"""
Kubernetes Controller - متحكم Kubernetes
========================================

Kubernetes Controller
---------------------

This module implements the Kubernetes controller for automatic management.

يطبق هذا الملف متحكم Kubernetes للإدارة التلقائية.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from distributed_cluster.kubernetes.crds import (
    API_GROUP,
    API_VERSION,
    ClusterCRD,
    ClusterPhase,
)

logger = logging.getLogger(__name__)


class ReconcileResult(str, Enum):
    """نتيجة المصالحة / Reconciliation result"""

    SUCCESS = "success"
    REQUEUE = "requeue"
    REQUEUE_AFTER = "requeue_after"
    ERROR = "error"
    SKIP = "skip"


@dataclass
class ControllerConfig:
    """
    إعدادات المتحكم
    Controller configuration
    """

    # Reconciliation
    reconcile_interval_seconds: int = 30
    requeue_delay_seconds: int = 5
    max_concurrent_reconciles: int = 3

    # Timeouts
    sync_timeout_seconds: int = 60
    status_update_timeout_seconds: int = 10

    # Retry
    max_retries: int = 5
    retry_base_delay_seconds: float = 1.0
    retry_max_delay_seconds: float = 60.0

    # Leader election
    leader_election_enabled: bool = True
    leader_election_namespace: str = "kube-system"
    leader_election_name: str = "distributed-cluster-controller"
    leader_election_lease_duration: int = 15
    leader_election_renew_deadline: int = 10
    leader_election_retry_period: int = 2

    # Metrics
    metrics_enabled: bool = True
    metrics_port: int = 8080

    def to_dict(self) -> dict[str, Any]:
        return {
            "reconcileInterval": self.reconcile_interval_seconds,
            "requeueDelay": self.requeue_delay_seconds,
            "maxConcurrentReconciles": self.max_concurrent_reconciles,
            "leaderElection": {
                "enabled": self.leader_election_enabled,
                "namespace": self.leader_election_namespace,
                "name": self.leader_election_name,
            },
            "metrics": {
                "enabled": self.metrics_enabled,
                "port": self.metrics_port,
            },
        }


@dataclass
class ReconcileRequest:
    """طلب مصالحة"""

    name: str
    namespace: str
    resource_type: str
    event_type: str  # ADDED, MODIFIED, DELETED


class ClusterController:
    """
    متحكم الكلاستر
    Cluster Controller

    يراقب موارد CRD ويديرها تلقائياً.
    Watches CRD resources and manages them automatically.
    """

    def __init__(
        self,
        config: Optional[ControllerConfig] = None,
        kubeconfig: Optional[str] = None,
    ):
        """
        تهيئة المتحكم

        Args:
            config: إعدادات المتحكم
            kubeconfig: مسار kubeconfig
        """
        self.config = config or ControllerConfig()
        self.kubeconfig = kubeconfig

        # Kubernetes clients
        self._core_api = None
        self._apps_api = None
        self._custom_api = None

        # State
        self._running = False
        self._is_leader = False
        self._work_queue: asyncio.Queue[ReconcileRequest] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []

        # Handlers
        self._reconcilers: dict[str, Callable] = {}

        # Metrics
        self._reconcile_count = 0
        self._reconcile_errors = 0
        self._last_reconcile_time: Optional[datetime] = None

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> bool:
        """بدء المتحكم"""
        try:
            from kubernetes import config
            from kubernetes.client import (
                AppsV1Api,
                CoreV1Api,
                CustomObjectsApi,
            )

            # Load config
            if self.kubeconfig:
                config.load_kube_config(config_file=self.kubeconfig)
            else:
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config()

            # Create clients
            self._core_api = CoreV1Api()
            self._apps_api = AppsV1Api()
            self._custom_api = CustomObjectsApi()

            # Start workers
            self._running = True
            for i in range(self.config.max_concurrent_reconciles):
                worker = asyncio.create_task(self._worker_loop(i))
                self._workers.append(worker)

            # Start watchers
            asyncio.create_task(self._watch_clusters())

            # Register default reconcilers
            self._register_default_reconcilers()

            logger.info("ClusterController started")
            return True

        except ImportError:
            logger.error("kubernetes package not installed")
            return False
        except Exception as e:
            logger.error(f"Failed to start controller: {e}")
            return False

    async def stop(self) -> None:
        """إيقاف المتحكم"""
        self._running = False

        # Cancel workers
        for worker in self._workers:
            worker.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        logger.info("ClusterController stopped")

    # =========================================================================
    # Reconciliation
    # =========================================================================

    def register_reconciler(
        self,
        resource_type: str,
        handler: Callable[[ReconcileRequest], ReconcileResult],
    ) -> None:
        """تسجيل معالج مصالحة"""
        self._reconcilers[resource_type] = handler
        logger.info(f"Registered reconciler for {resource_type}")

    def _register_default_reconcilers(self) -> None:
        """تسجيل المعالجات الافتراضية"""
        self.register_reconciler("DistributedCluster", self._reconcile_cluster)
        self.register_reconciler("ClusterWorker", self._reconcile_worker)
        self.register_reconciler("ClusterJob", self._reconcile_job)

    async def _worker_loop(self, worker_id: int) -> None:
        """حلقة العامل"""
        logger.info(f"Controller worker {worker_id} started")

        while self._running:
            try:
                request = await asyncio.wait_for(
                    self._work_queue.get(),
                    timeout=5.0,
                )

                await self._process_request(request)
                self._work_queue.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

    async def _process_request(self, request: ReconcileRequest) -> None:
        """معالجة طلب مصالحة"""
        handler = self._reconcilers.get(request.resource_type)
        if not handler:
            logger.warning(f"No reconciler for {request.resource_type}")
            return

        start_time = datetime.now(timezone.utc)
        self._reconcile_count += 1

        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(request)
            else:
                result = handler(request)

            self._last_reconcile_time = datetime.now(timezone.utc)

            if result == ReconcileResult.REQUEUE:
                await asyncio.sleep(self.config.requeue_delay_seconds)
                await self._work_queue.put(request)
            elif result == ReconcileResult.ERROR:
                self._reconcile_errors += 1

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.debug(
                f"Reconciled {request.resource_type}/{request.name} " f"in {duration:.2f}s with result {result.value}"
            )

        except Exception as e:
            self._reconcile_errors += 1
            logger.error(f"Reconcile error for {request.name}: {e}")

    async def _reconcile_cluster(
        self,
        request: ReconcileRequest,
    ) -> ReconcileResult:
        """
        مصالحة الكلاستر
        Reconcile cluster resource
        """
        if request.event_type == "DELETED":
            return await self._handle_cluster_deletion(request)

        try:
            # Get cluster resource
            cluster_data = self._custom_api.get_namespaced_custom_object(
                group=API_GROUP,
                version=API_VERSION,
                namespace=request.namespace,
                plural="distributedclusters",
                name=request.name,
            )

            cluster = ClusterCRD.from_dict(cluster_data)

            # Ensure master deployment
            await self._ensure_master_deployment(cluster)

            # Ensure worker statefulset
            await self._ensure_worker_statefulset(cluster)

            # Ensure services
            await self._ensure_services(cluster)

            # Update status
            await self._update_cluster_status(cluster)

            return ReconcileResult.SUCCESS

        except Exception as e:
            logger.error(f"Failed to reconcile cluster {request.name}: {e}")
            return ReconcileResult.ERROR

    async def _reconcile_worker(
        self,
        request: ReconcileRequest,
    ) -> ReconcileResult:
        """مصالحة العامل"""
        # Worker reconciliation logic
        return ReconcileResult.SUCCESS

    async def _reconcile_job(
        self,
        request: ReconcileRequest,
    ) -> ReconcileResult:
        """مصالحة المهمة"""
        # Job reconciliation logic
        return ReconcileResult.SUCCESS

    # =========================================================================
    # Resource Management
    # =========================================================================

    async def _ensure_master_deployment(self, cluster: ClusterCRD) -> None:
        """ضمان وجود deployment الماستر"""
        deployment_name = f"{cluster.metadata.name}-master"

        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": deployment_name,
                "namespace": cluster.metadata.namespace,
                "labels": {
                    "app": "distributed-cluster",
                    "component": "master",
                    "cluster": cluster.metadata.name,
                },
                "ownerReferences": [
                    {
                        "apiVersion": cluster.api_version,
                        "kind": cluster.kind,
                        "name": cluster.metadata.name,
                        "uid": cluster.metadata.uid,
                        "controller": True,
                    }
                ],
            },
            "spec": {
                "replicas": 1,
                "selector": {
                    "matchLabels": {
                        "app": "distributed-cluster",
                        "component": "master",
                        "cluster": cluster.metadata.name,
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "distributed-cluster",
                            "component": "master",
                            "cluster": cluster.metadata.name,
                        }
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "master",
                                "image": cluster.spec.image,
                                "imagePullPolicy": cluster.spec.image_pull_policy,
                                "ports": [{"containerPort": cluster.spec.master_port}],
                                "resources": cluster.spec.master_resources.to_dict(),
                                "livenessProbe": {
                                    "httpGet": {
                                        "path": cluster.spec.liveness_probe_path,
                                        "port": cluster.spec.master_port,
                                    },
                                    "periodSeconds": cluster.spec.probe_interval,
                                    "timeoutSeconds": cluster.spec.probe_timeout,
                                },
                                "readinessProbe": {
                                    "httpGet": {
                                        "path": cluster.spec.readiness_probe_path,
                                        "port": cluster.spec.master_port,
                                    },
                                    "periodSeconds": cluster.spec.probe_interval,
                                    "timeoutSeconds": cluster.spec.probe_timeout,
                                },
                                "env": [
                                    {"name": "CLUSTER_ROLE", "value": "master"},
                                    {"name": "CLUSTER_NAME", "value": cluster.metadata.name},
                                ],
                            }
                        ],
                    },
                },
            },
        }

        try:
            self._apps_api.read_namespaced_deployment(
                name=deployment_name,
                namespace=cluster.metadata.namespace,
            )
            # Update existing
            self._apps_api.patch_namespaced_deployment(
                name=deployment_name,
                namespace=cluster.metadata.namespace,
                body=deployment,
            )
        except Exception:
            # Create new
            self._apps_api.create_namespaced_deployment(
                namespace=cluster.metadata.namespace,
                body=deployment,
            )

    async def _ensure_worker_statefulset(self, cluster: ClusterCRD) -> None:
        """ضمان وجود StatefulSet للعمال"""
        sts_name = f"{cluster.metadata.name}-worker"

        statefulset = {
            "apiVersion": "apps/v1",
            "kind": "StatefulSet",
            "metadata": {
                "name": sts_name,
                "namespace": cluster.metadata.namespace,
                "labels": {
                    "app": "distributed-cluster",
                    "component": "worker",
                    "cluster": cluster.metadata.name,
                },
            },
            "spec": {
                "serviceName": sts_name,
                "replicas": cluster.spec.replicas,
                "selector": {
                    "matchLabels": {
                        "app": "distributed-cluster",
                        "component": "worker",
                        "cluster": cluster.metadata.name,
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "distributed-cluster",
                            "component": "worker",
                            "cluster": cluster.metadata.name,
                        }
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "worker",
                                "image": cluster.spec.image,
                                "ports": [{"containerPort": cluster.spec.worker_port}],
                                "resources": cluster.spec.worker_resources.to_dict(),
                                "env": [
                                    {"name": "CLUSTER_ROLE", "value": "worker"},
                                    {"name": "CLUSTER_NAME", "value": cluster.metadata.name},
                                    {
                                        "name": "MASTER_URL",
                                        "value": f"http://{cluster.metadata.name}-master:{cluster.spec.master_port}",
                                    },
                                ],
                            }
                        ],
                    },
                },
            },
        }

        try:
            self._apps_api.read_namespaced_stateful_set(
                name=sts_name,
                namespace=cluster.metadata.namespace,
            )
            self._apps_api.patch_namespaced_stateful_set(
                name=sts_name,
                namespace=cluster.metadata.namespace,
                body=statefulset,
            )
        except Exception:
            self._apps_api.create_namespaced_stateful_set(
                namespace=cluster.metadata.namespace,
                body=statefulset,
            )

    async def _ensure_services(self, cluster: ClusterCRD) -> None:
        """ضمان وجود Services"""
        # Master service
        master_svc = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"{cluster.metadata.name}-master",
                "namespace": cluster.metadata.namespace,
            },
            "spec": {
                "type": cluster.spec.service_type,
                "ports": [
                    {
                        "port": cluster.spec.master_port,
                        "targetPort": cluster.spec.master_port,
                        "name": "http",
                    }
                ],
                "selector": {
                    "app": "distributed-cluster",
                    "component": "master",
                    "cluster": cluster.metadata.name,
                },
            },
        }

        try:
            self._core_api.create_namespaced_service(
                namespace=cluster.metadata.namespace,
                body=master_svc,
            )
        except Exception:
            pass  # Already exists

    async def _update_cluster_status(self, cluster: ClusterCRD) -> None:
        """تحديث حالة الكلاستر"""
        # Get worker pods
        try:
            pods = self._core_api.list_namespaced_pod(
                namespace=cluster.metadata.namespace,
                label_selector=f"app=distributed-cluster,cluster={cluster.metadata.name},component=worker",
            )

            ready_workers = sum(
                1
                for pod in pods.items
                if pod.status.phase == "Running" and all(c.ready for c in (pod.status.container_statuses or []))
            )

            total_workers = len(pods.items)

            # Determine phase
            if total_workers == 0:
                phase = ClusterPhase.PROVISIONING
            elif ready_workers == total_workers:
                phase = ClusterPhase.RUNNING
            elif ready_workers > 0:
                phase = ClusterPhase.DEGRADED
            else:
                phase = ClusterPhase.FAILED

            # Update status
            status = {
                "status": {
                    "phase": phase.value,
                    "readyWorkers": ready_workers,
                    "totalWorkers": total_workers,
                    "lastUpdated": datetime.now(timezone.utc).isoformat(),
                }
            }

            self._custom_api.patch_namespaced_custom_object_status(
                group=API_GROUP,
                version=API_VERSION,
                namespace=cluster.metadata.namespace,
                plural="distributedclusters",
                name=cluster.metadata.name,
                body=status,
            )

        except Exception as e:
            logger.error(f"Failed to update cluster status: {e}")

    async def _handle_cluster_deletion(
        self,
        request: ReconcileRequest,
    ) -> ReconcileResult:
        """معالجة حذف الكلاستر"""
        logger.info(f"Handling deletion of cluster {request.name}")
        # Cleanup logic here
        return ReconcileResult.SUCCESS

    # =========================================================================
    # Watchers
    # =========================================================================

    async def _watch_clusters(self) -> None:
        """مراقبة موارد الكلاستر"""
        from kubernetes import watch

        w = watch.Watch()

        while self._running:
            try:
                for event in w.stream(
                    self._custom_api.list_cluster_custom_object,
                    group=API_GROUP,
                    version=API_VERSION,
                    plural="distributedclusters",
                    timeout_seconds=60,
                ):
                    event_type = event["type"]
                    obj = event["object"]
                    metadata = obj.get("metadata", {})

                    request = ReconcileRequest(
                        name=metadata.get("name", ""),
                        namespace=metadata.get("namespace", "default"),
                        resource_type="DistributedCluster",
                        event_type=event_type,
                    )

                    await self._work_queue.put(request)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watch error: {e}")
                await asyncio.sleep(5)

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """الحصول على حالة المتحكم"""
        return {
            "running": self._running,
            "is_leader": self._is_leader,
            "queue_size": self._work_queue.qsize(),
            "reconcile_count": self._reconcile_count,
            "reconcile_errors": self._reconcile_errors,
            "last_reconcile_time": self._last_reconcile_time.isoformat() if self._last_reconcile_time else None,
            "workers": len(self._workers),
        }
