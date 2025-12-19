"""
Event Broadcaster - موزع الأحداث
================================

يربط بين أحداث النظام و WebSocket:
- Job events (submitted, started, completed, failed)
- Worker events (registered, heartbeat, offline)
- Cluster events (scaling, alerts)
- Log streaming
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from starlette.websockets import WebSocket

from distributed_cluster.models.events import Event, EventType
from distributed_cluster.models.job import Job
from distributed_cluster.models.worker import WorkerInfo
from distributed_cluster.realtime.websocket_manager import EventCategory, WebSocketManager

logger = logging.getLogger(__name__)


@dataclass
class EventSubscription:
    """اشتراك في الأحداث."""

    callback: Callable[[Event], Awaitable[None]]
    event_types: Optional[Set[EventType]] = None  # None = all
    job_filter: Optional[str] = None  # specific job_id
    worker_filter: Optional[str] = None  # specific worker_id


class EventBroadcaster:
    """
    موزع الأحداث.

    يجمع الأحداث من مختلف مكونات النظام ويوزعها عبر WebSocket.
    """

    def __init__(self, ws_manager: WebSocketManager):
        self.ws_manager = ws_manager

        # Internal subscribers (callbacks)
        self._subscribers: List[EventSubscription] = []

        # Event queue for async processing
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue()

        # Background task
        self._processor_task: Optional[asyncio.Task] = None

        # Statistics
        self._events_processed = 0
        self._events_broadcast = 0

    async def start(self) -> None:
        """بدء المعالج."""
        self._processor_task = asyncio.create_task(self._process_events())
        logger.info("Event broadcaster started")

    async def stop(self) -> None:
        """إيقاف المعالج."""
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("Event broadcaster stopped")

    def subscribe(
        self,
        callback: Callable[[Event], Awaitable[None]],
        event_types: Optional[Set[EventType]] = None,
        job_filter: Optional[str] = None,
        worker_filter: Optional[str] = None,
    ) -> EventSubscription:
        """
        الاشتراك في الأحداث.

        Args:
            callback: دالة تُستدعى عند وصول حدث
            event_types: أنواع الأحداث للاشتراك (None = الكل)
            job_filter: تصفية بمعرف مهمة
            worker_filter: تصفية بمعرف عامل

        Returns:
            كائن الاشتراك (للإلغاء لاحقاً)
        """
        subscription = EventSubscription(
            callback=callback,
            event_types=event_types,
            job_filter=job_filter,
            worker_filter=worker_filter,
        )
        self._subscribers.append(subscription)
        return subscription

    def unsubscribe(self, subscription: EventSubscription) -> None:
        """إلغاء اشتراك."""
        if subscription in self._subscribers:
            self._subscribers.remove(subscription)

    async def publish(self, event: Event) -> None:
        """
        نشر حدث.

        Args:
            event: الحدث للنشر
        """
        await self._event_queue.put(event)

    async def publish_job_event(
        self,
        event_type: EventType,
        job: Job,
        message: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        نشر حدث متعلق بمهمة.

        Args:
            event_type: نوع الحدث
            job: المهمة
            message: رسالة اختيارية
            extra_data: بيانات إضافية
        """
        data = {
            "job_id": job.job_id,
            "name": job.submission.name,
            "status": job.status.value,
            "assigned_worker": job.assigned_worker,
        }
        if extra_data:
            data.update(extra_data)

        event = Event(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            source="master",
            job_id=job.job_id,
            worker_id=job.assigned_worker,
            message=message or f"Job {job.job_id} {event_type.value}",
            data=data,
        )
        await self.publish(event)

    async def publish_worker_event(
        self,
        event_type: EventType,
        worker: WorkerInfo,
        message: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        نشر حدث متعلق بعامل.

        Args:
            event_type: نوع الحدث
            worker: العامل
            message: رسالة اختيارية
            extra_data: بيانات إضافية
        """
        data = {
            "worker_id": worker.worker_id,
            "hostname": worker.hostname,
            "status": worker.status.value,
            "cpu_cores": worker.total_resources.cpu_cores,
            "memory_mb": worker.total_resources.memory_mb,
            "gpu_count": worker.total_resources.gpu_count,
        }
        if extra_data:
            data.update(extra_data)

        event = Event(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            source="master",
            worker_id=worker.worker_id,
            message=message or f"Worker {worker.worker_id} {event_type.value}",
            data=data,
        )
        await self.publish(event)

    async def publish_cluster_event(
        self,
        event_type: EventType,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        نشر حدث متعلق بالكلاستر.

        Args:
            event_type: نوع الحدث
            message: رسالة
            data: بيانات
        """
        event = Event(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            source="master",
            message=message,
            data=data or {},
        )
        await self.publish(event)

    async def _process_events(self) -> None:
        """معالجة الأحداث من الطابور."""
        while True:
            try:
                event = await self._event_queue.get()
                await self._dispatch_event(event)
                self._events_processed += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Event processing error: {e}")

    async def _dispatch_event(self, event: Event) -> None:
        """توزيع حدث للمشتركين و WebSocket."""
        # Determine category
        category = self._get_event_category(event.event_type)

        # Broadcast via WebSocket
        sent_count = await self.ws_manager.broadcast(
            category=category,
            event_type=event.event_type.value,
            data=self._event_to_dict(event),
            job_id=event.job_id,
            worker_id=event.worker_id,
        )

        if sent_count > 0:
            self._events_broadcast += sent_count

        # Call internal subscribers
        for subscriber in self._subscribers:
            if self._matches_subscription(event, subscriber):
                try:
                    await subscriber.callback(event)
                except Exception as e:
                    logger.error(f"Subscriber callback error: {e}")

    def _get_event_category(self, event_type: EventType) -> str:
        """تحديد فئة الحدث."""
        job_events = {
            EventType.JOB_SUBMITTED,
            EventType.JOB_ASSIGNED,
            EventType.JOB_STARTED,
            EventType.JOB_PROGRESS,
            EventType.JOB_SUCCEEDED,
            EventType.JOB_FAILED,
            EventType.JOB_CANCELLED,
            EventType.JOB_TIMEOUT,
            EventType.JOB_RETRY,
            EventType.JOB_COMPLETED,
        }

        worker_events = {
            EventType.WORKER_REGISTERED,
            EventType.WORKER_HEARTBEAT,
            EventType.WORKER_OFFLINE,
            EventType.WORKER_RECOVERED,
            EventType.WORKER_DEREGISTERED,
        }

        if event_type in job_events:
            return EventCategory.JOB.value
        elif event_type in worker_events:
            return EventCategory.WORKER.value
        else:
            return EventCategory.CLUSTER.value

    def _matches_subscription(
        self,
        event: Event,
        subscription: EventSubscription,
    ) -> bool:
        """تحقق من تطابق الحدث مع الاشتراك."""
        # Check event type filter
        if subscription.event_types and event.event_type not in subscription.event_types:
            return False

        # Check job filter
        if subscription.job_filter and event.job_id != subscription.job_filter:
            return False

        # Check worker filter
        if subscription.worker_filter and event.worker_id != subscription.worker_filter:
            return False

        return True

    def _event_to_dict(self, event: Event) -> Dict[str, Any]:
        """تحويل حدث إلى dictionary."""
        return {
            "event_type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source,
            "message": event.message,
            "data": event.data,
            "job_id": event.job_id,
            "worker_id": event.worker_id,
        }

    @property
    def stats(self) -> Dict[str, int]:
        """إحصائيات المعالج."""
        return {
            "events_processed": self._events_processed,
            "events_broadcast": self._events_broadcast,
            "queue_size": self._event_queue.qsize(),
            "subscribers": len(self._subscribers),
        }


# Helper function to integrate with FastAPI
def create_websocket_routes(
    ws_manager: WebSocketManager,
    broadcaster: EventBroadcaster,
):
    """
    إنشاء مسارات WebSocket لـ FastAPI.

    Usage:
        from fastapi import FastAPI, WebSocket, Query

        app = FastAPI()
        ws_manager = WebSocketManager()
        broadcaster = EventBroadcaster(ws_manager)

        @app.websocket("/ws")
        async def websocket_route(
            websocket: WebSocket,
            token: str = Query(None),
        ):
            await websocket_handler(websocket, ws_manager, token)

        @app.on_event("startup")
        async def startup():
            await ws_manager.start()
            await broadcaster.start()

        @app.on_event("shutdown")
        async def shutdown():
            await broadcaster.stop()
            await ws_manager.stop()
    """
    pass  # Implementation is in the docstring example


async def websocket_handler(
    websocket: WebSocket,
    manager: WebSocketManager,
    token: Optional[str] = None,
) -> None:
    """
    WebSocket handler.

    Args:
        websocket: WebSocket connection
        manager: WebSocket manager
        token: Auth token
    """
    from fastapi import WebSocketDisconnect

    conn_info = await manager.connect(websocket, token)
    if not conn_info:
        return

    try:
        while True:
            data = await websocket.receive_json()
            await manager.handle_message(conn_info.connection_id, data)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(conn_info.connection_id)
