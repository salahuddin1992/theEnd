"""
Report Generator - مولد التقارير
==================================

Advanced report generation system.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReportType(str, Enum):
    """نوع التقرير"""
    CLUSTER_OVERVIEW = "cluster_overview"
    JOB_SUMMARY = "job_summary"
    WORKER_PERFORMANCE = "worker_performance"
    RESOURCE_UTILIZATION = "resource_utilization"
    TENANT_USAGE = "tenant_usage"
    COST_ANALYSIS = "cost_analysis"
    ERROR_ANALYSIS = "error_analysis"
    SLA_COMPLIANCE = "sla_compliance"
    CUSTOM = "custom"


class ReportFormat(str, Enum):
    """تنسيق التقرير"""
    JSON = "json"
    HTML = "html"
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"


class ReportStatus(str, Enum):
    """حالة التقرير"""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """قسم التقرير"""
    title: str
    content: Any
    section_type: str = "text"  # text, table, chart, metric
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Report:
    """
    التقرير
    Report
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    report_type: ReportType = ReportType.CUSTOM
    status: ReportStatus = ReportStatus.PENDING

    # Time range
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime = field(default_factory=datetime.utcnow)

    # Content
    title: str = ""
    description: str = ""
    sections: List[ReportSection] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    generated_at: Optional[datetime] = None
    generation_time_ms: float = 0.0
    created_by: Optional[str] = None
    tenant_id: Optional[str] = None

    # Output
    format: ReportFormat = ReportFormat.JSON
    output_path: Optional[str] = None
    output_size_bytes: int = 0

    def add_section(
        self,
        title: str,
        content: Any,
        section_type: str = "text",
    ) -> None:
        """إضافة قسم"""
        self.sections.append(ReportSection(
            title=title,
            content=content,
            section_type=section_type,
        ))

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس"""
        return {
            "id": self.id,
            "name": self.name,
            "reportType": self.report_type.value,
            "status": self.status.value,
            "timeRange": {
                "start": self.start_time.isoformat(),
                "end": self.end_time.isoformat(),
            },
            "title": self.title,
            "description": self.description,
            "sections": [
                {
                    "title": s.title,
                    "content": s.content,
                    "type": s.section_type,
                }
                for s in self.sections
            ],
            "summary": self.summary,
            "createdAt": self.created_at.isoformat(),
            "generatedAt": self.generated_at.isoformat() if self.generated_at else None,
            "generationTimeMs": self.generation_time_ms,
        }

    def to_json(self, indent: int = 2) -> str:
        """تحويل لـ JSON"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)

    def to_html(self) -> str:
        """تحويل لـ HTML"""
        html = f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .report-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .report-header h1 {{
            margin: 0 0 10px 0;
        }}
        .section {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        .metric {{
            display: inline-block;
            background: #f0f0f0;
            padding: 15px 25px;
            border-radius: 8px;
            margin: 5px;
            text-align: center;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: right;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #667eea;
            color: white;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .footer {{
            text-align: center;
            color: #666;
            padding: 20px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="report-header">
        <h1>{self.title}</h1>
        <p>{self.description}</p>
        <small>الفترة: {self.start_time.strftime('%Y-%m-%d')} - {self.end_time.strftime('%Y-%m-%d')}</small>
    </div>
"""
        # Add sections
        for section in self.sections:
            html += f'<div class="section">\n<h2>{section.title}</h2>\n'

            if section.section_type == "metric":
                html += '<div class="metrics">\n'
                if isinstance(section.content, dict):
                    for key, value in section.content.items():
                        html += f'''
                        <div class="metric">
                            <div class="metric-value">{value}</div>
                            <div class="metric-label">{key}</div>
                        </div>
'''
                html += '</div>\n'

            elif section.section_type == "table":
                if isinstance(section.content, list) and section.content:
                    html += '<table>\n<thead><tr>\n'
                    for key in section.content[0].keys():
                        html += f'<th>{key}</th>\n'
                    html += '</tr></thead>\n<tbody>\n'
                    for row in section.content:
                        html += '<tr>\n'
                        for value in row.values():
                            html += f'<td>{value}</td>\n'
                        html += '</tr>\n'
                    html += '</tbody></table>\n'

            else:
                html += f'<p>{section.content}</p>\n'

            html += '</div>\n'

        # Summary
        if self.summary:
            html += '<div class="section">\n<h2>ملخص</h2>\n<div class="metrics">\n'
            for key, value in self.summary.items():
                html += f'''
                <div class="metric">
                    <div class="metric-value">{value}</div>
                    <div class="metric-label">{key}</div>
                </div>
'''
            html += '</div>\n</div>\n'

        html += f'''
    <div class="footer">
        تم إنشاؤه في {self.generated_at.strftime('%Y-%m-%d %H:%M:%S') if self.generated_at else 'N/A'} | NebulaCompute
    </div>
</body>
</html>
'''
        return html


class ReportGenerator:
    """
    مولد التقارير
    Report Generator

    يولد تقارير متنوعة عن الكلاستر.
    Generates various cluster reports.
    """

    def __init__(self, data_source: Any = None):
        self.data_source = data_source
        self._report_builders: Dict[ReportType, Callable] = {}
        self._register_default_builders()

    def _register_default_builders(self) -> None:
        """تسجيل بناة التقارير الافتراضية"""
        self._report_builders[ReportType.CLUSTER_OVERVIEW] = self._build_cluster_overview
        self._report_builders[ReportType.JOB_SUMMARY] = self._build_job_summary
        self._report_builders[ReportType.WORKER_PERFORMANCE] = self._build_worker_performance
        self._report_builders[ReportType.RESOURCE_UTILIZATION] = self._build_resource_utilization
        self._report_builders[ReportType.TENANT_USAGE] = self._build_tenant_usage
        self._report_builders[ReportType.COST_ANALYSIS] = self._build_cost_analysis

    def register_builder(
        self,
        report_type: ReportType,
        builder: Callable,
    ) -> None:
        """تسجيل باني تقرير"""
        self._report_builders[report_type] = builder

    async def generate(
        self,
        report_type: ReportType,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tenant_id: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Report:
        """
        توليد تقرير
        Generate report
        """
        start = datetime.utcnow()

        # Default time range: last 7 days
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(days=7)

        report = Report(
            name=f"{report_type.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            report_type=report_type,
            start_time=start_time,
            end_time=end_time,
            tenant_id=tenant_id,
            status=ReportStatus.GENERATING,
        )

        try:
            builder = self._report_builders.get(report_type)
            if not builder:
                raise ValueError(f"No builder for report type: {report_type}")

            await builder(report, options or {})

            report.status = ReportStatus.COMPLETED
            report.generated_at = datetime.utcnow()
            report.generation_time_ms = (datetime.utcnow() - start).total_seconds() * 1000

            logger.info(f"Generated report: {report.name} in {report.generation_time_ms:.2f}ms")

        except Exception as e:
            report.status = ReportStatus.FAILED
            report.summary["error"] = str(e)
            logger.error(f"Failed to generate report: {e}")

        return report

    async def _build_cluster_overview(
        self,
        report: Report,
        options: Dict[str, Any],
    ) -> None:
        """بناء تقرير نظرة عامة على الكلاستر"""
        report.title = "نظرة عامة على الكلاستر"
        report.description = f"تقرير شامل عن حالة الكلاستر للفترة من {report.start_time.strftime('%Y-%m-%d')} إلى {report.end_time.strftime('%Y-%m-%d')}"

        # Get data from source
        cluster_stats = await self._get_cluster_stats()

        # Add metrics section
        report.add_section(
            "إحصائيات الكلاستر",
            {
                "إجمالي العمال": cluster_stats.get("total_workers", 0),
                "العمال النشطين": cluster_stats.get("online_workers", 0),
                "إجمالي المهام": cluster_stats.get("total_jobs", 0),
                "المهام الجارية": cluster_stats.get("running_jobs", 0),
                "نسبة النجاح": f"{cluster_stats.get('success_rate', 0):.1f}%",
            },
            section_type="metric",
        )

        # Add resource utilization
        report.add_section(
            "استخدام الموارد",
            {
                "CPU المستخدم": f"{cluster_stats.get('cpu_utilization', 0):.1f}%",
                "الذاكرة المستخدمة": f"{cluster_stats.get('memory_utilization', 0):.1f}%",
                "GPU المستخدم": f"{cluster_stats.get('gpu_utilization', 0):.1f}%",
            },
            section_type="metric",
        )

        # Summary
        report.summary = {
            "صحة الكلاستر": "جيدة" if cluster_stats.get("health", True) else "تحتاج مراجعة",
            "وقت التشغيل": f"{cluster_stats.get('uptime_hours', 0):.1f} ساعة",
            "المهام المكتملة": cluster_stats.get("completed_jobs", 0),
        }

    async def _build_job_summary(
        self,
        report: Report,
        options: Dict[str, Any],
    ) -> None:
        """بناء تقرير ملخص المهام"""
        report.title = "ملخص المهام"
        report.description = "تقرير تفصيلي عن المهام المنفذة"

        job_stats = await self._get_job_stats()

        report.add_section(
            "إحصائيات المهام",
            {
                "إجمالي المهام": job_stats.get("total", 0),
                "مكتملة": job_stats.get("completed", 0),
                "فاشلة": job_stats.get("failed", 0),
                "ملغاة": job_stats.get("cancelled", 0),
            },
            section_type="metric",
        )

        report.add_section(
            "أداء المهام",
            {
                "متوسط وقت التنفيذ": f"{job_stats.get('avg_duration', 0):.1f} ثانية",
                "أقصى وقت": f"{job_stats.get('max_duration', 0):.1f} ثانية",
                "معدل المهام/ساعة": f"{job_stats.get('jobs_per_hour', 0):.1f}",
            },
            section_type="metric",
        )

        report.summary = {
            "نسبة النجاح": f"{job_stats.get('success_rate', 0):.1f}%",
            "إجمالي وقت الحوسبة": f"{job_stats.get('total_compute_hours', 0):.1f} ساعة",
        }

    async def _build_worker_performance(
        self,
        report: Report,
        options: Dict[str, Any],
    ) -> None:
        """بناء تقرير أداء العمال"""
        report.title = "أداء العمال"
        report.description = "تحليل أداء عمال الكلاستر"

        workers = await self._get_worker_stats()

        report.add_section(
            "ملخص العمال",
            {
                "إجمالي العمال": len(workers),
                "متصلين": sum(1 for w in workers if w.get("status") == "online"),
                "مشغولين": sum(1 for w in workers if w.get("status") == "busy"),
            },
            section_type="metric",
        )

        # Top workers table
        top_workers = sorted(workers, key=lambda w: w.get("jobs_completed", 0), reverse=True)[:10]
        report.add_section(
            "أفضل 10 عمال",
            [
                {
                    "الاسم": w.get("name", "N/A"),
                    "المهام المكتملة": w.get("jobs_completed", 0),
                    "نسبة النجاح": f"{w.get('success_rate', 0):.1f}%",
                    "استخدام CPU": f"{w.get('cpu_usage', 0):.1f}%",
                }
                for w in top_workers
            ],
            section_type="table",
        )

        report.summary = {
            "متوسط استخدام CPU": f"{sum(w.get('cpu_usage', 0) for w in workers) / len(workers) if workers else 0:.1f}%",
            "إجمالي المهام المكتملة": sum(w.get("jobs_completed", 0) for w in workers),
        }

    async def _build_resource_utilization(
        self,
        report: Report,
        options: Dict[str, Any],
    ) -> None:
        """بناء تقرير استخدام الموارد"""
        report.title = "استخدام الموارد"
        report.description = "تحليل استهلاك موارد الكلاستر"

        resources = await self._get_resource_stats()

        report.add_section(
            "ملخص الموارد",
            {
                "إجمالي CPU": resources.get("total_cpu", 0),
                "CPU المستخدم": resources.get("used_cpu", 0),
                "إجمالي الذاكرة": f"{resources.get('total_memory_gb', 0):.1f} GB",
                "الذاكرة المستخدمة": f"{resources.get('used_memory_gb', 0):.1f} GB",
                "إجمالي GPU": resources.get("total_gpu", 0),
                "GPU المستخدم": resources.get("used_gpu", 0),
            },
            section_type="metric",
        )

        report.summary = {
            "كفاءة CPU": f"{resources.get('cpu_efficiency', 0):.1f}%",
            "كفاءة الذاكرة": f"{resources.get('memory_efficiency', 0):.1f}%",
        }

    async def _build_tenant_usage(
        self,
        report: Report,
        options: Dict[str, Any],
    ) -> None:
        """بناء تقرير استخدام المستأجرين"""
        report.title = "استخدام المستأجرين"
        report.description = "تقرير استخدام الموارد لكل مستأجر"

        tenants = await self._get_tenant_stats()

        report.add_section(
            "ملخص المستأجرين",
            {
                "إجمالي المستأجرين": len(tenants),
                "نشطين": sum(1 for t in tenants if t.get("status") == "active"),
            },
            section_type="metric",
        )

        report.add_section(
            "استخدام المستأجرين",
            [
                {
                    "المستأجر": t.get("name", "N/A"),
                    "المهام": t.get("total_jobs", 0),
                    "CPU": f"{t.get('cpu_used', 0):.1f}",
                    "الذاكرة": f"{t.get('memory_used_gb', 0):.1f} GB",
                    "التكلفة": f"${t.get('cost', 0):.2f}",
                }
                for t in tenants
            ],
            section_type="table",
        )

        report.summary = {
            "إجمالي المهام": sum(t.get("total_jobs", 0) for t in tenants),
            "إجمالي التكلفة": f"${sum(t.get('cost', 0) for t in tenants):.2f}",
        }

    async def _build_cost_analysis(
        self,
        report: Report,
        options: Dict[str, Any],
    ) -> None:
        """بناء تقرير تحليل التكلفة"""
        report.title = "تحليل التكلفة"
        report.description = "تحليل تكاليف استخدام الكلاستر"

        costs = await self._get_cost_stats()

        report.add_section(
            "ملخص التكاليف",
            {
                "إجمالي التكلفة": f"${costs.get('total_cost', 0):.2f}",
                "تكلفة CPU": f"${costs.get('cpu_cost', 0):.2f}",
                "تكلفة الذاكرة": f"${costs.get('memory_cost', 0):.2f}",
                "تكلفة GPU": f"${costs.get('gpu_cost', 0):.2f}",
            },
            section_type="metric",
        )

        report.summary = {
            "متوسط التكلفة اليومي": f"${costs.get('daily_avg', 0):.2f}",
            "التكلفة المتوقعة للشهر": f"${costs.get('monthly_forecast', 0):.2f}",
        }

    # Helper methods to get data
    async def _get_cluster_stats(self) -> Dict[str, Any]:
        if self.data_source:
            return await self.data_source.get_cluster_stats()
        return {
            "total_workers": 10,
            "online_workers": 8,
            "total_jobs": 1500,
            "running_jobs": 25,
            "completed_jobs": 1400,
            "failed_jobs": 75,
            "success_rate": 94.9,
            "cpu_utilization": 65.5,
            "memory_utilization": 72.3,
            "gpu_utilization": 45.0,
            "health": True,
            "uptime_hours": 720,
        }

    async def _get_job_stats(self) -> Dict[str, Any]:
        if self.data_source:
            return await self.data_source.get_job_stats()
        return {
            "total": 1500,
            "completed": 1400,
            "failed": 75,
            "cancelled": 25,
            "avg_duration": 45.5,
            "max_duration": 3600,
            "jobs_per_hour": 62.5,
            "success_rate": 94.9,
            "total_compute_hours": 1125,
        }

    async def _get_worker_stats(self) -> List[Dict[str, Any]]:
        if self.data_source:
            return await self.data_source.get_worker_stats()
        return [
            {"name": f"worker-{i}", "status": "online", "jobs_completed": 150 - i * 10, "success_rate": 95 - i, "cpu_usage": 60 + i * 3}
            for i in range(10)
        ]

    async def _get_resource_stats(self) -> Dict[str, Any]:
        if self.data_source:
            return await self.data_source.get_resource_stats()
        return {
            "total_cpu": 80,
            "used_cpu": 52,
            "total_memory_gb": 320,
            "used_memory_gb": 231,
            "total_gpu": 8,
            "used_gpu": 4,
            "cpu_efficiency": 65,
            "memory_efficiency": 72.2,
        }

    async def _get_tenant_stats(self) -> List[Dict[str, Any]]:
        if self.data_source:
            return await self.data_source.get_tenant_stats()
        return [
            {"name": f"tenant-{i}", "status": "active", "total_jobs": 300 - i * 50, "cpu_used": 20 - i * 2, "memory_used_gb": 64 - i * 8, "cost": 250 - i * 30}
            for i in range(5)
        ]

    async def _get_cost_stats(self) -> Dict[str, Any]:
        if self.data_source:
            return await self.data_source.get_cost_stats()
        return {
            "total_cost": 1250.50,
            "cpu_cost": 520.00,
            "memory_cost": 380.50,
            "gpu_cost": 350.00,
            "daily_avg": 41.68,
            "monthly_forecast": 1250.50,
        }
