"""
Windows 11 Desktop Integration - تكامل سطح المكتب لويندوز 11
=============================================================

Comprehensive Windows 11 integration module providing:
- Windows Terminal Integration
- Enhanced Fluent Design System
- Advanced System Tray with Quick Actions
- Native Windows 11 Notifications (WinRT)
- Auto-start with Windows
- Windows Snap Layouts support
- PowerShell integration

يوفر هذا الملف تكامل شامل مع ويندوز 11:
- تكامل مع Windows Terminal
- نظام Fluent Design محسّن
- شريط النظام مع إجراءات سريعة
- إشعارات ويندوز 11 الأصلية
- بدء تلقائي مع ويندوز
- دعم Snap Layouts
- تكامل PowerShell

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.desktop.windows.auto_start import (
    AutoStartManager,
    StartupOptions,
)
from distributed_cluster.desktop.windows.enhanced_tray import (
    EnhancedSystemTray,
    QuickAction,
    TrayStatus,
)
from distributed_cluster.desktop.windows.fluent_widgets import (
    FluentButton,
    FluentCard,
    FluentComboBox,
    FluentInfoBar,
    FluentNavigationView,
    FluentProgressBar,
    FluentSearchBox,
    FluentSlider,
    FluentTeachingTip,
    FluentToggle,
)
from distributed_cluster.desktop.windows.terminal_integration import (
    TerminalProfile,
    TerminalSettings,
    WindowsTerminalManager,
)
from distributed_cluster.desktop.windows.winrt_notifications import (
    NotificationButton,
    NotificationProgress,
    WinRTNotificationManager,
)

__all__ = [
    # Terminal
    "WindowsTerminalManager",
    "TerminalProfile",
    "TerminalSettings",
    # Tray
    "EnhancedSystemTray",
    "QuickAction",
    "TrayStatus",
    # Notifications
    "WinRTNotificationManager",
    "NotificationButton",
    "NotificationProgress",
    # Auto-start
    "AutoStartManager",
    "StartupOptions",
    # Fluent Widgets
    "FluentButton",
    "FluentCard",
    "FluentProgressBar",
    "FluentToggle",
    "FluentSlider",
    "FluentComboBox",
    "FluentSearchBox",
    "FluentNavigationView",
    "FluentInfoBar",
    "FluentTeachingTip",
]

__version__ = "1.0.0"
