"""Read/Write routing configuration for Advanced Alchemy.

This module provides configuration classes for read/write replica routing,
enabling automatic routing of read operations to read replicas while directing
write operations to the primary database.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional, Union

__all__ = (
    "EngineGroupConfig",
    "ReplicaConfig",
    "RoutingBehavior",
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
class EngineGroupConfig:
    """Engine group topology configuration.

    Defines the available engine groups and which groups to use
    for read and write operations.
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


@dataclass
class RoutingBehavior:
    """Routing behavior configuration.

    Controls how the routing layer selects engines and manages
    read-your-writes consistency.
    """

    routing_strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN
    """Strategy for selecting engines within a group."""

    enabled: bool = True
    """Enable/disable routing."""

    sticky_after_write: bool = True
    """Stick to writer after first write in context (read-your-writes)."""

    reset_stickiness_on_commit: bool = True
    """Reset stickiness after commit."""


class RoutingConfig:
    """Read/Write routing configuration.

    This configuration enables automatic routing of database operations
    to different engine groups (e.g., writer, reader, analytics).

    Accepts both legacy keyword arguments (``engines``, ``default_group``,
    ``read_group``, ``routing_strategy``, ``enabled``, ``sticky_after_write``,
    ``reset_stickiness_on_commit``) and the new structured arguments
    (``engine_groups``, ``behavior``) for backward compatibility.
    """

    def __init__(
        self,
        primary_connection_string: Optional[str] = None,
        read_replicas: Optional[list[Union[str, EngineConfig]]] = None,
        engine_groups: Optional[EngineGroupConfig] = None,
        behavior: Optional[RoutingBehavior] = None,
        engines: Optional[dict[str, list[Union[str, EngineConfig]]]] = None,
        default_group: Optional[str] = None,
        read_group: Optional[str] = None,
        routing_strategy: Optional[RoutingStrategy] = None,
        enabled: Optional[bool] = None,
        sticky_after_write: Optional[bool] = None,
        reset_stickiness_on_commit: Optional[bool] = None,
    ) -> None:
        self.primary_connection_string = primary_connection_string
        self.read_replicas = read_replicas if read_replicas is not None else _default_read_replicas()

        if engine_groups is not None:
            self.engine_groups = engine_groups
        else:
            eg_kwargs: dict[str, Any] = {}
            if engines is not None:
                eg_kwargs["engines"] = engines
            if default_group is not None:
                eg_kwargs["default_group"] = default_group
            if read_group is not None:
                eg_kwargs["read_group"] = read_group
            self.engine_groups = EngineGroupConfig(**eg_kwargs)

        if behavior is not None:
            self.behavior = behavior
        else:
            bh_kwargs: dict[str, Any] = {}
            if routing_strategy is not None:
                bh_kwargs["routing_strategy"] = routing_strategy
            if enabled is not None:
                bh_kwargs["enabled"] = enabled
            if sticky_after_write is not None:
                bh_kwargs["sticky_after_write"] = sticky_after_write
            if reset_stickiness_on_commit is not None:
                bh_kwargs["reset_stickiness_on_commit"] = reset_stickiness_on_commit
            self.behavior = RoutingBehavior(**bh_kwargs)

        self.__post_init__()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"primary_connection_string={self.primary_connection_string!r}, "
            f"read_replicas={self.read_replicas!r}, "
            f"engine_groups={self.engine_groups!r}, "
            f"behavior={self.behavior!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RoutingConfig):
            return NotImplemented
        return (
            self.primary_connection_string == other.primary_connection_string
            and self.read_replicas == other.read_replicas
            and self.engine_groups == other.engine_groups
            and self.behavior == other.behavior
        )

    __hash__ = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Normalize configuration."""
        # Migrate legacy config to engines map
        if self.primary_connection_string:
            if self.engine_groups.default_group not in self.engine_groups.engines:
                self.engine_groups.engines[self.engine_groups.default_group] = []
            self.engine_groups.engines[self.engine_groups.default_group].insert(
                0, EngineConfig(connection_string=self.primary_connection_string, name="primary")
            )

        if self.read_replicas:
            if self.engine_groups.read_group not in self.engine_groups.engines:
                self.engine_groups.engines[self.engine_groups.read_group] = []
            self.engine_groups.engines[self.engine_groups.read_group].extend(self.read_replicas)

    def get_engine_configs(self, group: str) -> list[EngineConfig]:
        """Get engine configs for a specific group.

        Args:
            group: Name of the engine group.

        Returns:
            List of :class:`EngineConfig` instances.
        """
        if group not in self.engine_groups.engines:
            return []

        configs = self.engine_groups.engines[group]
        return [
            config if isinstance(config, EngineConfig) else EngineConfig(connection_string=config) for config in configs
        ]
