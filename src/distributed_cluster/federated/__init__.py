# -*- coding: utf-8 -*-
"""
Federated Learning Module - وحدة التعلم الموحد
==============================================

Comprehensive federated learning system for distributed training
across multiple clients while preserving data privacy.

نظام تعلم موحد شامل للتدريب الموزع عبر عملاء متعددين
مع الحفاظ على خصوصية البيانات.

Features:
- Multiple aggregation strategies (FedAvg, FedProx, FedYogi, etc.)
- Client selection strategies (Random, OORT, Resource-aware)
- Privacy mechanisms (Differential Privacy, Secure Aggregation)
- Model compression for communication efficiency
- Byzantine-robust aggregation
- Checkpointing and fault tolerance

Example Usage:
    from distributed_cluster.federated import (
        FederatedCoordinator,
        FederatedConfig,
        FederatedClient,
        AggregationStrategy,
    )

    # Create configuration
    config = FederatedConfig(
        job_id="my-fl-job",
        model_name="my-model",
        total_rounds=100,
        aggregation_strategy=AggregationStrategy.FEDAVG,
        min_clients=5,
        client_fraction=0.2,
    )

    # Create coordinator
    coordinator = FederatedCoordinator(config, initial_weights)

    # Register clients
    for client in clients:
        await coordinator.register_client(client)

    # Train
    metrics = await coordinator.train()

Author: Distributed Cluster Team
License: MIT
"""

# =============================================================================
# Models
# =============================================================================
# =============================================================================
# Aggregators
# =============================================================================
from distributed_cluster.federated.aggregator import (
    Aggregator,
    FedAdamAggregator,
    FedAvgAggregator,
    FedProxAggregator,
    FedYogiAggregator,
    KrumAggregator,
    MedianAggregator,
    ScaffoldAggregator,
    TrimmedMeanAggregator,
    create_aggregator,
)

# =============================================================================
# Client
# =============================================================================
from distributed_cluster.federated.client import (
    ClientManager,
    DataLoader,
    FederatedClient,
    InMemoryDataLoader,
    LocalModel,
    SimpleNeuralNetwork,
    TrainingResult,
    create_client,
    partition_data_iid,
    partition_data_non_iid,
)

# =============================================================================
# Compression
# =============================================================================
from distributed_cluster.federated.compression import (
    CompressionResult,
    Compressor,
    GradientCompressor,
    NoCompressor,
    QuantizationCompressor,
    RandomKCompressor,
    SketchingCompressor,
    SparsificationCompressor,
    TopKCompressor,
    compress_model_weights,
    create_compressor,
)

# =============================================================================
# Coordinator
# =============================================================================
from distributed_cluster.federated.coordinator import (
    CoordinatorState,
    FederatedCoordinator,
    create_coordinator,
)
from distributed_cluster.federated.models import (
    # Enums
    AggregationStrategy,
    # Data Classes
    ClientConfig,
    ClientInfo,
    ClientStatus,
    ClientUpdate,
    CompressionConfig,
    CompressionMethod,
    FederatedConfig,
    FederatedMetrics,
    ModelWeights,
    PrivacyConfig,
    PrivacyMechanism,
    RoundConfig,
    RoundResult,
    RoundStatus,
    SelectionStrategy,
)

# =============================================================================
# Privacy
# =============================================================================
from distributed_cluster.federated.privacy import (
    CentralDPPrivacy,
    DifferentialPrivacy,
    LocalDPPrivacy,
    NonePrivacy,
    PrivacyAccountant,
    PrivacyBudget,
    PrivacyMechanismBase,
    SecureAggregation,
    SecureAggregationPrivacy,
    create_privacy_mechanism,
)

# =============================================================================
# Selection
# =============================================================================
from distributed_cluster.federated.selection import (
    AvailabilitySelector,
    ClientSelector,
    ContributionBasedSelector,
    DataQualitySelector,
    OortSelector,
    RandomSelector,
    ResourceAwareSelector,
    RoundRobinSelector,
    SelectionResult,
    create_selector,
)

# =============================================================================
# Server
# =============================================================================
from distributed_cluster.federated.server import (
    FederatedServer,
    ServerState,
    create_server,
)

# =============================================================================
# Public API
# =============================================================================
__all__ = [
    # --- Models ---
    # Enums
    "AggregationStrategy",
    "ClientStatus",
    "CompressionMethod",
    "PrivacyMechanism",
    "RoundStatus",
    "SelectionStrategy",
    # Data Classes
    "ClientConfig",
    "ClientInfo",
    "ClientUpdate",
    "CompressionConfig",
    "FederatedConfig",
    "FederatedMetrics",
    "ModelWeights",
    "PrivacyConfig",
    "RoundConfig",
    "RoundResult",
    # --- Aggregators ---
    "Aggregator",
    "FedAvgAggregator",
    "FedProxAggregator",
    "FedAdamAggregator",
    "FedYogiAggregator",
    "ScaffoldAggregator",
    "MedianAggregator",
    "TrimmedMeanAggregator",
    "KrumAggregator",
    "create_aggregator",
    # --- Client ---
    "DataLoader",
    "InMemoryDataLoader",
    "LocalModel",
    "SimpleNeuralNetwork",
    "FederatedClient",
    "ClientManager",
    "TrainingResult",
    "create_client",
    "partition_data_iid",
    "partition_data_non_iid",
    # --- Server ---
    "FederatedServer",
    "ServerState",
    "create_server",
    # --- Coordinator ---
    "FederatedCoordinator",
    "CoordinatorState",
    "create_coordinator",
    # --- Selection ---
    "ClientSelector",
    "RandomSelector",
    "RoundRobinSelector",
    "ResourceAwareSelector",
    "DataQualitySelector",
    "ContributionBasedSelector",
    "OortSelector",
    "AvailabilitySelector",
    "SelectionResult",
    "create_selector",
    # --- Privacy ---
    "PrivacyMechanismBase",
    "NonePrivacy",
    "LocalDPPrivacy",
    "CentralDPPrivacy",
    "SecureAggregationPrivacy",
    "DifferentialPrivacy",
    "SecureAggregation",
    "PrivacyAccountant",
    "PrivacyBudget",
    "create_privacy_mechanism",
    # --- Compression ---
    "Compressor",
    "NoCompressor",
    "QuantizationCompressor",
    "SparsificationCompressor",
    "TopKCompressor",
    "RandomKCompressor",
    "GradientCompressor",
    "SketchingCompressor",
    "CompressionResult",
    "create_compressor",
    "compress_model_weights",
]
