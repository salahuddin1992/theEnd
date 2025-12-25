"""
Machine Learning Pipeline - خط أنابيب التعلم الآلي
===================================================

Comprehensive ML pipeline for model serving, feature store,
versioning, A/B testing, and AutoML.

Components:
- Model Serving: Deploy and serve ML models
- Feature Store: Manage and serve features
- Model Registry: Version and manage models
- A/B Testing: Experiment with model variants
- AutoML: Automated machine learning pipelines
"""

from distributed_cluster.ml.models import (
    Model,
    ModelConfig,
    ModelFramework,
    ModelMetadata,
    ModelState,
    ModelVersion,
    PredictionResult,
)

from distributed_cluster.ml.serving import (
    InferenceRequest,
    InferenceResponse,
    ModelEndpoint,
    ModelServer,
    BatchInferenceJob,
    ServingConfig,
)

from distributed_cluster.ml.features import (
    Feature,
    FeatureGroup,
    FeatureSet,
    FeatureStore,
    FeatureVector,
    FeatureType,
    OnlineFeatureStore,
    OfflineFeatureStore,
)

from distributed_cluster.ml.registry import (
    ModelRegistry,
    ModelArtifact,
    ModelStage,
    ExperimentTracker,
    Experiment,
    Run,
)

from distributed_cluster.ml.abtesting import (
    ABTest,
    ABTestConfig,
    ABTestResult,
    ABTestManager,
    TrafficSplit,
    Variant,
)

from distributed_cluster.ml.automl import (
    AutoMLConfig,
    AutoMLJob,
    AutoMLPipeline,
    HyperparameterSearch,
    SearchSpace,
    SearchAlgorithm,
)

from distributed_cluster.ml.training import (
    TrainingConfig,
    TrainingJob,
    TrainingPipeline,
    DistributedTrainer,
    CheckpointManager,
)

__all__ = [
    # Models
    "Model",
    "ModelConfig",
    "ModelFramework",
    "ModelMetadata",
    "ModelState",
    "ModelVersion",
    "PredictionResult",
    # Serving
    "InferenceRequest",
    "InferenceResponse",
    "ModelEndpoint",
    "ModelServer",
    "BatchInferenceJob",
    "ServingConfig",
    # Features
    "Feature",
    "FeatureGroup",
    "FeatureSet",
    "FeatureStore",
    "FeatureVector",
    "FeatureType",
    "OnlineFeatureStore",
    "OfflineFeatureStore",
    # Registry
    "ModelRegistry",
    "ModelArtifact",
    "ModelStage",
    "ExperimentTracker",
    "Experiment",
    "Run",
    # A/B Testing
    "ABTest",
    "ABTestConfig",
    "ABTestResult",
    "ABTestManager",
    "TrafficSplit",
    "Variant",
    # AutoML
    "AutoMLConfig",
    "AutoMLJob",
    "AutoMLPipeline",
    "HyperparameterSearch",
    "SearchSpace",
    "SearchAlgorithm",
    # Training
    "TrainingConfig",
    "TrainingJob",
    "TrainingPipeline",
    "DistributedTrainer",
    "CheckpointManager",
]
