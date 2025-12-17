"""
Theme System - Light and Dark themes
نظام السمات - السمات الفاتحة والداكنة
"""

from typing import Dict
from dataclasses import dataclass
from enum import Enum


class ThemeType(Enum):
    """Available theme types"""
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"


@dataclass
class Theme:
    """Theme color definitions"""
    name: str
    primary: str
    primary_hover: str
    primary_dark: str
    secondary: str
    success: str
    warning: str
    danger: str
    info: str

    bg_dark: str
    bg_medium: str
    bg_light: str
    bg_card: str

    text_primary: str
    text_secondary: str
    text_muted: str

    border: str
    border_light: str

    status_running: str
    status_pending: str
    status_failed: str
    status_completed: str
    status_idle: str


# Dark Theme
DARK_THEME = Theme(
    name="Dark",
    primary="#6366f1",
    primary_hover="#818cf8",
    primary_dark="#4f46e5",
    secondary="#64748b",
    success="#22c55e",
    warning="#f59e0b",
    danger="#ef4444",
    info="#3b82f6",

    bg_dark="#0f172a",
    bg_medium="#1e293b",
    bg_light="#334155",
    bg_card="#1e293b",

    text_primary="#f8fafc",
    text_secondary="#94a3b8",
    text_muted="#64748b",

    border="#334155",
    border_light="#475569",

    status_running="#22c55e",
    status_pending="#f59e0b",
    status_failed="#ef4444",
    status_completed="#3b82f6",
    status_idle="#64748b",
)

# Light Theme
LIGHT_THEME = Theme(
    name="Light",
    primary="#4f46e5",
    primary_hover="#6366f1",
    primary_dark="#4338ca",
    secondary="#64748b",
    success="#16a34a",
    warning="#d97706",
    danger="#dc2626",
    info="#2563eb",

    bg_dark="#f8fafc",
    bg_medium="#f1f5f9",
    bg_light="#e2e8f0",
    bg_card="#ffffff",

    text_primary="#0f172a",
    text_secondary="#475569",
    text_muted="#94a3b8",

    border="#e2e8f0",
    border_light="#cbd5e1",

    status_running="#16a34a",
    status_pending="#d97706",
    status_failed="#dc2626",
    status_completed="#2563eb",
    status_idle="#94a3b8",
)


class ThemeManager:
    """Manager for application themes"""

    _instance = None
    _current_theme: Theme = DARK_THEME
    _listeners = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_theme(cls) -> Theme:
        """Get current theme"""
        return cls._current_theme

    @classmethod
    def set_theme(cls, theme_type: ThemeType):
        """Set application theme"""
        if theme_type == ThemeType.DARK:
            cls._current_theme = DARK_THEME
        elif theme_type == ThemeType.LIGHT:
            cls._current_theme = LIGHT_THEME
        elif theme_type == ThemeType.SYSTEM:
            # Detect system theme (simplified - would need platform-specific code)
            cls._current_theme = DARK_THEME

        # Notify listeners
        for listener in cls._listeners:
            listener(cls._current_theme)

    @classmethod
    def add_listener(cls, callback):
        """Add theme change listener"""
        cls._listeners.append(callback)

    @classmethod
    def remove_listener(cls, callback):
        """Remove theme change listener"""
        if callback in cls._listeners:
            cls._listeners.remove(callback)

    @classmethod
    def get_colors(cls) -> Dict[str, str]:
        """Get current theme colors as dictionary"""
        theme = cls._current_theme
        return {
            "primary": theme.primary,
            "primary_hover": theme.primary_hover,
            "primary_dark": theme.primary_dark,
            "secondary": theme.secondary,
            "success": theme.success,
            "warning": theme.warning,
            "danger": theme.danger,
            "info": theme.info,
            "bg_dark": theme.bg_dark,
            "bg_medium": theme.bg_medium,
            "bg_light": theme.bg_light,
            "bg_card": theme.bg_card,
            "text_primary": theme.text_primary,
            "text_secondary": theme.text_secondary,
            "text_muted": theme.text_muted,
            "border": theme.border,
            "border_light": theme.border_light,
            "status_running": theme.status_running,
            "status_pending": theme.status_pending,
            "status_failed": theme.status_failed,
            "status_completed": theme.status_completed,
            "status_idle": theme.status_idle,
        }

    @classmethod
    def generate_stylesheet(cls) -> str:
        """Generate Qt stylesheet for current theme"""
        theme = cls._current_theme
        return f"""
/* Global Styles */
QMainWindow, QWidget {{
    background-color: {theme.bg_dark};
    color: {theme.text_primary};
    font-family: 'Segoe UI', 'SF Pro Display', -apple-system, sans-serif;
    font-size: 13px;
}}

/* Sidebar */
#sidebar {{
    background-color: {theme.bg_medium};
    border-right: 1px solid {theme.border};
    min-width: 220px;
    max-width: 220px;
}}

#sidebar_button {{
    background-color: transparent;
    border: none;
    border-radius: 8px;
    color: {theme.text_secondary};
    padding: 12px 16px;
    text-align: left;
    margin: 2px 8px;
}}

#sidebar_button:hover {{
    background-color: {theme.bg_light};
    color: {theme.text_primary};
}}

#sidebar_button:checked {{
    background-color: {theme.primary};
    color: {theme.text_primary};
}}

/* Cards */
#stat_card {{
    background-color: {theme.bg_card};
    border: 1px solid {theme.border};
    border-radius: 12px;
    padding: 20px;
}}

/* Tables */
QTableWidget {{
    background-color: {theme.bg_card};
    border: 1px solid {theme.border};
    border-radius: 8px;
    gridline-color: {theme.border};
}}

QTableWidget::item {{
    padding: 8px 12px;
    border-bottom: 1px solid {theme.border};
}}

QTableWidget::item:selected {{
    background-color: {theme.primary};
}}

QHeaderView::section {{
    background-color: {theme.bg_medium};
    color: {theme.text_secondary};
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid {theme.border};
    font-weight: 600;
}}

/* Buttons */
QPushButton {{
    background-color: {theme.primary};
    color: {theme.text_primary};
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {theme.primary_hover};
}}

QPushButton:pressed {{
    background-color: {theme.primary_dark};
}}

QPushButton:disabled {{
    background-color: {theme.secondary};
    color: {theme.text_muted};
}}

#secondary_button {{
    background-color: {theme.bg_light};
    color: {theme.text_primary};
}}

#secondary_button:hover {{
    background-color: {theme.border_light};
}}

#danger_button {{
    background-color: {theme.danger};
}}

#success_button {{
    background-color: {theme.success};
}}

/* Inputs */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {theme.bg_medium};
    color: {theme.text_primary};
    border: 1px solid {theme.border};
    border-radius: 6px;
    padding: 10px 12px;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {theme.primary};
}}

QComboBox {{
    background-color: {theme.bg_medium};
    color: {theme.text_primary};
    border: 1px solid {theme.border};
    border-radius: 6px;
    padding: 8px 12px;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background-color: {theme.bg_dark};
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background-color: {theme.border};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {theme.border_light};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* Tabs */
QTabWidget::pane {{
    border: 1px solid {theme.border};
    border-radius: 8px;
    background-color: {theme.bg_card};
}}

QTabBar::tab {{
    background-color: {theme.bg_medium};
    color: {theme.text_secondary};
    padding: 10px 20px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}

QTabBar::tab:selected {{
    background-color: {theme.bg_card};
    color: {theme.text_primary};
}}

/* Progress Bar */
QProgressBar {{
    background-color: {theme.bg_light};
    border-radius: 4px;
    height: 8px;
}}

QProgressBar::chunk {{
    background-color: {theme.primary};
    border-radius: 4px;
}}

/* Menu */
QMenu {{
    background-color: {theme.bg_medium};
    border: 1px solid {theme.border};
    border-radius: 8px;
    padding: 8px;
}}

QMenu::item {{
    padding: 8px 24px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {theme.primary};
}}

/* Menu Bar */
QMenuBar {{
    background-color: {theme.bg_medium};
    color: {theme.text_primary};
    border-bottom: 1px solid {theme.border};
    padding: 4px;
}}

QMenuBar::item:selected {{
    background-color: {theme.bg_light};
}}

/* Status Bar */
QStatusBar {{
    background-color: {theme.bg_medium};
    color: {theme.text_secondary};
    border-top: 1px solid {theme.border};
}}

/* Tooltips */
QToolTip {{
    background-color: {theme.bg_medium};
    color: {theme.text_primary};
    border: 1px solid {theme.border};
    border-radius: 4px;
    padding: 8px;
}}

/* Dialog */
QDialog {{
    background-color: {theme.bg_dark};
}}

/* Group Box */
QGroupBox {{
    border: 1px solid {theme.border};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {theme.text_secondary};
}}
"""


def get_status_color(status: str) -> str:
    """Get color for a status string"""
    theme = ThemeManager.get_theme()
    status_lower = status.lower()

    if status_lower in ("running", "active", "healthy", "online"):
        return theme.status_running
    elif status_lower in ("pending", "queued", "waiting"):
        return theme.status_pending
    elif status_lower in ("failed", "error", "unhealthy", "offline"):
        return theme.status_failed
    elif status_lower in ("completed", "success", "done"):
        return theme.status_completed
    else:
        return theme.status_idle
