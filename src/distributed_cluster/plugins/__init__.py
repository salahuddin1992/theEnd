"""
Plugin System - نظام الإضافات
=============================

Extensible plugin system for the distributed cluster.
نظام إضافات قابل للتوسيع للكلاستر الموزّع.
"""

from .base import Plugin, PluginManager, PluginType, PluginMetadata
from .hooks import HookManager, HookType

__all__ = [
    "Plugin",
    "PluginManager",
    "PluginType",
    "PluginMetadata",
    "HookManager",
    "HookType",
]
