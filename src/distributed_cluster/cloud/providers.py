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
        image_id: Optional[str] = None,
        key_name: Optional[str] = None,
        security_group_ids: Optional[List[str]] = None,
        subnet_id: Optional[str] = None,
        user_data: Optional[str] = None,
    ) -> CloudInstance:
        """
        Launch EC2 instance.

        إطلاق EC2 Instance جديد.

        Args:
            instance_type: EC2 instance type (e.g., 't3.medium', 'p3.2xlarge')
            region: AWS region
            zone: Availability zone
            pricing_type: ON_DEMAND or SPOT
            tags: Instance tags
            image_id: AMI ID (defaults to latest Amazon Linux 2)
            key_name: SSH key pair name
            security_group_ids: Security group IDs
            subnet_id: VPC subnet ID
            user_data: User data script for instance initialization

        Returns:
            CloudInstance object
        """
        client = await self._get_client()

        if client == "mock":
            # Return mock instance for testing
            import uuid
            mock_id = f"i-{uuid.uuid4().hex[:17]}"
            return CloudInstance(
                instance_id=mock_id,
                provider="aws",
                region=region,
                zone=zone,
                instance_type=instance_type,
                pricing_type=pricing_type,
                vcpus=2,
                memory_gb=4.0,
                state="pending",
                launch_time=datetime.now(),
                tags=tags or {},
            )

        try:
            # Get default AMI if not specified (Amazon Linux 2)
            if not image_id:
                ssm = await self._get_ssm_client()
                if ssm != "mock":
                    response = ssm.get_parameter(
                        Name="/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2"
                    )
                    image_id = response["Parameter"]["Value"]
                else:
                    image_id = "ami-0c55b159cbfafe1f0"  # Fallback

            # Prepare launch parameters
            launch_params = {
                "ImageId": image_id,
                "InstanceType": instance_type,
                "MinCount": 1,
                "MaxCount": 1,
                "Placement": {"AvailabilityZone": zone},
            }

            if key_name:
                launch_params["KeyName"] = key_name

            if security_group_ids:
                launch_params["SecurityGroupIds"] = security_group_ids

            if subnet_id:
                launch_params["SubnetId"] = subnet_id

            if user_data:
                import base64
                launch_params["UserData"] = base64.b64encode(
                    user_data.encode()
                ).decode()

            # Add NebulaCompute tags
            all_tags = {
                "CreatedBy": "NebulaCompute",
                "ManagedBy": "NebulaCompute",
            }
            if tags:
                all_tags.update(tags)

            launch_params["TagSpecifications"] = [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": k, "Value": v} for k, v in all_tags.items()
                    ],
                }
            ]

            # Launch spot or on-demand
            if pricing_type == InstanceType.SPOT:
                # Request spot instance
                spot_response = client.request_spot_instances(
                    InstanceCount=1,
                    LaunchSpecification={
                        "ImageId": image_id,
                        "InstanceType": instance_type,
                        "Placement": {"AvailabilityZone": zone},
                        "KeyName": key_name,
                        "SecurityGroupIds": security_group_ids or [],
                        "SubnetId": subnet_id,
                    },
                )

                # Wait for spot request to be fulfilled
                import asyncio
                spot_request_id = spot_response["SpotInstanceRequests"][0][
                    "SpotInstanceRequestId"
                ]

                for _ in range(60):  # Wait up to 5 minutes
                    spot_status = client.describe_spot_instance_requests(
                        SpotInstanceRequestIds=[spot_request_id]
                    )
                    status = spot_status["SpotInstanceRequests"][0]["Status"]["Code"]

                    if status == "fulfilled":
                        instance_id = spot_status["SpotInstanceRequests"][0][
                            "InstanceId"
                        ]
                        break
                    elif status in ["capacity-not-available", "price-too-low"]:
                        raise RuntimeError(f"Spot request failed: {status}")

                    await asyncio.sleep(5)
                else:
                    raise RuntimeError("Timeout waiting for spot instance")

            else:
                # Launch on-demand instance
                response = client.run_instances(**launch_params)
                instance_id = response["Instances"][0]["InstanceId"]

            # Wait for instance to be running
            waiter = client.get_waiter("instance_running")
            waiter.wait(InstanceIds=[instance_id])

            # Get instance details
            return await self.get_instance(instance_id)

        except Exception as e:
            logger.error(f"Error launching AWS instance: {e}")
            raise RuntimeError(f"Failed to launch EC2 instance: {e}")

    async def _get_ssm_client(self):
        """Get or create SSM client for parameter store."""
        try:
            import boto3
            return boto3.client(
                "ssm",
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region,
            )
        except ImportError:
            return "mock"

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

    # GCP machine type specifications (vCPUs, memory in GB)
    MACHINE_SPECS: Dict[str, tuple] = {
        "n1-standard-1": (1, 3.75),
        "n1-standard-2": (2, 7.5),
        "n1-standard-4": (4, 15),
        "n1-standard-8": (8, 30),
        "n1-standard-16": (16, 60),
        "n2-standard-2": (2, 8),
        "n2-standard-4": (4, 16),
        "n2-standard-8": (8, 32),
        "e2-micro": (0.25, 1),
        "e2-small": (0.5, 2),
        "e2-medium": (1, 4),
        "a2-highgpu-1g": (12, 85),  # 1x A100
        "a2-highgpu-2g": (24, 170),  # 2x A100
    }

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
        self._compute_client = None
        self._instances_client = None

    @property
    def name(self) -> str:
        return "gcp"

    async def _get_clients(self):
        """Get or create GCP compute clients."""
        if self._instances_client is None:
            try:
                from google.cloud import compute_v1
                from google.oauth2 import service_account

                if self.credentials_path:
                    credentials = service_account.Credentials.from_service_account_file(
                        self.credentials_path
                    )
                    self._instances_client = compute_v1.InstancesClient(
                        credentials=credentials
                    )
                else:
                    self._instances_client = compute_v1.InstancesClient()

                logger.info("GCP Compute client initialized")
            except ImportError:
                logger.warning("google-cloud-compute not available, using mock")
                self._instances_client = "mock"
            except Exception as e:
                logger.error(f"Failed to initialize GCP client: {e}")
                self._instances_client = "mock"

        return self._instances_client

    async def list_instances(
        self,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[CloudInstance]:
        """
        List GCE instances.

        سرد جميع GCE instances.
        """
        client = await self._get_clients()

        if client == "mock":
            return []

        try:
            from google.cloud import compute_v1

            instances = []
            # List instances in all zones of the region
            zones_client = compute_v1.ZonesClient()

            for zone in zones_client.list(project=self.project_id):
                if zone.name.startswith(self.region):
                    request = compute_v1.ListInstancesRequest(
                        project=self.project_id,
                        zone=zone.name,
                    )

                    if filters:
                        filter_str = " AND ".join(
                            f"{k}={v}" for k, v in filters.items()
                        )
                        request.filter = filter_str

                    for instance in client.list(request=request):
                        instances.append(self._parse_instance(instance, zone.name))

            return instances

        except Exception as e:
            logger.error(f"Error listing GCP instances: {e}")
            return []

    async def get_instance(self, instance_id: str) -> Optional[CloudInstance]:
        """
        Get GCE instance by ID.

        جلب GCE instance بواسطة المعرف.
        """
        client = await self._get_clients()

        if client == "mock":
            return None

        try:
            from google.cloud import compute_v1

            # Instance ID format: zones/{zone}/instances/{name}
            parts = instance_id.split("/")
            if len(parts) >= 4:
                zone = parts[1]
                name = parts[3]
            else:
                # Assume it's just the name, search in region zones
                name = instance_id
                zone = f"{self.region}-a"  # Default zone

            request = compute_v1.GetInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=name,
            )

            instance = client.get(request=request)
            return self._parse_instance(instance, zone)

        except Exception as e:
            logger.error(f"Error getting GCP instance {instance_id}: {e}")
            return None

    async def launch_instance(
        self,
        instance_type: str,
        region: str,
        zone: str,
        pricing_type: InstanceType = InstanceType.ON_DEMAND,
        tags: Optional[Dict[str, str]] = None,
        image_family: str = "debian-11",
        image_project: str = "debian-cloud",
        network: str = "default",
        subnet: Optional[str] = None,
        startup_script: Optional[str] = None,
        service_account_email: Optional[str] = None,
    ) -> CloudInstance:
        """
        Launch GCE instance.

        إطلاق GCE Instance جديد.

        Args:
            instance_type: Machine type (e.g., 'n1-standard-2')
            region: GCP region
            zone: GCP zone
            pricing_type: ON_DEMAND or PREEMPTIBLE
            tags: Instance labels
            image_family: OS image family
            image_project: Image project
            network: VPC network name
            subnet: Subnet name
            startup_script: Startup script content
            service_account_email: Service account for the instance

        Returns:
            CloudInstance object
        """
        client = await self._get_clients()

        if client == "mock":
            import uuid
            mock_id = f"nebula-{uuid.uuid4().hex[:8]}"
            specs = self.MACHINE_SPECS.get(instance_type, (2, 4))
            return CloudInstance(
                instance_id=f"zones/{zone}/instances/{mock_id}",
                provider="gcp",
                region=region,
                zone=zone,
                instance_type=instance_type,
                pricing_type=pricing_type,
                vcpus=int(specs[0]),
                memory_gb=specs[1],
                state="STAGING",
                launch_time=datetime.now(),
                tags=tags or {},
            )

        try:
            import uuid

            from google.cloud import compute_v1

            instance_name = f"nebula-{uuid.uuid4().hex[:8]}"

            # Get the latest image
            images_client = compute_v1.ImagesClient()
            image = images_client.get_from_family(
                project=image_project, family=image_family
            )

            # Prepare disk configuration
            disk = compute_v1.AttachedDisk(
                auto_delete=True,
                boot=True,
                initialize_params=compute_v1.AttachedDiskInitializeParams(
                    source_image=image.self_link,
                    disk_size_gb=50,
                ),
            )

            # Network interface
            network_interface = compute_v1.NetworkInterface(
                network=f"projects/{self.project_id}/global/networks/{network}",
                access_configs=[
                    compute_v1.AccessConfig(
                        name="External NAT",
                        type_="ONE_TO_ONE_NAT",
                    )
                ],
            )

            if subnet:
                network_interface.subnetwork = (
                    f"projects/{self.project_id}/regions/{region}/subnetworks/{subnet}"
                )

            # Prepare labels
            labels = {
                "created-by": "nebulacompute",
                "managed-by": "nebulacompute",
            }
            if tags:
                labels.update({k.lower().replace(" ", "-"): v for k, v in tags.items()})

            # Instance configuration
            instance = compute_v1.Instance(
                name=instance_name,
                machine_type=f"zones/{zone}/machineTypes/{instance_type}",
                disks=[disk],
                network_interfaces=[network_interface],
                labels=labels,
            )

            # Add startup script if provided
            if startup_script:
                instance.metadata = compute_v1.Metadata(
                    items=[
                        compute_v1.Items(
                            key="startup-script",
                            value=startup_script,
                        )
                    ]
                )

            # Set preemptible if requested
            if pricing_type == InstanceType.PREEMPTIBLE:
                instance.scheduling = compute_v1.Scheduling(
                    preemptible=True,
                    automatic_restart=False,
                )

            # Service account
            if service_account_email:
                instance.service_accounts = [
                    compute_v1.ServiceAccount(
                        email=service_account_email,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    )
                ]

            # Launch the instance
            request = compute_v1.InsertInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance_resource=instance,
            )

            operation = client.insert(request=request)

            # Wait for operation to complete
            import asyncio
            operations_client = compute_v1.ZoneOperationsClient()

            while operation.status != compute_v1.Operation.Status.DONE:
                await asyncio.sleep(2)
                operation = operations_client.get(
                    project=self.project_id,
                    zone=zone,
                    operation=operation.name,
                )

            if operation.error:
                raise RuntimeError(f"Instance creation failed: {operation.error}")

            # Get the created instance
            return await self.get_instance(f"zones/{zone}/instances/{instance_name}")

        except Exception as e:
            logger.error(f"Error launching GCP instance: {e}")
            raise RuntimeError(f"Failed to launch GCE instance: {e}")

    async def terminate_instance(self, instance_id: str) -> bool:
        """
        Terminate GCE instance.

        إنهاء GCE instance.
        """
        client = await self._get_clients()

        if client == "mock":
            return True

        try:
            from google.cloud import compute_v1

            # Parse instance ID
            parts = instance_id.split("/")
            if len(parts) >= 4:
                zone = parts[1]
                name = parts[3]
            else:
                name = instance_id
                zone = f"{self.region}-a"

            request = compute_v1.DeleteInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=name,
            )

            client.delete(request=request)
            logger.info(f"Terminated GCP instance: {instance_id}")
            return True

        except Exception as e:
            logger.error(f"Error terminating GCP instance {instance_id}: {e}")
            return False

    async def get_spot_price(
        self,
        instance_type: str,
        region: str,
        zone: Optional[str] = None,
    ) -> float:
        """
        Get GCE preemptible price estimate.

        الحصول على تقدير سعر preemptible.

        Note: GCP doesn't have dynamic spot pricing like AWS.
        Preemptible VMs are typically 60-91% cheaper than on-demand.
        """
        # GCP preemptible pricing is fixed at ~80% discount
        # These are approximate hourly rates for common machine types
        on_demand_prices = {
            "n1-standard-1": 0.0475,
            "n1-standard-2": 0.095,
            "n1-standard-4": 0.19,
            "n1-standard-8": 0.38,
            "n2-standard-2": 0.0971,
            "n2-standard-4": 0.1942,
            "e2-micro": 0.0084,
            "e2-small": 0.0168,
            "e2-medium": 0.0336,
            "a2-highgpu-1g": 3.67,
            "a2-highgpu-2g": 7.35,
        }

        on_demand = on_demand_prices.get(instance_type, 0.1)
        # Preemptible is typically 60-80% cheaper
        return on_demand * 0.2

    def _parse_instance(self, instance: Any, zone: str) -> CloudInstance:
        """Parse GCP instance data to CloudInstance."""
        # Extract machine type name
        machine_type = instance.machine_type.split("/")[-1]
        specs = self.MACHINE_SPECS.get(machine_type, (2, 4))

        # Determine pricing type
        pricing_type = InstanceType.ON_DEMAND
        if hasattr(instance, "scheduling") and instance.scheduling:
            if instance.scheduling.preemptible:
                pricing_type = InstanceType.PREEMPTIBLE

        # Get network IPs
        public_ip = None
        private_ip = None
        if instance.network_interfaces:
            ni = instance.network_interfaces[0]
            private_ip = ni.network_i_p if hasattr(ni, "network_i_p") else None
            if ni.access_configs:
                public_ip = ni.access_configs[0].nat_i_p

        # Parse labels
        labels = dict(instance.labels) if instance.labels else {}

        # Check for GPU
        gpu_count = 0
        gpu_type = None
        if hasattr(instance, "guest_accelerators") and instance.guest_accelerators:
            gpu_count = instance.guest_accelerators[0].accelerator_count
            gpu_type = instance.guest_accelerators[0].accelerator_type.split("/")[-1]

        return CloudInstance(
            instance_id=f"zones/{zone}/instances/{instance.name}",
            provider="gcp",
            region=self.region,
            zone=zone,
            instance_type=machine_type,
            pricing_type=pricing_type,
            vcpus=int(specs[0]),
            memory_gb=specs[1],
            gpu_count=gpu_count,
            gpu_type=gpu_type,
            state=instance.status,
            public_ip=public_ip,
            private_ip=private_ip,
            launch_time=datetime.fromisoformat(
                instance.creation_timestamp.replace("Z", "+00:00")
            ) if instance.creation_timestamp else None,
            tags=labels,
        )


class AzureProvider(CloudProvider):
    """
    Microsoft Azure Provider implementation.

    تكامل مع Microsoft Azure.
    """

    # Azure VM size specifications (vCPUs, memory in GB)
    VM_SPECS: Dict[str, tuple] = {
        "Standard_B1s": (1, 1),
        "Standard_B1ms": (1, 2),
        "Standard_B2s": (2, 4),
        "Standard_B2ms": (2, 8),
        "Standard_D2s_v3": (2, 8),
        "Standard_D4s_v3": (4, 16),
        "Standard_D8s_v3": (8, 32),
        "Standard_D16s_v3": (16, 64),
        "Standard_E2s_v3": (2, 16),
        "Standard_E4s_v3": (4, 32),
        "Standard_NC6": (6, 56),  # 1x K80
        "Standard_NC12": (12, 112),  # 2x K80
        "Standard_NC24": (24, 224),  # 4x K80
        "Standard_NC6s_v3": (6, 112),  # 1x V100
        "Standard_NC12s_v3": (12, 224),  # 2x V100
        "Standard_ND40rs_v2": (40, 672),  # 8x V100
    }

    def __init__(
        self,
        subscription_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        region: str = "eastus",
        resource_group: Optional[str] = None,
    ):
        """Initialize Azure provider."""
        self.subscription_id = subscription_id
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.region = region
        self.resource_group = resource_group or "nebulacompute-rg"
        self._compute_client = None
        self._network_client = None
        self._credential = None

    @property
    def name(self) -> str:
        return "azure"

    async def _get_credentials(self):
        """Get Azure credentials."""
        if self._credential is None:
            try:
                from azure.identity import ClientSecretCredential, DefaultAzureCredential

                if self.client_id and self.client_secret and self.tenant_id:
                    self._credential = ClientSecretCredential(
                        tenant_id=self.tenant_id,
                        client_id=self.client_id,
                        client_secret=self.client_secret,
                    )
                else:
                    self._credential = DefaultAzureCredential()

            except ImportError:
                logger.warning("azure-identity not available")
                self._credential = "mock"

        return self._credential

    async def _get_compute_client(self):
        """Get Azure Compute Management client."""
        if self._compute_client is None:
            try:
                from azure.mgmt.compute import ComputeManagementClient

                credential = await self._get_credentials()
                if credential == "mock":
                    self._compute_client = "mock"
                else:
                    self._compute_client = ComputeManagementClient(
                        credential=credential,
                        subscription_id=self.subscription_id,
                    )
                    logger.info("Azure Compute client initialized")

            except ImportError:
                logger.warning("azure-mgmt-compute not available")
                self._compute_client = "mock"

        return self._compute_client

    async def _get_network_client(self):
        """Get Azure Network Management client."""
        if self._network_client is None:
            try:
                from azure.mgmt.network import NetworkManagementClient

                credential = await self._get_credentials()
                if credential == "mock":
                    self._network_client = "mock"
                else:
                    self._network_client = NetworkManagementClient(
                        credential=credential,
                        subscription_id=self.subscription_id,
                    )

            except ImportError:
                self._network_client = "mock"

        return self._network_client

    async def list_instances(
        self,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[CloudInstance]:
        """
        List Azure VMs.

        سرد جميع Azure VMs.
        """
        client = await self._get_compute_client()

        if client == "mock":
            return []

        try:
            instances = []

            # List VMs in resource group
            for vm in client.virtual_machines.list(self.resource_group):
                # Apply filters
                if filters:
                    match = True
                    for key, value in filters.items():
                        if key == "tag":
                            tag_key, tag_value = value.split(":")
                            if vm.tags and vm.tags.get(tag_key) != tag_value:
                                match = False
                        elif key == "status":
                            instance_view = client.virtual_machines.instance_view(
                                self.resource_group, vm.name
                            )
                            statuses = [s.code for s in instance_view.statuses]
                            if f"PowerState/{value}" not in statuses:
                                match = False

                    if not match:
                        continue

                instances.append(await self._parse_instance(vm))

            return instances

        except Exception as e:
            logger.error(f"Error listing Azure VMs: {e}")
            return []

    async def get_instance(self, instance_id: str) -> Optional[CloudInstance]:
        """
        Get Azure VM by ID.

        جلب Azure VM بواسطة المعرف.
        """
        client = await self._get_compute_client()

        if client == "mock":
            return None

        try:
            # Instance ID could be full resource ID or just name
            if "/" in instance_id:
                # Parse resource ID
                parts = instance_id.split("/")
                vm_name = parts[-1]
                rg = parts[parts.index("resourceGroups") + 1] if "resourceGroups" in parts else self.resource_group
            else:
                vm_name = instance_id
                rg = self.resource_group

            vm = client.virtual_machines.get(rg, vm_name)
            return await self._parse_instance(vm)

        except Exception as e:
            logger.error(f"Error getting Azure VM {instance_id}: {e}")
            return None

    async def launch_instance(
        self,
        instance_type: str,
        region: str,
        zone: str,
        pricing_type: InstanceType = InstanceType.ON_DEMAND,
        tags: Optional[Dict[str, str]] = None,
        image_reference: Optional[Dict[str, str]] = None,
        admin_username: str = "nebulaadmin",
        ssh_public_key: Optional[str] = None,
        admin_password: Optional[str] = None,
        vnet_name: Optional[str] = None,
        subnet_name: Optional[str] = None,
        custom_data: Optional[str] = None,
    ) -> CloudInstance:
        """
        Launch Azure VM.

        إطلاق Azure VM جديد.

        Args:
            instance_type: VM size (e.g., 'Standard_D2s_v3')
            region: Azure region
            zone: Availability zone (1, 2, or 3)
            pricing_type: ON_DEMAND or SPOT
            tags: VM tags
            image_reference: Image reference (publisher, offer, sku, version)
            admin_username: Admin username
            ssh_public_key: SSH public key for authentication
            admin_password: Admin password (if not using SSH)
            vnet_name: Virtual network name
            subnet_name: Subnet name
            custom_data: Cloud-init custom data

        Returns:
            CloudInstance object
        """
        client = await self._get_compute_client()

        if client == "mock":
            import uuid
            mock_id = f"nebula-{uuid.uuid4().hex[:8]}"
            specs = self.VM_SPECS.get(instance_type, (2, 8))
            return CloudInstance(
                instance_id=f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}/providers/Microsoft.Compute/virtualMachines/{mock_id}",
                provider="azure",
                region=region,
                zone=zone,
                instance_type=instance_type,
                pricing_type=pricing_type,
                vcpus=specs[0],
                memory_gb=specs[1],
                state="Creating",
                launch_time=datetime.now(),
                tags=tags or {},
            )

        try:
            import uuid

            vm_name = f"nebula-{uuid.uuid4().hex[:8]}"

            # Default image reference (Ubuntu 22.04 LTS)
            if not image_reference:
                image_reference = {
                    "publisher": "Canonical",
                    "offer": "0001-com-ubuntu-server-jammy",
                    "sku": "22_04-lts-gen2",
                    "version": "latest",
                }

            # Create network interface
            network_client = await self._get_network_client()
            if network_client != "mock":
                nic = await self._create_network_interface(
                    network_client,
                    vm_name,
                    region,
                    vnet_name or f"{self.resource_group}-vnet",
                    subnet_name or "default",
                )
                nic_id = nic.id
            else:
                nic_id = (
                    f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}"
                    f"/providers/Microsoft.Network/networkInterfaces/{vm_name}-nic"
                )

            # Prepare tags
            all_tags = {
                "CreatedBy": "NebulaCompute",
                "ManagedBy": "NebulaCompute",
            }
            if tags:
                all_tags.update(tags)

            # OS profile
            os_profile = {
                "computer_name": vm_name,
                "admin_username": admin_username,
            }

            if ssh_public_key:
                os_profile["linux_configuration"] = {
                    "disable_password_authentication": True,
                    "ssh": {
                        "public_keys": [
                            {
                                "path": f"/home/{admin_username}/.ssh/authorized_keys",
                                "key_data": ssh_public_key,
                            }
                        ]
                    },
                }
            elif admin_password:
                os_profile["admin_password"] = admin_password
            else:
                # Generate random password if neither provided
                import secrets
                import string
                chars = string.ascii_letters + string.digits + "!@#$%^&*"
                os_profile["admin_password"] = "".join(
                    secrets.choice(chars) for _ in range(16)
                )

            # Custom data (cloud-init)
            if custom_data:
                import base64
                os_profile["custom_data"] = base64.b64encode(
                    custom_data.encode()
                ).decode()

            # VM parameters
            vm_params = {
                "location": region,
                "tags": all_tags,
                "hardware_profile": {
                    "vm_size": instance_type,
                },
                "storage_profile": {
                    "image_reference": image_reference,
                    "os_disk": {
                        "name": f"{vm_name}-osdisk",
                        "caching": "ReadWrite",
                        "create_option": "FromImage",
                        "managed_disk": {
                            "storage_account_type": "Premium_LRS",
                        },
                    },
                },
                "os_profile": os_profile,
                "network_profile": {
                    "network_interfaces": [
                        {
                            "id": nic_id,
                            "properties": {"primary": True},
                        }
                    ]
                },
            }

            # Availability zone
            if zone:
                vm_params["zones"] = [zone]

            # Spot VM configuration
            if pricing_type == InstanceType.SPOT:
                vm_params["priority"] = "Spot"
                vm_params["eviction_policy"] = "Deallocate"
                vm_params["billing_profile"] = {
                    "max_price": -1,  # Pay up to on-demand price
                }

            # Create VM
            poller = client.virtual_machines.begin_create_or_update(
                self.resource_group,
                vm_name,
                vm_params,
            )

            # Wait for completion
            vm = poller.result()
            logger.info(f"Created Azure VM: {vm_name}")

            return await self._parse_instance(vm)

        except Exception as e:
            logger.error(f"Error launching Azure VM: {e}")
            raise RuntimeError(f"Failed to launch Azure VM: {e}")

    async def _create_network_interface(
        self,
        network_client,
        vm_name: str,
        region: str,
        vnet_name: str,
        subnet_name: str,
    ):
        """Create network interface for VM."""
        # Get subnet
        try:
            subnet = network_client.subnets.get(
                self.resource_group, vnet_name, subnet_name
            )
        except Exception:
            # Create VNet and subnet if not exists
            await self._ensure_network(network_client, vnet_name, subnet_name, region)
            subnet = network_client.subnets.get(
                self.resource_group, vnet_name, subnet_name
            )

        # Create public IP
        public_ip_params = {
            "location": region,
            "sku": {"name": "Standard"},
            "public_ip_allocation_method": "Static",
            "public_ip_address_version": "IPv4",
        }

        poller = network_client.public_ip_addresses.begin_create_or_update(
            self.resource_group,
            f"{vm_name}-pip",
            public_ip_params,
        )
        public_ip = poller.result()

        # Create NIC
        nic_params = {
            "location": region,
            "ip_configurations": [
                {
                    "name": "ipconfig1",
                    "subnet": {"id": subnet.id},
                    "public_ip_address": {"id": public_ip.id},
                }
            ],
        }

        poller = network_client.network_interfaces.begin_create_or_update(
            self.resource_group,
            f"{vm_name}-nic",
            nic_params,
        )

        return poller.result()

    async def _ensure_network(
        self,
        network_client,
        vnet_name: str,
        subnet_name: str,
        region: str,
    ):
        """Ensure VNet and subnet exist."""
        # Create VNet
        vnet_params = {
            "location": region,
            "address_space": {"address_prefixes": ["10.0.0.0/16"]},
        }

        poller = network_client.virtual_networks.begin_create_or_update(
            self.resource_group, vnet_name, vnet_params
        )
        poller.result()

        # Create subnet
        subnet_params = {"address_prefix": "10.0.0.0/24"}

        poller = network_client.subnets.begin_create_or_update(
            self.resource_group, vnet_name, subnet_name, subnet_params
        )
        poller.result()

    async def terminate_instance(self, instance_id: str) -> bool:
        """
        Terminate Azure VM.

        إنهاء Azure VM.
        """
        client = await self._get_compute_client()

        if client == "mock":
            return True

        try:
            # Parse instance ID
            if "/" in instance_id:
                parts = instance_id.split("/")
                vm_name = parts[-1]
                rg = parts[parts.index("resourceGroups") + 1] if "resourceGroups" in parts else self.resource_group
            else:
                vm_name = instance_id
                rg = self.resource_group

            # Delete VM
            poller = client.virtual_machines.begin_delete(rg, vm_name)
            poller.result()

            # Clean up NIC and public IP
            network_client = await self._get_network_client()
            if network_client != "mock":
                try:
                    poller = network_client.network_interfaces.begin_delete(
                        rg, f"{vm_name}-nic"
                    )
                    poller.result()

                    poller = network_client.public_ip_addresses.begin_delete(
                        rg, f"{vm_name}-pip"
                    )
                    poller.result()
                except Exception:
                    pass  # Ignore cleanup errors

            logger.info(f"Terminated Azure VM: {instance_id}")
            return True

        except Exception as e:
            logger.error(f"Error terminating Azure VM {instance_id}: {e}")
            return False

    async def get_spot_price(
        self,
        instance_type: str,
        region: str,
        zone: Optional[str] = None,
    ) -> float:
        """
        Get Azure spot price.

        الحصول على سعر Azure Spot VM.

        Note: Azure spot prices vary dynamically. These are approximate values.
        """
        # Approximate on-demand hourly rates (USD)
        on_demand_prices = {
            "Standard_B1s": 0.0104,
            "Standard_B1ms": 0.0207,
            "Standard_B2s": 0.0416,
            "Standard_B2ms": 0.0832,
            "Standard_D2s_v3": 0.096,
            "Standard_D4s_v3": 0.192,
            "Standard_D8s_v3": 0.384,
            "Standard_D16s_v3": 0.768,
            "Standard_E2s_v3": 0.126,
            "Standard_E4s_v3": 0.252,
            "Standard_NC6": 0.90,
            "Standard_NC12": 1.80,
            "Standard_NC24": 3.60,
            "Standard_NC6s_v3": 3.06,
            "Standard_NC12s_v3": 6.12,
            "Standard_ND40rs_v2": 22.032,
        }

        on_demand = on_demand_prices.get(instance_type, 0.10)
        # Spot is typically 60-90% cheaper
        return on_demand * 0.2

    async def _parse_instance(self, vm) -> CloudInstance:
        """Parse Azure VM to CloudInstance."""
        specs = self.VM_SPECS.get(vm.hardware_profile.vm_size, (2, 8))

        # Determine pricing type
        pricing_type = InstanceType.ON_DEMAND
        if hasattr(vm, "priority") and vm.priority == "Spot":
            pricing_type = InstanceType.SPOT

        # Get instance view for status
        client = await self._get_compute_client()
        status = "Unknown"
        if client != "mock":
            try:
                instance_view = client.virtual_machines.instance_view(
                    self.resource_group, vm.name
                )
                for s in instance_view.statuses:
                    if s.code.startswith("PowerState/"):
                        status = s.code.replace("PowerState/", "")
                        break
            except Exception:
                pass

        # Get network IPs
        public_ip = None
        private_ip = None
        network_client = await self._get_network_client()
        if network_client != "mock" and vm.network_profile and vm.network_profile.network_interfaces:
            try:
                nic_id = vm.network_profile.network_interfaces[0].id
                nic_name = nic_id.split("/")[-1]
                nic = network_client.network_interfaces.get(self.resource_group, nic_name)

                if nic.ip_configurations:
                    ip_config = nic.ip_configurations[0]
                    private_ip = ip_config.private_ip_address

                    if ip_config.public_ip_address:
                        pip_id = ip_config.public_ip_address.id
                        pip_name = pip_id.split("/")[-1]
                        pip = network_client.public_ip_addresses.get(
                            self.resource_group, pip_name
                        )
                        public_ip = pip.ip_address
            except Exception:
                pass

        # Check for GPU
        gpu_count = 0
        gpu_type = None
        vm_size = vm.hardware_profile.vm_size
        if "NC" in vm_size or "ND" in vm_size or "NV" in vm_size:
            # Parse GPU info from VM size
            if "NC6s_v3" in vm_size:
                gpu_count, gpu_type = 1, "V100"
            elif "NC12s_v3" in vm_size:
                gpu_count, gpu_type = 2, "V100"
            elif "ND40rs_v2" in vm_size:
                gpu_count, gpu_type = 8, "V100"
            elif "NC6" in vm_size:
                gpu_count, gpu_type = 1, "K80"
            elif "NC12" in vm_size:
                gpu_count, gpu_type = 2, "K80"
            elif "NC24" in vm_size:
                gpu_count, gpu_type = 4, "K80"

        return CloudInstance(
            instance_id=vm.id,
            provider="azure",
            region=vm.location,
            zone=vm.zones[0] if vm.zones else "",
            instance_type=vm.hardware_profile.vm_size,
            pricing_type=pricing_type,
            vcpus=specs[0],
            memory_gb=specs[1],
            gpu_count=gpu_count,
            gpu_type=gpu_type,
            state=status,
            public_ip=public_ip,
            private_ip=private_ip,
            tags=dict(vm.tags) if vm.tags else {},
        )
