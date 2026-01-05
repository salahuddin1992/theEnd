"""
Job Templates System
====================

نظام قوالب الوظائف القابلة لإعادة الاستخدام.

يدعم:
- إنشاء وإدارة القوالب
- متغيرات القالب
- وراثة القوالب
- إصدارات القوالب
"""

import copy
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class TemplateError(Exception):
    """Template-related error."""

    pass


class VariableType(Enum):
    """Variable type for template parameters."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    SECRET = "secret"


@dataclass
class TemplateVariable:
    """Variable definition for a template."""

    name: str
    var_type: VariableType = VariableType.STRING
    default: Optional[Any] = None
    required: bool = False
    description: str = ""
    validation_pattern: Optional[str] = None  # Regex pattern
    allowed_values: Optional[List[Any]] = None

    def validate(self, value: Any) -> tuple[bool, str]:
        """Validate a value against this variable definition."""
        if value is None:
            if self.required and self.default is None:
                return False, f"Variable '{self.name}' is required"
            return True, ""

        # Type validation
        try:
            if self.var_type == VariableType.INTEGER:
                int(value)
            elif self.var_type == VariableType.FLOAT:
                float(value)
            elif self.var_type == VariableType.BOOLEAN:
                if not isinstance(value, bool):
                    if str(value).lower() not in ("true", "false", "1", "0", "yes", "no"):
                        return False, f"Variable '{self.name}' must be boolean"
            elif self.var_type == VariableType.LIST:
                if not isinstance(value, list):
                    return False, f"Variable '{self.name}' must be a list"
        except (ValueError, TypeError):
            return False, f"Variable '{self.name}' has invalid type, expected {self.var_type.value}"

        # Pattern validation
        if self.validation_pattern and isinstance(value, str):
            if not re.match(self.validation_pattern, value):
                return False, f"Variable '{self.name}' doesn't match pattern {self.validation_pattern}"

        # Allowed values validation
        if self.allowed_values:
            if value not in self.allowed_values:
                return False, f"Variable '{self.name}' must be one of: {self.allowed_values}"

        return True, ""

    def convert_value(self, value: Any) -> Any:
        """Convert value to the correct type."""
        if value is None:
            return self.default

        if self.var_type == VariableType.INTEGER:
            return int(value)
        elif self.var_type == VariableType.FLOAT:
            return float(value)
        elif self.var_type == VariableType.BOOLEAN:
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes")

        return value


@dataclass
class ResourceRequirements:
    """Resource requirements for a template."""

    cpu_cores: float = 1.0
    memory_mb: int = 512
    gpu_count: int = 0
    gpu_type: Optional[str] = None
    disk_mb: int = 0
    network_bandwidth_mbps: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_cores": self.cpu_cores,
            "memory_mb": self.memory_mb,
            "gpu_count": self.gpu_count,
            "gpu_type": self.gpu_type,
            "disk_mb": self.disk_mb,
            "network_bandwidth_mbps": self.network_bandwidth_mbps,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceRequirements":
        return cls(
            cpu_cores=data.get("cpu_cores", 1.0),
            memory_mb=data.get("memory_mb", 512),
            gpu_count=data.get("gpu_count", 0),
            gpu_type=data.get("gpu_type"),
            disk_mb=data.get("disk_mb", 0),
            network_bandwidth_mbps=data.get("network_bandwidth_mbps", 0),
        )


@dataclass
class JobTemplate:
    """Job template definition."""

    name: str
    template_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    version: str = "1.0.0"

    # Parent template for inheritance
    parent_template: Optional[str] = None

    # Command configuration
    command: Optional[str] = None  # Can use ${variable} syntax
    args: List[str] = field(default_factory=list)
    working_directory: Optional[str] = None

    # Container configuration
    docker_image: Optional[str] = None
    docker_registry: Optional[str] = None
    docker_credentials_secret: Optional[str] = None

    # Resources
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)

    # Execution settings
    timeout_seconds: int = 3600
    max_retries: int = 0
    retry_delay_seconds: int = 60

    # Environment
    environment: Dict[str, str] = field(default_factory=dict)

    # Secrets to inject (secret_name -> env_var_name)
    secrets: Dict[str, str] = field(default_factory=dict)

    # Worker selection
    required_tags: List[str] = field(default_factory=list)
    worker_pool: Optional[str] = None
    queue: Optional[str] = None

    # Scheduling
    priority: int = 50
    preemptible: bool = False

    # Variables
    variables: List[TemplateVariable] = field(default_factory=list)

    # Artifacts
    input_artifacts: List[Dict[str, str]] = field(default_factory=list)
    output_artifacts: List[Dict[str, str]] = field(default_factory=list)

    # Hooks
    pre_run_commands: List[str] = field(default_factory=list)
    post_run_commands: List[str] = field(default_factory=list)

    # Metadata
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    def substitute_variables(self, text: str, values: Dict[str, Any]) -> str:
        """Substitute variables in text using ${var} syntax."""

        def replace(match):
            var_name = match.group(1)
            if var_name in values:
                return str(values[var_name])

            # Check for variable definition with default
            for var in self.variables:
                if var.name == var_name:
                    if var.default is not None:
                        return str(var.default)

            return match.group(0)  # Keep original if not found

        pattern = r"\$\{([^}]+)\}"
        return re.sub(pattern, replace, text)

    def validate_variables(self, values: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate provided variable values."""
        errors = []

        for var in self.variables:
            value = values.get(var.name)
            valid, error = var.validate(value)
            if not valid:
                errors.append(error)

        return len(errors) == 0, errors

    def render(self, values: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Render the template with provided variable values.
        Returns a job specification dictionary.
        """
        values = values or {}

        # Validate variables
        valid, errors = self.validate_variables(values)
        if not valid:
            raise TemplateError(f"Variable validation failed: {errors}")

        # Build complete values with defaults
        complete_values = {}
        for var in self.variables:
            complete_values[var.name] = var.convert_value(values.get(var.name, var.default))

        # Render command
        command = self.command
        if command:
            command = self.substitute_variables(command, complete_values)

        # Render args
        rendered_args = [self.substitute_variables(arg, complete_values) for arg in self.args]

        # Render environment
        rendered_env = {}
        for key, value in self.environment.items():
            rendered_env[key] = self.substitute_variables(value, complete_values)

        # Build job spec
        job_spec = {
            "name": self.name,
            "template": self.name,
            "template_version": self.version,
            "command": command,
            "args": rendered_args,
            "working_directory": self.working_directory,
            "resources": self.resources.to_dict(),
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "environment": rendered_env,
            "secret_refs": list(self.secrets.keys()),
            "required_tags": self.required_tags,
            "worker_pool": self.worker_pool,
            "queue": self.queue or "default",
            "priority": self.priority,
            "preemptible": self.preemptible,
            "labels": self.labels.copy(),
            "pre_run_commands": self.pre_run_commands.copy(),
            "post_run_commands": self.post_run_commands.copy(),
            "input_artifacts": self.input_artifacts.copy(),
            "output_artifacts": self.output_artifacts.copy(),
        }

        if self.docker_image:
            job_spec["docker_image"] = self.substitute_variables(self.docker_image, complete_values)
            if self.docker_registry:
                job_spec["docker_registry"] = self.docker_registry
            if self.docker_credentials_secret:
                job_spec["docker_credentials_secret"] = self.docker_credentials_secret

        return job_spec

    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary."""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "parent_template": self.parent_template,
            "command": self.command,
            "args": self.args,
            "working_directory": self.working_directory,
            "docker_image": self.docker_image,
            "docker_registry": self.docker_registry,
            "resources": self.resources.to_dict(),
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "environment": self.environment,
            "secrets": self.secrets,
            "required_tags": self.required_tags,
            "worker_pool": self.worker_pool,
            "queue": self.queue,
            "priority": self.priority,
            "preemptible": self.preemptible,
            "variables": [
                {
                    "name": v.name,
                    "type": v.var_type.value,
                    "default": v.default,
                    "required": v.required,
                    "description": v.description,
                    "validation_pattern": v.validation_pattern,
                    "allowed_values": v.allowed_values,
                }
                for v in self.variables
            ],
            "input_artifacts": self.input_artifacts,
            "output_artifacts": self.output_artifacts,
            "pre_run_commands": self.pre_run_commands,
            "post_run_commands": self.post_run_commands,
            "labels": self.labels,
            "annotations": self.annotations,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobTemplate":
        """Create template from dictionary."""
        variables = []
        for v in data.get("variables", []):
            variables.append(
                TemplateVariable(
                    name=v["name"],
                    var_type=VariableType(v.get("type", "string")),
                    default=v.get("default"),
                    required=v.get("required", False),
                    description=v.get("description", ""),
                    validation_pattern=v.get("validation_pattern"),
                    allowed_values=v.get("allowed_values"),
                )
            )

        resources = ResourceRequirements.from_dict(data.get("resources", {}))

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            name=data["name"],
            template_id=data.get("template_id", str(uuid.uuid4())),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            parent_template=data.get("parent_template"),
            command=data.get("command"),
            args=data.get("args", []),
            working_directory=data.get("working_directory"),
            docker_image=data.get("docker_image"),
            docker_registry=data.get("docker_registry"),
            docker_credentials_secret=data.get("docker_credentials_secret"),
            resources=resources,
            timeout_seconds=data.get("timeout_seconds", 3600),
            max_retries=data.get("max_retries", 0),
            retry_delay_seconds=data.get("retry_delay_seconds", 60),
            environment=data.get("environment", {}),
            secrets=data.get("secrets", {}),
            required_tags=data.get("required_tags", []),
            worker_pool=data.get("worker_pool"),
            queue=data.get("queue"),
            priority=data.get("priority", 50),
            preemptible=data.get("preemptible", False),
            variables=variables,
            input_artifacts=data.get("input_artifacts", []),
            output_artifacts=data.get("output_artifacts", []),
            pre_run_commands=data.get("pre_run_commands", []),
            post_run_commands=data.get("post_run_commands", []),
            labels=data.get("labels", {}),
            annotations=data.get("annotations", {}),
            created_at=created_at or datetime.now(timezone.utc),
            updated_at=updated_at or datetime.now(timezone.utc),
            created_by=data.get("created_by"),
        )


class TemplateManager:
    """
    Manager for job templates.
    Handles storage, retrieval, inheritance, and versioning.
    """

    def __init__(self, database=None):
        self.database = database
        self._templates: Dict[str, Dict[str, JobTemplate]] = {}  # name -> version -> template
        self._by_id: Dict[str, JobTemplate] = {}  # template_id -> template

    async def create_template(self, template: JobTemplate) -> JobTemplate:
        """Create a new template."""
        # Initialize version storage for this template name
        if template.name not in self._templates:
            self._templates[template.name] = {}

        # Check if version exists
        if template.version in self._templates[template.name]:
            raise TemplateError(f"Template '{template.name}' version '{template.version}' already exists")

        # Resolve parent template
        if template.parent_template:
            parent = await self.get_template(template.parent_template)
            if not parent:
                raise TemplateError(f"Parent template '{template.parent_template}' not found")
            template = self._inherit_from_parent(template, parent)

        # Store template
        self._templates[template.name][template.version] = template
        self._by_id[template.template_id] = template

        # Persist to database
        if self.database:
            await self._persist_template(template)

        return template

    async def get_template(self, name: str, version: Optional[str] = None) -> Optional[JobTemplate]:
        """Get a template by name and optional version."""
        if name not in self._templates:
            return None

        versions = self._templates[name]

        if version:
            return versions.get(version)

        # Return latest version
        if not versions:
            return None

        latest_version = sorted(versions.keys(), reverse=True)[0]
        return versions[latest_version]

    async def get_template_by_id(self, template_id: str) -> Optional[JobTemplate]:
        """Get a template by ID."""
        return self._by_id.get(template_id)

    async def list_templates(self, include_all_versions: bool = False) -> List[JobTemplate]:
        """List all templates."""
        if include_all_versions:
            return list(self._by_id.values())

        # Return only latest versions
        templates = []
        for name, versions in self._templates.items():
            if versions:
                latest_version = sorted(versions.keys(), reverse=True)[0]
                templates.append(versions[latest_version])

        return templates

    async def update_template(self, name: str, updates: Dict[str, Any], bump_version: bool = True) -> JobTemplate:
        """Update a template, optionally creating a new version."""
        template = await self.get_template(name)
        if not template:
            raise TemplateError(f"Template '{name}' not found")

        # Create updated template
        template_dict = template.to_dict()
        template_dict.update(updates)

        if bump_version:
            # Bump minor version
            parts = template.version.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            template_dict["version"] = ".".join(parts)
            template_dict["template_id"] = str(uuid.uuid4())

        template_dict["updated_at"] = datetime.now(timezone.utc).isoformat()

        new_template = JobTemplate.from_dict(template_dict)

        if bump_version:
            return await self.create_template(new_template)
        else:
            # Update in place
            self._templates[name][template.version] = new_template
            self._by_id[template.template_id] = new_template

            if self.database:
                await self._persist_template(new_template)

            return new_template

    async def delete_template(
        self, name: str, version: Optional[str] = None, delete_all_versions: bool = False
    ) -> bool:
        """Delete a template."""
        if name not in self._templates:
            return False

        if delete_all_versions:
            # Delete all versions
            for v, t in self._templates[name].items():
                del self._by_id[t.template_id]
            del self._templates[name]
        elif version:
            # Delete specific version
            if version in self._templates[name]:
                template = self._templates[name][version]
                del self._templates[name][version]
                del self._by_id[template.template_id]

                # Clean up empty name entry
                if not self._templates[name]:
                    del self._templates[name]
            else:
                return False
        else:
            # Delete latest version
            template = await self.get_template(name)
            if template:
                del self._templates[name][template.version]
                del self._by_id[template.template_id]

                if not self._templates[name]:
                    del self._templates[name]

        return True

    async def render_job(
        self,
        template_name: str,
        variables: Dict[str, Any] = None,
        overrides: Dict[str, Any] = None,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Render a job specification from a template.

        Args:
            template_name: Name of the template
            variables: Variable values for substitution
            overrides: Direct overrides to the rendered job spec
            version: Specific template version to use

        Returns:
            Job specification dictionary
        """
        template = await self.get_template(template_name, version)
        if not template:
            raise TemplateError(f"Template '{template_name}' not found")

        # Render with variables
        job_spec = template.render(variables or {})

        # Apply overrides
        if overrides:
            job_spec.update(overrides)

        return job_spec

    def _inherit_from_parent(self, child: JobTemplate, parent: JobTemplate) -> JobTemplate:
        """Apply inheritance from parent template."""
        # Deep copy parent
        merged = copy.deepcopy(parent.to_dict())

        # Override with child values (only if explicitly set)
        child_dict = child.to_dict()

        # Simple fields - override if set
        simple_fields = [
            "command",
            "docker_image",
            "docker_registry",
            "working_directory",
            "timeout_seconds",
            "max_retries",
            "retry_delay_seconds",
            "worker_pool",
            "queue",
            "priority",
            "preemptible",
        ]

        for field_name in simple_fields:
            if child_dict.get(field_name) is not None:
                merged[field_name] = child_dict[field_name]

        # Merge fields - combine with parent
        merge_fields = ["environment", "labels", "annotations", "secrets"]

        for field_name in merge_fields:
            parent_val = merged.get(field_name, {})
            child_val = child_dict.get(field_name, {})
            merged[field_name] = {**parent_val, **child_val}

        # List fields - extend
        list_fields = [
            "args",
            "required_tags",
            "pre_run_commands",
            "post_run_commands",
            "input_artifacts",
            "output_artifacts",
        ]

        for field_name in list_fields:
            parent_val = merged.get(field_name, [])
            child_val = child_dict.get(field_name, [])
            merged[field_name] = parent_val + child_val

        # Variables - merge by name
        parent_vars = {v["name"]: v for v in merged.get("variables", [])}
        for v in child_dict.get("variables", []):
            parent_vars[v["name"]] = v
        merged["variables"] = list(parent_vars.values())

        # Resources - override individual fields
        merged_resources = merged.get("resources", {})
        child_resources = child_dict.get("resources", {})
        for key, value in child_resources.items():
            if value:
                merged_resources[key] = value
        merged["resources"] = merged_resources

        # Keep child metadata
        merged["name"] = child.name
        merged["template_id"] = child.template_id
        merged["description"] = child.description or parent.description
        merged["version"] = child.version
        merged["parent_template"] = parent.name
        merged["created_at"] = child.created_at.isoformat()
        merged["updated_at"] = child.updated_at.isoformat()
        merged["created_by"] = child.created_by

        return JobTemplate.from_dict(merged)

    async def _persist_template(self, template: JobTemplate):
        """Persist template to database."""
        if not self.database:
            return

        await self.database.execute(
            """
            INSERT OR REPLACE INTO templates
            (template_id, name, version, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                template.template_id,
                template.name,
                template.version,
                json.dumps(template.to_dict()),
                template.created_at.isoformat(),
                template.updated_at.isoformat(),
            ),
        )

    async def load_from_database(self):
        """Load templates from database."""
        if not self.database:
            return

        rows = await self.database.fetch_all("SELECT data FROM templates")

        for row in rows:
            data = json.loads(row["data"])
            template = JobTemplate.from_dict(data)

            if template.name not in self._templates:
                self._templates[template.name] = {}

            self._templates[template.name][template.version] = template
            self._by_id[template.template_id] = template


# Built-in templates
BUILTIN_TEMPLATES = [
    {
        "name": "python-job",
        "description": "Python script execution template",
        "docker_image": "python:3.11-slim",
        "resources": {
            "cpu_cores": 1.0,
            "memory_mb": 512,
        },
        "environment": {
            "PYTHONUNBUFFERED": "1",
        },
        "variables": [
            {
                "name": "script",
                "type": "string",
                "required": True,
                "description": "Python script to execute",
            },
            {
                "name": "requirements",
                "type": "string",
                "description": "pip requirements to install",
            },
        ],
        "pre_run_commands": [
            "pip install -q ${requirements}",
        ],
        "command": "python ${script}",
    },
    {
        "name": "gpu-training",
        "description": "GPU training job template",
        "docker_image": "nvidia/cuda:12.0-runtime-ubuntu22.04",
        "resources": {
            "cpu_cores": 4.0,
            "memory_mb": 16384,
            "gpu_count": 1,
        },
        "timeout_seconds": 86400,  # 24 hours
        "max_retries": 1,
        "required_tags": ["gpu"],
        "environment": {
            "CUDA_VISIBLE_DEVICES": "0",
        },
        "variables": [
            {
                "name": "framework",
                "type": "string",
                "default": "pytorch",
                "allowed_values": ["pytorch", "tensorflow", "jax"],
                "description": "ML framework to use",
            },
        ],
    },
    {
        "name": "batch-processing",
        "description": "Batch data processing template",
        "resources": {
            "cpu_cores": 2.0,
            "memory_mb": 4096,
        },
        "timeout_seconds": 7200,
        "max_retries": 3,
        "retry_delay_seconds": 120,
        "priority": 30,
        "preemptible": True,
        "variables": [
            {
                "name": "input_path",
                "type": "string",
                "required": True,
                "description": "Input data path",
            },
            {
                "name": "output_path",
                "type": "string",
                "required": True,
                "description": "Output data path",
            },
            {
                "name": "chunk_size",
                "type": "integer",
                "default": 1000,
                "description": "Processing chunk size",
            },
        ],
    },
    {
        "name": "ci-build",
        "description": "CI/CD build job template",
        "docker_image": "docker:24-dind",
        "resources": {
            "cpu_cores": 2.0,
            "memory_mb": 4096,
        },
        "timeout_seconds": 1800,  # 30 minutes
        "priority": 80,  # High priority
        "required_tags": ["docker"],
        "variables": [
            {
                "name": "repo_url",
                "type": "string",
                "required": True,
                "description": "Git repository URL",
            },
            {
                "name": "branch",
                "type": "string",
                "default": "main",
                "description": "Git branch to build",
            },
            {
                "name": "dockerfile",
                "type": "string",
                "default": "Dockerfile",
                "description": "Dockerfile path",
            },
        ],
        "pre_run_commands": [
            "git clone --branch ${branch} --depth 1 ${repo_url} /workspace",
        ],
    },
]


async def register_builtin_templates(manager: TemplateManager):
    """Register built-in templates with the manager."""
    for template_data in BUILTIN_TEMPLATES:
        template = JobTemplate.from_dict(template_data)
        try:
            await manager.create_template(template)
        except TemplateError:
            pass  # Already exists
