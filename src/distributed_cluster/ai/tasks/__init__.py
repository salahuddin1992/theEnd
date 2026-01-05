"""
AI Tasks Module - مهام الذكاء الاصطناعي
========================================

Built-in AI tasks for distributed inference, training, and more.
Includes task splitting for distributed prompt execution.
"""

# Core task management
# Builtin task definitions
from .builtin_tasks import (
    AITask as AITaskDefinition,
)
from .builtin_tasks import (
    AITaskCategory,
    AITaskRegistry,
    BuiltinTasks,
    ParameterType,
    TaskParameter,
    TaskResult,
    get_builtin_tasks,
)
from .embedding import EmbeddingTask

# Distributed execution tasks
from .inference import DistributedInferenceTask
from .manager import AITask, AITaskManager, AITaskStatus, AITaskType

# Task splitting for distributed execution
from .task_splitter import (
    AggregationStrategy,
    ChunkingStrategy,
    DistributedPromptExecutor,
    ResultAggregator,
    SplitTask,
    TaskChunk,
    TaskSplitter,
    TextChunker,
    WorkerInfo,
)
from .training import DistributedTrainingTask

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
    "ParameterType",
    "TaskParameter",
    "TaskResult",
    "get_builtin_tasks",
    # Task Splitting
    "TaskSplitter",
    "TaskChunk",
    "ChunkingStrategy",
    "AggregationStrategy",
    "DistributedPromptExecutor",
    "TextChunker",
    "ResultAggregator",
    "SplitTask",
    "WorkerInfo",
]
