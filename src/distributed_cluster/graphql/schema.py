# -*- coding: utf-8 -*-
"""
GraphQL Schema for NebulaCompute.

Defines GraphQL types and schema.

تعريفات مخطط GraphQL.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# GraphQL scalar types
class GraphQLScalar:
    """Base class for custom scalars."""

    name: str = "Scalar"

    @classmethod
    def serialize(cls, value: Any) -> Any:
        """Serialize value for output."""
        return value

    @classmethod
    def parse_value(cls, value: Any) -> Any:
        """Parse input value."""
        return value


class DateTimeScalar(GraphQLScalar):
    """DateTime scalar type."""

    name = "DateTime"

    @classmethod
    def serialize(cls, value: datetime) -> str:
        """Serialize datetime to ISO format."""
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    @classmethod
    def parse_value(cls, value: str) -> datetime:
        """Parse ISO format string to datetime."""
        return datetime.fromisoformat(value)


class JSONScalar(GraphQLScalar):
    """JSON scalar type for arbitrary data."""

    name = "JSON"

    @classmethod
    def serialize(cls, value: Any) -> Any:
        """Serialize to JSON-compatible value."""
        return value

    @classmethod
    def parse_value(cls, value: Any) -> Any:
        """Parse JSON value."""
        return value


# Enums
class JobStatusEnum(str, Enum):
    """Job status enumeration."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkerStatusEnum(str, Enum):
    """Worker status enumeration."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    MAINTENANCE = "MAINTENANCE"


class PriorityEnum(str, Enum):
    """Priority level enumeration."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Type definitions
@dataclass
class GraphQLField:
    """GraphQL field definition."""

    name: str
    type_name: str
    description: Optional[str] = None
    args: Optional[Dict[str, str]] = None
    nullable: bool = True
    is_list: bool = False


@dataclass
class GraphQLType:
    """GraphQL type definition."""

    name: str
    fields: List[GraphQLField]
    description: Optional[str] = None
    interfaces: Optional[List[str]] = None


# Object Types
class JobType:
    """GraphQL Job type."""

    name = "Job"
    description = "A compute job in the cluster"

    fields = [
        GraphQLField("id", "ID", "Unique job identifier", nullable=False),
        GraphQLField("name", "String", "Job name"),
        GraphQLField("status", "JobStatus", "Current job status", nullable=False),
        GraphQLField("priority", "Priority", "Job priority"),
        GraphQLField("progress", "Float", "Job progress (0-100)"),
        GraphQLField("createdAt", "DateTime", "Job creation time", nullable=False),
        GraphQLField("startedAt", "DateTime", "Job start time"),
        GraphQLField("completedAt", "DateTime", "Job completion time"),
        GraphQLField("worker", "Worker", "Assigned worker"),
        GraphQLField("result", "JSON", "Job result data"),
        GraphQLField("error", "String", "Error message if failed"),
        GraphQLField("metadata", "JSON", "Additional metadata"),
        GraphQLField("dependencies", "Job", "Job dependencies", is_list=True),
        GraphQLField("cpuRequested", "Float", "Requested CPU cores"),
        GraphQLField("memoryRequested", "Int", "Requested memory (MB)"),
        GraphQLField("gpuRequested", "Float", "Requested GPU units"),
        GraphQLField("estimatedDuration", "Int", "Estimated duration (seconds)"),
        GraphQLField("actualDuration", "Int", "Actual duration (seconds)"),
        GraphQLField("cost", "Float", "Job cost"),
    ]

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": cls.name,
            "description": cls.description,
            "fields": [
                {
                    "name": f.name,
                    "type": f.type_name,
                    "description": f.description,
                    "nullable": f.nullable,
                    "isList": f.is_list,
                }
                for f in cls.fields
            ],
        }


class WorkerType:
    """GraphQL Worker type."""

    name = "Worker"
    description = "A compute worker in the cluster"

    fields = [
        GraphQLField("id", "ID", "Unique worker identifier", nullable=False),
        GraphQLField("name", "String", "Worker name"),
        GraphQLField("status", "WorkerStatus", "Current worker status", nullable=False),
        GraphQLField("host", "String", "Worker hostname"),
        GraphQLField("port", "Int", "Worker port"),
        GraphQLField("cpuTotal", "Float", "Total CPU cores"),
        GraphQLField("cpuUsed", "Float", "Used CPU cores"),
        GraphQLField("memoryTotal", "Int", "Total memory (MB)"),
        GraphQLField("memoryUsed", "Int", "Used memory (MB)"),
        GraphQLField("gpuTotal", "Float", "Total GPU units"),
        GraphQLField("gpuUsed", "Float", "Used GPU units"),
        GraphQLField("activeJobs", "Job", "Currently running jobs", is_list=True),
        GraphQLField("jobsCompleted", "Int", "Total jobs completed"),
        GraphQLField("uptime", "Int", "Uptime in seconds"),
        GraphQLField("lastHeartbeat", "DateTime", "Last heartbeat time"),
        GraphQLField("labels", "JSON", "Worker labels"),
        GraphQLField("capabilities", "String", "Worker capabilities", is_list=True),
    ]

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": cls.name,
            "description": cls.description,
            "fields": [
                {
                    "name": f.name,
                    "type": f.type_name,
                    "description": f.description,
                    "nullable": f.nullable,
                    "isList": f.is_list,
                }
                for f in cls.fields
            ],
        }


class ClusterType:
    """GraphQL Cluster type."""

    name = "Cluster"
    description = "Cluster-wide information and statistics"

    fields = [
        GraphQLField("id", "ID", "Cluster identifier", nullable=False),
        GraphQLField("name", "String", "Cluster name"),
        GraphQLField("version", "String", "NebulaCompute version"),
        GraphQLField("workers", "Worker", "All workers", is_list=True),
        GraphQLField("activeWorkers", "Int", "Number of active workers"),
        GraphQLField("totalJobs", "Int", "Total jobs submitted"),
        GraphQLField("runningJobs", "Int", "Currently running jobs"),
        GraphQLField("queuedJobs", "Int", "Jobs in queue"),
        GraphQLField("completedJobs", "Int", "Completed jobs"),
        GraphQLField("failedJobs", "Int", "Failed jobs"),
        GraphQLField("cpuTotal", "Float", "Total CPU capacity"),
        GraphQLField("cpuUsed", "Float", "Used CPU"),
        GraphQLField("cpuUtilization", "Float", "CPU utilization percentage"),
        GraphQLField("memoryTotal", "Int", "Total memory (MB)"),
        GraphQLField("memoryUsed", "Int", "Used memory (MB)"),
        GraphQLField("memoryUtilization", "Float", "Memory utilization percentage"),
        GraphQLField("gpuTotal", "Float", "Total GPU capacity"),
        GraphQLField("gpuUsed", "Float", "Used GPU"),
        GraphQLField("uptime", "Int", "Cluster uptime in seconds"),
        GraphQLField("startedAt", "DateTime", "Cluster start time"),
    ]

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": cls.name,
            "description": cls.description,
            "fields": [
                {
                    "name": f.name,
                    "type": f.type_name,
                    "description": f.description,
                    "nullable": f.nullable,
                    "isList": f.is_list,
                }
                for f in cls.fields
            ],
        }


class QueueType:
    """GraphQL Queue type."""

    name = "Queue"
    description = "Job queue information"

    fields = [
        GraphQLField("name", "String", "Queue name", nullable=False),
        GraphQLField("size", "Int", "Number of jobs in queue"),
        GraphQLField("jobs", "Job", "Jobs in the queue", is_list=True),
        GraphQLField("priority", "Priority", "Queue priority"),
        GraphQLField("maxSize", "Int", "Maximum queue size"),
        GraphQLField("avgWaitTime", "Float", "Average wait time (seconds)"),
    ]


class MetricType:
    """GraphQL Metric type."""

    name = "Metric"
    description = "Time series metric data"

    fields = [
        GraphQLField("name", "String", "Metric name", nullable=False),
        GraphQLField("value", "Float", "Current value", nullable=False),
        GraphQLField("timestamp", "DateTime", "Measurement time", nullable=False),
        GraphQLField("labels", "JSON", "Metric labels"),
        GraphQLField("unit", "String", "Metric unit"),
    ]


class SLAType:
    """GraphQL SLA type."""

    name = "SLA"
    description = "Service Level Agreement"

    fields = [
        GraphQLField("id", "ID", "SLA identifier", nullable=False),
        GraphQLField("name", "String", "SLA name"),
        GraphQLField("target", "Float", "Target value"),
        GraphQLField("current", "Float", "Current value"),
        GraphQLField("status", "String", "Compliance status"),
        GraphQLField("violationsCount", "Int", "Number of violations"),
    ]


# Input Types
class JobInputType:
    """GraphQL input type for creating jobs."""

    name = "JobInput"
    description = "Input for creating a new job"

    fields = [
        GraphQLField("name", "String", "Job name", nullable=False),
        GraphQLField("type", "String", "Job type", nullable=False),
        GraphQLField("priority", "Priority", "Job priority"),
        GraphQLField("cpuRequested", "Float", "Requested CPU cores"),
        GraphQLField("memoryRequested", "Int", "Requested memory (MB)"),
        GraphQLField("gpuRequested", "Float", "Requested GPU units"),
        GraphQLField("payload", "JSON", "Job payload data"),
        GraphQLField("dependencies", "ID", "Dependency job IDs", is_list=True),
        GraphQLField("metadata", "JSON", "Additional metadata"),
    ]


class JobFilterInput:
    """GraphQL input type for filtering jobs."""

    name = "JobFilterInput"
    description = "Input for filtering jobs"

    fields = [
        GraphQLField("status", "JobStatus", "Filter by status", is_list=True),
        GraphQLField("priority", "Priority", "Filter by priority", is_list=True),
        GraphQLField("workerId", "ID", "Filter by worker"),
        GraphQLField("createdAfter", "DateTime", "Created after date"),
        GraphQLField("createdBefore", "DateTime", "Created before date"),
        GraphQLField("nameContains", "String", "Name contains string"),
    ]


# Query and Mutation definitions
class QueryType:
    """GraphQL Query type."""

    name = "Query"
    description = "Root query type"

    fields = [
        GraphQLField("job", "Job", "Get job by ID", args={"id": "ID!"}),
        GraphQLField(
            "jobs",
            "Job",
            "List jobs with optional filtering",
            args={"filter": "JobFilterInput", "limit": "Int", "offset": "Int"},
            is_list=True,
        ),
        GraphQLField("worker", "Worker", "Get worker by ID", args={"id": "ID!"}),
        GraphQLField("workers", "Worker", "List all workers", args={"status": "WorkerStatus"}, is_list=True),
        GraphQLField("cluster", "Cluster", "Get cluster information"),
        GraphQLField("queues", "Queue", "List job queues", is_list=True),
        GraphQLField("metrics", "Metric", "Get metrics", args={"names": "[String]", "since": "DateTime"}, is_list=True),
        GraphQLField("slas", "SLA", "Get SLA information", is_list=True),
    ]


class MutationType:
    """GraphQL Mutation type."""

    name = "Mutation"
    description = "Root mutation type"

    fields = [
        GraphQLField("submitJob", "Job", "Submit a new job", args={"input": "JobInput!"}),
        GraphQLField("cancelJob", "Job", "Cancel a job", args={"id": "ID!"}),
        GraphQLField("retryJob", "Job", "Retry a failed job", args={"id": "ID!"}),
        GraphQLField("pauseJob", "Job", "Pause a running job", args={"id": "ID!"}),
        GraphQLField("resumeJob", "Job", "Resume a paused job", args={"id": "ID!"}),
        GraphQLField("updateJobPriority", "Job", "Update job priority", args={"id": "ID!", "priority": "Priority!"}),
        GraphQLField("drainWorker", "Worker", "Drain a worker for maintenance", args={"id": "ID!"}),
        GraphQLField("activateWorker", "Worker", "Activate a drained worker", args={"id": "ID!"}),
        GraphQLField("scaleCluster", "Cluster", "Scale the cluster", args={"workerCount": "Int!"}),
    ]


class SubscriptionType:
    """GraphQL Subscription type."""

    name = "Subscription"
    description = "Root subscription type"

    fields = [
        GraphQLField("jobStatusChanged", "Job", "Subscribe to job status changes", args={"jobId": "ID"}),
        GraphQLField("jobProgress", "Job", "Subscribe to job progress updates", args={"jobId": "ID!"}),
        GraphQLField("workerStatusChanged", "Worker", "Subscribe to worker status changes", args={"workerId": "ID"}),
        GraphQLField("clusterMetrics", "Metric", "Subscribe to cluster metrics", args={"interval": "Int"}),
        GraphQLField("alerts", "JSON", "Subscribe to system alerts"),
    ]


def create_schema() -> Dict[str, Any]:
    """
    Create the complete GraphQL schema.

    إنشاء مخطط GraphQL الكامل.
    """
    schema = {
        "types": {
            "scalars": [
                {"name": "DateTime", "description": "ISO 8601 datetime"},
                {"name": "JSON", "description": "Arbitrary JSON data"},
            ],
            "enums": [
                {
                    "name": "JobStatus",
                    "values": [e.value for e in JobStatusEnum],
                },
                {
                    "name": "WorkerStatus",
                    "values": [e.value for e in WorkerStatusEnum],
                },
                {
                    "name": "Priority",
                    "values": [e.value for e in PriorityEnum],
                },
            ],
            "objects": [
                JobType.to_dict(),
                WorkerType.to_dict(),
                ClusterType.to_dict(),
            ],
            "inputs": [
                {
                    "name": JobInputType.name,
                    "description": JobInputType.description,
                    "fields": [{"name": f.name, "type": f.type_name} for f in JobInputType.fields],
                },
                {
                    "name": JobFilterInput.name,
                    "description": JobFilterInput.description,
                    "fields": [{"name": f.name, "type": f.type_name} for f in JobFilterInput.fields],
                },
            ],
        },
        "query": {
            "name": QueryType.name,
            "fields": [
                {
                    "name": f.name,
                    "type": f.type_name,
                    "description": f.description,
                    "args": f.args,
                }
                for f in QueryType.fields
            ],
        },
        "mutation": {
            "name": MutationType.name,
            "fields": [
                {
                    "name": f.name,
                    "type": f.type_name,
                    "description": f.description,
                    "args": f.args,
                }
                for f in MutationType.fields
            ],
        },
        "subscription": {
            "name": SubscriptionType.name,
            "fields": [
                {
                    "name": f.name,
                    "type": f.type_name,
                    "description": f.description,
                    "args": f.args,
                }
                for f in SubscriptionType.fields
            ],
        },
    }

    logger.info("GraphQL schema created")
    return schema


def generate_sdl() -> str:
    """
    Generate GraphQL Schema Definition Language (SDL).

    توليد لغة تعريف المخطط SDL.
    """
    sdl_parts = []

    # Scalars
    sdl_parts.append("scalar DateTime")
    sdl_parts.append("scalar JSON")
    sdl_parts.append("")

    # Enums
    sdl_parts.append("enum JobStatus {")
    for e in JobStatusEnum:
        sdl_parts.append(f"  {e.value}")
    sdl_parts.append("}")
    sdl_parts.append("")

    sdl_parts.append("enum WorkerStatus {")
    for e in WorkerStatusEnum:
        sdl_parts.append(f"  {e.value}")
    sdl_parts.append("}")
    sdl_parts.append("")

    sdl_parts.append("enum Priority {")
    for e in PriorityEnum:
        sdl_parts.append(f"  {e.value}")
    sdl_parts.append("}")
    sdl_parts.append("")

    # Types
    for type_cls in [JobType, WorkerType, ClusterType]:
        sdl_parts.append(f'"""{type_cls.description}"""')
        sdl_parts.append(f"type {type_cls.name} {{")
        for f in type_cls.fields:
            type_str = f"[{f.type_name}]" if f.is_list else f.type_name
            if not f.nullable:
                type_str += "!"
            if f.description:
                sdl_parts.append(f'  """{f.description}"""')
            sdl_parts.append(f"  {f.name}: {type_str}")
        sdl_parts.append("}")
        sdl_parts.append("")

    # Query
    sdl_parts.append("type Query {")
    for f in QueryType.fields:
        type_str = f"[{f.type_name}]" if f.is_list else f.type_name
        args_str = ""
        if f.args:
            args_str = "(" + ", ".join(f"{k}: {v}" for k, v in f.args.items()) + ")"
        sdl_parts.append(f"  {f.name}{args_str}: {type_str}")
    sdl_parts.append("}")
    sdl_parts.append("")

    # Mutation
    sdl_parts.append("type Mutation {")
    for f in MutationType.fields:
        args_str = ""
        if f.args:
            args_str = "(" + ", ".join(f"{k}: {v}" for k, v in f.args.items()) + ")"
        sdl_parts.append(f"  {f.name}{args_str}: {f.type_name}")
    sdl_parts.append("}")
    sdl_parts.append("")

    # Subscription
    sdl_parts.append("type Subscription {")
    for f in SubscriptionType.fields:
        args_str = ""
        if f.args:
            args_str = "(" + ", ".join(f"{k}: {v}" for k, v in f.args.items()) + ")"
        sdl_parts.append(f"  {f.name}{args_str}: {f.type_name}")
    sdl_parts.append("}")

    return "\n".join(sdl_parts)
