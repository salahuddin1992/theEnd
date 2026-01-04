"""
Model Registry - سجل النماذج
============================

Model versioning, tracking, and lifecycle management.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import Model, ModelConfig, ModelFramework, ModelMetadata, ModelState, ModelVersion

logger = logging.getLogger(__name__)


class ModelStage(str, Enum):
    """Model lifecycle stages."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


@dataclass
class ModelArtifact:
    """Model artifact metadata."""
    artifact_id: str
    model_id: str
    version_id: str
    path: str
    size_bytes: int
    hash: str

    # Storage info
    storage_type: str = "local"  # local, s3, gcs, azure
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "model_id": self.model_id,
            "version_id": self.version_id,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "hash": self.hash,
            "storage_type": self.storage_type,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Experiment:
    """ML experiment for tracking runs."""
    experiment_id: str
    name: str
    description: str = ""

    # Tags and metadata
    tags: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Associated model
    model_id: Optional[str] = None

    # Runs
    run_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "model_id": self.model_id,
            "run_ids": self.run_ids,
        }


@dataclass
class Run:
    """A single training run within an experiment."""
    run_id: str
    experiment_id: str
    name: str = ""
    status: str = "running"  # running, completed, failed, killed

    # Timing
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None

    # Parameters and metrics
    parameters: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)

    # Artifacts
    artifact_paths: List[str] = field(default_factory=list)
    model_version_id: Optional[str] = None

    # Source
    source_name: str = ""
    source_version: str = ""

    def log_param(self, key: str, value: Any) -> None:
        """Log a parameter."""
        self.parameters[key] = value

    def log_metric(self, key: str, value: float) -> None:
        """Log a metric."""
        self.metrics[key] = value

    def log_artifact(self, path: str) -> None:
        """Log an artifact."""
        self.artifact_paths.append(path)

    def set_tag(self, key: str, value: str) -> None:
        """Set a tag."""
        self.tags[key] = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "name": self.name,
            "status": self.status,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "parameters": self.parameters,
            "metrics": self.metrics,
            "tags": self.tags,
            "artifact_paths": self.artifact_paths,
            "model_version_id": self.model_version_id,
        }


class ExperimentTracker:
    """
    Experiment Tracker - متتبع التجارب.

    Tracks ML experiments, runs, parameters, and metrics.
    """

    def __init__(self, storage_path: str = "./mlruns"):
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._experiments: Dict[str, Experiment] = {}
        self._runs: Dict[str, Run] = {}
        self._active_run: Optional[Run] = None

    def create_experiment(
        self,
        name: str,
        description: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> Experiment:
        """Create a new experiment."""
        experiment = Experiment(
            experiment_id=str(uuid.uuid4()),
            name=name,
            description=description,
            tags=tags or {},
        )
        self._experiments[experiment.experiment_id] = experiment
        self._save_experiment(experiment)
        logger.info(f"Created experiment: {name}")
        return experiment

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Get an experiment by ID."""
        return self._experiments.get(experiment_id)

    def get_experiment_by_name(self, name: str) -> Optional[Experiment]:
        """Get an experiment by name."""
        for exp in self._experiments.values():
            if exp.name == name:
                return exp
        return None

    def list_experiments(self) -> List[Experiment]:
        """List all experiments."""
        return list(self._experiments.values())

    def start_run(
        self,
        experiment_id: str,
        run_name: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> Run:
        """Start a new run in an experiment."""
        if self._active_run:
            raise RuntimeError("A run is already active. End it first.")

        experiment = self._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        run = Run(
            run_id=str(uuid.uuid4()),
            experiment_id=experiment_id,
            name=run_name or f"run-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            tags=tags or {},
        )
        self._runs[run.run_id] = run
        experiment.run_ids.append(run.run_id)
        self._active_run = run

        logger.info(f"Started run: {run.name}")
        return run

    def end_run(self, status: str = "completed") -> None:
        """End the active run."""
        if not self._active_run:
            raise RuntimeError("No active run to end")

        self._active_run.status = status
        self._active_run.end_time = datetime.utcnow()
        self._save_run(self._active_run)

        logger.info(f"Ended run: {self._active_run.name} with status {status}")
        self._active_run = None

    def get_run(self, run_id: str) -> Optional[Run]:
        """Get a run by ID."""
        return self._runs.get(run_id)

    def log_param(self, key: str, value: Any) -> None:
        """Log a parameter to the active run."""
        if not self._active_run:
            raise RuntimeError("No active run")
        self._active_run.log_param(key, value)

    def log_params(self, params: Dict[str, Any]) -> None:
        """Log multiple parameters."""
        for key, value in params.items():
            self.log_param(key, value)

    def log_metric(self, key: str, value: float, step: Optional[int] = None) -> None:
        """Log a metric to the active run."""
        if not self._active_run:
            raise RuntimeError("No active run")
        self._active_run.log_metric(key, value)

    def log_metrics(self, metrics: Dict[str, float]) -> None:
        """Log multiple metrics."""
        for key, value in metrics.items():
            self.log_metric(key, value)

    def log_artifact(self, local_path: str, artifact_path: Optional[str] = None) -> None:
        """Log an artifact to the active run."""
        if not self._active_run:
            raise RuntimeError("No active run")

        src_path = Path(local_path)
        if not src_path.exists():
            raise FileNotFoundError(f"Artifact not found: {local_path}")

        # Copy to run's artifact directory
        run_artifacts = self._get_run_path(self._active_run.run_id) / "artifacts"
        run_artifacts.mkdir(parents=True, exist_ok=True)

        dest_name = artifact_path or src_path.name
        dest_path = run_artifacts / dest_name

        if src_path.is_file():
            shutil.copy2(src_path, dest_path)
        else:
            shutil.copytree(src_path, dest_path)

        self._active_run.log_artifact(str(dest_path))

    def set_tag(self, key: str, value: str) -> None:
        """Set a tag on the active run."""
        if not self._active_run:
            raise RuntimeError("No active run")
        self._active_run.set_tag(key, value)

    def _get_run_path(self, run_id: str) -> Path:
        """Get storage path for a run."""
        return self._storage_path / "runs" / run_id

    def _save_experiment(self, experiment: Experiment) -> None:
        """Save experiment to storage."""
        exp_path = self._storage_path / "experiments" / experiment.experiment_id
        exp_path.mkdir(parents=True, exist_ok=True)

        with open(exp_path / "meta.json", "w") as f:
            json.dump(experiment.to_dict(), f, indent=2)

    def _save_run(self, run: Run) -> None:
        """Save run to storage."""
        run_path = self._get_run_path(run.run_id)
        run_path.mkdir(parents=True, exist_ok=True)

        with open(run_path / "meta.json", "w") as f:
            json.dump(run.to_dict(), f, indent=2)

    def compare_runs(self, run_ids: List[str]) -> Dict[str, Any]:
        """Compare multiple runs."""
        comparison = {
            "runs": [],
            "parameters": {},
            "metrics": {},
        }

        for run_id in run_ids:
            run = self._runs.get(run_id)
            if run:
                comparison["runs"].append(run.to_dict())

                for key, value in run.parameters.items():
                    if key not in comparison["parameters"]:
                        comparison["parameters"][key] = {}
                    comparison["parameters"][key][run_id] = value

                for key, value in run.metrics.items():
                    if key not in comparison["metrics"]:
                        comparison["metrics"][key] = {}
                    comparison["metrics"][key][run_id] = value

        return comparison


class ModelRegistry:
    """
    Model Registry - سجل النماذج.

    Central registry for managing ML models, versions, and lifecycle.

    Example:
        registry = ModelRegistry()

        # Register a model
        model = registry.register_model(
            name="my-classifier",
            framework=ModelFramework.SKLEARN,
            description="Binary classifier"
        )

        # Create a version
        version = registry.create_version(
            model_id=model.model_id,
            artifact_path="./model.pkl",
            metrics={"accuracy": 0.95}
        )

        # Promote to staging
        registry.transition_stage(version.version_id, ModelStage.STAGING)

        # Promote to production
        registry.transition_stage(version.version_id, ModelStage.PRODUCTION)
    """

    def __init__(
        self,
        storage_path: str = "./model_registry",
        experiment_tracker: Optional[ExperimentTracker] = None,
    ):
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._tracker = experiment_tracker or ExperimentTracker(
            str(self._storage_path / "mlruns")
        )

        self._models: Dict[str, ModelMetadata] = {}
        self._versions: Dict[str, ModelVersion] = {}
        self._artifacts: Dict[str, ModelArtifact] = {}
        self._stage_assignments: Dict[Tuple[str, ModelStage], str] = {}  # (model_id, stage) -> version_id

        self._load_registry()

    def _load_registry(self) -> None:
        """Load registry from storage."""
        models_path = self._storage_path / "models"
        if models_path.exists():
            for model_dir in models_path.iterdir():
                if model_dir.is_dir():
                    meta_path = model_dir / "meta.json"
                    if meta_path.exists():
                        with open(meta_path) as f:
                            data = json.load(f)
                            self._models[data["name"]] = ModelMetadata.from_dict(data)

    def register_model(
        self,
        name: str,
        framework: ModelFramework = ModelFramework.CUSTOM,
        description: str = "",
        tags: Optional[List[str]] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> ModelMetadata:
        """Register a new model."""
        if name in self._models:
            return self._models[name]

        metadata = ModelMetadata(
            name=name,
            description=description,
            framework=framework,
            tags=tags or [],
            labels=labels or {},
        )

        self._models[name] = metadata
        self._save_model(name, metadata)

        logger.info(f"Registered model: {name}")
        return metadata

    def get_model(self, name: str) -> Optional[ModelMetadata]:
        """Get model metadata by name."""
        return self._models.get(name)

    def list_models(self) -> List[str]:
        """List all registered models."""
        return list(self._models.keys())

    def delete_model(self, name: str) -> None:
        """Delete a model and all its versions."""
        if name not in self._models:
            return

        # Delete all versions
        versions_to_delete = [
            v for v in self._versions.values()
            if v.model_id == name
        ]
        for version in versions_to_delete:
            self.delete_version(version.version_id)

        del self._models[name]

        model_path = self._storage_path / "models" / name
        if model_path.exists():
            shutil.rmtree(model_path)

        logger.info(f"Deleted model: {name}")

    def create_version(
        self,
        model_id: str,
        artifact_path: str,
        run_id: Optional[str] = None,
        metrics: Optional[Dict[str, float]] = None,
        config: Optional[ModelConfig] = None,
    ) -> ModelVersion:
        """Create a new model version."""
        if model_id not in self._models:
            raise ValueError(f"Model not registered: {model_id}")

        model_meta = self._models[model_id]

        # Get version number
        existing_versions = [
            v for v in self._versions.values()
            if v.model_id == model_id
        ]
        version_number = len(existing_versions) + 1

        # Compute artifact hash
        artifact_hash = Model.compute_artifact_hash(artifact_path)
        artifact_size = self._get_artifact_size(artifact_path)

        # Create version
        version_id = str(uuid.uuid4())
        version = ModelVersion(
            version_id=version_id,
            model_id=model_id,
            version_number=version_number,
            state=ModelState.READY,
            artifact_path=artifact_path,
            artifact_hash=artifact_hash,
            artifact_size_bytes=artifact_size,
            metadata=model_meta,
            config=config or ModelConfig(),
            training_job_id=run_id,
        )

        if metrics:
            version.metadata.metrics = metrics

        self._versions[version_id] = version

        # Copy artifact to registry
        self._store_artifact(model_id, version_id, artifact_path)

        logger.info(f"Created version {version_number} for model {model_id}")
        return version

    def get_version(self, version_id: str) -> Optional[ModelVersion]:
        """Get a model version by ID."""
        return self._versions.get(version_id)

    def get_latest_version(self, model_id: str) -> Optional[ModelVersion]:
        """Get the latest version of a model."""
        versions = [
            v for v in self._versions.values()
            if v.model_id == model_id
        ]
        if not versions:
            return None
        return max(versions, key=lambda v: v.version_number)

    def get_version_by_stage(
        self,
        model_id: str,
        stage: ModelStage,
    ) -> Optional[ModelVersion]:
        """Get the model version assigned to a stage."""
        version_id = self._stage_assignments.get((model_id, stage))
        if version_id:
            return self._versions.get(version_id)
        return None

    def list_versions(
        self,
        model_id: str,
        stage: Optional[ModelStage] = None,
    ) -> List[ModelVersion]:
        """List all versions of a model."""
        versions = [
            v for v in self._versions.values()
            if v.model_id == model_id
        ]

        if stage:
            version_id = self._stage_assignments.get((model_id, stage))
            versions = [v for v in versions if v.version_id == version_id]

        return sorted(versions, key=lambda v: v.version_number, reverse=True)

    def delete_version(self, version_id: str) -> None:
        """Delete a model version."""
        version = self._versions.get(version_id)
        if not version:
            return

        # Remove stage assignments
        for key in list(self._stage_assignments.keys()):
            if self._stage_assignments[key] == version_id:
                del self._stage_assignments[key]

        del self._versions[version_id]

        # Delete artifact
        artifact_path = self._get_version_path(version.model_id, version_id)
        if artifact_path.exists():
            shutil.rmtree(artifact_path)

        logger.info(f"Deleted version: {version_id}")

    def transition_stage(
        self,
        version_id: str,
        stage: ModelStage,
        archive_existing: bool = True,
    ) -> None:
        """Transition a model version to a new stage."""
        version = self._versions.get(version_id)
        if not version:
            raise ValueError(f"Version not found: {version_id}")

        model_id = version.model_id

        # Archive existing version in this stage
        if archive_existing:
            existing_version_id = self._stage_assignments.get((model_id, stage))
            if existing_version_id and existing_version_id != version_id:
                # Move to archived
                self._stage_assignments[(model_id, ModelStage.ARCHIVED)] = existing_version_id

        # Assign new version to stage
        self._stage_assignments[(model_id, stage)] = version_id

        if stage == ModelStage.PRODUCTION:
            version.deployed_at = datetime.utcnow()
            version.state = ModelState.DEPLOYED

        logger.info(f"Transitioned version {version_id} to stage {stage.value}")

    def load_model(
        self,
        model_id: str,
        version_id: Optional[str] = None,
        stage: Optional[ModelStage] = None,
    ) -> Model:
        """Load a model from the registry."""
        metadata = self._models.get(model_id)
        if not metadata:
            raise ValueError(f"Model not found: {model_id}")

        # Get version
        if version_id:
            version = self._versions.get(version_id)
        elif stage:
            version = self.get_version_by_stage(model_id, stage)
        else:
            version = self.get_latest_version(model_id)

        if not version:
            raise ValueError(f"No version found for model: {model_id}")

        # Create and load model
        model = Model(
            model_id=model_id,
            metadata=metadata,
            config=version.config,
        )

        artifact_path = self._get_version_path(model_id, version.version_id) / "artifacts"
        model.load(str(artifact_path))

        return model

    def _save_model(self, name: str, metadata: ModelMetadata) -> None:
        """Save model metadata to storage."""
        model_path = self._storage_path / "models" / name
        model_path.mkdir(parents=True, exist_ok=True)

        with open(model_path / "meta.json", "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)

    def _get_version_path(self, model_id: str, version_id: str) -> Path:
        """Get storage path for a version."""
        return self._storage_path / "models" / model_id / "versions" / version_id

    def _store_artifact(
        self,
        model_id: str,
        version_id: str,
        artifact_path: str,
    ) -> ModelArtifact:
        """Store model artifact in registry."""
        src_path = Path(artifact_path)
        dest_path = self._get_version_path(model_id, version_id) / "artifacts"
        dest_path.mkdir(parents=True, exist_ok=True)

        if src_path.is_file():
            shutil.copy2(src_path, dest_path / src_path.name)
        else:
            shutil.copytree(src_path, dest_path, dirs_exist_ok=True)

        artifact = ModelArtifact(
            artifact_id=str(uuid.uuid4()),
            model_id=model_id,
            version_id=version_id,
            path=str(dest_path),
            size_bytes=self._get_artifact_size(artifact_path),
            hash=Model.compute_artifact_hash(artifact_path),
        )
        self._artifacts[artifact.artifact_id] = artifact

        return artifact

    def _get_artifact_size(self, path: str) -> int:
        """Get total size of artifact."""
        path = Path(path)
        if path.is_file():
            return path.stat().st_size

        total = 0
        for file in path.rglob("*"):
            if file.is_file():
                total += file.stat().st_size
        return total

    @property
    def tracker(self) -> ExperimentTracker:
        """Get the experiment tracker."""
        return self._tracker
