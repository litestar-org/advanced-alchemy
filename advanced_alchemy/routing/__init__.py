"""Read/Write routing support for Advanced Alchemy.

This module provides automatic routing of read operations to read replicas
while directing write operations to the primary database.

Example:
    Basic usage with routing configuration::

        from advanced_alchemy.config import SQLAlchemyAsyncConfig
        from advanced_alchemy.config.routing import RoutingConfig

        config = SQLAlchemyAsyncConfig(
            routing_config=RoutingConfig(
                primary_connection_string="postgresql+asyncpg://user:pass@primary:5432/db",
                read_replicas=[
                    "postgresql+asyncpg://user:pass@replica1:5432/db",
                    "postgresql+asyncpg://user:pass@replica2:5432/db",
                ],
            ),
        )

    Using context managers for explicit control::

        from advanced_alchemy.routing import (
            primary_context,
            replica_context,
        )

        # Force all operations to primary
        with primary_context():
            user = await repo.get(user_id)

        # Allow reads on replicas even after writes
        with replica_context():
            users = await repo.list()
"""

from __future__ import annotations

from advanced_alchemy.routing.context import (
    force_primary_var,
    primary_context,
    replica_context,
    reset_routing_context,
    stick_to_primary_var,
)
from advanced_alchemy.routing.maker import RoutingAsyncSessionMaker, RoutingSyncSessionMaker
from advanced_alchemy.routing.selectors import RandomSelector, ReplicaSelector, RoundRobinSelector
from advanced_alchemy.routing.session import RoutingAsyncSession, RoutingSession

__all__ = (
    # Selectors
    "RandomSelector",
    "ReplicaSelector",
    "RoundRobinSelector",
    # Sessions
    "RoutingAsyncSession",
    # Session makers
    "RoutingAsyncSessionMaker",
    "RoutingSession",
    "RoutingSyncSessionMaker",
    # Context managers and variables
    "force_primary_var",
    "primary_context",
    "replica_context",
    "reset_routing_context",
    "stick_to_primary_var",
)
