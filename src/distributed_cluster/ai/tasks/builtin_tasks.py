"""
Built-in AI Tasks - مهام AI مدمجة
===================================

Pre-defined AI tasks for common use cases.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AITaskCategory(str, Enum):
    """فئات مهام AI."""
    TEXT_GENERATION = "text_generation"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    CODE_GENERATION = "code_generation"
    ANALYSIS = "analysis"
    EMBEDDING = "embedding"
    CLASSIFICATION = "classification"
    QA = "question_answering"
    CHAT = "chat"
    CUSTOM = "custom"


@dataclass
class TaskParameter:
    """معامل مهمة."""
    name: str
    type: str  # "string", "number", "boolean", "array", "object"
    description: str = ""
    required: bool = True
    default: Any = None
    choices: List[Any] = field(default_factory=list)

    def validate(self, value: Any) -> bool:
        """التحقق من القيمة."""
        if value is None:
            return not self.required

        if self.type == "string":
            if not isinstance(value, str):
                return False
            if self.choices and value not in self.choices:
                return False

        elif self.type == "number":
            if not isinstance(value, (int, float)):
                return False

        elif self.type == "boolean":
            if not isinstance(value, bool):
                return False

        elif self.type == "array":
            if not isinstance(value, list):
                return False

        elif self.type == "object":
            if not isinstance(value, dict):
                return False

        return True


@dataclass
class TaskResult:
    """نتيجة المهمة."""
    task_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    tokens_used: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metrics": self.metrics,
            "execution_time_ms": self.execution_time_ms,
            "tokens_used": self.tokens_used,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AITask:
    """تعريف مهمة AI."""
    name: str
    category: AITaskCategory
    description: str = ""
    parameters: List[TaskParameter] = field(default_factory=list)
    system_prompt: str = ""
    template: str = ""  # Prompt template with {param} placeholders
    model: str = ""  # Preferred model
    max_tokens: int = 1024
    temperature: float = 0.7

    # Execution
    handler: Optional[Callable] = field(default=None, repr=False)

    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """التحقق من المعاملات."""
        errors = []

        for param in self.parameters:
            value = params.get(param.name, param.default)

            if param.required and value is None:
                errors.append(f"Missing required parameter: {param.name}")
            elif value is not None and not param.validate(value):
                errors.append(f"Invalid value for {param.name}: {value}")

        return errors

    def format_prompt(self, params: Dict[str, Any]) -> str:
        """تنسيق الـ prompt مع المعاملات."""
        prompt = self.template

        for param in self.parameters:
            value = params.get(param.name, param.default)
            if value is not None:
                prompt = prompt.replace(f"{{{param.name}}}", str(value))

        return prompt


class AITaskRegistry:
    """سجل مهام AI."""

    def __init__(self):
        self._tasks: Dict[str, AITask] = {}

    def register(self, task: AITask) -> None:
        """تسجيل مهمة."""
        self._tasks[task.name] = task
        logger.info(f"Registered AI task: {task.name}")

    def get(self, name: str) -> Optional[AITask]:
        """الحصول على مهمة."""
        return self._tasks.get(name)

    def list_tasks(
        self,
        category: Optional[AITaskCategory] = None,
    ) -> List[AITask]:
        """قائمة المهام."""
        tasks = list(self._tasks.values())

        if category:
            tasks = [t for t in tasks if t.category == category]

        return tasks

    def list_categories(self) -> List[str]:
        """قائمة الفئات."""
        return list(set(t.category.value for t in self._tasks.values()))


class BuiltinTasks:
    """مهام AI مدمجة جاهزة للاستخدام."""

    @staticmethod
    def summarize() -> AITask:
        """مهمة التلخيص."""
        return AITask(
            name="summarize",
            category=AITaskCategory.SUMMARIZATION,
            description="Summarize text content",
            parameters=[
                TaskParameter(
                    name="text",
                    type="string",
                    description="Text to summarize",
                    required=True,
                ),
                TaskParameter(
                    name="length",
                    type="string",
                    description="Summary length",
                    required=False,
                    default="medium",
                    choices=["short", "medium", "long"],
                ),
                TaskParameter(
                    name="style",
                    type="string",
                    description="Summary style",
                    required=False,
                    default="paragraph",
                    choices=["bullet_points", "paragraph", "key_points"],
                ),
            ],
            system_prompt="You are a helpful assistant that creates clear and accurate summaries.",
            template="Please summarize the following text in a {length} {style} format:\n\n{text}",
            max_tokens=512,
            temperature=0.5,
        )

    @staticmethod
    def translate() -> AITask:
        """مهمة الترجمة."""
        return AITask(
            name="translate",
            category=AITaskCategory.TRANSLATION,
            description="Translate text between languages",
            parameters=[
                TaskParameter(
                    name="text",
                    type="string",
                    description="Text to translate",
                    required=True,
                ),
                TaskParameter(
                    name="source_language",
                    type="string",
                    description="Source language",
                    required=False,
                    default="auto",
                ),
                TaskParameter(
                    name="target_language",
                    type="string",
                    description="Target language",
                    required=True,
                ),
            ],
            system_prompt="You are an expert translator. Translate accurately while preserving meaning and tone.",
            template="Translate the following text from {source_language} to {target_language}:\n\n{text}",
            max_tokens=2048,
            temperature=0.3,
        )

    @staticmethod
    def generate_code() -> AITask:
        """مهمة توليد الكود."""
        return AITask(
            name="generate_code",
            category=AITaskCategory.CODE_GENERATION,
            description="Generate code from description",
            parameters=[
                TaskParameter(
                    name="description",
                    type="string",
                    description="Code description/requirements",
                    required=True,
                ),
                TaskParameter(
                    name="language",
                    type="string",
                    description="Programming language",
                    required=True,
                    choices=["python", "javascript", "typescript", "java", "go", "rust", "c++"],
                ),
                TaskParameter(
                    name="include_comments",
                    type="boolean",
                    description="Include comments in code",
                    required=False,
                    default=True,
                ),
            ],
            system_prompt="You are an expert programmer. Write clean, efficient, and well-documented code.",
            template="Write {language} code for the following:\n\n{description}\n\nInclude comments: {include_comments}",
            max_tokens=2048,
            temperature=0.4,
        )

    @staticmethod
    def analyze_sentiment() -> AITask:
        """مهمة تحليل المشاعر."""
        return AITask(
            name="analyze_sentiment",
            category=AITaskCategory.ANALYSIS,
            description="Analyze sentiment of text",
            parameters=[
                TaskParameter(
                    name="text",
                    type="string",
                    description="Text to analyze",
                    required=True,
                ),
            ],
            system_prompt="You are a sentiment analysis expert.",
            template="Analyze the sentiment of the following text. Provide: overall sentiment (positive/negative/neutral), confidence score (0-1), and key emotional indicators.\n\nText: {text}",
            max_tokens=256,
            temperature=0.2,
        )

    @staticmethod
    def answer_question() -> AITask:
        """مهمة الإجابة على الأسئلة."""
        return AITask(
            name="answer_question",
            category=AITaskCategory.QA,
            description="Answer questions based on context",
            parameters=[
                TaskParameter(
                    name="context",
                    type="string",
                    description="Context/background information",
                    required=False,
                    default="",
                ),
                TaskParameter(
                    name="question",
                    type="string",
                    description="Question to answer",
                    required=True,
                ),
            ],
            system_prompt="You are a helpful assistant. Answer questions accurately based on the provided context. If unsure, say so.",
            template="Context: {context}\n\nQuestion: {question}\n\nAnswer:",
            max_tokens=1024,
            temperature=0.5,
        )

    @staticmethod
    def classify() -> AITask:
        """مهمة التصنيف."""
        return AITask(
            name="classify",
            category=AITaskCategory.CLASSIFICATION,
            description="Classify text into categories",
            parameters=[
                TaskParameter(
                    name="text",
                    type="string",
                    description="Text to classify",
                    required=True,
                ),
                TaskParameter(
                    name="categories",
                    type="array",
                    description="List of possible categories",
                    required=True,
                ),
            ],
            system_prompt="You are a text classification expert.",
            template="Classify the following text into one of these categories: {categories}\n\nText: {text}\n\nCategory:",
            max_tokens=64,
            temperature=0.1,
        )

    @staticmethod
    def extract_entities() -> AITask:
        """مهمة استخراج الكيانات."""
        return AITask(
            name="extract_entities",
            category=AITaskCategory.ANALYSIS,
            description="Extract named entities from text",
            parameters=[
                TaskParameter(
                    name="text",
                    type="string",
                    description="Text to extract entities from",
                    required=True,
                ),
                TaskParameter(
                    name="entity_types",
                    type="array",
                    description="Types of entities to extract",
                    required=False,
                    default=["person", "organization", "location", "date", "money"],
                ),
            ],
            system_prompt="You are a named entity recognition expert.",
            template="Extract {entity_types} entities from the following text. Return as JSON.\n\nText: {text}",
            max_tokens=512,
            temperature=0.1,
        )


def get_builtin_tasks() -> AITaskRegistry:
    """الحصول على سجل المهام المدمجة."""
    registry = AITaskRegistry()

    # Register all builtin tasks
    registry.register(BuiltinTasks.summarize())
    registry.register(BuiltinTasks.translate())
    registry.register(BuiltinTasks.generate_code())
    registry.register(BuiltinTasks.analyze_sentiment())
    registry.register(BuiltinTasks.answer_question())
    registry.register(BuiltinTasks.classify())
    registry.register(BuiltinTasks.extract_entities())

    return registry
