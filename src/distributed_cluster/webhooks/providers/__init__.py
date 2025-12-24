"""
Webhook Providers - مزودي الـ Webhooks
======================================

Provider Implementations
------------------------

This module provides webhook provider implementations.

يوفر هذا الملف تطبيقات مزودي الـ webhooks.

Author: Distributed Cluster Team
License: MIT
"""

from distributed_cluster.webhooks.providers.discord import DiscordWebhook
from distributed_cluster.webhooks.providers.slack import SlackWebhook
from distributed_cluster.webhooks.providers.teams import TeamsWebhook
from distributed_cluster.webhooks.providers.custom import CustomWebhook

__all__ = [
    "DiscordWebhook",
    "SlackWebhook",
    "TeamsWebhook",
    "CustomWebhook",
]
