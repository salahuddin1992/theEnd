"""
LLM Response Cache - ذاكرة التخزين المؤقت للاستجابات
===================================================

تخزين مؤقت للاستجابات لتحسين الأداء وتقليل التكاليف:
- Cache responses by prompt hash
- TTL-based expiration
- LRU eviction policy
- Memory and Redis backends
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """إعدادات التخزين المؤقت."""

    enabled: bool = True
    backend: str = "memory"  # memory, redis
    max_size: int = 1000  # Max entries
    ttl_seconds: int = 3600  # 1 hour default

    # Redis settings
    redis_url: str = "redis://localhost:6379"
    redis_prefix: str = "llm_cache:"

    # Advanced
    hash_algorithm: str = "sha256"
    include_config_in_hash: bool = True  # Include generation config in cache key


@dataclass
class CacheEntry:
    """إدخال في الذاكرة المؤقتة."""

    key: str
    response_text: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    created_at: datetime
    expires_at: datetime
    hit_count: int = 0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "response_text": self.response_text,
            "model": self.model,
            "provider": self.provider,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "hit_count": self.hit_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        return cls(
            key=data["key"],
            response_text=data["response_text"],
            model=data["model"],
            provider=data["provider"],
            prompt_tokens=data["prompt_tokens"],
            completion_tokens=data["completion_tokens"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            hit_count=data.get("hit_count", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CacheStats:
    """إحصائيات التخزين المؤقت."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expired: int = 0
    size: int = 0
    total_saved_tokens: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expired": self.expired,
            "size": self.size,
            "hit_rate": self.hit_rate,
            "total_saved_tokens": self.total_saved_tokens,
        }


class CacheBackend(ABC):
    """واجهة backend للتخزين المؤقت."""

    @abstractmethod
    async def get(self, key: str) -> Optional[CacheEntry]:
        """الحصول على إدخال من الذاكرة المؤقتة."""
        pass

    @abstractmethod
    async def set(self, entry: CacheEntry) -> None:
        """تخزين إدخال في الذاكرة المؤقتة."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """حذف إدخال من الذاكرة المؤقتة."""
        pass

    @abstractmethod
    async def clear(self) -> int:
        """مسح جميع الإدخالات."""
        pass

    @abstractmethod
    async def size(self) -> int:
        """عدد الإدخالات الحالية."""
        pass

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """تنظيف الإدخالات المنتهية الصلاحية."""
        pass


class MemoryCacheBackend(CacheBackend):
    """تخزين مؤقت في الذاكرة مع LRU eviction."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[CacheEntry]:
        async with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]

            # Check expiration
            if entry.is_expired:
                del self._cache[key]
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.hit_count += 1
            return entry

    async def set(self, entry: CacheEntry) -> None:
        async with self._lock:
            # Evict if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)  # Remove oldest

            self._cache[entry.key] = entry
            self._cache.move_to_end(entry.key)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> int:
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    async def size(self) -> int:
        return len(self._cache)

    async def cleanup_expired(self) -> int:
        async with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() if v.is_expired
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)


class RedisCacheBackend(CacheBackend):
    """تخزين مؤقت في Redis للنشر الموزع."""

    def __init__(self, redis_url: str = "redis://localhost:6379", prefix: str = "llm_cache:"):
        self.redis_url = redis_url
        self.prefix = prefix
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = await aioredis.from_url(self.redis_url)
            except ImportError:
                raise ImportError("redis package is required for Redis cache backend")
        return self._redis

    def _make_key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    async def get(self, key: str) -> Optional[CacheEntry]:
        redis = await self._get_redis()
        full_key = self._make_key(key)

        data = await redis.get(full_key)
        if data is None:
            return None

        try:
            entry = CacheEntry.from_dict(json.loads(data))

            # Update hit count
            entry.hit_count += 1
            await redis.set(
                full_key,
                json.dumps(entry.to_dict()),
                keepttl=True,
            )

            return entry
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to decode cache entry: {e}")
            await redis.delete(full_key)
            return None

    async def set(self, entry: CacheEntry) -> None:
        redis = await self._get_redis()
        full_key = self._make_key(entry.key)

        ttl = int((entry.expires_at - datetime.utcnow()).total_seconds())
        if ttl > 0:
            await redis.setex(
                full_key,
                ttl,
                json.dumps(entry.to_dict()),
            )

    async def delete(self, key: str) -> bool:
        redis = await self._get_redis()
        result = await redis.delete(self._make_key(key))
        return result > 0

    async def clear(self) -> int:
        redis = await self._get_redis()
        keys = []
        async for key in redis.scan_iter(f"{self.prefix}*"):
            keys.append(key)

        if keys:
            return await redis.delete(*keys)
        return 0

    async def size(self) -> int:
        redis = await self._get_redis()
        count = 0
        async for _ in redis.scan_iter(f"{self.prefix}*"):
            count += 1
        return count

    async def cleanup_expired(self) -> int:
        # Redis handles TTL automatically
        return 0

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None


class LLMCache:
    """
    مدير التخزين المؤقت لاستجابات LLM.

    الاستخدام:
        cache = LLMCache(CacheConfig(enabled=True, max_size=1000))
        await cache.initialize()

        # Check cache before API call
        cached = await cache.get(prompt, model, config)
        if cached:
            return cached

        # After API call
        await cache.set(prompt, model, config, response)
    """

    def __init__(self, config: CacheConfig):
        self.config = config
        self._backend: Optional[CacheBackend] = None
        self._stats = CacheStats()
        self._initialized = False

    async def initialize(self) -> None:
        """تهيئة الـ cache backend."""
        if not self.config.enabled:
            return

        if self.config.backend == "memory":
            self._backend = MemoryCacheBackend(self.config.max_size)
        elif self.config.backend == "redis":
            self._backend = RedisCacheBackend(
                self.config.redis_url,
                self.config.redis_prefix,
            )
        else:
            raise ValueError(f"Unknown cache backend: {self.config.backend}")

        self._initialized = True
        logger.info(f"LLM Cache initialized with {self.config.backend} backend")

    def _compute_hash(
        self,
        prompt: str,
        model: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """حساب hash للـ prompt."""
        data = {
            "prompt": prompt,
            "model": model,
        }

        if self.config.include_config_in_hash and config:
            # Include only deterministic parameters
            data["config"] = {
                k: v for k, v in sorted(config.items())
                if k not in ("stream", "seed")  # Exclude non-deterministic
            }

        content = json.dumps(data, sort_keys=True)

        if self.config.hash_algorithm == "sha256":
            return hashlib.sha256(content.encode()).hexdigest()
        elif self.config.hash_algorithm == "md5":
            # nosec B324 - MD5 used for cache key generation, not security
            return hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()
        else:
            return hashlib.sha256(content.encode()).hexdigest()

    async def get(
        self,
        prompt: str,
        model: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Optional[CacheEntry]:
        """
        الحصول على استجابة مخزنة مؤقتاً.

        Returns:
            CacheEntry if found and valid, None otherwise
        """
        if not self.config.enabled or not self._backend:
            return None

        key = self._compute_hash(prompt, model, config)
        entry = await self._backend.get(key)

        if entry:
            self._stats.hits += 1
            self._stats.total_saved_tokens += entry.completion_tokens
            logger.debug(f"Cache hit for model {model}")
        else:
            self._stats.misses += 1

        return entry

    async def set(
        self,
        prompt: str,
        model: str,
        provider: str,
        response_text: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """تخزين استجابة في الذاكرة المؤقتة."""
        if not self.config.enabled or not self._backend:
            return

        key = self._compute_hash(prompt, model, config)
        now = datetime.utcnow()

        entry = CacheEntry(
            key=key,
            response_text=response_text,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            created_at=now,
            expires_at=now + timedelta(seconds=self.config.ttl_seconds),
            metadata=metadata or {},
        )

        await self._backend.set(entry)
        logger.debug(f"Cached response for model {model}")

    async def invalidate(
        self,
        prompt: str,
        model: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """إبطال إدخال في الذاكرة المؤقتة."""
        if not self.config.enabled or not self._backend:
            return False

        key = self._compute_hash(prompt, model, config)
        return await self._backend.delete(key)

    async def clear(self) -> int:
        """مسح جميع الإدخالات."""
        if not self._backend:
            return 0

        count = await self._backend.clear()
        self._stats = CacheStats()  # Reset stats
        return count

    async def cleanup(self) -> int:
        """تنظيف الإدخالات المنتهية الصلاحية."""
        if not self._backend:
            return 0

        count = await self._backend.cleanup_expired()
        self._stats.expired += count
        return count

    async def get_stats(self) -> CacheStats:
        """الحصول على إحصائيات التخزين المؤقت."""
        if self._backend:
            self._stats.size = await self._backend.size()
        return self._stats

    async def close(self) -> None:
        """إغلاق الـ cache backend."""
        if hasattr(self._backend, "close"):
            await self._backend.close()


# ==================== Semantic Cache (Advanced) ====================


class SemanticCache:
    """
    تخزين مؤقت دلالي باستخدام embeddings.

    يبحث عن prompts متشابهة دلالياً بدلاً من المطابقة التامة.
    """

    def __init__(
        self,
        embedding_provider: Any,  # LLMProvider with embedding support
        similarity_threshold: float = 0.95,
        max_size: int = 1000,
    ):
        self.embedding_provider = embedding_provider
        self.similarity_threshold = similarity_threshold
        self.max_size = max_size
        self._cache: Dict[str, Tuple[List[float], CacheEntry]] = {}
        self._lock = asyncio.Lock()

    async def _compute_embedding(self, text: str) -> List[float]:
        """حساب embedding للنص."""
        if hasattr(self.embedding_provider, "create_embedding"):
            return await self.embedding_provider.create_embedding(text)
        raise NotImplementedError("Embedding provider must implement create_embedding")

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """حساب التشابه بين embeddings."""
        import math

        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = math.sqrt(sum(x * x for x in a))
        magnitude_b = math.sqrt(sum(x * x for x in b))

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    async def get(self, prompt: str, model: str) -> Optional[CacheEntry]:
        """البحث عن استجابة مشابهة دلالياً."""
        async with self._lock:
            if not self._cache:
                return None

            query_embedding = await self._compute_embedding(prompt)

            best_match: Optional[CacheEntry] = None
            best_similarity = 0.0

            for key, (embedding, entry) in self._cache.items():
                if entry.model != model or entry.is_expired:
                    continue

                similarity = self._cosine_similarity(query_embedding, embedding)
                if similarity > best_similarity and similarity >= self.similarity_threshold:
                    best_similarity = similarity
                    best_match = entry

            if best_match:
                best_match.hit_count += 1
                logger.debug(f"Semantic cache hit with similarity {best_similarity:.3f}")

            return best_match

    async def set(
        self,
        prompt: str,
        model: str,
        provider: str,
        response_text: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        ttl_seconds: int = 3600,
    ) -> None:
        """تخزين استجابة مع embedding."""
        async with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self.max_size:
                # Remove oldest expired or least used
                to_remove = min(
                    self._cache.items(),
                    key=lambda x: (x[1][1].is_expired, -x[1][1].hit_count),
                )[0]
                del self._cache[to_remove]

            embedding = await self._compute_embedding(prompt)
            key = hashlib.sha256(prompt.encode()).hexdigest()
            now = datetime.utcnow()

            entry = CacheEntry(
                key=key,
                response_text=response_text,
                model=model,
                provider=provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                created_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )

            self._cache[key] = (embedding, entry)

    async def clear(self) -> int:
        """مسح جميع الإدخالات."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count


# ==================== Factory ====================


def create_cache(config: Optional[CacheConfig] = None) -> LLMCache:
    """إنشاء instance من cache."""
    return LLMCache(config or CacheConfig())
