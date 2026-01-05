# -*- coding: utf-8 -*-
"""
Federated Learning Coordinator - منسق التعلم الموحد
====================================================

High-level coordinator for federated learning.

منسق عالي المستوى للتعلم الموحد:
- تنسيق التدريب الكامل
- إدارة العملاء والخادم
- التقييم والمراقبة
- التسجيل والتتبع
"""

from __future__ import annotations

import asyncio
import logging
import os
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from distributed_cluster.federated.aggregator import create_aggregator
from distributed_cluster.federated.client import (
    ClientManager,
    FederatedClient,
)
from distributed_cluster.federated.compression import (
    create_compressor,
)
from distributed_cluster.federated.models import (
    AggregationStrategy,
    FederatedConfig,
    FederatedMetrics,
    ModelWeights,
    RoundResult,
    RoundStatus,
    SelectionStrategy,
)
from distributed_cluster.federated.privacy import (
    create_privacy_mechanism,
)
from distributed_cluster.federated.selection import (
    create_selector,
)
from distributed_cluster.federated.server import FederatedServer

logger = logging.getLogger(__name__)


# =============================================================================
# Evaluation Function Type
# =============================================================================


EvaluationFn = Callable[
    [Dict[str, np.ndarray], int],
    Tuple[float, Dict[str, float]]
]


# =============================================================================
# Coordinator State
# =============================================================================


@dataclass
class CoordinatorState:
    """Internal coordinator state."""
    is_running: bool = False
    current_round: int = 0
    total_rounds: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    round_results: List[RoundResult] = field(default_factory=list)
    evaluation_results: List[Dict[str, Any]] = field(default_factory=list)


# =============================================================================
# Federated Learning Coordinator
# =============================================================================


class FederatedCoordinator:
    """
    High-level coordinator for federated learning.

    منسق عالي المستوى للتعلم الموحد.

    This class brings together all FL components:
    - Server for aggregation
    - Clients for local training
    - Selection strategies
    - Privacy mechanisms
    - Compression
    - Evaluation

    Example usage:
        coordinator = FederatedCoordinator(config, initial_weights)
        coordinator.register_clients(clients)
        metrics = await coordinator.train()
    """

    def __init__(
        self,
        config: FederatedConfig,
        initial_weights: Optional[Dict[str, np.ndarray]] = None,
        evaluation_fn: Optional[EvaluationFn] = None,
        checkpoint_dir: str = "/tmp/federated",
    ):
        """
        Initialize the federated learning coordinator.

        Args:
            config: Federated learning configuration
            initial_weights: Initial model weights
            evaluation_fn: Function to evaluate global model
            checkpoint_dir: Directory for checkpoints
        """
        self.config = config
        self.checkpoint_dir = checkpoint_dir
        self._evaluation_fn = evaluation_fn

        # State
        self._state = CoordinatorState(total_rounds=config.total_rounds)

        # Metrics
        self._metrics = FederatedMetrics(
            job_id=config.job_id,
            total_rounds=config.total_rounds,
        )

        # Components
        self._server = FederatedServer(
            config=config,
            initial_weights=initial_weights,
            checkpoint_dir=checkpoint_dir,
        )

        self._client_manager = ClientManager()

        self._selector = create_selector(
            config.selection_strategy,
            seed=config.seed,
        )

        self._aggregator = create_aggregator(
            config.aggregation_strategy,
            server_lr=config.global_learning_rate,
        )

        self._privacy = create_privacy_mechanism(config.privacy_config)

        self._compressor = create_compressor(
            config.compression_config.method,
            config.compression_config,
        )

        # Callbacks
        self._callbacks: Dict[str, List[Callable]] = {
            "on_round_start": [],
            "on_round_end": [],
            "on_evaluation": [],
            "on_training_complete": [],
        }

        # Create checkpoint directory
        os.makedirs(checkpoint_dir, exist_ok=True)

        logger.info(
            f"Initialized FederatedCoordinator: job_id={config.job_id}, "
            f"rounds={config.total_rounds}, "
            f"aggregation={config.aggregation_strategy.value}"
        )

    @property
    def is_running(self) -> bool:
        return self._state.is_running

    @property
    def current_round(self) -> int:
        return self._state.current_round

    @property
    def metrics(self) -> FederatedMetrics:
        return self._metrics

    @property
    def global_model(self) -> Optional[ModelWeights]:
        return self._server.global_model

    # =========================================================================
    # Client Management
    # =========================================================================

    async def register_client(self, client: FederatedClient) -> str:
        """Register a federated learning client."""
        client_id = await self._client_manager.register_client(client)
        await self._server.register_client(client.get_info())
        self._metrics.total_clients += 1
        return client_id

    async def register_clients(self, clients: List[FederatedClient]) -> List[str]:
        """Register multiple clients."""
        client_ids = []
        for client in clients:
            client_id = await self.register_client(client)
            client_ids.append(client_id)
        return client_ids

    async def unregister_client(self, client_id: str) -> bool:
        """Unregister a client."""
        success = await self._client_manager.unregister_client(client_id)
        if success:
            await self._server.unregister_client(client_id)
            self._metrics.total_clients -= 1
        return success

    async def get_client(self, client_id: str) -> Optional[FederatedClient]:
        """Get client by ID."""
        return await self._client_manager.get_client(client_id)

    # =========================================================================
    # Training
    # =========================================================================

    async def _run_round(self, round_number: int) -> RoundResult:
        """Run a single federated learning round."""
        start_time = time.time()

        result = RoundResult(
            round_number=round_number,
            status=RoundStatus.PENDING,
            started_at=datetime.now(timezone.utc),
        )

        # Fire round start callbacks
        for callback in self._callbacks["on_round_start"]:
            try:
                await callback(round_number)
            except Exception as e:
                logger.error(f"Round start callback error: {e}")

        try:
            # Step 1: Client Selection
            result.status = RoundStatus.CLIENT_SELECTION

            available_clients = await self._client_manager.get_available_clients()
            client_infos = [c.get_info() for c in available_clients]

            num_to_select = max(
                self.config.min_clients,
                int(len(client_infos) * self.config.client_fraction),
            )
            num_to_select = min(num_to_select, self.config.max_clients)

            selection_result = self._selector.select(
                client_infos,
                num_to_select,
                round_number,
            )

            if len(selection_result.selected_clients) < self.config.min_clients:
                result.status = RoundStatus.FAILED
                result.error_message = (
                    f"Not enough clients: {len(selection_result.selected_clients)} "
                    f"< {self.config.min_clients}"
                )
                return result

            result.selected_clients = selection_result.selected_clients

            # Step 2: Distribute Model
            result.status = RoundStatus.DISTRIBUTING

            global_model = self._server.global_model
            if global_model is None:
                result.status = RoundStatus.FAILED
                result.error_message = "No global model available"
                return result

            # Step 3: Local Training
            result.status = RoundStatus.TRAINING

            updates = []
            participating_clients = []
            dropped_clients = []

            # Train clients concurrently
            training_tasks = []
            for client_id in selection_result.selected_clients:
                client = await self._client_manager.get_client(client_id)
                if client:
                    task = client.participate_in_round(
                        round_number,
                        global_model,
                        epochs=self.config.local_epochs,
                        learning_rate=self.config.client_learning_rate,
                    )
                    training_tasks.append((client_id, task))

            # Wait for all with timeout
            for client_id, task in training_tasks:
                try:
                    update = await asyncio.wait_for(
                        task,
                        timeout=self.config.round_timeout,
                    )

                    # Apply privacy mechanism
                    update = self._privacy.apply_to_update(update)

                    updates.append(update)
                    participating_clients.append(client_id)

                except asyncio.TimeoutError:
                    logger.warning(f"Client {client_id} timed out")
                    dropped_clients.append(client_id)
                except Exception as e:
                    logger.error(f"Client {client_id} failed: {e}")
                    dropped_clients.append(client_id)

            result.participating_clients = participating_clients
            result.dropped_clients = dropped_clients

            # Check minimum participation
            if len(updates) < self.config.min_clients:
                result.status = RoundStatus.FAILED
                result.error_message = (
                    f"Not enough updates: {len(updates)} "
                    f"< {self.config.min_clients}"
                )
                return result

            # Step 4: Aggregation
            result.status = RoundStatus.AGGREGATING

            aggregation_start = time.time()

            # Apply privacy during aggregation
            updates = self._privacy.apply_to_aggregation(updates)

            # Aggregate
            aggregated = await self._aggregator.aggregate(global_model, updates)

            result.aggregation_time = time.time() - aggregation_start
            result.global_model = aggregated

            # Calculate metrics
            result.total_samples = sum(u.num_samples for u in updates)
            result.aggregated_loss = sum(
                u.training_loss * u.num_samples for u in updates
            ) / result.total_samples if result.total_samples > 0 else 0.0

            # Update server
            await self._server.submit_update(updates[0])  # Trigger update
            for update in updates[1:]:
                await self._server.submit_update(update)

            # Update metrics
            self._metrics.current_round = round_number
            self._metrics.global_loss = result.aggregated_loss
            self._metrics.total_samples_trained += result.total_samples
            self._metrics.loss_history.append(result.aggregated_loss)
            self._metrics.participation_history.append(result.participation_rate)

            if result.aggregated_loss < self._metrics.best_loss:
                self._metrics.best_loss = result.aggregated_loss
                self._metrics.best_round = round_number

            result.status = RoundStatus.COMPLETED

        except Exception as e:
            result.status = RoundStatus.FAILED
            result.error_message = str(e)
            logger.exception(f"Round {round_number} failed")

        finally:
            result.completed_at = datetime.now(timezone.utc)
            result.round_duration = time.time() - start_time

            # Fire round end callbacks
            for callback in self._callbacks["on_round_end"]:
                try:
                    await callback(round_number, result)
                except Exception as e:
                    logger.error(f"Round end callback error: {e}")

        return result

    async def _evaluate(self, round_number: int) -> Optional[Dict[str, Any]]:
        """Evaluate the global model."""
        if self._evaluation_fn is None:
            return None

        if self._server.global_model is None:
            return None

        try:
            loss, metrics = await asyncio.get_event_loop().run_in_executor(
                None,
                self._evaluation_fn,
                self._server.global_model.weights,
                round_number,
            )

            result = {
                "round": round_number,
                "loss": loss,
                "metrics": metrics,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self._state.evaluation_results.append(result)

            if "accuracy" in metrics:
                self._metrics.global_accuracy = metrics["accuracy"]
                self._metrics.accuracy_history.append(metrics["accuracy"])
                if metrics["accuracy"] > self._metrics.best_accuracy:
                    self._metrics.best_accuracy = metrics["accuracy"]

            # Fire evaluation callbacks
            for callback in self._callbacks["on_evaluation"]:
                try:
                    await callback(round_number, result)
                except Exception as e:
                    logger.error(f"Evaluation callback error: {e}")

            return result

        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return None

    async def train(
        self,
        num_rounds: Optional[int] = None,
    ) -> FederatedMetrics:
        """
        Run federated training for specified number of rounds.

        تشغيل التدريب الموحد لعدد محدد من الجولات.

        Args:
            num_rounds: Number of rounds (uses config if not provided)

        Returns:
            Training metrics
        """
        self._state.is_running = True
        self._state.started_at = datetime.now(timezone.utc)
        self._metrics.started_at = datetime.now(timezone.utc)

        total_rounds = num_rounds or self.config.total_rounds
        self._state.total_rounds = total_rounds

        logger.info(f"Starting federated training: {total_rounds} rounds")

        try:
            for round_num in range(1, total_rounds + 1):
                self._state.current_round = round_num

                # Run round
                result = await self._run_round(round_num)
                self._state.round_results.append(result)

                # Log progress
                if result.status == RoundStatus.COMPLETED:
                    logger.info(
                        f"Round {round_num}/{total_rounds}: "
                        f"loss={result.aggregated_loss:.4f}, "
                        f"clients={len(result.participating_clients)}"
                    )
                else:
                    logger.warning(
                        f"Round {round_num}/{total_rounds} failed: "
                        f"{result.error_message}"
                    )

                # Evaluation
                if (
                    round_num % self.config.evaluate_every == 0
                    and result.status == RoundStatus.COMPLETED
                ):
                    eval_result = await self._evaluate(round_num)
                    if eval_result:
                        logger.info(
                            f"Evaluation: loss={eval_result['loss']:.4f}"
                        )

                # Checkpointing
                if (
                    round_num % self.config.checkpoint_every == 0
                    and result.status == RoundStatus.COMPLETED
                ):
                    await self._save_checkpoint(round_num)

                # Early stopping
                if self.config.early_stopping_rounds > 0:
                    if self._check_early_stopping():
                        logger.info(f"Early stopping at round {round_num}")
                        break

        finally:
            self._state.is_running = False
            self._state.completed_at = datetime.now(timezone.utc)
            self._metrics.last_updated = datetime.now(timezone.utc)

            # Fire training complete callbacks
            for callback in self._callbacks["on_training_complete"]:
                try:
                    await callback(self._metrics)
                except Exception as e:
                    logger.error(f"Training complete callback error: {e}")

        logger.info(
            f"Training completed: "
            f"rounds={self._metrics.current_round}, "
            f"best_loss={self._metrics.best_loss:.4f}"
        )

        return self._metrics

    def _check_early_stopping(self) -> bool:
        """Check if early stopping should trigger."""
        if len(self._metrics.loss_history) < self.config.early_stopping_rounds:
            return False

        recent = self._metrics.loss_history[-self.config.early_stopping_rounds:]
        improvement = recent[0] - min(recent)

        return improvement < self.config.early_stopping_threshold

    # =========================================================================
    # Checkpointing
    # =========================================================================

    async def _save_checkpoint(self, round_number: int) -> str:
        """Save training checkpoint."""
        checkpoint = {
            "round": round_number,
            "config": self.config.to_dict(),
            "global_model": self._server.global_model,
            "metrics": self._metrics.to_dict(),
            "state": {
                "current_round": self._state.current_round,
                "evaluation_results": self._state.evaluation_results,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        path = os.path.join(
            self.checkpoint_dir,
            f"coordinator_{self.config.job_id}_r{round_number}.pkl",
        )

        with open(path, "wb") as f:
            pickle.dump(checkpoint, f)

        logger.info(f"Saved checkpoint: {path}")
        return path

    async def load_checkpoint(self, checkpoint_path: str) -> bool:
        """Load from checkpoint."""
        try:
            with open(checkpoint_path, "rb") as f:
                checkpoint = pickle.load(f)

            # Restore state
            self._state.current_round = checkpoint["state"]["current_round"]
            self._state.evaluation_results = checkpoint["state"]["evaluation_results"]

            # Restore server model
            if checkpoint["global_model"]:
                await self._server.initialize_model(
                    checkpoint["global_model"].weights
                )

            logger.info(
                f"Loaded checkpoint from round {checkpoint['round']}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False

    # =========================================================================
    # Callbacks
    # =========================================================================

    def on_round_start(self, callback: Callable) -> None:
        """Register round start callback."""
        self._callbacks["on_round_start"].append(callback)

    def on_round_end(self, callback: Callable) -> None:
        """Register round end callback."""
        self._callbacks["on_round_end"].append(callback)

    def on_evaluation(self, callback: Callable) -> None:
        """Register evaluation callback."""
        self._callbacks["on_evaluation"].append(callback)

    def on_training_complete(self, callback: Callable) -> None:
        """Register training complete callback."""
        self._callbacks["on_training_complete"].append(callback)

    # =========================================================================
    # Status
    # =========================================================================

    async def get_status(self) -> Dict[str, Any]:
        """Get coordinator status."""
        return {
            "job_id": self.config.job_id,
            "is_running": self._state.is_running,
            "current_round": self._state.current_round,
            "total_rounds": self._state.total_rounds,
            "total_clients": self._metrics.total_clients,
            "active_clients": self._metrics.active_clients,
            "global_loss": self._metrics.global_loss,
            "best_loss": self._metrics.best_loss,
            "best_round": self._metrics.best_round,
            "started_at": (
                self._state.started_at.isoformat()
                if self._state.started_at else None
            ),
            "completed_at": (
                self._state.completed_at.isoformat()
                if self._state.completed_at else None
            ),
        }

    async def get_round_history(self) -> List[Dict[str, Any]]:
        """Get round history."""
        return [r.to_dict() for r in self._state.round_results]


# =============================================================================
# Coordinator Factory
# =============================================================================


def create_coordinator(
    model_name: str,
    total_rounds: int,
    initial_weights: Optional[Dict[str, np.ndarray]] = None,
    aggregation_strategy: AggregationStrategy = AggregationStrategy.FEDAVG,
    selection_strategy: SelectionStrategy = SelectionStrategy.RANDOM,
    evaluation_fn: Optional[EvaluationFn] = None,
    **kwargs,
) -> FederatedCoordinator:
    """
    Create a federated learning coordinator.

    Args:
        model_name: Name of the model
        total_rounds: Total number of training rounds
        initial_weights: Initial model weights
        aggregation_strategy: Aggregation strategy
        selection_strategy: Client selection strategy
        evaluation_fn: Evaluation function
        **kwargs: Additional configuration options

    Returns:
        Configured coordinator
    """
    config = FederatedConfig(
        job_id=kwargs.get("job_id", ""),
        model_name=model_name,
        total_rounds=total_rounds,
        aggregation_strategy=aggregation_strategy,
        selection_strategy=selection_strategy,
        **{
            k: v for k, v in kwargs.items()
            if k in FederatedConfig.__dataclass_fields__
        },
    )

    return FederatedCoordinator(
        config=config,
        initial_weights=initial_weights,
        evaluation_fn=evaluation_fn,
        checkpoint_dir=kwargs.get("checkpoint_dir", "/tmp/federated"),
    )
