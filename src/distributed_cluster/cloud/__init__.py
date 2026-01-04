# -*- coding: utf-8 -*-
"""
Cloud Integration Module for NebulaCompute.

Provides integration with major cloud providers for:
- Spot/Preemptible instance management
- Auto-scaling
- Cloud resource provisioning
- Cost optimization

تكامل مع مزودي الخدمات السحابية.
"""

from .providers import (
    AWSProvider,
    AzureProvider,
    CloudProvider,
    GCPProvider,
)
from .spot_handler import (
    SpotInstanceHandler,
    SpotInstanceState,
    SpotNotification,
    SpotProvider,
)

__all__ = [
    # Spot Handler
    "SpotInstanceHandler",
    "SpotNotification",
    "SpotProvider",
    "SpotInstanceState",
    # Providers
    "CloudProvider",
    "AWSProvider",
    "GCPProvider",
    "AzureProvider",
]
