"""
Stream processing engine for event aggregation, filtering, and transformation.
"""

import asyncio
import logging
import statistics
import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from .events import Event, EventPriority, EventType

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


class WindowType(Enum):
    """Types of time windows for stream processing."""

    TUMBLING = "tumbling"  # Fixed, non-overlapping windows
    SLIDING = "sliding"  # Overlapping windows
    SESSION = "session"  # Activity-based windows
    GLOBAL = "global"  # No windowing


@dataclass
class WindowConfig:
    """Configuration for windowed processing."""

    window_type: WindowType = WindowType.TUMBLING
    window_size_ms: int = 60000  # 1 minute
    slide_size_ms: int = 30000  # For sliding windows
    session_gap_ms: int = 30000  # For session windows
    allowed_lateness_ms: int = 0  # Late event tolerance
    watermark_interval_ms: int = 1000


@dataclass
class Window:
    """Represents a time window."""

    start: datetime
    end: datetime
    events: List[Event] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return int((self.end - self.start).total_seconds() * 1000)

    def contains(self, timestamp: datetime) -> bool:
        return self.start <= timestamp < self.end

    def add(self, event: Event):
        self.events.append(event)


class EventFilter(ABC):
    """Abstract base class for event filters."""

    @abstractmethod
    def matches(self, event: Event) -> bool:
        """Check if an event matches the filter."""
        pass

    def __and__(self, other: "EventFilter") -> "EventFilter":
        return AndFilter(self, other)

    def __or__(self, other: "EventFilter") -> "EventFilter":
        return OrFilter(self, other)

    def __invert__(self) -> "EventFilter":
        return NotFilter(self)


class AndFilter(EventFilter):
    """Combines filters with AND logic."""

    def __init__(self, *filters: EventFilter):
        self.filters = filters

    def matches(self, event: Event) -> bool:
        return all(f.matches(event) for f in self.filters)


class OrFilter(EventFilter):
    """Combines filters with OR logic."""

    def __init__(self, *filters: EventFilter):
        self.filters = filters

    def matches(self, event: Event) -> bool:
        return any(f.matches(event) for f in self.filters)


class NotFilter(EventFilter):
    """Negates a filter."""

    def __init__(self, filter: EventFilter):
        self.filter = filter

    def matches(self, event: Event) -> bool:
        return not self.filter.matches(event)


class TypeFilter(EventFilter):
    """Filter events by type."""

    def __init__(self, event_types: Union[EventType, List[EventType]]):
        if isinstance(event_types, EventType):
            event_types = [event_types]
        self.event_types = set(event_types)

    def matches(self, event: Event) -> bool:
        return event.event_type in self.event_types


class PriorityFilter(EventFilter):
    """Filter events by priority."""

    def __init__(self, min_priority: EventPriority):
        self.min_priority = min_priority

    def matches(self, event: Event) -> bool:
        return event.priority.value <= self.min_priority.value


class PayloadFilter(EventFilter):
    """Filter events by payload content."""

    def __init__(self, key: str, value: Any = None, predicate: Optional[Callable[[Any], bool]] = None):
        self.key = key
        self.value = value
        self.predicate = predicate

    def matches(self, event: Event) -> bool:
        actual_value = event.payload.get(self.key)

        if self.predicate:
            return self.predicate(actual_value)

        return actual_value == self.value


class TimeRangeFilter(EventFilter):
    """Filter events by time range."""

    def __init__(self, start: Optional[datetime] = None, end: Optional[datetime] = None):
        self.start = start
        self.end = end

    def matches(self, event: Event) -> bool:
        if self.start and event.timestamp < self.start:
            return False
        if self.end and event.timestamp >= self.end:
            return False
        return True


class SourceFilter(EventFilter):
    """Filter events by source."""

    def __init__(self, sources: Union[str, List[str]], pattern: bool = False):
        if isinstance(sources, str):
            sources = [sources]
        self.sources = sources
        self.pattern = pattern

    def matches(self, event: Event) -> bool:
        source = event.metadata.source

        if self.pattern:
            import re

            return any(re.match(p, source) for p in self.sources)

        return source in self.sources


class TenantFilter(EventFilter):
    """Filter events by tenant."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def matches(self, event: Event) -> bool:
        return event.metadata.tenant_id == self.tenant_id


class EventTransformer(ABC):
    """Abstract base class for event transformers."""

    @abstractmethod
    def transform(self, event: Event) -> Optional[Event]:
        """Transform an event. Returns None to drop the event."""
        pass

    def __rshift__(self, other: "EventTransformer") -> "EventTransformer":
        return ChainedTransformer(self, other)


class ChainedTransformer(EventTransformer):
    """Chains multiple transformers."""

    def __init__(self, *transformers: EventTransformer):
        self.transformers = transformers

    def transform(self, event: Event) -> Optional[Event]:
        result = event
        for transformer in self.transformers:
            result = transformer.transform(result)
            if result is None:
                return None
        return result


class MapTransformer(EventTransformer):
    """Transform events using a mapping function."""

    def __init__(self, map_fn: Callable[[Event], Event]):
        self.map_fn = map_fn

    def transform(self, event: Event) -> Optional[Event]:
        return self.map_fn(event)


class EnrichTransformer(EventTransformer):
    """Enrich events with additional data."""

    def __init__(
        self, enrichments: Dict[str, Any] = None, enrich_fn: Optional[Callable[[Event], Dict[str, Any]]] = None
    ):
        self.enrichments = enrichments or {}
        self.enrich_fn = enrich_fn

    def transform(self, event: Event) -> Optional[Event]:
        if self.enrich_fn:
            additional = self.enrich_fn(event)
            event.payload.update(additional)

        event.payload.update(self.enrichments)
        return event


class ProjectTransformer(EventTransformer):
    """Project only specific fields from the event payload."""

    def __init__(self, fields: List[str]):
        self.fields = set(fields)

    def transform(self, event: Event) -> Optional[Event]:
        event.payload = {k: v for k, v in event.payload.items() if k in self.fields}
        return event


class FlatMapTransformer(EventTransformer):
    """Transform one event into multiple events."""

    def __init__(self, flat_map_fn: Callable[[Event], List[Event]]):
        self.flat_map_fn = flat_map_fn

    def transform(self, event: Event) -> Optional[Event]:
        # Returns the first event; use with StreamProcessor for full flat_map
        results = self.flat_map_fn(event)
        return results[0] if results else None

    def transform_many(self, event: Event) -> List[Event]:
        return self.flat_map_fn(event)


class AggregationFunction(ABC):
    """Abstract base class for aggregation functions."""

    @abstractmethod
    def add(self, value: Any) -> None:
        """Add a value to the aggregation."""
        pass

    @abstractmethod
    def result(self) -> Any:
        """Get the aggregation result."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset the aggregation."""
        pass


class CountAggregation(AggregationFunction):
    """Count aggregation."""

    def __init__(self):
        self._count = 0

    def add(self, value: Any) -> None:
        self._count += 1

    def result(self) -> int:
        return self._count

    def reset(self) -> None:
        self._count = 0


class SumAggregation(AggregationFunction):
    """Sum aggregation."""

    def __init__(self):
        self._sum = 0.0

    def add(self, value: Any) -> None:
        if isinstance(value, (int, float)):
            self._sum += value

    def result(self) -> float:
        return self._sum

    def reset(self) -> None:
        self._sum = 0.0


class AvgAggregation(AggregationFunction):
    """Average aggregation."""

    def __init__(self):
        self._sum = 0.0
        self._count = 0

    def add(self, value: Any) -> None:
        if isinstance(value, (int, float)):
            self._sum += value
            self._count += 1

    def result(self) -> float:
        return self._sum / self._count if self._count > 0 else 0.0

    def reset(self) -> None:
        self._sum = 0.0
        self._count = 0


class MinAggregation(AggregationFunction):
    """Minimum aggregation."""

    def __init__(self):
        self._min = None

    def add(self, value: Any) -> None:
        if isinstance(value, (int, float)):
            if self._min is None or value < self._min:
                self._min = value

    def result(self) -> Optional[float]:
        return self._min

    def reset(self) -> None:
        self._min = None


class MaxAggregation(AggregationFunction):
    """Maximum aggregation."""

    def __init__(self):
        self._max = None

    def add(self, value: Any) -> None:
        if isinstance(value, (int, float)):
            if self._max is None or value > self._max:
                self._max = value

    def result(self) -> Optional[float]:
        return self._max

    def reset(self) -> None:
        self._max = None


class StdDevAggregation(AggregationFunction):
    """Standard deviation aggregation."""

    def __init__(self):
        self._values: List[float] = []

    def add(self, value: Any) -> None:
        if isinstance(value, (int, float)):
            self._values.append(float(value))

    def result(self) -> float:
        if len(self._values) < 2:
            return 0.0
        return statistics.stdev(self._values)

    def reset(self) -> None:
        self._values = []


class PercentileAggregation(AggregationFunction):
    """Percentile aggregation."""

    def __init__(self, percentile: float = 95.0):
        self.percentile = percentile
        self._values: List[float] = []

    def add(self, value: Any) -> None:
        if isinstance(value, (int, float)):
            self._values.append(float(value))

    def result(self) -> float:
        if not self._values:
            return 0.0
        sorted_values = sorted(self._values)
        index = int(len(sorted_values) * self.percentile / 100)
        return sorted_values[min(index, len(sorted_values) - 1)]

    def reset(self) -> None:
        self._values = []


class EventAggregator:
    """Aggregates events over time windows."""

    def __init__(
        self,
        window_config: Optional[WindowConfig] = None,
        group_by: Optional[Callable[[Event], str]] = None,
        aggregations: Optional[Dict[str, tuple]] = None,
    ):
        self.window_config = window_config or WindowConfig()
        self.group_by = group_by
        self.aggregations = aggregations or {}  # field -> (extract_fn, aggregation_fn)
        self._windows: Dict[str, Dict[datetime, Window]] = defaultdict(dict)  # group -> start -> window
        self._lock = threading.Lock()

    def add(self, event: Event):
        """Add an event to the appropriate window."""
        group_key = self.group_by(event) if self.group_by else "__default__"
        window_start = self._get_window_start(event.timestamp)

        with self._lock:
            if window_start not in self._windows[group_key]:
                window_end = window_start + timedelta(milliseconds=self.window_config.window_size_ms)
                self._windows[group_key][window_start] = Window(start=window_start, end=window_end)

            self._windows[group_key][window_start].add(event)

    def _get_window_start(self, timestamp: datetime) -> datetime:
        """Calculate window start time for a timestamp."""
        epoch = datetime(1970, 1, 1)
        ms_since_epoch = int((timestamp - epoch).total_seconds() * 1000)
        window_start_ms = (ms_since_epoch // self.window_config.window_size_ms) * self.window_config.window_size_ms
        return epoch + timedelta(milliseconds=window_start_ms)

    def get_completed_windows(self) -> List[tuple]:
        """Get all completed windows with their aggregation results."""
        now = datetime.now(timezone.utc)
        results = []

        with self._lock:
            for group_key, windows in list(self._windows.items()):
                for window_start, window in list(windows.items()):
                    if window.end <= now:
                        # Window is complete
                        agg_results = self._aggregate_window(window)
                        results.append((group_key, window, agg_results))
                        del windows[window_start]

        return results

    def _aggregate_window(self, window: Window) -> Dict[str, Any]:
        """Compute aggregations for a window."""
        results = {}

        for field_name, (extract_fn, agg_class) in self.aggregations.items():
            agg = agg_class()
            for event in window.events:
                value = extract_fn(event)
                agg.add(value)
            results[field_name] = agg.result()

        results["__count__"] = len(window.events)
        results["__window_start__"] = window.start.isoformat()
        results["__window_end__"] = window.end.isoformat()

        return results


class StreamProcessor:
    """Main stream processing engine."""

    def __init__(self):
        self._filters: List[EventFilter] = []
        self._transformers: List[EventTransformer] = []
        self._aggregator: Optional[EventAggregator] = None
        self._output_handlers: List[Callable[[Event], None]] = []
        self._running = False
        self._input_queue: asyncio.Queue = None
        self._process_task: Optional[asyncio.Task] = None
        self._metrics = {
            "events_processed": 0,
            "events_filtered": 0,
            "events_transformed": 0,
            "events_output": 0,
            "errors": 0,
        }

    def filter(self, *filters: EventFilter) -> "StreamProcessor":
        """Add filters to the processor."""
        self._filters.extend(filters)
        return self

    def transform(self, *transformers: EventTransformer) -> "StreamProcessor":
        """Add transformers to the processor."""
        self._transformers.extend(transformers)
        return self

    def aggregate(
        self,
        window_config: Optional[WindowConfig] = None,
        group_by: Optional[Callable[[Event], str]] = None,
        aggregations: Optional[Dict[str, tuple]] = None,
    ) -> "StreamProcessor":
        """Configure aggregation."""
        self._aggregator = EventAggregator(window_config, group_by, aggregations)
        return self

    def output(self, handler: Callable[[Event], None]) -> "StreamProcessor":
        """Add an output handler."""
        self._output_handlers.append(handler)
        return self

    async def start(self, buffer_size: int = 1000):
        """Start the stream processor."""
        self._input_queue = asyncio.Queue(maxsize=buffer_size)
        self._running = True
        self._process_task = asyncio.create_task(self._process_loop())

        if self._aggregator:
            asyncio.create_task(self._aggregation_loop())

    async def stop(self):
        """Stop the stream processor."""
        self._running = False
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass

    async def process(self, event: Event):
        """Add an event for processing."""
        if self._input_queue:
            await self._input_queue.put(event)

    def process_sync(self, event: Event) -> Optional[Event]:
        """Synchronously process a single event."""
        self._metrics["events_processed"] += 1

        # Apply filters
        for filter in self._filters:
            if not filter.matches(event):
                self._metrics["events_filtered"] += 1
                return None

        # Apply transformers
        for transformer in self._transformers:
            event = transformer.transform(event)
            if event is None:
                return None
            self._metrics["events_transformed"] += 1

        # Add to aggregator if configured
        if self._aggregator:
            self._aggregator.add(event)

        # Send to outputs
        for handler in self._output_handlers:
            try:
                handler(event)
                self._metrics["events_output"] += 1
            except Exception as e:
                logger.error(f"Output handler error: {e}")
                self._metrics["errors"] += 1

        return event

    async def _process_loop(self):
        """Main processing loop."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._input_queue.get(), timeout=0.1)
                self.process_sync(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Process loop error: {e}")
                self._metrics["errors"] += 1

    async def _aggregation_loop(self):
        """Background loop to emit aggregation results."""
        while self._running:
            await asyncio.sleep(1)  # Check every second

            if self._aggregator:
                completed = self._aggregator.get_completed_windows()
                for group_key, window, results in completed:
                    # Create aggregation event
                    agg_event = Event(
                        event_type=EventType.METRIC_CUSTOM,
                        payload={
                            "group": group_key,
                            "aggregations": results,
                        },
                    )

                    for handler in self._output_handlers:
                        try:
                            handler(agg_event)
                        except Exception as e:
                            logger.error(f"Aggregation output error: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get processor metrics."""
        return dict(self._metrics)


class WindowedProcessor:
    """Processor with explicit window management."""

    def __init__(self, window_config: WindowConfig):
        self.window_config = window_config
        self._windows: deque = deque()
        self._current_window: Optional[Window] = None
        self._handlers: List[Callable[[Window], None]] = []
        self._lock = threading.Lock()

    def add(self, event: Event):
        """Add an event to the current window."""
        with self._lock:
            now = datetime.now(timezone.utc)

            # Close expired windows
            self._close_expired_windows(now)

            # Create new window if needed
            if self._current_window is None or not self._current_window.contains(event.timestamp):
                self._create_new_window(event.timestamp)

            self._current_window.add(event)

    def _close_expired_windows(self, now: datetime):
        """Close windows that have expired."""
        while self._windows:
            window = self._windows[0]
            if window.end <= now:
                self._windows.popleft()
                for handler in self._handlers:
                    try:
                        handler(window)
                    except Exception as e:
                        logger.error(f"Window handler error: {e}")
            else:
                break

    def _create_new_window(self, timestamp: datetime):
        """Create a new window starting at the given timestamp."""
        start = self._align_to_window(timestamp)
        end = start + timedelta(milliseconds=self.window_config.window_size_ms)

        self._current_window = Window(start=start, end=end)
        self._windows.append(self._current_window)

    def _align_to_window(self, timestamp: datetime) -> datetime:
        """Align timestamp to window boundary."""
        epoch = datetime(1970, 1, 1)
        ms_since_epoch = int((timestamp - epoch).total_seconds() * 1000)
        aligned_ms = (ms_since_epoch // self.window_config.window_size_ms) * self.window_config.window_size_ms
        return epoch + timedelta(milliseconds=aligned_ms)

    def on_window_close(self, handler: Callable[[Window], None]):
        """Register a handler for window close events."""
        self._handlers.append(handler)

    def flush(self):
        """Force close all windows."""
        with self._lock:
            for window in self._windows:
                for handler in self._handlers:
                    try:
                        handler(window)
                    except Exception as e:
                        logger.error(f"Window flush error: {e}")
            self._windows.clear()
            self._current_window = None
