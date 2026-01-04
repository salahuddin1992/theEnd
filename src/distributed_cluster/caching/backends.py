"""
Cache backend implementations for various storage systems.
"""

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Dict, List, Optional, Set, Tuple

from .cache import CacheConnectionError

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    def get(self, key: str) -> Optional[bytes]:
        """Get raw bytes from backend."""
        pass

    @abstractmethod
    def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        """Set raw bytes in backend."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key from backend."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in backend."""
        pass

    @abstractmethod
    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern."""
        pass

    @abstractmethod
    def clear(self) -> int:
        """Clear all entries."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close backend connection."""
        pass

    def get_many(self, keys: List[str]) -> Dict[str, Optional[bytes]]:
        """Get multiple keys. Default implementation."""
        return {key: self.get(key) for key in keys}

    def set_many(
        self,
        mapping: Dict[str, bytes],
        ttl: Optional[int] = None
    ) -> Dict[str, bool]:
        """Set multiple keys. Default implementation."""
        return {key: self.set(key, value, ttl) for key, value in mapping.items()}

    def delete_many(self, keys: List[str]) -> int:
        """Delete multiple keys. Default implementation."""
        return sum(1 for key in keys if self.delete(key))


class MemoryBackend(CacheBackend):
    """In-memory cache backend using OrderedDict for LRU."""

    def __init__(self, max_size: int = 10000, default_ttl: int = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._data: OrderedDict[str, Tuple[bytes, Optional[float]]] = OrderedDict()
        self._lock = threading.RLock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = True
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """Start background cleanup thread."""
        def cleanup_loop():
            while self._running:
                time.sleep(60)
                self._cleanup_expired()

        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _cleanup_expired(self):
        """Remove expired entries."""
        now = time.time()
        with self._lock:
            expired = [
                key for key, (_, expires_at) in self._data.items()
                if expires_at and expires_at < now
            ]
            for key in expired:
                del self._data[key]

    def _evict_if_needed(self):
        """Evict oldest entries if over capacity."""
        while len(self._data) >= self.max_size:
            self._data.popitem(last=False)

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            if key not in self._data:
                return None

            value, expires_at = self._data[key]

            # Check expiration
            if expires_at and expires_at < time.time():
                del self._data[key]
                return None

            # Move to end for LRU
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        with self._lock:
            self._evict_if_needed()

            ttl = ttl if ttl is not None else self.default_ttl
            expires_at = time.time() + ttl if ttl > 0 else None

            self._data[key] = (value, expires_at)
            self._data.move_to_end(key)
            return True

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def exists(self, key: str) -> bool:
        with self._lock:
            if key not in self._data:
                return False

            _, expires_at = self._data[key]
            if expires_at and expires_at < time.time():
                del self._data[key]
                return False

            return True

    def keys(self, pattern: str = "*") -> List[str]:
        import fnmatch
        with self._lock:
            now = time.time()
            result = []
            for key, (_, expires_at) in self._data.items():
                if expires_at and expires_at < now:
                    continue
                if fnmatch.fnmatch(key, pattern):
                    result.append(key)
            return result

    def clear(self) -> int:
        with self._lock:
            count = len(self._data)
            self._data.clear()
            return count

    def close(self) -> None:
        self._running = False

    def get_many(self, keys: List[str]) -> Dict[str, Optional[bytes]]:
        with self._lock:
            now = time.time()
            results = {}
            for key in keys:
                if key in self._data:
                    value, expires_at = self._data[key]
                    if not expires_at or expires_at >= now:
                        results[key] = value
                        self._data.move_to_end(key)
                    else:
                        results[key] = None
                else:
                    results[key] = None
            return results

    @property
    def size(self) -> int:
        return len(self._data)


class RedisBackend(CacheBackend):
    """Redis cache backend."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: float = 1.0,
        connection_pool_size: int = 10,
        ssl: bool = False,
        ssl_cert_reqs: Optional[str] = None,
        cluster_mode: bool = False
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.socket_timeout = socket_timeout
        self.pool_size = connection_pool_size
        self.ssl = ssl
        self.cluster_mode = cluster_mode
        self._redis = None
        self._connect()

    def _connect(self):
        """Establish Redis connection."""
        try:
            import redis

            if self.cluster_mode:
                from redis.cluster import RedisCluster
                self._redis = RedisCluster(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                    socket_timeout=self.socket_timeout,
                )
            else:
                pool = redis.ConnectionPool(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    socket_timeout=self.socket_timeout,
                    max_connections=self.pool_size,
                    decode_responses=False,
                )
                self._redis = redis.Redis(connection_pool=pool)

            # Test connection
            self._redis.ping()
            logger.info(f"Connected to Redis: {self.host}:{self.port}")

        except ImportError:
            raise CacheConnectionError("redis package not installed. Run: pip install redis")
        except Exception as e:
            raise CacheConnectionError(f"Failed to connect to Redis: {e}")

    def get(self, key: str) -> Optional[bytes]:
        try:
            return self._redis.get(key)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        try:
            if ttl and ttl > 0:
                return self._redis.setex(key, ttl, value)
            else:
                return self._redis.set(key, value)
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        try:
            return self._redis.delete(key) > 0
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False

    def exists(self, key: str) -> bool:
        try:
            return self._redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False

    def keys(self, pattern: str = "*") -> List[str]:
        try:
            keys = self._redis.keys(pattern)
            return [k.decode("utf-8") if isinstance(k, bytes) else k for k in keys]
        except Exception as e:
            logger.error(f"Redis keys error: {e}")
            return []

    def clear(self) -> int:
        try:
            keys = self._redis.keys("*")
            if keys:
                return self._redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis clear error: {e}")
            return 0

    def close(self) -> None:
        if self._redis:
            self._redis.close()

    def get_many(self, keys: List[str]) -> Dict[str, Optional[bytes]]:
        try:
            values = self._redis.mget(keys)
            return dict(zip(keys, values))
        except Exception as e:
            logger.error(f"Redis mget error: {e}")
            return {key: None for key in keys}

    def set_many(
        self,
        mapping: Dict[str, bytes],
        ttl: Optional[int] = None
    ) -> Dict[str, bool]:
        try:
            pipe = self._redis.pipeline()
            for key, value in mapping.items():
                if ttl and ttl > 0:
                    pipe.setex(key, ttl, value)
                else:
                    pipe.set(key, value)
            results = pipe.execute()
            return dict(zip(mapping.keys(), [bool(r) for r in results]))
        except Exception as e:
            logger.error(f"Redis mset error: {e}")
            return {key: False for key in mapping}

    def delete_many(self, keys: List[str]) -> int:
        try:
            if keys:
                return self._redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis delete_many error: {e}")
            return 0

    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration on a key."""
        try:
            return self._redis.expire(key, ttl)
        except Exception as e:
            logger.error(f"Redis expire error: {e}")
            return False

    def ttl(self, key: str) -> int:
        """Get remaining TTL for a key."""
        try:
            return self._redis.ttl(key)
        except Exception as e:
            logger.error(f"Redis ttl error: {e}")
            return -1

    def incr(self, key: str, delta: int = 1) -> int:
        """Increment a counter."""
        try:
            return self._redis.incrby(key, delta)
        except Exception as e:
            logger.error(f"Redis incr error: {e}")
            return 0

    def decr(self, key: str, delta: int = 1) -> int:
        """Decrement a counter."""
        try:
            return self._redis.decrby(key, delta)
        except Exception as e:
            logger.error(f"Redis decr error: {e}")
            return 0

    def lpush(self, key: str, *values) -> int:
        """Push values to a list."""
        try:
            return self._redis.lpush(key, *values)
        except Exception as e:
            logger.error(f"Redis lpush error: {e}")
            return 0

    def rpop(self, key: str) -> Optional[bytes]:
        """Pop from right of a list."""
        try:
            return self._redis.rpop(key)
        except Exception as e:
            logger.error(f"Redis rpop error: {e}")
            return None

    def sadd(self, key: str, *members) -> int:
        """Add members to a set."""
        try:
            return self._redis.sadd(key, *members)
        except Exception as e:
            logger.error(f"Redis sadd error: {e}")
            return 0

    def smembers(self, key: str) -> Set[bytes]:
        """Get all members of a set."""
        try:
            return self._redis.smembers(key)
        except Exception as e:
            logger.error(f"Redis smembers error: {e}")
            return set()

    def hset(self, key: str, mapping: Dict[str, bytes]) -> int:
        """Set hash fields."""
        try:
            return self._redis.hset(key, mapping=mapping)
        except Exception as e:
            logger.error(f"Redis hset error: {e}")
            return 0

    def hget(self, key: str, field: str) -> Optional[bytes]:
        """Get a hash field."""
        try:
            return self._redis.hget(key, field)
        except Exception as e:
            logger.error(f"Redis hget error: {e}")
            return None

    def hgetall(self, key: str) -> Dict[bytes, bytes]:
        """Get all hash fields."""
        try:
            return self._redis.hgetall(key)
        except Exception as e:
            logger.error(f"Redis hgetall error: {e}")
            return {}


class MemcachedBackend(CacheBackend):
    """Memcached cache backend."""

    def __init__(
        self,
        servers: List[str] = None,
        connect_timeout: float = 1.0,
        timeout: float = 1.0,
        max_pool_size: int = 10
    ):
        self.servers = servers or ["localhost:11211"]
        self.connect_timeout = connect_timeout
        self.timeout = timeout
        self.max_pool_size = max_pool_size
        self._client = None
        self._connect()

    def _connect(self):
        """Establish Memcached connection."""
        try:
            from pymemcache import serde
            from pymemcache.client.hash import HashClient

            self._client = HashClient(
                self.servers,
                connect_timeout=self.connect_timeout,
                timeout=self.timeout,
                max_pool_size=self.max_pool_size,
                serde=serde.pickle_serde,
            )

            logger.info(f"Connected to Memcached: {self.servers}")

        except ImportError:
            raise CacheConnectionError(
                "pymemcache package not installed. Run: pip install pymemcache"
            )
        except Exception as e:
            raise CacheConnectionError(f"Failed to connect to Memcached: {e}")

    def get(self, key: str) -> Optional[bytes]:
        try:
            value = self._client.get(key)
            return value if value is not None else None
        except Exception as e:
            logger.error(f"Memcached get error: {e}")
            return None

    def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        try:
            expire = ttl if ttl and ttl > 0 else 0
            return self._client.set(key, value, expire=expire)
        except Exception as e:
            logger.error(f"Memcached set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        try:
            return self._client.delete(key)
        except Exception as e:
            logger.error(f"Memcached delete error: {e}")
            return False

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def keys(self, pattern: str = "*") -> List[str]:
        # Memcached doesn't support key listing
        logger.warning("Memcached doesn't support key listing")
        return []

    def clear(self) -> int:
        try:
            self._client.flush_all()
            return 0  # Memcached doesn't return count
        except Exception as e:
            logger.error(f"Memcached flush error: {e}")
            return 0

    def close(self) -> None:
        if self._client:
            self._client.close()

    def get_many(self, keys: List[str]) -> Dict[str, Optional[bytes]]:
        try:
            result = self._client.get_many(keys)
            return {key: result.get(key) for key in keys}
        except Exception as e:
            logger.error(f"Memcached get_many error: {e}")
            return {key: None for key in keys}

    def set_many(
        self,
        mapping: Dict[str, bytes],
        ttl: Optional[int] = None
    ) -> Dict[str, bool]:
        try:
            expire = ttl if ttl and ttl > 0 else 0
            failed = self._client.set_many(mapping, expire=expire)
            return {key: key not in failed for key in mapping}
        except Exception as e:
            logger.error(f"Memcached set_many error: {e}")
            return {key: False for key in mapping}

    def incr(self, key: str, delta: int = 1) -> int:
        """Increment a counter."""
        try:
            return self._client.incr(key, delta)
        except Exception as e:
            logger.error(f"Memcached incr error: {e}")
            return 0

    def decr(self, key: str, delta: int = 1) -> int:
        """Decrement a counter."""
        try:
            return self._client.decr(key, delta)
        except Exception as e:
            logger.error(f"Memcached decr error: {e}")
            return 0


class BackendFactory:
    """Factory for creating cache backends."""

    _backends: Dict[str, type] = {
        "memory": MemoryBackend,
        "redis": RedisBackend,
        "memcached": MemcachedBackend,
    }

    @classmethod
    def create(cls, backend_type: str, **kwargs) -> CacheBackend:
        """Create a backend instance."""
        backend_class = cls._backends.get(backend_type.lower())
        if not backend_class:
            raise ValueError(f"Unknown backend type: {backend_type}")
        return backend_class(**kwargs)

    @classmethod
    def register(cls, name: str, backend_class: type):
        """Register a new backend type."""
        cls._backends[name.lower()] = backend_class
