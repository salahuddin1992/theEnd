"""
Training Pipeline - خط أنابيب التدريب
======================================

Distributed training pipeline for ML models.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TrainingJobStatus(str, Enum):
    """Training job status."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DistributedStrategy(str, Enum):
    """Distributed training strategies."""
    NONE = "none"
    DATA_PARALLEL = "data_parallel"
    MODEL_PARALLEL = "model_parallel"
    PIPELINE_PARALLEL = "pipeline_parallel"
    HYBRID = "hybrid"


@dataclass
class TrainingConfig:
    """Training configuration."""
    # Model settings
    model_name: str = ""
    model_type: str = ""  # pytorch, tensorflow, sklearn

    # Data settings
    train_data_path: str = ""
    validation_data_path: Optional[str] = None
    test_data_path: Optional[str] = None
    batch_size: int = 32
    shuffle: bool = True

    # Training settings
    epochs: int = 10
    learning_rate: float = 0.001
    optimizer: str = "adam"
    loss_function: str = "cross_entropy"

    # Regularization
    weight_decay: float = 0.0
    dropout: float = 0.0

    # Checkpointing
    checkpoint_dir: str = "./checkpoints"
    save_every_n_epochs: int = 1
    save_best_only: bool = True
    max_checkpoints: int = 5

    # Early stopping
    early_stopping: bool = True
    early_stopping_patience: int = 5
    early_stopping_metric: str = "val_loss"
    early_stopping_mode: str = "min"

    # Distributed training
    distributed: bool = False
    distributed_strategy: DistributedStrategy = DistributedStrategy.DATA_PARALLEL
    num_workers: int = 1
    num_gpus_per_worker: int = 1

    # Logging
    log_every_n_steps: int = 100
    metrics: List[str] = field(default_factory=lambda: ["loss", "accuracy"])

    # Resources
    memory_limit_gb: Optional[float] = None
    gpu_memory_fraction: float = 0.9

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "model_type": self.model_type,
            "batch_size": self.batch_size,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "optimizer": self.optimizer,
            "distributed": self.distributed,
            "distributed_strategy": self.distributed_strategy.value,
            "num_workers": self.num_workers,
        }


@dataclass
class TrainingMetrics:
    """Training metrics snapshot."""
    epoch: int
    step: int
    metrics: Dict[str, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "epoch": self.epoch,
            "step": self.step,
            "metrics": self.metrics,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Checkpoint:
    """Model checkpoint."""
    checkpoint_id: str
    job_id: str
    epoch: int
    step: int
    path: str
    metrics: Dict[str, float]
    is_best: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "job_id": self.job_id,
            "epoch": self.epoch,
            "step": self.step,
            "path": self.path,
            "metrics": self.metrics,
            "is_best": self.is_best,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class TrainingJob:
    """Training job instance."""
    job_id: str
    config: TrainingConfig
    status: TrainingJobStatus = TrainingJobStatus.PENDING

    # Progress
    current_epoch: int = 0
    current_step: int = 0
    total_steps: int = 0

    # Metrics history
    metrics_history: List[TrainingMetrics] = field(default_factory=list)
    best_metrics: Optional[Dict[str, float]] = None

    # Checkpoints
    checkpoints: List[Checkpoint] = field(default_factory=list)
    best_checkpoint_id: Optional[str] = None

    # Output
    output_model_path: Optional[str] = None

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error
    error: Optional[str] = None

    @property
    def progress(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return min(1.0, self.current_step / self.total_steps)

    @property
    def elapsed_time(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "current_epoch": self.current_epoch,
            "current_step": self.current_step,
            "progress": self.progress,
            "best_metrics": self.best_metrics,
            "elapsed_time": self.elapsed_time,
            "created_at": self.created_at.isoformat(),
            "error": self.error,
        }


class CheckpointManager:
    """Manages model checkpoints."""

    def __init__(
        self,
        checkpoint_dir: str,
        max_checkpoints: int = 5,
    ):
        self._checkpoint_dir = Path(checkpoint_dir)
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._max_checkpoints = max_checkpoints
        self._checkpoints: Dict[str, List[Checkpoint]] = {}

    def save_checkpoint(
        self,
        job_id: str,
        epoch: int,
        step: int,
        model_state: Any,
        optimizer_state: Any,
        metrics: Dict[str, float],
        is_best: bool = False,
    ) -> Checkpoint:
        """Save a checkpoint."""
        checkpoint_id = str(uuid.uuid4())
        checkpoint_path = self._checkpoint_dir / job_id / f"checkpoint_{epoch}_{step}"
        checkpoint_path.mkdir(parents=True, exist_ok=True)

        # Save states
        state = {
            "epoch": epoch,
            "step": step,
            "model_state": model_state,
            "optimizer_state": optimizer_state,
            "metrics": metrics,
        }

        # Try to use torch if available
        try:
            import torch
            torch.save(state, checkpoint_path / "state.pt")
        except ImportError:
            import pickle
            with open(checkpoint_path / "state.pkl", "wb") as f:
                pickle.dump(state, f)

        # Save metadata
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            job_id=job_id,
            epoch=epoch,
            step=step,
            path=str(checkpoint_path),
            metrics=metrics,
            is_best=is_best,
        )

        with open(checkpoint_path / "meta.json", "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)

        # Track checkpoints
        if job_id not in self._checkpoints:
            self._checkpoints[job_id] = []
        self._checkpoints[job_id].append(checkpoint)

        # Cleanup old checkpoints
        self._cleanup_checkpoints(job_id)

        logger.info(f"Saved checkpoint: {checkpoint_id}")
        return checkpoint

    def load_checkpoint(
        self,
        checkpoint_path: str,
    ) -> Dict[str, Any]:
        """Load a checkpoint."""
        path = Path(checkpoint_path)

        try:
            import torch
            state = torch.load(path / "state.pt", map_location="cpu")
        except ImportError:
            import pickle
            with open(path / "state.pkl", "rb") as f:
                state = pickle.load(f)

        return state

    def get_best_checkpoint(self, job_id: str) -> Optional[Checkpoint]:
        """Get the best checkpoint for a job."""
        checkpoints = self._checkpoints.get(job_id, [])
        for cp in reversed(checkpoints):
            if cp.is_best:
                return cp
        return checkpoints[-1] if checkpoints else None

    def get_latest_checkpoint(self, job_id: str) -> Optional[Checkpoint]:
        """Get the latest checkpoint for a job."""
        checkpoints = self._checkpoints.get(job_id, [])
        return checkpoints[-1] if checkpoints else None

    def _cleanup_checkpoints(self, job_id: str) -> None:
        """Remove old checkpoints beyond max limit."""
        checkpoints = self._checkpoints.get(job_id, [])

        # Keep best checkpoint and most recent ones
        best = [cp for cp in checkpoints if cp.is_best]
        non_best = [cp for cp in checkpoints if not cp.is_best]

        # Sort by step and keep most recent
        non_best.sort(key=lambda cp: cp.step)
        to_remove = (
            non_best[:-self._max_checkpoints + len(best)]
            if len(non_best) > self._max_checkpoints - len(best)
            else []
        )

        for cp in to_remove:
            try:
                shutil.rmtree(cp.path)
                checkpoints.remove(cp)
            except Exception as e:
                logger.error(f"Failed to remove checkpoint: {e}")


class DistributedTrainer:
    """
    Distributed Trainer - المدرب الموزع.

    Handles distributed training across multiple workers.
    """

    def __init__(
        self,
        strategy: DistributedStrategy = DistributedStrategy.DATA_PARALLEL,
        num_workers: int = 1,
        num_gpus_per_worker: int = 1,
    ):
        self.strategy = strategy
        self.num_workers = num_workers
        self.num_gpus_per_worker = num_gpus_per_worker
        self._is_initialized = False
        self._rank = 0
        self._world_size = num_workers

    def initialize(self) -> None:
        """Initialize distributed training environment."""
        if self.strategy == DistributedStrategy.NONE:
            self._is_initialized = True
            return

        try:
            import torch.distributed as dist

            if not dist.is_initialized():
                # Initialize process group
                backend = "nccl" if self.num_gpus_per_worker > 0 else "gloo"
                dist.init_process_group(backend=backend)
                self._rank = dist.get_rank()
                self._world_size = dist.get_world_size()

            self._is_initialized = True
            logger.info(f"Initialized distributed training: rank={self._rank}, world_size={self._world_size}")

        except Exception as e:
            logger.warning(f"Failed to initialize distributed training: {e}")
            self._is_initialized = True

    def cleanup(self) -> None:
        """Cleanup distributed training environment."""
        try:
            import torch.distributed as dist
            if dist.is_initialized():
                dist.destroy_process_group()
        except Exception:
            pass

    def wrap_model(self, model: Any) -> Any:
        """Wrap model for distributed training."""
        if self.strategy == DistributedStrategy.NONE:
            return model

        try:
            import torch
            import torch.nn as nn
            from torch.nn.parallel import DistributedDataParallel

            if isinstance(model, nn.Module) and self.strategy == DistributedStrategy.DATA_PARALLEL:
                if torch.cuda.is_available():
                    model = model.cuda()
                    model = DistributedDataParallel(model)
                else:
                    model = nn.DataParallel(model)

            return model

        except ImportError:
            return model

    def is_main_process(self) -> bool:
        """Check if this is the main process."""
        return self._rank == 0

    @property
    def rank(self) -> int:
        return self._rank

    @property
    def world_size(self) -> int:
        return self._world_size


class TrainingPipeline:
    """
    Training Pipeline - خط أنابيب التدريب.

    Manages training jobs with support for distributed training.

    Example:
        pipeline = TrainingPipeline()

        # Create training job
        config = TrainingConfig(
            model_name="my-model",
            model_type="pytorch",
            train_data_path="./data/train",
            epochs=10,
            batch_size=32,
            distributed=True,
            num_workers=4,
        )

        job = pipeline.create_job(config)

        # Run training
        await pipeline.train(job.job_id, model, train_loader, val_loader)

        # Get best checkpoint
        checkpoint = pipeline.get_best_checkpoint(job.job_id)
    """

    def __init__(self, storage_path: str = "./training"):
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, TrainingJob] = {}
        self._checkpoint_manager = CheckpointManager(
            str(self._storage_path / "checkpoints")
        )

    def create_job(self, config: TrainingConfig) -> TrainingJob:
        """Create a new training job."""
        job = TrainingJob(
            job_id=str(uuid.uuid4()),
            config=config,
        )
        self._jobs[job.job_id] = job
        logger.info(f"Created training job: {job.job_id}")
        return job

    def get_job(self, job_id: str) -> Optional[TrainingJob]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        status: Optional[TrainingJobStatus] = None,
    ) -> List[TrainingJob]:
        """List all jobs."""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    async def train(
        self,
        job_id: str,
        model: Any,
        train_loader: Any,
        val_loader: Any = None,
        train_step_fn: Optional[Callable] = None,
        val_step_fn: Optional[Callable] = None,
    ) -> TrainingJob:
        """Run training for a job."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        job.status = TrainingJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)

        config = job.config
        best_metric = float("inf") if config.early_stopping_mode == "min" else float("-inf")
        patience_counter = 0

        try:
            # Initialize distributed training
            trainer = DistributedTrainer(
                strategy=config.distributed_strategy,
                num_workers=config.num_workers,
                num_gpus_per_worker=config.num_gpus_per_worker,
            )
            if config.distributed:
                trainer.initialize()
                model = trainer.wrap_model(model)

            # Calculate total steps
            steps_per_epoch = len(train_loader) if hasattr(train_loader, "__len__") else 1000
            job.total_steps = config.epochs * steps_per_epoch

            # Training loop
            for epoch in range(config.epochs):
                job.current_epoch = epoch + 1

                # Train epoch
                train_metrics = await self._train_epoch(
                    job, model, train_loader, train_step_fn, epoch
                )

                # Validation
                val_metrics = {}
                if val_loader:
                    val_metrics = await self._validate(
                        job, model, val_loader, val_step_fn
                    )

                # Combine metrics
                all_metrics = {**train_metrics}
                for k, v in val_metrics.items():
                    all_metrics[f"val_{k}"] = v

                # Log metrics
                job.metrics_history.append(TrainingMetrics(
                    epoch=epoch + 1,
                    step=job.current_step,
                    metrics=all_metrics,
                ))

                # Check for best model
                metric_value = all_metrics.get(config.early_stopping_metric, 0)
                is_best = False
                if config.early_stopping_mode == "min":
                    if metric_value < best_metric:
                        best_metric = metric_value
                        is_best = True
                        patience_counter = 0
                    else:
                        patience_counter += 1
                else:
                    if metric_value > best_metric:
                        best_metric = metric_value
                        is_best = True
                        patience_counter = 0
                    else:
                        patience_counter += 1

                # Save checkpoint
                if (epoch + 1) % config.save_every_n_epochs == 0:
                    if not config.save_best_only or is_best:
                        checkpoint = self._checkpoint_manager.save_checkpoint(
                            job_id=job.job_id,
                            epoch=epoch + 1,
                            step=job.current_step,
                            model_state=self._get_model_state(model),
                            optimizer_state=None,
                            metrics=all_metrics,
                            is_best=is_best,
                        )
                        job.checkpoints.append(checkpoint)
                        if is_best:
                            job.best_checkpoint_id = checkpoint.checkpoint_id
                            job.best_metrics = all_metrics

                # Early stopping
                if config.early_stopping and patience_counter >= config.early_stopping_patience:
                    logger.info(f"Early stopping at epoch {epoch + 1}")
                    break

            job.status = TrainingJobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)

            if config.distributed:
                trainer.cleanup()

            logger.info(f"Completed training job: {job_id}")

        except Exception as e:
            job.status = TrainingJobStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.now(timezone.utc)
            logger.error(f"Training job failed: {job_id}, error: {e}")

        return job

    async def _train_epoch(
        self,
        job: TrainingJob,
        model: Any,
        train_loader: Any,
        train_step_fn: Optional[Callable],
        epoch: int,
    ) -> Dict[str, float]:
        """Train for one epoch."""
        metrics_sum = {}
        num_batches = 0

        for batch_idx, batch in enumerate(train_loader):
            job.current_step += 1

            if train_step_fn:
                batch_metrics = train_step_fn(model, batch)
            else:
                batch_metrics = {"loss": 0.0}

            # Accumulate metrics
            for k, v in batch_metrics.items():
                if k not in metrics_sum:
                    metrics_sum[k] = 0.0
                metrics_sum[k] += v
            num_batches += 1

            # Log periodically
            if batch_idx % job.config.log_every_n_steps == 0:
                logger.debug(f"Epoch {epoch + 1}, Step {batch_idx}: {batch_metrics}")

            # Allow async operations
            await asyncio.sleep(0)

        # Average metrics
        return {k: v / num_batches for k, v in metrics_sum.items()}

    async def _validate(
        self,
        job: TrainingJob,
        model: Any,
        val_loader: Any,
        val_step_fn: Optional[Callable],
    ) -> Dict[str, float]:
        """Run validation."""
        metrics_sum = {}
        num_batches = 0

        for batch in val_loader:
            if val_step_fn:
                batch_metrics = val_step_fn(model, batch)
            else:
                batch_metrics = {"loss": 0.0}

            for k, v in batch_metrics.items():
                if k not in metrics_sum:
                    metrics_sum[k] = 0.0
                metrics_sum[k] += v
            num_batches += 1

            await asyncio.sleep(0)

        return {k: v / num_batches for k, v in metrics_sum.items()}

    def _get_model_state(self, model: Any) -> Any:
        """Get model state dict."""
        try:
            import torch.nn as nn
            from torch.nn.parallel import DataParallel, DistributedDataParallel

            if isinstance(model, (DistributedDataParallel, DataParallel)):
                return model.module.state_dict()
            elif isinstance(model, nn.Module):
                return model.state_dict()
        except ImportError:
            pass

        # For sklearn or other models
        return model

    def cancel_job(self, job_id: str) -> None:
        """Cancel a training job."""
        job = self._jobs.get(job_id)
        if job:
            job.status = TrainingJobStatus.CANCELLED
            job.completed_at = datetime.now(timezone.utc)

    def get_best_checkpoint(self, job_id: str) -> Optional[Checkpoint]:
        """Get the best checkpoint for a job."""
        return self._checkpoint_manager.get_best_checkpoint(job_id)

    def get_latest_checkpoint(self, job_id: str) -> Optional[Checkpoint]:
        """Get the latest checkpoint for a job."""
        return self._checkpoint_manager.get_latest_checkpoint(job_id)

    def load_checkpoint(self, checkpoint_path: str) -> Dict[str, Any]:
        """Load a checkpoint."""
        return self._checkpoint_manager.load_checkpoint(checkpoint_path)

    def get_metrics_history(
        self,
        job_id: str,
    ) -> List[Dict[str, Any]]:
        """Get metrics history for a job."""
        job = self._jobs.get(job_id)
        if not job:
            return []
        return [m.to_dict() for m in job.metrics_history]
