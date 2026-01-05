"""
AutoML Pipeline - خط أنابيب التعلم الآلي التلقائي
==================================================

Automated machine learning for hyperparameter search and model selection.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class SearchAlgorithm(str, Enum):
    """Hyperparameter search algorithms."""

    GRID = "grid"
    RANDOM = "random"
    BAYESIAN = "bayesian"
    HYPERBAND = "hyperband"
    EVOLUTIONARY = "evolutionary"


class ParameterType(str, Enum):
    """Parameter types for search space."""

    FLOAT = "float"
    INT = "int"
    CATEGORICAL = "categorical"
    LOG_FLOAT = "log_float"
    LOG_INT = "log_int"


class AutoMLJobStatus(str, Enum):
    """AutoML job status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ParameterSpace:
    """Definition of a single parameter's search space."""

    name: str
    param_type: ParameterType
    low: Optional[float] = None
    high: Optional[float] = None
    choices: Optional[List[Any]] = None
    default: Optional[Any] = None
    log_base: float = 10.0

    def sample(self) -> Any:
        """Sample a value from the parameter space."""
        if self.param_type == ParameterType.CATEGORICAL:
            return random.choice(self.choices)

        elif self.param_type == ParameterType.FLOAT:
            return random.uniform(self.low, self.high)

        elif self.param_type == ParameterType.INT:
            return random.randint(int(self.low), int(self.high))

        elif self.param_type == ParameterType.LOG_FLOAT:
            import math

            log_low = math.log(self.low, self.log_base)
            log_high = math.log(self.high, self.log_base)
            return self.log_base ** random.uniform(log_low, log_high)

        elif self.param_type == ParameterType.LOG_INT:
            import math

            log_low = math.log(self.low, self.log_base)
            log_high = math.log(self.high, self.log_base)
            return int(self.log_base ** random.uniform(log_low, log_high))

        return self.default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "param_type": self.param_type.value,
            "low": self.low,
            "high": self.high,
            "choices": self.choices,
            "default": self.default,
        }


@dataclass
class SearchSpace:
    """Complete hyperparameter search space."""

    parameters: List[ParameterSpace]
    constraints: Optional[List[Callable[[Dict], bool]]] = None

    def sample(self) -> Dict[str, Any]:
        """Sample a configuration from the search space."""
        max_attempts = 100
        for _ in range(max_attempts):
            config = {p.name: p.sample() for p in self.parameters}

            # Check constraints
            if self.constraints:
                if all(c(config) for c in self.constraints):
                    return config
            else:
                return config

        # Return without constraint check if we can't satisfy them
        return {p.name: p.sample() for p in self.parameters}

    def grid(self, n_points: int = 10) -> List[Dict[str, Any]]:
        """Generate grid of configurations."""
        import itertools

        grids = []
        for p in self.parameters:
            if p.param_type == ParameterType.CATEGORICAL:
                grids.append(p.choices)
            elif p.param_type in (ParameterType.FLOAT, ParameterType.LOG_FLOAT):
                import numpy as np

                if p.param_type == ParameterType.LOG_FLOAT:
                    grids.append(np.geomspace(p.low, p.high, n_points).tolist())
                else:
                    grids.append(np.linspace(p.low, p.high, n_points).tolist())
            elif p.param_type in (ParameterType.INT, ParameterType.LOG_INT):
                import numpy as np

                vals = np.linspace(p.low, p.high, min(n_points, int(p.high - p.low) + 1))
                grids.append([int(v) for v in vals])

        configs = []
        for combo in itertools.product(*grids):
            config = {p.name: v for p, v in zip(self.parameters, combo)}
            if not self.constraints or all(c(config) for c in self.constraints):
                configs.append(config)

        return configs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameters": [p.to_dict() for p in self.parameters],
        }


@dataclass
class Trial:
    """A single hyperparameter trial."""

    trial_id: str
    config: Dict[str, Any]
    status: str = "pending"

    # Results
    metrics: Dict[str, float] = field(default_factory=dict)
    objective_value: Optional[float] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Error handling
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "config": self.config,
            "status": self.status,
            "metrics": self.metrics,
            "objective_value": self.objective_value,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


class SearchStrategy(ABC):
    """Abstract search strategy."""

    @abstractmethod
    def suggest(self, trials: List[Trial]) -> Dict[str, Any]:
        """Suggest next configuration to try."""
        pass

    @abstractmethod
    def is_complete(self, trials: List[Trial]) -> bool:
        """Check if search is complete."""
        pass


class RandomSearch(SearchStrategy):
    """Random search strategy."""

    def __init__(self, search_space: SearchSpace, max_trials: int = 100):
        self.search_space = search_space
        self.max_trials = max_trials

    def suggest(self, trials: List[Trial]) -> Dict[str, Any]:
        return self.search_space.sample()

    def is_complete(self, trials: List[Trial]) -> bool:
        completed = sum(1 for t in trials if t.status == "completed")
        return completed >= self.max_trials


class GridSearch(SearchStrategy):
    """Grid search strategy."""

    def __init__(self, search_space: SearchSpace, n_points: int = 10):
        self.search_space = search_space
        self.configs = search_space.grid(n_points)
        self._index = 0

    def suggest(self, trials: List[Trial]) -> Dict[str, Any]:
        if self._index >= len(self.configs):
            return self.search_space.sample()

        config = self.configs[self._index]
        self._index += 1
        return config

    def is_complete(self, trials: List[Trial]) -> bool:
        completed = sum(1 for t in trials if t.status == "completed")
        return completed >= len(self.configs)


class BayesianSearch(SearchStrategy):
    """Bayesian optimization search strategy."""

    def __init__(
        self,
        search_space: SearchSpace,
        max_trials: int = 100,
        n_initial: int = 10,
    ):
        self.search_space = search_space
        self.max_trials = max_trials
        self.n_initial = n_initial
        self._model = None

    def suggest(self, trials: List[Trial]) -> Dict[str, Any]:
        completed = [t for t in trials if t.status == "completed" and t.objective_value is not None]

        # Initial random exploration
        if len(completed) < self.n_initial:
            return self.search_space.sample()

        # Try to use surrogate model
        try:
            return self._suggest_with_model(completed)
        except Exception:
            return self.search_space.sample()

    def _suggest_with_model(self, trials: List[Trial]) -> Dict[str, Any]:
        """Use Gaussian Process to suggest next point."""
        # Simplified version - in production use scikit-optimize or similar
        import numpy as np

        # Convert trials to arrays
        X = []
        y = []
        for t in trials:
            x = [t.config.get(p.name, p.default) for p in self.search_space.parameters]
            X.append(x)
            y.append(t.objective_value)

        X = np.array(X)
        y = np.array(y)

        # Simple acquisition: sample randomly and pick best expected improvement
        min(y)
        candidates = [self.search_space.sample() for _ in range(100)]

        # For now, just return random candidate (full GP would go here)
        return random.choice(candidates)

    def is_complete(self, trials: List[Trial]) -> bool:
        completed = sum(1 for t in trials if t.status == "completed")
        return completed >= self.max_trials


@dataclass
class HyperparameterSearch:
    """Hyperparameter search configuration and results."""

    search_id: str
    search_space: SearchSpace
    algorithm: SearchAlgorithm = SearchAlgorithm.RANDOM
    max_trials: int = 100
    objective_metric: str = "loss"
    objective_direction: str = "minimize"  # minimize or maximize

    # Status
    status: str = "pending"
    trials: List[Trial] = field(default_factory=list)

    # Best result
    best_trial_id: Optional[str] = None
    best_config: Optional[Dict[str, Any]] = None
    best_objective: Optional[float] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def get_best_trial(self) -> Optional[Trial]:
        """Get the best trial."""
        completed = [t for t in self.trials if t.status == "completed" and t.objective_value is not None]
        if not completed:
            return None

        if self.objective_direction == "minimize":
            return min(completed, key=lambda t: t.objective_value)
        else:
            return max(completed, key=lambda t: t.objective_value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "search_id": self.search_id,
            "search_space": self.search_space.to_dict(),
            "algorithm": self.algorithm.value,
            "max_trials": self.max_trials,
            "objective_metric": self.objective_metric,
            "status": self.status,
            "trials": [t.to_dict() for t in self.trials],
            "best_config": self.best_config,
            "best_objective": self.best_objective,
        }


@dataclass
class AutoMLConfig:
    """AutoML pipeline configuration."""

    name: str
    task_type: str = "classification"  # classification, regression
    target_column: str = ""
    feature_columns: List[str] = field(default_factory=list)

    # Search settings
    search_algorithm: SearchAlgorithm = SearchAlgorithm.RANDOM
    max_trials: int = 100
    time_budget_minutes: int = 60
    early_stopping_rounds: int = 10

    # Model selection
    models: List[str] = field(default_factory=lambda: ["xgboost", "lightgbm", "random_forest"])

    # Preprocessing
    auto_preprocessing: bool = True
    handle_missing: str = "auto"  # auto, drop, impute
    handle_categorical: str = "auto"  # auto, onehot, label

    # Validation
    cv_folds: int = 5
    validation_split: float = 0.2
    stratify: bool = True

    # Objective
    objective_metric: str = "accuracy"  # accuracy, f1, auc, rmse, mae
    objective_direction: str = "maximize"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "task_type": self.task_type,
            "search_algorithm": self.search_algorithm.value,
            "max_trials": self.max_trials,
            "time_budget_minutes": self.time_budget_minutes,
            "models": self.models,
            "objective_metric": self.objective_metric,
        }


@dataclass
class AutoMLJob:
    """AutoML job instance."""

    job_id: str
    config: AutoMLConfig
    status: AutoMLJobStatus = AutoMLJobStatus.PENDING

    # Data
    train_data_path: str = ""
    test_data_path: Optional[str] = None

    # Progress
    current_trial: int = 0
    best_score: Optional[float] = None
    best_model_path: Optional[str] = None

    # Hyperparameter search
    searches: List[HyperparameterSearch] = field(default_factory=list)

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "current_trial": self.current_trial,
            "best_score": self.best_score,
            "best_model_path": self.best_model_path,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class AutoMLPipeline:
    """
    AutoML Pipeline - خط أنابيب التعلم الآلي التلقائي.

    Automated machine learning for model selection and hyperparameter tuning.

    Example:
        pipeline = AutoMLPipeline()

        # Create AutoML job
        config = AutoMLConfig(
            name="my-automl-job",
            task_type="classification",
            target_column="label",
            max_trials=50,
            time_budget_minutes=30,
        )

        job = pipeline.create_job(config, train_data="data.csv")

        # Run the pipeline
        await pipeline.run(job.job_id)

        # Get best model
        best_model = pipeline.get_best_model(job.job_id)
    """

    def __init__(self, storage_path: str = "./automl"):
        self._storage_path = storage_path
        self._jobs: Dict[str, AutoMLJob] = {}
        self._model_configs: Dict[str, SearchSpace] = self._init_model_configs()

    def _init_model_configs(self) -> Dict[str, SearchSpace]:
        """Initialize default search spaces for models."""
        return {
            "xgboost": SearchSpace(
                parameters=[
                    ParameterSpace("n_estimators", ParameterType.INT, 50, 500),
                    ParameterSpace("max_depth", ParameterType.INT, 3, 10),
                    ParameterSpace("learning_rate", ParameterType.LOG_FLOAT, 0.01, 0.3),
                    ParameterSpace("subsample", ParameterType.FLOAT, 0.5, 1.0),
                    ParameterSpace("colsample_bytree", ParameterType.FLOAT, 0.5, 1.0),
                    ParameterSpace("min_child_weight", ParameterType.INT, 1, 10),
                ]
            ),
            "lightgbm": SearchSpace(
                parameters=[
                    ParameterSpace("n_estimators", ParameterType.INT, 50, 500),
                    ParameterSpace("max_depth", ParameterType.INT, 3, 10),
                    ParameterSpace("learning_rate", ParameterType.LOG_FLOAT, 0.01, 0.3),
                    ParameterSpace("num_leaves", ParameterType.INT, 20, 150),
                    ParameterSpace("subsample", ParameterType.FLOAT, 0.5, 1.0),
                    ParameterSpace("colsample_bytree", ParameterType.FLOAT, 0.5, 1.0),
                ]
            ),
            "random_forest": SearchSpace(
                parameters=[
                    ParameterSpace("n_estimators", ParameterType.INT, 50, 500),
                    ParameterSpace("max_depth", ParameterType.INT, 3, 20),
                    ParameterSpace("min_samples_split", ParameterType.INT, 2, 20),
                    ParameterSpace("min_samples_leaf", ParameterType.INT, 1, 10),
                    ParameterSpace("max_features", ParameterType.CATEGORICAL, choices=["sqrt", "log2", None]),
                ]
            ),
            "logistic_regression": SearchSpace(
                parameters=[
                    ParameterSpace("C", ParameterType.LOG_FLOAT, 0.001, 100),
                    ParameterSpace("penalty", ParameterType.CATEGORICAL, choices=["l1", "l2"]),
                    ParameterSpace("solver", ParameterType.CATEGORICAL, choices=["liblinear", "saga"]),
                ]
            ),
        }

    def create_job(
        self,
        config: AutoMLConfig,
        train_data: str,
        test_data: Optional[str] = None,
    ) -> AutoMLJob:
        """Create a new AutoML job."""
        job = AutoMLJob(
            job_id=str(uuid.uuid4()),
            config=config,
            train_data_path=train_data,
            test_data_path=test_data,
        )

        # Create hyperparameter searches for each model
        for model_name in config.models:
            if model_name in self._model_configs:
                search = HyperparameterSearch(
                    search_id=f"{job.job_id}-{model_name}",
                    search_space=self._model_configs[model_name],
                    algorithm=config.search_algorithm,
                    max_trials=config.max_trials // len(config.models),
                    objective_metric=config.objective_metric,
                    objective_direction=config.objective_direction,
                )
                job.searches.append(search)

        self._jobs[job.job_id] = job
        logger.info(f"Created AutoML job: {job.job_id}")
        return job

    def get_job(self, job_id: str) -> Optional[AutoMLJob]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        status: Optional[AutoMLJobStatus] = None,
    ) -> List[AutoMLJob]:
        """List all jobs."""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    async def run(self, job_id: str) -> AutoMLJob:
        """Run an AutoML job."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        job.status = AutoMLJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)

        try:
            # Run searches for each model type
            for search in job.searches:
                await self._run_search(job, search)

            # Find overall best
            best_trial = None
            for search in job.searches:
                trial = search.get_best_trial()
                if trial:
                    if best_trial is None:
                        best_trial = trial
                    elif job.config.objective_direction == "minimize":
                        if trial.objective_value < best_trial.objective_value:
                            best_trial = trial
                    else:
                        if trial.objective_value > best_trial.objective_value:
                            best_trial = trial

            if best_trial:
                job.best_score = best_trial.objective_value

            job.status = AutoMLJobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            logger.info(f"Completed AutoML job: {job_id}")

        except Exception as e:
            job.status = AutoMLJobStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.now(timezone.utc)
            logger.error(f"AutoML job failed: {job_id}, error: {e}")

        return job

    async def _run_search(
        self,
        job: AutoMLJob,
        search: HyperparameterSearch,
    ) -> None:
        """Run a hyperparameter search."""
        search.status = "running"
        search.started_at = datetime.now(timezone.utc)

        # Create search strategy
        if search.algorithm == SearchAlgorithm.RANDOM:
            strategy = RandomSearch(search.search_space, search.max_trials)
        elif search.algorithm == SearchAlgorithm.GRID:
            strategy = GridSearch(search.search_space)
        elif search.algorithm == SearchAlgorithm.BAYESIAN:
            strategy = BayesianSearch(search.search_space, search.max_trials)
        else:
            strategy = RandomSearch(search.search_space, search.max_trials)

        # Run trials
        while not strategy.is_complete(search.trials):
            # Check time budget
            if job.config.time_budget_minutes > 0:
                elapsed = (datetime.now(timezone.utc) - job.started_at).total_seconds() / 60
                if elapsed >= job.config.time_budget_minutes:
                    break

            # Get next config
            config = strategy.suggest(search.trials)

            # Run trial
            trial = Trial(
                trial_id=str(uuid.uuid4()),
                config=config,
            )
            search.trials.append(trial)
            job.current_trial += 1

            await self._run_trial(job, search, trial)

            # Update best
            best = search.get_best_trial()
            if best:
                search.best_trial_id = best.trial_id
                search.best_config = best.config
                search.best_objective = best.objective_value

            # Early stopping check
            if len(search.trials) >= job.config.early_stopping_rounds:
                recent = search.trials[-job.config.early_stopping_rounds :]
                if all(t.objective_value == recent[0].objective_value for t in recent if t.objective_value):
                    break

        search.status = "completed"
        search.completed_at = datetime.now(timezone.utc)

    async def _run_trial(
        self,
        job: AutoMLJob,
        search: HyperparameterSearch,
        trial: Trial,
    ) -> None:
        """Run a single trial."""
        import time

        trial.status = "running"
        trial.started_at = datetime.now(timezone.utc)
        start_time = time.time()

        try:
            # Simulate model training (in production, this would actually train)
            await asyncio.sleep(0.1)  # Placeholder

            # Mock metrics
            trial.objective_value = random.uniform(0.5, 1.0)
            trial.metrics = {
                job.config.objective_metric: trial.objective_value,
                "train_time": time.time() - start_time,
            }
            trial.status = "completed"

        except Exception as e:
            trial.status = "failed"
            trial.error = str(e)

        finally:
            trial.completed_at = datetime.now(timezone.utc)
            trial.duration_seconds = time.time() - start_time

    def cancel_job(self, job_id: str) -> None:
        """Cancel an AutoML job."""
        job = self._jobs.get(job_id)
        if job:
            job.status = AutoMLJobStatus.CANCELLED
            job.completed_at = datetime.now(timezone.utc)

    def get_best_model(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the best model from a completed job."""
        job = self._jobs.get(job_id)
        if not job or job.status != AutoMLJobStatus.COMPLETED:
            return None

        best_trial = None
        best_model_type = None

        for search in job.searches:
            trial = search.get_best_trial()
            if trial:
                if best_trial is None:
                    best_trial = trial
                    best_model_type = search.search_id.split("-")[-1]
                elif job.config.objective_direction == "minimize":
                    if trial.objective_value < best_trial.objective_value:
                        best_trial = trial
                        best_model_type = search.search_id.split("-")[-1]
                else:
                    if trial.objective_value > best_trial.objective_value:
                        best_trial = trial
                        best_model_type = search.search_id.split("-")[-1]

        if best_trial:
            return {
                "model_type": best_model_type,
                "config": best_trial.config,
                "metrics": best_trial.metrics,
                "objective_value": best_trial.objective_value,
            }

        return None
