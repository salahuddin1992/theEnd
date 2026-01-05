# -*- coding: utf-8 -*-
"""
Federated Learning Models - نماذج التعلم الموحد
=================================================

Data models for federated learning system.

نماذج البيانات لنظام التعلم الموحد:
- نموذج العميل والحالة
- تحديثات النموذج
- جولات التدريب
- إعدادات الخصوصية
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

# =============================================================================
# Enums
# =============================================================================


class ClientStatus(str, Enum):
    """Status of a federated learning client."""
    IDLE = "idle"
    SELECTED = "selected"
    TRAINING = "training"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    DROPPED = "dropped"


class RoundStatus(str, Enum):
    """Status of a federated learning round."""
    PENDING = "pending"
    CLIENT_SELECTION = "client_selection"
    DISTRIBUTING = "distributing"
    TRAINING = "training"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class AggregationStrategy(str, Enum):
    """Aggregation strategy for model updates."""
    FEDAVG = "fedavg"  # Federated Averaging
    FEDPROX = "fedprox"  # FedProx with proximal term
    FEDYOGI = "fedyogi"  # FedYogi adaptive optimizer
    FEDADAM = "fedadam"  # FedAdam adaptive optimizer
    SCAFFOLD = "scaffold"  # SCAFFOLD variance reduction
    FEDOPT = "fedopt"  # Federated Optimization
    WEIGHTED_AVG = "weighted_avg"  # Weighted average by samples
    MEDIAN = "median"  # Coordinate-wise median (Byzantine-robust)
    TRIMMED_MEAN = "trimmed_mean"  # Trimmed mean (Byzantine-robust)
    KRUM = "krum"  # Krum (Byzantine-robust)


class SelectionStrategy(str, Enum):
    """Client selection strategy."""
    RANDOM = "random"
    ROUND_ROBIN = "round_robin"
    RESOURCE_AWARE = "resource_aware"
    DATA_QUALITY = "data_quality"
    CONTRIBUTION_BASED = "contribution_based"
    AVAILABILITY = "availability"
    OORT = "oort"  # Guided participant selection


class PrivacyMechanism(str, Enum):
    """Privacy mechanism for federated learning."""
    NONE = "none"
    DIFFERENTIAL_PRIVACY = "differential_privacy"
    SECURE_AGGREGATION = "secure_aggregation"
    HOMOMORPHIC_ENCRYPTION = "homomorphic_encryption"
    LOCAL_DP = "local_dp"


class CompressionMethod(str, Enum):
    """Model compression method for communication efficiency."""
    NONE = "none"
    QUANTIZATION = "quantization"
    SPARSIFICATION = "sparsification"
    TOP_K = "top_k"
    RANDOM_K = "random_k"
    SKETCHING = "sketching"
    GRADIENT_COMPRESSION = "gradient_compression"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ModelWeights:
    """
    Model weights container for federated learning.

    حاوية أوزان النموذج للتعلم الموحد.
    """
    weights: Dict[str, np.ndarray]
    version: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    checksum: str = ""

    def __post_init__(self):
        if not self.checksum:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """Compute checksum of weights for verification."""
        data = b""
        for key in sorted(self.weights.keys()):
            data += self.weights[key].tobytes()
        return hashlib.sha256(data).hexdigest()[:16]

    def verify_checksum(self) -> bool:
        """Verify weights integrity."""
        return self.checksum == self._compute_checksum()

    @property
    def num_parameters(self) -> int:
        """Total number of parameters."""
        return sum(w.size for w in self.weights.values())

    @property
    def size_bytes(self) -> int:
        """Size in bytes."""
        return sum(w.nbytes for w in self.weights.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "checksum": self.checksum,
            "num_parameters": self.num_parameters,
            "size_bytes": self.size_bytes,
            "layer_shapes": {k: list(v.shape) for k, v in self.weights.items()},
        }


@dataclass
class ClientConfig:
    """
    Configuration for a federated learning client.

    إعدادات عميل التعلم الموحد.
    """
    client_id: str
    local_epochs: int = 1
    local_batch_size: int = 32
    learning_rate: float = 0.01
    momentum: float = 0.0
    weight_decay: float = 0.0
    optimizer: str = "sgd"
    max_samples: Optional[int] = None
    shuffle_data: bool = True
    seed: Optional[int] = None
    extra_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "local_epochs": self.local_epochs,
            "local_batch_size": self.local_batch_size,
            "learning_rate": self.learning_rate,
            "momentum": self.momentum,
            "weight_decay": self.weight_decay,
            "optimizer": self.optimizer,
            "max_samples": self.max_samples,
            "shuffle_data": self.shuffle_data,
            "seed": self.seed,
            "extra_config": self.extra_config,
        }


@dataclass
class ClientInfo:
    """
    Information about a federated learning client.

    معلومات عميل التعلم الموحد.
    """
    client_id: str
    worker_id: str
    status: ClientStatus = ClientStatus.IDLE
    dataset_size: int = 0
    data_distribution: Optional[Dict[str, float]] = None  # Label distribution
    available_resources: Optional[Dict[str, float]] = None
    last_participation_round: int = -1
    total_rounds_participated: int = 0
    average_training_time: float = 0.0
    reliability_score: float = 1.0  # Track client reliability
    contribution_score: float = 0.0  # Track contribution quality
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        """Check if client is available for selection."""
        if self.status != ClientStatus.IDLE:
            return False
        if self.last_heartbeat is None:
            return False
        delta = datetime.now(timezone.utc) - self.last_heartbeat
        return delta.total_seconds() < 60  # 60s timeout

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "worker_id": self.worker_id,
            "status": self.status.value,
            "dataset_size": self.dataset_size,
            "data_distribution": self.data_distribution,
            "available_resources": self.available_resources,
            "last_participation_round": self.last_participation_round,
            "total_rounds_participated": self.total_rounds_participated,
            "average_training_time": self.average_training_time,
            "reliability_score": self.reliability_score,
            "contribution_score": self.contribution_score,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "is_available": self.is_available,
            "metadata": self.metadata,
        }


@dataclass
class ClientUpdate:
    """
    Model update from a federated learning client.

    تحديث النموذج من عميل التعلم الموحد.
    """
    client_id: str
    round_number: int
    model_weights: ModelWeights
    num_samples: int
    training_loss: float
    validation_loss: Optional[float] = None
    validation_accuracy: Optional[float] = None
    training_time: float = 0.0
    metrics: Dict[str, float] = field(default_factory=dict)
    gradients: Optional[Dict[str, np.ndarray]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "round_number": self.round_number,
            "model_weights": self.model_weights.to_dict(),
            "num_samples": self.num_samples,
            "training_loss": self.training_loss,
            "validation_loss": self.validation_loss,
            "validation_accuracy": self.validation_accuracy,
            "training_time": self.training_time,
            "metrics": self.metrics,
            "has_gradients": self.gradients is not None,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class RoundConfig:
    """
    Configuration for a federated learning round.

    إعدادات جولة التعلم الموحد.
    """
    round_number: int
    min_clients: int = 2
    max_clients: int = 100
    client_fraction: float = 0.1  # Fraction of clients to select
    local_epochs: int = 1
    local_batch_size: int = 32
    learning_rate: float = 0.01
    aggregation_strategy: AggregationStrategy = AggregationStrategy.FEDAVG
    selection_strategy: SelectionStrategy = SelectionStrategy.RANDOM
    timeout_seconds: int = 300  # 5 minutes
    min_update_ratio: float = 0.5  # Min ratio of updates to proceed
    extra_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_number": self.round_number,
            "min_clients": self.min_clients,
            "max_clients": self.max_clients,
            "client_fraction": self.client_fraction,
            "local_epochs": self.local_epochs,
            "local_batch_size": self.local_batch_size,
            "learning_rate": self.learning_rate,
            "aggregation_strategy": self.aggregation_strategy.value,
            "selection_strategy": self.selection_strategy.value,
            "timeout_seconds": self.timeout_seconds,
            "min_update_ratio": self.min_update_ratio,
            "extra_config": self.extra_config,
        }


@dataclass
class RoundResult:
    """
    Result of a federated learning round.

    نتيجة جولة التعلم الموحد.
    """
    round_number: int
    status: RoundStatus
    global_model: Optional[ModelWeights] = None
    selected_clients: List[str] = field(default_factory=list)
    participating_clients: List[str] = field(default_factory=list)
    dropped_clients: List[str] = field(default_factory=list)
    total_samples: int = 0
    aggregated_loss: float = 0.0
    aggregated_accuracy: Optional[float] = None
    round_duration: float = 0.0
    communication_time: float = 0.0
    aggregation_time: float = 0.0
    metrics: Dict[str, float] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    @property
    def participation_rate(self) -> float:
        """Calculate participation rate."""
        if not self.selected_clients:
            return 0.0
        return len(self.participating_clients) / len(self.selected_clients)

    @property
    def success_rate(self) -> float:
        """Calculate success rate (non-dropped clients)."""
        if not self.selected_clients:
            return 0.0
        return 1 - (len(self.dropped_clients) / len(self.selected_clients))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_number": self.round_number,
            "status": self.status.value,
            "global_model": self.global_model.to_dict() if self.global_model else None,
            "selected_clients": self.selected_clients,
            "participating_clients": self.participating_clients,
            "dropped_clients": self.dropped_clients,
            "total_samples": self.total_samples,
            "aggregated_loss": self.aggregated_loss,
            "aggregated_accuracy": self.aggregated_accuracy,
            "round_duration": self.round_duration,
            "communication_time": self.communication_time,
            "aggregation_time": self.aggregation_time,
            "participation_rate": self.participation_rate,
            "success_rate": self.success_rate,
            "metrics": self.metrics,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }


@dataclass
class PrivacyConfig:
    """
    Privacy configuration for federated learning.

    إعدادات الخصوصية للتعلم الموحد.
    """
    mechanism: PrivacyMechanism = PrivacyMechanism.NONE
    epsilon: float = 1.0  # DP privacy budget
    delta: float = 1e-5  # DP failure probability
    noise_multiplier: float = 1.0  # DP noise multiplier
    clip_norm: float = 1.0  # Gradient clipping norm
    secure_aggregation_threshold: int = 3  # Min clients for secure agg
    min_separation: int = 2  # Min client separation for secure agg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mechanism": self.mechanism.value,
            "epsilon": self.epsilon,
            "delta": self.delta,
            "noise_multiplier": self.noise_multiplier,
            "clip_norm": self.clip_norm,
            "secure_aggregation_threshold": self.secure_aggregation_threshold,
            "min_separation": self.min_separation,
        }


@dataclass
class CompressionConfig:
    """
    Compression configuration for communication efficiency.

    إعدادات الضغط لكفاءة الاتصال.
    """
    method: CompressionMethod = CompressionMethod.NONE
    compression_ratio: float = 0.1  # Keep top 10%
    quantization_bits: int = 8  # For quantization
    error_feedback: bool = True  # Use error feedback
    seed: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method.value,
            "compression_ratio": self.compression_ratio,
            "quantization_bits": self.quantization_bits,
            "error_feedback": self.error_feedback,
            "seed": self.seed,
        }


@dataclass
class FederatedConfig:
    """
    Complete configuration for federated learning.

    الإعدادات الكاملة للتعلم الموحد.
    """
    job_id: str
    model_name: str
    total_rounds: int
    aggregation_strategy: AggregationStrategy = AggregationStrategy.FEDAVG
    selection_strategy: SelectionStrategy = SelectionStrategy.RANDOM
    min_clients: int = 2
    max_clients: int = 100
    client_fraction: float = 0.1
    local_epochs: int = 1
    local_batch_size: int = 32
    global_learning_rate: float = 1.0  # Server-side learning rate
    client_learning_rate: float = 0.01  # Client-side learning rate
    privacy_config: PrivacyConfig = field(default_factory=PrivacyConfig)
    compression_config: CompressionConfig = field(default_factory=CompressionConfig)
    round_timeout: int = 300  # seconds
    min_update_ratio: float = 0.5
    evaluate_every: int = 1  # Evaluate every N rounds
    checkpoint_every: int = 5  # Checkpoint every N rounds
    early_stopping_rounds: int = 0  # 0 = disabled
    early_stopping_threshold: float = 0.001
    seed: int = 42
    extra_config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.job_id:
            self.job_id = f"fl-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "model_name": self.model_name,
            "total_rounds": self.total_rounds,
            "aggregation_strategy": self.aggregation_strategy.value,
            "selection_strategy": self.selection_strategy.value,
            "min_clients": self.min_clients,
            "max_clients": self.max_clients,
            "client_fraction": self.client_fraction,
            "local_epochs": self.local_epochs,
            "local_batch_size": self.local_batch_size,
            "global_learning_rate": self.global_learning_rate,
            "client_learning_rate": self.client_learning_rate,
            "privacy_config": self.privacy_config.to_dict(),
            "compression_config": self.compression_config.to_dict(),
            "round_timeout": self.round_timeout,
            "min_update_ratio": self.min_update_ratio,
            "evaluate_every": self.evaluate_every,
            "checkpoint_every": self.checkpoint_every,
            "early_stopping_rounds": self.early_stopping_rounds,
            "early_stopping_threshold": self.early_stopping_threshold,
            "seed": self.seed,
            "extra_config": self.extra_config,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FederatedConfig:
        """Create config from dictionary."""
        privacy_config = PrivacyConfig(**data.get("privacy_config", {}))
        compression_config = CompressionConfig(**data.get("compression_config", {}))

        return cls(
            job_id=data.get("job_id", ""),
            model_name=data["model_name"],
            total_rounds=data["total_rounds"],
            aggregation_strategy=AggregationStrategy(
                data.get("aggregation_strategy", "fedavg")
            ),
            selection_strategy=SelectionStrategy(
                data.get("selection_strategy", "random")
            ),
            min_clients=data.get("min_clients", 2),
            max_clients=data.get("max_clients", 100),
            client_fraction=data.get("client_fraction", 0.1),
            local_epochs=data.get("local_epochs", 1),
            local_batch_size=data.get("local_batch_size", 32),
            global_learning_rate=data.get("global_learning_rate", 1.0),
            client_learning_rate=data.get("client_learning_rate", 0.01),
            privacy_config=privacy_config,
            compression_config=compression_config,
            round_timeout=data.get("round_timeout", 300),
            min_update_ratio=data.get("min_update_ratio", 0.5),
            evaluate_every=data.get("evaluate_every", 1),
            checkpoint_every=data.get("checkpoint_every", 5),
            early_stopping_rounds=data.get("early_stopping_rounds", 0),
            early_stopping_threshold=data.get("early_stopping_threshold", 0.001),
            seed=data.get("seed", 42),
            extra_config=data.get("extra_config", {}),
        )


@dataclass
class FederatedMetrics:
    """
    Metrics for federated learning training.

    مقاييس التدريب للتعلم الموحد.
    """
    job_id: str
    current_round: int = 0
    total_rounds: int = 0
    global_loss: float = 0.0
    global_accuracy: Optional[float] = None
    best_loss: float = float("inf")
    best_accuracy: float = 0.0
    best_round: int = 0
    total_clients: int = 0
    active_clients: int = 0
    total_samples_trained: int = 0
    total_communication_bytes: int = 0
    average_round_time: float = 0.0
    average_client_training_time: float = 0.0
    loss_history: List[float] = field(default_factory=list)
    accuracy_history: List[float] = field(default_factory=list)
    participation_history: List[float] = field(default_factory=list)
    started_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    @property
    def rounds_completed(self) -> int:
        return self.current_round

    @property
    def progress_percent(self) -> float:
        if self.total_rounds == 0:
            return 0.0
        return (self.current_round / self.total_rounds) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "global_loss": self.global_loss,
            "global_accuracy": self.global_accuracy,
            "best_loss": self.best_loss if self.best_loss != float("inf") else None,
            "best_accuracy": self.best_accuracy,
            "best_round": self.best_round,
            "total_clients": self.total_clients,
            "active_clients": self.active_clients,
            "total_samples_trained": self.total_samples_trained,
            "total_communication_bytes": self.total_communication_bytes,
            "average_round_time": self.average_round_time,
            "average_client_training_time": self.average_client_training_time,
            "rounds_completed": self.rounds_completed,
            "progress_percent": self.progress_percent,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }
