"""
Load Balancer - موزع الحمل
===========================

توزيع الحمل بين الحواسيب المتصلة بنسب محددة.
"""

import asyncio
from dataclasses import dataclass, field

import httpx


@dataclass
class LoadDistribution:
    """
    توزيع الحمل لحاسوب واحد

    Attributes:
        worker_id: معرف الـ Worker
        percentage: نسبة الحمل (0-100)
        max_jobs: أقصى عدد من المهام المتزامنة
        priority: الأولوية (أعلى = يستلم مهام أولاً)
    """
    worker_id: str
    percentage: int = 100  # نسبة الحمل
    max_jobs: int = 0      # 0 = غير محدود
    priority: int = 1      # أولوية (1-10)
    enabled: bool = True   # مفعّل


@dataclass
class ClusterLoad:
    """حالة الحمل للكلاستر"""
    total_workers: int
    active_workers: int
    total_jobs: int
    running_jobs: int
    pending_jobs: int
    distributions: list[LoadDistribution] = field(default_factory=list)


class LoadBalancer:
    """
    موزع الحمل بين الحواسيب

    يسمح بتحديد نسبة الحمل لكل حاسوب.

    مثال:
        balancer = LoadBalancer("http://master:8765")

        # توزيع: 95% على الحاسوب الثاني، 5% على الرئيسي
        await balancer.set_distribution({
            "my-pc": 5,
            "second-pc": 95,
        })

        # أو باستخدام الطريقة السريعة
        await balancer.offload_to("second-pc", percentage=95)
    """

    def __init__(self, master_url: str = "http://localhost:8765"):
        self.master_url = master_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self._distributions: dict[str, LoadDistribution] = {}

    async def close(self):
        """إغلاق الاتصال"""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def get_workers(self) -> list[dict]:
        """الحصول على قائمة Workers"""
        try:
            response = await self.client.get(f"{self.master_url}/api/workers")
            response.raise_for_status()
            return response.json()
        except Exception:
            return []

    async def get_cluster_load(self) -> ClusterLoad:
        """الحصول على حالة الحمل الحالية"""
        try:
            workers = await self.get_workers()
            jobs_response = await self.client.get(f"{self.master_url}/api/jobs")

            jobs = jobs_response.json() if jobs_response.status_code == 200 else []

            running = sum(1 for j in jobs if j.get("status") == "running")
            pending = sum(1 for j in jobs if j.get("status") == "pending")

            return ClusterLoad(
                total_workers=len(workers),
                active_workers=sum(1 for w in workers if w.get("status") == "online"),
                total_jobs=len(jobs),
                running_jobs=running,
                pending_jobs=pending,
                distributions=list(self._distributions.values()),
            )
        except Exception:
            return ClusterLoad(0, 0, 0, 0, 0)

    async def set_distribution(self, percentages: dict[str, int]) -> bool:
        """
        تعيين توزيع الحمل

        Args:
            percentages: قاموس {worker_id: percentage}

        مثال:
            await balancer.set_distribution({
                "my-pc": 5,
                "second-pc": 95,
            })
        """
        # التحقق من أن المجموع = 100
        total = sum(percentages.values())
        if total != 100:
            # تطبيع النسب
            factor = 100.0 / total if total > 0 else 1
            percentages = {k: int(v * factor) for k, v in percentages.items()}

        self._distributions.clear()
        for worker_id, percentage in percentages.items():
            self._distributions[worker_id] = LoadDistribution(
                worker_id=worker_id,
                percentage=percentage,
                priority=10 if percentage >= 50 else 5 if percentage >= 20 else 1,
            )

        # إرسال التوزيع للـ Master
        try:
            response = await self.client.post(
                f"{self.master_url}/api/scheduler/distribution",
                json={
                    "distributions": [
                        {
                            "worker_id": d.worker_id,
                            "percentage": d.percentage,
                            "priority": d.priority,
                            "max_jobs": d.max_jobs,
                        }
                        for d in self._distributions.values()
                    ]
                },
            )
            return response.status_code == 200
        except Exception:
            # حتى لو فشل الإرسال، نحتفظ بالتوزيع محلياً
            return True

    async def offload_to(
        self,
        worker_id: str,
        percentage: int = 95,
        local_id: str = "local",
    ) -> bool:
        """
        نقل الحمل لحاسوب آخر

        Args:
            worker_id: معرف الحاسوب المستهدف
            percentage: نسبة الحمل للنقل
            local_id: معرف الحاسوب المحلي

        مثال:
            # نقل 95% من الحمل للحاسوب الثاني
            await balancer.offload_to("second-pc", percentage=95)
        """
        return await self.set_distribution({
            local_id: 100 - percentage,
            worker_id: percentage,
        })

    async def offload_to_multiple(
        self,
        workers: dict[str, int],
        local_percentage: int = 5,
        local_id: str = "local",
    ) -> bool:
        """
        نقل الحمل لعدة حواسيب

        Args:
            workers: قاموس {worker_id: percentage}
            local_percentage: النسبة المتبقية للحاسوب المحلي
            local_id: معرف الحاسوب المحلي

        مثال:
            # توزيع على 3 حواسيب
            await balancer.offload_to_multiple({
                "pc-2": 47,
                "pc-3": 48,
            }, local_percentage=5)
        """
        distribution = {local_id: local_percentage}
        distribution.update(workers)
        return await self.set_distribution(distribution)

    async def balance_equally(self) -> bool:
        """توزيع الحمل بالتساوي على جميع Workers"""
        workers = await self.get_workers()
        if not workers:
            return False

        percentage_each = 100 // len(workers)
        remainder = 100 % len(workers)

        distribution = {}
        for i, worker in enumerate(workers):
            worker_id = worker.get("worker_id", f"worker-{i}")
            distribution[worker_id] = percentage_each + (1 if i < remainder else 0)

        return await self.set_distribution(distribution)

    async def disable_worker(self, worker_id: str) -> bool:
        """تعطيل Worker مؤقتاً"""
        if worker_id in self._distributions:
            self._distributions[worker_id].enabled = False
            self._distributions[worker_id].percentage = 0
        return True

    async def enable_worker(self, worker_id: str, percentage: int = 50) -> bool:
        """تفعيل Worker"""
        if worker_id in self._distributions:
            self._distributions[worker_id].enabled = True
            self._distributions[worker_id].percentage = percentage
        else:
            self._distributions[worker_id] = LoadDistribution(
                worker_id=worker_id,
                percentage=percentage,
            )
        return True

    def get_distribution_summary(self) -> str:
        """الحصول على ملخص التوزيع"""
        if not self._distributions:
            return "لا يوجد توزيع محدد"

        lines = ["توزيع الحمل الحالي:"]
        for d in sorted(self._distributions.values(), key=lambda x: -x.percentage):
            status = "✓" if d.enabled else "✗"
            lines.append(f"  {status} {d.worker_id}: {d.percentage}%")
        return "\n".join(lines)


async def quick_offload(target: str, percentage: int = 95, master_url: str = "http://localhost:8765") -> bool:
    """
    نقل سريع للحمل - أمر واحد فقط

    مثال:
        from distributed_cluster.control import quick_offload

        # نقل 95% من الحمل للحاسوب الثاني
        await quick_offload("second-pc", 95)
    """
    async with LoadBalancer(master_url) as balancer:
        return await balancer.offload_to(target, percentage)


def offload_sync(target: str, percentage: int = 95, master_url: str = "http://localhost:8765") -> bool:
    """نسخة متزامنة من quick_offload"""
    return asyncio.run(quick_offload(target, percentage, master_url))
