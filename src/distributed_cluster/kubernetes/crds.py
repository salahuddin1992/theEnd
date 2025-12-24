"""
Custom Resource Definitions - تعريفات الموارد المخصصة
====================================================

Kubernetes CRDs
---------------

This module defines Custom Resource Definitions for the distributed cluster.

يحدد هذا الملف تعريفات الموارد المخصصة للكلاستر الموزع.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

# API Version and Group
API_GROUP = "cluster.distributed.io"
API_VERSION = "v1alpha1"


class ClusterPhase(str, Enum):
    """مرحلة الكلاستر / Cluster phase"""
    PENDING = "Pending"
    PROVISIONING = "Provisioning"
    RUNNING = "Running"
    SCALING = "Scaling"
    UPDATING = "Updating"
    DEGRADED = "Degraded"
    FAILED = "Failed"
    TERMINATING = "Terminating"


class WorkerPhase(str, Enum):
    """مرحلة العامل / Worker phase"""
    PENDING = "Pending"
    STARTING = "Starting"
    RUNNING = "Running"
    DRAINING = "Draining"
    TERMINATED = "Terminated"
    FAILED = "Failed"


class JobPhase(str, Enum):
    """مرحلة المهمة / Job phase"""
    PENDING = "Pending"
    QUEUED = "Queued"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass
class ObjectMeta:
    """
    بيانات وصفية للكائن
    Kubernetes object metadata
    """
    name: str
    namespace: str = "default"
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    uid: str = ""
    resource_version: str = ""
    generation: int = 1
    creation_timestamp: Optional[datetime] = None
    deletion_timestamp: Optional[datetime] = None
    finalizers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس"""
        return {
            "name": self.name,
            "namespace": self.namespace,
            "labels": self.labels,
            "annotations": self.annotations,
            "uid": self.uid,
            "resourceVersion": self.resource_version,
            "generation": self.generation,
            "creationTimestamp": self.creation_timestamp.isoformat() if self.creation_timestamp else None,
            "deletionTimestamp": self.deletion_timestamp.isoformat() if self.deletion_timestamp else None,
            "finalizers": self.finalizers,
        }


@dataclass
class ResourceRequirements:
    """
    متطلبات الموارد
    Resource requirements
    """
    cpu: str = "100m"
    memory: str = "128Mi"
    gpu: int = 0
    storage: str = "1Gi"

    def to_dict(self) -> dict[str, Any]:
        return {
            "requests": {
                "cpu": self.cpu,
                "memory": self.memory,
                "nvidia.com/gpu": str(self.gpu) if self.gpu > 0 else None,
            },
            "limits": {
                "cpu": self.cpu,
                "memory": self.memory,
                "nvidia.com/gpu": str(self.gpu) if self.gpu > 0 else None,
            },
        }


# =============================================================================
# Cluster CRD
# =============================================================================

@dataclass
class ClusterSpec:
    """
    مواصفات الكلاستر
    Cluster specification
    """
    # Worker configuration
    replicas: int = 3
    min_replicas: int = 1
    max_replicas: int = 10

    # Auto-scaling
    auto_scaling_enabled: bool = True
    target_cpu_utilization: int = 80
    target_memory_utilization: int = 80
    scale_up_cooldown: int = 300
    scale_down_cooldown: int = 600

    # Resources
    worker_resources: ResourceRequirements = field(default_factory=ResourceRequirements)
    master_resources: ResourceRequirements = field(default_factory=ResourceRequirements)

    # Image
    image: str = "distributed-cluster:latest"
    image_pull_policy: str = "IfNotPresent"
    image_pull_secrets: list[str] = field(default_factory=list)

    # Networking
    service_type: str = "ClusterIP"
    master_port: int = 8080
    worker_port: int = 8081

    # Storage
    persistent_volume_claim: Optional[str] = None
    storage_class: str = "standard"

    # Configuration
    config_map: Optional[str] = None
    secret: Optional[str] = None
    env_vars: dict[str, str] = field(default_factory=dict)

    # Health
    liveness_probe_path: str = "/health"
    readiness_probe_path: str = "/ready"
    probe_interval: int = 10
    probe_timeout: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "replicas": self.replicas,
            "minReplicas": self.min_replicas,
            "maxReplicas": self.max_replicas,
            "autoScaling": {
                "enabled": self.auto_scaling_enabled,
                "targetCPUUtilization": self.target_cpu_utilization,
                "targetMemoryUtilization": self.target_memory_utilization,
                "scaleUpCooldown": self.scale_up_cooldown,
                "scaleDownCooldown": self.scale_down_cooldown,
            },
            "workerResources": self.worker_resources.to_dict(),
            "masterResources": self.master_resources.to_dict(),
            "image": self.image,
            "imagePullPolicy": self.image_pull_policy,
            "imagePullSecrets": self.image_pull_secrets,
            "service": {
                "type": self.service_type,
                "masterPort": self.master_port,
                "workerPort": self.worker_port,
            },
            "storage": {
                "persistentVolumeClaim": self.persistent_volume_claim,
                "storageClass": self.storage_class,
            },
            "config": {
                "configMap": self.config_map,
                "secret": self.secret,
                "envVars": self.env_vars,
            },
            "health": {
                "livenessProbe": self.liveness_probe_path,
                "readinessProbe": self.readiness_probe_path,
                "probeInterval": self.probe_interval,
                "probeTimeout": self.probe_timeout,
            },
        }


@dataclass
class ClusterStatus:
    """
    حالة الكلاستر
    Cluster status
    """
    phase: ClusterPhase = ClusterPhase.PENDING
    ready_workers: int = 0
    total_workers: int = 0
    active_jobs: int = 0
    pending_jobs: int = 0
    master_ready: bool = False
    last_updated: Optional[datetime] = None
    conditions: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "readyWorkers": self.ready_workers,
            "totalWorkers": self.total_workers,
            "activeJobs": self.active_jobs,
            "pendingJobs": self.pending_jobs,
            "masterReady": self.master_ready,
            "lastUpdated": self.last_updated.isoformat() if self.last_updated else None,
            "conditions": self.conditions,
            "message": self.message,
        }


@dataclass
class ClusterCRD:
    """
    Custom Resource Definition للكلاستر
    Cluster Custom Resource Definition
    """
    api_version: str = f"{API_GROUP}/{API_VERSION}"
    kind: str = "DistributedCluster"
    metadata: ObjectMeta = field(default_factory=lambda: ObjectMeta(name="default"))
    spec: ClusterSpec = field(default_factory=ClusterSpec)
    status: ClusterStatus = field(default_factory=ClusterStatus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata.to_dict(),
            "spec": self.spec.to_dict(),
            "status": self.status.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClusterCRD:
        """إنشاء من قاموس"""
        # Parse metadata
        meta_data = data.get("metadata", {})
        metadata = ObjectMeta(
            name=meta_data.get("name", ""),
            namespace=meta_data.get("namespace", "default"),
            labels=meta_data.get("labels", {}),
            annotations=meta_data.get("annotations", {}),
            uid=meta_data.get("uid", ""),
            resource_version=meta_data.get("resourceVersion", ""),
        )

        # Parse spec
        spec_data = data.get("spec", {})
        spec = ClusterSpec(
            replicas=spec_data.get("replicas", 3),
            min_replicas=spec_data.get("minReplicas", 1),
            max_replicas=spec_data.get("maxReplicas", 10),
            image=spec_data.get("image", "distributed-cluster:latest"),
        )

        # Parse status
        status_data = data.get("status", {})
        phase_str = status_data.get("phase", "Pending")
        try:
            phase = ClusterPhase(phase_str)
        except ValueError:
            phase = ClusterPhase.PENDING

        status = ClusterStatus(
            phase=phase,
            ready_workers=status_data.get("readyWorkers", 0),
            total_workers=status_data.get("totalWorkers", 0),
        )

        return cls(
            metadata=metadata,
            spec=spec,
            status=status,
        )

    @classmethod
    def get_crd_definition(cls) -> dict[str, Any]:
        """الحصول على تعريف CRD"""
        return {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {
                "name": f"distributedclusters.{API_GROUP}",
            },
            "spec": {
                "group": API_GROUP,
                "versions": [
                    {
                        "name": API_VERSION,
                        "served": True,
                        "storage": True,
                        "schema": {
                            "openAPIV3Schema": {
                                "type": "object",
                                "properties": {
                                    "spec": {
                                        "type": "object",
                                        "properties": {
                                            "replicas": {"type": "integer", "minimum": 1},
                                            "minReplicas": {"type": "integer", "minimum": 1},
                                            "maxReplicas": {"type": "integer", "minimum": 1},
                                            "image": {"type": "string"},
                                        },
                                    },
                                    "status": {
                                        "type": "object",
                                        "properties": {
                                            "phase": {"type": "string"},
                                            "readyWorkers": {"type": "integer"},
                                            "totalWorkers": {"type": "integer"},
                                        },
                                    },
                                },
                            },
                        },
                        "subresources": {
                            "status": {},
                            "scale": {
                                "specReplicasPath": ".spec.replicas",
                                "statusReplicasPath": ".status.totalWorkers",
                                "labelSelectorPath": ".status.selector",
                            },
                        },
                    },
                ],
                "scope": "Namespaced",
                "names": {
                    "plural": "distributedclusters",
                    "singular": "distributedcluster",
                    "kind": "DistributedCluster",
                    "shortNames": ["dc", "cluster"],
                },
            },
        }


# =============================================================================
# Worker CRD
# =============================================================================

@dataclass
class WorkerSpec:
    """مواصفات العامل"""
    cluster_ref: str = ""
    node_selector: dict[str, str] = field(default_factory=dict)
    tolerations: list[dict[str, Any]] = field(default_factory=list)
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clusterRef": self.cluster_ref,
            "nodeSelector": self.node_selector,
            "tolerations": self.tolerations,
            "resources": self.resources.to_dict(),
            "capabilities": self.capabilities,
        }


@dataclass
class WorkerStatus:
    """حالة العامل"""
    phase: WorkerPhase = WorkerPhase.PENDING
    pod_ip: str = ""
    node_name: str = ""
    active_tasks: int = 0
    completed_tasks: int = 0
    last_heartbeat: Optional[datetime] = None
    conditions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "podIP": self.pod_ip,
            "nodeName": self.node_name,
            "activeTasks": self.active_tasks,
            "completedTasks": self.completed_tasks,
            "lastHeartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "conditions": self.conditions,
        }


@dataclass
class WorkerCRD:
    """Worker Custom Resource Definition"""
    api_version: str = f"{API_GROUP}/{API_VERSION}"
    kind: str = "ClusterWorker"
    metadata: ObjectMeta = field(default_factory=lambda: ObjectMeta(name="default"))
    spec: WorkerSpec = field(default_factory=WorkerSpec)
    status: WorkerStatus = field(default_factory=WorkerStatus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata.to_dict(),
            "spec": self.spec.to_dict(),
            "status": self.status.to_dict(),
        }


# =============================================================================
# Job CRD
# =============================================================================

@dataclass
class JobSpec:
    """مواصفات المهمة"""
    cluster_ref: str = ""
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    image: Optional[str] = None
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)
    parallelism: int = 1
    completions: int = 1
    backoff_limit: int = 3
    active_deadline_seconds: Optional[int] = None
    ttl_seconds_after_finished: int = 3600
    priority: int = 0
    env_vars: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clusterRef": self.cluster_ref,
            "command": self.command,
            "args": self.args,
            "image": self.image,
            "resources": self.resources.to_dict(),
            "parallelism": self.parallelism,
            "completions": self.completions,
            "backoffLimit": self.backoff_limit,
            "activeDeadlineSeconds": self.active_deadline_seconds,
            "ttlSecondsAfterFinished": self.ttl_seconds_after_finished,
            "priority": self.priority,
            "envVars": self.env_vars,
        }


@dataclass
class JobStatus:
    """حالة المهمة"""
    phase: JobPhase = JobPhase.PENDING
    active: int = 0
    succeeded: int = 0
    failed: int = 0
    start_time: Optional[datetime] = None
    completion_time: Optional[datetime] = None
    conditions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "active": self.active,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "startTime": self.start_time.isoformat() if self.start_time else None,
            "completionTime": self.completion_time.isoformat() if self.completion_time else None,
            "conditions": self.conditions,
        }


@dataclass
class JobCRD:
    """Job Custom Resource Definition"""
    api_version: str = f"{API_GROUP}/{API_VERSION}"
    kind: str = "ClusterJob"
    metadata: ObjectMeta = field(default_factory=lambda: ObjectMeta(name="default"))
    spec: JobSpec = field(default_factory=JobSpec)
    status: JobStatus = field(default_factory=JobStatus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata.to_dict(),
            "spec": self.spec.to_dict(),
            "status": self.status.to_dict(),
        }


# =============================================================================
# CRD Manager
# =============================================================================

class CRDManager:
    """
    مدير CRDs
    CRD Manager

    يدير تثبيت وتحديث وحذف CRDs.
    Manages CRD installation, updates, and deletion.
    """

    def __init__(self, kubeconfig: Optional[str] = None):
        """
        تهيئة المدير

        Args:
            kubeconfig: مسار ملف kubeconfig
        """
        self.kubeconfig = kubeconfig
        self._client = None
        self._api = None

    async def initialize(self) -> bool:
        """تهيئة اتصال Kubernetes"""
        try:
            from kubernetes import client, config
            from kubernetes.client import ApiextensionsV1Api

            if self.kubeconfig:
                config.load_kube_config(config_file=self.kubeconfig)
            else:
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config()

            self._client = client
            self._api = ApiextensionsV1Api()

            logger.info("CRDManager initialized")
            return True

        except ImportError:
            logger.error("kubernetes package not installed")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize CRDManager: {e}")
            return False

    async def install_crds(self) -> bool:
        """تثبيت جميع CRDs"""
        if not self._api:
            return False

        crds = [
            ClusterCRD.get_crd_definition(),
            self._get_worker_crd_definition(),
            self._get_job_crd_definition(),
        ]

        for crd in crds:
            try:
                self._api.create_custom_resource_definition(body=crd)
                logger.info(f"Installed CRD: {crd['metadata']['name']}")
            except self._client.exceptions.ApiException as e:
                if e.status == 409:  # Already exists
                    logger.info(f"CRD already exists: {crd['metadata']['name']}")
                else:
                    logger.error(f"Failed to install CRD: {e}")
                    return False

        return True

    async def uninstall_crds(self) -> bool:
        """إزالة جميع CRDs"""
        if not self._api:
            return False

        crd_names = [
            f"distributedclusters.{API_GROUP}",
            f"clusterworkers.{API_GROUP}",
            f"clusterjobs.{API_GROUP}",
        ]

        for name in crd_names:
            try:
                self._api.delete_custom_resource_definition(name=name)
                logger.info(f"Deleted CRD: {name}")
            except Exception as e:
                logger.error(f"Failed to delete CRD {name}: {e}")

        return True

    def _get_worker_crd_definition(self) -> dict[str, Any]:
        """تعريف CRD للعامل"""
        return {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {"name": f"clusterworkers.{API_GROUP}"},
            "spec": {
                "group": API_GROUP,
                "versions": [{"name": API_VERSION, "served": True, "storage": True,
                    "schema": {"openAPIV3Schema": {"type": "object"}}}],
                "scope": "Namespaced",
                "names": {
                    "plural": "clusterworkers",
                    "singular": "clusterworker",
                    "kind": "ClusterWorker",
                    "shortNames": ["cw", "worker"],
                },
            },
        }

    def _get_job_crd_definition(self) -> dict[str, Any]:
        """تعريف CRD للمهمة"""
        return {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {"name": f"clusterjobs.{API_GROUP}"},
            "spec": {
                "group": API_GROUP,
                "versions": [{"name": API_VERSION, "served": True, "storage": True,
                    "schema": {"openAPIV3Schema": {"type": "object"}}}],
                "scope": "Namespaced",
                "names": {
                    "plural": "clusterjobs",
                    "singular": "clusterjob",
                    "kind": "ClusterJob",
                    "shortNames": ["cj", "job"],
                },
            },
        }
