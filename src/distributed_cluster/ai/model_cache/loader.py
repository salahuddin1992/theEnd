"""
Model Loader - محمل النماذج
===========================

Model Loader Interface
----------------------

This module defines the model loading interface and
provides implementations for various backends.

يحدد هذا الملف واجهة تحميل النماذج ويوفر
تطبيقات لخلفيات مختلفة.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from distributed_cluster.ai.model_cache.model import (
    ModelBackend,
    ModelInfo,
    ModelSpec,
    ModelState,
    ModelType,
)

logger = logging.getLogger(__name__)


@dataclass
class LoaderConfig:
    """
    إعدادات المحمل
    Loader configuration
    """

    # Paths
    cache_dir: str = ".model_cache"
    download_dir: str = ".model_downloads"

    # Device
    default_device: str = "auto"  # auto, cpu, cuda, cuda:0, etc.
    device_map: str = "auto"  # auto, sequential, balanced

    # Memory
    low_cpu_mem_usage: bool = True
    offload_folder: Optional[str] = None
    max_memory: Optional[dict[str, str]] = None

    # Options
    trust_remote_code: bool = False
    use_safetensors: bool = True
    torch_dtype: str = "auto"

    # Authentication
    huggingface_token: Optional[str] = None
    custom_tokens: dict[str, str] = field(default_factory=dict)


class ModelLoader(ABC):
    """
    واجهة محمل النماذج الأساسية
    Base Model Loader Interface

    جميع محملات النماذج يجب أن ترث من هذه الفئة.
    All model loaders must inherit from this class.
    """

    def __init__(self, config: Optional[LoaderConfig] = None):
        """
        تهيئة المحمل

        Args:
            config: إعدادات المحمل
        """
        self.config = config or LoaderConfig()
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """تهيئة المحمل"""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """تنظيف المحمل"""
        pass

    @abstractmethod
    async def load(
        self,
        model_id: str,
        spec: Optional[ModelSpec] = None,
    ) -> Optional[ModelInfo]:
        """
        تحميل نموذج
        Load a model

        Args:
            model_id: معرف النموذج
            spec: مواصفات النموذج

        Returns:
            معلومات النموذج أو None
        """
        pass

    @abstractmethod
    async def unload(self, model_info: ModelInfo) -> bool:
        """
        إفراغ نموذج
        Unload a model

        Args:
            model_info: معلومات النموذج

        Returns:
            True إذا تم الإفراغ بنجاح
        """
        pass

    @abstractmethod
    async def get_model_info(
        self,
        model_id: str,
    ) -> Optional[ModelSpec]:
        """
        الحصول على معلومات النموذج
        Get model information

        Args:
            model_id: معرف النموذج

        Returns:
            مواصفات النموذج أو None
        """
        pass


class HuggingFaceLoader(ModelLoader):
    """
    محمل نماذج HuggingFace
    HuggingFace Model Loader

    يحمل النماذج من HuggingFace Hub.
    Loads models from HuggingFace Hub.
    """

    def __init__(self, config: Optional[LoaderConfig] = None):
        super().__init__(config)
        self._transformers = None
        self._torch = None

    async def initialize(self) -> None:
        """تهيئة المحمل"""
        try:
            import torch
            import transformers

            self._transformers = transformers
            self._torch = torch

            # Set token if provided
            if self.config.huggingface_token:
                from huggingface_hub import login

                login(token=self.config.huggingface_token)

            # Create cache directories
            Path(self.config.cache_dir).mkdir(parents=True, exist_ok=True)
            Path(self.config.download_dir).mkdir(parents=True, exist_ok=True)

            self._initialized = True
            logger.info("HuggingFaceLoader initialized")

        except ImportError as e:
            logger.error(f"HuggingFace dependencies not installed: {e}")
            raise

    async def cleanup(self) -> None:
        """تنظيف المحمل"""
        self._initialized = False
        logger.info("HuggingFaceLoader cleaned up")

    async def load(
        self,
        model_id: str,
        spec: Optional[ModelSpec] = None,
    ) -> Optional[ModelInfo]:
        """تحميل نموذج من HuggingFace"""
        if not self._initialized:
            await self.initialize()

        try:
            loop = asyncio.get_event_loop()

            # Determine model type
            model_type = spec.model_type if spec else ModelType.LLM

            # Load based on type
            if model_type == ModelType.LLM:
                model_info = await loop.run_in_executor(
                    None,
                    self._load_llm,
                    model_id,
                    spec,
                )
            elif model_type == ModelType.EMBEDDING:
                model_info = await loop.run_in_executor(
                    None,
                    self._load_embedding,
                    model_id,
                    spec,
                )
            else:
                model_info = await loop.run_in_executor(
                    None,
                    self._load_generic,
                    model_id,
                    spec,
                )

            return model_info

        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return None

    def _load_llm(
        self,
        model_id: str,
        spec: Optional[ModelSpec] = None,
    ) -> ModelInfo:
        """تحميل نموذج LLM"""
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # Determine device
        device = self._get_device(spec)

        # Load tokenizer
        # nosec B615 - model_id is user-specified, revision pinning is optional via spec
        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            cache_dir=self.config.cache_dir,
            trust_remote_code=self.config.trust_remote_code,
            revision=spec.revision if spec and hasattr(spec, "revision") else None,
        )

        # Load model
        dtype = self._get_dtype(spec)

        model_kwargs = {
            "cache_dir": self.config.cache_dir,
            "trust_remote_code": self.config.trust_remote_code,
            "low_cpu_mem_usage": self.config.low_cpu_mem_usage,
            "torch_dtype": dtype,
        }

        if device == "auto" or "cuda" in device:
            model_kwargs["device_map"] = self.config.device_map

        if spec and spec.quantization:
            model_kwargs.update(self._get_quantization_config(spec.quantization))

        if spec and hasattr(spec, "revision") and spec.revision:
            model_kwargs["revision"] = spec.revision

        # nosec B615 - model_id is user-specified, revision pinning is optional via spec
        model = AutoModelForCausalLM.from_pretrained(model_id, **model_kwargs)

        # Get memory usage
        memory_mb = self._estimate_memory(model)
        gpu_memory_mb = self._estimate_gpu_memory(model)

        # Create spec if not provided
        if not spec:
            spec = ModelSpec(
                model_id=model_id,
                name=model_id.split("/")[-1],
                model_type=ModelType.LLM,
                backend=ModelBackend.HUGGINGFACE,
                source=model_id,
            )

        return ModelInfo(
            spec=spec,
            state=ModelState.LOADED,
            model_object=model,
            tokenizer_object=tokenizer,
            memory_used_mb=memory_mb,
            gpu_memory_used_mb=gpu_memory_mb,
            device=device,
        )

    def _load_embedding(
        self,
        model_id: str,
        spec: Optional[ModelSpec] = None,
    ) -> ModelInfo:
        """تحميل نموذج Embedding"""
        from sentence_transformers import SentenceTransformer

        device = self._get_device(spec)
        if device == "auto":
            device = "cuda" if self._torch.cuda.is_available() else "cpu"

        model = SentenceTransformer(
            model_id,
            cache_folder=self.config.cache_dir,
            device=device,
        )

        memory_mb = self._estimate_memory(model)

        if not spec:
            spec = ModelSpec(
                model_id=model_id,
                name=model_id.split("/")[-1],
                model_type=ModelType.EMBEDDING,
                backend=ModelBackend.HUGGINGFACE,
                source=model_id,
            )

        return ModelInfo(
            spec=spec,
            state=ModelState.LOADED,
            model_object=model,
            memory_used_mb=memory_mb,
            device=device,
        )

    def _load_generic(
        self,
        model_id: str,
        spec: Optional[ModelSpec] = None,
    ) -> ModelInfo:
        """تحميل نموذج عام"""
        from transformers import AutoModel, AutoTokenizer

        device = self._get_device(spec)
        dtype = self._get_dtype(spec)

        # nosec B615 - model_id is user-specified, revision pinning is optional via spec
        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            cache_dir=self.config.cache_dir,
            trust_remote_code=self.config.trust_remote_code,
            revision=spec.revision if spec and hasattr(spec, "revision") else None,
        )

        # nosec B615 - model_id is user-specified, revision pinning is optional via spec
        model = AutoModel.from_pretrained(
            model_id,
            cache_dir=self.config.cache_dir,
            trust_remote_code=self.config.trust_remote_code,
            torch_dtype=dtype,
            revision=spec.revision if spec and hasattr(spec, "revision") else None,
        )

        memory_mb = self._estimate_memory(model)

        if not spec:
            spec = ModelSpec(
                model_id=model_id,
                name=model_id.split("/")[-1],
                model_type=ModelType.CUSTOM,
                backend=ModelBackend.HUGGINGFACE,
                source=model_id,
            )

        return ModelInfo(
            spec=spec,
            state=ModelState.LOADED,
            model_object=model,
            tokenizer_object=tokenizer,
            memory_used_mb=memory_mb,
            device=device,
        )

    async def unload(self, model_info: ModelInfo) -> bool:
        """إفراغ نموذج"""
        try:
            # Delete model and tokenizer
            if model_info.model_object is not None:
                del model_info.model_object
                model_info.model_object = None

            if model_info.tokenizer_object is not None:
                del model_info.tokenizer_object
                model_info.tokenizer_object = None

            # Clear CUDA cache
            if self._torch and self._torch.cuda.is_available():
                self._torch.cuda.empty_cache()

            model_info.state = ModelState.UNLOADED
            return True

        except Exception as e:
            logger.error(f"Failed to unload model: {e}")
            return False

    async def get_model_info(
        self,
        model_id: str,
    ) -> Optional[ModelSpec]:
        """الحصول على معلومات النموذج"""
        try:
            from huggingface_hub import HfApi

            api = HfApi()
            info = api.model_info(model_id)

            # Determine model type
            model_type = ModelType.LLM
            if "sentence-transformers" in (info.tags or []):
                model_type = ModelType.EMBEDDING
            elif "image" in (info.pipeline_tag or ""):
                model_type = ModelType.VISION

            return ModelSpec(
                model_id=model_id,
                name=info.modelId.split("/")[-1],
                model_type=model_type,
                backend=ModelBackend.HUGGINGFACE,
                source=model_id,
                tags=info.tags or [],
            )

        except Exception as e:
            logger.error(f"Failed to get model info for {model_id}: {e}")
            return None

    def _get_device(self, spec: Optional[ModelSpec] = None) -> str:
        """تحديد الجهاز"""
        if spec and spec.requires_gpu:
            return "cuda" if self._torch.cuda.is_available() else "cpu"
        return self.config.default_device

    def _get_dtype(self, spec: Optional[ModelSpec] = None):
        """تحديد نوع البيانات"""
        dtype_str = spec.dtype if spec else self.config.torch_dtype

        if dtype_str == "auto":
            return "auto"
        elif dtype_str == "float16":
            return self._torch.float16
        elif dtype_str == "bfloat16":
            return self._torch.bfloat16
        elif dtype_str == "float32":
            return self._torch.float32
        else:
            return "auto"

    def _get_quantization_config(self, quantization: str) -> dict:
        """الحصول على إعدادات التكميم"""
        try:
            from transformers import BitsAndBytesConfig

            if quantization == "int8":
                return {"quantization_config": BitsAndBytesConfig(load_in_8bit=True)}
            elif quantization == "int4":
                return {
                    "quantization_config": BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=self._torch.float16,
                    )
                }
        except ImportError:
            logger.warning("bitsandbytes not installed for quantization")

        return {}

    def _estimate_memory(self, model: Any) -> int:
        """تقدير استخدام الذاكرة"""
        try:
            param_count = sum(p.numel() for p in model.parameters())
            # Rough estimate: 2 bytes per param for fp16
            return int(param_count * 2 / (1024 * 1024))
        except Exception:
            return 0

    def _estimate_gpu_memory(self, model: Any) -> int:
        """تقدير استخدام ذاكرة GPU"""
        if not self._torch.cuda.is_available():
            return 0

        try:
            allocated = self._torch.cuda.memory_allocated()
            return int(allocated / (1024 * 1024))
        except Exception:
            return 0


# Factory function
def create_loader(
    backend: ModelBackend = ModelBackend.HUGGINGFACE,
    config: Optional[LoaderConfig] = None,
) -> ModelLoader:
    """
    إنشاء محمل نماذج
    Create model loader

    Args:
        backend: خلفية التحميل
        config: إعدادات المحمل

    Returns:
        محمل النماذج
    """
    if backend == ModelBackend.HUGGINGFACE:
        return HuggingFaceLoader(config)
    else:
        raise ValueError(f"Unsupported backend: {backend}")
