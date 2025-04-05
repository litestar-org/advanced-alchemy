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


class PendingType:
    def __repr__(self) -> str:
        return "AsyncPending"


Pending = PendingType()


class PendingValueError(Exception):
    """Exception raised when a value is accessed before it is ready."""


class SoonValue(Generic[T]):
    """Holds a value that will be available soon after an async operation."""

    def __init__(self) -> None:
        self._stored_value: Union[T, PendingType] = Pending

    @property
    def value(self) -> "T":
        if isinstance(self._stored_value, PendingType):
            msg = "The return value of this task is still pending."
            raise PendingValueError(msg)
        return self._stored_value

    @property
    def ready(self) -> bool:
        return not isinstance(self._stored_value, PendingType)


class TaskGroup:
    """Manages a group of asyncio tasks, allowing them to be run concurrently."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._exceptions: list[BaseException] = []
        self._closed = False

    async def __aenter__(self) -> "TaskGroup":
        if self._closed:
            msg = "Cannot enter a task group that has already been closed."
            raise RuntimeError(msg)
        return self

    async def __aexit__(
        self,
        exc_type: "Optional[type[BaseException]]",  # noqa: PYI036
        exc_val: "Optional[BaseException]",  # noqa: PYI036
        exc_tb: "Optional[TracebackType]",  # noqa: PYI036
    ) -> None:
        self._closed = True
        if exc_val:
            self._exceptions.append(exc_val)

        if self._tasks:
            await asyncio.wait(self._tasks)

        if self._exceptions:
            # Re-raise the first exception encountered.
            raise self._exceptions[0]

    def create_task(self, coro: "Coroutine[Any, Any, Any]") -> "asyncio.Task[Any]":
        """Create and add a coroutine as a task to the task group.

        Args:
            coro (Coroutine): The coroutine to be added as a task.

        Returns:
            asyncio.Task: The created asyncio task.

        Raises:
            RuntimeError: If the task group has already been closed.
        """
        if self._closed:
            msg = "Cannot create a task in a task group that has already been closed."
            raise RuntimeError(msg)
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._check_result)
        return task

    def _check_result(self, task: "asyncio.Task[Any]") -> None:
        """Check and store exceptions from a completed task.

        Args:
            task (asyncio.Task): The task to check for exceptions.
        """
        try:
            task.result()  # This will raise the exception if one occurred.
        except Exception as e:  # noqa: BLE001
            self._exceptions.append(e)

    def start_soon_(
        self,
        async_function: "Callable[ParamSpecT, Awaitable[T]]",
        name: object = None,
    ) -> "Callable[ParamSpecT, SoonValue[T]]":
        """Create a function to start a new task in this task group.

        Args:
            async_function (Callable): An async function to call soon.
            name (object, optional): Name of the task for introspection and debugging.

        Returns:
            Callable: A function that starts the task and returns a SoonValue object.
        """

        @functools.wraps(async_function)
        def wrapper(*args: "ParamSpecT.args", **kwargs: "ParamSpecT.kwargs") -> "SoonValue[T]":
            partial_f = functools.partial(async_function, *args, **kwargs)
            soon_value: SoonValue[T] = SoonValue()

            @functools.wraps(partial_f)
            async def value_wrapper(*_args: "Any") -> None:
                value = await partial_f()
                soon_value._stored_value = value  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

            self.create_task(value_wrapper)  # type: ignore[arg-type]
            return soon_value

        return wrapper


def create_task_group() -> "TaskGroup":
    """Create a TaskGroup for managing multiple concurrent async tasks.

    Returns:
        TaskGroup: A new TaskGroup instance.
    """
    return TaskGroup()


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


_default_limiter = CapacityLimiter(40)


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

        if loop is None and raise_sync_error is False:
            return asyncio.run(partial_f())
        # Running in an existing event loop
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


def maybe_async_(
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


def wrap_sync(fn: "Callable[ParamSpecT, ReturnT]") -> "Callable[ParamSpecT, Awaitable[ReturnT]]":
    """Convert a sync function to an async one.

    Args:
        fn (Callable): The function to convert.

    Returns:
        Callable: An async function that runs the original function.
    """
    if inspect.iscoroutinefunction(fn):
        return fn

    async def wrapped(*args: "ParamSpecT.args", **kwargs: "ParamSpecT.kwargs") -> ReturnT:
        return await async_(functools.partial(fn, *args, **kwargs))()

    return wrapped


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


def maybe_async_context(
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
