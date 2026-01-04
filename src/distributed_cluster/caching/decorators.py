"""
Cache decorators for easy caching of function results.
"""

import asyncio
import functools
import hashlib
import inspect
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .cache import Cache, CacheError, cache_manager

logger = logging.getLogger(__name__)


def _make_cache_key(
    prefix: str,
    func: Callable,
    args: tuple,
    kwargs: dict,
    key_builder: Optional[Callable] = None,
    include_args: bool = True,
    include_kwargs: bool = True,
    arg_names: Optional[List[str]] = None
) -> str:
    """Generate a cache key from function and arguments."""
    if key_builder:
        return key_builder(*args, **kwargs)

    parts = [prefix, func.__module__, func.__qualname__]

    if include_args:
        if arg_names:
            # Get argument names from function signature
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())

            for i, arg in enumerate(args):
                if i < len(params) and params[i] in arg_names:
                    parts.append(f"{params[i]}={_serialize_arg(arg)}")
        else:
            for arg in args:
                parts.append(_serialize_arg(arg))

    if include_kwargs:
        if arg_names:
            for key, value in sorted(kwargs.items()):
                if key in arg_names:
                    parts.append(f"{key}={_serialize_arg(value)}")
        else:
            for key, value in sorted(kwargs.items()):
                parts.append(f"{key}={_serialize_arg(value)}")

    key_string = ":".join(parts)

    # Hash long keys
    if len(key_string) > 200:
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        return f"{prefix}:{func.__qualname__}:{key_hash}"

    return key_string


def _serialize_arg(arg: Any) -> str:
    """Serialize an argument for cache key."""
    if isinstance(arg, (str, int, float, bool)):
        return str(arg)
    elif isinstance(arg, (list, tuple)):
        return f"[{','.join(_serialize_arg(a) for a in arg)}]"
    elif isinstance(arg, dict):
        items = [f"{k}:{_serialize_arg(v)}" for k, v in sorted(arg.items())]
        return f"{{{','.join(items)}}}"
    elif hasattr(arg, '__dict__'):
        return f"{arg.__class__.__name__}:{id(arg)}"
    else:
        return str(hash(arg))


def cached(
    cache: Optional[Cache] = None,
    cache_name: Optional[str] = None,
    ttl: Optional[int] = None,
    key_prefix: Optional[str] = None,
    key_builder: Optional[Callable[..., str]] = None,
    condition: Optional[Callable[..., bool]] = None,
    unless: Optional[Callable[[Any], bool]] = None,
    lock: bool = False,
    namespace: Optional[str] = None
):
    """
    Decorator for caching function results.

    Args:
        cache: Cache instance to use
        cache_name: Name of cache in cache_manager
        ttl: Time-to-live in seconds
        key_prefix: Prefix for cache keys
        key_builder: Custom function to build cache key
        condition: Only cache if condition returns True
        unless: Don't cache if unless returns True for the result
        lock: Use a lock to prevent thundering herd
        namespace: Cache namespace
    """
    def decorator(func: Callable) -> Callable:
        _cache = cache or (cache_manager.get_cache(cache_name) if cache_name else None)
        _prefix = key_prefix or f"cached:{func.__module__}:{func.__qualname__}"
        _lock = threading.Lock() if lock else None
        _in_progress: Dict[str, threading.Event] = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            nonlocal _cache

            if _cache is None:
                try:
                    _cache = cache_manager.get_cache()
                except CacheError:
                    return func(*args, **kwargs)

            # Check condition
            if condition and not condition(*args, **kwargs):
                return func(*args, **kwargs)

            # Generate cache key
            cache_key = _make_cache_key(_prefix, func, args, kwargs, key_builder)

            # Try to get from cache
            cached_value = _cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Handle thundering herd with lock
            if _lock:
                with _lock:
                    # Check if another thread is computing
                    if cache_key in _in_progress:
                        event = _in_progress[cache_key]
                    else:
                        event = threading.Event()
                        _in_progress[cache_key] = event

                if event.is_set():
                    # Another thread completed, try cache again
                    cached_value = _cache.get(cache_key)
                    if cached_value is not None:
                        return cached_value
                elif cache_key in _in_progress:
                    # Wait for other thread
                    event.wait(timeout=30)
                    cached_value = _cache.get(cache_key)
                    if cached_value is not None:
                        return cached_value

            try:
                # Compute value
                result = func(*args, **kwargs)

                # Check unless condition
                if unless and unless(result):
                    return result

                # Cache the result
                _cache.set(cache_key, result, ttl)

                return result
            finally:
                if _lock and cache_key in _in_progress:
                    _in_progress[cache_key].set()
                    with _lock:
                        _in_progress.pop(cache_key, None)

        # Async version
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            nonlocal _cache

            if _cache is None:
                try:
                    _cache = cache_manager.get_cache()
                except CacheError:
                    return await func(*args, **kwargs)

            if condition and not condition(*args, **kwargs):
                return await func(*args, **kwargs)

            cache_key = _make_cache_key(_prefix, func, args, kwargs, key_builder)

            cached_value = _cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            result = await func(*args, **kwargs)

            if unless and unless(result):
                return result

            _cache.set(cache_key, result, ttl)
            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


def cache_aside(
    cache: Optional[Cache] = None,
    cache_name: Optional[str] = None,
    ttl: Optional[int] = None,
    key_prefix: Optional[str] = None,
    key_builder: Optional[Callable[..., str]] = None
):
    """
    Cache-aside pattern decorator.

    The function is only called on cache miss.
    """
    return cached(
        cache=cache,
        cache_name=cache_name,
        ttl=ttl,
        key_prefix=key_prefix,
        key_builder=key_builder,
    )


def cache_invalidate(
    cache: Optional[Cache] = None,
    cache_name: Optional[str] = None,
    key_prefix: Optional[str] = None,
    key_builder: Optional[Callable[..., str]] = None,
    keys: Optional[List[str]] = None,
    patterns: Optional[List[str]] = None,
    all_keys: bool = False
):
    """
    Decorator that invalidates cache entries when the function is called.

    Args:
        cache: Cache instance to use
        cache_name: Name of cache in cache_manager
        key_prefix: Prefix for cache keys
        key_builder: Custom function to build cache key
        keys: Specific keys to invalidate
        patterns: Patterns to match keys for invalidation
        all_keys: Invalidate all keys with the prefix
    """
    def decorator(func: Callable) -> Callable:
        _cache = cache or (cache_manager.get_cache(cache_name) if cache_name else None)
        _prefix = key_prefix or f"cached:{func.__module__}:{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            nonlocal _cache

            if _cache is None:
                try:
                    _cache = cache_manager.get_cache()
                except CacheError:
                    return func(*args, **kwargs)

            # Call the function first
            result = func(*args, **kwargs)

            # Then invalidate
            if keys:
                for key in keys:
                    _cache.delete(key)

            if key_builder:
                cache_key = key_builder(*args, **kwargs)
                _cache.delete(cache_key)

            if patterns:
                for pattern in patterns:
                    matching_keys = _cache.keys(pattern)
                    _cache.delete_many(matching_keys)

            if all_keys:
                matching_keys = _cache.keys(f"{_prefix}:*")
                _cache.delete_many(matching_keys)

            return result

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            nonlocal _cache

            if _cache is None:
                try:
                    _cache = cache_manager.get_cache()
                except CacheError:
                    return await func(*args, **kwargs)

            result = await func(*args, **kwargs)

            if keys:
                for key in keys:
                    _cache.delete(key)

            if key_builder:
                cache_key = key_builder(*args, **kwargs)
                _cache.delete(cache_key)

            if patterns:
                for pattern in patterns:
                    matching_keys = _cache.keys(pattern)
                    _cache.delete_many(matching_keys)

            if all_keys:
                matching_keys = _cache.keys(f"{_prefix}:*")
                _cache.delete_many(matching_keys)

            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


def memoize(
    maxsize: int = 128,
    ttl: Optional[int] = None,
    typed: bool = False
):
    """
    Simple in-memory memoization decorator.

    Similar to functools.lru_cache but with optional TTL support.

    Args:
        maxsize: Maximum number of cached results
        ttl: Time-to-live in seconds for cached results
        typed: If True, arguments of different types are cached separately
    """
    def decorator(func: Callable) -> Callable:
        cache: Dict[str, tuple] = {}  # key -> (value, timestamp)
        order: List[str] = []  # For LRU eviction
        lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Build cache key
            if typed:
                key_parts = [
                    f"{type(arg).__name__}:{_serialize_arg(arg)}"
                    for arg in args
                ]
                key_parts.extend(
                    f"{k}:{type(v).__name__}:{_serialize_arg(v)}"
                    for k, v in sorted(kwargs.items())
                )
            else:
                key_parts = [_serialize_arg(arg) for arg in args]
                key_parts.extend(
                    f"{k}:{_serialize_arg(v)}"
                    for k, v in sorted(kwargs.items())
                )

            cache_key = ":".join(key_parts)

            with lock:
                if cache_key in cache:
                    value, timestamp = cache[cache_key]

                    # Check TTL
                    if ttl and time.time() - timestamp > ttl:
                        del cache[cache_key]
                        order.remove(cache_key)
                    else:
                        # Move to end for LRU
                        order.remove(cache_key)
                        order.append(cache_key)
                        return value

            # Compute value
            result = func(*args, **kwargs)

            with lock:
                # Evict if necessary
                while len(cache) >= maxsize:
                    oldest_key = order.pop(0)
                    del cache[oldest_key]

                cache[cache_key] = (result, time.time())
                order.append(cache_key)

            return result

        def cache_clear():
            """Clear the cache."""
            with lock:
                cache.clear()
                order.clear()

        def cache_info() -> Dict[str, Any]:
            """Get cache info."""
            with lock:
                return {
                    "size": len(cache),
                    "maxsize": maxsize,
                    "ttl": ttl,
                }

        wrapper.cache_clear = cache_clear
        wrapper.cache_info = cache_info

        return wrapper

    return decorator


class CacheableClass:
    """
    Mixin class that provides caching capabilities to class methods.
    """

    _cache: Optional[Cache] = None
    _cache_ttl: int = 3600

    @classmethod
    def set_cache(cls, cache: Cache, ttl: int = 3600):
        """Set the cache for this class."""
        cls._cache = cache
        cls._cache_ttl = ttl

    def _get_cache_key(self, method_name: str, *args, **kwargs) -> str:
        """Generate a cache key for a method call."""
        parts = [
            self.__class__.__name__,
            method_name,
            str(id(self)),
        ]
        for arg in args:
            parts.append(_serialize_arg(arg))
        for key, value in sorted(kwargs.items()):
            parts.append(f"{key}={_serialize_arg(value)}")

        return ":".join(parts)

    def cache_get(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Get a cached method result."""
        if not self._cache:
            return None

        key = self._get_cache_key(method_name, *args, **kwargs)
        return self._cache.get(key)

    def cache_set(
        self,
        method_name: str,
        value: Any,
        *args,
        ttl: Optional[int] = None,
        **kwargs
    ):
        """Cache a method result."""
        if not self._cache:
            return

        key = self._get_cache_key(method_name, *args, **kwargs)
        self._cache.set(key, value, ttl or self._cache_ttl)

    def cache_delete(self, method_name: str, *args, **kwargs):
        """Delete a cached method result."""
        if not self._cache:
            return

        key = self._get_cache_key(method_name, *args, **kwargs)
        self._cache.delete(key)

    def cache_clear_all(self):
        """Clear all cached results for this instance."""
        if not self._cache:
            return

        pattern = f"{self.__class__.__name__}:*:{id(self)}:*"
        keys = self._cache.keys(pattern)
        self._cache.delete_many(keys)


def cacheable_method(ttl: Optional[int] = None):
    """
    Decorator for methods in CacheableClass subclasses.
    """
    def decorator(method: Callable) -> Callable:
        @functools.wraps(method)
        def wrapper(self: CacheableClass, *args, **kwargs) -> Any:
            if not isinstance(self, CacheableClass):
                return method(self, *args, **kwargs)

            # Try cache
            cached_value = self.cache_get(method.__name__, *args, **kwargs)
            if cached_value is not None:
                return cached_value

            # Compute
            result = method(self, *args, **kwargs)

            # Cache
            self.cache_set(method.__name__, result, *args, ttl=ttl, **kwargs)

            return result

        return wrapper

    return decorator
