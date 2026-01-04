# -*- coding: utf-8 -*-
"""
GraphQL API Module for NebulaCompute.

Provides a flexible GraphQL interface for querying and mutating
cluster resources.

واجهة GraphQL للحوسبة الموزعة.
"""

from .resolvers import (
    MutationResolver,
    QueryResolver,
)
from .schema import (
    ClusterType,
    JobType,
    WorkerType,
    create_schema,
)
from .server import (
    GraphQLConfig,
    GraphQLServer,
)
from .subscriptions import (
    ClusterSubscription,
    JobSubscription,
    SubscriptionManager,
)

__all__ = [
    # Schema
    "create_schema",
    "JobType",
    "WorkerType",
    "ClusterType",
    # Resolvers
    "QueryResolver",
    "MutationResolver",
    # Subscriptions
    "SubscriptionManager",
    "JobSubscription",
    "ClusterSubscription",
    # Server
    "GraphQLServer",
    "GraphQLConfig",
]
