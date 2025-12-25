"""
Desktop Widgets - عناصر واجهة سطح المكتب
========================================

Custom Qt widgets for the desktop application.

Author: NebulaCompute Team
License: MIT
"""

from distributed_cluster.desktop.widgets.charts import LineChart, DonutChart, BarChart, MiniChart
from distributed_cluster.desktop.widgets.connection_dialog import ConnectionDialog, ServerItem
from distributed_cluster.desktop.widgets.data_table import DataTable, StatusLabel
from distributed_cluster.desktop.widgets.login_dialog import LoginDialog
from distributed_cluster.desktop.widgets.notifications import (
    NotificationType,
    NotificationWidget,
    NotificationManager,
    ToastNotification,
)
from distributed_cluster.desktop.widgets.sidebar import Sidebar, SidebarButton
from distributed_cluster.desktop.widgets.stat_card import StatCard, ResourceCard
from distributed_cluster.desktop.widgets.system_tray import SystemTrayIcon
from distributed_cluster.desktop.widgets.terminal import TerminalWidget, TerminalOutput, CommandInput

__all__ = [
    # Charts
    "LineChart",
    "DonutChart",
    "BarChart",
    "MiniChart",
    # Connection Dialog
    "ConnectionDialog",
    "ServerItem",
    # Data Table
    "DataTable",
    "StatusLabel",
    # Login Dialog
    "LoginDialog",
    # Notifications
    "NotificationType",
    "NotificationWidget",
    "NotificationManager",
    "ToastNotification",
    # Sidebar
    "Sidebar",
    "SidebarButton",
    # Stat Card
    "StatCard",
    "ResourceCard",
    # System Tray
    "SystemTrayIcon",
    # Terminal
    "TerminalWidget",
    "TerminalOutput",
    "CommandInput",
]
