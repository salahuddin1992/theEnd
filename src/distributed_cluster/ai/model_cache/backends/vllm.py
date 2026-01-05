"""
vLLM Loader - محمل نماذج vLLM
=============================

vLLM Model Loader
-----------------

This module provides high-performance model loading through vLLM.

يوفر هذا الملف تحميل نماذج عالي الأداء عبر vLLM.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from distributed_cluster.ai.model_cache.loader import (
    LoaderConfig,
    ModelLoader,
)
from distributed_cluster.ai.model_cache.model import (
    ModelBackend,
    ModelInfo,
    ModelSpec,
    ModelState,
    ModelType,
)

logger = logging.getLogger(__name__)


@dataclass
class VLLMConfig(LoaderConfig):
    """
    إعدادات محمل vLLM
    vLLM loader configuration
    """

    # Server settings
    tensor_parallel_size: int = 1
    pipeline_parallel_size: int = 1
    gpu_memory_utilization: float = 0.9

    # Model settings
    max_model_len: Optional[int] = None
    max_num_seqs: int = 256
    max_num_batched_tokens: Optional[int] = None

    # Quantization
    quantization: Optional[str] = None  # awq, gptq, squeezellm
    load_format: str = "auto"  # auto, pt, safetensors, npcache

    # Engine settings
    enforce_eager: bool = False
    disable_custom_all_reduce: bool = False

    # API server settings
    serve_mode: str = "engine"  # engine, api
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Trust settings
    trust_remote_code: bool = False


class VLLMLoader(ModelLoader):
    """
    محمل نماذج vLLM
    vLLM Model Loader

    يحمل النماذج باستخدام vLLM لأداء استدلال عالي.
    Loads models using vLLM for high-performance inference.
    """

    def __init__(self, config: Optional[VLLMConfig] = None):
        """
        تهيئة محمل vLLM

        Args:
            config: إعدادات المحمل
        """
        super().__init__(config or VLLMConfig())
        self.config: VLLMConfig = self.config

        # vLLM components
        self._llm = None
        self._sampling_params = None
        self._vllm_available = False

    async def initialize(self) -> None:
        """تهيئة المحمل"""
        try:
            import vllm  # noqa: F401

            self._vllm_available = True

            self._initialized = True
            logger.info("VLLMLoader initialized")

        except ImportError:
            logger.warning("vLLM not installed. Install with: pip install vllm")
            self._vllm_available = False
            self._initialized = True

    async def cleanup(self) -> None:
        """تنظيف المحمل"""
        if self._llm is not None:
            # vLLM cleanup
            del self._llm
            self._llm = None

            # Clear GPU memory
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

        self._initialized = False
        logger.info("VLLMLoader cleaned up")

    async def load(
        self,
        model_id: str,
        spec: Optional[ModelSpec] = None,
    ) -> Optional[ModelInfo]:
        """
        تحميل نموذج عبر vLLM
        Load model through vLLM

        Args:
            model_id: معرف النموذج (HuggingFace model ID)
            spec: مواصفات النموذج

        Returns:
            معلومات النموذج أو None
        """
        if not self._initialized:
            await self.initialize()

        if not self._vllm_available:
            logger.error("vLLM is not available")
            return None

        try:
            from vllm import LLM, SamplingParams

            loop = asyncio.get_event_loop()

            # Load model in executor (blocking operation)
            def load_model():
                return LLM(
                    model=model_id,
                    tensor_parallel_size=self.config.tensor_parallel_size,
                    pipeline_parallel_size=self.config.pipeline_parallel_size,
                    gpu_memory_utilization=self.config.gpu_memory_utilization,
                    max_model_len=self.config.max_model_len,
                    max_num_seqs=self.config.max_num_seqs,
                    max_num_batched_tokens=self.config.max_num_batched_tokens,
                    quantization=self.config.quantization,
                    load_format=self.config.load_format,
                    enforce_eager=self.config.enforce_eager,
                    trust_remote_code=self.config.trust_remote_code,
                )

            llm = await loop.run_in_executor(None, load_model)

            # Create default sampling params
            sampling_params = SamplingParams(
                temperature=0.7,
                top_p=0.9,
                max_tokens=2048,
            )

            # Create spec if not provided
            if not spec:
                spec = ModelSpec(
                    model_id=model_id,
                    name=model_id.split("/")[-1],
                    model_type=ModelType.LLM,
                    backend=ModelBackend.VLLM,
                    source=model_id,
                    requires_gpu=True,
                )

            # Estimate memory usage
            memory_mb = self._estimate_memory(llm)
            gpu_memory_mb = self._estimate_gpu_memory()

            return ModelInfo(
                spec=spec,
                state=ModelState.LOADED,
                model_object={
                    "llm": llm,
                    "sampling_params": sampling_params,
                },
                memory_used_mb=memory_mb,
                gpu_memory_used_mb=gpu_memory_mb,
                device="cuda",
            )

        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return None

    async def unload(self, model_info: ModelInfo) -> bool:
        """
        إفراغ نموذج من vLLM
        Unload model from vLLM

        Args:
            model_info: معلومات النموذج

        Returns:
            True إذا تم الإفراغ بنجاح
        """
        try:
            if model_info.model_object:
                # Delete LLM instance
                if "llm" in model_info.model_object:
                    del model_info.model_object["llm"]

                model_info.model_object = None

            # Clear GPU memory
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            model_info.state = ModelState.UNLOADED

            logger.info(f"Unloaded model {model_info.model_id} from vLLM")
            return True

        except Exception as e:
            logger.error(f"Failed to unload model: {e}")
            return False

    async def get_model_info(
        self,
        model_id: str,
    ) -> Optional[ModelSpec]:
        """
        الحصول على معلومات النموذج
        Get model information
        """
        try:
            from huggingface_hub import HfApi

            api = HfApi()
            info = api.model_info(model_id)

            return ModelSpec(
                model_id=model_id,
                name=info.modelId.split("/")[-1],
                model_type=ModelType.LLM,
                backend=ModelBackend.VLLM,
                source=model_id,
                requires_gpu=True,
                tags=info.tags or [],
            )

        except Exception as e:
            logger.error(f"Failed to get model info for {model_id}: {e}")
            return None

    def _estimate_memory(self, llm: Any) -> int:
        """تقدير استخدام الذاكرة"""
        try:
            # vLLM doesn't expose memory usage directly
            # Use heuristic based on model parameters
            return 0
        except Exception:
            return 0

    def _estimate_gpu_memory(self) -> int:
        """تقدير استخدام ذاكرة GPU"""
        try:
            import torch

            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated()
                return int(allocated / (1024 * 1024))
            return 0
        except ImportError:
            return 0

    # =========================================================================
    # vLLM API Methods
    # =========================================================================

    async def generate(
        self,
        model_info: ModelInfo,
        prompts: list[str],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> list[str]:
        """
        توليد نص باستخدام vLLM
        Generate text using vLLM

        Args:
            model_info: معلومات النموذج
            prompts: قائمة المحفزات
            temperature: درجة الحرارة
            top_p: معامل top-p
            max_tokens: أقصى عدد رموز
            **kwargs: معاملات إضافية

        Returns:
            قائمة النصوص المولدة
        """
        if not model_info.is_loaded or not model_info.model_object:
            raise RuntimeError("Model is not loaded")

        try:
            from vllm import SamplingParams

            llm = model_info.model_object["llm"]

            sampling_params = SamplingParams(
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                **kwargs,
            )

            loop = asyncio.get_event_loop()

            # Generate in executor
            outputs = await loop.run_in_executor(
                None,
                lambda: llm.generate(prompts, sampling_params),
            )

            # Extract generated text
            results = []
            for output in outputs:
                generated_text = output.outputs[0].text
                results.append(generated_text)

            return results

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise

    async def generate_streaming(
        self,
        model_info: ModelInfo,
        prompt: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 2048,
        **kwargs: Any,
    ):
        """
        توليد نص متدفق باستخدام vLLM
        Stream text generation using vLLM

        Args:
            model_info: معلومات النموذج
            prompt: المحفز
            temperature: درجة الحرارة
            top_p: معامل top-p
            max_tokens: أقصى عدد رموز
            **kwargs: معاملات إضافية

        Yields:
            النص المولد token by token
        """
        if not model_info.is_loaded or not model_info.model_object:
            raise RuntimeError("Model is not loaded")

        try:
            from vllm import SamplingParams

            llm = model_info.model_object["llm"]

            sampling_params = SamplingParams(
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                **kwargs,
            )

            # vLLM streaming requires AsyncLLMEngine
            # For now, fall back to non-streaming
            loop = asyncio.get_event_loop()

            outputs = await loop.run_in_executor(
                None,
                lambda: llm.generate([prompt], sampling_params),
            )

            generated_text = outputs[0].outputs[0].text

            # Simulate streaming by yielding chunks
            chunk_size = 10
            for i in range(0, len(generated_text), chunk_size):
                yield generated_text[i : i + chunk_size]
                await asyncio.sleep(0.01)

        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            raise

    async def start_api_server(
        self,
        model_info: ModelInfo,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> bool:
        """
        بدء خادم API لـ vLLM
        Start vLLM API server

        Args:
            model_info: معلومات النموذج
            host: المضيف
            port: المنفذ

        Returns:
            True إذا بدأ الخادم بنجاح
        """
        try:
            import subprocess
            import sys

            model_id = model_info.model_id
            host = host or self.config.api_host
            port = port or self.config.api_port

            cmd = [
                sys.executable,
                "-m",
                "vllm.entrypoints.openai.api_server",
                "--model",
                model_id,
                "--host",
                host,
                "--port",
                str(port),
                "--tensor-parallel-size",
                str(self.config.tensor_parallel_size),
                "--gpu-memory-utilization",
                str(self.config.gpu_memory_utilization),
            ]

            if self.config.quantization:
                cmd.extend(["--quantization", self.config.quantization])

            if self.config.max_model_len:
                cmd.extend(["--max-model-len", str(self.config.max_model_len)])

            if self.config.trust_remote_code:
                cmd.append("--trust-remote-code")

            # Start server in background
            subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            logger.info(f"Started vLLM API server at {host}:{port}")
            return True

        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
            return False
