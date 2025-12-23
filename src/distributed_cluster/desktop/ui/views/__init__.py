"""
NebulaCompute Desktop - View Pages
صفحات العرض

All main application views/pages.
"""

from .jobs import FluentJobsView
from .workers import FluentWorkersView
from .settings import FluentSettingsView
from .logs import FluentLogsView
from .metrics import FluentMetricsView
from .templates import FluentTemplatesView
from .pools import FluentPoolsView
from .queues import FluentQueuesView

__all__ = [
    "FluentJobsView",
    "FluentWorkersView",
    "FluentSettingsView",
    "FluentLogsView",
    "FluentMetricsView",
    "FluentTemplatesView",
    "FluentPoolsView",
    "FluentQueuesView",
]
