# -*- coding: utf-8 -*-
"""
Job Execution Insights - تحليلات تنفيذ المهام
=============================================

Comprehensive job execution analytics providing:
- Performance metrics and trends
- Failure pattern analysis
- Resource utilization insights
- Optimization recommendations

نظام شامل لتحليل تنفيذ المهام:
- مقاييس الأداء والاتجاهات
- تحليل أنماط الفشل
- رؤى استخدام الموارد
- توصيات التحسين
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class InsightType(str, Enum):
    """Types of insights generated."""

    PERFORMANCE = "performance"
    FAILURE = "failure"
    RESOURCE = "resource"
    OPTIMIZATION = "optimization"
    ANOMALY = "anomaly"
    TREND = "trend"


class InsightPriority(str, Enum):
    """Priority levels for insights."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class JobStatus(str, Enum):
    """Job execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    RETRYING = "retrying"


@dataclass
class JobRecord:
    """Record of a job execution."""

    job_id: str
    name: str
    status: JobStatus
    submitted_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    worker_id: Optional[str] = None
    priority: int = 0
    retry_count: int = 0
    cpu_requested: float = 1.0
    memory_requested_mb: int = 1024
    gpu_requested: int = 0
    cpu_used: Optional[float] = None
    memory_used_mb: Optional[int] = None
    gpu_used: Optional[int] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def queue_time_seconds(self) -> Optional[float]:
        """Time spent in queue."""
        if self.started_at and self.submitted_at:
            return (self.started_at - self.submitted_at).total_seconds()
        return None

    @property
    def execution_time_seconds(self) -> Optional[float]:
        """Actual execution time."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def total_time_seconds(self) -> Optional[float]:
        """Total time from submission to completion."""
        if self.completed_at and self.submitted_at:
            return (self.completed_at - self.submitted_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status.value,
            "submitted_at": self.submitted_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "worker_id": self.worker_id,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "cpu_requested": self.cpu_requested,
            "memory_requested_mb": self.memory_requested_mb,
            "gpu_requested": self.gpu_requested,
            "cpu_used": self.cpu_used,
            "memory_used_mb": self.memory_used_mb,
            "exit_code": self.exit_code,
            "error_message": self.error_message,
            "queue_time_seconds": self.queue_time_seconds,
            "execution_time_seconds": self.execution_time_seconds,
            "total_time_seconds": self.total_time_seconds,
            "tags": self.tags,
        }


@dataclass
class Insight:
    """An actionable insight from job analysis."""

    insight_id: str
    type: InsightType
    priority: InsightPriority
    title: str
    description: str
    metric_value: Optional[float] = None
    metric_unit: Optional[str] = None
    threshold: Optional[float] = None
    affected_jobs: List[str] = field(default_factory=list)
    affected_workers: List[str] = field(default_factory=list)
    recommendation: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "type": self.type.value,
            "priority": self.priority.value,
            "title": self.title,
            "description": self.description,
            "metric_value": self.metric_value,
            "metric_unit": self.metric_unit,
            "threshold": self.threshold,
            "affected_jobs_count": len(self.affected_jobs),
            "affected_workers_count": len(self.affected_workers),
            "recommendation": self.recommendation,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class PerformanceSummary:
    """Summary of job performance metrics."""

    period_start: datetime
    period_end: datetime
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    cancelled_jobs: int
    timeout_jobs: int
    success_rate: float
    avg_queue_time_seconds: float
    avg_execution_time_seconds: float
    p50_execution_time_seconds: float
    p95_execution_time_seconds: float
    p99_execution_time_seconds: float
    avg_retries: float
    total_cpu_hours: float
    total_memory_gb_hours: float
    total_gpu_hours: float
    busiest_hour: Optional[int] = None
    top_failure_reasons: List[Tuple[str, int]] = field(default_factory=list)
    jobs_by_status: Dict[str, int] = field(default_factory=dict)
    jobs_by_worker: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_jobs": self.total_jobs,
            "completed_jobs": self.completed_jobs,
            "failed_jobs": self.failed_jobs,
            "cancelled_jobs": self.cancelled_jobs,
            "timeout_jobs": self.timeout_jobs,
            "success_rate": round(self.success_rate, 4),
            "avg_queue_time_seconds": round(self.avg_queue_time_seconds, 2),
            "avg_execution_time_seconds": round(self.avg_execution_time_seconds, 2),
            "p50_execution_time_seconds": round(self.p50_execution_time_seconds, 2),
            "p95_execution_time_seconds": round(self.p95_execution_time_seconds, 2),
            "p99_execution_time_seconds": round(self.p99_execution_time_seconds, 2),
            "avg_retries": round(self.avg_retries, 2),
            "total_cpu_hours": round(self.total_cpu_hours, 2),
            "total_memory_gb_hours": round(self.total_memory_gb_hours, 2),
            "total_gpu_hours": round(self.total_gpu_hours, 2),
            "busiest_hour": self.busiest_hour,
            "top_failure_reasons": [{"reason": reason, "count": count} for reason, count in self.top_failure_reasons],
            "jobs_by_status": self.jobs_by_status,
            "jobs_by_worker": self.jobs_by_worker,
        }


@dataclass
class FailurePattern:
    """Pattern of job failures."""

    pattern_id: str
    error_signature: str
    occurrence_count: int
    first_seen: datetime
    last_seen: datetime
    affected_job_ids: List[str]
    affected_workers: List[str]
    common_tags: List[str]
    severity: str
    suggested_action: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "error_signature": self.error_signature,
            "occurrence_count": self.occurrence_count,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "affected_job_count": len(self.affected_job_ids),
            "affected_worker_count": len(self.affected_workers),
            "common_tags": self.common_tags,
            "severity": self.severity,
            "suggested_action": self.suggested_action,
        }


class JobInsightsEngine:
    """
    Job Execution Insights Engine.

    Analyzes job execution patterns to provide actionable insights
    for improving cluster performance and reliability.

    محرك تحليلات تنفيذ المهام.

    Usage:
        engine = JobInsightsEngine()

        # Record job executions
        engine.record_job(job_record)

        # Get performance summary
        summary = engine.get_performance_summary(days=7)

        # Get insights
        insights = engine.generate_insights()

        # Get failure patterns
        patterns = engine.analyze_failure_patterns()
    """

    def __init__(
        self,
        max_records: int = 100000,
        persist_path: Optional[str] = None,
        insight_callbacks: Optional[List[Callable[[Insight], None]]] = None,
    ):
        """
        Initialize the insights engine.

        Args:
            max_records: Maximum job records to keep in memory
            persist_path: Path to persist job records
            insight_callbacks: Callbacks to invoke when insights are generated
        """
        self.max_records = max_records
        self.persist_path = persist_path
        self.insight_callbacks = insight_callbacks or []

        self._records: List[JobRecord] = []
        self._records_by_id: Dict[str, JobRecord] = {}
        self._insights: List[Insight] = []
        self._insight_counter = 0
        self._lock = asyncio.Lock()

        # Load persisted data
        if persist_path:
            self._load_records()

    def _load_records(self) -> None:
        """Load persisted job records."""
        if not self.persist_path:
            return

        path = Path(self.persist_path)
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    for record_data in data.get("records", []):
                        record = self._record_from_dict(record_data)
                        self._records.append(record)
                        self._records_by_id[record.job_id] = record
                logger.info(f"Loaded {len(self._records)} job records")
            except Exception as e:
                logger.error(f"Failed to load job records: {e}")

    def _save_records(self) -> None:
        """Save job records to disk."""
        if not self.persist_path:
            return

        try:
            path = Path(self.persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "records": [r.to_dict() for r in self._records[-self.max_records :]],
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }

            with open(path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"Failed to save job records: {e}")

    def _record_from_dict(self, data: Dict[str, Any]) -> JobRecord:
        """Create JobRecord from dictionary."""
        return JobRecord(
            job_id=data["job_id"],
            name=data["name"],
            status=JobStatus(data["status"]),
            submitted_at=datetime.fromisoformat(data["submitted_at"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            worker_id=data.get("worker_id"),
            priority=data.get("priority", 0),
            retry_count=data.get("retry_count", 0),
            cpu_requested=data.get("cpu_requested", 1.0),
            memory_requested_mb=data.get("memory_requested_mb", 1024),
            gpu_requested=data.get("gpu_requested", 0),
            cpu_used=data.get("cpu_used"),
            memory_used_mb=data.get("memory_used_mb"),
            exit_code=data.get("exit_code"),
            error_message=data.get("error_message"),
            tags=data.get("tags", []),
        )

    async def record_job(self, record: JobRecord) -> None:
        """
        Record a job execution.

        Args:
            record: The job record to store
        """
        async with self._lock:
            # Update existing or add new
            if record.job_id in self._records_by_id:
                idx = self._records.index(self._records_by_id[record.job_id])
                self._records[idx] = record
            else:
                self._records.append(record)

            self._records_by_id[record.job_id] = record

            # Trim if needed
            if len(self._records) > self.max_records:
                removed = self._records[: -self.max_records]
                self._records = self._records[-self.max_records :]
                for r in removed:
                    self._records_by_id.pop(r.job_id, None)

            # Save periodically
            if len(self._records) % 100 == 0:
                self._save_records()

    def get_record(self, job_id: str) -> Optional[JobRecord]:
        """Get a job record by ID."""
        return self._records_by_id.get(job_id)

    def get_performance_summary(
        self,
        days: int = 7,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> PerformanceSummary:
        """
        Get performance summary for a time period.

        Args:
            days: Number of days to analyze (if start/end not provided)
            start_date: Start of the analysis period
            end_date: End of the analysis period

        Returns:
            Performance summary with key metrics
        """
        end = end_date or datetime.now(timezone.utc)
        start = start_date or (end - timedelta(days=days))

        # Filter records in range
        records = [r for r in self._records if r.submitted_at >= start and r.submitted_at <= end]

        if not records:
            return PerformanceSummary(
                period_start=start,
                period_end=end,
                total_jobs=0,
                completed_jobs=0,
                failed_jobs=0,
                cancelled_jobs=0,
                timeout_jobs=0,
                success_rate=0.0,
                avg_queue_time_seconds=0.0,
                avg_execution_time_seconds=0.0,
                p50_execution_time_seconds=0.0,
                p95_execution_time_seconds=0.0,
                p99_execution_time_seconds=0.0,
                avg_retries=0.0,
                total_cpu_hours=0.0,
                total_memory_gb_hours=0.0,
                total_gpu_hours=0.0,
            )

        # Calculate metrics
        completed = [r for r in records if r.status == JobStatus.COMPLETED]
        failed = [r for r in records if r.status == JobStatus.FAILED]
        cancelled = [r for r in records if r.status == JobStatus.CANCELLED]
        timeout = [r for r in records if r.status == JobStatus.TIMEOUT]

        # Execution times
        execution_times = [r.execution_time_seconds for r in completed if r.execution_time_seconds is not None]
        queue_times = [r.queue_time_seconds for r in records if r.queue_time_seconds is not None]

        # Calculate percentiles
        sorted_exec = sorted(execution_times) if execution_times else [0]
        p50 = self._percentile(sorted_exec, 50)
        p95 = self._percentile(sorted_exec, 95)
        p99 = self._percentile(sorted_exec, 99)

        # Resource usage
        total_cpu_hours = sum(
            (r.cpu_used or r.cpu_requested) * (r.execution_time_seconds or 0) / 3600 for r in completed
        )
        total_memory_gb_hours = sum(
            (r.memory_used_mb or r.memory_requested_mb) / 1024 * (r.execution_time_seconds or 0) / 3600
            for r in completed
        )
        total_gpu_hours = sum(
            (r.gpu_used or r.gpu_requested) * (r.execution_time_seconds or 0) / 3600 for r in completed
        )

        # Jobs by hour
        hour_counts: Dict[int, int] = defaultdict(int)
        for r in records:
            hour_counts[r.submitted_at.hour] += 1
        busiest_hour = max(hour_counts.items(), key=lambda x: x[1])[0] if hour_counts else None

        # Failure reasons
        failure_reasons: Dict[str, int] = defaultdict(int)
        for r in failed:
            reason = self._extract_failure_reason(r.error_message)
            failure_reasons[reason] += 1

        top_failures = sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True)[:10]

        # Jobs by status
        jobs_by_status = defaultdict(int)
        for r in records:
            jobs_by_status[r.status.value] += 1

        # Jobs by worker
        jobs_by_worker = defaultdict(int)
        for r in records:
            if r.worker_id:
                jobs_by_worker[r.worker_id] += 1

        success_rate = len(completed) / len(records) if records else 0.0

        return PerformanceSummary(
            period_start=start,
            period_end=end,
            total_jobs=len(records),
            completed_jobs=len(completed),
            failed_jobs=len(failed),
            cancelled_jobs=len(cancelled),
            timeout_jobs=len(timeout),
            success_rate=success_rate,
            avg_queue_time_seconds=statistics.mean(queue_times) if queue_times else 0.0,
            avg_execution_time_seconds=statistics.mean(execution_times) if execution_times else 0.0,
            p50_execution_time_seconds=p50,
            p95_execution_time_seconds=p95,
            p99_execution_time_seconds=p99,
            avg_retries=statistics.mean([r.retry_count for r in records]),
            total_cpu_hours=total_cpu_hours,
            total_memory_gb_hours=total_memory_gb_hours,
            total_gpu_hours=total_gpu_hours,
            busiest_hour=busiest_hour,
            top_failure_reasons=top_failures,
            jobs_by_status=dict(jobs_by_status),
            jobs_by_worker=dict(jobs_by_worker),
        )

    def _percentile(self, sorted_data: List[float], percentile: float) -> float:
        """Calculate percentile from sorted data."""
        if not sorted_data:
            return 0.0
        k = (len(sorted_data) - 1) * percentile / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)

    def _extract_failure_reason(self, error_message: Optional[str]) -> str:
        """Extract a normalized failure reason from error message."""
        if not error_message:
            return "Unknown error"

        # Normalize common error patterns
        error_lower = error_message.lower()

        if "out of memory" in error_lower or "oom" in error_lower:
            return "Out of Memory"
        elif "timeout" in error_lower:
            return "Timeout"
        elif "connection" in error_lower:
            return "Connection Error"
        elif "permission" in error_lower or "access denied" in error_lower:
            return "Permission Denied"
        elif "not found" in error_lower:
            return "Resource Not Found"
        elif "disk" in error_lower or "storage" in error_lower:
            return "Storage Error"
        elif "gpu" in error_lower or "cuda" in error_lower:
            return "GPU Error"
        elif "network" in error_lower:
            return "Network Error"
        elif "invalid" in error_lower or "validation" in error_lower:
            return "Validation Error"

        # Return truncated message
        return error_message[:50] + "..." if len(error_message) > 50 else error_message

    async def generate_insights(
        self,
        days: int = 7,
        min_priority: InsightPriority = InsightPriority.LOW,
    ) -> List[Insight]:
        """
        Generate actionable insights from job execution data.

        Args:
            days: Number of days to analyze
            min_priority: Minimum priority level to include

        Returns:
            List of insights sorted by priority
        """
        insights = []
        summary = self.get_performance_summary(days=days)

        # 1. Check success rate
        if summary.total_jobs >= 10:
            if summary.success_rate < 0.8:
                insights.append(
                    self._create_insight(
                        type=InsightType.FAILURE,
                        priority=InsightPriority.CRITICAL if summary.success_rate < 0.5 else InsightPriority.HIGH,
                        title="Low Job Success Rate",
                        description=(
                            f"Only {summary.success_rate:.1%} of jobs completed successfully "
                            f"in the last {days} days"
                        ),
                        metric_value=summary.success_rate * 100,
                        metric_unit="percent",
                        threshold=80.0,
                        recommendation="Investigate top failure reasons and address root causes",
                    )
                )

        # 2. Check queue times
        if summary.avg_queue_time_seconds > 300:  # > 5 minutes
            insights.append(
                self._create_insight(
                    type=InsightType.PERFORMANCE,
                    priority=InsightPriority.MEDIUM if summary.avg_queue_time_seconds < 600 else InsightPriority.HIGH,
                    title="High Queue Wait Times",
                    description=f"Average queue time is {summary.avg_queue_time_seconds / 60:.1f} minutes",
                    metric_value=summary.avg_queue_time_seconds,
                    metric_unit="seconds",
                    threshold=300.0,
                    recommendation="Consider scaling up worker capacity or optimizing scheduling",
                )
            )

        # 3. Check execution time variance
        if summary.p95_execution_time_seconds > summary.avg_execution_time_seconds * 3:
            insights.append(
                self._create_insight(
                    type=InsightType.PERFORMANCE,
                    priority=InsightPriority.MEDIUM,
                    title="High Execution Time Variance",
                    description=(
                        f"P95 execution time ({summary.p95_execution_time_seconds:.0f}s) is 3x higher "
                        f"than average ({summary.avg_execution_time_seconds:.0f}s)"
                    ),
                    metric_value=summary.p95_execution_time_seconds,
                    metric_unit="seconds",
                    recommendation="Investigate outlier jobs and consider setting execution time limits",
                )
            )

        # 4. Check retry rate
        if summary.avg_retries > 0.5:
            insights.append(
                self._create_insight(
                    type=InsightType.FAILURE,
                    priority=InsightPriority.MEDIUM,
                    title="High Retry Rate",
                    description=f"Average retries per job is {summary.avg_retries:.2f}",
                    metric_value=summary.avg_retries,
                    metric_unit="retries",
                    threshold=0.5,
                    recommendation="Investigate retry causes; consider improving error handling or resource allocation",
                )
            )

        # 5. Analyze top failure reasons
        for reason, count in summary.top_failure_reasons[:3]:
            failure_rate = count / summary.total_jobs if summary.total_jobs > 0 else 0
            if failure_rate > 0.05:  # More than 5% of jobs
                insights.append(
                    self._create_insight(
                        type=InsightType.FAILURE,
                        priority=InsightPriority.HIGH if failure_rate > 0.1 else InsightPriority.MEDIUM,
                        title=f"Frequent Failure: {reason}",
                        description=f"{count} jobs ({failure_rate:.1%}) failed with: {reason}",
                        metric_value=count,
                        metric_unit="jobs",
                        recommendation=self._get_failure_recommendation(reason),
                    )
                )

        # 6. Check worker distribution
        if summary.jobs_by_worker:
            worker_counts = list(summary.jobs_by_worker.values())
            if len(worker_counts) >= 2:
                max_jobs = max(worker_counts)
                min_jobs = min(worker_counts)
                if max_jobs > min_jobs * 3:  # Significant imbalance
                    insights.append(
                        self._create_insight(
                            type=InsightType.RESOURCE,
                            priority=InsightPriority.MEDIUM,
                            title="Uneven Worker Load Distribution",
                            description=f"Highest loaded worker has {max_jobs} jobs vs {min_jobs} for the lowest",
                            recommendation="Review scheduling strategy; consider load-aware scheduling",
                        )
                    )

        # 7. Check timeout rate
        if summary.timeout_jobs > summary.total_jobs * 0.05:
            insights.append(
                self._create_insight(
                    type=InsightType.FAILURE,
                    priority=InsightPriority.HIGH,
                    title="High Timeout Rate",
                    description=(
                        f"{summary.timeout_jobs} jobs " f"({summary.timeout_jobs / summary.total_jobs:.1%}) timed out"
                    ),
                    metric_value=summary.timeout_jobs,
                    metric_unit="jobs",
                    recommendation="Review timeout settings; optimize job execution or increase limits",
                )
            )

        # 8. Peak hour analysis
        if summary.busiest_hour is not None:
            insights.append(
                self._create_insight(
                    type=InsightType.TREND,
                    priority=InsightPriority.INFO,
                    title="Peak Usage Pattern Detected",
                    description=f"Busiest hour is {summary.busiest_hour:02d}:00",
                    recommendation="Consider pre-scaling workers before peak hours",
                )
            )

        # Filter by priority
        priority_order = {
            InsightPriority.CRITICAL: 0,
            InsightPriority.HIGH: 1,
            InsightPriority.MEDIUM: 2,
            InsightPriority.LOW: 3,
            InsightPriority.INFO: 4,
        }
        min_level = priority_order[min_priority]
        insights = [i for i in insights if priority_order[i.priority] <= min_level]

        # Sort by priority
        insights.sort(key=lambda x: priority_order[x.priority])

        # Store insights
        self._insights = insights

        # Notify callbacks
        for insight in insights:
            for callback in self.insight_callbacks:
                try:
                    callback(insight)
                except Exception as e:
                    logger.error(f"Insight callback failed: {e}")

        return insights

    def _get_failure_recommendation(self, reason: str) -> str:
        """Get recommendation for a failure reason."""
        recommendations = {
            "Out of Memory": "Increase memory allocation or optimize memory usage in jobs",
            "Timeout": "Increase timeout limits or optimize job execution time",
            "Connection Error": "Check network connectivity and retry configuration",
            "Permission Denied": "Review access permissions and credentials",
            "Resource Not Found": "Verify required resources are available before job submission",
            "Storage Error": "Check disk space and storage health",
            "GPU Error": "Verify GPU availability and driver compatibility",
            "Network Error": "Check network stability and implement retry logic",
            "Validation Error": "Review input validation and job configuration",
        }
        return recommendations.get(reason, "Investigate error logs for detailed analysis")

    def _create_insight(
        self,
        type: InsightType,
        priority: InsightPriority,
        title: str,
        description: str,
        metric_value: Optional[float] = None,
        metric_unit: Optional[str] = None,
        threshold: Optional[float] = None,
        recommendation: Optional[str] = None,
    ) -> Insight:
        """Create an insight with a unique ID."""
        self._insight_counter += 1
        return Insight(
            insight_id=f"insight-{self._insight_counter:06d}",
            type=type,
            priority=priority,
            title=title,
            description=description,
            metric_value=metric_value,
            metric_unit=metric_unit,
            threshold=threshold,
            recommendation=recommendation,
        )

    def analyze_failure_patterns(
        self,
        days: int = 7,
        min_occurrences: int = 3,
    ) -> List[FailurePattern]:
        """
        Analyze failure patterns to identify recurring issues.

        Args:
            days: Number of days to analyze
            min_occurrences: Minimum occurrences for a pattern

        Returns:
            List of failure patterns
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        failed_records = [
            r for r in self._records if r.status == JobStatus.FAILED and r.submitted_at >= start and r.error_message
        ]

        # Group by error signature
        error_groups: Dict[str, List[JobRecord]] = defaultdict(list)
        for r in failed_records:
            signature = self._extract_failure_reason(r.error_message)
            error_groups[signature].append(r)

        patterns = []
        pattern_counter = 0

        for signature, records in error_groups.items():
            if len(records) < min_occurrences:
                continue

            pattern_counter += 1
            workers = list(set(r.worker_id for r in records if r.worker_id))
            all_tags = []
            for r in records:
                all_tags.extend(r.tags)
            common_tags = self._find_common_tags(all_tags)

            # Determine severity based on frequency
            occurrence_rate = len(records) / len(failed_records) if failed_records else 0
            if occurrence_rate > 0.3:
                severity = "critical"
            elif occurrence_rate > 0.1:
                severity = "high"
            else:
                severity = "medium"

            patterns.append(
                FailurePattern(
                    pattern_id=f"pattern-{pattern_counter:04d}",
                    error_signature=signature,
                    occurrence_count=len(records),
                    first_seen=min(r.submitted_at for r in records),
                    last_seen=max(r.submitted_at for r in records),
                    affected_job_ids=[r.job_id for r in records],
                    affected_workers=workers,
                    common_tags=common_tags,
                    severity=severity,
                    suggested_action=self._get_failure_recommendation(signature),
                )
            )

        # Sort by occurrence count
        patterns.sort(key=lambda x: x.occurrence_count, reverse=True)

        return patterns

    def _find_common_tags(self, all_tags: List[str]) -> List[str]:
        """Find tags that appear frequently."""
        if not all_tags:
            return []

        tag_counts: Dict[str, int] = defaultdict(int)
        for tag in all_tags:
            tag_counts[tag] += 1

        # Return tags that appear in at least 50% of cases
        threshold = len(all_tags) / len(set(all_tags)) * 0.5 if all_tags else 0
        return [tag for tag, count in tag_counts.items() if count >= threshold]

    def get_worker_performance(
        self,
        days: int = 7,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get performance metrics for each worker.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary of worker ID to performance metrics
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        records = [r for r in self._records if r.submitted_at >= start and r.worker_id]

        worker_stats: Dict[str, Dict[str, Any]] = {}

        for worker_id in set(r.worker_id for r in records if r.worker_id):
            worker_records = [r for r in records if r.worker_id == worker_id]
            completed = [r for r in worker_records if r.status == JobStatus.COMPLETED]
            failed = [r for r in worker_records if r.status == JobStatus.FAILED]

            exec_times = [r.execution_time_seconds for r in completed if r.execution_time_seconds is not None]

            worker_stats[worker_id] = {
                "total_jobs": len(worker_records),
                "completed_jobs": len(completed),
                "failed_jobs": len(failed),
                "success_rate": len(completed) / len(worker_records) if worker_records else 0,
                "avg_execution_time": statistics.mean(exec_times) if exec_times else 0,
                "total_cpu_hours": sum(
                    (r.cpu_used or r.cpu_requested) * (r.execution_time_seconds or 0) / 3600 for r in completed
                ),
                "total_retries": sum(r.retry_count for r in worker_records),
            }

        return worker_stats

    def get_hourly_distribution(self, days: int = 7) -> Dict[int, Dict[str, int]]:
        """
        Get job distribution by hour of day.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary of hour to job counts by status
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        records = [r for r in self._records if r.submitted_at >= start]

        distribution: Dict[int, Dict[str, int]] = {h: {"submitted": 0, "completed": 0, "failed": 0} for h in range(24)}

        for r in records:
            hour = r.submitted_at.hour
            distribution[hour]["submitted"] += 1
            if r.status == JobStatus.COMPLETED:
                distribution[hour]["completed"] += 1
            elif r.status == JobStatus.FAILED:
                distribution[hour]["failed"] += 1

        return distribution

    def get_trend_analysis(
        self,
        metric: str = "success_rate",
        days: int = 30,
        granularity: str = "daily",
    ) -> List[Dict[str, Any]]:
        """
        Get trend analysis for a metric over time.

        Args:
            metric: Metric to analyze (success_rate, avg_execution_time, job_count)
            days: Number of days to analyze
            granularity: Time granularity (daily, hourly)

        Returns:
            List of data points with timestamps and values
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        if granularity == "hourly":
            delta = timedelta(hours=1)
        else:
            delta = timedelta(days=1)

        data_points = []
        current = start

        while current < end:
            next_period = current + delta
            period_records = [r for r in self._records if r.submitted_at >= current and r.submitted_at < next_period]

            if period_records:
                if metric == "success_rate":
                    completed = sum(1 for r in period_records if r.status == JobStatus.COMPLETED)
                    value = completed / len(period_records)
                elif metric == "avg_execution_time":
                    times = [r.execution_time_seconds for r in period_records if r.execution_time_seconds is not None]
                    value = statistics.mean(times) if times else 0
                elif metric == "job_count":
                    value = len(period_records)
                else:
                    value = 0

                data_points.append(
                    {
                        "timestamp": current.isoformat(),
                        "value": round(value, 4),
                    }
                )

            current = next_period

        return data_points

    def get_recommendations(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get optimization recommendations based on analysis.

        Args:
            days: Number of days to analyze

        Returns:
            List of recommendations with priority and impact
        """
        recommendations = []
        summary = self.get_performance_summary(days=days)
        patterns = self.analyze_failure_patterns(days=days)

        # Resource optimization
        if summary.total_cpu_hours > 0:
            recommendations.append(
                {
                    "category": "resource_optimization",
                    "title": "Resource Usage Summary",
                    "description": (
                        f"Total compute: {summary.total_cpu_hours:.1f} CPU-hours, "
                        f"{summary.total_memory_gb_hours:.1f} GB-hours, "
                        f"{summary.total_gpu_hours:.1f} GPU-hours"
                    ),
                    "priority": "info",
                    "impact": "awareness",
                }
            )

        # Scaling recommendation
        if summary.avg_queue_time_seconds > 60:
            workers_needed = int(summary.avg_queue_time_seconds / 60)
            recommendations.append(
                {
                    "category": "scaling",
                    "title": "Consider Adding Workers",
                    "description": f"Queue times suggest adding {workers_needed} more workers could help",
                    "priority": "medium" if summary.avg_queue_time_seconds < 300 else "high",
                    "impact": f"Could reduce queue time by ~{summary.avg_queue_time_seconds * 0.5:.0f}s",
                }
            )

        # Failure prevention
        if patterns:
            top_pattern = patterns[0]
            recommendations.append(
                {
                    "category": "reliability",
                    "title": f"Address '{top_pattern.error_signature}' Failures",
                    "description": f"{top_pattern.occurrence_count} jobs affected. {top_pattern.suggested_action}",
                    "priority": top_pattern.severity,
                    "impact": f"Could prevent {top_pattern.occurrence_count} failures",
                }
            )

        # Timeout tuning
        if summary.timeout_jobs > 0:
            recommendations.append(
                {
                    "category": "configuration",
                    "title": "Review Timeout Settings",
                    "description": (
                        f"{summary.timeout_jobs} jobs timed out. Consider adjusting timeouts "
                        f"based on P95 execution time ({summary.p95_execution_time_seconds:.0f}s)"
                    ),
                    "priority": "medium",
                    "impact": f"Could save {summary.timeout_jobs} jobs from timeout",
                }
            )

        return recommendations

    def export_report(self, days: int = 7, format: str = "json") -> str:
        """
        Export a comprehensive report.

        Args:
            days: Number of days to analyze
            format: Output format (json)

        Returns:
            Report as string
        """
        summary = self.get_performance_summary(days=days)
        patterns = self.analyze_failure_patterns(days=days)
        worker_perf = self.get_worker_performance(days=days)
        recommendations = self.get_recommendations(days=days)

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            "summary": summary.to_dict(),
            "failure_patterns": [p.to_dict() for p in patterns],
            "worker_performance": worker_perf,
            "recommendations": recommendations,
            "hourly_distribution": self.get_hourly_distribution(days=days),
        }

        if format == "json":
            return json.dumps(report, indent=2)

        return json.dumps(report)


# =============================================================================
# Factory Functions
# =============================================================================


def create_job_insights_engine(
    persist_path: Optional[str] = None,
    max_records: int = 100000,
) -> JobInsightsEngine:
    """
    Create a job insights engine.

    Args:
        persist_path: Path to persist job records
        max_records: Maximum records to keep

    Returns:
        Configured JobInsightsEngine instance
    """
    return JobInsightsEngine(
        max_records=max_records,
        persist_path=persist_path,
    )
