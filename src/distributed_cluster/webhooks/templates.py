"""
Payload Templates - قوالب البيانات
==================================

Template Engine for Webhooks
----------------------------

This module provides payload templates for webhooks.

يوفر هذا الملف قوالب البيانات للـ webhooks.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class PayloadTemplate:
    """
    قالب البيانات
    Payload template
    """
    name: str
    template: dict[str, Any]
    description: str = ""
    variables: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "template": self.template,
            "variables": self.variables,
        }


class TemplateEngine:
    """
    محرك القوالب
    Template Engine

    يوفر معالجة قوالب البيانات مع استبدال المتغيرات.
    Provides template processing with variable substitution.
    """

    # Variable pattern: {{variable}} or {{variable.path}}
    VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\}\}")

    # Filter pattern: {{variable|filter}} or {{variable|filter:arg}}
    FILTER_PATTERN = re.compile(
        r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\|\s*([a-zA-Z_]+)(?::([^}]+))?\s*\}\}"
    )

    def __init__(self):
        """تهيئة المحرك"""
        self._templates: dict[str, PayloadTemplate] = {}
        self._filters: dict[str, Callable] = {}
        self._functions: dict[str, Callable] = {}

        # Register default filters
        self._register_default_filters()
        self._register_default_functions()

    def _register_default_filters(self) -> None:
        """تسجيل الفلاتر الافتراضية"""
        self._filters["upper"] = lambda x: str(x).upper()
        self._filters["lower"] = lambda x: str(x).lower()
        self._filters["title"] = lambda x: str(x).title()
        self._filters["strip"] = lambda x: str(x).strip()
        self._filters["default"] = lambda x, d="": x if x else d
        self._filters["truncate"] = lambda x, limit=100: str(x)[:int(limit)]
        self._filters["json"] = lambda x: json.dumps(x)
        self._filters["date"] = lambda x, f="%Y-%m-%d": (
            x.strftime(f) if isinstance(x, datetime) else str(x)
        )
        self._filters["time"] = lambda x, f="%H:%M:%S": (
            x.strftime(f) if isinstance(x, datetime) else str(x)
        )
        self._filters["datetime"] = lambda x, f="%Y-%m-%d %H:%M:%S": (
            x.strftime(f) if isinstance(x, datetime) else str(x)
        )
        self._filters["int"] = lambda x: int(float(x)) if x else 0
        self._filters["float"] = lambda x: float(x) if x else 0.0
        self._filters["round"] = lambda x, d=2: round(float(x), int(d))
        self._filters["abs"] = lambda x: abs(float(x)) if x else 0
        self._filters["len"] = lambda x: len(x) if x else 0
        self._filters["first"] = lambda x: x[0] if x else None
        self._filters["last"] = lambda x: x[-1] if x else None
        self._filters["join"] = lambda x, s=", ": s.join(str(i) for i in x) if x else ""
        self._filters["split"] = lambda x, s=",": str(x).split(s) if x else []

    def _register_default_functions(self) -> None:
        """تسجيل الدوال الافتراضية"""
        self._functions["now"] = lambda: datetime.now(timezone.utc)
        self._functions["today"] = lambda: datetime.now(timezone.utc).date()
        self._functions["timestamp"] = lambda: datetime.now(timezone.utc).isoformat()
        self._functions["uuid"] = lambda: str(__import__("uuid").uuid4())

    # =========================================================================
    # Registration
    # =========================================================================

    def register_template(self, template: PayloadTemplate) -> None:
        """تسجيل قالب"""
        self._templates[template.name] = template
        logger.debug(f"Registered template: {template.name}")

    def unregister_template(self, name: str) -> None:
        """إلغاء تسجيل قالب"""
        self._templates.pop(name, None)

    def register_filter(
        self,
        name: str,
        filter_fn: Callable,
    ) -> None:
        """تسجيل فلتر"""
        self._filters[name] = filter_fn

    def register_function(
        self,
        name: str,
        fn: Callable,
    ) -> None:
        """تسجيل دالة"""
        self._functions[name] = fn

    def get_template(self, name: str) -> Optional[PayloadTemplate]:
        """الحصول على قالب"""
        return self._templates.get(name)

    # =========================================================================
    # Rendering
    # =========================================================================

    def render(
        self,
        template: dict[str, Any] | str,
        context: dict[str, Any],
    ) -> dict[str, Any] | str:
        """
        تقديم القالب

        Args:
            template: القالب (dict أو str)
            context: السياق مع المتغيرات

        Returns:
            القالب المُقدَّم
        """
        if isinstance(template, str):
            return self._render_string(template, context)
        elif isinstance(template, dict):
            return self._render_dict(template, context)
        elif isinstance(template, list):
            return [self.render(item, context) for item in template]
        else:
            return template

    def render_template(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        تقديم قالب مسجل

        Args:
            template_name: اسم القالب
            context: السياق

        Returns:
            القالب المُقدَّم
        """
        template = self._templates.get(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_name}")

        return self.render(template.template, context)

    def _render_dict(
        self,
        template: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """تقديم قاموس"""
        result = {}

        for key, value in template.items():
            # Render key
            rendered_key = self._render_string(key, context)

            # Render value
            if isinstance(value, str):
                result[rendered_key] = self._render_string(value, context)
            elif isinstance(value, dict):
                result[rendered_key] = self._render_dict(value, context)
            elif isinstance(value, list):
                result[rendered_key] = [
                    self.render(item, context) for item in value
                ]
            else:
                result[rendered_key] = value

        return result

    def _render_string(
        self,
        template: str,
        context: dict[str, Any],
    ) -> str:
        """تقديم نص"""
        # First, apply filters
        def replace_filter(match: re.Match) -> str:
            var_path = match.group(1)
            filter_name = match.group(2)
            filter_arg = match.group(3)

            # Get value
            value = self._get_value(var_path, context)

            # Apply filter
            filter_fn = self._filters.get(filter_name)
            if filter_fn:
                try:
                    if filter_arg:
                        value = filter_fn(value, filter_arg)
                    else:
                        value = filter_fn(value)
                except Exception as e:
                    logger.warning(f"Filter error: {filter_name}: {e}")

            return str(value) if value is not None else ""

        result = self.FILTER_PATTERN.sub(replace_filter, template)

        # Then, replace simple variables
        def replace_variable(match: re.Match) -> str:
            var_path = match.group(1)

            # Check if it's a function
            if var_path in self._functions:
                value = self._functions[var_path]()
            else:
                value = self._get_value(var_path, context)

            return str(value) if value is not None else ""

        result = self.VARIABLE_PATTERN.sub(replace_variable, result)

        return result

    def _get_value(
        self,
        path: str,
        context: dict[str, Any],
    ) -> Any:
        """الحصول على قيمة من السياق"""
        parts = path.split(".")
        value = context

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                return None

            if value is None:
                return None

        return value

    # =========================================================================
    # Validation
    # =========================================================================

    def validate_template(
        self,
        template: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """
        التحقق من صحة القالب

        Returns:
            (صالح, قائمة الأخطاء)
        """
        errors = []
        variables = self.extract_variables(template)

        # Check for invalid variable names
        for var in variables:
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_\.]*$", var):
                errors.append(f"Invalid variable name: {var}")

        return len(errors) == 0, errors

    def extract_variables(
        self,
        template: dict[str, Any] | str,
    ) -> list[str]:
        """استخراج المتغيرات من القالب"""
        variables = set()

        if isinstance(template, str):
            # Find all variables
            for match in self.VARIABLE_PATTERN.finditer(template):
                variables.add(match.group(1))
            for match in self.FILTER_PATTERN.finditer(template):
                variables.add(match.group(1))

        elif isinstance(template, dict):
            for key, value in template.items():
                variables.update(self.extract_variables(key))
                variables.update(self.extract_variables(value))

        elif isinstance(template, list):
            for item in template:
                variables.update(self.extract_variables(item))

        return list(variables)


# =============================================================================
# Predefined Templates
# =============================================================================

def create_simple_template() -> PayloadTemplate:
    """إنشاء قالب بسيط"""
    return PayloadTemplate(
        name="simple",
        description="Simple event notification",
        template={
            "event": "{{event_type}}",
            "message": "{{message}}",
            "timestamp": "{{timestamp}}",
            "source": "{{source}}",
        },
        variables=["event_type", "message", "timestamp", "source"],
    )


def create_detailed_template() -> PayloadTemplate:
    """إنشاء قالب مفصل"""
    return PayloadTemplate(
        name="detailed",
        description="Detailed event notification",
        template={
            "event": {
                "id": "{{event_id}}",
                "type": "{{event_type}}",
                "timestamp": "{{timestamp}}",
            },
            "source": "{{source}}",
            "data": "{{data|json}}",
            "metadata": {
                "version": "{{version}}",
                "cluster": "{{cluster_name|default:unknown}}",
            },
        },
        variables=["event_id", "event_type", "timestamp", "source", "data", "version", "cluster_name"],
    )


def create_alert_template() -> PayloadTemplate:
    """إنشاء قالب تنبيه"""
    return PayloadTemplate(
        name="alert",
        description="Alert notification template",
        template={
            "alert": {
                "name": "{{alert_name}}",
                "severity": "{{severity|upper}}",
                "message": "{{message}}",
                "fired_at": "{{fired_at|datetime}}",
            },
            "labels": "{{labels|json}}",
            "annotations": "{{annotations|json}}",
            "value": "{{value|round:2}}",
        },
        variables=["alert_name", "severity", "message", "fired_at", "labels", "annotations", "value"],
    )


def create_job_template() -> PayloadTemplate:
    """إنشاء قالب مهمة"""
    return PayloadTemplate(
        name="job",
        description="Job event notification",
        template={
            "job": {
                "id": "{{job_id}}",
                "name": "{{job_name}}",
                "status": "{{status}}",
                "worker": "{{worker_id}}",
            },
            "duration_seconds": "{{duration|round:2}}",
            "result": "{{result}}",
            "error": "{{error|default:None}}",
        },
        variables=["job_id", "job_name", "status", "worker_id", "duration", "result", "error"],
    )
