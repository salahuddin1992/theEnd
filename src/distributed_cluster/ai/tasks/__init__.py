"""
AI Tasks Module - مهام الذكاء الاصطناعي المدمجة
=================================================

Built-in AI tasks for distributed inference, training, and more.
"""

from .manager import AITaskManager, AITask, AITaskStatus, AITaskType
from .inference import DistributedInferenceTask
from .training import DistributedTrainingTask
from .embedding import EmbeddingTask

__all__ = [
    "AITaskManager",
    "AITask",
    "AITaskStatus",
    "AITaskType",
    "DistributedInferenceTask",
    "DistributedTrainingTask",
    "EmbeddingTask",
]
