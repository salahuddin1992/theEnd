"""
Configuration Management - إدارة الإعدادات
==========================================

نظام إعدادات موحد يدعم:
- ملفات YAML
- متغيرات البيئة
- القيم الافتراضية
- التحقق من الصحة
- Hot reload
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field, fields, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Any, Type, TypeVar, get_type_hints
import logging
import json

logger = logging.getLogger(__name__)

T = TypeVar('T')


def _get_default_temp_dir() -> str:
    """Get platform-appropriate temporary directory for job files."""
    if sys.platform == "win32":
        # On Windows, use %TEMP%/nebula or %LOCALAPPDATA%/nebula
        base = os.environ.get("LOCALAPPDATA", tempfile.gettempdir())
        return str(Path(base) / "nebula")
    return "/tmp/nebula"


class ConfigError(Exception):
    """خطأ في الإعدادات."""
    pass


# =============================================================================
# Configuration Sections
# =============================================================================

@dataclass
class ServerConfig:
    """إعدادات السيرفر."""
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 4
    debug: bool = False

    # TLS
    tls_enabled: bool = False
    tls_cert_path: Optional[str] = None
    tls_key_path: Optional[str] = None
    tls_ca_path: Optional[str] = None


@dataclass
class GRPCConfig:
    """إعدادات gRPC."""
    enabled: bool = True
    port: int = 50051
    max_message_size_mb: int = 64
    keepalive_time_seconds: int = 30
    keepalive_timeout_seconds: int = 10


@dataclass
class DatabaseConfig:
    """إعدادات قاعدة البيانات."""
    type: str = "sqlite"  # sqlite, postgresql
    path: str = "./data/cluster.db"  # SQLite
    host: str = "localhost"  # PostgreSQL
    port: int = 5432
    database: str = "nebula"
    user: str = ""
    password: str = ""
    pool_size: int = 5
    max_overflow: int = 10


@dataclass
class SecurityConfig:
    """إعدادات الأمان."""
    secret_key: str = ""  # JWT secret
    token_expiry_hours: int = 24
    enrollment_mode: str = "auto_approve"  # auto_approve, token, allowlist
    enrollment_tokens: List[str] = field(default_factory=list)
    allowed_fingerprints: List[str] = field(default_factory=list)

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60


@dataclass
class SchedulerConfig:
    """إعدادات المجدول."""
    policy: str = "best_fit"  # best_fit, worst_fit, round_robin
    scoring_profile: str = "best_fit"  # best_fit, spread, locality_first, reliable
    scheduler_interval_seconds: float = 1.0
    max_pending_jobs: int = 10000

    # Lease
    lease_duration_seconds: int = 300
    lease_renewal_threshold_seconds: int = 60
    max_lease_renewals: int = 10


@dataclass
class RetryConfig:
    """إعدادات إعادة المحاولة."""
    max_retries: int = 3
    strategy: str = "exponential"  # immediate, linear, exponential, fibonacci
    initial_delay_seconds: float = 5.0
    max_delay_seconds: float = 300.0
    multiplier: float = 2.0
    jitter: bool = True


@dataclass
class WorkerAgentConfig:
    """إعدادات Worker Agent."""
    heartbeat_interval_seconds: int = 30
    job_poll_interval_seconds: int = 5
    max_concurrent_jobs: int = 10

    # Resources
    cpu_cores_override: Optional[int] = None
    memory_mb_override: Optional[int] = None
    gpu_indices: List[int] = field(default_factory=list)

    # Docker
    docker_enabled: bool = True
    docker_default_network: str = "bridge"
    docker_pull_timeout_seconds: int = 300
    sandbox_enabled: bool = True

    # Directories - use platform-appropriate defaults
    work_dir: str = field(default_factory=lambda: str(Path(_get_default_temp_dir()) / "jobs"))
    artifacts_dir: str = field(default_factory=lambda: str(Path(_get_default_temp_dir()) / "artifacts"))
    logs_dir: str = field(default_factory=lambda: str(Path(_get_default_temp_dir()) / "logs"))


@dataclass
class StorageConfig:
    """إعدادات التخزين."""
    type: str = "local"  # local, s3
    local_path: str = "./data/artifacts"

    # S3
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint: Optional[str] = None  # for MinIO
    s3_access_key: str = ""
    s3_secret_key: str = ""


@dataclass
class ObservabilityConfig:
    """إعدادات المراقبة."""
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json, text
    log_file: Optional[str] = None

    # Metrics
    metrics_enabled: bool = True
    metrics_port: int = 9090
    metrics_path: str = "/metrics"

    # Tracing
    tracing_enabled: bool = False
    tracing_endpoint: Optional[str] = None


@dataclass
class WebSocketConfig:
    """إعدادات WebSocket."""
    enabled: bool = True
    ping_interval_seconds: int = 30
    ping_timeout_seconds: int = 10
    max_connections: int = 1000


@dataclass
class ClusterConfig:
    """
    إعدادات الكلاستر الكاملة.

    تجمع كل الإعدادات في مكان واحد.
    """
    # Cluster identity
    cluster_name: str = "nebula-cluster"
    cluster_id: str = ""

    # Sub-configurations
    server: ServerConfig = field(default_factory=ServerConfig)
    grpc: GRPCConfig = field(default_factory=GRPCConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    worker: WorkerAgentConfig = field(default_factory=WorkerAgentConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)


# =============================================================================
# Configuration Loader
# =============================================================================

class ConfigLoader:
    """
    محمّل الإعدادات.

    يدعم:
    1. ملفات YAML
    2. متغيرات البيئة
    3. القيم الافتراضية
    4. الدمج والتجاوز
    """

    ENV_PREFIX = "NEBULA_"

    def __init__(self):
        self._yaml_available = False
        try:
            import yaml
            self._yaml = yaml
            self._yaml_available = True
        except ImportError:
            self._yaml = None

    def load(
        self,
        config_file: Optional[str] = None,
        env_override: bool = True,
    ) -> ClusterConfig:
        """
        تحميل الإعدادات.

        Args:
            config_file: مسار ملف الإعدادات (YAML/JSON)
            env_override: هل تتجاوز متغيرات البيئة؟

        Returns:
            ClusterConfig
        """
        # Start with defaults
        config_dict: Dict[str, Any] = {}

        # Load from file
        if config_file:
            file_config = self._load_file(config_file)
            config_dict = self._merge_dicts(config_dict, file_config)

        # Override with environment variables
        if env_override:
            env_config = self._load_env()
            config_dict = self._merge_dicts(config_dict, env_config)

        # Build config object
        return self._build_config(config_dict)

    def _load_file(self, path: str) -> Dict[str, Any]:
        """تحميل من ملف."""
        path_obj = Path(path)

        if not path_obj.exists():
            raise ConfigError(f"Config file not found: {path}")

        content = path_obj.read_text(encoding='utf-8')

        if path.endswith(('.yaml', '.yml')):
            if not self._yaml_available:
                raise ConfigError("YAML support requires PyYAML: pip install pyyaml")
            return self._yaml.safe_load(content) or {}

        elif path.endswith('.json'):
            return json.loads(content)

        else:
            # Try YAML first, then JSON
            if self._yaml_available:
                try:
                    return self._yaml.safe_load(content) or {}
                except Exception:
                    pass
            return json.loads(content)

    def _load_env(self) -> Dict[str, Any]:
        """تحميل من متغيرات البيئة."""
        config: Dict[str, Any] = {}

        # Mapping of env vars to config paths
        env_mappings = {
            # Server
            "SERVER_HOST": ("server", "host"),
            "SERVER_PORT": ("server", "port"),
            "DEBUG": ("server", "debug"),

            # gRPC
            "GRPC_PORT": ("grpc", "port"),
            "GRPC_ENABLED": ("grpc", "enabled"),

            # Database
            "DB_TYPE": ("database", "type"),
            "DB_PATH": ("database", "path"),
            "DB_HOST": ("database", "host"),
            "DB_PORT": ("database", "port"),
            "DB_NAME": ("database", "database"),
            "DB_USER": ("database", "user"),
            "DB_PASSWORD": ("database", "password"),

            # Security
            "SECRET_KEY": ("security", "secret_key"),
            "TOKEN_EXPIRY_HOURS": ("security", "token_expiry_hours"),
            "ENROLLMENT_MODE": ("security", "enrollment_mode"),

            # Scheduler
            "SCHEDULER_POLICY": ("scheduler", "policy"),
            "LEASE_DURATION": ("scheduler", "lease_duration_seconds"),

            # Retry
            "MAX_RETRIES": ("retry", "max_retries"),
            "RETRY_STRATEGY": ("retry", "strategy"),

            # Worker
            "HEARTBEAT_INTERVAL": ("worker", "heartbeat_interval_seconds"),
            "MAX_CONCURRENT_JOBS": ("worker", "max_concurrent_jobs"),
            "DOCKER_ENABLED": ("worker", "docker_enabled"),
            "WORK_DIR": ("worker", "work_dir"),

            # Storage
            "STORAGE_TYPE": ("storage", "type"),
            "STORAGE_PATH": ("storage", "local_path"),
            "S3_BUCKET": ("storage", "s3_bucket"),
            "S3_REGION": ("storage", "s3_region"),
            "S3_ENDPOINT": ("storage", "s3_endpoint"),
            "AWS_ACCESS_KEY_ID": ("storage", "s3_access_key"),
            "AWS_SECRET_ACCESS_KEY": ("storage", "s3_secret_key"),

            # Observability
            "LOG_LEVEL": ("observability", "log_level"),
            "LOG_FORMAT": ("observability", "log_format"),
            "METRICS_ENABLED": ("observability", "metrics_enabled"),

            # Cluster
            "CLUSTER_NAME": ("cluster_name",),
            "CLUSTER_ID": ("cluster_id",),
        }

        for env_key, config_path in env_mappings.items():
            full_key = f"{self.ENV_PREFIX}{env_key}"
            value = os.environ.get(full_key)

            if value is not None:
                self._set_nested(config, config_path, self._parse_value(value))

        return config

    def _parse_value(self, value: str) -> Any:
        """تحويل قيمة string."""
        # Boolean
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False

        # Number
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # List (comma-separated)
        if ',' in value:
            return [v.strip() for v in value.split(',')]

        return value

    def _set_nested(self, d: Dict, path: tuple, value: Any) -> None:
        """تعيين قيمة متداخلة."""
        for key in path[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        d[path[-1]] = value

    def _merge_dicts(self, base: Dict, override: Dict) -> Dict:
        """دمج dictionaries."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = value

        return result

    def _build_config(self, data: Dict[str, Any]) -> ClusterConfig:
        """بناء كائن الإعدادات."""
        return ClusterConfig(
            cluster_name=data.get("cluster_name", "nebula-cluster"),
            cluster_id=data.get("cluster_id", ""),
            server=self._build_section(ServerConfig, data.get("server", {})),
            grpc=self._build_section(GRPCConfig, data.get("grpc", {})),
            database=self._build_section(DatabaseConfig, data.get("database", {})),
            security=self._build_section(SecurityConfig, data.get("security", {})),
            scheduler=self._build_section(SchedulerConfig, data.get("scheduler", {})),
            retry=self._build_section(RetryConfig, data.get("retry", {})),
            worker=self._build_section(WorkerAgentConfig, data.get("worker", {})),
            storage=self._build_section(StorageConfig, data.get("storage", {})),
            observability=self._build_section(ObservabilityConfig, data.get("observability", {})),
            websocket=self._build_section(WebSocketConfig, data.get("websocket", {})),
        )

    def _build_section(self, cls: Type[T], data: Dict[str, Any]) -> T:
        """بناء قسم من الإعدادات."""
        # Get field names
        field_names = {f.name for f in fields(cls)}

        # Filter data to only include valid fields
        filtered_data = {k: v for k, v in data.items() if k in field_names}

        return cls(**filtered_data)

    def save(self, config: ClusterConfig, path: str) -> None:
        """حفظ الإعدادات."""
        data = self._config_to_dict(config)

        if path.endswith(('.yaml', '.yml')):
            if not self._yaml_available:
                raise ConfigError("YAML support requires PyYAML")
            content = self._yaml.dump(data, default_flow_style=False, sort_keys=False)
        else:
            content = json.dumps(data, indent=2)

        Path(path).write_text(content, encoding='utf-8')
        logger.info(f"Configuration saved to {path}")

    def _config_to_dict(self, config: ClusterConfig) -> Dict[str, Any]:
        """تحويل الإعدادات إلى dict."""
        return {
            "cluster_name": config.cluster_name,
            "cluster_id": config.cluster_id,
            "server": asdict(config.server),
            "grpc": asdict(config.grpc),
            "database": asdict(config.database),
            "security": asdict(config.security),
            "scheduler": asdict(config.scheduler),
            "retry": asdict(config.retry),
            "worker": asdict(config.worker),
            "storage": asdict(config.storage),
            "observability": asdict(config.observability),
            "websocket": asdict(config.websocket),
        }


# =============================================================================
# Global Configuration
# =============================================================================

_global_config: Optional[ClusterConfig] = None


def load_config(
    config_file: Optional[str] = None,
    env_override: bool = True,
) -> ClusterConfig:
    """تحميل الإعدادات العامة."""
    global _global_config
    loader = ConfigLoader()
    _global_config = loader.load(config_file, env_override)
    return _global_config


def get_config() -> ClusterConfig:
    """الحصول على الإعدادات العامة."""
    global _global_config
    if _global_config is None:
        _global_config = load_config()
    return _global_config


def reset_config() -> None:
    """إعادة تعيين الإعدادات."""
    global _global_config
    _global_config = None
