"""
Gateway Plugins - إضافات البوابة
=================================

Extensible plugin system for the API Gateway.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gateway import APIGateway, GatewayRequest, GatewayResponse

logger = logging.getLogger(__name__)


class PluginHook(str, Enum):
    """Available plugin hooks."""
    # Lifecycle hooks
    ON_LOAD = "on_load"
    ON_UNLOAD = "on_unload"
    ON_START = "on_start"
    ON_STOP = "on_stop"

    # Request hooks
    PRE_REQUEST = "pre_request"
    POST_REQUEST = "post_request"
    ON_REQUEST_ERROR = "on_request_error"

    # Response hooks
    PRE_RESPONSE = "pre_response"
    POST_RESPONSE = "post_response"

    # Route hooks
    ON_ROUTE_MATCH = "on_route_match"
    ON_ROUTE_NOT_FOUND = "on_route_not_found"

    # Backend hooks
    PRE_PROXY = "pre_proxy"
    POST_PROXY = "post_proxy"
    ON_PROXY_ERROR = "on_proxy_error"

    # Custom hooks
    CUSTOM = "custom"


@dataclass
class PluginConfig:
    """Plugin configuration."""
    name: str
    enabled: bool = True
    priority: int = 0
    settings: Dict[str, Any] = field(default_factory=dict)

    # Dependencies
    depends_on: List[str] = field(default_factory=list)

    # Hooks to enable
    hooks: List[PluginHook] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "priority": self.priority,
            "settings": self.settings,
            "depends_on": self.depends_on,
            "hooks": [h.value for h in self.hooks],
        }


@dataclass
class PluginContext:
    """Context passed to plugin hooks."""
    gateway: APIGateway
    request: Optional[GatewayRequest] = None
    response: Optional[GatewayResponse] = None
    route_match: Optional[Any] = None
    error: Optional[Exception] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """Set context data."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get context data."""
        return self.data.get(key, default)


class Plugin(ABC):
    """
    Base Plugin class.

    All gateway plugins should inherit from this class.

    Example:
        class MyPlugin(Plugin):
            @property
            def name(self) -> str:
                return "my-plugin"

            async def on_load(self, gateway: APIGateway) -> None:
                logger.info("Plugin loaded!")

            async def pre_request(self, ctx: PluginContext) -> Optional[GatewayResponse]:
                # Add custom header
                ctx.request.set_header("x-plugin", "active")
                return None
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name."""
        pass

    @property
    def version(self) -> str:
        """Plugin version."""
        return "1.0.0"

    @property
    def description(self) -> str:
        """Plugin description."""
        return ""

    @property
    def hooks(self) -> List[PluginHook]:
        """List of hooks this plugin implements."""
        implemented = []
        for hook in PluginHook:
            method_name = hook.value
            if hasattr(self, method_name) and callable(getattr(self, method_name)):
                implemented.append(hook)
        return implemented

    # Lifecycle hooks

    async def on_load(self, gateway: APIGateway) -> None:
        """Called when plugin is loaded."""
        pass

    async def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        pass

    async def on_start(self) -> None:
        """Called when gateway starts."""
        pass

    async def on_stop(self) -> None:
        """Called when gateway stops."""
        pass

    # Request hooks

    async def pre_request(self, ctx: PluginContext) -> Optional[GatewayResponse]:
        """
        Called before request is processed.

        Return a GatewayResponse to short-circuit the request.
        """
        pass

    async def post_request(self, ctx: PluginContext) -> None:
        """Called after request is processed."""
        pass

    async def on_request_error(self, ctx: PluginContext) -> Optional[GatewayResponse]:
        """Called when request processing fails."""
        pass

    # Response hooks

    async def pre_response(self, ctx: PluginContext) -> Optional[GatewayResponse]:
        """
        Called before response is sent.

        Return a modified response if needed.
        """
        pass

    async def post_response(self, ctx: PluginContext) -> None:
        """Called after response is sent."""
        pass

    # Route hooks

    async def on_route_match(self, ctx: PluginContext) -> None:
        """Called when a route is matched."""
        pass

    async def on_route_not_found(self, ctx: PluginContext) -> Optional[GatewayResponse]:
        """Called when no route is found."""
        pass

    # Proxy hooks

    async def pre_proxy(self, ctx: PluginContext) -> Optional[GatewayResponse]:
        """Called before proxying to upstream."""
        pass

    async def post_proxy(self, ctx: PluginContext) -> None:
        """Called after proxying to upstream."""
        pass

    async def on_proxy_error(self, ctx: PluginContext) -> Optional[GatewayResponse]:
        """Called when proxy fails."""
        pass


class PluginManager:
    """
    Plugin Manager - مدير الإضافات.

    Manages plugin lifecycle and hook execution.

    Example:
        manager = PluginManager(gateway)

        # Load plugins
        manager.load_plugin(MyPlugin())
        manager.load_from_directory("./plugins")

        # Execute hooks
        response = await manager.execute_hook(PluginHook.PRE_REQUEST, ctx)
    """

    def __init__(self, gateway: APIGateway):
        self.gateway = gateway
        self._plugins: Dict[str, Plugin] = {}
        self._plugin_configs: Dict[str, PluginConfig] = {}
        self._hook_handlers: Dict[PluginHook, List[Plugin]] = {
            hook: [] for hook in PluginHook
        }

    def load_plugin(
        self,
        plugin: Plugin,
        config: Optional[PluginConfig] = None,
    ) -> bool:
        """Load a plugin."""
        name = plugin.name

        if name in self._plugins:
            logger.warning(f"Plugin {name} already loaded")
            return False

        # Check dependencies
        config = config or PluginConfig(name=name)
        for dep in config.depends_on:
            if dep not in self._plugins:
                logger.error(f"Plugin {name} depends on {dep} which is not loaded")
                return False

        try:
            # Load plugin
            asyncio.get_event_loop().run_until_complete(
                plugin.on_load(self.gateway)
            )

            self._plugins[name] = plugin
            self._plugin_configs[name] = config

            # Register hooks
            for hook in plugin.hooks:
                self._hook_handlers[hook].append(plugin)

            # Sort by priority
            for hook in PluginHook:
                self._hook_handlers[hook].sort(
                    key=lambda p: self._plugin_configs.get(p.name, PluginConfig(name=p.name)).priority,
                    reverse=True
                )

            logger.info(f"Loaded plugin: {name} v{plugin.version}")
            return True

        except Exception as e:
            logger.error(f"Failed to load plugin {name}: {e}")
            return False

    def unload_plugin(self, name: str) -> bool:
        """Unload a plugin."""
        if name not in self._plugins:
            return False

        plugin = self._plugins[name]

        try:
            asyncio.get_event_loop().run_until_complete(
                plugin.on_unload()
            )
        except Exception as e:
            logger.error(f"Error unloading plugin {name}: {e}")

        # Remove from hooks
        for hook in PluginHook:
            self._hook_handlers[hook] = [
                p for p in self._hook_handlers[hook]
                if p.name != name
            ]

        del self._plugins[name]
        del self._plugin_configs[name]

        logger.info(f"Unloaded plugin: {name}")
        return True

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all loaded plugins."""
        return [
            {
                "name": plugin.name,
                "version": plugin.version,
                "description": plugin.description,
                "hooks": [h.value for h in plugin.hooks],
                "config": self._plugin_configs.get(plugin.name, PluginConfig(name=plugin.name)).to_dict(),
            }
            for plugin in self._plugins.values()
        ]

    async def execute_hook(
        self,
        hook: PluginHook,
        ctx: PluginContext,
    ) -> Optional[GatewayResponse]:
        """
        Execute a hook across all plugins.

        Returns a response if any plugin short-circuits the request.
        """
        for plugin in self._hook_handlers[hook]:
            config = self._plugin_configs.get(plugin.name)
            if config and not config.enabled:
                continue

            try:
                method = getattr(plugin, hook.value, None)
                if method and callable(method):
                    result = await method(ctx)
                    if isinstance(result, GatewayResponse):
                        return result

            except Exception as e:
                logger.error(f"Plugin {plugin.name} hook {hook.value} error: {e}")

        return None

    def load_from_directory(self, directory: str) -> int:
        """
        Load plugins from a directory.

        Expects Python files with a `create_plugin()` function.
        """
        loaded = 0
        path = Path(directory)

        if not path.exists():
            logger.warning(f"Plugin directory not found: {directory}")
            return 0

        for file in path.glob("*.py"):
            if file.name.startswith("_"):
                continue

            try:
                spec = importlib.util.spec_from_file_location(
                    file.stem,
                    file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "create_plugin"):
                    plugin = module.create_plugin()
                    if self.load_plugin(plugin):
                        loaded += 1

            except Exception as e:
                logger.error(f"Failed to load plugin from {file}: {e}")

        return loaded

    async def start_all(self) -> None:
        """Start all plugins."""
        for plugin in self._plugins.values():
            try:
                await plugin.on_start()
            except Exception as e:
                logger.error(f"Plugin {plugin.name} start error: {e}")

    async def stop_all(self) -> None:
        """Stop all plugins."""
        for plugin in self._plugins.values():
            try:
                await plugin.on_stop()
            except Exception as e:
                logger.error(f"Plugin {plugin.name} stop error: {e}")


# Built-in Plugins

class LoggingPlugin(Plugin):
    """Built-in logging plugin."""

    @property
    def name(self) -> str:
        return "logging"

    @property
    def description(self) -> str:
        return "Request/Response logging"

    async def pre_request(self, ctx: PluginContext) -> Optional[GatewayResponse]:
        logger.info(f"Request: {ctx.request.method} {ctx.request.path}")
        return None

    async def post_response(self, ctx: PluginContext) -> None:
        logger.info(
            f"Response: {ctx.request.method} {ctx.request.path} "
            f"-> {ctx.response.status_code}"
        )


class MetricsPlugin(Plugin):
    """Built-in metrics collection plugin."""

    def __init__(self):
        self._metrics = {
            "requests_total": 0,
            "requests_by_path": {},
            "requests_by_status": {},
            "latency_sum_ms": 0.0,
        }
        self._request_times: Dict[str, float] = {}

    @property
    def name(self) -> str:
        return "metrics"

    @property
    def description(self) -> str:
        return "Request metrics collection"

    async def pre_request(self, ctx: PluginContext) -> Optional[GatewayResponse]:
        import time
        self._request_times[ctx.request.request_id] = time.time()
        return None

    async def post_response(self, ctx: PluginContext) -> None:
        import time

        self._metrics["requests_total"] += 1

        path = ctx.request.path
        self._metrics["requests_by_path"][path] = \
            self._metrics["requests_by_path"].get(path, 0) + 1

        status = str(ctx.response.status_code)
        self._metrics["requests_by_status"][status] = \
            self._metrics["requests_by_status"].get(status, 0) + 1

        start_time = self._request_times.pop(ctx.request.request_id, None)
        if start_time:
            latency = (time.time() - start_time) * 1000
            self._metrics["latency_sum_ms"] += latency

    def get_metrics(self) -> Dict[str, Any]:
        """Get collected metrics."""
        return {
            **self._metrics,
            "avg_latency_ms": (
                self._metrics["latency_sum_ms"] / self._metrics["requests_total"]
                if self._metrics["requests_total"] > 0 else 0
            ),
        }


class HealthCheckPlugin(Plugin):
    """Built-in health check plugin."""

    def __init__(self, path: str = "/health"):
        self.path = path

    @property
    def name(self) -> str:
        return "health-check"

    @property
    def description(self) -> str:
        return "Health check endpoint"

    async def pre_request(self, ctx: PluginContext) -> Optional[GatewayResponse]:
        if ctx.request.path == self.path:
            return GatewayResponse.ok({
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        return None
