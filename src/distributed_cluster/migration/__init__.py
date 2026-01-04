# -*- coding: utf-8 -*-
"""
Live Migration Module for NebulaCompute.

This module provides live migration capabilities for running jobs,
allowing seamless transfer between workers without interruption.

نظام النقل الحي للمهام بين Workers.

Features:
- Live job migration without interruption
- Pre-copy and post-copy migration strategies
- CRIU-based checkpoint/restore
- Network state migration
- Automatic failure recovery
"""

from .checkpoint import (
    Checkpoint,
    CheckpointManager,
    CheckpointType,
)
from .coordinator import (
    MigrationCoordinator,
    MigrationPlan,
    MigrationResult,
)
from .manager import (
    MigrationManager,
    MigrationMode,
    MigrationState,
)
from .transfer import (
    StateTransfer,
    TransferProtocol,
    TransferStatus,
)

__all__ = [
    # Manager
    "MigrationManager",
    "MigrationState",
    "MigrationMode",
    # Checkpoint
    "CheckpointManager",
    "Checkpoint",
    "CheckpointType",
    # Transfer
    "StateTransfer",
    "TransferProtocol",
    "TransferStatus",
    # Coordinator
    "MigrationCoordinator",
    "MigrationPlan",
    "MigrationResult",
]
