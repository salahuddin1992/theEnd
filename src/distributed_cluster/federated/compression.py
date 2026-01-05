# -*- coding: utf-8 -*-
"""
Federated Learning Compression - ضغط التعلم الموحد
===================================================

Model compression for communication-efficient federated learning.

ضغط النموذج للتعلم الموحد الفعال في الاتصال:
- التكميم
- التخفيف
- Top-K
- الرسم التخطيطي
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

from distributed_cluster.federated.models import (
    CompressionConfig,
    CompressionMethod,
    ModelWeights,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Compression Result
# =============================================================================


@dataclass
class CompressionResult:
    """Result of model compression."""

    compressed_weights: Dict[str, np.ndarray]
    compression_ratio: float
    original_size_bytes: int
    compressed_size_bytes: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def savings_percent(self) -> float:
        """Compression savings as percentage."""
        if self.original_size_bytes == 0:
            return 0.0
        return (1 - self.compressed_size_bytes / self.original_size_bytes) * 100


# =============================================================================
# Base Compressor
# =============================================================================


class Compressor(ABC):
    """
    Base class for model compression.

    الفئة الأساسية لضغط النموذج.
    """

    def __init__(self, **kwargs):
        self.config = kwargs
        self._error_feedback: Dict[str, np.ndarray] = {}

    @abstractmethod
    def compress(
        self,
        weights: Dict[str, np.ndarray],
        **kwargs,
    ) -> CompressionResult:
        """
        Compress model weights.

        Args:
            weights: Model weights to compress

        Returns:
            Compression result
        """
        pass

    @abstractmethod
    def decompress(
        self,
        compressed: Dict[str, np.ndarray],
        metadata: Dict[str, Any],
    ) -> Dict[str, np.ndarray]:
        """
        Decompress model weights.

        Args:
            compressed: Compressed weights
            metadata: Compression metadata

        Returns:
            Decompressed weights
        """
        pass

    def reset_error_feedback(self) -> None:
        """Reset error feedback state."""
        self._error_feedback = {}


# =============================================================================
# No Compression
# =============================================================================


class NoCompressor(Compressor):
    """No compression (passthrough)."""

    def compress(
        self,
        weights: Dict[str, np.ndarray],
        **kwargs,
    ) -> CompressionResult:
        size_bytes = sum(w.nbytes for w in weights.values())

        return CompressionResult(
            compressed_weights=weights,
            compression_ratio=1.0,
            original_size_bytes=size_bytes,
            compressed_size_bytes=size_bytes,
            metadata={},
        )

    def decompress(
        self,
        compressed: Dict[str, np.ndarray],
        metadata: Dict[str, Any],
    ) -> Dict[str, np.ndarray]:
        return compressed


# =============================================================================
# Quantization
# =============================================================================


class QuantizationCompressor(Compressor):
    """
    Quantization-based compression.

    ضغط قائم على التكميم.

    Reduces precision of weights to fewer bits.
    """

    def __init__(
        self,
        num_bits: int = 8,
        stochastic: bool = False,
        **kwargs,
    ):
        """
        Initialize quantization compressor.

        Args:
            num_bits: Number of bits for quantization
            stochastic: Use stochastic rounding
        """
        super().__init__(**kwargs)
        self.num_bits = num_bits
        self.stochastic = stochastic
        self.num_levels = 2**num_bits

    def compress(
        self,
        weights: Dict[str, np.ndarray],
        **kwargs,
    ) -> CompressionResult:
        """Compress using uniform quantization."""
        original_size = sum(w.nbytes for w in weights.values())

        compressed = {}
        scale_factors = {}
        zero_points = {}

        for key, weight in weights.items():
            # Compute min/max
            w_min = weight.min()
            w_max = weight.max()

            # Compute scale and zero point
            scale = (w_max - w_min) / (self.num_levels - 1)
            -w_min / scale if scale != 0 else 0

            # Quantize
            if scale != 0:
                quantized = np.round((weight - w_min) / scale)
                if self.stochastic:
                    # Add stochastic rounding
                    noise = np.random.uniform(-0.5, 0.5, weight.shape)
                    quantized = np.round((weight - w_min) / scale + noise)
                quantized = np.clip(quantized, 0, self.num_levels - 1)
            else:
                quantized = np.zeros_like(weight)

            # Store as lower precision
            if self.num_bits <= 8:
                compressed[key] = quantized.astype(np.uint8)
            elif self.num_bits <= 16:
                compressed[key] = quantized.astype(np.uint16)
            else:
                compressed[key] = quantized.astype(np.uint32)

            scale_factors[key] = scale
            zero_points[key] = w_min

        compressed_size = sum(w.nbytes for w in compressed.values())

        return CompressionResult(
            compressed_weights=compressed,
            compression_ratio=original_size / compressed_size if compressed_size > 0 else 1.0,
            original_size_bytes=original_size,
            compressed_size_bytes=compressed_size,
            metadata={
                "scale_factors": scale_factors,
                "zero_points": zero_points,
                "num_bits": self.num_bits,
            },
        )

    def decompress(
        self,
        compressed: Dict[str, np.ndarray],
        metadata: Dict[str, Any],
    ) -> Dict[str, np.ndarray]:
        """Decompress quantized weights."""
        scale_factors = metadata["scale_factors"]
        zero_points = metadata["zero_points"]

        decompressed = {}
        for key, quantized in compressed.items():
            scale = scale_factors[key]
            zero_point = zero_points[key]

            # Dequantize
            decompressed[key] = quantized.astype(np.float32) * scale + zero_point

        return decompressed


# =============================================================================
# Sparsification
# =============================================================================


class SparsificationCompressor(Compressor):
    """
    Sparsification-based compression.

    ضغط قائم على التخفيف.

    Keeps only values above a threshold.
    """

    def __init__(
        self,
        threshold_percentile: float = 90.0,
        error_feedback: bool = True,
        **kwargs,
    ):
        """
        Initialize sparsification compressor.

        Args:
            threshold_percentile: Percentile threshold for sparsification
            error_feedback: Use error feedback to correct quantization error
        """
        super().__init__(**kwargs)
        self.threshold_percentile = threshold_percentile
        self.use_error_feedback = error_feedback

    def compress(
        self,
        weights: Dict[str, np.ndarray],
        client_id: Optional[str] = None,
        **kwargs,
    ) -> CompressionResult:
        """Compress using magnitude-based sparsification."""
        original_size = sum(w.nbytes for w in weights.values())

        compressed = {}
        masks = {}
        total_elements = 0
        nonzero_elements = 0

        for key, weight in weights.items():
            # Apply error feedback
            if self.use_error_feedback and client_id:
                error_key = f"{client_id}_{key}"
                if error_key in self._error_feedback:
                    weight = weight + self._error_feedback[error_key]

            # Compute threshold
            threshold = np.percentile(np.abs(weight), self.threshold_percentile)

            # Create mask
            mask = np.abs(weight) >= threshold
            masks[key] = mask

            # Apply mask
            sparse = np.where(mask, weight, 0)
            compressed[key] = sparse

            # Track error for feedback
            if self.use_error_feedback and client_id:
                error_key = f"{client_id}_{key}"
                self._error_feedback[error_key] = weight - sparse

            total_elements += weight.size
            nonzero_elements += np.count_nonzero(mask)

        # Estimate compressed size (sparse format)
        # Assuming CSR-like format: values + indices
        compressed_size = int(nonzero_elements * (4 + 4))  # 4 bytes value + 4 bytes index

        return CompressionResult(
            compressed_weights=compressed,
            compression_ratio=original_size / compressed_size if compressed_size > 0 else 1.0,
            original_size_bytes=original_size,
            compressed_size_bytes=compressed_size,
            metadata={
                "masks": masks,
                "sparsity": 1 - nonzero_elements / total_elements,
            },
        )

    def decompress(
        self,
        compressed: Dict[str, np.ndarray],
        metadata: Dict[str, Any],
    ) -> Dict[str, np.ndarray]:
        """Decompress sparsified weights."""
        # Already in dense format
        return compressed


# =============================================================================
# Top-K Compression
# =============================================================================


class TopKCompressor(Compressor):
    """
    Top-K compression.

    ضغط Top-K.

    Keeps only the K largest magnitude values.
    """

    def __init__(
        self,
        k_ratio: float = 0.1,
        error_feedback: bool = True,
        **kwargs,
    ):
        """
        Initialize Top-K compressor.

        Args:
            k_ratio: Ratio of values to keep (0-1)
            error_feedback: Use error feedback
        """
        super().__init__(**kwargs)
        self.k_ratio = k_ratio
        self.use_error_feedback = error_feedback

    def compress(
        self,
        weights: Dict[str, np.ndarray],
        client_id: Optional[str] = None,
        **kwargs,
    ) -> CompressionResult:
        """Compress using Top-K selection."""
        original_size = sum(w.nbytes for w in weights.values())

        compressed = {}
        indices_dict = {}
        values_dict = {}

        for key, weight in weights.items():
            # Apply error feedback
            if self.use_error_feedback and client_id:
                error_key = f"{client_id}_{key}"
                if error_key in self._error_feedback:
                    weight = weight + self._error_feedback[error_key]

            flat = weight.flatten()
            k = max(1, int(len(flat) * self.k_ratio))

            # Get top-k indices by magnitude
            top_k_indices = np.argpartition(np.abs(flat), -k)[-k:]
            top_k_values = flat[top_k_indices]

            # Store sparse representation
            indices_dict[key] = top_k_indices
            values_dict[key] = top_k_values

            # Reconstruct for error feedback
            reconstructed = np.zeros_like(flat)
            reconstructed[top_k_indices] = top_k_values
            compressed[key] = reconstructed.reshape(weight.shape)

            # Track error
            if self.use_error_feedback and client_id:
                error_key = f"{client_id}_{key}"
                self._error_feedback[error_key] = weight - compressed[key]

        # Compressed size: indices + values
        compressed_size = sum(idx.nbytes + val.nbytes for idx, val in zip(indices_dict.values(), values_dict.values()))

        return CompressionResult(
            compressed_weights=compressed,
            compression_ratio=original_size / compressed_size if compressed_size > 0 else 1.0,
            original_size_bytes=original_size,
            compressed_size_bytes=compressed_size,
            metadata={
                "indices": indices_dict,
                "values": values_dict,
                "k_ratio": self.k_ratio,
            },
        )

    def decompress(
        self,
        compressed: Dict[str, np.ndarray],
        metadata: Dict[str, Any],
    ) -> Dict[str, np.ndarray]:
        """Decompress Top-K weights."""
        return compressed


# =============================================================================
# Random-K Compression
# =============================================================================


class RandomKCompressor(Compressor):
    """
    Random-K compression.

    ضغط عشوائي-K.

    Randomly samples K values (unbiased estimator).
    """

    def __init__(
        self,
        k_ratio: float = 0.1,
        seed: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.k_ratio = k_ratio
        self.rng = np.random.RandomState(seed)

    def compress(
        self,
        weights: Dict[str, np.ndarray],
        **kwargs,
    ) -> CompressionResult:
        """Compress using random sampling."""
        original_size = sum(w.nbytes for w in weights.values())

        compressed = {}
        indices_dict = {}
        values_dict = {}
        scale_factors = {}

        for key, weight in weights.items():
            flat = weight.flatten()
            n = len(flat)
            k = max(1, int(n * self.k_ratio))

            # Random sampling
            indices = self.rng.choice(n, size=k, replace=False)
            values = flat[indices]

            # Scale to maintain expected value
            scale = n / k

            indices_dict[key] = indices
            values_dict[key] = values
            scale_factors[key] = scale

            # Reconstruct
            reconstructed = np.zeros_like(flat)
            reconstructed[indices] = values * scale
            compressed[key] = reconstructed.reshape(weight.shape)

        compressed_size = sum(idx.nbytes + val.nbytes for idx, val in zip(indices_dict.values(), values_dict.values()))

        return CompressionResult(
            compressed_weights=compressed,
            compression_ratio=original_size / compressed_size if compressed_size > 0 else 1.0,
            original_size_bytes=original_size,
            compressed_size_bytes=compressed_size,
            metadata={
                "indices": indices_dict,
                "values": values_dict,
                "scale_factors": scale_factors,
            },
        )

    def decompress(
        self,
        compressed: Dict[str, np.ndarray],
        metadata: Dict[str, Any],
    ) -> Dict[str, np.ndarray]:
        """Decompress Random-K weights."""
        return compressed


# =============================================================================
# Gradient Compression
# =============================================================================


class GradientCompressor(Compressor):
    """
    Combined gradient compression.

    ضغط التدرج المجمع.

    Combines quantization and sparsification for maximum compression.
    """

    def __init__(
        self,
        sparsity: float = 0.9,
        num_bits: int = 8,
        error_feedback: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.sparsity = sparsity
        self.num_bits = num_bits
        self.use_error_feedback = error_feedback
        self.num_levels = 2**num_bits

    def compress(
        self,
        weights: Dict[str, np.ndarray],
        client_id: Optional[str] = None,
        **kwargs,
    ) -> CompressionResult:
        """Compress using combined sparsification and quantization."""
        original_size = sum(w.nbytes for w in weights.values())

        compressed = {}
        metadata_per_key = {}

        for key, weight in weights.items():
            # Apply error feedback
            if self.use_error_feedback and client_id:
                error_key = f"{client_id}_{key}"
                if error_key in self._error_feedback:
                    weight = weight + self._error_feedback[error_key]

            flat = weight.flatten()

            # Step 1: Sparsification
            k = max(1, int(len(flat) * (1 - self.sparsity)))
            top_k_indices = np.argpartition(np.abs(flat), -k)[-k:]
            sparse_values = flat[top_k_indices]

            # Step 2: Quantization of non-zero values
            if len(sparse_values) > 0:
                v_min = sparse_values.min()
                v_max = sparse_values.max()
                scale = (v_max - v_min) / (self.num_levels - 1) if v_max != v_min else 1.0

                if scale != 0:
                    quantized = np.round((sparse_values - v_min) / scale)
                    quantized = np.clip(quantized, 0, self.num_levels - 1).astype(np.uint8)
                else:
                    quantized = np.zeros(len(sparse_values), dtype=np.uint8)
            else:
                quantized = np.array([], dtype=np.uint8)
                v_min = 0.0
                scale = 1.0

            metadata_per_key[key] = {
                "indices": top_k_indices,
                "quantized": quantized,
                "scale": scale,
                "min": v_min,
                "shape": weight.shape,
            }

            # Reconstruct for error feedback
            reconstructed = np.zeros_like(flat)
            if len(quantized) > 0:
                reconstructed[top_k_indices] = quantized * scale + v_min
            compressed[key] = reconstructed.reshape(weight.shape)

            # Track error
            if self.use_error_feedback and client_id:
                error_key = f"{client_id}_{key}"
                self._error_feedback[error_key] = weight - compressed[key]

        # Compressed size: indices + quantized values
        compressed_size = sum(m["indices"].nbytes + m["quantized"].nbytes for m in metadata_per_key.values())

        return CompressionResult(
            compressed_weights=compressed,
            compression_ratio=original_size / compressed_size if compressed_size > 0 else 1.0,
            original_size_bytes=original_size,
            compressed_size_bytes=compressed_size,
            metadata=metadata_per_key,
        )

    def decompress(
        self,
        compressed: Dict[str, np.ndarray],
        metadata: Dict[str, Any],
    ) -> Dict[str, np.ndarray]:
        """Decompress gradient compressed weights."""
        decompressed = {}

        for key, key_meta in metadata.items():
            shape = key_meta["shape"]
            indices = key_meta["indices"]
            quantized = key_meta["quantized"]
            scale = key_meta["scale"]
            v_min = key_meta["min"]

            # Reconstruct
            flat = np.zeros(np.prod(shape))
            if len(quantized) > 0:
                flat[indices] = quantized * scale + v_min

            decompressed[key] = flat.reshape(shape)

        return decompressed


# =============================================================================
# Sketching Compression
# =============================================================================


class SketchingCompressor(Compressor):
    """
    Count Sketch-based compression.

    ضغط قائم على الرسم التخطيطي.

    Uses count sketch for unbiased compression.
    """

    def __init__(
        self,
        num_rows: int = 5,
        num_cols: int = 1000,
        seed: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.num_rows = num_rows
        self.num_cols = num_cols
        self.rng = np.random.RandomState(seed)

        # Generate hash functions
        self._hash_params = [(self.rng.randint(1, 2**31 - 1), self.rng.randint(0, 2**31 - 1)) for _ in range(num_rows)]
        self._sign_params = [(self.rng.randint(1, 2**31 - 1), self.rng.randint(0, 2**31 - 1)) for _ in range(num_rows)]

    def _hash(self, idx: int, row: int) -> int:
        """Hash function for column assignment."""
        a, b = self._hash_params[row]
        return ((a * idx + b) % (2**31 - 1)) % self.num_cols

    def _sign(self, idx: int, row: int) -> int:
        """Sign function (+1 or -1)."""
        a, b = self._sign_params[row]
        return 1 if ((a * idx + b) % (2**31 - 1)) % 2 == 0 else -1

    def compress(
        self,
        weights: Dict[str, np.ndarray],
        **kwargs,
    ) -> CompressionResult:
        """Compress using count sketch."""
        original_size = sum(w.nbytes for w in weights.values())

        compressed = {}
        sketches = {}

        for key, weight in weights.items():
            flat = weight.flatten()

            # Create sketch
            sketch = np.zeros((self.num_rows, self.num_cols), dtype=np.float32)

            for idx, val in enumerate(flat):
                for row in range(self.num_rows):
                    col = self._hash(idx, row)
                    sign = self._sign(idx, row)
                    sketch[row, col] += sign * val

            sketches[key] = sketch

            # Reconstruct using median
            reconstructed = np.zeros_like(flat)
            for idx in range(len(flat)):
                estimates = []
                for row in range(self.num_rows):
                    col = self._hash(idx, row)
                    sign = self._sign(idx, row)
                    estimates.append(sign * sketch[row, col])
                reconstructed[idx] = np.median(estimates)

            compressed[key] = reconstructed.reshape(weight.shape)

        compressed_size = sum(s.nbytes for s in sketches.values())

        return CompressionResult(
            compressed_weights=compressed,
            compression_ratio=original_size / compressed_size if compressed_size > 0 else 1.0,
            original_size_bytes=original_size,
            compressed_size_bytes=compressed_size,
            metadata={
                "sketches": sketches,
                "shapes": {k: v.shape for k, v in weights.items()},
            },
        )

    def decompress(
        self,
        compressed: Dict[str, np.ndarray],
        metadata: Dict[str, Any],
    ) -> Dict[str, np.ndarray]:
        """Decompress sketched weights."""
        return compressed


# =============================================================================
# Compressor Factory
# =============================================================================


def create_compressor(
    method: CompressionMethod,
    config: Optional[CompressionConfig] = None,
    **kwargs,
) -> Compressor:
    """
    Create a compressor based on method.

    Args:
        method: Compression method
        config: Compression configuration
        **kwargs: Method-specific parameters

    Returns:
        Compressor instance
    """
    if config:
        kwargs.setdefault("k_ratio", config.compression_ratio)
        kwargs.setdefault("num_bits", config.quantization_bits)
        kwargs.setdefault("error_feedback", config.error_feedback)
        kwargs.setdefault("seed", config.seed)

    compressors = {
        CompressionMethod.NONE: NoCompressor,
        CompressionMethod.QUANTIZATION: QuantizationCompressor,
        CompressionMethod.SPARSIFICATION: SparsificationCompressor,
        CompressionMethod.TOP_K: TopKCompressor,
        CompressionMethod.RANDOM_K: RandomKCompressor,
        CompressionMethod.GRADIENT_COMPRESSION: GradientCompressor,
        CompressionMethod.SKETCHING: SketchingCompressor,
    }

    compressor_class = compressors.get(method)
    if compressor_class is None:
        logger.warning(f"Unknown compression method: {method}, using none")
        return NoCompressor()

    return compressor_class(**kwargs)


def compress_model_weights(
    weights: ModelWeights,
    method: CompressionMethod = CompressionMethod.NONE,
    **kwargs,
) -> Tuple[ModelWeights, CompressionResult]:
    """
    Compress model weights.

    Args:
        weights: Model weights to compress
        method: Compression method
        **kwargs: Compression parameters

    Returns:
        Tuple of (compressed weights, compression result)
    """
    compressor = create_compressor(method, **kwargs)
    result = compressor.compress(weights.weights, **kwargs)

    compressed_weights = ModelWeights(
        weights=result.compressed_weights,
        version=weights.version,
    )

    return compressed_weights, result
