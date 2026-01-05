"""
Hook System - نظام الخطافات
============================

Event hook system for extending cluster functionality.
نظام خطافات الأحداث لتوسيع وظائف الكلاستر.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class HookType(str, Enum):
    """أنواع الخطافات المدعومة."""

    # Job lifecycle hooks
    JOB_SUBMITTED = "job.submitted"
    JOB_SCHEDULED = "job.scheduled"
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"
    JOB_TIMEOUT = "job.timeout"
    JOB_RETRYING = "job.retrying"

    # Worker lifecycle hooks
    WORKER_REGISTERED = "worker.registered"
    WORKER_ONLINE = "worker.online"
    WORKER_OFFLINE = "worker.offline"
    WORKER_REMOVED = "worker.removed"
    WORKER_DRAINING = "worker.draining"
    WORKER_HEARTBEAT = "worker.heartbeat"

    # Scheduler hooks
    SCHEDULER_TICK = "scheduler.tick"
    SCHEDULER_NO_RESOURCES = "scheduler.no_resources"
    SCHEDULER_DECISION = "scheduler.decision"

    # System hooks
    MASTER_STARTED = "master.started"
    MASTER_STOPPED = "master.stopped"
    CLUSTER_HEALTH_CHECK = "cluster.health_check"

    # Custom hooks
    CUSTOM = "custom"


@dataclass
class HookContext:
    """سياق الخطاف."""

    hook_type: HookType
    timestamp: datetime
    data: Dict[str, Any]
    source: str = "system"
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# Type alias for hook handlers
HookHandler = Callable[[HookContext], Any]
AsyncHookHandler = Callable[[HookContext], "asyncio.Future[Any]"]


@dataclass
class RegisteredHook:
    """خطاف مسجل."""

    hook_type: HookType
    handler: Union[HookHandler, AsyncHookHandler]
    name: str
    priority: int = 100
    is_async: bool = False
    enabled: bool = True
    run_async: bool = False  # Run in background without waiting


class HookManager:
    """
    Hook Manager - مدير الخطافات.

    Manages registration and execution of event hooks.

    Example:
        manager = HookManager()

        # Register a hook
        @manager.on(HookType.JOB_COMPLETED)
        async def on_job_completed(ctx: HookContext):
            print(f"Job {ctx.data['job_id']} completed!")

        # Or register manually
        manager.register(
            HookType.JOB_FAILED,
            send_alert,
            name="alert-hook",
            priority=10
        )

        # Trigger hooks
        await manager.trigger(HookType.JOB_COMPLETED, {"job_id": "123"})
    """

    def __init__(self):
        self._hooks: Dict[HookType, List[RegisteredHook]] = {}
        self._global_hooks: List[RegisteredHook] = []  # Called for all events

    def register(
        self,
        hook_type: HookType,
        handler: Union[HookHandler, AsyncHookHandler],
        name: str = None,
        priority: int = 100,
        run_async: bool = False,
    ) -> RegisteredHook:
        """
        Register a hook handler.
        تسجيل معالج خطاف.

        Args:
            hook_type: Type of hook to register for
            handler: Handler function
            name: Optional name for the hook
            priority: Execution priority (lower = earlier)
            run_async: Run in background without waiting

        Returns:
            RegisteredHook instance
        """
        is_async = asyncio.iscoroutinefunction(handler)
        name = name or handler.__name__

        hook = RegisteredHook(
            hook_type=hook_type,
            handler=handler,
            name=name,
            priority=priority,
            is_async=is_async,
            run_async=run_async,
        )

        if hook_type not in self._hooks:
            self._hooks[hook_type] = []

        self._hooks[hook_type].append(hook)
        self._hooks[hook_type].sort(key=lambda h: h.priority)

        logger.debug(f"Registered hook: {name} for {hook_type.value}")
        return hook

    def register_global(
        self,
        handler: Union[HookHandler, AsyncHookHandler],
        name: str = None,
        priority: int = 100,
        run_async: bool = False,
    ) -> RegisteredHook:
        """
        Register a global hook that runs for all events.
        تسجيل خطاف عام يعمل لجميع الأحداث.
        """
        is_async = asyncio.iscoroutinefunction(handler)
        name = name or handler.__name__

        hook = RegisteredHook(
            hook_type=HookType.CUSTOM,
            handler=handler,
            name=name,
            priority=priority,
            is_async=is_async,
            run_async=run_async,
        )

        self._global_hooks.append(hook)
        self._global_hooks.sort(key=lambda h: h.priority)

        logger.debug(f"Registered global hook: {name}")
        return hook

    def unregister(self, name: str) -> bool:
        """
        Unregister a hook by name.
        إلغاء تسجيل خطاف بالاسم.
        """
        found = False

        # Check type-specific hooks
        for hook_type, hooks in self._hooks.items():
            for hook in hooks[:]:
                if hook.name == name:
                    hooks.remove(hook)
                    found = True

        # Check global hooks
        for hook in self._global_hooks[:]:
            if hook.name == name:
                self._global_hooks.remove(hook)
                found = True

        if found:
            logger.debug(f"Unregistered hook: {name}")
        return found

    def on(
        self,
        hook_type: HookType,
        priority: int = 100,
        run_async: bool = False,
    ) -> Callable:
        """
        Decorator for registering hooks.
        مزخرف لتسجيل الخطافات.

        Example:
            @manager.on(HookType.JOB_COMPLETED)
            async def handle_completion(ctx):
                pass
        """

        def decorator(func):
            self.register(
                hook_type=hook_type,
                handler=func,
                name=func.__name__,
                priority=priority,
                run_async=run_async,
            )
            return func

        return decorator

    async def trigger(
        self,
        hook_type: HookType,
        data: Dict[str, Any] = None,
        source: str = "system",
        metadata: Dict[str, Any] = None,
    ) -> List[Any]:
        """
        Trigger all handlers for a hook type.
        تشغيل جميع المعالجات لنوع خطاف.

        Args:
            hook_type: Type of hook to trigger
            data: Data to pass to handlers
            source: Source of the event
            metadata: Additional metadata

        Returns:
            List of handler results
        """
        context = HookContext(
            hook_type=hook_type,
            timestamp=datetime.now(timezone.utc),
            data=data or {},
            source=source,
            metadata=metadata or {},
        )

        results = []
        background_tasks = []

        # Get all applicable hooks
        hooks = self._global_hooks + self._hooks.get(hook_type, [])
        hooks = [h for h in hooks if h.enabled]
        hooks.sort(key=lambda h: h.priority)

        for hook in hooks:
            try:
                if hook.run_async:
                    # Run in background
                    if hook.is_async:
                        task = asyncio.create_task(hook.handler(context))
                    else:
                        task = asyncio.get_running_loop().run_in_executor(None, hook.handler, context)
                    background_tasks.append(task)
                else:
                    # Run and wait
                    if hook.is_async:
                        result = await hook.handler(context)
                    else:
                        result = hook.handler(context)
                    results.append(result)

            except Exception as e:
                logger.error(f"Hook {hook.name} failed: {e}")

        return results

    def trigger_sync(
        self,
        hook_type: HookType,
        data: Dict[str, Any] = None,
        source: str = "system",
    ) -> List[Any]:
        """
        Trigger hooks synchronously (sync handlers only).
        تشغيل الخطافات بشكل متزامن.
        """
        context = HookContext(
            hook_type=hook_type,
            timestamp=datetime.now(timezone.utc),
            data=data or {},
            source=source,
        )

        results = []
        hooks = self._global_hooks + self._hooks.get(hook_type, [])
        hooks = [h for h in hooks if h.enabled and not h.is_async]
        hooks.sort(key=lambda h: h.priority)

        for hook in hooks:
            try:
                result = hook.handler(context)
                results.append(result)
            except Exception as e:
                logger.error(f"Hook {hook.name} failed: {e}")

        return results

    def enable_hook(self, name: str) -> bool:
        """Enable a hook by name."""
        return self._set_hook_enabled(name, True)

    def disable_hook(self, name: str) -> bool:
        """Disable a hook by name."""
        return self._set_hook_enabled(name, False)

    def _set_hook_enabled(self, name: str, enabled: bool) -> bool:
        """Set hook enabled state."""
        for hooks in self._hooks.values():
            for hook in hooks:
                if hook.name == name:
                    hook.enabled = enabled
                    return True

        for hook in self._global_hooks:
            if hook.name == name:
                hook.enabled = enabled
                return True

        return False

    def get_hooks(self, hook_type: HookType = None) -> List[Dict[str, Any]]:
        """
        Get information about registered hooks.
        الحصول على معلومات الخطافات المسجلة.
        """
        hooks = []

        if hook_type:
            registered = self._hooks.get(hook_type, [])
        else:
            registered = []
            for h in self._hooks.values():
                registered.extend(h)
            registered.extend(self._global_hooks)

        for hook in registered:
            hooks.append(
                {
                    "name": hook.name,
                    "type": hook.hook_type.value,
                    "priority": hook.priority,
                    "is_async": hook.is_async,
                    "run_async": hook.run_async,
                    "enabled": hook.enabled,
                }
            )

        return hooks

    def clear(self, hook_type: HookType = None) -> None:
        """
        Clear all hooks or hooks of a specific type.
        مسح جميع الخطافات.
        """
        if hook_type:
            self._hooks[hook_type] = []
        else:
            self._hooks.clear()
            self._global_hooks.clear()


# Global hook manager instance
_default_manager: Optional[HookManager] = None


def get_hook_manager() -> HookManager:
    """Get the default hook manager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = HookManager()
    return _default_manager


def on(hook_type: HookType, priority: int = 100, run_async: bool = False):
    """
    Convenience decorator for registering with default manager.

    Example:
        @on(HookType.JOB_COMPLETED)
        async def handle_job_completed(ctx):
            pass
    """
    return get_hook_manager().on(hook_type, priority, run_async)
