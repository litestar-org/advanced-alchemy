"""Read/Write routing configuration for Advanced Alchemy.

This module provides configuration classes for read/write replica routing,
enabling automatic routing of read operations to read replicas while directing
write operations to the primary database.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Union

__all__ = (
    "ReplicaConfig",
    "RoutingConfig",
    "RoutingStrategy",
)


class RoutingStrategy(Enum):
    """Strategy for selecting engines from a group.

    Determines how the routing layer chooses which engine to use
    when multiple engines are configured for a routing group.
    """

    ROUND_ROBIN = auto()
    """Cycle through engines in order."""

    RANDOM = auto()
    """Select engines randomly."""


def _default_read_replicas() -> list[Union[str, "EngineConfig"]]:
    """Return an empty list for read replica configuration."""
    return []


def _default_engines() -> dict[str, list[Union[str, "EngineConfig"]]]:
    """Return default empty engines map."""
    return {}


@dataclass
class EngineConfig:
    """Configuration for a single database engine."""

    connection_string: str
    """Connection string for the engine."""

    weight: int = 1
    """Relative weight for load balancing (higher weight = more traffic)."""

    name: str = ""
    """Optional human-readable name for this engine."""


# Alias for backward compatibility
ReplicaConfig = EngineConfig


@dataclass
class RoutingConfig:
    """Read/Write routing configuration.

    This configuration enables automatic routing of database operations
    to different engine groups (e.g., writer, reader, analytics).
    """

    primary_connection_string: Optional[str] = None
    """Legacy: Connection string for the primary (write) database.
    Mapped to ``engines[default_group]``.
    """

    read_replicas: list[Union[str, EngineConfig]] = field(default_factory=_default_read_replicas)
    """Legacy: Read replica connection strings or configs.
    Mapped to ``engines[read_group]``.
    """

    engines: dict[str, list[Union[str, EngineConfig]]] = field(default_factory=_default_engines)
    """Dictionary mapping group names to lists of engine configs.

    Example:
        .. code-block:: python

            {
                "writer": ["postgres://primary"],
                "reader": ["postgres://rep1", "postgres://rep2"],
                "analytics": ["postgres://warehouse"]
            }
    """

    default_group: str = "default"
    """Name of the group to use for write operations."""

    read_group: str = "read"
    """Name of the group to use for read operations."""

    routing_strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN
    """Strategy for selecting engines within a group."""

    enabled: bool = True
    """Enable/disable routing."""

    sticky_after_write: bool = True
    """Stick to writer after first write in context (read-your-writes)."""

    reset_stickiness_on_commit: bool = True
    """Reset stickiness after commit."""

    def __post_init__(self) -> None:
        """Normalize configuration."""
        # Migrate legacy config to engines map
        if self.primary_connection_string:
            if self.default_group not in self.engines:
                self.engines[self.default_group] = []
            self.engines[self.default_group].insert(
                0, EngineConfig(connection_string=self.primary_connection_string, name="primary")
            )

        if self.read_replicas:
            if self.read_group not in self.engines:
                self.engines[self.read_group] = []
            self.engines[self.read_group].extend(self.read_replicas)

    def get_engine_configs(self, group: str) -> list[EngineConfig]:
        """Get engine configs for a specific group.

        Args:
            group: Name of the engine group.

        Returns:
            List of :class:`EngineConfig` instances.
        """
        if group not in self.engines:
            return []

        configs = self.engines[group]
        return [
            config if isinstance(config, EngineConfig) else EngineConfig(connection_string=config) for config in configs
        ]
