"""
Dashboard Manager - مدير لوحات التحكم
=======================================

Interactive dashboard management.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class WidgetType(str, Enum):
    """نوع الأداة"""
    METRIC = "metric"
    CHART = "chart"
    TABLE = "table"
    TEXT = "text"
    GAUGE = "gauge"
    HEATMAP = "heatmap"
    LIST = "list"
    STATUS = "status"


class ChartType(str, Enum):
    """نوع الرسم البياني"""
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    AREA = "area"
    SCATTER = "scatter"
    DONUT = "donut"


@dataclass
class WidgetConfig:
    """تكوين الأداة"""
    data_source: str = ""
    refresh_interval_seconds: int = 30
    query: Optional[str] = None
    chart_type: Optional[ChartType] = None
    colors: List[str] = field(default_factory=list)
    thresholds: Dict[str, float] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Widget:
    """
    أداة لوحة التحكم
    Dashboard Widget
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    widget_type: WidgetType = WidgetType.METRIC
    config: WidgetConfig = field(default_factory=WidgetConfig)

    # Layout
    x: int = 0
    y: int = 0
    width: int = 4
    height: int = 3

    # Data
    data: Any = None
    last_updated: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس"""
        return {
            "id": self.id,
            "title": self.title,
            "type": self.widget_type.value,
            "config": {
                "dataSource": self.config.data_source,
                "refreshInterval": self.config.refresh_interval_seconds,
                "query": self.config.query,
                "chartType": self.config.chart_type.value if self.config.chart_type else None,
                "options": self.config.options,
            },
            "layout": {
                "x": self.x,
                "y": self.y,
                "w": self.width,
                "h": self.height,
            },
            "data": self.data,
            "lastUpdated": self.last_updated.isoformat() if self.last_updated else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Widget":
        """إنشاء من قاموس"""
        layout = data.get("layout", {})
        config_data = data.get("config", {})

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            title=data.get("title", ""),
            widget_type=WidgetType(data.get("type", "metric")),
            config=WidgetConfig(
                data_source=config_data.get("dataSource", ""),
                refresh_interval_seconds=config_data.get("refreshInterval", 30),
                query=config_data.get("query"),
                chart_type=ChartType(config_data["chartType"]) if config_data.get("chartType") else None,
                options=config_data.get("options", {}),
            ),
            x=layout.get("x", 0),
            y=layout.get("y", 0),
            width=layout.get("w", 4),
            height=layout.get("h", 3),
        )


@dataclass
class Dashboard:
    """
    لوحة التحكم
    Dashboard
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    widgets: List[Widget] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    tenant_id: Optional[str] = None

    # Settings
    is_default: bool = False
    is_public: bool = False
    auto_refresh: bool = True
    refresh_interval_seconds: int = 30
    grid_columns: int = 12

    # Tags
    tags: List[str] = field(default_factory=list)

    def add_widget(self, widget: Widget) -> None:
        """إضافة أداة"""
        self.widgets.append(widget)
        self.updated_at = datetime.utcnow()

    def remove_widget(self, widget_id: str) -> bool:
        """إزالة أداة"""
        for i, widget in enumerate(self.widgets):
            if widget.id == widget_id:
                del self.widgets[i]
                self.updated_at = datetime.utcnow()
                return True
        return False

    def get_widget(self, widget_id: str) -> Optional[Widget]:
        """الحصول على أداة"""
        for widget in self.widgets:
            if widget.id == widget_id:
                return widget
        return None

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "widgets": [w.to_dict() for w in self.widgets],
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            "createdBy": self.created_by,
            "isDefault": self.is_default,
            "isPublic": self.is_public,
            "autoRefresh": self.auto_refresh,
            "refreshInterval": self.refresh_interval_seconds,
            "gridColumns": self.grid_columns,
            "tags": self.tags,
        }

    def to_json(self, indent: int = 2) -> str:
        """تحويل لـ JSON"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Dashboard":
        """إنشاء من قاموس"""
        dashboard = cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            is_default=data.get("isDefault", False),
            is_public=data.get("isPublic", False),
            auto_refresh=data.get("autoRefresh", True),
            refresh_interval_seconds=data.get("refreshInterval", 30),
            grid_columns=data.get("gridColumns", 12),
            tags=data.get("tags", []),
        )

        for widget_data in data.get("widgets", []):
            dashboard.widgets.append(Widget.from_dict(widget_data))

        return dashboard


class DashboardManager:
    """
    مدير لوحات التحكم
    Dashboard Manager
    """

    def __init__(self, storage: Any = None):
        self.storage = storage
        self._dashboards: Dict[str, Dashboard] = {}
        self._default_dashboard_id: Optional[str] = None

    async def create_dashboard(
        self,
        name: str,
        description: str = "",
        created_by: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Dashboard:
        """إنشاء لوحة تحكم"""
        dashboard = Dashboard(
            name=name,
            description=description,
            created_by=created_by,
            tenant_id=tenant_id,
        )

        self._dashboards[dashboard.id] = dashboard

        if self.storage:
            await self.storage.save_dashboard(dashboard)

        return dashboard

    async def get_dashboard(self, dashboard_id: str) -> Optional[Dashboard]:
        """الحصول على لوحة تحكم"""
        return self._dashboards.get(dashboard_id)

    async def list_dashboards(
        self,
        tenant_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Dashboard]:
        """قائمة لوحات التحكم"""
        dashboards = list(self._dashboards.values())

        if tenant_id:
            dashboards = [d for d in dashboards if d.tenant_id == tenant_id or d.is_public]

        if tags:
            dashboards = [d for d in dashboards if any(t in d.tags for t in tags)]

        return dashboards

    async def update_dashboard(
        self,
        dashboard_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs,
    ) -> Optional[Dashboard]:
        """تحديث لوحة تحكم"""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return None

        if name:
            dashboard.name = name
        if description:
            dashboard.description = description
        for key, value in kwargs.items():
            if hasattr(dashboard, key):
                setattr(dashboard, key, value)

        dashboard.updated_at = datetime.utcnow()

        if self.storage:
            await self.storage.save_dashboard(dashboard)

        return dashboard

    async def delete_dashboard(self, dashboard_id: str) -> bool:
        """حذف لوحة تحكم"""
        if dashboard_id not in self._dashboards:
            return False

        del self._dashboards[dashboard_id]

        if self.storage:
            await self.storage.delete_dashboard(dashboard_id)

        return True

    async def add_widget(
        self,
        dashboard_id: str,
        widget: Widget,
    ) -> Optional[Dashboard]:
        """إضافة أداة للوحة"""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return None

        dashboard.add_widget(widget)

        if self.storage:
            await self.storage.save_dashboard(dashboard)

        return dashboard

    async def update_widget(
        self,
        dashboard_id: str,
        widget_id: str,
        **kwargs,
    ) -> Optional[Widget]:
        """تحديث أداة"""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return None

        widget = dashboard.get_widget(widget_id)
        if not widget:
            return None

        for key, value in kwargs.items():
            if hasattr(widget, key):
                setattr(widget, key, value)

        dashboard.updated_at = datetime.utcnow()

        if self.storage:
            await self.storage.save_dashboard(dashboard)

        return widget

    async def remove_widget(
        self,
        dashboard_id: str,
        widget_id: str,
    ) -> bool:
        """إزالة أداة"""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return False

        result = dashboard.remove_widget(widget_id)

        if result and self.storage:
            await self.storage.save_dashboard(dashboard)

        return result

    async def set_default(self, dashboard_id: str) -> bool:
        """تعيين لوحة افتراضية"""
        if dashboard_id not in self._dashboards:
            return False

        # Remove default from current
        if self._default_dashboard_id:
            current_default = self._dashboards.get(self._default_dashboard_id)
            if current_default:
                current_default.is_default = False

        # Set new default
        self._dashboards[dashboard_id].is_default = True
        self._default_dashboard_id = dashboard_id

        return True

    async def get_default(self) -> Optional[Dashboard]:
        """الحصول على اللوحة الافتراضية"""
        if self._default_dashboard_id:
            return self._dashboards.get(self._default_dashboard_id)
        return None

    def create_default_dashboards(self) -> None:
        """إنشاء لوحات افتراضية"""
        # Cluster Overview Dashboard
        cluster_dashboard = Dashboard(
            name="نظرة عامة على الكلاستر",
            description="لوحة تحكم شاملة لمراقبة الكلاستر",
            is_default=True,
            is_public=True,
        )

        cluster_dashboard.add_widget(Widget(
            title="إجمالي العمال",
            widget_type=WidgetType.METRIC,
            config=WidgetConfig(data_source="cluster.workers.total"),
            x=0, y=0, width=3, height=2,
        ))

        cluster_dashboard.add_widget(Widget(
            title="المهام الجارية",
            widget_type=WidgetType.METRIC,
            config=WidgetConfig(data_source="cluster.jobs.running"),
            x=3, y=0, width=3, height=2,
        ))

        cluster_dashboard.add_widget(Widget(
            title="استخدام CPU",
            widget_type=WidgetType.GAUGE,
            config=WidgetConfig(
                data_source="cluster.cpu.utilization",
                thresholds={"warning": 70, "critical": 90},
            ),
            x=6, y=0, width=3, height=2,
        ))

        cluster_dashboard.add_widget(Widget(
            title="استخدام الذاكرة",
            widget_type=WidgetType.GAUGE,
            config=WidgetConfig(
                data_source="cluster.memory.utilization",
                thresholds={"warning": 70, "critical": 90},
            ),
            x=9, y=0, width=3, height=2,
        ))

        cluster_dashboard.add_widget(Widget(
            title="المهام عبر الزمن",
            widget_type=WidgetType.CHART,
            config=WidgetConfig(
                data_source="cluster.jobs.timeline",
                chart_type=ChartType.LINE,
            ),
            x=0, y=2, width=8, height=4,
        ))

        cluster_dashboard.add_widget(Widget(
            title="حالة العمال",
            widget_type=WidgetType.CHART,
            config=WidgetConfig(
                data_source="cluster.workers.status",
                chart_type=ChartType.PIE,
            ),
            x=8, y=2, width=4, height=4,
        ))

        self._dashboards[cluster_dashboard.id] = cluster_dashboard
        self._default_dashboard_id = cluster_dashboard.id
