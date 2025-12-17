"""
Application styles and themes
الأنماط والثيمات للتطبيق
"""

# Color palette - Modern dark theme
COLORS = {
    "primary": "#6366f1",      # Indigo
    "primary_hover": "#818cf8",
    "primary_dark": "#4f46e5",
    "secondary": "#64748b",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "info": "#3b82f6",

    # Background colors
    "bg_dark": "#0f172a",
    "bg_medium": "#1e293b",
    "bg_light": "#334155",
    "bg_card": "#1e293b",

    # Text colors
    "text_primary": "#f8fafc",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",

    # Border colors
    "border": "#334155",
    "border_light": "#475569",

    # Status colors
    "status_running": "#22c55e",
    "status_pending": "#f59e0b",
    "status_failed": "#ef4444",
    "status_completed": "#3b82f6",
    "status_idle": "#64748b",
}

# Main application stylesheet
MAIN_STYLESHEET = f"""
/* Global Styles */
QMainWindow, QWidget {{
    background-color: {COLORS['bg_dark']};
    color: {COLORS['text_primary']};
    font-family: 'Segoe UI', 'SF Pro Display', -apple-system, sans-serif;
    font-size: 13px;
}}

/* Sidebar Styles */
#sidebar {{
    background-color: {COLORS['bg_medium']};
    border-right: 1px solid {COLORS['border']};
    min-width: 220px;
    max-width: 220px;
}}

#sidebar_logo {{
    font-size: 18px;
    font-weight: bold;
    color: {COLORS['primary']};
    padding: 20px;
}}

#sidebar_button {{
    background-color: transparent;
    border: none;
    border-radius: 8px;
    color: {COLORS['text_secondary']};
    padding: 12px 16px;
    text-align: left;
    margin: 2px 8px;
}}

#sidebar_button:hover {{
    background-color: {COLORS['bg_light']};
    color: {COLORS['text_primary']};
}}

#sidebar_button:checked, #sidebar_button[active="true"] {{
    background-color: {COLORS['primary']};
    color: {COLORS['text_primary']};
}}

/* Card Styles */
.card {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
    padding: 20px;
}}

#stat_card {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
    padding: 20px;
    min-width: 180px;
}}

#stat_card_title {{
    color: {COLORS['text_secondary']};
    font-size: 12px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

#stat_card_value {{
    color: {COLORS['text_primary']};
    font-size: 28px;
    font-weight: 600;
    margin-top: 8px;
}}

/* Table Styles */
QTableWidget {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    gridline-color: {COLORS['border']};
}}

QTableWidget::item {{
    padding: 8px 12px;
    border-bottom: 1px solid {COLORS['border']};
}}

QTableWidget::item:selected {{
    background-color: {COLORS['primary']};
}}

QHeaderView::section {{
    background-color: {COLORS['bg_medium']};
    color: {COLORS['text_secondary']};
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid {COLORS['border']};
    font-weight: 600;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.5px;
}}

/* Button Styles */
QPushButton {{
    background-color: {COLORS['primary']};
    color: {COLORS['text_primary']};
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {COLORS['primary_hover']};
}}

QPushButton:pressed {{
    background-color: {COLORS['primary_dark']};
}}

QPushButton:disabled {{
    background-color: {COLORS['secondary']};
    color: {COLORS['text_muted']};
}}

#secondary_button {{
    background-color: {COLORS['bg_light']};
    color: {COLORS['text_primary']};
}}

#secondary_button:hover {{
    background-color: {COLORS['border_light']};
}}

#danger_button {{
    background-color: {COLORS['danger']};
}}

#danger_button:hover {{
    background-color: #dc2626;
}}

#success_button {{
    background-color: {COLORS['success']};
}}

/* Input Styles */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {COLORS['bg_medium']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 10px 12px;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {COLORS['primary']};
}}

QComboBox {{
    background-color: {COLORS['bg_medium']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 8px 12px;
    min-width: 120px;
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox QAbstractItemView {{
    background-color: {COLORS['bg_medium']};
    border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['primary']};
}}

QSpinBox {{
    background-color: {COLORS['bg_medium']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 8px;
}}

/* Scrollbar Styles */
QScrollBar:vertical {{
    background-color: {COLORS['bg_dark']};
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background-color: {COLORS['border']};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {COLORS['border_light']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {COLORS['bg_dark']};
    height: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal {{
    background-color: {COLORS['border']};
    border-radius: 5px;
    min-width: 30px;
}}

/* Tab Styles */
QTabWidget::pane {{
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    background-color: {COLORS['bg_card']};
}}

QTabBar::tab {{
    background-color: {COLORS['bg_medium']};
    color: {COLORS['text_secondary']};
    padding: 10px 20px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}

QTabBar::tab:selected {{
    background-color: {COLORS['bg_card']};
    color: {COLORS['text_primary']};
}}

/* Progress Bar */
QProgressBar {{
    background-color: {COLORS['bg_light']};
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {COLORS['primary']};
    border-radius: 4px;
}}

/* Tooltips */
QToolTip {{
    background-color: {COLORS['bg_medium']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 8px;
}}

/* Status Labels */
#status_running {{
    color: {COLORS['status_running']};
    font-weight: 600;
}}

#status_pending {{
    color: {COLORS['status_pending']};
    font-weight: 600;
}}

#status_failed {{
    color: {COLORS['status_failed']};
    font-weight: 600;
}}

#status_completed {{
    color: {COLORS['status_completed']};
    font-weight: 600;
}}

/* Section Headers */
#section_header {{
    font-size: 16px;
    font-weight: 600;
    color: {COLORS['text_primary']};
    margin-bottom: 16px;
}}

/* Menu */
QMenu {{
    background-color: {COLORS['bg_medium']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px;
}}

QMenu::item {{
    padding: 8px 24px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {COLORS['primary']};
}}

/* Dialog */
QDialog {{
    background-color: {COLORS['bg_dark']};
}}

QDialogButtonBox QPushButton {{
    min-width: 80px;
}}

/* Group Box */
QGroupBox {{
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {COLORS['text_secondary']};
}}

/* Splitter */
QSplitter::handle {{
    background-color: {COLORS['border']};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}
"""


def get_status_color(status: str) -> str:
    """Get color for a status string"""
    status_lower = status.lower()
    if status_lower in ("running", "active", "healthy", "online"):
        return COLORS["status_running"]
    elif status_lower in ("pending", "queued", "waiting"):
        return COLORS["status_pending"]
    elif status_lower in ("failed", "error", "unhealthy", "offline"):
        return COLORS["status_failed"]
    elif status_lower in ("completed", "success", "done"):
        return COLORS["status_completed"]
    else:
        return COLORS["status_idle"]
