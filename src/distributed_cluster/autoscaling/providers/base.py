"""
Cloud Provider Base - القاعدة الأساسية لمزودي السحابة
=====================================================

Base Cloud Provider Interface
-----------------------------

This module defines the abstract interface that all cloud providers
must implement for auto-scaling worker provisioning.

يحدد هذا الملف الواجهة الأساسية التي يجب على جميع
مزودي السحابة تنفيذها لتوفير العمال للتوسع التلقائي.

Author: Distributed Cluster Team
License: MIT
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions / الاستثناءات
# =============================================================================


class ProviderError(Exception):
    """خطأ عام في المزود / General provider error"""
    pass


class ProvisioningError(ProviderError):
    """خطأ في إنشاء العمال / Worker provisioning error"""
    pass


class TerminationError(ProviderError):
    """خطأ في إنهاء العمال / Worker termination error"""
    pass


class ConnectionError(ProviderError):
    """خطأ في الاتصال / Connection error"""
    pass


# =============================================================================
# Data Classes / فئات البيانات
# =============================================================================


class InstanceState(str, Enum):
    """
    حالة الـ Instance
    Instance state
    """

    PENDING = "pending"  # قيد الإنشاء
    RUNNING = "running"  # يعمل
    STOPPING = "stopping"  # يتوقف
    STOPPED = "stopped"  # متوقف
    TERMINATING = "terminating"  # يُنهى
    TERMINATED = "terminated"  # تم إنهاؤه
    UNKNOWN = "unknown"  # غير معروف


@dataclass
class InstanceInfo:
    """
    معلومات Instance واحد
    Single instance information
    """

    instance_id: str  # معرف الـ instance
    provider: str  # اسم المزود (aws, gcp, azure, local)
    state: InstanceState  # الحالة الحالية
    instance_type: str = ""  # نوع الـ instance
    zone: str = ""  # المنطقة
    private_ip: Optional[str] = None  # IP الخاص
    public_ip: Optional[str] = None  # IP العام
    created_at: Optional[datetime] = None  # وقت الإنشاء
    tags: dict[str, str] = field(default_factory=dict)  # الوسوم
    labels: dict[str, str] = field(default_factory=dict)  # التسميات
    metadata: dict[str, Any] = field(default_factory=dict)  # بيانات إضافية

    # Worker mapping
    worker_id: Optional[str] = None  # معرف العامل المرتبط
    is_terminable: bool = True  # هل يمكن إنهاؤه

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس / Convert to dictionary"""
        return {
            "instance_id": self.instance_id,
            "provider": self.provider,
            "state": self.state.value,
            "instance_type": self.instance_type,
            "zone": self.zone,
            "private_ip": self.private_ip,
            "public_ip": self.public_ip,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tags": self.tags,
            "labels": self.labels,
            "worker_id": self.worker_id,
            "is_terminable": self.is_terminable,
        }


@dataclass
class ProviderConfig:
    """
    إعدادات المزود
    Provider configuration
    """

    # General
    name: str = "default"  # اسم الإعداد
    enabled: bool = True  # مفعل

    # Instance defaults
    default_instance_type: str = "default"  # نوع الـ instance الافتراضي
    default_zone: str = ""  # المنطقة الافتراضية
    default_tags: dict[str, str] = field(default_factory=dict)  # وسوم افتراضية
    default_labels: dict[str, str] = field(default_factory=dict)  # تسميات افتراضية

    # Networking
    vpc_id: Optional[str] = None  # VPC
    subnet_ids: list[str] = field(default_factory=list)  # الشبكات الفرعية
    security_group_ids: list[str] = field(default_factory=list)  # مجموعات الأمان

    # Worker configuration
    worker_image: str = ""  # صورة العامل (AMI, Container, etc.)
    worker_startup_script: str = ""  # سكربت البدء
    worker_ssh_key: str = ""  # مفتاح SSH
    worker_user_data: str = ""  # بيانات المستخدم

    # Limits
    max_instances: int = 100  # الحد الأقصى للـ instances
    min_instances: int = 0  # الحد الأدنى للـ instances

    # Timeouts
    provisioning_timeout_seconds: int = 300  # مهلة الإنشاء
    termination_timeout_seconds: int = 120  # مهلة الإنهاء
    health_check_interval_seconds: int = 30  # فترة فحص الصحة

    # Cost
    cost_per_hour: float = 0.0  # التكلفة بالساعة
    spot_enabled: bool = False  # استخدام spot instances
    spot_max_price: float = 0.0  # أقصى سعر للـ spot

    def to_dict(self) -> dict[str, Any]:
        """تحويل إلى قاموس / Convert to dictionary"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "default_instance_type": self.default_instance_type,
            "default_zone": self.default_zone,
            "default_tags": self.default_tags,
            "default_labels": self.default_labels,
            "vpc_id": self.vpc_id,
            "subnet_ids": self.subnet_ids,
            "security_group_ids": self.security_group_ids,
            "worker_image": self.worker_image,
            "max_instances": self.max_instances,
            "min_instances": self.min_instances,
            "cost_per_hour": self.cost_per_hour,
            "spot_enabled": self.spot_enabled,
        }


# =============================================================================
# Abstract Base Class / الفئة الأساسية المجردة
# =============================================================================


class CloudProvider(ABC):
    """
    مزود السحابة الأساسي
    Base Cloud Provider

    جميع مزودي السحابة يجب أن يرثوا من هذه الفئة
    ويقوموا بتنفيذ الطرق المطلوبة.

    All cloud providers must inherit from this class
    and implement the required methods.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        """
        تهيئة المزود

        Args:
            config: إعدادات المزود (اختياري)
        """
        self.config = config or ProviderConfig()
        self._connected = False
        self._instances: dict[str, InstanceInfo] = {}

    # =========================================================================
    # Connection / الاتصال
    # =========================================================================

    @abstractmethod
    async def connect(self) -> None:
        """
        الاتصال بالمزود
        Connect to the provider

        Raises:
            ConnectionError: إذا فشل الاتصال
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        قطع الاتصال بالمزود
        Disconnect from the provider
        """
        pass

    @property
    def is_connected(self) -> bool:
        """هل المزود متصل؟ / Is provider connected?"""
        return self._connected

    # =========================================================================
    # Provisioning / التوفير
    # =========================================================================

    @abstractmethod
    async def provision_workers(
        self,
        count: int,
        instance_type: Optional[str] = None,
        zone: Optional[str] = None,
        tags: Optional[list[str]] = None,
        labels: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> list[str]:
        """
        إنشاء عمال جدد
        Provision new workers

        Args:
            count: عدد العمال المطلوب إنشاؤهم
            instance_type: نوع الـ instance (اختياري)
            zone: المنطقة (اختياري)
            tags: الوسوم (اختياري)
            labels: التسميات (اختياري)
            **kwargs: خيارات إضافية

        Returns:
            list[str]: قائمة معرفات الـ instances الجديدة

        Raises:
            ProvisioningError: إذا فشل الإنشاء
        """
        pass

    @abstractmethod
    async def terminate_workers(self, instance_ids: list[str]) -> int:
        """
        إنهاء عمال
        Terminate workers

        Args:
            instance_ids: قائمة معرفات الـ instances للإنهاء

        Returns:
            int: عدد الـ instances التي تم إنهاؤها بنجاح

        Raises:
            TerminationError: إذا فشل الإنهاء
        """
        pass

    # =========================================================================
    # Instance Management / إدارة الـ Instances
    # =========================================================================

    @abstractmethod
    async def get_instances(
        self,
        state: Optional[InstanceState] = None,
        tags: Optional[dict[str, str]] = None,
    ) -> list[InstanceInfo]:
        """
        الحصول على قائمة الـ instances
        Get list of instances

        Args:
            state: فلترة بالحالة (اختياري)
            tags: فلترة بالوسوم (اختياري)

        Returns:
            list[InstanceInfo]: قائمة الـ instances
        """
        pass

    @abstractmethod
    async def get_instance(self, instance_id: str) -> Optional[InstanceInfo]:
        """
        الحصول على instance واحد
        Get single instance

        Args:
            instance_id: معرف الـ instance

        Returns:
            InstanceInfo أو None
        """
        pass

    @abstractmethod
    async def get_terminable_workers(self, count: int) -> list[str]:
        """
        الحصول على عمال قابلين للإنهاء
        Get workers that can be terminated

        يجب تجنب العمال الذين لديهم مهام نشطة.

        Args:
            count: العدد المطلوب

        Returns:
            list[str]: قائمة معرفات الـ instances
        """
        pass

    @abstractmethod
    async def get_worker_count(self) -> int:
        """
        الحصول على عدد العمال الحاليين
        Get current worker count

        Returns:
            int: عدد العمال العاملين
        """
        pass

    # =========================================================================
    # Health & Status / الصحة والحالة
    # =========================================================================

    async def health_check(self) -> bool:
        """
        فحص صحة الاتصال بالمزود
        Check provider connection health

        Returns:
            bool: True إذا كان الاتصال سليماً
        """
        try:
            await self.get_worker_count()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_status(self) -> dict[str, Any]:
        """
        الحصول على حالة المزود
        Get provider status

        Returns:
            dict: معلومات الحالة
        """
        return {
            "provider": self.__class__.__name__,
            "connected": self._connected,
            "config": self.config.to_dict(),
            "instances_cached": len(self._instances),
        }

    # =========================================================================
    # Helper Methods / طرق مساعدة
    # =========================================================================

    def _merge_tags(
        self,
        custom_tags: Optional[list[str]] = None,
    ) -> dict[str, str]:
        """
        دمج الوسوم مع الافتراضية
        Merge tags with defaults
        """
        tags = dict(self.config.default_tags)

        if custom_tags:
            for tag in custom_tags:
                tags[tag] = "true"

        # إضافة وسوم النظام
        tags["managed-by"] = "distributed-cluster"
        tags["autoscaling"] = "true"

        return tags

    def _merge_labels(
        self,
        custom_labels: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """
        دمج التسميات مع الافتراضية
        Merge labels with defaults
        """
        labels = dict(self.config.default_labels)

        if custom_labels:
            labels.update(custom_labels)

        return labels

    def _get_instance_type(
        self,
        instance_type: Optional[str] = None,
    ) -> str:
        """
        الحصول على نوع الـ instance
        Get instance type
        """
        return instance_type or self.config.default_instance_type

    def _get_zone(self, zone: Optional[str] = None) -> str:
        """
        الحصول على المنطقة
        Get zone
        """
        return zone or self.config.default_zone

    async def wait_for_instances(
        self,
        instance_ids: list[str],
        target_state: InstanceState,
        timeout_seconds: int = 300,
        check_interval: int = 10,
    ) -> bool:
        """
        الانتظار حتى تصل الـ instances لحالة معينة
        Wait for instances to reach a state

        Args:
            instance_ids: معرفات الـ instances
            target_state: الحالة المستهدفة
            timeout_seconds: مهلة الانتظار
            check_interval: فترة الفحص

        Returns:
            bool: True إذا وصلت جميع الـ instances للحالة المطلوبة
        """
        import asyncio
        from datetime import datetime, timedelta

        deadline = datetime.utcnow() + timedelta(seconds=timeout_seconds)

        while datetime.utcnow() < deadline:
            all_ready = True

            for instance_id in instance_ids:
                instance = await self.get_instance(instance_id)
                if not instance or instance.state != target_state:
                    all_ready = False
                    break

            if all_ready:
                return True

            await asyncio.sleep(check_interval)

        logger.warning(
            f"Timeout waiting for instances to reach state {target_state.value}"
        )
        return False
