"""
Performance Optimizations - تحسينات الأداء
==========================================

Performance Optimization Module
-------------------------------

This module provides performance optimization utilities:
- Async I/O helpers
- Connection pooling
- Memory-mapped file I/O
- Batching utilities
- Caching decorators

يوفر هذا الملف أدوات تحسين الأداء:
- مساعدات I/O غير متزامنة
- تجميع الاتصالات
- ملفات مخطوطة بالذاكرة
- أدوات التجميع
- مزخرفات التخزين المؤقت

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.core.performance.async_io import (
    AsyncFileReader,
    AsyncFileWriter,
    async_read_file,
    async_write_file,
    async_read_json,
    async_write_json,
)
from distributed_cluster.core.performance.connection_pool import (
    ConnectionPool,
    ConnectionPoolConfig,
    PooledConnection,
)
from distributed_cluster.core.performance.mmap_io import (
    MemoryMappedFile,
    MMapReader,
    MMapWriter,
)
from distributed_cluster.core.performance.batching import (
    BatchProcessor,
    BatchConfig,
    batch_items,
)
from distributed_cluster.core.performance.caching import (
    async_lru_cache,
    timed_cache,
    memoize,
)

# Circuit Breaker
from distributed_cluster.core.performance.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    CircuitBreakerStats,
    CircuitOpenError,
    CircuitState,
    Bulkhead,
    Retry,
    RetryConfig,
    ResiliencePolicy,
    circuit_breaker,
    bulkhead,
    retry,
    get_circuit_breaker,
)

# Rate Limiter
from distributed_cluster.core.performance.rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    RateLimitResult,
    RateLimitExceeded,
    RateLimitAlgorithm,
    TokenBucketLimiter,
    SlidingWindowLimiter,
    FixedWindowLimiter,
    LeakyBucketLimiter,
    TieredRateLimiter,
    TierConfig,
    AdaptiveRateLimiter,
    RateLimiterManager,
    RedisRateLimiter,
    create_rate_limiter,
    get_rate_limiter,
    rate_limit,
    create_rate_limit_middleware,
)

# Benchmarking
from distributed_cluster.core.performance.benchmarking import (
    Benchmarker,
    BenchmarkReport,
    BenchmarkUnit,
    TimingResult,
    MemoryResult,
    PerformanceMonitor,
    timed,
    profile_memory,
    quick_benchmark,
    quick_async_benchmark,
    compare_functions,
)

# Unified Resilience Module
from distributed_cluster.core.performance.resilience import (
    # Health states and events
    HealthState,
    ResilienceEvent,
    ResilienceEventData,
    ResilienceEventListener,
    LoggingEventListener,
    # Enhanced Circuit Breaker
    EnhancedCircuitState,
    EnhancedCircuitBreakerConfig,
    EnhancedCircuitBreakerStats,
    EnhancedCircuitBreakerError,
    EnhancedCircuitOpenError,
    EnhancedCircuitBreaker,
    # Rate Limiters
    SlidingWindowCounterConfig,
    SlidingWindowCounterResult,
    SlidingWindowCounterLimiter,
    TokenBucketConfig,
    TokenBucketRateLimiter,
    RateLimitStrategy,
    UnifiedRateLimitConfig,
    UnifiedRateLimiter,
    # Health Monitoring
    HealthCheckResult,
    HealthMonitor,
    # Resilience Manager
    ResilienceConfig,
    ResilienceManager,
    # Factory and Decorators
    get_resilience_manager,
    resilient,
)

__all__ = [
    # Async I/O
    "AsyncFileReader",
    "AsyncFileWriter",
    "async_read_file",
    "async_write_file",
    "async_read_json",
    "async_write_json",
    # Connection Pool
    "ConnectionPool",
    "ConnectionPoolConfig",
    "PooledConnection",
    # Memory-Mapped I/O
    "MemoryMappedFile",
    "MMapReader",
    "MMapWriter",
    # Batching
    "BatchProcessor",
    "BatchConfig",
    "batch_items",
    # Caching
    "async_lru_cache",
    "timed_cache",
    "memoize",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "CircuitBreakerRegistry",
    "CircuitBreakerStats",
    "CircuitOpenError",
    "CircuitState",
    "Bulkhead",
    "Retry",
    "RetryConfig",
    "ResiliencePolicy",
    "circuit_breaker",
    "bulkhead",
    "retry",
    "get_circuit_breaker",
    # Rate Limiter
    "RateLimiter",
    "RateLimitConfig",
    "RateLimitResult",
    "RateLimitExceeded",
    "RateLimitAlgorithm",
    "TokenBucketLimiter",
    "SlidingWindowLimiter",
    "FixedWindowLimiter",
    "LeakyBucketLimiter",
    "TieredRateLimiter",
    "TierConfig",
    "AdaptiveRateLimiter",
    "RateLimiterManager",
    "RedisRateLimiter",
    "create_rate_limiter",
    "get_rate_limiter",
    "rate_limit",
    "create_rate_limit_middleware",
    # Benchmarking
    "Benchmarker",
    "BenchmarkReport",
    "BenchmarkUnit",
    "TimingResult",
    "MemoryResult",
    "PerformanceMonitor",
    "timed",
    "profile_memory",
    "quick_benchmark",
    "quick_async_benchmark",
    "compare_functions",
    # Unified Resilience Module
    "HealthState",
    "ResilienceEvent",
    "ResilienceEventData",
    "ResilienceEventListener",
    "LoggingEventListener",
    "EnhancedCircuitState",
    "EnhancedCircuitBreakerConfig",
    "EnhancedCircuitBreakerStats",
    "EnhancedCircuitBreakerError",
    "EnhancedCircuitOpenError",
    "EnhancedCircuitBreaker",
    "SlidingWindowCounterConfig",
    "SlidingWindowCounterResult",
    "SlidingWindowCounterLimiter",
    "TokenBucketConfig",
    "TokenBucketRateLimiter",
    "RateLimitStrategy",
    "UnifiedRateLimitConfig",
    "UnifiedRateLimiter",
    "HealthCheckResult",
    "HealthMonitor",
    "ResilienceConfig",
    "ResilienceManager",
    "get_resilience_manager",
    "resilient",
]
