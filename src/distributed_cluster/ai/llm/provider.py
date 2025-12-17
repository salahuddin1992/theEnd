"""
LLM Provider - موفرو نماذج اللغة الكبيرة
=========================================

Supports multiple LLM backends:
- Ollama (local models)
- vLLM (high-performance serving)
- OpenAI-compatible APIs
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Union,
)

import httpx

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """أنواع الموفرين."""
    OLLAMA = "ollama"
    VLLM = "vllm"
    OPENAI = "openai"
    LOCAL = "local"


@dataclass
class GenerationConfig:
    """إعدادات التوليد."""
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 2048
    stop_sequences: List[str] = field(default_factory=list)
    repeat_penalty: float = 1.1
    seed: Optional[int] = None

    # Streaming
    stream: bool = False

    # Advanced
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0

    def to_ollama_params(self) -> Dict[str, Any]:
        """تحويل لمعاملات Ollama."""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "num_predict": self.max_tokens,
            "stop": self.stop_sequences,
            "repeat_penalty": self.repeat_penalty,
            "seed": self.seed,
        }

    def to_openai_params(self) -> Dict[str, Any]:
        """تحويل لمعاملات OpenAI."""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "stop": self.stop_sequences or None,
            "presence_penalty": self.presence_penalty,
            "frequency_penalty": self.frequency_penalty,
            "seed": self.seed,
        }


@dataclass
class LLMResponse:
    """استجابة من النموذج."""
    text: str
    model: str
    provider: str

    # Metadata
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Timing
    generation_time_ms: float = 0
    tokens_per_second: float = 0

    # Raw response
    raw_response: Optional[Dict[str, Any]] = None

    # Finish reason
    finish_reason: str = "stop"

    @property
    def total_time_seconds(self) -> float:
        return self.generation_time_ms / 1000


@dataclass
class ModelInfo:
    """معلومات النموذج."""
    name: str
    provider: str
    size_bytes: int = 0
    parameter_size: str = ""
    quantization: str = ""
    family: str = ""
    format: str = ""
    modified_at: Optional[datetime] = None

    # Capabilities
    supports_vision: bool = False
    supports_tools: bool = False
    supports_json_mode: bool = False
    context_length: int = 4096


class LLMProvider(ABC):
    """
    واجهة موفر LLM الأساسية.

    Abstract base class for all LLM providers.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """الحصول على HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self) -> None:
        """إغلاق الاتصال."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """توليد نص من النموذج."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """توليد نص مع streaming."""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        config: Optional[GenerationConfig] = None,
    ) -> LLMResponse:
        """محادثة مع النموذج."""
        pass

    @abstractmethod
    async def list_models(self) -> List[ModelInfo]:
        """قائمة النماذج المتاحة."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """فحص صحة الموفر."""
        pass

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """نوع الموفر."""
        pass


class OllamaProvider(LLMProvider):
    """
    موفر Ollama - لتشغيل النماذج محلياً.

    Ollama is a tool for running large language models locally.
    Default URL: http://localhost:11434
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        **kwargs,
    ):
        super().__init__(base_url=base_url, **kwargs)

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OLLAMA

    async def generate(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """توليد نص باستخدام Ollama."""
        config = config or GenerationConfig()
        client = await self._get_client()

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": config.to_ollama_params(),
        }

        if system_prompt:
            payload["system"] = system_prompt

        start_time = time.time()

        for attempt in range(self.max_retries):
            try:
                response = await client.post("/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()

                generation_time = (time.time() - start_time) * 1000

                return LLMResponse(
                    text=data.get("response", ""),
                    model=model,
                    provider="ollama",
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                    total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                    generation_time_ms=generation_time,
                    tokens_per_second=data.get("eval_count", 0) / (generation_time / 1000) if generation_time > 0 else 0,
                    raw_response=data,
                    finish_reason="stop" if data.get("done") else "length",
                )

            except httpx.HTTPError as e:
                logger.warning(f"Ollama request failed (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)

        raise RuntimeError("Failed to generate response")

    async def generate_stream(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """توليد نص مع streaming."""
        config = config or GenerationConfig()
        client = await self._get_client()

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": config.to_ollama_params(),
        }

        if system_prompt:
            payload["system"] = system_prompt

        async with client.stream("POST", "/api/generate", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "response" in data:
                            yield data["response"]
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        config: Optional[GenerationConfig] = None,
    ) -> LLMResponse:
        """محادثة مع Ollama."""
        config = config or GenerationConfig()
        client = await self._get_client()

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": config.to_ollama_params(),
        }

        start_time = time.time()

        response = await client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        generation_time = (time.time() - start_time) * 1000
        message = data.get("message", {})

        return LLMResponse(
            text=message.get("content", ""),
            model=model,
            provider="ollama",
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            generation_time_ms=generation_time,
            tokens_per_second=data.get("eval_count", 0) / (generation_time / 1000) if generation_time > 0 else 0,
            raw_response=data,
        )

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        config: Optional[GenerationConfig] = None,
    ) -> AsyncIterator[str]:
        """محادثة مع streaming."""
        config = config or GenerationConfig()
        client = await self._get_client()

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": config.to_ollama_params(),
        }

        async with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        message = data.get("message", {})
                        if "content" in message:
                            yield message["content"]
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    async def list_models(self) -> List[ModelInfo]:
        """قائمة نماذج Ollama."""
        client = await self._get_client()

        response = await client.get("/api/tags")
        response.raise_for_status()
        data = response.json()

        models = []
        for model_data in data.get("models", []):
            details = model_data.get("details", {})
            models.append(ModelInfo(
                name=model_data.get("name", ""),
                provider="ollama",
                size_bytes=model_data.get("size", 0),
                parameter_size=details.get("parameter_size", ""),
                quantization=details.get("quantization_level", ""),
                family=details.get("family", ""),
                format=details.get("format", ""),
                modified_at=datetime.fromisoformat(
                    model_data.get("modified_at", "").replace("Z", "+00:00")
                ) if model_data.get("modified_at") else None,
            ))

        return models

    async def pull_model(self, model: str) -> AsyncIterator[Dict[str, Any]]:
        """تحميل نموذج."""
        client = await self._get_client()

        async with client.stream(
            "POST",
            "/api/pull",
            json={"name": model, "stream": True},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    async def delete_model(self, model: str) -> bool:
        """حذف نموذج."""
        client = await self._get_client()

        response = await client.delete("/api/delete", json={"name": model})
        return response.status_code == 200

    async def health_check(self) -> bool:
        """فحص صحة Ollama."""
        try:
            client = await self._get_client()
            response = await client.get("/")
            return response.status_code == 200
        except Exception:
            return False

    async def get_model_info(self, model: str) -> Optional[ModelInfo]:
        """معلومات نموذج محدد."""
        client = await self._get_client()

        try:
            response = await client.post("/api/show", json={"name": model})
            response.raise_for_status()
            data = response.json()

            details = data.get("details", {})
            return ModelInfo(
                name=model,
                provider="ollama",
                parameter_size=details.get("parameter_size", ""),
                quantization=details.get("quantization_level", ""),
                family=details.get("family", ""),
                format=details.get("format", ""),
            )
        except httpx.HTTPError:
            return None


class VLLMProvider(LLMProvider):
    """
    موفر vLLM - لخدمة النماذج بأداء عالي.

    vLLM is a fast and easy-to-use library for LLM inference and serving.
    Uses OpenAI-compatible API.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        **kwargs,
    ):
        super().__init__(base_url=base_url, **kwargs)

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.VLLM

    async def generate(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """توليد نص باستخدام vLLM."""
        config = config or GenerationConfig()
        client = await self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **config.to_openai_params(),
        }

        start_time = time.time()

        response = await client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        generation_time = (time.time() - start_time) * 1000

        choice = data.get("choices", [{}])[0]
        usage = data.get("usage", {})

        return LLMResponse(
            text=choice.get("message", {}).get("content", ""),
            model=model,
            provider="vllm",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            generation_time_ms=generation_time,
            tokens_per_second=usage.get("completion_tokens", 0) / (generation_time / 1000) if generation_time > 0 else 0,
            raw_response=data,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def generate_stream(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """توليد نص مع streaming."""
        config = config or GenerationConfig()
        client = await self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            **config.to_openai_params(),
        }

        async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
                    except json.JSONDecodeError:
                        continue

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        config: Optional[GenerationConfig] = None,
    ) -> LLMResponse:
        """محادثة مع vLLM."""
        config = config or GenerationConfig()
        client = await self._get_client()

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **config.to_openai_params(),
        }

        start_time = time.time()

        response = await client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        generation_time = (time.time() - start_time) * 1000

        choice = data.get("choices", [{}])[0]
        usage = data.get("usage", {})

        return LLMResponse(
            text=choice.get("message", {}).get("content", ""),
            model=model,
            provider="vllm",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            generation_time_ms=generation_time,
            raw_response=data,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def list_models(self) -> List[ModelInfo]:
        """قائمة نماذج vLLM."""
        client = await self._get_client()

        response = await client.get("/v1/models")
        response.raise_for_status()
        data = response.json()

        models = []
        for model_data in data.get("data", []):
            models.append(ModelInfo(
                name=model_data.get("id", ""),
                provider="vllm",
            ))

        return models

    async def health_check(self) -> bool:
        """فحص صحة vLLM."""
        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception:
            return False


class OpenAIProvider(LLMProvider):
    """
    موفر OpenAI-compatible APIs.

    Works with OpenAI, Azure OpenAI, and other compatible services.
    """

    def __init__(
        self,
        base_url: str = "https://api.openai.com",
        api_key: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(base_url=base_url, api_key=api_key, **kwargs)

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OPENAI

    async def generate(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """توليد نص."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.chat(messages, model, config)

    async def generate_stream(
        self,
        prompt: str,
        model: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """توليد نص مع streaming."""
        config = config or GenerationConfig()
        client = await self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            **config.to_openai_params(),
        }

        async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
                    except json.JSONDecodeError:
                        continue

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        config: Optional[GenerationConfig] = None,
    ) -> LLMResponse:
        """محادثة."""
        config = config or GenerationConfig()
        client = await self._get_client()

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **config.to_openai_params(),
        }

        start_time = time.time()

        response = await client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        generation_time = (time.time() - start_time) * 1000

        choice = data.get("choices", [{}])[0]
        usage = data.get("usage", {})

        return LLMResponse(
            text=choice.get("message", {}).get("content", ""),
            model=model,
            provider="openai",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            generation_time_ms=generation_time,
            raw_response=data,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def list_models(self) -> List[ModelInfo]:
        """قائمة النماذج."""
        client = await self._get_client()

        response = await client.get("/v1/models")
        response.raise_for_status()
        data = response.json()

        models = []
        for model_data in data.get("data", []):
            models.append(ModelInfo(
                name=model_data.get("id", ""),
                provider="openai",
            ))

        return models

    async def health_check(self) -> bool:
        """فحص الصحة."""
        try:
            client = await self._get_client()
            response = await client.get("/v1/models")
            return response.status_code == 200
        except Exception:
            return False


def create_provider(
    provider_type: Union[str, ProviderType],
    **kwargs,
) -> LLMProvider:
    """إنشاء موفر حسب النوع."""
    if isinstance(provider_type, str):
        provider_type = ProviderType(provider_type.lower())

    providers = {
        ProviderType.OLLAMA: OllamaProvider,
        ProviderType.VLLM: VLLMProvider,
        ProviderType.OPENAI: OpenAIProvider,
    }

    provider_class = providers.get(provider_type)
    if not provider_class:
        raise ValueError(f"Unknown provider type: {provider_type}")

    return provider_class(**kwargs)
