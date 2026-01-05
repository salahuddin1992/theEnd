# -*- coding: utf-8 -*-
"""
GraphQL Server for NebulaCompute.

HTTP and WebSocket server for GraphQL API.

خادم GraphQL للواجهة.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .resolvers import MutationResolver, QueryResolver, ResolverContext, ResolverInfo
from .schema import create_schema, generate_sdl
from .subscriptions import SubscriptionManager, WebSocketHandler

logger = logging.getLogger(__name__)


@dataclass
class GraphQLConfig:
    """GraphQL server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080
    path: str = "/graphql"
    ws_path: str = "/graphql/ws"
    playground_enabled: bool = True
    introspection_enabled: bool = True
    max_query_depth: int = 10
    max_query_complexity: int = 1000
    # Security: default to empty list (no CORS) instead of ["*"]
    cors_origins: List[str] = field(default_factory=list)
    rate_limit_per_minute: int = 1000


@dataclass
class GraphQLRequest:
    """GraphQL request object."""

    query: str
    operation_name: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None


@dataclass
class GraphQLResponse:
    """GraphQL response object."""

    data: Optional[Dict[str, Any]] = None
    errors: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {}
        if self.data is not None:
            result["data"] = self.data
        if self.errors:
            result["errors"] = self.errors
        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class GraphQLExecutor:
    """
    Executes GraphQL queries and mutations.

    منفذ استعلامات وتعديلات GraphQL.
    """

    def __init__(
        self,
        services: Dict[str, Any],
        config: Optional[GraphQLConfig] = None,
    ):
        """
        Initialize GraphQL executor.

        Args:
            services: Dictionary of service instances
            config: Server configuration
        """
        self.services = services
        self.config = config or GraphQLConfig()

        self.query_resolver = QueryResolver(services)
        self.mutation_resolver = MutationResolver(services)
        self.schema = create_schema()

        # Statistics
        self._stats = {
            "queries_executed": 0,
            "mutations_executed": 0,
            "errors_count": 0,
            "avg_execution_time_ms": 0.0,
        }

    async def execute(
        self,
        request: GraphQLRequest,
        context: Optional[ResolverContext] = None,
    ) -> GraphQLResponse:
        """
        Execute a GraphQL request.

        تنفيذ طلب GraphQL.
        """
        start_time = datetime.now(timezone.utc)
        context = context or ResolverContext()

        try:
            # Parse and validate query
            operation = self._parse_query(request.query)

            if not operation:
                return GraphQLResponse(errors=[{
                    "message": "Invalid query",
                    "code": "PARSE_ERROR",
                }])

            # Execute based on operation type
            if operation["type"] == "query":
                data = await self._execute_query(
                    operation, request.variables or {}, context
                )
                self._stats["queries_executed"] += 1

            elif operation["type"] == "mutation":
                data = await self._execute_mutation(
                    operation, request.variables or {}, context
                )
                self._stats["mutations_executed"] += 1

            else:
                return GraphQLResponse(errors=[{
                    "message": f"Unsupported operation: {operation['type']}",
                    "code": "UNSUPPORTED_OPERATION",
                }])

            # Update statistics
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            self._update_avg_time(execution_time)

            return GraphQLResponse(data=data)

        except Exception as e:
            self._stats["errors_count"] += 1
            logger.error(f"GraphQL execution error: {e}")

            return GraphQLResponse(errors=[{
                "message": str(e),
                "code": getattr(e, "code", "INTERNAL_ERROR"),
            }])

    def _parse_query(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse GraphQL query string."""
        query = query.strip()

        # Determine operation type
        if query.startswith("query") or query.startswith("{"):
            op_type = "query"
        elif query.startswith("mutation"):
            op_type = "mutation"
        elif query.startswith("subscription"):
            op_type = "subscription"
        else:
            return None

        # Extract fields
        fields = self._extract_fields(query)

        return {
            "type": op_type,
            "fields": fields,
        }

    def _extract_fields(self, query: str) -> List[Dict[str, Any]]:
        """Extract field selections from query."""
        fields = []

        # Simple field extraction - production should use proper parser
        import re

        # Match field patterns like: fieldName(args) { ... } or fieldName
        pattern = r'(\w+)\s*(?:\(([^)]*)\))?\s*(?:\{([^}]*)\})?'

        # Find the main body
        brace_match = re.search(r'\{(.+)\}', query, re.DOTALL)
        if brace_match:
            body = brace_match.group(1)

            for match in re.finditer(pattern, body):
                field_name = match.group(1)
                args_str = match.group(2)
                subfields = match.group(3)

                # Skip GraphQL keywords
                if field_name in ["query", "mutation", "subscription", "fragment"]:
                    continue

                args = {}
                if args_str:
                    # Parse arguments
                    for arg_match in re.finditer(r'(\w+)\s*:\s*([^,\)]+)', args_str):
                        arg_name = arg_match.group(1)
                        arg_value = arg_match.group(2).strip().strip('"')
                        args[arg_name] = arg_value

                fields.append({
                    "name": field_name,
                    "args": args,
                    "subfields": subfields.strip() if subfields else None,
                })

        return fields

    async def _execute_query(
        self,
        operation: Dict[str, Any],
        variables: Dict[str, Any],
        context: ResolverContext,
    ) -> Dict[str, Any]:
        """Execute a query operation."""
        result = {}

        for gql_field in operation["fields"]:
            field_name = gql_field["name"]
            args = self._resolve_variables(gql_field["args"], variables)

            info = ResolverInfo(
                field_name=field_name,
                parent_type="Query",
                return_type="Unknown",
                path=[field_name],
            )

            result[field_name] = await self.query_resolver.resolve(
                field_name, args, context, info
            )

        return result

    async def _execute_mutation(
        self,
        operation: Dict[str, Any],
        variables: Dict[str, Any],
        context: ResolverContext,
    ) -> Dict[str, Any]:
        """Execute a mutation operation."""
        result = {}

        for gql_field in operation["fields"]:
            field_name = gql_field["name"]
            args = self._resolve_variables(gql_field["args"], variables)

            info = ResolverInfo(
                field_name=field_name,
                parent_type="Mutation",
                return_type="Unknown",
                path=[field_name],
            )

            result[field_name] = await self.mutation_resolver.resolve(
                field_name, args, context, info
            )

        return result

    def _resolve_variables(
        self,
        args: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Resolve variable references in arguments."""
        resolved = {}

        for key, value in args.items():
            if isinstance(value, str) and value.startswith("$"):
                var_name = value[1:]
                resolved[key] = variables.get(var_name, value)
            else:
                resolved[key] = value

        return resolved

    def _update_avg_time(self, execution_time: float) -> None:
        """Update average execution time."""
        total = self._stats["queries_executed"] + self._stats["mutations_executed"]
        current_avg = self._stats["avg_execution_time_ms"]

        if total == 1:
            self._stats["avg_execution_time_ms"] = execution_time
        else:
            self._stats["avg_execution_time_ms"] = (
                (current_avg * (total - 1) + execution_time) / total
            )

    async def get_statistics(self) -> Dict[str, Any]:
        """Get executor statistics."""
        return {**self._stats}


class GraphQLServer:
    """
    GraphQL HTTP and WebSocket server.

    خادم GraphQL HTTP و WebSocket.

    Features:
    - HTTP endpoint for queries/mutations
    - WebSocket endpoint for subscriptions
    - GraphQL Playground UI
    - Introspection support
    - Rate limiting
    - CORS handling
    """

    def __init__(
        self,
        services: Dict[str, Any],
        config: Optional[GraphQLConfig] = None,
    ):
        """
        Initialize GraphQL server.

        Args:
            services: Dictionary of service instances
            config: Server configuration
        """
        self.services = services
        self.config = config or GraphQLConfig()

        self.executor = GraphQLExecutor(services, self.config)
        self.subscription_manager = SubscriptionManager()
        self.ws_handler = WebSocketHandler(self.subscription_manager)

        self._running = False
        self._server = None

        # Rate limiting
        self._request_counts: Dict[str, List[datetime]] = {}

    async def start(self) -> None:
        """Start the GraphQL server."""
        await self.subscription_manager.start()
        self._running = True

        logger.info(
            f"GraphQL server starting on "
            f"http://{self.config.host}:{self.config.port}{self.config.path}"
        )

        # In production, integrate with actual HTTP framework (aiohttp, FastAPI, etc.)
        # This is a minimal implementation for demonstration

    async def stop(self) -> None:
        """Stop the GraphQL server."""
        self._running = False
        await self.subscription_manager.stop()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        logger.info("GraphQL server stopped")

    async def handle_request(
        self,
        method: str,
        path: str,
        body: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle an HTTP request.

        معالجة طلب HTTP.
        """
        headers = headers or {}

        # Rate limiting
        if client_ip and not self._check_rate_limit(client_ip):
            return {
                "status": 429,
                "body": {"error": "Rate limit exceeded"},
            }

        # CORS preflight
        if method == "OPTIONS":
            return {
                "status": 200,
                "headers": self._get_cors_headers(),
            }

        # GraphQL Playground
        if method == "GET" and self.config.playground_enabled:
            if path == self.config.path:
                return {
                    "status": 200,
                    "headers": {"Content-Type": "text/html"},
                    "body": self._get_playground_html(),
                }

        # GraphQL endpoint
        if path == self.config.path:
            if method == "POST":
                return await self._handle_graphql_request(body, headers)
            elif method == "GET":
                # Introspection query
                if self.config.introspection_enabled:
                    return {
                        "status": 200,
                        "headers": {"Content-Type": "application/json"},
                        "body": {"data": {"__schema": self.executor.schema}},
                    }

        # Schema SDL endpoint
        if path == f"{self.config.path}/schema":
            return {
                "status": 200,
                "headers": {"Content-Type": "text/plain"},
                "body": generate_sdl(),
            }

        return {"status": 404, "body": {"error": "Not found"}}

    async def _handle_graphql_request(
        self,
        body: Optional[str],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Handle GraphQL POST request."""
        try:
            if not body:
                return {
                    "status": 400,
                    "body": {"error": "Request body is required"},
                }

            data = json.loads(body)

            request = GraphQLRequest(
                query=data.get("query", ""),
                operation_name=data.get("operationName"),
                variables=data.get("variables"),
            )

            # Create context from headers
            context = ResolverContext(
                user_id=headers.get("X-User-Id"),
                auth_token=headers.get("Authorization"),
                request_id=headers.get("X-Request-Id"),
            )

            response = await self.executor.execute(request, context)

            return {
                "status": 200,
                "headers": {
                    "Content-Type": "application/json",
                    **self._get_cors_headers(),
                },
                "body": response.to_dict(),
            }

        except json.JSONDecodeError:
            return {
                "status": 400,
                "body": {"error": "Invalid JSON"},
            }
        except Exception as e:
            logger.error(f"GraphQL request error: {e}")
            return {
                "status": 500,
                "body": {"error": str(e)},
            }

    def _check_rate_limit(self, client_ip: str) -> bool:
        """Check if request is within rate limit."""
        now = datetime.now(timezone.utc)
        minute_ago = now.replace(second=0, microsecond=0)

        # Clean old entries
        if client_ip in self._request_counts:
            self._request_counts[client_ip] = [
                t for t in self._request_counts[client_ip]
                if t > minute_ago
            ]
        else:
            self._request_counts[client_ip] = []

        # Check limit
        if len(self._request_counts[client_ip]) >= self.config.rate_limit_per_minute:
            return False

        self._request_counts[client_ip].append(now)
        return True

    def _get_cors_headers(self) -> Dict[str, str]:
        """Get CORS headers."""
        if not self.config.cors_origins:
            # No CORS configured - return empty headers
            return {}
        return {
            "Access-Control-Allow-Origin": ", ".join(self.config.cors_origins),
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-User-Id",
        }

    def _get_playground_html(self) -> str:
        """Get GraphQL Playground HTML."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>NebulaCompute GraphQL Playground</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/graphql-playground-react/build/static/css/index.css" />
    <script src="https://cdn.jsdelivr.net/npm/graphql-playground-react/build/static/js/middleware.js"></script>
</head>
<body>
    <div id="root"></div>
    <script>
        window.addEventListener('load', function() {{
            GraphQLPlayground.init(document.getElementById('root'), {{
                endpoint: '{self.config.path}',
                subscriptionEndpoint: 'ws://localhost:{self.config.port}{self.config.ws_path}',
                settings: {{
                    'editor.theme': 'dark',
                    'request.credentials': 'include'
                }}
            }})
        }})
    </script>
</body>
</html>
"""

    async def get_statistics(self) -> Dict[str, Any]:
        """Get server statistics."""
        executor_stats = await self.executor.get_statistics()
        subscription_stats = await self.subscription_manager.get_subscription_stats()

        return {
            "executor": executor_stats,
            "subscriptions": subscription_stats,
            "config": {
                "host": self.config.host,
                "port": self.config.port,
                "playground_enabled": self.config.playground_enabled,
            },
        }
