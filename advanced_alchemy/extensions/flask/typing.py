"""Module providing a Greenlet-based blocking portal that behaves similarly to AnyIO's BlockingPortal,
but without requiring AnyIO or greenback. Instead, the portal uses only greenlet and asyncio.

Usage:
    1. Create an instance of GreenletBlockingPortal (or GreenletBlockingPortalProvider).
    2. Start the portal at application startup or use it within a context manager.
    3. Call ``portal.call(async_function, *args, **kwargs)`` from synchronous code.

Example:
    from advanced_alchemy.extensions.flask.typing import GreenletBlockingPortal

    portal = GreenletBlockingPortal()
    portal.start()  # Start the dedicated greenlet and event loop

    def my_sync_handler():
        result = portal.call(some_async_function, 1, 2)
        return result

    # When your application exits:
    portal.stop()  # Ensures the greenlet receives the sentinel and frees resources
"""

from __future__ import annotations

import asyncio
import queue
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, TypeVar, cast

from greenlet import getcurrent, greenlet

if TYPE_CHECKING:
    from types import TracebackType

R = TypeVar("R")


def switch_to_greenlet(fn: Callable[..., R], *args: Any, **kwargs: Any) -> R:
    """Switches execution to a new greenlet and runs the given function synchronously,
    returning the result.

    This helper is kept for backwards compatibility with older bridging code.
    In most scenarios, you should use GreenletBlockingPortal instead.

    Args:
        fn: The function (sync or async) to run in a new greenlet.
        *args: Positional arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        The result of the function call.
    """
    gl = greenlet(fn)
    return cast("R", gl.switch(*args, **kwargs))


@dataclass
class GreenletBlockingPortal:
    """A portal that runs an asyncio event loop in a dedicated greenlet,
    exposing synchronous methods to call asynchronous functions.

    When .start() is called, a dedicated greenlet and event loop are created.
    All async tasks are run on that single event loop via an internal queue.

    By using a context manager, you ensure automatic resource cleanup:
        with GreenletBlockingPortal() as portal:
            result = portal.call(my_async_func, arg1, arg2)

    Or manually:
        portal = GreenletBlockingPortal()
        portal.start()
        ...
        portal.stop()
    """

    _task_queue: queue.Queue[Optional[tuple[greenlet, Callable[..., Any], tuple[Any, ...], dict[str, Any]]]] = field(  # noqa: UP007
        default_factory=queue.Queue, init=False
    )
    _loop: Optional[asyncio.AbstractEventLoop] = None  # noqa: UP007
    _portal_greenlet: Optional[greenlet] = field(default=None, init=False)  # noqa: UP007
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _active_tasks: set[asyncio.Task[Any]] = field(default_factory=set, init=False)

    def _loop_main(self) -> None:
        """Main function for the dedicated greenlet.
        It waits for tasks in _task_queue. Each task is an async function
        plus arguments. The portal runs each task with run_until_complete()
        and switches back to the caller with the result or raises an exception.
        """
        if self._loop is None:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        item: Any | None = None
        while not self._stop_event.is_set():
            try:
                # Use a timeout to periodically check for the sentinel
                item = self._task_queue.get(timeout=0.1)
            except queue.Empty:
                # If the queue is empty, check if we should stop
                continue

            if item is None:  # pyright: ignore[reportUnnecessaryComparison]
                continue

            caller_greenlet, async_func, args, kwargs = item
            try:
                result = self._loop.run_until_complete(async_func(*args, **kwargs))
            except BaseException as exc:  # Raise back to the caller's greenlet  # noqa: BLE001
                caller_greenlet.throw(exc)
            else:
                caller_greenlet.switch(result)

        # Cleanly shut down the loop once we see the sentinel
        if self._loop is not None:  # pyright: ignore[reportUnnecessaryComparison]
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()
            self._loop = None

    def start(self) -> None:
        """Start the portal's event loop greenlet. If it's already running,
        this is a no-op.
        """
        if self._portal_greenlet and not self._portal_greenlet.dead:
            return
        self._stop_event.clear()  # Reset the stop event
        self._portal_greenlet = greenlet(self._loop_main)
        self._portal_greenlet.switch()

    def stop(self) -> None:
        """Stop the portal's loop by sending 'None' to _task_queue and setting the stop event.
        This tells the loop to exit its while-True block. If the portal is
        already stopped, this call is a no-op.
        """
        if not self._portal_greenlet or self._portal_greenlet.dead:
            return
        self._stop_event.set()  # Signal the loop to stop
        self._task_queue.put(None)  # mypy: ignore[arg-type]
        try:
            self._portal_greenlet.switch()
        except BaseException:  # noqa: BLE001, S110
            # The greenlet may raise or just exit
            pass
        finally:
            self._portal_greenlet = None

    def call(self, async_func: Callable[..., Awaitable[R]], *args: Any, **kwargs: Any) -> R:
        """Call an async function from sync code, blocking until it completes.

        If called from the portal greenlet itself, we just run
        ``run_until_complete()`` directly. Otherwise, we enqueue the job
        and block (switch) until the portal returns a result.

        Args:
            async_func: The async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Whatever the async function returns synchronously
        """
        if self._loop is None:
            msg = "Event loop not started. Call start() first."
            raise RuntimeError(msg)
        if getcurrent() is self._portal_greenlet:
            # Already in the portal's greenlet
            return self._loop.run_until_complete(async_func(*args, **kwargs))

        caller = getcurrent()
        done_event = asyncio.Event()

        async def task_wrapper() -> None:
            try:
                result = await async_func(*args, **kwargs)
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(caller.switch, result)
            except BaseException as exc:  # Raise back to the caller's greenlet  # noqa: BLE001
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(caller.throw, exc)
            finally:
                done_event.set()

        async def schedule_task() -> None:
            assert self._loop is not None  # noqa: S101
            task = self._loop.create_task(task_wrapper())
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
            await done_event.wait()

        _ = self._loop.call_soon_threadsafe(asyncio.create_task, schedule_task())
        return cast("R", caller.switch())  # Wait for result from portal greenlet

    def start_task_soon(self, async_func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Schedule an async function for concurrent execution in the loop,
        without awaiting the result immediately.

        Use this to launch background tasks that do not need to
        return a value to the caller.

        Args:
            async_func: The async function to run
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
        """

        def task_runner() -> None:
            if self._loop is not None:
                task = self._loop.create_task(async_func(*args, **kwargs))
                self._active_tasks.add(task)
                task.add_done_callback(self._active_tasks.discard)

        caller = getcurrent()
        self._task_queue.put((caller, task_runner, (), {}))

    def wrap_async_context_manager(self, manager: Any) -> Any:
        """Wrap an async context manager for usage in synchronous code.

        Example:
            with portal.wrap_async_context_manager(some_async_cm) as val:
                ...
                # runs __aenter__ and __aexit__ under the portal

        Args:
            manager: The async context manager object

        Returns:
            A synchronous context manager
        """
        portal = self

        class SyncContextManager:
            def __enter__(self) -> Any:
                return portal.call(manager.__aenter__)

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                portal.call(manager.__aexit__, exc_type, exc_val, exc_tb)

        return SyncContextManager()

    def __enter__(self) -> GreenletBlockingPortal:  # noqa: PYI034
        """Context manager entry point. Starts the portal if not running."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit point. Stops the portal and frees resources."""
        self.stop()

    def __del__(self) -> None:
        """Finalizer to ensure the portal stops if it hasn't been explicitly stopped."""
        self.stop()


@dataclass
class GreenletBlockingPortalProvider:
    """Provides a GreenletBlockingPortal instance for frameworks like Flask.
    Usage:
        provider = GreenletBlockingPortalProvider()
        with provider as portal:
            # Portal is running
            portal.call(my_async_func)
    """

    portal: GreenletBlockingPortal = field(default_factory=GreenletBlockingPortal)

    def __enter__(self) -> GreenletBlockingPortal:
        return self.portal

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None: ...


GREENLET_INSTALLED = True
"""Flag indicating greenlet is installed."""

__all__ = (
    "GREENLET_INSTALLED",
    "GreenletBlockingPortal",
    "GreenletBlockingPortalProvider",
    "switch_to_greenlet",
)
