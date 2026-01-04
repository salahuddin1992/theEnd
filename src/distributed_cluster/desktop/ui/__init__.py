"""
NebulaCompute Desktop - Advanced Windows 11 UI System
واجهة مستخدم متقدمة بتصميم Windows 11

This module provides:
- Fluent Design System (Mica, Acrylic, Reveal effects)
- Modern animations and transitions
- Custom window decorations
- Advanced widgets and data tables
- Complete dashboard and view pages
- Notification system
- Windows 11 integration (tray, notifications, registry)
- Splash screen with animations
- Modern dialogs
"""

from .animations import (
    AnimationManager,
    ColorAnimation,
    FadeAnimation,
    FluentEasing,
    ScaleAnimation,
    SlideAnimation,
    SpringAnimation,
    SpringConfig,
    StaggeredAnimation,
    animations,
)
from .components import (
    BadgeVariant,
    ButtonSize,
    ButtonVariant,
    FluentAvatar,
    FluentBadge,
    FluentButton,
    FluentCard,
    FluentInput,
    FluentProgressRing,
    FluentSlider,
    FluentSwitch,
    FluentTooltip,
    SkeletonLoader,
)
from .dashboard import (
    ActivityFeed,
    ActivityItemData,
    AnimatedStatCard,
    CircularProgressChart,
    FluentDashboard,
    LineChart,
    SystemHealthCard,
)
from .data_table import (
    CellRenderer,
    ColumnDefinition,
    ColumnType,
    FluentDataTable,
)
from .dialogs import (
    ConfirmationDialog,
    ConfirmationType,
    ConnectionDialog,
    ConnectionProfile,
    FluentDialog,
    InputDialog,
    JobSubmitDialog,
    ProgressDialog,
)
from .fluent_design import (
    AcrylicEffect,
    FluentColors,
    FluentCorners,
    FluentDesignSystem,
    FluentElevation,
    FluentSpacing,
    FluentTheme,
    FluentTypography,
    MicaEffect,
    RevealEffect,
    fluent,
)
from .main_window import (
    FluentMainWindow,
    create_fluent_app,
    run_app,
)
from .notifications import (
    InAppNotificationManager,
    Notification,
    NotificationAction,
    NotificationCenter,
    NotificationType,
    Toast,
)
from .sidebar import (
    ConnectionStatus,
    FluentSidebar,
    NavItem,
    SidebarGroup,
    SidebarHeader,
    SidebarItem,
)
from .splash import (
    AnimatedLogo,
    FluentSplashScreen,
    LoadingOverlay,
    SplashProgressRing,
    SplashScreenManager,
)
from .titlebar import (
    CustomTitleBar,
    FluentIcons,
    FramelessWindow,
    TitleBarButton,
)
from .views import (
    FluentJobsView,
    FluentLogsView,
    FluentMetricsView,
    FluentPoolsView,
    FluentQueuesView,
    FluentSettingsView,
    FluentTemplatesView,
    FluentWorkersView,
)
from .windows_integration import (
    APP_ID,
    APP_NAME,
    IS_WINDOWS,
    FluentSystemTray,
    JumpListItem,
    TaskbarProgress,
    TaskbarProgressState,
    Windows11Effects,
    WindowsCredentialManager,
    WindowsIntegrationManager,
    WindowsJumpList,
    WindowsRegistry,
    WindowsThemeDetector,
    WindowsToastNotifications,
)

__all__ = [
    # Design System
    "FluentDesignSystem",
    "FluentTheme",
    "FluentColors",
    "FluentTypography",
    "FluentSpacing",
    "FluentCorners",
    "FluentElevation",
    "MicaEffect",
    "AcrylicEffect",
    "RevealEffect",
    "fluent",
    # Animations
    "AnimationManager",
    "FadeAnimation",
    "SlideAnimation",
    "ScaleAnimation",
    "SpringAnimation",
    "ColorAnimation",
    "StaggeredAnimation",
    "FluentEasing",
    "SpringConfig",
    "animations",
    # Components
    "FluentButton",
    "FluentCard",
    "FluentInput",
    "FluentSwitch",
    "FluentSlider",
    "FluentProgressRing",
    "FluentBadge",
    "FluentAvatar",
    "FluentTooltip",
    "ButtonVariant",
    "ButtonSize",
    "BadgeVariant",
    "SkeletonLoader",
    # Data Table
    "FluentDataTable",
    "ColumnDefinition",
    "ColumnType",
    "CellRenderer",
    # Window
    "CustomTitleBar",
    "FramelessWindow",
    "TitleBarButton",
    "FluentIcons",
    # Sidebar
    "FluentSidebar",
    "SidebarItem",
    "SidebarGroup",
    "NavItem",
    "SidebarHeader",
    "ConnectionStatus",
    # Notifications
    "NotificationCenter",
    "InAppNotificationManager",
    "Toast",
    "Notification",
    "NotificationAction",
    "NotificationType",
    # Dashboard
    "FluentDashboard",
    "AnimatedStatCard",
    "CircularProgressChart",
    "LineChart",
    "ActivityFeed",
    "ActivityItemData",
    "SystemHealthCard",
    # Splash Screen
    "FluentSplashScreen",
    "SplashScreenManager",
    "AnimatedLogo",
    "SplashProgressRing",
    "LoadingOverlay",
    # Dialogs
    "FluentDialog",
    "ConnectionDialog",
    "ConfirmationDialog",
    "ConfirmationType",
    "ProgressDialog",
    "InputDialog",
    "JobSubmitDialog",
    "ConnectionProfile",
    # Windows Integration
    "WindowsIntegrationManager",
    "WindowsThemeDetector",
    "WindowsToastNotifications",
    "TaskbarProgress",
    "TaskbarProgressState",
    "FluentSystemTray",
    "WindowsRegistry",
    "WindowsCredentialManager",
    "WindowsJumpList",
    "Windows11Effects",
    "JumpListItem",
    "IS_WINDOWS",
    "APP_ID",
    "APP_NAME",
    # Views
    "FluentJobsView",
    "FluentWorkersView",
    "FluentSettingsView",
    "FluentLogsView",
    "FluentMetricsView",
    "FluentTemplatesView",
    "FluentPoolsView",
    "FluentQueuesView",
    # Main Window
    "FluentMainWindow",
    "create_fluent_app",
    "run_app",
]
