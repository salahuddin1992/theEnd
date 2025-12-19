"""
Web Dashboard Module - واجهة ويب لمراقبة الكلاستر

Provides a web-based dashboard for:
- Monitoring cluster status
- Managing workers and jobs
- Real-time updates via WebSocket
- Statistics and charts
"""

from .app import WebDashboard, create_app

__all__ = ["create_app", "WebDashboard"]
