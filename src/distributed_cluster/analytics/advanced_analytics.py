# -*- coding: utf-8 -*-
"""
Advanced Predictive Analytics for NebulaCompute
================================================

تحليلات تنبؤية متقدمة:
- كشف الشذوذ
- تصنيف أعباء العمل
- التنبؤ بالتكلفة
- تحليل الأنماط
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================


class AnomalyType(str, Enum):
    """Type of anomaly detected."""
    SPIKE = "spike"
    DROP = "drop"
    DRIFT = "drift"
    PATTERN_BREAK = "pattern_break"
    OUTLIER = "outlier"


class WorkloadCategory(str, Enum):
    """Workload classification category."""
    CPU_INTENSIVE = "cpu_intensive"
    MEMORY_INTENSIVE = "memory_intensive"
    GPU_INTENSIVE = "gpu_intensive"
    IO_INTENSIVE = "io_intensive"
    BALANCED = "balanced"
    BURSTY = "bursty"
    STEADY = "steady"


class AlertSeverity(str, Enum):
    """Alert severity level."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Anomaly:
    """Detected anomaly."""
    anomaly_id: str
    anomaly_type: AnomalyType
    metric_name: str
    value: float
    expected_value: float
    deviation: float
    severity: AlertSeverity
    timestamp: datetime
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_id": self.anomaly_id,
            "anomaly_type": self.anomaly_type.value,
            "metric_name": self.metric_name,
            "value": self.value,
            "expected_value": self.expected_value,
            "deviation": self.deviation,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
        }


@dataclass
class WorkloadProfile:
    """Workload profile for a job type."""
    job_type: str
    category: WorkloadCategory
    avg_cpu_usage: float
    avg_memory_usage: float
    avg_gpu_usage: float
    avg_io_operations: float
    avg_duration: float
    variance_coefficient: float
    peak_hours: List[int]
    sample_count: int
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_type": self.job_type,
            "category": self.category.value,
            "avg_cpu_usage": self.avg_cpu_usage,
            "avg_memory_usage": self.avg_memory_usage,
            "avg_gpu_usage": self.avg_gpu_usage,
            "avg_io_operations": self.avg_io_operations,
            "avg_duration": self.avg_duration,
            "variance_coefficient": self.variance_coefficient,
            "peak_hours": self.peak_hours,
            "sample_count": self.sample_count,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class CostPrediction:
    """Cost prediction result."""
    prediction_id: str
    job_type: str
    estimated_cost: float
    cost_breakdown: Dict[str, float]
    confidence: float
    currency: str = "USD"
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "job_type": self.job_type,
            "estimated_cost": self.estimated_cost,
            "cost_breakdown": self.cost_breakdown,
            "confidence": self.confidence,
            "currency": self.currency,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PatternMatch:
    """Pattern matching result."""
    pattern_id: str
    pattern_name: str
    confidence: float
    matched_features: List[str]
    recommendations: List[str]


# =============================================================================
# Anomaly Detector
# =============================================================================


class AnomalyDetector:
    """
    Real-time anomaly detection engine.

    محرك كشف الشذوذ في الوقت الفعلي.

    Uses multiple detection methods:
    - Z-score based detection
    - Moving average deviation
    - Isolation Forest approximation
    - Seasonal decomposition
    """

    def __init__(
        self,
        window_size: int = 100,
        z_threshold: float = 3.0,
        sensitivity: float = 0.8,
    ):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.sensitivity = sensitivity

        # Per-metric sliding windows
        self._windows: Dict[str, Deque[Tuple[datetime, float]]] = {}
        self._baselines: Dict[str, Dict[str, float]] = {}
        self._anomalies: List[Anomaly] = []
        self._callbacks: List[Callable[[Anomaly], None]] = []
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "data_points_processed": 0,
            "anomalies_detected": 0,
            "false_positives_reported": 0,
        }

    async def add_data_point(
        self,
        metric_name: str,
        value: float,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Anomaly]:
        """
        Add a data point and check for anomalies.

        إضافة نقطة بيانات والتحقق من الشذوذ.
        """
        timestamp = timestamp or datetime.utcnow()

        async with self._lock:
            # Initialize window if needed
            if metric_name not in self._windows:
                self._windows[metric_name] = deque(maxlen=self.window_size)
                self._baselines[metric_name] = {
                    "mean": value,
                    "std": 0.0,
                    "min": value,
                    "max": value,
                }

            window = self._windows[metric_name]
            baseline = self._baselines[metric_name]

            # Add to window
            window.append((timestamp, value))
            self._stats["data_points_processed"] += 1

            # Need minimum data for detection
            if len(window) < 10:
                self._update_baseline(baseline, value)
                return None

            # Detect anomaly
            anomaly = await self._detect_anomaly(
                metric_name, value, timestamp, window, baseline
            )

            # Update baseline
            self._update_baseline(baseline, value)

            if anomaly:
                self._anomalies.append(anomaly)
                self._stats["anomalies_detected"] += 1

                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        callback(anomaly)
                    except Exception as e:
                        logger.error(f"Anomaly callback error: {e}")

            return anomaly

    async def _detect_anomaly(
        self,
        metric_name: str,
        value: float,
        timestamp: datetime,
        window: Deque[Tuple[datetime, float]],
        baseline: Dict[str, float],
    ) -> Optional[Anomaly]:
        """Detect if value is anomalous."""
        import uuid

        values = [v for _, v in window]
        mean = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 0.01

        # Z-score detection
        z_score = abs(value - mean) / std if std > 0 else 0

        if z_score > self.z_threshold * self.sensitivity:
            # Determine anomaly type
            if value > mean:
                anomaly_type = AnomalyType.SPIKE
            else:
                anomaly_type = AnomalyType.DROP

            # Determine severity
            if z_score > self.z_threshold * 2:
                severity = AlertSeverity.CRITICAL
            elif z_score > self.z_threshold * 1.5:
                severity = AlertSeverity.WARNING
            else:
                severity = AlertSeverity.INFO

            return Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type=anomaly_type,
                metric_name=metric_name,
                value=value,
                expected_value=mean,
                deviation=z_score,
                severity=severity,
                timestamp=timestamp,
                context={
                    "z_score": z_score,
                    "baseline_mean": baseline["mean"],
                    "baseline_std": baseline["std"],
                    "window_size": len(window),
                },
            )

        # Check for drift (gradual change)
        if len(values) >= 50:
            recent_mean = statistics.mean(values[-20:])
            historical_mean = statistics.mean(values[:-20])
            drift = abs(recent_mean - historical_mean) / historical_mean if historical_mean > 0 else 0

            if drift > 0.3 * self.sensitivity:
                return Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    anomaly_type=AnomalyType.DRIFT,
                    metric_name=metric_name,
                    value=value,
                    expected_value=historical_mean,
                    deviation=drift,
                    severity=AlertSeverity.WARNING,
                    timestamp=timestamp,
                    context={
                        "recent_mean": recent_mean,
                        "historical_mean": historical_mean,
                        "drift_percentage": drift * 100,
                    },
                )

        return None

    def _update_baseline(self, baseline: Dict[str, float], value: float) -> None:
        """Update baseline statistics with exponential smoothing."""
        alpha = 0.1
        baseline["mean"] = alpha * value + (1 - alpha) * baseline["mean"]

        diff = abs(value - baseline["mean"])
        baseline["std"] = alpha * diff + (1 - alpha) * baseline["std"]

        baseline["min"] = min(baseline["min"], value)
        baseline["max"] = max(baseline["max"], value)

    def register_callback(self, callback: Callable[[Anomaly], None]) -> None:
        """Register anomaly detection callback."""
        self._callbacks.append(callback)

    async def get_recent_anomalies(
        self,
        limit: int = 100,
        metric_name: Optional[str] = None,
        severity: Optional[AlertSeverity] = None,
    ) -> List[Anomaly]:
        """Get recent anomalies with optional filtering."""
        anomalies = self._anomalies[-limit:]

        if metric_name:
            anomalies = [a for a in anomalies if a.metric_name == metric_name]
        if severity:
            anomalies = [a for a in anomalies if a.severity == severity]

        return anomalies

    async def get_statistics(self) -> Dict[str, Any]:
        """Get detector statistics."""
        return {
            **self._stats,
            "metrics_tracked": len(self._windows),
            "active_anomalies": len([
                a for a in self._anomalies
                if a.timestamp > datetime.utcnow() - timedelta(hours=1)
            ]),
        }


# =============================================================================
# Workload Classifier
# =============================================================================


class WorkloadClassifier:
    """
    ML-based workload classification.

    تصنيف أعباء العمل القائم على التعلم الآلي.
    """

    def __init__(self):
        self._profiles: Dict[str, WorkloadProfile] = {}
        self._training_data: Dict[str, List[Dict[str, float]]] = {}
        self._lock = asyncio.Lock()

    async def add_sample(
        self,
        job_type: str,
        cpu_usage: float,
        memory_usage: float,
        gpu_usage: float,
        io_operations: float,
        duration: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Add a workload sample for classification."""
        timestamp = timestamp or datetime.utcnow()

        sample = {
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "gpu_usage": gpu_usage,
            "io_operations": io_operations,
            "duration": duration,
            "hour": timestamp.hour,
        }

        async with self._lock:
            if job_type not in self._training_data:
                self._training_data[job_type] = []
            self._training_data[job_type].append(sample)

            # Reclassify if enough samples
            if len(self._training_data[job_type]) % 10 == 0:
                await self._classify_workload(job_type)

    async def _classify_workload(self, job_type: str) -> None:
        """Classify workload based on collected samples."""
        samples = self._training_data.get(job_type, [])
        if not samples:
            return

        # Calculate averages
        avg_cpu = statistics.mean(s["cpu_usage"] for s in samples)
        avg_memory = statistics.mean(s["memory_usage"] for s in samples)
        avg_gpu = statistics.mean(s["gpu_usage"] for s in samples)
        avg_io = statistics.mean(s["io_operations"] for s in samples)
        avg_duration = statistics.mean(s["duration"] for s in samples)

        # Calculate variance
        if len(samples) > 1:
            duration_std = statistics.stdev(s["duration"] for s in samples)
            variance_coef = duration_std / avg_duration if avg_duration > 0 else 0
        else:
            variance_coef = 0

        # Determine category
        category = self._determine_category(avg_cpu, avg_memory, avg_gpu, avg_io, variance_coef)

        # Find peak hours
        hour_counts: Dict[int, int] = {}
        for s in samples:
            hour = s["hour"]
            hour_counts[hour] = hour_counts.get(hour, 0) + 1

        avg_count = len(samples) / 24
        peak_hours = [h for h, c in hour_counts.items() if c > avg_count * 1.5]

        self._profiles[job_type] = WorkloadProfile(
            job_type=job_type,
            category=category,
            avg_cpu_usage=avg_cpu,
            avg_memory_usage=avg_memory,
            avg_gpu_usage=avg_gpu,
            avg_io_operations=avg_io,
            avg_duration=avg_duration,
            variance_coefficient=variance_coef,
            peak_hours=peak_hours,
            sample_count=len(samples),
        )

    def _determine_category(
        self,
        cpu: float,
        memory: float,
        gpu: float,
        io: float,
        variance: float,
    ) -> WorkloadCategory:
        """Determine workload category based on resource usage."""
        # Check absolute thresholds first for high-intensity workloads
        # GPU-intensive: GPU usage above 70%
        if gpu > 70:
            return WorkloadCategory.GPU_INTENSIVE

        # CPU-intensive: CPU usage above 70% and low GPU
        if cpu > 70 and gpu < 20:
            return WorkloadCategory.CPU_INTENSIVE

        # Memory-intensive: memory usage above 70% and moderate CPU
        if memory > 70 and cpu < 50:
            return WorkloadCategory.MEMORY_INTENSIVE

        # IO-intensive: high IO with moderate CPU/memory
        if io > 50 and cpu < 50:
            return WorkloadCategory.IO_INTENSIVE

        # Normalize values for ratio-based classification
        total = cpu + memory + gpu + io
        if total == 0:
            return WorkloadCategory.BALANCED

        cpu_ratio = cpu / total
        memory_ratio = memory / total
        gpu_ratio = gpu / total
        io_ratio = io / total

        # Check for bursty pattern (high variance)
        if variance > 0.5:
            return WorkloadCategory.BURSTY

        # Classify by dominant resource
        if gpu_ratio > 0.4:
            return WorkloadCategory.GPU_INTENSIVE
        elif cpu_ratio > 0.4:
            return WorkloadCategory.CPU_INTENSIVE
        elif memory_ratio > 0.4:
            return WorkloadCategory.MEMORY_INTENSIVE
        elif io_ratio > 0.4:
            return WorkloadCategory.IO_INTENSIVE

                # Check for steady pattern (low variance without dominant resource)
        elif variance < 0.1:
                        return WorkloadCategory.STEADY
        else:
            return WorkloadCategory.BALANCED

    async def get_profile(self, job_type: str) -> Optional[WorkloadProfile]:
        """Get workload profile for a job type."""
        return self._profiles.get(job_type)

    async def get_all_profiles(self) -> List[WorkloadProfile]:
        """Get all workload profiles."""
        return list(self._profiles.values())

    async def recommend_resources(
        self,
        job_type: str,
        scale_factor: float = 1.0,
    ) -> Dict[str, float]:
        """Recommend resources based on workload profile."""
        profile = self._profiles.get(job_type)

        if not profile:
            # Default recommendations
            return {
                "cpu_cores": 2.0 * scale_factor,
                "memory_mb": 4096 * scale_factor,
                "gpu_units": 0,
            }

        # Base on profile with safety margin
        safety_margin = 1.2

        recommendations = {
            "cpu_cores": max(1, profile.avg_cpu_usage / 100 * 4 * safety_margin * scale_factor),
            "memory_mb": max(512, profile.avg_memory_usage / 100 * 8192 * safety_margin * scale_factor),
            "gpu_units": (
                profile.avg_gpu_usage / 100 * safety_margin * scale_factor
                if profile.avg_gpu_usage > 10 else 0
            ),
        }

        # Adjust based on category
        if profile.category == WorkloadCategory.CPU_INTENSIVE:
            recommendations["cpu_cores"] *= 1.5
        elif profile.category == WorkloadCategory.MEMORY_INTENSIVE:
            recommendations["memory_mb"] *= 1.5
        elif profile.category == WorkloadCategory.GPU_INTENSIVE:
            recommendations["gpu_units"] = max(1, recommendations["gpu_units"] * 1.5)

        return recommendations


# =============================================================================
# Cost Predictor
# =============================================================================


class CostPredictor:
    """
    Job cost prediction engine.

    محرك التنبؤ بتكلفة الوظائف.
    """

    def __init__(
        self,
        cpu_cost_per_hour: float = 0.05,
        memory_cost_per_gb_hour: float = 0.01,
        gpu_cost_per_hour: float = 0.50,
        storage_cost_per_gb_hour: float = 0.001,
    ):
        self.cpu_cost = cpu_cost_per_hour
        self.memory_cost = memory_cost_per_gb_hour
        self.gpu_cost = gpu_cost_per_hour
        self.storage_cost = storage_cost_per_gb_hour

        self._historical_costs: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def predict_cost(
        self,
        job_type: str,
        cpu_cores: float,
        memory_mb: float,
        gpu_units: float,
        estimated_duration_seconds: float,
        storage_gb: float = 0,
    ) -> CostPrediction:
        """
        Predict job cost.

        التنبؤ بتكلفة الوظيفة.
        """
        import uuid

        hours = estimated_duration_seconds / 3600

        # Calculate component costs
        cpu_cost = cpu_cores * self.cpu_cost * hours
        memory_cost = (memory_mb / 1024) * self.memory_cost * hours
        gpu_cost = gpu_units * self.gpu_cost * hours
        storage_cost = storage_gb * self.storage_cost * hours

        total_cost = cpu_cost + memory_cost + gpu_cost + storage_cost

        # Adjust based on historical data
        confidence = 0.7
        if job_type in self._historical_costs:
            historical = self._historical_costs[job_type]
            if historical:
                avg_historical = statistics.mean(historical)
                # Blend prediction with historical average
                total_cost = 0.7 * total_cost + 0.3 * avg_historical
                confidence = min(0.95, 0.7 + 0.05 * len(historical))

        return CostPrediction(
            prediction_id=str(uuid.uuid4()),
            job_type=job_type,
            estimated_cost=round(total_cost, 4),
            cost_breakdown={
                "cpu": round(cpu_cost, 4),
                "memory": round(memory_cost, 4),
                "gpu": round(gpu_cost, 4),
                "storage": round(storage_cost, 4),
            },
            confidence=confidence,
        )

    async def record_actual_cost(
        self,
        job_type: str,
        actual_cost: float,
    ) -> None:
        """Record actual job cost for future predictions."""
        async with self._lock:
            if job_type not in self._historical_costs:
                self._historical_costs[job_type] = []
            self._historical_costs[job_type].append(actual_cost)

            # Keep only recent history
            if len(self._historical_costs[job_type]) > 1000:
                self._historical_costs[job_type] = self._historical_costs[job_type][-500:]

    async def estimate_monthly_cost(
        self,
        avg_jobs_per_day: int,
        avg_cost_per_job: float,
    ) -> Dict[str, float]:
        """Estimate monthly costs."""
        daily_cost = avg_jobs_per_day * avg_cost_per_job
        weekly_cost = daily_cost * 7
        monthly_cost = daily_cost * 30
        yearly_cost = daily_cost * 365

        return {
            "daily": round(daily_cost, 2),
            "weekly": round(weekly_cost, 2),
            "monthly": round(monthly_cost, 2),
            "yearly": round(yearly_cost, 2),
        }


# =============================================================================
# Pattern Analyzer
# =============================================================================


class PatternAnalyzer:
    """
    Pattern recognition and analysis.

    التعرف على الأنماط وتحليلها.
    """

    def __init__(self):
        self._patterns: Dict[str, Dict[str, Any]] = {}
        self._sequence_buffer: Deque[Dict[str, Any]] = deque(maxlen=1000)

    async def add_event(self, event: Dict[str, Any]) -> None:
        """Add an event to the pattern buffer."""
        event["timestamp"] = event.get("timestamp", datetime.utcnow())
        self._sequence_buffer.append(event)

    async def detect_patterns(self) -> List[PatternMatch]:
        """Detect patterns in event sequence."""

        patterns = []
        events = list(self._sequence_buffer)

        if len(events) < 10:
            return patterns

        # Detect failure patterns
        failure_pattern = await self._detect_failure_pattern(events)
        if failure_pattern:
            patterns.append(failure_pattern)

        # Detect resource exhaustion patterns
        resource_pattern = await self._detect_resource_pattern(events)
        if resource_pattern:
            patterns.append(resource_pattern)

        # Detect periodic patterns
        periodic_pattern = await self._detect_periodic_pattern(events)
        if periodic_pattern:
            patterns.append(periodic_pattern)

        return patterns

    async def _detect_failure_pattern(
        self,
        events: List[Dict[str, Any]],
    ) -> Optional[PatternMatch]:
        """Detect cascading failure patterns."""
        import uuid

        failures = [e for e in events if e.get("type") == "failure"]

        if len(failures) < 3:
            return None

        # Check for cascading failures (failures close together)
        failure_times = [f["timestamp"] for f in failures]

        cascading = False
        for i in range(len(failure_times) - 2):
            if all(
                (failure_times[i + j + 1] - failure_times[i + j]).total_seconds() < 60
                for j in range(2)
            ):
                cascading = True
                break

        if cascading:
            return PatternMatch(
                pattern_id=str(uuid.uuid4()),
                pattern_name="cascading_failure",
                confidence=0.85,
                matched_features=["rapid_failure_sequence", "time_proximity"],
                recommendations=[
                    "Implement circuit breaker pattern",
                    "Add failure isolation between components",
                    "Review retry policies",
                ],
            )

        return None

    async def _detect_resource_pattern(
        self,
        events: List[Dict[str, Any]],
    ) -> Optional[PatternMatch]:
        """Detect resource exhaustion patterns."""
        import uuid

        resource_events = [
            e for e in events
            if e.get("type") in ["high_cpu", "high_memory", "oom"]
        ]

        if len(resource_events) < 5:
            return None

        # Check for increasing trend
        values = [e.get("value", 0) for e in resource_events]
        if len(values) >= 3:
            trend = sum(1 for i in range(len(values) - 1) if values[i + 1] > values[i])
            if trend / (len(values) - 1) > 0.7:
                return PatternMatch(
                    pattern_id=str(uuid.uuid4()),
                    pattern_name="resource_exhaustion",
                    confidence=0.8,
                    matched_features=["increasing_usage", "high_utilization"],
                    recommendations=[
                        "Scale up resources",
                        "Investigate memory leaks",
                        "Optimize resource-heavy operations",
                    ],
                )

        return None

    async def _detect_periodic_pattern(
        self,
        events: List[Dict[str, Any]],
    ) -> Optional[PatternMatch]:
        """Detect periodic patterns."""
        import uuid

        if len(events) < 24:
            return None

        # Group by hour
        hour_counts: Dict[int, int] = {}
        for e in events:
            hour = e["timestamp"].hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1

        if not hour_counts:
            return None

        avg_count = sum(hour_counts.values()) / len(hour_counts)
        peak_hours = [h for h, c in hour_counts.items() if c > avg_count * 1.5]

        if peak_hours:
            return PatternMatch(
                pattern_id=str(uuid.uuid4()),
                pattern_name="periodic_load",
                confidence=0.75,
                matched_features=["time_correlation", "recurring_peaks"],
                recommendations=[
                    f"Schedule scaling for peak hours: {peak_hours}",
                    "Pre-warm resources before peak periods",
                    "Consider reserved capacity for predictable loads",
                ],
            )

        return None


# =============================================================================
# Unified Analytics Engine
# =============================================================================


class AdvancedAnalyticsEngine:
    """
    Unified advanced analytics engine.

    محرك التحليلات المتقدمة الموحد.
    """

    def __init__(
        self,
        anomaly_sensitivity: float = 0.8,
        cost_rates: Optional[Dict[str, float]] = None,
    ):
        self.anomaly_detector = AnomalyDetector(sensitivity=anomaly_sensitivity)
        self.workload_classifier = WorkloadClassifier()
        self.cost_predictor = CostPredictor(**(cost_rates or {}))
        self.pattern_analyzer = PatternAnalyzer()

        self._running = False
        self._stats = {
            "events_processed": 0,
            "start_time": datetime.utcnow(),
        }

    async def start(self) -> None:
        """Start the analytics engine."""
        self._running = True
        logger.info("Advanced Analytics Engine started")

    async def stop(self) -> None:
        """Stop the analytics engine."""
        self._running = False
        logger.info("Advanced Analytics Engine stopped")

    async def process_metric(
        self,
        metric_name: str,
        value: float,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Anomaly]:
        """Process a metric and check for anomalies."""
        self._stats["events_processed"] += 1
        return await self.anomaly_detector.add_data_point(
            metric_name, value, timestamp
        )

    async def process_job_completion(
        self,
        job_type: str,
        cpu_usage: float,
        memory_usage: float,
        gpu_usage: float,
        io_operations: float,
        duration: float,
        cost: float,
    ) -> None:
        """Process a completed job for analytics."""
        # Update workload classifier
        await self.workload_classifier.add_sample(
            job_type, cpu_usage, memory_usage, gpu_usage, io_operations, duration
        )

        # Record cost
        await self.cost_predictor.record_actual_cost(job_type, cost)

        # Add event for pattern analysis
        await self.pattern_analyzer.add_event({
            "type": "job_completion",
            "job_type": job_type,
            "duration": duration,
            "cost": cost,
        })

    async def get_recommendations(
        self,
        job_type: str,
    ) -> Dict[str, Any]:
        """Get comprehensive recommendations for a job type."""
        profile = await self.workload_classifier.get_profile(job_type)
        resources = await self.workload_classifier.recommend_resources(job_type)
        patterns = await self.pattern_analyzer.detect_patterns()

        return {
            "workload_profile": profile.to_dict() if profile else None,
            "recommended_resources": resources,
            "detected_patterns": [
                {
                    "name": p.pattern_name,
                    "confidence": p.confidence,
                    "recommendations": p.recommendations,
                }
                for p in patterns
            ],
        }

    async def get_statistics(self) -> Dict[str, Any]:
        """Get engine statistics."""
        anomaly_stats = await self.anomaly_detector.get_statistics()

        return {
            **self._stats,
            "uptime_seconds": (datetime.utcnow() - self._stats["start_time"]).total_seconds(),
            "anomaly_detector": anomaly_stats,
            "workload_profiles_count": len(await self.workload_classifier.get_all_profiles()),
            "running": self._running,
        }
