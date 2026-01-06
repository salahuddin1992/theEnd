"""
Desktop Views - واجهات سطح المكتب
=================================

Main views/pages for the desktop application.

Author: NebulaCompute Team
License: MIT
"""

from distributed_cluster.desktop.views.cluster_overview import ClusterOverviewView
from distributed_cluster.desktop.views.dashboard import DashboardView
from distributed_cluster.desktop.views.jobs import JobDetailPanel, JobsView, SubmitJobDialog
from distributed_cluster.desktop.views.logs import LogsView
from distributed_cluster.desktop.views.metrics import MetricCard, MetricsTable, MetricsView
from distributed_cluster.desktop.views.plugin_manager import PluginCard, PluginLoader, PluginManagerView
from distributed_cluster.desktop.views.pools import PoolsView
from distributed_cluster.desktop.views.powershell_console import PowerShellConsoleView, ShellProcess
from distributed_cluster.desktop.views.queues import QueuesView
from distributed_cluster.desktop.views.script_editor import PythonHighlighter, SandboxExecutor, ScriptEditorView
from distributed_cluster.desktop.views.settings import SettingsView
from distributed_cluster.desktop.views.templates import CreateTemplateDialog, TemplateDetailPanel, TemplatesView
from distributed_cluster.desktop.views.workers import WorkerDetailPanel, WorkersView

__all__ = [
    # Cluster Overview
    "ClusterOverviewView",
    # Dashboard
    "DashboardView",
    # Jobs
    "JobsView",
    "JobDetailPanel",
    "SubmitJobDialog",
    # Logs
    "LogsView",
    # Metrics
    "MetricsView",
    "MetricCard",
    "MetricsTable",
    # Plugin Manager
    "PluginManagerView",
    "PluginLoader",
    "PluginCard",
    # Pools
    "PoolsView",
    # PowerShell Console
    "PowerShellConsoleView",
    "ShellProcess",
    # Queues
    "QueuesView",
    # Script Editor
    "ScriptEditorView",
    "PythonHighlighter",
    "SandboxExecutor",
    # Settings
    "SettingsView",
    # Templates
    "TemplatesView",
    "TemplateDetailPanel",
    "CreateTemplateDialog",
    # Workers
    "WorkersView",
    "WorkerDetailPanel",
]
