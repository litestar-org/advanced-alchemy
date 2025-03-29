import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import TypeVar

import pytest

from advanced_alchemy.utils.sync_tools import (
    CapacityLimiter,
    PendingValueError,
    SoonValue,
    TaskGroup,
    async_,
    await_,
    maybe_async_,
    maybe_async_context,
    run_,
)

T = TypeVar("T")


@pytest.mark.asyncio
async def test_maybe_async() -> None:
    @maybe_async_
    def sync_func(x: int) -> int:
        return x * 2

    @maybe_async_  # type: ignore[arg-type]
    async def async_func(x: int) -> int:
        return x * 2

    assert await sync_func(21) == 42
    assert await async_func(21) == 42


@pytest.mark.asyncio
async def test_maybe_async_context() -> None:
    @contextmanager
    def sync_cm() -> Iterator[int]:
        yield 42

    @asynccontextmanager
    async def async_cm() -> AsyncIterator[int]:
        yield 42

    async with maybe_async_context(sync_cm()) as value:
        assert value == 42

    async with maybe_async_context(async_cm()) as value:
        assert value == 42


@pytest.mark.asyncio
async def test_soon_value() -> None:
    soon_value = SoonValue[int]()
    assert not soon_value.ready
    with pytest.raises(PendingValueError):
        _ = soon_value.value

    setattr(soon_value, "_stored_value", 42)
    assert soon_value.ready
    assert soon_value.value == 42  # type: ignore[unreachable]


@pytest.mark.asyncio
async def test_task_group() -> None:
    async def sample_task(x: int) -> int:
        return x * 2

    async with TaskGroup() as tg:
        task = tg.create_task(sample_task(21))
        await asyncio.wait([task])
        assert task.result() == 42


@pytest.mark.asyncio
async def test_capacity_limiter() -> None:
    limiter = CapacityLimiter(1)

    async with limiter:
        assert limiter.total_tokens == 0

    assert limiter.total_tokens == 1


def test_run_() -> None:
    async def async_func(x: int) -> int:
        return x * 2

    sync_func = run_(async_func)
    assert sync_func(21) == 42


def test_await_() -> None:
    async def async_func(x: int) -> int:
        return x * 2

    sync_func = await_(async_func, raise_sync_error=False)
    assert sync_func(21) == 42


@pytest.mark.asyncio
async def test_async_() -> None:
    def sync_func(x: int) -> int:
        return x * 2

    async_func = async_(sync_func)
    assert await async_func(21) == 42
