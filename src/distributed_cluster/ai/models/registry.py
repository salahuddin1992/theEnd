"""
Model Registry - سجل النماذج
==============================

Manages AI models across the distributed cluster:
- Model metadata and versioning
- Model distribution to workers
- Model discovery and search
- Model lifecycle management
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class ModelSource(str, Enum):
    """مصدر النموذج."""
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"
    LOCAL = "local"
    CUSTOM = "custom"


class ModelFormat(str, Enum):
    """صيغة النموذج."""
    GGUF = "gguf"
    SAFETENSORS = "safetensors"
    PYTORCH = "pytorch"
    ONNX = "onnx"
    OTHER = "other"


class ModelStatus(str, Enum):
    """حالة النموذج."""
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


@dataclass
class ModelVersion:
    """إصدار النموذج."""
    version: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    size_bytes: int = 0
    checksum: str = ""
    changelog: str = ""

    # Metadata
    parameter_count: Optional[str] = None
    quantization: Optional[str] = None
    context_length: int = 4096

    # Performance
    tokens_per_second: Optional[float] = None
    memory_required_gb: Optional[float] = None


@dataclass
class ModelMetadata:
    """بيانات النموذج الوصفية."""
    model_id: str
    name: str
    family: str = ""
    description: str = ""

    # Source
    source: ModelSource = ModelSource.LOCAL
    source_url: str = ""

    # Format
    format: ModelFormat = ModelFormat.GGUF

    # Versions
    versions: List[ModelVersion] = field(default_factory=list)
    current_version: str = ""

    # Capabilities
    supports_chat: bool = True
    supports_completion: bool = True
    supports_embedding: bool = False
    supports_vision: bool = False
    supports_tools: bool = False

    # Tags and categories
    tags: List[str] = field(default_factory=list)
    category: str = "general"
    language: List[str] = field(default_factory=lambda: ["en"])

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Usage stats
    download_count: int = 0
    usage_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس."""
        return {
            "model_id": self.model_id,
            "name": self.name,
            "family": self.family,
            "description": self.description,
            "source": self.source.value,
            "source_url": self.source_url,
            "format": self.format.value,
            "versions": [
                {
                    "version": v.version,
                    "created_at": v.created_at.isoformat(),
                    "size_bytes": v.size_bytes,
                    "checksum": v.checksum,
                    "quantization": v.quantization,
                    "context_length": v.context_length,
                }
                for v in self.versions
            ],
            "current_version": self.current_version,
            "supports_chat": self.supports_chat,
            "supports_embedding": self.supports_embedding,
            "supports_vision": self.supports_vision,
            "tags": self.tags,
            "category": self.category,
            "language": self.language,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "download_count": self.download_count,
            "usage_count": self.usage_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelMetadata:
        """إنشاء من قاموس."""
        versions = []
        for v in data.get("versions", []):
            versions.append(ModelVersion(
                version=v.get("version", "1.0"),
                created_at=datetime.fromisoformat(v["created_at"]) if "created_at" in v else datetime.utcnow(),
                size_bytes=v.get("size_bytes", 0),
                checksum=v.get("checksum", ""),
                quantization=v.get("quantization"),
                context_length=v.get("context_length", 4096),
            ))

        return cls(
            model_id=data.get("model_id", ""),
            name=data.get("name", ""),
            family=data.get("family", ""),
            description=data.get("description", ""),
            source=ModelSource(data.get("source", "local")),
            source_url=data.get("source_url", ""),
            format=ModelFormat(data.get("format", "gguf")),
            versions=versions,
            current_version=data.get("current_version", ""),
            supports_chat=data.get("supports_chat", True),
            supports_embedding=data.get("supports_embedding", False),
            supports_vision=data.get("supports_vision", False),
            tags=data.get("tags", []),
            category=data.get("category", "general"),
            language=data.get("language", ["en"]),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.utcnow(),
            download_count=data.get("download_count", 0),
            usage_count=data.get("usage_count", 0),
        )


class ModelRegistry:
    """
    سجل النماذج.

    Central registry for managing AI models in the cluster.

    Features:
    - Model registration and discovery
    - Version management
    - Model distribution
    - Usage tracking
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        ollama_url: str = "http://localhost:11434",
    ):
        self.storage_dir = storage_dir or Path.home() / ".theend" / "models"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.ollama_url = ollama_url

        # Model cache
        self._models: Dict[str, ModelMetadata] = {}

        # Index file
        self._index_path = self.storage_dir / "index.json"

        # Load existing index
        self._load_index()

    def _load_index(self) -> None:
        """تحميل فهرس النماذج."""
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                for model_data in data.get("models", []):
                    model = ModelMetadata.from_dict(model_data)
                    self._models[model.model_id] = model

                logger.info(f"Loaded {len(self._models)} models from index")

            except Exception as e:
                logger.error(f"Failed to load model index: {e}")

    def _save_index(self) -> None:
        """حفظ فهرس النماذج."""
        data = {
            "models": [m.to_dict() for m in self._models.values()],
            "updated_at": datetime.utcnow().isoformat(),
        }

        self._index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def register_model(self, metadata: ModelMetadata) -> None:
        """تسجيل نموذج."""
        self._models[metadata.model_id] = metadata
        self._save_index()

        logger.info(f"Registered model: {metadata.model_id}")

    def unregister_model(self, model_id: str) -> bool:
        """إلغاء تسجيل نموذج."""
        if model_id in self._models:
            del self._models[model_id]
            self._save_index()
            logger.info(f"Unregistered model: {model_id}")
            return True
        return False

    def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        """الحصول على نموذج."""
        return self._models.get(model_id)

    def list_models(
        self,
        source: Optional[ModelSource] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        supports_chat: Optional[bool] = None,
        supports_vision: Optional[bool] = None,
    ) -> List[ModelMetadata]:
        """قائمة النماذج."""
        models = list(self._models.values())

        if source:
            models = [m for m in models if m.source == source]

        if category:
            models = [m for m in models if m.category == category]

        if tag:
            models = [m for m in models if tag in m.tags]

        if supports_chat is not None:
            models = [m for m in models if m.supports_chat == supports_chat]

        if supports_vision is not None:
            models = [m for m in models if m.supports_vision == supports_vision]

        return models

    def search_models(self, query: str) -> List[ModelMetadata]:
        """البحث في النماذج."""
        query_lower = query.lower()
        results = []

        for model in self._models.values():
            score = 0

            if query_lower in model.name.lower():
                score += 10
            if query_lower in model.model_id.lower():
                score += 8
            if query_lower in model.description.lower():
                score += 5
            if query_lower in model.family.lower():
                score += 3

            for tag in model.tags:
                if query_lower in tag.lower():
                    score += 2

            if score > 0:
                results.append((model, score))

        # Sort by score
        results.sort(key=lambda x: x[1], reverse=True)

        return [m for m, _ in results]

    async def sync_from_ollama(self) -> List[ModelMetadata]:
        """مزامنة النماذج من Ollama."""
        synced = []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.ollama_url}/api/tags",
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                for model_data in data.get("models", []):
                    name = model_data.get("name", "")
                    details = model_data.get("details", {})

                    model = ModelMetadata(
                        model_id=f"ollama:{name}",
                        name=name,
                        family=details.get("family", ""),
                        source=ModelSource.OLLAMA,
                        source_url=f"{self.ollama_url}",
                        versions=[
                            ModelVersion(
                                version="latest",
                                size_bytes=model_data.get("size", 0),
                                quantization=details.get("quantization_level"),
                                parameter_count=details.get("parameter_size"),
                            )
                        ],
                        current_version="latest",
                    )

                    self._models[model.model_id] = model
                    synced.append(model)

                self._save_index()
                logger.info(f"Synced {len(synced)} models from Ollama")

        except Exception as e:
            logger.error(f"Failed to sync from Ollama: {e}")

        return synced

    async def pull_model(
        self,
        model_name: str,
        source: ModelSource = ModelSource.OLLAMA,
    ) -> AsyncIterator[Dict[str, Any]]:
        """تحميل نموذج."""
        if source == ModelSource.OLLAMA:
            async for progress in self._pull_from_ollama(model_name):
                yield progress

        elif source == ModelSource.HUGGINGFACE:
            async for progress in self._pull_from_huggingface(model_name):
                yield progress

        else:
            raise ValueError(f"Unsupported source: {source}")

    async def _pull_from_ollama(
        self,
        model_name: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """تحميل من Ollama."""
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.ollama_url}/api/pull",
                json={"name": model_name, "stream": True},
                timeout=None,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            yield data

                            if data.get("status") == "success":
                                # Register model
                                await self.sync_from_ollama()

                        except json.JSONDecodeError:
                            continue

    async def _pull_from_huggingface(
        self,
        model_name: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """تحميل من HuggingFace."""
        # Note: This is a simplified implementation
        # Real implementation would use huggingface_hub library

        yield {"status": "starting", "model": model_name}

        try:
            # Download model files
            model_dir = self.storage_dir / "huggingface" / model_name.replace("/", "_")
            model_dir.mkdir(parents=True, exist_ok=True)

            async with httpx.AsyncClient() as client:
                # Get model info
                response = await client.get(
                    f"https://huggingface.co/api/models/{model_name}",
                    timeout=30.0,
                )
                response.raise_for_status()
                model_info = response.json()

                yield {"status": "downloading", "model": model_name}

                # Register model
                model = ModelMetadata(
                    model_id=f"hf:{model_name}",
                    name=model_name.split("/")[-1],
                    family=model_info.get("library_name", ""),
                    description=model_info.get("description", ""),
                    source=ModelSource.HUGGINGFACE,
                    source_url=f"https://huggingface.co/{model_name}",
                    tags=model_info.get("tags", []),
                )

                self.register_model(model)

                yield {"status": "success", "model": model_name}

        except Exception as e:
            yield {"status": "error", "error": str(e)}

    async def delete_model(
        self,
        model_id: str,
        delete_files: bool = False,
    ) -> bool:
        """حذف نموذج."""
        model = self._models.get(model_id)
        if not model:
            return False

        # Delete from Ollama if applicable
        if model.source == ModelSource.OLLAMA:
            try:
                async with httpx.AsyncClient() as client:
                    await client.delete(
                        f"{self.ollama_url}/api/delete",
                        json={"name": model.name},
                        timeout=30.0,
                    )
            except Exception as e:
                logger.warning(f"Failed to delete from Ollama: {e}")

        # Delete local files if requested
        if delete_files:
            model_dir = self.storage_dir / model_id.replace(":", "_")
            if model_dir.exists():
                shutil.rmtree(model_dir)

        # Remove from registry
        self.unregister_model(model_id)

        return True

    def get_model_path(self, model_id: str) -> Optional[Path]:
        """الحصول على مسار النموذج."""
        model = self._models.get(model_id)
        if not model:
            return None

        if model.source == ModelSource.LOCAL:
            return self.storage_dir / model_id.replace(":", "_")

        return None

    def record_usage(self, model_id: str) -> None:
        """تسجيل استخدام."""
        model = self._models.get(model_id)
        if model:
            model.usage_count += 1
            model.updated_at = datetime.utcnow()
            self._save_index()

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات السجل."""
        total_size = 0
        by_source = {}
        by_category = {}

        for model in self._models.values():
            # Size
            if model.versions:
                total_size += model.versions[0].size_bytes

            # By source
            source = model.source.value
            by_source[source] = by_source.get(source, 0) + 1

            # By category
            by_category[model.category] = by_category.get(model.category, 0) + 1

        return {
            "total_models": len(self._models),
            "total_size_bytes": total_size,
            "by_source": by_source,
            "by_category": by_category,
        }


# Popular model presets
POPULAR_MODELS = {
    "llama3.2": {
        "name": "Llama 3.2",
        "family": "llama",
        "description": "Meta's Llama 3.2 model",
        "supports_chat": True,
        "tags": ["general", "coding", "reasoning"],
    },
    "mistral": {
        "name": "Mistral",
        "family": "mistral",
        "description": "Mistral AI's base model",
        "supports_chat": True,
        "tags": ["general", "fast"],
    },
    "codellama": {
        "name": "Code Llama",
        "family": "llama",
        "description": "Meta's code-specialized Llama",
        "supports_chat": True,
        "tags": ["coding"],
        "category": "coding",
    },
    "llava": {
        "name": "LLaVA",
        "family": "llava",
        "description": "Large Language and Vision Assistant",
        "supports_chat": True,
        "supports_vision": True,
        "tags": ["vision", "multimodal"],
        "category": "multimodal",
    },
    "phi3": {
        "name": "Phi-3",
        "family": "phi",
        "description": "Microsoft's Phi-3 small language model",
        "supports_chat": True,
        "tags": ["small", "fast", "efficient"],
    },
    "qwen2": {
        "name": "Qwen 2",
        "family": "qwen",
        "description": "Alibaba's Qwen 2 model",
        "supports_chat": True,
        "tags": ["general", "multilingual"],
        "language": ["en", "zh"],
    },
}
