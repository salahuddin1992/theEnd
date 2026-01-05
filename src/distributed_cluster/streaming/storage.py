"""
Event storage and replay functionality for persistent event streams.
"""

import asyncio
import gzip
import json
import logging
import shutil
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from .events import Event, EventPriority, EventType

logger = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """Configuration for event storage."""
    retention_days: int = 30
    max_events: int = 10000000  # 10 million
    batch_size: int = 1000
    compression: bool = True
    sync_interval_ms: int = 1000
    archive_enabled: bool = True
    archive_after_days: int = 7
    index_fields: List[str] = field(default_factory=lambda: ["event_type", "timestamp"])


@dataclass
class StorageMetrics:
    """Metrics for event storage."""
    events_stored: int = 0
    events_retrieved: int = 0
    bytes_stored: int = 0
    bytes_retrieved: int = 0
    storage_errors: int = 0


class EventStore(ABC):
    """Abstract base class for event storage."""

    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        self.metrics = StorageMetrics()

    @abstractmethod
    def store(self, event: Event) -> bool:
        """Store a single event."""
        pass

    @abstractmethod
    def store_batch(self, events: List[Event]) -> int:
        """Store a batch of events. Returns number stored."""
        pass

    @abstractmethod
    def get(self, event_id: str) -> Optional[Event]:
        """Get an event by ID."""
        pass

    @abstractmethod
    def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Event]:
        """Query events with filters."""
        pass

    @abstractmethod
    def count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None
    ) -> int:
        """Count events matching filters."""
        pass

    @abstractmethod
    def delete(self, event_ids: List[str]) -> int:
        """Delete events by ID. Returns number deleted."""
        pass

    @abstractmethod
    def cleanup(self, before: datetime) -> int:
        """Delete events older than the given time. Returns number deleted."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the store."""
        pass


class InMemoryEventStore(EventStore):
    """In-memory event store for testing and development."""

    def __init__(self, config: Optional[StorageConfig] = None):
        super().__init__(config)
        self._events: Dict[str, Event] = {}
        self._events_by_time: List[Tuple[datetime, str]] = []  # (timestamp, event_id)
        self._lock = threading.RLock()

    def store(self, event: Event) -> bool:
        with self._lock:
            if len(self._events) >= self.config.max_events:
                # Remove oldest events
                self._evict_oldest(self.config.max_events // 10)

            self._events[event.event_id] = event
            self._events_by_time.append((event.timestamp, event.event_id))
            self._events_by_time.sort(key=lambda x: x[0])

            self.metrics.events_stored += 1
            self.metrics.bytes_stored += len(event.to_json())
            return True

    def store_batch(self, events: List[Event]) -> int:
        count = 0
        for event in events:
            if self.store(event):
                count += 1
        return count

    def get(self, event_id: str) -> Optional[Event]:
        with self._lock:
            event = self._events.get(event_id)
            if event:
                self.metrics.events_retrieved += 1
                self.metrics.bytes_retrieved += len(event.to_json())
            return event

    def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Event]:
        with self._lock:
            results = []

            for timestamp, event_id in self._events_by_time:
                if start_time and timestamp < start_time:
                    continue
                if end_time and timestamp >= end_time:
                    continue

                event = self._events.get(event_id)
                if not event:
                    continue

                if event_types and event.event_type not in event_types:
                    continue

                results.append(event)

            # Apply offset and limit
            results = results[offset:offset + limit]

            for event in results:
                self.metrics.events_retrieved += 1
                self.metrics.bytes_retrieved += len(event.to_json())

            return results

    def count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None
    ) -> int:
        with self._lock:
            count = 0

            for timestamp, event_id in self._events_by_time:
                if start_time and timestamp < start_time:
                    continue
                if end_time and timestamp >= end_time:
                    continue

                event = self._events.get(event_id)
                if not event:
                    continue

                if event_types and event.event_type not in event_types:
                    continue

                count += 1

            return count

    def delete(self, event_ids: List[str]) -> int:
        with self._lock:
            count = 0
            for event_id in event_ids:
                if event_id in self._events:
                    del self._events[event_id]
                    count += 1

            self._events_by_time = [
                (ts, eid) for ts, eid in self._events_by_time
                if eid not in event_ids
            ]
            return count

    def cleanup(self, before: datetime) -> int:
        with self._lock:
            to_delete = []
            for timestamp, event_id in self._events_by_time:
                if timestamp < before:
                    to_delete.append(event_id)
                else:
                    break  # Sorted by time, so we can stop

            return self.delete(to_delete)

    def _evict_oldest(self, count: int):
        """Evict the oldest events."""
        to_delete = [eid for _, eid in self._events_by_time[:count]]
        self.delete(to_delete)

    def close(self) -> None:
        with self._lock:
            self._events.clear()
            self._events_by_time.clear()


class FileEventStore(EventStore):
    """File-based event store with rotation and compression."""

    def __init__(self, directory: str, config: Optional[StorageConfig] = None):
        super().__init__(config)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

        self._current_file: Optional[Path] = None
        self._current_handle = None
        self._buffer: List[Event] = []
        self._lock = threading.RLock()
        self._last_sync = time.time()

        self._init_current_file()

    def _init_current_file(self):
        """Initialize current log file."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._current_file = self.directory / f"events-{today}.jsonl"

        if self.config.compression:
            self._current_file = self._current_file.with_suffix(".jsonl")

        self._current_handle = open(self._current_file, "a", encoding="utf-8")

    def _rotate_if_needed(self):
        """Rotate log file if date changed."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        expected_file = self.directory / f"events-{today}.jsonl"

        if expected_file != self._current_file:
            self._close_current_file()
            self._compress_old_files()
            self._init_current_file()

    def _close_current_file(self):
        """Close the current file handle."""
        if self._current_handle:
            self._flush_buffer()
            self._current_handle.close()
            self._current_handle = None

    def _compress_old_files(self):
        """Compress old log files."""
        if not self.config.compression:
            return

        for file in self.directory.glob("events-*.jsonl"):
            if file == self._current_file:
                continue

            gz_file = file.with_suffix(".jsonl.gz")
            if not gz_file.exists():
                with open(file, "rb") as f_in:
                    with gzip.open(gz_file, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                file.unlink()

    def _flush_buffer(self):
        """Flush the buffer to disk."""
        if not self._buffer:
            return

        for event in self._buffer:
            self._current_handle.write(event.to_json() + "\n")

        self._current_handle.flush()
        self._buffer.clear()
        self._last_sync = time.time()

    def store(self, event: Event) -> bool:
        with self._lock:
            try:
                self._rotate_if_needed()
                self._buffer.append(event)

                self.metrics.events_stored += 1
                self.metrics.bytes_stored += len(event.to_json())

                # Flush if batch size reached or sync interval passed
                if (len(self._buffer) >= self.config.batch_size or
                    (time.time() - self._last_sync) * 1000 >= self.config.sync_interval_ms):
                    self._flush_buffer()

                return True
            except Exception as e:
                logger.error(f"Error storing event: {e}")
                self.metrics.storage_errors += 1
                return False

    def store_batch(self, events: List[Event]) -> int:
        count = 0
        for event in events:
            if self.store(event):
                count += 1
        return count

    def get(self, event_id: str) -> Optional[Event]:
        with self._lock:
            # Check buffer first
            for event in self._buffer:
                if event.event_id == event_id:
                    self.metrics.events_retrieved += 1
                    return event

            # Search files
            for file in sorted(self.directory.glob("events-*"), reverse=True):
                for event in self._read_file(file):
                    if event.event_id == event_id:
                        self.metrics.events_retrieved += 1
                        return event

            return None

    def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Event]:
        with self._lock:
            self._flush_buffer()  # Ensure all events are on disk

            results = []
            skipped = 0

            for event in self._iterate_all_events():
                if start_time and event.timestamp < start_time:
                    continue
                if end_time and event.timestamp >= end_time:
                    continue
                if event_types and event.event_type not in event_types:
                    continue

                if skipped < offset:
                    skipped += 1
                    continue

                results.append(event)
                self.metrics.events_retrieved += 1

                if len(results) >= limit:
                    break

            return results

    def count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None
    ) -> int:
        with self._lock:
            self._flush_buffer()

            count = 0
            for event in self._iterate_all_events():
                if start_time and event.timestamp < start_time:
                    continue
                if end_time and event.timestamp >= end_time:
                    continue
                if event_types and event.event_type not in event_types:
                    continue
                count += 1

            return count

    def _iterate_all_events(self) -> Iterator[Event]:
        """Iterate all events in chronological order."""
        files = sorted(self.directory.glob("events-*"))

        for file in files:
            for event in self._read_file(file):
                yield event

    def _read_file(self, file: Path) -> Iterator[Event]:
        """Read events from a file."""
        try:
            if file.suffix == ".gz":
                with gzip.open(file, "rt", encoding="utf-8") as f:
                    for line in f:
                        yield Event.from_json(line.strip())
            else:
                with open(file, "r", encoding="utf-8") as f:
                    for line in f:
                        yield Event.from_json(line.strip())
        except Exception as e:
            logger.error(f"Error reading file {file}: {e}")

    def delete(self, event_ids: List[str]) -> int:
        # File-based store doesn't support individual deletion
        logger.warning("FileEventStore doesn't support individual event deletion")
        return 0

    def cleanup(self, before: datetime) -> int:
        with self._lock:
            count = 0
            cutoff_date = before.strftime("%Y-%m-%d")

            for file in self.directory.glob("events-*"):
                # Extract date from filename
                try:
                    file_date = file.stem.split("-", 1)[1].replace(".jsonl", "")
                    if file_date < cutoff_date:
                        event_count = sum(1 for _ in self._read_file(file))
                        file.unlink()
                        count += event_count
                except Exception as e:
                    logger.error(f"Error cleaning up file {file}: {e}")

            return count

    def close(self) -> None:
        with self._lock:
            self._close_current_file()


class PostgresEventStore(EventStore):
    """PostgreSQL-based event store for production use."""

    def __init__(self, connection_string: str, config: Optional[StorageConfig] = None):
        super().__init__(config)
        self.connection_string = connection_string
        self._pool = None
        self._init_pool()
        self._init_schema()

    def _init_pool(self):
        """Initialize connection pool."""
        try:
            import psycopg2  # noqa: F401
            from psycopg2 import pool

            self._pool = pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                dsn=self.connection_string
            )
        except ImportError:
            logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
            raise

    def _init_schema(self):
        """Initialize database schema."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        event_id VARCHAR(36) PRIMARY KEY,
                        event_type VARCHAR(50) NOT NULL,
                        priority VARCHAR(20) NOT NULL,
                        timestamp TIMESTAMP NOT NULL,
                        payload JSONB NOT NULL,
                        metadata JSONB NOT NULL,
                        version VARCHAR(10) NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
                    CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
                    CREATE INDEX IF NOT EXISTS idx_events_type_timestamp ON events(event_type, timestamp);
                """)
                conn.commit()
        finally:
            self._pool.putconn(conn)

    def store(self, event: Event) -> bool:
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO events (event_id, event_type, priority, timestamp, payload, metadata, version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id) DO NOTHING
                """, (
                    event.event_id,
                    event.event_type.name,
                    event.priority.name,
                    event.timestamp,
                    json.dumps(event.payload),
                    json.dumps(event.metadata.to_dict()),
                    event.version
                ))
                conn.commit()
                self.metrics.events_stored += 1
                self.metrics.bytes_stored += len(event.to_json())
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error storing event: {e}")
            self.metrics.storage_errors += 1
            return False
        finally:
            self._pool.putconn(conn)

    def store_batch(self, events: List[Event]) -> int:
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                from psycopg2.extras import execute_values

                values = [
                    (
                        e.event_id,
                        e.event_type.name,
                        e.priority.name,
                        e.timestamp,
                        json.dumps(e.payload),
                        json.dumps(e.metadata.to_dict()),
                        e.version
                    )
                    for e in events
                ]

                execute_values(cur, """
                    INSERT INTO events (event_id, event_type, priority, timestamp, payload, metadata, version)
                    VALUES %s
                    ON CONFLICT (event_id) DO NOTHING
                """, values)

                conn.commit()
                count = cur.rowcount
                self.metrics.events_stored += count
                return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Error storing batch: {e}")
            self.metrics.storage_errors += 1
            return 0
        finally:
            self._pool.putconn(conn)

    def get(self, event_id: str) -> Optional[Event]:
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT event_id, event_type, priority, timestamp, payload, metadata, version
                    FROM events WHERE event_id = %s
                """, (event_id,))

                row = cur.fetchone()
                if row:
                    self.metrics.events_retrieved += 1
                    return self._row_to_event(row)
                return None
        finally:
            self._pool.putconn(conn)

    def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Event]:
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                conditions = []
                params = []

                if start_time:
                    conditions.append("timestamp >= %s")
                    params.append(start_time)
                if end_time:
                    conditions.append("timestamp < %s")
                    params.append(end_time)
                if event_types:
                    placeholders = ",".join(["%s"] * len(event_types))
                    conditions.append(f"event_type IN ({placeholders})")
                    params.extend(et.name for et in event_types)

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                cur.execute(f"""
                    SELECT event_id, event_type, priority, timestamp, payload, metadata, version
                    FROM events
                    WHERE {where_clause}
                    ORDER BY timestamp
                    LIMIT %s OFFSET %s
                """, params + [limit, offset])

                results = [self._row_to_event(row) for row in cur.fetchall()]
                self.metrics.events_retrieved += len(results)
                return results
        finally:
            self._pool.putconn(conn)

    def count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None
    ) -> int:
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                conditions = []
                params = []

                if start_time:
                    conditions.append("timestamp >= %s")
                    params.append(start_time)
                if end_time:
                    conditions.append("timestamp < %s")
                    params.append(end_time)
                if event_types:
                    placeholders = ",".join(["%s"] * len(event_types))
                    conditions.append(f"event_type IN ({placeholders})")
                    params.extend(et.name for et in event_types)

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                cur.execute(f"SELECT COUNT(*) FROM events WHERE {where_clause}", params)
                return cur.fetchone()[0]
        finally:
            self._pool.putconn(conn)

    def delete(self, event_ids: List[str]) -> int:
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(event_ids))
                cur.execute(f"DELETE FROM events WHERE event_id IN ({placeholders})", event_ids)
                conn.commit()
                return cur.rowcount
        finally:
            self._pool.putconn(conn)

    def cleanup(self, before: datetime) -> int:
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM events WHERE timestamp < %s", (before,))
                conn.commit()
                return cur.rowcount
        finally:
            self._pool.putconn(conn)

    def _row_to_event(self, row) -> Event:
        """Convert database row to Event."""
        return Event(
            event_id=row[0],
            event_type=EventType[row[1]],
            priority=EventPriority[row[2]],
            timestamp=row[3],
            payload=row[4],
            metadata=row[5],
            version=row[6]
        )

    def close(self) -> None:
        if self._pool:
            self._pool.closeall()


class EventReplay:
    """Replays events from storage."""

    def __init__(
        self,
        store: EventStore,
        handler: Callable[[Event], None],
        speed_multiplier: float = 1.0,
        batch_size: int = 100
    ):
        self.store = store
        self.handler = handler
        self.speed_multiplier = speed_multiplier
        self.batch_size = batch_size
        self._running = False
        self._paused = False
        self._current_position: Optional[datetime] = None
        self._events_replayed = 0
        self._replay_task = None

    async def replay(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None,
        real_time: bool = False
    ):
        """
        Replay events within a time range.

        Args:
            start_time: Start of replay range
            end_time: End of replay range
            event_types: Filter by event types
            real_time: If True, replay at original speed (adjusted by speed_multiplier)
        """
        self._running = True
        self._paused = False
        self._events_replayed = 0

        offset = 0
        last_timestamp: Optional[datetime] = None

        while self._running:
            if self._paused:
                await asyncio.sleep(0.1)
                continue

            events = self.store.query(
                start_time=start_time,
                end_time=end_time,
                event_types=event_types,
                limit=self.batch_size,
                offset=offset
            )

            if not events:
                break

            for event in events:
                if not self._running:
                    break

                while self._paused:
                    await asyncio.sleep(0.1)

                # Real-time replay with timing
                if real_time and last_timestamp:
                    delay = (event.timestamp - last_timestamp).total_seconds()
                    adjusted_delay = delay / self.speed_multiplier
                    if adjusted_delay > 0:
                        await asyncio.sleep(adjusted_delay)

                try:
                    self.handler(event)
                    self._events_replayed += 1
                    self._current_position = event.timestamp
                    last_timestamp = event.timestamp
                except Exception as e:
                    logger.error(f"Error replaying event {event.event_id}: {e}")

            offset += len(events)

        self._running = False

    def pause(self):
        """Pause replay."""
        self._paused = True

    def resume(self):
        """Resume replay."""
        self._paused = False

    def stop(self):
        """Stop replay."""
        self._running = False

    @property
    def events_replayed(self) -> int:
        return self._events_replayed

    @property
    def current_position(self) -> Optional[datetime]:
        return self._current_position

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused
