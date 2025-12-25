"""
OpenAPI Routes - مسارات OpenAPI
=================================

Routes for serving OpenAPI documentation.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def get_swagger_ui(openapi_url: str = "/openapi.json", title: str = "NebulaCompute API") -> str:
    """
    الحصول على صفحة Swagger UI
    Get Swagger UI HTML page
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Swagger UI</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css">
    <style>
        html {{ box-sizing: border-box; overflow-y: scroll; }}
        *, *:before, *:after {{ box-sizing: inherit; }}
        body {{ margin: 0; background: #fafafa; }}
        .swagger-ui .topbar {{ display: none; }}
        .swagger-ui .info hgroup.main a {{ color: #3b4151; font-weight: bold; }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"></script>
    <script>
        window.onload = function() {{
            window.ui = SwaggerUIBundle({{
                url: "{openapi_url}",
                dom_id: '#swagger-ui',
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
                layout: "StandaloneLayout",
                deepLinking: true,
                showMutatedRequest: true,
                supportedSubmitMethods: ['get', 'post', 'put', 'delete', 'patch'],
                validatorUrl: null,
                persistAuthorization: true,
                requestInterceptor: function(req) {{
                    // Add default headers
                    return req;
                }}
            }});
        }}
    </script>
</body>
</html>
    """


def get_redoc_ui(openapi_url: str = "/openapi.json", title: str = "NebulaCompute API") -> str:
    """
    الحصول على صفحة ReDoc
    Get ReDoc HTML page
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Documentation</title>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;700&family=Roboto:wght@300;400;700&display=swap" rel="stylesheet">
    <style>
        body {{ margin: 0; padding: 0; }}
    </style>
</head>
<body>
    <redoc spec-url="{openapi_url}"
           hide-download-button="false"
           theme='{{"colors": {{"primary": {{"main": "#667eea"}}}}, "typography": {{"headings": {{"fontFamily": "Montserrat, sans-serif"}}}}}}'
    ></redoc>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
</body>
</html>
    """


def setup_openapi_routes(app: Any, spec_generator: Any = None) -> None:
    """
    إعداد مسارات OpenAPI
    Setup OpenAPI routes for FastAPI app
    """
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse, JSONResponse

        from distributed_cluster.openapi.spec import generate_openapi_spec

        if not isinstance(app, FastAPI):
            logger.warning("App is not a FastAPI instance, skipping OpenAPI routes")
            return

        # Generate spec
        spec = spec_generator() if spec_generator else generate_openapi_spec()

        @app.get("/openapi.json", include_in_schema=False)
        async def get_openapi():
            """Get OpenAPI specification as JSON"""
            return JSONResponse(spec.to_dict())

        @app.get("/openapi.yaml", include_in_schema=False)
        async def get_openapi_yaml():
            """Get OpenAPI specification as YAML"""
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(spec.to_yaml(), media_type="text/yaml")

        @app.get("/docs", include_in_schema=False)
        async def swagger_ui():
            """Swagger UI documentation"""
            return HTMLResponse(get_swagger_ui("/openapi.json", spec.title))

        @app.get("/redoc", include_in_schema=False)
        async def redoc():
            """ReDoc documentation"""
            return HTMLResponse(get_redoc_ui("/openapi.json", spec.title))

        logger.info("OpenAPI routes configured: /docs, /redoc, /openapi.json, /openapi.yaml")

    except ImportError:
        logger.warning("FastAPI not available, skipping route setup")
    except Exception as e:
        logger.error(f"Failed to setup OpenAPI routes: {e}")


class OpenAPIRouter:
    """
    موجه OpenAPI
    OpenAPI Router for non-FastAPI apps
    """

    def __init__(self, spec_generator: Any = None):
        from distributed_cluster.openapi.spec import generate_openapi_spec
        self.spec = spec_generator() if spec_generator else generate_openapi_spec()

    def get_openapi_json(self) -> Dict[str, Any]:
        """Get OpenAPI JSON"""
        return self.spec.to_dict()

    def get_openapi_yaml(self) -> str:
        """Get OpenAPI YAML"""
        return self.spec.to_yaml()

    def get_swagger_html(self) -> str:
        """Get Swagger UI HTML"""
        return get_swagger_ui("/openapi.json", self.spec.title)

    def get_redoc_html(self) -> str:
        """Get ReDoc HTML"""
        return get_redoc_ui("/openapi.json", self.spec.title)

    async def handle_request(self, path: str) -> tuple[str, str, int]:
        """
        معالجة الطلب
        Handle request

        Returns: (content, content_type, status_code)
        """
        if path == "/openapi.json":
            import json
            return json.dumps(self.get_openapi_json()), "application/json", 200
        elif path == "/openapi.yaml":
            return self.get_openapi_yaml(), "text/yaml", 200
        elif path == "/docs":
            return self.get_swagger_html(), "text/html", 200
        elif path == "/redoc":
            return self.get_redoc_html(), "text/html", 200
        else:
            return '{"error": "Not Found"}', "application/json", 404
