"""
Ollama Loader - محمل نماذج Ollama
=================================

Ollama Model Loader
-------------------

This module provides model loading through Ollama.

يوفر هذا الملف تحميل النماذج عبر Ollama.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

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
class OllamaConfig(LoaderConfig):
    """
    إعدادات محمل Ollama
    Ollama loader configuration
    """
    host: str = "http://localhost:11434"
    timeout_seconds: int = 300
    keep_alive: str = "5m"  # How long to keep model loaded


class OllamaLoader(ModelLoader):
    """
    محمل نماذج Ollama
    Ollama Model Loader

    يحمل النماذج من Ollama API ويديرها.
    Loads and manages models through Ollama API.
    """

    def __init__(self, config: Optional[OllamaConfig] = None):
        """
        تهيئة محمل Ollama

        Args:
            config: إعدادات المحمل
        """
        super().__init__(config or OllamaConfig())
        self.config: OllamaConfig = self.config
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        """تهيئة المحمل"""
        try:
            self._client = httpx.AsyncClient(
                base_url=self.config.host,
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )

            # Test connection
            response = await self._client.get("/api/version")
            response.raise_for_status()

            self._initialized = True
            logger.info(f"OllamaLoader initialized at {self.config.host}")

        except Exception as e:
            logger.error(f"Failed to initialize OllamaLoader: {e}")
            raise

    async def cleanup(self) -> None:
        """تنظيف المحمل"""
        if self._client:
            await self._client.aclose()
            self._client = None

        self._initialized = False
        logger.info("OllamaLoader cleaned up")

    async def load(
        self,
        model_id: str,
        spec: Optional[ModelSpec] = None,
    ) -> Optional[ModelInfo]:
        """
        تحميل نموذج عبر Ollama
        Load model through Ollama

        Args:
            model_id: معرف النموذج (اسم النموذج في Ollama)
            spec: مواصفات النموذج

        Returns:
            معلومات النموذج أو None
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Check if model exists locally
            if not await self._model_exists(model_id):
                # Pull the model
                logger.info(f"Pulling model {model_id} from Ollama...")
                await self._pull_model(model_id)

            # Load the model (warm it up)
            await self._warm_model(model_id)

            # Get model details
            details = await self._get_model_details(model_id)

            # Create spec if not provided
            if not spec:
                spec = ModelSpec(
                    model_id=model_id,
                    name=model_id,
                    model_type=ModelType.LLM,
                    backend=ModelBackend.OLLAMA,
                    source=model_id,
                    context_length=details.get("context_length", 4096),
                )

            # Estimate memory usage
            memory_mb = details.get("size", 0) // (1024 * 1024)

            return ModelInfo(
                spec=spec,
                state=ModelState.LOADED,
                model_object={"name": model_id, "details": details},
                memory_used_mb=memory_mb,
                device="cpu",  # Ollama manages device internally
            )

        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return None

    async def unload(self, model_info: ModelInfo) -> bool:
        """
        إفراغ نموذج من Ollama
        Unload model from Ollama

        Args:
            model_info: معلومات النموذج

        Returns:
            True إذا تم الإفراغ بنجاح
        """
        try:
            model_id = model_info.model_id

            # Send request with keep_alive=0 to unload
            await self._client.post(
                "/api/generate",
                json={
                    "model": model_id,
                    "prompt": "",
                    "keep_alive": 0,
                },
            )

            model_info.state = ModelState.UNLOADED
            model_info.model_object = None

            logger.info(f"Unloaded model {model_id} from Ollama")
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
            details = await self._get_model_details(model_id)

            if not details:
                return None

            return ModelSpec(
                model_id=model_id,
                name=model_id,
                model_type=ModelType.LLM,
                backend=ModelBackend.OLLAMA,
                source=model_id,
                context_length=details.get("context_length", 4096),
            )

        except Exception as e:
            logger.error(f"Failed to get model info for {model_id}: {e}")
            return None

    # =========================================================================
    # Ollama API Methods
    # =========================================================================

    async def _model_exists(self, model_id: str) -> bool:
        """التحقق من وجود النموذج"""
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()

            data = response.json()
            models = [m["name"] for m in data.get("models", [])]

            return model_id in models or f"{model_id}:latest" in models

        except Exception:
            return False

    async def _pull_model(self, model_id: str) -> None:
        """تنزيل النموذج"""
        async with self._client.stream(
            "POST",
            "/api/pull",
            json={"name": model_id, "stream": True},
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if line:
                    import json
                    data = json.loads(line)
                    if "error" in data:
                        raise Exception(data["error"])
                    status = data.get("status", "")
                    if status == "success":
                        break

        logger.info(f"Successfully pulled model {model_id}")

    async def _warm_model(self, model_id: str) -> None:
        """تسخين النموذج (تحميله في الذاكرة)"""
        # Send a minimal request to load the model
        await self._client.post(
            "/api/generate",
            json={
                "model": model_id,
                "prompt": "Hi",
                "keep_alive": self.config.keep_alive,
            },
            timeout=httpx.Timeout(60.0),
        )

    async def _get_model_details(self, model_id: str) -> dict[str, Any]:
        """الحصول على تفاصيل النموذج"""
        try:
            response = await self._client.post(
                "/api/show",
                json={"name": model_id},
            )
            response.raise_for_status()

            data = response.json()

            # Extract relevant details
            details = data.get("details", {})
            data.get("modelfile", "")

            # Parse context length from modelfile or parameters
            context_length = 4096
            parameters = data.get("parameters", {})
            if "num_ctx" in parameters:
                context_length = parameters["num_ctx"]

            return {
                "family": details.get("family", "unknown"),
                "parameter_size": details.get("parameter_size", "unknown"),
                "quantization_level": details.get("quantization_level", "unknown"),
                "size": data.get("size", 0),
                "context_length": context_length,
            }

        except Exception as e:
            logger.error(f"Failed to get model details: {e}")
            return {}

    async def list_models(self) -> list[str]:
        """قائمة النماذج المتاحة"""
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()

            data = response.json()
            return [m["name"] for m in data.get("models", [])]

        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []

    async def delete_model(self, model_id: str) -> bool:
        """حذف نموذج"""
        try:
            response = await self._client.delete(
                "/api/delete",
                json={"name": model_id},
            )
            response.raise_for_status()
            return True

        except Exception as e:
            logger.error(f"Failed to delete model {model_id}: {e}")
            return False
