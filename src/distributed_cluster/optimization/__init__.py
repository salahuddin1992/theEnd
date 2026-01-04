"""
Optimization Module - Comprehensive caching and performance optimization system.

This module provides a unified API for cache optimization, performance
tuning, and distributed cluster optimization including:

- Intelligent cache optimization based on workload patterns
- System-wide performance optimization
- Proactive cache warmup strategies
- Deep cache analytics and insights
- Specialized scheduler query caching
- Efficient memory pool management
- Hot data tracking and prioritization
- Distributed cache coordination
- Comprehensive performance profiling
"""

from .cache_analytics import (
    AccessPatternAnalyzer,
    AnalyticsReport,
    AnomalyDetector,
    AnomalyType,
    CacheAnalytics,
    CacheAnomaly,
    CacheEvent,
    KeyAnalytics,
    MetricType,
    TimeGranularity,
    TimeSeriesBuffer,
    TimeSeriesPoint,
)
from .cache_optimizer import (
    AccessPattern,
    AdaptiveTTLManager,
    CacheConfiguration,
    CacheMetrics,
    CacheOptimizer,
    OptimizationRecommendation,
    OptimizationStrategy,
    WorkloadCharacteristics,
    WorkloadType,
)
from .cache_warmup import (
    AccessPatternPredictor,
    CacheRefresher,
    CacheWarmer,
    HistoricalWarmupSource,
    IncrementalWarmer,
    StaticWarmupSource,
    WarmupDataSource,
    WarmupItem,
    WarmupPriority,
    WarmupResult,
    WarmupStats,
    WarmupStrategy,
)
from .distributed_coordinator import (
    CacheNode,
    ConsistencyLevel,
    ConsistentHash,
    DistributedCacheCoordinator,
    NodeStatus,
    Partition,
    PartitionManager,
    ReplicationEvent,
    ReplicationManager,
    ReplicationStrategy,
)
from .hot_data_tracker import (
    AccessEventType,
    FrequencyCounter,
    HotDataConfig,
    HotDataReplicator,
    HotDataTracker,
    HotLevel,
    KeyMetrics,
    RecencyTracker,
)
from .memory_pool import (
    MemoryBlock,
    MemoryPoolManager,
    MemoryPressureHandler,
    MemoryPressureLevel,
    MemoryStats,
    ObjectPool,
    PoolConfig,
    SlabAllocator,
    SlabClass,
)
from .performance_optimizer import (
    AdaptiveConnectionPool,
    AdaptiveThreadPool,
    BottleneckDetector,
    BottleneckType,
    OptimizationAction,
    OptimizationLevel,
    PerformanceMetrics,
    PerformanceOptimizer,
    PerformanceProfile,
    QueryOptimizer,
    ResourceMetrics,
    ResourceMonitor,
    track_performance,
)
from .performance_profiler import (
    FlameGraphProfiler,
    LatencyHistogram,
    OperationContext,
    OperationProfile,
    OperationStats,
    OperationType,
    PerformanceProfiler,
    ProfileLevel,
    ProfileSnapshot,
    profile_function,
)
from .query_cache import (
    BatchQueryCache,
    CachedQuery,
    CachedQueryExecutor,
    JobStatusCache,
    QueryCache,
    QueryCacheConfig,
    QueryKeyBuilder,
    QueryType,
    SchedulerStateCache,
    WorkerStatusCache,
    cached_query,
)

__all__ = [
    # Cache Optimizer
    'CacheOptimizer',
    'CacheConfiguration',
    'CacheMetrics',
    'WorkloadType',
    'WorkloadCharacteristics',
    'OptimizationStrategy',
    'OptimizationRecommendation',
    'AccessPattern',
    'AdaptiveTTLManager',

    # Performance Optimizer
    'PerformanceOptimizer',
    'ResourceMonitor',
    'BottleneckDetector',
    'BottleneckType',
    'ResourceMetrics',
    'PerformanceMetrics',
    'PerformanceProfile',
    'OptimizationLevel',
    'OptimizationAction',
    'AdaptiveConnectionPool',
    'AdaptiveThreadPool',
    'QueryOptimizer',
    'track_performance',

    # Cache Warmup
    'CacheWarmer',
    'WarmupStrategy',
    'WarmupPriority',
    'WarmupItem',
    'WarmupResult',
    'WarmupStats',
    'WarmupDataSource',
    'StaticWarmupSource',
    'HistoricalWarmupSource',
    'AccessPatternPredictor',
    'IncrementalWarmer',
    'CacheRefresher',

    # Cache Analytics
    'CacheAnalytics',
    'CacheEvent',
    'CacheAnomaly',
    'AnomalyType',
    'MetricType',
    'KeyAnalytics',
    'AnalyticsReport',
    'TimeSeriesBuffer',
    'TimeSeriesPoint',
    'TimeGranularity',
    'AccessPatternAnalyzer',
    'AnomalyDetector',

    # Query Cache
    'QueryCache',
    'QueryType',
    'QueryCacheConfig',
    'QueryKeyBuilder',
    'CachedQuery',
    'CachedQueryExecutor',
    'BatchQueryCache',
    'WorkerStatusCache',
    'JobStatusCache',
    'SchedulerStateCache',
    'cached_query',

    # Memory Pool
    'MemoryPoolManager',
    'SlabAllocator',
    'MemoryBlock',
    'SlabClass',
    'MemoryStats',
    'PoolConfig',
    'MemoryPressureLevel',
    'MemoryPressureHandler',
    'ObjectPool',

    # Hot Data Tracker
    'HotDataTracker',
    'HotLevel',
    'HotDataConfig',
    'KeyMetrics',
    'AccessEventType',
    'FrequencyCounter',
    'RecencyTracker',
    'HotDataReplicator',

    # Distributed Coordinator
    'DistributedCacheCoordinator',
    'ConsistentHash',
    'ReplicationManager',
    'PartitionManager',
    'CacheNode',
    'Partition',
    'NodeStatus',
    'ReplicationStrategy',
    'ConsistencyLevel',
    'ReplicationEvent',

    # Performance Profiler
    'PerformanceProfiler',
    'ProfileLevel',
    'OperationType',
    'OperationProfile',
    'OperationStats',
    'OperationContext',
    'ProfileSnapshot',
    'LatencyHistogram',
    'FlameGraphProfiler',
    'profile_function',

    # Unified API
    'OptimizationManager',
]


class OptimizationManager:
    """
    Unified optimization manager that coordinates all optimization
    components for comprehensive cache and performance optimization.
    """

    def __init__(
        self,
        node_id: str = "node-1",
        enable_cache_optimization: bool = True,
        enable_performance_optimization: bool = True,
        enable_warmup: bool = True,
        enable_analytics: bool = True,
        enable_profiling: bool = True,
        enable_distributed: bool = False,
        optimization_level: OptimizationLevel = OptimizationLevel.ADAPTIVE,
        profile_level: ProfileLevel = ProfileLevel.BASIC,
    ):
        self.node_id = node_id
        self._running = False

        # Initialize components based on configuration
        self.cache_optimizer = None
        self.performance_optimizer = None
        self.cache_warmer = None
        self.analytics = None
        self.query_cache = None
        self.memory_pool = None
        self.hot_data_tracker = None
        self.distributed_coordinator = None
        self.profiler = None

        if enable_cache_optimization:
            self.cache_optimizer = CacheOptimizer(
                strategy=OptimizationStrategy.ADAPTIVE
            )

        if enable_performance_optimization:
            self.performance_optimizer = PerformanceOptimizer(
                level=optimization_level
            )

        if enable_warmup:
            async def dummy_set(k, v, t):
                return True
            self.cache_warmer = CacheWarmer(cache_set=dummy_set)

        if enable_analytics:
            self.analytics = CacheAnalytics()

        self.query_cache = QueryCache()
        self.memory_pool = MemoryPoolManager()
        self.hot_data_tracker = HotDataTracker()

        if enable_distributed:
            self.distributed_coordinator = DistributedCacheCoordinator(
                node_id=node_id
            )

        if enable_profiling:
            self.profiler = PerformanceProfiler(level=profile_level)

    async def start(self):
        """Start all optimization components."""
        if self._running:
            return

        self._running = True

        if self.performance_optimizer:
            await self.performance_optimizer.start_async()

        if self.cache_optimizer:
            await self.cache_optimizer.start_background_optimization()

        if self.cache_warmer:
            await self.cache_warmer.start_background_warming()

        if self.query_cache:
            await self.query_cache.start_cleanup_loop()

        if self.memory_pool:
            await self.memory_pool.start_monitoring()

        if self.hot_data_tracker:
            await self.hot_data_tracker.start_decay_loop()

        if self.distributed_coordinator:
            await self.distributed_coordinator.start_heartbeat()

        if self.profiler:
            await self.profiler.start_snapshot_loop()

    async def stop(self):
        """Stop all optimization components."""
        self._running = False

        if self.performance_optimizer:
            await self.performance_optimizer.stop_async()

        if self.cache_optimizer:
            await self.cache_optimizer.stop_background_optimization()

        if self.cache_warmer:
            await self.cache_warmer.stop_background_warming()

        if self.query_cache:
            await self.query_cache.stop_cleanup_loop()

        if self.memory_pool:
            await self.memory_pool.stop_monitoring()

        if self.hot_data_tracker:
            await self.hot_data_tracker.stop_decay_loop()

        if self.distributed_coordinator:
            await self.distributed_coordinator.stop_heartbeat()

        if self.profiler:
            await self.profiler.stop_snapshot_loop()

    def record_cache_operation(
        self,
        key: str,
        operation: str,
        hit: bool = True,
        latency_ms: float = 0.0,
        value_size: int = 0
    ):
        """Record a cache operation across all relevant components."""
        if self.cache_optimizer:
            self.cache_optimizer.record_operation(
                key, operation, hit, latency_ms, value_size
            )

        if self.analytics:
            if operation == 'r' and hit:
                self.analytics.record_hit(key, latency_ms, value_size)
            elif operation == 'r':
                self.analytics.record_miss(key, latency_ms)
            elif operation == 'w':
                self.analytics.record_write(key, latency_ms, value_size)

        if self.hot_data_tracker:
            event_type = AccessEventType.READ if operation == 'r' else AccessEventType.WRITE
            self.hot_data_tracker.record_access(key, event_type, latency_ms, value_size)

        if self.cache_warmer:
            self.cache_warmer.record_access(key)

        if self.profiler:
            op_type = OperationType.CACHE_GET if operation == 'r' else OperationType.CACHE_SET
            self.profiler.record_operation(
                op_type, latency_ms, success=True, key=key, size=value_size
            )

    def get_comprehensive_report(self) -> dict:
        """Get a comprehensive report from all components."""
        report = {
            'node_id': self.node_id,
            'running': self._running,
        }

        if self.cache_optimizer:
            report['cache_optimization'] = self.cache_optimizer.get_optimization_report()

        if self.performance_optimizer:
            report['performance_optimization'] = self.performance_optimizer.get_optimization_report()

        if self.analytics:
            report['cache_analytics'] = self.analytics.get_analytics_summary()

        if self.query_cache:
            report['query_cache'] = self.query_cache.get_stats()

        if self.memory_pool:
            report['memory_pool'] = self.memory_pool.get_detailed_stats()

        if self.hot_data_tracker:
            report['hot_data'] = self.hot_data_tracker.get_stats()

        if self.distributed_coordinator:
            report['distributed_cluster'] = self.distributed_coordinator.get_cluster_stats()

        if self.profiler:
            report['profiling'] = self.profiler.get_profiling_report()

        return report

    def get_recommendations(self) -> list:
        """Get optimization recommendations from all components."""
        recommendations = []

        if self.cache_optimizer:
            recs = self.cache_optimizer.analyze_and_recommend()
            for rec in recs:
                recommendations.append({
                    'source': 'cache_optimizer',
                    'parameter': rec.parameter,
                    'current': rec.current_value,
                    'recommended': rec.recommended_value,
                    'reason': rec.reason,
                    'priority': rec.priority,
                    'confidence': rec.confidence,
                })

        if self.analytics:
            report = self.analytics.generate_report()
            for rec in report.recommendations:
                recommendations.append({
                    'source': 'analytics',
                    'parameter': None,
                    'current': None,
                    'recommended': None,
                    'reason': rec,
                    'priority': 5,
                    'confidence': 0.7,
                })

        return sorted(recommendations, key=lambda r: r['priority'], reverse=True)
