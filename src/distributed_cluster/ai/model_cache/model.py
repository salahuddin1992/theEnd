"""
Model Info - معلومات النموذج
============================

Model Information Classes
-------------------------

This module defines model metadata and state tracking.

يحدد هذا الملف البيانات الوصفية وتتبع حالة النموذج.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    """نوع النموذج / Model type"""
    LLM = "llm"  # نماذج اللغة الكبيرة
    EMBEDDING = "embedding"  # نماذج التضمين
    VISION = "vision"  # نماذج الرؤية
    AUDIO = "audio"  # نماذج الصوت
    MULTIMODAL = "multimodal"  # نماذج متعددة الوسائط
    CUSTOM = "custom"  # نماذج مخصصة


class ModelState(str, Enum):
    """حالة النموذج / Model state"""
    UNLOADED = "unloaded"  # غير محمل
    LOADING = "loading"  # يتم التحميل
    LOADED = "loaded"  # محمل
    UNLOADING = "unloading"  # يتم الإفراغ
    ERROR = "error"  # خطأ


class ModelBackend(str, Enum):
    """خلفية النموذج / Model backend"""
    HUGGINGFACE = "huggingface"  # HuggingFace Transformers
    OLLAMA = "ollama"  # Ollama
    VLLM = "vllm"  # vLLM
    ONNX = "onnx"  # ONNX Runtime
    PYTORCH = "pytorch"  # PyTorch
    TENSORFLOW = "tensorflow"  # TensorFlow
    LOCAL = "local"  # ملفات محلية


@dataclass
class ModelSpec:
    """
    مواصفات النموذج
    Model specifications
    """
    # Identification
    model_id: str  # معرف فريد
    name: str  # الاسم المعروض
    version: str = "latest"

    # Type & Backend
    model_type: ModelType = ModelType.LLM
    backend: ModelBackend = ModelBackend.HUGGINGFACE

    # Source
    source: str = ""  # مسار أو معرف المصدر
    revision: Optional[str] = None  # إصدار Git

    # Resource requirements
    memory_required_mb: int = 0  # الذاكرة المطلوبة
    gpu_memory_required_mb: int = 0  # ذاكرة GPU المطلوبة
    requires_gpu: bool = False  # يتطلب GPU

    # Configuration
    quantization: Optional[str] = None  # مثل "int8", "int4"
    dtype: str = "float16"  # نوع البيانات
    max_batch_size: int = 1  # حجم الدفعة الأقصى
    context_length: int = 4096  # طول السياق

    # Tags
    tags: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس"""
        return {
            "model_id": self.model_id,
            "name": self.name,
            "version": self.version,
            "model_type": self.model_type.value,
            "backend": self.backend.value,
            "source": self.source,
            "revision": self.revision,
            "memory_required_mb": self.memory_required_mb,
            "gpu_memory_required_mb": self.gpu_memory_required_mb,
            "requires_gpu": self.requires_gpu,
            "quantization": self.quantization,
            "dtype": self.dtype,
            "max_batch_size": self.max_batch_size,
            "context_length": self.context_length,
            "tags": self.tags,
            "labels": self.labels,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelSpec:
        """إنشاء من قاموس"""
        return cls(
            model_id=data["model_id"],
            name=data["name"],
            version=data.get("version", "latest"),
            model_type=ModelType(data.get("model_type", "llm")),
            backend=ModelBackend(data.get("backend", "huggingface")),
            source=data.get("source", ""),
            revision=data.get("revision"),
            memory_required_mb=data.get("memory_required_mb", 0),
            gpu_memory_required_mb=data.get("gpu_memory_required_mb", 0),
            requires_gpu=data.get("requires_gpu", False),
            quantization=data.get("quantization"),
            dtype=data.get("dtype", "float16"),
            max_batch_size=data.get("max_batch_size", 1),
            context_length=data.get("context_length", 4096),
            tags=data.get("tags", []),
            labels=data.get("labels", {}),
        )


@dataclass
class ModelInfo:
    """
    معلومات النموذج المحمل
    Loaded model information
    """
    # Specification
    spec: ModelSpec

    # State
    state: ModelState = ModelState.UNLOADED
    error_message: Optional[str] = None

    # Timing
    loaded_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    load_time_seconds: float = 0.0

    # Usage statistics
    request_count: int = 0
    total_tokens_processed: int = 0
    average_latency_ms: float = 0.0

    # Memory usage (actual)
    memory_used_mb: int = 0
    gpu_memory_used_mb: int = 0

    # Reference to actual model object
    model_object: Optional[Any] = None
    tokenizer_object: Optional[Any] = None

    # Worker assignment
    worker_id: Optional[str] = None
    device: str = "cpu"  # "cpu", "cuda:0", etc.

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس (بدون model_object)"""
        return {
            "spec": self.spec.to_dict(),
            "state": self.state.value,
            "error_message": self.error_message,
            "loaded_at": self.loaded_at.isoformat() if self.loaded_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "load_time_seconds": self.load_time_seconds,
            "request_count": self.request_count,
            "total_tokens_processed": self.total_tokens_processed,
            "average_latency_ms": self.average_latency_ms,
            "memory_used_mb": self.memory_used_mb,
            "gpu_memory_used_mb": self.gpu_memory_used_mb,
            "worker_id": self.worker_id,
            "device": self.device,
        }

    @property
    def model_id(self) -> str:
        """معرف النموذج"""
        return self.spec.model_id

    @property
    def is_loaded(self) -> bool:
        """هل النموذج محمل؟"""
        return self.state == ModelState.LOADED

    @property
    def is_loading(self) -> bool:
        """هل النموذج يتم تحميله؟"""
        return self.state == ModelState.LOADING

    def update_usage(self, tokens: int = 0, latency_ms: float = 0.0) -> None:
        """تحديث إحصائيات الاستخدام"""
        self.last_used_at = datetime.now(timezone.utc)
        self.request_count += 1
        self.total_tokens_processed += tokens

        # Update average latency (rolling average)
        if self.request_count == 1:
            self.average_latency_ms = latency_ms
        else:
            self.average_latency_ms = (
                (self.average_latency_ms * (self.request_count - 1) + latency_ms)
                / self.request_count
            )


@dataclass
class PreloadConfig:
    """
    إعدادات التحميل المسبق
    Preload configuration
    """
    # Models to preload
    models: list[ModelSpec] = field(default_factory=list)

    # Preload behavior
    preload_on_startup: bool = True
    preload_timeout_seconds: int = 300
    parallel_preloads: int = 2

    # Priority
    priority_order: list[str] = field(default_factory=list)  # model_ids

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس"""
        return {
            "models": [m.to_dict() for m in self.models],
            "preload_on_startup": self.preload_on_startup,
            "preload_timeout_seconds": self.preload_timeout_seconds,
            "parallel_preloads": self.parallel_preloads,
            "priority_order": self.priority_order,
        }
