"""
Task Router - توجيه المهام في شبكة Mesh

يختار أفضل عقدة لتنفيذ كل مهمة بناءً على:
- الموارد المتاحة
- الحمل الحالي
- القرب (latency)
- العلامات المطلوبة
"""

import random
from enum import Enum
from typing import TYPE_CHECKING, Optional, List, Dict, Any
from dataclasses import dataclass

if TYPE_CHECKING:
    from .node import MeshNode
    from .peer import Peer
    from ..models.job import Job


class RoutingStrategy(str, Enum):
    """استراتيجيات التوجيه"""
    RANDOM = "random"              # اختيار عشوائي
    ROUND_ROBIN = "round_robin"    # بالتناوب
    LEAST_LOADED = "least_loaded"  # الأقل حملاً
    BEST_FIT = "best_fit"          # أفضل تطابق للموارد
    NEAREST = "nearest"            # الأقرب (أقل latency)
    RESOURCE_AWARE = "resource_aware"  # مراعاة الموارد والحمل


@dataclass
class RoutingDecision:
    """قرار التوجيه"""
    job_id: str
    target_node_id: str
    strategy_used: RoutingStrategy
    score: float
    reason: str


class TaskRouter:
    """
    موجه المهام

    يختار أفضل عقدة لتنفيذ كل مهمة
    """

    def __init__(
        self,
        node: "MeshNode",
        strategy: RoutingStrategy = RoutingStrategy.LEAST_LOADED,
    ):
        self.node = node
        self.strategy = strategy
        self._round_robin_index = 0
        self._routing_history: List[RoutingDecision] = []

    async def find_best_peer(self, job: "Job") -> Optional["Peer"]:
        """
        البحث عن أفضل عقدة لتنفيذ المهمة

        Args:
            job: المهمة المراد توجيهها

        Returns:
            أفضل عقدة، أو None إذا لم تتوفر
        """
        candidates = self._get_eligible_peers(job)
        if not candidates:
            return None

        if self.strategy == RoutingStrategy.RANDOM:
            return self._route_random(candidates)
        elif self.strategy == RoutingStrategy.ROUND_ROBIN:
            return self._route_round_robin(candidates)
        elif self.strategy == RoutingStrategy.LEAST_LOADED:
            return self._route_least_loaded(candidates)
        elif self.strategy == RoutingStrategy.BEST_FIT:
            return self._route_best_fit(candidates, job)
        elif self.strategy == RoutingStrategy.NEAREST:
            return self._route_nearest(candidates)
        elif self.strategy == RoutingStrategy.RESOURCE_AWARE:
            return self._route_resource_aware(candidates, job)
        else:
            return self._route_random(candidates)

    def _get_eligible_peers(self, job: "Job") -> List["Peer"]:
        """الحصول على العقد المؤهلة"""
        eligible = []

        for peer in self.node.peers.values():
            # التحقق من الصحة
            if not peer.is_healthy:
                continue

            # التحقق من الموارد
            if not self._has_enough_resources(peer, job):
                continue

            # التحقق من العلامات
            if hasattr(job, "required_tags") and job.required_tags:
                if not job.required_tags.issubset(peer.tags):
                    continue

            eligible.append(peer)

        return eligible

    def _get_job_resources(self, job: "Job") -> "ResourceSpec":
        """الحصول على موارد المهمة"""
        # Job يحتوي على submission.resources
        if hasattr(job, "submission") and job.submission:
            return job.submission.resources
        # للتوافق مع الإصدارات القديمة
        if hasattr(job, "resources"):
            return job.resources
        # افتراضي
        from ..models.resources import ResourceSpec
        return ResourceSpec()

    def _has_enough_resources(self, peer: "Peer", job: "Job") -> bool:
        """التحقق من توفر الموارد"""
        available = peer.available_resources
        required = self._get_job_resources(job)

        return (
            available.cpu_cores >= required.cpu_cores and
            available.memory_mb >= required.memory_mb and
            available.gpu_count >= required.gpu_count
        )

    def _route_random(self, candidates: List["Peer"]) -> "Peer":
        """اختيار عشوائي"""
        return random.choice(candidates)

    def _route_round_robin(self, candidates: List["Peer"]) -> "Peer":
        """اختيار بالتناوب"""
        self._round_robin_index = (self._round_robin_index + 1) % len(candidates)
        return candidates[self._round_robin_index]

    def _route_least_loaded(self, candidates: List["Peer"]) -> "Peer":
        """اختيار الأقل حملاً"""
        return min(candidates, key=lambda p: p.jobs_running)

    def _route_best_fit(self, candidates: List["Peer"], job: "Job") -> "Peer":
        """اختيار أفضل تطابق للموارد (bin packing)"""
        required = self._get_job_resources(job)

        def waste_score(peer: "Peer") -> float:
            available = peer.available_resources
            waste = (
                (available.cpu_cores - required.cpu_cores) +
                (available.memory_mb - required.memory_mb) / 1024 +
                (available.gpu_count - required.gpu_count) * 10
            )
            return waste

        return min(candidates, key=waste_score)

    def _route_nearest(self, candidates: List["Peer"]) -> "Peer":
        """اختيار الأقرب"""
        return min(candidates, key=lambda p: p.latency_ms)

    def _route_resource_aware(self, candidates: List["Peer"], job: "Job") -> "Peer":
        """اختيار مراعي للموارد والحمل معاً"""
        def score(peer: "Peer") -> float:
            # درجة مركبة: حمل + تطابق موارد + latency
            load_score = peer.jobs_running * 10
            resource_score = self._resource_match_score(peer, job)
            latency_score = peer.latency_ms / 100

            return load_score + resource_score + latency_score

        return min(candidates, key=score)

    def _resource_match_score(self, peer: "Peer", job: "Job") -> float:
        """درجة تطابق الموارد"""
        available = peer.available_resources
        required = self._get_job_resources(job)

        cpu_ratio = required.cpu_cores / max(available.cpu_cores, 0.1)
        mem_ratio = required.memory_mb / max(available.memory_mb, 1)
        gpu_ratio = required.gpu_count / max(available.gpu_count, 0.1) if required.gpu_count > 0 else 0

        # أفضل تطابق هو الأقرب لـ 1.0 (استخدام كامل بدون هدر)
        return abs(1 - cpu_ratio) + abs(1 - mem_ratio) + abs(1 - gpu_ratio)

    def record_decision(self, decision: RoutingDecision) -> None:
        """تسجيل قرار التوجيه"""
        self._routing_history.append(decision)
        # الاحتفاظ بآخر 1000 قرار
        if len(self._routing_history) > 1000:
            self._routing_history = self._routing_history[-1000:]

    def stats(self) -> Dict[str, Any]:
        """إحصائيات التوجيه"""
        return {
            "strategy": self.strategy.value,
            "total_decisions": len(self._routing_history),
            "decisions_by_target": self._count_by_target(),
        }

    def _count_by_target(self) -> Dict[str, int]:
        """عدد القرارات لكل عقدة"""
        counts: Dict[str, int] = {}
        for decision in self._routing_history:
            counts[decision.target_node_id] = counts.get(decision.target_node_id, 0) + 1
        return counts
