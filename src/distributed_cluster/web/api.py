"""
Web API Module - Backwards compatibility module

This module re-exports create_app from app.py for backwards compatibility.
"""

from .app import WebDashboard, create_app

__all__ = ["create_app", "WebDashboard"]
