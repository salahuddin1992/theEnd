"""
OpenAPI Documentation Module - وحدة توثيق OpenAPI
===================================================

Comprehensive OpenAPI/Swagger documentation for NebulaCompute API.
توثيق شامل لواجهة برمجة التطبيقات.

Features | الميزات:
- Auto-generated OpenAPI 3.0 spec
- Interactive Swagger UI
- ReDoc documentation
- Code examples in multiple languages
- Request/Response validation

Author: NebulaCompute Team
License: MIT
"""

from distributed_cluster.openapi.generator import (
    APIDocGenerator,
    EndpointDoc,
)
from distributed_cluster.openapi.routes import (
    get_redoc_ui,
    get_swagger_ui,
    setup_openapi_routes,
)
from distributed_cluster.openapi.spec import (
    OpenAPISpec,
    generate_openapi_spec,
)

__all__ = [
    "OpenAPISpec",
    "generate_openapi_spec",
    "setup_openapi_routes",
    "get_swagger_ui",
    "get_redoc_ui",
    "APIDocGenerator",
    "EndpointDoc",
]
