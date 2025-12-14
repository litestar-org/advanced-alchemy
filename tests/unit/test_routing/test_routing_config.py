"""Unit tests for routing configuration classes.

Tests the configuration classes used for read/write routing setup.
"""

from __future__ import annotations

from advanced_alchemy.config.routing import ReplicaConfig, RoutingConfig, RoutingStrategy


def test_routing_strategy_enum() -> None:
    """Test that RoutingStrategy enum has expected values."""
    assert RoutingStrategy.ROUND_ROBIN is not None
    assert RoutingStrategy.RANDOM is not None
    assert len(RoutingStrategy) == 2


def test_replica_config_defaults() -> None:
    """Test ReplicaConfig with default values."""
    replica = ReplicaConfig(connection_string="postgresql://replica:5432/db")

    assert replica.connection_string == "postgresql://replica:5432/db"
    assert replica.weight == 1
    assert replica.name == ""


def test_replica_config_custom_values() -> None:
    """Test ReplicaConfig with custom values."""
    replica = ReplicaConfig(
        connection_string="postgresql://replica:5432/db",
        weight=5,
        name="replica-1",
    )

    assert replica.connection_string == "postgresql://replica:5432/db"
    assert replica.weight == 5
    assert replica.name == "replica-1"


def test_routing_config_defaults() -> None:
    """Test RoutingConfig with default values."""
    config = RoutingConfig(primary_connection_string="postgresql://primary:5432/db")

    assert config.primary_connection_string == "postgresql://primary:5432/db"
    assert config.read_replicas == []
    assert config.routing_strategy == RoutingStrategy.ROUND_ROBIN
    assert config.enabled is True
    assert config.sticky_after_write is True
    assert config.reset_stickiness_on_commit is True


def test_routing_config_with_string_replicas() -> None:
    """Test RoutingConfig with replica connection strings."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[
            "postgresql://replica1:5432/db",
            "postgresql://replica2:5432/db",
        ],
    )

    assert len(config.read_replicas) == 2
    assert config.read_replicas[0] == "postgresql://replica1:5432/db"
    assert config.read_replicas[1] == "postgresql://replica2:5432/db"


def test_routing_config_with_replica_configs() -> None:
    """Test RoutingConfig with ReplicaConfig objects."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[
            ReplicaConfig(
                connection_string="postgresql://replica1:5432/db",
                weight=2,
                name="replica-1",
            ),
            ReplicaConfig(
                connection_string="postgresql://replica2:5432/db",
                weight=1,
                name="replica-2",
            ),
        ],
    )

    assert len(config.read_replicas) == 2
    assert isinstance(config.read_replicas[0], ReplicaConfig)
    assert isinstance(config.read_replicas[1], ReplicaConfig)


def test_routing_config_mixed_replicas() -> None:
    """Test RoutingConfig with mixed string and ReplicaConfig replicas."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[
            "postgresql://replica1:5432/db",
            ReplicaConfig(
                connection_string="postgresql://replica2:5432/db",
                weight=2,
                name="replica-2",
            ),
        ],
    )

    assert len(config.read_replicas) == 2
    assert isinstance(config.read_replicas[0], str)
    assert isinstance(config.read_replicas[1], ReplicaConfig)


def test_routing_config_custom_strategy() -> None:
    """Test RoutingConfig with custom routing strategy."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
        routing_strategy=RoutingStrategy.RANDOM,
    )

    assert config.routing_strategy == RoutingStrategy.RANDOM


def test_routing_config_disabled() -> None:
    """Test RoutingConfig with routing disabled."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
        enabled=False,
    )

    assert config.enabled is False


def test_routing_config_no_sticky_after_write() -> None:
    """Test RoutingConfig with sticky_after_write disabled."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
        sticky_after_write=False,
    )

    assert config.sticky_after_write is False


def test_routing_config_no_reset_on_commit() -> None:
    """Test RoutingConfig with reset_stickiness_on_commit disabled."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
        reset_stickiness_on_commit=False,
    )

    assert config.reset_stickiness_on_commit is False


def test_get_replica_connection_strings_empty() -> None:
    """Test get_replica_connection_strings with no replicas."""
    config = RoutingConfig(primary_connection_string="postgresql://primary:5432/db")

    connection_strings = config.get_replica_connection_strings()

    assert connection_strings == []


def test_get_replica_connection_strings_from_strings() -> None:
    """Test get_replica_connection_strings with string replicas."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[
            "postgresql://replica1:5432/db",
            "postgresql://replica2:5432/db",
        ],
    )

    connection_strings = config.get_replica_connection_strings()

    assert connection_strings == [
        "postgresql://replica1:5432/db",
        "postgresql://replica2:5432/db",
    ]


def test_get_replica_connection_strings_from_configs() -> None:
    """Test get_replica_connection_strings with ReplicaConfig objects."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[
            ReplicaConfig(connection_string="postgresql://replica1:5432/db"),
            ReplicaConfig(connection_string="postgresql://replica2:5432/db"),
        ],
    )

    connection_strings = config.get_replica_connection_strings()

    assert connection_strings == [
        "postgresql://replica1:5432/db",
        "postgresql://replica2:5432/db",
    ]


def test_get_replica_connection_strings_mixed() -> None:
    """Test get_replica_connection_strings with mixed replicas."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[
            "postgresql://replica1:5432/db",
            ReplicaConfig(connection_string="postgresql://replica2:5432/db"),
        ],
    )

    connection_strings = config.get_replica_connection_strings()

    assert connection_strings == [
        "postgresql://replica1:5432/db",
        "postgresql://replica2:5432/db",
    ]


def test_get_replica_configs_empty() -> None:
    """Test get_replica_configs with no replicas."""
    config = RoutingConfig(primary_connection_string="postgresql://primary:5432/db")

    replica_configs = config.get_replica_configs()

    assert replica_configs == []


def test_get_replica_configs_from_strings() -> None:
    """Test get_replica_configs converts strings to ReplicaConfig objects."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[
            "postgresql://replica1:5432/db",
            "postgresql://replica2:5432/db",
        ],
    )

    replica_configs = config.get_replica_configs()

    assert len(replica_configs) == 2
    assert all(isinstance(r, ReplicaConfig) for r in replica_configs)
    assert replica_configs[0].connection_string == "postgresql://replica1:5432/db"
    assert replica_configs[1].connection_string == "postgresql://replica2:5432/db"
    # Default values should be set
    assert replica_configs[0].weight == 1
    assert replica_configs[0].name == ""


def test_get_replica_configs_from_configs() -> None:
    """Test get_replica_configs returns ReplicaConfig objects as-is."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[
            ReplicaConfig(
                connection_string="postgresql://replica1:5432/db",
                weight=2,
                name="replica-1",
            ),
            ReplicaConfig(
                connection_string="postgresql://replica2:5432/db",
                weight=1,
                name="replica-2",
            ),
        ],
    )

    replica_configs = config.get_replica_configs()

    assert len(replica_configs) == 2
    assert replica_configs[0].weight == 2
    assert replica_configs[0].name == "replica-1"
    assert replica_configs[1].weight == 1
    assert replica_configs[1].name == "replica-2"


def test_get_replica_configs_mixed() -> None:
    """Test get_replica_configs with mixed string and ReplicaConfig replicas."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[
            "postgresql://replica1:5432/db",
            ReplicaConfig(
                connection_string="postgresql://replica2:5432/db",
                weight=3,
                name="replica-2",
            ),
        ],
    )

    replica_configs = config.get_replica_configs()

    assert len(replica_configs) == 2
    assert all(isinstance(r, ReplicaConfig) for r in replica_configs)
    # String converted to ReplicaConfig with defaults
    assert replica_configs[0].connection_string == "postgresql://replica1:5432/db"
    assert replica_configs[0].weight == 1
    assert replica_configs[0].name == ""
    # ReplicaConfig preserved
    assert replica_configs[1].connection_string == "postgresql://replica2:5432/db"
    assert replica_configs[1].weight == 3
    assert replica_configs[1].name == "replica-2"
