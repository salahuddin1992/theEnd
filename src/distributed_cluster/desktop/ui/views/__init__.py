"""
NebulaCompute Desktop - View Pages
صفحات العرض

All main application views/pages.
"""

from .ai_tasks import AITasksView
from .jobs import FluentJobsView
from .logs import FluentLogsView
from .metrics import FluentMetricsView
from .pools import FluentPoolsView
from .queues import FluentQueuesView
from .settings import FluentSettingsView
from .templates import FluentTemplatesView
from .workers import FluentWorkersView

__all__ = [
    "FluentJobsView",
    "FluentWorkersView",
    "FluentSettingsView",
    "FluentLogsView",
    "FluentMetricsView",
    "FluentTemplatesView",
    "FluentPoolsView",
    "FluentQueuesView",
    "AITasksView",
]
