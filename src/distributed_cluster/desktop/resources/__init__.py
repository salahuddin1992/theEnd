"""
Desktop Resources - موارد سطح المكتب
=====================================

Icons, styles, and themes for the desktop application.

Author: NebulaCompute Team
License: MIT
"""

from distributed_cluster.desktop.resources.styles import COLORS, MAIN_STYLESHEET
from distributed_cluster.desktop.resources.themes import get_theme, apply_theme, Theme

__all__ = [
    "COLORS",
    "MAIN_STYLESHEET",
    "get_theme",
    "apply_theme",
    "Theme",
]
