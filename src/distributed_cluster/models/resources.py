"""
Resource Models - نماذج الموارد
================================

تعريفات الموارد المتاحة على كل Worker:
- CPU cores
- RAM (memory)
- GPU (with VRAM)
- Custom resources (optional)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ResourceType(str, Enum):
    """أنواع الموارد المدعومة."""
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    CUSTOM = "custom"


@dataclass
class GPUInfo:
    """معلومات GPU واحدة."""
    index: int
    name: str
    uuid: str
    memory_total_mb: int
    memory_free_mb: int
    memory_used_mb: int
    utilization_percent: float
    temperature_c: Optional[float] = None
    power_draw_w: Optional[float] = None

    @property
    def memory_available_mb(self) -> int:
        """الذاكرة المتاحة."""
        return self.memory_free_mb

    @property
    def is_available(self) -> bool:
        """هل الـ GPU متاحة للاستخدام؟"""
        return self.utilization_percent < 90 and self.memory_free_mb > 500


@dataclass
class ResourceSpec:
    """
    مواصفات الموارد المطلوبة لـ Job أو المتاحة على Worker.

    هذا هو "Resource Vector" اللي يستخدمه الـ Scheduler للمطابقة.
    """
    cpu_cores: float = 1.0  # عدد الأنوية (يدعم كسور مثل 0.5)
    memory_mb: int = 512  # الذاكرة بالميغابايت
    gpu_count: int = 0  # عدد GPUs المطلوبة
    gpu_memory_mb: int = 0  # ذاكرة GPU المطلوبة (لكل GPU)
    custom: dict[str, float] = field(default_factory=dict)  # موارد مخصصة

    def fits_in(self, available: ResourceSpec) -> bool:
        """
        هل هذه المتطلبات تتناسب مع الموارد المتاحة؟

        يُستخدم في الـ Scheduler للتحقق قبل تعيين Job لـ Worker.
        """
        if self.cpu_cores > available.cpu_cores:
            return False
        if self.memory_mb > available.memory_mb:
            return False
        if self.gpu_count > available.gpu_count:
            return False
        if self.gpu_memory_mb > available.gpu_memory_mb:
            return False

        # تحقق من الموارد المخصصة
        for key, required in self.custom.items():
            if key not in available.custom or required > available.custom[key]:
                return False

        return True

    def subtract(self, other: ResourceSpec) -> ResourceSpec:
        """طرح موارد (عند تخصيص job)."""
        return ResourceSpec(
            cpu_cores=max(0, self.cpu_cores - other.cpu_cores),
            memory_mb=max(0, self.memory_mb - other.memory_mb),
            gpu_count=max(0, self.gpu_count - other.gpu_count),
            gpu_memory_mb=max(0, self.gpu_memory_mb - other.gpu_memory_mb),
            custom={k: max(0, v - other.custom.get(k, 0)) for k, v in self.custom.items()},
        )

    def add(self, other: ResourceSpec) -> ResourceSpec:
        """جمع موارد (عند تحرير job)."""
        custom = {**self.custom}
        for k, v in other.custom.items():
            custom[k] = custom.get(k, 0) + v

        return ResourceSpec(
            cpu_cores=self.cpu_cores + other.cpu_cores,
            memory_mb=self.memory_mb + other.memory_mb,
            gpu_count=self.gpu_count + other.gpu_count,
            gpu_memory_mb=self.gpu_memory_mb + other.gpu_memory_mb,
            custom=custom,
        )

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "cpu_cores": self.cpu_cores,
            "memory_mb": self.memory_mb,
            "gpu_count": self.gpu_count,
            "gpu_memory_mb": self.gpu_memory_mb,
            "custom": self.custom,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ResourceSpec:
        """إنشاء من dictionary."""
        return cls(
            cpu_cores=data.get("cpu_cores", 1.0),
            memory_mb=data.get("memory_mb", 512),
            gpu_count=data.get("gpu_count", 0),
            gpu_memory_mb=data.get("gpu_memory_mb", 0),
            custom=data.get("custom", {}),
        )


@dataclass
class ResourceUsage:
    """
    استخدام الموارد الحالي على Worker.

    يُرسل مع كل heartbeat لمراقبة الأداء.
    """
    cpu_percent: float  # نسبة استخدام CPU (0-100)
    memory_used_mb: int
    memory_total_mb: int
    memory_percent: float
    gpus: list[GPUInfo] = field(default_factory=list)
    load_average: tuple[float, float, float] = (0.0, 0.0, 0.0)  # 1, 5, 15 دقيقة
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    network_recv_mb: float = 0.0
    network_sent_mb: float = 0.0

    @property
    def memory_free_mb(self) -> int:
        """الذاكرة الحرة."""
        return self.memory_total_mb - self.memory_used_mb

    @property
    def gpu_count(self) -> int:
        """عدد GPUs."""
        return len(self.gpus)

    @property
    def is_overloaded(self) -> bool:
        """هل الـ Worker محمّل زيادة؟"""
        return self.cpu_percent > 95 or self.memory_percent > 95

    def to_dict(self) -> dict:
        """تحويل إلى dictionary."""
        return {
            "cpu_percent": self.cpu_percent,
            "memory_used_mb": self.memory_used_mb,
            "memory_total_mb": self.memory_total_mb,
            "memory_percent": self.memory_percent,
            "memory_free_mb": self.memory_free_mb,
            "gpus": [
                {
                    "index": g.index,
                    "name": g.name,
                    "uuid": g.uuid,
                    "memory_total_mb": g.memory_total_mb,
                    "memory_free_mb": g.memory_free_mb,
                    "memory_used_mb": g.memory_used_mb,
                    "utilization_percent": g.utilization_percent,
                    "temperature_c": g.temperature_c,
                    "power_draw_w": g.power_draw_w,
                }
                for g in self.gpus
            ],
            "load_average": self.load_average,
            "disk_used_gb": self.disk_used_gb,
            "disk_total_gb": self.disk_total_gb,
            "network_recv_mb": self.network_recv_mb,
            "network_sent_mb": self.network_sent_mb,
            "gpu_count": self.gpu_count,
            "is_overloaded": self.is_overloaded,
        }
