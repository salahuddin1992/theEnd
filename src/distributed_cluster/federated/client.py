# -*- coding: utf-8 -*-
"""
Federated Learning Client - عميل التعلم الموحد
==============================================

Client-side implementation for federated learning.

تنفيذ جانب العميل للتعلم الموحد:
- التدريب المحلي
- تحديث النموذج
- الاتصال بالخادم
- الخصوصية المحلية
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import numpy as np

from distributed_cluster.federated.models import (
    ClientConfig,
    ClientInfo,
    ClientStatus,
    ClientUpdate,
    CompressionConfig,
    ModelWeights,
    PrivacyConfig,
    PrivacyMechanism,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Data Loader Interface
# =============================================================================


class DataLoader(ABC):
    """
    Abstract data loader for federated learning.

    واجهة محمل البيانات للتعلم الموحد.
    """

    @property
    @abstractmethod
    def num_samples(self) -> int:
        """Total number of samples."""
        pass

    @abstractmethod
    def __iter__(self) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        """Iterate over batches of (data, labels)."""
        pass

    @abstractmethod
    def __len__(self) -> int:
        """Number of batches."""
        pass


class InMemoryDataLoader(DataLoader):
    """
    Simple in-memory data loader.

    محمل بيانات بسيط في الذاكرة.
    """

    def __init__(
        self,
        data: np.ndarray,
        labels: np.ndarray,
        batch_size: int = 32,
        shuffle: bool = True,
        seed: Optional[int] = None,
    ):
        self.data = data
        self.labels = labels
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.rng = np.random.RandomState(seed)

    @property
    def num_samples(self) -> int:
        return len(self.data)

    def __len__(self) -> int:
        return (len(self.data) + self.batch_size - 1) // self.batch_size

    def __iter__(self) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        indices = np.arange(len(self.data))
        if self.shuffle:
            self.rng.shuffle(indices)

        for i in range(0, len(indices), self.batch_size):
            batch_indices = indices[i:i + self.batch_size]
            yield self.data[batch_indices], self.labels[batch_indices]


# =============================================================================
# Model Interface
# =============================================================================


class LocalModel(ABC):
    """
    Abstract local model for federated learning.

    واجهة النموذج المحلي للتعلم الموحد.
    """

    @abstractmethod
    def get_weights(self) -> Dict[str, np.ndarray]:
        """Get model weights as dictionary."""
        pass

    @abstractmethod
    def set_weights(self, weights: Dict[str, np.ndarray]) -> None:
        """Set model weights from dictionary."""
        pass

    @abstractmethod
    def train_step(
        self,
        data: np.ndarray,
        labels: np.ndarray,
        learning_rate: float,
    ) -> float:
        """
        Perform a training step.

        Returns:
            Training loss
        """
        pass

    @abstractmethod
    def evaluate(
        self,
        data: np.ndarray,
        labels: np.ndarray,
    ) -> Tuple[float, float]:
        """
        Evaluate model.

        Returns:
            (loss, accuracy)
        """
        pass


class SimpleNeuralNetwork(LocalModel):
    """
    Simple neural network for demonstration.

    شبكة عصبية بسيطة للتوضيح.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        output_size: int,
        seed: Optional[int] = None,
    ):
        rng = np.random.RandomState(seed)

        # Xavier initialization
        self.weights = {
            "W1": rng.randn(input_size, hidden_size) * np.sqrt(2.0 / input_size),
            "b1": np.zeros(hidden_size),
            "W2": rng.randn(hidden_size, output_size) * np.sqrt(2.0 / hidden_size),
            "b2": np.zeros(output_size),
        }

    def get_weights(self) -> Dict[str, np.ndarray]:
        return {k: v.copy() for k, v in self.weights.items()}

    def set_weights(self, weights: Dict[str, np.ndarray]) -> None:
        for k, v in weights.items():
            if k in self.weights:
                self.weights[k] = v.copy()

    def _forward(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Forward pass."""
        # Hidden layer with ReLU
        z1 = x @ self.weights["W1"] + self.weights["b1"]
        a1 = np.maximum(0, z1)  # ReLU

        # Output layer with softmax
        z2 = a1 @ self.weights["W2"] + self.weights["b2"]
        exp_z2 = np.exp(z2 - np.max(z2, axis=1, keepdims=True))
        a2 = exp_z2 / np.sum(exp_z2, axis=1, keepdims=True)

        return a1, a2

    def _backward(
        self,
        x: np.ndarray,
        a1: np.ndarray,
        a2: np.ndarray,
        y: np.ndarray,
    ) -> Dict[str, np.ndarray]:
        """Backward pass."""
        batch_size = x.shape[0]

        # Output layer gradient
        dz2 = a2 - y
        dW2 = (a1.T @ dz2) / batch_size
        db2 = np.mean(dz2, axis=0)

        # Hidden layer gradient
        da1 = dz2 @ self.weights["W2"].T
        dz1 = da1 * (a1 > 0)  # ReLU derivative
        dW1 = (x.T @ dz1) / batch_size
        db1 = np.mean(dz1, axis=0)

        return {"W1": dW1, "b1": db1, "W2": dW2, "b2": db2}

    def train_step(
        self,
        data: np.ndarray,
        labels: np.ndarray,
        learning_rate: float,
    ) -> float:
        """Perform training step with SGD."""
        # One-hot encode labels if needed
        if labels.ndim == 1:
            num_classes = self.weights["W2"].shape[1]
            y_onehot = np.zeros((len(labels), num_classes))
            y_onehot[np.arange(len(labels)), labels.astype(int)] = 1
        else:
            y_onehot = labels

        # Forward pass
        a1, a2 = self._forward(data)

        # Compute loss (cross-entropy)
        epsilon = 1e-8
        loss = -np.mean(np.sum(y_onehot * np.log(a2 + epsilon), axis=1))

        # Backward pass
        gradients = self._backward(data, a1, a2, y_onehot)

        # Update weights
        for k in self.weights:
            self.weights[k] -= learning_rate * gradients[k]

        return float(loss)

    def evaluate(
        self,
        data: np.ndarray,
        labels: np.ndarray,
    ) -> Tuple[float, float]:
        """Evaluate model."""
        # One-hot encode labels if needed
        if labels.ndim == 1:
            num_classes = self.weights["W2"].shape[1]
            y_onehot = np.zeros((len(labels), num_classes))
            y_onehot[np.arange(len(labels)), labels.astype(int)] = 1
            label_indices = labels.astype(int)
        else:
            y_onehot = labels
            label_indices = np.argmax(labels, axis=1)

        # Forward pass
        _, a2 = self._forward(data)

        # Compute loss
        epsilon = 1e-8
        loss = -np.mean(np.sum(y_onehot * np.log(a2 + epsilon), axis=1))

        # Compute accuracy
        predictions = np.argmax(a2, axis=1)
        accuracy = np.mean(predictions == label_indices)

        return float(loss), float(accuracy)


# =============================================================================
# Federated Learning Client
# =============================================================================


@dataclass
class TrainingResult:
    """Result of local training."""
    loss: float
    num_samples: int
    training_time: float
    metrics: Dict[str, float] = field(default_factory=dict)


class FederatedClient:
    """
    Federated Learning Client.

    عميل التعلم الموحد.

    Features:
    - Local model training
    - Privacy-preserving updates
    - Communication with server
    - Model compression
    """

    def __init__(
        self,
        client_id: str,
        model: LocalModel,
        data_loader: DataLoader,
        config: Optional[ClientConfig] = None,
        privacy_config: Optional[PrivacyConfig] = None,
        compression_config: Optional[CompressionConfig] = None,
        validation_loader: Optional[DataLoader] = None,
    ):
        """
        Initialize federated learning client.

        Args:
            client_id: Unique client identifier
            model: Local model instance
            data_loader: Training data loader
            config: Client configuration
            privacy_config: Privacy configuration
            compression_config: Compression configuration
            validation_loader: Optional validation data loader
        """
        self.client_id = client_id
        self.model = model
        self.data_loader = data_loader
        self.validation_loader = validation_loader

        self.config = config or ClientConfig(client_id=client_id)
        self.privacy_config = privacy_config or PrivacyConfig()
        self.compression_config = compression_config

        # Client state
        self._status = ClientStatus.IDLE
        self._current_round = 0
        self._total_samples_trained = 0
        self._training_history: List[TrainingResult] = []

        # Callbacks
        self._on_round_complete: Optional[Callable] = None

        logger.info(f"Initialized federated client: {client_id}")

    @property
    def status(self) -> ClientStatus:
        return self._status

    @property
    def dataset_size(self) -> int:
        return self.data_loader.num_samples

    def get_info(self) -> ClientInfo:
        """Get client information."""
        return ClientInfo(
            client_id=self.client_id,
            worker_id=self.client_id,  # Could be different in distributed setting
            status=self._status,
            dataset_size=self.dataset_size,
            last_participation_round=self._current_round,
            total_rounds_participated=len(self._training_history),
            last_heartbeat=datetime.utcnow(),
        )

    async def receive_model(self, weights: ModelWeights) -> None:
        """
        Receive global model from server.

        استلام النموذج العالمي من الخادم.
        """
        self._status = ClientStatus.SELECTED
        self.model.set_weights(weights.weights)
        logger.debug(f"Client {self.client_id} received model v{weights.version}")

    async def train_local(
        self,
        round_number: int,
        epochs: Optional[int] = None,
        learning_rate: Optional[float] = None,
    ) -> TrainingResult:
        """
        Perform local training.

        تنفيذ التدريب المحلي.

        Args:
            round_number: Current federated round number
            epochs: Number of local epochs (overrides config)
            learning_rate: Learning rate (overrides config)

        Returns:
            Training result with loss and metrics
        """
        self._status = ClientStatus.TRAINING
        self._current_round = round_number

        epochs = epochs or self.config.local_epochs
        lr = learning_rate or self.config.learning_rate

        start_time = time.time()
        total_loss = 0.0
        num_samples = 0
        num_batches = 0

        logger.debug(
            f"Client {self.client_id} starting local training: "
            f"epochs={epochs}, lr={lr}"
        )

        for epoch in range(epochs):
            epoch_loss = 0.0
            epoch_samples = 0

            for batch_data, batch_labels in self.data_loader:
                batch_loss = self.model.train_step(batch_data, batch_labels, lr)
                epoch_loss += batch_loss * len(batch_data)
                epoch_samples += len(batch_data)
                num_batches += 1

            total_loss += epoch_loss
            num_samples += epoch_samples

        # Average loss
        avg_loss = total_loss / num_samples if num_samples > 0 else 0.0

        training_time = time.time() - start_time
        self._total_samples_trained += num_samples

        result = TrainingResult(
            loss=avg_loss,
            num_samples=num_samples,
            training_time=training_time,
            metrics={
                "epochs": epochs,
                "batches": num_batches,
            },
        )

        # Evaluate on validation set if available
        if self.validation_loader:
            val_data = []
            val_labels = []
            for batch_data, batch_labels in self.validation_loader:
                val_data.append(batch_data)
                val_labels.append(batch_labels)

            if val_data:
                val_data = np.concatenate(val_data)
                val_labels = np.concatenate(val_labels)
                val_loss, val_acc = self.model.evaluate(val_data, val_labels)
                result.metrics["val_loss"] = val_loss
                result.metrics["val_accuracy"] = val_acc

        self._training_history.append(result)
        self._status = ClientStatus.COMPLETED

        logger.debug(
            f"Client {self.client_id} completed training: "
            f"loss={avg_loss:.4f}, samples={num_samples}"
        )

        return result

    def _apply_local_dp(
        self,
        weights: Dict[str, np.ndarray],
    ) -> Dict[str, np.ndarray]:
        """Apply local differential privacy to weights."""
        if self.privacy_config.mechanism != PrivacyMechanism.LOCAL_DP:
            return weights

        noisy_weights = {}
        for key, value in weights.items():
            # Clip gradients
            norm = np.linalg.norm(value)
            if norm > self.privacy_config.clip_norm:
                value = value * self.privacy_config.clip_norm / norm

            # Add Gaussian noise
            noise_scale = (
                self.privacy_config.clip_norm
                * self.privacy_config.noise_multiplier
            )
            noise = np.random.normal(0, noise_scale, value.shape)
            noisy_weights[key] = value + noise

        return noisy_weights

    async def get_update(self) -> ClientUpdate:
        """
        Get model update to send to server.

        الحصول على تحديث النموذج لإرساله للخادم.

        Returns:
            Client update with model weights and metrics
        """
        self._status = ClientStatus.UPLOADING

        # Get current weights
        weights = self.model.get_weights()

        # Apply local differential privacy if configured
        if self.privacy_config.mechanism == PrivacyMechanism.LOCAL_DP:
            weights = self._apply_local_dp(weights)

        # Get last training result
        last_result = self._training_history[-1] if self._training_history else None

        update = ClientUpdate(
            client_id=self.client_id,
            round_number=self._current_round,
            model_weights=ModelWeights(weights=weights),
            num_samples=last_result.num_samples if last_result else 0,
            training_loss=last_result.loss if last_result else 0.0,
            validation_loss=last_result.metrics.get("val_loss"),
            validation_accuracy=last_result.metrics.get("val_accuracy"),
            training_time=last_result.training_time if last_result else 0.0,
            metrics=last_result.metrics if last_result else {},
        )

        self._status = ClientStatus.IDLE
        return update

    async def participate_in_round(
        self,
        round_number: int,
        global_weights: ModelWeights,
        epochs: Optional[int] = None,
        learning_rate: Optional[float] = None,
    ) -> ClientUpdate:
        """
        Complete participation in a federated round.

        إكمال المشاركة في جولة موحدة.

        Args:
            round_number: Current round number
            global_weights: Global model weights from server
            epochs: Number of local epochs
            learning_rate: Learning rate

        Returns:
            Client update with trained model
        """
        # Receive model
        await self.receive_model(global_weights)

        # Train locally
        await self.train_local(round_number, epochs, learning_rate)

        # Get update
        update = await self.get_update()

        if self._on_round_complete:
            await self._on_round_complete(round_number, update)

        return update

    def on_round_complete(self, callback: Callable) -> None:
        """Register callback for round completion."""
        self._on_round_complete = callback

    def get_statistics(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "client_id": self.client_id,
            "status": self._status.value,
            "dataset_size": self.dataset_size,
            "current_round": self._current_round,
            "total_rounds": len(self._training_history),
            "total_samples_trained": self._total_samples_trained,
            "average_loss": (
                np.mean([r.loss for r in self._training_history])
                if self._training_history
                else None
            ),
            "average_training_time": (
                np.mean([r.training_time for r in self._training_history])
                if self._training_history
                else None
            ),
        }


# =============================================================================
# Client Manager
# =============================================================================


class ClientManager:
    """
    Manager for multiple federated learning clients.

    مدير لعملاء التعلم الموحد المتعددين.
    """

    def __init__(self):
        self._clients: Dict[str, FederatedClient] = {}
        self._lock = asyncio.Lock()

    async def register_client(self, client: FederatedClient) -> str:
        """Register a client."""
        async with self._lock:
            self._clients[client.client_id] = client
            logger.info(f"Registered client: {client.client_id}")
            return client.client_id

    async def unregister_client(self, client_id: str) -> bool:
        """Unregister a client."""
        async with self._lock:
            if client_id in self._clients:
                del self._clients[client_id]
                logger.info(f"Unregistered client: {client_id}")
                return True
            return False

    async def get_client(self, client_id: str) -> Optional[FederatedClient]:
        """Get client by ID."""
        return self._clients.get(client_id)

    async def get_available_clients(self) -> List[FederatedClient]:
        """Get all available clients."""
        return [
            c for c in self._clients.values()
            if c.status == ClientStatus.IDLE
        ]

    async def get_all_clients(self) -> List[FederatedClient]:
        """Get all registered clients."""
        return list(self._clients.values())

    async def get_client_infos(self) -> List[ClientInfo]:
        """Get info for all clients."""
        return [c.get_info() for c in self._clients.values()]

    @property
    def num_clients(self) -> int:
        """Total number of registered clients."""
        return len(self._clients)

    @property
    def num_available(self) -> int:
        """Number of available clients."""
        return sum(1 for c in self._clients.values() if c.status == ClientStatus.IDLE)


# =============================================================================
# Utility Functions
# =============================================================================


def create_client(
    client_id: str,
    data: np.ndarray,
    labels: np.ndarray,
    model_factory: Callable[[], LocalModel],
    batch_size: int = 32,
    **kwargs,
) -> FederatedClient:
    """
    Create a federated learning client.

    Args:
        client_id: Client identifier
        data: Training data
        labels: Training labels
        model_factory: Factory function to create model
        batch_size: Batch size for training
        **kwargs: Additional arguments for client

    Returns:
        Configured federated client
    """
    data_loader = InMemoryDataLoader(
        data=data,
        labels=labels,
        batch_size=batch_size,
    )

    model = model_factory()

    config = ClientConfig(
        client_id=client_id,
        local_batch_size=batch_size,
        **{k: v for k, v in kwargs.items() if k in ClientConfig.__dataclass_fields__},
    )

    return FederatedClient(
        client_id=client_id,
        model=model,
        data_loader=data_loader,
        config=config,
    )


def partition_data_iid(
    data: np.ndarray,
    labels: np.ndarray,
    num_clients: int,
    seed: Optional[int] = None,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Partition data IID across clients.

    توزيع البيانات بالتساوي على العملاء.

    Args:
        data: Full dataset
        labels: Full labels
        num_clients: Number of clients
        seed: Random seed

    Returns:
        List of (data, labels) tuples for each client
    """
    rng = np.random.RandomState(seed)
    indices = np.arange(len(data))
    rng.shuffle(indices)

    client_indices = np.array_split(indices, num_clients)

    return [
        (data[idx], labels[idx])
        for idx in client_indices
    ]


def partition_data_non_iid(
    data: np.ndarray,
    labels: np.ndarray,
    num_clients: int,
    num_shards_per_client: int = 2,
    seed: Optional[int] = None,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Partition data non-IID across clients.

    توزيع البيانات بشكل غير متساوٍ على العملاء.

    Each client gets a subset of classes.

    Args:
        data: Full dataset
        labels: Full labels
        num_clients: Number of clients
        num_shards_per_client: Number of label shards per client
        seed: Random seed

    Returns:
        List of (data, labels) tuples for each client
    """
    rng = np.random.RandomState(seed)

    # Sort by labels
    sorted_indices = np.argsort(labels)

    # Create shards
    num_shards = num_clients * num_shards_per_client
    shard_size = len(data) // num_shards
    shards = [
        sorted_indices[i * shard_size:(i + 1) * shard_size]
        for i in range(num_shards)
    ]

    # Assign shards to clients
    rng.shuffle(shards)

    client_data = []
    for i in range(num_clients):
        client_indices = np.concatenate(
            shards[i * num_shards_per_client:(i + 1) * num_shards_per_client]
        )
        rng.shuffle(client_indices)
        client_data.append((data[client_indices], labels[client_indices]))

    return client_data
