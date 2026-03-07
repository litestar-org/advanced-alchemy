"""Unit tests for routing context variables and context managers.

Tests the context-based state management for routing decisions.
"""

import pytest

from advanced_alchemy.routing.context import (
    force_primary_var,
    primary_context,
    replica_context,
    reset_routing_context,
    set_sticky_primary,
    should_use_primary,
    stick_to_primary_var,
)


def test_context_vars_default_values() -> None:
    """Test that context variables have correct default values."""
    reset_routing_context()

    assert stick_to_primary_var.get() is False
    assert force_primary_var.get() is False


def test_set_sticky_primary() -> None:
    """Test that set_sticky_primary sets the sticky flag."""
    reset_routing_context()

    set_sticky_primary()

    assert stick_to_primary_var.get() is True


def test_reset_routing_context() -> None:
    """Test that reset_routing_context resets all flags."""
    stick_to_primary_var.set(True)
    force_primary_var.set(True)

    assert stick_to_primary_var.get() is True
    assert force_primary_var.get() is True

    reset_routing_context()

    assert stick_to_primary_var.get() is False
    assert force_primary_var.get() is False


def test_should_use_primary_when_not_forced() -> None:
    """Test should_use_primary returns False when no flags are set."""
    reset_routing_context()

    assert should_use_primary() is False


def test_should_use_primary_when_sticky() -> None:
    """Test should_use_primary returns True when sticky flag is set."""
    reset_routing_context()
    stick_to_primary_var.set(True)

    assert should_use_primary() is True


def test_should_use_primary_when_forced() -> None:
    """Test should_use_primary returns True when force flag is set."""
    reset_routing_context()
    force_primary_var.set(True)

    assert should_use_primary() is True


def test_should_use_primary_when_both_set() -> None:
    """Test should_use_primary returns True when both flags are set."""
    reset_routing_context()
    stick_to_primary_var.set(True)
    force_primary_var.set(True)

    assert should_use_primary() is True


def test_primary_context_forces_primary() -> None:
    """Test that primary_context sets force_primary flag."""
    reset_routing_context()

    assert force_primary_var.get() is False

    with primary_context():
        assert force_primary_var.get() is True

    assert force_primary_var.get() is False


def test_primary_context_resets_on_exit() -> None:
    """Test that primary_context properly resets the flag on exit."""
    reset_routing_context()

    with primary_context():
        assert force_primary_var.get() is True

    assert force_primary_var.get() is False


def test_primary_context_resets_on_exception() -> None:
    """Test that primary_context resets the flag even on exception."""
    reset_routing_context()

    def _raise_in_primary_context() -> None:
        with primary_context():
            assert force_primary_var.get() is True
            raise ValueError("test exception")

    with pytest.raises(ValueError):
        _raise_in_primary_context()

    assert force_primary_var.get() is False


def test_primary_context_nested() -> None:
    """Test that primary_context works correctly when nested."""
    reset_routing_context()

    with primary_context():
        assert force_primary_var.get() is True

        with primary_context():
            assert force_primary_var.get() is True

        assert force_primary_var.get() is True

    assert force_primary_var.get() is False


def test_replica_context_clears_sticky_flag() -> None:
    """Test that replica_context clears the sticky flag."""
    reset_routing_context()
    stick_to_primary_var.set(True)

    assert stick_to_primary_var.get() is True

    with replica_context():
        assert stick_to_primary_var.get() is False

    assert stick_to_primary_var.get() is True


def test_replica_context_clears_force_flag() -> None:
    """Test that replica_context clears the force flag."""
    reset_routing_context()
    force_primary_var.set(True)

    assert force_primary_var.get() is True

    with replica_context():
        assert force_primary_var.get() is False

    assert force_primary_var.get() is True


def test_replica_context_clears_both_flags() -> None:
    """Test that replica_context clears both flags."""
    reset_routing_context()
    stick_to_primary_var.set(True)
    force_primary_var.set(True)

    with replica_context():
        assert stick_to_primary_var.get() is False
        assert force_primary_var.get() is False

    assert stick_to_primary_var.get() is True
    assert force_primary_var.get() is True


def test_replica_context_resets_on_exception() -> None:
    """Test that replica_context properly resets flags on exception."""
    reset_routing_context()
    stick_to_primary_var.set(True)
    force_primary_var.set(True)

    def _raise_in_replica_context() -> None:
        with replica_context():
            assert stick_to_primary_var.get() is False
            assert force_primary_var.get() is False
            raise ValueError("test exception")

    with pytest.raises(ValueError):
        _raise_in_replica_context()

    assert stick_to_primary_var.get() is True
    assert force_primary_var.get() is True


def test_context_vars_are_isolated_per_context() -> None:
    """Test that context variables are isolated per execution context."""
    from contextvars import copy_context

    reset_routing_context()

    def set_force() -> None:
        force_primary_var.set(True)

    ctx = copy_context()
    ctx.run(set_force)

    assert force_primary_var.get() is False

    assert ctx.run(lambda: force_primary_var.get()) is True


def test_primary_and_replica_contexts_can_be_nested() -> None:
    """Test that primary_context and replica_context can be nested."""
    reset_routing_context()

    stick_to_primary_var.set(True)

    with replica_context():
        assert stick_to_primary_var.get() is False
        assert force_primary_var.get() is False

        with primary_context():
            assert force_primary_var.get() is True
            assert stick_to_primary_var.get() is False

        assert force_primary_var.get() is False

    assert stick_to_primary_var.get() is True
    assert force_primary_var.get() is False


def test_context_manager_as_decorator_not_supported() -> None:
    """Test that context managers are not meant to be used as decorators.

    This is a documentation test - the context managers should be used
    with 'with' statements, not as function decorators.
    """
    reset_routing_context()

    with primary_context():
        assert force_primary_var.get() is True

    assert force_primary_var.get() is False
