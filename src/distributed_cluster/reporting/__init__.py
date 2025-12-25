"""
Reporting & Analytics Module - وحدة التقارير والتحليلات
==========================================================

Advanced reporting and analytics for NebulaCompute.
تقارير وتحليلات متقدمة لنظام الحوسبة الموزعة.

Features | الميزات:
- Real-time dashboards
- Historical reports
- Performance analytics
- Cost analysis
- Trend prediction
- Custom report builder
- Export to PDF/Excel/CSV

Author: NebulaCompute Team
License: MIT
"""

from distributed_cluster.reporting.analytics import (
    AnalyticsEngine,
    MetricAggregator,
    TrendAnalyzer,
)
from distributed_cluster.reporting.reports import (
    ReportGenerator,
    ReportType,
    Report,
)
from distributed_cluster.reporting.dashboards import (
    DashboardManager,
    Dashboard,
    Widget,
)
from distributed_cluster.reporting.exporters import (
    ReportExporter,
    PDFExporter,
    ExcelExporter,
    CSVExporter,
)

__all__ = [
    # Analytics
    "AnalyticsEngine",
    "MetricAggregator",
    "TrendAnalyzer",
    # Reports
    "ReportGenerator",
    "ReportType",
    "Report",
    # Dashboards
    "DashboardManager",
    "Dashboard",
    "Widget",
    # Exporters
    "ReportExporter",
    "PDFExporter",
    "ExcelExporter",
    "CSVExporter",
]
