from __future__ import annotations

import inspect
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from typing import (
    TYPE_CHECKING,
    AsyncContextManager,
    Awaitable,
    Callable,
    ContextManager,
    Mapping,
    TypeVar,
    cast,
    overload,
)

import anyio
import pytest
from typing_extensions import ParamSpec

if TYPE_CHECKING:
    from types import TracebackType

T = TypeVar("T")
P = ParamSpec("P")


@dataclass
class LazyFixture:
    """Lazy fixture dataclass."""

    name: str


def lazy_fixture(name: str) -> LazyFixture:
    """Mark a fixture as lazy."""
    return LazyFixture(name)


def is_lazy_fixture(value: object) -> bool:
    """Check whether a value is a lazy fixture."""
    return isinstance(value, LazyFixture)


def pytest_make_parametrize_id(
    config: pytest.Config,
    val: object,
    argname: str,
) -> str | None:
    """Inject lazy fixture parametrized id.

    Reference:
    - https://bit.ly/48Off6r

    Args:
        config (pytest.Config): pytest configuration.
        value (object): fixture value.
        argname (str): automatic parameter name.

    Returns:
        str: new parameter id.
    """
    if is_lazy_fixture(val):
        return cast(LazyFixture, val).name
    return None


def _resolve_lazy_fixture(__val: object, request: pytest.FixtureRequest) -> object:
    """Lazy fixture resolver.

    Args:
        __val (object): fixture value object.
        request (pytest.FixtureRequest): pytest fixture request object.

    Returns:
        object: resolved fixture value.
    """
    if isinstance(__val, list | tuple):
        return tuple(_resolve_lazy_fixture(v, request) for v in __val)
    if isinstance(__val, Mapping):
        return {k: _resolve_lazy_fixture(v, request) for k, v in __val.items()}
    if not is_lazy_fixture(__val):
        return __val
    lazy_obj = cast(LazyFixture, __val)
    return request.getfixturevalue(lazy_obj.name)


class _ContextManagerWrapper:
    def __init__(self, cm: ContextManager[T]) -> None:
        self._cm = cm

    async def __aenter__(self) -> T:
        return self._cm.__enter__()

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
        return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))

    return wrapped
