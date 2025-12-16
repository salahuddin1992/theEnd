"""
WebSocket Manager - مدير WebSocket
==================================

إدارة اتصالات WebSocket للتحديثات الفورية:
- اتصالات متعددة
- المصادقة
- الاشتراك في الأحداث
- إرسال الرسائل
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Set, List, Any, Callable
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from distributed_cluster.security.auth import AuthManager, Permission

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """أنواع الرسائل."""
    # Client -> Server
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"

    # Server -> Client
    EVENT = "event"
    ACK = "ack"
    ERROR = "error"
    PONG = "pong"


class EventCategory(str, Enum):
    """فئات الأحداث."""
    JOB = "job"
    WORKER = "worker"
    CLUSTER = "cluster"
    METRICS = "metrics"
    LOGS = "logs"


@dataclass
class ConnectionInfo:
    """معلومات الاتصال."""
    connection_id: str
    websocket: WebSocket
    user_id: Optional[str] = None
    worker_id: Optional[str] = None
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_ping: datetime = field(default_factory=datetime.utcnow)
    subscriptions: Set[str] = field(default_factory=set)  # category:filter patterns
    permissions: Set[Permission] = field(default_factory=set)


class WebSocketManager:
    """
    مدير اتصالات WebSocket.

    الميزات:
    - إدارة الاتصالات المتعددة
    - نظام اشتراك مرن
    - مصادقة JWT
    - Heartbeat/Ping-Pong
    """

    def __init__(
        self,
        auth_manager: Optional[AuthManager] = None,
        ping_interval: int = 30,
        ping_timeout: int = 10,
    ):
        self.auth_manager = auth_manager
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        # Active connections
        self._connections: Dict[str, ConnectionInfo] = {}

        # Subscription index: category -> set of connection_ids
        self._subscriptions: Dict[str, Set[str]] = {}

        # Job-specific subscriptions: job_id -> set of connection_ids
        self._job_subscriptions: Dict[str, Set[str]] = {}

        # Worker-specific subscriptions: worker_id -> set of connection_ids
        self._worker_subscriptions: Dict[str, Set[str]] = {}

        # Background tasks
        self._ping_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """بدء المدير."""
        self._ping_task = asyncio.create_task(self._ping_loop())
        logger.info("WebSocket manager started")

    async def stop(self) -> None:
        """إيقاف المدير."""
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        for conn_id in list(self._connections.keys()):
            await self.disconnect(conn_id)

        logger.info("WebSocket manager stopped")

    async def connect(
        self,
        websocket: WebSocket,
        token: Optional[str] = None,
    ) -> Optional[ConnectionInfo]:
        """
        قبول اتصال WebSocket جديد.

        Args:
            websocket: اتصال WebSocket
            token: JWT token للمصادقة (اختياري)

        Returns:
            ConnectionInfo إذا نجح، None إذا فشل
        """
        # Accept connection
        await websocket.accept()

        # Generate connection ID
        conn_id = f"ws-{uuid.uuid4().hex[:12]}"

        # Authenticate if token provided
        user_id = None
        worker_id = None
        permissions: Set[Permission] = set()

        if token and self.auth_manager:
            payload = self.auth_manager.verify_token(token)
            if payload:
                user_id = payload.subject
                worker_id = payload.worker_id
                permissions = payload.permissions

        # Create connection info
        conn_info = ConnectionInfo(
            connection_id=conn_id,
            websocket=websocket,
            user_id=user_id,
            worker_id=worker_id,
            permissions=permissions,
        )

        self._connections[conn_id] = conn_info

        # Send acknowledgment
        await self._send(conn_info, {
            "type": MessageType.ACK.value,
            "connection_id": conn_id,
            "authenticated": user_id is not None,
        })

        logger.info(f"WebSocket connected: {conn_id}, user={user_id}")

        return conn_info

    async def disconnect(self, connection_id: str) -> None:
        """قطع اتصال WebSocket."""
        conn_info = self._connections.pop(connection_id, None)
        if not conn_info:
            return

        # Remove from subscriptions
        for category in list(self._subscriptions.keys()):
            self._subscriptions[category].discard(connection_id)

        for job_id in list(self._job_subscriptions.keys()):
            self._job_subscriptions[job_id].discard(connection_id)

        for worker_id in list(self._worker_subscriptions.keys()):
            self._worker_subscriptions[worker_id].discard(connection_id)

        # Close connection
        try:
            if conn_info.websocket.client_state == WebSocketState.CONNECTED:
                await conn_info.websocket.close()
        except Exception:
            pass

        logger.info(f"WebSocket disconnected: {connection_id}")

    async def handle_message(
        self,
        connection_id: str,
        message: Dict[str, Any],
    ) -> None:
        """
        معالجة رسالة واردة.

        Args:
            connection_id: معرف الاتصال
            message: الرسالة
        """
        conn_info = self._connections.get(connection_id)
        if not conn_info:
            return

        msg_type = message.get("type")

        if msg_type == MessageType.SUBSCRIBE.value:
            await self._handle_subscribe(conn_info, message)

        elif msg_type == MessageType.UNSUBSCRIBE.value:
            await self._handle_unsubscribe(conn_info, message)

        elif msg_type == MessageType.PING.value:
            conn_info.last_ping = datetime.utcnow()
            await self._send(conn_info, {"type": MessageType.PONG.value})

    async def _handle_subscribe(
        self,
        conn_info: ConnectionInfo,
        message: Dict[str, Any],
    ) -> None:
        """معالجة طلب اشتراك."""
        category = message.get("category")
        filter_id = message.get("filter")  # job_id or worker_id

        if not category:
            await self._send(conn_info, {
                "type": MessageType.ERROR.value,
                "error": "category is required",
            })
            return

        # Check permissions
        if category == EventCategory.METRICS.value:
            if Permission.VIEW_METRICS not in conn_info.permissions and self.auth_manager:
                await self._send(conn_info, {
                    "type": MessageType.ERROR.value,
                    "error": "Permission denied for metrics",
                })
                return

        # Add to subscriptions
        subscription_key = f"{category}:{filter_id or '*'}"
        conn_info.subscriptions.add(subscription_key)

        # Update index
        if category not in self._subscriptions:
            self._subscriptions[category] = set()
        self._subscriptions[category].add(conn_info.connection_id)

        # Specific subscriptions
        if category == EventCategory.JOB.value and filter_id:
            if filter_id not in self._job_subscriptions:
                self._job_subscriptions[filter_id] = set()
            self._job_subscriptions[filter_id].add(conn_info.connection_id)

        elif category == EventCategory.WORKER.value and filter_id:
            if filter_id not in self._worker_subscriptions:
                self._worker_subscriptions[filter_id] = set()
            self._worker_subscriptions[filter_id].add(conn_info.connection_id)

        await self._send(conn_info, {
            "type": MessageType.ACK.value,
            "action": "subscribed",
            "subscription": subscription_key,
        })

        logger.debug(f"Connection {conn_info.connection_id} subscribed to {subscription_key}")

    async def _handle_unsubscribe(
        self,
        conn_info: ConnectionInfo,
        message: Dict[str, Any],
    ) -> None:
        """معالجة طلب إلغاء اشتراك."""
        category = message.get("category")
        filter_id = message.get("filter")

        subscription_key = f"{category}:{filter_id or '*'}"
        conn_info.subscriptions.discard(subscription_key)

        # Update indexes
        if category in self._subscriptions:
            self._subscriptions[category].discard(conn_info.connection_id)

        if filter_id:
            if category == EventCategory.JOB.value and filter_id in self._job_subscriptions:
                self._job_subscriptions[filter_id].discard(conn_info.connection_id)
            elif category == EventCategory.WORKER.value and filter_id in self._worker_subscriptions:
                self._worker_subscriptions[filter_id].discard(conn_info.connection_id)

        await self._send(conn_info, {
            "type": MessageType.ACK.value,
            "action": "unsubscribed",
            "subscription": subscription_key,
        })

    async def broadcast(
        self,
        category: str,
        event_type: str,
        data: Dict[str, Any],
        job_id: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> int:
        """
        بث حدث للمشتركين.

        Args:
            category: فئة الحدث
            event_type: نوع الحدث
            data: بيانات الحدث
            job_id: معرف المهمة (اختياري)
            worker_id: معرف العامل (اختياري)

        Returns:
            عدد المشتركين الذين استلموا الحدث
        """
        message = {
            "type": MessageType.EVENT.value,
            "category": category,
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if job_id:
            message["job_id"] = job_id
        if worker_id:
            message["worker_id"] = worker_id

        # Find subscribers
        subscribers: Set[str] = set()

        # Category subscribers (wildcard)
        if category in self._subscriptions:
            subscribers.update(self._subscriptions[category])

        # Specific job subscribers
        if job_id and job_id in self._job_subscriptions:
            subscribers.update(self._job_subscriptions[job_id])

        # Specific worker subscribers
        if worker_id and worker_id in self._worker_subscriptions:
            subscribers.update(self._worker_subscriptions[worker_id])

        # Send to all subscribers
        sent_count = 0
        for conn_id in subscribers:
            conn_info = self._connections.get(conn_id)
            if conn_info:
                try:
                    await self._send(conn_info, message)
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send to {conn_id}: {e}")
                    # Schedule disconnect
                    asyncio.create_task(self.disconnect(conn_id))

        return sent_count

    async def send_to_connection(
        self,
        connection_id: str,
        message: Dict[str, Any],
    ) -> bool:
        """
        إرسال رسالة لاتصال محدد.

        Args:
            connection_id: معرف الاتصال
            message: الرسالة

        Returns:
            True إذا نجح الإرسال
        """
        conn_info = self._connections.get(connection_id)
        if not conn_info:
            return False

        try:
            await self._send(conn_info, message)
            return True
        except Exception:
            return False

    async def _send(self, conn_info: ConnectionInfo, message: Dict[str, Any]) -> None:
        """إرسال رسالة."""
        if conn_info.websocket.client_state != WebSocketState.CONNECTED:
            raise RuntimeError("WebSocket not connected")

        await conn_info.websocket.send_json(message)

    async def _ping_loop(self) -> None:
        """حلقة Ping للحفاظ على الاتصالات."""
        while True:
            try:
                await asyncio.sleep(self.ping_interval)

                now = datetime.utcnow()
                disconnected = []

                for conn_id, conn_info in self._connections.items():
                    # Check if connection timed out
                    elapsed = (now - conn_info.last_ping).total_seconds()
                    if elapsed > self.ping_interval + self.ping_timeout:
                        disconnected.append(conn_id)
                        continue

                    # Send ping
                    try:
                        await self._send(conn_info, {"type": MessageType.PING.value})
                    except Exception:
                        disconnected.append(conn_id)

                # Disconnect timed out connections
                for conn_id in disconnected:
                    await self.disconnect(conn_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ping loop error: {e}")

    @property
    def connection_count(self) -> int:
        """عدد الاتصالات النشطة."""
        return len(self._connections)

    def get_connection_info(self, connection_id: str) -> Optional[ConnectionInfo]:
        """الحصول على معلومات اتصال."""
        return self._connections.get(connection_id)

    def get_all_connections(self) -> List[ConnectionInfo]:
        """الحصول على كل الاتصالات."""
        return list(self._connections.values())


# FastAPI WebSocket endpoint helper
async def websocket_endpoint(
    websocket: WebSocket,
    manager: WebSocketManager,
    token: Optional[str] = None,
) -> None:
    """
    FastAPI WebSocket endpoint helper.

    Usage:
        @app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket, token: str = Query(None)):
            await websocket_endpoint(websocket, manager, token)
    """
    conn_info = await manager.connect(websocket, token)
    if not conn_info:
        return

    try:
        while True:
            data = await websocket.receive_json()
            await manager.handle_message(conn_info.connection_id, data)
    except WebSocketDisconnect:
        await manager.disconnect(conn_info.connection_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(conn_info.connection_id)
