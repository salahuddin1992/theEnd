"""
Cache Optimizer - Intelligent cache tuning based on workload patterns.

This module provides adaptive cache optimization that automatically tunes
cache parameters based on observed workload patterns, access frequencies,
and system resource utilization.
"""

import asyncio
import time
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from enum import Enum
from collections import deque, defaultdict
import threading
import logging
import hashlib
import json

logger = logging.getLogger(__name__)


class WorkloadType(Enum):
    """Classification of cache workload patterns."""
    READ_HEAVY = "read_heavy"           # High read-to-write ratio
    WRITE_HEAVY = "write_heavy"         # High write-to-read ratio
    BALANCED = "balanced"               # Approximately equal reads/writes
    BURSTY = "bursty"                   # Irregular access patterns
    SEQUENTIAL = "sequential"           # Sequential access patterns
    RANDOM = "random"                   # Random access patterns
    HOT_COLD = "hot_cold"               # Skewed access (few hot keys)
    UNIFORM = "uniform"                 # Uniform access distribution


class OptimizationStrategy(Enum):
    """Cache optimization strategies."""
    AGGRESSIVE = "aggressive"           # Maximize hit rate
    CONSERVATIVE = "conservative"       # Minimize memory usage
    BALANCED = "balanced"               # Balance hit rate and memory
    LATENCY_FOCUSED = "latency_focused" # Minimize latency
    THROUGHPUT_FOCUSED = "throughput_focused"  # Maximize throughput
    ADAPTIVE = "adaptive"               # Dynamically adjust based on metrics


@dataclass
class CacheMetrics:
    """Snapshot of cache performance metrics."""
    timestamp: datetime = field(default_factory=datetime.now)
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    writes: int = 0
    deletes: int = 0
    memory_bytes: int = 0
    entry_count: int = 0
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    throughput_ops: float = 0.0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def miss_rate(self) -> float:
        """Calculate miss rate."""
        return 1.0 - self.hit_rate


@dataclass
class WorkloadCharacteristics:
    """Characteristics of observed workload."""
    workload_type: WorkloadType
    read_write_ratio: float
    avg_key_size: float
    avg_value_size: float
    access_frequency_std: float  # Standard deviation of access frequency
    temporal_locality: float     # 0-1, higher = more temporal locality
    spatial_locality: float      # 0-1, higher = more spatial locality
    hot_key_ratio: float         # Percentage of keys that are "hot"
    burstiness_score: float      # 0-1, higher = more bursty

    @classmethod
    def default(cls) -> 'WorkloadCharacteristics':
        """Create default characteristics."""
        return cls(
            workload_type=WorkloadType.BALANCED,
            read_write_ratio=1.0,
            avg_key_size=32.0,
            avg_value_size=256.0,
            access_frequency_std=1.0,
            temporal_locality=0.5,
            spatial_locality=0.5,
            hot_key_ratio=0.2,
            burstiness_score=0.3
        )


@dataclass
class OptimizationRecommendation:
    """Recommendation for cache optimization."""
    parameter: str
    current_value: Any
    recommended_value: Any
    reason: str
    priority: int  # 1-10, higher = more important
    estimated_improvement: float  # Estimated % improvement
    confidence: float  # 0-1, confidence in recommendation


@dataclass
class CacheConfiguration:
    """Tunable cache configuration parameters."""
    max_size: int = 10000
    ttl_seconds: int = 300
    eviction_policy: str = "lru"
    write_policy: str = "write_through"
    compression_enabled: bool = True
    compression_threshold: int = 1024
    batch_size: int = 100
    async_writes: bool = True
    prefetch_enabled: bool = True
    prefetch_threshold: float = 0.8
    memory_limit_mb: int = 1024
    l1_size_ratio: float = 0.1
    l2_size_ratio: float = 0.3
    hot_key_threshold: int = 10
    bloom_filter_enabled: bool = True
    bloom_filter_fp_rate: float = 0.01


class AccessPattern:
    """Track and analyze access patterns for optimization."""

    def __init__(self, window_size: int = 10000):
        self.window_size = window_size
        self.access_times: deque = deque(maxlen=window_size)
        self.key_access_counts: Dict[str, int] = defaultdict(int)
        self.key_last_access: Dict[str, float] = {}
        self.operation_types: deque = deque(maxlen=window_size)  # 'r' or 'w'
        self.value_sizes: deque = deque(maxlen=window_size)
        self.inter_arrival_times: deque = deque(maxlen=window_size - 1)
        self._last_access_time: Optional[float] = None
        self._lock = threading.Lock()

    def record_access(self, key: str, operation: str = 'r', value_size: int = 0):
        """Record a cache access."""
        current_time = time.time()

        with self._lock:
            self.access_times.append(current_time)
            self.key_access_counts[key] += 1
            self.key_last_access[key] = current_time
            self.operation_types.append(operation)
            self.value_sizes.append(value_size)

            if self._last_access_time is not None:
                iat = current_time - self._last_access_time
                self.inter_arrival_times.append(iat)
            self._last_access_time = current_time

    def get_workload_type(self) -> WorkloadType:
        """Classify the current workload type."""
        with self._lock:
            if len(self.operation_types) < 100:
                return WorkloadType.BALANCED

            # Calculate read/write ratio
            reads = sum(1 for op in self.operation_types if op == 'r')
            writes = len(self.operation_types) - reads

            if reads > writes * 4:
                base_type = WorkloadType.READ_HEAVY
            elif writes > reads * 4:
                base_type = WorkloadType.WRITE_HEAVY
            else:
                base_type = WorkloadType.BALANCED

            # Check for burstiness
            if len(self.inter_arrival_times) >= 10:
                iat_list = list(self.inter_arrival_times)
                iat_std = statistics.stdev(iat_list) if len(iat_list) > 1 else 0
                iat_mean = statistics.mean(iat_list)
                cv = iat_std / iat_mean if iat_mean > 0 else 0
                if cv > 2.0:
                    return WorkloadType.BURSTY

            # Check for hot/cold pattern
            if len(self.key_access_counts) > 0:
                counts = list(self.key_access_counts.values())
                total_accesses = sum(counts)
                sorted_counts = sorted(counts, reverse=True)
                top_20_pct_keys = max(1, len(sorted_counts) // 5)
                top_20_pct_accesses = sum(sorted_counts[:top_20_pct_keys])

                if top_20_pct_accesses > total_accesses * 0.8:
                    return WorkloadType.HOT_COLD

            return base_type

    def get_characteristics(self) -> WorkloadCharacteristics:
        """Get comprehensive workload characteristics."""
        with self._lock:
            workload_type = self.get_workload_type()

            # Read/write ratio
            reads = sum(1 for op in self.operation_types if op == 'r')
            writes = len(self.operation_types) - reads
            rw_ratio = reads / writes if writes > 0 else float('inf')

            # Value sizes
            avg_value_size = statistics.mean(self.value_sizes) if self.value_sizes else 256.0

            # Access frequency analysis
            counts = list(self.key_access_counts.values())
            freq_std = statistics.stdev(counts) if len(counts) > 1 else 0.0

            # Temporal locality (recency of re-access)
            current_time = time.time()
            if self.key_last_access:
                recencies = [current_time - t for t in self.key_last_access.values()]
                temporal_locality = 1.0 / (1.0 + statistics.mean(recencies))
            else:
                temporal_locality = 0.5

            # Hot key ratio
            if counts:
                total = sum(counts)
                sorted_counts = sorted(counts, reverse=True)
                hot_threshold = total * 0.5
                cumsum = 0
                hot_keys = 0
                for c in sorted_counts:
                    cumsum += c
                    hot_keys += 1
                    if cumsum >= hot_threshold:
                        break
                hot_key_ratio = hot_keys / len(counts)
            else:
                hot_key_ratio = 0.2

            # Burstiness score
            if len(self.inter_arrival_times) > 1:
                iat_list = list(self.inter_arrival_times)
                iat_std = statistics.stdev(iat_list)
                iat_mean = statistics.mean(iat_list)
                burstiness = min(1.0, iat_std / (iat_mean + 0.001))
            else:
                burstiness = 0.3

            return WorkloadCharacteristics(
                workload_type=workload_type,
                read_write_ratio=min(rw_ratio, 100.0),
                avg_key_size=32.0,  # Assumed
                avg_value_size=avg_value_size,
                access_frequency_std=freq_std,
                temporal_locality=min(1.0, temporal_locality),
                spatial_locality=0.5,  # Would need key analysis
                hot_key_ratio=hot_key_ratio,
                burstiness_score=burstiness
            )


class CacheOptimizer:
    """
    Intelligent cache optimizer that analyzes workload patterns
    and automatically tunes cache parameters for optimal performance.
    """

    def __init__(
        self,
        config: Optional[CacheConfiguration] = None,
        strategy: OptimizationStrategy = OptimizationStrategy.ADAPTIVE,
        optimization_interval: float = 60.0,
        metrics_window_size: int = 1000
    ):
        self.config = config or CacheConfiguration()
        self.strategy = strategy
        self.optimization_interval = optimization_interval

        # Metrics tracking
        self.metrics_history: deque = deque(maxlen=metrics_window_size)
        self.current_metrics = CacheMetrics()
        self.access_pattern = AccessPattern()

        # Latency tracking
        self.latencies: deque = deque(maxlen=10000)

        # Optimization state
        self.recommendations: List[OptimizationRecommendation] = []
        self.applied_optimizations: List[Dict[str, Any]] = []
        self.optimization_callbacks: List[Callable[[CacheConfiguration], None]] = []

        # Background optimization
        self._optimization_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = threading.Lock()

        # Configuration bounds
        self._param_bounds = {
            'max_size': (100, 10000000),
            'ttl_seconds': (1, 86400),
            'batch_size': (1, 10000),
            'memory_limit_mb': (10, 65536),
            'l1_size_ratio': (0.01, 0.5),
            'l2_size_ratio': (0.1, 0.8),
            'hot_key_threshold': (1, 1000),
            'prefetch_threshold': (0.1, 0.99),
            'bloom_filter_fp_rate': (0.001, 0.1),
            'compression_threshold': (64, 65536),
        }

    def record_operation(
        self,
        key: str,
        operation: str,
        hit: bool = True,
        latency_ms: float = 0.0,
        value_size: int = 0
    ):
        """Record a cache operation for analysis."""
        with self._lock:
            # Update access pattern
            self.access_pattern.record_access(key, operation, value_size)

            # Update metrics
            if operation == 'r':
                if hit:
                    self.current_metrics.hits += 1
                else:
                    self.current_metrics.misses += 1
            elif operation == 'w':
                self.current_metrics.writes += 1
            elif operation == 'd':
                self.current_metrics.deletes += 1

            # Track latency
            self.latencies.append(latency_ms)

    def record_eviction(self):
        """Record a cache eviction."""
        with self._lock:
            self.current_metrics.evictions += 1

    def update_memory_usage(self, memory_bytes: int, entry_count: int):
        """Update memory usage metrics."""
        with self._lock:
            self.current_metrics.memory_bytes = memory_bytes
            self.current_metrics.entry_count = entry_count

    def snapshot_metrics(self) -> CacheMetrics:
        """Create a metrics snapshot and reset counters."""
        with self._lock:
            # Calculate latency stats
            if self.latencies:
                latency_list = list(self.latencies)
                self.current_metrics.avg_latency_ms = statistics.mean(latency_list)
                sorted_latencies = sorted(latency_list)
                p99_idx = int(len(sorted_latencies) * 0.99)
                self.current_metrics.p99_latency_ms = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]

            # Calculate throughput
            if len(self.access_pattern.access_times) >= 2:
                time_span = self.access_pattern.access_times[-1] - self.access_pattern.access_times[0]
                if time_span > 0:
                    self.current_metrics.throughput_ops = len(self.access_pattern.access_times) / time_span

            # Create snapshot
            snapshot = CacheMetrics(
                timestamp=datetime.now(),
                hits=self.current_metrics.hits,
                misses=self.current_metrics.misses,
                evictions=self.current_metrics.evictions,
                writes=self.current_metrics.writes,
                deletes=self.current_metrics.deletes,
                memory_bytes=self.current_metrics.memory_bytes,
                entry_count=self.current_metrics.entry_count,
                avg_latency_ms=self.current_metrics.avg_latency_ms,
                p99_latency_ms=self.current_metrics.p99_latency_ms,
                throughput_ops=self.current_metrics.throughput_ops
            )

            # Store in history
            self.metrics_history.append(snapshot)

            # Reset counters
            self.current_metrics = CacheMetrics()
            self.latencies.clear()

            return snapshot

    def analyze_and_recommend(self) -> List[OptimizationRecommendation]:
        """Analyze current state and generate optimization recommendations."""
        recommendations = []

        if len(self.metrics_history) < 2:
            return recommendations

        # Get recent metrics and workload characteristics
        recent_metrics = list(self.metrics_history)[-10:]
        characteristics = self.access_pattern.get_characteristics()

        # Aggregate metrics
        avg_hit_rate = statistics.mean([m.hit_rate for m in recent_metrics])
        avg_evictions = statistics.mean([m.evictions for m in recent_metrics])
        avg_latency = statistics.mean([m.avg_latency_ms for m in recent_metrics])

        # Generate recommendations based on strategy
        if self.strategy == OptimizationStrategy.AGGRESSIVE:
            recommendations.extend(self._aggressive_recommendations(
                avg_hit_rate, avg_evictions, avg_latency, characteristics
            ))
        elif self.strategy == OptimizationStrategy.CONSERVATIVE:
            recommendations.extend(self._conservative_recommendations(
                avg_hit_rate, avg_evictions, characteristics
            ))
        elif self.strategy == OptimizationStrategy.LATENCY_FOCUSED:
            recommendations.extend(self._latency_recommendations(
                avg_latency, characteristics
            ))
        elif self.strategy == OptimizationStrategy.THROUGHPUT_FOCUSED:
            recommendations.extend(self._throughput_recommendations(
                avg_evictions, characteristics
            ))
        else:  # BALANCED or ADAPTIVE
            recommendations.extend(self._balanced_recommendations(
                avg_hit_rate, avg_evictions, avg_latency, characteristics
            ))

        # Sort by priority
        recommendations.sort(key=lambda r: r.priority, reverse=True)
        self.recommendations = recommendations

        return recommendations

    def _aggressive_recommendations(
        self,
        hit_rate: float,
        evictions: float,
        latency: float,
        characteristics: WorkloadCharacteristics
    ) -> List[OptimizationRecommendation]:
        """Generate aggressive optimization recommendations."""
        recs = []

        # Increase cache size if hit rate is low
        if hit_rate < 0.9 and evictions > 0:
            new_size = min(
                self.config.max_size * 2,
                self._param_bounds['max_size'][1]
            )
            if new_size != self.config.max_size:
                recs.append(OptimizationRecommendation(
                    parameter='max_size',
                    current_value=self.config.max_size,
                    recommended_value=new_size,
                    reason=f"Hit rate {hit_rate:.2%} is below 90%, increase cache size",
                    priority=9,
                    estimated_improvement=min(20.0, (0.9 - hit_rate) * 100),
                    confidence=0.8
                ))

        # Adjust TTL based on workload
        if characteristics.workload_type == WorkloadType.READ_HEAVY:
            new_ttl = min(self.config.ttl_seconds * 2, 3600)
            if new_ttl != self.config.ttl_seconds:
                recs.append(OptimizationRecommendation(
                    parameter='ttl_seconds',
                    current_value=self.config.ttl_seconds,
                    recommended_value=new_ttl,
                    reason="Read-heavy workload benefits from longer TTL",
                    priority=7,
                    estimated_improvement=10.0,
                    confidence=0.7
                ))

        # Enable prefetching for high temporal locality
        if characteristics.temporal_locality > 0.7 and not self.config.prefetch_enabled:
            recs.append(OptimizationRecommendation(
                parameter='prefetch_enabled',
                current_value=False,
                recommended_value=True,
                reason="High temporal locality suggests prefetching would help",
                priority=8,
                estimated_improvement=15.0,
                confidence=0.75
            ))

        return recs

    def _conservative_recommendations(
        self,
        hit_rate: float,
        evictions: float,
        characteristics: WorkloadCharacteristics
    ) -> List[OptimizationRecommendation]:
        """Generate conservative optimization recommendations."""
        recs = []

        # Reduce cache size if hit rate is already high
        if hit_rate > 0.95 and evictions < 10:
            new_size = max(
                int(self.config.max_size * 0.8),
                self._param_bounds['max_size'][0]
            )
            if new_size != self.config.max_size:
                recs.append(OptimizationRecommendation(
                    parameter='max_size',
                    current_value=self.config.max_size,
                    recommended_value=new_size,
                    reason=f"Hit rate {hit_rate:.2%} is high with low evictions, can reduce size",
                    priority=5,
                    estimated_improvement=0.0,  # Memory savings, not hit rate
                    confidence=0.7
                ))

        # Enable compression for large values
        if characteristics.avg_value_size > 512 and not self.config.compression_enabled:
            recs.append(OptimizationRecommendation(
                parameter='compression_enabled',
                current_value=False,
                recommended_value=True,
                reason="Large average value size would benefit from compression",
                priority=6,
                estimated_improvement=0.0,
                confidence=0.8
            ))

        return recs

    def _latency_recommendations(
        self,
        latency: float,
        characteristics: WorkloadCharacteristics
    ) -> List[OptimizationRecommendation]:
        """Generate latency-focused optimization recommendations."""
        recs = []

        # Increase L1 cache ratio for lower latency
        if latency > 5.0 and self.config.l1_size_ratio < 0.3:
            new_ratio = min(self.config.l1_size_ratio * 1.5, 0.4)
            recs.append(OptimizationRecommendation(
                parameter='l1_size_ratio',
                current_value=self.config.l1_size_ratio,
                recommended_value=new_ratio,
                reason=f"High latency ({latency:.2f}ms) - increase L1 cache for faster access",
                priority=9,
                estimated_improvement=20.0,
                confidence=0.8
            ))

        # Disable compression for latency-sensitive workloads
        if latency > 10.0 and self.config.compression_enabled:
            recs.append(OptimizationRecommendation(
                parameter='compression_enabled',
                current_value=True,
                recommended_value=False,
                reason="Disable compression to reduce latency overhead",
                priority=7,
                estimated_improvement=15.0,
                confidence=0.6
            ))

        # Enable bloom filter for faster miss detection
        if not self.config.bloom_filter_enabled:
            recs.append(OptimizationRecommendation(
                parameter='bloom_filter_enabled',
                current_value=False,
                recommended_value=True,
                reason="Bloom filter reduces latency for cache misses",
                priority=6,
                estimated_improvement=10.0,
                confidence=0.7
            ))

        return recs

    def _throughput_recommendations(
        self,
        evictions: float,
        characteristics: WorkloadCharacteristics
    ) -> List[OptimizationRecommendation]:
        """Generate throughput-focused optimization recommendations."""
        recs = []

        # Enable async writes for better throughput
        if not self.config.async_writes:
            recs.append(OptimizationRecommendation(
                parameter='async_writes',
                current_value=False,
                recommended_value=True,
                reason="Async writes improve throughput for write operations",
                priority=8,
                estimated_improvement=30.0,
                confidence=0.85
            ))

        # Increase batch size for bursty workloads
        if characteristics.workload_type == WorkloadType.BURSTY:
            new_batch = min(self.config.batch_size * 2, 1000)
            if new_batch != self.config.batch_size:
                recs.append(OptimizationRecommendation(
                    parameter='batch_size',
                    current_value=self.config.batch_size,
                    recommended_value=new_batch,
                    reason="Bursty workload benefits from larger batch sizes",
                    priority=7,
                    estimated_improvement=20.0,
                    confidence=0.7
                ))

        return recs

    def _balanced_recommendations(
        self,
        hit_rate: float,
        evictions: float,
        latency: float,
        characteristics: WorkloadCharacteristics
    ) -> List[OptimizationRecommendation]:
        """Generate balanced optimization recommendations."""
        recs = []

        # Combine recommendations from different strategies with lower priority
        recs.extend(self._aggressive_recommendations(hit_rate, evictions, latency, characteristics))
        recs.extend(self._latency_recommendations(latency, characteristics))
        recs.extend(self._throughput_recommendations(evictions, characteristics))

        # Reduce priority for balanced approach
        for rec in recs:
            rec.priority = max(1, rec.priority - 2)

        # Eviction policy recommendation based on workload
        recommended_policy = self._recommend_eviction_policy(characteristics)
        if recommended_policy != self.config.eviction_policy:
            recs.append(OptimizationRecommendation(
                parameter='eviction_policy',
                current_value=self.config.eviction_policy,
                recommended_value=recommended_policy,
                reason=f"Workload type {characteristics.workload_type.value} suits {recommended_policy} policy",
                priority=6,
                estimated_improvement=10.0,
                confidence=0.7
            ))

        return recs

    def _recommend_eviction_policy(self, characteristics: WorkloadCharacteristics) -> str:
        """Recommend eviction policy based on workload characteristics."""
        if characteristics.workload_type == WorkloadType.HOT_COLD:
            return "lfu"  # LFU works well for hot/cold patterns
        elif characteristics.temporal_locality > 0.7:
            return "lru"  # LRU for high temporal locality
        elif characteristics.workload_type == WorkloadType.SEQUENTIAL:
            return "fifo"  # FIFO for sequential access
        else:
            return "adaptive"  # Adaptive for mixed workloads

    def apply_recommendation(
        self,
        recommendation: OptimizationRecommendation,
        notify: bool = True
    ) -> bool:
        """Apply a specific optimization recommendation."""
        try:
            # Validate the parameter exists
            if not hasattr(self.config, recommendation.parameter):
                logger.error(f"Unknown parameter: {recommendation.parameter}")
                return False

            # Apply the change
            old_value = getattr(self.config, recommendation.parameter)
            setattr(self.config, recommendation.parameter, recommendation.recommended_value)

            # Record the optimization
            self.applied_optimizations.append({
                'timestamp': datetime.now().isoformat(),
                'parameter': recommendation.parameter,
                'old_value': old_value,
                'new_value': recommendation.recommended_value,
                'reason': recommendation.reason
            })

            logger.info(
                f"Applied optimization: {recommendation.parameter} "
                f"{old_value} -> {recommendation.recommended_value}"
            )

            # Notify callbacks
            if notify:
                for callback in self.optimization_callbacks:
                    try:
                        callback(self.config)
                    except Exception as e:
                        logger.error(f"Optimization callback failed: {e}")

            return True

        except Exception as e:
            logger.error(f"Failed to apply recommendation: {e}")
            return False

    def auto_optimize(self, apply_threshold: float = 0.7) -> List[OptimizationRecommendation]:
        """Automatically analyze and apply high-confidence recommendations."""
        recommendations = self.analyze_and_recommend()
        applied = []

        for rec in recommendations:
            if rec.confidence >= apply_threshold and rec.priority >= 7:
                if self.apply_recommendation(rec):
                    applied.append(rec)

        return applied

    async def start_background_optimization(self):
        """Start background optimization loop."""
        if self._running:
            return

        self._running = True
        self._optimization_task = asyncio.create_task(self._optimization_loop())
        logger.info("Started background cache optimization")

    async def stop_background_optimization(self):
        """Stop background optimization loop."""
        self._running = False
        if self._optimization_task:
            self._optimization_task.cancel()
            try:
                await self._optimization_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped background cache optimization")

    async def _optimization_loop(self):
        """Background loop for periodic optimization."""
        while self._running:
            try:
                await asyncio.sleep(self.optimization_interval)

                # Take metrics snapshot
                self.snapshot_metrics()

                # Analyze and apply optimizations
                if self.strategy == OptimizationStrategy.ADAPTIVE:
                    self.auto_optimize()
                else:
                    self.analyze_and_recommend()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Optimization loop error: {e}")

    def register_callback(self, callback: Callable[[CacheConfiguration], None]):
        """Register a callback for configuration changes."""
        self.optimization_callbacks.append(callback)

    def get_optimization_report(self) -> Dict[str, Any]:
        """Get a comprehensive optimization report."""
        characteristics = self.access_pattern.get_characteristics()

        recent_metrics = list(self.metrics_history)[-10:] if self.metrics_history else []

        return {
            'current_configuration': {
                'max_size': self.config.max_size,
                'ttl_seconds': self.config.ttl_seconds,
                'eviction_policy': self.config.eviction_policy,
                'write_policy': self.config.write_policy,
                'compression_enabled': self.config.compression_enabled,
                'async_writes': self.config.async_writes,
                'prefetch_enabled': self.config.prefetch_enabled,
                'l1_size_ratio': self.config.l1_size_ratio,
                'l2_size_ratio': self.config.l2_size_ratio,
            },
            'workload_characteristics': {
                'type': characteristics.workload_type.value,
                'read_write_ratio': characteristics.read_write_ratio,
                'temporal_locality': characteristics.temporal_locality,
                'hot_key_ratio': characteristics.hot_key_ratio,
                'burstiness_score': characteristics.burstiness_score,
            },
            'performance_metrics': {
                'avg_hit_rate': statistics.mean([m.hit_rate for m in recent_metrics]) if recent_metrics else 0,
                'avg_latency_ms': statistics.mean([m.avg_latency_ms for m in recent_metrics]) if recent_metrics else 0,
                'avg_throughput_ops': statistics.mean([m.throughput_ops for m in recent_metrics]) if recent_metrics else 0,
            },
            'recommendations': [
                {
                    'parameter': r.parameter,
                    'current': r.current_value,
                    'recommended': r.recommended_value,
                    'reason': r.reason,
                    'priority': r.priority,
                    'estimated_improvement': r.estimated_improvement,
                    'confidence': r.confidence,
                }
                for r in self.recommendations
            ],
            'applied_optimizations': self.applied_optimizations[-20:],
            'strategy': self.strategy.value,
        }


class AdaptiveTTLManager:
    """
    Manages TTL values adaptively based on access patterns and data freshness requirements.
    """

    def __init__(
        self,
        default_ttl: int = 300,
        min_ttl: int = 10,
        max_ttl: int = 86400
    ):
        self.default_ttl = default_ttl
        self.min_ttl = min_ttl
        self.max_ttl = max_ttl

        # Per-key TTL tracking
        self.key_access_counts: Dict[str, int] = defaultdict(int)
        self.key_last_access: Dict[str, float] = {}
        self.key_ttls: Dict[str, int] = {}

        self._lock = threading.Lock()

    def get_ttl(self, key: str) -> int:
        """Get the optimal TTL for a key based on its access pattern."""
        with self._lock:
            if key not in self.key_ttls:
                return self.default_ttl
            return self.key_ttls[key]

    def record_access(self, key: str):
        """Record an access and update the key's TTL."""
        current_time = time.time()

        with self._lock:
            self.key_access_counts[key] += 1

            # Calculate inter-access time
            if key in self.key_last_access:
                iat = current_time - self.key_last_access[key]
                # Set TTL to 2x the inter-access time, bounded
                new_ttl = int(min(max(iat * 2, self.min_ttl), self.max_ttl))

                # Smooth the TTL update
                if key in self.key_ttls:
                    # Exponential moving average
                    self.key_ttls[key] = int(0.3 * new_ttl + 0.7 * self.key_ttls[key])
                else:
                    self.key_ttls[key] = new_ttl
            else:
                self.key_ttls[key] = self.default_ttl

            self.key_last_access[key] = current_time

    def cleanup_stale_keys(self, max_age: float = 3600):
        """Remove tracking for keys not accessed recently."""
        current_time = time.time()
        cutoff = current_time - max_age

        with self._lock:
            stale_keys = [
                k for k, t in self.key_last_access.items()
                if t < cutoff
            ]

            for key in stale_keys:
                self.key_access_counts.pop(key, None)
                self.key_last_access.pop(key, None)
                self.key_ttls.pop(key, None)
