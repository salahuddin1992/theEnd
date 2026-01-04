# -*- coding: utf-8 -*-
"""
Federated Learning Aggregators - مجمعات التعلم الموحد
======================================================

Aggregation strategies for federated learning.

استراتيجيات التجميع للتعلم الموحد:
- FedAvg: المتوسط الموحد
- FedProx: مع الحد التقريبي
- FedYogi/FedAdam: المحسنات التكيفية
- SCAFFOLD: تقليل التباين
- Byzantine-robust: مقاومة الهجمات
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np

from distributed_cluster.federated.models import (
    AggregationStrategy,
    ClientUpdate,
    ModelWeights,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Base Aggregator
# =============================================================================


class Aggregator(ABC):
    """
    Base class for federated learning aggregators.

    الفئة الأساسية لمجمعات التعلم الموحد.
    """

    def __init__(self, **kwargs):
        self.config = kwargs
        self._state: Dict[str, Any] = {}

    @abstractmethod
    async def aggregate(
        self,
        global_weights: ModelWeights,
        client_updates: List[ClientUpdate],
    ) -> ModelWeights:
        """
        Aggregate client updates into a new global model.

        Args:
            global_weights: Current global model weights
            client_updates: List of client model updates

        Returns:
            New aggregated global model weights
        """
        pass

    def reset_state(self) -> None:
        """Reset aggregator state."""
        self._state = {}

    def get_state(self) -> Dict[str, Any]:
        """Get aggregator state."""
        return self._state.copy()


# =============================================================================
# FedAvg Aggregator
# =============================================================================


class FedAvgAggregator(Aggregator):
    """
    Federated Averaging (FedAvg) aggregator.

    المتوسط الموحد - الخوارزمية الأساسية للتعلم الموحد.

    Reference: McMahan et al., "Communication-Efficient Learning of Deep Networks
    from Decentralized Data" (2017)
    """

    def __init__(
        self,
        weighted: bool = True,
        **kwargs,
    ):
        """
        Initialize FedAvg aggregator.

        Args:
            weighted: Weight updates by number of samples (True) or equal weight (False)
        """
        super().__init__(**kwargs)
        self.weighted = weighted

    async def aggregate(
        self,
        global_weights: ModelWeights,
        client_updates: List[ClientUpdate],
    ) -> ModelWeights:
        """Aggregate using federated averaging."""
        if not client_updates:
            return global_weights

        # Calculate weights for each client
        if self.weighted:
            total_samples = sum(u.num_samples for u in client_updates)
            weights = [u.num_samples / total_samples for u in client_updates]
        else:
            weights = [1.0 / len(client_updates)] * len(client_updates)

        # Aggregate weights
        aggregated = {}
        for key in global_weights.weights.keys():
            weighted_sum = np.zeros_like(global_weights.weights[key])
            for update, weight in zip(client_updates, weights):
                if key in update.model_weights.weights:
                    weighted_sum += weight * update.model_weights.weights[key]
            aggregated[key] = weighted_sum

        return ModelWeights(
            weights=aggregated,
            version=global_weights.version + 1,
        )


# =============================================================================
# FedProx Aggregator
# =============================================================================


class FedProxAggregator(Aggregator):
    """
    FedProx aggregator with proximal term.

    مجمع FedProx مع الحد التقريبي لمعالجة عدم التجانس.

    Reference: Li et al., "Federated Optimization in Heterogeneous Networks" (2020)
    """

    def __init__(
        self,
        mu: float = 0.01,
        weighted: bool = True,
        **kwargs,
    ):
        """
        Initialize FedProx aggregator.

        Args:
            mu: Proximal term coefficient
            weighted: Weight updates by number of samples
        """
        super().__init__(**kwargs)
        self.mu = mu
        self.weighted = weighted

    async def aggregate(
        self,
        global_weights: ModelWeights,
        client_updates: List[ClientUpdate],
    ) -> ModelWeights:
        """Aggregate using FedProx (same as FedAvg at aggregation time)."""
        # Note: The proximal term is applied during local training, not aggregation
        # The aggregation is the same as FedAvg
        if not client_updates:
            return global_weights

        if self.weighted:
            total_samples = sum(u.num_samples for u in client_updates)
            weights = [u.num_samples / total_samples for u in client_updates]
        else:
            weights = [1.0 / len(client_updates)] * len(client_updates)

        aggregated = {}
        for key in global_weights.weights.keys():
            weighted_sum = np.zeros_like(global_weights.weights[key])
            for update, weight in zip(client_updates, weights):
                if key in update.model_weights.weights:
                    weighted_sum += weight * update.model_weights.weights[key]
            aggregated[key] = weighted_sum

        return ModelWeights(
            weights=aggregated,
            version=global_weights.version + 1,
        )


# =============================================================================
# Adaptive Optimizers (FedYogi, FedAdam)
# =============================================================================


class FedAdaptiveAggregator(Aggregator):
    """
    Base class for adaptive federated optimizers.

    الفئة الأساسية للمحسنات الموحدة التكيفية.
    """

    def __init__(
        self,
        server_lr: float = 1.0,
        beta1: float = 0.9,
        beta2: float = 0.99,
        epsilon: float = 1e-3,
        tau: float = 1e-3,
        weighted: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.server_lr = server_lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.epsilon = epsilon
        self.tau = tau
        self.weighted = weighted

    def _compute_pseudo_gradient(
        self,
        global_weights: ModelWeights,
        client_updates: List[ClientUpdate],
    ) -> Dict[str, np.ndarray]:
        """Compute pseudo-gradient from client updates."""
        if self.weighted:
            total_samples = sum(u.num_samples for u in client_updates)
            weights = [u.num_samples / total_samples for u in client_updates]
        else:
            weights = [1.0 / len(client_updates)] * len(client_updates)

        # Compute weighted average of updates
        avg_update = {}
        for key in global_weights.weights.keys():
            weighted_sum = np.zeros_like(global_weights.weights[key])
            for update, weight in zip(client_updates, weights):
                if key in update.model_weights.weights:
                    weighted_sum += weight * update.model_weights.weights[key]
            avg_update[key] = weighted_sum

        # Pseudo-gradient = global - averaged_update
        pseudo_grad = {}
        for key in global_weights.weights.keys():
            pseudo_grad[key] = global_weights.weights[key] - avg_update[key]

        return pseudo_grad


class FedAdamAggregator(FedAdaptiveAggregator):
    """
    FedAdam aggregator with adaptive learning rate.

    مجمع FedAdam مع معدل تعلم تكيفي.

    Reference: Reddi et al., "Adaptive Federated Optimization" (2021)
    """

    async def aggregate(
        self,
        global_weights: ModelWeights,
        client_updates: List[ClientUpdate],
    ) -> ModelWeights:
        """Aggregate using FedAdam."""
        if not client_updates:
            return global_weights

        # Initialize momentum if needed
        if "m" not in self._state:
            self._state["m"] = {
                k: np.zeros_like(v) for k, v in global_weights.weights.items()
            }
            self._state["v"] = {
                k: np.zeros_like(v) for k, v in global_weights.weights.items()
            }
            self._state["t"] = 0

        self._state["t"] += 1
        t = self._state["t"]

        # Compute pseudo-gradient
        pseudo_grad = self._compute_pseudo_gradient(global_weights, client_updates)

        # Update momentum and adaptive terms
        aggregated = {}
        for key in global_weights.weights.keys():
            g = pseudo_grad[key]

            # Update biased first moment estimate
            self._state["m"][key] = (
                self.beta1 * self._state["m"][key] + (1 - self.beta1) * g
            )

            # Update biased second moment estimate
            self._state["v"][key] = (
                self.beta2 * self._state["v"][key] + (1 - self.beta2) * (g ** 2)
            )

            # Bias correction
            m_hat = self._state["m"][key] / (1 - self.beta1 ** t)
            v_hat = self._state["v"][key] / (1 - self.beta2 ** t)

            # Update parameters
            aggregated[key] = (
                global_weights.weights[key]
                - self.server_lr * m_hat / (np.sqrt(v_hat) + self.epsilon)
            )

        return ModelWeights(
            weights=aggregated,
            version=global_weights.version + 1,
        )


class FedYogiAggregator(FedAdaptiveAggregator):
    """
    FedYogi aggregator with improved adaptive learning.

    مجمع FedYogi مع تعلم تكيفي محسن.

    Reference: Reddi et al., "Adaptive Federated Optimization" (2021)
    """

    async def aggregate(
        self,
        global_weights: ModelWeights,
        client_updates: List[ClientUpdate],
    ) -> ModelWeights:
        """Aggregate using FedYogi."""
        if not client_updates:
            return global_weights

        # Initialize state if needed
        if "m" not in self._state:
            self._state["m"] = {
                k: np.zeros_like(v) for k, v in global_weights.weights.items()
            }
            self._state["v"] = {
                k: self.tau ** 2 * np.ones_like(v)
                for k, v in global_weights.weights.items()
            }
            self._state["t"] = 0

        self._state["t"] += 1

        # Compute pseudo-gradient
        pseudo_grad = self._compute_pseudo_gradient(global_weights, client_updates)

        # Update with Yogi update rule
        aggregated = {}
        for key in global_weights.weights.keys():
            g = pseudo_grad[key]

            # Update first moment
            self._state["m"][key] = (
                self.beta1 * self._state["m"][key] + (1 - self.beta1) * g
            )

            # Yogi update for second moment (key difference from Adam)
            g_squared = g ** 2
            sign = np.sign(g_squared - self._state["v"][key])
            self._state["v"][key] = (
                self._state["v"][key]
                + (1 - self.beta2) * sign * g_squared
            )

            # Update parameters
            aggregated[key] = (
                global_weights.weights[key]
                - self.server_lr
                * self._state["m"][key]
                / (np.sqrt(self._state["v"][key]) + self.epsilon)
            )

        return ModelWeights(
            weights=aggregated,
            version=global_weights.version + 1,
        )


# =============================================================================
# SCAFFOLD Aggregator
# =============================================================================


@dataclass
class ScaffoldState:
    """State for SCAFFOLD aggregator."""
    server_control: Dict[str, np.ndarray]
    client_controls: Dict[str, Dict[str, np.ndarray]]


class ScaffoldAggregator(Aggregator):
    """
    SCAFFOLD aggregator for variance reduction.

    مجمع SCAFFOLD لتقليل التباين في التعلم الموحد.

    Reference: Karimireddy et al., "SCAFFOLD: Stochastic Controlled Averaging
    for Federated Learning" (2020)
    """

    def __init__(
        self,
        server_lr: float = 1.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.server_lr = server_lr

    async def aggregate(
        self,
        global_weights: ModelWeights,
        client_updates: List[ClientUpdate],
    ) -> ModelWeights:
        """Aggregate using SCAFFOLD."""
        if not client_updates:
            return global_weights

        # Initialize control variates if needed
        if "server_control" not in self._state:
            self._state["server_control"] = {
                k: np.zeros_like(v) for k, v in global_weights.weights.items()
            }
            self._state["client_controls"] = {}

        num_clients = len(client_updates)

        # Aggregate model updates (standard FedAvg)
        total_samples = sum(u.num_samples for u in client_updates)
        aggregated = {}

        for key in global_weights.weights.keys():
            weighted_sum = np.zeros_like(global_weights.weights[key])
            for update in client_updates:
                weight = update.num_samples / total_samples
                if key in update.model_weights.weights:
                    weighted_sum += weight * update.model_weights.weights[key]
            aggregated[key] = weighted_sum

        # Update server control variate
        # Note: In full SCAFFOLD, clients send control variate updates
        # Here we use a simplified version
        for key in global_weights.weights.keys():
            delta = aggregated[key] - global_weights.weights[key]
            self._state["server_control"][key] += delta / num_clients

        return ModelWeights(
            weights=aggregated,
            version=global_weights.version + 1,
        )

    def get_server_control(self) -> Dict[str, np.ndarray]:
        """Get server control variate for clients."""
        return self._state.get("server_control", {})


# =============================================================================
# Byzantine-Robust Aggregators
# =============================================================================


class MedianAggregator(Aggregator):
    """
    Coordinate-wise median aggregator (Byzantine-robust).

    مجمع الوسيط لمقاومة الهجمات البيزنطية.

    Reference: Yin et al., "Byzantine-Robust Distributed Learning" (2018)
    """

    async def aggregate(
        self,
        global_weights: ModelWeights,
        client_updates: List[ClientUpdate],
    ) -> ModelWeights:
        """Aggregate using coordinate-wise median."""
        if not client_updates:
            return global_weights

        if len(client_updates) < 3:
            # Fall back to mean if too few clients
            logger.warning("Too few clients for median, using mean")
            total = sum(u.num_samples for u in client_updates)
            weights = [u.num_samples / total for u in client_updates]

            aggregated = {}
            for key in global_weights.weights.keys():
                weighted_sum = np.zeros_like(global_weights.weights[key])
                for update, weight in zip(client_updates, weights):
                    if key in update.model_weights.weights:
                        weighted_sum += weight * update.model_weights.weights[key]
                aggregated[key] = weighted_sum
        else:
            aggregated = {}
            for key in global_weights.weights.keys():
                # Stack all client weights
                stacked = np.stack([
                    u.model_weights.weights[key]
                    for u in client_updates
                    if key in u.model_weights.weights
                ])
                # Take coordinate-wise median
                aggregated[key] = np.median(stacked, axis=0)

        return ModelWeights(
            weights=aggregated,
            version=global_weights.version + 1,
        )


class TrimmedMeanAggregator(Aggregator):
    """
    Trimmed mean aggregator (Byzantine-robust).

    مجمع المتوسط المقطوع لمقاومة الهجمات البيزنطية.

    Reference: Yin et al., "Byzantine-Robust Distributed Learning" (2018)
    """

    def __init__(
        self,
        trim_ratio: float = 0.1,
        **kwargs,
    ):
        """
        Initialize trimmed mean aggregator.

        Args:
            trim_ratio: Fraction of extreme values to trim (0 to 0.5)
        """
        super().__init__(**kwargs)
        self.trim_ratio = min(0.5, max(0.0, trim_ratio))

    async def aggregate(
        self,
        global_weights: ModelWeights,
        client_updates: List[ClientUpdate],
    ) -> ModelWeights:
        """Aggregate using trimmed mean."""
        if not client_updates:
            return global_weights

        n_clients = len(client_updates)
        trim_count = int(n_clients * self.trim_ratio)

        if n_clients - 2 * trim_count < 1:
            # Not enough clients to trim, use regular mean
            logger.warning("Too few clients for trimming, using mean")
            trim_count = 0

        aggregated = {}
        for key in global_weights.weights.keys():
            # Stack all client weights
            stacked = np.stack([
                u.model_weights.weights[key]
                for u in client_updates
                if key in u.model_weights.weights
            ])

            if trim_count > 0:
                # Sort along client axis and trim extremes
                sorted_weights = np.sort(stacked, axis=0)
                trimmed = sorted_weights[trim_count:n_clients - trim_count]
                aggregated[key] = np.mean(trimmed, axis=0)
            else:
                aggregated[key] = np.mean(stacked, axis=0)

        return ModelWeights(
            weights=aggregated,
            version=global_weights.version + 1,
        )


class KrumAggregator(Aggregator):
    """
    Krum aggregator (Byzantine-robust).

    مجمع Krum لمقاومة الهجمات البيزنطية.

    Reference: Blanchard et al., "Machine Learning with Adversaries" (2017)
    """

    def __init__(
        self,
        num_byzantine: int = 0,
        multi_krum: bool = False,
        **kwargs,
    ):
        """
        Initialize Krum aggregator.

        Args:
            num_byzantine: Expected number of Byzantine clients
            multi_krum: Use Multi-Krum (average of best m clients)
        """
        super().__init__(**kwargs)
        self.num_byzantine = num_byzantine
        self.multi_krum = multi_krum

    def _flatten_weights(self, weights: Dict[str, np.ndarray]) -> np.ndarray:
        """Flatten weights dictionary to single vector."""
        return np.concatenate([v.flatten() for v in weights.values()])

    def _compute_distances(
        self,
        client_updates: List[ClientUpdate],
    ) -> np.ndarray:
        """Compute pairwise distances between client updates."""
        n = len(client_updates)
        flat_weights = [
            self._flatten_weights(u.model_weights.weights)
            for u in client_updates
        ]

        distances = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                dist = np.linalg.norm(flat_weights[i] - flat_weights[j])
                distances[i, j] = dist
                distances[j, i] = dist

        return distances

    async def aggregate(
        self,
        global_weights: ModelWeights,
        client_updates: List[ClientUpdate],
    ) -> ModelWeights:
        """Aggregate using Krum."""
        if not client_updates:
            return global_weights

        n = len(client_updates)
        f = self.num_byzantine

        if n < 2 * f + 3:
            logger.warning("Too few clients for Krum, using FedAvg")
            # Fall back to FedAvg
            total = sum(u.num_samples for u in client_updates)
            weights = [u.num_samples / total for u in client_updates]

            aggregated = {}
            for key in global_weights.weights.keys():
                weighted_sum = np.zeros_like(global_weights.weights[key])
                for update, weight in zip(client_updates, weights):
                    if key in update.model_weights.weights:
                        weighted_sum += weight * update.model_weights.weights[key]
                aggregated[key] = weighted_sum

            return ModelWeights(
                weights=aggregated,
                version=global_weights.version + 1,
            )

        # Compute pairwise distances
        distances = self._compute_distances(client_updates)

        # For each client, compute sum of distances to n-f-2 closest neighbors
        scores = []
        n_neighbors = n - f - 2
        for i in range(n):
            sorted_dists = np.sort(distances[i])
            # Exclude self (distance 0) and sum closest neighbors
            score = np.sum(sorted_dists[1:n_neighbors + 1])
            scores.append(score)

        if self.multi_krum:
            # Select m = n - f clients with lowest scores
            m = n - f
            selected_indices = np.argsort(scores)[:m]

            # Average selected clients
            aggregated = {}
            for key in global_weights.weights.keys():
                avg = np.zeros_like(global_weights.weights[key])
                for idx in selected_indices:
                    avg += client_updates[idx].model_weights.weights[key]
                aggregated[key] = avg / m
        else:
            # Select single client with lowest score
            best_idx = np.argmin(scores)
            aggregated = client_updates[best_idx].model_weights.weights.copy()

        return ModelWeights(
            weights=aggregated,
            version=global_weights.version + 1,
        )


# =============================================================================
# Aggregator Factory
# =============================================================================


def create_aggregator(
    strategy: AggregationStrategy,
    **kwargs,
) -> Aggregator:
    """
    Create an aggregator based on strategy.

    Args:
        strategy: Aggregation strategy
        **kwargs: Strategy-specific parameters

    Returns:
        Aggregator instance
    """
    aggregators = {
        AggregationStrategy.FEDAVG: FedAvgAggregator,
        AggregationStrategy.WEIGHTED_AVG: lambda **kw: FedAvgAggregator(weighted=True, **kw),
        AggregationStrategy.FEDPROX: FedProxAggregator,
        AggregationStrategy.FEDADAM: FedAdamAggregator,
        AggregationStrategy.FEDYOGI: FedYogiAggregator,
        AggregationStrategy.SCAFFOLD: ScaffoldAggregator,
        AggregationStrategy.MEDIAN: MedianAggregator,
        AggregationStrategy.TRIMMED_MEAN: TrimmedMeanAggregator,
        AggregationStrategy.KRUM: KrumAggregator,
    }

    aggregator_class = aggregators.get(strategy)
    if aggregator_class is None:
        raise ValueError(f"Unknown aggregation strategy: {strategy}")

    return aggregator_class(**kwargs)
