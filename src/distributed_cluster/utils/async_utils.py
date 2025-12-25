"""
Async Utilities - أدوات غير متزامنة
====================================

Async utility functions for concurrent operations.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from functools import wraps
from typing import Any, Awaitable, Callable, List, Optional, Set, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def run_with_timeout(
    coro: Awaitable[T],
    timeout: float,
    default: Optional[T] = None,
) -> Optional[T]:
    """
    تنفيذ coroutine مع مهلة زمنية
    Run coroutine with timeout

    Args:
        coro: Coroutine to run
        timeout: Timeout in seconds
        default: Default value if timeout

    Returns:
        Result or default if timeout
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.debug(f"Coroutine timed out after {timeout}s")
        return default


async def gather_with_concurrency(
    coroutines: List[Awaitable[T]],
    max_concurrency: int = 10,
    return_exceptions: bool = False,
) -> List[T]:
    """
    تنفيذ coroutines مع تحديد التزامن
    Run coroutines with limited concurrency

    Args:
        coroutines: List of coroutines
        max_concurrency: Maximum concurrent tasks
        return_exceptions: Return exceptions instead of raising

    Returns:
        List of results
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def limited_coro(coro: Awaitable[T]) -> T:
        async with semaphore:
            return await coro

    return await asyncio.gather(
        *[limited_coro(coro) for coro in coroutines],
        return_exceptions=return_exceptions,
    )


def async_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    """
    مزخرف لإعادة المحاولة مع تحكم متقدم
    Advanced retry decorator for async functions

    Args:
        max_retries: Maximum retry attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier
        exceptions: Exception types to retry
        on_retry: Callback on retry (exception, attempt)

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        if on_retry:
                            on_retry(e, attempt + 1)

                        logger.debug(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {current_delay}s: {e}"
                        )

                        await asyncio.sleep(current_delay)
                        current_delay *= backoff

            raise last_exception

        return wrapper

    return decorator


def create_task_with_name(
    coro: Awaitable[T],
    name: str,
    callback: Optional[Callable[[asyncio.Task], None]] = None,
) -> asyncio.Task[T]:
    """
    إنشاء task مع اسم و callback اختياري
    Create task with name and optional callback

    Args:
        coro: Coroutine to run
        name: Task name
        callback: Callback when task completes

    Returns:
        Created task
    """
    task = asyncio.create_task(coro, name=name)

    if callback:
        task.add_done_callback(callback)

    return task


async def cancel_tasks(
    tasks: List[asyncio.Task],
    timeout: float = 5.0,
) -> List[bool]:
    """
    إلغاء مجموعة من المهام
    Cancel a list of tasks

    Args:
        tasks: Tasks to cancel
        timeout: Timeout for cancellation

    Returns:
        List of cancellation results
    """
    results = []

    for task in tasks:
        if not task.done():
            task.cancel()

    # Wait for all tasks to complete cancellation
    if tasks:
        done, pending = await asyncio.wait(
            tasks,
            timeout=timeout,
            return_when=asyncio.ALL_COMPLETED,
        )

        for task in tasks:
            results.append(task.cancelled() or task.done())

    return results


async def wait_for_first(
    coroutines: List[Awaitable[T]],
    timeout: Optional[float] = None,
) -> Optional[T]:
    """
    انتظار أول coroutine ينتهي بنجاح
    Wait for first coroutine to complete successfully

    Args:
        coroutines: List of coroutines
        timeout: Optional timeout

    Returns:
        First successful result or None
    """
    tasks: Set[asyncio.Task] = set()

    for coro in coroutines:
        task = asyncio.create_task(coro)
        tasks.add(task)

    try:
        done, pending = await asyncio.wait(
            tasks,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()

        # Return first successful result
        for task in done:
            if not task.cancelled() and task.exception() is None:
                return task.result()

        return None

    except Exception:
        # Cancel all tasks on error
        for task in tasks:
            task.cancel()
        raise


class AsyncEventEmitter:
    """
    باعث أحداث غير متزامن
    Async event emitter
    """

    def __init__(self):
        self._handlers: dict[str, List[Callable]] = {}

    def on(self, event: str, handler: Callable) -> None:
        """Register event handler"""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

    def off(self, event: str, handler: Callable) -> None:
        """Unregister event handler"""
        if event in self._handlers:
            self._handlers[event] = [h for h in self._handlers[event] if h != handler]

    async def emit(self, event: str, *args, **kwargs) -> None:
        """Emit event to all handlers"""
        if event not in self._handlers:
            return

        for handler in self._handlers[event]:
            try:
                result = handler(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Error in event handler for {event}: {e}")

    def clear(self, event: Optional[str] = None) -> None:
        """Clear handlers for event or all events"""
        if event:
            self._handlers.pop(event, None)
        else:
            self._handlers.clear()


class AsyncPool:
    """
    مجمع للتحكم في التزامن
    Pool for controlling concurrency
    """

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self._semaphore = asyncio.Semaphore(max_workers)
        self._tasks: Set[asyncio.Task] = set()

    async def submit(self, coro: Awaitable[T]) -> T:
        """Submit coroutine to pool"""
        async with self._semaphore:
            task = asyncio.create_task(coro)
            self._tasks.add(task)
            try:
                return await task
            finally:
                self._tasks.discard(task)

    async def map(
        self,
        func: Callable[..., Awaitable[T]],
        items: List[Any],
    ) -> List[T]:
        """Map function over items with concurrency control"""
        return await asyncio.gather(
            *[self.submit(func(item)) for item in items]
        )

    async def shutdown(self, wait: bool = True) -> None:
        """Shutdown pool"""
        if wait and self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        else:
            for task in self._tasks:
                task.cancel()

    @property
    def active_count(self) -> int:
        """Number of active tasks"""
        return len(self._tasks)
