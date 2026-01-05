# -*- coding: utf-8 -*-
"""
GraphQL Subscriptions for NebulaCompute.

Implements real-time subscriptions using WebSocket.

اشتراكات GraphQL للتحديثات المباشرة.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class Subscriber:
    """Subscription client."""

    subscriber_id: str
    subscription_type: str
    filters: Dict[str, Any]
    queue: asyncio.Queue
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_message_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "subscriber_id": self.subscriber_id,
            "subscription_type": self.subscription_type,
            "filters": self.filters,
            "created_at": self.created_at.isoformat(),
            "last_message_at": (self.last_message_at.isoformat() if self.last_message_at else None),
        }


@dataclass
class JobSubscription:
    """Job status subscription configuration."""

    job_id: Optional[str] = None
    statuses: Optional[List[str]] = None
    include_progress: bool = True


@dataclass
class ClusterSubscription:
    """Cluster metrics subscription configuration."""

    interval_seconds: int = 5
    metrics: Optional[List[str]] = None


class SubscriptionManager:
    """
    Manages GraphQL subscriptions.

    مدير اشتراكات GraphQL.

    Features:
    - Job status subscriptions
    - Job progress updates
    - Worker status changes
    - Cluster metrics streaming
    - Alert notifications
    """

    def __init__(
        self,
        max_subscribers: int = 1000,
        message_buffer_size: int = 100,
    ):
        """
        Initialize Subscription Manager.

        Args:
            max_subscribers: Maximum concurrent subscribers
            message_buffer_size: Size of message buffer per subscriber
        """
        self.max_subscribers = max_subscribers
        self.message_buffer_size = message_buffer_size

        # Subscriber storage
        self._subscribers: Dict[str, Subscriber] = {}
        self._subscribers_by_type: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()

        # Event handlers
        self._event_handlers: Dict[str, List[Callable]] = {}

        # Statistics
        self._stats = {
            "total_subscriptions": 0,
            "active_subscriptions": 0,
            "messages_published": 0,
            "messages_delivered": 0,
        }

        # Background tasks
        self._running = False
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        """Start the subscription manager."""
        self._running = True
        logger.info("Subscription Manager started")

    async def stop(self) -> None:
        """Stop the subscription manager."""
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Close all subscriptions
        async with self._lock:
            for subscriber_id in list(self._subscribers.keys()):
                await self._remove_subscriber(subscriber_id)

        logger.info("Subscription Manager stopped")

    async def subscribe(
        self,
        subscription_type: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a new subscription.

        إنشاء اشتراك جديد.

        Returns:
            Subscriber ID
        """
        async with self._lock:
            if len(self._subscribers) >= self.max_subscribers:
                raise Exception("Maximum subscribers reached")

            subscriber_id = str(uuid.uuid4())
            subscriber = Subscriber(
                subscriber_id=subscriber_id,
                subscription_type=subscription_type,
                filters=filters or {},
                queue=asyncio.Queue(maxsize=self.message_buffer_size),
            )

            self._subscribers[subscriber_id] = subscriber

            # Add to type index
            if subscription_type not in self._subscribers_by_type:
                self._subscribers_by_type[subscription_type] = set()
            self._subscribers_by_type[subscription_type].add(subscriber_id)

            self._stats["total_subscriptions"] += 1
            self._stats["active_subscriptions"] += 1

            logger.debug(f"New subscription: {subscriber_id} for {subscription_type}")

            return subscriber_id

    async def unsubscribe(self, subscriber_id: str) -> bool:
        """
        Remove a subscription.

        إلغاء الاشتراك.
        """
        async with self._lock:
            return await self._remove_subscriber(subscriber_id)

    async def _remove_subscriber(self, subscriber_id: str) -> bool:
        """Remove subscriber (must be called with lock)."""
        subscriber = self._subscribers.get(subscriber_id)
        if not subscriber:
            return False

        # Remove from type index
        sub_type = subscriber.subscription_type
        if sub_type in self._subscribers_by_type:
            self._subscribers_by_type[sub_type].discard(subscriber_id)

        del self._subscribers[subscriber_id]
        self._stats["active_subscriptions"] -= 1

        logger.debug(f"Subscription removed: {subscriber_id}")
        return True

    async def subscribe_to_job_status(
        self,
        job_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Subscribe to job status changes.

        الاشتراك في تغييرات حالة الوظيفة.
        """
        subscriber_id = await self.subscribe(
            "jobStatusChanged",
            {"jobId": job_id} if job_id else {},
        )

        try:
            async for message in self._iterate_messages(subscriber_id):
                yield message
        finally:
            await self.unsubscribe(subscriber_id)

    async def subscribe_to_job_progress(
        self,
        job_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Subscribe to job progress updates.

        الاشتراك في تحديثات تقدم الوظيفة.
        """
        subscriber_id = await self.subscribe(
            "jobProgress",
            {"jobId": job_id},
        )

        try:
            async for message in self._iterate_messages(subscriber_id):
                yield message
        finally:
            await self.unsubscribe(subscriber_id)

    async def subscribe_to_worker_status(
        self,
        worker_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Subscribe to worker status changes.

        الاشتراك في تغييرات حالة العامل.
        """
        subscriber_id = await self.subscribe(
            "workerStatusChanged",
            {"workerId": worker_id} if worker_id else {},
        )

        try:
            async for message in self._iterate_messages(subscriber_id):
                yield message
        finally:
            await self.unsubscribe(subscriber_id)

    async def subscribe_to_cluster_metrics(
        self,
        interval: int = 5,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Subscribe to cluster metrics.

        الاشتراك في مقاييس المجموعة.
        """
        subscriber_id = await self.subscribe(
            "clusterMetrics",
            {"interval": interval},
        )

        try:
            async for message in self._iterate_messages(subscriber_id):
                yield message
        finally:
            await self.unsubscribe(subscriber_id)

    async def subscribe_to_alerts(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Subscribe to system alerts.

        الاشتراك في تنبيهات النظام.
        """
        subscriber_id = await self.subscribe("alerts", {})

        try:
            async for message in self._iterate_messages(subscriber_id):
                yield message
        finally:
            await self.unsubscribe(subscriber_id)

    async def _iterate_messages(
        self,
        subscriber_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Iterate over messages for a subscriber."""
        subscriber = self._subscribers.get(subscriber_id)
        if not subscriber:
            return

        while self._running:
            try:
                message = await asyncio.wait_for(
                    subscriber.queue.get(),
                    timeout=30.0,
                )
                subscriber.last_message_at = datetime.now(timezone.utc)
                self._stats["messages_delivered"] += 1
                yield message
            except asyncio.TimeoutError:
                # Send heartbeat
                yield {"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()}

    async def publish(
        self,
        subscription_type: str,
        data: Dict[str, Any],
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Publish a message to subscribers.

        نشر رسالة للمشتركين.

        Returns:
            Number of subscribers who received the message
        """
        subscriber_ids = self._subscribers_by_type.get(subscription_type, set())
        delivered = 0

        for subscriber_id in subscriber_ids:
            subscriber = self._subscribers.get(subscriber_id)
            if not subscriber:
                continue

            # Check filters
            if not self._matches_filters(subscriber.filters, filters or {}, data):
                continue

            try:
                # Non-blocking put
                subscriber.queue.put_nowait(
                    {
                        "type": subscription_type,
                        "data": data,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                delivered += 1
            except asyncio.QueueFull:
                logger.warning(f"Queue full for subscriber {subscriber_id}, " "dropping message")

        self._stats["messages_published"] += 1
        return delivered

    def _matches_filters(
        self,
        subscriber_filters: Dict[str, Any],
        message_filters: Dict[str, Any],
        data: Dict[str, Any],
    ) -> bool:
        """Check if message matches subscriber filters."""
        for key, value in subscriber_filters.items():
            if value is None:
                continue  # No filter on this field

            # Check message filters first
            if key in message_filters:
                if message_filters[key] != value:
                    return False
            # Then check data
            elif key in data:
                if data[key] != value:
                    return False

        return True

    # Event publishing methods
    async def publish_job_status_change(
        self,
        job_id: str,
        status: str,
        job_data: Dict[str, Any],
    ) -> int:
        """Publish job status change event."""
        return await self.publish(
            "jobStatusChanged",
            {
                "jobId": job_id,
                "status": status,
                **job_data,
            },
            {"jobId": job_id},
        )

    async def publish_job_progress(
        self,
        job_id: str,
        progress: float,
        message: Optional[str] = None,
    ) -> int:
        """Publish job progress update."""
        return await self.publish(
            "jobProgress",
            {
                "jobId": job_id,
                "progress": progress,
                "message": message,
            },
            {"jobId": job_id},
        )

    async def publish_worker_status_change(
        self,
        worker_id: str,
        status: str,
        worker_data: Dict[str, Any],
    ) -> int:
        """Publish worker status change event."""
        return await self.publish(
            "workerStatusChanged",
            {
                "workerId": worker_id,
                "status": status,
                **worker_data,
            },
            {"workerId": worker_id},
        )

    async def publish_cluster_metrics(
        self,
        metrics: Dict[str, Any],
    ) -> int:
        """Publish cluster metrics update."""
        return await self.publish("clusterMetrics", metrics)

    async def publish_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Publish system alert."""
        return await self.publish(
            "alerts",
            {
                "alertType": alert_type,
                "severity": severity,
                "message": message,
                "details": details or {},
            },
        )

    async def get_active_subscriptions(self) -> List[Dict[str, Any]]:
        """Get list of active subscriptions."""
        return [subscriber.to_dict() for subscriber in self._subscribers.values()]

    async def get_subscription_stats(self) -> Dict[str, Any]:
        """Get subscription statistics."""
        type_counts = {sub_type: len(subscribers) for sub_type, subscribers in self._subscribers_by_type.items()}

        return {
            **self._stats,
            "subscriptions_by_type": type_counts,
        }


class WebSocketHandler:
    """
    WebSocket handler for GraphQL subscriptions.

    معالج WebSocket للاشتراكات.
    """

    def __init__(
        self,
        subscription_manager: SubscriptionManager,
    ):
        """
        Initialize WebSocket handler.

        Args:
            subscription_manager: Subscription manager instance
        """
        self.subscription_manager = subscription_manager
        self._connections: Dict[str, Any] = {}

    async def handle_connection(
        self,
        websocket: Any,
        connection_id: str,
    ) -> None:
        """Handle a new WebSocket connection."""
        self._connections[connection_id] = {
            "websocket": websocket,
            "subscriptions": [],
            "connected_at": datetime.now(timezone.utc),
        }

        try:
            async for message in websocket:
                await self._handle_message(connection_id, message)
        finally:
            await self._cleanup_connection(connection_id)

    async def _handle_message(
        self,
        connection_id: str,
        message: str,
    ) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "connection_init":
                await self._send(connection_id, {"type": "connection_ack"})

            elif msg_type == "subscribe":
                await self._handle_subscribe(connection_id, data)

            elif msg_type == "unsubscribe":
                await self._handle_unsubscribe(connection_id, data)

            elif msg_type == "ping":
                await self._send(connection_id, {"type": "pong"})

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from {connection_id}")

    async def _handle_subscribe(
        self,
        connection_id: str,
        data: Dict[str, Any],
    ) -> None:
        """Handle subscription request."""
        subscription_id = data.get("id")
        query = data.get("payload", {}).get("query", "")
        variables = data.get("payload", {}).get("variables", {})

        # Extract subscription type from query
        subscription_type = self._extract_subscription_type(query)

        if not subscription_type:
            await self._send(
                connection_id,
                {
                    "type": "error",
                    "id": subscription_id,
                    "payload": {"message": "Invalid subscription query"},
                },
            )
            return

        # Create subscription
        subscriber_id = await self.subscription_manager.subscribe(
            subscription_type,
            variables,
        )

        # Store subscription mapping
        conn = self._connections.get(connection_id)
        if conn:
            conn["subscriptions"].append(
                {
                    "id": subscription_id,
                    "subscriber_id": subscriber_id,
                    "type": subscription_type,
                }
            )

        # Start streaming
        asyncio.create_task(
            self._stream_subscription(
                connection_id,
                subscription_id,
                subscriber_id,
            )
        )

    async def _handle_unsubscribe(
        self,
        connection_id: str,
        data: Dict[str, Any],
    ) -> None:
        """Handle unsubscribe request."""
        subscription_id = data.get("id")

        conn = self._connections.get(connection_id)
        if not conn:
            return

        for sub in conn["subscriptions"]:
            if sub["id"] == subscription_id:
                await self.subscription_manager.unsubscribe(sub["subscriber_id"])
                conn["subscriptions"].remove(sub)
                break

        await self._send(
            connection_id,
            {
                "type": "complete",
                "id": subscription_id,
            },
        )

    async def _stream_subscription(
        self,
        connection_id: str,
        subscription_id: str,
        subscriber_id: str,
    ) -> None:
        """Stream subscription data to client."""
        subscriber = self.subscription_manager._subscribers.get(subscriber_id)
        if not subscriber:
            return

        while subscriber_id in self.subscription_manager._subscribers:
            try:
                message = await asyncio.wait_for(
                    subscriber.queue.get(),
                    timeout=30.0,
                )

                await self._send(
                    connection_id,
                    {
                        "type": "next",
                        "id": subscription_id,
                        "payload": {"data": message},
                    },
                )

            except asyncio.TimeoutError:
                # Send keepalive
                await self._send(
                    connection_id,
                    {
                        "type": "ping",
                    },
                )

    async def _send(
        self,
        connection_id: str,
        data: Dict[str, Any],
    ) -> None:
        """Send message to WebSocket client."""
        conn = self._connections.get(connection_id)
        if conn and conn.get("websocket"):
            try:
                await conn["websocket"].send(json.dumps(data))
            except Exception as e:
                logger.warning(f"Failed to send to {connection_id}: {e}")

    async def _cleanup_connection(self, connection_id: str) -> None:
        """Clean up disconnected connection."""
        conn = self._connections.get(connection_id)
        if not conn:
            return

        # Unsubscribe all
        for sub in conn["subscriptions"]:
            await self.subscription_manager.unsubscribe(sub["subscriber_id"])

        del self._connections[connection_id]
        logger.debug(f"Connection cleaned up: {connection_id}")

    def _extract_subscription_type(self, query: str) -> Optional[str]:
        """Extract subscription type from GraphQL query."""
        # Simple extraction - in production, use proper GraphQL parser
        for sub_type in [
            "jobStatusChanged",
            "jobProgress",
            "workerStatusChanged",
            "clusterMetrics",
            "alerts",
        ]:
            if sub_type in query:
                return sub_type
        return None
