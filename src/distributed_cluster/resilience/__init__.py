# -*- coding: utf-8 -*-
"""
Resilience Module for NebulaCompute.

Provides load shedding, graceful degradation, and capacity planning
for production distributed systems.

وحدة المرونة للحوسبة السحابية.
"""

from .load_shedding import (
    LoadShedder,
    LoadSheddingPolicy,
    LoadSheddingStrategy,
    LoadMetrics,
    PriorityLevel,
    SheddingDecision,
    QueuedRequest,
    create_load_shedder,
)
from .capacity_planning import (
    CapacityPlanner,
    CapacityConfig,
    CapacityForecast,
    CapacityRecommendation,
    GrowthModel,
    ResourceTrend,
    ResourceType,
    ScalingAction,
    create_capacity_planner,
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
