"""
AWS Provider - مزود Amazon Web Services
========================================

AWS Cloud Provider for Auto-Scaling
-----------------------------------

This module provides integration with AWS EC2 for provisioning
and terminating worker instances.

يوفر هذا الملف التكامل مع AWS EC2 لإنشاء وإنهاء العمال:
- إنشاء EC2 instances
- إدارة Auto Scaling Groups
- دعم Spot Instances
- تكامل مع VPC/Subnets

Requirements:
- boto3 library
- AWS credentials configured

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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

# AWS state mapping
AWS_STATE_MAP = {
    "pending": InstanceState.PENDING,
    "running": InstanceState.RUNNING,
    "stopping": InstanceState.STOPPING,
    "stopped": InstanceState.STOPPED,
    "shutting-down": InstanceState.TERMINATING,
    "terminated": InstanceState.TERMINATED,
}


class AWSProvider(CloudProvider):
    """
    مزود Amazon Web Services للتوسع التلقائي
    AWS Cloud Provider for auto-scaling

    يستخدم boto3 للتفاعل مع AWS EC2.
    Uses boto3 to interact with AWS EC2.
    """

    def __init__(
        self,
        region: str = "us-east-1",
        instance_type: str = "t3.large",
        ami_id: Optional[str] = None,
        key_name: Optional[str] = None,
        security_group_ids: Optional[list[str]] = None,
        subnet_id: Optional[str] = None,
        iam_instance_profile: Optional[str] = None,
        user_data: Optional[str] = None,
        spot_enabled: bool = False,
        spot_max_price: Optional[str] = None,
        config: Optional[ProviderConfig] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ):
        """
        تهيئة مزود AWS

        Args:
            region: منطقة AWS (مثل us-east-1)
            instance_type: نوع الـ instance (مثل t3.large)
            ami_id: معرف AMI للعامل
            key_name: اسم مفتاح SSH
            security_group_ids: معرفات مجموعات الأمان
            subnet_id: معرف الشبكة الفرعية
            iam_instance_profile: ملف IAM profile
            user_data: سكربت بدء التشغيل
            spot_enabled: استخدام Spot Instances
            spot_max_price: أقصى سعر للـ Spot
            config: إعدادات إضافية
            aws_access_key_id: مفتاح AWS (اختياري)
            aws_secret_access_key: سر AWS (اختياري)
        """
        super().__init__(config)

        self.region = region
        self.instance_type = instance_type
        self.ami_id = ami_id
        self.key_name = key_name
        self.security_group_ids = security_group_ids or []
        self.subnet_id = subnet_id
        self.iam_instance_profile = iam_instance_profile
        self.user_data = user_data
        self.spot_enabled = spot_enabled
        self.spot_max_price = spot_max_price

        # AWS credentials
        self._aws_access_key_id = aws_access_key_id
        self._aws_secret_access_key = aws_secret_access_key

        # AWS clients
        self._ec2_client = None
        self._ec2_resource = None

        # Thread pool for boto3 (which is not async)
        self._executor = ThreadPoolExecutor(max_workers=4)

        # إعداد التكلفة التقريبية
        self.config.cost_per_hour = self._estimate_hourly_cost()

    def _estimate_hourly_cost(self) -> float:
        """تقدير التكلفة بالساعة (تقريبي)"""
        # أسعار تقريبية لـ On-Demand في us-east-1
        instance_prices = {
            "t3.micro": 0.0104,
            "t3.small": 0.0208,
            "t3.medium": 0.0416,
            "t3.large": 0.0832,
            "t3.xlarge": 0.1664,
            "t3.2xlarge": 0.3328,
            "m5.large": 0.096,
            "m5.xlarge": 0.192,
            "m5.2xlarge": 0.384,
            "c5.large": 0.085,
            "c5.xlarge": 0.17,
            "c5.2xlarge": 0.34,
            "p3.2xlarge": 3.06,  # GPU
            "p3.8xlarge": 12.24,  # GPU
            "g4dn.xlarge": 0.526,  # GPU
            "g4dn.2xlarge": 0.752,  # GPU
        }
        return instance_prices.get(self.instance_type, 0.10)

    async def connect(self) -> None:
        """الاتصال بـ AWS"""
        try:
            import boto3

            session_kwargs = {"region_name": self.region}

            if self._aws_access_key_id and self._aws_secret_access_key:
                session_kwargs["aws_access_key_id"] = self._aws_access_key_id
                session_kwargs["aws_secret_access_key"] = self._aws_secret_access_key

            session = boto3.Session(**session_kwargs)
            self._ec2_client = session.client("ec2")
            self._ec2_resource = session.resource("ec2")

            # اختبار الاتصال
            await self._run_in_executor(self._ec2_client.describe_instances, MaxResults=5)

            self._connected = True
            logger.info(f"Connected to AWS EC2 in region {self.region}")

        except ImportError:
            raise ProvisioningError("boto3 is required for AWS provider. Install it with: pip install boto3")
        except Exception as e:
            raise ProvisioningError(f"Failed to connect to AWS: {e}")

    async def disconnect(self) -> None:
        """قطع الاتصال"""
        self._ec2_client = None
        self._ec2_resource = None
        self._connected = False
        logger.info("Disconnected from AWS EC2")

    async def _run_in_executor(self, func, *args, **kwargs):
        """تشغيل دالة boto3 في thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, lambda: func(*args, **kwargs))

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
        إنشاء EC2 instances
        Provision EC2 instances
        """
        if not self._connected:
            raise ProvisioningError("Provider not connected")

        instance_type = instance_type or self.instance_type
        merged_tags = self._merge_tags(tags)
        merged_labels = self._merge_labels(labels)

        # إضافة التسميات كـ tags
        for key, value in merged_labels.items():
            merged_tags[key] = value

        # تحويل tags إلى صيغة AWS
        aws_tags = [{"Key": k, "Value": v} for k, v in merged_tags.items()]
        aws_tags.append({"Key": "Name", "Value": "distributed-cluster-worker"})

        try:
            # إعداد طلب الإنشاء
            run_kwargs: dict[str, Any] = {
                "ImageId": self.ami_id,
                "InstanceType": instance_type,
                "MinCount": count,
                "MaxCount": count,
                "TagSpecifications": [{"ResourceType": "instance", "Tags": aws_tags}],
            }

            if self.key_name:
                run_kwargs["KeyName"] = self.key_name

            if self.security_group_ids:
                run_kwargs["SecurityGroupIds"] = self.security_group_ids

            if self.subnet_id:
                run_kwargs["SubnetId"] = self.subnet_id

            if self.iam_instance_profile:
                run_kwargs["IamInstanceProfile"] = {"Name": self.iam_instance_profile}

            if self.user_data:
                import base64

                run_kwargs["UserData"] = base64.b64encode(self.user_data.encode()).decode()

            # Spot instances
            if self.spot_enabled:
                run_kwargs["InstanceMarketOptions"] = {
                    "MarketType": "spot",
                    "SpotOptions": {
                        "SpotInstanceType": "one-time",
                    },
                }
                if self.spot_max_price:
                    run_kwargs["InstanceMarketOptions"]["SpotOptions"]["MaxPrice"] = self.spot_max_price

            # إنشاء الـ instances
            response = await self._run_in_executor(self._ec2_client.run_instances, **run_kwargs)

            instance_ids = [inst["InstanceId"] for inst in response["Instances"]]

            logger.info(f"[AWS] Provisioned {len(instance_ids)} instances: {instance_ids}")

            # تحديث الذاكرة المحلية
            for inst in response["Instances"]:
                self._instances[inst["InstanceId"]] = InstanceInfo(
                    instance_id=inst["InstanceId"],
                    provider="aws",
                    state=AWS_STATE_MAP.get(inst["State"]["Name"], InstanceState.UNKNOWN),
                    instance_type=inst["InstanceType"],
                    zone=inst.get("Placement", {}).get("AvailabilityZone", ""),
                    private_ip=inst.get("PrivateIpAddress"),
                    created_at=datetime.now(timezone.utc),
                    tags=merged_tags,
                    labels=merged_labels,
                )

            return instance_ids

        except Exception as e:
            logger.error(f"[AWS] Failed to provision instances: {e}")
            raise ProvisioningError(f"Failed to provision AWS instances: {e}")

    async def terminate_workers(self, instance_ids: list[str]) -> int:
        """
        إنهاء EC2 instances
        Terminate EC2 instances
        """
        if not self._connected:
            raise TerminationError("Provider not connected")

        if not instance_ids:
            return 0

        try:
            response = await self._run_in_executor(self._ec2_client.terminate_instances, InstanceIds=instance_ids)

            terminated = len(response.get("TerminatingInstances", []))

            # تحديث الذاكرة المحلية
            for instance_id in instance_ids:
                if instance_id in self._instances:
                    self._instances[instance_id].state = InstanceState.TERMINATING

            logger.info(f"[AWS] Terminated {terminated} instances: {instance_ids}")
            return terminated

        except Exception as e:
            logger.error(f"[AWS] Failed to terminate instances: {e}")
            raise TerminationError(f"Failed to terminate AWS instances: {e}")

    async def get_instances(
        self,
        state: Optional[InstanceState] = None,
        tags: Optional[dict[str, str]] = None,
    ) -> list[InstanceInfo]:
        """الحصول على قائمة الـ instances"""
        if not self._connected:
            return []

        try:
            filters: list[dict[str, Any]] = [
                {"Name": "tag:managed-by", "Values": ["distributed-cluster"]},
            ]

            if state:
                # تحويل الحالة إلى صيغة AWS
                aws_states = [k for k, v in AWS_STATE_MAP.items() if v == state]
                if aws_states:
                    filters.append({"Name": "instance-state-name", "Values": aws_states})

            if tags:
                for key, value in tags.items():
                    filters.append({"Name": f"tag:{key}", "Values": [value]})

            response = await self._run_in_executor(self._ec2_client.describe_instances, Filters=filters)

            instances: list[InstanceInfo] = []

            for reservation in response.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    # تحويل tags إلى dict
                    inst_tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}

                    instance_info = InstanceInfo(
                        instance_id=inst["InstanceId"],
                        provider="aws",
                        state=AWS_STATE_MAP.get(inst["State"]["Name"], InstanceState.UNKNOWN),
                        instance_type=inst["InstanceType"],
                        zone=inst.get("Placement", {}).get("AvailabilityZone", ""),
                        private_ip=inst.get("PrivateIpAddress"),
                        public_ip=inst.get("PublicIpAddress"),
                        created_at=inst.get("LaunchTime"),
                        tags=inst_tags,
                    )

                    instances.append(instance_info)
                    self._instances[inst["InstanceId"]] = instance_info

            return instances

        except Exception as e:
            logger.error(f"[AWS] Failed to get instances: {e}")
            return []

    async def get_instance(self, instance_id: str) -> Optional[InstanceInfo]:
        """الحصول على instance واحد"""
        if not self._connected:
            return None

        try:
            response = await self._run_in_executor(self._ec2_client.describe_instances, InstanceIds=[instance_id])

            for reservation in response.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    inst_tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}

                    return InstanceInfo(
                        instance_id=inst["InstanceId"],
                        provider="aws",
                        state=AWS_STATE_MAP.get(inst["State"]["Name"], InstanceState.UNKNOWN),
                        instance_type=inst["InstanceType"],
                        zone=inst.get("Placement", {}).get("AvailabilityZone", ""),
                        private_ip=inst.get("PrivateIpAddress"),
                        public_ip=inst.get("PublicIpAddress"),
                        created_at=inst.get("LaunchTime"),
                        tags=inst_tags,
                    )

            return None

        except Exception as e:
            logger.error(f"[AWS] Failed to get instance {instance_id}: {e}")
            return None

    async def get_terminable_workers(self, count: int) -> list[str]:
        """الحصول على عمال قابلين للإنهاء"""
        instances = await self.get_instances(state=InstanceState.RUNNING)

        # فرز حسب وقت الإنشاء (الأحدث أولاً)
        instances.sort(
            key=lambda i: i.created_at or datetime.min,
            reverse=True,
        )

        # اختيار الـ instances القابلة للإنهاء
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
        status.update(
            {
                "provider_type": "aws",
                "region": self.region,
                "instance_type": self.instance_type,
                "ami_id": self.ami_id,
                "spot_enabled": self.spot_enabled,
                "estimated_cost_per_hour": self.config.cost_per_hour,
            }
        )
        return status
