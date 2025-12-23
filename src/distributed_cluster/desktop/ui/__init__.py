"""
NebulaCompute Desktop - Advanced Windows 11 UI System
واجهة مستخدم متقدمة بتصميم Windows 11

This module provides:
- Fluent Design System (Mica, Acrylic, Reveal effects)
- Modern animations and transitions
- Custom window decorations
- Advanced widgets
- Complete dashboard view
- Notification system
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
from .main_window import (
    FluentMainWindow,
    create_fluent_app,
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
    # Main Window
    "FluentMainWindow",
    "create_fluent_app",
]
