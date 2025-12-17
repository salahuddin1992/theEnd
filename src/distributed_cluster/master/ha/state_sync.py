"""
State Synchronization - مزامنة الحالة
======================================

مزامنة الحالة بين Masters لضمان:
- كل Master لديه نفس معلومات Workers
- كل Master لديه نفس قائمة Jobs
- التبديل السلس عند فشل القائد
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional, Callable, Any
import logging

import httpx

if TYPE_CHECKING:
    from distributed_cluster.master.state import ClusterState

logger = logging.getLogger(__name__)


class SyncMessageType(str, Enum):
    """أنواع رسائل المزامنة"""
    FULL_SYNC = "full_sync"           # مزامنة كاملة
    INCREMENTAL = "incremental"        # تحديث جزئي
    WORKER_UPDATE = "worker_update"    # تحديث worker
    JOB_UPDATE = "job_update"          # تحديث job
    EVENT = "event"                    # حدث جديد


@dataclass
class SyncMessage:
    """رسالة مزامنة"""
    type: SyncMessageType
    source_master_id: str
    timestamp: datetime
    sequence: int  # رقم تسلسلي للترتيب
    data: dict

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "source_master_id": self.source_master_id,
            "timestamp": self.timestamp.isoformat(),
            "sequence": self.sequence,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SyncMessage":
        return cls(
            type=SyncMessageType(d["type"]),
            source_master_id=d["source_master_id"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            sequence=d["sequence"],
            data=d["data"],
        )


@dataclass
class SyncConfig:
    """إعدادات المزامنة"""
    master_id: str = ""

    # فترة المزامنة الكاملة
    full_sync_interval_seconds: float = 60.0

    # فترة إرسال التحديثات الجزئية
    incremental_sync_interval_seconds: float = 1.0

    # الحد الأقصى للتحديثات المخزنة
    max_pending_updates: int = 1000

    # HTTP timeout
    http_timeout_seconds: float = 10.0

    # قائمة Masters الأخرى
    peers: list[str] = field(default_factory=list)


class StateSync:
    """
    مزامنة الحالة بين Masters

    يعمل في وضعين:
    1. كقائد (Leader): يرسل التحديثات للـ Followers
    2. كتابع (Follower): يستلم ويطبق التحديثات من القائد
    """

    def __init__(
        self,
        config: SyncConfig,
        state: "ClusterState",
        is_leader_func: Callable[[], bool],
    ):
        self.config = config
        self.state = state
        self._is_leader = is_leader_func

        # قائمة التحديثات المعلقة (للإرسال)
        self._pending_updates: list[SyncMessage] = []
        self._sequence = 0
        self._lock = asyncio.Lock()

        # التحكم
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._client: Optional[httpx.AsyncClient] = None

        # آخر مزامنة كاملة
        self._last_full_sync: Optional[datetime] = None
        self._last_received_sequence: dict[str, int] = {}

    async def start(self) -> None:
        """بدء المزامنة"""
        logger.info("Starting State Synchronization...")

        self._client = httpx.AsyncClient(
            timeout=self.config.http_timeout_seconds,
        )

        self._running = True

        self._tasks = [
            asyncio.create_task(self._sync_loop()),
            asyncio.create_task(self._full_sync_loop()),
        ]

        logger.info("State Synchronization started")

    async def stop(self) -> None:
        """إيقاف المزامنة"""
        logger.info("Stopping State Synchronization...")

        self._running = False

        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._client:
            await self._client.aclose()

        logger.info("State Synchronization stopped")

    def queue_update(self, update_type: SyncMessageType, data: dict) -> None:
        """إضافة تحديث للإرسال"""
        if not self._is_leader():
            return  # فقط القائد يرسل تحديثات

        self._sequence += 1
        msg = SyncMessage(
            type=update_type,
            source_master_id=self.config.master_id,
            timestamp=datetime.utcnow(),
            sequence=self._sequence,
            data=data,
        )

        self._pending_updates.append(msg)

        # إزالة التحديثات القديمة إذا تجاوزنا الحد
        if len(self._pending_updates) > self.config.max_pending_updates:
            self._pending_updates = self._pending_updates[-self.config.max_pending_updates:]

    def queue_worker_update(self, worker_id: str, action: str, data: dict) -> None:
        """إضافة تحديث worker"""
        self.queue_update(
            SyncMessageType.WORKER_UPDATE,
            {"worker_id": worker_id, "action": action, **data},
        )

    def queue_job_update(self, job_id: str, action: str, data: dict) -> None:
        """إضافة تحديث job"""
        self.queue_update(
            SyncMessageType.JOB_UPDATE,
            {"job_id": job_id, "action": action, **data},
        )

    async def _sync_loop(self) -> None:
        """حلقة إرسال التحديثات الجزئية"""
        while self._running:
            try:
                await asyncio.sleep(self.config.incremental_sync_interval_seconds)

                if not self._is_leader():
                    continue

                if not self._pending_updates:
                    continue

                # إرسال التحديثات للـ peers
                async with self._lock:
                    updates_to_send = self._pending_updates.copy()
                    self._pending_updates.clear()

                await self._send_updates(updates_to_send)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync loop error: {e}")

    async def _full_sync_loop(self) -> None:
        """حلقة المزامنة الكاملة"""
        while self._running:
            try:
                await asyncio.sleep(self.config.full_sync_interval_seconds)

                if self._is_leader():
                    # كقائد: أرسل المزامنة الكاملة
                    await self._send_full_sync()
                else:
                    # كتابع: اطلب المزامنة الكاملة
                    await self._request_full_sync()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Full sync loop error: {e}")

    async def _send_updates(self, updates: list[SyncMessage]) -> None:
        """إرسال التحديثات للـ peers"""
        for peer_addr in self.config.peers:
            try:
                url = f"http://{peer_addr}/ha/sync/updates"
                await self._client.post(
                    url,
                    json={"updates": [u.to_dict() for u in updates]},
                    timeout=5.0,
                )
            except Exception as e:
                logger.debug(f"Failed to send updates to {peer_addr}: {e}")

    async def _send_full_sync(self) -> None:
        """إرسال مزامنة كاملة"""
        # جمع الحالة الكاملة
        full_state = self._get_full_state()

        msg = SyncMessage(
            type=SyncMessageType.FULL_SYNC,
            source_master_id=self.config.master_id,
            timestamp=datetime.utcnow(),
            sequence=self._sequence,
            data=full_state,
        )

        for peer_addr in self.config.peers:
            try:
                url = f"http://{peer_addr}/ha/sync/full"
                await self._client.post(
                    url,
                    json=msg.to_dict(),
                    timeout=30.0,  # وقت أطول للمزامنة الكاملة
                )
                logger.debug(f"Full sync sent to {peer_addr}")
            except Exception as e:
                logger.debug(f"Failed to send full sync to {peer_addr}: {e}")

    async def _request_full_sync(self) -> None:
        """طلب مزامنة كاملة من القائد"""
        # هذا يحدث عادة عند بدء التشغيل أو بعد فقدان الاتصال
        pass

    def _get_full_state(self) -> dict:
        """الحصول على الحالة الكاملة للمزامنة"""
        workers = self.state.get_all_workers()
        jobs = self.state.get_all_jobs()

        return {
            "workers": [w.to_dict() for w in workers],
            "jobs": [j.to_dict() for j in jobs],
            "stats": self.state.get_stats(),
        }

    # ==================== API Handlers ====================

    async def handle_updates(self, updates: list[dict]) -> dict:
        """معالجة تحديثات من القائد"""
        if self._is_leader():
            return {"status": "ignored", "reason": "I am the leader"}

        applied = 0
        for update_dict in updates:
            try:
                msg = SyncMessage.from_dict(update_dict)

                # تجاهل التحديثات القديمة
                last_seq = self._last_received_sequence.get(msg.source_master_id, 0)
                if msg.sequence <= last_seq:
                    continue

                await self._apply_update(msg)
                self._last_received_sequence[msg.source_master_id] = msg.sequence
                applied += 1

            except Exception as e:
                logger.error(f"Error applying update: {e}")

        return {"status": "ok", "applied": applied}

    async def handle_full_sync(self, sync_data: dict) -> dict:
        """معالجة مزامنة كاملة من القائد"""
        if self._is_leader():
            return {"status": "ignored", "reason": "I am the leader"}

        try:
            msg = SyncMessage.from_dict(sync_data)
            await self._apply_full_sync(msg.data)
            self._last_full_sync = datetime.utcnow()
            self._last_received_sequence[msg.source_master_id] = msg.sequence

            return {"status": "ok"}

        except Exception as e:
            logger.error(f"Error applying full sync: {e}")
            return {"status": "error", "message": str(e)}

    async def _apply_update(self, msg: SyncMessage) -> None:
        """تطبيق تحديث على الحالة المحلية"""
        if msg.type == SyncMessageType.WORKER_UPDATE:
            await self._apply_worker_update(msg.data)
        elif msg.type == SyncMessageType.JOB_UPDATE:
            await self._apply_job_update(msg.data)
        elif msg.type == SyncMessageType.EVENT:
            pass  # الأحداث للمعلومات فقط

    async def _apply_worker_update(self, data: dict) -> None:
        """تطبيق تحديث worker"""
        action = data.get("action")
        worker_id = data.get("worker_id")

        if action == "registered":
            # إضافة worker جديد
            from distributed_cluster.models.worker import WorkerRegistration
            from distributed_cluster.models.resources import ResourceSpec

            reg_data = data.get("registration", {})
            res_data = reg_data.get("total_resources", {})

            registration = WorkerRegistration(
                hostname=reg_data.get("hostname", ""),
                ip_address=reg_data.get("ip_address", ""),
                port=reg_data.get("port", 0),
                total_resources=ResourceSpec(
                    cpu_cores=res_data.get("cpu_cores", 1),
                    memory_mb=res_data.get("memory_mb", 512),
                    gpu_count=res_data.get("gpu_count", 0),
                ),
                tags=reg_data.get("tags", []),
            )
            self.state.register_worker(registration)

        elif action == "removed":
            self.state.remove_worker(worker_id)

        elif action == "heartbeat":
            from distributed_cluster.models.resources import ResourceUsage
            usage_data = data.get("usage", {})
            usage = ResourceUsage(
                cpu_percent=usage_data.get("cpu_percent", 0),
                memory_used_mb=usage_data.get("memory_used_mb", 0),
                memory_total_mb=usage_data.get("memory_total_mb", 0),
                memory_percent=usage_data.get("memory_percent", 0),
            )
            self.state.update_worker_heartbeat(worker_id, usage)

    async def _apply_job_update(self, data: dict) -> None:
        """تطبيق تحديث job"""
        action = data.get("action")
        job_id = data.get("job_id")

        if action == "submitted":
            from distributed_cluster.models.job import JobSubmission
            from distributed_cluster.models.resources import ResourceSpec

            sub_data = data.get("submission", {})
            res_data = sub_data.get("resources", {})

            submission = JobSubmission(
                command=sub_data.get("command", ""),
                args=sub_data.get("args", []),
                resources=ResourceSpec(
                    cpu_cores=res_data.get("cpu_cores", 1),
                    memory_mb=res_data.get("memory_mb", 512),
                ),
            )
            self.state.submit_job(submission)

        elif action == "scheduled":
            worker_id = data.get("worker_id")
            lease_id = data.get("lease_id")
            self.state.schedule_job(job_id, worker_id, lease_id)

        elif action == "started":
            worker_id = data.get("worker_id")
            self.state.start_job(job_id, worker_id)

        elif action == "completed":
            from distributed_cluster.models.job import JobResult
            worker_id = data.get("worker_id")
            result_data = data.get("result", {})
            result = JobResult(
                exit_code=result_data.get("exit_code", 0),
                stdout=result_data.get("stdout", ""),
                stderr=result_data.get("stderr", ""),
            )
            self.state.complete_job(job_id, worker_id, result)

        elif action == "cancelled":
            self.state.cancel_job(job_id)

    async def _apply_full_sync(self, data: dict) -> None:
        """تطبيق مزامنة كاملة"""
        logger.info("Applying full state sync from leader")

        # هذه عملية حساسة - نحتاج لاستبدال الحالة بالكامل
        # في الإنتاج، قد نحتاج لمنطق أكثر تعقيداً

        # مزامنة Workers
        for worker_data in data.get("workers", []):
            try:
                await self._apply_worker_update({
                    "action": "registered",
                    "worker_id": worker_data.get("worker_id"),
                    "registration": worker_data,
                })
            except Exception as e:
                logger.error(f"Error syncing worker: {e}")

        # مزامنة Jobs
        for job_data in data.get("jobs", []):
            try:
                # لا نعيد إرسال jobs موجودة
                existing = self.state.get_job(job_data.get("job_id"))
                if not existing:
                    await self._apply_job_update({
                        "action": "submitted",
                        "job_id": job_data.get("job_id"),
                        "submission": job_data,
                    })
            except Exception as e:
                logger.error(f"Error syncing job: {e}")

        logger.info("Full state sync completed")

    def get_sync_status(self) -> dict:
        """الحصول على حالة المزامنة"""
        return {
            "is_leader": self._is_leader(),
            "sequence": self._sequence,
            "pending_updates": len(self._pending_updates),
            "last_full_sync": self._last_full_sync.isoformat() if self._last_full_sync else None,
            "peers": self.config.peers,
        }
