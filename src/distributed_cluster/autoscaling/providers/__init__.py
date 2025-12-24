"""
Cloud Providers - مزودو السحابة للتوسع التلقائي
================================================

Cloud Provider Integration for Auto-Scaling
-------------------------------------------

This package provides integration with various cloud providers
for provisioning and terminating worker instances.

يوفر هذا الحزمة تكامل مع مزودي السحابة المختلفين:
- AWS (Amazon Web Services)
- GCP (Google Cloud Platform)
- Azure (Microsoft Azure)
- Local (للاختبار المحلي)

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.autoscaling.providers.base import (
    CloudProvider,
    InstanceInfo,
    InstanceState,
    ProviderConfig,
    ProviderError,
    ProvisioningError,
    TerminationError,
)
from distributed_cluster.autoscaling.providers.local import LocalProvider
from distributed_cluster.autoscaling.providers.aws import AWSProvider
from distributed_cluster.autoscaling.providers.gcp import GCPProvider
from distributed_cluster.autoscaling.providers.azure import AzureProvider

__all__ = [
    # Base
    "CloudProvider",
    "ProviderConfig",
    "InstanceInfo",
    "InstanceState",
    "ProviderError",
    "ProvisioningError",
    "TerminationError",
    # Providers
    "LocalProvider",
    "AWSProvider",
    "GCPProvider",
    "AzureProvider",
]
