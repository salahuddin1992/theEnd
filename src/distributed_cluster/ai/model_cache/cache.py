"""
Model Cache - ذاكرة التخزين المؤقت للنماذج
==========================================

LRU Model Cache
---------------

This module implements an LRU cache for AI models with
intelligent memory management and preloading.

يطبق هذا الملف ذاكرة تخزين مؤقت LRU لنماذج الذكاء الاصطناعي
مع إدارة ذكية للذاكرة والتحميل المسبق.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from distributed_cluster.ai.model_cache.loader import ModelLoader
    from distributed_cluster.ai.model_cache.model import ModelSpec

from distributed_cluster.ai.model_cache.model import (
    ModelInfo,
    ModelState,
    PreloadConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """
    إحصائيات الذاكرة المؤقتة
    Cache statistics
    """

    # Hit/Miss
    cache_hits: int = 0
    cache_misses: int = 0

    # Counts
    models_loaded: int = 0
    models_evicted: int = 0
    models_preloaded: int = 0

    # Memory
    total_memory_used_mb: int = 0
    total_gpu_memory_used_mb: int = 0
    peak_memory_used_mb: int = 0

    # Timing
    total_load_time_seconds: float = 0.0
    average_load_time_seconds: float = 0.0

    # Errors
    load_errors: int = 0
    eviction_errors: int = 0

    @property
    def hit_rate(self) -> float:
        """نسبة الإصابة"""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس"""
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": self.hit_rate,
            "models_loaded": self.models_loaded,
            "models_evicted": self.models_evicted,
            "models_preloaded": self.models_preloaded,
            "total_memory_used_mb": self.total_memory_used_mb,
            "total_gpu_memory_used_mb": self.total_gpu_memory_used_mb,
            "peak_memory_used_mb": self.peak_memory_used_mb,
            "total_load_time_seconds": self.total_load_time_seconds,
            "average_load_time_seconds": self.average_load_time_seconds,
            "load_errors": self.load_errors,
            "eviction_errors": self.eviction_errors,
        }


@dataclass
class ModelCacheConfig:
    """
    إعدادات ذاكرة التخزين المؤقت
    Cache configuration
    """

    # Memory limits
    max_memory_mb: int = 16384  # 16 GB
    max_gpu_memory_mb: int = 8192  # 8 GB
    max_models: int = 10  # أقصى عدد من النماذج

    # Eviction
    eviction_policy: str = "lru"  # lru, lfu, fifo
    eviction_threshold: float = 0.9  # 90% من الحد الأقصى

    # Preloading
    preload_config: Optional[PreloadConfig] = None

    # Timeouts
    load_timeout_seconds: int = 300
    unload_timeout_seconds: int = 60

    # Paths
    cache_dir: str = ".model_cache"
    download_dir: str = ".model_downloads"

    # Options
    enable_memory_mapping: bool = True
    enable_sharding: bool = False
    cleanup_on_exit: bool = False

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس"""
        return {
            "max_memory_mb": self.max_memory_mb,
            "max_gpu_memory_mb": self.max_gpu_memory_mb,
            "max_models": self.max_models,
            "eviction_policy": self.eviction_policy,
            "eviction_threshold": self.eviction_threshold,
            "preload_config": self.preload_config.to_dict() if self.preload_config else None,
            "load_timeout_seconds": self.load_timeout_seconds,
            "cache_dir": self.cache_dir,
            "enable_memory_mapping": self.enable_memory_mapping,
        }


class ModelCache:
    """
    ذاكرة تخزين مؤقت ذكية للنماذج
    Intelligent Model Cache

    توفر إدارة ذكية للنماذج مع سياسة LRU
    وتحميل مسبق وإدارة الذاكرة.

    Provides intelligent model management with LRU policy,
    preloading, and memory management.
    """

    def __init__(
        self,
        loader: ModelLoader,
        config: Optional[ModelCacheConfig] = None,
    ):
        """
        تهيئة ذاكرة التخزين المؤقت

        Args:
            loader: محمل النماذج
            config: إعدادات الذاكرة المؤقتة
        """
        self.loader = loader
        self.config = config or ModelCacheConfig()

        # LRU ordered dict for models
        self._cache: OrderedDict[str, ModelInfo] = OrderedDict()
        self._lock = Lock()

        # Loading state
        self._loading: dict[str, asyncio.Event] = {}
        self._loading_tasks: dict[str, asyncio.Task] = {}

        # Statistics
        self._stats = CacheStats()

        # Callbacks
        self._on_load: list[Callable[[ModelInfo], None]] = []
        self._on_evict: list[Callable[[ModelInfo], None]] = []

        # State
        self._running = False

    # =========================================================================
    # Lifecycle / دورة الحياة
    # =========================================================================

    async def start(self) -> None:
        """بدء الذاكرة المؤقتة"""
        self._running = True

        # Initialize loader
        await self.loader.initialize()

        # Preload models if configured
        if self.config.preload_config and self.config.preload_config.preload_on_startup:
            await self._preload_models()

        logger.info("ModelCache started")

    async def stop(self) -> None:
        """إيقاف الذاكرة المؤقتة"""
        self._running = False

        # Cancel loading tasks
        for task in self._loading_tasks.values():
            task.cancel()

        # Unload all models if configured
        if self.config.cleanup_on_exit:
            await self.clear()

        await self.loader.cleanup()
        logger.info("ModelCache stopped")

    # =========================================================================
    # Cache Operations / عمليات الذاكرة المؤقتة
    # =========================================================================

    async def get(
        self,
        model_id: str,
        load_if_missing: bool = True,
    ) -> Optional[ModelInfo]:
        """
        الحصول على نموذج من الذاكرة المؤقتة
        Get model from cache

        Args:
            model_id: معرف النموذج
            load_if_missing: تحميل إذا غير موجود

        Returns:
            معلومات النموذج أو None
        """
        with self._lock:
            if model_id in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(model_id)
                model_info = self._cache[model_id]

                if model_info.is_loaded:
                    self._stats.cache_hits += 1
                    model_info.update_usage()
                    return model_info

        # Not in cache or not loaded
        self._stats.cache_misses += 1

        if load_if_missing:
            return await self.load(model_id)

        return None

    async def load(
        self,
        model_id: str,
        spec: Optional[ModelSpec] = None,
        priority: bool = False,
    ) -> Optional[ModelInfo]:
        """
        تحميل نموذج
        Load a model

        Args:
            model_id: معرف النموذج
            spec: مواصفات النموذج (اختياري)
            priority: أولوية عالية

        Returns:
            معلومات النموذج أو None
        """
        # Check if already loading
        if model_id in self._loading:
            event = self._loading[model_id]
            await event.wait()
            return self._cache.get(model_id)

        # Check if already loaded
        with self._lock:
            if model_id in self._cache:
                model_info = self._cache[model_id]
                if model_info.is_loaded:
                    return model_info

        # Start loading
        event = asyncio.Event()
        self._loading[model_id] = event

        try:
            # Ensure space in cache
            await self._ensure_capacity(model_id, spec)

            # Load the model
            start_time = datetime.now(timezone.utc)

            model_info = await asyncio.wait_for(
                self.loader.load(model_id, spec),
                timeout=self.config.load_timeout_seconds,
            )

            if model_info:
                load_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                model_info.load_time_seconds = load_time
                model_info.loaded_at = datetime.now(timezone.utc)
                model_info.state = ModelState.LOADED

                # Add to cache
                with self._lock:
                    self._cache[model_id] = model_info
                    if priority:
                        self._cache.move_to_end(model_id)

                # Update stats
                self._stats.models_loaded += 1
                self._stats.total_load_time_seconds += load_time
                self._stats.average_load_time_seconds = self._stats.total_load_time_seconds / self._stats.models_loaded
                self._update_memory_stats()

                # Callbacks
                for callback in self._on_load:
                    try:
                        callback(model_info)
                    except Exception as e:
                        logger.error(f"Load callback error: {e}")

                logger.info(f"Loaded model {model_id} in {load_time:.2f}s")
                return model_info

        except asyncio.TimeoutError:
            logger.error(f"Timeout loading model {model_id}")
            self._stats.load_errors += 1
        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            self._stats.load_errors += 1
        finally:
            event.set()
            self._loading.pop(model_id, None)

        return None

    async def unload(self, model_id: str) -> bool:
        """
        إفراغ نموذج من الذاكرة
        Unload a model

        Args:
            model_id: معرف النموذج

        Returns:
            True إذا تم الإفراغ بنجاح
        """
        with self._lock:
            if model_id not in self._cache:
                return False

            model_info = self._cache[model_id]

        if not model_info.is_loaded:
            return False

        try:
            model_info.state = ModelState.UNLOADING

            await asyncio.wait_for(
                self.loader.unload(model_info),
                timeout=self.config.unload_timeout_seconds,
            )

            with self._lock:
                if model_id in self._cache:
                    del self._cache[model_id]

            # Callbacks
            for callback in self._on_evict:
                try:
                    callback(model_info)
                except Exception as e:
                    logger.error(f"Evict callback error: {e}")

            self._stats.models_evicted += 1
            self._update_memory_stats()

            logger.info(f"Unloaded model {model_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to unload model {model_id}: {e}")
            self._stats.eviction_errors += 1
            return False

    async def clear(self) -> int:
        """
        مسح جميع النماذج
        Clear all models

        Returns:
            عدد النماذج التي تم إفراغها
        """
        cleared = 0
        model_ids = list(self._cache.keys())

        for model_id in model_ids:
            if await self.unload(model_id):
                cleared += 1

        logger.info(f"Cleared {cleared} models from cache")
        return cleared

    # =========================================================================
    # Capacity Management / إدارة السعة
    # =========================================================================

    async def _ensure_capacity(
        self,
        model_id: str,
        spec: Optional[ModelSpec] = None,
    ) -> None:
        """ضمان وجود سعة كافية"""
        # Estimate memory needed
        memory_needed = spec.memory_required_mb if spec else 4096
        gpu_memory_needed = spec.gpu_memory_required_mb if spec else 0

        # Check if eviction needed
        while self._should_evict(memory_needed, gpu_memory_needed):
            evicted = await self._evict_one()
            if not evicted:
                break

    def _should_evict(
        self,
        additional_memory: int = 0,
        additional_gpu_memory: int = 0,
    ) -> bool:
        """التحقق من الحاجة للإخلاء"""
        # Check model count
        if len(self._cache) >= self.config.max_models:
            return True

        # Check memory
        current_memory = self._stats.total_memory_used_mb + additional_memory
        threshold = self.config.max_memory_mb * self.config.eviction_threshold
        if current_memory >= threshold:
            return True

        # Check GPU memory
        current_gpu = self._stats.total_gpu_memory_used_mb + additional_gpu_memory
        gpu_threshold = self.config.max_gpu_memory_mb * self.config.eviction_threshold
        if current_gpu >= gpu_threshold:
            return True

        return False

    async def _evict_one(self) -> bool:
        """إخلاء نموذج واحد (LRU)"""
        with self._lock:
            if not self._cache:
                return False

            # Get least recently used (first in ordered dict)
            model_id = next(iter(self._cache))

        return await self.unload(model_id)

    def _update_memory_stats(self) -> None:
        """تحديث إحصائيات الذاكرة"""
        total_memory = 0
        total_gpu = 0

        for model_info in self._cache.values():
            if model_info.is_loaded:
                total_memory += model_info.memory_used_mb
                total_gpu += model_info.gpu_memory_used_mb

        self._stats.total_memory_used_mb = total_memory
        self._stats.total_gpu_memory_used_mb = total_gpu

        if total_memory > self._stats.peak_memory_used_mb:
            self._stats.peak_memory_used_mb = total_memory

    # =========================================================================
    # Preloading / التحميل المسبق
    # =========================================================================

    async def _preload_models(self) -> None:
        """تحميل النماذج مسبقاً"""
        preload_config = self.config.preload_config
        if not preload_config:
            return

        models = preload_config.models

        # Sort by priority
        if preload_config.priority_order:
            priority_map = {mid: i for i, mid in enumerate(preload_config.priority_order)}
            models = sorted(
                models,
                key=lambda m: priority_map.get(m.model_id, len(priority_map)),
            )

        # Preload with concurrency limit
        semaphore = asyncio.Semaphore(preload_config.parallel_preloads)

        async def preload_one(spec: ModelSpec) -> None:
            async with semaphore:
                try:
                    await asyncio.wait_for(
                        self.load(spec.model_id, spec),
                        timeout=preload_config.preload_timeout_seconds,
                    )
                    self._stats.models_preloaded += 1
                except Exception as e:
                    logger.error(f"Failed to preload {spec.model_id}: {e}")

        # Run preloads
        await asyncio.gather(
            *[preload_one(spec) for spec in models],
            return_exceptions=True,
        )

        logger.info(f"Preloaded {self._stats.models_preloaded} models")

    async def preload(
        self,
        model_ids: list[str],
        specs: Optional[dict[str, ModelSpec]] = None,
    ) -> int:
        """
        تحميل نماذج محددة مسبقاً
        Preload specific models

        Args:
            model_ids: قائمة معرفات النماذج
            specs: مواصفات النماذج (اختياري)

        Returns:
            عدد النماذج المحملة
        """
        loaded = 0

        for model_id in model_ids:
            spec = specs.get(model_id) if specs else None
            try:
                result = await self.load(model_id, spec)
                if result:
                    loaded += 1
            except Exception as e:
                logger.error(f"Preload failed for {model_id}: {e}")

        return loaded

    # =========================================================================
    # Query / الاستعلام
    # =========================================================================

    def list_models(
        self,
        state: Optional[ModelState] = None,
    ) -> list[ModelInfo]:
        """قائمة النماذج"""
        with self._lock:
            models = list(self._cache.values())

        if state:
            models = [m for m in models if m.state == state]

        return models

    def get_loaded_models(self) -> list[ModelInfo]:
        """النماذج المحملة"""
        return self.list_models(state=ModelState.LOADED)

    def is_loaded(self, model_id: str) -> bool:
        """هل النموذج محمل؟"""
        with self._lock:
            if model_id not in self._cache:
                return False
            return self._cache[model_id].is_loaded

    def get_stats(self) -> CacheStats:
        """الحصول على الإحصائيات"""
        return self._stats

    def get_status(self) -> dict[str, Any]:
        """الحصول على الحالة"""
        return {
            "running": self._running,
            "models_count": len(self._cache),
            "models_loaded": len(self.get_loaded_models()),
            "config": self.config.to_dict(),
            "stats": self._stats.to_dict(),
            "models": [m.to_dict() for m in self._cache.values()],
        }

    # =========================================================================
    # Callbacks / ردود الاتصال
    # =========================================================================

    def on_load(self, callback: Callable[[ModelInfo], None]) -> None:
        """تسجيل callback عند التحميل"""
        self._on_load.append(callback)

    def on_evict(self, callback: Callable[[ModelInfo], None]) -> None:
        """تسجيل callback عند الإخلاء"""
        self._on_evict.append(callback)
