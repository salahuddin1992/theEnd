# -*- coding: utf-8 -*-
"""
Job Predictor for NebulaCompute.

ML-based prediction engine for job duration and resource usage.

محرك التنبؤ القائم على التعلم الآلي.
"""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class PredictionModel(str, Enum):
    """Prediction model type."""

    LINEAR = "linear"
    POLYNOMIAL = "polynomial"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    NEURAL_NETWORK = "neural_network"


@dataclass
class PredictionResult:
    """
    Result of a prediction.

    نتيجة التنبؤ.
    """

    prediction_id: str
    job_type: str
    predicted_value: float
    confidence: float  # 0-1
    lower_bound: float
    upper_bound: float
    model_used: PredictionModel
    features_used: List[str]
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "prediction_id": self.prediction_id,
            "job_type": self.job_type,
            "predicted_value": self.predicted_value,
            "confidence": self.confidence,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "model_used": self.model_used.value,
            "features_used": self.features_used,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class JobFeatures:
    """Features extracted from a job for prediction."""

    job_type: str
    input_size_mb: float
    cpu_requested: float
    memory_requested_mb: float
    gpu_requested: float
    priority: int
    dependencies_count: int
    historical_avg_duration: Optional[float] = None
    queue_depth: int = 0
    cluster_load: float = 0.0
    time_of_day: int = 0  # Hour of day
    day_of_week: int = 0


@dataclass
class TrainingData:
    """Training data point for model training."""

    features: JobFeatures
    actual_duration: float
    actual_cpu_usage: float
    actual_memory_usage: float
    timestamp: datetime


class JobPredictor:
    """
    ML-based job prediction engine.

    محرك التنبؤ بالوظائف القائم على التعلم الآلي.

    Features:
    - Job duration prediction
    - Resource usage prediction
    - Queue wait time estimation
    - Model training and updating
    - Confidence intervals
    """

    def __init__(
        self,
        default_model: PredictionModel = PredictionModel.EXPONENTIAL_SMOOTHING,
        min_training_samples: int = 10,
        confidence_level: float = 0.95,
    ):
        """
        Initialize Job Predictor.

        Args:
            default_model: Default prediction model to use
            min_training_samples: Minimum samples before training
            confidence_level: Confidence level for intervals
        """
        self.default_model = default_model
        self.min_training_samples = min_training_samples
        self.confidence_level = confidence_level

        # Storage
        self._training_data: Dict[str, List[TrainingData]] = {}
        self._models: Dict[str, Dict[str, Any]] = {}
        self._predictions: Dict[str, PredictionResult] = {}
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "predictions_made": 0,
            "models_trained": 0,
            "accuracy_sum": 0.0,
            "prediction_errors": 0,
        }

    async def add_training_data(
        self,
        job_type: str,
        features: JobFeatures,
        actual_duration: float,
        actual_cpu_usage: float,
        actual_memory_usage: float,
    ) -> None:
        """
        Add training data point.

        إضافة نقطة بيانات للتدريب.
        """
        data = TrainingData(
            features=features,
            actual_duration=actual_duration,
            actual_cpu_usage=actual_cpu_usage,
            actual_memory_usage=actual_memory_usage,
            timestamp=datetime.utcnow(),
        )

        async with self._lock:
            if job_type not in self._training_data:
                self._training_data[job_type] = []
            self._training_data[job_type].append(data)

            # Trigger model retraining if needed
            if len(self._training_data[job_type]) % 50 == 0:
                await self._retrain_model(job_type)

    async def predict_duration(
        self,
        features: JobFeatures,
        model: Optional[PredictionModel] = None,
    ) -> PredictionResult:
        """
        Predict job duration.

        التنبؤ بمدة الوظيفة.
        """
        import uuid

        model = model or self.default_model
        job_type = features.job_type

        # Get or create model
        model_data = await self._get_model(job_type, "duration")

        # Extract feature vector
        feature_vector = self._extract_feature_vector(features)

        # Make prediction
        predicted_value, confidence, lower, upper = await self._predict(
            model_data, feature_vector, model
        )

        # Use historical average as fallback
        if features.historical_avg_duration and confidence < 0.5:
            predicted_value = features.historical_avg_duration
            confidence = 0.6

        result = PredictionResult(
            prediction_id=str(uuid.uuid4()),
            job_type=job_type,
            predicted_value=max(0, predicted_value),
            confidence=confidence,
            lower_bound=max(0, lower),
            upper_bound=upper,
            model_used=model,
            features_used=self._get_feature_names(),
        )

        async with self._lock:
            self._predictions[result.prediction_id] = result
            self._stats["predictions_made"] += 1

        logger.debug(
            f"Duration prediction for {job_type}: "
            f"{predicted_value:.1f}s (confidence: {confidence:.2f})"
        )

        return result

    async def predict_resource_usage(
        self,
        features: JobFeatures,
        resource_type: str = "cpu",
    ) -> PredictionResult:
        """
        Predict resource usage.

        التنبؤ باستخدام الموارد.
        """
        import uuid

        job_type = features.job_type
        model_data = await self._get_model(job_type, resource_type)
        feature_vector = self._extract_feature_vector(features)

        predicted_value, confidence, lower, upper = await self._predict(
            model_data, feature_vector, self.default_model
        )

        result = PredictionResult(
            prediction_id=str(uuid.uuid4()),
            job_type=job_type,
            predicted_value=max(0, min(100, predicted_value)),
            confidence=confidence,
            lower_bound=max(0, lower),
            upper_bound=min(100, upper),
            model_used=self.default_model,
            features_used=self._get_feature_names(),
            metadata={"resource_type": resource_type},
        )

        async with self._lock:
            self._predictions[result.prediction_id] = result
            self._stats["predictions_made"] += 1

        return result

    async def predict_queue_wait_time(
        self,
        queue_depth: int,
        avg_job_duration: float,
        available_workers: int,
        priority: int = 0,
    ) -> PredictionResult:
        """
        Predict queue wait time.

        التنبؤ بوقت الانتظار في الطابور.
        """
        import uuid

        # Simple queueing theory based prediction
        if available_workers == 0:
            # No workers available
            predicted_wait = queue_depth * avg_job_duration
            confidence = 0.3
        else:
            # Little's Law approximation
            arrival_rate = 1 / avg_job_duration if avg_job_duration > 0 else 0
            service_rate = available_workers / avg_job_duration if avg_job_duration > 0 else 1

            if service_rate > arrival_rate:
                # Stable queue
                rho = arrival_rate / service_rate
                predicted_wait = (rho / (1 - rho)) * avg_job_duration
                confidence = 0.7
            else:
                # Unstable queue
                predicted_wait = queue_depth * avg_job_duration / available_workers
                confidence = 0.4

        # Priority adjustment
        priority_factor = max(0.5, 1 - (priority * 0.1))
        predicted_wait *= priority_factor

        # Calculate bounds
        lower = predicted_wait * 0.5
        upper = predicted_wait * 2.0

        result = PredictionResult(
            prediction_id=str(uuid.uuid4()),
            job_type="queue_wait",
            predicted_value=max(0, predicted_wait),
            confidence=confidence,
            lower_bound=max(0, lower),
            upper_bound=upper,
            model_used=PredictionModel.LINEAR,
            features_used=["queue_depth", "avg_job_duration", "available_workers", "priority"],
        )

        async with self._lock:
            self._predictions[result.prediction_id] = result
            self._stats["predictions_made"] += 1

        return result

    async def _get_model(
        self,
        job_type: str,
        target: str,
    ) -> Dict[str, Any]:
        """Get or initialize model for job type."""
        key = f"{job_type}:{target}"

        async with self._lock:
            if key not in self._models:
                self._models[key] = {
                    "mean": 60.0,  # Default 60 seconds
                    "std": 30.0,
                    "coefficients": [],
                    "samples": 0,
                    "alpha": 0.3,  # Smoothing factor
                    "last_value": 60.0,
                }
            return self._models[key]

    async def _predict(
        self,
        model_data: Dict[str, Any],
        features: np.ndarray,
        model_type: PredictionModel,
    ) -> Tuple[float, float, float, float]:
        """Make prediction using model."""
        samples = model_data.get("samples", 0)

        if samples < self.min_training_samples:
            # Not enough data, use mean
            mean = model_data.get("mean", 60.0)
            std = model_data.get("std", 30.0)
            confidence = 0.3
            return mean, confidence, mean - 2 * std, mean + 2 * std

        if model_type == PredictionModel.LINEAR:
            return self._predict_linear(model_data, features)
        elif model_type == PredictionModel.POLYNOMIAL:
            return self._predict_polynomial(model_data, features)
        elif model_type == PredictionModel.EXPONENTIAL_SMOOTHING:
            return self._predict_exponential_smoothing(model_data, features)
        else:
            # Fallback to exponential smoothing
            return self._predict_exponential_smoothing(model_data, features)

    def _predict_linear(
        self,
        model_data: Dict[str, Any],
        features: np.ndarray,
    ) -> Tuple[float, float, float, float]:
        """Linear regression prediction."""
        coefficients = model_data.get("coefficients", [])
        mean = model_data.get("mean", 60.0)
        std = model_data.get("std", 30.0)

        if not coefficients or len(coefficients) != len(features):
            return mean, 0.5, mean - 2 * std, mean + 2 * std

        # y = sum(coef * feature) + intercept
        prediction = sum(c * f for c, f in zip(coefficients, features))
        prediction += model_data.get("intercept", 0)

        confidence = min(0.9, 0.5 + model_data.get("r_squared", 0) * 0.4)
        margin = std * (2 - confidence)

        return prediction, confidence, prediction - margin, prediction + margin

    def _predict_polynomial(
        self,
        model_data: Dict[str, Any],
        features: np.ndarray,
    ) -> Tuple[float, float, float, float]:
        """Polynomial regression prediction."""
        # For simplicity, use quadratic terms
        extended_features = np.concatenate([features, features ** 2])
        return self._predict_linear(
            {**model_data, "coefficients": model_data.get("poly_coefficients", [])},
            extended_features
        )

    def _predict_exponential_smoothing(
        self,
        model_data: Dict[str, Any],
        features: np.ndarray,
    ) -> Tuple[float, float, float, float]:
        """Exponential smoothing prediction."""
        alpha = model_data.get("alpha", 0.3)
        last_value = model_data.get("last_value", 60.0)
        mean = model_data.get("mean", 60.0)
        std = model_data.get("std", 30.0)

        # Simple exponential smoothing
        prediction = alpha * mean + (1 - alpha) * last_value

        # Adjust based on features (simple scaling)
        input_size = features[0] if len(features) > 0 else 1.0
        features[1] if len(features) > 1 else 1.0

        # Scale prediction based on input size
        if input_size > 0:
            prediction *= math.log1p(input_size) / math.log1p(100)

        confidence = min(0.85, 0.4 + 0.05 * math.log1p(model_data.get("samples", 0)))
        margin = std * (2 - confidence)

        return prediction, confidence, prediction - margin, prediction + margin

    async def _retrain_model(self, job_type: str) -> None:
        """Retrain model with new data."""
        data = self._training_data.get(job_type, [])
        if len(data) < self.min_training_samples:
            return

        # Extract training data
        durations = [d.actual_duration for d in data]
        mean_duration = sum(durations) / len(durations)
        std_duration = math.sqrt(
            sum((d - mean_duration) ** 2 for d in durations) / len(durations)
        )

        # Simple linear regression
        X = np.array([
            self._extract_feature_vector(d.features)
            for d in data
        ])
        y = np.array(durations)

        # Compute coefficients using normal equation
        # (X^T X)^-1 X^T y
        try:
            X_with_intercept = np.column_stack([np.ones(len(X)), X])
            coefficients = np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]

            # Calculate R-squared
            y_pred = X_with_intercept @ coefficients
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - mean_duration) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        except Exception as e:
            logger.warning(f"Model training failed: {e}")
            coefficients = np.zeros(X.shape[1] + 1)
            r_squared = 0

        # Update model
        key = f"{job_type}:duration"
        self._models[key] = {
            "mean": mean_duration,
            "std": std_duration,
            "intercept": coefficients[0],
            "coefficients": coefficients[1:].tolist(),
            "r_squared": r_squared,
            "samples": len(data),
            "alpha": 0.3,
            "last_value": durations[-1],
        }

        self._stats["models_trained"] += 1
        logger.info(
            f"Retrained model for {job_type}: "
            f"R² = {r_squared:.3f}, samples = {len(data)}"
        )

    def _extract_feature_vector(self, features: JobFeatures) -> np.ndarray:
        """Extract feature vector from JobFeatures."""
        return np.array([
            features.input_size_mb,
            features.cpu_requested,
            features.memory_requested_mb / 1024,  # Normalize to GB
            features.gpu_requested,
            features.priority,
            features.dependencies_count,
            features.queue_depth,
            features.cluster_load,
            features.time_of_day / 24,  # Normalize to 0-1
            features.day_of_week / 7,  # Normalize to 0-1
        ])

    def _get_feature_names(self) -> List[str]:
        """Get list of feature names."""
        return [
            "input_size_mb",
            "cpu_requested",
            "memory_requested_gb",
            "gpu_requested",
            "priority",
            "dependencies_count",
            "queue_depth",
            "cluster_load",
            "time_of_day",
            "day_of_week",
        ]

    async def evaluate_prediction(
        self,
        prediction_id: str,
        actual_value: float,
    ) -> float:
        """
        Evaluate prediction accuracy.

        تقييم دقة التنبؤ.
        """
        prediction = self._predictions.get(prediction_id)
        if not prediction:
            return 0.0

        predicted = prediction.predicted_value
        if predicted == 0:
            return 0.0

        # Calculate accuracy (1 - MAPE)
        error = abs(actual_value - predicted) / actual_value
        accuracy = max(0, 1 - error)

        async with self._lock:
            self._stats["accuracy_sum"] += accuracy

        return accuracy

    async def get_statistics(self) -> Dict[str, Any]:
        """Get predictor statistics."""
        predictions_made = self._stats["predictions_made"]
        avg_accuracy = (
            self._stats["accuracy_sum"] / predictions_made
            if predictions_made > 0
            else 0.0
        )

        return {
            **self._stats,
            "average_accuracy": avg_accuracy,
            "job_types_tracked": len(self._training_data),
            "models_count": len(self._models),
            "total_training_samples": sum(
                len(data) for data in self._training_data.values()
            ),
        }

    async def shutdown(self) -> None:
        """Shutdown predictor."""
        logger.info("Job Predictor shutdown complete")
