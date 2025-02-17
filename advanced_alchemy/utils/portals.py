"""This module provides a portal provider and portal for calling async functions from synchronous code."""

import asyncio
import functools
import queue
import threading
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Optional, TypeVar, cast
from warnings import warn

from advanced_alchemy.exceptions import ImproperConfigurationError

if TYPE_CHECKING:
    from collections.abc import Coroutine

__all__ = ("Portal", "PortalProvider", "PortalProviderSingleton")

_R = TypeVar("_R")


class PortalProviderSingleton(type):
    """A singleton metaclass for PortalProvider."""

    _instances: "ClassVar[dict[type, PortalProvider]]" = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> "PortalProvider":
        if cls not in cls._instances:  # pyright: ignore[reportUnnecessaryContains]
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]


class PortalProvider(metaclass=PortalProviderSingleton):
    """A provider for creating and managing threaded portals."""

    def __init__(self) -> None:
        """Initialize the PortalProvider."""
        self._request_queue: queue.Queue[
            tuple[
                Callable[..., Coroutine[Any, Any, Any]],
                tuple[Any, ...],
                dict[str, Any],
                queue.Queue[tuple[Optional[Any], Optional[Exception]]],
            ]
        ] = queue.Queue()
        self._result_queue: queue.Queue[tuple[Optional[Any], Optional[Exception]]] = queue.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready_event: threading.Event = threading.Event()

    @property
    def portal(self) -> "Portal":
        """The portal instance."""
        return Portal(self)

    @property
    def is_running(self) -> bool:
        """Whether the portal provider is running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_ready(self) -> bool:
        """Whether the portal provider is ready."""
        return self._ready_event.is_set()

    @property
    def loop(self) -> "asyncio.AbstractEventLoop":  # pragma: no cover
        """The event loop."""
        if self._loop is None:
            msg = "The PortalProvider is not started.  Did you forget to call .start()?"
            raise ImproperConfigurationError(msg)
        return self._loop

    def start(self) -> None:
        """Starts the background thread and event loop."""
        if self._thread is not None:  # pragma: no cover
            warn("PortalProvider already started", stacklevel=2)
            return
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        self._ready_event.wait()  # Wait for the loop to be ready

    def stop(self) -> None:
        """Stops the background thread and event loop."""
        if self._loop is None or self._thread is None:
            return

        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()
        self._loop = None
        self._thread = None
        self._ready_event.clear()

    def _run_event_loop(self) -> None:  # pragma: no cover
        """The main function of the background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready_event.set()  # Signal that the loop is ready

        self._loop.run_forever()

    async def _async_caller(
        self,
        func: "Callable[..., Coroutine[Any, Any, _R]]",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> _R:
        """Wrapper to run the async function and send the result to the result queue."""
        result: _R = await func(*args, **kwargs)
        return result

    def call(self, func: "Callable[..., Coroutine[Any, Any, _R]]", *args: Any, **kwargs: Any) -> _R:
        """Calls an async function from a synchronous context.

        Args:
            func: The async function to call.
            *args: Positional arguments to the function.
            **kwargs: Keyword arguments to the function.

        Returns:
            The result of the async function.

        Raises:
            Exception: If the async function raises an exception.
        """
        if self._loop is None:
            msg = "The PortalProvider is not started.  Did you forget to call .start()?"
            raise ImproperConfigurationError(msg)

        # Create a new result queue
        local_result_queue: queue.Queue[tuple[Optional[_R], Optional[Exception]]] = queue.Queue()

        # Send the request to the background thread
        self._request_queue.put((func, args, kwargs, local_result_queue))

        # Trigger the execution in the event loop
        _handle = self._loop.call_soon_threadsafe(self._process_request)

        # Wait for the result from the background thread
        result, exception = local_result_queue.get()

        if exception:
            raise exception
        return cast("_R", result)

    def _process_request(self) -> None:  # pragma: no cover
        """Processes a request from the request queue in the event loop."""
        assert self._loop is not None  # noqa: S101

        if not self._request_queue.empty():
            func, args, kwargs, local_result_queue = self._request_queue.get()
            future = asyncio.run_coroutine_threadsafe(self._async_caller(func, args, kwargs), self._loop)

            # Attach a callback to handle the result/exception
            future.add_done_callback(
                functools.partial(self._handle_future_result, local_result_queue=local_result_queue),  # pyright: ignore[reportArgumentType]
            )

    def _handle_future_result(
        self,
        future: "asyncio.Future[Any]",
        local_result_queue: "queue.Queue[tuple[Optional[Any], Optional[Exception]]]",
    ) -> None:  # pragma: no cover
        """Handles the result or exception from the completed future."""
        try:
            result = future.result()
            local_result_queue.put((result, None))
        except Exception as e:  # noqa: BLE001
            local_result_queue.put((None, e))


class Portal:
    def __init__(self, provider: "PortalProvider") -> None:
        self._provider = provider

    def call(self, func: "Callable[..., Coroutine[Any, Any, _R]]", *args: Any, **kwargs: Any) -> _R:
        """Calls an async function using the associated PortalProvider."""
        return self._provider.call(func, *args, **kwargs)
