"""
Distributed Rate Limiting for NebulaCompute.

Provides rate limiting across multiple nodes using Redis.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class DistributedRateLimitResult:
    """Result of distributed rate limit check."""
    allowed: bool
    limit: int
    remaining: int
    reset_at: float
    retry_after: Optional[float] = None
    node_id: Optional[str] = None

    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(self.reset_at)),
        }

        if self.retry_after:
            headers["Retry-After"] = str(int(self.retry_after))

        return headers


class DistributedRateLimiter:
    """
    Base class for distributed rate limiters.

    Provides interface for rate limiting across multiple nodes.
    """

    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        cost: int = 1,
    ) -> DistributedRateLimitResult:
        """
        Check if request is allowed.

        Args:
            key: Rate limit key (e.g., client ID)
            limit: Maximum requests in window
            window_seconds: Window duration
            cost: Cost of this request

        Returns:
            Rate limit result
        """
        raise NotImplementedError

    async def reset(self, key: str) -> bool:
        """Reset rate limit for a key."""
        raise NotImplementedError

    async def get_usage(self, key: str) -> Dict[str, Any]:
        """Get current usage for a key."""
        raise NotImplementedError


class RedisRateLimiter(DistributedRateLimiter):
    """
    Redis-based distributed rate limiter.

    Uses Redis for distributed state, supporting:
    - Sliding window algorithm
    - Atomic operations
    - High throughput
    """

    # Lua script for atomic sliding window rate limiting
    SLIDING_WINDOW_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local cost = tonumber(ARGV[4])

    -- Remove expired entries
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

    -- Get current count
    local current = redis.call('ZCARD', key)

    if current + cost <= limit then
        -- Add new entry
        redis.call('ZADD', key, now, now .. ':' .. math.random())
        redis.call('EXPIRE', key, window)
        return {1, limit - current - cost, now + window}
    else
        -- Get oldest entry for retry-after
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local retry_after = 0
        if #oldest > 0 then
            retry_after = oldest[2] + window - now
        end
        return {0, 0, now + window, retry_after}
    end
    """

    # Lua script for token bucket algorithm
    TOKEN_BUCKET_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local capacity = tonumber(ARGV[2])
    local refill_rate = tonumber(ARGV[3])
    local cost = tonumber(ARGV[4])

    -- Get current state
    local state = redis.call('HMGET', key, 'tokens', 'last_update')
    local tokens = tonumber(state[1]) or capacity
    local last_update = tonumber(state[2]) or now

    -- Calculate token refill
    local elapsed = now - last_update
    tokens = math.min(capacity, tokens + elapsed * refill_rate)

    if tokens >= cost then
        tokens = tokens - cost
        redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
        redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) + 1)
        return {1, math.floor(tokens), 0}
    else
        local wait_time = (cost - tokens) / refill_rate
        return {0, 0, wait_time}
    end
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        prefix: str = "ratelimit:",
        algorithm: str = "sliding_window",
        node_id: Optional[str] = None,
    ):
        """
        Initialize Redis rate limiter.

        Args:
            redis_url: Redis connection URL
            prefix: Key prefix
            algorithm: Algorithm to use (sliding_window, token_bucket)
            node_id: Identifier for this node
        """
        self.redis_url = redis_url
        self.prefix = prefix
        self.algorithm = algorithm
        self.node_id = node_id or "node-1"

        self._redis = None
        self._connected = False
        self._scripts: Dict[str, Any] = {}

    async def connect(self) -> None:
        """Connect to Redis and register scripts."""
        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(self.redis_url)
            await self._redis.ping()

            # Register Lua scripts
            self._scripts["sliding_window"] = self._redis.register_script(
                self.SLIDING_WINDOW_SCRIPT
            )
            self._scripts["token_bucket"] = self._redis.register_script(
                self.TOKEN_BUCKET_SCRIPT
            )

            self._connected = True
            logger.info("RedisRateLimiter connected to %s", self.redis_url)

        except ImportError:
            logger.error("redis package not installed")
            raise
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            raise

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._connected = False

    def _make_key(self, key: str) -> str:
        """Generate prefixed key."""
        return f"{self.prefix}{key}"

    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        cost: int = 1,
    ) -> DistributedRateLimitResult:
        """
        Check if request is allowed using sliding window.

        Args:
            key: Rate limit key
            limit: Maximum requests in window
            window_seconds: Window duration
            cost: Cost of this request

        Returns:
            Rate limit result
        """
        if not self._connected:
            # Fail open if not connected
            logger.warning("Redis not connected, allowing request")
            return DistributedRateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit,
                reset_at=time.time() + window_seconds,
                node_id=self.node_id,
            )

        try:
            now = time.time()
            redis_key = self._make_key(key)

            if self.algorithm == "sliding_window":
                result = await self._scripts["sliding_window"](
                    keys=[redis_key],
                    args=[now, window_seconds, limit, cost],
                )

                allowed = bool(result[0])
                remaining = int(result[1])
                reset_at = float(result[2])
                retry_after = float(result[3]) if len(result) > 3 else None

            else:  # token_bucket
                refill_rate = limit / window_seconds
                result = await self._scripts["token_bucket"](
                    keys=[redis_key],
                    args=[now, limit, refill_rate, cost],
                )

                allowed = bool(result[0])
                remaining = int(result[1])
                retry_after = float(result[2]) if result[2] > 0 else None
                reset_at = now + (1.0 / refill_rate) if retry_after else now

            return DistributedRateLimitResult(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
                node_id=self.node_id,
            )

        except Exception as e:
            logger.error("Rate limit check failed: %s", e)
            # Fail open on error
            return DistributedRateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit,
                reset_at=time.time() + window_seconds,
                node_id=self.node_id,
            )

    async def reset(self, key: str) -> bool:
        """Reset rate limit for a key."""
        if not self._connected:
            return False

        try:
            redis_key = self._make_key(key)
            await self._redis.delete(redis_key)
            return True
        except Exception as e:
            logger.error("Failed to reset rate limit: %s", e)
            return False

    async def get_usage(self, key: str) -> Dict[str, Any]:
        """Get current usage for a key."""
        if not self._connected:
            return {}

        try:
            redis_key = self._make_key(key)

            if self.algorithm == "sliding_window":
                time.time()
                count = await self._redis.zcard(redis_key)
                ttl = await self._redis.ttl(redis_key)

                return {
                    "key": key,
                    "current_count": count,
                    "ttl_seconds": ttl,
                    "algorithm": "sliding_window",
                }

            else:  # token_bucket
                state = await self._redis.hgetall(redis_key)

                return {
                    "key": key,
                    "tokens": float(state.get(b"tokens", 0)),
                    "last_update": float(state.get(b"last_update", 0)),
                    "algorithm": "token_bucket",
                }

        except Exception as e:
            logger.error("Failed to get usage: %s", e)
            return {}

    async def get_all_keys(self, pattern: str = "*") -> List[str]:
        """Get all rate limit keys matching pattern."""
        if not self._connected:
            return []

        try:
            full_pattern = f"{self.prefix}{pattern}"
            keys = []

            async for key in self._redis.scan_iter(match=full_pattern):
                keys.append(key.decode().replace(self.prefix, ""))

            return keys

        except Exception as e:
            logger.error("Failed to get keys: %s", e)
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        if not self._connected:
            return {"connected": False}

        try:
            info = await self._redis.info("stats")

            return {
                "connected": True,
                "node_id": self.node_id,
                "algorithm": self.algorithm,
                "redis_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "total_keys": await self._redis.dbsize(),
            }

        except Exception as e:
            logger.error("Failed to get stats: %s", e)
            return {"connected": False, "error": str(e)}


class ClusterRateLimiter(DistributedRateLimiter):
    """
    Rate limiter for Redis Cluster.

    Handles rate limiting across a Redis cluster with
    proper key distribution.
    """

    def __init__(
        self,
        startup_nodes: List[Dict[str, Any]],
        prefix: str = "ratelimit:",
        algorithm: str = "sliding_window",
    ):
        """
        Initialize cluster rate limiter.

        Args:
            startup_nodes: List of cluster node configs
            prefix: Key prefix (should include hash tag for slot)
            algorithm: Algorithm to use
        """
        self.startup_nodes = startup_nodes
        self.prefix = prefix
        self.algorithm = algorithm
        self._cluster = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to Redis Cluster."""
        try:
            from redis.asyncio.cluster import RedisCluster

            self._cluster = RedisCluster(
                startup_nodes=self.startup_nodes,
                decode_responses=False,
            )

            await self._cluster.ping()
            self._connected = True
            logger.info("Connected to Redis Cluster")

        except ImportError:
            logger.error("redis package not installed")
            raise
        except Exception as e:
            logger.error("Failed to connect to Redis Cluster: %s", e)
            raise

    async def close(self) -> None:
        """Close cluster connection."""
        if self._cluster:
            await self._cluster.close()
            self._connected = False

    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        cost: int = 1,
    ) -> DistributedRateLimitResult:
        """Check rate limit on cluster."""
        if not self._connected:
            return DistributedRateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit,
                reset_at=time.time() + window_seconds,
            )

        # Use hash tag to ensure key goes to same slot
        redis_key = f"{self.prefix}{{{key}}}"

        try:
            now = time.time()
            window_start = now - window_seconds

            # Use pipeline for atomicity
            async with self._cluster.pipeline() as pipe:
                pipe.zremrangebyscore(redis_key, 0, window_start)
                pipe.zcard(redis_key)
                pipe.zadd(redis_key, {f"{now}": now})
                pipe.expire(redis_key, window_seconds)

                results = await pipe.execute()

            current = results[1]
            allowed = current < limit
            remaining = max(0, limit - current - cost)

            return DistributedRateLimitResult(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_at=now + window_seconds,
                retry_after=window_seconds if not allowed else None,
            )

        except Exception as e:
            logger.error("Cluster rate limit check failed: %s", e)
            return DistributedRateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit,
                reset_at=time.time() + window_seconds,
            )

    async def reset(self, key: str) -> bool:
        """Reset rate limit for a key."""
        if not self._connected:
            return False

        try:
            redis_key = f"{self.prefix}{{{key}}}"
            await self._cluster.delete(redis_key)
            return True
        except Exception as e:
            logger.error("Failed to reset: %s", e)
            return False

    async def get_usage(self, key: str) -> Dict[str, Any]:
        """Get usage for a key."""
        if not self._connected:
            return {}

        try:
            redis_key = f"{self.prefix}{{{key}}}"
            count = await self._cluster.zcard(redis_key)
            ttl = await self._cluster.ttl(redis_key)

            return {
                "key": key,
                "current_count": count,
                "ttl_seconds": ttl,
            }
        except Exception as e:
            logger.error("Failed to get usage: %s", e)
            return {}
