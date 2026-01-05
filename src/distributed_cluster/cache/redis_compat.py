"""
Redis Compatible Client - عميل متوافق مع Redis
==============================================

Redis Compatible API
--------------------

This module provides a Redis-compatible API for the distributed cache.

يوفر هذا الملف واجهة متوافقة مع Redis للتخزين المؤقت الموزع.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

from distributed_cluster.cache.store import CacheStore

logger = logging.getLogger(__name__)


class RedisCommand(str, Enum):
    """أوامر Redis"""

    # Strings
    GET = "GET"
    SET = "SET"
    MGET = "MGET"
    MSET = "MSET"
    INCR = "INCR"
    DECR = "DECR"
    APPEND = "APPEND"
    STRLEN = "STRLEN"
    GETSET = "GETSET"
    SETEX = "SETEX"
    SETNX = "SETNX"

    # Keys
    DEL = "DEL"
    EXISTS = "EXISTS"
    EXPIRE = "EXPIRE"
    TTL = "TTL"
    KEYS = "KEYS"
    SCAN = "SCAN"
    TYPE = "TYPE"
    RENAME = "RENAME"

    # Lists
    LPUSH = "LPUSH"
    RPUSH = "RPUSH"
    LPOP = "LPOP"
    RPOP = "RPOP"
    LLEN = "LLEN"
    LRANGE = "LRANGE"

    # Sets
    SADD = "SADD"
    SREM = "SREM"
    SMEMBERS = "SMEMBERS"
    SISMEMBER = "SISMEMBER"
    SCARD = "SCARD"

    # Hashes
    HGET = "HGET"
    HSET = "HSET"
    HMGET = "HMGET"
    HMSET = "HMSET"
    HDEL = "HDEL"
    HGETALL = "HGETALL"
    HKEYS = "HKEYS"
    HVALS = "HVALS"
    HLEN = "HLEN"

    # Server
    PING = "PING"
    INFO = "INFO"
    FLUSHDB = "FLUSHDB"
    DBSIZE = "DBSIZE"


class RedisCompatClient:
    """
    عميل متوافق مع Redis
    Redis Compatible Client

    يوفر واجهة مشابهة لـ Redis للتخزين المؤقت المحلي.
    Provides Redis-like interface for local cache.
    """

    def __init__(self, store: Optional[CacheStore] = None):
        """
        تهيئة العميل

        Args:
            store: مخزن التخزين المؤقت
        """
        self.store = store or CacheStore()
        self._lists: dict[str, list] = {}
        self._sets: dict[str, set] = {}
        self._hashes: dict[str, dict] = {}

    # =========================================================================
    # String Commands
    # =========================================================================

    async def get(self, key: str) -> Optional[str]:
        """GET command"""
        return await self.store.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """SET command with options"""
        # Check NX/XX conditions
        if nx:
            if await self.store.exists(key):
                return False
        if xx:
            if not await self.store.exists(key):
                return False

        # Calculate TTL
        ttl = None
        if ex:
            ttl = float(ex)
        elif px:
            ttl = float(px) / 1000

        return await self.store.set(key, value, ttl_seconds=ttl)

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        """SETEX command"""
        return await self.store.set(key, value, ttl_seconds=float(seconds))

    async def setnx(self, key: str, value: str) -> bool:
        """SETNX command"""
        if await self.store.exists(key):
            return False
        return await self.store.set(key, value)

    async def getset(self, key: str, value: str) -> Optional[str]:
        """GETSET command"""
        old_value = await self.store.get(key)
        await self.store.set(key, value)
        return old_value

    async def mget(self, *keys: str) -> list[Optional[str]]:
        """MGET command"""
        results = await self.store.mget(list(keys))
        return [results.get(key) for key in keys]

    async def mset(self, mapping: dict[str, str]) -> bool:
        """MSET command"""
        return await self.store.mset(mapping)

    async def incr(self, key: str) -> int:
        """INCR command"""
        return await self.store.incr(key)

    async def incrby(self, key: str, amount: int) -> int:
        """INCRBY command"""
        return await self.store.incr(key, amount)

    async def decr(self, key: str) -> int:
        """DECR command"""
        return await self.store.decr(key)

    async def decrby(self, key: str, amount: int) -> int:
        """DECRBY command"""
        return await self.store.decr(key, amount)

    async def append(self, key: str, value: str) -> int:
        """APPEND command"""
        current = await self.store.get(key) or ""
        new_value = str(current) + value
        await self.store.set(key, new_value)
        return len(new_value)

    async def strlen(self, key: str) -> int:
        """STRLEN command"""
        value = await self.store.get(key)
        return len(str(value)) if value else 0

    # =========================================================================
    # Key Commands
    # =========================================================================

    async def delete(self, *keys: str) -> int:
        """DEL command"""
        count = 0
        for key in keys:
            if await self.store.delete(key):
                count += 1
        return count

    async def exists(self, *keys: str) -> int:
        """EXISTS command"""
        count = 0
        for key in keys:
            if await self.store.exists(key):
                count += 1
        return count

    async def expire(self, key: str, seconds: int) -> bool:
        """EXPIRE command"""
        return await self.store.expire(key, float(seconds))

    async def ttl(self, key: str) -> int:
        """TTL command"""
        remaining = await self.store.ttl(key)
        if remaining is None:
            if await self.store.exists(key):
                return -1  # No expiration
            return -2  # Key doesn't exist
        return int(remaining)

    async def keys(self, pattern: str = "*") -> list[str]:
        """KEYS command"""
        return await self.store.keys(pattern)

    async def type(self, key: str) -> str:
        """TYPE command"""
        if key in self._lists:
            return "list"
        if key in self._sets:
            return "set"
        if key in self._hashes:
            return "hash"
        if await self.store.exists(key):
            return "string"
        return "none"

    async def rename(self, key: str, new_key: str) -> bool:
        """RENAME command"""
        value = await self.store.get(key)
        if value is None:
            return False

        ttl = await self.store.ttl(key)
        await self.store.delete(key)
        await self.store.set(new_key, value, ttl_seconds=ttl)
        return True

    # =========================================================================
    # List Commands
    # =========================================================================

    async def lpush(self, key: str, *values: Any) -> int:
        """LPUSH command"""
        if key not in self._lists:
            self._lists[key] = []

        for value in values:
            self._lists[key].insert(0, value)

        return len(self._lists[key])

    async def rpush(self, key: str, *values: Any) -> int:
        """RPUSH command"""
        if key not in self._lists:
            self._lists[key] = []

        self._lists[key].extend(values)
        return len(self._lists[key])

    async def lpop(self, key: str) -> Optional[Any]:
        """LPOP command"""
        if key not in self._lists or not self._lists[key]:
            return None
        return self._lists[key].pop(0)

    async def rpop(self, key: str) -> Optional[Any]:
        """RPOP command"""
        if key not in self._lists or not self._lists[key]:
            return None
        return self._lists[key].pop()

    async def llen(self, key: str) -> int:
        """LLEN command"""
        return len(self._lists.get(key, []))

    async def lrange(self, key: str, start: int, stop: int) -> list[Any]:
        """LRANGE command"""
        if key not in self._lists:
            return []

        # Handle negative indices
        lst = self._lists[key]
        if stop == -1:
            stop = len(lst)
        else:
            stop = stop + 1

        return lst[start:stop]

    # =========================================================================
    # Set Commands
    # =========================================================================

    async def sadd(self, key: str, *members: Any) -> int:
        """SADD command"""
        if key not in self._sets:
            self._sets[key] = set()

        before = len(self._sets[key])
        self._sets[key].update(members)
        return len(self._sets[key]) - before

    async def srem(self, key: str, *members: Any) -> int:
        """SREM command"""
        if key not in self._sets:
            return 0

        count = 0
        for member in members:
            if member in self._sets[key]:
                self._sets[key].remove(member)
                count += 1
        return count

    async def smembers(self, key: str) -> set[Any]:
        """SMEMBERS command"""
        return self._sets.get(key, set()).copy()

    async def sismember(self, key: str, member: Any) -> bool:
        """SISMEMBER command"""
        return member in self._sets.get(key, set())

    async def scard(self, key: str) -> int:
        """SCARD command"""
        return len(self._sets.get(key, set()))

    # =========================================================================
    # Hash Commands
    # =========================================================================

    async def hget(self, key: str, field: str) -> Optional[Any]:
        """HGET command"""
        if key not in self._hashes:
            return None
        return self._hashes[key].get(field)

    async def hset(self, key: str, field: str, value: Any) -> bool:
        """HSET command"""
        if key not in self._hashes:
            self._hashes[key] = {}

        is_new = field not in self._hashes[key]
        self._hashes[key][field] = value
        return is_new

    async def hmget(self, key: str, *fields: str) -> list[Optional[Any]]:
        """HMGET command"""
        if key not in self._hashes:
            return [None] * len(fields)

        return [self._hashes[key].get(field) for field in fields]

    async def hmset(self, key: str, mapping: dict[str, Any]) -> bool:
        """HMSET command"""
        if key not in self._hashes:
            self._hashes[key] = {}

        self._hashes[key].update(mapping)
        return True

    async def hdel(self, key: str, *fields: str) -> int:
        """HDEL command"""
        if key not in self._hashes:
            return 0

        count = 0
        for field in fields:
            if field in self._hashes[key]:
                del self._hashes[key][field]
                count += 1
        return count

    async def hgetall(self, key: str) -> dict[str, Any]:
        """HGETALL command"""
        return self._hashes.get(key, {}).copy()

    async def hkeys(self, key: str) -> list[str]:
        """HKEYS command"""
        return list(self._hashes.get(key, {}).keys())

    async def hvals(self, key: str) -> list[Any]:
        """HVALS command"""
        return list(self._hashes.get(key, {}).values())

    async def hlen(self, key: str) -> int:
        """HLEN command"""
        return len(self._hashes.get(key, {}))

    # =========================================================================
    # Server Commands
    # =========================================================================

    async def ping(self, message: str = "PONG") -> str:
        """PING command"""
        return message

    async def info(self, section: Optional[str] = None) -> dict[str, Any]:
        """INFO command"""
        stats = self.store.get_stats()

        return {
            "server": {
                "redis_version": "distributed-cluster-1.0",
                "uptime_in_seconds": 0,
            },
            "clients": {
                "connected_clients": 1,
            },
            "memory": {
                "used_memory": stats.get("memory_bytes", 0),
                "maxmemory": stats.get("max_memory_bytes", 0),
            },
            "stats": {
                "keyspace_hits": stats.get("hits", 0),
                "keyspace_misses": stats.get("misses", 0),
            },
            "keyspace": {
                "keys": stats.get("size", 0),
            },
        }

    async def flushdb(self) -> bool:
        """FLUSHDB command"""
        await self.store.clear()
        self._lists.clear()
        self._sets.clear()
        self._hashes.clear()
        return True

    async def dbsize(self) -> int:
        """DBSIZE command"""
        return self.store.size + len(self._lists) + len(self._sets) + len(self._hashes)

    # =========================================================================
    # Utility
    # =========================================================================

    async def execute_command(
        self,
        command: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        تنفيذ أمر Redis
        Execute Redis command
        """
        cmd = command.upper()

        handlers = {
            "GET": lambda: self.get(args[0]),
            "SET": lambda: self.set(args[0], args[1], **kwargs),
            "DEL": lambda: self.delete(*args),
            "EXISTS": lambda: self.exists(*args),
            "EXPIRE": lambda: self.expire(args[0], int(args[1])),
            "TTL": lambda: self.ttl(args[0]),
            "KEYS": lambda: self.keys(args[0] if args else "*"),
            "INCR": lambda: self.incr(args[0]),
            "DECR": lambda: self.decr(args[0]),
            "PING": lambda: self.ping(args[0] if args else "PONG"),
            "INFO": lambda: self.info(),
            "FLUSHDB": lambda: self.flushdb(),
            "DBSIZE": lambda: self.dbsize(),
            # Add more as needed
        }

        handler = handlers.get(cmd)
        if handler:
            return await handler()

        raise ValueError(f"Unknown command: {command}")
