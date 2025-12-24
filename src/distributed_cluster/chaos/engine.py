# -*- coding: utf-8 -*-
"""
Chaos Engine for NebulaCompute.

Core chaos engineering engine for orchestrating fault injection
experiments and measuring system resilience.

محرك هندسة الفوضى لـ NebulaCompute.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TargetType(str, Enum):
    """Target type for chaos experiments."""

    WORKER = "worker"
    MASTER = "master"
    JOB = "job"
    NETWORK = "network"
    STORAGE = "storage"
    GPU = "gpu"
    CLUSTER = "cluster"


class ExperimentStatus(str, Enum):
    """Experiment status."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class ImpactLevel(str, Enum):
    """Experiment impact level."""

    LOW = "low"  # Minor disruption
    MEDIUM = "medium"  # Noticeable impact
    HIGH = "high"  # Significant disruption
    CRITICAL = "critical"  # System-wide impact


@dataclass
class ExperimentHypothesis:
    """
    Experiment hypothesis.

    فرضية التجربة.
    """

    description: str
    expected_behavior: str
    success_criteria: Dict[str, Any] = field(default_factory=dict)
    failure_indicators: List[str] = field(default_factory=list)


@dataclass
class ExperimentResult:
    """
    Experiment result.

    نتيجة التجربة.
    """

    success: bool
    hypothesis_validated: bool
    observations: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    recovery_time_seconds: Optional[float] = None
    impact_assessment: Optional[str] = None
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "hypothesis_validated": self.hypothesis_validated,
            "observations": self.observations,
            "metrics": self.metrics,
            "recovery_time_seconds": self.recovery_time_seconds,
            "impact_assessment": self.impact_assessment,
            "recommendations": self.recommendations,
        }


@dataclass
class ChaosExperiment:
    """
    Chaos experiment definition.

    تعريف تجربة الفوضى.
    """

    experiment_id: str
    name: str
    description: str
    target_type: TargetType
    target_selector: Dict[str, Any]  # How to select targets
    fault_type: str
    fault_config: Dict[str, Any]
    hypothesis: ExperimentHypothesis
    duration_seconds: int = 300
    cooldown_seconds: int = 60
    impact_level: ImpactLevel = ImpactLevel.LOW
    status: ExperimentStatus = ExperimentStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    rollback_config: Dict[str, Any] = field(default_factory=dict)
    abort_conditions: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[ExperimentResult] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Check if experiment is active."""
        return self.status in [ExperimentStatus.RUNNING, ExperimentStatus.PAUSED]

    @property
    def duration_elapsed(self) -> float:
        """Get elapsed duration in seconds."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "description": self.description,
            "target_type": self.target_type.value,
            "target_selector": self.target_selector,
            "fault_type": self.fault_type,
            "fault_config": self.fault_config,
            "hypothesis": {
                "description": self.hypothesis.description,
                "expected_behavior": self.hypothesis.expected_behavior,
                "success_criteria": self.hypothesis.success_criteria,
            },
            "duration_seconds": self.duration_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "impact_level": self.impact_level.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_by": self.created_by,
            "tags": self.tags,
            "result": self.result.to_dict() if self.result else None,
            "metadata": self.metadata,
        }


class ChaosEngine:
    """
    Chaos engineering engine.

    محرك هندسة الفوضى.

    Features:
    - Experiment management
    - Fault injection orchestration
    - Impact monitoring
    - Automatic rollback
    - Results analysis
    - Safety controls
    """

    def __init__(
        self,
        enable_safety_controls: bool = True,
        max_concurrent_experiments: int = 1,
        require_approval: bool = True,
        blast_radius_limit: float = 0.25,  # Max % of targets affected
        emergency_stop_callback: Optional[Callable] = None,
    ):
        """
        Initialize Chaos Engine.

        Args:
            enable_safety_controls: Enable safety mechanisms
            max_concurrent_experiments: Max simultaneous experiments
            require_approval: Require approval before execution
            blast_radius_limit: Max percentage of targets to affect
            emergency_stop_callback: Called on emergency stop
        """
        self.safety_enabled = enable_safety_controls
        self.max_concurrent = max_concurrent_experiments
        self.require_approval = require_approval
        self.blast_radius_limit = blast_radius_limit
        self.emergency_stop_callback = emergency_stop_callback

        # State
        self._experiments: Dict[str, ChaosExperiment] = {}
        self._running_experiments: Set[str] = set()
        self._experiment_tasks: Dict[str, asyncio.Task] = {}
        self._paused: bool = False
        self._emergency_stopped: bool = False
        self._lock = asyncio.Lock()

        # Fault injector (would be imported from faults module)
        self._fault_injector = None

        # Statistics
        self._stats = {
            "total_experiments": 0,
            "successful_experiments": 0,
            "failed_experiments": 0,
            "aborted_experiments": 0,
            "total_faults_injected": 0,
            "total_duration_seconds": 0.0,
        }

    def set_fault_injector(self, injector) -> None:
        """Set fault injector instance."""
        self._fault_injector = injector

    async def create_experiment(
        self,
        name: str,
        description: str,
        target_type: TargetType,
        target_selector: Dict[str, Any],
        fault_type: str,
        fault_config: Dict[str, Any],
        hypothesis: ExperimentHypothesis,
        duration_seconds: int = 300,
        impact_level: ImpactLevel = ImpactLevel.LOW,
        created_by: Optional[str] = None,
        tags: Optional[List[str]] = None,
        abort_conditions: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChaosExperiment:
        """
        Create a chaos experiment.

        إنشاء تجربة فوضى.
        """
        experiment = ChaosExperiment(
            experiment_id=str(uuid.uuid4()),
            name=name,
            description=description,
            target_type=target_type,
            target_selector=target_selector,
            fault_type=fault_type,
            fault_config=fault_config,
            hypothesis=hypothesis,
            duration_seconds=duration_seconds,
            impact_level=impact_level,
            created_by=created_by,
            tags=tags or [],
            abort_conditions=abort_conditions or [],
            metadata=metadata or {},
        )

        async with self._lock:
            self._experiments[experiment.experiment_id] = experiment
            self._stats["total_experiments"] += 1

        logger.info(f"Created chaos experiment: {name} ({experiment.experiment_id})")
        return experiment

    async def approve_experiment(
        self,
        experiment_id: str,
        approved_by: str,
    ) -> bool:
        """
        Approve an experiment for execution.

        الموافقة على تجربة للتنفيذ.
        """
        async with self._lock:
            experiment = self._experiments.get(experiment_id)
            if not experiment:
                return False

            if experiment.status != ExperimentStatus.DRAFT:
                return False

            experiment.status = ExperimentStatus.SCHEDULED
            experiment.metadata["approved_by"] = approved_by
            experiment.metadata["approved_at"] = datetime.utcnow().isoformat()

        logger.info(f"Experiment {experiment_id} approved by {approved_by}")
        return True

    async def run_experiment(
        self,
        experiment_id: str,
        wait: bool = True,
    ) -> Optional[ExperimentResult]:
        """
        Run a chaos experiment.

        تشغيل تجربة فوضى.
        """
        async with self._lock:
            experiment = self._experiments.get(experiment_id)
            if not experiment:
                raise ValueError(f"Experiment {experiment_id} not found")

            # Safety checks
            if self._emergency_stopped:
                raise RuntimeError("Chaos engine is in emergency stop mode")

            if self._paused:
                raise RuntimeError("Chaos engine is paused")

            if self.require_approval and experiment.status == ExperimentStatus.DRAFT:
                raise RuntimeError("Experiment requires approval")

            if len(self._running_experiments) >= self.max_concurrent:
                raise RuntimeError(
                    f"Maximum concurrent experiments ({self.max_concurrent}) reached"
                )

            # Validate blast radius
            if self.safety_enabled:
                await self._validate_blast_radius(experiment)

            # Start experiment
            experiment.status = ExperimentStatus.RUNNING
            experiment.started_at = datetime.utcnow()
            self._running_experiments.add(experiment_id)

        logger.info(f"Starting chaos experiment: {experiment.name}")

        # Create experiment task
        task = asyncio.create_task(self._execute_experiment(experiment))
        self._experiment_tasks[experiment_id] = task

        if wait:
            result = await task
            return result
        else:
            return None

    async def _execute_experiment(
        self,
        experiment: ChaosExperiment,
    ) -> ExperimentResult:
        """Execute the experiment."""
        observations = []
        metrics = {}
        time.monotonic()

        try:
            # Pre-experiment metrics
            pre_metrics = await self._collect_metrics()
            metrics["pre_experiment"] = pre_metrics

            observations.append(f"Experiment started at {datetime.utcnow().isoformat()}")

            # Inject fault
            if self._fault_injector:
                await self._fault_injector.inject(
                    experiment.fault_type,
                    experiment.fault_config,
                    experiment.target_selector,
                )
                observations.append(f"Fault injected: {experiment.fault_type}")
                self._stats["total_faults_injected"] += 1

            # Wait for duration while monitoring
            duration_remaining = experiment.duration_seconds
            abort_triggered = False

            while duration_remaining > 0 and not abort_triggered:
                await asyncio.sleep(min(10, duration_remaining))
                duration_remaining -= 10

                # Check abort conditions
                for condition in experiment.abort_conditions:
                    if await self._check_abort_condition(condition):
                        abort_triggered = True
                        observations.append(
                            f"Abort condition triggered: {condition.get('name', 'unknown')}"
                        )
                        break

                # Check for pause/stop
                if self._paused or self._emergency_stopped:
                    abort_triggered = True
                    observations.append("Experiment paused/stopped by operator")
                    break

            # Remove fault
            if self._fault_injector:
                await self._fault_injector.remove(
                    experiment.fault_type,
                    experiment.fault_config,
                    experiment.target_selector,
                )
                observations.append("Fault removed")

            # Wait for recovery
            recovery_start = time.monotonic()
            recovered = await self._wait_for_recovery(experiment)
            recovery_time = time.monotonic() - recovery_start

            if recovered:
                observations.append(f"System recovered in {recovery_time:.1f}s")
            else:
                observations.append("System did not fully recover")

            # Post-experiment metrics
            post_metrics = await self._collect_metrics()
            metrics["post_experiment"] = post_metrics
            metrics["recovery_time_seconds"] = recovery_time

            # Validate hypothesis
            hypothesis_validated = await self._validate_hypothesis(
                experiment.hypothesis, metrics, observations
            )

            # Create result
            result = ExperimentResult(
                success=not abort_triggered and recovered,
                hypothesis_validated=hypothesis_validated,
                observations=observations,
                metrics=metrics,
                recovery_time_seconds=recovery_time,
                impact_assessment=self._assess_impact(metrics),
                recommendations=self._generate_recommendations(
                    experiment, hypothesis_validated, metrics
                ),
            )

            experiment.result = result
            experiment.status = (
                ExperimentStatus.COMPLETED
                if result.success
                else ExperimentStatus.FAILED
            )

            if result.success:
                self._stats["successful_experiments"] += 1
            else:
                self._stats["failed_experiments"] += 1

            return result

        except asyncio.CancelledError:
            experiment.status = ExperimentStatus.ABORTED
            self._stats["aborted_experiments"] += 1

            # Cleanup fault
            if self._fault_injector:
                await self._fault_injector.remove(
                    experiment.fault_type,
                    experiment.fault_config,
                    experiment.target_selector,
                )

            result = ExperimentResult(
                success=False,
                hypothesis_validated=False,
                observations=observations + ["Experiment aborted"],
                metrics=metrics,
            )
            experiment.result = result
            return result

        except Exception as e:
            experiment.status = ExperimentStatus.FAILED
            self._stats["failed_experiments"] += 1

            # Cleanup fault on error
            if self._fault_injector:
                try:
                    await self._fault_injector.remove(
                        experiment.fault_type,
                        experiment.fault_config,
                        experiment.target_selector,
                    )
                except Exception:
                    pass

            result = ExperimentResult(
                success=False,
                hypothesis_validated=False,
                observations=observations + [f"Error: {str(e)}"],
                metrics=metrics,
            )
            experiment.result = result
            logger.error(f"Experiment {experiment.experiment_id} failed: {e}")
            return result

        finally:
            experiment.completed_at = datetime.utcnow()
            self._stats["total_duration_seconds"] += experiment.duration_elapsed
            self._running_experiments.discard(experiment.experiment_id)
            self._experiment_tasks.pop(experiment.experiment_id, None)

    async def _validate_blast_radius(self, experiment: ChaosExperiment) -> None:
        """Validate experiment blast radius is within limits."""
        # In real implementation, would calculate affected targets
        # and compare to total targets
        pass

    async def _collect_metrics(self) -> Dict[str, Any]:
        """Collect system metrics."""
        # In real implementation, would collect:
        # - Worker health
        # - Job success rates
        # - Response times
        # - Error rates
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "healthy_workers": 5,
            "running_jobs": 10,
            "error_rate": 0.01,
        }

    async def _check_abort_condition(self, condition: Dict[str, Any]) -> bool:
        """Check if abort condition is met."""
        # In real implementation, would evaluate condition
        return False

    async def _wait_for_recovery(self, experiment: ChaosExperiment) -> bool:
        """Wait for system to recover."""
        # Wait for cooldown period
        await asyncio.sleep(min(experiment.cooldown_seconds, 60))
        return True

    async def _validate_hypothesis(
        self,
        hypothesis: ExperimentHypothesis,
        metrics: Dict[str, Any],
        observations: List[str],
    ) -> bool:
        """Validate experiment hypothesis."""
        # In real implementation, would check success criteria
        # against collected metrics
        return True

    def _assess_impact(self, metrics: Dict[str, Any]) -> str:
        """Assess experiment impact."""
        return "Minimal impact observed"

    def _generate_recommendations(
        self,
        experiment: ChaosExperiment,
        hypothesis_validated: bool,
        metrics: Dict[str, Any],
    ) -> List[str]:
        """Generate recommendations based on results."""
        recommendations = []

        if not hypothesis_validated:
            recommendations.append(
                "System behavior did not match expected. "
                "Review fault tolerance mechanisms."
            )

        recovery_time = metrics.get("recovery_time_seconds", 0)
        if recovery_time > 60:
            recommendations.append(
                f"Recovery time ({recovery_time:.0f}s) exceeds 60s target. "
                "Consider improving failover mechanisms."
            )

        return recommendations

    async def abort_experiment(self, experiment_id: str) -> bool:
        """
        Abort a running experiment.

        إيقاف تجربة جارية.
        """
        async with self._lock:
            if experiment_id not in self._running_experiments:
                return False

            task = self._experiment_tasks.get(experiment_id)
            if task:
                task.cancel()

        logger.warning(f"Aborted experiment {experiment_id}")
        return True

    async def emergency_stop(self) -> int:
        """
        Emergency stop all experiments.

        إيقاف طوارئ لجميع التجارب.
        """
        self._emergency_stopped = True
        stopped = 0

        async with self._lock:
            for experiment_id in list(self._running_experiments):
                task = self._experiment_tasks.get(experiment_id)
                if task:
                    task.cancel()
                    stopped += 1

        if self.emergency_stop_callback:
            try:
                result = self.emergency_stop_callback()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Emergency stop callback error: {e}")

        logger.critical(f"Emergency stop: stopped {stopped} experiments")
        return stopped

    async def reset_emergency_stop(self) -> None:
        """Reset emergency stop state."""
        self._emergency_stopped = False
        logger.info("Emergency stop state reset")

    async def pause_all(self) -> None:
        """Pause all experiments."""
        self._paused = True
        logger.info("Chaos engine paused")

    async def resume_all(self) -> None:
        """Resume all experiments."""
        self._paused = False
        logger.info("Chaos engine resumed")

    async def get_experiment(
        self,
        experiment_id: str,
    ) -> Optional[ChaosExperiment]:
        """Get experiment by ID."""
        return self._experiments.get(experiment_id)

    async def list_experiments(
        self,
        status: Optional[ExperimentStatus] = None,
        target_type: Optional[TargetType] = None,
        tags: Optional[List[str]] = None,
    ) -> List[ChaosExperiment]:
        """List experiments with optional filtering."""
        experiments = list(self._experiments.values())

        if status:
            experiments = [e for e in experiments if e.status == status]

        if target_type:
            experiments = [e for e in experiments if e.target_type == target_type]

        if tags:
            experiments = [
                e for e in experiments if any(t in e.tags for t in tags)
            ]

        return experiments

    async def delete_experiment(self, experiment_id: str) -> bool:
        """Delete an experiment."""
        async with self._lock:
            if experiment_id in self._running_experiments:
                return False

            if experiment_id in self._experiments:
                del self._experiments[experiment_id]
                return True

        return False

    async def get_statistics(self) -> Dict[str, Any]:
        """Get chaos engine statistics."""
        return {
            **self._stats,
            "running_experiments": len(self._running_experiments),
            "total_stored_experiments": len(self._experiments),
            "safety_enabled": self.safety_enabled,
            "paused": self._paused,
            "emergency_stopped": self._emergency_stopped,
        }

    async def shutdown(self) -> None:
        """Shutdown chaos engine."""
        # Abort all running experiments
        for experiment_id in list(self._running_experiments):
            await self.abort_experiment(experiment_id)

        logger.info("Chaos Engine shutdown complete")
