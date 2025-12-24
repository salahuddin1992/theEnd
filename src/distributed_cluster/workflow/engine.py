"""
Workflow Engine - محرك سير العمل
================================

Provides high-level workflow management on top of DAG execution.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    croniter = None
    CRONITER_AVAILABLE = False

from distributed_cluster.models.job import Job
from distributed_cluster.models.resources import ResourceRequirements
from distributed_cluster.scheduler.dag import (
    DAG,
    DAGBuilder,
    DAGExecutor,
    DAGStatus,
    DependencyType,
)

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """حالة سير العمل."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class TriggerType(str, Enum):
    """نوع التشغيل."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"
    EVENT = "event"


@dataclass
class WorkflowTrigger:
    """مشغل سير العمل."""

    trigger_type: TriggerType
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    # For scheduled triggers
    cron_expression: Optional[str] = None
    timezone: str = "UTC"

    # For webhook triggers
    webhook_secret: Optional[str] = None

    # For event triggers
    event_type: Optional[str] = None
    event_filter: Optional[Dict[str, Any]] = None


@dataclass
class WorkflowVersion:
    """إصدار سير العمل."""

    version_id: str
    workflow_id: str
    version_number: int
    definition: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    changelog: Optional[str] = None
    is_current: bool = False


@dataclass
class WorkflowRun:
    """تشغيل سير عمل واحد."""

    run_id: str
    workflow_id: str
    version_id: str
    dag_id: str
    status: DAGStatus = DAGStatus.PENDING
    trigger: TriggerType = TriggerType.MANUAL
    triggered_by: Optional[str] = None
    input_params: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "version_id": self.version_id,
            "dag_id": self.dag_id,
            "status": self.status.value,
            "trigger": self.trigger.value,
            "triggered_by": self.triggered_by,
            "input_params": self.input_params,
            "output_data": self.output_data,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
        }


@dataclass
class Workflow:
    """تعريف سير العمل."""

    workflow_id: str
    name: str
    description: str = ""
    status: WorkflowStatus = WorkflowStatus.DRAFT
    triggers: List[WorkflowTrigger] = field(default_factory=list)
    default_params: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    owner: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Version management
    versions: List[WorkflowVersion] = field(default_factory=list)
    current_version_id: Optional[str] = None

    # Run history
    runs: List[WorkflowRun] = field(default_factory=list)
    max_concurrent_runs: int = 5

    # Notifications
    notify_on_success: bool = False
    notify_on_failure: bool = True
    notification_channels: List[str] = field(default_factory=list)

    def get_current_version(self) -> Optional[WorkflowVersion]:
        """الحصول على الإصدار الحالي."""
        for version in self.versions:
            if version.version_id == self.current_version_id:
                return version
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "tags": self.tags,
            "owner": self.owner,
            "current_version_id": self.current_version_id,
            "max_concurrent_runs": self.max_concurrent_runs,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class WorkflowEngine:
    """
    محرك سير العمل.

    يدير تعريفات workflows وتنفيذها.
    """

    def __init__(
        self,
        dag_executor: DAGExecutor,
        on_workflow_completed: Optional[Callable[[WorkflowRun], Any]] = None,
    ):
        self.dag_executor = dag_executor
        self.on_workflow_completed = on_workflow_completed

        # Storage
        self._workflows: Dict[str, Workflow] = {}
        self._runs: Dict[str, WorkflowRun] = {}

    async def create_workflow(
        self,
        name: str,
        definition: Dict[str, Any],
        description: str = "",
        owner: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Workflow:
        """
        إنشاء workflow جديد.

        Args:
            name: اسم الـ workflow
            definition: تعريف الخطوات والتبعيات
            description: وصف
            owner: المالك
            tags: العلامات

        Returns:
            Workflow object
        """
        workflow_id = f"wf-{uuid.uuid4().hex[:12]}"

        workflow = Workflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            owner=owner,
            tags=tags or [],
        )

        # Create initial version
        version = await self._create_version(workflow, definition, "Initial version")
        workflow.current_version_id = version.version_id

        self._workflows[workflow_id] = workflow

        logger.info(f"Created workflow {workflow_id}: {name}")
        return workflow

    async def _create_version(
        self,
        workflow: Workflow,
        definition: Dict[str, Any],
        changelog: str = "",
        created_by: Optional[str] = None,
    ) -> WorkflowVersion:
        """إنشاء إصدار جديد."""
        version_number = len(workflow.versions) + 1
        version_id = f"v{version_number}-{uuid.uuid4().hex[:8]}"

        # Mark current version as not current
        for v in workflow.versions:
            v.is_current = False

        version = WorkflowVersion(
            version_id=version_id,
            workflow_id=workflow.workflow_id,
            version_number=version_number,
            definition=definition,
            changelog=changelog,
            created_by=created_by,
            is_current=True,
        )

        workflow.versions.append(version)
        return version

    async def update_workflow(
        self,
        workflow_id: str,
        definition: Dict[str, Any],
        changelog: str = "",
        updated_by: Optional[str] = None,
    ) -> WorkflowVersion:
        """
        تحديث workflow (إنشاء إصدار جديد).

        Args:
            workflow_id: معرف الـ workflow
            definition: التعريف الجديد
            changelog: سجل التغييرات
            updated_by: المحدث

        Returns:
            New version
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        version = await self._create_version(workflow, definition, changelog, updated_by)
        workflow.current_version_id = version.version_id
        workflow.updated_at = datetime.utcnow()

        logger.info(f"Updated workflow {workflow_id} to version {version.version_number}")
        return version

    async def run_workflow(
        self,
        workflow_id: str,
        params: Optional[Dict[str, Any]] = None,
        version_id: Optional[str] = None,
        trigger: TriggerType = TriggerType.MANUAL,
        triggered_by: Optional[str] = None,
    ) -> WorkflowRun:
        """
        تشغيل workflow.

        Args:
            workflow_id: معرف الـ workflow
            params: معاملات التشغيل
            version_id: إصدار معين (اختياري)
            trigger: نوع التشغيل
            triggered_by: المشغل

        Returns:
            WorkflowRun object
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValueError(f"Workflow {workflow_id} is not active")

        # Check concurrent runs
        active_runs = [r for r in workflow.runs if r.status in (DAGStatus.PENDING, DAGStatus.RUNNING)]
        if len(active_runs) >= workflow.max_concurrent_runs:
            raise ValueError(f"Maximum concurrent runs ({workflow.max_concurrent_runs}) reached")

        # Get version
        version = None
        if version_id:
            for v in workflow.versions:
                if v.version_id == version_id:
                    version = v
                    break
        else:
            version = workflow.get_current_version()

        if not version:
            raise ValueError("No version found")

        # Merge params
        merged_params = {**workflow.default_params, **(params or {})}

        # Create DAG from definition
        dag = await self._build_dag(version.definition, merged_params)

        # Create run record
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        run = WorkflowRun(
            run_id=run_id,
            workflow_id=workflow_id,
            version_id=version.version_id,
            dag_id=dag.dag_id,
            trigger=trigger,
            triggered_by=triggered_by,
            input_params=merged_params,
            started_at=datetime.utcnow(),
        )

        workflow.runs.append(run)
        self._runs[run_id] = run

        # Submit DAG
        await self.dag_executor.submit_dag(dag)
        run.status = DAGStatus.RUNNING

        logger.info(f"Started workflow run {run_id} for {workflow_id}")
        return run

    async def _build_dag(
        self,
        definition: Dict[str, Any],
        params: Dict[str, Any],
    ) -> DAG:
        """بناء DAG من التعريف."""
        dag_name = definition.get("name", "workflow")
        builder = DAGBuilder(dag_name)

        steps = definition.get("steps", [])
        job_map: Dict[str, str] = {}

        for step in steps:
            step_id = step.get("id")

            # Substitute params in command
            command = step.get("command", "")
            for key, value in params.items():
                command = command.replace(f"${{{key}}}", str(value))
                command = command.replace(f"$({key})", str(value))

            # Create job
            resources = ResourceRequirements(
                cpu_cores=step.get("cpu", 1.0),
                memory_mb=step.get("memory", 512),
                gpu_count=step.get("gpu", 0),
            )

            job = Job(
                job_id=f"job-{uuid.uuid4().hex[:12]}",
                name=step.get("name", step_id),
                command=command,
                resources=resources,
                docker_image=step.get("image"),
                environment=step.get("env", {}),
                timeout_seconds=step.get("timeout", 3600),
            )

            builder.add_job(job)
            job_map[step_id] = job.job_id

        # Add dependencies
        for step in steps:
            step_id = step.get("id")
            child_job_id = job_map.get(step_id)

            for dep in step.get("depends_on", []):
                if isinstance(dep, str):
                    parent_id = dep
                    dep_type = DependencyType.SUCCESS
                elif isinstance(dep, dict):
                    parent_id = list(dep.keys())[0]
                    dep_type = DependencyType(dep[parent_id])
                else:
                    continue

                parent_job_id = job_map.get(parent_id)
                if parent_job_id and child_job_id:
                    builder.add_dependency(parent_job_id, child_job_id, dep_type)

        return builder.build()

    async def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """الحصول على workflow."""
        return self._workflows.get(workflow_id)

    async def list_workflows(
        self,
        status: Optional[WorkflowStatus] = None,
        owner: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Workflow]:
        """قائمة الـ workflows."""
        workflows = list(self._workflows.values())

        if status:
            workflows = [w for w in workflows if w.status == status]

        if owner:
            workflows = [w for w in workflows if w.owner == owner]

        if tags:
            workflows = [w for w in workflows if any(t in w.tags for t in tags)]

        return workflows

    async def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        """الحصول على تشغيل."""
        return self._runs.get(run_id)

    async def list_runs(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[DAGStatus] = None,
        limit: int = 100,
    ) -> List[WorkflowRun]:
        """قائمة التشغيلات."""
        runs = list(self._runs.values())

        if workflow_id:
            runs = [r for r in runs if r.workflow_id == workflow_id]

        if status:
            runs = [r for r in runs if r.status == status]

        # Sort by start time, newest first
        runs.sort(key=lambda r: r.started_at or datetime.min, reverse=True)

        return runs[:limit]

    async def cancel_run(self, run_id: str) -> bool:
        """إلغاء تشغيل."""
        run = self._runs.get(run_id)
        if not run:
            return False

        if run.status not in (DAGStatus.PENDING, DAGStatus.RUNNING):
            return False

        # Cancel the DAG
        await self.dag_executor.cancel_dag(run.dag_id)
        run.status = DAGStatus.CANCELLED
        run.completed_at = datetime.utcnow()

        logger.info(f"Cancelled workflow run {run_id}")
        return True

    async def activate_workflow(self, workflow_id: str) -> bool:
        """تفعيل workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        workflow.status = WorkflowStatus.ACTIVE
        workflow.updated_at = datetime.utcnow()
        return True

    async def pause_workflow(self, workflow_id: str) -> bool:
        """إيقاف workflow مؤقتاً."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        workflow.status = WorkflowStatus.PAUSED
        workflow.updated_at = datetime.utcnow()
        return True

    async def archive_workflow(self, workflow_id: str) -> bool:
        """أرشفة workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        workflow.status = WorkflowStatus.ARCHIVED
        workflow.updated_at = datetime.utcnow()
        return True

    async def notify_dag_completed(self, dag: DAG) -> None:
        """إشعار باكتمال DAG."""
        # Find the run
        for run in self._runs.values():
            if run.dag_id == dag.dag_id:
                run.status = dag.status
                run.completed_at = datetime.utcnow()

                if run.started_at:
                    run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

                # Collect output from completed jobs
                for node in dag.nodes.values():
                    if node.result:
                        run.output_data[node.job_id] = node.result

                logger.info(f"Workflow run {run.run_id} completed with status {dag.status}")

                if self.on_workflow_completed:
                    await self.on_workflow_completed(run)

                break

    @property
    def stats(self) -> Dict[str, Any]:
        """إحصائيات."""
        workflows = list(self._workflows.values())
        runs = list(self._runs.values())

        return {
            "total_workflows": len(workflows),
            "active_workflows": len([w for w in workflows if w.status == WorkflowStatus.ACTIVE]),
            "total_runs": len(runs),
            "running_runs": len([r for r in runs if r.status == DAGStatus.RUNNING]),
            "completed_runs": len([r for r in runs if r.status == DAGStatus.SUCCEEDED]),
            "failed_runs": len([r for r in runs if r.status == DAGStatus.FAILED]),
        }


class WorkflowScheduler:
    """
    مجدول سير العمل.

    يدير تشغيل workflows حسب جداول زمنية.
    """

    def __init__(self, workflow_engine: WorkflowEngine):
        self.engine = workflow_engine
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._schedules: Dict[str, datetime] = {}  # workflow_id -> next_run

    async def start(self) -> None:
        """بدء المجدول."""
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Workflow scheduler started")

    async def stop(self) -> None:
        """إيقاف المجدول."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Workflow scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """حلقة الجدولة."""
        while self._running:
            try:
                now = datetime.utcnow()

                workflows = await self.engine.list_workflows(status=WorkflowStatus.ACTIVE)

                for workflow in workflows:
                    for trigger in workflow.triggers:
                        if not trigger.enabled:
                            continue

                        if trigger.trigger_type != TriggerType.SCHEDULED:
                            continue

                        if not trigger.cron_expression:
                            continue

                        if not CRONITER_AVAILABLE:
                            logger.warning(
                                f"croniter not installed, cannot schedule workflow {workflow.workflow_id}. "
                                "Install with: pip install croniter"
                            )
                            continue

                        # Calculate next run time
                        next_run = self._schedules.get(workflow.workflow_id)

                        if not next_run:
                            # Calculate from cron
                            cron = croniter(trigger.cron_expression, now)
                            next_run = cron.get_next(datetime)
                            self._schedules[workflow.workflow_id] = next_run

                        if now >= next_run:
                            # Time to run
                            try:
                                await self.engine.run_workflow(
                                    workflow.workflow_id,
                                    trigger=TriggerType.SCHEDULED,
                                    triggered_by="scheduler",
                                )
                                logger.info(f"Scheduled run triggered for {workflow.workflow_id}")
                            except Exception as e:
                                logger.error(f"Failed to run scheduled workflow {workflow.workflow_id}: {e}")

                            # Calculate next run
                            cron = croniter(trigger.cron_expression, now)
                            self._schedules[workflow.workflow_id] = cron.get_next(datetime)

                await asyncio.sleep(30)  # Check every 30 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)

    def get_next_run(self, workflow_id: str) -> Optional[datetime]:
        """الحصول على وقت التشغيل التالي."""
        return self._schedules.get(workflow_id)
