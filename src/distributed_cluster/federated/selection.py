# -*- coding: utf-8 -*-
"""
Federated Learning Client Selection - اختيار عملاء التعلم الموحد
================================================================

Client selection strategies for federated learning.

استراتيجيات اختيار العملاء للتعلم الموحد:
- عشوائي
- قائم على الموارد
- قائم على جودة البيانات
- OORT (اختيار موجه)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from distributed_cluster.federated.models import (
    ClientInfo,
    SelectionStrategy,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Selection Result
# =============================================================================


@dataclass
class SelectionResult:
    """Result of client selection."""
    selected_clients: List[str]
    selection_scores: Dict[str, float]
    selection_strategy: SelectionStrategy
    num_available: int
    num_selected: int
    metadata: Dict[str, Any]


# =============================================================================
# Base Selector
# =============================================================================


class ClientSelector(ABC):
    """
    Base class for client selection strategies.

    الفئة الأساسية لاستراتيجيات اختيار العملاء.
    """

    def __init__(self, **kwargs):
        self.config = kwargs

    @abstractmethod
    def select(
        self,
        available_clients: List[ClientInfo],
        num_to_select: int,
        round_number: int = 0,
        **kwargs,
    ) -> SelectionResult:
        """
        Select clients for a training round.

        Args:
            available_clients: List of available clients
            num_to_select: Number of clients to select
            round_number: Current round number
            **kwargs: Additional selection parameters

        Returns:
            Selection result with selected clients
        """
        pass


# =============================================================================
# Random Selection
# =============================================================================


class RandomSelector(ClientSelector):
    """
    Random client selection.

    اختيار عشوائي للعملاء.
    """

    def __init__(self, seed: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        self.rng = np.random.RandomState(seed)

    def select(
        self,
        available_clients: List[ClientInfo],
        num_to_select: int,
        round_number: int = 0,
        **kwargs,
    ) -> SelectionResult:
        """Select clients randomly."""
        num_available = len(available_clients)
        num_select = min(num_to_select, num_available)

        if num_available == 0:
            return SelectionResult(
                selected_clients=[],
                selection_scores={},
                selection_strategy=SelectionStrategy.RANDOM,
                num_available=0,
                num_selected=0,
                metadata={},
            )

        indices = self.rng.choice(
            num_available,
            size=num_select,
            replace=False,
        )

        selected = [available_clients[i].client_id for i in indices]
        scores = {c: 1.0 / num_available for c in selected}

        return SelectionResult(
            selected_clients=selected,
            selection_scores=scores,
            selection_strategy=SelectionStrategy.RANDOM,
            num_available=num_available,
            num_selected=num_select,
            metadata={"round": round_number},
        )


# =============================================================================
# Round Robin Selection
# =============================================================================


class RoundRobinSelector(ClientSelector):
    """
    Round-robin client selection.

    اختيار العملاء بالتناوب.
    """

    def select(
        self,
        available_clients: List[ClientInfo],
        num_to_select: int,
        round_number: int = 0,
        **kwargs,
    ) -> SelectionResult:
        """Select clients in round-robin fashion."""
        num_available = len(available_clients)
        num_select = min(num_to_select, num_available)

        if num_available == 0:
            return SelectionResult(
                selected_clients=[],
                selection_scores={},
                selection_strategy=SelectionStrategy.ROUND_ROBIN,
                num_available=0,
                num_selected=0,
                metadata={},
            )

        # Sort by last participation round (least recently used)
        sorted_clients = sorted(
            available_clients,
            key=lambda c: c.last_participation_round,
        )

        selected = [c.client_id for c in sorted_clients[:num_select]]

        # Score is inverse of last participation round
        max_round = max(c.last_participation_round for c in sorted_clients) + 1
        scores = {
            c.client_id: (max_round - c.last_participation_round) / max_round
            for c in sorted_clients[:num_select]
        }

        return SelectionResult(
            selected_clients=selected,
            selection_scores=scores,
            selection_strategy=SelectionStrategy.ROUND_ROBIN,
            num_available=num_available,
            num_selected=num_select,
            metadata={"round": round_number},
        )


# =============================================================================
# Resource-Aware Selection
# =============================================================================


class ResourceAwareSelector(ClientSelector):
    """
    Resource-aware client selection.

    اختيار العملاء بناءً على الموارد المتاحة.
    """

    def __init__(
        self,
        cpu_weight: float = 0.3,
        memory_weight: float = 0.3,
        gpu_weight: float = 0.4,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.cpu_weight = cpu_weight
        self.memory_weight = memory_weight
        self.gpu_weight = gpu_weight

    def _compute_resource_score(self, client: ClientInfo) -> float:
        """Compute resource score for a client."""
        if not client.available_resources:
            return 0.0

        cpu = client.available_resources.get("cpu", 0.0)
        memory = client.available_resources.get("memory", 0.0)
        gpu = client.available_resources.get("gpu", 0.0)

        score = (
            self.cpu_weight * min(cpu / 8.0, 1.0)  # Normalize to 8 cores
            + self.memory_weight * min(memory / 16384.0, 1.0)  # 16GB
            + self.gpu_weight * min(gpu, 1.0)  # At least 1 GPU
        )

        return score

    def select(
        self,
        available_clients: List[ClientInfo],
        num_to_select: int,
        round_number: int = 0,
        **kwargs,
    ) -> SelectionResult:
        """Select clients based on available resources."""
        num_available = len(available_clients)
        num_select = min(num_to_select, num_available)

        if num_available == 0:
            return SelectionResult(
                selected_clients=[],
                selection_scores={},
                selection_strategy=SelectionStrategy.RESOURCE_AWARE,
                num_available=0,
                num_selected=0,
                metadata={},
            )

        # Compute scores
        scores = {
            c.client_id: self._compute_resource_score(c)
            for c in available_clients
        }

        # Sort by score (descending)
        sorted_clients = sorted(
            available_clients,
            key=lambda c: scores[c.client_id],
            reverse=True,
        )

        selected = [c.client_id for c in sorted_clients[:num_select]]

        return SelectionResult(
            selected_clients=selected,
            selection_scores={c: scores[c] for c in selected},
            selection_strategy=SelectionStrategy.RESOURCE_AWARE,
            num_available=num_available,
            num_selected=num_select,
            metadata={"round": round_number},
        )


# =============================================================================
# Data Quality Selection
# =============================================================================


class DataQualitySelector(ClientSelector):
    """
    Data quality-based client selection.

    اختيار العملاء بناءً على جودة البيانات.
    """

    def __init__(
        self,
        min_samples: int = 10,
        diversity_weight: float = 0.5,
        size_weight: float = 0.3,
        reliability_weight: float = 0.2,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.min_samples = min_samples
        self.diversity_weight = diversity_weight
        self.size_weight = size_weight
        self.reliability_weight = reliability_weight

    def _compute_diversity_score(self, distribution: Optional[Dict[str, float]]) -> float:
        """Compute data diversity score based on label distribution."""
        if not distribution:
            return 0.5  # Neutral score if no distribution info

        # Use entropy as diversity measure
        probs = np.array(list(distribution.values()))
        probs = probs / probs.sum()  # Normalize
        probs = probs[probs > 0]  # Remove zeros

        if len(probs) <= 1:
            return 0.0

        entropy = -np.sum(probs * np.log(probs))
        max_entropy = np.log(len(probs))

        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _compute_quality_score(self, client: ClientInfo) -> float:
        """Compute overall data quality score."""
        # Dataset size score (logarithmic)
        size_score = min(np.log10(client.dataset_size + 1) / 4, 1.0)

        # Diversity score
        diversity_score = self._compute_diversity_score(client.data_distribution)

        # Reliability score
        reliability_score = client.reliability_score

        score = (
            self.size_weight * size_score
            + self.diversity_weight * diversity_score
            + self.reliability_weight * reliability_score
        )

        return score

    def select(
        self,
        available_clients: List[ClientInfo],
        num_to_select: int,
        round_number: int = 0,
        **kwargs,
    ) -> SelectionResult:
        """Select clients based on data quality."""
        # Filter by minimum samples
        eligible = [c for c in available_clients if c.dataset_size >= self.min_samples]

        num_available = len(eligible)
        num_select = min(num_to_select, num_available)

        if num_available == 0:
            return SelectionResult(
                selected_clients=[],
                selection_scores={},
                selection_strategy=SelectionStrategy.DATA_QUALITY,
                num_available=len(available_clients),
                num_selected=0,
                metadata={"filtered_out": len(available_clients) - num_available},
            )

        # Compute scores
        scores = {c.client_id: self._compute_quality_score(c) for c in eligible}

        # Sort by score
        sorted_clients = sorted(
            eligible,
            key=lambda c: scores[c.client_id],
            reverse=True,
        )

        selected = [c.client_id for c in sorted_clients[:num_select]]

        return SelectionResult(
            selected_clients=selected,
            selection_scores={c: scores[c] for c in selected},
            selection_strategy=SelectionStrategy.DATA_QUALITY,
            num_available=num_available,
            num_selected=num_select,
            metadata={
                "round": round_number,
                "filtered_out": len(available_clients) - num_available,
            },
        )


# =============================================================================
# Contribution-Based Selection
# =============================================================================


class ContributionBasedSelector(ClientSelector):
    """
    Contribution-based client selection.

    اختيار العملاء بناءً على مساهماتهم السابقة.
    """

    def __init__(
        self,
        exploration_rate: float = 0.1,
        contribution_weight: float = 0.7,
        data_weight: float = 0.3,
        seed: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.exploration_rate = exploration_rate
        self.contribution_weight = contribution_weight
        self.data_weight = data_weight
        self.rng = np.random.RandomState(seed)

    def select(
        self,
        available_clients: List[ClientInfo],
        num_to_select: int,
        round_number: int = 0,
        **kwargs,
    ) -> SelectionResult:
        """Select clients based on historical contribution."""
        num_available = len(available_clients)
        num_select = min(num_to_select, num_available)

        if num_available == 0:
            return SelectionResult(
                selected_clients=[],
                selection_scores={},
                selection_strategy=SelectionStrategy.CONTRIBUTION_BASED,
                num_available=0,
                num_selected=0,
                metadata={},
            )

        # Compute scores
        scores = {}
        for client in available_clients:
            contribution = client.contribution_score
            data_score = np.log10(client.dataset_size + 1) / 4

            score = (
                self.contribution_weight * contribution
                + self.data_weight * data_score
            )

            # Add exploration bonus for new/underrepresented clients
            if client.total_rounds_participated == 0:
                score += 0.1

            scores[client.client_id] = score

        # Epsilon-greedy exploration
        num_explore = max(1, int(num_select * self.exploration_rate))
        num_exploit = num_select - num_explore

        # Exploit: select top contributors
        sorted_clients = sorted(
            available_clients,
            key=lambda c: scores[c.client_id],
            reverse=True,
        )
        exploited = [c.client_id for c in sorted_clients[:num_exploit]]

        # Explore: randomly select from remaining
        remaining = [c for c in available_clients if c.client_id not in exploited]
        if remaining and num_explore > 0:
            explore_indices = self.rng.choice(
                len(remaining),
                size=min(num_explore, len(remaining)),
                replace=False,
            )
            explored = [remaining[i].client_id for i in explore_indices]
        else:
            explored = []

        selected = exploited + explored

        return SelectionResult(
            selected_clients=selected,
            selection_scores={c: scores[c] for c in selected},
            selection_strategy=SelectionStrategy.CONTRIBUTION_BASED,
            num_available=num_available,
            num_selected=len(selected),
            metadata={
                "round": round_number,
                "exploited": len(exploited),
                "explored": len(explored),
            },
        )


# =============================================================================
# OORT Selection
# =============================================================================


class OortSelector(ClientSelector):
    """
    OORT: Guided participant selection for efficient FL.

    اختيار OORT الموجه لتعلم موحد فعال.

    Reference: Lai et al., "OORT: Efficient Federated Learning via Guided
    Participant Selection" (2022)
    """

    def __init__(
        self,
        utility_weight: float = 0.5,
        statistical_weight: float = 0.3,
        system_weight: float = 0.2,
        pacer_decay: float = 0.9,
        seed: Optional[int] = None,
        **kwargs,
    ):
        """
        Initialize OORT selector.

        Args:
            utility_weight: Weight for statistical utility
            statistical_weight: Weight for data distribution
            system_weight: Weight for system performance
            pacer_decay: Decay factor for pacer
        """
        super().__init__(**kwargs)
        self.utility_weight = utility_weight
        self.statistical_weight = statistical_weight
        self.system_weight = system_weight
        self.pacer_decay = pacer_decay
        self.rng = np.random.RandomState(seed)

        # Tracking
        self._client_utilities: Dict[str, float] = {}
        self._round_durations: Dict[str, List[float]] = {}
        self._pacer_target: float = 0.0

    def _compute_statistical_utility(
        self,
        client: ClientInfo,
        global_distribution: Optional[Dict[str, float]] = None,
    ) -> float:
        """Compute statistical utility (data importance)."""
        if not client.data_distribution:
            return 0.5

        # Higher utility for rare data
        utility = np.sqrt(client.dataset_size)

        if global_distribution:
            # Weight by inverse frequency of labels
            for label, freq in client.data_distribution.items():
                global_freq = global_distribution.get(label, 0.5)
                if global_freq > 0:
                    utility *= freq / global_freq

        return min(utility, 10.0)  # Cap utility

    def _compute_system_utility(self, client: ClientInfo) -> float:
        """Compute system utility (training speed)."""
        # Use historical training time
        client_times = self._round_durations.get(client.client_id, [])

        if not client_times:
            return 1.0  # Default for new clients

        avg_time = np.mean(client_times)

        # Faster clients get higher utility
        return 1.0 / (1.0 + avg_time / 60.0)  # Normalize to minutes

    def _compute_oort_utility(
        self,
        client: ClientInfo,
        global_distribution: Optional[Dict[str, float]] = None,
    ) -> float:
        """Compute OORT utility score."""
        stat_util = self._compute_statistical_utility(client, global_distribution)
        sys_util = self._compute_system_utility(client)

        # Combine utilities
        utility = (
            self.statistical_weight * stat_util
            + self.system_weight * sys_util
        )

        # Apply exploration bonus
        participation_penalty = 1.0 / (1 + client.total_rounds_participated)
        utility *= (1 + 0.1 * participation_penalty)

        return utility

    def update_client_stats(
        self,
        client_id: str,
        round_duration: float,
        loss_improvement: float,
    ) -> None:
        """Update client statistics after a round."""
        if client_id not in self._round_durations:
            self._round_durations[client_id] = []

        self._round_durations[client_id].append(round_duration)

        # Keep only recent history
        if len(self._round_durations[client_id]) > 10:
            self._round_durations[client_id] = self._round_durations[client_id][-10:]

        # Update utility based on contribution
        old_utility = self._client_utilities.get(client_id, 1.0)
        self._client_utilities[client_id] = (
            self.pacer_decay * old_utility
            + (1 - self.pacer_decay) * loss_improvement
        )

    def select(
        self,
        available_clients: List[ClientInfo],
        num_to_select: int,
        round_number: int = 0,
        global_distribution: Optional[Dict[str, float]] = None,
        **kwargs,
    ) -> SelectionResult:
        """Select clients using OORT algorithm."""
        num_available = len(available_clients)
        num_select = min(num_to_select, num_available)

        if num_available == 0:
            return SelectionResult(
                selected_clients=[],
                selection_scores={},
                selection_strategy=SelectionStrategy.OORT,
                num_available=0,
                num_selected=0,
                metadata={},
            )

        # Compute utilities
        scores = {}
        for client in available_clients:
            utility = self._compute_oort_utility(client, global_distribution)
            scores[client.client_id] = utility

        # Normalize scores to probabilities
        total_utility = sum(scores.values())
        if total_utility > 0:
            probs = {k: v / total_utility for k, v in scores.items()}
        else:
            probs = {k: 1.0 / len(scores) for k in scores}

        # Sample based on utilities
        client_ids = list(probs.keys())
        prob_values = [probs[c] for c in client_ids]

        selected_indices = self.rng.choice(
            len(client_ids),
            size=num_select,
            replace=False,
            p=prob_values,
        )

        selected = [client_ids[i] for i in selected_indices]

        return SelectionResult(
            selected_clients=selected,
            selection_scores={c: scores[c] for c in selected},
            selection_strategy=SelectionStrategy.OORT,
            num_available=num_available,
            num_selected=len(selected),
            metadata={
                "round": round_number,
                "total_utility": total_utility,
            },
        )


# =============================================================================
# Availability-Based Selection
# =============================================================================


class AvailabilitySelector(ClientSelector):
    """
    Availability-based client selection.

    اختيار العملاء بناءً على التوافر.
    """

    def __init__(
        self,
        heartbeat_timeout: float = 60.0,
        reliability_threshold: float = 0.5,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.heartbeat_timeout = heartbeat_timeout
        self.reliability_threshold = reliability_threshold

    def select(
        self,
        available_clients: List[ClientInfo],
        num_to_select: int,
        round_number: int = 0,
        **kwargs,
    ) -> SelectionResult:
        """Select clients based on availability and reliability."""
        now = datetime.utcnow()

        # Filter by availability
        eligible = []
        for client in available_clients:
            if client.last_heartbeat is None:
                continue

            time_since_heartbeat = (now - client.last_heartbeat).total_seconds()
            if time_since_heartbeat > self.heartbeat_timeout:
                continue

            if client.reliability_score < self.reliability_threshold:
                continue

            eligible.append(client)

        num_available = len(eligible)
        num_select = min(num_to_select, num_available)

        if num_available == 0:
            return SelectionResult(
                selected_clients=[],
                selection_scores={},
                selection_strategy=SelectionStrategy.AVAILABILITY,
                num_available=len(available_clients),
                num_selected=0,
                metadata={"filtered_out": len(available_clients)},
            )

        # Score by reliability and recency
        scores = {}
        for client in eligible:
            time_since = (now - client.last_heartbeat).total_seconds()
            recency_score = 1.0 / (1 + time_since / 10.0)

            scores[client.client_id] = (
                0.7 * client.reliability_score
                + 0.3 * recency_score
            )

        # Sort by score
        sorted_clients = sorted(
            eligible,
            key=lambda c: scores[c.client_id],
            reverse=True,
        )

        selected = [c.client_id for c in sorted_clients[:num_select]]

        return SelectionResult(
            selected_clients=selected,
            selection_scores={c: scores[c] for c in selected},
            selection_strategy=SelectionStrategy.AVAILABILITY,
            num_available=num_available,
            num_selected=len(selected),
            metadata={
                "round": round_number,
                "filtered_out": len(available_clients) - num_available,
            },
        )


# =============================================================================
# Selector Factory
# =============================================================================


def create_selector(
    strategy: SelectionStrategy,
    **kwargs,
) -> ClientSelector:
    """
    Create a client selector based on strategy.

    Args:
        strategy: Selection strategy
        **kwargs: Strategy-specific parameters

    Returns:
        Client selector instance
    """
    selectors = {
        SelectionStrategy.RANDOM: RandomSelector,
        SelectionStrategy.ROUND_ROBIN: RoundRobinSelector,
        SelectionStrategy.RESOURCE_AWARE: ResourceAwareSelector,
        SelectionStrategy.DATA_QUALITY: DataQualitySelector,
        SelectionStrategy.CONTRIBUTION_BASED: ContributionBasedSelector,
        SelectionStrategy.OORT: OortSelector,
        SelectionStrategy.AVAILABILITY: AvailabilitySelector,
    }

    selector_class = selectors.get(strategy)
    if selector_class is None:
        raise ValueError(f"Unknown selection strategy: {strategy}")

    return selector_class(**kwargs)
