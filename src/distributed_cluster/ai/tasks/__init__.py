"""
AI Tasks - مهام الذكاء الاصطناعي
================================

Built-in AI tasks and distributed prompt execution.
"""

from distributed_cluster.ai.tasks.builtin_tasks import (
    AITask,
    AITaskCategory,
    AITaskRegistry,
    BuiltinTasks,
    TaskParameter,
    TaskResult,
    get_builtin_tasks,
)
from distributed_cluster.ai.tasks.task_splitter import (
    ChunkingStrategy,
    DistributedPromptExecutor,
    TaskChunk,
    TaskSplitter,
)

__all__ = [
    # Builtin Tasks
    "AITask",
    "AITaskCategory",
    "AITaskRegistry",
    "BuiltinTasks",
    "TaskParameter",
    "TaskResult",
    "get_builtin_tasks",
    # Task Splitting
    "TaskSplitter",
    "TaskChunk",
    "ChunkingStrategy",
    "DistributedPromptExecutor",
]
