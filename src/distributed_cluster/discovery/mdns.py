"""
mDNS Discovery - اكتشاف عبر mDNS
==================================

Automatic service discovery using multicast DNS (Zeroconf/Bonjour).
"""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Service type for NebulaCompute
SERVICE_TYPE = "_nebulacompute._tcp.local."
MASTER_SERVICE = "_nebula-master._tcp.local."
WORKER_SERVICE = "_nebula-worker._tcp.local."


@dataclass
class ServiceInfo:
    """معلومات الخدمة المكتشفة."""

    name: str
    service_type: str
    host: str
    port: int
    properties: Dict[str, str] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)

    @property
    def address(self) -> str:
        """عنوان الخدمة."""
        return f"{self.host}:{self.port}"

    def to_dict(self) -> Dict:
        """تحويل إلى قاموس."""
        return {
            "name": self.name,
            "service_type": self.service_type,
            "host": self.host,
            "port": self.port,
            "address": self.address,
            "properties": self.properties,
            "discovered_at": self.discovered_at.isoformat(),
            "last_seen": self.last_seen.isoformat(),
        }


class MDNSDiscovery:
    """
    اكتشاف الخدمات عبر mDNS.

    Uses Zeroconf/Bonjour for automatic service discovery on local networks.

    Features:
    - Automatic master discovery
    - Worker registration and discovery
    - Service health monitoring
    - Cross-platform support
    """

    def __init__(
        self,
        service_name: Optional[str] = None,
        on_service_found: Optional[Callable[[ServiceInfo], None]] = None,
        on_service_removed: Optional[Callable[[ServiceInfo], None]] = None,
    ):
        self.service_name = service_name or socket.gethostname()
        self.on_service_found = on_service_found
        self.on_service_removed = on_service_removed

        self._services: Dict[str, ServiceInfo] = {}
        self._zeroconf = None
        self._browser = None
        self._service_info = None
        self._running = False

    async def start_browser(self, service_type: str = MASTER_SERVICE) -> None:
        """
        بدء البحث عن الخدمات.

        Args:
            service_type: نوع الخدمة للبحث عنها
        """
        try:
            from zeroconf import ServiceBrowser
            from zeroconf.asyncio import AsyncZeroconf

            logger.info(f"Starting mDNS browser for {service_type}")

            self._zeroconf = AsyncZeroconf()
            self._browser = ServiceBrowser(
                self._zeroconf.zeroconf,
                service_type,
                self,
            )
            self._running = True

            logger.info("mDNS browser started")

        except ImportError:
            logger.warning("zeroconf not installed, using fallback discovery")
            await self._fallback_discovery()

    async def register_service(
        self,
        name: str,
        service_type: str,
        port: int,
        properties: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        تسجيل خدمة في الشبكة.

        Args:
            name: اسم الخدمة
            service_type: نوع الخدمة
            port: منفذ الخدمة
            properties: خصائص إضافية
        """
        try:
            from zeroconf import ServiceInfo as ZeroconfServiceInfo
            from zeroconf.asyncio import AsyncZeroconf

            if not self._zeroconf:
                self._zeroconf = AsyncZeroconf()

            # Get local IP
            local_ip = self._get_local_ip()

            # Create service info
            props = properties or {}
            props.update(
                {
                    "version": "1.0.0",
                    "hostname": socket.gethostname(),
                }
            )

            self._service_info = ZeroconfServiceInfo(
                service_type,
                f"{name}.{service_type}",
                addresses=[socket.inet_aton(local_ip)],
                port=port,
                properties=props,
                server=f"{name}.local.",
            )

            await self._zeroconf.async_register_service(self._service_info)
            logger.info(f"Registered service: {name} at {local_ip}:{port}")

        except ImportError:
            logger.warning("zeroconf not installed, skipping registration")

    async def unregister_service(self) -> None:
        """إلغاء تسجيل الخدمة."""
        if self._zeroconf and self._service_info:
            await self._zeroconf.async_unregister_service(self._service_info)
            logger.info("Service unregistered")

    async def stop(self) -> None:
        """إيقاف الاكتشاف."""
        self._running = False

        if self._browser:
            self._browser.cancel()
            self._browser = None

        if self._zeroconf:
            await self._zeroconf.async_close()
            self._zeroconf = None

        logger.info("mDNS discovery stopped")

    def add_service(self, zeroconf, service_type: str, name: str) -> None:
        """معالج إضافة خدمة (Zeroconf callback)."""
        asyncio.create_task(self._handle_service_found(zeroconf, service_type, name))

    def remove_service(self, zeroconf, service_type: str, name: str) -> None:
        """معالج إزالة خدمة (Zeroconf callback)."""
        if name in self._services:
            service = self._services.pop(name)
            logger.info(f"Service removed: {name}")
            if self.on_service_removed:
                self.on_service_removed(service)

    def update_service(self, zeroconf, service_type: str, name: str) -> None:
        """معالج تحديث خدمة (Zeroconf callback)."""
        if name in self._services:
            self._services[name].last_seen = datetime.now(timezone.utc)

    async def _handle_service_found(self, zeroconf, service_type: str, name: str) -> None:
        """معالجة خدمة مكتشفة."""
        try:
            info = zeroconf.get_service_info(service_type, name)
            if info:
                addresses = info.parsed_addresses()
                host = addresses[0] if addresses else None

                if host:
                    service = ServiceInfo(
                        name=name,
                        service_type=service_type,
                        host=host,
                        port=info.port,
                        properties={k.decode(): v.decode() for k, v in info.properties.items()},
                    )

                    self._services[name] = service
                    logger.info(f"Service found: {name} at {service.address}")

                    if self.on_service_found:
                        self.on_service_found(service)

        except Exception as e:
            logger.error(f"Error handling service: {e}")

    def get_services(self) -> List[ServiceInfo]:
        """الحصول على قائمة الخدمات."""
        return list(self._services.values())

    def get_masters(self) -> List[ServiceInfo]:
        """الحصول على قائمة الماسترات."""
        return [s for s in self._services.values() if MASTER_SERVICE in s.service_type]

    def get_workers(self) -> List[ServiceInfo]:
        """الحصول على قائمة العمال."""
        return [s for s in self._services.values() if WORKER_SERVICE in s.service_type]

    async def _fallback_discovery(self) -> None:
        """اكتشاف بديل باستخدام broadcast."""
        logger.info("Using broadcast fallback discovery")
        # Will use BroadcastDiscovery as fallback

    def _get_local_ip(self) -> str:
        """الحصول على IP المحلي."""
        try:
            # Create a socket to determine the local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


async def discover_masters(timeout: float = 5.0) -> List[ServiceInfo]:
    """
    اكتشاف الماسترات في الشبكة.

    Args:
        timeout: مدة البحث بالثواني

    Returns:
        قائمة الماسترات المكتشفة
    """
    discovered = []

    def on_found(service: ServiceInfo):
        discovered.append(service)

    discovery = MDNSDiscovery(on_service_found=on_found)
    await discovery.start_browser(MASTER_SERVICE)

    await asyncio.sleep(timeout)

    await discovery.stop()

    return discovered
