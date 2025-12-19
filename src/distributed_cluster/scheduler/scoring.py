"""
Scheduler Scoring - خوارزميات التسجيل
========================================

خوارزميات لتسجيل (score) مدى مناسبة Worker لـ Job.

**المبدأ:**
كل Worker يُعطى "نقاط" بناءً على عدة معايير.
الـ Scheduler يختار Worker صاحب أعلى/أقل نقاط حسب السياسة.

**المعايير:**
1. Resource Fit: كم الموارد المتبقية بعد التخصيص
2. Load Balance: توزيع عادل للأحمال
3. Locality: قرب البيانات (إن وُجدت)
4. Affinity/Anti-affinity: تفضيلات التوزيع
5. Priority: أولوية Worker (VIP workers)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from distributed_cluster.models.job import Job
from distributed_cluster.models.worker import WorkerInfo


@dataclass
class ScoringWeights:
    """
    أوزان معايير التسجيل.

    تتحكم في أهمية كل معيار نسبياً.
    """

    resource_fit: float = 1.0  # Best-fit vs Worst-fit
    load_balance: float = 0.5  # توزيع الأحمال
    locality: float = 0.3  # قرب البيانات
    affinity: float = 0.2  # تفضيلات
    freshness: float = 0.1  # حداثة الـ heartbeat
    reliability: float = 0.2  # نسبة النجاح

    def normalize(self) -> ScoringWeights:
        """تطبيع الأوزان (مجموعها = 1)."""
        total = (
            self.resource_fit + self.load_balance + self.locality + self.affinity + self.freshness + self.reliability
        )
        if total == 0:
            return self

        return ScoringWeights(
            resource_fit=self.resource_fit / total,
            load_balance=self.load_balance / total,
            locality=self.locality / total,
            affinity=self.affinity / total,
            freshness=self.freshness / total,
            reliability=self.reliability / total,
        )


@dataclass
class ScoreBreakdown:
    """تفصيل النقاط لكل معيار."""

    worker_id: str
    total_score: float
    resource_fit_score: float = 0.0
    load_balance_score: float = 0.0
    locality_score: float = 0.0
    affinity_score: float = 0.0
    freshness_score: float = 0.0
    reliability_score: float = 0.0
    penalty: float = 0.0
    reason: str = ""


class Scorer(ABC):
    """واجهة لمسجّل (scorer)."""

    @abstractmethod
    def score(
        self,
        job: Job,
        worker: WorkerInfo,
        context: Optional[dict] = None,
    ) -> float:
        """
        حساب نقاط worker لـ job.

        Args:
            job: المهمة
            worker: العامل
            context: سياق إضافي (مثل مواقع البيانات)

        Returns:
            نقاط (أعلى = أفضل)
        """
        pass


class ResourceFitScorer(Scorer):
    """
    تسجيل مدى مناسبة الموارد.

    **Best-Fit (minimize_slack=True):**
    يفضل Worker اللي يترك أقل موارد فائضة.
    مفيد لتقليل التجزئة (fragmentation).

    **Worst-Fit (minimize_slack=False):**
    يفضل Worker صاحب أكثر موارد فائضة.
    مفيد لتوزيع الأحمال.
    """

    def __init__(self, minimize_slack: bool = True):
        self.minimize_slack = minimize_slack

    def score(
        self,
        job: Job,
        worker: WorkerInfo,
        context: Optional[dict] = None,
    ) -> float:
        required = job.submission.resources
        available = worker.available_resources

        # Calculate slack (what remains after allocation)
        cpu_slack = (available.cpu_cores - required.cpu_cores) / max(worker.total_resources.cpu_cores, 1)
        mem_slack = (available.memory_mb - required.memory_mb) / max(worker.total_resources.memory_mb, 1)

        gpu_slack = 0.0
        if worker.total_resources.gpu_count > 0:
            gpu_slack = (available.gpu_count - required.gpu_count) / worker.total_resources.gpu_count

        # Average slack
        avg_slack = (cpu_slack + mem_slack + gpu_slack) / 3

        if self.minimize_slack:
            # Best-fit: lower slack = higher score
            # We want to minimize slack, so invert
            return 1.0 - avg_slack
        else:
            # Worst-fit: higher slack = higher score
            return avg_slack


class LoadBalanceScorer(Scorer):
    """
    تسجيل توزيع الأحمال.

    يفضل Workers الأقل انشغالاً.
    """

    def __init__(self, max_jobs_per_worker: int = 10):
        self.max_jobs_per_worker = max_jobs_per_worker

    def score(
        self,
        job: Job,
        worker: WorkerInfo,
        context: Optional[dict] = None,
    ) -> float:
        active_jobs = len(worker.active_jobs)

        # Score decreases as active jobs increase
        if active_jobs >= self.max_jobs_per_worker:
            return 0.0

        return 1.0 - (active_jobs / self.max_jobs_per_worker)


class LocalityScorer(Scorer):
    """
    تسجيل قرب البيانات.

    إذا البيانات موجودة على Worker (أو قريبة)، يحصل على نقاط أعلى.
    يقلل نقل البيانات عبر الشبكة.
    """

    def score(
        self,
        job: Job,
        worker: WorkerInfo,
        context: Optional[dict] = None,
    ) -> float:
        if not context:
            return 0.5  # Neutral

        # Check if inputs are on this worker
        input_locations = context.get("input_locations", {})
        worker_inputs = 0
        total_inputs = len(job.submission.input_files)

        if total_inputs == 0:
            return 0.5  # No inputs, neutral

        for input_name, location in input_locations.items():
            if location == worker.worker_id or location == worker.hostname:
                worker_inputs += 1

        return worker_inputs / total_inputs


class AffinityScorer(Scorer):
    """
    تسجيل Affinity/Anti-affinity.

    - prefer_workers: زيادة نقاط
    - avoid_workers: خصم نقاط
    - require_tags: تمت معالجتها في الفلترة
    """

    def score(
        self,
        job: Job,
        worker: WorkerInfo,
        context: Optional[dict] = None,
    ) -> float:
        score = 0.5  # Neutral start

        # Check preferred workers
        prefer_workers = job.submission.labels.get("prefer_workers", "").split(",")
        prefer_workers = [w.strip() for w in prefer_workers if w.strip()]

        if prefer_workers:
            if worker.worker_id in prefer_workers or worker.hostname in prefer_workers:
                score += 0.4

        # Check avoided workers
        avoid_workers = job.submission.labels.get("avoid_workers", "").split(",")
        avoid_workers = [w.strip() for w in avoid_workers if w.strip()]

        if avoid_workers:
            if worker.worker_id in avoid_workers or worker.hostname in avoid_workers:
                score -= 0.4

        return max(0.0, min(1.0, score))


class FreshnessScorer(Scorer):
    """
    تسجيل حداثة الـ heartbeat.

    Workers اللي heartbeat حديث يحصلون نقاط أعلى.
    يتجنب Workers اللي ممكن يكونوا غير مستجيبين.
    """

    def __init__(self, max_age_seconds: float = 30.0):
        self.max_age_seconds = max_age_seconds

    def score(
        self,
        job: Job,
        worker: WorkerInfo,
        context: Optional[dict] = None,
    ) -> float:
        from datetime import datetime

        if worker.last_heartbeat is None:
            return 0.0

        age = (datetime.utcnow() - worker.last_heartbeat).total_seconds()

        if age >= self.max_age_seconds:
            return 0.0

        return 1.0 - (age / self.max_age_seconds)


class ReliabilityScorer(Scorer):
    """
    تسجيل موثوقية Worker.

    بناءً على نسبة Jobs الناجحة.
    """

    def __init__(self, min_jobs_for_scoring: int = 5):
        self.min_jobs_for_scoring = min_jobs_for_scoring

    def score(
        self,
        job: Job,
        worker: WorkerInfo,
        context: Optional[dict] = None,
    ) -> float:
        total = worker.completed_jobs_count + worker.failed_jobs_count

        if total < self.min_jobs_for_scoring:
            return 0.5  # Not enough data, neutral

        success_rate = worker.completed_jobs_count / total
        return success_rate


class CompositeScorer:
    """
    مسجّل مركّب يجمع عدة معايير.

    يحسب النقاط النهائية بناءً على الأوزان.
    """

    def __init__(
        self,
        weights: Optional[ScoringWeights] = None,
        minimize_slack: bool = True,  # Best-fit by default
    ):
        self.weights = (weights or ScoringWeights()).normalize()

        # Initialize scorers
        self.scorers = {
            "resource_fit": ResourceFitScorer(minimize_slack=minimize_slack),
            "load_balance": LoadBalanceScorer(),
            "locality": LocalityScorer(),
            "affinity": AffinityScorer(),
            "freshness": FreshnessScorer(),
            "reliability": ReliabilityScorer(),
        }

    def score(
        self,
        job: Job,
        worker: WorkerInfo,
        context: Optional[dict] = None,
    ) -> ScoreBreakdown:
        """
        حساب النقاط الكاملة مع التفصيل.

        Returns:
            ScoreBreakdown مع كل التفاصيل
        """
        scores = {}

        # Calculate individual scores
        scores["resource_fit"] = self.scorers["resource_fit"].score(job, worker, context)
        scores["load_balance"] = self.scorers["load_balance"].score(job, worker, context)
        scores["locality"] = self.scorers["locality"].score(job, worker, context)
        scores["affinity"] = self.scorers["affinity"].score(job, worker, context)
        scores["freshness"] = self.scorers["freshness"].score(job, worker, context)
        scores["reliability"] = self.scorers["reliability"].score(job, worker, context)

        # Calculate weighted total
        total = (
            scores["resource_fit"] * self.weights.resource_fit
            + scores["load_balance"] * self.weights.load_balance
            + scores["locality"] * self.weights.locality
            + scores["affinity"] * self.weights.affinity
            + scores["freshness"] * self.weights.freshness
            + scores["reliability"] * self.weights.reliability
        )

        # Apply penalties
        penalty = 0.0

        # Penalty for overloaded workers
        if worker.current_usage and worker.current_usage.is_overloaded:
            penalty += 0.2

        # Penalty for workers in draining status
        from distributed_cluster.models.worker import WorkerStatus

        if worker.status == WorkerStatus.DRAINING:
            penalty += 0.5

        final_score = max(0.0, total - penalty)

        return ScoreBreakdown(
            worker_id=worker.worker_id,
            total_score=final_score,
            resource_fit_score=scores["resource_fit"],
            load_balance_score=scores["load_balance"],
            locality_score=scores["locality"],
            affinity_score=scores["affinity"],
            freshness_score=scores["freshness"],
            reliability_score=scores["reliability"],
            penalty=penalty,
        )

    def rank_workers(
        self,
        job: Job,
        workers: List[WorkerInfo],
        context: Optional[dict] = None,
        top_n: Optional[int] = None,
    ) -> List[ScoreBreakdown]:
        """
        ترتيب Workers حسب النقاط.

        Args:
            job: المهمة
            workers: قائمة Workers
            context: سياق إضافي
            top_n: أعلى N فقط (None = كلهم)

        Returns:
            قائمة مرتبة من الأعلى للأقل
        """
        scores = [self.score(job, worker, context) for worker in workers]
        scores.sort(key=lambda s: s.total_score, reverse=True)

        if top_n:
            return scores[:top_n]
        return scores


# Predefined scoring profiles
SCORING_PROFILES = {
    "best_fit": ScoringWeights(
        resource_fit=1.0,
        load_balance=0.3,
        locality=0.2,
        affinity=0.2,
        freshness=0.1,
        reliability=0.2,
    ),
    "spread": ScoringWeights(
        resource_fit=0.3,
        load_balance=1.0,
        locality=0.2,
        affinity=0.2,
        freshness=0.1,
        reliability=0.2,
    ),
    "locality_first": ScoringWeights(
        resource_fit=0.3,
        load_balance=0.3,
        locality=1.0,
        affinity=0.2,
        freshness=0.1,
        reliability=0.2,
    ),
    "reliable": ScoringWeights(
        resource_fit=0.5,
        load_balance=0.3,
        locality=0.2,
        affinity=0.2,
        freshness=0.2,
        reliability=1.0,
    ),
}
