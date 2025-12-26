"""
Desktop API Client - عميل API سطح المكتب
=========================================

API client for communicating with master server.

Author: NebulaCompute Team
License: MIT
"""

from distributed_cluster.desktop.api.client import APIClient, ClusterStats

__all__ = [
    "APIClient",
    "ClusterStats",
]
