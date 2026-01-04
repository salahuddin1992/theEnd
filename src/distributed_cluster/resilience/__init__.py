# -*- coding: utf-8 -*-
"""
Resilience Module for NebulaCompute.

Provides load shedding, graceful degradation, and capacity planning
for production distributed systems.

وحدة المرونة للحوسبة السحابية.
"""

from .capacity_planning import (
    CapacityConfig,
    CapacityForecast,
    CapacityPlanner,
    CapacityRecommendation,
    GrowthModel,
    ResourceTrend,
    ResourceType,
    ScalingAction,
    create_capacity_planner,
)
from .load_shedding import (
    LoadMetrics,
    LoadShedder,
    LoadSheddingPolicy,
    LoadSheddingStrategy,
    PriorityLevel,
    QueuedRequest,
    SheddingDecision,
    create_load_shedder,
)

__all__ = [
    # Load Shedding
    "LoadShedder",
    "LoadSheddingPolicy",
    "LoadSheddingStrategy",
    "LoadMetrics",
    "PriorityLevel",
    "SheddingDecision",
    "QueuedRequest",
    "create_load_shedder",
    # Capacity Planning
    "CapacityPlanner",
    "CapacityConfig",
    "CapacityForecast",
    "CapacityRecommendation",
    "GrowthModel",
    "ResourceTrend",
    "ResourceType",
    "ScalingAction",
    "create_capacity_planner",
]
