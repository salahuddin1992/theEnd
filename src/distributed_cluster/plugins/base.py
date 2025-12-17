"""
Plugin Base Classes - الأصناف الأساسية للإضافات
==============================================

Base classes and interfaces for the plugin system.
"""

from __future__ import annotations

import abc
import importlib
import importlib.util
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class PluginType(str, Enum):
    """أنواع الإضافات المدعومة."""
    SCHEDULER = "scheduler"          # Custom scheduling policies
    EXECUTOR = "executor"            # Custom job executors
    STORAGE = "storage"              # Storage backends
    AUTH = "auth"                    # Authentication providers
    NOTIFICATION = "notification"    # Notification handlers
    METRICS = "metrics"              # Custom metrics collectors
    HOOK = "hook"                    # Event hooks
    MIDDLEWARE = "middleware"        # API middleware
    CUSTOM = "custom"                # Custom plugins


@dataclass
class PluginMetadata:
    """معلومات الإضافة."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    plugin_type: PluginType = PluginType.CUSTOM
    dependencies: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 100  # Lower = higher priority


class Plugin(abc.ABC):
    """
    Base class for all plugins.
    الصنف الأساسي لجميع الإضافات.

    Example:
        class MySchedulerPlugin(Plugin):
            metadata = PluginMetadata(
                name="my-scheduler",
                version="1.0.0",
                plugin_type=PluginType.SCHEDULER,
            )

            async def initialize(self, config):
                self.config = config

            async def cleanup(self):
                pass
    """

    metadata: PluginMetadata

    def __init__(self):
        self._initialized = False
        self._config: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        """اسم الإضافة."""
        return self.metadata.name

    @property
    def version(self) -> str:
        """إصدار الإضافة."""
        return self.metadata.version

    @property
    def is_initialized(self) -> bool:
        """هل تم تهيئة الإضافة؟"""
        return self._initialized

    @abc.abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """
        Initialize the plugin with configuration.
        تهيئة الإضافة مع الإعدادات.

        Args:
            config: Plugin-specific configuration
        """
        pass

    @abc.abstractmethod
    async def cleanup(self) -> None:
        """
        Cleanup plugin resources.
        تنظيف موارد الإضافة.
        """
        pass

    async def health_check(self) -> bool:
        """
        Check plugin health.
        فحص صحة الإضافة.

        Returns:
            True if healthy
        """
        return self._initialized


class PluginManager:
    """
    Plugin Manager - مدير الإضافات.

    Handles plugin discovery, loading, initialization, and lifecycle.

    Example:
        manager = PluginManager()

        # Load plugins from directory
        await manager.discover_plugins("/path/to/plugins")

        # Load specific plugin
        await manager.load_plugin(MyPlugin)

        # Get plugin by name
        scheduler = manager.get_plugin("my-scheduler")

        # Get all plugins of type
        schedulers = manager.get_plugins_by_type(PluginType.SCHEDULER)
    """

    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._plugin_classes: Dict[str, Type[Plugin]] = {}
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._load_order: List[str] = []

    @property
    def plugins(self) -> Dict[str, Plugin]:
        """جميع الإضافات المحملة."""
        return self._plugins.copy()

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """
        Get plugin by name.
        الحصول على إضافة بالاسم.
        """
        return self._plugins.get(name)

    def get_plugins_by_type(self, plugin_type: PluginType) -> List[Plugin]:
        """
        Get all plugins of a specific type.
        الحصول على جميع الإضافات من نوع معين.
        """
        return [
            p for p in self._plugins.values()
            if p.metadata.plugin_type == plugin_type
        ]

    async def discover_plugins(self, plugins_dir: str | Path) -> int:
        """
        Discover and load plugins from a directory.
        اكتشاف وتحميل الإضافات من مجلد.

        Args:
            plugins_dir: Path to plugins directory

        Returns:
            Number of plugins discovered
        """
        plugins_path = Path(plugins_dir)
        if not plugins_path.exists():
            logger.warning(f"Plugins directory not found: {plugins_path}")
            return 0

        count = 0
        for item in plugins_path.iterdir():
            try:
                if item.is_file() and item.suffix == ".py":
                    # Single file plugin
                    await self._load_plugin_from_file(item)
                    count += 1
                elif item.is_dir() and (item / "__init__.py").exists():
                    # Package plugin
                    await self._load_plugin_from_package(item)
                    count += 1
            except Exception as e:
                logger.error(f"Failed to load plugin from {item}: {e}")

        return count

    async def _load_plugin_from_file(self, file_path: Path) -> None:
        """Load plugin from a Python file."""
        spec = importlib.util.spec_from_file_location(
            file_path.stem,
            file_path
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            await self._register_plugins_from_module(module)

    async def _load_plugin_from_package(self, package_path: Path) -> None:
        """Load plugin from a package directory."""
        spec = importlib.util.spec_from_file_location(
            package_path.name,
            package_path / "__init__.py"
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            await self._register_plugins_from_module(module)

    async def _register_plugins_from_module(self, module) -> None:
        """Find and register Plugin subclasses from a module."""
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, Plugin)
                and obj is not Plugin
                and hasattr(obj, "metadata")
            ):
                await self.register_plugin_class(obj)

    async def register_plugin_class(self, plugin_class: Type[Plugin]) -> None:
        """
        Register a plugin class.
        تسجيل صنف إضافة.
        """
        if not hasattr(plugin_class, "metadata"):
            raise ValueError(f"Plugin class {plugin_class} missing metadata")

        name = plugin_class.metadata.name
        if name in self._plugin_classes:
            logger.warning(f"Plugin {name} already registered, replacing")

        self._plugin_classes[name] = plugin_class
        logger.info(f"Registered plugin class: {name}")

    async def load_plugin(
        self,
        plugin_class: Type[Plugin],
        config: Dict[str, Any] = None
    ) -> Plugin:
        """
        Instantiate and initialize a plugin.
        إنشاء وتهيئة إضافة.

        Args:
            plugin_class: The plugin class to load
            config: Plugin configuration

        Returns:
            Initialized plugin instance
        """
        config = config or {}
        name = plugin_class.metadata.name

        # Check dependencies
        for dep in plugin_class.metadata.dependencies:
            if dep not in self._plugins:
                raise RuntimeError(
                    f"Plugin {name} requires {dep} which is not loaded"
                )

        # Create instance
        plugin = plugin_class()

        # Initialize
        try:
            await plugin.initialize(config)
            plugin._initialized = True
            plugin._config = config
        except Exception as e:
            logger.error(f"Failed to initialize plugin {name}: {e}")
            raise

        # Register
        self._plugins[name] = plugin
        self._configs[name] = config
        self._load_order.append(name)

        logger.info(f"Loaded plugin: {name} v{plugin.version}")
        return plugin

    async def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin.
        إلغاء تحميل إضافة.

        Args:
            name: Plugin name

        Returns:
            True if unloaded successfully
        """
        plugin = self._plugins.get(name)
        if not plugin:
            return False

        # Check if other plugins depend on this one
        for other_name, other_plugin in self._plugins.items():
            if name in other_plugin.metadata.dependencies:
                raise RuntimeError(
                    f"Cannot unload {name}: {other_name} depends on it"
                )

        try:
            await plugin.cleanup()
        except Exception as e:
            logger.error(f"Error during plugin cleanup: {e}")

        del self._plugins[name]
        if name in self._configs:
            del self._configs[name]
        if name in self._load_order:
            self._load_order.remove(name)

        logger.info(f"Unloaded plugin: {name}")
        return True

    async def reload_plugin(self, name: str) -> Optional[Plugin]:
        """
        Reload a plugin with its current configuration.
        إعادة تحميل إضافة.
        """
        if name not in self._plugins:
            return None

        plugin_class = self._plugin_classes.get(name)
        config = self._configs.get(name, {})

        if not plugin_class:
            logger.error(f"Cannot reload {name}: class not found")
            return None

        await self.unload_plugin(name)
        return await self.load_plugin(plugin_class, config)

    async def initialize_all(self, configs: Dict[str, Dict[str, Any]] = None) -> None:
        """
        Load and initialize all registered plugins.
        تحميل وتهيئة جميع الإضافات المسجلة.
        """
        configs = configs or {}

        # Sort by priority
        sorted_classes = sorted(
            self._plugin_classes.values(),
            key=lambda c: c.metadata.priority
        )

        for plugin_class in sorted_classes:
            if not plugin_class.metadata.enabled:
                continue

            name = plugin_class.metadata.name
            config = configs.get(name, {})

            try:
                await self.load_plugin(plugin_class, config)
            except Exception as e:
                logger.error(f"Failed to load plugin {name}: {e}")

    async def cleanup_all(self) -> None:
        """
        Cleanup all plugins in reverse load order.
        تنظيف جميع الإضافات.
        """
        for name in reversed(self._load_order):
            try:
                await self.unload_plugin(name)
            except Exception as e:
                logger.error(f"Error unloading plugin {name}: {e}")

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Run health checks on all plugins.
        فحص صحة جميع الإضافات.

        Returns:
            Dict mapping plugin names to health status
        """
        results = {}
        for name, plugin in self._plugins.items():
            try:
                results[name] = await plugin.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                results[name] = False
        return results

    def get_plugin_info(self) -> List[Dict[str, Any]]:
        """
        Get information about all loaded plugins.
        الحصول على معلومات جميع الإضافات المحملة.
        """
        return [
            {
                "name": p.name,
                "version": p.version,
                "type": p.metadata.plugin_type.value,
                "description": p.metadata.description,
                "author": p.metadata.author,
                "initialized": p.is_initialized,
                "priority": p.metadata.priority,
            }
            for p in self._plugins.values()
        ]
