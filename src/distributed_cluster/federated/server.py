# -*- coding: utf-8 -*-
"""
Federated Learning Server - خادم التعلم الموحد
==============================================

Server-side implementation for federated learning.

تنفيذ جانب الخادم للتعلم الموحد:
- تنسيق جولات التدريب
- تجميع تحديثات العملاء
- إدارة النموذج العالمي
- التقييم والنقاط المرجعية
"""

from __future__ import annotations

import asyncio
import logging
import os
import pickle
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from distributed_cluster.federated.aggregator import create_aggregator
from distributed_cluster.federated.models import (
    AggregationStrategy,
    ClientInfo,
    ClientStatus,
    ClientUpdate,
    FederatedConfig,
    FederatedMetrics,
    ModelWeights,
    RoundConfig,
    RoundResult,
    RoundStatus,
    SelectionStrategy,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Server State
# =============================================================================


@dataclass
class ServerState:
    """Internal server state."""
    current_round: int = 0
    status: str = "idle"
    is_training: bool = False
    global_model: Optional[ModelWeights] = None
    best_model: Optional[ModelWeights] = None
    best_loss: float = float("inf")
    round_history: List[RoundResult] = field(default_factory=list)
    registered_clients: Dict[str, ClientInfo] = field(default_factory=dict)
    pending_updates: Dict[int, List[ClientUpdate]] = field(default_factory=dict)


# =============================================================================
# Federated Learning Server
# =============================================================================


class FederatedServer:
    """
    Federated Learning Server.

    خادم التعلم الموحد.

    Features:
    - Round-based training coordination
    - Multiple aggregation strategies
    - Client selection and management
    - Privacy mechanisms
    - Model checkpointing
    - Evaluation and monitoring
    """

    def __init__(
        self,
        config: FederatedConfig,
        initial_weights: Optional[Dict[str, np.ndarray]] = None,
        checkpoint_dir: str = "/tmp/federated",
    ):
        """
        Initialize federated learning server.

        Args:
            config: Federated learning configuration
            initial_weights: Initial model weights
            checkpoint_dir: Directory for checkpoints
        """
        self.config = config
        self.checkpoint_dir = checkpoint_dir

        # Initialize state
        self._state = ServerState()
        if initial_weights:
            self._state.global_model = ModelWeights(weights=initial_weights)

        # Create aggregator
        self._aggregator = create_aggregator(
            config.aggregation_strategy,
            server_lr=config.global_learning_rate,
        )

        # Metrics
        self._metrics = FederatedMetrics(
            job_id=config.job_id,
            total_rounds=config.total_rounds,
        )

        # Locks
        self._lock = asyncio.Lock()
        self._round_lock = asyncio.Lock()

        # Callbacks
        self._callbacks: Dict[str, List[Callable]] = {
            "on_round_start": [],
            "on_round_end": [],
            "on_training_complete": [],
        }

        # Create checkpoint directory
        os.makedirs(checkpoint_dir, exist_ok=True)

        logger.info(f"Initialized federated server: {config.job_id}")

    @property
    def current_round(self) -> int:
        return self._state.current_round

    @property
    def is_training(self) -> bool:
        return self._state.is_training

    @property
    def global_model(self) -> Optional[ModelWeights]:
        return self._state.global_model

    @property
    def metrics(self) -> FederatedMetrics:
        return self._metrics

    # =========================================================================
    # Client Management
    # =========================================================================

    async def register_client(self, client_info: ClientInfo) -> bool:
        """
        Register a client with the server.

        تسجيل عميل مع الخادم.
        """
        async with self._lock:
            self._state.registered_clients[client_info.client_id] = client_info
            self._metrics.total_clients = len(self._state.registered_clients)
            logger.info(f"Registered client: {client_info.client_id}")
            return True

    async def unregister_client(self, client_id: str) -> bool:
        """Unregister a client."""
        async with self._lock:
            if client_id in self._state.registered_clients:
                del self._state.registered_clients[client_id]
                self._metrics.total_clients = len(self._state.registered_clients)
                logger.info(f"Unregistered client: {client_id}")
                return True
            return False

    async def update_client_heartbeat(
        self,
        client_id: str,
        status: Optional[ClientStatus] = None,
    ) -> bool:
        """Update client heartbeat."""
        async with self._lock:
            if client_id in self._state.registered_clients:
                client = self._state.registered_clients[client_id]
                client.last_heartbeat = datetime.now(timezone.utc)
                if status:
                    client.status = status
                return True
            return False

    async def get_available_clients(self) -> List[ClientInfo]:
        """Get list of available clients."""
        now = datetime.now(timezone.utc)
        available = []

        for client in self._state.registered_clients.values():
            if client.status != ClientStatus.IDLE:
                continue
            if client.last_heartbeat is None:
                continue
            delta = now - client.last_heartbeat
            if delta.total_seconds() < 60:  # 60s timeout
                available.append(client)

        return available

    # =========================================================================
    # Model Management
    # =========================================================================

    async def initialize_model(self, weights: Dict[str, np.ndarray]) -> None:
        """Initialize global model weights."""
        async with self._lock:
            self._state.global_model = ModelWeights(weights=weights)
            logger.info("Initialized global model")

    async def get_global_model(self) -> Optional[ModelWeights]:
        """Get current global model."""
        return self._state.global_model

    async def save_checkpoint(
        self,
        round_number: Optional[int] = None,
    ) -> str:
        """
        Save model checkpoint.

        حفظ نقطة تفتيش للنموذج.
        """
        round_num = round_number or self._state.current_round

        checkpoint = {
            "round": round_num,
            "global_model": self._state.global_model,
            "best_model": self._state.best_model,
            "best_loss": self._state.best_loss,
            "config": self.config.to_dict(),
            "metrics": self._metrics.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        checkpoint_path = os.path.join(
            self.checkpoint_dir,
            f"checkpoint_{self.config.job_id}_r{round_num}.pkl"
        )

        with open(checkpoint_path, "wb") as f:
            pickle.dump(checkpoint, f)

        logger.info(f"Saved checkpoint: {checkpoint_path}")
        return checkpoint_path

    async def load_checkpoint(self, checkpoint_path: str) -> bool:
        """Load model from checkpoint."""
        try:
            with open(checkpoint_path, "rb") as f:
                checkpoint = pickle.load(f)

            self._state.global_model = checkpoint["global_model"]
            self._state.best_model = checkpoint.get("best_model")
            self._state.best_loss = checkpoint.get("best_loss", float("inf"))
            self._state.current_round = checkpoint["round"]

            logger.info(f"Loaded checkpoint from round {checkpoint['round']}")
            return True
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False

    # =========================================================================
    # Training Round Management
    # =========================================================================

    async def select_clients(
        self,
        round_config: RoundConfig,
    ) -> List[str]:
        """
        Select clients for a training round.

        اختيار العملاء لجولة تدريب.
        """
        available = await self.get_available_clients()

        if len(available) < round_config.min_clients:
            logger.warning(
                f"Not enough clients available: "
                f"{len(available)} < {round_config.min_clients}"
            )
            return []

        # Calculate number of clients to select
        num_to_select = max(
            round_config.min_clients,
            int(len(available) * round_config.client_fraction)
        )
        num_to_select = min(num_to_select, round_config.max_clients, len(available))

        # Selection based on strategy
        if round_config.selection_strategy == SelectionStrategy.RANDOM:
            indices = np.random.choice(
                len(available),
                size=num_to_select,
                replace=False,
            )
            selected = [available[i].client_id for i in indices]

        elif round_config.selection_strategy == SelectionStrategy.ROUND_ROBIN:
            # Sort by last participation round
            sorted_clients = sorted(
                available,
                key=lambda c: c.last_participation_round,
            )
            selected = [c.client_id for c in sorted_clients[:num_to_select]]

        elif round_config.selection_strategy == SelectionStrategy.RESOURCE_AWARE:
            # Select clients with most resources
            sorted_clients = sorted(
                available,
                key=lambda c: (
                    c.available_resources.get("cpu", 0)
                    if c.available_resources else 0
                ),
                reverse=True,
            )
            selected = [c.client_id for c in sorted_clients[:num_to_select]]

        elif round_config.selection_strategy == SelectionStrategy.DATA_QUALITY:
            # Select clients with highest contribution score
            sorted_clients = sorted(
                available,
                key=lambda c: c.contribution_score,
                reverse=True,
            )
            selected = [c.client_id for c in sorted_clients[:num_to_select]]

        elif round_config.selection_strategy == SelectionStrategy.CONTRIBUTION_BASED:
            # Weighted selection by contribution and data size
            weights = np.array([
                c.dataset_size * c.contribution_score
                for c in available
            ])
            weights = weights / weights.sum() if weights.sum() > 0 else None

            indices = np.random.choice(
                len(available),
                size=num_to_select,
                replace=False,
                p=weights,
            )
            selected = [available[i].client_id for i in indices]

        else:
            # Default to random
            indices = np.random.choice(
                len(available),
                size=num_to_select,
                replace=False,
            )
            selected = [available[i].client_id for i in indices]

        logger.info(f"Selected {len(selected)} clients for round {round_config.round_number}")
        return selected

    async def distribute_model(
        self,
        client_ids: List[str],
    ) -> Dict[str, ModelWeights]:
        """
        Prepare model for distribution to selected clients.

        تجهيز النموذج للتوزيع على العملاء المختارين.
        """
        if self._state.global_model is None:
            raise ValueError("No global model initialized")

        # In a real system, this would send the model to clients
        # Here we just return the model for each client
        return {
            client_id: self._state.global_model
            for client_id in client_ids
        }

    async def submit_update(
        self,
        update: ClientUpdate,
    ) -> bool:
        """
        Submit a client update for the current round.

        تقديم تحديث العميل للجولة الحالية.
        """
        async with self._lock:
            round_num = update.round_number

            if round_num not in self._state.pending_updates:
                self._state.pending_updates[round_num] = []

            self._state.pending_updates[round_num].append(update)

            # Update client info
            if update.client_id in self._state.registered_clients:
                client = self._state.registered_clients[update.client_id]
                client.last_participation_round = round_num
                client.total_rounds_participated += 1
                client.status = ClientStatus.IDLE

            logger.debug(
                f"Received update from {update.client_id} for round {round_num}"
            )
            return True

    async def aggregate_round(
        self,
        round_number: int,
    ) -> Optional[ModelWeights]:
        """
        Aggregate updates for a round.

        تجميع تحديثات الجولة.
        """
        async with self._round_lock:
            updates = self._state.pending_updates.get(round_number, [])

            if not updates:
                logger.warning(f"No updates for round {round_number}")
                return None

            # Check minimum update ratio
            min_updates = int(
                len(self._state.registered_clients) * self.config.min_update_ratio
            )
            if len(updates) < min_updates:
                logger.warning(
                    f"Not enough updates: {len(updates)} < {min_updates}"
                )
                return None

            start_time = time.time()

            # Aggregate using configured strategy
            aggregated = await self._aggregator.aggregate(
                self._state.global_model,
                updates,
            )

            aggregation_time = time.time() - start_time

            # Update global model
            self._state.global_model = aggregated

            # Calculate aggregated metrics
            total_samples = sum(u.num_samples for u in updates)
            avg_loss = sum(
                u.training_loss * u.num_samples for u in updates
            ) / total_samples if total_samples > 0 else 0.0

            # Update best model
            if avg_loss < self._state.best_loss:
                self._state.best_loss = avg_loss
                self._state.best_model = aggregated
                self._metrics.best_loss = avg_loss
                self._metrics.best_round = round_number

            # Update metrics
            self._metrics.global_loss = avg_loss
            self._metrics.total_samples_trained += total_samples
            self._metrics.loss_history.append(avg_loss)

            # Clean up
            del self._state.pending_updates[round_number]

            logger.info(
                f"Aggregated round {round_number}: "
                f"loss={avg_loss:.4f}, clients={len(updates)}, "
                f"time={aggregation_time:.2f}s"
            )

            return aggregated

    async def run_round(
        self,
        round_number: Optional[int] = None,
        selected_clients: Optional[List[str]] = None,
        updates: Optional[List[ClientUpdate]] = None,
    ) -> RoundResult:
        """
        Run a complete federated learning round.

        تشغيل جولة تعلم موحد كاملة.

        This is a higher-level method that coordinates the entire round.

        Args:
            round_number: Round number (auto-increments if not provided)
            selected_clients: Pre-selected clients (selects if not provided)
            updates: Pre-collected updates (collects if not provided)

        Returns:
            Round result with metrics
        """
        async with self._round_lock:
            round_num = round_number or (self._state.current_round + 1)
            self._state.current_round = round_num

            round_config = RoundConfig(
                round_number=round_num,
                min_clients=self.config.min_clients,
                max_clients=self.config.max_clients,
                client_fraction=self.config.client_fraction,
                local_epochs=self.config.local_epochs,
                local_batch_size=self.config.local_batch_size,
                learning_rate=self.config.client_learning_rate,
                aggregation_strategy=self.config.aggregation_strategy,
                selection_strategy=self.config.selection_strategy,
                timeout_seconds=self.config.round_timeout,
                min_update_ratio=self.config.min_update_ratio,
            )

            result = RoundResult(
                round_number=round_num,
                status=RoundStatus.PENDING,
                started_at=datetime.now(timezone.utc),
            )

            start_time = time.time()

            # Fire round start callbacks
            for callback in self._callbacks["on_round_start"]:
                try:
                    await callback(round_num, round_config)
                except Exception as e:
                    logger.error(f"Round start callback error: {e}")

            try:
                # Client selection
                result.status = RoundStatus.CLIENT_SELECTION
                if selected_clients is None:
                    selected_clients = await self.select_clients(round_config)

                result.selected_clients = selected_clients

                if len(selected_clients) < round_config.min_clients:
                    result.status = RoundStatus.FAILED
                    result.error_message = "Not enough clients available"
                    return result

                # Distribution (in real system, would send to clients)
                result.status = RoundStatus.DISTRIBUTING

                # Wait for updates or use provided ones
                result.status = RoundStatus.TRAINING

                if updates:
                    # Use provided updates
                    for update in updates:
                        await self.submit_update(update)

                # Aggregation
                result.status = RoundStatus.AGGREGATING

                aggregated = await self.aggregate_round(round_num)

                if aggregated is None:
                    result.status = RoundStatus.FAILED
                    result.error_message = "Aggregation failed"
                    return result

                # Success
                result.status = RoundStatus.COMPLETED
                result.global_model = aggregated
                result.participating_clients = [
                    u.client_id
                    for u in self._state.pending_updates.get(round_num, [])
                ]
                result.dropped_clients = [
                    c for c in selected_clients
                    if c not in result.participating_clients
                ]
                result.aggregated_loss = self._metrics.global_loss

            except Exception as e:
                result.status = RoundStatus.FAILED
                result.error_message = str(e)
                logger.error(f"Round {round_num} failed: {e}")

            finally:
                result.completed_at = datetime.now(timezone.utc)
                result.round_duration = time.time() - start_time
                self._state.round_history.append(result)
                self._metrics.current_round = round_num
                self._metrics.last_updated = datetime.now(timezone.utc)

            # Fire round end callbacks
            for callback in self._callbacks["on_round_end"]:
                try:
                    await callback(round_num, result)
                except Exception as e:
                    logger.error(f"Round end callback error: {e}")

            # Checkpointing
            if (
                round_num % self.config.checkpoint_every == 0
                and result.status == RoundStatus.COMPLETED
            ):
                await self.save_checkpoint(round_num)

            return result

    async def train(
        self,
        num_rounds: Optional[int] = None,
        client_updates_provider: Optional[
            Callable[[int, List[str], ModelWeights], List[ClientUpdate]]
        ] = None,
    ) -> FederatedMetrics:
        """
        Run complete federated training.

        تشغيل التدريب الموحد الكامل.

        Args:
            num_rounds: Number of rounds (uses config if not provided)
            client_updates_provider: Function to get client updates

        Returns:
            Final training metrics
        """
        self._state.is_training = True
        self._metrics.started_at = datetime.now(timezone.utc)
        total_rounds = num_rounds or self.config.total_rounds

        logger.info(f"Starting federated training for {total_rounds} rounds")

        try:
            for round_num in range(1, total_rounds + 1):
                self._state.current_round = round_num

                # Select clients
                round_config = RoundConfig(
                    round_number=round_num,
                    min_clients=self.config.min_clients,
                    max_clients=self.config.max_clients,
                    client_fraction=self.config.client_fraction,
                    local_epochs=self.config.local_epochs,
                    local_batch_size=self.config.local_batch_size,
                    learning_rate=self.config.client_learning_rate,
                    aggregation_strategy=self.config.aggregation_strategy,
                    selection_strategy=self.config.selection_strategy,
                )

                selected = await self.select_clients(round_config)

                if len(selected) < round_config.min_clients:
                    logger.warning(f"Skipping round {round_num}: not enough clients")
                    continue

                # Get client updates
                updates = None
                if client_updates_provider:
                    updates = await client_updates_provider(
                        round_num,
                        selected,
                        self._state.global_model,
                    )

                # Run round
                result = await self.run_round(
                    round_number=round_num,
                    selected_clients=selected,
                    updates=updates,
                )

                if result.status != RoundStatus.COMPLETED:
                    logger.warning(f"Round {round_num} did not complete successfully")

                # Early stopping check
                if self.config.early_stopping_rounds > 0:
                    if self._check_early_stopping():
                        logger.info("Early stopping triggered")
                        break

        finally:
            self._state.is_training = False
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

        recent_losses = self._metrics.loss_history[-self.config.early_stopping_rounds:]
        improvement = recent_losses[0] - min(recent_losses)

        return improvement < self.config.early_stopping_threshold

    # =========================================================================
    # Callbacks
    # =========================================================================

    def on_round_start(self, callback: Callable) -> None:
        """Register round start callback."""
        self._callbacks["on_round_start"].append(callback)

    def on_round_end(self, callback: Callable) -> None:
        """Register round end callback."""
        self._callbacks["on_round_end"].append(callback)

    def on_training_complete(self, callback: Callable) -> None:
        """Register training complete callback."""
        self._callbacks["on_training_complete"].append(callback)

    # =========================================================================
    # Status and Metrics
    # =========================================================================

    async def get_status(self) -> Dict[str, Any]:
        """Get server status."""
        return {
            "job_id": self.config.job_id,
            "status": "training" if self._state.is_training else "idle",
            "current_round": self._state.current_round,
            "total_rounds": self.config.total_rounds,
            "registered_clients": len(self._state.registered_clients),
            "global_model_version": (
                self._state.global_model.version
                if self._state.global_model else None
            ),
            "best_loss": self._state.best_loss,
            "metrics": self._metrics.to_dict(),
        }

    async def get_round_history(self) -> List[Dict[str, Any]]:
        """Get round history."""
        return [r.to_dict() for r in self._state.round_history]


# =============================================================================
# Server Factory
# =============================================================================


def create_server(
    model_name: str,
    total_rounds: int,
    initial_weights: Optional[Dict[str, np.ndarray]] = None,
    aggregation_strategy: AggregationStrategy = AggregationStrategy.FEDAVG,
    **kwargs,
) -> FederatedServer:
    """
    Create a federated learning server.

    Args:
        model_name: Name of the model
        total_rounds: Total number of training rounds
        initial_weights: Initial model weights
        aggregation_strategy: Aggregation strategy
        **kwargs: Additional configuration options

    Returns:
        Configured federated server
    """
    config = FederatedConfig(
        job_id=kwargs.get("job_id", f"fl-{uuid.uuid4().hex[:8]}"),
        model_name=model_name,
        total_rounds=total_rounds,
        aggregation_strategy=aggregation_strategy,
        **{k: v for k, v in kwargs.items() if k in FederatedConfig.__dataclass_fields__},
    )

    return FederatedServer(
        config=config,
        initial_weights=initial_weights,
        checkpoint_dir=kwargs.get("checkpoint_dir", "/tmp/federated"),
    )
