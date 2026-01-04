"""
API Documentation Generator - مولد توثيق API
==============================================

Automatic API documentation generation from code.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, get_type_hints

logger = logging.getLogger(__name__)


@dataclass
class ParameterDoc:
    """توثيق المعامل"""
    name: str
    type_name: str
    description: str = ""
    required: bool = True
    default: Any = None
    location: str = "query"  # query, path, header, body
    example: Any = None


@dataclass
class ResponseDoc:
    """توثيق الاستجابة"""
    status_code: int
    description: str
    schema: Optional[Dict[str, Any]] = None
    example: Any = None


@dataclass
class EndpointDoc:
    """توثيق نقطة النهاية"""
    path: str
    method: str
    summary: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    parameters: List[ParameterDoc] = field(default_factory=list)
    request_body: Optional[Dict[str, Any]] = None
    responses: List[ResponseDoc] = field(default_factory=list)
    security: List[Dict[str, List[str]]] = field(default_factory=list)
    deprecated: bool = False
    operation_id: Optional[str] = None

    def to_openapi(self) -> Dict[str, Any]:
        """تحويل لتنسيق OpenAPI"""
        operation = {
            "summary": self.summary,
            "description": self.description,
            "tags": self.tags,
            "deprecated": self.deprecated,
            "responses": {},
        }

        if self.operation_id:
            operation["operationId"] = self.operation_id

        # Parameters
        if self.parameters:
            operation["parameters"] = []
            for param in self.parameters:
                if param.location != "body":
                    operation["parameters"].append({
                        "name": param.name,
                        "in": param.location,
                        "description": param.description,
                        "required": param.required,
                        "schema": {"type": param.type_name},
                        **({"example": param.example} if param.example else {}),
                    })

        # Request body
        if self.request_body:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": self.request_body,
                    },
                },
            }

        # Responses
        for response in self.responses:
            operation["responses"][str(response.status_code)] = {
                "description": response.description,
                **({"content": {"application/json": {"schema": response.schema}}} if response.schema else {}),
            }

        # Default response if none specified
        if not self.responses:
            operation["responses"]["200"] = {"description": "Successful response"}

        # Security
        if self.security:
            operation["security"] = self.security

        return operation


class APIDocGenerator:
    """
    مولد توثيق API
    API Documentation Generator

    Automatically generates OpenAPI documentation from code.
    """

    def __init__(self):
        self._endpoints: List[EndpointDoc] = []
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._type_mapping = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
            type(None): "null",
        }

    def document(
        self,
        path: str,
        method: str = "GET",
        summary: str = "",
        description: str = "",
        tags: Optional[List[str]] = None,
        responses: Optional[List[ResponseDoc]] = None,
        deprecated: bool = False,
    ) -> Callable:
        """
        مزخرف لتوثيق نقطة النهاية
        Decorator for documenting an endpoint

        Usage:
            @doc_generator.document(
                path="/jobs",
                method="POST",
                summary="Submit a new job",
                tags=["Jobs"],
            )
            async def submit_job(job_input: JobInput) -> Job:
                ...
        """
        def decorator(func: Callable) -> Callable:
            # Extract docstring
            doc = inspect.getdoc(func) or ""

            # Extract parameters from function signature
            parameters = self._extract_parameters(func)

            # Extract request body from type hints
            request_body = self._extract_request_body(func)

            # Create endpoint documentation
            endpoint = EndpointDoc(
                path=path,
                method=method.upper(),
                summary=summary or self._extract_summary(doc),
                description=description or doc,
                tags=tags or [],
                parameters=parameters,
                request_body=request_body,
                responses=responses or [ResponseDoc(200, "Successful response")],
                deprecated=deprecated,
                operation_id=func.__name__,
            )

            self._endpoints.append(endpoint)

            # Return original function
            return func

        return decorator

    def _extract_parameters(self, func: Callable) -> List[ParameterDoc]:
        """استخراج المعاملات من الدالة"""
        parameters = []
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}

        for name, param in sig.parameters.items():
            if name in ("self", "cls", "request", "info"):
                continue

            type_hint = hints.get(name, str)
            type_name = self._get_type_name(type_hint)

            # Determine location based on naming convention
            if name.endswith("_id"):
                location = "path"
            else:
                location = "query"

            parameters.append(ParameterDoc(
                name=name,
                type_name=type_name,
                description=f"The {name} parameter",
                required=param.default == inspect.Parameter.empty,
                default=param.default if param.default != inspect.Parameter.empty else None,
                location=location,
            ))

        return parameters

    def _extract_request_body(self, func: Callable) -> Optional[Dict[str, Any]]:
        """استخراج جسم الطلب"""
        hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}
        sig = inspect.signature(func)

        for name, param in sig.parameters.items():
            if name in ("self", "cls", "request", "info"):
                continue

            type_hint = hints.get(name)
            if type_hint and hasattr(type_hint, "__dataclass_fields__"):
                return self._dataclass_to_schema(type_hint)

        return None

    def _extract_summary(self, docstring: str) -> str:
        """استخراج الملخص من docstring"""
        if not docstring:
            return ""
        lines = docstring.split("\n")
        return lines[0].strip()

    def _get_type_name(self, type_hint: Any) -> str:
        """الحصول على اسم النوع"""
        if type_hint in self._type_mapping:
            return self._type_mapping[type_hint]

        origin = getattr(type_hint, "__origin__", None)
        if origin:
            if origin is list:
                return "array"
            elif origin is dict:
                return "object"

        return "string"

    def _dataclass_to_schema(self, cls: Type) -> Dict[str, Any]:
        """تحويل dataclass لـ schema"""
        if not hasattr(cls, "__dataclass_fields__"):
            return {"type": "object"}

        properties = {}
        required = []

        hints = get_type_hints(cls) if hasattr(cls, "__annotations__") else {}

        for field_name, field_info in cls.__dataclass_fields__.items():
            type_hint = hints.get(field_name, str)
            properties[field_name] = {
                "type": self._get_type_name(type_hint),
            }

            if field_info.default is field_info.default_factory:
                required.append(field_name)

        schema = {
            "type": "object",
            "properties": properties,
        }

        if required:
            schema["required"] = required

        return schema

    def register_schema(self, name: str, schema: Dict[str, Any]) -> None:
        """تسجيل schema"""
        self._schemas[name] = schema

    def generate_paths(self) -> Dict[str, Any]:
        """توليد المسارات"""
        paths: Dict[str, Dict[str, Any]] = {}

        for endpoint in self._endpoints:
            if endpoint.path not in paths:
                paths[endpoint.path] = {}
            paths[endpoint.path][endpoint.method.lower()] = endpoint.to_openapi()

        return paths

    def generate_components(self) -> Dict[str, Any]:
        """توليد المكونات"""
        return {
            "schemas": self._schemas,
        }

    def get_endpoints(self) -> List[EndpointDoc]:
        """الحصول على جميع نقاط النهاية"""
        return self._endpoints.copy()

    def clear(self) -> None:
        """مسح التوثيق"""
        self._endpoints.clear()
        self._schemas.clear()


# Global generator instance
doc_generator = APIDocGenerator()


def document(
    path: str,
    method: str = "GET",
    summary: str = "",
    tags: Optional[List[str]] = None,
    **kwargs,
) -> Callable:
    """
    مزخرف مختصر للتوثيق
    Shorthand decorator for documentation

    Usage:
        @document("/jobs", "POST", "Submit a job", tags=["Jobs"])
        async def submit_job(input: JobInput) -> Job:
            ...
    """
    return doc_generator.document(
        path=path,
        method=method,
        summary=summary,
        tags=tags,
        **kwargs,
    )
