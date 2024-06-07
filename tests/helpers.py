from __future__ import annotations

import inspect
from contextlib import AbstractContextManager
from functools import partial
from typing import TYPE_CHECKING, AsyncContextManager, Awaitable, Callable, ContextManager, TypeVar, cast, overload

import anyio
from typing_extensions import ParamSpec

if TYPE_CHECKING:
    from types import TracebackType

T = TypeVar("T")
P = ParamSpec("P")


class _ContextManagerWrapper:
    def __init__(self, cm: ContextManager[T]) -> None:
        self._cm = cm

    async def __aenter__(self) -> T:  # pyright: ignore
        return self._cm.__enter__()  # pyright: ignore

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        return self._cm.__exit__(exc_type, exc_val, exc_tb)


@overload
async def maybe_async(obj: Awaitable[T]) -> T: ...


@overload
async def maybe_async(obj: T) -> T: ...


async def maybe_async(obj: Awaitable[T] | T) -> T:
    return cast(T, await obj) if inspect.isawaitable(obj) else cast(T, obj)


def maybe_async_cm(obj: ContextManager[T] | AsyncContextManager[T]) -> AsyncContextManager[T]:
    if isinstance(obj, AbstractContextManager):
        return cast(AsyncContextManager[T], _ContextManagerWrapper(obj))
    return obj


def wrap_sync(fn: Callable[P, T]) -> Callable[P, Awaitable[T]]:
    if inspect.iscoroutinefunction(fn):
        return fn

    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))  # pyright: ignore

    return wrapped
