"""
Azure Provider - مزود Microsoft Azure
======================================

Azure Cloud Provider for Auto-Scaling
-------------------------------------

This module provides integration with Azure Virtual Machines
for provisioning and terminating worker instances.

يوفر هذا الملف التكامل مع Azure VMs لإنشاء وإنهاء العمال:
- إنشاء Azure VMs
- إدارة Virtual Machine Scale Sets
- دعم Spot VMs
- تكامل مع VNet/Subnets

Requirements:
- azure-mgmt-compute library
- azure-identity library
- Azure credentials configured

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

# Azure state mapping
AZURE_STATE_MAP = {
    "Creating": InstanceState.PENDING,
    "Starting": InstanceState.PENDING,
    "Running": InstanceState.RUNNING,
    "Stopping": InstanceState.STOPPING,
    "Stopped": InstanceState.STOPPED,
    "Deallocating": InstanceState.STOPPING,
    "Deallocated": InstanceState.STOPPED,
    "Deleting": InstanceState.TERMINATING,
    "Deleted": InstanceState.TERMINATED,
}


class AzureProvider(CloudProvider):
    """
    مزود Microsoft Azure للتوسع التلقائي
    Azure Cloud Provider for auto-scaling

    يستخدم azure-mgmt-compute للتفاعل مع Azure VMs.
    Uses azure-mgmt-compute to interact with Azure VMs.
    """

    def __init__(
        self,
        subscription_id: str,
        resource_group: str,
        location: str = "eastus",
        vm_size: str = "Standard_D4s_v3",
        image_reference: Optional[dict[str, str]] = None,
        vnet_name: Optional[str] = None,
        subnet_name: Optional[str] = None,
        network_security_group: Optional[str] = None,
        admin_username: str = "azureuser",
        admin_password: Optional[str] = None,
        ssh_key: Optional[str] = None,
        custom_data: Optional[str] = None,
        spot_vm: bool = False,
        spot_max_price: float = -1,  # -1 means pay-as-you-go price
        config: Optional[ProviderConfig] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        """
        تهيئة مزود Azure

        Args:
            subscription_id: معرف اشتراك Azure
            resource_group: اسم مجموعة الموارد
            location: موقع Azure (مثل eastus)
            vm_size: حجم VM (مثل Standard_D4s_v3)
            image_reference: مرجع الصورة
            vnet_name: اسم الشبكة الافتراضية
            subnet_name: اسم الشبكة الفرعية
            network_security_group: مجموعة أمان الشبكة
            admin_username: اسم المستخدم
            admin_password: كلمة المرور (أو SSH key)
            ssh_key: مفتاح SSH العام
            custom_data: بيانات مخصصة (cloud-init)
            spot_vm: استخدام Spot VMs
            spot_max_price: أقصى سعر للـ Spot
            config: إعدادات إضافية
            tenant_id: معرف المستأجر
            client_id: معرف العميل
            client_secret: سر العميل
        """
        super().__init__(config)

        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.vm_size = vm_size
        self.image_reference = image_reference or {
            "publisher": "Canonical",
            "offer": "0001-com-ubuntu-server-jammy",
            "sku": "22_04-lts-gen2",
            "version": "latest",
        }
        self.vnet_name = vnet_name
        self.subnet_name = subnet_name
        self.network_security_group = network_security_group
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.ssh_key = ssh_key
        self.custom_data = custom_data
        self.spot_vm = spot_vm
        self.spot_max_price = spot_max_price

        # Azure credentials
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret

        # Azure clients
        self._compute_client = None
        self._network_client = None

        # Thread pool
        self._executor = ThreadPoolExecutor(max_workers=4)

        # Instance counter
        self._instance_counter = 0

        # إعداد التكلفة التقريبية
        self.config.cost_per_hour = self._estimate_hourly_cost()

    def _estimate_hourly_cost(self) -> float:
        """تقدير التكلفة بالساعة (تقريبي)"""
        # أسعار تقريبية في East US
        vm_prices = {
            "Standard_B1s": 0.0104,
            "Standard_B2s": 0.0416,
            "Standard_D2s_v3": 0.096,
            "Standard_D4s_v3": 0.192,
            "Standard_D8s_v3": 0.384,
            "Standard_D16s_v3": 0.768,
            "Standard_E2s_v3": 0.126,
            "Standard_E4s_v3": 0.252,
            "Standard_F4s_v2": 0.169,
            "Standard_F8s_v2": 0.338,
            "Standard_NC6": 0.90,  # GPU
            "Standard_NC12": 1.80,  # GPU
            "Standard_NC24": 3.60,  # GPU
            "Standard_NV6": 1.14,  # GPU
        }
        price = vm_prices.get(self.vm_size, 0.10)

        # Spot VMs أرخص بـ 60-90%
        if self.spot_vm:
            price *= 0.2

        return price

    async def connect(self) -> None:
        """الاتصال بـ Azure"""
        try:
            from azure.identity import ClientSecretCredential, DefaultAzureCredential
            from azure.mgmt.compute import ComputeManagementClient
            from azure.mgmt.network import NetworkManagementClient

            # إعداد credentials
            if self._tenant_id and self._client_id and self._client_secret:
                credential = ClientSecretCredential(
                    tenant_id=self._tenant_id,
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                )
            else:
                credential = DefaultAzureCredential()

            # إنشاء clients
            self._compute_client = ComputeManagementClient(
                credential, self.subscription_id
            )
            self._network_client = NetworkManagementClient(
                credential, self.subscription_id
            )

            # اختبار الاتصال
            await self._run_in_executor(
                list,
                self._compute_client.virtual_machines.list(self.resource_group),
            )

            self._connected = True
            logger.info(f"Connected to Azure in location {self.location}")

        except ImportError:
            raise ProvisioningError(
                "azure-mgmt-compute and azure-identity are required for Azure provider. "
                "Install them with: pip install azure-mgmt-compute azure-identity azure-mgmt-network"
            )
        except Exception as e:
            raise ProvisioningError(f"Failed to connect to Azure: {e}")

    async def disconnect(self) -> None:
        """قطع الاتصال"""
        self._compute_client = None
        self._network_client = None
        self._connected = False
        logger.info("Disconnected from Azure")

    async def _run_in_executor(self, func, *args, **kwargs):
        """تشغيل دالة في thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, lambda: func(*args, **kwargs)
        )

    async def _create_nic(self, nic_name: str) -> str:
        """إنشاء Network Interface"""
        from azure.mgmt.network.models import NetworkInterface, NetworkInterfaceIPConfiguration

        # الحصول على الشبكة الفرعية
        if self.vnet_name and self.subnet_name:
            subnet = await self._run_in_executor(
                self._network_client.subnets.get,
                self.resource_group,
                self.vnet_name,
                self.subnet_name,
            )
            subnet_id = subnet.id
        else:
            # استخدام default subnet
            vnets = await self._run_in_executor(
                list,
                self._network_client.virtual_networks.list(self.resource_group),
            )
            if vnets:
                subnet_id = vnets[0].subnets[0].id
            else:
                raise ProvisioningError("No virtual network found in resource group")

        # إنشاء IP configuration
        ip_config = NetworkInterfaceIPConfiguration(
            name=f"{nic_name}-ipconfig",
            subnet={"id": subnet_id},
            private_ip_allocation_method="Dynamic",
        )

        # إنشاء NIC
        nic_params = NetworkInterface(
            location=self.location,
            ip_configurations=[ip_config],
        )

        if self.network_security_group:
            nsg = await self._run_in_executor(
                self._network_client.network_security_groups.get,
                self.resource_group,
                self.network_security_group,
            )
            nic_params.network_security_group = {"id": nsg.id}

        poller = await self._run_in_executor(
            self._network_client.network_interfaces.begin_create_or_update,
            self.resource_group,
            nic_name,
            nic_params,
        )

        nic = await self._run_in_executor(poller.result)
        return nic.id

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
        إنشاء Azure VMs
        Provision Azure VMs
        """
        if not self._connected:
            raise ProvisioningError("Provider not connected")

        from azure.mgmt.compute.models import (
            BillingProfile,
            DiskCreateOptionTypes,
            HardwareProfile,
            ImageReference,
            LinuxConfiguration,
            ManagedDiskParameters,
            NetworkInterfaceReference,
            NetworkProfile,
            OSDisk,
            OSProfile,
            SshConfiguration,
            SshPublicKey,
            StorageAccountTypes,
            StorageProfile,
            VirtualMachine,
            VirtualMachineEvictionPolicyTypes,
            VirtualMachinePriorityTypes,
        )

        vm_size = instance_type or self.vm_size
        merged_tags = self._merge_tags(tags)
        merged_labels = self._merge_labels(labels)

        # دمج tags و labels
        azure_tags = {**merged_tags, **merged_labels}
        azure_tags["managed-by"] = "distributed-cluster"
        azure_tags["autoscaling"] = "true"

        instance_ids: list[str] = []

        for i in range(count):
            self._instance_counter += 1
            vm_name = f"dc-worker-{self._instance_counter:04d}"
            nic_name = f"{vm_name}-nic"

            try:
                # إنشاء NIC
                nic_id = await self._create_nic(nic_name)

                # إعداد الـ VM
                hardware_profile = HardwareProfile(vm_size=vm_size)

                image_reference = ImageReference(
                    publisher=self.image_reference["publisher"],
                    offer=self.image_reference["offer"],
                    sku=self.image_reference["sku"],
                    version=self.image_reference["version"],
                )

                os_disk = OSDisk(
                    name=f"{vm_name}-osdisk",
                    caching="ReadWrite",
                    create_option=DiskCreateOptionTypes.FROM_IMAGE,
                    managed_disk=ManagedDiskParameters(
                        storage_account_type=StorageAccountTypes.PREMIUM_LRS
                    ),
                )

                storage_profile = StorageProfile(
                    image_reference=image_reference,
                    os_disk=os_disk,
                )

                # إعداد OS Profile
                os_profile_params: dict[str, Any] = {
                    "computer_name": vm_name,
                    "admin_username": self.admin_username,
                }

                if self.ssh_key:
                    ssh_config = SshConfiguration(
                        public_keys=[
                            SshPublicKey(
                                path=f"/home/{self.admin_username}/.ssh/authorized_keys",
                                key_data=self.ssh_key,
                            )
                        ]
                    )
                    os_profile_params["linux_configuration"] = LinuxConfiguration(
                        disable_password_authentication=True,
                        ssh=ssh_config,
                    )
                elif self.admin_password:
                    os_profile_params["admin_password"] = self.admin_password

                if self.custom_data:
                    import base64
                    os_profile_params["custom_data"] = base64.b64encode(
                        self.custom_data.encode()
                    ).decode()

                os_profile = OSProfile(**os_profile_params)

                network_profile = NetworkProfile(
                    network_interfaces=[
                        NetworkInterfaceReference(id=nic_id, primary=True)
                    ]
                )

                # إعداد VM params
                vm_params: dict[str, Any] = {
                    "location": self.location,
                    "tags": azure_tags,
                    "hardware_profile": hardware_profile,
                    "storage_profile": storage_profile,
                    "os_profile": os_profile,
                    "network_profile": network_profile,
                }

                # Spot VM configuration
                if self.spot_vm:
                    vm_params["priority"] = VirtualMachinePriorityTypes.SPOT
                    vm_params["eviction_policy"] = VirtualMachineEvictionPolicyTypes.DEALLOCATE
                    if self.spot_max_price >= 0:
                        vm_params["billing_profile"] = BillingProfile(
                            max_price=self.spot_max_price
                        )

                vm = VirtualMachine(**vm_params)

                # إنشاء الـ VM
                poller = await self._run_in_executor(
                    self._compute_client.virtual_machines.begin_create_or_update,
                    self.resource_group,
                    vm_name,
                    vm,
                )

                await self._run_in_executor(poller.result)

                instance_ids.append(vm_name)

                # تحديث الذاكرة المحلية
                self._instances[vm_name] = InstanceInfo(
                    instance_id=vm_name,
                    provider="azure",
                    state=InstanceState.PENDING,
                    instance_type=vm_size,
                    zone=self.location,
                    created_at=datetime.utcnow(),
                    tags=azure_tags,
                    labels=merged_labels,
                )

                logger.info(f"[Azure] Provisioned VM: {vm_name}")

            except Exception as e:
                logger.error(f"[Azure] Failed to provision VM: {e}")
                raise ProvisioningError(f"Failed to provision Azure VM: {e}")

        return instance_ids

    async def terminate_workers(self, instance_ids: list[str]) -> int:
        """
        إنهاء Azure VMs
        Terminate Azure VMs
        """
        if not self._connected:
            raise TerminationError("Provider not connected")

        if not instance_ids:
            return 0

        terminated = 0

        for vm_name in instance_ids:
            try:
                # حذف الـ VM
                poller = await self._run_in_executor(
                    self._compute_client.virtual_machines.begin_delete,
                    self.resource_group,
                    vm_name,
                )

                await self._run_in_executor(poller.result)

                # حذف NIC
                nic_name = f"{vm_name}-nic"
                try:
                    nic_poller = await self._run_in_executor(
                        self._network_client.network_interfaces.begin_delete,
                        self.resource_group,
                        nic_name,
                    )
                    await self._run_in_executor(nic_poller.result)
                except Exception:
                    pass  # NIC might not exist or already deleted

                # تحديث الذاكرة المحلية
                if vm_name in self._instances:
                    self._instances[vm_name].state = InstanceState.TERMINATED

                terminated += 1
                logger.info(f"[Azure] Terminated VM: {vm_name}")

            except Exception as e:
                logger.error(f"[Azure] Failed to terminate VM {vm_name}: {e}")

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
            vms = await self._run_in_executor(
                list,
                self._compute_client.virtual_machines.list(self.resource_group),
            )

            instances: list[InstanceInfo] = []

            for vm in vms:
                # التحقق من الـ tags
                vm_tags = vm.tags or {}
                if "managed-by" not in vm_tags or vm_tags.get("managed-by") != "distributed-cluster":
                    continue

                # الحصول على حالة الـ VM
                vm_instance = await self._run_in_executor(
                    self._compute_client.virtual_machines.instance_view,
                    self.resource_group,
                    vm.name,
                )

                azure_state = InstanceState.UNKNOWN
                if vm_instance.statuses:
                    for status in vm_instance.statuses:
                        if status.code.startswith("PowerState/"):
                            power_state = status.code.replace("PowerState/", "")
                            azure_state = AZURE_STATE_MAP.get(
                                power_state.capitalize(), InstanceState.UNKNOWN
                            )
                            break

                if state and azure_state != state:
                    continue

                # الحصول على IP
                private_ip = None
                if vm.network_profile and vm.network_profile.network_interfaces:
                    nic_id = vm.network_profile.network_interfaces[0].id
                    nic_name = nic_id.split("/")[-1]
                    try:
                        nic = await self._run_in_executor(
                            self._network_client.network_interfaces.get,
                            self.resource_group,
                            nic_name,
                        )
                        if nic.ip_configurations:
                            private_ip = nic.ip_configurations[0].private_ip_address
                    except Exception:
                        pass

                instance_info = InstanceInfo(
                    instance_id=vm.name,
                    provider="azure",
                    state=azure_state,
                    instance_type=vm.hardware_profile.vm_size if vm.hardware_profile else "",
                    zone=vm.location,
                    private_ip=private_ip,
                    tags=vm_tags,
                )

                instances.append(instance_info)
                self._instances[vm.name] = instance_info

            return instances

        except Exception as e:
            logger.error(f"[Azure] Failed to get instances: {e}")
            return []

    async def get_instance(self, instance_id: str) -> Optional[InstanceInfo]:
        """الحصول على instance واحد"""
        if not self._connected:
            return None

        try:
            vm = await self._run_in_executor(
                self._compute_client.virtual_machines.get,
                self.resource_group,
                instance_id,
            )

            vm_instance = await self._run_in_executor(
                self._compute_client.virtual_machines.instance_view,
                self.resource_group,
                instance_id,
            )

            azure_state = InstanceState.UNKNOWN
            if vm_instance.statuses:
                for status in vm_instance.statuses:
                    if status.code.startswith("PowerState/"):
                        power_state = status.code.replace("PowerState/", "")
                        azure_state = AZURE_STATE_MAP.get(
                            power_state.capitalize(), InstanceState.UNKNOWN
                        )
                        break

            return InstanceInfo(
                instance_id=vm.name,
                provider="azure",
                state=azure_state,
                instance_type=vm.hardware_profile.vm_size if vm.hardware_profile else "",
                zone=vm.location,
                tags=vm.tags or {},
            )

        except Exception as e:
            logger.error(f"[Azure] Failed to get instance {instance_id}: {e}")
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
            "provider_type": "azure",
            "subscription_id": self.subscription_id[:8] + "...",
            "resource_group": self.resource_group,
            "location": self.location,
            "vm_size": self.vm_size,
            "spot_vm": self.spot_vm,
            "estimated_cost_per_hour": self.config.cost_per_hour,
        })
        return status
