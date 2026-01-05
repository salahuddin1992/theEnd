"""
Configuration - إعدادات النظام
================================

إعدادات Master و Worker والـ Cluster ككل.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MasterConfig:
    """إعدادات الـ Master / Control Plane."""

    # Network - nosec B104: 0.0.0.0 is intentional for distributed system binding
    host: str = "0.0.0.0"
    port: int = 8765
    api_prefix: str = "/api/v1"

    # TLS (للإنتاج)
    tls_enabled: bool = False
    tls_cert_file: Optional[str] = None
    tls_key_file: Optional[str] = None

    # Database/State
    state_dir: Path = field(default_factory=lambda: Path("./cluster_state"))
    db_file: str = "cluster.db"

    # Worker management
    heartbeat_timeout_seconds: int = 30  # كم ينتظر قبل يعتبر worker offline
    heartbeat_interval_seconds: int = 10
    worker_cleanup_interval_seconds: int = 60

    # Job scheduling
    scheduler_interval_seconds: float = 1.0  # كل كم يشتغل الـ scheduler
    max_concurrent_jobs_per_worker: int = 10
    job_timeout_default_seconds: int = 3600
    job_max_retries_default: int = 3

    # Multi-master (HA)
    enable_ha: bool = False
    etcd_endpoints: list[str] = field(default_factory=list)
    leader_lease_ttl_seconds: int = 15

    # Authentication
    auth_enabled: bool = False
    auth_secret_key: Optional[str] = None
    api_keys: list[str] = field(default_factory=list)

    # CORS - إعدادات CORS للأمان
    # قائمة فارغة = لا CORS (أكثر أماناً)
    # ["*"] = كل المواقع (غير آمن - فقط للتطوير)
    # ["https://example.com"] = مواقع محددة (موصى به للإنتاج)
    cors_allowed_origins: list[str] = field(default_factory=list)
    cors_allow_credentials: bool = False

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "api_prefix": self.api_prefix,
            "tls_enabled": self.tls_enabled,
            "state_dir": str(self.state_dir),
            "heartbeat_timeout_seconds": self.heartbeat_timeout_seconds,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "scheduler_interval_seconds": self.scheduler_interval_seconds,
            "max_concurrent_jobs_per_worker": self.max_concurrent_jobs_per_worker,
            "enable_ha": self.enable_ha,
            "auth_enabled": self.auth_enabled,
            "cors_allowed_origins": self.cors_allowed_origins,
            "cors_allow_credentials": self.cors_allow_credentials,
            "log_level": self.log_level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MasterConfig:
        """إنشاء من dictionary."""
        return cls(
            host=data.get("host", "0.0.0.0"),
            port=data.get("port", 8765),
            api_prefix=data.get("api_prefix", "/api/v1"),
            tls_enabled=data.get("tls_enabled", False),
            tls_cert_file=data.get("tls_cert_file"),
            tls_key_file=data.get("tls_key_file"),
            state_dir=Path(data.get("state_dir", "./cluster_state")),
            db_file=data.get("db_file", "cluster.db"),
            heartbeat_timeout_seconds=data.get("heartbeat_timeout_seconds", 30),
            heartbeat_interval_seconds=data.get("heartbeat_interval_seconds", 10),
            worker_cleanup_interval_seconds=data.get("worker_cleanup_interval_seconds", 60),
            scheduler_interval_seconds=data.get("scheduler_interval_seconds", 1.0),
            max_concurrent_jobs_per_worker=data.get("max_concurrent_jobs_per_worker", 10),
            job_timeout_default_seconds=data.get("job_timeout_default_seconds", 3600),
            job_max_retries_default=data.get("job_max_retries_default", 3),
            enable_ha=data.get("enable_ha", False),
            etcd_endpoints=data.get("etcd_endpoints", []),
            leader_lease_ttl_seconds=data.get("leader_lease_ttl_seconds", 15),
            auth_enabled=data.get("auth_enabled", False),
            auth_secret_key=data.get("auth_secret_key"),
            api_keys=data.get("api_keys", []),
            cors_allowed_origins=data.get("cors_allowed_origins", []),
            cors_allow_credentials=data.get("cors_allow_credentials", False),
            log_level=data.get("log_level", "INFO"),
            log_file=data.get("log_file"),
        )

    @classmethod
    def from_env(cls) -> MasterConfig:
        """إنشاء من environment variables."""
        cors_origins = os.getenv("DC_CORS_ORIGINS", "")
        return cls(
            host=os.getenv("DC_MASTER_HOST", "0.0.0.0"),
            port=int(os.getenv("DC_MASTER_PORT", "8765")),
            heartbeat_timeout_seconds=int(os.getenv("DC_HEARTBEAT_TIMEOUT", "30")),
            auth_enabled=os.getenv("DC_AUTH_ENABLED", "false").lower() == "true",
            auth_secret_key=os.getenv("DC_AUTH_SECRET"),
            cors_allowed_origins=cors_origins.split(",") if cors_origins else [],
            cors_allow_credentials=os.getenv("DC_CORS_CREDENTIALS", "false").lower() == "true",
            log_level=os.getenv("DC_LOG_LEVEL", "INFO"),
        )


@dataclass
class WorkerConfig:
    """إعدادات الـ Worker Agent."""

    # Identity
    worker_name: Optional[str] = None  # اسم مخصص (اختياري)

    # Network
    host: str = "0.0.0.0"
    port: int = 8766

    # Master connection
    master_url: str = "http://localhost:8765"
    master_api_key: Optional[str] = None

    # Heartbeat
    heartbeat_interval_seconds: int = 10

    # Resources
    cpu_cores_override: Optional[float] = None  # override التلقائي
    memory_mb_override: Optional[int] = None
    gpu_indices: Optional[list[int]] = None  # أي GPUs يستخدم

    # Tags and labels
    tags: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)

    # Job execution
    work_dir: Path = field(default_factory=lambda: Path("./worker_jobs"))
    docker_enabled: bool = True
    docker_default_network: str = "bridge"
    docker_pull_policy: str = "if-not-present"  # always, if-not-present, never

    # === Execution Mode - وضع التنفيذ ===
    # auto: تلقائي - Docker إذا متاح، وإلا مباشر
    # docker: Docker فقط (يفشل إذا غير متاح)
    # direct: مباشر على الحاسوب بدون Docker
    execution_mode: str = "auto"

    # === Docker Full Permissions - صلاحيات Docker الكاملة ===
    docker_privileged: bool = False  # --privileged mode
    docker_capabilities: list[str] = field(default_factory=list)  # capabilities إضافية
    docker_allow_host_network: bool = False  # السماح بشبكة المضيف
    docker_allow_host_pid: bool = False  # السماح بـ PID namespace المضيف
    docker_allow_all_devices: bool = False  # السماح بكل الأجهزة

    # === Shell Configuration - إعدادات الـ Shell ===
    # أنواع الـ Shell المدعومة:
    # - cmd: Windows Command Prompt
    # - powershell: Windows PowerShell 5.1
    # - pwsh: PowerShell 7 (Cross-platform)
    # - bash: Linux Bash
    # - sh: POSIX shell
    # - zsh: Z shell
    # - wsl: Default WSL
    # - ubuntu: Ubuntu via WSL
    # - debian: Debian via WSL
    # - kali: Kali Linux via WSL
    # - git-bash: Git Bash (MINGW)
    # - auto: تلقائي
    default_shell: str = "auto"
    shell_run_as_admin: bool = True  # تشغيل كمدير (Admin/Root)
    shell_timeout: int = 3600  # مهلة الـ Shell بالثواني
    shell_enable_wsl: bool = True  # تفعيل WSL
    shell_wsl_default_user: str = "root"  # المستخدم الافتراضي في WSL (root للصلاحيات الكاملة)

    # Security
    sandbox_enabled: bool = True
    allowed_commands: list[str] = field(default_factory=list)  # فارغ = كلها مسموحة
    blocked_commands: list[str] = field(default_factory=list)

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "worker_name": self.worker_name,
            "host": self.host,
            "port": self.port,
            "master_url": self.master_url,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "tags": self.tags,
            "labels": self.labels,
            "work_dir": str(self.work_dir),
            "docker_enabled": self.docker_enabled,
            "sandbox_enabled": self.sandbox_enabled,
            "log_level": self.log_level,
            # Execution mode and Docker permissions
            "execution_mode": self.execution_mode,
            "docker_privileged": self.docker_privileged,
            "docker_capabilities": self.docker_capabilities,
            "docker_allow_host_network": self.docker_allow_host_network,
            "docker_allow_host_pid": self.docker_allow_host_pid,
            "docker_allow_all_devices": self.docker_allow_all_devices,
            # Shell configuration
            "default_shell": self.default_shell,
            "shell_run_as_admin": self.shell_run_as_admin,
            "shell_timeout": self.shell_timeout,
            "shell_enable_wsl": self.shell_enable_wsl,
            "shell_wsl_default_user": self.shell_wsl_default_user,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkerConfig:
        """إنشاء من dictionary."""
        return cls(
            worker_name=data.get("worker_name"),
            host=data.get("host", "0.0.0.0"),
            port=data.get("port", 8766),
            master_url=data.get("master_url", "http://localhost:8765"),
            master_api_key=data.get("master_api_key"),
            heartbeat_interval_seconds=data.get("heartbeat_interval_seconds", 10),
            cpu_cores_override=data.get("cpu_cores_override"),
            memory_mb_override=data.get("memory_mb_override"),
            gpu_indices=data.get("gpu_indices"),
            tags=data.get("tags", []),
            labels=data.get("labels", {}),
            work_dir=Path(data.get("work_dir", "./worker_jobs")),
            docker_enabled=data.get("docker_enabled", True),
            docker_default_network=data.get("docker_default_network", "bridge"),
            docker_pull_policy=data.get("docker_pull_policy", "if-not-present"),
            # Execution mode and Docker permissions
            execution_mode=data.get("execution_mode", "auto"),
            docker_privileged=data.get("docker_privileged", False),
            docker_capabilities=data.get("docker_capabilities", []),
            docker_allow_host_network=data.get("docker_allow_host_network", False),
            docker_allow_host_pid=data.get("docker_allow_host_pid", False),
            docker_allow_all_devices=data.get("docker_allow_all_devices", False),
            # Shell configuration
            default_shell=data.get("default_shell", "auto"),
            shell_run_as_admin=data.get("shell_run_as_admin", True),
            shell_timeout=data.get("shell_timeout", 3600),
            shell_enable_wsl=data.get("shell_enable_wsl", True),
            shell_wsl_default_user=data.get("shell_wsl_default_user", "root"),
            sandbox_enabled=data.get("sandbox_enabled", True),
            allowed_commands=data.get("allowed_commands", []),
            blocked_commands=data.get("blocked_commands", []),
            log_level=data.get("log_level", "INFO"),
            log_file=data.get("log_file"),
        )

    @classmethod
    def from_env(cls) -> WorkerConfig:
        """إنشاء من environment variables."""
        tags = os.getenv("DC_WORKER_TAGS", "")
        capabilities = os.getenv("DC_DOCKER_CAPABILITIES", "")
        return cls(
            worker_name=os.getenv("DC_WORKER_NAME"),
            host=os.getenv("DC_WORKER_HOST", "0.0.0.0"),
            port=int(os.getenv("DC_WORKER_PORT", "8766")),
            master_url=os.getenv("DC_MASTER_URL", "http://localhost:8765"),
            master_api_key=os.getenv("DC_API_KEY"),
            heartbeat_interval_seconds=int(os.getenv("DC_HEARTBEAT_INTERVAL", "10")),
            tags=tags.split(",") if tags else [],
            docker_enabled=os.getenv("DC_DOCKER_ENABLED", "true").lower() == "true",
            log_level=os.getenv("DC_LOG_LEVEL", "INFO"),
            # Execution mode and Docker permissions from environment
            execution_mode=os.getenv("DC_EXECUTION_MODE", "auto"),  # auto, docker, direct
            docker_privileged=os.getenv("DC_DOCKER_PRIVILEGED", "false").lower() == "true",
            docker_capabilities=capabilities.split(",") if capabilities else [],
            docker_allow_host_network=os.getenv("DC_DOCKER_HOST_NETWORK", "false").lower() == "true",
            docker_allow_host_pid=os.getenv("DC_DOCKER_HOST_PID", "false").lower() == "true",
            docker_allow_all_devices=os.getenv("DC_DOCKER_ALL_DEVICES", "false").lower() == "true",
            # Shell configuration from environment
            default_shell=os.getenv("DC_DEFAULT_SHELL", "auto"),
            shell_run_as_admin=os.getenv("DC_SHELL_RUN_AS_ADMIN", "true").lower() == "true",
            shell_timeout=int(os.getenv("DC_SHELL_TIMEOUT", "3600")),
            shell_enable_wsl=os.getenv("DC_SHELL_ENABLE_WSL", "true").lower() == "true",
            shell_wsl_default_user=os.getenv("DC_SHELL_WSL_USER", "root"),
        )


@dataclass
class ClusterConfig:
    """إعدادات الـ Cluster الكاملة."""

    master: MasterConfig = field(default_factory=MasterConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)

    # Storage
    artifact_storage_type: str = "local"  # local, s3, nfs
    artifact_storage_path: str = "./artifacts"
    artifact_storage_s3_bucket: Optional[str] = None
    artifact_storage_s3_prefix: str = "cluster-artifacts/"

    @classmethod
    def load(cls, path: str | Path) -> ClusterConfig:
        """تحميل من ملف JSON أو YAML."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            if path.suffix in (".yaml", ".yml"):
                import yaml

                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        return cls(
            master=MasterConfig.from_dict(data.get("master", {})),
            worker=WorkerConfig.from_dict(data.get("worker", {})),
            artifact_storage_type=data.get("artifact_storage_type", "local"),
            artifact_storage_path=data.get("artifact_storage_path", "./artifacts"),
        )

    def save(self, path: str | Path) -> None:
        """حفظ في ملف JSON."""
        data = {
            "master": self.master.to_dict(),
            "worker": self.worker.to_dict(),
            "artifact_storage_type": self.artifact_storage_type,
            "artifact_storage_path": self.artifact_storage_path,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
