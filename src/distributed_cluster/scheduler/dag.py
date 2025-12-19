"""
Job Dependencies & DAG Execution
================================

نظام تبعيات المهام:
- تعريف التبعيات بين المهام
- تنفيذ DAG (Directed Acyclic Graph)
- Topological sorting
- Parallel execution of independent jobs
- Failure propagation
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from distributed_cluster.models.job import Job, JobStatus

logger = logging.getLogger(__name__)


class DependencyType(str, Enum):
    """نوع التبعية."""

    SUCCESS = "success"  # يعمل فقط إذا نجح الـ parent
    COMPLETION = "completion"  # يعمل بعد اكتمال الـ parent (نجاح أو فشل)
    FAILURE = "failure"  # يعمل فقط إذا فشل الـ parent


class DAGStatus(str, Enum):
    """حالة الـ DAG."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"  # بعض المهام نجحت وبعضها فشلت


@dataclass
class JobDependency:
    """تبعية بين مهمتين."""

    parent_job_id: str
    child_job_id: str
    dependency_type: DependencyType = DependencyType.SUCCESS


@dataclass
class DAGNode:
    """عقدة في الـ DAG."""

    job_id: str
    job: Optional[Job] = None
    status: JobStatus = JobStatus.PENDING
    parents: Set[str] = field(default_factory=set)
    children: Set[str] = field(default_factory=set)
    dependency_types: Dict[str, DependencyType] = field(default_factory=dict)  # parent_id -> type
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None


@dataclass
class DAG:
    """
    Directed Acyclic Graph للمهام.

    يمثل workflow من المهام المترابطة.
    """

    dag_id: str
    name: str
    nodes: Dict[str, DAGNode] = field(default_factory=dict)
    status: DAGStatus = DAGStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_job(self, job: Job) -> DAGNode:
        """إضافة مهمة للـ DAG."""
        node = DAGNode(job_id=job.job_id, job=job)
        self.nodes[job.job_id] = node
        return node

    def add_dependency(
        self,
        parent_id: str,
        child_id: str,
        dependency_type: DependencyType = DependencyType.SUCCESS,
    ) -> None:
        """إضافة تبعية."""
        if parent_id not in self.nodes or child_id not in self.nodes:
            raise ValueError("Both jobs must exist in DAG")

        if parent_id == child_id:
            raise ValueError("Job cannot depend on itself")

        parent = self.nodes[parent_id]
        child = self.nodes[child_id]

        parent.children.add(child_id)
        child.parents.add(parent_id)
        child.dependency_types[parent_id] = dependency_type

    def get_root_nodes(self) -> List[DAGNode]:
        """الحصول على العقد الجذرية (بدون parents)."""
        return [node for node in self.nodes.values() if not node.parents]

    def get_leaf_nodes(self) -> List[DAGNode]:
        """الحصول على العقد الورقية (بدون children)."""
        return [node for node in self.nodes.values() if not node.children]

    def get_ready_nodes(self) -> List[DAGNode]:
        """الحصول على العقد الجاهزة للتنفيذ."""
        ready = []

        for node in self.nodes.values():
            if node.status != JobStatus.PENDING:
                continue

            # Check if all parents are satisfied
            all_satisfied = True
            for parent_id in node.parents:
                parent = self.nodes[parent_id]
                dep_type = node.dependency_types.get(parent_id, DependencyType.SUCCESS)

                if dep_type == DependencyType.SUCCESS:
                    if parent.status != JobStatus.COMPLETED:
                        all_satisfied = False
                        break
                elif dep_type == DependencyType.COMPLETION:
                    if parent.status not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                        all_satisfied = False
                        break
                elif dep_type == DependencyType.FAILURE:
                    if parent.status != JobStatus.FAILED:
                        all_satisfied = False
                        break

            if all_satisfied:
                ready.append(node)

        return ready

    def is_valid(self) -> tuple[bool, str]:
        """التحقق من صحة الـ DAG (لا يحتوي cycles)."""
        # Kahn's algorithm for cycle detection
        in_degree = {node_id: len(node.parents) for node_id, node in self.nodes.items()}
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        visited = 0

        while queue:
            node_id = queue.pop(0)
            visited += 1

            node = self.nodes[node_id]
            for child_id in node.children:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

        if visited != len(self.nodes):
            return False, "DAG contains cycles"

        return True, ""

    def topological_sort(self) -> List[str]:
        """ترتيب طوبولوجي للعقد."""
        in_degree = {node_id: len(node.parents) for node_id, node in self.nodes.items()}
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node_id = queue.pop(0)
            result.append(node_id)

            node = self.nodes[node_id]
            for child_id in node.children:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

        return result

    def get_execution_levels(self) -> List[List[str]]:
        """
        تقسيم العقد إلى مستويات للتنفيذ المتوازي.

        كل مستوى يحتوي عقد يمكن تنفيذها بالتوازي.
        """
        levels = []
        remaining = set(self.nodes.keys())
        completed = set()

        while remaining:
            # Find nodes whose parents are all completed
            level = []
            for node_id in remaining:
                node = self.nodes[node_id]
                if node.parents.issubset(completed):
                    level.append(node_id)

            if not level:
                # Cycle detected or invalid state
                break

            levels.append(level)
            for node_id in level:
                remaining.remove(node_id)
                completed.add(node_id)

        return levels


class DAGExecutor:
    """
    منفذ الـ DAG.

    يدير تنفيذ المهام المترابطة بالترتيب الصحيح.
    """

    def __init__(
        self,
        submit_job: Callable[[Job], Awaitable[str]],
        get_job_status: Callable[[str], Awaitable[JobStatus]],
        on_dag_completed: Optional[Callable[[DAG], Awaitable[None]]] = None,
        on_job_ready: Optional[Callable[[Job, DAG], Awaitable[None]]] = None,
        max_parallel_jobs: int = 10,
    ):
        self.submit_job = submit_job
        self.get_job_status = get_job_status
        self.on_dag_completed = on_dag_completed
        self.on_job_ready = on_job_ready
        self.max_parallel_jobs = max_parallel_jobs

        # Active DAGs
        self._dags: Dict[str, DAG] = {}
        self._running_jobs: Dict[str, str] = {}  # job_id -> dag_id

        # Background processor
        self._processor_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """بدء المنفذ."""
        self._running = True
        self._processor_task = asyncio.create_task(self._process_dags())
        logger.info("DAG executor started")

    async def stop(self) -> None:
        """إيقاف المنفذ."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("DAG executor stopped")

    async def submit_dag(self, dag: DAG) -> str:
        """
        إرسال DAG للتنفيذ.

        Args:
            dag: الـ DAG

        Returns:
            dag_id
        """
        # Validate DAG
        valid, error = dag.is_valid()
        if not valid:
            raise ValueError(f"Invalid DAG: {error}")

        # Store DAG
        self._dags[dag.dag_id] = dag
        dag.status = DAGStatus.RUNNING
        dag.started_at = datetime.utcnow()

        logger.info(f"DAG {dag.dag_id} submitted with {len(dag.nodes)} jobs")

        # Start root jobs immediately
        await self._schedule_ready_jobs(dag)

        return dag.dag_id

    async def get_dag(self, dag_id: str) -> Optional[DAG]:
        """الحصول على DAG."""
        return self._dags.get(dag_id)

    async def cancel_dag(self, dag_id: str) -> bool:
        """إلغاء DAG."""
        dag = self._dags.get(dag_id)
        if not dag:
            return False

        dag.status = DAGStatus.CANCELLED

        # Cancel pending jobs
        for node in dag.nodes.values():
            if node.status == JobStatus.PENDING:
                node.status = JobStatus.CANCELLED

        logger.info(f"DAG {dag_id} cancelled")
        return True

    async def notify_job_completed(
        self,
        job_id: str,
        status: JobStatus,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        إشعار باكتمال مهمة.

        Args:
            job_id: معرف المهمة
            status: الحالة النهائية
            result: نتيجة التنفيذ
        """
        dag_id = self._running_jobs.pop(job_id, None)
        if not dag_id:
            return

        dag = self._dags.get(dag_id)
        if not dag:
            return

        node = dag.nodes.get(job_id)
        if not node:
            return

        # Update node
        node.status = status
        node.completed_at = datetime.utcnow()
        node.result = result

        logger.info(f"Job {job_id} in DAG {dag_id} completed with status {status}")

        # Handle failure propagation
        if status == JobStatus.FAILED:
            await self._handle_failure(dag, node)

        # Schedule dependent jobs
        await self._schedule_ready_jobs(dag)

        # Check if DAG is complete
        await self._check_dag_completion(dag)

    async def _schedule_ready_jobs(self, dag: DAG) -> None:
        """جدولة المهام الجاهزة."""
        if dag.status not in (DAGStatus.RUNNING, DAGStatus.PENDING):
            return

        ready_nodes = dag.get_ready_nodes()

        for node in ready_nodes[: self.max_parallel_jobs]:
            # Skip if dependencies not satisfied due to failure
            should_skip = False
            for parent_id in node.parents:
                parent = dag.nodes[parent_id]
                dep_type = node.dependency_types.get(parent_id, DependencyType.SUCCESS)

                if dep_type == DependencyType.SUCCESS and parent.status == JobStatus.FAILED:
                    should_skip = True
                    break
                elif dep_type == DependencyType.FAILURE and parent.status == JobStatus.COMPLETED:
                    should_skip = True
                    break

            if should_skip:
                node.status = JobStatus.CANCELLED
                logger.info(f"Job {node.job_id} skipped due to dependency failure")
                continue

            # Submit job
            if node.job:
                node.status = JobStatus.SCHEDULED
                node.started_at = datetime.utcnow()
                self._running_jobs[node.job_id] = dag.dag_id

                try:
                    await self.submit_job(node.job)
                    logger.info(f"Job {node.job_id} submitted from DAG {dag.dag_id}")

                    if self.on_job_ready:
                        await self.on_job_ready(node.job, dag)

                except Exception as e:
                    logger.error(f"Failed to submit job {node.job_id}: {e}")
                    node.status = JobStatus.FAILED
                    node.result = {"error": str(e)}

    async def _handle_failure(self, dag: DAG, failed_node: DAGNode) -> None:
        """معالجة فشل مهمة."""
        # Cancel dependent jobs that require success
        queue = list(failed_node.children)

        while queue:
            child_id = queue.pop(0)
            child = dag.nodes.get(child_id)
            if not child:
                continue

            dep_type = child.dependency_types.get(failed_node.job_id, DependencyType.SUCCESS)

            if dep_type == DependencyType.SUCCESS:
                if child.status == JobStatus.PENDING:
                    child.status = JobStatus.CANCELLED
                    logger.info(f"Job {child_id} cancelled due to parent failure")
                    # Propagate to children
                    queue.extend(child.children)

    async def _check_dag_completion(self, dag: DAG) -> None:
        """التحقق من اكتمال الـ DAG."""
        completed_statuses = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}

        all_done = all(node.status in completed_statuses for node in dag.nodes.values())

        if not all_done:
            return

        # Determine final status
        statuses = [node.status for node in dag.nodes.values()]

        if all(s == JobStatus.COMPLETED for s in statuses):
            dag.status = DAGStatus.SUCCEEDED
        elif all(s == JobStatus.CANCELLED for s in statuses):
            dag.status = DAGStatus.CANCELLED
        elif all(s in (JobStatus.FAILED, JobStatus.CANCELLED) for s in statuses):
            dag.status = DAGStatus.FAILED
        else:
            dag.status = DAGStatus.PARTIAL

        dag.completed_at = datetime.utcnow()

        logger.info(f"DAG {dag.dag_id} completed with status {dag.status}")

        if self.on_dag_completed:
            await self.on_dag_completed(dag)

    async def _process_dags(self) -> None:
        """معالجة الـ DAGs النشطة."""
        while self._running:
            try:
                # Update job statuses
                for job_id, dag_id in list(self._running_jobs.items()):
                    try:
                        status = await self.get_job_status(job_id)
                        if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                            await self.notify_job_completed(job_id, status)
                    except Exception as e:
                        logger.error(f"Error checking job {job_id}: {e}")

                await asyncio.sleep(2)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"DAG processor error: {e}")
                await asyncio.sleep(5)

    @property
    def active_dags(self) -> List[DAG]:
        """الـ DAGs النشطة."""
        return [dag for dag in self._dags.values() if dag.status == DAGStatus.RUNNING]

    @property
    def stats(self) -> Dict[str, Any]:
        """إحصائيات."""
        return {
            "total_dags": len(self._dags),
            "active_dags": len(self.active_dags),
            "running_jobs": len(self._running_jobs),
        }


# =============================================================================
# DAG Builder - بناء DAG بطريقة سهلة
# =============================================================================


class DAGBuilder:
    """
    بناء DAG بطريقة fluent.

    Usage:
        dag = (DAGBuilder("my-workflow")
            .add_job(job1)
            .add_job(job2)
            .add_job(job3)
            .add_dependency(job1.job_id, job2.job_id)
            .add_dependency(job1.job_id, job3.job_id)
            .add_dependency(job2.job_id, job3.job_id, DependencyType.COMPLETION)
            .build())
    """

    def __init__(self, name: str, dag_id: Optional[str] = None):
        self.name = name
        self.dag_id = dag_id or f"dag-{uuid.uuid4().hex[:12]}"
        self._jobs: List[Job] = []
        self._dependencies: List[tuple[str, str, DependencyType]] = []
        self._metadata: Dict[str, Any] = {}

    def add_job(self, job: Job) -> DAGBuilder:
        """إضافة مهمة."""
        self._jobs.append(job)
        return self

    def add_jobs(self, jobs: List[Job]) -> DAGBuilder:
        """إضافة مهام متعددة."""
        self._jobs.extend(jobs)
        return self

    def add_dependency(
        self,
        parent_id: str,
        child_id: str,
        dependency_type: DependencyType = DependencyType.SUCCESS,
    ) -> DAGBuilder:
        """إضافة تبعية."""
        self._dependencies.append((parent_id, child_id, dependency_type))
        return self

    def chain(self, *job_ids: str) -> DAGBuilder:
        """
        ربط مهام بالتسلسل.

        chain(a, b, c) -> a -> b -> c
        """
        for i in range(len(job_ids) - 1):
            self.add_dependency(job_ids[i], job_ids[i + 1])
        return self

    def fan_out(self, parent_id: str, *child_ids: str) -> DAGBuilder:
        """
        Fan-out: مهمة واحدة تؤدي لمهام متعددة.

        fan_out(a, b, c, d) -> a -> [b, c, d]
        """
        for child_id in child_ids:
            self.add_dependency(parent_id, child_id)
        return self

    def fan_in(self, *parent_ids: str, child_id: str) -> DAGBuilder:
        """
        Fan-in: مهام متعددة تؤدي لمهمة واحدة.

        fan_in(a, b, c, child_id=d) -> [a, b, c] -> d
        """
        for parent_id in parent_ids:
            self.add_dependency(parent_id, child_id)
        return self

    def set_metadata(self, key: str, value: Any) -> DAGBuilder:
        """إضافة metadata."""
        self._metadata[key] = value
        return self

    def build(self) -> DAG:
        """بناء الـ DAG."""
        dag = DAG(
            dag_id=self.dag_id,
            name=self.name,
            metadata=self._metadata,
        )

        # Add jobs
        for job in self._jobs:
            dag.add_job(job)

        # Add dependencies
        for parent_id, child_id, dep_type in self._dependencies:
            dag.add_dependency(parent_id, child_id, dep_type)

        # Validate
        valid, error = dag.is_valid()
        if not valid:
            raise ValueError(f"Invalid DAG: {error}")

        return dag


# =============================================================================
# DAG from YAML
# =============================================================================


def parse_dag_yaml(yaml_content: str, job_factory: Callable[[Dict], Job]) -> DAG:
    """
    تحليل DAG من YAML.

    Format:
        name: my-workflow
        jobs:
          - id: job1
            name: First Job
            command: ["echo", "hello"]
          - id: job2
            name: Second Job
            command: ["echo", "world"]
            depends_on:
              - job1
          - id: job3
            name: Third Job
            command: ["echo", "done"]
            depends_on:
              - job1: completion  # يعمل بعد اكتمال job1 (نجاح أو فشل)
              - job2: success     # يعمل فقط إذا نجح job2
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("YAML support requires PyYAML: pip install pyyaml")

    data = yaml.safe_load(yaml_content)

    dag_name = data.get("name", "unnamed-dag")
    dag_id = data.get("id", f"dag-{uuid.uuid4().hex[:12]}")

    builder = DAGBuilder(dag_name, dag_id)

    # Add metadata
    for key, value in data.get("metadata", {}).items():
        builder.set_metadata(key, value)

    # Create jobs
    job_map: Dict[str, str] = {}  # yaml_id -> job_id

    for job_data in data.get("jobs", []):
        yaml_id = job_data.get("id")
        job = job_factory(job_data)
        builder.add_job(job)
        job_map[yaml_id] = job.job_id

    # Add dependencies
    for job_data in data.get("jobs", []):
        yaml_id = job_data.get("id")
        child_job_id = job_map.get(yaml_id)

        depends_on = job_data.get("depends_on", [])
        for dep in depends_on:
            if isinstance(dep, str):
                # Simple dependency
                parent_yaml_id = dep
                dep_type = DependencyType.SUCCESS
            elif isinstance(dep, dict):
                # Dependency with type
                parent_yaml_id = list(dep.keys())[0]
                dep_type_str = dep[parent_yaml_id]
                dep_type = DependencyType(dep_type_str)
            else:
                continue

            parent_job_id = job_map.get(parent_yaml_id)
            if parent_job_id and child_job_id:
                builder.add_dependency(parent_job_id, child_job_id, dep_type)

    return builder.build()
