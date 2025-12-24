"""
GCP Provider - مزود Google Cloud Platform
==========================================

GCP Cloud Provider for Auto-Scaling
------------------------------------

This module provides integration with Google Compute Engine (GCE)
for provisioning and terminating worker instances.

يوفر هذا الملف التكامل مع Google Compute Engine لإنشاء وإنهاء العمال:
- إنشاء GCE instances
- إدارة Instance Groups
- دعم Preemptible VMs
- تكامل مع VPC/Subnets

Requirements:
- google-cloud-compute library
- GCP credentials configured

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Optional

from distributed_cluster.autoscaling.providers.base import (
    CloudProvider,
    InstanceInfo,
    InstanceState,
    ProviderConfig,
    ProvisioningError,
    TerminationError,
)

logger = logging.getLogger(__name__)

# GCP state mapping
GCP_STATE_MAP = {
    "PROVISIONING": InstanceState.PENDING,
    "STAGING": InstanceState.PENDING,
    "RUNNING": InstanceState.RUNNING,
    "STOPPING": InstanceState.STOPPING,
    "STOPPED": InstanceState.STOPPED,
    "SUSPENDING": InstanceState.STOPPING,
    "SUSPENDED": InstanceState.STOPPED,
    "TERMINATED": InstanceState.TERMINATED,
}


class GCPProvider(CloudProvider):
    """
    مزود Google Cloud Platform للتوسع التلقائي
    GCP Cloud Provider for auto-scaling

    يستخدم google-cloud-compute للتفاعل مع GCE.
    Uses google-cloud-compute to interact with GCE.
    """

    def __init__(
        self,
        project: str,
        zone: str = "us-central1-a",
        machine_type: str = "n1-standard-4",
        image_family: str = "ubuntu-2204-lts",
        image_project: str = "ubuntu-os-cloud",
        network: str = "default",
        subnetwork: Optional[str] = None,
        service_account: Optional[str] = None,
        startup_script: Optional[str] = None,
        preemptible: bool = False,
        config: Optional[ProviderConfig] = None,
        credentials_path: Optional[str] = None,
    ):
        """
        تهيئة مزود GCP

        Args:
            project: معرف مشروع GCP
            zone: منطقة GCP (مثل us-central1-a)
            machine_type: نوع الآلة (مثل n1-standard-4)
            image_family: عائلة الصورة
            image_project: مشروع الصورة
            network: اسم الشبكة
            subnetwork: اسم الشبكة الفرعية
            service_account: حساب الخدمة
            startup_script: سكربت بدء التشغيل
            preemptible: استخدام Preemptible VMs
            config: إعدادات إضافية
            credentials_path: مسار ملف credentials
        """
        super().__init__(config)

        self.project = project
        self.zone = zone
        self.machine_type = machine_type
        self.image_family = image_family
        self.image_project = image_project
        self.network = network
        self.subnetwork = subnetwork
        self.service_account = service_account
        self.startup_script = startup_script
        self.preemptible = preemptible
        self.credentials_path = credentials_path

        # GCP clients
        self._instances_client = None
        self._zone_operations_client = None

        # Thread pool
        self._executor = ThreadPoolExecutor(max_workers=4)

        # Instance counter
        self._instance_counter = 0

        # إعداد التكلفة التقريبية
        self.config.cost_per_hour = self._estimate_hourly_cost()

    def _estimate_hourly_cost(self) -> float:
        """تقدير التكلفة بالساعة (تقريبي)"""
        # أسعار تقريبية في us-central1
        machine_prices = {
            "n1-standard-1": 0.0475,
            "n1-standard-2": 0.095,
            "n1-standard-4": 0.19,
            "n1-standard-8": 0.38,
            "n1-standard-16": 0.76,
            "n2-standard-2": 0.0971,
            "n2-standard-4": 0.1942,
            "n2-standard-8": 0.3884,
            "e2-medium": 0.0336,
            "e2-standard-2": 0.0672,
            "e2-standard-4": 0.1344,
            "a2-highgpu-1g": 3.67,  # GPU
            "a2-highgpu-2g": 7.35,  # GPU
        }
        price = machine_prices.get(self.machine_type, 0.10)

        # Preemptible أرخص بـ 60-80%
        if self.preemptible:
            price *= 0.3

        return price

    async def connect(self) -> None:
        """الاتصال بـ GCP"""
        try:
            from google.cloud import compute_v1
            from google.oauth2 import service_account

            # إعداد credentials إذا تم توفير مسار
            credentials = None
            if self.credentials_path:
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )

            # إنشاء clients
            self._instances_client = compute_v1.InstancesClient(credentials=credentials)
            self._zone_operations_client = compute_v1.ZoneOperationsClient(
                credentials=credentials
            )

            # اختبار الاتصال
            await self._run_in_executor(
                self._instances_client.list,
                project=self.project,
                zone=self.zone,
            )

            self._connected = True
            logger.info(f"Connected to GCP Compute Engine in zone {self.zone}")

        except ImportError:
            raise ProvisioningError(
                "google-cloud-compute is required for GCP provider. "
                "Install it with: pip install google-cloud-compute"
            )
        except Exception as e:
            raise ProvisioningError(f"Failed to connect to GCP: {e}")

    async def disconnect(self) -> None:
        """قطع الاتصال"""
        self._instances_client = None
        self._zone_operations_client = None
        self._connected = False
        logger.info("Disconnected from GCP Compute Engine")

    async def _run_in_executor(self, func, *args, **kwargs):
        """تشغيل دالة في thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, lambda: func(*args, **kwargs)
        )

    async def _wait_for_operation(self, operation) -> None:
        """انتظار اكتمال عملية GCP"""
        while True:
            result = await self._run_in_executor(
                self._zone_operations_client.get,
                project=self.project,
                zone=self.zone,
                operation=operation.name,
            )

            if result.status.name == "DONE":
                if result.error:
                    raise ProvisioningError(f"Operation failed: {result.error}")
                return

            await asyncio.sleep(2)

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
        إنشاء GCE instances
        Provision GCE instances
        """
        if not self._connected:
            raise ProvisioningError("Provider not connected")

        from google.cloud import compute_v1

        machine_type = instance_type or self.machine_type
        zone = zone or self.zone
        merged_tags = self._merge_tags(tags)
        merged_labels = self._merge_labels(labels)

        # تنظيف التسميات (GCP يتطلب أحرف صغيرة)
        gcp_labels = {
            k.lower().replace("-", "_"): v.lower().replace("-", "_")
            for k, v in merged_labels.items()
        }
        gcp_labels["managed_by"] = "distributed_cluster"
        gcp_labels["autoscaling"] = "true"

        instance_ids: list[str] = []

        for i in range(count):
            self._instance_counter += 1
            instance_name = f"dc-worker-{self._instance_counter:04d}"

            try:
                # إعداد الـ instance
                instance = compute_v1.Instance()
                instance.name = instance_name
                instance.machine_type = f"zones/{zone}/machineTypes/{machine_type}"
                instance.labels = gcp_labels

                # Disk configuration
                disk = compute_v1.AttachedDisk()
                disk.boot = True
                disk.auto_delete = True
                disk.initialize_params = compute_v1.AttachedDiskInitializeParams()
                disk.initialize_params.source_image = (
                    f"projects/{self.image_project}/global/images/family/{self.image_family}"
                )
                disk.initialize_params.disk_size_gb = 50
                instance.disks = [disk]

                # Network configuration
                network_interface = compute_v1.NetworkInterface()
                network_interface.network = f"global/networks/{self.network}"

                if self.subnetwork:
                    network_interface.subnetwork = (
                        f"regions/{zone.rsplit('-', 1)[0]}/subnetworks/{self.subnetwork}"
                    )

                # External IP
                access_config = compute_v1.AccessConfig()
                access_config.name = "External NAT"
                access_config.type_ = "ONE_TO_ONE_NAT"
                network_interface.access_configs = [access_config]

                instance.network_interfaces = [network_interface]

                # Tags
                instance.tags = compute_v1.Tags()
                instance.tags.items = list(merged_tags.keys())

                # Service account
                if self.service_account:
                    sa = compute_v1.ServiceAccount()
                    sa.email = self.service_account
                    sa.scopes = [
                        "https://www.googleapis.com/auth/cloud-platform"
                    ]
                    instance.service_accounts = [sa]

                # Preemptible
                if self.preemptible:
                    scheduling = compute_v1.Scheduling()
                    scheduling.preemptible = True
                    instance.scheduling = scheduling

                # Startup script
                if self.startup_script:
                    metadata = compute_v1.Metadata()
                    metadata.items = [
                        compute_v1.Items(
                            key="startup-script",
                            value=self.startup_script,
                        )
                    ]
                    instance.metadata = metadata

                # إنشاء الـ instance
                operation = await self._run_in_executor(
                    self._instances_client.insert,
                    project=self.project,
                    zone=zone,
                    instance_resource=instance,
                )

                # انتظار اكتمال العملية
                await self._wait_for_operation(operation)

                instance_ids.append(instance_name)

                # تحديث الذاكرة المحلية
                self._instances[instance_name] = InstanceInfo(
                    instance_id=instance_name,
                    provider="gcp",
                    state=InstanceState.PENDING,
                    instance_type=machine_type,
                    zone=zone,
                    created_at=datetime.utcnow(),
                    tags=merged_tags,
                    labels=merged_labels,
                )

                logger.info(f"[GCP] Provisioned instance: {instance_name}")

            except Exception as e:
                logger.error(f"[GCP] Failed to provision instance: {e}")
                raise ProvisioningError(f"Failed to provision GCP instance: {e}")

        return instance_ids

    async def terminate_workers(self, instance_ids: list[str]) -> int:
        """
        إنهاء GCE instances
        Terminate GCE instances
        """
        if not self._connected:
            raise TerminationError("Provider not connected")

        if not instance_ids:
            return 0

        terminated = 0

        for instance_id in instance_ids:
            try:
                operation = await self._run_in_executor(
                    self._instances_client.delete,
                    project=self.project,
                    zone=self.zone,
                    instance=instance_id,
                )

                await self._wait_for_operation(operation)

                # تحديث الذاكرة المحلية
                if instance_id in self._instances:
                    self._instances[instance_id].state = InstanceState.TERMINATED

                terminated += 1
                logger.info(f"[GCP] Terminated instance: {instance_id}")

            except Exception as e:
                logger.error(f"[GCP] Failed to terminate instance {instance_id}: {e}")

        return terminated

    async def get_instances(
        self,
        state: Optional[InstanceState] = None,
        tags: Optional[dict[str, str]] = None,
    ) -> list[InstanceInfo]:
        """الحصول على قائمة الـ instances"""
        if not self._connected:
            return []

        try:
            # فلتر بالتسميات
            filter_str = 'labels.managed_by="distributed_cluster"'

            instances_list = await self._run_in_executor(
                self._instances_client.list,
                project=self.project,
                zone=self.zone,
                filter=filter_str,
            )

            instances: list[InstanceInfo] = []

            for inst in instances_list:
                gcp_state = GCP_STATE_MAP.get(inst.status, InstanceState.UNKNOWN)

                if state and gcp_state != state:
                    continue

                # استخراج IPs
                private_ip = None
                public_ip = None
                if inst.network_interfaces:
                    private_ip = inst.network_interfaces[0].network_i_p
                    if inst.network_interfaces[0].access_configs:
                        public_ip = inst.network_interfaces[0].access_configs[0].nat_i_p

                instance_info = InstanceInfo(
                    instance_id=inst.name,
                    provider="gcp",
                    state=gcp_state,
                    instance_type=inst.machine_type.split("/")[-1],
                    zone=inst.zone.split("/")[-1],
                    private_ip=private_ip,
                    public_ip=public_ip,
                    created_at=datetime.fromisoformat(
                        inst.creation_timestamp.replace("Z", "+00:00")
                    ) if inst.creation_timestamp else None,
                    labels=dict(inst.labels) if inst.labels else {},
                )

                instances.append(instance_info)
                self._instances[inst.name] = instance_info

            return instances

        except Exception as e:
            logger.error(f"[GCP] Failed to get instances: {e}")
            return []

    async def get_instance(self, instance_id: str) -> Optional[InstanceInfo]:
        """الحصول على instance واحد"""
        if not self._connected:
            return None

        try:
            inst = await self._run_in_executor(
                self._instances_client.get,
                project=self.project,
                zone=self.zone,
                instance=instance_id,
            )

            private_ip = None
            public_ip = None
            if inst.network_interfaces:
                private_ip = inst.network_interfaces[0].network_i_p
                if inst.network_interfaces[0].access_configs:
                    public_ip = inst.network_interfaces[0].access_configs[0].nat_i_p

            return InstanceInfo(
                instance_id=inst.name,
                provider="gcp",
                state=GCP_STATE_MAP.get(inst.status, InstanceState.UNKNOWN),
                instance_type=inst.machine_type.split("/")[-1],
                zone=inst.zone.split("/")[-1],
                private_ip=private_ip,
                public_ip=public_ip,
                created_at=datetime.fromisoformat(
                    inst.creation_timestamp.replace("Z", "+00:00")
                ) if inst.creation_timestamp else None,
                labels=dict(inst.labels) if inst.labels else {},
            )

        except Exception as e:
            logger.error(f"[GCP] Failed to get instance {instance_id}: {e}")
            return None

    async def get_terminable_workers(self, count: int) -> list[str]:
        """الحصول على عمال قابلين للإنهاء"""
        instances = await self.get_instances(state=InstanceState.RUNNING)

        # فرز حسب وقت الإنشاء (الأحدث أولاً)
        instances.sort(
            key=lambda i: i.created_at or datetime.min,
            reverse=True,
        )

        terminable: list[str] = []
        for inst in instances:
            if inst.is_terminable:
                terminable.append(inst.instance_id)
                if len(terminable) >= count:
                    break

        return terminable

    async def get_worker_count(self) -> int:
        """الحصول على عدد العمال الحاليين"""
        instances = await self.get_instances(state=InstanceState.RUNNING)
        return len(instances)

    def get_status(self) -> dict[str, Any]:
        """الحصول على حالة المزود"""
        status = super().get_status()
        status.update({
            "provider_type": "gcp",
            "project": self.project,
            "zone": self.zone,
            "machine_type": self.machine_type,
            "preemptible": self.preemptible,
            "estimated_cost_per_hour": self.config.cost_per_hour,
        })
        return status
