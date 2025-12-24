# -*- coding: utf-8 -*-
"""
Cloud Providers for NebulaCompute.

Abstract and concrete implementations for cloud provider integration.

تكامل مع مزودي الخدمات السحابية.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class InstanceType(str, Enum):
    """Instance type category."""

    ON_DEMAND = "on_demand"
    SPOT = "spot"
    RESERVED = "reserved"
    PREEMPTIBLE = "preemptible"


@dataclass
class CloudInstance:
    """
    Cloud instance representation.

    تمثيل Instance سحابي.
    """

    instance_id: str
    provider: str
    region: str
    zone: str
    instance_type: str
    pricing_type: InstanceType
    vcpus: int
    memory_gb: float
    gpu_count: int = 0
    gpu_type: Optional[str] = None
    hourly_cost: float = 0.0
    state: str = "running"
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    launch_time: Optional[datetime] = None
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "instance_id": self.instance_id,
            "provider": self.provider,
            "region": self.region,
            "zone": self.zone,
            "instance_type": self.instance_type,
            "pricing_type": self.pricing_type.value,
            "vcpus": self.vcpus,
            "memory_gb": self.memory_gb,
            "gpu_count": self.gpu_count,
            "gpu_type": self.gpu_type,
            "hourly_cost": self.hourly_cost,
            "state": self.state,
            "public_ip": self.public_ip,
            "private_ip": self.private_ip,
            "launch_time": self.launch_time.isoformat() if self.launch_time else None,
            "tags": self.tags,
        }


class CloudProvider(ABC):
    """
    Abstract base class for cloud providers.

    واجهة أساسية لمزودي الخدمات السحابية.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @abstractmethod
    async def list_instances(
        self,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[CloudInstance]:
        """List all instances."""
        pass

    @abstractmethod
    async def get_instance(self, instance_id: str) -> Optional[CloudInstance]:
        """Get instance by ID."""
        pass

    @abstractmethod
    async def launch_instance(
        self,
        instance_type: str,
        region: str,
        zone: str,
        pricing_type: InstanceType = InstanceType.ON_DEMAND,
        tags: Optional[Dict[str, str]] = None,
    ) -> CloudInstance:
        """Launch a new instance."""
        pass

    @abstractmethod
    async def terminate_instance(self, instance_id: str) -> bool:
        """Terminate an instance."""
        pass

    @abstractmethod
    async def get_spot_price(
        self,
        instance_type: str,
        region: str,
        zone: Optional[str] = None,
    ) -> float:
        """Get current spot price."""
        pass


class AWSProvider(CloudProvider):
    """
    AWS Cloud Provider implementation.

    تكامل مع Amazon Web Services.
    """

    def __init__(
        self,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        region: str = "us-east-1",
    ):
        """Initialize AWS provider."""
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self._client = None

    @property
    def name(self) -> str:
        return "aws"

    async def _get_client(self):
        """Get or create EC2 client."""
        if self._client is None:
            try:
                import boto3

                self._client = boto3.client(
                    "ec2",
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                    region_name=self.region,
                )
            except ImportError:
                logger.warning("boto3 not available, using mock client")
                self._client = "mock"
        return self._client

    async def list_instances(
        self,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[CloudInstance]:
        """List EC2 instances."""
        client = await self._get_client()

        if client == "mock":
            return []

        try:
            aws_filters = []
            if filters:
                for key, value in filters.items():
                    aws_filters.append({"Name": key, "Values": [value]})

            response = client.describe_instances(Filters=aws_filters)
            instances = []

            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instances.append(self._parse_instance(instance))

            return instances

        except Exception as e:
            logger.error(f"Error listing AWS instances: {e}")
            return []

    async def get_instance(self, instance_id: str) -> Optional[CloudInstance]:
        """Get EC2 instance by ID."""
        client = await self._get_client()

        if client == "mock":
            return None

        try:
            response = client.describe_instances(InstanceIds=[instance_id])

            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    return self._parse_instance(instance)

            return None

        except Exception as e:
            logger.error(f"Error getting AWS instance {instance_id}: {e}")
            return None

    async def launch_instance(
        self,
        instance_type: str,
        region: str,
        zone: str,
        pricing_type: InstanceType = InstanceType.ON_DEMAND,
        tags: Optional[Dict[str, str]] = None,
    ) -> CloudInstance:
        """Launch EC2 instance."""
        # In production, would use boto3 to launch instance
        raise NotImplementedError("Instance launching not implemented")

    async def terminate_instance(self, instance_id: str) -> bool:
        """Terminate EC2 instance."""
        client = await self._get_client()

        if client == "mock":
            return False

        try:
            client.terminate_instances(InstanceIds=[instance_id])
            return True
        except Exception as e:
            logger.error(f"Error terminating AWS instance {instance_id}: {e}")
            return False

    async def get_spot_price(
        self,
        instance_type: str,
        region: str,
        zone: Optional[str] = None,
    ) -> float:
        """Get current EC2 spot price."""
        client = await self._get_client()

        if client == "mock":
            return 0.0

        try:
            response = client.describe_spot_price_history(
                InstanceTypes=[instance_type],
                ProductDescriptions=["Linux/UNIX"],
                MaxResults=1,
            )

            prices = response.get("SpotPriceHistory", [])
            if prices:
                return float(prices[0]["SpotPrice"])

            return 0.0

        except Exception as e:
            logger.error(f"Error getting AWS spot price: {e}")
            return 0.0

    def _parse_instance(self, instance: Dict) -> CloudInstance:
        """Parse AWS instance data."""
        tags = {
            tag["Key"]: tag["Value"]
            for tag in instance.get("Tags", [])
        }

        pricing_type = InstanceType.ON_DEMAND
        if instance.get("InstanceLifecycle") == "spot":
            pricing_type = InstanceType.SPOT

        return CloudInstance(
            instance_id=instance["InstanceId"],
            provider="aws",
            region=self.region,
            zone=instance.get("Placement", {}).get("AvailabilityZone", ""),
            instance_type=instance["InstanceType"],
            pricing_type=pricing_type,
            vcpus=instance.get("CpuOptions", {}).get("CoreCount", 1),
            memory_gb=0,  # Would need to look up from instance type
            state=instance["State"]["Name"],
            public_ip=instance.get("PublicIpAddress"),
            private_ip=instance.get("PrivateIpAddress"),
            launch_time=instance.get("LaunchTime"),
            tags=tags,
        )


class GCPProvider(CloudProvider):
    """
    Google Cloud Platform Provider implementation.

    تكامل مع Google Cloud Platform.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
        region: str = "us-central1",
    ):
        """Initialize GCP provider."""
        self.project_id = project_id
        self.credentials_path = credentials_path
        self.region = region
        self._client = None

    @property
    def name(self) -> str:
        return "gcp"

    async def list_instances(
        self,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[CloudInstance]:
        """List GCE instances."""
        # Would use google-cloud-compute library
        return []

    async def get_instance(self, instance_id: str) -> Optional[CloudInstance]:
        """Get GCE instance by ID."""
        return None

    async def launch_instance(
        self,
        instance_type: str,
        region: str,
        zone: str,
        pricing_type: InstanceType = InstanceType.ON_DEMAND,
        tags: Optional[Dict[str, str]] = None,
    ) -> CloudInstance:
        """Launch GCE instance."""
        raise NotImplementedError("Instance launching not implemented")

    async def terminate_instance(self, instance_id: str) -> bool:
        """Terminate GCE instance."""
        return False

    async def get_spot_price(
        self,
        instance_type: str,
        region: str,
        zone: Optional[str] = None,
    ) -> float:
        """Get GCE preemptible price."""
        return 0.0


class AzureProvider(CloudProvider):
    """
    Microsoft Azure Provider implementation.

    تكامل مع Microsoft Azure.
    """

    def __init__(
        self,
        subscription_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        region: str = "eastus",
    ):
        """Initialize Azure provider."""
        self.subscription_id = subscription_id
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.region = region
        self._client = None

    @property
    def name(self) -> str:
        return "azure"

    async def list_instances(
        self,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[CloudInstance]:
        """List Azure VMs."""
        # Would use azure-mgmt-compute library
        return []

    async def get_instance(self, instance_id: str) -> Optional[CloudInstance]:
        """Get Azure VM by ID."""
        return None

    async def launch_instance(
        self,
        instance_type: str,
        region: str,
        zone: str,
        pricing_type: InstanceType = InstanceType.ON_DEMAND,
        tags: Optional[Dict[str, str]] = None,
    ) -> CloudInstance:
        """Launch Azure VM."""
        raise NotImplementedError("Instance launching not implemented")

    async def terminate_instance(self, instance_id: str) -> bool:
        """Terminate Azure VM."""
        return False

    async def get_spot_price(
        self,
        instance_type: str,
        region: str,
        zone: Optional[str] = None,
    ) -> float:
        """Get Azure spot price."""
        return 0.0
