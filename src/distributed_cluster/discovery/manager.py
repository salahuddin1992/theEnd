"""
Discovery Manager - مدير الاكتشاف
===================================

Unified discovery manager supporting multiple discovery methods.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from .mdns import MDNSDiscovery, ServiceInfo, MASTER_SERVICE, WORKER_SERVICE
from .broadcast import BroadcastDiscovery, BroadcastMessage

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredService:
    """خدمة مكتشفة موحدة."""
    service_id: str
    service_type: str  # "master" or "worker"
    name: str
    host: str
    port: int
    discovery_method: str  # "mdns" or "broadcast"
    properties: Dict[str, str] = field(default_factory=dict)
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    healthy: bool = True

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> Dict:
        return {
            "service_id": self.service_id,
            "service_type": self.service_type,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "address": self.address,
            "url": self.url,
            "discovery_method": self.discovery_method,
            "properties": self.properties,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "healthy": self.healthy,
        }


class DiscoveryManager:
    """
    مدير الاكتشاف الموحد.

    Combines mDNS and broadcast discovery for maximum compatibility.

    Features:
    - Automatic fallback between discovery methods
    - Service health monitoring
    - Event callbacks for service changes
    - Periodic refresh
    """

    def __init__(
        self,
        on_master_found: Optional[Callable[[DiscoveredService], None]] = None,
        on_worker_found: Optional[Callable[[DiscoveredService], None]] = None,
        on_service_lost: Optional[Callable[[DiscoveredService], None]] = None,
        stale_timeout: float = 90.0,  # Mark stale after 90s without heartbeat
    ):
        self.on_master_found = on_master_found
        self.on_worker_found = on_worker_found
        self.on_service_lost = on_service_lost
        self.stale_timeout = stale_timeout

        self._services: Dict[str, DiscoveredService] = {}
        self._mdns: Optional[MDNSDiscovery] = None
        self._broadcast: Optional[BroadcastDiscovery] = None
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self, use_mdns: bool = True, use_broadcast: bool = True) -> None:
        """
        بدء مدير الاكتشاف.

        Args:
            use_mdns: استخدام mDNS
            use_broadcast: استخدام البث
        """
        self._running = True

        if use_mdns:
            try:
                self._mdns = MDNSDiscovery(
                    on_service_found=self._handle_mdns_found,
                    on_service_removed=self._handle_mdns_removed,
                )
                await self._mdns.start_browser(MASTER_SERVICE)
                await self._mdns.start_browser(WORKER_SERVICE)
                logger.info("mDNS discovery enabled")
            except Exception as e:
                logger.warning(f"mDNS not available: {e}")
                self._mdns = None

        if use_broadcast:
            self._broadcast = BroadcastDiscovery(
                on_discovered=self._handle_broadcast_found,
            )
            await self._broadcast.start()
            logger.info("Broadcast discovery enabled")

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("Discovery manager started")

    async def stop(self) -> None:
        """إيقاف مدير الاكتشاف."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._mdns:
            await self._mdns.stop()

        if self._broadcast:
            await self._broadcast.stop()

        logger.info("Discovery manager stopped")

    async def register_master(
        self,
        name: str,
        port: int,
        properties: Optional[Dict[str, str]] = None,
    ) -> None:
        """تسجيل ماستر."""
        if self._mdns:
            await self._mdns.register_service(
                name=name,
                service_type=MASTER_SERVICE,
                port=port,
                properties=properties,
            )

        if self._broadcast:
            self._broadcast.service_type = "master"
            self._broadcast.service_name = name
            self._broadcast.port = port
            await self._broadcast.announce()

        logger.info(f"Registered master: {name} on port {port}")

    async def register_worker(
        self,
        name: str,
        port: int,
        properties: Optional[Dict[str, str]] = None,
    ) -> None:
        """تسجيل عامل."""
        if self._mdns:
            await self._mdns.register_service(
                name=name,
                service_type=WORKER_SERVICE,
                port=port,
                properties=properties,
            )

        if self._broadcast:
            self._broadcast.service_type = "worker"
            self._broadcast.service_name = name
            self._broadcast.port = port
            await self._broadcast.announce()

        logger.info(f"Registered worker: {name} on port {port}")

    async def discover(self, timeout: float = 5.0) -> Dict[str, List[DiscoveredService]]:
        """
        اكتشاف الخدمات.

        Args:
            timeout: مدة البحث

        Returns:
            قاموس بالماسترات والعمال
        """
        # Trigger discovery
        if self._broadcast:
            await self._broadcast.discover(timeout)

        # Wait for results
        await asyncio.sleep(timeout)

        return {
            "masters": self.get_masters(),
            "workers": self.get_workers(),
        }

    def get_services(self) -> List[DiscoveredService]:
        """الحصول على جميع الخدمات."""
        return list(self._services.values())

    def get_masters(self) -> List[DiscoveredService]:
        """الحصول على الماسترات."""
        return [s for s in self._services.values() if s.service_type == "master" and s.healthy]

    def get_workers(self) -> List[DiscoveredService]:
        """الحصول على العمال."""
        return [s for s in self._services.values() if s.service_type == "worker" and s.healthy]

    def get_best_master(self) -> Optional[DiscoveredService]:
        """الحصول على أفضل ماستر."""
        masters = self.get_masters()
        if not masters:
            return None

        # Sort by most recently seen
        masters.sort(key=lambda m: m.last_seen, reverse=True)
        return masters[0]

    def _handle_mdns_found(self, service: ServiceInfo) -> None:
        """معالجة خدمة mDNS مكتشفة."""
        service_type = "master" if MASTER_SERVICE in service.service_type else "worker"
        service_id = f"mdns:{service_type}:{service.host}:{service.port}"

        discovered = DiscoveredService(
            service_id=service_id,
            service_type=service_type,
            name=service.name,
            host=service.host,
            port=service.port,
            discovery_method="mdns",
            properties=service.properties,
        )

        self._add_service(discovered)

    def _handle_mdns_removed(self, service: ServiceInfo) -> None:
        """معالجة إزالة خدمة mDNS."""
        service_type = "master" if MASTER_SERVICE in service.service_type else "worker"
        service_id = f"mdns:{service_type}:{service.host}:{service.port}"

        if service_id in self._services:
            lost_service = self._services.pop(service_id)
            logger.info(f"Service removed: {lost_service.name}")
            if self.on_service_lost:
                self.on_service_lost(lost_service)

    def _handle_broadcast_found(self, message: BroadcastMessage) -> None:
        """معالجة خدمة broadcast مكتشفة."""
        service_id = f"broadcast:{message.service_type}:{message.host}:{message.port}"

        discovered = DiscoveredService(
            service_id=service_id,
            service_type=message.service_type,
            name=message.name,
            host=message.host,
            port=message.port,
            discovery_method="broadcast",
            properties=message.properties,
        )

        self._add_service(discovered)

    def _add_service(self, service: DiscoveredService) -> None:
        """إضافة أو تحديث خدمة."""
        is_new = service.service_id not in self._services

        if is_new:
            self._services[service.service_id] = service
            logger.info(f"Discovered {service.service_type}: {service.name} at {service.address}")

            # Notify callbacks
            if service.service_type == "master" and self.on_master_found:
                self.on_master_found(service)
            elif service.service_type == "worker" and self.on_worker_found:
                self.on_worker_found(service)
        else:
            # Update last seen
            self._services[service.service_id].last_seen = datetime.now(timezone.utc)
            self._services[service.service_id].healthy = True

    async def _cleanup_loop(self) -> None:
        """حلقة تنظيف الخدمات القديمة."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                now = datetime.now(timezone.utc)
                stale_threshold = now - timedelta(seconds=self.stale_timeout)

                stale_services = []
                for service_id, service in list(self._services.items()):
                    if service.last_seen < stale_threshold:
                        stale_services.append(service_id)
                        service.healthy = False
                        logger.warning(f"Service stale: {service.name}")

                # Remove very old services
                very_stale = now - timedelta(seconds=self.stale_timeout * 2)
                for service_id in stale_services:
                    service = self._services[service_id]
                    if service.last_seen < very_stale:
                        del self._services[service_id]
                        logger.info(f"Service removed: {service.name}")
                        if self.on_service_lost:
                            self.on_service_lost(service)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")


async def auto_discover_master(timeout: float = 5.0) -> Optional[str]:
    """
    اكتشاف تلقائي للماستر.

    Returns:
        URL للماستر أو None
    """
    manager = DiscoveryManager()
    await manager.start()

    result = await manager.discover(timeout)

    await manager.stop()

    if result["masters"]:
        return result["masters"][0].url

    return None
