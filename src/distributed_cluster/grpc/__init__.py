"""
gRPC Module - خدمات gRPC
========================

تنفيذ بروتوكول gRPC للاتصال بين Master و Workers.
"""

from distributed_cluster.grpc.client_service import ClientServicer
from distributed_cluster.grpc.master_service import MasterServicer
from distributed_cluster.grpc.server import GRPCServer, GRPCServerConfig

__all__ = [
    "GRPCServer",
    "GRPCServerConfig",
    "MasterServicer",
    "ClientServicer",
]
