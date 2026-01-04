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
    async_read_json,
    async_write_file,
    async_write_json,
)
from distributed_cluster.core.performance.batching import (
    BatchConfig,
    BatchProcessor,
    batch_items,
)

# Benchmarking
from distributed_cluster.core.performance.benchmarking import (
    Benchmarker,
    BenchmarkReport,
    BenchmarkUnit,
    MemoryResult,
    PerformanceMonitor,
    TimingResult,
    compare_functions,
    profile_memory,
    quick_async_benchmark,
    quick_benchmark,
    timed,
)
from distributed_cluster.core.performance.caching import (
    async_lru_cache,
    memoize,
    timed_cache,
)

# Circuit Breaker
from distributed_cluster.core.performance.circuit_breaker import (
    Bulkhead,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    CircuitBreakerStats,
    CircuitOpenError,
    CircuitState,
    ResiliencePolicy,
    Retry,
    RetryConfig,
    bulkhead,
    circuit_breaker,
    get_circuit_breaker,
    retry,
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

# Rate Limiter
from distributed_cluster.core.performance.rate_limiter import (
    AdaptiveRateLimiter,
    FixedWindowLimiter,
    LeakyBucketLimiter,
    RateLimitAlgorithm,
    RateLimitConfig,
    RateLimiter,
    RateLimiterManager,
    RateLimitExceeded,
    RateLimitResult,
    RedisRateLimiter,
    SlidingWindowLimiter,
    TierConfig,
    TieredRateLimiter,
    TokenBucketLimiter,
    create_rate_limit_middleware,
    create_rate_limiter,
    get_rate_limiter,
    rate_limit,
)

# Unified Resilience Module
from distributed_cluster.core.performance.resilience import (
    EnhancedCircuitBreaker,
    EnhancedCircuitBreakerConfig,
    EnhancedCircuitBreakerError,
    EnhancedCircuitBreakerStats,
    EnhancedCircuitOpenError,
    # Enhanced Circuit Breaker
    EnhancedCircuitState,
    # Health Monitoring
    HealthCheckResult,
    HealthMonitor,
    # Health states and events
    HealthState,
    LoggingEventListener,
    RateLimitStrategy,
    # Resilience Manager
    ResilienceConfig,
    ResilienceEvent,
    ResilienceEventData,
    ResilienceEventListener,
    ResilienceManager,
    # Rate Limiters
    SlidingWindowCounterConfig,
    SlidingWindowCounterLimiter,
    SlidingWindowCounterResult,
    TokenBucketConfig,
    TokenBucketRateLimiter,
    UnifiedRateLimitConfig,
    UnifiedRateLimiter,
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
