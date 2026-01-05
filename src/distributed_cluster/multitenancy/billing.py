"""
Billing Management - إدارة الفوترة
====================================

Usage tracking and billing for multi-tenancy.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BillingPeriod(str, Enum):
    """فترة الفوترة"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ResourceType(str, Enum):
    """نوع المورد"""
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    STORAGE = "storage"
    NETWORK_EGRESS = "network_egress"
    JOB_EXECUTION = "job_execution"


@dataclass
class ResourcePrice:
    """سعر المورد"""
    resource_type: ResourceType
    unit: str  # e.g., "core-hour", "gb-hour", "request"
    price_per_unit: Decimal
    currency: str = "USD"


@dataclass
class UsageRecord:
    """سجل الاستخدام"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    resource_type: ResourceType = ResourceType.CPU
    quantity: Decimal = Decimal("0")
    unit: str = ""
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    job_id: Optional[str] = None
    worker_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        """المدة بالثواني"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "resourceType": self.resource_type.value,
            "quantity": float(self.quantity),
            "unit": self.unit,
            "startTime": self.start_time.isoformat(),
            "endTime": self.end_time.isoformat() if self.end_time else None,
            "durationSeconds": self.duration_seconds,
            "jobId": self.job_id,
        }


@dataclass
class InvoiceLineItem:
    """بند الفاتورة"""
    description: str
    resource_type: ResourceType
    quantity: Decimal
    unit: str
    unit_price: Decimal
    total: Decimal
    usage_records: List[str] = field(default_factory=list)


@dataclass
class Invoice:
    """الفاتورة"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    period_start: datetime = field(default_factory=datetime.utcnow)
    period_end: datetime = field(default_factory=datetime.utcnow)
    status: str = "draft"  # draft, pending, paid, overdue, cancelled
    currency: str = "USD"
    line_items: List[InvoiceLineItem] = field(default_factory=list)
    subtotal: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=datetime.utcnow)
    paid_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    notes: str = ""

    def calculate_totals(self) -> None:
        """حساب المجاميع"""
        self.subtotal = sum(item.total for item in self.line_items)
        self.total = self.subtotal + self.tax

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "periodStart": self.period_start.isoformat(),
            "periodEnd": self.period_end.isoformat(),
            "status": self.status,
            "currency": self.currency,
            "lineItems": [
                {
                    "description": item.description,
                    "resourceType": item.resource_type.value,
                    "quantity": float(item.quantity),
                    "unit": item.unit,
                    "unitPrice": float(item.unit_price),
                    "total": float(item.total),
                }
                for item in self.line_items
            ],
            "subtotal": float(self.subtotal),
            "tax": float(self.tax),
            "total": float(self.total),
            "createdAt": self.created_at.isoformat(),
            "dueDate": self.due_date.isoformat() if self.due_date else None,
        }


class UsageTracker:
    """
    متتبع الاستخدام
    Usage Tracker
    """

    def __init__(self):
        self._records: Dict[str, List[UsageRecord]] = {}  # tenant_id -> records
        self._active_records: Dict[str, UsageRecord] = {}  # record_id -> record
        self._lock = asyncio.Lock()

    async def start_tracking(
        self,
        tenant_id: str,
        resource_type: ResourceType,
        quantity: Decimal,
        unit: str,
        job_id: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> str:
        """بدء تتبع الاستخدام"""
        record = UsageRecord(
            tenant_id=tenant_id,
            resource_type=resource_type,
            quantity=quantity,
            unit=unit,
            job_id=job_id,
            worker_id=worker_id,
        )

        async with self._lock:
            self._active_records[record.id] = record
            if tenant_id not in self._records:
                self._records[tenant_id] = []
            self._records[tenant_id].append(record)

        logger.debug(f"Started tracking {resource_type.value} for tenant {tenant_id}")
        return record.id

    async def stop_tracking(self, record_id: str) -> Optional[UsageRecord]:
        """إيقاف تتبع الاستخدام"""
        async with self._lock:
            record = self._active_records.pop(record_id, None)
            if record:
                record.end_time = datetime.now(timezone.utc)
                logger.debug(f"Stopped tracking {record.resource_type.value}")
            return record

    async def record_usage(
        self,
        tenant_id: str,
        resource_type: ResourceType,
        quantity: Decimal,
        unit: str,
        job_id: Optional[str] = None,
    ) -> UsageRecord:
        """تسجيل استخدام فوري"""
        record = UsageRecord(
            tenant_id=tenant_id,
            resource_type=resource_type,
            quantity=quantity,
            unit=unit,
            job_id=job_id,
            end_time=datetime.now(timezone.utc),
        )

        async with self._lock:
            if tenant_id not in self._records:
                self._records[tenant_id] = []
            self._records[tenant_id].append(record)

        return record

    async def get_usage(
        self,
        tenant_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        resource_type: Optional[ResourceType] = None,
    ) -> List[UsageRecord]:
        """الحصول على سجلات الاستخدام"""
        records = self._records.get(tenant_id, [])

        if start_time:
            records = [r for r in records if r.start_time >= start_time]
        if end_time:
            records = [r for r in records if r.start_time <= end_time]
        if resource_type:
            records = [r for r in records if r.resource_type == resource_type]

        return records

    async def get_summary(
        self,
        tenant_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """الحصول على ملخص الاستخدام"""
        records = await self.get_usage(tenant_id, start_time, end_time)

        summary: Dict[str, Dict[str, Any]] = {}
        for record in records:
            rt = record.resource_type.value
            if rt not in summary:
                summary[rt] = {
                    "total_quantity": Decimal("0"),
                    "total_duration_hours": 0.0,
                    "record_count": 0,
                }
            summary[rt]["total_quantity"] += record.quantity
            summary[rt]["total_duration_hours"] += record.duration_seconds / 3600
            summary[rt]["record_count"] += 1

        return {
            "tenantId": tenant_id,
            "periodStart": start_time.isoformat() if start_time else None,
            "periodEnd": end_time.isoformat() if end_time else None,
            "resources": {
                k: {
                    "totalQuantity": float(v["total_quantity"]),
                    "totalDurationHours": v["total_duration_hours"],
                    "recordCount": v["record_count"],
                }
                for k, v in summary.items()
            },
        }


class BillingManager:
    """
    مدير الفوترة
    Billing Manager
    """

    def __init__(self, usage_tracker: Optional[UsageTracker] = None):
        self.usage_tracker = usage_tracker or UsageTracker()
        self._prices: Dict[ResourceType, ResourcePrice] = {}
        self._invoices: Dict[str, List[Invoice]] = {}  # tenant_id -> invoices
        self._lock = asyncio.Lock()

        # Set default prices
        self._set_default_prices()

    def _set_default_prices(self) -> None:
        """تعيين الأسعار الافتراضية"""
        self._prices = {
            ResourceType.CPU: ResourcePrice(
                ResourceType.CPU, "core-hour", Decimal("0.05")
            ),
            ResourceType.MEMORY: ResourcePrice(
                ResourceType.MEMORY, "gb-hour", Decimal("0.01")
            ),
            ResourceType.GPU: ResourcePrice(
                ResourceType.GPU, "gpu-hour", Decimal("0.50")
            ),
            ResourceType.STORAGE: ResourcePrice(
                ResourceType.STORAGE, "gb-month", Decimal("0.10")
            ),
            ResourceType.NETWORK_EGRESS: ResourcePrice(
                ResourceType.NETWORK_EGRESS, "gb", Decimal("0.05")
            ),
            ResourceType.JOB_EXECUTION: ResourcePrice(
                ResourceType.JOB_EXECUTION, "job", Decimal("0.001")
            ),
        }

    def set_price(
        self,
        resource_type: ResourceType,
        price_per_unit: Decimal,
        unit: str,
    ) -> None:
        """تعيين سعر"""
        self._prices[resource_type] = ResourcePrice(
            resource_type, unit, price_per_unit
        )

    def get_price(self, resource_type: ResourceType) -> Optional[ResourcePrice]:
        """الحصول على سعر"""
        return self._prices.get(resource_type)

    async def generate_invoice(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Invoice:
        """توليد فاتورة"""
        invoice = Invoice(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            due_date=period_end + timedelta(days=30),
        )

        # Get usage records
        records = await self.usage_tracker.get_usage(
            tenant_id, period_start, period_end
        )

        # Group by resource type
        by_type: Dict[ResourceType, List[UsageRecord]] = {}
        for record in records:
            if record.resource_type not in by_type:
                by_type[record.resource_type] = []
            by_type[record.resource_type].append(record)

        # Create line items
        for resource_type, type_records in by_type.items():
            price = self._prices.get(resource_type)
            if not price:
                continue

            # Calculate total usage
            if resource_type in (ResourceType.CPU, ResourceType.MEMORY, ResourceType.GPU):
                # Time-based resources
                total_hours = sum(r.duration_seconds / 3600 for r in type_records)
                avg_quantity = sum(r.quantity for r in type_records) / len(type_records)
                quantity = Decimal(str(total_hours)) * avg_quantity
            else:
                # Count-based resources
                quantity = sum(r.quantity for r in type_records)

            total = quantity * price.price_per_unit

            invoice.line_items.append(InvoiceLineItem(
                description=f"{resource_type.value.replace('_', ' ').title()} Usage",
                resource_type=resource_type,
                quantity=quantity,
                unit=price.unit,
                unit_price=price.price_per_unit,
                total=total,
                usage_records=[r.id for r in type_records],
            ))

        invoice.calculate_totals()
        invoice.status = "pending"

        # Store invoice
        async with self._lock:
            if tenant_id not in self._invoices:
                self._invoices[tenant_id] = []
            self._invoices[tenant_id].append(invoice)

        logger.info(f"Generated invoice {invoice.id} for tenant {tenant_id}: ${invoice.total}")
        return invoice

    async def get_invoices(
        self,
        tenant_id: str,
        status: Optional[str] = None,
    ) -> List[Invoice]:
        """الحصول على الفواتير"""
        invoices = self._invoices.get(tenant_id, [])
        if status:
            invoices = [i for i in invoices if i.status == status]
        return invoices

    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """الحصول على فاتورة"""
        for invoices in self._invoices.values():
            for invoice in invoices:
                if invoice.id == invoice_id:
                    return invoice
        return None

    async def mark_invoice_paid(self, invoice_id: str) -> Optional[Invoice]:
        """تعليم الفاتورة كمدفوعة"""
        invoice = await self.get_invoice(invoice_id)
        if invoice:
            invoice.status = "paid"
            invoice.paid_at = datetime.now(timezone.utc)
            logger.info(f"Invoice {invoice_id} marked as paid")
        return invoice

    async def get_current_month_cost(self, tenant_id: str) -> Decimal:
        """الحصول على تكلفة الشهر الحالي"""
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        records = await self.usage_tracker.get_usage(
            tenant_id, month_start, now
        )

        total = Decimal("0")
        for record in records:
            price = self._prices.get(record.resource_type)
            if price:
                if record.resource_type in (ResourceType.CPU, ResourceType.MEMORY, ResourceType.GPU):
                    hours = Decimal(str(record.duration_seconds / 3600))
                    total += record.quantity * hours * price.price_per_unit
                else:
                    total += record.quantity * price.price_per_unit

        return total

    async def get_cost_forecast(
        self,
        tenant_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """الحصول على توقعات التكلفة"""
        now = datetime.now(timezone.utc)
        past_days = min(days, 7)
        start = now - timedelta(days=past_days)

        records = await self.usage_tracker.get_usage(tenant_id, start, now)

        # Calculate daily average
        total = Decimal("0")
        for record in records:
            price = self._prices.get(record.resource_type)
            if price:
                if record.resource_type in (ResourceType.CPU, ResourceType.MEMORY, ResourceType.GPU):
                    hours = Decimal(str(record.duration_seconds / 3600))
                    total += record.quantity * hours * price.price_per_unit
                else:
                    total += record.quantity * price.price_per_unit

        daily_avg = total / Decimal(str(past_days)) if past_days > 0 else Decimal("0")
        forecast = daily_avg * Decimal(str(days))

        return {
            "tenantId": tenant_id,
            "forecastDays": days,
            "dailyAverage": float(daily_avg),
            "forecastTotal": float(forecast),
            "currency": "USD",
        }
