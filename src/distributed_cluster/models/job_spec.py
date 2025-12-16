"""
Job Specification - تعريف المهمة
==================================

YAML/JSON specification للـ Jobs.

مثال:
```yaml
apiVersion: nebula/v1
kind: Job
metadata:
  name: "train-resnet50"
spec:
  runtime:
    type: "container"
    image: "registry.local/ml/train:1.2.0"
    command: ["python", "train.py"]
    args: ["--epochs", "20"]
  resources:
    cpu: 8
    memoryMiB: 16384
    gpu:
      count: 1
  io:
    inputs:
      - name: "dataset"
        uri: "s3://bucket/data.tar"
        mountPath: "/data"
    outputs:
      - name: "model"
        path: "/work/out"
        uploadUri: "s3://bucket/results/"
  policy:
    retries: 2
    timeoutSeconds: 7200
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
import json


class RuntimeType(str, Enum):
    """نوع بيئة التشغيل."""
    CONTAINER = "container"
    PROCESS = "process"


class NetworkPolicy(str, Enum):
    """سياسة الشبكة."""
    NONE = "none"           # لا شبكة
    HOST = "host"           # شبكة المضيف
    BRIDGE = "bridge"       # جسر (افتراضي)
    EGRESS_DENY = "egress_deny"  # منع الخروج


@dataclass
class RuntimeSpec:
    """مواصفات بيئة التشغيل."""
    type: RuntimeType = RuntimeType.CONTAINER

    # Container
    image: Optional[str] = None
    command: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    working_dir: str = "/work"
    user: Optional[str] = None

    # Process (direct execution)
    executable: Optional[str] = None

    # Security
    privileged: bool = False
    read_only_rootfs: bool = False
    capabilities_add: List[str] = field(default_factory=list)
    capabilities_drop: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> RuntimeSpec:
        """إنشاء من dictionary."""
        runtime_type = RuntimeType(data.get("type", "container"))

        return cls(
            type=runtime_type,
            image=data.get("image"),
            command=data.get("command", []),
            args=data.get("args", []),
            working_dir=data.get("workdir", data.get("working_dir", "/work")),
            user=data.get("user"),
            executable=data.get("executable"),
            privileged=data.get("privileged", False),
            read_only_rootfs=data.get("readOnlyRootfs", data.get("read_only_rootfs", False)),
            capabilities_add=data.get("capabilitiesAdd", data.get("capabilities_add", [])),
            capabilities_drop=data.get("capabilitiesDrop", data.get("capabilities_drop", [])),
        )

    def to_dict(self) -> Dict:
        """تحويل إلى dictionary."""
        return {
            "type": self.type.value,
            "image": self.image,
            "command": self.command,
            "args": self.args,
            "workdir": self.working_dir,
            "user": self.user,
            "executable": self.executable,
            "privileged": self.privileged,
            "readOnlyRootfs": self.read_only_rootfs,
            "capabilitiesAdd": self.capabilities_add,
            "capabilitiesDrop": self.capabilities_drop,
        }


@dataclass
class GPUResourceSpec:
    """مواصفات GPU."""
    count: int = 0
    vendor: Optional[str] = None  # nvidia, amd
    memory_mib: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict) -> GPUResourceSpec:
        if isinstance(data, int):
            return cls(count=data)
        return cls(
            count=data.get("count", 0),
            vendor=data.get("vendor"),
            memory_mib=data.get("memoryMiB", data.get("memory_mib")),
        )

    def to_dict(self) -> Dict:
        return {
            "count": self.count,
            "vendor": self.vendor,
            "memoryMiB": self.memory_mib,
        }


@dataclass
class ResourceRequirements:
    """متطلبات الموارد."""
    cpu: float = 1.0
    memory_mib: int = 512
    gpu: GPUResourceSpec = field(default_factory=GPUResourceSpec)
    custom: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict) -> ResourceRequirements:
        gpu_data = data.get("gpu", {})
        gpu = GPUResourceSpec.from_dict(gpu_data) if gpu_data else GPUResourceSpec()

        return cls(
            cpu=data.get("cpu", 1.0),
            memory_mib=data.get("memoryMiB", data.get("memory_mib", 512)),
            gpu=gpu,
            custom=data.get("custom", {}),
        )

    def to_dict(self) -> Dict:
        return {
            "cpu": self.cpu,
            "memoryMiB": self.memory_mib,
            "gpu": self.gpu.to_dict(),
            "custom": self.custom,
        }


@dataclass
class InputSpec:
    """مواصفات ملف إدخال."""
    name: str
    uri: str
    mount_path: str
    executable: bool = False
    checksum: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> InputSpec:
        return cls(
            name=data["name"],
            uri=data["uri"],
            mount_path=data.get("mountPath", data.get("mount_path", "/input")),
            executable=data.get("executable", False),
            checksum=data.get("checksum"),
        )

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "uri": self.uri,
            "mountPath": self.mount_path,
            "executable": self.executable,
            "checksum": self.checksum,
        }


@dataclass
class OutputSpec:
    """مواصفات ملف إخراج."""
    name: str
    path: str
    upload_uri: str
    required: bool = True

    @classmethod
    def from_dict(cls, data: Dict) -> OutputSpec:
        return cls(
            name=data["name"],
            path=data["path"],
            upload_uri=data.get("uploadUri", data.get("upload_uri", "")),
            required=data.get("required", True),
        )

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "path": self.path,
            "uploadUri": self.upload_uri,
            "required": self.required,
        }


@dataclass
class IOSpec:
    """مواصفات الإدخال/الإخراج."""
    inputs: List[InputSpec] = field(default_factory=list)
    outputs: List[OutputSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> IOSpec:
        inputs = [InputSpec.from_dict(i) for i in data.get("inputs", [])]
        outputs = [OutputSpec.from_dict(o) for o in data.get("outputs", [])]
        return cls(inputs=inputs, outputs=outputs)

    def to_dict(self) -> Dict:
        return {
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
        }


@dataclass
class PlacementConstraints:
    """قيود التوزيع."""
    require_tags: List[str] = field(default_factory=list)
    avoid_workers: List[str] = field(default_factory=list)
    prefer_workers: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> PlacementConstraints:
        return cls(
            require_tags=data.get("requireTags", data.get("require_tags", [])),
            avoid_workers=data.get("avoidWorkers", data.get("avoid_workers", [])),
            prefer_workers=data.get("preferWorkers", data.get("prefer_workers", [])),
        )

    def to_dict(self) -> Dict:
        return {
            "requireTags": self.require_tags,
            "avoidWorkers": self.avoid_workers,
            "preferWorkers": self.prefer_workers,
        }


@dataclass
class ExecutionPolicy:
    """سياسة التنفيذ."""
    retries: int = 3
    timeout_seconds: int = 3600
    network: NetworkPolicy = NetworkPolicy.BRIDGE
    placement: PlacementConstraints = field(default_factory=PlacementConstraints)

    # Retry policy
    retry_delay_seconds: int = 30
    retry_backoff_multiplier: float = 2.0

    @classmethod
    def from_dict(cls, data: Dict) -> ExecutionPolicy:
        network = NetworkPolicy(data.get("network", "bridge"))
        placement_data = data.get("placement", {})
        placement = PlacementConstraints.from_dict(placement_data) if placement_data else PlacementConstraints()

        return cls(
            retries=data.get("retries", 3),
            timeout_seconds=data.get("timeoutSeconds", data.get("timeout_seconds", 3600)),
            network=network,
            placement=placement,
            retry_delay_seconds=data.get("retryDelaySeconds", data.get("retry_delay_seconds", 30)),
            retry_backoff_multiplier=data.get("retryBackoffMultiplier", data.get("retry_backoff_multiplier", 2.0)),
        )

    def to_dict(self) -> Dict:
        return {
            "retries": self.retries,
            "timeoutSeconds": self.timeout_seconds,
            "network": self.network.value,
            "placement": self.placement.to_dict(),
            "retryDelaySeconds": self.retry_delay_seconds,
            "retryBackoffMultiplier": self.retry_backoff_multiplier,
        }


@dataclass
class JobMetadata:
    """معلومات وصفية للـ Job."""
    name: str
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    owner: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> JobMetadata:
        return cls(
            name=data["name"],
            labels=data.get("labels", {}),
            annotations=data.get("annotations", {}),
            owner=data.get("owner"),
        )

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "labels": self.labels,
            "annotations": self.annotations,
            "owner": self.owner,
        }


@dataclass
class JobSpecification:
    """
    مواصفات Job الكاملة.

    هذا هو الـ "عقد" بين المستخدم والنظام.
    """
    api_version: str
    kind: str
    metadata: JobMetadata
    runtime: RuntimeSpec
    resources: ResourceRequirements
    io: IOSpec = field(default_factory=IOSpec)
    policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    environment: Dict[str, str] = field(default_factory=dict)
    secrets: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> JobSpecification:
        """إنشاء من dictionary."""
        spec = data.get("spec", data)  # Support both wrapped and unwrapped

        return cls(
            api_version=data.get("apiVersion", "nebula/v1"),
            kind=data.get("kind", "Job"),
            metadata=JobMetadata.from_dict(data.get("metadata", {"name": "unnamed"})),
            runtime=RuntimeSpec.from_dict(spec.get("runtime", {})),
            resources=ResourceRequirements.from_dict(spec.get("resources", {})),
            io=IOSpec.from_dict(spec.get("io", {})),
            policy=ExecutionPolicy.from_dict(spec.get("policy", {})),
            environment=spec.get("environment", spec.get("env", {})),
            secrets=spec.get("secrets", []),
        )

    @classmethod
    def from_yaml(cls, yaml_content: str) -> JobSpecification:
        """إنشاء من YAML."""
        try:
            import yaml
            data = yaml.safe_load(yaml_content)
            return cls.from_dict(data)
        except ImportError:
            raise RuntimeError("PyYAML is required for YAML parsing. Install with: pip install pyyaml")

    @classmethod
    def from_json(cls, json_content: str) -> JobSpecification:
        """إنشاء من JSON."""
        data = json.loads(json_content)
        return cls.from_dict(data)

    @classmethod
    def from_file(cls, filepath: str) -> JobSpecification:
        """إنشاء من ملف (YAML or JSON)."""
        with open(filepath) as f:
            content = f.read()

        if filepath.endswith(('.yaml', '.yml')):
            return cls.from_yaml(content)
        elif filepath.endswith('.json'):
            return cls.from_json(content)
        else:
            # Try YAML first, then JSON
            try:
                return cls.from_yaml(content)
            except Exception:
                return cls.from_json(content)

    def to_dict(self) -> Dict:
        """تحويل إلى dictionary."""
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata.to_dict(),
            "spec": {
                "runtime": self.runtime.to_dict(),
                "resources": self.resources.to_dict(),
                "io": self.io.to_dict(),
                "policy": self.policy.to_dict(),
                "environment": self.environment,
                "secrets": self.secrets,
            },
        }

    def to_yaml(self) -> str:
        """تحويل إلى YAML."""
        try:
            import yaml
            return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)
        except ImportError:
            raise RuntimeError("PyYAML is required. Install with: pip install pyyaml")

    def to_json(self, indent: int = 2) -> str:
        """تحويل إلى JSON."""
        return json.dumps(self.to_dict(), indent=indent)

    def validate(self) -> List[str]:
        """
        التحقق من صحة المواصفات.

        Returns:
            قائمة الأخطاء (فارغة إذا صالح)
        """
        errors = []

        # Metadata
        if not self.metadata.name:
            errors.append("metadata.name is required")

        # Runtime
        if self.runtime.type == RuntimeType.CONTAINER:
            if not self.runtime.image:
                errors.append("runtime.image is required for container runtime")
        elif self.runtime.type == RuntimeType.PROCESS:
            if not self.runtime.executable and not self.runtime.command:
                errors.append("runtime.executable or runtime.command is required for process runtime")

        # Resources
        if self.resources.cpu <= 0:
            errors.append("resources.cpu must be positive")
        if self.resources.memory_mib <= 0:
            errors.append("resources.memoryMiB must be positive")

        # IO
        for i, inp in enumerate(self.io.inputs):
            if not inp.name:
                errors.append(f"io.inputs[{i}].name is required")
            if not inp.uri:
                errors.append(f"io.inputs[{i}].uri is required")

        for i, out in enumerate(self.io.outputs):
            if not out.name:
                errors.append(f"io.outputs[{i}].name is required")
            if not out.path:
                errors.append(f"io.outputs[{i}].path is required")

        # Policy
        if self.policy.timeout_seconds <= 0:
            errors.append("policy.timeoutSeconds must be positive")
        if self.policy.retries < 0:
            errors.append("policy.retries cannot be negative")

        return errors


def create_simple_job_spec(
    name: str,
    image: str,
    command: List[str],
    cpu: float = 1.0,
    memory_mib: int = 512,
    gpu_count: int = 0,
    timeout_seconds: int = 3600,
    environment: Optional[Dict[str, str]] = None,
) -> JobSpecification:
    """
    إنشاء مواصفات job بسيطة.

    Helper function للحالات الشائعة.
    """
    return JobSpecification(
        api_version="nebula/v1",
        kind="Job",
        metadata=JobMetadata(name=name),
        runtime=RuntimeSpec(
            type=RuntimeType.CONTAINER,
            image=image,
            command=command,
        ),
        resources=ResourceRequirements(
            cpu=cpu,
            memory_mib=memory_mib,
            gpu=GPUResourceSpec(count=gpu_count),
        ),
        policy=ExecutionPolicy(timeout_seconds=timeout_seconds),
        environment=environment or {},
    )
