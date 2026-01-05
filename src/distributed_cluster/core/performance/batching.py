"""
Batching Utilities - أدوات التجميع
==================================

Batching Utilities
------------------

This module provides utilities for batching operations.

يوفر هذا الملف أدوات لتجميع العمليات.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    Generic,
    Iterator,
    Optional,
    TypeVar,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class BatchConfig:
    """
    إعدادات التجميع
    Batch configuration
    """

    # Size
    max_batch_size: int = 100
    min_batch_size: int = 1

    # Timing
    max_wait_seconds: float = 0.1
    batch_timeout_seconds: float = 30.0

    # Options
    flush_on_max: bool = True
    preserve_order: bool = True


class BatchProcessor(Generic[T, R]):
    """
    معالج دفعات
    Batch Processor

    يجمع العناصر ويعالجها بشكل دفعات.
    Collects items and processes them in batches.
    """

    def __init__(
        self,
        processor: Callable[[list[T]], Awaitable[list[R]]],
        config: Optional[BatchConfig] = None,
    ):
        """
        تهيئة معالج الدفعات

        Args:
            processor: دالة معالجة الدفعة
            config: إعدادات التجميع
        """
        self.processor = processor
        self.config = config or BatchConfig()

        # Internal state
        self._batch: list[tuple[T, asyncio.Future]] = []
        self._lock = asyncio.Lock()
        self._timer_task: Optional[asyncio.Task] = None
        self._running = False

        # Statistics
        self._stats = {
            "items_processed": 0,
            "batches_processed": 0,
            "total_wait_time": 0.0,
            "average_batch_size": 0.0,
        }

    async def start(self) -> None:
        """بدء المعالج"""
        self._running = True
        logger.info("BatchProcessor started")

    async def stop(self) -> None:
        """إيقاف المعالج"""
        self._running = False

        # Process remaining items
        if self._batch:
            await self._flush()

        if self._timer_task:
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass

        logger.info("BatchProcessor stopped")

    async def submit(self, item: T) -> R:
        """
        تقديم عنصر للمعالجة
        Submit item for processing

        Args:
            item: العنصر للمعالجة

        Returns:
            نتيجة المعالجة
        """
        future: asyncio.Future[R] = asyncio.get_event_loop().create_future()

        async with self._lock:
            self._batch.append((item, future))

            # Start timer if this is the first item
            if len(self._batch) == 1:
                self._start_timer()

            # Flush if batch is full
            if len(self._batch) >= self.config.max_batch_size:
                if self.config.flush_on_max:
                    await self._flush()

        return await future

    async def submit_many(self, items: list[T]) -> list[R]:
        """
        تقديم عناصر متعددة
        Submit multiple items
        """
        futures = await asyncio.gather(*[self.submit(item) for item in items])
        return list(futures)

    async def _flush(self) -> None:
        """معالجة الدفعة الحالية"""
        if not self._batch:
            return

        # Cancel timer
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None

        # Get batch
        batch = self._batch
        self._batch = []

        items = [item for item, _ in batch]
        futures = [future for _, future in batch]

        try:
            # Process batch
            start_time = time.time()

            results = await asyncio.wait_for(
                self.processor(items),
                timeout=self.config.batch_timeout_seconds,
            )

            process_time = time.time() - start_time

            # Update statistics
            self._stats["items_processed"] += len(items)
            self._stats["batches_processed"] += 1
            self._stats["total_wait_time"] += process_time
            self._stats["average_batch_size"] = self._stats["items_processed"] / self._stats["batches_processed"]

            # Set results
            for future, result in zip(futures, results):
                if not future.done():
                    future.set_result(result)

        except Exception as e:
            # Set error for all futures
            for future in futures:
                if not future.done():
                    future.set_exception(e)

            logger.error(f"Batch processing failed: {e}")

    def _start_timer(self) -> None:
        """بدء مؤقت الانتظار"""
        if self._timer_task and not self._timer_task.done():
            return

        async def timer():
            await asyncio.sleep(self.config.max_wait_seconds)
            async with self._lock:
                if self._batch:
                    await self._flush()

        self._timer_task = asyncio.create_task(timer())

    def get_stats(self) -> dict[str, Any]:
        """الحصول على الإحصائيات"""
        return {
            **self._stats,
            "pending_items": len(self._batch),
        }


# =============================================================================
# Utility Functions / دوال مساعدة
# =============================================================================


def batch_items(
    items: list[T],
    batch_size: int,
) -> Iterator[list[T]]:
    """
    تقسيم قائمة إلى دفعات
    Split list into batches

    Args:
        items: القائمة
        batch_size: حجم الدفعة

    Yields:
        دفعات من العناصر
    """
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


async def process_in_batches(
    items: list[T],
    processor: Callable[[list[T]], Awaitable[list[R]]],
    batch_size: int = 100,
    max_concurrent: int = 5,
) -> list[R]:
    """
    معالجة عناصر في دفعات متزامنة
    Process items in concurrent batches

    Args:
        items: العناصر
        processor: دالة المعالجة
        batch_size: حجم الدفعة
        max_concurrent: أقصى تزامن

    Returns:
        النتائج
    """
    batches = list(batch_items(items, batch_size))
    results: list[R] = []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_batch(batch: list[T]) -> list[R]:
        async with semaphore:
            return await processor(batch)

    batch_results = await asyncio.gather(*[process_batch(batch) for batch in batches])

    for batch_result in batch_results:
        results.extend(batch_result)

    return results


async def map_concurrent(
    items: list[T],
    func: Callable[[T], Awaitable[R]],
    max_concurrent: int = 10,
) -> list[R]:
    """
    تطبيق دالة على عناصر بشكل متزامن
    Apply function to items concurrently

    Args:
        items: العناصر
        func: الدالة
        max_concurrent: أقصى تزامن

    Returns:
        النتائج
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_item(item: T) -> R:
        async with semaphore:
            return await func(item)

    return await asyncio.gather(*[process_item(item) for item in items])
