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

__all__ = [
    "FluentJobsView",
    "FluentWorkersView",
    "FluentSettingsView",
    "FluentLogsView",
    "FluentMetricsView",
]
