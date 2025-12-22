"""
Control Module - وحدة التحكم الموحد
====================================

وحدة للتحكم الكامل في جميع الحواسيب المتصلة بالشبكة.
تسمح بتوزيع الحمل وتنفيذ الأوامر عن بعد.
"""

from .load_balancer import LoadBalancer, LoadDistribution
from .remote import CommandResult, RemoteCommand, RemoteController

__all__ = [
    "RemoteController",
    "RemoteCommand",
    "CommandResult",
    "LoadBalancer",
    "LoadDistribution",
]
