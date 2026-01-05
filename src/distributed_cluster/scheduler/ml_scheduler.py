"""
ML-Based Predictive Scheduler - مجدول تنبؤي بالذكاء الاصطناعي
============================================================

Uses historical job data to predict:
- Optimal resource allocation
- Job execution time
- Worker selection
- Queue wait times
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from distributed_cluster.models.job import Job, JobStatus
from distributed_cluster.models.resources import ResourceRequirements
from distributed_cluster.models.worker import Worker

logger = logging.getLogger(__name__)


@dataclass
class JobHistory:
    """سجل تاريخي لمهمة."""

    job_id: str
    name: str
    command: str
    requested_resources: ResourceRequirements
    actual_resources: Optional[ResourceRequirements] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    status: JobStatus = JobStatus.PENDING
    worker_id: Optional[str] = None
    exit_code: Optional[int] = None
    labels: Dict[str, str] = field(default_factory=dict)

    @property
    def features(self) -> Dict[str, float]:
        """استخراج ميزات للتعلم."""
        return {
            "requested_cpu": self.requested_resources.cpu_cores,
            "requested_memory": self.requested_resources.memory_mb,
            "requested_gpu": self.requested_resources.gpu_count,
            "command_length": len(self.command),
            "has_docker": 1.0 if "docker" in self.command.lower() else 0.0,
            "has_python": 1.0 if "python" in self.command.lower() else 0.0,
            "has_gpu": 1.0 if self.requested_resources.gpu_count > 0 else 0.0,
        }


@dataclass
class ResourcePrediction:
    """تنبؤ الموارد."""

    cpu_cores: float
    memory_mb: int
    gpu_count: int
    confidence: float
    duration_estimate_seconds: float
    duration_confidence: float


class JobFeatureExtractor:
    """مستخرج ميزات المهام."""

    def __init__(self):
        # Known command patterns
        self._patterns = {
            "training": ["train", "fit", "learn"],
            "inference": ["predict", "infer", "eval"],
            "preprocessing": ["preprocess", "transform", "clean"],
            "testing": ["test", "pytest", "unittest"],
            "building": ["build", "compile", "make"],
        }

    def extract(self, job: Job) -> np.ndarray:
        """استخراج ميزات من مهمة."""
        features = []

        # Resource features
        features.extend(
            [
                job.resources.cpu_cores,
                job.resources.memory_mb / 1024,  # GB
                job.resources.gpu_count,
            ]
        )

        # Command features
        cmd_lower = job.command.lower()
        features.append(len(job.command))
        features.append(job.command.count(" "))  # Number of args

        # Pattern matching
        for pattern_name, keywords in self._patterns.items():
            has_pattern = any(kw in cmd_lower for kw in keywords)
            features.append(1.0 if has_pattern else 0.0)

        # Docker features
        features.append(1.0 if job.docker_image else 0.0)

        # Priority
        features.append(job.priority / 100.0)

        return np.array(features)

    @property
    def feature_names(self) -> List[str]:
        """أسماء الميزات."""
        names = [
            "cpu_cores",
            "memory_gb",
            "gpu_count",
            "command_length",
            "arg_count",
        ]
        names.extend(self._patterns.keys())
        names.extend(["has_docker", "priority"])
        return names


class SimpleLinearModel:
    """نموذج خطي بسيط للتنبؤ."""

    def __init__(self, learning_rate: float = 0.01):
        self.learning_rate = learning_rate
        self.weights: Optional[np.ndarray] = None
        self.bias: float = 0.0
        self._fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 100) -> None:
        """تدريب النموذج."""
        n_samples, n_features = X.shape

        if self.weights is None:
            self.weights = np.zeros(n_features)

        for _ in range(epochs):
            # Forward pass
            predictions = X.dot(self.weights) + self.bias

            # Gradients
            errors = predictions - y
            dw = (1 / n_samples) * X.T.dot(errors)
            db = (1 / n_samples) * np.sum(errors)

            # Update
            self.weights -= self.learning_rate * dw
            self.bias -= self.learning_rate * db

        self._fitted = True

    def predict(self, X: np.ndarray) -> np.ndarray:
        """التنبؤ."""
        if not self._fitted:
            return np.zeros(X.shape[0])

        return X.dot(self.weights) + self.bias

    def save(self, path: str) -> None:
        """حفظ النموذج."""
        with open(path, "wb") as f:
            pickle.dump({"weights": self.weights, "bias": self.bias}, f)

    def load(self, path: str) -> None:
        """تحميل النموذج."""
        with open(path, "rb") as f:
            # nosec B301 - Loading ML model from trusted internal file
            data = pickle.load(f)
            self.weights = data["weights"]
            self.bias = data["bias"]
            self._fitted = True


class KNNPredictor:
    """K-Nearest Neighbors للتنبؤ."""

    def __init__(self, k: int = 5):
        self.k = k
        self._X: Optional[np.ndarray] = None
        self._y: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """تخزين البيانات."""
        self._X = X
        self._y = y

    def predict(self, X: np.ndarray) -> np.ndarray:
        """التنبؤ."""
        if self._X is None:
            return np.zeros(X.shape[0])

        predictions = []
        for x in X:
            # Calculate distances
            distances = np.sqrt(np.sum((self._X - x) ** 2, axis=1))

            # Get k nearest
            k_indices = np.argsort(distances)[: self.k]
            k_nearest = self._y[k_indices]

            # Average prediction
            predictions.append(np.mean(k_nearest))

        return np.array(predictions)


class MLScheduler:
    """
    مجدول ذكي باستخدام Machine Learning.

    يتعلم من تاريخ المهام للتنبؤ بـ:
    - وقت التنفيذ المتوقع
    - الموارد الفعلية المطلوبة
    - أفضل عامل للمهمة
    """

    def __init__(
        self,
        min_history_size: int = 50,
        model_update_interval: int = 100,
    ):
        self.min_history_size = min_history_size
        self.model_update_interval = model_update_interval

        # Feature extraction
        self._extractor = JobFeatureExtractor()

        # Models
        self._duration_model = SimpleLinearModel(learning_rate=0.001)
        self._cpu_model = SimpleLinearModel(learning_rate=0.001)
        self._memory_model = SimpleLinearModel(learning_rate=0.001)
        self._knn = KNNPredictor(k=5)

        # History
        self._history: List[JobHistory] = []
        self._jobs_since_update = 0

        # Statistics
        self._prediction_errors: List[float] = []

    def record_job(self, history: JobHistory) -> None:
        """تسجيل مهمة مكتملة."""
        if history.status != JobStatus.COMPLETED:
            return

        if history.duration_seconds is None:
            return

        self._history.append(history)
        self._jobs_since_update += 1

        # Retrain models periodically
        if self._jobs_since_update >= self.model_update_interval:
            self._retrain_models()
            self._jobs_since_update = 0

    def _retrain_models(self) -> None:
        """إعادة تدريب النماذج."""
        if len(self._history) < self.min_history_size:
            return

        # Prepare training data
        X = []
        y_duration = []
        y_cpu = []
        y_memory = []

        for h in self._history[-1000:]:  # Use last 1000 jobs
            job = Job(
                job_id=h.job_id,
                name=h.name,
                command=h.command,
                resources=h.requested_resources,
            )
            features = self._extractor.extract(job)
            X.append(features)
            y_duration.append(h.duration_seconds)

            if h.actual_resources:
                y_cpu.append(h.actual_resources.cpu_cores)
                y_memory.append(h.actual_resources.memory_mb)
            else:
                y_cpu.append(h.requested_resources.cpu_cores)
                y_memory.append(h.requested_resources.memory_mb)

        X = np.array(X)
        y_duration = np.array(y_duration)
        y_cpu = np.array(y_cpu)
        y_memory = np.array(y_memory)

        # Train models
        self._duration_model.fit(X, y_duration, epochs=200)
        self._cpu_model.fit(X, y_cpu, epochs=200)
        self._memory_model.fit(X, y_memory, epochs=200)
        self._knn.fit(X, y_duration)

        logger.info(f"ML models retrained with {len(X)} samples")

    def predict_duration(self, job: Job) -> Tuple[float, float]:
        """
        تنبؤ وقت التنفيذ.

        Returns:
            (estimated_seconds, confidence)
        """
        if len(self._history) < self.min_history_size:
            # Not enough data, return default estimate
            return self._default_duration_estimate(job), 0.3

        features = self._extractor.extract(job).reshape(1, -1)

        # Linear model prediction
        linear_pred = self._duration_model.predict(features)[0]

        # KNN prediction
        knn_pred = self._knn.predict(features)[0]

        # Ensemble
        estimate = 0.6 * linear_pred + 0.4 * knn_pred

        # Calculate confidence based on history similarity
        confidence = self._calculate_confidence(features)

        # Ensure positive
        estimate = max(estimate, 60)  # At least 1 minute

        return estimate, confidence

    def predict_resources(self, job: Job) -> ResourcePrediction:
        """
        تنبؤ الموارد المثلى.

        Returns:
            ResourcePrediction object
        """
        if len(self._history) < self.min_history_size:
            # Return requested resources with low confidence
            duration, _ = self.predict_duration(job)
            return ResourcePrediction(
                cpu_cores=job.resources.cpu_cores,
                memory_mb=job.resources.memory_mb,
                gpu_count=job.resources.gpu_count,
                confidence=0.3,
                duration_estimate_seconds=duration,
                duration_confidence=0.3,
            )

        features = self._extractor.extract(job).reshape(1, -1)

        # Predict resources
        cpu = max(0.5, self._cpu_model.predict(features)[0])
        memory = max(256, int(self._memory_model.predict(features)[0]))

        # Duration
        duration, duration_conf = self.predict_duration(job)

        # GPU is harder to predict, use requested
        gpu = job.resources.gpu_count

        confidence = self._calculate_confidence(features)

        return ResourcePrediction(
            cpu_cores=round(cpu, 1),
            memory_mb=memory,
            gpu_count=gpu,
            confidence=confidence,
            duration_estimate_seconds=duration,
            duration_confidence=duration_conf,
        )

    def _default_duration_estimate(self, job: Job) -> float:
        """تقدير افتراضي للمدة."""
        # Simple heuristics
        base = 300  # 5 minutes base

        # Adjust for resources
        base *= job.resources.cpu_cores / 2
        base *= 1 + (job.resources.memory_mb / 4096)
        base *= 1 + (job.resources.gpu_count * 2)

        # Adjust for command patterns
        cmd_lower = job.command.lower()
        if "train" in cmd_lower:
            base *= 4
        elif "test" in cmd_lower:
            base *= 0.5
        elif "build" in cmd_lower:
            base *= 2

        return base

    def _calculate_confidence(self, features: np.ndarray) -> float:
        """حساب مستوى الثقة."""
        if len(self._history) < self.min_history_size:
            return 0.3

        # Calculate based on similarity to historical jobs
        all_features = []
        for h in self._history[-100:]:
            job = Job(
                job_id=h.job_id,
                name=h.name,
                command=h.command,
                resources=h.requested_resources,
            )
            all_features.append(self._extractor.extract(job))

        if not all_features:
            return 0.3

        all_features = np.array(all_features)

        # Calculate minimum distance to historical jobs
        distances = np.sqrt(np.sum((all_features - features) ** 2, axis=1))
        min_distance = np.min(distances)

        # Convert distance to confidence (closer = higher confidence)
        confidence = 1.0 / (1.0 + min_distance)

        # Scale to reasonable range
        confidence = 0.3 + 0.6 * confidence

        return min(confidence, 0.95)

    def recommend_worker(
        self,
        job: Job,
        workers: List[Worker],
    ) -> Optional[Tuple[Worker, float]]:
        """
        توصية بأفضل عامل للمهمة.

        Returns:
            (worker, score) or None
        """
        if not workers:
            return None

        prediction = self.predict_resources(job)

        scored_workers = []
        for worker in workers:
            if not self._worker_can_run(worker, prediction):
                continue

            score = self._score_worker(worker, prediction)
            scored_workers.append((worker, score))

        if not scored_workers:
            return None

        # Sort by score (descending)
        scored_workers.sort(key=lambda x: x[1], reverse=True)

        return scored_workers[0]

    def _worker_can_run(
        self,
        worker: Worker,
        prediction: ResourcePrediction,
    ) -> bool:
        """التحقق من قدرة العامل على تنفيذ المهمة."""
        avail = worker.available_resources

        return (
            avail.cpu_cores >= prediction.cpu_cores
            and avail.memory_mb >= prediction.memory_mb
            and avail.gpu_count >= prediction.gpu_count
        )

    def _score_worker(
        self,
        worker: Worker,
        prediction: ResourcePrediction,
    ) -> float:
        """تقييم ملاءمة العامل."""
        avail = worker.available_resources
        total = worker.total_resources

        # Resource utilization score (prefer workers with available capacity)
        cpu_util = 1 - (avail.cpu_cores / total.cpu_cores)
        mem_util = 1 - (avail.memory_mb / total.memory_mb)

        # Fit score (how well the job fits)
        cpu_fit = 1 - abs(prediction.cpu_cores - avail.cpu_cores) / total.cpu_cores
        mem_fit = 1 - abs(prediction.memory_mb - avail.memory_mb) / total.memory_mb

        # Health score
        health = 1.0  # Assume healthy

        # Combined score
        score = (
            0.3 * (1 - cpu_util)  # Prefer less utilized
            + 0.2 * (1 - mem_util)
            + 0.2 * cpu_fit
            + 0.2 * mem_fit
            + 0.1 * health
        )

        return score

    def estimate_queue_wait(
        self,
        job: Job,
        pending_jobs: List[Job],
        workers: List[Worker],
    ) -> Tuple[float, float]:
        """
        تقدير وقت الانتظار في الطابور.

        Returns:
            (estimated_wait_seconds, confidence)
        """
        if not workers:
            return float("inf"), 0.1

        # Calculate total available capacity
        total_cpu = sum(w.available_resources.cpu_cores for w in workers)
        sum(w.available_resources.memory_mb for w in workers)

        # Calculate pending job requirements
        pending_duration = 0.0
        for pending in pending_jobs:
            est, _ = self.predict_duration(pending)
            pending_duration += est

        # Estimate parallel capacity
        avg_cpu_per_job = sum(j.resources.cpu_cores for j in pending_jobs) / max(len(pending_jobs), 1)

        parallel_capacity = max(1, total_cpu / max(avg_cpu_per_job, 0.5))

        # Calculate wait time
        wait_time = pending_duration / parallel_capacity

        # Position in queue
        job_position = len([j for j in pending_jobs if j.priority >= job.priority])

        # Adjust for position
        wait_time *= (job_position + 1) / len(pending_jobs) if pending_jobs else 1

        confidence = 0.5 if len(self._history) >= self.min_history_size else 0.3

        return wait_time, confidence

    @property
    def stats(self) -> Dict[str, Any]:
        """إحصائيات."""
        return {
            "history_size": len(self._history),
            "min_history_required": self.min_history_size,
            "models_trained": len(self._history) >= self.min_history_size,
            "jobs_since_update": self._jobs_since_update,
            "avg_prediction_error": (np.mean(self._prediction_errors[-100:]) if self._prediction_errors else None),
        }

    def save_models(self, directory: str) -> None:
        """حفظ النماذج."""
        import os

        os.makedirs(directory, exist_ok=True)

        self._duration_model.save(f"{directory}/duration_model.pkl")
        self._cpu_model.save(f"{directory}/cpu_model.pkl")
        self._memory_model.save(f"{directory}/memory_model.pkl")

        # Save history summary
        with open(f"{directory}/history_stats.pkl", "wb") as f:
            pickle.dump(
                {
                    "history_size": len(self._history),
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                },
                f,
            )

        logger.info(f"ML models saved to {directory}")

    def load_models(self, directory: str) -> None:
        """تحميل النماذج."""
        import os

        if os.path.exists(f"{directory}/duration_model.pkl"):
            self._duration_model.load(f"{directory}/duration_model.pkl")
            self._cpu_model.load(f"{directory}/cpu_model.pkl")
            self._memory_model.load(f"{directory}/memory_model.pkl")
            logger.info(f"ML models loaded from {directory}")


# =============================================================================
# Usage Example
# =============================================================================


def create_ml_scheduler_from_history(
    history: List[Dict[str, Any]],
) -> MLScheduler:
    """إنشاء مجدول ML من تاريخ المهام."""
    scheduler = MLScheduler()

    for h in history:
        job_history = JobHistory(
            job_id=h.get("job_id", ""),
            name=h.get("name", ""),
            command=h.get("command", ""),
            requested_resources=ResourceRequirements(
                cpu_cores=h.get("cpu", 1),
                memory_mb=h.get("memory", 512),
                gpu_count=h.get("gpu", 0),
            ),
            duration_seconds=h.get("duration"),
            status=JobStatus.COMPLETED if h.get("success") else JobStatus.FAILED,
        )
        scheduler.record_job(job_history)

    return scheduler
