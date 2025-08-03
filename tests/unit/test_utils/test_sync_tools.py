import asyncio
from collections.abc import AsyncIterator, Awaitable, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Callable, Optional, TypeVar

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


async def test_async_() -> None:
    def sync_func(x: int) -> int:
        return x * 2

    async_func = async_(sync_func)
    assert await async_func(21) == 42


async def test_capacity_limiter_setter() -> None:
    limiter = CapacityLimiter(2)
    assert limiter.total_tokens == 2
    limiter.total_tokens = 5
    assert limiter.total_tokens == 5


async def test_capacity_limiter_release_without_acquire() -> None:
    limiter = CapacityLimiter(1)
    # Release without acquire should not raise, but will increase tokens beyond initial
    limiter.release()
    assert limiter.total_tokens == 2


async def test_run_with_running_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    async def async_func(x: int) -> int:
        return x * 2

    sync_func = run_(async_func)

    # Simulate running loop
    class DummyLoop:
        def is_running(self) -> bool:
            return True

    monkeypatch.setattr("asyncio.get_running_loop", lambda: DummyLoop())

    # Suppress the expected warning about unawaited coroutine
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine .* was never awaited")
        with pytest.raises(Exception):
            sync_func(1)


def test_run_with_uvloop(monkeypatch: pytest.MonkeyPatch) -> None:
    async def async_func(x: int) -> int:
        return x * 2

    sync_func = run_(async_func)
    monkeypatch.setattr(
        "advanced_alchemy.utils.sync_tools.uvloop", type("UVLoop", (), {"install": staticmethod(lambda: None)})()
    )
    monkeypatch.setattr("sys.platform", "linux")
    # Should not raise
    assert sync_func(2) == 4


def test_await_no_loop_raises() -> None:
    async def async_func(x: int) -> int:
        return x * 2

    sync_func = await_(async_func, raise_sync_error=True)
    # Remove running loop
    orig = asyncio.get_running_loop
    asyncio.get_running_loop = lambda: (_ for _ in ()).throw(RuntimeError())
    try:
        with pytest.raises(RuntimeError, match="await_ called without a running event loop"):
            sync_func(1)
    finally:
        asyncio.get_running_loop = orig


def test_await_in_async_task(monkeypatch: pytest.MonkeyPatch) -> None:
    from typing import Optional

    async def async_func(x: int) -> int:
        return x * 2

    sync_func = await_(async_func, raise_sync_error=True)

    class DummyLoop:
        def is_running(self) -> bool:
            return True

    class DummyTask:
        pass

    monkeypatch.setattr("asyncio.get_running_loop", lambda: DummyLoop())

    def dummy_current_task(loop: Optional[object] = None) -> DummyTask:
        return DummyTask()

    monkeypatch.setattr("asyncio.current_task", dummy_current_task)
    with pytest.raises(RuntimeError, match="await_ cannot be called from within an async task"):
        sync_func(1)


def test_await_non_running_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    async def async_func(x: int) -> int:
        return x * 2

    sync_func = await_(async_func, raise_sync_error=True)

    class DummyLoop:
        def is_running(self) -> bool:
            return False

    monkeypatch.setattr("asyncio.get_running_loop", lambda: DummyLoop())
    with pytest.raises(RuntimeError, match="await_ found a non-running loop"):
        sync_func(1)


def test_ensure_async_identity() -> None:
    async def afunc(x: int) -> int:
        return x

    wrapped: Callable[[int], Awaitable[int]] = ensure_async_(afunc)
    assert wrapped is afunc


def test_ensure_async_awaitable() -> None:
    def sync_func(x: int) -> Awaitable[int]:
        async def coro() -> int:
            return x * 2

        return coro()

    wrapped: Callable[[int], Awaitable[int]] = ensure_async_(sync_func)

    async def runner() -> int:
        return await wrapped(21)

    assert asyncio.run(runner()) == 42


def test_ensure_async_non_awaitable() -> None:
    def sync_func(x: int) -> int:
        return x * 2

    wrapped = ensure_async_(sync_func)

    async def runner() -> int:
        return await wrapped(21)

    assert asyncio.run(runner()) == 42


def test_context_manager_wrapper_exceptions() -> None:
    from types import TracebackType

    class DummyCM:
        def __enter__(self) -> int:
            raise ValueError("enter error")

        def __exit__(
            self,
            exc_type: Optional[type[BaseException]],
            exc_val: Optional[BaseException],
            exc_tb: Optional[TracebackType],
        ) -> None:
            raise ValueError("exit error")

    wrapper = with_ensure_async_(DummyCM())
    with pytest.raises(ValueError, match="enter error"):
        asyncio.run(wrapper.__aenter__())
    # __aexit__ should propagate exception
    with pytest.raises(ValueError, match="exit error"):
        asyncio.run(wrapper.__aexit__(None, None, None))


def test_with_ensure_async_identity() -> None:
    from types import TracebackType

    class DummyAsyncCM:
        async def __aenter__(self) -> int:
            return 42

        async def __aexit__(
            self,
            exc_type: Optional[type[BaseException]],
            exc_val: Optional[BaseException],
            exc_tb: Optional[TracebackType],
        ) -> None:
            return None

    acm = DummyAsyncCM()
    assert with_ensure_async_(acm) is acm


async def test_async_with_custom_limiter() -> None:
    def sync_func(x: int) -> int:
        return x * 2

    limiter = CapacityLimiter(1)
    async_func = async_(sync_func, limiter=limiter)

    async def runner() -> int:
        return await async_func(21)

    assert await runner() == 42
