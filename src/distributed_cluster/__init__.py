"""
نظام الحوسبة الموزّعة - Distributed Cluster Computing System
=============================================================

A distributed computing framework implementing Master/Worker architecture.

Features:
- Resource-aware job scheduling (CPU/GPU/RAM)
- Container-based job isolation (Docker)
- Multi-master support with leader election
- Real-time monitoring and health checks
- Fault tolerance with automatic job retry

Architecture:
    Master (Control Plane)
    ├── API Server (REST + WebSocket)
    ├── Scheduler (Resource matching + Bin-packing)
    ├── State Store (Jobs, Workers, Leases)
    └── Health Monitor

    Worker Agent (on each node)
    ├── Resource Reporter (CPU/GPU/RAM)
    ├── Job Executor (Container sandbox)
    ├── Heartbeat Sender
    └── Result Uploader
"""

__version__ = "0.1.0"
__author__ = "theEnd Team"
