"""
AI Task Manager - مدير مهام الذكاء الاصطناعي
=============================================

Manages AI tasks including distributed inference, training, embedding, and fine-tuning.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AITaskType(str, Enum):
    """أنواع مهام AI."""
    INFERENCE = "inference"
    TRAINING = "training"
    EMBEDDING = "embedding"
    FINE_TUNE = "fine-tune"


class AITaskStatus(str, Enum):
    """حالة مهمة AI."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AITaskResult:
    """نتيجة مهمة AI."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)


@dataclass
class AITask:
    """مهمة AI موزعة."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: AITaskType = AITaskType.INFERENCE
    status: AITaskStatus = AITaskStatus.PENDING

    # Configuration
    model: str = ""
    input_data: Any = None
    config: Dict[str, Any] = field(default_factory=dict)

    # Distributed settings
    distributed: bool = False
    num_workers: int = 1
    worker_ids: List[str] = field(default_factory=list)

    # Progress tracking
    progress: float = 0.0
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Results
    result: Optional[AITaskResult] = None
    error: Optional[str] = None

    # Callbacks
    _progress_callback: Optional[Callable[[float, str], None]] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى قاموس."""
        return {
            "task_id": self.task_id,
            "type": self.type.value,
            "status": self.status.value,
            "model": self.model,
            "distributed": self.distributed,
            "num_workers": self.num_workers,
            "progress": self.progress,
            "current_step": self.current_step,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }

    def update_progress(self, progress: float, step: str = "") -> None:
        """تحديث التقدم."""
        self.progress = min(100.0, max(0.0, progress))
        if step:
            self.current_step = step
        if self._progress_callback:
            self._progress_callback(self.progress, self.current_step)


class AITaskManager:
    """
    مدير مهام AI الموزعة.

    Manages distributed AI tasks including:
    - Distributed inference across multiple workers
    - Distributed training (data parallel, model parallel)
    - Batch embedding generation
    - Model fine-tuning
    """

    def __init__(
        self,
        master_client=None,
        max_concurrent: int = 10,
    ):
        self.master_client = master_client
        self.max_concurrent = max_concurrent

        self._tasks: Dict[str, AITask] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()

        # Task handlers
        self._handlers: Dict[AITaskType, Callable] = {}

    def register_handler(
        self,
        task_type: AITaskType,
        handler: Callable[[AITask], Any],
    ) -> None:
        """تسجيل معالج لنوع مهمة."""
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for {task_type.value}")

    async def submit_task(
        self,
        task_type: AITaskType,
        model: str,
        input_data: Any = None,
        config: Optional[Dict[str, Any]] = None,
        distributed: bool = False,
        num_workers: int = 1,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> AITask:
        """
        إرسال مهمة AI جديدة.

        Args:
            task_type: نوع المهمة
            model: اسم النموذج
            input_data: بيانات الإدخال
            config: إعدادات إضافية
            distributed: تشغيل موزع
            num_workers: عدد العمال
            progress_callback: دالة تحديث التقدم

        Returns:
            AITask: المهمة المنشأة
        """
        task = AITask(
            type=task_type,
            model=model,
            input_data=input_data,
            config=config or {},
            distributed=distributed,
            num_workers=num_workers,
            _progress_callback=progress_callback,
        )

        async with self._lock:
            self._tasks[task.task_id] = task

        # Start task execution
        asyncio_task = asyncio.create_task(self._execute_task(task))
        self._running_tasks[task.task_id] = asyncio_task

        logger.info(f"Submitted AI task {task.task_id} ({task_type.value})")
        return task

    async def get_task(self, task_id: str) -> Optional[AITask]:
        """الحصول على مهمة."""
        return self._tasks.get(task_id)

    async def list_tasks(
        self,
        task_type: Optional[AITaskType] = None,
        status: Optional[AITaskStatus] = None,
        limit: int = 100,
    ) -> List[AITask]:
        """قائمة المهام."""
        tasks = list(self._tasks.values())

        if task_type:
            tasks = [t for t in tasks if t.type == task_type]
        if status:
            tasks = [t for t in tasks if t.status == status]

        # Sort by creation time (newest first)
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return tasks[:limit]

    async def cancel_task(self, task_id: str) -> bool:
        """إلغاء مهمة."""
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task.status not in (AITaskStatus.PENDING, AITaskStatus.RUNNING):
            return False

        # Cancel asyncio task
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]

        task.status = AITaskStatus.CANCELLED
        task.completed_at = datetime.utcnow()

        logger.info(f"Cancelled AI task {task_id}")
        return True

    async def _execute_task(self, task: AITask) -> None:
        """تنفيذ مهمة."""
        async with self._semaphore:
            try:
                task.status = AITaskStatus.RUNNING
                task.started_at = datetime.utcnow()
                task.update_progress(0, "Starting task")

                # Get handler
                handler = self._handlers.get(task.type)
                if not handler:
                    raise ValueError(f"No handler for task type: {task.type}")

                # Execute
                if task.distributed and task.num_workers > 1:
                    result = await self._execute_distributed(task, handler)
                else:
                    result = await handler(task)

                task.result = result
                task.status = AITaskStatus.COMPLETED
                task.progress = 100.0
                task.update_progress(100, "Completed")

            except asyncio.CancelledError:
                task.status = AITaskStatus.CANCELLED
                logger.info(f"Task {task.task_id} cancelled")

            except Exception as e:
                task.status = AITaskStatus.FAILED
                task.error = str(e)
                task.result = AITaskResult(success=False, error=str(e))
                logger.error(f"Task {task.task_id} failed: {e}")

            finally:
                task.completed_at = datetime.utcnow()
                if task.task_id in self._running_tasks:
                    del self._running_tasks[task.task_id]

    async def _execute_distributed(
        self,
        task: AITask,
        handler: Callable,
    ) -> AITaskResult:
        """
        تنفيذ مهمة موزعة.

        Distributes work across multiple workers.
        """
        task.update_progress(5, "Allocating workers")

        # Request workers from master
        if self.master_client:
            workers = await self._allocate_workers(task)
            task.worker_ids = [w["worker_id"] for w in workers]
        else:
            # Simulate distributed execution locally
            task.worker_ids = [f"local-worker-{i}" for i in range(task.num_workers)]

        task.update_progress(10, f"Allocated {len(task.worker_ids)} workers")

        # Partition work
        partitions = self._partition_input(task.input_data, task.num_workers)

        # Execute on each worker
        results = []
        for i, (worker_id, partition) in enumerate(zip(task.worker_ids, partitions)):
            progress = 10 + (80 * (i + 1) / len(partitions))
            task.update_progress(progress, f"Processing partition {i+1}/{len(partitions)}")

            # Create sub-task for worker
            sub_task = AITask(
                type=task.type,
                model=task.model,
                input_data=partition,
                config=task.config,
            )

            result = await handler(sub_task)
            results.append(result)

        # Aggregate results
        task.update_progress(95, "Aggregating results")
        aggregated = self._aggregate_results(results, task.type)

        return aggregated

    async def _allocate_workers(self, task: AITask) -> List[Dict]:
        """تخصيص عمال للمهمة."""
        # Request workers with GPU if available
        resources = task.config.get("resources", {})

        if self.master_client:
            workers = await self.master_client.get_available_workers(
                count=task.num_workers,
                gpu_required=resources.get("gpu", False),
            )
            return workers

        return []

    def _partition_input(self, input_data: Any, num_partitions: int) -> List[Any]:
        """تقسيم البيانات."""
        if isinstance(input_data, list):
            # Partition list evenly
            chunk_size = max(1, len(input_data) // num_partitions)
            partitions = []
            for i in range(num_partitions):
                start = i * chunk_size
                end = start + chunk_size if i < num_partitions - 1 else len(input_data)
                partitions.append(input_data[start:end])
            return partitions

        elif isinstance(input_data, str):
            # For text, just duplicate for each worker (model parallelism)
            return [input_data] * num_partitions

        else:
            # Single input to all workers
            return [input_data] * num_partitions

    def _aggregate_results(
        self,
        results: List[AITaskResult],
        task_type: AITaskType,
    ) -> AITaskResult:
        """تجميع النتائج."""
        if not results:
            return AITaskResult(success=False, error="No results")

        # Check if all succeeded
        all_success = all(r.success for r in results)

        if task_type == AITaskType.INFERENCE:
            # Concatenate outputs
            outputs = [r.output for r in results if r.output]
            return AITaskResult(
                success=all_success,
                output=outputs if len(outputs) > 1 else (outputs[0] if outputs else None),
            )

        elif task_type == AITaskType.EMBEDDING:
            # Stack embeddings
            embeddings = []
            for r in results:
                if r.output:
                    if isinstance(r.output, list):
                        embeddings.extend(r.output)
                    else:
                        embeddings.append(r.output)
            return AITaskResult(success=all_success, output=embeddings)

        elif task_type == AITaskType.TRAINING:
            # Aggregate metrics
            metrics = {}
            for r in results:
                for key, value in r.metrics.items():
                    if key not in metrics:
                        metrics[key] = []
                    metrics[key].append(value)

            # Average metrics
            avg_metrics = {k: sum(v) / len(v) for k, v in metrics.items()}
            return AITaskResult(success=all_success, metrics=avg_metrics)

        else:
            # Default: return last result
            return results[-1]

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات المدير."""
        tasks = list(self._tasks.values())

        return {
            "total_tasks": len(tasks),
            "pending": len([t for t in tasks if t.status == AITaskStatus.PENDING]),
            "running": len([t for t in tasks if t.status == AITaskStatus.RUNNING]),
            "completed": len([t for t in tasks if t.status == AITaskStatus.COMPLETED]),
            "failed": len([t for t in tasks if t.status == AITaskStatus.FAILED]),
            "by_type": {
                t.value: len([task for task in tasks if task.type == t])
                for t in AITaskType
            },
        }
