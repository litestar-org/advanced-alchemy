from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import TypeVar

import pytest

from advanced_alchemy.utils.sync_tools import (
    CapacityLimiter,
    async_,
    await_,
    ensure_async_,
    run_,
    with_ensure_async_,
)

T = TypeVar("T")


@pytest.mark.asyncio
async def test_ensure_async_() -> None:
    @ensure_async_
    def sync_func(x: int) -> int:
        return x * 2

    @ensure_async_  # type: ignore[arg-type]
    async def async_func(x: int) -> int:
        return x * 2

    assert await sync_func(21) == 42
    assert await async_func(21) == 42


@pytest.mark.asyncio
async def test_with_ensure_async_() -> None:
    @contextmanager
    def sync_cm() -> Iterator[int]:
        yield 42

    @asynccontextmanager
    async def async_cm() -> AsyncIterator[int]:
        yield 42

    async with with_ensure_async_(sync_cm()) as value:
        assert value == 42

    async with with_ensure_async_(async_cm()) as value:
        assert value == 42


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
