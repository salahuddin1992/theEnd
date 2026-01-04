"""
Report Exporters - مصدّرات التقارير
=====================================

Export reports to various formats.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import csv
import io
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional

from distributed_cluster.reporting.reports import Report

logger = logging.getLogger(__name__)


class ReportExporter(ABC):
    """
    مصدّر التقارير الأساسي
    Base Report Exporter
    """

    @abstractmethod
    async def export(self, report: Report, output_path: Optional[str] = None) -> bytes:
        """تصدير التقرير"""
        pass

    @abstractmethod
    def get_content_type(self) -> str:
        """الحصول على نوع المحتوى"""
        pass

    @abstractmethod
    def get_file_extension(self) -> str:
        """الحصول على امتداد الملف"""
        pass


class JSONExporter(ReportExporter):
    """مصدّر JSON"""

    async def export(self, report: Report, output_path: Optional[str] = None) -> bytes:
        """تصدير لـ JSON"""
        content = report.to_json(indent=2)
        data = content.encode("utf-8")

        if output_path:
            Path(output_path).write_bytes(data)

        return data

    def get_content_type(self) -> str:
        return "application/json"

    def get_file_extension(self) -> str:
        return ".json"


class CSVExporter(ReportExporter):
    """مصدّر CSV"""

    async def export(self, report: Report, output_path: Optional[str] = None) -> bytes:
        """تصدير لـ CSV"""
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header info
        writer.writerow(["Report", report.title])
        writer.writerow(["Generated", report.generated_at.isoformat() if report.generated_at else "N/A"])
        writer.writerow(["Period", f"{report.start_time.isoformat()} - {report.end_time.isoformat()}"])
        writer.writerow([])

        # Write sections
        for section in report.sections:
            writer.writerow([f"=== {section.title} ==="])

            if section.section_type == "metric" and isinstance(section.content, dict):
                for key, value in section.content.items():
                    writer.writerow([key, value])

            elif section.section_type == "table" and isinstance(section.content, list):
                if section.content:
                    # Header
                    writer.writerow(list(section.content[0].keys()))
                    # Rows
                    for row in section.content:
                        writer.writerow(list(row.values()))

            else:
                writer.writerow([str(section.content)])

            writer.writerow([])

        # Write summary
        if report.summary:
            writer.writerow(["=== Summary ==="])
            for key, value in report.summary.items():
                writer.writerow([key, value])

        data = output.getvalue().encode("utf-8-sig")  # BOM for Excel

        if output_path:
            Path(output_path).write_bytes(data)

        return data

    def get_content_type(self) -> str:
        return "text/csv"

    def get_file_extension(self) -> str:
        return ".csv"


class HTMLExporter(ReportExporter):
    """مصدّر HTML"""

    async def export(self, report: Report, output_path: Optional[str] = None) -> bytes:
        """تصدير لـ HTML"""
        content = report.to_html()
        data = content.encode("utf-8")

        if output_path:
            Path(output_path).write_bytes(data)

        return data

    def get_content_type(self) -> str:
        return "text/html"

    def get_file_extension(self) -> str:
        return ".html"


class ExcelExporter(ReportExporter):
    """مصدّر Excel"""

    async def export(self, report: Report, output_path: Optional[str] = None) -> bytes:
        """تصدير لـ Excel"""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill  # noqa: F401
            from openpyxl.utils import get_column_letter
        except ImportError:
            logger.warning("openpyxl not available, falling back to CSV")
            csv_exporter = CSVExporter()
            return await csv_exporter.export(report, output_path)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Report"

        # Styles
        header_font = Font(bold=True, size=14, color="FFFFFF")
        header_fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
        section_font = Font(bold=True, size=12)
        section_fill = PatternFill(start_color="E8E8E8", end_color="E8E8E8", fill_type="solid")

        row = 1

        # Title
        ws.cell(row=row, column=1, value=report.title)
        ws.cell(row=row, column=1).font = header_font
        ws.cell(row=row, column=1).fill = header_fill
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        row += 1

        # Metadata
        ws.cell(row=row, column=1, value="Generated:")
        ws.cell(row=row, column=2, value=report.generated_at.isoformat() if report.generated_at else "N/A")
        row += 1

        ws.cell(row=row, column=1, value="Period:")
        period_value = (
            f"{report.start_time.strftime('%Y-%m-%d')} - "
            f"{report.end_time.strftime('%Y-%m-%d')}"
        )
        ws.cell(row=row, column=2, value=period_value)
        row += 2

        # Sections
        for section in report.sections:
            # Section header
            ws.cell(row=row, column=1, value=section.title)
            ws.cell(row=row, column=1).font = section_font
            ws.cell(row=row, column=1).fill = section_fill
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
            row += 1

            if section.section_type == "metric" and isinstance(section.content, dict):
                for key, value in section.content.items():
                    ws.cell(row=row, column=1, value=key)
                    ws.cell(row=row, column=2, value=str(value))
                    row += 1

            elif section.section_type == "table" and isinstance(section.content, list):
                if section.content:
                    # Header
                    for col, key in enumerate(section.content[0].keys(), 1):
                        cell = ws.cell(row=row, column=col, value=key)
                        cell.font = Font(bold=True)
                    row += 1

                    # Data
                    for item in section.content:
                        for col, value in enumerate(item.values(), 1):
                            ws.cell(row=row, column=col, value=str(value))
                        row += 1

            else:
                ws.cell(row=row, column=1, value=str(section.content))
                row += 1

            row += 1

        # Summary
        if report.summary:
            ws.cell(row=row, column=1, value="Summary")
            ws.cell(row=row, column=1).font = section_font
            ws.cell(row=row, column=1).fill = section_fill
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
            row += 1

            for key, value in report.summary.items():
                ws.cell(row=row, column=1, value=key)
                ws.cell(row=row, column=2, value=str(value))
                row += 1

        # Auto-width columns
        for col in range(1, 7):
            ws.column_dimensions[get_column_letter(col)].width = 20

        # Save
        output = io.BytesIO()
        wb.save(output)
        data = output.getvalue()

        if output_path:
            Path(output_path).write_bytes(data)

        return data

    def get_content_type(self) -> str:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def get_file_extension(self) -> str:
        return ".xlsx"


class PDFExporter(ReportExporter):
    """مصدّر PDF"""

    async def export(self, report: Report, output_path: Optional[str] = None) -> bytes:
        """تصدير لـ PDF"""
        try:
            from weasyprint import CSS, HTML
        except ImportError:
            logger.warning("weasyprint not available, returning HTML")
            html_exporter = HTMLExporter()
            return await html_exporter.export(report, output_path)

        # Generate HTML first
        html_content = report.to_html()

        # Add PDF-specific CSS
        pdf_css = CSS(string="""
            @page {
                size: A4;
                margin: 2cm;
            }
            body {
                font-size: 12pt;
            }
            .report-header {
                page-break-after: avoid;
            }
            .section {
                page-break-inside: avoid;
            }
            table {
                page-break-inside: avoid;
            }
        """)

        # Generate PDF
        html = HTML(string=html_content)
        pdf_bytes = html.write_pdf(stylesheets=[pdf_css])

        if output_path:
            Path(output_path).write_bytes(pdf_bytes)

        return pdf_bytes

    def get_content_type(self) -> str:
        return "application/pdf"

    def get_file_extension(self) -> str:
        return ".pdf"


class ExporterFactory:
    """
    مصنع المصدّرات
    Exporter Factory
    """

    _exporters: Dict[str, type] = {
        "json": JSONExporter,
        "csv": CSVExporter,
        "html": HTMLExporter,
        "excel": ExcelExporter,
        "xlsx": ExcelExporter,
        "pdf": PDFExporter,
    }

    @classmethod
    def get_exporter(cls, format_name: str) -> ReportExporter:
        """الحصول على مصدّر"""
        format_lower = format_name.lower()
        if format_lower not in cls._exporters:
            raise ValueError(f"Unknown export format: {format_name}")
        return cls._exporters[format_lower]()

    @classmethod
    def register_exporter(cls, format_name: str, exporter_class: type) -> None:
        """تسجيل مصدّر"""
        cls._exporters[format_name.lower()] = exporter_class

    @classmethod
    def available_formats(cls) -> List[str]:
        """التنسيقات المتاحة"""
        return list(cls._exporters.keys())


async def export_report(
    report: Report,
    format_name: str,
    output_path: Optional[str] = None,
) -> bytes:
    """
    تصدير تقرير
    Export a report to the specified format
    """
    exporter = ExporterFactory.get_exporter(format_name)
    return await exporter.export(report, output_path)
