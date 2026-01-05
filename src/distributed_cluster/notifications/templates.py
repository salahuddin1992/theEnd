"""
Notification Templates - قوالب الإشعارات
=========================================

Template engine for notification content with multi-format support.
محرك قوالب لمحتوى الإشعارات مع دعم تنسيقات متعددة.

Features:
- HTML templates with responsive design
- Markdown templates
- Plain text templates
- RTL (Arabic) support
- Variable substitution
- Conditional blocks
- Loops for lists
- Built-in template library
"""

from __future__ import annotations

import html
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from distributed_cluster.notifications.channels import (
    Notification,
)

logger = logging.getLogger(__name__)


class TemplateFormat(str, Enum):
    """تنسيق القالب."""

    PLAIN = "plain"
    HTML = "html"
    MARKDOWN = "markdown"
    SLACK = "slack"
    DISCORD = "discord"
    TEAMS = "teams"


class TextDirection(str, Enum):
    """اتجاه النص."""

    LTR = "ltr"
    RTL = "rtl"
    AUTO = "auto"


@dataclass
class TemplateContext:
    """
    سياق القالب.

    Context for template rendering.
    """

    notification: Optional[Notification] = None
    variables: Dict[str, Any] = field(default_factory=dict)
    locale: str = "en"
    direction: TextDirection = TextDirection.AUTO
    timezone: str = "UTC"

    def get(self, key: str, default: Any = None) -> Any:
        """Get a variable from context."""
        # Check notification fields first
        if self.notification and hasattr(self.notification, key):
            return getattr(self.notification, key)

        # Check notification metadata
        if self.notification and key in self.notification.metadata:
            return self.notification.metadata[key]

        # Check notification data
        if self.notification and key in self.notification.data:
            return self.notification.data[key]

        # Check variables
        return self.variables.get(key, default)

    def update(self, **kwargs) -> "TemplateContext":
        """Update context with new variables."""
        self.variables.update(kwargs)
        return self


class NotificationTemplate(ABC):
    """
    قالب الإشعار الأساسي.

    Abstract Base Notification Template.
    """

    def __init__(
        self,
        name: str,
        template_format: TemplateFormat = TemplateFormat.PLAIN,
        direction: TextDirection = TextDirection.AUTO,
    ):
        self.name = name
        self.template_format = template_format
        self.direction = direction

    @abstractmethod
    def render(self, context: TemplateContext) -> str:
        """Render the template with context."""
        pass

    def render_notification(self, notification: Notification, **kwargs) -> str:
        """Convenience method to render with notification."""
        context = TemplateContext(notification=notification, variables=kwargs)
        return self.render(context)


class StringTemplate(NotificationTemplate):
    """
    قالب نصي بسيط.

    Simple String Template with Variable Substitution.

    Supports:
    - {{variable}} - Simple substitution
    - {{variable|default}} - With default value
    - {{variable|upper}} - With filter
    - {% if condition %}...{% endif %} - Conditionals
    - {% for item in items %}...{% endfor %} - Loops
    """

    VARIABLE_PATTERN = re.compile(r"\{\{(\w+)(?:\|(\w+))?\}\}")
    IF_PATTERN = re.compile(r"\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}", re.DOTALL)
    FOR_PATTERN = re.compile(r"\{%\s*for\s+(\w+)\s+in\s+(\w+)\s*%\}(.*?)\{%\s*endfor\s*%\}", re.DOTALL)

    def __init__(
        self,
        name: str,
        template: str,
        template_format: TemplateFormat = TemplateFormat.PLAIN,
        direction: TextDirection = TextDirection.AUTO,
    ):
        super().__init__(name, template_format, direction)
        self.template = template
        self._filters: Dict[str, Callable[[Any], str]] = {
            "upper": lambda x: str(x).upper(),
            "lower": lambda x: str(x).lower(),
            "title": lambda x: str(x).title(),
            "html": lambda x: html.escape(str(x)),
            "json": lambda x: json.dumps(x),
            "date": lambda x: x.strftime("%Y-%m-%d") if isinstance(x, datetime) else str(x),
            "time": lambda x: x.strftime("%H:%M:%S") if isinstance(x, datetime) else str(x),
            "datetime": lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if isinstance(x, datetime) else str(x),
        }

    def add_filter(self, name: str, func: Callable[[Any], str]) -> None:
        """Add a custom filter."""
        self._filters[name] = func

    def render(self, context: TemplateContext) -> str:
        """Render the template."""
        result = self.template

        # Process conditionals first
        result = self._process_conditionals(result, context)

        # Process loops
        result = self._process_loops(result, context)

        # Process variables
        result = self._process_variables(result, context)

        return result

    def _process_conditionals(self, template: str, context: TemplateContext) -> str:
        """Process {% if %} blocks."""

        def replace_if(match):
            condition = match.group(1)
            content = match.group(2)
            value = context.get(condition)
            if value:
                return content
            return ""

        return self.IF_PATTERN.sub(replace_if, template)

    def _process_loops(self, template: str, context: TemplateContext) -> str:
        """Process {% for %} blocks."""

        def replace_for(match):
            item_name = match.group(1)
            items_name = match.group(2)
            content = match.group(3)

            items = context.get(items_name, [])
            if not isinstance(items, (list, tuple)):
                return ""

            result = []
            for item in items:
                # Create temporary context with loop variable
                item_content = content
                item_content = item_content.replace(f"{{{{{item_name}}}}}", str(item))
                result.append(item_content)

            return "".join(result)

        return self.FOR_PATTERN.sub(replace_for, template)

    def _process_variables(self, template: str, context: TemplateContext) -> str:
        """Process {{variable}} substitutions."""

        def replace_var(match):
            var_name = match.group(1)
            filter_name = match.group(2)

            value = context.get(var_name, "")

            if filter_name and filter_name in self._filters:
                value = self._filters[filter_name](value)
            elif filter_name:
                # Use as default value
                if not value:
                    value = filter_name

            return str(value) if value is not None else ""

        return self.VARIABLE_PATTERN.sub(replace_var, template)


class HTMLTemplate(StringTemplate):
    """
    قالب HTML.

    HTML Template with Responsive Design Support.
    """

    def __init__(
        self,
        name: str,
        template: str,
        css: Optional[str] = None,
        direction: TextDirection = TextDirection.AUTO,
    ):
        super().__init__(name, template, TemplateFormat.HTML, direction)
        self.css = css or self._default_css()

    def _default_css(self) -> str:
        """Default responsive CSS."""
        return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }
        .container {
            max-width: 600px;
            margin: 20px auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            padding: 20px;
            text-align: center;
        }
        .content {
            padding: 20px;
        }
        .footer {
            padding: 15px 20px;
            background: #f8f9fa;
            text-align: center;
            font-size: 12px;
            color: #6c757d;
        }
        .priority-low { border-top: 4px solid #6c757d; }
        .priority-normal { border-top: 4px solid #17a2b8; }
        .priority-high { border-top: 4px solid #ffc107; }
        .priority-critical { border-top: 4px solid #dc3545; }
        .priority-emergency { border-top: 4px solid #7b1fa2; }
        @media (prefers-color-scheme: dark) {
            body { background: #1a1a1a; color: #e0e0e0; }
            .container { background: #2d2d2d; }
            .footer { background: #252525; }
        }
        """

    def render(self, context: TemplateContext) -> str:
        """Render HTML template with wrapper."""
        content = super().render(context)

        # Determine direction
        direction = self.direction
        if direction == TextDirection.AUTO:
            # Auto-detect based on locale or content
            if context.locale in ("ar", "he", "fa", "ur"):
                direction = TextDirection.RTL
            else:
                direction = TextDirection.LTR

        priority_class = ""
        if context.notification:
            priority_class = f"priority-{context.notification.priority.value}"

        return f"""
<!DOCTYPE html>
<html dir="{direction.value}" lang="{context.locale}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{self.css}</style>
</head>
<body>
    <div class="container {priority_class}">
        {content}
    </div>
</body>
</html>
        """.strip()


class MarkdownTemplate(StringTemplate):
    """
    قالب Markdown.

    Markdown Template with CommonMark Support.
    """

    def __init__(
        self,
        name: str,
        template: str,
        direction: TextDirection = TextDirection.AUTO,
    ):
        super().__init__(name, template, TemplateFormat.MARKDOWN, direction)


class RTLTemplate(StringTemplate):
    """
    قالب RTL.

    Right-to-Left Template for Arabic/Hebrew/Persian.
    """

    def __init__(
        self,
        name: str,
        template: str,
        template_format: TemplateFormat = TemplateFormat.PLAIN,
    ):
        super().__init__(name, template, template_format, TextDirection.RTL)


class TemplateEngine:
    """
    محرك القوالب.

    Template Engine with Template Registry.

    Usage:
        engine = TemplateEngine()

        # Register template
        engine.register(StringTemplate(
            name="alert",
            template="[{{priority|upper}}] {{title}}\n\n{{message}}",
        ))

        # Render
        content = engine.render("alert", notification)

        # Or use built-in templates
        content = engine.render("default_email", notification)
    """

    def __init__(self):
        self._templates: Dict[str, NotificationTemplate] = {}
        self._register_builtin_templates()

    def _register_builtin_templates(self) -> None:
        """Register built-in templates."""
        # Plain text templates
        self.register(
            StringTemplate(
                name="plain_simple",
                template="{{emoji}} {{title}}\n\n{{message}}",
            )
        )

        self.register(
            StringTemplate(
                name="plain_detailed",
                template="""{{emoji}} {{title}}
=====================================

{{message}}

-------------------------------------
Priority: {{priority}}
Category: {{category}}
Source: {{source}}
Time: {{timestamp|datetime}}
ID: {{notification_id}}
""",
            )
        )

        # Markdown templates
        self.register(
            MarkdownTemplate(
                name="markdown_simple",
                template="# {{emoji}} {{title}}\n\n{{message}}",
            )
        )

        self.register(
            MarkdownTemplate(
                name="markdown_detailed",
                template="""# {{emoji}} {{title}}

{{message}}

---

| Field | Value |
|-------|-------|
| Priority | `{{priority}}` |
| Category | `{{category}}` |
| Source | {{source}} |
| Time | {{timestamp|datetime}} |

_Notification ID: `{{notification_id}}`_
""",
            )
        )

        # Slack template
        self.register(
            StringTemplate(
                name="slack_block",
                template="""{
    "blocks": [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "{{emoji}} {{title}}", "emoji": true}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "{{message}}"}
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "*Priority:* {{priority}} | *Category:* {{category}}"}
            ]
        }
    ]
}""",
                template_format=TemplateFormat.SLACK,
            )
        )

        # HTML email template
        self.register(
            HTMLTemplate(
                name="email_modern",
                template="""
<div class="header" style="background: {{color}}; color: white;">
    <div style="font-size: 48px;">{{emoji}}</div>
    <h1>{{title}}</h1>
    <span style="background: rgba(255,255,255,0.2); padding: 5px 15px; border-radius: 20px;">
        {{priority|upper}} PRIORITY
    </span>
</div>
<div class="content">
    <p style="font-size: 16px; line-height: 1.8; background: #f8f9fa; padding: 20px; border-radius: 8px;">
        {{message}}
    </p>
    <table style="width: 100%; margin-top: 20px; font-size: 14px;">
        <tr><td><strong>Category:</strong></td><td>{{category}}</td></tr>
        <tr><td><strong>Source:</strong></td><td>{{source}}</td></tr>
        <tr><td><strong>Time:</strong></td><td>{{timestamp|datetime}}</td></tr>
    </table>
</div>
<div class="footer">
    Notification ID: {{notification_id}}<br>
    Powered by Dawood AI Assistant
</div>
""",
            )
        )

        # RTL Arabic template
        self.register(
            RTLTemplate(
                name="arabic_notification",
                template="""{{emoji}} {{title}}
=====================================

{{message}}

-------------------------------------
الأولوية: {{priority}}
التصنيف: {{category}}
المصدر: {{source}}
الوقت: {{timestamp|datetime}}
""",
            )
        )

        # Discord embed template
        self.register(
            StringTemplate(
                name="discord_embed",
                template="""{
    "embeds": [{
        "title": "{{emoji}} {{title}}",
        "description": "{{message}}",
        "color": {{color_int}},
        "fields": [
            {"name": "Priority", "value": "{{priority}}", "inline": true},
            {"name": "Category", "value": "{{category}}", "inline": true}
        ],
        "footer": {"text": "Dawood AI Assistant"},
        "timestamp": "{{timestamp}}"
    }]
}""",
                template_format=TemplateFormat.DISCORD,
            )
        )

    def register(self, template: NotificationTemplate) -> None:
        """Register a template."""
        self._templates[template.name] = template
        logger.debug(f"Registered template: {template.name}")

    def unregister(self, name: str) -> bool:
        """Unregister a template."""
        if name in self._templates:
            del self._templates[name]
            return True
        return False

    def get(self, name: str) -> Optional[NotificationTemplate]:
        """Get a template by name."""
        return self._templates.get(name)

    def list_templates(self) -> List[str]:
        """List all registered template names."""
        return list(self._templates.keys())

    def render(
        self,
        template_name: str,
        notification: Optional[Notification] = None,
        **kwargs,
    ) -> str:
        """
        Render a template.

        Args:
            template_name: Name of the template
            notification: Optional notification object
            **kwargs: Additional template variables

        Returns:
            Rendered template string
        """
        template = self._templates.get(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_name}")

        context = TemplateContext(notification=notification, variables=kwargs)

        # Add notification properties to context if available
        if notification:
            context.variables["color"] = notification.priority.color_hex
            context.variables["color_int"] = notification.priority.color_int
            context.variables["emoji"] = notification.emoji

        return template.render(context)

    def render_notification(
        self,
        notification: Notification,
        template_name: str = "plain_simple",
        **kwargs,
    ) -> str:
        """Convenience method to render notification."""
        return self.render(template_name, notification, **kwargs)

    def create_template(
        self,
        name: str,
        template: str,
        template_format: TemplateFormat = TemplateFormat.PLAIN,
        direction: TextDirection = TextDirection.AUTO,
    ) -> NotificationTemplate:
        """Create and register a new template."""
        if template_format == TemplateFormat.HTML:
            t = HTMLTemplate(name, template, direction=direction)
        elif template_format == TemplateFormat.MARKDOWN:
            t = MarkdownTemplate(name, template, direction=direction)
        else:
            t = StringTemplate(name, template, template_format, direction)

        self.register(t)
        return t


# ============================================================================
# Built-in Template Instances
# ============================================================================

# Create default engine instance
default_engine = TemplateEngine()


def render_template(
    template_name: str,
    notification: Optional[Notification] = None,
    **kwargs,
) -> str:
    """Render using the default template engine."""
    return default_engine.render(template_name, notification, **kwargs)


def create_notification_content(
    notification: Notification,
    format: TemplateFormat = TemplateFormat.PLAIN,
) -> str:
    """Create notification content in the specified format."""
    template_map = {
        TemplateFormat.PLAIN: "plain_detailed",
        TemplateFormat.HTML: "email_modern",
        TemplateFormat.MARKDOWN: "markdown_detailed",
        TemplateFormat.SLACK: "slack_block",
        TemplateFormat.DISCORD: "discord_embed",
    }
    template_name = template_map.get(format, "plain_simple")
    return default_engine.render(template_name, notification)
