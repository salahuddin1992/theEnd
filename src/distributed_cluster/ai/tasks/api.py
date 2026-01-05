"""
AI Tasks API - واجهة برمجة مهام AI
===================================

REST API endpoints for:
- Listing and executing built-in AI tasks
- Submitting distributed prompts
- Monitoring task progress
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from distributed_cluster.ai.tasks.builtin_tasks import (
    AITask,
    AITaskCategory,
    AITaskRegistry,
    TaskResult,
    get_builtin_tasks,
)
from distributed_cluster.ai.tasks.task_splitter import (
    AggregationStrategy,
    ChunkingStrategy,
    DistributedPromptExecutor,
    SplitTask,
    WorkerInfo,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/tasks", tags=["AI Tasks"])


# ============== Models ==============


class TaskParameterInput(BaseModel):
    """معامل مهمة."""

    name: str
    value: Any


class ExecuteTaskRequest(BaseModel):
    """طلب تنفيذ مهمة."""

    task_id: str
    parameters: Dict[str, Any]
    model: Optional[str] = None
    distributed: bool = False
    chunking_strategy: Optional[str] = None
    aggregation_strategy: Optional[str] = None


class ExecutePromptRequest(BaseModel):
    """طلب تنفيذ prompt."""

    prompt: str
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    distributed: bool = False


class BatchPromptRequest(BaseModel):
    """طلب تنفيذ دفعة prompts."""

    prompts: List[Dict[str, Any]]
    model: Optional[str] = None
    parallel: bool = True
    max_concurrent: int = 5


class TaskResponse(BaseModel):
    """استجابة مهمة."""

    task_id: str
    name: str
    name_ar: str
    description: str
    description_ar: str
    category: str
    icon: str
    tags: List[str]
    parameters: List[Dict[str, Any]]
    supports_distributed: bool


class ExecutionResponse(BaseModel):
    """استجابة تنفيذ."""

    execution_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    progress: float = 0
    execution_time_ms: float = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskProgressUpdate(BaseModel):
    """تحديث تقدم المهمة."""

    execution_id: str
    progress: float
    status: str
    message: str
    chunks_completed: int = 0
    chunks_total: int = 0


# ============== State ==============


class TaskExecutionState:
    """حالة تنفيذ المهام."""

    def __init__(self):
        self.executions: Dict[str, Dict[str, Any]] = {}
        self.executor = DistributedPromptExecutor()
        self._websocket_clients: Dict[str, List[WebSocket]] = {}

    def create_execution(self, task_id: str) -> str:
        """إنشاء تنفيذ جديد."""
        execution_id = str(uuid.uuid4())
        self.executions[execution_id] = {
            "execution_id": execution_id,
            "task_id": task_id,
            "status": "pending",
            "progress": 0,
            "result": None,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "metadata": {},
        }
        return execution_id

    def update_execution(self, execution_id: str, **kwargs) -> None:
        """تحديث تنفيذ."""
        if execution_id in self.executions:
            self.executions[execution_id].update(kwargs)

    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """الحصول على تنفيذ."""
        return self.executions.get(execution_id)

    async def notify_progress(self, execution_id: str, update: TaskProgressUpdate) -> None:
        """إرسال تحديث التقدم عبر WebSocket."""
        if execution_id in self._websocket_clients:
            message = update.model_dump_json()
            for ws in self._websocket_clients[execution_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    pass


# Global state
_state: Optional[TaskExecutionState] = None


def get_state() -> TaskExecutionState:
    """الحصول على حالة التنفيذ."""
    global _state
    if _state is None:
        _state = TaskExecutionState()
    return _state


# ============== Endpoints ==============


@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search query"),
) -> List[TaskResponse]:
    """
    قائمة مهام AI الجاهزة.

    List all available built-in AI tasks.
    """
    registry = get_builtin_tasks()

    if category:
        try:
            cat = AITaskCategory(category)
            tasks = registry.list_by_category(cat)
        except ValueError:
            tasks = registry.list_all()
    elif search:
        tasks = registry.search(search)
    else:
        tasks = registry.list_all()

    return [
        TaskResponse(
            task_id=t.task_id,
            name=t.name,
            name_ar=t.name_ar,
            description=t.description,
            description_ar=t.description_ar,
            category=t.category.value,
            icon=t.icon,
            tags=t.tags,
            parameters=[
                {
                    "name": p.name,
                    "label": p.label,
                    "type": p.param_type.value,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "options": p.options,
                    "placeholder": p.placeholder,
                }
                for p in t.parameters
            ],
            supports_distributed=t.supports_distributed,
        )
        for t in tasks
    ]


@router.get("/categories")
async def list_categories() -> List[Dict[str, Any]]:
    """
    قائمة فئات المهام.

    List all task categories with counts.
    """
    registry = get_builtin_tasks()
    return registry.get_categories()


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    """
    الحصول على تفاصيل مهمة.

    Get details of a specific AI task.
    """
    registry = get_builtin_tasks()
    task = registry.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    return TaskResponse(
        task_id=task.task_id,
        name=task.name,
        name_ar=task.name_ar,
        description=task.description,
        description_ar=task.description_ar,
        category=task.category.value,
        icon=task.icon,
        tags=task.tags,
        parameters=[
            {
                "name": p.name,
                "label": p.label,
                "type": p.param_type.value,
                "description": p.description,
                "required": p.required,
                "default": p.default,
                "options": p.options,
                "placeholder": p.placeholder,
            }
            for p in task.parameters
        ],
        supports_distributed=task.supports_distributed,
    )


@router.post("/execute", response_model=ExecutionResponse)
async def execute_task(
    request: ExecuteTaskRequest,
    background_tasks: BackgroundTasks,
) -> ExecutionResponse:
    """
    تنفيذ مهمة AI.

    Execute a built-in AI task with the given parameters.
    """
    registry = get_builtin_tasks()
    task = registry.get(request.task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{request.task_id}' not found")

    # Validate parameters
    valid, errors = task.validate_parameters(request.parameters)
    if not valid:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Create execution
    state = get_state()
    execution_id = state.create_execution(request.task_id)

    if request.distributed and task.supports_distributed:
        # Execute distributed in background
        background_tasks.add_task(
            _execute_distributed_task,
            execution_id,
            task,
            request.parameters,
            request.chunking_strategy,
            request.aggregation_strategy,
        )

        return ExecutionResponse(
            execution_id=execution_id,
            status="running",
            progress=0,
            metadata={"distributed": True},
        )
    else:
        # Execute synchronously
        background_tasks.add_task(
            _execute_task,
            execution_id,
            task,
            request.parameters,
        )

        return ExecutionResponse(
            execution_id=execution_id,
            status="running",
            progress=0,
        )


async def _execute_task(
    execution_id: str,
    task: AITask,
    parameters: Dict[str, Any],
) -> None:
    """تنفيذ مهمة في الخلفية."""
    import time

    state = get_state()
    state.update_execution(
        execution_id,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    start_time = time.time()

    try:
        # Build prompt
        prompt = task.build_prompt(**parameters)

        # Here we would call the LLM provider
        # For now, simulate with a placeholder
        await asyncio.sleep(1)  # Simulate processing

        result = f"[Task: {task.name}]\n\nPrompt generated successfully.\nLength: {len(prompt)} characters"

        execution_time = (time.time() - start_time) * 1000

        state.update_execution(
            execution_id,
            status="completed",
            result=result,
            progress=100,
            completed_at=datetime.now(timezone.utc).isoformat(),
            metadata={"execution_time_ms": execution_time},
        )

    except Exception as e:
        logger.error(f"Task execution failed: {e}")
        state.update_execution(
            execution_id,
            status="failed",
            error=str(e),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )


async def _execute_distributed_task(
    execution_id: str,
    task: AITask,
    parameters: Dict[str, Any],
    chunking_strategy: Optional[str],
    aggregation_strategy: Optional[str],
) -> None:
    """تنفيذ مهمة موزعة في الخلفية."""
    state = get_state()
    state.update_execution(
        execution_id,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    try:
        async def on_progress(progress: float, message: str):
            state.update_execution(execution_id, progress=progress)
            await state.notify_progress(
                execution_id,
                TaskProgressUpdate(
                    execution_id=execution_id,
                    progress=progress,
                    status="running",
                    message=message,
                ),
            )

        # Determine text parameter
        text_param = "text"
        for param in task.parameters:
            if param.param_type.value in ["text", "string"] and param.required:
                text_param = param.name
                break

        result = await state.executor.execute_distributed(
            task,
            parameters,
            text_param=text_param,
            on_progress=on_progress,
        )

        state.update_execution(
            execution_id,
            status="completed" if result.success else "failed",
            result=result.output,
            error=result.error,
            progress=100,
            completed_at=datetime.now(timezone.utc).isoformat(),
            metadata=result.metadata,
        )

    except Exception as e:
        logger.error(f"Distributed task execution failed: {e}")
        state.update_execution(
            execution_id,
            status="failed",
            error=str(e),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )


@router.get("/execution/{execution_id}", response_model=ExecutionResponse)
async def get_execution_status(execution_id: str) -> ExecutionResponse:
    """
    حالة تنفيذ مهمة.

    Get the status of a task execution.
    """
    state = get_state()
    execution = state.get_execution(execution_id)

    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    return ExecutionResponse(
        execution_id=execution["execution_id"],
        status=execution["status"],
        result=execution.get("result"),
        error=execution.get("error"),
        progress=execution.get("progress", 0),
        execution_time_ms=execution.get("metadata", {}).get("execution_time_ms", 0),
        metadata=execution.get("metadata", {}),
    )


@router.post("/prompt", response_model=ExecutionResponse)
async def execute_prompt(
    request: ExecutePromptRequest,
    background_tasks: BackgroundTasks,
) -> ExecutionResponse:
    """
    تنفيذ prompt مباشر.

    Execute a raw prompt directly.
    """
    state = get_state()
    execution_id = state.create_execution("raw_prompt")

    background_tasks.add_task(
        _execute_raw_prompt,
        execution_id,
        request.prompt,
        request.model,
        request.system_prompt,
        request.temperature,
        request.max_tokens,
        request.distributed,
    )

    return ExecutionResponse(
        execution_id=execution_id,
        status="running",
        progress=0,
        metadata={"distributed": request.distributed},
    )


async def _execute_raw_prompt(
    execution_id: str,
    prompt: str,
    model: Optional[str],
    system_prompt: Optional[str],
    temperature: float,
    max_tokens: int,
    distributed: bool,
) -> None:
    """تنفيذ prompt مباشر."""
    import time

    state = get_state()
    state.update_execution(
        execution_id,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    start_time = time.time()

    try:
        # Here we would call the LLM provider
        await asyncio.sleep(1)  # Simulate processing

        result = f"[Raw Prompt Execution]\n\nPrompt: {prompt[:100]}...\nModel: {model or 'default'}"

        execution_time = (time.time() - start_time) * 1000

        state.update_execution(
            execution_id,
            status="completed",
            result=result,
            progress=100,
            completed_at=datetime.now(timezone.utc).isoformat(),
            metadata={"execution_time_ms": execution_time},
        )

    except Exception as e:
        state.update_execution(
            execution_id,
            status="failed",
            error=str(e),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )


@router.post("/batch", response_model=ExecutionResponse)
async def execute_batch(
    request: BatchPromptRequest,
    background_tasks: BackgroundTasks,
) -> ExecutionResponse:
    """
    تنفيذ دفعة prompts.

    Execute a batch of prompts in parallel.
    """
    state = get_state()
    execution_id = state.create_execution("batch")

    background_tasks.add_task(
        _execute_batch,
        execution_id,
        request.prompts,
        request.model,
        request.parallel,
        request.max_concurrent,
    )

    return ExecutionResponse(
        execution_id=execution_id,
        status="running",
        progress=0,
        metadata={
            "batch_size": len(request.prompts),
            "parallel": request.parallel,
        },
    )


async def _execute_batch(
    execution_id: str,
    prompts: List[Dict[str, Any]],
    model: Optional[str],
    parallel: bool,
    max_concurrent: int,
) -> None:
    """تنفيذ دفعة prompts."""
    import time

    state = get_state()
    state.update_execution(
        execution_id,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    start_time = time.time()
    total = len(prompts)
    completed = 0
    results = []

    try:

        async def on_progress(done: int, total: int):
            nonlocal completed
            completed = done
            progress = (done / total) * 100
            state.update_execution(execution_id, progress=progress)

        batch_results = await state.executor.execute_batch(
            prompts,
            on_progress=on_progress,
        )

        results = [
            {
                "success": r.success,
                "output": r.output,
                "error": r.error,
            }
            for r in batch_results
        ]

        execution_time = (time.time() - start_time) * 1000

        state.update_execution(
            execution_id,
            status="completed",
            result=results,
            progress=100,
            completed_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "execution_time_ms": execution_time,
                "total_prompts": total,
                "successful": sum(1 for r in batch_results if r.success),
            },
        )

    except Exception as e:
        state.update_execution(
            execution_id,
            status="failed",
            error=str(e),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )


@router.websocket("/ws/{execution_id}")
async def websocket_progress(websocket: WebSocket, execution_id: str):
    """
    WebSocket للتقدم المباشر.

    Real-time progress updates for task execution.
    """
    state = get_state()

    await websocket.accept()

    # Register client
    if execution_id not in state._websocket_clients:
        state._websocket_clients[execution_id] = []
    state._websocket_clients[execution_id].append(websocket)

    try:
        # Send initial status
        execution = state.get_execution(execution_id)
        if execution:
            await websocket.send_json(execution)

        # Keep connection alive
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break

    finally:
        # Unregister client
        if execution_id in state._websocket_clients:
            state._websocket_clients[execution_id].remove(websocket)
            if not state._websocket_clients[execution_id]:
                del state._websocket_clients[execution_id]


@router.get("/workers/stats")
async def get_workers_stats() -> Dict[str, Any]:
    """
    إحصائيات Workers.

    Get statistics about distributed execution workers.
    """
    state = get_state()
    return state.executor.get_stats()


@router.post("/workers/register")
async def register_worker(worker: Dict[str, Any]) -> Dict[str, str]:
    """
    تسجيل Worker جديد.

    Register a new worker for distributed execution.
    """
    state = get_state()

    worker_info = WorkerInfo(
        worker_id=worker.get("worker_id", str(uuid.uuid4())),
        capacity=worker.get("capacity", 1),
        specializations=worker.get("specializations", []),
    )

    state.executor.register_worker(worker_info)

    return {"status": "registered", "worker_id": worker_info.worker_id}
