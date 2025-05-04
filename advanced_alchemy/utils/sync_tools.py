import asyncio
import functools
import inspect
import sys
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Optional,
    TypeVar,
    Union,
    cast,
)

from typing_extensions import ParamSpec

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine
    from types import TracebackType

try:
    import uvloop  # pyright: ignore[reportMissingImports]
except ImportError:
    uvloop = None  # type: ignore[assignment]


ReturnT = TypeVar("ReturnT")
ParamSpecT = ParamSpec("ParamSpecT")
T = TypeVar("T")


class CapacityLimiter:
    """Limits the number of concurrent operations using a semaphore."""

    def __init__(self, total_tokens: int) -> None:
        self._semaphore = asyncio.Semaphore(total_tokens)

    async def acquire(self) -> None:
        await self._semaphore.acquire()

    def release(self) -> None:
        self._semaphore.release()

    @property
    def total_tokens(self) -> int:
        return self._semaphore._value  # noqa: SLF001

    @total_tokens.setter
    def total_tokens(self, value: int) -> None:
        self._semaphore = asyncio.Semaphore(value)

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(
        self,
        exc_type: "Optional[type[BaseException]]",  # noqa: PYI036
        exc_val: "Optional[BaseException]",  # noqa: PYI036
        exc_tb: "Optional[TracebackType]",  # noqa: PYI036
    ) -> None:
        self.release()


_default_limiter = CapacityLimiter(15)


def run_(async_function: "Callable[ParamSpecT, Coroutine[Any, Any, ReturnT]]") -> "Callable[ParamSpecT, ReturnT]":
    """Convert an async function to a blocking function using asyncio.run().

    Args:
        async_function (Callable): The async function to convert.

    Returns:
        Callable: A blocking function that runs the async function.

    """

    @functools.wraps(async_function)
    def wrapper(*args: "ParamSpecT.args", **kwargs: "ParamSpecT.kwargs") -> "ReturnT":
        partial_f = functools.partial(async_function, *args, **kwargs)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Running in an existing event loop
            return asyncio.run(partial_f())
        # Create a new event loop and run the function
        if uvloop and sys.platform != "win32":
            uvloop.install()  # pyright: ignore[reportUnknownMemberType]
        return asyncio.run(partial_f())

    return wrapper


def await_(
    async_function: "Callable[ParamSpecT, Coroutine[Any, Any, ReturnT]]",
    raise_sync_error: bool = True,
) -> "Callable[ParamSpecT, ReturnT]":
    """Convert an async function to a blocking one, running in the main async loop.

    Args:
        async_function (Callable): The async function to convert.
        raise_sync_error (bool, optional): If False, runs in a new event loop if no loop is present.
                                         If True (default), raises RuntimeError if no loop is running.

    Returns:
        Callable: A blocking function that runs the async function.
    """

    @functools.wraps(async_function)
    def wrapper(*args: "ParamSpecT.args", **kwargs: "ParamSpecT.kwargs") -> "ReturnT":
        partial_f = functools.partial(async_function, *args, **kwargs)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop
            if raise_sync_error:
                msg = "await_ called without a running event loop and raise_sync_error=True"
                raise RuntimeError(msg) from None
            return asyncio.run(partial_f())
        else:
            # Running in an existing event loop.
            if loop.is_running():
                try:
                    # Check if the current context is within a task managed by this loop
                    current_task = asyncio.current_task(loop=loop)
                except RuntimeError:
                    # Not running inside a task managed by this loop
                    current_task = None

                if current_task is not None:
                    # Called from within the event loop's execution context (a task).
                    # Blocking here would deadlock the loop.
                    msg = "await_ cannot be called from within an async task running on the same event loop. Use 'await' instead."
                    raise RuntimeError(msg)
                # Called from a different thread than the loop's thread.
                # It's safe to block this thread and wait for the loop.
                future = asyncio.run_coroutine_threadsafe(partial_f(), loop)
                # This blocks the *calling* thread, not the loop thread.
                return future.result()
            # This case should ideally not happen if get_running_loop() succeeded
            # but the loop isn't running, but handle defensively.
            # loop is not running
            if raise_sync_error:
                msg = "await_ found a non-running loop via get_running_loop()"
                raise RuntimeError(msg)
            # Fallback to running in a new loop
            return asyncio.run(partial_f())

    return wrapper


def async_(
    function: "Callable[ParamSpecT, ReturnT]",
    *,
    limiter: "Optional[CapacityLimiter]" = None,
) -> "Callable[ParamSpecT, Awaitable[ReturnT]]":
    """Convert a blocking function to an async one using asyncio.to_thread().

    Args:
        function (Callable): The blocking function to convert.
        cancellable (bool, optional): Allow cancellation of the operation.
        limiter (CapacityLimiter, optional): Limit the total number of threads.

    Returns:
        Callable: An async function that runs the original function in a thread.
    """

    async def wrapper(
        *args: "ParamSpecT.args",
        **kwargs: "ParamSpecT.kwargs",
    ) -> "ReturnT":
        partial_f = functools.partial(function, *args, **kwargs)
        used_limiter = limiter or _default_limiter
        async with used_limiter:
            return await asyncio.to_thread(partial_f)

    return wrapper


def ensure_async_(
    function: "Callable[ParamSpecT, Union[Awaitable[ReturnT], ReturnT]]",
) -> "Callable[ParamSpecT, Awaitable[ReturnT]]":
    """Convert a function to an async one if it is not already.

    Args:
        function (Callable): The function to convert.

    Returns:
        Callable: An async function that runs the original function.
    """
    if inspect.iscoroutinefunction(function):
        return function

    async def wrapper(*args: "ParamSpecT.args", **kwargs: "ParamSpecT.kwargs") -> "ReturnT":
        result = function(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return await async_(lambda: result)()

    return wrapper


class _ContextManagerWrapper(Generic[T]):
    def __init__(self, cm: AbstractContextManager[T]) -> None:
        self._cm = cm

    async def __aenter__(self) -> T:
        return self._cm.__enter__()

    async def __aexit__(
        self,
        exc_type: "Optional[type[BaseException]]",  # noqa: PYI036
        exc_val: "Optional[BaseException]",  # noqa: PYI036
        exc_tb: "Optional[TracebackType]",  # noqa: PYI036
    ) -> "Optional[bool]":
        return self._cm.__exit__(exc_type, exc_val, exc_tb)


def with_ensure_async_(
    obj: "Union[AbstractContextManager[T], AbstractAsyncContextManager[T]]",
) -> "AbstractAsyncContextManager[T]":
    """Convert a context manager to an async one if it is not already.

    Args:
        obj (AbstractContextManager[T] or AbstractAsyncContextManager[T]): The context manager to convert.

    Returns:
        AbstractAsyncContextManager[T]: An async context manager that runs the original context manager.
    """

    if isinstance(obj, AbstractContextManager):
        return cast("AbstractAsyncContextManager[T]", _ContextManagerWrapper(obj))
    return obj
