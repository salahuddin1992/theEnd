"""
Workflow Definitions - تعريفات سير العمل
=========================================

Support for loading workflows from YAML and JSON files.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StepDefinition:
    """تعريف خطوة في سير العمل."""
    id: str
    name: str
    command: str
    image: Optional[str] = None
    cpu: float = 1.0
    memory: int = 512
    gpu: int = 0
    timeout: int = 3600
    env: Dict[str, str] = field(default_factory=dict)
    depends_on: List[Any] = field(default_factory=list)
    retry_count: int = 0
    retry_delay: int = 60
    condition: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StepDefinition:
        """إنشاء من dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", data.get("id", "")),
            command=data.get("command", ""),
            image=data.get("image"),
            cpu=data.get("cpu", 1.0),
            memory=data.get("memory", 512),
            gpu=data.get("gpu", 0),
            timeout=data.get("timeout", 3600),
            env=data.get("env", {}),
            depends_on=data.get("depends_on", []),
            retry_count=data.get("retry_count", 0),
            retry_delay=data.get("retry_delay", 60),
            condition=data.get("condition"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        result = {
            "id": self.id,
            "name": self.name,
            "command": self.command,
            "cpu": self.cpu,
            "memory": self.memory,
            "timeout": self.timeout,
        }

        if self.image:
            result["image"] = self.image
        if self.gpu:
            result["gpu"] = self.gpu
        if self.env:
            result["env"] = self.env
        if self.depends_on:
            result["depends_on"] = self.depends_on
        if self.retry_count:
            result["retry_count"] = self.retry_count
            result["retry_delay"] = self.retry_delay
        if self.condition:
            result["condition"] = self.condition

        return result


@dataclass
class WorkflowDefinition:
    """تعريف سير العمل الكامل."""
    name: str
    description: str = ""
    version: str = "1.0.0"
    steps: List[StepDefinition] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    defaults: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    timeout: int = 86400  # 24 hours default
    notifications: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowDefinition:
        """إنشاء من dictionary."""
        steps = [
            StepDefinition.from_dict(s)
            for s in data.get("steps", [])
        ]

        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            steps=steps,
            parameters=data.get("parameters", {}),
            defaults=data.get("defaults", {}),
            tags=data.get("tags", []),
            timeout=data.get("timeout", 86400),
            notifications=data.get("notifications", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "steps": [s.to_dict() for s in self.steps],
            "parameters": self.parameters,
            "defaults": self.defaults,
            "tags": self.tags,
            "timeout": self.timeout,
            "notifications": self.notifications,
        }

    def validate(self) -> tuple[bool, List[str]]:
        """
        التحقق من صحة التعريف.

        Returns:
            (is_valid, list of errors)
        """
        errors = []

        if not self.name:
            errors.append("Workflow name is required")

        if not self.steps:
            errors.append("At least one step is required")

        # Check step IDs are unique
        step_ids = [s.id for s in self.steps]
        if len(step_ids) != len(set(step_ids)):
            errors.append("Step IDs must be unique")

        # Check dependencies exist
        for step in self.steps:
            for dep in step.depends_on:
                dep_id = dep if isinstance(dep, str) else list(dep.keys())[0]
                if dep_id not in step_ids:
                    errors.append(f"Step {step.id} depends on non-existent step {dep_id}")

        # Check for cycles (simple check)
        visited = set()
        for step in self.steps:
            if step.id in visited:
                continue
            path = []
            if self._has_cycle(step.id, step_ids, visited, path):
                errors.append(f"Circular dependency detected: {' -> '.join(path)}")

        return len(errors) == 0, errors

    def _has_cycle(
        self,
        step_id: str,
        all_ids: List[str],
        visited: set,
        path: List[str],
    ) -> bool:
        """كشف الدورات."""
        if step_id in path:
            path.append(step_id)
            return True

        if step_id in visited:
            return False

        path.append(step_id)

        step = next((s for s in self.steps if s.id == step_id), None)
        if step:
            for dep in step.depends_on:
                dep_id = dep if isinstance(dep, str) else list(dep.keys())[0]
                if self._has_cycle(dep_id, all_ids, visited, path):
                    return True

        path.pop()
        visited.add(step_id)
        return False


def load_workflow_from_yaml(yaml_content: str) -> WorkflowDefinition:
    """
    تحميل workflow من YAML.

    Example YAML:
        name: data-pipeline
        description: Daily data processing pipeline
        version: "1.0.0"

        parameters:
          date:
            type: string
            default: "today"
          batch_size:
            type: integer
            default: 1000

        steps:
          - id: extract
            name: Extract Data
            command: python extract.py --date ${date}
            cpu: 2
            memory: 2048

          - id: transform
            name: Transform Data
            command: python transform.py --batch ${batch_size}
            cpu: 4
            memory: 4096
            depends_on:
              - extract

          - id: load
            name: Load Data
            command: python load.py
            cpu: 2
            memory: 2048
            depends_on:
              - transform

        notifications:
          on_success:
            - slack://channel/data-team
          on_failure:
            - email://data-team@company.com
            - slack://channel/alerts
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("YAML support requires PyYAML: pip install pyyaml")

    data = yaml.safe_load(yaml_content)
    definition = WorkflowDefinition.from_dict(data)

    # Validate
    is_valid, errors = definition.validate()
    if not is_valid:
        raise ValueError(f"Invalid workflow: {', '.join(errors)}")

    return definition


def load_workflow_from_json(json_content: str) -> WorkflowDefinition:
    """
    تحميل workflow من JSON.

    Example JSON:
        {
          "name": "ml-training",
          "description": "ML model training pipeline",
          "version": "2.1.0",
          "steps": [
            {
              "id": "preprocess",
              "name": "Preprocess Data",
              "command": "python preprocess.py",
              "cpu": 4,
              "memory": 8192
            },
            {
              "id": "train",
              "name": "Train Model",
              "command": "python train.py --epochs 100",
              "cpu": 8,
              "memory": 16384,
              "gpu": 1,
              "image": "pytorch/pytorch:2.0-cuda11.8",
              "depends_on": ["preprocess"]
            },
            {
              "id": "evaluate",
              "name": "Evaluate Model",
              "command": "python evaluate.py",
              "cpu": 4,
              "memory": 8192,
              "gpu": 1,
              "depends_on": [
                {"train": "success"}
              ]
            }
          ]
        }
    """
    data = json.loads(json_content)
    definition = WorkflowDefinition.from_dict(data)

    # Validate
    is_valid, errors = definition.validate()
    if not is_valid:
        raise ValueError(f"Invalid workflow: {', '.join(errors)}")

    return definition


def load_workflow_from_file(file_path: str) -> WorkflowDefinition:
    """
    تحميل workflow من ملف.

    يدعم .yaml, .yml, .json
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if file_path.endswith((".yaml", ".yml")):
        return load_workflow_from_yaml(content)
    elif file_path.endswith(".json"):
        return load_workflow_from_json(content)
    else:
        # Try JSON first, then YAML
        try:
            return load_workflow_from_json(content)
        except json.JSONDecodeError:
            return load_workflow_from_yaml(content)


# =============================================================================
# Workflow Templates
# =============================================================================

WORKFLOW_TEMPLATES = {
    "etl": {
        "name": "ETL Pipeline",
        "description": "Extract, Transform, Load data pipeline",
        "steps": [
            {
                "id": "extract",
                "name": "Extract",
                "command": "python extract.py",
                "cpu": 2,
                "memory": 2048,
            },
            {
                "id": "transform",
                "name": "Transform",
                "command": "python transform.py",
                "cpu": 4,
                "memory": 4096,
                "depends_on": ["extract"],
            },
            {
                "id": "load",
                "name": "Load",
                "command": "python load.py",
                "cpu": 2,
                "memory": 2048,
                "depends_on": ["transform"],
            },
        ],
    },
    "ml-training": {
        "name": "ML Training Pipeline",
        "description": "Machine learning model training",
        "steps": [
            {
                "id": "preprocess",
                "name": "Preprocess Data",
                "command": "python preprocess.py",
                "cpu": 4,
                "memory": 8192,
            },
            {
                "id": "train",
                "name": "Train Model",
                "command": "python train.py",
                "cpu": 8,
                "memory": 16384,
                "gpu": 1,
                "depends_on": ["preprocess"],
            },
            {
                "id": "evaluate",
                "name": "Evaluate",
                "command": "python evaluate.py",
                "cpu": 4,
                "memory": 8192,
                "depends_on": ["train"],
            },
            {
                "id": "deploy",
                "name": "Deploy Model",
                "command": "python deploy.py",
                "cpu": 2,
                "memory": 2048,
                "depends_on": [{"evaluate": "success"}],
            },
        ],
    },
    "ci-cd": {
        "name": "CI/CD Pipeline",
        "description": "Continuous Integration and Deployment",
        "steps": [
            {
                "id": "checkout",
                "name": "Checkout Code",
                "command": "git checkout ${branch}",
                "cpu": 1,
                "memory": 512,
            },
            {
                "id": "test",
                "name": "Run Tests",
                "command": "pytest tests/",
                "cpu": 2,
                "memory": 2048,
                "depends_on": ["checkout"],
            },
            {
                "id": "build",
                "name": "Build",
                "command": "docker build -t ${image}:${tag} .",
                "cpu": 4,
                "memory": 4096,
                "depends_on": ["test"],
            },
            {
                "id": "push",
                "name": "Push Image",
                "command": "docker push ${image}:${tag}",
                "cpu": 1,
                "memory": 1024,
                "depends_on": ["build"],
            },
            {
                "id": "deploy",
                "name": "Deploy",
                "command": "kubectl apply -f deployment.yaml",
                "cpu": 1,
                "memory": 512,
                "depends_on": ["push"],
            },
        ],
    },
    "parallel-processing": {
        "name": "Parallel Processing",
        "description": "Fan-out / Fan-in pattern",
        "steps": [
            {
                "id": "split",
                "name": "Split Data",
                "command": "python split.py",
                "cpu": 2,
                "memory": 2048,
            },
            {
                "id": "process-1",
                "name": "Process Chunk 1",
                "command": "python process.py --chunk 1",
                "cpu": 4,
                "memory": 4096,
                "depends_on": ["split"],
            },
            {
                "id": "process-2",
                "name": "Process Chunk 2",
                "command": "python process.py --chunk 2",
                "cpu": 4,
                "memory": 4096,
                "depends_on": ["split"],
            },
            {
                "id": "process-3",
                "name": "Process Chunk 3",
                "command": "python process.py --chunk 3",
                "cpu": 4,
                "memory": 4096,
                "depends_on": ["split"],
            },
            {
                "id": "merge",
                "name": "Merge Results",
                "command": "python merge.py",
                "cpu": 2,
                "memory": 4096,
                "depends_on": ["process-1", "process-2", "process-3"],
            },
        ],
    },
}


def get_workflow_template(template_name: str) -> WorkflowDefinition:
    """الحصول على قالب workflow."""
    if template_name not in WORKFLOW_TEMPLATES:
        raise ValueError(f"Unknown template: {template_name}")

    return WorkflowDefinition.from_dict(WORKFLOW_TEMPLATES[template_name])


def list_workflow_templates() -> List[Dict[str, str]]:
    """قائمة القوالب المتاحة."""
    return [
        {"name": name, "description": data.get("description", "")}
        for name, data in WORKFLOW_TEMPLATES.items()
    ]
