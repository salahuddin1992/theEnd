"""
Statistics Card Widget
ويدجت بطاقة الإحصائيات
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from ..resources.styles import COLORS


class StatCard(QFrame):
    """A card widget displaying a statistic with title and value"""

    def __init__(
        self,
        title: str,
        value: str = "0",
        icon: str = "",
        color: str = None,
        parent=None
    ):
        super().__init__(parent)
        self.setObjectName("stat_card")

        self._color = color or COLORS["primary"]
        self._setup_ui(title, value, icon)

    def _setup_ui(self, title: str, value: str, icon: str):
        """Setup the card UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # Icon and title row
        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"font-size: 20px; color: {self._color};")
            layout.addWidget(icon_label)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setObjectName("stat_card_title")
        layout.addWidget(self.title_label)

        # Value
        self.value_label = QLabel(value)
        self.value_label.setObjectName("stat_card_value")
        self.value_label.setStyleSheet(f"color: {self._color}; font-size: 28px; font-weight: 600;")
        layout.addWidget(self.value_label)

        layout.addStretch()

    def set_value(self, value: str):
        """Update the displayed value"""
        self.value_label.setText(value)

    def set_color(self, color: str):
        """Update the value color"""
        self._color = color
        self.value_label.setStyleSheet(f"color: {self._color}; font-size: 28px; font-weight: 600;")


class ResourceCard(QFrame):
    """A card showing resource usage with progress indicator"""

    def __init__(
        self,
        title: str,
        used: float = 0,
        total: float = 100,
        unit: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.setObjectName("stat_card")

        self._unit = unit
        self._setup_ui(title, used, total)

    def _setup_ui(self, title: str, used: float, total: float):
        """Setup the card UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setObjectName("stat_card_title")
        layout.addWidget(self.title_label)

        # Usage value
        self.value_label = QLabel()
        self.value_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 18px; font-weight: 600;")
        layout.addWidget(self.value_label)

        # Progress bar frame
        self.progress_frame = QFrame()
        self.progress_frame.setFixedHeight(8)
        self.progress_frame.setStyleSheet(f"""
            background-color: {COLORS['bg_light']};
            border-radius: 4px;
        """)

        self.progress_bar = QFrame(self.progress_frame)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet(f"""
            background-color: {COLORS['primary']};
            border-radius: 4px;
        """)

        layout.addWidget(self.progress_frame)

        # Percentage label
        self.percentage_label = QLabel()
        self.percentage_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(self.percentage_label)

        self.set_values(used, total)
        layout.addStretch()

    def set_values(self, used: float, total: float):
        """Update resource values"""
        if total > 0:
            percentage = (used / total) * 100
        else:
            percentage = 0

        self.value_label.setText(f"{used:.1f} / {total:.1f} {self._unit}")
        self.percentage_label.setText(f"{percentage:.1f}% used")

        # Update progress bar width
        progress_width = int((percentage / 100) * self.progress_frame.width())
        self.progress_bar.setFixedWidth(max(0, progress_width))

        # Change color based on usage
        if percentage > 90:
            color = COLORS["danger"]
        elif percentage > 70:
            color = COLORS["warning"]
        else:
            color = COLORS["primary"]

        self.progress_bar.setStyleSheet(f"""
            background-color: {color};
            border-radius: 4px;
        """)

    def resizeEvent(self, event):
        """Handle resize to update progress bar"""
        super().resizeEvent(event)
        # Trigger a values update to recalculate progress bar width
        current_text = self.value_label.text()
        if current_text and " / " in current_text:
            try:
                parts = current_text.replace(self._unit, "").strip().split(" / ")
                used = float(parts[0])
                total = float(parts[1])
                self.set_values(used, total)
            except (ValueError, IndexError):
                pass
