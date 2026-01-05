"""
Built-in AI Tasks - مهام AI الجاهزة
====================================

Predefined AI tasks ready to use:
- Text Summarization (تلخيص النصوص)
- Translation (الترجمة)
- Code Generation (توليد الكود)
- Sentiment Analysis (تحليل المشاعر)
- Question Answering (الإجابة على الأسئلة)
- Text Classification (تصنيف النصوص)
- Data Extraction (استخراج البيانات)
- Content Generation (توليد المحتوى)
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class AITaskCategory(str, Enum):
    """فئات مهام AI."""

    TEXT_PROCESSING = "text_processing"  # معالجة النصوص
    CODE = "code"  # البرمجة
    ANALYSIS = "analysis"  # التحليل
    GENERATION = "generation"  # التوليد
    TRANSLATION = "translation"  # الترجمة
    EXTRACTION = "extraction"  # الاستخراج
    CONVERSATION = "conversation"  # المحادثة
    EMBEDDING = "embedding"  # التضمين
    CLASSIFICATION = "classification"  # التصنيف
    CUSTOM = "custom"  # مخصص


class ParameterType(str, Enum):
    """أنواع المعاملات."""

    STRING = "string"
    TEXT = "text"  # نص طويل
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    SELECT = "select"  # اختيار من قائمة
    MULTI_SELECT = "multi_select"
    FILE = "file"
    JSON = "json"
    ARRAY = "array"


@dataclass
class TaskParameter:
    """معامل لمهمة AI."""

    name: str
    label: str
    param_type: ParameterType
    description: str = ""
    required: bool = True
    default: Any = None
    options: List[str] = field(default_factory=list)  # للـ select
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    placeholder: str = ""

    def validate(self, value: Any) -> tuple[bool, str]:
        """التحقق من صحة القيمة."""
        if self.required and value is None:
            return False, f"Parameter '{self.name}' is required"

        if value is None:
            return True, ""

        if self.param_type == ParameterType.STRING:
            if not isinstance(value, str):
                return False, f"Parameter '{self.name}' must be a string"

        elif self.param_type == ParameterType.NUMBER:
            if not isinstance(value, (int, float)):
                return False, f"Parameter '{self.name}' must be a number"
            if self.min_value is not None and value < self.min_value:
                return False, f"Parameter '{self.name}' must be >= {self.min_value}"
            if self.max_value is not None and value > self.max_value:
                return False, f"Parameter '{self.name}' must be <= {self.max_value}"

        elif self.param_type == ParameterType.INTEGER:
            if not isinstance(value, int):
                return False, f"Parameter '{self.name}' must be an integer"

        elif self.param_type == ParameterType.BOOLEAN:
            if not isinstance(value, bool):
                return False, f"Parameter '{self.name}' must be a boolean"

        elif self.param_type == ParameterType.SELECT:
            if value not in self.options:
                return False, f"Parameter '{self.name}' must be one of {self.options}"

        elif self.param_type == ParameterType.ARRAY:
            if not isinstance(value, list):
                return False, f"Parameter '{self.name}' must be an array"

        return True, ""


@dataclass
class TaskResult:
    """نتيجة تنفيذ مهمة AI."""

    task_id: str
    task_name: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0
    tokens_used: int = 0
    model: str = ""
    worker_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "tokens_used": self.tokens_used,
            "model": self.model,
            "worker_id": self.worker_id,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AITask:
    """
    مهمة AI جاهزة للاستخدام.

    Defines a reusable AI task with:
    - Prompt template
    - Input parameters
    - Output format
    - Recommended models
    """

    task_id: str
    name: str
    name_ar: str  # الاسم بالعربية
    description: str
    description_ar: str
    category: AITaskCategory
    prompt_template: str
    parameters: List[TaskParameter]
    output_format: str = "text"  # text, json, markdown, code
    recommended_models: List[str] = field(default_factory=list)
    icon: str = "🤖"
    tags: List[str] = field(default_factory=list)
    supports_streaming: bool = True
    supports_distributed: bool = True
    max_input_tokens: int = 4000
    estimated_output_tokens: int = 1000

    # Execution handler (optional)
    handler: Optional[Callable] = field(default=None, repr=False)

    def build_prompt(self, **kwargs) -> str:
        """بناء الـ prompt من المعاملات."""
        try:
            return self.prompt_template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing parameter: {e}")

    def validate_parameters(self, params: Dict[str, Any]) -> tuple[bool, List[str]]:
        """التحقق من المعاملات."""
        errors = []

        for param in self.parameters:
            value = params.get(param.name, param.default)
            valid, error = param.validate(value)
            if not valid:
                errors.append(error)

        return len(errors) == 0, errors

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "name_ar": self.name_ar,
            "description": self.description,
            "description_ar": self.description_ar,
            "category": self.category.value,
            "parameters": [
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
                for p in self.parameters
            ],
            "output_format": self.output_format,
            "recommended_models": self.recommended_models,
            "icon": self.icon,
            "tags": self.tags,
            "supports_streaming": self.supports_streaming,
            "supports_distributed": self.supports_distributed,
        }


class BuiltinTasks:
    """مهام AI الجاهزة المدمجة."""

    @staticmethod
    def text_summarization() -> AITask:
        """تلخيص النصوص."""
        return AITask(
            task_id="summarize",
            name="Text Summarization",
            name_ar="تلخيص النصوص",
            description="Summarize long texts into concise summaries",
            description_ar="تلخيص النصوص الطويلة إلى ملخصات موجزة",
            category=AITaskCategory.TEXT_PROCESSING,
            icon="📝",
            tags=["text", "summarization", "nlp"],
            prompt_template="""Please summarize the following text in {style} style.
Target length: {length}
Language: {language}

Text to summarize:
{text}

Summary:""",
            parameters=[
                TaskParameter(
                    name="text",
                    label="Text to Summarize",
                    param_type=ParameterType.TEXT,
                    description="The text you want to summarize",
                    placeholder="Paste your text here...",
                ),
                TaskParameter(
                    name="style",
                    label="Summary Style",
                    param_type=ParameterType.SELECT,
                    description="The style of summary",
                    default="concise",
                    options=["concise", "detailed", "bullet_points", "executive"],
                ),
                TaskParameter(
                    name="length",
                    label="Target Length",
                    param_type=ParameterType.SELECT,
                    description="Desired summary length",
                    default="medium",
                    options=["short", "medium", "long"],
                ),
                TaskParameter(
                    name="language",
                    label="Output Language",
                    param_type=ParameterType.SELECT,
                    description="Language for the summary",
                    default="same",
                    options=["same", "english", "arabic", "spanish", "french", "german"],
                ),
            ],
            recommended_models=["llama3.2", "mistral", "gpt-4"],
        )

    @staticmethod
    def translation() -> AITask:
        """الترجمة."""
        return AITask(
            task_id="translate",
            name="Translation",
            name_ar="الترجمة",
            description="Translate text between languages",
            description_ar="ترجمة النصوص بين اللغات",
            category=AITaskCategory.TRANSLATION,
            icon="🌐",
            tags=["translation", "language", "nlp"],
            prompt_template="""Translate the following text from {source_language} to {target_language}.
Maintain the original tone and style: {preserve_style}

Text to translate:
{text}

Translation:""",
            parameters=[
                TaskParameter(
                    name="text",
                    label="Text to Translate",
                    param_type=ParameterType.TEXT,
                    description="The text you want to translate",
                    placeholder="Enter text to translate...",
                ),
                TaskParameter(
                    name="source_language",
                    label="Source Language",
                    param_type=ParameterType.SELECT,
                    description="Original language",
                    default="auto",
                    options=["auto", "english", "arabic", "spanish", "french", "german", "chinese", "japanese"],
                ),
                TaskParameter(
                    name="target_language",
                    label="Target Language",
                    param_type=ParameterType.SELECT,
                    description="Language to translate to",
                    default="english",
                    options=["english", "arabic", "spanish", "french", "german", "chinese", "japanese"],
                ),
                TaskParameter(
                    name="preserve_style",
                    label="Preserve Style",
                    param_type=ParameterType.BOOLEAN,
                    description="Keep the original tone and style",
                    default=True,
                ),
            ],
            recommended_models=["llama3.2", "mistral", "gpt-4"],
        )

    @staticmethod
    def code_generation() -> AITask:
        """توليد الكود."""
        return AITask(
            task_id="code_gen",
            name="Code Generation",
            name_ar="توليد الكود",
            description="Generate code from natural language descriptions",
            description_ar="توليد الكود من وصف باللغة الطبيعية",
            category=AITaskCategory.CODE,
            icon="💻",
            tags=["code", "programming", "generation"],
            output_format="code",
            prompt_template="""Generate {language} code for the following task:

Task Description:
{description}

Requirements:
- Include comments: {include_comments}
- Include error handling: {include_error_handling}
- Code style: {code_style}

Additional context:
{context}

Generated Code:""",
            parameters=[
                TaskParameter(
                    name="description",
                    label="Task Description",
                    param_type=ParameterType.TEXT,
                    description="Describe what the code should do",
                    placeholder="Describe the function or code you need...",
                ),
                TaskParameter(
                    name="language",
                    label="Programming Language",
                    param_type=ParameterType.SELECT,
                    description="Target programming language",
                    default="python",
                    options=["python", "javascript", "typescript", "java", "c++", "go", "rust", "c#"],
                ),
                TaskParameter(
                    name="include_comments",
                    label="Include Comments",
                    param_type=ParameterType.BOOLEAN,
                    description="Add code comments",
                    default=True,
                ),
                TaskParameter(
                    name="include_error_handling",
                    label="Include Error Handling",
                    param_type=ParameterType.BOOLEAN,
                    description="Add error handling",
                    default=True,
                ),
                TaskParameter(
                    name="code_style",
                    label="Code Style",
                    param_type=ParameterType.SELECT,
                    description="Coding style preference",
                    default="clean",
                    options=["clean", "verbose", "minimal", "enterprise"],
                ),
                TaskParameter(
                    name="context",
                    label="Additional Context",
                    param_type=ParameterType.TEXT,
                    description="Any additional context or requirements",
                    required=False,
                    default="",
                    placeholder="Optional: existing code, libraries to use, etc.",
                ),
            ],
            recommended_models=["codellama", "deepseek-coder", "gpt-4"],
        )

    @staticmethod
    def sentiment_analysis() -> AITask:
        """تحليل المشاعر."""
        return AITask(
            task_id="sentiment",
            name="Sentiment Analysis",
            name_ar="تحليل المشاعر",
            description="Analyze the sentiment of text",
            description_ar="تحليل مشاعر النصوص (إيجابي/سلبي/محايد)",
            category=AITaskCategory.ANALYSIS,
            icon="😊",
            tags=["sentiment", "analysis", "nlp"],
            output_format="json",
            prompt_template="""Analyze the sentiment of the following text.
Provide analysis in {detail_level} detail.

Text:
{text}

Return a JSON object with:
- sentiment: "positive", "negative", or "neutral"
- confidence: 0.0 to 1.0
- emotions: list of detected emotions
- key_phrases: phrases that indicate sentiment
{additional_analysis}

Analysis:""",
            parameters=[
                TaskParameter(
                    name="text",
                    label="Text to Analyze",
                    param_type=ParameterType.TEXT,
                    description="The text to analyze for sentiment",
                    placeholder="Enter text to analyze...",
                ),
                TaskParameter(
                    name="detail_level",
                    label="Detail Level",
                    param_type=ParameterType.SELECT,
                    description="How detailed the analysis should be",
                    default="medium",
                    options=["basic", "medium", "detailed"],
                ),
                TaskParameter(
                    name="additional_analysis",
                    label="Additional Analysis",
                    param_type=ParameterType.MULTI_SELECT,
                    description="Additional analysis to include",
                    required=False,
                    default=[],
                    options=["emotions", "key_phrases", "summary", "recommendations"],
                ),
            ],
            recommended_models=["llama3.2", "mistral"],
        )

    @staticmethod
    def question_answering() -> AITask:
        """الإجابة على الأسئلة."""
        return AITask(
            task_id="qa",
            name="Question Answering",
            name_ar="الإجابة على الأسئلة",
            description="Answer questions based on provided context",
            description_ar="الإجابة على الأسئلة بناءً على سياق محدد",
            category=AITaskCategory.CONVERSATION,
            icon="❓",
            tags=["qa", "question", "answering"],
            prompt_template="""Based on the following context, answer the question.
If the answer is not in the context, say so.

Context:
{context}

Question: {question}

Answer style: {answer_style}
Include sources: {include_sources}

Answer:""",
            parameters=[
                TaskParameter(
                    name="context",
                    label="Context",
                    param_type=ParameterType.TEXT,
                    description="The context/document to search for answers",
                    placeholder="Paste the context here...",
                ),
                TaskParameter(
                    name="question",
                    label="Question",
                    param_type=ParameterType.STRING,
                    description="Your question",
                    placeholder="What is your question?",
                ),
                TaskParameter(
                    name="answer_style",
                    label="Answer Style",
                    param_type=ParameterType.SELECT,
                    description="How to format the answer",
                    default="detailed",
                    options=["brief", "detailed", "step_by_step"],
                ),
                TaskParameter(
                    name="include_sources",
                    label="Include Sources",
                    param_type=ParameterType.BOOLEAN,
                    description="Quote relevant parts from context",
                    default=True,
                ),
            ],
            recommended_models=["llama3.2", "mistral", "gpt-4"],
        )

    @staticmethod
    def text_classification() -> AITask:
        """تصنيف النصوص."""
        return AITask(
            task_id="classify",
            name="Text Classification",
            name_ar="تصنيف النصوص",
            description="Classify text into categories",
            description_ar="تصنيف النصوص إلى فئات محددة",
            category=AITaskCategory.CLASSIFICATION,
            icon="🏷️",
            tags=["classification", "categorization", "nlp"],
            output_format="json",
            prompt_template="""Classify the following text into one or more of these categories:
Categories: {categories}

Text:
{text}

Allow multiple categories: {multi_label}
Provide confidence scores: {with_confidence}

Return a JSON object with:
- categories: list of assigned categories
- confidence: confidence score for each category (0.0 to 1.0)
- reasoning: brief explanation

Classification:""",
            parameters=[
                TaskParameter(
                    name="text",
                    label="Text to Classify",
                    param_type=ParameterType.TEXT,
                    description="The text to classify",
                    placeholder="Enter text to classify...",
                ),
                TaskParameter(
                    name="categories",
                    label="Categories",
                    param_type=ParameterType.STRING,
                    description="Comma-separated list of categories",
                    placeholder="tech, sports, politics, entertainment, science",
                ),
                TaskParameter(
                    name="multi_label",
                    label="Multi-label",
                    param_type=ParameterType.BOOLEAN,
                    description="Allow multiple categories",
                    default=False,
                ),
                TaskParameter(
                    name="with_confidence",
                    label="Include Confidence",
                    param_type=ParameterType.BOOLEAN,
                    description="Include confidence scores",
                    default=True,
                ),
            ],
            recommended_models=["llama3.2", "mistral"],
        )

    @staticmethod
    def data_extraction() -> AITask:
        """استخراج البيانات."""
        return AITask(
            task_id="extract",
            name="Data Extraction",
            name_ar="استخراج البيانات",
            description="Extract structured data from unstructured text",
            description_ar="استخراج بيانات منظمة من نصوص غير منظمة",
            category=AITaskCategory.EXTRACTION,
            icon="📊",
            tags=["extraction", "data", "parsing"],
            output_format="json",
            prompt_template="""Extract the following information from the text:
Fields to extract: {fields}

Text:
{text}

Output format: {output_format}
Handle missing data: {missing_strategy}

Return a JSON object with the extracted fields.
If a field is not found, use null or the specified missing strategy.

Extracted Data:""",
            parameters=[
                TaskParameter(
                    name="text",
                    label="Source Text",
                    param_type=ParameterType.TEXT,
                    description="Text to extract data from",
                    placeholder="Paste text containing data to extract...",
                ),
                TaskParameter(
                    name="fields",
                    label="Fields to Extract",
                    param_type=ParameterType.STRING,
                    description="Comma-separated list of fields",
                    placeholder="name, email, phone, address, date",
                ),
                TaskParameter(
                    name="output_format",
                    label="Output Format",
                    param_type=ParameterType.SELECT,
                    description="Format of extracted data",
                    default="json",
                    options=["json", "csv", "table"],
                ),
                TaskParameter(
                    name="missing_strategy",
                    label="Missing Data Strategy",
                    param_type=ParameterType.SELECT,
                    description="How to handle missing fields",
                    default="null",
                    options=["null", "empty_string", "skip", "error"],
                ),
            ],
            recommended_models=["llama3.2", "mistral", "gpt-4"],
        )

    @staticmethod
    def content_generation() -> AITask:
        """توليد المحتوى."""
        return AITask(
            task_id="content_gen",
            name="Content Generation",
            name_ar="توليد المحتوى",
            description="Generate various types of content",
            description_ar="توليد أنواع مختلفة من المحتوى",
            category=AITaskCategory.GENERATION,
            icon="✍️",
            tags=["content", "generation", "writing"],
            prompt_template="""Generate {content_type} content about the following topic:

Topic: {topic}

Requirements:
- Tone: {tone}
- Length: {length}
- Target audience: {audience}
- Include: {include_elements}

Additional instructions:
{instructions}

Generated Content:""",
            parameters=[
                TaskParameter(
                    name="topic",
                    label="Topic",
                    param_type=ParameterType.STRING,
                    description="Main topic or subject",
                    placeholder="Enter the topic...",
                ),
                TaskParameter(
                    name="content_type",
                    label="Content Type",
                    param_type=ParameterType.SELECT,
                    description="Type of content to generate",
                    default="article",
                    options=["article", "blog_post", "social_media", "email", "product_description", "story"],
                ),
                TaskParameter(
                    name="tone",
                    label="Tone",
                    param_type=ParameterType.SELECT,
                    description="Writing tone",
                    default="professional",
                    options=["professional", "casual", "formal", "friendly", "humorous", "persuasive"],
                ),
                TaskParameter(
                    name="length",
                    label="Length",
                    param_type=ParameterType.SELECT,
                    description="Content length",
                    default="medium",
                    options=["short", "medium", "long"],
                ),
                TaskParameter(
                    name="audience",
                    label="Target Audience",
                    param_type=ParameterType.STRING,
                    description="Who is this content for",
                    default="general",
                    placeholder="e.g., developers, marketers, students",
                ),
                TaskParameter(
                    name="include_elements",
                    label="Include Elements",
                    param_type=ParameterType.MULTI_SELECT,
                    description="Elements to include",
                    required=False,
                    default=[],
                    options=["introduction", "conclusion", "examples", "statistics", "call_to_action"],
                ),
                TaskParameter(
                    name="instructions",
                    label="Additional Instructions",
                    param_type=ParameterType.TEXT,
                    description="Any additional requirements",
                    required=False,
                    default="",
                    placeholder="Optional: specific points to cover, keywords to use, etc.",
                ),
            ],
            recommended_models=["llama3.2", "mistral", "gpt-4"],
        )

    @staticmethod
    def code_review() -> AITask:
        """مراجعة الكود."""
        return AITask(
            task_id="code_review",
            name="Code Review",
            name_ar="مراجعة الكود",
            description="Review code for issues and improvements",
            description_ar="مراجعة الكود للأخطاء والتحسينات",
            category=AITaskCategory.CODE,
            icon="🔍",
            tags=["code", "review", "quality"],
            output_format="markdown",
            prompt_template="""Review the following {language} code.

Focus areas: {focus_areas}
Severity threshold: {severity}

Code:
```{language}
{code}
```

Provide:
1. Summary of code quality
2. Issues found (with severity: critical, major, minor, suggestion)
3. Specific recommendations
4. Improved code snippets where applicable

Code Review:""",
            parameters=[
                TaskParameter(
                    name="code",
                    label="Code to Review",
                    param_type=ParameterType.TEXT,
                    description="The code to review",
                    placeholder="Paste your code here...",
                ),
                TaskParameter(
                    name="language",
                    label="Programming Language",
                    param_type=ParameterType.SELECT,
                    description="Code language",
                    default="python",
                    options=["python", "javascript", "typescript", "java", "c++", "go", "rust"],
                ),
                TaskParameter(
                    name="focus_areas",
                    label="Focus Areas",
                    param_type=ParameterType.MULTI_SELECT,
                    description="What to focus on",
                    default=["bugs", "security"],
                    options=["bugs", "security", "performance", "readability", "best_practices", "documentation"],
                ),
                TaskParameter(
                    name="severity",
                    label="Minimum Severity",
                    param_type=ParameterType.SELECT,
                    description="Minimum issue severity to report",
                    default="minor",
                    options=["critical", "major", "minor", "suggestion"],
                ),
            ],
            recommended_models=["codellama", "deepseek-coder", "gpt-4"],
        )

    @staticmethod
    def text_rewriting() -> AITask:
        """إعادة صياغة النص."""
        return AITask(
            task_id="rewrite",
            name="Text Rewriting",
            name_ar="إعادة صياغة النص",
            description="Rewrite text in different styles or for different purposes",
            description_ar="إعادة صياغة النص بأساليب مختلفة أو لأغراض مختلفة",
            category=AITaskCategory.TEXT_PROCESSING,
            icon="🔄",
            tags=["rewriting", "paraphrasing", "text"],
            prompt_template="""Rewrite the following text.

Purpose: {purpose}
Target style: {style}
Preserve meaning: {preserve_meaning}
Target length: {length_change}

Original text:
{text}

Rewritten text:""",
            parameters=[
                TaskParameter(
                    name="text",
                    label="Text to Rewrite",
                    param_type=ParameterType.TEXT,
                    description="The text to rewrite",
                    placeholder="Enter text to rewrite...",
                ),
                TaskParameter(
                    name="purpose",
                    label="Purpose",
                    param_type=ParameterType.SELECT,
                    description="Why you're rewriting",
                    default="improve_clarity",
                    options=["improve_clarity", "simplify", "formalize", "make_casual", "remove_jargon", "seo_optimize"],
                ),
                TaskParameter(
                    name="style",
                    label="Target Style",
                    param_type=ParameterType.SELECT,
                    description="Desired writing style",
                    default="professional",
                    options=["professional", "academic", "conversational", "technical", "creative"],
                ),
                TaskParameter(
                    name="preserve_meaning",
                    label="Preserve Meaning",
                    param_type=ParameterType.BOOLEAN,
                    description="Keep the same meaning",
                    default=True,
                ),
                TaskParameter(
                    name="length_change",
                    label="Length Change",
                    param_type=ParameterType.SELECT,
                    description="How to change length",
                    default="same",
                    options=["shorter", "same", "longer"],
                ),
            ],
            recommended_models=["llama3.2", "mistral", "gpt-4"],
        )

    @staticmethod
    def extract_entities() -> AITask:
        """استخراج الكيانات."""
        return AITask(
            task_id="extract_entities",
            name="Entity Extraction",
            name_ar="استخراج الكيانات",
            description="Extract named entities from text",
            description_ar="استخراج الكيانات المسماة من النص",
            category=AITaskCategory.EXTRACTION,
            icon="🔎",
            tags=["entities", "ner", "extraction"],
            output_format="json",
            prompt_template="""Extract {entity_types} entities from the following text. Return as JSON.

Text: {text}""",
            parameters=[
                TaskParameter(
                    name="text",
                    label="Text",
                    param_type=ParameterType.TEXT,
                    description="Text to extract entities from",
                    placeholder="Enter text...",
                ),
                TaskParameter(
                    name="entity_types",
                    label="Entity Types",
                    param_type=ParameterType.MULTI_SELECT,
                    description="Types of entities to extract",
                    default=["person", "organization", "location"],
                    options=["person", "organization", "location", "date", "money", "product", "event"],
                ),
            ],
            recommended_models=["llama3.2", "mistral"],
        )


class AITaskRegistry:
    """سجل مهام AI."""

    def __init__(self):
        self._tasks: Dict[str, AITask] = {}
        self._load_builtin_tasks()

    def _load_builtin_tasks(self) -> None:
        """تحميل المهام المدمجة."""
        builtin = [
            BuiltinTasks.text_summarization(),
            BuiltinTasks.translation(),
            BuiltinTasks.code_generation(),
            BuiltinTasks.sentiment_analysis(),
            BuiltinTasks.question_answering(),
            BuiltinTasks.text_classification(),
            BuiltinTasks.data_extraction(),
            BuiltinTasks.content_generation(),
            BuiltinTasks.code_review(),
            BuiltinTasks.text_rewriting(),
            BuiltinTasks.extract_entities(),
        ]

        for task in builtin:
            self.register(task)

    def register(self, task: AITask) -> None:
        """تسجيل مهمة."""
        self._tasks[task.task_id] = task
        logger.debug(f"Registered AI task: {task.task_id}")

    def unregister(self, task_id: str) -> None:
        """إلغاء تسجيل مهمة."""
        if task_id in self._tasks:
            del self._tasks[task_id]

    def get(self, task_id: str) -> Optional[AITask]:
        """الحصول على مهمة."""
        return self._tasks.get(task_id)

    def list_all(self) -> List[AITask]:
        """قائمة جميع المهام."""
        return list(self._tasks.values())

    def list_by_category(self, category: AITaskCategory) -> List[AITask]:
        """قائمة المهام حسب الفئة."""
        return [t for t in self._tasks.values() if t.category == category]

    def list_tasks(self, category: Optional[AITaskCategory] = None) -> List[AITask]:
        """قائمة المهام."""
        tasks = list(self._tasks.values())
        if category:
            tasks = [t for t in tasks if t.category == category]
        return tasks

    def list_categories(self) -> List[str]:
        """قائمة الفئات."""
        return list(set(t.category.value for t in self._tasks.values()))

    def search(self, query: str) -> List[AITask]:
        """البحث في المهام."""
        query = query.lower()
        results = []

        for task in self._tasks.values():
            if (
                query in task.name.lower()
                or query in task.name_ar
                or query in task.description.lower()
                or query in task.description_ar
                or any(query in tag for tag in task.tags)
            ):
                results.append(task)

        return results

    def get_categories(self) -> List[Dict[str, Any]]:
        """قائمة الفئات مع عدد المهام."""
        category_counts: Dict[AITaskCategory, int] = {}

        for task in self._tasks.values():
            category_counts[task.category] = category_counts.get(task.category, 0) + 1

        return [
            {
                "category": cat.value,
                "name": cat.name.replace("_", " ").title(),
                "count": count,
            }
            for cat, count in category_counts.items()
        ]


# Global registry instance
_registry: Optional[AITaskRegistry] = None


def get_builtin_tasks() -> AITaskRegistry:
    """الحصول على سجل المهام المدمجة."""
    global _registry
    if _registry is None:
        _registry = AITaskRegistry()
    return _registry
