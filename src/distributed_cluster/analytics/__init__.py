# -*- coding: utf-8 -*-
"""
Predictive Analytics Module for NebulaCompute.

Provides ML-based predictions for job duration, resource usage,
and capacity planning.

نظام التحليلات التنبؤية للحوسبة الموزعة.
"""

from .predictor import (
    JobPredictor,
    PredictionResult,
    PredictionModel,
)
from .forecaster import (
    ResourceForecaster,
    Forecast,
    ForecastHorizon,
)
from .trends import (
    TrendAnalyzer,
    TrendReport,
    TrendDirection,
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
