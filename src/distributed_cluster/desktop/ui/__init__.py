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

from .fluent_design import (
    FluentDesignSystem,
    FluentTheme,
    FluentColors,
    FluentTypography,
    FluentSpacing,
    FluentCorners,
    FluentElevation,
    MicaEffect,
    AcrylicEffect,
    RevealEffect,
    fluent,
)
from .animations import (
    AnimationManager,
    FadeAnimation,
    SlideAnimation,
    ScaleAnimation,
    SpringAnimation,
    ColorAnimation,
    StaggeredAnimation,
    FluentEasing,
    SpringConfig,
    animations,
)
from .components import (
    FluentButton,
    FluentCard,
    FluentInput,
    FluentSwitch,
    FluentSlider,
    FluentProgressRing,
    FluentBadge,
    FluentAvatar,
    FluentTooltip,
    ButtonVariant,
    ButtonSize,
    BadgeVariant,
    SkeletonLoader,
)
from .titlebar import (
    CustomTitleBar,
    FramelessWindow,
    TitleBarButton,
    FluentIcons,
)
from .sidebar import (
    FluentSidebar,
    SidebarItem,
    SidebarGroup,
    NavItem,
    SidebarHeader,
    ConnectionStatus,
)
from .notifications import (
    NotificationCenter,
    InAppNotificationManager,
    Toast,
    Notification,
    NotificationAction,
    NotificationType,
)
from .dashboard import (
    FluentDashboard,
    AnimatedStatCard,
    CircularProgressChart,
    LineChart,
    ActivityFeed,
    ActivityItemData,
    SystemHealthCard,
)
from .data_table import (
    FluentDataTable,
    ColumnDefinition,
    ColumnType,
    CellRenderer,
)
from .splash import (
    FluentSplashScreen,
    SplashScreenManager,
    AnimatedLogo,
    SplashProgressRing,
    LoadingOverlay,
)
from .dialogs import (
    FluentDialog,
    ConnectionDialog,
    ConfirmationDialog,
    ConfirmationType,
    ProgressDialog,
    InputDialog,
    JobSubmitDialog,
    ConnectionProfile,
)
from .windows_integration import (
    WindowsIntegrationManager,
    WindowsThemeDetector,
    WindowsToastNotifications,
    TaskbarProgress,
    TaskbarProgressState,
    FluentSystemTray,
    WindowsRegistry,
    WindowsCredentialManager,
    WindowsJumpList,
    Windows11Effects,
    JumpListItem,
    IS_WINDOWS,
    APP_ID,
    APP_NAME,
)
from .views import (
    FluentJobsView,
    FluentWorkersView,
    FluentSettingsView,
    FluentLogsView,
    FluentMetricsView,
)
from .main_window import (
    FluentMainWindow,
    create_fluent_app,
    run_app,
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
    # Main Window
    "FluentMainWindow",
    "create_fluent_app",
    "run_app",
]
