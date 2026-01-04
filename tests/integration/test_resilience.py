"""
Integration Tests for Resilience Module
=======================================

Comprehensive tests for circuit breaker, rate limiting, and health monitoring.
"""

import asyncio
import time
from typing import List

import pytest

from distributed_cluster.core.performance.resilience import (
    EnhancedCircuitBreaker,
    EnhancedCircuitBreakerConfig,
    EnhancedCircuitOpenError,
    EnhancedCircuitState,
    HealthMonitor,
    HealthState,
    LoggingEventListener,
    RateLimitStrategy,
    ResilienceConfig,
    ResilienceEvent,
    ResilienceEventData,
    ResilienceEventListener,
    ResilienceManager,
    SlidingWindowCounterConfig,
    SlidingWindowCounterLimiter,
    TokenBucketConfig,
    TokenBucketRateLimiter,
    UnifiedRateLimitConfig,
    UnifiedRateLimiter,
    get_resilience_manager,
    resilient,
)

# =============================================================================
# Test Event Listener
# =============================================================================


class MockEventListener(ResilienceEventListener):
    """Event listener for testing that captures all events."""

    def __init__(self):
        self.events: List[ResilienceEventData] = []

    def on_event(self, event: ResilienceEventData) -> None:
        self.events.append(event)

    def get_events_of_type(self, event_type: ResilienceEvent) -> List[ResilienceEventData]:
        return [e for e in self.events if e.event_type == event_type]

    def clear(self) -> None:
        self.events.clear()


# =============================================================================
# Enhanced Circuit Breaker Tests
# =============================================================================


class TestEnhancedCircuitBreaker:
    """Tests for Enhanced Circuit Breaker."""

    @pytest.fixture
    def event_listener(self):
        return MockEventListener()

    @pytest.fixture
    def circuit_breaker(self, event_listener):
        config = EnhancedCircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            reset_timeout=0.5,  # Short timeout for testing
            sliding_window_size=10,
            half_open_max_calls=3,
        )
        return EnhancedCircuitBreaker("test-cb", config, event_listeners=[event_listener])

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self, circuit_breaker):
        """Test that circuit breaker starts in closed state."""
        assert circuit_breaker.state == EnhancedCircuitState.CLOSED
        assert circuit_breaker.is_closed
        assert not circuit_breaker.is_open

    @pytest.mark.asyncio
    async def test_successful_calls_keep_circuit_closed(self, circuit_breaker):
        """Test that successful calls keep the circuit closed."""

        async def success_func():
            return "success"

        for _ in range(5):
            result = await circuit_breaker.execute(success_func)
            assert result == "success"

        assert circuit_breaker.state == EnhancedCircuitState.CLOSED
        assert circuit_breaker.stats.successful_calls == 5
        assert circuit_breaker.stats.failed_calls == 0

    @pytest.mark.asyncio
    async def test_failures_open_circuit(self, circuit_breaker, event_listener):
        """Test that consecutive failures open the circuit."""

        async def fail_func():
            raise ValueError("Test error")

        # Cause enough failures to trip the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await circuit_breaker.execute(fail_func)

        assert circuit_breaker.state == EnhancedCircuitState.OPEN
        assert circuit_breaker.is_open

        # Verify event was emitted
        open_events = event_listener.get_events_of_type(ResilienceEvent.CIRCUIT_OPENED)
        assert len(open_events) == 1

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_calls(self, circuit_breaker):
        """Test that open circuit rejects calls."""

        async def fail_func():
            raise ValueError("Test error")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await circuit_breaker.execute(fail_func)

        # Now calls should be rejected
        async def success_func():
            return "success"

        with pytest.raises(EnhancedCircuitOpenError) as exc_info:
            await circuit_breaker.execute(success_func)

        assert "test-cb" in str(exc_info.value)
        assert circuit_breaker.stats.rejected_calls >= 1

    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open(self, circuit_breaker, event_listener):
        """Test that circuit transitions to half-open after timeout."""

        async def fail_func():
            raise ValueError("Test error")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await circuit_breaker.execute(fail_func)

        assert circuit_breaker.state == EnhancedCircuitState.OPEN

        # Wait for reset timeout
        await asyncio.sleep(0.6)

        # Check state transition
        assert circuit_breaker.state == EnhancedCircuitState.HALF_OPEN

        # Verify event was emitted
        half_open_events = event_listener.get_events_of_type(ResilienceEvent.CIRCUIT_HALF_OPEN)
        assert len(half_open_events) == 1

    @pytest.mark.asyncio
    async def test_half_open_closes_on_success(self, circuit_breaker, event_listener):
        """Test that half-open circuit closes on successful calls."""

        async def fail_func():
            raise ValueError("Test error")

        async def success_func():
            return "success"

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await circuit_breaker.execute(fail_func)

        # Wait for reset timeout
        await asyncio.sleep(0.6)
        assert circuit_breaker.state == EnhancedCircuitState.HALF_OPEN

        # Successful calls should close the circuit
        for _ in range(2):
            result = await circuit_breaker.execute(success_func)
            assert result == "success"

        assert circuit_breaker.state == EnhancedCircuitState.CLOSED

        # Verify event was emitted
        closed_events = event_listener.get_events_of_type(ResilienceEvent.CIRCUIT_CLOSED)
        assert len(closed_events) == 1

    @pytest.mark.asyncio
    async def test_half_open_reopens_on_failure(self, circuit_breaker):
        """Test that half-open circuit reopens on failure."""

        async def fail_func():
            raise ValueError("Test error")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await circuit_breaker.execute(fail_func)

        # Wait for reset timeout
        await asyncio.sleep(0.6)
        assert circuit_breaker.state == EnhancedCircuitState.HALF_OPEN

        # A failure should reopen the circuit
        with pytest.raises(ValueError):
            await circuit_breaker.execute(fail_func)

        assert circuit_breaker.state == EnhancedCircuitState.OPEN

    @pytest.mark.asyncio
    async def test_fallback_on_open_circuit(self, circuit_breaker):
        """Test that fallback is called when circuit is open."""

        async def fail_func():
            raise ValueError("Test error")

        def fallback():
            return "fallback_value"

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await circuit_breaker.execute(fail_func)

        async def success_func():
            return "success"

        # Call with fallback
        result = await circuit_breaker.execute(success_func, fallback=fallback)
        assert result == "fallback_value"

    @pytest.mark.asyncio
    async def test_force_open_and_reset(self, circuit_breaker):
        """Test force open and reset functionality."""
        circuit_breaker.force_open()
        assert circuit_breaker.state == EnhancedCircuitState.FORCED_OPEN

        circuit_breaker.reset()
        assert circuit_breaker.state == EnhancedCircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_disable_and_enable(self, circuit_breaker):
        """Test disable and enable functionality."""

        async def fail_func():
            raise ValueError("Test error")

        # Disable the circuit breaker
        circuit_breaker.disable()
        assert circuit_breaker.state == EnhancedCircuitState.DISABLED

        # Failures should still be tracked but circuit should not open
        for _ in range(5):
            with pytest.raises(ValueError):
                await circuit_breaker.execute(fail_func)

        # Should still be disabled
        assert circuit_breaker.state == EnhancedCircuitState.DISABLED

        # Enable it
        circuit_breaker.enable()
        assert circuit_breaker.state == EnhancedCircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_stats_tracking(self, circuit_breaker):
        """Test statistics tracking."""

        async def success_func():
            return "success"

        async def fail_func():
            raise ValueError("Test error")

        # Some successful calls
        for _ in range(3):
            await circuit_breaker.execute(success_func)

        # Some failed calls
        for _ in range(2):
            with pytest.raises(ValueError):
                await circuit_breaker.execute(fail_func)

        stats = circuit_breaker.stats
        assert stats.total_calls == 5
        assert stats.successful_calls == 3
        assert stats.failed_calls == 2

    @pytest.mark.asyncio
    async def test_decorator_usage(self, circuit_breaker):
        """Test using circuit breaker as a decorator."""

        @circuit_breaker
        async def decorated_func():
            return "decorated_result"

        result = await decorated_func()
        assert result == "decorated_result"
        assert circuit_breaker.stats.successful_calls >= 1

    @pytest.mark.asyncio
    async def test_get_info(self, circuit_breaker):
        """Test getting circuit breaker info."""

        async def success_func():
            return "success"

        await circuit_breaker.execute(success_func)

        info = circuit_breaker.get_info()
        assert info["name"] == "test-cb"
        assert info["state"] == "closed"
        assert "stats" in info
        assert "config" in info


# =============================================================================
# Sliding Window Counter Rate Limiter Tests
# =============================================================================


class TestSlidingWindowCounterLimiter:
    """Tests for Sliding Window Counter Rate Limiter."""

    @pytest.fixture
    def limiter(self):
        config = SlidingWindowCounterConfig(
            requests_per_window=10,
            window_size_seconds=1.0,
            precision_segments=5,
        )
        return SlidingWindowCounterLimiter(config)

    def test_allows_requests_within_limit(self, limiter):
        """Test that requests within limit are allowed."""
        for i in range(10):
            result = limiter.acquire("test-key")
            assert result.allowed, f"Request {i+1} should be allowed"

    def test_denies_requests_over_limit(self, limiter):
        """Test that requests over limit are denied."""
        # Use up the limit
        for _ in range(10):
            limiter.acquire("test-key")

        # Next request should be denied
        result = limiter.acquire("test-key")
        assert not result.allowed
        assert result.retry_after > 0

    def test_different_keys_have_separate_limits(self, limiter):
        """Test that different keys have separate limits."""
        # Use up limit for key1
        for _ in range(10):
            limiter.acquire("key1")

        # key2 should still have capacity
        result = limiter.acquire("key2")
        assert result.allowed

    def test_reset_clears_counts(self, limiter):
        """Test that reset clears counts."""
        # Use up the limit
        for _ in range(10):
            limiter.acquire("test-key")

        # Reset
        limiter.reset("test-key")

        # Should be allowed again
        result = limiter.acquire("test-key")
        assert result.allowed

    def test_returns_correct_headers(self, limiter):
        """Test that result includes correct headers."""
        result = limiter.acquire("test-key")

        headers = result.to_headers()
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers

    @pytest.mark.asyncio
    async def test_async_acquire(self, limiter):
        """Test async acquire method."""
        result = await limiter.acquire_async("test-key")
        assert result.allowed

    def test_stats(self, limiter):
        """Test getting statistics."""
        for _ in range(5):
            limiter.acquire("test-key")

        stats = limiter.get_stats("test-key")
        assert stats["current_count"] == 5
        assert stats["limit"] == 10
        assert stats["remaining"] == 5


# =============================================================================
# Token Bucket Rate Limiter Tests
# =============================================================================


class TestTokenBucketRateLimiter:
    """Tests for Token Bucket Rate Limiter."""

    @pytest.fixture
    def limiter(self):
        config = TokenBucketConfig(
            rate=10.0,  # 10 tokens per second
            capacity=20,  # Max 20 tokens
            initial_tokens=20,
        )
        return TokenBucketRateLimiter(config)

    def test_allows_burst(self, limiter):
        """Test that burst is allowed up to capacity."""
        for i in range(20):
            result = limiter.acquire("test-key")
            assert result.allowed, f"Request {i+1} should be allowed"

    def test_denies_after_burst(self, limiter):
        """Test that requests after burst are denied."""
        # Use up all tokens
        for _ in range(20):
            limiter.acquire("test-key")

        # Next request should be denied
        result = limiter.acquire("test-key")
        assert not result.allowed

    def test_tokens_refill_over_time(self, limiter):
        """Test that tokens refill over time."""
        # Use up all tokens
        for _ in range(20):
            limiter.acquire("test-key")

        # Wait for some tokens to refill (0.1s = 1 token at 10/sec)
        time.sleep(0.15)

        # Should now have at least 1 token
        result = limiter.acquire("test-key")
        assert result.allowed

    def test_get_tokens(self, limiter):
        """Test getting current token count."""
        initial_tokens = limiter.get_tokens("test-key")
        assert initial_tokens == pytest.approx(20, rel=0.01)

        limiter.acquire("test-key", tokens=5)
        remaining_tokens = limiter.get_tokens("test-key")
        assert remaining_tokens == pytest.approx(15, rel=0.01)


# =============================================================================
# Unified Rate Limiter Tests
# =============================================================================


class TestUnifiedRateLimiter:
    """Tests for Unified Rate Limiter."""

    @pytest.fixture
    def event_listener(self):
        return MockEventListener()

    @pytest.fixture
    def limiter(self, event_listener):
        config = UnifiedRateLimitConfig(
            requests_per_second=10.0,
            burst_size=20,
            strategy=RateLimitStrategy.TOKEN_BUCKET,
            warn_threshold=0.8,
        )
        return UnifiedRateLimiter("test-limiter", config, event_listeners=[event_listener])

    def test_allows_requests_within_limit(self, limiter):
        """Test that requests within limit are allowed."""
        for _ in range(10):
            result = limiter.acquire("test-key")
            assert result.allowed

    def test_emits_event_on_limit_exceeded(self, limiter, event_listener):
        """Test that event is emitted when limit is exceeded."""
        # Exhaust the limit
        for _ in range(25):
            limiter.acquire("test-key")

        # Check for rate limit exceeded event
        events = event_listener.get_events_of_type(ResilienceEvent.RATE_LIMIT_EXCEEDED)
        assert len(events) > 0

    def test_stats(self, limiter):
        """Test statistics tracking."""
        for _ in range(5):
            limiter.acquire("test-key")

        stats = limiter.get_stats()
        assert stats["total_requests"] == 5
        assert stats["allowed_requests"] == 5
        assert stats["denied_requests"] == 0


class TestUnifiedRateLimiterMultiLevel:
    """Tests for multi-level rate limiting."""

    @pytest.fixture
    def limiter(self):
        config = UnifiedRateLimitConfig(
            requests_per_second=100.0,
            burst_size=100,
            per_second_limit=10,
            strategy=RateLimitStrategy.TOKEN_BUCKET,
        )
        return UnifiedRateLimiter("multi-level-limiter", config)

    def test_per_second_limit(self, limiter):
        """Test per-second limit is enforced."""
        # Should allow 10 per second
        allowed_count = 0
        for _ in range(15):
            result = limiter.acquire("test-key")
            if result.allowed:
                allowed_count += 1

        # Should have been limited by per-second limit
        assert allowed_count == 10


# =============================================================================
# Health Monitor Tests
# =============================================================================


class TestHealthMonitor:
    """Tests for Health Monitor."""

    @pytest.fixture
    def event_listener(self):
        return MockEventListener()

    @pytest.mark.asyncio
    async def test_healthy_check(self, event_listener):
        """Test healthy check updates state correctly."""

        async def healthy_check():
            return True

        monitor = HealthMonitor(
            "test-monitor",
            healthy_check,
            check_interval=0.1,
            unhealthy_threshold=2,
            healthy_threshold=2,
            event_listeners=[event_listener],
        )

        # Perform checks
        for _ in range(3):
            result = await monitor.check_health()
            assert result.healthy

        assert monitor.state == HealthState.HEALTHY

    @pytest.mark.asyncio
    async def test_unhealthy_check(self, event_listener):
        """Test unhealthy check updates state correctly."""

        async def unhealthy_check():
            return False

        monitor = HealthMonitor(
            "test-monitor",
            unhealthy_check,
            check_interval=0.1,
            unhealthy_threshold=2,
            healthy_threshold=2,
            event_listeners=[event_listener],
        )

        # Perform checks
        for _ in range(3):
            result = await monitor.check_health()
            assert not result.healthy

        assert monitor.state == HealthState.UNHEALTHY

        # Check events
        events = event_listener.get_events_of_type(ResilienceEvent.HEALTH_CHECK_FAILED)
        assert len(events) >= 2

    @pytest.mark.asyncio
    async def test_health_check_timeout(self, event_listener):
        """Test health check timeout handling."""

        async def slow_check():
            await asyncio.sleep(10)  # Will timeout
            return True

        monitor = HealthMonitor(
            "test-monitor",
            slow_check,
            timeout=0.1,
            event_listeners=[event_listener],
        )

        result = await monitor.check_health()
        assert not result.healthy
        assert "timed out" in result.message.lower()

    @pytest.mark.asyncio
    async def test_start_stop(self, event_listener):
        """Test starting and stopping periodic checks."""
        check_count = 0

        async def counting_check():
            nonlocal check_count
            check_count += 1
            return True

        monitor = HealthMonitor(
            "test-monitor",
            counting_check,
            check_interval=0.05,
            event_listeners=[event_listener],
        )

        await monitor.start()
        await asyncio.sleep(0.2)
        await monitor.stop()

        # Should have performed multiple checks
        assert check_count >= 2

    @pytest.mark.asyncio
    async def test_stats(self, event_listener):
        """Test health monitor statistics."""

        async def healthy_check():
            return True

        monitor = HealthMonitor(
            "test-monitor",
            healthy_check,
            event_listeners=[event_listener],
        )

        for _ in range(3):
            await monitor.check_health()

        stats = monitor.get_stats()
        assert stats["total_checks"] == 3
        assert stats["successful_checks"] == 3
        assert stats["success_rate"] == 1.0


# =============================================================================
# Resilience Manager Tests
# =============================================================================


class TestResilienceManager:
    """Tests for Resilience Manager."""

    @pytest.fixture
    def event_listener(self):
        return MockEventListener()

    @pytest.fixture
    def manager(self, event_listener):
        config = ResilienceConfig(
            circuit_breaker_enabled=True,
            rate_limiter_enabled=True,
            circuit_breaker_config=EnhancedCircuitBreakerConfig(
                failure_threshold=3,
                reset_timeout=0.5,
            ),
            rate_limiter_config=UnifiedRateLimitConfig(
                requests_per_second=10.0,
                burst_size=50,
            ),
        )
        return ResilienceManager(
            "test-manager",
            config,
            event_listeners=[event_listener],
        )

    @pytest.mark.asyncio
    async def test_successful_execution(self, manager):
        """Test successful execution through manager."""

        async def success_func():
            return "success"

        result = await manager.execute(success_func)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, manager, event_listener):
        """Test circuit breaker is applied."""

        async def fail_func():
            raise ValueError("Test error")

        # Cause failures to trip circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await manager.execute(fail_func)

        # Next call should be rejected by circuit breaker
        with pytest.raises(Exception) as exc_info:
            await manager.execute(fail_func)

        assert "open" in str(exc_info.value).lower() or "circuit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_rate_limiter_integration(self, manager):
        """Test rate limiter is applied."""

        async def success_func():
            return "success"

        # Make many calls quickly
        results = []
        for _ in range(60):
            try:
                result = await manager.execute(success_func)
                results.append(result)
            except Exception:
                break

        # Should have been rate limited at some point
        assert len(results) < 60

    @pytest.mark.asyncio
    async def test_fallback(self, manager):
        """Test fallback is called on failure."""

        async def fail_func():
            raise ValueError("Test error")

        def fallback():
            return "fallback_value"

        result = await manager.execute(fail_func, fallback=fallback)
        assert result == "fallback_value"

    @pytest.mark.asyncio
    async def test_protect_decorator(self, manager):
        """Test protect decorator."""

        @manager.protect
        async def protected_func():
            return "protected_result"

        result = await protected_func()
        assert result == "protected_result"

    @pytest.mark.asyncio
    async def test_reset(self, manager):
        """Test reset clears all state."""

        async def fail_func():
            raise ValueError("Test error")

        # Trip the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await manager.execute(fail_func)

        # Reset
        manager.reset()

        # Circuit should be closed again
        assert manager.get_health_state() == HealthState.HEALTHY

    @pytest.mark.asyncio
    async def test_get_stats(self, manager):
        """Test getting comprehensive stats."""

        async def success_func():
            return "success"

        await manager.execute(success_func)

        stats = manager.get_stats()
        assert stats["name"] == "test-manager"
        assert "circuit_breaker" in stats
        assert "rate_limiter" in stats


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_get_resilience_manager_creates_new(self):
        """Test get_resilience_manager creates new manager."""
        manager1 = get_resilience_manager("factory-test-1")
        manager2 = get_resilience_manager("factory-test-2")

        assert manager1 is not manager2

    def test_get_resilience_manager_returns_same(self):
        """Test get_resilience_manager returns same manager for same name."""
        manager1 = get_resilience_manager("factory-test-same")
        manager2 = get_resilience_manager("factory-test-same")

        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_resilient_decorator(self):
        """Test resilient decorator factory."""

        @resilient("decorator-test", circuit_breaker=True, rate_limiter=True)
        async def decorated_func():
            return "decorated"

        result = await decorated_func()
        assert result == "decorated"

    @pytest.mark.asyncio
    async def test_resilient_decorator_with_fallback(self):
        """Test resilient decorator with fallback."""

        def my_fallback():
            return "fallback"

        @resilient("decorator-fallback-test", fallback=my_fallback)
        async def failing_func():
            raise ValueError("Error")

        result = await failing_func()
        assert result == "fallback"


# =============================================================================
# Event Listener Tests
# =============================================================================


class TestEventListeners:
    """Tests for event listeners."""

    def test_logging_event_listener(self, caplog):
        """Test logging event listener logs events."""
        import logging

        listener = LoggingEventListener(log_level=logging.INFO)
        event = ResilienceEventData(
            event_type=ResilienceEvent.CIRCUIT_OPENED,
            component_name="test-component",
        )

        with caplog.at_level(logging.INFO):
            listener.on_event(event)

        assert "Resilience Event" in caplog.text
        assert "circuit_opened" in caplog.text

    def test_custom_event_listener(self):
        """Test custom event listener receives events."""
        listener = MockEventListener()
        event = ResilienceEventData(
            event_type=ResilienceEvent.RATE_LIMIT_EXCEEDED,
            component_name="test-component",
            metadata={"key": "value"},
        )

        listener.on_event(event)

        assert len(listener.events) == 1
        assert listener.events[0].event_type == ResilienceEvent.RATE_LIMIT_EXCEEDED

    def test_event_data_to_dict(self):
        """Test event data serialization."""
        event = ResilienceEventData(
            event_type=ResilienceEvent.HEALTH_CHECK_PASSED,
            component_name="test-component",
            metadata={"latency": 100},
        )

        data = event.to_dict()
        assert data["event_type"] == "health_check_passed"
        assert data["component_name"] == "test-component"
        assert data["metadata"]["latency"] == 100
        assert "timestamp" in data


# =============================================================================
# Concurrency Tests
# =============================================================================


class TestConcurrency:
    """Tests for concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_circuit_breaker_calls(self):
        """Test circuit breaker handles concurrent calls."""
        config = EnhancedCircuitBreakerConfig(
            failure_threshold=10,
            sliding_window_size=100,
        )
        cb = EnhancedCircuitBreaker("concurrent-test", config)

        async def quick_func():
            return "result"

        # Make many concurrent calls
        tasks = [cb.execute(quick_func) for _ in range(100)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 100
        assert all(r == "result" for r in results)
        assert cb.stats.total_calls == 100

    @pytest.mark.asyncio
    async def test_concurrent_rate_limiter_calls(self):
        """Test rate limiter handles concurrent calls."""
        config = UnifiedRateLimitConfig(
            requests_per_second=100.0,
            burst_size=50,
        )
        limiter = UnifiedRateLimiter("concurrent-rl-test", config)

        async def acquire():
            return limiter.acquire("test-key")

        # Make many concurrent acquire calls
        tasks = [acquire() for _ in range(100)]
        results = await asyncio.gather(*tasks)

        allowed = sum(1 for r in results if r.allowed)
        denied = sum(1 for r in results if not r.allowed)

        # Should have some allowed and some denied
        assert allowed > 0
        assert allowed <= 50  # Limited by burst size
        assert allowed + denied == 100


# =============================================================================
# Integration Scenario Tests
# =============================================================================


class TestIntegrationScenarios:
    """End-to-end integration scenarios."""

    @pytest.mark.asyncio
    async def test_service_degradation_and_recovery(self):
        """Test complete service degradation and recovery cycle."""
        event_listener = MockEventListener()
        config = ResilienceConfig(
            circuit_breaker_enabled=True,
            rate_limiter_enabled=True,
            circuit_breaker_config=EnhancedCircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                reset_timeout=0.3,
            ),
        )
        manager = ResilienceManager(
            "degradation-test",
            config,
            event_listeners=[event_listener],
        )

        call_count = 0
        should_fail = True

        async def flaky_service():
            nonlocal call_count
            call_count += 1
            if should_fail:
                raise ConnectionError("Service unavailable")
            return "success"

        # Phase 1: Service starts failing
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await manager.execute(flaky_service)

        # Circuit should be open
        assert manager.get_health_state() == HealthState.UNHEALTHY

        # Phase 2: Wait for half-open
        await asyncio.sleep(0.4)

        # Phase 3: Service recovers
        should_fail = False

        # Make successful calls
        for _ in range(3):
            result = await manager.execute(flaky_service)
            assert result == "success"

        # Circuit should be closed again
        assert manager.get_health_state() == HealthState.HEALTHY

        # Verify events
        opened_events = event_listener.get_events_of_type(ResilienceEvent.CIRCUIT_OPENED)
        closed_events = event_listener.get_events_of_type(ResilienceEvent.CIRCUIT_CLOSED)

        assert len(opened_events) >= 1
        assert len(closed_events) >= 1

    @pytest.mark.asyncio
    async def test_rate_limiting_under_load(self):
        """Test rate limiting behavior under sustained load."""
        config = UnifiedRateLimitConfig(
            requests_per_second=10.0,
            burst_size=10,
            strategy=RateLimitStrategy.TOKEN_BUCKET,
        )
        limiter = UnifiedRateLimiter("load-test", config)

        allowed_over_time = []

        # Simulate sustained load over 0.5 seconds
        start = time.time()
        while time.time() - start < 0.5:
            result = limiter.acquire("load-test")
            if result.allowed:
                allowed_over_time.append(time.time() - start)

        # Should have allowed roughly 15 requests
        # (10 initial burst + ~5 refilled over 0.5s at 10/sec)
        assert 10 <= len(allowed_over_time) <= 20

    @pytest.mark.asyncio
    async def test_combined_protection(self):
        """Test combined circuit breaker and rate limiter protection."""
        manager = ResilienceManager(
            "combined-test",
            ResilienceConfig(
                circuit_breaker_enabled=True,
                rate_limiter_enabled=True,
                circuit_breaker_config=EnhancedCircuitBreakerConfig(
                    failure_threshold=5,
                ),
                rate_limiter_config=UnifiedRateLimitConfig(
                    burst_size=100,
                    requests_per_second=100.0,
                ),
            ),
            fallback=lambda: "fallback",
        )

        success_count = 0
        fallback_count = 0

        async def service_call():
            return "success"

        # Make many calls
        for _ in range(150):
            try:
                result = await manager.execute(service_call)
                if result == "success":
                    success_count += 1
                elif result == "fallback":
                    fallback_count += 1
            except Exception:
                pass

        # Should have processed most calls successfully
        assert success_count > 50

        stats = manager.get_stats()
        assert stats["circuit_breaker"]["stats"]["successful_calls"] > 0
