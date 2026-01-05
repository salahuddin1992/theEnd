"""
Local Provider - مزود محلي للاختبار
====================================

Local/Mock Cloud Provider
-------------------------

This module provides a local provider for testing and development.
It simulates cloud provider behavior without actually creating instances.

يوفر هذا الملف مزود محلي للاختبار والتطوير.
يحاكي سلوك مزود السحابة بدون إنشاء instances فعلية.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from distributed_cluster.autoscaling.providers.base import (
    CloudProvider,
    InstanceInfo,
    InstanceState,
    ProviderConfig,
    ProvisioningError,
    TerminationError,
)

if TYPE_CHECKING:
    from distributed_cluster.master.state import ClusterState

logger = logging.getLogger(__name__)


class LocalProvider(CloudProvider):
    """
    مزود محلي للاختبار والتطوير
    Local provider for testing and development

    يحاكي سلوك مزود السحابة ويتكامل مع ClusterState
    لإنشاء عمال محليين وهميين.

    Simulates cloud provider behavior and integrates with
    ClusterState to create mock local workers.
    """

    def __init__(
        self,
        cluster_state: Optional[ClusterState] = None,
        config: Optional[ProviderConfig] = None,
        simulate_delay: bool = False,
        delay_seconds: float = 2.0,
    ):
        """
        تهيئة المزود المحلي

        Args:
            cluster_state: حالة الكلاستر للتكامل (اختياري)
            config: الإعدادات (اختياري)
            simulate_delay: محاكاة تأخير الإنشاء
            delay_seconds: مدة التأخير بالثواني
        """
        super().__init__(config)
        self.cluster_state = cluster_state
        self.simulate_delay = simulate_delay
        self.delay_seconds = delay_seconds

        # تخزين محلي للـ instances
        self._local_instances: dict[str, InstanceInfo] = {}
        self._instance_counter = 0

        # إحصائيات
        self._stats = {
            "total_provisioned": 0,
            "total_terminated": 0,
            "current_count": 0,
        }

    async def connect(self) -> None:
        """الاتصال (لا يوجد اتصال فعلي للمزود المحلي)"""
        self._connected = True
        logger.info("LocalProvider connected (simulation mode)")

    async def disconnect(self) -> None:
        """قطع الاتصال"""
        self._connected = False
        logger.info("LocalProvider disconnected")

    async def provision_workers(
        self,
        count: int,
        instance_type: Optional[str] = None,
        zone: Optional[str] = None,
        tags: Optional[list[str]] = None,
        labels: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> list[str]:
        """
        إنشاء عمال محليين وهميين
        Provision mock local workers
        """
        if not self._connected:
            raise ProvisioningError("Provider not connected")

        instance_ids: list[str] = []

        for _ in range(count):
            self._instance_counter += 1

            instance_id = f"local-{self._instance_counter:04d}-{uuid.uuid4().hex[:8]}"

            instance = InstanceInfo(
                instance_id=instance_id,
                provider="local",
                state=InstanceState.PENDING,
                instance_type=instance_type or "local.default",
                zone=zone or "local-zone-1",
                private_ip=f"10.0.0.{100 + self._instance_counter}",
                created_at=datetime.now(timezone.utc),
                tags=self._merge_tags(tags),
                labels=self._merge_labels(labels),
                metadata={"simulated": True},
            )

            self._local_instances[instance_id] = instance
            instance_ids.append(instance_id)

            logger.info(f"[LOCAL] Provisioned instance: {instance_id}")

        # محاكاة تأخير الإنشاء
        if self.simulate_delay:
            await asyncio.sleep(self.delay_seconds)

        # تحديث الحالة إلى RUNNING
        for instance_id in instance_ids:
            if instance_id in self._local_instances:
                self._local_instances[instance_id].state = InstanceState.RUNNING

        # تحديث الإحصائيات
        self._stats["total_provisioned"] += count
        self._stats["current_count"] += count

        # التكامل مع ClusterState إذا متاح
        if self.cluster_state:
            for instance_id in instance_ids:
                self._register_worker(instance_id)

        return instance_ids

    async def terminate_workers(self, instance_ids: list[str]) -> int:
        """
        إنهاء عمال محليين
        Terminate local workers
        """
        if not self._connected:
            raise TerminationError("Provider not connected")

        terminated = 0

        for instance_id in instance_ids:
            if instance_id in self._local_instances:
                instance = self._local_instances[instance_id]
                instance.state = InstanceState.TERMINATING

                # محاكاة تأخير الإنهاء
                if self.simulate_delay:
                    await asyncio.sleep(self.delay_seconds / 2)

                instance.state = InstanceState.TERMINATED

                # إزالة من ClusterState
                if self.cluster_state and instance.worker_id:
                    self.cluster_state.remove_worker(instance.worker_id)

                # إزالة من التخزين المحلي
                del self._local_instances[instance_id]
                terminated += 1

                logger.info(f"[LOCAL] Terminated instance: {instance_id}")

        # تحديث الإحصائيات
        self._stats["total_terminated"] += terminated
        self._stats["current_count"] -= terminated

        return terminated

    async def get_instances(
        self,
        state: Optional[InstanceState] = None,
        tags: Optional[dict[str, str]] = None,
    ) -> list[InstanceInfo]:
        """الحصول على قائمة الـ instances"""
        instances = list(self._local_instances.values())

        if state:
            instances = [i for i in instances if i.state == state]

        if tags:
            instances = [
                i for i in instances
                if all(i.tags.get(k) == v for k, v in tags.items())
            ]

        return instances

    async def get_instance(self, instance_id: str) -> Optional[InstanceInfo]:
        """الحصول على instance واحد"""
        return self._local_instances.get(instance_id)

    async def get_terminable_workers(self, count: int) -> list[str]:
        """
        الحصول على عمال قابلين للإنهاء
        Get workers that can be terminated
        """
        terminable: list[str] = []

        for instance_id, instance in self._local_instances.items():
            if instance.state != InstanceState.RUNNING:
                continue

            if not instance.is_terminable:
                continue

            # التحقق من عدم وجود مهام نشطة
            if self.cluster_state and instance.worker_id:
                worker = self.cluster_state.get_worker(instance.worker_id)
                if worker and len(worker.active_jobs) > 0:
                    continue

            terminable.append(instance_id)

            if len(terminable) >= count:
                break

        return terminable

    async def get_worker_count(self) -> int:
        """الحصول على عدد العمال الحاليين"""
        return len([
            i for i in self._local_instances.values()
            if i.state == InstanceState.RUNNING
        ])

    def _register_worker(self, instance_id: str) -> None:
        """
        تسجيل العامل في ClusterState
        Register worker in ClusterState
        """
        if not self.cluster_state:
            return

        instance = self._local_instances.get(instance_id)
        if not instance:
            return

        from distributed_cluster.models.resources import ResourceSpec
        from distributed_cluster.models.worker import WorkerRegistration

        registration = WorkerRegistration(
            worker_id=f"worker-{instance_id}",
            hostname=f"local-{instance_id}",
            port=8080,
            total_resources=ResourceSpec(
                cpu_cores=4.0,
                memory_mb=8192,
                gpu_count=0,
            ),
            tags=list(instance.tags.keys()),
            labels=instance.labels,
        )

        worker = self.cluster_state.register_worker(registration)
        instance.worker_id = worker.worker_id

        logger.debug(f"Registered worker {worker.worker_id} for instance {instance_id}")

    def get_status(self) -> dict[str, Any]:
        """الحصول على حالة المزود"""
        status = super().get_status()
        status.update({
            "provider_type": "local",
            "simulate_delay": self.simulate_delay,
            "stats": self._stats,
            "instances": {
                "total": len(self._local_instances),
                "running": len([
                    i for i in self._local_instances.values()
                    if i.state == InstanceState.RUNNING
                ]),
            },
        })
        return status


class DryRunProvider(LocalProvider):
    """
    مزود للتشغيل الجاف (بدون إجراءات فعلية)
    Dry-run provider (no actual actions)

    يسجل فقط ما كان سيحدث بدون تنفيذ.
    Only logs what would happen without executing.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._action_log: list[dict[str, Any]] = []

    async def provision_workers(
        self,
        count: int,
        instance_type: Optional[str] = None,
        zone: Optional[str] = None,
        tags: Optional[list[str]] = None,
        labels: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> list[str]:
        """تسجيل طلب الإنشاء فقط"""
        action = {
            "action": "provision",
            "count": count,
            "instance_type": instance_type,
            "zone": zone,
            "tags": tags,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._action_log.append(action)
        logger.info(f"[DRY-RUN] Would provision {count} workers")

        # إنشاء IDs وهمية
        return [f"dry-run-{i}" for i in range(count)]

    async def terminate_workers(self, instance_ids: list[str]) -> int:
        """تسجيل طلب الإنهاء فقط"""
        action = {
            "action": "terminate",
            "instance_ids": instance_ids,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._action_log.append(action)
        logger.info(f"[DRY-RUN] Would terminate {len(instance_ids)} workers")
        return len(instance_ids)

    def get_action_log(self) -> list[dict[str, Any]]:
        """الحصول على سجل الإجراءات"""
        return self._action_log

    def clear_action_log(self) -> None:
        """مسح سجل الإجراءات"""
        self._action_log.clear()
