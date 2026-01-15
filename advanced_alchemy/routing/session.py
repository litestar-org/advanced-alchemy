"""Routing-aware session classes for read/write routing.

This module provides custom SQLAlchemy session classes that implement
read/write routing via the ``get_bind()`` method.
"""

from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy import Delete, Insert, Update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.routing.context import (
    bind_group_var,
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
    from advanced_alchemy.routing.selectors import EngineSelector


__all__ = (
    "RoutingAsyncSession",
    "RoutingSyncSession",
)


class RoutingSyncSession(Session):
    """Synchronous session with read/write routing via ``get_bind()``.

    This session class extends SQLAlchemy's :class:`Session` to provide
    automatic routing of operations to different engine groups (e.g. writer/reader).

    The routing decision is made in ``get_bind()`` based on:
    1. Execution options (``bind_group``)
    2. Context variables (``bind_group``, ``force_primary``)
    3. Stickiness state
    4. Operation type (Write vs Read)

    Attributes:
        _default_engine: The default (write) database engine.
        _selectors: Map of group names to engine selectors.
        _routing_config: Configuration for routing behavior.
    """

    _default_engine: "Engine"
    _selectors: "dict[str, EngineSelector[Engine]]"
    _routing_config: "RoutingConfig"

    def __init__(
        self,
        routing_config: "RoutingConfig",
        selectors: "dict[str, EngineSelector[Engine]]",
        default_engine: "Engine",
        **kwargs: Any,
    ) -> None:
        """Initialize the routing session.

        Args:
            routing_config: Configuration for routing behavior.
            selectors: Map of group names to engine selectors.
            default_engine: The default (fallback/write) engine.
            **kwargs: Additional arguments passed to the parent Session.
        """
        kwargs.pop("bind", None)
        kwargs.pop("binds", None)
        super().__init__(**kwargs)
        self._default_engine = default_engine
        self._selectors = selectors
        self._routing_config = routing_config

    def get_bind(
        self,
        mapper: Optional[Union["Mapper[Any]", type[Any]]] = None,
        clause: Optional[Any] = None,
        **kwargs: Any,
    ) -> "Engine":
        """Route to appropriate engine based on operation and context.

        Args:
            mapper: Optional mapper for the operation.
            clause: The SQL clause being executed.
            **kwargs: Additional keyword arguments.

        Returns:
            The selected engine.
        """
        # 1. Check for explicit bind group in execution options
        if clause is not None and hasattr(clause, "_execution_options"):
            bind_group = clause._execution_options.get("bind_group")  # noqa: SLF001
            if bind_group:
                return self._get_engine_for_group(bind_group)

        # 2. Check context variable for bind group
        bind_group = bind_group_var.get()
        if bind_group:
            return self._get_engine_for_group(bind_group)

        # 3. Check if we should force/stick to default (writer)
        if self._should_use_default_group(clause):
            return self._get_engine_for_group(self._routing_config.default_group)

        # 4. Read operation -> use read group
        return self._get_engine_for_group(self._routing_config.read_group)

    def _get_engine_for_group(self, group: str) -> "Engine":
        """Get an engine for the specified group.

        Args:
            group: Name of the engine group.

        Returns:
            An engine from the group, or the default engine if group not found.
        """
        if group in self._selectors:
            selector = self._selectors[group]
            if selector.has_engines():
                return selector.next()

        # Fallback to default engine if group has no selector/engines
        # or if it's the default group and we want to be safe
        return self._default_engine

    def _should_use_default_group(self, clause: Optional[Any]) -> bool:
        """Determine if the operation should use the default (writer) group.

        Args:
            clause: The SQL clause being executed.

        Returns:
            ``True`` if default group should be used.
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
        """Commit the transaction and reset routing state."""
        super().commit()
        if self._routing_config.reset_stickiness_on_commit:
            reset_routing_context()

    def rollback(self) -> None:
        """Rollback the transaction and reset routing state."""
        super().rollback()
        reset_routing_context()


class RoutingAsyncSession(AsyncSession):
    """Async session with read/write routing support.

    Wraps :class:`RoutingSyncSession` to provide async routing capabilities.
    """

    sync_session_class: "type[Session]" = RoutingSyncSession

    def __init__(
        self,
        routing_config: "RoutingConfig",
        selectors: "dict[str, EngineSelector[AsyncEngine]]",
        default_engine: "AsyncEngine",
        **kwargs: Any,
    ) -> None:
        """Initialize the async routing session.

        Args:
            routing_config: Configuration for routing behavior.
            selectors: Map of group names to async engine selectors.
            default_engine: The default (fallback/write) async engine.
            **kwargs: Additional arguments passed to the parent AsyncSession.
        """
        kwargs.pop("bind", None)
        kwargs.pop("binds", None)

        # Convert async selectors to sync selectors for the wrapped session
        sync_selectors = {name: _SyncEngineSelectorWrapper(selector) for name, selector in selectors.items()}

        super().__init__(
            sync_session_class=RoutingSyncSession,
            routing_config=routing_config,
            selectors=sync_selectors,
            default_engine=default_engine.sync_engine,
            **kwargs,
        )
        self._default_engine = default_engine
        self._selectors = selectors
        self._routing_config = routing_config

    @property
    def primary_engine(self) -> "AsyncEngine":
        """Get the primary (default) async engine.

        Returns:
            The default database engine.
        """
        return self._default_engine

    @property
    def routing_config(self) -> "RoutingConfig":
        """Get the routing configuration.

        Returns:
            The routing configuration.
        """
        return self._routing_config


class _SyncEngineSelectorWrapper:
    """Wrapper to adapt async engine selector for sync session.

    This wrapper extracts sync engines from async engines in the selector.
    """

    __slots__ = ("_async_selector",)

    def __init__(self, async_selector: "EngineSelector[AsyncEngine]") -> None:
        """Initialize the wrapper.

        Args:
            async_selector: The async engine selector to wrap.
        """
        self._async_selector = async_selector

    def has_engines(self) -> bool:
        """Check if any engines are configured.

        Returns:
            ``True`` if at least one engine is available.
        """
        return self._async_selector.has_engines()

    def next(self) -> "Engine":
        """Get the next engine's sync engine.

        Returns:
            The sync engine for the next selection.
        """
        return self._async_selector.next().sync_engine
