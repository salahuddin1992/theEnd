"""
ML Models - نماذج التعلم الآلي
==============================

Core model definitions and metadata.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class ModelFramework(str, Enum):
    """Supported ML frameworks."""
    PYTORCH = "pytorch"
    TENSORFLOW = "tensorflow"
    SKLEARN = "sklearn"
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    ONNX = "onnx"
    CUSTOM = "custom"


class ModelState(str, Enum):
    """Model lifecycle states."""
    DRAFT = "draft"
    TRAINING = "training"
    VALIDATING = "validating"
    READY = "ready"
    DEPLOYED = "deployed"
    ARCHIVED = "archived"
    FAILED = "failed"


@dataclass
class ModelMetadata:
    """Model metadata and documentation."""
    name: str
    description: str = ""
    author: str = ""
    tags: List[str] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Model information
    framework: ModelFramework = ModelFramework.CUSTOM
    framework_version: str = ""
    python_version: str = ""

    # Input/Output schema
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)

    # Performance metrics
    metrics: Dict[str, float] = field(default_factory=dict)

    # Dependencies
    requirements: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "labels": self.labels,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "framework": self.framework.value,
            "framework_version": self.framework_version,
            "python_version": self.python_version,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "metrics": self.metrics,
            "requirements": self.requirements,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelMetadata:
        data = data.copy()
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        data["framework"] = ModelFramework(data["framework"])
        return cls(**data)


@dataclass
class ModelConfig:
    """Model configuration for inference."""
    batch_size: int = 32
    max_batch_size: int = 128
    timeout_ms: int = 5000
    max_concurrent_requests: int = 100

    # GPU settings
    use_gpu: bool = False
    gpu_memory_fraction: float = 0.5

    # Preprocessing
    preprocessing_fn: Optional[str] = None
    postprocessing_fn: Optional[str] = None

    # Caching
    enable_caching: bool = False
    cache_ttl_seconds: int = 3600

    # Warmup
    warmup_requests: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_size": self.batch_size,
            "max_batch_size": self.max_batch_size,
            "timeout_ms": self.timeout_ms,
            "max_concurrent_requests": self.max_concurrent_requests,
            "use_gpu": self.use_gpu,
            "gpu_memory_fraction": self.gpu_memory_fraction,
            "preprocessing_fn": self.preprocessing_fn,
            "postprocessing_fn": self.postprocessing_fn,
            "enable_caching": self.enable_caching,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "warmup_requests": self.warmup_requests,
        }


@dataclass
class ModelVersion:
    """Represents a specific version of a model."""
    version_id: str
    model_id: str
    version_number: int
    state: ModelState = ModelState.DRAFT

    # Artifact information
    artifact_path: str = ""
    artifact_hash: str = ""
    artifact_size_bytes: int = 0

    # Metadata
    metadata: ModelMetadata = field(default_factory=lambda: ModelMetadata(name=""))
    config: ModelConfig = field(default_factory=ModelConfig)

    # Training information
    training_job_id: Optional[str] = None
    training_dataset_id: Optional[str] = None
    parent_version_id: Optional[str] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    deployed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "model_id": self.model_id,
            "version_number": self.version_number,
            "state": self.state.value,
            "artifact_path": self.artifact_path,
            "artifact_hash": self.artifact_hash,
            "artifact_size_bytes": self.artifact_size_bytes,
            "metadata": self.metadata.to_dict(),
            "config": self.config.to_dict(),
            "training_job_id": self.training_job_id,
            "training_dataset_id": self.training_dataset_id,
            "parent_version_id": self.parent_version_id,
            "created_at": self.created_at.isoformat(),
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
        }


@dataclass
class PredictionResult:
    """Result of a model prediction."""
    request_id: str
    model_id: str
    version_id: str

    # Predictions
    predictions: List[Any] = field(default_factory=list)
    probabilities: Optional[List[List[float]]] = None

    # Metadata
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Optional explanations
    feature_importance: Optional[Dict[str, float]] = None
    explanations: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "model_id": self.model_id,
            "version_id": self.version_id,
            "predictions": self.predictions,
            "probabilities": self.probabilities,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
            "feature_importance": self.feature_importance,
            "explanations": self.explanations,
        }


class Model:
    """
    ML Model wrapper.

    Provides a unified interface for loading and running inference
    across different ML frameworks.
    """

    def __init__(
        self,
        model_id: str,
        metadata: ModelMetadata,
        config: Optional[ModelConfig] = None,
    ):
        self.model_id = model_id
        self.metadata = metadata
        self.config = config or ModelConfig()

        self._model: Any = None
        self._preprocessor: Optional[Callable] = None
        self._postprocessor: Optional[Callable] = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self, artifact_path: str) -> None:
        """Load model from artifact path."""
        path = Path(artifact_path)

        if not path.exists():
            raise FileNotFoundError(f"Model artifact not found: {artifact_path}")

        framework = self.metadata.framework

        if framework == ModelFramework.PYTORCH:
            self._load_pytorch(path)
        elif framework == ModelFramework.TENSORFLOW:
            self._load_tensorflow(path)
        elif framework == ModelFramework.SKLEARN:
            self._load_sklearn(path)
        elif framework == ModelFramework.ONNX:
            self._load_onnx(path)
        elif framework == ModelFramework.XGBOOST:
            self._load_xgboost(path)
        elif framework == ModelFramework.LIGHTGBM:
            self._load_lightgbm(path)
        else:
            self._load_custom(path)

        self._loaded = True
        logger.info(f"Loaded model {self.model_id} from {artifact_path}")

    def _load_pytorch(self, path: Path) -> None:
        """Load PyTorch model."""
        try:
            import torch
            self._model = torch.jit.load(str(path / "model.pt"))
            self._model.eval()
        except ImportError:
            raise ImportError("PyTorch is required for loading PyTorch models")

    def _load_tensorflow(self, path: Path) -> None:
        """Load TensorFlow model."""
        try:
            import tensorflow as tf
            self._model = tf.saved_model.load(str(path))
        except ImportError:
            raise ImportError("TensorFlow is required for loading TensorFlow models")

    def _load_sklearn(self, path: Path) -> None:
        """Load scikit-learn model."""
        try:
            import joblib
            self._model = joblib.load(path / "model.joblib")
        except ImportError:
            import pickle
            with open(path / "model.pkl", "rb") as f:
                self._model = pickle.load(f)

    def _load_onnx(self, path: Path) -> None:
        """Load ONNX model."""
        try:
            import onnxruntime as ort
            self._model = ort.InferenceSession(str(path / "model.onnx"))
        except ImportError:
            raise ImportError("ONNX Runtime is required for loading ONNX models")

    def _load_xgboost(self, path: Path) -> None:
        """Load XGBoost model."""
        try:
            import xgboost as xgb
            self._model = xgb.Booster()
            self._model.load_model(str(path / "model.xgb"))
        except ImportError:
            raise ImportError("XGBoost is required for loading XGBoost models")

    def _load_lightgbm(self, path: Path) -> None:
        """Load LightGBM model."""
        try:
            import lightgbm as lgb
            self._model = lgb.Booster(model_file=str(path / "model.lgb"))
        except ImportError:
            raise ImportError("LightGBM is required for loading LightGBM models")

    def _load_custom(self, path: Path) -> None:
        """Load custom model."""
        import pickle
        with open(path / "model.pkl", "rb") as f:
            self._model = pickle.load(f)

    def predict(
        self,
        inputs: Any,
        request_id: Optional[str] = None,
    ) -> PredictionResult:
        """Run inference on inputs."""
        import time

        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        request_id = request_id or str(uuid.uuid4())
        start_time = time.time()

        # Preprocess
        if self._preprocessor:
            inputs = self._preprocessor(inputs)

        # Run inference
        predictions = self._run_inference(inputs)

        # Postprocess
        if self._postprocessor:
            predictions = self._postprocessor(predictions)

        latency_ms = (time.time() - start_time) * 1000

        return PredictionResult(
            request_id=request_id,
            model_id=self.model_id,
            version_id="",  # Set by caller
            predictions=predictions if isinstance(predictions, list) else [predictions],
            latency_ms=latency_ms,
        )

    def _run_inference(self, inputs: Any) -> Any:
        """Run inference based on framework."""
        framework = self.metadata.framework

        if framework == ModelFramework.PYTORCH:
            import torch
            with torch.no_grad():
                if isinstance(inputs, list):
                    inputs = torch.tensor(inputs)
                outputs = self._model(inputs)
                return outputs.numpy().tolist()

        elif framework == ModelFramework.TENSORFLOW:
            import numpy as np
            if isinstance(inputs, list):
                inputs = np.array(inputs)
            outputs = self._model(inputs)
            return outputs.numpy().tolist()

        elif framework == ModelFramework.SKLEARN:
            return self._model.predict(inputs).tolist()

        elif framework == ModelFramework.ONNX:
            import numpy as np
            input_name = self._model.get_inputs()[0].name
            if isinstance(inputs, list):
                inputs = np.array(inputs, dtype=np.float32)
            outputs = self._model.run(None, {input_name: inputs})
            return outputs[0].tolist()

        elif framework == ModelFramework.XGBOOST:
            import xgboost as xgb
            import numpy as np
            if isinstance(inputs, list):
                inputs = np.array(inputs)
            dmatrix = xgb.DMatrix(inputs)
            return self._model.predict(dmatrix).tolist()

        elif framework == ModelFramework.LIGHTGBM:
            import numpy as np
            if isinstance(inputs, list):
                inputs = np.array(inputs)
            return self._model.predict(inputs).tolist()

        else:
            # Custom model - assume it has a predict method
            return self._model.predict(inputs)

    def set_preprocessor(self, fn: Callable) -> None:
        """Set preprocessing function."""
        self._preprocessor = fn

    def set_postprocessor(self, fn: Callable) -> None:
        """Set postprocessing function."""
        self._postprocessor = fn

    def warmup(self, sample_input: Any) -> None:
        """Warm up model with sample input."""
        for _ in range(self.config.warmup_requests):
            self.predict(sample_input)
        logger.info(f"Warmed up model {self.model_id}")

    def unload(self) -> None:
        """Unload model from memory."""
        self._model = None
        self._loaded = False
        logger.info(f"Unloaded model {self.model_id}")

    @staticmethod
    def compute_artifact_hash(artifact_path: str) -> str:
        """Compute hash of model artifact."""
        path = Path(artifact_path)
        hasher = hashlib.sha256()

        if path.is_file():
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
        elif path.is_dir():
            for file in sorted(path.rglob("*")):
                if file.is_file():
                    with open(file, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            hasher.update(chunk)

        return hasher.hexdigest()
