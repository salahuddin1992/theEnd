"""
Model Cache - ذاكرة تخزين مؤقت للنماذج
======================================

AI Model Caching Layer
----------------------

This module provides intelligent caching for AI models with:
- LRU eviction policy
- Model preloading
- Memory management
- Multi-backend support (Ollama, vLLM, HuggingFace)

يوفر هذا النظام تخزين مؤقت ذكي لنماذج الذكاء الاصطناعي:
- سياسة LRU للإخلاء
- تحميل مسبق للنماذج
- إدارة الذاكرة
- دعم خلفيات متعددة

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.ai.model_cache.cache import (
    ModelCache,
    ModelCacheConfig,
    CacheStats,
)
from distributed_cluster.ai.model_cache.model import (
    ModelInfo,
    ModelState,
    ModelType,
)
from distributed_cluster.ai.model_cache.loader import (
    ModelLoader,
    LoaderConfig,
    HuggingFaceLoader,
    create_loader,
)
from distributed_cluster.ai.model_cache.backends.ollama import (
    OllamaLoader,
    OllamaConfig,
)
from distributed_cluster.ai.model_cache.backends.vllm import (
    VLLMLoader,
    VLLMConfig,
)

__all__ = [
    # Cache
    "ModelCache",
    "ModelCacheConfig",
    "CacheStats",
    # Model
    "ModelInfo",
    "ModelState",
    "ModelType",
    # Loader Base
    "ModelLoader",
    "LoaderConfig",
    "create_loader",
    # HuggingFace
    "HuggingFaceLoader",
    # Ollama
    "OllamaLoader",
    "OllamaConfig",
    # vLLM
    "VLLMLoader",
    "VLLMConfig",
]
