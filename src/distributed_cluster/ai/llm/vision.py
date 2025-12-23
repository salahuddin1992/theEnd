"""
Vision & Embeddings - دعم الصور والتضمينات
==========================================

دعم متقدم للرؤية والتضمينات:
- Vision (image analysis) support
- Embeddings for semantic search
- Multi-modal inputs
"""

from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class ImageSource(str, Enum):
    """مصادر الصور."""

    BASE64 = "base64"
    URL = "url"
    FILE = "file"


class MediaType(str, Enum):
    """أنواع الوسائط."""

    JPEG = "image/jpeg"
    PNG = "image/png"
    GIF = "image/gif"
    WEBP = "image/webp"
    PDF = "application/pdf"


@dataclass
class ImageInput:
    """مدخلات صورة."""

    source: ImageSource
    data: str  # Base64 data, URL, or file path
    media_type: MediaType = MediaType.JPEG
    detail: str = "auto"  # auto, low, high (for OpenAI)

    @classmethod
    def from_file(cls, path: str) -> "ImageInput":
        """إنشاء من ملف."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")

        # Detect media type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        media_type = MediaType.JPEG  # default

        if mime_type:
            for mt in MediaType:
                if mt.value == mime_type:
                    media_type = mt
                    break

        # Read and encode
        with open(file_path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")

        return cls(
            source=ImageSource.BASE64,
            data=data,
            media_type=media_type,
        )

    @classmethod
    def from_url(cls, url: str) -> "ImageInput":
        """إنشاء من URL."""
        return cls(
            source=ImageSource.URL,
            data=url,
            media_type=MediaType.JPEG,  # Will be auto-detected by provider
        )

    @classmethod
    def from_base64(cls, data: str, media_type: MediaType = MediaType.JPEG) -> "ImageInput":
        """إنشاء من base64."""
        return cls(
            source=ImageSource.BASE64,
            data=data,
            media_type=media_type,
        )

    def to_anthropic_format(self) -> Dict[str, Any]:
        """تحويل لصيغة Anthropic."""
        if self.source == ImageSource.URL:
            return {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": self.data,
                },
            }
        else:
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self.media_type.value,
                    "data": self.data,
                },
            }

    def to_openai_format(self) -> Dict[str, Any]:
        """تحويل لصيغة OpenAI."""
        if self.source == ImageSource.URL:
            return {
                "type": "image_url",
                "image_url": {
                    "url": self.data,
                    "detail": self.detail,
                },
            }
        else:
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{self.media_type.value};base64,{self.data}",
                    "detail": self.detail,
                },
            }

    def to_gemini_format(self) -> Dict[str, Any]:
        """تحويل لصيغة Gemini."""
        if self.source == ImageSource.URL:
            # Gemini requires inline data, fetch URL
            return {
                "inline_data": {
                    "mime_type": self.media_type.value,
                    "data": self.data,  # Will need to fetch and convert
                },
            }
        else:
            return {
                "inline_data": {
                    "mime_type": self.media_type.value,
                    "data": self.data,
                },
            }


@dataclass
class VisionMessage:
    """رسالة تحتوي على نص وصور."""

    text: str
    images: List[ImageInput] = field(default_factory=list)
    role: str = "user"

    def to_anthropic_content(self) -> List[Dict[str, Any]]:
        """تحويل لمحتوى Anthropic."""
        content = []

        # Add images first
        for image in self.images:
            content.append(image.to_anthropic_format())

        # Add text
        if self.text:
            content.append({"type": "text", "text": self.text})

        return content

    def to_openai_content(self) -> List[Dict[str, Any]]:
        """تحويل لمحتوى OpenAI."""
        content = []

        # Add text first
        if self.text:
            content.append({"type": "text", "text": self.text})

        # Add images
        for image in self.images:
            content.append(image.to_openai_format())

        return content


@dataclass
class EmbeddingResult:
    """نتيجة embedding."""

    embedding: List[float]
    model: str
    provider: str
    input_tokens: int = 0
    dimensions: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def dimension_count(self) -> int:
        return len(self.embedding)


@dataclass
class BatchEmbeddingResult:
    """نتائج embedding متعددة."""

    embeddings: List[List[float]]
    model: str
    provider: str
    total_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class EmbeddingProvider(ABC):
    """واجهة موفر embeddings."""

    @abstractmethod
    async def create_embedding(self, text: str) -> EmbeddingResult:
        """إنشاء embedding لنص واحد."""
        pass

    @abstractmethod
    async def create_embeddings(self, texts: List[str]) -> BatchEmbeddingResult:
        """إنشاء embeddings لنصوص متعددة."""
        pass


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """موفر embeddings من OpenAI."""

    MODELS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def create_embedding(self, text: str) -> EmbeddingResult:
        """إنشاء embedding لنص واحد."""
        result = await self.create_embeddings([text])
        return EmbeddingResult(
            embedding=result.embeddings[0],
            model=result.model,
            provider="openai",
            input_tokens=result.total_tokens,
            dimensions=len(result.embeddings[0]),
        )

    async def create_embeddings(self, texts: List[str]) -> BatchEmbeddingResult:
        """إنشاء embeddings لنصوص متعددة."""
        response = await self._client.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": texts,
            },
        )

        response.raise_for_status()
        data = response.json()

        embeddings = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

        return BatchEmbeddingResult(
            embeddings=embeddings,
            model=self.model,
            provider="openai",
            total_tokens=data.get("usage", {}).get("total_tokens", 0),
        )

    async def close(self) -> None:
        await self._client.aclose()


class CohereEmbeddingProvider(EmbeddingProvider):
    """موفر embeddings من Cohere."""

    MODELS = {
        "embed-english-v3.0": 1024,
        "embed-multilingual-v3.0": 1024,
        "embed-english-light-v3.0": 384,
        "embed-multilingual-light-v3.0": 384,
    }

    def __init__(
        self,
        api_key: str,
        model: str = "embed-english-v3.0",
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def create_embedding(self, text: str) -> EmbeddingResult:
        """إنشاء embedding لنص واحد."""
        result = await self.create_embeddings([text])
        return EmbeddingResult(
            embedding=result.embeddings[0],
            model=result.model,
            provider="cohere",
            dimensions=len(result.embeddings[0]),
        )

    async def create_embeddings(
        self,
        texts: List[str],
        input_type: str = "search_document",
    ) -> BatchEmbeddingResult:
        """
        إنشاء embeddings لنصوص متعددة.

        Args:
            texts: قائمة النصوص
            input_type: نوع المدخلات (search_document, search_query, classification, clustering)
        """
        response = await self._client.post(
            "https://api.cohere.ai/v1/embed",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "texts": texts,
                "input_type": input_type,
            },
        )

        response.raise_for_status()
        data = response.json()

        return BatchEmbeddingResult(
            embeddings=data["embeddings"],
            model=self.model,
            provider="cohere",
            metadata={"input_type": input_type},
        )

    async def close(self) -> None:
        await self._client.aclose()


class VoyageEmbeddingProvider(EmbeddingProvider):
    """موفر embeddings من Voyage AI."""

    MODELS = {
        "voyage-3": 1024,
        "voyage-3-lite": 512,
        "voyage-code-3": 1024,
        "voyage-finance-2": 1024,
        "voyage-law-2": 1024,
    }

    def __init__(
        self,
        api_key: str,
        model: str = "voyage-3",
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def create_embedding(self, text: str) -> EmbeddingResult:
        """إنشاء embedding لنص واحد."""
        result = await self.create_embeddings([text])
        return EmbeddingResult(
            embedding=result.embeddings[0],
            model=result.model,
            provider="voyage",
            input_tokens=result.total_tokens,
            dimensions=len(result.embeddings[0]),
        )

    async def create_embeddings(
        self,
        texts: List[str],
        input_type: Optional[str] = None,
    ) -> BatchEmbeddingResult:
        """إنشاء embeddings لنصوص متعددة."""
        payload = {
            "model": self.model,
            "input": texts,
        }
        if input_type:
            payload["input_type"] = input_type

        response = await self._client.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        response.raise_for_status()
        data = response.json()

        embeddings = [item["embedding"] for item in data["data"]]

        return BatchEmbeddingResult(
            embeddings=embeddings,
            model=self.model,
            provider="voyage",
            total_tokens=data.get("usage", {}).get("total_tokens", 0),
        )

    async def close(self) -> None:
        await self._client.aclose()


class OllamaEmbeddingProvider(EmbeddingProvider):
    """موفر embeddings من Ollama (محلي)."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: float = 60.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def create_embedding(self, text: str) -> EmbeddingResult:
        """إنشاء embedding لنص واحد."""
        response = await self._client.post(
            f"{self.base_url}/api/embeddings",
            json={
                "model": self.model,
                "prompt": text,
            },
        )

        response.raise_for_status()
        data = response.json()

        return EmbeddingResult(
            embedding=data["embedding"],
            model=self.model,
            provider="ollama",
            dimensions=len(data["embedding"]),
        )

    async def create_embeddings(self, texts: List[str]) -> BatchEmbeddingResult:
        """إنشاء embeddings لنصوص متعددة."""
        import asyncio

        results = await asyncio.gather(*[self.create_embedding(t) for t in texts])

        return BatchEmbeddingResult(
            embeddings=[r.embedding for r in results],
            model=self.model,
            provider="ollama",
        )

    async def close(self) -> None:
        await self._client.aclose()


# ==================== Utility Functions ====================


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """حساب التشابه الكوساين بين متجهين."""
    import math

    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x * x for x in a))
    magnitude_b = math.sqrt(sum(x * x for x in b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def euclidean_distance(a: List[float], b: List[float]) -> float:
    """حساب المسافة الإقليدية بين متجهين."""
    import math

    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def dot_product(a: List[float], b: List[float]) -> float:
    """حساب الجداء النقطي بين متجهين."""
    return sum(x * y for x, y in zip(a, b))


async def fetch_image_as_base64(url: str, timeout: float = 30.0) -> ImageInput:
    """جلب صورة من URL وتحويلها لـ base64."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "image/jpeg")
        media_type = MediaType.JPEG

        for mt in MediaType:
            if mt.value in content_type:
                media_type = mt
                break

        data = base64.standard_b64encode(response.content).decode("utf-8")

        return ImageInput(
            source=ImageSource.BASE64,
            data=data,
            media_type=media_type,
        )


# ==================== Semantic Search Helper ====================


@dataclass
class SearchResult:
    """نتيجة بحث دلالي."""

    text: str
    score: float
    index: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class SemanticSearchIndex:
    """فهرس للبحث الدلالي."""

    def __init__(self, embedding_provider: EmbeddingProvider):
        self.provider = embedding_provider
        self._documents: List[str] = []
        self._embeddings: List[List[float]] = []
        self._metadata: List[Dict[str, Any]] = []

    async def add_documents(
        self,
        documents: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """إضافة مستندات للفهرس."""
        result = await self.provider.create_embeddings(documents)

        self._documents.extend(documents)
        self._embeddings.extend(result.embeddings)

        if metadata:
            self._metadata.extend(metadata)
        else:
            self._metadata.extend([{} for _ in documents])

    async def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> List[SearchResult]:
        """البحث عن المستندات الأكثر تشابهاً."""
        query_result = await self.provider.create_embedding(query)
        query_embedding = query_result.embedding

        # Calculate similarities
        scores = [
            (i, cosine_similarity(query_embedding, emb))
            for i, emb in enumerate(self._embeddings)
        ]

        # Sort by score descending
        scores.sort(key=lambda x: -x[1])

        # Filter and return top_k
        results = []
        for idx, score in scores[:top_k]:
            if score >= threshold:
                results.append(SearchResult(
                    text=self._documents[idx],
                    score=score,
                    index=idx,
                    metadata=self._metadata[idx],
                ))

        return results

    def clear(self) -> None:
        """مسح الفهرس."""
        self._documents.clear()
        self._embeddings.clear()
        self._metadata.clear()

    @property
    def size(self) -> int:
        return len(self._documents)


# ==================== Factory ====================


def create_embedding_provider(
    provider: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs,
) -> EmbeddingProvider:
    """إنشاء موفر embeddings."""
    if provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=api_key or "",
            model=model or "text-embedding-3-small",
            **kwargs,
        )
    elif provider == "cohere":
        return CohereEmbeddingProvider(
            api_key=api_key or "",
            model=model or "embed-english-v3.0",
            **kwargs,
        )
    elif provider == "voyage":
        return VoyageEmbeddingProvider(
            api_key=api_key or "",
            model=model or "voyage-3",
            **kwargs,
        )
    elif provider == "ollama":
        return OllamaEmbeddingProvider(
            model=model or "nomic-embed-text",
            **kwargs,
        )
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")
