"""
AI Tasks Module - مهام الذكاء الاصطناعي
========================================

Built-in AI tasks for distributed inference, training, and more.
Includes task splitting for distributed prompt execution.
"""

# Core task management
from .manager import AITaskManager, AITask, AITaskStatus, AITaskType

# Distributed execution tasks
from .inference import DistributedInferenceTask
from .training import DistributedTrainingTask
from .embedding import EmbeddingTask

# Builtin task definitions
from .builtin_tasks import (
    AITask as AITaskDefinition,
    AITaskCategory,
    AITaskRegistry,
    BuiltinTasks,
    TaskParameter,
    TaskResult,
    get_builtin_tasks,
)

# Task splitting for distributed execution
from .task_splitter import (
    ChunkingStrategy,
    DistributedPromptExecutor,
    TaskChunk,
    TaskSplitter,
)

__all__ = [
    # Core
    "AITaskManager",
    "AITask",
    "AITaskStatus",
    "AITaskType",
    # Distributed Tasks
    "DistributedInferenceTask",
    "DistributedTrainingTask",
    "EmbeddingTask",
    # Builtin Tasks
    "AITaskDefinition",
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
