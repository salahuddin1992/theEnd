"""
Lease Model - نموذج الـ Lease
================================

الـ Lease هو "حجز مؤقت" لـ Job على Worker.

**لماذا الـ Leases مهمة؟**
الأنظمة الموزعة تكذب عليك طول الوقت:
- الشبكة تقطع
- الجهاز ينام
- الـ Agent يتهنج
- الـ Master يعيد تشغيل

الـ Lease يمنع "الأشباح" (ghost jobs):
- Worker يحجز job لفترة محدودة
- إذا ما جدد الـ lease قبل انتهائه → Job يرجع للطابور
- إذا Worker مات → الـ Master ما يبقى مصدق إنه شغال

**Idempotency (التكرار الآمن):**
- كل lease له ID فريد
- إذا Worker كرر ReportCompleted بنفس lease_id → نتجاهل التكرار
- هذا يحمي من مشاكل الشبكة (retries)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import uuid
import hashlib


class LeaseState(str, Enum):
    """حالات الـ Lease."""
    ACTIVE = "active"           # فعّال
    EXPIRED = "expired"         # انتهت صلاحيته
    RELEASED = "released"       # تم تحريره (انتهى job)
    REVOKED = "revoked"         # تم إلغاؤه (من Master)


@dataclass
class Lease:
    """
    Lease - حجز مؤقت.

    قواعد الـ Lease:
    1. Worker يستلم job مع lease_id + expires_at
    2. Worker لازم يجدد الـ lease قبل انتهائه (عبر Heartbeat أو RenewLease)
    3. إذا انتهى الـ lease → Job يُعاد للطابور
    4. Worker واحد فقط يملك lease في أي وقت
    5. الـ lease_id فريد عالمياً (لمنع التضارب)
    """

    lease_id: str
    job_id: str
    worker_id: str
    state: LeaseState = LeaseState.ACTIVE

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_renewed_at: Optional[datetime] = None
    released_at: Optional[datetime] = None

    # Tracking
    renewal_count: int = 0
    idempotency_key: Optional[str] = None  # لمنع التكرار

    # Default duration
    DEFAULT_DURATION_SECONDS: int = 60

    @classmethod
    def create(
        cls,
        job_id: str,
        worker_id: str,
        duration_seconds: int = 60,
        idempotency_key: Optional[str] = None,
    ) -> Lease:
        """
        إنشاء Lease جديد.

        Args:
            job_id: ID الـ Job
            worker_id: ID الـ Worker
            duration_seconds: مدة الـ lease بالثواني
            idempotency_key: مفتاح لمنع التكرار
        """
        now = datetime.utcnow()
        lease_id = cls._generate_lease_id(job_id, worker_id, now)

        return cls(
            lease_id=lease_id,
            job_id=job_id,
            worker_id=worker_id,
            state=LeaseState.ACTIVE,
            created_at=now,
            expires_at=now + timedelta(seconds=duration_seconds),
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _generate_lease_id(job_id: str, worker_id: str, timestamp: datetime) -> str:
        """توليد ID فريد للـ lease."""
        unique_string = f"{job_id}-{worker_id}-{timestamp.isoformat()}-{uuid.uuid4().hex[:8]}"
        hash_suffix = hashlib.sha256(unique_string.encode()).hexdigest()[:12]
        return f"lease-{hash_suffix}"

    @property
    def is_active(self) -> bool:
        """هل الـ lease فعّال؟"""
        if self.state != LeaseState.ACTIVE:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """هل انتهت صلاحيته؟"""
        if self.state == LeaseState.EXPIRED:
            return True
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return True
        return False

    @property
    def time_remaining_seconds(self) -> float:
        """الوقت المتبقي بالثواني."""
        if not self.expires_at:
            return float('inf')
        remaining = (self.expires_at - datetime.utcnow()).total_seconds()
        return max(0, remaining)

    @property
    def duration_seconds(self) -> float:
        """مدة الـ lease الأصلية."""
        if not self.expires_at:
            return 0
        return (self.expires_at - self.created_at).total_seconds()

    def renew(self, extension_seconds: Optional[int] = None) -> bool:
        """
        تجديد الـ lease.

        Args:
            extension_seconds: مدة التمديد (افتراضي: نفس المدة الأصلية)

        Returns:
            True إذا نجح التجديد
        """
        if not self.is_active:
            return False

        now = datetime.utcnow()

        if extension_seconds is None:
            # استخدم نفس المدة الأصلية
            extension_seconds = int(self.duration_seconds) or self.DEFAULT_DURATION_SECONDS

        self.expires_at = now + timedelta(seconds=extension_seconds)
        self.last_renewed_at = now
        self.renewal_count += 1

        return True

    def release(self, reason: str = "completed") -> None:
        """
        تحرير الـ lease (بعد انتهاء Job).

        Args:
            reason: سبب التحرير
        """
        self.state = LeaseState.RELEASED
        self.released_at = datetime.utcnow()

    def expire(self) -> None:
        """تعليم الـ lease كمنتهي الصلاحية."""
        if self.state == LeaseState.ACTIVE:
            self.state = LeaseState.EXPIRED

    def revoke(self, reason: str = "revoked by master") -> None:
        """
        إلغاء الـ lease (من Master).

        يُستخدم عندما:
        - Worker banned
        - Job canceled
        - إعادة جدولة manual
        """
        self.state = LeaseState.REVOKED
        self.released_at = datetime.utcnow()

    def validate_ownership(self, worker_id: str) -> bool:
        """
        التحقق من ملكية الـ lease.

        مهم لمنع worker من التلاعب بـ jobs غيره.
        """
        return self.worker_id == worker_id and self.is_active

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "lease_id": self.lease_id,
            "job_id": self.job_id,
            "worker_id": self.worker_id,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_renewed_at": self.last_renewed_at.isoformat() if self.last_renewed_at else None,
            "released_at": self.released_at.isoformat() if self.released_at else None,
            "renewal_count": self.renewal_count,
            "is_active": self.is_active,
            "is_expired": self.is_expired,
            "time_remaining_seconds": self.time_remaining_seconds,
        }


@dataclass
class LeaseManager:
    """
    مدير الـ Leases.

    المسؤوليات:
    1. إنشاء leases جديدة
    2. تجديد leases
    3. فحص وتنظيف leases منتهية
    4. منع التضارب (worker واحد لكل job)
    """

    # Storage
    _leases: dict[str, Lease] = field(default_factory=dict)
    _job_to_lease: dict[str, str] = field(default_factory=dict)  # job_id -> lease_id
    _worker_leases: dict[str, set[str]] = field(default_factory=dict)  # worker_id -> {lease_ids}

    # Configuration
    default_duration_seconds: int = 60
    max_renewals: int = 100  # حد أقصى للتجديدات

    # Idempotency cache (لمنع التكرار)
    _completed_leases: dict[str, datetime] = field(default_factory=dict)  # lease_id -> completed_at
    _idempotency_cache: dict[str, str] = field(default_factory=dict)  # key -> job_id

    def create_lease(
        self,
        job_id: str,
        worker_id: str,
        duration_seconds: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[Lease]:
        """
        إنشاء lease جديد.

        قواعد:
        1. Job واحد يمكن أن يكون له lease واحد فقط في أي وقت
        2. إذا كان هناك lease فعّال → نرفض
        3. إذا كان idempotency_key موجود سابقاً → نرجع نفس الـ job
        """
        # Check idempotency
        if idempotency_key and idempotency_key in self._idempotency_cache:
            existing_job_id = self._idempotency_cache[idempotency_key]
            if existing_job_id == job_id:
                # Same request, return existing lease if active
                existing_lease_id = self._job_to_lease.get(job_id)
                if existing_lease_id:
                    return self._leases.get(existing_lease_id)
            return None  # Different job with same key

        # Check if job already has active lease
        existing_lease_id = self._job_to_lease.get(job_id)
        if existing_lease_id:
            existing_lease = self._leases.get(existing_lease_id)
            if existing_lease and existing_lease.is_active:
                return None  # Already has active lease

        # Create new lease
        duration = duration_seconds or self.default_duration_seconds
        lease = Lease.create(job_id, worker_id, duration, idempotency_key)

        # Store
        self._leases[lease.lease_id] = lease
        self._job_to_lease[job_id] = lease.lease_id

        if worker_id not in self._worker_leases:
            self._worker_leases[worker_id] = set()
        self._worker_leases[worker_id].add(lease.lease_id)

        if idempotency_key:
            self._idempotency_cache[idempotency_key] = job_id

        return lease

    def get_lease(self, lease_id: str) -> Optional[Lease]:
        """الحصول على lease بالـ ID."""
        return self._leases.get(lease_id)

    def get_lease_by_job(self, job_id: str) -> Optional[Lease]:
        """الحصول على lease لـ job."""
        lease_id = self._job_to_lease.get(job_id)
        if lease_id:
            return self._leases.get(lease_id)
        return None

    def get_worker_leases(self, worker_id: str) -> list[Lease]:
        """الحصول على كل leases لـ worker."""
        lease_ids = self._worker_leases.get(worker_id, set())
        return [self._leases[lid] for lid in lease_ids if lid in self._leases]

    def renew_lease(
        self,
        lease_id: str,
        worker_id: str,
        extension_seconds: Optional[int] = None,
    ) -> Optional[Lease]:
        """
        تجديد lease.

        Args:
            lease_id: ID الـ lease
            worker_id: ID الـ worker (للتحقق من الملكية)
            extension_seconds: مدة التمديد
        """
        lease = self._leases.get(lease_id)
        if not lease:
            return None

        # Validate ownership
        if not lease.validate_ownership(worker_id):
            return None

        # Check max renewals
        if lease.renewal_count >= self.max_renewals:
            return None

        # Renew
        if lease.renew(extension_seconds):
            return lease
        return None

    def release_lease(
        self,
        lease_id: str,
        worker_id: str,
        reason: str = "completed",
    ) -> bool:
        """
        تحرير lease.

        **Idempotent**: إذا تم التحرير سابقاً → نرجع True
        """
        # Check if already completed (idempotency)
        if lease_id in self._completed_leases:
            return True

        lease = self._leases.get(lease_id)
        if not lease:
            return False

        # Validate ownership
        if lease.worker_id != worker_id:
            return False

        # Release
        lease.release(reason)
        self._completed_leases[lease_id] = datetime.utcnow()

        # Cleanup mappings
        if lease.job_id in self._job_to_lease:
            del self._job_to_lease[lease.job_id]

        if worker_id in self._worker_leases:
            self._worker_leases[worker_id].discard(lease_id)

        return True

    def check_expired_leases(self) -> list[Lease]:
        """
        فحص وإرجاع leases منتهية.

        يُستدعى دورياً من Scheduler.
        """
        expired = []
        now = datetime.utcnow()

        for lease in list(self._leases.values()):
            if lease.state == LeaseState.ACTIVE and lease.expires_at:
                if now > lease.expires_at:
                    lease.expire()
                    expired.append(lease)

                    # Cleanup mappings
                    if lease.job_id in self._job_to_lease:
                        del self._job_to_lease[lease.job_id]

                    if lease.worker_id in self._worker_leases:
                        self._worker_leases[lease.worker_id].discard(lease.lease_id)

        return expired

    def revoke_worker_leases(self, worker_id: str, reason: str = "worker offline") -> list[str]:
        """
        إلغاء كل leases لـ worker (عندما يصير offline).

        Returns:
            قائمة job_ids اللي تحتاج إعادة جدولة
        """
        job_ids = []
        lease_ids = list(self._worker_leases.get(worker_id, set()))

        for lease_id in lease_ids:
            lease = self._leases.get(lease_id)
            if lease and lease.is_active:
                lease.revoke(reason)
                job_ids.append(lease.job_id)

                if lease.job_id in self._job_to_lease:
                    del self._job_to_lease[lease.job_id]

        if worker_id in self._worker_leases:
            del self._worker_leases[worker_id]

        return job_ids

    def cleanup_old_leases(self, max_age_hours: int = 24) -> int:
        """
        تنظيف leases قديمة من الذاكرة.

        Returns:
            عدد الـ leases المحذوفة
        """
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        removed = 0

        for lease_id in list(self._leases.keys()):
            lease = self._leases[lease_id]
            if lease.state != LeaseState.ACTIVE and lease.created_at < cutoff:
                del self._leases[lease_id]
                removed += 1

        # Cleanup completed leases cache
        for lease_id in list(self._completed_leases.keys()):
            if self._completed_leases[lease_id] < cutoff:
                del self._completed_leases[lease_id]

        return removed

    def get_stats(self) -> dict:
        """إحصائيات الـ leases."""
        active = sum(1 for l in self._leases.values() if l.is_active)
        expired = sum(1 for l in self._leases.values() if l.state == LeaseState.EXPIRED)
        released = sum(1 for l in self._leases.values() if l.state == LeaseState.RELEASED)
        revoked = sum(1 for l in self._leases.values() if l.state == LeaseState.REVOKED)

        return {
            "total_leases": len(self._leases),
            "active_leases": active,
            "expired_leases": expired,
            "released_leases": released,
            "revoked_leases": revoked,
            "completed_cache_size": len(self._completed_leases),
            "idempotency_cache_size": len(self._idempotency_cache),
        }
