# -*- coding: utf-8 -*-
"""
GraphQL API Module for NebulaCompute.

Provides a flexible GraphQL interface for querying and mutating
cluster resources.

واجهة GraphQL للحوسبة الموزعة.
"""

from .schema import (
    create_schema,
    JobType,
    WorkerType,
    ClusterType,
)
from .resolvers import (
    QueryResolver,
    MutationResolver,
)
from .subscriptions import (
    SubscriptionManager,
    JobSubscription,
    ClusterSubscription,
)
from .server import (
    GraphQLServer,
    GraphQLConfig,
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
