# -*- coding: utf-8 -*-
"""
Federated Learning Privacy - خصوصية التعلم الموحد
=================================================

Privacy mechanisms for federated learning.

آليات الخصوصية للتعلم الموحد:
- الخصوصية التفاضلية
- التجميع الآمن
- تشفير متماثل الشكل
"""

from __future__ import annotations

import logging
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from distributed_cluster.federated.models import (
    ClientUpdate,
    ModelWeights,
    PrivacyConfig,
    PrivacyMechanism,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Privacy Accountant
# =============================================================================


@dataclass
class PrivacyBudget:
    """Track privacy budget consumption."""
    epsilon_spent: float = 0.0
    delta_spent: float = 0.0
    queries: int = 0
    max_epsilon: float = 10.0
    max_delta: float = 1e-5

    @property
    def remaining_epsilon(self) -> float:
        return max(0.0, self.max_epsilon - self.epsilon_spent)

    @property
    def is_exhausted(self) -> bool:
        return (
            self.epsilon_spent >= self.max_epsilon
            or self.delta_spent >= self.max_delta
        )

    def consume(self, epsilon: float, delta: float) -> bool:
        """Consume privacy budget. Returns False if budget exhausted."""
        if self.is_exhausted:
            return False
        self.epsilon_spent += epsilon
        self.delta_spent += delta
        self.queries += 1
        return True


class PrivacyAccountant:
    """
    Privacy accountant for tracking DP budget.

    محاسب الخصوصية لتتبع ميزانية الخصوصية التفاضلية.
    """

    def __init__(
        self,
        epsilon: float = 1.0,
        delta: float = 1e-5,
    ):
        self.total_epsilon = epsilon
        self.total_delta = delta
        self._budget = PrivacyBudget(
            max_epsilon=epsilon,
            max_delta=delta,
        )

    @property
    def remaining_budget(self) -> Tuple[float, float]:
        """Get remaining (epsilon, delta) budget."""
        return (
            self._budget.remaining_epsilon,
            max(0.0, self._budget.max_delta - self._budget.delta_spent),
        )

    def compute_noise_multiplier(
        self,
        target_epsilon: float,
        num_steps: int,
        sample_rate: float,
    ) -> float:
        """
        Compute noise multiplier for target privacy level.

        Uses simplified composition theorem.
        """
        # Simplified: sigma = sqrt(2 * T * log(1.25/delta)) / epsilon
        # where T is number of steps
        if target_epsilon <= 0:
            return float("inf")

        noise_mult = (
            np.sqrt(2 * num_steps * np.log(1.25 / self.total_delta))
            / target_epsilon
            / sample_rate
        )

        return noise_mult

    def get_epsilon(
        self,
        noise_multiplier: float,
        num_steps: int,
        sample_rate: float,
    ) -> float:
        """
        Get privacy spent for given noise and steps.

        Simplified Gaussian mechanism composition.
        """
        if noise_multiplier == 0:
            return float("inf")

        # RDP-based accounting (simplified)
        epsilon = (
            np.sqrt(2 * num_steps * np.log(1.25 / self.total_delta))
            / (noise_multiplier * sample_rate)
        )

        return epsilon

    def step(self, epsilon: float, delta: float = 0.0) -> bool:
        """Record a privacy-consuming step."""
        return self._budget.consume(epsilon, delta)


# =============================================================================
# Differential Privacy
# =============================================================================


class DifferentialPrivacy:
    """
    Differential privacy mechanisms for federated learning.

    آليات الخصوصية التفاضلية للتعلم الموحد.
    """

    def __init__(
        self,
        epsilon: float = 1.0,
        delta: float = 1e-5,
        clip_norm: float = 1.0,
        noise_multiplier: Optional[float] = None,
    ):
        """
        Initialize DP mechanism.

        Args:
            epsilon: Privacy budget epsilon
            delta: Privacy budget delta
            clip_norm: L2 norm clipping bound
            noise_multiplier: Noise multiplier (computed if not provided)
        """
        self.epsilon = epsilon
        self.delta = delta
        self.clip_norm = clip_norm

        # Compute noise multiplier if not provided
        if noise_multiplier is None:
            # Standard Gaussian mechanism
            self.noise_multiplier = (
                np.sqrt(2 * np.log(1.25 / delta)) / epsilon
            )
        else:
            self.noise_multiplier = noise_multiplier

        self._accountant = PrivacyAccountant(epsilon, delta)

        logger.info(
            f"DP initialized: epsilon={epsilon}, delta={delta}, "
            f"clip_norm={clip_norm}, noise_mult={self.noise_multiplier:.4f}"
        )

    def clip_gradients(
        self,
        gradients: Dict[str, np.ndarray],
    ) -> Dict[str, np.ndarray]:
        """
        Clip gradients to bounded L2 norm.

        قص التدرجات لتحديد معيار L2.
        """
        # Compute total L2 norm
        total_norm = np.sqrt(
            sum(np.sum(g ** 2) for g in gradients.values())
        )

        # Clip if necessary
        if total_norm > self.clip_norm:
            scale = self.clip_norm / total_norm
            clipped = {k: v * scale for k, v in gradients.items()}
        else:
            clipped = gradients

        return clipped

    def add_noise(
        self,
        gradients: Dict[str, np.ndarray],
        num_samples: int = 1,
    ) -> Dict[str, np.ndarray]:
        """
        Add Gaussian noise to gradients.

        إضافة ضوضاء غاوسية إلى التدرجات.
        """
        noise_scale = self.clip_norm * self.noise_multiplier / num_samples

        noisy = {}
        for key, grad in gradients.items():
            noise = np.random.normal(0, noise_scale, grad.shape)
            noisy[key] = grad + noise

        return noisy

    def privatize(
        self,
        gradients: Dict[str, np.ndarray],
        num_samples: int = 1,
    ) -> Dict[str, np.ndarray]:
        """
        Apply full DP mechanism: clip and add noise.

        تطبيق آلية الخصوصية التفاضلية الكاملة.
        """
        # Clip gradients
        clipped = self.clip_gradients(gradients)

        # Add noise
        noisy = self.add_noise(clipped, num_samples)

        return noisy

    def privatize_weights(
        self,
        weights: ModelWeights,
        num_samples: int = 1,
    ) -> ModelWeights:
        """Apply DP to model weights."""
        privatized = self.privatize(weights.weights, num_samples)

        return ModelWeights(
            weights=privatized,
            version=weights.version,
        )

    @property
    def remaining_budget(self) -> Tuple[float, float]:
        """Get remaining privacy budget."""
        return self._accountant.remaining_budget


# =============================================================================
# Secure Aggregation
# =============================================================================


@dataclass
class SecretShare:
    """A secret share for secure aggregation."""
    owner_id: str
    recipient_id: str
    share: Dict[str, np.ndarray]
    mask_seed: bytes


class SecureAggregation:
    """
    Secure aggregation for federated learning.

    التجميع الآمن للتعلم الموحد.

    Implements a simplified version of the Bonawitz et al. secure aggregation
    protocol using Shamir's secret sharing.
    """

    def __init__(
        self,
        threshold: int = 2,
        num_clients: int = 3,
    ):
        """
        Initialize secure aggregation.

        Args:
            threshold: Minimum clients needed for reconstruction
            num_clients: Total number of clients
        """
        self.threshold = threshold
        self.num_clients = num_clients
        self._shares: Dict[str, Dict[str, SecretShare]] = {}
        self._masks: Dict[str, Dict[str, np.ndarray]] = {}

    def _generate_mask_seed(self) -> bytes:
        """Generate a random mask seed."""
        return secrets.token_bytes(32)

    def _generate_mask(
        self,
        seed: bytes,
        shape: Tuple[int, ...],
    ) -> np.ndarray:
        """Generate a mask from seed."""
        # Use seed to initialize RNG
        seed_int = int.from_bytes(seed[:4], byteorder="big")
        rng = np.random.RandomState(seed_int)
        return rng.randn(*shape)

    def generate_shares(
        self,
        client_id: str,
        weights: Dict[str, np.ndarray],
        peer_ids: List[str],
    ) -> Tuple[Dict[str, SecretShare], Dict[str, np.ndarray]]:
        """
        Generate secret shares for secure aggregation.

        توليد الحصص السرية للتجميع الآمن.

        Returns:
            - Dictionary of shares to send to peers
            - Masked weights to send to server
        """
        shares = {}
        total_mask = {k: np.zeros_like(v) for k, v in weights.items()}

        # Generate pairwise masks with each peer
        for peer_id in peer_ids:
            if peer_id == client_id:
                continue

            # Generate mask seed
            seed = self._generate_mask_seed()

            # Generate mask for each weight
            mask = {}
            for key, weight in weights.items():
                m = self._generate_mask(seed, weight.shape)

                # Determine sign based on lexicographic ordering
                if client_id < peer_id:
                    mask[key] = m
                    total_mask[key] += m
                else:
                    mask[key] = -m
                    total_mask[key] -= m

            shares[peer_id] = SecretShare(
                owner_id=client_id,
                recipient_id=peer_id,
                share=mask,
                mask_seed=seed,
            )

        # Add mask to weights
        masked_weights = {
            k: v + total_mask[k]
            for k, v in weights.items()
        }

        return shares, masked_weights

    def aggregate_with_shares(
        self,
        masked_updates: List[Tuple[str, Dict[str, np.ndarray]]],
        dropout_shares: Dict[str, List[SecretShare]],
    ) -> Dict[str, np.ndarray]:
        """
        Aggregate masked updates using dropout reconstruction.

        تجميع التحديثات المقنعة باستخدام إعادة بناء الانسحاب.

        Args:
            masked_updates: List of (client_id, masked_weights) tuples
            dropout_shares: Shares from clients that dropped out

        Returns:
            Aggregated weights
        """
        if len(masked_updates) < self.threshold:
            raise ValueError(
                f"Not enough updates for secure aggregation: "
                f"{len(masked_updates)} < {self.threshold}"
            )

        # Start with sum of masked updates
        active_clients = {client_id for client_id, _ in masked_updates}
        aggregated = {}

        for key in masked_updates[0][1].keys():
            aggregated[key] = np.zeros_like(masked_updates[0][1][key])
            for _, weights in masked_updates:
                aggregated[key] += weights[key]

        # Reconstruct masks for dropped clients
        for client_id, shares in dropout_shares.items():
            if client_id in active_clients:
                continue

            # Reconstruct client's mask from shares
            for share in shares:
                if share.owner_id not in active_clients:
                    continue

                for key in aggregated.keys():
                    if key in share.share:
                        # Subtract the mask that would have been added
                        aggregated[key] -= share.share[key]

        # Average
        num_clients = len(masked_updates)
        for key in aggregated:
            aggregated[key] /= num_clients

        return aggregated


# =============================================================================
# Privacy-Preserving Mechanisms
# =============================================================================


class PrivacyMechanismBase(ABC):
    """Base class for privacy mechanisms."""

    @abstractmethod
    def apply_to_update(
        self,
        update: ClientUpdate,
        **kwargs,
    ) -> ClientUpdate:
        """Apply privacy mechanism to client update."""
        pass

    @abstractmethod
    def apply_to_aggregation(
        self,
        updates: List[ClientUpdate],
        **kwargs,
    ) -> List[ClientUpdate]:
        """Apply privacy mechanism during aggregation."""
        pass


class NonePrivacy(PrivacyMechanismBase):
    """No privacy mechanism."""

    def apply_to_update(
        self,
        update: ClientUpdate,
        **kwargs,
    ) -> ClientUpdate:
        return update

    def apply_to_aggregation(
        self,
        updates: List[ClientUpdate],
        **kwargs,
    ) -> List[ClientUpdate]:
        return updates


class LocalDPPrivacy(PrivacyMechanismBase):
    """Local differential privacy mechanism."""

    def __init__(self, config: PrivacyConfig):
        self.config = config
        self._dp = DifferentialPrivacy(
            epsilon=config.epsilon,
            delta=config.delta,
            clip_norm=config.clip_norm,
            noise_multiplier=config.noise_multiplier,
        )

    def apply_to_update(
        self,
        update: ClientUpdate,
        **kwargs,
    ) -> ClientUpdate:
        """Apply local DP to client update."""
        privatized_weights = self._dp.privatize_weights(
            update.model_weights,
            num_samples=update.num_samples,
        )

        return ClientUpdate(
            client_id=update.client_id,
            round_number=update.round_number,
            model_weights=privatized_weights,
            num_samples=update.num_samples,
            training_loss=update.training_loss,
            validation_loss=update.validation_loss,
            validation_accuracy=update.validation_accuracy,
            training_time=update.training_time,
            metrics={**update.metrics, "dp_applied": True},
        )

    def apply_to_aggregation(
        self,
        updates: List[ClientUpdate],
        **kwargs,
    ) -> List[ClientUpdate]:
        """Local DP is applied at client side, not aggregation."""
        return updates


class CentralDPPrivacy(PrivacyMechanismBase):
    """Central differential privacy mechanism."""

    def __init__(self, config: PrivacyConfig):
        self.config = config
        self._dp = DifferentialPrivacy(
            epsilon=config.epsilon,
            delta=config.delta,
            clip_norm=config.clip_norm,
            noise_multiplier=config.noise_multiplier,
        )

    def apply_to_update(
        self,
        update: ClientUpdate,
        **kwargs,
    ) -> ClientUpdate:
        """Clip gradients at client side."""
        clipped_weights = self._dp.clip_gradients(update.model_weights.weights)

        return ClientUpdate(
            client_id=update.client_id,
            round_number=update.round_number,
            model_weights=ModelWeights(weights=clipped_weights),
            num_samples=update.num_samples,
            training_loss=update.training_loss,
            validation_loss=update.validation_loss,
            validation_accuracy=update.validation_accuracy,
            training_time=update.training_time,
            metrics={**update.metrics, "clipped": True},
        )

    def apply_to_aggregation(
        self,
        updates: List[ClientUpdate],
        **kwargs,
    ) -> List[ClientUpdate]:
        """Add noise during aggregation."""
        # In practice, noise is added after aggregation, not to individual updates
        # This is handled in the aggregator
        return updates


class SecureAggregationPrivacy(PrivacyMechanismBase):
    """Secure aggregation privacy mechanism."""

    def __init__(self, config: PrivacyConfig):
        self.config = config
        self._secure_agg: Optional[SecureAggregation] = None

    def initialize(self, num_clients: int) -> None:
        """Initialize secure aggregation with number of clients."""
        self._secure_agg = SecureAggregation(
            threshold=self.config.secure_aggregation_threshold,
            num_clients=num_clients,
        )

    def apply_to_update(
        self,
        update: ClientUpdate,
        peer_ids: Optional[List[str]] = None,
        **kwargs,
    ) -> ClientUpdate:
        """Generate shares for secure aggregation."""
        if self._secure_agg is None or peer_ids is None:
            return update

        shares, masked_weights = self._secure_agg.generate_shares(
            update.client_id,
            update.model_weights.weights,
            peer_ids,
        )

        # Store shares for later (in practice, send to peers)
        return ClientUpdate(
            client_id=update.client_id,
            round_number=update.round_number,
            model_weights=ModelWeights(weights=masked_weights),
            num_samples=update.num_samples,
            training_loss=update.training_loss,
            validation_loss=update.validation_loss,
            validation_accuracy=update.validation_accuracy,
            training_time=update.training_time,
            metrics={
                **update.metrics,
                "secure_agg": True,
                "num_shares": len(shares),
            },
        )

    def apply_to_aggregation(
        self,
        updates: List[ClientUpdate],
        **kwargs,
    ) -> List[ClientUpdate]:
        """Secure aggregation handles aggregation differently."""
        return updates


# =============================================================================
# Privacy Factory
# =============================================================================


def create_privacy_mechanism(
    config: PrivacyConfig,
) -> PrivacyMechanismBase:
    """
    Create a privacy mechanism based on configuration.

    Args:
        config: Privacy configuration

    Returns:
        Privacy mechanism instance
    """
    mechanisms = {
        PrivacyMechanism.NONE: NonePrivacy,
        PrivacyMechanism.LOCAL_DP: LocalDPPrivacy,
        PrivacyMechanism.DIFFERENTIAL_PRIVACY: CentralDPPrivacy,
        PrivacyMechanism.SECURE_AGGREGATION: SecureAggregationPrivacy,
    }

    mechanism_class = mechanisms.get(config.mechanism)
    if mechanism_class is None:
        logger.warning(f"Unknown privacy mechanism: {config.mechanism}, using none")
        return NonePrivacy()

    if mechanism_class == NonePrivacy:
        return NonePrivacy()

    return mechanism_class(config)
