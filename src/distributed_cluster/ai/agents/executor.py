"""
Agent Executor - منفذ الوكلاء الموزع
=====================================

Executes agents across distributed workers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from distributed_cluster.ai.agents.base import (
    Agent,
    AgentTask,
    AgentResult,
    AgentStatus,
)
from distributed_cluster.ai.llm.provider import LLMProvider, create_provider

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    """أوضاع التنفيذ."""
    LOCAL = "local"  # تنفيذ محلي
    DISTRIBUTED = "distributed"  # تنفيذ موزع
    HYBRID = "hybrid"  # مختلط


@dataclass
class ExecutionConfig:
    """إعدادات التنفيذ."""
    mode: ExecutionMode = ExecutionMode.LOCAL
    master_url: Optional[str] = None
    worker_id: Optional[str] = None
    max_concurrent: int = 5
    retry_on_failure: bool = True
    max_retries: int = 3
    timeout_seconds: float = 600


@dataclass
class AgentJob:
    """مهمة وكيل للتنفيذ."""
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    task: AgentTask = field(default_factory=AgentTask)
    status: AgentStatus = AgentStatus.IDLE
    result: Optional[AgentResult] = None
    worker_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retries: int = 0


class AgentExecutor:
    """
    منفذ الوكلاء - يدير تنفيذ الوكلاء محلياً أو موزعاً.

    Features:
    - Local execution for single machine
    - Distributed execution across cluster
    - Job queuing and scheduling
    - Result aggregation
    """

    def __init__(
        self,
        config: Optional[ExecutionConfig] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        self.config = config or ExecutionConfig()
        self.llm_provider = llm_provider

        # Job management
        self._jobs: Dict[str, AgentJob] = {}
        self._job_queue: asyncio.Queue[AgentJob] = asyncio.Queue()
        self._results: Dict[str, AgentResult] = {}

        # Agents registry
        self._agents: Dict[str, Agent] = {}

        # Workers (for distributed mode)
        self._workers: Dict[str, Dict[str, Any]] = {}

        # State
        self._running = False
        self._executor_task: Optional[asyncio.Task] = None

        # Callbacks
        self._on_job_complete: Optional[Callable[[AgentJob], None]] = None
        self._on_job_failed: Optional[Callable[[AgentJob, str], None]] = None

    def register_agent(self, agent: Agent) -> None:
        """تسجيل وكيل."""
        self._agents[agent.name] = agent
        logger.info(f"Registered agent: {agent.name}")

    def unregister_agent(self, agent_name: str) -> None:
        """إلغاء تسجيل وكيل."""
        if agent_name in self._agents:
            del self._agents[agent_name]

    async def submit(
        self,
        agent_name: str,
        task: AgentTask,
        priority: int = 50,
    ) -> str:
        """تقديم مهمة للتنفيذ."""
        if agent_name not in self._agents:
            raise ValueError(f"Unknown agent: {agent_name}")

        job = AgentJob(
            agent_name=agent_name,
            task=task,
        )

        self._jobs[job.job_id] = job
        await self._job_queue.put(job)

        logger.info(f"Submitted job {job.job_id} for agent {agent_name}")

        return job.job_id

    async def execute(
        self,
        agent_name: str,
        task_description: str,
        **task_kwargs,
    ) -> AgentResult:
        """تنفيذ مهمة مباشرة."""
        task = AgentTask(
            description=task_description,
            **task_kwargs,
        )

        job_id = await self.submit(agent_name, task)

        # Wait for completion
        return await self.wait_for_result(job_id)

    async def wait_for_result(
        self,
        job_id: str,
        timeout: Optional[float] = None,
    ) -> AgentResult:
        """انتظار نتيجة مهمة."""
        timeout = timeout or self.config.timeout_seconds

        start_time = asyncio.get_event_loop().time()

        while True:
            if job_id in self._results:
                return self._results[job_id]

            job = self._jobs.get(job_id)
            if job and job.status in [AgentStatus.COMPLETED, AgentStatus.FAILED]:
                if job.result:
                    return job.result

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Job {job_id} timed out")

            await asyncio.sleep(0.1)

    def get_job_status(self, job_id: str) -> Optional[AgentJob]:
        """الحصول على حالة مهمة."""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        status: Optional[AgentStatus] = None,
    ) -> List[AgentJob]:
        """قائمة المهام."""
        jobs = list(self._jobs.values())

        if status:
            jobs = [j for j in jobs if j.status == status]

        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    async def start(self) -> None:
        """بدء المنفذ."""
        if self._running:
            return

        self._running = True
        self._executor_task = asyncio.create_task(self._run_executor())

        logger.info("Agent executor started")

    async def stop(self) -> None:
        """إيقاف المنفذ."""
        self._running = False

        if self._executor_task:
            self._executor_task.cancel()
            try:
                await self._executor_task
            except asyncio.CancelledError:
                pass

        logger.info("Agent executor stopped")

    async def _run_executor(self) -> None:
        """حلقة التنفيذ الرئيسية."""
        workers = []

        for _ in range(self.config.max_concurrent):
            worker = asyncio.create_task(self._worker_loop())
            workers.append(worker)

        try:
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            for worker in workers:
                worker.cancel()

    async def _worker_loop(self) -> None:
        """حلقة العامل."""
        while self._running:
            try:
                job = await asyncio.wait_for(
                    self._job_queue.get(),
                    timeout=1.0,
                )

                await self._execute_job(job)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")

    async def _execute_job(self, job: AgentJob) -> None:
        """تنفيذ مهمة."""
        job.status = AgentStatus.EXECUTING
        job.started_at = datetime.utcnow()

        logger.info(f"Executing job {job.job_id}")

        try:
            agent = self._agents.get(job.agent_name)
            if not agent:
                raise ValueError(f"Agent not found: {job.agent_name}")

            if self.config.mode == ExecutionMode.LOCAL:
                result = await agent.execute_task(job.task)

            elif self.config.mode == ExecutionMode.DISTRIBUTED:
                result = await self._execute_distributed(job)

            else:  # HYBRID
                # Try local first, fallback to distributed
                try:
                    result = await agent.execute_task(job.task)
                except Exception:
                    result = await self._execute_distributed(job)

            job.result = result
            job.status = result.status
            job.completed_at = datetime.utcnow()

            self._results[job.job_id] = result

            if self._on_job_complete:
                self._on_job_complete(job)

            logger.info(f"Job {job.job_id} completed: {result.status}")

        except Exception as e:
            logger.error(f"Job {job.job_id} failed: {e}")

            job.status = AgentStatus.FAILED
            job.completed_at = datetime.utcnow()

            # Retry if configured
            if self.config.retry_on_failure and job.retries < self.config.max_retries:
                job.retries += 1
                job.status = AgentStatus.IDLE
                await self._job_queue.put(job)
                logger.info(f"Retrying job {job.job_id} (attempt {job.retries})")
            else:
                error_result = AgentResult(
                    task_id=job.task.task_id,
                    status=AgentStatus.FAILED,
                    error=str(e),
                )
                job.result = error_result
                self._results[job.job_id] = error_result

                if self._on_job_failed:
                    self._on_job_failed(job, str(e))

    async def _execute_distributed(self, job: AgentJob) -> AgentResult:
        """تنفيذ موزع على الكلاستر."""
        if not self.config.master_url:
            raise ValueError("Master URL required for distributed execution")

        import httpx

        async with httpx.AsyncClient() as client:
            # Submit job to master
            payload = {
                "job_id": job.job_id,
                "name": f"agent-{job.agent_name}",
                "command": json.dumps({
                    "type": "agent_task",
                    "agent": job.agent_name,
                    "task": {
                        "task_id": job.task.task_id,
                        "description": job.task.description,
                        "context": job.task.context,
                        "priority": job.task.priority,
                        "timeout_seconds": job.task.timeout_seconds,
                        "max_iterations": job.task.max_iterations,
                    },
                }),
                "priority": job.task.priority,
            }

            response = await client.post(
                f"{self.config.master_url}/jobs/submit",
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()

            cluster_job_id = response.json().get("job_id")

            # Poll for result
            while True:
                response = await client.get(
                    f"{self.config.master_url}/jobs/{cluster_job_id}",
                    timeout=10.0,
                )
                response.raise_for_status()

                data = response.json()
                status = data.get("status")

                if status in ["completed", "failed"]:
                    result_data = data.get("result", {})

                    return AgentResult(
                        task_id=job.task.task_id,
                        status=AgentStatus.COMPLETED if status == "completed" else AgentStatus.FAILED,
                        result=result_data.get("output"),
                        error=result_data.get("error"),
                        total_tokens=result_data.get("total_tokens", 0),
                        total_time_ms=result_data.get("total_time_ms", 0),
                    )

                await asyncio.sleep(1.0)


class MultiAgentOrchestrator:
    """
    منسق متعدد الوكلاء.

    Orchestrates multiple agents working together on complex tasks.
    """

    def __init__(
        self,
        executor: AgentExecutor,
    ):
        self.executor = executor
        self._workflows: Dict[str, List[Dict[str, Any]]] = {}

    def define_workflow(
        self,
        name: str,
        steps: List[Dict[str, Any]],
    ) -> None:
        """تعريف سير عمل."""
        self._workflows[name] = steps

    async def run_workflow(
        self,
        name: str,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """تشغيل سير عمل."""
        if name not in self._workflows:
            raise ValueError(f"Unknown workflow: {name}")

        steps = self._workflows[name]
        context = initial_context or {}
        results = {}

        for i, step in enumerate(steps):
            agent_name = step["agent"]
            task_template = step["task"]
            output_key = step.get("output", f"step_{i}")

            # Format task with context
            task_description = task_template.format(**context)

            # Execute
            result = await self.executor.execute(
                agent_name=agent_name,
                task_description=task_description,
                context=context,
            )

            # Store result
            results[output_key] = result.result
            context[output_key] = result.result

            # Check for failure
            if not result.is_success:
                logger.error(f"Workflow step {i} failed: {result.error}")
                if not step.get("continue_on_failure", False):
                    break

        return {
            "results": results,
            "context": context,
        }

    async def run_parallel(
        self,
        tasks: List[Dict[str, Any]],
    ) -> List[AgentResult]:
        """تشغيل مهام بالتوازي."""
        jobs = []

        for task_def in tasks:
            agent_name = task_def["agent"]
            task_description = task_def["task"]

            task = AgentTask(
                description=task_description,
                context=task_def.get("context", {}),
            )

            job_id = await self.executor.submit(agent_name, task)
            jobs.append(job_id)

        # Wait for all
        results = []
        for job_id in jobs:
            result = await self.executor.wait_for_result(job_id)
            results.append(result)

        return results


def create_default_executor(
    llm_provider_type: str = "ollama",
    llm_base_url: str = "http://localhost:11434",
    model: str = "llama3.2",
    **kwargs,
) -> AgentExecutor:
    """إنشاء منفذ افتراضي مع وكلاء جاهزين."""
    from distributed_cluster.ai.agents.base import Agent, CodeAgent, ResearchAgent
    from distributed_cluster.ai.agents.tools import get_default_tools

    # Create LLM provider
    provider = create_provider(llm_provider_type, base_url=llm_base_url)

    # Create executor
    executor = AgentExecutor(llm_provider=provider)

    # Create and register default agents
    tools = get_default_tools()

    general_agent = Agent(
        name="assistant",
        llm_provider=provider,
        model=model,
        tools=tools,
        system_prompt="You are a helpful AI assistant.",
    )

    code_agent = Agent(
        name="coder",
        llm_provider=provider,
        model=model,
        tools=tools,
        system_prompt="You are an expert software developer.",
    )

    research_agent = Agent(
        name="researcher",
        llm_provider=provider,
        model=model,
        tools=tools,
        system_prompt="You are a research assistant.",
    )

    executor.register_agent(general_agent)
    executor.register_agent(code_agent)
    executor.register_agent(research_agent)

    return executor
