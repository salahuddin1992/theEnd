# -*- coding: utf-8 -*-
"""
Predictive Analytics Module for NebulaCompute.

Provides ML-based predictions for job duration, resource usage,
and capacity planning.

نظام التحليلات التنبؤية للحوسبة الموزعة.
"""

from .forecaster import (
    Forecast,
    ForecastHorizon,
    ResourceForecaster,
)
from .predictor import (
    JobPredictor,
    PredictionModel,
    PredictionResult,
)
from .trends import (
    TrendAnalyzer,
    TrendDirection,
    TrendReport,
)

__all__ = [
    # Predictor
    "JobPredictor",
    "PredictionResult",
    "PredictionModel",
    # Forecaster
    "ResourceForecaster",
    "Forecast",
    "ForecastHorizon",
    # Trends
    "TrendAnalyzer",
    "TrendReport",
    "TrendDirection",
]
