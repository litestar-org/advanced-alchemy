"""Context variables and context managers for read/write routing.

This module provides the context-based state management for routing decisions,
including the sticky-to-primary behavior after writes.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = (
    "force_primary_var",
    "primary_context",
    "replica_context",
    "reset_routing_context",
    "stick_to_primary_var",
)


# Context variable for sticky-to-primary state after writes
stick_to_primary_var: ContextVar[bool] = ContextVar("stick_to_primary", default=False)
"""Context variable tracking if we should stick to primary after a write.

When ``True``, all operations (including reads) will use the primary database
until the context is reset (typically after commit/rollback).
"""

# Context variable for forcing primary regardless of operation type
force_primary_var: ContextVar[bool] = ContextVar("force_primary", default=False)
"""Context variable for explicitly forcing all operations to primary.

When ``True``, all operations will use the primary database regardless
of operation type or stickiness state.
"""


@contextmanager
def primary_context() -> Generator[None, None, None]:
    """Force all operations to use primary within this context.

    Use this context manager when you need to ensure all database operations
    (including reads) go to the primary database.

    Example:
        Force a specific query to use the primary database::

            from advanced_alchemy.routing import primary_context

            async with primary_context():
                # All queries in this block use primary
                user = await repo.get(user_id)
                orders = await order_repo.list()

    Yields:
        None
    """
    token: Token[bool] = force_primary_var.set(True)
    try:
        yield
    finally:
        force_primary_var.reset(token)


@contextmanager
def replica_context() -> Generator[None, None, None]:
    """Force read operations to use replicas (temporarily disable stickiness).

    Use this context manager when you want to explicitly allow reads to go
    to replicas, even if a previous write has set the sticky-to-primary state.

    .. warning::
        Use with caution! This can lead to read-after-write inconsistency
        if you're reading data that was recently written.

    Example:
        Allow reads to use replicas after a write::

            from advanced_alchemy.routing import replica_context

            # After a write, stickiness is set
            await repo.add(user)

            # This read will still use primary due to stickiness
            user = await repo.get(user_id)

            # But within replica_context, reads use replicas
            async with replica_context():
                # This may return stale data if replica hasn't caught up
                users = await repo.list()

    Yields:
        None
    """
    stick_token: Token[bool] = stick_to_primary_var.set(False)
    force_token: Token[bool] = force_primary_var.set(False)
    try:
        yield
    finally:
        stick_to_primary_var.reset(stick_token)
        force_primary_var.reset(force_token)


def reset_routing_context() -> None:
    """Reset all routing context variables to their defaults.

    This is typically called after a commit or rollback to allow
    subsequent reads to use replicas again.

    Example:
        Manual reset after transaction::

            from advanced_alchemy.routing import reset_routing_context

            await session.commit()
            reset_routing_context()
            # Now reads can use replicas again
    """
    # Reset by setting to default values
    # Note: We can't use reset() without tokens, so we set to defaults
    stick_to_primary_var.set(False)
    force_primary_var.set(False)


def set_sticky_primary() -> None:
    """Set the sticky-to-primary flag.

    This is called internally after write operations to ensure
    subsequent reads use the primary database.
    """
    stick_to_primary_var.set(True)


def should_use_primary() -> bool:
    """Check if we should route to the primary database.

    Returns:
        ``True`` if routing should use primary (due to force or stickiness).
    """
    return force_primary_var.get() or stick_to_primary_var.get()
