# -*- coding: utf-8 -*-
"""
Migration Coordinator for NebulaCompute.

Coordinates live migration across the cluster, handling
multi-job migrations and dependency management.

منسق النقل الحي للكلستر.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .manager import (
    MigrationManager,
    MigrationMode,
    MigrationPriority,
    MigrationState,
)

logger = logging.getLogger(__name__)


class MigrationTrigger(str, Enum):
    """Migration trigger reason."""

    MAINTENANCE = "maintenance"  # Scheduled maintenance
    LOAD_BALANCING = "load_balancing"  # Load rebalancing
    SPOT_PREEMPTION = "spot_preemption"  # Spot instance termination
    RESOURCE_PRESSURE = "resource_pressure"  # Resource exhaustion
    FAILURE_RECOVERY = "failure_recovery"  # Node failure
    USER_REQUESTED = "user_requested"  # Manual request
    POLICY = "policy"  # Automated policy


class PlanStatus(str, Enum):
    """Migration plan status."""

    DRAFT = "draft"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MigrationStep:
    """
    Single migration step in a plan.

    خطوة واحدة في خطة النقل.
    """

    step_id: str
    job_id: str
    source_worker: str
    target_worker: str
    mode: MigrationMode
    priority: MigrationPriority
    dependencies: List[str] = field(default_factory=list)  # Step IDs
    status: MigrationState = MigrationState.PENDING
    request_id: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "job_id": self.job_id,
            "source_worker": self.source_worker,
            "target_worker": self.target_worker,
            "mode": self.mode.value,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "request_id": self.request_id,
            "error_message": self.error_message,
        }


@dataclass
class MigrationPlan:
    """
    Migration plan containing multiple steps.

    خطة النقل تحتوي على خطوات متعددة.
    """

    plan_id: str
    name: str
    trigger: MigrationTrigger
    steps: List[MigrationStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    description: str = ""
    rollback_on_failure: bool = True
    max_parallel: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def pending_steps(self) -> List[MigrationStep]:
        """Get pending steps."""
        return [s for s in self.steps if s.status == MigrationState.PENDING]

    @property
    def completed_steps(self) -> List[MigrationStep]:
        """Get completed steps."""
        return [s for s in self.steps if s.status == MigrationState.COMPLETED]

    @property
    def failed_steps(self) -> List[MigrationStep]:
        """Get failed steps."""
        return [s for s in self.steps if s.status == MigrationState.FAILED]

    @property
    def progress_percent(self) -> float:
        """Calculate plan progress."""
        if not self.steps:
            return 0.0
        return (len(self.completed_steps) / len(self.steps)) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "trigger": self.trigger.value,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_by": self.created_by,
            "description": self.description,
            "progress_percent": self.progress_percent,
            "rollback_on_failure": self.rollback_on_failure,
            "max_parallel": self.max_parallel,
            "metadata": self.metadata,
        }


@dataclass
class MigrationResult:
    """
    Migration execution result.

    نتيجة تنفيذ النقل.
    """

    plan_id: str
    success: bool
    total_steps: int
    completed_steps: int
    failed_steps: int
    total_duration_seconds: float
    total_downtime_ms: int
    total_bytes_transferred: int
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "plan_id": self.plan_id,
            "success": self.success,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "total_duration_seconds": self.total_duration_seconds,
            "total_downtime_ms": self.total_downtime_ms,
            "total_bytes_transferred": self.total_bytes_transferred,
            "errors": self.errors,
        }


class MigrationCoordinator:
    """
    Coordinates complex migration scenarios.

    منسق سيناريوهات النقل المعقدة.

    Features:
    - Multi-job migration planning
    - Dependency-aware execution
    - Maintenance window scheduling
    - Load-balanced target selection
    - Rollback orchestration
    - Progress monitoring
    """

    def __init__(
        self,
        migration_manager: MigrationManager,
        enable_auto_planning: bool = True,
        maintenance_window_hours: Tuple[int, int] = (2, 6),  # 2 AM - 6 AM
    ):
        """
        Initialize Migration Coordinator.

        Args:
            migration_manager: Migration manager instance
            enable_auto_planning: Enable automatic migration planning
            maintenance_window_hours: Preferred maintenance hours
        """
        self.migration_manager = migration_manager
        self.enable_auto_planning = enable_auto_planning
        self.maintenance_window = maintenance_window_hours

        # State
        self._plans: Dict[str, MigrationPlan] = {}
        self._executing_plans: Set[str] = set()
        self._scheduled_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

        # Callbacks
        self._on_plan_complete: Optional[Callable] = None
        self._on_step_complete: Optional[Callable] = None

        # Worker state (would be populated from cluster state)
        self._worker_loads: Dict[str, float] = {}
        self._worker_capacity: Dict[str, Dict[str, int]] = {}

    def set_callbacks(
        self,
        on_plan_complete: Optional[Callable] = None,
        on_step_complete: Optional[Callable] = None,
    ) -> None:
        """Set coordinator callbacks."""
        self._on_plan_complete = on_plan_complete
        self._on_step_complete = on_step_complete

    async def create_maintenance_plan(
        self,
        worker_id: str,
        name: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
        created_by: Optional[str] = None,
    ) -> MigrationPlan:
        """
        Create a maintenance migration plan for a worker.

        إنشاء خطة نقل للصيانة.

        Args:
            worker_id: Worker to evacuate
            name: Plan name
            scheduled_at: Scheduled execution time
            created_by: Creator identity

        Returns:
            Created MigrationPlan
        """
        import uuid

        plan = MigrationPlan(
            plan_id=str(uuid.uuid4()),
            name=name or f"Maintenance: {worker_id}",
            trigger=MigrationTrigger.MAINTENANCE,
            scheduled_at=scheduled_at,
            created_by=created_by,
            description=f"Evacuate all jobs from {worker_id} for maintenance",
        )

        # Get jobs running on worker (simulated)
        jobs = await self._get_worker_jobs(worker_id)

        # Find targets for each job
        for job_id in jobs:
            target = await self._select_migration_target(job_id, exclude=[worker_id])
            if target:
                step = MigrationStep(
                    step_id=str(uuid.uuid4()),
                    job_id=job_id,
                    source_worker=worker_id,
                    target_worker=target,
                    mode=MigrationMode.PRE_COPY,
                    priority=MigrationPriority.NORMAL,
                )
                plan.steps.append(step)

        async with self._lock:
            self._plans[plan.plan_id] = plan

        logger.info(f"Created maintenance plan {plan.plan_id} with {len(plan.steps)} steps")

        return plan

    async def create_load_balance_plan(
        self,
        name: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> MigrationPlan:
        """
        Create a load balancing migration plan.

        إنشاء خطة نقل لموازنة الحمل.
        """
        import uuid

        plan = MigrationPlan(
            plan_id=str(uuid.uuid4()),
            name=name or "Load Balancing",
            trigger=MigrationTrigger.LOAD_BALANCING,
            created_by=created_by,
            description="Rebalance workload across workers",
        )

        # Calculate load imbalance (simulated)
        migrations = await self._calculate_load_balance_migrations()

        for job_id, source, target in migrations:
            step = MigrationStep(
                step_id=str(uuid.uuid4()),
                job_id=job_id,
                source_worker=source,
                target_worker=target,
                mode=MigrationMode.PRE_COPY,
                priority=MigrationPriority.LOW,
            )
            plan.steps.append(step)

        async with self._lock:
            self._plans[plan.plan_id] = plan

        return plan

    async def create_spot_preemption_plan(
        self,
        worker_id: str,
        deadline_seconds: int = 120,
    ) -> MigrationPlan:
        """
        Create emergency plan for spot instance preemption.

        إنشاء خطة طوارئ لإنهاء Spot Instance.
        """
        import uuid

        plan = MigrationPlan(
            plan_id=str(uuid.uuid4()),
            name=f"Spot Preemption: {worker_id}",
            trigger=MigrationTrigger.SPOT_PREEMPTION,
            description=f"Emergency evacuation of {worker_id} (deadline: {deadline_seconds}s)",
            rollback_on_failure=False,  # No time for rollback
            max_parallel=10,  # Maximize parallelism
        )

        # Get jobs and create high-priority migrations
        jobs = await self._get_worker_jobs(worker_id)

        for job_id in jobs:
            target = await self._select_migration_target(
                job_id,
                exclude=[worker_id],
                prefer_on_demand=True,
            )
            if target:
                step = MigrationStep(
                    step_id=str(uuid.uuid4()),
                    job_id=job_id,
                    source_worker=worker_id,
                    target_worker=target,
                    mode=MigrationMode.POST_COPY,  # Fastest
                    priority=MigrationPriority.URGENT,
                )
                plan.steps.append(step)

        plan.status = PlanStatus.APPROVED  # Auto-approve emergency plans

        async with self._lock:
            self._plans[plan.plan_id] = plan

        logger.warning(
            f"Created emergency preemption plan {plan.plan_id} " f"for {worker_id} with {len(plan.steps)} jobs"
        )

        return plan

    async def approve_plan(self, plan_id: str, approved_by: str) -> bool:
        """
        Approve a migration plan.

        الموافقة على خطة النقل.
        """
        async with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return False

            if plan.status != PlanStatus.DRAFT:
                logger.warning(f"Plan {plan_id} is not in draft status")
                return False

            plan.status = PlanStatus.APPROVED
            plan.metadata["approved_by"] = approved_by
            plan.metadata["approved_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"Plan {plan_id} approved by {approved_by}")
        return True

    async def execute_plan(
        self,
        plan_id: str,
        wait: bool = True,
    ) -> Optional[MigrationResult]:
        """
        Execute a migration plan.

        تنفيذ خطة النقل.

        Args:
            plan_id: Plan to execute
            wait: Wait for completion

        Returns:
            MigrationResult if wait=True
        """
        async with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise ValueError(f"Plan {plan_id} not found")

            if plan.status not in [PlanStatus.APPROVED, PlanStatus.DRAFT]:
                raise ValueError(f"Plan {plan_id} cannot be executed: {plan.status}")

            if plan_id in self._executing_plans:
                raise ValueError(f"Plan {plan_id} is already executing")

            plan.status = PlanStatus.EXECUTING
            plan.started_at = datetime.now(timezone.utc)
            self._executing_plans.add(plan_id)

        logger.info(f"Executing migration plan {plan_id} ({len(plan.steps)} steps)")

        try:
            result = await self._execute_plan_steps(plan)

            plan.status = PlanStatus.COMPLETED if result.success else PlanStatus.FAILED
            plan.completed_at = datetime.now(timezone.utc)

            if self._on_plan_complete:
                await self._safe_callback(self._on_plan_complete, plan, result)

            return result

        except Exception as e:
            plan.status = PlanStatus.FAILED
            plan.completed_at = datetime.now(timezone.utc)
            logger.error(f"Plan {plan_id} execution failed: {e}")

            return MigrationResult(
                plan_id=plan_id,
                success=False,
                total_steps=len(plan.steps),
                completed_steps=len(plan.completed_steps),
                failed_steps=len(plan.failed_steps),
                total_duration_seconds=(plan.completed_at - plan.started_at).total_seconds(),
                total_downtime_ms=0,
                total_bytes_transferred=0,
                errors=[str(e)],
            )

        finally:
            self._executing_plans.discard(plan_id)

    async def _execute_plan_steps(self, plan: MigrationPlan) -> MigrationResult:
        """Execute plan steps with dependency handling."""
        completed_steps: Set[str] = set()
        failed = False
        errors: List[str] = []
        total_downtime = 0
        total_bytes = 0

        while plan.pending_steps and not failed:
            # Find executable steps (all dependencies satisfied)
            executable = [
                step for step in plan.pending_steps if all(dep in completed_steps for dep in step.dependencies)
            ]

            if not executable:
                errors.append("Deadlock: no executable steps")
                failed = True
                break

            # Execute up to max_parallel steps
            batch = executable[: plan.max_parallel]

            # Start migrations
            tasks = []
            for step in batch:
                task = asyncio.create_task(self._execute_step(step))
                tasks.append((step, task))

            # Wait for batch completion
            for step, task in tasks:
                try:
                    request_id = await task
                    step.request_id = request_id

                    # Wait for migration to complete
                    while True:
                        record = await self.migration_manager.get_migration_status(request_id)
                        if record is None:
                            step.status = MigrationState.FAILED
                            step.error_message = "Migration record not found"
                            break

                        if record.progress.state == MigrationState.COMPLETED:
                            step.status = MigrationState.COMPLETED
                            completed_steps.add(step.step_id)
                            total_downtime += record.progress.downtime_ms
                            total_bytes += record.progress.bytes_transferred

                            if self._on_step_complete:
                                await self._safe_callback(self._on_step_complete, plan, step)
                            break

                        if record.progress.state == MigrationState.FAILED:
                            step.status = MigrationState.FAILED
                            step.error_message = record.progress.error_message
                            errors.append(f"Step {step.step_id} failed: {step.error_message}")

                            if plan.rollback_on_failure:
                                failed = True
                            break

                        await asyncio.sleep(0.5)

                except Exception as e:
                    step.status = MigrationState.FAILED
                    step.error_message = str(e)
                    errors.append(f"Step {step.step_id}: {e}")

                    if plan.rollback_on_failure:
                        failed = True

        # Calculate result
        duration = 0.0
        if plan.started_at:
            end = plan.completed_at or datetime.now(timezone.utc)
            duration = (end - plan.started_at).total_seconds()

        return MigrationResult(
            plan_id=plan.plan_id,
            success=not failed and len(plan.failed_steps) == 0,
            total_steps=len(plan.steps),
            completed_steps=len(completed_steps),
            failed_steps=len(plan.failed_steps),
            total_duration_seconds=duration,
            total_downtime_ms=total_downtime,
            total_bytes_transferred=total_bytes,
            errors=errors,
        )

    async def _execute_step(self, step: MigrationStep) -> str:
        """Execute a single migration step."""
        request = await self.migration_manager.request_migration(
            job_id=step.job_id,
            source_worker=step.source_worker,
            target_worker=step.target_worker,
            mode=step.mode,
            priority=step.priority,
            reason=f"Plan step: {step.step_id}",
        )
        return request.request_id

    async def schedule_plan(
        self,
        plan_id: str,
        scheduled_time: datetime,
    ) -> bool:
        """
        Schedule a plan for later execution.

        جدولة خطة للتنفيذ لاحقاً.
        """
        async with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return False

            plan.scheduled_at = scheduled_time

            # Create scheduled task
            delay = (scheduled_time - datetime.now(timezone.utc)).total_seconds()
            if delay > 0:
                task = asyncio.create_task(self._scheduled_execution(plan_id, delay))
                self._scheduled_tasks[plan_id] = task

        logger.info(f"Plan {plan_id} scheduled for {scheduled_time}")
        return True

    async def _scheduled_execution(self, plan_id: str, delay: float) -> None:
        """Execute plan after delay."""
        await asyncio.sleep(delay)
        await self.execute_plan(plan_id)

    async def cancel_plan(self, plan_id: str) -> bool:
        """
        Cancel a migration plan.

        إلغاء خطة النقل.
        """
        async with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return False

            if plan.status == PlanStatus.EXECUTING:
                # Cancel active migrations
                for step in plan.steps:
                    if step.request_id:
                        await self.migration_manager.cancel_migration(step.request_id)

            plan.status = PlanStatus.CANCELLED

            # Cancel scheduled task
            if plan_id in self._scheduled_tasks:
                self._scheduled_tasks[plan_id].cancel()
                del self._scheduled_tasks[plan_id]

        logger.info(f"Plan {plan_id} cancelled")
        return True

    async def _get_worker_jobs(self, worker_id: str) -> List[str]:
        """Get jobs running on a worker (simulated)."""
        # In real implementation, would query cluster state
        return [f"job-{i}" for i in range(3)]

    async def _select_migration_target(
        self,
        job_id: str,
        exclude: List[str] = None,
        prefer_on_demand: bool = False,
    ) -> Optional[str]:
        """Select target worker for migration."""
        # In real implementation, would analyze:
        # - Resource availability
        # - Network proximity
        # - Worker health
        # - Load balance
        exclude = exclude or []

        # Simulated worker selection
        available = ["worker-1", "worker-2", "worker-3"]
        for worker in available:
            if worker not in exclude:
                return worker

        return None

    async def _calculate_load_balance_migrations(
        self,
    ) -> List[Tuple[str, str, str]]:
        """Calculate migrations needed for load balancing."""
        # In real implementation, would:
        # - Calculate average load
        # - Identify overloaded workers
        # - Select jobs to migrate
        # - Find underloaded targets
        return []

    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute callback."""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Callback error: {e}")

    async def get_plan(self, plan_id: str) -> Optional[MigrationPlan]:
        """Get migration plan."""
        return self._plans.get(plan_id)

    async def list_plans(
        self,
        status: Optional[PlanStatus] = None,
    ) -> List[MigrationPlan]:
        """List migration plans."""
        plans = list(self._plans.values())
        if status:
            plans = [p for p in plans if p.status == status]
        return plans

    async def delete_plan(self, plan_id: str) -> bool:
        """Delete a migration plan."""
        async with self._lock:
            if plan_id in self._executing_plans:
                return False
            if plan_id in self._plans:
                del self._plans[plan_id]
                return True
        return False

    async def get_statistics(self) -> Dict[str, Any]:
        """Get coordinator statistics."""
        return {
            "total_plans": len(self._plans),
            "executing_plans": len(self._executing_plans),
            "scheduled_plans": len(self._scheduled_tasks),
            "plans_by_status": {
                status.value: len([p for p in self._plans.values() if p.status == status]) for status in PlanStatus
            },
            "plans_by_trigger": {
                trigger.value: len([p for p in self._plans.values() if p.trigger == trigger])
                for trigger in MigrationTrigger
            },
        }

    async def shutdown(self) -> None:
        """Shutdown coordinator."""
        # Cancel scheduled tasks
        for task in self._scheduled_tasks.values():
            task.cancel()
        self._scheduled_tasks.clear()

        logger.info("Migration Coordinator shutdown complete")
