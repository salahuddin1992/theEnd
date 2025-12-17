"""
HA Health Monitor - مراقبة صحة الـ Masters
==========================================

مراقبة صحة كل Masters وإدارة التبديل التلقائي (Failover).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable, Any
import logging

import httpx

logger = logging.getLogger(__name__)


class MasterHealthStatus(str, Enum):
    """حالة صحة Master"""
    HEALTHY = "healthy"        # يعمل بشكل طبيعي
    DEGRADED = "degraded"      # يعمل مع مشاكل
    UNHEALTHY = "unhealthy"    # لا يعمل
    UNKNOWN = "unknown"        # غير معروف


@dataclass
class MasterHealth:
    """معلومات صحة Master"""
    master_id: str
    address: str
    port: int
    status: MasterHealthStatus = MasterHealthStatus.UNKNOWN
    last_check: Optional[datetime] = None
    response_time_ms: float = 0.0
    consecutive_failures: int = 0
    error_message: Optional[str] = None

    # مقاييس إضافية
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    active_connections: int = 0
    jobs_count: int = 0
    workers_count: int = 0

    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.port}"

    def to_dict(self) -> dict:
        return {
            "master_id": self.master_id,
            "address": self.address,
            "port": self.port,
            "status": self.status.value,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "response_time_ms": self.response_time_ms,
            "consecutive_failures": self.consecutive_failures,
            "error_message": self.error_message,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "active_connections": self.active_connections,
            "jobs_count": self.jobs_count,
            "workers_count": self.workers_count,
        }


@dataclass
class HealthConfig:
    """إعدادات مراقبة الصحة"""
    master_id: str = ""
    address: str = "0.0.0.0"
    port: int = 8080

    # قائمة Masters الأخرى
    peers: list[str] = field(default_factory=list)

    # فترات الفحص
    check_interval_seconds: float = 5.0
    http_timeout_seconds: float = 3.0

    # عتبات الحالة
    unhealthy_threshold: int = 3      # عدد الفشل قبل اعتباره غير صحي
    degraded_response_ms: float = 1000.0  # زمن استجابة للاعتبار متدهور

    # Failover
    auto_failover_enabled: bool = True
    failover_delay_seconds: float = 5.0  # انتظار قبل التبديل


class HAHealthMonitor:
    """
    مراقبة صحة Masters

    المهام:
    1. فحص صحة كل Masters دورياً
    2. تتبع زمن الاستجابة والأخطاء
    3. تحفيز التبديل التلقائي عند الحاجة
    """

    def __init__(
        self,
        config: HealthConfig,
        on_master_unhealthy: Optional[Callable[[str], Any]] = None,
        on_master_recovered: Optional[Callable[[str], Any]] = None,
        trigger_election: Optional[Callable[[], Any]] = None,
    ):
        self.config = config
        self._on_master_unhealthy = on_master_unhealthy
        self._on_master_recovered = on_master_recovered
        self._trigger_election = trigger_election

        # حالة الـ Masters
        self._masters: dict[str, MasterHealth] = {}
        self._self_health = MasterHealth(
            master_id=config.master_id,
            address=config.address,
            port=config.port,
            status=MasterHealthStatus.HEALTHY,
        )

        # التحكم
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def masters(self) -> dict[str, MasterHealth]:
        """قائمة صحة كل Masters"""
        return self._masters.copy()

    @property
    def self_health(self) -> MasterHealth:
        """صحة هذا الـ Master"""
        return self._self_health

    async def start(self) -> None:
        """بدء المراقبة"""
        logger.info("Starting HA Health Monitor...")

        self._client = httpx.AsyncClient(
            timeout=self.config.http_timeout_seconds,
        )

        # تهيئة قائمة Masters
        for peer_addr in self.config.peers:
            try:
                if ":" in peer_addr:
                    host, port = peer_addr.rsplit(":", 1)
                    port = int(port)
                else:
                    host = peer_addr
                    port = 8080

                peer_id = f"{host}:{port}"
                self._masters[peer_id] = MasterHealth(
                    master_id=peer_id,
                    address=host,
                    port=port,
                )
            except Exception as e:
                logger.warning(f"Invalid peer address {peer_addr}: {e}")

        self._running = True

        self._tasks = [
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self._self_health_loop()),
        ]

        logger.info(f"HA Health Monitor started, monitoring {len(self._masters)} peers")

    async def stop(self) -> None:
        """إيقاف المراقبة"""
        logger.info("Stopping HA Health Monitor...")

        self._running = False

        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._client:
            await self._client.aclose()

        logger.info("HA Health Monitor stopped")

    async def _health_check_loop(self) -> None:
        """حلقة فحص صحة الـ peers"""
        while self._running:
            try:
                await asyncio.sleep(self.config.check_interval_seconds)

                # فحص كل peer
                tasks = [
                    self._check_master_health(master)
                    for master in self._masters.values()
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")

    async def _self_health_loop(self) -> None:
        """تحديث صحة هذا الـ Master"""
        while self._running:
            try:
                await asyncio.sleep(self.config.check_interval_seconds)

                # تحديث مقاييس هذا الـ Master
                import psutil
                self._self_health.cpu_percent = psutil.cpu_percent()
                self._self_health.memory_percent = psutil.virtual_memory().percent
                self._self_health.last_check = datetime.utcnow()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Self health loop error: {e}")

    async def _check_master_health(self, master: MasterHealth) -> None:
        """فحص صحة master معين"""
        start_time = datetime.utcnow()
        old_status = master.status

        try:
            resp = await self._client.get(
                f"{master.url}/health",
                timeout=self.config.http_timeout_seconds,
            )

            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            master.response_time_ms = response_time
            master.last_check = datetime.utcnow()
            master.consecutive_failures = 0
            master.error_message = None

            if resp.status_code == 200:
                # فحص زمن الاستجابة
                if response_time > self.config.degraded_response_ms:
                    master.status = MasterHealthStatus.DEGRADED
                else:
                    master.status = MasterHealthStatus.HEALTHY

                # محاولة الحصول على مقاييس إضافية
                try:
                    stats_resp = await self._client.get(
                        f"{master.url}/stats",
                        timeout=2.0,
                    )
                    if stats_resp.status_code == 200:
                        stats = stats_resp.json()
                        master.jobs_count = stats.get("total_jobs", 0)
                        master.workers_count = stats.get("total_workers", 0)
                except Exception:
                    pass

            else:
                master.status = MasterHealthStatus.DEGRADED
                master.error_message = f"HTTP {resp.status_code}"

        except httpx.TimeoutException:
            master.consecutive_failures += 1
            master.error_message = "Timeout"
            master.last_check = datetime.utcnow()

            if master.consecutive_failures >= self.config.unhealthy_threshold:
                master.status = MasterHealthStatus.UNHEALTHY

        except Exception as e:
            master.consecutive_failures += 1
            master.error_message = str(e)
            master.last_check = datetime.utcnow()

            if master.consecutive_failures >= self.config.unhealthy_threshold:
                master.status = MasterHealthStatus.UNHEALTHY

        # معالجة تغيير الحالة
        if old_status != master.status:
            await self._handle_status_change(master, old_status)

    async def _handle_status_change(
        self,
        master: MasterHealth,
        old_status: MasterHealthStatus,
    ) -> None:
        """معالجة تغيير حالة master"""
        logger.info(
            f"Master {master.master_id} status changed: "
            f"{old_status.value} -> {master.status.value}"
        )

        if master.status == MasterHealthStatus.UNHEALTHY:
            # Master أصبح غير صحي
            if self._on_master_unhealthy:
                try:
                    result = self._on_master_unhealthy(master.master_id)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"on_master_unhealthy callback error: {e}")

            # تحفيز انتخاب جديد إذا كان القائد
            if self.config.auto_failover_enabled and self._trigger_election:
                try:
                    result = self._trigger_election()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"trigger_election error: {e}")

        elif (
            old_status == MasterHealthStatus.UNHEALTHY
            and master.status in (MasterHealthStatus.HEALTHY, MasterHealthStatus.DEGRADED)
        ):
            # Master تعافى
            if self._on_master_recovered:
                try:
                    result = self._on_master_recovered(master.master_id)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"on_master_recovered callback error: {e}")

    def update_self_metrics(
        self,
        jobs_count: int = 0,
        workers_count: int = 0,
        active_connections: int = 0,
    ) -> None:
        """تحديث مقاييس هذا الـ Master"""
        self._self_health.jobs_count = jobs_count
        self._self_health.workers_count = workers_count
        self._self_health.active_connections = active_connections

    def get_cluster_health(self) -> dict:
        """الحصول على صحة الكلاستر الكاملة"""
        healthy_count = sum(
            1 for m in self._masters.values()
            if m.status == MasterHealthStatus.HEALTHY
        )
        degraded_count = sum(
            1 for m in self._masters.values()
            if m.status == MasterHealthStatus.DEGRADED
        )
        unhealthy_count = sum(
            1 for m in self._masters.values()
            if m.status == MasterHealthStatus.UNHEALTHY
        )

        # تحديد حالة الكلاستر الإجمالية
        total = len(self._masters) + 1  # +1 لهذا الـ Master
        if unhealthy_count > total // 2:
            cluster_status = "critical"
        elif unhealthy_count > 0 or degraded_count > total // 2:
            cluster_status = "degraded"
        else:
            cluster_status = "healthy"

        return {
            "cluster_status": cluster_status,
            "self": self._self_health.to_dict(),
            "peers": {
                mid: m.to_dict()
                for mid, m in self._masters.items()
            },
            "summary": {
                "total_masters": total,
                "healthy": healthy_count + (1 if self._self_health.status == MasterHealthStatus.HEALTHY else 0),
                "degraded": degraded_count,
                "unhealthy": unhealthy_count,
            },
        }

    # ==================== API Handler ====================

    def get_health_response(self) -> dict:
        """استجابة endpoint الصحة"""
        return {
            "status": self._self_health.status.value,
            "master_id": self.config.master_id,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "cpu_percent": self._self_health.cpu_percent,
                "memory_percent": self._self_health.memory_percent,
                "jobs_count": self._self_health.jobs_count,
                "workers_count": self._self_health.workers_count,
                "active_connections": self._self_health.active_connections,
            },
        }
