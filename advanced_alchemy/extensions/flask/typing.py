"""This is a simple wrapper around a few important classes that are optionally used in the Flask extension."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from types import TracebackType

try:
    from anyio.from_thread import BlockingPortal, BlockingPortalProvider  # pyright: ignore[reportAssignmentType]

    ANYIO_INSTALLED = True
except ImportError:

    class BlockingPortal:  # type: ignore[no-redef]
        """Shim implementation of AnyIO's BlockingPortal interface."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Initialize the portal shim."""
            self._stopped = False

        def call(self, async_fn: Any, *args: Any, **kwargs: Any) -> Any:
            """Shim for calling async functions."""
            return None

        def start_task_soon(self, async_fn: Any, *args: Any, **kwargs: Any) -> None:
            """Shim for starting background tasks."""

        def stop(self, *args: Any, **kwargs: Any) -> None:
            """Shim for stopping the portal."""
            self._stopped = True

        def wrap_async_context_manager(self, context_manager: Any) -> Any:
            """Shim for wrapping async context managers."""
            return {}

    @dataclass
    class BlockingPortalProvider(Protocol):  # type: ignore[no-redef]
        """Shim implementation of AnyIO's BlockingPortalProvider interface."""

        _portal: BlockingPortal

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Initialize the provider shim."""
            self._portal = BlockingPortal()

        def __enter__(self) -> BlockingPortal:
            """Enter the context, returning a BlockingPortal instance."""
            return self._portal

        def __exit__(
            self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
        ) -> None:
            """Exit the context, stopping the portal."""
            self._portal.stop()

    ANYIO_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]


__all__ = (
    "ANYIO_INSTALLED",
    "BlockingPortal",
    "BlockingPortalProvider",
)
