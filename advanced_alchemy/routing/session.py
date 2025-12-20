"""Routing-aware session classes for read/write routing.

This module provides custom SQLAlchemy session classes that implement
read/write routing via the ``get_bind()`` method.
"""

from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy import Delete, Insert, Update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.routing.context import (
    force_primary_var,
    reset_routing_context,
    set_sticky_primary,
    stick_to_primary_var,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.orm import Mapper

    from advanced_alchemy.config.routing import RoutingConfig
    from advanced_alchemy.routing.selectors import ReplicaSelector


__all__ = (
    "RoutingAsyncSession",
    "RoutingSyncSession",
)


class RoutingSyncSession(Session):
    """Synchronous session with read/write routing via ``get_bind()``.

    This session class extends SQLAlchemy's :class:`Session` to provide
    automatic routing of read operations to replicas and write operations
    to the primary database.

    The routing decision is made in ``get_bind()`` based on:
    1. Whether routing is enabled
    2. The ``force_primary`` context variable
    3. The ``stick_to_primary`` context variable (set after writes)
    4. Whether the session is flushing
    5. The type of statement being executed (INSERT/UPDATE/DELETE vs SELECT)
    6. Whether FOR UPDATE is being used

    Attributes:
        _primary_engine: The primary (write) database engine.
        _replica_selector: Selector for choosing read replicas.
        _routing_config: Configuration for routing behavior.
    """

    _primary_engine: "Engine"
    _replica_selector: "ReplicaSelector[Engine]"
    _routing_config: "RoutingConfig"

    def __init__(
        self,
        primary_engine: "Engine",
        replica_selector: "ReplicaSelector[Engine]",
        routing_config: "RoutingConfig",
        **kwargs: Any,
    ) -> None:
        """Initialize the routing session.

        Args:
            primary_engine: The primary (write) database engine.
            replica_selector: Selector for choosing read replicas.
            routing_config: Configuration for routing behavior.
            **kwargs: Additional arguments passed to the parent Session.
        """
        kwargs.pop("bind", None)
        kwargs.pop("binds", None)
        super().__init__(**kwargs)
        self._primary_engine = primary_engine
        self._replica_selector = replica_selector
        self._routing_config = routing_config

    def get_bind(
        self,
        mapper: Optional[Union["Mapper[Any]", type[Any]]] = None,
        clause: Optional[Any] = None,
        **kwargs: Any,
    ) -> "Engine":
        """Route to primary or replica based on operation and context.

        This method implements the routing logic:
        1. If routing is disabled, use primary
        2. If ``force_primary`` is set, use primary
        3. If ``stick_to_primary`` is set (after a write), use primary
        4. If flushing, use primary
        5. If the statement is INSERT/UPDATE/DELETE, use primary and set stickiness
        6. If FOR UPDATE is requested, use primary
        7. Otherwise, use a replica if available

        Args:
            mapper: Optional mapper for the operation.
            clause: The SQL clause being executed.
            **kwargs: Additional keyword arguments.

        Returns:
            The appropriate engine (primary or replica).
        """
        if self._should_use_primary(clause):
            return self._primary_engine

        if self._replica_selector.has_replicas():
            return self._replica_selector.next()

        return self._primary_engine

    def _should_use_primary(self, clause: Optional[Any]) -> bool:
        """Determine if the operation should use the primary database.

        Args:
            clause: The SQL clause being executed.

        Returns:
            ``True`` if primary should be used.
        """
        if not self._routing_config.enabled:
            return True

        if force_primary_var.get():
            return True

        if stick_to_primary_var.get():
            return True

        if self._flushing:
            if self._routing_config.sticky_after_write:
                set_sticky_primary()
            return True

        if clause is not None and isinstance(clause, (Insert, Update, Delete)):
            if self._routing_config.sticky_after_write:
                set_sticky_primary()
            return True

        return self._has_for_update(clause)

    def _has_for_update(self, clause: Optional[Any]) -> bool:
        """Check if the clause has FOR UPDATE.

        Args:
            clause: The SQL clause to check.

        Returns:
            ``True`` if FOR UPDATE is present.
        """
        if clause is None:
            return False
        for_update_arg = getattr(clause, "_for_update_arg", None)
        return for_update_arg is not None

    def commit(self) -> None:
        """Commit the transaction and optionally reset stickiness.

        After a successful commit, the sticky-to-primary state is reset
        if ``reset_stickiness_on_commit`` is enabled in the config.
        """
        super().commit()
        if self._routing_config.reset_stickiness_on_commit:
            reset_routing_context()

    def rollback(self) -> None:
        """Rollback the transaction and reset stickiness.

        On rollback, the sticky-to-primary state is always reset since
        the write that caused the stickiness was rolled back.
        """
        super().rollback()
        reset_routing_context()


class RoutingAsyncSession(AsyncSession):
    """Async session with read/write routing support.

    This session class wraps :class:`RoutingSyncSession` to provide
    async routing capabilities. The actual routing logic is handled
    by the underlying sync session class.

    Example:
        Creating a routing async session::

            session = RoutingAsyncSession(
                primary_engine=primary_engine,
                replica_selector=selector,
                routing_config=config,
            )
    """

    sync_session_class: "type[Session]" = RoutingSyncSession

    def __init__(
        self,
        primary_engine: "AsyncEngine",
        replica_selector: "ReplicaSelector[AsyncEngine]",
        routing_config: "RoutingConfig",
        **kwargs: Any,
    ) -> None:
        """Initialize the async routing session.

        Args:
            primary_engine: The primary (write) async database engine.
            replica_selector: Selector for choosing read replicas.
            routing_config: Configuration for routing behavior.
            **kwargs: Additional arguments passed to the parent AsyncSession.
        """
        kwargs.pop("bind", None)
        kwargs.pop("binds", None)
        super().__init__(
            sync_session_class=RoutingSyncSession,
            primary_engine=primary_engine.sync_engine,
            replica_selector=_SyncReplicaSelectorWrapper(replica_selector),
            routing_config=routing_config,
            **kwargs,
        )
        self._primary_engine = primary_engine
        self._replica_selector = replica_selector
        self._routing_config = routing_config

    @property
    def primary_engine(self) -> "AsyncEngine":
        """Get the primary async engine.

        Returns:
            The primary database engine.
        """
        return self._primary_engine

    @property
    def routing_config(self) -> "RoutingConfig":
        """Get the routing configuration.

        Returns:
            The routing configuration.
        """
        return self._routing_config


class _SyncReplicaSelectorWrapper:
    """Wrapper to adapt async replica selector for sync session.

    This wrapper extracts sync engines from async engines in the selector.
    """

    __slots__ = ("_async_selector",)

    def __init__(self, async_selector: "ReplicaSelector[AsyncEngine]") -> None:
        """Initialize the wrapper.

        Args:
            async_selector: The async replica selector to wrap.
        """
        self._async_selector = async_selector

    def has_replicas(self) -> bool:
        """Check if any replicas are configured.

        Returns:
            ``True`` if replicas are available.
        """
        return self._async_selector.has_replicas()

    def next(self) -> "Engine":
        """Get the next replica's sync engine.

        Returns:
            The sync engine for the next replica.
        """
        return self._async_selector.next().sync_engine
