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

from distributed_cluster.ai.model_cache.backends.ollama import (
    OllamaConfig,
    OllamaLoader,
)
from distributed_cluster.ai.model_cache.backends.vllm import (
    VLLMConfig,
    VLLMLoader,
)
from distributed_cluster.ai.model_cache.cache import (
    CacheStats,
    ModelCache,
    ModelCacheConfig,
)
from distributed_cluster.ai.model_cache.loader import (
    HuggingFaceLoader,
    LoaderConfig,
    ModelLoader,
    create_loader,
)
from distributed_cluster.ai.model_cache.model import (
    ModelInfo,
    ModelState,
    ModelType,
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
