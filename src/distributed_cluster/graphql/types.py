"""
GraphQL Types - أنواع GraphQL
==============================

GraphQL type definitions for NebulaCompute.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, List, Optional

import strawberry

if TYPE_CHECKING:
    from distributed_cluster.graphql.context import GraphQLContext


# =============================================================================
# Enums | التعدادات
# =============================================================================


@strawberry.enum
class JobStatus(Enum):
    """حالة المهمة"""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@strawberry.enum
class JobPriority(Enum):
    """أولوية المهمة"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@strawberry.enum
class WorkerStatus(Enum):
    """حالة العامل"""
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    DRAINING = "draining"
    MAINTENANCE = "maintenance"


@strawberry.enum
class TenantStatus(Enum):
    """حالة المستأجر"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    QUOTA_EXCEEDED = "quota_exceeded"
    TERMINATING = "terminating"


@strawberry.enum
class BackupStatus(Enum):
    """حالة النسخ الاحتياطي"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@strawberry.enum
class SortOrder(Enum):
    """ترتيب الفرز"""
    ASC = "asc"
    DESC = "desc"


# =============================================================================
# Scalar Types | الأنواع القياسية
# =============================================================================


@strawberry.scalar
class JSON:
    """نوع JSON مخصص"""

    @staticmethod
    def serialize(value: Any) -> Any:
        return value

    @staticmethod
    def parse_value(value: Any) -> Any:
        return value


# =============================================================================
# Input Types | أنواع الإدخال
# =============================================================================


@strawberry.input
class ResourceRequirementsInput:
    """متطلبات الموارد"""
    cpu: Optional[float] = 1.0
    memory: Optional[int] = 1024  # MB
    gpu: Optional[int] = 0
    gpu_memory: Optional[int] = None  # MB


@strawberry.input
class JobInput:
    """إدخال مهمة جديدة"""
    command: str
    args: Optional[List[str]] = None
    image: Optional[str] = None
    priority: Optional[JobPriority] = JobPriority.NORMAL
    resources: Optional[ResourceRequirementsInput] = None
    timeout: Optional[int] = 3600
    retries: Optional[int] = 3
    env: Optional[JSON] = None
    working_dir: Optional[str] = None
    tags: Optional[List[str]] = None
    tenant_id: Optional[str] = None


@strawberry.input
class JobFilterInput:
    """فلتر المهام"""
    status: Optional[List[JobStatus]] = None
    priority: Optional[List[JobPriority]] = None
    worker_id: Optional[str] = None
    tenant_id: Optional[str] = None
    tags: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    search: Optional[str] = None


@strawberry.input
class WorkerFilterInput:
    """فلتر العمال"""
    status: Optional[List[WorkerStatus]] = None
    tags: Optional[List[str]] = None
    has_gpu: Optional[bool] = None
    min_cpu: Optional[float] = None
    min_memory: Optional[int] = None


@strawberry.input
class PaginationInput:
    """إعدادات الصفحات"""
    offset: Optional[int] = 0
    limit: Optional[int] = 20
    sort_by: Optional[str] = "created_at"
    sort_order: Optional[SortOrder] = SortOrder.DESC


@strawberry.input
class TenantInput:
    """إدخال مستأجر جديد"""
    name: str
    description: Optional[str] = None
    admin_email: Optional[str] = None
    max_jobs: Optional[int] = 100
    max_workers: Optional[int] = 10
    max_cpu: Optional[float] = 100.0
    max_memory: Optional[int] = 204800  # 200 GB
    max_gpu: Optional[int] = 4
    priority: Optional[int] = 50


@strawberry.input
class BackupInput:
    """إدخال نسخ احتياطي"""
    name: Optional[str] = None
    backup_type: Optional[str] = "full"
    include_jobs: Optional[bool] = True
    include_events: Optional[bool] = True
    compression: Optional[bool] = True


# =============================================================================
# Object Types | أنواع الكائنات
# =============================================================================


@strawberry.type
class ResourceRequirements:
    """متطلبات الموارد"""
    cpu: float
    memory: int  # MB
    gpu: int
    gpu_memory: Optional[int]  # MB


@strawberry.type
class ResourceUsage:
    """استخدام الموارد"""
    cpu_percent: float
    memory_used: int  # MB
    memory_total: int  # MB
    gpu_percent: Optional[float]
    gpu_memory_used: Optional[int]
    gpu_memory_total: Optional[int]


@strawberry.type
class Job:
    """نوع المهمة"""
    id: str
    command: str
    args: Optional[List[str]]
    image: Optional[str]
    status: JobStatus
    priority: JobPriority
    resources: ResourceRequirements
    timeout: int
    retries: int
    retry_count: int
    exit_code: Optional[int]
    output: Optional[str]
    error: Optional[str]
    env: Optional[JSON]
    working_dir: Optional[str]
    tags: List[str]
    tenant_id: Optional[str]
    worker_id: Optional[str]
    created_at: datetime
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]

    @strawberry.field
    async def worker(self, info: strawberry.Info) -> Optional["Worker"]:
        """الحصول على العامل المعين"""
        if not self.worker_id:
            return None
        context: GraphQLContext = info.context
        return await context.dataloaders.worker_loader.load(self.worker_id)

    @strawberry.field
    async def tenant(self, info: strawberry.Info) -> Optional["Tenant"]:
        """الحصول على المستأجر"""
        if not self.tenant_id:
            return None
        context: GraphQLContext = info.context
        return await context.dataloaders.tenant_loader.load(self.tenant_id)


@strawberry.type
class Worker:
    """نوع العامل"""
    id: str
    name: str
    hostname: str
    status: WorkerStatus
    ip_address: Optional[str]
    port: int
    tags: List[str]
    capabilities: JSON
    resources_total: ResourceRequirements
    resources_available: ResourceRequirements
    resource_usage: Optional[ResourceUsage]
    active_jobs: int
    max_concurrent_jobs: int
    total_jobs_completed: int
    total_jobs_failed: int
    docker_enabled: bool
    gpu_enabled: bool
    registered_at: datetime
    last_heartbeat: Optional[datetime]
    uptime_seconds: Optional[float]
    version: Optional[str]

    @strawberry.field
    async def jobs(
        self,
        info: strawberry.Info,
        status: Optional[List[JobStatus]] = None,
        limit: int = 10,
    ) -> List[Job]:
        """الحصول على مهام العامل"""
        context: GraphQLContext = info.context
        return await context.services.job_service.get_worker_jobs(
            self.id, status=status, limit=limit
        )


@strawberry.type
class Tenant:
    """نوع المستأجر"""
    id: str
    name: str
    description: Optional[str]
    status: TenantStatus
    admin_email: Optional[str]
    priority: int
    created_at: datetime
    updated_at: Optional[datetime]

    # Quotas
    max_jobs: int
    max_workers: int
    max_cpu: float
    max_memory: int  # MB
    max_gpu: int
    max_storage: int  # MB

    # Usage
    active_jobs: int
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    worker_count: int
    cpu_used: float
    memory_used: int
    gpu_used: int
    storage_used: int

    @strawberry.field
    def quota_usage_percent(self) -> JSON:
        """نسبة استخدام الحصص"""
        return {
            "jobs": (self.active_jobs / self.max_jobs * 100) if self.max_jobs > 0 else 0,
            "cpu": (self.cpu_used / self.max_cpu * 100) if self.max_cpu > 0 else 0,
            "memory": (self.memory_used / self.max_memory * 100) if self.max_memory > 0 else 0,
            "gpu": (self.gpu_used / self.max_gpu * 100) if self.max_gpu > 0 else 0,
        }

    @strawberry.field
    async def jobs(
        self,
        info: strawberry.Info,
        filter: Optional[JobFilterInput] = None,
        pagination: Optional[PaginationInput] = None,
    ) -> "JobConnection":
        """الحصول على مهام المستأجر"""
        context: GraphQLContext = info.context
        return await context.services.job_service.get_tenant_jobs(
            self.id, filter=filter, pagination=pagination
        )

    @strawberry.field
    async def workers(self, info: strawberry.Info) -> List[Worker]:
        """الحصول على عمال المستأجر"""
        context: GraphQLContext = info.context
        return await context.services.worker_service.get_tenant_workers(self.id)


@strawberry.type
class Backup:
    """نوع النسخ الاحتياطي"""
    id: str
    name: str
    backup_type: str
    status: BackupStatus
    size_bytes: Optional[int]
    size_human: Optional[str]
    location: Optional[str]
    checksum: Optional[str]
    items_count: JSON
    compression: bool
    encryption: bool
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    error: Optional[str]
    created_by: Optional[str]


@strawberry.type
class ClusterStats:
    """إحصائيات الكلاستر"""
    total_workers: int
    online_workers: int
    offline_workers: int
    busy_workers: int
    total_jobs: int
    pending_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    total_cpu: float
    available_cpu: float
    total_memory: int  # MB
    available_memory: int  # MB
    total_gpu: int
    available_gpu: int
    jobs_per_hour: float
    avg_job_duration: float
    success_rate: float
    uptime_seconds: float


@strawberry.type
class SystemInfo:
    """معلومات النظام"""
    version: str
    build_date: Optional[str]
    go_version: Optional[str]
    python_version: str
    platform: str
    arch: str
    hostname: str
    started_at: datetime
    uptime_seconds: float
    config: JSON


@strawberry.type
class HealthCheck:
    """فحص الصحة"""
    healthy: bool
    status: str
    checks: JSON
    timestamp: datetime


# =============================================================================
# Connection Types (Pagination) | أنواع الاتصال (التصفح)
# =============================================================================


@strawberry.type
class PageInfo:
    """معلومات الصفحة"""
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str]
    end_cursor: Optional[str]
    total_count: int


@strawberry.type
class JobEdge:
    """حافة المهمة"""
    node: Job
    cursor: str


@strawberry.type
class JobConnection:
    """اتصال المهام"""
    edges: List[JobEdge]
    page_info: PageInfo
    total_count: int


@strawberry.type
class WorkerEdge:
    """حافة العامل"""
    node: Worker
    cursor: str


@strawberry.type
class WorkerConnection:
    """اتصال العمال"""
    edges: List[WorkerEdge]
    page_info: PageInfo
    total_count: int


@strawberry.type
class TenantEdge:
    """حافة المستأجر"""
    node: Tenant
    cursor: str


@strawberry.type
class TenantConnection:
    """اتصال المستأجرين"""
    edges: List[TenantEdge]
    page_info: PageInfo
    total_count: int


@strawberry.type
class BackupEdge:
    """حافة النسخ الاحتياطي"""
    node: Backup
    cursor: str


@strawberry.type
class BackupConnection:
    """اتصال النسخ الاحتياطية"""
    edges: List[BackupEdge]
    page_info: PageInfo
    total_count: int


# =============================================================================
# Mutation Response Types | أنواع استجابة الطفرات
# =============================================================================


@strawberry.type
class MutationResponse:
    """استجابة الطفرة الأساسية"""
    success: bool
    message: str
    errors: Optional[List[str]]


@strawberry.type
class JobMutationResponse(MutationResponse):
    """استجابة طفرة المهمة"""
    job: Optional[Job]


@strawberry.type
class WorkerMutationResponse(MutationResponse):
    """استجابة طفرة العامل"""
    worker: Optional[Worker]


@strawberry.type
class TenantMutationResponse(MutationResponse):
    """استجابة طفرة المستأجر"""
    tenant: Optional[Tenant]


@strawberry.type
class BackupMutationResponse(MutationResponse):
    """استجابة طفرة النسخ الاحتياطي"""
    backup: Optional[Backup]


@strawberry.type
class BatchJobMutationResponse(MutationResponse):
    """استجابة طفرة دفعة المهام"""
    jobs: List[Job]
    submitted_count: int
    failed_count: int


# =============================================================================
# Subscription Types | أنواع الاشتراك
# =============================================================================


@strawberry.type
class JobEvent:
    """حدث المهمة"""
    event_type: str  # created, updated, completed, failed, cancelled
    job: Job
    timestamp: datetime
    previous_status: Optional[JobStatus]


@strawberry.type
class WorkerEvent:
    """حدث العامل"""
    event_type: str  # registered, online, offline, updated
    worker: Worker
    timestamp: datetime
    previous_status: Optional[WorkerStatus]


@strawberry.type
class ClusterEvent:
    """حدث الكلاستر"""
    event_type: str
    message: str
    data: Optional[JSON]
    timestamp: datetime
    severity: str  # info, warning, error, critical


@strawberry.type
class MetricsSnapshot:
    """لقطة المقاييس"""
    timestamp: datetime
    cluster_stats: ClusterStats
    top_workers: List[Worker]
    recent_jobs: List[Job]
