"""Read/Write routing configuration for Advanced Alchemy.

This module provides configuration classes for read/write replica routing,
enabling automatic routing of read operations to read replicas while directing
write operations to the primary database.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Union

__all__ = (
    "ReplicaConfig",
    "RoutingConfig",
    "RoutingStrategy",
)


class RoutingStrategy(Enum):
    """Strategy for selecting read replicas.

    Determines how the routing layer chooses which replica to use
    for read operations when multiple replicas are configured.
    """

    ROUND_ROBIN = auto()
    """Cycle through replicas in order."""

    RANDOM = auto()
    """Select replicas randomly."""


def _default_read_replicas() -> list[Union[str, "ReplicaConfig"]]:
    """Return an empty list for read replica configuration."""
    return []


@dataclass
class ReplicaConfig:
    """Configuration for a single read replica.

    Attributes:
        connection_string: Database connection string for the replica.
        weight: Relative weight for load balancing (higher = more traffic).
            Only used with certain routing strategies.
        name: Optional human-readable name for the replica.
    """

    connection_string: str
    """Connection string for the read replica."""

    weight: int = 1
    """Relative weight for load balancing (higher weight = more traffic)."""

    name: str = ""
    """Optional human-readable name for this replica."""


@dataclass
class RoutingConfig:
    """Read/Write routing configuration.

    This configuration enables automatic routing of database operations
    to primary (write) or replica (read) databases.

    Attributes:
        primary_connection_string: Connection string for the primary (write) database.
        read_replicas: List of read replica connection strings or configs.
        routing_strategy: Strategy for selecting read replicas.
        enabled: Enable/disable routing (all to primary when False).
        sticky_after_write: Stick to primary after first write in context.
        reset_stickiness_on_commit: Reset stickiness after commit.

    Example:
        Basic configuration with a single replica::

            config = RoutingConfig(
                primary_connection_string="postgresql+asyncpg://user:pass@primary:5432/db",
                read_replicas=[
                    "postgresql+asyncpg://user:pass@replica1:5432/db"
                ],
            )

        Configuration with multiple weighted replicas::

            config = RoutingConfig(
                primary_connection_string="postgresql+asyncpg://user:pass@primary:5432/db",
                read_replicas=[
                    ReplicaConfig(
                        connection_string="postgresql+asyncpg://user:pass@replica1:5432/db",
                        weight=2,
                        name="replica-1",
                    ),
                    ReplicaConfig(
                        connection_string="postgresql+asyncpg://user:pass@replica2:5432/db",
                        weight=1,
                        name="replica-2",
                    ),
                ],
                routing_strategy=RoutingStrategy.ROUND_ROBIN,
            )
    """

    primary_connection_string: str
    """Connection string for the primary (write) database."""

    read_replicas: list[Union[str, ReplicaConfig]] = field(default_factory=_default_read_replicas)
    """Read replica connection strings or configs.

    Can be a list of connection strings or :class:`ReplicaConfig` instances
    for more control over replica configuration.
    """

    routing_strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN
    """Strategy for selecting read replicas.

    Defaults to round-robin for even distribution.
    """

    enabled: bool = True
    """Enable/disable routing.

    When ``False``, all traffic goes to the primary database.
    Useful for testing or temporarily disabling routing.
    """

    sticky_after_write: bool = True
    """Stick to primary after first write in context (read-your-writes).

    When ``True`` (default), after any write operation in the current context,
    all subsequent read operations will also use the primary database until
    the transaction is committed. This prevents read-after-write inconsistency
    due to replica lag.
    """

    reset_stickiness_on_commit: bool = True
    """Reset stickiness after commit.

    When ``True`` (default), the sticky-to-primary state is reset after
    a successful commit, allowing subsequent reads to use replicas again.
    """

    def get_replica_connection_strings(self) -> list[str]:
        """Get all replica connection strings.

        Returns:
            List of connection strings for all configured replicas.
        """
        return [
            replica.connection_string if isinstance(replica, ReplicaConfig) else replica
            for replica in self.read_replicas
        ]

    def get_replica_configs(self) -> list[ReplicaConfig]:
        """Get all replicas as ReplicaConfig instances.

        Returns:
            List of :class:`ReplicaConfig` instances.
        """
        return [
            replica if isinstance(replica, ReplicaConfig) else ReplicaConfig(connection_string=replica)
            for replica in self.read_replicas
        ]
