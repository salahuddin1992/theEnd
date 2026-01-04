"""
OpenAPI Specification - مواصفات OpenAPI
=========================================

OpenAPI 3.0 specification generator for NebulaCompute.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class OpenAPISpec:
    """
    مواصفات OpenAPI
    OpenAPI Specification
    """
    title: str = "NebulaCompute API"
    description: str = ""
    version: str = "1.0.0"
    servers: List[Dict[str, str]] = field(default_factory=list)
    paths: Dict[str, Any] = field(default_factory=dict)
    components: Dict[str, Any] = field(default_factory=dict)
    tags: List[Dict[str, str]] = field(default_factory=list)
    security: List[Dict[str, List[str]]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس"""
        return {
            "openapi": "3.0.3",
            "info": {
                "title": self.title,
                "description": self.description,
                "version": self.version,
                "contact": {
                    "name": "NebulaCompute Team",
                    "email": "support@nebulacompute.io",
                    "url": "https://nebulacompute.io",
                },
                "license": {
                    "name": "MIT",
                    "url": "https://opensource.org/licenses/MIT",
                },
            },
            "servers": self.servers or [
                {"url": "http://localhost:8765", "description": "Local development"},
                {"url": "https://api.nebulacompute.io", "description": "Production"},
            ],
            "paths": self.paths,
            "components": self.components,
            "tags": self.tags,
            "security": self.security,
        }

    def to_json(self, indent: int = 2) -> str:
        """تحويل لـ JSON"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_yaml(self) -> str:
        """تحويل لـ YAML"""
        try:
            import yaml
            return yaml.dump(self.to_dict(), allow_unicode=True, default_flow_style=False)
        except ImportError:
            raise RuntimeError("PyYAML is required for YAML output")


def generate_openapi_spec() -> OpenAPISpec:
    """
    توليد مواصفات OpenAPI الكاملة
    Generate complete OpenAPI specification
    """
    spec = OpenAPISpec(
        title="NebulaCompute API",
        description="""
# NebulaCompute REST API
## نظام الحوسبة الموزعة - واجهة برمجة التطبيقات

NebulaCompute provides a comprehensive distributed computing platform with:
- **Job Management**: Submit, monitor, and manage compute jobs
- **Worker Management**: Register and manage compute workers
- **Cluster Monitoring**: Real-time cluster metrics and health
- **Multi-tenancy**: Tenant isolation and quota management
- **Authentication**: JWT-based authentication and RBAC

## Authentication
All API requests require authentication using a Bearer token:
```
Authorization: Bearer <your-token>
```

## Rate Limiting
API requests are rate-limited. Check response headers:
- `X-RateLimit-Limit`: Maximum requests per window
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Window reset time

## Errors
Errors follow RFC 7807 Problem Details format:
```json
{
  "type": "https://api.nebulacompute.io/errors/quota-exceeded",
  "title": "Quota Exceeded",
  "status": 429,
  "detail": "Maximum concurrent jobs limit reached"
}
```
        """,
        version="1.0.0",
        tags=[
            {"name": "Jobs", "description": "Job management operations"},
            {"name": "Workers", "description": "Worker management operations"},
            {"name": "Cluster", "description": "Cluster status and metrics"},
            {"name": "Tenants", "description": "Multi-tenancy management"},
            {"name": "Backups", "description": "Backup and restore operations"},
            {"name": "Auth", "description": "Authentication and authorization"},
        ],
    )

    # Add components (schemas, security schemes, etc.)
    spec.components = _generate_components()

    # Add paths
    spec.paths = _generate_paths()

    # Add security
    spec.security = [{"bearerAuth": []}]

    return spec


def _generate_components() -> Dict[str, Any]:
    """توليد المكونات"""
    return {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT authentication token",
            },
            "apiKey": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key authentication",
            },
        },
        "schemas": {
            # Job schemas
            "Job": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid", "description": "Unique job identifier"},
                    "command": {"type": "string", "description": "Command to execute"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "Command arguments"},
                    "status": {"$ref": "#/components/schemas/JobStatus"},
                    "priority": {"$ref": "#/components/schemas/JobPriority"},
                    "resources": {"$ref": "#/components/schemas/ResourceRequirements"},
                    "worker_id": {"type": "string", "nullable": True},
                    "exit_code": {"type": "integer", "nullable": True},
                    "output": {"type": "string", "nullable": True},
                    "error": {"type": "string", "nullable": True},
                    "created_at": {"type": "string", "format": "date-time"},
                    "started_at": {"type": "string", "format": "date-time", "nullable": True},
                    "completed_at": {"type": "string", "format": "date-time", "nullable": True},
                },
                "required": ["id", "command", "status"],
            },
            "JobStatus": {
                "type": "string",
                "enum": ["pending", "scheduled", "running", "completed", "failed", "cancelled", "timeout"],
                "description": "Current status of the job",
            },
            "JobPriority": {
                "type": "string",
                "enum": ["low", "normal", "high", "critical"],
                "description": "Job priority level",
            },
            "JobInput": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute"},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "image": {"type": "string", "description": "Docker image (optional)"},
                    "priority": {"$ref": "#/components/schemas/JobPriority"},
                    "resources": {"$ref": "#/components/schemas/ResourceRequirements"},
                    "timeout": {"type": "integer", "default": 3600, "description": "Timeout in seconds"},
                    "retries": {"type": "integer", "default": 3},
                    "env": {"type": "object", "additionalProperties": {"type": "string"}},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["command"],
            },
            "ResourceRequirements": {
                "type": "object",
                "properties": {
                    "cpu": {"type": "number", "minimum": 0.1, "default": 1.0, "description": "CPU cores"},
                    "memory": {"type": "integer", "minimum": 128, "default": 1024, "description": "Memory in MB"},
                    "gpu": {"type": "integer", "minimum": 0, "default": 0, "description": "GPU count"},
                    "gpu_memory": {"type": "integer", "description": "GPU memory in MB"},
                },
            },
            # Worker schemas
            "Worker": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "name": {"type": "string"},
                    "hostname": {"type": "string"},
                    "status": {"$ref": "#/components/schemas/WorkerStatus"},
                    "ip_address": {"type": "string", "format": "ipv4"},
                    "port": {"type": "integer"},
                    "resources_total": {"$ref": "#/components/schemas/ResourceRequirements"},
                    "resources_available": {"$ref": "#/components/schemas/ResourceRequirements"},
                    "active_jobs": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "registered_at": {"type": "string", "format": "date-time"},
                    "last_heartbeat": {"type": "string", "format": "date-time"},
                },
            },
            "WorkerStatus": {
                "type": "string",
                "enum": ["online", "offline", "busy", "draining", "maintenance"],
            },
            # Cluster schemas
            "ClusterStats": {
                "type": "object",
                "properties": {
                    "total_workers": {"type": "integer"},
                    "online_workers": {"type": "integer"},
                    "total_jobs": {"type": "integer"},
                    "running_jobs": {"type": "integer"},
                    "pending_jobs": {"type": "integer"},
                    "completed_jobs": {"type": "integer"},
                    "failed_jobs": {"type": "integer"},
                    "total_cpu": {"type": "number"},
                    "available_cpu": {"type": "number"},
                    "total_memory": {"type": "integer"},
                    "available_memory": {"type": "integer"},
                    "total_gpu": {"type": "integer"},
                    "available_gpu": {"type": "integer"},
                    "uptime_seconds": {"type": "number"},
                },
            },
            # Tenant schemas
            "Tenant": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "name": {"type": "string"},
                    "display_name": {"type": "string"},
                    "status": {"$ref": "#/components/schemas/TenantStatus"},
                    "tier": {"type": "string", "enum": ["free", "starter", "professional", "enterprise"]},
                    "quotas": {"$ref": "#/components/schemas/TenantQuotas"},
                    "usage": {"$ref": "#/components/schemas/TenantUsage"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "TenantStatus": {
                "type": "string",
                "enum": ["pending", "active", "suspended", "quota_exceeded", "terminating"],
            },
            "TenantQuotas": {
                "type": "object",
                "properties": {
                    "max_concurrent_jobs": {"type": "integer"},
                    "max_jobs_per_day": {"type": "integer"},
                    "max_cpu_cores": {"type": "number"},
                    "max_memory_mb": {"type": "integer"},
                    "max_gpu_count": {"type": "integer"},
                },
            },
            "TenantUsage": {
                "type": "object",
                "properties": {
                    "active_jobs": {"type": "integer"},
                    "total_jobs": {"type": "integer"},
                    "cpu_used": {"type": "number"},
                    "memory_used_mb": {"type": "integer"},
                    "gpu_used": {"type": "integer"},
                },
            },
            # Backup schemas
            "Backup": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["full", "incremental", "snapshot"]},
                    "status": {"type": "string", "enum": ["pending", "running", "completed", "failed"]},
                    "size_bytes": {"type": "integer"},
                    "location": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "completed_at": {"type": "string", "format": "date-time"},
                },
            },
            # Common schemas
            "Error": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "format": "uri"},
                    "title": {"type": "string"},
                    "status": {"type": "integer"},
                    "detail": {"type": "string"},
                    "instance": {"type": "string"},
                },
                "required": ["type", "title", "status"],
            },
            "PaginatedResponse": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {}},
                    "total": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            },
            "HealthCheck": {
                "type": "object",
                "properties": {
                    "healthy": {"type": "boolean"},
                    "status": {"type": "string"},
                    "version": {"type": "string"},
                    "uptime_seconds": {"type": "number"},
                    "checks": {"type": "object"},
                },
            },
        },
        "parameters": {
            "offsetParam": {
                "name": "offset",
                "in": "query",
                "description": "Number of items to skip",
                "schema": {"type": "integer", "minimum": 0, "default": 0},
            },
            "limitParam": {
                "name": "limit",
                "in": "query",
                "description": "Maximum number of items to return",
                "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
        },
        "responses": {
            "NotFound": {
                "description": "Resource not found",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                    },
                },
            },
            "Unauthorized": {
                "description": "Authentication required",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                    },
                },
            },
            "Forbidden": {
                "description": "Access denied",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                    },
                },
            },
            "RateLimited": {
                "description": "Too many requests",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                    },
                },
                "headers": {
                    "X-RateLimit-Limit": {"schema": {"type": "integer"}},
                    "X-RateLimit-Remaining": {"schema": {"type": "integer"}},
                    "X-RateLimit-Reset": {"schema": {"type": "integer"}},
                },
            },
        },
    }


def _generate_paths() -> Dict[str, Any]:
    """توليد المسارات"""
    return {
        # Health
        "/health": {
            "get": {
                "tags": ["Cluster"],
                "summary": "Health check",
                "description": "Check cluster health status",
                "operationId": "healthCheck",
                "security": [],
                "responses": {
                    "200": {
                        "description": "Cluster is healthy",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/HealthCheck"},
                            },
                        },
                    },
                    "503": {
                        "description": "Cluster is unhealthy",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/HealthCheck"},
                            },
                        },
                    },
                },
            },
        },
        # Jobs
        "/jobs": {
            "get": {
                "tags": ["Jobs"],
                "summary": "List jobs",
                "description": "Get a paginated list of jobs with optional filtering",
                "operationId": "listJobs",
                "parameters": [
                    {"$ref": "#/components/parameters/offsetParam"},
                    {"$ref": "#/components/parameters/limitParam"},
                    {
                        "name": "status",
                        "in": "query",
                        "schema": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/JobStatus"}
                        }
                    },
                    {
                        "name": "priority",
                        "in": "query",
                        "schema": {"$ref": "#/components/schemas/JobPriority"}
                    },
                    {"name": "worker_id", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {
                        "description": "List of jobs",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "allOf": [
                                        {"$ref": "#/components/schemas/PaginatedResponse"},
                                        {
                                            "properties": {
                                                "items": {
                                                    "type": "array",
                                                    "items": {"$ref": "#/components/schemas/Job"}
                                                }
                                            }
                                        },
                                    ],
                                },
                            },
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                },
            },
            "post": {
                "tags": ["Jobs"],
                "summary": "Submit job",
                "description": "Submit a new compute job",
                "operationId": "submitJob",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/JobInput"},
                            "examples": {
                                "simple": {
                                    "summary": "Simple command",
                                    "value": {"command": "echo 'Hello World'"},
                                },
                                "python": {
                                    "summary": "Python script",
                                    "value": {
                                        "command": "python",
                                        "args": ["train.py", "--epochs", "100"],
                                        "resources": {"cpu": 4, "memory": 8192, "gpu": 1},
                                        "image": "pytorch/pytorch:2.0.1-cuda11.7",
                                    },
                                },
                            },
                        },
                    },
                },
                "responses": {
                    "201": {
                        "description": "Job submitted successfully",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Job"},
                            },
                        },
                    },
                    "400": {
                        "description": "Invalid job specification",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "429": {"$ref": "#/components/responses/RateLimited"},
                },
            },
        },
        "/jobs/{jobId}": {
            "get": {
                "tags": ["Jobs"],
                "summary": "Get job",
                "description": "Get job details by ID",
                "operationId": "getJob",
                "parameters": [
                    {"name": "jobId", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                ],
                "responses": {
                    "200": {
                        "description": "Job details",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Job"}}},
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            },
            "delete": {
                "tags": ["Jobs"],
                "summary": "Cancel job",
                "description": "Cancel a pending or running job",
                "operationId": "cancelJob",
                "parameters": [
                    {"name": "jobId", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                ],
                "responses": {
                    "200": {
                        "description": "Job cancelled",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Job"}}},
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            },
        },
        "/jobs/{jobId}/retry": {
            "post": {
                "tags": ["Jobs"],
                "summary": "Retry job",
                "description": "Retry a failed job",
                "operationId": "retryJob",
                "parameters": [
                    {"name": "jobId", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                ],
                "responses": {
                    "200": {
                        "description": "Job queued for retry",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Job"}}},
                    },
                    "400": {"description": "Job cannot be retried"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            },
        },
        # Workers
        "/workers": {
            "get": {
                "tags": ["Workers"],
                "summary": "List workers",
                "description": "Get a list of all workers",
                "operationId": "listWorkers",
                "parameters": [
                    {"name": "status", "in": "query", "schema": {"$ref": "#/components/schemas/WorkerStatus"}},
                    {"name": "has_gpu", "in": "query", "schema": {"type": "boolean"}},
                ],
                "responses": {
                    "200": {
                        "description": "List of workers",
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"$ref": "#/components/schemas/Worker"}},
                            },
                        },
                    },
                },
            },
        },
        "/workers/{workerId}": {
            "get": {
                "tags": ["Workers"],
                "summary": "Get worker",
                "description": "Get worker details by ID",
                "operationId": "getWorker",
                "parameters": [
                    {"name": "workerId", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {
                        "description": "Worker details",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Worker"}}},
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            },
        },
        "/workers/{workerId}/drain": {
            "post": {
                "tags": ["Workers"],
                "summary": "Drain worker",
                "description": "Start draining a worker for maintenance",
                "operationId": "drainWorker",
                "parameters": [
                    {"name": "workerId", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {
                        "description": "Worker draining started",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Worker"}}},
                    },
                },
            },
        },
        # Cluster
        "/stats": {
            "get": {
                "tags": ["Cluster"],
                "summary": "Get cluster stats",
                "description": "Get cluster-wide statistics",
                "operationId": "getClusterStats",
                "responses": {
                    "200": {
                        "description": "Cluster statistics",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ClusterStats"}}},
                    },
                },
            },
        },
        # Tenants
        "/tenants": {
            "get": {
                "tags": ["Tenants"],
                "summary": "List tenants",
                "description": "Get a list of all tenants (admin only)",
                "operationId": "listTenants",
                "responses": {
                    "200": {
                        "description": "List of tenants",
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"$ref": "#/components/schemas/Tenant"}},
                            },
                        },
                    },
                    "403": {"$ref": "#/components/responses/Forbidden"},
                },
            },
            "post": {
                "tags": ["Tenants"],
                "summary": "Create tenant",
                "description": "Create a new tenant (admin only)",
                "operationId": "createTenant",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "display_name": {"type": "string"},
                                    "admin_email": {"type": "string", "format": "email"},
                                    "tier": {"type": "string"},
                                },
                                "required": ["name"],
                            },
                        },
                    },
                },
                "responses": {
                    "201": {
                        "description": "Tenant created",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Tenant"}}},
                    },
                },
            },
        },
        # Backups
        "/backups": {
            "get": {
                "tags": ["Backups"],
                "summary": "List backups",
                "description": "Get a list of all backups",
                "operationId": "listBackups",
                "responses": {
                    "200": {
                        "description": "List of backups",
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"$ref": "#/components/schemas/Backup"}},
                            },
                        },
                    },
                },
            },
            "post": {
                "tags": ["Backups"],
                "summary": "Create backup",
                "description": "Create a new backup",
                "operationId": "createBackup",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string", "enum": ["full", "incremental"]},
                                },
                            },
                        },
                    },
                },
                "responses": {
                    "201": {
                        "description": "Backup started",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Backup"}}},
                    },
                },
            },
        },
        "/backups/{backupId}/restore": {
            "post": {
                "tags": ["Backups"],
                "summary": "Restore backup",
                "description": "Restore from a backup",
                "operationId": "restoreBackup",
                "parameters": [
                    {"name": "backupId", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {"description": "Restore started"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            },
        },
    }
