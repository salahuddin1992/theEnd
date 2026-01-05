"""
Cache Analytics - Deep insights into cache performance.

This module provides comprehensive analytics for cache operations including
hit rate analysis, access pattern insights, cost optimization metrics,
and anomaly detection for cache behavior.
"""

import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of cache metrics."""

    HIT_RATE = "hit_rate"
    MISS_RATE = "miss_rate"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    MEMORY_USAGE = "memory_usage"
    EVICTION_RATE = "eviction_rate"
    WRITE_RATE = "write_rate"
    ENTRY_COUNT = "entry_count"


class AnomalyType(Enum):
    """Types of cache anomalies."""

    HIT_RATE_DROP = "hit_rate_drop"
    LATENCY_SPIKE = "latency_spike"
    EVICTION_SURGE = "eviction_surge"
    MEMORY_PRESSURE = "memory_pressure"
    THUNDERING_HERD = "thundering_herd"
    HOT_KEY = "hot_key"
    CACHE_POLLUTION = "cache_pollution"


class TimeGranularity(Enum):
    """Time granularities for analytics."""

    SECOND = 1
    MINUTE = 60
    HOUR = 3600
    DAY = 86400


@dataclass
class CacheEvent:
    """Represents a single cache event."""

    timestamp: float
    event_type: str  # 'hit', 'miss', 'write', 'delete', 'evict'
    key: str
    latency_ms: float
    value_size: int = 0
    tags: Set[str] = field(default_factory=set)


@dataclass
class TimeSeriesPoint:
    """A point in a time series."""

    timestamp: datetime
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CacheAnomaly:
    """Detected cache anomaly."""

    anomaly_type: AnomalyType
    timestamp: datetime
    severity: float  # 0-1
    description: str
    affected_keys: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    recommended_action: str = ""


@dataclass
class KeyAnalytics:
    """Analytics for a specific cache key."""

    key: str
    hit_count: int = 0
    miss_count: int = 0
    write_count: int = 0
    last_access: Optional[datetime] = None
    total_latency_ms: float = 0.0
    avg_value_size: float = 0.0
    access_pattern: str = "unknown"  # 'hot', 'warm', 'cold', 'bursty'


@dataclass
class AnalyticsReport:
    """Comprehensive cache analytics report."""

    period_start: datetime
    period_end: datetime
    total_operations: int
    hit_rate: float
    miss_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    throughput_ops: float
    memory_usage_mb: float
    entry_count: int
    eviction_count: int
    top_hot_keys: List[Tuple[str, int]]
    top_slow_keys: List[Tuple[str, float]]
    anomalies: List[CacheAnomaly]
    recommendations: List[str]


class TimeSeriesBuffer:
    """Efficient time series data buffer with aggregation."""

    def __init__(self, granularity: TimeGranularity, max_points: int = 10000):
        self.granularity = granularity
        self.max_points = max_points
        self.points: deque = deque(maxlen=max_points)
        self._lock = threading.Lock()

    def add(self, value: float, timestamp: Optional[datetime] = None):
        """Add a value to the time series."""
        if timestamp is None:
            timestamp = datetime.now()

        # Round to granularity
        ts = timestamp.timestamp()
        bucket = int(ts // self.granularity.value) * self.granularity.value
        bucket_dt = datetime.fromtimestamp(bucket)

        with self._lock:
            # Check if we should aggregate with last point
            if self.points and self.points[-1].timestamp == bucket_dt:
                # Update existing bucket (running average)
                last = self.points[-1]
                count = last.metadata.get("count", 1)
                new_count = count + 1
                new_value = (last.value * count + value) / new_count
                last.value = new_value
                last.metadata["count"] = new_count
                last.metadata["max"] = max(last.metadata.get("max", value), value)
                last.metadata["min"] = min(last.metadata.get("min", value), value)
            else:
                self.points.append(
                    TimeSeriesPoint(timestamp=bucket_dt, value=value, metadata={"count": 1, "max": value, "min": value})
                )

    def get_range(self, start: Optional[datetime] = None, end: Optional[datetime] = None) -> List[TimeSeriesPoint]:
        """Get points in a time range."""
        with self._lock:
            points = list(self.points)

        if start:
            points = [p for p in points if p.timestamp >= start]
        if end:
            points = [p for p in points if p.timestamp <= end]

        return points

    def get_average(self, window_seconds: float = 60.0) -> float:
        """Get average value over a time window."""
        cutoff = datetime.now() - timedelta(seconds=window_seconds)
        points = self.get_range(start=cutoff)

        if not points:
            return 0.0

        return statistics.mean([p.value for p in points])


class AccessPatternAnalyzer:
    """Analyzes cache access patterns for optimization insights."""

    def __init__(self, window_size: int = 100000):
        self.window_size = window_size
        self.key_stats: Dict[str, KeyAnalytics] = {}
        self.access_sequence: deque = deque(maxlen=window_size)
        self.inter_arrival_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._lock = threading.Lock()

    def record_access(self, event: CacheEvent):
        """Record a cache access event."""
        with self._lock:
            key = event.key

            # Initialize or update key stats
            if key not in self.key_stats:
                self.key_stats[key] = KeyAnalytics(key=key)

            stats = self.key_stats[key]

            if event.event_type == "hit":
                stats.hit_count += 1
            elif event.event_type == "miss":
                stats.miss_count += 1
            elif event.event_type == "write":
                stats.write_count += 1

            stats.total_latency_ms += event.latency_ms
            stats.last_access = datetime.fromtimestamp(event.timestamp)

            if event.value_size > 0:
                count = stats.hit_count + stats.miss_count + stats.write_count
                stats.avg_value_size = (stats.avg_value_size * (count - 1) + event.value_size) / count

            # Track inter-arrival time
            if self.access_sequence:
                last_access = None
                for prev_event in reversed(self.access_sequence):
                    if prev_event.key == key:
                        last_access = prev_event.timestamp
                        break

                if last_access:
                    iat = event.timestamp - last_access
                    self.inter_arrival_times[key].append(iat)

            self.access_sequence.append(event)

    def classify_key(self, key: str) -> str:
        """Classify a key's access pattern."""
        with self._lock:
            if key not in self.key_stats:
                return "unknown"

            stats = self.key_stats[key]
            total = stats.hit_count + stats.miss_count

            if total < 5:
                return "cold"

            # Calculate access frequency
            if stats.last_access:
                age = (datetime.now() - stats.last_access).total_seconds()
                frequency = total / (age + 1)
            else:
                frequency = 0

            # Check burstiness
            if key in self.inter_arrival_times and len(self.inter_arrival_times[key]) >= 5:
                iats = list(self.inter_arrival_times[key])
                cv = statistics.stdev(iats) / (statistics.mean(iats) + 0.001)
                if cv > 2.0:
                    return "bursty"

            # Classify by frequency
            if frequency > 10:
                return "hot"
            elif frequency > 1:
                return "warm"
            else:
                return "cold"

    def get_hot_keys(self, count: int = 20) -> List[Tuple[str, int]]:
        """Get the most frequently accessed keys."""
        with self._lock:
            sorted_keys = sorted(self.key_stats.items(), key=lambda x: x[1].hit_count + x[1].miss_count, reverse=True)
            return [(k, v.hit_count + v.miss_count) for k, v in sorted_keys[:count]]

    def get_slow_keys(self, count: int = 20) -> List[Tuple[str, float]]:
        """Get keys with highest average latency."""
        with self._lock:
            result = []
            for key, stats in self.key_stats.items():
                total = stats.hit_count + stats.miss_count + stats.write_count
                if total > 0:
                    avg_latency = stats.total_latency_ms / total
                    result.append((key, avg_latency))

            result.sort(key=lambda x: x[1], reverse=True)
            return result[:count]


class AnomalyDetector:
    """Detects anomalies in cache behavior."""

    def __init__(
        self,
        hit_rate_threshold: float = 0.7,
        latency_threshold_ms: float = 100.0,
        eviction_rate_threshold: float = 100.0,  # per minute
    ):
        self.hit_rate_threshold = hit_rate_threshold
        self.latency_threshold_ms = latency_threshold_ms
        self.eviction_rate_threshold = eviction_rate_threshold

        # Historical baselines
        self.hit_rate_history: deque = deque(maxlen=1000)
        self.latency_history: deque = deque(maxlen=1000)
        self.eviction_history: deque = deque(maxlen=1000)

        # Hot key tracking
        self.key_access_counts: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        self._lock = threading.Lock()

    def record_metrics(self, hit_rate: float, latency_ms: float, evictions: int):
        """Record current metrics for baseline calculation."""
        with self._lock:
            self.hit_rate_history.append(hit_rate)
            self.latency_history.append(latency_ms)
            self.eviction_history.append(evictions)

    def record_key_access(self, key: str):
        """Record a key access for hot key detection."""
        current_time = time.time()
        with self._lock:
            self.key_access_counts[key].append(current_time)

    def detect_anomalies(
        self, current_hit_rate: float, current_latency: float, current_evictions: int, memory_percent: float = 0.0
    ) -> List[CacheAnomaly]:
        """Detect anomalies based on current metrics."""
        anomalies = []

        with self._lock:
            # Hit rate drop
            if len(self.hit_rate_history) >= 10:
                baseline = statistics.mean(list(self.hit_rate_history)[-100:])
                if current_hit_rate < baseline * 0.8 and current_hit_rate < self.hit_rate_threshold:
                    severity = min(1.0, (baseline - current_hit_rate) / baseline)
                    anomalies.append(
                        CacheAnomaly(
                            anomaly_type=AnomalyType.HIT_RATE_DROP,
                            timestamp=datetime.now(),
                            severity=severity,
                            description=f"Hit rate dropped from {baseline:.2%} to {current_hit_rate:.2%}",
                            metrics={"baseline": baseline, "current": current_hit_rate},
                            recommended_action="Consider increasing cache size or reviewing eviction policy",
                        )
                    )

            # Latency spike
            if len(self.latency_history) >= 10:
                baseline = statistics.mean(list(self.latency_history)[-100:])
                if current_latency > baseline * 2 and current_latency > self.latency_threshold_ms:
                    severity = min(1.0, (current_latency - baseline) / baseline)
                    anomalies.append(
                        CacheAnomaly(
                            anomaly_type=AnomalyType.LATENCY_SPIKE,
                            timestamp=datetime.now(),
                            severity=severity,
                            description=f"Latency spiked from {baseline:.2f}ms to {current_latency:.2f}ms",
                            metrics={"baseline": baseline, "current": current_latency},
                            recommended_action="Check for memory pressure or GC activity",
                        )
                    )

            # Eviction surge
            if len(self.eviction_history) >= 10:
                baseline = statistics.mean(list(self.eviction_history)[-100:])
                if current_evictions > baseline * 3 and current_evictions > self.eviction_rate_threshold:
                    severity = min(1.0, (current_evictions - baseline) / (baseline + 1))
                    anomalies.append(
                        CacheAnomaly(
                            anomaly_type=AnomalyType.EVICTION_SURGE,
                            timestamp=datetime.now(),
                            severity=severity,
                            description=f"Evictions surged from {baseline:.1f} to {current_evictions}",
                            metrics={"baseline": baseline, "current": current_evictions},
                            recommended_action="Consider increasing cache size or adjusting TTL",
                        )
                    )

            # Memory pressure
            if memory_percent > 90:
                severity = min(1.0, (memory_percent - 90) / 10)
                anomalies.append(
                    CacheAnomaly(
                        anomaly_type=AnomalyType.MEMORY_PRESSURE,
                        timestamp=datetime.now(),
                        severity=severity,
                        description=f"Cache memory usage at {memory_percent:.1f}%",
                        metrics={"memory_percent": memory_percent},
                        recommended_action="Consider enabling compression or reducing cache size",
                    )
                )

            # Hot key detection
            hot_keys = self._detect_hot_keys()
            if hot_keys:
                anomalies.append(
                    CacheAnomaly(
                        anomaly_type=AnomalyType.HOT_KEY,
                        timestamp=datetime.now(),
                        severity=0.5,
                        description=f"Detected {len(hot_keys)} hot keys consuming disproportionate resources",
                        affected_keys=hot_keys,
                        recommended_action="Consider separate caching tier for hot keys",
                    )
                )

        return anomalies

    def _detect_hot_keys(self, threshold_ratio: float = 0.1) -> List[str]:
        """Detect keys that receive disproportionate traffic."""
        current_time = time.time()
        window = 60.0  # Last minute

        hot_keys = []
        total_accesses = 0
        key_counts: Dict[str, int] = {}

        for key, accesses in self.key_access_counts.items():
            count = sum(1 for t in accesses if current_time - t <= window)
            if count > 0:
                key_counts[key] = count
                total_accesses += count

        if total_accesses < 100:
            return []

        # Keys with more than threshold_ratio of total traffic
        for key, count in key_counts.items():
            if count / total_accesses > threshold_ratio:
                hot_keys.append(key)

        return hot_keys


class CacheAnalytics:
    """
    Comprehensive cache analytics engine that provides deep insights
    into cache performance and behavior.
    """

    def __init__(self, enable_detailed_tracking: bool = True, anomaly_detection_enabled: bool = True):
        self.enable_detailed_tracking = enable_detailed_tracking
        self.anomaly_detection_enabled = anomaly_detection_enabled

        # Time series metrics
        self.hit_rate_series = TimeSeriesBuffer(TimeGranularity.MINUTE)
        self.latency_series = TimeSeriesBuffer(TimeGranularity.MINUTE)
        self.throughput_series = TimeSeriesBuffer(TimeGranularity.MINUTE)
        self.memory_series = TimeSeriesBuffer(TimeGranularity.MINUTE)
        self.eviction_series = TimeSeriesBuffer(TimeGranularity.MINUTE)

        # Pattern analyzer
        self.pattern_analyzer = AccessPatternAnalyzer()

        # Anomaly detector
        self.anomaly_detector = AnomalyDetector()

        # Real-time metrics
        self.current_hits = 0
        self.current_misses = 0
        self.current_evictions = 0
        self.current_writes = 0
        self.latencies: deque = deque(maxlen=10000)

        # Event log
        self.event_log: deque = deque(maxlen=100000)

        # Detected anomalies
        self.anomalies: deque = deque(maxlen=100)

        # State
        self._lock = threading.Lock()
        self._last_snapshot_time = time.time()

    def record_hit(self, key: str, latency_ms: float, value_size: int = 0):
        """Record a cache hit."""
        self._record_event("hit", key, latency_ms, value_size)

    def record_miss(self, key: str, latency_ms: float):
        """Record a cache miss."""
        self._record_event("miss", key, latency_ms, 0)

    def record_write(self, key: str, latency_ms: float, value_size: int):
        """Record a cache write."""
        self._record_event("write", key, latency_ms, value_size)

    def record_eviction(self, key: str):
        """Record a cache eviction."""
        self._record_event("evict", key, 0, 0)

    def _record_event(self, event_type: str, key: str, latency_ms: float, value_size: int):
        """Record a cache event."""
        current_time = time.time()

        event = CacheEvent(
            timestamp=current_time,
            event_type=event_type,
            key=key,
            latency_ms=latency_ms,
            value_size=value_size,
        )

        with self._lock:
            # Update counters
            if event_type == "hit":
                self.current_hits += 1
            elif event_type == "miss":
                self.current_misses += 1
            elif event_type == "write":
                self.current_writes += 1
            elif event_type == "evict":
                self.current_evictions += 1

            self.latencies.append(latency_ms)

            # Store event for detailed tracking
            if self.enable_detailed_tracking:
                self.event_log.append(event)

            # Update pattern analyzer
            self.pattern_analyzer.record_access(event)

            # Update anomaly detector
            self.anomaly_detector.record_key_access(key)

        # Periodic snapshot
        if current_time - self._last_snapshot_time >= 60.0:
            self._take_snapshot()

    def _take_snapshot(self):
        """Take a metrics snapshot."""
        with self._lock:
            total = self.current_hits + self.current_misses
            hit_rate = self.current_hits / total if total > 0 else 0

            avg_latency = statistics.mean(self.latencies) if self.latencies else 0

            # Update time series
            self.hit_rate_series.add(hit_rate)
            self.latency_series.add(avg_latency)
            self.throughput_series.add(total)
            self.eviction_series.add(self.current_evictions)

            # Record for anomaly baseline
            self.anomaly_detector.record_metrics(
                hit_rate=hit_rate, latency_ms=avg_latency, evictions=self.current_evictions
            )

            # Reset counters
            self.current_hits = 0
            self.current_misses = 0
            self.current_evictions = 0
            self.current_writes = 0
            self.latencies.clear()
            self._last_snapshot_time = time.time()

    def update_memory_usage(self, memory_mb: float):
        """Update memory usage metric."""
        self.memory_series.add(memory_mb)

    def detect_anomalies(self, memory_percent: float = 0.0) -> List[CacheAnomaly]:
        """Detect current anomalies."""
        if not self.anomaly_detection_enabled:
            return []

        with self._lock:
            total = self.current_hits + self.current_misses
            hit_rate = self.current_hits / total if total > 0 else 0
            avg_latency = statistics.mean(self.latencies) if self.latencies else 0

        anomalies = self.anomaly_detector.detect_anomalies(
            current_hit_rate=hit_rate,
            current_latency=avg_latency,
            current_evictions=self.current_evictions,
            memory_percent=memory_percent,
        )

        for anomaly in anomalies:
            self.anomalies.append(anomaly)

        return anomalies

    def get_current_metrics(self) -> Dict[str, float]:
        """Get current real-time metrics."""
        with self._lock:
            total = self.current_hits + self.current_misses
            hit_rate = self.current_hits / total if total > 0 else 0

            if self.latencies:
                sorted_latencies = sorted(self.latencies)
                avg_latency = statistics.mean(sorted_latencies)
                p95_idx = int(len(sorted_latencies) * 0.95)
                p99_idx = int(len(sorted_latencies) * 0.99)
                p95_latency = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
                p99_latency = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]
            else:
                avg_latency = p95_latency = p99_latency = 0

            return {
                "hit_rate": hit_rate,
                "miss_rate": 1 - hit_rate,
                "hits": self.current_hits,
                "misses": self.current_misses,
                "writes": self.current_writes,
                "evictions": self.current_evictions,
                "avg_latency_ms": avg_latency,
                "p95_latency_ms": p95_latency,
                "p99_latency_ms": p99_latency,
            }

    def get_time_series(
        self, metric: MetricType, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> List[TimeSeriesPoint]:
        """Get time series data for a metric."""
        series_map = {
            MetricType.HIT_RATE: self.hit_rate_series,
            MetricType.LATENCY: self.latency_series,
            MetricType.THROUGHPUT: self.throughput_series,
            MetricType.MEMORY_USAGE: self.memory_series,
            MetricType.EVICTION_RATE: self.eviction_series,
        }

        series = series_map.get(metric)
        if series:
            return series.get_range(start, end)
        return []

    def get_hot_keys(self, count: int = 20) -> List[Tuple[str, int]]:
        """Get most frequently accessed keys."""
        return self.pattern_analyzer.get_hot_keys(count)

    def get_slow_keys(self, count: int = 20) -> List[Tuple[str, float]]:
        """Get keys with highest latency."""
        return self.pattern_analyzer.get_slow_keys(count)

    def get_key_analytics(self, key: str) -> Optional[KeyAnalytics]:
        """Get analytics for a specific key."""
        with self.pattern_analyzer._lock:
            return self.pattern_analyzer.key_stats.get(key)

    def classify_key(self, key: str) -> str:
        """Classify a key's access pattern."""
        return self.pattern_analyzer.classify_key(key)

    def generate_report(self, period_hours: float = 24.0) -> AnalyticsReport:
        """Generate a comprehensive analytics report."""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=period_hours)

        # Get time series data
        hit_rates = self.hit_rate_series.get_range(start_time, end_time)
        latencies = self.latency_series.get_range(start_time, end_time)
        throughputs = self.throughput_series.get_range(start_time, end_time)
        memory = self.memory_series.get_range(start_time, end_time)
        evictions = self.eviction_series.get_range(start_time, end_time)

        # Calculate aggregates
        avg_hit_rate = statistics.mean([p.value for p in hit_rates]) if hit_rates else 0
        avg_latency = statistics.mean([p.value for p in latencies]) if latencies else 0
        total_ops = sum(p.value for p in throughputs)
        avg_memory = statistics.mean([p.value for p in memory]) if memory else 0
        total_evictions = sum(p.value for p in evictions)

        # Calculate latency percentiles from event log
        with self._lock:
            recent_events = [e for e in self.event_log if datetime.fromtimestamp(e.timestamp) >= start_time]

        event_latencies = [e.latency_ms for e in recent_events if e.latency_ms > 0]
        if event_latencies:
            sorted_lats = sorted(event_latencies)
            p95 = sorted_lats[int(len(sorted_lats) * 0.95)]
            p99 = sorted_lats[int(len(sorted_lats) * 0.99)]
        else:
            p95 = p99 = 0

        # Get hot and slow keys
        hot_keys = self.get_hot_keys(10)
        slow_keys = self.get_slow_keys(10)

        # Get recent anomalies
        recent_anomalies = [a for a in self.anomalies if a.timestamp >= start_time]

        # Generate recommendations
        recommendations = self._generate_recommendations(avg_hit_rate, avg_latency, total_evictions, hot_keys)

        return AnalyticsReport(
            period_start=start_time,
            period_end=end_time,
            total_operations=int(total_ops),
            hit_rate=avg_hit_rate,
            miss_rate=1 - avg_hit_rate,
            avg_latency_ms=avg_latency,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            throughput_ops=total_ops / (period_hours * 3600) if period_hours > 0 else 0,
            memory_usage_mb=avg_memory,
            entry_count=len(self.pattern_analyzer.key_stats),
            eviction_count=int(total_evictions),
            top_hot_keys=hot_keys,
            top_slow_keys=slow_keys,
            anomalies=recent_anomalies,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self, hit_rate: float, avg_latency: float, evictions: int, hot_keys: List[Tuple[str, int]]
    ) -> List[str]:
        """Generate optimization recommendations."""
        recommendations = []

        if hit_rate < 0.8:
            recommendations.append("Hit rate is below 80%. Consider increasing cache size or adjusting TTL.")

        if hit_rate < 0.5:
            recommendations.append("Very low hit rate. Review cache key generation strategy.")

        if avg_latency > 50:
            recommendations.append("Average latency is high. Consider enabling compression or reducing value sizes.")

        if avg_latency > 100:
            recommendations.append("Critical latency issues. Review cache backend performance.")

        if evictions > 1000:
            recommendations.append("High eviction rate. Cache size may be too small for workload.")

        if hot_keys and len(hot_keys) > 0:
            top_key, top_count = hot_keys[0]
            if top_count > 10000:
                recommendations.append(f"Hot key detected ({top_key}). Consider dedicated caching or replication.")

        return recommendations

    def get_analytics_summary(self) -> Dict[str, Any]:
        """Get a summary of analytics data."""
        current = self.get_current_metrics()
        hot_keys = self.get_hot_keys(5)
        slow_keys = self.get_slow_keys(5)
        recent_anomalies = list(self.anomalies)[-5:]

        return {
            "current_metrics": current,
            "hit_rate_trend": self.hit_rate_series.get_average(window_seconds=300),
            "latency_trend": self.latency_series.get_average(window_seconds=300),
            "throughput_trend": self.throughput_series.get_average(window_seconds=300),
            "hot_keys": hot_keys,
            "slow_keys": slow_keys,
            "recent_anomalies": [
                {
                    "type": a.anomaly_type.value,
                    "timestamp": a.timestamp.isoformat(),
                    "severity": a.severity,
                    "description": a.description,
                }
                for a in recent_anomalies
            ],
            "tracked_keys_count": len(self.pattern_analyzer.key_stats),
            "total_events_logged": len(self.event_log),
        }
