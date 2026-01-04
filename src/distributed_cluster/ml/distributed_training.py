# -*- coding: utf-8 -*-
"""
Distributed Training Module for NebulaCompute
==============================================

وحدة التدريب الموزع للتعلم الآلي:
- تدريب البيانات المتوازية
- تدريب النموذج المتوازي
- تجميع التدرجات
- نقاط التفتيش والاستعادة
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import pickle
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================


class TrainingStrategy(str, Enum):
    """Distributed training strategy."""
    DATA_PARALLEL = "data_parallel"
    MODEL_PARALLEL = "model_parallel"
    PIPELINE_PARALLEL = "pipeline_parallel"
    HYBRID = "hybrid"


class AggregationMethod(str, Enum):
    """Gradient aggregation method."""
    SYNC_SGD = "sync_sgd"
    ASYNC_SGD = "async_sgd"
    FEDERATED_AVG = "federated_avg"
    RING_ALLREDUCE = "ring_allreduce"


class TrainingStatus(str, Enum):
    """Training job status."""
    PENDING = "pending"
    INITIALIZING = "initializing"
    TRAINING = "training"
    CHECKPOINTING = "checkpointing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TrainingConfig:
    """Configuration for distributed training."""
    job_id: str
    model_name: str
    strategy: TrainingStrategy
    aggregation: AggregationMethod
    num_workers: int
    batch_size: int
    epochs: int
    learning_rate: float
    checkpoint_interval: int = 100  # steps
    gradient_accumulation_steps: int = 1
    mixed_precision: bool = False
    distributed_optimizer: str = "adam"
    warmup_steps: int = 0
    max_grad_norm: float = 1.0
    seed: int = 42
    extra_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "model_name": self.model_name,
            "strategy": self.strategy.value,
            "aggregation": self.aggregation.value,
            "num_workers": self.num_workers,
            "batch_size": self.batch_size,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "checkpoint_interval": self.checkpoint_interval,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "mixed_precision": self.mixed_precision,
            "distributed_optimizer": self.distributed_optimizer,
            "warmup_steps": self.warmup_steps,
            "max_grad_norm": self.max_grad_norm,
            "seed": self.seed,
            "extra_config": self.extra_config,
        }


@dataclass
class WorkerState:
    """State of a training worker."""
    worker_id: str
    rank: int
    status: TrainingStatus
    current_epoch: int = 0
    current_step: int = 0
    samples_processed: int = 0
    loss: float = 0.0
    learning_rate: float = 0.0
    throughput: float = 0.0  # samples/sec
    gpu_memory_used: int = 0
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "rank": self.rank,
            "status": self.status.value,
            "current_epoch": self.current_epoch,
            "current_step": self.current_step,
            "samples_processed": self.samples_processed,
            "loss": self.loss,
            "learning_rate": self.learning_rate,
            "throughput": self.throughput,
            "gpu_memory_used": self.gpu_memory_used,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "error_message": self.error_message,
        }


@dataclass
class TrainingMetrics:
    """Training metrics and statistics."""
    job_id: str
    total_steps: int = 0
    total_samples: int = 0
    current_epoch: int = 0
    current_step: int = 0
    train_loss: float = 0.0
    val_loss: Optional[float] = None
    learning_rate: float = 0.0
    throughput: float = 0.0
    elapsed_time: float = 0.0
    estimated_remaining: float = 0.0
    gpu_utilization: float = 0.0
    communication_overhead: float = 0.0
    checkpoints_saved: int = 0
    best_loss: float = float("inf")
    loss_history: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "total_steps": self.total_steps,
            "total_samples": self.total_samples,
            "current_epoch": self.current_epoch,
            "current_step": self.current_step,
            "train_loss": self.train_loss,
            "val_loss": self.val_loss,
            "learning_rate": self.learning_rate,
            "throughput": self.throughput,
            "elapsed_time": self.elapsed_time,
            "estimated_remaining": self.estimated_remaining,
            "gpu_utilization": self.gpu_utilization,
            "communication_overhead": self.communication_overhead,
            "checkpoints_saved": self.checkpoints_saved,
            "best_loss": self.best_loss if self.best_loss != float("inf") else None,
        }


@dataclass
class Checkpoint:
    """Training checkpoint."""
    checkpoint_id: str
    job_id: str
    epoch: int
    step: int
    model_state: bytes
    optimizer_state: bytes
    metrics: TrainingMetrics
    created_at: datetime = field(default_factory=datetime.utcnow)
    size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "job_id": self.job_id,
            "epoch": self.epoch,
            "step": self.step,
            "metrics": self.metrics.to_dict(),
            "created_at": self.created_at.isoformat(),
            "size_bytes": self.size_bytes,
        }


@dataclass
class GradientUpdate:
    """Gradient update from a worker."""
    worker_id: str
    step: int
    gradients: Dict[str, np.ndarray]
    loss: float
    samples_in_batch: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# Gradient Aggregator
# =============================================================================


class GradientAggregator(ABC):
    """Base class for gradient aggregation."""

    @abstractmethod
    async def aggregate(
        self,
        updates: List[GradientUpdate],
    ) -> Dict[str, np.ndarray]:
        """Aggregate gradients from multiple workers."""
        pass


class SyncSGDAggregator(GradientAggregator):
    """Synchronous SGD aggregation."""

    async def aggregate(
        self,
        updates: List[GradientUpdate],
    ) -> Dict[str, np.ndarray]:
        """Average gradients synchronously."""
        if not updates:
            return {}

        aggregated = {}
        total_samples = sum(u.samples_in_batch for u in updates)

        for key in updates[0].gradients.keys():
            weighted_sum = np.zeros_like(updates[0].gradients[key])
            for update in updates:
                weight = update.samples_in_batch / total_samples
                weighted_sum += update.gradients[key] * weight
            aggregated[key] = weighted_sum

        return aggregated


class RingAllReduceAggregator(GradientAggregator):
    """Ring AllReduce aggregation (simulated)."""

    def __init__(self, num_workers: int):
        self.num_workers = num_workers

    async def aggregate(
        self,
        updates: List[GradientUpdate],
    ) -> Dict[str, np.ndarray]:
        """Simulate ring allreduce aggregation."""
        if not updates:
            return {}

        # In real implementation, this would use NCCL or similar
        # Here we simulate the ring reduce-scatter and allgather phases

        aggregated = {}
        for key in updates[0].gradients.keys():
            # Sum all gradients
            total = np.zeros_like(updates[0].gradients[key])
            for update in updates:
                total += update.gradients[key]
            # Average
            aggregated[key] = total / len(updates)

        return aggregated


class FederatedAvgAggregator(GradientAggregator):
    """Federated Averaging aggregation."""

    async def aggregate(
        self,
        updates: List[GradientUpdate],
    ) -> Dict[str, np.ndarray]:
        """Federated averaging of model updates."""
        if not updates:
            return {}

        aggregated = {}
        total_samples = sum(u.samples_in_batch for u in updates)

        for key in updates[0].gradients.keys():
            weighted_avg = np.zeros_like(updates[0].gradients[key])
            for update in updates:
                weight = update.samples_in_batch / total_samples
                weighted_avg += update.gradients[key] * weight
            aggregated[key] = weighted_avg

        return aggregated


# =============================================================================
# Parameter Server
# =============================================================================


class ParameterServer:
    """
    Central parameter server for distributed training.

    خادم المعلمات المركزي للتدريب الموزع.
    """

    def __init__(
        self,
        aggregation_method: AggregationMethod = AggregationMethod.SYNC_SGD,
        num_workers: int = 1,
    ):
        self.aggregation_method = aggregation_method
        self.num_workers = num_workers

        # Model parameters
        self._parameters: Dict[str, np.ndarray] = {}
        self._optimizer_state: Dict[str, Any] = {}

        # Gradient buffer
        self._gradient_buffer: Dict[int, List[GradientUpdate]] = {}
        self._current_step = 0

        # Aggregator
        self._aggregator = self._create_aggregator()

        # Locks
        self._param_lock = asyncio.Lock()
        self._gradient_lock = asyncio.Lock()

        # Stats
        self._stats = {
            "updates_received": 0,
            "aggregations_performed": 0,
            "total_samples": 0,
        }

    def _create_aggregator(self) -> GradientAggregator:
        """Create appropriate aggregator."""
        if self.aggregation_method == AggregationMethod.RING_ALLREDUCE:
            return RingAllReduceAggregator(self.num_workers)
        elif self.aggregation_method == AggregationMethod.FEDERATED_AVG:
            return FederatedAvgAggregator()
        else:
            return SyncSGDAggregator()

    async def initialize_parameters(
        self,
        parameters: Dict[str, np.ndarray],
    ) -> None:
        """Initialize model parameters."""
        async with self._param_lock:
            self._parameters = {k: v.copy() for k, v in parameters.items()}
            logger.info(f"Initialized {len(parameters)} parameter tensors")

    async def get_parameters(self) -> Dict[str, np.ndarray]:
        """Get current model parameters."""
        async with self._param_lock:
            return {k: v.copy() for k, v in self._parameters.items()}

    async def submit_gradients(
        self,
        update: GradientUpdate,
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Submit gradients from a worker.

        Returns aggregated gradients if all workers have submitted.
        """
        async with self._gradient_lock:
            step = update.step

            if step not in self._gradient_buffer:
                self._gradient_buffer[step] = []

            self._gradient_buffer[step].append(update)
            self._stats["updates_received"] += 1
            self._stats["total_samples"] += update.samples_in_batch

            # Check if all workers have submitted for this step
            if len(self._gradient_buffer[step]) >= self.num_workers:
                # Aggregate gradients
                aggregated = await self._aggregator.aggregate(
                    self._gradient_buffer[step]
                )

                # Clear buffer for this step
                del self._gradient_buffer[step]
                self._stats["aggregations_performed"] += 1

                return aggregated

        return None

    async def apply_gradients(
        self,
        gradients: Dict[str, np.ndarray],
        learning_rate: float,
    ) -> None:
        """Apply aggregated gradients to parameters."""
        async with self._param_lock:
            for key, grad in gradients.items():
                if key in self._parameters:
                    # Simple SGD update
                    self._parameters[key] -= learning_rate * grad

            self._current_step += 1

    async def get_statistics(self) -> Dict[str, Any]:
        """Get parameter server statistics."""
        return {
            **self._stats,
            "current_step": self._current_step,
            "num_parameters": len(self._parameters),
            "pending_gradients": sum(
                len(updates) for updates in self._gradient_buffer.values()
            ),
        }


# =============================================================================
# Distributed Trainer
# =============================================================================


class DistributedTrainer:
    """
    Distributed training coordinator.

    منسق التدريب الموزع.

    Features:
    - Data parallel training
    - Model parallel training
    - Gradient aggregation
    - Checkpointing
    - Fault tolerance
    """

    def __init__(
        self,
        config: TrainingConfig,
        checkpoint_dir: str = "/tmp/checkpoints",
    ):
        self.config = config
        self.checkpoint_dir = checkpoint_dir

        # Parameter server
        self.parameter_server = ParameterServer(
            aggregation_method=config.aggregation,
            num_workers=config.num_workers,
        )

        # Worker states
        self._workers: Dict[str, WorkerState] = {}
        self._metrics = TrainingMetrics(job_id=config.job_id)

        # Training state
        self._status = TrainingStatus.PENDING
        self._start_time: Optional[float] = None
        self._checkpoints: List[Checkpoint] = []

        # Callbacks
        self._on_step_callbacks: List[Callable] = []
        self._on_epoch_callbacks: List[Callable] = []

        # Locks
        self._lock = asyncio.Lock()

        # Create checkpoint directory
        os.makedirs(checkpoint_dir, exist_ok=True)

    async def initialize(
        self,
        initial_parameters: Dict[str, np.ndarray],
    ) -> None:
        """Initialize training with model parameters."""
        self._status = TrainingStatus.INITIALIZING

        await self.parameter_server.initialize_parameters(initial_parameters)

        # Calculate total steps
        # Assuming dataset_size is provided in config
        dataset_size = self.config.extra_config.get("dataset_size", 10000)
        steps_per_epoch = dataset_size // (
            self.config.batch_size * self.config.num_workers
        )
        self._metrics.total_steps = steps_per_epoch * self.config.epochs

        self._status = TrainingStatus.TRAINING
        self._start_time = time.time()

        logger.info(
            f"Initialized distributed training: "
            f"workers={self.config.num_workers}, "
            f"total_steps={self._metrics.total_steps}"
        )

    async def register_worker(
        self,
        worker_id: str,
        rank: int,
    ) -> Dict[str, np.ndarray]:
        """
        Register a training worker.

        Returns initial model parameters.
        """
        async with self._lock:
            self._workers[worker_id] = WorkerState(
                worker_id=worker_id,
                rank=rank,
                status=TrainingStatus.TRAINING,
            )

        logger.info(f"Worker registered: {worker_id} (rank {rank})")

        return await self.parameter_server.get_parameters()

    async def submit_training_update(
        self,
        worker_id: str,
        step: int,
        gradients: Dict[str, np.ndarray],
        loss: float,
        samples: int,
        metrics: Optional[Dict[str, float]] = None,
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Submit training update from a worker.

        Returns new parameters if aggregation completed.
        """
        # Update worker state
        async with self._lock:
            if worker_id in self._workers:
                worker = self._workers[worker_id]
                worker.current_step = step
                worker.loss = loss
                worker.samples_processed += samples
                worker.last_heartbeat = datetime.utcnow()

                if metrics:
                    worker.throughput = metrics.get("throughput", 0)
                    worker.gpu_memory_used = metrics.get("gpu_memory", 0)

        # Submit gradients
        update = GradientUpdate(
            worker_id=worker_id,
            step=step,
            gradients=gradients,
            loss=loss,
            samples_in_batch=samples,
        )

        aggregated = await self.parameter_server.submit_gradients(update)

        if aggregated:
            # Apply gradients
            lr = self._get_learning_rate(step)
            await self.parameter_server.apply_gradients(aggregated, lr)

            # Update metrics
            await self._update_metrics(step, loss)

            # Check for checkpoint
            if step % self.config.checkpoint_interval == 0:
                await self._save_checkpoint(step)

            # Call step callbacks
            for callback in self._on_step_callbacks:
                try:
                    await callback(step, self._metrics)
                except Exception as e:
                    logger.error(f"Step callback error: {e}")

            return await self.parameter_server.get_parameters()

        return None

    def _get_learning_rate(self, step: int) -> float:
        """Get learning rate with warmup and decay."""
        base_lr = self.config.learning_rate

        # Warmup
        if step < self.config.warmup_steps:
            return base_lr * (step / self.config.warmup_steps)

        # Could add learning rate decay here
        return base_lr

    async def _update_metrics(self, step: int, loss: float) -> None:
        """Update training metrics."""
        self._metrics.current_step = step
        self._metrics.train_loss = loss
        self._metrics.learning_rate = self._get_learning_rate(step)
        self._metrics.loss_history.append(loss)

        if loss < self._metrics.best_loss:
            self._metrics.best_loss = loss

        # Calculate epoch
        steps_per_epoch = self._metrics.total_steps // self.config.epochs
        self._metrics.current_epoch = step // steps_per_epoch if steps_per_epoch > 0 else 0

        # Calculate throughput and timing
        if self._start_time:
            elapsed = time.time() - self._start_time
            self._metrics.elapsed_time = elapsed

            total_samples = sum(w.samples_processed for w in self._workers.values())
            self._metrics.total_samples = total_samples
            self._metrics.throughput = total_samples / elapsed if elapsed > 0 else 0

            # Estimate remaining time
            if step > 0:
                time_per_step = elapsed / step
                remaining_steps = self._metrics.total_steps - step
                self._metrics.estimated_remaining = time_per_step * remaining_steps

    async def _save_checkpoint(self, step: int) -> Checkpoint:
        """Save training checkpoint."""
        import uuid

        parameters = await self.parameter_server.get_parameters()

        # Serialize parameters
        model_state = pickle.dumps(parameters)
        optimizer_state = pickle.dumps(self.parameter_server._optimizer_state)

        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            job_id=self.config.job_id,
            epoch=self._metrics.current_epoch,
            step=step,
            model_state=model_state,
            optimizer_state=optimizer_state,
            metrics=TrainingMetrics(**self._metrics.to_dict()),
            size_bytes=len(model_state) + len(optimizer_state),
        )

        # Save to disk
        checkpoint_path = os.path.join(
            self.checkpoint_dir,
            f"checkpoint_{self.config.job_id}_{step}.pkl"
        )
        with open(checkpoint_path, "wb") as f:
            pickle.dump(checkpoint, f)

        self._checkpoints.append(checkpoint)
        self._metrics.checkpoints_saved += 1

        logger.info(f"Saved checkpoint at step {step}")

        return checkpoint

    async def load_checkpoint(
        self,
        checkpoint_id: str,
    ) -> bool:
        """Load training from checkpoint."""
        for checkpoint in self._checkpoints:
            if checkpoint.checkpoint_id == checkpoint_id:
                parameters = pickle.loads(checkpoint.model_state)
                await self.parameter_server.initialize_parameters(parameters)

                self._metrics = checkpoint.metrics
                logger.info(f"Loaded checkpoint from step {checkpoint.step}")
                return True

        return False

    async def get_status(self) -> Dict[str, Any]:
        """Get training status."""
        return {
            "job_id": self.config.job_id,
            "status": self._status.value,
            "config": self.config.to_dict(),
            "metrics": self._metrics.to_dict(),
            "workers": {
                wid: w.to_dict() for wid, w in self._workers.items()
            },
            "checkpoints": len(self._checkpoints),
        }

    async def complete_training(self) -> Dict[str, Any]:
        """Mark training as complete."""
        self._status = TrainingStatus.COMPLETED

        # Save final checkpoint
        await self._save_checkpoint(self._metrics.current_step)

        # Get final parameters
        final_parameters = await self.parameter_server.get_parameters()

        return {
            "status": "completed",
            "metrics": self._metrics.to_dict(),
            "final_parameters": {k: v.shape for k, v in final_parameters.items()},
            "checkpoints": len(self._checkpoints),
        }

    async def cancel_training(self) -> None:
        """Cancel training."""
        self._status = TrainingStatus.CANCELLED
        logger.info(f"Training cancelled: {self.config.job_id}")

    def on_step(self, callback: Callable) -> None:
        """Register step callback."""
        self._on_step_callbacks.append(callback)

    def on_epoch(self, callback: Callable) -> None:
        """Register epoch callback."""
        self._on_epoch_callbacks.append(callback)


# =============================================================================
# Training Job Manager
# =============================================================================


class TrainingJobManager:
    """
    Manager for distributed training jobs.

    مدير وظائف التدريب الموزع.
    """

    def __init__(
        self,
        checkpoint_base_dir: str = "/tmp/training",
        max_concurrent_jobs: int = 10,
    ):
        self.checkpoint_base_dir = checkpoint_base_dir
        self.max_concurrent_jobs = max_concurrent_jobs

        self._jobs: Dict[str, DistributedTrainer] = {}
        self._lock = asyncio.Lock()

        os.makedirs(checkpoint_base_dir, exist_ok=True)

    async def create_job(
        self,
        config: TrainingConfig,
        initial_parameters: Optional[Dict[str, np.ndarray]] = None,
    ) -> str:
        """Create a new training job."""
        async with self._lock:
            if len(self._jobs) >= self.max_concurrent_jobs:
                raise RuntimeError("Maximum concurrent jobs reached")

            checkpoint_dir = os.path.join(
                self.checkpoint_base_dir,
                config.job_id
            )

            trainer = DistributedTrainer(
                config=config,
                checkpoint_dir=checkpoint_dir,
            )

            if initial_parameters:
                await trainer.initialize(initial_parameters)

            self._jobs[config.job_id] = trainer

        logger.info(f"Created training job: {config.job_id}")
        return config.job_id

    async def get_job(self, job_id: str) -> Optional[DistributedTrainer]:
        """Get training job by ID."""
        return self._jobs.get(job_id)

    async def list_jobs(self) -> List[Dict[str, Any]]:
        """List all training jobs."""
        jobs = []
        for job_id, trainer in self._jobs.items():
            status = await trainer.get_status()
            jobs.append(status)
        return jobs

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a training job."""
        trainer = self._jobs.get(job_id)
        if trainer:
            await trainer.cancel_training()
            return True
        return False

    async def cleanup_completed_jobs(self) -> int:
        """Remove completed jobs from memory."""
        async with self._lock:
            completed = [
                jid for jid, t in self._jobs.items()
                if t._status in [TrainingStatus.COMPLETED, TrainingStatus.CANCELLED]
            ]
            for jid in completed:
                del self._jobs[jid]
            return len(completed)


# =============================================================================
# Data Sharding Utilities
# =============================================================================


class DataSharder:
    """
    Utility for sharding data across workers.

    أداة لتقسيم البيانات عبر العمال.
    """

    @staticmethod
    def shard_indices(
        total_samples: int,
        num_shards: int,
        shard_id: int,
        shuffle: bool = True,
        seed: int = 42,
    ) -> List[int]:
        """Get indices for a specific shard."""
        indices = list(range(total_samples))

        if shuffle:
            rng = np.random.RandomState(seed)
            rng.shuffle(indices)

        # Calculate shard boundaries
        shard_size = total_samples // num_shards
        remainder = total_samples % num_shards

        start = shard_id * shard_size + min(shard_id, remainder)
        end = start + shard_size + (1 if shard_id < remainder else 0)

        return indices[start:end]

    @staticmethod
    def create_batch_iterator(
        indices: List[int],
        batch_size: int,
        drop_last: bool = True,
    ):
        """Create batch iterator from indices."""
        for i in range(0, len(indices), batch_size):
            batch = indices[i:i + batch_size]
            if len(batch) == batch_size or not drop_last:
                yield batch

    @staticmethod
    def compute_shard_hash(
        data: bytes,
        num_shards: int,
    ) -> int:
        """Compute consistent shard assignment for data."""
        hash_value = int(hashlib.md5(data).hexdigest(), 16)
        return hash_value % num_shards


# =============================================================================
# Model Partitioner (for Model Parallelism)
# =============================================================================


class ModelPartitioner:
    """
    Utility for partitioning models across workers.

    أداة لتقسيم النماذج عبر العمال.
    """

    @staticmethod
    def partition_layers(
        layer_names: List[str],
        num_partitions: int,
    ) -> Dict[int, List[str]]:
        """Partition layers across workers."""
        partitions: Dict[int, List[str]] = {i: [] for i in range(num_partitions)}

        for i, layer in enumerate(layer_names):
            partition_id = i % num_partitions
            partitions[partition_id].append(layer)

        return partitions

    @staticmethod
    def partition_by_memory(
        layers: List[Tuple[str, int]],  # (name, memory_bytes)
        num_partitions: int,
    ) -> Dict[int, List[str]]:
        """Partition layers by memory usage (balanced)."""
        # Sort by memory (largest first)
        sorted_layers = sorted(layers, key=lambda x: x[1], reverse=True)

        partitions: Dict[int, List[str]] = {i: [] for i in range(num_partitions)}
        partition_sizes = [0] * num_partitions

        # Greedy assignment to smallest partition
        for name, size in sorted_layers:
            min_partition = min(range(num_partitions), key=lambda i: partition_sizes[i])
            partitions[min_partition].append(name)
            partition_sizes[min_partition] += size

        return partitions


# =============================================================================
# Training Utilities
# =============================================================================


def create_training_config(
    job_id: str,
    model_name: str,
    num_workers: int = 4,
    batch_size: int = 32,
    epochs: int = 10,
    learning_rate: float = 0.001,
    strategy: TrainingStrategy = TrainingStrategy.DATA_PARALLEL,
    **kwargs,
) -> TrainingConfig:
    """Helper to create training configuration."""
    return TrainingConfig(
        job_id=job_id,
        model_name=model_name,
        strategy=strategy,
        aggregation=AggregationMethod.SYNC_SGD,
        num_workers=num_workers,
        batch_size=batch_size,
        epochs=epochs,
        learning_rate=learning_rate,
        extra_config=kwargs,
    )


async def simulate_training_step(
    trainer: DistributedTrainer,
    worker_id: str,
    step: int,
    batch_size: int,
) -> Optional[Dict[str, np.ndarray]]:
    """Simulate a training step (for testing)."""
    # Generate fake gradients
    params = await trainer.parameter_server.get_parameters()
    gradients = {
        k: np.random.randn(*v.shape) * 0.01
        for k, v in params.items()
    }

    # Simulate loss
    loss = 1.0 / (1 + step * 0.01) + np.random.random() * 0.1

    return await trainer.submit_training_update(
        worker_id=worker_id,
        step=step,
        gradients=gradients,
        loss=loss,
        samples=batch_size,
    )
